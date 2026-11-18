"""Worker loop + full job lifecycle through the API, with a fake adapter (no TensorFlow)."""
import io
import json
import os
import uuid
from datetime import timedelta

import numpy as np
import pytest
from PIL import Image

import config
import storage
from conftest import FakeAdapter, auth, make_opt_dicom
from core.ingest import IngestError
from db import InferenceJob, SessionLocal, utcnow
from worker import Worker

REF = "oct-fluid-spectralis@1.0.0"


@pytest.fixture
def submit(app_client, tmp_path, clean_db):
    def _submit(user=None, **kw):
        user = user or uuid.uuid4()
        p = make_opt_dicom(str(tmp_path / f"{uuid.uuid4()}.dcm"), n=7, rows=80, cols=120, **kw)
        with open(p, "rb") as f:
            r = app_client.post("/inference/jobs", headers=auth(user),
                                files={"file": ("scan.dcm", io.BytesIO(f.read()), "application/dicom")})
        assert r.status_code == 202, r.text
        return r.json()["job_id"], auth(user)
    return _submit


@pytest.fixture
def worker(fake_manifest):
    return Worker({REF: FakeAdapter(fake_manifest)}, device="CPU", worker_id="test-worker")


def get_job(job_id) -> InferenceJob:
    with SessionLocal() as s:
        return s.get(InferenceJob, uuid.UUID(job_id))


def test_full_lifecycle(app_client, submit, worker):
    job_id, h = submit()
    assert worker.run_once()
    assert not worker.run_once()   # queue empty

    j = app_client.get(f"/inference/jobs/{job_id}", headers=h).json()
    assert j["status"] == "succeeded", j
    assert j["progress"] == 100 and j["device"] == "CPU" and j["duration_ms"] >= 0
    res = j["result"]
    assert res["model"]["id"] == "oct-fluid-spectralis" and res["model"]["device"] == "CPU"
    assert res["scan"]["n_bscans"] == 7 and res["scan"]["laterality"] == "OD"
    assert set(res["volumes_nl"]) == {"total", "etdrs_1mm", "etdrs_3mm", "etdrs_6mm"}

    # IRF block: 10 px x 30 cols per B-scan, Cavalieri over 7 B-scans of 0.25 mm
    expected_irf = 10 * 30 * 0.0115 * 0.0039 * 0.25 * 7 * 1000
    assert res["volumes_nl"]["total"]["IRF"] == pytest.approx(expected_irf, rel=1e-3)
    assert res["volumes_nl"]["total"]["SRF"] == 0
    assert res["volumes_nl"]["total"]["PED"] > 0
    assert len(res["bscans"]) == 7 and res["bscans"][3]["area_mm2"]["PED"] > 0
    assert res["max_height_um"]["IRF"] == pytest.approx(39.0)
    assert res["etdrs_center_mm"]["source"] == "scan_center"
    assert any("ETDRS" in w for w in res["warnings"])    # 1.4 mm x 1.5 mm field: circles not covered
    assert res["disclaimer"]
    assert j["total_nl"] == res["volumes_nl"]["total"]

    # input deleted after processing (KEEP_INPUT=false), outputs present
    assert not os.path.exists(storage.input_path(job_id))
    for path in ("bscan/0.png", "overlay/6.png", "enface/IRF.png"):
        r = app_client.get(f"/inference/jobs/{job_id}/{path}", headers=h)
        assert r.status_code == 200 and r.headers["content-type"] == "image/png", path
    overlay = np.array(Image.open(io.BytesIO(app_client.get(f"/inference/jobs/{job_id}/overlay/0.png",
                                                            headers=h).content)))
    assert overlay.shape == (80, 120, 4)
    assert tuple(overlay[25, 40]) == (0xE5, 0x39, 0x35, 140)     # IRF colour, alpha 0.55
    assert overlay[0, 0, 3] == 0
    assert app_client.get(f"/inference/jobs/{job_id}/bscan/99.png", headers=h).status_code == 404
    assert app_client.get(f"/inference/jobs/{job_id}/enface/XYZ.png", headers=h).status_code == 404

    r = app_client.get(f"/inference/jobs/{job_id}/labels.npz", headers=h)
    with np.load(io.BytesIO(r.content)) as f:
        assert f["labels"].shape == (7, 80, 120)
    assert json.loads(app_client.get(f"/inference/jobs/{job_id}/result.json", headers=h).content)["scan"]

    # other users still get 404 on files
    assert app_client.get(f"/inference/jobs/{job_id}/bscan/0.png", headers=auth()).status_code == 404

    # list shows headline volumes
    [item] = app_client.get("/inference/jobs", headers=h).json()["items"]
    assert item["total_nl"]["IRF"] == pytest.approx(expected_irf, rel=1e-3)


