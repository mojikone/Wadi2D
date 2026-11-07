"""W39's item 6 through the real dock, his word of 2026-11-07 ("totally unnecessary"): on the HMS route a run writes
network series only for what entered the grid, so the Result lines panel offers no phantom lumped element.

W39's PMP hybrid: S13 lumped, the other 17 subbasins rain-on-grid, Bidah 03 at 30 m. Before, the run wrote 40 network
series, Z4C reading 9,130 m3/s that the run never carried; now it writes S13's alone.
"""


def settled(lines):
    return lambda: lines.query is None and not lines.waiting


def scenario(h):
    from pathlib import Path

    h.VENV = Path(r"D:\Mojtaba\Renardet\Wadi2D\.venv\Scripts\python.exe")
    h.TOTAL_LIMIT = 3600.0
    ground = h.Bidah()
    cn = h.add_raster(h.BLOCK / "HEC_HMS_Block_02" / "Hydrology Data" / "CN_Include_Hill_Area.tif", "cn")
    dock = yield from h.open_dock()
    hy, storm = dock.hydrology, dock.storm
    h.set_rain_job(dock, ground, "pmp_hybrid", dx=30.0, rain=10.0, hours=1.0, sim_hours=48.0, pixels=False)
    dock.points.layer.setLayer(ground.lines)
    dock.points.name.setField("name")
    hy.cn.raster.setLayer(cn)
    hy.folder.setFilePath(str(h.BLOCK / "HEC_HMS_Block_02"))
    yield lambda: hy.files["basin"].count() > 0
    hy.files["met"].setCurrentText("FM_PMP.met")
    storm.kind.setCurrentIndex(storm.kind.findData("hms"))
    for r in range(hy.table.rowCount()):
        hy.table.cellWidget(r, 1).setCurrentText("lumped" if hy.table.item(r, 0).text() == "S13" else "2d")
    folder = h.RUNS / "pmp_hybrid"
    yield from h.run(dock, 3000)
    done = h.events(folder, "done")
    h.check("the run finished", bool(done) and done[-1].get("code") == 0, dock.panel.message.text()[:300])
    written = sorted(p.stem for p in (folder / "series").glob("network_*.csv"))
    h.log(f"network series: {written}")
    h.check("only S13's network series is written", written == ["network_S13"], written)
    dock.panel.lines_button.click()
    lines = dock.line_panel
    yield settled(lines)
    labels = [lines.choice.itemText(i) for i in range(lines.choice.count())]
    lumped = [text for text in labels if text.startswith("Lumped element: ")]
    h.log(f"panel: {lumped}")
    h.check("the panel offers S13 alone as a lumped element", lumped == ["Lumped element: S13"], lumped)
    h.check("the dam lines are still offered", any(text.endswith("Bidah 03") and "Lumped" not in text for text in labels), labels[:6])
