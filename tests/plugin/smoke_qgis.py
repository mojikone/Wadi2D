# Wadi2D QGIS plugin tests. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Headless smoke test on QGIS's own Python: the real dock, the real process wrapper, the fake engine.

Started by ``test_smoke_qgis.py`` through ``python-qgis-ltr.bat`` with ``QT_QPA_PLATFORM=offscreen``. Arguments:
the engine's Python (the project venv, so that QGIS's environment really has to be cleaned for it to start).
Prints ``SMOKE PASSED`` as its last line. Settings go to a temporary profile.
"""

from __future__ import annotations

import faulthandler
import importlib
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parents[1] / "plugin"), str(HERE), str(HERE.parents[1] / "tools")]
faulthandler.enable()

WORK = Path(tempfile.mkdtemp(prefix="wadi2d_smoke_"))
os.environ["QGIS_CUSTOM_CONFIG_PATH"] = str(WORK / "profile")
os.environ["WADI2D_FAKE_STEP_S"] = "0.08"

import fake_engine  # noqa: E402
from qgis.core import (  # noqa: E402
    QgsApplication,
    QgsColorRampShader,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsRasterLayer,
    QgsVectorLayer,
)
from qgis.gui import QgsMapCanvas  # noqa: E402
from qgis.PyQt.QtCore import QCoreApplication  # noqa: E402
from qgis.PyQt.QtWidgets import QMainWindow  # noqa: E402

app = QgsApplication([], True)
app.setPrefixPath(os.environ["QGIS_PREFIX_PATH"], True)
app.initQgis()

import wadi2d_qgis  # noqa: E402
from wadi2d_qgis import settings  # noqa: E402
from wadi2d_qgis.job_builder import problems  # noqa: E402
from wadi2d_qgis.protocol import PROGRESS_FILE, STOP_FILE, pid_alive, read_run_info  # noqa: E402

UTM = QgsCoordinateReferenceSystem("EPSG:32640")
WGS84 = QgsCoordinateReferenceSystem("EPSG:4326")
PROJECT = QgsProject.instance()


class Iface:
    """The few calls the plugin makes on QGIS's interface."""

    def __init__(self) -> None:
        self.window = QMainWindow()
        self.canvas = QgsMapCanvas(self.window)
        self.window.setCentralWidget(self.canvas)
        self.canvas.setDestinationCrs(UTM)
        self.icons: list = []
        self.menu: list = []

    def mainWindow(self):
        return self.window

    def mapCanvas(self):
        return self.canvas

    def addToolBarIcon(self, action):
        self.icons.append(action)

    def removeToolBarIcon(self, action):
        self.icons.remove(action)

    def addPluginToMenu(self, _menu, action):
        self.menu.append(action)

    def removePluginMenu(self, _menu, action):
        self.menu.remove(action)

    def addDockWidget(self, area, dock):
        self.window.addDockWidget(area, dock)

    def removeDockWidget(self, dock):
        self.window.removeDockWidget(dock)


def say(text: str) -> None:
    print(f"ok: {text}", flush=True)


def check(condition, text: str) -> None:
    if not condition:
        raise AssertionError(text)
    say(text)


def pump(condition, timeout: float = 30.0, what: str = "a condition") -> None:
    limit = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > limit:
            raise TimeoutError(f"gave up waiting for {what}")
        QCoreApplication.processEvents()
        time.sleep(0.005)


def mode(name: str) -> None:
    os.environ["WADI2D_FAKE_MODE"] = name


def to_wgs84(x: float, y: float) -> QgsPointXY:
    return QgsCoordinateTransform(UTM, WGS84, PROJECT).transform(QgsPointXY(x, y))


def line_layer(name: str, fields: str, points, crs="EPSG:32640", attributes=None, kind="LineString"):
    layer = QgsVectorLayer(f"{kind}?crs={crs}{fields}", name, "memory")
    feature = QgsFeature(layer.fields())
    feature.setGeometry(QgsGeometry.fromPolylineXY(points) if isinstance(points, list) else points)
    if attributes:
        feature.setAttributes(attributes)
    layer.dataProvider().addFeature(feature)
    layer.updateExtents()
    PROJECT.addMapLayer(layer, False)
    return layer


def finished_run(dock) -> None:
    pump(lambda: dock.run is None and dock.panel.run_button.isEnabled(), what="the run to end")


def start(dock) -> None:
    dock.panel.run_button.click()
    pump(lambda: dock.run is not None, what="the run to start")


def group(name: str):
    """A run's results group, under its model's group (W68)."""
    from wadi2d_qgis.layer_groups import results_title

    return PROJECT.layerTreeRoot().findGroup(results_title(name))


def qgis_loader() -> None:
    """QGIS's own plugin loader, on a copy made by the installer."""
    import install_plugin
    import qgis.utils

    folder = WORK / "plugins"
    install_plugin.install(folder)
    qgis.utils.plugin_paths[:] = [str(folder)]
    sys.path.insert(0, str(folder))
    for name in [name for name in sys.modules if name.startswith("wadi2d_qgis")]:
        del sys.modules[name]
    qgis.utils.updateAvailablePlugins()
    check("wadi2d_qgis" in qgis.utils.available_plugins, "QGIS's loader finds the installed plugin")
    check(qgis.utils.pluginMetadata("wadi2d_qgis", "name") == "Wadi2D", "QGIS reads metadata.txt")
    check(qgis.utils.loadPlugin("wadi2d_qgis"), "QGIS's loader imports it")
    check("wadi2d_qgis" in sys.modules, "from the installed copy")
    sys.path.remove(str(folder))
    for name in [name for name in sys.modules if name.startswith("wadi2d_qgis")]:
        del sys.modules[name]


def pick(combo, key) -> None:
    combo.setCurrentIndex(combo.findData(key))


