# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The Propose K and X button of the Hydrology section's reach table (W89): one question to the engine."""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from qgis.PyQt.QtCore import QObject

from . import settings
from .engine_process import EngineQuery
from .muskingum_rows import proposal_args
from .protocol import engine_error_text, exit_message

ANSWER_FILE = "muskingum.json"
NO_BASIN = "Choose an HMS basin file, or generate the basin, first: the proposal is made from its reaches."


class MuskingumLinks(QObject):
    """Answers the reach table's ``propose_requested`` for the dock."""

    def __init__(self, dock) -> None:
        super().__init__(dock)
        self.hydrology = dock.hydrology
        self.box = dock.hydrology.muskingum
        self._query: EngineQuery | None = None
        self._scratch: str | None = None
        self.box.propose_requested.connect(self.ask)

    def ask(self) -> None:
        source = self.hydrology.reach_source()
        if source is None:
            self.box.say(NO_BASIN)
            return
        basin_file, control = source
        self._drop()
        self._scratch = tempfile.mkdtemp(prefix="wadi2d_muskingum_")
        self.box.say("Proposing ...")
        self.box.set_busy(True)
        self._query = EngineQuery(settings.engine_text(), self)
        self._query.done.connect(self._answered)
        out = Path(self._scratch) / ANSWER_FILE
        self._query.start(proposal_args(basin_file, out, self.box.rows, self.box.velocity_ms(), control))

    def _answered(self, code: int, _out: str, err: str) -> None:
        try:
            if code != 0:
                raise ValueError(f"{exit_message(code)} {engine_error_text(err)}".strip())
            found = json.loads((Path(self._scratch) / ANSWER_FILE).read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError) as problem:
            self.box.say(f"No proposal could be made. {problem}")
        else:
            self.box.take(found)
        finally:
            self.box.set_busy(False)
            self._drop()

    def _drop(self) -> None:
        if self._scratch:
            shutil.rmtree(self._scratch, ignore_errors=True)
            self._scratch = None
