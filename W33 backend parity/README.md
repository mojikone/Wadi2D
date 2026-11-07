# W33 backend parity

**Status (2026-11-06): done, findings only, no engine code changed on this branch. The CPU twin and the GPU parting on the Block 2 hybrid (W32 item 1) is not a backend fault: the hybrid magnifies any difference at all. A one-in-a-million nudge of the Courant number on the same GPU moves the lines as far as switching to the CPU, and so does compiling without `--use_fast_math`. Dam lines stay within 0.4 % raw and 0.17 % on the 15-minute peak in every variant; only rings round lumped inflows move several per cent. Found on the way: a second CUDA process crashed the moment another held a context, inside the NVIDIA driver. **Cleared by his reboot of 7 November**: the same tests, still over Remote Desktop, pass every time, so it was the driver's state after eight GPU faults without a reboot since 23 June, not the code and not Remote Desktop.**

The resume re-phase of W32 item 4, taken up beside this, is fixed on its own branch, `fix/resume-window`; see the last section.

## 1. Sensitivity, not a backend fault

`p01_hybrid_80m.py`: the Block 2 hybrid at 80 m, the HMS basin lumped under the HMS 100-yr storm, rain on the plain, the sixteen lines of the validation job, series every 60 s. Four runs, each in its own process, set against the GPU as it ships (`compare_p01.py`, `compare_p01.json`):

| Run | What differs from `gpu` | Steps |
|---|---|---|
| `gpu` | nothing | 110,227 |
| `gpu_exact` | kernels compiled without `--use_fast_math` | 110,219 |
| `gpu_nudge` | Courant number 0.45 x (1 − 1e-6), the same GPU | 110,231 |
| `cpu` | the Numba twin | 110,211 |

Peak against `gpu`, raw at the minute / 15-minute mean:

| Line | `gpu_exact` | `gpu_nudge` | `cpu` |
|---|---|---|---|
| Bidah 03 | +0.00 / +0.00 % | +0.00 / −0.01 % | +0.01 / +0.00 % |
| Faydh 01 | +0.00 / +0.00 % | −0.01 / +0.00 % | +0.00 / +0.00 % |
| R5A | +0.01 / +0.01 % | +0.01 / +0.01 % | +0.00 / +0.00 % |
| R2A | +0.09 / +0.05 % | **+0.38 / +0.17 %** | +0.16 / +0.03 % |
| Z4C | +0.00 / +0.00 % | +0.01 / −0.00 % | +0.01 / +0.01 % |
| Bidah 03 ring (peak about 20 m3/s) | **+17.3** / −1.97 % | −2.87 / −1.86 % | +10.1 / +0.53 % |
| R2A ring | +0.11 / −0.10 % | −2.13 / −0.44 % | −0.81 / −0.78 % |
| R5A ring | +0.88 / +0.11 % | +0.96 / +0.13 % | +0.65 / +0.07 % |
| S5 ring, volume | −1.54 % | −0.42 % | −1.16 % |

The lumped network's own series are identical in all four (the grid does not reach them). Mass error 4e-10 to 2e-8.

- [Certain] **The split is the run's own sensitivity.** A change of one part in a million in the step, on the same hardware and the same compiled code, parts the lines as far as the CPU does; the R2A dam line moves more under the nudge (+0.38 %) than under the CPU (+0.16 %). Nothing in either backend needs correcting to get the GPU's digits from the CPU, because the GPU does not keep its own digits under a perturbation that small.
- [Certain] **Fast math is not the cause.** Exact maths moves the lines by the same order as the CPU, and the biggest single ring move of all (+17 %).
- [Likely] **Where the sensitivity sits:** the rings that move are the ones round lumped inflows, where W31 found the pond surge: 630 m3/s entering a gorge pocket with no momentum, sloshing at an 11 s period. A surge picks up the rounding of whatever runs it, and a raw peak on a line across it reads whichever crest the sample lands on. The dam lines, further down, carry it at a tenth of a per cent.
- **What it means for numbers of record:** read dam lines, and read lumped elements from `series/network_<name>.csv` (W31); a raw ring peak beside a lumped inflow is not a number to quote from either backend. Matching backends to the digit is not a goal worth code: it would not survive a change to the Courant number either.
- **W32's Faydh 01 −2.5 %, reproduced and explained (2026-11-07, after the reboot).** W20's storm scenario was run again through the real dock (41 of 41) and its Block 2 job kept as `dock_hms_job.json`; `p02_dock_job.py` runs it at 80 m as W32 did. The GPU and the CPU give W32's numbers to the digit: 101,432 and 101,421 steps, Faydh 01 506.6 and 493.7 m3/s. The nudged GPU gives 101,429 steps and 497.2 m3/s.

| Line, against `gpu` (raw / 15-min) | `gpu_nudge` | `cpu` |
|---|---|---|
| Faydh 01 | −1.86 / +0.05 % | **−2.54 / −0.06 %** |
| Bidah 03 | +0.07 / +0.06 % | +0.03 / −0.01 % |
| R5A | +0.10 / +0.09 % | +0.21 / −0.09 % |
| R2A | −0.21 / −0.14 % | −0.01 / −0.06 % |
| Z4C | +0.11 / +0.22 % | −0.06 / +0.04 % |
| Bidah 03 ring (about 55 m3/s) | −1.47 / +9.30 % | −23.2 / −12.8 % |
| S6 ring | −1.59 / −0.61 % | +0.20 / −5.71 % |

  [Certain] Faydh 01's raw peak moves 1.9 % under a one-in-a-million change on the same GPU, and 2.5 % on the CPU; its 15-minute peak moves 0.05 % and 0.06 %. The raw minute value on that line catches a surge crest, the 15-minute peak does not. The small rings move by double figures under either. Same verdict as above, on the job that raised the question.

