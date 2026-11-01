#!/bin/bash
# usage: queue_ras.sh name1 name2 ...; RAS runs one after another, so their wall times stay clean
V="/d/Mojtaba/Renardet/Wadi2D/W1 research and design note/validation/ras_rain_on_grid"
cd "$V"
export PYTHONPATH="$V/engine_609462d"
for n in "$@"; do
  echo "== $n start $(date)"
  python build_case.py "$n"
  python run_ras.py "ras_$n" Bidah
  echo "== $n exit $? $(date)"
done
