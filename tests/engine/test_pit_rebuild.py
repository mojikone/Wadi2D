"""The build with the pit fills taken from the build before them (W91): the tiles the fills reach built again, the
strip's tables kept when no fill is near it; every one the whole build's to the digit."""

from __future__ import annotations

from dataclasses import fields
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from tests.engine.conftest import X0, Y0, tilted_box, write_dem
from tests.engine.conftest import job as base_job
from tests.engine.test_run import valley
from wadi2d.config.schema import RunConfig, TerrainObject
from wadi2d.demstore import open_bed
from wadi2d.engine.pit_rebuild import fill_tiles, fills_follow, strip_untouched
from wadi2d.engine.pit_step import resolve_pits
from wadi2d.io.progress import Progress
from wadi2d.run import prepare_grid
from wadi2d.strips.geometry import MeshGeometry
from wadi2d.tables import GridTables
from wadi2d.terrain.pits import fill_objects, find_pits

NX, NY, DX, PIXEL = 128, 96, 8.0, 2.0
"""4 by 3 tiles and their padding: room for tiles no fill reaches."""
PITS = ((60.0, 52.0), (256.0, 252.0))
"""Holes beside the thalweg, metres east and south of the corner: one near the north-west corner, one across a tile's
edge, so the fills reach some tiles and not others."""


@pytest.fixture
def pits_dem(tmp_path: Path) -> Path:
    z = valley(int(NX * DX / PIXEL), int(NY * DX / PIXEL), PIXEL)
    for x, y in PITS:
        r, c = int(y / PIXEL), int(x / PIXEL)
        z[r - 2 : r + 2, c - 1 : c + 1] -= 12.0
    return write_dem(tmp_path / "pits.tif", z, PIXEL)


def job(dem: Path, **terrain) -> RunConfig:
    cfg = base_job(dem, NX, NY, DX, terrain={"manning": 0.04, **terrain})
    return cfg


def with_fills(cfg: RunConfig, tables: GridTables) -> RunConfig:
    pits = find_pits(tables, cfg.terrain)
    objects = [*cfg.terrain.objects, *fill_objects(pits, tables)]
    return cfg.model_copy(update={"terrain": cfg.terrain.model_copy(update={"objects": objects})})


def same(a: GridTables, b: GridTables) -> None:
    assert np.array_equal(a.grid.mask, b.grid.mask)
    for field in fields(GridTables):
        if field.name != "grid":
            assert np.array_equal(getattr(a, field.name), getattr(b, field.name), equal_nan=True), field.name


def test_the_tiles_the_fills_reach_built_again_are_the_whole_build_to_the_digit(pits_dem, tmp_path):
    asked = job(pits_dem, fill_pits=True)
    assert fills_follow(asked)
    before, _crs = prepare_grid(asked, tmp_path / "a")
    assert before.raw is not None  # a build before fills keeps what the rebuild needs
    filled = with_fills(asked, before)
    assert not fills_follow(filled)
    with open_bed(filled, tmp_path / "a") as bed:
        only = fill_tiles(filled, before, before.grid, bed)
    assert only and len(only) < before.grid.ntiles - 1  # some tiles, not all

    part, _crs = prepare_grid(filled, tmp_path / "b", base=before)
    whole, _crs = prepare_grid(filled, tmp_path / "c")
    same(part, whole)
    assert part.raw is None and whole.raw is None  # nothing kept where no rebuild follows
    # the fills did change the tables, so the test is not of two identical builds
    assert not np.array_equal(part.zmin, before.zmin)
    # and what the partial build saved is read back as the same tables
    again, _crs = prepare_grid(filled, tmp_path / "b")
    same(again, whole)


def test_a_base_read_from_the_cache_builds_the_whole_grid(pits_dem, tmp_path):
    asked = job(pits_dem, fill_pits=True)
    prepare_grid(asked, tmp_path / "a")
    cached, _crs = prepare_grid(asked, tmp_path / "a")  # a cache hit: no raw faces
    assert getattr(cached, "raw", None) is None
    filled = with_fills(asked, cached)
    with open_bed(filled, tmp_path / "a") as bed:
        assert fill_tiles(filled, cached, cached.grid, bed) is None
    part, _crs = prepare_grid(filled, tmp_path / "b", base=cached)
    whole, _crs = prepare_grid(filled, tmp_path / "c")
    same(part, whole)


def test_the_pit_step_hands_its_rebuild_the_tables_before_and_lets_their_raw_faces_go(pits_dem, tmp_path):
    asked = job(pits_dem, fill_pits=True)
    cache = tmp_path / "cache"
    before, crs = prepare_grid(asked, cache)
    seen = []

    def rebuild(cfg, base):
        seen.append(base)
        return prepare_grid(cfg, cache, base=base)[0]

    progress = Progress(tmp_path / "progress.jsonl")
    try:
        cfg, tables, pits = resolve_pits(asked, before, crs, tmp_path, progress, rebuild)
    finally:
        progress.close()
    assert seen == [before] and len(pits) == len(PITS)
    assert tables.raw is None
    same(tables, prepare_grid(cfg, tmp_path / "whole")[0])


