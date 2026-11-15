"""runs/inputs/run3_catchments.gpkg: run 3's catchments by how they are modelled, for its group in the QGIS project.

His definition of run 3 (2026-11-15): HMS's subbasins and reaches above the five dams (S1 to S18) and above junction
HAT-J4 (HAT-S1 to HAT-S8), left out of the 2D mesh; rain on the grid on the other 78 subbasins. One polygon per
subbasin with ``part`` (the three groups), ``carried_by`` (the dam or HAT-J4), ``arf_area_km2`` and ``area_km2``, and a
dissolved layer of the three groups.
"""

from __future__ import annotations

import sys
from pathlib import Path

import geopandas as gpd
import shapely

sys.path.insert(0, str(Path(__file__).resolve().parent))
from s02_jobs import HAT_AREA_KM2, HAT_JUNCTION, above_hat, reaches_dam  # noqa: E402
from w79 import BASIN, DAM_AREA_KM2, HMS_DIR, RUNS, STORM_AREA_KM2  # noqa: E402

from wadi2d.config.schema import Hydrology  # noqa: E402
from wadi2d.forcing import load_polygons  # noqa: E402

DAMS_PART = "HMS above the five dams (S1 to S18), left out of the mesh"
HAT_PART = f"HMS above {HAT_JUNCTION} (HAT-S1 to HAT-S8), left out of the mesh"
GRID_PART = "Rain on the grid (78 subbasins), ARF at 100 km2"
OUT = RUNS / "inputs" / "run3_catchments.gpkg"


def main() -> None:
    h = Hydrology(hms_basin=str(HMS_DIR / BASIN), hms_sqlite=str(HMS_DIR / BASIN.replace(".basin", ".sqlite")))
    rows = []
    for name, polygon in load_polygons(h).items():
        dam = reaches_dam(name)
        if dam is not None:
            part, by, area = DAMS_PART, f"{dam} Reservoir", DAM_AREA_KM2[dam]
        elif above_hat(name):
            part, by, area = HAT_PART, HAT_JUNCTION, HAT_AREA_KM2
        else:
            part, by, area = GRID_PART, "", STORM_AREA_KM2
        geometry = shapely.make_valid(polygon)
        rows.append({"name": name, "part": part, "carried_by": by, "arf_area_km2": area,
                     "area_km2": round(geometry.area / 1e6, 3), "geometry": geometry})
    frame = gpd.GeoDataFrame(rows, crs="EPSG:32640")
    OUT.unlink(missing_ok=True)
    frame.to_file(OUT, layer="subbasins", driver="GPKG")
    parts = frame.dissolve(by="part", aggfunc={"area_km2": "sum"}).reset_index()
    parts.to_file(OUT, layer="parts", driver="GPKG")
    print(parts[["part", "area_km2"]].to_string())


if __name__ == "__main__":
    main()
