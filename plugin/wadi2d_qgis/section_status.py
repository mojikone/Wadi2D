# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The status of each section of the dock (W99): Ready, Optional or Missing, and one line of words. No Qt here.

A section's ``standing()`` gathers a few plain facts from its own widgets, with no layer read feature by feature, and one
function here turns them into a :class:`Status`: the state the card, the step strip and the footer colour by, and the
words that always stand beside the colour. Missing means the run cannot start as the section stands; the words say what
to do. It is a quick guide while the model is filled in: Check and run still makes the whole check on the job itself.
"""

from __future__ import annotations

from pathlib import Path
from typing import NamedTuple

from . import land_rows, reduction_rows, table_rows
from .model_types import NEEDS_LUMPED, TWO_D, TYPES, UNUSED_LUMPED
from .simulation_rows import STEPS_REVERSED, start_problem
from .storm_rows import (
    ARF_AREA,
    ARF_GIVEN,
    ARF_STUDY,
    KIND_DEPTH,
    KIND_DEPTH_GRID,
    KIND_DESIGN,
    KIND_FIXED,
    KIND_GAUGES,
    KIND_GRID,
    KIND_HMS,
    KIND_STEADY,
    KIND_TABLE,
    storm_problems,
)

READY, OPTIONAL, MISSING = "ready", "optional", "missing"
STATE_WORDS = {READY: "Ready", OPTIONAL: "Optional", MISSING: "Missing"}
STATE_MARKS = {READY: "\N{CHECK MARK}", OPTIONAL: "\N{EN DASH}", MISSING: "!"}
"""A mark beside a step's name, so the strip does not tell a state by colour alone."""
SEP = " \N{MIDDLE DOT} "
STEP_NAMES = {
    "terrain": "Terrain", "mesh": "Mesh", "hydrology": "Hydrology", "tables": "Tables", "storm": "Storm",
    "reduction": "ARF", "structures": "Structures", "boundaries": "Boundaries", "points": "Points", "gauges": "Gauges",
    "simulation": "Simulation", "run": "Run", "study": "Study",
}  # fmt: skip
"""Section key to its short name on the step strip."""


NO_LOSSES = "no losses: all the rain on the grid runs off"


class Status(NamedTuple):
    state: str
    words: str


def needing(statuses: dict[str, Status], shown: tuple[str, ...]) -> list[str]:
    """The keys of the shown sections that are missing something."""
    return [key for key in shown if key in statuses and statuses[key].state == MISSING]


def footer_words(count: int) -> str:
    if count == 0:
        return "No section is missing anything"
    return f"{count} section{'s' if count > 1 else ''} need{'' if count > 1 else 's'} you before running"


def join(*parts: str) -> str:
    return SEP.join(part for part in parts if part)


# One function per section. Each takes plain facts and nothing of Qt.


def terrain(
    dem: str | None,
    has_file: bool,
    geographic: bool,
    dx: float,
    domain: str | None,
    manning: float,
    manning_raster: str | None,
    roughness: dict | None = None,
) -> Status:
    if dem is None or not has_file:
        return Status(MISSING, "Choose a DEM layer backed by a file.")
    if geographic:
        return Status(MISSING, "The DEM must be in a projected CRS, in metres.")
    found = land_rows.roughness_problems(roughness, True)  # the aligned cells are the Mesh section's to say
    if found:
        return Status(MISSING, found[0])
    rough = land_rows.rough_words(roughness, manning, manning_raster)
    return Status(
        READY,
        join(f"DEM {dem}", f"cell {dx:g} m", f"domain {domain}" if domain else "current map extent", rough),
    )


def mesh(
    enabled: bool, coarse: float, lines: int, corridors: bool, corridor_layer: str | None, centres: bool = False
) -> Status:
    if corridors and centres and corridor_layer and not enabled:  # the aligned centre mesh (W101)
        return Status(READY, f"The aligned centre mesh along the streams of {corridor_layer}")
    if enabled and corridors:
        return Status(
            MISSING, "Corridors run on the uniform grid: untick the mesh refinement or the corridors."
        )
    if corridors and not corridor_layer:
        return Status(MISSING, "Choose the Suggested breaklines layer for the corridors, or untick them.")
    if corridors:
        return Status(READY, f"Corridors of aligned cells along {corridor_layer}")
    if enabled:
        return Status(
            READY, join(f"Refined: coarsest cell {coarse:g} m", f"{lines} refinement lines" if lines else "")
        )
    return Status(OPTIONAL, "One cell size everywhere, the one of Terrain")


def _losses(cn: float | None, cn_raster: str | None, loss: float | None) -> str:
    """``cn`` beside ``cn_raster`` is the CN of the grid's holes (W106)."""
    if cn_raster:
        curve = f"curve number from {cn_raster}" + (f", {cn:g} where it has none" if cn else "")
    else:
        curve = f"curve number {cn:g}" if cn else NO_LOSSES
    return join(curve, f"transmission loss {loss:g} mm/h" if loss else "")


