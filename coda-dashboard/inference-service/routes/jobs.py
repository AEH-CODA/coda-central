"""/inference/* routes (plan §5.1). No TensorFlow here: uploads are validated from the DICOM header only."""
from __future__ import annotations

import json
import logging
import os
import re
import uuid
from datetime import timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session

import config
import storage
from auth import CurrentUser, current_user
from core.ingest import IngestError, inspect_dicom_opt
from core.manifest import Manifest
from core.pipeline import LABELS_FILE, load_labels, write_result
from core.quantify import etdrs_summary
from db import CANCELLED, FAILED, QUEUED, RUNNING, SUCCEEDED, InferenceJob, InferenceWorker, get_db, utcnow

log = logging.getLogger(__name__)
router = APIRouter(prefix="/inference", tags=["inference"])

UPLOAD_CHUNK = 1 << 20


class ApiError(Exception):
    """Rendered as {"detail": message, "code": code}; message is safe to show to users."""

    def __init__(self, status: int, code: str, message: str):
        self.status, self.code, self.message = status, code, message


def manifests(request: Request) -> dict[str, Manifest]:
    return request.app.state.manifests


def iso(dt) -> str | None:
    return dt.isoformat(timespec="seconds") + "Z" if dt else None


# ------------------------------------------------------------------ helpers

def resolve_model(available: dict[str, Manifest], model_id: str | None) -> Manifest:
    """Accepts 'id@version', 'id' (latest enabled version, i.e. last listed), or nothing if exactly one model."""
    if not available:
        raise ApiError(503, "no_models", "No inference models are enabled.")
    if not model_id:
        if len(available) == 1:
            return next(iter(available.values()))
        raise ApiError(422, "model_required", "Choose a model: " + ", ".join(available))
    if model_id in available:
        return available[model_id]
    matches = [m for m in available.values() if m.id == model_id]
    if matches:
        return matches[-1]
    raise ApiError(422, "unknown_model", f"Unknown model '{model_id}'. Available: {', '.join(available)}")


def safe_filename(name: str | None) -> str:
    base = os.path.basename((name or "").replace("\\", "/")).strip()
    base = re.sub(r"[\x00-\x1f\x7f]", "", base)
    return (base or "upload.dcm")[:200]


def get_job_for(db: Session, job_id: UUID, user: CurrentUser) -> InferenceJob:
    job = db.get(InferenceJob, job_id)
    # 404 (not 403) for other users' jobs: don't reveal that the id exists
    if job is None or (job.user_id != user.id and not user.is_admin):
        raise ApiError(404, "not_found", "Job not found.")
    return job


def headline(job: InferenceJob) -> dict | None:
    if job.status != SUCCEEDED or not job.result_json:
        return None
    return job.result_json.get("volumes_nl", {}).get("total")


def job_summary(job: InferenceJob) -> dict:
    meta = job.input_meta or {}
    return {
        "id": str(job.id),
        "user_id": str(job.user_id),
        "filename": job.original_filename,
        "model": {"id": job.model_id, "version": job.model_version},
        "status": job.status,
        "stage": job.stage,
        "progress": job.progress,
        "laterality": meta.get("laterality"),
        "n_bscans": meta.get("n_bscans"),
        "study_date": meta.get("study_date"),
        "total_nl": headline(job),
        "error": {"code": job.error_code, "message": job.error_message} if job.status == FAILED else None,
        "created_at": iso(job.created_at),
        "started_at": iso(job.started_at),
        "finished_at": iso(job.finished_at),
    }


def job_detail(job: InferenceJob) -> dict:
    out = job_summary(job)
    out.update({
        "input": job.input_meta,
        "device": job.device,
        "duration_ms": job.duration_ms,
        "result": job.result_json if job.status == SUCCEEDED else None,
    })
    return out


def require_succeeded(job: InferenceJob):
    if job.status != SUCCEEDED:
        raise ApiError(409, "not_ready", f"Job is {job.status}; results are not available.")


def job_file(job: InferenceJob, *parts: str) -> str:
    path = os.path.join(storage.job_dir(job.id), *parts)
    if not os.path.isfile(path):
        raise ApiError(404, "not_found", "File not found (results may have expired).")
    return path


