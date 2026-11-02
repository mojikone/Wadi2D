"""The hybrid maps, from a run folder, by the code behind the Make map button. Own process, python-qgis-ltr.bat.

Usage: s04_maps.py <run folder> <output folder> [satellite|hillshade]. Writes the PDF, one PNG per sheet.
"""

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "plugin"))

from qgis.core import QgsApplication, QgsProject  # noqa: E402

RUN = Path(sys.argv[1])
OUT = Path(sys.argv[2])
BACKGROUND = sys.argv[3] if len(sys.argv) > 3 else "satellite"
TITLE = "Wadi2D hybrid model, Block 2"
CAUTION = "Not a design result. No gauge, no culverts, 20 m cells."

app = QgsApplication([], False)
app.initQgis()

from wadi2d_qgis.map_sheets import build_book, export_images, export_pdf  # noqa: E402

OUT.mkdir(parents=True, exist_ok=True)
book = build_book(RUN, TITLE, BACKGROUND, CAUTION, leave_out="ring", project=QgsProject.instance())
print("png", export_images(book, OUT / "sheet.png", 300), flush=True)
print("pdf", export_pdf(book, OUT / "Wadi2D_hybrid_Block2_maps.pdf"), flush=True)
sys.stdout.flush()
os._exit(0)
