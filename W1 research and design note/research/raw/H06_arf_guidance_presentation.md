# H06 Areal reduction factors: fixed-area versus storm-centred, arid-region practice, presentation to reviewers

Date: 2026-10-29

## Scope

What this file answers, for the Wadi2D design note (decision 9 of `CLAUDE.md`, "ARF the HMS depth-area way with one shortcut"):

1. What fixed-area and storm-centred ARFs are, how the national standards (NOAA TP-29 / Atlas 14, ARR 2019 Book 2 Chapter 4, UK FSR/FEH) define and derive them, and what Svensson & Jones (2010), Pavlovic et al. (2016) and Asquith (1999) say about return-period and climate dependence.
2. Arid-region ARF values at 24 h for 10-600 km² (Arizona / semi-arid Southwest: NOAA HYDRO-40 and the Maricopa County manual) and what exists for Oman, Saudi Arabia and the UAE.
3. How HEC-HMS depth-area analyses work and how US authorities (FEMA, HEC) expect them presented and documented.
4. The error of interpolating between runs at 6-8 log-spaced storm areas instead of one run per analysis point, computed on three 24-h curves including the project's own `ARF FM` table.
5. Whether the composite map (each cell reads the run matching its own drainage area) has a precedent.
6. How to present one-run-per-storm-area and the composite map to reviewers without new vocabulary.

Method: 19 primary documents read in full or in the relevant chapters (PDF text extracted locally where the fetch returned binary), the project's `ARF Gonu.xlsx` and Block 2 profile read, and a short script (`H06_arf_interp.py`, beside this file) for the arithmetic. The web-search budget of this run was exhausted after about 20 searches; the Saudi/UAE/Oman-specific and TxDOT searches did not run and are listed under Open issues. Wright et al. (2014) was reachable only as an abstract.

Tags: [Certain] read in a primary source or arithmetic on one; [Likely] strong inference or secondary source; [Guessing] gap-filling.

## Findings

1. **Two ARF types exist and they are not interchangeable.** A *fixed-area* (geographically fixed) ARF divides the T-year areal rainfall over a fixed area (a catchment or a circle) by the T-year point rainfall of the same duration; a *storm-centred* ARF divides the areal depth inside an isohyet of one storm by that storm's centre maximum. [Certain] "Note that the ARF defined in this way (Eq. 2) is radically different from that for the storm-centred approach (Eq. 1)." https://nora.nerc.ac.uk/id/eprint/8816/1/N008816PP.pdf

2. **Only fixed-area ARFs carry the frequency of the point rainfall through to the areal rainfall; storm-centred ratios belong to PMP work.** Omolayo's argument, adopted by Svensson & Jones, is that extreme point and extreme areal rainfalls are unlikely to come from the same storm; the review concludes a fixed-area approach gives probabilistically correct areal estimates and the other families do not until their discrepancy is quantified. [Certain] "Storm-centred approaches may be used for probable maximum precipitation (PMP) purposes, because PMP does not have an associated frequency estimate." https://nora.nerc.ac.uk/id/eprint/8816/1/N008816PP.pdf

3. **Storm-centred ratios are systematically lower than fixed-area ARFs**, because they are built from storms with heavy point rainfall (convective, small extent) and the storm centre is rarely inside a fixed boundary. Applied to frequency rainfall this under-states design rainfall. [Certain] "Sivapalan and Blöschl (1998) note that storm-centred ARFs are usually somewhat smaller than geographically fixed ARFs." https://nora.nerc.ac.uk/id/eprint/8816/1/N008816PP.pdf (same statement in USGS WRIR 99-4267, p. 3)

