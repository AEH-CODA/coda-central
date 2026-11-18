"""Phase 0: choose DICOM preprocessing (padding strategy x intensity harmonization).

1. Build the RETOUCH intensity reference (histogram of stretched uint8 values on training B-scans).
2. Estimate a RETOUCH-raw -> DICOM-raw transfer curve by quantile matching pooled intensities, and use it to
   simulate the DICOM domain (curve shape + 0..100 quantisation) on RETOUCH volumes, which have ground truth.
3. Score every variant on the held-out validation B-scans (val_split.json) with the notebook's metrics.
4. Run the best variants on the real sample DICOMs and write contact sheets for visual review.

    python experiments/phase0_domain.py --retouch ~/Desktop/OCT_Others/RETOUCH --dicoms tests/data/sample_spectralis
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import time

import cv2
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from core.adapters.refattn_unet_v1 import (PADDING_FNS, edge_padding, new_size, reference_histogram,  # noqa: E402
                                           resize_2d, to_canvas, zero_border_padding)
from core.ingest import read_dicom_opt  # noqa: E402
from core.ingest.mhd import read_mhd_array  # noqa: E402
from core.manifest import Harmonization  # noqa: E402
from core.quantify import volumes_nl  # noqa: E402
from core.registry import load_adapter  # noqa: E402
from core.volume import OctVolume  # noqa: E402

CLASSES = {1: "IRF", 2: "SRF", 3: "PED"}
COLORS = {1: (229, 57, 53), 2: (251, 192, 45), 3: (30, 136, 229)}

VARIANTS = {
    # name: (padding, Harmonization)
    "pad=edge | none":          ("edge_connected_zero_runs", Harmonization(method="none")),
    "pad=border | none":        ("zero_border", Harmonization(method="none")),
    "pad=edge | gamma0.5":      ("edge_connected_zero_runs", Harmonization(method="gamma", gamma=0.5)),
    "pad=edge | hist":          ("edge_connected_zero_runs", Harmonization(method="histogram_match", reference="REF")),
    "pad=edge | hist+dither":   ("edge_connected_zero_runs", Harmonization(method="histogram_match", reference="REF", dither=True)),
    "pad=border | hist+dither": ("zero_border", Harmonization(method="histogram_match", reference="REF", dither=True)),
}


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


# ---------------------------------------------------------------- data

def load_train(retouch: str):
    root = os.path.join(retouch, "RETOUCH-TrainingSet-Spectralis")
    cases = {}
    for case in sorted(os.listdir(root)):
        d = os.path.join(root, case)
        if not os.path.isfile(os.path.join(d, "oct.mhd")):
            continue
        vol, sp = read_mhd_array(os.path.join(d, "oct.mhd"))
        ref, _ = read_mhd_array(os.path.join(d, "reference.mhd"))
        cases[case] = (vol, ref, sp)
    return cases


def transfer_curve(train_cases, dicom_vols, n_q=2001):
    """Monotone map RETOUCH raw -> DICOM raw by matching pooled quantiles of image (non-padding) pixels."""
    rng = np.random.default_rng(0)
    r_vals = []
    for vol, _, _ in train_cases.values():
        for z in range(0, vol.shape[0], 4):
            img = vol[z]
            r_vals.append(rng.choice(img[~edge_padding(img)], 20000))
    d_vals = []
    for v in dicom_vols:
        for z in range(0, v.n_bscans, 2):
            img = v.voxels[z]
            d_vals.append(rng.choice(img[~zero_border_padding(img)], 20000))
    q = np.linspace(0, 100, n_q)
    rq = np.percentile(np.concatenate(r_vals), q)
    dq = np.percentile(np.concatenate(d_vals), q)
    rq = rq + np.arange(n_q) * 1e-6            # strictly increasing for interp
    return rq, dq


def simulate_dicom(vol: np.ndarray, curve) -> np.ndarray:
    rq, dq = curve
    pad = np.stack([edge_padding(b) for b in vol])
    out = np.rint(np.interp(vol.astype(np.float64), rq, dq)).astype(np.float32)
    out[pad] = 0
    return out


# ---------------------------------------------------------------- scoring (notebook metrics)

def gt_to_canvas(mask, sp_lat, sp_ax, tgt, canvas_hw):
    h, w = mask.shape
    nh, nw = new_size(h, w, sp_lat, sp_ax, tgt.lateral, tgt.axial)
    return to_canvas(resize_2d(mask, nh, nw, True), *canvas_hw)[0]


def score(pred, gt):
    out, scores = {}, []
    for c, n in CLASSES.items():
        pc, gc = pred == c, gt == c
        tp, fp, fn = (pc & gc).sum((1, 2)), (pc & ~gc).sum((1, 2)), (~pc & gc).sum((1, 2))
        pos = (tp + fn) > 0
        fa = fp[~pos].sum()
        out[f"fa_{n}"] = float(fa / max(fa + tp[pos].sum() + fn[pos].sum(), 1))
        out[f"dice_{n}"] = float(2 * tp[pos].sum() / max(2 * tp[pos].sum() + fp[pos].sum() + fn[pos].sum(), 1))
        scores.append(out[f"dice_{n}"] - out[f"fa_{n}"])
    out["score"] = float(np.mean(scores))
    return out


def eval_variant(adapter, train_cases, val_ids, curve, padding, harm, simulate=True):
    tgt = adapter.manifest.input.target_spacing_mm
    preds, gts = [], []
    for case, (vol, ref, sp) in train_cases.items():
        zs = sorted(z for c, z in val_ids if c == case)
        if not zs:
            continue
        vox = simulate_dicom(vol, curve) if simulate else vol.astype(np.float32)
        meta = {"value_range": [0.0, 100.0]} if simulate else {}
        ov = OctVolume(vox, sp[0], sp[1], np.arange(vol.shape[0]) * sp[2], source_format="sim", meta=meta)
        canv, _ = adapter.preprocess(ov, padding=padding, harmonization=harm)
        sel = canv[zs]
        preds.append(adapter.predict_labels(sel))
        g = np.stack([gt_to_canvas(ref[z], sp[0], sp[1], tgt, canv.shape[1:]) for z in zs])
        g[sel == 0] = 0
        gts.append(g)
    return score(np.concatenate(preds), np.concatenate(gts))


# ---------------------------------------------------------------- contact sheets

def overlay(img_u8, lab):
    rgb = cv2.cvtColor(img_u8, cv2.COLOR_GRAY2RGB).astype(np.float32)
    for c, col in COLORS.items():
        m = lab == c
        rgb[m] = rgb[m] * 0.45 + np.array(col) * 0.55
    return rgb.astype(np.uint8)


def display(img):
    v = img[img > 0]
    lo, hi = (np.percentile(v, (0.5, 99.5)) if v.size else (0, 1))
    return (np.clip((img - lo) / max(hi - lo, 1e-6), 0, 1) * 255).astype(np.uint8)


def label_bar(text, w):
    bar = np.full((28, w, 3), 255, np.uint8)
    cv2.putText(bar, text, (6, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 1, cv2.LINE_AA)
    return bar


def contact_sheet(path, vol, rows, zs, scale=0.5):
    """rows: list of (title, labels(Z,H,W)). Columns: chosen B-scans. First row = raw image."""
    tiles = []
    first = [display(vol.voxels[z]) for z in zs]
    tiles.append(("input (display stretch)", [cv2.cvtColor(t, cv2.COLOR_GRAY2RGB) for t in first]))
    for title, lab in rows:
        tiles.append((title, [overlay(first[i], lab[z]) for i, z in enumerate(zs)]))
    out_rows = []
    for title, imgs in tiles:
        row = np.concatenate([np.pad(cv2.resize(t, None, fx=scale, fy=scale), ((0, 0), (0, 4), (0, 0)),
                                     constant_values=255) for t in imgs], axis=1)
        out_rows.append(label_bar(title, row.shape[1]))
        out_rows.append(row)
    cv2.imwrite(path, cv2.cvtColor(np.concatenate(out_rows, axis=0), cv2.COLOR_RGB2BGR))


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--retouch", required=True)
    ap.add_argument("--dicoms", required=True)
    ap.add_argument("--package", default=os.path.join(os.path.dirname(__file__), "..", "models",
                                                      "oct-fluid-spectralis", "1.0.0"))
    ap.add_argument("--val-split", help="default: <package>/training/val_split.json")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "out"))
    ap.add_argument("--variants", nargs="*", help="subset of variant names")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    adapter, device = load_adapter(args.package)
    log("model loaded on", device)
    val_ids = [tuple(x) for x in json.load(open(args.val_split or os.path.join(args.package, "training", "val_split.json")))["val_bscans"]]
    val_set = set(val_ids)
    train_cases = load_train(args.retouch)
    dicom_paths = sorted(glob.glob(os.path.join(args.dicoms, "*.dcm")))
    dicom_vols = [read_dicom_opt(p) for p in dicom_paths]
    log(f"{len(train_cases)} training volumes, {len(val_ids)} val B-scans, {len(dicom_vols)} DICOMs")

    # 1. reference histogram from TRAIN-split B-scans, notebook preprocessing
    ref_path = adapter.manifest.path("intensity_reference.npy")
    canv_all = []
    for case, (vol, _, sp) in train_cases.items():
        ov = OctVolume(vol.astype(np.float32), sp[0], sp[1], np.arange(vol.shape[0]) * sp[2], source_format="mhd")
        c, _ = adapter.preprocess(ov, padding="edge_connected_zero_runs", harmonization=Harmonization())
        keep = [z for z in range(len(c)) if (case, z) not in val_set]
        canv_all.append(c[keep])
    reference = reference_histogram(np.concatenate(canv_all))
    np.save(ref_path, reference)
    adapter._reference = reference
    log("saved", ref_path)

    # 2. transfer curve
    curve = transfer_curve(train_cases, dicom_vols)
    np.save(os.path.join(args.out, "transfer_curve.npy"), np.stack(curve))
    stats = {}
    for name, (vols, padfn) in {"retouch_sim": ([simulate_dicom(v, curve) for v, _, _ in list(train_cases.values())[:3]], edge_padding),
                                "dicom": ([v.voxels for v in dicom_vols], zero_border_padding)}.items():
        x = np.concatenate([v[::5].ravel() for v in vols])
        stats[name] = {"zero_frac": float((x == 0).mean()), "p50": float(np.median(x)), "p99": float(np.percentile(x, 99))}
    log("domain check (raw values)", stats)

    # 3. score variants on validation B-scans
    results = {}
    t = time.time()
    results["RETOUCH original (upper bound)"] = eval_variant(adapter, train_cases, val_ids, curve,
                                                             "edge_connected_zero_runs", Harmonization(), simulate=False)
    log("baseline", results["RETOUCH original (upper bound)"], f"{time.time()-t:.0f}s")
    names = args.variants or list(VARIANTS)
    for name in names:
        pad, harm = VARIANTS[name]
        if harm.reference == "REF":
            harm = harm.model_copy(update={"reference": "intensity_reference.npy"})
        t = time.time()
        results[name] = eval_variant(adapter, train_cases, val_ids, curve, pad, harm)
        log(name, {k: round(v, 3) for k, v in results[name].items()}, f"{time.time()-t:.0f}s")
        json.dump(results, open(os.path.join(args.out, "simulated_scores.json"), "w"), indent=1)

    # 4. real DICOMs: top variants by simulated score + pad=edge|none as the "as-trained" reference
    ranked = sorted(names, key=lambda n: results[n]["score"], reverse=True)
    show = list(dict.fromkeys(ranked[:3] + ["pad=edge | none"]))
    dicom_report = {}
    for path, vol in zip(dicom_paths, dicom_vols):
        base = os.path.splitext(os.path.basename(path))[0]
        rows, vols_by_variant = [], {}
        for name in show:
            pad, harm = VARIANTS[name]
            if harm.reference == "REF":
                harm = harm.model_copy(update={"reference": "intensity_reference.npy"})
            res = adapter.segment(vol, padding=pad, harmonization=harm)
            rows.append((name, res.labels))
            v = volumes_nl(res.labels, vol, CLASSES)
            vols_by_variant[name] = {k: {c: round(x, 1) for c, x in v[k].items()} for k in ("total", "etdrs_1mm", "etdrs_6mm")}
            log(base, name, vols_by_variant[name]["total"])
        fluid = sum((lab > 0).sum(axis=(1, 2)) for _, lab in rows)
        zs = sorted(np.argsort(fluid)[-3:].tolist())
        contact_sheet(os.path.join(args.out, f"sheet_{base}.png"), vol, rows, zs)
        dicom_report[base] = {"bscans_shown": zs, "volumes_nl": vols_by_variant}
    json.dump(dicom_report, open(os.path.join(args.out, "dicom_volumes.json"), "w"), indent=1)

    print("\n| variant | score | Dice IRF | Dice SRF | Dice PED | FA IRF | FA SRF | FA PED |\n|---|---|---|---|---|---|---|---|")
    for n, r in results.items():
        print(f"| {n} | {r['score']:.3f} | {r['dice_IRF']:.3f} | {r['dice_SRF']:.3f} | {r['dice_PED']:.3f} | "
              f"{r['fa_IRF']:.3f} | {r['fa_SRF']:.3f} | {r['fa_PED']:.3f} |")


if __name__ == "__main__":
    main()
