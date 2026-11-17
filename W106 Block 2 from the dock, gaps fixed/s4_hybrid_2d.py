"""W106 session 4 through the real dock: the Hybrid 2D model on a generated basin (gap 3), with no way round.

The project of session 3 opened; the Hybrid 2D card, its own folder; the HAT-J4 point layer of session 3; Generate
basin; Last points: the five dams and HAT-J4; the area reduction as in Hybrid Lumped; Run. The card sets the generated
basin's rule: the catchments above the last points lumped, each entering at its own outlet, no reach or reservoir routed
lumped, the dams 2D pools behind their crest lines, every lumped subbasin read at its last point's area.
"""

from pathlib import Path


def scenario(h):
    import importlib.util

    spec = importlib.util.spec_from_file_location("s3", Path(h.SCENARIO).parent / "s3_hybrid_lumped.py")
    s3 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(s3)
    w = s3.helper(h)
    w.limits(h, 3.0)
    session = Path(h.P).name
    steps = w.Steps(h, session)
    w.read_project(h)
    dock = yield from h.open_dock(all_sections=False)
    yield lambda: dock.model.ready
    yield from s3.hybrid(h, w, dock, steps, session, "hybrid_2d", "outlets", "Hybrid 2D")
