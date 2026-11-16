"""W79's QGIS project of the four Block 2 runs, saved here with its maps pointed at this iteration's remakes.

    "C:\\Program Files\\QGIS 3.44.8\\bin\\python-qgis-ltr.bat" s09_project.py

Reads ``W79 Block 2 four ways/Block2_four_ways.qgz`` (never written) and writes ``Block2_four_ways_W100.qgz`` here: every
layer of runs 1, 3 and 4 read from ``pixels/`` or ``maps/`` now reads the same file in ``runs/hazard01_<run>/`` (the
continuous surface, 2 m, LERC, overviews, no hazard class under 0.1 m), the depth x speed raster is dropped (not
written any more), and the depth layers are styled again by the plugin (the deep-water clip fix). Everything else
(series, checks, time slider, run 2, inputs) still reads W79's files.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from qgis.core import QgsApplication, QgsDataProvider, QgsProject

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
SOURCE = REPO / "W79 Block 2 four ways" / "Block2_four_ways.qgz"
TARGET = HERE / "Block2_four_ways_W100.qgz"
REMAKE = HERE / "runs"
TAG = "hazard01_"
DROPPED = "pixel_dv.tif"
PATTERN = re.compile(r"/runs/(rerun2_run[134][^/]*)/(pixels|maps)/([^|]+)(.*)$")

sys.path.insert(0, str(REPO / "plugin"))
app = QgsApplication([], False)
app.initQgis()
project = QgsProject.instance()
assert project.read(str(SOURCE)), SOURCE
moved, dropped, kept = 0, 0, 0
for layer in list(project.mapLayers().values()):
    found = PATTERN.search(layer.source().replace("\\", "/"))
    if found is None:
        continue
    run, folder, name, rest = found.groups()
    if name == DROPPED:
        project.removeMapLayer(layer.id())
        dropped += 1
        continue
    new = REMAKE / f"{TAG}{run}" / folder / name
    if not new.exists():
        kept += 1
        continue
    layer.setDataSource(new.as_posix() + rest, layer.name(), layer.providerType(), QgsDataProvider.ProviderOptions())
    moved += 1

from wadi2d_qgis import style  # noqa: E402  after the application, as the plugin is

STYLE_BY_FILE = {
    "pixel_depth.tif": style.style_pixel_depth,
    "pixel_hazard.tif": style.style_pixel_hazard,
    "max_depth.tif": style.style_depth,
}  # W79's layers carry no plugin style tag, so they are styled by their file: the deep-water fix
restyled = 0
for layer in project.mapLayers().values():
    make = STYLE_BY_FILE.get(Path(layer.source().split("|")[0]).name)
    if make is not None and str(REMAKE) in str(Path(layer.source().split("|")[0])):
        make(layer)
        restyled += 1
for group in project.layerTreeRoot().findGroups(True):
    if group.name() == "Pixel rasters, the numbers of record":
        group.setName("Pixel rasters of record (W100: continuous surface, 2 m; hazard from 0.1 m)")
project.setTitle("Block 2, four ways, with W100's maps")
assert project.write(str(TARGET)), TARGET
print(f"moved {moved}, dropped {dropped}, kept on W79 {kept}, restyled {restyled}; wrote {TARGET}")
app.exitQgis()
