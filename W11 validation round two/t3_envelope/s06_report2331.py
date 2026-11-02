"""Read the 2331 flood data analysis report: headings, tables, anything on envelopes and regional relations. Read only."""
import sys
from pathlib import Path

import docx

R = Path(r"W:\2331 Flood Hazard Maps for Muscat-Dhofar-Musandam_MWR\06-WORKING\03-Hydrology\0.13 REPORTS\Hydrology Final Report- Flood Data Analysis")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
d = docx.Document(R / "Report" / "Final Report" / "Hydrology Final Report- Flood Data Analysis.docx")
print(len(d.paragraphs), len(d.tables))
for p in d.paragraphs:
    t = p.text.strip()
    if not t:
        continue
    if p.style.name.startswith(("Heading", "Caption")):
        print("#", p.style.name[:10], t[:160])
    elif any(k in t.lower() for k in ("francou", "creager", "envelope", "regional", "unit peak", "specific", "shaheen", "gonu", "km2", "km²")):
        print("  ", t[:420])
for i, t in enumerate(d.tables):
    print("TABLE", i, len(t.rows), len(t.columns), [c.text[:14] for c in t.rows[0].cells][:10])