## 2. A second CUDA process crashes on this PC (driver, not Wadi2D)

How it was found: two of the four runs above segfaulted at start-up when the resume tests were also using the GPU, and the dock's run died at the same point with nothing in its error file.

| Test | Result |
|---|---|
| The dock's steady job, 14 runs one at a time, warm or cold grid cache, cold kernel cache | 14 of 14 run |
| Two engines started together (`run`, same job) | one of the two crashes, 5 pairs of 5 (exit 0xC0000005, access violation in CuPy's `_get_arch`) |
| Bare CuPy, two processes racing: `import cupy` / NVRTC version / device capability | 0 / 0 / 6 crashed of 16 |
| The same race with the first device query behind a shared lock file | 0 crashed of 36 |
| **One process holds a context (an array) and sleeps; another starts CUDA** | **the newcomer crashes, 3 of 3; once the holder exits, it starts** |
| The same, the newcomer using the CUDA driver API directly (`nvcuda.dll`, no CuPy) | `cuInit`, `cuDeviceGet`, `cuDeviceGetAttribute` succeed; `cuDevicePrimaryCtxRetain` reads address 0x8 and dies |

- [Certain] On this PC today a process cannot create a CUDA context while another process holds one: the fault is inside the NVIDIA driver, below CuPy and below Wadi2D.
- [Certain] Nothing under the engine changed: driver 32.0.15.8142 (581.42) dated 21 September 2025, CuPy 14.2.0 with its CUDA 12.9 wheels installed 29 October; only Store apps were updated since.
- [Certain] The system log holds eight `nvlddmkm` event 153 entries (GPU error, recovered) and two event 13 entries (graphics engine exception) on 1 and 2 November, during the heaviest GPU work of the project; the last boot was 23 June 2026.
- **Answered 2026-11-07, after his reboot at 00:05, still over Remote Desktop:** a second process beside a context holder starts 3 of 3; racing pairs 16 of 16; two engines started together 3 pairs of 3. [Certain] the cause was the driver's state, and a reboot clears it. If it comes back, the system log's `nvlddmkm` event 153 entries are the sign, and a reboot the cure.
- What was thought before the reboot, kept as the record: one of two things changed since GPU processes last ran side by side cleanly: the driver, after those eight recoveries without a reboot; or the Remote Desktop session this PC is used through (`rdp-tcp#0`), which was disconnected and reconnected at 07:45 on 6 November. A lone process still starts every time. A reboot, or one test at the console instead of over Remote Desktop, tells them apart; both are his to do.
- What it costs until then: any two GPU processes at once, one dies silently. That includes a dock run started while another engine process uses the GPU, the test suite's GPU tests that start an engine child while the test process holds a context, and parallel runs of a study.
- `candidate start lock/` holds a lock file around the first device query that cures the racing-start case (0 of 36 against 6 of 16) but not the case of starting beside a running process. It is not in the engine: after a reboot, the racing test decides whether it is needed at all.
- The suite shows it: `test_the_dock_runs_the_real_engine_to_done_on_qgis_python` fails on `main` and on `fix/resume-window` alike, its dry-run engine ending with -1073741819 (0xC0000005) while the dock's own estimate query is on the GPU; it passed in the full suite on 2 November. Every other test passes on both.
- Worth doing whatever the cause: the plugin should say "the GPU driver crashed at start-up" when the engine exits with 0xC0000005, instead of an empty result. Not built; it is a plugin change.

## 3. The resume re-phase (W32 item 4), fixed on `fix/resume-window`

W32 thought the series clock was reset at a resume. It is not: the checkpoint has always saved and restored `next_series` and `next_map`. The cause is that a stop saved the checkpoint in the middle of a source window, and the resumed loop built its windows from the stop time (`t_next = t + source_every_s`), so forcing windows, step landings and sample times all shifted for the rest of the run. Periodic checkpoints already fall on window ends.

The fix: a stop takes effect at the end of the window it falls in. `tests/engine/test_resume_exact.py` stops a run at a random moment and resumes it: the series files are byte-identical to the unbroken run's, with the same steps, outflow and storage, on the CPU and the GPU. Booked rain and inflow agree to 1e-12, not to the digit, because the books credit a window's rain in pieces at wall-clock progress ticks: two unbroken runs part there too. The cost: a stop waits up to one source window of simulated time (60 s by default, a fraction of a second of wall time here). Commit `f2a66cf`.

## Files

`p01_hybrid_80m.py` (the four runs, one per call), `compare_p01.py` (`--file results_p02.json` for the dock job), `results_p01.json`, `compare_p01.json`, `log_p01_*.txt`; `p02_dock_job.py`, `dock_hms_job.json` (the dock's Block 2 job, 40 m, run at 80 m), `results_p02.json`, `compare_p02.json`, `log_p02_*.txt`; `candidate start lock/`. The run folders under `runs/` are not kept.

## Rerun

```
.venv\Scripts\python "W33 backend parity\p01_hybrid_80m.py" gpu
.venv\Scripts\python "W33 backend parity\p01_hybrid_80m.py" gpu_nudge
.venv\Scripts\python "W33 backend parity\compare_p01.py"
```

Variants may run side by side again since the reboot; give each its own grid cache folder, or two runs building one cache collide on the file lock.
