"""Configuration management for auth-service."""
import os

# JWT Configuration
JWT_SECRET = os.getenv("JWT_SECRET")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM")
ACCESS_TOKEN_EXPIRE_MINUTES = 60

# Google OAuth Configuration
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI")
GOOGLE_AUTH_URL = os.getenv("GOOGLE_AUTH_URL", "https://accounts.google.com/o/oauth2/v2/auth")
GOOGLE_TOKEN_URL = os.getenv("GOOGLE_TOKEN_URL", "https://oauth2.googleapis.com/token")

# Frontend Configuration
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://localhost:5000")
FRONTEND_ORIGINS = os.getenv("FRONTEND_ORIGINS", "")

# Database Configuration
DB_HOST = os.getenv("DB_HOST")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")

# OAuth2 provider configuration (for connected apps, e.g. Biomni).
# Access tokens issued this way carry no `role` claim and are restricted to
# a `scope`, unlike the interactive session token from /auth/callback.
OAUTH_ACCESS_TOKEN_EXPIRE_DAYS = int(os.getenv("OAUTH_ACCESS_TOKEN_EXPIRE_DAYS", "30"))

# Biomni is registered as an OAuth client via env config rather than a
# self-service registration UI, since CODA only expects to integrate with a
# small, known set of first-party tools for now. Seeded into oauth_clients
# at startup — see services/oauth_service.seed_client_from_env().
BIOMNI_CLIENT_ID = os.getenv("BIOMNI_CLIENT_ID", "biomni")
BIOMNI_CLIENT_SECRET = os.getenv("BIOMNI_CLIENT_SECRET")
BIOMNI_REDIRECT_URI = os.getenv("BIOMNI_REDIRECT_URI", "http://127.0.0.1:7860/oauth/callback")