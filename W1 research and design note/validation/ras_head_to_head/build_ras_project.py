"""Write a HEC-RAS 2D project as text: prj, g01, u01, p01, rasmap. No GUI, no RasMapper.

usage: build_ras_project.py FOLDER --dx 20 --equation 1 [--cores 16]
The seeds are a square lattice aligned to the DEM, so interior cells are the same squares as the Wadi2D grid.
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
from pathlib import Path

import numpy as np

import case

HERE = Path(__file__).resolve().parent
COMMON = HERE / "ras_common"
NAME = "Fan"
PROJECT = "Fan"


def pair(x: float, y: float) -> str:
    return f"{x:16.9f}{y:16.8f}"


def records(xy: np.ndarray, per_line: int) -> list[str]:
    out = []
    for i in range(0, len(xy), per_line):
        out.append("".join(pair(x, y) for x, y in xy[i : i + per_line]))
    return out


def geometry(dx: float) -> str:
    x0, y0, side = case.X0, case.Y0, case.SIDE
    x1, y1 = x0 + side, y0 - side
    n = round(side / dx)
    perim = np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]])
    xs = x0 + (np.arange(n) + 0.5) * dx
    ys = y0 - (np.arange(n) + 0.5) * dx
    xx, yy = np.meshgrid(xs, ys)
    seeds = np.column_stack([xx.ravel(), yy.ravel()])
    stamp = dt.datetime.now().strftime("%d%b%Y %H:%M:%S")
    g = [
        f"Geom Title=Fan window {dx:g} m",
        "Program Version=6.60",
        f"Viewing Rectangle= {x0 - 100} , {x1 + 100} , {y0 + 100} , {y1 - 100} ",
        "",
        f"Storage Area={NAME:<16},,",
        f"Storage Area Surface Line= {len(perim)} ",
        *[pair(x, y) for x, y in perim],
        "Storage Area Type= 1 ",
        "Storage Area Area=",
        "Storage Area Min Elev=",
        "Storage Area Is2D=-1",
        f"Storage Area Point Generation Data=,,{dx:g},{dx:g}",
        f"Storage Area 2D Points= {len(seeds)} ",
        *records(seeds, 2),
        f"Storage Area 2D PointsPerimeterTime={stamp}",
        f"Storage Area Mannings={case.MANNING}",
        "2D Cell Volume Filter Tolerance=0.003",
        "2D Cell Minimum Area Fraction=0.01",
        "2D Face Profile Filter Tolerance=0.003",
        "2D Face Area Elevation Profile Filter Tolerance=0.003",
        "2D Face Area Elevation Conveyance Ratio=0.02",
        "2D Face Min Length Ratio=0.05",
        "2D Face Area Laminar Depth=0.06",
        "2D Multiple Face Mann n=0",
        "2D Composite LC=0",
        "",
    ]
    lines = {
        "Inflow": np.array([[x0, case.INFLOW_Y[0]], [x0, case.INFLOW_Y[1]]]),
        "OutEast": np.array([[x1, y1], [x1, y0]]),
        "OutNorth": np.array([[x1, y0], [x0, y0]]),
    }
    for name, c in lines.items():
        mid = c.mean(axis=0)
        g += [
            f"BC Line Name={name:<32}",
            f"BC Line Storage Area={NAME:<16}",
            f"BC Line Start Position= {c[0, 0]} , {c[0, 1]} ",
            f"BC Line Middle Position= {mid[0]} , {mid[1]} ",
            f"BC Line End Position= {c[-1, 0]} , {c[-1, 1]} ",
            f"BC Line Arc= {len(c)} ",
            *records(c, 2),
            "BC Line Text Position= 1.79769313486232E+308 , 1.79769313486232E+308 ",
        ]
    for name, (off, a, b) in case.SECTIONS.items():
        xl = x0 + off
        c = np.array([[xl, y0 - b], [xl, y0 - a]])
        mid = c.mean(axis=0)
        g += [
            f"Reference Line Name={name:<40}",
            f"Reference Line Storage Area={NAME:<16}",
            f"Reference Line Start Position= {c[0, 0]} , {c[0, 1]} ",
            f"Reference Line Middle Position= {mid[0]} , {mid[1]} ",
            f"Reference Line End Position= {c[-1, 0]} , {c[-1, 1]} ",
            f"Reference Line Arc= {len(c)} ",
            *records(c, 2),
            "Reference Line Text Position= 1.79769313486232E+308 , 1.79769313486232E+308 ",
        ]
    g += [
        "",
        "Use User Specified Reach Order=0",
        "GIS Ratio Cuts To Invert=-1",
        "GIS Limit At Bridges=0",
        "Composite Channel Slope=5",
        "",
    ]
    return "\r\n".join(g)


def _f8(v: float) -> str:
    s = f"{v:.6g}"
    return f"{s:>8}"


def flow() -> str:
    t, q = case.hydrograph()
    u = [
        "Flow Title=Fan hydrograph",
        "Program Version=6.60",
        "Use Restart= 0 ",
    ]
    loc = "Boundary Location=                ,                ,        ,        ,                ,"
    u += [
        f"{loc}{NAME:<16},                ,{'Inflow':<32},                                ",
        f"Interval={case.DT_TABLE_MIN}MIN",
        f"Flow Hydrograph= {len(q)} ",
    ]
    for i in range(0, len(q), 10):
        u.append("".join(_f8(v) for v in q[i : i + 10]))
    u += [
        "Stage Hydrograph TW Check=0",
        f"Flow Hydrograph Slope= {case.SLOPE_IN} ",
        "DSS Path=",
        "Use DSS=False",
        "Use Fixed Start Time=False",
        "Fixed Start Date/Time=,",
        "Is Critical Boundary=False",
        "Critical Boundary Flow=",
    ]
    for name in ("OutEast", "OutNorth"):
        u += [
            f"{loc}{NAME:<16},                ,{name:<32},                                ",
            f"Friction Slope={case.SLOPE_OUT},0",
        ]
    tail = (COMMON / "template.u").read_text(encoding="latin-1").replace("\r\n", "\n").split("\n")
    start = next(i for i, x in enumerate(tail) if x.startswith("Met Point Raster Parameters"))
    stop = next(i for i in range(start, len(tail)) if tail[i].startswith("Boundary Location"))
    return "\r\n".join(u + tail[start:stop])


DROP = re.compile(
    r"^(Breach |Simplified Physical|Mass Wasting|DLBreach|Calibration |\s+\d+\s+\d+\s+\d+\s+\d+\s*$)"
)


def plan(dx: float, equation: int, cores: int, step: str, courant: bool = True) -> str:
    text = (COMMON / "template.p").read_text(encoding="latin-1").replace("\r\n", "\n").split("\n")
    subst = {
        "Plan Title=": f"Plan Title=Fan {dx:g} m eq{equation}",
        "Short Identifier=": f"Short Identifier=Fan{dx:g}e{equation}".ljust(82),
        "Simulation Date=": f"Simulation Date=01JAN2000,0000,01JAN2000,{case.DURATION_H:02d}00",
        "Geom File=": "Geom File=g01",
        "Flow File=": "Flow File=u01",
        "Computation Interval=": f"Computation Interval={step}",
        "Output Interval=": "Output Interval=1MIN",
        "Instantaneous Interval=": "Instantaneous Interval=5MIN",
        "Mapping Interval=": "Mapping Interval=5MIN",
        "UNET D2 Equation=": f"UNET D2 Equation= {equation} ",
        "UNET D2 Cores=": f"UNET D2 Cores={cores}",
        "UNET D2 Name=": f"UNET D2 Name={NAME}",
        "Run RASMapper=": "Run RASMapper= 0 ",
        "Computation Time Step Use Courant=": f"Computation Time Step Use Courant=        {-1 if courant else 0}",
        "Computation Time Step Max Courant=": "Computation Time Step Max Courant=1",
        "Computation Time Step Min Courant=": "Computation Time Step Min Courant=0.45",
        "Computation Time Step Count To Double=": "Computation Time Step Count To Double=5",
        "Computation Time Step Max Doubling=": "Computation Time Step Max Doubling=3",
        "Computation Time Step Max Halving=": "Computation Time Step Max Halving=5",
    }
    out = []
    for line in text:
        if DROP.match(line):
            continue
        for key, value in subst.items():
            if line.startswith(key):
                line = value
                break
        out.append(line)
    i = next(n for n, x in enumerate(out) if x.startswith("Write Detailed="))
    out[i:i] = ["HDF Additional Output Variable=Face Flow", "HDF Additional Output Variable=Cell Velocity"]
    return "\r\n".join(out)


def prj() -> str:
    text = (COMMON / "template.prj").read_text(encoding="latin-1").replace("\r\n", "\n").split("\n")
    out = ["Proj Title=Fan", "Current Plan=p01"]
    for line in text:
        if line.startswith(("Proj Title", "Current Plan", "Geom File", "Unsteady File", "Plan File")):
            if line.startswith("Geom File") and "Geom File=g01" not in out:
                out += ["Geom File=g01", "Unsteady File=u01", "Plan File=p01"]
            continue
        out.append(line)
    return "\r\n".join(out)


def rasmap(terrain_rel: str) -> str:
    return f"""<RASMapper>
  <Version>2.0.0</Version>
  <RASProjectionFilename Filename=".\\Projection UTM40.prj" />
  <Geometries Checked="True" Expanded="True">
    <Layer Name="Fan" Type="RASGeometry" Checked="True" Filename=".\\{PROJECT}.g01.hdf" />
  </Geometries>
  <Terrains Checked="True" Expanded="True">
    <Layer Name="Terrain" Type="TerrainLayer" Checked="True" Filename="{terrain_rel}">
      <ResampleMethod>near</ResampleMethod>
      <Surface On="True" />
    </Layer>
  </Terrains>
  <CurrentSettings>
    <ProjectSettings>
      <RiverStationUnits>Meters</RiverStationUnits>
    </ProjectSettings>
  </CurrentSettings>
