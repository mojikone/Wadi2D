# W60 dam workbook

**Status (2026-11-14): built on `feature/dam-workbook` (off `feature/fast-products` at `c7c08e3`), not merged, nothing pushed.
The engine writes his approved dam workbook from finished runs or HMS DSS files. Rebuilt from the same DSS files as Block 2's W1
workbook, it matches W1 in all 560 formulas, all 375 chart references and every chart anchor. Every number matches once W1's own
double rounding is imitated. No dock button yet.**

## What was asked

His approval of 2026-11-14 (project `CLAUDE.md`, "Dam workbook, his approval"), and the design in `W58 HMS elements and dam
workbook/README.md` section 7. The layout is W1's `Block02_Dam_Inflow_Hydrographs.xlsx`, for any dams or picked elements:

- Read me first, then the target return period sheet (200-yr by default).
- Summary sheets of peak, volume and time to peak, written as Excel formulas.
- One sheet per dam with every return period, its statistics block and its main chart.
- With a reservoir, outflow, pool level and storage beside each inflow, plus summaries of peak outflow, attenuation and highest pool.
- Below the main chart, one inflow-outflow chart per return period, tiled.
- No Status column.

## What is built

- `wadi2d/workbook/`:
  - `model.py`: the data, one hydrograph per dam and return period.
  - `sources.py`: reads finished runs or HMS DSS files.
  - `layout.py`: the sheets, formulas and charts.
  - `style.py`: W1's chart look.
- The command:

  ```
  wadi2d workbook --out FILE.xlsx --element NAME[=SHEET] ... (--run RP=RUN_DIR ... | --dss RP=FILE.dss ...)
                  [--basin FILE.basin] [--area NAME=KM2] [--target 200yr] [--project ..] [--method ..] [--no-period-charts]
  ```

  Return periods are keyed `2yr` ... `10000yr` and `PMP`, sorted by years with the PMP last.
- **From a run**, an element is read from the first series of its name the run wrote:
  - `series/network_<name>.csv`: the element's inflow. A subbasin, whose inflow is zero, gives its outflow. The element counts
    as routed when its outflow differs from its inflow.
  - `design_<name>.csv`, otherwise: the design line's total.
  - `line_<name>.csv`, otherwise: the size of the line's discharge.

  Pool and storage columns are taken when the run writes them: a column named `pool*`, `stage*` or `elevation*`, and one named
  `storage*` with a `_m3`, `_1000m3` or `_mm3` suffix. **Today's engine writes neither**; the reservoir pool series are another
  worker's, on `feature/hms-structures`. Until then a routed run element gets inflow and outflow, and the Read me and the dam
  sheet's note say that no pool level or storage was written.
- **From HMS**, each element is read at its own analysis point, where the F part ends in `>name`. A reservoir gives FLOW-COMBINE
  (inflow), FLOW (outflow), ELEVATION (pool) and STORAGE (storage, converted from 1000 m3 to Mm3). Any other element gives FLOW.
  With `--basin`, the catchment is the sum of subbasin areas upstream, and reservoirs are recognised by their element type.
- **Layout rules beyond W1, decided here:**
  - A routed dam's sheet carries inflow, outflow, pool and storage per return period, each present only if the source has it.
  - Its statistics block adds peak outflow, attenuation `1 - Qout/Qin`, highest pool and highest storage. These sit after W1's
    columns P:U, so a sheet with no reservoir keeps W1's columns exactly.
  - The facts block is Dam, element, Catchment, note, in rows 17 to 20. W1's Status row is removed, so the catchment moves from
    Q20 to Q19.
  - The target sheet adds each routed dam's outflow, pool and storage columns, and peak outflow, attenuation and highest pool
    after the label column. Its chart draws outflows dashed in the dam's colour.
  - The inflow-outflow charts are drawn on every dam sheet: 15 x 7.5 cm, three across, starting two rows below the main chart.
    A dam with no reservoir gets inflow-only charts, one per return period, at its own scale. They are left out with
    `--no-period-charts`.
  - Excel recalculates on open (`fullCalcOnLoad`). openpyxl writes formulas without cached values.
- `openpyxl` (MIT) is a runtime dependency now, in `pyproject.toml` and the licence audit.

## The check, rule fixed before the run (W58 section 7)

