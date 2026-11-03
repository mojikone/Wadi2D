"""A job on a generated basin: what runs lumped, what runs on the grid, and the links between them, from ``basin.json``.

The owner's rules (work order item 9), as built here:

- The 2D flow area is always the whole domain.
- A subbasin is lumped by default. One that lacks a parameter runs as rain-on-grid, and the run says what it lacks; the
  job's ``hydrology.subbasins[].parameters`` can complete it without editing the file.
- A lumped polygon masks the rain under it, so a cell never gets two rainfalls (checked in :mod:`wadi2d.engine.rain_once`).
- Where a reach is defined the flow is routed HMS style. Where none is, the junction's water enters the grid at the junction
  and runs over the ground to the next junction: an inflow is built there, and the link below it is cut in the lumped engine.
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
    RESERVOIR,
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
from wadi2d.config.schema import REACH_HMS, Handback, Hydrology, Inflow, RunConfig, Subbasin
from wadi2d.hydrology.model import Basin

MODE_LUMPED, MODE_2D = "lumped", "2d"
LAG_INPUTS = ("curve_number", "flow_length_m", "slope", "slope_10_85")
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
    return refresh(model)


def load_model(h: Hydrology) -> Model:
    """The job's basin model with its overrides."""
    return with_overrides(read_model(h.basin_json), h.subbasins)


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
    model: Model, modes: dict[str, str], basin: Basin, geometry: ModelGeometry, cfg: RunConfig
) -> tuple[list[JunctionPlan], frozenset[tuple[str, str]], list[Inflow], list[Handback]]:
    elements = {e["name"]: e for e in model["elements"]}
    routes: dict[str, JunctionRoute] = junction_routes(model)
    direct_2d: dict[str, list[str]] = {name: [] for name in routes}
    for element in model["elements"]:
        if element["kind"] == SUBBASIN and modes[element["name"]] == MODE_2D:
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
        handback = route.route == ROUTE_REACH and bool(sources)
        plan = JunctionPlan(
            name, element["kind"], route.route, route.reach, route.next_junction, route.reach_missing,
            enters, handback, sources,
        )  # fmt: skip
        plans.append(plan)
        if enters:
            x, y = element["outlet"]
            inflows.append(Inflow(name=name, x=x, y=y, element=name))
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
    basin = engine_basin(model, modes, h.reach_routing)
    geometry = model_geometry(model, path, crs)
    plans, cut, inflows, handbacks = _plan(model, modes, basin, geometry, cfg)
    return GeneratedBasin(path, model, modes, missing, notes, plans, cut, inflows, handbacks)


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
        subbasins.append(
            Subbasin(
                name=name,
                mode=mode,
                outlet=given.outlet if given is not None else None,
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
