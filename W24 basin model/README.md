# W24 basin model (D6a)

[PRESERVE-CHECK]

KEEP, not touched:
- `wadi2d/forcing.py`, `wadi2d/run.py`, everything under `plugin/`: left to D5 and the next piece.
- `RunConfig` and its JSON Schema: no new field, so `tests/plugin/schema_sample.json` stays as it is and an old job
  is byte-identical in its resolved config, its grid key and its checkpoint hash.
- `wadi2d/mesh/streams.py`, the mesher, the lumped engine and the reservoir classes: reused, unchanged.

CHANGE:
- New package `wadi2d/basin/`: delineation on the job's DEM and domain, the network, terrain parameters, reservoirs, the
  `basin.json` contract, `basin.gpkg`, the loader into `wadi2d/hydrology/model.py`, the junction routes.
- `wadi2d/engine/cli.py`: one new subcommand, `wadi2d basin JOB --out FOLDER`. Nothing else in the file moves.
- `wadi2d/config/schema.py`: one new class, `BasinSettings`. It is not a field of `RunConfig`; it holds the defaults of the
  command, so each is set once.
- Nothing is removed; nothing existing changes behaviour.
- Base corrected on the coordinator's word: rebased onto local `main` (`0c540e4`), which holds D2, D8, D1 and D5.

FILES: `wadi2d/basin/*` (new), `wadi2d/engine/cli.py` (`_basin`, one subparser), `wadi2d/config/schema.py` (`BasinSettings`),
`tests/basin/*` (new), `W24 basin model/*` (new).

## State (2026-11-02, branch `feature/basin-model`, on local `main` at `0c540e4`)

**The terrain side of the basin model reads what HMS reads: drainage at the five dams within 0.2 %, Bidah -4.2 %, subbasins, flow lengths, reach lengths and slopes within about 1 %. The peaks do not follow, 1.05 to 1.58 x HMS at 100 yr, and the cause is one parameter: the lag.** HMS's lags are not NRCS lags. All 18 equal 0.474 x Kirpich on the longest length and the 10-85 slope, to 0.3 %. Take that rule on the generated terrain and the peaks fall to 0.88 to 0.98 x HMS. This is D6a only: data and a loader. Nothing here is in the dock, so by his rule it is not a feature yet.

Live. Nothing here supersedes an earlier iteration; the lag finding adds to `W1 ... block2_full.md` and to decision 20.

## What it is

```
wadi2d basin JOB --out FOLDER [--threshold-km2 T] [--pour-points LAYER] [--pixel P] [--settings FILE]
```

Reads the job's DEM, domain, CN raster, Manning, dams and design lines; writes `basin.json` and `basin.gpkg`. 17 s for 811 km2 at 5 m, no GPU. `--threshold-km2 0` breaks at the pour points only. A rerun into the same folder keeps every name whose outlet has not moved, and the old file stays as `basin.previous.json`.

| Module in `wadi2d/basin/` | Job |
|---|---|
| `delineate.py`, `kernels.py` | Analysis raster, WhiteboxTools through `mesh/streams.py`, D8 as flat arrays, numba walks |
| `pour.py`, `network.py` | Pour points, links, nodes, catchments |
| `parameters.py`, `sections.py`, `reservoirs.py` | NRCS lag, zonal means, cross-sections, the pool behind a dam |
| `elements.py`, `contract.py` | The elements of `basin.json`, sources, `missing`, `refresh` |
| `loader.py`, `routes.py`, `layers.py`, `build.py` | Into `hydrology/model.py`, junction routes, `basin.gpkg`, the command |

What the owner's rules ask of the next piece: `load_network(model, skip_incomplete=True)` holds what can run; an incomplete reach cuts the network there, so the element above is an outlet of the lumped network. `junction_routes(model)` gives each junction `route` (`reach` or `none`), `reach`, `next_junction`, `reach_missing`. A reservoir counts as a junction there.

### basin.json

