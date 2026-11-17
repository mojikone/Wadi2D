"""A job on a generated basin: what runs lumped, what runs on the grid, and the links between them, from ``basin.json``.

The owner's rules (work order item 9), as built here:

- The 2D flow area is always the whole domain.
- A subbasin is lumped by default. One that lacks a parameter runs as rain-on-grid, and the run says what it lacks; the
  job's ``hydrology.subbasins[].parameters`` can complete it without editing the file.
- A lumped polygon masks the rain under it, so a cell never gets two rainfalls (checked in :mod:`wadi2d.engine.rain_once`).
- Where a reach is defined the flow is routed HMS style. Where none is, the junction's water enters the grid at the junction
  and runs over the ground to the next junction: an inflow is built there, and the link below it is cut in the lumped engine.
  A junction built on a design line has an ``entry: wadi`` inflow, so it enters up the wadi, clear above the line
  (W41); every other inflow enters at its junction.
- A design line whose junction sends its water down a reach reads that water from the network
  (:mod:`wadi2d.engine.design_lines`).
- A reach-routed hydrograph stays out of the grid until the end of its reach. 2D flow that reaches a junction with a reach
  below leaves the grid at a hand-back line built there (the link of `W25`), into that junction; the lumped water above the
  junction stays in the network, because the routes already say what is on the grid.

The user types nothing: inflows and hand-backs come from the routes, and the resolved job, written beside the results,
carries them in full.

Interface: :func:`resolve`, :func:`generated_basin`, :func:`engine_basin`, :class:`GeneratedBasin`, :class:`JunctionPlan`.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from wadi2d.basin.contract import (
    MUSKINGUM_SUBREACHES,
    REACH,
    RESERVOIR,
    ROUTING_KEY,
    ROUTING_MUSKINGUM,
    SOURCE_DERIVED,
    SOURCE_JOB,
    SUBBASIN,
    Element,
    Model,
    parameter,
    read_model,
    refresh,
    value_of,
)
from wadi2d.basin.geometry import ModelGeometry, first_direction, model_geometry
from wadi2d.basin.loader import load_network
from wadi2d.basin.routes import ROUTE_NONE, ROUTE_REACH, JunctionRoute, junction_routes
from wadi2d.config.schema import (
    ENTRY_EDGE,
    ENTRY_POINT,
    ENTRY_WADI,
    REACH_HMS,
    REACH_MUSKINGUM,
    Handback,
    Hydrology,
    Inflow,
    MuskingumReach,
    RunConfig,
    Subbasin,
)
from wadi2d.hydrology.model import Basin

MODE_LUMPED, MODE_2D = "lumped", "2d"
LAG_INPUTS = ("curve_number", "flow_length_m", "slope", "slope_10_85")
TC_INPUTS = ("flow_length_m", "slope_10_85")
"""A subbasin's Kirpich tc follows these two (W64)."""
"""An override of one of these re-derives a derived lag; a lag the user or the terrain gave stays."""
JUNCTION_SHIFT_CELLS = 1.0
"""A built hand-back line sits this far down the reach from a junction: on the reach, clear of the confluence."""
RESERVOIR_SHIFT_CELLS = -3.0
"""And this far up from a dam's axis, so 2D water enters the pool before the crest faces of the grid."""


@dataclass(frozen=True)
class JunctionPlan:
    """One junction of the run: its route, and what the grid does there."""

    junction: str
    kind: str
    route: str
    reach: str | None
    next_junction: str | None
    reach_missing: tuple[str, ...]
    enters_2d: bool
    """Its network outflow enters the grid here and runs over the ground to the next junction."""
    handback: bool
    """A line here takes 2D flow into it and the reach below."""
    two_d_sources: tuple[str, ...]
    """Where 2D water can come from: 2D subbasins draining here, junctions above whose water is on the grid."""


@dataclass
class GeneratedBasin:
    """A job's generated basin, resolved."""

    path: Path
    model: Model
    modes: dict[str, str]
    missing: dict[str, list[str]]
    notes: list[str]
    junctions: list[JunctionPlan]
    cut: frozenset[tuple[str, str]]
    inflows: list[Inflow]
    handbacks: list[Handback]
    last_point_of: dict[str, str] | None = None
    """Under a hybrid rule (``hydrology.generated_entry``, W106): every element at or above a last point, with the
    first last point at or below it, read on the whole file; None under 'routes'."""
    topology: Model | None = None
    """The whole file's model under a hybrid rule, whose drainage areas the area reduction reads; ``model`` is what
    the rule leaves lumped."""

    def report(self) -> dict:
        """What the run says about the basin, for ``progress.jsonl`` and the dock."""
        return {
            "junctions": [_plain(asdict(j)) for j in self.junctions],
            "incomplete": [{"name": name, "missing": lacks} for name, lacks in self.missing.items()],
            "lumped": [name for name, mode in self.modes.items() if mode == MODE_LUMPED],
            "two_d": [name for name, mode in self.modes.items() if mode == MODE_2D],
            "inflows": [i.name for i in self.inflows],
            "handbacks": [h.name for h in self.handbacks],
        }


