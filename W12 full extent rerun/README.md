# W12 full extent rerun

**Status (2026-11-01): finished, passes the rule set before the run. The maps here predate the cell-edge fix (`W14 cell edge steps`) and are to be remade.** W2's job on the merged engine, `2195de6`: same domain, terrain, storm, losses, Manning and outlets. W2 stays as it was and remains the record of the first run.

## What changed against W2

| Change | Expected effect |
|---|---|
| Dry-face fix in the momentum advection | Peaks in narrow diagonal channels fall slightly |
| Boundary fix | None: W2's two coast lines keep every cell |
| Map interval 900 s, not 21,600 s, and the pixel step in the run | Pixel depth, hazard, smooth polygons and the depth drawing come from the run itself |
| Fill to mean depth in the pixel step | H1 grows about 12 % against W2's issued maps, H3 to H6 hardly move |

Set before the run: mass error at most 1e-6, and each of the five dam peaks within 5 % of W2. A dam outside that is explained before anything is issued.

## Result

Mass error 3.9e-8 against the limit of 1e-6: 106 m3 in 2,697 Mm3 of excess; 2,343 Mm3 left by the coast. 370,434 steps, loop 111 min, but the card was shared for most of it, so that is not a timing.

| Dam | W2, m3/s | Here, m3/s | Change |
|---|---|---|---|
| Faydh_01 | 1,920.1 | 1,947.0 | +1.40 % |
| Bidah_03 | 601.0 | 603.7 | +0.44 % |
| R5A | 1,959.7 | 1,964.2 | +0.23 % |
| R2A | 3,064.9 | 3,116.5 | +1.68 % |
| Z4C | 2,786.2 | 2,887.2 | +3.62 % |

**All five within 5 %.** The expected effect above was wrong in sign: every line rose, none fell, and two rings moved most, S1 +4.2 %, S5 +5.3 %. Why is not known yet.

Pixel classes, km2: H1 1,113, H2 797, H3 385, H4 709, H5 1,189, H6 439, within 0.5 % of `W9`'s reading of the first run with the same fill, H1 included. 144 maps. The step's own drawing moves H3 and above under 0.06 %.

Two things that are the terrain, not the solver:

- The reported deepest pixel, 709 m, is a hole in the blended DEM at 508,137 / 2,579,657: about 30 m wide, ground falling from 1,880 m to 1,172 m high in the mountains, where nothing suggests a real shaft [Likely]. 1,315 pixels stand over 50 m, 0.03 km2. So `depth_max_m` and `dv_max_m2s` in `pixels.json` mean nothing here; do not quote them. Water and volume are correct for that ground.
- The run warns of 31.5 m of water against the domain edge at (529,070 / 2,566,250): an edge is a wall, so check the polygon there.

## Rerun

From the repository root with the project venv:

`python -m wadi2d.engine.cli run "W12 full extent rerun/jobs/full_30m_200yr.json" --out "W12 full extent rerun/runs/full_30m_200yr"`

`runs/`, `cache/` and `run.log` stay out of git.
