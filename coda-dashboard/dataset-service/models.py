from pydantic import BaseModel
from datetime import datetime
from uuid import UUID
from typing import Optional, Any

class DatasetSaveRequest(BaseModel):
    """Request to save a new dataset."""
    nl_query: str
    sparql_query: str
    results: Any  # Can be dict, list, or any JSON-serializable object
    name: str
    description: Optional[str] = None

class DatasetUpdateRequest(BaseModel):
    """Request to update dataset metadata."""
    name: Optional[str] = None
    description: Optional[str] = None

class DatasetResponse(BaseModel):
    """Response containing dataset details."""
    id: UUID
    user_id: UUID
    nl_query: str
    sparql_query: str
    name: str
    description: Optional[str] = None
    result_file_path: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

class DatasetListResponse(BaseModel):
    """Response for dataset listing (without large results)."""
    id: UUID
    name: str
    description: Optional[str] = None
    nl_query: str
    sparql_query: str
    created_at: datetime
    
    class Config:
        from_attributes = True

class DatasetDetailResponse(BaseModel):
    """Response containing full dataset including results."""
    id: UUID
    user_id: UUID
    nl_query: str
    sparql_query: str
    results: Any  # Results loaded from file or JSON field
    name: str
    description: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True
