"""checkpoint.h5: enough to continue a run: state arrays, maxima, series so far, the water accounts, the job's hash.

A checkpoint continues the job that made it and no other: resuming with another rain or another Manning would
give a result belonging to neither job, under exit 0.
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

import h5py
import numpy as np

from wadi2d.solver.layout import STATE_ARRAYS

CHECKPOINT_FORMAT = "2"
BALANCE = "balance_"
SAVED_ARRAYS = (*STATE_ARRAYS, "res", "om")
"""The state, the cells' rounding residuals, and the wet share of the cell plan."""


def save_checkpoint(path: str | Path, model, monitor, job_hash: str) -> Path:
    """Write through a temporary name; a crash during the write leaves the last good checkpoint."""
    out = Path(path)
    tmp = out.with_suffix(".tmp")
    st = model.stepper
    model.backend.synchronize()
    monitor.balance.outflow = monitor.tally.volume()
    with h5py.File(tmp, "w") as f:
        f.attrs["format"] = CHECKPOINT_FORMAT
        f.attrs["job_hash"] = job_hash
        f.attrs["t"], f.attrs["dt"], f.attrs["nsteps"] = st.t, st.dt, st.nsteps
        f.attrs["next_series"], f.attrs["next_map"] = monitor.next_series, monitor.next_map
        for name in SAVED_ARRAYS:
            f.create_dataset(f"state/{name}", data=model.backend.get_field(name))
        for name, a in monitor.maxima.raw().items():
            f.create_dataset(f"maxima/{name}", data=a)
        for key, value in asdict(monitor.balance).items():
            f.attrs[f"{BALANCE}{key}"] = value
        f.create_dataset("times", data=np.asarray(monitor.times, np.float64))
        for n, s in enumerate(monitor.series + monitor.line_series):
            for key, values in s.columns.items():
                f.create_dataset(f"series/{n}/{key}", data=np.asarray(values, np.float64))
    tmp.replace(out)
    return out


def checkpoint_job(path: str | Path) -> str | None:
    """The hash of the job that wrote this checkpoint; None for a file too old or damaged to say."""
    try:
        with h5py.File(path, "r") as f:
            if f.attrs.get("format") != CHECKPOINT_FORMAT:
                return None
            return str(f.attrs["job_hash"])
    except (OSError, KeyError):
        return None


def load_checkpoint(path: str | Path, model, monitor) -> None:
    """Put a saved run back into a freshly built model and monitor of the same job."""
    with h5py.File(path, "r") as f:
        for name in SAVED_ARRAYS:
            model.backend.set_field(name, f[f"state/{name}"][()])
        monitor.maxima.restore({name: f[f"maxima/{name}"][()] for name in f["maxima"]})
        st = model.stepper
        st.t, st.dt, st.nsteps = float(f.attrs["t"]), float(f.attrs["dt"]), int(f.attrs["nsteps"])
        monitor.last_t = st.t
        monitor.settled = st.t
        monitor.next_series, monitor.next_map = float(f.attrs["next_series"]), float(f.attrs["next_map"])
        saved = {k[len(BALANCE) :]: v.item() for k, v in f.attrs.items() if k.startswith(BALANCE)}
        monitor.balance = type(monitor.balance)(**saved)
        monitor.tally.restore(monitor.balance.outflow)
        monitor.times = list(f["times"][()])
        for n, s in enumerate(monitor.series + monitor.line_series):
            for key in s.columns:
                s.columns[key] = list(f[f"series/{n}/{key}"][()])
    wet = model._tile_wet(model.field("h"))
    model.backend.wet[:] = wet
    model.stepper.rebuild_active()
