"""What the W99 dock scenarios share: a dock filled in every section as a user would, and the job it builds.

Not a scenario: ``dock_model_saved_a.py`` and ``dock_model_saved_b.py`` load it by path.
"""

import json
import shutil
from pathlib import Path

LAYER_NAMES = ("terrain", "domain bidah", "outlets", "mixed outlets", "dam lines", "w99 crests", "w99 refinement", "w99 ponds")


def shared(h) -> Path:
    """One folder both scenarios see: run_check wipes only its own scenario's folder."""
    folder = Path(h.P).parent / "model_shared"
    folder.mkdir(exist_ok=True)
    return folder


def extra_layers(h, ground):
    """Layers of this check's own, written beside the first scenario's data so the saved project finds them again."""
    jobs = json.loads((h.VALIDATION / "jobs" / "c10_A74_h100.json").read_text(encoding="utf-8"))
    dam = next(k["coordinates"] for k in jobs["outputs"]["lines"] if k["name"] == "Bidah 03")
    crests = h.add_vector(h.geojson("w99_crests", [h.line(dam, name="Bidah 03", crest_z=104.0)]), "w99 crests", ground.crs)
    box = ground.domain.extent()
    cx, cy = box.center().x(), box.center().y()
    lines = [
        h.line([[cx - 600.0, cy], [cx + 600.0, cy]], name="wadi a"),
        h.line([[cx, cy - 500.0], [cx, cy + 500.0]], name="wadi b"),
    ]
    refinement = h.add_vector(h.geojson("w99_refinement", lines), "w99 refinement", ground.crs)
    ring = [[cx - 80.0, cy - 80.0], [cx + 80.0, cy - 80.0], [cx + 80.0, cy + 80.0], [cx - 80.0, cy + 80.0], [cx - 80.0, cy - 80.0]]
    pond = {"type": "Feature", "properties": {"level": 91.5}, "geometry": {"type": "Polygon", "coordinates": [ring]}}
    ponds = h.add_vector(h.geojson("w99_ponds", [pond]), "w99 ponds", ground.crs)
    record = h.DATA / "w99_flow.csv"
    record.write_text("time,flow_m3s\n0,0\n30,12.5\n60,3\n", encoding="utf-8")
    return {"crests": crests, "refinement": refinement, "ponds": ponds, "record": str(record)}


def find_layers(project):
    """The same layers by name, in a project read from disk."""
    found = {}
    for name in LAYER_NAMES:
        layers = project.mapLayersByName(name)
        found[name] = layers[0] if layers else None
    return found


