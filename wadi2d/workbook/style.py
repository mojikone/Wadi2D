"""The look of the dam workbook: cell styles and the chart style of the W1 template.

Interface: :data:`FONT`, :func:`font`, :func:`header`, :data:`BOX`, :data:`BLUE_IN`, :data:`GREY`, :data:`RAMP`,
:data:`DAM_COLOURS`, :func:`style_chart`. Light hairline gridlines, light grey axes, Arial 9 pt labels, 11 pt bold
title, no chart border.
"""

from __future__ import annotations

from openpyxl.chart.axis import ChartLines
from openpyxl.chart.shapes import GraphicalProperties
from openpyxl.chart.text import RichText
from openpyxl.drawing.line import LineProperties
from openpyxl.drawing.text import CharacterProperties, Paragraph, ParagraphProperties
from openpyxl.drawing.text import Font as DrawingFont
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

FONT = "Arial"
HEADER_FILL = PatternFill("solid", fgColor="1F4E79")
_THIN = Side(style="thin", color="BFBFBF")
BOX = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)
BLUE_IN = Font(name=FONT, size=10, color="0000FF")
"""An input typed in, not a formula: the catchment areas."""
GREY = Font(name=FONT, size=9, color="7F7F7F")
RAMP = [
    "C6DBEF",
    "B3CDE8",
    "9EC9E2",
    "86B9DC",
    "6BAED6",
    "4F9BCF",
    "3E8AC5",
    "3182BD",
    "2171B5",
    "1A5FA3",
    "0D4A8E",
    "08306B",
]
"""Return periods, light to dark; the PMP is black and dashed."""
DAM_COLOURS = ["1F4E79", "C55A11", "548235", "7030A0", "BF9000", "2E75B6", "A50021", "00B0F0"]
OUTFLOW_COLOUR = "C55A11"
GRID, AXIS, INK, MUTED = "EDEDED", "BFBFBF", "404040", "595959"


def font(size: int = 10, **kw) -> Font:
    return Font(name=FONT, size=size, **kw)


def header(cell, wrap: bool = True) -> None:
    cell.font = font(bold=True, color="FFFFFF")
    cell.fill = HEADER_FILL
    cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=wrap)
    cell.border = BOX


def _rich(size: int, bold: bool = False, colour: str = INK) -> RichText:
    cp = CharacterProperties(sz=size, b=bold, solidFill=colour, latin=DrawingFont(typeface=FONT))
    return RichText(p=[Paragraph(pPr=ParagraphProperties(defRPr=cp), endParaRPr=cp)])


def _title_font(title, size: int, bold: bool, colour: str) -> None:
    try:
        for p in title.tx.rich.p:
            cp = CharacterProperties(sz=size, b=bold, solidFill=colour, latin=DrawingFont(typeface=FONT))
            p.pPr = ParagraphProperties(defRPr=cp)
            for r in p.r or []:
                r.rPr = cp
    except AttributeError:
        pass


def style_chart(ch, grid_y: bool = True, label_size: int = 900, title_size: int = 1100):
    """The W1 chart style, in place; call after the title, axes and legend are set."""
    ch.style = 2
    ch.roundedCorners = False
    ch.graphical_properties = GraphicalProperties(ln=LineProperties(noFill=True))
    ch.plot_area.graphicalProperties = GraphicalProperties(noFill=True, ln=LineProperties(noFill=True))
    for ax, grid in ((ch.y_axis, grid_y), (ch.x_axis, False)):
        ax.spPr = GraphicalProperties(ln=LineProperties(solidFill=AXIS, w=9525))
        ax.txPr = _rich(label_size, colour=MUTED)
        ax.majorGridlines = (
            ChartLines(spPr=GraphicalProperties(ln=LineProperties(solidFill=GRID, w=6350))) if grid else None
        )
        ax.minorGridlines = None
        if ax.title is not None:
            _title_font(ax.title, label_size, False, MUTED)
    if ch.title is not None:
        ch.title.overlay = False
        _title_font(ch.title, title_size, True, INK)
    if ch.legend is not None:
        ch.legend.overlay = False
        ch.legend.txPr = _rich(label_size, colour=MUTED)
        ch.legend.graphicalProperties = GraphicalProperties(noFill=True, ln=LineProperties(noFill=True))
    return ch
