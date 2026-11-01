#!/bin/bash
# usage: queue_head.sh job1 ...; the same jobs on the later engine snapshot, to see whether the numbers moved
V="/d/Mojtaba/Renardet/Wadi2D/W1 research and design note/validation/block2_full"
PY=/d/Mojtaba/Renardet/Wadi2D/.venv/Scripts/python.exe
cd "$V/engine_63d580c"
export PYTHONPATH="$V/engine_63d580c"
for j in "$@"; do
  echo "== $j $(date)"
  $PY -m wadi2d.engine.cli run "$V/jobs/$j.json" --out "$V/runs/$j" > "$V/logs/$j.log" 2>&1
  echo "== $j exit $? $(date)"
done
