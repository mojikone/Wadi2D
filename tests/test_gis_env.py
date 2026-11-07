"""Another GIS program's PROJ and GDAL settings do not reach the engine (his laptop, 2026-11-07)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WRITE = """
import numpy as np, rasterio, sys
from rasterio.transform import from_origin
import wadi2d
with rasterio.open(sys.argv[1], "w", driver="GTiff", width=4, height=4, count=1, dtype="float32", crs="EPSG:32640",
                   transform=from_origin(400000, 2700000, 1, 1)) as dst:
    dst.write(np.zeros((1, 4, 4), np.float32))
print(rasterio.open(sys.argv[1]).crs.to_epsg())
"""


def test_a_foreign_proj_database_and_driver_path_are_set_aside(tmp_path: Path) -> None:
    foreign = tmp_path / "other_gis" / "share"
    foreign.mkdir(parents=True)
    (foreign / "proj.db").write_bytes(b"not a proj database")
    env = {**os.environ, "PROJ_LIB": str(foreign), "PROJ_DATA": str(foreign), "GDAL_DATA": str(foreign),
           "GDAL_DRIVER_PATH": str(foreign)}  # fmt: skip
    code = "import wadi2d" + WRITE.replace("import wadi2d\n", "")
    done = subprocess.run([sys.executable, "-c", code, str(tmp_path / "x.tif")], env=env, cwd=ROOT,
                          capture_output=True, text=True)  # fmt: skip
    assert done.returncode == 0, done.stderr[-1500:]
    assert done.stdout.strip().splitlines()[-1] == "32640"


def test_a_clean_environment_is_left_as_it_is(monkeypatch) -> None:
    from wadi2d.gis_env import own_gis_data

    for name in ("PROJ_LIB", "PROJ_DATA", "GDAL_DATA", "GDAL_DRIVER_PATH"):
        monkeypatch.delenv(name, raising=False)
    assert own_gis_data() == {}
    assert "PROJ_LIB" not in os.environ and "GDAL_DATA" not in os.environ
