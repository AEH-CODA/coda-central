import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
JWT_SECRET = os.getenv("JWT_SECRET")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM")
# Used only to check revocation of oauth_access tokens (Connected Apps, e.g.
# Biomni) via /oauth/introspect — regular session-token requests never call out.
AUTH_SERVICE_URL = os.getenv("AUTH_SERVICE_URL")
DATA_DIRECTORY = os.getenv("DATA_DIRECTORY")
GRAPHDB_ENDPOINT = os.getenv("GRAPHDB_ENDPOINT", "http://graphdb:7200/repositories/feb-sample")
SPARQL_QUERY_TIMEOUT = int(os.getenv("SPARQL_QUERY_TIMEOUT", "30"))
PREVIEW_ROW_LIMIT = int(os.getenv("PREVIEW_ROW_LIMIT", "1000"))

# Ensure data directory exists
os.makedirs(DATA_DIRECTORY, exist_ok=True)
