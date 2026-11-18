"""PNG renders for the report: B-scan display images, label overlays and en-face fluid height maps.

Model-agnostic: everything is driven by the label volume and the manifest's class colours.
"""
from __future__ import annotations

import os

import numpy as np
from PIL import Image

OVERLAY_ALPHA = 0.55
ENFACE_SCALE_MAX_UM = 250.0
ENFACE_MIN_ALPHA = 0.25     # smallest visible opacity for any non-zero fluid height


def hex_to_rgb(color: str) -> tuple[int, int, int]:
    c = color.lstrip("#")
    if len(c) != 6:
        raise ValueError(f"expected #RRGGBB colour, got '{color}'")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def display_window(voxels: np.ndarray, clip_pct=(0.5, 99.5)) -> tuple[float, float]:
    """One intensity window for the whole volume (non-zero pixels), so brightness is consistent across B-scans."""
    sample = voxels[:, ::2, ::2]
    vals = sample[sample > 0]
    if vals.size == 0:
        return 0.0, 1.0
    lo, hi = np.percentile(vals, clip_pct)
    return float(lo), float(max(hi, lo + 1e-6))


def display_image(bscan: np.ndarray, window: tuple[float, float]) -> np.ndarray:
    """(H, W) -> uint8 greyscale on the native grid; zero (padding / no signal) stays black."""
    lo, hi = window
    out = np.round(np.clip((bscan.astype(np.float32) - lo) / (hi - lo), 0, 1) * 255).astype(np.uint8)
    out[bscan <= 0] = 0
    return out


def overlay_rgba(labels: np.ndarray, colors: dict[int, str], alpha: float = OVERLAY_ALPHA) -> np.ndarray:
    """(H, W) labels -> transparent RGBA overlay in class colours (background fully transparent)."""
    out = np.zeros(labels.shape + (4,), np.uint8)
    a = int(round(alpha * 255))
    for c, color in colors.items():
        m = labels == c
        if m.any():
            out[m] = (*hex_to_rgb(color), a)
    return out


def enface_rgba(height_um: np.ndarray, color: str, scale_max_um: float = ENFACE_SCALE_MAX_UM) -> np.ndarray:
    """Isotropic (rows, cols) height map -> RGBA in the class colour; opacity encodes height (0 = transparent).

    The UI legend maps opacity ENFACE_MIN_ALPHA..1 to (0, scale_max_um].
    """
    out = np.zeros(height_um.shape + (4,), np.uint8)
    out[..., :3] = hex_to_rgb(color)
    t = np.clip(height_um / scale_max_um, 0, 1)
    alpha = np.where(height_um > 0.5, ENFACE_MIN_ALPHA + (1 - ENFACE_MIN_ALPHA) * t, 0)
    out[..., 3] = np.round(alpha * 255).astype(np.uint8)
    return out


def save_png(path: str, arr: np.ndarray):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    Image.fromarray(arr).save(path, format="PNG", compress_level=6)


def render_bscans(voxels: np.ndarray, labels: np.ndarray, colors: dict[int, str], out_dir: str, progress=None):
    """Writes bscan/{z}.png and overlay/{z}.png for every B-scan."""
    window = display_window(voxels)
    n = voxels.shape[0]
    for z in range(n):
        save_png(os.path.join(out_dir, "bscan", f"{z}.png"), display_image(voxels[z], window))
        save_png(os.path.join(out_dir, "overlay", f"{z}.png"), overlay_rgba(labels[z], colors))
        if progress:
            progress(z + 1, n)
