"""Every mesh the W46 and W52 tests build, made by the code before this branch and by this branch, compared field by
field (the s01 digest).

    python e06_w46_tests_equal.py

The old generator is ``runs/old``'s ``strips/centres.py`` with its own ``geometry.py`` and ``mesher.resample``,
loaded under other names. Each test function runs twice, once with each generator put in its module's namespace;
every call to ``build_centre_mesh`` is recorded, and the two records must agree call by call.
"""

from __future__ import annotations

import inspect
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from e05_pieces_equal import old_module  # noqa: E402
from s01_mesh import digest  # noqa: E402


def old_generator():
    old_geometry = old_module("strips/geometry.py", "old_geometry")
    old_mesher = old_module("strips/mesher.py", "old_mesher")
    old = old_module("strips/centres.py", "old_centres")
    old.MeshGeometry = old_geometry.MeshGeometry
    old.resample = old_mesher.resample
    return old.build_centre_mesh


def main() -> None:
    import tests.strips.test_centres as tc
    import tests.strips.test_gorge as tg
    from wadi2d.strips.centres import build_centre_mesh as new

    old = old_generator()
    calls = 0
    bad = 0
    for module in (tc, tg):
        tests = [(name, f) for name, f in vars(module).items() if name.startswith("test_") and callable(f)]
        for name, f in tests:
            params = inspect.signature(f).parameters
            runs = [{}]
            if params:  # the parametrised ones: their own marks give the values
                marks = getattr(f, "pytestmark", [])
                values = [m.args for m in marks if m.name == "parametrize"]
                if not values:
                    continue
                keys = [k.strip() for k in values[0][0].split(",")]
                runs = [dict(zip(keys, v if isinstance(v, tuple) else (v,), strict=True)) for v in values[0][1]]
            for kwargs in runs:
                records = {}
                for label, gen in (("new", new), ("old", old)):
                    out = []

                    def recording(*a, _gen=gen, _out=out, **k):
                        mesh = _gen(*a, **k)
                        _out.append(digest(np.zeros(1, bool), mesh))
                        return mesh

                    module.build_centre_mesh = recording
                    try:
                        f(**kwargs)
                        status = "passed"
                    except Exception as error:  # a test may fail on old code by design; the meshes are what count
                        status = f"raised {type(error).__name__}"
                    finally:
                        module.build_centre_mesh = new
                    records[label] = (out, status)
                (a, sa), (b, sb) = records["new"], records["old"]
                same = a == b
                calls += len(a)
                bad += not same
                print(f"{module.__name__.split('.')[-1]}::{name}{kwargs or ''}: {len(a)} meshes, {'identical' if same else 'DIFFERENT'} (new {sa}, old {sb})")
    print(f"{calls} meshes in all, {bad} tests with a difference")


if __name__ == "__main__":
    main()
