from fastapi import APIRouter, Depends, HTTPException, Header, Query, Body, Form, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from uuid import UUID
from jose import jwt, JWTError
import io

from db import get_db
from config import JWT_SECRET, JWT_ALGORITHM, SPARQL_QUERY_TIMEOUT
from models import (
    DatasetSaveRequest, DatasetUpdateRequest, DatasetListResponse, DatasetDetailResponse,
    PreviewRequest, PreviewResponse,
    AccessRequestCreateRequest, AccessRequestResponse, AccessRequestListResponse,
    AccessRequestDetailResponse, AccessRequestApprovalRequest
)
from services.dataset_service import DatasetService
from services.preview_service import PreviewService
from services.access_request_service import AccessRequestService
from services.oauth_client import introspect_is_active

router = APIRouter(prefix="/datasets", tags=["datasets"])

# Roles allowed to review/approve/reject access requests. "admin" additionally
# gets the Role Management page; "data-manager" keeps its original,
# request-review-only privileges.
REQUEST_MANAGER_ROLES = ("admin", "data-manager")

# Roles that see the full dataset directly (paginated, downloadable) instead
# of a 5-row preview, and therefore have no access-request workflow of their
# own to go through.
FULL_ACCESS_ROLES = ("doctor", "admin", "data-manager")

def verify_token(authorization: str = Header(...)) -> UUID:
    """
    Verify JWT token and extract user_id.

    Rejects oauth_access tokens (Connected Apps, e.g. Biomni): every endpoint
    guarded by this dependency is a write or otherwise sensitive operation
    that a connected app's datasets:read grant should never reach. The two
    read endpoints connected apps are meant to use (list/detail) are guarded
    by require_scope() instead.
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Invalid token format",
            headers={"WWW-Authenticate": "Bearer"}
        )

    token = authorization.split(" ")[1]

    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    # python-jose's jwt module has no InvalidSignatureError/DecodeError (those
    # are PyJWT names) — a bad signature or malformed token both surface as
    # JWTError, caught below.
    except (JWTError, ValueError) as e:
        raise HTTPException(status_code=401, detail=f"Token validation failed: {str(e)}")
    except Exception:
        raise HTTPException(status_code=401, detail="Token validation error")

    # Raised outside the try/except above: an HTTPException here must not be
    # re-caught and downgraded by the bare `except Exception` clause.
    if payload.get("token_type") == "oauth_access":
        raise HTTPException(status_code=403, detail="This connected app is not authorized for this action")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token: missing sub claim")
    return UUID(user_id)


def extract_user_role(authorization: str = Header(...)) -> tuple:
    """
    Extract user_id and role from JWT token.
    
    Returns:
        Tuple of (user_id, role)
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Invalid token format",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    token = authorization.split(" ")[1]

    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    # python-jose's jwt module has no InvalidSignatureError/DecodeError (those
    # are PyJWT names) — a bad signature or malformed token both surface as
    # JWTError, caught below.
    except (JWTError, ValueError) as e:
        raise HTTPException(status_code=401, detail=f"Token validation failed: {str(e)}")
    except Exception:
        raise HTTPException(status_code=401, detail="Token validation error")

    if payload.get("token_type") == "oauth_access":
        raise HTTPException(status_code=403, detail="This connected app is not authorized for this action")

    user_id = payload.get("sub")
    role = payload.get("role", "user")  # Default to "user" if role not in token

    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token: missing sub claim")

    return UUID(user_id), role


