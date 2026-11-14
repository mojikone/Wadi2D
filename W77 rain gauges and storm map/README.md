# W77 rain gauges and storm map

**Live.** Branch `feature/rain-gauges-map`, off `feature/fast-products` at `1ace4e8`; not merged, nothing pushed.

His word of 2026-11-14: one place for rain. W65 left two things open: the rain gauges stayed in the Gauges section
(7b), which held rain, flow and level gauges in one table, and Preview rain gave a table and a chart but no map.

## 1. The rain gauges in the Storm section

**Storm > Rain source: Rain gauges** now holds the rain gauges themselves: the point layer and its name field, the
table (Name, Record, Series, Position x, y), Add rain gauge and Remove, then how rain is spread (nearest gauge or
inverse distance squared), the search radius (inverse distance only), what a gap does, what a rain CSV holds, and the
run's start. **7b. Gauges** keeps flow and level gauges (Name, Gauge, Record, Series, Line, point or element) and a
start of its own.

| W54's one table | Now |
|---|---|
| rain, flow and level rows in one table, a point layer for rain | rain rows in Storm (with the point layer), flow and level rows in 7b (`sections/gauge_table.py` is the one table widget both use) |
| one "Run starts at" for the rain and the records | Storm's start is the rain's (`storm.rain_start`); 7b's is the records'; **7b's left empty takes the rain's**, which is what the one field gave |
| a rain row incomplete was refused even when the storm was not the gauges | rain rows are read and checked only when the Rain source is the gauges; the job never held them otherwise |
| the Storm page listed the gauges and opened 7b | gone with its use: the table is on the page |
| new rows numbered G1, G2 ... across all kinds | numbered within each table: a default name can differ from W54's for the same clicks; a named row is the same |

**The job is the same for the same rows.** The dock joins the two tables into W54's one (`gauge_rows.joined_gauges`)
before the job builder, which is unchanged but for one line: the observed records take `observed_start` when given,
else `start` as before. The job lists rain gauges and observed records apart, each in its table's order, so the order
of the two tables cannot change it. `tests/plugin/test_gauge_rows.py` builds the job from W54's single-table values
and from the two tables for each case and compares them whole: rain gauges only (nearest gauge, a start); rain, flow
and level (inverse distance in a radius, zero gaps, a start); rain and flow with no start (neighbours gaps); flow and
level under a design storm with a start; an empty 7b. All equal. A record start typed in 7b beside a rain start goes
to the records only. **Old jobs load unchanged:** no engine schema or job key changed; the dock does not read job
files back.

## 2. The storm map before the run

**`wadi2d rain-preview JOB --out FILE --map DIR`** (new option) writes `rain_map.json` beside the preview: every
lumped subbasin and the 2D area with its polygon (WKT, the DEM's system) and its depth, peak and area as the preview
gives them; for gridded or gauge rain also `rain_total.tif`, the total depth over the domain
(`wadi2d/engine/rain_map.py`):

- a gridded file: the grid's own pixels summed over the event, times the area factor, cropped and masked to the domain;
- rain gauges: each gauge's total spread by the job's method at pixel centres, 400 pixels along the domain's longer
  side; gauge weights a job gives a lumped subbasin replace the method for that subbasin only, so they are not on it;
- a design storm, a hyetograph or the HMS storm: no raster, the rain is even; the areas layer only.

A subbasin with no polygon (an HMS basin without its .sqlite or a polygon file) is left off the map and listed under
`missing`.

**Preview rain** now loads it into the model's **Inputs > Hydrology** under its own slot (`SLOT_RAIN`,
`layer_groups.py`): "Rain depth by area, before the run", each area in a blue of its depth in five steps from the least
to the most, labelled with its name and depth; and "Total rain depth, before the run", the raster in the same blues.
Each preview replaces the last one's layers and deletes its files (`rain_layers.py`, `rain_query.py`).

Tests: `tests/engine/test_rain_preview.py` 3 new: a grid reduced at 505 km2 draws its two pixels at 40 and 10 mm times
the factor and its mean is the 2D depth; two gauges by nearest gauge give 60 mm west of the bisector and 15 mm east,
the 2D area 37.5 mm; a lumped subbasin and the 2D area tile the domain, no raster on even rain. The real-engine QGIS
smoke on 3.44.8: 20 mm on the plane's 2D area with no raster; two gauges of 30 and 10 mm by nearest gauge, 20 mm on
the 2D area, a raster from 10 to 30 mm, styled, replacing the first map.

## 3. Through the real dock

W65 left the W20 and W54 dock scenarios on the old widgets. They were copied here (W20's and W54's own files stay as
their records), moved to the new widgets and the CPU engine, and run through `tests/dock/run_check.ps1` in a throwaway
QGIS 3.44.8 profile. Changed lines carry "W77". The checks and their pass rules are W20's and W54's.

