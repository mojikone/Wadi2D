# W83 given area reduction factor

**Live.** Branch `feature/arf-given-factor` off `feature/fast-products` (`9117f7b`), not merged, not pushed.

## What was asked

His words of 2026-11-15: for 2D the reduction is an option: the real ARF (the depth-area study), a fixed catchment area
from which the reduction is calculated, "or the user can directly say how much reduction to be applied. Let's say 0.7
means 30 % reduction." The first two existed (`W53`, `W65`); this adds the third.

## What was built

- **Job:** `storm.arf_factor`, a number above 0 and at most 1, default none. Every depth of a uniform, hypothetical
  (design) or gridded storm is multiplied by it, on the 2D cells and under the lumped subbasins alike, at every storm
  area, with no table. Refused in words beside `storm.arf` or `storm.storm_area_km2` ("not both"), and on a
  hyetograph, gauge or no-rain storm, which take no area reduction today either.
- **Engine:** `GivenFactor` in `wadi2d/storm/arf.py` answers where a table would; the three storms read their factor
  through one function, `factor_at`, so a table run is the same arithmetic as before. A depth-area study refuses the
  factor (`check_storm`, and the ARF-step rule): every run would be the same run.
- **Record of the run:** `config.resolved.json` carries `arf_factor`; the progress log has an `area_reduction` event
  with the factor, no storm area, and type `given`, and the warning "every depth is multiplied by 0.7000, the given
  area-reduction factor, over the whole event"; output tags `arf_table_type: given`, `arf_factor`.
- **Preview rain:** the engine's reply carries `arf_factor`; the dock's line reads "Depths after an area reduction of
  0.7000 (given), on the hydrology step of 5 min."
- **Dock:** Storm > Area reduction has four choices: None, At one storm area, A given factor, By the depth-area study.
  A given factor shows one number box (0 to 1, four decimals, starts at 1) and hides the area and the table; the job
  holds `arf_factor` alone. Outside 0 < f <= 1 the run is refused before it starts; the study section refuses it in words.
- **Old jobs:** a job without the factor hashes as before. Checked by hashing three jobs (uniform, design storm with a
  table, no rain) on a fixed DEM before and after the change: the same three hashes. The job hash drops the key when
  it is none, as it does for gauges.

## Tests

- `tests/engine/test_given_factor.py`, 8 tests: validation and refusals; uniform, design and gridded storms take f at
  any storm area, the gridded total equal to f times the unreduced total; runs of a uniform and a gridded storm book
  rain f times the plain run (rel 1e-6) and say so; the lumped network's outflow f times the whole (no losses,
  rel 1e-9) and equal to the uniform storm's with the same factor; Preview rain gives a lumped subbasin and the 2D area
  50 x 0.7 mm; the study refuses; a set factor changes the hash, a none factor does not.
- `tests/plugin/test_storm_rows.py`, 4 new tests: the job the dock writes for a design storm and a grid, refusals
  out of range, the preview line, the study's refusal.
- `tests/plugin/smoke_qgis.py` (real QGIS, offscreen): the choice shows only its box, a design storm and a grid write
  the factor alone, and Preview rain through the real engine gives 80 x 0.7 mm and says "0.7000 (given)".
- `tests/plugin/schema_sample.json`, the frozen contract, regenerated: 16 lines added, the new field only.
- Targeted engine tests (rain runs, preview, ARF study, forcing, storms, lumped network) 229 passed; `tests/plugin`
  whole 580 of 580 (the first run 579 of 580, the frozen sample, then regenerated), the real-QGIS smoke included.
  CPU only; the full suite not run.

## Not done

- A single hyetograph and rain gauges still take no area reduction, as before: they are rain as received. Say if a
  given factor should apply to them too; it is one line in the schema check.
- The HMS project's own storm ("As in the HMS project") keeps the reduction of its met file; the block is not shown
  for it, as before.
