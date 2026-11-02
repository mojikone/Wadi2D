# W4 plan_min test

**Status (2026-11-01): accuracy passes; the speed gain is not shown. `plan_min` stays at 0.02 until a clean timing exists.**

`plan_min` is the floor on a cell's wet plan share in the wave-speed sum. One setting changed, 0.02 to 0.05, on the frozen Bidah rain-on-grid jobs already compared with HEC-RAS 6.6 (`validation/ras_rain_on_grid.md`). Pass mark, fixed in `s01_jobs.py` before running: peak within 1 % of baseline, ratio to RAS inside +/-10 %, time of peak within 2 min, mass error under 1e-6.

| Bidah section | Peak, m3/s, 0.02 to 0.05 | Change | Time shift | Wadi2D / RAS | Steps | Loop time, s |
|---|---|---|---|---|---|---|
| 20 m | 601.6 to 602.8 | +0.19 % | 0 min | 0.958 to 0.960 | -9.5 % | 14.5 to 15.0 |
| 10 m | 622.0 to 622.0 | -0.01 % | 0 min | 1.000 to 1.000 | -6.0 % | 48.0 to 52.3 |

Both pass. Steps fell, loop time did not: a CPU test was running at the same time, so the timing is not clean. One catchment, natural ground, no crest lines. Rerun `wadi2d run jobs\\..._planmin05.json --out runs\\...` on an idle machine, then `s02_compare.py`, before changing the default.
