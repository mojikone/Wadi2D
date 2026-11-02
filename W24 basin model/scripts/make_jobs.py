"""The Block 2 jobs of this iteration. Reads Block 2, writes `W24 basin model/jobs`.

`block2` has the five axes of the whole-catchment validation as crest lines, so each collects the wadis it crosses, as the
wall layers of the HMS model do. Their levels are only the highest ground on each axis: this job measures areas and flows, and
none of the five has a spillway here, so each passes as a junction. `block2_lines` has the same axes as design lines.
The `dam_` jobs are the two designed dams on the NSA terrain, whose datum their levels are on.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import rasterio
import shapely

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parent
FULL = ROOT / "W1 research and design note" / "validation" / "block2_full"
HYDROLOGY = Path(r"D:\Mojtaba\Renardet\2224 WS11\Batinah\Block 2\Hydrology")
GGC_5M = HYDROLOGY / "Terrain" / "GGC_2_MERGE_HDSM_5.tif"
NSA_5M = HYDROLOGY / "Terrain" / "NSA_Batinah_5m.tif"
CN = HYDROLOGY / "HEC_HMS_Block_02" / "Hydrology Data" / "CN_Include_Hill_Area.tif"
PIXEL = 5.0
HMS_REACH_N = 0.1
"""HMS's own value on all eight reaches, used unchanged; see the README."""
DAMS = ("Bidah 03", "Faydh 01", "R5A", "R2A", "Z4C")
RELATIVE_FULL = Path("..") / ".." / FULL.relative_to(ROOT)


def dam_lines() -> list[dict]:
    """The five dam axes of the whole-catchment validation, as design lines."""
    job = json.loads((FULL / "jobs" / "c20_A74_h100.json").read_text(encoding="utf-8"))
    return [line for line in job["outputs"]["lines"] if line["name"] in DAMS]


def highest_ground(coordinates: list[list[float]]) -> float:
    """The highest ground along an axis on the job's DEM."""
    line = shapely.LineString(coordinates)
    points = [line.interpolate(d) for d in np.arange(0.0, line.length, PIXEL)]
    with rasterio.open(GGC_5M) as src:
        return float(max(v[0] for v in src.sample([(p.x, p.y) for p in points])))


def axes_as_crests(lines: list[dict]) -> list[dict]:
    """Every axis as a crest line at its highest ground."""
    return [
        {
            "kind": "crest_line",
            "name": line["name"],
            "coordinates": line["coordinates"],
            "z_constant": highest_ground(line["coordinates"]),
        }
        for line in lines
    ]


def job(
    name: str, dem: Path, domain: str, lines: list[dict] | None = None, objects: list | None = None
) -> None:
    body = {
        "project": {"name": name, "description": "W24 basin model"},
        "grid": {"dx": PIXEL, "domain": str(RELATIVE_FULL / domain)},
        "mesh": {"analysis_pixel": PIXEL},
        "terrain": {"dem": str(dem), "cn_raster": str(CN), "manning": HMS_REACH_N, "objects": objects or []},
        "outputs": {"lines": lines or []},
    }
    (HERE / "jobs" / f"{name}.json").write_text(json.dumps(body, indent=1), encoding="utf-8")


def dam_objects(name: str) -> list:
    """Crest lines and spillway of a dam as the whole-catchment validation had them; levels on the NSA datum."""
    data = json.loads((FULL / "jobs" / f"dam_{name}_100yr_10.json").read_text(encoding="utf-8"))
    return data["terrain"]["objects"]


def main() -> None:
    lines = dam_lines()
    job("block2", GGC_5M, "domain.geojson", None, axes_as_crests(lines))
    job("block2_lines", GGC_5M, "domain.geojson", lines)
    for name in ("Faydh01", "Bidah03"):
        job(f"dam_{name}", NSA_5M, f"domain_{name}.geojson", None, dam_objects(name))


if __name__ == "__main__":
    main()
