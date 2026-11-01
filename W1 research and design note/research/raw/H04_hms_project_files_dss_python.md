# H04 HEC-HMS project file formats and DSS access from Python

Date: 2026-10-29

## Scope

What Wadi2D must read to run test (a) of decision 6 (all-lumped replication of the Block 2 HEC-HMS model) and to import
the hydrology of any HMS project: the grammar of the HMS text files (`.hms`, `.basin`, `.met`, `.control`, `.run`, `.pdata`,
`.gage`, `.grid`, `.terrain`, `.nals`), the geometry file (`.sqlite`), the DSS pathname conventions HMS 4.12 uses for inputs
and results, where peaks and volumes are summarised (`.results`, `.log`, `.out`), and the Python routes into DSS (`hecdss`,
`pydsstools`, HEC's Jython API). Then a reader design and a test strategy against the real Block 2 project.

Primary evidence is of two kinds: (1) files HEC's own software wrote, read on this machine - the Block 2 project
(`D:\Mojtaba\Renardet\2224 WS11\Batinah\Block 2\Hydrology\HEC_HMS_Block_02`, HMS 4.12), the Block 4 and Block 6 projects,
and the four sample projects HEC ships in `C:\Program Files\HEC\HEC-HMS\4.12\samples.zip` (castro, tenk, tifton,
river_bend): 111 text files, 23 basin models, 1,321 subbasins, 1,073 reaches, 52 reservoirs, 85 sinks, 11 diversions,
11 gages; (2) HEC's manuals and the libraries' own source, issues and changelogs. Everything that touched the user's DSS
files was done on copies in the scratchpad; nothing under the Batinah folders was written.

Not in scope: the hydrologic methods themselves (SCS CN, lag, Muskingum-Cunge, depth-area) - those are H-topics of their own;
the HMS `.hdf` 2D mesh file of the 2D Diffusion Wave subbasin (seen in Block 6, not parsed).

## Findings

### A. The text-file grammar (all ten file types share it)

1. One grammar for every HMS text file: a block opens with a column-0 `Type: Name` line and closes with a column-0 `End:`;
   parameters are `Key: Value` indented exactly five spaces; blank lines may appear inside a block; CRLF line endings
   (110 of 111 files), no BOM, UTF-8 (3 files needed cp1252 for a Latin-1 character). [Certain] - scan of 111 files:
   "106486 kv5 canonical, 8910 header col0, 8854 End:, 18727 blank" (grammar_scan.py, this session).
   Source: file:///D:/Mojtaba/Renardet/2224%20WS11/Batinah/Block%202/Hydrology/HEC_HMS_Block_02/Basin_1.basin and the
   HEC samples; secondary: https://hms-commander.readthedocs.io/en/latest/data_formats/overview/ ("Parameters are indented
   with 5 spaces and use a colon delimiter").

2. HMS's own writer is not canonical, so a byte-exact round trip must keep the raw separator per line. Three fixed
   irregularities, each 100 % consistent: `Latitude Degrees:  24.51...` always has two spaces after the colon (1,326 of
   1,326 lines); `Layer:13` inside `Map Layer:` sub-blocks has no space (62 lines); an empty value is written with a
   trailing space (`Depth: `, `Description: `, `Flow Hydrograph Name: `), whereas a nested-block opener has none
   (`Element Layer:`). [Certain] - "kv5 value with extra/trailing spaces 1326 ... Latitude Degrees:  #" (grammar_scan.py).
   Source: the same files.

3. Nesting is lexically ambiguous: a sub-block opens with an indented `Name:` line that looks exactly like an empty-valued
   key, and closes with an indented `End <Name>:` line; its parameters are indented ten spaces in the `Basin Layer
   Properties` and `Break Point` sub-blocks, five spaces in the Reservoir `Spillway`/`Conduit`/`Pump`/`Evaporation` and
   Subbasin `Canopy`/`Surface` sub-blocks, and seven spaces in the `.gage`/`.grid` `Variant: Variant-1` sub-block (closed
   by `End Variant: Variant-1`). Terminators seen: `End Layer:` 279, `End Parameter Set:` 140, `End Break Point:` 95,
   `End Evaporation:` 26, `End Spillway:` 26, `End Diverter:` 11, `End Et:` 3, `End Conduit:` 3, `End Pump:` 2,
   `End Canopy:` 1, `End Surface:` 1. Only the matching `End X:` tells an opener from a key. [Certain] -
   "nested ends seen: [('End Layer:', 279), ('End Parameter Set:', 140), ('End Break Point:', 95) ..." (grammar_scan.py).
   Source: HEC samples (tifton/Tifton.basin, river_bend/Minimum_Facility.basin, castro/castro.gage).

4. One column-0 block does not close with `End:`. `Computation Point: <element>` in a `.basin` file closes with
   `End Computation Point: ` (note the trailing space), 31 occurrences across the samples and Block 4/6, each holding
   `Parameter Set: n` / `End Parameter Set:` and `Graph Definition: ` / `End Graph Definition: ` sub-blocks. A parser that
   assumes every column-0 block ends at `End:` swallows the rest of the file: my first typed parser failed on 17 of 111
   files for exactly this reason. [Certain] - "Castro_1.basin | open block at EOF: ('Computation Point', 280)"
   (debug_parse.py). Source: samples/castro/Castro_1.basin lines 280-307.

5. Repeated keys inside one block are ordered lists, not overwrites: `Use Basin Model:` (one per basin the met model
   serves), `Analysis Point:` (40 per depth-area analysis in Block 2), `Gage:` + `Volume Weight:` pairs (Weighted Gages),
   `Pan Evaporation:` x12 and `Evapotranspiration Coefficient:` x12 (Monthly Evaporation), `2D Connection Name:` groups
   of five keys (2D subbasin), `Spillway:` sub-blocks (Main and Auxiliary outlets), `Start Time:`/`End Time:` pairs
   inside `Variant`. A dict-of-first-occurrence parser (the W1 `basinfile.py`, hms-commander's `_parse_attribute_block`)
   silently loses them. [Certain] - "Duplicate keys within a block overwrite earlier ones, because the result is a plain
   dict" (hms-commander `_parsing.py` as read).
   Source: https://raw.githubusercontent.com/gpt-cmdr/hms-commander/main/hms_commander/_parsing.py; samples/castro/GageWts.met.

6. Methods are discriminated by a selector key whose value fixes the parameter keys that follow, in a fixed order within
   the Subbasin block: `Discretization` -> `Canopy` -> `Surface` -> `LossRate` -> `Transform` -> `Baseflow`. Values seen
   in 1,321 subbasins and 1,073 reaches: `LossRate` {SCS 1302, Initial+Constant 12, Deficit Constant 6, Soil Moisture
   Account 1}; `Transform` {SCS 1304, Snyder 8, Modified Clark 4, 2D Diffusion Wave 4, Clark 1}; `Baseflow` {None 1304,
   Recession 12, Mesh Linear Reservoir Interflow 4, Linear Reservoir 1}; `Route` {Muskingum Cunge 1061, Modified Puls 32,
   Controlled Outflow 26 (reservoirs), Muskingum 5, Lag 1}; `Canopy`/`Surface` {None, Simple}; `Discretization` {None,
   Structured, Unstructured, File-Specified}; `Unitgraph Type` {STANDARD}; `Channel` {Trapezoid}. Keys per method:
   - SCS loss: `Percent Impervious Area`, `Curve Number`, `Initial Abstraction`; Initial+Constant: `Initial Loss`,
     `Constant Loss Rate`; Deficit Constant: `Initial Deficit`, `Maximum Deficit`, `Percolation Rate`, `Recovery Factor`;
     Soil Moisture Account: `Initial Soil Storage Percent`, `Initial Gw1/Gw2 Storage Percent`, `Soil Maximum
     Infiltration`, `Soil Storage Capacity`, `Soil Tension Capacity`, `Soil Maximum Percolation`, `Groundwater 1/2 Storage
     Capacity`, `... Routing Coefficient`, `... Maximum Percolation`.
   - SCS transform: `Lag` (minutes), `Unitgraph Type`; Snyder: `Snyder Method`, `Snyder Tp`, `Snyder Cp`; Clark: `Clark
     Method`, `Time of Concentration`, `Storage Coefficient`, `Time Area Method`; Modified Clark: `Mod Clark Method`,
     `Time of Concentration`, `Storage Coefficient` (+ `Discretization: File-Specified`, `File: regions\hrapcells`, or
     `Structured` with `Projection: 5070`, `Cell Size: 1000.0`); 2D Diffusion Wave: `Discretization: Unstructured`,
     `File: <mesh>.hdf`, repeated `2D Connection Name`/`Boundary Type`/`Flow Hydrograph Name`/`Flow Hydrograph Energy
     Grade Slope`/`Ratio of Subbasin Baseflow`, then `Downstream Flow Link`, `Normal Depth Friction Slope`, `Implicit
     Weighting Factor`, `Water Surface Tolerance`, `Volume Tolerance`, `Maximum Number Iterations`, `Time Step Method`,
     `Maximum Courant Number`, `Maximum Time Step`, `Use Warm Up Period`, `Warm Up Period`, `Warm Up Period Fraction`,
     `Number Of Cores`.
   - Recession baseflow: `Recession Factor`, `Initial Flow/Area Ratio` or `Initial Baseflow`, `Threshold Flow to Peak
     Ratio`; Linear Reservoir: `Groundwater Layer`, `GW-1/GW-2 Number Reservoirs`, `... Routing Coefficient`,
     `... Initial Baseflow`.
   - Muskingum Cunge: `Channel: Trapezoid`, `Length`, `Energy Slope`, `Mannings n`, `Bottom Width`, `Side Slope`,
     `Initial Variable: Combined Inflow`, `Space-Time Method: Automatic DX and DT`, `Index Parameter Type: Index
     Celerity`, `Index Celerity`, `Number Subreaches`, `Maximum Depth Iterations`, `Maximum Route Step Iterations`,
     `Channel Loss`; Muskingum: `Muskingum K`, `Muskingum x`, `Muskingum Steps`; Lag: `Lag`; Modified Puls (reach):
     `Number of Reaches`, `Storage Outflow Table Name`; Modified Puls (reservoir): `Routing Curve:
     Elevation-Area-Outflow`, `Initial Elevation`, `Elevation-Area Table`, `Elevation-Outflow Table`, `Primary Table`;
     Controlled Outflow (reservoir): `Routing Curve: Elevation-Storage | Elevation-Area`, `Elevation-Storage Table` or
     `Elevation-Area Table`, `Initial Elevation`, `Adaptive Control`, `Main Tailwater Condition`, `Auxiliary Tailwater
     Condition`, `Auxiliary Flow To`, then sub-blocks `Spillway: Broad-Crested Spillway` (`Spillway Outlet: Main |
     Auxiliary`, `Spillway Crest Length: 1000`, `Spillway Crest Elevation: 207`, `Spillway Coefficient: 2.2`,
     `End Spillway:`; Block 6 dam "Al Ais 10 Reservoir"), `Conduit: Culvert` (`Culvert Shape`, `Chart Number`, `Scale
     Number`, `Rise`, `Span`, `Number Barrels`, `Culvert Length`, `Entrance/Exit Loss Coefficient`, `Top Manning's n`,
     `Inlet/Outlet Invert Elevation`, `End Conduit:`), `Pump:`, `Evaporation Method: Zero Evaporation` / `End Evaporation:`.
   The 8-point cross-section option of Muskingum-Cunge (decision 8), Green and Ampt losses and Source elements were not
   seen in any file on this machine; their keys are unknown. [Certain for what was seen; Likely that HMS 4.12 has more
   values, e.g. Green and Ampt, Kinematic Wave, Straddle Stagger] - "LossRate: [('SCS', 1302), ('Initial+Constant', 12),
   ('Deficit Constant', 6), ('Soil Moisture Account', 1)]" (survey_hms_files.py). Source: the 23 basin files listed in
   Scope; Block 6 `Basin_1___1D___DAM.basin` for the spillway block.

7. Topology and coordinates. `Downstream: <element name>` on Subbasin, Junction, Reach, Reservoir and Diversion
   (plus `Divert To:` and a `Diverter:` sub-block with `Inflow Diversion Table Name` on Diversion); Sink and the terminal
   junction have none. `Canvas X`/`Canvas Y` are projected coordinates in the basin's `Coordinate System` (OGC WKT string
   on one line in `Basin Spatial Properties`, EPSG:32640 for Block 2), `From Canvas X/Y` is the upstream end of a reach,
   `Latitude Degrees`/`Longitude Degrees` the subbasin centroid. The polygons and lines are NOT in the `.basin`: they
   live in the Spatialite file named by `File: Basin_1.sqlite` (tables `subbasin2d` MultiPolygon with `area_sqkm`,
   `centroid_x/y`; `reach2d` LineString with `slope`, `length`, `dscontarea`; `outlet`, `centroid`, `longest_flowpath`,
   `centroidal_flowpath`, `teneightyfive_flowpath`; `subbasin_statistics`, `reach_statistics`; SRID 32640). [Certain] -
   "geometry_columns: [('subbasin2d', 'GEOMETRY', 6, 32640), ('reach2d', 'GEOMETRY', 2, 32640) ..." (sqlite3 read-only).
   Source: Basin_1.basin and Basin_1.sqlite of Block 2.

