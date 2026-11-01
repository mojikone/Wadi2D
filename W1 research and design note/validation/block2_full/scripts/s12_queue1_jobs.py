"""First queue: Manning at one storm area, 36 h for the sensitivity."""
import sys
sys.path.insert(0, r"D:\Mojtaba\Renardet\Wadi2D\W1 research and design note\validation\block2_full\scripts")
from common import OUT, domain, job, write_domain, write_job

p = write_domain()
d = domain()
print(d.geom_type, d.area / 1e6, len(getattr(d, "interiors", [])))
A = 74.304
write_job(job("c20_A74_n040", 20.0, area=A, duration_s=172800.0), "c20_A74_n040")
for tag in ("050", "100", "200"):
    write_job(job(f"c20_A74_h{tag}", 20.0, area=A, duration_s=129600.0,
                  manning_raster=str(OUT / "manning" / f"hills_{tag}.tif")), f"c20_A74_h{tag}")
write_job(job("c20_A74_u100", 20.0, area=A, duration_s=129600.0, manning=0.1), "c20_A74_u100")