def _plain(data: dict) -> dict:
    """Tuples as lists, so the event and the file read the same."""
    return {key: list(value) if isinstance(value, tuple) else value for key, value in data.items()}


def with_overrides(model: Model, subbasins: list[Subbasin]) -> Model:
    """The model with the job's values in place of the file's, marked as the job's, then refreshed."""
    elements = {e["name"]: e for e in model["elements"]}
    for sub in subbasins:
        element = elements.get(sub.name)
        if element is None or element["kind"] != SUBBASIN:
            raise ValueError(f"hydrology.subbasins names {sub.name}, which is not a subbasin of basin.json")
        for key, value in (sub.parameters or {}).items():
            element["parameters"][key] = parameter(value, SOURCE_JOB)
            lag = element["parameters"].get("lag_minutes")
            if key in LAG_INPUTS and lag is not None and lag["source"] == SOURCE_DERIVED:
                element["parameters"]["lag_minutes"] = parameter(None, SOURCE_DERIVED)
            tc = element["parameters"].get("tc_minutes")
            if key in TC_INPUTS and tc is not None and tc["source"] == SOURCE_DERIVED:
                element["parameters"]["tc_minutes"] = parameter(None, SOURCE_DERIVED)
    return refresh(model)


def with_reach_routing(model: Model, reach_routing: str, rows: list[MuskingumReach]) -> Model:
    """The model as the job routes its reaches (W89). Under 'muskingum' every reach is a Muskingum reach, with the
    job's K, X and subreaches where it gives them and the file's own where not; one with neither then lacks them,
    and the rule for an incomplete reach applies: it is left out and named, its water running on the 2D grid."""
    if reach_routing != REACH_MUSKINGUM:
        return model
    reaches = {e["name"]: e for e in model["elements"] if e["kind"] == REACH}
    strangers = sorted({row.reach for row in rows} - set(reaches))
    if strangers:
        raise ValueError(f"hydrology.muskingum names {strangers}, not reaches of basin.json")
    for element in reaches.values():
        element[ROUTING_KEY] = ROUTING_MUSKINGUM
    for row in rows:
        values = {"muskingum_k_hours": row.k_hours, "muskingum_x": row.x, MUSKINGUM_SUBREACHES: row.subreaches}
        for key, value in values.items():
            reaches[row.reach]["parameters"][key] = parameter(value, SOURCE_JOB)
    return refresh(model)


def dry_start(model: Model) -> Model:
    """A reservoir whose start the file only derived starts empty, at the foot of its table, in place.

    Files written before 2026-11-07 derived the lowest spillway crest; a design run reads a dam's attenuation from an
    empty pool, and a scenario names its level in ``RunConfig.dam_levels`` (his decision of 2026-11-07).
    """
    for element in model["elements"]:
        start = element["parameters"].get("initial_elevation_m")
        table = value_of(element, "elevation_m") if element["kind"] == RESERVOIR else None
        if table and start is not None and start["source"] == SOURCE_DERIVED:
            start["value"] = table[0]
    return model


def with_reach_manning(model: Model, every: float | None, by_reach: dict[str, float]) -> Model:
    """The model with the job's Manning n on its reaches (W106): ``every`` on each, ``by_reach`` over it, marked as the
    job's; a celerity derived from the file's n is derived again. Nothing given leaves the model as it was."""
    if every is None and not by_reach:
        return model
    reaches = {e["name"]: e for e in model["elements"] if e["kind"] == REACH}
    strangers = sorted(set(by_reach) - set(reaches))
    if strangers:
        raise ValueError(f"hydrology.reach_manning names {strangers}, not reaches of basin.json")
    for name, element in reaches.items():
        n = by_reach.get(name, every)
        if n is None:
            continue
        element["parameters"]["manning_n"] = parameter(n, SOURCE_JOB)
        celerity = element["parameters"].get("index_celerity")
        if celerity is not None and celerity["source"] == SOURCE_DERIVED:
            element["parameters"]["index_celerity"] = parameter(None, SOURCE_DERIVED)
    return refresh(model)


