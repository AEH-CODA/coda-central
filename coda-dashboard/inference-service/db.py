"""Database models. The `inference_jobs` table doubles as the job queue (claimed with SELECT ... FOR UPDATE SKIP LOCKED).

Timestamps are naive UTC (same convention as dataset-service), so the same code runs on Postgres and on SQLite in tests.
"""
import logging
import time
import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Column, DateTime, Integer, String, Text, Uuid, create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base, sessionmaker

from config import DATABASE_URL

log = logging.getLogger(__name__)

_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, pool_pre_ping=True, connect_args=_connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

JsonType = JSON().with_variant(JSONB(), "postgresql")

# job status values
QUEUED, RUNNING, SUCCEEDED, FAILED, CANCELLED = "queued", "running", "succeeded", "failed", "cancelled"
STATUSES = (QUEUED, RUNNING, SUCCEEDED, FAILED, CANCELLED)
ACTIVE = (QUEUED, RUNNING)


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class InferenceJob(Base):
    __tablename__ = "inference_jobs"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid, nullable=False, index=True)
    model_id = Column(String(128), nullable=False)
    model_version = Column(String(64), nullable=False)
    model_sha256 = Column(String(64), nullable=True)
    status = Column(String(16), nullable=False, default=QUEUED, index=True)
    stage = Column(String(32), nullable=True)
    progress = Column(Integer, nullable=False, default=0)
    original_filename = Column(String(255), nullable=False)
    input_meta = Column(JsonType, nullable=True)
    result_json = Column(JsonType, nullable=True)
    error_code = Column(String(64), nullable=True)
    error_message = Column(Text, nullable=True)
    device = Column(String(128), nullable=True)
    duration_ms = Column(Integer, nullable=True)
    worker_id = Column(String(128), nullable=True)
    attempts = Column(Integer, nullable=False, default=0)
    heartbeat_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=utcnow, index=True)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)

    @property
    def model_ref(self) -> str:
        return f"{self.model_id}@{self.model_version}"


class InferenceWorker(Base):
    """One row per worker process; lets the API report the device and liveness in /inference/health."""
    __tablename__ = "inference_workers"

    worker_id = Column(String(128), primary_key=True)
    device = Column(String(128), nullable=True)
    models = Column(JsonType, nullable=True)
    started_at = Column(DateTime, nullable=False, default=utcnow)
    heartbeat_at = Column(DateTime, nullable=False, default=utcnow)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db(retries: int = 30, delay: float = 2.0):
    """Create tables, waiting for the database container to accept connections."""
    for attempt in range(1, retries + 1):
        try:
            Base.metadata.create_all(bind=engine)
            return
        except Exception as e:  # OperationalError while Postgres starts
            if attempt == retries:
                raise
            log.warning("database not ready (%s), retrying in %.0fs", type(e).__name__, delay)
            time.sleep(delay)
