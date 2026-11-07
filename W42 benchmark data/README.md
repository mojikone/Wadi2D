# W42 benchmark data

**Status (2026-11-07): two public validation datasets downloaded, on his permission of 2026-11-07 for exactly these two: the UK Environment Agency 2D benchmark data package with its reports (76 MB downloaded, 345 MB on disk after unzipping; Tests 1 to 7, no Tests 8A/8B, no expected-results files) and the Iber/VAMONOS weir flume dataset from Zenodo (all six files of record 5062775, 1.29 GB, every md5 matching the record; the 11 GB raw archive left zipped). Nothing in them has been run, opened in an application or imported; only the PDF documentation and the small CSV/TXT tables were read as text. The raw data sit under `downloads/`, which `.gitignore` keeps out of git; this README and the `.gitignore` are committed. No Wadi2D run has used them yet. They are for the cap's tests (EA Tests 1, 3 and 7, the Iber weirs) and the aligned-mesh race.**

Live: this folder. Nothing superseded.

Layout:

```
W42 benchmark data/
  README.md            this file
  .gitignore           downloads/
  downloads/
    ea_2d_benchmark/   EA data package, its 2010 and 2013 reports, the 2013 LIT 8570 bundle
    iber_weirs/        Zenodo 10.5281/zenodo.5062775, all six files
```

Handling rules kept: every archive was unzipped only inside its own folder; no script, macro or executable was run; no Python file was imported (there are none; the Iber set has three MATLAB `.m` files, left untouched); the `.xls`/`.xlsx` files were not opened.

---

## 1. Environment Agency 2D benchmark (Néelz and Pender)

### Source

- Data package and 2013 reports: GOV.UK FCRM research page, project SC120002, "2D benchmarking: evaluating the latest generation of the hydraulic models for FCRM", published 22 February 2021, completed 31 August 2013:
  https://www.gov.uk/flood-and-coastal-erosion-risk-management-research-reports/2d-benchmarking-evaluating-the-latest-generation-of-the-hydraulic-models-for-fcrm
  - `Benchmarking_Model_Data.zip`: https://assets.publishing.service.gov.uk/media/6033a9bbd3bf7f72182e99ca/Benchmarking_Model_Data.zip
  - Technical report: https://assets.publishing.service.gov.uk/media/6033a943d3bf7f721f4b0d49/_SC120002_Benchmarking_2D_hydraulic_models_Report.pdf
  - Summary: https://assets.publishing.service.gov.uk/media/6033a91ce90e076601e9f4e2/_SC120002_Benchmarking_2D_hydraulic_models_Summary.pdf
- 2010 report (SC080035/SR2, withdrawn by the 2013 report but still served) and the 2013 bundle: GOV.UK publication "Benchmarking the latest generation of 2D hydraulic flood modelling packages", published 14 August 2013 by the Environment Agency:
  https://www.gov.uk/government/publications/benchmarking-the-latest-generation-of-2d-hydraulic-flood-modelling-packages
  - `LIT_8570_a3d694.zip` (it holds the 2013 report and summary, not data): https://assets.publishing.service.gov.uk/media/5a7c5d4d40f0b62aff6c1276/LIT_8570_a3d694.zip
  - 2010 report, 169 pages: https://assets.publishing.service.gov.uk/media/5a75765c40f0b6360e4744dd/scho0510bsno-e-e.pdf
  - 2010 summary: https://assets.publishing.service.gov.uk/media/5a7c65bbe5274a7ee501ab0f/scho0510bsnp-e-e.pdf

Not downloaded, though on the same pages: the 2005 1D river benchmarking reports (Tests A to O, a different project) and the 2009 desktop review (SC080035 phase 1). Neither is documentation of this data package.

Project codes: SC080035 is the 2009 desktop review and the 2010 benchmark report (SC080035/SR2, also printed SC080035/R2). The 2013 report "Benchmarking the latest generation of 2D hydraulic modelling packages" is **SC120002** (ISBN 978-1-84911-306-9) and states that it supersedes the 2010 report.

### Licence and terms, as written by the source

