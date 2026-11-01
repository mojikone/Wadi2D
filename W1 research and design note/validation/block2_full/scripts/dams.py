"""The two dams as terrain objects, their local domains, the level-pool routing, the volume check.

Geometry from Dams.shp and Dikes.shp (polylines split where the file jumps), levels from Block 2 Dams Details.xlsx.
The spillway position is not in the data: it is drawn centred on the thalweg of the axis, an assumption.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import shapely
from shapely.geometry import mapping

sys.path.insert(0, r"D:\Mojtaba\Renardet\Wadi2D\W1 research and design note\validation\block2_full\scripts")
from common import BLOCK, CACHE, DAMS, OUT, polygons  # noqa: E402

EAV_DIR = DAMS.parent / "EAV"
NSA2 = BLOCK / "Terrain" / "NSA_Batinah_2m.tif"
GGC_MINUS_NSA = 2.39
"""GGC_2_MERGE_HDSM over NSA_Batinah in both reservoirs, m (dem_difference.json); the dam levels are on NSA."""
OVERTOP_C = 1.7


@dataclass
class Dam:
    name: str
    fsl: float
    crest: float
    c: float
    spill_len: float
    crest_lines: list[list[tuple[float, float]]]
    spillway: list[tuple[float, float]]
    subbasins: list[str]
    box: tuple[float, float, float, float]
    boundaries: list[dict]
    inject: tuple[float, float]
    axis_line: list[tuple[float, float]]
    tailwater_point: tuple[float, float]
    pool_point: tuple[float, float]
    upstream_side: tuple[float, float]

    def eav(self) -> np.ndarray:
        return np.loadtxt(EAV_DIR / f"{self.name} EAV.csv", delimiter=",", skiprows=1, encoding="utf-8")

    def volume_at(self, z: np.ndarray | float) -> np.ndarray:
        e = self.eav()
        return np.interp(z, e[:, 1], e[:, 2])


def _point_on(line: list[tuple[float, float]], s: float) -> tuple[float, float]:
    p = shapely.LineString(line).interpolate(s)
    return (p.x, p.y)


BIDAH_AXIS = [(438259.32, 2727264.77), (438807.68, 2726752.81)]
_s = shapely.LineString(BIDAH_AXIS).project(shapely.Point(438600.0, 2726950.0))
FAYDH_AXIS = [(431003.28, 2734233.93), (431235.24, 2733997.1), (431244.34, 2733873.98), (431019.77, 2733523.58),
              (431054.16, 2733225.76)]
_main = shapely.LineString(FAYDH_AXIS[3:])
_fs = _main.project(shapely.Point(431031.55, 2733421.52))

BIDAH = Dam(
    name="Bidah 03", fsl=100.0, crest=105.0, c=2.1, spill_len=72.0,
    crest_lines=[
        BIDAH_AXIS + [(438800.2, 2726723.6), (438804.0, 2726713.5), (438814.8, 2726694.0), (438828.7, 2726674.3),
                      (438854.3, 2726650.3), (438864.9, 2726625.5), (438859.8, 2726618.6), (438851.2, 2726603.5),
                      (438843.2, 2726583.8), (438837.1, 2726568.1), (438823.4, 2726554.4), (438804.7, 2726543.3),
                      (438734.6, 2726533.6)],
        [(437647.8, 2726911.9), (437562.8, 2726927.1)],
        [(438259.32, 2727264.77), (438147.3, 2727215.7), (438114.4, 2727197.5), (438029.0, 2727157.6),
         (438004.2, 2727143.4), (437921.6, 2727135.2)],
    ],
    spillway=[_point_on(BIDAH_AXIS, _s - 36.0), _point_on(BIDAH_AXIS, _s + 36.0)],
    subbasins=["S13"],
    box=(437300.0, 2725700.0, 440300.0, 2728700.0),
    boundaries=[
        {"kind": "normal", "slope": 0.008, "coordinates": [(440290.0, 2725700.0), (440290.0, 2728700.0)]},
        {"kind": "normal", "slope": 0.008, "coordinates": [(437300.0, 2728690.0), (440300.0, 2728690.0)]},
    ],
    inject=(438130.0, 2726810.0),
    axis_line=BIDAH_AXIS,
    tailwater_point=(438700.0, 2727060.0),
    pool_point=(438300.0, 2726860.0),
    upstream_side=(438300.0, 2726860.0),
)
FAYDH = Dam(
    name="Faydh 01", fsl=230.0, crest=235.0, c=2.1, spill_len=207.0,
    crest_lines=[
        FAYDH_AXIS + [(431069.8, 2733186.8), (431061.7, 2733137.8)],
        [(430983.8, 2733612.6), (430983.6, 2733580.1)],
    ],
    spillway=[_point_on(FAYDH_AXIS[3:], max(_fs - 103.5, 0.0)), _point_on(FAYDH_AXIS[3:], min(_fs + 103.5, _main.length))],
    subbasins=["S11", "S12"],
    box=(430800.0, 2732000.0, 433600.0, 2735000.0),
    boundaries=[
        {"kind": "normal", "slope": 0.008, "coordinates": [(433590.0, 2732000.0), (433590.0, 2735000.0)]},
        {"kind": "normal", "slope": 0.008, "coordinates": [(431400.0, 2734990.0), (433600.0, 2734990.0)]},
        {"kind": "normal", "slope": 0.008, "coordinates": [(431400.0, 2732010.0), (433600.0, 2732010.0)]},
    ],
    inject=(430000.0, 2733100.0),
    axis_line=FAYDH_AXIS,
    tailwater_point=(431300.0, 2733400.0),
    pool_point=(430800.0, 2733400.0),
    upstream_side=(430800.0, 2733400.0),
)
DAM_LIST = {"Bidah 03": BIDAH, "Faydh 01": FAYDH}


def tied(dam: Dam, dem: Path = NSA2, step: float = 5.0, reach: float = 400.0) -> list[list[tuple[float, float]]]:
    """Crest lines with each open end carried on along its last segment until the ground passes the crest + 0.5 m."""
    import rasterio

    out = []
    with rasterio.open(dem) as src:
        for line in dam.crest_lines:
            pts = [tuple(p) for p in line]
            for end in (0, -1):
                a, b = (pts[1], pts[0]) if end == 0 else (pts[-2], pts[-1])
                v = np.array(b) - np.array(a)
                v = v / np.hypot(*v)
                extra = None
                for s in np.arange(step, reach, step):
                    q = np.array(b) + s * v
                    z = next(src.sample([(q[0], q[1])]))[0]
                    if z >= dam.crest + 0.5:
                        extra = (float(q[0]), float(q[1]))
                        break
                ground = next(src.sample([b]))[0]
                if ground < dam.crest + 0.5 and extra is not None:
                    pts = [extra] + pts if end == 0 else pts + [extra]
            out.append(pts)
    return out


def write_domain(dam: Dam) -> Path:
    polys = polygons()
    u = shapely.union_all([polys[n].buffer(40.0) for n in dam.subbasins] + [shapely.box(*dam.box)])
    path = OUT / f"domain_{dam.name.replace(' ', '')}.geojson"
    path.write_text(json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"name": dam.name}, "geometry": mapping(u)}]}), encoding="utf-8")
    return path


def objects(dam: Dam, shift: float = 0.0) -> list[dict]:
    """``shift`` moves the levels to another terrain's datum."""
    out: list[dict] = [{"kind": "crest_line", "coordinates": c, "z_constant": dam.crest + shift} for c in tied(dam)]
    out.append({"kind": "spillway", "coordinates": dam.spillway, "z_constant": dam.fsl + shift, "coefficient": dam.c,
                "length": dam.spill_len})
    return out


