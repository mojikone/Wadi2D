from java.lang import System
print(System.getProperty("java.library.path"))
try:
    System.loadLibrary("gdalalljni"); print("loaded gdalalljni")
except Exception as e:
    print("load failed", e)
from org.gdal.gdal import gdal
print(gdal.VersionInfo())
