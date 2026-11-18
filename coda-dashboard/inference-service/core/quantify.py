"""Model-agnostic quantification of a label volume: fluid volumes (total / ETDRS) and en-face height maps.

Volumes use Cavalieri summation (pixel area x B-scan spacing), the same estimator the model was validated with.
Interpolation between B-scans is only used for display (en-face maps), never for the reported numbers.
"""
from __future__ import annotations

import cv2
import numpy as np

from core.volume import OctVolume

MM3_TO_NL = 1000.0


def height_maps_um(labels: np.ndarray, classes: dict[int, str], axial_mm: float) -> dict[str, np.ndarray]:
    """Per class: (Z, W) fluid thickness per A-scan in micrometres."""
    return {name: (labels == c).sum(axis=1).astype(np.float64) * axial_mm * 1000.0 for c, name in classes.items()}


def etdrs_mask(volume: OctVolume, center_mm: tuple[float, float], diameter_mm: float) -> np.ndarray:
    """(Z, W) boolean: A-scans whose (lateral, slow-axis) position lies within the circle."""
    w = volume.voxels.shape[2]
    x = (np.arange(w) + 0.5) * volume.spacing_lateral_mm
    z = volume.bscan_positions_mm
    dx = x[None, :] - center_mm[0]
    dz = z[:, None] - center_mm[1]
    return dx ** 2 + dz ** 2 <= (diameter_mm / 2) ** 2


def scan_center_mm(volume: OctVolume) -> tuple[float, float]:
    w = volume.voxels.shape[2]
    pos = volume.bscan_positions_mm
    return w * volume.spacing_lateral_mm / 2, float(pos.min() + pos.max()) / 2


def volumes_nl(labels: np.ndarray, volume: OctVolume, classes: dict[int, str],
               etdrs_diameters_mm=(1.0, 3.0, 6.0), center_mm: tuple[float, float] | None = None) -> dict:
    """Total and ETDRS-circle fluid volumes in nanolitres, computed on the native B-scan grid."""
    center = center_mm or scan_center_mm(volume)
    dz = volume.bscan_spacing_mm[:, None]                                      # (Z, 1)
    col_area = volume.spacing_lateral_mm * volume.spacing_axial_mm * dz       # mm^2 * mm per pixel, per B-scan
    counts = {name: (labels == c).sum(axis=1) for c, name in classes.items()}  # (Z, W)

    out = {"total": {n: float((cnt * col_area).sum() * MM3_TO_NL) for n, cnt in counts.items()}}
    for d in etdrs_diameters_mm:
        m = etdrs_mask(volume, center, d)
        out[f"etdrs_{d:g}mm"] = {n: float((cnt * col_area * m).sum() * MM3_TO_NL) for n, cnt in counts.items()}
    # does the scan cover the whole circle? (reported so the UI can flag partial coverage)
    width_mm = volume.voxels.shape[2] * volume.spacing_lateral_mm
    pos = volume.bscan_positions_mm
    out["etdrs_coverage"] = {
        f"etdrs_{d:g}mm": bool(center[0] - d / 2 >= 0 and center[0] + d / 2 <= width_mm
                               and center[1] - d / 2 >= pos.min() - 1e-9 and center[1] + d / 2 <= pos.max() + 1e-9)
        for d in etdrs_diameters_mm
    }
    out["center_mm"] = {"x": float(center[0]), "z": float(center[1])}
    return out


def volumes_canvas_mm3(canvas_labels: np.ndarray, px_area_mm2: np.ndarray, bscan_spacing_mm: np.ndarray,
                       classes: dict[int, str]) -> dict[str, float]:
    """Notebook-equivalent volumes (counted on the model canvas with effective pixel size), in mm^3."""
    return {name: float(((canvas_labels == c).sum(axis=(1, 2)) * px_area_mm2 * bscan_spacing_mm).sum())
            for c, name in classes.items()}


def bscan_stats(labels: np.ndarray, volume: OctVolume, classes: dict[int, str]) -> list[dict]:
    px_area = volume.spacing_lateral_mm * volume.spacing_axial_mm
    counts = {name: (labels == c).sum(axis=(1, 2)) for c, name in classes.items()}
    return [{"z": int(z), "position_mm": float(volume.bscan_positions_mm[z]),
             "area_mm2": {n: float(counts[n][z] * px_area) for n in counts}}
            for z in range(labels.shape[0])]


def enface_isotropic(height_map: np.ndarray, volume: OctVolume, grid_mm: float = 0.02) -> np.ndarray:
    """Resample a (Z, W) height map onto an isotropic grid, linearly interpolating between B-scans (display only)."""
    z, w = height_map.shape
    out_w = max(1, int(round(w * volume.spacing_lateral_mm / grid_mm)))
    span = float(np.ptp(volume.bscan_positions_mm)) if z > 1 else grid_mm
    out_h = max(1, int(round(span / grid_mm)) + 1)
    if z == 1:
        return cv2.resize(height_map.astype(np.float32), (out_w, out_h), interpolation=cv2.INTER_LINEAR)
    # lateral first (area-average when shrinking), then interpolate across (possibly non-uniform) B-scan positions
    lat = cv2.resize(height_map.astype(np.float32), (out_w, z), interpolation=cv2.INTER_AREA)
    targets = volume.bscan_positions_mm.min() + np.arange(out_h) * grid_mm
    idx = np.interp(targets, volume.bscan_positions_mm, np.arange(z))
    i0 = np.floor(idx).astype(int)
    i1 = np.minimum(i0 + 1, z - 1)
    t = (idx - i0)[:, None]
    return (lat[i0] * (1 - t) + lat[i1] * t).astype(np.float32)


def max_height_um(height_maps: dict[str, np.ndarray]) -> dict[str, float]:
    return {n: float(h.max()) if h.size else 0.0 for n, h in height_maps.items()}


def etdrs_summary(labels: np.ndarray, volume: OctVolume, classes: dict[int, str], diameters_mm,
                  center_mm: tuple[float, float] | None = None, ndigits: int = 3) -> dict:
    """Report-shaped volumes: {volumes_nl: {total, etdrs_*}, etdrs_center_mm, etdrs_coverage}."""
    v = volumes_nl(labels, volume, classes, diameters_mm, center_mm)
    vols = {k: {n: round(x, ndigits) for n, x in d.items()} for k, d in v.items()
            if k == "total" or (k.startswith("etdrs_") and k != "etdrs_coverage")}
    return {
        "volumes_nl": vols,
        "etdrs_center_mm": {"x": round(v["center_mm"]["x"], 4), "z": round(v["center_mm"]["z"], 4),
                            "source": "scan_center" if center_mm is None else "user"},
        "etdrs_coverage": v["etdrs_coverage"],
    }
