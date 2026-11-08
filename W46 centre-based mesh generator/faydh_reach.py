"""Who is right on Faydh's own channel: an 8 km reach of the main stem (4 to 12 km from its head) under a flash flood
with no rain, squares at 20, 10, 5 and 2 m against the centre mesh at 20 and 10 m (W46, 2026-11-08).

The split runs showed the main stem's strip routing a flood with 4 to 7 % less attenuation than the squares along the
stem, the same at 20 and 10 m, where on a smooth synthetic channel the two agree to a tenth of a per cent. Faydh's
gorge channel is 5 to 15 m wide, one to three cells at 5 m, where W3 measured the staircase's own error at +3.5 to
+8 % of depth on an oblique channel: the 5 m squares may not be the converged answer. Here the squares go to 2 m on a
small domain, 250 m either side of the stem, so both constructions can be read against a reference the staircase no
longer biases.

    .venv\\Scripts\\python "W46 centre-based mesh generator\\faydh_reach.py" [build|run|report|all] [sq20 ce20 sq10 ce10 sq5 sq2 ...]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import shapely
from shapely.ops import substring

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "W45 aligned mesh engine"))
from race_faydh import W26, base, run  # noqa: E402

from wadi2d.strips.banks import read_thalwegs  # noqa: E402
from wadi2d.strips.centres import chain_streams  # noqa: E402

LONG = "--long" in sys.argv
"""The long reach runs to 20 km, where the split runs read the strip's deficit of attenuation at its largest."""
STEADY = "--steady" in sys.argv
"""A constant 300 m3/s for 6 h in place of the flash flood: the water each construction stores along the reach at the
same discharge, and the level profile along the thalweg, say whether the strip conveys the real channel more easily."""
WORK = Path(__file__).resolve().parent / "race_faydh" / (("reach_long" if LONG else "reach") + ("_steady_ramp" if STEADY else ""))
CRS = "EPSG:32640"
REACH = (4_000.0, 20_000.0 if LONG else 12_000.0)
DOMAIN = (3_500.0, REACH[1] + 650.0)
HALF_DOMAIN_M = 250.0
STRIP_FROM_M = 300.0
"""The strip starts this far below the inflow, so the injection lands on squares in every run."""
LINES_KM = (6, 10, 14, 18) if LONG else (6, 8, 10, 12)
LINE_OFFSETS_M = {"a": -100.0, "b": 0.0, "c": 100.0}
"""Three lines per kilometre mark, 100 m apart, read as their median. A line across the strip that falls between two
station faces at a bend read half the flow in the first run (k08 and k12 at 20 m, -55 and -45 %), and a line across
20 m squares read 15 % high at one mark where the two beside it read 5 and 3 % high; the 2 m squares' three agree to
1 %. The readers' faults on coarse cells are on record, not fixed."""
HALF_LINE_M = 220.0
OUTFLOW_AT = REACH[1] + 600.0
TIMES_S = [0.0, 3_600.0, 21_600.0] if STEADY else [0.0, 1_800.0, 3_000.0, 5_400.0, 21_600.0 if LONG else 14_400.0]
FLOWS = [0.0, 300.0, 300.0] if STEADY else [20.0, 20.0, 300.0, 20.0, 20.0]
"""The steady inflow ramps up over an hour: the first steady runs (reach_long_steady) started at 300 m3/s into a dry
channel and their maximum-level rasters carried the arrival bore, which is not the steady surface."""
MESHES = {"sq20": (20.0, False), "ce20": (20.0, True), "sq10": (10.0, False), "ce10": (10.0, True), "sq5": (5.0, False), "sq2": (2.0, False),
          "ce10s1": (10.0, True), "ce10s15": (10.0, True), "ce20s1": (20.0, True), "ce20s15": (20.0, True)}
