"""Make map at full size: the code behind the dock's button on the rerun, with its 1.1 GB of polygons. Own process, python-qgis-ltr.bat.

Usage: s03_make_map.py <output folder> [hillshade|satellite]. Writes the PDF and one PNG per sheet, and the seconds each took.
"""

import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "plugin"))

from qgis.core import QgsApplication, QgsProject  # noqa: E402

RUN = HERE / "runs" / "full_30m_200yr"
OUT = Path(sys.argv[1])
BACKGROUND = sys.argv[2] if len(sys.argv) > 2 else "hillshade"
TITLE = "Wadi2D, full extent, 200-yr storm"
CAUTION = "Not a design result. No gauge, no culverts, 30 m cells."

app = QgsApplication([], False)
app.initQgis()

from wadi2d_qgis.map_sheets import build_book, export_images, export_pdf  # noqa: E402

OUT.mkdir(parents=True, exist_ok=True)
start = time.monotonic()
book = build_book(RUN, TITLE, BACKGROUND, CAUTION, leave_out="ring", project=QgsProject.instance())
print(f"built {time.monotonic() - start:.0f} s", flush=True)
start = time.monotonic()
print("pdf", export_pdf(book, OUT / "Wadi2D_full_extent_maps.pdf"), f"{time.monotonic() - start:.0f} s", flush=True)
start = time.monotonic()
print("png", export_images(book, OUT / "sheet.png"), f"{time.monotonic() - start:.0f} s", flush=True)
sys.stdout.flush()
os._exit(0)
