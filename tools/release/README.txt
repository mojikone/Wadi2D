Wadi2D for QGIS on Windows
==========================

GPU 2D flood modelling with HEC-HMS style hydrology inside, run from one dock in QGIS. Experimental. GPL-3.0-or-later.
https://github.com/mojikone/Wadi2D

You need
  - Windows 10 or 11, 64 bit
  - QGIS 3.34 or later (Qt5 builds; the LTR is fine)
  - Python 3.12 or 3.13. Your own if you have one, otherwise the one inside QGIS. If neither fits, install Python 3.12
    from https://www.python.org/downloads/
  - An NVIDIA card with a current driver for the fast engine. Without one the engine runs on the CPU, tens of times slower.
  - About 4 GB of disk, and the internet during installation (about 2 GB to download)

Install
  1. Unzip this whole folder anywhere.
  2. Double-click install_wadi2d.bat. Nothing is asked. Run it again later to update.
  3. Open QGIS, go to Plugins > Manage and Install Plugins > Installed, and tick Wadi2D.

  The engine goes into %LOCALAPPDATA%\Wadi2D, the plugin into the default QGIS profile. For another QGIS profile, add
  wadi2d_qgis-*.zip there through Plugins > Manage and Install Plugins > Install from ZIP; it finds the same engine.

  If the dock says the engine was not found, press Engine... and give it
  %LOCALAPPDATA%\Wadi2D\engine\Scripts\python.exe, then Check engine.

First run
  1. Load a DEM from a file, in a projected CRS, and a polygon of the area.
  2. In the dock, top to bottom: Terrain (DEM, cell size, polygon), Hydrology (rain in mm/h and hours, or an HEC-HMS project
     folder), Boundaries (a line layer where water leaves, kind and value), Results points (lines across the flow give
     discharge).
  3. Under Run, choose an output folder, press Estimate, then Run. Start small: a few km2 at 20 m takes seconds on a GPU.
  4. Depth appears live. At the end the maps load into a group. Make map writes A3 sheets as a PDF.

Remove
  Uninstall the plugin in QGIS's Plugin Manager and delete the folder %LOCALAPPDATA%\Wadi2D.

Results are not validated against every case. Check them before you rely on them. There is no warranty; see LICENSE.txt.
Third-party licences are listed in LICENSES.md. The NVIDIA libraries are downloaded by pip from PyPI under NVIDIA's own terms
and are not part of this package.
