"""W98: the NRCS 24-hour distributions against their source.

Source: HEC-HMS 4.12, ``C:/Program Files/HEC/HEC-HMS/4.12/hms.jar``, class ``hms/model/met/e/aT`` (the same arrays in
``aV``), the 1441 ordinates a minute its SCS Storm uses, read from the class file by
``W98 lumped ARF at entry area/scripts/scs_check.py``; every sixth ordinate is the NRCS 0.1-hour table to four
decimals, and the minutes between lie on a natural cubic spline through those, as HMS gives them to four significant
figures. The values below are HMS's own ordinates at minutes between the 0.1-hour knots, copied from
``results/scs_hms_4_12_minutes.csv`` of that folder.

W95 typed 23 ordinates of each type from memory; against HMS the largest differences were Type I -0.0060 (20 h), IA
-0.0066 (20 h), II -0.0285 (11.75 h) and III -0.0169 (11.75 h).
"""

from __future__ import annotations

import numpy as np
import pytest

from wadi2d.storm.patterns import scs_curve
from wadi2d.storm.scs_tables import SCS_KNOTS

HMS_ROUNDING = 6e-5
"""HMS holds its minutes to four significant figures; the spline through the knots is within half a unit of that."""
HMS_4_12_MINUTES = {
    "I": {123: 0.0359, 363: 0.1263, 483: 0.1961, 573: 0.3102, 597: 0.4943, 603: 0.5258, 663: 0.6264, 693: 0.6585,
          705: 0.6703, 711: 0.6759, 717: 0.6813, 723: 0.6866, 729: 0.6918, 753: 0.7116, 843: 0.7716, 1203: 0.933},
    "IA": {123: 0.05153, 363: 0.209, 483: 0.4329, 573: 0.5528, 597: 0.5741, 603: 0.5796, 663: 0.6262, 693: 0.647,
           705: 0.6546, 711: 0.6584, 717: 0.6622, 723: 0.6658, 729: 0.6696, 753: 0.6848, 843: 0.7377, 1203: 0.9138},
    "II": {123: 0.0226, 363: 0.0809, 483: 0.1211, 573: 0.1646, 597: 0.179, 603: 0.183, 663: 0.2387, 693: 0.2923,
           705: 0.3855, 711: 0.4968, 717: 0.6259, 723: 0.6775, 729: 0.6893, 753: 0.7393, 843: 0.8219, 1203: 0.9526},
    "III": {123: 0.0205, 363: 0.07279, 483: 0.1153, 573: 0.1681, 597: 0.1866, 603: 0.1915, 663: 0.2538, 693: 0.3053,
            705: 0.3559, 711: 0.391, 717: 0.454, 723: 0.546, 729: 0.609, 753: 0.708, 843: 0.8134, 1203: 0.9577},
}  # fmt: skip
NRCS_ANCHORS = {"I": (100, 0.515), "IA": (80, 0.425), "II": (120, 0.663), "III": (120, 0.500)}
"""The 0.1-hour index and ordinate each type is known by: I at 10 h, IA at 8 h, II and III at 12 h (NRCS TR-55)."""
W95_WORST = {"I": (20.0, 0.926), "IA": (20.0, 0.906), "II": (11.75, 0.357), "III": (11.75, 0.339)}
"""W95's ordinate where it was furthest from HMS, and what it read."""


@pytest.mark.parametrize("scs_type", list(SCS_KNOTS))
def test_the_curve_is_hms_s_between_the_knots(scs_type) -> None:
    minutes, fraction = scs_curve(scs_type)
    assert minutes.size == 1441 and fraction[0] == 0.0 and fraction[-1] == 1.0
    assert np.all(np.diff(fraction) >= 0.0), "no minute takes rain back"
    for minute, hms in HMS_4_12_MINUTES[scs_type].items():
        assert abs(fraction[minute] - hms) <= HMS_ROUNDING, (scs_type, minute)
    assert np.array_equal(fraction[::6], np.asarray(SCS_KNOTS[scs_type])), "the knots are the 0.1-hour table"


@pytest.mark.parametrize("scs_type", list(SCS_KNOTS))
def test_the_nrcs_anchor_and_w95_s_worst_ordinate(scs_type) -> None:
    index, ordinate = NRCS_ANCHORS[scs_type]
    assert SCS_KNOTS[scs_type][index] == ordinate
    hour, w95 = W95_WORST[scs_type]
    _minutes, fraction = scs_curve(scs_type)
    assert abs(fraction[int(hour * 60)] - w95) > 0.005, "the corrected curve is not W95's"
