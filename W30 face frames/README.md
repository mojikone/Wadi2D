# W30 face frames

**Status (2026-11-02): done on QGIS 3.44.8, branch `feature/face-frames`, not merged.** A run now saves the discharge on the faces with every map (`outputs.face_discharge`, on by default), and a line drawn after the run reads the same signed face discharges an upfront line uses: the number of record at the frame interval, with no estimate. Through the real dock on Bidah, four upfront lines, across, oblique, along the axis and bent, read back within 0.3 % of their own series at the frames on the uniform grid and to the digit on the mesh; the unit tests show equality to the last digit at the maps' own instants. **The cost: a map grows 1.58 x, 18.4 against 11.7 B per cell per map on Bidah, and only runs made from now on have it; older runs fall back to the W21 estimate and the plot says so.** 42 of 42 through the dock, 13 new engine tests, 4 new plugin tests.

## [PRESERVE-CHECK]

KEEP, not touched:

- Upfront lines and points: `Monitor.record`, the series files, `results.h5` `series/`, their format and the job format.
- The three map fields `depth`, `mean_depth`, `speed` and every reader of them: `frames.py`, the time slider's `frames.nc`, the pixel maps, Make map. `frames.nc` does not carry the faces: it is for the mesh layer, and QGIS has no use for a per-face discharge.
- The W21 estimate from depth and speed: it stays as the fallback and its tests stay, now on a run with the setting off.
- The panel's buttons, the slider, the Temporal Controller wiring, the scratch layer, the map tool.
- The job hash of old jobs and the checkpoint format: the setting is in `NOT_WATER`, so a checkpoint resumes whatever it is set to.

CHANGE, additions and one wording:

- `outputs.face_discharge` in the schema, default on. `Monitor.snapshot` adds `qx` and `qy` to every saved map when it is on, through `model.field`, so the GPU and the CPU write the same thing from one source.
- New `wadi2d/products/face_flow.py`: the staircase of a line on the lattice of the saved maps, the real faces it crosses, the signed sum.
- `read_line` uses it when every saved map holds both faces, else the estimate; the answer carries `flow_source`, `faces` or `estimate`.
- The plot's frames curve is labelled "from the faces, of record" and the footer says what that means; an estimate keeps W21's words.
- The dry-run estimate of the maps' disk scales by `FACE_FRAME_SHARE` 1.6 when the setting is on.
- The frozen schema sample follows the schema.

FILES: `wadi2d/config/schema.py`, `wadi2d/run.py` (one entry in `NOT_WATER`), `wadi2d/io/results.py` (the layout note, `FACE_FIELDS`), `wadi2d/engine/monitor.py` (`snapshot`), `wadi2d/engine/estimate.py` (`saved_maps`), new `wadi2d/products/face_flow.py`, `wadi2d/products/result_lines.py`, `plugin/wadi2d_qgis/line_view.py`, `plugin/wadi2d_qgis/README.md`, `tests/products/test_face_flow.py` (new), `tests/products/test_result_lines.py`, `tests/products/test_step.py`, `tests/plugin/test_line_view.py`, `tests/plugin/schema_sample.json`, this folder.

## The setting

`outputs.face_discharge: true` (the default). With it, `maps/t<seconds>/` holds `qx` and `qy` beside `depth`, `mean_depth` and `speed`: the discharge through each cell's west face, positive eastward, and through its north face, positive southward, m3/s, float32, as the solver's state arrays hold them (`Model.discharge_x`, `discharge_y`). Discharge and not unit discharge: it is the quantity the upfront line sums, and a line then needs no face length and no table. On a quadtree a coarse cell's discharge is painted onto every finest cell under it, as the other maps are.

`false` writes the maps as before. The job hash ignores the setting, so a run can be resumed with it switched either way; a run resumed from a checkpoint made before this branch holds maps of both kinds, and then every line falls back to the estimate, because a curve half of record and half estimated would say neither.

## How a line is read

`face_crossing` rasterises the line onto the face lattice with the same `staircase` the engine uses for an upfront line (`forcing.line_faces`), keeps the edges on active cells, and takes the staircase's own sign, positive to the right of the line. `face_flow` is the dot product of the saved `qx` and `qy` at those cells with the signs, the sum the `Monitor` makes at every series step. A test holds the two to the same state indices and the same signs on an across, an oblique and a bent line.

