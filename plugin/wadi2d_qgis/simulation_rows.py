# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The Simulation section as plain values (W99): the run's one start, the 2D step, and what of them the job takes.
No Qt here.

The job takes a number only where the user moved it off the engine's default, so a model left at the defaults writes
the job it wrote before this section existed. A fixed step is the engine's largest and smallest step set to the same
value: the engine has no other way to hold one, and where the flow needs a shorter step it stops the run and names the
cell, which is its own refusal.
"""

from __future__ import annotations

from datetime import datetime

CFL, DT_MAX, DT_MIN = "numerics.cfl", "numerics.dt_max", "numerics.dt_min"
LUMPED_STEP = "hydrology.time_step_min"
SERIES_EVERY = "outputs.series_every_s"
NUMERIC_KEYS = ("cfl", "dt_max", "dt_min")
STEP_AUTO, STEP_FIXED = "auto", "fixed"
STEP_WORDS = {STEP_AUTO: "Automatic: the largest step the flow allows", STEP_FIXED: "Fixed (advanced)"}
FIXED_START = 0.5
"""The fixed step the box opens with, s, held inside the engine's bounds."""
START_PLACEHOLDER = "As 2021-10-04 00:00; empty: the start of the rain"
START_TIP = (
    "Date and time of the run's minute zero. A rain file's and a rain gauge's rain before it is left out, and records "
    "written with dates (rain gauges, observed flows and levels) are read from it. Left empty, the run starts with the "
    "first period of the rain. One field for the whole run: it replaces the three starts of the gridded rain, the rain "
    "gauges and the observed gauges."
)
BAD_START = "The run's start is not a date and time: write it as 2021-10-04 00:00, or leave it empty."
STEPS_REVERSED = "The smallest 2D step must not exceed the largest."
FIXED_NOTE = (
    "The step is held by setting the engine's largest and smallest step to it. The engine takes a smallest step of at "
    "most {high:g} s, so a fixed step lies between {low:g} and {high:g} s. Where the flow needs a shorter step than the "
    'one given, the engine does not shorten it: it stops the run and names the cell ("time step below the minimum").'
)
MAPS_NOTE = (
    "Peak depth and hazard do not need the shorter interval: the run keeps its own peaks. It takes three times "
    "the disk, so choose it for an animation. Estimate says how much."
)
LUMPED_REPLACES = (
    "The lumped step of the form, {own:g} min, replaces the {theirs:g} min of the HMS control file."
)


def start_problem(text: str) -> str:
    """Why a typed start cannot be read, or an empty string; the engine reads ISO dates."""
    if not text:
        return ""
    try:
        datetime.fromisoformat(text)
    except ValueError:
        return BAD_START
    return ""


def numerics_of(mode: str, fixed: float, held: dict[str, float], defaults: dict[str, float]) -> dict:
    """What the job's ``numerics`` takes: a fixed step as both bounds, else each number moved off its default."""
    if mode == STEP_FIXED:
        return {"dt_max": fixed, "dt_min": fixed}
    return {key: held[key] for key in NUMERIC_KEYS if key in held and held[key] != defaults.get(key)}


def simulation_problems(values: dict) -> list[str]:
    """What stops a run, in plain words."""
    found = [start_problem(values.get("start", ""))]
    # the smallest and the largest 2D step the form holds
    low, high = values.get("step_bounds") or (None, None)
    if low is not None and high is not None and low > high:
        found.append(STEPS_REVERSED)
    return [text for text in found if text]


def fixed_step(numerics: dict) -> float | None:
    """The fixed step a job's ``numerics`` holds, or None: both bounds given and equal."""
    low, high = numerics.get("dt_min"), numerics.get("dt_max")
    return high if low is not None and low == high else None
