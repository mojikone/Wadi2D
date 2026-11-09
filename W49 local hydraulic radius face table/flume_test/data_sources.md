# Flume data for the wall-shear test: sources (W49 flume_test)

**What we have: three open measured datasets of narrow channels with b/h in the 1-10 band.** They are Lansford & Mitchell (1949), with rough walls and five 5 ft sections including compound ones; Knight, Demetriou & Hamed (1984), smooth rectangular with %SFw; and Al-Hamid (1991), trapezoidal channels with gravel walls, with %SFw. Further open sets are Yuen (1989, smooth trapezoidal) and Tracy & Lester / Cruff (USGS, smooth rectangular, mostly b/h > 7). Knight & Demetriou (1983) K1 was not found in any open table. The FCF Series A data are not online.

Compiled 2026-11-08. All downloads are open access, made with the engineer's permission and without any login. They are stored in `raw/`, one folder per source. Nothing that was downloaded was executed. Text and images were read with PyMuPDF from scripts kept outside `raw/`, run with `python -I`. The CSVs in this folder are transcriptions. Every CSV opens with `#` comment lines giving its source table, page and checks.

## Summary

| Source | Section, walls / bed | b (or 2b) | b/h range | Runs with Q and normal depth | Wall shear | CSV |
|---|---|---|---|---|---|---|
| Lansford & Mitchell 1949, UIUC Bull. 381 | rectangular, wire mesh n~0.019 or chain link n~0.026 on walls and bed; 3 compound | 5.00 ft | 1.6-26 (rect. 1.8-26) | Rect.: 23 (T50) + 38 (T51); compound: 26 (T51) + 9 (T49); ratings for XS2-6; 41 M1 profiles | no | 7 files `lansford_mitchell_1949_*` |
| Knight, Demetriou & Hamed 1984, via Chlebek 2009 | rectangular, smooth | 610, 381, 152, 70 mm | B/H 0.31-19.1 (16 runs in 1-10) | 25 | %SFw, all 25 | `knight_et_al_1984_*` |
| Same 152 mm runs, plus Tominaga 1989, via Sharifi 2009 | rectangular, smooth | 0.152 / 0.40 m | 0.99-8.06 | 6 + 4 (Tominaga Q integrated, not measured) | tau mean only | `knight_1984a_DWK_and_tominaga_*` |
| Al-Hamid 1991, via Sharifi 2009 and Chlebek 2009 | trapezoid 1:1, gravel walls (d84 18 / 9.3 mm) on a smooth bed, or gravel walls and bed | 0.107-0.441 m | 2b/h 0.85-10 | 38 | %SFw, 31 runs | `alhamid_1991_*` |
| Yuen 1989, archived flowdata page | trapezoid 1:1, smooth PVC | 0.044, 0.15, 0.45 m | 2b/H 0.30-15 (43 runs in 1-10) | 56 (S0 1-23.4 ‰, Fr 0.39-3.6) | no (files lost) | `yuen_1989_*` |
| Tracy & Lester 1961, USGS WSP 1592-A | rectangular, smooth steel | 3.5 ft | 7.0-40 | 49 (24 sub-, 25 supercritical) | no | `tracy_lester_1961_*` |
| Cruff 1965, USGS WSP 1592-B | rectangular, smooth | 3.49 / 1.99 ft | 4.7-38 | 26 (21 = T&L runs, 5 new) | figures only | `cruff_1965_*` |
| Spada et al. 2015, HESS | FCF F2 and K&D K4 compound | - | - | 7 + 6 | no | `spada_2015_*` |

The test's priority targets are these four:
- **L&M cross-sections 2 and 4:** a homogeneous rough perimeter, b/h 1.8-12.8.
- **Knight et al. 1984:** smooth, with measured %SFw.
- **Al-Hamid:** rough walls on a smooth bed, with %SFw, the case where the wall term matters most.
- **Yuen:** a smooth trapezoid at three widths.

---

## 1. Knight & Demetriou (1983), the K series

