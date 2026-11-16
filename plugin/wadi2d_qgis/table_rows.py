# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The Data tables of the dock as plain values (W101): named rain patterns and area-reduction curves, HEC-HMS's paired
data. No Qt here.

The store is ``{"patterns": {name: pattern}, "arf_curves": {name: curve}}``, a pattern ``{"time", "depth",
"time_units", "form"}`` and a curve ``{"areas_km2", "factors", "reduces_below_table"}``: the shapes of the engine's
``data_tables`` (``wadi2d/config/rain.py``). A job carries only the tables its storm names, so a store nothing reads
changes no job.

Interface: :func:`pattern_problems`, :func:`curve_problems`, :func:`store_problems`, :func:`store_job`,
:func:`unique_name`, :func:`cumulative_share`, :data:`PATTERN_CHOICES`.
"""

from __future__ import annotations

import itertools

PATTERNS, CURVES = "patterns", "arf_curves"
TIME_UNITS = {"percent": "% of the duration", "fraction": "fraction of the duration", "hours": "hours", "minutes": "minutes"}
FORMS = {"cumulative": "Cumulative: depth fallen by then", "incremental": "Incremental: depth in each period"}
ENDS = {"percent": 100.0, "fraction": 1.0}
UNIFORM, SCS, TABLE = "uniform", "scs", "table"
SCS_TYPES = ("I", "IA", "II", "III")
SCS_HOURS = 24.0
PATTERN_CHOICES = (
    (UNIFORM, "Uniform: a constant rate"),
    *((f"{SCS}:{kind}", f"SCS type {kind}, the NRCS 24-hour curve (HEC-HMS's tables)") for kind in SCS_TYPES),
)
"""The patterns every model has; the stored ones follow them as ``table:<name>``."""
TABLE_PREFIX = f"{TABLE}:"
NEW_PATTERN, NEW_CURVE = "Pattern", "Curve"
NAME_TAKEN = 'There is already a table named "{name}".'


def new_store() -> dict:
    return {PATTERNS: {}, CURVES: {}}


def new_pattern() -> dict:
    return {"time": [0.0, 100.0], "depth": [0.0, 100.0], "time_units": "percent", "form": "cumulative"}


def new_curve() -> dict:
    return {"areas_km2": [10.0, 1000.0], "factors": [1.0, 0.8], "reduces_below_table": True}


def unique_name(base: str, taken) -> str:
    if base not in taken:
        return base
    return next(f"{base} {n}" for n in itertools.count(2) if f"{base} {n}" not in taken)


def _rising(values: list[float]) -> bool:
    return all(b > a for a, b in itertools.pairwise(values))


def pattern_problems(name: str, pattern: dict) -> list[str]:
    """The engine's checks of a pattern table (``PatternTable``), in the dock's words."""
    t, d = list(pattern.get("time") or []), list(pattern.get("depth") or [])
    where = f'Pattern "{name}"'
    if not t or len(t) != len(d):
        return [f"{where} needs one depth per time."]
    if not _rising(t):
        return [f"{where}: its times must rise."]
    if min(d) < 0.0:
        return [f"{where}: its depths cannot go below zero."]
    if pattern.get("form", "cumulative") == "cumulative":
        if len(t) < 2 or t[0] != 0.0 or d[0] != 0.0:
            return [f"{where} is cumulative: it starts at time 0 with depth 0 and holds two rows at least."]
        if any(b < a for a, b in itertools.pairwise(d)) or d[-1] <= 0.0:
            return [f"{where} is cumulative: its depth cannot fall, and must end above zero."]
    elif t[0] <= 0.0 or sum(d) <= 0.0:
        return [f"{where} is incremental: its first period ends after time 0, and its depths hold some rain."]
    end = ENDS.get(pattern.get("time_units", "percent"))
    if end is not None and abs(t[-1] - end) > 1e-9 * end:
        return [f"{where}: a pattern in {TIME_UNITS[pattern['time_units']]} ends at {end:g}, not {t[-1]:g}."]
    return []


def curve_problems(name: str, curve: dict) -> list[str]:
    """The engine's checks of an area-reduction table (``ArfTableConfig``, ``ArfTable``), in the dock's words."""
    areas, factors = list(curve.get("areas_km2") or []), list(curve.get("factors") or [])
    where = f'Curve "{name}"'
    if not areas or len(areas) != len(factors):
        return [f"{where} needs one factor per area."]
    if not _rising(areas):
        return [f"{where}: its areas must rise."]
    if min(areas) <= 0.0:
        return [f"{where}: its areas are above zero."]
    if any(not 0.0 < f <= 1.0 for f in factors):
        return [f"{where}: a factor lies above 0 and at most 1."]
    return []


def store_problems(store: dict, patterns: set[str], curves: set[str]) -> list[str]:
    """What is wrong with the tables a job reads, by name; a table nothing reads is not checked."""
    found = []
    for name in sorted(patterns):
        if name not in store.get(PATTERNS, {}):
            found.append(f'The rain reads pattern "{name}", which Data tables does not hold.')
        else:
            found += pattern_problems(name, store[PATTERNS][name])
    for name in sorted(curves):
        if name not in store.get(CURVES, {}):
            found.append(f'The area reduction reads curve "{name}", which Data tables does not hold.')
        else:
            found += curve_problems(name, store[CURVES][name])
    return found


def _pattern_job(pattern: dict) -> dict:
    found = {"time": list(pattern["time"]), "depth": list(pattern["depth"])}
    for key, default in (("time_units", "percent"), ("form", "cumulative")):
        if pattern.get(key, default) != default:
            found[key] = pattern[key]
    return found


def _curve_job(curve: dict) -> dict:
    found = {"areas_km2": list(curve["areas_km2"]), "factors": list(curve["factors"])}
    if not curve.get("reduces_below_table", True):
        found["reduces_below_table"] = False
    return found


def store_job(store: dict, patterns: set[str], curves: set[str]) -> dict:
    """The job's ``data_tables``: only the tables the storm names; empty when it names none."""
    found = {}
    if patterns:
        found[PATTERNS] = {name: _pattern_job(store[PATTERNS][name]) for name in sorted(patterns)}
    if curves:
        found[CURVES] = {name: _curve_job(store[CURVES][name]) for name in sorted(curves)}
    return found


