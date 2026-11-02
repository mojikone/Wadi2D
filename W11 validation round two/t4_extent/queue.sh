#!/bin/bash
cd "/d/Mojtaba/Renardet/Wadi2D/W11 validation round two/t4_extent"
export PYTHONDONTWRITEBYTECODE=1
P=/d/Mojtaba/Renardet/Wadi2D/.venv/Scripts/python.exe
for n in "$@"; do nvidia-smi --query-gpu=memory.free --format=csv,noheader; $P run_wadi.py $n; done
echo ALLDONE
