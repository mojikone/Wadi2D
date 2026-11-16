# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The rows of the Boundaries table, without Qt: which line has which kind and value, and who decided it.

A row follows the section's Kind and Value until it is pinned, its kind and its value apart: by a field of the layer, or by the
user editing it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

VALUE_KINDS = ("stage", "normal")
"""The kinds that take a value; ``free`` has none."""
FILE_KINDS = ("flow",)
"""The kinds that take a hydrograph file: HEC-RAS's Flow Hydrograph line (W61)."""
DIRECTIONS = ("auto", "left", "right")
"""Which side a flow line's water goes to, the engine's ``flow.direction`` (W70); ``auto`` is its default."""
MOMENTUM_DEFAULT = True
"""The engine's ``flow.momentum``: the water enters moving (W70)."""


@dataclass
class Row:
    fid: int
    label: str
    kind: str
    value: float | None
    kind_pinned: bool = False
    value_pinned: bool = False
    file: str | None = None
    """The hydrograph of a ``flow`` line: a CSV or DSS file, from the layer's ``file`` field or the table."""
    momentum: bool = MOMENTUM_DEFAULT
    """A ``flow`` line's water enters moving (W70): the layer's ``momentum`` field or the table."""
    direction: str = "auto"
    """The side a ``flow`` line's water goes to (W70): the layer's ``direction`` field or the table."""
    typed: bool = False
    """W101 item 3: the hydrograph is typed in the dock, a flow every ``step_min``, HEC-RAS's way, not a file."""
    step_min: float = 15.0
    flows: list = field(default_factory=list)
    slope: float | None = None
    """The energy slope across the line that shares the flow by normal depth; None is the engine's (0.005)."""


def default_value(kind: str, defaults: dict[str, float]) -> float | None:
    return defaults.get(kind) if kind in VALUE_KINDS else None


def line_label(number: int, name: Any) -> str:
    text = "" if name is None else str(name).strip()
    return text or f"Line {number}"


def as_number(value: Any) -> float | None:
    """What a field holds, as a number; a blank, or text that is none, counts as not set."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def new_row(line: dict, kind: str, value: float | None, defaults: dict[str, float]) -> Row:
    """A row for a line seen for the first time. ``line``: fid, label, and the layer's own kind and value, if any."""
    own_kind = str(line.get("kind") or "").strip().lower()
    own_value = as_number(line.get("value"))
    chosen = own_kind or kind
    if own_value is not None:
        start = own_value
    else:
        start = value if chosen == kind else default_value(chosen, defaults)
    own_file = str(line.get("file") or "").strip() or None
    direction = str(line.get("direction") or "").strip().lower()
    return Row(
        line["fid"], line["label"], chosen, start, bool(own_kind), own_value is not None, own_file,
        as_flag(line.get("momentum"), MOMENTUM_DEFAULT), direction if direction in DIRECTIONS else "auto",
    )  # fmt: skip


def as_flag(value: Any, default: bool) -> bool:
    """A yes-or-no field: blank is the default."""
    if value is None or str(value).strip() == "":
        return default
    return str(value).strip().lower() not in ("0", "false", "no", "off")


def merge_rows(lines: list[dict], old: list[Row], kind: str, value: float | None, defaults: dict[str, float]) -> list[Row]:
    """The layer as it is now: rows it still has keep what they were given, new lines start afresh, gone ones go."""
    known = {row.fid: row for row in old}
    rows = []
    for line in lines:
        row = known.get(line["fid"])
        if row is None:
            rows.append(new_row(line, kind, value, defaults))
        else:
            row.label = line["label"]
            rows.append(row)
    return rows


def follow(rows: list[Row], kind: str, value: float | None) -> None:
    """The section's Kind or Value changed: what is not pinned in each row takes them."""
    for row in rows:
        if not row.kind_pinned:
            row.kind = kind
        if not row.value_pinned and row.kind == kind:
            row.value = value


def set_kind(row: Row, kind: str, defaults: dict[str, float]) -> None:
    """The user chose a kind: the value in the row meant something else, so it starts from the default of the new one."""
    if kind != row.kind:
        row.kind = kind
        row.value = default_value(kind, defaults)
    row.kind_pinned = True
    row.value_pinned = True


def set_value(row: Row, value: float) -> None:
    row.value = value
    row.value_pinned = True


def set_file(row: Row, path: str) -> None:
    row.file = path.strip() or None


def set_momentum(row: Row, on: bool) -> None:
    row.momentum = bool(on)


def set_direction(row: Row, direction: str) -> None:
    row.direction = direction if direction in DIRECTIONS else "auto"


def has_hydrograph(row: Row) -> bool:
    """A flow line with what it brings in: a file, or a typed table of two flows at least at a step above zero."""
    return bool(row.file) if not row.typed else len(row.flows) >= 2 and row.step_min > 0.0


def table_problems(rows: list[Row]) -> list[str]:
    """What is wrong with the typed hydrographs, in words (W101)."""
    found = []
    for number, row in enumerate(rows, start=1):
        if row.kind not in FILE_KINDS or not row.typed:
            continue
        if len(row.flows) < 2 or row.step_min <= 0.0:
            found.append(f"Boundary line {number}: a typed hydrograph needs a step above zero and two flows at least.")
        elif min(row.flows) < 0.0:
            found.append(f"Boundary line {number}: a typed hydrograph's flows cannot go below zero.")
    return found


def job_properties(row: Row) -> dict:
    """What the job builder takes; a flow line's momentum and direction only where they differ from the engine's
    defaults, so a default left alone stays the engine's (the quadtree drops it with a warning, W70)."""
    out = {"kind": row.kind, "value": row.value if row.kind in VALUE_KINDS else None}
    if row.kind in FILE_KINDS and row.typed:  # W101 item 3: HEC-RAS's table of flows at a step
        out["step_s"] = row.step_min * 60.0
        out["flows"] = [float(q) for q in row.flows]
    if row.kind in FILE_KINDS and row.slope is not None:
        out["slope"] = row.slope
    if row.kind in FILE_KINDS:
        out["file"] = None if row.typed else row.file
        if row.momentum != MOMENTUM_DEFAULT:
            out["momentum"] = row.momentum
        if row.direction != "auto":
            out["direction"] = row.direction
    return out