def pattern_of(choice: str | None) -> dict:
    """A pattern choice of the Storm section (``uniform``, ``scs:II``, ``table:<name>``) as the job's ``storm.pattern``;
    empty for uniform, which is the engine's own default."""
    if not choice or choice == UNIFORM:
        return {}
    if choice.startswith(f"{SCS}:"):
        return {"kind": SCS, "scs_type": choice.split(":", 1)[1]}
    return {"kind": TABLE, "table": choice[len(TABLE_PREFIX) :]}


def pattern_name(choice: str | None) -> str | None:
    """The stored pattern a choice names, or None."""
    return choice[len(TABLE_PREFIX) :] if choice and choice.startswith(TABLE_PREFIX) else None


def pattern_words(choice: str | None) -> str:
    if not choice or choice == UNIFORM:
        return "uniform"
    if choice.startswith(f"{SCS}:"):
        return f"SCS type {choice.split(':', 1)[1]}"
    return f'pattern "{pattern_name(choice)}"'


def cumulative_share(pattern: dict) -> tuple[list[float], list[float]]:
    """The pattern as the share of the depth fallen by each time, 0 to 1, for its chart."""
    t, d = list(pattern.get("time") or []), list(pattern.get("depth") or [])
    if not t or len(t) != len(d):
        return [], []
    if pattern.get("form", "cumulative") == "cumulative":
        top = d[-1] if d and d[-1] > 0 else 1.0
        return t, [v / top for v in d]
    total = sum(d) or 1.0
    shares, run = [0.0], 0.0
    for value in d:
        run += value
        shares.append(run / total)
    return [0.0, *t], shares
