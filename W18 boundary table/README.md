# W18 boundary table

**Status (2026-11-02): done, D8 of his work order.** One line layer holds all the boundaries. The dock lists each line in a table with its kind and value, editable, and no fields are needed in the layer. The `kind` and `value` field route stays.

## How it works

- Pick the layer: one row per line, named by a `name` field or by its number.
- **Kind** and the value box above the table set every row until that row is pinned. A row is pinned by a field of the layer or by being edited, its kind and its value apart: a layer with a `value` field and no `kind` field keeps following Kind, as it did before.
- Change a row's kind and its value starts from that kind's default in the schema, not from a number that meant something else. `free` has no value.
- Rows are kept by feature id, so adding or deleting a line keeps what was set on the others.
- Click a row to flash its line on the map.

The job format did not change; the engine sees what it always saw.

One small correction to the old behaviour: a layer with a `kind` field and no `value` field used to send the dock's value to every line, so a `stage` line could be given an energy slope as its level. It now starts from the default of its own kind.

## Results

`dock_boundary_table.py` through the real dock on Block 2 ground around Bidah, 34 of 34 (`log_dock_boundary_table.txt`):

- A layer with no fields fills the table; Kind and Value set all rows.
- Three lines as stage 2.5, normal 0.02 and free reach `job.json` and the engine's resolved configuration; the run closes its mass.
- A layer with `kind` and `value` fields fills the table, the fields outrank Kind, and an edit outranks the field.
- A line added to the layer appears, the edits on the others survive, and a layer no longer chosen is let go.

The section was also drawn and looked at. 13 unit tests hold the row logic in `tests/plugin/test_boundary_rows.py`.

## Rerun

```
powershell -File tests\dock\run_check.ps1 "W18 boundary table\dock_boundary_table.py" <throwaway folder> -Copy "W18 boundary table"
```
