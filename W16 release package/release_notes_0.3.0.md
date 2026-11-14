Pre-release for testing. Windows, QGIS 3.40 or 3.44 LTR; NVIDIA GPU optional (the CPU engine runs everywhere).

Install: unzip `Wadi2D-0.3.0-windows.zip`, close QGIS, double-click `install_wadi2d.bat`, then open the dock from the Wadi2D toolbar button or Plugins > Wadi2D.

## New since 0.2.0

**Hydrology (HEC-HMS style, lumped, metric; each checked against HEC-HMS 4.12 run headless)**
- Culverts (box and circular, FHWA HDS-5 inlet and outlet control as HMS does it, any number of barrels).
- Drowned weirs on spillways and dam tops by HMS's submergence table; drowned gates and gate control by percent time series, as HMS does them.
- Diversions: inflow table, constant flow, lateral weir, pump station, specified flow, with maximum flow and volume limits.
- Basin points layer: outfalls, design points, dams, diversions, sources (external hydrographs), add or remove junctions, join subbasins; every Generate basin replays the edits. Walls and burn lines take part in the delineation by a tick.
- Time of concentration for HMS subbasins; the chart names reservoirs and diversions, shows a diversion's passed and diverted flow, overlays a second element.
- The dam workbook fills reservoir sheets from Wadi2D runs, takes a depth-area study folder, and renames sheets; a dock dialog writes it.

**2D model**
- Dam breach on squares, the aligned mesh (corridors, centre mesh, mixed dams) and the quadtree; Froehlich 2016 and Xu and Zhang 2009 estimators added; a breach row in the dock.
- Inflow hydrograph lines bring their momentum (on by default); not on the quadtree or with local time stepping.
- Domain edge check: streams that leave through a closed domain edge are named before the run, deep flat water against a closed edge after it, as a point layer.

**Dock**
- One QGIS layer group per model: `Wadi2D – <model>` with Inputs (Terrain, Boundaries, Structures, Hydrology, Mesh) and one Results group per run; a rerun replaces only its own results.
- Rain gauges in the Storm section; Preview rain draws the storm's depth per subbasin and a depth raster.
- Inflow momentum and direction in the boundary table; each HMS reservoir's structures shown with the engine's refusals; a diversion points table.

## Known limits
Culvert shapes other than box and circular, steep barrels, gate rule-based operations, Constant Flow's annual pattern and a pump's run and rest times are refused by name. The breach is not run with local time stepping or a resumed run. Not yet installed on another PC.
