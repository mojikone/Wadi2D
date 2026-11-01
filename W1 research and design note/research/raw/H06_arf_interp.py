import math
import numpy as np

# --- Curve 1: project table "ARF Gonu" (fit from the workbook) ---
def arf_gonu(A):
    return 0.1971816 + (1.077106 - 0.1971816) / (1 + (A / 975.5382) ** 0.7625714)
gonu_nodes = [(28.26, 0.99886), (78.5, 0.97714), (153.86, 0.92), (200.96, 0.88457), (254.34, 0.85029),
              (314.0, 0.81714), (706.5, 0.67314), (1256.0, 0.57943)]

# --- Curve 2: UK FSR / FEH (Keers & Wescott 1977), D in hours ---
def arf_fsr(A, D=24.0):
    if A <= 20:
        a = 0.40 - 0.0208 * math.log(4.6 - math.log(A)); b = 0.0394 * A ** 0.354
    elif A < 100:
        a = 0.40 - 0.00382 * (4.6 - math.log(A)) ** 2; b = 0.0394 * A ** 0.354
    elif A < 500:
        a = 0.40 - 0.00382 * (4.6 - math.log(A)) ** 2; b = 0.0627 * A ** 0.254
    elif A < 1000:
        a = 0.40 - 0.0208 * math.log(math.log(A) - 4.6); b = 0.0627 * A ** 0.254
    else:
        a = 0.40 - 0.0208 * math.log(math.log(A) - 4.6); b = 0.1050 * A ** 0.180
    return 1 - b * D ** (-a)

# --- Curve 3: ARR 2019 long-duration eq. (2.4.2), D in minutes, AEP fraction ---
REG = {"Inland Arid": (0.297, 0.234, 0.449, 0.344, 0.00142, 0.216, 0.129, 0, 0),
       "Southern Semi-arid": (0.254, 0.247, 0.403, 0.351, 0.0013, 0.302, 0.058, 0, 0),
       "Semi-arid Inland Qld": (0.159, 0.283, 0.25, 0.308, 7.3e-7, 1, 0.039, 0, 0),
       "East Coast North": (0.327, 0.241, 0.448, 0.36, 0.00096, 0.48, -0.21, 0.012, -0.0013)}
def arf_arr_long(A, D=1440.0, AEP=0.01, region="Inland Arid"):
    a, b, c, d, e, f, g, h, i = REG[region]
    v = 1 - a * (A ** b - c * math.log10(D)) * D ** (-d) \
        + e * A ** f * D ** g * (0.3 + math.log10(AEP)) \
        + h * 10 ** (i * A * D / 1440.0) * (0.3 + math.log10(AEP))
    return min(1.0, v)

print("check ARR worked example (ECN, 245.07 km2, 24 h, 1%):", round(arf_arr_long(245.07, 1440, 0.01, "East Coast North"), 3), "(book: 0.929)")
print("check FSR 24 h: 100 km2 ->", round(arf_fsr(100), 3), " 500 km2 ->", round(arf_fsr(500), 3), "(NZ paper: 0.94, 0.91)")

curves = {"Gonu table fit (project)": arf_gonu,
          "FSR/FEH 24 h": lambda A: arf_fsr(A, 24.0),
          "ARR2019 Inland Arid 24 h 1%": lambda A: arf_arr_long(A, 1440, 0.01, "Inland Arid"),
          "ARR2019 S.Semi-arid 24 h 1%": lambda A: arf_arr_long(A, 1440, 0.01, "Southern Semi-arid")}

print("\nARF values at 24 h")
areas = [10, 20, 30, 50, 100, 200, 300, 450, 600, 1000]
print("area km2      " + "".join(f"{a:>8}" for a in areas))
for name, fn in curves.items():
    print(f"{name:28s}" + "".join(f"{fn(a):8.3f}" for a in areas))

print("\nMis-assigned storm area: rainfall ratio ARF(600)/ARF(A) - 1 (one catchment-wide storm area of 600 km2 used at a point of area A)")
for name, fn in curves.items():
    print(f"{name:28s}" + "".join(f"{(fn(600)/fn(a)-1)*100:7.1f}%" for a in areas))

print("\nInterpolation error between log-spaced storm-area runs, 10-600 km2; test points: 2000 log-spaced areas")
test = np.logspace(math.log10(10), math.log10(600), 2000)
for name, fn in curves.items():
    truth = np.array([fn(a) for a in test])
    for n in (5, 6, 7, 8):
        nodes = np.logspace(math.log10(10), math.log10(600), n)
        vals = np.array([fn(a) for a in nodes])
        lin_logA = np.interp(np.log(test), np.log(nodes), vals)
        lin_A = np.interp(test, nodes, vals)
        # nearest-node (no interpolation): snap each point to the node nearest in log A
        idx = np.abs(np.log(test)[:, None] - np.log(nodes)[None, :]).argmin(axis=1)
        snap = vals[idx]
        step = max(abs(vals[k] - vals[k + 1]) / vals[k + 1] for k in range(n - 1)) * 100
        print(f"{name:28s} n={n}: max step between neighbours {step:4.1f}% | max err lin-in-logA {np.max(np.abs(lin_logA-truth)/truth)*100:5.2f}% | lin-in-A {np.max(np.abs(lin_A-truth)/truth)*100:5.2f}% | nearest-node {np.max(np.abs(snap-truth)/truth)*100:5.2f}%")

print("\nProject HMS table itself (linear in A between the Gonu nodes, as HMS 'Linear Interpolation') vs the smooth fit, 28-700 km2:")
xs = np.array([n[0] for n in gonu_nodes]); ys = np.array([n[1] for n in gonu_nodes])
t2 = np.logspace(math.log10(28.3), math.log10(700), 2000)
err = np.abs(np.interp(t2, xs, ys) - arf_gonu(t2)) / arf_gonu(t2)
print(f"max |table - fit| / fit = {err.max()*100:.2f}% at A = {t2[err.argmax()]:.0f} km2")
