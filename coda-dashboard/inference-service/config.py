"""Environment configuration shared by inference-api (main.py) and inference-worker (worker.py)."""
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:   # optional: compose passes env_file directly
    pass

_HERE = os.path.dirname(os.path.abspath(__file__))

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///" + os.path.join(_HERE, "inference-dev.db"))
DATA_DIR = os.getenv("DATA_DIR", os.path.join(_HERE, "data"))
MODELS_DIR = os.getenv("MODELS_DIR", os.path.join(_HERE, "models"))
ENABLED_MODELS = os.getenv("ENABLED_MODELS", "oct-fluid-spectralis@1.0.0")

JWT_SECRET = os.getenv("JWT_SECRET")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")

MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "300"))
RESULT_TTL_DAYS = int(os.getenv("RESULT_TTL_DAYS", "30"))
KEEP_INPUT = os.getenv("KEEP_INPUT", "false").lower() in ("1", "true", "yes")

# worker
WORKER_POLL_SECONDS = float(os.getenv("WORKER_POLL_SECONDS", "2"))
HEARTBEAT_SECONDS = float(os.getenv("HEARTBEAT_SECONDS", "15"))
STALE_JOB_MINUTES = float(os.getenv("STALE_JOB_MINUTES", "10"))
MAX_ATTEMPTS = int(os.getenv("MAX_ATTEMPTS", "2"))
MAINTENANCE_SECONDS = float(os.getenv("MAINTENANCE_SECONDS", "600"))
# a worker counts as online in /inference/health if it reported within this window
WORKER_ONLINE_SECONDS = float(os.getenv("WORKER_ONLINE_SECONDS", "60"))
VERIFY_MODEL_CHECKSUM = os.getenv("VERIFY_MODEL_CHECKSUM", "true").lower() in ("1", "true", "yes")

FRONTEND_ORIGINS = os.getenv("FRONTEND_ORIGINS", "")

ADMIN_ROLES = ("admin",)
