# W16 release package

**Status (2026-11-02): published as pre-release `v0.1.0` at `540bf10`, https://github.com/mojikone/Wadi2D/releases/tag/v0.1.0. Tested on this PC on `f326d6c`; the published zip differs from the tested one only in its build stamp and the README text inside the wheel. Passed on a second PC the same day (section below); a PC with no NVIDIA card is still untested.** The Windows package others install from: `Wadi2D-0.1.0-windows.zip`, 0.4 MB, from `python tools/build_release.py`. The zip stays out of git and lives on the GitHub release; sha256 `baf0be5025f7993bc37c814bba823cd4289ed22fe6f86140b24e1477e102cb32`. `gh` is not logged in on this PC, so the tag went by git and the release page through the browser.

## What is in it

| File | Job |
|---|---|
| `install_wadi2d.bat`, `install_wadi2d.ps1` | Double-click. Finds Python, makes the engine's own environment in `%LOCALAPPDATA%\Wadi2D`, installs, checks, copies the plugin into the default QGIS profile, records the engine |
| `wadi2d-0.1.0-py3-none-any.whl` | The engine, kernels included |
| `wadi2d_qgis-0.1.0.zip` | The plugin; also works alone through QGIS's Install from ZIP |
| `constraints.txt` | 179 pinned versions, those the tests ran on, so a new install computes what this one does |
| `README.txt`, `LICENSE.txt`, `LICENSES.md`, `BUILD.txt` | First steps, licences, the commit |

The builder takes committed files only, refuses a wheel that drops a package file, and refuses a plugin version that differs from the engine's. The version is set once, in `wadi2d/__init__.py`. The NVIDIA libraries are not in the package: pip fetches them from PyPI on the user's PC, 1.9 GB of wheels; the engine then takes 3.2 GB on disk with the GPU, 0.76 GB without.

## Results

From the unzipped package, in a folder with a space in its name, into a fresh environment that shares nothing with the repository's venv, and throwaway QGIS 3.44.8 profiles. The repository's venv reads the system Python, where `hecdss` and `whitebox` live, so this is the first run without them. Packages came from pip's cache, so no timing here stands for a first install.

| Check | Result |
|---|---|
| Plugin as the installer copied it, QGIS's own loader, GPU engine (`gpu`) | 16 of 16 |
| Block 2 hybrid, 40 m, against the five peaks in `W15` | **all five equal, worst 0.00 m3/s** |
| HMS read, pixel maps, Make map, mesh preview and mesh run on the installed engine | pass |
| Plugin through QGIS's Install from ZIP, engine found by the shared record (`zip`) | 8 of 8 |
| CPU engine through the dock, small area (`cpu`) | 10 of 10; first time the CPU path has run through the plugin |
| The `.bat` itself; a second install over the first | pass |
| Neither `py` nor `python` on the PATH | finds the Python inside QGIS |
| No Python at all; the installer alone without the other files | stops, says what to do, nothing half-made |
| A developer's junction where the plugin goes | only the link goes, its target is kept |

## Found on the way

- **Windows' 260-character limit.** CuPy's deepest file sits 141 characters below the engine root, so a root over about 114 characters failed part way through pip with an obscure error. The installer now refuses such a folder first and names a short one. The default path is 37 characters here; a very long Windows user name is the only way to reach the limit.
- **A plugin added by Install from ZIP has no engine file beside it.** It now also reads `%LOCALAPPDATA%\Wadi2D\engine.txt`. Order: a saved Engine setting, the file beside the plugin, the shared record, Python on the PATH.
- **The Python inside QGIS works** as the base of the engine's environment, HTTPS included, so most engineers need nothing else. The price: uninstall that QGIS and the engine stops until the installer is run again, which rebuilds it.
- **WhiteboxTools downloads its own program** from `whiteboxgeo.com` when first imported. The installer does that at install time and warns if it fails; only the Mesh section needs it.

## Second PC, 2026-11-02

His laptop, driven by a separate Claude session from the published zip, reported by that session; only the PROJ point below was rechecked here. Windows 11 Home, i7-12700H, 31.7 GB, RTX 3070 Ti Laptop 8 GB, driver 596.08, QGIS 3.40.14 LTR, Python 3.14 on the PATH and 3.12 through `py`.

