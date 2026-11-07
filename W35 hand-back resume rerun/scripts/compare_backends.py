"""Item 1: the GPU pass and the CPU pass of each dock scenario side by side, from the numbers_<scenario>_<backend>.json
files that run_dock.ps1 brings back. Writes ../results/item1_backends.json and prints a table.

The existing tests hold the two backends to each other at 1e-3 of a peak (tests/engine/test_handback.py: the GPU's
hand-back volume within rel 1e-3 of the CPU's) and the plugin's own checks at 1e-5 on rain. Here: every series peak of
every run, the relative difference, flagged over 1e-3; the balance fields the same.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

DOCK = Path(__file__).resolve().parents[1] / "dock"
RESULTS = Path(__file__).resolve().parents[1] / "results"
TOL = 1e-3
SCENARIOS = ("dock_basin_bidah_w32", "dock_mesh_controls_w32", "dock_result_lines_w32", "dock_storm_w32")


def summary(log: Path) -> str:
    if not log.exists():
        return "no log"
    for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
        if "SUMMARY" in line:
            return line.split("SUMMARY", 1)[1].strip()
    return "no summary"


def failures(log: Path) -> list[str]:
    if not log.exists():
        return []
    return [s.strip() for s in log.read_text(encoding="utf-8", errors="replace").splitlines() if s.strip().startswith("FAILED") or " FAIL " in s]


def compare(gpu: dict, cpu: dict) -> dict:
    out = {}
    for run in gpu:
        if run not in cpu:
            out[run] = {"missing_on_cpu": True}
            continue
        g, p = gpu[run], cpu[run]
        rows = []
        for series, columns in g.get("peaks", {}).items():
            for column, (peak, at) in columns.items():
                other = p.get("peaks", {}).get(series, {}).get(column)
                if other is None:
                    rows.append({"series": series, "column": column, "gpu": peak, "cpu": None})
                    continue
                rel = (other[0] - peak) / peak if peak else other[0] - peak
                rows.append({"series": series, "column": column, "gpu": peak, "cpu": other[0], "rel": rel, "at_gpu_h": at, "at_cpu_h": other[1], "over": abs(rel) > TOL and peak > 1.0})
        balance = {}
        for key, value in g.get("balance", {}).items():
            other = p.get("balance", {}).get(key)
            if isinstance(value, (int, float)) and isinstance(other, (int, float)):
                rel = (other - value) / value if value else other - value
                balance[key] = {"gpu": value, "cpu": other, "rel": rel}
        out[run] = {
            "backend": (g.get("backend"), p.get("backend")), "cells": (g.get("cells"), p.get("cells")),
            "steps": (g.get("steps"), p.get("steps")), "loop_s": (g.get("loop_s"), p.get("loop_s")),
            "exit": (g.get("exit"), p.get("exit")), "peaks": rows, "balance": balance,
            "worst_rel": max((abs(r["rel"]) for r in rows if r.get("rel") is not None and r["gpu"] > 1.0), default=0.0),
            "over_tolerance": [r for r in rows if r.get("over")],
        }  # fmt: skip
    return out


def main() -> None:
    report = {}
    print(f"| Scenario | GPU checks | CPU checks | Runs compared | Worst peak difference | Over {TOL:.0e} |")
    print("|---|---|---|---|---|---|")
    for name in SCENARIOS:
        g, p = DOCK / f"numbers_{name}_gpu.json", DOCK / f"numbers_{name}_cpu.json"
        gpu = json.loads(g.read_text(encoding="utf-8")) if g.exists() else {}
        cpu = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
        comp = compare(gpu, cpu)
        worst = max((v.get("worst_rel", 0.0) for v in comp.values() if "worst_rel" in v), default=0.0)
        worst_run = max(((v.get("worst_rel", 0.0), k) for k, v in comp.items() if "worst_rel" in v), default=(0.0, ""))[1]
        over = sum(len(v.get("over_tolerance", [])) for v in comp.values())
        report[name] = {
            "gpu_summary": summary(DOCK / f"log_{name}_gpu.txt"), "cpu_summary": summary(DOCK / f"log_{name}_cpu.txt"),
            "gpu_failures": failures(DOCK / f"log_{name}_gpu.txt"), "cpu_failures": failures(DOCK / f"log_{name}_cpu.txt"),
            "runs": comp, "worst_rel": worst, "worst_run": worst_run, "over_tolerance": over,
        }  # fmt: skip
        print(f"| {name} | {report[name]['gpu_summary']} | {report[name]['cpu_summary']} | {len(comp)} | {worst:.2e} ({worst_run}) | {over} |")
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "item1_backends.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    for name, r in report.items():
        for run, v in r["runs"].items():
            for row in v.get("over_tolerance", []):
                print(f"  {name} / {run} / {row['series']}.{row['column']}: GPU {row['gpu']:.4f} CPU {row['cpu']:.4f} ({row['rel']:+.2e}) at {row['at_gpu_h']:.2f} / {row['at_cpu_h']:.2f} h")


if __name__ == "__main__":
    sys.exit(main())
