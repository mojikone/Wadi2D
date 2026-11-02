"""Crest lines: raised linear features found by the top-hat of W5, thinned to a line, split at gaps.

Top-hat is the ground less its morphological opening with a disc: anything narrower than the disc that stands above
the ground around it survives. Its height is the feature's height over its fitted ground, which is what a face
needs to close. The kind is a guess from shape: a crest that crosses a wadi reads as a dam, a long straight one as
a road, the rest as other crest. The user corrects the guess; nothing downstream depends on it.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import shapely
from scipy import ndimage

from wadi2d.breaklines.pixels import length_of, simplify, smooth, straightness, thin, walk
from wadi2d.breaklines.settings import DAM, OTHER, ROAD, Settings
from wadi2d.breaklines.thalweg import Thalweg
from wadi2d.breaklines.window import Window


@dataclass
class Crest:
    xy: np.ndarray
    height_m: float
    """Median top-hat height along the line."""
    kind: str
    crossed_km2: float
    """Largest drainage area of a thalweg the line crosses; 0 when it crosses none."""
    slope: float
    """Median slope of the ground under the line, the opened surface, m/m."""


def disc(radius_px: int) -> np.ndarray:
    r = np.arange(-radius_px, radius_px + 1)
    return (r[:, None] ** 2 + r[None, :] ** 2) <= radius_px**2


def top_hat(z: np.ndarray, pixel: float, radius_m: float) -> np.ndarray:
    """Ground less its opening with a disc; zero where the DEM has no data."""
    return opening(z, pixel, radius_m)[0]


def opening(z: np.ndarray, pixel: float, radius_m: float) -> tuple[np.ndarray, np.ndarray]:
    """The top-hat and the opened surface it was read from: the ground a crest stands on.

    Past the edge the ground continues by odd reflection, as in ``incision``: an opening that saw the edge as its
    own neighbour would call the top of every slope that reaches the edge a crest.
    """
    valid = np.isfinite(z)
    filled = z
    if not valid.all():
        nearest = ndimage.distance_transform_edt(~valid, return_distances=False, return_indices=True)
        filled = z[tuple(nearest)]
    r = max(1, round(radius_m / pixel))
    wide = np.pad(filled, r, mode="reflect", reflect_type="odd")
    opened = ndimage.grey_opening(wide, footprint=disc(r), mode="nearest")[r:-r, r:-r]
    return np.where(valid, filled - opened, 0.0), opened


def ground_slope(opened: np.ndarray, pixel: float) -> np.ndarray:
    """Slope of the opened surface, m/m: the ground under a crest, not the crest."""
    gy, gx = np.gradient(opened, pixel)
    return np.hypot(gx, gy)


def raised(top: np.ndarray, inside: np.ndarray, height: float, min_length: float, pixel: float) -> np.ndarray:
    """Pixels at least ``height`` above their ground, in objects at least ``min_length`` across.

    A gap of one pixel is bridged first: where a crest crosses the edge of a cut, the mixed pixel there reads below
    the ground the opening restores, and one missing pixel would cut the line in three.
    """
    joined = ndimage.binary_closing(top >= height, structure=np.ones((3, 3)), border_value=0)
    labels, count = ndimage.label(joined & inside, structure=np.ones((3, 3)))
    keep = np.zeros(count + 1, bool)
    for n, box in enumerate(ndimage.find_objects(labels), start=1):
        if box is not None:
            span = np.hypot(box[0].stop - box[0].start, box[1].stop - box[1].start) * pixel
            keep[n] = span >= min_length
    return keep[labels]


def crests_of(win: Window, thalwegs: list[Thalweg], incision_depth: float, settings: Settings) -> list[Crest]:
    """Crest lines of the window: a crest that crosses a defined wadi, one incised at least ``incision_depth``, is
    a dam and stays; any other on ground steeper than ``settings.ground_slope_max`` is the mountain's own and goes.
    """
    top, opened = opening(win.z, win.pixel, settings.disc_radius_m)
    slope = ground_slope(opened, win.pixel)
    mask = raised(top, win.inside, settings.crest_height_m, settings.min_length_m, win.pixel)
    streams = [
        (shapely.LineString(t.xy), t.area_km2)
        for t in thalwegs
        if len(t.xy) >= 2 and t.incised_m >= incision_depth
    ]
    tree = shapely.STRtree([s for s, _a in streams]) if streams else None
    out = []
    for pixels in walk(thin(mask)):
        xy = simplify(
            smooth(win.xy(pixels[:, 0], pixels[:, 1]), settings.smooth_vertices),
            settings.simplify_pixels * win.pixel,
        )
        if length_of(xy) < settings.min_length_m:
            continue
        height = float(np.median(top[pixels[:, 0], pixels[:, 1]]))
        ground = float(np.median(slope[pixels[:, 0], pixels[:, 1]]))
        line = shapely.LineString(xy)
        crossed = 0.0
        if tree is not None:
            hits = tree.query(line, predicate="intersects")
            crossed = max((streams[h][1] for h in hits), default=0.0)
        if crossed > 0.0:
            kind = DAM
        elif ground > settings.ground_slope_max:
            continue
        elif length_of(xy) >= settings.road_length_m and straightness(xy) >= settings.road_straightness:
            kind = ROAD
        else:
            kind = OTHER
        out.append(Crest(xy, height, kind, crossed, ground))
    return out
