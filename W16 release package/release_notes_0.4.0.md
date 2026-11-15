Wadi2D 0.4.0. Install: unzip `Wadi2D-0.4.0-windows.zip`, close QGIS, double-click `install_wadi2d.bat`, as for 0.3.1. A new install over 0.3.1 or 0.4.0rc1 replaces the plugin and updates the engine in place.

## New since 0.3.1

- **HMS catchments left out of the mesh.** One project-wide 2D domain. With Hydrology's tick "Leave the catchments the lumped network carries out of the 2D mesh", the cells under the catchments HMS routes get no tables, no solver work and no maps. The edge there is a closed wall. An inflow that falls inside moves to the wadi cell just outside, within 500 m; if there is none, the run stops and says why.
- **The HMS way in the dock, with charts.** Hydrology > HMS: lumped water can go down the HMS reaches and dams and enter the 2D model where rain-on-grid water joins it, or the run can be the HMS way only, with no grid and no DEM. A run's group gets the lumped network as layers, labelled with peak and time. A right-click on a catchment, reach, junction or reservoir opens its chart, and Result lines lists every element.
- **Each element at its own ARF.** With the HMS way only, every element is read at the area reduction of its own drainage area, as HMS's depth-area analysis does.
- **A given ARF factor.** A fourth Area reduction choice: one number, 0.7 meaning a 30 % reduction, applied to cells and lumped elements alike.
- **The depth cutoff.** Run > "Draw depth from", 0.05 m by default: every depth layer and Make map draws from that depth up. The rasters of record keep every depth.
- **Muskingum.** Reach routing gains Muskingum as HEC-HMS 4.12 computes it (HMS's own series to 9e-13 on fourteen cases), read from an HMS basin file or set in a reach table, and a Propose K and X button that shows a proposal and never applies it. On Block 2 it agrees with Muskingum-Cunge in the hill reaches and runs up to 20 % high and an hour early down the plain; K matters far more than X.
- **Pit check and fill.** Before every run the small deep sinks of the terrain are named (63 on Block 2, in about a second); a tick in Terrain fills them as terrain objects of the run. One DEM hole was setting Block 2's time step.
- **Pixel maps on the aligned mesh.** The pixel maps of aligned-mesh runs now finish (Block 2 at 0.5 m in about 18 min, where they failed before), the wadis are no longer blank in the cell maps, and the card and the CPU give the same pixels.
- **The strip join fix.** The aligned cells no longer record speeds of millions of m/s, and the velocity at the join between aligned cells and squares is held to the step's own limit. Every aligned-mesh run's water changes slightly (Faydh's dam-axis peak +0.07 %).
- **Sleeping tiles.** A dry tile that no water can reach is not stepped until water comes near. A tile that wakes equals one that was stepped all along, so the results are the same to the last bit. Estimated on Block 2's hybrid runs: 13 to 24 % less stepping time.
- **Shorter wait before the solver starts.** A run with pit fills used to build its tables twice in full. Now the second build redoes only the tiles and aligned-cell pieces the fills touch, the domain-edge check runs alongside the table build, and the terrain survey reads the same fast terrain store as the tables. On Block 2's aligned runs, a cold start waits 14.5 min where it waited 42, and 9 min where it waited 26. Tables, pits, terrain volumes and the resolved job are identical to the digit.
- **Faster tables, terrain store.** The tables build on 16 threads and in pieces, so Block 2's aligned job at 0.5 m builds in 13 GB where it was refused for 66 GB. The aligned mesh is cached between runs, and the DEM is read through a store of its own that scales with threads.
- **Layer groups as before.** A run's layers land in its own group as in 0.3.1, with the lumped network beside them.

## Known limits

- **The dock has not been redesigned yet.** The sections are the ones of 0.3.1 plus the new controls.
- **The aligned-mesh generator uses one core.** It is most of what is left of the wait before the solver: about 10 of the 14.5 minutes on Block 2's largest aligned run.
- **Pixel maps take about 8 s a frame on a full-2D block.** Making a time-slider film of a whole block at the terrain pixel takes minutes.
- **The velocity at the strip join is capped, not exact.** It is held to the step's limit so the run stays stable; a cell at the join can still read a speed that is too high.
- **Muskingum is an option. Muskingum-Cunge is the recommended routing.** Muskingum's K from Kirpich, where a reach has no section, is 2 to 4 times too long; give a section or a velocity.
- A run with catchments left out has not been made on Block 2 through the dock, nor on a generated basin.
- The time slider and Make map do not show the lumped network layers.
- Aligned-mesh results from before 0.4.0 are superseded by the strip join fix and need a rerun.

## What was tested on this build

On the build PC (RTX 5080), on the commit the zip was built from:

- **The full test suite:** 2,787 passed, 10 skipped (HMS cases with no evaporation), none failed. It ran in chunks, one per test folder, on the CPU and the GPU.
- **The installer and the plugin, in throwaway QGIS 3.44.8 profiles:** GPU 17 of 17, QGIS's own Install from ZIP 8 of 8, CPU engine 10 of 10. A developer's linked plugin folder survives an install.
- **The five Block 2 hybrid dam peaks at 40 m:** equal to the record to the digit (Bidah 03 622.4, Faydh 01 1,122.8, R2A 1,812.2, R5A 1,262.6, Z4C 2,103.3 m3/s). None of this release's changes moves a square-cell run's numbers.

Not tested: a PC other than the build PC; a fresh install on a PC that never had Wadi2D (this test installed over an earlier test install); a Block 2 run with catchments left out through the dock.