Top level: `format`, `format_version`, `name`, `crs`, `geometry_file`, `inputs`, `settings`, `analysis` (pixel, window, `ground_km2`, `unassigned_km2`), `elements`, `notes`. `basin.json` is the record; the columns of `basin.gpkg` only show it, and geometry is found by `layer` and `name`. Sources: `terrain`, `raster`, `job`, `derived`, `user`, `missing`.

```json
{"kind": "subbasin", "name": "S1", "downstream": "J1", "outlet": [443498.49, 2710482.89],
 "geometry": {"layer": "subbasins", "name": "S1"},
 "parameters": {"area_km2": {"value": 5.4152, "source": "terrain"},
  "flow_length_m": {"value": 6026.42, "source": "terrain"},
  "slope": {"value": 0.31317, "source": "terrain"},
  "flow_path_slope": {"value": 0.017963, "source": "terrain"},
  "slope_10_85": {"value": 0.008755, "source": "terrain"},
  "curve_number": {"value": 87.18, "source": "raster"},
  "lag_minutes": {"value": 29.06, "source": "derived"}},
 "missing": []}

{"kind": "reach", "name": "R1", "downstream": "J9", "outlet": [438233.49, 2736197.89],
 "geometry": {"layer": "reaches", "name": "R1"},
 "parameters": {"length_m": {"value": 10208.36, "source": "terrain"},
  "slope": {"value": 0.011974, "source": "terrain"},
  "manning_n": {"value": 0.1, "source": "job"},
  "bottom_width_m": {"value": 19.73, "source": "terrain"},
  "side_slope": {"value": 6.31, "source": "terrain"},
  "index_celerity": {"value": 3.394, "source": "derived"},
  "section": {"value": {"depth_m": [0.5, 1.0, "..."], "width_m": [20.0, 30.0, "..."],
                        "stations": 102, "open_ground": false}, "source": "terrain"}},
 "missing": []}

{"kind": "junction", "name": "J1", "downstream": null, "outlet": [443498.49, 2710482.89],
 "geometry": {"layer": "junctions", "name": "J1"},
 "parameters": {"drainage_area_km2": {"value": 216.952, "source": "terrain"}}, "missing": []}

{"kind": "reservoir", "name": "Z4C", "downstream": "R13", "outlet": [440973.49, 2710482.89],
 "geometry": {"layer": "junctions", "name": "Z4C"},
 "parameters": {"drainage_area_km2": {"value": 211.5368, "source": "terrain"},
  "crest_elevation_m": {"value": 188.84, "source": "job"},
  "elevation_m": {"value": [149.414, 149.914, "..."], "source": "terrain"},
  "area_m2": {"value": [25.0, 1450.0, "..."], "source": "terrain"},
  "volume_m3": {"value": [0.0, 266.9, "..."], "source": "terrain"},
  "spillways": {"value": null, "source": "missing"},
  "initial_elevation_m": {"value": null, "source": "missing"}},
 "missing": ["spillways", "initial_elevation_m"],
 "pour_point": {"kind": "dam", "x": 440973.49, "y": 2710482.89, "line": null, "line_km2": null, "aliases": []}}
```

A dam with a spillway object has `"spillways": {"value": [{"crest_elevation_m": 230.0, "crest_length_m": 207.0, "coefficient": 2.1, "outlet": 0}], "source": "job"}` and an `initial_elevation_m` at the lowest spillway crest, `derived`.

`missing` names what stops an element running lumped: subbasin `area_km2`, `curve_number`, `lag_minutes`; reach `length_m`, `slope`, `manning_n`, `bottom_width_m`, `side_slope`, `index_celerity`; reservoir `elevation_m`, `area_m2`, `spillways`, `initial_elevation_m`. It is rebuilt on every read. A user who fills a null gets that value marked `user`, and the lag or celerity that follows is computed. A number that is there is never overwritten: to recompute a lag after changing a CN, set the lag to null.

## Rules the first Block 2 run forced