SMOOTH = {"ce10s1": 1, "ce10s15": 15, "ce20s1": 1, "ce20s15": 15}
MESHES |= {"sq10first": (10.0, False), "sq5first": (5.0, False), "sq20first": (20.0, False), "ce5": (5.0, True)}
FIRST_ORDER = {"sq10first", "sq5first", "sq20first"}
"""Squares with numerics.limiter 'none', which makes the lattice's momentum advection first-order upwind as the
polygon kernel's always is: if the squares then under-attenuate the flood as the strip does, that is the mechanism."""
"""The strip with the guide line smoothed over 1 or 15 stations in place of the schema's 5: if the strip's excess
follows the misalignment of its station faces with the channel, it moves with the smoothing."""


def main_stem() -> shapely.LineString:
    return chain_streams(read_thalwegs(W26))[0]["line"]


def across(line: shapely.LineString, s: float, half: float) -> list[list[float]]:
    p = np.asarray(line.interpolate(s).coords)[0]
    a = np.asarray(line.interpolate(max(s - 50.0, 0.0)).coords)[0]
    b = np.asarray(line.interpolate(min(s + 50.0, line.length)).coords)[0]
    t = (b - a) / max(np.hypot(*(b - a)), 1e-9)
    n = np.array([-t[1], t[0]])
    return [list(map(float, p - half * n)), list(map(float, p + half * n))]


def ground() -> None:
    """The domain polygon and the thalweg file of the reach."""
    import fiona
    from shapely.geometry import mapping

    WORK.mkdir(parents=True, exist_ok=True)
    stem = main_stem()
    piece = substring(stem, *DOMAIN)
    domain = piece.buffer(HALF_DOMAIN_M, cap_style="flat")
    if domain.geom_type != "Polygon":
        domain = max(domain.geoms, key=lambda g: g.area)
    (WORK / "domain.geojson").write_text(json.dumps({
        "type": "FeatureCollection",
        "features": [{"type": "Feature", "properties": {"name": "faydh_reach"}, "geometry": mapping(domain)}],
    }), encoding="utf-8")
    strip = substring(stem, REACH[0] + STRIP_FROM_M, DOMAIN[1])
    gpkg = WORK / "thalweg_reach.gpkg"
    gpkg.unlink(missing_ok=True)
    with fiona.open(gpkg, "w", driver="GPKG", layer="thalwegs", crs=CRS,
                    schema={"geometry": "LineString", "properties": {"area_km2": "float", "incised_m": "float"}}) as dst:
        dst.write({"geometry": mapping(strip), "properties": {"area_km2": 74.0, "incised_m": 0.0}})
    with fiona.open(gpkg, "w", driver="GPKG", layer="breaklines", crs=CRS,
                    schema={"geometry": "LineString", "properties": {"kind": "str", "side": "str", "area_km2": "float"}}):
        pass
    print(f"reach: domain {domain.area / 1e6:.2f} km2, strip line {strip.length / 1000:.2f} km")


def build(meshes: list[str]) -> None:
    ground()
    stem = main_stem()
    p = np.asarray(stem.interpolate(REACH[0]).coords)[0]
    for mesh in meshes:
        dx, centres = MESHES[mesh]
        job = base(WORK, "gpu")
        job["grid"] = {"dx": dx, "domain": str(WORK / "domain.geojson"), "cache_dir": str(WORK / "cache")}
        job["storm"] = {"kind": "none"}
        job["hydrology"] = {"inflows": [{"name": "head", "x": float(p[0]), "y": float(p[1]), "times_s": TIMES_S, "flows": FLOWS}], "inject_radius": 60.0}
        job["boundaries"] = [{"kind": "normal", "slope": 0.015, "coordinates": across(stem, OUTFLOW_AT, HALF_DOMAIN_M + 20.0)}]
        job["outputs"]["lines"] = [{"name": f"k{km:02d}{tag}", "coordinates": across(stem, km * 1000.0 + off, HALF_LINE_M)} for km in LINES_KM for tag, off in LINE_OFFSETS_M.items()]
        job["outputs"]["series_every_s"] = 30.0
        job["run"]["duration_s"] = TIMES_S[-1]
        job.pop("strips", None)
        if mesh in FIRST_ORDER:
            job["numerics"] = job.get("numerics", {}) | {"limiter": "none"}
        if centres:
            job["strips"] = {"enabled": True, "generator": "centres", "banks": str(WORK / "thalweg_reach.gpkg"), "along": dx}
            if mesh in SMOOTH:
                job["strips"]["smooth"] = SMOOTH[mesh]
        (WORK / f"{mesh}.json").write_text(json.dumps(job, indent=1), encoding="utf-8")
    print("jobs written:", ", ".join(meshes))