def hydrology(
    kind: str | None, hms: str | None, hms_complete: bool, basin_ticked: bool, basin_ready: bool, subbasins: int,
    lumped: int, cn: float | None, cn_raster: str | None, loss: float | None,
) -> Status:  # fmt: skip
    losses = _losses(cn, cn_raster, loss)
    has_lumped = bool(hms) or basin_ticked
    if kind == TWO_D or (not has_lumped and not (kind in TYPES and TYPES[kind].needs_lumped)):
        state = READY if cn or cn_raster else OPTIONAL
        return Status(
            state, join(losses[0].upper() + losses[1:], UNUSED_LUMPED if kind == TWO_D and has_lumped else "")
        )
    if not has_lumped:
        return Status(MISSING, NEEDS_LUMPED.format(title=TYPES[kind].title))
    if hms and not hms_complete:
        return Status(MISSING, "The HMS folder needs a basin, a meteorologic and a control file.")
    if basin_ticked and not hms and not basin_ready:
        return Status(MISSING, "Press Generate basin first, or untick it: the run needs the generated basin.")
    source = f"HMS project {hms}" if hms else "Basin generated from the DEM"
    return Status(READY, join(source, f"{subbasins} subbasins, {lumped} lumped" if subbasins else "", losses))


def _reduction(storm: dict) -> str:
    mode = storm.get("arf_mode")
    if mode == ARF_AREA:
        return f"area reduction at {storm.get('area_km2', 0.0):g} km2"
    if mode == ARF_GIVEN:
        return f"reduction factor {storm.get('arf_factor', 1.0):g}"
    if mode == ARF_STUDY:
        return "area reduction by the depth-area study"
    return "no area reduction"


def storm(source: str, values: dict, hms_in_use: bool, rain_gauges: int = 0) -> Status:
    """``values`` is what the Storm section gives the job builder; ``source`` its Rain source."""
    if source == KIND_HMS:
        return Status(READY, "As in the HMS project, with its area reduction")
    if source == KIND_GAUGES:
        if rain_gauges == 0:
            return Status(MISSING, "Add the rain gauges: a row each, or a point layer.")
        return Status(READY, f"{rain_gauges} rain gauge{'s' if rain_gauges > 1 else ''}, as received")
    held = values.get("storm")
    if held is None:  # constant rain with no HMS project: the two numbers alone
        rain, hours = values.get("rain_mm_h", 0.0), values.get("rain_hours", 0.0)
        if rain <= 0.0 or hours <= 0.0:
            return Status(MISSING, "Set the rain and how many hours it lasts.")
        return Status(READY, f"Constant rain {rain:g} mm/h for {hours:g} h")
    found = storm_problems(held)
    if found:
        return Status(MISSING, found[0])
    kind = held["kind"]
    if kind == KIND_FIXED:
        return Status(READY, f"Fixed depth {held['depth_mm']:g} mm over {held['hours']:g} h, uniform")
    if kind == KIND_DEPTH:
        pattern = table_rows.pattern_words(held.get("pattern"))
        return Status(READY, f"Depth {held['depth_mm']:g} mm in {held['hours']:g} h, {pattern}")
    if kind == KIND_DEPTH_GRID:
        pattern = table_rows.pattern_words(held.get("pattern"))
        return Status(READY, f"Depth grid {Path(held['raster']).name} over {held['hours']:g} h, {pattern}")
    if kind == KIND_STEADY:
        return Status(READY, f"Constant rain {held['mm_h']:g} mm/h for {held['hours']:g} h")
    if kind == KIND_TABLE:
        total = sum(row[1] for row in held["rows"])
        return Status(READY, f"Hyetograph of {len(held['rows'])} periods, {total:g} mm")
    if kind == KIND_DESIGN:
        return Status(
            READY, join(f"Design storm {held['depth_mm']:g} mm in {held['hours']:g} h", _reduction(held))
        )
    if kind == KIND_GRID:
        return Status(READY, join(f"Gridded rain from {Path(held['file']).name}", _reduction(held)))
    return Status(READY, "")


def reduction(source: str | None, parts: dict, curves: dict, hms: bool) -> Status:
    """The area reduction (W101): ``parts`` is what the section gives the job builder, ``source`` the rain source."""
    if source == KIND_HMS:
        return Status(READY, "As in the HMS project's meteorologic file")
    if source not in reduction_rows.REDUCED_KINDS:
        return Status(OPTIONAL, reduction_rows.UNUSED_WORDS)
    found = reduction_rows.reduction_problems(parts, source, curves, hms=hms)
    if found and found[0] != reduction_rows.SINGLE_WORDS:  # the study's single-run area is Run's matter
        return Status(MISSING, found[0])
    shown = [
        reduction_rows.words(parts.get(which), which, curves)
        for which in (reduction_rows.LUMPED, reduction_rows.GRID)
        if not parts.get(f"{which}_absent")
    ]
    every = [parts.get(which) for which in (reduction_rows.LUMPED, reduction_rows.GRID) if not parts.get(f"{which}_absent")]
    if all((entry or {}).get("form", reduction_rows.NONE) == reduction_rows.NONE for entry in every):
        return Status(OPTIONAL, "None: the depth falls whole")
    return Status(READY, join(*shown))


