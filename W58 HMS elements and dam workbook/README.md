# W58 HMS elements and dam workbook: design note

**Status: design only, 2026-11-14, branch `design/hms-elements` off `feature/fast-products` (`4eac3e7`). Nothing is built
here and no engine file is changed. This is the live iteration for the HMS element work; there is no earlier one to supersede.**

The most important finding comes first. [Certain] Every one of HEC-HMS 4.12's own sample projects (`castro`, `river_bend`,
`tenk`, `tifton` in `samples.zip`) is in **English units**, and the Wadi2D HMS reader refuses anything but metric
(`from_hms.py`, "only Metric basin models are read"). So no HEC sample can test a structure until the reader converts
units. Only `river_bend` has outflow structures: a box culvert, a head-discharge pump and a specified-stage tailwater.
Every other test has to come from a metric copy of his Block 2 project, run headless as W55 ran it. The structure keys of
that copy can only be learned from a file HEC-HMS itself has written (see Decisions, item 1).

Iteration and files:

- `template/` holds copies of his two workbooks from the Block 02 session. They are read only, and the originals are untouched.
  They are **not committed**: they carry project hydrographs, and whether the public repo may keep project data is still
  open (root `CLAUDE.md`, open question 5).
- The W1 workbook to check against is `D:\Mojtaba\Renardet\2224 WS11\Batinah\Block 2\Claude Block 02\W1\output\excel\Block02_Dam_Inflow_Hydrographs.xlsx`.
  The reservoir-routed figures are in `...\Claude Block 02\W14 reservoirs Basin 3\output\`.

## 1. What HEC-HMS 4.12 has, and what Wadi2D has today

Sources are HEC's own pages, listed at the end. They are Confluence pages and **carry no page numbers**, so each claim
cites its page and section. [Certain] The User's Manual (UM) pages are the 4.12 ones. The Technical Reference (TRM) pages
carry no version number. Where the TRM gives no equation, this note says so rather than supplying one.

### 1.1 Reservoir routing methods

| HMS 4.12 method | Inputs (UM 4.12) | Wadi2D today (code) |
|---|---|---|
| Outflow Curve (Modified Puls, one routing step) | Storage method: Storage-Discharge, Elevation-Storage-Discharge, Elevation-Area-Discharge, Elevation-Storage-Area-Discharge. Primary curve. Initial condition: discharge, storage, elevation or inflow = outflow (which ones depends on the method) | Only Elevation-Area-Discharge with Elevation-Area primary and an initial elevation (`ReservoirOutflowCurve`); anything else raises |
| Specified Release | Elevation-Storage or Elevation-Area (conic). Initial elevation or storage. A discharge gage. Maximum release and maximum capacity are warnings only, and the gage release is always discharged | No |
| Outflow Structures | Below | Elevation-Area only, broad-crested spillways to main or auxiliary, no tailwater, Zero Evaporation, Adaptive Control On, initial elevation (`ReservoirOutflowStructures`). Anything else raises (`from_hms._outflow_structures`) |
| Rule-Based Operations | Release rules on a reservoir. Not read for this note | No. Not proposed (section 2) |

Routing equations [Certain, TRM "Reservoir Modeling Concepts and Equations"]:

- Level-pool step: (2 S2/dt + O2) = (I1 + I2) + (2 S1/dt - O1).
- Conic storage: dS = dz/3 (A1 + A2 + sqrt(A1 A2)).

Wadi2D reproduces both, measured: Hawasinah 02 to 8e-12 m3/s, Block 2's five reservoirs to 1e-11 (W55).

### 1.2 Outflow Structures: every option

UM 4.12 "Outflow Structures Routing" gives the inputs. TRM "Outlets", "Spillways", "Dam Tops", "Pumps", "Dam Break",
"Dam Seepage" and "Evaporation" give the equations.

| Option | Inputs | Equation or rule | Wadi2D |
|---|---|---|---|
| Storage method | Elevation-Storage, or Elevation-Area (conic) | | Elevation-Area only |
| Initial condition | Elevation, storage, or inflow = outflow (the pool level that passes the first inflow) | | Elevation only, plus the job's `dam_levels` (Empty, Spillway crest, Level) on a generated basin |
| Tailwater, main and auxiliary set separately | None; Reservoir Main Discharge (rating of the reservoir's own outflow); Downstream of Main Discharge (rating of the downstream element's total inflow); Specified Stage (gage); Fixed Stage | Enters the submergence of each structure | None only |
| Time step control | Automatic Adaption Time Step, or Simulation Interval | | Adaptive only. HMS's own split rule was not identified past 0.2 m (`reservoir.py`) |
| Outlet: culvert (up to 10) | Inlet Control, Outlet Control or Automatic. Number of barrels. Shape: arch, box, circular, Con-Span, elliptical, high- and low-profile arch, pipe arch, semi-circular. FHWA chart and scale. Rise, span or diameter. Length. Inlet and outlet inverts. Entrance coefficient 0.2 to 1.0. Exit coefficient. Manning's n | HEC-RAS TRM culvert equations 6-2, 6-3, 6-4 and 6-7, with approach and exit velocities taken as zero, a level quiescent pool and a quiescent stilling basin. Automatic takes the lower flow of inlet and outlet control. **The TRM page states no equation of its own** | No |
| Outlet: orifice (up to 10) | Number of barrels, centre elevation, area, discharge coefficient | O = K A sqrt(2 g H), with H between the pool and the downstream level. The UM requires the inlet submerged by at least 0.2 x its height, and HMS counts the steps where it is not | No |
| Spillway: broad-crested (up to 10) | Crest elevation, length, coefficient (1.10 to 1.66 SI) | Q = C L H^1.5, H the energy head above the crest. A tailwater check adjusts Q, but **the TRM gives no equation for it** | Yes, no tailwater |
| Spillway: ogee | Concrete or earthen abutments (none, one, two). Approach depth and energy loss. Crest elevation and length. Apron elevation and width. Design head | Le = Lc - 2 He (n Kp + Ka); Q = CQ Le He^1.5; CQ = C (Da/HD)^E. C, E, Kp and Ka are read from a table on He/HD. **No apron or submergence equation is given** | No |
| Spillway: specified | Elevation-discharge rating | Table lookup, no submergence | No |
| Gates on broad-crested or ogee (up to 10 per spillway) | Sluice: width, gate and orifice coefficients. Radial: width, coefficients, trunnion height, and the trunnion, opening and head exponents. Control: Fixed Opening, Percent Annual Pattern, Percent Time Series | Sluice free flow: Q = C W B sqrt(2 g H). Radial free flow: Q = C sqrt(2g) W T^TE B^BE H^HE. Submergence starts at tailwater/head 0.67 and is full orifice flow Q = C A sqrt(2 g H) at 0.80. **The submerged sluice formula renders ambiguously on the page** | No |
| Dam top: level (up to 10) | Crest elevation, length (spillways excluded), coefficient | Q = C L H^1.5. Submergence: recompute the head to the tailwater and keep the smaller flow, with no reverse flow | No (the 2D crest faces overtop, the lumped pool raises above its table) |
| Dam top: non-level | Eight-point station-elevation section, one coefficient | Each segment a broad-crested weir. **The page defines no Li or Hi** | No |
| Pump (up to 10) | Number of identical units. Intake elevation. Line elevation. On and off elevations. Minimum rest and run times. Equipment loss. Head-discharge curve | Total head = line - pool + loss, and Q comes from the curve. On at the on level, off below the off level. A minimum run time holds unless the pool falls below the intake | No |
| Dam break (one) | Top and bottom elevation, bottom width, side slopes, development time. Trigger: elevation, duration at elevation, or time. Progression: linear, sine wave or user curve. Piping adds an elevation and a coefficient | Overtop: Q = 1.7 b H^1.5 + 1.35 m H^2.5. Piping: Q = C A sqrt(2 g H) until the pipe reaches the top, then weir flow | No |
| Seepage (one) | Tabular: an inflow curve and an outflow curve | hs = pool - tailwater. Outflow seepage comes from storage and goes to the main outlet. Inflow seepage only adds to storage | No |
| Additional release | Discharge gage | Added to the structure outflow | No |
| Evaporation | Monthly depths. Needs Elevation-Area | The month's depth is spread evenly over its steps and times the current area. Reported separately | Zero Evaporation only |

### 1.3 Diversion methods

[Certain, UM 4.12 "Diversion"]

| HMS 4.12 | Inputs and rule | Wadi2D |
|---|---|---|
| None | All flow down the main link | Yes (no element) |
| Constant Flow | A rate, and an optional annual percent pattern. Limited to the inflow | No |
| Inflow Function | An inflow-diversion table. Its last row should exceed the largest inflow | Yes (`InflowDiversion`). An inflow above the table raises, because HMS's rule there is unknown |
| Lateral Weir | Broad-crested only. Channel rating (stage-flow). Optional tailwater rating. Crest elevation, length, coefficient. Head uniform along the weir | No |
| Pump Station | A channel rating and an optional tailwater rating, plus the reservoir pump's fields. Dynamic head = channel level - line level, at least 0. A submerged line adds its depth | No |
| Specified Flow | A discharge gage, limited to the inflow | No |
| Limits, all methods | Maximum volume (diversion stops once the cumulative volume reaches it). Maximum allowed flowrate (a cap each interval). The flow is computed first and capped after | No |
| Divert To | A downstream element, or Not Connected (the water leaves the system) | Downstream element only |

### 1.4 Source element

[Certain, UM 4.12 "Source"] The inflow is None, a Discharge Gage, or a Constant Flow with an annual pattern. An optional
representative area feeds the drainage area of the elements below.

**Wadi2D has no source element.** [Certain] `basin_from_hms` raises on a Source, and a generated basin has none. The only
way an external hydrograph enters today is a point inflow on the 2D grid.

### 1.5 GIS delineation

[Certain, UM 4.12 "GIS Menu"]

| HMS 4.12 step | What it does | Wadi2D (`wadi2d/basin/`) |
|---|---|---|
| Terrain reconditioning | Build walls along a boundary shapefile (smooth and sharp raise, buffer in cells; a negative raise digs a trench). Burn streams along a stream shapefile (smooth and sharp drop). A burn wins over a wall where they cross | **None.** Delineation reads the raw DEM (`delineate.read_surface`); walls and burn lines act on the 2D only |
| Preprocess sinks, then drainage | Fill pits, then D8 direction and accumulation | WhiteboxTools least-cost breach, then D8 |
| Identify streams | An accumulation threshold, close to the subbasin size | `basin.stream_threshold_km2`, 10 km2 by default |
| Break point manager | Click named break points; the lowest one is the outlet | A point layer (any `name` field), the crest lines of the job (dams) and the design lines and points. They snap within `snap_m` |
| Delineate elements | Prefixes; insert junctions above reaches; turn break points into computation points; the lowest one becomes a sink. A rerun deletes the elements | Yes. A regeneration rebuilds everything from the inputs |
| Split, merge, reverse flow direction | Split one subbasin or reach at a point. Merge adjacent elements that share an outlet; HMS does not check that the result makes sense | **None** |
| Basin characteristics | Longest, centroidal and 10-85 flow paths and their slopes; basin slope, relief, relief ratio, elongation, drainage density; reach slope, sinuosity, relief | Longest path, the 10-85 slope, land slope, the means of the CN and Manning rasters, and an 8-point or trapezoid section per reach (`parameters.py`, `sections.py`) |

[Certain] HMS computes no time of concentration at any element (UM "Basin Characteristics": no Tc or lag formula is
offered). Wadi2D's lag is the owner's Kirpich rule (`kirpich_lag_minutes`).

## 2. Build order for the reservoir structures

The order follows his priority, with one piece of groundwork first that every item needs. Efforts are agent working days,
including the HEC-HMS comparison and the run through the real dock [Guessing, from the size of W29, W34 and W55].
Each item gets its own branch and tests, merged one at a time behind the full suite.

**Test method for every item**, the W55 way:

- Work on a copy of his Block 2 HMS project (never his file).
- Add one test basin per structure: a Source with a DSS inflow hydrograph, then a reservoir carrying the structure, then a sink.
- Run HEC-HMS 4.12 headless (`W55 .../scripts/run_hms.ps1`).
- Run the same network in Wadi2D, and compare outflow, pool level and storage at every step.
- Drive each structure through its regimes with a sweep of inflows: below the crest, free flow, drowned flow, a part-full
  barrel, a pump cycling.
- Fix the tolerance in the test before the run. [Likely] 1e-6 of the peak for closed-form structures, where W55 reached
  1e-11. [Guessing] 0.5 % for culverts, where HMS's own iteration sets the floor.

| # | Item | Inputs | How it is tested | Effort |
|---|---|---|---|---|
| 0 | **Groundwork** | No new user inputs | The Bidah 03 case of W55 still matches to 1e-11. A source-to-sink basin matches HMS exactly. Every new key of every structure is read or raises by name | 3 d |
| 1 | **Rating tables and tailwater** | Elevation-storage or elevation-area tables. Elevation-discharge ratings. Tailwater ratings, a fixed stage or a stage gage | HMS on each storage method and each tailwater kind. A rating with no submergence must equal a broad-crested spillway tabulated at 1 cm to the table's interpolation error | 2.5 d |
| 2 | **Culvert outlets** | The UM fields in section 1.2. The FHWA coefficient tables for the nine shapes | HMS on a box culvert first (`river_bend`'s, converted to metric), then circular. Inlet, outlet and automatic control, with the tailwater swept from dry to above the crown | 6 to 9 d |
| 3 | **Orifice outlets** | Barrels, centre elevation, area, coefficient | HMS, free and drowned. HMS's count of steps under-submerged reproduced as a warning | 0.5 to 1 d |
| 4 | **Dam top, level and non-level** | Crest and length, or a station-elevation section, and a coefficient | HMS on both, with the tailwater above the crest for the smaller-flow rule | 1.5 d |
| 5 | **Gates** (sluice, radial) on broad-crested spillways, and on ogee once item 10 exists | Width, coefficients, exponents. Opening fixed, as an annual percent pattern, or a percent gage | HMS: free, transition (0.67 to 0.80) and orifice regimes. A run starting in January and one starting in July for the annual pattern | 2.5 d |
| 6 | **Pumps** | UM fields | HMS's `river_bend` pump case converted to metric, then 1 and 4 units, with the run and rest times binding | 2.5 d |
| 7 | **Seepage** | Inflow and outflow curves on head | HMS with the tailwater above and below the pool | 1 d |
| 8 | **Evaporation** | 12 monthly depths | HMS over a month boundary. The volume equals the sum of depth x area to 1e-9 | 0.5 d |
| 9 | Additional release | Discharge gage | HMS | 0.5 d |
| 10 | Ogee spillway | UM fields, and the TRM's table of C, E, Kp and Ka | HMS across He/HD from 0.2 to 1.3, both abutment types | 2 d |
| 11 | Specified Release routing | Storage table, gage, the two warnings | HMS, including a storage over the maximum (warn, never cap) | 1 d |
| 12 | Dam break in the lumped reservoir (HMS's own) | UM fields | HMS on overtop and piping, each trigger, linear and sine progression | 3 d |
| 13 | Rule-Based Operations | His rules | **Not proposed.** [Likely] 10 days or more, and his dams have no operating rules | - |
| | Diversions (section 3) | | | 3.5 d |
| | Dock: an outlets editor per dam | | Through the real dock | 4 d |

Items 0 to 8 come to about 20 to 23 days. With items 9 to 12, the diversions and the dock, the total is about 34 to 37
days. Sections 4 to 8 add about 24 to 26 days more.

### 2.1 What the groundwork (item 0) is

- **One structure model.** Each structure is a pure function Q(pool, tailwater) with its dQ/dz, behind a registry, as the
  routing methods already are. The Numba kernel takes the structures as arrays: a kind code per structure and a row of
  parameters. The present Newton solve (`_solve_row`) then sums them, which is what it does today for spillways alone.
  - [Likely] The same functions later serve a 2D link from a pool cell to a tailwater cell, so a culvert through a 2D crest
    line comes at almost no cost. That 2D side is not proposed now (Decisions, item 3).
- **Stateful structures.** A pump's on and off, its run and rest clocks, a breach's progress and a diversion's volume limit
  carry state from step to step. They go in the step loop's state, not in Q(z), and each part of an adaptive bisection
  hands the state on.
- **Results.** Every reservoir writes `pool_m`, `storage_m3` and the flow of each structure beside `inflow_m3s` and
  `outflow_m3s`. `reservoir.pool()` already computes the pool and storage (W55); nothing writes them today. The dam
  workbook needs them.
- **A calendar on the time grid.** `TimeGrid` has no date [Certain]. Evaporation, the annual patterns and the gages need
  one: take it from the HMS control file, or from the job's start time.
- **The Source element.** A Source with a discharge gage or a constant flow. It is the test inflow, and it is also the "add
  source" edit of section 4.
- **The comparison harness.** W55's scripts generalised to "one basin per structure, inflow from DSS, compare every step".
  The metric test project lives in this folder's `hms/`, which is not yet made.
- **Order inside the network.** [Likely] "Downstream of Main Discharge" tailwater needs the other inflows at the downstream
  element in the same step, and today the lumped network routes each element's whole series in turn. Whether HMS uses
  the previous step there is not documented, so the test decides. Until then this tailwater kind raises.

### 2.2 Culverts: why the effort is so large

[Certain, TRM "Outlets"] HMS uses HEC-RAS's culvert routine with two changes: velocities taken as zero, and no approach or
exit cross-sections.

- Inlet control is the FHWA HDS-5 family: unsubmerged forms 1 and 2, the submerged form, and the coefficients K, M, c and
  Y per chart and scale.
- Outlet control is an energy balance through the barrel, with a backwater profile when the barrel runs part full.
- The work is transcribing the HDS-5 coefficient tables for nine shapes, which are public-domain FHWA tables, plus the
  part-full barrel.

[Guessing] To keep the step loop fast, each culvert can be tabulated once per run as Q(headwater, tailwater) on a 1 cm by
1 cm grid. That holds only if the test shows the table within the tolerance; otherwise the kernel calls the culvert
directly. [Likely] HMS warns that a culvert computes 10 to 20 times slower than an orifice.

## 3. Diversions

| Method | Build | Test |
|---|---|---|
| Constant Flow, with the annual pattern | A rate times the pattern's percent, capped at the inflow | HMS |
| Inflow Function | Exists. Match HMS's rule above the last row, once a test shows it | HMS with an inflow past the table |
| Lateral Weir | Channel stage from the rating, then Q = C L H^1.5 over the crest. Submergence from the tailwater rating | HMS, free and drowned |
| Pump Station | The reservoir pump of item 6 on the channel stage | HMS |
| Specified Flow | A gage, capped at the inflow | HMS |
| Limits, all methods | Maximum volume, maximum flow, applied after the method | HMS, each limit binding |
| Not Connected | The diverted water leaves the books on its own line | Mass balance |

About 3.5 days after item 6, because the pump station reuses the pump. In the dock, a diversion point (section 4) carries
the method and the Divert To name. Its tables use the same paired-data editor as the reservoir outlets.

## 4. The point layer and editing the basin

**One "Basin points" layer** replaces the pour-point layer combo in the Hydrology section's Generate box. It holds a
`name`, a `kind` and the fields that kind needs. A layer with no `kind` field still reads as plain break points, so old
jobs keep their numbers.

| Kind | Meaning | Extra fields |
|---|---|---|
| `outfall` | An outlet of the network. Several outfalls make several networks in one generation (his "all outfalls in one go") | - |
| `design_point` | A break with a computation point. A design line still works as now | optional `alias` (the name a workbook shows, as W1 shows R5 for junction R5A) |
| `dam` | A reservoir node | `crest_m` and `crest_line` (the name of a crest line of the job). See Decisions, item 4 |
| `diversion` | A diversion node | `method`, `divert_to`, `table`, `limits` |
| `source` | An external inflow hydrograph entering at the snapped junction | `file` (CSV or DSS path), `series`, `area_km2` (optional) |
| `junction` | A forced junction: the split of a reach, or of a subbasin at a point | - |
| `remove_junction` | Drops the junction it snaps to. The reaches on either side become one, and its local subbasins join the next junction's | - |
| `join_subbasins` | Keeps the junction and makes one subbasin of the local subbasins draining to it (HMS's merge) | - |

[Likely] Every edit is a point, never an element name, because names change when the threshold or the DEM changes. A
regeneration then replays every edit, which HMS does not do: in HMS a rerun of Delineate Elements deletes them.

- **On the map**, the points are styled by kind. Right-click on a generated subbasin, reach or junction offers "Split here",
  "Add junction here", "Make a reservoir here", "Add a source here", "Join the subbasins at this junction" and "Remove
  this junction". Each writes a row to the Basin points layer and asks for a regeneration.
- **In the dock**, the junctions table of the Generate box gains a column for the kind of each node. The subbasin table
  stays as it is.
- **Threshold confluences** ("delineation at main confluences"): `stream_threshold_km2` already breaks at every confluence of
  two streams above it [Certain, `pour.stream_limit`]. A test confirms that several outfalls delineate in one run.

Effort: engine 5 to 6 days, dock and map 4 days.

## 5. Walls and burn lines in the delineation

The job's terrain objects already hold walls, burn lines, channels and embankments for the 2D. Each object gets a tick,
`delineation` (on by default for `wall` and `burn_line`, off for the rest), and the delineation runs on the ground with
the ticked objects applied at the analysis pixel. There is no separate HMS-style wall or burn tool.

- A wall sets each pixel to the larger of the ground and the wall's own top level. If the wall has no level, the ground is
  raised by `basin.wall_raise_m`, after HMS's sharp raise.
- A burn line sets each pixel to the smaller of the ground and its invert profile. Where a burn line and a wall cross, the
  burn wins, as in HMS.
- [Likely] A wall one pixel wide on a diagonal leaks between corner pixels under D8. The wall is widened to a 4-connected
  line.
- [Likely] WhiteboxTools' least-cost breach can cut through a wall if that is the cheapest way out of a closed depression.
  Walls are applied after the breach, with any depression they close filled instead. A synthetic ring wall is the test.

Effort 2 days.

## 6. Time of concentration and the hydrograph chart

### 6.1 Time of concentration at every element and point

His rule, the one his lags follow:

> Tc = (0.75 L)^0.77 / (52 S^0.385) minutes,

where L is the longest flow path in m and S is the 10-85 slope of that path.

- **A subbasin** uses its own path. The lag is 0.6 Tc, as now.
- **A junction, reach outlet, dam, design point or design line** uses the longest D8 path from the whole drainage area
  above it, reaches included. One pass upstream-first over the analysis raster gives every pixel's longest upstream path.
  The 10-85 slope comes from the ground along that path.
- **The network check**, beside it: the time from the centroid of excess rain to the peak of the element's hydrograph.

[Certain] Kirpich (1940) was fitted on small Tennessee farm basins, so on a 200 km2 junction the figure is outside its range.
Both numbers are shown, labelled, and no lag is derived from a junction's Tc.

The figures go in `basin.json` per element, in the element tables of the dock, and in the chart header. Effort 1.5 days.

### 6.2 The chart

**Recommended: right-click on the map, with one shared docked chart panel.**

- Right-click on a subbasin, reach, junction, dam, design point or line on the map and choose "Hydrograph". The existing
  docked Result lines panel (`result_lines.py`), widened to a Results panel, shows that element.
- [Likely] The canvas context menu (`QgsMapCanvas.contextMenuAboutToShow`) is available on his QGIS 3.40 and 3.44.
- An "add to chart" choice overlays a second element. The panel keeps following the time slider, as it does for lines now.

Why not HMS's way: HMS opens a floating window per element, which piles up and loses the time slider. The dock alone means
finding the element in a list while looking at the map.

The chart, after HMS's layout:

- A thin rain bar hangs from the top axis. Rain is light, excess darker, and the losses are the difference.
- The flow plot sits below. A reservoir shows inflow and outflow, with the pool level on a right-hand axis.
- The header carries the name, the drainage area, Tc, the peak, its time, and the volume.

His own layout, when he shows it, replaces this one.

Each element's series gains `rain_mm` and `excess_mm` per interval, with the area reduction already applied. A subbasin
carries its own. A downstream element or a design line carries the area-weighted rain of every subbasin above it.

Effort: engine series 1 day, panel 2 to 3 days.

## 7. The dam workbook

The layout is his approved one: `template/Block02_Dam_Inflow_Hydrographs.xlsx`. A command,
`wadi2d workbook <runs or study> --elements ... --target 200`, and a dock button write it with openpyxl.

**Inputs** are one run per return period, or a depth-area study. Any dams can be chosen: reservoirs, dam lines, or picked
elements and lines.

**Sheets, in order:**

1. **Read me.** Source, method, step, date.
2. **The target return period sheet.**
   - The time column, then one inflow column per dam.
   - The table: dam, catchment, peak inflow (`=MAX`), time to peak (`=INDEX/MATCH`), volume (`=SUM*dt/1e6`), legend and
     label strings.
   - A scatter chart of all dams, with one single-point series per peak carrying the peak label, as the template does.
3. **Peak inflow, Inflow volume, Time to peak.** One row per dam and one column per return period, all formulas pointing
   at the dam sheets' statistics block.
4. **With reservoirs, also Peak outflow, Attenuation (1 - Qout/Qin) and Highest pool level.**
5. **One sheet per dam.**
   - Column A holds the time.
   - Then one inflow column per return period, B:N for 13 periods. With a reservoir, each period has four columns:
     inflow, outflow, pool, storage.
   - The statistics block follows after one empty column, as P:U in the template: peak, time, volume, legend, label. With
     a reservoir it adds peak outflow, attenuation, highest pool and highest storage.
   - The main chart carries all return periods and the peak labels.
   - **Below the main chart, one inflow-outflow chart per return period**, tiled three across at the template's chart size
     (15 x 7.5 cm).

Rules:

- **No Status column** anywhere (his word: it is project-specific).
- The step goes into each volume formula as its number, `*300/1000000` on a 5-minute run, as the template writes it. The
  workbook then rebuilds the W1 file formula for formula.
- [Certain] The sum of the ordinates x dt equals the trapezoid volume when the series starts and ends at zero.

**The check**, fixed before it runs:

- Rebuild the W1 workbook from the same HMS depth-area DSS files that built it (its Read me names them), with the Status
  column removed.
- Compare every cell, mapping the columns past the dropped Status column:
  - data cells exactly, at W1's rounding (time to 4 decimals, flow to 3, as its cells show);
  - formula cells as text;
  - charts by count, anchor, and every series reference.
- Then the same check against W14's reservoir results for the outflow, pool and storage columns.

[Likely] If the workbook goes to the client, it is scanned like a client report (his rule 14). The template's Read me names
the HMS project and model, and that text is internal.

Effort: 3 days, plus 1 day for the check.

## 8. The rainfall input

The dock's Storm section is already one choice with stacked pages (`sections/storm.py`). Three things confuse it today:

- Steady rain and a hyetograph table are two choices for one thing.
- Gauge rain is chosen here, but its fields live in section 7b.
- The area reduction is set in three places: the design page, the gridded page and the depth-area study.

**The redesign: one "Rain source" combo with four choices, and only the chosen one's fields shown.**

| Rain source | Fields shown |
|---|---|
| Design storm with area reduction | Point depth, duration, pattern, and the area reduction (below) |
| Gridded file with area reduction | File or folder, series, units, period, time stamp, run start, and the area reduction (off for observed rain) |
| Rain gauges | The gauge table and the spreading method, moved here from 7b. Section 7b keeps only the observed flow gauges |
| Single hyetograph | The table, with a "constant rain" button that fills it (this replaces Steady rain) |
| As in the HMS project (shown only when one is loaded) | A read-only summary of the HMS storm, and "Copy into the form" |

**The area reduction is one shared block:** None; At one storm area (area plus table, or the HMS table); or By the
depth-area study (section 9), which then shows the study's areas read only.

**A "Preview rain" button** asks the engine, as reading a rain file does now, for each subbasin's depth after reduction,
peak intensity and hyetograph, and for the 2D area's mean depth.

- The dock shows a table and a small chart.
- A temporary map layer colours the subbasins by depth.
- On gridded and gauge rain, a total-depth raster is added.

The engine already computes each subbasin's rain (`storm/by_subbasin.py`, `grid_depth.py`), so this is wiring. Effort 4
days through the dock.

## 9. Deferred, his word

- **Dam breach in the 2D model.** The crest faces would lower over time along a breach trapezoid, which needs face tables
  that change during the run. Item 12's lumped breach gives the check on outflow.
- **Inflow hydrographs as 2D boundary lines.** Today the 2D takes point inflows and stage, normal and free lines. A flow
  line needs the discharge spread along it by conveyance, as HEC-RAS does.

## 10. Decisions for him

1. **Structure keys.** Ten minutes in the HEC-HMS window on a copy of his project: one reservoir carrying an orifice, a
   culvert, a level and a non-level dam top, a gated broad-crested spillway, an ogee, a specified spillway, a pump,
   seepage, a monthly evaporation, a dam break and an additional release, plus one diversion of each method; then save. The
   saved file names every key, and without it each key is a guess. Only the culvert and pump keys are known now, from
   `river_bend`.
2. **English units.** Teach the HMS reader English units, about 2 days, so HEC's own samples become tests? Otherwise every
   test is a metric copy of his project.
3. **Where structures go.** Lumped reservoirs only for now, with a culvert or orifice through a 2D crest line later from
   the same functions?
4. **A dam point with no crest line.** Should a `dam` point demand a crest line of the job (the pool is then measured from
   the DEM, as now), or draw a short line across the valley at `crest_m` by itself?
5. **Culverts.** Keep them second, at 6 to 9 days, or let the orifice (1 day) and the dam top (1.5 days) go ahead of them,
   so low-level outlets run sooner?
6. **The chart.** Right-click plus the shared docked panel, as recommended? And his own chart layout, if he has one to show.
7. **The per-period chart.** Keep the inflow-outflow chart to its two flows, or add the pool level on a second axis?

## Sources

HEC-HMS 4.12 User's Manual:
[Outflow Structures Routing](https://www.hec.usace.army.mil/confluence/cwmsdocs/hmsum/4.12/outflow-structures-routing-146343405.html),
[Outflow Curve Routing](https://www.hec.usace.army.mil/confluence/hmsdocs/hmsum/4.12/reservoir-elements/outflow-curve-routing),
[Specified Release Routing](https://www.hec.usace.army.mil/confluence/hmsdocs/hmsum/4.12/reservoir-elements/specified-release-routing),
[Diversion](https://www.hec.usace.army.mil/confluence/hmsdocs/hmsum/4.12/source-junction-diversion-and-sink-elements/diversion),
[Source](https://www.hec.usace.army.mil/confluence/hmsdocs/hmsum/4.12/source-junction-diversion-and-sink-elements/source),
[GIS Menu](https://www.hec.usace.army.mil/confluence/hmsdocs/hmsum/4.12/geographic-information/gis-menu),
[Basin Characteristics](https://www.hec.usace.army.mil/confluence/hmsdocs/hmsum/4.12/geographic-information/basin-characteristics).

HEC-HMS Technical Reference Manual, Reservoir Modeling Concepts and Equations:
[the section page](https://www.hec.usace.army.mil/confluence/hmsdocs/hmstrm/reservoir-modeling/reservoir-modeling-concepts-and-equations),
[Outlets](https://www.hec.usace.army.mil/confluence/hmsdocs/hmstrm/reservoir-modeling/reservoir-modeling-concepts-and-equations/outlets),
[Spillways](https://www.hec.usace.army.mil/confluence/hmsdocs/hmstrm/reservoir-modeling/reservoir-modeling-concepts-and-equations/spillways),
[Dam Tops](https://www.hec.usace.army.mil/confluence/hmsdocs/hmstrm/reservoir-modeling/reservoir-modeling-concepts-and-equations/dam-tops),
[Pumps](https://www.hec.usace.army.mil/confluence/hmsdocs/hmstrm/reservoir-modeling/reservoir-modeling-concepts-and-equations/pumps),
[Dam Break](https://www.hec.usace.army.mil/confluence/hmsdocs/hmstrm/reservoir-modeling/reservoir-modeling-concepts-and-equations/dam-break),
[Dam Seepage](https://www.hec.usace.army.mil/confluence/hmsdocs/hmstrm/reservoir-modeling/reservoir-modeling-concepts-and-equations/dam-seepage),
[Evaporation](https://www.hec.usace.army.mil/confluence/hmsdocs/hmstrm/reservoir-modeling/reservoir-modeling-concepts-and-equations/evaporation).

Not read for this note: the Rule-Based Operations pages, HEC-RAS TRM chapter 6 on culverts, and the HDS-5 tables. Each is
read before its item is built.
