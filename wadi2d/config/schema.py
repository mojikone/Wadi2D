"""RunConfig: every parameter of a run, its unit, default and bounds, in one place.

Units are SI and fixed. ``extra="forbid"`` makes a misspelt key an error, not a silent default. The JSON
Schema exported from this module is what the QGIS plugin reads for its forms and defaults, so a number is
never written twice. Numerics reach the kernels through ``wadi2d.solver.params``, never as literals.
"""

from __future__ import annotations

import itertools
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

FORMAT_VERSION = "1.0"
SHAPED_KINDS = ("embankment", "channel", "channel_dyke")
"""Terrain objects with a cross-section: they reshape the ground along an alignment."""


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


class RefineLine(_Part):
    """Cells of a size on a band around a line, set as a HEC-RAS breakline is: near size, rows, far size.

    It only refines: no wall, and no faces on the line. Sizes go down to the ladder ``grid.dx`` x 2^n.
    """

    name: str = Field("", description="Name in reports; empty gives its number")
    coordinates: list[tuple[float, float]] = Field(description="Line, m", min_length=2)
    near_dx: float = Field(gt=0.0, le=1000.0, description="Cell size beside the line, m")
    rows: int = Field(
        4, ge=1, le=1000, description="Rows of near cells each side; each doubling out to far holds as many rows"
    )
    far_dx: float = Field(gt=0.0, le=1000.0, description="Cell size the band grades out to, 2:1; past it the other rules apply, m")

    @model_validator(mode="after")
    def _order(self) -> RefineLine:
        if self.near_dx > self.far_dx:
            raise ValueError(f"mesh line {self.name}: near_dx {self.near_dx} m must not exceed far_dx {self.far_dx} m")
        return self


class Mesh(_Part):
    """The quadtree. Off keeps the uniform grid of ``grid.dx``; on, that is the finest cell and tiles coarsen from it."""

    enabled: bool = Field(
        False,
        description="Refine tiles by the rules below; off is the uniform grid. Saves time above about 1 M cells, only memory below",
    )
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
    lines: list[RefineLine] = []

    @model_validator(mode="after")
    def _sizes(self) -> Mesh:
        if self.stream_area_mid_km2 > self.stream_area_fine_km2:
            raise ValueError("mesh.stream_area_mid_km2 must not exceed mesh.stream_area_fine_km2")
        return self


EndKind = Literal["open", "closed", "taper"]


class Opening(_Part):
    """A station range where the raised part of an object is left out: a side inflow or a culvert gap."""

    start: float = Field(ge=0.0, description="Station where the opening starts, m")
    end: float = Field(gt=0.0, description="Station where the opening ends, m")
    side: Literal["left", "right", "both"] = Field("both", description="Bank, looking along the stations")

    @model_validator(mode="after")
    def _order(self) -> Opening:
        if self.end <= self.start:
            raise ValueError(f"an opening ends at station {self.end:g}, before it starts at {self.start:g}")
        return self


class SectionRow(_Part):
    """One row of a section table; an empty value is read between its neighbours in the column."""

    station: float = Field(ge=0.0, description="Distance along the alignment, m")
    bed_z: float | None = Field(None, description="Bed elevation, m")
    width: float | None = Field(None, ge=0.0, le=2000.0, description="Bottom or crest width, m")
    crest_z: float | None = Field(None, description="Top on both sides, m")
    left_top_z: float | None = Field(None, description="Top of the left bank, m")
    right_top_z: float | None = Field(None, description="Top of the right bank, m")
    left_slope: float | None = Field(None, ge=0.0, le=50.0, description="Left inner slope, H:V")
    right_slope: float | None = Field(None, ge=0.0, le=50.0, description="Right inner slope, H:V")
    left_crest_width: float | None = Field(None, ge=0.0, le=200.0, description="Left dyke crest, m")
    right_crest_width: float | None = Field(None, ge=0.0, le=200.0, description="Right dyke crest, m")
    left_outer_slope: float | None = Field(None, ge=0.0, le=50.0, description="Left outer slope, H:V")
    right_outer_slope: float | None = Field(None, ge=0.0, le=50.0, description="Right outer slope, H:V")
    water_z: float | None = Field(None, description="Design water level, for a top set by freeboard, m")


