"""Terrain objects on a strip (W45, stage 6): a crest line lands on the faces that separate the cells it passes
between, a wall closes them, a burn line lowers the strip's ground, and a crest across a corridor holds the water
the squares' crest holds."""

from __future__ import annotations

import json
import sqlite3

import numpy as np
import pytest

from tests.engine.conftest import X0, Y0, tilted_dem  # noqa: F401
from tests.engine.test_strips_run import MID_Y, corridor, plane_job
from tests.strips.test_pixels import two_quads
from wadi2d.config.constants import CRITICAL_WEIR_COEFF
from wadi2d.config.schema import Tables, TerrainObject
from wadi2d.run import run_job
from wadi2d.strips.objects import CrestPolyline, faces_from_objects
from wadi2d.strips.tables import build_poly_tables


def shared_face(geo) -> int:
    (face,) = [f for f in range(geo.nfaces) if geo.face_cell[f, 1] >= 0]
    return face


def test_a_crest_line_between_two_cells_lifts_their_shared_face_and_a_wall_closes_it() -> None:
    geo, mesh, kept, pix = two_quads()
    across = np.array([[20.0, -5.0], [20.0, 15.0]])  # along the shared edge at x = 20
    crest, cw, wall = faces_from_objects(geo, None, [CrestPolyline(across, np.array([100.5, 100.5]), CRITICAL_WEIR_COEFF)])
    f = shared_face(geo)
    assert crest[f] == pytest.approx(100.5) and cw[f] == CRITICAL_WEIR_COEFF and not wall[f]
    assert np.isnan(np.delete(crest, f)).all()  # the outer faces have the void beyond them: no side to separate
    lifted, _kept = build_poly_tables(geo, pix, Tables(), 20.0, 0.03, given_cw=cw, crest=crest)
    k = int(np.nonzero(_kept == f)[0][0])
    assert lifted.zf[k] == pytest.approx(100.5) and lifted.cw[k] == CRITICAL_WEIR_COEFF
    assert mesh.zf[int(np.nonzero(kept == f)[0][0])] < 100.5  # the ground alone sat lower
    _crest, _cw, walled = faces_from_objects(geo, None, [CrestPolyline(across, np.zeros(2), 0.0, wall=True)])
    assert walled[f] and walled.sum() == 1


def test_a_spillway_sets_its_own_level_under_a_higher_crest() -> None:
    geo, _mesh, _kept, _pix = two_quads()
    across = np.array([[20.0, -5.0], [20.0, 15.0]])
    lines = [
        CrestPolyline(across, np.array([101.0, 101.0]), CRITICAL_WEIR_COEFF),
        CrestPolyline(across, np.array([100.4, 100.4]), 1.7, keep_max=False),
    ]
    crest, cw, _wall = faces_from_objects(geo, None, lines)
    f = shared_face(geo)
    assert crest[f] == pytest.approx(100.4) and cw[f] == 1.7


def crest_across(z: float) -> dict:
    return {"kind": "crest_line", "coordinates": [(X0 + 120.0, Y0 + 2.0), (X0 + 120.0, Y0 - 98.0)], "z_constant": z}


def test_a_crest_across_a_corridor_holds_the_water_the_squares_crest_holds(tilted_dem, tmp_path) -> None:  # noqa: F811
    """The rain east of the crest leaves, the rain west of it is held, on squares alone and with the corridor alike;
    before stage 6 the corridor was a gap in the crest."""
    objects = {"objects": [TerrainObject.model_validate(crest_across(200.0))]}
    runs = {}
    for name, strips in (("squares", None), ("corridor", corridor())):
        cfg = plane_job(tilted_dem, strips)
        run = run_job(cfg.model_copy(update={"terrain": cfg.terrain.model_copy(update=objects)}), tmp_path / name)
        assert run.exit_code == 0, run.message
        assert abs(run.balance.relative) < 1e-6
        runs[name] = run
    east_share = 80.0 / 200.0  # of the plane lies east of the crest and drains freely
    squares, strip = runs["squares"].balance, runs["corridor"].balance
    assert squares.outflow < east_share * squares.rain and squares.storage > 0.5 * squares.rain, squares
    assert strip.outflow == pytest.approx(squares.outflow, rel=0.01), (strip.outflow, squares.outflow)
    db = sqlite3.connect(tmp_path / "corridor" / "maps" / "strip_mesh.gpkg")
    lifted = db.execute("SELECT COUNT(*), MIN(invert_m), MAX(max_discharge_m3s) FROM strip_faces WHERE invert_m > 150").fetchone()
    db.close()
    assert lifted[0] >= 6 and lifted[1] == pytest.approx(200.0) and lifted[2] == 0.0, lifted  # a face per row, nothing over it


def test_a_burn_line_along_the_corridor_lowers_the_strip_ground(tilted_dem, tmp_path) -> None:  # noqa: F811
    cfg = plane_job(tilted_dem, corridor())
    burn = {"kind": "burn_line", "coordinates": [(X0 + 40.0, MID_Y), (X0 + 160.0, MID_Y)], "depth": 1.0, "width": 6.0}
    cut = cfg.model_copy(update={"terrain": cfg.terrain.model_copy(update={"objects": [TerrainObject.model_validate(burn)]})})
    plain = run_job(cfg, tmp_path / "plain")
    burned = run_job(cut, tmp_path / "burned")
    assert plain.exit_code == 0 and burned.exit_code == 0
    lows = []
    for name in ("plain", "burned"):
        db = sqlite3.connect(tmp_path / name / "maps" / "strip_mesh.gpkg")
        lows.append(db.execute("SELECT MIN(zmin_m) FROM strip_cells WHERE row = 3").fetchone()[0])
        db.close()
    assert lows[1] == pytest.approx(lows[0] - 1.0, abs=0.05), lows
    stats = json.loads((tmp_path / "burned" / "progress.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert stats["code"] == 0
