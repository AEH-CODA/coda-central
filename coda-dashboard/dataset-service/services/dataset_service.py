import json
import os
from uuid import UUID
from datetime import datetime
from sqlalchemy.orm import Session
from typing import Optional, List, Any

from db import Dataset
from config import DATA_DIRECTORY
from models import DatasetDetailResponse

class DatasetService:
    """Business logic for dataset operations."""
    
    @staticmethod
    def save_dataset(
        db: Session,
        user_id: UUID,
        nl_query: str,
        sparql_query: str,
        results: Any,
        name: str,
        description: Optional[str] = None
    ) -> Dataset:
        """
        Save a new dataset.
        Stores metadata in DB and results in volume if large.
        """
        # Determine if results should go to file or JSON field
        results_json = json.dumps(results)
        result_file_path = None
        
        # If results are large (>100KB), store in file; otherwise keep in DB
        if len(results_json) > 100000:
            # Generate filename based on dataset ID and timestamp
            filename = f"{user_id}_{datetime.utcnow().timestamp()}.json"
            result_file_path = f"results/{filename}"
            filepath = os.path.join(DATA_DIRECTORY, result_file_path)
            
            # Create results directory if needed
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            
            # Write results to file
            with open(filepath, "w") as f:
                json.dump(results, f)
            
            results_json = None  # Don't store in DB if in file
        
        # Create dataset record
        dataset = Dataset(
            user_id=user_id,
            nl_query=nl_query,
            sparql_query=sparql_query,
            name=name,
            description=description,
            result_file_path=result_file_path,
            result_json=results_json,
        )
        
        db.add(dataset)
        db.commit()
        db.refresh(dataset)
        
        return dataset
    
    @staticmethod
    def get_user_datasets(
        db: Session,
        user_id: UUID,
        skip: int = 0,
        limit: int = 10
    ) -> List[Dataset]:
        """Get paginated list of user's datasets (ordered by creation date DESC)."""
        return db.query(Dataset).filter(
            Dataset.user_id == user_id
        ).order_by(
            Dataset.created_at.desc()
        ).offset(skip).limit(limit).all()
    
    @staticmethod
    def get_user_datasets_count(db: Session, user_id: UUID) -> int:
        """Get total count of user's datasets."""
        return db.query(Dataset).filter(Dataset.user_id == user_id).count()
    
    @staticmethod
    def get_dataset(db: Session, dataset_id: UUID, user_id: UUID) -> Optional[Dataset]:
        """Get a specific dataset, verifying user ownership."""
        return db.query(Dataset).filter(
            Dataset.id == dataset_id,
            Dataset.user_id == user_id
        ).first()
    
    @staticmethod
    def get_dataset_detail(db: Session, dataset_id: UUID, user_id: UUID) -> Optional[DatasetDetailResponse]:
        """Get dataset with results loaded from file or DB."""
        dataset = DatasetService.get_dataset(db, dataset_id, user_id)
        
        if not dataset:
            return None
        
        # Load results from file if stored there
        results = None
        if dataset.result_file_path:
            filepath = os.path.join(DATA_DIRECTORY, dataset.result_file_path)
            if os.path.exists(filepath):
                with open(filepath, "r") as f:
                    results = json.load(f)
            else:
                results = {"error": "Result file not found"}
        elif dataset.result_json:
            results = json.loads(dataset.result_json)
        else:
            results = None
        
        return DatasetDetailResponse(
            id=dataset.id,
            user_id=dataset.user_id,
            nl_query=dataset.nl_query,
            sparql_query=dataset.sparql_query,
            results=results,
            name=dataset.name,
            description=dataset.description,
            created_at=dataset.created_at,
            updated_at=dataset.updated_at,
        )
    
    @staticmethod
    def update_dataset(
        db: Session,
        dataset_id: UUID,
        user_id: UUID,
        name: Optional[str] = None,
        description: Optional[str] = None
    ) -> Optional[Dataset]:
        """Update dataset metadata (name/description only)."""
        dataset = DatasetService.get_dataset(db, dataset_id, user_id)
        
        if not dataset:
            return None
        
        if name is not None:
            dataset.name = name
        if description is not None:
            dataset.description = description
        
        dataset.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(dataset)
        
        return dataset
    
    @staticmethod
    def delete_dataset(db: Session, dataset_id: UUID, user_id: UUID) -> bool:
        """Delete a dataset and its result file if exists."""
        dataset = DatasetService.get_dataset(db, dataset_id, user_id)
        
        if not dataset:
            return False
        
        # Delete result file if it exists
        if dataset.result_file_path:
            filepath = os.path.join(DATA_DIRECTORY, dataset.result_file_path)
            if os.path.exists(filepath):
                try:
                    os.remove(filepath)
                except Exception as e:
                    print(f"Failed to delete result file {filepath}: {str(e)}")
        
        # Delete database record
        db.delete(dataset)
        db.commit()
        
        return True
