"""Read the mean-of-two face diagnosis (W52) beside the same meshes on the engine's own rule."""

import json

import gorges as g

out = {}
for case, specs in {"narrow_sine": [("ce20", 0), ("ce20", 2), ("ce10", 0)], "narrow": [("ce20", 0)]}.items():
    runs = {}
    for mesh, rows in specs:
        runs[f"{mesh}_rows{rows}"] = g.RUNS / case / f"{case}_{mesh}_rows{rows}"
        runs[f"{mesh}_rows{rows}_meanface"] = g.RUNS / case / f"{case}_{mesh}_rows{rows}_meanface"
    res = g.read(case, runs)
    g.show(case, res)
    out[case] = res
(g.HERE / "mean_face.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
