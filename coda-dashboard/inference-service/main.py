"""inference-api: validates uploads, queues jobs and serves results. Never imports TensorFlow (see worker.py)."""
import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import config
from core.registry import load_manifests
from db import init_db
from routes.jobs import ApiError, router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

if not config.JWT_SECRET:
    raise RuntimeError("JWT_SECRET is not set")

init_db()

app = FastAPI(title="CODA Inference Service")
# manifests only (no weights loaded); checksums are verified by the worker
app.state.manifests = load_manifests(config.MODELS_DIR, config.ENABLED_MODELS, verify_checksum=False)

origins = [o.strip() for o in config.FRONTEND_ORIGINS.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(ApiError)
def api_error(_: Request, e: ApiError):
    return JSONResponse(status_code=e.status, content={"detail": e.message, "code": e.code})


app.include_router(router)


@app.get("/")
def root():
    return {"status": "Inference Service running"}
