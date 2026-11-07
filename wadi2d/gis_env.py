"""The engine's own PROJ and GDAL data, whatever other GIS software has set for the whole user.

Interface: :func:`own_gis_data`.

GIS programs often set ``PROJ_LIB``, ``PROJ_DATA``, ``GDAL_DATA`` or ``GDAL_DRIVER_PATH`` for the user: a Grasshopper GDAL
plugin did on his laptop (2026-11-07). The rasterio wheel carries its own PROJ and GDAL and their data. Another
installation's ``proj.db`` has another layout ("DATABASE.LAYOUT.VERSION.MINOR = 2 whereas a number >= 6 is expected"),
and its driver plugins are built for another GDAL (0xc0000139 when loaded). So, before rasterio loads, the engine points
PROJ and GDAL at rasterio's own data and drops outside drivers. A variable that is not set is left alone: rasterio then
finds its own data unaided. The QGIS plugin already starts the engine with these cleared; this covers a shell and the tests.
"""

from __future__ import annotations

import os
from importlib.util import find_spec
from pathlib import Path

DATA = {"PROJ_DATA": "proj_data", "PROJ_LIB": "proj_data", "GDAL_DATA": "gdal_data"}
"""Variable, and the folder in the rasterio package that answers it."""
FOREIGN = ("GDAL_DRIVER_PATH",)
"""Variables that load another GDAL's code into this one."""


def own_gis_data() -> dict[str, str]:
    """Point the set PROJ and GDAL variables at rasterio's bundled data, drop outside drivers; what changed, by name."""
    spec = find_spec("rasterio")
    if spec is None or spec.origin is None:
        return {}
    root = Path(spec.origin).parent
    changed: dict[str, str] = {}
    for name, folder in DATA.items():
        old, own = os.environ.get(name), root / folder
        if old is not None and own.is_dir() and Path(old) != own:
            changed[name] = old
            os.environ[name] = str(own)
    for name in FOREIGN:
        if name in os.environ:
            changed[name] = os.environ.pop(name)
    return changed
