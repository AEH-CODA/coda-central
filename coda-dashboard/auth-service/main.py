from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import (
    FRONTEND_ORIGINS,
    BIOMNI_CLIENT_ID, BIOMNI_CLIENT_SECRET, BIOMNI_REDIRECT_URI,
)
from db import init_db
from routes.auth import router as auth_router
from routes.oauth import router as oauth_router
from routes.users import router as users_router
from services.oauth_service import seed_client_from_env

# Initialize FastAPI app
app = FastAPI(
    title="Auth Service",
    description="Google OAuth 2.0 Authentication Service"
)

# Configure CORS
origins = [o.strip() for o in FRONTEND_ORIGINS.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,  # Allow all origins (configured for development)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize database on startup
@app.on_event("startup")
def startup():
    """Initialize database schema and register known OAuth clients on service startup."""
    init_db()
    seed_client_from_env(
        client_id=BIOMNI_CLIENT_ID,
        client_secret=BIOMNI_CLIENT_SECRET,
        redirect_uri=BIOMNI_REDIRECT_URI,
        allowed_scopes=["datasets:read"],
        name="Biomni",
    )

# Include routers
app.include_router(auth_router)
app.include_router(oauth_router)
app.include_router(users_router)

# Health check endpoint
@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "Auth service running"}
