# Block 2 test data inventory for Wadi2D

Written 2026-10-29 from `D:\Mojtaba\Renardet\2224 WS11\Batinah\Block 2`, read-only: `cat`/`grep` for text, `rasterio` headers plus one 512 x 512 window, `pyogrio`/`geopandas` metadata, sqlite `mode=ro&immutable=1`, the DSS files through scratch copies deleted afterwards (`hecdss` 0.1 `HecDss(filename)` has no read-only mode). A final check found no Block 2 file touched by this session (HEC-HMS itself re-saved its project files at 07:46 today, before this began). Full per-element results and the HMS terrain statistics: `block2_hms_da100_elements.md` beside this file.

Block 2's `CLAUDE.md` on the data: his dams-only HMS 4.12 model `Hydrology\HEC_HMS_Block_02` (Basin 1, 18 subbasins, 599 km², 8 reaches, 14 junctions, five dam-site junctions, no reservoir, 13 frequency storms with the `ARF FM` table, 13 depth-area analyses computed 2026-10-26, PMP grid unit fixed from inches to mm that day); terrain 0.5 / 5 / 2 m rasters; shapefiles for dams, channels, culverts, land use, streams, global catchments; his files read-only; W1 is the dams hydrology package.

## 1. HEC-HMS model `Hydrology\HEC_HMS_Block_02`

`HEC_HMS_Block_02.hms`: `Version: 4.12`, `DSS File Name: HEC_HMS_Block_02.dss`, `Time Zone ID: America/Los_Angeles`; one basin `Basin 1` (`Basin_1.basin`), one control, 13 met models. `Basin_1.basin`: `Unit System: Metric`, `Coordinate System:` WKT `WGS_1984_UTM_Zone_40N` (`EPSG 32640`), `Terrain: GGC_2_MERGE_HDSM_5m` (`.terrain`: `Stream Threshold: 20 km²`), five `Break Point` entries. Elements: 18 `Subbasin:`, 8 `Reach:`, 14 `Junction:`; no `Sink:`, `Source:`, `Reservoir:`, `Diversion:` (those sqlite tables are empty). Every subbasin: `Discretization: None`, `Canopy: None`, `Surface: None`, `LossRate: SCS`, `Percent Impervious Area: 0.0`, `Transform: SCS`, `Unitgraph Type: STANDARD`, `Baseflow: None`; `Initial Abstraction:` is in mm, not a ratio.

| Subbasin | Area km² | Downstream | CN | Ia mm | Lag min |
|---|---|---|---|---|---|
| S1 | 59.078 | J1 | 90.7 | 5.22 | 112 |
| S2 | 44.392 | J1 | 90.9 | 5.09 | 102 |
| S3 | 87.597 | J2 | 90 | 5.64 | 157 |
| S4 | 20.018 | Z4C | 86.7 | 7.77 | 64.4 |
| S5 | 73.869 | J4 | 90.8 | 5.12 | 127 |
| S6 | 24.633 | J5 | 90.5 | 5.31 | 65.5 |
| S7 | 37.656 | J6 | 87.5 | 7.22 | 75.1 |
| S8 | 5.0816 | J6 | 86.8 | 7.7 | 55.9 |
| S9 | 30.781 | R2A | 88 | 6.95 | 101 |
| S10 | 3.8459 | R2A | 86.1 | 8.24 | 37.3 |
| S11 | 41.465 | J9 | 90.8 | 5.13 | 78.2 |
| S12 | 32.839 | Faydh 01 | 90.5 | 5.34 | 67.8 |
| S13 | 20.971 | Bidah 03 | 87.6 | 7.2 | 53.3 |
| S14 | 42.298 | J12 | 91.1 | 4.99 | 93.5 |
| S15 | 38.894 | J13 | 90.3 | 5.45 | 85.5 |
| S16 | 22.355 | R5A | 87 | 7.6 | 70 |
| S17 | 11.888 | R5A | 87.5 | 7.28 | 53 |
| S18 | 1.6696 | R5A | 86.4 | 7.98 | 31.5 |

