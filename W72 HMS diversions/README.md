# W72 HMS diversions: HEC-HMS 4.12's five diversion methods and two limits, raced against HMS headless

**Status: built on branch `feature/hms-diversions` off `feature/fast-products` (`3a4e2e9`), not merged, nothing
pushed. Lumped network only, metric only. Live iteration for diversions; W58 section 1.3 and 3 is the design note.**

The uncomfortable finding first. [Certain] **A pump station that its own draw switches off while the river still
stands over its switch-on level is not reproduced**: HMS then holds the pump at the switch-off level's head for one
or two steps by a rule not identified (`div_pump_cycle`), so that case raises in words rather than run something else.
And [Certain] **HMS's drowned lateral weir fails to converge at small flows on a steep tailwater rating**: on 35 of
577 steps its flow is not a root of its own law, and on 26 of them it returns 0 m3/s where the root is 1 to 2 m3/s (`div_weir_drowned`); ours returns the root,
so that run's diverted volume is 0.5 % above HMS's.

## What is built

| Piece | Where | Law, as measured on HMS's own output |
|---|---|---|
| Inflow Function | `wadi2d/hydrology/diversion.py` `InflowDiversion` | The table read linearly at the inflow. **An inflow above the last row: HMS refuses (ERROR 42824)** [Certain], so the existing raise stands |
| Constant Flow | `ConstantDiversion` | The rate, capped at the inflow (HMS WARNING 42803, "diversion flow set to inflow"). An annual pattern (`Pattern Name`) is refused by name: not measured |
| Specified Flow | `SpecifiedDiversion` | The flow gage's record at each ordinate, linear in time, capped at the inflow; an ordinate outside the record raises. Needs the run's start date (`storm.rain_start`) and the project's `.gage` file |
| Lateral Weir | `LateralWeirDiversion` | Q = C L H^1.5, **H = channel stage at the flow that stays in the channel** (solved with it each ordinate, not the stage of the inflow) [Certain: HMS's diverted flow is the law at its own passed flow to 3e-4 m3/s]. Drowned: W67's submergence table at s = (tailwater - crest) / H, the tailwater read off its rating at the diverted flow, none from s = 1 [Certain on 542 of 577 steps, to 1e-3] |
| Pump Station | `PumpStationDiversion` | Per unit, the head-discharge table at (discharge elevation + equipment loss - channel stage), the stage again at the passed flow. On when the stage of the whole inflow reaches the switch-on level, and **on that ordinate it pumps at the switch-on level's head** [Certain, 3 switch-ons]. Off, pumping nothing that ordinate, when its draw would pull the stage under the switch-off level and the whole inflow is under the switch-on level. Minimum run or rest time and a tailwater rating are refused by name: not measured |
| Limits, all methods | `DiversionLimits` | After the method and the inflow cap: maximum flow caps each ordinate; maximum volume, **held in the file in 1000 m3** [Certain: 2000 stops at 2.000 Mm3], counts each ordinate's flow times the step from the first ordinate, the ordinate that would pass it diverts the remainder over its step, none after |
| Divert To / Not Connected | `from_hms.py` | Divert To names the element that receives the diverted flow; with no `Divert To` line (HMS writes none for Not Connected) the water leaves the network on the diversion's `branched_m3s` |
| Reader | `from_hms.py` `_diversion`, `DIVERTER_BUILDERS`, `diversion_from_hms`, `load_flow_gages` | Any other key in a Diverter block, another diverter, a sub-block other than the station's pump: refused by name |
| Series | `engine/network_series.py`, `engine/handback.py` | `series/network_<diversion>.csv` gains `passed_m3s` and `diverted_m3s` (the same numbers as `outflow_m3s` and `branched_m3s`, which are unchanged) |
| Hand-back | `hydrology/live_network.py` | The diverted flow already runs through a live route as any second outlet does (W25). A Specified Flow diversion on a live route is refused at planning: the drain after the run would read past the gage's record |

Old jobs: the inflow-function diversion now caps its diverted flow at the inflow, which changes nothing where the
table never exceeds it. Replication, network, live-network, hand-back and `tests/hms` pass (below).

## The basin-file keys, and how they were established

As W59: written by me into a test basin, opened by HEC-HMS 4.12 and written back on `SaveBasinModelAs`. The candidates
came from the string constants of `hms.jar` (`hms/model/basin/e/*.class`; the internal names in `e/c.class`, the
display names in `BasinInterfaceResources.properties`).

| Diverter (HMS's internal name; display name) | Keys |
|---|---|
| `Inflow-Diversion Table` (Inflow Function) | `Inflow Diversion Table Name` (an `Inflow-Diversion` paired table, M3/S both) |
| `Constant` (Constant Flow) | `Constant Flow` |
| `Specified` (Specified Flow) | `Flow Gage` |
| `Lateral Weir` | `Weir Coefficient`, `Weir Elevation`, `Weir Length`, `Diverter Rating Table Name`, `Tailwater Rating Table Name` (both `Stage-Flow`, stage on x) |
| `Pump` (Pump Station) | `Diverter Rating Table Name`, `Tailwater Rating Table Name` (HMS writes it blank), and one `Pump: Head-Discharge Pump` sub-block with the reservoir pump's keys; HMS adds `Pump Outlet: Auxiliary` |
| Every method | `Maximum Diversion Flow`, `Maximum Diversion Volume`, written before the method's own keys |

Results in the run DSS: `//Diversion/FLOW/` (passed), `FLOW-DIVERSION` (diverted), `FLOW-COMBINE` (inflow).

## The race against HEC-HMS 4.12

Method, W59's: its metric test project (`W59 .../scripts/hms_project.py`) with W72's basins (`scripts/w72_cases.py`):
Source with W59's 400 m3/s gage hydrograph, a Diversion, a Sink for the main channel and one for the diverted flow,
48 h at 5 min. HMS ran headless (W59's `run_hms.ps1`), re-saving each basin first; `scripts/export_cases.py` wrote its
series and re-saved basins to `tests/data/hms_diversions/`. Wadi2D reads each re-saved basin and routes HMS's own
inflow. Tolerances in the test, fixed before the comparison: 1e-12 of the peak for the closed-form methods, 1e-5 for
the solved ones (HMS's own solve sits within 3e-4 m3/s).

| Case | HMS peak diverted, m3/s | max abs difference, m3/s | of peak | diverted volume, Mm3 (HMS, ours) |
|---|---|---|---|---|
| inflow function (table to 500 m3/s) | 150.00 | 0 | 0 | 5.0186, 5.0186 |
| constant 50 m3/s | 50.00 | 0 | 0 | 4.4503, 4.4503 |
| specified (gage up to 150 m3/s, above the inflow early) | 149.99 | 0 | 0 | 7.5437, 7.5437 |
| inflow function, maximum flow 60 | 60.00 | 0 | 0 | 2.8218, 2.8218 |
| constant 50, maximum volume 2000 (thousand m3) | 50.00 | 2.7e-15 | 5e-17 | 2.0000, 2.0000 |
| inflow function, not connected | 150.00 | 0 | 0 | 5.0186, 5.0186 |
| lateral weir 20 m, C 1.6, crest 103 m | 113.74 | 1.7e-4 | 1.5e-6 | 2.2196, 2.2196 |
| lateral weir, tailwater rating (submergence under 0.39) | 113.74 | 1.7e-4 | 1.5e-6 | 2.2196, 2.2196 |
| pump station, 2 units, on 103, off 102 | 47.04 | 2.0e-5 | 4.2e-7 | 2.1783, 2.1783 |
| lateral weir drowned (s to 0.997) | 95.97 | 2.18 (HMS's 0s) | 2.3e-2 | 1.6796, 1.6875 |
| pump station cycling, on 104, off 103.6 | refused | | | |

An inflow-function table ending at 300 m3/s under a 400 m3/s inflow: HMS aborts the run (ERROR 42824, WARNING 12465).

## Not done

- Constant Flow's annual pattern, a pump station's minimum run and rest times and its tailwater rating, and the
  chattering pump station: refused by name, not measured.
- A Specified Flow diversion on a hand-back's live route: refused; on the lumped network alone it routes.
- Not run through the real dock, and no dock control for diversions (W58 section 4's diversion point is not built);
  an HMS basin carrying a diversion is read by the HMS route as it is.
- No diversion in a generated basin (`basin.json`).
- Performance: the weir and the pump solve each ordinate in Python (about 0.1 s for 577 ordinates); a live route
  reruns the series every hand-back step, so a long run with a weir on a live route will be slow. Not measured.

## Files

- `scripts/w72_cases.py` writes the HMS project to `_work/<folder>` (not committed) and the Jython script for W59's
  `run_hms.ps1`; `scripts/export_cases.py` writes the oracle; `scripts/probe_laws.py` reads the weir and pump laws off
  HMS's own series.
- Tests: `tests/hydrology/test_hms_diversions.py`.
