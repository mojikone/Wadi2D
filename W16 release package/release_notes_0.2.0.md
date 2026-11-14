Pre-release for testing. Windows, QGIS 3.40 or 3.44 LTR; NVIDIA GPU optional (the CPU engine runs everywhere).

Install: unzip `Wadi2D-0.2.0-windows.zip`, close QGIS, double-click `install_wadi2d.bat`, then open the dock from the Wadi2D toolbar button or Plugins > Wadi2D.

## New since 0.1.1

**Hydrology (HEC-HMS style, lumped reservoirs, metric)**
- Reservoir outflow structures read from the HMS basin file: rating-table spillway, orifice, level dam top, tabular seepage, monthly evaporation, fixed tailwater, elevation-storage; gated spillways (sluice and radial, fixed opening) and pumps (head-discharge). Checked against HEC-HMS 4.12 run headless: within 1e-4 of peak on the ungated structures, 4e-4 on gates. A reservoir series now carries pool level, storage and each structure's flow.
- Refused with a message, not guessed: culverts, a weir drowned by tailwater, gate controls other than a fixed opening.
- Time of concentration (Kirpich) at every subbasin, reach, junction, reservoir and design point of a generated basin; the run's series carry rain and excess per step.
- Right-click an element on the map: its hydrograph in a docked chart, with a thin rain bar on top and a reservoir's pool level on a second axis.
- Dam workbook: `wadi2d workbook` writes the dam-site Excel workbook (target return period sheet, summaries as live formulas, one sheet per dam with inflow-outflow charts per return period) from runs or HMS DSS files. Command line only.

**2D model**
- Flow hydrograph boundary lines (`flow` kind in the boundary table): Q(t) from CSV, DSS or a table, shared across the line by normal depth at an energy slope. Water enters without momentum along the line; draw the line a cell inside the domain edge.
- Dam breach on a crest line (job file only, no dock row yet): trapezoid, linear or sine growth, overtopping or piping, triggers by level, level and duration, or time; Froehlich 2008, MacDonald and Langridge-Monopolis, Von Thun and Gillette estimators. Uniform grid only; refused on the quadtree, corridors, local time stepping and resumed runs.

**Dock**
- One Rain source choice in the Storm section (design storm, gridded file, gauges, single hyetograph), only its fields shown, and a Preview rain button giving each subbasin's depth and hyetograph before the run.
- Also since 0.1.1: the time-slider layer drawn at the terrain pixel on demand, rain and flow gauges with NSE, RSR and PBIAS, gridded storms with the area reduction and the depth-area study, the local hydraulic radius face law (default), faster products (polygons and the depth drawing off by default, a tick in the dock).

## Tested
Full test suite 2,263 passed. Installed from this zip into throwaway QGIS profiles on the build PC (GPU, Install from ZIP, CPU). Not yet tested on another PC.
