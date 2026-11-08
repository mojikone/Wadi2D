"""Where on Faydh 01 the aligned cells' excess arises (W46, 2026-11-08): the centre mesh on the main stem alone, on
the tributaries alone, and on every stem, against no lines, all at 20 m on the GPU, read on the dam axis and on
lines across the main stem 5, 10 and 15 km from its head and across two tributaries at mid-length.

The race's own hydrographs say the centre mesh routes the flood faster than the squares (centroid 5.5 min earlier,
rising limb 7 to 14 % higher, recession 8 to 16 % lower, the same rain), and the synthetic valley shows nothing of
it, so the question is whether the speed comes from the channel cells on real ground or from the delivery of the
hills' water through the tributary strips and the band.

    .venv\\Scripts\\python "W46 centre-based mesh generator\\faydh_split.py" [build|run|report|all] [none all main tribs ...]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import shapely

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "W45 aligned mesh engine"))
from race_faydh import W26, base, run  # noqa: E402

from wadi2d.strips.banks import read_thalwegs  # noqa: E402
from wadi2d.strips.centres import chain_streams  # noqa: E402

WORK = Path(__file__).resolve().parent / "race_faydh" / "split"
CRS = "EPSG:32640"
SETS = {"all": None, "main": lambda k: k == 0, "tribs": lambda k: k > 0}
HALF_M = 200.0
NEAR_M = 150.0
"""Rain 'near' falls within this distance of the main stem (its pair, rows and band), 'hills' beyond it."""


def stems():
    return chain_streams(read_thalwegs(W26))


def write_stems(path: Path, keep) -> int:
    """A thalweg file holding the chained stems that ``keep`` admits by index, as the generator reads them."""
    import fiona
    from shapely.geometry import mapping

    path.unlink(missing_ok=True)
    n = 0
    with fiona.open(path, "w", driver="GPKG", layer="thalwegs", crs=CRS,
                    schema={"geometry": "LineString", "properties": {"area_km2": "float", "incised_m": "float"}}) as dst:
        for k, s in enumerate(stems()):
            if keep is None or keep(k):
                dst.write({"geometry": mapping(s["line"]), "properties": {"area_km2": float(s["area_km2"]), "incised_m": 0.0}})
                n += 1
    with fiona.open(path, "w", driver="GPKG", layer="breaklines", crs=CRS,
                    schema={"geometry": "LineString", "properties": {"kind": "str", "side": "str", "area_km2": "float"}}):
        pass
    return n


def across(line: shapely.LineString, s: float) -> list[list[float]]:
    """A line of 2 x HALF_M across ``line`` at arc length s."""
    p = np.asarray(line.interpolate(s).coords)[0]
    a = np.asarray(line.interpolate(max(s - 50.0, 0.0)).coords)[0]
    b = np.asarray(line.interpolate(min(s + 50.0, line.length)).coords)[0]
    t = (b - a) / max(np.hypot(*(b - a)), 1e-9)
    n = np.array([-t[1], t[0]])
    return [list(map(float, p - HALF_M * n)), list(map(float, p + HALF_M * n))]


def extra_lines() -> list[dict]:
    st = stems()
    main = st[0]["line"]
    out = [{"name": f"m{int(km):02d}", "coordinates": across(main, km * 1000.0)} for km in (5, 10, 15)]
    for k in (3, 6):
        out.append({"name": f"t{k}mid", "coordinates": across(st[k]["line"], 0.5 * st[k]["line"].length)})
    return out


def depth_grid(where: str, depth_mm: float) -> Path:
    """The storm's depth as a raster at 10 m over the race domain: the full depth within NEAR_M of the main stem
    ('near') or beyond it ('hills'), nothing elsewhere. The run reads it at every cell, strip cells by position, so
    both meshes get the same water."""
    import rasterio
    import shapely
    from rasterio.transform import from_origin

    path = WORK / f"depth_{where}.tif"
    if path.is_file():
        return path
    domain = json.loads(Path(base(WORK, "gpu")["grid"]["domain"]).read_text(encoding="utf-8"))
    xmin, ymin, xmax, ymax = shapely.geometry.shape(domain["features"][0]["geometry"]).bounds
    step = 10.0
    xmin, ymin = np.floor(xmin / step) * step - step, np.floor(ymin / step) * step - step
    ncols, nrows = int(np.ceil((xmax - xmin) / step)) + 2, int(np.ceil((ymax - ymin) / step)) + 2
    top = ymin + nrows * step
    x = xmin + (np.arange(ncols) + 0.5) * step
    y = top - (np.arange(nrows) + 0.5) * step
    px, py = np.meshgrid(x, y)
    main = stems()[0]["line"]
    d = shapely.distance(main, shapely.points(np.column_stack((px.ravel(), py.ravel())))).reshape(px.shape)
    near = d <= NEAR_M
    z = np.where(near if where == "near" else ~near, depth_mm, 0.0).astype(np.float32)
    with rasterio.open(path, "w", driver="GTiff", height=nrows, width=ncols, count=1, dtype="float32", crs=CRS, nodata=-9999.0,
                       transform=from_origin(xmin, top, step, step)) as dst:
        dst.write(z, 1)
    return path


def split_name(name: str) -> tuple[str, str | None]:
    """'main_near' -> ('main', 'near'); 'main10' -> ('main', None); 'main' -> ('main', None)."""
    for where in ("near", "hills", "flood"):
        if name.endswith("_" + where):
            return name[: -len(where) - 1].rstrip("0123456789"), where
    return name.rstrip("0123456789"), None


FLOOD_AT_M = 2_000.0
FLOOD_TIMES_S = [0.0, 1_800.0, 3_000.0, 5_400.0, 21_600.0]
FLOOD_M3S = [20.0, 20.0, 300.0, 20.0, 20.0]
"""The 'flood' forcing: no rain, a flash flood entering the main stem 2 km below its head, 20 min up and 40 min down,
so the strip's routing of a wave on real ground is read apart from the lateral entry of the hills' water."""


def dx_of(name: str) -> float:
    """A trailing number on a run name is its cell size, m; none means the race's 20 m."""
    stem = name.split("_")[0]
    digits = stem[len(stem.rstrip("0123456789")) :]
    return float(digits) if digits else 20.0