class Section(_Part):
    """The cross-section of an embankment, channel or channel_dyke.

    Three ways in, which may be mixed: these constants; ``table`` or ``rows`` by station; or the bed from
    ``bed_start_z`` and ``bed_slope`` with the top ``freeboard`` above the water. Left and right are looking
    along increasing station, which runs from the first vertex.
    """

    width: float = Field(
        5.0, ge=0.0, le=2000.0, description="Bottom width of a channel, crest width of an embankment, m"
    )
    left_slope: float = Field(
        2.0, ge=0.0, le=50.0, description="Left side slope, H:V; the inner slope of a channel with dykes"
    )
    right_slope: float = Field(
        2.0, ge=0.0, le=50.0, description="Right side slope, H:V; the inner slope of a channel with dykes"
    )
    left_crest_width: float = Field(3.0, ge=0.0, le=200.0, description="Crest of the left dyke, m")
    right_crest_width: float = Field(3.0, ge=0.0, le=200.0, description="Crest of the right dyke, m")
    left_outer_slope: float = Field(2.0, ge=0.0, le=50.0, description="Outer slope of the left dyke, H:V")
    right_outer_slope: float = Field(2.0, ge=0.0, le=50.0, description="Outer slope of the right dyke, H:V")
    bed_z: float | None = Field(None, description="Constant bed elevation, m")
    crest_z: float | None = Field(None, description="Constant top on both banks, m")
    left_top_z: float | None = Field(None, description="Constant top of the left bank, m")
    right_top_z: float | None = Field(None, description="Constant top of the right bank, m")
    table: str | None = Field(None, description="CSV section table: station, then any section row column")
    rows: list[SectionRow] = Field([], description="The table inline; filled from ``table`` when that is set")
    bed_start_z: float | None = Field(None, description="Bed at station 0, m")
    bed_slope: float | None = Field(
        None, ge=-1.0, le=1.0, description="Fall of the bed per metre of station, m/m; with bed_start_z"
    )
    water_depth: float | None = Field(None, ge=0.0, le=100.0, description="Design depth above the bed, m")
    freeboard: float | None = Field(None, ge=0.0, le=20.0, description="Top above the design water, m")

    @model_validator(mode="after")
    def _stations(self) -> Section:
        for before, after in itertools.pairwise(self.rows):
            if after.station <= before.station:
                raise ValueError(
                    f"section stations must increase: station {after.station:g} comes after {before.station:g}"
                )
        return self


