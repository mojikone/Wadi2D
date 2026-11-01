# HEC-HMS replication, held-out projects

The lumped engine's rules were found on Block 2 alone (`hms_replication.md`, 520 peaks within 0.002 %). This reruns
every depth-area analysis of three other HMS 4.12 projects from their files and compares each peak with
`results\DAA_*.results`. Error = (Wadi2D / HMS - 1) x 100. Reproduce with `heldout_replication.py` (about 20 s on 14
processes); `tests/hydrology/test_heldout_replication.py` keeps a sample from regressing.

**Bottom line.** On first contact Block 4 and Block 6 failed, by up to 6.6 % and 3.9 %: 126 peaks beyond 1 %, 25 beyond
2 %. One Block 2 blind spot caused all of them. After correcting it, no peak of 26,369 is beyond 0.12 %.

**These final numbers are not held-out in the strict sense.** The sub-step rule was corrected by reading the logs of
these same projects. It was read from logged `Delta t` and `Delta x`, inputs to the method and not peaks, and nothing
was fitted to a peak, but the only strictly held-out figures are the first-contact ones below. There is no independent
project on this machine to settle it: the other computed copies (Block 6 `63`, `63 old`, the Majlas and Block 4 `Claude`
folders) carry identical reach parameters, reproduce the same errors, and prove nothing further.

## Results

| Project | Analyses | Point-peaks | Worst error % | At | Beyond 1 % | Beyond 2 % | Peak one step off |
|---|---|---|---|---|---|---|---|
| Block 4 | 78 | 16,341 | -0.008 | SHA-R32, DA 2yr B2 | 0 | 0 | 2 |
| Block 6 | 28 | 8,182 | +0.117 | ful-J6, DA 1000yr 1D DAM - All | 0 | 0 | 4 |
| Majlas | 39 | 1,846 | -0.002 | O1, DA PMP Res2 | 0 | 0 | 0 |

First contact, with the sub-step rule as documented and one trapezoid per reservoir step:

| Project | Point-peaks | Worst error % | At | Beyond 1 % | Beyond 2 % | Time error of the peak |
|---|---|---|---|---|---|---|
| Block 4 | 16,341 | +6.597 | HAW-J21, DA 2yr B3 | 23 | 14 | 120 points, up to 15 steps |
| Block 6 | 8,182 | +3.893 | R106, DA 5yr 1D DAM - All | 103 | 11 | 483 points, up to 24 steps |
| Majlas | 1,846 | +0.016 | Rdn1, DA PMP Res | 0 | 0 | 0 |

Reservoirs at their own analysis point: Block 4, 325 peaks, worst 0.005 %, Modified Puls. Majlas, 26 peaks, worst
0.002 %, one spillway. Peaks of exactly zero, a dam that does not spill, compare as equal: 349, 61 and 28 of them.

Left out, each with its reason in `Replication`:

- **Block 6, `DA PMP Basin DAMs`**: no results file, only an `.h5`.
- **Majlas, point S1 in 26 analyses** (`Dams`, `Res`): the `.nals` holds a point the results do not.

Not left out, and looked at: Block 6's `Basin DAMs` and Majlas's `Basin 1 Res` carry elements stamped after their
results were computed. Their peaks agree to 0.001 % and 0.002 %, so the edits did not change them.

## The Block 2 rules: which held

| Rule found on Block 2 | Verdict | Evidence |
|---|---|---|
| Cells N = ceil(L / (c dt)) | **Held** | 8,363 of 8,390 logged reach runs; the rest are one reach, below |
| Sub-steps of a short reach | **Failed** | This was the documented rule, never exercised: no Block 2 reach is short enough. Replaced, below |
| Negative new-inflow weight split evenly | Held | Block 4 worst 0.008 %, on the 2 yr reaches where it acts most |
| Low-flow rule, 0.01 m3/s | Held | The same reaches |
| Stencil and tolerance 1e-3 | Held | The same reaches |
| SCS cubic-spline unit hydrograph | Held | Every subbasin at its own point |
| ARF table, linear in area | Held | The small end needed a correction, below |
| Grid depth, unweighted cell centres | Held | All 168 subbasins logged, within the 0.0005 mm of the log |
| One upstream set for water and for storm area | **Failed** | With branches they differ, below |

The three rules named as suspect (the C2 split, the low-flow rule, the spline) all held. What failed was a rule nobody
suspected, because Block 2 never reached it. That is a warning about the 0.002 % of Block 2: it measured the code
paths Block 2 uses.

