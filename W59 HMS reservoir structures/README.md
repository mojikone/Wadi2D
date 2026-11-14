# W59 HMS reservoir structures: the first slice, built and raced against HEC-HMS 4.12

**Status: built on branch `feature/hms-structures` off `feature/fast-products` (`c7c08e3`), not merged, nothing pushed.
This is the live iteration for HMS reservoir structures; W58 is the design note it follows (items 0, 1, 3, 4, 7, 8 of
its section 2, in part). Lumped reservoirs only, metric only.**

The uncomfortable finding first. [Certain] **HMS's drowned weir is a curve, not the "smaller of two heads" its manual
describes**, and it was not identified here: with a fixed tailwater above a level dam top, HMS passes 0.93 of free flow
at a submergence of 0.90, 0.67 at 0.966 and 0.0075 at 0.9999, which neither Villemonte nor "head to the tailwater"
reproduce (`scripts/damtop_tw.py`). So a reservoir whose fixed tailwater reaches any weir crest on the main outlet is
**refused by name**, and the same holds for broad-crested spillways, whose manual page says the same thing.

## What is built

| Piece | Where | Law, as measured on HMS's own output |
|---|---|---|
| One structure interface | `wadi2d/hydrology/structures.py` | Each structure packs itself (kind, outlet, three numbers, a table); a registry `STRUCTURE_KINDS` by HMS name |
| One compiled kernel | `wadi2d/hydrology/structure_kernel.py` | The W55 implicit trapezoid and adaptive bisection, summing every structure and the evaporation |
| Rating-curve spillway | same | The elevation-discharge table at the pool, linear between rows; no tailwater acts on it [Certain, `level_dam_tw` with a tailwater above half the table] |
| Orifice | same | Q = n K A sqrt(2 g H), H from the higher of the centreline and the tailwater, **g = 9.80665** [Certain: 0 difference at every step; 9.81 is 4e-3 m3/s off] |
| Level dam top | same | Q = C L H^1.5 over the crest; drowned flow refused (above) |
| Tabular seepage | same | The pool-to-tailwater table at pool - tailwater, with no tailwater at pool - bottom of the storage table [Likely, one table bottom tested]; extended below 0 along its first segment, so a tailwater above the pool gives negative seepage on the main outlet [Certain]. The tailwater-to-pool table changed nothing in any run, a tailwater above the pool included [Certain on these runs] |
| Monthly evaporation | same | Each month's depth spread evenly over its days, **February 28 days in the leap year 2000 too** [Certain: 16.071429 mm/day = 450/28], by the month a control step starts in, times the pool area (the step's mean area in the books); lost, not sent to an outlet |
| Fixed-stage main tailwater | `reservoir.py` | Enters the orifice and the seepage; the auxiliary outlet takes none |
| Elevation-storage storage method | `reservoir.py`, `from_hms.py` | Storage linear between rows; HMS takes the table in `THOU M3` and refuses `1000 M3` |
| Pool, storage and each structure's flow written | `engine/network_series.py`, `engine/handback.py` | `series/network_<reservoir>.csv` gains `pool_m`, `storage_m3` (both reservoir methods) and, with structures, `<kind>_<n>_m3s` and `evaporation_m3s`; the flow columns are unchanged |
| HMS basin reader | `from_hms.py`, `hms/methods.py`, `hms/text.py` | The keys below; any other key in a structure block raises by name |

Old jobs: a reservoir of broad-crested spillways alone, with none of the rest, still routes on the untouched
`route_spillways`; a test shows the new kernel gives the same bits on it, one and two outlets. Block 2's five
reservoirs (W55, to 1e-6) and the replication pass.

## The basin-file keys, and how they were established