- **A dam stops every stream across its axis.** The largest pixel alone read R5A at 93 km2 and R2A at 105 km2 against HMS's 117 and 176, because those axes cross several wadis and HMS has wall layers. The whole crest line now drains to its largest pixel. This changes the D8 lines upstream of the dam only.
- **A design line stops nothing.** Each stream of the threshold it crosses gets its own node, `Name`, `Name 2`, and each keeps its way. `pour_point.line_km2` holds everything crossing the line, small streams included.
- **A crest line is a dam by its own drainage, not by the threshold.** Under `dam_min_km2`, 1 km2, it is a saddle: no node, a note.
- **The schema's default Manning 0.035 does not count as a value of the job.** Only a Manning the job sets, or the raster, does; otherwise `manning_n` is missing.

## Validation, Block 2, against numbers known without it

Terrain `GGC_2_MERGE_HDSM_5.tif`, the 5 m raster HMS's polygons sit on; `domain.geojson` of `W1`, 810 km2; project CN raster; `Mannings n` 0.1 on all reaches, HMS's own value, used unchanged and not fitted. The 100-yr storm, HMS's step, each site at its own storm area. Nothing was tuned. All numbers are in `results/validation.json` and `results/dams.json`; `scripts/tables.py` prints them.

**As a user would:** threshold 10 km2, the five axes as crest lines (`jobs/block2.json`): 41 subbasins, 18 reaches. **Aligned:** pour points at the outlets of the 18 HMS polygons and no threshold, so each HMS element has a generated twin.

### Drainage area

| Site | HMS km2 | Generated km2 | % | As a design line: nodes, their sum km2 | Across the line km2 |
|---|---|---|---|---|---|
| Faydh 01 | 74.30 | 74.43 | +0.2 | 1, 73.86 | 74.43 |
| Bidah 03 | 20.97 | 20.09 | **-4.2** | 1, 19.31 | 20.09 |
| R5A | 117.10 | 117.12 | +0.0 | 2, 106.50 | 117.12 |
| R2A | 175.87 | 175.92 | +0.0 | 2, 172.63 | 175.92 |
| Z4C | 211.09 | 211.54 | +0.2 | 1, 210.28 | 211.54 |

[Certain] Bidah's -4.2 % is the part of the S13 polygon past the axis, the same 4 % `W1` read from a closed ring. The generated number is what crosses the axis; HMS's polygon is the larger one. Which is right for the dam is his call.

### Peak at 100 yr, ratio to HMS, time h

| Threshold km2 | Subbasins, reaches | Faydh 01 | Bidah 03 | R5A | R2A | Z4C |
|---|---|---|---|---|---|---|
| HMS | 18, 8 | 994 at 13.25 | 362 at 12.75 | 887 at 14.75 | 1356 at 14.25 | 1666 at 15.58 |
| 5 | 87, 39 | 1.41, 12.67 | 1.22, 12.67 | 1.28, 13.42 | 1.63, 13.25 | 1.20, 15.17 |
| **10** | **41, 18** | **1.45, 12.67** | **1.05, 12.58** | **1.46, 13.33** | **1.58, 13.25** | **1.18, 15.25** |
| 20 | 17, 8 | 1.32, 12.67 | 1.05, 12.58 | 1.44, 13.50 | 1.53, 13.08 | 1.23, 15.17 |
| 40 | 15, 7 | 1.32, 12.67 | 1.05, 12.58 | 1.44, 13.50 | 1.49, 13.25 | 1.23, 15.17 |

[Certain, measured] The threshold moves a peak by up to 0.18 x HMS. Subdividing a catchment changes the answer, because the NRCS lag is not additive over subbasins.

### Which parameter hurts: the aligned model with one family taken from HMS

| Taken from HMS | Faydh 01 | Bidah 03 | R5A | R2A | Z4C |
|---|---|---|---|---|---|
| Nothing, all generated | 1.40 | 1.05 | 1.27 | 1.53 | 1.23 |
| CN | 1.40 | 1.05 | 1.27 | 1.53 | 1.23 |
| Reaches | 1.43 | 1.05 | 1.42 | 1.60 | 1.43 |
| Lag | 0.98 | 0.96 | **0.88** | 0.98 | 0.95 |
| Lag and reaches | 1.00 | 0.96 | 0.98 | 1.01 | 1.00 |
| Lag, CN and reaches | 1.00 | 0.96 | 0.98 | 1.01 | 1.00 |
| Diagnosis: 0.474 Kirpich on the generated L and 10-85 S | 0.98 | 0.96 | 0.88 | 0.98 | 0.95 |

