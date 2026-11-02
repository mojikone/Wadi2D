import sys, time, pathlib
sys.path.insert(0, r"D:\Mojtaba\Renardet\Wadi2D")
from wadi2d.hms.dss import open_dss
t = time.time()
with open_dss(pathlib.Path(sys.argv[1])) as d:
    ps = d.grid_pathnames(); print("RESULT records", len(ps), "first", ps[0] if ps else None, "catalogue s %.1f" % (time.time()-t), flush=True)
    t = time.time()
    r = d.read_grid(ps[0]); print("RESULT shape", r.values.shape, "cell", r.cell_size, "ll", r.lower_left_x, r.lower_left_y, "units", r.units, "read s %.1f" % (time.time()-t), flush=True)
