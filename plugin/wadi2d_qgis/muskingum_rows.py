# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The Hydrology section's reach table for Muskingum routing (W89), without Qt.

One row per reach: a reference flow the user may give, and K, X and subreaches, typed or proposed. The engine proposes
(``wadi2d muskingum``) only when the button is pressed, and a proposal lands in the cells where the user sees it, with
its derivation beside it; the job takes what the cells hold. A row the user typed is never overwritten by a proposal.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

MUSKINGUM = "muskingum"
"""The engine's name of the choice, ``hydrology.reach_routing``."""
MUSKINGUM_ROWS = "hydrology.muskingum"
COLUMNS = ["Reach", "Ref. flow, m3/s", "K, h", "X", "Subreaches", "How it was derived"]
FLOW_COLUMN, K_COLUMN, X_COLUMN, COUNT_COLUMN, WORDS_COLUMN = 1, 2, 3, 4, 5
EDITABLE = (FLOW_COLUMN, K_COLUMN, X_COLUMN, COUNT_COLUMN)
X_RANGE = (0.0, 0.5)
TYPED = "Typed here."
COLUMN_TIPS = {
    FLOW_COLUMN: "Optional. The flow K and X are proposed at: about midway between base flow and the peak of the "
    "flood to be routed (EM 1110-2-1417). Blank proposes at the flow of the reach's index celerity.",
    K_COLUMN: "Muskingum K, the travel time of the flood wave through the reach, hours.",
    X_COLUMN: "Muskingum X, 0 (most attenuation) to 0.5 (none).",
    COUNT_COLUMN: "Equal parts the reach is routed in, about K over the lumped step. A part is stable while "
    "2KX <= step <= 2K(1-X); outside it the run warns and routes as given, as HEC-HMS does.",
}


@dataclass
class ReachRow:
    """One reach. ``proposed`` says the numbers are the engine's proposal, untouched; an edit clears it."""

    name: str
    flow: float | None = None
    k_hours: float | None = None
    x: float | None = None
    subreaches: int | None = None
    words: str = ""
    proposed: bool = False
    problems: list[str] = field(default_factory=list)
    """What is wrong with K, X or the subreaches; a row with any stays out of the job."""
    flow_problem: str = ""
    """What is wrong with the reference flow typed; the flow is then not used, and the row is not held back."""

    def complete(self) -> bool:
        return self.k_hours is not None and self.x is not None and not self.problems

    def empty(self) -> bool:
        return self.k_hours is None and self.x is None and self.subreaches is None


def hms_reaches(basin_file: str | Path) -> list[str]:
    """The reaches of a ``.basin`` file, in file order."""
    text = Path(basin_file).read_text(encoding="utf-8", errors="replace")
    return re.findall(r"^Reach:\s*(.+?)\s*$", text, re.MULTILINE)


def model_reaches(model: dict) -> list[str]:
    """The reaches of a generated basin, in file order."""
    return [e["name"] for e in model.get("elements", []) if e.get("kind") == "reach"]


def merge_reaches(names: list[str], old: list[ReachRow]) -> list[ReachRow]:
    """The reaches as they are now; a reach still there keeps its row."""
    known = {row.name: row for row in old}
    return [known.get(name) or ReachRow(name) for name in names]


def _number(text: str) -> float | None:
    cleaned = str(text).strip().replace(",", "")
    return float(cleaned) if cleaned else None


def _set_flow(row: ReachRow, text: str) -> None:
    """The reference flow is only a question to the helper: one that means nothing is left out of the question and
    named, and never keeps the row's K and X from the job."""
    try:
        value = _number(text)
    except ValueError:
        row.flow, row.flow_problem = None, f"Ref. flow: {text!r} is not a number, so none is used"
        return
    if value is not None and value <= 0.0:
        row.flow, row.flow_problem = None, "Ref. flow: above zero, so none is used"
        return
    row.flow, row.flow_problem = value, ""


def set_cell(row: ReachRow, column: int, text: str) -> None:
    """What the user typed into a cell; a number that means nothing stays out and is named in ``problems``."""
    if column == FLOW_COLUMN:
        _set_flow(row, text)
        return
    names = {K_COLUMN: "k_hours", X_COLUMN: "x", COUNT_COLUMN: "subreaches"}
    try:
        value = _number(text)
    except ValueError:
        value, bad = None, f"{COLUMNS[column]}: {text!r} is not a number"
    else:
        bad = None
    if value is not None and column == COUNT_COLUMN:
        if value != int(value):
            value, bad = None, f"Subreaches: {text!r} is not a whole number"
        else:
            value = int(value)
    setattr(row, names[column], value)
    row.proposed = False
    row.words = "" if row.empty() else TYPED
    row.problems = [p for p in row.problems if not p.startswith(COLUMNS[column].split(",")[0])]
    if bad:
        row.problems.append(bad)
    check(row)