Rebuild W1's workbook from the same HEC-HMS depth-area DSS files (`DA_<rp>_B1.dss`, dated 26 Oct, before W1's workbook) and
`Basin_1.basin`. Compare every cell after mapping past the dropped Status column:

- data exactly, at W1's rounding;
- formulas as text, every reference inside them mapped the same way;
- charts by count, anchor and every series reference.

The scripts:

- `rebuild_w1.py OUT_DIR` writes the rebuild through `wadi2d.workbook.make`, and a second copy with the series first rounded to
  4 decimals.
- `compare_w1.py W1.xlsx REBUILT.xlsx [report]` does the comparison.

The workbooks hold project data and stay out of git.

| | W1 | Matched | Not matched |
|---|---|---|---|
| Formula cells | 560 | **560** | 0 |
| Chart series references | 375 (6 charts) | **375**, all anchors | 0 |
| Data cells | 44,145 | 42,790 | **1,347 by 0.001**, 8 text |
| Status cells dropped | 34 | | |
| Cells only in the rebuild | | | 0 |
| Charts only in the rebuild | | | 65: the 13 inflow charts per period on each of the 5 dam sheets, his addition |

**Why the 1,347.** [Certain] W1's step 01 wrote the DSS series to a CSV at 4 decimals, and step 05 rounded that again to 3. The
engine rounds the DSS value once. With the 4-decimal rounding imitated (`w1_rebuild_round4.xlsx`), every data cell matches exactly
except the same 8 text cells. The rebuild's numbers are the correctly rounded ones; the difference is in W1.

**The 8 text cells are wording, by design:**

- Read me A1 and A3 to A8. W1's lines are project prose: "dam design team", "to be designed", "next step". The engine writes the
  source files, the dams with their model names, routing, layout and build date.
- Peak inflow!A1. W1's title adds "at the dam junction's own analysis point, no reservoir routing". The engine writes "Peak
  inflow at the dam site (m³/s) - depth-area analyses".

**Two compare artefacts, handled in the compare and not in the engine:**

- Excel drops the quotes around a sheet name that needs none when it saves; W1 was saved by Excel after its recalculation. So
  W1 holds `=Z4C!$Q$2` where the engine writes `='Z4C'!$Q$2`, the same formula. The compare reads both forms as one.
- The main chart keeps its place at P23, although the cells below the dropped Status row move up one.

**Reservoirs, against Block 2's W14** (Basin 3, `DA_<rp>_B3.dss`, the five `<dam> Reservoir` elements, 13 periods):
`check_b3.py` compares the workbook's data columns with W14's `.results` tables, which are rounded to 0.1 m3/s and 0.01.

| Quantity, 65 dam-period rows | Largest difference |
|---|---|
| Peak inflow and peak outflow | 0.05 m3/s |
| Inflow and outflow volume | 0.005 Mm3 |
| Highest pool and highest storage | 0.005 m, 0.005 Mm3 |

Every difference is inside W14's rounding.

**Excel itself** opened the Basin 3 workbook read-only, recalculated it and kept all 14 charts on a dam sheet. On Faydh 01 at
200-yr it read:

- peak 1,240.149 m3/s at 13.25 h;
- volume 15.231 Mm3, which equals the DSS storage maximum, since nothing spills;
- outflow 0, attenuation 100 %;
- pool 228.418 m;
- legend "200-yr: Qp 1,240 m³/s, V 15.23 Mm³".

Unit tests: `tests/workbook/test_workbook.py`, 7 tests. They cover the layout, the formulas, the absence of a Status column, the
chart tiling, the reservoir columns and summaries, the refusals, the run source (network, junction, subbasin, line) and the
command with its exit codes.

## Not done

- **A dock button.** It needs a dialog that takes one run per return period and the elements to pick, and his rule wants it
  tested through the real dock. That is not small, so it waits for his word.
- **Pool level and storage from a Wadi2D run.** The engine does not write them yet (`feature/hms-structures`). The reader takes
  them by column name; the names may need matching once that branch fixes them.
- **The depth-area study's folder as one input**, with one run per storm area rather than per return period. Not wired.
- **[Likely] A client scan.** If a workbook goes to a client, it gets scanned like a report (his rule 14): its Read me names the
  model's files.
