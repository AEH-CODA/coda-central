from fastapi import APIRouter, Depends, HTTPException, Header, Query
from sqlalchemy.orm import Session
from uuid import UUID
from jose import jwt, JWTError

from db import get_db
from config import JWT_SECRET, JWT_ALGORITHM
from models import DatasetSaveRequest, DatasetUpdateRequest, DatasetListResponse, DatasetDetailResponse
from services.dataset_service import DatasetService

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
