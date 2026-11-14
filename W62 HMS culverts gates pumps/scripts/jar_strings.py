"""Print the string constants of HEC-HMS 4.12's classes that match a pattern: the candidate basin-file keys.

Usage: ``python jar_strings.py <package path inside hms.jar> <regex>``. Reads the jar in place, writes nothing.
"""

import re
import sys
import zipfile

JAR = r"C:\Program Files\HEC\HEC-HMS\4.12\hms.jar"

with zipfile.ZipFile(JAR) as jar:
    for name in sorted(jar.namelist()):
        if not name.startswith(sys.argv[1]) or not name.endswith(".class"):
            continue
        found = sorted({s.decode() for s in re.findall(rb"[ -~]{4,}", jar.read(name))})
        hits = [s for s in found if re.search(sys.argv[2], s)]
        if hits:
            print(name, hits)