def storm_sources(dock) -> None:
    """The Rain source of W65: one choice, only its fields, and for each kind the job the old section wrote."""
    from wadi2d_qgis.storm_rows import storm_job

    storm, crs = dock.storm, UTM
    sources = [storm.kind.itemData(i) for i in range(storm.kind.count())]
    check(sources == ["hypothetical", "gridded", "gauges", "single"], f"storm: four rain sources without HMS {sources}")
    check(storm.kind.currentData() == "single" and storm.single.currentData() == "uniform", "storm: constant rain first")
    check(storm.reduction.isHidden(), "storm: no area reduction on a single hyetograph")
    storm.rain.setValue(30.0)
    storm.hours.setValue(2.0)
    check(storm.values(crs) == {"rain_mm_h": 30.0, "rain_hours": 2.0}, "storm: constant rain writes what Steady rain wrote")

    pick(storm.single, "hyetograph")
    storm.hyetograph.set_rows([(30.0, 10.0), (60.0, 25.0)])
    old = {"kind": "hyetograph", "rows": [(30.0, 10.0), (60.0, 25.0)]}
    check(storm_job(storm.values(crs)["storm"]) == storm_job(old), "storm: a table writes what Hyetograph table wrote")

    pick(storm.kind, "hypothetical")
    check(not storm.reduction.isHidden() and storm.arf_detail.isHidden(), "storm: the reduction block, None first")
    storm.design_depth.setValue(100.0)
    storm.design_hours.setValue(24.0)
    pattern = [(0.0, 0.0), (50.0, 70.0), (100.0, 100.0)]
    storm.pattern.set_rows(pattern)
    old = {"kind": "hypothetical", "depth_mm": 100.0, "hours": 24.0, "pattern": pattern, "area_km2": 0.0, "arf": []}
    check(storm_job(storm.values(crs)["storm"]) == storm_job(old), "storm: a design storm with no reduction as before")
    pick(storm.arf_mode, "area")
    check(not storm.arf_detail.isHidden(), "storm: one storm area shows the area and the table")
    storm.storm_area.setValue(200.0)
    storm.arf.set_rows([(10.0, 0.95), (1000.0, 0.7)])
    old = {**old, "area_km2": 200.0, "arf": [(10.0, 0.95), (1000.0, 0.7)]}
    check(storm_job(storm.values(crs)["storm"]) == storm_job(old), "storm: a reduced design storm as before")
    pick(storm.arf_mode, "study")
    check(not storm.study_label.isHidden() and "storm areas" in storm.study_label.text(), "storm: the study's areas")
    check(storm_job(storm.values(crs)["storm"]) == storm_job(old), "storm: the study reads the same table")
    pick(storm.arf_mode, "given")
    check(storm.arf_detail.isHidden() and not storm.given_box.isHidden(), "storm: a given factor shows its one number")
    storm.arf_factor.setValue(0.7)
    given = storm_job(storm.values(crs)["storm"])
    check(given.get("arf_factor") == 0.7 and "arf" not in given and "storm_area_km2" not in given,
          f"storm: a given factor writes the factor alone {given}")  # fmt: skip
    pick(storm.arf_mode, "study")
    check(storm.given_box.isHidden(), "storm: the given factor hidden under the study")
    storm.arf.set_rows([])
    check(any("reduction table" in p for p in problems({**dock._collect(), "output": str(WORK)})),
          "storm: a reduction with no table is refused before the run")  # fmt: skip

    pick(storm.kind, "gridded")
    path = WORK / "rain.nc"
    storm.rain_file.setFilePath(str(path))
    pick(storm.arf_mode, "none")
    check(not storm.grid_note.isHidden(), "storm: a gridded file says observed rain takes no reduction")
    grid = storm.values(crs)["storm"]
    old = {"kind": "gridded", "file": str(path), "variable": "", "choices": [], "units": grid["units"],
           "interval_min": 0.0, "stamp": grid["stamp"], "start": "", "arf_on": False, "area_km2": 200.0, "arf": []}  # fmt: skip
    check(storm_job(grid) == storm_job(old), "storm: an observed grid as before")
    pick(storm.arf_mode, "area")
    storm.arf.set_rows([(10.0, 0.9), (1000.0, 0.6)])
    old = {**old, "arf_on": True, "arf": [(10.0, 0.9), (1000.0, 0.6)]}
    check(storm_job(storm.values(crs)["storm"]) == storm_job(old), "storm: a grid of point depths as before")
    pick(storm.arf_mode, "given")
    given = storm_job(storm.values(crs)["storm"])
    check(given.get("arf_factor") == 0.7 and "arf" not in given and "storm_area_km2" not in given,
          f"storm: a grid with a given factor {given}")  # fmt: skip
    pick(storm.arf_mode, "area")

    storm_gauges(dock, crs)

    pick(storm.kind, "single")
    pick(storm.single, "uniform")
    pick(storm.arf_mode, "none")


def storm_gauges(dock, crs) -> None:
    """W77: the rain gauges in Storm's Rain gauges page, flow and level gauges in 7b; one table's job for the same rows."""
    from wadi2d_qgis.gauge_rows import GaugeRow, joined_gauges

    storm, table = dock.storm, dock.storm.gauge_table
    pick(storm.kind, "gauges")
    check(not table.isHidden() and table.kinds == ("rain",), "storm: the rain gauges' own table")
    check(list(dock.gauges.gauges.add_buttons) == ["flow", "level"], "gauges: 7b keeps flow and level gauges only")
    record = WORK / "gauge.csv"
    record.write_text("minute,mm\n10,1\n", encoding="utf-8")
    table.add_row("rain")
    table.table.item(0, 0).setText("West")
    table.table.item(0, table.at_column).setText("400100, 2699500")
    table.set_row(0, file=str(record))
    pick(storm.gauge_method, "inverse_distance")
    check(storm.gauge_radius.isEnabled(), "storm: the radius for inverse distance")
    storm.gauge_radius.setValue(5000.0)
    storm.gauge_start.setText("2021-10-04 00:00")
    dock.gauges.add_row("flow")
    dock.gauges.table.item(0, 0).setText("Dam")
    dock.gauges.table.item(0, dock.gauges.gauges.at_column).setText("Outlet")
    dock.gauges.set_row(0, file=str(record))
    joined = joined_gauges({**storm.values(crs), **dock.gauges.values(crs)})
    old = [
        GaugeRow("West", "rain", file=str(record), x=400100.0, y=2699500.0),
        GaugeRow("Dam", "flow", file=str(record), at="Outlet"),
    ]
    settings = {"method": "inverse_distance", "radius_m": 5000.0, "gaps": "error", "start": "2021-10-04 00:00"}
    check(joined["storm"] == {"kind": "gauges"} and joined["gauges"]["rows"] == old, "storm: the rows of W54's one table")
    check({k: joined["gauges"]["settings"][k] for k in settings} == settings, "storm: its reading rules as before")
    check(joined["gauges"]["settings"]["observed_start"] == "2021-10-04 00:00", "gauges: the records take the rain's start")
    table.rows.clear()
    table._show()
    dock.gauges.rows.clear()
    dock.gauges.gauges._show()
    storm.gauge_start.clear()