</RASMapper>
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--dx", type=float, default=20.0)
    ap.add_argument("--equation", type=int, default=1, help="0 DWE, 1 SWE-ELM, 2 SWE-EM")
    ap.add_argument("--cores", type=int, default=16)
    ap.add_argument("--step", default="10SEC")
    ap.add_argument("--fixed-step", action="store_true", help="turn the Courant control off")
    a = ap.parse_args()
    d = Path(a.folder)
    d.mkdir(parents=True, exist_ok=True)
    enc = "latin-1"
    (d / f"{PROJECT}.prj").write_text(prj(), encoding=enc, newline="")
    (d / f"{PROJECT}.g01").write_text(geometry(a.dx), encoding=enc, newline="")
    (d / f"{PROJECT}.u01").write_text(flow(), encoding=enc, newline="")
    (d / f"{PROJECT}.p01").write_text(plan(a.dx, a.equation, a.cores, a.step, not a.fixed_step), encoding=enc, newline="")
    (d / f"{PROJECT}.rasmap").write_text(
        rasmap(r"..\ras_common\Terrain\Terrain.hdf"), encoding=enc, newline=""
    )
    (d / "Projection UTM40.prj").write_bytes((COMMON / "Projection UTM40.prj").read_bytes())
    print("written", d)


if __name__ == "__main__":
    main()
