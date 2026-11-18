"""Adapter for the RETOUCH-trained reference attention U-Net (OCT_Fluid_Spectralis_RefAttUNet.ipynb).

Each function mirrors the notebook function of the same name; deviations are explicit and configurable:
  * canvas size can grow (instead of center-cropping) when the resampled B-scan is larger than 512 x 576
  * padding detection strategy is selectable
  * optional intensity harmonization for input domains that differ from RETOUCH
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import cv2
import numpy as np

from core.adapters.base import ModelAdapter, SegmentationResult
from core.manifest import Harmonization, Manifest
from core.volume import OctVolume


# ---------------------------------------------------------------- notebook ports (pure functions)

def resize_2d(img: np.ndarray, new_h: int, new_w: int, is_mask: bool) -> np.ndarray:
    if is_mask:
        return cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_NEAREST)
    out = img.astype(np.float32)
    h, w = out.shape
    if new_h != h:
        out = cv2.resize(out, (w, new_h), interpolation=cv2.INTER_AREA if new_h < h else cv2.INTER_LINEAR)
    if new_w != w:
        out = cv2.resize(out, (new_w, new_h), interpolation=cv2.INTER_AREA if new_w < w else cv2.INTER_LINEAR)
    return out


def stretch_to_uint8(img: np.ndarray, pad: np.ndarray, clip_pct=(0.5, 99.5)) -> np.ndarray:
    vals = img[~pad]
    if vals.size < 100:
        return np.zeros(img.shape, np.uint8)
    lo, hi = np.percentile(vals, clip_pct)
    out = np.round(np.clip((img - lo) / max(hi - lo, 1e-6), 0, 1) * 254 + 1).astype(np.uint8)
    out[pad] = 0
    return out


def to_canvas(a: np.ndarray, canvas_h: int, canvas_w: int):
    h, w = a.shape
    out = np.zeros((canvas_h, canvas_w), a.dtype)
    rows = min(h, canvas_h)
    if w <= canvas_w:
        x0 = (canvas_w - w) // 2
        out[:rows, x0:x0 + w] = a[:rows]
        return out, rows, x0
    c = (w - canvas_w) // 2
    out[:rows] = a[:rows, c:c + canvas_w]
    return out, rows, -c


def edge_padding(img: np.ndarray) -> np.ndarray:
    """Notebook: runs of zeros that start at an image edge are padding; zeros inside the image (dark fluid) are data."""
    z = (img == 0).astype(np.uint8)
    pad = np.cumprod(z, axis=0).astype(bool)
    pad |= np.cumprod(z[::-1], axis=0)[::-1].astype(bool)
    pad |= np.cumprod(z, axis=1).astype(bool)
    pad |= np.cumprod(z[:, ::-1], axis=1)[:, ::-1].astype(bool)
    return pad


def zero_border_padding(img: np.ndarray) -> np.ndarray:
    """Only fully-zero rows/columns are padding (keeps black vitreous as image content)."""
    z = img == 0
    pad = np.zeros(img.shape, bool)
    pad[z.all(axis=1), :] = True
    pad[:, z.all(axis=0)] = True
    return pad



PADDING_FNS = {
    "edge_connected_zero_runs": edge_padding,
    "zero_border": zero_border_padding,
}


def normalise(x: np.ndarray) -> np.ndarray:
    """uint8 (N,H,W) -> float32 z-score over non-padding pixels of each B-scan; padding -> 0."""
    valid = x > 0
    xf = x.astype(np.float32)
    n = np.maximum(valid.sum(axis=(1, 2), keepdims=True), 1)
    mean = (xf * valid).sum(axis=(1, 2), keepdims=True) / n
    var = (((xf - mean) * valid) ** 2).sum(axis=(1, 2), keepdims=True) / n
    return np.where(valid, (xf - mean) / np.sqrt(var + 1e-6), 0).astype(np.float32)


def _ceil_to(v: int, m: int) -> int:
    return int(math.ceil(v / m) * m)


# ---------------------------------------------------------------- harmonization (operates on stretched uint8 canvases)

def harmonize(canvases: np.ndarray, cfg: Harmonization, reference: np.ndarray | None,
              raw_levels: int | None = None) -> np.ndarray:
    """Map non-padding intensities (1..255) of the whole volume to the RETOUCH training domain."""
    if cfg.method == "none":
        return canvases
    out = canvases.copy()
    valid = canvases > 0
    v = canvases[valid].astype(np.float64)
    if v.size == 0:
        return out

    if cfg.method == "gamma":
        f = (v - 1) / 254
        out[valid] = np.clip(np.round(f ** cfg.gamma * 254 + 1), 1, 255).astype(np.uint8)
        return out

    if cfg.method == "histogram_match":
        if reference is None:
            raise ValueError("histogram_match requires a reference histogram")
        if cfg.dither:
            # coarse inputs (e.g. 101 raw levels) collapse into few uint8 values; spread each value over its bin so
            # quantile matching yields a continuous distribution instead of a few large steps
            step = 254 / max((raw_levels or 101) - 1, 1)
            rng = np.random.default_rng(cfg.seed)
            v = v + rng.uniform(-step / 2, step / 2, v.shape)
        ranks = np.argsort(np.argsort(v, kind="stable"), kind="stable")
        q = (ranks + 0.5) / v.size                                    # empirical quantile of every pixel
        ref = np.asarray(reference, np.float64)
        ref_cdf = np.cumsum(ref / ref.sum())
        ref_vals = np.arange(1, 256, dtype=np.float64)
        mapped = np.interp(q, ref_cdf, ref_vals)
        out[valid] = np.clip(np.round(mapped), 1, 255).astype(np.uint8)
        return out

    raise ValueError(f"unknown harmonization method {cfg.method}")


def reference_histogram(canvases: np.ndarray) -> np.ndarray:
    """Probabilities of uint8 values 1..255 over non-padding pixels (input for histogram_match)."""
    v = canvases[canvases > 0]
    h = np.bincount(v.ravel(), minlength=256)[1:256].astype(np.float64)
    return h / h.sum()


# ---------------------------------------------------------------- per-volume preprocessing

@dataclass
class BscanInfo:
    H: int
    W: int
    H_res: int
    W_res: int
    rows_kept: int
    x_off: int
    eff_x_mm: float
    eff_y_mm: float


def new_size(h: int, w: int, sp_lat: float, sp_ax: float, tgt_lat: float, tgt_ax: float) -> tuple[int, int]:
    return int(round(h * sp_ax / tgt_ax)), int(round(w * sp_lat / tgt_lat))


def canvas_to_original(lab: np.ndarray, info: BscanInfo) -> np.ndarray:
    r = np.zeros((info.H_res, info.W_res), np.uint8)
    rows, x = info.rows_kept, info.x_off
    if x >= 0:
        r[:rows] = lab[:rows, x:x + info.W_res]
    else:
        r[:rows, -x:-x + lab.shape[1]] = lab[:rows]
    return cv2.resize(r, (info.W, info.H), interpolation=cv2.INTER_NEAREST)


class RefAttUNetV1(ModelAdapter):
    name = "refattn_unet_v1"

    def __init__(self, manifest: Manifest, model, batch_size: int = 8, reference: np.ndarray | None = None):
        super().__init__(manifest, model)
        self.batch_size = batch_size
        self._reference = reference

    # --- preprocessing
    def reference(self, cfg: Harmonization) -> np.ndarray | None:
        if cfg.method != "histogram_match":
            return None
        if self._reference is None:
            self._reference = np.load(self.manifest.path(cfg.reference))
        return self._reference

    def canvas_size(self, h_res: int, w_res: int) -> tuple[int, int]:
        c = self.manifest.input.canvas
        if not c.dynamic:
            return c.height, c.width
        return max(c.height, _ceil_to(h_res, c.multiple_of)), max(c.width, _ceil_to(w_res, c.multiple_of))

    def preprocess(self, volume: OctVolume, padding: str | None = None, harmonization: Harmonization | None = None):
        spec = self.manifest.input
        padding = padding or spec.padding_for(volume.source_format)
        harmonization = harmonization or spec.harmonization_for(volume.source_format)
        pad_fn = PADDING_FNS[padding]
        tgt = spec.target_spacing_mm
        z, h, w = volume.voxels.shape
        h_res, w_res = new_size(h, w, volume.spacing_lateral_mm, volume.spacing_axial_mm, tgt.lateral, tgt.axial)
        ch, cw = self.canvas_size(h_res, w_res)

        canv = np.zeros((z, ch, cw), np.uint8)
        infos = []
        for i in range(z):
            img = volume.voxels[i]
            r = resize_2d(img, h_res, w_res, False)
            pad = resize_2d(pad_fn(img).astype(np.uint8), h_res, w_res, True) > 0
            canv[i], rows, x_off = to_canvas(stretch_to_uint8(r, pad, spec.clip_percentiles), ch, cw)
            infos.append(BscanInfo(H=h, W=w, H_res=h_res, W_res=w_res, rows_kept=rows, x_off=x_off,
                                   eff_x_mm=volume.spacing_lateral_mm * w / w_res,
                                   eff_y_mm=volume.spacing_axial_mm * h / h_res))

        raw_levels = None
        if volume.meta.get("value_range"):
            lo, hi = volume.meta["value_range"]
            raw_levels = int(hi - lo + 1)
        canv = harmonize(canv, harmonization, self.reference(harmonization), raw_levels)
        return canv, infos

    # --- inference
    def predict_labels(self, imgs_u8: np.ndarray, progress=None) -> np.ndarray:
        out = np.zeros(imgs_u8.shape, np.uint8)
        b = self.batch_size
        for s in range(0, len(imgs_u8), b):
            chunk = imgs_u8[s:s + b]
            n = len(chunk)
            x = normalise(chunk)[..., None]
            if n < b:   # fixed batch shape avoids re-tracing
                x = np.concatenate([x, np.zeros((b - n,) + x.shape[1:], x.dtype)])
            lab = np.asarray(self.model.predict_on_batch(x))[:n].argmax(-1).astype(np.uint8)
            lab[chunk == 0] = 0
            out[s:s + n] = lab
            if progress:
                progress(min(s + n, len(imgs_u8)), len(imgs_u8))
        return out

    def segment(self, volume: OctVolume, progress=None, padding: str | None = None,
                harmonization: Harmonization | None = None) -> SegmentationResult:
        canv, infos = self.preprocess(volume, padding, harmonization)
        pred = self.predict_labels(canv, progress)
        native = np.stack([canvas_to_original(pred[i], infos[i]) for i in range(len(pred))])
        return SegmentationResult(
            labels=native,
            canvas_labels=pred,
            canvas_images=canv,
            canvas_px_area_mm2=np.array([i.eff_x_mm * i.eff_y_mm for i in infos]),
            extras={"canvas_shape": list(canv.shape[1:]), "resampled_shape": [infos[0].H_res, infos[0].W_res]},
        )
