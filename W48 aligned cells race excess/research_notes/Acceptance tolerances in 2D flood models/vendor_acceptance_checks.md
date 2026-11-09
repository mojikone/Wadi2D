# Acceptance checks and numerical tolerances that 2D flood model makers publish for their own software

Scope note. Researched 2026-11-08. Primary vendor documents were read in full text where they could be downloaded (HEC-RAS 7.0 V&V of September 2026, HEC-RAS 2D User's Manual 6.6, RD-51, TUFLOW's 2017 EA benchmark report, Huxley et al. 2022, Kitts 2020, the Iber 2020 benchmark report, the EA 2010 benchmark report); others were read as web pages. Wording is paraphrased, numbers are as the source gives them. "Threshold" below means a number the vendor presents as a limit or an acceptance rule; "comparison" means numbers shown without a pass mark.

## Q1. HEC-RAS 2D (USACE HEC): what the V&V report, RD-51 and the 2D User's Manual state

### Takeaway
HEC publishes error statistics (ME, MAE, RMSE, NRMSE, R², volume error %) and an observed order of grid convergence, but sets no pass/fail tolerance for any 2D verification, validation, mesh-resolution, feature or volume-accounting check. The only numeric rules in its 2D manual are Courant guidance (C about 1, up to 3 for the shallow-water solvers, up to 5 for diffusion wave) and 5 to 7 cells across a channel when in-channel 2D detail is wanted.

