import sys
from pptx import Presentation
import docx
B=r"W:/2224 Flood Protection Scheme in North & South Batinah_MAFWWR/06-WORKING/03-Hydrology/"
p=Presentation(B+"MODEL CALIBRATION and FLODD CHANNELS.pptx")
for i,s in enumerate(p.slides,1):
    t=[]
    for sh in s.shapes:
        if sh.has_text_frame:
            x=' | '.join(q.text for q in sh.text_frame.paragraphs if q.text.strip())
            if x: t.append(x)
        if sh.has_table:
            for r in sh.table.rows:
                t.append(' ; '.join(c.text for c in r.cells))
    print('SLIDE',i,len(s.shapes),' // '.join(t)[:900])
d=docx.Document(B+"Hydrometry/Report/Appendix A - Rainfall and Flow analysis.docx")
print('DOCX paras',len(d.paragraphs),'tables',len(d.tables))
for q in d.paragraphs:
    if q.text.strip(): print(q.style.name[:12],'|',q.text[:300])