def load_model(h: Hydrology) -> Model:
    """The job's basin model with its overrides; a derived reservoir start is the empty pool."""
    model = with_overrides(dry_start(read_model(h.basin_json)), h.subbasins)
    model = with_reach_manning(model, h.reach_manning_n, h.reach_manning)
    return with_reach_routing(model, h.reach_routing, h.muskingum)


def _modes(model: Model, subbasins: list[Subbasin]) -> tuple[dict[str, str], dict[str, list[str]], list[str]]:
    """Every subbasin's mode, every incomplete element's lacks, and the warnings, in words."""
    asked = {s.name: s.mode for s in subbasins}
    modes: dict[str, str] = {}
    missing: dict[str, list[str]] = {}
    notes: list[str] = []
    for element in model["elements"]:
        name, lacks = element["name"], list(element["missing"])
        if lacks:
            missing[name] = lacks
        if element["kind"] != SUBBASIN:
            if lacks and element["kind"] == RESERVOIR:
                notes.append(f"reservoir {name} lacks {', '.join(lacks)}: it passes its inflow on as a junction")
            elif lacks:
                above = [e["name"] for e in model["elements"] if e["downstream"] == name and e["kind"] != SUBBASIN]
                notes.append(
                    f"reach {name} lacks {', '.join(lacks)}: the water of {', '.join(above) or 'the junction above'} "
                    "enters the 2D grid there and runs over the ground instead"
                )
            continue
        if lacks:
            modes[name] = MODE_2D
            said = ", not lumped as asked" if asked.get(name) == MODE_LUMPED else ""
            notes.append(
                f"subbasin {name} lacks {', '.join(lacks)}: it runs as rain-on-grid{said}; fill the value in basin.json "
                "or give it in hydrology.subbasins[].parameters"
            )
        else:
            modes[name] = asked.get(name, MODE_LUMPED)
    return modes, missing, notes


GEN_ROUTES, GEN_LAST_POINTS, GEN_OUTLETS = "routes", "last_points", "outlets"
"""``hydrology.generated_entry``: as always; Hybrid Lumped's rule; Hybrid 2D's rule (W106)."""


def _drainage(element: Element) -> float:
    value = value_of(element, "drainage_area_km2")
    if value is None:
        value = value_of(element, "area_km2")
    return float(value) if value is not None else float("inf")


def above_last_points(model: Model, given: list[str] | None) -> dict[str, str]:
    """Every element of the file at or above a last point, with the first last point at or below it: of two, the one of
    smaller drainage area, which its water reaches first. The last points are every dam (reservoir) of the file when
    ``given`` is None, as the engine's default (W105), read on the file so a dam without a rating counts too.
    ``ValueError`` in words for a name the file does not hold."""
    elements = {e["name"]: e for e in model["elements"]}
    if given is None:
        points = [name for name, e in elements.items() if e["kind"] == RESERVOIR]
    else:
        unknown = [name for name in given if name not in elements]
        if unknown:
            raise ValueError(
                f"hydrology.last_points names {', '.join(unknown)}, which the generated basin does not hold: a last "
                "point is one of its dams or junctions"
            )
        points = list(dict.fromkeys(given))
    upstream: dict[str, list[str]] = {}
    for name, element in elements.items():
        if element["downstream"] is not None:
            upstream.setdefault(element["downstream"], []).append(name)
    found: dict[str, str] = {}
    for point in points:
        todo, seen = [point], set()
        while todo:
            name = todo.pop()
            if name in seen:
                continue
            seen.add(name)
            held = found.get(name)
            if held is None or (held != name and (point == name or _drainage(elements[point]) < _drainage(elements[held]))):
                found[name] = point
            todo.extend(upstream.get(name, []))
    return found