On a mesh the maps are on the finest raster. Of the staircase's edges only those on a coarse cell's own boundary count (column or row a multiple of the cell's size), each weighted by one over the size, so a line across a whole coarse face reads the whole discharge once, a line across part of it reads that part, and an edge inside a coarse cell, which is no face, counts nothing. Upfront lines on a mesh sit on finest cells (the engine refines along them), so for them the rule is the uniform one; for a temporary line through coarse cells the share rule is reasoned, tested on a painted raster, and not held to an independent record, because none exists [Likely].

The answer's `t_s` is still the frame's name, whole seconds, as the time slider reads it; the map itself was taken at the first step at or past that second, up to a step later. That is the only reason the dock's ratios are not exactly 1 on the uniform grid.

## The table

Through the real dock on Block 2 ground around Bidah, uniform rain 60 mm in 1 h, 2 h run, maps every 5 min, series every minute, GPU. "Record at the frames" is the line's own series interpolated at the frame times; "worst" is the largest departure from it over the frames where the record stands above a quarter of its peak. `table.json` holds the numbers, `log_dock_face_frames.txt` the run.

| Run | Cells, maps | Line | Record peak, m3/s | Read from the faces | Peak ratio | Worst over running frames |
|---|---|---|---|---|---|---|
| Bidah, 20 m, 5 min | 71,934 cells, 24 maps | Across | 314.3 | 313.7 | 1.001 | 0.28 % |
| | | Oblique | 325.1 | 323.8 | 1.001 | 0.10 % |
| | | Axis, 550 m along the wadi | 327.1 | 326.3 | 1.001 | 0.13 % |
| | | Bent, the dam line, 4 vertices | 327.8 | 327.1 | 1.001 | 0.13 % |
| Bidah, same job, faces off | | Across, the W21 estimate | 314.3 | 294.4 | 0.939 | 6.1 % |
| Bidah, mesh 10 to 40 m, 5 min | | Across, Oblique, Axis, Bent | 316.3 to 327.3 | the same | 1.000 | 0.00 % |

The 0.1 to 0.3 % on the uniform grid is the whole-second frame name against a series read every minute on a rising limb, not the reading: the engine tests compare at the maps' own instants and agree to 2 mm3/s, the rounding of the answer. On the mesh the steps fall on whole seconds and the two coincide.

Besides the table: a line drawn through the real map tool and a line picked from a layer both read from the faces and say so; the run without faces, opened by its folder, shows the estimate with W21's words; a drawn line on the mesh reads the faces. Looked at: `plot_upfront_line_of_record.png` (the record and the frames lie on each other), `plot_temporary_line_of_record.png`, `plot_estimate_fallback.png`, `plot_mesh_line.png`. The first plot of the day had the new legend run past its chart into the next panel; the label was shortened and the full words moved to the footer.

## The disk cost, measured

Same job, same machine, Bidah at 20 m, 71,934 cells, 24 maps, gzip level 1 as before:

| | `results.h5` | Per cell per map |
|---|---|---|
| With the faces | 31.8 MB | 18.4 B |
| Without | 20.1 MB | 11.7 B |
| The faces alone | 11.6 MB, 37 % of the file | 6.7 B |

So a map costs 1.58 x what it did, on wet ground with two float32 fields added to three; dry ground compresses better on all five. W21 guessed 5/3. The dry-run estimate (`FACE_FRAME_SHARE` 1.6 on `frame_bytes_per_cell`) follows. On the full extent at 30 m, 17.1 M cells, 144 maps at 5 min, W2's 10 B per cell per map would become about 16: 24.6 GB in place of 15.4 [Likely, scaled, not run].

## Tests

- `tests/products/test_face_flow.py`, 13: both faces on every map, float32, the grid's shape; the GPU writes the same and its line reads its record (marked `gpu`); the setting leaves the job hash; across, oblique and bent lines read their series to 2 mm3/s, sign included; the crossing is `line_faces` to the index and the sign; the sum's sign; the quadtree rule on a painted raster; a run without faces falls back and says so, with W21's 8 %; one map without faces sends the line to the estimate; no maps, no faces; a stop and a resume keep the faces on every map and the line its record.
- `tests/products/test_result_lines.py`: the W21 tests now expect the record, sign included, on the uniform run and the mesh run, and `flow_source` in the command's answer.
- `tests/plugin/test_line_view.py`, 4: the label and footer of a line of record, the old words for an estimate or an older answer, the record beside the frames, the words are the engine's.
- `tests/products/test_step.py`: the disk estimate with the faces on and off.

## Not tested

- The full extent: only Bidah and the engine's small planes. Disk and time there are scaled, not measured.
- A temporary line through coarse cells of a mesh against an independent number: the share rule has only the painted-raster test.
- The resume on the GPU: CPU only; the GPU resume of a mesh run is covered by `test_mesh_paths` on `main`, unchanged.
- A run with the setting off through the dock: the dock has no switch for it, by design; the fallback came from a job edited by hand and run by the engine's command line, then opened in the panel by its folder.
- QGIS other than 3.44.8.

## Rerun

```
powershell -File tests\dock\run_check.ps1 "<full path>\W30 face frames\dock_face_frames.py" <throwaway folder> -Copy "W30 face frames"
```

From a worktree the harness needs `.venv` beside the repository: a junction to the main checkout's works. The engine tests: `.venv\Scripts\python -m pytest -q tests\products\test_face_flow.py`.
