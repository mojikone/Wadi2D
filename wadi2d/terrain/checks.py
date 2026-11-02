"""What is allowed but probably not meant, in plain words, before a run.

Each check looks at one shaped object against the ground it was drawn on and returns sentences for the user. What
cannot be built at all (stations out of order, a top below the bed) is refused where it is read, not here.
"""

from __future__ import annotations

import numpy as np
import shapely

from wadi2d.config.schema import SHAPED_KINDS, Terrain, TerrainObject
from wadi2d.terrain.alignment import Alignment
from wadi2d.terrain.earthworks import Sampler, Shape, _stretches
from wadi2d.terrain.template import crest_edge

BARRIER_KINDS = ("crest_line", "wall", "embankment", "channel_dyke")


def _long(mask: np.ndarray, s: np.ndarray, length: float) -> list[tuple[int, int]]:
    return [(a, b) for a, b in _stretches(mask) if s[b] - s[a] >= length and b > a]


def check_table(shape: Shape) -> list[str]:
    """Stations that do not fit the line."""
    rows = (shape.obj.section.rows if shape.obj.section else []) or []
    if not rows:
        return []
    last, length = rows[-1].station, shape.line.length
    if last > length + 1.0:
        return [
            f"{shape.title}: the section table runs to station {last:.0f}, but the line is only {length:.0f} m long."
        ]
    if last < length - 1.0:
        return [
            f"{shape.title}: the section table stops at station {last:.0f} of {length:.0f} m; the last section holds to the end."
        ]
    return []


def check_bed(shape: Shape, ground: Sampler, step: float, cfg: Terrain) -> list[str]:
    """A bed above the ground for a long reach, and a bed that rises along the stations."""
    if not shape.cuts:
        return []
    notes = []
    s = shape.line.samples(step)
    g = ground(*shape.line.point_at(s))
    bed = np.interp(s, shape.profile.station, shape.profile.bed)
    verb = "nothing is cut there" if shape.obj.kind == "channel" else "it stands on fill there"
    for a, b in _long(bed > g + cfg.dyke_min_height, s, cfg.check_bed_length):
        high = float((bed - g)[a : b + 1].max())
        notes.append(
            f"{shape.title}: the bed is above the ground for {s[b] - s[a]:.0f} m from station {s[a]:.0f} to "
            f"{s[b]:.0f}, by up to {high:.1f} m; {verb}."
        )
    stations, levels = shape.profile.station, shape.profile.bed
    for a, b in _stretches(np.diff(levels) > 0.0):
        rise = float(levels[b + 1] - levels[a])
        if rise > cfg.check_rise:
            notes.append(
                f"{shape.title}: adverse slope, the bed rises {rise:.2f} m from station {stations[a]:.0f} to "
                f"{stations[b + 1]:.0f}. Check the direction of the line: station 0 is its first vertex."
            )
    return notes


def check_steps(shape: Shape, cfg: Terrain) -> list[str]:
    """Bed or top changing so fast between two stations that the ground shows a step."""
    notes = []
    p = shape.profile
    run = np.diff(p.station)
    named = [("top of the left bank", p.top[0]), ("top of the right bank", p.top[1])]
    if shape.cuts:
        named.insert(0, ("bed", p.bed))
    for label, values in named:
        grade = np.abs(np.diff(values)) / run
        for index in np.flatnonzero(grade > cfg.check_grade)[:1]:
            notes.append(
                f"{shape.title}: the {label} changes {abs(values[index + 1] - values[index]):.2f} m in "
                f"{run[index]:.1f} m at station {p.station[index]:.0f}, which is a step in the ground."
            )
    return notes


def check_resolution(shape: Shape, ground: Sampler, dx: float, pixel: float, cfg: Terrain) -> list[str]:
    """A section finer than the DEM, or a channel the cells cannot carry."""
    if not shape.cuts:
        return []  # a thin crest is held by its faces, whatever the pixels show
    notes = []
    narrowest = 2.0 * float(shape.profile.half.min())
    if 0.0 < narrowest < cfg.check_pixels * pixel:
        notes.append(
            f"{shape.title}: the bottom width of {narrowest:.1f} m is finer than the DEM can show at {pixel:g} m pixels."
        )
    s = shape.line.samples(dx)
    left, right = shape.profile.at(s, False), shape.profile.at(s, True)
    if shape.fills:
        banks = crest_edge(left) + crest_edge(right)
    else:
        depth = np.maximum(ground(*shape.line.point_at(s)) - left.bed, 0.0)
        banks = 2.0 * left.half + (left.inner + right.inner) * depth
    tightest = float(banks.min())
    if tightest < cfg.check_cells * dx:
        at = float(s[int(np.argmin(banks))])
        notes.append(
            f"{shape.title}: only {tightest:.1f} m between the banks at station {at:.0f}, under "
            f"{cfg.check_cells:g} cells of {dx:g} m: expect conveyance errors of several per cent; use smaller cells."
        )
    return notes


