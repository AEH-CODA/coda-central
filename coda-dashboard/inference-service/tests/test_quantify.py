import numpy as np
import pytest

from core.quantify import enface_isotropic, height_maps_um, volumes_nl
from core.volume import OctVolume

CLASSES = {1: "IRF", 2: "SRF", 3: "PED"}


def cylinder_volume(radius_mm=0.5, height_px=26, dx=0.01, dy=0.0039, dz=0.05, w=800, z=121, h=100):
    """IRF cylinder (axis along depth) centred in the scan."""
    vol = OctVolume(np.zeros((z, h, w), np.float32), dx, dy, np.arange(z) * dz)
    labels = np.zeros((z, h, w), np.uint8)
    cx, cz = w * dx / 2, (z - 1) * dz / 2
    xs = (np.arange(w) + 0.5) * dx
    zs = np.arange(z) * dz
    inside = (xs[None, :] - cx) ** 2 + (zs[:, None] - cz) ** 2 <= radius_mm ** 2
    for k in range(z):
        labels[k, 30:30 + height_px][:, inside[k]] = 1
    return vol, labels, np.pi * radius_mm ** 2 * height_px * dy * 1000


def test_cylinder_volume_matches_analytic():
    vol, labels, expected_nl = cylinder_volume()
    v = volumes_nl(labels, vol, CLASSES)
    assert v["total"]["IRF"] == pytest.approx(expected_nl, rel=0.01)
    assert v["total"]["SRF"] == 0 and v["total"]["PED"] == 0
    # the cylinder (diameter 1 mm) sits at the scan centre: the 1 mm circle contains ~all of it
    assert v["etdrs_1mm"]["IRF"] == pytest.approx(expected_nl, rel=0.02)
    assert v["etdrs_6mm"]["IRF"] == pytest.approx(v["total"]["IRF"])


def test_etdrs_center_override_moves_circle():
    vol, labels, _ = cylinder_volume()
    v = volumes_nl(labels, vol, CLASSES, center_mm=(1.0, 1.0))
    assert v["etdrs_1mm"]["IRF"] == 0
    assert v["center_mm"] == {"x": 1.0, "z": 1.0}


def test_coverage_flags():
    vol, labels, _ = cylinder_volume(w=800, z=121, dz=0.05)   # 8 mm x 6 mm field
    cov = volumes_nl(labels, vol, CLASSES)["etdrs_coverage"]
    assert cov["etdrs_1mm"] and cov["etdrs_6mm"]
    vol2, labels2, _ = cylinder_volume(w=800, z=81, dz=0.05)  # 4 mm tall: 6 mm circle not covered
    assert not volumes_nl(labels2, vol2, CLASSES)["etdrs_coverage"]["etdrs_6mm"]


def test_height_maps_and_enface():
    vol, labels, _ = cylinder_volume(height_px=26)
    hm = height_maps_um(labels, CLASSES, vol.spacing_axial_mm)
    assert hm["IRF"].max() == pytest.approx(26 * 3.9)
    en = enface_isotropic(hm["IRF"], vol, grid_mm=0.02)
    assert en.shape == (round(6.0 / 0.02) + 1, round(8.0 / 0.02))
    assert en.max() == pytest.approx(26 * 3.9, rel=0.05)


def test_etdrs_membership_at_boundary():
    """A-scan centres exactly on the circle are inside; just outside are not."""
    from core.quantify import etdrs_mask
    dx, dz = 0.1, 0.1
    vol = OctVolume(np.zeros((21, 4, 21), np.float32), dx, 0.004, np.arange(21) * dz)
    # A-scan x centres are (i + 0.5) * dx; put the centre on one so distances are exact multiples of 0.1 mm
    center = (10.5 * dx, 10 * dz)
    m = etdrs_mask(vol, center, diameter_mm=1.0)
    assert m[10, 10] and m[10, 15] and m[15, 10] and m[5, 10]     # 0.5 mm away: on the circle -> inside
    assert not m[10, 16] and not m[16, 10]                         # 0.6 mm away
    assert not m[14, 14]                                           # sqrt(0.32) = 0.566 mm diagonal


def test_etdrs_summary_shape():
    from core.quantify import etdrs_summary
    vol, labels, _ = cylinder_volume()
    s = etdrs_summary(labels, vol, CLASSES, [1, 3, 6])
    assert set(s["volumes_nl"]) == {"total", "etdrs_1mm", "etdrs_3mm", "etdrs_6mm"}
    assert s["etdrs_center_mm"]["source"] == "scan_center"
    assert etdrs_summary(labels, vol, CLASSES, [1], center_mm=(1, 1))["etdrs_center_mm"]["source"] == "user"


def test_geometry_only_volume_gives_same_numbers():
    vol, labels, _ = cylinder_volume()
    g = OctVolume.geometry_only(vol.voxels.shape, vol.spacing_lateral_mm, vol.spacing_axial_mm,
                                vol.bscan_positions_mm)
    assert volumes_nl(labels, g, CLASSES) == volumes_nl(labels, vol, CLASSES)
