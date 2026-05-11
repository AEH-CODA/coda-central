"""Service for managing data access requests."""
import json
import os
from uuid import UUID
from datetime import datetime
from typing import Optional, List, Any
from sqlalchemy.orm import Session

from db import AccessRequest, Dataset
from config import DATA_DIRECTORY
from models import AccessRequestDetailResponse

class AccessRequestService:
    """Business logic for access request operations."""
    
    @staticmethod
    def create_access_request(
        db: Session,
        user_id: UUID,
        user_name: str,
        project_name: str,
        reason: str,
        nl_query: str,
        sparql_query: str,
        data_preview: Optional[Any] = None,
        full_results: Optional[Any] = None,
        supporting_doc_file: Optional[Any] = None,
        supporting_doc_filename: Optional[str] = None,
    ) -> AccessRequest:
        """
        Create a new data access request.
        Stores both preview and full results immediately.
        
        Args:
            db: Database session
            user_id: User requesting access
            user_name: Requester's display name from JWT token
            project_name: Project requesting access
            reason: User's reason for needing data
            nl_query: Natural language query
            sparql_query: SPARQL query
            data_preview: Preview data (optional, from frontend)
            full_results: Full query results to store
            supporting_doc_file: Optional file object for PDF document
            supporting_doc_filename: Original filename of the PDF
        
        Returns:
            AccessRequest model instance
        """
        # Store preview
        preview_json = json.dumps(data_preview) if data_preview else None
        
        # Determine if results should go to file or DB
        result_file_path = None
        result_json = None
        
        if full_results:
            results_json = json.dumps(full_results)
            
            # If results > 100KB, store in file; otherwise keep in DB
            if len(results_json) > 100000:
                filename = f"access_request_{user_id}_{datetime.utcnow().timestamp()}.json"
                result_file_path = f"access_requests/{filename}"
                filepath = os.path.join(DATA_DIRECTORY, result_file_path)
                
                os.makedirs(os.path.dirname(filepath), exist_ok=True)
                with open(filepath, "w") as f:
                    json.dump(full_results, f)
            else:
                result_json = results_json
        
        # Store supporting document if provided
        supporting_doc_path = None
        if supporting_doc_file and supporting_doc_filename:
            timestamp = datetime.utcnow().timestamp()
            # Create filename from timestamp and original filename (sanitized)
            sanitized_filename = "".join(c for c in supporting_doc_filename if c.isalnum() or c in ('-', '_', '.'))
            filename = f"{int(timestamp)}_{sanitized_filename}"
            supporting_doc_path = f"access_requests/{user_id}/{filename}"
            filepath = os.path.join(DATA_DIRECTORY, supporting_doc_path)
            
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            # Save the file
            with open(filepath, "wb") as f:
                f.write(supporting_doc_file.read())
        
        # Create access request record
        request = AccessRequest(
            user_id=user_id,
            user_name=user_name,
            project_name=project_name,
            reason=reason,
            nl_query=nl_query,
            sparql_query=sparql_query,
            data_preview=preview_json,
            result_file_path=result_file_path,
            result_json=result_json,
            supporting_doc_path=supporting_doc_path,
            supporting_doc_filename=supporting_doc_filename,
            status="pending"
        )
        
        db.add(request)
        db.commit()
        db.refresh(request)
        
        return request
    
    @staticmethod
    def get_pending_requests(
        db: Session,
        skip: int = 0,
        limit: int = 20
    ) -> List[AccessRequest]:
        """
        Get all pending access requests (for data managers).
        
        Args:
            db: Database session
            skip: Number of records to skip
            limit: Max records to return
        
        Returns:
            List of pending AccessRequest records
        """
        return db.query(AccessRequest).filter(
            AccessRequest.status == "pending"
        ).order_by(
            AccessRequest.created_at.desc()
        ).offset(skip).limit(limit).all()
    
    @staticmethod
    def get_pending_requests_count(db: Session) -> int:
        """Get total count of pending requests."""
        return db.query(AccessRequest).filter(
            AccessRequest.status == "pending"
        ).count()
    
    @staticmethod
    def get_all_requests(
        db: Session,
        skip: int = 0,
        limit: int = 20
    ) -> List[AccessRequest]:
        """
        Get all access requests (pending, approved, rejected).
        
        Args:
            db: Database session
            skip: Number of records to skip
            limit: Max records to return
        
        Returns:
            List of AccessRequest records
        """
        return db.query(AccessRequest).order_by(
            AccessRequest.created_at.desc()
        ).offset(skip).limit(limit).all()
    
    @staticmethod
    def get_request_by_id(
        db: Session,
        request_id: UUID
    ) -> Optional[AccessRequest]:
        """Get a specific access request."""
        return db.query(AccessRequest).filter(
            AccessRequest.id == request_id
        ).first()
    
    @staticmethod
    def get_request_detail(
        db: Session,
        request_id: UUID
    ) -> Optional[AccessRequestDetailResponse]:
        """
        Get access request with full results loaded.
        
        Args:
            db: Database session
            request_id: Request ID
        
        Returns:
            AccessRequestDetailResponse with full results, or None if not found
        """
        request = AccessRequestService.get_request_by_id(db, request_id)
        
        if not request:
            return None
        
        # Load full results
        full_results = None
        if request.result_file_path:
            filepath = os.path.join(DATA_DIRECTORY, request.result_file_path)
            if os.path.exists(filepath):
                with open(filepath, "r") as f:
                    full_results = json.load(f)
            else:
                full_results = {"error": "Result file not found"}
        elif request.result_json:
            full_results = json.loads(request.result_json)
        
        # Parse preview
        data_preview = None
        if request.data_preview:
            try:
                data_preview = json.loads(request.data_preview)
            except:
                pass
        
        return AccessRequestDetailResponse(
            id=request.id,
            user_id=request.user_id,
            user_name=request.user_name,
            project_name=request.project_name,
            reason=request.reason,
            nl_query=request.nl_query,
            sparql_query=request.sparql_query,
            data_preview=data_preview,
            full_results=full_results,
            supporting_doc_path=request.supporting_doc_path,
            supporting_doc_filename=request.supporting_doc_filename,
            status=request.status,
            created_at=request.created_at,
            reviewed_by_id=request.reviewed_by_id,
            reviewed_at=request.reviewed_at,
            review_reason=request.review_reason
        )
    
    @staticmethod
    def get_user_request_history(
        db: Session,
        user_id: UUID,
        skip: int = 0,
        limit: int = 20
    ) -> List[AccessRequest]:
        """
        Get request history for a specific user.
        
        Args:
            db: Database session
            user_id: User ID
            skip: Number of records to skip
            limit: Max records to return
        
        Returns:
            List of user's AccessRequest records (all statuses)
        """
        return db.query(AccessRequest).filter(
            AccessRequest.user_id == user_id
        ).order_by(
            AccessRequest.created_at.desc()
        ).offset(skip).limit(limit).all()
    
    @staticmethod
    def approve_request(
        db: Session,
        request_id: UUID,
        data_manager_id: UUID
    ) -> Optional[AccessRequest]:
        """
        Approve an access request and create corresponding dataset.
        
        Args:
            db: Database session
            request_id: Request ID to approve
            data_manager_id: UUID of approving data manager
        
        Returns:
            Updated AccessRequest, or None if not found
        """
        request = AccessRequestService.get_request_by_id(db, request_id)
        
        if not request:
            return None
        
        # Update request status
        request.status = "approved"
        request.reviewed_by_id = data_manager_id
        request.reviewed_at = datetime.utcnow()
        
        # Create dataset record for the user
        # Load full results to pass to dataset
        full_results = None
        if request.result_file_path:
            filepath = os.path.join(DATA_DIRECTORY, request.result_file_path)
            if os.path.exists(filepath):
                with open(filepath, "r") as f:
                    full_results = json.load(f)
        elif request.result_json:
            full_results = json.loads(request.result_json)
        
        # Create dataset from approved request
        # Store results in same way as access request
        dataset_result_file_path = None
        dataset_result_json = None
        
        if full_results:
            results_json = json.dumps(full_results)
            
            if len(results_json) > 100000:
                filename = f"dataset_{request.user_id}_{datetime.utcnow().timestamp()}.json"
                dataset_result_file_path = f"results/{filename}"
                filepath = os.path.join(DATA_DIRECTORY, dataset_result_file_path)
                
                os.makedirs(os.path.dirname(filepath), exist_ok=True)
                with open(filepath, "w") as f:
                    json.dump(full_results, f)
            else:
                dataset_result_json = results_json
        
        dataset = Dataset(
            user_id=request.user_id,
            nl_query=request.nl_query,
            sparql_query=request.sparql_query,
            name=f"Approved Request - {request.created_at.strftime('%Y-%m-%d %H:%M')}",
            description=f"Approved by data manager on {datetime.utcnow().strftime('%Y-%m-%d')}. Reason: {request.reason}",
            result_file_path=dataset_result_file_path,
            result_json=dataset_result_json,
        )
        
        db.add(dataset)
        db.commit()
        db.refresh(request)
        
        return request
    
    @staticmethod
    def reject_request(
        db: Session,
        request_id: UUID,
        data_manager_id: UUID,
        reason: Optional[str] = None
    ) -> Optional[AccessRequest]:
        """
        Reject an access request.
        
        Args:
            db: Database session
            request_id: Request ID to reject
            data_manager_id: UUID of rejecting data manager
            reason: Optional reason for rejection
        
        Returns:
            Updated AccessRequest, or None if not found
        """
        request = AccessRequestService.get_request_by_id(db, request_id)
        
        if not request:
            return None
        
        request.status = "rejected"
        request.reviewed_by_id = data_manager_id
        request.reviewed_at = datetime.utcnow()
        request.review_reason = reason
        
        db.commit()
        db.refresh(request)
        
        return request