def test_etdrs_recenter(app_client, submit, worker):
    job_id, h = submit()
    worker.run_once()
    base = app_client.get(f"/inference/jobs/{job_id}", headers=h).json()["result"]
    # IRF block spans cols 30..59 -> x 0.35..0.69 mm, inside the 1 mm circle at the scan centre (0.69, 0.75);
    # a centre at x = 1.3 mm is > 0.5 mm from every IRF A-scan
    assert base["volumes_nl"]["etdrs_1mm"]["IRF"] > 0
    r = app_client.post(f"/inference/jobs/{job_id}/etdrs", headers=h, json={"center_mm": {"x": 1.3, "z": 0.75}})
    assert r.status_code == 200, r.text
    moved = r.json()
    assert moved["etdrs_center_mm"] == {"x": 1.3, "z": 0.75, "source": "user"}
    assert moved["volumes_nl"]["total"] == base["volumes_nl"]["total"]
    assert moved["volumes_nl"]["etdrs_1mm"]["IRF"] == 0
    # persisted
    again = app_client.get(f"/inference/jobs/{job_id}", headers=h).json()["result"]
    assert again["etdrs_center_mm"]["source"] == "user"
    # reset
    r = app_client.post(f"/inference/jobs/{job_id}/etdrs", headers=h, json={"center_mm": None})
    assert r.json()["volumes_nl"] == base["volumes_nl"]
    # outside the scan
    r = app_client.post(f"/inference/jobs/{job_id}/etdrs", headers=h, json={"center_mm": {"x": 50, "z": 0}})
    assert r.status_code == 422 and r.json()["code"] == "invalid_center"


def test_ingest_failure_marks_failed(app_client, submit, worker, fake_manifest):
    job_id, h = submit()
    worker.adapters[REF] = FakeAdapter(fake_manifest, fail_with=IngestError("invalid_pixel_data", "bad pixels"))
    worker.run_once()
    j = app_client.get(f"/inference/jobs/{job_id}", headers=h).json()
    assert j["status"] == "failed"
    assert j["error"] == {"code": "invalid_pixel_data", "message": "bad pixels"}
    assert not os.path.exists(storage.input_path(job_id))


def test_internal_error_is_not_leaked(app_client, submit, worker, fake_manifest):
    job_id, h = submit()
    worker.adapters[REF] = FakeAdapter(fake_manifest, fail_with=RuntimeError("CUDA_ERROR_OUT_OF_MEMORY at 0xdeadbeef"))
    worker.run_once()
    j = app_client.get(f"/inference/jobs/{job_id}", headers=h).json()
    assert j["status"] == "failed" and j["error"]["code"] == "internal_error"
    assert "CUDA" not in j["error"]["message"]


def test_cancel_running_job(app_client, submit, worker, fake_manifest):
    job_id, h = submit()

    def cancel_mid_run():
        assert app_client.delete(f"/inference/jobs/{job_id}", headers=h).status_code == 204
        assert get_job(job_id).status == "cancelled"
    worker.adapters[REF] = FakeAdapter(fake_manifest, on_segment=cancel_mid_run)
    worker.run_once()
    assert get_job(job_id) is None
    assert not os.path.exists(storage.job_dir(job_id))


def test_requeue_stale_then_fail_after_max_attempts(submit, worker):
    job_id, _ = submit()
    jid = uuid.UUID(job_id)
    old = utcnow() - timedelta(minutes=config.STALE_JOB_MINUTES + 1)
    with SessionLocal() as s:   # simulate a worker that claimed the job and died
        j = s.get(InferenceJob, jid)
        j.status, j.worker_id, j.heartbeat_at, j.attempts = "running", "dead-worker", old, 1
        s.commit()
    worker.maintenance()
    j = get_job(job_id)
    assert j.status == "queued" and j.worker_id is None

    with SessionLocal() as s:
        j = s.get(InferenceJob, jid)
        j.status, j.worker_id, j.heartbeat_at, j.attempts = "running", "dead-worker", old, config.MAX_ATTEMPTS
        s.commit()
    worker.maintenance()
    j = get_job(job_id)
    assert j.status == "failed" and j.error_code == "worker_lost"


def test_fresh_running_job_not_requeued(submit, worker):
    job_id, _ = submit()
    with SessionLocal() as s:
        j = s.get(InferenceJob, uuid.UUID(job_id))
        j.status, j.worker_id, j.heartbeat_at = "running", "other-worker", utcnow()
        s.commit()
    worker.maintenance()
    assert get_job(job_id).status == "running"


def test_recover_own_jobs_on_restart(submit, worker):
    job_id, _ = submit()
    with SessionLocal() as s:
        j = s.get(InferenceJob, uuid.UUID(job_id))
        j.status, j.worker_id, j.heartbeat_at = "running", worker.worker_id, utcnow()
        s.commit()
    worker.recover_own_jobs()
    assert get_job(job_id).status == "queued"


def test_ttl_purge(submit, worker):
    job_id, _ = submit()
    worker.run_once()
    assert os.path.isdir(storage.job_dir(job_id))
    with SessionLocal() as s:
        s.get(InferenceJob, uuid.UUID(job_id)).finished_at = utcnow() - timedelta(days=config.RESULT_TTL_DAYS + 1)
        s.commit()
    worker.maintenance()
    assert get_job(job_id) is None
    assert not os.path.exists(storage.job_dir(job_id))


def test_job_taken_over_is_left_alone(submit, worker, fake_manifest):
    """If our heartbeat was missed and another worker re-claimed the job, we must not delete or overwrite it."""
    job_id, _ = submit()

    def steal():
        with SessionLocal() as s:
            s.get(InferenceJob, uuid.UUID(job_id)).worker_id = "other-worker"
            s.commit()
    worker.adapters[REF] = FakeAdapter(fake_manifest, on_segment=steal)
    worker.run_once()
    j = get_job(job_id)
    assert j is not None and j.status == "running" and j.worker_id == "other-worker"
    assert os.path.exists(storage.input_path(job_id))   # the other worker still needs it


def test_worker_heartbeat_makes_health_ok(app_client, worker, clean_db):
    worker.beat()
    body = app_client.get("/inference/health").json()
    assert body["status"] == "ok" and body["device"] == "CPU"
    assert body["models_loaded"] == [REF] and body["workers_online"] == 1