def storm_map(dock) -> dict:
    """The storm map's layers by name, in the model's Inputs > Hydrology (W77)."""
    from wadi2d_qgis.layer_groups import HYDROLOGY, SLOT, SLOT_RAIN, input_group, model_name

    group = input_group(model_name(dock.panel.folder.filePath()), HYDROLOGY)
    return {node.layer().name(): node.layer() for node in group.findLayers() if node.customProperty(SLOT) == SLOT_RAIN}


def gauge_preview(dock) -> None:
    """Two rain gauges on the plane, nearest gauge: the map steps from 30 to 10 mm; the old map is replaced."""
    storm, table = dock.storm, dock.storm.gauge_table
    pick(storm.kind, "gauges")
    for name, x, mm in (("West", 400500.0, 15.0), ("East", 401500.0, 5.0)):
        record = WORK / f"rain_{name}.csv"
        record.write_text(f"minute,mm\n5,{mm}\n10,{mm}\n", encoding="utf-8")  # inside the run's 15 min
        row = table.add_row("rain")
        row.name, row.x, row.y, row.file = name, x, 2701000.0, str(record)
    table._show()
    pick(storm.gauge_method, "thiessen")
    storm.preview_button.click()
    pump(lambda: storm.preview_button.isEnabled(), 120.0, "the gauge rain preview")
    rows = storm.preview_table.rows
    check(len(rows) == 1 and abs(rows[0]["depth_mm"] - 20.0) < 1e-6, f"real: two halves of 30 and 10 mm, {rows}")
    shown = storm_map(dock)
    check(len(shown) == 2, f"real: the gauge storm map replaces the last, with its raster {list(shown)}")
    total = shown.get("Total rain depth, before the run")
    stats = total.dataProvider().bandStatistics(1) if total is not None else None
    check(stats is not None and abs(stats.minimumValue - 10.0) < 1e-4 and abs(stats.maximumValue - 30.0) < 1e-4,
          f"real: the raster steps from 10 to 30 mm {stats and (stats.minimumValue, stats.maximumValue)}")  # fmt: skip
    check(total is not None and total.renderer().type() == "singlebandpseudocolor", "real: the raster styled")
    table.rows.clear()
    table._show()


def real_pits(dock, plane, raster_of) -> None:
    """W85 through the real dock and the real engine: a hole in the DEM is named, and with the two ticks it is filled
    and the cell that sets the step is named; the checks land in Inputs > Terrain."""
    import numpy as np
    from osgeo import gdal
    from wadi2d_qgis import layer_groups as g
    from wadi2d_qgis.check_layers import SLOT_CHECKS

    size, pixel, west, north, srs = raster_of
    check(dock.schema.has("terrain.fill_pits") and dock.schema.has("outputs.step_limiter"), "real: the engine has W85's fields")
    z = 120.0 - 0.01 * pixel * np.tile(np.arange(size), (size, 1))
    z[200:202, 199:201] -= 12.0  # 10 m by 10 m and 12 m deep, across the face between two 20 m cells
    path = WORK / "plane_with_a_hole.tif"
    raster = gdal.GetDriverByName("GTiff").Create(str(path), size, size, 1, gdal.GDT_Float32)
    raster.SetGeoTransform((west, pixel, 0.0, north, 0.0, -pixel))
    raster.SetProjection(srs.ExportToWkt())
    raster.GetRasterBand(1).WriteArray(z)
    raster = None
    holed = QgsRasterLayer(str(path), "plane with a hole")
    PROJECT.addMapLayer(holed)
    dock.terrain.dem.setLayer(holed)
    hole_x, hole_y = west + 200 * pixel, north - 201 * pixel

    def run_to(folder: str) -> tuple[Path, str]:
        dock.panel.folder.setFilePath(str(WORK / "real" / folder))
        start(dock)
        out = dock.run.out_dir
        pump(lambda: dock.run is None and dock.panel.run_button.isEnabled(), 180.0, f"the real run {folder}")
        return out, dock.panel.message.text()

    def checks(model: str) -> dict:
        nodes = g.input_group(model, g.TERRAIN).findLayers()
        return {n.layer().name(): n.layer() for n in nodes if n.customProperty(g.SLOT) == SLOT_CHECKS}

    out, said = run_to("hole")
    check("a pit in the ground" in said and "11.8 m deep" in said, f"real: the hole is named, to its rim: {said}")
    check("tick Fill pits" in said, "real: and the dock is told what to tick")
    shown = checks(out.name)
    check(list(shown) == ["Pits in the ground: small and deep"], f"real: the pit in Inputs > Terrain {list(shown)}")
    point = next(shown["Pits in the ground: small and deep"].getFeatures())
    at = point.geometry().asPoint()
    check(abs(at.x() - hole_x) <= 20.0 and abs(at.y() - hole_y) <= 20.0, f"real: at the hole ({at.x():.0f}, {at.y():.0f})")
    check(abs(point["depth_m"] - 11.8) < 0.1 and point["filled"] == 0, f"real: 11.8 m to its rim, not filled {point['depth_m']}")

    dock.terrain.fill_pits.setChecked(True)
    dock.panel.limiter.setChecked(True)
    out, said = run_to("hole_filled")
    check("filled to its spill level" in said and "1 pits filled" in said, f"real: the hole is filled: {said}")
    job = json.loads((out / "job.json").read_text(encoding="utf-8"))
    check(job["terrain"]["fill_pits"] is True and job["outputs"]["step_limiter"] == "layer", "real: both ticks in the job")
    ran = json.loads((out / "config.resolved.json").read_text(encoding="utf-8"))
    fills = [o for o in ran["terrain"]["objects"] if o["kind"] == "fill" and o["name"].startswith("pit fill")]
    check(len(fills) == 2, f"real: the two cells of the hole are fill objects of the job as it ran, {len(fills)}")
    lines = (out / PROGRESS_FILE).read_text(encoding="utf-8").splitlines()
    named = [json.loads(line) for line in lines if '"ev": "limiter"' in line]
    check(len(named) >= 1 and all("dt_without_tile" in e for e in named), f"real: the step limiter spoke {len(named)} times")
    shown = checks(out.name)
    check("Pits in the ground: small and deep" in shown, f"real: the filled pit stays on the map {list(shown)}")
    check(next(shown["Pits in the ground: small and deep"].getFeatures())["filled"] == 1, "real: marked as filled")
    depth = next(n.layer() for n in group(out.name).findLayers() if n.layer().name() == "max_depth")
    peak = depth.dataProvider().bandStatistics(1).maximumValue
    check(0.0 < peak < 5.0, f"real: no water 12 m deep left in the run with the fill, {peak:.3f} m")
    dock.terrain.fill_pits.setChecked(False)
    dock.panel.limiter.setChecked(False)
    dock.terrain.dem.setLayer(plane)


