"""Print the numeric and string constants of HEC-HMS 4.12's classes under a package, in constant-pool order: where its
culvert routine keeps the FHWA HDS-5 coefficients and its tolerances. Reads ``hms.jar`` in place, writes nothing.

Usage: ``python class_constants.py <prefix> [min count of doubles]``.
"""

import struct
import sys
import zipfile

JAR = r"C:\Program Files\HEC\HEC-HMS\4.12\hms.jar"


def constants(data: bytes) -> list[tuple[str, object]]:
    count = struct.unpack(">H", data[8:10])[0]
    out: list[tuple[str, object]] = []
    at = 10
    index = 1
    while index < count:
        tag = data[at]
        if tag == 1:
            length = struct.unpack(">H", data[at + 1 : at + 3])[0]
            out.append(("s", data[at + 3 : at + 3 + length].decode("utf-8", "replace")))
            at += 3 + length
        elif tag in (3, 4):
            raw = data[at + 1 : at + 5]
            out.append(("i", struct.unpack(">i", raw)[0]) if tag == 3 else ("f", struct.unpack(">f", raw)[0]))
            at += 5
        elif tag in (5, 6):
            raw = data[at + 1 : at + 9]
            out.append(("l", struct.unpack(">q", raw)[0]) if tag == 5 else ("d", struct.unpack(">d", raw)[0]))
            at += 9
            index += 1
        elif tag in (7, 8, 16, 19, 20):
            at += 3
        elif tag == 15:
            at += 4
        elif tag in (9, 10, 11, 12, 17, 18):
            at += 5
        else:
            raise ValueError(f"tag {tag}")
        index += 1
    return out


prefix = sys.argv[1]
minimum = int(sys.argv[2]) if len(sys.argv) > 2 else 1
with zipfile.ZipFile(JAR) as jar:
    for name in sorted(jar.namelist()):
        if not name.startswith(prefix) or not name.endswith(".class"):
            continue
        pool = constants(jar.read(name))
        numbers = [v for k, v in pool if k in ("d", "f")]
        if len(numbers) < minimum:
            continue
        print("=====", name, len(numbers), "doubles")
        print(" ".join(f"{v:g}" for v in numbers))
        strings = [v for k, v in pool if k == "s" and not v.startswith(("(", "L", "[")) and " " in v]
        if strings:
            print("  strings:", strings[:40])
