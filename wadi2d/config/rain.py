"""Rain patterns, the area reduction split by part, and the job's store of named tables (W95).

Interface: :class:`ArfTableConfig`, :class:`PatternTable`, :class:`StormPattern`, :class:`ArfPart`,
:class:`AreaReduction` (``storm.pattern``, ``storm.area_reduction``), :class:`DataTables` (``data_tables``) and
:func:`resolve_tables`, which replaces every table named by a storm with the table's numbers before the job is
validated, so the run, its hash and ``config.resolved.json`` see numbers and never a dangling name.

The store holds patterns and area-reduction curves by name, in the job (``data_tables.patterns``,
``data_tables.arf_curves``) or in a JSON file beside it (``data_tables.file``, the same two keys). A name in both must
hold the same table; a name the store does not hold stops the job in words.
"""

from __future__ import annotations

import itertools
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

PATTERN_UNIFORM, PATTERN_SCS, PATTERN_TABLE = "uniform", "scs", "table"
SCS_TYPES = ("I", "IA", "II", "III")
SCS_DURATION_MIN = 1440.0
"""The NRCS distributions are 24-hour curves."""
ARF_CURVE, ARF_AREA, ARF_COEFFICIENT = "curve", "area", "coefficient"
PART_LUMPED, PART_GRID = "lumped", "grid"
PERCENT_END, FRACTION_END = 100.0, 1.0
PATTERNS, ARF_CURVES = "patterns", "arf_curves"
"""The two kinds of table in the store, and the keys of a sidecar file."""