### Cited Findings
- **Current V&V document.** HEC's reference-documents page lists "HEC-RAS Verification and Validation Document", updated for version 7.0, September 2026, as current; RD-52 of September 2020 is marked superseded; RD-51 (2D benchmarking) is listed as updated April 2020. — [HEC-RAS reference documents](https://www.hec.usace.army.mil/confluence/rasdocs/hgt/latest/reference-documents)
- **Purpose of the V&V (RD-52, 7.0, Sept 2026, run with 7.0.2).** It states its aim as showing that the code works correctly and how well it performs against analytical, textbook, laboratory and gauged field data. No acceptance criterion is stated for the suite. — [HEC-RAS 7.0 V&V Tests, RD-52, Sept 2026](https://www.hec.usace.army.mil/confluence/rasdocs/hgt/files/latest/384140705/384140719/1/1790798753494/HEC-RAS+7.0+V%26V+Spetember+2026.pdf)
- **Metrics used.** Appendix A defines mean error (bias), mean absolute error, RMSE, standard deviation of residuals, normalised forms (NRMSE etc., with the remark that there is no consistent way to normalise), performance scores (Brier skill, Nash-Sutcliffe) and Willmott's index of agreement. — [RD-52, 2026, Appendix A](https://www.hec.usace.army.mil/confluence/rasdocs/hgt/files/latest/384140705/384140719/1/1790798753494/HEC-RAS+7.0+V%26V+Spetember+2026.pdf)
- **The one numeric grading scale in the V&V.** Appendix A gives recommended qualifications for performance-score ranges: 0.8 to 1 Excellent, 0.6 to 0.8 Good, 0.3 to 0.6 Reasonable, 0 to 0.3 Poor, below 0 Bad. It is a skill-score grading borrowed from coastal practice, not a tolerance on depth, level or discharge. — [RD-52, 2026, Appendix A, Table 1](https://www.hec.usace.army.mil/confluence/rasdocs/hgt/files/latest/384140705/384140719/1/1790798753494/HEC-RAS+7.0+V%26V+Spetember+2026.pdf)
- **Analytic verification, reported not judged.** Chow Example 10.1 run in 2D: water-level ME -0.019 ft, MAE 0.0215 ft, RMSE 0.0285 ft, total volume error 0.0000057825 %, described only as excellent volume conservation. — [RD-52, 2026, section 4.2.1](https://www.hec.usace.army.mil/confluence/rasdocs/hgt/files/latest/384140705/384140719/1/1790798753494/HEC-RAS+7.0+V%26V+Spetember+2026.pdf)
- **Grid convergence (a and b).** MacDonald's 1D subcritical case on a variable slope was run at 1, 2, 4, 8, 16 and 32 m (refinement ratio 2) against the analytic depth. MAE runs from about 0.0035 m (0.05 %) at 1 m to about 0.104 m (1.5 %) at 32 m, RMSE about 0.004 to 0.111 m, and the fitted order of convergence is about 1.32, put down to first-order backward tracking in the Eulerian-Lagrangian scheme. No pass mark is set; the table columns were rebuilt from a text extraction. — [RD-52, 2026, section 4.2.2, Table 4-4](https://www.hec.usace.army.mil/confluence/rasdocs/hgt/files/latest/384140705/384140719/1/1790798753494/HEC-RAS+7.0+V%26V+Spetember+2026.pdf)
- **Other V&V numbers, all descriptive.** On a wetting-front case, volume conservation error under 1x10^-6 % and the front arriving slightly early, with good agreement above about 0.2 m depth. On a laboratory case, NRMSE of discharge 2.5 to 12.5 %, R² 0.88 to 0.995 and volume error 0.001 to 0.013 %. For the lab bridge cases, time steps were set for a Courant number of about 1.0 or less in the fastest cells. — [RD-52, 2026, chapter 4](https://www.hec.usace.army.mil/confluence/rasdocs/hgt/files/latest/384140705/384140719/1/1790798753494/HEC-RAS+7.0+V%26V+Spetember+2026.pdf)
- **RD-51 (UK EA benchmark tests, April 2018 edition read).** It aims to show that HEC-RAS 2D gives results similar to the leading models in the EA report. Test 1 results sit in the middle of TUFLOW, MIKE FLOOD, ISIS 2D and SOBEK. No numeric criterion is given anywhere. — [RD-51, April 2018](https://www.hec.usace.army.mil/software/hec-ras/documentation/RD-51_Benchmarking_2D.pdf); the April 2020 update is at [RD-51 Apr 2020](https://www.hec.usace.army.mil/confluence/rasdocs/hgt/files/latest/384140705/384140708/1/1790798710148/RD-51+HEC-RAS+Benchmarking_Apr2020.pdf) (not read)
- **RD-51's coarse-mesh claim (b and c).** Each base grid was compared with one twice as coarse: 5 against 10 m (Test 4), 50 against 100 m (Test 5), 20 against 40 m (Test 7), 2 against 4 m (Test 8A). HEC calls the results almost the same or similar and credits the sub-grid cell and face tables. Time steps of 1, 2, 5 and 10 s converge to the same result. No difference is quantified as a tolerance. — [RD-51, chapters 5, 6, 8, 9](https://www.hec.usace.army.mil/software/hec-ras/documentation/RD-51_Benchmarking_2D.pdf)
- **Courant guidance (e).**
  - SWE-EM, the explicit scheme, needs C below 1.0.
  - For the shallow-water solvers the suggested value is C = 1.0, and a user "may be able to get away with" up to 3.0 (SWE) or 5.0 (diffusion wave) and stay stable and accurate.
  - C = 1.0 is needed for rapidly varying waves and for a domain that starts dry.
  
  — [HEC-RAS 2D User's Manual 6.6, exported Sept 2024, "Selecting an Appropriate Grid Size and Time Step"](https://www.hec.usace.army.mil/software/hec-ras/documentation/HEC-RAS_2D_Users_Manual_v6.6.pdf)
- **Mesh and time-step sensitivity (b).** The manual tells users always to test different cell sizes and different time steps for each mesh, citing the consistency principle that both must be refined together for convergence. It gives no tolerance for deciding when results agree. — [HEC-RAS 2D User's Manual 6.6](https://www.hec.usace.army.mil/software/hec-ras/documentation/HEC-RAS_2D_Users_Manual_v6.6.pdf)
- **Cells across a channel (c, refinement and breaklines).** For two-dimensional velocity and level detail inside a channel, the manual calls for 5 to 7 or more cells across it. Otherwise a coarse cell carries the channel in a 1D-like mode through its face tables. Breakline near and far spacing and gradual size transitions are advised, with no numeric accuracy check. — [HEC-RAS 2D User's Manual 6.6, chapter 3](https://www.hec.usace.army.mil/software/hec-ras/documentation/HEC-RAS_2D_Users_Manual_v6.6.pdf)
- **Volume accounting (d).** The computation log always reports a volume accounting for the whole model and for each 2D area. The manual's worked example calls 0.02017 % "very low" and 0.00003 to 0.001063 % "extremely low", and sets no acceptable limit. The 2D water-surface tolerance (default 0.01 ft, maximum 0.2 ft) is an iteration tolerance, not an acceptance limit. — [HEC-RAS 2D User's Manual 6.6, "Computation Progress, Numerical Stability, and Volume Accounting"](https://www.hec.usace.army.mil/software/hec-ras/documentation/HEC-RAS_2D_Users_Manual_v6.6.pdf)
- **Second-hand, practitioner forum, not HEC.** A user reports finding no volume-error threshold in any HEC manual. One expert suggests about 0.1 % for an all-2D model; others cite under 1 % as ideal and 2 to 3 % as possibly tolerable for rain on the mesh. — [RAS Solution forum: acceptable level of error in volume conservation](https://therassolution.kleinschmidtgroup.com/the-ras-solution-forum/topic/acceptable-level-of-error-in-the-volume-conservation/); [RAS Solution forum: how good/bad is 1 % volume error](https://therassolution.kleinschmidtgroup.com/the-ras-solution-forum/topic/how-goodbad-is-1-volume-errorae)

### Inferences
- [Certain] HEC sets no numeric pass mark for (a) analytic or lab agreement, (b) coarse against fine mesh, (c) a new option or feature against a reference, or (d) volume error. (e) is covered only by Courant guidance.
- [Likely] HEC's mesh-resolution evidence is one doubling per test, judged by eye on hydrograph plots, so "almost the same" is the only standard HEC applies to itself for coarse against fine.
- [Likely] HEC's reported grid-convergence order of about 1.3 on MacDonald's case is the closest vendor analogue to a convergence study. At 16 to 32 m it carries 0.8 to 1.5 % mean depth error, so HEC accepts errors of this size on a smooth analytic case without remark.

### Gaps
- I read RD-51 in the April 2018 edition, not the April 2020 update.
- I did not check which V&V test cases, if any, use the Excellent/Good/Poor performance-score scale.
- The Hydraulic Reference Manual's "Robustness and Stability" section, which the V&V cites for a second time-step criterion with turbulence on, was not read.
- No HEC statement compares a breakline-refined mesh against a reference with a number.

## Q2. TUFLOW (Classic and HPC, including Quadtree and SGS)

### Takeaway
TUFLOW is the only vendor with a stated health threshold on mass error: ±1 % cumulative mass error for Classic, repeated as "up to 1 %" for HPC on the wiki. It also gives numeric stability flags and cells-across-a-flow-path rules. For cell-size convergence and for comparing solvers or meshes, TUFLOW says plainly that acceptance is subjective and study-specific. Its own authors state that no convergence acceptability criterion exists and that industry consultation is needed. HPC 2nd order against Classic is described, not ruled, as usually within a few per cent of depth.

### Cited Findings
- **Mass error, Classic (d).** The manual says healthy Classic models fall within ±1 % cumulative mass error, and ideally the overall, 1D and 2D percentages should each be within ±1 %. Above 1 % is a warning sign, though a high error at the start is acceptable if it dies away quickly. — [TUFLOW Classic/HPC Manual 2026.3, Checks and Logs](https://docs.tuflow.com/classic-hpc/manual/2026.3/12-Checks-and-Logs.html); [TUFLOW Manual 2025.2, Mass Balance Output](https://docs.tuflow.com/classic-hpc/manual/2025.2/MB-2.html)
- **Mass error, HPC (d).**
  - The HPC mass-balance section gives no numeric criterion; small errors are put down to numerical precision. — [TUFLOW Manual 2026.3, Checks and Logs](https://docs.tuflow.com/classic-hpc/manual/2026.3/12-Checks-and-Logs.html)
  - The search summary of the 2025.2 mass-balance page says HPC's adaptive scheme conserves 2D mass fully; the page was not fetched. — [TUFLOW Manual 2025.2, MB](https://docs.tuflow.com/classic-hpc/manual/2025.2/MB-2.html)
  - The wiki says a healthy model usually reports up to 1 % mass error. — [TUFLOW Wiki, HPC Model Review](https://wiki.tuflow.com/HPC_Model_Review)
- **Mass error on direct rainfall (d).** According to the search summary, the wiki advises lowering the cell wet/dry depth to 0.0002 when cumulative mass error exceeds 1 % on direct-rainfall models. The page was not fetched. — [TUFLOW Wiki, Message 2317](https://wiki.tuflow.com/TUFLOW_Message_2317)
- **Other mass-balance details.** Classic's peak-period figure (pCME5) covers the time when flow in and out exceeds 5 % of the peak flow. The 1D node error is judged against the flow passing through: 1 m³/s at a node carrying 1,000 m³/s is not an issue, at 2 m³/s it is. — [TUFLOW Manual 2026.3, Checks and Logs](https://docs.tuflow.com/classic-hpc/manual/2026.3/12-Checks-and-Logs.html)
- **Run-time stability flags (e).**
  - Negative depths below -0.1 m are counted and flagged. — [TUFLOW Manual 2026.3, Checks and Logs](https://docs.tuflow.com/classic-hpc/manual/2026.3/12-Checks-and-Logs.html)
  - HPC lets control numbers be breached by 20 % and repeats a step only above Nc, Nu 1.2 or Nd 0.36. A time step under 1/10 of a healthy Classic step is low. Nu ≥ 1.0 suggests unusually high velocity, Nc ≥ 1.0 an erroneously low cell, Nd ≥ 0.3 a poor boundary.
  - The recommended sensitivity test is Control Number Factor 0.8, about 20 % longer run time; models should not need it lower.
  
  — [TUFLOW Wiki, HPC Model Review](https://wiki.tuflow.com/HPC_Model_Review)
- **Cell size rules (b).** Minimum cells across a flow path:
  - Classic 4 to 6, low sensitivity to flow-path orientation.
  - HPC without SGS 6 to 8, medium sensitivity.
  - HPC with SGS 3 to 4, very low sensitivity, provided the terrain is at least 2 x finer.
  
  Convergence testing is called the most robust check on cell size. — [TUFLOW Manual 2026.0, 3.2 Model Resolution](https://docs.tuflow.com/classic-hpc/manual/2026.0/ModelResolutionDiscretisation-2.html)
- **How convergence is judged (b), no number given.**
  - Results should trend towards a common answer as cells shrink. Acceptance is subjective and depends on the essential results: document the tests and engage stakeholders if needed.
  - Methods offered: halve the cell until extents are acceptably similar and take the penultimate size; flow lines; a result-against-cell-size plot, taking the largest size within some defined tolerance; a histogram of differences at 100 or more points against the finest feasible size, with a criterion such as 95 % of points within ± a tolerance left blank.
  - A worked example finds 40 m consistent with finer sizes and 60 m not. Smagorinsky viscosity makes results more cell-size sensitive than HPC's default Wu model.
  
  — [TUFLOW Manual 2026.0, 3.2.4 Cell Size Results Convergence](https://docs.tuflow.com/classic-hpc/manual/2026.0/ModelResolutionDiscretisation-2.html)
- **No convergence criterion exists (b), in TUFLOW's own words.** Huxley, Syme, Ryan and Collecutt (BMT/TUFLOW, HWRS 2022) say their paper does not address convergence acceptability criteria for catchment flood studies. They say broader industry consultation is needed to set guidelines, and expect the criteria to vary with study objectives and local flood sensitivity. — [Huxley et al. 2022, HWRS](https://www.tuflow.com/media/7555/2022-hydraulic-modelling-2d-cell-size-result-convergence-huxley-et-al-hwrs.pdf)
- **Huxley et al. 2022, numbers.**
  - Brisbane River: 1st order, 2nd order and 2nd order SGS at 20, 30, 40, 50 and 60 m, scored against 2011 flood marks, coloured "good" within ±0.2 m. That is a calibration band, not a convergence tolerance.
  - Throsby Creek: SGS converges below 9 to 12 m cells, traditional sampling below 6 m at one gauge and not at the other.
  - SGS runs 12 to 50 % slower.
  
  — [Huxley et al. 2022](https://www.tuflow.com/media/7555/2022-hydraulic-modelling-2d-cell-size-result-convergence-huxley-et-al-hwrs.pdf)
- **SGS on against off (c).** Kitts (BMT, River Flow 2020) concludes that SGS cuts mesh-size and orientation sensitivity, so a regular mesh can be rotated or resized with "acceptable" changes in results. Without SGS the changes are much greater and sometimes "unacceptable", but no number defines either word. — [Kitts 2020](https://tuflow.com/media/5022/2020-mesh-orientation-and-cell-size-sensitivity-in-2d-swe-solvers-kitts-et-al-iahr-river-flow-delft.pdf)
- **HPC against Classic (c), described not ruled.**
  - 2nd-order HPC and Classic peak levels usually differ by a few per cent of the depth in the main flow paths, more next to them and at the flood edge; a slight Manning's n adjustment typically reconciles them.
  - 1st-order HPC can exceed Classic by more than 10 % of the main flow-path depth in deep, fast channels.
  - Best practice is to compare the results and fine-tune if the differences are unacceptable, with no threshold given.
  - Quadtree and SGS "can warrant" larger cells in places; no Quadtree against uniform number is given.
  
  — [TUFLOW Wiki, HPC FAQ](https://wiki.tuflow.com/HPC_FAQ)
- **Reproducibility (c).** Repeat runs are bit-identical. CPU against GPU, or one CPU type against another, typically differ by under 1 mm of water level, more at overtopping or structure thresholds. HPC and Classic always differ a little, more with default settings (Wu against Smagorinsky). — [TUFLOW Manual 2026.0, 13.7 Reproducibility of Results](https://docs.tuflow.com/classic-hpc/manual/2026.0/ResultsReplication-3.html)
- **EA benchmark self-report (a, c).** TUFLOW's 2017-09 report runs the 8 EA tests with Classic, HPC on CPU and GPU, the old GPU solver and FV. It concludes the engines are consistent with each other and consistent with or better than the other full schemes in the 2012 EA report, with no numeric criterion. Test 2 end-of-run volume error is 0.0 % for every engine. — [TUFLOW 2017 UK EA 2D Benchmarking Results](https://tuflow.com/media/5017/2017-uk-ea-2d-benchmarking-results-update-latest-tuflow-solvers.pdf)
- **Older validation figure, thesis, Classic era (a).** Huxley (2004) reports TUFLOW within 2 % of analytical estimates in 97 % of the benchmark models (culverts, weirs, channels, floodplains). The analytic-dam-break check of HPC (Sheehy et al. 2018) gives no error metric. — [TUFLOW Wiki, TUFLOW Benchmarking](https://wiki.tuflow.com/TUFLOW_Benchmarking)

### Inferences
- [Certain] TUFLOW's only published pass/fail-type numbers are ±1 % cumulative mass error, the stability flags (-0.1 m negative depth, the control-number limits, 1/10 of a Classic step) and the cells-across-a-flow-path rule.
- [Certain] For (b) and (c), whether cell size, HPC against Classic, SGS or Quadtree, TUFLOW gives methods and examples but leaves the tolerance blank, and its developers say in print that none has been established.
- [Likely] "A few per cent of depth" between HPC 2nd order and Classic is the nearest vendor statement to the project's "within 3 % of the squares". It describes typical observed difference in peak level as a share of depth, not of peak discharge, and it is not offered as an acceptance rule.
- [Likely] TUFLOW's recommended reference for convergence is the finest feasible cell size, or a converged answer, never a peer mesh at the same cell size. A gate "within 3 % of the 20 m squares" therefore differs in kind from TUFLOW's practice: it compares two unconverged meshes. TUFLOW's histogram method (95 % of points within ± a tolerance of the finest mesh) is the closest published template for a defensible replacement.

### Gaps
- No TUFLOW document found states a Quadtree against uniform tolerance or any number from Quadtree validation.
- The 2025.2 page's claim that HPC fully conserves 2D mass was seen only in a search summary.
- The EA 2013 results for TUFLOW HPC were not read in the EA's own text.

## Q3. InfoWorks ICM 2D (Autodesk/Innovyze) and MIKE 21 FM (DHI)

### Takeaway
Neither vendor publishes a validation report with tolerances that could be found. Both give mass-balance guidance only. ICM's help gives a node rule of thumb (volume balance above 0.5 % of node throughput signals instability), and an Autodesk blog gives under 5 % for the 2D summary as usually acceptable (seen only in a search snippet). DHI's knowledge base is purely qualitative; a 2011 DHI UK blog gives under 2 % as a rule of thumb and quotes the EA Fluvial Design Guide's 5 % review trigger.

### Cited Findings
- **ICM node volume balance (d, e).** The ICM help says a node volume balance above about 0.5 % of the total flow through the node, positive or negative, signals instability. It suggests an SQL query on sim.volbal with 0.05 as a placeholder to change, and recommends volume-balance tolerances of 0.01 with scaling factor 1.0 for initialisation and simulation. A shorter time step sometimes removes instabilities. No version is stated on the page. — [Autodesk ICM Help 2024, Computational Instabilities](https://help.autodesk.com/cloudhelp/2024/ENU/ICM-Help/files/GUID-2C5C3870-5BC6-487C-8306-AA7397CDD239.htm)
- **ICM 2D summary volume balance (d), second-hand, page not fetched (403).** According to the search engine's summary, an Autodesk water blog of January 2018 says the 2D summary volume-balance error should be close to 0 % and under 5 % is usually acceptable. Larger errors are listed by location, nearly always at the 1D-2D interface. — [Autodesk blog, Troubleshooting hydraulic models in InfoWorks ICM, 2018-01-09](https://www.autodesk.com/blogs/water/2018/01/09/troubleshooting-hydraulic-models-in-infoworks-icm/)
- **ICM benchmark claim (a), vendor press release reposted.** Innovyze said ICM successfully completed all tests of the EA's 2013 benchmarking. The EA report defines no pass/fail, see Q5. — [Innovyze press release (2013), reposted](https://swmm56.blogspot.com/2013/08/uk-environment-agency-study-confirms.html)
- **MIKE 21 FM volume balance (d).** DHI's knowledge base says the 2D volume balance is in the simulation log and an HTML file. The check is whether the continuity error is small relative to the volumes involved; no number and no date are given. — [DHI Knowledge Base KA-01032](https://support.dhigroup.com/knowledgebase/article/KA-01032/en-us)
- **MIKE FLOOD rule of thumb (d), DHI UK blog, 11 July 2011.** Mass errors should generally be under 2 %. Above 2 %, find the cause and location and assess the consequence. Above 5 %, the schematisation is not robust and needs review, a figure attributed to the EA Fluvial Design Guide. — [MIKE by DHI UK and Ireland blog, "TIPS: MIKE FLOOD", 2011](https://dhiuk-demos.blogspot.com/2011/07)
- **MIKE 21 FM verification (a).** DHI's product short description says only that, before first release, the model was applied to idealised cases comparable with analytical solutions or literature; it gives no numbers. — [DHI MIKE 21/3 FM HD Short Description](https://www.mikepoweredbydhi.com:443/-/media/shared%20content/mike%20by%20dhi/flyers%20and%20pdf/product-documentation/short%20descriptions/mike213_fm_hd_short_description.pdf)

### Inferences
- [Likely] ICM's 0.5 % rule is a per-node instability flag for 1D nodes, not a 2D acceptance criterion. The 5 % figure is a blog's practitioner guidance, not a help-file rule.
- [Likely] The 5 % mass-error trigger that recurs in UK practice traces to the EA's Fluvial Design Guide, an agency guide and not a vendor rule. DHI UK's 2 % is its own rule of thumb.
- [Certain] Neither vendor, in anything found, states a tolerance for (b) mesh convergence or (c) a new mesh type or option against a reference.

### Gaps
- No public ICM 2D verification and validation report or MIKE 21 FM validation report with error metrics was found.
- DHI's validation documentation, if any, may sit behind its software portal.
- The Autodesk 2018 blog text could not be fetched directly.
- The Fluvial Design Guide's own wording was not checked.

## Q4. Flood Modeller 2D (Jacobs), Iber, Deltares D-Flow FM / SOBEK

### Takeaway
None of the three publishes acceptance thresholds. Flood Modeller's only number is an example stop-on-error setting of 5 %. Iber's 2020 benchmark reports differences against the EA report's packages (under 1 % on peak levels) and mass errors (under 0.05 %) as results, not as criteria. Deltares' D-Flow FM validation document was, as of 2015, unpublished. Its testbench of about 249 cases is run and checked automatically for regression, with no published tolerance found.

### Cited Findings
- **Flood Modeller 2D stop-on-mass-error (d, e).** The 2D solver can stop a run when an absolute mass-balance error is exceeded. The help's example uses 5 % after the first 1,800 s (flag_mass_error, tolerance_pct 5.0, check_after_seconds 1800), presented as an example and not a recommended default. The delay exists because early-run percentages are high while cumulative inflow is small. — [Flood Modeller Help, Stopping Runs that Exceed a Pre-defined % Mass Balance Error](https://help.floodmodeller.com/docs/stopping-runs-that-exceed-a-pre-defined-mass-balance-error)
- **Flood Modeller mass-balance definitions (d).** The percentage is the volume discrepancy against the maximum system volume increase, or alternatively against boundary inflow. The user should judge whether the discrepancy is within acceptable limits; no number is given. The page was updated 2024-05-02 and is flagged stale. — [Flood Modeller Help, 1D Mass Balance Calculations](https://help.floodmodeller.com/docs/1d-mass-balance-calculations)
  - According to the search summary, another help page warns the percentage can be larger on the rising limb. — [Flood Modeller Help, Mass Balance Files and Calculations](https://help.floodmodeller.com/docs/mass-balance-files-and-calculations)
- **Iber benchmark, 2020 (a), developers' own report.** Cea, Bladé, Sanz-Ramos et al. run 11 tests, some from the EA suite. Their results:
  - Test 1: peak and final levels within 1 % of expected.
  - EA-type tests: maximum levels within 1 % of the values in the EA report (for example 0.31, 0.12, 0.54 and 0.50 % at named points, TUFLOW as reference).
  - A laboratory junction: mean error under 2.5 % and R² up to 0.99.
  - Rain on a basin at 10, 20, 40 and 80 m elements: accumulated mass-balance error under 0.05 %, at most 3.25e-4 at 10 m and about 4.6e-10 at the coarser meshes.
  
  All are stated as results; no acceptance criterion was found in a full-text search. CFL is set adaptively between 0.35 and 0.9 by scheme. — [Iber 2020 benchmark report, doi:10.17979/spudc.9788497497640](https://ruc.udc.es/entities/publication/b9a62a6a-ffaf-49aa-aaa0-81f04fe26240/full)
- **D-Flow FM (a, c).** A 2015 Deltares presentation gives validation two purposes: quality of results, and consistency over time through regression testing. It reports 249 test cases run and checked automatically. The validation document covered 2D(+1D) hydrodynamics, had been partly reviewed and was not yet officially published. — [Delft Software Days 2015, Validation of Delft3D FM, van Dam](https://www.slideshare.net/Delft_Software_Days/dsdint-2015-validation-of-delft3-d-fm-van-dam)

### Inferences
- [Likely] Iber's "under 1 % of the reference packages" is the same kind of evidence as the project's "within 3 % of the squares": agreement with peers, reported after the fact, with no criterion set before.
- [Guessing] Deltares' automated testbench almost certainly compares against stored reference results with numeric tolerances, but these are regression tolerances (detecting code change), not accuracy acceptance, and none was found in public.

### Gaps
- No published D-Flow FM validation document, SOBEK 2D validation document or Flood Modeller 2D benchmark report was found.
- No public acceptance threshold was found for any of the three vendors.
- Iber's user manual was not checked for mass-balance or CFL guidance beyond the benchmark report.

## Q5. Threshold stated, or comparison only, for checks (a) to (e); and what the benchmark funder (UK EA) used

### Takeaway
Across all seven vendors, published numeric thresholds exist only for (d) mass or volume error and (e) run-time stability or time step. For (a) analytic or lab verification, (b) cell-size convergence and (c) a new mesh type, solver or feature against a reference, every vendor shows comparisons with no pass mark. TUFLOW says explicitly that criteria are study-specific and not yet established. The EA benchmark that most vendors cite also judges by the spread among full shallow-water models, with no pass/fail, and accepted spreads far wider than 3 % (peak levels within 0.4 m, travel times within about 20 % on its dam-break valley test).

### Cited Findings
- **The EA benchmark judges by spread, not by rule.** In the EA's 2010 report (SC080035/SR2):
  - Test 2: the full models' level differences were small and within the accuracy acceptable in practice. Simplified models differing by more than about 0.05 m might also be acceptable, depending on the accuracy needed.
  - Test 5 (dam-break valley): the full models agreed on travel times within about 20 % and on peak levels within 0.4 m, differences the EA judged unlikely to exceed the accuracy needed in practice.
  - Test 3: no exact solution exists.
  - RFSM depths fell within 10 to 20 % of the full models.
  
  — [EA, Benchmarking of 2D Hydraulic Modelling Packages, SC080035/SR2, 2010](https://assets.publishing.service.gov.uk/media/5a75765c40f0b6360e4744dd/scho0510bsno-e-e.pdf); publication page [gov.uk, 14 Aug 2013 bundle](https://www.gov.uk/government/publications/benchmarking-the-latest-generation-of-2d-hydraulic-flood-modelling-packages)
- **Mass error thresholds found (d):**
  - TUFLOW Classic ±1 %, with HPC "up to 1 %" on the wiki. — [TUFLOW Manual 2026.3](https://docs.tuflow.com/classic-hpc/manual/2026.3/12-Checks-and-Logs.html); [HPC Model Review](https://wiki.tuflow.com/HPC_Model_Review)
  - ICM: 0.5 % of node throughput as an instability flag; 5 % for the 2D summary in a blog. — [ICM Help](https://help.autodesk.com/cloudhelp/2024/ENU/ICM-Help/files/GUID-2C5C3870-5BC6-487C-8306-AA7397CDD239.htm); [Autodesk blog 2018](https://www.autodesk.com/blogs/water/2018/01/09/troubleshooting-hydraulic-models-in-infoworks-icm/)
  - DHI UK: 2 %, with the Fluvial Design Guide's 5 %. — [DHI UK blog 2011](https://dhiuk-demos.blogspot.com/2011/07)
  - Flood Modeller: 5 %, as an example only. — [Flood Modeller Help](https://help.floodmodeller.com/docs/stopping-runs-that-exceed-a-pre-defined-mass-balance-error)
  - HEC-RAS: none; values are only called very low or extremely low. — [HEC-RAS 2D UM 6.6](https://www.hec.usace.army.mil/software/hec-ras/documentation/HEC-RAS_2D_Users_Manual_v6.6.pdf)
- **Stability and time-step numbers found (e):**
  - HEC-RAS: C about 1, up to 3 for SWE and 5 for diffusion wave. — [HEC-RAS 2D UM 6.6](https://www.hec.usace.army.mil/software/hec-ras/documentation/HEC-RAS_2D_Users_Manual_v6.6.pdf)
  - TUFLOW HPC: control-number limits, the 20 % breach, a 1/10-of-Classic step flag and -0.1 m negative depths. — [HPC Model Review](https://wiki.tuflow.com/HPC_Model_Review); [TUFLOW Manual 2026.3](https://docs.tuflow.com/classic-hpc/manual/2026.3/12-Checks-and-Logs.html)
  - Iber: CFL 0.35 to 0.9 as used. — [Iber 2020](https://ruc.udc.es/entities/publication/b9a62a6a-ffaf-49aa-aaa0-81f04fe26240/full)

### Inferences
Summary matrix. T = numeric threshold stated by the vendor; C = comparisons or metrics shown, no pass mark; G = guidance without numbers; — = nothing found.

| Vendor | (a) analytic/lab | (b) coarse vs fine | (c) new mesh/option vs reference | (d) mass/volume | (e) stability/time step |
|---|---|---|---|---|---|
| HEC-RAS 2D | C (ME, MAE, RMSE, NRMSE, R², volume %, order 1.32; skill-score grades) | C (one doubling per test, "almost the same"), G (always test) | C (SWE vs DW plots) | C (example % called very or extremely low) | T/G (C about 1, up to 3 or 5) |
| TUFLOW | C (EA tests; Huxley 2004: 2 % in 97 % of cases) | G (methods, tolerance left blank; "no criteria established"), T-like rule (cells across a flow path) | C/G (HPC vs Classic usually a few % of depth, 1st order above 10 %; CPU vs GPU under 1 mm) | T (±1 %) | T (control numbers, 20 %, 1/10 step, -0.1 m) |
| ICM 2D | C (vendor claim, EA 2013) | — | — | T (0.5 % node flag; 5 % blog) | G |
| MIKE 21 FM | G (idealised tests, no numbers) | — | — | G (DHI KB), T (DHI UK blog 2 %, FDG 5 %) | — |
| Flood Modeller 2D | — | — | — | Example 5 % stop | Example stop setting |
| Iber | C (under 1 % vs EA packages; lab under 2.5 %) | C (mass error across 10 to 80 m) | — | C (under 0.05 %) | Values used (CFL 0.35 to 0.9) |
| D-Flow FM / SOBEK | Automated testbench, tolerances not published | — | — | — | — |

- [Certain] No vendor publishes a tolerance of the form "a new mesh type (or SGS, Quadtree, breakline refinement) must be within x % of a reference run". The 3 % rule in the brief has no vendor precedent in that form.
- [Likely] Where vendors judge a new option at all, they compare against a finer or converged answer (TUFLOW: the finest feasible cell size; HEC: an analytic solution with an order of convergence) or against the spread of independent full shallow-water models (EA, RD-51, Iber). They do not compare against a peer mesh at the same cell size. A same-size peer comparison can pass when the two meshes share an error and fail when only one carries it, which is the situation recorded in W46 to W48.
- [Likely] For a defensible replacement gate, the published practice points to:
  - an error against the converged (finest feasible) answer, not against the 20 m squares;
  - a field statistic, such as TUFLOW's "95 % of points within ± tolerance", rather than a single dam-line peak;
  - the tolerance set before the run and tied to what the design needs (TUFLOW: document it and agree it with stakeholders).
- [Likely] The magnitudes vendors live with, on the evidence above:
  - Peak-level differences of a few per cent of depth between their own solvers (TUFLOW).
  - 0.8 to 1.5 % mean depth error at coarse cells on a smooth analytic case (HEC).
  - Agreement within 1 % of peer packages on simple EA tests (Iber).
  - 0.4 m peak level and about 20 % arrival time among full models on a dam-break valley (EA).
  - Measured against these, a 3 % peak-discharge band is in the range vendors quote for agreement on easy cases, not a hard industry standard.

### Gaps
- The EA's 2013 update (SC120002) was not read; the judgement statements above are from the 2010 report.
- No vendor statement was found for peak discharge specifically, as opposed to level or depth. The vendors' language is almost entirely about water level, depth, extent and arrival time, so a discharge-based gate has no direct vendor analogue.
- Courant and time-step guidance for ICM, MIKE 21 FM, Flood Modeller 2D and D-Flow FM was not researched in depth; none surfaced in the searches made.