- **Citation.** Knight D.W. & Demetriou J.D. (1983) Flood plain and main channel flow interaction. J. Hydraul. Eng. 109(8):1073-1092, doi:10.1061/(ASCE)0733-9429(1983)109:8(1073).
- **Status.** Not obtained. The paper is behind the ASCE paywall. NTUA's repository holds the record with no file (https://dspace.lib.ntua.gr/xmlui/handle/123456789/22232). No open thesis with the K-series tables turned up.
  - Searches covered etheses.bham.ac.uk (by title and by "Shiono Knight"), the archived flowdata site, and Spada's preprint, final paper and revised manuscript.
- **What is open instead:**
  - [Likely] K1, the plain 152 mm rectangular channel at S0 = 0.966e-3, is the same apparatus as the 152 mm channel of Knight et al. (1984) in §2. Same width, same slope, same Birmingham flume. Its 7 runs (exps 15-21, H = 76-153 mm) are in `knight_et_al_1984_*.csv`.
  - Spada et al. (2015) Table 2 gives the measured H-Q of K4, a compound section with 6 runs (§8).
- **Inconsistency in Spada's Table 1.** The text says K1 is "simply rectangular", yet the table prints 0.229 m flood plains for K1 and "-" for K4. K4's own data prove it is compound: 29 l/s at H = 0.154 m, against 9.85 l/s in the plain 152 mm channel at 0.153 m. So the table's b1/b3 column is [Likely] in reverse row order.

## 2. Knight, Demetriou & Hamed (1984): smooth rectangular, with %SFw

- **Citation.** Knight D.W., Demetriou J.D. & Hamed M.E. (1984) Boundary shear in smooth rectangular channels. J. Hydraul. Eng. 110(4):405-422, doi:10.1061/(ASCE)0733-9429(1984)110:4(405).
  - The paper is paywalled. The data come from the open thesis below.
- **Source used.** Chlebek J. (2009) *Modelling of simple prismatic channels with varying roughness using the SKM and a study of flows in smooth non-prismatic channels with skewed floodplains.* PhD thesis, University of Birmingham.
  - Record: https://etheses.bham.ac.uk/id/eprint/688/
  - PDF: https://etheses.bham.ac.uk/id/eprint/688/1/Chlebek09PhD.pdf
  - Open on Birmingham eTheses, which displays "Preview / PDF Download".
- **Downloaded.**
  - `raw/chlebek_2009_bham_phd/Chlebek09PhD.pdf` (18,297,609 B, 506 pp.)
  - `eprint688_record.txt`, the repository citation export.
- **Where the data are:**
  - Table 3.1, thesis p. 3-33 (PDF p. 142): the data.
  - Section 3.2.1, p. 3-3 (PDF p. 112): the apparatus.
- **Apparatus.** A 15 m tilting flume, 610 mm wide, holding inner channels 381, 152 and 70 mm wide; S0 = 9.66e-4. Velocity was measured in all channels; boundary shear stress only in the 152 mm channel.
- **Quantities.** 25 runs, each with:
  - B, b = B/2 and H (normal depth);
  - Pb/Pw = B/2H;
  - Q (l/s and m³/s), U and tau_e = rho g R S0;
  - **%SFw**, the wall share of the total boundary shear force;
  - f.
  - Ranges: B/H 0.31-19.1 (16 runs inside 1-10), %SFw 6.9-85.2 %.
- **Transcription.** Parsed from the PDF text layer and checked against the page image.
  - By script: U = Q/(BH) within 0.5 %, tau_e = rho g R S0 within 0.5 %, f = 8gRS0/U² within 1 %, Pb/Pw = B/2H. All 25 rows pass.
  - Two source errors are kept as printed and noted in the CSV:
    - the slope column is headed "x10^-3" but is ×10^-4;
    - Q in m³/s for exps 15-16 repeats exps 13-14. The l/s values are right.
- **Cross-check.** Sharifi (2009) Table 5-12 (§4) lists 6 of the 152 mm runs as DWK 01-06, all matching.
- **Not open.** Patel's (1984) air-duct data and Rhodes & Knight (1994) are the aspect ratios up to 100 behind the %SFw formula. Patel's flowdata page lists them, but the tables were images that were not archived.

## 3. Lansford & Mitchell (1949): 5 ft flume, rough walls, M1 profiles