def real_preview(dock) -> None:
    """Preview rain through the real engine: the 2D area's depth after the reduction, before any run (W65)."""
    storm = dock.storm

    def previewed() -> str:
        storm.preview_button.click()
        pump(lambda: storm.preview_button.isEnabled(), 120.0, "the rain preview")
        return storm.preview_label.text()

    said = previewed()
    rows = storm.preview_table.rows
    check(len(rows) == 1 and rows[0]["mode"] == "2d", f"real: the plane is all 2D area: {said}")
    check(abs(rows[0]["depth_mm"] - 20.0) < 1e-6, f"real: 100 mm/h for 0.2 h is 20 mm, {rows[0]['depth_mm']}")
    check(abs(rows[0]["peak_mm_h"] - 100.0) < 1e-3, "real: at 100 mm/h")
    check(abs(rows[0]["area_km2"] - 4.0) < 1e-6, "real: over the 4 km2 of the plane")
    check(not storm.preview_chart.isHidden() and storm.preview_chart.row is rows[0], "real: its hyetograph drawn")
    shown = storm_map(dock)
    check(list(shown) == ["Rain depth by area, before the run"], f"real: the storm map, no raster for even rain {shown}")
    area = shown["Rain depth by area, before the run"]
    check(area.featureCount() == 1 and abs(next(area.getFeatures())["depth_mm"] - 20.0) < 1e-6, "real: the 2D area, 20 mm")

    gauge_preview(dock)
    pick(storm.kind, "hypothetical")
    storm.design_depth.setValue(80.0)
    storm.design_hours.setValue(0.25)
    storm.pattern.set_rows([(0.0, 0.0), (100.0, 100.0)])
    pick(storm.arf_mode, "area")
    storm.storm_area.setValue(505.0)
    storm.arf.set_rows([(10.0, 1.0), (1000.0, 0.5)])
    said = previewed()
    depth = storm.preview_table.rows[0]["depth_mm"]
    check(abs(depth - 80.0 * 0.75) < 1e-4 and "0.7500 at 505" in said, f"real: the design storm reduced, {said} {depth}")
    pick(storm.arf_mode, "given")
    storm.arf_factor.setValue(0.7)
    said = previewed()
    depth = storm.preview_table.rows[0]["depth_mm"]
    check(abs(depth - 80.0 * 0.7) < 1e-4 and "0.7000 (given)" in said, f"real: a given factor, {said} {depth}")
    pick(storm.arf_mode, "area")
    storm.arf.set_rows([])
    previewed()
    check("reduction table" in storm.preview_label.text(), f"real: refused in words, {storm.preview_label.text()}")
    pick(storm.kind, "single")
    pick(storm.arf_mode, "none")


