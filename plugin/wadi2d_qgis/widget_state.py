# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""What an input widget holds, as plain values, and back again: the part of a saved model that needs Qt.

A section's inputs are found by walking its attributes in the order ``build`` made them, so a widget added to a
section is saved without anyone listing it. :func:`inputs` yields ``(path, widget)``; :func:`read` and :func:`write`
turn one widget into a JSON value and back. A layer is saved by its id, with its source and name to find it again in
another project (W99).

Tables whose rows are dataclasses are not walked here: a section names them in ``state_rows`` and
:func:`read_rows` / :func:`write_rows` carry them.
"""

from __future__ import annotations

import dataclasses
import os
from pathlib import Path

from qgis.core import QgsCoordinateReferenceSystem, QgsProject, QgsRasterLayer, QgsVectorLayer
from qgis.gui import QgsFieldComboBox, QgsFileWidget, QgsMapLayerComboBox
from qgis.PyQt.QtWidgets import (
    QAbstractButton,
    QAbstractSpinBox,
    QCheckBox,
    QComboBox,
    QGroupBox,
    QLineEdit,
    QRadioButton,
)

from .model_doc import RASTER_PROVIDER

PACKAGE = __name__.split(".")[0]
CHECKED = "#checked"
"""The path suffix of a checkable box that also holds inputs of its own."""
MAX_DEPTH = 5
PLAIN = (str, int, float, bool)
NOTE = "note: "
"""How :func:`write` begins a text that is news, not a failure: a layer it added to the project."""


def _own(value) -> bool:
    """An object of this plugin, whose attributes may hold inputs."""
    return type(value).__module__.startswith(PACKAGE) and not dataclasses.is_dataclass(value)


def _pair_table(value) -> bool:
    """The Storm section's two-column table, by what it can do: this module imports no section."""
    return callable(getattr(value, "set_rows", None)) and callable(getattr(value, "rows", None))


def is_input(value) -> bool:
    if isinstance(value, (QgsMapLayerComboBox, QgsFieldComboBox, QgsFileWidget, QComboBox, QLineEdit)):
        return True
    if isinstance(value, QAbstractSpinBox) and hasattr(value, "value"):
        return True
    if isinstance(value, (QCheckBox, QRadioButton)):
        return True
    return _pair_table(value)


def inputs(owner, skip: tuple[str, ...] = (), prefix: str = "", seen: set | None = None, depth: int = 0):
    """Every input of ``owner`` as ``(path, widget)``, in the order its attributes were made; a widget reached twice
    is given once, by its first path."""
    seen = set() if seen is None else seen
    for name, value in list(vars(owner).items()):
        path = f"{prefix}{name}"
        if name.startswith("_") or path in skip:
            continue
        yield from _visit(path, value, skip, seen, depth)


def _visit(path: str, value, skip, seen: set, depth: int):
    if id(value) in seen or path in skip:
        return
    if is_input(value):
        seen.add(id(value))
        yield path, value
    elif isinstance(value, dict):
        for key, item in list(value.items()):
            if isinstance(key, str):
                yield from _visit(f"{path}.{key}", item, skip, seen, depth)
    elif _own(value) and depth < MAX_DEPTH:
        seen.add(id(value))
        if isinstance(value, QGroupBox) and value.isCheckable():
            yield f"{path}{CHECKED}", value
        yield from inputs(value, skip, f"{path}.", seen, depth + 1)


# One widget


def layer_state(layer) -> dict | None:
    if layer is None:
        return None
    return {
        "id": layer.id(),
        "source": layer.source(),
        "name": layer.name(),
        "provider": layer.providerType(),
        "crs": layer.crs().authid(),
    }


def _file_of(source: str) -> str:
    return os.path.normcase(os.path.normpath(source.split("|")[0])) if source else ""


def find_layer(saved: dict):
    """The layer a saved choice names: by id, else by its source, the same name first."""
    project = QgsProject.instance()
    layer = project.mapLayer(saved.get("id") or "")
    if layer is not None:
        return layer
    source = saved.get("source") or ""
    same = [candidate for candidate in project.mapLayers().values() if candidate.source() == source]
    if not same and _file_of(source):
        same = [c for c in project.mapLayers().values() if _file_of(c.source()) == _file_of(source)]
    named = [candidate for candidate in same if candidate.name() == saved.get("name")]
    return (named or same or [None])[0]


