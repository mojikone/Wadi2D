"""RunConfig: every parameter of a run, its unit, default and bounds, in one place.

Units are SI and fixed. ``extra="forbid"`` makes a misspelt key an error, not a silent default. The JSON
Schema exported from this module is what the QGIS plugin reads for its forms and defaults, so a number is
never written twice. Numerics reach the kernels through ``wadi2d.solver.params``, never as literals.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

FORMAT_VERSION = "1.0"


class _Part(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Project(_Part):
    format_version: str = FORMAT_VERSION
    name: str = "run"
    description: str = ""


class GridConfig(_Part):
    """The uniform grid. The origin snaps to DEM pixel corners; dx must be a multiple of the DEM pixel."""

    dx: float = Field(10.0, ge=0.5, le=1000.0, description="Cell size, m")
    domain: str | None = Field(None, description="Polygon file; None uses extent")
    extent: tuple[float, float, float, float] | None = Field(None, description="xmin, ymin, xmax, ymax, m")


class TerrainObject(_Part):
    """A vector edit of the terrain, applied when the tables are built; the DEM file never changes."""

    kind: Literal["crest_line", "wall", "burn_line", "spillway"]
    coordinates: list[tuple[float, float]] = Field(description="Polyline vertices in the DEM CRS, m")
    z: list[float] | None = Field(None, description="Crest or invert elevation per vertex, m")
    z_constant: float | None = Field(None, description="Constant crest or invert elevation, m")
    width: float = Field(0.0, ge=0.0, le=200.0, description="Burn width, m; 0 means two DEM pixels")
    depth: float = Field(0.0, ge=0.0, le=50.0, description="Burn depth below ground, m")
    coefficient: float = Field(2.1, ge=0.5, le=4.0, description="Spillway C in Q = C L H^1.5, m^0.5/s")
    length: float | None = Field(None, ge=0.1, le=2000.0, description="Spillway crest length, m")


class Terrain(_Part):
    dem: str | None = Field(None, description="GeoTIFF path; its CRS is the project CRS")
    objects: list[TerrainObject] = []
    manning: float = Field(0.035, ge=0.008, le=0.5, description="Default Manning n, s/m^(1/3)")
    manning_raster: str | None = None
    cn_raster: str | None = None


class Tables(_Part):
    """Sub-grid tables. Rows are spaced quadratically: fine near the bottom, where the geometry matters."""

    rows: int = Field(16, ge=4, le=64, description="Rows per cell and per face table")
    face_depth_max: float = Field(
        16.0, ge=1.0, le=100.0, description="Table top above the face invert, at most, m"
    )
    face_depth_min: float = Field(
        8.0, ge=0.5, le=50.0, description="Table top above the face invert, at least, m"
    )
    crest_tolerance: float = Field(
        0.05,
        ge=0.0,
        le=1.0,
        description="A face is a natural crest when its invert exceeds both mean beds by this, m",
    )


class Numerics(_Part):
    cfl: float = Field(0.45, ge=0.05, le=0.7, description="Courant number on |u| + sqrt(g d)")
    limiter: Literal["none", "minmod"] = Field(
        "minmod", description="Second-order momentum advection limiter"
    )
    sheet_flow: bool = Field(
        True, description="Volume-based section and mean-surface drive for thin flow on slopes"
    )
    e_wet: float = Field(
        1e-4, ge=1e-6, le=0.1, description="Depth over the face invert below which a face is dry, m"
    )
    h_cfl: float = Field(
        0.01, ge=1e-4, le=1.0, description="Cells with a level below this are left out of the step, m"
    )
    u_max: float = Field(25.0, ge=1.0, le=100.0, description="Velocity cap, m/s")
    dt_max: float = Field(5.0, ge=1e-3, le=600.0, description="Largest step, s")
    dt_min: float = Field(1e-3, ge=1e-6, le=1.0, description="Below it the run stops and names the cell, s")
    dt_every: int = Field(8, ge=1, le=64, description="Steps between time-step reductions")
    active_every: int = Field(
        16, ge=1, le=64, description="Steps between active-tile rebuilds; must stay under the tile size"
    )


class Boundary(_Part):
    """An open boundary: cells along a line whose level is prescribed; every other edge is a wall."""

    kind: Literal["stage", "normal", "free"]
    coordinates: list[tuple[float, float]] = Field(description="Polyline along the boundary cells, m")
    stage: float = Field(0.0, description="Level for kind 'stage', m")
    slope: float = Field(0.005, ge=1e-5, le=0.5, description="Energy slope for kind 'normal'")


class Outputs(_Part):
    map_every_s: float = Field(900.0, ge=0.0, le=86400.0, description="0 disables time maps, s")
    series_every_s: float = Field(60.0, ge=1.0, le=3600.0, description="Point and line series step, s")
    live_every_s: float = Field(
        5.0, ge=0.0, le=3600.0, description="Wall seconds between live rasters; 0 disables"
    )
    live_stride: int = Field(2, ge=1, le=16, description="Cells per live-raster pixel")
    hazard: Literal["dv"] = "dv"


class Run(_Part):
    duration_s: float = Field(3600.0, ge=1.0, le=2.6e6, description="Simulated time, s")
    backend: Literal["auto", "gpu", "cpu"] = "auto"
    source_every_s: float = Field(
        30.0, ge=1.0, le=600.0, description="Step at which rain and inflows are refreshed, s"
    )
    checkpoint_every_s: float = Field(
        300.0, ge=0.0, le=86400.0, description="Wall seconds between checkpoints; 0 disables"
    )


class RunConfig(_Part):
    """The whole job."""

    project: Project = Project()
    grid: GridConfig = GridConfig()
    terrain: Terrain = Terrain()
    tables: Tables = Tables()
    numerics: Numerics = Numerics()
    boundaries: list[Boundary] = []
    outputs: Outputs = Outputs()
    run: Run = Run()


def json_schema() -> dict:
    """The JSON Schema of a job file, for the plugin and the documentation."""
    return RunConfig.model_json_schema()


PositiveFloat = Annotated[float, Field(gt=0.0)]