4. **Every national design standard read uses fixed-area ARFs.** TP-29 (US, 1957-58: ratio of means of annual maxima, one 2-yr curve applied to all return periods up to 100 yr), FSR/FEH (UK, 1975, adopted unchanged into FEH), ARR 2019 (Australia: modified Bell's method on hypothetical circular catchments, GEV quantiles of areal and point annual maxima, AEP-dependent). [Certain] "The method adopted for the derivation of areal reduction factors is a modified version of Bell's method" https://www.arr-software.org/pdfs/ARR_190514_Book2_V4.2.pdf ; "TP–29 presents a single curve based on 2-year recurrence intervals. This curve was judged applicable for all return periods up to 100 years." https://pubs.usgs.gov/wri/wri99-4267/pdf/wri99-4267.pdf

5. **ARFs fall with return period, and faster for convective rainfall and in semi-arid climates.** Skaugen (Norway), Allen & DeGaetano (US east), Asquith & Famiglietti (Texas) and Bell (UK) all found ARF decreasing with T; Zehr & Myers found the semi-arid Southwest curves fall much faster than the national average. [Certain] "ARFs for both convective and frontal events decrease with increasing return period, but the rate of decrease for convective events is considerably greater" https://nora.nerc.ac.uk/id/eprint/8816/1/N008816PP.pdf ; "Zehr and Myers (1984) suggest that ARFs decline more rapidly in the semi-arid southwestern United States than in the rest of the country" (same source). Asquith's physical reading: "large storms have (on average) a smaller spatial extent" https://pubs.usgs.gov/wri/wri99-4267/pdf/wri99-4267.pdf

6. **At 24 h the choice of fixed-area method barely matters; at 1 h it matters a lot.** Pavlovic et al. ran four fixed-area methods on one radar dataset (Oklahoma, 2002-2013): at 500 km² and 24 h all gave 0.95-0.96 against TP-29's 0.92; at 1 h TP-29 is 0.1-0.2 lower than any of them; the 2-yr to 100-yr difference at 24 h is 0.02-0.06 at 1000-1500 km², about 0.08 at 1 h. [Certain] "For the 24-h duration, the ARFs from all the four methods were alike for all the area sizes analyzed." https://repository.library.noaa.gov/view/noaa/15277/noaa_15277_DS1.pdf

7. **ARR 2019 fixes the area that the ARF is computed for: the total catchment to each point of interest, never per subarea.** This is the sentence that licenses one-run-per-storm-area and the composite map, and that forbids a single catchment-wide ARF for interior points. [Certain] "the ARF should be computed for the total catchment upstream of each location of interest where a design flood estimate is required" and "The ARF should not be computed independently for each subarea in a runoff-routing model of the catchment of interest" https://www.arr-software.org/pdfs/ARR_190514_Book2_V4.2.pdf

8. **HEC-HMS implements the same rule mechanically: storm area = drainage area at the evaluation point, one storm per point, automated by the Depth-Area Analysis.** The met model's storm area and computation point are overridden by each analysis point's upstream area; results are a Peak Flow Summary table (point, drainage area, peak, time) with per-point time series for the elements upstream of that point only. Supported met methods: Frequency Storm and Hypothetical Storm (point depth or precipitation-frequency grid). [Certain] "Failure to match the storm area to the drainage area can result in significant under or over estimation of the flow." https://www.hec.usace.army.mil/confluence/hmsdocs/hmsum/4.9/depth-area-reduction/depth-area-analyses ; "When there are several evaluation locations in a watershed, separate storms must be prepared for each location." https://www.hec.usace.army.mil/confluence/hmsdocs/hmstrm/meteorology/precipitation/hypothetical-storm ; "The drainage area at each of the user-defined analysis points will replace the storm area" https://www.hec.usace.army.mil/confluence/hmsdocs/hmsum/4.9/meteorology-description/precipitation

9. **HMS applies the ARF per duration inside the nested storm, and limits the built-in curves.** TP-40 curves differ by duration (up to 24 h), TP-49 beyond 24 h; the User-Specified area-reduction function is a paired-data table (area vs factor) interpolated linearly; the built-in curves are not to be used above 400 mi² (1036 km²). [Certain] "TP-40/49 should not be applied to watersheds (total study areas) larger than 400 square miles" https://www.hec.usace.army.mil/confluence/hmsdocs/hmstrm/meteorology/precipitation/hypothetical-storm ; "There are different area-reduction curves for different storm durations." https://www.hec.usace.army.mil/confluence/hmsdocs/hmsum/4.9/meteorology-description/precipitation

10. **US review practice: the ARF must be documented and sourced; Atlas 14 values are point values; NOAA has not yet replaced TP-29.** FEMA's hydrology guidance (Nov 2024) makes the ARF and its source a documentation requirement; Atlas 14 Vol 1 (Arizona) says its estimates are point estimates and points to TR-24, HYDRO-40 and Atlas 2 for ARFs, with an update project announced. [Certain] "The Mapping Partner must document the use of areal reduction factors (or lack thereof)." https://www.fema.gov/sites/default/files/documents/fema_guidance_hydrology_rainfall-runoff_analysis_nov_2024.pdf ; "The precipitation frequency estimates in this Atlas are point estimates, that is, estimates of precipitation frequency at a point location, not for an area." https://www.weather.gov/media/owp/oh/hdsc/docs/Atlas14_Volume1.pdf

11. **Arid-region 24-h values (Arizona, the only published semi-arid fixed-area set found): far below the UK/Australian curves.** HYDRO-40 (Zehr & Myers 1984, station-pair method anchored on Walnut Gulch): at 300 mi² (777 km²) the 24-h ratio is 0.66 in zones B/D (southeast Arizona) and 0.80 in zones A/C, against 0.91 in NOAA Atlas 2. Maricopa County adopts the HYDRO-40 Fig. 15 curve for its 24-h general storm (0.950 at 10 mi², 0.848 at 100 mi², 0.806 at 300 mi², 0.783 at 500 mi²) and the 1954 Queen Creek storm curve for the 6-h local storm (0.94 at 10 mi², 0.80 at 100 mi²). [Certain] "reductions of point rainfalls for area size in the semi-arid Southwest are greater than previously published nationwide average depth-area curves" https://www.weather.gov/media/owp/oh/hdsc/docs/TM40.pdf ; "local storms are characterized by relatively small areas of high intensity rainfall resulting in depth-area reduction curves that decrease rapidly with increasing area" https://www.resolutionmineeis.us/sites/default/files/references/maricopa-county-2011.pdf

12. **HYDRO-40 could not resolve the return-period dependence and froze a mean (2.54-yr) curve, declared conservative for rarer events.** The Maricopa table therefore carries no AEP axis either. [Certain] "Use of a mean curve for all return periods will lead to conservative estimates for all return periods greater than 2.54 yr." https://www.weather.gov/media/owp/oh/hdsc/docs/TM40.pdf

13. **No published ARF study for Oman, Saudi Arabia or the UAE was found.** Searches on the Arabian Peninsula returned convective-climatology papers only; the Oman hits (Al-Rawas thesis, Al-Qurashi et al. 2008 Kineros2, the JICA roads study chapter, Wheater & Bell 1983) concern design storms and spatial variability, not ARF tables, and none was readable in this run (DNS failure, blocked hosts, exhausted search budget). [Certain that nothing was found; Likely that nothing public exists beyond project reports] Source list: https://www.collectionscanada.gc.ca/obj/thesescanada/vol2/002/NR62136.PDF (not reached), https://tucson.ars.ag.gov/unit/publications/pdffiles/1905.pdf (DNS failure)

14. **The Batinah project's `ARF FM` table is a storm-centred depth-area ratio of one event, Cyclone Gonu (June 2007).** The workbook `ARF Gonu.xlsx` is titled "Based on Gonu"; its area column is a set of circles (28.26 = π·3², 78.5 = π·5², ... 7854 = π·50² km²) and its ratios fall to 0.817 at 314 km², 0.673 at 707 km², 0.579 at 1256 km² and 0.222 at 44 042 km², with the fit ARF = 0.19718 + 0.87992/(1 + (A/975.54)^0.76257). The Block 2 profile confirms the table is applied to all 13 frequency storms including the PMP. [Certain for the workbook and its use; Likely that the ratios are mean-depth-inside-circle / centre-depth of Gonu, which is the storm-centred definition of finding 1] "Based on Gonu" `D:\Mojtaba\Renardet\2224 WS11\Batinah\Block 2\Hydrology\HEC_HMS_Block_02\Hydrology Data\XLS\ARF Gonu.xlsx` ; "storm area 300 km², ARF table "ARF FM"" `D:\Mojtaba\Renardet\2224 WS11\Batinah\Block 2\CLAUDE.md`

15. **The Gonu table is of the wrong type for frequency storms (findings 2-3) but its magnitude is not out of line with the Arizona semi-arid fixed-area curve up to about 800 km².** At 259 km² the Gonu fit gives 0.84 against Maricopa's 0.848; at 777 km² it gives 0.68 against HYDRO-40 zone B/D 0.66 (zone A/C 0.80); against the UK FSR and ARR 2019 Inland Arid curves it is 11% lower at 300 km² and 20% lower at 600 km². Beyond 1000 km² it falls far below every published curve (0.59 at 1295 km² against Maricopa 0.783). [Certain, arithmetic on the sources] Values in the Numbers table below.

16. **Interpolating between 6-8 log-spaced storm-area runs is accurate only if you interpolate; snapping to the nearest run is not.** On the FSR and ARR Inland Arid 24-h curves the ARF step between neighbouring nodes is 1.6-2.5% and linear interpolation in ln(A) has a maximum error of 0.03-0.08%. On the project's steep Gonu curve the step is 12-17% and log-linear interpolation still holds the error to 0.46% (6 nodes) / 0.24% (8 nodes); linear-in-area interpolation 1.2% / 0.67%; nearest-node 8.2% / 6.0%. The "~2% between neighbours" remembered in `CLAUDE.md` decision 9 is true for the standard curves, not for the project table. [Certain, computed with `H06_arf_interp.py`]

17. **The cost of one catchment-wide storm area at interior points is large on arid curves.** Using a 600 km² storm area at a 50 km² point under-states rainfall by 5.1% (FSR), 6.1% (ARR Inland Arid) and 27.8% (Gonu table); peaks fall by more than rainfall because losses are nonlinear. A New Zealand case study measured the practical spread: whole-catchment versus subcatchment-scale ARF application changed 100-yr peaks by 14-25% along one stream. [Certain for the rainfall ratios and the NZ numbers; Likely for the flow amplification] "the application of ARF lies in the range 14.2% to 16.7% with largest reduction being at the upper most end of the catchment" https://www.waternz.org.nz/Attachment?Action=Download&Attachment_id=1192

18. **The composite map has a direct precedent in Australian practice, for duration rather than area.** The ARR 2019 ensemble workflow takes the median over temporal patterns per duration and then the cell-by-cell maximum across durations; TUFLOW's `asc_to_asc -max` writes the envelope plus a `_src` grid that names the governing input grid at every cell. Each cell reading the run matching its own drainage area is the same operation with the accumulation grid as the selector; no source read does it for ARF explicitly. [Certain for the precedent; Certain that no ARF-composite was found among the sources read] "A classified grid with the suffix _src which contains the source grid for the maximum value." https://wiki.tuflow.com/ASC_to_ASC ; workflow: https://wiki.tuflow.com/ARR_2019_Ensembles_Processing

19. **Small areas are not exempt.** ARR sets ARF = 1 only below 1 km² and interpolates to the 10 km² equation between 1 and 10 km²; the 2026 Austrian gauge study finds reduction already at 1 km² (0.93 in spring at T = 1 yr) and lowest ARFs in the convective seasons. [Certain] "an application of ARF is required even for areas as small as 1 km2" https://nhess.copernicus.org/articles/26/5057/2026/

20. **ARR 2019 gives no separate ARF rule for direct-rainfall (rain-on-grid) models.** Book 7 only warns about pre-wetting under direct rainfall; the Book 2 rule (finding 7) stands for any model type. [Certain] "Beware of direct rainfall boundary conditions and pre-wetting of catchment." https://www.arr-software.org/pdfs/ARR_190514_Book7_V4.1.pdf

21. **Wright et al. (2014) argue TP-29 misrepresents extreme rainfall because it mixes storms and storm types, and build storm-centred ARFs from 10 years of Charlotte radar, split tropical/non-tropical.** Read as abstract only; the storm-centred ARFs they propose are meant for stochastic storm transposition, not for multiplying a point frequency depth. [Likely] Abstract: https://ascelibrary.org/doi/10.1061/(ASCE)HE.1943-5584.0000855 (the author PDF redirects; ResearchGate and MDPI copies returned 403)

## Equations and algorithms

Notation: A catchment or storm area (km² unless stated), D duration, T return period, AEP annual exceedance probability as a fraction, P point depth, P_area areal depth.

**E1. Storm-centred ARF** (Svensson & Jones Eq. 1):
ARF_sc = P_area / P_point, where P_area is the mean rainfall inside a chosen isohyet of one storm and P_point the maximum at that storm's centre. No frequency attached.

**E2. Fixed-area ARF, probabilistically correct form** (Omolayo 1993 as Svensson & Jones Eq. 2):
ARF(A, D, T) = P_area(A, D, T) / [ Σ_i w_i P_i(D, T) / Σ_i w_i ],
P_area(A, D, T) the T-year areal rainfall over the fixed region of area A, P_i(D, T) the T-year point rainfall at gauge i, w_i the gauge weights (Thiessen).

**E3. TP-29 / US Weather Bureau** (Svensson & Jones Eq. 3; Pavlovic M1):
ARF_TP29 = Σ_j Σ_i w_i P'_ij / Σ_j Σ_i w_i P_ij, P_ij the annual maximum at station i in year j, P'_ij the station values making up the annual-maximum areal event. Independent of T by construction. Pavlovic's M1: ARF1(D, A) = P(D, A) / P(D, A*), A* one radar cell.

**E4. UK FSR** (NERC 1975): ARF_FSR = (1/IJ) Σ_j Σ_i P'_ij / P_ij, I stations, J years; an average of ratios instead of a ratio of averages.

**E5. UK FSR/FEH closed form** (Keers & Wescott 1977, as given in the ReFH2 technical guide; D in hours, A in km²):
ARF = 1 − b·D^(−a)
| A (km²) | a | b |
|---|---|---|
| A ≤ 20 | 0.40 − 0.0208·ln(4.6 − ln A) | 0.0394·A^0.354 |
| 20 < A < 100 | 0.40 − 0.00382·(4.6 − ln A)² | 0.0394·A^0.354 |
| 100 ≤ A < 500 | 0.40 − 0.00382·(4.6 − ln A)² | 0.0627·A^0.254 |
| 500 ≤ A < 1000 | 0.40 − 0.0208·ln(ln A − 4.6) | 0.0627·A^0.254 |
| A ≥ 1000 | 0.40 − 0.0208·ln(ln A − 4.6) | 0.1050·A^0.180 |
Check: 24 h, 100 km² → 0.943; 500 km² → 0.912 (the Water NZ paper tabulates FSR as 94% and 91%). Design depth in ReFH: P = DDF × ARF × SCF.

**E6. NWS TR-24 / HYDRO-40** (Myers & Zehr 1980; Zehr & Myers 1984):
ARF_NWS(f, Δt, A) = X_A(f, Δt, A) / X_A(f, Δt, 0), with X(f) = μ + K(f)·σ (Chow), μ and σ of the areal annual maxima estimated from station-pair statistics against distance and duration, calibrated on five-station groups. HYDRO-40 then dropped the K(f) dependence (too much scatter) and published the mean-based curves (T = 2.54 yr) by zone, as figures.

**E7. ARR 2019 Book 2 Chapter 4** (A in km², D in minutes, AEP a fraction between 0.5 and 0.0005):

Short duration, Eq. (2.4.1), D ≤ 720 min, 10 ≤ A ≤ 1000 km²:
ARF = min{ 1, 1 − 0.287·(A^0.265 − 0.439·log10 D)·D^(−0.36) + 2.26×10⁻³·A^0.226·D^0.125·(0.3 + log10 AEP) + 0.0141·A^0.213·10^[−0.021·(D − 180)²/1440]·(0.3 + log10 AEP) }

Long duration, Eq. (2.4.2), 1440 ≤ D ≤ 10 080 min, 10 ≤ A ≤ 30 000 km²:
ARF = min{ 1, 1 − a·(A^b − c·log10 D)·D^(−d) + e·A^f·D^g·(0.3 + log10 AEP) + h·10^(i·A·D/1440)·(0.3 + log10 AEP) }

Table 2.4.2 coefficients (reconstructed from the extracted text; the split numbers were re-joined and cross-checked against Ladson's gist for Tasmania and Inland Arid):
| Region | a | b | c | d | e | f | g | h | i |
|---|---|---|---|---|---|---|---|---|---|
| East Coast North | 0.327 | 0.241 | 0.448 | 0.36 | 0.00096 | 0.48 | −0.21 | 0.012 | −0.0013 |
| Semi-arid Inland Queensland | 0.159 | 0.283 | 0.25 | 0.308 | 7.3E−07 | 1 | 0.039 | 0 | 0 |
| Tasmania | 0.0605 | 0.347 | 0.2 | 0.283 | 0.00076 | 0.347 | 0.0877 | 0.012 | −0.00033 |
| South-West Western Australia | 0.183 | 0.259 | 0.271 | 0.33 | 3.85E−06 | 0.41 | 0.55 | 0.00817 | −0.00045 |
| Central New South Wales | 0.265 | 0.241 | 0.505 | 0.321 | 0.00056 | 0.414 | −0.021 | 0.015 | −0.00033 |
| South-East Coast | 0.06 | 0.361 | 0 | 0.317 | 8.11E−05 | 0.651 | 0 | 0 | 0 |
| Southern Semi-arid | 0.254 | 0.247 | 0.403 | 0.351 | 0.0013 | 0.302 | 0.058 | 0 | 0 |
| Southern Temperate | 0.158 | 0.276 | 0.372 | 0.315 | 0.000141 | 0.41 | 0.15 | 0.01 | −0.0027 |
| Northern Coastal | 0.326 | 0.223 | 0.442 | 0.323 | 0.0013 | 0.58 | −0.374 | 0.013 | −0.0015 |
| Inland Arid | 0.297 | 0.234 | 0.449 | 0.344 | 0.00142 | 0.216 | 0.129 | 0 | 0 |

Interpolation 12-24 h, Eq. (2.4.3): ARF = ARF_12h + (ARF_24h − ARF_12h)·(D − 720)/720.
Areas 1-10 km², Eq. (2.4.4): ARF = 1 − 0.6614·(1 − ARF_10km²)·(A^0.4 − 1). ARF = 1 for A ≤ 1 km². Above 30 000 km² the equations do not apply (do a catchment-average frequency analysis; model partial-area storms explicitly, also to be considered from 5000 km²).
Verification: the Book 2 worked example (East Coast North, 245.07 km², 24 h, 1% AEP) gives 0.929; my implementation reproduces 0.929.

**E8. HEC-HMS Depth-Area Analysis, as documented** (User's Manual 4.9, TRM, HEC guides):
For each analysis point p chosen in the basin model:
1. A_p = drainage area upstream of p (computed by HMS; it replaces the met model's storm area and computation point).
2. For every duration d of the nested frequency storm (or the single depth of a hypothetical storm): F(d, A_p) read from the area-reduction curve for that duration (TP-40 by duration up to 24 h, TP-49 beyond; or the user's paired-data table, "Linear Interpolation" between its nodes); reduced depth P_d = F(d, A_p)·P_point,d.
3. Build the hyetograph (intensity position / SCS or user pattern) and run the basin; keep results for elements upstream of p only.
4. Peak Flow Summary: point, drainage area, peak discharge, time of peak; per-point time series.
An ordinary simulation run is "correct" only at the computation point whose area equals the storm area.

**E9. Wadi2D proposal, one run per storm area and interpolation at points and cells** (mine; the numbers come from E10):
Inputs: ARF function F(A, d, AEP) (user table by area and duration, or E5/E7), point or gridded design rainfall P(x, d), accumulation grid giving the drainage area A(x) of every cell.
1. Nodes A_0 = "no reduction" (F = 1, the ARR rule for A ≤ 1 km²), then K = 6-8 nodes log-spaced from A_1 = 10 km² to A_K = the largest drainage area of interest (Block 2: 600 km²).
2. Run k: rainfall field R_k(x, t) = F(A_k, d, AEP)·P(x, t), the same factor on every lumped subbasin hyetograph and on every 2D cell of that run (a uniform factor per run, as HMS does; never a cell-by-cell factor inside one run, which would make a field with no frequency meaning). Store Q_k(p) and hydrographs at the design points, and the max grids H_k(c).
3. Design point p with drainage area A_p: find k with A_k ≤ A_p ≤ A_{k+1}, w = (ln A_p − ln A_k)/(ln A_{k+1} − ln A_k); ln Q(p) = (1 − w)·ln Q_k(p) + w·ln Q_{k+1}(p); hydrograph ordinates by the same weights (log-linear in A because ARF is near-linear in ln A and peaks are near-power-law in rainfall).
4. Composite map: for each cell c, k and w from A(c) exactly as in step 3; H(c) = (1 − w)·H_k(c) + w·H_{k+1}(c); write a source grid (k, A(c)) beside it, the equivalent of TUFLOW's `_src`.
5. Verification during validation only: one exact-area run per design point (K + P runs instead of K); acceptance |Q_interp − Q_exact|/Q_exact ≤ 2%. Afterwards only the K runs are made.
Cost: K runs per return period regardless of the number of design points or cells.

**E10. Interpolation-error arithmetic** (`H06_arf_interp.py`, 2000 test areas log-spaced over 10-600 km²; results in the Numbers table). Curves: the project Gonu fit (finding 14), FSR 24 h (E5), ARR 2019 Inland Arid and Southern Semi-arid at 24 h and 1% AEP (E7). Node counts 5-8. Errors reported as max |ARF_interp − ARF|/ARF, for interpolation linear in ln A, linear in A, and nearest-node snapping. Flow error ≈ m × ARF error with m = d ln Q / d ln P ≈ 1.2-2 for SCS-CN wadi catchments [Likely], so ≤ 1% at 6 log-spaced nodes even on the Gonu curve.

## Numbers

| Value | Context | Source |
|---|---|---|
| 0.94, 0.91 | FSR 24-h ARF at 100 km² and 500 km² (as % in the paper: 94%, 91%); FEH 95%, 91% | Ahsan & Kay, Water NZ paper, Tables 1 and 6 |
| 0.79, 0.67 | FSR 1-h ARF at 100 km² and 500 km²; 30-min: 0.72, 0.57 | same |
| 0.97, 0.93 | ARR 1987 (rev. 1998) 24-h ARF at 100 and 500 km² | same |
| 0.92 (24 h), 0.67 (1 h) | TP-29 at 500 km² | Pavlovic et al. 2016 §4.1 |
| 0.96, 0.95, 0.95, 0.95 | Four fixed-area methods, 24 h, 500 km², Oklahoma radar 2002-2013 | Pavlovic et al. 2016 §5.1 |
| 0.75-0.80 vs 0.69 | Same methods at 1 h, 750 km², vs TP-29 | same |
| 0.02-0.06 (24 h), ~0.08 (1 h) | ARF difference between 2-yr and 100-yr at 1000-1500 km² | Pavlovic et al. 2016 §5.2 |
| 0.66 / 0.80 vs 0.91 | HYDRO-40 24-h ratio at 300 mi² (777 km²), zones B/D and A/C, vs NOAA Atlas 2 | HYDRO-40 §5.3 |
| 0.950, 0.918, 0.900, 0.877, 0.848, 0.806, 0.783 | Maricopa 24-h general storm at 10, 20, 30, 50, 100, 300, 500 mi² (26, 52, 78, 130, 259, 777, 1295 km²), from HYDRO-40 Fig. 15 | Maricopa 2011 Table 2.2 |
| 0.940, 0.910, 0.870, 0.800 | Maricopa 6-h local storm at 10, 20, 40, 100 mi² (1954 Queen Creek storm) | Maricopa 2011 Table 2.1 |
| 2.54 yr | Return period the HYDRO-40 mean curves correspond to; declared conservative above it | HYDRO-40 §4.4 |
| 0.929 | ARR 2019 worked example, East Coast North, 245.07 km², 24 h, 1% AEP | ARR Book 2 §6.5.3 |
| 0.983, 0.968, 0.946, 0.921, 0.901, 0.885 | ARR 2019 Inland Arid, 24 h, 1% AEP at 10, 30, 100, 300, 600, 1000 km² (computed, E7) | `H06_arf_interp.py` |
| 0.974, 0.963, 0.943, 0.924, 0.907, 0.892 | FSR 24 h at the same areas (computed, E5) | same |
| 0.999, 0.977, 0.920, 0.885, 0.850, 0.817, 0.673, 0.579, 0.512, 0.384, 0.222 | Project `ARF Gonu` table at 28.3, 78.5, 153.9, 201, 254, 314, 706.5, 1256, 1963, 7854, 44 042 km² (circles of radius 3-118 km) | `ARF Gonu.xlsx`, Block 2 |
| 0.84 vs 0.848; 0.68 vs 0.66 (B/D) or 0.80 (A/C); 0.59 vs 0.783 | Gonu fit vs Arizona 24-h at 259, 777, 1295 km² | arithmetic on the two sources |
| 0.823 vs 0.924/0.921; 0.718 vs 0.907/0.901 | Gonu fit vs FSR/ARR Inland Arid at 300 and 600 km²: 11% and 20% lower | same |
| 1.6-2.5% | ARF step between neighbouring nodes, 6-8 log-spaced nodes 10-600 km², FSR and ARR arid curves | `H06_arf_interp.py` |
| 12-17% | Same on the Gonu curve (steep) | same |
| ≤ 0.08% / ≤ 0.46% (6 nodes); ≤ 0.04% / 0.24% (8 nodes) | Max error of log-linear interpolation, standard curves / Gonu curve | same |
| 1.1-1.6% / 6-10% | Max error of nearest-node snapping (no interpolation), standard / Gonu | same |
| 2.46% | HMS linear-in-area interpolation between the Gonu table's own nodes vs the smooth fit, worst at ~700 km² | same |
| −5.1%, −6.1%, −27.8% | Rainfall at a 50 km² point if one 600 km² storm area is used: FSR, ARR Inland Arid, Gonu | same |
| −3.8%, −4.8%, −24.1% | Same at a 100 km² point | same |
| 14.2-16.7% and 23.4-25.0% | Peak-flow change from applying ARF at subcatchment scale (NZ, two catchments, 100-yr) | Ahsan & Kay |
| 0.93 at 1 km² | Lowest 1 km² ARF (spring, T = 1 yr), Austrian 5-min gauge network 2007-2022 | NHESS 2026 |
| 400 mi² (1036 km²) | Upper limit for the HMS built-in TP-40/49 curves | HMS TRM hypothetical storm |
| 1 km² / 10 km² / 30 000 km² | ARR thresholds: ARF = 1 below; interpolation 1-10; equations invalid above | ARR Book 2 Table 2.4.1 |
| 13 × 14 | Block 2 practice: depth-area analyses per return period × analysis points (every element) | Block 2 `CLAUDE.md` |

## Recommendation for Wadi2D

**Lead with the uncomfortable part: the table Wadi2D must reproduce for Block 2 is a storm-centred ratio of one cyclone, and the software should say so rather than hide it.** The `ARF FM` table is "Based on Gonu" (finding 14). By the definitions every standard uses (findings 1-3), multiplying a 100-yr point depth by a Gonu isohyet ratio does not give a 100-yr areal depth; it gives something lower (finding 3), and beyond ~800 km² much lower than even the steepest published semi-arid curve (finding 15). Between 80 and 800 km², the range of his dam sites, the magnitude happens to sit on the Arizona HYDRO-40 curves, which is a defensible argument for it, but the argument has never been written down. Wadi2D's job is not to overrule the project; it is to (a) accept any user table, (b) label its type on every output, and (c) make the comparison with published fixed-area curves one click away so the design note and the reviewers see it.

Specifics:

1. **ARF input = a paired-data function F(area, duration), HMS-compatible, plus built-in reference curves.** Accept the HMS table form (area vs factor; optionally one column per duration, as TP-40 has). Ship as built-ins, for comparison and for countries that prescribe them: FSR/FEH (E5), ARR 2019 generalised equations with all ten regions and the AEP term (E7), the Maricopa/HYDRO-40 24-h and 6-h tables, TP-29 via the HMS TP-40 24-h curve values (to be digitised; not done here). Every table carries a type flag, `fixed-area` or `event depth-area ratio`, that is printed in the run log and the report tables. Reject: inventing an Oman ARF; nothing published exists (finding 13), and the ARR Inland Arid curve must be offered only as a labelled reference, never as a default.

2. **One uniform factor per run, never a cell-by-cell factor inside one run.** The ARF of a run multiplies the lumped subbasin hyetographs and the 2D rain alike (E9 step 2). This is what HMS does and what ARR's "not per subarea" sentence (finding 7) requires. Reject the alternative in `CLAUDE.md` decision 9, a storm-centred spatial storm whose isohyets carry the depth-area relation: fixed-area tables cannot be converted to it exactly (finding 1), it has no HMS counterpart for the apples-to-apples test, and reviewers cannot check it.

3. **K log-spaced storm-area runs with log-linear interpolation at design points, plus the ARF = 1 run.** K = 6 is enough for standard curves (error < 0.1%) and acceptable for the Gonu table (< 0.5% in ARF, ≤ 1% in peak); K = 8 if the user's table is steeper than Gonu. Interpolate ln Q linearly in ln A (E9 step 3). Reject nearest-node snapping (6-10% on the Gonu table, finding 16) and reject a single catchment-wide storm area for interior points (up to 28% rainfall error on the Gonu table, finding 17). Keep the exact-area run as a validation mode: on Block 2, run the five dam sites exactly once, show ≤ 2% against the interpolated values, then never again.

4. **Composite map = the depth-area analysis evaluated at every cell.** Implement E9 step 4 with the accumulation grid as the selector and write the source grid, exactly as TUFLOW's `-max` writes `_src` (finding 18). State in the output metadata that the composite is not one event: volumes and hydrographs at a point must come from that point's interpolated run, not from the composite grid. Offer the plain per-run grids as well, since a reviewer may ask for the "600 km² storm" map alone.

5. **Duration axis.** Store F by duration and apply the duration's own factor to each nested depth, as HMS does (finding 9); the Block 2 24-h specified-pattern storm reduces to one factor per run, but a critical-duration ensemble (TUFLOW/ARR practice, finding 18) needs the full axis, and the FSR numbers (0.79 vs 0.94 at 100 km²) show how much it moves.

6. **Small areas.** Follow ARR: F = 1 below 1 km², Eq. (2.4.4) interpolation 1-10 km², and the ARF = 1 run as node A_0 so hillslope cells in the composite map read unreduced rain (findings 7, 19).

7. **Presentation to reviewers, in HMS and ARR words only.** Call the K runs a "depth-area analysis with storm areas of 10, 25, 60, 150, 350, 600 km²" and the point values "peak flows at the analysis points, interpolated between the two storm areas bracketing each point's drainage area (linear interpolation, as in the HEC-HMS area-reduction table)". Print the HMS Peak Flow Summary layout: analysis point, drainage area, storm areas bracketing it, ARF at the point's own area, peak, time of peak. Call the composite map "the depth-area analysis evaluated at every cell; each cell takes the storm area equal to its own drainage area", and quote the two standard sentences that justify it: HMS's "storm area equal to the drainage area at the point of evaluation" (finding 8) and ARR's "total catchment upstream of each location of interest" (finding 7). Document the ARF table, its type and its source in the report the way FEMA requires (finding 10). No new vocabulary: not "composite", not "ARF-consistent map", not "storm-area ensemble".

8. **Hazard-map mode.** ARF = 1 everywhere (the HEC-RAS default) stays available for hazard mapping, labelled "point rainfall, no areal reduction"; it over-states areal rainfall by 10-28% at 100-600 km² on arid curves, which is why it must never be the design-flow default.

9. **What to measure on Block 2 to close the open question.** Test (a) of decision 6 must include the 13 depth-area analyses: Wadi2D's interpolated peaks at the five dam sites against HMS's exact-area peaks (acceptance ±2%); then the same with the ARR Inland Arid and HYDRO-40 curves in place of the Gonu table, so the design note can show the dam-site peaks under each ARF type. That table is the argument for or against the Gonu table, and it costs K runs per curve.

## Open issues

1. Provenance of `ARF Gonu.xlsx`: who derived it, from which isohyet map of Gonu, whether MAFWWR reviewed it, and whether the dam team's earlier reports justify it against HYDRO-40-type curves. Ask him; nothing in the files read says.
2. No Oman / Saudi / UAE ARF literature found; the Oman leads not read: Al-Rawas (2009) Calgary thesis (2042 Rustaq storms), Al-Qurashi et al. (2008) Kineros2 Wadi Ahin, the JICA roads study chapter 10 and the MRMEWR flood design manual of November 2000 it cites, Wheater & Bell (1983) Northern Oman flood study. The search budget ran out before the Saudi (Elfeki/Ewea/Al-Amri, Awadallah & Younan 2012) and UAE (Abu Dhabi / Dubai drainage manuals) searches.
3. Wright et al. (2014) full text and the MDPI radar storm-centred ARF paper (2019) and the MDPI 2026 "network-consistent return periods" rain-on-grid paper were blocked (403); the last may contain a per-reach return-period correction close to the composite-map idea.
4. Osborn et al. (1980) Walnut Gulch ratios (30 min-6 h) not read directly (DNS failure); quoted through HYDRO-40 and Maricopa.
5. The HYDRO-40 zone curves (Figs 14-15) exist only as figures; the Maricopa Table 2.2 is their tabulation for zones A/C. The zone B/D 24-h table (the steeper one, 0.66 at 777 km²) is not tabulated anywhere read.
6. Return-period dependence for arid convective storms is qualitative only (HYDRO-40 could not quantify it; Asquith shows the direction). Wadi2D's AEP term exists only through ARR's equations.
7. The flow sensitivity m ≈ 1.2-2 used to turn ARF error into peak error is a guess to be measured on Block 2 (E10).
8. TP-29 24-h curve values were not digitised (HMS has them hard-coded as TP-40); needed if the built-in library is to include them.
9. Interpolating hydrograph ordinates between two runs can blur the time of peak when the two runs' peaks differ in timing; check on Block 2 and, if needed, interpolate peak and volume and take the nearer run's shape.

## Sources

1. Svensson, C. & Jones, D.A. (2010) Review of methods for deriving areal reduction factors, J. Flood Risk Management 3, 232-245, author manuscript: https://nora.nerc.ac.uk/id/eprint/8816/1/N008816PP.pdf — definitions E1-E4, return-period and climate dependence, storm-centred vs fixed-area conclusions.
2. Pavlovic, S., Perica, S., St Laurent, M., Mejía, A. (2016) Intercomparison of selected fixed-area areal reduction factor methods, J. Hydrology 537, 419-430: https://repository.library.noaa.gov/view/noaa/15277/noaa_15277_DS1.pdf — TP-29 definition and values, four-method comparison at 24 h and 1 h, ARI dependence.
3. ARR 2019 Book 2 (V4.2), Chapter 4 Areal Reduction Factors and Chapter 6 worked example: https://www.arr-software.org/pdfs/ARR_190514_Book2_V4.2.pdf — E7 equations and coefficients, the per-point-of-interest rule, limits.
4. ARR Project 2 Stage 3 report (short-duration ARFs): https://www.arr-software.org/pdfs/ARR_Project02_Stage3_Short_Duration_Areal_Reduction_Factors_S3_v1.pdf — derivation method (circular catchments, GEV, median per case).
5. ARR 2019 Book 7 (V4.1): https://www.arr-software.org/pdfs/ARR_190514_Book7_V4.1.pdf — absence of a direct-rainfall ARF rule.
6. Ladson, T. (2020) ARR2019 areal reduction factors: https://tonyladson.wordpress.com/2020/04/05/arr2019-areal-reduction-factors/ — cross-check of Eqs 2.4.3, 2.4.4 and the coefficient transcription (secondary).
7. NOAA Atlas 14 Volume 1 Version 5 (Semiarid Southwest), §7 Interpretation: https://www.weather.gov/media/owp/oh/hdsc/docs/Atlas14_Volume1.pdf — point-estimate statement, referral to TR-24 / HYDRO-40.
8. Zehr, R.M. & Myers, V.A. (1984) Depth-area ratios in the semi-arid southwest United States, NOAA Tech. Memo. NWS HYDRO-40: https://www.weather.gov/media/owp/oh/hdsc/docs/TM40.pdf — fixed-area definition, Walnut Gulch, zone ratios, return-period caveat.
9. Flood Control District of Maricopa County (2011) Drainage Design Manual, Hydrology, §2.3 Depth-area relation: https://www.resolutionmineeis.us/sites/default/files/references/maricopa-county-2011.pdf — Tables 2.1 and 2.2, local vs general storm practice.
10. Asquith, W.H. (1999) Areal-reduction factors for the precipitation of the 1-day design storm in Texas, USGS WRIR 99-4267: https://pubs.usgs.gov/wri/wri99-4267/pdf/wri99-4267.pdf — two ARF types, TP-29 basis and limits, frequency considerations, Table 7 form.
11. FEMA (Nov 2024) Guidance for Flood Risk Analysis and Mapping, Hydrology: Rainfall-Runoff Analysis: https://www.fema.gov/sites/default/files/documents/fema_guidance_hydrology_rainfall-runoff_analysis_nov_2024.pdf — ARF documentation requirement.
12. HEC-HMS User's Manual 4.9, Depth-Area Analyses: https://www.hec.usace.army.mil/confluence/hmsdocs/hmsum/4.9/depth-area-reduction/depth-area-analyses — storm area = drainage area, automation, results.
13. HEC-HMS User's Manual 4.9, Precipitation (Frequency Storm, Hypothetical Storm): https://www.hec.usace.army.mil/confluence/hmsdocs/hmsum/4.9/meteorology-description/precipitation — storm area, TP-40 per duration, user table, analysis-point override.
14. HEC-HMS Technical Reference Manual, Hypothetical Storm: https://www.hec.usace.army.mil/confluence/hmsdocs/hmstrm/meteorology/precipitation/hypothetical-storm — point values, separate storms per location, 400 mi² limit.
15. HEC guide, Applying Depth-Area Analysis to Precipitation-Frequency Grids: https://www.hec.usace.army.mil/confluence/hmsdocs/hmsguides/meteorologic-methods-in-hms/flow-frequency-simulation-options-in-hec-hms/applying-depth-area-analysis-to-precipitation-frequency-grids — algorithm E8, area-reduction function form.
16. HEC guide, Applying the Frequency Storm Met Model in HEC-HMS: https://www.hec.usace.army.mil/confluence/hmsdocs/hmsguides/meteorologic-methods-in-hms/flow-frequency-simulation-options-in-hec-hms/applying-the-frequency-storm-met-model-in-hec-hms — workshop statement that interior points are wrong without their own storm area; Peak Flow Summary table.
17. ReFH2 Technical Guide, Design rainfall depth (FEH/FSR ARF, Keers & Wescott 1977): https://refhdocs.hydrosolutions.co.uk/Design-DDF-Rainfall-Hyetographs/Design-Rainfall-Depth/ — E5.
18. Ahsan, H. & Kay, T., Use of areal reduction factor in modelling and its implication, Water New Zealand conference paper: https://www.waternz.org.nz/Attachment?Action=Download&Attachment_id=1192 — FSR/FEH/ARR tabulated values, subcatchment-vs-catchment peak differences.
19. Pietersen, J.P.J., Gericke, O.J., Smithers, J.C., Pegram, G.G.S. (2015) Review of current methods for estimating areal reduction factors applied to South African design point rainfall, Water SA 41(1): https://scielo.org.za/scielo.php?pid=S1021-20192015000100002&script=sci_arttext — Omolayo's argument, Bell's method, Alexander's equations.
20. TUFLOW wiki, ARR 2019 Ensembles Processing: https://wiki.tuflow.com/ARR_2019_Ensembles_Processing and ASC to ASC: https://wiki.tuflow.com/ASC_to_ASC — envelope workflow and `_src` grid (composite-map precedent).
21. NHESS (2026) Areal reduction factors from high-resolution rain gauges in Austria: https://nhess.copernicus.org/articles/26/5057/2026/ — small-area and seasonal findings.
22. Wright, D.B., Smith, J.A., Baeck, M.L. (2014) Critical examination of area reduction factors, J. Hydrol. Eng. 19(4), 769-776, abstract only: https://ascelibrary.org/doi/10.1061/(ASCE)HE.1943-5584.0000855
23. Project files (read-only): `D:\Mojtaba\Renardet\2224 WS11\Batinah\Block 2\Hydrology\HEC_HMS_Block_02\Hydrology Data\XLS\ARF Gonu.xlsx` (the `ARF FM` table and its fit) and `D:\Mojtaba\Renardet\2224 WS11\Batinah\Block 2\CLAUDE.md` (how the table is applied in the 13 frequency storms and 13 depth-area analyses).
24. Not reached in this run: Osborn et al. (1980) https://www.tucson.ars.ag.gov/unit/publications/PDFfiles/2845.pdf (DNS); Al-Qurashi et al. (2008) https://tucson.ars.ag.gov/unit/publications/pdffiles/1905.pdf (DNS); Al-Rawas thesis https://www.collectionscanada.gc.ca/obj/thesescanada/vol2/002/NR62136.PDF (fetch failed); MDPI Water 2019 storm-centred radar ARFs https://www.mdpi.com/2073-4441/11/6/1120 (403); MDPI Water 2026 rain-on-grid network-consistent return periods https://doi.org/10.3390/w18080950 (403); J. Hydrology X 2020 CONUS ARF variability https://www.sciencedirect.com/science/article/pii/S2589915520300158 (403).

Script: `H06_arf_interp.py` in this folder reproduces every computed number above (`python -I H06_arf_interp.py`; needs numpy).