Sum 599.33 km². [Certain, reproduced on S1 and S18] `Ia = 0.2 x 25.4 x (1000/CN - 10)`; `Lag = 0.6 x Kirpich Tc`, `Tc(min) = (1/52) L^0.77 S^-0.385` on the **10-85 flowpath** length and slope in `Basin_1.sqlite` `subbasin_statistics` (S1: 19,623 m, 0.01707 -> 111.7; S18: 3,181 m, 0.01206 -> 31.5); formulas in `Hydrology Data\txt\Kirpich NRCS lag time HEC HMS.md`. CN area-weighted from `SCS Grid` = `Hydrology Data\CN_Include_Hill_Area.tif` [Likely].

```
Subbasin: S1
     Last Modified Date: 26 October 2026
     Last Modified Time: 09:36:22
     Latitude Degrees:  24.512354479213208
     Longitude Degrees: 56.20888842451248
     Canvas X: 419855.2832157733
     Canvas Y: 2711182.7818185077
     Area: 59.078
     Downstream: J1

     Discretization: None
     File: Basin_1.sqlite

     Canopy: None
     Allow Simultaneous Precip Et: No
     Plant Uptake Method: None

     Surface: None

     LossRate: SCS
     Percent Impervious Area: 0.0
     Curve Number: 90.7
     Initial Abstraction: 5.22

     Transform: SCS
     Lag: 112
     Unitgraph Type: STANDARD

     Baseflow: None
End:
```

Reaches, all: `Route: Muskingum Cunge`, `Channel: Trapezoid`, `Mannings n: 0.100`, `Initial Variable: Combined Inflow`, `Space-Time Method: Automatic DX and DT`, `Index Parameter Type: Index Celerity`, `Index Celerity: 1.524`, `Number Subreaches: 1`, `Maximum Depth Iterations: 20`, `Maximum Route Step Iterations: 30`, `Channel Loss: None`; no 8-point section, no index flow. Length and slope equal `reach_statistics` in the sqlite (terrain-derived).

| Reach | Downstream | Length m | Energy Slope | Bottom Width m | Side Slope |
|---|---|---|---|---|---|
| R1 | J2 | 26008.98 | 0.01241 | 60 | 0.700 |
| R2 | Z4C | 8347.98 | 0.00931 | 100 | 1.500 |
| R3 | R2A | 14552.26 | 0.01162 | 60 | 1.500 |
| R4 | J6 | 9427.58 | 0.01485 | 100 | 2.000 |
| R5 | J7 | 659.62 | 0.00945 | 100 | 5.000 |
| R6 | Faydh 01 | 4259.46 | 0.01474 | 50 | 1.000 |
| R7 | J13 | 17006.85 | 0.01523 | 50 | 1.000 |
| R8 | R5A | 7765.33 | 0.011 | 70 | 3.000 |

```
Reach: R1
     Last Modified Date: 26 October 2026
     Last Modified Time: 09:34:34
     Canvas X: 434685.98973783385
     Canvas Y: 2707602.893463373
     From Canvas X: 424978.48973783385
     From Canvas Y: 2705532.893463373
     Downstream: J2

     Route: Muskingum Cunge
     Channel: Trapezoid
     Length: 26008.98
     Energy Slope: 0.01241
     Mannings n: 0.100
     Bottom Width: 60
     Side Slope: 0.700
     Initial Variable: Combined Inflow
     Space-Time Method: Automatic DX and DT
     Index Parameter Type: Index Celerity
     Index Celerity: 1.524
     Number Subreaches: 1
     Maximum Depth Iterations: 20
     Maximum Route Step Iterations: 30
     Channel Loss: None
End:
```

Junctions (`Downstream:`): J1->R1, J2->R2, J4->R3, J5->R4, J6->R5, J7->R2A, J9->R6, J12->R7, J13->R8; **Z4C, R2A, Faydh 01, Bidah 03, R5A carry no `Downstream:`** (terminal outlets, the dam sites). Connectivity, five separate trees (drainage areas from the results XML):

```
Z4C      211.085 km2 <- R2 <- J2 <- { R1 <- J1 <- {S1, S2} ; S3 } ; S4
R2A      175.867 km2 <- { R3 <- J4 <- S5 ; J7 <- R5 <- J6 <- { R4 <- J5 <- S6 ; S7 ; S8 } ; S9 ; S10 }
Faydh 01  74.304 km2 <- { R6 <- J9 <- S11 ; S12 }
Bidah 03  20.971 km2 <- S13
R5A      117.105 km2 <- { R8 <- J13 <- { R7 <- J12 <- S14 ; S15 } ; S16 ; S17 ; S18 }
```