- GOV.UK, both pages, footer: "All content is available under the Open Government Licence v3.0, except where otherwise stated".
- The data package carries no licence file or statement of its own, so the GOV.UK OGL v3.0 statement is the one that applies to it [Likely; nothing in the zip says otherwise].
- The reports do state otherwise. 2013 report, inside cover: "© Environment Agency – August 2013. All rights reserved. This document may be reproduced with prior permission of the Environment Agency." Dissemination status: "Publicly available". The 2010 report carries the same wording, dated June 2010.
- Test 7's DEM is described in its specification as Environment Agency LiDAR, 1 m, "no vegetation or buildings", lightly processed (tiles merged, small gaps filled).

### What the package holds

`Benchmarking_Model_Data.zip` holds the **2010 test datasets for Tests 1 to 7** (one inner zip per test, files dated 2009 to 2010) and the Test 5/6B cross-section workbooks of 2011. **It does not hold Tests 8A and 8B** (urban rainfall and sewer surcharge), and **it holds no expected-results or model-results files** for any test: the `*output*.csv` files are output-point coordinates. Model results exist only as plots in the reports. Each test folder carries its own specification PDF (`EA2DTestN - May2010.pdf`), the same text as Appendix A of the 2013 report.

Files (bytes). The inner zips are kept beside their extracted folders.

| File | Bytes |
|---|---:|
| `Benchmarking_Model_Data.zip` (downloaded) | 52,456,734 |
| `LIT_8570_a3d694.zip` (downloaded; 2013 report 8,771,052 + summary 95,151, not extracted) | 7,972,945 |
| `_SC120002_Benchmarking_2D_hydraulic_models_Report.pdf` (2013 report, 2021 reissue) | 8,824,927 |
| `_SC120002_Benchmarking_2D_hydraulic_models_Summary.pdf` | 97,508 |
| `scho0510bsno-e-e.pdf` (2010 report SC080035/SR2, 169 pp.) | 6,966,974 |
| `scho0510bsnp-e-e.pdf` (2010 summary) | 43,309 |
| **Extracted `Benchmarking_Model_Data/`:** | |
| `Test1_dataset_2010.zip` | 84,587 |
| `Test1 dataset 2010/EA2DTest1 - May2010.pdf` | 110,202 |
| `Test1 dataset 2010/Test1BC.csv` | 83 |
| `Test1 dataset 2010/Test1output.csv` | 34 |
| `Test1 dataset 2010/test1DEM.asc` | 193,693 |
| `Test2_dataset_2010.zip` | 3,339,300 |
| `Test2 dataset 2010/EA2DTest2 - May2010.pdf` | 237,310 |
| `Test2 dataset 2010/Test2ActiveArea_region.dbf/.shp/.shx` | 77 / 236 / 108 |
| `Test2 dataset 2010/Test2BC_polyline.dbf/.shp/.shx` | 77 / 188 / 108 |
| `Test2 dataset 2010/Test2_BC.csv` | 66 |
| `Test2 dataset 2010/Test2output.csv` | 213 |
| `Test2 dataset 2010/test2DEM.asc` | 9,965,074 |
| `Test3_dataset_2010.zip` | 91,265 |
| `Test3 dataset 2010/EA2DTest3 - May2010.pdf` | 132,439 |
| `Test3 dataset 2010/Test3BC.csv` | 67 |
| `Test3 dataset 2010/test3DEM.asc` | 98,630 |
| `Test4_dataset_2010.zip` | 59,757 |
| `Test4 dataset 2010/EA2DTest4 - May2010.pdf` | 78,670 |
| `Test4 dataset 2010/Test4BC.csv` | 60 |
| `Test4 dataset 2010/Test4output.csv` | 85 |
| `Test5_dataset_2010.zip` | 1,139,437 |
| `Test5 dataset 2010/EA2DTest5 - May2010.pdf` | 133,378 |
| `Test5 dataset 2010/Test5ActiveArea_region.dbf/.shp/.shx` | 650 / 1,356 / 108 |
| `Test5 dataset 2010/Test5BC.csv` | 71 |
| `Test5 dataset 2010/Test5BC_backup.txt` | 112 |
| `Test5 dataset 2010/Test5BC_polyline.dbf/.shp/.shx` | 650 / 188 / 108 |
| `Test5 dataset 2010/Test5DEM.asc` | 10,701,974 |
| `Test5 dataset 2010/Test5output.csv` | 133 |
| `Test6_dataset_2010.zip` | 92,981 |
| `Test6 dataset 2010/EA2DTest6 - May2010.pdf` | 99,138 |
| `Test6 dataset 2010/Test6ADEM.asc` | 2,430,578 |
| `Test6 dataset 2010/Test6Aoutput.csv` | 90 |
| `Test6 dataset 2010/Test6BDEM.asc` | 2,430,568 |
| `Test6 dataset 2010/Test6Boutput.csv` | 79 |
| `Test7_dataset_2010.zip` | 48,131,417 |
| `EA2DTest7 - May2010.pdf` | 191,094 |
| `Test7-1DLoc-Spacing.csv` | 1,270 |
| `Test7-1DXS.txt` | 123,677 |
| `Test7-A4104Bridge.JPG` | 54,244 |
| `Test7-A4104bridge.xls` | 13,824 |
| `Test7-Bank-bklines.csv` | 3,136 |
| `Test7-DSRatingCurve.csv` (an Excel 97-2003 workbook despite the extension) | 14,336 |
| `Test7-FP-OuterBoundaries_polyline.dbf/.shp/.shx` | 99 / 2,428 / 124 |
| `Test7-FP-bklines.csv` | 2,112 |
| `Test7-Output.csv` | 323 |
| `Test7-PoolBrookCulvert.JPG` | 108,177 |
| `Test7-PoolBrookCulvert.xls` | 13,824 |
| `Test7-USInflow.csv` | 231 |
| `Test7DEM.asc` (1 m, 3000 x 8000) | 186,428,029 |
| `Test7DEM_10m.asc` (10 m, 301 x 801) | 1,871,603 |
| `XS info Tests_5&6.zip` | 80,643 |
| `XS info Tests_5&6/GPJune2011/Test5CrossSection.xlsx` | 28,443 |
| `XS info Tests_5&6/GPJune2011/Test6BCrossSection1.xlsx` | 29,619 |
| `XS info Tests_5&6/GPJune2011/Test6BCrossSection2.xlsx` | 29,442 |

