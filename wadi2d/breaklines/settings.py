"""Every number the suggestion uses, set once.

What the mesher already defines is read from the job's ``mesh`` settings and not repeated here: the analysis pixel,
the drainage area that makes a wadi, and the incision that makes it a defined one. The rest is this module's.
"""

from __future__ import annotations

from dataclasses import dataclass

FILE = "suggested_breaklines.gpkg"
LAYER = "breaklines"
THALWEG_LAYER = "thalwegs"
BANK, ROAD, DAM, OTHER = "stream bank", "road", "dam", "other crest"
"""The ``kind`` of a line: banks of defined wadis; crests by shape, a guess the user corrects."""
LEFT, RIGHT = "left", "right"
"""Side of a bank, looking downstream."""
LINE_FIELDS = ("near_dx", "rows", "far_dx")
"""What the Mesh section's table of refinement lines reads from a layer by itself: the same layer serves it."""
COLUMNS = {
    "name": str,
    "kind": str,
    "side": str,
    "height_m": float,
    "length_m": float,
    "area_km2": float,
    "slope": float,
    "score": float,
    "why": str,
    "near_dx": float,
    "rows": int,
    "far_dx": float,
}
"""``height_m`` is how far a crest stands above its surroundings, or a channel below them; ``slope`` the ground
under a crest, m/m; ``score`` is height times length, m2, the face of the line above the ground: the lines that
matter most come first. ``near_dx``, ``rows`` and ``far_dx`` fill the Mesh section's table: the job's cell beside
the line, the schema's rows, the job's coarsest cell."""
THALWEG_COLUMNS = {"area_km2": float, "incised_m": float, "length_m": float}


@dataclass(frozen=True)
class Settings:
    disc_radius_m: float = 40.0
    """Top-hat structuring disc: a raised feature narrower than twice this stands out of its ground. W5's sweep:
    40 m finds 82 % of the highway at 0.5 m with the fewest lines elsewhere of the settings over 80 %."""
    crest_height_m: float = 0.5
    """Top-hat height that counts as a crest, m. An embankment stands 0.5 to 1 m above its fitted ground."""
    min_length_m: float = 100.0
    """A line shorter than this is noise, whatever its height."""
    section_step_m: float = 10.0
    """Spacing of the sections that find the banks along a thalweg."""
    bank_offset_cells: float = 1.0
    """A bank line stands at least this many cells from the thalweg: the thalweg keeps a row of cells of its own."""
    smooth_vertices: int = 5
    """Moving average over this many vertices before a line is simplified."""
    simplify_pixels: float = 0.5
    """Douglas-Peucker tolerance, in analysis pixels."""
    ground_slope_max: float = 0.15
    """A crest on ground steeper than this is the mountain's own spur or gully edge, which the sub-grid tables hold
    already, and is left out; a crest that crosses a defined wadi stays whatever its ground. On Bidah the hills'
    crests stand on ground of median slope 0.32, the fan's on 0.03."""
    road_length_m: float = 1000.0
    """A straight crest at least this long reads as a road."""
    road_straightness: float = 0.9
    """Chord over length that makes a crest straight."""
    bank_jump_steps: float = 3.0
    """A bank that moves more than this many section steps between sections starts a new line."""
