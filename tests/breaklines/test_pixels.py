"""Thinning, the pixel-graph walk and the line tools, on shapes drawn by hand."""

from __future__ import annotations

import numpy as np

from wadi2d.breaklines.pixels import branches, length_of, simplify, smooth, straightness, thin, walk


def test_a_thick_bar_thins_to_one_pixel_and_keeps_its_length():
    mask = np.zeros((20, 60), bool)
    mask[7:12, 5:55] = True
    skel = thin(mask)
    assert skel.sum(axis=0)[10:50].max() == 1
    assert skel.any(axis=0)[8:52].all()
    lines = walk(skel)
    assert len(lines) == 1
    assert len(lines[0]) >= 45


def test_a_cross_walks_into_four_lines_meeting_at_the_centre():
    mask = np.zeros((31, 31), bool)
    mask[15, :] = True
    mask[:, 15] = True
    lines = walk(mask)
    assert len(lines) == 4
    assert all((ln[0] == (15, 15)).all() or (ln[-1] == (15, 15)).all() for ln in lines)
    assert sum(len(ln) - 1 for ln in lines) == 60


def test_a_thick_bar_at_any_angle_walks_as_one_line():
    for angle in (10.0, 27.0, 45.0, 60.0, 80.0):
        jj, ii = np.indices((120, 120))
        t = np.deg2rad(angle)
        across = np.abs(-np.sin(t) * (ii - 10) + np.cos(t) * (jj - 10))
        along = np.cos(t) * (ii - 10) + np.sin(t) * (jj - 10)
        skeleton = thin((across <= 2.5) & (along >= 0) & (along <= 100))
        lines = walk(skeleton)
        assert len(lines) == 1, angle
        assert len(lines[0]) == skeleton.sum()


def test_a_closed_ring_walks_as_one_loop():
    mask = np.zeros((12, 12), bool)
    mask[2, 2:10] = mask[9, 2:10] = True
    mask[2:10, 2] = mask[2:10, 9] = True
    assert (branches(mask)[mask] == 2).all()
    lines = walk(mask)
    assert len(lines) == 1
    assert (lines[0][0] == lines[0][-1]).all()
    assert len(lines[0]) == 29


def test_a_diagonal_line_keeps_eight_connectivity():
    mask = np.zeros((20, 20), bool)
    for k in range(20):
        mask[k, k] = True
    lines = walk(thin(mask))
    assert len(lines) == 1 and len(lines[0]) == 20


def test_smoothing_keeps_the_ends_and_simplifying_keeps_a_straight_line_to_two_points():
    xy = np.column_stack((np.arange(50.0), np.sin(np.arange(50.0)) * 0.3))
    out = smooth(xy, 5)
    assert np.allclose(out[0], xy[0]) and np.allclose(out[-1], xy[-1])
    assert np.abs(out[5:-5, 1]).max() < np.abs(xy[5:-5, 1]).max()
    straight = simplify(np.column_stack((np.arange(10.0), np.zeros(10))), 0.1)
    assert straight.shape == (2, 2)
    assert length_of(straight) == 9.0
    assert straightness(straight) == 1.0
    bent = np.array([[0.0, 0.0], [10.0, 0.0], [10.0, 10.0]])
    assert abs(straightness(bent) - np.sqrt(200.0) / 20.0) < 1e-12
