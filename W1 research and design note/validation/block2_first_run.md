# Block 2, first real run of the engine pipeline (2026-11-01)

**Verdict: the pipeline runs end to end on the real 27 GB terrain. 8 h of flood on 564,001 cells took 24 s on the RTX 5080 and 18 s of tables. Flow gathers into the wadis, the water balance closes to 0.026 %, and the discharge at Bidah 03 reaches 96 % of the lumped figure. No validation against HEC-RAS yet; this is a sanity run, not an acceptance run.**

[Certain] for every number below: read from the run folders named here. Interpretation is tagged where it is not.

## Job

`block2_first_run/job.json`: window 426,000-441,000 E, 2,720,000-2,735,000 N (15 x 15 km, both dams inside), 20 m grid, `GGC_2_MERGE_HDSM.tif` read with `pixel_stride` 2 (1 m pixels, 20 per cell side), Manning 0.04, uniform 50 mm/h for 6 h then 2 h dry, CN 85 on every cell, Ia 0.2 S, normal boundary (slope 0.008) on the east and north edges, walls on the other two. Design lines on the two dam axes from `Dams.shp`. No dam object in the terrain: this is the natural ground.

## Numbers

| | |
|---|---|
| Max-depth GeoTIFF | `W1 research and design note\validation\block2_first_run\run\maps\max_depth.tif` |
| Cells, tiles | 564,001, 576 |
| Tables, cold cache | 17.9 s (16.6 s on the very first read of the file); 0.7 s from cache |
| Run wall time | 23.9 s for 28,800 s simulated: 1,200 x real time |
| Steps, dt | 54,696; mean 0.527 s, minimum 0.457 s |
| Step cost | 0.44 ms with maps and live raster, 0.39 ms without (1.45 G cell-steps/s, overhead included; the flat-bed kernel probe gives 2.45 G) |
| Dry-run estimate | cells exact, 0.285 GB on the device, 5.5 s against 24 s: it assumed 2 m and 3 m/s (dt 1.2 s), the kernel probe only, so it reads about 4 x low |
| Rain excess in | 56,743,625 m3 (251.5 mm over 225.6 km2) |
| Out through the boundaries | 53,839,376 m3 |
| Storage at the end | 2,889,529 m3 |
| Balance error | 14,719 m3, **0.026 %** |
| Wet area | 20.8 km2 at mean depth >= 0.1 m, 6.5 km2 at >= 0.5 m, of 225.6 km2 |
| Bidah 03 line | 272.5 m3/s at 6 h |
| Faydh 01 line | 413.3 m3/s at 6 h; part of its catchment lies west of the window |

## Looking at the result

`block2_first_run/run/overview.png`. **Flow gathers.** The wadis come out as continuous threads from the hills, join, and braid on the fan at the east edge. Rain on the hills stays a film of about 2 mm mean depth, the plain's sheet flow collects into channels of 1-2 m.

**Discharge check.** S13 is 20.97 km2. With the same storm, CN 85 and the HMS lag of 53.3 min, the lumped engine gives 283.3 m3/s at 6 h. Rain-on-grid gives 272.5 m3/s, 96 % of it, with both near their plateau. The 2D figure carries storage still filling; the rest may be flow passing the ends of the line [Guessing].

**Sub-grid sensitivity.** The same job with every 0.5 m pixel (`run_full_pixels`): tables 25.3 s, Bidah 272.5 m3/s, Faydh 413.5, wet area 20.7 km2, 99th percentile depth 2.08 against 2.06 m. **`pixel_stride` 2 changed nothing that matters, and full resolution costs only 7 s more.**

**Hybrid mode** (`run_hybrid`): S13 lumped from the HMS basin, its polygon masking the rain, its hydrograph injected at the wadi above the dam: rain 51.44 Mm3, inflow 5.42 Mm3, balance 0.024 %, no instability from a 286 m3/s injection at one point, Bidah line 286.0 m3/s. The polygons, the HMS network and the injection work together on real files.

## Diagnosed

1. **The time step collapsed to 0.24 s on the first attempt, and the cause was mine: fixed.** Normal-boundary cells followed the inner cell's level, so a boundary cell in a pit below a dry neighbour stood at 12-15 m of level with no water, and that set the step for the whole domain. The level now never exceeds the inner cell's depth (`forcing._one_boundary`, with a test). Steps went from 105,394 to 54,696, and all the cells at the velocity cap of 25 m/s went with them.
2. **Water ponds against the closed edges.** The window cuts hill catchments on the south and west sides, so runoff stands up to 33 m deep against the wall: an artefact of the window, not of the solver. With all four edges open (`run_all_edges`, 21.6 s): deepest cell 9.6 m, balance 0.013 %, Bidah unchanged at 272.5 m3/s. Any window job should leave every edge that falls outward open.
3. **Deep water near cell (79, 462), about 435,200 E, 2,733,400 N: 9.6 m mean depth with 8 m/s over the sill.** This is what now sets the time step (dt 0.46-0.65 s). Probably an embankment in the surface model with its culvert missing [Guessing, not checked on the ground]. A burn line or a crest line is the tool if it needs treating.

## What this run did not test

Dam crest lines and spillways on real terrain (synthetic tests only), the ARF study on Block 2, the composite map on a real run (the accumulation raster reads correctly: 20.97 km2 within 10 % at the Bidah line), any comparison with HEC-RAS, and any observed event.
