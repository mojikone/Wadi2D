# Wadi2D. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The hybrid step: square tiles and a polygon strip in one time step (W45, stage 3 on the CPU, stage 5 on the GPU).

The tile backend steps its faces and positivity as ever; in its ``before_update`` hook the strip mirrors the tile
cells it touches into its ghost entries (mean depth, level, wet share), adds those cells' lattice faces to the Perot
and Green-Gauss sums, steps its own faces, limits its outflows (a real cell gives what it holds; a ghost gives what its
lattice faces left it, so the books close), updates its real cells, and hands each ghost's net outflow to the tile
update as a source term; ``after_update`` restores the sources and writes each interface's discharge and velocity
into the tile's closed face on that edge, own slot and halo copies, so the next tile step's momentum stencil sees
the flow the strip carries across. One global time step: the smaller of the tile rule and the strip's. A tile that
holds a ghost is stepped while water, the strip's or the squares', can reach it before the next check of the active
list (W90, :mod:`wadi2d.strips.watch`); the strip itself is stepped whole.

What a ghost's lattice faces add [Likely the right form; measured by the stage gate]: the Perot sum of a square from its
four face discharges, the Green-Gauss gradient from its open wet faces' level differences, and the advection rate from its four lattice
faces' outflows times the upwind velocity, a neighbour's taken from that neighbour's own four faces.

