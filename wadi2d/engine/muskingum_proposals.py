"""``wadi2d muskingum``: K, X and subreaches proposed for every reach of an HMS basin file or of a generated basin,
without a run (W89).

For the dock's reach table and for a user at a shell. Per reach, the best basis its data allow, in this order:

1. a section and a reference flow the user names: Cunge's K and X at that flow;
2. a section alone: the same at the flow whose wave speed is the reach's index celerity;
3. no section, a mean velocity the user gives: K from the length over 1.5 times it, X a stated default;
4. no section, a length and a slope: K from Kirpich's expression on the reach, X a stated default;
5. nothing of these: no proposal, in words.

A reach the file already routes by Muskingum shows its own numbers beside the proposal. The relations and their
sources are in :mod:`wadi2d.hydrology.muskingum_proposal`. Nothing here changes a job: a proposal becomes a number of
the run only when someone writes it into ``hydrology.muskingum``.

Interface: :func:`propose_reaches`, :func:`proposal_table`.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from wadi2d.hydrology.muskingum_proposal import (
    Proposal,
    at_index_celerity,
    at_reference_flow,
    at_travel_time,
    at_velocity,
)

GENERATED, HMS = "generated", "hms"
SECTION_KEYS = ("length_m", "slope", "manning_n", "bottom_width_m", "side_slope")
NO_PROPOSAL = "No proposal: the reach has no section, no length and slope, and no velocity was given. Give K and X."
BASIS_KIRPICH = "kirpich"


def _propose(
    name: str, known: Mapping[str, Any], dt_minutes: float, flows: Mapping[str, float], velocity_ms: float | None
) -> tuple[Proposal | None, str]:
    """The best proposal ``known`` allows (the order of the module's note), and its words."""
    from dataclasses import replace

    from wadi2d.basin.parameters import kirpich_travel_minutes

    section = [known.get(key) for key in SECTION_KEYS]
    whole = all(value is not None for value in section) and section[0] > 0.0 and section[1] > 0.0 and section[2] > 0.0
    if whole and name in flows:
        proposal = at_reference_flow(*section, flows[name], dt_minutes)
        return proposal, proposal.words
    if whole and known.get("index_celerity"):
        proposal = at_index_celerity(*section, known["index_celerity"], dt_minutes)
        if proposal is not None:
            return proposal, proposal.words
    length, slope = known.get("length_m"), known.get("slope")
    if length and velocity_ms:
        proposal = at_velocity(length, velocity_ms, dt_minutes)
        return proposal, proposal.words
    if length and slope and slope > 0.0:
        minutes = kirpich_travel_minutes(length, slope)
        source = (
            f"No section and no velocity: Kirpich's expression on the reach, L^0.77 / (52 S^0.385) with L "
            f"{length:,.0f} m and S {slope:g} = {minutes:.1f} min, a formula fitted to small basins and not to a "
            "flood wave, so a rough start only."
        )
        proposal = replace(at_travel_time(minutes, dt_minutes, source), basis=BASIS_KIRPICH)
        return proposal, proposal.words
    return None, NO_PROPOSAL


def _row(name: str, method: str, own: dict | None, proposal: Proposal | None, words: str) -> dict[str, Any]:
    return {
        "name": name,
        "method": method,
        "own": own,
        "proposal": None if proposal is None else proposal.as_dict(),
        "words": words,
    }


def _hms_rows(path: Path, dt_minutes: float, flows: Mapping[str, float], velocity_ms: float | None) -> list[dict]:
    from wadi2d.hms import load_basin
    from wadi2d.hms.methods import MuskingumCungeRoute, MuskingumRoute

    rows = []
    for name, element in load_basin(path).reaches.items():
        route = element.route
        known: dict[str, Any] = {}
        own = None
        if isinstance(route, MuskingumCungeRoute):
            known = {
                "length_m": route.length, "slope": route.energy_slope, "manning_n": route.mannings_n,
                "bottom_width_m": route.bottom_width, "side_slope": route.side_slope,
                "index_celerity": route.index_celerity,
            }
        elif isinstance(route, MuskingumRoute):
            own = {"k_hours": route.muskingum_k, "x": route.muskingum_x, "subreaches": route.muskingum_steps or 1}
        proposal, words = _propose(name, known, dt_minutes, flows, velocity_ms)
        if own is not None and proposal is None:
            words = "The file routes this reach by Muskingum with its own K and X; it has no section to propose from."
        rows.append(_row(name, element.route_method or "None", own, proposal, words))
    return rows


def _generated_rows(path: Path, dt_minutes: float, flows: Mapping[str, float], velocity_ms: float | None) -> list[dict]:
    from wadi2d.basin.contract import (
        MUSKINGUM_SUBREACHES,
        REACH,
        ROUTING_KEY,
        ROUTING_MUSKINGUM,
        read_model,
        value_of,
    )

    rows = []
    for element in read_model(path)["elements"]:
        if element["kind"] != REACH:
            continue
        known = {key: value_of(element, key) for key in (*SECTION_KEYS, "index_celerity")}
        own = None
        if value_of(element, "muskingum_k_hours") is not None and value_of(element, "muskingum_x") is not None:
            own = {
                "k_hours": value_of(element, "muskingum_k_hours"), "x": value_of(element, "muskingum_x"),
                "subreaches": int(value_of(element, MUSKINGUM_SUBREACHES) or 1),
            }
        method = "Muskingum" if element.get(ROUTING_KEY) == ROUTING_MUSKINGUM else "Muskingum Cunge"
        proposal, words = _propose(element["name"], known, dt_minutes, flows, velocity_ms)
        rows.append(_row(element["name"], method, own, proposal, words))
    return rows


def propose_reaches(
    basin_file: str | Path,
    dt_minutes: float,
    flows: Mapping[str, float] | None = None,
    velocity_ms: float | None = None,
) -> dict[str, Any]:
    """Every reach of an HMS ``.basin`` file or of a ``basin.json``, with its own Muskingum numbers if it has any and
    a proposal. ``flows`` are reference flows by reach name, m3/s; ``velocity_ms`` a mean velocity for the reaches
    with no section. A reference flow for a name that is no reach is refused."""
    path = Path(basin_file)
    flows = dict(flows or {})
    kind = GENERATED if path.suffix.lower() == ".json" else HMS
    rows = (_generated_rows if kind == GENERATED else _hms_rows)(path, dt_minutes, flows, velocity_ms)
    strangers = sorted(set(flows) - {row["name"] for row in rows})
    if strangers:
        raise ValueError(f"reference flows for {strangers}, not reaches of {path.name}")
    return {"basin": str(path), "kind": kind, "step_minutes": dt_minutes, "reaches": rows}


def proposal_table(found: Mapping[str, Any]) -> str:
    """The proposals as text for a shell: one line of numbers per reach, then its derivation."""
    lines = [f"{found['basin']}: Muskingum K, X and subreaches proposed at a {found['step_minutes']:g} min step"]
    for row in found["reaches"]:
        proposal, own = row["proposal"], row["own"]
        numbers = "no proposal" if proposal is None else (
            f"K {proposal['k_hours']:g} h, X {proposal['x']:g}, {proposal['subreaches']} subreaches"
            + ("" if proposal["stable"] else " (NOT stable at this step)")
        )
        held = "" if own is None else f"; the file's own: K {own['k_hours']:g} h, X {own['x']:g}, {own['subreaches']}"
        lines.append(f"{row['name']} ({row['method']}): {numbers}{held}")
        lines.append(f"    {row['words']}")
    lines.append("A proposal is a start, not a result: nothing is used until it is written into hydrology.muskingum.")
    return "\n".join(lines)
