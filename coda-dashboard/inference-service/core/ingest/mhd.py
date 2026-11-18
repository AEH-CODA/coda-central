"""MetaImage (.mhd/.raw) reader, used for the RETOUCH golden test and the CLI (not exposed via the API)."""
from __future__ import annotations

import os

import numpy as np

from core.volume import OctVolume

_MET_TYPES = {"MET_UCHAR": np.uint8, "MET_USHORT": np.uint16, "MET_SHORT": np.int16, "MET_FLOAT": np.float32}


def read_mhd_array(path: str) -> tuple[np.ndarray, list[float]]:
    """Same semantics as the training notebook's read_mhd: returns (Z, H, W) array and spacing (x, y, z) in mm."""
    hdr = {}
    with open(path) as f:
        for line in f:
            if "=" in line:
                k, v = line.split("=", 1)
                hdr[k.strip()] = v.strip()
    w, h, z = (int(x) for x in hdr["DimSize"].split())
    spacing = [float(x) for x in hdr["ElementSpacing"].split()]
    dt = np.dtype(_MET_TYPES[hdr["ElementType"]]).newbyteorder(
        ">" if hdr.get("BinaryDataByteOrderMSB", "False") == "True" else "<")
    arr = np.fromfile(os.path.join(os.path.dirname(path), hdr["ElementDataFile"]), dtype=dt)
    if arr.size != w * h * z:
        raise ValueError(f"size mismatch in {path}")
    return arr.reshape(z, h, w).astype(_MET_TYPES[hdr["ElementType"]]), spacing


def read_mhd(path: str, manufacturer: str = "Heidelberg Engineering", device_model: str = "Spectralis") -> OctVolume:
    arr, (sx, sy, sz) = read_mhd_array(path)
    return OctVolume(
        voxels=arr,
        spacing_lateral_mm=sx,
        spacing_axial_mm=sy,
        bscan_positions_mm=np.arange(arr.shape[0]) * sz,
        manufacturer=manufacturer,
        device_model=device_model,
        source_format="mhd",
    )
