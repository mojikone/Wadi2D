"""Write the domain and the first job."""
import sys

sys.path.insert(0, r"D:\Mojtaba\Renardet\Wadi2D\W1 research and design note\validation\block2_full\scripts")
from common import domain, hms_reference, job, lumped_outlets, storm, write_domain, write_job

p = write_domain()
print(p, domain().area / 1e6)
print(lumped_outlets())
print(storm(74.304)["storm_area_km2"], storm()["depth_mm"], storm()["duration_min"])
j = job("c20_A74_probe", 20.0, area=74.304)
print(write_job(j, "c20_A74_probe"))
print(hms_reference())
