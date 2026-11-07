# W35 hand-back resume rerun

**Status (2026-11-07): done, testing only. W32's item 4 (a generated basin with a live hand-back, stopped inside the flood and resumed) rerun on `main` with the resume fix of W33: 17 of 17, every one of the 19 series files equal to the last digit, against 1 of 19 in W32.**

W32 found a resumed run re-phased its series by 30 s and re-tallied the hand-back period that held the stop (up to 0.0024 m3/s on the network series). W33 traced both to one cause, a stop that saved its checkpoint in the middle of a source window, and made a stop land at the window's end. This reruns W32's own case on that fix.

| | W32, before | Here |
|---|---|---|
| Series files equal to the last digit | 1 of 19 | **19 of 19** |
| Hand-back volume, straight against resumed | 3,251,468.13 against 3,251,467.84 m3 | 3,251,467.925 against 3,251,467.925 m3 |
| Network storage | within 1e-3 | 3,253,336.514 both |
| Stopped near | 12.09 h | 13.18 h (a stop now ends at its window) |
| Checks | 16 of 17 | 17 of 17 |

The basin was generated again first (W32's item 2 script, 24 of 24), since W32's scratch folder was gone.

The scripts are W32's, copied into `scripts/` so that their results land here and W32 stays as it was; nothing in them changed. `results/` holds the logs and the JSON.

## Rerun

```
.venv\Scripts\python "W35 hand-back resume rerun\scripts\item2_gridded.py" <scratch folder>
.venv\Scripts\python "W35 hand-back resume rerun\scripts\item4_resume.py" <scratch folder>
```
