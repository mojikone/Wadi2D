# W78 domain edge valley check

**Live.** Branch `feature/edge-valley-check` off `feature/fast-products` at `3169935`; not merged, nothing pushed.

The uncomfortable finding first. [Certain] **Faydh 01's 12 m against the edge is not a valley the outline cuts.** At
424,370 / 2,726,845 the outline runs on the catchment divide: the ground stands at about 930 m on the edge and falls
about 120 m within 200 m to the north (into the domain) and about 130 m within 240 m to the south. No stream of even
0.02 km2 crosses the outline within 500 m. The 20 m cells on the outline straddle the divide, their outer pixels fall
south, the wall closes them, and each holds its own rain: 12.9 m in one cell of 400 m2. Faydh has 33 of these bowls
all round its outline, every one one or two cells. Faydh's real pool is elsewhere: 7.8 m deep at 430,996 /
2,733,910, 1.3 km above the outlet, where the edge crosses a side valley (below). Bidah is what the brief guessed: its
old north outlet, made an inflow line, dams the valleys under it.

## What was built

**Before a run** (`wadi2d/edge_valleys.py`, `stream_crossings`): the ground over the domain and 1 km past it (the DEM
where it exists), at 10 m, D8 through breached depressions by the delineation's own WhiteboxTools calls. Every D8 link
across the outline from a pixel draining 0.25 km2 or more is a crossing:

- **stream leaves**: the stream runs out through the edge (or the DEM ends under it) and no `stage`, `normal` or `free`
  line or hand-back is within 150 m. A `flow` line is not an outlet.
- **stream enters**: it runs in from beyond the edge and no `stage` or `flow` line or inflow point is within 150 m. The
  area named is what drains to the edge from outside, as far as the 1 km margin and the DEM reach.

Crossings of one kind within 200 m are one place, the largest named. Each is a warning in the run log (so in the dock's
message) and a point in `edge_checks.gpkg`, layer `edge_streams`. The D8 part is cached in the grid cache, keyed on the
DEM file, the outline and the settings, so an ARF study does it once.

**After a run** (`edge_pools`): closed-edge cells (away from open boundary cells by `EDGE_REACH`, 2 cells, as before)
deeper than `outputs.edge_depth` (3 m, unchanged) are grouped along the edge. For each group, the deepest cell, its
level, the level's spread over the group, the edge length, and the water within `flat_m` of that level joined to it:

- **pool**: level flat within 0.3 m along the edge and at least 5 cells of water at it: the edge dams a valley.
- **bowl**: flat but fewer than 5 cells: edge cells whose ground falls outward past a divide.
- **deep water**: the level slopes along the edge: water running along the wall.

Two stretches of edge holding the same water are one pool. Warnings list pools first, then deep water, then bowls, 10 of
each kind, the rest counted; each opens with the old words, "water stood X m deep against the domain edge at (x, y)".
Layer `edge_pools` in the same file. With the check off, on a quadtree run, or if it fails, the old single
deepest-cell warning stands exactly as before.

**Dock**: after a run, the two layers go on top of the model's Inputs > Boundaries (slot `edge checks`), styled by kind
(red triangle leaves, orange triangle enters, blue pool, purple deep water, grey bowl); the next run of the model takes
them away before it starts; a clean run adds none (`plugin/wadi2d_qgis/edge_layers.py`).

**Settings**, `outputs.edge_check`, off the job hash (a checkpoint survives a change):