class TerrainObject(_Part):
    """A vector edit of the terrain, applied when the tables are built; the DEM file never changes."""

    kind: Literal["crest_line", "wall", "burn_line", "spillway", "embankment", "channel", "channel_dyke"]
    name: str = Field("", description="Name in reports and messages")
    coordinates: list[tuple[float, float]] = Field(description="Polyline vertices in the DEM CRS, m")
    z: list[float] | None = Field(None, description="Crest or invert elevation per vertex, m")
    z_constant: float | None = Field(None, description="Constant crest or invert elevation, m")
    width: float = Field(0.0, ge=0.0, le=200.0, description="Burn width, m; 0 means two DEM pixels")
    depth: float = Field(0.0, ge=0.0, le=50.0, description="Burn depth below ground, m")
    coefficient: float = Field(2.1, ge=0.5, le=4.0, description="Spillway C in Q = C L H^1.5, m^0.5/s")
    length: float | None = Field(None, ge=0.1, le=2000.0, description="Spillway crest length, m")
    section: Section | None = Field(None, description="Cross-section of a shaped object")
    openings: list[Opening] = Field([], description="Stretches with the raised part left out")
    lining_n: float | None = Field(
        None, ge=0.008, le=0.5, description="Manning n of the pixels on the channel section, s/m^(1/3)"
    )
    start_end: EndKind = Field(
        "open",
        description="Station 0: open stops the cut square, closed wraps the section round the end, taper fades it to the ground",
    )
    end_end: EndKind = Field(
        "open",
        description="Last station: open stops the cut square, closed wraps the section round the end, taper fades it to the ground",
    )
    taper_length: float = Field(30.0, gt=0.0, le=2000.0, description="Length of a tapered end, m")

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
        if self.kind in SHAPED_KINDS:
            self._check_shaped()
        elif self.section is not None or self.openings or self.lining_n is not None:
            raise ValueError(f"{self.kind} takes no section, openings or lining")
        return self

    def _check_shaped(self) -> None:
        section = self.section or Section()
        if self.kind == "channel" and self.openings:
            raise ValueError("a channel has no raised part to open: use channel_dyke")
        if self.kind == "embankment" and self.lining_n is not None:
            raise ValueError("an embankment has no channel section to line")
        if section.table is not None or section.rows:
            return  # checked when the table is read
        profile = self.z is not None or self.z_constant is not None
        bed = section.bed_z is not None or (section.bed_start_z is not None and section.bed_slope is not None)
        banks = section.left_top_z is not None and section.right_top_z is not None
        top = section.crest_z is not None or banks
        designed = section.freeboard is not None and section.water_depth is not None
        if self.kind == "embankment" and not (profile or top):
            raise ValueError("an embankment needs a crest: z, z_constant or section.crest_z")
        if self.kind != "embankment" and not (profile or bed):
            raise ValueError(
                f"{self.kind} needs a bed: z, z_constant, section.bed_z, or bed_start_z with bed_slope"
            )
        if self.kind == "channel_dyke" and not (top or designed):
            raise ValueError("channel_dyke needs a top: crest_z, both tops, or freeboard with water_depth")


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
    dyke_min_height: float = Field(
        0.05, ge=0.0, le=5.0, description="Ground this far below the top makes a stretch stand as a dyke, m"
    )
    crest_thin_ratio: float = Field(
        0.4, ge=0.0, le=8.0, description="Crest over cell size up to which a raised crest is a thin weir"
    )
    crest_eased_ratio: float = Field(
        1.5, ge=0.0, le=8.0, description="Crest over cell size at which the weir limit has eased fully"
    )
    crest_resolved_ratio: float = Field(
        2.0,
        ge=0.0,
        le=16.0,
        description="Crest over cell size from which the cells resolve it: no weir limit",
    )
    crest_eased_coefficient: float = Field(
        2.0, ge=1.0, le=4.0, description="Weir limit at crest_eased_ratio, on the energy head, m^0.5/s"
    )
    crest_accurate_ratio: float = Field(
        0.5, ge=0.0, le=8.0, description="Crest over cell size past which overtopping draws a warning"
    )
    volume_step: float = Field(
        50.0, gt=0.0, le=10000.0, description="Stations between rows of the cut and fill table, m"
    )
    preview_sections: int = Field(11, ge=2, le=101, description="Cross-sections per object in the preview")
    preview_points: int = Field(101, ge=11, le=2001, description="Points across a previewed cross-section")
    check_bed_length: float = Field(
        50.0, ge=0.0, le=10000.0, description="A bed above ground for this long draws a warning, m"
    )
    check_rise: float = Field(
        0.05, ge=0.0, le=10.0, description="A bed rising more than this along the stations is adverse, m"
    )
    check_grade: float = Field(
        0.5, ge=0.0, le=10.0, description="Bed or top changing faster than this is a step, m per m of station"
    )
    check_cells: float = Field(
        3.0,
        ge=0.0,
        le=64.0,
        description="A channel narrower than this between its banks draws a warning, cells",
    )
    check_pixels: float = Field(
        2.0, ge=0.0, le=64.0, description="A width below this cannot be seen in the DEM, pixels"
    )
    check_tie_height: float = Field(
        0.3,
        ge=0.0,
        le=20.0,
        description="A section ending this far off the ground has nothing to tie into, m",
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
        False,
        description="Each tile steps a power of two of the smallest step. Saves no time on a uniform grid; helps on a large mesh",
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
    snap_m: float = Field(
        150.0,
        ge=0.0,
        le=5000.0,
        description="A line this far off the active cells still opens the nearest of them, m",
    )
    min_share: float = Field(
        0.6,
        ge=0.0,
        le=1.0,
        description="A line opening less of the domain than this share of its length draws a warning",
    )


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


class Pixels(_Part):
    """The post-run product: depth and hazard at the terrain pixel, from the saved maps of the run.

    A pixel takes the highest class any limit gives, and H1 where it is wet but under every limit. The engine's
    cell hazard (``maps/hazard.tif``) stays as it is; this is a second, finer reading of the same run.
    """

    enabled: bool = Field(True, description="Make the pixel maps when a run finishes")
    pixel_m: float = Field(
        0.0, ge=0.0, le=1000.0, description="Pixel of the maps, a multiple of the DEM pixel, m; 0 means the DEM's"
    )
    cell_depth: float = Field(
        0.05, ge=0.0, le=10.0, description="A cell whose mean depth never reaches this is left out, m"
    )
    depth_floor: float = Field(
        0.05, ge=0.0, le=10.0, description="Below this a pixel is dry and takes no class, m"
    )
    hazard_limits: list[tuple[float, float, float]] = Field(
        [(0.3, 0.3, 2.0), (0.6, 0.5, 2.0), (0.6, 1.2, 2.0), (1.0, 2.0, 2.0), (4.0, 4.0, 4.0)],
        min_length=1,
        description="Depth x speed m2/s, depth m, speed m/s: above any of these a pixel leaves H1, then H2, ...",
    )
    link_margin: float = Field(
        0.01, ge=0.0, le=1.0, description="Water must stand this far above the ground of a shared face, m"
    )
    link_ratio: float = Field(
        0.5,
        gt=0.0,
        le=1.0,
        description="Two cells stepping down a slope are one flow if the shallower is this share of the deeper",
    )
    edge_band: float = Field(
        0.3,
        gt=0.0,
        le=0.5,
        description="Width beside a cell edge over which two joined cells ease into one surface, share of a cell",
    )
    edge_passes: int = Field(
        3, ge=0, le=12, description="Refills that remove the step at joined cell edges; 0 leaves each cell a block"
    )
    peak_lift: float = Field(
        3.0,
        ge=1.0,
        le=100.0,
        description="Most a cell's depth x speed is scaled up to the peak the run saw between saved maps",
    )
    batch_pixels: int = Field(
        50_000_000, ge=1_000_000, le=2_000_000_000, description="Pixels handled at a time on the GPU"
    )

    @model_validator(mode="after")
    def _rising(self) -> Pixels:
        for low, high in zip(self.hazard_limits, self.hazard_limits[1:], strict=False):
            if any(b < a for a, b in zip(low, high, strict=True)):
                raise ValueError("hazard_limits must not fall from one class to the next")
        return self


class Smooth(_Part):
    """The smooth drawing of the pixel maps. The pixel rasters stay the numbers of record."""

    enabled: bool = Field(True, description="Make smooth class polygons and the depth drawing")
    sigma_px: float = Field(
        1.0, ge=0.25, le=8.0, description="Width of the soft class masks, Gaussian sigma in pixels"
    )
    speckle_m2: float = Field(
        500.0, ge=0.0, le=1.0e6, description="A patch or a hole of a class smaller than this goes, m2"
    )
    simplify_px: float = Field(
        0.1, ge=0.0, le=2.0, description="Polygon vertices closer than this to the line go, pixels"
    )
    block_px: int = Field(
        4096, ge=256, le=32768, description="Pixels along a block, so memory stays bounded on any domain"
    )
    workers: int = Field(0, ge=0, le=256, description="Blocks worked on at once; 0 means half the logical cores")
    domain_sigma_cells: float = Field(
        0.8, ge=0.1, le=8.0, description="Width of the soft domain mask, Gaussian sigma in cells"
    )
    depth_scale: int = Field(
        2, ge=1, le=8, description="Drawing pixels per terrain pixel in the depth drawing"
    )
    depth_sigma_px: float = Field(
        0.7, ge=0.0, le=8.0, description="Width of the blur of the depth drawing, in terrain pixels"
    )
    wet_edge_px: float = Field(
        1.0, gt=0.0, le=8.0, description="Width of the soft wet edge of the depth drawing, in terrain pixels"
    )


class Outputs(_Part):
    map_every_s: float = Field(
        900.0,
        ge=0.0,
        le=86400.0,
        description="Seconds between saved maps; 900 for design work, 300 for an animation; 0 disables",
    )
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
    frame_bytes_per_cell: float = Field(
        10.0,
        gt=0.0,
        le=100.0,
        description="Disk per cell per saved map, for the estimate, B; the full extent at 30 m gave 10",
    )
    pixels: Pixels = Pixels()
    smooth: Smooth = Smooth()
    terrain_map: bool = Field(False, description="Write the modified terrain as a GeoTIFF with the run")
    points: list[DesignPoint] = []
    lines: list[DesignLine] = []


OBSERVED_STORMS = ("hyetograph", "gridded")
"""Rain given as it falls: no area reduction applies."""


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

    kind: Literal["none", "uniform", "hypothetical", "hyetograph", "gridded"] = "none"
    depth_mm: float = Field(0.0, ge=0.0, le=5000.0, description="Point depth, mm")
    depth_grid: str | None = Field(
        None, description="Raster of depths in mm, replacing depth_mm; each 2D cell takes its own value"
    )
    duration_min: float = Field(60.0, gt=0.0, le=20160.0, description="Storm duration, minutes")
    time_percent: list[float] | None = Field(None, description="Hypothetical pattern, percent of duration")
    depth_percent: list[float] | None = Field(None, description="Hypothetical pattern, percent of depth")
    storm_area_km2: float | None = Field(None, gt=0.0, description="Area at which the ARF table is read")
    arf: ArfTableConfig | None = None
    hyetograph_min: list[float] | None = Field(None, description="End of each period, minutes from the start")
    hyetograph_mm: list[float] | None = Field(None, description="Depth in each period, mm")
    rain_file: str | None = Field(None, description="NetCDF file, DSS file, or folder of one GeoTIFF per period")
    rain_variable: str | None = Field(
        None, description="NetCDF variable, or B/C/F of a DSS pathname; None takes the only one there is"
    )
    rain_units: Literal["auto", "mm", "mm/h", "m"] = Field(
        "auto", description="What the rain values are; auto reads the file, and a GeoTIFF has no units so it is mm"
    )
    rain_interval_min: float | None = Field(
        None, gt=0.0, description="Length of a period, for a file that does not say; a GeoTIFF folder always needs it"
    )
    rain_stamp: Literal["end", "start"] = Field(
        "end", description="Whether a time with no bounds closes its period or opens it"
    )
    rain_start: str | None = Field(
        None, description="Date and time the run starts at; None takes the start of the first period"
    )

    @model_validator(mode="after")
    def _pattern(self) -> Storm:
        if self.kind == "hypothetical" and (self.time_percent is None or self.depth_percent is None):
            raise ValueError("a hypothetical storm needs time_percent and depth_percent")
        if self.kind in OBSERVED_STORMS and (self.arf is not None or self.depth_grid is not None):
            raise ValueError(f"a {self.kind} storm takes no area reduction and no depth grid: it is the rain itself")
        if self.kind == "hyetograph":
            self._check_hyetograph()
        if self.kind == "gridded" and self.rain_file is None:
            raise ValueError("a gridded storm needs rain_file")
        return self

    def _check_hyetograph(self) -> None:
        ends, depths = self.hyetograph_min, self.hyetograph_mm
        if not ends or not depths or len(ends) != len(depths):
            raise ValueError("a hyetograph needs hyetograph_min and hyetograph_mm, one depth per period")
        if ends[0] <= 0.0 or any(b <= a for a, b in itertools.pairwise(ends)):
            raise ValueError("hyetograph_min must rise from above zero: each value closes a period")
        if min(depths) < 0.0 or sum(depths) <= 0.0:
            raise ValueError("hyetograph_mm cannot go below zero and must hold some rain")


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


class Handback(_Part):
    """A line where 2D flow leaves the grid and enters a lumped element, whose route runs during the 2D run.

    Inside the grid the line is a sink: its cells stay dry and take what reaches them from either side. A boundary
    that follows the level would pass water on to the cells beyond it, and that water would miss the reach.
    """

    name: str
    coordinates: list[tuple[float, float]] = Field(description="Polyline across the flow, m", min_length=2)
    element: str = Field(description="Lumped element that receives what crosses the line")
    snap_m: float = Field(
        150.0, ge=0.0, le=5000.0, description="A line this far off the active cells still opens the nearest, m"
    )
    min_share: float = Field(
        0.6,
        ge=0.0,
        le=1.0,
        description="A line opening less of the domain than this share of its length draws a warning",
    )


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
    handbacks: list[Handback] = []
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

    @model_validator(mode="after")
    def _handback_names(self) -> Hydrology:
        names = [h.name for h in self.handbacks]
        if len(set(names)) != len(names):
            raise ValueError("hand-back names must differ: results are kept by name")
        return self


class Transmission(_Part):
    """Dry-bed transmission loss on 2D routing cells: a rate over the wetted bed, as HEC-HMS's percolation method."""

    enabled: bool = Field(False, description="Off leaves every number as it was")
    rate_mm_h: float = Field(
        25.0, gt=0.0, le=2000.0, description="Infiltration into the wetted bed, mm/h"
    )
    max_depth_mm: float | None = Field(
        None, gt=0.0, description="Total a square metre of bed can take, mm; None means no limit"
    )
    min_depth_m: float = Field(
        0.1,
        ge=0.0,
        le=10.0,
        description="Level above a cell's lowest point that makes it a channel cell, m; thin sheet flow keeps its CN",
    )
    water_share: float = Field(
        0.5, gt=0.0, le=1.0, description="Most of a cell's water one source window may take"
    )
    area: str | None = Field(None, description="Polygons of the bed it applies to; None means every cell")


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
    transmission: Transmission = Transmission()
    boundaries: list[Boundary] = []
    initial_levels: list[InitialLevel] = []
    outputs: Outputs = Outputs()
    run: Run = Run()
    arf: ArfStudy = ArfStudy()


class BasinSettings(_Part):
    """What ``wadi2d basin`` needs beyond the job. Not a part of RunConfig, so a job is the same with or without it."""

    stream_threshold_km2: float | None = Field(
        10.0, gt=0.0, description="Drainage area that starts a stream, km2; None breaks at the pour points only"
    )
    analysis_pixel: float | None = Field(
        None, gt=0.0, le=100.0, description="Pixel of the delineation, m; None takes mesh.analysis_pixel"
    )
    max_pixels: int = Field(
        400_000_000, ge=1, description="Largest analysis raster, pixels; a bigger one asks for a coarser pixel"
    )
    snap_m: float = Field(
        100.0, ge=0.0, le=5000.0, description="Reach of a pour point towards the nearest stream, m; 0 keeps its pixel"
    )
    min_reach_m: float = Field(
        100.0, ge=0.0, le=5000.0, description="A shorter link gets no reach: its junctions join directly, m"
    )
    min_subbasin_km2: float = Field(
        0.05, ge=0.0, description="A smaller local catchment joins a neighbour draining to the same junction, km2"
    )
    min_slope: float = Field(1.0e-4, gt=0.0, le=0.1, description="Floor of a reach slope, m/m")
    min_raster_share: float = Field(
        0.9, gt=0.0, le=1.0, description="Share of an element a raster must cover for its mean to count"
    )
    section_spacing_m: float = Field(100.0, gt=0.0, le=5000.0, description="Cross-sections along a reach, m")
    section_half_width_m: float = Field(
        500.0, gt=0.0, le=10000.0, description="Reach of a cross-section from the stream, m"
    )
    section_depth_m: float = Field(
        4.0, gt=0.0, le=50.0, description="Depth above the bed over which the trapezoid is fitted, m"
    )
    section_depths: int = Field(9, ge=3, le=33, description="Depths of the width curve of a section")
    section_search_m: float = Field(
        30.0, ge=0.0, le=500.0, description="How far from the D8 line the bed of a section is looked for, m"
    )
    reservoir_step_m: float = Field(0.5, gt=0.0, le=20.0, description="Rows of a reservoir table, m")
    reservoir_top_m: float = Field(
        10.0, gt=0.0, le=100.0, description="Reservoir table above the dam crest, m"
    )
    dam_min_km2: float = Field(
        1.0, ge=0.0, description="A crest line draining less is a saddle dam: it makes no node, km2"
    )
    dam_join_m: float = Field(
        50.0, ge=0.0, le=2000.0, description="A spillway this close to a crest line belongs to that dam, m"
    )


def json_schema() -> dict:
    """The JSON Schema of a job file, for the plugin and the documentation."""
    return RunConfig.model_json_schema()


PositiveFloat = Annotated[float, Field(gt=0.0)]
