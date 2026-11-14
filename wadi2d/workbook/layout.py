"""The dam workbook's sheets, in the layout he approved on 2026-11-14 (the W1 template, Status column removed).

Interface: :func:`build`, :func:`write`, :data:`STATS_FIRST_ROW`, :func:`dam_columns`.

Sheets in order: Read me; the target return period (dams side by side, statistics, one chart); Peak inflow, Inflow
volume, Time to peak (formulas into the dam sheets); with a reservoir also Peak outflow, Attenuation, Highest pool
level; then one sheet per dam: time in column A, the series of every return period, one empty column, the statistics
block (formulas), the dam's facts, the main inflow chart and below it one inflow-outflow chart per return period,
three across. Data cells are the series rounded as W1 rounds them (time 4 decimals, flow 3); everything else is a
formula on them, the step written into each volume formula as its number.
"""

from __future__ import annotations

import math
from datetime import date
from pathlib import Path

from openpyxl import Workbook
from openpyxl.chart import Reference, ScatterChart, Series
from openpyxl.chart.label import DataLabelList
from openpyxl.chart.layout import Layout, ManualLayout
from openpyxl.chart.legend import LegendEntry
from openpyxl.chart.series import SeriesLabel, StrRef
from openpyxl.drawing.spreadsheet_drawing import AnchorMarker, OneCellAnchor
from openpyxl.drawing.xdr import XDRPositiveSize2D
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter as L
from openpyxl.utils.units import cm_to_EMU, pixels_to_EMU

from wadi2d.workbook import style
from wadi2d.workbook.model import (
    ATTENUATION,
    HIGHEST_POOL,
    INFLOW_VOLUME,
    PEAK_INFLOW,
    PEAK_OUTFLOW,
    PMP,
    READ_ME,
    TIME_TO_PEAK,
    Dam,
    WorkbookInput,
    rp_label,
    structure_name,
    target_sheet_name,
)

FIRST = 2
"""First data row; row 1 holds the headings."""
STATS_FIRST_ROW = 2
FACTS_ROW = 17
"""W1's dam facts start here when the return periods fit above it."""
MAIN_CHART_CM = (30.0, 15.0)
TILE_CM = (15.0, 7.5)
TILE_GAP_CM = 0.4
TILES_ACROSS = 3
ROW_EMU = 190500
"""A default row, 15 pt."""
UNITS = {"inflow": "m³/s", "outflow": "m³/s", "pool": "m", "storage": "Mm³"}
ROUND = {"inflow": (3, "0.0"), "outflow": (3, "0.0"), "pool": (3, "0.00"), "storage": (4, "0.000")}
STATS = [
    "Return period",
    "Peak inflow (m³/s)",
    "Time to peak (h)",
    "Inflow volume (Mm³)",
    "Legend: return period",
    "Label: peak",
]
STATS_WIDTH = [12, 13, 12, 13, 36, 22]
ROUTED_STATS = {
    "outflow": [("Peak outflow (m³/s)", "#,##0", 13), ("Attenuation (-)", "0.0%", 12)],
    "pool": [("Highest pool (m)", "0.00", 12)],
    "storage": [("Highest storage (Mm³)", "0.000", 13)],
}


def _words(quantity: str) -> str:
    """``structure:rating_spillway_1`` -> ``rating spillway 1``; the other quantities as they are."""
    name = structure_name(quantity)
    return quantity if name is None else name.replace("_", " ")


def _heading(quantity: str, rp: str) -> str:
    """W1's ``Inflow_200yr``; a structure's ``Orifice_1_200yr`` (W74)."""
    name = structure_name(quantity)
    return f"{(quantity if name is None else name).capitalize()}_{rp}"


def _rounding(quantity: str) -> tuple[int, str]:
    return ROUND.get(quantity, ROUND["outflow"])


def _stats_of(quantity: str) -> list[tuple[str, str, int]]:
    """The statistics columns a quantity adds after W1's; a structure its peak flow."""
    if quantity in ROUTED_STATS:
        return ROUTED_STATS[quantity]
    return [(f"Peak {_words(quantity)} (m³/s)", "#,##0.0", 14)]


def dam_columns(dam: Dam, rps: list[str]) -> dict[tuple[str, str], int]:
    """(return period, quantity) -> column on the dam sheet; return periods in order, quantities within each."""
    qs = dam.quantities()
    return {(rp, q): 2 + k * len(qs) + j for k, rp in enumerate(rps) for j, q in enumerate(qs)}


