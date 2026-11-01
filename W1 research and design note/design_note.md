# Wadi2D design note, version 1

Status (2026-11-01): live; the build follows it. He said "go ahead and come back with the software", so this note was written while
building, not approved beforehand. Everything here was measured in `prototypes/` or read in `research/raw/` unless tagged.

## 1. What changed from the first decisions

| Recorded | Now | Why |
|---|---|---|
| Decision 1: collocated second-order Godunov (MUSCL, HLLC) | **Staggered explicit scheme**: level per cell, conservative momentum per face | Sub-grid tables sit exactly on these unknowns; TUFLOW HPC, the accepted GCC tool, does the same; the source review `research/raw/N01_subgrid_scheme_decision.md` reached the same verdict independently; still water is exact by construction |
| Decision 18: `dx <= h/S` as a hard rule | A guide. The sheet-flow treatment below keeps storage and timing right at cell drops many times the depth | Measured on planes of 1-20 %: storage within 1 % at dx 20 and 40 m |
| Energy-head advection at contractions (Stelling and Duinmeijer) | Dropped; momentum form everywhere, plus a critical-flow limit on crest faces | Measured: better on Ritter, Stoker, the hump and the channels, and simpler |
| Decision 2: crest faces handled by the ordinary scheme | Crest faces carry a limit, because the plain scheme over-discharges a thin crest (ratio 2.7 measured) | Limit gives ratio 0.996 against ideal critical flow |

## 2. The scheme

Cell state: mean depth `hbar = V / dx^2`, float32 (decision 3). `d` is the level above the cell's lowest pixel, read from the cell table.
Face state: velocity `u`, momentum `M`, discharge `Q`. For a face with cell L on one side and R on the other, `fl`, `fr` are the face
invert over each cell's zmin, so `eL = dL - fl` and `eR = dR - fr` are both depths over the same invert. No absolute elevation exists in a
kernel, so float32 keeps its resolution at any datum.

One step:

1. **Faces.** `eup` is the depth on the upwind side (by the sign of `u`, or the higher side at rest). Below `e_wet` the face is dry.
   Otherwise read `A(eup)`, `T = K^(3/5)`, wet width `W` from the face table.
   - *Section.* `Avol = hup dx`. If `Avol < A`, `rho = alpha + (1 - alpha) Avol/A`, `alpha = min(edown/eup, 1)^4`. Thin flow spreads over the
     cell instead of standing at its low edge; a drowned face passes its whole area.
   - *Drive.* `dEta = eR+ - eL+`. When the downstream level is under the invert the face is disconnected and the drive is
     `max(eup, min(drop, |eL - eR|))`, with `drop` the mean-surface drop clipped at the crest:
     `drop = (hup - gU) - max(hD - gD, (gU - gD)/2)`, `g` the invert over each mean bed. Thin sheet flow then feels the bed slope and a crest
     does not. Bounding it by the true level difference keeps still water still.
   - *Momentum.* `M* = M - dt (F_R - F_L + F_N - F_S)/dx`, each `F = Qc u*` with `Qc` the cell-centre discharge and `u*` upwinded with a minmod
     correction. `u* = M*/Abar - dt g dEta/dx`, `Abar = (hL + hR) dx / 2`. The velocity form was tried and rejected: it converges to the wrong
     shock (plateau 5.009 m against 5.079 m at every dx).
   - *Friction.* Implicit in the speed, with the transverse velocity at the face:
     `u = 2 u* / (1 + sqrt(1 + 4 dt g F s))`, `F = (A/K)^2 rho^(-4/3)`, `s = sqrt(u*^2 + v^2)`.
   - *Crest faces* (`cw > 0`): `|Q| <= cw A sqrt(A/W)`. `cw` is 1.705 on natural crests (invert above both mean beds by 5 cm) and crest lines,
     and the user's C on spillways. Drowning follows from the momentum balance: the limit stops binding near r = 0.85.
2. **Positivity.** `r = min(1, V/(outflow dt))` per cell; each face takes the ratio of its upwind cell, so mass is conserved exactly.
3. **Cells.** `hbar += dt (div Q)/dx^2 + dt src`; `d` from the table.
4. **Boundaries.** Prescribed-level cells: fixed stage, free (dry), or following an inner cell lowered by `S dx`. Every other edge is a wall.
5. **Step.** `dt = cfl dx / max(|u| + sqrt(g d))` over cells with `d > h_cfl`, refreshed every `dt_every` steps.

Tables are quadratic in the row: level against hbar is read linearly in the row (exact on a plane, O(1), no search); area and `K^(3/5)` are
read linearly in depth (exact for a wide section). Face tables reach at least `face_depth_min` above the invert: a table that stopped at the
face's relief extrapolated wrongly above it and gave a 12 % velocity error.

Layout, in `wadi2d/solver/layout.py`: compact tiles of 32 x 32 with a 2-cell halo; kernels use plain offsets; tile 0 is the void.

## 3. Measured

