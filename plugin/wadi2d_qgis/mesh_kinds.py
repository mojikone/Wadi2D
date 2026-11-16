# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The Mesh section's kind and what Build mesh says, without Qt (W101 item 4).

The kind is not stored: it is read from the two switches a saved model has always held, the quadtree's tick
(``mesh.enabled``) and the corridors' tick (``strips.enabled``), so a model from before opens on its own kind and
writes the job it wrote. Choosing a kind sets the two switches.
"""

from __future__ import annotations

SQUARES, QUADTREE, ALIGNED = "squares", "quadtree", "aligned"
KIND_WORDS = {
    SQUARES: "Squares: one cell size everywhere, Terrain's",
    QUADTREE: "Quadtree: the finest cells on the wadis, coarser on the hills",
    ALIGNED: "Aligned centre mesh: cells along the streams, squares beyond",
}
KIND_NOTES = {
    SQUARES: "Every cell the size Terrain gives. Crest lines and walls in Structures hold high ground on the faces.",
    QUADTREE: (
        "Tiles of 32 cells halve and double, 2:1, from the finest cell (Terrain's) to the coarsest: the finest on "
        "wadis draining more than the first area, one step coarser past the second, zones and lines where you draw "
        "them (W10, W23). A mesh saves time above about 1 M cells."
    ),
    ALIGNED: (
        "Each stream of the Suggest breaklines file becomes a chain of faces with 4-sided cells either side, Terrain's "
        "cell size across, repeated outward to the floor's edge; polygons of 5 to 8 faces join them to the squares "
        "(W46, the four Block 2 runs). Press Suggest breaklines first and choose its layer."
    ),
}
GENERATORS = ("rings", "centres")


def kind_of(quadtree: bool, corridors: bool) -> str:
    """The kind a model's two switches mean; both on is an aligned mesh the engine refuses on the quadtree, and the
    section says so."""
    if corridors:
        return ALIGNED
    return QUADTREE if quadtree else SQUARES


def switches(kind: str) -> tuple[bool, bool]:
    """(quadtree, corridors) for a kind."""
    return kind == QUADTREE, kind == ALIGNED


def _cells(n: int, words: str) -> str:
    return f"{n:,} {words}"


def built_words(summary: dict) -> str:
    """What Build mesh says, from the engine's ``mesh.json``."""
    kind = summary.get("kind", QUADTREE)
    if kind == ALIGNED:
        text = (
            f"{summary['cells']:,} cells: {_cells(summary['aligned'], 'aligned along the streams')}, "
            f"{_cells(summary['squares'], 'squares')} ({summary['replaced']:,} squares replaced). Smallest cell "
            f"{summary['smallest_m2']:,.0f} m2, a square of {summary['smallest_m']:.1f} m."
        )
    elif kind == SQUARES:
        text = f"{summary['cells']:,} square cells of {summary['smallest_m']:g} m."
    else:
        tiles = ", ".join(f"{n} of {size}" for size, n in summary["tiles_by_size"].items() if n)
        text = (
            f"{summary['cells']:,} cells, {summary['ratio']:g} x fewer than the uniform grid. Smallest cell "
            f"{summary['smallest_m']:g} m. Tiles: {tiles}."
        )
        text = " ".join(
            [
                text,
                *(
                    f"{line['name']}: {line['near']:g} m for {line['rows']} rows each side, no coarser than "
                    f"{line['far']:g} m within {line['reach']:,.0f} m."
                    for line in summary.get("lines", [])
                ),
            ]
        )
    left = summary.get("left_out") or []
    if left:
        text += f" Left out of the mesh, lumped: {', '.join(left)}."
    notes = summary.get("notes") or []
    if notes:
        said = " ".join(note.rstrip(".") + "." for note in notes[:MOST_NOTES])
        more = len(notes) - MOST_NOTES
        text += " The mesher: " + said + (f" And {more} more of the kind." if more > 0 else "")
    return text


MOST_NOTES = 4
"""The mesher's notes said in full; on Bidah the centre mesh gives one per stream, 13."""


__all__ = ["ALIGNED", "KIND_NOTES", "KIND_WORDS", "QUADTREE", "SQUARES", "built_words", "kind_of", "switches"]
