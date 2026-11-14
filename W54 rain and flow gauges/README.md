# W54 rain and flow gauges

**Status (2026-11-13): built on branch `feature/gauges`, not merged, not pushed.** His request: "I need to be able to
apply rainfall gages and flow gages (observed, to check with simulation results as HMS does in hydrographs)." Rain
gauges are a storm kind; flow and level gauges are observed records compared with a run after it ends, and again on
any finished run with a new file, with no rerun.

The work began as a stopped worker's commit `d45a300` (nine modules, unwired, untested). It was read through before
anything was built on it; its design held (one clock for every gauge, periods cut on common edges, the gap rule named
in words), and what it lacked is listed under "What was added".

## What a job holds

**Rain gauges, `storm.kind: gauges`, `storm.gauges`:**

| Field | Meaning |
|---|---|
| `gauges[]` | `name`, `x`, `y` (the DEM's system), `file` (CSV or DSS), `record` (CSV column heading, or DSS pathname or its `B/C` parts), `values` (`incremental` or `cumulative`, for a CSV), `units` (`mm`, `cm`, `m`, `in`), `interval_min`, `time_unit`, `time_format`; or `hms_gage`, a precipitation gage of the HMS project by name, which supplies the DSS file and pathname |
| `method` | `thiessen` (nearest gauge; a lumped subbasin takes exact area shares) or `inverse_distance` (HEC-HMS's: 1/d^`power`, `power` 2, the nearest gauge in each quadrant when `quadrants`, within `search_radius_m`; a place with no gauge in reach takes its nearest one and the run counts them) |
| `weights` | HEC-HMS gage weights by subbasin then gauge, scaled to 1; they replace the spatial method for that lumped subbasin only |
| `gaps` | `error` (the default: the run stops and names the gauge and the time), `zero`, or `neighbours` (the gap takes what the method reads at the gauge from the gauges that have data) |
| `rain_start` | the date and time of the run's minute zero; empty takes the start of the first period |

An empty `gauges` list takes every precipitation gage of the HMS project that has a position. **His Block 2 `.gage`
file holds no gage**: such a job is refused with "storm.gauges lists no rain gauge, and the HMS project's
HEC_HMS_Block_02.gage holds no precipitation gage with a position: list the gauges in the job".

**Observed records, `outputs.observed[]`:** `name`, `file`, `record`, `quantity` (`flow` m3/s, `level` m on the DEM's
datum, `depth` m), `compare` (`line`, `point` or `element`), `target` (its name), `series` (`outflow` or `inflow` of a
lumped element), `start` (the run's minute zero on the record's clock; empty takes `storm.rain_start`, then the gauge
storm's start written in the run folder), `offset` (added to every value: a level moved onto the DEM's datum),
`time_unit`, `time_format`. DSS flow in CFS and stage in feet are converted.

Neither section changes an old job: `storm.gauges` is dropped from the job's hash when empty and `outputs.observed` is
not water (`NOT_WATER`). Checked on three existing jobs (Block 2 `c10_A74_h100`, `dam_Bidah03_100yr_20`, W11's
`lihban_phi`): the hash before the WIP commit and now is the same to the digit.

## Accepted layouts

**CSV** (also `.txt`, `.tsv`, `.dat`): cells separated by commas, semicolons or tabs; `#` lines and empty lines left
out; an optional heading line; the time first, either a number from the run's start in `time_unit`, or a date and time
year first (`2021-10-04 00:05`, `2021-10-04T00:05:00`, `2021/10/04 00:05`) or as HEC writes it (`04Oct2021 00:05`,
`03Oct2021, 2400`); any other spelling needs `time_format` (`%d/%m/%Y %H:%M`), because 04/10/2021 is two different days
in two countries; a date in the first column and a time of day in the second are one time; the value is the column
named by `record`, else the first after the time; an empty cell, a word, `nan` or a value at or below -900 is missing.

**DSS:** the pathname as HMS writes it in a gage or `B/C` or `B/C/F`; with none, the file must hold one series of the
quantity (C part `PRECIP...`, `FLOW...`, `STAGE` or `ELEV...`). `PER-CUM` is depth per period stamped at its end,
`INST-CUM` depth since the start; the file's own type and units win over the job's. Read through a scratch copy.

**Rain periods.** Incremental with `interval_min`: each value closes a period of that length (a CSV with `rain_stamp:
start` opens it), and a stamp spacing longer than the interval is a gap. Without it the spacing is the period, the
first as long as the second, and only an empty value is a gap. Cumulative: the difference of two neighbouring values,
a fall refused as a counter reset. Every gauge's periods are cut on one set of edges at a constant rate inside each.

## The statistics

Common time base: the observed instants with a value inside the simulated record; the simulated series read straight
between its own samples at each of them. With `o` observed, `s` simulated, `n` points:

- **NSE** = 1 - sum (s - o)^2 / sum (o - mean o)^2.
- **RSR** = sqrt(sum (s - o)^2 / n) / sqrt(sum (o - mean o)^2 / n) = sqrt(1 - NSE).
- **PBIAS** = 100 sum (s - o) / sum o, **positive when the model is high**. Moriasi et al. (2007) write sum (o - s), the
  other sign; the run's `statistics.json` says which.
- **RMSE** = sqrt(sum (s - o)^2 / n), in the quantity's unit.
- **Peaks and their times** on each series' own samples between the first and last instant of the base; **volumes**
  (flow only) the trapezoid of each on its own samples in that window.

A line's discharge carries its direction's sign and is compared as a size, as the plot draws it; a line with a design
record (W41) is compared on grid plus lumped water. Written in the run folder: `observed/<name>.csv` (both series on
the base, with dates when the record had them) and `observed/statistics.json` (formulas, every record, every failure
with its reason). Tested against hand numbers in `tests/engine/test_observed.py`.

**`wadi2d compare RUN_DIR [--observed FILE.json]`** redoes the comparison on a finished run: the job's own list, or a
JSON list of observed records whose paths are relative to that file.

## Checks

**Cells against lumped (`lumped_vs_cells/`).** Three synthetic gauges of 80, 160 and 40 mm over Block 2; for each of
the 18 subbasins of his HMS basin the lumped areal mean against the mean of the cells centred inside its polygon.
Worst difference: Thiessen 0.13 % at 30 m and 0.09 % at 10 m (the bisector drawn by cell centres), inverse distance
0.04 % and 0.05 % (20,000 points on a polygon). Rain is linear in the gauges, so the same holds for any record.

**Engine (`tests/engine/test_gauge_run.py`, closed box, CPU):** one steady gauge gives the uniform storm's rain and
storage to 1e-6; two gauges by Thiessen put each gauge's rain on its own half, volume to 1e-6, balance error under
1e-4; a run compares its observed records when it ends (NSE above 0.99 for a depth the rain sets); a changed record
changes the job hash; a missing record stops the run before the grid.

**Shaheen at Lihban (`shaheen/`): W11's run rebuilt through the gauge storm and the observed overlay, nothing tuned.**
W11 ran the 5-minute rain of gauge DB839224AD less a phi index of 3.251 mm per 5 min (39 mm/h), the index that makes
the excess the observed runoff, 150.67 mm, as a hypothetical storm. Here that excess is a rain gauge record with dates
at the gauge, the run starting at 23:15 on 3 October, and the 5-minute observed flow an observed record with dates.
W11's own job was run again on this branch's engine beside it:

| | Peak, m3/s | at | / observed | Volume, Mm3 | NSE | RSR | PBIAS |
|---|---|---|---|---|---|---|---|
| Observed, 5-min sheet of project 2331 | 2,540 | 04:00 | 1 | 29.60 | | | |
| **Gauge storm** | **2,379** | **03:11** | **0.937** | **29.40** | **0.782** | **0.467** | **-0.7 %** |
| W11's hypothetical job, this engine | 2,379 | 03:11 | 0.937 | 29.40 | 0.782 | 0.467 | -0.7 % |
| W11 as recorded (engine of 2026-11-02) | 2,428 | 03:05 | 0.96 | 29.4 | 0.75 | | |

The gauge storm gives W11's job on the same engine to within 2.0 m3/s at any time of the line series (0.09 % of the
peak) and 3.9 m3 of 30.3 Mm3 of rain. The difference to W11's own figures is the engine since then, not the gauges
[Likely: the local-radius face table of W49 lowers peaks in narrow gorges by 3 to 4 %; not isolated here].

**Found, for his decision: the project's HMS calibration holds a different record of the same gauge.** Its flow gage
`DB839224AD - Shahin` (6 min, `Albatinah_Calibration.dss`) peaks at 2,540 m3/s at **04:48**, 48 min after the 2331
sheet, and holds **35.47 Mm3**, 20 % more (the "older project table" figure W11 set aside). Compared with no rerun
through `wadi2d compare`, the same run reads NSE 0.637 and PBIAS -17.1 % against it, 0.782 and -0.7 % against the sheet.
Its rain gage `DM827927AF - Shahin` holds 412.8 mm from 00:01 on 4 October, against the sheet's 458.8 mm from 13:05 on
the 3rd. Which record is the gauge's is his call; W11's number stands on the sheet.

**Dock (`dock_gauges.py`, Bidah 03 at 30 m, QGIS 3.44.8 with a throwaway profile in `dock_check/`): 34 of 35.**
Two synthetic rain gauges from a point layer, West (433,000, 2,725,500) 40 mm and East (438,500, 2,725,500) 10 mm in
four 15-minute periods written with dates, and a flow gauge typed by hand against the Bidah 03 dam line, a synthetic
triangle peaking at 60 m3/s at 01:30; the run starts at the time typed in the section. Passed: the section and its
table, the positions from the layer, a gauge with no record refused in words before a run, the job's storm and
observed record, both runs finished, observed compared after each run, the observed flow in Result lines dashed and
dotted beside the computed one, its value in the readout at the slider's frame, the agreement in words
(`widget_observed_on_line.png`, `widget_gauges_table.png`, `log_dock_gauges.txt`).

| Method | Cell shares West / East | Mean rain, mm | Rain, m3 | Rained area, km2 | Peak at Bidah 03, m3/s |
|---|---|---|---|---|---|
| Nearest gauge | 0.444 / 0.556 | 23.33 | 667,188 | 28.595 | 141.66 |
| Inverse distance squared | 0.469 / 0.531 | 24.06 | 688,138 | 28.596 | 142.49 |

Each run's rain equals its own gauge shares of the rained area: the area that closes it is the same under both methods
to 3e-5. **The one failure is the rule set before the run, that the two methods move the dam line's peak by more than
2 %: they move its volume by 3.1 % and its peak by 0.6 %.** Where they part is shown by `two_gauges/transect.json`:
nearest gauge steps from 40 to 10 mm at x 435,750; inverse distance runs 38.6, 32.6, 22.3, 13.7 mm from x 434 to 437 km,
and beyond either gauge, with both gauges in one quadrant, takes that gauge alone, as HEC-HMS's quadrant rule does. [Guessing, not
traced] the dam's peak is set by runoff near the dam, which both methods give nearly the same rain. A case designed to
move a peak was not rerun: the rule stands failed as set.

