from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os

from db import init_db
from routes.datasets import router as datasets_router

# Initialize database on startup
init_db()

app = FastAPI(title="CODA Dataset Service")

# CORS configuration
origins = os.getenv("FRONTEND_ORIGINS", "")
allow_origins = [o.strip() for o in origins.split(",") if o.strip()] if origins else ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(datasets_router)

@app.get("/")
def health_check():
    """Health check endpoint."""
    return {"status": "Dataset Service running"}
