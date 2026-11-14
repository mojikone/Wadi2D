"""Block 2's products remade end to end and timed stage by stage (W50, 2026-11-13), after `profile_products.py`.

The source run is W49's Block 2 at 20 m with the local radius (2.03 M cells, 7 maps with the run's peak). Its
`config.resolved.json` and `results.h5` are copied into `remake/runs/<tag>/` (not in git: 2 to 7 GB a run), the copy's `grid.cache_dir` is pointed at
`remake/cache` (the source's points into another checkout) and `outputs.smooth.enabled` is set as asked; then the
engine's own `remake` runs, every progress event stamped with the wall clock. No profiler: cProfile counts threads
twice and slows the step.

    python "W50 products speed and time slider maps\time_products.py" TAG on|off [--src ENGINE_ROOT] [--command products|drawings]

`--src` runs another copy of the engine (the commit the work started from, exported with `git archive`), so "before"
and "after" are measured the same way. `--command drawings` runs the on-demand step on a run that already holds its
rasters. Writes `remake/stages_<tag>.json`; the ones quoted in the README are copied to `timings/`.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent / "remake"
ROOT = HERE.parent.parent
MAIN = Path(r"D:\Mojtaba\Renardet\Wadi2D")
SOURCE = MAIN / "W49 local hydraulic radius face table" / "validation_reruns" / "block2_b20_local_radius"
RUNS = HERE / "runs"
CACHE = HERE / "cache"


def prepare(run: Path, smooth: bool) -> None:
    run.mkdir(parents=True, exist_ok=True)
    for name in ("config.resolved.json", "results.h5"):
        if not (run / name).is_file():
            shutil.copy2(SOURCE / name, run / name)
    path = run / "config.resolved.json"
    cfg = json.loads(path.read_text(encoding="utf-8"))
    cfg["grid"]["cache_dir"] = str(CACHE)
    cfg["outputs"]["smooth"]["enabled"] = smooth
    path.write_text(json.dumps(cfg), encoding="utf-8")


def stage_of(ev: str, fields: dict) -> str:
    if ev == "products":
        stage = fields.get("stage", "")
        if stage == "smooth" and fields.get("of"):
            return "drawing" if fields["done"] >= fields["of"] / 2 else "polygons"
        return stage
    if ev == "output":
        return str(fields.get("kind"))
    return ev


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("tag")
    ap.add_argument("smooth", choices=("on", "off"))
    ap.add_argument("--src", default=str(ROOT))
    ap.add_argument("--command", choices=("products", "drawings"), default="products")
    args = ap.parse_args()
    sys.path.insert(0, args.src)
    import wadi2d
    from wadi2d.io import progress as progress_mod

    assert Path(wadi2d.__file__).resolve().is_relative_to(Path(args.src).resolve()), wadi2d.__file__
    run = RUNS / args.tag
    prepare(run, args.smooth == "on")
    stamps: list[tuple[float, str, dict]] = []
    emit = progress_mod.Progress.emit

    def stamped(self, ev, **fields):
        stamps.append((time.perf_counter(), ev, fields))
        return emit(self, ev, **fields)

    progress_mod.Progress.emit = stamped
    t0 = time.perf_counter()
    if args.command == "products":
        from wadi2d.products.runner import remake

        code = remake(run, None, False)
    else:
        from wadi2d.products.runner import draw

        code = draw(run, None, False)
    total = time.perf_counter() - t0
    starts: list[tuple[str, float]] = []
    for t, ev, fields in stamps:
        key = stage_of(ev, fields)
        if not starts or starts[-1][0] != key:
            starts.append((key, t - t0))
    rows = []
    for (key, a), (_next, b) in zip(starts, [*starts[1:], ("end", total)], strict=True):
        rows.append({"stage": key, "from_s": round(a, 1), "seconds": round(b - a, 1)})
    lead = starts[0][1] if starts else total
    out = {"tag": args.tag, "smooth": args.smooth, "src": args.src, "command": args.command, "code": code,
           "total_s": round(total, 1), "before_first_event_s": round(lead, 1), "stages": rows}  # fmt: skip
    (HERE / f"stages_{args.tag}.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"{args.tag}: total {total:.1f} s, exit {code}; {lead:.1f} s before the first event")
    for r in rows:
        print(f"  {r['stage']:18s} from {r['from_s']:8.1f} s  {r['seconds']:8.1f} s")
    return code


if __name__ == "__main__":
    sys.exit(main())
