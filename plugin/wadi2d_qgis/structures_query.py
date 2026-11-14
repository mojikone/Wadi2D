# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The Hydrology section's question to the engine when an HMS basin is chosen: what each reservoir routes by (W75)."""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from qgis.PyQt.QtCore import QObject

from . import settings
from .engine_process import EngineQuery
from .hms_structure_rows import reservoir_rows, structures_args, structures_note
from .protocol import engine_error_text, exit_message

ANSWER_FILE = "hms_structures.json"


class StructuresLinks(QObject):
    """Answers the Hydrology section's ``structures_requested`` for the dock."""

    def __init__(self, dock) -> None:
        super().__init__(dock)
        self.hydrology = dock.hydrology
        self._query: EngineQuery | None = None
        self._scratch: str | None = None
        self.hydrology.structures_requested.connect(self.ask)

    def ask(self, basin_file: str) -> None:
        self._drop()
        self._scratch = tempfile.mkdtemp(prefix="wadi2d_structures_")
        self.hydrology.say_structures("Reading the reservoirs ...")
        self._query = EngineQuery(settings.engine_text(), self)
        self._query.done.connect(self._answered)
        self._query.start(structures_args(basin_file, Path(self._scratch) / ANSWER_FILE))

    def _answered(self, code: int, _out: str, err: str) -> None:
        try:
            if code != 0:
                raise ValueError(f"{exit_message(code)} {engine_error_text(err)}".strip())
            found = json.loads((Path(self._scratch) / ANSWER_FILE).read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError) as problem:
            self.hydrology.show_structures([], f"The reservoirs could not be read. {problem}")
        else:
            self.hydrology.show_structures(reservoir_rows(found), structures_note(found))
        finally:
            self._drop()

    def _drop(self) -> None:
        if self._scratch:
            shutil.rmtree(self._scratch, ignore_errors=True)
            self._scratch = None
