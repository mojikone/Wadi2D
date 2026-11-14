# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The rows of the dam breach table, without Qt: one breach of a named dam line each, and the job's ``breaches`` (W63).

A row carries what HEC-RAS's user-entered breach asks: mode, final bottom, bottom width, side slope, formation time, and the
trigger. The breach centre (the lowest ground under the line), the weir and orifice coefficients, the update interval and
the estimators stay the engine's defaults; a job written by hand still sets them.
"""

from __future__ import annotations

from dataclasses import dataclass

BREACHES = "breaches"
MODES = {"overtopping": "Overtopping", "piping": "Piping"}
PROGRESSIONS = {"linear": "Linear", "sine": "Sine wave"}
TRIGGER_LEVEL, TRIGGER_HELD, TRIGGER_TIME = "level", "level_duration", "time"
TRIGGERS = {TRIGGER_LEVEL: "Pool level", TRIGGER_HELD: "Level held", TRIGGER_TIME: "Run time"}
SECONDS_PER_MINUTE = 60.0
SECONDS_PER_HOUR = 3600.0
REFUSAL = {  # the engine's own refusals (wadi2d.breach.control.refusal), said before the run
    "mesh": "A dam breach runs on the uniform grid in this version: untick the mesh refinement or the breach.",
    "strips": "A dam breach runs on the uniform grid in this version: untick the corridors or the breach.",
    "local_steps": "A dam breach is not tested with local time stepping: switch it off or remove the breach.",
}


@dataclass
class BreachRow:
    dam: str = ""
    mode: str = "overtopping"
    bottom_z: float | None = None
    width_m: float | None = None
    slope: float = 1.0
    formation_min: float | None = None
    progression: str = "linear"
    trigger: str = TRIGGER_LEVEL
    value: float | None = None
    """The pool level, m, for a level trigger; the run time, h, for a time trigger."""
    held_min: float | None = None
    piping_z: float | None = None


def breach_jobs(rows: list[BreachRow]) -> list[dict]:
    """The job's ``breaches``, one per row, in the engine's units."""
    out = []
    for row in rows:
        job = {
            "dam": row.dam,
            "mode": row.mode,
            "bottom_z": row.bottom_z,
            "bottom_width_m": row.width_m,
            "left_slope": row.slope,
            "right_slope": row.slope,
            "formation_time_s": None if row.formation_min is None else row.formation_min * SECONDS_PER_MINUTE,
            "progression": row.progression,
            "trigger": row.trigger,
        }
        if row.trigger == TRIGGER_TIME:
            job["trigger_time_s"] = None if row.value is None else row.value * SECONDS_PER_HOUR
        else:
            job["trigger_level"] = row.value
        if row.trigger == TRIGGER_HELD:
            job["trigger_duration_s"] = None if row.held_min is None else row.held_min * SECONDS_PER_MINUTE
        if row.mode == "piping":
            job["piping_z"] = row.piping_z
        out.append(job)
    return out


def breach_problems(rows: list[BreachRow], dams: list[str], values: dict) -> list[str]:
    """What stops a run with these breaches, in the dock's words; the engine's refusals first."""
    if not rows:
        return []
    found = [REFUSAL[key] for key in ("mesh", "strips", "local_steps") if values.get(key)]
    for number, row in enumerate(rows, 1):
        name = row.dam or f"row {number}"
        if row.dam not in dams:
            found.append(f"Breach {name}: choose a named crest line or embankment of the Structures layers.")
            continue
        missing = [
            words
            for words, value in (
                ("the final bottom", row.bottom_z),
                ("the bottom width", row.width_m),
                ("the formation time", row.formation_min),
                ("the time" if row.trigger == TRIGGER_TIME else "the pool level", row.value),
            )
            if value is None
        ]
        if row.trigger == TRIGGER_HELD and row.held_min is None:
            missing.append("how long the level is held")
        if row.mode == "piping" and row.piping_z is None:
            missing.append("the pipe's centre")
        if missing:
            found.append(f"Breach of {name}: type {', '.join(missing)}.")
        elif row.mode == "piping" and row.piping_z < row.bottom_z:
            found.append(f"Breach of {name}: the pipe's centre lies below the final bottom.")
    return found