Each key below was written by me into a test basin, and **HEC-HMS 4.12 opened it and wrote it back** on
`SaveBasinModelAs` (a Jython API call, found by listing `hms.model.JythonHms`'s methods). A key HMS does not read is
dropped and warned on re-save ("Draw Icons By Default" was, as a control). The candidates came from the string
constants of `hms.jar` (`hms/model/basin/hydraulics/*.class`, the enum of structure names in `aq.class`).

| Block | Keys |
|---|---|
| `Spillway: Rating Curve Spillway` | `Spillway Outlet`, `Spillway Rating Curve Name` (a `Stage-Flow` paired table) |
| `Conduit: Orifice` | `Conduit Outlet`, `Number Barrels`, `Centerline Elevation`, `Orifice Area`, `Orifice Coefficient` |
| `Dam Top: Level Dam` | `Dam Top Outlet`, `Top Elevation`, `Top Length`, `Overflow Coefficient` |
| `Dam Seepage: Tabular Dam Seepage` | `Dam Seepage Outlet`, `Pool-To-Tailwater Table Name`, `Tailwater-To-Pool Table Name` |
| `Evaporation Method: Monthly Evaporation` | `Evaporation Rate`, twelve lines, January first, mm |
| Route | `Main Tailwater Condition: Fixed Stage`, `Main Fixed Tailwater Stage`; `Routing Curve: Elevation-Storage`, `Elevation-Storage Table` |
| `Source` (test inflow only) | `Flow Method: GAGE_FLOW`, `Flow Gage`; HMS refuses `Discharge Gage` there |

Not established, so not read: the non-level dam top (`Top Cross-Section` names a cross-section table whose
paired-data type HMS's `.pdata` did not keep: the `Cross Section` type I wrote was dropped on re-save), the auxiliary
fixed stage, and every other tailwater kind (rating, specified stage, downstream). Each still raises.

## The race against HEC-HMS 4.12

Method, W55's: a metric test project written from scratch (`scripts/hms_project.py`), one basin per case (Source with
a discharge gage, one reservoir, a Sink), a 48 h window from 31 January 2000 12:00 at 5 min crossing the month
boundary, a 400 m3/s peak at 6 h, a pool of 100 to 125 m and 0.2 to 2.7 km2, Adaptive Control On, start 103 m.
HMS ran headless (`scripts/run_hms.ps1`, a copy of W55's), its series went to CSV (`scripts/export_hms.py`) as the
test oracle in `tests/data/hms_structures/` together with the basin files HMS re-saved. Wadi2D's reader builds each
reservoir from that file and routes HMS's own inflow of record. Tolerances in the test are the floor of the existing
broad-crested path (reservoir.py: HMS's adaptive splits past 0.2 m are not identified, 0.03 % of peak).

| Case | HMS peak outflow, m3/s | max abs outflow difference, of peak | peak | pool, m | storage, of max |
|---|---|---|---|---|---|
| broad (the W55 path, control) | 242.59 | 1.3e-5 | -3.1e-6 | 2.4e-5 | 3.6e-6 |
| rating | 140.44 | 1.5e-7 | +2.1e-8 | 6.0e-7 | 6.7e-8 |
| orifice + broad | 236.35 | 2.5e-5 | -7.5e-6 | 4.3e-5 | 6.8e-6 |
| orifice + broad, tailwater 103 m | 239.89 | 2.0e-5 | -3.1e-6 | 4.3e-5 | 3.6e-6 |
| rating + level dam top | 238.38 | 9.5e-5 | -2.2e-5 | 9.4e-5 | 1.5e-5 |
| rating + seepage | 141.15 | 2.1e-7 | +1.3e-7 | 7.8e-7 | 8.8e-8 |
| rating + seepage, tailwater 103 m | 140.94 | 2.3e-6 | +1.1e-6 | 1.9e-5 | 1.2e-6 |
| rating + seepage, tailwater 105 m (above the pool) | 140.82 | 1.5e-7 | +5.4e-9 | 7.5e-7 | 8.3e-8 |
| rating, elevation-storage table | 140.44 | 1.5e-7 | +2.1e-8 | 6.0e-7 | 6.7e-8 |
| all: orifice, rating, dam top, seepage, tailwater 103 m, monthly evaporation | 229.71 | 2.1e-5 | +3.0e-6 | 4.2e-5 | 3.4e-6 |
| rating + monthly evaporation | 139.84 | 7.3e-3 | +3.6e-3 | 4.2e-2 | 3.9e-3 |

Each law alone, at HMS's own pool levels, gives HMS's own structure flow to 1e-9 (orifice under tailwater, dam top,
negative seepage, rating). Evaporation volume: all case -4.6e-4, evaporation case +1.4e-5 of HMS's.

**The last row is HMS's, not ours.** [Certain] In that case HMS's storage falls 33,100 m3 (0.25 % of the inflow)
more than inflow, outflow and its own reported evaporation account for, almost all of it while the pool is below the
rating's first flow; 1,589 m3 go in the one step where the pool crosses it. Ours closes. In the `all` case, where an
orifice always flows, HMS's books close (2 m3 over the run) and the two agree to 2e-5 of the peak. Not chased
further; the test records both books.

Also seen in HMS's log: "Pool storage is below the lowest value in elevation-storage table" 428 times in each
seepage run whose pool never went below 103 m; [Likely] trial levels of HMS's own iteration. And "minimum time step of
2 seconds": HMS bisects deeper than 0.1 m of pool change would ask on these inflows.

## Not done

- **Culverts, gates, pumps, ogee, specified spillway, non-level dam top, dam break, additional release** (W58 items 2,
  5, 6, 9, 10, 12): not started.
- **Drowned weirs**: refused, the HMS curve not identified (above). Tailwater kinds other than Fixed Stage: refused.
- **Monthly evaporation in a job**: the job has no calendar, so a reservoir with it refuses to route ("needs the run's
  start date"); `basin_from_hms(..., start=)` and `reservoir_from_hms` take one. The job's start date is W58's
  calendar item, not built.
- **The dock**: no change. Structures in the HMS file are read by the HMS route as they are, with nothing to select;
  not run through the real dock.
- **The Source element** in the engine: not built (the test inflow is HMS's own FLOW-COMBINE).
- A `Spillway crest` dam start on a reservoir with no broad-crested spillway now refuses in words, where it failed on
  an empty `min()`.
- A tokenizer fix rides with this: `End Evaporation:` closed the last `Evaporation Rate:` line instead of
  `Evaporation Method:` (a loose prefix match took the nearest line), so a monthly evaporation block read as unknown
  keys. The prefix match now takes the farthest line back before an earlier sub-block; `tests/hms` passes.

## Files

- `scripts/hms_project.py` writes the test project to `_work/<folder>` (not committed) and the Jython script.
- `scripts/run_hms.ps1` runs it (W55's). `scripts/export_hms.py` writes the oracle. `scripts/compare.py` prints the
  table above to `results/compare.json`. `scripts/fit_*.py`, `damtop_tw.py`, `evap_rate.py`, `balance.py`,
  `consistency.py`, `where.py` are the probes behind each law.
- Tests: `tests/hydrology/test_hms_structures.py`; the reservoir refusal test was moved from "Elevation-Storage is
  refused" to "Storage-Discharge is refused" (`tests/hydrology/test_reservoir.py`).
