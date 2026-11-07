# W39 gridded 200-yr rain test

**Status (2026-11-07): done on QGIS 3.44.8, testing only, branch `test/gridded-200yr` from `c5d2dec`; no engine or plugin code changed. 41 of 44 checks pass through the real dock. The 3 failures are one rule, DSS and NetCDF water within 0.1 %, failing in three modes: the two files themselves differ by +0.265 % over the domain, and the engine reads that difference exactly. Bidah 03 peaks, RP200, 30 m: full 2D NetCDF 661.6 and DSS 663.4 m3/s; hybrid NetCDF 410.2 and DSS 411.4 m3/s. The hybrid figures come from the lumped junction `Bidah 03` (`series/network_Bidah_03.csv`); the hybrid's result line reads 0.69 m3/s, because the lumped flow passes it inside a reach. PMP through the HMS route: full 2D 1,701.1 m3/s; hybrid 1,443.8 m3/s (S13 network). HMS's own figure is 1,688.4 m3/s, but at a different ARF.**

His request: "just 200 year grid, try both dss and nc to check the model work fine"; "both [hybrid and full 2D] but on small catchment to expedite, 30 meter cell size"; "no ARF applied in them". Added the same day: "Also check the PMP tif with its pattern as used in HMS."

## The files, read outside the engine first (`rain_volume.py`, `results/rain_before.json`)

| | NetCDF `Precipitation_RP200_10min.nc` | DSS `Precipitation_RP200_10min.dss` |
|---|---|---|
| Frames | 144 x 10 min, 2000-01-01 00:00 to 24:00, period-ending with bounds | 144 records, D/E parts 10 min apart, same times |
| Grid | 494 x 605 pixels of 2 km, WGS 84 / UTM 40N, north row first | 606 x 528 cells of 2 km, **SHG: USA Contiguous Albers (USGS), central meridian -96°**, south row first |
| Mean / max 24 h total, whole grid (dock label) | 161.9 / 360.9 mm | 161.9 / 360.8 mm |
| Over the Bidah 03 domain, 28.77 km2, area-weighted | **157.48 mm**, 17 pixels | **157.90 mm**, 18 pixels |
| Over HMS's S13 polygon, 20.97 km2 | 157.14 mm | 157.62 mm |

- [Certain] The DSS is the NetCDF resampled onto the Standard Hydrologic Grid. At 74,764 shared ground points the two agree with a correlation of 0.99983 and a median difference of 0.013 mm. Read with the other row order they correlate at -0.11, which settles the row order without trusting any reader. Over Oman the SHG axes are turned about 92° from north (conic convergence 0.603 x 152.4°), and 6.7 % of the DSS cells hold no data: the corners of the turned grid.
- [Certain] **The resampling moves the depth over this 29 km2 domain by +0.265 %.** That is the whole of the failed rule below. Writing the DSS in UTM 40N would remove it. HEC Vortex takes a target WKT [Likely].
- [Certain] **The RP200 grid holds 157 mm over Bidah 03, where his HMS storm `FM_200yr.met` uses a 251 mm point depth: 37 % less.** The NetCDF's own attributes list 251 mm as the RP200 reference depth and describe a blend of a 24-hour GeoTIFF with regional patterns. Each pixel also carries its own timing (`Per-cell magnitude-selected weights`).

### `FM_PMP.met`, as written

Precipitation Method: Hypothetical Storm. Precipitation-Frequency Grid `PMP`. Storm Type: Specified Pattern `FM PMP`, 24 h. **Storm Area 300 km2, Depth-Area Reduction Method: User-Specified, table `ARF FM`.** Uniform Depth: Yes. The grid manager (`HEC_HMS_Block_02.grid`) points `PMP` at **`Hydrology Data\Rainfall Grids\tiff\Clip_PMP_823mm_21c_27032024.tif`, the clipped raster, not `PMP_823mm_21c.tif`**. The pattern reaches 100 % at 87.5 % of the 24 h. ARF FM at 300 km2 is 0.8347, interpolated linearly between 200 km2 (0.864) and 500 km2 (0.776). The met asks for this ARF, so the HMS route applies it, to the lumped subbasins and to the 2D cells alike. Nothing was added.

- [Certain] **The raster named 823 mm holds 1,404 mm over S13 (area-weighted) and 1,406 mm by cell centres, with a maximum of 1,841 mm on the clip.** HMS read it as it is: its depth-area analysis put 1,370.4 mm on S13, which is 1,405.65 x 0.9749. Whether the values or the name are right is his to say.

## The runs (`dock_gridded.py`, `log_dock_gridded.txt`)

