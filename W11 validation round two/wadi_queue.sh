#!/bin/bash
export PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="/d/Mojtaba/Renardet/Wadi2D/W11 validation round two/engine_f976c23"
P=/d/Mojtaba/Renardet/Wadi2D/.venv/Scripts/python.exe
cd "/d/Mojtaba/Renardet/Wadi2D/W11 validation round two/t1_crest"
for n in z94_20 z96_20 z94_10 z96_10; do $P build.py $n --wadi-only; nvidia-smi --query-gpu=memory.free --format=csv,noheader; $P run_wadi.py $n; done
cd "/d/Mojtaba/Renardet/Wadi2D/W11 validation round two/t2_faydh"
for n in 20m_n050_em 10m_n050_em; do $P build_case.py $n --wadi-only; nvidia-smi --query-gpu=memory.free --format=csv,noheader; $P run_wadi.py $n; done
echo ALLDONE