Total: downloaded 76,362,397 bytes (72.8 MiB); on disk with the extractions 344,914,420 bytes (329 MiB).

SHA-256 of the downloads: `Benchmarking_Model_Data.zip` 388c2789570e5975fe909033e34bedbe5d7bde5e6d7f9b7d7c1eaf04e58bc732; `LIT_8570_a3d694.zip` ae2c32acdd86e161657f3f3c2a9e8a803470e68db36dad85892cdcfeec1bea68; 2013 report e2c03b52f28c9f85cd11f6509b40d190bf16d18e8ff69c59c4b965e776f95dea; 2013 summary e4c3181c4d652b3c70a43f9fd7c13a2e9cf0ab5d9e92d3560b5973f4a6f20838; 2010 report 88ce6773b46e41ba8ceb358b619d8e87cc83e762112105238bb7ca08a9fd99ae; 2010 summary 141069e4d51f17b5e76538cf39816573ad652ee5254d79d8c6b79328368dc1ab.

Tests in the package (2013 numbering = 2010 numbering for 1 to 7): 1 flooding a disconnected water body; 2 filling of floodplain depressions; 3 momentum conservation over a small obstruction; 4 speed of flood propagation over an extended floodplain; 5 valley flooding; 6A dam break, laboratory scale, and 6B dam break with a building, field scale; 7 river and floodplain linking. Absent: 8A, 8B.

### Test 1: flooding a disconnected water body

- Domain: a perfect rectangle 700 m x 100 m (X 0 to 700, Y 0 to 100); a sloping bed with a depression behind a sill.
- DEM: `test1DEM.asc`, 2 m, 371 x 71 cells, lower-left corner (-20, -20), nodata -999.
- Boundary: water level along the whole left side (X = 0), `Test1BC.csv`, **time in minutes**: 9.7 m at 0 and 5 min, 10.35 m from 60 to 660 min, 9.7 m at 720 and 1200 min. All other sides closed. Initial level 9.7 m.
- Manning n 0.03; grid 10 m (700 cells); run to 20 h.
- Output points `Test1output.csv`: point 1 (400, 50), point 2 (600, 50); water level every 60 s.
- Expected outcome stated by the reports (2013 report section 4.2.1, printed p. 19): peak ~10.35 m and final ~10.25 m at both points, the final level being the sill elevation. This is the one test of the three with a stated physical answer.

### Test 3: momentum conservation over a small obstruction

