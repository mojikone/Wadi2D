# W64 time of concentration and chart

Live. Branch `feature/tc-and-chart` off `feature/fast-products` at `5d6ced2`; not merged, nothing pushed.
The specification is `W58 HMS elements and dam workbook/README.md` section 6.

His words (2026-11-14): HMS shows only the subbasin lag; he wants Tc at every element and every point, and a hydrograph
chart per element with a thin rainfall bar chart on top, inverted, his layout.

**Default chosen for him while he was out, his to overturn:** a right-click on an element or point on the map opens its
chart in the one shared docked panel (the Result lines panel), not a window per element as HMS does. His own layout,
when he shows it, replaces this one.

## 1. Time of concentration

The rule, his HEC-HMS expression (the one all 18 Block 2 lags follow, `wadi2d/basin/parameters.py`):

> Tc = (0.75 L)^0.77 / (52 S^0.385) minutes, L the longest flow path in m, S its 10-85 slope in m/m.

- **Subbasin:** its own longest path, as its lag uses. Under the Kirpich lag method the lag stays 0.6 Tc (the SCS
  lag-to-Tc relation, NEH 630 chapter 15, L = 0.6 Tc [Likely the equation number 15-3; not re-read]). Under the NRCS lag
  method the lag is NRCS's and the Tc shown is still Kirpich's.
- **Reach, junction, reservoir; so every dam, design point and design line** (they are junctions of the basin model):
  the longest D8 path from the whole drainage area above the outlet, reaches included. One pass upstream first over the
  analysis raster gives every pixel's longest upstream path and the pixel it starts from (`longest_upstream` in
  `wadi2d/basin/kernels.py`); the 10-85 slope is read on the breached ground along that path, as for a subbasin. A reach
  carries the figure at its outlet.
- **Network check, beside it in the chart:** the time from the centroid of the excess to the peak of the element's own
  outflow, from the run's series.

[Certain] Kirpich (1940) was fitted on small Tennessee farm basins; a junction of tens or hundreds of km2 is far outside
that range. Both figures are shown, labelled, and no lag is taken from a junction's Tc.

Where it is: `tc_minutes` (derived) in every element of `basin.json`, beside `tc_flow_length_m` and `tc_slope_10_85`
(terrain) for non-subbasins; a column `tc_minutes` in all three layers of `basin.gpkg`; a `Tc, min` column in the dock's
junction table; the chart header. A `basin.json` written before W64 gains the subbasins' Tc on reading (`refresh`);
its junctions need the basin generated again for theirs. A job override of a subbasin's flow length or 10-85 slope
recomputes its Tc as it does its lag.

## 2. The chart

- The engine writes `rain_mm` and `excess_mm` per step into every `series/network_<element>.csv` and `results.h5`
  series: a subbasin its own depths (the storm's area reduction already in them), any other element the area-weighted
  depths of the subbasins above it through `Downstream` links. The value at a time is the step ending there; the first
  time holds 0. Elements the hand-back link runs live carry them too.
- `wadi2d lines` (the panel's listing) gives each lumped element, design point and design line of a generated basin its
  kind, drainage area, Tc and a subbasin's lag.
- The panel (`plugin/wadi2d_qgis/element_view.py`, drawn by `line_plot.py`): a thin rain bar hangs from the top axis,
  rain light, excess dark over it, the losses the difference; the flow below (outflow of record, inflow); a reservoir's
  pool level on a right-hand axis when its series has `pool_m` (W59); the header names the drainage area, Tc, the
  network's centroid-to-peak time, the peak, its time and the volume. The time slider's cursor runs through both.
- Right-click on the map: every shown vector layer with a `name` field is searched within 6 screen pixels of the click;
  each feature whose name is an entry of the open run gives a `Hydrograph: ...` item in QGIS's own map menu, points
  before lines before polygons (a junction sits inside its subbasin). The generated basin's layers, the design points
  and lines and the job's upfront lines all carry `name`. The panel must have a run open (Result lines in the dock).

Pictures of the chart as the headless test drew it: `chart_reservoir.png`, `chart_subbasin.png` (synthetic series).

## 3. Tests (targeted, CPU, `.venv\Scripts\python -m pytest -o addopts=""`)

| Test | What it checks | Result |
|---|---|---|
| `tests/basin/test_tc.py` (5) | Kirpich by hand (L 10 km, S 0.01: 109.1 min); on a straight valley, the two design points' path length, 10-85 slope and Tc against the geometry; reach = its outlet; subbasin lag = 0.6 Tc; an old file gains Tc; the gpkg columns | pass, within 2 to 3 % of the hand path |
| `tests/engine/test_basin_run.py` (1 new) | a real generated-basin run: 60 mm in an hour on 2-min steps, 2 mm a step and 27.17 mm of excess at the outlet, the fork and both arms; the listing's Tc equals the file's | pass |
| `tests/plugin/test_element_view.py` (7) | centroid to peak and volume by hand; reservoir chart with bars, pool axis and header; subbasin and HMS element; facts under a point; right-click matching order | pass |
| `tests/plugin/test_basin_rows.py` (1 new) | the junction table's Tc cell | pass |
| `tests/plugin/test_chart_qgis.py` | on QGIS 3.44.8's Python, headless: the real panel on a real canvas, the right-click menu over a junction inside a subbasin, over the subbasin alone, and off both; triggering opens the right chart; the chart paints | pass |
| Existing: `tests/basin/test_model.py`, `test_job.py`, `test_network.py`, `tests/engine/test_network_series.py`, `test_handback.py`, `tests/plugin/test_line_view.py` | unchanged behaviour | pass |

The full suite was not run (his rule: full suite at merge).

## 4. Not done

- **Not tested through the real dock** (`tests/dock/harness.py` in a throwaway profile); the right-click was driven by
  emitting the canvas's `contextMenuAboutToShow` signal on a headless canvas. [Likely] On his QGIS the map menu appears
  only under a map tool that shows it (the pan tool does).
- "Add to chart", a second element overlaid: not built.
- A design line's own rain bar: the line's facts (area, Tc) are shown, its rain is not (its series is the grid's).
- HMS basins: no Tc (no terrain path in the model); their elements' chart has rain bars only for what the lumped engine
  computed.
- Tc on Block 2's real basin not computed or compared with anything; no published Tc for it exists here.
- The time-to-peak "network check" uses the element's outflow; on a reservoir that is the routed peak, not the inflow's.