def check_crest(shape: Shape, dx: float, cfg: Terrain) -> list[str]:
    """A crest wider than its weir limit holds: overtopping then depends on where the line falls in the cell."""
    if not shape.fills:
        return []
    widest = float(shape.profile.crest.max()) * (1.0 if shape.cuts else 2.0)
    if widest / dx <= cfg.crest_accurate_ratio:
        return []
    return [
        f"{shape.title}: a crest {widest:g} m wide on {dx:g} m cells is over {cfg.crest_accurate_ratio:g} of a cell: "
        "overtopping can read up to 13 % low or 8 % high, depending on where the line falls in the cell. "
        "Check any design discharge over this crest with a weir calculation."
    ]


def check_openings(shape: Shape, dx: float) -> list[str]:
    notes = []
    for opening in shape.obj.openings:
        if opening.start >= shape.line.length:
            notes.append(
                f"{shape.title}: the opening at station {opening.start:.0f} lies past the end of the line."
            )
        elif opening.end - opening.start < dx:
            notes.append(
                f"{shape.title}: the opening at station {opening.start:.0f} is narrower than one {dx:g} m cell "
                "and may not pass water."
            )
    return notes


def check_ends(
    shape: Shape, ground: Sampler, others: list[shapely.LineString], dx: float, cfg: Terrain
) -> list[str]:
    """Raised parts with nothing to tie into, and channels ending in a face of ground."""
    notes = []
    length = shape.line.length
    ends = (("start", 0.0, shape.obj.start_end), ("end", length, shape.obj.end_end))
    reach = cfg.join_cells * dx
    for label, station, kind in ends:
        if kind == "taper":
            continue
        s = np.array([station])
        for side in ("left", "right") if shape.fills and shape.cuts else ("left",) if shape.fills else ():
            sec, offset = shape.crest_offsets(s, side == "right")
            x, y = shape.line.offset_at(s, offset)
            gap = float((sec.top - ground(x, y))[0])
            tied = any(other.distance(shapely.Point(x[0], y[0])) <= reach for other in others)
            if gap > cfg.check_tie_height and not tied:
                bank = f"the {side} dyke" if shape.cuts else "it"
                notes.append(
                    f"{shape.title}: {bank} ends at station {station:.0f} standing {gap:.1f} m above the ground, with "
                    "nothing to tie into: water goes round the end. Run it to high ground or to another line."
                )
        if shape.cuts and kind == "open":
            bed = float(np.interp(station, shape.profile.station, shape.profile.bed))
            depth = float(ground(*shape.line.point_at(s))[0]) - bed
            if depth > cfg.check_tie_height:
                notes.append(
                    f"{shape.title}: its {label} is cut {depth:.1f} m below the ground with a square face. "
                    "Tie it to something, or use a closed or tapered end."
                )
    return notes


def check_extent(shape: Shape, bounds: tuple[float, float, float, float]) -> list[str]:
    xmin, ymin, xmax, ymax = bounds
    x0, y0, x1, y1 = shape.line.line.bounds
    if x0 < xmin or y0 < ymin or x1 > xmax or y1 > ymax:
        return [f"{shape.title}: part of the line lies outside the grid; only what is inside is built."]
    return []


def _barrier_lines(objects: list[TerrainObject], skip: TerrainObject) -> list[shapely.LineString]:
    return [Alignment(o.coordinates).line for o in objects if o is not skip and o.kind in BARRIER_KINDS]


def terrain_notes(
    objects: list[TerrainObject],
    ground: Sampler,
    dx: float,
    pixel: float,
    cfg: Terrain,
    bounds: tuple[float, float, float, float],
) -> list[str]:
    """Every sentence for every shaped object."""
    notes: list[str] = []
    for obj in objects:
        if obj.kind not in SHAPED_KINDS:
            continue
        shape = Shape.of(obj)
        notes += check_extent(shape, bounds)
        notes += check_table(shape)
        notes += check_bed(shape, ground, dx, cfg)
        notes += check_steps(shape, cfg)
        notes += check_resolution(shape, ground, dx, pixel, cfg)
        notes += check_crest(shape, dx, cfg)
        notes += check_openings(shape, dx)
        notes += check_ends(shape, ground, _barrier_lines(objects, obj), dx, cfg)
    return notes
