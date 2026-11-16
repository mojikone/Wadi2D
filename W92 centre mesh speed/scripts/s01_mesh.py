"""The centre generator's mesh of a job alone, timed stage by stage, its peak memory, and a digest of every field.

    python s01_mesh.py <job.json> <label> [--profile]

As ``prepare_grid`` reaches it: the DEM on the chunk store (W84, a store of W79's hard-linked into ``runs/cache`` so
nothing is decoded again), the domain mask, the left-out catchments, then ``mask_for_strips``. The stages are the
mesher's own functions, wrapped to sum their seconds. Writes ``runs/<label>.json`` (stages, peak memory, digests) and
``runs/<label>.mesh.pkl`` (the mask and the mesh, for ``s02_compare.py``); with ``--profile`` also
``runs/<label>.prof.txt``.
"""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
import pickle
import shutil
import sys
import time
from ctypes import wintypes
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNS = HERE.parent / "runs"
STORE = "dem_0bedda043cf08b5074aeaac6"
SOURCE_CACHE = Path(r"D:\Mojtaba\Renardet\Wadi2D\W79 Block 2 four ways\runs\cache")


class _Counters(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD), ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t), ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t), ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t), ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t), ("PrivateUsage", ctypes.c_size_t),
    ]  # fmt: skip


def peak_gb() -> dict[str, float]:
    c = _Counters()
    c.cb = ctypes.sizeof(c)
    k32 = ctypes.windll.kernel32
    k32.GetCurrentProcess.restype = wintypes.HANDLE
    k32.K32GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(_Counters), wintypes.DWORD]
    k32.K32GetProcessMemoryInfo(k32.GetCurrentProcess(), ctypes.byref(c), c.cb)
    return {"peak_working_set_gb": round(c.PeakWorkingSetSize / 2**30, 2), "peak_committed_gb": round(c.PeakPagefileUsage / 2**30, 2)}


def cache_folder() -> Path:
    """``runs/cache``, or ``runs/<W92_CACHE>`` when that is set: a fresh folder holds W79's store as its runs left it
    (the domain's chunks), so the window's other chunks are decoded as on a job's first start."""
    cache = RUNS / os.environ.get("W92_CACHE", "cache")
    if not (cache / STORE).exists():
        (cache / STORE).mkdir(parents=True)
        for f in (SOURCE_CACHE / STORE).iterdir():
            if f.name == "source.json":
                shutil.copy2(f, cache / STORE / f.name)
            else:
                os.link(f, cache / STORE / f.name)
    return cache


def _sha(*parts) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(p if isinstance(p, bytes) else repr(p).encode())
    return h.hexdigest()[:24]


def digest(mask, strip) -> dict[str, str]:
    """A hash per field of the strip's mask and mesh: arrays by dtype, shape and bytes, polygons by WKB."""
    import numpy as np
    import shapely

    def arr(a):
        a = np.ascontiguousarray(a)
        return _sha(str(a.dtype), a.shape, a.tobytes())

    g = strip.geometry
    out = {"mask": arr(mask)}
    for name in ("x", "y", "ring_start", "ring_node", "face_node", "face_cell"):
        out[f"geometry.{name}"] = arr(getattr(g, name))
    out["masked"] = _sha(arr(strip.masked[0]), arr(strip.masked[1]))
    out["corridor"] = arr(strip.corridor)
    out["row"] = arr(strip.row)
    out["gorge"] = "none" if strip.gorge is None else arr(strip.gorge)
    out["breakline_edges"] = _sha(sorted((k, sorted(v)) for k, v in strip.breakline_edges.items()))
    out["polygons"] = _sha(*[shapely.to_wkb(p, hex=False) if not p.is_empty else b"empty" for p in strip.polygons])
    out["notes"] = _sha(list(strip.notes))
    out["rules"] = _sha(json.dumps(strip.rules, sort_keys=True, default=str))
    out["cells"] = str(g.ncells)
    return out


STAGES = [
    ("wadi2d.breaklines.window", "read_window"),
    ("wadi2d.breaklines.window", "domain_mask"),
    ("wadi2d.breaklines.window", "read_coarse"),
    ("wadi2d.strips.banks", "read_thalwegs"),
    ("wadi2d.strips.centres", "chain_streams"),
    ("wadi2d.strips.floor", "floor_of_line"),
    ("wadi2d.strips.centres", "place_centres"),
    ("wadi2d.strips.centres", "lattice_centres"),
    ("wadi2d.strips.centres", "_rings_of"),
    ("wadi2d.strips.centres", "Voronoi"),
    ("wadi2d.strips.centres", "regions_to_rings"),
    ("wadi2d.strips.centres", "shared_faces"),
    ("wadi2d.strips.centres", "_clip_to_hole"),
    ("wadi2d.strips.centres", "_contract_short_faces"),
    ("wadi2d.strips.centres", "_areas_centroids"),
    ("wadi2d.strips.centres", "build_centre_mesh"),
    ("wadi2d.strips.geometry.MeshGeometry", "from_rings"),
    ("wadi2d.strips.gorge", "split_gorge_rows"),
]


