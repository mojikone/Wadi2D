# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Where the dock's model is kept, and how it comes back (W99).

- **With the QGIS project**, as one text entry of the project's own properties. In the project and not in a file
  beside it, because a layer choice is a layer id, which means something only inside that project; because it is saved
  and renamed with the project in one go, so the two cannot part; and because an unsaved project has no place for a
  file beside it. The copies anyone can read without QGIS are the next two.
- **In every run folder**, ``model.wadi2d.json`` beside ``job.json``, written when Run is pressed: Open a run refills
  the dock from it. A run from before W99 has only its job: :mod:`job_reader` takes what the job can tell.
- **As scenarios**, named copies in ``scenarios/`` inside the output folder.

The entry is kept up to date by a timer that compares the dock with what was last written: every widget of every
section would otherwise need its own change signal wired, and a new widget would be forgotten. A change marks the
project as modified, so QGIS asks to save on closing, as it does for a moved layer.
"""

from __future__ import annotations

import configparser
import contextlib
import json
from pathlib import Path

from qgis.core import QgsProject
from qgis.PyQt.QtCore import QObject, QTimer

from . import model_doc
from .protocol import JOB_FILE
from .widget_state import NOTE

ENTRY_SCOPE = "Wadi2D"
ENTRY_KEY = "model"
KEEP_MS = 2000
"""How often the dock is compared with the project's copy."""
RESTORED = "The model was restored from the QGIS project."
NOT_RESTORED = "Could not be restored:"
ADDED = "Added:"
NO_FOLDER = "Choose the output folder in Run first: scenarios are kept inside it."
NO_NAME = "Give the scenario a name."
NO_RUN = "There is no run in this folder: it holds neither a saved model nor a job."


def plugin_version() -> str:
    parser = configparser.ConfigParser()
    try:
        parser.read(Path(__file__).with_name("metadata.txt"), encoding="utf-8")
        return parser.get("general", "version", fallback="")
    except (configparser.Error, OSError):
        return ""


def outcome(first: str, words: list[str]) -> str:
    """What was done, what was added to the project on the way, and what could not be restored."""
    news = [text[len(NOTE) :] for text in words if text.startswith(NOTE)]
    lost = [text for text in words if not text.startswith(NOTE)]
    parts = [first]
    if news:
        parts.append(f"{ADDED} {'; '.join(news)}.")
    if lost:
        parts.append(f"{NOT_RESTORED} {'; '.join(lost)}.")
    return " ".join(parts)


def labelled(section, words: list[str]) -> list[str]:
    """A section's words with its heading; news keeps its mark and needs no heading."""
    return [text if text.startswith(NOTE) else f"{section.heading}, {text}" for text in words]


