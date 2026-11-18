"""Model adapter interface. One adapter per family of models that share pre/post-processing."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import numpy as np

from core.manifest import Manifest
from core.volume import OctVolume


@dataclass
class SegmentationResult:
    labels: np.ndarray                    # (Z, H, W) uint8 on the native B-scan grid of the input volume
    canvas_labels: np.ndarray | None = None   # (Z, Hc, Wc) uint8 in model space (debug / notebook-equivalent metrics)
    canvas_images: np.ndarray | None = None   # (Z, Hc, Wc) uint8 model input before z-scoring
    canvas_px_area_mm2: np.ndarray | None = None  # (Z,) effective pixel area in model space
    extras: dict = field(default_factory=dict)


class ModelAdapter(ABC):
    def __init__(self, manifest: Manifest, model):
        self.manifest = manifest
        self.model = model

    @abstractmethod
    def segment(self, volume: OctVolume, progress=None) -> SegmentationResult:
        """Run the full adapter pipeline: preprocess -> predict -> map labels back to the native grid."""