- Domain: 300 m x 100 m (X 0 to 300, Y 0 to 100); bed falling at 1:200 with two depressions separated by an obstruction.
- DEM: `test3DEM.asc`, 2 m, 186 x 71 cells, lower-left corner (-50, -20), nodata -999.
- Boundary: inflow along the left end, `Test3BC.csv`, **time in seconds**: 0 at 0 and 5 s, 65.5 m3/s from 15 to 25 s, 0 from 35 s to 900 s. Dry bed. The specification insists the effective width be exactly 100 m (or the inflow scaled by the ratio).
- Manning n 0.01; grid 5 m (~1,200 cells); run to 15 min.
- Output points are in the specification only, no CSV: location 1 (150, 50), centre of the first depression, level and velocity; location 2 (250, 50), centre of the second, level; every 2 s.
- Expected result: no exact solution. A full-SWE model must show a rise at point 2. The 2013 report (section 4.4.3, printed p. 38) records the full-SWE consensus: point 1 rises from 9.75 m at t ~ 60 s to ~9.98/9.99 m at t ~ 120 s; after t ~ 150 s point 2 rises quickly by ~5 to ~6 cm.

### Test 7: river and floodplain linking (Upton-upon-Severn)

The test is 1D river linked to 2D floodplains, with flooding by bank and embankment overtopping, a culvert, an opening and a 40 m causeway opening. It is not a pure 2D levee case: the river is meant to be 1D cross-sections, with a "glass wall" where no floodplain is modelled. A fully 2D model is admissible (SOBEK ran it fully 2D at 10 m).

- Site: River Severn near Upton-upon-Severn; river modelled over ~20 km; three floodplains over ~7 km x 0.75 to 1.75 km. British National Grid.
- DEMs: `Test7DEM.asc`, 1 m LiDAR, 3000 x 8000, lower-left (384000, 237000), nodata -9999 (gaps only outside the 2D domain); `Test7DEM_10m.asc`, 10 m, 301 x 801, lower-left (383995, 236995), which the specification warns will not carry the right crest elevations.
- River: `Test7-1DXS.txt`, 42 cross-sections M013 to M054 (use only the first two columns, chainage and elevation), with locations and spacing in `Test7-1DLoc-Spacing.csv`. Manning n 0.028 in the river.
- Crest lines with Z: `Test7-Bank-bklines.csv` (3 river-bank breaklines, 111 vertices) and `Test7-FP-bklines.csv` (8 floodplain breaklines, embankments and raised roads, 68 vertices; number 7 is the A4104 causeway opening, number 2 holds the 10 m sluice opening). Floodplain outer boundaries: `Test7-FP-OuterBoundaries_polyline` (FP1, FP2, FP3), drawn roughly on the 16 m contour.
- Structures: Pool Brook culvert (circular, masonry; `Test7-PoolBrookCulvert.xls` and photo); A4104 low bridges as one 40 m opening (`Test7-A4104bridge.xls` and photo); a 10 m wide opening, invert 10 m, at X 384606, Y 242489, open throughout, linking FP1 to the river at M030. The bridge at the north end of Upton is ignored; flapped outfalls ignored; buildings ignored.
- Boundaries: upstream inflow at M013, `Test7-USInflow.csv`, **time in hours**: 200 m3/s to 1 h, rising to 1,000 m3/s from 8.44 to 10.18 h, back to 200 m3/s at 30.58 h, held to 72 h; linear interpolation. Downstream rating curve at M054, `Test7-DSRatingCurve.csv`, columns "Flow (m^3/s)" and "Water level (m)", **stored as an .xls binary under a .csv name**; it must be converted before use and was not opened here. Initial level 9.8 m in river, floodplains and culvert. All other boundaries closed.
- Floodplains: Manning n 0.04; grid 20 m (~16,700 cells); run to 72 h.
- Output: `Test7-Output.csv`, 18 floodplain points (1 to 6 in FP1, 7 to 9 in FP2, 10 to 18 in FP3), level and velocity every 60 s; river level and velocity at M015, M025, M035, M045; peak and 72 h grids of level, depth and speed over the floodplains.
- Expected results: none in the package. The reports compare models with one another; there is no pass mark. What the reports state as the physically expected levels is in the next section.

### Test 7 control levels: 12.13 m and ~12.5 m are both right, for different floodplains

