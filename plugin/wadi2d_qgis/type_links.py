# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The model type and what follows from it in the dock (W99).

The start page chooses a type, or none; this keeps it, shows the sections a model of that type uses, tells Hydrology
what the type leaves to choose, lays the type's own values over the dock's before a job is built, and gives the type
to the saved model. With no type the dock is what it was: every section, and a job that names no type.
"""

from __future__ import annotations

from qgis.PyQt.QtCore import QObject

from .job_builder import LayerError
from .model_types import MODEL_TYPE, TYPES, apply_type, inferred, sections_shown, title_of, type_notes

PAGE_START, PAGE_MODEL = "start", "model"
OLD_ENGINE = "This engine is from before the model types: the job will not name the type, and the engine reads it from the job."


class TypeLinks(QObject):
    def __init__(self, dock) -> None:
        super().__init__(dock)
        self.dock = dock
        self.start, self.header = dock.start_page, dock.header
        self.kind: str | None = None
        self.page = PAGE_START
        self._infer = False
        self._engine_knows = True
        for card in self.start.cards.values():
            card.clicked.connect(self.choose)
        self.start.all_button.clicked.connect(lambda: self.choose(None))
        self.start.open_run_button.clicked.connect(self.open_run)
        self.header.back_button.clicked.connect(self.back)
        self.header.show_all.toggled.connect(self.refresh)
        self.refresh()

    def apply_schema(self, schema) -> None:
        self._engine_knows = schema.has(MODEL_TYPE)

    # Choosing

    def choose(self, kind: str | None) -> None:
        """A type from the start page, or None for every section and no type; the model's sections follow."""
        self.kind = kind if kind in TYPES else None
        self.page = PAGE_MODEL
        self.refresh()

    def back(self) -> None:
        self.page = PAGE_START
        self.refresh()

    def open_run(self) -> None:
        """The start page's Open run: the model of the run, its type with it, and its results at hand."""
        self.dock.model.open_run(self.start.run_folder.filePath())
        said = self.dock.model_bar.message.text()
        if self.page == PAGE_START:  # nothing was opened: the reason belongs on this page
            self.start.say(said)

    def refresh(self, *_) -> None:
        dock = self.dock
        dock.pages.setCurrentIndex(0 if self.page == PAGE_START else 1)
        self.start.mark(self.kind)
        self.header.show_type(self.kind)
        shown = sections_shown(self.kind, self.header.show_all.isChecked())
        for section in dock.sections:
            section.setVisible(section.key in shown)
        dock.hydrology.set_model_type(self.kind)

    # The job

    def values(self, raw: dict) -> dict:
        """The dock's values as a model of this type gives them to the job builder."""
        notes = type_notes(raw, self.kind)
        typed = apply_type(raw, self.kind)
        if self.kind in TYPES and not self._engine_knows:
            typed.pop("model_type", None)
            notes.append(OLD_ENGINE)
        self.header.say(" ".join(notes))
        return typed

    # The saved model

    def parts(self) -> dict:
        return {"model_type": self.kind, "show_all": self.header.show_all.isChecked(), "page": self.page}

    def set_parts(self, doc: dict) -> None:
        """Before the sections are restored. A model saved with no word on its type gets one from its own content."""
        self._infer = "model_type" not in doc
        self.kind = doc.get("model_type") if doc.get("model_type") in TYPES else None
        self.page = doc.get("page") if doc.get("page") in (PAGE_START, PAGE_MODEL) else PAGE_MODEL
        self.header.show_all.setChecked(bool(doc.get("show_all")))

    def restored(self, job_type: str | None = None, infer: bool = False) -> None:
        """After the sections are restored: the type the job named, or the one the model runs as, where none was
        saved. ``infer`` is a run opened from its job alone, which never says what page it was on."""
        if infer:
            self._infer, self.page = True, PAGE_MODEL
        if job_type in TYPES:
            self.kind, self.page = job_type, PAGE_MODEL
        elif self._infer:
            try:
                self.kind = inferred(self.dock.raw_values())
            except LayerError:
                self.kind = None
        self._infer = False
        self.refresh()

    def words(self) -> str:
        return title_of(self.kind)
