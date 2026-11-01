"""swe_bench.py - Wadi2D micro-benchmark: an explicit second-order SWE step on the GPU through CuPy + NVRTC.

Throwaway benchmark, not the product. Measures ms per step and giga cell updates per second (GCUPS) of a
MUSCL-Hancock and an SSP-RK2 step (minmod MUSCL, hydrostatic reconstruction, HLLC, point-implicit Manning,
adaptive CFL time step) in three kernel organisations (fused, split, tiled) on closed boxes of 1024^2, 2048^2
and 4096^2 cells, wet and all-dry-with-a-patch. Writes results.json next to this script. Kernels: swe_kernels.cu.

Usage:  python swe_bench.py            (full matrix, about 2 minutes)
        python swe_bench.py --quick    (small grids, cross-checks only)
"""
from __future__ import annotations

import argparse
import json
import math
import platform
import sys
import time
import warnings
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore", category=UserWarning)
import cupy as cp  # noqa: E402
from cupy.cuda import runtime as rt  # noqa: E402

HERE = Path(__file__).resolve().parent
SRC = (HERE / "swe_kernels.cu").read_text(encoding="utf-8")
KERNEL_NAMES = ["ghost_x", "ghost_y", "cfl_partial", "cfl_final", "rk2_fused", "mh_fused",
                "recon_cells", "flux_x", "flux_y", "update_cells", "rk2_tiled", "mh_tiled"]
G = 9.81
HEPS = 1e-4
CFL = 0.45
DT_MAX = 10.0
BLOCK = (32, 8)
CFL_BLOCKS = 1024
I32, F32 = np.int32, np.float32


