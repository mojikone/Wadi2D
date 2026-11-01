"""``results\\DAA_*.results``: the statistics of a depth-area analysis.

Interface: :func:`load`, :class:`AnalysisResults`, :class:`ElementStatistics`. One element appears once per
analysis point it drains to, each time with that point's area reduction, so results are keyed by (analysis
point, element). Every ``StatisticMeasure`` stays in ``ElementStatistics.measures``; the named attributes
are the ones the rest of Wadi2D needs. Values are the file's own: its ``units`` attributes say what they
are.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree

from wadi2d.hms.typed import parse_stamp

POINT_TAG = "AnalysisPoint"
ELEMENT_TAG = "BasinElement"
MEASURE_PATH = "Statistics/StatisticMeasure"

OUTFLOW_MAXIMUM = "Outflow Maximum"
OUTFLOW_MAXIMUM_TIME = "Outflow Maximum Time"
OUTFLOW_VOLUME = "Outflow Volume"
OUTFLOW_DEPTH = "Outflow Depth"
PRECIPITATION_TOTAL = "Precipitation Total"
LOSS_TOTAL = "Loss Total"
EXCESS_TOTAL = "Excess Total"


@dataclass(frozen=True)
class Measure:
    """One ``StatisticMeasure``: the raw value (a number or a time stamp) and its units."""

    value: str
    units: str | None = None

    def number(self) -> float:
        """The value as a number."""
        return float(self.value)


@dataclass(frozen=True)
class ElementStatistics:
    """The statistics of one element at one analysis point."""

    analysis_point: str
    element: str
    element_type: str
    drainage_area: float | None = None
    subbasin_area: float | None = None
    area_units: str | None = None
    measures: dict[str, Measure] = field(default_factory=dict)

    def _number(self, measure: str) -> float | None:
        found = self.measures.get(measure)
        return None if found is None else found.number()

    @property
    def outflow_max(self) -> float | None:
        """Peak outflow."""
        return self._number(OUTFLOW_MAXIMUM)

    @property
    def outflow_max_time(self) -> datetime | None:
        """Time of the peak outflow."""
        found = self.measures.get(OUTFLOW_MAXIMUM_TIME)
        return None if found is None else parse_stamp(found.value)

    @property
    def outflow_volume(self) -> float | None:
        """Outflow volume."""
        return self._number(OUTFLOW_VOLUME)

    @property
    def outflow_depth(self) -> float | None:
        """Outflow volume as a depth over the drainage area."""
        return self._number(OUTFLOW_DEPTH)

    @property
    def precipitation(self) -> float | None:
        """Total precipitation depth; subbasins only."""
        return self._number(PRECIPITATION_TOTAL)

    @property
    def loss(self) -> float | None:
        """Total loss depth; subbasins only."""
        return self._number(LOSS_TOTAL)

    @property
    def excess(self) -> float | None:
        """Total excess depth; subbasins only."""
        return self._number(EXCESS_TOTAL)


@dataclass(frozen=True)
class AnalysisResults:
    """One results file; ``points[point][element]`` gives the statistics."""

    name: str
    start: datetime | None
    end: datetime | None
    execution_time: datetime | None
    points: dict[str, dict[str, ElementStatistics]] = field(default_factory=dict)

    def element(self, point: str, element: str | None = None) -> ElementStatistics:
        """The statistics of ``element`` at ``point``; the point's own element when ``element`` is omitted."""
        return self.points[point][element or point]

    def own_points(self) -> dict[str, ElementStatistics]:
        """Each analysis point read at its own element: the design flows."""
        return {point: elements[point] for point, elements in self.points.items() if point in elements}


def _stamp(root: ElementTree.Element, tag: str) -> datetime | None:
    found = root.findtext(tag)
    return None if found is None else parse_stamp(found)


def _area(node: ElementTree.Element | None) -> tuple[float | None, str | None]:
    if node is None:
        return None, None
    return float(node.attrib["area"]), node.get("units")


def _element(point: str, node: ElementTree.Element) -> ElementStatistics:
    drainage, units = _area(node.find("DrainageArea"))
    subbasin, subbasin_units = _area(node.find("SubbasinArea"))
    measures = {
        m.attrib["type"]: Measure(m.attrib["value"], m.get("units")) for m in node.iterfind(MEASURE_PATH)
    }
    return ElementStatistics(
        analysis_point=point,
        element=node.attrib["name"],
        element_type=node.get("type", ""),
        drainage_area=drainage,
        subbasin_area=subbasin,
        area_units=units or subbasin_units,
        measures=measures,
    )


def load(path: str | Path) -> AnalysisResults:
    """Read a ``.results`` XML file."""
    root = ElementTree.parse(path).getroot()
    points: dict[str, dict[str, ElementStatistics]] = {}
    for point in root.iter(POINT_TAG):
        name = point.attrib["name"]
        elements = (_element(name, node) for node in point.iter(ELEMENT_TAG))
        points[name] = {statistics.element: statistics for statistics in elements}
    return AnalysisResults(
        name=root.findtext("AnalysisName", default=""),
        start=_stamp(root, "StartTime"),
        end=_stamp(root, "EndTime"),
        execution_time=_stamp(root, "ExecutionTime"),
        points=points,
    )
