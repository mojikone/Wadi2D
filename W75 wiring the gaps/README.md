# W75 wiring the gaps

**Live.** Branch `feature/wire-gaps` off `feature/fast-products` at `3b196d9`; not merged, nothing pushed. Closes the gaps
between W67, W68, W70, W72 and W73 as merged: a generated basin's diversion point now runs, a source's area counts, the
dock has the controls those pieces left as job fields, and Bidah's pile against the domain edge is re-measured.

The uncomfortable finding first. [Certain] **W70's momentum does not cure Bidah's 4.3 m at the domain edge, because it
is not a pile at the line: it is a pool.** On W61's own job (Bidah at 20 m, 10 mm in half an hour, the flow line on the
middle half of the north outlet, 20 m3/s for 30 min), the cell on the line reads 4.2946 m at rest and 4.2951 m moving;
the water level stands flat at 77.00 to 77.01 m over the 240 m of wadi below the line in both runs, the cell's 4.3 m is
that level over its lowest pixel (72.71 m), and with no flow line the same cell holds 0.42 m and no warning. The line's
36,000 m3 fills a hollow whose level is set by the ground below it, not by how the water enters; the two runs differ by
at most 9 mm anywhere (71 cells over 1 mm). [Likely] a closed or cut-off valley in the domain outline; not looked at.
W61's advice stands: an inflow line wants a wall-free edge or a line a cell inside it, and the warning names the place.