def square(x: float, y: float, side: float) -> np.ndarray:
    return np.array([(x, y), (x + side, y), (x + side, y + side), (x, y + side)], np.float64)


def strip_of(cells: list[np.ndarray]) -> SimpleNamespace:
    """A stand-in strip: only its cells' rings are read."""
    xs = np.concatenate([c[:, 0] for c in cells])
    ys = np.concatenate([c[:, 1] for c in cells])
    starts = np.cumsum([0] + [len(c) for c in cells])
    geo = MeshGeometry(xs, ys, starts, np.arange(xs.size), np.zeros((0, 2), np.int64), np.zeros((0, 2), np.int64))
    return SimpleNamespace(geometry=geo)


def test_the_strip_keeps_its_tables_only_when_no_fill_is_near_it(pits_dem):
    cfg = job(pits_dem)
    strip = strip_of([square(X0 + 600.0, Y0 - 300.0, 20.0), square(X0 + 620.0, Y0 - 300.0, 20.0)])
    base = SimpleNamespace(strip_mesh=(None, strip), strip=object())
    reach = cfg.tables.local_radius_beta * cfg.tables.face_depth_max if cfg.tables.face_conveyance == "local_radius" else 0.0

    def fill_at(x: float) -> RunConfig:
        fill = TerrainObject(kind="fill", name="pit fill 1", coordinates=square(x, Y0 - 300.0, DX).tolist(), z_constant=1.0)
        return cfg.model_copy(update={"terrain": cfg.terrain.model_copy(update={"objects": [fill]})})

    far = X0 + 640.0 + reach + 4.0 * DX
    near = X0 + 640.0 + reach + 2.0 * DX
    assert strip_untouched(fill_at(far), base, strip)
    assert not strip_untouched(fill_at(near), base, strip)
    assert not strip_untouched(fill_at(far), base, strip_of([square(X0, Y0, 1.0)]))  # another mesh
    assert not strip_untouched(cfg, base, strip)  # no fills: nothing says the job is the base's


def _strip_arrays(tables) -> dict[str, np.ndarray]:
    s = tables.strip
    out = {f"m_{k}": v for k, v in vars(s.mesh).items() if isinstance(v, np.ndarray)}
    out["kept"] = s.kept
    return out


def test_the_strip_pieces_the_fills_reach_built_again_are_the_whole_build_to_the_digit(tmp_path, monkeypatch):
    import wadi2d.strips.tables as st

    dem = write_dem(tmp_path / "long.tif", tilted_box(400, 48, 2.0, 0.01), 2.0)
    mid = Y0 - 48.0
    strips = {"enabled": True, "corridors": [
        {"name": "mid", "centre": [(X0 + 40.0, mid), (X0 + 760.0, mid)], "offsets": [-12.0, -8.0, -4.0, 0.0, 4.0, 8.0, 12.0]}
    ]}  # fmt: skip
    asked = base_job(dem, 200, 24, 4.0, terrain={"manning": 0.04, "fill_pits": True}, strips=strips)
    before, _crs = prepare_grid(asked, tmp_path / "a")
    assert before.strip_raw is not None and not hasattr(before.strip.mesh, "raw")  # kept off the cached strip
    # two cells beside the corridor's west end, raised: the strip reads them through its faces' local radius
    fills = [
        TerrainObject(kind="fill", name=f"pit fill 1.{m}", coordinates=square(X0 + x, mid + 16.0, 4.0).tolist(), z_constant=100.5)
        for m, x in ((1, 60.0), (2, 64.0))
    ]  # fmt: skip
    filled = asked.model_copy(update={"terrain": asked.terrain.model_copy(update={"objects": fills})})
    assert not strip_untouched(filled, before, before.strip_mesh[1])  # near: the strip's tables must change
    sizes = []
    real = st.run_all

    def counted(items, work, workers):
        items = list(items)
        sizes.append(len(items))
        return real(items, work, workers)

    monkeypatch.setattr(st, "run_all", counted)
    part, _crs = prepare_grid(filled, tmp_path / "b", base=before)
    built = list(sizes)
    sizes.clear()
    whole, _crs = prepare_grid(filled, tmp_path / "c")
    assert max(built) < max(sizes)  # some pieces, not all
    a, b = _strip_arrays(part), _strip_arrays(whole)
    assert a.keys() == b.keys()
    for name in a:
        assert np.array_equal(a[name], b[name], equal_nan=True), name
    assert not np.array_equal(part.strip.mesh.ftab, before.strip.mesh.ftab)  # the fills did reach the strip
    same(part, whole)
