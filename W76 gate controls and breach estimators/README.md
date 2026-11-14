# W76 gate controls and breach estimators

**Status: built on branch `feature/gates-estimators` off `feature/fast-products` (`1ace4e8`), not merged, nothing pushed.
Live iteration for HMS gate controls and drowned gates after W62 (which stays as it is: its numbers still hold), and for
the 2D breach's estimators after W63. Lumped reservoirs only, metric only.**

The uncomfortable findings first.

- [Certain] **HMS's drowned gate passes more water than the free gate at the same pool.** Once the pool stands more than
  1.25 openings over the tailwater, HMS computes the gate law on the head over the tailwater times sqrt(3); the gate
  coefficient is the free one and the Orifice Coefficient changes nothing. A sluice at 1.5 m with a tailwater 0.6 m
  over the crest peaks at 195.2 m3/s where the same gate with no tailwater peaks at 140.7 (`gate_sluice_tw_low`
  against W62's `gate_sluice`). Wadi2D carries HMS's rule, so it reproduces HMS and not a hand calculation; whoever
  designs a gated dam under a high tailwater with either tool should know it.
- [Certain] **HMS's books lose a sixtieth of each step's net inflow while its pool stands between the crest and the
  tailwater** (8,000 to 43,000 m3 on these runs; storage change 59/60 of the net inflow at every such step), the defect
  W62 and W67 found. Ours close, so the drowned runs route to within 3.4 cm of HMS's pool and 6e-3 of its peak, and
  their law is tested on HMS's own pool levels, where it is exact.
- **Percent Annual Pattern is refused**: its keys are proven by HMS's re-save, but on a guessed pattern record (a
  `Pattern:` block, data type `Percent Pattern`, an IR-YEAR record of 25 to 100 % in the year 2000) HMS ran and held the
  gate at 75.07 % through the whole window; how HMS reads a pattern is not identified (`gate_annual_sluice` kept as
  the record). **Adjustable Gate Control is refused**: it is driven by HMS's rule-based reservoir operations
  (`Gate Priority`, `Minimum Time Between Adjustments`), which are not built.

## Gates: what is built

| Piece | Where | Law, as measured on HMS's output at HMS's own pool levels |
|---|---|---|
| Percent Time Series | `from_hms._gate_opening`, `structures.SpillwayGate` (`maximum_opening_m`, `schedule_minutes`, `schedule_percent`, `openings_at`) | Opening = Maximum Gate Opening x percent / 100, the percent **linear in the gage at the time itself** (candidates of the step before, the hour before and after are 6e-2 to 0.6 of the peak off; the time itself 4e-16). The gage is a `Percent` gage in `%`, INST-VAL, read like W72's flow gages; its times become minutes from the run's start, so it needs `storm.rain_start` |
| The opening in the step | `structure_kernel.route_structures` (`schedule`) | Each structure's opening at each inflow time, NaN for a fixed one; a bisected part's end takes it linearly between its step's two times, the start of a part keeps the previous end's |
| Drowned gate | `structure_kernel._gate` | With a fixed tailwater over the crest, r = (pool - tailwater) / B: up to 1 the free law (W62) times W67's submergence share at s = (tailwater - crest) / (pool - crest); from 1.25 **sqrt(3) x the gate law on pool - tailwater** (sluice and radial, gate coefficients 0.5 to 0.7, orifice coefficients 0.7 to 0.9, openings 0.8 to 1.5 m: X / C = 1.732051 on every step); linear in r between. With no tailwater, or one under the crest, the arithmetic is W62's, bit for bit |
| Refusal removed | `reservoir.py` | A tailwater reaching a gated crest routed nothing before (refused, W62); it now routes |

Packed gate parameters gain two slots (the factor without its opening term, and the opening exponent); a fixed opening
reads the packed factor exactly as before.

## The basin-file keys

Written into a test basin and **re-saved by HEC-HMS 4.12** (`SaveBasinModelAs`), every key written back; the names are
hms.jar's (`hms/model/basin/hydraulics`, the gate-control enum `I` and classes `B`, `ax`, `az`, `b`).

| Block | Keys |
|---|---|
| `Gate Control: Percent Time Series` | `Maximum Gate Opening`, `Percent Gage Name` (a gage of `Gage Type: Percent`, `Units: %`; HMS refuses `Units: PERCENT`, its warning 10613) |
| `Gate Control: Percent Annual Pattern` | `Maximum Gate Opening`, `Percent Pattern Name` (refused, above) |
| `Gate Control: Adjustable Gate Control` (seen in hms.jar, not written) | `Gate Priority`, `Initial Gate Opening`, `Initial Percent Open`, `Maximum Gate Opening`, `Minimum Time Between Adjustments` (refused, above) |

