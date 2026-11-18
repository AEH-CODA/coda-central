import numpy as np
import pytest

from core.render import display_image, display_window, enface_rgba, hex_to_rgb, overlay_rgba


def test_hex_to_rgb():
    assert hex_to_rgb("#1E88E5") == (0x1E, 0x88, 0xE5)
    with pytest.raises(ValueError):
        hex_to_rgb("#fff")


def test_overlay_colours_and_transparency():
    lab = np.zeros((4, 4), np.uint8)
    lab[0, 0], lab[1, 1], lab[2, 2] = 1, 2, 3
    o = overlay_rgba(lab, {1: "#E53935", 2: "#FBC02D", 3: "#1E88E5"})
    assert o.shape == (4, 4, 4) and o.dtype == np.uint8
    assert tuple(o[0, 0]) == (0xE5, 0x39, 0x35, 140)
    assert tuple(o[2, 2][:3]) == (0x1E, 0x88, 0xE5)
    assert o[3, 3, 3] == 0


def test_enface_opacity_encodes_height():
    h = np.array([[0.0, 1.0, 125.0, 250.0, 400.0]])
    e = enface_rgba(h, "#E53935", scale_max_um=250)
    a = e[0, :, 3]
    assert a[0] == 0                       # no fluid -> transparent
    assert 0 < a[1] < a[2] < a[3] == a[4] == 255


def test_display_image_keeps_zero_black_and_uses_volume_window():
    vol = np.stack([np.full((10, 10), v, np.float32) for v in (10, 50, 90)])
    vol[:, 0, :] = 0
    win = display_window(vol)
    imgs = [display_image(b, win) for b in vol]
    assert all(i[0].max() == 0 for i in imgs)
    assert imgs[0][5, 5] < imgs[1][5, 5] < imgs[2][5, 5]   # one window for the whole volume