Every run goes through the real dock on Bidah 03's catchment (`domain_Bidah03.geojson`, 31,971 active cells of 30 m, of which 199 are outlet cells). Block 2 ground comes from the 5 m DEM. The outlets are Bidah's two `normal` boundaries, slope 0.01, as in W20 and W27. The result line is the validation job's `Bidah 03` dam line. There are no dam objects. Losses come from the project CN grid (`CN_Include_Hill_Area.tif`) unless the table says otherwise. The rain is RP200 with no ARF: the job carries the file as `gridded` and nothing else, as checked. The runs last 30 h, except the PMP runs, where the HMS control file sets 48 h and the dock says so. Pixel products are off. Runs 1g, 2g and 6g have no losses, because a run books rain after losses, and only a lossless run shows the gross rain that the volume rule is about.

| # | Run | Mode | Rain | Losses | Bidah 03 peak, m3/s (time) | Volume past Bidah 03, Mm3 | Water in, m3 | Mass error |
|---|---|---|---|---|---|---|---|---|
| 1 | `full_nc` | full 2D | RP200 NetCDF | CN grid | **661.6** (12.43 h), line | 2.429 | 3,449,023 | 2.3e-8 |
| 2 | `full_dss` | full 2D | RP200 DSS | CN grid | **663.4** (12.43 h), line | 2.438 | 3,460,466 | 2.3e-8 |
| 3 | `hybrid_nc` | hybrid, generated basin, all lumped | RP200 NetCDF | CN grid | **410.2** (12.67 h), network junction; line 0.69 | 2.340 | 737,336 + 2,707,864 | 2.2e-8 |
| 4 | `hybrid_dss` | same | RP200 DSS | CN grid | **411.4** (12.67 h), network junction; line 0.69 | 2.349 | 739,107 + 2,717,576 | 2.2e-8 |
| 1g | `gross_nc` | full 2D | RP200 NetCDF | none | 769.9 (12.38 h), line | 3.160 | 4,503,036 | 2.3e-8 |
| 2g | `gross_dss` | full 2D | RP200 DSS | none | 771.8 (12.38 h), line | 3.169 | 4,514,956 | 2.3e-8 |
| 5 | `pmp_hybrid` | hybrid, HMS route: S13 lumped, other 17 rain-on-grid | `FM_PMP.met` | CN grid; S13 its HMS CN 87.6, Ia 7.2 mm | **1,443.8** (12.83 h), network S13; line 24.4 | 23.72 | 8,711,044 + 23,721,807 | 2.3e-8 |
| 6 | `pmp_full` | full 2D, HMS route, all 18 rain-on-grid | `FM_PMP.met` | CN grid | **1,701.1** (12.16 h), line | 23.08 | 32,448,107 | 2.4e-8 |
| 6g | `pmp_gross` | same | `FM_PMP.met` | none (a CN 100 raster; see below) | 1,707.4 (12.16 h), line | 23.94 | 33,681,352 | 2.4e-8 |

"Water in" is the grid's rain after losses, plus, for a hybrid, what the lumped network put on the grid. A time is hours from the start of the storm. The volume is through the line, or of the network series where the network is the record. Run 6g uses a raster of CN 100 instead of the dock's "No losses": under the HMS route, a rain-on-grid subbasin takes its HMS curve number unless a raster overrides it.

### Which number at Bidah 03 is which

- **Full 2D:** the result line on the grid.
- **Hybrid on the generated basin (3, 4):** the design line became a junction named `Bidah 03`, 19.31 km2 against HMS's 20.97. Its route is *reach R1 to J1*, so its hydrograph travels inside R1 and enters the grid at J1, 2.29 km below the line (`render_basin.png`). **The line on the grid sees only the rain-on-grid around it: 0.69 m3/s against 410.2 in the network.** The run gives no warning; W38's warning covers only lines over inflow cells. The value of record is `series/network_Bidah_03.csv`.
- **PMP hybrid (5):** S13 enters at the icon of HMS's `Bidah 03` junction, **87 m downstream of the dam line**, so the line reads 24.4 m3/s against 1,443.8 in the network. There is no warning here either. The value of record is `series/network_S13.csv`, which equals `network_Bidah_03.csv`.

## The rules, fixed before the runs