## The race against HEC-HMS 4.12

W59's project and method unchanged (`scripts/w76_cases.py` adds the cases on W59's `hms_project.py` and W62's gates): a
400 m3/s flood into a 100 to 125 m pool from 103 m, 48 h at 5 min, Adaptive Control On, HMS headless (W62's
`run_hms.ps1`), two gates of 10 m on a 20 m crest at 108 m. `scripts/export_cases.py` writes the oracle into
`tests/data/hms_structures/`; `scripts/compare.py` writes `results/compare.json`.

| Case | Gate, opening, tailwater | HMS peak outflow, m3/s | routed: max outflow difference, of peak | peak | pool, m | law at HMS's levels, of peak |
|---|---|---|---|---|---|---|
| `gate_percent_sluice` | sluice, 2 m x percent (100, 25, 75 %), none | 155.00 | 2.2e-4 | -5.7e-5 | 4.4e-4 | 4e-16 |
| `gate_percent_radial` | radial, the same | 173.55 | 4.4e-4 | -4.7e-5 | 3.1e-4 | 2e-16 |
| `gate_sluice_tw_low` | sluice 1.5 m, 108.6 m | 195.22 | 5.4e-3 | +5.5e-4 | 8.9e-3 | 3e-16 |
| `gate_sluice_tw_lip` | sluice 1.5 m, 109.6 m (over the lip) | 146.21 | 6.3e-2 at the stiff steps | +6.0e-3 | 2.3e-2 | 2e-16 |
| `gate_sluice_tw_high` | sluice 1.5 m, 110.4 m | 146.17 | 1.2e-1 at the stiff steps | +2.3e-3 | 3.4e-2 | 5e-17 |
| `gate_radial_tw_low`, `_lip` | radial 1.5 m, 108.6 and 109.6 m | 221.60, 181.25 | 7.1e-3, 6.2e-2 | +1.4e-3, +2.0e-3 | 8.9e-3, 2.3e-2 | 4e-18, 4e-17 |
| `gate_sluice_tw_a`, `_b`, `_c` | sluice 0.8 to 1.0 m, coefficients 0.5 to 0.6 and 0.7 to 0.9 | 123.56, 108.13, 118.97 | 7.1e-3, 7.1e-3, 9.3e-2 | +6.8e-4 to +1.7e-3 | 8.9e-3 to 1.7e-2 | 2e-16 |
| `gate_radial_tw_a`, `_b` | radial 0.8 m | 171.96, 157.23 | 9.8e-3, 8.4e-3 | +8.7e-4, +8.5e-4 | 8.9e-3 | 2e-16 |

The 8.9 mm of the six runs at 108.6 m is HMS's 7,979 m3 lost while its pool stood between 108 and 108.6 m, over the pool
area there; the larger outflow differences sit where the submergence nears 1 and the outflow moves thousands of m3/s
per metre of pool (W67's `level_dam_tw`). The percent runs route within W62's flow tolerance (5e-4 of the peak); their
pool reads 4.4e-4 m at the worst step against W62's 4e-4, HMS's unidentified sub-steps near a gate's kink, which a
moving opening crosses more often.

Old jobs: every W59, W62 and W67 case (47 cases, 323 series) routes to the same bits as on `1ace4e8`
(`scripts/bits.py`, the base engine from `git archive`). `tests/hydrology` and `tests/hms` pass (506, 9 skipped).
W62's test of the drowned-gate refusal is removed, and its Percent Pattern refusal now reads "is not supported".

## Files

- `scripts/w76_cases.py` (the cases), `export_cases.py`, `compare.py`, `bits.py`; the probes `probe_percent.py`
  (which time's opening), `probe_drowned.py` (the drowned candidates), `check_drowned.py` (the law on all ten runs).
  `_work/` holds the HMS projects and is not committed.
- Tests: `tests/hydrology/test_hms_gate_controls.py` (28).

## Not done (gates)

- Percent Annual Pattern and Adjustable Gate Control (above); a percent gage other than INST-VAL in %; an opening that
  varies inside a control step other than linearly between its two times (a gage finer than the step).
- HMS's sub-steps near a gate's kink and near full submergence; HMS's sixtieth (not reproduced, on purpose).
- The dock: no change; the HMS route reads these gates from the file. Not run through the real dock.
