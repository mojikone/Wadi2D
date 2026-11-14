# W74 chart and workbook polish

**Live.** Branch `feature/chart-workbook-polish` off `feature/fast-products` at `80c1cd3`; not merged, nothing pushed.

The open P3 items of the hydrograph chart (`W64 time of concentration and chart`) and the dam workbook (`W60 dam workbook`,
its dock dialog in `W68 layer groups and dock rows`), 2026-11-14. Basin generation and the dock's hydrology section were
not touched (another worker's, `feature/basin-editing`).

## 1. The dam workbook

| Item | Built | Where |
|---|---|---|
| Reservoir sheets from our own runs | A Wadi2D run's `series/network_<reservoir>.csv` fills a reservoir's sheet: pool from `pool_m`, storage from `storage_m3` (both read since W60, now with the names W59 writes), and **each structure's flow**, W59's `<kind>_<n>_m3s` and `evaporation_m3s`, as a column per return period after storage (`Orifice_1_200yr`, `Rating_spillway_1_200yr` ...), with a `Peak <structure> (m³/s)` column in the statistics block after W60's. The summaries keep their columns (peak outflow, attenuation, highest pool); the side-by-side target sheet carries no structure. | `wadi2d/workbook/model.py` (`Hydrograph.structures`), `sources.py`, `layout.py` |
| A depth-area study's folder as one input | `--run RP=DIR` takes a study's folder (it holds `study.json`) as that return period. Each element is read as the study reads it: an element the study reran lumped at its own area is rerun the same way (the whole hydrograph, with pool, storage and structures at a reservoir); a design line or a hand-back-fed element is blended from the two storm-area runs either side of its area, linear in ln A, every ordinate, with the weights the study's maps and lines use; an element whose water stays on the grid is refused, as the study gives it no row; one with no row needs `--area NAME=KM2`. The catchment is the study's area; the Read me names each element's reading and the study's tabled peak. | `wadi2d/workbook/study.py` |
| Renaming sheets | The dialog's element list is a table: tick, element, **Sheet name** (the element's name until typed over); a renamed sheet goes to the engine as `NAME=SHEET`. Excel's rules (31 characters, none of `[]:*?/\`), the workbook's own sheet names and duplicates are said before the engine starts, and the engine refuses them in words too. The dialog also takes a study folder as a return period's row and offers the rows of its table. | `plugin/wadi2d_qgis/workbook_rows.py`, `workbook_dialog.py`; `model.check` |

[Certain] A blended hydrograph's own peak is not the study's tabled design peak: the study reads ln Q against ln A between the
two runs' peaks, the blend is linear in every ordinate (as `wadi2d/products/study_lines.py` blends lines), so the blend's
peak sits at or under the tabled one when the runs peak at different times. Both are in the Read me; which one a dam
designer quotes is his call.

## 2. The chart

