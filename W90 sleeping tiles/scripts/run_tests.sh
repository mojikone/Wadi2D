#!/bin/sh
# The test files that touch what W90 changed, one file at a time (memory); per file the exit code of pytest (0 is
# all passed), its count line and any failure lines, into a log.
#   sh run_tests.sh <log file> <test file> [<test file> ...]
log="$1"
shift
PY="D:/Mojtaba/Renardet/Wadi2D/.venv/Scripts/python.exe"
: > "$log"
for f in "$@"; do
    out=$("$PY" -m pytest "$f" -p no:cacheprovider -o addopts="" -q 2>&1)
    code=$?
    echo "$f :: exit $code :: $(echo "$out" | grep -E "passed|failed|error|no tests ran" | tail -1)" >> "$log"
    echo "$out" | grep -E "^(FAILED|ERROR)" >> "$log"
done
echo "done" >> "$log"
