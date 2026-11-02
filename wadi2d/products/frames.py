"""The saved maps of a run, read ahead on a thread: decompressing is most of the wait, and the GPU can use it."""

from __future__ import annotations

import queue
import threading
from collections.abc import Iterator
from pathlib import Path

import h5py
import numpy as np

AHEAD = 3
"""Maps held ready."""
WAIT_S = 0.2
FIELDS = ("depth", "mean_depth", "speed")


def frame_names(results: Path) -> list[str]:
    with h5py.File(results, "r") as f:
        return sorted(f["maps"]) if "maps" in f else []


def run_maxima(results: Path) -> dict[str, np.ndarray]:
    """The run's own maxima, each taken at its own peak."""
    with h5py.File(results, "r") as f:
        return {name: f["maxima"][name][:] for name in ("depth", "mean_depth", "speed", "hazard")}


def read_frames(results: Path, names: list[str]) -> Iterator[tuple[np.ndarray, np.ndarray, np.ndarray]]:
    """(depth, mean depth, speed) of each map in turn; leaving the loop early ends the reader."""
    ready: queue.Queue = queue.Queue(maxsize=AHEAD)
    done = threading.Event()
    failed: list[BaseException] = []

    def hand_over(item) -> bool:
        while not done.is_set():
            try:
                ready.put(item, timeout=WAIT_S)
                return True
            except queue.Full:
                continue
        return False

    def read() -> None:
        try:
            with h5py.File(results, "r") as f:
                for name in names:
                    group = f["maps"][name]
                    if not hand_over(tuple(group[field][:] for field in FIELDS)):
                        return
        except (OSError, KeyError) as error:
            failed.append(error)
        hand_over(None)

    thread = threading.Thread(target=read, daemon=True)
    thread.start()
    try:
        while (item := ready.get()) is not None:
            yield item
    finally:
        done.set()
        thread.join()  # a reader left running holds h5py's lock, and the process then cannot exit
    if failed:
        raise failed[0]
