"""Vendor-neutral OCT volume: the contract between ingest and model adapters."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class OctVolume:
    voxels: np.ndarray                 # (Z, H, W), B-scans in acquisition order; H = axial (depth), W = lateral
    spacing_lateral_mm: float          # along a B-scan (x)
    spacing_axial_mm: float            # depth (y)
    bscan_positions_mm: np.ndarray     # (Z,) slow-axis position of each B-scan, starting at 0
    manufacturer: str = ""
    device_model: str = ""
    laterality: str | None = None      # "OD" | "OS" | None
    study_date: str | None = None
    source_format: str = ""            # "dicom-opt" | "mhd"
    meta: dict = field(default_factory=dict)   # non-PHI extras only

    def __post_init__(self):
        if self.voxels.ndim != 3:
            raise ValueError(f"voxels must be (Z, H, W), got shape {self.voxels.shape}")
        self.bscan_positions_mm = np.asarray(self.bscan_positions_mm, dtype=np.float64)
        if len(self.bscan_positions_mm) != self.voxels.shape[0]:
            raise ValueError("bscan_positions_mm length must equal the number of B-scans")
        if self.spacing_lateral_mm <= 0 or self.spacing_axial_mm <= 0:
            raise ValueError("pixel spacing must be positive")

    @classmethod
    def geometry_only(cls, shape: tuple[int, int, int], spacing_lateral_mm: float, spacing_axial_mm: float,
                      bscan_positions_mm, **kw) -> "OctVolume":
        """A volume with geometry but no pixel data (zero-copy), e.g. to recompute ETDRS volumes from saved labels."""
        return cls(np.broadcast_to(np.zeros((), np.float32), tuple(shape)), spacing_lateral_mm, spacing_axial_mm,
                   bscan_positions_mm, **kw)

    @property
    def n_bscans(self) -> int:
        return self.voxels.shape[0]

    @property
    def bscan_spacing_mm(self) -> np.ndarray:
        """Per-B-scan slow-axis spacing (Cavalieri weight). Uniform scans give a constant array."""
        if self.n_bscans == 1:
            return np.array([0.0])
        return np.abs(np.gradient(self.bscan_positions_mm))

    def summary(self) -> dict:
        z, h, w = self.voxels.shape
        return {
            "manufacturer": self.manufacturer,
            "device_model": self.device_model,
            "laterality": self.laterality,
            "study_date": self.study_date,
            "source_format": self.source_format,
            "n_bscans": z,
            "bscan_shape": [h, w],
            "spacing_mm": {
                "lateral": self.spacing_lateral_mm,
                "axial": self.spacing_axial_mm,
                "bscan": float(np.median(self.bscan_spacing_mm)) if z > 1 else None,
            },
            "field_mm": {
                "width": round(w * self.spacing_lateral_mm, 3),
                "height": round(float(np.ptp(self.bscan_positions_mm)), 3),
                "depth": round(h * self.spacing_axial_mm, 3),
            },
        }
