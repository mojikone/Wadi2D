import sys, pathlib, shutil, tempfile
from hecdss import HecDss
for f in sys.argv[1:]:
    d = pathlib.Path(tempfile.mkdtemp()); shutil.copy2(f, d/"x.dss"); h = HecDss(str(d/"x.dss"))
    g = h.get(h.get_catalog().uncondensed_paths[0]); h.close()
    print("LEN", pathlib.Path(f).name, len(g.srsDefinition), g.srsDefinition[:44])
