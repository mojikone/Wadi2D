"""W81: a strip's mesh and tables are cached with the grid, read back to the digit, and rebuilt when its rules change."""

from __future__ import annotations

import numpy as np

from tests.engine.conftest import tilted_dem  # noqa: F401
from tests.engine.test_strips_run import corridor, plane_job
from wadi2d.run import prepare_grid


def _arrays(obj, prefix: str) -> dict[str, np.ndarray]:
    return {prefix + k: v for k, v in vars(obj).items() if isinstance(v, np.ndarray)}


def _everything(tables) -> dict[str, np.ndarray]:
    s = tables.strip
    out = {**_arrays(tables, "g_"), **_arrays(s.mesh, "m_"), **_arrays(s.strip.geometry, "geo_"), "kept": s.kept}
    out["masked_j"], out["masked_i"] = s.strip.masked
    return out


def test_a_second_prepare_reads_the_strip_from_the_cache(tilted_dem, tmp_path, monkeypatch) -> None:  # noqa: F811
    cfg = plane_job(tilted_dem, corridor())
    cache = tmp_path / "cache"
    events = []

    class Log:
        def emit(self, ev, **kw):
            events.append((ev, kw.get("kind")))

    first, _crs = prepare_grid(cfg, cache, Log())
    assert ("output", "strip_cache_saved") in events and list(cache.glob("strip_*.pkl"))
    import wadi2d.strips.build as sb

    def refuse(*_a, **_k):
        raise AssertionError("the strip was rebuilt")

    monkeypatch.setattr(sb, "mask_for_strips", refuse)
    monkeypatch.setattr(sb, "strip_tables", refuse)
    events.clear()
    second, _crs = prepare_grid(cfg, cache, Log())
    assert ("output", "strip_cache_hit") in events and ("output", "grid_cache_hit") in events
    a, b = _everything(first), _everything(second)
    assert a.keys() == b.keys()
    for name in a:
        np.testing.assert_array_equal(a[name], b[name], err_msg=name)
    assert second.strip.strip.notes == first.strip.strip.notes


def test_a_changed_corridor_misses_the_strip_cache(tilted_dem, tmp_path) -> None:  # noqa: F811
    cache = tmp_path / "cache"
    prepare_grid(plane_job(tilted_dem, corridor()), cache)
    events = []

    class Log:
        def emit(self, ev, **kw):
            events.append((ev, kw.get("kind")))

    prepare_grid(plane_job(tilted_dem, corridor(x_end=150.0)), cache, Log())
    assert ("output", "strip_cache_saved") in events and ("output", "strip_cache_hit") not in events
    assert len(list(cache.glob("strip_*.pkl"))) == 2
