"""A domain aligned to catchment polygons (W97): W79's rim removed, a strip of catchment outside the outline added, a
wide piece beyond the catchments (the coast strip) kept with the band that joins it to them."""

from __future__ import annotations

import shapely

from wadi2d.config.schema import DomainSettings
from wadi2d.domain.align import align_outline, outside_cells

CELL = 20.0
UPPER = shapely.box(0.0, 2000.0, 3000.0, 5000.0)
LOWER = shapely.box(0.0, 0.0, 3000.0, 1999.9)
"""Two catchments with a hairline gap between them, as two HMS polygons digitised apart."""
STRIP = shapely.box(-500.0, -1040.0, 3500.0, -40.0)
"""The coast strip, 40 m off the catchments' seaward edge, as W79's."""
CATCHMENTS = [UPPER, LOWER]
WHOLE = shapely.box(0.0, 0.0, 3000.0, 5000.0)


def test_the_rim_goes_and_the_coast_strip_stays() -> None:
    with_rim = shapely.union(WHOLE.buffer(40.0, join_style="mitre"), STRIP)
    tol = DomainSettings().align_tolerance_m
    done = align_outline(with_rim, CATCHMENTS, DomainSettings(), cell_m=CELL)
    wanted = shapely.union(WHOLE, STRIP).union(shapely.box(-40, -40, 3040, 0))
    # exact but for the two junctions of the band and the strip, where the opening rounds a corner of radius tol
    assert done.polygon.symmetric_difference(wanted).area < 2 * tol**2
    assert done.polygon.symmetric_difference(wanted).difference(STRIP.buffer(tol)).area < 1.0
    assert done.report["cells_outside_catchments_before"] - done.report["cells_outside_catchments"] > 1000
    # no cell outside every catchment away from the strip: W79's count, there 13 against 17,420
    assert outside_cells(done.polygon.difference(STRIP.buffer(tol)), WHOLE, CELL) == 0
    assert outside_cells(with_rim.difference(STRIP.buffer(tol)), WHOLE, CELL) > 1000


def test_a_strip_of_catchment_outside_is_added() -> None:
    short = shapely.box(0.0, 0.0, 2930.0, 5000.0)
    done = align_outline(short, CATCHMENTS, DomainSettings())
    assert done.polygon.symmetric_difference(WHOLE).area < 1.0
    assert abs(done.report["gap_added_km2"] - 70.0 * 5000.0 / 1e6) < 1e-4


def test_beyond_the_tolerance_nothing_moves() -> None:
    wide = WHOLE.buffer(300.0, join_style="mitre")
    done = align_outline(wide, CATCHMENTS, DomainSettings(align_tolerance_m=100.0))
    assert done.polygon.symmetric_difference(wide).area < 1.0
    assert done.report["rim_removed_km2"] == 0.0


def test_a_kept_edge_stays_as_drawn() -> None:
    with_rim = WHOLE.buffer(40.0, join_style="mitre")
    south = shapely.LineString([(-100.0, -40.0), (3100.0, -40.0)])
    done = align_outline(with_rim, CATCHMENTS, DomainSettings(keep_m=50.0), kept=[south])
    assert done.polygon.bounds[1] == -40.0
    assert done.polygon.bounds[3] == 5000.0