def build(names: list[str]) -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    lines = extra_lines()
    for name in names:
        stem_set, where = split_name(name)
        dx = dx_of(name)
        job = base(WORK, "gpu")
        job["grid"]["dx"] = dx
        job["grid"]["cache_dir"] = str(WORK / "cache")
        job["outputs"]["lines"] = job["outputs"]["lines"] + lines
        if where in ("near", "hills"):
            job["storm"]["depth_grid"] = str(depth_grid(where, job["storm"]["depth_mm"]))
        elif where == "flood":
            p = np.asarray(stems()[0]["line"].interpolate(FLOOD_AT_M).coords)[0]
            job["storm"] = {"kind": "none"}
            job["hydrology"] = {"inflows": [{"name": "head", "x": float(p[0]), "y": float(p[1]), "times_s": FLOOD_TIMES_S, "flows": FLOOD_M3S}], "inject_radius": 60.0}
            job["run"]["duration_s"] = FLOOD_TIMES_S[-1]
        if stem_set != "none":
            gpkg = WORK / f"thalwegs_{stem_set}.gpkg"
            n = write_stems(gpkg, SETS[stem_set])
            job["strips"] = {"enabled": True, "generator": "centres", "banks": str(gpkg), "along": dx}
            print(f"{name}: {n} stems")
        (WORK / f"{name}.json").write_text(json.dumps(job, indent=1), encoding="utf-8")
    print("jobs written:", ", ".join(names))


def series(folder: Path, line: str) -> tuple[np.ndarray, np.ndarray]:
    rows = (folder / "series" / f"line_{line}.csv").read_text(encoding="utf-8").splitlines()[1:]
    a = np.array([[float(v) for v in r.split(",")[:2]] for r in rows])
    return a[:, 0], np.abs(a[:, 1])


def report(names: list[str]) -> None:
    lines = ["axis", "m05", "m10", "m15", "t3mid", "t6mid"]
    out: dict = {}
    for name in names:
        folder = WORK / name
        if not (folder / "progress.jsonl").is_file():
            print(f"{name}: no run")
            continue
        prog = (folder / "progress.jsonl").read_text(encoding="utf-8").splitlines()
        done = [json.loads(s) for s in prog if '"done"' in s[:14]][-1]
        built = [json.loads(s) for s in prog if '"ev": "strips"' in s]
        r = {"steps": done["steps"], "loop_s": done["loop_s"], "storage_end_Mm3": done["balance"]["storage_end_m3"] / 1e6}
        if built:
            r["strip_cells"] = built[-1]["cells"]
        for line in lines:
            t, q = series(folder, line)
            dt = float(np.median(np.diff(t)))
            r[line] = {"peak": float(q.max()), "at_h": float(t[q.argmax()] / 3600), "centroid_h": float((q * t).sum() / max(q.sum(), 1e-9) / 3600), "vol_Mm3": float(q.sum() * dt / 1e6)}
        out[name] = r
    print("\nFaydh 01 at 20 m: peak m3/s (centroid h) per line; in brackets the peak against no lines with the same rain")
    print(f"{'run':11s} " + " ".join(f"{line:>22s}" for line in lines) + "   strip cells  stored at end Mm3")
    for name, r in out.items():
        stem_set, where = split_name(name)
        ref = out.get("none" + (f"_{where}" if where else ""))  # the 20 m squares with the same rain, whatever the run's own size
        cells = []
        for line in lines:
            p = r[line]["peak"]
            ratio = f"{100 * (p / ref[line]['peak'] - 1):+.1f}%" if ref and stem_set != "none" and ref[line]["peak"] > 1.0 else ""
            cells.append(f"{p:7.1f} ({r[line]['centroid_h']:6.3f}) {ratio:>6s}")
        print(f"{name:11s} " + " ".join(cells) + f"   {r.get('strip_cells', '-'):>6}  {r['storage_end_Mm3']:.4f}")
    tag = "_".join(sorted({split_name(n)[1] or "all" for n in out}))
    (WORK / f"split_{tag}.json").write_text(json.dumps(out, indent=1), encoding="utf-8")


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    sizes = ("", "10", "5")
    valid = [f"{s}{d}{w}" for s in ("none", *SETS) for d in sizes for w in ("", "_near", "_hills", "_flood")]
    names = [a for a in sys.argv[2:] if a in valid] or ["none", *SETS]
    if what in ("build", "all"):
        build(names)
    if what in ("run", "all"):
        for name in names:
            run(WORK, name)
    if what in ("report", "all"):
        report(names)
