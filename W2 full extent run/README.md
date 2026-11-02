# W2 full extent run

**Status (2026-11-01): live. The full project boundary, 15,398 km2, at 30 m with 5 m terrain inside the tables, Block 2's 200-yr storm.** Engine at `eb8583a`.

| Input | Value | Why |
|---|---|---|
| Boundary | `Project Boundary Actual extent.shp`, from `06-WORKING\04-Hydraulic\00 Data\SHP\Project Boundary` | His approval, 2026-11-01. The copy of that name in `03-Hydrology\GIS\SHP` is empty |
| Terrain | `terrain/NSA5_COP30_blend.tif`, NSA 5 m, Copernicus 30 m in its gaps (701 km2) | His instruction. `s01_terrain.py`; results in `terrain/blend_qa.json` |
| Cell | 30 m, 6 NSA pixels | The finest that fits the 16 GB card: 17.1 M cells, 8.7 GB by `--dry-run`. 20 m needs about 20 GB |
| Storm | 251.0 mm, 24 h, pattern FM 10-1000yr, storm area 300 km2, ARF FM | `FM_200yr.met`, uniform over the extent, his instruction. It is Block 2's storm, not the rain of the other blocks |
| Losses | Project CN grid, 88 where it has no value (24 km2) | Same grid as Block 2 |
| Manning | 0.05 everywhere | The n of the HEC-RAS head-to-head. The hill and wadi rasters exist for Block 2 only |
| Outlets | Normal depth at S 0.003 along 248 km of edge on ground of 5 m or less | The coast. Every other edge is a wall |
| Duration | 36 h | As the Block 2 10 m run |

