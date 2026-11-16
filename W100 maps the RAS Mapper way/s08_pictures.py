"""The before and after pictures of W100: the same windows of Block 2's 2D run, the maps as W79 made them and as
this branch makes them, in the plugin's colours (``pictures.py``).

    python s08_pictures.py BEFORE_RUN AFTER_RUN WINDOWS_DIR OUT_DIR

BEFORE_RUN is W79's run folder (its own rasters, 0.5 m, W9's rule); AFTER_RUN the remake of this iteration (2 m, the
continuous surface); WINDOWS_DIR the 0.5 m window exports of ``s03_windows.py`` (``<rule>/<window>/``), the detail.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEM = r"D:\Mojtaba\Renardet\2224 WS11\Batinah\Block 2\Hydrology\Terrain\GGC_2_MERGE_HDSM.tif"
WINDOWS = {
    "pool": ((437800, 2714600, 439800, 2716400), "the R2A pool and its dam", False),
    "hill": ((440600, 2716900, 441200, 2717350), "a hillside of RIJ-S12, rain on the grid", True),
    "reach": ((440300, 2717300, 441100, 2717800), "an aligned-cell reach and its join with the squares", True),
}
WIDTH = 1000


def picture(kind: str, raster: Path, bounds, out: Path, grid: Path | None, title: str) -> None:
    command = [sys.executable, "-W", "ignore", str(HERE / "pictures.py"), kind, str(raster), DEM, *map(str, bounds), str(out)]
    command += ["--width", str(WIDTH), "--title", title]
    if grid is not None:
        command += ["--grid", str(grid)]
    subprocess.run(command, check=True, capture_output=True)


def main() -> None:
    before, after, windows, out = (Path(a) for a in sys.argv[1:5])
    out.mkdir(parents=True, exist_ok=True)
    for name, (bounds, what, with_grid) in WINDOWS.items():
        grid = before if with_grid else None
        for kind, file in (("depth", "pixel_depth.tif"), ("hazard", "pixel_hazard.tif")):
            sets = (
                ("1_before", before / "pixels" / file, f"BEFORE (W79, 0.5 m, cells filled to their water): {kind}, {what}"),
                ("2_after", after / "pixels" / file, f"AFTER (map of record, 2 m, continuous surface): {kind}, {what}"),
                ("3_after_detail", windows / "continuous" / name / file, f"AFTER, detail (wadi2d window, 0.5 m): {kind}, {what}"),
            )
            for tag, raster, title in sets:
                if raster.is_file():
                    picture(kind, raster, bounds, out / f"{name}_{kind}_{tag}.png", grid, title)
                    print(out / f"{name}_{kind}_{tag}.png")


if __name__ == "__main__":
    main()
