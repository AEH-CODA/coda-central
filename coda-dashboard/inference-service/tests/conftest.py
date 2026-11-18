import os
import shutil
import sys
import tempfile
import uuid
from datetime import datetime, timedelta, timezone

import numpy as np
import pydicom
import pytest
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, generate_uid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

HERE = os.path.dirname(os.path.abspath(__file__))
SERVICE = os.path.abspath(os.path.join(HERE, ".."))
MODEL_PACKAGE = os.environ.get("OCT_MODEL_PACKAGE", os.path.join(SERVICE, "models", "oct-fluid-spectralis", "1.0.0"))

# ---- service environment for API / worker tests (config.py reads it at import time) ----
# The API only needs manifests, so tests use a copy of the real model.yaml next to a dummy weights file: no TensorFlow,
# no 114 MB download, no Postgres.
_TMP = tempfile.mkdtemp(prefix="coda-inference-tests-")
FAKE_MODELS_DIR = os.path.join(_TMP, "models")
_fake_pkg = os.path.join(FAKE_MODELS_DIR, "oct-fluid-spectralis", "1.0.0")
os.makedirs(_fake_pkg)
shutil.copy(os.path.join(SERVICE, "models", "oct-fluid-spectralis", "1.0.0", "model.yaml"), _fake_pkg)
open(os.path.join(_fake_pkg, "best_model.keras"), "wb").close()
os.environ.update({
    "DATABASE_URL": f"sqlite:///{_TMP}/test.db",
    "DATA_DIR": os.path.join(_TMP, "data"),
    "MODELS_DIR": FAKE_MODELS_DIR,
    "ENABLED_MODELS": "oct-fluid-spectralis@1.0.0",
    "JWT_SECRET": "test-secret",
    "JWT_ALGORITHM": "HS256",
    "MAX_UPLOAD_MB": "5",
    "KEEP_INPUT": "false",
})

from core.ingest.dicom_opt import OPT_SOP_CLASS  # noqa: E402
# Real patient exports: kept locally under tests/data/ (gitignored); tests that need them skip when absent.
SAMPLE_DICOM_DIR = os.environ.get("OCT_SAMPLE_DICOMS", os.path.join(HERE, "data", "sample_spectralis"))
RETOUCH_TEST015 = os.environ.get(
    "OCT_RETOUCH_TEST015", os.path.expanduser("~/Desktop/OCT_Others/RETOUCH/RETOUCH-TestSet-Spectralis/TEST015/oct.mhd"))


def make_opt_dicom(path, n=5, rows=64, cols=96, axial=0.0039, lateral=0.0115, spacing=0.25,
                   manufacturer="Heidelberg Engineering", model="Spectralis", sop=OPT_SOP_CLASS,
                   with_spacing=True, with_positions=True, shuffle_frames=False, laterality="R"):
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = sop
    meta.MediaStorageSOPInstanceUID = generate_uid()
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds = Dataset()
    ds.file_meta = meta
    ds.SOPClassUID = sop
    ds.SOPInstanceUID = meta.MediaStorageSOPInstanceUID
    ds.Modality = "OPT"
    ds.Manufacturer = manufacturer
    ds.ManufacturerModelName = model
    ds.ImageLaterality = laterality
    ds.StudyDate = "20250101"
    ds.PatientName = "Test^Patient"
    ds.NumberOfFrames = n
    ds.Rows, ds.Columns = rows, cols
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.BitsAllocated = ds.BitsStored = 16
    ds.HighBit = 15
    ds.PixelRepresentation = 0
    frames = np.stack([np.full((rows, cols), i + 1, np.uint16) for i in range(n)])   # frame k has value k+1
    order = np.arange(n)
    if shuffle_frames:
        order = np.random.default_rng(0).permutation(n)
    ds.PixelData = frames[order].tobytes()
    if with_spacing:
        pm = Dataset()
        pm.PixelSpacing = [axial, lateral]
        pm.SliceThickness = spacing
        shared = Dataset()
        shared.PixelMeasuresSequence = [pm]
        ds.SharedFunctionalGroupsSequence = [shared]
    per = []
    for k in order:
        f = Dataset()
        fc = Dataset()
        fc.InStackPositionNumber = int(k) + 1
        f.FrameContentSequence = [fc]
        if with_positions:
            pp = Dataset()
            pp.ImagePositionPatient = [0.0, 0.0, float(k) * spacing]
            f.PlanePositionSequence = [pp]
        per.append(f)
    ds.PerFrameFunctionalGroupsSequence = per
    ds.save_as(path, enforce_file_format=True)
    return path


@pytest.fixture
def opt_dicom(tmp_path):
    def _make(**kw):
        return make_opt_dicom(str(tmp_path / "x.dcm"), **kw)
    return _make


@pytest.fixture(scope="session")
def adapter():
    if not os.path.exists(os.path.join(MODEL_PACKAGE, "model.yaml")):
        pytest.skip("model package not available")
    from core.registry import load_adapter
    a, _ = load_adapter(MODEL_PACKAGE)
    return a


def make_token(user_id=None, role="user", **extra) -> str:
    from jose import jwt
    payload = {"sub": str(user_id or uuid.uuid4()), "role": role,
               "exp": datetime.now(timezone.utc) + timedelta(minutes=30), **extra}
    return jwt.encode(payload, "test-secret", algorithm="HS256")


def auth(user_id=None, role="user", **extra) -> dict:
    return {"Authorization": f"Bearer {make_token(user_id, role, **extra)}"}


class FakeAdapter:
    """Stands in for a real model: labels a fixed block per class, so tests run without TensorFlow."""

    def __init__(self, manifest, fail_with: Exception | None = None, on_segment=None):
        self.manifest = manifest
        self.fail_with = fail_with
        self.on_segment = on_segment

    def segment(self, volume, progress=None):
        from core.adapters.base import SegmentationResult
        if self.on_segment:
            self.on_segment()
        if self.fail_with:
            raise self.fail_with
        z, h, w = volume.voxels.shape
        labels = np.zeros((z, h, w), np.uint8)
        labels[:, h // 4:h // 4 + 10, w // 4:w // 2] = 1       # IRF: 10 px tall, W/4 wide, every B-scan
        labels[z // 2, h // 2:h // 2 + 4, w // 2:w // 2 + 8] = 3   # PED: one B-scan only
        if progress:
            for i in range(z):
                progress(i + 1, z)
        return SegmentationResult(labels=labels, extras={"canvas_shape": [512, 576]})


@pytest.fixture(scope="session")
def fake_manifest():
    from core.manifest import load_manifest
    return load_manifest(_fake_pkg, verify_checksum=False)


@pytest.fixture(scope="session")
def app_client():
    from fastapi.testclient import TestClient
    import main
    with TestClient(main.app) as c:
        yield c


@pytest.fixture
def clean_db():
    from db import InferenceJob, InferenceWorker, SessionLocal
    with SessionLocal() as s:
        s.query(InferenceJob).delete()
        s.query(InferenceWorker).delete()
        s.commit()
    yield


__all__ = ["pydicom"]
