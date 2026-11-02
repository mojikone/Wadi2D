# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The rows of the mesh lines table, without Qt: what each line asks, what the ladder gives it, and who set it.

A row starts at the finest and coarsest cells and follows them until it is pinned, each size apart: by a field of the
layer, or by the user editing it. A layer with fields ``near_dx``, ``rows`` and ``far_dx`` fills the table by itself.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from .boundary_rows import as_number

LADDER_NOISE = 1e-9
"""As the engine's ``wadi2d.mesh.refine.rung``: a size a whisker under a rung is on it."""
LINE_FIELDS = ("near_dx", "rows", "far_dx")


@dataclass
class LineRow:
    fid: int
    label: str
    near: float
    rows: int
    far: float
    near_pinned: bool = False
    rows_pinned: bool = False
    far_pinned: bool = False


def rung_size(asked: float, finest: float, coarsest: float) -> float:
    """The cell a size gets: down to ``finest`` x 2^n, never coarser than asked, held between the two ends.

    The same arithmetic as the engine's ``rung``, so that the table can answer at every key press; a contract test holds
    the two together, and the preview reports the engine's own numbers.
    """
    if finest <= 0.0 or asked <= 0.0:
        return asked
    top = max(math.floor(math.log2(max(coarsest, finest) / finest) + LADDER_NOISE), 0)
    level = min(max(math.floor(math.log2(asked / finest) + LADDER_NOISE), 0), top)
    return finest * 2**level


def new_row(line: dict, finest: float, coarsest: float, rows: int) -> LineRow:
    """A row for a line seen for the first time. ``line``: fid, label, and the layer's own near_dx, rows and far_dx, if any."""
    near, count, far = (as_number(line.get(key)) for key in LINE_FIELDS)
    return LineRow(
        line["fid"], line["label"], finest if near is None else near, rows if count is None else int(count),
        coarsest if far is None else far, near is not None, count is not None, far is not None,
    )  # fmt: skip


def merge_rows(lines: list[dict], old: list[LineRow], finest: float, coarsest: float, rows: int) -> list[LineRow]:
    """The layer as it is now: rows it still has keep what they were given, new lines start afresh, gone ones go."""
    known = {row.fid: row for row in old}
    out = []
    for line in lines:
        row = known.get(line["fid"])
        if row is None:
            out.append(new_row(line, finest, coarsest, rows))
        else:
            row.label = line["label"]
            out.append(row)
    return out


def follow(rows: list[LineRow], finest: float, coarsest: float) -> None:
    """The finest or the coarsest cell changed: a size nobody set takes it."""
    for row in rows:
        if not row.near_pinned:
            row.near = finest
        if not row.far_pinned:
            row.far = coarsest


def set_near(row: LineRow, value: float) -> None:
    row.near = value
    row.near_pinned = True


def set_rows(row: LineRow, value: float) -> None:
    row.rows = int(value)
    row.rows_pinned = True


def set_far(row: LineRow, value: float) -> None:
    row.far = value
    row.far_pinned = True


def job_properties(row: LineRow) -> dict:
    """What the job needs of a row; the sizes as asked, because the engine does its own rounding and says what it gave."""
    return {"name": row.label, "near_dx": row.near, "rows": row.rows, "far_dx": row.far}


def rounded_note(name: Any, near: float, far: float, finest: float, coarsest: float) -> str:
    """A sentence on what moved on one line, empty when both sizes are on the ladder."""
    moved = [
        f"{word} {asked:g} m becomes {rung_size(asked, finest, coarsest):g} m"
        for word, asked in (("near", near), ("far", far))
        if rung_size(asked, finest, coarsest) != asked
    ]
    return f"{name}: {', '.join(moved)}." if moved else ""


def reversed_note(name: Any, near: float, far: float) -> str:
    """What stops a line whose near cell is the larger, empty when it is not."""
    return f"{name}: the near cell must not be larger than the far cell." if near > far else ""
