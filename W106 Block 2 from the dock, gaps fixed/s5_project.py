"""W106 session 5 (W104's, its paths changed and gap 8 checked): the QGIS project of the four models, opened once more,
its pictures drawn, the four runs compared on the dams, and saved.

No model is changed and nothing is run: the project the four sessions saved is read, each model's own group is listed
(the plugin's pattern: Wadi2D - <model> > Inputs and Results - <run>), the maps for the README are drawn off the
screen, the dock shows each model's results page, and the project is written back.
"""

import json
from pathlib import Path


def scenario(h):
    import importlib.util

    spec = importlib.util.spec_from_file_location("w106_help", Path(h.SCENARIO).parent / "w106_help.py")
    w = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(w)
    w.limits(h, 1.0)
    from qgis.core import QgsFillSymbol, QgsLineSymbol, QgsProject, QgsSingleSymbolRenderer, QgsVectorLayer

    w.read_project(h)
    root = QgsProject.instance().layerTreeRoot()
    tree = []
    for group in root.findGroups(recursive=True):
        tree.append(f"{'  ' * _depth(group)}{group.name()}: {len(group.findLayers())} layers")
    (w.LOGS / "s5_tree.txt").write_text("\n".join(tree), encoding="utf-8")
    h.log("tree:\n" + "\n".join(tree[:80]))
    for model in w.MODELS.values():
        h.check(f"the model group of {model}", any(g.name().endswith(model) for g in root.findGroups(recursive=True)))

    def outline(layer, colour, width="0.6", dash=False):
        if layer is None:
            return None
        symbol = QgsFillSymbol.createSimple({"style": "no", "outline_color": colour, "outline_width": width, "outline_style": "dash" if dash else "solid"})
        copy = QgsVectorLayer(layer.source(), layer.name(), layer.providerType())
        copy.setRenderer(QgsSingleSymbolRenderer(symbol))
        return copy

    def lines(layer, colour, width="0.5"):
        if layer is None:
            return None
        copy = QgsVectorLayer(layer.source(), layer.name(), layer.providerType())
        copy.setRenderer(QgsSingleSymbolRenderer(QgsLineSymbol.createSimple({"color": colour, "width": width})))
        return copy

    rough = w.find_layer("Rough outline of Block 2")
    completed = _first(w.layers_by_title("Domain completed upstream")) or w.find_layer("Completed domain, the outline")
    aligned = w.find_layer("Domain aligned")
    sea = w.find_layer("Outflow lines")
    w.render_map(h, "s5_domain", [lines(sea, "#d40000", "1.0"), outline(rough, "#606060", "0.5", True), outline(completed, "#0a63c9", "0.5"), outline(aligned, "#1b9e3e", "0.3")], aligned)
    subbasins = w.layers_by_title("Subbasins, generated")
    reaches = w.layers_by_title("Reaches, generated")
    h.log(f"generated layers: {[l.source() for l in subbasins]}")
    for n, (sub, reach) in enumerate(zip(subbasins, reaches)):
        w.render_map(h, f"s5_basin_{n}_{Path(sub.source().split('|')[0]).parents[1].name}", [lines(reach, "#0a63c9", "0.6"), outline(sub, "#404040", "0.3"), outline(aligned, "#1b9e3e", "0.4")], aligned)
    for layer in QgsProject.instance().mapLayers().values():
        if layer.name() == "Depth, m":
            run = Path(layer.source()).parents[1].name
            w.render_map(h, f"s5_depth_{run}", [lines(sea, "#d40000", "1.0"), outline(aligned, "#404040", "0.3"), layer], aligned)
    dock = yield from h.open_dock(all_sections=False)
    yield lambda: dock.model.ready
    links, page = dock.results_links, dock.results_page
    for model in w.MODELS.values():
        folder = w.RUNS / model
        if not (folder / "progress.jsonl").is_file():
            continue
        dock.model.open_run(str(folder))
        yield lambda: True
        if dock.panel.results_button.isEnabled():
            dock.panel.results_button.click()
            yield lambda: links.query is None and not page.words.text().startswith("Reading")
            w.pick(page.kind, None) if page.kind.findData(None) >= 0 else None
            page.search.setText("")
            h.log(f"{model} elements of record: {page.table.rowCount()} rows; {page.words.text()[:300]}")
            w.big_shot(h, dock, f"s5_results_{model}")
            if model == "Hybrid2D" and not list((folder / "scenarios").glob("Hybrid 2D*.json")):
                dock.types.show_model()  # session 4's window was closed before it saved its scenario: saved here
                w.save_scenario(h, dock, "Hybrid 2D")
    # the last run's page: the four runs side by side on the dams (his default rows: design lines, else dams)
    from qgis.PyQt.QtCore import Qt

    for i in range(page.runs.count()):
        page.runs.item(i).setCheckState(Qt.Checked)
    page.compare_button.click()
    yield lambda: links.query is None and not links.queue and not page.compare_words.text().startswith("Reading")
    h.log(f"compare: {page.compare_words.text()[:400]}")
    written = links.export_to(w.W106 / "compare_runs.xlsx")
    comparison = links.comparison
    dams = [key for key in (comparison.keys if comparison else []) if key.startswith("dam:")]
    filled = {key: [run for run in comparison.runs if (comparison.values.get((run, key)) or (None,))[0] is not None] for key in dams} if comparison else {}
    h.log(f"gap 8: compared rows {comparison.keys if comparison else None}; runs with an inflow per dam {filled}")
    h.check("gap 8: Compare runs lines each of the five dams up across the four model types", len(dams) == 5 and all(len(v) == 4 for v in filled.values()), filled)
    (w.LOGS / "s5_compare.json").write_text(json.dumps({"runs": comparison.runs, "rows": comparison.table()} if comparison else {}, indent=1), encoding="utf-8")
    h.check("the four runs compared in the dock, the table in Excel", written is not None and written.is_file(), page.compare_words.text()[:300])
    w.big_shot(h, dock, "s5_compare_runs")
    w.save_project(h)
    sizes = {p.name: p.stat().st_size for p in [w.PROJECT] if p.is_file()}
    h.log(f"project: {json.dumps(sizes)}")


def _depth(group) -> int:
    depth, node = 0, group.parent()
    while node is not None and node.parent() is not None:
        depth, node = depth + 1, node.parent()
    return depth


def _first(items):
    return items[0] if items else None