PNG_HEADERS = {"Cache-Control": "private, max-age=86400"}   # outputs of a finished job never change


# ------------------------------------------------------------------ routes

@router.get("/health")
def health(request: Request, db: Session = Depends(get_db)):
    cutoff = utcnow() - timedelta(seconds=config.WORKER_ONLINE_SECONDS)
    online = (db.query(InferenceWorker).filter(InferenceWorker.heartbeat_at >= cutoff)
              .order_by(InferenceWorker.heartbeat_at.desc()).all())
    queued = db.query(InferenceJob).filter(InferenceJob.status == QUEUED).count()
    running = db.query(InferenceJob).filter(InferenceJob.status == RUNNING).count()
    return {
        "status": "ok" if online else "degraded",
        "device": online[0].device if online else None,
        "models_enabled": list(manifests(request)),
        "models_loaded": sorted({m for w in online for m in (w.models or [])}),
        "workers_online": len(online),
        "queue": {"queued": queued, "running": running},
    }


@router.get("/models")
def list_models(request: Request, user: CurrentUser = Depends(current_user)):
    return [m.public() for m in manifests(request).values()]


@router.post("/jobs", status_code=202)
def create_job(
    request: Request,
    file: UploadFile = File(...),
    model_id: str | None = Form(default=None),
    user: CurrentUser = Depends(current_user),
    db: Session = Depends(get_db),
):
    manifest = resolve_model(manifests(request), model_id)
    job_id = uuid.uuid4()
    path = storage.input_path(job_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    limit = config.MAX_UPLOAD_MB * 1024 * 1024
    try:
        size = 0
        with open(path, "wb") as out:
            while chunk := file.file.read(UPLOAD_CHUNK):
                size += len(chunk)
                if size > limit:
                    raise ApiError(413, "file_too_large", f"The file exceeds the {config.MAX_UPLOAD_MB} MB limit.")
                out.write(chunk)
        if size == 0:
            raise ApiError(422, "empty_file", "The uploaded file is empty.")
        try:
            meta = inspect_dicom_opt(path, manifest.input.supported_manufacturers, manifest.input.supported_models)
        except IngestError as e:
            raise ApiError(422, e.code, str(e))
    except BaseException:
        storage.delete_job_files(job_id)
        raise

    meta["size_bytes"] = size
    job = InferenceJob(
        id=job_id, user_id=user.id, model_id=manifest.id, model_version=manifest.version,
        model_sha256=manifest.sha256, status=QUEUED, stage="queued", progress=0,
        original_filename=safe_filename(file.filename), input_meta=meta,
    )
    db.add(job)
    db.commit()
    log.info("job %s queued (%s, %d B-scans, %.1f MB)", job_id, manifest.ref, meta["n_bscans"], size / 1e6)
    return {"job_id": str(job_id), "status": QUEUED}


@router.get("/jobs")
def list_jobs(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    all_users: bool = Query(False, alias="all", description="admins only: include every user's jobs"),
    status: str | None = Query(None, description="comma-separated statuses"),
    user: CurrentUser = Depends(current_user),
    db: Session = Depends(get_db),
):
    q = db.query(InferenceJob)
    if not (all_users and user.is_admin):
        q = q.filter(InferenceJob.user_id == user.id)
    if status:
        q = q.filter(or_(*[InferenceJob.status == s.strip() for s in status.split(",") if s.strip()]))
    total = q.count()
    jobs = q.order_by(InferenceJob.created_at.desc()).offset(skip).limit(limit).all()
    return {"total": total, "skip": skip, "limit": limit, "items": [job_summary(j) for j in jobs]}


@router.get("/jobs/{job_id}")
def get_job(job_id: UUID, user: CurrentUser = Depends(current_user), db: Session = Depends(get_db)):
    return job_detail(get_job_for(db, job_id, user))


class EtdrsRequest(BaseModel):
    center_mm: dict[str, float] | None = None   # {"x": lateral mm, "z": slow-axis mm}; null resets to scan centre


@router.post("/jobs/{job_id}/etdrs")
def recenter_etdrs(job_id: UUID, body: EtdrsRequest, request: Request,
                   user: CurrentUser = Depends(current_user), db: Session = Depends(get_db)):
    job = get_job_for(db, job_id, user)
    require_succeeded(job)
    labels, vol = load_labels(job_file(job, LABELS_FILE))
    center = None
    if body.center_mm is not None:
        try:
            center = (float(body.center_mm["x"]), float(body.center_mm["z"]))
        except KeyError:
            raise ApiError(422, "invalid_center", "center_mm needs x and z (mm).")
        width = vol.voxels.shape[2] * vol.spacing_lateral_mm
        pos = vol.bscan_positions_mm
        if not (0 <= center[0] <= width and pos.min() <= center[1] <= pos.max()):
            raise ApiError(422, "invalid_center", "The ETDRS centre must lie inside the scanned area.")

    result = dict(job.result_json)
    classes = {c["id"]: c["name"] for c in result["classes"]}
    diameters = [float(k.removeprefix("etdrs_").removesuffix("mm")) for k in result["volumes_nl"] if k != "total"]
    s = etdrs_summary(labels, vol, classes, diameters, center)
    result.update(s)
    job.result_json = result          # persisted so the report reopens with the chosen centre
    db.commit()
    try:
        write_result(storage.job_dir(job.id), result)
    except OSError:
        log.warning("job %s: could not rewrite result.json", job.id)
    return s


@router.get("/jobs/{job_id}/bscan/{z}.png")
def bscan_png(job_id: UUID, z: int, user: CurrentUser = Depends(current_user), db: Session = Depends(get_db)):
    job = get_job_for(db, job_id, user)
    require_succeeded(job)
    return FileResponse(job_file(job, "bscan", f"{z}.png"), media_type="image/png", headers=PNG_HEADERS)


@router.get("/jobs/{job_id}/overlay/{z}.png")
def overlay_png(job_id: UUID, z: int, user: CurrentUser = Depends(current_user), db: Session = Depends(get_db)):
    job = get_job_for(db, job_id, user)
    require_succeeded(job)
    return FileResponse(job_file(job, "overlay", f"{z}.png"), media_type="image/png", headers=PNG_HEADERS)


@router.get("/jobs/{job_id}/enface/{cls}.png")
def enface_png(job_id: UUID, cls: str, user: CurrentUser = Depends(current_user), db: Session = Depends(get_db)):
    job = get_job_for(db, job_id, user)
    require_succeeded(job)
    names = {c["name"] for c in job.result_json.get("classes", [])}
    if cls not in names:
        raise ApiError(404, "not_found", f"Unknown class '{cls}'.")
    return FileResponse(job_file(job, "enface", f"{cls}.png"), media_type="image/png", headers=PNG_HEADERS)


@router.get("/jobs/{job_id}/labels.npz")
def labels_npz(job_id: UUID, user: CurrentUser = Depends(current_user), db: Session = Depends(get_db)):
    job = get_job_for(db, job_id, user)
    require_succeeded(job)
    stem = os.path.splitext(job.original_filename)[0]
    return FileResponse(job_file(job, LABELS_FILE), media_type="application/octet-stream",
                        filename=f"{stem}_labels.npz")


@router.get("/jobs/{job_id}/result.json")
def result_json(job_id: UUID, user: CurrentUser = Depends(current_user), db: Session = Depends(get_db)):
    job = get_job_for(db, job_id, user)
    require_succeeded(job)
    stem = os.path.splitext(job.original_filename)[0]
    return Response(json.dumps(job.result_json, indent=1), media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="{stem}_result.json"'})


@router.delete("/jobs/{job_id}", status_code=204)
def delete_job(job_id: UUID, user: CurrentUser = Depends(current_user), db: Session = Depends(get_db)):
    job = get_job_for(db, job_id, user)
    if job.status == RUNNING:
        # the worker notices at its next progress update, stops, and removes the row and files
        job.status = CANCELLED
        db.commit()
    else:
        db.delete(job)
        db.commit()
        storage.delete_job_files(job_id)
    return Response(status_code=204)

