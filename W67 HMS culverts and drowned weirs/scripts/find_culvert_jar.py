"""List the entries of HEC-HMS 4.12's jars under a package (default ``culvert/``): where the culvert routine and its
coefficient tables live. Reads the jars in place, writes nothing.

Usage: ``python find_culvert_jar.py [prefix]``.
"""

import sys
import zipfile
from pathlib import Path

ROOT = Path(r"C:\Program Files\HEC\HEC-HMS\4.12")
prefix = sys.argv[1] if len(sys.argv) > 1 else "culvert/"
for jar in [ROOT / "hms.jar", *sorted((ROOT / "lib").glob("*.jar"))]:
    try:
        with zipfile.ZipFile(jar) as archive:
            names = [n for n in archive.namelist() if n.startswith(prefix)]
    except zipfile.BadZipFile:
        continue
    if names:
        print(jar.name, len(names))
        for name in names:
            print("  ", name)