:class:`Hybrid` holds what both backends share (the ghosts, their open faces, the interface edges, the run's hooks);
:class:`HybridCpu` steps the strip with the Numba kernels, :class:`wadi2d.strips.hybrid_gpu.HybridGpu` with the CUDA
twin; :func:`make_hybrid` picks by the model's backend.
"""

from __future__ import annotations

import numpy as np
from numba import njit

from wadi2d.solver.layout import CLOSED, HALO, STRIDE, STRIDE2, TILE
from wadi2d.solver.model import Model
from wadi2d.solver.poly import kernel
from wadi2d.solver.poly.mesh import PolyMesh
from wadi2d.solver.poly.model import PolyState
from wadi2d.solver.state import exchange_map, level_of, plan_of, state_index
from wadi2d.strips.geometry import MeshGeometry
from wadi2d.strips.tables import Ghosts
from wadi2d.tables.builder import GridTables, hbar_at_level

F = np.float32
ZERO, HALF = F(0.0), F(0.5)
AUTO_SUBSTEPS = 8
AUTO_SUBSTEP_CELLS = 2_000_000
"""Sub-cycling pays where the squares' step costs more than the strip's launches: Faydh 01 at 20 m (189,000 squares,
20,000 strip cells) ran 40 % slower with it, the strip taking its own steps whatever the squares do; the full extent
(17 M squares) stands to gain up to the strip's share of the step. The boundary is a guess from those two points."""


@njit(cache=True)
def ghost_sums(ng, nreal, ghost, dx, open_w, open_e, open_n, open_s, zmin, h, d, qx, qy, Ux, Uy, Gx, Gy) -> None:
    """A ghost's lattice part of the Perot sum and of the Green-Gauss sum, before the strip's faces add theirs."""
    for g in range(ng):
        c = nreal + g
        k = ghost[g]
        Ux[c] += HALF * dx * (qx[k] + qx[k + 1])
        Uy[c] -= HALF * dx * (qy[k] + qy[k + STRIDE])
        eta = zmin[k] + d[k]
        if open_w[g] and h[k - 1] > ZERO and h[k] > ZERO:
            Gx[c] += HALF * (eta - (zmin[k - 1] + d[k - 1])) * dx
        if open_e[g] and h[k + 1] > ZERO and h[k] > ZERO:
            Gx[c] += HALF * ((zmin[k + 1] + d[k + 1]) - eta) * dx
        if open_n[g] and h[k - STRIDE] > ZERO and h[k] > ZERO:
            Gy[c] -= HALF * (eta - (zmin[k - STRIDE] + d[k - STRIDE])) * dx
        if open_s[g] and h[k + STRIDE] > ZERO and h[k] > ZERO:
            Gy[c] -= HALF * ((zmin[k + STRIDE] + d[k + STRIDE]) - eta) * dx


@njit(cache=True)
def ghost_rates(ng, nreal, ghost, dx, u_max, open_w, open_e, open_n, open_s, h, qx, qy, Ux, Uy, Rx, Ry) -> None:
    """A ghost's lattice part of the advection rate: each lattice face's outflow times the upwind velocity, the
    ghost's own (complete by now) or the neighbour's Perot velocity from that neighbour's four lattice faces, held
    to the velocity cap as every cell vector is (W87)."""
    for g in range(ng):
        c = nreal + g
        k = ghost[g]
        # west face: inflow when qx[k] > 0
        for side in range(4):
            if side == 0:
                opened, q_out, n = open_w[g], -qx[k], k - 1
            elif side == 1:
                opened, q_out, n = open_e[g], qx[k + 1], k + 1
            elif side == 2:
                opened, q_out, n = open_n[g], -qy[k], k - STRIDE
            else:
                opened, q_out, n = open_s[g], qy[k + STRIDE], k + STRIDE
            if not opened or q_out == ZERO:
                continue
            if q_out > ZERO:
                ux, uy = Ux[c], Uy[c]
            else:
                vol = h[n] * dx * dx
                if vol > F(1e-9):
                    ux, uy = kernel.bounded(
                        HALF * dx * (qx[n] + qx[n + 1]) / vol, -HALF * dx * (qy[n] + qy[n + STRIDE]) / vol, u_max
                    )
                else:
                    ux, uy = ZERO, ZERO
            Rx[c] += q_out * ux
            Ry[c] += q_out * uy


@njit(cache=True)
def ghost_ratios(ng, nreal, ghost, dt_tile, dt, dx, h, r_tile, qx1, qy1, out, given, r) -> None:
    """A ghost gives through the strip's faces at most what its lattice faces, which come first, left it over the
    squares' step, less what it has already given in this step's earlier sub-steps."""
    area = dx * dx
    for g in range(ng):
        c = nreal + g
        k = ghost[g]
        lattice = max(qx1[k + 1], ZERO) + max(-qx1[k], ZERO) + max(qy1[k + STRIDE], ZERO) + max(-qy1[k], ZERO)
        have = max(h[k], ZERO) * area
        avail = max(have - dt_tile * r_tile[k] * lattice - given[g], ZERO)
        o = out[c]
        r[c] = avail / (o * dt) if o * dt > avail else F(1.0)


class Hybrid:
    """A tile model and a strip stepped together; installs itself as the tile backend's hooks. What the backends
    share: the ghosts and their open lattice faces, the interface edges, the strip's place in the run."""

    def __init__(self, model: Model, mesh: PolyMesh, substeps: int = 1) -> None:
        if mesh.ghost_state is None:
            raise ValueError("the strip has no ghosts: build its tables with the tile cells it touches")
        self.model = model
        self.mesh = mesh
        self.ghost = np.asarray(mesh.ghost_state, np.int64)
        self.nreal = mesh.real
        grid, tables = model.grid, model.tables
        self.dx = F(grid.dx)
        self.zmin_state = np.asarray(model.host.to_state(tables.zmin), F)
        flx, fly = grid.from_tiles(tables.flx), grid.from_tiles(tables.fly)
        j, i = self.cells_of(self.ghost)
        ny, nx = grid.shape
        self.open_w = flx[j, i] < CLOSED
        self.open_e = np.where(i + 1 < nx, flx[j, np.minimum(i + 1, nx - 1)] < CLOSED, False)
        self.open_n = fly[j, i] < CLOSED
        self.open_s = np.where(j + 1 < ny, fly[np.minimum(j + 1, ny - 1), i] < CLOSED, False)
        self._edges(mesh, grid)
        wanted = int(substeps)
        if wanted <= 0:
            wanted = AUTO_SUBSTEPS if int(grid.mask.sum()) >= AUTO_SUBSTEP_CELLS else 1
        self.k_max = max(wanted, 1)
        """How many strip steps may share one step of the squares; the squares' step is capped at that multiple."""
        self.strip_freq = 0.0
        """The strip's largest wave frequency of record, 1/s: what sets its own step."""
        self.b_faces = np.zeros(0, np.int64)
        """Interface faces whose ghost is a boundary cell: what crosses them has left the model (set by ``attach``)."""
        self.state = self.make_state()
        b = model.backend
        b.hooks = self
        tiles = np.unique(self.ghost // STRIDE2)
        model.stepper.pinned[tiles] = True  # a ghost's tile takes every smallest step while it is awake
        self.watch = None
        """Which tiles the strip's water can reach between two checks (W90); None on a quadtree, whose ghost tiles
        stay awake."""
        if getattr(grid, "quad", False):
            model.stepper.keep_active[tiles] = True
            self.always = tiles
            model.stepper.wake_rules.append(self._ghost_tiles)
        else:
            from wadi2d.strips.watch import build_watch

            self.watch = build_watch(mesh, grid, *self.cells_of(self.ghost), model.stepper.check_period())
            model.stepper.wake_rules.append(self.tiles_to_wake)
        model.stepper.rebuild_active(retain=True)

    def make_state(self):
        raise NotImplementedError

    def _ghost_tiles(self, wet: np.ndarray) -> np.ndarray:
        """The wake rule of a quadtree: every tile that holds a ghost and its neighbours, as before W90."""
        out = np.zeros(wet.size, bool)
        out[self.always] = True
        out[self.model.grid.nbr[self.always].ravel()] = True
        return out

    def tiles_to_wake(self, wet: np.ndarray) -> np.ndarray:
        """The stepper's wake rule: the tiles water can reach through the strip before the next check, from the
        tiles whose squares hold water or a source (``wet``) and from the strip's own wet cells."""
        return self.watch.tiles_to_wake(wet, self.strip_flags())

    def strip_flags(self) -> np.ndarray:
        """Per tile whether a strip cell with its centre there holds water or a source, on the host."""
        raise NotImplementedError

    def strip_changed(self) -> None:
        """The strip's water or sources were set from outside the step: wake what they can reach."""
        self.model.stepper.rebuild_active(retain=True)

    def _edges(self, mesh: PolyMesh, grid) -> None:
        """Each interface face's closed tile face: its state slot, the sign between the strip's normal and the
        lattice's eastward or southward discharge, and every state copy of that slot (own and halos)."""
        n = self.nreal
        iface = np.nonzero(mesh.right >= n)[0]
        g = self.ghost[mesh.right[iface] - n]
        nx, ny = mesh.nx[iface], mesh.ny[iface]
        east, west, south, north = nx > 0.5, nx < -0.5, ny < -0.5, ny > 0.5
        if not np.all(east | west | south | north):
            raise ValueError("an interface face must lie on a lattice edge")
        slot = np.where(east, g, np.where(west, g + 1, np.where(south, g, g + STRIDE)))
        sign = np.where(east | south, 1.0, -1.0).astype(F)
        dst, src = exchange_map(grid)
        copies: dict[int, list[int]] = {}
        for d_, s_ in zip(dst.tolist(), src.tolist(), strict=True):
            copies.setdefault(s_, []).append(d_)
        self.edge = {}
        for axis, on in (("x", east | west), ("y", south | north)):
            faces, slots, signs = iface[on], slot[on], sign[on]
            unique, group = np.unique(slots, return_inverse=True)
            all_copies = np.array([k for u in unique.tolist() for k in [u, *copies.get(u, [])]], np.int64)
            owner = np.array([m for m, u in enumerate(unique.tolist()) for _ in [u, *copies.get(u, [])]], np.int64)
            ghost_of = np.zeros(unique.size, np.int64)
            ghost_of[group] = self.ghost_slot(mesh, faces, n)
            self.edge[axis] = (faces, group, signs, unique, all_copies, owner, ghost_of)

    def ghost_slot(self, mesh: PolyMesh, faces: np.ndarray, n: int) -> np.ndarray:
        return mesh.right[faces] - n

    def cells_of(self, index: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Grid (j, i) of state indices."""
        grid = self.model.grid
        index = np.asarray(index, np.int64)
        t = index // STRIDE2
        rem = index % STRIDE2
        oj, oi = rem // STRIDE - HALO, rem % STRIDE - HALO
        return grid.tiles[t, 0] * TILE + oj, grid.tiles[t, 1] * TILE + oi

    # ---- the strip's own state, as the backends share it
    def strip_hbar_at_level(self, level: float | np.ndarray) -> np.ndarray:
        m, n = self.mesh, self.nreal
        return hbar_at_level(level, m.zmin[:n], m.hc[:n], m.dtab[:n])

    def substeps(self, dt: float) -> tuple[int, float]:
        """How many strip steps fit the squares' step ``dt`` at the strip's own rule, at most ``k_max``, and each."""
        num = self.model.num
        if self.k_max <= 1 or self.strip_freq <= 0.0:
            return 1, dt
        own = min(num.cfl / max(self.strip_freq, num.wave_floor / float(self.dx)), num.dt_max)
        k = int(min(max(np.ceil(dt / own - 1e-9), 1), self.k_max))
        return k, dt / k

    def cap_wave(self, freq: float) -> float:
        """The wave speed the squares' stepper reads for the strip: its step is capped at k_max strip steps."""
        return float(freq) * float(self.dx) / float(self.k_max)

    def forcing_cells(self) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """The real cells as the forcing takes them: centres, areas and lowest ground."""
        m, n = self.mesh, self.nreal
        return m.cx[:n], m.cy[:n], m.area[:n], m.zmin[:n]

    def strip_depth_real(self) -> np.ndarray:
        return self.strip_host("d")[: self.nreal]

    def strip_initial_depth(self, levels) -> tuple[np.ndarray, list[bool]]:
        """Mean depth of the real cells at the start, each polygon filling its cells to its level as the squares; and
        per polygon whether it wets a strip cell."""
        import shapely

        m, n = self.mesh, self.nreal
        out = np.zeros(n)
        wet = []
        for item in levels:
            inside = shapely.contains_xy(shapely.Polygon(item.coordinates), m.cx[:n], m.cy[:n])
            depth = np.zeros(0)
            if inside.any():
                depth = np.asarray(hbar_at_level(item.level, m.zmin[:n][inside], m.hc[:n][inside], m.dtab[:n][inside]))
                out[inside] = depth
            wet.append(bool((depth > 0.0).any()))
        return out, wet

    def strip_start(self, hbar: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Mean depth, level and wet share of the real cells for a depth."""
        m, n = self.mesh, self.nreal
        h = np.asarray(hbar, F)
        d = level_of(h.astype(np.float64), m.hc[:n], m.dtab[:n]).astype(F)
        om = plan_of(h.astype(np.float64), m.hc[:n], m.dtab[:n]).astype(F)
        self.model.stepper.refresh_due = True
        return h, d, om

    def strip_host(self, name: str) -> np.ndarray:
        """A strip array on the host (a copy on the GPU, the array itself on the CPU)."""
        raise NotImplementedError

    def strip_maxima(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """The largest depth and mean depth of each real cell and the largest discharge of each face, on the host."""
        raise NotImplementedError

    def strip_speed_maxima(self) -> tuple[np.ndarray, np.ndarray]:
        """The largest cell speed (where the cell is deeper than ``speed_depth``) and depth x speed, on the host."""
        raise NotImplementedError

    def strip_cell_speed(self) -> np.ndarray:
        """The speed of record at each real cell's centre now, on the host: from the faces' velocities, as the
        squares read theirs (W87), never the cell's momentum over its volume."""
        raise NotImplementedError

    def strip_frame_fields(self) -> dict[str, np.ndarray]:
        """The strip's cells in a saved map: level above zmin, mean depth and cell speed, each (1, n)."""
        n = self.nreal
        return {
            "strip_depth": self.strip_host("d")[:n][None, :],
            "strip_mean_depth": self.strip_host("h")[:n][None, :],
            "strip_speed": self.strip_cell_speed()[None, :],
        }

    def strip_maxima_fields(self) -> dict[str, np.ndarray]:
        max_d, max_h, _max_q = self.strip_maxima()
        max_s, max_dv = self.strip_speed_maxima()
        return {
            "strip_depth": max_d[None, :], "strip_mean_depth": max_h[None, :],
            "strip_speed": max_s[None, :], "strip_hazard": max_dv[None, :],
        }  # fmt: skip

    def strip_volume(self) -> float:
        """Water in the strip, the clamp residual of each cell included, as the tiles count theirs."""
        n = self.nreal
        h, res = self.strip_host("h")[:n].astype(np.float64), self.strip_host("res")[:n].astype(np.float64)
        return float(np.sum((h + res) * self.mesh.area[:n]))

    def volume(self) -> float:
        return self.model.volume() + self.strip_volume()

    def advance(self, t_end: float, on_step=None) -> float:
        return self.model.advance(t_end, on_step)

    # ---- the run's hooks
    def attach(self, monitor, strip, lines) -> None:
        """The strip's water in the balance, what it passes into boundary cells as outflow (a boundary cell's depth
        is reset after every step, so that water has left), and its faces in every result line that crosses it."""
        from wadi2d.forcing import line_faces
        from wadi2d.strips.build import line_crossings
        from wadi2d.strips.products import STRIP_MESH_FILE, write_strip_mesh

        monitor.extra_storage.append(self.strip_volume)
        j, i = self.cells_of(self.ghost)
        at_boundary = np.asarray(monitor.boundary.mask)[j, i]
        n = self.nreal
        iface = np.nonzero(self.mesh.right >= n)[0]
        self.b_faces = iface[at_boundary[self.mesh.right[iface] - n]]
        self.b_ghost = self.mesh.right[self.b_faces] - n
        self.watch_boundary(self.b_faces)
        monitor.extra_outflow.append(self.boundary_outflow)
        monitor.extra_boundary_flow.append(self.flow_into)
        monitor.parts.append(self)
        monitor.extra_products.append(lambda folder, crs: ("strip_mesh", write_strip_mesh(folder / STRIP_MESH_FILE, self, strip, crs)))
        self.speed_depth = F(monitor.cfg.outputs.speed_depth)
        monitor.extra_fields.append(self.strip_frame_fields)
        monitor.extra_maxima.append(self.strip_maxima_fields)
        joins = {axis: set(self.edge[axis][3].tolist()) for axis in self.edge}
        idx = self.model.device_index
        for n, line in enumerate(lines):
            faces, signs = line_crossings(strip.strip.geometry, strip.kept, strip.mesh, line.coordinates)
            if faces.size:
                monitor.extra_lines.setdefault(n, []).append(self._line_flow(faces, signs))
            # the lattice staircase may land on a join slot the strip writes; the strip counts that face
            lf = line_faces(self.model.grid, line.coordinates)
            kx = np.array([k not in joins.get("x", ()) for k in lf.xfaces.tolist()], bool)
            ky = np.array([k not in joins.get("y", ()) for k in lf.yfaces.tolist()], bool)
            if not (kx.all() and ky.all()):
                monitor.lines[n] = (idx(lf.xfaces[kx]), lf.xsign[kx], idx(lf.yfaces[ky]), lf.ysign[ky])

    def _line_flow(self, faces: np.ndarray, signs: np.ndarray):
        def flow() -> float:
            return float(np.dot(self.strip_host("q")[faces].astype(np.float64), signs))

        return flow

    def rain(self, rate: np.ndarray, step: float) -> float:
        """Uniform rain on the strip at the lattice's own rate; returns the volume of the window, m3."""
        r = float(rate.max()) if rate.size else 0.0
        self.set_strip_source(np.full(self.nreal, r, F))
        return r * float(self.mesh.area[: self.nreal].sum()) * step

    def watch_boundary(self, faces: np.ndarray) -> None:
        """Start the tally of what crosses these interface faces into boundary cells (positive outward)."""
        raise NotImplementedError

    def boundary_outflow(self) -> float:
        """Water that left the strip into boundary cells since the start, m3."""
        raise NotImplementedError

    def ghost_outflow(self) -> np.ndarray:
        """Water that left the strip into each ghost since the start, m3, on the host."""
        raise NotImplementedError

    def flow_into(self, cells: tuple[np.ndarray, np.ndarray]) -> float:
        """What the strip has passed into these lattice cells (grid rows and columns), m3: a hand-back line's share."""
        j, i = (np.asarray(a, np.int64) for a in cells)
        if j.size == 0 or self.ghost.size == 0:
            return 0.0
        wanted = np.asarray(state_index(self.model.grid, j, i), np.int64)
        on = np.isin(self.ghost, wanted)
        return float(self.ghost_outflow()[on].sum()) if on.any() else 0.0

    # ---- the checkpoint part (``monitor.parts``): the strip's state is state
    STATE_NAMES = ("h", "d", "om", "u", "m", "q", "res")

    def save(self, f) -> None:
        group = f.create_group("strip")
        for name in self.STATE_NAMES:
            group.create_dataset(name, data=np.asarray(self.strip_host(name)))
        max_d, max_h, max_q = self.strip_maxima()
        max_s, max_dv = self.strip_speed_maxima()
        for name, a in (("max_d", max_d), ("max_h", max_h), ("max_q", max_q), ("max_s", max_s), ("max_dv", max_dv)):
            group.create_dataset(name, data=np.asarray(a))
        group.create_dataset("ghost_outflow", data=np.asarray(self.ghost_outflow(), np.float64))

    def load(self, f) -> None:
        if "strip" not in f:
            raise ValueError("this checkpoint has no strip: it was written by a run without corridors, so run without --resume")
        group = f["strip"]
        for name in self.STATE_NAMES:
            self.put(name, group[name][()])
        self.put_maxima({name: group[name][()] for name in ("max_d", "max_h", "max_q", "max_s", "max_dv")})
        self.put_ghost_outflow(group["ghost_outflow"][()])
        self.model.stepper.refresh_due = True  # the loader makes the active list afresh once every part is back

    def put(self, name: str, values: np.ndarray) -> None:
        raise NotImplementedError

    def put_maxima(self, values: dict[str, np.ndarray]) -> None:
        raise NotImplementedError

    def put_ghost_outflow(self, values: np.ndarray) -> None:
        raise NotImplementedError

    def finish(self, t: float, balance) -> None:
        """Nothing to add at the end: the strip's water and outflow are in the balance every window."""

    def write(self, results, out) -> None:
        """The strip's products are written with the maps (``extra_products``)."""

    def figures(self, balance) -> dict[str, float]:
        return {"strip_outflow_m3": self.boundary_outflow()}

    def set_strip_depth(self, hbar: np.ndarray) -> None:
        raise NotImplementedError

    def set_strip_source(self, rate: np.ndarray) -> None:
        raise NotImplementedError

    def before_update(self, dt: float, want_wave: bool) -> None:
        raise NotImplementedError

    def after_update(self, dt: float, want_wave: bool) -> None:
        raise NotImplementedError


class HybridCpu(Hybrid):
    """The hybrid step with the Numba kernels on the host arrays."""

    def make_state(self) -> PolyState:
        if self.model.backend.name != "cpu":
            raise ValueError("HybridCpu steps a CPU model; make_hybrid picks the class")
        self.saved = np.zeros(self.ghost.size, F)
        self.left_m3 = 0.0
        self.left_ghost = np.zeros(self.ghost.size, np.float64)
        self.max_d, self.max_h = np.zeros(self.nreal, F), np.zeros(self.nreal, F)
        self.max_s, self.max_dv = np.zeros(self.nreal, F), np.zeros(self.nreal, F)
        self.max_q = np.zeros(self.mesh.nfaces, F)
        self.speed_depth = F(0.0)
        return PolyState(self.mesh, self.model.num)

    def strip_host(self, name: str) -> np.ndarray:
        return getattr(self.state, name)

    def strip_maxima(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        return self.max_d, self.max_h, self.max_q

    def strip_speed_maxima(self) -> tuple[np.ndarray, np.ndarray]:
        return self.max_s, self.max_dv

    def strip_cell_speed(self) -> np.ndarray:
        return self.state.cell_speed().copy()

    def watch_boundary(self, faces: np.ndarray) -> None:
        self.b_faces = np.asarray(faces, np.int64)

    def boundary_outflow(self) -> float:
        return self.left_m3

    def ghost_outflow(self) -> np.ndarray:
        return self.left_ghost

    def put(self, name: str, values: np.ndarray) -> None:
        getattr(self.state, name)[:] = np.asarray(values, F)

    def put_maxima(self, values: dict[str, np.ndarray]) -> None:
        for name, a in values.items():
            getattr(self, name)[:] = np.asarray(a, F)

    def put_ghost_outflow(self, values: np.ndarray) -> None:
        self.left_ghost[:] = np.asarray(values, np.float64)
        self.left_m3 = float(self.left_ghost.sum())

    def strip_flags(self) -> np.ndarray:
        from wadi2d.strips.watch import home_flags

        s, n = self.state, self.nreal
        return home_flags(np, s.h[:n], s.src[:n], self.watch.home, self.model.grid.ntiles)

    def set_strip_depth(self, hbar: np.ndarray) -> None:
        s, n = self.state, self.nreal
        s.h[:n], s.d[:n], s.om[:n] = self.strip_start(hbar)
        self.strip_changed()

    def set_strip_source(self, rate: np.ndarray) -> None:
        self.state.src[: self.nreal] = np.asarray(rate, F)
        self.strip_changed()

    def before_update(self, dt: float, want_wave: bool) -> None:
        b, s, n, g = self.model.backend, self.state, self.nreal, self.ghost
        s.h[n:] = b.h[g]
        s.d[n:] = b.d[g]
        s.om[n:] = b.om[g]
        k, dts = self.substeps(dt)
        ng = g.size
        div_acc = np.zeros(ng, np.float64)
        given = np.zeros(ng, F)
        self.q_mean = np.zeros(s.mesh.nfaces, np.float64)
        L, R = s.static[0], s.static[1]

        def rates() -> None:
            ghost_rates(
                ng, n, g, self.dx, s.nums[5], self.open_w, self.open_e, self.open_n, self.open_s, b.h, b.qx, b.qy,
                s.Ux, s.Uy, s.Rx, s.Ry,
            )  # fmt: skip

        for sub in range(k):
            last = sub == k - 1
            s.zero_vectors()
            ghost_sums(
                ng, n, g, self.dx, self.open_w, self.open_e, self.open_n, self.open_s, self.zmin_state,
                b.h, b.d, b.qx, b.qy, s.Ux, s.Uy, s.Gx, s.Gy,
            )  # fmt: skip
            s.step_faces(dts, want_wave and last, rates)
            kernel.outflows(s.mesh.nfaces, s.ncells, L, R, s.q1, s.out)
            kernel.positivity(n, F(dts), s.h, s.area, s.out, s.r)
            ghost_ratios(ng, n, g, F(dt), F(dts), self.dx, b.h, b.r, b.qx1, b.qy1, s.out, given, s.r)
            kernel.update(
                s.mesh.nfaces, s.ncells, n, F(dts), want_wave and last, L, R, s.area, s.hc, s.dtab, s.q1, s.r, s.src,
                s.div, s.res, s.h, s.d, s.om, s.q, s.nums[0],
            )  # fmt: skip
            s.u, s.u1 = s.u1, s.u
            s.m, s.m1 = s.m1, s.m
            loss = s.div[n:].astype(np.float64) * dts
            div_acc += loss
            given += np.maximum(loss, 0.0).astype(F)
            self.q_mean += s.q.astype(np.float64) * (dts / dt)
            self._book(dts)
        self.saved[:] = b.src[g]
        b.src[g] = self.saved - (div_acc / (dt * float(self.dx) ** 2)).astype(F)
        if want_wave:
            self.strip_freq = float(s.wave)
            b.extra_wave = self.cap_wave(s.wave)

    def _book(self, dt: float) -> None:
        """One strip step's bookkeeping: the boundary tally and the run's maxima."""
        s, n = self.state, self.nreal
        if self.b_faces.size:
            crossed = s.q[self.b_faces].astype(np.float64) * dt
            self.left_m3 += float(crossed.sum())
            np.add.at(self.left_ghost, self.b_ghost, crossed)
        np.maximum(self.max_d, s.d[:n], out=self.max_d)
        np.maximum(self.max_h, s.h[:n], out=self.max_h)
        np.maximum(self.max_q, np.abs(s.q), out=self.max_q)
        speed = s.cell_speed() * (s.d[:n] > self.speed_depth)
        np.maximum(self.max_s, speed, out=self.max_s)
        np.maximum(self.max_dv, s.d[:n] * speed, out=self.max_dv)

    def after_update(self, dt: float, want_wave: bool) -> None:
        """The join's discharge and velocity into the squares' closed faces. The velocity is the discharge over the
        ghost's mean depth, held to ``u_max`` as every lattice face velocity is (W87): on a front entering a dry
        square the depth is its floor of 1e-6 m, and uncapped the squares' advection stencil read tens of km/s."""
        b, s, n = self.model.backend, self.state, self.nreal
        b.src[self.ghost] = self.saved
        dx = float(self.dx)
        u_max = float(s.nums[5])
        for axis, (faces, group, signs, unique, all_copies, owner, ghost_of) in self.edge.items():
            if faces.size == 0:
                continue
            q_edge = np.zeros(unique.size, np.float64)
            np.add.at(q_edge, group, self.q_mean[faces] * signs)
            depth = np.maximum(s.h[n + ghost_of].astype(np.float64), 1e-6)
            speed = np.clip(q_edge / (depth * dx), -u_max, u_max)
            discharge, velocity = (b.qx, b.u1) if axis == "x" else (b.qy, b.v1)
            discharge[unique] = q_edge.astype(F)
            velocity[all_copies] = speed[owner].astype(F)


def make_hybrid(model: Model, mesh: PolyMesh, substeps: int = 1) -> Hybrid:
    """The hybrid stepper for the model's backend; ``substeps`` as ``strips.substeps`` (1 steps the strip with the
    squares at the smaller step)."""
    if model.backend.name == "gpu":
        from wadi2d.strips.hybrid_gpu import HybridGpu

        return HybridGpu(model, mesh, substeps)
    return HybridCpu(model, mesh, substeps)


def ghosts_for(geo: MeshGeometry, grid_or_model, tables: GridTables) -> Ghosts:
    """The tile cells the geometry's boundary faces open onto: half a cell out along each face's outward normal, an
    active tile cell makes that face an interface; a wall or the void makes it a wall."""
    grid = getattr(grid_or_model, "grid", grid_or_model)
    _area, cx, cy = geo.areas_centroids()
    _length, nfx, nfy, xf, yf = geo.faces(cx, cy)
    boundary = np.nonzero(geo.face_cell[:, 1] < 0)[0]
    px, py = xf[boundary] + 0.5 * grid.dx * nfx[boundary], yf[boundary] + 0.5 * grid.dx * nfy[boundary]
    i = np.floor((px - grid.x0) / grid.dx).astype(np.int64)
    j = np.floor((grid.y0 - py) / grid.dx).astype(np.int64)
    ny, nx = grid.shape
    inside = (i >= 0) & (i < nx) & (j >= 0) & (j < ny)
    active = np.zeros(boundary.size, bool)
    active[inside] = grid.mask[j[inside], i[inside]]
    face_slot = np.full(geo.nfaces, -1, np.int64)
    cells = sorted({(int(a), int(b)) for a, b, on in zip(j, i, active, strict=True) if on})
    slot_of = {c: k for k, c in enumerate(cells)}
    for f, jj, ii, on in zip(boundary, j, i, active, strict=True):
        if on:
            face_slot[f] = slot_of[(int(jj), int(ii))]
    jj = np.array([c[0] for c in cells], np.int64)
    ii = np.array([c[1] for c in cells], np.int64)
    state = np.asarray(state_index(grid, jj, ii), np.int64) if jj.size else np.zeros(0, np.int64)
    gx, gy = grid.xy_of(jj, ii)
    hc, dtab = grid.from_tiles(tables.hc), grid.from_tiles(tables.dtab)
    return Ghosts(
        face_slot, state, gx.astype(np.float64), gy.astype(np.float64), tables.zmin[jj, ii].astype(np.float64),
        tables.zbar[jj, ii].astype(np.float64), hc[jj, ii].astype(np.float64), dtab[jj, ii].astype(np.float64),
        np.full(jj.size, grid.dx * grid.dx),
    )  # fmt: skip