`Control_1.control`: `Time Zone ID: Asia/Dubai`, `Start Date: 31 December 1999`, `Start Time: 24:00`, `End Date: 2 January 2000`, `End Time: 24:00`, `Time Interval: 5` (577 steps). The `.nals` analyses repeat the window with `Time Zone GMT Offset: -28800000`; DSS times run nominally 2000-01-01 00:00 to 2000-01-03 00:00.

Met models: 13 `FM_<rp>.met`; **no `DA_*.met`** (the depth-area analyses live in `HEC_HMS_Block_02.nals`). `FM_100yr.met`: `Precipitation Method: Hypothetical Storm`, `Evapotranspiration Method: No Evapotranspiration`, `Use Basin Model: Basin 1`; block `Precip Method Parameters: Hypothetical Storm`: `Precipitation Method: Point Depth`, `Storm Depth: 205.4`, `Storm Type: Specified Pattern`, `Storm Duration: 24`, `Pattern Name: FM 10-1000yr`, `Storm Area: 300`, `Depth-Area Reduction Method: User-Specified`, `Reduction Table Name: ARF FM`, `Uniform Depth: Yes`; then a `Subbasin:` block per subbasin with an empty `Depth:`. Frequency-storm keys (per-duration depths, intensity duration, intensity position) do not exist: this is the Hypothetical Storm method with a user pattern. `FM_PMP.met` differs only in `Precipitation Method: Precipitation-Frequency Grid`, `Precip-Freq Grid Name: PMP`, `Pattern Name: FM PMP`. 24 h point depths (mm): 2yr 27.6 (pattern `FM 2yr`), 5yr 55.3 (`FM 5yr`), 10yr 105.5, 25yr 137.5, 50yr 168.1, 100yr 205.4, 200yr 251.0, 500yr 327.2, 1000yr 399.9 (`FM 10-1000yr`), 2000yr 488.7, 5000yr 639.1, 10000yr 685.1 (`FM 2000-10000`); PMP from `Hydrology Data\Rainfall Grids\tiff\Clip_PMP_823mm_21c_27032024.tif` (`.grid`: `Units: mm`; about 1,022-1,965 mm across the Batinah [Likely, parent-grid statistics]).

`HEC_HMS_Block_02.pdata` holds no values, only DSS references: `Table: ARF FM` (`Table Type: Area-Reduction Factor`, `X-Units: KM2`, `Pathname: //ARF FM/AREA-REDUCTION FACTOR///TABLE/`, `Interpolation: Linear Interpolation`); `Percent Graph` tables `FM 2yr`, `FM 5yr`, `FM 10-1000yr`, `FM 2000-10000`, `FM PMP` (`//<name>/PERCENT GRAPH///TABLE/`); `Elev-Dis` and `Elev-Area` entries without DSS records. `ARF FM`, verbatim from the DSS (km², ARF): 1, 0.999; 5, 0.994; 10, 0.987; 20, 0.976; 30, 0.965; 40, 0.956; 50, 0.948; 100, 0.913; 200, 0.864; 500, 0.776; 1000, 0.694; 2000, 0.606. Percent graphs: 145 ordinates (10-min steps), peak step at 48.6-49.3 % of the 24 h carrying 36.7 / 28.5 / 17.0 / 15.1 / 4.6 % of the depth (`FM 2yr` / `5yr` / `10-1000yr` / `2000-10000` / `PMP`).

