"""Print the reservoir blocks of HEC-HMS 4.12's own samples that carry a pattern (Gate, Pump, Culvert): the format.

Usage: ``python sample_blocks.py <regex>``. Reads ``samples.zip`` in place, writes nothing.
"""

import re
import sys
import zipfile

SAMPLES = r"C:\Program Files\HEC\HEC-HMS\4.12\samples.zip"

with zipfile.ZipFile(SAMPLES) as archive:
    for name in archive.namelist():
        if not name.endswith(".basin"):
            continue
        text = archive.read(name).decode("utf-8", "replace")
        for block in re.split(r"\n(?=\S)", text):
            if block.startswith("Reservoir:") and re.search(sys.argv[1], block):
                print("=====", name)
                print(block)