class ModelLinks(QObject):
    """The dock's model in and out of the project, a run folder and the scenarios."""

    def __init__(self, dock) -> None:
        super().__init__(dock)
        self.dock = dock
        self.bar = dock.model_bar
        self.ready = False
        self._applying = False
        self._last = ""
        self._pristine: dict | None = None
        self._version = plugin_version()
        self._timer = QTimer(self)
        self._timer.setInterval(KEEP_MS)
        self._timer.timeout.connect(self.keep)
        project = QgsProject.instance()
        project.readProject.connect(self._project_read)
        project.cleared.connect(self._project_cleared)
        project.writeProject.connect(self._project_writing)
        self.bar.open_run_button.clicked.connect(lambda: self.open_run(self.bar.run_folder.filePath()))
        self.bar.save_button.clicked.connect(lambda: self.save_scenario(self.bar.scenario_name.text()))
        self.bar.open_button.clicked.connect(lambda: self.open_scenario(self.bar.scenarios.currentData()))
        dock.panel.folder.fileChanged.connect(self.list_scenarios)

    # The document

    def collect(self) -> dict:
        sections = {section.key: section.state() for section in self.dock.sections}
        return model_doc.new_doc(sections, self._version, **self.dock.model_parts())

    def apply(self, doc: dict, add_missing: bool = False) -> list[str]:
        """Fill the dock from a document; what could not be restored, section by section."""
        words = []
        self._applying = True
        try:
            self.dock.set_model_parts(doc)
            for section in self.dock.sections:
                state = doc["sections"].get(section.key)
                if state is None:
                    continue
                try:
                    words += labelled(section, section.restore(state, add_missing))
                except (KeyError, TypeError, ValueError, AttributeError) as problem:  # a file edited by hand
                    words.append(f"{section.heading}, its saved state could not be read ({problem})")
        finally:
            self._applying = False
        self.dock.model_applied()
        return words

    # The QGIS project

    def start(self) -> None:
        """The engine has answered and every section holds its defaults: from now on the model is kept."""
        self._pristine = {**self.collect(), **self.dock.fresh_parts()}
        self._last = model_doc.fingerprint(self._pristine)
        self.ready = True
        self.restore_from_project()
        self.list_scenarios()
        self._timer.start()

    def restore_from_project(self) -> None:
        text, found = QgsProject.instance().readEntry(ENTRY_SCOPE, ENTRY_KEY, "")
        if not found or not text:
            return
        try:
            doc = model_doc.loads(text)
        except ValueError as problem:
            self.bar.say(str(problem))
            return
        words = self.apply(doc)
        self._last = model_doc.fingerprint(self.collect())
        self.bar.say(outcome(RESTORED, words) if words else "")

    def keep(self) -> None:
        """Write the model into the project when it differs from what was last written there."""
        if not self.ready or self._applying:
            return
        doc = self.collect()
        mark = model_doc.fingerprint(doc)
        if mark != self._last:
            QgsProject.instance().writeEntry(ENTRY_SCOPE, ENTRY_KEY, model_doc.dumps(doc))
            self._last = mark

    def _project_read(self, *_) -> None:
        if self.ready:
            self.restore_from_project()

    def reset(self) -> None:
        """The dock as it stood when the engine first answered: every section at its defaults."""
        if self.ready and self._pristine is not None:
            self.apply(self._pristine)

    def _project_cleared(self) -> None:
        """A new project, or the moment before another is read: the dock goes back to its defaults."""
        if self.ready:
            self.reset()
            self._last = model_doc.fingerprint(self.collect())
            self.bar.say("")

    def _project_writing(self, *_) -> None:
        self.keep()

    # A run folder

    def write_run_copy(self, run_folder: Path | str) -> None:
        """The model that made a run, into its folder. A copy that cannot be written stops no run."""
        with contextlib.suppress(OSError):
            model_doc.write_doc(Path(run_folder) / model_doc.MODEL_FILE, self.collect())

    def open_run(self, folder: str) -> None:
        """Refill the dock from a finished run: its saved model, or what its job can tell."""
        if not self.ready:
            return
        root = Path(folder) if folder else None
        if root is None or not root.is_dir():
            self.bar.say(NO_RUN)
            return
        saved, job = root / model_doc.MODEL_FILE, root / JOB_FILE
        if saved.is_file():
            try:
                doc = model_doc.read_doc(saved)
            except (OSError, ValueError) as problem:
                self.bar.say(str(problem))
                return
            self.reset()
            words = self.apply(doc, add_missing=True)
            self.bar.say(outcome(f"The model of run {root.name} is in the dock.", words))
        elif job.is_file():
            from .job_reader import refill

            try:
                words = refill(self, json.loads(job.read_text(encoding="utf-8")), root)
            except (OSError, ValueError) as problem:
                self.bar.say(f"The job of run {root.name} could not be read: {problem}")
                return
            first = f"Run {root.name} has no saved model: the dock holds what its job tells."
            self.bar.say(outcome(first, words))
        else:
            self.bar.say(NO_RUN)
            return
        self.keep()
        self.dock.show_run(str(root))

    # Scenarios

    def model_folder(self) -> str:
        return self.dock.panel.folder.filePath()

    def list_scenarios(self, *_) -> None:
        self.bar.show_scenarios(model_doc.list_scenarios(self.model_folder()))

    def save_scenario(self, name: str) -> Path | None:
        if not self.ready:
            return None
        folder, name = self.model_folder(), model_doc.safe_name(name or "")
        if not folder or not name:
            self.bar.say(NO_FOLDER if not folder else NO_NAME)
            return None
        try:
            path = model_doc.write_doc(model_doc.scenario_path(folder, name), self.collect())
        except OSError as problem:
            self.bar.say(f"The scenario could not be written: {problem}")
            return None
        self.list_scenarios()
        self.bar.scenarios.setCurrentIndex(max(self.bar.scenarios.findText(name), 0))
        self.bar.say(f"Scenario {name} saved: {path}")
        return path

    def open_scenario(self, path: str | None) -> None:
        if not self.ready or not path:
            return
        try:
            doc = model_doc.read_doc(path)
        except (OSError, ValueError) as problem:
            self.bar.say(str(problem))
            return
        self.reset()
        words = self.apply(doc, add_missing=True)
        name = Path(path).name[: -len(model_doc.SCENARIO_SUFFIX)]
        self.bar.say(outcome(f"Scenario {name} is in the dock.", words))
        self.keep()

    def release(self) -> None:
        """QGIS is closing or the plugin is being reloaded: no more reading of widgets that are going away."""
        self._timer.stop()
        self.ready = False
        project = QgsProject.instance()
        for signal, slot in (
            (project.readProject, self._project_read),
            (project.cleared, self._project_cleared),
            (project.writeProject, self._project_writing),
        ):
            with contextlib.suppress(TypeError, RuntimeError):
                signal.disconnect(slot)