| Field | Default | Meaning |
|---|---|---|
| `enabled` | true | both checks |
| `stream_km2` | 0.25 | a stream draining this much at a closed edge is named; 0.5 missed Faydh's side valley (0.28 km2) |
| `pixel_m` | 10 | pixel of the analysis, rounded to whole DEM pixels |
| `beyond_m` | 1000 | ground read past the domain |
| `max_pixels` | 6,000,000 | the pixel doubles until the window fits |
| `line_reach_m` | 150 | a line or inflow point this close opens the crossing (a boundary's own `snap_m` default) |
| `cluster_m` | 200 | crossings of one kind this close are one place |
| `flat_m` | 0.3 | level spread along the edge within which deep water is flat |
| `pool_cells` | 5 | cells of water at the level that make a pool rather than a bowl |
| `max_listed` | 10 | places named one by one, of each kind |

## Results on the two known spots

Pre-run on the jobs themselves (`probe_crossings.py`, `logs/crossings.json`); post-run on Bidah through `run_job` on the
CPU, on Faydh from W11's 20 m squares run, the same domain and DEM as W56's (`probe_pools.py`, `logs/pools.json`).

| Job | Before the run | After the run | Ground there |
|---|---|---|---|
| Bidah, W61's job (outlet 2's middle half a flow line), 20 m | **leaves** 4.01 km2 at (438561, 2728700), 0.43 km2 at (439281, 2728700), 1.01 km2 at (437791, 2728700), 0.27 km2 at (440081, 2728700); 5 entries, below | **pool** 4.3 m at **(439416, 2728690)**, the W75 spot to the metre, level 77.00 m flat within 0.00 m, 100 m of edge, 0.034 km2 of water | 10 m inside the north edge the ground has two valley floors, 75.7 to 78 m at x 438,400 to 438,600 and 73 to 75 m at 439,250 to 439,550, between banks and a spur of 80 to 91 m, and falls to 66.5 m at 439,700; the pool stands over the second floor, the flow line on both |
| Bidah, the same with outlet 2 free its whole length | no leaves; 5 entries, below | **nothing** | |
| Faydh 01, W56's job | **leaves** 0.28 km2 at (431006, 2733905); enters 1.26 km2 at (431591, 2733860) and 0.54 km2 at (432121, 2732940) | **pool** 7.8 m at (430996, 2733910), level 213.50 m flat, 300 m of edge, 0.041 km2; pools of 6.2 m at (432116, 2733850) and 5.6 m at (431616, 2732950); **33 bowls**, the deepest 12.9 m at **(424376, 2726850)**, the W56 spot | at 431,006 the edge crosses a side valley floored at 206 m that runs on east past it; at the W56 spot, the divide (above) |

Both of Bidah's checks find the W75 pool: the pre-run crossing at 439,281 is 135 m from its deepest cell, under the
flow line, which is not an outlet. Faydh's W56 spot is found after the run as a bowl, and not before it, because there is
no stream there.

[Likely] **Bidah's five entries are real by D8 but by the dam job's design**: 3.41 km2 at (437300, 2727855), 2.48 at
(438821, 2725700), 1.01 at (438021, 2725700), 0.83 at (437300, 2728315), 0.74 at (439021, 2725700), across the
domain's west and south notches. At the first the ground is a valley about 150 m wide at 93.7 to 95.7 m between sides of
101 to 108 m, falling into the domain. `domain_Bidah03` is a reservoir window fed by one inflow point at
(438300, 2726860), more than 150 m from all of them, so the check names them. Not judged further.

A clean job reports nothing: Bidah with outlet 2 open reports no stream leaving and no water against the edge; the
synthetic valley with its outlet line reports nothing before or after a run, and writes no file (tests below).

Time: the D8 part on Faydh 15 s the first time (the 0.5 m DEM read over 15 by 12 km), from the cache after; Bidah 0.6 s.

## Tests

- `tests/engine/test_edge_valleys.py`, 13 tests: a valley 2 km wide falling 2 % south, on 5 m pixels. Leaving through
  a closed edge named at the thalweg with 3.0 km2; an outflow line makes it clean; a flow line does not; entering from
  beyond named with the 1.0 km2 north of the domain; a stream leaving where the DEM ends says so; the threshold and the
  switch; the cache. A flat pool once, a single cell a bowl, sloping deep water not a pool, water at an open boundary
  not listed. Two CPU runs through `run_job`: the closed valley names the stream before and a pool after, both in the
  file; with its outlet open, no warning and no file. `tests/engine/test_block2_findings.py` (the old `edge_ponding`)
  unchanged and passing.
- `tests/plugin/test_edge_qgis.py` on QGIS 3.44.8's Python: the engine's file lands as two styled layers in Inputs >
  Boundaries; the model's next run clears them; a clean run adds none. `tests/plugin` whole: 562 passed (with the
  frozen schema sample regenerated for `outputs.edge_check`).

## Not done

- No real dock click-through scenario; the dock part is tested on QGIS's Python, not through the dock's Run button.
- No GPU run (not needed); the Faydh post-run read W11's 20 m run's maps, not a new run.
- No dock controls for the settings: job fields only.
- A quadtree run keeps the old single warning; the pre-run check runs on it.
- Bidah's five entries and Faydh's two entries near the outlet: not judged against what the domains were drawn for.

## Files

- `probe_crossings.py`: the pre-run check on Faydh 01 and Bidah, with ground sections at the nearest crossing;
  `logs/crossings.json`.
- `probe_pools.py <runs folder>`: the post-run check on Faydh's W11 maps and two Bidah CPU runs (W61's job, and outlet 2
  free); `logs/pools.json`. The run folders went to a scratch folder and are not kept.
