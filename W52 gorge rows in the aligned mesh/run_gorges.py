"""Run and read the three synthetic gorges with gorge rows (W52).

    .venv\Scripts\python "W52 gorge rows in the aligned mesh\run_gorges.py" run|read [case ...] [ce20 ce10] [rows=0,2,4,6] [sq2]

`run` makes the centre-mesh runs of each case at each along spacing and rows setting (and the gentle sine's 2 m
squares with `sq2`); `read` reads them all against the 2 m squares of the same table rule (W49's for the straight and
the tight sine, this folder's for the gentle) and writes `gorge_rows.json`.
"""

from __future__ import annotations

import json
import sys

import gorges as g

CASES = ("narrow", "narrow_gentle", "narrow_sine")


def label(mesh: str, rows: int) -> str:
    return f"{mesh}_rows{rows}"


if __name__ == "__main__":
    what = sys.argv[1]
    cases = [a for a in sys.argv[2:] if a in CASES] or list(CASES)
    meshes = [a for a in sys.argv[2:] if a in ("ce20", "ce10", "ce5")] or ["ce20", "ce10"]
    rows = next((tuple(int(v) for v in a.split("=")[1].split(",")) for a in sys.argv[2:] if a.startswith("rows=")), (0, 2, 4, 6))
    if what == "run":
        if "sq2" in sys.argv:
            for case in cases:
                if case == "narrow_gentle":
                    name, data = g.job(case, "sq2")
                    g.run(f"{case}_steady_sq2", data, case)
        for case in cases:
            for mesh in meshes:
                for n in rows:
                    name, data = g.job(case, mesh, tag=f"rows{n}", strips={"gorge_rows": n})
                    g.run(name, data, case)
    else:
        out = json.loads((g.HERE / "gorge_rows.json").read_text()) if (g.HERE / "gorge_rows.json").is_file() else {}
        for case in cases:
            runs = {label(m, n): g.RUNS / case / f"{case}_{m}_rows{n}" for m in meshes for n in rows}
            res = g.read(case, runs)
            g.show(case, res)
            out[case] = res
        (g.HERE / "gorge_rows.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
