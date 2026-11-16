"""The lumped part's area-reduction curve read at the entry element's area (W98, his rule of 2026-11-15).

With ``storm.area_reduction.lumped`` a curve, in a run with a 2D part, each lumped subbasin reads the curve at the total
upstream area of the element where its water enters the 2D grid: the inflow's element (a dam, a junction) or the end of
a hand-back's route it lies above, on links the grid does not carry; a subbasin that enters at its own outlet reads its
own area, unless a last point lies at or below it (a dam, or a junction ``hydrology.last_points`` names): then that
last point's area, one factor per dam, because the grid routes it from its outlet and the 2D model cannot run once per
point (W105, his rule of 2026-11-16; :mod:`wadi2d.engine.last_points`). It is found from the network, HMS import and
generated basin alike, and never refused. A subbasin with ``storm_area_km2`` of its own keeps it; one whose water
reaches no entry (a table inflow of its name) reads its own area.

The grid takes the hydrographs of that run. An element above its entry (a dam whose outflow passes another design
point before the grid) is not read at its own area there, so its series of record comes from a lumped-only rerun of the
network above it at its own drainage area, HMS's depth-area practice, as a lumped-only run reads every element
(:mod:`wadi2d.engine.lumped_run`); the hydrograph that run gave the grid is kept beside it (``ENTRY_AREA_KIND``), and
``ENTRY_AREAS_FILE`` says which is which.

Interface: :func:`entry_of`, :func:`subbasin_entry_areas`, :func:`read_areas`, :func:`own_area_runs`,
:func:`entry_record`, :data:`ENTRY_AREAS_FILE`, :data:`ENTRY_AREA_KIND`.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable, Mapping

from wadi2d.hydrology.depth_area import point_storm
from wadi2d.hydrology.model import Basin, TimeGrid
from wadi2d.hydrology.network import LumpedEngine, Run

ENTRY_AREAS_FILE = "lumped_entry_areas.json"
ENTRY_AREA_KIND = "entry_area"
"""The series an element above its entry gave the grid: ``series/entry_area/<element>`` and
``series/entry_area_<element>.csv``, beside its series of record ``network_<element>``."""
SAME_AREA = 1e-9
"""Relative difference under which two drainage areas are one, so no rerun is needed."""


def _walk_above(basin: Basin, element: str, cut: Collection[tuple[str, str]]) -> set[str]:
    """The element and what sends it water; a cut link sends none, because the grid carries that water instead."""
    if not cut:
        return basin.upstream_of(element)
    links = {name: [p for p in parents if (p, name) not in cut] for name, parents in basin.upstream.items()}
    return Basin._walk(links, element)


def entry_of(basin: Basin, entering: Iterable[str], routes=None) -> dict[str, str]:
    """Every element at or above an entry, with the element its water enters the grid at: ``entering`` (the inflows'
    elements and the subbasins entering at their own outlets) and the ends of the hand-backs' routes. Above two
    entries, the nearer one, the smaller drainage area, takes it: its water reaches the grid there first."""
    cut = routes.cut if routes is not None else ()
    ends = [name for name, _second in routes.ends] if routes is not None else []
    area: dict[str, float] = {}
    found: dict[str, str] = {}
    for entry in dict.fromkeys([*entering, *ends]):
        if entry not in basin.elements:
            continue  # refused in words where the run checks its routes
        area[entry] = basin.drainage_area(entry)
        for name in _walk_above(basin, entry, cut):
            if name not in found or area[entry] < area[found[name]]:
                found[name] = entry
    return found


def subbasin_entry_areas(basin: Basin, entry: Mapping[str, str]) -> dict[str, tuple[str, float]]:
    """Each subbasin of the network that reaches an entry, with that entry and its total upstream area, km2."""
    return {name: (entry[name], basin.drainage_area(entry[name])) for name in basin.subbasins if name in entry}


CARRIED, AT_LAST_POINT, OWN_OUTLET, NO_ENTRY = "carried", "last point", "own outlet", "no entry"
"""Why a subbasin reads the curve where it does (:func:`read_areas`)."""


def read_areas(
    basin: Basin, entry: Mapping[str, str], last: Mapping[str, str] | None = None
) -> dict[str, tuple[float, str | None, str]]:
    """Each subbasin, the area the lumped curve reads it at in a run with a 2D part, the element whose drainage area
    that is, and why: carried by the network to an entry, that entry's (W98: the grid takes the entry's own
    hydrograph); entering at its own outlet with a last point at or below it (``last``, :func:`wadi2d.engine.last_points.
    first_last_point`), that last point's (W105: the 2D routing below it runs once); else its own area."""
    last = last or {}
    found = {}
    for name, sub in basin.subbasins.items():
        enters = entry.get(name)
        if enters is not None and enters != name:
            found[name] = (basin.drainage_area(enters), enters, CARRIED)
        elif enters == name and last.get(name, name) != name:
            found[name] = (basin.drainage_area(last[name]), last[name], AT_LAST_POINT)
        elif enters == name:
            found[name] = (basin.drainage_area(name), name, OWN_OUTLET)
        else:
            found[name] = (sub.area_km2, None, NO_ENTRY)
    return found


