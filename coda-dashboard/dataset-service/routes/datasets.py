from fastapi import APIRouter, Depends, HTTPException, Header, Query
from sqlalchemy.orm import Session
from uuid import UUID
from jose import jwt, JWTError

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

router = APIRouter(prefix="/datasets", tags=["datasets"])

def verify_token(authorization: str = Header(...)) -> UUID:
    """
    Verify JWT token and extract user_id.
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
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token: missing sub claim")
        return UUID(user_id)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidSignatureError:
        raise HTTPException(status_code=401, detail="Invalid token signature")
    except jwt.DecodeError:
        raise HTTPException(status_code=401, detail="Invalid token")
    except (JWTError, ValueError) as e:
        raise HTTPException(status_code=401, detail=f"Token validation failed: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=401, detail="Token validation error")


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
        user_id = payload.get("sub")
        role = payload.get("role", "user")  # Default to "user" if role not in token
        
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token: missing sub claim")
        
        return UUID(user_id), role
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidSignatureError:
        raise HTTPException(status_code=401, detail="Invalid token signature")
    except jwt.DecodeError:
        raise HTTPException(status_code=401, detail="Invalid token")
    except (JWTError, ValueError) as e:
        raise HTTPException(status_code=401, detail=f"Token validation failed: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=401, detail="Token validation error")

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
    user_id: UUID = Depends(verify_token)
) -> PreviewResponse:
    """
    Generate a dataset preview (metadata only) for a SPARQL query.
    
    Args:
        req: Preview request containing SPARQL query
        user_id: Verified user ID from JWT (for audit/logging)
    
    Returns:
        Dataset preview with metadata: dataset_summary, column stats, and sample rows
    """
    try:
        # Generate preview metadata
        preview_data = PreviewService.generate_preview(
            req.sparql_query, 
            timeout=SPARQL_QUERY_TIMEOUT
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
    user_id: UUID = Depends(verify_token),
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """
    List all datasets for the authenticated user with pagination.
    
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
    user_id: UUID = Depends(verify_token),
    db: Session = Depends(get_db)
):
    """
    Retrieve full dataset details including results.
    
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
    req: AccessRequestCreateRequest,
    authorization: str = Header(...),
    db: Session = Depends(get_db)
):
    """
    Create a new data access request.
    
    Args:
        req: Access request details (reason, nl_query, sparql_query, data_preview, full results)
        authorization: Bearer token
        db: Database session
    
    Returns:
        Access request ID and status
    """
    try:
        # Extract user_id and role from token
        user_id, role = extract_user_role(authorization)
        
        # Validate reason length
        if not req.reason or len(req.reason) < 10 or len(req.reason) > 500:
            raise HTTPException(
                status_code=400,
                detail="Reason must be between 10 and 500 characters"
            )
        
        access_request = AccessRequestService.create_access_request(
            db=db,
            user_id=user_id,
            reason=req.reason,
            nl_query=req.nl_query,
            sparql_query=req.sparql_query,
            data_preview=req.data_preview,
            full_results=None  # Will be populated by frontend after query execution
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
    full_results: dict,
    user_id: UUID = Depends(verify_token),
    db: Session = Depends(get_db)
):
    """
    Store full query results for an access request (called after full query executes).
    
    Args:
        request_id: Access request ID
        full_results: Full query results dictionary
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
    Get all pending access requests (data manager only).
    
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
        
        if role != "data-manager":
            raise HTTPException(status_code=403, detail="Only data managers can view pending requests")
        
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
    Get all access requests (data manager only) - pending, approved, and rejected.
    
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
        
        if role != "data-manager":
            raise HTTPException(status_code=403, detail="Only data managers can view requests")
        
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
        
        # Only data managers and the requester can view details
        access_request = AccessRequestService.get_request_by_id(db, request_uuid)
        
        if not access_request:
            raise HTTPException(status_code=404, detail="Access request not found")
        
        if role != "data-manager" and access_request.user_id != user_id:
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
    Approve an access request (data manager only).
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
        
        if role != "data-manager":
            raise HTTPException(status_code=403, detail="Only data managers can approve requests")
        
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
    Reject an access request (data manager only).
    
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
        
        if role != "data-manager":
            raise HTTPException(status_code=403, detail="Only data managers can reject requests")
        
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

