"""What the W101 dock scenarios share. Not a scenario: each loads it by path (``helper(h)``)."""

import json
import shutil
from pathlib import Path


def helper(h, name="w101_help"):
    import importlib.util

    spec = importlib.util.spec_from_file_location(name, Path(h.SCENARIO).parent / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def big_shot(h, dock, name, size=(460, 1000), top=None, open_only=None):
    """The dock's frame at the width of a real dock, the card ``top`` brought to the top of the sections; with
    ``open_only`` every other section is folded first, so the picture shows that one."""
    from qgis.PyQt.QtWidgets import QApplication

    if open_only is not None:
        for section in dock.sections:
            section.setCollapsed(section.key != open_only)
        top = top or open_only
    dock.status_links.refresh()  # the cards' words as they stand now, not at the last tick
    if open_only is not None:  # the card itself, whole, at the dock's width: a docked frame keeps its own size
        QApplication.processEvents()
        dock.cards[open_only].grab().save(str(h.P / f"widget_{name}_card.png"))
    frame = dock.widget()
    held = frame.size()
    frame.resize(*size)
    QApplication.processEvents()
    if top is not None:
        dock.scroll.verticalScrollBar().setValue(max(dock.cards[top].y() - 8, 0))
    frame.grab().save(str(h.P / f"widget_{name}.png"))
    frame.resize(held)
    QApplication.processEvents()


def built(dock, out: Path, **more) -> dict:
    """The job the dock builds now, into ``out`` (emptied first), as plain JSON."""
    from wadi2d_qgis.job_builder import build_job

    shutil.rmtree(out, ignore_errors=True)
    return json.loads(json.dumps(build_job({**dock._collect(), "output": str(out), **more}, out)))


def problems_of(dock, out: Path, **more) -> list:
    from wadi2d_qgis.job_builder import problems

    return problems({**dock._collect(), "output": str(out), **more})


def validated(job: dict):
    """The engine's own schema on the job: the run would read it."""
    from wadi2d.config.schema import RunConfig

    return RunConfig.model_validate(job)


def constant_raster(path: Path, like, value: float):
    """A GeoTIFF of one value over the extent and pixel of ``like`` (a raster layer), for a depth grid."""
    from osgeo import gdal

    source = gdal.Open(like.source())
    driver = gdal.GetDriverByName("GTiff")
    step = 10
    cols, rows = max(source.RasterXSize // step, 1), max(source.RasterYSize // step, 1)
    out = driver.Create(str(path), cols, rows, 1, gdal.GDT_Float32)
    x0, dx, _a, y0, _b, dy = source.GetGeoTransform()
    out.SetGeoTransform((x0, dx * step, 0.0, y0, 0.0, dy * step))
    out.SetProjection(source.GetProjection())
    band = out.GetRasterBand(1)
    band.Fill(value)
    band.SetNoDataValue(-9999.0)
    out.FlushCache()
    out = None
    return path


def pick(combo, key) -> bool:
    index = combo.findData(key)
    combo.setCurrentIndex(index)
    return index >= 0


def words_of(widget, text):
    """The labels of ``widget`` a user would see that hold ``text``."""
    from qgis.PyQt.QtWidgets import QLabel

    return [label for label in widget.findChildren(QLabel) if text in label.text() and label.isVisibleTo(widget)]
