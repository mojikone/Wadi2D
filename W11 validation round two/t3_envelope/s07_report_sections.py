"""Text of selected sections of the 2331 report, with the tables in document order. Read only."""
import sys
from pathlib import Path

import docx
from docx.table import Table
from docx.text.paragraph import Paragraph

R = Path(r"W:\2331 Flood Hazard Maps for Muscat-Dhofar-Musandam_MWR\06-WORKING\03-Hydrology\0.13 REPORTS\Hydrology Final Report- Flood Data Analysis")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
d = docx.Document(R / "Report" / "Final Report" / "Hydrology Final Report- Flood Data Analysis.docx")
out = open(Path(__file__).with_name("report2331_full.txt"), "w", encoding="utf-8")
n = 0
for el in d.element.body.iterchildren():
    if el.tag.endswith("}p"):
        p = Paragraph(el, d)
        t = p.text.strip()
        if t:
            out.write(f"[{p.style.name[:9]}] {t}\n")
    elif el.tag.endswith("}tbl"):
        t = Table(el, d)
        out.write(f"<<TABLE {n} rows {len(t.rows)}>>\n")
        for r in t.rows:
            cells = []
            prev = None
            for c in r.cells:
                if c._tc is prev:
                    continue
                prev = c._tc
                cells.append(c.text.strip().replace("\n", " "))
            out.write(" | ".join(cells) + "\n")
        n += 1
out.close()