def hybrid_model(
    model: Model, modes: dict[str, str], rule: str, given: list[str] | None
) -> tuple[Model, dict[str, str], list[str], dict[str, str]]:
    """What a hybrid rule leaves of a generated basin (W106, his rules of record): the model the lumped engine runs,
    every subbasin's mode, the words, and each element above a last point with its first last point.

    Both rules: a subbasin at or above a last point keeps its mode; one below every last point rains on the grid.
    'last_points' (Hybrid Lumped): the elements at or above a last point stay, each linked as in the file, the lowest
    last point on each way an outlet of the network, whose water enters the grid there; nothing below is lumped.
    'outlets' (Hybrid 2D): only the subbasins stay, each an outlet of its own; no reach or reservoir is routed."""
    above = above_last_points(model, given)
    new_modes = dict(modes)
    below = sorted(n for n, m in modes.items() if m == MODE_LUMPED and n not in above)
    for name in below:
        new_modes[name] = MODE_2D
    words = []
    if below:
        words.append(f"{len(below)} subbasins lie below every last point and rain on the grid: {', '.join(below)}")
    kept = []
    for element in model["elements"]:
        if rule == GEN_OUTLETS and element["kind"] != SUBBASIN:
            continue
        if rule == GEN_LAST_POINTS and element["kind"] != SUBBASIN and element["name"] not in above:
            continue
        copy = dict(element)
        if rule == GEN_OUTLETS or copy["downstream"] not in above or element["name"] not in above:
            copy["downstream"] = None
        kept.append(copy)
    lumped = sorted(n for n, m in new_modes.items() if m == MODE_LUMPED)
    if rule == GEN_OUTLETS:
        words.append(
            f"Hybrid 2D: {len(lumped)} lumped subbasins enter the grid at their own outlets; no reach or reservoir is "
            "routed lumped, the grid routes their water"
        )
    else:
        ends = sorted({point for name, point in above.items() if name == point and model_downstream_out(model, name, above)})
        words.append(
            f"Hybrid Lumped: the lumped network ends at {', '.join(ends) or 'no last point'}; its water enters the grid "
            "there, and nothing below is lumped"
        )
    return {**model, "elements": kept}, new_modes, words, above


def model_downstream_out(model: Model, name: str, above: dict[str, str]) -> bool:
    """Whether an element's water leaves the elements above the last points: it is the lowest last point there."""
    element = next(e for e in model["elements"] if e["name"] == name)
    return element["downstream"] is None or element["downstream"] not in above


class AreasOfFile:
    """A lumped basin's subbasins with the drainage areas of the whole file (W106): under the 'outlets' rule the
    engine's basin holds the subbasins alone, so a last point's area is read where the file measured it."""

    def __init__(self, basin: Basin, whole: Model) -> None:
        self.basin = basin
        self.subbasins = basin.subbasins
        self.areas = {e["name"]: _drainage(e) for e in whole["elements"]}

    def drainage_area(self, name: str) -> float:
        if name in self.basin.elements:
            return self.basin.drainage_area(name)
        return self.areas[name]


def engine_basin(model: Model, modes: dict[str, str], reach_routing: str = REACH_HMS) -> Basin:
    """The lumped engine's basin: every element that can run, the 2D subbasins left out (their water is on the grid)."""
    kept = [e for e in model["elements"] if not (e["kind"] == SUBBASIN and modes.get(e["name"]) == MODE_2D)]
    return load_network({**model, "elements": kept}, skip_incomplete=True, reach_routing=reach_routing)


def _line(junction: Element, reach: Element, geometry: ModelGeometry, cfg: RunConfig) -> list[tuple[float, float]]:
    """A straight line across the valley at a junction, square to the reach below, long enough to span its section."""
    settings, dx = cfg.basin, cfg.grid.dx
    dx_, dy_ = first_direction(geometry.reaches[reach["name"]])
    section = value_of(reach, "section")
    width = float(section["width_m"][-1]) if section else 0.0
    length = max(settings.handback_span * width, settings.handback_min_cells * dx)
    shift = (RESERVOIR_SHIFT_CELLS if junction["kind"] == RESERVOIR else JUNCTION_SHIFT_CELLS) * dx
    x, y = junction["outlet"]
    cx, cy = x + shift * dx_, y + shift * dy_
    nx, ny = -dy_, dx_
    half = 0.5 * length
    return [(cx - half * nx, cy - half * ny), (cx + half * nx, cy + half * ny)]