def wrap_stages(times: dict[str, list[float]]) -> None:
    import importlib

    for where, name in STAGES:
        parts = where.split(".")
        try:
            owner = importlib.import_module(where)
        except ImportError:
            owner = getattr(importlib.import_module(".".join(parts[:-1])), parts[-1])
        if not hasattr(owner, name):
            continue
        raw = owner.__dict__[name]
        is_class = isinstance(raw, classmethod)
        func = raw.__func__ if is_class else raw
        times[name] = [0.0, 0]

        def timed(*a, _f=func, _n=name, **k):
            t0 = time.perf_counter()
            try:
                return _f(*a, **k)
            finally:
                times[_n][0] += time.perf_counter() - t0
                times[_n][1] += 1

        setattr(owner, name, classmethod(timed) if is_class else timed)


def main() -> None:
    job, label = Path(sys.argv[1]), sys.argv[2]
    profile = "--profile" in sys.argv
    RUNS.mkdir(exist_ok=True)
    times: dict[str, list[float]] = {}
    wrap_stages(times)

    from wadi2d.demstore import open_bed
    from wadi2d.run import _domain_polygon, _wkt, grid_window, kept_domain_mask, left_out_of, load_job
    from wadi2d.strips.build import mask_for_strips
    from wadi2d.terrain.sections import with_tables

    cfg = with_tables(load_job(job))
    cache = cache_folder()
    t_all = time.perf_counter()
    with open_bed(cfg, cache) as bed:
        crs = _wkt(bed)
        window = grid_window(cfg, bed)
        left = left_out_of(cfg, crs)
        t0 = time.perf_counter()
        mask = kept_domain_mask(cfg, bed, window, cache)
        mask_s = time.perf_counter() - t0
        full = mask
        if left is not None and left.names:
            mask = mask & ~(left.cells(window.x0, window.y0, cfg.grid.dx, mask.shape) & mask)
        polygon = _domain_polygon(cfg.grid.domain, crs)
        if polygon is None:
            import shapely

            polygon = shapely.box(window.x0, window.y0 - mask.shape[0] * cfg.grid.dx, window.x0 + mask.shape[1] * cfg.grid.dx, window.y0)
        if left is not None and left.names:
            polygon = polygon.difference(left.area.buffer(cfg.grid.dx))
        prof = None
        if profile:
            import cProfile

            prof = cProfile.Profile()
            prof.enable()
        t0 = time.perf_counter()
        import inspect

        extra = {"domain_mask": full, "cache_dir": str(cache)} if "domain_mask" in inspect.signature(mask_for_strips).parameters else {}
        out, strip = mask_for_strips(cfg, mask, window.x0, window.y0, polygon, **extra)
        mesh_s = time.perf_counter() - t0
        if prof is not None:
            prof.disable()
    total_s = time.perf_counter() - t_all
    record = {
        "job": str(job), "label": label, "domain_mask_s": round(mask_s, 1), "mask_for_strips_s": round(mesh_s, 1),
        "total_s": round(total_s, 1), "stages": {k: [round(v[0], 2), v[1]] for k, v in times.items() if v[1]},
        "workers": os.environ.get("WADI2D_MESH_WORKERS", "default"), **peak_gb(), "digest": digest(out, strip),
    }  # fmt: skip
    (RUNS / f"{label}.json").write_text(json.dumps(record, indent=1), encoding="utf-8")
    with open(RUNS / f"{label}.mesh.pkl", "wb") as f:
        pickle.dump((out, strip), f, protocol=pickle.HIGHEST_PROTOCOL)
    if prof is not None:
        import io
        import pstats

        text = io.StringIO()
        st = pstats.Stats(prof, stream=text)
        st.sort_stats("cumulative").print_stats(45)
        st.sort_stats("tottime").print_stats(30)
        (RUNS / f"{label}.prof.txt").write_text(text.getvalue(), encoding="utf-8")
    print(json.dumps({k: v for k, v in record.items() if k != "digest"}, indent=1))


if __name__ == "__main__":
    main()
