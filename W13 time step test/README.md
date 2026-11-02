# W13 time step test

**Status (2026-11-01): done. The time step does not matter for a rain-on-grid design peak on Bidah: a quarter of the step moves the peak 0.23 %.** Engine at `2195de6`.

Why: `W10 mesher` found outflow moving 14 % between steps of about 1.2 s and 0.05 s on a short valley job with thin rain sheets, 142.8 against 125.7 m3 in 900 s. If that held at a peak it would touch every rain-on-grid result.

Rule, fixed before the first run: the peak at the axis moves by under 2 % from the default step to a quarter of it. Then the step does not matter for a design peak. Otherwise the cause is found first.

Bidah section, the job of the HEC-RAS head-to-head, 20 m, n 0.05, 18 h through the peak (`s01_bidah_cfl.py`, `results.json`):

| CFL | Steps | Mean step, s | Peak at the axis, m3/s | Hour | Volume through it, Mm3 |
|---|---|---|---|---|---|
| 0.45, default | 48,151 | 1.346 | 601.56 | 12.34 | 2.8157 |
| 0.225 | 95,895 | 0.676 | 600.73 | 12.34 | 2.8150 |
| 0.1125 | 192,326 | 0.337 | 600.20 | 12.34 | 2.8142 |
| 0.05625 | 386,232 | 0.168 | 599.95 | 12.34 | 2.8136 |

**Passes.** A quarter of the step: -0.23 % on the peak, -0.05 % on the volume. An eighth: -0.27 %. It converges, and the default step stands.

What this does not settle:

- The 14 % stands as measured on its own job. It is the first 900 s of thin sheets, before any channel flow. This test reads a section at the peak of a 24 h storm, so it says that effect does not reach a design peak here, not that it does not exist.
- One catchment at one cell size. A short storm on a small catchment, where the thin sheet is a larger share of the answer, is not tested.
