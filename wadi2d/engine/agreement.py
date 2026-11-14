"""How well a simulated series follows an observed one. Interface: :func:`agreement`, :data:`FORMULAS`.

The common time base is the observed instants that carry a value and lie inside the simulated record; the simulated
series is read at each of them, straight between its own samples, so no observation is invented and none is moved.
Over that base, with ``o`` the observed values, ``s`` the simulated ones and ``n`` their count:

* **Nash-Sutcliffe efficiency** ``NSE = 1 - sum (s - o)^2 / sum (o - mean o)^2``: 1 is a perfect match, 0 is no better
  than the observed mean, below 0 worse than it.
* **RMSE over the observed standard deviation** ``RSR = sqrt(sum (s - o)^2 / n) / sqrt(sum (o - mean o)^2 / n)``,
  which is ``sqrt(1 - NSE)``: 0 is a perfect match.
* **Per cent bias** ``PBIAS = 100 sum (s - o) / sum o``: **positive when the model is high**. Moriasi et al. (2007)
  write it ``sum (o - s)``, the other sign; this record says which it uses.
* **RMSE** ``sqrt(sum (s - o)^2 / n)``, in the quantity's unit.

Peaks and their times are read on each series' own samples inside the window, from the first to the last instant of
the common base, so a simulated peak between two observations is not cut off. Volumes, of a flow only, are the
trapezoid of each series on its own samples inside the window, the simulated series cut at the window's ends by the
same straight reading; an observed gap is bridged straight across.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

FORMULAS = {
    "time_base": "observed instants with a value inside the simulated record; simulated read straight between its samples",
    "nse": "1 - sum((s - o)^2) / sum((o - mean(o))^2)",
    "rsr": "sqrt(sum((s - o)^2) / n) / sqrt(sum((o - mean(o))^2) / n) = sqrt(1 - NSE)",
    "pbias_percent": "100 * sum(s - o) / sum(o); positive when the model is high (Moriasi 2007 uses the other sign)",
    "rmse": "sqrt(sum((s - o)^2) / n), in the quantity's unit",
    "peaks": "highest value of each series on its own samples between the first and last instant of the time base",
    "volumes_m3": "trapezoid of each series on its own samples in the same window, flow only; an observed gap bridged",
}
MIN_POINTS = 2


@dataclass(frozen=True)
class Agreement:
    """The numbers of one comparison; times in seconds from the start of the run."""

    points: int
    window_s: tuple[float, float]
    observed_peak: float
    observed_peak_t_s: float
    simulated_peak: float
    simulated_peak_t_s: float
    peak_ratio: float | None
    peak_shift_s: float
    nse: float | None
    rsr: float | None
    pbias_percent: float | None
    rmse: float
    observed_volume_m3: float | None = None
    simulated_volume_m3: float | None = None
    volume_ratio: float | None = None

    def as_dict(self) -> dict:
        return asdict(self)


def _trapezoid(t: np.ndarray, v: np.ndarray) -> float:
    return float(np.sum(0.5 * (v[1:] + v[:-1]) * np.diff(t))) if t.size > 1 else 0.0


def _cut(t: np.ndarray, v: np.ndarray, start: float, end: float) -> tuple[np.ndarray, np.ndarray]:
    """A series inside [start, end], read straight at the two ends."""
    inside = (t > start) & (t < end)
    times = np.concatenate(([start], t[inside], [end]))
    return times, np.interp(times, t, v)


def _ratio(top: float, bottom: float) -> float | None:
    return top / bottom if bottom != 0.0 else None


def agreement(
    t_obs: np.ndarray, observed: np.ndarray, t_sim: np.ndarray, simulated: np.ndarray, volumes: bool = True
) -> Agreement:
    """The statistics of the module's note; ``volumes`` false for a level or a depth."""
    t_obs, observed = np.asarray(t_obs, np.float64), np.asarray(observed, np.float64)
    t_sim, simulated = np.asarray(t_sim, np.float64), np.asarray(simulated, np.float64)
    if t_sim.size < MIN_POINTS:
        raise ValueError("the simulated series has fewer than two values")
    keep = np.isfinite(observed) & (t_obs >= t_sim[0]) & (t_obs <= t_sim[-1])
    t, o = t_obs[keep], observed[keep]
    if t.size < MIN_POINTS:
        raise ValueError(
            f"only {t.size} observed values lie inside the simulated record ({t_sim[0]:g} to {t_sim[-1]:g} s from the "
            "start of the run): check the observed record's clock and the run's start"
        )
    s = np.interp(t, t_sim, simulated)
    error = s - o
    spread = float(np.sum((o - o.mean()) ** 2))
    squares = float(np.sum(error**2))
    nse = 1.0 - squares / spread if spread > 0.0 else None
    rsr = float(np.sqrt(squares / spread)) if spread > 0.0 else None
    total = float(np.sum(o))
    pbias = 100.0 * float(np.sum(error)) / total if total != 0.0 else None
    start, end = float(t[0]), float(t[-1])
    ts, vs = _cut(t_sim, simulated, start, end)
    at_obs, at_sim = int(np.argmax(o)), int(np.argmax(vs))
    found = Agreement(
        points=int(t.size), window_s=(start, end), observed_peak=float(o[at_obs]), observed_peak_t_s=float(t[at_obs]),
        simulated_peak=float(vs[at_sim]), simulated_peak_t_s=float(ts[at_sim]),
        peak_ratio=_ratio(float(vs[at_sim]), float(o[at_obs])), peak_shift_s=float(ts[at_sim] - t[at_obs]),
        nse=nse, rsr=rsr, pbias_percent=pbias, rmse=float(np.sqrt(squares / t.size)),
    )  # fmt: skip
    if not volumes:
        return found
    v_obs, v_sim = _trapezoid(t, o), _trapezoid(ts, vs)
    return Agreement(
        **{
            **found.as_dict(),
            "observed_volume_m3": v_obs,
            "simulated_volume_m3": v_sim,
            "volume_ratio": _ratio(v_sim, v_obs),
        }
    )
