"""W101, his two faults of 2026-11-16, through the real dock.

1. A project of results opened with no saved model: Terrain's DEM picker took the first raster, a depth map. It now
   starts on the DEM a run in the project was made on, never on a run's own raster, and on nothing when there is none.
2. Storm's short pages left a gap the height of the tallest page: each page now takes its own height.
"""

import json
import shutil
from pathlib import Path


def scenario(h):
    import importlib.util

    spec = importlib.util.spec_from_file_location("w101_help", Path(h.SCENARIO).parent / "w101_help.py")
    w = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(w)
    from qgis.core import QgsProject, QgsRasterLayer
    from qgis.PyQt.QtWidgets import QApplication

    project = QgsProject.instance()

    def on_root(layer):
        """A layer at the top of the tree: QGIS puts a new layer into the group selected in the panel."""
        project.addMapLayer(layer, False)
        project.layerTreeRoot().insertLayer(0, layer)
        return layer
    dem_path = h.BLOCK / "Terrain" / "GGC_2_MERGE_HDSM_5.tif"
    run = h.DATA / "a_run"
    (run / "pixels").mkdir(parents=True, exist_ok=True)
    (run / "job.json").write_text(json.dumps({"terrain": {"dem": str(dem_path)}, "run": {}}), encoding="utf-8")
    dem_first = QgsRasterLayer(str(dem_path), "terrain")
    w.constant_raster(run / "pixels" / "pixel_depth.tif", dem_first, 0.3)
    root = project.layerTreeRoot()
    group = root.addGroup("Results \N{EN DASH} a_run")
    depth = QgsRasterLayer(str(run / "pixels" / "pixel_depth.tif"), "Depth, m (from 0.05 m)")
    project.addMapLayer(depth, False)
    group.addLayer(depth)  # the first raster of the project, as in his W100 project
    on_root(dem_first)
    project.setCrs(dem_first.crs())
    dock = yield from h.open_dock()
    from wadi2d_qgis.dem_choice import default_dem, is_product
    from wadi2d_qgis.section_status import MISSING

    t, storm = dock.terrain, dock.storm
    h.log("=== 1 the DEM picker in a project of results")
    h.check("the run's own raster is a product, by its file and by its group", is_product(depth) and is_product(depth, root))
    h.check("the DEM is not one", not is_product(dem_first, root))
    h.check("the dock starts on the DEM the run was made on, not the depth map", t.dem_layer() is not None and t.dem_layer().id() == dem_first.id(), t.dem_layer().name() if t.dem_layer() else None)
    project.removeMapLayer(dem_first.id())
    h.check("with the DEM gone, nothing is chosen for the user", default_dem(project) is None)
    t.choose_default_dem()
    h.check("and Terrain says the DEM is missing", t.dem_layer() is None and dock.status_links.refresh()["terrain"].state == MISSING, dock.status_links.refresh()["terrain"])
    plain = QgsRasterLayer(str(run / "pixels" / "pixel_depth.tif"), "loose copy")
    loose = h.DATA / "elsewhere.tif"
    shutil.copy(run / "pixels" / "pixel_depth.tif", loose)
    other = on_root(QgsRasterLayer(str(loose), "some raster"))
    found = default_dem(project)
    h.check("a raster no run names is not taken either", found is None and not is_product(other, root), (found.name() if found else None, is_product(other, root), other.source(), [(l.name(), l.source()) for l in project.mapLayers().values()]))
    del plain
    in_results = QgsRasterLayer(str(dem_path), "terrain under results")
    project.addMapLayer(in_results, False)
    group.addLayer(in_results)
    project.removeEntry("Wadi2D", "model")
    dock.model._project_read()
    h.check("the run's DEM is taken even under a results group, for want of another", t.dem_layer() is not None and t.dem_layer().id() == in_results.id(), t.dem_layer().name() if t.dem_layer() else None)
    dem = on_root(QgsRasterLayer(str(dem_path), "terrain again"))
    project.removeEntry("Wadi2D", "model")  # the dock keeps its model in the project: a project with none
    dock.model._project_read()  # read with no saved model: the store chooses the default again
    h.check("on a project read with no model, the run's DEM is found again", t.dem_layer() is not None and t.dem_layer().id() == dem.id(), t.dem_layer().name() if t.dem_layer() else None)

    h.log("=== 2 each Storm page takes its own height")
    storm.setCollapsed(False)
    pages = storm.pages
    heights = {}
    for kind in ("fixed", "gauges", "hyetograph", "fixed"):
        w.pick(storm.kind, kind)
        QApplication.processEvents()
        heights[kind] = (pages.sizeHint().height(), pages.currentWidget().sizeHint().height())
    fixed, gauges = heights["fixed"], heights["gauges"]
    h.check("the stack is as tall as the page shown, a fixed depth", abs(fixed[0] - fixed[1]) <= 2, heights)
    h.check("on the screen too", pages.height() <= fixed[1] + 2, (pages.height(), fixed))
    h.check("and a tall page makes it tall", gauges[0] >= gauges[1] - 2 and gauges[0] > fixed[0] + 100, heights)
    h.check("no gap of the tallest page under a short one", fixed[0] < gauges[1] - 100, heights)
    w.big_shot(h, dock, "storm_fixed_no_gap", open_only="storm")
