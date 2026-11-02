#!/bin/bash
export NUMBA_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
until [ -f results/chain.done ]; do python -c "import time; time.sleep(15)"; done
python run_matrix.py > results/matrix.log 2>&1
python analyse.py > results/matrix_summary.txt 2>&1
python run_still_dry.py > results/still_dry.txt 2>&1
python run_bent.py > results/bent.txt 2>&1
echo finished > results/chain2.done
