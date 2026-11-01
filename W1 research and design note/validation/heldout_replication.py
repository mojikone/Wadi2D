"""Held-out check: the replication rules were found on Block 2; do they hold on other HMS projects?

Reads the projects read-only, runs every depth-area analysis in parallel, prints per project the analyses compared,
the point-peaks, the worst error and the counts beyond 1 % and 2 %, and what was left out. With --json it saves
every comparison to that file. Run from the repository root.
"""

import argparse
import json
import os
import sys
import warnings
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
from pathlib import Path

warnings.simplefilter("ignore")
from wadi2d.hms import load_nals  # noqa: E402
from wadi2d.hydrology.replication import Comparison, replicate  # noqa: E402

PROJECTS = {
    "Block 4": r"D:\Mojtaba\Renardet\2224 WS11\Batinah\Block 4\Hydrology\HEC_HMS_Block_04\HEC_HMS_Block_04.hms",
    "Block 6": r"D:\Mojtaba\Renardet\2224 WS11\HMS\B6\60 HMS_Block_6_Mod1\HMS_Block_6_Mod1.hms",
    "Majlas": r"D:\Mojtaba\Renardet\2224 WS11\Majlas\Hydrology\HEC_HMS_Majlas\HEC_HMS_Majlas.hms",
}
RESERVED_CORES = 2


def run_one(job: tuple[str, str]) -> dict:
    """One analysis of one project, as plain data."""
    project, analysis = job
    result = replicate(project, [analysis])
    return {
        "analysis": analysis,
        "rows": [asdict(row) for row in result.comparisons],
        "left_out": result.left_out,
        "lacking": result.points_without_results,
    }


def run_project(project: str, pool: ProcessPoolExecutor) -> dict:
    """Every analysis of a project."""
    names = [analysis.name for analysis in load_nals(Path(project).with_suffix(".nals")).analyses]
    collected = {"rows": [], "left_out": {}, "lacking": {}}
    for part in pool.map(run_one, [(project, name) for name in names]):
        collected["rows"] += part["rows"]
        collected["left_out"] |= part["left_out"]
        collected["lacking"] |= part["lacking"]
    return collected


def report(label: str, collected: dict) -> None:
    """The summary of one project."""
    rows = [Comparison(**row) for row in collected["rows"]]
    print(f"== {label}: {len({r.analysis for r in rows})} analyses, {len(rows)} point-peaks")
    if rows:
        worst = max(rows, key=lambda r: abs(r.error_percent))
        beyond = [sum(abs(r.error_percent) > limit for r in rows) for limit in (1.0, 2.0)]
        print(f"   worst {worst.error_percent:+.3f}% at {worst.point} in {worst.analysis}")
        print(f"   beyond 1%: {beyond[0]}, beyond 2%: {beyond[1]}")
    print(f"   left out: {collected['left_out']}")
    print(f"   points without results: { {k: len(v) for k, v in collected['lacking'].items()} }")


def main() -> None:
    """Run the projects named on the command line, or all of them."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("projects", nargs="*", default=list(PROJECTS), help="labels of PROJECTS")
    parser.add_argument("--json", type=Path, help="save every comparison here")
    args = parser.parse_args()
    collected = {}
    with ProcessPoolExecutor(max(1, (os.cpu_count() or 2) - RESERVED_CORES)) as pool:
        for label in args.projects:
            if not Path(PROJECTS[label]).exists():
                print(f"== {label}: missing")
                continue
            collected[label] = run_project(PROJECTS[label], pool)
            report(label, collected[label])
            sys.stdout.flush()
    if args.json is not None:
        args.json.write_text(json.dumps(collected), encoding="utf-8")


if __name__ == "__main__":
    main()
