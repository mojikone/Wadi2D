"""A result line across a lumped inflow's cells is named before the run (W31's surge)."""

from __future__ import annotations

import json

from tests.engine.conftest import X0, Y0, job, tilted_dem  # noqa: F401
from wadi2d.run import run_job

INFLOW_X, INFLOW_Y = X0 + 60.0, Y0 - 48.0


def warnings(folder) -> list[str]:
    lines = (folder / "progress.jsonl").read_text(encoding="utf-8").splitlines()
    return [e["message"] for e in map(json.loads, lines) if e.get("ev") == "warn"]


def test_a_line_over_an_inflow_is_named_and_a_line_clear_of_it_is_not(tilted_dem, tmp_path) -> None:  # noqa: F811
    cfg = job(
        tilted_dem, 50, 24, 4.0,
        hydrology={"inflows": [{"name": "S5", "x": INFLOW_X, "y": INFLOW_Y, "times_s": [0.0, 60.0], "flows": [1.0, 1.0]}]},
        outputs={"lines": [
            {"name": "Ring", "coordinates": [(INFLOW_X, Y0 - 4.0), (INFLOW_X, Y0 - 92.0)]},
            {"name": "Below", "coordinates": [(X0 + 180.0, Y0 - 4.0), (X0 + 180.0, Y0 - 92.0)]},
        ]},
        run={"duration_s": 10.0},
    )  # fmt: skip
    out = tmp_path / "run"
    assert run_job(cfg, out).exit_code == 0
    said = [w for w in warnings(out) if "pond's surge" in w]
    assert len(said) == 1 and said[0].startswith("line Ring crosses") and "S5" in said[0]
