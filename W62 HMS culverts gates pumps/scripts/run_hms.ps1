# Run a Jython script in HEC-HMS 4.12 with no window: what HEC-HMS.cmd -s does, with java called directly.
# Usage: powershell -File run_hms.ps1 <script.py> <log.txt>
param([string]$Script, [string]$Log)
$h = 'C:\Program Files\HEC\HEC-HMS\4.12'
$env:PATH = "$h\bin;$h\bin\gdal;$h\bin\taudem;$env:PATH"
$env:PROJ_LIB = "$h\bin\gdal\projlib"
$env:GDAL_DATA = "$h\bin\gdal\gdal-data"
$jars = "$h\hms.jar;$h\lib\*"
$arguments = @('-Dsun.java2d.d3d=false', '-DMapPanel.NoVolatileImage=true', '-Dpython.import.site=false', '-Xms32M',
    "`"-Dpython.path=$jars`"", "`"-Djava.library.path=$h\bin;$h\bin\gdal;$h\bin\hdf`"", '-classpath', "`"$jars`"",
    'hms.Hms', '-s', "`"$Script`"")
$p = Start-Process -FilePath "$h\jre\bin\java.exe" -WorkingDirectory $h -ArgumentList $arguments -NoNewWindow -Wait `
    -PassThru -RedirectStandardOutput $Log -RedirectStandardError "$Log.err"
"HEC-HMS exit $($p.ExitCode)"
