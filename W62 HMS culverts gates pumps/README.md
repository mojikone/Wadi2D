# W62 HMS culverts, gates and pumps: the second slice of reservoir structures, raced against HEC-HMS 4.12

**Status: built on branch `feature/hms-structures-b` off `feature/fast-products` (`5d6ced2`), not merged, nothing
pushed. Live iteration for HMS reservoir structures after W59 (which stays as it is: its numbers still hold). Lumped
reservoirs only, metric only. Built: the job calendar, gates, pumps. Not built: culverts.**

The uncomfortable findings first.

- [Certain] **HMS's own books do not close while a pump is off and the pool stands above its intake.** In every such
  run HMS's storage grows by 59/60 of the step's net inflow: one sixtieth of each step, 19,000 to 36,000 m3 per run
  (0.15 to 0.28 % of the inflow), goes nowhere: not to the pump (0 m3/s reported), not to the outflow. The ratio is
  1/59 of the storage change to six digits in two table rows (11,006 and 12,702 m3 per metre against the conic
  649,358 and 749,444). HMS logs a 5 s minimum time step in those runs: [Likely] it sub-steps in 60 parts while a pump
  is armed and drops one. Ours closes, so on those runs the pool parts from HMS's by up to 3.6 cm and a switch-off
  lands one step later. The pump is therefore tested against HMS on HMS's own levels (exact) and routed only on a
  case where the pool is never armed (`pump_closed`, within W59's flow tolerance).
- [Certain] **Culverts are not built.** The reader refuses a `Conduit: Culvert` by name, as before. Section "Not done".
- **The gates route to 4.1e-4 of the peak at the worst step, against W59's 3e-4**, every law exact at HMS's own
  levels. HMS takes 7 s steps near a gate's change of regime that the 0.1 m bisection does not ask for; bisecting
  every step that crosses the regime boundary brought two cases nearer (0.8e-4, 1.5e-4) and the third further
  (5.4e-4), so it is not HMS's rule and is not in the engine (`scripts/probe_gate_kink.py`). The test holds 5e-4.

## What is built

| Piece | Where | Law, as measured on HMS's own output |
|---|---|---|
| Job calendar | `run.py` (`run_calendar`) | `storm.rain_start` dates the lumped network's first step, and `basin_from_hms` passes it to every reservoir, so monthly evaporation routes in a job. With no date a reservoir with evaporation refuses, naming `storm.rain_start`. A gridded or gauge storm with no `rain_start` still gives the lumped network no date (its own start is found later, in the forcing) |
| Gated broad-crested spillway | `structures.py` `SpillwayGate`, `structure_kernel.py` `_gate` | Per gate group (n gates of width W): weir flow Cs (nW) H^1.5 at the **spillway's** coefficient while H <= B (H over the crest, B the opening); the gate law from H >= 1.25 B; **linear in H/B between** [Certain: 1e-12 at HMS's levels]. Sluice C (nW) B k H^0.5; radial C k (nW) T^TE B^BE H^HE; **k = 4.42869**, a literal in HMS (its flows over the law read 4.42869 to the last digit; sqrt(2 x 9.80665) = 4.4286906) |
| Pump | `structures.py` `Pump`, `structure_kernel.py` `_switch_pumps` | While on: units x table(discharge elevation - pool + equipment loss) [Certain: 0 difference at every step of nine cases]. A fixed tailwater under the intake changes nothing [Certain, `pump` against `pump_tw`, identical]. On when the pool at a step part's start is at the switch-on level **less half a millimetre** and the pump has rested; off below the switch-off level once it has run, below the intake at once. **Run and rest times are minutes** [Certain: 40 and 15 changed nothing; 2000 held the pump on to the step where 2000 min ran out; 900 kept it off to the end]. The trapezoid of the step where it switches uses the new state at both ends [Likely: HMS's books at a switch-on step are short by half the new pump flow over the step, while it reports 0 at the step's start] |
| State per structure | `structure_kernel.route_structures` | The kernel carries each structure's state (a pump's on or off, since when) and returns it per step, so `flows_at` reports each structure's flow with its state; `series/network_<reservoir>.csv` gains `gate_<n>_m3s` and `pump_<n>_m3s` by the W59 rule |
| Parameter slots | `structures.pack_all` | A packed structure carries up to 8 numbers (was 3), padded with zeros; W59's kinds read the same first three |