def job(dam: Dam, name: str, dx: float, times: np.ndarray, flows: np.ndarray, duration_s: float, with_objects: bool = True,
        manning: float = 0.04, dem: Path = NSA2, shift: float = 0.0) -> dict:
    lines = [
        {"name": "axis", "coordinates": dam.axis_line},
        {"name": "spillway", "coordinates": dam.spillway},
    ]
    points = [
        {"name": "pool", "x": dam.pool_point[0], "y": dam.pool_point[1]},
        {"name": "inject", "x": dam.inject[0], "y": dam.inject[1]},
        {"name": "tail", "x": dam.tailwater_point[0], "y": dam.tailwater_point[1]},
    ]
    return {
        "project": {"name": name, "description": f"{dam.name} routing"},
        "grid": {"dx": dx, "domain": str(write_domain(dam)), "cache_dir": str(CACHE)},
        "terrain": {"dem": str(dem), "pixel_stride": 1, "manning": manning, "objects": objects(dam, shift) if with_objects else []},
        "hydrology": {"inject_radius": 45.0, "inflows": [
            {"name": "inflow", "x": dam.inject[0], "y": dam.inject[1], "times_s": [float(t) for t in times],
             "flows": [float(q) for q in flows]}]},
        "boundaries": dam.boundaries,
        "outputs": {"map_every_s": 0.0, "series_every_s": 60.0, "live_every_s": 0.0, "lines": lines, "points": points},
        "run": {"duration_s": duration_s, "backend": "gpu", "source_every_s": 30.0, "checkpoint_every_s": 0.0},
    }


def modified_puls(dam: Dam, t_s: np.ndarray, q: np.ndarray, z0: float, crest_len: float) -> dict:
    """Level-pool routing on the EAV, by the storage-indication curve, on the inflow's own step."""
    e = dam.eav()
    z = np.arange(z0 - 8.0, dam.crest + 12.0, 0.01)
    s = np.interp(z, e[:, 1], e[:, 2])
    if z.max() > e[:, 1].max():
        last = e[-1]
        above = z > last[1]
        s[above] = last[2] + last[0] * (z[above] - last[1])
    out = dam.c * dam.spill_len * np.maximum(z - dam.fsl, 0.0) ** 1.5
    over = OVERTOP_C * crest_len * np.maximum(z - dam.crest, 0.0) ** 1.5
    total = out + over
    dt = float(t_s[1] - t_s[0])
    indication = 2.0 * s / dt + total
    st = float(np.interp(z0, z, s))
    level = np.zeros_like(q)
    outflow = np.zeros_like(q)
    level[0] = z0
    outflow[0] = float(np.interp(z0, z, total))
    for k in range(q.size - 1):
        rhs = q[k] + q[k + 1] + 2.0 * st / dt - outflow[k]
        zn = float(np.interp(rhs, indication, z))
        outflow[k + 1] = float(np.interp(zn, z, total))
        st = float(np.interp(zn, z, s))
        level[k + 1] = zn
    return {"t_s": t_s, "level": level, "outflow": outflow, "peak_out": float(outflow.max()),
            "t_peak_h": float(t_s[int(np.argmax(outflow))] / 3600.0), "peak_level": float(level.max()),
            "spill_at_peak": float(dam.c * dam.spill_len * max(level.max() - dam.fsl, 0.0) ** 1.5)}


if __name__ == "__main__":
    for d in DAM_LIST.values():
        print(d.name, d.spillway, shapely.LineString(d.spillway).length)