def smoke() -> None:
    engine = f'"{sys.argv[1]}" "{HERE / "fake_engine.py"}"'
    settings.set_engine_text(engine)
    iface = Iface()

    dem_path = WORK / "dem.tif"
    fake_engine.write_tiff(dem_path, 500.0)
    dem = QgsRasterLayer(str(dem_path), "dem")
    check(dem.isValid(), "temporary raster layer is valid")
    PROJECT.addMapLayer(dem)
    iface.canvas.setLayers([dem])
    iface.canvas.setExtent(dem.extent())

    plugin = wadi2d_qgis.classFactory(iface)
    plugin.initGui()
    check(iface.icons and len(iface.menu) == 2, "toolbar button and menu entries added")
    plugin.toggle_action.setChecked(True)
    dock = plugin.dock
    check(dock.isVisibleTo(iface.window), "dock opens from the toolbar button")
    pump(lambda: dock.schema is not None, what="the engine schema")
    check(dock.engine_label.text() == "Engine ready.", "schema read through the process wrapper")

    check(dock.terrain.dx.value() == 20.0, "cell size starts at 20")
    check(
        abs(dock.terrain.manning.value() - dock.schema.default("terrain.manning")) < 1e-9,
        "Manning from schema",
    )
    check(dock.panel.duration.value() == 1.0, "simulated time from schema")
    kinds = [dock.boundaries.kind.itemText(i) for i in range(dock.boundaries.kind.count())]
    check(kinds == ["stage", "normal", "free", "flow"], "boundary kinds from schema")
    check(dock.terrain.dem_layer().id() == dem.id(), "DEM combo lists the project raster")

    dialog = settings.EngineDialog(dock)
    dialog.check()
    pump(lambda: dialog.check_button.isEnabled(), what="the doctor")
    report = dialog.report.toPlainText()
    check(report.startswith("Engine found."), "doctor checks the engine")
    leaked = json.loads(report.split("\n", 1)[1])["qgis_env"]
    check(not any(leaked.values()), "the venv Python ran with QGIS's environment cleaned away")

    storm_sources(dock)
    dock.hydrology.rain.setValue(25.0)
    dock.hydrology.hours.setValue(0.5)
    dock.panel.say("")
    dock.panel.folder.setFilePath("")
    dock.panel.run_button.click()
    check("output folder" in dock.panel.message.text(), "a missing folder is said in plain words")

    out = WORK / "study" / "run"
    dock.panel.folder.setFilePath(str(out))

    dock.panel.estimate_button.click()
    pump(lambda: "cells" in dock.panel.estimate_label.text(), what="the estimate")
    check(
        dock.panel.estimate_label.text() == "48 cells, 1.25 GB, about 4 min",
        "estimate shows cells, memory, time",
    )
    check(dock._scratch is None, "estimate left no temporary folder")

    values = dock._collect()
    check(values["crs"] == "EPSG:32640" and problems(values) == [], "job values collected from the dock")
    check(values["extent"] == (400000.0, 2699880.0, 400160.0, 2700000.0), "map extent inside the DEM")

    start_line = to_wgs84(400020.0, 2699940.0)
    end_line = to_wgs84(400140.0, 2699940.0)
    crest = line_layer("crest", "&field=crest:double", [start_line, end_line], "EPSG:4326", [512.5])
    z_wall = QgsGeometry.fromWkt("LineStringZ(400020 2699900 700, 400140 2699900 701)")
    spill = line_layer(
        "spill",
        "&field=crest:double&field=c:double&field=l:double",
        [QgsPointXY(400040, 2699960), QgsPointXY(400080, 2699960)],
        attributes=[510.0, 2.1, 40.0],
    )
    wall = line_layer("wall", "", z_wall, kind="LineStringZ")
    limit = line_layer(
        "limit",
        "&field=kind:string&field=value:double",
        [QgsPointXY(400000, 2699880), QgsPointXY(400160, 2699880)],
        attributes=["stage", 1.5],
    )
    ring = QgsGeometry.fromPolygonXY(
        [
            [
                QgsPointXY(400000, 2699880),
                QgsPointXY(400160, 2699880),
                QgsPointXY(400160, 2700000),
                QgsPointXY(400000, 2700000),
            ]
        ]
    )
    domain = line_layer("domain", "", ring, kind="Polygon")
    point = line_layer(
        "dam",
        "&field=name:string",
        QgsGeometry.fromPointXY(QgsPointXY(400080, 2699940)),
        attributes=["Dam 1"],
        kind="Point",
    )
    for layer in (crest, spill, wall, limit, domain, point):
        PROJECT.addMapLayer(layer)

    structures = dock.structures
    structures.layers["crest_line"].setLayer(crest)
    structures.fields["crest_line"]["crest_z"].setField("crest")
    structures.layers["spillway"].setLayer(spill)
    structures.fields["spillway"]["crest_z"].setField("crest")
    structures.fields["spillway"]["coefficient"].setField("c")
    structures.fields["spillway"]["length"].setField("l")
    structures.layers["wall"].setLayer(wall)
    dock.boundaries.layer.setLayer(limit)
    dock.terrain.domain.setLayer(domain)
    dock.points.layer.setLayer(point)
    dock.points.name.setField("name")
    dock.structures.setCollapsed(False)

    added: list[str] = []
    PROJECT.layersAdded.connect(lambda layers: added.extend(layer.name() for layer in layers))
    live_values: set[float] = set()
    probe = QgsPointXY(400030, 2699970)

    def watch_live() -> bool:
        layer = dock.live.layer()
        if layer is not None:
            value, good = layer.dataProvider().sample(probe, 1)
            if good:
                live_values.add(value)
        return dock.run is None and dock.panel.run_button.isEnabled()

    mode("ok")
    os.environ["WADI2D_FAKE_STEPS"] = "16"
    os.environ["WADI2D_FAKE_STEP_S"] = "0.2"
    start(dock)
    check(
        not dock.panel.run_button.isEnabled() and dock.panel.stop_button.isEnabled(), "buttons follow the run"
    )
    pump(watch_live, what="the good run")
    check(dock.panel.bar.value() == 100, "progress bar reaches 100")
    said = dock.panel.message.text()
    check(said == "Finished. point P1 is outside the domain.", "the warning stays on screen")
    status = dock.panel.status.text()
    check(
        all(word in status for word in ("of 1 h 00 min", "step 1.5 s", "wet cells", "mass error")),
        "status line",
    )

    job = json.loads((out / "job.json").read_text(encoding="utf-8"))
    check(
        Path(job["terrain"]["dem"]).is_absolute() and Path(job["grid"]["domain"]).is_absolute(),
        "paths absolute",
    )
    check(
        sorted(p.name for p in (out / "inputs").glob("*.geojson"))
        == [
            "boundaries.geojson",
            "crest_line.geojson",
            "design_points.geojson",
            "domain.geojson",
            "spillway.geojson",
            "wall.geojson",
        ],
        "every vector layer landed in inputs/ as GeoJSON",
    )
    crest_saved = json.loads((out / "inputs" / "crest_line.geojson").read_text(encoding="utf-8"))
    check(crest_saved["crs"]["properties"]["name"] == "EPSG:32640", "GeoJSON names the DEM CRS")
    x, y = crest_saved["features"][0]["geometry"]["coordinates"][0]
    check(
        abs(x - 400020.0) < 0.01 and abs(y - 2699940.0) < 0.01, "a WGS84 layer was reprojected to the DEM CRS"
    )
    objects = {entry["kind"]: entry for entry in job["terrain"]["objects"]}
    check(objects["crest_line"]["z_constant"] == 512.5, "crest elevation read from its field")
    check(
        objects["spillway"]["coefficient"] == 2.1 and objects["spillway"]["length"] == 40.0, "spillway fields"
    )
    check(objects["wall"]["z"] == [700.0, 701.0], "vertex Z of a 3D line kept")
    check(
        job["boundaries"][0]["kind"] == "stage" and job["boundaries"][0]["stage"] == 1.5,
        "per-line boundary fields",
    )
    check(
        job["outputs"]["points"] == [{"name": "Dam 1", "x": 400080.0, "y": 2699940.0}], "design point named"
    )
    check(job["storm"]["depth_mm"] == 12.5, "rain written as a depth")
    engines = [dock.panel.backend.itemData(i) for i in range(dock.panel.backend.count())]
    check(engines == dock.schema.enum("run.backend"), "the engine choices are the schema's")
    check("backend" not in job["run"], "the automatic engine leaves the job as it was")
    check(
        "fill_pits" not in job["terrain"] and "step_limiter" not in job["outputs"],
        "Fill pits and the step limiter left unticked leave the job as it was",
    )
    check(
        not dock.terrain.fill_pits.isChecked() and dock.terrain.fill_pits.isEnabled(),
        "Fill pits starts unticked, as the schema has it",
    )
    check("spill level" in dock.terrain.fill_pits.toolTip(), "Fill pits carries the schema's words")
    check("time step" in dock.panel.limiter.toolTip(), "the step limiter tick carries the schema's words")

    check(added.count("Wadi2D live depth") == 1, "live layer added exactly once")
    check(len(live_values) >= 3, f"live layer showed the rewrites in place: {sorted(live_values)}")
    os.environ["WADI2D_FAKE_STEP_S"] = "0.08"
    check(dock.live.layer() is None, "live layer leaves when the maps arrive")
    node = group("run")
    check(node is not None, "maps in the results group named after the run")
    names = [child.name() for child in node.children()]
    check(names[:2] == ["max_depth", "hazard"] and len(names) == 6, "maps ordered, depth first")
    layers = {child.name(): child.layer() for child in node.children()}
    depth_renderer = layers["max_depth"].renderer()
    check(depth_renderer.type() == "singlebandpseudocolor", "depth styled")
    shader = depth_renderer.shader().rasterShaderFunction()
    items = shader.colorRampItemList()
    check(  # W88: under the display cutoff nothing is drawn; with none the ramp fades from transparent
        ((shader.clip() and items[0].value > 0.0) or items[0].color.alpha() == 0)
        and items[-1].color.blue() > items[-1].color.red(),
        "ramp is transparent blue",
    )
    ramp = layers["hazard"].renderer().shader().rasterShaderFunction()
    check(len(ramp.colorRampItemList()) == 5, "hazard has its five classes")
    check(ramp.colorRampType() == QgsColorRampShader.Discrete, "hazard styled in classes")
    check(
        node.children()[0].isVisible() and not node.children()[1].itemVisibilityChecked(),
        "only depth switched on",
    )
    check(dock.panel.open_button.isVisibleTo(dock.panel), "Open results folder offered")

    dock.panel.backend.setCurrentIndex(dock.panel.backend.findData("cpu"))
    dock.terrain.fill_pits.setChecked(True)
    dock.panel.limiter.setChecked(True)
    start(dock)
    check(not dock.panel.backend.isEnabled(), "the engine choice is held while it runs")
    check(not dock.panel.limiter.isEnabled(), "the step limiter tick is held while it runs")
    finished_run(dock)
    check(
        (WORK / "study" / "run_2" / PROGRESS_FILE).is_file() and group("run_2"),
        "a second run never overwrites",
    )
    second_job = json.loads((WORK / "study" / "run_2" / "job.json").read_text(encoding="utf-8"))
    check(second_job["run"].get("backend") == "cpu", "a CPU choice reaches the job")
    check(second_job["terrain"].get("fill_pits") is True, "Fill pits ticked reaches the job")
    check(second_job["outputs"].get("step_limiter") == "layer", "the step limiter ticked reaches the job")
    dock.terrain.fill_pits.setChecked(False)
    dock.panel.limiter.setChecked(False)
    dock.panel.backend.setCurrentIndex(dock.panel.backend.findData("auto"))

    mode("error")
    os.environ["WADI2D_FAKE_STEPS"] = "6"
    start(dock)
    finished_run(dock)
    said = dock.panel.message.text()
    check("numerically unstable" in said and "time step below the floor" in said, f"plain failure: {said}")
    check(dock.marker is not None, "failed cell marked on the map")
    centre = iface.canvas.center()
    check(abs(centre.x() - 400070.0) < 1.0 and abs(centre.y() - 2699950.0) < 1.0, "map centred on the cell")
    start(dock)
    check(dock.marker is None, "the marker goes with the next run")
    finished_run(dock)

    mode("refuse")
    start(dock)
    finished_run(dock)
    said = dock.panel.message.text()
    check(
        "refused" in said and "multiple of the DEM pixel" in said, f"exit 2 with the engine's reason: {said}"
    )

    mode("crash")
    start(dock)
    finished_run(dock)
    said = dock.panel.message.text()
    check("failed unexpectedly" in said and "before the first event" in said, f"exit 1 with stderr: {said}")

    mode("slow")
    os.environ["WADI2D_FAKE_STEPS"] = "400"
    start(dock)
    run_dir = dock.run.out_dir
    pump(lambda: dock.run.state.t > 0.0, what="the first step")
    dock.panel.stop_button.click()
    finished_run(dock)
    check(
        dock.panel.message.text() == "Stopped on request.",
        "Stop creates the file and exit 6 reads as stopped",
    )
    check(not (run_dir / STOP_FILE).exists(), "the engine took the stop file away")
    check(group(run_dir.name) is not None, "maps of a stopped run are loaded")

    mode("deaf")
    os.environ["WADI2D_FAKE_STEPS"] = "3"
    start(dock)
    deaf = dock.run
    deaf.stop_grace_ms = 800
    pump(lambda: deaf.pid is not None and deaf.state.t > 0.0, what="the deaf run")
    pid = deaf.pid
    dock.panel.stop_button.click()
    finished_run(dock)
    check("killed" in dock.panel.message.text(), "killed after the grace time, and it says so")
    pump(lambda: not pid_alive(pid), 10.0, "the process to die")
    say("the killed process is really gone")

    mode("slow")
    os.environ["WADI2D_FAKE_STEPS"] = "60"
    start(dock)
    run_dir = dock.run.out_dir
    pump(lambda: dock.run.state.t > 0.0 and dock.run.pid is not None, what="a run to outlive the plugin")
    pid = read_run_info(run_dir)["pid"]
    plugin.unload()
    pump(lambda: plugin.dock is None, what="the unload")
    for _ in range(20):
        QCoreApplication.processEvents()
        time.sleep(0.01)
    check(pid_alive(pid), "the engine survives the plugin being unloaded")
    check(not iface.icons and not iface.menu, "unload removes the button and the menu")

    second = wadi2d_qgis.classFactory(iface)
    second.initGui()
    check(second.dock is not None and second.dock.run is not None, "the next session re-attaches by itself")
    finished_run(second.dock)
    check(second.dock.panel.message.text().startswith("Finished."), "the attached run ends normally")
    check(group(run_dir.name) is not None, "the attached run's maps are loaded")
    check(not pid_alive(pid), "and its process is gone")

    dock = second.dock
    mode("ok")
    os.environ["WADI2D_FAKE_STEPS"] = "4"
    hms = WORK / "hms"
    hms.mkdir()
    (hms / "B.basin").write_text("Basin: B\n\nSubbasin: S1\nEnd:\n\nSubbasin: S2\nEnd:\n", "utf-8")
    (hms / "Storm.met").write_text("x", "utf-8")
    (hms / "C.control").write_text("x", "utf-8")
    dock.hydrology.folder.setFilePath(str(hms))
    check(dock.hydrology.table.rowCount() == 2, "subbasin table read from the basin file")
    check(dock.storm.kind.currentData() == "hms", "an HMS project brings its storm")
    dock.hydrology.table.cellWidget(1, 1).setCurrentText("2d")
    routing = dock.hydrology.routing
    schemes = [routing.itemData(i) for i in range(routing.count())]
    check(schemes == dock.schema.enum("hydrology.reach_routing"), "the reach routing choices are the engine's")
    check(routing.currentData() == dock.schema.default("hydrology.reach_routing"), "HMS-faithful routing by default")
    routing.setCurrentIndex(routing.findData("conserving"))
    dock.hydrology.setCollapsed(True)
    values = dock._collect()
    check("hms" in values, "a collapsed section still gives its HMS project")
    dock.hydrology.setCollapsed(False)
    start(dock)
    run_dir = dock.run.out_dir
    finished_run(dock)
    job = json.loads((run_dir / "job.json").read_text(encoding="utf-8"))
    check(job["storm"]["kind"] == "hypothetical", "the HMS storm comes through hms-import")
    modes = {entry["name"]: entry["mode"] for entry in job["hydrology"]["subbasins"]}
    check(modes == {"S1": "lumped", "S2": "2d"}, "lumped or 2D per subbasin")
    check(job["hydrology"]["reach_routing"] == "conserving", "the conserving reach routing survives the HMS merge")
    routing.setCurrentIndex(routing.findData("hms"))
    check(job["run"]["duration_s"] == 7200.0, "the HMS control file sets the simulated time")
    muskingum_smoke(dock, hms)

    study_smoke(dock)

    settings.set_engine_text(r"C:\no\such\python.exe -m wadi2d.engine.cli")
    dock.schema = None
    dock.load_engine()
    pump(lambda: "not found" in dock.engine_label.text(), what="the missing engine message")
    check(not dock.panel.run_button.isEnabled(), "no engine, no Run")

    second.unload()