| Step | Result |
|---|---|
| Download, SHA-256 | pass |
| `install_wadi2d.bat`, a real download | pass, 7 min 25 s; passed over 3.14 for 3.12, chose the GPU, no warning; 3.09 GB |
| Plugin in the real default profile, engine found with nothing set | pass, about 8 s |
| Synthetic valley through the dock, 20 m, 8,100 cells, 1 h of rain | pass on the GPU; mass -2.6e-08; about 67 s, of which the solver 0.45 s |
| Depth and hazard maps, Make map | pass; PDF of 3 A3 pages in 1.3 s |

Found there, fixed in 0.1.1 where the line says so:

- The `.bat` always exits 0, whatever the installer returned. Fixed.
- `README.txt` stops at the tick box: it does not say the dock opens from the toolbar button or Plugins > Wadi2D, nor that QGIS must be closed during the install or restarted after it. Fixed, in the file and in the installer's last lines.
- Estimate shows nothing for 15 to 45 s on a cold start. Fixed: the status line says the first one can take a minute. The bar restarts from 0 for about a minute of pixel maps; left, the status line already says "Pixel maps".
- CuPy's `CUDA_PATH` warning lands in `engine.err` on every run, though the GPU works. Fixed, at the engine's start.
- `constraints.txt` pins the whole build environment, tools that have nothing to do with the engine among them. Fixed: 36 pins, not 179.
- The engine always goes on C:, 3.1 GB, unless the user gives `-EngineRoot`, which `README.txt` does not mention. Fixed; the shared record now stays in `%LOCALAPPDATA%\Wadi2D` wherever the engine goes, or Install from ZIP would miss it.

**PROJ, checked here.** That PC sets `PROJ_LIB` and `GDAL_DATA` for another program's GDAL, and a test script's `CRS.from_epsg` failed on them. The session reported the engine's command line fails the same way. Rechecked with a foreign PROJ folder: the lookup fails as reported, but a real engine run, fresh tables and pixel maps, finished with exit 0, and printed one PROJ error line. The dock is not exposed at all, because it strips those variables. So this is noise on that job, not a failure; whether the written rasters kept their CRS was not read. In 0.1.1 the engine's command line drops those variables at its start, as the dock does. The engine's Python used directly in a script of one's own is still exposed.

## 0.1.1

