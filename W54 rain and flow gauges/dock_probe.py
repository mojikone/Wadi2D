"""Why the dock finds no engine in the throwaway QGIS: the engine query of the dock, its exit code and its words."""

import os
import sys


def scenario(h):
    sys.path.insert(0, str(h.REPO / "plugin"))
    from wadi2d_qgis.engine_process import EngineQuery, engine_environment

    env = engine_environment()
    for key in ("PYTHONHOME", "PYTHONPATH", "PATH", "PROJ_LIB", "GDAL_DATA", "QT_PLUGIN_PATH", "PYTHONUTF8"):
        h.log(f"env {key} = {env.value(key)[:300]!r}  (QGIS: {os.environ.get(key, '')[:120]!r})")
    answer = []
    query = EngineQuery(f'"{h.VENV}" "{h.P / "engine.py"}"')
    query.done.connect(lambda code, out, err: answer.append((code, out[:200], err[-2000:])))
    query.start(["schema"])
    yield lambda: bool(answer)
    code, out, err = answer[0]
    h.check("engine schema answers", code == 0, f"code {code}; out {out!r}; err {err!r}")
    h.log(f"ERR {err}")
