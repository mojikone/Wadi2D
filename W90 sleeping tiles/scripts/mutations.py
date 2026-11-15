"""Do the identity tests see a broken rule? Each mutation breaks one piece of the sleeping-tile rule on the valley
with a strip (CPU) and reports whether the sleeping run still equals the run that steps every tile.

    python mutations.py

Expected: the unbroken rule is equal; a reach too short for the steps between two checks is not.
"""

from __future__ import annotations

import numpy as np

from tests.strips.valley import Valley, valley
from wadi2d.solver import stepper as stepper_module
from wadi2d.strips import watch as watch_module

ENDS = (4, 76)
"""The strip ends in the sixth of eight tile columns, two tiles short of the open end, whose tiles are always awake."""


def differs(times=(60.0, 300.0, 900.0, 1800.0, 2700.0, 3600.0)) -> str:
    """Rain on a stretch of the strip alone: the water stays in the strip, runs down it and leaves by its end into
    squares no water had touched, in a tile that slept. Only the strip's wake rule can wake that tile in time."""
    a, b = valley(sleeping=True, strip_ends=ENDS), valley(sleeping=False, strip_ends=ENDS)
    for v in (a, b):
        v.open_end()
        _jj, ii = v.strip_cells
        v.hybrid.set_strip_source(np.where((ii >= 60) & (ii < 80), 3000.0 / 3.6e6, 0.0))
    for t in times:
        for v in (a, b):
            v.advance(t)
        fa, fb = a.fields(), b.fields()
        bad = {k: int(np.sum(fa[k] != fb[k])) for k in fa if np.any(fa[k] != fb[k])}
        steps = (a.model.stepper.nsteps, b.model.stepper.nsteps)
        if bad or steps[0] != steps[1]:
            lost = b.hybrid.volume() - a.hybrid.volume()
            return f"DIFFERS at t = {t:g} s: steps {steps}, entries {bad}; awake {a.awake()}; water short {lost:.1f} m3"
    squares = float(a.model.field("h").sum()) * 400.0
    return f"equal to the last bit through t = {times[-1]:g} s; awake at the end {a.awake()} of {b.awake()}; in the squares {squares:.0f} m3"


def main() -> None:
    print("the rule as built              :", differs())

    keep = watch_module.MARGIN
    for margin in (-10, -14, -17):
        watch_module.MARGIN = margin
        print(f"reach {16 + margin:2d} cells (16 steps a check):", differs())
    watch_module.MARGIN = keep

    wake = stepper_module.Stepper._wake
    stepper_module.Stepper._wake = lambda self, tiles: None
    print("no halo and wet-share pass at a wake:", differs())
    stepper_module.Stepper._wake = wake

    rule = Valley.__init__  # noqa: F841  (kept to show nothing else is patched)
    from wadi2d.strips import hybrid as hybrid_module

    real = hybrid_module.Hybrid.tiles_to_wake
    hybrid_module.Hybrid.tiles_to_wake = lambda self, wet: np.zeros(wet.size, bool)
    print("no wake rule for the strip at all   :", differs())
    hybrid_module.Hybrid.tiles_to_wake = real


if __name__ == "__main__":
    main()
