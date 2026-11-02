# W6 dry face fix test

**Status (2026-11-01): the fix works on the GPU and does not fully pass. On branch `fix/dry-face-advection`, not merged.** `numerics.mirror_dry_faces`, on by default there: in momentum advection a neighbour face with u exactly 0, dry or closed, gives the current face's velocity instead of a false zero. Found by `W3 breakline faces test`.

## Rotated channels, production GPU engine, float32, error against Manning, 8 lateral positions

| Case | Off: range, mean | On: range, mean |
|---|---|---|
| 45 deg, vertical walls, 3 cells | +2.05 to +8.46, +6.44 % | -0.45 to +4.21, +1.06 % |
| 45 deg, vertical walls, 6 cells | +0.77 to +3.93, +2.43 % | -1.29 to +1.15, -0.25 % |
| 30 deg, vertical walls, 3 cells | +4.54 to +4.73, +4.64 % | -0.77 to -0.11, -0.46 % |
| 45 deg, 2:1 banks, 3 cells | +1.66 to +8.14, +5.79 % | +0.12 to +5.88, +1.61 % |

W3's 3 % mark fails at one or two positions: +4.21 % on vertical walls, +3.07 and +5.88 % on banks. The GPU worst case is higher than W3's CPU float64 port, +3.16 %. The banks at +8 % off were not in any earlier record, which read one position only.

## Against HEC-RAS with the fix

| Case | Before | After |
|---|---|---|
| Bidah rain-on-grid 10 m, peak / RAS | 1.0002 | 0.9999, NSE 0.999 |
| Bidah rain-on-grid 20 m, peak / RAS | 0.958 | 0.958, NSE 0.983 |
| Fan window 10 m, max level, deep cells | +2.6 cm, rms 5.5 cm | +2.6 cm, rms 5.3 cm |

Steps change by under 0.3 %. Test suite: 709 passed before the new regression test, `tests/solver/test_dry_faces.py`, 2 more.

The full-extent run and every result on `main` were made without the fix. Not rerun.