Built and checked here from `edf3c39`, the same way as 0.1.0: 35 of 35 through three QGIS profiles (`log_gpu.txt`, `log_zip.txt`, `log_cpu.txt` are this run's), the five Block 2 peaks equal to the record, `engine.err` empty, a failing install now returns 1 through the `.bat`, 1,124 tests. Published as pre-release `v0.1.1` on his word, https://github.com/mojikone/Wadi2D/releases/tag/v0.1.1; only documents changed between `edf3c39` and the tagged commit. Not rerun on the laptop yet. Solver and job format did not change.

## Not tested

- A PC with no NVIDIA card. The CPU engine has run through the dock only on this PC. Also unproven: a Windows with no Visual C++ runtime and no earlier Python, a proxy, and a locked-down office PC. [Likely] the runtime is the first thing to fail on a bare machine, if anything does.
- QGIS other than 3.44.8 and 3.40.14, Python 3.13 and any AMD or Intel GPU machine. QGIS 4 / Qt6 is refused by the plugin's metadata.
- A signed installer: Windows SmartScreen may warn about the `.bat`.

## Rerun

```
python tools/build_release.py
```

Unzip the result, then, with `<hms>` a copy of Block 2's HMS folder:

```
powershell -File "W16 release package\run_test.ps1" <unzipped release> <throwaway folder> <hms>
powershell -File "W16 release package\run_edges.ps1" <unzipped release> <throwaway folder>
```

Both install under `%LOCALAPPDATA%\W2D test`, which can be deleted afterwards.

## 0.2.0

Built from `b511cb3` (`python tools/build_release.py`, `Wadi2D-0.2.0-windows.zip`, 0.9 MB) after the full suite passed, 2,263 of 2,263 (9 skipped). Installed and driven through three throwaway QGIS 3.44.8 profiles: GPU 16 of 17, Install from ZIP 8 of 8, CPU 10 of 10, the junction check passes. **The one failure is the record, not the package:** the five Block 2 hybrid dam peaks differed from the 0.1.x record by up to 385.8 m3/s, and the same job run on the repository's own engine gives all 16 line peaks equal to the installed engine's to the digit. The record predates W41 (lumped hydrographs enter at the wadi outlet, so dam lines now count them), W34 (reservoirs start empty) and W49 (local hydraulic radius); `dock_release.py` now holds the 0.2.0 values: Bidah 03 622.4, Faydh 01 1,122.8, R2A 1,812.2, R5A 1,262.6, Z4C 2,103.3 m3/s at 40 m. Release notes: `release_notes_0.2.0.md`. Not tested on another PC.

## 0.3.0

Built from `0d1029a` (`Wadi2D-0.3.0-windows.zip`, 1.0 MB). Full suite before the bump 2,469 passed and 1 failed: the ARF study test found W78's edge check caching per run; fixed in `a0353f3` (runs read the study's cache), 92 depth-area tests pass after it. Installed and driven through three throwaway QGIS 3.44.8 profiles: GPU 17 of 17 (the five Block 2 hybrid dam peaks equal to 0.2.0's record), Install from ZIP 8 of 8, CPU 10 of 10, the junction check passes; the installed engine reads 0.3.0. Published as pre-release `v0.3.0` on his word. Release notes: `release_notes_0.3.0.md`. Not tested on another PC; the office PC is next when he is back.

### 0.3.0 on the office PC, 2026-11-14

Driven by that PC's own Claude session from the published zip (its report; nothing rechecked here). No usable NVIDIA card (GT 730, driver 391.35), QGIS 3.36.2, Python 3.12.3. Zip 959,725 bytes, `BUILD.txt` `0d1029a`. `install_wadi2d.bat` exit 0 in 68 s, CPU engine chosen; the dock found the engine with nothing set, version 0.3.0. A synthetic V valley through the real dock at 20 m (10,150 cells, 1 h of rain): finished in 16.7 s, mass error -1.5e-08, `engine.err` empty; one group `Wadi2D – valley` with Inputs and Results subgroups; Make map 2.4 s; the right-click hydrograph chart draws. **Found:** (1) the installer detects a GPU only by `nvidia-smi` on the PATH; on this PC it is not on the PATH, so the CPU was chosen by luck, and an old-driver card with `nvidia-smi` on the PATH would download the 2 GB CUDA stack and then only warn; (2) Preview rain on a job with no lumped subbasins shows no row for the 2D area and the sentence "No area reduction" after "Depths after the area reduction". Test files on that PC: `C:\Users\mojtaba\wadi2d_v030_test`.

## 0.3.1

The two findings of the office PC on 0.3.0: the installer's engine choice from the driver (`tools/release/gpu_check.ps1`, dot-sourced by the installer, in the package; driver 527.41 and compute capability 5.0 at least; 9 tests with fake cards, this PC reads "RTX 5080, driver 581.42: GPU engine"), and the Preview rain sentence. The office PC's second finding, an empty preview table, was its own inference from the label and is withdrawn by that session; the engine and the dock show the 2D row (a guard test added). Built from `e50603e`; plugin tests 576 passed; install test 35 of 35 in three throwaway profiles. Published as pre-release `v0.3.1` on his word.

### 0.3.1 on the office PC, 2026-11-14

Its own session, from the published zip (its report): installed over 0.3.0 in 5.7 s; the installer found `nvidia-smi` under `NVSMI` (not on the PATH) and said "GeForce GT 730, driver 391.35: older than 527.41, which the GPU engine needs. CPU engine; ..."; `Read-NvidiaCard` gave no compute capability (driver 391 cannot report it), so the driver alone decided, as designed; no CUDA package installed. Through the dock: 0.3.1, the valley run finished with mass error -1.5e-08 (balance identical to 0.3.0), Preview rain showed one 2D row of 30 mm with the new sentence, the group pattern, Make map and the right-click chart.

## 0.4.0rc1, release candidate 1 (test build), 2026-11-15

**Published as pre-release `v0.4.0-rc1`, https://github.com/mojikone/Wadi2D/releases/tag/v0.4.0-rc1, for the owner to try on his laptop. Not merged into `main` (still 0.3.1).** Branch `release/0.4.0-rc1`: `feature/fast-products` at `6408033`, then `feature/muskingum` (W89), `perf/sleeping-tiles` (W90) and `feature/hms-dock-and-lumped` (W88 items 2 to 6) merged one at a time; the tag is on the build commit `6c85ff3`. `Wadi2D-0.4.0rc1-windows.zip`, 1,076,926 bytes, sha256 `51e867b7e70ff0bba89bef66fa909355f1493b936a95fd2aba8afe9c545b1b5e` (the published asset downloaded back gives the same). Notes: `release_notes_0.4.0rc1.md`.

Conflicts, all resolved keeping both sides: the README iteration rows (union, W88's newer row kept), the Hydrology section (the Muskingum reach table under Reach routing, then the left-out tick and W88's HMS-way controls), `wadi2d/config/schema.py` (the reach routing choice keeps `muskingum`; both validators kept) and the frozen `tests/plugin/schema_sample.json`, checked equal to `json_schema()`.

Tested, CPU only (`CUDA_VISIBLE_DEVICES` empty), each file on its own: after W89 `tests/hydrology` 19 files and `tests/plugin` 37 files all passed (9 skipped); after W90 the three sleeping-tile files 16 of 16; after W88 `tests/engine/test_left_out.py` 18 of 18, `test_lumped_network.py` 7 of 8 once and 8 of 8 three times after (an exact float equality on the inflow total, off in the 16th digit once: the run-to-run sum order W88's README records for the rain total, not the merge), `test_basin_run.py` 10 of 10, `tests/plugin` all passed. The installer with `-CpuOnly -EngineRoot -RecordRoot -PluginsDir` into throwaway folders under `%LOCALAPPDATA%\W2D rc1` and the scratchpad: exit 0 in 37 s; `dock_release.py` in throwaway QGIS 3.44.8 profiles: cpu 10 of 10 (`log_cpu_0.4.0rc1.txt`), zip 8 of 8 (`log_zip_0.4.0rc1.txt`); the driver is `run_test_cpu_only.ps1`. Not tested: the GPU install and the gpu mode (the card was busy with the owner's Block 2 reruns), the full suite, another PC.

## 0.4.0, 2026-11-15

**Released as `v0.4.0`, the first normal (not pre-) release; `main` fast-forwarded to it.** On the owner's standing order of 2026-11-15 (merge, push and release). `feature/fast-products` took `release/0.4.0-rc1` (W88 items 2 to 6, W89, W90, the rc1 bump and notes; no conflicts) and then `perf/pre-solver` (W91), one at a time. W91's conflict was `_run` in `wadi2d/run.py`: the edge check now starts beside the table build and reports when the build ends, and W88's fallback to the lumped network alone (every cell left out) runs after that report; the README's W91 row joins the rc1 rows. After each merge its own test files, one at a time under the 10 GB cap: rc1's 15 files all passed; W91's 8 files (pit rebuild, survey boxes, fill pits, edge valleys, left out, lumped network, strip cache, `test_run`) all passed.

The known flaky check in `tests/engine/test_lumped_network.py` (two balance sums compared bit for bit, off in the 16th digit once on rc1) now compares to 1e-12, a commit of its own (`481c736`). Full suite on `481c736`, one process per test folder under the 10 GB cap, GPU visible: **2,787 passed, 10 skipped, 0 failed** (`logs_0.4.0/pytest_full.log`; a test rewrote `W1 .../validation/hms_replication.md`, restored).

Built from `31904d3`: `Wadi2D-0.4.0-windows.zip`, 1,084,115 bytes, sha256 `184b0d60942a3b3f3eb68938d9c60442dfe9ee917f0a1f81f3e3c6a06ef03070`. `run_test.ps1` with the rel020 HMS copy: GPU 17 of 17, Install from ZIP 8 of 8, CPU 10 of 10, the junction check passes (`logs_0.4.0/`; the script's copies over `log_gpu.txt`, `log_zip.txt` and `log_cpu.txt` were moved there and the 0.2.0 files restored). **The five hybrid dam peaks equal the 0.2.0 record to the digit, so `dock_release.py` is unchanged:** W88 to W91 leave a square-cell hybrid run as it was (sleeping tiles are exact by construction, the strip join fix touches only aligned cells, the pre-solver work gives identical tables). The installs took 4 to 6 s because they went over the earlier test installs under `%LOCALAPPDATA%\W2D test`; a fresh download was not repeated. Notes: `release_notes_0.4.0.md`. Not tested: another PC.