- **Lag: the whole gap.** [Certain] With HMS's lags every site comes under 1.0. CN does nothing.
- **Sections: the second error, 10 points at R5A.** [Certain] With HMS's lag the generated trapezoids read 0.88 at R5A and 0.95 at Z4C; HMS's own read 0.98 and 1.00. They attenuate more, which partly hides the lag error in the top row.
- **Area:** with all parameters from HMS the rest is 0.96 at Bidah, the -4.2 % above, and 0.98 to 1.01 elsewhere.
- **What HMS's lags are.** [Certain, arithmetic] A free fit of ln lag on ln L and ln S 10-85 gives exponents 0.770 and -0.386, Kirpich's 0.77 and -0.385, rms 0.13 %. Lag / Kirpich is 0.473 to 0.476 on all 18. Where 0.474 comes from is not in the files; the textbook lag ratio is 0.6. The diagnosis row is not a setting of the model: it shows the terrain can carry that rule, not that the rule is right.
- **The NRCS lags sit on the 2D response, not on HMS.** [Certain for the numbers] `W1`'s equivalent lags of the 2D model, from hills 0.05 to n 0.1 everywhere, against NRCS on terrain: S1 45-65 / 56, S2 44-61 / 48, S5 40-57 / 61, S6 21-37 / 40, S11 27-41 / 41, S14 41-57 / 43. Two sit just above the range. Two methods agreeing is not a gauge; this says nothing on which is right (decision 20).

### Subbasins, aligned

| HMS | Twin | IoU | Area HMS, km2 | Area | CN HMS | CN | Lag HMS, min | NRCS lag | L HMS, m | L | 10-85 HMS | 10-85 | Land slope HMS | Land slope |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| S1 | S22 | 0.999 | 59.08 | 59.11 | 90.7 | 90.68 | 112.0 | 55.77 | 26164 | 26343 | 0.01707 | 0.01689 | 0.689 | 0.683 |
| S2 | S23 | 0.999 | 44.39 | 44.42 | 90.9 | 90.89 | 102.0 | 48.25 | 22926 | 22934 | 0.01655 | 0.01658 | 0.723 | 0.718 |
| S3 | S4 | 1.000 | 87.60 | 87.63 | 90.0 | 90.01 | 157.0 | 79.35 | 36721 | 36686 | 0.01388 | 0.01392 | 0.606 | 0.606 |
| S4 | S3 | 0.979 | 20.02 | 20.38 | 86.7 | 86.72 | 64.4 | 55.32 | 11551 | 11558 | 0.01390 | 0.01391 | 0.253 | 0.253 |
| S5 | S18 | 1.000 | 73.87 | 73.87 | 90.8 | 90.85 | 127.0 | 60.82 | 32260 | 32298 | 0.01848 | 0.01847 | 0.791 | 0.785 |
| S6 | S28 | 1.000 | 24.63 | 24.63 | 90.5 | 90.53 | 65.5 | 39.76 | 16586 | 16573 | 0.02745 | 0.02749 | 0.646 | 0.649 |
| S7 | S26 | 1.000 | 37.66 | 37.66 | 87.5 | 87.55 | 75.1 | 51.38 | 14859 | 14846 | 0.01543 | 0.01542 | 0.410 | 0.412 |
| S8 | S27 | 1.000 | 5.08 | 5.08 | 86.8 | 86.84 | 55.9 | 45.87 | 9965 | 9971 | 0.01493 | 0.01493 | 0.287 | 0.288 |
| S9 | S11 | 1.000 | 30.78 | 30.78 | 88.0 | 87.97 | 101.0 | 66.02 | 21651 | 21604 | 0.01533 | 0.01539 | 0.439 | 0.441 |
| S10 | S7 | 0.833 | 3.85 | 3.29 | 86.1 | 86.06 | 37.3 | 53.31 | 5105 | 4514 | 0.01123 | 0.01412 | 0.061 | 0.064 |
| S11 | S25 | 1.000 | 41.47 | 41.46 | 90.8 | 90.83 | 78.2 | 41.21 | 19738 | 19753 | 0.02452 | 0.02431 | 0.783 | 0.779 |
| S12 | S19 | 0.986 | 32.84 | 32.39 | 90.5 | 90.51 | 67.8 | 41.38 | 16940 | 16917 | 0.02615 | 0.02613 | 0.613 | 0.620 |
| S13 | S30 | 0.957 | 20.97 | 20.09 | 87.6 | 87.65 | 53.3 | 45.61 | 11874 | 11800 | 0.02405 | 0.02418 | 0.344 | 0.360 |
| S14 | S24 | 1.000 | 42.30 | 42.30 | 91.1 | 91.05 | 93.5 | 43.23 | 21621 | 21606 | 0.01851 | 0.01853 | 0.810 | 0.802 |
| S15 | S15 | 1.000 | 38.89 | 38.89 | 90.3 | 90.31 | 85.5 | 47.16 | 19384 | 19390 | 0.01878 | 0.01874 | 0.601 | 0.603 |
| S16 | S31 | 0.600 | 22.36 | 13.42 | 87.0 | 87.28 | 70.0 | 49.21 | 13772 | 12685 | 0.01596 | 0.01691 | 0.300 | 0.357 |
| S17 | S13 | 1.000 | 11.89 | 11.89 | 87.5 | 87.47 | 53.0 | 43.70 | 11373 | 11365 | 0.02237 | 0.02242 | 0.369 | 0.374 |
| S18 | S10 | 0.157 | 1.67 | 10.62 | 86.4 | 86.54 | 31.5 | 44.43 | 4242 | 7753 | 0.01206 | 0.01857 | 0.136 | 0.210 |

