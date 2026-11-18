"""DICOM Ophthalmic Tomography (OPT, multi-frame) -> OctVolume.

Spacing lives in the functional-group sequences for Spectralis exports, not at the top level. DICOM PixelSpacing is
[row spacing, column spacing] = [axial, lateral]; the training notebook uses (lateral, axial), so the order is
swapped here explicitly.
"""
from __future__ import annotations

import numpy as np
import pydicom

from core.volume import OctVolume

OPT_SOP_CLASS = "1.2.840.10008.5.1.4.1.1.77.1.5.4"   # Ophthalmic Tomography Image Storage


class IngestError(ValueError):
    """Input rejected; `code` is a stable machine-readable reason, message is safe to show to users."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _first(seq_owner, *path):
    """Walk ds.Seq1[0].Seq2[0]...attr, returning None if anything is missing."""
    cur = seq_owner
    for name in path[:-1]:
        seq = getattr(cur, name, None)
        if not seq:
            return None
        cur = seq[0]
    return getattr(cur, path[-1], None)


def _pixel_spacing(ds) -> tuple[float, float] | None:
    """Returns (axial_mm, lateral_mm)."""
    candidates = [
        _first(ds, "SharedFunctionalGroupsSequence", "PixelMeasuresSequence", "PixelSpacing"),
        _first(ds, "PerFrameFunctionalGroupsSequence", "PixelMeasuresSequence", "PixelSpacing"),
        getattr(ds, "PixelSpacing", None),
    ]
    for ps in candidates:
        if ps is not None and len(ps) == 2 and float(ps[0]) > 0 and float(ps[1]) > 0:
            return float(ps[0]), float(ps[1])
    return None


def _slice_thickness(ds) -> float | None:
    for v in (
        _first(ds, "SharedFunctionalGroupsSequence", "PixelMeasuresSequence", "SliceThickness"),
        getattr(ds, "SpacingBetweenSlices", None),
        getattr(ds, "SliceThickness", None),
    ):
        if v is not None and float(v) > 0:
            return float(v)
    return None


def _frame_order_and_positions(ds, n_frames: int) -> tuple[np.ndarray, np.ndarray | None]:
    """Returns (frame order, slow-axis positions in that order, relative to the first B-scan) if available."""
    pf = getattr(ds, "PerFrameFunctionalGroupsSequence", None)
    order = np.arange(n_frames)
    if not pf or len(pf) != n_frames:
        return order, None

    stack_pos = [_first(f, "FrameContentSequence", "InStackPositionNumber") for f in pf]
    if all(p is not None for p in stack_pos):
        order = np.argsort(np.asarray(stack_pos, dtype=np.int64), kind="stable")

    ipp = [_first(f, "PlanePositionSequence", "ImagePositionPatient") for f in pf]
    if not all(p is not None and len(p) == 3 for p in ipp):
        return order, None
    pos = np.asarray(ipp, dtype=np.float64)[order]
    axis = int(np.argmax(np.ptp(pos, axis=0)))
    if np.ptp(pos[:, axis]) <= 0:
        return order, None
    slow = np.abs(pos[:, axis] - pos[0, axis])
    if np.any(np.diff(slow) <= 0):
        return order, None
    return order, slow


def _read(path_or_file, stop_before_pixels: bool):
    try:
        return pydicom.dcmread(path_or_file, stop_before_pixels=stop_before_pixels)
    except Exception as e:
        raise IngestError("invalid_dicom", "The file is not a readable DICOM file.") from e


def _check_header(ds, allowed_manufacturers: list[str] | None,
                  allowed_models: list[str] | None) -> tuple[str, str, float, float]:
    """Validates SOP class, device and pixel spacing. Returns (manufacturer, model, axial_mm, lateral_mm)."""
    sop = str(getattr(ds, "SOPClassUID", ""))
    if sop != OPT_SOP_CLASS:
        raise IngestError("unsupported_sop_class",
                          f"Expected an OCT volume (Ophthalmic Tomography, {OPT_SOP_CLASS}); got SOP class '{sop or 'none'}'.")

    manufacturer = str(getattr(ds, "Manufacturer", "") or "").strip()
    device_model = str(getattr(ds, "ManufacturerModelName", "") or "").strip()
    if allowed_manufacturers and manufacturer not in allowed_manufacturers:
        raise IngestError("unsupported_device",
                          f"This file is from '{manufacturer or 'unknown manufacturer'}'; "
                          f"the model supports {', '.join(allowed_manufacturers)} only.")
    if allowed_models and device_model not in allowed_models:
        raise IngestError("unsupported_device",
                          f"This file is from device '{device_model or 'unknown'}'; "
                          f"the model supports {', '.join(allowed_models)} only.")

    spacing = _pixel_spacing(ds)
    if spacing is None:
        raise IngestError("missing_spacing", "The DICOM has no pixel spacing; fluid volumes cannot be computed.")
    return manufacturer, device_model, spacing[0], spacing[1]


def _laterality(ds) -> str | None:
    lat = str(getattr(ds, "ImageLaterality", "") or getattr(ds, "Laterality", "") or "").upper()
    return {"L": "OS", "R": "OD"}.get(lat)


def _study_date(ds) -> str | None:
    d = str(getattr(ds, "StudyDate", "") or "")
    if len(d) == 8 and d.isdigit():
        return f"{d[:4]}-{d[4:6]}-{d[6:]}"
    return None


def inspect_dicom_opt(path_or_file, allowed_manufacturers: list[str] | None = None,
                      allowed_models: list[str] | None = None) -> dict:
    """Header-only validation (no pixel decoding), used by the API before a job is queued.

    Applies the same checks as read_dicom_opt except pixel decoding, and returns non-PHI metadata.
    """
    ds = _read(path_or_file, stop_before_pixels=True)
    manufacturer, device_model, axial_mm, lateral_mm = _check_header(ds, allowed_manufacturers, allowed_models)
    n = int(getattr(ds, "NumberOfFrames", 1) or 1)
    rows, cols = int(getattr(ds, "Rows", 0) or 0), int(getattr(ds, "Columns", 0) or 0)
    if rows <= 0 or cols <= 0:
        raise IngestError("invalid_pixel_data", "The DICOM has no image dimensions.")
    _, positions = _frame_order_and_positions(ds, n)
    if positions is None and n > 1 and _slice_thickness(ds) is None:
        raise IngestError("missing_spacing", "The DICOM has no B-scan spacing; fluid volumes cannot be computed.")
    return {
        "manufacturer": manufacturer,
        "device_model": device_model,
        "laterality": _laterality(ds),
        "study_date": _study_date(ds),
        "n_bscans": n,
        "bscan_shape": [rows, cols],
        "spacing_mm": {"lateral": lateral_mm, "axial": axial_mm},
    }


def read_dicom_opt(path_or_file, allowed_manufacturers: list[str] | None = None,
                   allowed_models: list[str] | None = None) -> OctVolume:
    ds = _read(path_or_file, stop_before_pixels=False)
    manufacturer, device_model, axial_mm, lateral_mm = _check_header(ds, allowed_manufacturers, allowed_models)

    try:
        px = ds.pixel_array
    except Exception as e:
        raise IngestError("invalid_pixel_data", f"Pixel data could not be decoded: {e}") from e
    if px.ndim == 2:
        px = px[None]
    if px.ndim != 3:
        raise IngestError("invalid_pixel_data", f"Expected a multi-frame greyscale volume, got shape {px.shape}.")
    n = px.shape[0]

    order, positions = _frame_order_and_positions(ds, n)
    px = px[order]
    if positions is None:
        thick = _slice_thickness(ds)
        if thick is None and n > 1:
            raise IngestError("missing_spacing", "The DICOM has no B-scan spacing; fluid volumes cannot be computed.")
        positions = np.arange(n) * (thick or 0.0)

    vox = px.astype(np.float32)
    slope = float(getattr(ds, "RescaleSlope", 1) or 1)
    intercept = float(getattr(ds, "RescaleIntercept", 0) or 0)
    if slope != 1 or intercept != 0:
        vox = vox * slope + intercept
    if str(getattr(ds, "PhotometricInterpretation", "MONOCHROME2")) == "MONOCHROME1":
        vox = vox.max() - vox

    return OctVolume(
        voxels=vox,
        spacing_lateral_mm=lateral_mm,
        spacing_axial_mm=axial_mm,
        bscan_positions_mm=positions,
        manufacturer=manufacturer,
        device_model=device_model,
        laterality=_laterality(ds),
        study_date=_study_date(ds),
        source_format="dicom-opt",
        meta={
            "bits_stored": int(getattr(ds, "BitsStored", 0) or 0),
            "value_range": [float(px.min()), float(px.max())],
            "image_type": list(getattr(ds, "ImageType", []) or []),
        },
    )
