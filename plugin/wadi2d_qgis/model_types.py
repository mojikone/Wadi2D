# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The four model types of the dock (W99): what each means, shows, sets and needs. No Qt here.

The keys are the engine's ``run.model_type`` (W96, ``wadi2d/config/model_type.py``); a contract test holds them
together. A type decides which sections show, sets the three Hydrology choices it leaves no room for, and is written
into the job. ``None`` is the dock as it was before W99: every section, and a job that names no type.

Interface: :data:`TYPES` (key to :class:`ModelType`), :func:`sections_shown`, :func:`apply_type` (the type's own values
laid over the dock's), :func:`type_problems`, :func:`inferred` (the type a model with none runs as, the engine's rule).
"""

from __future__ import annotations

from dataclasses import dataclass

MODEL_TYPE = "run.model_type"
TWO_D, LUMPED, HYBRID_LUMPED, HYBRID_2D = "2d", "lumped", "hybrid_lumped", "hybrid_2d"
ALL_SECTIONS = (
    "terrain", "mesh", "hydrology", "storm", "structures", "boundaries", "points", "gauges", "simulation", "run",
    "study",
)  # fmt: skip
"""Section keys in the dock's order; a contract test holds them to the dock's own."""
ENTRY_OUTLET = "outlet"


@dataclass(frozen=True)
class ModelType:
    key: str
    title: str
    badge: str
    meaning: str
    """One line, as the start page says it."""
    parts: tuple[tuple[str, bool], ...]
    """What is lumped (True) and what is 2D (False): the small tags of the card."""
    hidden: tuple[str, ...] = ()
    """Sections a model of this type has no use for."""
    needs_lumped: bool = False
    """Whether it needs a lumped network: an HMS project or a generated basin."""


TYPES = {
    kind.key: kind
    for kind in (
        ModelType(
            TWO_D,
            "2D",
            "2D",
            "Rain on the grid everywhere: hills, wadis, dams and plain all in 2D.",
            (("Hills 2D", False), ("Routing 2D", False), ("Plain 2D", False)),
        ),
        ModelType(
            LUMPED,
            "Lumped",
            "LUMP",
            "The HMS way: subbasins, reaches and reservoirs, no 2D model.",
            (("Hills lumped", True), ("Routing lumped", True)),
            hidden=("mesh", "boundaries", "study"),
            needs_lumped=True,
        ),
        ModelType(
            HYBRID_LUMPED,
            "Hybrid Lumped",
            "HYB-L",
            "Lumped catchments left out of the mesh, entering the 2D model at their outlets; rain on the grid on the rest.",
            (("Hills lumped", True), ("Routing lumped", True), ("Plain 2D", False)),
            needs_lumped=True,
        ),
        ModelType(
            HYBRID_2D,
            "Hybrid 2D",
            "HYB-2D",
            "The same catchments lumped, their water routed on the 2D mesh with dams as 2D pools; rain on the grid "
            "on the rest.",
            (("Hills lumped", True), ("Routing 2D", False), ("Plain 2D", False)),
            needs_lumped=True,
        ),
    )
}
NO_TYPE_TITLE = "All sections"
NO_TYPE_BADGE = "ALL"
NO_TYPE_MEANING = (
    "Every section, as the dock was: the job names no model type and the engine reads it from the job."
)
NEEDS_LUMPED = (
    "A {title} model needs its lumped catchments: choose an HMS project or generate the basin, in Hydrology."
)
UNUSED_LUMPED = (
    "The HMS project or generated basin set in Hydrology is not used: a 2D model has no lumped part."
)


def title_of(kind: str | None) -> str:
    return TYPES[kind].title if kind in TYPES else NO_TYPE_TITLE


def sections_shown(kind: str | None, show_all: bool = False) -> tuple[str, ...]:
    """The keys of the sections a model of this type shows; all of them with no type or with the switch on."""
    if show_all or kind not in TYPES:
        return ALL_SECTIONS
    return tuple(key for key in ALL_SECTIONS if key not in TYPES[kind].hidden)


def has_lumped(values: dict) -> bool:
    return bool(values.get("hms") or values.get("basin"))


def inferred(values: dict) -> str:
    """The type a model that names none runs as, by the engine's rule: lumped alone, hybrid with the catchments left
    out or kept, else 2D."""
    if values.get("lumped_only"):
        return LUMPED
    if has_lumped(values):
        return HYBRID_LUMPED if values.get("exclude_lumped") else HYBRID_2D
    return TWO_D


def apply_type(values: dict, kind: str | None) -> dict:
    """The dock's values with what the type sets laid over them, and the type itself for the job.

    A 2D model has no lumped part, so an HMS project or basin still chosen in Hydrology stays out of the job; a
    Lumped model is the lumped network alone; the hybrids leave the catchments out of the mesh or keep them, and
    Hybrid 2D enters at the outlets so the 2D model routes. The mode of each subbasin stays the table's. Nothing in
    the dock's widgets is changed by this.
    """
    if kind not in TYPES or not values:
        return values
    out = {**values, "model_type": kind}
    if kind == TWO_D:
        for key in ("hms", "basin", "lumped_entry", "lumped_only", "arf_by_element", "muskingum"):
            out.pop(key, None)
        out["handbacks"] = []
        out["exclude_lumped"] = False
        return out
    out["lumped_only"] = kind == LUMPED
    out["exclude_lumped"] = kind == HYBRID_LUMPED
    if kind == LUMPED:
        out.pop("lumped_entry", None)
    else:
        out["arf_by_element"] = False
    if kind == HYBRID_2D:
        out["lumped_entry"] = ENTRY_OUTLET
    return out


def type_problems(values: dict) -> list[str]:
    """What stops a run of the type the values name, in plain words."""
    kind = values.get("model_type")
    if kind in TYPES and TYPES[kind].needs_lumped and not has_lumped(values):
        return [NEEDS_LUMPED.format(title=TYPES[kind].title)]
    return []


def type_notes(dock_values: dict, kind: str | None) -> list[str]:
    """What the type leaves unused of what the dock holds, so nothing set is dropped without a word."""
    return [UNUSED_LUMPED] if kind == TWO_D and has_lumped(dock_values) else []