NRCS over HMS lag: 0.46 to 0.86, median 0.61, on the 15 subbasins that are the same catchment. S16 and S18 share one mouth at the R5A axis: 24.03 km2 in HMS, 24.04 here, split differently because an outlet here is the largest pixel in a polygon and HMS's walls draw the line elsewhere. S10 has the same cause at R2A. These three say nothing against the terrain measures.

### Reaches, aligned

A generated reach counts for an HMS reach when most of it lies within 30 m of the HMS line.

| HMS | Twin | L HMS, m | L | % | S HMS | S | % | b HMS, m | b | z HMS | z |
|---|---|---|---|---|---|---|---|---|---|---|---|
| R1 | R13 | 26009.0 | 25947.2 | -0.2 | 0.01241 | 0.01244 | +0.2 | 60 | 18.0 | 0.7 | 5.7 |
| R2 | R11 | 8348.0 | 8359.6 | +0.1 | 0.00931 | 0.00929 | -0.2 | 100 | 22.0 | 1.5 | 8.9 |
| R3 | R10 | 14552.3 | 14490.7 | -0.4 | 0.01162 | 0.01171 | +0.8 | 60 | 21.3 | 1.5 | 3.8 |
| R4 | R9 | 9427.6 | 9428.3 | +0.0 | 0.01485 | 0.01483 | -0.1 | 100 | 37.1 | 2.0 | 16.3 |
| R5 | none | 659.6 | | | 0.00945 | | | 100 | | 5.0 | |
| R6 | R2 | 4259.5 | 4227.9 | -0.7 | 0.01474 | 0.01495 | +1.4 | 50 | 12.1 | 1.0 | 5.9 |
| R7 | R4 | 17006.9 | 16999.3 | -0.0 | 0.01523 | 0.01522 | -0.1 | 50 | 16.6 | 1.0 | 6.3 |
| R8 | R5 | 7765.3 | 7751.7 | -0.2 | 0.01100 | 0.01104 | +0.4 | 70 | 26.0 | 3.0 | 7.1 |