**Through the real dock: 39 of 40** (`dock_wiring_gaps.py`, `tests/dock/run_check.ps1`, a throwaway QGIS 3.44.8
profile, CPU engine, Bidah 03's ground; `logs/log_dock_wiring_gaps.txt`, `logs/pile.json`, `logs/widget_*.png`). The one
failure is the check written before the run that momentum lowers the pile, kept as the record of the finding above.

| Step | Result |
|---|---|
| the Basin points layer gets the `parameters` field; a source and a diversion clicked on one junction; the diversion table shows the point, offers the five methods, its Needs column follows the method; Method, Divert to, Parameters and Limits typed into the table land in the layer's fields | pass |
| Generate basin: `basin.json`'s junction `Diversion 1` carries the read block (Constant Flow, to the outlet J1, `max_volume_m3` 9000); the box names the diversion; the source with no area: the box says the area below is the ground's | pass |
| the source given 3 km2: +3.000 km2 on the diversion junction's and the outlet's drainage area, and the box says so | pass |
| `{"rate": 5}` typed: refused, the last model kept, in the engine's words ("Constant Flow takes no ['rate']; it takes ['rate_m3s']"); mended and generated again | pass |
| a 1 h run on the generated basin: the diversion runs on a live hand-back route (the 2D flood handed back at it), `network_Diversion_1.csv` with `passed_m3s` and `diverted_m3s`: inflow peak 335.5 m3/s, diverted 5.000 m3/s until the volume reaches 9,000.0 m3, passed + diverted = inflow to the CSV's six digits; 2D balance 5e-9 | pass |
| Boundaries: the two columns, off on a free line, ticked and auto on a flow line; a direction chosen reaches the job's line and the momentum tick left alone does not; `momentum: false` in the job only when unticked | pass |
| the pile, at rest and moving | the finding above |
| HMS: W68's copy of his project; the table lists its five reservoirs, four Modified Puls and Bidah 03 Reservoir by Controlled Outflow with `Conduit: Orifice (number barrels 2); Spillway: Rating Curve Spillway; Dam Top: Level Dam`, each "routes as HMS does"; read only | pass |
| a copy whose orifice is a Gated Orifice: "refused: Bidah 03 Reservoir: outlet or option Conduit Gated Orifice is not supported", the run's own words, and the note counts it | pass |

Found on the way: a diversion pointed at the dam above it made a loop that only the run's start refused ("cycle in
basin ..."); the generation now refuses it by name (section 1). The run's whole books carry the HMS-faithful
Muskingum-Cunge's known routing defect (-7,853 m3, W25), not the diversion's.

## 1. A diversion point runs as W72's diversion element (`wadi2d/basin/diversion.py`)

W73's `diversion` block was written into `basin.json` and read by nothing: the junction routed as a junction. Now:

- **At generation** the block is read for the element: the method named (HMS's five names; `inflow function`,
  `constant`, `specified`, `lateral weir`, `pump` also read), the `parameters` and `limits` fields parsed from JSON text,
  the tables read into `basin.json` (`tables`), so the file stands alone as a source's hydrograph does, and the
  element built once to check it. A new field `parameters` on the Basin points layer.
- **The loader** (`wadi2d/basin/loader.py`) builds a `Diversion` with W72's routing and limits from the block alone; a
  hand-written block without `tables` is read there.
- **Fields per method:** Inflow-Diversion Table: `table` inflow and diverted flow, m3/s. Constant Flow:
  `{"rate_m3s"}`. Specified Flow: `table` minutes from the run's start and m3/s, or a CSV or DSS flow record. Lateral
  Weir: `table` channel stage and flow, `{"crest_m", "length_m", "coefficient"}`, optional `"tailwater"` table. Pump
  Station: `table` channel stage and flow, `{"units", "on_m", "off_m", "lift_m", "pump"}`, `"pump"` a head-flow table
  per unit. Limits for any: `{"max_m3s", "max_volume_m3"}`, **the volume in m3, not HMS's 1000 m3**. A table is a CSV of
  two columns beside the layer (a header skipped) or inline `[[x, y], ...]`.
- **Refused in words, stopping the generation:** no method or an unknown one; a parameter the method does not take, or
  one it needs missing; an empty or unreadable table; an unknown limit; `divert_to` not an element of the model, the
  diversion itself, its own main channel, or **above it (a loop)**: the last found through the dock, where the run's
  start refused the loop as `cycle in basin` with no word of the diversion. Blank `divert_to`: the water leaves the
  network (HMS's Not Connected).

Tests (`tests/basin/test_diversion_points.py`, 11, on the conftest's two-arm valley, a source and a diversion on the west
arm's junction, diverted to the east arm's): an inflow-function table with a 15 m3/s cap, diverted = min(0.4 Q, 15) to
1e-12, passed + diverted = inflow per ordinate, all of the diverted flow arriving at the east junction; a constant
10 m3/s with a 60,000 m3 cap, the volume to the cap; a lateral weir from a CSV beside the layer, the CSV deleted before
the run (`basin.json` holds it), the diverted flow C L H^1.5 at the stage of the passed flow to 1e-6; Not Connected; seven
refusals. W73's block test updated to the read block.

Not done: a diversion on the hybrid beyond the dock run (a Constant Flow on a live hand-back route); a Specified Flow
diversion on a hand-back route stays refused (W72); the weir and the pump through the dock.

## 2. A source's area counts below it (`wadi2d/basin/build.py`, `wadi2d/hydrology/model.py`)

- A source point with `area_km2` adds it to `drainage_area_km2` of every node below it in `basin.json` (the chart's
  facts and the junctions table read it), and the engine's source element (`Source`, a reach giving its hydrograph,
  with `area_km2`) counts it in `Basin.drainage_area`, which the ARF and depth-area lookups read: HMS's representative
  area of a source.
- A source without one leaves the ground's area as it is, and the generation's notes say so; the dock's Generate box
  shows the notes.
- Tc is not touched: a source has no flow path on the ground, so the longest path and its slope are the ground's.

Test (`tests/basin/test_points.py`): 12.5 km2 on a source adds 12.5 km2 to the junction it enters and to every node
below, in the file and in the engine; without it, the note.

## 3. The dock

| Control | Where | What it does |
|---|---|---|
| Enters moving, Flows to | Boundaries table, two columns, live on flow rows | W70's `flow.momentum` (ticked) and `flow.direction` (auto, left, right of the line as drawn); a layer's own `momentum` and `direction` fields fill them; written into the job only off the engine's defaults, so a default left alone stays the engine's (the quadtree takes it at rest with a warning; a `momentum: true` written would be refused there) |
| Reservoirs read from HMS | Hydrology, under the HMS files, read only | a new engine command `wadi2d hms-structures BASIN --out JSON` (`wadi2d/engine/hms_structures.py`) builds each reservoir as the run does and lists its blocks in file order (culverts with shape and barrels, orifices, gates, pumps, spillways, dam tops, seepage, evaporation), its fixed main tailwater, and the run's own refusal; the table shows them, a refused row in red, and a line counting how many route |
| Diversion points | Generate box, under Add a point, when the layer holds a diversion point | Point, Method (the five), Divert to, Table, Parameters, Limits and the method's Needs; an edit writes the layer's field; relative tables and table parameters are made absolute against the layer's folder before the generation job is written. The box's summary names each diversion and where it diverts |

Tests: `tests/plugin` whole, 555 passed; `tests/plugin/test_contract.py` (the two columns reach the engine only off
their defaults, the methods and fields are the engine's), `test_hms_structure_rows.py`, `test_basin_point_rows.py`;
`tests/engine/test_hms_structures_cli.py` (a culvert reservoir routes, an Arch culvert is refused in the run's words, the
command writes the file; no `.hms` beside the basin is said).

## 4. Bidah's pile at the domain edge

See the finding at the top: re-measured on W61's job through the dock, at rest 4.2946 m and moving 4.2951 m in the
line's cell at (439416, 2728690), the warning the same in both; the same job without the line 0.415 m and no warning.
The level is flat at 77.0 m for 240 m below the line in both runs: a pool, not the at-rest bump W70 removed on its
channels. Numbers in `logs/pile.json`.

## Files

- `dock_wiring_gaps.py`: the dock scenario (`powershell -File tests\dock\run_check.ps1 "W75 wiring the gaps\dock_wiring_gaps.py" <throwaway folder>`);
  `logs/`: its log, `pile.json` and the widgets' pictures.
