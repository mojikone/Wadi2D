# W28 final merge test

**Status (2026-11-02): done. Every dock scenario of the work order, rerun on the merged `main` at `5b4cc23`, passes: 497 of 497.**

The nine items of his side-chat decisions were built on nine branches at the same time and merged one at a time, each merge gated on the full test suite. A scenario that passed on its own branch could still break on the merged code, where every section sits in one dock, so each was run again here on the final code, in a throwaway QGIS 3.44.8 with a throwaway profile, the plugin and the engine from this checkout.

| Scenario | Item | Checks |
|---|---|---|
| `W17 cell grid layer/dock_cell_grid.py` | D2 | 21 of 21 |
| `W18 boundary table/dock_boundary_table.py` | D8 | 34 of 34 |
| `W19 time slider/dock_time_slider.py` | D1 | 31 of 31 |
| `W20 storm section/dock_storm.py` | D5 | 41 of 41 |
| `W21 result lines/dock_result_lines.py` | D9 | 73 of 73 |
| `W22 profile editor/dock_profile_editor.py` | D7 | 120 of 120 |
| `W23 mesh controls/dock_mesh_controls.py` | D3 | 67 of 67 |
| `W26 suggested breaklines/dock_suggest.py` | D4 | 32 of 32 |
| `W27 basin wiring/checks/dock_basin_bidah.py` | D6 | 52 of 52 |
| `W27 basin wiring/checks/dock_basin_block2.py` | D6 | 26 of 26 |

The logs are beside this file.

**What the merges caught, before this run.** One check of the profile editor failed on the merged code after passing alone: the Edit profile button came out 78 px wide against a hint of 80, because with more sections the dock's scroll area takes a scrollbar's width off every row and `QSizePolicy.Minimum` guards only the smaller minimum hint. The text was whole in the render; the button is now pinned at its hint (`1510de6`). Two merges conflicted and were resolved by keeping both sides: `wadi2d/engine/cli.py`, where D5 and D9 each added a command, and the plugin README's file table.

**Not tested here.** QGIS other than 3.44.8; the laptop with 3.40.14; a PC with no NVIDIA card; the full extent through any of the new sections; the CPU engine through the new sections. The suites of each W folder say what each item itself did not test.

## Rerun

```
powershell -File tests\dock\run_check.ps1 "<W folder>\<scenario>.py" <throwaway folder> -Copy "W28 final merge test"
```