The two earlier notes do not disagree about one control; each quotes a different one, and both are in the official reports.

| Where | Level | What controls it | 2013 report SC120002, section 4.8.5 | 2010 report SC080035/SR2, section 4.7.3 |
|---|---|---|---|---|
| FP1, point 1 (outside the embankment) | final level ~12.13 m | lowest point on the river-bank breakline | printed p. 95 (PDF p. 105): "is expected to be equal to ~12.13m" | printed p. 69 (PDF p. 76): "should theoretically be ~12.13m" |
| FP1, points 2 to 6 (behind the embankment) | peak ~13.20 ± 0.1 m, one near-level water body; embankment ~13.1 m north to ~12.8 m south | river level overtopping the embankment; drains out through the M030 opening | printed p. 95 | printed p. 69 gives model peaks 13.15 to 13.45 m; ISIS without the opening drained to ~12.62 m, the embankment low point |
| FP2, points 7 and 8 | final level ~12.5 m | lowest point on the embankment crest, "~12.50m" | printed pp. 95 to 96 | printed p. 71 (PDF p. 78) |
| FP2, point 9 | floods only if the river near M035 exceeds ~12.49 m; exceeded by ~0.08 to ~0.13 m | a low point on the embankment to the south | printed p. 96 (PDF p. 106) | printed p. 71 |
| FP3, points 12 to 17 | final level ~11.5 m, all models within ~0.05 m | low point on the river-bank crest | printed p. 96 | printed p. 74 (PDF p. 81) |
| River bank crest range | ~13 m at the top of FP1 (M024) to ~11.5 m at the bottom of FP3 (above M044) | | section 4.8.2, printed p. 84 | section 4.7.2, printed p. 65 |

So: **12.13 m is FP1 point 1's dewatered level; ~12.5 m is FP2's.** Neither is a pass criterion. The 2010 report adds that the 12.13 m low point is local, between two higher points ~70 m apart, and that models read up to ~12 cm high there; the 2013 report says all models predicted it reasonably well except ISIS 2D (0.5 m high).

A check on the data, not in the reports: no breakline vertex sits at 12.13 or 12.50 m. The lowest vertices of the three bank breaklines are 12.05 m (line 1, at 384718.9, 244536.5, about 190 m from point 1), 12.16 m and 11.37 m; those of the eight floodplain breaklines range from 11.89 to 13.20 m. So the reports' "~" figures are rounded readings, not values from the dataset, and a Wadi2D check should take each control from the breaklines and the DEM along the line that actually drains the point, not from the report's number. Which low point drains each depression was not established here.

---

## 2. Iber weir flume dataset (VAMONOS, University of A Coruña)

### Source

- Zenodo record "VAMONOS - Open-channel flow over weirs. Experimental data.", García-Alén, G., García-Fonte, O., Pena, L., Puertas, J., Cea, L. (Universidade da Coruña). DOI 10.5281/zenodo.5062775 (version 2 of concept DOI 10.5281/zenodo.3940170); record page https://zenodo.org/records/5062775; files from `https://zenodo.org/records/5062775/files/<name>?download=1`. The documents inside are dated 02/07/2021. Project CTM2017-85171-C2-2-R.
- The data behind García-Alén et al. 2021, "Modelling weirs in two-dimensional shallow water models", Water 13(16) 2152, doi 10.3390/w13162152. The paper itself was not downloaded (outside the permission); which of the nine weirs the paper uses was therefore not checked.

### Licence, as written by the source

Creative Commons Attribution 4.0 International (CC BY 4.0), licence id `cc-by-4.0` on the record. Use and redistribution allowed with attribution; cite the Zenodo DOI and the authors above.

### Files

| File | Bytes | Zenodo md5 | Local md5 matches |
|---|---:|---|---|
| `Readme.pdf` | 206,880 | 7dfacd7620dfa9e544391586d0f54b53 | yes |
| `Data_package_description.pdf` | 1,253,055 | 5998aacc21fc1c429cbed76e67f13a7f | yes |
| `Summary_tests.pdf` | 3,229,219 | 4febf4c7b4f7d49809bcbab1c5aef8da | yes |
| `Processed_data.zip` | 1,449,014 | cce4a4622846b6819633a3b85db7fc0f | yes |
| `Matlab_files.zip` | 6,273 | 6b281ee01d59fa5bb29695c996e49dc9 | yes |
| `Raw_data.zip` | 1,287,251,242 | 0e806c7603a9ad54f943c7865cad8e6a | yes |

