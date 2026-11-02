from pathlib import Path
p = Path(r"D:\Mojtaba\Renardet\Wadi2D\wadi2d\hms\dss.py")
s = p.read_bytes().decode("utf-8")
crlf = "\r\n" in s
t = s.replace("\r\n", "\n")

old = """Interface: :func:`open_dss`, :class:`DssFile`, :class:`TimeSeries`, :class:`PairedTable`,
:class:`DssPathname` and the F-part helpers :func:`run_fpart`, :func:`daa_fpart`, :func:`met_fpart`.
"""
new = """Interface: :func:`open_dss`, :class:`DssFile`, :class:`TimeSeries`, :class:`PairedTable`, :class:`GridRecord`,
:class:`DssPathname` and the F-part helpers :func:`run_fpart`, :func:`daa_fpart`, :func:`met_fpart`.
"""
assert t.count(old) == 1
t = t.replace(old, new)

old = """class DssLookupError(KeyError):
    \"\"\"No catalogue pathname, or more than one, matches the request.\"\"\"
"""
new = """@dataclass(frozen=True)
class GridRecord:
    \"\"\"A gridded record as stored: ``values`` is (rows, columns) with the southern row first.\"\"\"

    pathname: DssPathname
    values: np.ndarray
    lower_left_x: int
    lower_left_y: int
    cell_size: float
    x_cell_zero: float
    y_cell_zero: float
    null_value: float
    units: str
    grid_type: int
    srs: str


class DssLookupError(KeyError):
    \"\"\"No catalogue pathname, or more than one, matches the request.\"\"\"
"""
assert t.count(old) == 1
t = t.replace(old, new)

old = """def open_dss(path: str | Path, *, readonly: bool = True) -> DssFile:
"""
new = """    def grid_pathnames(self) -> list[DssPathname]:
        \"\"\"Every gridded record; grids are never condensed, so each keeps its own D and E.\"\"\"
        from hecdss.record_type import RecordType

        items = self._native.get_catalog().items
        return [DssPathname(i.A, i.B, i.C, i.D, i.E, i.F) for i in items if i.recType == RecordType.Grid]

    def read_grid(self, pathname: DssPathname) -> GridRecord:
        \"\"\"The gridded record at this pathname, as stored.\"\"\"
        grid = self._native.get(str(pathname))
        if grid is None:
            raise DssLookupError(f"no gridded record at {pathname}")
        return GridRecord(
            pathname=pathname,
            values=np.asarray(grid.data, dtype=float),
            lower_left_x=int(grid.lowerLeftCellX),
            lower_left_y=int(grid.lowerLeftCellY),
            cell_size=float(grid.cellSize),
            x_cell_zero=float(grid.xCoordOfGridCellZero),
            y_cell_zero=float(grid.yCoordOfGridCellZero),
            null_value=float(grid.nullValue),
            units=str(grid.dataUnits),
            grid_type=int(grid.type),
            srs=str(grid.srsDefinition),
        )


def open_dss(path: str | Path, *, readonly: bool = True) -> DssFile:
"""
assert t.count(old) == 1
t = t.replace(old, new)
if crlf:
    t = t.replace("\n", "\r\n")
p.write_bytes(t.encode("utf-8"))
print("edited; crlf", crlf)
