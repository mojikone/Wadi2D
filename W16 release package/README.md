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

Found there, to fix in the next package:

- The `.bat` always exits 0, whatever the installer returned.
- `README.txt` stops at the tick box: it does not say the dock opens from the toolbar button or Plugins > Wadi2D, nor that QGIS must be closed during the install or restarted after it.
- Estimate shows nothing for 15 to 45 s on a cold start. The bar restarts from 0 for about a minute of pixel maps.
- CuPy's `CUDA_PATH` warning lands in `engine.err` on every run, though the GPU works.
- `constraints.txt` pins the whole build environment, tools that have nothing to do with the engine among them.
- The engine always goes on C:, 3.1 GB, unless the user gives `-EngineRoot`, which `README.txt` does not mention.

**PROJ, checked here.** That PC sets `PROJ_LIB` and `GDAL_DATA` for another program's GDAL, and a test script's `CRS.from_epsg` failed on them. The session reported the engine's command line fails the same way. Rechecked with a foreign PROJ folder: the lookup fails as reported, but a real engine run, fresh tables and pixel maps, finished with exit 0, and printed one PROJ error line. The dock is not exposed at all, because it strips those variables. So this is noise on that job, not a failure; whether the written rasters kept their CRS was not read.

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
