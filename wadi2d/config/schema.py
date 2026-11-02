"""RunConfig: every parameter of a run, its unit, default and bounds, in one place.

Units are SI and fixed. ``extra="forbid"`` makes a misspelt key an error, not a silent default. The JSON
Schema exported from this module is what the QGIS plugin reads for its forms and defaults, so a number is
never written twice. Numerics reach the kernels through ``wadi2d.solver.params``, never as literals.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

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
    cache_dir: str | None = Field(None, description="Grid cache folder; None uses 'cache' in the run folder")
    line_samples: int = Field(
        4, ge=1, le=32, description="Points per cell when a boundary line picks the cells it crosses"
    )
    content_hash_limit_mb: float = Field(
        64.0,
        ge=0.0,
        le=4096.0,
        description="Input files up to this size are hashed by content for the cache, MB",
    )


class RefineZone(_Part):
    """A polygon the user wants at a cell size."""

    coordinates: list[tuple[float, float]] = Field(description="Polygon ring, m", min_length=3)
    dx: float = Field(gt=0.0, le=1000.0, description="Wanted cell size inside it, m")


class Mesh(_Part):
    """The quadtree. Off keeps the uniform grid of ``grid.dx``; on, that is the finest cell and tiles coarsen from it."""

    enabled: bool = Field(False, description="Refine tiles by the rules below; off is the uniform grid")
    coarse_dx: float = Field(
        40.0, gt=0.0, le=1000.0, description="Coarsest cell, m; grid.dx times a power of two"
    )
    min_dx: float = Field(
        5.0, gt=0.0, le=1000.0, description="Smallest cell the mesher accepts, m; small cells set the step"
    )
    analysis_pixel: float = Field(5.0, gt=0.0, le=100.0, description="Pixel of the stream analysis, m")
    stream_area_fine_km2: float = Field(
        10.0, gt=0.0, description="Defined wadis draining this much stay at the finest cell, km2"
    )
    stream_area_mid_km2: float = Field(
        1.0, gt=0.0, description="Defined wadis draining this much stay one step coarser than the coarsest, km2"
    )
    stream_pixels: int = Field(3, ge=1, description="Pixels of wadi that make a tile count as holding one")
    incision_depth: float = Field(
        0.5, ge=0.0, le=50.0, description="A stream counts where it lies this far below the ground around it, m"
    )
    incision_width: float = Field(
        200.0, gt=0.0, le=5000.0, description="Square over which the ground around a stream is averaged, m"
    )
    break_depth: float = Field(
        0.0, ge=0.0, le=50.0, description="Ground leaving a plane by this over a coarse cell is a slope break, m; 0 is off"
    )
    break_share: float = Field(
        0.4, gt=0.0, le=1.0, description="Share of a tile in slope breaks that refines it one step"
    )
    refine_lines: bool = Field(
        True, description="Barriers, boundaries and design lines sit on the finest cells; faces must lie on them"
    )
    zones: list[RefineZone] = []

    @model_validator(mode="after")
    def _sizes(self) -> Mesh:
        if self.stream_area_mid_km2 > self.stream_area_fine_km2:
            raise ValueError("mesh.stream_area_mid_km2 must not exceed mesh.stream_area_fine_km2")
        return self


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

    @model_validator(mode="after")
    def _heights(self) -> TerrainObject:
        if len(self.coordinates) < 2:
            raise ValueError("a terrain object needs at least two vertices")
        if self.z is not None and len(self.z) != len(self.coordinates):
            raise ValueError("z needs one elevation per vertex")
        if self.kind in ("crest_line", "spillway") and self.z is None and self.z_constant is None:
            raise ValueError(f"{self.kind} needs z or z_constant")
        if self.kind == "burn_line" and self.z is None and self.z_constant is None and self.depth <= 0.0:
            raise ValueError("burn_line needs z, z_constant or depth")
        return self


class Terrain(_Part):
    dem: str | None = Field(None, description="GeoTIFF path; its CRS is the project CRS")
    pixel_stride: int = Field(
        1, ge=1, le=64, description="Read every n-th DEM pixel; dx must be a multiple of pixel * stride"
    )
    join_cells: float = Field(
        2.0, ge=0.0, le=16.0, description="A crest or wall ending this close to another line joins it, cells"
    )
    spillway_snap_cells: float = Field(
        1.0,
        ge=0.0,
        le=8.0,
        description="A crest face this close to a spillway line carries the spillway, cells",
    )
    burn_pixels: int = Field(2, ge=1, le=64, description="Burn width when an object gives none, DEM pixels")
    spillway_stretch: float = Field(
        1.5, ge=1.0, le=20.0, description="A spillway longer than its drawn line by this ratio gets a warning"
    )
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
    mirror_dry_faces: bool = Field(
        True, description="A dry or closed neighbour face gives no velocity to momentum advection"
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
    wave_floor: float = Field(
        3.0,
        ge=0.1,
        le=30.0,
        description="Least wave speed in the step rule, so dry ground gets no long step, m/s",
    )
    plan_min: float = Field(
        0.02, ge=1e-4, le=1.0, description="Least wet share of a cell plan in the wave speed"
    )
    active_every: int = Field(
        16, ge=1, le=32, description="Steps between active-tile rebuilds; at most the tile size"
    )
    local_time_stepping: bool = Field(
        False, description="Each tile steps a power of two of the smallest step; off keeps the uniform step"
    )
    lts_levels: int = Field(
        3, ge=0, le=5, description="Highest time level: the slowest tile steps 2^this x the smallest step"
    )
    lts_wave_floor: float = Field(
        1.0,
        ge=0.1,
        le=30.0,
        description="Least wave speed in a tile's own step, m/s; lower than wave_floor, the buffer guards fronts",
    )
    lts_buffer: float = Field(
        1.0,
        ge=0.5,
        le=1.0,
        description="Share of the fastest neighbour's wave a tile respects, so a front can enter it within a cycle",
    )


class Boundary(_Part):
    """An open boundary: cells along a line whose level is prescribed; every other edge is a wall."""

    kind: Literal["stage", "normal", "free"]
    coordinates: list[tuple[float, float]] = Field(description="Polyline along the boundary cells, m")
    stage: float = Field(0.0, description="Level for kind 'stage', m")
    slope: float = Field(0.005, ge=1e-5, le=0.5, description="Energy slope for kind 'normal'")


class InitialLevel(_Part):
    """Water standing at a level when the run starts: a reservoir at its full supply level, say."""

    coordinates: list[tuple[float, float]] = Field(description="Polygon ring, m", min_length=3)
    level: float = Field(description="Water level on the datum of the DEM, m")


class DesignPoint(_Part):
    """A point where depth and level are recorded."""

    name: str
    x: float = Field(description="Easting, m")
    y: float = Field(description="Northing, m")
    drainage_area_km2: float | None = Field(None, gt=0.0, description="For the depth-area study, km2")


class DesignLine(_Part):
    """A line across the flow; discharge is summed over the lattice faces it crosses, positive to its right."""

    name: str
    coordinates: list[tuple[float, float]] = Field(description="Polyline, m", min_length=2)
    drainage_area_km2: float | None = Field(None, gt=0.0, description="For the depth-area study, km2")


class Outputs(_Part):
    map_every_s: float = Field(900.0, ge=0.0, le=86400.0, description="0 disables time maps, s")
    series_every_s: float = Field(60.0, ge=1.0, le=3600.0, description="Point and line series step, s")
    live_every_s: float = Field(
        5.0, ge=0.0, le=3600.0, description="Wall seconds between live rasters; 0 disables"
    )
    live_stride: int = Field(2, ge=1, le=16, description="Cells per live-raster pixel")
    hazard: Literal["dv"] = "dv"
    maxima_every: int = Field(4, ge=1, le=64, description="Steps between updates of the maxima")
    arrival_depth: float = Field(
        0.1, ge=0.0, le=10.0, description="Level above the cell's lowest point that counts as arrival, m"
    )
    speed_depth: float = Field(
        0.05, ge=0.0, le=1.0, description="Cells shallower than this are left out of speed and hazard, m"
    )
    wet_depth: float = Field(
        0.1, ge=0.0, le=10.0, description="Mean depth that counts a cell as wet in the wet area, m"
    )
    edge_depth: float = Field(
        3.0, ge=0.0, le=100.0, description="Depth against a closed domain edge that draws a warning, m"
    )
    progress_every_s: float = Field(
        2.0, ge=0.05, le=600.0, description="Wall seconds between progress events and stop checks"
    )
    points: list[DesignPoint] = []
    lines: list[DesignLine] = []


class ArfTableConfig(_Part):
    """An area-reduction table, read linearly in area."""

    areas_km2: list[float] = Field(min_length=1, description="Storm areas, increasing, km2")
    factors: list[float] = Field(min_length=1, description="Area-reduction factor per area")
    table_type: str = Field(
        "fixed-area",
        description="What the table is; printed on every output, because a storm-centred ratio is not a "
        "fixed-area curve",
    )
    reduces_below_table: bool = Field(
        True,
        description="Below the smallest area the first factor holds; False leaves the depth whole, as HMS",
    )


class Storm(_Part):
    """Rain as a function of time. ``kind`` selects the builder in ``wadi2d.storm``."""

    kind: Literal["none", "uniform", "hypothetical"] = "none"
    depth_mm: float = Field(0.0, ge=0.0, le=5000.0, description="Point depth, mm")
    depth_grid: str | None = Field(
        None, description="Raster of depths in mm, replacing depth_mm; each 2D cell takes its own value"
    )
    duration_min: float = Field(60.0, gt=0.0, le=20160.0, description="Storm duration, minutes")
    time_percent: list[float] | None = Field(None, description="Hypothetical pattern, percent of duration")
    depth_percent: list[float] | None = Field(None, description="Hypothetical pattern, percent of depth")
    storm_area_km2: float | None = Field(None, gt=0.0, description="Area at which the ARF table is read")
    arf: ArfTableConfig | None = None

    @model_validator(mode="after")
    def _pattern(self) -> Storm:
        if self.kind == "hypothetical" and (self.time_percent is None or self.depth_percent is None):
            raise ValueError("a hypothetical storm needs time_percent and depth_percent")
        return self


class Subbasin(_Part):
    """A subbasin of the job. Lumped: its hydrograph enters at ``outlet`` and its polygon masks the rain."""

    name: str
    mode: Literal["lumped", "2d"] = "lumped"
    outlet: tuple[float, float] | None = Field(None, description="Where a lumped hydrograph enters, m")
    curve_number: float | None = Field(None, gt=0.0, le=100.0, description="CN of a 2D subbasin")


class Inflow(_Part):
    """A hydrograph entering at a point: from ``element`` of the lumped network, or from the table."""

    name: str
    x: float = Field(description="Easting, m")
    y: float = Field(description="Northing, m")
    element: str | None = Field(None, description="Lumped element whose outflow enters here")
    times_s: list[float] | None = Field(None, description="Table times, s")
    flows: list[float] | None = Field(None, description="Table discharges, m3/s")

    @model_validator(mode="after")
    def _source(self) -> Inflow:
        table = self.times_s is not None and self.flows is not None
        if table == (self.element is not None):
            raise ValueError(f"inflow {self.name} needs either element or times_s and flows")
        if table and len(self.times_s) != len(self.flows):
            raise ValueError(f"inflow {self.name}: one flow per time")
        return self


class Hydrology(_Part):
    """Subbasins, their polygons and the lumped network. Every path is optional: rain-on-grid needs none."""

    hms_basin: str | None = Field(None, description="HEC-HMS .basin file of the lumped network")
    hms_project: str | None = Field(
        None, description="The .hms file, for paired tables; None takes the one beside the basin file"
    )
    hms_sqlite: str | None = Field(None, description="The basin .sqlite holding the subbasin polygons")
    polygons: str | None = Field(None, description="GeoJSON of subbasin polygons with a 'name' property")
    time_step_min: float = Field(5.0, gt=0.0, le=60.0, description="Step of the lumped engine, minutes")
    curve_number: float | None = Field(
        None, gt=0.0, le=100.0, description="CN of 2D cells without a better source; None means no losses"
    )
    subbasins: list[Subbasin] = []
    inflows: list[Inflow] = []
    inject_radius: float = Field(
        30.0, ge=0.0, le=1000.0, description="Cells this close to an inflow point receive it, m"
    )
    inject_min_depth: float = Field(
        0.1, ge=0.0, le=5.0, description="Cells below this level count as dry for an inflow, m"
    )
    inject_max_offset: float = Field(
        200.0,
        ge=0.0,
        le=5000.0,
        description="An inflow point farther than this from the domain is refused, m",
    )


class ArfStudy(_Part):
    """The depth-area study: one run per storm area, each design point reading its own drainage area."""

    areas_km2: list[float] = Field([], description="Storm areas, km2; empty means log-spaced")
    n_areas: int = Field(6, ge=2, le=32, description="Log-spaced storm areas")
    area_min_km2: float = Field(10.0, gt=0.0, description="Smallest log-spaced storm area, km2")
    area_max_km2: float = Field(600.0, gt=0.0, description="Largest log-spaced storm area, km2")
    exact_points: bool = Field(False, description="Add each design point's drainage area as a storm area")
    accumulation: str | None = Field(None, description="Flow accumulation raster for the composite map")
    accumulation_units: Literal["cells", "km2"] = "cells"


class Run(_Part):
    duration_s: float = Field(3600.0, ge=1.0, le=2.6e6, description="Simulated time, s")
    backend: Literal["auto", "gpu", "cpu"] = "auto"
    source_every_s: float = Field(
        30.0, ge=1.0, le=600.0, description="Step at which rain and inflows are refreshed, s"
    )
    checkpoint_every_s: float = Field(
        300.0, ge=0.0, le=86400.0, description="Wall seconds between checkpoints; 0 disables"
    )
    balance_every: int = Field(
        8, ge=1, le=64, description="Kept so old jobs load; the balance now counts every step"
    )
    estimate_depth: float = Field(
        7.5,
        gt=0.0,
        le=50.0,
        description="Deepest flowing cell assumed by --dry-run, m; Block 2 at 20 m gave 7.5",
    )
    estimate_speed: float = Field(
        8.0, ge=0.0, le=25.0, description="Fastest flow assumed by --dry-run, m/s; Block 2 at 20 m gave 8"
    )
    estimate_wave: float = Field(
        1.3,
        ge=1.0,
        le=10.0,
        description="Real wave speed over u + sqrt(g h), the wet plan share raises it; Block 2 whole catchment at 20 m gave 1.3",
    )
    estimate_overhead: float = Field(
        1.5, ge=1.0, le=10.0, description="Real step cost over the flat-bed probe; Block 2 at 20 m gave 1.5"
    )


class RunConfig(_Part):
    """The whole job."""

    project: Project = Project()
    grid: GridConfig = GridConfig()
    mesh: Mesh = Mesh()
    terrain: Terrain = Terrain()
    tables: Tables = Tables()
    numerics: Numerics = Numerics()
    storm: Storm = Storm()
    hydrology: Hydrology = Hydrology()
    boundaries: list[Boundary] = []
    initial_levels: list[InitialLevel] = []
    outputs: Outputs = Outputs()
    run: Run = Run()
    arf: ArfStudy = ArfStudy()


def json_schema() -> dict:
    """The JSON Schema of a job file, for the plugin and the documentation."""
    return RunConfig.model_json_schema()


PositiveFloat = Annotated[float, Field(gt=0.0)]