| Rule | Mode | Result | |
|---|---|---|---|
| DSS and NetCDF water on the domain within 0.1 % | full 2D | +0.332 % | **FAIL** |
| | full 2D, no losses | +0.265 % | **FAIL** |
| | hybrid (rain + lumped inflow) | +0.333 % | **FAIL** |
| DSS and NetCDF Bidah 03 peak within 0.5 % | full 2D | 661.58 / 663.42, +0.279 % | PASS |
| | hybrid | line 0.688 / 0.689, +0.160 %; network junction 410.16 / 411.39, +0.302 % | PASS (both readings) |
| Mass error under 1e-6 relative | all 9 runs | 2.2e-8 to 2.4e-8 | PASS 9 of 9 |
| Gross rain = the file's depth over the domain within 1 % | NetCDF, 1g | -0.617 % | PASS |
| | DSS, 2g | -0.617 % | PASS |
| PMP: gross rain = raster depth over the domain x pattern total (1.000) x the met's ARF (0.8347) within 1 % | 6g | -0.622 %; without the ARF -17.05 % | PASS |
| A lumped subbasin runs off the SCS excess of its own polygon mean within 1 % | hybrid NetCDF, 8 subbasins | worst 4.5e-7 | PASS |
| | hybrid DSS, 8 subbasins | worst 3.8e-7 | PASS |
| PMP: S13 runs off the raster's polygon mean x ARF | 5 | -1.4e-7 against the cell-centre mean, HMS's way; +0.148 % against the area-weighted mean | PASS |

The other 24 checks are the dock's own: every run finished, both labels read 144 frames of 10 min, the basin was generated with every subbasin lumped, the job carries no ARF, the met is offered, and so on (log lines 1 to 33, less the nine mass checks).

**The failure, with its evidence.** The files differ by +0.2649 % over the domain (`rain_before.json`). The engine's gross rain differs by +0.2647 % (1g against 2g). After CN losses the difference grows to +0.33 %, because the excess is convex in the rain. [Certain] It is a property of the files, not of the engine: the DSS is the NetCDF resampled onto a 2 km grid turned 92°. On a 29 km2 domain that covers 17 pixels, such a resampling cannot hold 0.1 %. The 0.1 % bar assumed the two files held the same rain.

**Why the gross rain reads 0.62 % under the domain.** [Certain] The 199 outlet cells (0.622 % of 31,971) take no rain by design: rain falls on interior cells only. `boundary_cells.py` rebuilds the grid and its boundary cells with the engine, sums the NetCDF over the 31,772 interior cells with h5py, and finds the run's rain equal to it within 8e-10 (`results/boundary_cells.json`). The PMP run shows the same -0.62 %.

**The lumped side is exact.** Each generated subbasin's runoff volume equals the SCS excess of the file's own area-weighted mean over its polygon (CN and area from `basin.json`), to rounding. The polygon means run from 156.0 to 159.7 mm across 2 to 7 pixels. For the depth grid, S13 takes the mean of the raster cells centred in it, as HMS does. That mean, x 0.9749, gives HMS's own logged 1,370.41 mm.

## Reported without a pass mark

### Hybrid against full 2D at Bidah 03

| | Peak | Time | Volume |
|---|---|---|---|
| RP200 NetCDF: hybrid network junction / full 2D line | 410.2 / 661.6 = **0.620** | 12.67 against 12.43 h, **15 min later** | 2.340 / 2.429 Mm3 = 0.963 |
| RP200 DSS | 411.4 / 663.4 = 0.620 | the same | 2.349 / 2.438 = 0.963 |
| PMP: hybrid S13 network / full 2D line | 1,443.8 / 1,701.1 = **0.849** | 12.83 against 12.16 h, **40 min later** | 23.72 / 23.08 = 1.028 |

The generated basin uses the default lag, `kirpich`, HMS-style, at a 2 km2 stream threshold: 8 subbasins, 4 reaches and 5 junctions, with 6.43 km2 reaching the edge without meeting a stream and raining on the grid.

### Against the HMS project at Bidah 03 (`hms_reference.py`, `results/hms_reference.json`)

`FM_200yr.dss` and `FM_PMP.dss`, the run files named in the `.run` file, hold precipitation only, with no flow. HMS's own flows at Bidah 03 are in the depth-area analyses `DA_200yr_B1.dss` and `DA_PMP_B1.dss`. Each runs the FM met with the storm area set to the point's own drainage area, 20.971 km2, where the ARF is 0.9749. **No HMS run without an ARF exists in the project.** The no-ARF figures below are HMS's method recomputed by Wadi2D's lumped engine, which gives HMS's own 454.635 m3/s to 1e-13 when it is given HMS's ARF.