def extract_user_info(authorization: str = Header(...)) -> tuple:
    """
    Extract user_id, role, and user_name from JWT token.
    
    Returns:
        Tuple of (user_id, role, user_name)
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Invalid token format",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    token = authorization.split(" ")[1]

    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    # python-jose's jwt module has no InvalidSignatureError/DecodeError (those
    # are PyJWT names) — a bad signature or malformed token both surface as
    # JWTError, caught below.
    except (JWTError, ValueError) as e:
        raise HTTPException(status_code=401, detail=f"Token validation failed: {str(e)}")
    except Exception:
        raise HTTPException(status_code=401, detail="Token validation error")

    if payload.get("token_type") == "oauth_access":
        raise HTTPException(status_code=403, detail="This connected app is not authorized for this action")

    user_id = payload.get("sub")
    role = payload.get("role", "user")  # Default to "user" if role not in token
    user_name = payload.get("name", "Unknown User")  # Get user_name from JWT

    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token: missing sub claim")

    return UUID(user_id), role, user_name


def require_scope(required_scope: str):
    """
    Dependency factory for the read endpoints a connected app (e.g. Biomni)
    is allowed to call. Accepts a normal session token from any role
    (unchanged behavior for the CODA UI) or an oauth_access token whose
    granted scope includes `required_scope` — the latter is also checked
    against auth-service's revocation list, since a JWT's signature alone
    can't reflect a since-revoked Connected App grant.
    """
    def dependency(authorization: str = Header(...)) -> UUID:
        if not authorization.startswith("Bearer "):
            raise HTTPException(
                status_code=401,
                detail="Invalid token format",
                headers={"WWW-Authenticate": "Bearer"}
            )

        token = authorization.split(" ")[1]

        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token has expired")
        # python-jose's jwt module has no InvalidSignatureError/DecodeError
        # (those are PyJWT names) — a bad signature or malformed token both
        # surface as JWTError, caught below.
        except (JWTError, ValueError) as e:
            raise HTTPException(status_code=401, detail=f"Token validation failed: {str(e)}")
        except Exception:
            raise HTTPException(status_code=401, detail="Token validation error")

        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token: missing sub claim")

        if payload.get("token_type") == "oauth_access":
            granted_scopes = set(payload.get("scope", "").split())
            if required_scope not in granted_scopes:
                raise HTTPException(status_code=403, detail=f"This connected app is not authorized for '{required_scope}'")
            if not introspect_is_active(token):
                raise HTTPException(status_code=401, detail="This connected app's access has been revoked or expired")

        return UUID(user_id)

    return dependency

@router.post("")
def save_dataset(
    req: DatasetSaveRequest,
    user_id: UUID = Depends(verify_token),
    db: Session = Depends(get_db)
):
    """
    Save a new dataset with query results.
    
    Args:
        req: Dataset save request (nl_query, sparql_query, results, name, description)
        user_id: Verified user ID from JWT
        db: Database session
    
    Returns:
        Dataset ID and created timestamp
    """
    try:
        dataset = DatasetService.save_dataset(
            db=db,
            user_id=user_id,
            nl_query=req.nl_query,
            sparql_query=req.sparql_query,
            results=req.results,
            name=req.name,
            description=req.description
        )
        
        return {
            "dataset_id": str(dataset.id),
            "created_at": dataset.created_at,
            "message": "Dataset saved successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save dataset: {str(e)}")

@router.post("/preview")
def preview_dataset(
    req: PreviewRequest,
    user_role: tuple = Depends(extract_user_role)
) -> PreviewResponse:
    """
    Generate a dataset preview (metadata only) for a SPARQL query.

    Args:
        req: Preview request containing SPARQL query
        user_role: Verified (user_id, role) tuple from JWT

    Returns:
        Dataset preview with metadata: dataset_summary, column stats, and sample rows.
        Doctors, admins, and data managers (FULL_ACCESS_ROLES) receive every
        fetched row in sample_rows rather than being capped at 5, since they
        aren't subject to the request-access workflow.
    """
    user_id, role = user_role
    try:
        # Generate preview metadata
        preview_data = PreviewService.generate_preview(
            req.sparql_query,
            timeout=SPARQL_QUERY_TIMEOUT,
            full_sample=role in FULL_ACCESS_ROLES,
        )

        return PreviewResponse(**preview_data)
        
    except ValueError as e:
        # Invalid query format
        raise HTTPException(status_code=400, detail="Invalid SPARQL query or malformed request")
    except TimeoutError as e:
        # Query execution timeout
        raise HTTPException(status_code=408, detail="Query execution timeout")
    except Exception as e:
        # Other errors
        raise HTTPException(status_code=500, detail="Error processing query results")

@router.get("")
def list_datasets(
    user_id: UUID = Depends(require_scope("datasets:read")),
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """
    List all datasets for the authenticated user with pagination.

    Reachable by a connected app's datasets:read token (e.g. Biomni browsing
    what it can import) as well as the CODA UI's own session token.

    Args:
        user_id: Verified user ID from JWT
        skip: Number of records to skip (pagination)
        limit: Max records to return
        db: Database session

    Returns:
        Paginated list of user's datasets (without results)
    """
    try:
        datasets = DatasetService.get_user_datasets(db, user_id, skip, limit)
        total = DatasetService.get_user_datasets_count(db, user_id)
        
        return {
            "datasets": [
                DatasetListResponse.from_orm(d) for d in datasets
            ],
            "total": total,
            "skip": skip,
            "limit": limit
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list datasets: {str(e)}")

@router.get("/{dataset_id}")
def get_dataset_detail(
    dataset_id: str,
    user_id: UUID = Depends(require_scope("datasets:read")),
    db: Session = Depends(get_db)
):
    """
    Retrieve full dataset details including results.

    Reachable by a connected app's datasets:read token as well as the CODA
    UI's own session token — see require_scope().

    Args:
        dataset_id: Dataset ID to retrieve
        user_id: Verified user ID from JWT
        db: Database session

    Returns:
        Full dataset object with results
    """
    try:
        dataset_uuid = UUID(dataset_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid dataset ID format")

    try:
        dataset_detail = DatasetService.get_dataset_detail(db, dataset_uuid, user_id)

        if not dataset_detail:
            raise HTTPException(status_code=404, detail="Dataset not found")

        return dataset_detail
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve dataset: {str(e)}")


@router.get("/{dataset_id}/export")
def export_dataset_csv(
    dataset_id: str,
    format: str = Query("csv"),
    user_id: UUID = Depends(require_scope("datasets:read")),
    db: Session = Depends(get_db)
):
    """
    Export a saved dataset's results as a downloadable file.

    A CODA "dataset" is stored as SPARQL JSON results, not a CSV — this is
    the endpoint that does that conversion, so any client (Biomni included)
    gets a real CSV rather than having to reimplement the SPARQL-bindings
    flattening logic itself. Only `format=csv` is supported today.
    """
    if format != "csv":
        raise HTTPException(status_code=400, detail="Only format=csv is supported")

    try:
        dataset_uuid = UUID(dataset_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid dataset ID format")

    try:
        dataset_detail = DatasetService.get_dataset_detail(db, dataset_uuid, user_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve dataset: {str(e)}")

    if not dataset_detail:
        raise HTTPException(status_code=404, detail="Dataset not found")

    if not dataset_detail.results:
        raise HTTPException(status_code=422, detail="This dataset has no results to export")

    df = PreviewService.results_to_dataframe(dataset_detail.results)

    buffer = io.StringIO()
    df.to_csv(buffer, index=False)
    buffer.seek(0)

    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in (dataset_detail.name or str(dataset_uuid)))
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}.csv"'},
    )


@router.put("/{dataset_id}")
def update_dataset(
    dataset_id: str,
    req: DatasetUpdateRequest,
    user_id: UUID = Depends(verify_token),
    db: Session = Depends(get_db)
):
    """
    Update dataset metadata (name and/or description).
    
    Args:
        dataset_id: Dataset ID to update
        req: Update request (name, description)
        user_id: Verified user ID from JWT
        db: Database session
    
    Returns:
        Updated dataset metadata
    """
    try:
        dataset_uuid = UUID(dataset_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid dataset ID format")
    
    try:
        dataset = DatasetService.update_dataset(
            db, dataset_uuid, user_id, req.name, req.description
        )
        
        if not dataset:
            raise HTTPException(status_code=404, detail="Dataset not found")
        
        return {
            "id": str(dataset.id),
            "name": dataset.name,
            "description": dataset.description,
            "updated_at": dataset.updated_at,
            "message": "Dataset updated successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update dataset: {str(e)}")

@router.delete("/{dataset_id}")
def delete_dataset(
    dataset_id: str,
    user_id: UUID = Depends(verify_token),
    db: Session = Depends(get_db)
):
    """
    Delete a dataset and its associated result file.
    
    Args:
        dataset_id: Dataset ID to delete
        user_id: Verified user ID from JWT
        db: Database session
    
    Returns:
        Success message
    """
    try:
        dataset_uuid = UUID(dataset_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid dataset ID format")
    
    try:
        success = DatasetService.delete_dataset(db, dataset_uuid, user_id)
        
        if not success:
            raise HTTPException(status_code=404, detail="Dataset not found")
        
        return {"message": "Dataset deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete dataset: {str(e)}")


# ============================================================================
# ACCESS REQUEST ENDPOINTS
# ============================================================================

@router.post("/access-requests/create")
def create_access_request(
    project_name: str = Form(...),
    reason: str = Form(...),
    nl_query: str = Form(...),
    sparql_query: str = Form(...),
    data_preview: str = Form(None),  # JSON string from form
    supporting_document: UploadFile = File(None),  # Optional PDF file
    authorization: str = Header(...),
    db: Session = Depends(get_db)
):
    """
    Create a new data access request with optional PDF support document.
    
    Args:
        project_name: Project requesting access
        reason: Reason for access request
        nl_query: Natural language query
        sparql_query: SPARQL query
        data_preview: JSON string of preview data
        supporting_document: Optional PDF file upload
        authorization: Bearer token
        db: Database session
    
    Returns:
        Access request ID and status
    """
    try:
        import json
        
        # Extract user_id, role, and user_name from token
        user_id, role, user_name = extract_user_info(authorization)

        if role in FULL_ACCESS_ROLES:
            raise HTTPException(
                status_code=403,
                detail="This role already has full dataset access and does not need to request it"
            )

        # Validate project name
        if not project_name or len(project_name.strip()) < 2 or len(project_name.strip()) > 255:
            raise HTTPException(
                status_code=400,
                detail="Project name must be between 2 and 255 characters"
            )
        
        # Validate reason length
        if not reason or len(reason) < 10 or len(reason) > 500:
            raise HTTPException(
                status_code=400,
                detail="Reason must be between 10 and 500 characters"
            )
        
        # Parse data_preview if provided
        preview_data = None
        if data_preview:
            try:
                preview_data = json.loads(data_preview)
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="Invalid preview data format")
        
        # Validate supporting document if provided
        supporting_doc_file = None
        supporting_doc_filename = None
        if supporting_document and supporting_document.filename:
            # Validate file extension
            if not supporting_document.filename.lower().endswith('.pdf'):
                raise HTTPException(
                    status_code=400,
                    detail="Supporting document must be a PDF file"
                )
            
            # Check file size (max 10MB)
            content = supporting_document.file.read()
            if len(content) > 10 * 1024 * 1024:  # 10MB
                raise HTTPException(
                    status_code=400,
                    detail="PDF file size must not exceed 10MB"
                )
            
            # Reset file pointer for service to read
            supporting_document.file.seek(0)
            supporting_doc_file = supporting_document.file
            supporting_doc_filename = supporting_document.filename
        
        access_request = AccessRequestService.create_access_request(
            db=db,
            user_id=user_id,
            user_name=user_name,
            project_name=project_name.strip(),
            reason=reason,
            nl_query=nl_query,
            sparql_query=sparql_query,
            data_preview=preview_data,
            full_results=None,  # Will be populated by frontend after query execution
            supporting_doc_file=supporting_doc_file,
            supporting_doc_filename=supporting_doc_filename
        )
        
        return {
            "request_id": str(access_request.id),
            "status": access_request.status,
            "created_at": access_request.created_at,
            "message": "Access request submitted successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create access request: {str(e)}")  


@router.post("/access-requests/{request_id}/full-results")
def store_access_request_full_results(
    request_id: str,
    full_results: dict = Body(...),
    user_id: UUID = Depends(verify_token),
    db: Session = Depends(get_db)
):
    """
    Store full query results for an access request (called after full query executes).
    
    Args:
        request_id: Access request ID
        full_results: Full query results dictionary (from request body)
        user_id: Verified user ID from JWT
        db: Database session
    
    Returns:
        Success message
    """
    try:
        request_uuid = UUID(request_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid request ID format")
    
    try:
        access_request = AccessRequestService.get_request_by_id(db, request_uuid)
        
        if not access_request:
            raise HTTPException(status_code=404, detail="Access request not found")
        
        if access_request.user_id != user_id:
            raise HTTPException(status_code=403, detail="Not authorized to update this request")
        
        # Store full results (will handle file/DB storage automatically)
        import json
        import os
        from config import DATA_DIRECTORY
        
        results_json = json.dumps(full_results)
        
        if len(results_json) > 100000:
            from datetime import datetime
            filename = f"access_request_{user_id}_{datetime.utcnow().timestamp()}.json"
            result_file_path = f"access_requests/{filename}"
            filepath = os.path.join(DATA_DIRECTORY, result_file_path)
            
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            with open(filepath, "w") as f:
                json.dump(full_results, f)
            
            access_request.result_file_path = result_file_path
            access_request.result_json = None
        else:
            access_request.result_json = results_json
            access_request.result_file_path = None
        
        db.commit()
        
        return {"message": "Full results stored successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to store results: {str(e)}")


@router.get("/access-requests/pending")
def get_pending_requests(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    authorization: str = Header(...),
    db: Session = Depends(get_db)
):
    """
    Get all pending access requests (admin or data-manager only).

    Args:
        skip: Pagination offset
        limit: Pagination limit
        authorization: Bearer token
        db: Database session

    Returns:
        List of pending access requests
    """
    try:
        user_id, role = extract_user_role(authorization)

        if role not in REQUEST_MANAGER_ROLES:
            raise HTTPException(status_code=403, detail="Only admins or data managers can view pending requests")
        
        requests = AccessRequestService.get_pending_requests(db, skip, limit)
        total = AccessRequestService.get_pending_requests_count(db)
        
        return {
            "requests": [
                AccessRequestListResponse.from_orm(r) for r in requests
            ],
            "total": total,
            "skip": skip,
            "limit": limit
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list pending requests: {str(e)}")


@router.get("/access-requests/all")
def get_all_requests(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    authorization: str = Header(...),
    db: Session = Depends(get_db)
):
    """
    Get all access requests (admin or data-manager only) - pending, approved, and rejected.

    Args:
        skip: Pagination offset
        limit: Pagination limit
        authorization: Bearer token
        db: Database session

    Returns:
        List of all access requests
    """
    try:
        user_id, role = extract_user_role(authorization)

        if role not in REQUEST_MANAGER_ROLES:
            raise HTTPException(status_code=403, detail="Only admins or data managers can view requests")
        
        requests = AccessRequestService.get_all_requests(db, skip, limit)
        total = db.query(db.func.count()).from_statement(
            "SELECT COUNT(*) FROM access_requests"
        ).scalar() if hasattr(db, 'func') else len(requests)
        
        return {
            "requests": [
                AccessRequestListResponse.from_orm(r) for r in requests
            ],
            "total": total,
            "skip": skip,
            "limit": limit
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list requests: {str(e)}")


@router.get("/access-requests/user/history")
def get_user_request_history(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    user_id: UUID = Depends(verify_token),
    db: Session = Depends(get_db)
):
    """
    Get access request history for the authenticated user.
    
    Args:
        skip: Pagination offset
        limit: Pagination limit
        user_id: Verified user ID from JWT
        db: Database session
    
    Returns:
        List of user's access requests
    """
    try:
        requests = AccessRequestService.get_user_request_history(db, user_id, skip, limit)
        
        return {
            "requests": [
                AccessRequestListResponse.from_orm(r) for r in requests
            ],
            "skip": skip,
            "limit": limit
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve request history: {str(e)}")


@router.get("/access-requests/{request_id}")
def get_request_detail(
    request_id: str,
    authorization: str = Header(...),
    db: Session = Depends(get_db)
):
    """
    Get detailed view of an access request (including full results).
    
    Args:
        request_id: Access request ID
        authorization: Bearer token
        db: Database session
    
    Returns:
        Full access request details with results
    """
    try:
        request_uuid = UUID(request_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid request ID format")
    
    try:
        user_id, role = extract_user_role(authorization)
        
        # Only admins/data managers and the requester can view details
        access_request = AccessRequestService.get_request_by_id(db, request_uuid)

        if not access_request:
            raise HTTPException(status_code=404, detail="Access request not found")

        if role not in REQUEST_MANAGER_ROLES and access_request.user_id != user_id:
            raise HTTPException(status_code=403, detail="Not authorized to view this request")
        
        request_detail = AccessRequestService.get_request_detail(db, request_uuid)
        
        return request_detail
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve request: {str(e)}")


@router.post("/access-requests/{request_id}/approve")
def approve_access_request(
    request_id: str,
    authorization: str = Header(...),
    db: Session = Depends(get_db)
):
    """
    Approve an access request (admin or data-manager only).
    Creates a new dataset for the user.

    Args:
        request_id: Access request ID to approve
        authorization: Bearer token
        db: Database session

    Returns:
        Success message with created dataset ID
    """
    try:
        request_uuid = UUID(request_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid request ID format")

    try:
        user_id, role = extract_user_role(authorization)

        if role not in REQUEST_MANAGER_ROLES:
            raise HTTPException(status_code=403, detail="Only admins or data managers can approve requests")
        
        access_request = AccessRequestService.approve_request(db, request_uuid, user_id)
        
        if not access_request:
            raise HTTPException(status_code=404, detail="Access request not found")
        
        return {
            "message": "Access request approved successfully",
            "request_id": str(access_request.id),
            "status": access_request.status,
            "approved_at": access_request.reviewed_at
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to approve request: {str(e)}")


@router.post("/access-requests/{request_id}/reject")
def reject_access_request(
    request_id: str,
    req: AccessRequestApprovalRequest,
    authorization: str = Header(...),
    db: Session = Depends(get_db)
):
    """
    Reject an access request (admin or data-manager only).

    Args:
        request_id: Access request ID to reject
        req: Rejection details (action, optional review_reason)
        authorization: Bearer token
        db: Database session

    Returns:
        Success message
    """
    try:
        request_uuid = UUID(request_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid request ID format")

    try:
        user_id, role = extract_user_role(authorization)

        if role not in REQUEST_MANAGER_ROLES:
            raise HTTPException(status_code=403, detail="Only admins or data managers can reject requests")
        
        if req.action != "reject":
            raise HTTPException(status_code=400, detail="Invalid action for this endpoint")
        
        access_request = AccessRequestService.reject_request(
            db, request_uuid, user_id, req.review_reason
        )
        
        if not access_request:
            raise HTTPException(status_code=404, detail="Access request not found")
        
        return {
            "message": "Access request rejected successfully",
            "request_id": str(access_request.id),
            "status": access_request.status,
            "rejected_at": access_request.reviewed_at
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to reject request: {str(e)}")

