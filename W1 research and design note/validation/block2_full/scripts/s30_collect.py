"""All tables of the report, as Markdown, from the run folders. Each site reads the run at its own storm area."""
import json
import sys

sys.path.insert(0, r"D:\Mojtaba\Renardet\Wadi2D\W1 research and design note\validation\block2_full\scripts")
from analyze import done_event, line_stats
from common import OUT, SITES, hms_reference
from lumped_ref import run_at, stats

from wadi2d.arf import run_name

REF = hms_reference()
ORDER = ["Faydh 01", "Bidah 03", "R5A", "R2A", "Z4C"]


def study(name):
    out = {}
    for site in ORDER:
        run = OUT / "runs" / name / "runs" / run_name(round(SITES[site], 4))
        if (run / "series").exists():
            out[site] = (line_stats(run, site), line_stats(run, f"{site} ring"))
    return out


b40 = study("arf_b20_n040")
b100 = study("arf_b20_n100")
c100 = study("arf_c20_h100")
print("| Site, storm area km2 | HMS m3/s, h, Mm3 | (b) n 0.04 | ratio | (b) n 0.1 | ratio | (c) 20 m | ratio | ring ratio |")
print("|---|---|---|---|---|---|---|---|---|")
for s in ORDER:
    r = REF[s]
    cells = [f"| {s}, {SITES[s]:.1f} | {r['peak']:.0f}, {r['t_h']:.2f}, {r['vol_m3']/1e6:.2f} |"]
    for d in (b40, b100, c100):
        if s in d:
            a, g = d[s]
            cells.append(f" {a['peak']:.0f}, {a['t_h']:.2f}, {a['vol_m3']/1e6:.2f} | {a['peak']/r['peak']:.2f} / {a['vol_m3']/r['vol_m3']:.3f} |")
        else:
            cells.append(" - | - |")
    if s in c100:
        cells.append(f" {c100[s][1]['peak']/r['peak']:.2f} / {c100[s][1]['vol_m3']/r['vol_m3']:.3f} |")
    print("".join(cells))

print()
print("Manning, storm area 74.3, peak ratio to the lumped engine at that area")
runs = ["c20_A74_n040", "c20_A74_h050", "c20_A74_h100", "c20_A74_h200", "c20_A74_u100", "c10_A74_h100"]
lump = run_at(74.304).outflow
print("| Run | " + " | ".join(ORDER) + " | time of peak h, " + ", ".join(ORDER) + " |")
print("|---|---|---|---|---|---|---|")
print("| Lumped | " + " | ".join(f"{stats(lump[s])['peak']:.0f}" for s in ORDER) + " | " + ", ".join(f"{stats(lump[s])['t_h']:.2f}" for s in ORDER) + " |")
for n in runs:
    run = OUT / "runs" / n
    if not (run / "series").exists():
        continue
    a = {s: line_stats(run, s) for s in ORDER}
    print(f"| {n} | " + " | ".join(f"{a[s]['peak']/stats(lump[s])['peak']:.2f}" for s in ORDER) + " | " + ", ".join(f"{a[s]['t_h']:.2f}" for s in ORDER) + " |")

print()
print("Speed")
for label, runs in (("c20 n040", [OUT / "runs" / "c20_A74_n040"]),
                    ("c20 h100 study", sorted((OUT / "runs" / "arf_c20_h100" / "runs").glob("A*"))),
                    ("b20 n040 study", sorted((OUT / "runs" / "arf_b20_n040" / "runs").glob("A*"))),
                    ("b20 n100 study", sorted((OUT / "runs" / "arf_b20_n100" / "runs").glob("A*"))),
                    ("c10", [OUT / "runs" / "c10_A74_h100"])):
    for run in runs:
        if not (run / "progress.jsonl").exists():
            continue
        e = done_event(run)
        d, st = e["done"], e["start"]
        if not d:
            continue
        print(f"{label} {run.name}: cells {st['cells']} tiles {st['tiles']} tables {st['tables_s']} s, loop {d['loop_s']} s, steps {d['steps']}, sim {d['t']/3600:.0f} h, mean dt {d['t']/d['steps']:.3f}, dt_min {d['dt_min']:.3f}, ms/step {1e3*d['loop_s']/d['steps']:.2f}, balance {d['balance']['relative_error']:.1e}, wet {d['wet_area_km2']}")
