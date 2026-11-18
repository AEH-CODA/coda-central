"""Debug CLI: run a model package on a DICOM or .mhd volume and print volumes.

    python cli.py run <file.dcm|oct.mhd> --package models/oct-fluid-spectralis/1.0.0 [--out DIR]

With --out, the full service pipeline runs and writes the same files a job would (result.json, labels.npz, PNGs).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.pipeline import load_volume, run_pipeline  # noqa: E402
from core.quantify import volumes_canvas_mm3, volumes_nl  # noqa: E402
from core.registry import load_adapter  # noqa: E402


def cmd_run(args):
    adapter, device = load_adapter(args.package)
    m = adapter.manifest
    if args.out:
        t = time.time()
        result = run_pipeline(args.input, adapter, device, args.out,
                              progress=lambda stage, pct: print(f"\r{stage:<10} {pct:3d}%", end="", file=sys.stderr))
        print(file=sys.stderr)
        print(json.dumps({k: result[k] for k in ("model", "scan", "volumes_nl", "etdrs_center_mm",
                                                  "etdrs_coverage", "max_height_um", "warnings", "timings_ms")},
                         indent=1))
        print(f"wrote {args.out} in {time.time() - t:.1f}s", file=sys.stderr)
        return
    classes = {c: s.name for c, s in m.classes.items()}
    vol = load_volume(args.input, m)
    t = time.time()
    res = adapter.segment(vol)
    dt = time.time() - t
    report = {
        "model": m.ref, "device": device, "seconds": round(dt, 2),
        "scan": vol.summary(),
        "canvas_shape": res.extras["canvas_shape"],
        "volumes_nl": volumes_nl(res.labels, vol, classes, m.quantification.etdrs_diameters_mm),
        "notebook_equivalent_mm3": volumes_canvas_mm3(res.canvas_labels, res.canvas_px_area_mm2,
                                                      vol.bscan_spacing_mm, classes),
    }
    print(json.dumps(report, indent=1))


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("input")
    r.add_argument("--package", default=os.path.join(os.path.dirname(__file__), "models",
                                                     "oct-fluid-spectralis", "1.0.0"))
    r.add_argument("--out")
    r.set_defaults(fn=cmd_run)
    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
