# W73 basin points and editing

**Live.** Branch `feature/basin-editing` off `feature/fast-products` at `d430700`; not merged, nothing pushed.

His to-do of 2026-11-14 and `W58 HMS elements and dam workbook/README.md` sections 4 and 5: a point layer the user clicks
(outfalls, design points, dams, diversions, sources), all outfalls in one go, merge and split of subbasins and reaches,
walls and burn lines from the job's own terrain objects with a tick for the delineation, no separate HMS tools.

## 1. Walls and burn lines in the delineation (`wadi2d/basin/barriers.py`)

Every terrain object has a new field `delineate` (`TerrainObject.delineates`): **None means on for `wall` and `burn_line`,
off for the rest** (W58 section 5); a spillway never delineates. The 2D never reads it: the job hash and the grid cache
leave it out, so a job's checkpoint and tables keep.

| Object, ticked | What it does to the ground the basin is delineated on |
|---|---|
| wall | raised to its own `z`/`z_constant`, else the ground plus `basin.wall_raise_m` (100 m, new), on the 4-connected line of pixels it touches |
| crest line | raised to its crest the same way |
| burn line | cut to its invert or by its depth (the 2D's own pixel edit) |
| channel, channel_dyke, embankment | the 2D's own built ground: cuts where it lowers, raises where it lifts |

- **Cuts go in before WhiteboxTools' least-cost breach, raises after it**, with the depressions they close filled and the
  D8 lines taken on the filled ground; W58's [Likely] that a breach cuts through a wall is so avoided rather than tested.
- A pixel any object cuts is never raised: where a burn crosses a wall the burn wins, as in HMS.
- `Surface.z` stays the ground as read (slopes, sections, pools); on a wall's pixels the slope ground is the breached
  ground under it, so a longest path starting on a wall does not read a 100 m drop.
- The model's notes say which objects were applied.

Tests (`tests/basin/test_barriers.py`, 10, hand counts on a plane falling due south, where each column carries only itself):
under a 101-pixel wall every pixel holds 2 (itself and the wall pixel above), against 102 with no wall; what the wall holds
back passes round its two ends, to the pixel; a burn line carries everything north of it in the 51 columns it crosses and
the column under its middle keeps only what lies below it; the burn's own column passes the wall through the cut; nothing
enters a ring wall; the tick off changes nothing; the job hash is the same with the tick on or off.

[Likely] A raise narrower than the analysis pixel on a shaped object (an embankment crest of 2 m on 5 m pixels) can fall
between pixel centres and leak; walls and crest lines do not, they take every pixel they touch.

## 2. The Basin points layer (`wadi2d/basin/points.py`, `pour.py`, `network.py`, `elements.py`)

One point layer; its `kind` field says what each point is. **A layer with no `kind` field reads as plain break points, as
before**, so old jobs keep their numbers. Every edit is a point, never an element name, so a regeneration replays them
after the threshold or the DEM changes (HMS deletes its edits on a rerun of Delineate Elements).

| kind | Fields | What the generator does |
|---|---|---|
| `outfall` | | A node and an outlet. With any outfall in the layer, the model keeps only what drains to one and each outfall drains nowhere: several outfalls make several networks in one generation. An outfall above another stays a node of that network (said in the notes) |
| `design_point` | `alias` | A node; the alias goes to `pour_point.aliases` |
| `dam` | `crest_line` | The dam of that crest line takes the point's name as an alias. No such crest line: it stays a junction, said in the notes (W58 decision 4 is his) |
| `diversion` | `method`, `divert_to`, `table`, `limits` (JSON text) | A junction carrying a `diversion` block; see below |
| `source` | `file` (CSV or DSS, relative to the layer's folder), `series`, `area_km2` | A `source` element draining to the junction it snaps to; the hydrograph is read at generation into `basin.json` |
| `junction` | | A forced node: splits the reach and the subbasin it lands on |
| `remove_junction` | | Drops the node it snaps to: the reaches on either side become one; at a confluence the tributary's reach runs on along the D8 line to the next node, and its subbasin drains there |
| `join_subbasins` | | Makes one subbasin of the local subbasins draining to the node it snaps to, HMS's merge; area, longest path, 10-85 slope, lag and Tc are measured again on the union |

Areas, flow lengths, slopes, lags and Tc are all measured again by the regeneration: an edit is never a patch of the file.

**Refusals, in words, that stop the generation:** a kind not in the list (named); a `remove_junction` or `join_subbasins`
farther than `snap_m` from any node; a `remove_junction` on a point of the job or of the layer ("delete that point
instead") or on an outlet; a `join_subbasins` on a node with fewer than two local subbasins; a source with no file, a
file not found, or missing flows.

### The diversion block, for the worker on `feature/hms-diversions`

A diversion point makes an ordinary **`junction`** element in `basin.json`, routed as a junction until a loader reads this
block. Nothing in `wadi2d/hydrology/` was touched:

```json
{"kind": "junction", "name": "Div", "downstream": "R3", ...,
 "diversion": {"method": "Inflow-Diversion Table", "divert_to": "Site", "table": null,
               "limits": {"max_m3s": 50}, "point": "Div"}}
```

- `method`: the text of the layer's field, meant as a name in `ROUTING_METHODS` (today `Inflow-Diversion Table` is the
  only one registered); not checked here.
- `divert_to`: the name of the element that takes the diverted flow, as the user typed it; not checked against the model
  here [the loader should refuse a name the model does not hold].
- `table`: the field's text (a path or an inline table, the diversion element's to decide); `limits`: parsed from JSON
  text, else the generation stops.
- `point`: the Basin point's name.

### The source element

`basin.json` gains a kind `source` (`contract.SOURCE`, required: `hydrograph`):
`parameters.hydrograph.value = {"minutes": [...], "flow_m3s": [...]}`, beside `file`, `series` and `area_km2`, and
`downstream` the junction. A CSV is read through `wadi2d.io.series` (minutes, hours or dates); a DSS record the same, CFS
converted to m3/s. A dated record is taken from its first time, at the start of the run (said in the notes). In the
lumped engine a source runs as a reach with no inflow whose routing (`wadi2d/basin/source.py`, registered as `Source
hydrograph`) returns the hydrograph, linear between its times, nothing before the first or after the last. `area_km2` is
carried, not yet added to the drainage area below (HMS's representative area).

Tests (`tests/basin/test_points.py`, 18, on the two arms joining one valley of the conftest): a layer without kinds reads as
before; a junction splits a reach and a subbasin and the subbasins above it hold its drainage area; `remove_junction` at the
fork gives two reaches into the next junction, each the length of its arm plus the main reach below the fork within two
diagonal pixels, the area above unchanged; the three refusals; `join_subbasins` at the fork makes one subbasin of the two
arms, area their sum, Tc measured; two outfalls on the two arms make two networks, each its own drainage area, the rest
left out and counted unassigned; an outfall above another stays linked; a source's hydrograph in the file and through the
lumped engine at the junction to 1e-8; the diversion block and an alias; a dam point without its crest line; an unknown
kind; `build_basin` writes the source into `basin.gpkg`'s junctions layer.

## 3. The dock (`plugin/wadi2d_qgis/sections/basin.py`, `basin_points.py`, `basin_point_rows.py`)

In section 3's **Generate the basin from the DEM** box:

- **Basin points**: the point-layer combo (was "Pour points") and **New layer**, which makes an empty memory layer with
  every field, styled by kind, in the model's Inputs > Hydrology under its own slot, so a regeneration never removes it.
  Save it to keep it.
- **Add a point**: the eight kinds and **Click on the map**: one click adds a point of that kind, named afresh
  (`Outfall 1`, `Junction 1`, `Remove 1` ...), and the box says that Generate basin applies it.
- **Generate basin takes the last generation's layers off the map before it starts**: Windows refuses to replace a
  `basin.gpkg` that QGIS holds open, so before W73 a second generation in one session failed with `Access is denied`
  (found by the dock check below); the new layers come back when it ends.
- **Delineate on**: one tick per terrain-object kind (Crest lines, Walls, Burn lines, Embankments, Channels, Channels with
  dykes), walls and burn lines ticked. Written into the generation job only where it differs from the engine's default;
  a crest, wall, spillway or burn layer's own `delineate` field outranks the tick. The run's job never carries it.
- Every Basin points field the layer has is passed on; a source's relative `file` is made absolute against the layer's
  folder, because the dock writes the points beside its basin job.

Tests: `tests/plugin/test_basin_point_rows.py` (5), `tests/plugin/test_contract.py` (+2: the kinds and the default ticks
are the engine's; the ticks reach the generation job and not the run's), the schema sample regenerated (+22 lines).

Through the real dock: `dock_basin_points.py` (`tests/dock/run_check.ps1`, a throwaway QGIS 3.44.8 profile) on Bidah 03's
ground and dam (W27's set-up, 2 km2 threshold), the real engine generating seven times, each edit replayed on the next.
**36 of 36** (`logs/log_dock_basin_points.txt`, `logs/widget_basin_box.png`):

| Step | Result |
|---|---|
| the box offers the eight kinds; Walls and Burn lines ticked, the rest not | pass |
| plain generation: 8 subbasins, 4 reaches, 4 junctions, 1 reservoir | pass |
| New layer: the box's choice, with the kind field, in Inputs > Hydrology; it survives every regeneration | pass |
| a `junction` clicked at the middle of the longest reach: 9 subbasins, a node named `Junction 1` | pass |
| `join_subbasins` clicked on a confluence: one subbasin there, 9.8484 km2, the two summed | pass |
| `remove_junction` clicked on another confluence: J3 gone, the subbasins still cover 22.3552 km2 | pass |
| `source` clicked on Junction 1 with a CSV: `Source 1` drains to Junction 1, `basin.json` holds 0, 40, 0 m3/s | pass |
| a 850 m wall across the reach: the notes name it (6.43 to 6.49 km2 now reach the edge); the Walls tick off: no wall applied and `delineate: false` in the generation job | pass |

Each step's map tool is the box's own (`canvasClicked` emitted as the canvas does), and the button comes back up with the
box's words. **Edits replay in one order on the regenerated network: removals, then joins.** In the check, removing J3
ran its tributary on to J2, and the join already at J2 then took that subbasin too (8 to 6 subbasins, not 7): the
consistent reading of "every edit is a point", but a reader of the points layer should know it.

## Not done

- Right-click on a generated subbasin, reach or junction offering the edits (W58 section 4): the kind combo and one click
  do the same; the junctions table has no kind column yet.
- A per-feature `delineate` field on the shaped objects' layers (embankments, channels): their tick is per kind only.
- A diversion's element (the other worker's), a source's `area_km2` in the drainage area below, a source in the hybrid's
  2D wiring beyond the lumped network (it enters at its junction, and the junction's route decides as for any junction).
- The Block 2 basin regenerated with points (no run of his ground beyond Bidah).

## Files

- `dock_basin_points.py`: the dock scenario; `logs/`: its log and the box's picture.
