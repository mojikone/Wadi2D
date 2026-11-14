"""Lines after a depth-area study on Bidah 03 at 30 m: a flow-accumulation raster, a study on the RP100 NetCDF grid with
ARF FM, a line drawn across a tributary read through the study, and the wait for one request against a single run's.

usage: study_lines_bidah.py OUT_ROOT RESULT.json      (venv python, PYTHONPATH on this checkout)

OUT_ROOT takes the raster, the study and the line answers; it must lie outside the owner's folders.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import rasterio
import shapely
from rasterio.transform import Affine

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from run_engine import BLOCK, VALIDATION, engine, hms_import, make_job  # noqa: E402

from wadi2d.mesh.streams import drainage_area, read_coarse  # noqa: E402
from wadi2d.terrain.vector import read_features  # noqa: E402

PIXEL = 30.0
FACTOR = 6
"""5 m DEM pixels averaged to the 30 m accumulation pixel."""
AREAS = [5.0, 10.0, 20.971, 40.0]
TRIBUTARY_KM2 = (8.0, 14.0)
"""A tributary to draw a line across: between these drainage areas, away from the domain's edge."""
REPEAT = 3


def accumulation(root: Path) -> Path:
    """D8 catchment area, km2, on 30 m pixels over the Bidah 03 domain, through breached depressions."""
    out = root / "accumulation_km2.tif"
    if out.is_file():
        return out
    domain = shapely.union_all([s for _p, s in read_features(VALIDATION / "domain_Bidah03.geojson", "EPSG:32640")])
    west, south, east, north = domain.bounds
    x0, y0 = np.floor(west / PIXEL) * PIXEL - PIXEL, np.ceil(north / PIXEL) * PIXEL + PIXEL
    nx, ny = int(np.ceil((east - x0) / PIXEL)) + 1, int(np.ceil((y0 - south) / PIXEL)) + 1
    z = read_coarse(BLOCK / "Terrain" / "GGC_2_MERGE_HDSM_5.tif", x0, y0, ny, nx, PIXEL, 1)
    area = drainage_area(z, PIXEL, x0, y0, "EPSG:32640") / 1e6
    with rasterio.open(out, "w", driver="GTiff", height=ny, width=nx, count=1, dtype="float32", nodata=-1.0,
                       crs="EPSG:32640", transform=Affine(PIXEL, 0.0, x0, 0.0, -PIXEL, y0)) as dst:  # fmt: skip
        dst.write(area.astype(np.float32), 1)
    return out


def tributary_line(raster: Path, domain) -> list:
    """A 300 m line square to the flow across a pixel draining 8 to 14 km2, well inside the domain."""
    with rasterio.open(raster) as src:
        a = src.read(1)
        t = src.transform
    rows, columns = np.nonzero((a > TRIBUTARY_KM2[0]) & (a < TRIBUTARY_KM2[1]))
    inner = domain.buffer(-1000.0)
    for r, c in zip(rows, columns, strict=True):
        x, y = t * (c + 0.5, r + 0.5)
        if not inner.contains(shapely.Point(x, y)):
            continue
        window = a[max(r - 2, 0) : r + 3, max(c - 2, 0) : c + 3]
        dr, dc = np.unravel_index(np.argmax(np.where(window < a[r, c], window, -1)), window.shape)
        down = np.array([dc - min(c, 2), -(dr - min(r, 2))], float)  # the upstream neighbour's way, east and north
        if not np.any(down):
            continue
        across = np.array([-down[1], down[0]]) / np.hypot(*down) * 150.0
        return [[x - across[0], y - across[1]], [x + across[0], y + across[1]]]
    raise RuntimeError("no tributary pixel of 8 to 14 km2 inside the domain")


def timed(code: Path, args: list[str]) -> float:
    t0 = time.monotonic()
    done = engine(code, *args)
    if done.returncode:
        raise RuntimeError(done.stderr[-2000:])
    return time.monotonic() - t0


def main() -> None:
    root, target = Path(sys.argv[1]).resolve(), Path(sys.argv[2])
    root.mkdir(parents=True, exist_ok=True)
    code = HERE.parent
    raster = accumulation(root)
    domain = shapely.union_all([s for _p, s in read_features(VALIDATION / "domain_Bidah03.geojson", "EPSG:32640")])
    imported = hms_import(code, root)
    job = make_job(code, root, {"name": "study_lines", "storm": "RP100", "fmt": "nc", "mode": "full", "area": 20.971})
    job["storm"]["arf"] = imported["storm"]["arf"]
    job["arf"] = {"areas_km2": AREAS, "accumulation": str(raster), "accumulation_units": "km2"}
    job["outputs"]["lines"][0]["drainage_area_km2"] = 20.971
    study = root / "study"
    if not (study / "study.json").is_file():
        (root / "job.json").write_text(json.dumps(job, indent=1), encoding="utf-8")
        t0 = time.monotonic()
        done = engine(code, "arf", str(root / "job.json"), "--out", str(study), "--backend", "gpu")
        if done.returncode:
            raise RuntimeError(done.stderr[-3000:])
        study_s = time.monotonic() - t0
    else:
        study_s = None
    line = tributary_line(raster, domain)
    design = job["outputs"]["lines"][0]["coordinates"]
    found = {"raster": str(raster), "study_s": study_s, "areas_km2": AREAS, "line": line, "requests": {}}
    for key, coordinates in (("tributary", line), ("on Bidah 03", design)):
        request = root / f"{key.replace(' ', '_')}.json"
        request.write_text(json.dumps({"name": key, "coordinates": coordinates}), encoding="utf-8")
        answer = root / f"{key.replace(' ', '_')}_answer.json"
        single = root / f"{key.replace(' ', '_')}_single.json"
        one_run = study / "runs" / sorted(p.name for p in (study / "runs").iterdir())[0]
        waits = [timed(code, ["lines", str(study), "--line", str(request), "--out", str(answer)]) for _ in range(REPEAT)]
        alone = [timed(code, ["lines", str(one_run), "--line", str(request), "--out", str(single)]) for _ in range(REPEAT)]
        read = json.loads(answer.read_text(encoding="utf-8"))
        found["requests"][key] = {
            "study_request_s": waits, "single_run_request_s": alone, "study": read["study"],
            "peak_blended_series_m3s": max(abs(q) for q in read["flow_m3s"]),
        }  # fmt: skip
        print(key, read["study"]["words"], f"study {np.median(waits):.2f} s, one run {np.median(alone):.2f} s", flush=True)
    rows = json.loads((study / "study.json").read_text(encoding="utf-8"))["table"]
    found["study_table"] = rows
    target.write_text(json.dumps(found, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
