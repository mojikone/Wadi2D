"""The lateral weir and pump-station laws read off HMS's own series: the channel stage from the passed flow.

For each step, the stage is the channel rating read at HMS's passed flow; the weir's C L H^1.5 and the pump's units x
table(head) at that stage are compared with HMS's diverted flow. Prints the worst differences and where the pump ran.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np

DATA = Path(__file__).resolve().parents[2] / "tests" / "data" / "hms_diversions"
TABLES = json.loads((DATA / "tables.json").read_text(encoding="utf-8"))


def load(case: str) -> dict[str, np.ndarray]:
    rows = list(csv.DictReader((DATA / f"{case}.csv").open(encoding="utf-8")))
    return {key: np.array([float(row[key]) for row in rows]) for key in rows[0]}


def stage(flow: np.ndarray) -> np.ndarray:
    channel = TABLES["W72 Channel"]
    return np.interp(flow, channel["y"], channel["x"])


def weir(case: str) -> None:
    hms = load(case)
    head = np.maximum(stage(hms["passed"]) - 103.0, 0.0)
    law = 1.6 * 20.0 * head**1.5
    print(case, "weir law at HMS's passed flow, worst", np.abs(law - hms["diverted"]).max())
    tail = TABLES["W72 Tail"]
    tailwater = np.interp(hms["diverted"], tail["y"], tail["x"])
    up = stage(hms["passed"])
    s = np.where(up > 103.0, (tailwater - 103.0) / np.maximum(up - 103.0, 1e-9), 0.0)
    print("  submergence max", s.max())


def pump() -> None:
    hms = load("div_pump")
    level = stage(hms["passed"])
    table = TABLES["W72 Pump"]
    one = np.interp(112.5 - level, table["x"], table["y"])
    running = hms["diverted"] > 0.0
    law = np.where(running, 2.0 * one, 0.0)
    print("pump law where running, worst", np.abs(law - hms["diverted"]).max())
    edges = np.nonzero(np.diff(running.astype(int)))[0]
    for edge in edges:
        span = slice(max(edge - 1, 0), edge + 3)
        print("  switch at", edge + 1, "levels", np.round(level[span], 5), "diverted", np.round(hms["diverted"][span], 4))


if __name__ == "__main__":
    weir("div_weir")
    weir("div_weir_tw")
    pump()