8. Units are implicit. `Unit System: Metric|English` in the `Basin:` and `Meteorology:` headers fixes the unit of every
   number in those files (Block 2: `Area` km2, `Lag` min, `Length` m, `Bottom Width` m, `Storm Depth` mm, `Storm Area`
   km2, `Initial Abstraction` mm; castro: mi2, ft, in). Only paired-data tables (`X-Units: KM2`, `Y-Units: M3/S`),
   gages (`Units: IN` / `INCHES` / `cfs` / `CFS` / `FT`, free text) and grids (`Units: mm`) carry unit strings, and the
   W1 README of Block 2 records a real case where `Units: in` on a PMP grid multiplied the rainfall by 25.4.
   [Certain] - "Units: in set to Units: mm ... HMS multiplies the 823 mm grid by 25.4" (Block 2 W1 README).
   Source: file:///D:/Mojtaba/Renardet/2224%20WS11/Batinah/Block%202/Claude%20Block%2002/W1/README.md; HEC_HMS_Block_02.grid.

9. The project file `.hms` is a registry: `Project:` header (`Version: 4.12`, `Filepath Separator: \`, `DSS File Name:
   HEC_HMS_Block_02.dss`, `Time Zone ID: America/Los_Angeles`), then one `Basin:`, `Precipitation:` (met model) and
   `Control:` block per component with `Filename:` (`FileName:` for Control - the capitalisation differs) and `Last
   Modified Date/Time`. HEC: component names map to file names with illegal characters replaced by underscores.
   [Certain] - "'North Branch' becomes North_Branch.basin" (HEC User's Manual, Directories and Files).
   Source: https://www.hec.usace.army.mil/confluence/hmsdocs/hmsum/latest/projects-and-control-specifications/directories-and-files

10. `.control`: `Start Date: 31 December 1999`, `Start Time: 24:00`, `End Date: 2 January 2000`, `End Time: 24:00`,
    `Time Interval: 5` (minutes), `Time Zone ID: Asia/Dubai`, `Time Zone GMT Offset: 14400000` (milliseconds). HEC:
    24:00 "is automatically converted to 00:00 on the following day"; intervals 1 minute to 1 day; start and end must be
    integer multiples of the interval. [Certain] Source: Control_1.control;
    https://www.hec.usace.army.mil/confluence/hmsdocs/hmsum/latest/projects-and-control-specifications/control-specifications

11. `.met`: a `Meteorology:` header with the method selectors (`Precipitation Method`, `Air Temperature Method`,
    `Atmospheric Pressure Method`, `Dew Point Method`, `Wind Speed Method`, `Shortwave Radiation Method`, `Longwave
    Radiation Method`, `Snowmelt Method`, `Evapotranspiration Method`), `Unit System`, `Set Missing Data to Default`,
    repeated `Use Basin Model:`; then `Precip Method Parameters: <method>`; then one `Subbasin:` block per subbasin;
    `Gage:` blocks (`Type: Total Storm`, `Total Precipitation`) for storm-total gages; `Evapotranspiration Method
    Parameters:`. Hypothetical Storm keys (Block 2): `Precipitation Method: Point Depth | Precipitation-Frequency Grid`,
    `Storm Depth: 205.4`, `Storm Type: Specified Pattern`, `Storm Duration: 24`, `Pattern Name: FM 10-1000yr` (a Percent
    Graph table), `Storm Area: 300`, `Depth-Area Reduction Method: User-Specified`, `Reduction Table Name: ARF FM`,
    `Uniform Depth: Yes`, and for the grid variant `Precip-Freq Grid Name: PMP`, `Computation Point Basin Name`,
    `Computation Point Element Name`. Other methods seen: `Weighted Gages` (`Use HEC1 Weighting Scheme`, `Use Indexing`,
    `Allow Depth Override`; per subbasin `Gage:`/`Volume Weight:` pairs and `Temporal Distribution Weight`), `Specified
    Average` (per subbasin `Gage:`), `Gridded Precipitation` (`Precip Grid Name`, `Time Shift Method: NONE`). The 13
    Block 2 met files differ only in name, `Storm Depth`, `Pattern Name` and timestamps. [Certain] -
    "Storm Depth: 205.4 ... Storm Area: 300 ... Reduction Table Name: ARF FM" (FM_100yr.met). Source: FM_100yr.met,
    FM_PMP.met; samples castro/GageWts.met, river_bend/Historic_Precipitation.met, tenk/Stage3_HRAP.met.

12. `.pdata` holds only metadata; the numbers are paired-data records in the project DSS: `Table: ARF FM` -> `Table Type:
    Area-Reduction Factor`, `X-Units: KM2`, `Use External DSS File: NO`, `DSS File: HEC_HMS_Block_02.dss`, `Pathname:
    //ARF FM/AREA-REDUCTION FACTOR///TABLE/`, `Interpolation: Linear Interpolation`. C parts seen: PERCENT GRAPH,
    AREA-REDUCTION FACTOR, STAGE-FLOW, ELEVATION-AREA, ELEVATION-STORAGE, STORAGE-FLOW (for `Table Type: Storage-Outflow`);
    F = TABLE, D and E empty. hecdss returns them as `PairedData` (ordinates 145, values 145x1, units '%', type 'Linear').
    [Certain] - "ordinates: ndarray shape=(145,) first=[0., 0.69, 1.39] ... units_independent: '%'" (probe_hecdss.py).
    Source: HEC_HMS_Block_02.pdata, HEC_HMS_Block_02.dss (copy).

13. `.run`, `.nals`, `.grid`, `.terrain`. `Run:` -> `Log File`, `DSS File`, `Is Save Spatial Results`, `Basin`, `Precip`,
    `Control`, `Save State Type`, `Time-Series Output: Save All`, `Time Series Results Manager Start:`/`End:` (empty
    pair), `Last Execution Date/Time` once computed. `Analysis:` (`.nals`, depth-area) -> `DSS File`, `Time Zone GMT
    Offset: -28800000`, `Start/End Date/Time`, `Time Interval`, `Basin Model Name`, `Met Model Name`, `Analysis Point:` xN,
    `Time-Series Output`, `Last Execution Date/Time`. `Grid:` -> `Grid Type` {Precipitation, Precipitation-Frequency,
    Curve Number}, `Units`, `Data Source Type` {GeoTIFF with `Filename`, External DSS with a `Variant` sub-block holding
    `DSS File Name` and `DSS Pathname: /HRAP/ABRFC/PRECIP////`}. `Terrain Data:` -> `Terrain Directory`, `Vertical Units:
    Meters`, `Stream Threshold: 20 km2`. Every manager file starts with a `<X> Manager: <project>` header carrying
    `Version` and `Filepath Separator`. [Certain] Source: HEC_HMS_Block_02.run/.nals/.grid/.terrain; samples castro/castro.run.

14. `.gage`: `Gage Manager:` header, then `Gage:` blocks with `Reference Height Units`, `Reference Height`, `Gage Type`
    {Precipitation, Flow, Stage; HEC lists 18 types}, `Precipitation Type: Incremental`, `Units`, `Data Type` {PER-CUM,
    INST-VAL, PER-AVER, INST-CUM}, `Data Source Type: External DSS`, and a `Variant: Variant-1` sub-block (seven-space
    indent) with `Default Variant`, `DSS File Name`, `DSS Pathname: /CASTRO VALLEY/FIRE DEPT./PRECIP-INC//10MIN/OBS/`
    (D part empty, so the whole record is read) and one or more `Start Time: 16 January 1973, 03:10` / `End Time:` pairs
    (time windows). Manually entered gages are stored by HMS in a DSS file in the project directory named after the gage.
    [Certain for External DSS, from HEC's own sample files; Likely for manual entry, from the manual only] - "The program
    names the file after the gage" (HEC UM, Time-Series Data, as read).
    Source: samples/castro/castro.gage; https://www.hec.usace.army.mil/confluence/hmsdocs/hmsum/latest/shared-component-data/time-series-data

### B. DSS conventions used by HMS 4.12

15. HMS 4.12 writes DSS version 7 files ("7-IS"); hecdss 0.1.29 ships library "7-JA" and opens them. HEC: "Support for
    HEC-DSS version 6 ended July 31, 2024" and "HEC-DSS version 7 is the recommend version"; hecdss reads only version 7
    (convert v6 with DSSVue, Tools menu, or Jython `HecDSSUtilities.convertVersion`). The file signature is the ASCII
    `ZDSS` at byte 0 and `7-IS` at byte 16. [Certain] - "DSS Versions - Software: 7-IS, File:  7-IS"
    (HEC_HMS_Block_02.out). Source: https://www.hec.usace.army.mil/software/hec-dss/ ;
    https://github.com/HydrologicEngineeringCenter/hec-dss-python/issues/60

16. Result pathnames. A is empty; B is the element name exactly as in the `.basin` (case and spaces kept: `Faydh 01`);
    C the parameter; D the block start date `01Jan2000` (one record per calendar day for 5-minute data, so a 48 h run
    is three records `31Dec1999`, `01Jan2000`, `02Jan2000`); E the interval in DSS 7 spelling `5Minute` (a converted DSS 6
    file keeps `5MIN`); F names the producer: `RUN:<run name>` for a simulation run (`//SHA-S21/FLOW/01Jan2000/5Minute/
    RUN:FM 200yr B2/`, Block 4), `DAA:<analysis name>><analysis point>` for a depth-area analysis (`//S18/FLOW//5Minute/
    DAA:DA 100yr B1>S18/`, 40 analysis points -> 40 F parts in one file), `MET:<met name>` for the met model output of a
    run and `MET:<met name>><analysis point>` for the storm generated per analysis point. Met output goes to a DSS file
    named after the met model (`FM_100yr.dss`: only PRECIP-INC/PRECIP-CUM, 335 records), flow results to the run's or
    analysis's `DSS File` (`DA_100yr_B1.dss`: 2,928 records). Pathnames are case-insensitive but whitespace-sensitive.
    [Certain] - "//S18/PRECIP-INC//5MIN/MET:FM 100yr>S18/" (DAA_DA_100yr_B1.results); "DSS is not capitilazation
    sensitive but it is white space sensitive" (hecdss issue 67). Source: results/DAA_DA_100yr_B1.results; FM_100yr.dss,
    DA_100yr_B1.dss, Block 4 FM_200yr_B2.dss (binary scans); https://github.com/HydrologicEngineeringCenter/hec-dss-python/issues/67

17. C parts and data types. In the DAA file: FLOW, FLOW-COMBINE, FLOW-CUMULATIVE (every element), FLOW-BASE, FLOW-DIRECT,
    PRECIP-EXCESS, PRECIP-EXCESS-CUM, PRECIP-LOSS, PRECIP-LOSS-CUM, INFILTRATION, ET-POTENTIAL, ET-CANOPY, EXCESS-CANOPY,
    STORAGE-CANOPY (subbasins); in the met file PRECIP-INC, PRECIP-CUM. HEC's descriptor table adds FLOW-DIVERSION,
    FLOW-LOCAL, FLOW-RESIDUAL, STORAGE, ELEVATION. FLOW is `INST-VAL` in `M3/S` with 577 values from 00:00 1 Jan to
    00:00 3 Jan (24:00 2 Jan); PRECIP-INC and PRECIP-EXCESS are `PER-CUM` in `MM` with 576 values stamped at the END of
    each 5-minute period (first 00:05). The DSS convention: "Period-average values are stored at the end of the period".
    [Certain] - "units: 'M3/S' data_type: 'INST-VAL' interval: 300 ... n=577" (probe_hecdss.py). Source: DA_100yr_B1.dss
    (copy); https://www.hec.usace.army.mil/confluence/hmsdocs/hmsum/latest/data-storage-in-hec-dss/descriptors ;
    https://www.hec.usace.army.mil/confluence/dssdocs/dssvueum/introduction/time-series-conventions

18. Time zones are decorative. The DSS records carry an empty time-zone name (hecdss `time_zone_name: ''`), although the
    project says `Time Zone ID: America/Los_Angeles`, the control `Asia/Dubai` / `14400000` ms and the analyses
    `-28800000` ms; HEC: times are processed "in an arbitrary local time zone that does not observe daylight saving time";
    DSSVue ignores time-zone settings for records without one. Treat every HMS time as naive local simulation time.
    [Certain for the files; Likely as the general rule] - "If a DSS record does not have a time zone set it is
    tabulated/displayed ignoring time zone settings" (DSSVue UM). Source:
    https://www.hec.usace.army.mil/confluence/dssdocs/dssvueum/display-and-editing/setting-the-time-zone ;
    HEC_HMS_Block_02.hms, Control_1.control, HEC_HMS_Block_02.nals.

19. Where the peak summaries are. Not in `.out` (it is the DSS open/close log: "List of all data read or written from DSS
    files") and not in the run `.log` (the 13 `FM_*.log` are 0 bytes here; `FM_PMP.log` holds the compute NOTE/ERROR
    lines of an aborted run). For depth-area analyses they are in `results/DAA_<analysis>.results`, an XML of 735 KB per
    analysis: `<AnalysisPoint name="S18" fPart="DAA:DA 100yr B1>S18">` -> `<BasinElement name type>` -> `<DrainageArea
    area units>` -> `<Hydrology>` with `<TimeSeries>` (`<TimeSeriesType>`, `<DssFileName>`, `<DssPathname>`) ->
    `<Statistics>` with `<StatisticMeasure type="Outflow Maximum" value="606.0563464" units="M3/S"/>`, `Outflow Maximum
    Time`, `Outflow Volume` (M3), `Outflow Depth` (MM), `Outflow Average`, the same for Inflow, Direct Flow, Baseflow,
    and `Precipitation Total/Maximum/Volume`, `Loss Total`, `Excess Total` for subbasins; 3,562 StatisticMeasure elements
    per file. The DAA log `DA_<rp>_B1_daa.log` adds `NOTE 15405: Storm area is 1.67 sq.km. for analysis point "S18"`,
    `NOTE 23409: Area-reduced hypothetical storm depth: 205.023 mm` and `NOTE 41083: Celerity in reach "R1" ranged from
    0.0 to 4.8 m/s`. No `RUN_*.results` exists in Block 2 (no run was computed to completion); whether HMS 4.12 writes
    one for runs is unverified. [Certain for what exists; Guessing for run results XML] - "<StatisticMeasure type="Outflow
    Maximum" displayString="Maximum Outflow" value="39.3801133" units="M3/S" />" (DAA_DA_100yr_B1.results).
    Source: file:///D:/Mojtaba/Renardet/2224%20WS11/Batinah/Block%202/Hydrology/HEC_HMS_Block_02/results/DAA_DA_100yr_B1.results ;
    https://www.hec.usace.army.mil/confluence/hmsdocs/hmsum/latest/projects-and-control-specifications/directories-and-files

20. The XML statistics and the DSS series agree to the last digit, so either can be the oracle for the other: S18 outflow
    maximum 39.3801133 m3/s at 01Jan2000 12:20 in the XML; hecdss max 39.38011335 at 2000-01-01 12:20; XML volume
    273,489.3564 m3 = hecdss sum 911.631 m3/s x 300 s = 273,489.3 m3; XML depth 163.8053 mm = 273,489.36 / 1.6696 km2 =
    163.805 mm = XML Excess Total (no baseflow). The five dam-site peaks (Faydh 01 993.5, Bidah 03 362.4, R5A 887.1, R2A
    1356.1, Z4C 1666.4 m3/s, 100-yr) equal the Block 2 W1 README table. [Certain] Source: probe_hecdss.py and timing
    script on DA_100yr_B1.dss (copy); the .results file; Block 2 W1 README.

### C. Python access

21. `hecdss` (HEC's official package; MIT; `pip install hecdss`; 0.1.29 installed here, 0.1.33 on PyPI 2026-08-28;
    Python >= 3.8; requires numpy and tzdata; ships `lib/hecdss.dll` 1.9 MB and `lib/libhecdss.so` 4.3 MB and calls them
    through ctypes, no Java). API as installed: `HecDss(filename)` opens or CREATES the file; context manager;
    `get_catalog()` -> `Catalog` with `.items` (condensed `DssPath` objects whose D part is `31Dec1999-02Jan2000`) and
    `.uncondensed_paths` (one per daily block); `get(pathname, startdatetime=None, enddatetime=None, trim=False)` strips
    the D part for time series and returns the FULL extent (`hec_dss_tsGetDateTimeRange(fullSet=1)`) unless dates are
    given, trimming leading/trailing undefined values; `RegularTimeSeries` fields `times` (list of datetime),
    `values` (float64 ndarray), `units`, `data_type`, `interval` (s), `start_date`, `time_granularity_seconds`,
    `julian_base_date`, `time_zone_name` (applied as `ZoneInfo` when present), `id`, `location_info`; `PairedData`
    (`ordinates`, `values` n x k, `labels`, `units_independent/dependent`, `type_independent/dependent`); `GriddedData`;
    `put(container)`, `delete`, `record_count()`, `get_record_type()`, `set_global_debug_level(0-15)` (default 3 prints
    every zopen/zread to stdout). [Certain] - "HecDss(file_path: str): Opens a DSS file located at the provided file
    path" (README); "filename (str): DSS filename to be opened; it will be created if it doesn't exist" (hecdss.py).
    Source: https://github.com/HydrologicEngineeringCenter/hec-dss-python ; https://pypi.org/project/hecdss/ ;
    file:///C:/Users/mojtaba/AppData/Local/Programs/Python/Python312/Lib/site-packages/hecdss/hecdss.py

22. hecdss pitfalls on record (issues): a specified D part limited the data to that block (#54, closed Dec 2024, "Our next
    release should address and fix this issue"); long regular series with missing blocks were truncated because
    `hec_dss_tsGetSizes` "Reports sizes for blocks, not within blocks" (#55, closed Feb 2025 with a documenting test, no
    fix named); the catalog is case-insensitive (#33); 1Month regular series could not be read (#91, closed Jul 2025);
    `put()` can return 0 on failure when `location_info` is set (#126, open Sep 2026); time-zone support in the DLL was
    added in Apr 2025 (#82). Measured here on the 6.9 MB DAA file: open 2 ms, catalog of 1,151 condensed items 26 ms,
    40 series x 577 values 194 ms (4.9 ms per series). [Certain] Source:
    https://github.com/HydrologicEngineeringCenter/hec-dss-python/issues/54 , /issues/55 , /issues?q=is%3Aissue ;
    timing script in this session.

23. `pydsstools` (Gyan Basyal, MIT, third party): Cython bindings over a bundled static heclib; 3.1.0 of 2026-06-06,
    3.0.0 of 2026-05-01 "NumPy 2.0 and Cython 3.0 compatibility (builds against NumPy 1.x for 3.9-3.12, 2.x for 3.13+)",
    wheels for Windows and Linux; targets HEC-DSS 7-IV-1; reads DSS-6 on Windows only ("DSS-6 files now raise an error
    on Linux and Mac"); API `HecDss.Open(file)` context manager, `read_ts(pathname, window=(start, end), trim_missing=True,
    reg=True)` -> `TimeSeriesStruct` (`values`, `times`, `data_units`, `data_type`, `interval` s, `granularity`, `tzid`,
    `nodata`, `empty`), `put_ts(TimeSeriesContainer)`, paired data, grids, `search_path`, `squeeze_file`; an empty D part
    reads all data. Build from source needs Visual Studio Build Tools on Windows. Not installed here, not tested.
    [Certain from its docs and changelog; Likely that its wheels install cleanly on this Python 3.12] -
    "Fixed DSS-6 regular time-series time assertion: use window read instead of trim_missing" (CHANGES.MD 3.1.0).
    Source: https://raw.githubusercontent.com/gyanz/pydsstools/master/CHANGES.MD ;
    https://pydsstools.readthedocs.io/en/stable/topics/timeseries.html ;
    https://raw.githubusercontent.com/gyanz/pydsstools/master/docs/source/installation.md

24. Third route, HEC's Jython API, already proven on this machine: HMS computes headless with `HEC-HMS.cmd -script
    <file.py>` run from `C:\Program Files\HEC\HEC-HMS\4.12` (the script path must contain no spaces), using `from
    hms.model.JythonHms import *; OpenProject(name, dir); ComputeRun(name); SaveAllProjectComponents(); Exit(1)` and,
    for depth-area analyses, the `hms.model.Project` object's `computeDepthAreaAnalysis(name)` (Block 04: 13 analyses in
    19 s; Block 02: `DA PMP B1` in 5 s). DSSVue's Jython DSS API: `HecDss.open(file)`, `get(path, True)` for the whole
    span, `getCatalogedPathnames("B=*XYZ*")`, `setTimeWindow("04MAR2003 1400 06APR2004 0900")`, `TimeSeriesContainer`
    (`fullName`, `interval`, `times`, `values`, `numberValues`, `units`, `type`), `put`, `done()`. The HMS launcher is a
    plain cmd file that sets `-Dpython.path` and `java.library.path` and starts `hms.Hms` under the bundled JRE.
    [Certain] - "Run: cd "C:\Program Files\HEC\HEC-HMS\4.12" && HEC-HMS.cmd -script <this file>" (hms_compute_all.py).
    Source: file:///D:/Mojtaba/Renardet/2224%20WS11/Batinah/Block%204/Claude%20Block%2004/scripts/hms_compute_all.py ;
    file:///C:/Program%20Files/HEC/HEC-HMS/4.12/HEC-HMS.cmd ;
    https://www.hec.usace.army.mil/confluence/dssdocs/dssvueum/scripting/reading-and-writing-to-hec-dss-files ;
    https://www.hec.usace.army.mil/confluence/hmsdocs/hmsum/latest/scripting

25. `hms-commander` (gpt-cmdr, third party) is a regex editor, not a parser: `rf'{block_keyword}:\s*(.+?)\n(.*?)End:'`
    with DOTALL over the whole file, attributes into a plain dict (duplicates overwrite, nesting ignored), updates by
    string replacement, DSS through Java/pyjnius; its format pages document keys that HMS 4.12 does not write (`Type:`,
    `DSS File:` in gages instead of `Gage Type:` and the `Variant` sub-block; `Return Period`, `Temporal Pattern`,
    `Precipitation Gage Weight` in met files) - they read as generated, not observed. Usable as a list of ideas, not as
    a specification. [Certain for the discrepancies; Likely about their origin] - "Blocks are found with regexes built
    from the keyword ... Nested blocks are not handled" (as read from `_parsing.py`). Source:
    https://raw.githubusercontent.com/gpt-cmdr/hms-commander/main/hms_commander/_parsing.py ;
    https://hms-commander.readthedocs.io/en/latest/data_formats/gage_file/ ;
    https://hms-commander.readthedocs.io/en/latest/data_formats/met_file/

## Equations and algorithms

### E1. The HMS text grammar (as observed; EBNF)

```
file        = { blank | block | cpblock } ;
block       = header , { item } , "End:" , EOL ;                     (* column-0 "End:" *)
cpblock     = "Computation Point: " name , EOL , { item } , "End Computation Point: " , EOL ;   (* .basin only *)
header      = type , ":" , [ " " , name ] , EOL ;                     (* column 0; name may be empty: "Basin Layer Properties:" *)
item        = kv | blank | subblock ;
kv          = indent , key , sep , value , EOL ;
indent      = 5*" " | 7*" " | 10*" " ;                               (* 5 normal; 7 inside Variant; 10 inside Layer/Break Point *)
sep         = ": " | ":  " | ":" ;                                    (* ":  " only after "Latitude Degrees"; ":" only in "Layer:13" *)
value       = text | "" ;                                             (* empty values carry one trailing space *)
subblock    = indent , subname , ":" , [ " " , subvalue ] , EOL , { item } , indent , "End " , subname , ":" , [ " " , subvalue ] , EOL ;
```
Rules a parser must apply: (1) a column-0 line decides block boundaries, never indentation alone; (2) `End:` and
`End Computation Point: ` are the only column-0 terminators; (3) an indented `X:` line with no value is a sub-block opener
if and only if a later `End X:` at the same indent closes it, else it is an empty key (`Time Series Results Manager Start:`
never has an `End`); (4) keys repeat, keep order; (5) key lookup is case-sensitive (`Filename` vs `FileName`); (6) the
value of `Coordinate System` is a single-line WKT string containing colons and brackets, so split on the FIRST ": " only.

### E2. Pathname and time axis of a regular HMS series

For record `/A/B/C/D/E/F/` with interval `E` = dt seconds (5Minute -> 300) and N values read for the whole extent:
```
t_k = t_first + k * dt,     k = 0 .. N-1
INST-VAL (FLOW, STAGE, STORAGE):  value at instant t_k               t_0 = run start (31Dec1999 24:00 = 2000-01-01 00:00), N = 577
PER-CUM  (PRECIP-INC, -EXCESS, -LOSS, INFILTRATION): depth accumulated over (t_k - dt, t_k]   t_0 = start + dt, N = 576
```
Block start date D = first day of the calendar block (one day for 1MIN-12MIN intervals, one month for 15MIN-12HOUR, one
year for 1DAY; DSSVue time-series conventions). The condensed catalog item carries `D = first-last` (`31Dec1999-02Jan2000`),
built by hecdss as: group uncondensed paths by `/A/B/C//E/F/` (lower-cased), sort the D dates, join first and last with "-".
Conversions: DSS "24:00" of day d is Python `datetime(d) + 1 day` at 00:00 (hecdss `DateConverter`); DSS Julian day 0 is
1899-12-31; a missing value is the sentinel -901.0 (DSS 6/7 regular series) and hecdss trims undefined values at both ends.

### E3. Statistics HMS reports, reproduced from the series (checked on S18, 100-yr)

```
Q_peak   = max_k Q_k                                  39.3801 m3/s at k = 148 -> t = 2000-01-01 12:20
V        = sum_k Q_k * dt                             911.631 m3/s * 300 s = 273,489 m3    (HMS "Outflow Volume" 273,489.36 m3)
D_out    = V / A                                      273,489.36 m3 / 1.6696e6 m2 = 163.805 mm (HMS "Outflow Depth" 163.8053 mm)
P_total  = sum_k P_k (PER-CUM)                        205.023 mm   (= area-reduced storm depth, NOTE 23409)
E_total  = sum_k PE_k                                 163.805 mm   (= D_out when baseflow = 0)
ARF(A)   = D_reduced / D_point                        205.023/205.4 = 0.99816 at 1.67 km2;  200.466/205.4 = 0.97598 at 20.0 km2
```
with Q_k the FLOW value at step k (m3/s), dt the control interval (s), A the subbasin area (m2), P_k and PE_k the PER-CUM
precipitation and excess depths of period k (mm), D_point the met model's `Storm Depth` and D_reduced the depth HMS applies
after the `ARF FM` table at the analysis point's drainage area. HMS stamps INST-VAL peaks at the sample time and PER-CUM
maxima at the END of the period (precipitation maximum "01Jan2000, 11:45" is the 11:40-11:45 interval).

### E4. Reading a depth-area analysis at its own analysis points (the proven W1 algorithm)

```
for each return period rp:
    open DA_<rp>_B1.dss; paths = [str(p) for p in catalog.items]
    own = {(B, C): p for p in paths if F.split(">")[-1] == B}        # F = "DAA:<analysis>><point>", keep the point's own storm
    for each element name in the .basin: series = get(own[(name, "FLOW")])
    peak = max; volume = sum * dt; t_peak = argmax * dt
```
A junction's FLOW equals its FLOW-COMBINE where no reservoir exists (verified max |diff| = 0 in W1). Cost: 13 files x 40
series x 5 ms = under 3 s.

### E5. Headless HMS compute (Jython inside HMS's JVM)

```
from hms.model.JythonHms import *
OpenProject("HEC_HMS_Block_02", r"D:\...\HEC_HMS_Block_02")
ComputeRun("FM 100yr")                       # or project.computeDepthAreaAnalysis("DA 100yr B1") via hms.model.Project
SaveAllProjectComponents(); Exit(1)
```
run as `HEC-HMS.cmd -script C:\nospaces\script.py` from the HMS 4.12 folder; completion is detected by polling the
analysis log for "Finished computing" (NOTE 15402) or "Aborted".

## Numbers

| Value | Context | Source |
|---|---|---|
| 111 files, 106,486 canonical `Key: Value` lines, 8,910 headers, 8,854 `End:`, 18,727 blank lines | HMS 4.12 text files on this machine (Block 2, 4, 6 + HEC samples) | grammar_scan.py, this session |
| 110 CRLF / 1 LF; 108 UTF-8 / 3 cp1252; 0 BOM | encodings and line endings of the same 111 files | grammar_scan.py |
| 1,326 / 1,326 | `Latitude Degrees` lines written with two spaces after the colon | grammar_scan.py |
| 62 | `Layer:13`-style lines with no space after the colon | grammar_scan.py |
| 807 | empty-valued keys or sub-block openers (`Time Series Results Manager Start:` 264, `Base Layer:` 112 ...) | grammar_scan.py |
| 31 | column-0 `End Computation Point: ` terminators (the non-`End:` case) | debug_parse.py, survey |
| 17 of 111 | files a naive `End:`-only parser leaves unterminated | grammar_scan.py |
| 1,321 subbasins, 1,073 reaches, 1,182 junctions, 52 reservoirs, 85 sinks, 11 diversions, 0 sources | element inventory of 23 basin models | survey_hms_files.py |
| 1,554 SCS / 12 Initial+Constant / 6 Deficit Constant / 1 Soil Moisture Account / 0 Green and Ampt | `LossRate` values in every basin file on this machine (incl. backups) | grep |
| 18 / 14 / 8 | subbasins / junctions / reaches of Block 2 `Basin 1` (599 km2, 5 dam-site junctions) | Basin_1.basin |
| 5 min, 31 Dec 1999 24:00 to 2 Jan 2000 24:00, 577 values | Control 1 and every result series | Control_1.control, hecdss |
| +14,400,000 ms (Asia/Dubai) / -28,800,000 ms / `America/Los_Angeles` | time zone in .control / .nals / .hms of the same project; DSS records carry none | the three files, hecdss |
| 335 records, 1,076,440 bytes | `FM_100yr.dss`: met output only (PRECIP-INC/PRECIP-CUM, F = `MET:FM 100yr><point>`) | probe_hecdss.py |
| 2,928 records, 7,041,504 bytes, 1,151 condensed items, 15 C parts, 40 F parts | `DA_100yr_B1.dss` | probe_hecdss.py |
| 6 paired-data records | project DSS (5 Percent Graph, 1 Area-Reduction Factor; 145 ordinates each) | probe_hecdss.py |
| 8,390 to 8,940 pathnames, 17.6-20.5 MB | Block 4 met-output DSS files (`FM_<rp>.dss`), F = `MET:` only | binary scan |
| 5,815 pathnames, 13.5 MB, F = `RUN:FM 200yr B2` | Block 4 run DSS file with FLOW results | binary scan |
| 735,049 bytes, 3,562 `StatisticMeasure`, 950 `TimeSeries`, 130 `BasinElement`, 40 `AnalysisPoint` | `results/DAA_DA_100yr_B1.results` | grep |
| 39.3801133 m3/s at 01Jan2000 12:20; 273,489.36 m3; 163.8053 mm | S18 100-yr outflow maximum, volume, depth (XML) = hecdss recomputation | .results, probe |
| 993.5 / 362.4 / 887.1 / 1,356.1 / 1,666.4 m3/s | 100-yr peaks at Faydh 01 / Bidah 03 / R5A / R2A / Z4C from DSS = W1 README | timing script, W1 README |
| 205.4 mm -> 205.023 mm (1.67 km2), 200.466 mm (20.0 km2), 176.798 mm (largest point) | point depth and area-reduced depths, 100-yr | DA_100yr_B1_daa.log |
| 1000 m, 207 m, 2.2 | spillway crest length, crest elevation, coefficient of the Block 6 "Al Ais 10 Reservoir" (`Controlled Outflow`, Main + Auxiliary) | Basin_1___1D___DAM.basin |
| 2 ms / 26 ms / 194 ms (4.9 ms per series) | hecdss open / catalog 1,151 items / 40 x 577 values | timing script |
| 0.1.29 installed, 0.1.33 latest (2026-08-28), Python >= 3.8, MIT, numpy + tzdata | hecdss | PyPI, dist-info |
| 1,877,504 B / 4,305,424 B | `hecdss.dll` / `libhecdss.so` shipped inside the wheel | package listing |
| 7-IS (file, HMS 4.12) / 7-JA (hecdss library) / 7-IV-1 (pydsstools 3.0.0b1) | HEC-DSS library versions | .out, hecdss log, CHANGES.MD |
| 2024-07-31 | end of HEC-DSS version 6 support | hec.usace.army.mil/software/hec-dss |
| 3.1.0, 2026-06-06 | latest pydsstools; DSS-6 reads Windows-only | CHANGES.MD |
| 19 s for 13 analyses (Block 4), 5 s for one (Block 2) | headless HMS depth-area computes via Jython | Block 04 W6 README, W1 hms log |
| 391 / 64 characters | DSS pathname / part length limits | DSSVue UM general concepts |

## Recommendation for Wadi2D

1. **Write our own reader, `wadi2d.io.hms`, in two layers, and do not adopt hms-commander.** Layer 1 is a lossless
   tokenizer: every line becomes (indent, key, raw separator, value) or a header/terminator, blocks are an ordered
   multimap, sub-blocks are recognised only by their `End X:` partner, and `End Computation Point: ` is a terminator.
   Emitting layer 1 must reproduce every one of the 111 files byte for byte; that is the first test. Layer 2 is typed:
   `Project`, `Basin` (elements in file order; `Subbasin` with `Loss`, `Transform`, `Baseflow` variant objects keyed by
   the selector values of finding 6; `Reach` with `Route` variants; `Reservoir` with `Spillway`/`Conduit`/`Pump`
   sub-objects; `Junction`, `Sink`, `Diversion`), `Met` (`HypotheticalStorm`, `WeightedGages`, `SpecifiedAverage`,
   `GriddedPrecipitation`), `Control`, `Run`, `DepthAreaAnalysis`, `PairedTable`, `Grid`, `Gage`. Unknown keys and
   unknown selector values are kept raw and reported, never dropped, so a Block 6 2D subbasin or a future HMS 4.14 key
   does not crash the import. Units are resolved once from `Unit System` into SI at the typed layer.
2. **Geometry comes from the Spatialite file, not the `.basin`.** Read `subbasin2d` (polygons, the masks of decision 5),
   `reach2d` (lines) and `outlet` with sqlite3 + a WKB decoder (shapely or GDAL, both already used in QGIS workflows);
   the `.basin` only gives icon positions.
3. **Use `hecdss` for DSS, wrapped.** Official, MIT, ctypes-only, on this machine, 5 ms per series. The wrapper must:
   refuse to open a path that does not exist (the constructor creates files), open copies when the caller asks for
   read-only safety on a modeller's file, call `set_global_debug_level(1)` once, resolve a series from the condensed
   catalog by (B, C, F) rather than by typing a D part, and convert PER-CUM period-ending stamps to Wadi2D's
   period-start convention explicitly. Keep `pydsstools` as the documented fallback for a DSS 6 file on Windows and for
   grids; do not make it a dependency. Reject the Java/pyjnius route (hms-commander, ras-commander) for reading: it
   needs an HMS or DSSVue install and a JVM for what two DLLs do.
4. **Peaks and volumes: read the XML, verify from the series.** For depth-area analyses parse
   `results/DAA_<name>.results` (`StatisticMeasure` per element per analysis point, with the DSS pointers) and assert
   equality with the recomputed series statistics (E3); for plain runs recompute from DSS and treat a `RUN_*.results`,
   if HMS 4.12 writes one, as a bonus to verify, not a dependency. Ignore `.out`; parse `*_daa.log` only for the storm
   area and the area-reduced depth per analysis point, which are the ARF audit trail reviewers will ask for.
5. **Do not write HMS files from Wadi2D** in version 1. The byte-exact emitter exists for the round-trip test and for a
   future "export to HMS" only; HEC warns that externally edited files can desynchronise the project.
6. **Test strategy against the real project.** Fixtures: a copy of the Block 2 project minus `terrain/` (text files
   100 KB; DSS 1-8 MB each; `.results` 0.7 MB; the 13 DAA DSS files total 92 MB, below the 100 MB GitHub rule) and the
   four HEC samples (castro, tenk, tifton, river_bend; licence to confirm before redistribution). Tests, in order:
   (a) byte-exact round trip of all 111 text files through layer 1; (b) typed->text->typed idempotence and a
   normalised diff that lists exactly the three known irregularities and nothing else; (c) schema: every `Downstream`
   target exists, no cycles, one outlet per basin, subbasin areas sum to 599.3 km2, every `Reduction Table Name` and
   `Pattern Name` resolves to a `.pdata` table whose DSS record exists; (d) DSS: record counts 335/2,928/6, 40 own-point
   FLOW series per DAA file, peaks equal the XML `Outflow Maximum` to 1e-6 relative and volumes/depths to 1e-6, the
   five dam-site peaks equal the W1 table; (e) the hydrology gate of decision 6 test (a): Wadi2D's lumped engine fed with
   the parsed model reproduces the 40 x 13 HMS peaks within the tolerance the design note sets; (f) regression on demand:
   re-run an analysis headless through the Jython route (E5) and diff the new `.results` against the fixture, so a
   modeller's change to the HMS project is caught before it silently changes a Wadi2D comparison.
7. **Reject** reading `Canvas X/Y` as geometry, inferring units from key names, dict-of-first-occurrence parsing, D-part
   typing by hand (`01Jan2000` vs `31Dec1999-02Jan2000` vs `5MIN` vs `5Minute` all exist), and any reliance on the
   project/control time-zone fields.

## Open issues

- Keys of the methods no project on this machine uses (Green and Ampt, Smith Parlange, Exponential losses; Kinematic
  Wave and Straddle Stagger routing; the Muskingum-Cunge 8-point cross-section of decision 8; Source elements; `Dam Top`
  overflow of a reservoir): to be captured from a throw-away HMS project built in the GUI, then added to the fixtures.
- Whether HMS 4.12 writes `results/RUN_<name>.results` after a completed simulation run (Block 2 has none because the
  runs were never computed; Block 4's `FM_200yr_B2` run should be checked in its `results/` folder).
- The exact storage of a manual-entry gage ("a DSS file named after the gage" per the manual) and its pathname.
- hecdss issue #55 (truncation of long regular series with missing blocks) closed without a stated fix; irrelevant for
  48 h event files, relevant for continuous or observed-event (Cyclone Shaheen) series. Verify with a multi-month file
  before relying on `get()` for long records; the Jython `get(path, True)` route is the control.
- Licence of HEC's sample projects for redistribution in Wadi2D's test fixtures (US Government work, presumably public
  domain, not stated in samples.zip).
- HMS 4.13 (July 2025) and 4.14 (September 2026) are installed or released; the files here are all `Version: 4.12`.
  Grammar drift between versions is unmeasured; the round-trip test should run on a 4.14 re-save of the Block 2 project.
- The HMS 2D subbasin mesh (`File: Basin_1_-_2D.hdf`, Block 6) and the `.hdf` layout are unparsed; relevant only if
  Wadi2D ever imports an HMS 2D setup.
- WebSearch quota ran out mid-task; the HMS Jython API reference page (`hms.model.JythonHms`) and the HMS 4.x release
  note that introduced DSS 7 output were not read; both facts are covered by direct evidence (working scripts; `7-IS`
  files) rather than by the manuals.

## Sources

1. file:///D:/Mojtaba/Renardet/2224%20WS11/Batinah/Block%202/Hydrology/HEC_HMS_Block_02/ - the Block 2 HMS 4.12 project:
   `HEC_HMS_Block_02.hms`, `Basin_1.basin`, `Control_1.control`, 13 `FM_*.met`, `.run`, `.pdata`, `.grid`, `.terrain`,
   `.nals`, `.out`, `*_daa.log`, `FM_PMP.log`, `results/DAA_*.results`, `Basin_1.sqlite` (read only) - grammar, keys,
   pathnames, peak summaries, geometry tables. Primary (files written by HEC-HMS).
2. Copies of `FM_100yr.dss`, `DA_100yr_B1.dss`, `HEC_HMS_Block_02.dss` in the scratchpad, read with hecdss 0.1.29 and a
   binary pathname scan - catalog structure, units, data types, time stamps, paired data, timing. Primary.
3. `C:\Program Files\HEC\HEC-HMS\4.12\samples.zip` (castro, tenk, tifton, river_bend; extracted to the scratchpad) -
   reservoirs, sinks, diversions, gages, Weighted Gages / Specified Average / Gridded met models, Modified Puls, Muskingum,
   Lag, Snyder, Clark, ModClark, Soil Moisture Accounting, Computation Point blocks. Primary (HEC-authored files).
4. Block 4 (`...\Block 4\Hydrology\HEC_HMS_Block_04`) and Block 6 (`...\HMS\B6\60 HMS_Block_6_Mod1`) HMS projects -
   `RUN:` F parts in a computed run file, reservoirs with Modified Puls and Controlled Outflow spillways, 2D Diffusion
   Wave subbasin, diversions. Primary.
5. file:///D:/Mojtaba/Renardet/2224%20WS11/Batinah/Block%202/Claude%20Block%2002/W1/ (README, `scripts/01_extract_b1.py`,
   `config.py`, `basinfile.py`, `hms/hms_b2_pmp.log`) and Block 04 `scripts/hms_compute_all.py` - the proven extraction
   algorithm, the dam-site peaks, the headless Jython compute recipe, the PMP unit incident. Primary (working code and logs).
6. file:///C:/Users/mojtaba/AppData/Local/Programs/Python/Python312/Lib/site-packages/hecdss/ (`hecdss.py`, `catalog.py`,
   `dsspath.py`, `dateconverter.py`, `regular_timeseries.py`, `native.py`, `hec_dss_native-readme.md`, dist-info
   METADATA) - the installed hecdss API, time-window and time-zone handling, condensed catalog algorithm, DLL loading.
   Primary (library source).
7. https://github.com/HydrologicEngineeringCenter/hec-dss-python - README: scope, DSS 7 only, MIT, examples. Primary.
8. https://pypi.org/project/hecdss/ - versions and dates, Python requirement. Primary.
9. https://github.com/HydrologicEngineeringCenter/hec-dss-python/issues?q=is%3Aissue , /issues/54 , /issues/55 ,
   /issues/60 , /issues/67 - D-part, truncation, v6 migration, HMS results extraction, whitespace sensitivity. Primary.
10. https://www.hec.usace.army.mil/software/hec-dss/ - DSS 7 recommended, v6 support ended 2024-07-31, v7 library can
    read v6 files. Primary (HEC).
11. https://www.hec.usace.army.mil/confluence/dssdocs/dssvueum/introduction/time-series-conventions - A-F parts, block
    lengths per interval, data types, end-of-period convention, irregular series. Primary (HEC).
12. https://www.hec.usace.army.mil/confluence/dssdocs/dssvueum/introduction/general-concepts-for-hec-dss - pathname
    limits (391/64), record types, condensed catalog, grids in UTC. Primary.
13. https://www.hec.usace.army.mil/confluence/dssdocs/dssvueum/introduction/paired-data-curve-data-conventions - paired
    data parts and scale types. Primary.
14. https://www.hec.usace.army.mil/confluence/dssdocs/dssvueum/display-and-editing/setting-the-time-zone - records
    without a time zone are displayed ignoring time-zone settings. Primary.
15. https://www.hec.usace.army.mil/confluence/dssdocs/dssvueum/scripting/reading-and-writing-to-hec-dss-files - the
    Jython DSS API (`HecDss.open`, `get(path, True)`, catalog patterns, time windows, `TimeSeriesContainer`). Primary.
16. https://www.hec.usace.army.mil/confluence/hmsdocs/hmsum/latest/projects-and-control-specifications/directories-and-files
    - the file-extension table, project vs simulation DSS files, underscore naming, the warning against external editing.
    Primary (HEC-HMS User's Manual 4.14).
17. https://www.hec.usace.army.mil/confluence/hmsdocs/hmsum/latest/data-storage-in-hec-dss/descriptors - the C-part
    descriptor table (FLOW, FLOW-COMBINE, FLOW-BASE, FLOW-DIRECT, FLOW-DIVERSION, FLOW-LOCAL, FLOW-RESIDUAL, PRECIP-INC,
    PRECIP-EXCESS, PRECIP-LOSS, INFILTRATION, STORAGE, ELEVATION). Primary.
18. https://www.hec.usace.army.mil/confluence/hmsdocs/hmsum/latest/shared-component-data/time-series-data - gage types,
    data sources, manual-entry storage, 24:00 rule, units labels, "arbitrary local time zone". Primary.
19. https://www.hec.usace.army.mil/confluence/hmsdocs/hmsum/latest/projects-and-control-specifications/control-specifications
    - date/time formats, interval range, no limit on steps. Primary.
20. https://www.hec.usace.army.mil/confluence/hmsdocs/hmsum/latest/depth-area-reduction/depth-area-analyses - analysis
    points, storm area = drainage area, allowed met methods. Primary.
21. https://www.hec.usace.army.mil/confluence/hmsdocs/hmsum/latest/scripting and
    https://www.hec.usace.army.mil/confluence/hmsdocs/hmsum/latest/hydrologic-simulation/computing-results-for-a-run -
    Jython/Java API existence, incremental recompute. Primary, thin.
22. https://www.hec.usace.army.mil/software/hec-hms/documentation.aspx - HMS versions and dates (4.12 May 2024, 4.13 July
    2025, 4.14 September 2026), release-note URLs. Primary.
23. https://raw.githubusercontent.com/gyanz/pydsstools/master/CHANGES.MD ,
    https://pydsstools.readthedocs.io/en/stable/topics/timeseries.html ,
    https://raw.githubusercontent.com/gyanz/pydsstools/master/docs/source/installation.md ,
    https://github.com/gyanz/pydsstools - pydsstools versions, API, DSS 6/7 support, build requirements. Primary (project docs).
24. https://raw.githubusercontent.com/gpt-cmdr/hms-commander/main/hms_commander/_parsing.py and
    https://hms-commander.readthedocs.io/en/latest/data_formats/{overview,basin_file,gage_file,met_file,dss_integration}/ -
    a third-party parser's regexes and format pages, used to show what a regex approach loses and which documented keys
    do not match real files. Secondary.
