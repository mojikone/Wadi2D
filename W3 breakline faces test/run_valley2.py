"""The reading of run_valley checked: does the wadi loss come from the coarse plane cells?"""
import csv, sys
sys.path.insert(0, ".")
from concurrent.futures import ProcessPoolExecutor
from run_valley import run
if __name__ == "__main__":
    names = ["quad by change of slope", "quad by change of slope max20", "quad by change of slope eps05", "quad by slope max20"]
    with ProcessPoolExecutor(4) as ex:
        res = list(ex.map(run, names))
    ref = list(csv.DictReader(open("results/valley.csv")))[0]
    q0, w0, d0, d3, c0 = float(ref["qpeak"]), float(ref["qwadi"]), float(ref["d1000"]), float(ref["d300"]), float(ref["cell_steps"])
    print(f"{'mesh':34s} {'cells':>7s} {'x ref':>7s} {'Q %':>6s} {'Qw %':>6s} {'tpk h':>6s} {'d1000 %':>8s} {'d300 %':>7s} {'share10':>7s} {'share40':>7s}")
    for r in res:
        print(f"{r['name']:34s} {r['cells']:7d} {r['cell_steps']/c0:7.3f} {(r['qpeak']/q0-1)*100:+6.1f} {(r['qwadi']/w0-1)*100:+6.1f} {r['tpeak']/3600:6.2f} {(r['d1000']/d0-1)*100:+8.1f} {(r['d300']/d3-1)*100:+7.1f} {r['share10']:7.2f} {r['share40']:7.2f}")
