# W34 reservoir start level

**Status (2026-11-07): done on QGIS 3.44.8, branch `feature/dam-start-level`. A dam's pool starts empty unless the job names it, his decision: a design run reads the dam's attenuation from an empty pool, and a scenario (a breach, say) sets a level. One table in the dock's Structures section gives each named dam Empty, Spillway crest or a Level; one value sets whichever pool the run routes, the lumped reservoir or the pool behind the crest on the grid, never both. Through the real dock on Bidah's own dam, 23 of 23: full to the 100 m spillway holds 3.833 Mm3, 2.5 % over W32's hand-drawn polygon. Initial water polygons, job-only until now, have a dock row too.**

## What was wrong

A generated basin's reservoir started full to its lowest spillway crest, while the same dam on the grid started dry. On Bidah that was 3.6 Mm3 apart, nearly the whole 100-yr flood (4.25 Mm3 of rain on the catchment); W32 had to fill the grid pool by hand to compare the two.

## What it does now

- **Default: empty.** A generated reservoir's start is derived at the foot of its pool table. A `basin.json` written before this change, which derived the spillway crest, reads as empty too; a start typed in the file by hand stays.
- **`dam_levels`** in the job, one entry per dam: `{"name": ..., "start": "empty" | "spillway" | <level, m>}`. Empty is the default and is not written, so old jobs keep their hash and their checkpoints.
- **Which pool takes it.** A reservoir of that name that routes in the run's lumped network takes it (generated or HMS-imported); its grid cells drain to the hand-back above the dam, so filling them too would count the pool twice. Any other name is a crest line or an embankment on the grid, and the pool behind it is filled.
- **The grid pool** at level L is found on the cells: those whose lowest ground is under L, joined through faces still open at L (crest and spillway faces closed up to their crests, as the solver has them), touching the dam's line, and reaching no open boundary. A dam drawn in pieces is one dam. Each piece is judged alone, and a held body of water takes the side most of its cells lie on; two held bodies on opposite sides of one piece are refused, since which is the pool cannot be told. Water that reaches an open boundary is refused too: the line does not close the valley at that level, or the pool runs out of the domain. The run notes how many cells and how much water it filled.
- **Dock:** in Structures, a table lists each named crest line or embankment once, with Start (Empty, Spillway crest, Level; the meaning in each tooltip) and Level, m. Below it, a polygon layer and its level field write `initial_levels`. A Level row with no level, or a polygon with no level, stops the run in words.

## Results

| Check | Result |
|---|---|
| Synthetic V valley, 1 % fall, sides 0.2, dam at 200 m, spillway 100 m (`tests/engine/test_dam_levels.py`) | grid pool 1,320 m3 against 1,333 m3 analytic (−1.0 %); level at a pool point 100.00 m; nothing below the dam; the same pool with the dam drawn as two pieces either way |
| Empty, unnamed and named empty | no water at the start, the same hash as before |
| Level over the crest; a name that is no dam | refused, in words |
| Lumped reservoir by name | empty = foot of the table, spillway = lowest spillway crest, a level inside the table; off the table refused |
| **Bidah's dam through the real dock** (`dock_dam_start.py`, `log_dock_dam_start.txt`) | **23 of 23**: three crest pieces at 105 m named in a layer field make one row; empty writes nothing and starts dry; full to the spillway starts with **3,832,907 m3** in 1,810 cells of 20 m; a level of 98 m holds less; a pond polygon reaches the job and holds water |

W32 (item 6b) filled the same grid pool at 100 m through a polygon bounded by the dam line and reaching 3 km up the valley: 3.740 Mm3 with crest lines, 3.658 with the W8 embankment. The fill here is 2.5 % over the crest-line figure. [Likely] the difference is the tail of the pool beyond that polygon, which is the direction it goes. **The first run of the check compared against 3.658, misread from W32's table, and failed at +4.8 %**; the reference was corrected to the crest-line figure, and the check now also asks that the full pool is no smaller than the polygon's.

Found on the way: Bidah's main crest line bends, and near a bend the nearest segment put a few pool cells on the other side of the line, so the first version refused the dam as "held on both sides". The side of a held body is now its majority side (`s01_pool_sides.py` lists the bodies beside each piece).

## What changes for earlier runs

Any run on a generated basin whose reservoirs had a spillway started them full; they now start empty, so the dam's outflow is lower and later wherever the flood does not fill the pool. To reproduce such a run, name the dam with `spillway`. HMS-imported reservoirs keep their file's Initial Elevation unless the job names them.

## Not tested

- A generated basin through the dock with the reservoir routing lumped and taking its start: covered by unit tests on the lumped network, not by a dock run.
- HMS-imported reservoirs from the dock: the table lists dams of the Structures layers, so an HMS reservoir whose name no line carries is set in `job.json` only.
- On the mesh, a grid pool is refused in words; draw it as an initial water polygon there.
- A dam breach itself is not built; this is the start level such a scenario needs.

## Rerun

```
powershell -File tests\dock\run_check.ps1 "W34 reservoir start level\dock_dam_start.py" <throwaway folder> -Copy "W34 reservoir start level"
.venv\Scripts\python -m pytest tests\engine\test_dam_levels.py tests\plugin\test_dam_rows.py
```
