"""Write the Wadi2D job and the RAS project of one configuration. usage: build.py NAME [--wadi-only]"""
from __future__ import annotations

import datetime as dt
import json
import sys

import numpy as np
import rasterio
import shapely
from shapely.geometry import LineString

import t1case as c

sys.path.insert(0, str(c.W1))
import build_case as bc  # noqa: E402
import ras_text  # noqa: E402

HERE = c.HERE


def wadi_job(name: str, cfg: dict) -> None:
    job = json.loads((c.base.HERE / "jobs" / f"{cfg['dx']:g}m_n050_em.json").read_text(encoding="utf-8"))
    job["project"]["name"] = f"t1_{name}"
    job["grid"]["cache_dir"] = str(HERE / "cache")
    job["run"]["duration_s"] = cfg["hours"] * 3600.0
    job["outputs"]["map_every_s"] = 300.0
    if cfg["zc"] is not None:
        job["terrain"]["objects"] = [
            {"kind": "crest_line", "coordinates": [list(p) for p in c.AXIS], "z_constant": cfg["zc"]}
        ]
        job["outputs"]["lines"].append({"name": "crest", "coordinates": [list(p) for p in c.AXIS]})
    (HERE / "jobs").mkdir(exist_ok=True)
    (HERE / "jobs" / f"{name}.json").write_text(json.dumps(job, indent=1), encoding="utf-8")


def weir_profile(zc: float, line: list[tuple[float, float]], step: float = 2.0) -> np.ndarray:
    """(station, elevation) from the start of ``line``: max(ground, crest), corners only, stations from 0."""
    ls = LineString(line)
    s = np.append(np.arange(0.0, ls.length, step), ls.length)
    pts = [(ls.interpolate(a).x, ls.interpolate(a).y) for a in s]
    with rasterio.open(c.base.DEM) as ds:
        z = np.array([v[0] for v in ds.sample(pts)], float)
    prof = np.maximum(z, zc)
    keep = [0]
    for k in range(1, len(s) - 1):
        if not (prof[k - 1] == prof[k] == prof[k + 1]):
            keep.append(k)
    keep.append(len(s) - 1)
    return np.column_stack((s[keep], prof[keep]))


def connection_block(
    name: str, area: str, line: list[tuple[float, float]], prof: np.ndarray, method2d: bool, dx: float
) -> list[str]:
    mid = np.mean(line, axis=0)
    stamp = dt.datetime.now().strftime("%b/%d/%Y %H:%M:%S")
    out = [
        f"Connection={name:<16},{mid[0]},{mid[1]}",
        "Connection Desc=",
        f"Connection Line={len(line)}",
        *ras_text.records(np.array(line), 2),
        "Connection Centerline Profile=0",
        f"Connection Last Edited Time={stamp}",
        f"Conn CellSize Min={dx:g}",
        f"Conn CellSize Max={dx:g}",
        "Conn Near Repeats=1",
        f"Connection Up SA={area:<16}",
        f"Connection Dn SA={area:<16}",
        "Conn Routing Type= 1 ",
        "Conn Use RC Family=False",
        f"Conn OverFlow Method 2D={'True' if method2d else 'False'}",
        "Conn Weir WD=6",
        f"Conn Weir Coef={c.WEIR_C}",
        "Conn Weir Is Ogee= 0 ",
        "Conn Simple Spill Pos Coef=0.05",
        "Conn Simple Spill Neg Coef=0.05",
        f"Conn Weir SE= {len(prof)} ",
    ]
    vals = [f"{v:8.3f}"[:8] for v in prof.ravel()]
    out += ["".join(vals[i : i + 10]) for i in range(0, len(vals), 10)]
    out += [
        "",
        "Conn Outlet Rating Curve= 0 ,False,,",
        "Conn BR: Bridge=0,0,0,0, 0 ,0.3,0.5",
        "Conn BR: Pressure-Weir=,,,,",
        "Conn BR: Deck Dist Width WeirC Skew NumUp NumDn MinLoCord MaxHiCord MaxSubmerge Is_Ogee",
        f",6,{c.WEIR_C},0, 0, 0, , , 0.98, 0, 0,0,,",
        "Conn BR: BR SE=1,0",
        "Conn BR: BR Bank Stations=1,,",
        "Conn BR: BR Mann=1,0",
        "Conn BR: BR SE=2,0",
        "Conn BR: BR Bank Stations=2,,",
        "Conn BR: BR Mann=2,0",
        "Conn BR: BR Coef=-1 , 0 , 0 ,,,0.8,-1,,0,",
        "Conn BR: BR Skew=0",
        "Conn BR: XS SE=1,0",
        "Conn BR: XS Bank Stations=1,,",
        "Conn BR: XS Mann=1,0",
        "Conn BR: XS SE=2,0",
        "Conn BR: XS Bank Stations=2,,",
        "Conn BR: XS Mann=2,0",
    ]
    return out


