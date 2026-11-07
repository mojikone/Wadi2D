"""Every name the suggestion writes, set once; its numbers are the job's ``breaklines`` section.

What the mesher already defines is read from the job's ``mesh`` settings and not repeated here: the analysis pixel,
the drainage area that makes a wadi, and the incision that makes it a defined one. The numbers of the detectors
themselves (the bank rise and reach, the flood margin, the top-hat) are the schema's ``Breaklines``, so the dock
can set them and a run folder records them; ``Settings`` is that class under the name this package has always used.
"""

from __future__ import annotations

from wadi2d.config.schema import Breaklines as Settings

FILE = "suggested_breaklines.gpkg"
LAYER = "breaklines"
THALWEG_LAYER = "thalwegs"
BANK, ROAD, DAM, OTHER = "stream bank", "road", "dam", "other crest"
"""The ``kind`` of a line: banks of defined wadis; crests by shape, a guess the user corrects."""
LEFT, RIGHT = "left", "right"
"""Side of a bank, looking downstream."""
GROUND, DEPTH_MAP = "ground", "depth map"
"""What placed the banks: the rise of the ground over the bed, or the flooded course of a run's depth map."""
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

__all__ = [
    "BANK",
    "COLUMNS",
    "DAM",
    "DEPTH_MAP",
    "FILE",
    "GROUND",
    "LAYER",
    "LEFT",
    "LINE_FIELDS",
    "OTHER",
    "RIGHT",
    "ROAD",
    "Settings",
    "THALWEG_COLUMNS",
    "THALWEG_LAYER",
]