- **Citation.** Lansford W.M. & Mitchell W.D. (1949) *An investigation of the backwater profile for steady flow in prismatic channels.* Univ. of Illinois Engineering Experiment Station Bulletin 381 (with the USGS), 96 pp.
  - Record: https://hdl.handle.net/2142/4227 (IDEALS item 4822)
  - PDF: https://www.ideals.illinois.edu/items/4822/bitstreams/18866/data.pdf
- **Downloaded.** `raw/lansford_mitchell_1949_uiuc_bull381/UIUC_EES_Bulletin381_Lansford_Mitchell_1949.pdf` (14,935,248 B, 108 PDF pp.; a scan with a poor text layer).
- **Licence.** IDEALS states "Copyright 1949 Board of Trustees University of Illinois". It is openly downloadable without login.
- **Page offset.** Bulletin page + 6 = PDF page in the text part. In the tables part, bulletin page + 8 = PDF page.
- **Apparatus (pp. 7-14, Fig. 4 on p. 14 / PDF p. 20).**
  - Concrete channel 5.00 ± 0.05 ft wide, 163.7 ft long, with a plank false floor at S0 = 0.003. Depth was read by point gauges on the centre line, 10 gauges at 15 ft (XS1-4) or 14 at 10 ft (XS5-7). Discharge came from elbow meters, calibrated volumetrically and by current meter.
  - Roughness materials:
    - a = 2×4 in No. 12 wire mesh, n ~ 0.019;
    - b = 2 in chain link with triangular wooden strips every 6 in, n ~ 0.026;
    - c = smooth concrete, n ~ 0.011.
  - Cross-sections:
    - XS1: bed a, walls a up to 1.5 ft, c above.
    - **XS2: a all round.**
    - XS3: bed a, walls a up to 1.5 ft, b above.
    - **XS4: b all round.**
    - XS5-7: compound. A 1.00 ft × 1.00 ft main channel with 2.00 ft flood plains rising from 1.00 to 1.20 ft at the wall. Walls a (XS5), a up to 1.5 ft then c (XS6), or c (XS7).
  - All of this is in `lansford_mitchell_1949_cross_sections.csv`.
- **Data and CSVs.**

  | Table | Content | Bulletin pages (PDF pages) | CSV |
  |---|---|---|---|
  | 1-41 | M1 backwater profiles: stations and gauge depths per run, a "normal depth readings, no backwater" row, and backwater-gate settings | 39-80 (47-88) | headers only: `..._profile_tables_T1-41_headers.csv` |
  | 42-46 | Normal depth-discharge ratings, XS2-6, every 0.01 ft from 0.1 (or 0.4) to 4.0 ft | 81-85 (89-93) | `..._ratings_T42-46.csv` (tenths and DIFF), `..._curvilinear_hundredths.csv` |
  | 49 | Pitometer measurements, XS5-7 (in-bank flow) | 88 (96) | `..._T49_pitometer.csv` |
  | 50 | Current-meter discharges with the normal depth (rectangular sections) | 89 (97) | `..._T50_current_meter.csv` |
  | 51 | Simultaneous normal depth and elbow-meter discharge (all sections) | 90-91 (98-99) | `..._T51_normal_depth_observations.csv` |
  | 47-48, 52 | Elbow-meter ratings; current-meter details | 86-87, 92-94 | not transcribed |

- **Ranges.**
  - Measured y_n runs from 0.19 to 3.17 ft, Q from 0.75 to 49.9 cfs.
  - The rectangular sections cover b/h 1.8-26: XS1/XS2 2.7-12.8 (26 at the shallowest current-meter run, y_n 0.192 ft), XS3 2.1-12.4, XS4 1.8-9.5.
  - **The independent measured pairs are Tables 49-51. The discharge in each profile header (Tables 1-41) is the rating value at y_n, not a measurement.** The script reproduces all 41 headers from Tables 42-46 within 0.5 %. For XS1 the authors used the XS2 rating, even above 1.5 ft.
- **Rating caveats.** The ratings are smoothed curves. The source says they rest on these numbers of current-meter series plus simultaneous observations:

  | Rating | Current-meter series | Simultaneous observations |
  |---|---|---|
  | XS2 | 14 | 10 |
  | XS3 | 7 | 14 |
  | XS4 | 1 | 13 |
  | XS5 | 8 | 20 |
  | XS6 | 8 | 14 |

  - Above about 50 cfs the ratings are extrapolated; the CSV header gives the highest measured depth per section.
