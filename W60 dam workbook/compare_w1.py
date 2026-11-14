"""W60 check: the workbook Wadi2D writes from Block 2's HMS depth-area DSS files against W1's own workbook, cell by cell.

Usage: python compare_w1.py W1_WORKBOOK.xlsx REBUILT.xlsx [report.txt]

The rule, fixed before the run (W58 section 7): every cell of W1's workbook is compared with the cell it maps to in
the rebuild, the Status column (summary sheets column B, 200-year sheet column J) and the Status row (dam sheets P19:Q19)
dropped and everything past them moved up by one; data cells exactly at W1's rounding; formula cells as text after
the same mapping is applied to every reference inside them; charts by count, anchor and every series reference.
Cells the rebuild holds that W1 does not (the inflow-outflow chart per period) are listed as additions.
"""

from __future__ import annotations

import re
import sys
from collections import Counter

from openpyxl import load_workbook
from openpyxl.utils import column_index_from_string as ci
from openpyxl.utils import get_column_letter as L

REF = re.compile(r"(?:'([^']+)'!|([A-Za-z_][\w\-]*)!)?(\$?)([A-Z]{1,3})(\$?)(\d+)(?![\w(])")
SUMMARY = ("Peak inflow", "Inflow volume", "Time to peak")
TARGET = "200-year"


def mapper(sheet: str, dam_sheets: set[str]):
    """(col, row) of W1 -> (col, row) of the rebuild, or None where the Status column or row was."""
    if sheet in SUMMARY:
        return lambda c, r: None if c == 2 else (c - 1 if c > 2 else c, r)
    if sheet == TARGET:
        return lambda c, r: None if c == 10 else (c - 1 if c > 10 else c, r)
    if sheet in dam_sheets:
        return lambda c, r: (
            None if (c in (16, 17) and r == 19) else (c, r - 1 if (c in (16, 17) and r > 19) else r)
        )
    return lambda c, r: (c, r)


def translate(formula: str, own: str, dam_sheets: set[str]) -> str:
    def one(m: re.Match) -> str:
        sheet = m.group(1) or m.group(2)
        to = mapper(sheet or own, dam_sheets)(ci(m.group(4)), int(m.group(6)))
        if to is None:
            return "#STATUS!"
        prefix = f"'{m.group(1)}'!" if m.group(1) else (f"{m.group(2)}!" if m.group(2) else "")
        return f"{prefix}{m.group(3)}{L(to[0])}{m.group(5)}{to[1]}"

    return REF.sub(one, formula)


QUOTED = re.compile(r"'([A-Za-z_][\w.]*)'!")


def unquote(formula):
    """Excel drops the quotes round a sheet name that needs none when it saves (W1 was saved by Excel): ='Z4C'!$Q$2 = =Z4C!$Q$2."""
    return QUOTED.sub(r"\1!", formula) if isinstance(formula, str) else formula


def chart_refs(ch) -> list[str]:
    out = []
    for s in ch.series:
        for part in (
            s.tx.strRef if s.tx else None,
            s.xVal.numRef if s.xVal else None,
            s.yVal.numRef if s.yVal else None,
        ):
            out.append(part.f if part is not None else None)
    return out


def main(w1_path: str, new_path: str, report: str | None = None) -> int:
    w1, new = load_workbook(w1_path), load_workbook(new_path)
    dam_sheets = {ws.title for ws in w1.worksheets if ws.title not in (*SUMMARY, TARGET, "Read me")}
    lines, tally = [], Counter()
    lines.append(f"sheets W1:      {w1.sheetnames}")
    lines.append(f"sheets rebuild: {new.sheetnames}")
    for ws in w1.worksheets:
        if ws.title not in new.sheetnames:
            lines.append(f"MISSING SHEET {ws.title}")
            continue
        nw, f = new[ws.title], mapper(ws.title, dam_sheets)
        for row in ws.iter_rows():
            for c in row:
                if c.value is None:
                    continue
                to = f(c.column, c.row)
                if to is None:
                    tally["status cells dropped"] += 1
                    continue
                got = nw.cell(row=to[1], column=to[0])
                want = c.value
                kind = "formula" if isinstance(want, str) and want.startswith("=") else "data"
                if kind == "formula":
                    want = translate(want, ws.title, dam_sheets)
                tally[f"{kind} cells"] += 1
                if unquote(got.value) != unquote(want):
                    tally[f"{kind} mismatches"] += 1
                    if (
                        kind == "data"
                        and isinstance(want, float | int)
                        and isinstance(got.value, float | int)
                    ):
                        tally["data mismatches of 0.001 or less"] += abs(want - got.value) <= 0.0010001
                    lines.append(
                        f"{ws.title}!{c.coordinate} -> {got.coordinate}: W1 {want!r} | rebuild {got.value!r}"
                    )
                elif got.number_format != c.number_format:
                    tally["number format differences"] += 1
                    lines.append(
                        f"{ws.title}!{c.coordinate}: format W1 {c.number_format!r} | rebuild {got.number_format!r}"
                    )
        # cells the rebuild has that map from nothing in W1
        back = {f(c.column, c.row) for row in ws.iter_rows() for c in row if c.value is not None}
        for row in nw.iter_rows():
            for c in row:
                if c.value is not None and (c.column, c.row) not in back:
                    tally["cells only in the rebuild"] += 1
                    lines.append(f"{ws.title}!{c.coordinate}: only in the rebuild: {c.value!r}")
        w1c, nc = ws._charts, nw._charts
        tally["charts W1"] += len(w1c)
        tally["charts rebuild"] += len(nc)
        for k, ch in enumerate(w1c):
            mine = nc[k]
            a0 = (ch.anchor._from.col + 1, ch.anchor._from.row + 1)
            to = a0  # the chart keeps its place; the Status row shift is for cells only
            a1 = (mine.anchor._from.col + 1, mine.anchor._from.row + 1)
            if to != a1:
                lines.append(
                    f"{ws.title} chart {k}: anchor W1 {L(a0[0])}{a0[1]} -> {L(to[0])}{to[1]} | rebuild {L(a1[0])}{a1[1]}"
                )
                tally["chart anchor mismatches"] += 1
            want = [unquote(translate(r, ws.title, dam_sheets)) if r else r for r in chart_refs(ch)]
            got = [unquote(r) for r in chart_refs(mine)]
            tally["chart references"] += len(want)
            if want != got:
                bad = [(w, g) for w, g in zip(want, got, strict=False) if w != g]
                tally["chart reference mismatches"] += len(bad) + abs(len(want) - len(got))
                lines.append(
                    f"{ws.title} chart {k}: {len(want)} refs W1, {len(got)} rebuild; first differences {bad[:3]}"
                )
        if len(nc) > len(w1c):
            lines.append(
                f"{ws.title}: {len(nc) - len(w1c)} charts only in the rebuild (the inflow-outflow chart per period)"
            )
    head = [f"{k}: {v}" for k, v in sorted(tally.items())]
    text = "\n".join(["TALLY", *head, "", "DETAIL", *lines])
    print("\n".join(head))
    if report:
        with open(report, "w", encoding="utf-8") as out:
            out.write(text + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
