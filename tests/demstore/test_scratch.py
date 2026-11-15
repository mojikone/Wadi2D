"""W84: a window's arrays are given out again only when nobody holds them, and a used window reads as a fresh one."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pytest

from tests.demstore.test_store import NX, NY, beds
from wadi2d.demstore import chunks as chunks_mod
from wadi2d.demstore import scratch as scratch_mod
from wadi2d.demstore.scratch import Scratch


@pytest.fixture(autouse=True)
def small_chunks(monkeypatch):
    monkeypatch.setattr(chunks_mod, "CHUNK", 64)
    monkeypatch.setattr(chunks_mod, "_STORES", {})


def memory(a: np.ndarray) -> int:
    return a.__array_interface__["data"][0]


def test_the_interpreter_counts_as_the_scratch_expects() -> None:
    assert scratch_mod._ALONE is not None  # else nothing is reused, and the reads are only slower


def test_free_arrays_come_again_and_held_ones_do_not() -> None:
    scratch = Scratch()
    z, mask, used = scratch.arrays(30, 40)
    assert not used and not z.any() and mask.all()
    where = memory(z)
    again = scratch.arrays(30, 40)
    assert not again[2] and memory(again[0]) != where  # z and mask are still held here
    del z, mask, again
    z, mask, used = scratch.arrays(30, 40)  # the last pair made, free now
    first = memory(z)
    del z, mask
    z, mask, used = scratch.arrays(20, 50)  # another shape of no more pixels: the same memory
    assert used and memory(z) == first and z.shape == (20, 50) and z.flags.c_contiguous and z.flags.writeable
    part = z[3:5]
    part[:] = 7.0
    del z, mask
    other = scratch.arrays(30, 40)
    assert not other[2] and memory(other[0]) != first  # a slice keeps the window
    other[0][:] = 1.0
    assert (part == 7.0).all()
    del part, other
    assert scratch.arrays(30, 40)[2]  # the pair made while the slice was held is the kept one now, and free
    held_mask = scratch.arrays(30, 40)[1]
    assert not scratch.arrays(30, 40)[2]  # the mask alone keeps the pair
    del held_mask


def test_a_small_window_takes_no_large_one_and_a_large_one_is_not_kept(monkeypatch) -> None:
    scratch = Scratch()
    scratch.arrays(100, 100)
    assert not scratch.arrays(10, 10)[2]  # under a quarter of the kept pair: its own arrays
    assert not scratch.arrays(200, 200)[2]  # larger than the kept pair
    monkeypatch.setattr(scratch_mod, "KEEP_PIXELS", 50)
    other = Scratch()
    other.arrays(10, 10)
    assert not other.arrays(10, 10)[2]


def test_an_interpreter_that_does_not_count_reuses_nothing(monkeypatch) -> None:
    monkeypatch.setattr(scratch_mod, "_ALONE", None)
    scratch = Scratch()
    scratch.arrays(5, 5)
    assert not scratch.arrays(5, 5)[2]


def test_windows_kept_by_the_reader_keep_their_pixels(tmp_path) -> None:
    plain, stored = beds(tmp_path)
    with plain, stored:
        boxes = [(r, c, 70, 90) for r in range(-30, 260, 45) for c in range(-30, 380, 55)]
        kept = [stored.read(*box) for box in boxes]  # every window alive at once
        for box, z in zip(boxes, kept, strict=True):
            np.testing.assert_array_equal(z, plain.read(*box))
        pairs = [stored._window(r, c, 70, 90) for r, c, _h, _w in boxes]
        for (r, c, _h, _w), (z, mask) in zip(boxes, pairs, strict=True):
            want_z, want_mask = plain._window(r, c, 70, 90)
            np.testing.assert_array_equal(z, want_z)
            np.testing.assert_array_equal(mask, want_mask)


def test_a_used_window_reads_as_a_fresh_one(tmp_path) -> None:
    """After a window full of ground, the same arrays take a window past the edge, one of holes, one with holes."""
    plain, stored = beds(tmp_path)
    with plain, stored:
        seen = set()
        for box in [
            (200, 20, 80, 60),
            (-40, -30, 80, 60),
            (60, 120, 80, 60),
            (0, 0, 80, 60),
            (280, 400, 80, 60),
        ]:
            z, mask = stored._window(*box)
            seen.add(memory(z))
            want_z, want_mask = plain._window(*box)
            np.testing.assert_array_equal(z, want_z)
            np.testing.assert_array_equal(mask, want_mask)
            del z, mask
            for fill in (True, False):
                np.testing.assert_array_equal(stored.read(*box, fill), plain.read(*box, fill))
        assert len(seen) == 1  # one pair of arrays served them all


def test_each_thread_has_its_own_arrays(tmp_path) -> None:
    plain, stored = beds(tmp_path)
    with plain, stored:
        boxes = [(r, c, 64, 64) for r in range(0, NY - 64, 16) for c in range(0, NX - 64, 16)]
        want = [plain.read(*box, False) for box in boxes]

        def read(
            box,
        ):  # one bed for all the threads, as a careless caller would: its arrays are still a thread's own
            z = stored.read(*box, False)
            return z.copy(), memory(z)

        with ThreadPoolExecutor(8) as pool:
            got = list(pool.map(read, boxes))
        for (z, _where), w in zip(got, want, strict=True):
            np.testing.assert_array_equal(z, w)
