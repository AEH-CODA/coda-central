"""Model package registry.

* `resolve_packages` / `load_manifests`: manifest-only (no TensorFlow import), used by the API.
* `load_adapter(s)`: loads weights, picks the compute device (GPU if visible, otherwise CPU) and warms up. Worker / CLI.
"""
from __future__ import annotations

import logging
import os

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
os.environ.setdefault("TF_FORCE_GPU_ALLOW_GROWTH", "true")

from core.adapters import ADAPTERS, ModelAdapter  # noqa: E402
from core.manifest import Manifest, load_manifest  # noqa: E402

log = logging.getLogger(__name__)


def parse_model_refs(spec: str) -> list[tuple[str, str]]:
    """'a@1.0.0, b@2.1.0' -> [('a', '1.0.0'), ('b', '2.1.0')]."""
    refs = []
    for item in (s.strip() for s in spec.split(",")):
        if not item:
            continue
        if "@" not in item:
            raise ValueError(f"model reference '{item}' must be '<id>@<version>'")
        mid, ver = item.split("@", 1)
        refs.append((mid.strip(), ver.strip()))
    return refs


def resolve_packages(models_dir: str, spec: str) -> list[str]:
    return [os.path.join(models_dir, mid, ver) for mid, ver in parse_model_refs(spec)]


def load_manifests(models_dir: str, spec: str, verify_checksum: bool = False) -> dict[str, Manifest]:
    """ref ('id@version') -> manifest, in ENABLED_MODELS order. Raises if a package is missing or invalid."""
    out: dict[str, Manifest] = {}
    for pkg in resolve_packages(models_dir, spec):
        m = load_manifest(pkg, verify_checksum=verify_checksum)
        if m.adapter not in ADAPTERS:
            raise ValueError(f"{m.ref}: unknown adapter '{m.adapter}' (known: {', '.join(ADAPTERS)})")
        out[m.ref] = m
    return out


_DEVICE: str | None = None


def select_device() -> str:
    global _DEVICE
    if _DEVICE is not None:
        return _DEVICE
    import tensorflow as tf

    gpus = tf.config.list_physical_devices("GPU")
    for g in gpus:
        try:
            tf.config.experimental.set_memory_growth(g, True)
        except RuntimeError:
            pass   # already initialised
    _DEVICE = "CPU"
    if gpus:
        try:
            name = tf.config.experimental.get_device_details(gpus[0]).get("device_name", "GPU")
        except Exception:
            name = "GPU"
        _DEVICE = f"GPU:{name}"
    return _DEVICE


def load_adapter(package_dir: str, batch_size: int | None = None, verify_checksum: bool = True,
                 warm_up: bool = True) -> tuple[ModelAdapter, str]:
    import keras
    import numpy as np

    manifest: Manifest = load_manifest(package_dir, verify_checksum=verify_checksum)
    device = select_device()
    if manifest.framework != "keras":
        raise ValueError(f"unsupported framework {manifest.framework}")
    if manifest.adapter not in ADAPTERS:
        raise ValueError(f"{manifest.ref}: unknown adapter '{manifest.adapter}'")
    # The weights are stored with float32 layer policies, so the same file runs on CPU and GPU unchanged.
    model = keras.models.load_model(manifest.path(manifest.weights), compile=False)
    bs = batch_size or (8 if device.startswith("GPU") else 4)
    adapter = ADAPTERS[manifest.adapter](manifest, model, batch_size=bs)

    if warm_up:   # so the first real job does not pay for graph tracing
        c = manifest.input.canvas
        model.predict_on_batch(np.zeros((bs, c.height, c.width, 1), np.float32))
    log.info("loaded %s on %s (batch %d)", manifest.ref, device, bs)
    return adapter, device


def load_adapters(models_dir: str, spec: str, verify_checksum: bool = True) -> tuple[dict[str, ModelAdapter], str]:
    adapters = {}
    device = "CPU"
    for pkg in resolve_packages(models_dir, spec):
        a, device = load_adapter(pkg, verify_checksum=verify_checksum)
        adapters[a.manifest.ref] = a
    return adapters, device
