from sqlalchemy import create_engine, Column, String, Text, DateTime, UUID, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from datetime import datetime
import uuid

from config import DATABASE_URL

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Dataset(Base):
    __tablename__ = "datasets"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)  # Foreign key to users table (in auth-service DB)
    nl_query = Column(Text, nullable=False)
    sparql_query = Column(Text, nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    result_file_path = Column(String(1024), nullable=True)  # Path in volume if large
    result_json = Column(Text, nullable=True)  # JSON string for small results or metadata
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        # Composite index for efficient user dataset listing
        # No native composite index in SQLAlchemy declarative, but can be added via raw SQL if needed
    )


class AccessRequest(Base):
    """Data access request from user to data manager."""
    __tablename__ = "access_requests"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)  # User requesting access
    user_name = Column(String(255), nullable=False)  # Requester's display name from JWT token
    project_name = Column(String(255), nullable=False)  # Project requesting access
    reason = Column(Text, nullable=False)  # Why they need this data
    nl_query = Column(Text, nullable=False)  # Original natural language query
    sparql_query = Column(Text, nullable=False)  # SPARQL query executed
    data_preview = Column(Text, nullable=True)  # JSON string of preview data
    result_file_path = Column(String(1024), nullable=True)  # Path to full results if large
    result_json = Column(Text, nullable=True)  # JSON string of full results if small
    supporting_doc_path = Column(String(1024), nullable=True)  # Path to supporting PDF file
    supporting_doc_filename = Column(String(255), nullable=True)  # Original filename of uploaded PDF
    status = Column(String(20), nullable=False, default="pending", index=True)  # pending, approved, rejected
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    reviewed_by_id = Column(UUID(as_uuid=True), nullable=True, index=True)  # Data manager who reviewed
    reviewed_at = Column(DateTime, nullable=True)  # When data manager took action
    review_reason = Column(Text, nullable=True)  # Reason for rejection (optional)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    """Initialize database with all tables."""
    Base.metadata.create_all(bind=engine)
