from pydantic import BaseModel
from datetime import datetime
from uuid import UUID
from typing import Optional, Any, Dict, List

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


# Preview-related models

class PreviewRequest(BaseModel):
    """Request to generate dataset preview metadata for a SPARQL query."""
    sparql_query: str


class ColumnMetadata(BaseModel):
    """Metadata for a single column in the dataset."""
    name: str
    dtype: str  # "numeric", "categorical", "datetime", "identifier"
    is_patient_id: bool = False  # True if this is the patient ID column
    unique_values: int
    missing_percentage: float
    
    # Numeric column fields
    mean: Optional[float] = None
    min: Optional[float] = None
    max: Optional[float] = None
    std: Optional[float] = None
    distribution: Optional[Dict[str, List[Any]]] = None  # For numeric: {"bins": [...], "counts": [...]}
    
    # Categorical column fields
    top_values: Optional[Dict[str, int]] = None  # Top 5 with counts
    
    # Datetime column fields
    min_date: Optional[str] = None
    max_date: Optional[str] = None


class PatientInsights(BaseModel):
    """Patient-level insights for healthcare datasets."""
    patient_id_column: str
    unique_patients: int
    returning_patients: int
    return_rate_percentage: float
    appearance_distribution: Optional[Dict[str, List[Any]]] = None


class DatasetSummary(BaseModel):
    """High-level summary of dataset."""
    row_count: int
    column_count: int


class PreviewResponse(BaseModel):
    """Response containing dataset preview metadata."""
    dataset_summary: DatasetSummary
    patient_insights: Optional[PatientInsights] = None
    columns: List[ColumnMetadata]
    sample_rows: List[Dict[str, Any]]


# Access Request-related models

class AccessRequestCreateRequest(BaseModel):
    """Request to create a new access request for a dataset."""
    project_name: str  # Project requesting access
    reason: str
    nl_query: str
    sparql_query: str
    data_preview: Optional[Any] = None  # Preview data from /datasets/preview endpoint


class AccessRequestResponse(BaseModel):
    """Response containing access request details."""
    id: UUID
    user_id: UUID
    user_name: str
    project_name: str
    reason: str
    nl_query: str
    sparql_query: str
    data_preview: Optional[Any] = None
    result_file_path: Optional[str] = None
    result_json: Optional[str] = None
    full_results: Optional[Any] = None  # Loaded from file or JSON for frontend
    supporting_doc_path: Optional[str] = None
    supporting_doc_filename: Optional[str] = None
    status: str  # "pending", "approved", "rejected"
    created_at: datetime
    reviewed_by_id: Optional[UUID] = None
    reviewed_at: Optional[datetime] = None
    review_reason: Optional[str] = None
    
    class Config:
        from_attributes = True


class AccessRequestListResponse(BaseModel):
    """Response for access request listing."""
    id: UUID
    user_id: UUID
    user_name: str
    project_name: str
    reason: str
    nl_query: str
    sparql_query: str
    status: str
    created_at: datetime
    reviewed_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class AccessRequestDetailResponse(BaseModel):
    """Response for access request details (includes full data)."""
    id: UUID
    user_id: UUID
    user_name: str
    project_name: str
    reason: str
    nl_query: str
    sparql_query: str
    data_preview: Optional[Any] = None
    result_file_path: Optional[str] = None
    result_json: Optional[str] = None
    full_results: Optional[Any] = None
    supporting_doc_path: Optional[str] = None
    supporting_doc_filename: Optional[str] = None
    status: str
    created_at: datetime
    reviewed_by_id: Optional[UUID] = None
    reviewed_at: Optional[datetime] = None
    review_reason: Optional[str] = None
    
    class Config:
        from_attributes = True


class AccessRequestApprovalRequest(BaseModel):
    """Request to approve or reject an access request."""
    action: str  # "approve" or "reject"
    review_reason: Optional[str] = None  # Reason for rejection
