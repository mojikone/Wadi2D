#!/bin/bash
# usage: queue.sh job1 job2 ...; runs each job in turn into runs/<job>, on the frozen engine snapshot
V="/d/Mojtaba/Renardet/Wadi2D/W1 research and design note/validation/block2_full"
PY=/d/Mojtaba/Renardet/Wadi2D/.venv/Scripts/python.exe
cd "$V/engine_3f32ca6"
export PYTHONPATH="$V/engine_3f32ca6"
for j in "$@"; do
  echo "== $j $(date)"
  $PY -m wadi2d.engine.cli run "$V/jobs/$j.json" --out "$V/runs/$j" > "$V/logs/$j.log" 2>&1
  echo "== $j exit $? $(date)"
done
