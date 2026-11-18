"""inference-api: auth, upload validation, ownership, result endpoints (no TensorFlow, SQLite)."""
import io
import os
import subprocess
import sys
import uuid

import pytest

from conftest import SERVICE, auth, make_opt_dicom


@pytest.fixture
def dicom_bytes(tmp_path):
    def _make(**kw):
        p = make_opt_dicom(str(tmp_path / f"{uuid.uuid4()}.dcm"), **kw)
        with open(p, "rb") as f:
            return f.read()
    return _make


def upload(client, headers, data: bytes, filename="scan.dcm", model_id=None):
    form = {"model_id": model_id} if model_id else {}
    return client.post("/inference/jobs", headers=headers, data=form,
                       files={"file": (filename, io.BytesIO(data), "application/dicom")})


# ---------------------------------------------------------------- auth

def test_requires_token(app_client):
    assert app_client.get("/inference/jobs").status_code == 401
    assert app_client.get("/inference/models").status_code == 401
    assert app_client.get("/inference/jobs", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_rejects_connected_app_tokens(app_client):
    h = auth(token_type="oauth_access", scope="datasets:read")
    assert app_client.get("/inference/jobs", headers=h).status_code == 403


def test_health_is_public_and_reports_no_worker(app_client, clean_db):
    r = app_client.get("/inference/health")
    assert r.status_code == 200
    body = r.json()
    assert body["models_enabled"] == ["oct-fluid-spectralis@1.0.0"]
    assert body["workers_online"] == 0 and body["status"] == "degraded"


def test_models_list(app_client):
    r = app_client.get("/inference/models", headers=auth())
    assert r.status_code == 200
    [m] = r.json()
    assert m["ref"] == "oct-fluid-spectralis@1.0.0"
    assert [c["name"] for c in m["classes"]] == ["IRF", "SRF", "PED"]
    assert m["supported_manufacturers"] == ["Heidelberg Engineering"]
    assert "package_dir" not in m and "sha256" not in m


# ---------------------------------------------------------------- upload validation

def test_upload_queues_job(app_client, dicom_bytes):
    h = auth()
    r = upload(app_client, h, dicom_bytes(), filename="../../etc/My Scan.dcm")
    assert r.status_code == 202, r.text
    job_id = r.json()["job_id"]
    j = app_client.get(f"/inference/jobs/{job_id}", headers=h).json()
    assert j["status"] == "queued" and j["filename"] == "My Scan.dcm"
    assert j["input"]["n_bscans"] == 5 and j["input"]["laterality"] == "OD"
    assert j["input"]["spacing_mm"] == {"lateral": 0.0115, "axial": 0.0039}
    assert j["result"] is None
    # no PHI persisted: the synthetic file has PatientName set
    assert "Test" not in str(j)
    from storage import input_path
    assert os.path.exists(input_path(job_id))


@pytest.mark.parametrize("kw,code", [
    ({"manufacturer": "Carl Zeiss Meditec", "model": "Cirrus"}, "unsupported_device"),
    ({"model": "Spectralis HRA"}, "unsupported_device"),
    ({"sop": "1.2.840.10008.5.1.4.1.1.7"}, "unsupported_sop_class"),
    ({"with_spacing": False}, "missing_spacing"),
    ({"with_spacing": False, "with_positions": False}, "missing_spacing"),
])
def test_upload_rejections(app_client, dicom_bytes, kw, code):
    r = upload(app_client, auth(), dicom_bytes(**kw))
    assert r.status_code == 422, r.text
    assert r.json()["code"] == code
    assert r.json()["detail"]


def test_upload_rejects_non_dicom_and_empty(app_client):
    r = upload(app_client, auth(), b"definitely not a dicom file" * 10)
    assert r.status_code == 422 and r.json()["code"] == "invalid_dicom"
    r = upload(app_client, auth(), b"")
    assert r.status_code == 422 and r.json()["code"] == "empty_file"


def test_upload_too_large(app_client):
    r = upload(app_client, auth(), b"\0" * (5 * 1024 * 1024 + 1))   # MAX_UPLOAD_MB=5 in tests
    assert r.status_code == 413 and r.json()["code"] == "file_too_large"


def test_rejected_upload_leaves_no_files(app_client, dicom_bytes):
    from storage import jobs_root
    before = set(os.listdir(jobs_root())) if os.path.isdir(jobs_root()) else set()
    upload(app_client, auth(), dicom_bytes(manufacturer="Topcon"))
    after = set(os.listdir(jobs_root())) if os.path.isdir(jobs_root()) else set()
    assert after == before


def test_unknown_model(app_client, dicom_bytes):
    r = upload(app_client, auth(), dicom_bytes(), model_id="nope@9")
    assert r.status_code == 422 and r.json()["code"] == "unknown_model"
    r = upload(app_client, auth(), dicom_bytes(), model_id="oct-fluid-spectralis")
    assert r.status_code == 202


# ---------------------------------------------------------------- ownership

def test_other_users_cannot_see_or_delete(app_client, dicom_bytes):
    alice, bob = uuid.uuid4(), uuid.uuid4()
    job_id = upload(app_client, auth(alice), dicom_bytes()).json()["job_id"]
    assert app_client.get(f"/inference/jobs/{job_id}", headers=auth(bob)).status_code == 404
    assert app_client.delete(f"/inference/jobs/{job_id}", headers=auth(bob)).status_code == 404
    assert app_client.get("/inference/jobs", headers=auth(bob)).json()["total"] == 0
    # ?all=true is ignored for non-admins
    assert app_client.get("/inference/jobs?all=true", headers=auth(bob)).json()["total"] == 0
    assert app_client.get("/inference/jobs", headers=auth(alice)).json()["total"] == 1


def test_admin_sees_all(app_client, dicom_bytes):
    alice = uuid.uuid4()
    job_id = upload(app_client, auth(alice), dicom_bytes()).json()["job_id"]
    admin = auth(role="admin")
    assert app_client.get(f"/inference/jobs/{job_id}", headers=admin).status_code == 200
    ids = [j["id"] for j in app_client.get("/inference/jobs?all=true&limit=200", headers=admin).json()["items"]]
    assert job_id in ids


def test_results_not_ready_and_delete_queued(app_client, dicom_bytes):
    h = auth()
    job_id = upload(app_client, h, dicom_bytes()).json()["job_id"]
    r = app_client.get(f"/inference/jobs/{job_id}/bscan/0.png", headers=h)
    assert r.status_code == 409 and r.json()["code"] == "not_ready"
    assert app_client.delete(f"/inference/jobs/{job_id}", headers=h).status_code == 204
    assert app_client.get(f"/inference/jobs/{job_id}", headers=h).status_code == 404
    from storage import job_dir
    assert not os.path.exists(job_dir(job_id))


def test_bad_job_id(app_client):
    assert app_client.get("/inference/jobs/not-a-uuid", headers=auth()).status_code == 422


def test_api_does_not_import_tensorflow():
    code = "import sys, main; assert 'tensorflow' not in sys.modules and 'keras' not in sys.modules"
    r = subprocess.run([sys.executable, "-c", code], cwd=SERVICE, env=os.environ.copy(), capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-2000:]
