#!/bin/sh
# Bidah rain-on-grid and the fan window on the fix, same jobs as the HEC-RAS comparisons. Default engine settings, so the fix is on.
cd "$(dirname "$0")"
V="../W1 research and design note/validation"
W=../.venv/Scripts/wadi2d.exe
for n in 20m_n050_em 10m_n050_em; do
  $W run "$V/ras_rain_on_grid/jobs/$n.json" --out "runs/bidah_$n" --backend gpu > "runs_bidah_$n.log" 2>&1
  echo "bidah $n exit $?"
done
$W run "$V/ras_head_to_head/job_10m.json" --out runs/fan_10m --backend gpu > runs_fan_10m.log 2>&1
echo "fan exit $?"
