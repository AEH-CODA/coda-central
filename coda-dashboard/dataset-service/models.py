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