class _Part(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


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


class PatternTable(_Part):
    """How a storm's depth falls in time: a dimensionless or cumulative curve, or the share of each period."""

    time: list[float] = Field(min_length=1, description="Times of the table, in time_units from the storm's start")
    depth: list[float] = Field(
        min_length=1,
        description="Depth at each time (form 'cumulative': depth fallen by then, any unit, read as a share of the "
        "last) or in the period that ends there (form 'incremental': read as a share of the sum)",
    )
    time_units: Literal["percent", "fraction", "hours", "minutes"] = Field(
        "percent",
        description="'percent' or 'fraction' of the storm's duration, ending at 100 or 1; 'hours' or 'minutes' from "
        "the start, ending at the storm's duration",
    )
    form: Literal["cumulative", "incremental"] = "cumulative"

    @model_validator(mode="after")
    def _shape(self) -> PatternTable:
        t, d = self.time, self.depth
        if len(t) != len(d):
            raise ValueError("a pattern needs one depth per time")
        if any(b <= a for a, b in itertools.pairwise(t)):
            raise ValueError("a pattern's times must rise")
        if min(d) < 0.0:
            raise ValueError("a pattern's depths cannot go below zero")
        if self.form == "cumulative":
            if len(t) < 2 or t[0] != 0.0 or d[0] != 0.0:
                raise ValueError("a cumulative pattern starts at time 0 with depth 0 and holds two rows at least")
            if any(b < a for a, b in itertools.pairwise(d)) or d[-1] <= 0.0:
                raise ValueError("a cumulative pattern cannot fall, and must end above zero")
        elif t[0] <= 0.0 or sum(d) <= 0.0:
            raise ValueError("an incremental pattern's first period ends after time 0, and its depths hold some rain")
        end = {"percent": PERCENT_END, "fraction": FRACTION_END}.get(self.time_units)
        if end is not None and abs(t[-1] - end) > 1e-9 * end:
            raise ValueError(f"a pattern in {self.time_units} of the duration ends at {end:g}, not {t[-1]:g}")
        return self

    def duration_min(self) -> float | None:
        """The duration a pattern in hours or minutes spans; None for one relative to the storm's duration."""
        scale = {"hours": 60.0, "minutes": 1.0}.get(self.time_units)
        return None if scale is None else self.time[-1] * scale


class StormPattern(_Part):
    """How a depth or a depth grid is spread over the storm's duration."""

    kind: Literal["uniform", "scs", "table"] = Field(
        PATTERN_UNIFORM,
        description="'uniform': a constant rate. 'scs': an NRCS 24-hour distribution (storm.duration_min 1440). "
        "'table': a pattern of data_tables.patterns by name, or given here",
    )
    scs_type: Literal["I", "IA", "II", "III"] | None = Field(None, description="The NRCS type, for kind 'scs'")
    table: str | None = Field(None, description="Name of a pattern in data_tables.patterns, for kind 'table'")
    values: PatternTable | None = Field(
        None, description="The pattern itself, for kind 'table'; filled from the store when the job names one"
    )

    @model_validator(mode="after")
    def _one_source(self) -> StormPattern:
        if self.kind == PATTERN_SCS and (self.scs_type is None or self.table is not None or self.values is not None):
            raise ValueError("an SCS pattern takes scs_type alone")
        if self.kind == PATTERN_TABLE and self.table is None and self.values is None:
            raise ValueError("a table pattern needs the name of a stored pattern (table) or the pattern (values)")
        if self.kind == PATTERN_UNIFORM and any(v is not None for v in (self.scs_type, self.table, self.values)):
            raise ValueError("a uniform pattern takes nothing else")
        if self.kind != PATTERN_SCS and self.scs_type is not None:
            raise ValueError("scs_type is for kind 'scs'")
        return self


class ArfPart(_Part):
    """The area reduction of one part of the model: a curve, a fixed area read on a curve, or a fixed coefficient."""

    form: Literal["curve", "area", "coefficient"] = Field(
        description="'curve': read at each element's own area (lumped; in a run with a 2D part, each subbasin at the "
        "drainage area of the element where its water enters the grid, and one entering at its own outlet at the "
        "first last point's below it, its dam's, hydrology.last_points) or at each run's storm area of a depth-area "
        "study (2D). 'area': read on the curve at area_km2, one factor for the part. 'coefficient': one factor given",
    )
    curve: str | None = Field(None, description="Name of a curve in data_tables.arf_curves")
    table: ArfTableConfig | None = Field(
        None, description="The curve itself; filled from the store when the job names one"
    )
    area_km2: float | None = Field(None, gt=0.0, description="Storm area the curve is read at, for form 'area', km2")
    coefficient: float | None = Field(
        None, gt=0.0, le=1.0, description="The factor, for form 'coefficient': 0.7 is a 30 % reduction"
    )

    @model_validator(mode="after")
    def _form(self) -> ArfPart:
        curve = self.curve is not None or self.table is not None
        if self.form == ARF_COEFFICIENT:
            if self.coefficient is None or curve or self.area_km2 is not None:
                raise ValueError("a coefficient takes coefficient alone: no curve and no area")
            return self
        if not curve:
            raise ValueError(f"form {self.form!r} needs a curve: the name of a stored curve (curve) or the table")
        if self.coefficient is not None:
            raise ValueError(f"form {self.form!r} reads a curve: leave out coefficient, or choose form 'coefficient'")
        if (self.form == ARF_AREA) != (self.area_km2 is not None):
            raise ValueError("form 'area' needs area_km2, and form 'curve' takes none: its areas are the elements' own")
        return self


class AreaReduction(_Part):
    """The area reduction of the lumped part and of the 2D part, set apart; a part left out is not reduced."""

    lumped: ArfPart | None = Field(None, description="Rain on the lumped subbasins")
    grid: ArfPart | None = Field(None, description="Rain on the 2D cells")

    @model_validator(mode="after")
    def _some(self) -> AreaReduction:
        if self.lumped is None and self.grid is None:
            raise ValueError("storm.area_reduction sets neither part: leave it out for no reduction")
        return self


class DataTables(_Part):
    """Named patterns and area-reduction curves, which storms refer to by name (the dock's Data tables section)."""

    file: str | None = Field(
        None, description="A JSON file of more tables, with the keys 'patterns' and 'arf_curves'; relative to the job"
    )
    patterns: dict[str, PatternTable] = {}
    arf_curves: dict[str, ArfTableConfig] = {}


def _plain(value: Any) -> Any:
    """A part of a job as plain data, whether it came as a dict or as a model."""
    if isinstance(value, BaseModel):
        return value.model_dump()
    return value


MODELS: dict[str, type[_Part]] = {PATTERNS: PatternTable, ARF_CURVES: ArfTableConfig}
"""The model of each kind of stored table."""


def _normal(key: str, table: Any) -> dict:
    """A table as its model writes it out, defaults included, so two spellings of one table compare equal."""
    return MODELS[key].model_validate(_plain(table)).model_dump()


def _merged(store: dict, key: str, extra: dict, source: str) -> dict:
    found = {name: _normal(key, table) for name, table in (store.get(key) or {}).items()}
    for name, table in extra.items():
        table = _normal(key, table)
        if name in found and found[name] != table:
            raise ValueError(f"data_tables.{key}: {name!r} is in the job and in {source} with other numbers")
        found[name] = table
    return found


def _sidecar(store: dict) -> dict:
    """The store with its file's tables added; the job's own tables stand beside them, never over them."""
    path = store.get("file")
    if path is None:
        return store
    source = Path(path)
    if not source.is_file():
        raise ValueError(f"data_tables.file not found: {source}")
    tables = json.loads(source.read_text(encoding="utf-8"))
    unknown = set(tables) - {PATTERNS, ARF_CURVES}
    if unknown:
        raise ValueError(f"{source.name}: only 'patterns' and 'arf_curves' belong in a tables file, not {sorted(unknown)}")
    return {
        **store,
        PATTERNS: _merged(store, PATTERNS, tables.get(PATTERNS, {}), source.name),
        ARF_CURVES: _merged(store, ARF_CURVES, tables.get(ARF_CURVES, {}), source.name),
    }


def _named(holder: dict, name_key: str, value_key: str, tables: dict, where: str, key: str) -> dict:
    """``holder`` with the table its ``name_key`` names filled in under ``value_key``."""
    name = holder.get(name_key)
    if name is None:
        return holder
    kind = "pattern" if key == PATTERNS else "curve"
    if name not in tables:
        held = ", ".join(sorted(tables)) or "none"
        raise ValueError(f"{where} names {kind} {name!r}, which data_tables.{key} does not hold (it holds: {held})")
    given = holder.get(value_key)
    if given is not None and _normal(key, given) != tables[name]:
        raise ValueError(f"{where} names {kind} {name!r} and gives other numbers beside it: give one of the two")
    return {**holder, value_key: tables[name]}


def resolve_tables(data: Any) -> Any:
    """A job's raw data with every stored table its storm names filled in. Data that names none comes back as it
    was, so an old job is the job it was."""
    if not isinstance(data, dict):
        return data
    storm = _plain(data.get("storm"))
    raw_store = _plain(data.get("data_tables")) or {}
    names_pattern = isinstance(storm, dict) and isinstance(storm.get("pattern"), (dict, BaseModel))
    names_part = isinstance(storm, dict) and isinstance(storm.get("area_reduction"), (dict, BaseModel))
    if not raw_store.get("file") and not names_pattern and not names_part:
        return data
    store = _sidecar(raw_store)
    out = {**data, "data_tables": store} if raw_store else dict(data)
    if not (names_pattern or names_part):
        return out
    storm = dict(storm)
    patterns = {name: _normal(PATTERNS, t) for name, t in (store.get(PATTERNS) or {}).items()}
    curves = {name: _normal(ARF_CURVES, t) for name, t in (store.get(ARF_CURVES) or {}).items()}
    if names_pattern:
        storm["pattern"] = _named(_plain(storm["pattern"]), "table", "values", patterns, "storm.pattern", PATTERNS)
    if names_part:
        reduction = dict(_plain(storm["area_reduction"]))
        for part in (PART_LUMPED, PART_GRID):
            if reduction.get(part) is not None:
                where = f"storm.area_reduction.{part}"
                reduction[part] = _named(_plain(reduction[part]), "curve", "table", curves, where, ARF_CURVES)
        storm["area_reduction"] = reduction
    out["storm"] = storm
    return out


def absolute_store(data: Any, base: Path) -> Any:
    """A job's raw data with ``data_tables.file`` made absolute against the job's folder."""
    if not isinstance(data, dict) or not isinstance(data.get("data_tables"), dict):
        return data
    path = data["data_tables"].get("file")
    if path is None or Path(path).is_absolute():
        return data
    return {**data, "data_tables": {**data["data_tables"], "file": str((base / path).resolve())}}
