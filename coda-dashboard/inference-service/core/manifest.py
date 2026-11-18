"""model.yaml schema: the contract every model package must satisfy."""
from __future__ import annotations

import hashlib
import os
from typing import Literal

import yaml
from pydantic import BaseModel, Field


class TargetSpacing(BaseModel):
    lateral: float
    axial: float


class CanvasSpec(BaseModel):
    height: int = 512
    width: int = 576
    # dynamic: grow the canvas (rounded up to `multiple_of`) instead of cropping when the resampled B-scan is larger.
    # For B-scans that already fit, the result is identical to the fixed canvas used in training.
    dynamic: bool = True
    multiple_of: int = 16


class Harmonization(BaseModel):
    method: Literal["none", "histogram_match", "gamma"] = "none"
    reference: str | None = None    # histogram_match: .npy file in the package (probabilities for uint8 values 1..255)
    gamma: float = 1.0              # gamma: exponent applied to the stretched [0, 1] intensities
    dither: bool = False            # histogram_match: break ties of coarsely quantised inputs before matching
    seed: int = 0


PaddingStrategy = Literal["edge_connected_zero_runs", "zero_border"]


class InputSpec(BaseModel):
    supported_manufacturers: list[str] = Field(default_factory=list)
    supported_models: list[str] = Field(default_factory=list)
    target_spacing_mm: TargetSpacing
    canvas: CanvasSpec = CanvasSpec()
    clip_percentiles: tuple[float, float] = (0.5, 99.5)
    padding: PaddingStrategy = "edge_connected_zero_runs"
    # Per source format (e.g. "dicom-opt", "mhd") overrides for harmonization; "default" applies otherwise.
    harmonization: dict[str, Harmonization] = Field(default_factory=lambda: {"default": Harmonization()})
    padding_overrides: dict[str, PaddingStrategy] = Field(default_factory=dict)

    def harmonization_for(self, source_format: str) -> Harmonization:
        return self.harmonization.get(source_format) or self.harmonization.get("default") or Harmonization()

    def padding_for(self, source_format: str) -> str:
        return self.padding_overrides.get(source_format, self.padding)


class ClassSpec(BaseModel):
    name: str
    label: str
    color: str


class Quantification(BaseModel):
    units: Literal["nL"] = "nL"
    etdrs_diameters_mm: list[float] = Field(default_factory=lambda: [1.0, 3.0, 6.0])


class ReportSpec(BaseModel):
    disclaimer: str = "Research use only. Not for clinical diagnosis."
    # Per source format (e.g. "dicom-opt") report warnings; "default" applies to every input.
    warnings: dict[str, list[str]] = Field(default_factory=dict)

    def warnings_for(self, source_format: str) -> list[str]:
        return list(self.warnings.get("default", [])) + list(self.warnings.get(source_format, []))


class Manifest(BaseModel):
    id: str
    version: str
    display_name: str
    task: str
    modality: str
    adapter: str
    framework: Literal["keras"]
    weights: str
    sha256: str | None = None
    input: InputSpec
    classes: dict[int, ClassSpec]
    quantification: Quantification = Quantification()
    report: ReportSpec = ReportSpec()

    # set by load_manifest
    package_dir: str = ""

    @property
    def class_names(self) -> dict[int, str]:
        return {c: s.name for c, s in self.classes.items()}

    @property
    def class_colors(self) -> dict[int, str]:
        return {c: s.color for c, s in self.classes.items()}

    def public(self) -> dict:
        """What the API exposes in /inference/models (no paths, no checksums of local files)."""
        return {
            "ref": self.ref, "id": self.id, "version": self.version, "display_name": self.display_name,
            "task": self.task, "modality": self.modality,
            "classes": [{"id": c, **s.model_dump()} for c, s in sorted(self.classes.items())],
            "supported_manufacturers": self.input.supported_manufacturers,
            "supported_models": self.input.supported_models,
            "etdrs_diameters_mm": self.quantification.etdrs_diameters_mm,
        }

    @property
    def ref(self) -> str:
        return f"{self.id}@{self.version}"

    def path(self, rel: str) -> str:
        return os.path.join(self.package_dir, rel)


def sha256_file(path: str, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while b := f.read(chunk):
            h.update(b)
    return h.hexdigest()


def load_manifest(package_dir: str, verify_checksum: bool = True) -> Manifest:
    with open(os.path.join(package_dir, "model.yaml")) as f:
        m = Manifest(**yaml.safe_load(f), package_dir=os.path.abspath(package_dir))
    weights = m.path(m.weights)
    if not os.path.exists(weights):
        raise FileNotFoundError(f"{m.ref}: weights file missing: {weights}")
    if verify_checksum and m.sha256:
        actual = sha256_file(weights)
        if actual != m.sha256:
            raise ValueError(f"{m.ref}: sha256 mismatch for {m.weights} (expected {m.sha256}, got {actual})")
    return m
