import glob
import os

import numpy as np
import pytest

from conftest import SAMPLE_DICOM_DIR
from core.ingest import IngestError, inspect_dicom_opt, read_dicom_opt


def test_spacing_order_is_axial_then_lateral(opt_dicom):
    v = read_dicom_opt(opt_dicom(axial=0.0039, lateral=0.0115))
    assert v.spacing_axial_mm == pytest.approx(0.0039)
    assert v.spacing_lateral_mm == pytest.approx(0.0115)


def test_positions_and_frame_order(opt_dicom):
    v = read_dicom_opt(opt_dicom(n=6, spacing=0.25, shuffle_frames=True))
    np.testing.assert_allclose(v.bscan_positions_mm, np.arange(6) * 0.25)
    # frame k was filled with value k+1; after sorting by InStackPositionNumber they must be in order
    assert [int(v.voxels[i, 0, 0]) for i in range(6)] == [1, 2, 3, 4, 5, 6]
    np.testing.assert_allclose(v.bscan_spacing_mm, 0.25)


def test_positions_fall_back_to_slice_thickness(opt_dicom):
    v = read_dicom_opt(opt_dicom(n=4, spacing=0.3, with_positions=False))
    np.testing.assert_allclose(v.bscan_positions_mm, [0, 0.3, 0.6, 0.9])


def test_laterality_and_metadata(opt_dicom):
    v = read_dicom_opt(opt_dicom(laterality="R"))
    assert v.laterality == "OD"
    assert v.study_date == "2025-01-01"
    assert "Test" not in str(v.summary()) and "Test" not in str(v.meta)   # no PHI carried along


def test_rejects_missing_spacing(opt_dicom):
    with pytest.raises(IngestError) as e:
        read_dicom_opt(opt_dicom(with_spacing=False))
    assert e.value.code == "missing_spacing"


def test_rejects_non_opt(opt_dicom):
    with pytest.raises(IngestError) as e:
        read_dicom_opt(opt_dicom(sop="1.2.840.10008.5.1.4.1.1.2"))   # CT
    assert e.value.code == "unsupported_sop_class"


def test_rejects_other_vendor(opt_dicom):
    with pytest.raises(IngestError) as e:
        read_dicom_opt(opt_dicom(manufacturer="Carl Zeiss Meditec", model="Cirrus"),
                       allowed_manufacturers=["Heidelberg Engineering"])
    assert e.value.code == "unsupported_device"
    assert "Heidelberg" in str(e.value)


def test_rejects_garbage(tmp_path):
    p = tmp_path / "x.dcm"
    p.write_bytes(b"not a dicom")
    with pytest.raises(IngestError) as e:
        read_dicom_opt(str(p))
    assert e.value.code == "invalid_dicom"


SAMPLES = sorted(glob.glob(os.path.join(SAMPLE_DICOM_DIR, "*.dcm")))


@pytest.mark.skipif(not SAMPLES, reason="sample DICOMs not available")
@pytest.mark.parametrize("path", SAMPLES, ids=os.path.basename)
def test_sample_spectralis(path):
    v = read_dicom_opt(path, ["Heidelberg Engineering"], ["Spectralis"])
    assert v.voxels.shape == (31, 496, 768)
    assert v.spacing_lateral_mm == pytest.approx(0.011484)
    assert v.spacing_axial_mm == pytest.approx(0.0038717, rel=1e-4)
    assert v.bscan_positions_mm[-1] == pytest.approx(7.34019, rel=1e-5)
    assert v.laterality == "OS"
    assert v.summary()["field_mm"]["width"] == pytest.approx(8.82, abs=0.01)


def test_inspect_matches_full_read_without_pixels(opt_dicom):
    p = opt_dicom(n=6, rows=40, cols=70, axial=0.004, lateral=0.012, spacing=0.2, laterality="L")
    meta = inspect_dicom_opt(p, ["Heidelberg Engineering"], ["Spectralis"])
    vol = read_dicom_opt(p)
    assert meta["n_bscans"] == vol.n_bscans and meta["bscan_shape"] == list(vol.voxels.shape[1:])
    assert meta["spacing_mm"] == {"lateral": vol.spacing_lateral_mm, "axial": vol.spacing_axial_mm}
    assert meta["laterality"] == "OS" and meta["study_date"] == "2025-01-01"
    assert "PatientName" not in str(meta) and "Test" not in str(meta)


@pytest.mark.parametrize("kw,code", [
    ({"manufacturer": "Topcon"}, "unsupported_device"),
    ({"sop": "1.2.840.10008.5.1.4.1.1.2"}, "unsupported_sop_class"),
    ({"with_spacing": False}, "missing_spacing"),
])
def test_inspect_rejections(opt_dicom, kw, code):
    with pytest.raises(IngestError) as e:
        inspect_dicom_opt(opt_dicom(**kw), ["Heidelberg Engineering"], ["Spectralis"])
    assert e.value.code == code
