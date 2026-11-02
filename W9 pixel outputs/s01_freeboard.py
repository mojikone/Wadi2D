"""The pass marks of the sloped surface: straight channel 45 m wide on 30 m cells, the case of W2's s09b_freeboard.py.

Run from the repository root with PYTHONPATH on it. Writes freeboard.json. ``level`` is the mean surface over the wet
pixels, as s09b; ``fill`` is the flat fill of the same water, which is what a cell really holds on a slope.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from tests.products.conftest import channel_case, marks, surface_of

HERE = Path(__file__).resolve().parent
rows = []
for slope in (0.01, 0.05, 0.10):
    flat_error = 12.5 * slope  # half a cell less half a pixel
    for label, freeboard in (("1.5 x flat", 1.5 * flat_error), ("0.5 x flat", 0.5 * flat_error)):
        case = channel_case(slope, freeboard)
        flat = np.where(np.isfinite(case.level), case.level, np.nan)
        row = {"slope": slope, "freeboard": round(freeboard, 3), "against": label}
        for name, level, is_flat in (
            ("flat", case.level, True),
            ("sloped_level", case.level, False),
            ("sloped_fill", case.fill_level, False),
        ):
            result = marks(case, surface_of(case, level, flat=is_flat))
            row[name] = {k: round(v, 3) for k, v in result.items()}
        rows.append(row)
        print(row, flush=True)
(HERE / "freeboard.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
