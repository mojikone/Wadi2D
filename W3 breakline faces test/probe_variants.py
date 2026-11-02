"""Settings of each option, chosen on three phases before the full matrix."""
import sys
sys.path.insert(0, ".")
import numpy as np
from concurrent.futures import ProcessPoolExecutor
from options import run, run_dir

V = [
 ("a", lambda *x: run("lattice", *x)),
 ("m", lambda *x: run("lattice", *x, mirror=True)),
 ("dir", lambda *x: run_dir(*x)),
 ("dir+m", lambda *x: run_dir(*x, mirror=True)),
 ("P s1", lambda *x: run("P", *x, sheet=1)),
 ("P s2", lambda *x: run("P", *x, sheet=2)),
 ("P s0", lambda *x: run("P", *x, sheet=0)),
 ("b s1", lambda *x: run("b", *x, sheet=1)),
 ("b s2", lambda *x: run("b", *x, sheet=2)),
 ("b s0", lambda *x: run("b", *x, sheet=0)),
 ("b s1 noskew", lambda *x: run("b", *x, sheet=1, skew=False)),
 ("b s1 noadv", lambda *x: run("b", *x, sheet=1, adv=False)),
 ("b s1 sm5", lambda *x: run("b", *x, sheet=1, smooth=5)),
 ("c s1", lambda *x: run("c", *x, sheet=1)),
 ("c s2", lambda *x: run("c", *x, sheet=2)),
 ("c s0", lambda *x: run("c", *x, sheet=0)),
 ("c s1 f.1", lambda *x: run("c", *x, sheet=1, fmin=0.1)),
 ("c s2 f.1", lambda *x: run("c", *x, sheet=2, fmin=0.1)),
 ("c s1 noskew", lambda *x: run("c", *x, sheet=1, skew=False)),
]
CASES = [(45.,3,0.,0.),(45.,3,0.,5.),(45.,3,0.,10.),(45.,3,2.,5.),(30.,3,0.,0.),(30.,3,2.,0.),(22.5,3,0.,0.),(15.,3,0.,0.),(0.,3,0.,0.)]
def job(a):
    n, c = a
    r = dict(V)[n](*c)
    return n, c, r
if __name__ == "__main__":
    jobs = [(n, c) for n, _ in V for c in CASES]
    out = {}
    with ProcessPoolExecutor(11) as ex:
        for n, c, r in ex.map(job, jobs):
            out[(n, c)] = r
    head = " ".join(f"{c[0]:>5.1f}/{int(c[2])}/{int(c[3]):<2d}" for c in CASES)
    print("Strip-reference error %, columns theta/bank/offset, all 3 cells. Then dt mean.")
    print(f"{'':14s}", head)
    for n, _ in V:
        print(f"{n:14s}", " ".join(f"{out[(n,c)]['err_strip']:+9.2f}" for c in CASES))
    print("\nVs Manning %")
    for n, _ in V:
        print(f"{n:14s}", " ".join(f"{out[(n,c)]['err']:+9.2f}" for c in CASES))
    print("\ndt mean s")
    for n, _ in V:
        print(f"{n:14s}", " ".join(f"{out[(n,c)]['dt']:9.3f}" for c in CASES))
    print("\nQ error %")
    for n, _ in V:
        print(f"{n:14s}", " ".join(f"{out[(n,c)]['qerr']:+9.2f}" for c in CASES))
