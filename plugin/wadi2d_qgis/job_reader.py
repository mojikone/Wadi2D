# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""A run from before the model was saved (W99) opened into the dock: :mod:`job_states` says what its job tells, the
sections restore it as they restore a saved model, and the job the refilled dock would write is compared with the
run's own to say what could not be restored."""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from .job_builder import LayerError, build_job
from .job_states import job_states, lost
from .model_store import labelled
from .widget_state import inputs


def refill(links, job: dict, run_folder: Path) -> list[str]:
    """Fill the dock from a job; what could not be restored, in words."""
    dock = links.dock
    links.reset()
    states = job_states(job, run_folder)
    words = []
    for section in dock.sections:
        state = states.get(section.key)
        if state is None:
            continue
        known = {path for path, _widget in inputs(section, section.state_skip)}
        unknown = sorted(set(state.get("widgets", {})) - known)
        if unknown:  # this module names an input the section no longer has: say so, do not pass over it
            words.append(f"{section.heading}, inputs the dock no longer has: {', '.join(unknown)}")
        words += labelled(section, section.restore(state, add_missing=True))
    dock.model_applied()
    scratch = Path(tempfile.mkdtemp(prefix="wadi2d_open_run_"))
    try:
        rebuilt = json.loads(json.dumps(build_job(dock._collect(), scratch)))
        words += lost(job, run_folder, rebuilt, scratch)
    except (LayerError, KeyError, ValueError, OSError) as problem:
        words.append(f"the job of the refilled dock could not be built to compare it: {problem}")
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    return words
