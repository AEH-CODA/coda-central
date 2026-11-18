"""Regression: the service pipeline must reproduce the training notebook on RETOUCH TEST015.

Reference values: models/oct-fluid-spectralis/1.0.0/training/test_predicted_volumes.csv (Colab GPU). Tolerance covers CPU fp32 vs
GPU numerical differences.
"""
import os

import pytest

from conftest import RETOUCH_TEST015
from core.ingest import read_mhd
from core.quantify import volumes_canvas_mm3, volumes_nl

EXPECTED_MM3 = {"IRF": 0.7169002570113361, "SRF": 0.004349568811268606, "PED": 1.6876951787661933}
CLASSES = {1: "IRF", 2: "SRF", 3: "PED"}


def close(actual, expected):
    return abs(actual - expected) <= max(0.02 * expected, 0.005)


@pytest.mark.slow
@pytest.mark.skipif(not os.path.exists(RETOUCH_TEST015), reason="RETOUCH TEST015 not available")
def test_test015_matches_notebook(adapter):
    vol = read_mhd(RETOUCH_TEST015)
    res = adapter.segment(vol)
    assert res.extras["canvas_shape"] == [512, 576]   # dynamic canvas == training canvas for RETOUCH size

    nb = volumes_canvas_mm3(res.canvas_labels, res.canvas_px_area_mm2, vol.bscan_spacing_mm, CLASSES)
    native = volumes_nl(res.labels, vol, CLASSES)["total"]
    for n, exp in EXPECTED_MM3.items():
        assert close(nb[n], exp), f"{n}: canvas {nb[n]:.5f} vs notebook {exp:.5f}"
        assert close(native[n] / 1000, exp), f"{n}: native {native[n] / 1000:.5f} vs notebook {exp:.5f}"