def muskingum_smoke(dock, hms: Path) -> None:
    """W89: the reach table under the Muskingum choice, the proposal button through the process wrapper, the job."""
    section, routing = dock.hydrology, dock.hydrology.routing
    box = section.muskingum
    check(box.isHidden(), "no reach table under another reach routing")
    basin = "Basin: B\n\nSubbasin: S1\nEnd:\n\nSubbasin: S2\nEnd:\n\nReach: R1\nEnd:\n\nReach: R_none\nEnd:\n"
    (hms / "B2.basin").write_text(basin, "utf-8")
    section.folder.setFilePath("")
    section.folder.setFilePath(str(hms))
    section.files["basin"].setCurrentText("B2.basin")
    routing.setCurrentIndex(routing.findData("muskingum"))
    check(not box.isHidden(), "the reach table shows under Muskingum")
    check([row.name for row in box.rows] == ["R1", "R_none"], "with the reaches of the HMS basin file")
    check(dock._collect()["muskingum"] == [], "no K and X in the job until one is typed or proposed")
    check("0 of 2 reaches have K and X" in box.note.text() and "A run stops" in box.note.text(), "and the note says so")
    box.table.item(0, 1).setText("800")
    check(box.rows[0].flow == 800.0, "a reference flow typed into the table")
    box.velocity.setValue(2.0)
    box.button.click()
    pump(lambda: box.button.isEnabled() and box.rows[0].proposed, what="the proposal")
    first, second = box.rows
    check((first.k_hours, first.x, first.subreaches) == (1.5, 0.25, 18), "the proposal fills K, X and subreaches")
    check("at 800.0 m3/s" in first.words and "--velocity 2.0" in first.words, "asked at the user's flow and velocity")
    check(f"--control {hms / 'C.control'}" in first.words, "and at the step of the HMS control file")
    check(box.table.item(0, 2).font().italic() and box.table.item(0, 5).text() == first.words, "shown as a proposal, with its derivation")
    check(second.empty() and second.words.startswith("No proposal"), "a reach with nothing to propose from stays empty")
    check("1 proposed" in box.note.text() and "A proposal is a start" in box.note.text(), "the note says what was done")
    box.table.item(1, 2).setText("0.4")
    box.table.item(1, 3).setText("0.6")
    check("X: between 0 and 0.5" in box.table.item(1, 5).text(), "a number HMS does not take is named in the row")
    box.table.item(1, 3).setText("0.1")
    box.table.item(0, 3).setText("0.3")
    check(not box.table.item(0, 2).font().italic() and first.words == "Typed here.", "an edit makes a proposal the user's")
    box.button.click()
    pump(lambda: box.button.isEnabled() and "kept as typed" in box.note.text(), what="the second proposal")
    check(first.x == 0.3 and second.k_hours == 0.4, "a second proposal overwrites nothing typed")
    start(dock)
    run_dir = dock.run.out_dir
    finished_run(dock)
    hydrology = json.loads((run_dir / "job.json").read_text(encoding="utf-8"))["hydrology"]
    wanted = [
        {"reach": "R1", "k_hours": 1.5, "x": 0.3, "subreaches": 18},
        {"reach": "R_none", "k_hours": 0.4, "x": 0.1, "subreaches": 1},
    ]
    check(hydrology["reach_routing"] == "muskingum" and hydrology["muskingum"] == wanted, "the table's rows are the job's")
    routing.setCurrentIndex(routing.findData("hms"))
    check(box.isHidden() and "muskingum" not in dock._collect(), "another choice hides the table and leaves the rows out")
    section.files["basin"].setCurrentText("B.basin")


