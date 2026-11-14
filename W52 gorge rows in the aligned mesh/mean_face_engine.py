"""The engine with the strip faces' ground read as the mean of the two pixels either side of the face line, not the
higher (W52, diagnosis only, nothing in the engine changes): does the higher-of-two rule, which on a face oblique to
the pixel grid reads a steep wall too near the axis, carry the pair's remaining bend excess?

    python mean_face_engine.py run <job> --out <folder>
"""

from __future__ import annotations

import sys

import numpy as np

import wadi2d.strips.tables as t

_profile, _line = t.face_profile, t.face_line


def _mean_of_two(pix, ax, ay, bx, by, reach=None):
    length = float(np.hypot(bx - ax, by - ay))
    m = max(int(np.ceil(length / pix.pixel - 1e-9)), 1)
    spacing = length / m
    extra = 0 if reach is None else int(np.ceil(reach / max(spacing, 1e-9)))
    s = (np.arange(-extra, m + extra) + 0.5) / m
    xs, ys = ax + (bx - ax) * s, ay + (by - ay) * s
    nx, ny = (by - ay) / max(length, 1e-12), -(bx - ax) / max(length, 1e-12)
    off = 0.5 * pix.pixel
    z1 = t._sample(pix.z, pix.pixel, pix.x0, pix.y0, xs - off * nx, ys - off * ny)
    z2 = t._sample(pix.z, pix.pixel, pix.x0, pix.y0, xs + off * nx, ys + off * ny)
    z = 0.5 * (z1 + z2)
    return (z, spacing) if reach is None else (z, extra, extra + m, spacing)


t.face_profile = lambda pix, ax, ay, bx, by: _mean_of_two(pix, ax, ay, bx, by)
t.face_line = lambda pix, ax, ay, bx, by, reach: _mean_of_two(pix, ax, ay, bx, by, reach)

from wadi2d.engine.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