## What changed

**Sub-steps of a reach** (`routing.py`). After N cells, the control step is rounded to the nearest divisor of a cell's
travel time: k = round(N c dt / L), at least 1. The documented rule split the step whenever a wave crossed the reach in
less than a step, with ceil. Read off 258 distinct reaches, L / (c dt) from 0.02 to 39. It explains every transition:
dt halves for ratios 1.02 to 1.26 and returns at 1.3345, the predicted 4/3. A short reach run at the wrong step is why
the peaks came out 2 to 4 % high and early. Block 2 is unaffected: its report is byte-identical.

**Storm area and branches** (`model.py`). HMS computes everything that sends water to a point, diversions and
auxiliary outlets included, but its storm area counts only `Downstream` links. All 417 points of Block 6 agree: J93 lists
27 elements and a storm area of 2.753 km2, not 270. Sinks are junctions at an outlet.

**ARF below the table** (`arf.py`). HMS logs `No area reduction performed` below the smallest area, so the factor is 1,
not the first row's 0.999. HMS tables opt into this; `ArfTable` otherwise keeps its end-hold, which `tests/storm` pins.
Above the largest area stays unverified: no project reaches it.

**Results names** (`replication.py`). HMS replaces every non-alphanumeric character, so the hyphen in
`DA 10yr 1D DAM - All` becomes `_`. Most of Block 6's "missing" results were this: 13 of the 14 analyses reported
missing exist, and only one is truly absent.

## Corrected premises

- **Majlas was not a catchment smaller than a cell.** No subbasin in any project holds zero cell centres. Its PMP raster
  is EPSG:4326 under UTM polygons, so no centre fell in any polygon. Cell centres are now moved to the basin's system.
  Neither area weighting nor the nearest cell is implemented: there is no evidence for either, so that case raises.
- **`Uniform Depth: No` is read now.** It was ignored: each subbasin takes the mean over its own polygon, not the mean
  above the point. Block 6 and Majlas PMP use it; Block 2 and Block 4 do not.

## Reservoirs (`reservoir.py`)

Storage is conic, S(z), A(z) and Q(z) linear between rows of the primary table, agreeing with Block 4's series to 1e-11.

- **Modified Puls, Elevation-Area-Outflow** (Block 4): the storage-indication step of the technical reference. With HMS's
  inflow it reproduces Hawasinah 02 at 100 yr to 8e-12 m3/s. Fully replicated.
- **Controlled Outflow, broad-crested spillways** (Block 6, Majlas): Q = C L H^1.5 exactly, main and auxiliary on the
  same pool, implicit trapezoid per step. **Adaptive Control** is undocumented; measured: a step moving the pool more than
  0.1 m is cut in two, inflow held at the mean of the control step. Exact to 2e-11 m up to 0.2 m.
- **Not identified**: HMS's deeper splits. On the Majlas PMP one step matches the partition 1/8 1/8 1/4 1/2, which a plain
  0.1 m test does not produce. Bisecting by the same test is the closest form found. Against HMS's inflows it brings the
  worst reservoir peak from 0.33 % to 0.03 %, and the mean from 0.036 % to 0.004 %. Series can still differ by up to
  8.4 m3/s. This is the larger remaining error: Block 6's worst, 0.117 % at ful-J6, is in the model with dams and does
  not move when R20 is corrected.

**Known exception**: Block 6's reach R20 (L / (c dt) = 0.94) logs N = 2, k = 2 where the rule gives 1 and 1, in all 27
logs that hold it. Its output confirms the logged grid, to 0.003 m3/s. Nothing in its inputs separates it from R40 at
0.93 or SAK-R18 at 0.97. It is left unexplained, not special-cased: 0.035 % on its own peak at 1000 yr, up to 0.09 %
downstream of it. Given its logged grid in a scratch run, every Block 6 model without dams falls from 0.094 % to
0.0015 %. So R20 is all of the error of those models, and every other reach rule is right to 0.0015 % there.

## What raises instead of guessing

Leaves the analysis out with its reason: a pool above the top of its table; an inflow above a diversion table; a polygon
holding no cell centre; tailwater; evaporation other than zero; conduits, pumps, ogee spillways; `Adaptive Control` other
than `On`; storage methods and curves other than the two above; a network table in units other than m, m2, m3/s; a
results file that does not exist.

Not used by any of these projects, so unmeasured: every one of those, plus the auxiliary outlet at flows where it is
not symmetric with the main one, since Al Ais 10 is the only case.
