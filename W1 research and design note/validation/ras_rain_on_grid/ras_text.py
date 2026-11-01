"""Write a HEC-RAS 6.6 rain-on-grid project as text, no GUI. Grammar notes in ras_rain_on_grid.md.

Templates come from ras_head_to_head/ras_common. Precipitation sits on the Boundary Conditions side, as in the
Majlas models: a Boundary Location naming the 2D area with an empty BC line, then Interval and Precipitation
Hydrograph. `Precipitation Mode` on the Meteorology side stays Disable: a message in Ras.exe warns against both on.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
COMMON = HERE.parent / "ras_head_to_head" / "ras_common"
ENC = "latin-1"
LOC = "Boundary Location=                ,                ,        ,        ,                ,"


@dataclass
class Project:
    name: str  # also the name of the 2D area, at most 16 characters
    title: str
    perimeter: np.ndarray  # closed ring, (n, 2)
    seeds: np.ndarray  # (m, 2)
    dx: float
    manning: float
    rain_interval: str  # "5MIN"
    rain_mm: np.ndarray  # depth per interval, the first value at the start of the run is 0
    duration_h: int
    equation: int  # 1 SWE-ELM, 2 SWE-EM
    cores: int = 8
    step: str = "10SEC"
    map_interval: str = "1MIN"
    terrain_rel: str = r"..\ras_terrain\Terrain.hdf"
    bc_lines: dict[str, np.ndarray] = field(default_factory=dict)  # normal depth lines on the perimeter
    slope_out: float = 0.01
    extra_outputs: list[str] = field(default_factory=list)


def pair(x: float, y: float) -> str:
    return f"{x:16.9f}{y:16.8f}"


def records(xy: np.ndarray, per_line: int) -> list[str]:
    return ["".join(pair(x, y) for x, y in xy[i : i + per_line]) for i in range(0, len(xy), per_line)]


def geometry(p: Project) -> str:
    x0, y0 = p.perimeter.min(axis=0)
    x1, y1 = p.perimeter.max(axis=0)
    stamp = dt.datetime.now().strftime("%d%b%Y %H:%M:%S")
    g = [
        f"Geom Title={p.title}",
        "Program Version=6.60",
        f"Viewing Rectangle= {x0 - 100} , {x1 + 100} , {y1 + 100} , {y0 - 100} ",
        "",
        f"Storage Area={p.name:<16},,",
        f"Storage Area Surface Line= {len(p.perimeter)} ",
        *[pair(x, y) for x, y in p.perimeter],
        "Storage Area Type= 1 ",
        "Storage Area Area=",
        "Storage Area Min Elev=",
        "Storage Area Is2D=-1",
        f"Storage Area Point Generation Data=,,{p.dx:g},{p.dx:g}",
        f"Storage Area 2D Points= {len(p.seeds)} ",
        *records(p.seeds, 2),
        f"Storage Area 2D PointsPerimeterTime={stamp}",
        f"Storage Area Mannings={p.manning}",
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
    for name, c in p.bc_lines.items():
        mid = c.mean(axis=0)
        g += [
            f"BC Line Name={name:<32}",
            f"BC Line Storage Area={p.name:<16}",
            f"BC Line Start Position= {c[0, 0]} , {c[0, 1]} ",
            f"BC Line Middle Position= {mid[0]} , {mid[1]} ",
            f"BC Line End Position= {c[-1, 0]} , {c[-1, 1]} ",
            f"BC Line Arc= {len(c)} ",
            *records(c, 2),
            "BC Line Text Position= 1.79769313486232E+308 , 1.79769313486232E+308 ",
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


def f8(v: float) -> str:
    """Exactly eight characters, as many digits as fit; RAS reads the table by column."""
    if v == 0.0:
        return f"{0:>8}"
    for digits in (6, 5, 4, 3, 2, 1, 0):
        s = f"{v:.{digits}f}"
        if len(s) <= 8:
            return f"{s:>8}"
    raise ValueError(v)


def flow(p: Project) -> str:
    u = [f"Flow Title={p.title}", "Program Version=6.60", "Use Restart= 0 "]
    for name in p.bc_lines:
        u += [
            f"{LOC}{p.name:<16},                ,{name:<32},                                ",
            f"Friction Slope={p.slope_out},0",
        ]
    u += [
        f"{LOC}{p.name:<16},                ,{'':<32},                                ",
        f"Interval={p.rain_interval}",
        f"Precipitation Hydrograph= {len(p.rain_mm)} ",
    ]
    for i in range(0, len(p.rain_mm), 10):
        u.append("".join(f8(v) for v in p.rain_mm[i : i + 10]))
    u += [
        "DSS Path=",
        "Use DSS=False",
        "Use Fixed Start Time=False",
        "Fixed Start Date/Time=,",
        "Is Critical Boundary=False",
        "Critical Boundary Flow=",
    ]
    tail = (COMMON / "template.u").read_text(encoding=ENC).replace("\r\n", "\n").split("\n")
    start = next(i for i, x in enumerate(tail) if x.startswith("Met Point Raster Parameters"))
    stop = next(i for i in range(start, len(tail)) if tail[i].startswith("Boundary Location"))
    return "\r\n".join(u + tail[start:stop])


DROP = re.compile(
    r"^(Breach |Simplified Physical|Mass Wasting|DLBreach|Calibration |\s+\d+\s+\d+\s+\d+\s+\d+\s*$)"
)


def sim_date(duration_h: int) -> str:
    start = dt.datetime(2000, 1, 1)
    end = start + dt.timedelta(hours=duration_h)
    return f"{start:%d%b%Y},0000,{end:%d%b%Y},{end:%H%M}".upper()


def plan(p: Project) -> str:
    text = (COMMON / "template.p").read_text(encoding=ENC).replace("\r\n", "\n").split("\n")
    subst = {
        "Plan Title=": f"Plan Title={p.title}",
        "Short Identifier=": f"Short Identifier={p.name}{p.dx:g}e{p.equation}".ljust(82),
        "Simulation Date=": f"Simulation Date={sim_date(p.duration_h)}",
        "Geom File=": "Geom File=g01",
        "Flow File=": "Flow File=u01",
        "Computation Interval=": f"Computation Interval={p.step}",
        "Output Interval=": "Output Interval=1MIN",
        "Instantaneous Interval=": f"Instantaneous Interval={p.map_interval}",
        "Mapping Interval=": f"Mapping Interval={p.map_interval}",
        "UNET D2 Equation=": f"UNET D2 Equation= {p.equation} ",
        "UNET D2 Cores=": f"UNET D2 Cores={p.cores}",
        "UNET D2 Name=": f"UNET D2 Name={p.name}",
        "Run RASMapper=": "Run RASMapper= 0 ",
        "Computation Time Step Use Courant=": "Computation Time Step Use Courant=        -1",
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
    variables = ["Face Flow", "Cell Velocity", *p.extra_outputs]
    out[i:i] = [f"HDF Additional Output Variable={v}" for v in variables]
    return "\r\n".join(out)


def prj(p: Project) -> str:
    text = (COMMON / "template.prj").read_text(encoding=ENC).replace("\r\n", "\n").split("\n")
    out = [f"Proj Title={p.name}", "Current Plan=p01"]
    for line in text:
        if line.startswith(("Proj Title", "Current Plan", "Geom File", "Unsteady File", "Plan File")):
            if line.startswith("Geom File") and "Geom File=g01" not in out:
                out += ["Geom File=g01", "Unsteady File=u01", "Plan File=p01"]
            continue
        out.append(line)
    return "\r\n".join(out)


def rasmap(p: Project) -> str:
    return f"""<RASMapper>
  <Version>2.0.0</Version>
  <RASProjectionFilename Filename=".\\Projection UTM40.prj" />
  <Geometries Checked="True" Expanded="True">
    <Layer Name="{p.name}" Type="RASGeometry" Checked="True" Filename=".\\{p.name}.g01.hdf" />
  </Geometries>
  <Terrains Checked="True" Expanded="True">
    <Layer Name="Terrain" Type="TerrainLayer" Checked="True" Filename="{p.terrain_rel}">
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


def write(p: Project, folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{p.name}.prj").write_text(prj(p), encoding=ENC, newline="")
    (folder / f"{p.name}.g01").write_text(geometry(p), encoding=ENC, newline="")
    (folder / f"{p.name}.u01").write_text(flow(p), encoding=ENC, newline="")
    (folder / f"{p.name}.p01").write_text(plan(p), encoding=ENC, newline="")
    (folder / f"{p.name}.rasmap").write_text(rasmap(p), encoding=ENC, newline="")
    (folder / "Projection UTM40.prj").write_bytes((COMMON / "Projection UTM40.prj").read_bytes())
