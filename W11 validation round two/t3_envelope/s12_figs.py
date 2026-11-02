import docx, re, sys
from pathlib import Path
R=Path(r"W:/2331 Flood Hazard Maps for Muscat-Dhofar-Musandam_MWR/06-WORKING/03-Hydrology/0.13 REPORTS/Hydrology Final Report- Flood Data Analysis/Report/Final Report/Hydrology Final Report- Flood Data Analysis.docx")
d=docx.Document(R)
ps=d.paragraphs
for i,p in enumerate(ps):
    t=p.text
    if re.search(r'Figure (35|49|36|34)\b',t) and p.style.name.lower().startswith(('caption','normal')) and len(t)<120:
        # look for the nearest inline image before
        for j in range(i,max(i-6,0),-1):
            x=ps[j]._p.xml
            m=re.findall(r'r:embed="(rId\d+)"',x)
            if m:
                for k,rid in enumerate(m):
                    part=d.part.related_parts[rid]
                    name=f"rep/fig_{re.search(r'Figure (\d+)',t).group(1)}_{k}{Path(str(part.partname)).suffix}"
                    open(name,'wb').write(part.blob); print(t[:80],'->',name,len(part.blob))
                break