def study_smoke(dock) -> None:
    """The depth-area study through the dock and the process wrapper: progress, its table, a stop."""
    mode("ok")
    os.environ["WADI2D_FAKE_STEPS"] = "6"
    os.environ["WADI2D_FAKE_STEP_S"] = "0.2"
    across = line_layer(
        "across", "&field=name:string&field=area:double",
        [QgsPointXY(400020, 2699940), QgsPointXY(400140, 2699940)], attributes=["Outlet", 20.0],
    )  # fmt: skip
    PROJECT.addMapLayer(across)
    dock.points.layer.setLayer(across)
    dock.points.name.setField("name")
    dock.points.area.setField("area")
    box = dock.study
    check(box.spacing.currentData() == "bracket", "a study's storm areas bracket the drainage areas by default")
    check(not box.composite.isChecked(), "the composite map is off by default")
    box.start_button.click()
    pump(lambda: dock.study_run is not None, what="the study to start")
    check(not dock.panel.run_button.isEnabled() and not box.start_button.isEnabled(), "no run while a study runs")
    pump(lambda: "Run 1 of 2" in box.status.text(), what="the first run of the study")
    check("1 run left after it" in box.status.text(), f"the study says how many runs are left: {box.status.text()}")
    pump(lambda: dock.study_run is None, 60.0, "the study to end")
    check(box.table.rowCount() == 2 and box.table.item(0, 0).text() == "Outlet", "a table of design flows")
    check(box.message.text().startswith("Finished: 2 runs, 2 design flows"), f"the study ends: {box.message.text()}")
    label = box.file_label.text()
    check("design_points.csv" in label and "J1" in label, "where it is written, and the elements on the grid")
    job = json.loads((dock._study_dir / "job.json").read_text(encoding="utf-8"))
    check(job["arf"] == {"bracket": True}, "the study's job asks for bracketing storm areas")
    check(job["outputs"]["lines"][0]["drainage_area_km2"] == 20.0, "a line's drainage area from its field")
    check(dock.panel.run_button.isEnabled() and box.start_button.isEnabled(), "Run and Start study are back")

    mode("slow")
    os.environ["WADI2D_FAKE_STEPS"] = "400"
    box.start_button.click()
    pump(lambda: dock.study_run is not None, what="a slow study to start")
    follow = dock.study_run
    pump(lambda: follow.state.run is not None and follow.state.run.t > 0.0, what="the first run of a slow study")
    box.stop_button.click()
    pump(lambda: dock.study_run is None, 60.0, "the stopped study")
    said = box.message.text()
    check(said.startswith("Stopped after 0 of 2 runs") and "no design table" in said, f"a stopped study: {said}")
    check(box.table.rowCount() == 0 and box.start_button.isEnabled(), "no table, and a study can start again")
    os.environ["WADI2D_FAKE_STEP_S"] = "0.08"
    mode("ok")
    dock.points.layer.setLayer(None)