- **Checks on the transcription:**
  - Consecutive tenth values match the printed DIFF, within rounding above 50 cfs.
  - The hundredths in the curvilinear ranges are monotonic and start at the tenth value.
  - The printed "% variation from rating" in Tables 49-51 is reproduced from Q / Q_rating(y_n) for every row but two. One is rounding: T51 "aw" computes 0.0 % against a printed -0.1 %, because the rating is rounded above 50 cfs. The other is Table 50 series 22 (below).
- **Open points:**
  - Table 50 series 22 (Feb. 25, 1947, section "2'", y_n 1.874 ft, Q 39.9 cfs) prints -0.5 %. The XS2 rating gives -3.6 %, and the meaning of "2'" and "2',3" (1947) is not stated in the text. [Likely] it is XS2's mesh relaid in 1947.
  - At the same depth (~0.6 ft) XS3 carries about 5 % less than XS2 (7.37 against 7.99 cfs), although both should be wire mesh "a" below 1.5 ft. This is a real difference between the 1945 and 1947 installations, not a transcription error.
- **Not transcribed.** The M1 profile bodies of Tables 1-41: about 41 tables of stations and 10-14 gauge depths per run, several thousand numbers. They are clean scans and can be done per profile when a gradually-varied-flow test needs them. Each table also has the normal-depth row, which shows how uniform the flow was along the flume.
- **Companion, downloaded but not transcribed.** Mitchell W.D. (1954) *Stage-fall-discharge relations for steady flow in prismatic channels.* USGS Water-Supply Paper 1164, https://pubs.usgs.gov/wsp/1164/report.pdf.
  - Stored as `raw/usgs_wsp1164_mitchell_1954/wsp1164_report.pdf` (3,289,085 B, 170 pp.); public domain.
  - It re-analyses the same channels: step-method profile tables and conveyance values. No new measurements.

## 4. Al-Hamid (1991): trapezoids with gravel-roughened walls

- **Original.** Al-Hamid A.A.I. (1991) *Boundary shear stress and velocity distributions in differentially roughened trapezoidal open channels.* PhD thesis, Univ. of Birmingham. Not online. Its flowdata page is archived but the data tables, all images, were not captured.
- **Sources used:**
  - **Sharifi S. (2009)** *Application of evolutionary computation to open channel flow modelling.* PhD thesis, Univ. of Birmingham.
    - PDF: https://etheses.bham.ac.uk/id/eprint/478/1/Sharifi09PhD.pdf
    - Stored as `raw/sharifi_2009_bham_phd/Sharifi09PhD.pdf` (5,921,209 B, 330 pp.).
    - Table 5-5, thesis p. 5-17 (PDF p. 172), lists all 38 runs. Table 4-2, p. 4-9 (PDF p. 137), gives the dataset summary.
  - **Chlebek (2009)** (§2) supplies %SFw:
    - Table 4.1, p. 4-16 (PDF p. 175): 26 runs with a smooth bed and rough walls.
    - Table 4.8, p. 4-22 (PDF p. 181): 5 runs with roughness all round.
- **Apparatus.** 1:1 trapezoids built in PVC inside a 22 m × 0.615 m tilting flume.
  - Gravel R1 (d84 = 18.0 mm) or R2 (d84 = 9.3 mm), on the walls only (smooth bed) or on bed and walls.
  - S0 = 3.92e-3, 1.935e-3 and 4.03e-3; 2b/h 0.85-10; Fr 0.39-0.89.
- **Quantities.** 2b, h, 2b/h, Pb/Pw, S0, Q, R, U, tau mean, Re, Fr, and %SFw for 31 of the 38 runs.
- **Checks.**
  - R and U agree with a 1:1 trapezoid within 2 % for every run (depth is to the gravel datum).
  - h and Q agree between the two theses on every common run.
- **Caveat.** These are rough-wall cases, so a local-hydraulic-radius face table must carry a wall roughness different from the bed. That is the case the Spada form is meant for.