def _plot_layout(ch, x, y, w, h) -> None:
    ch.layout = Layout(
        manualLayout=ManualLayout(layoutTarget="inner", xMode="edge", yMode="edge", x=x, y=y, w=w, h=h)
    )


def _series(
    xref, yref, title_ref: str, colour: str, width_emu: int = 19050, dash: str | None = None
) -> Series:
    s = Series(yref, xref, title=None)
    s.tx = SeriesLabel(strRef=StrRef(title_ref))
    s.marker.symbol = "none"
    s.smooth = False
    s.graphicalProperties.line.solidFill = colour
    s.graphicalProperties.line.width = width_emu
    s.graphicalProperties.line.cap = "rnd"
    if dash:
        s.graphicalProperties.line.dashStyle = dash
    return s


def _base_chart(title: str, size_cm: tuple[float, float], hours: float) -> ScatterChart:
    ch = ScatterChart()
    ch.title = title
    ch.style = 2
    ch.width, ch.height = size_cm
    ch.x_axis.title = "Time from start of storm (h)"
    ch.y_axis.title = "Flow (m³/s)"
    ch.x_axis.delete = ch.y_axis.delete = False
    ch.x_axis.scaling.min = 0
    ch.x_axis.scaling.max = max(6, 6 * math.ceil(hours / 6 - 1e-9))
    ch.x_axis.majorUnit = 6 if hours <= 96 else 12
    ch.y_axis.scaling.min = 0
    ch.x_axis.number_format = "0"
    ch.y_axis.number_format = "#,##0"
    style.style_chart(ch)
    return ch


def _peak_labels(ch, ws, q, rows_cols, peaks, keys, colours, ymax) -> None:
    """One invisible single-point series per peak with room for its label, the label cell its name."""
    labelled, last = [], -1e9
    for k in sorted(keys, key=lambda k: peaks[k]):
        if peaks[k] - last >= 0.04 * ymax:
            labelled.append(k)
            last = peaks[k]
    n0 = len(ch.series)
    for k in labelled:
        r, cx, cy, clab = rows_cols[k]
        s = Series(
            Reference(ws, min_col=cy, min_row=r, max_row=r),
            Reference(ws, min_col=cx, min_row=r, max_row=r),
            title=None,
        )
        s.tx = SeriesLabel(strRef=StrRef(f"{q}!${L(clab)}${r}"))
        s.marker.symbol = "circle"
        s.marker.size = 4
        s.marker.graphicalProperties.solidFill = colours[k]
        s.marker.graphicalProperties.line.solidFill = "FFFFFF"
        s.graphicalProperties.line.noFill = True
        s.dLbls = DataLabelList()
        s.dLbls.showVal = s.dLbls.showCatName = s.dLbls.showLegendKey = s.dLbls.showPercent = False
        s.dLbls.showSerName = True
        s.dLbls.position = "r"
        ch.series.append(s)
    ch.legend.legendEntry = [LegendEntry(idx=n0 + i, delete=True) for i in range(len(labelled))]


def _rp_colour(k: int, rp: str) -> str:
    return "000000" if rp == PMP else style.RAMP[k % len(style.RAMP)]


def _write_series(ws, col: int, values, quantity: str) -> None:
    """The column's data cells; none when this period's source did not write the quantity."""
    if values is None:
        return
    digits, fmt = _rounding(quantity)
    for i, v in enumerate(values):
        c = ws.cell(row=FIRST + i, column=col, value=round(float(v), digits))
        c.number_format = fmt


def _write_time(ws, t_h) -> None:
    style.header(ws.cell(row=1, column=1, value="Time (hrs)"))
    for i, th in enumerate(t_h):
        ws.cell(row=FIRST + i, column=1, value=round(float(th), 4)).number_format = "0.0000"


def _anchor(ws, col: int, row: int, dx_emu: int, size_cm: tuple[float, float]) -> OneCellAnchor:
    """A chart dx_emu to the right of column ``col`` (1-based) at ``row``, walking the column widths."""
    c = col - 1
    while True:
        width = ws.column_dimensions[L(c + 1)].width or 8.43
        px = pixels_to_EMU(int(width * 7 + 5))
        if dx_emu < px:
            break
        dx_emu -= px
        c += 1
    ext = XDRPositiveSize2D(cm_to_EMU(size_cm[0]), cm_to_EMU(size_cm[1]))
    return OneCellAnchor(_from=AnchorMarker(col=c, colOff=int(dx_emu), row=row - 1, rowOff=0), ext=ext)


