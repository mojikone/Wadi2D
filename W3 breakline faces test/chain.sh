#!/bin/bash
export NUMBA_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
python run_matrix.py > results/matrix.log 2>&1
python analyse.py > results/matrix_summary.txt 2>&1
python run_still_dry.py > results/still_dry.txt 2>&1
python run_bent.py > results/bent.txt 2>&1
python run_alignment.py > results/alignment.txt 2>&1
python run_valley.py > results/valley.txt 2>&1 &
python run_fan.py 20 > results/fan_20m.txt 2>&1 &
wait
python run_fan.py 10 > results/fan_10m.txt 2>&1
python run_regress.py > results/regress.txt 2>&1
python run_bench.py > results/bench.txt 2>&1
echo finished > results/chain.done
