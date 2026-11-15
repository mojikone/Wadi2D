**Test build, not a release.** Wadi2D 0.4.0 release candidate 1, a pre-release for trying on the laptop. Branch `release/0.4.0-rc1`; `main` stays at 0.3.1.

Install: unzip `Wadi2D-0.4.0rc1-windows.zip`, close QGIS, double-click `install_wadi2d.bat`, as for 0.3.1. A new install over 0.3.1 replaces the plugin and updates the engine in place.

## New since 0.3.1

- **HMS catchments left out of the mesh.** One project-wide 2D domain; with Hydrology's tick "Leave the catchments the lumped network carries out of the 2D mesh", the cells under the catchments HMS routes get no tables, no solver work and no maps. The edge there is a closed wall, and an inflow that falls inside moves to the wadi cell just outside (within 500 m, or the run stops and says why).
- **The HMS way in the dock, with charts.** Hydrology > HMS: lumped water can go down the HMS reaches and dams and enter the 2D model where rain-on-grid water joins it, or the run can be the HMS way only (no grid, no DEM). A run's group gets the lumped network as layers, labelled with peak and time; a right-click on a catchment, reach, junction or reservoir opens its chart, and Result lines lists every element.
- **Each element at its own ARF.** With the HMS way only, every element is read at the area reduction of its own drainage area, as HMS's depth-area analysis does.
- **The given ARF factor.** A fourth Area reduction choice: one number, 0.7 meaning 30 % reduction, on cells and lumped elements alike.
- **The depth cutoff.** Run > "Draw depth from", 0.05 m by default: every depth layer and Make map draws from that depth up. The rasters of record keep every depth.
- **Muskingum.** Reach routing gains Muskingum as HEC-HMS 4.12 computes it (HMS's own series to 9e-13 on fourteen cases), read from an HMS basin file or set in a reach table, and a Propose K and X button that shows a proposal and never applies it. On Block 2 it agrees with Muskingum-Cunge in the hill reaches and runs up to 20 % high and an hour early down the plain; K matters far more than X.
- **Pit check and fill.** Before every run the small deep sinks of the terrain are named (63 on Block 2 in about a second); a tick in Terrain fills them as terrain objects of the run. One DEM hole was setting Block 2's time step.
- **Pixel maps on the aligned mesh.** The pixel maps of aligned-mesh runs now finish (Block 2 at 0.5 m in about 18 min, where they failed before), the wadis are no longer blank in the cell maps, and the card and the CPU give the same pixels.
- **The strip join fix.** The aligned cells no longer record speeds of millions of m/s, and the velocity at the join of aligned cells and squares is held to the step's own limit. Every aligned-mesh run's water changes slightly (Faydh's dam-axis peak +0.07 %).
- **Sleeping tiles.** A dry tile that no water can reach stops being stepped until water comes near; a tile that wakes equals one that was stepped all along, so the results are the same to the last bit. Estimated on Block 2's hybrid runs: 13 to 24 % less stepping time.
- **Faster tables, terrain store.** The tables build on 16 threads and in pieces, so Block 2's aligned job at 0.5 m builds in 13 GB where it was refused for 66 GB; the aligned mesh is cached between runs; the DEM is read through a store of its own that scales with threads.
- **Layer groups as before.** A run's layers land in its own group as in 0.3.1, the lumped network beside them.

## Known limits

- **A test build.** Not every combination has been run; the full test suite was not run on this build (see the test record below).
- **No GPU check of this build.** The installer and the plugin were tried with the CPU engine only; the GPU engine has not run from this zip.
- Muskingum's K from Kirpich, where a reach has no section, is 2 to 4 times too long; give a section or a velocity.
- A run with catchments left out has not been made on Block 2 through the dock, nor on a generated basin.
- The time slider and Make map do not show the lumped network layers.
- Aligned-mesh results from before this build (W79's runs) are superseded by the strip join fix and need a rerun.

## What was tested on this build

On the build PC, CPU engine only, each test file on its own:

- Muskingum's own tests and the plugin's: `tests/hydrology` (19 files) and `tests/plugin` (37 files), all passed, 9 skipped (cases with no evaporation).
- Sleeping tiles' tests (solver, strips, a whole run): 16 of 16.
- The HMS-way tests: catchments left out 18 of 18, the lumped network 7 of 8 on the first run and 8 of 8 on three reruns (one check compares two float sums for exact equality and differed in the last of 16 digits once), generated-basin runs 10 of 10, `tests/plugin` again all passed.
- The zip built from commit `6c85ff3`; it holds the engine wheel, the plugin zip with its new modules, `gpu_check.ps1` and the installer.
- The installer with `-CpuOnly` into a throwaway folder: installed in 37 s. The installed plugin in a throwaway QGIS 3.44.8 profile, a small rain run on the CPU engine: 10 of 10. QGIS's own Install from ZIP, finding the engine by its record: 8 of 8.

Not tested: the GPU install and any GPU run from this zip, the full test suite, a Block 2 run through the dock, a PC other than the build PC.