| Item | Built | Where |
|---|---|---|
| Heading by kind on the HMS route | The listing of an HMS network now carries each element's kind (subbasin, reach, junction, reservoir, diversion, source, sink) and drainage area (`Downstream` links only, HMS's reading; the same number as the workbook's catchments for all 40 elements of Block 2's Basin 1), so the heading reads `Reservoir: Bidah 03 Reservoir.` where W68 found `Lumped element: ...`. | `wadi2d/products/hms_facts.py`, `result_lines.element_facts` |
| Tc on HMS basins | HMS keeps a subbasin's longest flow path and 10-85 slope in the basin's `.sqlite` (`subbasin_statistics`), not in the `.basin` text; where they are there, the tc is his Kirpich expression on them. **On Block 2's Basin 1, 0.6 x that tc gives every one of the 18 HMS lags back within 0.34 %**, which is W24's finding read the other way and proves the units. Everywhere else the header says `tc not available` and why (no flow path in the .sqlite; HMS holds no flow path to a reach's, junction's or reservoir's outlet). | same |
| Rain bar on design lines | A design line of a generated basin carries the rain and excess of the junction it pours into, the area-weighted depths of the subbasins above it (W64's columns), and its chart hangs the bar as an element's does. | `result_lines.line_rain`, `element_view.with_facts` |
| Add to chart | An `Add to chart` button (a menu of the run's other entries) and, on the map's right-click, `Add to chart: ...` beside `Hydrograph: ...` for every entry under the click: its flow of record (an element's outflow, a line's record, a drawn line's frames) over the chart shown, a colour each, named in the heading (`Added: S1.`); `Clear added`; choosing another chart drops them. A point has no flow and is refused in words. | `element_view.overlay_curve`, `with_overlays`; `result_lines.py` (panel) |
| A diversion's flows | `passed_m3s` and `diverted_m3s` (W72): the outflow is labelled `Passed on (outflow)`, the diverted flow drawn beside it in red, and the header gives each one's peak, time and volume. | `element_view.element_view` |

Pictures from the headless test on QGIS's Python: `chart_overlay.png` (S1 added over the reservoir), `chart_reservoir.png`,
`chart_subbasin.png`.

## 3. Tests (CPU, `.venv\Scripts\python -m pytest -o addopts=""`)

| Test | Checks | Result |
|---|---|---|
| `tests/workbook/test_workbook.py` (1 new) | a run reservoir with W59's columns: pool, storage, evaporation and two structures as columns and peaks, the summaries in place, the target sheet without structures, the note | pass |
| `tests/workbook/test_study_source.py` (3, new) | the blend by hand; a real two-run study: the exact element's peak equals the study's tabled peak to 1e-9, the hand-back reach equals half and half of its two runs' series, on-grid refused, no row refused, an element at a given area; the workbook from the study with a renamed sheet and the readings in the Read me | pass |
| `tests/plugin/test_workbook_rows.py` (2 new, 1 extended) | `NAME=SHEET`, every sheet-name refusal, a study as a source; the engine writes the renamed sheet and refuses `Read me` | pass |
| `tests/engine/test_hms_facts.py` (3, new) | a diversion basin: kinds, no tc and why; **Block 2 (data): 18 lags = 0.6 tc within the 0.5 % rule (worst 0.34 %), areas equal to the workbook's**; a design line's rain | pass |
| `tests/engine/test_basin_run.py` (1 new) | a real generated-basin run: a design line listed with its junction's rain, 60 mm and 27.17 mm of excess | pass |
| `tests/plugin/test_element_view.py` (4 new) | HMS heading and tc not available; a diversion's two flows and the diverted volume by hand; a design line's rain bar; Add to chart (labels, colours, readout, points refused, a drawn line only once read) | pass |
| `tests/plugin/test_chart_qgis.py` (extended) | on QGIS 3.44.8's Python, headless, the real panel: `Add to chart` from the right-click and from the button, not offered twice, `Clear added`, dropped by a new chart; the overlay paints | pass |
| W60's W1 rebuild, `W60 dam workbook/rebuild_w1.py` + `compare_w1.py` | 560 of 560 formulas, 375 of 375 chart references, 8 text cells by design, 1,347 cells by W1's double rounding and 0 with it imitated: unchanged from W60 | pass |
| `tests/plugin` whole, `tests/workbook`, `tests/products/test_result_lines.py`, `test_face_flow.py`, `tests/render/test_server.py`, `tests/engine/test_study_lines.py` | unchanged behaviour | 572 + 48 pass |

The full suite was not run (his rule: the full suite at merge).

## 4. Through the real dock

`dock_chart_workbook.py` by `tests/dock/run_check.ps1`, a throwaway QGIS 3.44.8 profile, CPU engine, W68's run (Bidah 03 at
30 m, the 200-yr storm from W68's HMS copy, the reservoir with an orifice, a rating spillway and a dam top fed by a
hand-back line): **13 of 13**, 360 s. Log and picture in `logs/`.

| Check | Result |
|---|---|
| the run finishes; the right-click under the pan tool offers the reservoir's hydrograph | pass |
| the heading reads `Reservoir: Bidah 03 Reservoir.` on the HMS route (W68 read `Lumped element:`); the note: drainage area 20.97 km2 (W39's validation-line area), `tc not available: HMS holds no flow path to an element's outlet`, peak out 25.4 m3/s | pass |
| the right-click offers `Add to chart:` for the two upfront lines under it; one added: `Reservoir: Bidah 03 Reservoir. Added: Bidah 03.`, one curve more; `Clear added` gives the chart back | pass |
| the workbook dialog: the reservoir's sheet renamed `Bidah 03 dam` in the table; the workbook written with that sheet and not the series name, its `Pool_200yr`, `Storage_200yr`, `Orifice_1_200yr`, `Rating_spillway_1_200yr`, `Dam_top_1_200yr` columns from the run, and Peak outflow, Attenuation, Highest pool level | pass |

## 5. Not done

- A design line on the HMS route has no rain bar: no HMS element is tied to a design line. On a generated basin whose
  subbasins above the line run rain-on-grid, the junction's series holds only the lumped subbasins' rain, weighted over
  their own area, so the bar is the lumped part's; [Likely] the right bar there is the storm over the line's whole
  drainage area, not built.
- Tc at an HMS junction, reach or reservoir: HMS holds no path to their outlets; the generated basin's D8 path has no
  HMS twin.
- The workbook's inflow-outflow tile charts do not draw the structures' flows (columns and peaks only).
- The study's exact rerun reads the run folder's `config.resolved.json` and the DEM where the study found it; a study
  moved off its DEM cannot rerun its exact elements (refused in the rasterio error's words).
- The readout under the chart names an added curve's value only as `flow ... (upfront)`, not by element.
