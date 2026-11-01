import json,sys
for fn in sys.argv[1:]:
    d=json.load(open(fn))
    print("=====",fn,d["ras_version"][:11],d["ras_equation"],d["ras_cores"],"RAS",d["ras_summary"]["Computation Time Total"],"W",d["wadi_done"]["loop_s"],d["wadi_done"]["tables_s"],d["wadi_done"]["steps"],d["wadi_done"]["dt_min"])
    print(" RAS end vol",d["ras_volume"]["Volume Ending"],"Wadi",d["wadi_done"]["balance"]["storage_end_m3"]/1000, "RAS err%",d["ras_volume"]["Error Percent"],"W err",d["wadi_done"]["balance"]["relative_error"])
    f=lambda v:{a:round(b,3) for a,b in v.items() if a in("n","mean","rms","p5","p50","p95")}
    print(" level wet ",f(d["max_level_wadi_minus_ras_m"]["wet_both_0.1"]))
    print(" level deep",f(d["max_level_wadi_minus_ras_m"]["deep_both_0.5"]))
    print(" mean depth",f(d["max_mean_depth_wadi_minus_ras_m"]), d["max_mean_depth_sum_m3"])
    for k,v in d["extent"].items(): print(" ",k,{a:round(b,3) for a,b in v.items()})
    for k,v in d["sections"].items(): print(" ",k,"pk R %.1f W %.1f (%+.2f%%) tpk %.0f/%.0f t50 %.1f/%.1f nse %.4f vol %.0f/%.0f"%(v["peak_ras"],v["peak_wadi"],v["peak_diff_pct"],v["t_peak_ras_min"],v["t_peak_wadi_min"],v["t_half_rise_ras_min"],v["t_half_rise_wadi_min"],v["nse_5min"],v["volume_ras_m3"]/1000,v["volume_wadi_m3"]/1000))
    print(" arrival",f(d["arrival_wadi_minus_ras_min"]))
    print(" speed",f(d["max_speed_5min_wadi_minus_ras_mps"]),d["max_speed_means_mps"], "ratio",f(d["max_speed_5min_ratio_wadi_over_ras"]))