| Test | Result |
|---|---|
| Still water, rough bed at 1,500 m, 25 % dry cells (float64 prototype) | max velocity 2.4e-13 m/s; float32 about 2e-4 m/s |
| Stoker | plateau 5.077 against 5.079 m; L1 falling with dx |
| Ritter, Thacker | see `tests/solver/test_analytic.py`, limits are measured values plus a margin |
| Rain on planes of 1, 5, 20 %, dx 20-40 m | storage within 1 % of the kinematic wave; a plain flat-surface sub-grid holds 14 % of it |
| Thin crest | 0.996 of critical flow |
| Aligned channel, 3 cells wide | normal depth within 1 % |
| Rotated channel, 45 degrees, final code | 2:1 banks: +6.8 % at 1.5 cells wide, +2.0 % at 3, +0.8 % at 6. Vertical walls: +11 % at 3, +2 % at 6. 30 degrees: +4 to 5 % |
| Speed on the RTX 5080, all cells wet, real tables | 2.2 to 2.9 G cell-updates/s; 1 M cells 0.48 ms per step; 48 h at 1 s step in 1.4 min |
| Speed on real runs, GPU idle | Block 2, 2.03 M cells, 48 h: 8.9 min, 1.28 ms per step, 1.58 G cell-updates/s. 8.1 M cells, 36 h: 42 min |
| HEC-RAS 6.6, 3 x 3 km fan, inflow only | 10 m: +2.6 cm, rms 5.5 cm, F 0.936, Q within 0.2 %, 39 x faster |
| HEC-RAS 6.6 rain-on-grid, Bidah 22 km2, same excess | 10 m: 622.0 against 621.9 m3/s, NSE 0.999, wadi +6.9 cm, fan F 0.934, 145 x faster. 20 m: 4.2 % low, wadi +14.6 cm. Crests not compared |

## 4. Module map

`config/` schema and constants, the single source of truth. `grid/` tile bookkeeping. `tables/` pixels to tables. `terrain/` DEM access and
vector objects. `solver/` layout, state, stepper, model, `gpu/` and `cpu/` backends. `hms/` readers. `hydrology/` lumped engine. `storm/` rain
as a function of time. `forcing.py` config + grid to what the solver consumes. `io/` files. `run.py` wires one job. `arf.py` a depth-area
study as independent jobs. `engine/cli.py` the process protocol. `validation/` analytic cases. `plugin/wadi2d_qgis/` the QGIS plugin, which
imports none of this. Dependency direction: `config` <- everything; `solver` knows nothing of storms or files; `run.py` is the only module that
imports all.

## 5. Process protocol

```
wadi2d schema                          JSON Schema of job.json
wadi2d doctor                          environment report
wadi2d run job.json --out DIR [--backend auto|gpu|cpu] [--dry-run] [--resume]
wadi2d arf job.json --out DIR          depth-area study: one run per storm area, design-point table
wadi2d hms-import HMS_DIR --basin F --met F --control F --out job.json
```

Exit codes: 0 finished; 1 unexpected; 2 invalid job; 3 input missing; 4 backend unavailable; 5 numerical failure, with the cell; 6 stopped on
request; 7 out of memory. Stop: create the empty file `DIR/stop`.

Run folder: `config.resolved.json`, `progress.jsonl` (one JSON object per event: `{"ev": "start|step|output|warn|done|error", ...}`, the plugin
tails it), `live/depth.tif` (rewritten in place, one float32 band, the plugin reloads it), `maps/max_depth.tif`, `max_speed.tif`, `hazard.tif`,
`arrival.tif`, `series/*.csv`, `results.h5`.

Grid cache: tables are the only expensive artefact; cached by a hash of DEM identity, extent, dx, terrain objects and table settings.

## 6. Hydrology coupling

The lumped engine runs first, one way, on the HMS time step. A lumped subbasin's hydrograph enters at its outlet: a source spread over the
receiving cells, proportional to depth once they are wet, all to the lowest cell before. Its polygon masks rain on the cells beneath it (decision
5). 2D subbasins take rain on the cell with CN losses per cell (per-cell CN is the weighted-Q method, HMS's composite CN the weighted-CN
method; volumes differ where CN varies, and that is a property of the methods, research H01). Mode (a) runs no 2D.

## 7. ARF

As decision 9 with research H06: one run per storm area (K = 6 by default), log-linear interpolation of ln Q in ln A at design points, the
five named design points may be added as exact members. The table's type is printed on every output: `ARF FM` is a storm-centred ratio of
one cyclone, not a fixed-area curve (research H06), and the reports must say so. Reviewer vocabulary: "depth-area analysis".

## 8. Known limits

- Rotated channels narrower than about 3 cells run deep (section 3). Natural banks are less severe than vertical walls. Keep a wadi at 3 cells or more.
- No eddy viscosity. Recirculation behind obstacles is under-resolved.
- A ridge inside a cell, parallel to its faces, is invisible unless a crest line marks it (TUFLOW has the same limit; its breakline detection is
  a version-2 item).
- First-order in time; the Thacker limit stands in `tests/solver/test_analytic.py`.
- Lateral inflow carries no momentum.
- The hump case is 3 % high on critical discharge.
- Rain-on-grid over steep hills matches HEC-RAS at one section on one catchment, within about 4 %, and it responds 2 to 3 x faster than the SCS lags in both. No gauge says which is right.
- Steep cells: cells with over 10 m relief hold 2 to 2.6 x less water than in HEC-RAS, unexplained; the hillslope total and the section peak still match.
- At 20 m a narrow steep gorge runs about 15 cm high and 4 % low on peak against HEC-RAS; both halve or better at 10 m. Run design points at 10 m.
- A 20 m face takes its lowest pixel, so a thin ridge can leak at a level the DEM does not show: Bidah's dike at 104.4 m at 20 m, gone at 10 m. Draw a crest line.
- A design line drawn on a spillway reads 4 to 25 % low, because the spillway takes crest faces within one cell. Read the whole dam axis.
- A domain edge is a wall. A run warns when water stands more than `outputs.edge_depth` against one, because the balance still closes.
- Rain falls only on the cell it hits: no transmission loss into the wadi bed, in 2D as in HMS.