def aligned_seeds(dx: float) -> np.ndarray:
    """Lattice seeds with pairs mirrored across each leg of the line, so that cell faces lie on it, as a breakline does."""
    lat = bc.seeds_of(dx)
    line = LineString(c.AXIS)
    keep = np.array([line.distance(shapely.Point(p)) > 1.1 * dx for p in lat])
    pairs = []
    a = np.array(c.AXIS)
    for p, q in zip(a[:-1], a[1:], strict=True):
        leg = float(np.hypot(*(q - p)))
        d = (q - p) / leg
        n = np.array([-d[1], d[0]])
        m = max(round(leg / dx), 1)
        for k in range(m):
            mid = p + d * (k + 0.5) * leg / m
            pairs.append(mid + 0.5 * dx * n)
            pairs.append(mid - 0.5 * dx * n)
    pairs = np.array(pairs)
    good = []
    for z in pairs:
        if not good or np.min(np.hypot(*(np.array(good) - z).T)) > 0.6 * dx:
            good.append(z)
    return np.vstack((lat[keep], np.array(good)))


def ras_project(name: str, cfg: dict, seeds: np.ndarray | None = None) -> None:
    per = json.loads((c.base.HERE / "perimeter.json").read_text(encoding="utf-8"))
    bc.FOLDER = c.base.HERE
    step_end, mm = bc.hyetograph()
    rain = bc.ras_rain(step_end, mm)
    rain = rain[: round(cfg["hours"] * 60 / 5.0) + 1]
    terrain = str(c.base.HERE / "ras_terrain" / "Terrain.hdf")
    p = ras_text.Project(
        name="Bidah",
        title=f"Bidah crest {name}",
        perimeter=np.array(per["ring"]),
        seeds=(aligned_seeds(cfg["dx"]) if cfg.get("aligned") else bc.seeds_of(cfg["dx"])) if seeds is None else seeds,
        dx=cfg["dx"],
        manning=0.05,
        rain_interval="5MIN",
        rain_mm=rain,
        duration_h=cfg["hours"],
        equation=2,
        cores=int(cfg.get("cores", 8)),
        step="10SEC",
        map_interval="1MIN",
        bc_lines={"OutEast": np.array(per["east_outlet"]), "OutNorth": np.array(per["north_outlet"])},
        slope_out=c.base.SLOPE_OUT,
        terrain_rel=terrain,
    )
    folder = HERE / f"ras_{name}"
    ras_text.write(p, folder)
    if cfg["zc"] is None:
        return
    line = list(reversed(c.AXIS))  # left to right looking downstream
    prof = weir_profile(cfg["zc"], line)
    g = (folder / "Bidah.g01").read_text(encoding=ras_text.ENC).splitlines()
    k = next(i for i, x in enumerate(g) if x.startswith("BC Line Name="))
    g[k:k] = connection_block("Embankment", "Bidah", line, prof, cfg["method2d"], cfg["dx"])
    (folder / "Bidah.g01").write_text("\r\n".join(g), encoding=ras_text.ENC, newline="")


def main() -> None:
    name = sys.argv[1]
    cfg = c.CONFIGS[name]
    wadi_job(name, cfg)
    if "--wadi-only" not in sys.argv:
        ras_project(name, cfg)
    print("written", name)


if __name__ == "__main__":
    main()