def tables(store: dict) -> Status:
    patterns, curves = store.get(table_rows.PATTERNS, {}), store.get(table_rows.CURVES, {})
    for name, pattern in sorted(patterns.items()):
        found = table_rows.pattern_problems(name, pattern)
        if found:
            return Status(MISSING, found[0])
    for name, curve in sorted(curves.items()):
        found = table_rows.curve_problems(name, curve)
        if found:
            return Status(MISSING, found[0])
    if not patterns and not curves:
        return Status(OPTIONAL, "None: patterns are uniform or an SCS type, and no area reduction reads a curve")
    count = lambda n, word: f"{n} {word}{'s' if n != 1 else ''}"  # noqa: E731
    return Status(READY, join(count(len(patterns), "pattern"), count(len(curves), "curve")))


def structures(
    layers: dict[str, str], no_elevation: list[str], dam_words: list[str], dams_set: int, breaches: int
) -> Status:
    """``layers``: label of each kind with a layer chosen, to the layer's name; ``no_elevation``: labels of kinds that
    need an elevation and have neither a field nor Z values."""
    if no_elevation:
        return Status(
            MISSING, f"{no_elevation[0]} need an elevation: choose a field, or use a layer with Z values."
        )
    if dam_words:
        return Status(MISSING, dam_words[0])
    if not layers and not breaches:
        return Status(OPTIONAL, "None: the terrain as the DEM has it")
    parts = [", ".join(layers), f"{dams_set} dam start{'s' if dams_set > 1 else ''} set" if dams_set else ""]
    return Status(READY, join(*parts, f"{breaches} breach{'es' if breaches > 1 else ''}" if breaches else ""))


def boundaries(layer: str | None, rows: list[tuple[str, str | None]], file_kinds: tuple[str, ...]) -> Status:
    """``rows``: each line's kind and hydrograph file."""
    if layer is None or not rows:
        return Status(OPTIONAL, "None: every edge is a wall, so water cannot leave the domain")
    unfiled = [str(n) for n, (kind, file) in enumerate(rows, start=1) if kind in file_kinds and not file]
    if unfiled:
        return Status(
            MISSING,
            f"Boundary line {', '.join(unfiled)}: a flow line needs its hydrograph file in the table.",
        )
    kinds = [kind for kind, _file in rows]
    counted = ", ".join(f"{kinds.count(kind)} {kind}" for kind in dict.fromkeys(kinds))
    return Status(READY, join(f"{len(rows)} line{'s' if len(rows) > 1 else ''}", counted))


def points(layer: str | None, count: int) -> Status:
    if layer is None:
        return Status(OPTIONAL, "None: no hydrograph or level is recorded during the run")
    return Status(READY, f"{count} lines and points from {layer}")


def gauges(rows: list[tuple[str, str, str]]) -> Status:
    """``rows``: name, record file and what it is compared with, of each flow or level gauge."""
    if not rows:
        return Status(OPTIONAL, "None: the run is compared with no record")
    for name, file, at in rows:
        if not file:
            return Status(MISSING, f"Gauge {name} needs its record file.")
        if not at:
            return Status(MISSING, f"Gauge {name} needs the line, point or element it is compared with.")
    return Status(READY, f"{len(rows)} observed record{'s' if len(rows) > 1 else ''}")


def run(folder: str, pixels: bool) -> Status:
    if not folder:
        return Status(MISSING, "Choose an output folder.")
    return Status(
        READY, join(f"Into {Path(folder).name}", "pixel maps after the run" if pixels else "cell maps only")
    )


def study() -> Status:
    return Status(OPTIONAL, "Design flows by drainage area: one run per storm area, started from here")


def simulation(
    start: str, hours: float, fixed_step: float | None, cfl: float, maps_min: float | None, lumped_min: float | None,
    bounds: tuple[float, float] | None = None,
) -> Status:  # fmt: skip
    """``fixed_step`` is None for the automatic step, whose smallest and largest step are ``bounds``; ``maps_min``
    and ``lumped_min`` are None where the model has no 2D part or no lumped part."""
    problem = start_problem(start)
    if problem:
        return Status(MISSING, problem)
    if bounds is not None and bounds[0] > bounds[1]:
        return Status(MISSING, STEPS_REVERSED)
    if maps_min is None:
        step = maps = ""
    else:
        step = (
            f"fixed step {fixed_step:g} s" if fixed_step is not None else f"automatic step, Courant {cfl:g}"
        )
        maps = f"maps every {maps_min:g} min" if maps_min else "no maps"
    lumped = f"lumped step {lumped_min:g} min" if lumped_min is not None else ""
    return Status(READY, join(f"Starts {start}" if start else "", f"{hours:g} h", step, maps, lumped))