def fill(dock, dem, domain, outlets, lines, crests, refinement, ponds, record, folder):
    """Every section moved off its defaults, tables with rows a user pinned."""
    t, m, hy, s = dock.terrain, dock.mesh, dock.hydrology, dock.storm
    t.dem.setLayer(dem)
    t.dx.setValue(30.0)
    t.domain.setLayer(domain)
    t.manning.box.setValue(0.045)
    t.fill_pits.setChecked(True)

    m.enabled.setChecked(True)
    m.coarse.setValue(120.0)
    m.fine_area.setValue(3.0)
    m.mid_area.setValue(1.5)
    m.lines.layer.setLayer(refinement)
    m.lines.table.cellWidget(0, 1).setValue(30.0)  # near of the first line, pinned by the edit
    m.lines.table.cellWidget(0, 2).setValue(3)
    m.local_steps.setChecked(False)
    m.bank_rise.setValue(1.5)
    m.crest_height.setValue(0.8)

    hy.cn.box.setValue(78.0)
    hy.loss.enabled.setChecked(True)
    hy.loss.rate.setValue(12.0)
    hy.routing.setCurrentIndex(hy.routing.findData("conserving"))

    s.kind.setCurrentIndex(s.kind.findData("hypothetical"))
    s.design_depth.setValue(120.0)
    s.design_hours.setValue(6.0)
    s.pattern.set_rows([(0.0, 0.0), (25.0, 10.0), (50.0, 62.5), (75.0, 90.0), (100.0, 100.0)])
    s.arf_mode.setCurrentIndex(s.arf_mode.findData("area"))
    s.storm_area.setValue(74.3)
    s.arf.set_rows([(10.0, 0.99), (100.0, 0.913), (1000.0, 0.7)])

    st = dock.structures
    st.layers["crest_line"].setLayer(crests)
    st.fields["crest_line"]["crest_z"].setField("crest_z")
    st.start_water.ponds.setLayer(ponds)
    st.start_water.pond_level.setField("level")
    start = st.start_water.table.cellWidget(0, 1)
    start.setCurrentIndex(start.findData("level"))
    st.start_water.table.cellWidget(0, 2).setValue(97.25)
    st.terrain_map.setChecked(True)

    b = dock.boundaries
    b.layer.setLayer(outlets)
    b.kind.setCurrentText("normal")
    b.value.setValue(0.008)
    b.table.cellWidget(0, 1).setCurrentText("stage")
    b.table.cellWidget(0, 2).setValue(2.5)

    dock.points.layer.setLayer(lines)
    dock.points.name.setField("name")

    g = dock.gauges
    g.add_row("flow")
    g.set_row(0, name="Bidah gauge", file=record, at="Bidah 03")
    g.start.setText("2021-10-04 00:00")

    p = dock.panel
    p.folder.setFilePath(str(folder))
    p.duration.setValue(2.25)
    p.maps.setCurrentIndex(1)
    p.pixels.setChecked(False)
    p.limiter.setChecked(True)
    p.backend.setCurrentIndex(p.backend.findData("cpu"))
    p.map_title.setText("W99 saved model")

    dock.study.spacing.setCurrentIndex(dock.study.spacing.findData("listed"))
    dock.study.listed.setText("10, 30, 90")


def built(dock, out: Path) -> dict:
    """The job the dock builds now, into ``out`` (emptied first), as plain JSON; its input files stay in ``out``."""
    from wadi2d_qgis.job_builder import build_job

    shutil.rmtree(out, ignore_errors=True)
    return json.loads(json.dumps(build_job(dock._collect(), out)))


def input_files(out: Path) -> dict:
    """Each input file the job wrote, by name, as text."""
    folder = out / "inputs"
    return {path.name: path.read_text(encoding="utf-8") for path in sorted(folder.glob("*"))} if folder.is_dir() else {}


def normal(job: dict, out: Path) -> dict:
    """A job with its own output folder taken out of every path and its name dropped, to compare two folders' jobs."""
    text = json.dumps(job)
    for form in (str(out), str(out).replace("\\", "/")):
        text = text.replace(json.dumps(form)[1:-1], "<out>")
    found = json.loads(text)
    found.get("project", {}).pop("name", None)
    return found


def plain_paths(value):
    """A model's states with every layer source written one way: a project read from disk gives forward slashes."""
    if isinstance(value, dict):
        return {key: item.replace("\\", "/") if key == "source" and isinstance(item, str) else plain_paths(item) for key, item in value.items()}
    if isinstance(value, list):
        return [plain_paths(item) for item in value]
    return value


def differences(a, b, path="", within=0.0) -> list[str]:
    """Dotted paths where two JSON values differ; numbers may stand ``within`` apart."""
    if isinstance(a, dict) and isinstance(b, dict):
        found = []
        for key in sorted(set(a) | set(b)):
            if key not in a or key not in b:
                found.append(f"{path}{key} (only in {'second' if key not in a else 'first'})")
            else:
                found += differences(a[key], b[key], f"{path}{key}.", within)
        return found
    if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        return [d for n, (x, y) in enumerate(zip(a, b)) for d in differences(x, y, f"{path}{n}.", within)]
    if within and isinstance(a, float) and isinstance(b, float) and abs(a - b) <= within:
        return []
    return [] if a == b else [f"{path.rstrip('.')}: {str(a)[:60]} != {str(b)[:60]}"]