Rerun from this folder with the project venv: `s01_terrain.py`, `s02_job.py`, then `wadi2d run jobs\full_30m_200yr.json --out runs\full_30m_200yr`. `terrain\`, `runs\` and `cache\` stay out of git.

The project's own 200-yr rain grid, `RBF_C_P200_2 zone_V6.tif`, ranges from 127 to 468 mm over this boundary and was not used, on his instruction.

## Results (run finished 2026-11-01)

| Measure | Value |
|---|---|
| Run | 17.1 M cells, 370,915 steps, 68.3 min on the RTX 5080, tables 2.3 min, 8.7 GB by `--dry-run`, 10.9 GB in use on the card |
| Water | Excess 2,697 Mm3, out at the coast 2,342 (87 %), still on land at 36 h 355 (13 %), mass error 3.9e-8 |
| Mean depth over 0.1 / 0.5 / 1 / 3 m | 5,019 / 2,590 / 1,195 / 184 km2 |
| Peaks at the Block 2 dams, m3/s | Faydh 01 1,920, Bidah 03 601, R5A 1,960, R2A 3,065, Z4C 2,786 |

- **Against his 200-yr layer**, inside the 1,730 km2 of that raster's frame, 3 m depths averaged to 30 m with dry pixels as dry: over 0.3 m he has 225 km2, Wadi2D 299, both 150, F 0.40. Where both are over 0.5 m, Wadi2D less his is -0.11 m in the median, -1.35 to +0.88 m (5 to 95 %). The inputs differ (rain, terrain, n, cell size, whatever his model held); the cause was not isolated.
- **Not a design result.** One uniform storm from Block 2 over 200 km of coast, n 0.05 everywhere, no structures, no road embankment culverts, 30 m cells. Peaks here are not comparable with HMS without a run at each point's storm area.
- **Walls.** 423 of 36,062 closed edge cells hold over 3 m, 34 over 10 m, largest 31.5 m at (529,070, 2,566,250). Pockets where gullies meet the polygon, not real water.
- **36 h was short.** 13 % of the excess was still on land; part of that is real ponding behind embankments, the split was not measured.
- **Maps** are stored every 6 h, so the run cannot make a flood animation.
- **Sub-grid.** Yes: 16-row tables built from the 5 m pixels, 6 x 6 in each 30 m cell, sheet flow on (`config.resolved.json`).

## Hazard (AIDR H1 to H6)

`s05_hazard.py` uses the limits and the rule of the Majlas dam-break script (`Dam Breack\W2\01_scripts\ras_results.py`, `data_facts.py`): a cell takes the highest class any threshold gives, floor 0.05 m. `hazard.tif` holds depth x speed at one moment, updated every 4 steps, so a class from the three maxima equals the worst class over the flood; no time series is needed. His limits are the standard ones.

| km2 | H1 | H2 | H3 | H4 | H5 | H6 |
|---|---|---|---|---|---|---|
| Delivered map, depth above the cell's low point | 379 | 922 | 893 | 974 | 1,941 | 875 |
| Same test on cell-mean depth, D x V scaled to it | 2,087 | 865 | 360 | 717 | 1,441 | 515 |

- **The map reads high on steep ground.** The depth is the level above the lowest of 36 pixels. The second row is an estimate of the spread, not a substitute: D x V cannot be redone after the run.
- **Odd values.** 707 m of depth is one cell, an NSA pit 660 m below its neighbours, at (508,130, 2,579,660). 137 cells exceed 50 m. Speed reaches 24.9 m/s against the 25 m/s cap, and 0.2 km2 exceeds 15 m/s. Neither moves the class areas. The deep cells at (512,630, 2,583,500), mean depth about 58 m at level 1,014 m, were not explained.
- **Maps:** `Wadi2D_full_extent_MAX_DEPTH.jpg`, `Wadi2D_full_extent_HAZARD_H1-H6.jpg`, one image pixel per cell. Hazard is shown opaque, his layer's colours at 100 %: his 35 % opacity is unreadable on white.

## Hazard at the 5 m pixel (rerun with maps every 5 min)

`runs/full_30m_200yr_5min`: 432 frames, 72 GB, 112 min, same steps and balance as the first run. `s06_pixel_hazard.py` takes pixel depth from the cell's level less the pixel's ground and interpolates speed to the pixel from wet cell corners, then updates max depth, max speed and max depth x speed per pixel at each frame, on the GPU: 239 M pixels, about 5 min. Classes as the Majlas script. **Supersedes the cell hazard above.**

| km2 | H1 | H2 | H3 | H4 | H5 | H6 |
|---|---|---|---|---|---|---|
| Pixel method, 5-minute frames | 975 | 784 | 397 | 708 | 1,170 | 436 |
| Cell method, low-point depth, superseded | 379 | 922 | 893 | 974 | 1,941 | 875 |

- A peak between frames is missed: at most 5 min, not measured. Max speed 22.5 m/s against 24.9 in the run's maxima.
- Water level is flat per cell here, so on steep channels a pixel at the low end of a cell reads high (the freeboard sawtooth).
- A first version of `s06` had a wrong axis in the interpolation weights; 52.7 m/s against the run's cap gave it away. Fixed, with an assertion that the weights sum to 1. Maps built before the fix were not issued.
- `Wadi2D_full_extent_PIXEL_HAZARD_H1-H6.jpg` and `_PIXEL_DEPTH.jpg` show the 5 m rasters lifted to 20 m by maximum, so thin channels stay visible at map scale. The 5 m rasters are `terrain/pixel_hazard_5m.tif` and `terrain/pixel_depth_5m.tif`.

## Sloped water surface and the film

`s06_pixel_hazard.py` now slopes the surface inside a cell: level at each cell corner is the mean of the wet neighbours within `LEVEL_JUMP`, 2 m, so it follows connected flow and is not carried over a bank. A flat level per cell gave a regular stipple of false wet pixels at the low end of each cell on any slope, visible in the first film preview. **This supersedes the flat table above.** Issued maps: `Wadi2D_full_extent_PIXEL_HAZARD_H1-H6.jpg`, `Wadi2D_full_extent_PIXEL_DEPTH.jpg`; rasters `terrain/pixel_hazard_sloped_5m.tif`, `terrain/pixel_depth_sloped_5m.tif`.

| km2 | H1 | H2 | H3 | H4 | H5 | H6 |
|---|---|---|---|---|---|---|
| Flat level | 975 | 784 | 397 | 708 | 1,170 | 436 |
| Sloped level | 989 | 777 | 392 | 709 | 1,170 | 438 |

Class areas move under 2 %. 146 km2 is wet only when sloped, 141 km2 only when flat, median depth there 0.11 m; 86 % of pixels wet in both keep their class.

Dry freeboard, synthetic channel 45 m wide on 30 m cells (`s09b_freeboard.py`), share of bank pixels falsely wet, and largest surface error in the channel:

| Bed slope, freeboard | Flat | Sloped |
|---|---|---|
| 1 %, 0.2 m | 0 %, 0.13 m | 0 %, 0.06 m |
| 5 %, 0.3 m | 2.2 %, 0.62 m | 0 %, 0.29 m |
| 5 %, 0.6 m | 0 %, 0.62 m | 0 %, 0.29 m |
| 10 %, 1.0 m | 1.1 %, 1.25 m | 1.1 %, 1.25 m |
| 10 %, 2.0 m | 0 %, 1.25 m | 0 %, 1.25 m |

At 10 % the step between 30 m cells is 3 m, over the 2 m guard, so nothing is interpolated: the guard should scale with slope. A straight synthetic channel only; no designed channel was tested, and a slope across a bend is untested.

`s08_video.py`: `Wadi2D_full_extent_flood_hazard.mp4`, 80 s, 1920 x 1080, 30 fps, 283 MB, hour 3.5 to 30, hazard class at each moment from the 5-minute frames blended in time, over Google satellite hybrid fetched by `s08b_background.py`, `s08c_base_patches.py` and `s08d_low.py`. Drawn by this script on the GPU, not inside QGIS. Depth under 0.1 m is left out of the picture. Google imagery: for internal use; check the terms before any public or client use.