def needs_own_run(basin: Basin, name: str, entry: Mapping[str, str]) -> bool:
    """An element above its entry, with a drainage area other than the entry's: the grid's run does not read it."""
    if name not in entry or entry[name] == name:
        return False
    own, at = basin.drainage_area(name), basin.drainage_area(entry[name])
    return abs(own - at) > SAME_AREA * max(abs(at), 1.0)


def own_area_runs(
    engine: LumpedEngine,
    rain,
    grid: TimeGrid,
    names: Iterable[str],
    entry: Mapping[str, str],
    routes=None,
) -> dict[str, Run]:
    """For each element of ``names`` above its entry, the network above it rerun lumped with the storm at its own
    drainage area (``rain`` is the lumped rain without the entry areas: a subbasin's own storm area still holds). An
    element a hand-back runs live is left out: its water is the grid's."""
    cut = routes.cut if routes is not None else ()
    live = set(routes.live) if routes is not None else set()
    at_point = point_storm(rain)
    found: dict[str, Run] = {}
    for name in names:
        if name in live or not needs_own_run(engine.basin, name, entry):
            continue
        above = _walk_above(engine.basin, name, cut)
        if above & live:
            continue
        found[name] = engine.run(at_point(name, engine.basin.drainage_area(name)), grid, only=above, cut=cut)
    return found


def entry_record(
    basin: Basin,
    table,
    entry: Mapping[str, str],
    explicit: Mapping[str, float],
    reruns: Iterable[str],
    curve: str | None,
    last: Mapping[str, str] | None = None,
) -> dict:
    """What ``ENTRY_AREAS_FILE`` holds: each subbasin's area and factor and where it came from, and each element whose
    series of record is its own-area rerun. ``last`` is each element's first last point (W105)."""

    def factor(area: float) -> float:
        return round(float(table.factor(area)), 6)

    read = read_areas(basin, entry, last)
    subbasins = []
    for name in basin.subbasins:
        area, at, why = read[name]
        enters = entry.get(name)
        if name in explicit:
            area, source = explicit[name], "its own storm_area_km2"
        elif why == CARRIED:
            source = f"the drainage area of {at}"
        elif why == AT_LAST_POINT:
            source = f"the drainage area of its last point {at}: it enters at its own outlet and the grid routes it there"
        elif why == OWN_OUTLET:
            source = "its own area: it enters at its own outlet"
        else:
            source = "its own area: its water enters the grid at no element"
        row = {"subbasin": name, "enters_at": enters, "storm_area_km2": round(area, 6), "factor": factor(area),
               "read_at": source}  # fmt: skip
        if last:
            row["last_point"] = last.get(name)
            row["at_last_point"] = why == AT_LAST_POINT and name not in explicit
        subbasins.append(row)
    elements = []
    for name in reruns:
        own, at = basin.drainage_area(name), basin.drainage_area(entry[name])
        elements.append({
            "element": name, "enters_at": entry[name],
            "own_area_km2": round(own, 6), "own_factor": factor(own),
            "entry_area_km2": round(at, 6), "entry_factor": factor(at),
            "series_of_record": "network: a lumped-only rerun of the network above it at its own drainage area",
            "grid_series": f"{ENTRY_AREA_KIND}: the run whose water entered the grid, at {entry[name]}'s area",
        })  # fmt: skip
    record = {
        "rule": "the lumped part's curve read at the total upstream area of the element where each subbasin's water "
        "enters the 2D grid; an element above its entry reported at its own drainage area (W98)",
        "curve": curve,
        "subbasins": subbasins,
        "elements": elements,
    }
    if last:
        record["rule"] += (
            "; a subbasin entering at its own outlet read at the drainage area of the first last point at or below "
            "it, one factor per dam, since the 2D routing runs once (W105)"
        )
        record["last_points"] = sorted({point for point in last.values()})
    return record