def series(folder: Path, line: str) -> tuple[np.ndarray, np.ndarray]:
    rows = (folder / "series" / f"line_{line}.csv").read_text(encoding="utf-8").splitlines()[1:]
    a = np.array([[float(v) for v in r.split(",")[:2]] for r in rows])
    return a[:, 0], np.abs(a[:, 1])


def report(meshes: list[str]) -> None:
    lines = [f"k{km:02d}" for km in LINES_KM]
    out: dict = {}
    for mesh in meshes:
        folder = WORK / mesh
        if not (folder / "progress.jsonl").is_file():
            print(f"{mesh}: no run")
            continue
        prog = (folder / "progress.jsonl").read_text(encoding="utf-8").splitlines()
        finished = [json.loads(s) for s in prog if '"done"' in s[:14]]
        if not finished:
            failed = [json.loads(s) for s in prog if '"ev": "error"' in s]
            print(f"{mesh}: no finished run" + (f": {failed[-1]['message']}" if failed else ""))
            continue
        done = finished[-1]
        built = [json.loads(s) for s in prog if '"ev": "strips"' in s]
        r = {"dx": MESHES[mesh][0], "steps": done["steps"], "loop_s": done["loop_s"], "mass_error": done["balance"]["relative_error"],
             "storage_end_m3": done["balance"]["storage_end_m3"], "outflow_m3": done["balance"]["outflow_m3"]}
        if built:
            r["strip_cells"] = built[-1]["cells"]
        for line in lines:
            three = []
            for tag in LINE_OFFSETS_M:
                t, q = series(folder, line + tag)
                three.append({"peak": float(q.max()), "at_h": float(t[q.argmax()] / 3600), "centroid_h": float((q * t).sum() / max(q.sum(), 1e-9) / 3600), "line": line + tag})
            # the median of the three: on 20 m cells a single line reads up to 15 % high or 55 % low (the 2 m squares'
            # three agree to 1 %), so neither the largest nor one line alone is the reach's number
            r[line] = sorted(three, key=lambda one: one["peak"])[1] | {"three": [one["peak"] for one in three]}
        out[mesh] = r
    ref = out.get("sq2")
    print("\nFaydh main stem, 4 to 12 km, flash flood of 300 m3/s at 4 km, no rain: peak m3/s (centroid h) per line, against the 2 m squares")
    print(f"{'mesh':6s}" + "".join(f"{line:>26s}" for line in lines) + "   steps   GPU s")
    for mesh, r in out.items():
        cells = []
        for line in lines:
            p = r[line]["peak"]
            against = f"{100 * (p / ref[line]['peak'] - 1):+5.1f}%" if ref and mesh != "sq2" else "      "
            cells.append(f"{p:7.1f} ({r[line]['centroid_h']:5.3f}) {against}")
        print(f"{mesh:6s}" + "".join(f"{c:>26s}" for c in cells) + f"  {r['steps']:7d}  {r['loop_s']:6.0f}  stored {r['storage_end_m3'] / 1e3:7.1f} km3e-3" + (f"  strip cells {r['strip_cells']}" if "strip_cells" in r else ""))
    (WORK / "reach.json").write_text(json.dumps(out, indent=1), encoding="utf-8")


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    meshes = [a for a in sys.argv[2:] if a in MESHES] or list(MESHES)  # --long is read at import
    if what in ("build", "all"):
        build(meshes)
    if what in ("run", "all"):
        for mesh in meshes:
            run(WORK, mesh)
    if what in ("report", "all"):
        report(meshes)