Runs: `HEC_HMS_Block_02.run` has 13 `Run: FM <rp>` (`Basin: Basin 1`, `Precip: FM <rp>`, `Control: Control 1`, `DSS File: FM_<rp>.dss`); `.nals` has 13 `Analysis: DA <rp> B1` (`Met Model Name: FM <rp>`, `DSS File: DA_<rp>_B1.dss`, 40 `Analysis Point:` = every element, executed 26 Oct 2026). Return periods 2, 5, 10, 25, 50, 100, 200, 500, 1000, 2000, 5000, 10000 yr and PMP. `FM_PMP.log`: `ERROR 23411: No computation point selected for precipitation-frequency grid` (aborted). All `DA_*.out` and `FM_*.log` are 0 bytes except the PMP pair; `DA_<rp>_B1_daa.log` logs storm area and reduced depth per analysis point and reach celerity (R1 0-4.8 m/s), **no peak table**. Peaks live in `results\DAA_DA_<rp>_B1.results` (XML, per `AnalysisPoint`/`BasinElement`, `<StatisticMeasure type="Outflow Maximum" units="M3/S"/>`, `"Outflow Maximum Time"`). `DA 100yr B1`, each element at its own analysis point, peak m³/s (time on 1 Jan): S1 628.6 (13:45), S2 511.5 (13:35), S3 708.3 (14:30), S4 303.9 (12:55), S5 711.8 (14:00), S6 386.9 (12:55), S7 512.2 (13:05), S8 86.2 (12:45), S9 348.0 (13:35), S10 82.0 (12:25), S11 572.2 (13:10), S12 499.5 (13:00), S13 362.4 (12:45), S14 519.5 (13:25), S15 503.7 (13:15), S16 321.9 (13:00), S17 208.2 (12:45), S18 39.4 (12:20); J1 1089.6, R1 1080.8, J2 1646.1, R2 1640.4, **Z4C 1666.4 (15:35)**, J4 711.8, R3 708.6, J5 386.9, R4 384.8, J6 819.3, R5 821.0, J7 821.0, **R2A 1356.1 (14:15)**, J9 572.2, R6 570.9, **Faydh 01 993.5 (13:15)**, **Bidah 03 362.4 (12:45)**, J12 519.5, R7 516.5, J13 784.7, R8 781.4, **R5A 887.1 (14:45)**. Subbasin excess 159-171 mm of 189-205 mm (companion file).

## 2. DSS results (hecdss on scratch copies)

API that worked: `HecDss(path)`, `.record_count()`, `.get_catalog().items` (condensed pathnames), `.get(path)` -> `RegularTimeSeries` (`.values`, `.times`, `.units`) or `PairedData` (`.ordinates`, `.values`); library 7-JA, files 7-IS. `pydsstools` not installed, not needed.