def _plan(
    model: Model, modes: dict[str, str], basin: Basin, geometry: ModelGeometry, cfg: RunConfig, rule: str = GEN_ROUTES
) -> tuple[list[JunctionPlan], frozenset[tuple[str, str]], list[Inflow], list[Handback]]:
    """Under 'last_points' (W106) a junction joined to the next with no reach passes its water on, lumped, and the
    network's ends (its lowest last points) enter on the edge of the catchments the mesh leaves out."""
    elements = {e["name"]: e for e in model["elements"]}
    routes: dict[str, JunctionRoute] = junction_routes(model)
    direct_2d: dict[str, list[str]] = {name: [] for name in routes}
    for element in model["elements"]:
        if element["kind"] == SUBBASIN and modes[element["name"]] == MODE_2D and element["downstream"] in direct_2d:
            direct_2d[element["downstream"]].append(element["name"])
    feeding: dict[str, list[str]] = {name: [] for name in routes}
    for name, route in routes.items():
        if route.route == ROUTE_NONE and route.next_junction is not None:
            feeding[route.next_junction].append(name)
    plans: list[JunctionPlan] = []
    cut: set[tuple[str, str]] = set()
    inflows: list[Inflow] = []
    handbacks: list[Handback] = []
    for name, route in routes.items():
        element = elements[name]
        sources = tuple(direct_2d[name] + feeding[name])
        enters = route.route == ROUTE_NONE
        if rule == GEN_LAST_POINTS:  # on to the next junction, lumped, unless a reach there cannot run
            enters = enters and (route.next_junction is None or route.reach is not None)
        handback = route.route == ROUTE_REACH and bool(sources)
        plan = JunctionPlan(
            name, element["kind"], route.route, route.reach, route.next_junction, route.reach_missing,
            enters, handback, sources,
        )  # fmt: skip
        plans.append(plan)
        if enters:
            x, y = element["outlet"]
            on_line = bool((element.get("pour_point") or {}).get("line"))
            entry = ENTRY_WADI if on_line else ENTRY_POINT  # a junction on a design line enters above it
            if rule == GEN_LAST_POINTS and route.next_junction is None:
                entry = ENTRY_EDGE  # a last point: on the edge of the catchments left out, the wadi just below (W105)
            inflows.append(Inflow(name=name, x=x, y=y, element=name, entry=entry))
            below = basin.elements[name].downstream
            if below is not None:
                cut.add((name, below))
        if handback:
            line = _line(element, elements[route.reach], geometry, cfg)
            handbacks.append(Handback(name=name, coordinates=line, element=name))
    return plans, frozenset(cut), inflows, handbacks


def generated_basin(cfg: RunConfig, crs: str = "") -> GeneratedBasin:
    """Everything a run on a generated basin decides before it starts."""
    h = cfg.hydrology
    if h.basin_json is None:
        raise ValueError("the job names no basin: set hydrology.basin_json")
    path = Path(h.basin_json)
    model = load_model(h)
    modes, missing, notes = _modes(model, h.subbasins)
    rule = h.generated_entry
    whole, last_point_of = None, None
    if rule != GEN_ROUTES:
        whole = model
        model, modes, words, last_point_of = hybrid_model(model, modes, rule, h.last_points)
        notes += words
    basin = engine_basin(model, modes, h.reach_routing)
    geometry = model_geometry(model, path, crs)
    plans, cut, inflows, handbacks = _plan(model, modes, basin, geometry, cfg, rule)
    return GeneratedBasin(path, model, modes, missing, notes, plans, cut, inflows, handbacks, last_point_of, whole)


def resolve(cfg: RunConfig, crs: str = "") -> tuple[RunConfig, GeneratedBasin]:
    """The job as the engine runs it: every subbasin with its mode, the inflows and hand-backs the routes give.

    Calling it on a job already resolved adds nothing: the built inflows and lines are known by name and element.
    """
    gen = generated_basin(cfg, crs)
    h = cfg.hydrology
    asked = {s.name: s for s in h.subbasins}
    elements = {e["name"]: e for e in gen.model["elements"]}
    subbasins = []
    for name, mode in gen.modes.items():
        given = asked.get(name)
        curve = given.curve_number if given is not None and given.curve_number is not None else None
        if mode == MODE_2D and curve is None:
            curve = value_of(elements[name], "curve_number")
        outlet = given.outlet if given is not None else None
        entry = given.entry if given is not None else ENTRY_POINT
        if h.generated_entry == GEN_OUTLETS and mode == MODE_LUMPED and outlet is None:
            outlet = tuple(elements[name]["outlet"])  # Hybrid 2D: at its own outlet, inside its own polygon (W106)
            entry = ENTRY_WADI
        subbasins.append(
            Subbasin(
                name=name,
                mode=mode,
                outlet=outlet,
                entry=entry,
                curve_number=curve,
                parameters=given.parameters if given is not None else None,
            )
        )
    known_inflows = {(i.name, i.element) for i in h.inflows}
    known_lines = {(line.name, line.element) for line in h.handbacks}
    hydrology = h.model_copy(
        update={
            "subbasins": subbasins,
            "inflows": [*h.inflows, *(i for i in gen.inflows if (i.name, i.element) not in known_inflows)],
            "handbacks": [*h.handbacks, *(x for x in gen.handbacks if (x.name, x.element) not in known_lines)],
        }
    )
    return cfg.model_copy(update={"hydrology": hydrology}), gen
