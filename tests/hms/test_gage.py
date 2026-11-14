"""The HMS ``.gage`` file: gages in HEC-HMS 4.12's layout, with the record in the default variant (W54)."""

from __future__ import annotations

from pathlib import Path

import pytest

from wadi2d.hms import gage

GAGES = """Gage Manager: Calibration
     Version: 4.12
     Filepath Separator: \\
End:

Gage: Lihban flow
     Gage Type: Flow
     Units: M3/S
     Data Type: INST-VAL
     Variant: Variant-1
       Default Variant: Yes
       DSS File Name: data\\Calibration.dss
       DSS Pathname: //Lihban flow/FLOW//6MIN/GAGE/
     End Variant: Variant-1
End:

Gage: Rain A
     Gage Type: Precipitation
     Units: MM
     Data Type: PER-CUM
     Latitude Degrees: 23
     Latitude Minutes: 48
     Latitude Seconds: 0
     Longitude: 57.25
     Variant: Variant-1
       DSS File Name: Old.dss
       DSS Pathname: //Rain A/PRECIP-INC//1MIN/OLD/
     End Variant: Variant-1
     Variant: Variant-2
       Default Variant: Yes
       DSS File Name: C:\\HMS\\Rain.dss
       DSS Pathname: //Rain A/PRECIP-INC//1MIN/GAGE/
     End Variant: Variant-2
End:
"""


def test_gages_read_with_their_default_variant_and_position(tmp_path: Path) -> None:
    path = tmp_path / "Calibration.gage"
    path.write_text(GAGES, encoding="utf-8")
    flow, rain = gage.load(path)
    assert (flow.name, flow.kind, flow.is_rain) == ("Lihban flow", "Flow", False)
    assert flow.dss_file == tmp_path / "data" / "Calibration.dss" and flow.pathname == "//Lihban flow/FLOW//6MIN/GAGE/"
    assert rain.is_rain and rain.pathname.endswith("/GAGE/") and rain.dss_file == Path("C:/HMS/Rain.dss")
    assert rain.latitude == pytest.approx(23.8) and rain.longitude == pytest.approx(57.25)
    assert flow.latitude is None


def test_a_project_with_only_its_manager_block_has_no_gages(tmp_path: Path) -> None:
    path = tmp_path / "Empty.gage"
    path.write_text("Gage Manager: Empty\n     Version: 4.12\nEnd:\n", encoding="utf-8")
    assert gage.load(path) == []
    assert gage.beside(None, tmp_path / "Empty.basin") == path
    assert gage.beside(tmp_path / "Other.hms", None) is None


BLOCK2 = Path(r"D:\Mojtaba\Renardet\2224 WS11\Batinah\Block 2\Hydrology\HEC_HMS_Block_02\HEC_HMS_Block_02.gage")


@pytest.mark.skipif(not BLOCK2.is_file(), reason="his Block 2 HMS project is not on this machine")
def test_his_block_2_gage_file_is_empty_and_reads_so() -> None:
    assert gage.load(BLOCK2) == []