`FM_100yr.dss`: 335 records, 134 condensed pathnames, C parts `PRECIP-INC` and `PRECIP-CUM` only (no flow), F part `MET:FM 100yr><analysis point>` (a subbasin appears once per analysis point it drains to, with that point's ARF). `DA_100yr_B1.dss`: 2,928 records, 1,151 condensed pathnames; 15 C parts (FLOW, FLOW-COMBINE, FLOW-CUMULATIVE 130 each; FLOW-DIRECT, FLOW-BASE, PRECIP-EXCESS, PRECIP-LOSS, INFILTRATION, ET and canopy series 67 each; FLOW-VELOCITY 24); F part `DAA:DA 100yr B1><analysis point>`, E part `5Minute`, D part condensed `31Dec1999-02Jan2000` (daily blocks). `HEC_HMS_Block_02.dss`: 6 records, the tables above. Representative pathnames:

```
//Z4C/FLOW/31Dec1999-02Jan2000/5Minute/DAA:DA 100yr B1>Z4C/
//R2A/FLOW/31Dec1999-02Jan2000/5Minute/DAA:DA 100yr B1>R2A/
//R5A/FLOW/31Dec1999-02Jan2000/5Minute/DAA:DA 100yr B1>R5A/
//Faydh 01/FLOW/31Dec1999-02Jan2000/5Minute/DAA:DA 100yr B1>Faydh 01/
//Bidah 03/FLOW/31Dec1999-02Jan2000/5Minute/DAA:DA 100yr B1>Bidah 03/
//J1/FLOW-COMBINE/31Dec1999-02Jan2000/5Minute/DAA:DA 100yr B1>J1/
//R1/FLOW/31Dec1999-02Jan2000/5Minute/DAA:DA 100yr B1>R1/
//S3/FLOW/31Dec1999-02Jan2000/5Minute/DAA:DA 100yr B1>S3/
//S3/FLOW/31Dec1999-02Jan2000/5Minute/DAA:DA 100yr B1>Z4C/
//S3/PRECIP-EXCESS/01Jan2000-02Jan2000/5Minute/DAA:DA 100yr B1>S3/
//S3/INFILTRATION/01Jan2000-02Jan2000/5Minute/DAA:DA 100yr B1>S3/
//R2/FLOW-VELOCITY/31Dec1999-02Jan2000/5Minute/DAA:DA 100yr B1>Z4C/
//S3/PRECIP-INC/01Jan2000-02Jan2000/5Minute/MET:FM 100yr>S3/      (FM_100yr.dss)
//S3/PRECIP-CUM/31Dec1999-02Jan2000/5Minute/MET:FM 100yr>S3/      (FM_100yr.dss)
//S18/PRECIP-INC/01Jan2000-02Jan2000/5Minute/MET:FM 100yr>S18/    (FM_100yr.dss)
```

Peaks read from the series (flow: 577 values from 2000-01-01 00:00; precipitation: 576 interval-end values from 00:05): Z4C FLOW 1666.40 m³/s at 15:35; R2A 1356.11 at 14:15; R5A 887.09 at 14:45; Faydh 01 993.47 at 13:15; Bidah 03 362.37 at 12:45; S3 FLOW 708.28 at 14:30 at its own point and 655.22 at 14:35 under Z4C's ARF; J1 FLOW-COMBINE 1089.65 at 13:40; S3 PRECIP-INC 15.94 mm per 5 min (191 mm/h) at 11:50, total 189.31 mm; S3 PRECIP-EXCESS 15.04 mm at 11:50, total 159.21; INFILTRATION 1.19 mm at 11:45, total 30.10. DSS values equal the XML statistics to the last digit.

## 3. `Claude Block 02\W1`

`W1\README.md` (2026-10-26): the dams hydrology package from the 13 depth-area analyses `DA <rp> B1`, read at **each dam's own analysis point** (C part `FLOW`; at the dam junctions FLOW = FLOW-COMBINE), inflow only. Its table gives the five dams with catchments Faydh 01 74, Bidah 03 21, R5 (R5A) 117, R2A 176, Z4C 211 km² and the 100 / 200 / 1,000 / 10,000-yr and PMP peaks; every value equals the cross-check below (the PMP column first came out 30-52 times larger, 124,256 to 245,445 m³/s, from the grid declared in inches, and was superseded). Cross-check from `results\DAA_DA_<rp>_B1.results` today, all 13 analyses, m³/s at the dam's own analysis point:

| RP | Faydh 01 | Bidah 03 | R5A | R2A | Z4C |
|---|---|---|---|---|---|
| 2 | 59 | 19 | 39 | 55 | 71 |
| 5 | 200 | 70 | 145 | 222 | 275 |
| 10 | 447 | 159 | 368 | 559 | 735 |
| 25 | 622 | 224 | 530 | 806 | 1042 |
| 50 | 790 | 286 | 685 | 1051 | 1313 |
| 100 | 993 | 362 | 887 | 1356 | 1666 |
| 200 | 1240 | 455 | 1144 | 1736 | 2101 |
| 500 | 1653 | 608 | 1587 | 2377 | 2824 |
| 1000 | 2045 | 753 | 2020 | 2997 | 3512 |
| 2000 | 2269 | 830 | 2321 | 3435 | 3982 |
| 5000 | 2992 | 1095 | 3153 | 4616 | 5274 |
| 10000 | 3212 | 1176 | 3407 | 4977 | 5668 |
| PMP | 4860 | 1688 | 6572 | 9107 | 9500 |

Folder, one level deep: `README.md`; `hms\` (only `hms_b2_pmp.log`; the `hms_b2_pmp.py` named in the README is not there); `output\` (`data`, `excel`, `kmz`, `shp` with `Dams_B1`, `Points_B1`, `Reaches_B1`, `Subbasins_B1.shp`); `package\` (`Block 02 - Dams hydrology package.zip`, 53.2 MB, plus the unpacked folder); `scripts\` (`01_extract_b1.py` .. `06_package.py`, `basinfile.py`, `config.py`, `xlstyle.py`).

## 4. Terrain rasters `Hydrology\Terrain` (EPSG:32640, one float32 band, `AREA_OR_POINT=Area`, no overviews)

| File | Size | Cell | Width x height | Bounds E / N (m) | Nodata | Layout |
|---|---|---|---|---|---|---|
| `GGC_2_MERGE_HDSM.tif` | 27.80 GB | 0.5 m | 131,136 x 128,660 (16.9 Gpx) | 398,676-464,244 / 2,686,580-2,750,910 (65.6 x 64.3 km) | 3.4e38 | LZW, tiles 128 x 128 |
| `GGC_2_MERGE_HDSM_5.tif` | 308 MB | 5 m | 13,114 x 12,866 | same extent | 3.4e38 | LZW, 128 x 128 |
| `NSA_Batinah_2m.tif` | 48.39 GB | 2 m | 112,000 x 108,000 (12.1 Gpx) | 392,000-616,000 / 2,550,000-2,766,000 | -99999 | **uncompressed, untiled** (1 x 112,000 strips; windowed reads slow) |
| `NSA_Batinah_5m.tif` | 2.05 GB | 5 m | 46,400 x 44,000 | 388,000-620,000 / 2,546,000-2,766,000 | 3.4e38 | LZW, 128 x 128 |

Window of the 0.5 m raster, 512 x 512 at columns 65,312-65,823, rows 64,074-64,585 (top-left 431,332.2 E / 2,718,873.1 N): float32, nodata 0.0 %, min 299.336, max 366.390, mean 333.322, std 16.181 m; raw values 355.12497, 355.16675, 355.21588 (sub-millimetre steps: an interpolated surface, not integer metres). Whole-raster statistics exist only on the HMS 5 m copy: min -0.149, max 1456.43, mean 358.0, valid 46.26 % of the rectangle. Basin 1 spans 413,431-440,996 E / 2,700,025-2,735,810 N, inside the GGC_2 extent.

## 5. Vector data `Hydrology\SHP` (EPSG:32640 unless noted)

| File | Geometry | Features | First fields | Wadi2D use |
|---|---|---|---|---|
| `Block 2 Dams\Block 2 Dams.zip`: `SHP\Dams.shp`; `Dikes.shp`; `Reservoirs.shp` | LineString; LineString; Polygon Z | 2; 2; 2 | Dam Name, FSL, Crest Ele, Res_Cap; Dike Name; Reservoir | **yes**: Bidah 03 FSL 100 / crest 105 m, Faydh 01 FSL 230 / crest 235 m; reservoirs 0.83 and 0.96 km² |
| same zip: `EAV\Faydh 01 EAV.csv`, `Bidah 03 EAV.csv`; `Block 2 Dams Details.xlsx` | tables | 146 / 227 rows; 2 | Area m², Elevation m, Volume m³; Dm Type, Crest Ele, FSL, Capacity, QPMF, Hmax, C, Spillway Length | **yes**: EAV 175.8-248.3 m (40.4 Mm³) and 84.7-107.3 m (13.4 Mm³), the dam-as-crest cross-check; Bidah 03 GFRD, 5.7 MCM, QPMF 1,688, C 2.1, spillway 72 m; Faydh 01 RCC, 17.1 MCM, QPMF 4,860, C 2.1, 207 m [Likely column mapping] |
| `already designed dams\FSL_Poly2.shp` | Polygon ZM | 8 | Id, FSL_CONT_V, CREST_CONT, NAME | **yes**: Z4C FSL 168 m (1.14 km²), R2A 162 m (2.68), R5 144 m (2.77); also M3 272, M4 206, SAKHIN 120, Z1 590, RIJMA DABAYAN 269; `CREST_CONT` 0 everywhere |
| `already designed dams\Det_Design_DAMS.shp` | LineString, **no .prj** | 8 | FID_, Entity, Layer, ..., RefName | yes: axes R2A 2,487 m, R5 2,270 m, Z4C 1,596 m (+ 5 other dams); UTM 40N [Likely] |
| `Channels and Dykes 04102026` | LineString | 246 (`Block` = 2: 74) | Length, Width, Type, CHtype, Buffer, Name, Block, CHtypeText | yes (breaklines, channel templates): Flood Protection / Stormwater Main / Secondary Channel and Dyke, `Name` empty, not frozen |
| `Existing Culverts\Culverts_2_4.shp` | LineString | 1,662 | Num, OutE, InlE, H, W, Dist, Code, L, Size | yes: culvert inventory, Blocks 2 and 4 (`3x3x2`, invert levels) |
| `Global Catchments GCA\GCA RENN.shp` | Polygon | 34 | ALLOCATION, G_ID, G_NAME, G_AREA_KM, T_INF_DAM, T_INF_CH (20 fields) | yes: Basin 1 lies in Rijma 291.5 km², Fizh 210.7, Faydh 74.1, Bidah 22.7 [Likely, overlay]; Z4C (S1-S4) in Fizh, R2A and R5A in Rijma |
| `HMS\for HMS\Wall CH\1 for Dams only\Wall.shp`, `CH.shp` | LineString | 5; 7 | id (empty) | yes: HMS wall layer at the dam sites, burn lines [Likely] |
| `HMS\from HMS\1 DAMS only\Basin.shp`, `Junction.shp`, `Reach.shp` | Polygon; Point; LineString | 18; 14; 8 | name, area_sqkm; junction; name, W, SS | **yes**: subbasin polygons, outlets, reach lines (W, SS = the trapezoids) |
| `Landuse Block 02\LandUSE_block2.shp` | Polygon | 51,656 | OBJECTID, LandUse, Descriptio, ParcelLand | limited: parcel allocation (Residential 31,128, Future Plans 12,622, Agricultural 3,049 ...), plain only, no land cover |
| `OQ pipeline\` North, South; `Roads\` (4 files) | LineString (Z) | 26; 6; 1; 1; 221; 1 | NameEnglis, Owner, Status, BlockNo; Name, OSM fields | no; partly (embankments as breaklines) |
| `Streams B2 5m Gmap\B2_Streams5m.shp` | LineString, UTM 40N + unknown vertical CRS | 4,263 | UniqueID, StrahlerID (1-6), ShreveID, HackID | **yes**: refinement bands |
| `Streams NSA 5m Batinah` | LineString | 25,748 | STRM_VAL | yes (whole Batinah) |

## 6. Everything else relevant to a 2D test

- **No HEC-RAS model exists in Block 2** [Certain]: no `.g0x`, `.p0x`, `.u0x`, `.b0x`, `.hdf`, `.rasmap`, and no `.prj` containing `Proj Title` anywhere under Block 2.
- **2D results without their model**: `Hydrology\Raster\Block2_Depth_200Year.tif` (933 MB, 3 m, 16,004 x 14,337, 410,964-458,976 / 2,699,707-2,742,718, nodata -9999, valid 13.68 %, max 13.72 m, mean 1.16 m) and `Block_2_Hazard_200y.tif` (16 MB, 5 m, overviews). The QGIS project sources them from `//workstation-12/tayyab/Block-2/` and a `W:` path: someone else's model, software unknown [Guessing: the other company's]. A benchmark for extent only.
- **HMS terrain derivatives** `HEC_HMS_Block_02\terrain\GGC_2_MERGE_HDSM_5m\00\` (1.3 GB, the 5 m grid): `elevation`, `sinkfill`, `reconditioned`, `flowdir` (int16), `flowaccum` (float32, cells), `streams`, `str_bin`, `sinklocs`, `demsd8.tif`; plus the sqlite flowpath layers and `subbasin_statistics` / `reach_statistics` (companion file). A reference for Wadi2D's delineation and reach parameters.
- **CN grids**: `Hydrology Data\CN_Include_Hill_Area.tif` (uint8, 8.377 m, 27,331 x 27,709, nodata 127, 388-617 km E / 2,547-2,779 km N, 22.5 MB) = the model's `SCS Grid`; `oman_GCN250_merge_int_c.tif` (int16, 219 m).
- **PMP grids** `Hydrology Data\Rainfall Grids\tiff\`: `Clip_PMP_823mm_21c_27032024.tif` (float32, 957.76 m, 237 x 242, EPSG:32640, nodata -9999; the one HMS uses), `PMP_823mm_21c_27032024.tif` (same grid), `PMP_823mm_21c.tif` (float64, EPSG:4326, all Oman).
- **Rainfall workbooks** `Hydrology Data\XLS\`: `FM rainfall 2-PMP.xlsx` (sheet `FM 10 min precipitation`, the pattern source), `IDF C OHDS 2017.xlsx`, `ARF Gonu.xlsx` (a Gonu-based ARF fit, 314 km² -> 0.817; not the model's table), `Qp and Volume.xlsx`; `txt\IDFC extrapolation formula.txt`. `Meteo Data` and `Hydrographs\Abyad 01*` belong to other work.
- **Dam drawings** `Hydrology\Detailed Design Dams\PDF` (10 PDFs: Z4C outlet, tower, spillway and dam excavation sections): the only crest/spillway geometry on disk for the under-construction dams; not read.
- **Backups and copies**: `Hydrology\Backup\1..4 HEC_HMS_Block_02.rar` (0.3-1.3 GB each, not opened), `Backup\20261026_before_PMP_unit_fix\`; `Meetings\Meeting 27102026 Sohar MAFWR\` (2.06 GB rar plus duplicates of rasters, QGIS project and `SHP`). **QGIS project** `Hydrology\QGIS\QGIS Block 02.qgz`: EPSG:32640, 44 layers, several sourced from `W:`, `workstation-12` and `Downloads` (offline here).