| Bidah 03 | Rain on S13 | Peak, m3/s | Time | Full 2D / it | Hybrid / it |
|---|---|---|---|---|---|
| HMS's own, DA 200yr B1 | 251 x 0.9749 = 244.7 mm | **454.6** | 12.75 h | 1.455 | 0.902 |
| HMS method, 251 mm, **no ARF** | 251 mm | **467.6** | 12.75 h | 1.415 | 0.877 |
| HMS method, **the grid's own rain** over S13, no ARF | 157.1 mm NetCDF / 157.6 mm DSS, the grid's timing | **368.2 / 369.2** | 12.92 h | 1.797 | 1.114 |
| HMS's own, DA PMP B1 | 1,405.65 x 0.9749 = 1,370.4 mm | **1,688.4** | 12.83 h | 1.008 | 0.855 |
| HMS method, the met as written (ARF 0.8347 at 300 km2) | 1,173.3 mm | 1,443.8 (run 5's S13 network itself) | 12.83 h | 1.178 | 1.000 |

The ratios use the NetCDF runs. The fair comparison for the gridded storm is the third row, the same rain through HMS's method. **Full 2D reads 1.80 x it at 200 years and 1.18 x it at PMP.** This test does not explain why the gap shrinks at PMP. It bears on decision 20, and no gauge settles it.

## Found on the way (not checks)

- **Under the HMS route, subbasins switched to rain-on-grid still get network series as if lumped.** In run 5, S1 to S18 except S13 are `2d` in `job.json` and none of them entered the grid: the inflow equals S13's volume to 3 m3. Yet `network_Z4C.csv` shows 9,130 m3/s, `network_S1.csv` 2,662, and so on. The Result lines panel lists them as lumped elements. Evidence: `results/pmp_hybrid/`.
- Every run warns of water standing against the domain edge: 8 to 9 m at (434861, 2723525) at 200 years, and about 20 m at (432071, 2725085) at PMP. This is the Bidah test domain's known edge (W27), and it is not investigated here.
- A depth grid on a *generated* basin is refused by the engine (`run.py`, "a generated basin cannot take one yet"), so the PMP hybrid can only be the HMS route's S13. [Certain, read in the code; not run]

## What he must decide

1. Which RP200 depth governs Bidah 03: the grid's 157 mm or the 251 mm point depth of `FM_200yr.met`.
2. The DSS in SHG Albers: accept 0.27 % from DSS to NetCDF on small domains, or have the DSS written in UTM 40N.
3. The PMP raster: its name says 823 mm and its values say about 1,400 mm over Bidah.
4. The PMP ARF: the met says 300 km2 (0.835), while HMS's depth-area analysis uses the point's own area (0.975 at Bidah 03), 16.8 % more rain. Which one applies to a Bidah 03 design?
5. Hybrid result lines that read nothing: a design line routed through a reach, or a lumped inflow placed below the line, gives no warning. The options are to warn, to enter the flow at the line, or to read the network series in the dock (W38's open question, here on both routes).
6. Network series of subbasins set to rain-on-grid: keep, label or drop.

## Not tested

- Any other return period, any extent other than Bidah 03, and other cell sizes.
- A mesh, a resume, the CPU twin (the default GPU ran), pixel products, the time slider, and the Result lines panel reading the network series.
- HEC-HMS itself on the gridded storm or on the DSS file. The no-ARF HMS figures are recomputed, not HMS's own.
- The generated basin with the NRCS lag, or another threshold.
- Run times: the GPU may have been shared, so none are quoted.

## Rerun

```
powershell -File tests\dock\run_check.ps1 "<absolute path>\W39 gridded 200-yr rain test\dock_gridded.py" <throwaway folder> -Copy "<absolute path>\W39 gridded 200-yr rain test" -LimitMin 60
```

The scenario calls `rain_volume.py` itself through the project venv. When a checkout has no `.venv` (a worktree), it uses `D:\Mojtaba\Renardet\Wadi2D\.venv`, and the engine runs this checkout's code either way. The references and the boundary-cell check run with the venv and `PYTHONPATH` set to the checkout: `hms_reference.py OUT.json`, `boundary_cells.py <run folder> <cache folder>`. The rain files are read in place and never copied.

## Files

- `dock_gridded.py`: the scenario, with its rules as constants. `log_dock_gridded.txt` is its log.
- `rain_volume.py`, `hms_reference.py`, `boundary_cells.py`: the independent figures.
- `results/`: `w39_summary.json` (every number of every run), `rain_before.json` and `rain_after.json`, `hms_reference.json`, `boundary_cells.json`, and per run `job.json`, `done.json`, the line series and the network series.
- `render_*.png`: maximum depth per run with the Bidah 03 line, and the generated basin. `widget_*.png`: the Storm section reading each file and the HMS storm, and the Hydrology section.
