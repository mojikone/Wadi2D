"""Print the pathnames of an HMS result DSS file."""

import sys

import hecdss

dss = hecdss.HecDss(sys.argv[1])
try:
    for path in dss.get_catalog().uncondensed_paths:
        print(path)
finally:
    dss.close()
