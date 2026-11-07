"""On an HMS network, network series are written only for what this run put on the grid (W39 item 6, his word).

The lumped engine computes an HMS basin whole, as HMS would route it. On a hybrid only the lumped subbasins' own
hydrographs enter the grid; the grid routes them from there. A subbasin switched to rain-on-grid, and the junctions and
reaches below the lumped ones, never ran in this model, so their series would read as design flows they are not.
"""

from __future__ import annotations

import json

from tests.engine.conftest import job
from tests.engine.test_handback import CHAIN, DX, MIDDLE, NX, NY, SINK, SUB, X0, Y0, plane, write_basin
from wadi2d.run import run_job


def _polygons(tmp_path):
    def ring(x0, x1):
        return [[x0, Y0], [x1, Y0], [x1, Y0 - 40.0], [x0, Y0 - 40.0], [x0, Y0]]

    features = [
        {"type": "Feature", "properties": {"name": name}, "geometry": {"type": "Polygon", "coordinates": [ring(*span)]}}
        for name, span in (("Side", (X0, X0 + 40.0)), ("Wide", (X0 + 60.0, X0 + 100.0)))
    ]
    path = tmp_path / "subbasins.geojson"
    path.write_text(json.dumps({"type": "FeatureCollection", "features": features}), encoding="utf-8")
    return path


def test_only_the_elements_whose_water_entered_the_grid_get_a_network_series(tmp_path) -> None:
    wide = SUB.replace("Subbasin: Side", "Subbasin: Wide").format(down="J")
    basin = write_basin(tmp_path, SUB.format(down="J"), wide, CHAIN, SINK)
    cfg = job(
        plane(tmp_path), NX, NY, DX,
        terrain={"manning": 0.03},
        storm={"kind": "uniform", "depth_mm": 20.0, "duration_min": 20.0},
        hydrology={
            "hms_basin": str(basin), "time_step_min": 1.0, "inject_radius": 6.0, "polygons": str(_polygons(tmp_path)),
            "subbasins": [
                {"name": "Side", "mode": "lumped", "outlet": (X0 + 300.0, MIDDLE)},
                {"name": "Wide", "mode": "2d"},
            ],
        },
        run={"duration_s": 1800.0, "backend": "cpu", "source_every_s": 30.0},
    )  # fmt: skip
    out = tmp_path / "run"
    run = run_job(cfg, out)
    assert run.exit_code == 0, run.message
    written = sorted(p.stem for p in (out / "series").glob("network_*.csv"))
    assert written == ["network_Side"]  # not the 2D subbasin Wide, not J, R1, R2 or Out, which the grid stood in for
