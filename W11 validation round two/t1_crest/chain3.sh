#!/bin/bash
cd "/d/Mojtaba/Renardet/Wadi2D/W11 validation round two/t1_crest"
export PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="/d/Mojtaba/Renardet/Wadi2D/W11 validation round two/engine_f976c23"
P=/d/Mojtaba/Renardet/Wadi2D/.venv/Scripts/python.exe
until grep -q "^ras_a96_20," ras_timing.csv; do sleep 30; done
for n in "$@"; do
  echo "== $n start $(date)"
  $P build.py "$n"
  python run_ras.py "ras_$n" Bidah
  echo "== $n exit $? $(date)"
done
