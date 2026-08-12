import os
import sys
from pathlib import Path

# Must be set before any app module is imported, since config.py reads these
# at import time.
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("JWT_ALGORITHM", "HS256")
os.environ.setdefault("FRONTEND_ORIGINS", "http://localhost:5173")
os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")

# auth-service uses flat (non-package) imports like `from config import ...`,
# so its own root directory needs to be importable.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