**The harness needs `.venv` in the checkout it runs from.** In a worktree the dock found no engine ("Process failed to
start: The system cannot find the file specified", `dock_probe.py`) until a junction `.venv` pointed at the main
checkout's environment; another worker's dock check stalled the same way the same evening.

## What was added to the WIP commit

- Wiring: the run writes `rain_gauges.json` (method, totals, positions, the date of minute zero, the rained area's share
  of each gauge, every lumped subbasin's shares) and compares `outputs.observed` once its series are written.
- `wadi2d/engine/agreement.py` (the statistics), `wadi2d/engine/observed.py` (the comparison on a run folder), the
  `compare` command, observed records in `wadi2d lines`' catalogue.
- Plugin: section `7b. Gauges (optional)` (a point layer of rain gauges or rows by hand; name, gauge, record, series,
  position or what it is compared with; how rain is spread, the search radius, what a gap does, what a rain CSV
  holds, the run's start); `Rain gauges` in the Storm section's choices; the observed series drawn dashed and dotted in
  black beside the computed one in Result lines, its value in the readout at the slider's frame, and the agreement in
  words above the plot. A flow gauge names a line or a lumped element and the dock decides which from the Results
  points layer's names.
- Tests: `tests/storm/test_gauges.py` (29), `tests/engine/test_observed.py` (8), `tests/engine/test_gauge_run.py` (6),
  `tests/hms/test_gage.py` (3), `tests/plugin/test_gauge_rows.py` (7), three in `tests/plugin/test_line_view.py`.

## Not done

- The dock's values for a rain CSV (`incremental` or `cumulative`) are one choice for every gauge; the job holds one per
  gauge. Per-gauge units, interval and time format are job-only.
- HMS's time-varying inverse distance (a gauge with no value in a period drops out of that period's weights) is the
  `neighbours` gap rule only in effect, not in form: a gap is filled at the gauge, then spread.
- A lumped subbasin's shares under inverse distance are averaged on 2,000 points by default (`samples`); 0.05 % on Block 2
  needed 20,000.
- No ARF study on a gauge storm: gauged rain has no area reduction, and `at_area` returns the same rain.