def grid2d(nx: int, ny: int, bs=BLOCK):
    return ((nx + bs[0] - 1) // bs[0], (ny + bs[1] - 1) // bs[1])


class Kernels:
    """One NVRTC module per (fast_math, early_exit) combination."""

    def __init__(self, fast_math: bool, early_exit: bool):
        opts = ["-std=c++17", f"-DEARLY_EXIT={1 if early_exit else 0}"]
        if fast_math:
            opts.append("--use_fast_math")
        self.fast_math, self.early_exit = fast_math, early_exit
        t0 = time.perf_counter()
        self.mod = cp.RawModule(code=SRC, options=tuple(opts))
        self.k = {n: self.mod.get_function(n) for n in KERNEL_NAMES}
        self.compile_s = time.perf_counter() - t0

    def resources(self) -> dict:
        return {n: {"regs": f.num_regs, "local_bytes": f.local_size_bytes, "shared_bytes": f.shared_size_bytes}
                for n, f in self.k.items()}


class Domain:
    """Closed box, sloping (0.5 % in x, high in the west) bumpy bed (+-0.5 m), 2-cell ghost frame."""

    def __init__(self, nx: int, ny: int, dx: float, kind: str, seed: int = 1):
        self.nx, self.ny, self.dx, self.kind = nx, ny, dx, kind
        self.sx = nx + 4
        self.shape = (ny + 4, nx + 4)
        rs = cp.random.RandomState(seed)
        from cupyx.scipy.ndimage import uniform_filter
        ii = cp.arange(nx, dtype=cp.float32)[None, :]
        jj = cp.arange(ny, dtype=cp.float32)[:, None]
        slope = (0.005 * dx) * (nx - 1 - ii)
        noise = rs.uniform(-1.0, 1.0, size=(ny, nx)).astype(cp.float32)
        noise = uniform_filter(noise, size=5, mode="reflect")
        noise *= F32(0.5) / cp.abs(noise).max()
        z = cp.zeros(self.shape, cp.float32)
        z[2:-2, 2:-2] = slope + noise
        h = cp.zeros(self.shape, cp.float32)
        if kind == "wet":
            sig = 0.1 * nx
            r2 = (ii - nx / 2) ** 2 + (jj - ny / 2) ** 2
            # flat-ish water surface: 1 m above the sloping plane plus the mound, so depth = 1 + mound - bump >= 0.5 m
            h[2:-2, 2:-2] = cp.maximum(1.0 + 3.0 * cp.exp(-r2 / (2 * sig * sig)) - noise, 0.0)
        elif kind == "dry":
            p = 300
            r0, c0 = ny // 2 - p // 2, nx // 2 - p // 2
            hi = cp.zeros((ny, nx), cp.float32)
            hi[r0:r0 + p, c0:c0 + p] = 2.0 - noise[r0:r0 + p, c0:c0 + p]   # flat surface 2 m above the plane
            h[2:-2, 2:-2] = hi
        else:
            raise ValueError(kind)
        self.z, self.h0 = z, h
        self.hu0 = cp.zeros(self.shape, cp.float32)
        self.hv0 = cp.zeros(self.shape, cp.float32)
        self.mass0 = float(cp.sum(h[2:-2, 2:-2], dtype=cp.float64)) * dx * dx
        self.wet0 = float(cp.count_nonzero(h[2:-2, 2:-2] >= HEPS)) / (nx * ny)

    def fill_z_ghosts(self, K: Kernels):
        dummy = cp.zeros(self.shape, cp.float32)
        n1 = max(self.nx, self.ny) + 4
        args = (dummy, dummy, dummy, self.z, I32(self.nx), I32(self.ny), I32(self.sx), I32(1))
        K.k["ghost_x"](((n1 + 255) // 256,), (256,), args)
        K.k["ghost_y"](((n1 + 255) // 256,), (256,), args)


class Stepper:
    """One time step of a given integrator ('mh' | 'rk2') and organisation ('fused' | 'split' | 'tiled').

    cfl: 'custom' (two-pass kernels, dt stays on the device), 'cupy' (cupy.ReductionKernel), 'fixed' (no
    reduction, dt constant), 'host' (custom + float(dt) read back every step).
    """

    def __init__(self, K: Kernels, dom: Domain, integ: str, org: str, cfl: str = "custom", fixed_dt: float = 0.5):
        self.K, self.dom, self.integ, self.org, self.cfl_mode = K, dom, integ, org, cfl
        self.fixed_dt = fixed_dt
        if org == "tiled":
            assert dom.nx % 32 == 0 and dom.ny % 32 == 0, "tiled kernels need nx, ny multiples of 32"
        sh = dom.shape
        self.A = [cp.empty(sh, cp.float32) for _ in range(3)]
        self.B = [cp.empty(sh, cp.float32) for _ in range(3)]
        self.C = [cp.empty(sh, cp.float32) for _ in range(3)] if integ == "rk2" else None
        if org == "split":
            npad = sh[0] * sh[1]
            self.fs = cp.empty((16, npad), cp.float32)
            self.fx = cp.zeros((5, npad), cp.float32)
            self.fy = cp.zeros((5, npad), cp.float32)
        self.partial = cp.zeros(CFL_BLOCKS, cp.float32)
        self.dt_dev = cp.full(1, fixed_dt, cp.float32)
        self.red = cp.ReductionKernel(
            "float32 h, float32 hu, float32 hv", "float32 m", "_speed(h, hu, hv)",
            "max(a, b)", "m = a", "0.0f", "cfl_speed_max",
            preamble="__device__ float _speed(float h, float hu, float hv) { if (h < 1e-4f) return 0.f; "
                     "float u = hu / h, v = hv / h; return fmaxf(fabsf(u), fabsf(v)) + sqrtf(9.81f * h); }")
        self.dt_from = cp.ElementwiseKernel("float32 s, float32 cfl_dx, float32 dtmax", "float32 dt",
                                            "dt = (s > 1e-6f) ? fminf(dtmax, cfl_dx / s) : dtmax", "dt_from_smax")
        self.n_launch = 0
        self.reset()

    # -- buffers -------------------------------------------------------------------------------------
    def reset(self):
        d = self.dom
        self.A[0][...] = d.h0; self.A[1][...] = d.hu0; self.A[2][...] = d.hv0
        self.cur, self.aux = self.A, self.B
        self.dt_dev[...] = self.fixed_dt

    def current(self):
        return self.cur

    # -- pieces --------------------------------------------------------------------------------------
    def ghosts(self, U):
        d, K = self.dom, self.K
        n1 = max(d.nx, d.ny) + 4
        args = (U[0], U[1], U[2], d.z, I32(d.nx), I32(d.ny), I32(d.sx), I32(0))
        K.k["ghost_x"](((n1 + 255) // 256,), (256,), args)
        K.k["ghost_y"](((n1 + 255) // 256,), (256,), args)
        self.n_launch += 2

    def cfl(self, U):
        d, K = self.dom, self.K
        mode = self.cfl_mode
        if mode == "fixed":
            return
        if mode in ("custom", "host"):
            K.k["cfl_partial"]((min(CFL_BLOCKS, d.ny),), (256,),
                               (U[0], U[1], U[2], I32(d.nx), I32(d.ny), I32(d.sx), self.partial))
            K.k["cfl_final"]((1,), (1024,), (self.partial, I32(min(CFL_BLOCKS, d.ny)), self.dt_dev,
                                               F32(CFL * d.dx), F32(DT_MAX)))
            self.n_launch += 2
            if mode == "host":
                self.last_dt = float(self.dt_dev[0])
        elif mode == "cupy":
            smax = self.red(U[0][2:-2, 2:-2], U[1][2:-2, 2:-2], U[2][2:-2, 2:-2])   # strided interior views
            self.dt_from(smax, F32(CFL * d.dx), F32(DT_MAX), self.dt_dev)
            self.n_launch += 2

    def _common(self):
        d = self.dom
        return I32(d.nx), I32(d.ny), I32(d.sx), F32(d.dx)

    def stage(self, Uin, Uprev, Uout, a: float, b: float):
        """RK2 stage (a, b) or, for MH, one full flux update (a=0, b=1)."""
        d, K = self.dom, self.K
        nx, ny, sx, dx = self._common()
        g = grid2d(d.nx, d.ny)
        if self.org == "fused":
            if self.integ == "mh":
                K.k["mh_fused"](g, BLOCK, (Uin[0], d.z, Uin[1], Uin[2], Uout[0], Uout[1], Uout[2],
                                           self.dt_dev, nx, ny, sx, dx))
            else:
                K.k["rk2_fused"](g, BLOCK, (Uin[0], d.z, Uin[1], Uin[2], Uprev[0], Uprev[1], Uprev[2],
                                            Uout[0], Uout[1], Uout[2], self.dt_dev, nx, ny, sx, dx, F32(a), F32(b)))
            self.n_launch += 1
        elif self.org == "tiled":
            gt = (d.nx // 32, d.ny // 32)
            if self.integ == "mh":
                K.k["mh_tiled"](gt, BLOCK, (Uin[0], d.z, Uin[1], Uin[2], Uout[0], Uout[1], Uout[2],
                                            self.dt_dev, nx, ny, sx, dx))
            else:
                K.k["rk2_tiled"](gt, BLOCK, (Uin[0], d.z, Uin[1], Uin[2], Uprev[0], Uprev[1], Uprev[2],
                                             Uout[0], Uout[1], Uout[2], self.dt_dev, nx, ny, sx, dx, F32(a), F32(b)))
            self.n_launch += 1
        else:  # split
            K.k["recon_cells"](grid2d(d.nx + 2, d.ny + 2), BLOCK,
                               (Uin[0], d.z, Uin[1], Uin[2], self.fs, self.dt_dev, nx, ny, sx, dx,
                                I32(1 if self.integ == "mh" else 0)))
            K.k["flux_x"](grid2d(d.nx + 1, d.ny), BLOCK, (self.fs, self.fx, nx, ny, sx))
            K.k["flux_y"](grid2d(d.nx, d.ny + 1), BLOCK, (self.fs, self.fy, nx, ny, sx))
            K.k["update_cells"](g, BLOCK, (Uin[0], Uin[1], Uin[2], Uprev[0], Uprev[1], Uprev[2],
                                           Uout[0], Uout[1], Uout[2], self.fs, self.fx, self.fy, self.dt_dev,
                                           nx, ny, sx, dx, F32(a), F32(b)))
            self.n_launch += 4

    def step(self):
        U = self.cur
        self.ghosts(U)
        self.cfl(U)
        if self.integ == "mh":
            self.stage(U, U, self.aux, 0.0, 1.0)
            self.cur, self.aux = self.aux, self.cur
        else:
            U1 = self.aux
            self.stage(U, U, U1, 0.0, 1.0)
            self.ghosts(U1)
            self.stage(U1, U, self.C, 0.5, 0.5)
            self.cur, self.C = self.C, self.cur


# ---------------------------------------------------------------------------------------------- harness
def timed(fn, stream, n: int) -> float:
    """ms per call of fn, measured with CUDA events on the stream (fn must launch on that stream)."""
    s, e = cp.cuda.Event(), cp.cuda.Event()
    s.record(stream)
    for _ in range(n):
        fn()
    e.record(stream)
    e.synchronize()
    return cp.cuda.get_elapsed_time(s, e) / n


def state_checks(st: Stepper) -> dict:
    d = st.dom
    h, hu, hv = st.current()
    hi, hui, hvi = h[2:-2, 2:-2], hu[2:-2, 2:-2], hv[2:-2, 2:-2]
    wet = hi >= HEPS
    nwet = int(cp.count_nonzero(wet))
    mass = float(cp.sum(hi, dtype=cp.float64)) * d.dx * d.dx
    hs = cp.where(wet, hi, F32(1.0))
    sp = cp.where(wet, cp.sqrt((hui / hs) ** 2 + (hvi / hs) ** 2), F32(0.0))
    return {
        "nan": bool(cp.isnan(hi).any() or cp.isnan(hui).any() or cp.isnan(hvi).any()),
        "mass_rel_change": (mass - d.mass0) / d.mass0,
        "wet_fraction_end": nwet / (d.nx * d.ny),
        "max_depth_m": float(hi.max()),
        "max_speed_m_s": float(sp.max()),
        "dt_end_s": float(st.dt_dev[0]),
    }


def measure(st: Stepper, stream, nsteps: int = 200, warm: int = 20, graph: bool = False) -> dict:
    st.reset()
    st.n_launch = 0
    with stream:
        for _ in range(warm):
            st.step()
        stream.synchronize()
        launches_per_step = st.n_launch / warm
        if graph:
            stream.begin_capture()
            st.step(); st.step()
            g = stream.end_capture()
            if hasattr(g, "upload"):
                g.upload(stream)
            ms = timed(lambda: g.launch(stream), stream, nsteps // 2) / 2
            nsteps = (nsteps // 2) * 2
        else:
            ms = timed(st.step, stream, nsteps)
        stream.synchronize()
    d = st.dom
    out = {"ms_per_step": ms, "gcups": d.nx * d.ny / ms / 1e6, "steps_timed": nsteps, "warm_up_steps": warm,
           "launches_per_step": launches_per_step, "graph": graph}
    out.update(state_checks(st))
    return out


def components(K: Kernels, dom: Domain, stream, n: int = 200) -> dict:
    """Cost of the pieces around the step kernels, on the wet state after 20 fused RK2 steps."""
    st = Stepper(K, dom, "rk2", "fused", cfl="custom")
    with stream:
        for _ in range(20):
            st.step()
        stream.synchronize()
        U = st.current()
        res = {"ghost_fill_ms": timed(lambda: st.ghosts(U), stream, n)}
        st.cfl_mode = "custom"
        res["cfl_custom_two_pass_ms"] = timed(lambda: st.cfl(U), stream, n)
        st.cfl_mode = "cupy"
        res["cfl_cupy_reduction_ms"] = timed(lambda: st.cfl(U), stream, n)
        st.cfl_mode = "host"
        t0 = time.perf_counter()
        for _ in range(n):
            st.cfl(U)
        res["cfl_custom_plus_host_readback_ms"] = (time.perf_counter() - t0) / n * 1e3
        res["dt_custom_s"] = float(st.dt_dev[0])
        st.cfl_mode = "cupy"; st.cfl(U); stream.synchronize()
        res["dt_cupy_s"] = float(st.dt_dev[0])
        # Python launch overhead of one fused stage, measured on a tiny grid (GPU idle), for reference
        t0 = time.perf_counter()
        for _ in range(n):
            K.k["ghost_x"]((1,), (32,), (U[0], U[1], U[2], dom.z, I32(dom.nx), I32(dom.ny), I32(dom.sx), I32(0)))
        stream.synchronize()
        res["python_launch_overhead_us"] = (time.perf_counter() - t0) / n * 1e6
    return res


def crosscheck(K: Kernels, nx: int, ny: int, nsteps: int, stream) -> dict:
    """Max |dh| between organisations after nsteps on a small wet box; all three run the same arithmetic,
    so the differences must be round-off (fast-math reassociation) only. Also MH vs RK2 for scale."""
    dom = Domain(nx, ny, 10.0, "wet", seed=3)
    dom.fill_z_ghosts(K)
    out = {"domain": f"{nx}x{ny}", "steps": nsteps}
    ref = {}
    for integ in ("mh", "rk2"):
        hs = {}
        for org in ("fused", "split", "tiled"):
            st = Stepper(K, dom, integ, org, cfl="custom")
            with stream:
                for _ in range(nsteps):
                    st.step()
                stream.synchronize()
            hs[org] = st.current()[0][2:-2, 2:-2].copy()
            chk = state_checks(st)
            out[f"{integ}-{org}"] = {"nan": chk["nan"], "mass_rel_change": chk["mass_rel_change"],
                                     "max_depth_m": chk["max_depth_m"], "max_speed_m_s": chk["max_speed_m_s"],
                                     "dt_end_s": chk["dt_end_s"]}
        out[f"{integ}: max|dh| split-fused"] = float(cp.abs(hs["split"] - hs["fused"]).max())
        out[f"{integ}: max|dh| tiled-fused"] = float(cp.abs(hs["tiled"] - hs["fused"]).max())
        ref[integ] = hs["fused"]
    out["max|dh| mh-rk2 (scheme difference, for scale)"] = float(cp.abs(ref["mh"] - ref["rk2"]).max())
    out["max depth (scale)"] = float(ref["mh"].max())
    return out


# ---------------------------------------------------------------------------------------------- the matrix
def device_info() -> dict:
    p = rt.getDeviceProperties(0)
    name = p["name"].decode() if isinstance(p["name"], bytes) else str(p["name"])
    return {"name": name, "compute_capability": f"{p['major']}.{p['minor']}", "sm_count": int(p["multiProcessorCount"]),
            "total_mem_GB": round(p["totalGlobalMem"] / 2 ** 30, 2), "l2_MB": round(p["l2CacheSize"] / 2 ** 20, 1),
            "cupy": cp.__version__, "cuda_runtime": rt.runtimeGetVersion(), "cuda_driver": rt.driverGetVersion(),
            "nvrtc": list(cp.cuda.nvrtc.getVersion()), "python": sys.version.split()[0], "platform": platform.platform()}


def run_matrix(quick: bool, nsteps: int) -> dict:
    t_all = time.perf_counter()
    stream = cp.cuda.Stream(non_blocking=True)
    results: dict = {"device": device_info(), "settings": {
        "dx_m": 10.0, "cfl": CFL, "dt_max_s": DT_MAX, "manning_n": 0.03, "wet_dry_threshold_m": HEPS,
        "block": list(BLOCK), "tile": "32x32 cells, 2-cell halo, 32x8 threads (4 cells per thread)",
        "steps_timed": nsteps, "warm_up_steps": 20, "timing": "CUDA events on a non-blocking stream"},
        "cases": [], "notes": []}
    K_fm = Kernels(True, False)
    results["compile"] = {"nvrtc_compile_s_fast_math": round(K_fm.compile_s, 2), "kernels": K_fm.resources()}
    log = lambda *a: print(f"[{time.perf_counter() - t_all:6.1f} s]", *a, flush=True)

    # correctness cross-check first
    results["crosscheck"] = crosscheck(K_fm, 512, 512, 100, stream)
    log("crosscheck:", json.dumps({k: v for k, v in results["crosscheck"].items() if "max" in k}))
    if quick:
        sizes = [(512, "wet"), (512, "dry")]
    else:
        sizes = [(2048, "wet"), (2048, "dry"), (1024, "wet"), (4096, "wet")]
    K_nofm = Kernels(False, False)
    K_ee = Kernels(True, True)
    results["compile"]["nvrtc_compile_s_no_fast_math"] = round(K_nofm.compile_s, 2)
    results["compile"]["kernels_no_fast_math"] = K_nofm.resources()
    results["compile"]["kernels_early_exit"] = K_ee.resources()

    def run(K, dom, integ, org, cfl="custom", graph=False, fixed_dt=0.5, tag=""):
        try:
            st = Stepper(K, dom, integ, org, cfl=cfl, fixed_dt=fixed_dt)
            r = measure(st, stream, nsteps=nsteps, graph=graph)
            del st
        except Exception as e:  # noqa: BLE001
            r = {"error": repr(e)[:500]}
        r.update({"integrator": integ, "organisation": org, "domain": f"{dom.nx}x{dom.ny}", "cells": dom.nx * dom.ny,
                  "kind": dom.kind, "fast_math": K.fast_math, "early_exit": K.early_exit, "cfl": cfl, "tag": tag})
        results["cases"].append(r)
        if "error" in r:
            log(f"{integ:3s} {org:5s} {dom.nx}^2 {dom.kind:3s} fm={int(K.fast_math)} ee={int(K.early_exit)} "
                f"cfl={cfl:6s} graph={int(graph)}  ERROR {r['error'][:120]}")
        else:
            log(f"{integ:3s} {org:5s} {dom.nx}^2 {dom.kind:3s} fm={int(K.fast_math)} ee={int(K.early_exit)} "
                f"cfl={cfl:6s} graph={int(graph)}  {r['ms_per_step']:8.3f} ms  {r['gcups']:6.2f} GCUPS  "
                f"dt={r['dt_end_s']:.3f} s  mass={r['mass_rel_change']:+.1e}  wet={r['wet_fraction_end']:.3f}  "
                f"nan={r['nan']}")
        cp.get_default_memory_pool().free_all_blocks()
        return r

    for n, kind in sizes:
        dom = Domain(n, n, 10.0, kind)
        dom.fill_z_ghosts(K_fm)
        log(f"domain {n}^2 {kind}: wet fraction {dom.wet0:.3f}, mass {dom.mass0:.4e} m3")
        big = (n >= 4096)
        orgs = ("fused", "tiled") if big else ("fused", "split", "tiled")
        dt_ref = {}
        for integ in ("mh", "rk2"):
            for org in orgs:
                r = run(K_fm, dom, integ, org)
                if org == "fused" and "dt_end_s" in r:
                    dt_ref[integ] = r["dt_end_s"]
        if kind == "wet" and n in (2048, 512):
            for integ in ("mh", "rk2"):
                for org in ("fused", "tiled"):
                    run(K_nofm, dom, integ, org)
            for integ in ("mh", "rk2"):
                fd = 0.9 * dt_ref.get(integ, 0.5)
                run(K_fm, dom, integ, "fused", cfl="fixed", fixed_dt=fd, tag=f"fixed dt {fd:.3f} s")
                run(K_fm, dom, integ, "fused", cfl="cupy")
                run(K_fm, dom, integ, "fused", cfl="host")
            results["components"] = components(K_fm, dom, stream)
            log("components:", json.dumps({k: round(v, 4) for k, v in results["components"].items()}))
        if kind == "dry":
            for integ in ("mh", "rk2"):
                for org in ("fused", "tiled"):
                    run(K_ee, dom, integ, org)
        if kind == "wet" and n in (1024, 2048, 512):
            for integ in ("mh", "rk2"):
                run(K_fm, dom, integ, "fused", graph=True)
                if n == 2048:
                    run(K_fm, dom, integ, "tiled", graph=True)
        del dom
        cp.get_default_memory_pool().free_all_blocks()
    results["total_wall_s"] = round(time.perf_counter() - t_all, 1)
    return results


# ---------------------------------------------------------------------------------------------- README
def fmt_row(r: dict) -> str:
    if "error" in r:
        return f"| {r['integrator']} | {r['organisation']} | {r['domain']} {r['kind']} | not done: {r['error'][:60]} | | | | |"
    flags = []
    if not r["fast_math"]:
        flags.append("no fast-math")
    if r["early_exit"]:
        flags.append("early exit")
    if r["cfl"] != "custom":
        flags.append(f"cfl={r['cfl']}")
    if r["graph"]:
        flags.append("CUDA graph")
    return (f"| {r['integrator'].upper()} | {r['organisation']} | {r['domain']} {r['kind']} | {', '.join(flags) or '-'} | "
            f"{r['ms_per_step']:.3f} | {r['gcups']:.2f} | {r['dt_end_s']:.3f} | {r['mass_rel_change']:+.1e} | "
            f"{r['wet_fraction_end']:.3f} | {'yes' if r['nan'] else 'no'} |")


def write_readme(res: dict, path: Path):
    d = res["device"]
    hdr = ("| Integrator | Organisation | Domain | Flags | ms/step | GCUPS | dt end (s) | mass rel. change | wet fraction end | NaN |\n"
           "|---|---|---|---|---|---|---|---|---|---|\n")
    cases = res["cases"]
    groups = [
        ("2048 x 2048 wet, fast-math, adaptive dt (two-pass custom reduction)",
         [r for r in cases if r["domain"] == "2048x2048" and r["kind"] == "wet" and r["fast_math"] and not r["early_exit"]
          and r["cfl"] == "custom" and not r["graph"]]),
        ("2048 x 2048 wet, fast-math off",
         [r for r in cases if r["domain"] == "2048x2048" and r["kind"] == "wet" and not r["fast_math"]]),
        ("2048 x 2048 wet, cost of the CFL reduction (fused kernels)",
         [r for r in cases if r["domain"] == "2048x2048" and r["kind"] == "wet" and r["cfl"] != "custom"]),
        ("CUDA graph (one graph = two captured steps, launched 100 times)",
         [r for r in cases if r["graph"]]),
        ("2048 x 2048 all dry except a 300 x 300 wet patch (dry-cell cost and the active-cell early exit)",
         [r for r in cases if r["kind"] == "dry"]),
        ("Scaling of the fused and tiled kernels with domain size (wet, fast-math, adaptive dt)",
         [r for r in cases if r["kind"] == "wet" and r["cfl"] == "custom" and not r["graph"] and r["fast_math"]
          and r["domain"] in ("1024x1024", "2048x2048", "4096x4096") and r["organisation"] in ("fused", "tiled")
          and not r["early_exit"]]),
    ]
    L = [f"# SWE kernel micro-benchmark on the {d['name']}\n",
         f"Measured on {time.strftime('%Y-%m-%d')} with CuPy {d['cupy']} (CUDA runtime {d['cuda_runtime']}, driver {d['cuda_driver']}, "
         f"NVRTC {'.'.join(map(str, d['nvrtc']))}, compute capability {d['compute_capability']}, {d['sm_count']} SMs). "
         f"All numbers below are measured [Certain]; the script is `swe_bench.py`, the kernels `swe_kernels.cu`, "
         f"the raw output `results.json`. Throwaway benchmark: plausibility checks only (no NaN, mass conserved on the closed box, "
         f"the three organisations agree to round-off), no validation.\n",
         "## Results\n",
         "ms/step is one full time step (ghost fill + CFL reduction + all stage kernels; RK2 = two flux evaluations). "
         "GCUPS = interior cells / step time (giga cell updates per second). Mass change is relative, over the whole run "
         "(20 warm-up + timed steps). 200 timed steps after 20 warm-up steps, CUDA-event timing.\n"]
    for title, rows in groups:
        if rows:
            L.append(f"### {title}\n")
            L.append(hdr + "\n".join(fmt_row(r) for r in rows) + "\n")
    c = res.get("components", {})
    if c:
        L.append("### Pieces around the step kernels (2048 x 2048 wet, per step)\n")
        L.append("| Piece | ms |\n|---|---|\n" + "\n".join(
            f"| {k} | {v:.4f} |" for k, v in c.items() if k.endswith("_ms")) +
            f"\n| Python launch overhead of one tiny kernel (us) | {c.get('python_launch_overhead_us', float('nan')):.1f} |\n")
    x = res["crosscheck"]
    L.append("### Cross-check of the organisations (512 x 512 wet, 100 steps)\n")
    L.append("| Quantity | Value |\n|---|---|\n" + "\n".join(
        f"| {k} | {v:.3e} |" for k, v in x.items() if isinstance(v, float)) + "\n")
    k = res["compile"]["kernels"]
    L.append("### Kernel resources (fast-math build)\n")
    L.append("| Kernel | Registers | Local (spill) bytes | Static shared bytes |\n|---|---|---|---|\n" + "\n".join(
        f"| {n} | {v['regs']} | {v['local_bytes']} | {v['shared_bytes']} |" for n, v in k.items()) + "\n")
    L.append(METHOD)
    L.append(f"\nTotal wall time of the run: {res.get('total_wall_s', 0)} s.\n")
    path.write_text("\n".join(L), encoding="utf-8")


METHOD = """## Method

**State and grid.** Uniform grid, dx = dy = 10 m, float32, depth-based state (h, hu, hv) with the bed z as a fourth
array; the water level eta = h + z is formed in registers only (decision 3). Every array carries a 2-cell ghost frame;
the walls are reflective ghosts (normal discharge negated), refilled by a small kernel before every flux evaluation.

**Scheme.** Per face: MUSCL reconstruction with the minmod limiter of eta, h, hu and hv (z at the face = eta - h), first
order where the cell or a neighbour is dry; hydrostatic reconstruction at the face (Audusse et al. 2004); HLLC with the
two-rarefaction wave-speed estimates and the dry-bed cases; the Audusse face source terms plus the centred bed-slope
term (Audusse and Bristeau 2005), which makes still water on the bumpy sloping bed exact; point-implicit Manning
friction (n = 0.03, h^(4/3) via cbrtf) after the flux update; wet/dry threshold 1e-4 m; adaptive global time step
dt = 0.45 dx / max(max(|u|,|v|) + c) from a min-reduction over the wet cells, kept on the device (the kernels read dt
from a device pointer; no host synchronisation).

**Integrators.** MH = MUSCL-Hancock: the four reconstructed faces of a cell are advanced by dt/2 with the cell's own
flux divergence and bed-slope term, then one HLLC per face; one flux evaluation per step. RK2 = SSP-RK2 (Heun):
two flux evaluations per step, friction applied inside each stage.

**Organisations.** (1) *fused*: one kernel per flux evaluation computes the four face fluxes of its cell and updates
the cell; the neighbours' face states are recomputed (RK2: 9-cell cross stencil; MH: 13-cell stencil because the
neighbour's predictor needs its own neighbours), no intermediate arrays. (2) *split*: a reconstruction (+ predictor)
kernel writes the four face states of every cell (16 floats per cell), two flux kernels write the x and y face fluxes
and the face source terms (5 floats per face), an update kernel reads them back: the classic layout, every face
computed once, at the price of about 250 bytes per cell of global traffic instead of 28. (3) *tiled*: 32 x 32 cells per
block loaded with a 2-cell halo into shared memory (36 x 36 x 4 arrays = 20.7 KB); RK2: every face computed once into a
shared flux buffer (x pass, then y pass reusing the buffer, 21 KB); MH: the predictor is computed once per cell per pass
into shared memory (26 KB, faces stored without z, z recomputed) and the four face fluxes per owned cell. Block of
32 x 8 threads, four cells per thread; static shared memory stays under 48 KB.

**Domains.** Closed box of 2048 x 2048 cells (4.19 M) of 10 m, bed sloping 0.5 % in x plus smoothed random bumps of
+-0.5 m. Wet case: 1 m of water everywhere plus a Gaussian mound of 3 m (sigma 0.1 nx) at the centre, water starts at
rest and reaches its friction equilibrium (about 2 m/s) within the run. Dry case: the same bed dry except a 300 x 300
cell patch 2 m deep at the centre, which spreads during the run. 1024 x 1024 and 4096 x 4096 wet boxes for scaling.

**Early exit.** Fused kernels: a cell whose 5-cell cross (itself and the four neighbours) is dry copies its state and
returns (the fluxes on its four faces are exactly zero, also for the MH predictor, so this is consistent). Tiled
kernels: a block whose whole 36 x 36 tile is dry writes through and returns (`__syncthreads_or`). The split kernels have
no early exit.

**Timing.** 20 warm-up steps, then 200 timed steps between CUDA events on a non-blocking stream. The CUDA-graph
variant captures two consecutive steps (so the ping-pong buffers return to their roles) and launches the graph 100
times. The 'fixed' CFL mode uses 0.9 x the adaptive dt of the matching run; 'cupy' uses a `cupy.ReductionKernel`
instead of the two custom kernels; 'host' adds a `float(dt)` read-back every step (a full pipeline drain).
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="small grids, cross-checks only")
    ap.add_argument("--steps", type=int, default=200)
    ap.add_argument("--out", default=str(HERE / "results.json"))
    a = ap.parse_args()
    res = run_matrix(a.quick, a.steps)
    Path(a.out).write_text(json.dumps(res, indent=2, default=float), encoding="utf-8")
    if not a.quick:
        write_readme(res, HERE / "README.md")
    print("wrote", a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