def real_engine() -> None:
    """The same dock against the real CLI: a job it accepts, an estimate, a run, a stop."""
    import numpy as np
    from osgeo import gdal, osr

    os.chdir(WORK)  # QGIS's working folder is not the repo: the engine must resolve from anywhere
    launcher = WORK / "engine.py"  # this checkout's engine, not the one the venv installed (a worktree's own, W65)
    launcher.write_text(
        f"import sys\nsys.path.insert(0, r'{HERE.parents[1]}')\nfrom wadi2d.engine.cli import main\nraise SystemExit(main())\n",
        encoding="utf-8",
    )
    settings.set_engine_text(f'"{sys.argv[1]}" "{launcher}"')
    iface = Iface()
    size, pixel, west, north = 400, 5.0, 400000.0, 2702000.0
    east, south = west + size * pixel, north - size * pixel
    dem_path = WORK / "plane.tif"
    raster = gdal.GetDriverByName("GTiff").Create(str(dem_path), size, size, 1, gdal.GDT_Float32)
    raster.SetGeoTransform((west, pixel, 0.0, north, 0.0, -pixel))
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(32640)
    raster.SetProjection(srs.ExportToWkt())
    raster.GetRasterBand(1).WriteArray(120.0 - 0.01 * pixel * np.tile(np.arange(size), (size, 1)))
    raster = None
    dem = QgsRasterLayer(str(dem_path), "plane")
    check(dem.isValid(), "real: synthetic plane loaded")
    PROJECT.addMapLayer(dem)
    iface.canvas.setLayers([dem])
    iface.canvas.setExtent(dem.extent())
    outfall = line_layer("outfall", "", [QgsPointXY(east - 10, north), QgsPointXY(east - 10, south)])
    PROJECT.addMapLayer(outfall)

    plugin = wadi2d_qgis.classFactory(iface)
    plugin.initGui()
    plugin.toggle_action.setChecked(True)
    dock = plugin.dock
    pump(lambda: dock.schema is not None, 60.0, "the real schema")
    check(dock.terrain.dx.value() == 20.0, "real: the dock takes its defaults from wadi2d schema")
    dock.hydrology.rain.setValue(100.0)
    dock.hydrology.hours.setValue(0.2)
    dock.panel.duration.setValue(0.25)
    dock.boundaries.layer.setLayer(outfall)
    dock.boundaries.kind.setCurrentText("free")
    dock.panel.folder.setFilePath(str(WORK / "real" / "first"))

    dock.panel.estimate_button.click()
    pump(lambda: dock.panel.estimate_label.text() not in ("", "Estimating..."), 120.0, "the real estimate")
    said = dock.panel.estimate_label.text()
    check(said.startswith("10,000 cells") and "GB" in said, f"real: dry run reads {said}")

    start(dock)
    run_dir = dock.run.out_dir
    pump(lambda: dock.run is None and dock.panel.run_button.isEnabled(), 180.0, "the real run")
    said = dock.panel.message.text()
    check(said == "Finished.", f"real: {said} {dock.panel.status.text()}")
    check(dock.panel.bar.value() == 100, "real: progress bar reaches 100")
    status = dock.panel.status.text()
    check("0 h 15 min of 0 h 15 min" in status and "wet area" in status, f"real: {status}")
    check("mass error" in status, "real: mass error reported")
    node = group(run_dir.name)
    names = [found.layer().name() for found in node.findLayers()]  # W100: the pixel rasters now come too, so the maps sit in subgroups
    check({"max_depth", "hazard", "max_speed", "arrival"} <= set(names), f"real: maps loaded {names}")
    depth = next(n.layer() for n in node.findLayers() if n.layer().name() == "max_depth")
    check(depth.name() == "max_depth", "real: depth on top")
    check(depth.renderer().type() == "singlebandpseudocolor", "real: depth styled")
    peak = depth.dataProvider().bandStatistics(1).maximumValue
    check(0.0 < peak < 5.0, f"real: a believable peak depth, {peak:.3f} m")
    real_preview(dock)
    real_pits(dock, dem, raster_of=(size, pixel, west, north, srs))

    dock.panel.folder.setFilePath(str(WORK / "real" / "stopped"))
    dock.panel.duration.setValue(dock.panel.duration.maximum())
    start(dock)
    run_dir = dock.run.out_dir
    live_seen: list[bool] = []

    def stepping() -> bool:
        live_seen.append(dock.live.layer() is not None)
        return dock.run.state.t > 0.0 and any(live_seen)

    pump(stepping, 120.0, "the real run to step and show its live layer")
    check(True, "real: live/depth.tif on the map while it runs")
    dock.panel.stop_button.click()
    pump(lambda: dock.run is None and dock.panel.run_button.isEnabled(), 120.0, "the real stop")
    check(dock.panel.message.text() == "Stopped on request.", f"real: {dock.panel.message.text()}")
    check(group(run_dir.name) is not None, "real: a stopped run still gives its maps")
    plugin.unload()


if __name__ == "__main__":
    try:
        if sys.argv[2:] == ["real"]:
            real_engine()
        else:
            qgis_loader()
            wadi2d_qgis = importlib.import_module("wadi2d_qgis")
            settings = importlib.import_module("wadi2d_qgis.settings")
            smoke()
        print("SMOKE PASSED", flush=True)
    finally:
        shutil.rmtree(WORK, ignore_errors=True)
    sys.stdout.flush()
    os._exit(0)  # QGIS's own teardown is not what this test is about