def check(row: ReachRow) -> None:
    """The range problems of a row's K, X and subreaches, replacing the ones found before."""
    found = [p for p in row.problems if "is not a" in p]
    if row.k_hours is not None and row.k_hours <= 0.0:
        found.append("K: above zero")
    if row.x is not None and not X_RANGE[0] <= row.x <= X_RANGE[1]:
        found.append(f"X: between {X_RANGE[0]:g} and {X_RANGE[1]:g}")
    if row.subreaches is not None and row.subreaches < 1:
        found.append("Subreaches: 1 or more")
    if (row.k_hours is None) != (row.x is None):
        found.append("K and X: both, or neither")
    row.problems = found


def proposal_args(
    basin_file: str | Path, out: str | Path, rows: list[ReachRow], velocity_ms: float | None, control: str | None
) -> list[str]:
    """``wadi2d muskingum`` for the table: the reference flows the user gave, the velocity, and the HMS control file
    whose interval is the lumped step (None on a generated basin, which steps at the engine's default)."""
    args = ["muskingum", str(basin_file), "--out", str(out)]
    for row in rows:
        if row.flow is not None and row.flow > 0.0:
            args += ["--flow", f"{row.name}={row.flow!r}"]
    if velocity_ms:
        args += ["--velocity", repr(float(velocity_ms))]
    if control:
        args += ["--control", str(control)]
    return args


def apply_proposals(rows: list[ReachRow], found: dict) -> str:
    """The engine's proposals into the rows the user has not typed, and the line under the table.

    A row is filled when it is empty or still holds an earlier proposal. A reach the file already routes by Muskingum
    and that has no proposal takes the file's own numbers, said to be the file's.
    """
    by_name = {item["name"]: item for item in found.get("reaches", [])}
    filled = kept = none = unstable = 0
    for row in rows:
        item = by_name.get(row.name)
        if item is None:
            continue
        if not (row.empty() or row.proposed):
            kept += 1
            continue
        proposal, own = item.get("proposal"), item.get("own")
        source = proposal or own
        if source is None:
            row.k_hours = row.x = row.subreaches = None
            row.words, row.proposed = item.get("words") or "", False
            none += 1
            continue
        row.k_hours, row.x, row.subreaches = source["k_hours"], source["x"], int(source["subreaches"])
        row.words = item.get("words") or ""
        if proposal is None:
            row.words = f"The file's own Muskingum numbers. {row.words}".strip()
        row.proposed = True
        filled += 1
        unstable += int(bool(proposal) and not proposal.get("stable", True))
        check(row)
    step = found.get("step_minutes")
    words = f"{filled} proposed" + (f" for a {step:g} min step" if step else "")
    if kept:
        words += f"; {kept} kept as typed (clear a row's K and X to have it proposed)"
    if none:
        words += f"; {none} with nothing to propose from: type K and X"
    if unstable:
        words += f"; {unstable} not stable at this step, a reach the wave crosses in under half a step"
    return words + ". A proposal is a start, not a result: read how each was derived, and change what you know better."


def job_rows(rows: list[ReachRow]) -> list[dict]:
    """``hydrology.muskingum``: every row that holds K and X; subreaches 1 where the cell is blank."""
    return [
        {"reach": row.name, "k_hours": row.k_hours, "x": row.x, "subreaches": row.subreaches or 1}
        for row in rows
        if row.complete()
    ]


def table_note(rows: list[ReachRow], generated: bool) -> str:
    """What the rows as they stand mean for a run."""
    if not rows:
        return "No reaches: nothing to route."
    lacking = [row.name for row in rows if not row.complete()]
    wrong = [f"{row.name} ({'; '.join(row.problems)})" for row in rows if row.problems]
    words = f"{len(rows) - len(lacking)} of {len(rows)} reaches have K and X."
    if wrong:
        words += f" Not usable: {', '.join(wrong)}."
    if lacking and generated:
        words += (
            f" Without them a reach is left out and its water runs on the 2D grid from the junction above: "
            f"{', '.join(lacking)}."
        )
    elif lacking:
        words += (
            f" A run stops on a Muskingum-Cunge reach without them: {', '.join(lacking)} (a reach the file routes by "
            "Muskingum, a lag or nothing keeps the file's method)."
        )
    return words


def cell_text(row: ReachRow, column: int) -> str:
    value = {FLOW_COLUMN: row.flow, K_COLUMN: row.k_hours, X_COLUMN: row.x, COUNT_COLUMN: row.subreaches}.get(column)
    if column == 0:
        return row.name
    if column == WORDS_COLUMN:
        if row.problems:
            return "; ".join(row.problems)
        return " ".join(part for part in (row.flow_problem and f"{row.flow_problem}.", row.words) if part)
    return "" if value is None else f"{value:g}"