| Scenario | Result | Against the original |
|---|---|---|
| `dock_gauges.py` (W54): two rain gauges from a point layer in Storm, a flow gauge typed in 7b, Bidah 03 at 30 m, nearest gauge then inverse distance; plus step 2b, the storm map | **42 of 43** | W54 34 of 35 |
| `dock_storm.py` (W20): steady, table, refusal, paste, design storm with reduction, NetCDF-4, classic NetCDF, start date, GeoTIFF folder north only, DSS, mesh, a bad file, then the Block 2 hybrid on the HMS storm and on the same rain as frames | **40 of 41** | W20 41 of 41 on the GPU |

**The gauges scenario reads W54's numbers to the digit.** Cell shares were 0.4444 / 0.5556, mean rain 23.332 mm and
rain 667,188 m3, with peaks at Bidah 03 of 141.657 and 142.487 m3/s by the two methods. The job writes `rain_start`
2021-10-04 00:00 and the flow record's `start` is the same, taken from the rain because 7b's start was left empty. The
one failure is W54's own rule, set before W54's run, that the methods move the dam line's peak by more than 2 %: they
move it 0.6 % here as there.

**The storm map through the real dock (step 2b).** Preview rain, before any run, put both layers in `Wadi2D – thiessen
> Inputs > Hydrology`. The raster runs from 10.0 to 40.0 mm by nearest gauge. The 2D area is drawn at the preview's
23.280 mm, within 0.23 % of the run's own mean of 23.332 mm: the preview weights pixels by area over the exact
polygon, the run reads the gauge under each cell's centre (`render_storm_map.png`).

**The storm scenario's one failure is a ring, not a change.** Its rule is "every steady line within 0.5 % between the
HMS storm and the same rain as frames". It read 0.52 %, on `S5_ring`: 633.1 against 636.4 m3/s. Hills and plain took
the same water to 1e-9 (84,501,544 and 35,884,012 m3). Every dam line was within 0.13 %: Faydh 01 901.7 / 900.5,
Z4C 1,674.2 / 1,673.8, R2A, R5A and Bidah 03 within 0.01 %. `S5_ring` sits on a lumped inflow's pond surge (W31). On
W20's GPU run its roughness classed it as flickering and kept it out of the steady set. On the CPU at this run it fell
under the flicker threshold, so it counted. [Likely] it is the run-to-run sensitivity W33 measured at rings round
lumped inflows, not the rain input: the rain was the same to 1e-9. Not traced further.

Two things the harness needed, both in this folder's scenario and not in the harness:

- **W68's groups.** `h.group_of("north")` looked a run's group up by its folder name. W68 named it `Results – north`,
  so the scenario now finds it through `layer_groups.find_run_results`. W20's own file would now fail there for the
  same reason.
- **The CPU.** A 48 h Block 2 hybrid at 40 m takes about 45 min on the CPU engine (506,615 cells), past the harness's
  1,000 s per step and 2,400 s in all. The scenario raises `h.STEP_LIMIT` and `h.TOTAL_LIMIT` for itself. The first
  attempt hit the old limit. Its QGIS closed but its engine ran on and held `runs/hms`, which broke the next attempt's
  run in that folder. The folder was cleared and the scenario run a third time, the result above.

Logs: `log_dock_gauges.txt`, `log_dock_storm.txt`. Pictures and the run inputs: `dock_check/*/`. Runs are not kept.

## Tests

- `.venv\Scripts\python -m pytest -o addopts="" tests/plugin`, CPU: **562 passed**, including the QGIS 3.44.8 smoke
  scripts, fake and real engine (new: the rain gauge page's rows and rules equal W54's one table, the storm map on even
  and on gauge rain).
- `tests/plugin/test_gauge_rows.py`: 7 new (four cases of the job against W54's, the empty 7b, the records' own start).
- `tests/engine/test_rain_preview.py`: 6 of 6 (3 new).
- The full suite of the repository was not run.

## Not done

- **No raster for a design storm on a grid of point depths through the HMS route** (`storm.depth_grid`). Its areas
  layer is drawn and its raster is not. A gridded file with an area reduction does get one.
- The map draws gauge rain by the spatial method only. Gauge weights given per subbasin in a job are not on the raster.
  Their subbasins' depths in the areas layer are right.
- 7b's start falls back to the rain gauges' start in the job the dock writes. The engine's own fallback
  (`storm.rain_start`, then the gauge storm's start) is unchanged.
- The Block 2 hybrid's `S5_ring` reads 0.52 % between the two rain forms on the CPU against the 0.5 % rule. It was not
  traced, see above.
