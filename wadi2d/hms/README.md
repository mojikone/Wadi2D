# `wadi2d.hms`: HEC-HMS file readers

Reads a HEC-HMS 4.12 project so Wadi2D can use its model and compare against its results. Nothing here writes to an
HMS project. The byte-exact emitter exists for the round-trip test and a possible later export.

## Layers

- **`text.py`, lossless tokenizer.** Every line keeps its indent, key, separator, value and line ending; blocks are
  ordered multimaps; a sub-block exists only because its `End X:` partner was found. `dumps(parse(b)) == b` for any
  bytes, and that is the first test.
- **Typed models**, pydantic v2, one module per file type. `typed.py` holds the base: a model declares its HMS keys
  once, as field aliases, and `Cursor` fills them. `methods.py` holds the method registries (loss, transform, baseflow,
  route): a new method is one class and one line.
- **Other formats.** `sqlite.py` (read-only, immutable), `results.py` (XML), `dss.py` (wrapper over `hecdss`).

| Module | Reads | Entry point |
|---|---|---|
| `basin.py` | `.basin` | `load_basin` -> `Basin` (`subbasins`, `reaches`, `connectivity()`, `unknown_report()`) |
| `met.py` | `.met` | `load_met` -> `Met` (`storm`, `frequency_storm`) |
| `control.py` | `.control` | `load_control` -> `Control` (`start`, `end`, `n_steps`) |
| `nals.py` | `.nals` | `load_nals` -> `NalsFile` (`analyses`, `analysis(name).points`) |
| `pdata.py` | `.pdata` | `load_pdata` -> `PairedDataFile` (`tables`: metadata and DSS pathname) |
| `project.py` | `.hms` | `load_project` -> `Project` (`basins`, `mets`, `controls`, `path_of`) |
| `run.py` | `.run` | `load_run` -> `RunFile` |
| `results.py` | `results\DAA_*.results` | `load_results` -> `AnalysisResults` (`element(point, element)`) |
| `sqlite.py` | basin `.sqlite` | `subbasin_polygons`, `reach_lines`, `subbasin_statistics`, `reach_statistics` |
| `dss.py` | `.dss` | `open_dss` -> `DssFile` (`catalog`, `read_timeseries`, `read_paired`) |

```python
from wadi2d.hms import daa_fpart, load_basin, open_dss

basin = load_basin("Basin_1.basin")
print(basin.subbasins["S1"].loss.curve_number, basin.connectivity().outlets)
with open_dss("DA_100yr_B1.dss") as dss:
    flow = dss.read_timeseries("Z4C", "FLOW", daa_fpart("DA 100yr B1", "Z4C"))
```

## Rules these readers keep

- **Nothing is dropped.** A key a model does not know stays in the element's `unknown`, a sub-block in `blocks`, a
  whole block in `other_blocks`; a selector value with no registry entry becomes `UnknownMethod`. `unknown_report()`
  lists all of it. A value that does not parse as its declared number is reported the same way, and does not raise.
- **Repeated keys are lists.** `Analysis Point`, `Use Basin Model`, `Spillway` keep file order.
- **Values are in the file's units.** `unit_system` tells which; nothing converts here.
- **Times.** `24:00` is legal and rolls to the next day. `period_start_times()` moves a `PER-CUM` DSS stamp to the
  start of its period.
- **DSS is opened on a copy by default.** `hecdss` creates missing files and has no read-only mode, so `open_dss`
  refuses a missing path and, unless `readonly=False`, works on a temporary copy deleted on close.

## Grammar traps

- Non-ASCII bytes are not always UTF-8: `.terrain` writes the km2 superscript as one Latin-1 byte, so the tokenizer
  falls back to Latin-1 and records the encoding.
- `End Layer:` closes `Element Layer:`, `2D Connection Layer:` and `Map Layer:`; `Layer:13` inside a `Map Layer:` body
  sits at a deeper indent and is not an opener. `Evaporation Method:` is closed by `End Evaporation:`.
- `End Time:` and `End Date:` are ordinary keys. `End Variant: Variant-1` is a closer with a value.
- `Computation Point:` closes at column 0 with `End Computation Point: `, trailing space included.
- `Filename` in `.hms` is spelled `FileName` on `Control` entries.
- `reach2d` in the `.sqlite` also holds stream links named after subbasins, with repeated names: pass `names` to
  `reach_lines`.

## Tests

`tests/hms` runs in CI on the synthetic files in `tests/data/hms` (CRLF on purpose, guarded by a `.gitattributes`
there); the DSS tests build their file with `hecdss`. Tests marked `data` run on the real Block 2 project.