def add_layer(saved: dict):
    """The saved layer added to the project from its file, or None when there is no such file."""
    path = (saved.get("source") or "").split("|")[0]
    if not path or not Path(path).is_file():
        return None
    name = saved.get("name") or Path(path).stem
    if saved.get("provider") == RASTER_PROVIDER:
        layer = QgsRasterLayer(saved["source"], name)
    else:
        layer = QgsVectorLayer(saved["source"], name, "ogr")
    if not layer.isValid():
        return None
    wanted = QgsCoordinateReferenceSystem(saved.get("crs") or "")
    if (
        wanted.isValid() and wanted != layer.crs()
    ):  # a file that names no CRS, which the user had set on the layer
        layer.setCrs(wanted)
    QgsProject.instance().addMapLayer(layer)
    return layer


def read(widget):
    """The widget's value as JSON can hold it."""
    if isinstance(widget, QgsMapLayerComboBox):
        return layer_state(widget.currentLayer())
    if isinstance(widget, QgsFieldComboBox):
        return widget.currentField()
    if isinstance(widget, QgsFileWidget):
        return widget.filePath()
    if isinstance(widget, QComboBox):
        data = widget.currentData()
        return {"data": data if isinstance(data, PLAIN) else None, "text": widget.currentText()}
    if isinstance(widget, QGroupBox):
        return widget.isChecked()
    if isinstance(widget, QAbstractButton):
        return widget.isChecked()
    if isinstance(widget, QLineEdit):
        return widget.text()
    if isinstance(widget, QAbstractSpinBox):
        return widget.value()
    return [list(row) for row in widget.rows()]  # a pair table


def write(widget, value, add_missing: bool = False, hold: bool = False) -> str:
    """Set the widget; what could not be set, in words, or an empty string. ``hold`` is for a list the engine fills
    later: the saved choice is put into the empty list, to be found there when the answer comes."""
    if isinstance(widget, QgsMapLayerComboBox):
        return _write_layer(widget, value, add_missing)
    if isinstance(widget, QgsFieldComboBox):
        widget.setField(value or "")
        return "" if widget.currentField() == (value or "") else f'no field "{value}" in the layer'
    if isinstance(widget, QgsFileWidget):
        widget.setFilePath(value or "")
        return ""
    if isinstance(widget, QComboBox):
        return _write_combo(widget, value, hold)
    if isinstance(widget, (QGroupBox, QAbstractButton)):
        widget.setChecked(bool(value))
        return ""
    if isinstance(widget, QLineEdit):
        widget.setText(value or "")
        return ""
    if isinstance(widget, QAbstractSpinBox):
        widget.setValue(type(widget.value())(value))
        return ""
    widget.set_rows([tuple(row) for row in value or []])
    return ""


def _write_layer(widget, saved, add_missing: bool) -> str:
    if not saved:
        widget.setLayer(None)
        return ""
    layer = find_layer(saved)
    added = ""
    if layer is None and add_missing:
        layer = add_layer(saved)
        added = f'{NOTE}layer "{saved.get("name")}" added to the project from {saved.get("source", "").split("|")[0]}'
    if layer is None:
        widget.setLayer(None)
        return f'layer "{saved.get("name")}" ({saved.get("source")}) is not in this project'
    widget.setLayer(layer)
    if widget.currentLayer() is not layer:
        return f'layer "{layer.name()}" is not of the kind this field takes'
    return added


def _write_combo(widget, saved, hold: bool = False) -> str:
    if not isinstance(saved, dict):
        saved = {"data": None, "text": "" if saved is None else str(saved)}
    data, text = saved.get("data"), saved.get("text") or ""
    index = widget.findData(data) if data is not None else -1
    if index < 0:
        index = widget.findText(text)
    if index < 0 and widget.isEditable():
        widget.setCurrentText(text)
        return ""
    if (
        index < 0 and text and hold and widget.count() == 0
    ):  # the engine has not answered yet: keep the choice
        widget.addItem(text)
        index = 0
    if index < 0:
        return f'no choice "{text}"' if text else ""
    widget.setCurrentIndex(index)
    return ""


# Tables of dataclass rows


def read_rows(rows: list) -> list[dict]:
    return [dataclasses.asdict(row) for row in rows]


def write_rows(row_class, saved: list[dict]) -> list:
    """Rows of ``row_class`` from saved dicts; a field the class no longer has is dropped, a new one takes its default."""
    names = {field.name for field in dataclasses.fields(row_class)}
    return [
        row_class(**{key: value for key, value in entry.items() if key in names}) for entry in saved or []
    ]


def resolve(owner, path: str):
    """The object at a dotted path under ``owner``; an empty path is the owner itself."""
    target = owner
    for part in filter(None, path.split(".")):
        target = target[part] if isinstance(target, dict) else getattr(target, part)
    return target
