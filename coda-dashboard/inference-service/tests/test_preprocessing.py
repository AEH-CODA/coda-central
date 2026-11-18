import numpy as np
import pytest

from core.adapters.refattn_unet_v1 import (BscanInfo, canvas_to_original, edge_padding,
                                           harmonize, normalise, reference_histogram, to_canvas, zero_border_padding)
from core.manifest import Harmonization


def test_to_canvas_matches_notebook_when_it_fits():
    a = np.arange(496 * 469, dtype=np.uint8).reshape(496, 469)
    out, rows, x0 = to_canvas(a, 512, 576)
    assert out.shape == (512, 576) and rows == 496 and x0 == (576 - 469) // 2
    np.testing.assert_array_equal(out[:496, x0:x0 + 469], a)
    assert out[496:].sum() == 0


def test_dynamic_canvas_never_crops(adapter):
    assert adapter.canvas_size(496, 469) == (512, 576)       # RETOUCH-sized: identical to training canvas
    h, w = adapter.canvas_size(496, 789)                       # sample DICOM width after resampling
    assert w >= 789 and w % 16 == 0 and h == 512


def test_canvas_round_trip():
    lab = np.zeros((512, 800), np.uint8)
    lab[100:150, 20:780] = 2
    info = BscanInfo(H=496, W=768, H_res=496, W_res=789, rows_kept=496, x_off=(800 - 789) // 2,
                     eff_x_mm=0.011174, eff_y_mm=0.003872)
    back = canvas_to_original(lab, info)
    assert back.shape == (496, 768)
    assert (back == 2).any() and set(np.unique(back)) <= {0, 2}


def test_padding_strategies():
    img = np.ones((10, 12), np.float32)
    img[:3, :] = 0          # black vitreous at the top (touches top edge)...
    img[:3, 7] = 1          # ...with occasional speckle, so its rows are not entirely zero
    img[:, -2:] = 0         # fully-zero padding strip on the right
    img[6, 5] = 0           # dark pixel inside the image (data)
    e = edge_padding(img)
    assert e[:3, :7].all() and e[:, -2:].all() and not e[6, 5]   # notebook rule treats the vitreous as padding
    b = zero_border_padding(img)
    assert b[:, -2:].all() and not b[:3, :10].any() and not b[6, 5]


def test_normalise_ignores_padding():
    x = np.zeros((1, 4, 4), np.uint8)
    x[0, :2] = 100
    x[0, 2, :2] = 200
    z = normalise(x)
    assert (z[0][x[0] == 0] == 0).all()
    v = z[0][x[0] > 0]
    assert v.mean() == pytest.approx(0, abs=1e-5) and v.std() == pytest.approx(1, abs=1e-3)


def test_harmonize_none_is_identity():
    c = np.random.default_rng(0).integers(0, 256, (2, 8, 8)).astype(np.uint8)
    np.testing.assert_array_equal(harmonize(c, Harmonization(), None), c)


def test_histogram_match_hits_reference_and_keeps_padding():
    rng = np.random.default_rng(0)
    ref_src = np.clip(rng.normal(120, 30, (4, 64, 64)), 1, 255).astype(np.uint8)
    ref = reference_histogram(ref_src)
    c = np.clip(rng.normal(40, 5, (4, 64, 64)), 1, 255).astype(np.uint8)
    c[:, :, :4] = 0
    out = harmonize(c, Harmonization(method="histogram_match", dither=True), ref, raw_levels=101)
    assert (out[:, :, :4] == 0).all()
    v = out[out > 0]
    assert abs(v.mean() - 120) < 3 and abs(v.std() - 30) < 3
