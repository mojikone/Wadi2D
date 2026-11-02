"""Shaped objects in place: the new ground of embankments and channels, and the crest lines that keep them tight.

:class:`Shape` joins an alignment, a section profile and the object's openings and ends, and answers two questions:
what a pixel becomes, and where a raised part stands as a crest. Raised ground alone leaks on coarse cells, because a
diagonal ridge blocks each face only in part, so every stretch standing above the ground also runs as a line of crest
faces. Those lines end with the stretch: they stop at openings, and where the ground rises past the top.

A crest face limits the discharge to critical flow for the head on it. The constant 1.705 belongs to a head read in
still water. A raised crest may be as wide as the cells, and then the cell before the face has already spent its
velocity head, so these faces read the energy head (a negative coefficient, see the face kernels; crest lines and
natural crests keep their law). The limit eases as the crest takes up more of a cell, and goes once cells resolve it:
the momentum equation then finds critical flow itself. Values from the sweep in ``W8 terrain tools``.

A spillway drawn on a raised part takes the fill out of the pixels there: a face is closed up to the higher of its
crest and its ground, so with the embankment still in the pixels the water would meet the embankment. The notch is an
opening for the pixels only; its faces stay, at the spillway crest, and carry the spillway's own law as a thin crest.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

import numpy as np
from rasterio import features
from rasterio.transform import Affine

from wadi2d.config.constants import CRITICAL_WEIR_COEFF
from wadi2d.config.schema import Terrain, TerrainObject
from wadi2d.grid.tiles import TileGrid
from wadi2d.terrain.alignment import Alignment, Located
from wadi2d.terrain.sections import Profile, SectionAt, build_profile, lowered
from wadi2d.terrain.template import clamp, crest_edge, cut_surface, fill_surface, nose_surface

Sampler = Callable[[np.ndarray, np.ndarray], np.ndarray]
"""Ground at (x, y), one value per point."""

STRIP_ROUNDING = 16.0
"""Footprints are rounded up to this, m, so most tiles share one buffered line."""
RUN_SAMPLES_PER_CELL = 2
"""Points per cell along a crest line."""
RUN_OVERLAP_CELLS = 1.0
"""A crest line runs this far past the end of its stretch, into the ground it ties to, cells."""
LINED_TOLERANCE = 1e-6
"""A pixel this close to the cut surface lies on the channel section, m."""
BOTH = ("left", "right")


@dataclass(frozen=True)
class Notch:
    """Stations where a spillway stands on a raised part: no fill in the pixels, faces at ``level``."""

    start: float
    end: float
    level: float
    side: str = "both"


@dataclass
class CrestRun:
    """One unbroken stretch standing above the ground, as a dense line with its elevation at each point."""

    coordinates: np.ndarray
    z: np.ndarray
    joins: tuple[bool, bool]
    side: str
    width: float = 0.0
    """Mean crest width, m."""


@dataclass
class Shape:
    """A shaped object: what it does to a pixel and where it stands."""

    obj: TerrainObject
    line: Alignment
    profile: Profile
    notches: list[Notch] = field(default_factory=list)

    @classmethod
    def of(cls, obj: TerrainObject) -> Shape:
        line = Alignment(obj.coordinates)
        return cls(obj, line, build_profile(obj, line.length))

    @property
    def title(self) -> str:
        return self.obj.name or self.obj.kind.replace("_", " ")

    @property
    def cuts(self) -> bool:
        return self.obj.kind != "embankment"

    @property
    def fills(self) -> bool:
        return self.obj.kind != "channel"

    def section(self, s: np.ndarray, right: np.ndarray | bool) -> SectionAt:
        """The section at stations ``s``, on ``right`` or left."""
        return self.profile.at(s, right)

    def _notched(self, sec: SectionAt, s: np.ndarray, right: bool) -> SectionAt:
        """The section a crest line follows: down to the spillway crest at each notch."""
        for notch in self.notches:
            sec = lowered(sec, self.opening_mask(notch, s, right), notch.level)
        return sec

    def edge(self, at: SectionAt) -> np.ndarray:
        """Inner edge of the crest: the line itself for an embankment, whose crest straddles it."""
        return crest_edge(at) if self.cuts else np.zeros_like(at.half)

    def opening_mask(self, opening, s: np.ndarray, right: np.ndarray | bool) -> np.ndarray:
        mask = (s >= opening.start) & (s <= opening.end)
        if opening.side == "both" or not self.cuts:
            return mask
        return mask & (np.asarray(right) == (opening.side == "right"))

    def _limits(self, at: Located) -> tuple[np.ndarray, np.ndarray]:
        """(low, high) at each point: the two surfaces, with the ends and the openings in them."""
        right, a = at.offset >= 0.0, np.abs(at.offset)
        sec = self.section(at.s, right)
        past = at.beyond > 0.0
        start = at.s <= 0.0
        ends = (self.obj.start_end, self.obj.end_end)
        closed = past & ((start & (ends[0] == "closed")) | (~start & (ends[1] == "closed")))
        reach = np.where(closed, sec.half + np.hypot(at.beyond, np.maximum(a - sec.half, 0.0)), a)
        high = cut_surface(sec, reach) if self.cuts else np.full(a.shape, np.inf)
        if not self.fills:
            low = np.full(a.shape, -np.inf)
            return low, np.where(past & ~closed, np.inf, high)
        edge = self.edge(sec)
        low = np.minimum(fill_surface(sec, edge, reach), high)
        square = past & ~closed
        if square.any():
            low[square] = nose_surface(sec.pick(square), edge[square], a[square], at.beyond[square])
            high[square] = np.inf
        self._open(at, right, a, low, high)
        return low, high

    def _open(self, at: Located, right: np.ndarray, a: np.ndarray, low: np.ndarray, high: np.ndarray) -> None:
        """Take the raised part out of the openings, ending it in a nose at each side of the gap."""
        for notch in self.notches:  # a spillway has training walls: the fill stops dead at each side
            low[self.opening_mask(notch, at.s, right)] = -np.inf
        for opening in self.obj.openings:
            mask = self.opening_mask(opening, at.s, right)
            if not mask.any():
                continue
            s = at.s[mask]
            edges = [e for e in (opening.start, opening.end) if 0.0 < e < self.line.length]
            if not edges:
                low[mask] = -np.inf
                continue
            near = np.array(edges)[np.argmin(np.abs(np.subtract.outer(s, edges)), axis=1)]
            sec = self.section(near, right[mask])
            nose = nose_surface(sec, self.edge(sec), a[mask], np.abs(s - near))
            low[mask] = np.minimum(np.minimum(low[mask], nose), high[mask])

    def _fade(self, at: Located) -> np.ndarray:
        """1 where the section stands in full, falling to 0 towards a tapered end."""
        fade = np.ones(at.s.shape)
        length = self.obj.taper_length
        if self.obj.start_end == "taper":
            fade = np.minimum(fade, at.s / length)
        if self.obj.end_end == "taper":
            fade = np.minimum(fade, (self.line.length - at.s) / length)
        return fade

    def surface(self, x: np.ndarray, y: np.ndarray, ground: np.ndarray) -> np.ndarray:
        """The new ground at points whose old ground is ``ground``."""
        at = self.line.locate(x, y)
        low, high = self._limits(at)
        return ground + self._fade(at) * (clamp(ground, low, high) - ground)

    def on_section(self, x: np.ndarray, y: np.ndarray, ground: np.ndarray) -> np.ndarray:
        """Which points of finished ground lie on the channel section: they take its lining."""
        _low, high = self._limits(self.line.locate(x, y))
        return ground >= high - LINED_TOLERANCE

    def reach(self, lowest: float, highest: float) -> float:
        """How far from the line this object can change ground that lies between these two levels, m."""
        p = self.profile
        tops, beds = float(p.top.max()), float(p.bed.min())
        inner = float(p.inner.max())
        half = float(p.half.max())
        cut = half + inner * max(highest - beds, 0.0) if self.cuts else 0.0
        edge = half + inner * max(tops - beds, 0.0) if self.cuts else 0.0
        fill = edge + float(p.crest.max()) + float(p.outer.max()) * max(tops - lowest, 0.0)
        return max(cut, fill if self.fills else 0.0)

    def crest_offsets(self, s: np.ndarray, right: bool) -> tuple[SectionAt, np.ndarray]:
        """The section and the offset of the middle of the crest, signed, at stations ``s``."""
        sec = self.section(s, right)
        if not self.cuts:
            return sec, np.zeros_like(s)
        return sec, (1.0 if right else -1.0) * (crest_edge(sec) + 0.5 * sec.crest)

    def crest_runs(self, dx: float, cfg: Terrain, ground: Sampler | None) -> list[CrestRun]:
        """Every stretch standing above the ground, one line per stretch."""
        if not self.fills:
            return []
        runs: list[CrestRun] = []
        s = self.line.samples(dx / RUN_SAMPLES_PER_CELL)
        for side in BOTH if self.cuts else BOTH[:1]:
            right = side == "right"
            sec, offset = self.crest_offsets(s, right)
            x, y = self.line.offset_at(s, offset)
            real = self.line.distance(x, y) >= np.abs(offset) - 0.5 * dx  # past the centre of a tight bend: a loop
            g = ground(x, y) if ground is not None else np.full(s.shape, -np.inf)
            closed = np.zeros(s.shape, bool)
            for opening in self.obj.openings:
                closed |= self.opening_mask(opening, s, right)
            standing = (g < sec.top - cfg.dyke_min_height) & real
            wanted = _widen(standing, round(RUN_OVERLAP_CELLS * RUN_SAMPLES_PER_CELL)) & real & ~closed
            fade = self._fade(Located(s, offset, np.zeros_like(s)))
            top = self._notched(sec, s, right).top
            base = np.where(np.isfinite(g), g, top)
            z = base + fade * (top - base)
            width = sec.crest if self.cuts else 2.0 * sec.crest
            for first, last in _stretches(wanted):
                if last == first:
                    continue
                points = np.column_stack((x[first : last + 1], y[first : last + 1]))
                joins = (first == 0, last == s.size - 1)
                mean = float(width[first : last + 1].mean())
                runs.append(CrestRun(points, z[first : last + 1], joins, side, mean))
        return runs + self._closing_runs(runs)

    def _closing_runs(self, runs: list[CrestRun]) -> list[CrestRun]:
        """A closed end of a channel with dykes: its two crests meet across the end."""
        found = []
        for index, kind in ((0, self.obj.start_end), (-1, self.obj.end_end)):
            ends = [run for run in runs if run.joins[index]]
            if kind == "closed" and self.cuts and len(ends) == 2:
                points = np.array([ends[0].coordinates[index], ends[1].coordinates[index]])
                found.append(CrestRun(points, np.array([ends[0].z[index], ends[1].z[index]]), (False, False), "both"))
        return found


def crest_coefficient(width: float, dx: float, cfg: Terrain) -> float:
    """The weir limit of a raised crest ``width`` wide on cells of ``dx``: negative reads the energy head, 0 is none."""
    share = width / dx
    if share >= cfg.crest_resolved_ratio:
        return 0.0
    ratios = (cfg.crest_thin_ratio, cfg.crest_eased_ratio)
    return -float(np.interp(share, ratios, (CRITICAL_WEIR_COEFF, cfg.crest_eased_coefficient)))


def _widen(mask: np.ndarray, samples: int) -> np.ndarray:
    """True within ``samples`` of a True."""
    if samples <= 0 or not mask.any():
        return mask
    return np.convolve(mask.astype(int), np.ones(2 * samples + 1, int), mode="same") > 0


def _stretches(mask: np.ndarray) -> list[tuple[int, int]]:
    """(first, last) index of each run of True."""
    edges = np.diff(np.concatenate(([0], mask.astype(np.int8), [0])))
    return list(zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1) - 1, strict=True))


def notch_shapes(shapes: Iterable[Shape], objects: Iterable[TerrainObject], snap: float) -> None:
    """Find the spillways standing on each shape's crest, and notch it there.

    ``snap`` is the reach of a spillway's faces, m: the notch runs that far past each end of its line, because the
    spillway takes every crest face that close and each of them has to reach down to its crest.
    """
    spillways = [o for o in objects if o.kind == "spillway"]
    for shape in shapes:
        if shape.fills:
            for spillway in spillways:
                shape.notches.extend(_notches(shape, spillway, snap))


def _notches(shape: Shape, spillway: TerrainObject, snap: float) -> list[Notch]:
    points = np.asarray(spillway.coordinates, dtype=np.float64)
    at = shape.line.locate(points[:, 0], points[:, 1])
    s = np.clip(at.s, 0.0, shape.line.length)
    level = float(np.min(spillway.z)) if spillway.z is not None else float(spillway.z_constant)
    found = []
    start, end = float(s.min()) - snap, float(s.max()) + snap
    for side in BOTH if shape.cuts else ("both",):
        sec, offset = shape.crest_offsets(s, side == "right")
        width = 0.5 * sec.crest if shape.cuts else sec.crest
        if np.all(np.abs(at.offset - offset) <= snap + width):
            found.append(Notch(start, end, level, side))
    return found


@dataclass
class ShapeEdit:
    """A shape applied to windows of pixels. A window is ``z``; ``row0`` and ``col0`` count from the grid origin."""

    shape: Shape
    grid: TileGrid
    pixel: float
    lining: bool = False
    _strips: dict[float, object] = field(default_factory=dict)

    def _strip(self, reach: float):
        rounded = float(np.ceil(max(reach, self.pixel) / STRIP_ROUNDING) * STRIP_ROUNDING)
        if rounded not in self._strips:
            self._strips[rounded] = self.shape.line.line.buffer(rounded)
        return self._strips[rounded]

    def _pixels(self, z: np.ndarray, row0: int, col0: int):
        """(rows, columns, x, y) of the pixels of this window the shape can reach, or None."""
        strip = self._strip(self.shape.reach(float(z.min()), float(z.max())))
        west = self.grid.x0 + col0 * self.pixel
        north = self.grid.y0 - row0 * self.pixel
        ny, nx = z.shape
        xmin, ymin, xmax, ymax = strip.bounds
        if xmax < west or xmin > west + nx * self.pixel or ymin > north or ymax < north - ny * self.pixel:
            return None
        transform = Affine(self.pixel, 0.0, west, 0.0, -self.pixel, north)
        hit = features.rasterize([(strip, 1)], out_shape=z.shape, transform=transform, all_touched=True, dtype="uint8")
        r, c = np.nonzero(hit)
        if r.size == 0:
            return None
        return r, c, west + (c + 0.5) * self.pixel, north - (r + 0.5) * self.pixel

    def __call__(self, z: np.ndarray, row0: int, col0: int) -> None:
        found = self._pixels(z, row0, col0)
        if found is not None:
            r, c, x, y = found
            z[r, c] = self.shape.surface(x, y, z[r, c])

    def line_pixels(self, z: np.ndarray, n: np.ndarray, row0: int, col0: int) -> None:
        """Write the lining into ``n`` where finished ground ``z`` lies on the channel section."""
        found = self._pixels(z, row0, col0)
        if found is not None:
            r, c, x, y = found
            on = self.shape.on_section(x, y, z[r, c])
            n[r[on], c[on]] = self.shape.obj.lining_n