## 5. Yuen (1989): smooth trapezoid, three widths

- **Original.** Yuen K.W.H. (1989), PhD thesis, Univ. of Birmingham. Not online.
- **Source used.** The summary list on the Birmingham "flowdata" site, as archived by the Internet Archive:
  - http://web.archive.org/web/20070612132639/http://www.flowdata.bham.ac.uk:80/yuen/sum.htm
  - Saved as `raw/flowdata_bham_wayback/yuen_sum_20070612132639.htm` (82,815 B), with the site's data page `yuen_data_20070612182444.htm`.
- **Quantities.** 56 simple-channel runs: S0, bed width 2b, H, 2b/H, Q, Re, Fr and file name.
  - 1:1 smooth PVC trapezoid in a 22 m flume.
  - S0 = 1.000, 3.969, 8.706, 14.52 and 23.37 ‰ (sub- and supercritical).
  - 2b = 0.044, 0.15 and 0.45 m; 2b/H 0.30-15.
  - The same page lists the compound-channel runs; those are not put in the CSV.
- **Parsing and checks.** Parsed programmatically from the HTML, with no hand typing.
  - Fr recomputed from Q, H and the 1:1 geometry matches all 56 rows within 1 % except run 208. Run 208 prints H = 0.0449 m, but its listed 2b/H (10.23) and Fr (2.1934) both give H = 0.044 m. [Likely] a typo; it is flagged in the CSV `note` column.
  - Sharifi Table 5-3 (17 of the runs) agrees.
- **Lost.** The per-run boundary-shear and velocity files (`ssum/sres/sdata*.zip` at www.eee.bham.ac.uk/flowdata/yuen/) are not in the archive (§9).

## 6. Tracy & Lester (1961): smooth rectangular, USGS

- **Citation.** Tracy H.J. & Lester C.M. (1961) *Resistance coefficients and velocity distribution, smooth rectangular channel.* USGS Water-Supply Paper 1592-A.
  - https://pubs.usgs.gov/wsp/1592a/report.pdf, doi:10.3133/wsp1592A. Public domain (US Government).
- **Downloaded.** `raw/usgs_wsp1592A_tracy_lester_1961/wsp1592A_report.pdf` (551,050 B, 23 pp.).
- **Data.** Tables 1 and 2, p. A-10 (PDF p. 15). The flume is described on p. A-5.
  - 49 runs (24 subcritical, 25 supercritical) in a smooth steel tilting flume 3.5 ft wide.
  - Each run gives Q, y0 (normal depth from bracketing profiles), S0, T, nu, f, Re and F.
  - b/y0 runs from 7.0 to 40, so only 15 runs fall at b/h ≤ 10.
- **Checks.** Hand transcribed and re-read at 320 dpi.
  - 38 rows reproduce F, f and Re from Q, y0, S0 and nu.
  - 11 rows differ by 1-4 % inside the source itself (listed in the CSV header). Run 31 is the largest: F is printed 2.20, while Q and y0 give 2.11.

## 7. Cruff (1965): the same flume plus a 2 ft channel, with wall and bed shear

- **Citation.** Cruff R.W. (1965) *Cross-channel transfer of linear momentum in smooth rectangular channels.* USGS Water-Supply Paper 1592-B.
  - https://pubs.usgs.gov/wsp/1592b/report.pdf. Public domain.
- **Downloaded.** `raw/usgs_wsp1592B_cruff_1965/wsp1592B_report.pdf` (648,481 B, 33 pp.).
- **Data.** Table 1, p. B10 (PDF p. 17): 26 tests, each with B, U, y0/B, gamma·y0·S0 and Re.
  - Tests 1-21 are Tracy & Lester runs, matched by Re within 0.5 % with U agreeing within 1 %.
  - Test 22 is new: 3.49 ft wide, B/y0 = 4.7.
  - Tests 23-26 are new, in a 1.99 ft wide, 0.4 ft deep rectangular channel formed by an overbank insert: B/y0 = 5.1-20.
  - The CSV derives y0, Q and S0 from these.
- **Bonus, not transcribed.** Wall and bed boundary-shear distributions, by Preston tube and log law, are in Figs. 5-23. They are figures only.

## 8. Spada et al. (2015): the LHRM paper itself

