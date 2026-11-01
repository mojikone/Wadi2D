"""Weir: the free law is the maximum of the crest discharge; the drowned references behave and join it."""

from __future__ import annotations

import math

import numpy as np
import pytest

from wadi2d.validation import BoundaryKind, UniformGrid
from wadi2d.validation._constants import G
from wadi2d.validation._hydraulics import froude, specific_energy, specific_force
from wadi2d.validation.cases.weir import (
    MODULAR_LIMIT,
    DrownedReference,
    borda_crest_depth,
    build_weir,
    drowned_unit_discharge,
    free_unit_discharge,
    villemonte_unit_discharge,
)

GRID = UniformGrid(0.0, 0.0, 1.0, 200, 3)
HEAD, CREST = 1.0, 2.0


def test_free_law_is_the_ideal_critical_section() -> None:
    assert free_unit_discharge(1.0) == pytest.approx(1.7046, abs=1e-3)
    head = 1.7
    yc = 2.0 * head / 3.0
    assert free_unit_discharge(head) == pytest.approx(yc * math.sqrt(G * yc))


def test_free_law_is_the_largest_discharge_at_that_head() -> None:
    y = np.linspace(0.01, 0.99, 981) * HEAD
    q = y * np.sqrt(2.0 * G * (HEAD - y))
    assert q.max() == pytest.approx(free_unit_discharge(HEAD), rel=1e-5)
    assert y[np.argmax(q)] == pytest.approx(MODULAR_LIMIT * HEAD, abs=2e-3)


def test_free_case_is_subcritical_upstream_critical_on_the_crest_supercritical_downstream() -> None:
    case = build_weir(GRID, head=HEAD, crest_height=CREST)
    weir = case.solution
    assert froude(weir.q, weir.upstream_depth) < 1.0
    assert froude(weir.q, weir.crest_depth) == pytest.approx(1.0)
    assert froude(weir.q, weir.downstream_depth) > 1.0
    total = CREST + HEAD
    assert specific_energy(weir.q, weir.upstream_depth) == pytest.approx(total)
    assert specific_energy(weir.q, weir.crest_depth) + CREST == pytest.approx(total)
    assert specific_energy(weir.q, weir.downstream_depth) == pytest.approx(total)
    assert case.boundaries.east.kind is BoundaryKind.TRANSMISSIVE


def test_crest_sits_on_one_cell_column_of_the_bed() -> None:
    case = build_weir(GRID)
    bed = case.bed()
    assert np.count_nonzero(bed[0]) == 1
    assert bed[0, GRID.nx // 2] == CREST
    h = case.exact(0.0).h
    assert h[0, GRID.nx // 2] == pytest.approx(MODULAR_LIMIT * HEAD)


def test_crest_as_a_line_on_a_face_leaves_the_bed_flat() -> None:
    case = build_weir(GRID, crest_width=0.0)
    assert np.all(case.bed() == 0.0)
    assert case.solution.crest_x == pytest.approx(GRID.x0 + (GRID.nx // 2) * GRID.dx)


def test_textbook_drowned_law_joins_the_free_law_and_falls_to_zero() -> None:
    limit = MODULAR_LIMIT * HEAD
    assert drowned_unit_discharge(HEAD, limit) == pytest.approx(free_unit_discharge(HEAD))
    assert drowned_unit_discharge(HEAD, limit * 1.0001) == pytest.approx(free_unit_discharge(HEAD), rel=1e-6)
    assert drowned_unit_discharge(HEAD, 0.5 * limit) == free_unit_discharge(HEAD)
    assert drowned_unit_discharge(HEAD, HEAD) == 0.0
    depths = np.linspace(limit, HEAD, 50)
    q = [drowned_unit_discharge(HEAD, y) for y in depths]
    assert np.all(np.diff(q) < 0.0)


def test_drowned_case_with_the_textbook_reference() -> None:
    tailwater = 2.85
    case = build_weir(GRID, tailwater=tailwater)
    weir = case.solution
    assert weir.crest_depth == pytest.approx(tailwater - CREST)
    assert weir.q < free_unit_discharge(HEAD)
    assert weir.q == pytest.approx(0.85 * math.sqrt(2.0 * G * 0.15))
    assert case.boundaries.east.kind is BoundaryKind.DEPTH
    assert case.boundaries.east.depth == tailwater


def test_borda_reference_closes_energy_and_momentum() -> None:
    tailwater = 2.9
    crest_depth = borda_crest_depth(HEAD, CREST, tailwater)
    assert crest_depth is not None
    q = crest_depth * math.sqrt(2.0 * G * (HEAD - crest_depth))
    assert specific_energy(q, crest_depth) == pytest.approx(HEAD)
    crest_side = q * q / crest_depth + 0.5 * G * (crest_depth + CREST) ** 2
    assert crest_side == pytest.approx(specific_force(q, tailwater), rel=1e-9)


def test_borda_weir_stays_modular_above_the_textbook_limit() -> None:
    """A tailwater the textbook calls drowned, with the crest still critical by momentum."""
    tailwater = CREST + 0.75 * HEAD
    assert borda_crest_depth(HEAD, CREST, tailwater) is None
    assert drowned_unit_discharge(HEAD, tailwater - CREST) < free_unit_discharge(HEAD)


def test_drowned_references_differ_and_that_is_on_record() -> None:
    tailwater = 2.9
    textbook = build_weir(GRID, tailwater=tailwater).solution
    borda = build_weir(GRID, tailwater=tailwater, reference=DrownedReference.BORDA).solution
    assert borda.q > textbook.q
    assert (borda.q - textbook.q) / textbook.q > 0.02


def test_villemonte_factor_runs_from_one_to_zero() -> None:
    assert villemonte_unit_discharge(HEAD, 0.0) == pytest.approx(free_unit_discharge(HEAD))
    assert villemonte_unit_discharge(HEAD, HEAD) == 0.0
    assert villemonte_unit_discharge(HEAD, 0.8 * HEAD) < free_unit_discharge(HEAD)


@pytest.mark.parametrize("tailwater", [2.5, 3.0])
def test_a_tailwater_that_cannot_drown_is_refused(tailwater) -> None:
    with pytest.raises(ValueError, match="does not drown"):
        build_weir(GRID, tailwater=tailwater)
