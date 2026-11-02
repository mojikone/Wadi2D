"""The full comparison: every option at every angle, width, bank and three lattice phases, plus an eight-phase scan of the pass case."""
import csv, sys, time
sys.path.insert(0, ".")
from concurrent.futures import ProcessPoolExecutor, as_completed
from options import run, run_dir

OPT = {
    "a": ("lattice", {}),
    "m": ("lattice", dict(mirror=True)),
    "ms3": ("lattice", dict(mirror=True, sheet=3)),
    "dir": ("dir", {}),
    "P": ("P", dict(sheet=1)),
    "b": ("b", dict(sheet=2)),
    "c": ("c", dict(sheet=2)),
    "t20": ("tri", dict(sheet=3, h=20.0)),
    "t26": ("tri", dict(sheet=3, h=26.3)),
}
KEYS = ["name","theta","cells","bank","offset","err","err_strip","qerr","dt","nsteps","nelem","nfaces","ns_per_cellstep","build_s","run_s","skew_max","skew_p95","area_min","dn_min","split_cells","clipped_dn","neg_dn","blew"]

def job(a):
    name, theta, cells, bank, off = a
    opt, kw = OPT[name]
    try:
        r = run_dir(theta, cells, bank, off) if opt == "dir" else run(opt, theta, cells, bank, off, **dict(kw))
    except Exception as e:
        r = dict(blew=f"{type(e).__name__}: {e}")
    r.update(name=name, theta=theta, cells=cells, bank=bank, offset=off)
    return r

if __name__ == "__main__":
    jobs = [(n, th, c, b, off) for n in OPT for th in (0., 15., 22.5, 30., 45.) for c in (3, 6, 12) for b in (0., 2.) for off in (0., 5., 10.)]
    extra = [(n, 45., 3, b, off) for n in OPT for b in (0., 2.) for off in (2.5, 7.5, 12.5, 15., 17.5)]
    extra += [(n, th, 3, 0., off) for n in OPT for th in (15., 22.5, 30.) for off in (2.5, 7.5, 12.5, 15., 17.5)]
    t0 = time.time()
    with open("results/matrix.csv", "w", newline="") as f, ProcessPoolExecutor(11) as ex:
        w = csv.DictWriter(f, KEYS, extrasaction="ignore")
        w.writeheader()
        done = 0
        for fut in as_completed([ex.submit(job, j) for j in jobs + extra]):
            w.writerow(fut.result()); f.flush(); done += 1
            if done % 100 == 0:
                print(done, len(jobs) + len(extra), round(time.time() - t0), flush=True)
    print("done", round(time.time() - t0), flush=True)