Length and slope are the same measure on the same raster. The section is not: generated bottoms are a quarter to a third of HMS's and side slopes two to eight times flatter. The fit runs over 4 m of depth with the bed as the lowest ground, so it reads a narrow low-flow channel in a wide bed; HMS's trapezoids are a judgement of the wadi. Neither is checked against a surveyed flood section [Likely the generated one is a poor fit above the low-flow channel]. R5, 660 m, has no twin: the J6 to J7 stretch falls inside other links. HMS's reach parameters were left out for it in the attribution.

### Reservoirs, on the NSA 5 m terrain of the dam levels

| Dam | Level | Volume, EAV Mm3 | Generated | % | Area, EAV km2 | Generated | % |
|---|---|---|---|---|---|---|---|
| Faydh 01 | FSL 230 | 17.150 | 17.154 | +0.0 | 0.941 | 0.972 | +3.3 |
| Faydh 01 | Crest 235 | 22.469 | 22.539 | +0.3 | 1.149 | 1.184 | +3.1 |
| Bidah 03 | FSL 100 | 5.668 | 5.665 | -0.1 | 0.825 | 0.831 | +0.7 |
| Bidah 03 | Crest 105 | 10.595 | 10.596 | +0.0 | 1.127 | 1.136 | +0.8 |

100-yr, from FSL, through the loader: Faydh out 905.8 against 910.5 on the EAV curve with the same class, Bidah 220.1 against 221.2, both -0.5 %, and 908 and 220 by `W1`'s Modified Puls. The EAV area column runs 3 % under this table at Faydh while the volumes agree; the cause was not found.

## Weak, and what to decide

1. **Which lag.** NRCS is what the brief asked for and it gives 1.05 to 1.58 x HMS. Kirpich x 0.474 is a one-line alternative that reproduces his model. `slope_10_85` is in `basin.json` for it. Not built: choosing a lag method is a design decision for him, and no gauge settles it.
2. **Sections** cost 10 points of the HMS peak at R5A. The trapezoid is what the engine's Muskingum-Cunge takes, so the 8-point section of decision 8 is not there; the width curve is stored in `section`.
3. **`index_celerity` is derived**, 5/3 of Manning at `section_depth_m`, 2 to 4 m/s against HMS's 1.524 on every reach. It sets the reach's grid, not its physics, but it is not HMS's number.
4. **D8 on a flat bed runs parallel lines**, which do not join, so a confluence on a wide bed lands further down than on the ground.
5. **Delineation ignores `burn_line`, `wall` and the shaped objects.** A channel in the job does not change the network; an embankment across a wadi is not a dam. Decision 10 wants them in.
6. **Reservoir:** the rating is the spillway object only, no crest overflow; a pool over the top of its table, crest + 10 m, raises, as the engine does. The start is the lowest spillway crest, assumed. A saddle dam is reported, not a barrier, and the pool has no leak check past the catchment. Levels are taken on the DEM's datum and only a crest under the ground raises a note: the GGC 2.39 m gap is not detected.
7. **Ground with no subbasin:** 80 km2 of 810 here, what reaches the domain edge without meeting a stream. It is in `unassigned_km2` and has no element: rain-on-grid, by the rule of the next piece.
8. **Slivers:** a local catchment under `min_subbasin_km2` joins a neighbour only if one drains to the same junction; a few pixels at a chain of nodes stay as a subbasin.
9. **`BasinSettings` is not in `RunConfig`**, so it is not in the JSON Schema and a job cannot carry it. Adding `basin: BasinSettings = BasinSettings()` is one line, plus a `NOT_WATER` entry in `run.py` or old checkpoints stop matching, plus the sample.

## Not tested

- Through the dock: nothing here is in the plugin.
- Any storm but the 100-yr, any project but Block 2, the full 15,398 km2 extent (at 5 m it is over `max_pixels` and asks for a coarser pixel; 30 m not run).
- The 0.5 m DEM on the whole catchment: on Bidah's domain only, 5 s.
- The generated model in 2D: no job reads `basin.json` yet.
- `basin.gpkg` in QGIS: opened through GDAL (fiona), three layers, the CRS and every column read; not loaded in a QGIS window.
- Reruns of the name carry-over on real ground: synthetic only.
