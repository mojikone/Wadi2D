"""Result lines that read a lumped inflow's pond rather than the flow (W31).

Interface: :func:`inflow_crossings`.

A lumped hydrograph enters the grid at a few cells with no momentum; in a gorge pocket it ponds and surges between them,
a sawtooth of seconds. A line whose faces touch those cells reads the surge in its raw peak, and a ring on a lumped
subbasin's edge passes about half the hydrograph. The lumped element's own series is the number of record there.
"""

from __future__ import annotations

import numpy as np

from wadi2d.terrain.crest import NORTH, staircase


def _touched(grid, coordinates) -> set[tuple[int, int]]:
    """The cells either side of every face under the line."""
    st = staircase(grid, coordinates)
    north = st.axis == NORTH
    j_other = np.where(north, st.j - 1, st.j)
    i_other = np.where(north, st.i, st.i - 1)
    return set(zip(st.j.tolist(), st.i.tolist(), strict=True)) | set(zip(j_other.tolist(), i_other.tolist(), strict=True))


def inflow_crossings(lines, inflows: dict[str, set[tuple[int, int]]], grid) -> list[str]:
    """One warning per line that touches the cells of a lumped inflow, in words.

    ``inflows`` maps an inflow's name to its cells as (j, i).
    """
    notes = []
    for line in lines:
        touched = _touched(grid, line.coordinates)
        hit = sorted(name for name, cells in inflows.items() if touched & cells)
        if hit:
            notes.append(
                f"line {line.name} crosses the cells where the lumped hydrograph of {', '.join(hit)} enters the grid: "
                "its raw peak reads the pond's surge there, not the flow; read the lumped element's own series "
                "(series/network_<name>.csv), or move the line downstream of the inflow"
            )
    return notes
