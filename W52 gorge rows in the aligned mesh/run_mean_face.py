"""Run the mean-of-two face diagnosis (W52) on gorge cases: `python run_mean_face.py case:mesh:rows ...`."""

import sys

import gorges as g

for spec in sys.argv[1:]:
    case, mesh, rows = spec.split(":")
    name, data = g.job(case, mesh, tag=f"rows{rows}_meanface", strips={"gorge_rows": int(rows)})
    g.run(name, data, case, runner=[sys.executable, str(g.HERE / "mean_face_engine.py")])