Refused by name (rule not identified, or HMS refuses it): a gate control other than Fixed Opening (Percent Pattern,
Percent Gage; "Percent Pattern" is a paired-data type in `hms.jar`, its axis not established); gates whose widths do
not add up to the crest length (HMS's error 42204); a tailwater reaching the crest of a gated spillway (W59's
drowned-weir refusal, since the crest attribute is the spillway's); a pump whose intake, switch-off and switch-on do
not rise in that order (HMS's error 42585 for switch-off under the intake); a fixed tailwater at or above a pump's
intake; a pump run at a head outside its table; any key of a gate, gate control or pump block not listed below.

Old jobs: W59's tests pass unchanged (broad-crested alone still to the same bits on both kernels), `tests/hms` and
`tests/hydrology` pass. A broad-crested spillway that carries gates was read before as an ungated one, the gates
ignored; it is now read with them.

## The basin-file keys, and how they were established

As W59: written into a test basin, **re-saved by HEC-HMS 4.12** (`SaveBasinModelAs`), every key written back. The
candidates came from `hms.jar` (`scripts/jar_strings.py`) and HMS's `river_bend` sample (`scripts/sample_blocks.py`).
The re-saved basins are the test data.

| Block | Keys |
|---|---|
| `Spillway: Broad-Crested Spillway` carrying gates | `Spillway Outlet`, `Spillway Crest Length`, `Spillway Crest Elevation`, `Spillway Coefficient`, then one sub-block per gate group |
| `Spillway Gate: Sluice` (closed by `End Gate:`) | `Number Gates`, `Gate Width`, `Gate Coefficient`, `Orifice Coefficient` (the drowned regime's, not used) |
| `Spillway Gate: Radial` | the sluice's, plus `Trunnion Height`, `Trunnion Exponent`, `Opening Exponent`, `Head Exponent` |
| `Gate Control: Fixed Opening` (inside the gate) | `Gate Opening` |
| `Pump: Head-Discharge Pump` | `Pump Outlet`, `Number Of Pumps`, `Intake Elevation`, `Discharge Elevation`, `Switch-On Elevation`, `Switch-Off Elevation`, `Minimum Run Time`, `Minimum Rest Time` (blank is none), `Head-Discharge Table Name` (a `Stage-Flow` table of head against flow), `Equipment Head Loss` |

HMS reorders the gate's keys on re-save (the control first). Seen and not read: `Gate Control: Percent Pattern` with
`Maximum Gate Opening`, `Percent Pattern Name`; `Percent Gage Name`; `Orifice Gate`; the culvert's `Culvert Shape`,
`Solution Control`, `Chart Number`, `Scale Number`, `Rise`, `Span`, `Culvert Length`, `Entrance Loss Coefficient`,
`Exit Loss Coefficient`, `Top Manning's n`, `Inlet Invert Elevation`, `Outlet Invert Elevation` (from `river_bend`;
`DIAMETER` and `BOTTOM_MANNINGS_N` are in the class, their file keys not seen).

## The race against HEC-HMS 4.12

W59's project and method unchanged (`scripts/hms_cases.py` adds the cases to W59's `hms_project.py`): a 400 m3/s
flood into a 100 to 125 m pool from 103 m, 48 h at 5 min, Adaptive Control On, HMS headless (`scripts/run_hms.ps1`),
each case in its own `try` so one refusal does not stop the rest. `scripts/export_cases.py` writes the oracle into
`tests/data/hms_structures/`; `scripts/compare.py` writes `results/compare.json`.

| Case | HMS peak outflow, m3/s | max abs outflow difference, of peak | peak | pool, m | HMS unbooked, m3 |
|---|---|---|---|---|---|
| sluice, 2 x 10 m, open 1.5 m | 140.69 | 1.4e-4 | -7.2e-6 | 1.2e-4 | +171 |
| radial, the same, T 3 m, exponents 0.16, 0.72, 0.62 | 179.31 | 4.1e-4 | -2.3e-5 | 3.0e-4 | +348 |
| both groups on a 40 m crest | 256.37 | 1.1e-4 | +6.2e-6 | 7.1e-5 | +59 |
| pump, intake = off = on, 2 units (books close) | 146.23 | 2.2e-4 | -1.1e-4 | 1.2e-3 | -983 |
| pump, 2 units, armed 103.5 to 106.5 m | 145.82 | 5.4e-3 | +2.7e-3 | 3.6e-2 | -27,734 |
| pump, 10 units cycling (and the run, rest, intake, band cases) | 162.51 | 0.40 at a switch step | +1.7e-3 | 1.9e-2 | -19,196 to -35,784 |

On HMS's own pool levels the pump's state machine gives HMS's on and off at every step of all nine pump cases,
except one step in `pump` that HMS cut in two (0.121 m of pool change), where it switched at the second part's start.
`pump_closed`'s pool difference equals HMS's 983 m3 unbooked over the pool area (1.16 mm against 1.20).

## Not done

- **Culverts** (box and circular first): not started. W58 section 2.2 holds why it is large: FHWA HDS-5 inlet control
  per chart and scale, outlet control with a part-full barrel, HMS's own iteration. Refused by name.
- Gate controls other than Fixed Opening; drowned gates (any tailwater at the crest); HMS's sub-stepping near a gate's
  kink and while a pump is armed.
- A pump with a tailwater at or above its intake; an initial pump state from a basin state file (`Pump State`,
  `State Change Time` are in `hms.jar`).
- The dock: no change; the HMS route reads these structures from the file as it is. Not run through the real dock.
- `storm.rain_start`'s description in the schema still speaks of the rain only (the plugin's schema sample carries
  the text); the job calendar for a gridded or gauge storm without `rain_start`.

## Files

- `scripts/hms_cases.py` (the cases), `run_hms.ps1` (W55's), `export_cases.py`, `compare.py`, the probes
  `fit_gates.py`, `probe_gate_kink.py`, `probe_pumps.py`, and `jar_strings.py`, `sample_blocks.py` for the keys.
  `_work/` holds the HMS projects and is not committed.
- Tests: `tests/hydrology/test_hms_gates_pumps.py`; the calendar's in `tests/hydrology/test_hms_structures.py`.
