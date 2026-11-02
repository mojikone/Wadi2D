# W5 automatic breaklines test

**Status (2026-11-01): done, first pass. DEM detection finds the highway but cannot be trusted alone: it suggests lines for review, it does not make them.**

Question: can raised linear features be found from the 5 m terrain alone? Scored against `Bathinah Highway CL`, the only fully built reference he named, 40.8 km inside a 3 km corridor of 273 km2 over the frame of the Block 2 200-yr layer. Terrain is `W2 full extent run/terrain/NSA5_COP30_blend.tif`.

Method: morphological top-hat (ground less its opening with a disc), threshold on height, drop objects under 100 m, thin to a skeleton. Found means a detected line within 30 m of the highway. "Elsewhere" is detected length away from the highway. Some of it is real, other roads or dykes, and this test has no layer to separate them.

## Height and disc alone (`s01_highway.py`)

| Disc radius, m | Height, m | Found | Elsewhere, km |
|---|---|---|---|
| 40 | 0.3 | 94 % | 1,193 |
| 40 | 0.5 | 82 % | 376 |
| 40 | 1.0 | 42 % | 98 |
| 60 | 0.3 | 96 % | 1,972 |
| 60 | 0.5 | 88 % | 791 |
| 60 | 1.0 | 52 % | 152 |
| 100 | 0.5 | 92 % | 1,481 |
| 100 | 1.0 | 63 % | 306 |

The embankment stands 0.5 to 1 m above its fitted ground over most of this length: at 1 m half of it disappears.

## Long and straight objects only (`s02_straight.py`, disc 60 m)

| Height, m | Length over, m | Elongation over | Found | Elsewhere, km |
|---|---|---|---|---|
| 0.5 | 300 | 5 | 61 % | 125 |
| 0.5 | 1000 | 5 | 52 % | 81 |
| 0.5 | 300 | 10 | 38 % | 52 |
| 0.75 | 300 | 5 | 49 % | 75 |
| 0.3 | 300 | 5 | 43 % | 308 |

Full tables in `results.json` and `results_straight.json`.

## Reading

- [Certain] At the settings that find the highway well, detected length elsewhere is about 19 x the highway's 40.8 km. Filtering on shape cuts that about 6 x and loses a third of the highway.
- [Likely] The shape filter loses highway because the embankment joins neighbouring ridges into one object, or breaks at culverts, so whole-object length and elongation are poor measures. Following a line segment by segment may do better. Not tested.
- Not tested: dams, ponds, stockpiles, ditches, or whether a missed stretch matters to the flood. A low embankment may matter less than the tall stretches, which are the ones found.
- Decision so far: surveyed layers first. DEM detection is a suggestion layer reviewed in QGIS, sorted by height and by the flow against each line.
