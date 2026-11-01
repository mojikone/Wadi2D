"""HEC-HMS file readers: project text files, basin geometry, depth-area results and DSS records.

Two layers: :mod:`wadi2d.hms.text` is a lossless tokenizer, the other modules type its blocks. Nothing here
writes to an HMS project. See ``README.md`` beside this file.
"""

from __future__ import annotations

from wadi2d.hms.basin import Basin, Connectivity
from wadi2d.hms.basin import load as load_basin
from wadi2d.hms.control import Control
from wadi2d.hms.control import load as load_control
from wadi2d.hms.dss import (
    DssFile,
    DssPathname,
    PairedTable,
    TimeSeries,
    daa_fpart,
    met_fpart,
    open_dss,
    run_fpart,
)
from wadi2d.hms.met import Met
from wadi2d.hms.met import load as load_met
from wadi2d.hms.nals import NalsFile
from wadi2d.hms.nals import load as load_nals
from wadi2d.hms.pdata import PairedDataFile
from wadi2d.hms.pdata import load as load_pdata
from wadi2d.hms.project import Project
from wadi2d.hms.project import load as load_project
from wadi2d.hms.results import AnalysisResults, ElementStatistics
from wadi2d.hms.results import load as load_results
from wadi2d.hms.run import RunFile
from wadi2d.hms.run import load as load_run
from wadi2d.hms.text import Document
from wadi2d.hms.text import load as load_document

__all__ = [
    "AnalysisResults",
    "Basin",
    "Connectivity",
    "Control",
    "Document",
    "DssFile",
    "DssPathname",
    "ElementStatistics",
    "Met",
    "NalsFile",
    "PairedDataFile",
    "PairedTable",
    "Project",
    "RunFile",
    "TimeSeries",
    "daa_fpart",
    "load_basin",
    "load_control",
    "load_document",
    "load_met",
    "load_nals",
    "load_pdata",
    "load_project",
    "load_results",
    "load_run",
    "met_fpart",
    "open_dss",
    "run_fpart",
]
