import os
import sys
import tempfile
from pathlib import Path

# Must be set before any app module is imported, since config.py reads these
# at import time (and touches the filesystem for DATA_DIRECTORY).
_TMP_DIR = tempfile.mkdtemp(prefix="coda-dataset-service-tests-")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_TMP_DIR}/test.db")
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("JWT_ALGORITHM", "HS256")
os.environ.setdefault("DATA_DIRECTORY", _TMP_DIR)
os.environ.setdefault("GRAPHDB_ENDPOINT", "http://localhost:0/repositories/test")
os.environ.setdefault("SPARQL_QUERY_TIMEOUT", "5")
os.environ.setdefault("PREVIEW_ROW_LIMIT", "1000")

# dataset-service uses flat (non-package) imports like `from config import ...`,
# so its own root directory needs to be importable.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
