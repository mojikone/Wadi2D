"""lattice.py with face_step pasted into two loops, for timing only.

Numba passes about forty arrays by value to a non-inlined face_step, and that call overhead hides the arithmetic: the first bench had the
lattice 6 x slower than the polygon kernel, which does more work. This module rewrites the source text, so the statements are the same ones
and the two kernels are compiled alike. Results must equal lattice.py exactly; run_bench.py checks that.
"""
from __future__ import annotations

from pathlib import Path

_src = (Path(__file__).parent / "lattice.py").read_text(encoding="utf-8")
_fs = _src[_src.index("@njit\ndef face_step(") : _src.index("@njit\ndef step(")]
_body = _fs.split('"""One face: s is the array step along the normal, p across it. Returns the wave speed."""\n')[1].rstrip() + "\n"
_lines = []
for line in _body.split("\n"):
    t = line.strip()
    ind = line[: len(line) - len(line.lstrip())]
    if t == "return 0.0":
        line = ind + "continue"
    elif t == "return 1e30":
        line = ind + "wmax = 1e30\n    " + ind + "continue"
    elif t.startswith("return "):
        line = ind + "wmax = max(wmax, " + t[len("return ") :] + ")"
    _lines.append("    " + line if line.strip() else line)
_pasted = "\n".join(_lines)

_st = _src[_src.index("@njit\ndef step(") : _src.index("class Lattice:")]
_head = _st[: _st.index("    w = 0.0\n")]
_tail = _st[_st.index("    area = dx * dx\n") :].replace("    return w\n", "    return wmax\n")
_setup = """    wmax = 0.0
    ux_, vy_, ux1_, vy1_ = u, v, u1, v1
    mx_, my_, mx1_, my1_ = mx, my, mx1, my1
    s, p = 1, st
    u, vp, m, q, qp, u1, m1, q1 = ux_, vy_, mx_, qx, qy, ux1_, mx1_, qx1
    fl, fr, gl, gr, ef, cw, ftab, fstart, fscale = flx, frx, glx, grx, efx, cwx, ftx, fsx, fscx
    for a_ in range(alist.size):
        k = alist[a_]
"""
_second = """    s, p = st, 1
    u, vp, m, q, qp, u1, m1, q1 = vy_, ux_, my_, qy, qx, vy1_, my1_, qy1
    fl, fr, gl, gr, ef, cw, ftab, fstart, fscale = fly, fry, gly, gry, efy, cwy, fty, fsy, fscy
    for a_ in range(alist.size):
        k = alist[a_]
"""
_new_step = _head + _setup + _pasted + "\n" + _second + _pasted + "\n" + _tail
_full = _src[: _src.index("@njit\ndef step(")] + _new_step + _src[_src.index("class Lattice:") :]
_full = _full.replace("from __future__ import annotations\n", "", 1)
exec(compile(_full, "lattice_fast_generated", "exec"), globals())
