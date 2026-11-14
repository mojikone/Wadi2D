"""W60 check, reservoir side: the Basin 3 workbook's inflow, outflow, pool and storage columns against Block 2's W14 tables.

Usage: python check_b3.py B3_WORKBOOK.xlsx W14_QPEAK_VOLUME.csv W14_RESERVOIRS.csv

W14 read HMS's .results statistics (peaks to 0.1 m3/s, volumes, levels and storage to 0.01); the workbook reads the DSS
series. The check takes the maximum of each written column and the volume as sum x step, per dam and return period.
Formulas are not evaluated here; the data cells they point at are.
"""

from __future__ import annotations

import csv
import sys

from openpyxl import load_workbook

STEP_S = 300


def _rows(path: str) -> list[dict[str, str]]:
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _column(wb, dam: str, quantity: str, rp: str) -> list[float]:
    ws = wb[dam.replace(" Reservoir", "").replace("R5A", "R5")]
    heads = {ws.cell(row=1, column=c).value: c for c in range(1, ws.max_column + 1)}
    c = heads[f"{quantity}_{rp}"]
    return [ws.cell(row=i, column=c).value or 0.0 for i in range(2, ws.max_row + 1)]


def main(book: str, table: str, reservoirs: str) -> int:
    wb = load_workbook(book)
    worst = {"Q_in": 0.0, "Q_out": 0.0, "V_in_MCM": 0.0, "V_out_MCM": 0.0}
    rows = _rows(table)
    for r in rows:
        qin, qout = _column(wb, r["dam"], "Inflow", r["rp"]), _column(wb, r["dam"], "Outflow", r["rp"])
        got = {
            "Q_in": max(qin),
            "Q_out": max(qout),
            "V_in_MCM": sum(qin) * STEP_S / 1e6,
            "V_out_MCM": sum(qout) * STEP_S / 1e6,
        }
        for k, v in got.items():
            worst[k] = max(worst[k], abs(v - float(r[k])))
    print(
        f"{len(rows)} dam-period rows; largest |workbook - W14|:", {k: round(v, 4) for k, v in worst.items()}
    )
    top = {"max_level": 0.0, "max_storage_mcm": 0.0}
    rows = _rows(reservoirs)
    for r in rows:
        top["max_level"] = max(
            top["max_level"], abs(max(_column(wb, r["dam"], "Pool", r["rp"])) - float(r["max_level"]))
        )
        top["max_storage_mcm"] = max(
            top["max_storage_mcm"],
            abs(max(_column(wb, r["dam"], "Storage", r["rp"])) - float(r["max_storage_mcm"])),
        )
    print(f"{len(rows)} reservoir rows; largest |workbook - W14|:", {k: round(v, 4) for k, v in top.items()})
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