def _dam_sheet(wb: Workbook, wi: WorkbookInput, dam: Dam, tile_charts: bool) -> int:
    """One dam's sheet; returns the column where its statistics block starts."""
    rps, ws = wi.return_periods, wb.create_sheet(dam.label)
    q, qs, cols = f"'{dam.label}'", dam.quantities(), dam_columns(dam, wi.return_periods)
    n = max(len(h.t_h) for h in dam.series.values())
    last = FIRST + n - 1
    longest = max(dam.series.values(), key=lambda h: len(h.t_h))
    _write_time(ws, longest.t_h)
    for (rp, quantity), ci in cols.items():
        style.header(ws.cell(row=1, column=ci, value=_heading(quantity, rp)))
        _write_series(ws, ci, dam.series[rp].column(quantity), quantity)
        ws.column_dimensions[L(ci)].width = 12
    ws.column_dimensions["A"].width = 10
    ws.row_dimensions[1].height = 30
    st = 1 + len(rps) * len(qs) + 2
    extras = [item for quantity in qs[1:] for item in _stats_of(quantity)]
    heads = STATS + [h for h, _, _ in extras]
    for j, (head, width) in enumerate(zip(heads, STATS_WIDTH + [w for _, _, w in extras], strict=True)):
        style.header(ws.cell(row=1, column=st + j, value=head))
        ws.column_dimensions[L(st + j)].width = width
    a = lambda j: L(st + j)  # noqa: E731
    rows_cols, peaks, colours = {}, {}, {}
    rng_t = f"$A${FIRST}:$A${last}"
    for k, rp in enumerate(rps):
        r = STATS_FIRST_ROW + k
        rng = {
            quantity: f"{L(cols[(rp, quantity)])}${FIRST}:{L(cols[(rp, quantity)])}${last}" for quantity in qs
        }
        vals = [
            rp_label(rp),
            f"=MAX({rng['inflow']})",
            f"=INDEX({rng_t},MATCH({a(1)}{r},{rng['inflow']},0))",
            f"=SUM({rng['inflow']})*{wi.dt_s}/1000000",
            f'={a(0)}{r}&": Qp "&TEXT({a(1)}{r},"#,##0")&" m³/s, V "&TEXT({a(3)}{r},"#,##0.00")&" Mm³"',
            f'={a(0)}{r}&"  "&TEXT({a(1)}{r},"#,##0")&" m³/s"',
        ]
        fmts = ["@", "#,##0", "0.00", "0.000", "@", "@"]
        j = len(vals)
        for quantity in qs[1:]:
            if quantity == "outflow":
                vals += [f"=MAX({rng['outflow']})", f'=IF({a(1)}{r}>0,1-{a(j)}{r}/{a(1)}{r},"")']
            else:
                vals.append(f"=MAX({rng[quantity]})")
            fmts += [f for _, f, _ in _stats_of(quantity)]
        for jj, (v, fm) in enumerate(zip(vals, fmts, strict=True)):
            c = ws.cell(row=r, column=st + jj, value=v)
            c.number_format = fm
            c.border = style.BOX
        rows_cols[rp] = (r, st + 2, st + 1, st + 5)
        peaks[rp] = float(max(dam.series[rp].inflow))
        colours[rp] = _rp_colour(k, rp)
    facts = max(FACTS_ROW, STATS_FIRST_ROW + len(rps) + 2)
    ws.cell(row=facts, column=st, value="Dam").font = style.font(bold=True)
    ws.cell(row=facts, column=st + 1, value=dam.label)
    ws.cell(row=facts + 1, column=st, value=dam.element_kind or "Element").font = style.font(bold=True)
    ws.cell(row=facts + 1, column=st + 1, value=dam.name)
    ws.cell(row=facts + 2, column=st, value="Catchment (km²)").font = style.font(bold=True)
    c = ws.cell(row=facts + 2, column=st + 1, value=dam.catchment_km2)
    c.font, c.number_format = style.BLUE_IN, "0.00"
    span = f"A:{L(1 + len(rps) * len(qs))}"
    more = [x for x, k in (("pool level", "pool"), ("storage", "storage")) if k in qs]
    built = [_words(quantity) for quantity in qs if structure_name(quantity) is not None]
    if built:
        more.append(f"the flow through each structure ({', '.join(built)})")
    if dam.routed:
        tail = " Each return period carries the inflow and the outflow routed through the reservoir"
        tail += (
            f", with its {' and '.join(more)}." if more else "; the source wrote no pool level or storage."
        )
    else:
        tail = " No reservoir in the model: the series is the inflow at the dam site."
    note = f"Columns {span} are the {wi.source_short} series (data); the statistics and the summary sheets are formulas on them.{tail}"
    ws.cell(row=facts + 3, column=st, value=note).font = style.GREY
    hours = float(longest.t_h[-1])
    method = f" ({wi.method})" if wi.method else ""
    ch = _base_chart(
        f"{dam.label} dam - inflow hydrographs, all return periods{method}", MAIN_CHART_CM, hours
    )
    ch.legend.position = "r"
    _plot_layout(ch, 0.085, 0.10, 0.64, 0.72)
    xs = Reference(ws, min_col=1, min_row=FIRST, max_row=last)
    for k, rp in enumerate(rps):
        y = Reference(ws, min_col=cols[(rp, "inflow")], min_row=FIRST, max_row=last)
        pmp = rp == PMP
        ch.series.append(
            _series(
                xs, y, f"{q}!${a(4)}${2 + k}", colours[rp], 19050 if pmp else 15875, "dash" if pmp else None
            )
        )
    _peak_labels(ch, ws, q, rows_cols, peaks, rps, colours, max(peaks.values()))
    chart_row = facts + 6
    ws.add_chart(ch, f"{a(0)}{chart_row}")
    if tile_charts:
        top = chart_row + math.ceil(cm_to_EMU(MAIN_CHART_CM[1]) / ROW_EMU) + 2
        step_rows = math.ceil(cm_to_EMU(TILE_CM[1] + TILE_GAP_CM) / ROW_EMU)
        for k, rp in enumerate(rps):
            title = f"{dam.label} - {rp_label(rp)}: inflow" + (" and outflow" if dam.routed else "")
            tile = _base_chart(title, TILE_CM, hours)
            tile.legend.position = "b"
            for quantity, colour, dash in (
                ("inflow", style.DAM_COLOURS[0], None),
                ("outflow", style.OUTFLOW_COLOUR, "dash"),
            ):
                if quantity in qs:
                    ci = cols[(rp, quantity)]
                    y = Reference(ws, min_col=ci, min_row=FIRST, max_row=last)
                    tile.series.append(_series(xs, y, f"{q}!${L(ci)}$1", colour, 19050, dash))
            dx = (k % TILES_ACROSS) * cm_to_EMU(TILE_CM[0] + TILE_GAP_CM)
            tile.anchor = _anchor(ws, st, top + (k // TILES_ACROSS) * step_rows, dx, TILE_CM)
            ws.add_chart(tile)
    ws.freeze_panes = "B2"
    ws.sheet_view.zoomScale = 85
    return st


def _target_sheet(wb: Workbook, wi: WorkbookInput) -> None:
    rp, rpl = wi.target, rp_label(wi.target)
    name = target_sheet_name(rp)
    ws, q = wb.create_sheet(name), f"'{name}'"
    dams = wi.dams
    n = max(len(d.series[rp].t_h) for d in dams)
    last = FIRST + n - 1
    longest = max((d.series[rp] for d in dams), key=lambda h: len(h.t_h))
    _write_time(ws, longest.t_h)
    col, ci = {}, 2
    for dam in dams:
        for quantity in dam.quantities(structures=False):  # each structure's flow stays on the dam's own sheet
            col[(dam.name, quantity)] = ci
            style.header(ws.cell(row=1, column=ci, value=f"{dam.label} {quantity} {rpl} ({UNITS[quantity]})"))
            ws.column_dimensions[L(ci)].width = 16
            _write_series(ws, ci, dam.series[rp].column(quantity), quantity)
            ci += 1
    ws.column_dimensions["A"].width = 10
    ws.row_dimensions[1].height = 42
    s2 = ci + 2
    a = lambda j: L(s2 + j)  # noqa: E731
    heads = [
        "Dam",
        "Catchment (km²)",
        f"Peak inflow {rpl} (m³/s)",
        "Time to peak (h)",
        f"Volume {rpl} (Mm³)",
        "Legend",
        "Label: peak",
    ]
    widths = [12, 12, 14, 12, 13, 36, 22]
    routed = [d for d in dams if d.routed]
    has_pool = any("pool" in d.quantities() for d in routed)
    if routed:
        heads += [f"Peak outflow {rpl} (m³/s)", "Attenuation (-)"] + (
            [f"Highest pool {rpl} (m)"] if has_pool else []
        )
        widths += [14, 12] + ([14] if has_pool else [])
    for j, (head, w) in enumerate(zip(heads, widths, strict=True)):
        style.header(ws.cell(row=1, column=s2 + j, value=head))
        ws.column_dimensions[L(s2 + j)].width = w
    rng_t = f"$A${FIRST}:$A${last}"
    rows_cols, peaks, colours = {}, {}, {}
    for k, dam in enumerate(dams):
        r = 2 + k
        rng = {qq: f"{L(c)}${FIRST}:{L(c)}${last}" for (nm, qq), c in col.items() if nm == dam.name}
        vals = [
            dam.label,
            dam.catchment_km2,
            f"=MAX({rng['inflow']})",
            f"=INDEX({rng_t},MATCH({a(2)}{r},{rng['inflow']},0))",
            f"=SUM({rng['inflow']})*{wi.dt_s}/1000000",
            f'={a(0)}{r}&": Qp "&TEXT({a(2)}{r},"#,##0")&" m³/s, V "&TEXT({a(4)}{r},"#,##0.00")&" Mm³"',
            f'={a(0)}{r}&"  "&TEXT({a(2)}{r},"#,##0")&" m³/s"',
        ]
        fmts = ["@", "0.00", "#,##0", "0.00", "0.000", "@", "@"]
        if dam.routed:
            vals += [f"=MAX({rng['outflow']})", f'=IF({a(2)}{r}>0,1-{a(7)}{r}/{a(2)}{r},"")']
            fmts += ["#,##0", "0.0%"]
            if "pool" in rng:
                vals.append(f"=MAX({rng['pool']})")
                fmts.append("0.00")
        for j, (v, fm) in enumerate(zip(vals, fmts, strict=True)):
            c = ws.cell(row=r, column=s2 + j, value=v)
            c.number_format, c.border = fm, style.BOX
            if j == 1:
                c.font = style.BLUE_IN
        rows_cols[dam.name] = (r, s2 + 3, s2 + 2, s2 + 6)
        peaks[dam.name] = float(max(dam.series[rp].inflow))
        colours[dam.name] = style.DAM_COLOURS[k % len(style.DAM_COLOURS)]
    who = f"{wi.project} dams" if wi.project else "Dams"
    method = f" ({wi.method})" if wi.method else ""
    ch = _base_chart(f"{who} - {name} inflow hydrographs{method}", MAIN_CHART_CM, float(longest.t_h[-1]))
    ch.legend.position = "r"
    _plot_layout(ch, 0.085, 0.10, 0.64, 0.72)
    xs = Reference(ws, min_col=1, min_row=FIRST, max_row=last)
    for k, dam in enumerate(dams):
        y = Reference(ws, min_col=col[(dam.name, "inflow")], min_row=FIRST, max_row=last)
        ch.series.append(_series(xs, y, f"{q}!${a(5)}${2 + k}", colours[dam.name], 19050))
    for dam in routed:
        c = col[(dam.name, "outflow")]
        y = Reference(ws, min_col=c, min_row=FIRST, max_row=last)
        ch.series.append(_series(xs, y, f"{q}!${L(c)}$1", colours[dam.name], 15875, "dash"))
    _peak_labels(ch, ws, q, rows_cols, peaks, [d.name for d in dams], colours, max(peaks.values()))
    ws.add_chart(ch, f"{a(0)}{max(10, len(dams) + 5)}")
    ws.freeze_panes = "B2"
    ws.sheet_view.zoomScale = 85


def _summary(
    wb, wi: WorkbookInput, dams: list[Dam], st: dict[str, int], name: str, stat: int, fmt: str, title: str
) -> None:
    """One row per dam, one column per return period, each cell a formula into the dam sheet's statistics block."""
    ws = wb.create_sheet(name)
    ws["A1"] = title
    ws["A1"].font = style.font(size=12, bold=True)
    style.header(ws.cell(row=3, column=1, value="Dam"))
    style.header(ws.cell(row=3, column=2, value="Catchment (km²)"))
    for j, rp in enumerate(wi.return_periods):
        style.header(ws.cell(row=3, column=3 + j, value=rp_label(rp)))
        ws.column_dimensions[L(3 + j)].width = 10
    ws.column_dimensions["A"].width = 12
    ws.column_dimensions["B"].width = 14
    facts = max(FACTS_ROW, STATS_FIRST_ROW + len(wi.return_periods) + 2)
    for i, dam in enumerate(dams):
        ws.cell(row=4 + i, column=1, value=dam.label).font = style.font(bold=True)
        if dam.catchment_km2 is not None:
            ws.cell(
                row=4 + i, column=2, value=f"='{dam.label}'!${L(st[dam.name] + 1)}${facts + 2}"
            ).number_format = "0.00"
        for j, _rp in enumerate(wi.return_periods):
            c = ws.cell(
                row=4 + i,
                column=3 + j,
                value=f"='{dam.label}'!${L(st[dam.name] + stat)}${STATS_FIRST_ROW + j}",
            )
            c.number_format, c.border = fmt, style.BOX


def _read_me(ws, wi: WorkbookInput) -> None:
    from wadi2d import __version__

    who = f"{wi.project} dams" if wi.project else "Dams"
    routed = [d.label for d in wi.dams if d.routed]
    lines = [
        f"{who} - hydrographs at {len(wi.dams)} dam sites",
        "",
        f"Source: {wi.source}",
        "Dams: "
        + "; ".join(
            f"{d.label} ({d.element_kind} {d.name})" if d.label != d.name else f"{d.label} ({d.element_kind})"
            for d in wi.dams
        )
        + ".",
        (
            f"Reservoirs routed: {', '.join(routed)}; their sheets carry outflow, and pool level and storage where the source wrote them."
            if routed
            else "No reservoir routes in these results, so every series is the unrouted inflow at the dam site."
        ),
        *wi.notes,
        f"Dam sheets: the series are data; the statistics block and all summary sheets are formulas. The {target_sheet_name(wi.target)} sheet puts the dams side by side.",
        f"Built on {date.today():%Y-%m-%d} by Wadi2D {__version__}; step {wi.dt_s} s.",
    ]
    for i, text in enumerate(lines):
        ws.cell(row=1 + i, column=1, value=text).font = style.font(size=12 if i == 0 else 10, bold=i == 0)
    ws.column_dimensions["A"].width = 160


def build(wi: WorkbookInput, tile_charts: bool = True) -> Workbook:
    """The workbook in memory."""
    wi.check()
    wb = Workbook()
    readme = wb.active
    readme.title = READ_ME
    _target_sheet(wb, wi)
    routed = [d for d in wi.dams if d.routed]
    specs = [
        (
            PEAK_INFLOW,
            1,
            "#,##0",
            "Peak inflow at the dam site (m³/s)" + (f" - {wi.method}" if wi.method else ""),
            wi.dams,
        ),
        (
            INFLOW_VOLUME,
            3,
            "0.000",
            f"Inflow volume (Mm³) - sum of the {wi.dt_s / 60:g}-minute ordinates x {wi.dt_s} s / 1e6",
            wi.dams,
        ),
        (TIME_TO_PEAK, 2, "0.00", "Time from the start of the storm to the peak inflow (h)", wi.dams),
    ]
    if routed:
        specs += [
            (
                PEAK_OUTFLOW,
                6,
                "#,##0",
                "Peak outflow at the dam (m³/s) - routed through the reservoir",
                routed,
            ),
            (ATTENUATION, 7, "0.0%", "Attenuation of the peak, 1 - peak outflow / peak inflow", routed),
        ]
        pooled = [d for d in routed if "pool" in d.quantities()]
        if pooled:
            specs.append((HIGHEST_POOL, 8, "0.00", "Highest pool level in the reservoir (m)", pooled))
    sheets_before = len(wb.worksheets)
    st = {dam.name: _dam_sheet(wb, wi, dam, tile_charts) for dam in wi.dams}
    for k, (name, stat, fmt, title, dams) in enumerate(specs):
        _summary(wb, wi, dams, st, name, stat, fmt, title)
        wb.move_sheet(name, offset=sheets_before + k - wb.sheetnames.index(name))
    _read_me(readme, wi)
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for c in row:
                if c.font is None or c.font.name != style.FONT:
                    c.font = Font(
                        name=style.FONT, size=c.font.size or 10, bold=c.font.bold, color=c.font.color
                    )
    wb.calculation.fullCalcOnLoad = True
    return wb


def write(wi: WorkbookInput, out: str | Path, tile_charts: bool = True) -> Path:
    """Build and save; returns the path."""
    path = Path(out)
    path.parent.mkdir(parents=True, exist_ok=True)
    build(wi, tile_charts).save(path)
    return path
