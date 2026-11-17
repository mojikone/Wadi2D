Wadi2D 0.5.0. Install: unzip `Wadi2D-0.5.0-windows.zip`, close QGIS, double-click `install_wadi2d.bat`, as for 0.4.0. A new install over 0.4.0 replaces the plugin and updates the engine in place.

## New since 0.4.0

**A new dock.**
- **The model type first:** 2D, Lumped, Hybrid Lumped or Hybrid 2D, or open a finished run. Only that type's sections show. "All sections" keeps the old full list.
- **The model is saved with the QGIS project.** A finished run, or a job the dock did not write, opens back into the dock and says in words whatever it could not hold. Models can be saved as named scenarios.
- **Each section is a card** with Ready, Optional or Missing and one line saying what is set or missing. A step strip at the top jumps to a section, and the footer names what still needs you, beside Check and run. A dark version follows the QGIS theme.
- **A Simulation section:** one start time, simulated time, the 2D step (automatic, or fixed under Advanced), the lumped step, and map and hydrograph intervals.
- **Area reduction** has a lumped part and a 2D part, each a curve (table and chart), a fixed area or a coefficient (1 means none).
- **Rain sources:** a fixed depth, a depth and pattern, a TIF depth grid and pattern, DSS, NetCDF, gauges, an HMS met file. A Data tables section holds named patterns and ARF curves. The SCS type I, IA, II and III patterns are HEC-HMS 4.12's own tables.
- **Losses and roughness:**
  - a CN override table (by land use, CN range or subbasin);
  - a CN value for the cells a CN grid leaves empty;
  - Manning as one value, squares and aligned cells apart, a grid, or land-use classes;
  - a reach Manning n for generated basins, 0.1 by default.
- **Boundaries:** an inflow hydrograph typed at a time step with its chart, and initial water levels from points.
- **One Mesh section:** squares, quadtree or the aligned centre mesh, and Build mesh, which draws the cells, their count and the smallest cell before any run.
- **Domain from a drawn outline:**
  - Complete upstream adds every catchment draining in.
  - Align to catchments snaps the edge to them.
  - Streams that would leave through a closed edge are named, with a button to add outflow lines there.
- **Generated basins:**
  - each basin point says which stream it snapped to and what drains there;
  - the dams, and junctions you mark (HAT-J4 on Block 2), are the last points of the lumped model.
- **A results page:**
  - the run's elements by kind, with search and pinned elements;
  - every row opens its hydrograph chart;
  - Compare runs, with each dam lined up across the four model types, and export to Excel.

**Your ARF rules.**
- **Lumped and Hybrid Lumped:** each point at its own drainage area. Hybrid Lumped's routed outflow enters the 2D model at the dams and marked last points.
- **Hybrid 2D:** every lumped catchment at its dam's (last point's) area.
- **Rain on the 2D grid:** one reduction per run.

**Maps drawn the RAS Mapper way.**
- **One continuous water surface minus the terrain at each pixel**, with no cell blocks or cut edges. A reservoir or gorge deeper than the colour ramp now draws in its darkest blue instead of vanishing.
- **Maps of record at a pixel chosen by rule** (2 m on Block 2), compressed within 1 mm, with overviews: 20 to 26 times lighter, and QGIS opens them at any zoom.
- **A highest water level raster** beside depth, speed and hazard.
- **Detail at the terrain's finest resolution for a window you draw.**
- **One depth threshold for every map and the screen**, 0.1 m by default. The hazard map leaves out water under it.
- No depth × speed raster unless ticked.

**Faster.**
- The aligned-mesh builder: 615 to 87 s on Block 2.
- Maps after a run: 1,740 to 177 s on Block 2's full 2D run.
- Block 2's four models built and run through the dock alone: 2D 46 min, Hybrid Lumped 20 min, Hybrid 2D 40 min, Lumped 10 s, from Run to maps loaded.

## Known limits

- **Map numbers change against 0.4.0.** The continuous surface shows water the old cell cut hid: Block 2's 2D wet area is about 21 % larger at a 0.05 m threshold. The hazard map's H1 is smaller again at the 0.1 m threshold. Remake older runs' maps to compare like with like.
- **Generating a basin over flat coastal ground is not exactly repeatable.** The same inputs gave 108, 109 or 111 subbasins on Block 2. The dam areas are identical every time.
- **A generated basin is not HEC-HMS's basin.** On Block 2, Lumped reads within 5.4 % of the owner's HMS model at four dams and 27 % over at R2A. Hybrid 2D reads −18 % to +42 % against the HMS-based run, from 67 generated outlets against 26.
- The time slider at the pixel draws aligned and quadtree runs one value per cell. On those, the terrain's finest detail comes from a drawn window.
- The quadtree's maps have no water-level raster. Aligned streams inside coarse quadtree hills are not available.
- The smoothed polygons and depth drawing remain as options, off by default.
- Not tested on a PC other than the build PC.

## What was tested on this build

On the build PC (RTX 5080), on the commit the zip was built from (`c50f5c7`):

- **The full test suite:** 3,124 passed, 10 skipped (HMS cases with no evaporation), none failed. It ran one file at a time on the CPU and the GPU. Two solver files stalled at their first GPU test during the long run; each passed on its own (29 of 29, 18 of 18) with no solver code changed since they last passed and no GPU driver fault logged. A stall like this has not been seen in a user run.
- **The installer and the plugin, in throwaway QGIS 3.44.8 profiles:** GPU 17 of 17, QGIS's own Install from ZIP 8 of 8, CPU engine 10 of 10. A developer's linked plugin folder survives an install.
- **The five Block 2 hybrid dam peaks at 40 m:** equal to the record to the digit (Bidah 03 622.4, Faydh 01 1,122.8, R2A 1,812.2, R5A 1,262.6, Z4C 2,103.3 m3/s).
- **Block 2's four models built and run through the dock alone, from raw inputs:** 77 of 77 checks (W106).

Not tested: a PC other than the build PC; a fresh install on a PC that never had Wadi2D.

`Wadi2D-0.5.0-windows.zip`: 1,323,958 bytes, sha256 `aa27f7047399eef3de4dd7db81f17a036eac35cd485d95fb50c6051618e2c7dd`.
