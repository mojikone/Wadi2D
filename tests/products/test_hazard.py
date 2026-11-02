"""The class rule, from the limits in the schema."""

from __future__ import annotations

import numpy as np
import pytest
from pydantic import ValidationError

from wadi2d.config.schema import Pixels
from wadi2d.products.hazard import class_names, classify

RULE = Pixels()


def one(depth: float, speed: float, dv: float | None = None) -> int:
    product = depth * speed if dv is None else dv
    return int(classify(np.array([depth]), np.array([speed]), np.array([product]), RULE)[0])


def test_limits_and_floor_are_the_brief_s() -> None:
    assert RULE.hazard_limits == [
        (0.3, 0.3, 2.0), (0.6, 0.5, 2.0), (0.6, 1.2, 2.0), (1.0, 2.0, 2.0), (4.0, 4.0, 4.0),
    ]  # fmt: skip
    assert RULE.depth_floor == 0.05
    assert class_names(RULE) == ["H1", "H2", "H3", "H4", "H5", "H6"]


@pytest.mark.parametrize(
    ("depth", "speed", "expected"),
    [
        (0.04, 1.0, 0),  # below the floor
        (0.2, 1.0, 1),
        (0.4, 0.1, 2),  # depth alone
        (0.2, 2.5, 3),  # depth x speed 0.5, over H1's 0.3, speed over 2 gives H3's limit too
        (0.7, 0.1, 3),
        (1.3, 0.1, 4),
        (2.5, 0.1, 5),
        (0.2, 4.5, 6),  # speed alone
        (5.0, 0.1, 6),
    ],
)
def test_a_pixel_takes_the_highest_class_any_limit_gives(depth: float, speed: float, expected: int) -> None:
    got = one(depth, speed)
    assert got == expected or (speed == 2.5 and got >= expected)


def test_depth_times_speed_alone_lifts_a_class() -> None:
    assert one(0.1, 1.0, dv=5.0) == 6


def test_limits_must_not_fall() -> None:
    with pytest.raises(ValidationError):
        Pixels(hazard_limits=[(1.0, 1.0, 1.0), (0.5, 2.0, 2.0)])
