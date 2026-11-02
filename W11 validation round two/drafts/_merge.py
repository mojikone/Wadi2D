"""Merge the drafted sections into the README under Results. One use."""
from pathlib import Path

H = Path(__file__).resolve().parent
t1 = (H / "_t1_section.md").read_text(encoding="utf-8")
a = "| 94 m, 20 m, weir equation, **lattice** |"
b = "| 94 m, 10 m, **2D equations**, aligned, no coefficient | **638.8** | 536.6 | **0.840** | +7.5 | 1.011 | **+0.411** | 0.002 |\n" + a
assert a in t1
t1 = t1.replace(a, b)
a = "With overflow by the 2D equations RAS passes 627 m3/s with the pool only 0.25 m over the crest. That is C 7.8, 4.6 x critical flow for a free overfall on the crest [Certain, arithmetic], and it equals the natural peak of 628 as if the crest were not there."
b = "With overflow by the 2D equations RAS passes 627 m3/s at 20 m with the pool 0.25 m over the crest, and 639 at 10 m with it 0.20 m over: C 7.8 and 10.6, 4.6 and 6.2 x critical flow [Certain, arithmetic]. It moves away from critical as the mesh refines, and it stands at the natural peak of 622 to 628 as if the crest were not there."
assert a in t1
t1 = t1.replace(a, b)
a = "**It is outside the rule, it does not change the verdict, and it needs saying: on the only coefficient-free pair the two models differ by 19 % and 0.34 m.** Wadi2D sits on critical flow, 0.996 of it in the analytic test. `a94_10_2d` is running as the same check at 10 m."
b = "**It is outside the rule, it does not change the verdict, and it needs saying: on the only coefficient-free pair the two models differ by 16 % and 0.41 m at 10 m, so no independent check of crest discharge exists yet.** Wadi2D sits on critical flow, 0.996 of it in the analytic test."
assert a in t1
t1 = t1.replace(a, b)
r = H / "README.md"
t = r.read_text(encoding="utf-8")
t2 = "### Test 2, second catchment\n\nTo follow.\n\n"
body = t1 + "\n" + t2 + (H / "_t3_section.md").read_text(encoding="utf-8") + "\n" + (H / "_t4_section.md").read_text(encoding="utf-8")
assert "## Results\n\nTo follow.\n" in t
t = t.replace("## Results\n\nTo follow.\n", "## Results\n\n" + body)
r.write_text(t, encoding="utf-8")
print(len(t))