Total downloaded: 1,293,395,683 bytes (1.20 GiB, 1.29 GB).

Extracted: `Processed_data/Processed_data/Weir<N>-<name>/` with `W<N>Test1_Result.txt` (free), `W<N>Test2_Result.txt` (submerged), each 6.3 to 6.7 kB, and `W<N>_Geometry.pdf` (175 to 204 kB), 37 entries, 1,777,438 bytes; `Matlab_files/Matlab_files/` with `TestReader.m` (14,028), `DrawWeir.m` (6,503), `Zcalibration.m` (2,122), not run. On disk with these two extractions: 1,295,195,774 bytes.

`Raw_data.zip` is **left zipped**: it expands to 11,015,404,905 bytes (11.0 GB) in 172 entries, one folder per weir and run (`Raw_data/Weir<N>-<name>/W<N>Test<1|2>-<Free|Submerged>/`), holding 36 National Instruments `.tdms` voltage logs (10.97 GB) with their `.tdms_index` files, 54 `.txt` files (flow logs, Z-calibration metadata), and 18 photographs. They are needed only to reprocess the measurements with the MATLAB scripts, which the authors say; the processed files are the calibration data.

### What it holds

A 15 m flume, 0.5 m x 0.5 m rectangular section, horizontal bed (0.0 %), outlet sluice gate; stainless-steel weirs; inflow close to 30 l/s in every run; the downstream gate set for a free and a submerged run per weir, so **9 weirs x 2 runs = 18 tests**. Water surface measured by a needle gauge on an automatic positioner over a grid 400 mm wide (X about 50 to 450 mm, 50 mm clear of the walls) by 1,155 mm long (Y), about 125 points per run (124 to 130), each point an average of 12 to 64 contacts downstream of the weir, designed for a relative depth error of 5 % or less. The authors advise model calibration from `Processed_data` only.

Each processed result file gives the average flow, the average level at the Y = 0 section, and per point X, Y, mean Z, min Z, max Z and variance, in mm.

| Weir | Geometry | Run 1, free: Q l/s, h down mm, h up mm | Run 2, submerged: Q l/s, h down mm, h up mm |
|---|---|---|---|
| 1 | Duckbill | 29.16, 110.70, 251.96 | 29.18, 168.44, 249.20 |
| 2 | Double rectangular | 29.21, 111.80, 262.14 | 28.41, 171.85, 260.62 |
| 3 | Rectangular | 29.07, 152.84, 293.14 | 29.00, 225.83, 297.16 |
| 4 | Rectangular with slope | 28.03, 146.96, 283.10 | 28.29, 229.01, 288.80 |
| 5 | **Diagonal 30** | 28.29, 130.80, 291.15 | 28.92, 219.80, 292.93 |
| 6 | **Diagonal 45** | 29.06, 128.93, 273.94 | 28.99, 213.08, 277.39 |
| 7 | **Diagonal 60** | 31.94, 118.40, 265.18 | 31.90, 175.35, 265.41 |
| 8 | **Diagonal 30 with slope** | 28.90, 134.88, 280.54 | 30.47, 210.22, 283.68 |
| 9 | **Diagonal 45 with slope** | 31.88, 111.43, 275.94 | 30.45, 220.06, 274.50 |

Source: Data_package_description.pdf Table 2 and Summary_tests.pdf; "h down" and "h up" are the mean depths of the last and first measured rows.

**Oblique weirs: 5, 6, 7 (thin plates) and 8, 9 (plates with a sloping ramp), ten runs.** From the geometry drawings, read as images [Likely]: the angle is measured from the flume cross-section, not from the flow axis. Weir 8's sheet dimensions the crest's run along the flume as 0.288 m, which is 0.5 tan 30°, and Weir 7 (60°) visibly spans most of the measured reach (0.5 tan 60° = 0.866 m). The plate height shown on weirs 5, 7 and 8 is 0.200 m. The "with slope" weirs add a ramp, with dimensions 0.143, 0.288, 0.166, 0.288 m along the flume on Weir 8. The geometry PDFs are drawings with no text dimensions beyond these, so exact crest coordinates must be taken from the sheets by eye or from the paper.
