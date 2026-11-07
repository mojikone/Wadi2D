"""Shared inputs of the W44 MeshKernel mesh race on the Faydh 01 gorge: paths, the domain polygon, the bank lines.

Everything here is read-only against the project; the outputs go beside these scripts.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import numpy as np
import shapely
from shapely.geometry import shape

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]  # D:\Mojtaba\Renardet\Wadi2D
W26 = ROOT / "W26 suggested breaklines" / "suggested" / "faydh" / "suggested_breaklines.gpkg"
W11 = ROOT / "W11 validation round two" / "t2_faydh"
DOMAIN_20M = W11 / "domain_wadi_20m.geojson"
JOB = W11 / "jobs" / "10m_n050_em.json"
DEM_5M = Path(r"D:\Mojtaba\Renardet\2224 WS11\Batinah\Block 2\Hydrology\Terrain\GGC_2_MERGE_HDSM_5.tif")
DX = 20.0


def domain() -> shapely.Polygon:
    data = json.load(open(DOMAIN_20M))
    return shape(data["features"][0]["geometry"])


def dam_axis() -> shapely.LineString:
    """The dam line of the Faydh 01 case: the `axis` result line of the W11 job."""
    job = json.load(open(JOB))
    for line in job["outputs"]["lines"]:
        if line["name"] == "axis":
            return shapely.LineString(line["coordinates"])
    raise KeyError("axis")


def bank_lines() -> list[dict]:
    """W26's stream-bank lines of Faydh 01 with their fields; geometry as 2D LineStrings (one part each)."""
    db = sqlite3.connect(W26)
    out = []
    for fid, name, side, area, length, height, blob in db.execute(
        "SELECT fid, name, side, area_km2, length_m, height_m, geom FROM breaklines WHERE kind='stream bank'"
    ):
        geom = shapely.from_wkb(blob[40:])
        parts = list(geom.geoms) if hasattr(geom, "geoms") else [geom]
        for part in parts:
            xy = np.asarray(part.coords)[:, :2]
            out.append(
                {
                    "fid": fid,
                    "name": name,
                    "side": side,
                    "area_km2": area,
                    "length_m": length,
                    "height_m": height,
                    "line": shapely.LineString(xy),
                }
            )
    db.close()
    return out


def thalwegs() -> list[dict]:
    db = sqlite3.connect(W26)
    out = []
    for fid, area, incised, length, blob in db.execute("SELECT fid, area_km2, incised_m, length_m, geom FROM thalwegs"):
        geom = shapely.from_wkb(blob[40:])
        parts = list(geom.geoms) if hasattr(geom, "geoms") else [geom]
        for part in parts:
            xy = np.asarray(part.coords)[:, :2]
            out.append({"fid": fid, "area_km2": area, "incised_m": incised, "length_m": length, "line": shapely.LineString(xy)})
    db.close()
    return out
