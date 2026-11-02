"""Test 1: one embankment on the Bidah dam axis, overtopped; a crest line in Wadi2D, a 2D Connection in RAS.

The domain, terrain, excess, n and outlets are those of validation/ras_rain_on_grid, read from its case.py. Only the
structure is added. The crest is constant; where the ground along the line stands higher, the ground is the crest in
both models (Wadi2D's face table takes max(ground, crest); RAS's weir profile is written the same way).
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
W1 = Path(r"D:\Mojtaba\Renardet\Wadi2D\W1 research and design note\validation\ras_rain_on_grid")
sys.path.insert(0, str(W1))
import case as base  # noqa: E402

ENGINE = HERE.parent / "engine_f976c23"
VENV = r"D:\Mojtaba\Renardet\Wadi2D\.venv\Scripts\python.exe"
AXIS = base.AXIS  # south-east to north-west
WEIR_C = 1.7046  # Wadi2D's critical-flow coefficient, m^0.5/s, set in RAS too

CONFIGS = {
    # name: dx, crest on the GGC terrain, RAS overflow method (False weir equation, True 2D equations), hours
    "probe20_z92": dict(dx=20.0, zc=92.0, method2d=False, hours=30),
    "probe20_z94": dict(dx=20.0, zc=94.0, method2d=False, hours=30),
    "probe20_z96": dict(dx=20.0, zc=96.0, method2d=False, hours=30),
    "grammar": dict(dx=20.0, zc=94.0, method2d=False, hours=2),
    "base20": dict(dx=20.0, zc=None, method2d=False, hours=30),
    "base10": dict(dx=10.0, zc=None, method2d=False, hours=30),
    # the rule's primary configuration is z94_10; the rest are sensitivities
    "z94_10": dict(dx=10.0, zc=94.0, method2d=False, hours=30),
    "z94_20": dict(dx=20.0, zc=94.0, method2d=False, hours=30),
    "z96_10": dict(dx=10.0, zc=96.0, method2d=False, hours=30),
    "z96_20": dict(dx=20.0, zc=96.0, method2d=False, hours=30),
    "z94_10_2d": dict(dx=10.0, zc=94.0, method2d=True, hours=30),
    "z94_20_2d": dict(dx=20.0, zc=94.0, method2d=True, hours=30),
}

# Diagnosis of RAS's volume error, 6 h, before any flood: is the spurious source the unaligned mesh or the weir?
CONFIGS.update({
    "d6_lattice2d": dict(dx=20.0, zc=94.0, method2d=True, hours=6),
    "d6_aligned": dict(dx=20.0, zc=94.0, method2d=False, hours=6, aligned=True),
    "d6_aligned2d": dict(dx=20.0, zc=94.0, method2d=True, hours=6, aligned=True),
    "a94_20": dict(dx=20.0, zc=94.0, method2d=False, hours=30, aligned=True),
    "a94_10": dict(dx=10.0, zc=94.0, method2d=False, hours=30, aligned=True),
    "a96_20": dict(dx=20.0, zc=96.0, method2d=False, hours=30, aligned=True),
    "a94_20_2d": dict(dx=20.0, zc=94.0, method2d=True, hours=30, aligned=True),
    "a94_10_2d": dict(dx=10.0, zc=94.0, method2d=True, hours=30, aligned=True),
})

# Stage points fixed before the runs: 150 m and 400 m upstream of the axis, normal to its middle leg, from station 450.
STAGE_POINTS = {"pool150": None, "pool400": None}
