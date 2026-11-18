"""ingest -> adapter -> quantify -> render -> result.json, for one input file.

Job directory layout (written by run_pipeline, served by the API):
    input.dcm                 upload (deleted after processing unless KEEP_INPUT)
    labels.npz                labels (Z, H, W) uint8 + geometry, used for ETDRS re-centering and download
    result.json               the report (same object stored in inference_jobs.result_json)
    bscan/{z}.png             8-bit B-scan on the native grid
    overlay/{z}.png           RGBA label overlay
    enface/{CLASS}.png        RGBA isotropic fluid height map, row 0 = first B-scan in acquisition order
"""
from __future__ import annotations

import json
import os
import time
from typing import Callable

import numpy as np

from core.adapters.base import ModelAdapter
from core.ingest import read_dicom_opt, read_mhd
from core.manifest import Manifest
from core.quantify import bscan_stats, enface_isotropic, etdrs_summary, height_maps_um, max_height_um
from core.render import ENFACE_SCALE_MAX_UM, enface_rgba, render_bscans, save_png
from core.volume import OctVolume

ENFACE_GRID_MM = 0.02
LABELS_FILE = "labels.npz"
RESULT_FILE = "result.json"

# stage -> (start %, end %) of overall job progress
STAGES = {"ingest": (0, 5), "inference": (5, 80), "quantify": (80, 85), "render": (85, 100)}

ProgressFn = Callable[[str, int], None]


class Cancelled(Exception):
    """Raised from a progress callback to abort a job."""


def load_volume(path: str, manifest: Manifest | None = None) -> OctVolume:
    if path.lower().endswith(".mhd"):
        return read_mhd(path)
    spec = manifest.input if manifest else None
    return read_dicom_opt(path, spec.supported_manufacturers if spec else None,
                          spec.supported_models if spec else None)


def save_labels(path: str, labels: np.ndarray, volume: OctVolume):
    np.savez_compressed(path, labels=labels, bscan_positions_mm=volume.bscan_positions_mm,
                        spacing_lateral_mm=volume.spacing_lateral_mm, spacing_axial_mm=volume.spacing_axial_mm)


def load_labels(path: str) -> tuple[np.ndarray, OctVolume]:
    """Labels plus a pixel-free volume with the original geometry."""
    with np.load(path) as f:
        labels = f["labels"]
        vol = OctVolume.geometry_only(labels.shape, float(f["spacing_lateral_mm"]), float(f["spacing_axial_mm"]),
                                      f["bscan_positions_mm"])
    return labels, vol


def _stage_progress(progress: ProgressFn | None, stage: str):
    lo, hi = STAGES[stage]

    def cb(done: int, total: int):
        if progress:
            progress(stage, int(lo + (hi - lo) * done / max(total, 1)))
    if progress:
        progress(stage, lo)
    return cb


def build_result(manifest: Manifest, device: str, volume: OctVolume, labels: np.ndarray,
                 height_maps: dict[str, np.ndarray], enface_shape: list[int]) -> dict:
    names = manifest.class_names
    scan = volume.summary()
    s = etdrs_summary(labels, volume, names, manifest.quantification.etdrs_diameters_mm)
    warnings = manifest.report.warnings_for(volume.source_format)
    uncovered = [k.removeprefix("etdrs_") for k, ok in s["etdrs_coverage"].items() if not ok]
    if uncovered:
        warnings.append(f"The scan does not fully cover the ETDRS {', '.join(uncovered)} circle(s); "
                        "those volumes include only the scanned area.")
    return {
        "model": {"id": manifest.id, "version": manifest.version, "sha256": manifest.sha256, "device": device},
        "scan": {
            "manufacturer": scan["manufacturer"], "device_model": scan["device_model"],
            "laterality": scan["laterality"], "study_date": scan["study_date"],
            "source_format": scan["source_format"],
            "n_bscans": scan["n_bscans"], "bscan_shape": scan["bscan_shape"],
            "spacing_mm": scan["spacing_mm"], "field_mm": scan["field_mm"],
            "bscan_positions_mm": [round(float(p), 5) for p in volume.bscan_positions_mm],
        },
        "classes": [{"id": c, **cs.model_dump()} for c, cs in sorted(manifest.classes.items())],
        **s,
        "bscans": bscan_stats(labels, volume, names),
        "max_height_um": {n: round(v, 1) for n, v in max_height_um(height_maps).items()},
        "enface": {"grid_mm_per_px": ENFACE_GRID_MM, "shape": enface_shape, "scale_max_um": ENFACE_SCALE_MAX_UM,
                   "row0": "first_bscan", "encoding": "class colour, opacity = height"},
        "warnings": warnings,
        "disclaimer": manifest.report.disclaimer,
    }


def run_pipeline(input_path: str, adapter: ModelAdapter, device: str, out_dir: str,
                 progress: ProgressFn | None = None) -> dict:
    """Runs one job end to end and writes all outputs into out_dir. Returns the result dict."""
    m = adapter.manifest
    t0 = time.time()
    timings = {}

    _stage_progress(progress, "ingest")
    volume = load_volume(input_path, m)
    timings["ingest"] = time.time() - t0

    t = time.time()
    seg = adapter.segment(volume, progress=_stage_progress(progress, "inference"))
    labels = seg.labels
    timings["inference"] = time.time() - t

    t = time.time()
    _stage_progress(progress, "quantify")
    hm = height_maps_um(labels, m.class_names, volume.spacing_axial_mm)
    enface = {n: enface_isotropic(h, volume, ENFACE_GRID_MM) for n, h in hm.items()}
    enface_shape = list(next(iter(enface.values())).shape)
    result = build_result(m, device, volume, labels, hm, enface_shape)
    timings["quantify"] = time.time() - t

    t = time.time()
    render_cb = _stage_progress(progress, "render")
    os.makedirs(out_dir, exist_ok=True)
    save_labels(os.path.join(out_dir, LABELS_FILE), labels, volume)
    colors = m.class_colors
    by_name = {cs.name: cs.color for cs in m.classes.values()}
    for name, grid in enface.items():
        save_png(os.path.join(out_dir, "enface", f"{name}.png"), enface_rgba(grid, by_name[name]))
    render_bscans(volume.voxels, labels, colors, out_dir, progress=render_cb)
    timings["render"] = time.time() - t

    result["timings_ms"] = {k: int(v * 1000) for k, v in timings.items()}
    result["model"]["canvas_shape"] = seg.extras.get("canvas_shape")
    write_result(out_dir, result)
    if progress:
        progress("render", 100)
    return result


def write_result(out_dir: str, result: dict):
    tmp = os.path.join(out_dir, RESULT_FILE + ".tmp")
    with open(tmp, "w") as f:
        json.dump(result, f, indent=1)
    os.replace(tmp, os.path.join(out_dir, RESULT_FILE))