- **Citation.** Spada E., Tucciarelli T., Sinagra M., Sammartano V. & Corato G. (2015) Computation of vertically averaged velocities in irregular sections of straight channels. Hydrol. Earth Syst. Sci. 19:3857-3873, doi:10.5194/hess-19-3857-2015. CC BY 3.0.
- **Downloaded** to `raw/spada2015_hess/`:
  - `hess-19-3857-2015.pdf` (7,186,554 B), the final paper;
  - `hessd-12-2607-2015.pdf` (3,588,760 B), the HESSD preprint;
  - `hessd-12-C860-2015-supplement.pdf` (3,151,714 B), the authors' revised manuscript posted in the discussion. It contains no extra data.
- **Data, final paper:**
  - Table 1 (p. 3861): series geometry. In `spada_2015_hess_T1_series_geometry.csv`; merged cells are repeated on every row.
  - Table 2 (p. 3862): measured H and Q for FCF F2 (7 points, 0.156-0.249 m) and K4 (6 points). In `spada_2015_hess_T2_F2_K4_stage_discharge.csv`. K4's Q is given to 0.001 m³/s only, so its points carry up to 10 % rounding.
- **What Spada did not publish.** No other series data. Their FCF calibration set was F1, F2, F3 and F6; validation used F2, F8, F10 and K1-K4. K1, the rectangular case, is not tabulated in either version of the paper.

## 9. FCF and the Birmingham "flowdata" site

- **Site status.** www.flowdata.bham.ac.uk no longer resolves in DNS. A 2022 capture of `fcf-data.shtml` redirects to the University home page.
- **What the Internet Archive holds.**
  - It holds the site's HTML pages from 2007-2008: data descriptions for FCF Phase A, Yuen, Al-Hamid, Patel and others.
  - The data themselves were zip files on a second host, `www.eee.bham.ac.uk/flowdata/...`, for example FCF Phase A `sum01-11.zip`, `res*.zip`, `bv*.zip` and `exp*.zip`. The Archive's prefix query for that host returned no captures. A domain-wide query timed out, so [Likely] they were never archived, but that is not certain.
  - Downloaded for the record into `raw/flowdata_bham_wayback/`: `FCFA_data_*.htm` (lists the lost FCF files), `alhamid_data_*.htm` and `patel_data_*.htm`.
- **FCF F1, F2, F3 and F6 were Spada's calibration set.**
  - The only open FCF numbers found are Spada's 7 F2 points (§8).
  - The University of Bristol research portal lists the SERC FCF test data reports (Sellin; Phase A and Series B43-B48) as publication records. They were seen only in search results and were not opened; no download was found.
- **Not tried, and needing the engineer's call.** Writing to Prof. Knight's group, HR Wallingford or the Bristol archive for the FCF Series A files.

## 10. Downloaded but not used

`raw/jesson_2012_bham_phd/Jesson12PhD.pdf` is Jesson M.A. (2012), *The effect of heterogeneous roughness on conveyance capacity and application to the Shiono-Knight method*, PhD thesis, Univ. of Birmingham (https://etheses.bham.ac.uk/id/eprint/3240/; 17,706,121 B, 336 pp.).
- Its roughness changes across the bed (rough and smooth halves), not between wall and bed.
- It has few runs (Table 9, p. 140, "Configuration and flow properties").
- It is low relevance to the wall-shear test and was not transcribed.

## Scripts and how to reproduce

The transcriptions and their checks live in scripts outside the project, in the session scratchpad:
- `lm_build.py`
- `bham_build.py`
- `usgs_build.py`
- `pdftext.py`, `stack.py` and `htmltxt.py`, which extract text and images.

The scratchpad is `C:\Users\mojtaba\AppData\Local\Temp\claude\0411bb1eda7ca588\563cf3f8-070b-42eb-82ea-489205b14695\scratchpad\`. **It is temporary and will be lost when the session is cleaned.** If the CSVs are to stay reproducible, the scripts should be copied into this folder; that was not done here, because the brief limited writes outside `raw/` to this note and the CSVs.

Unit conversions in the derived columns use 1 ft = 0.3048 m and 1 cfs = 0.028316846592 m³/s.
