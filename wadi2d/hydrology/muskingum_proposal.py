"""K, X and subreaches proposed for a Muskingum reach from what is known of it. Interface: :class:`Proposal`,
:func:`at_reference_flow`, :func:`at_index_celerity`, :func:`at_velocity`, :func:`at_travel_time`,
:func:`section_state`.

A proposal is a starting value with its derivation in words. It is shown to the user and taken only when the user
writes it into the job: nothing here is read by a run.

The relations, each read in the source named (EM 1110-2-1417, Flood-Runoff Analysis, USACE 1994, chapter 9, paragraph
9-3c; HEC-HMS Technical Reference Manual, "Muskingum Model"):

- K is the travel time of the flood wave, K = L / c (EM eq. 9-21; HMS eq. 8), with the wave speed c from Seddon's
  law on the section's rating, c = (1 / B) dQ / dy (EM eq. 9-20; HMS eq. 7), or as a ratio of the mean velocity
  (EM 9-3c(2)(b): 1.67 wide rectangular, 1.44 wide parabolic, 1.33 triangular, 1.5 suggested for natural channels).
- X by Cunge (1969), X = 1/2 (1 - Q0 / (B S0 c dx)) at a reference flow Q0, dx the length of a subreach (EM eq. 9-22).
  The EM says of the reference flow that one "midway between the base flow and the peak flow" suits best in general,
  and that a peak reference speeds the wave up; it is the user's number here, never this module's choice.
- Subreaches: about K over the step, so that a subreach's travel time is about the step (EM 9-3c(3); HMS manual),
  inside 2KX <= step <= 2K(1-X) (EM eq. 9-23 gives the lower bound; both bounds keep the coefficients from going
  negative, and HMS 4.12 warns outside them).
- With no section, X is :data:`DEFAULT_X` and said to be a default: the EM gives 0.0 to 0.5 and no typical value,
  only that mild slopes with overbank flow lie nearer 0.0 and steep, well defined channels nearer 0.5.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

from wadi2d.hydrology.constants import MINUTES_PER_HOUR, SECONDS_PER_HOUR, SECONDS_PER_MINUTE
from wadi2d.hydrology.muskingum import X_MAX, X_MIN, Muskingum
from wadi2d.hydrology.routing import HMS_DEPTH_TOLERANCE
from wadi2d.hydrology.routing_kernel import MANNING_EXPONENT, WIDE_CHANNEL_POWER, normal_depth

DEFAULT_X = 0.2
"""X where no section says more. Chow, Maidment and Mays (1988, section 8.4) give 0 to 0.3 for natural streams with a
mean near 0.2 [quoted from memory, not re-read for W89]; EM 1110-2-1417 gives only the limits 0.0 and 0.5."""
NATURAL_WAVE_RATIO = 1.5
"""Wave speed over mean velocity, the EM's suggestion for natural channels (paragraph 9-3c(2)(b))."""
K_DIGITS, X_DIGITS = 4, 3
"""A proposal is rounded to what a table shows, so the number shown is the number used."""
CUT_GUARD = 1.0e-9
"""A ceiling that is a whole number of the last digit shown, less round-off, is that number."""
DEPTH_ITERATIONS = 200
CELERITY_BISECTIONS = 200
FLOW_BRACKET = (1.0e-6, 1.0e7)
"""The flows, m3/s, between which the flow of an index celerity is looked for."""
BASIS_FLOW = "reference flow"
BASIS_INDEX = "index celerity"
BASIS_VELOCITY = "velocity"
BASIS_TRAVEL_TIME = "travel time"


@dataclass(frozen=True)
class SectionState:
    """Uniform flow in a trapezoid at one discharge."""

    flow_m3s: float
    depth_m: float
    area_m2: float
    top_width_m: float
    velocity_ms: float
    celerity_ms: float


def section_state(flow_m3s: float, bottom_width_m: float, side_slope: float, slope: float, manning_n: float) -> SectionState:
    """Manning's normal depth at a flow and Seddon's wave speed there, c = (1 / B) dQ / dy; the same expressions the
    Muskingum-Cunge kernel reads its Courant number from."""
    conveyance = math.sqrt(slope) / manning_n
    depth = normal_depth(flow_m3s, bottom_width_m, side_slope, conveyance, 0.0, DEPTH_ITERATIONS, HMS_DEPTH_TOLERANCE)
    wet_side = 2.0 * math.sqrt(1.0 + side_slope * side_slope)
    area = (bottom_width_m + side_slope * depth) * depth
    top = bottom_width_m + 2.0 * side_slope * depth
    perimeter = bottom_width_m + wet_side * depth
    velocity = flow_m3s / area
    celerity = velocity * (WIDE_CHANNEL_POWER - MANNING_EXPONENT * area / perimeter * wet_side / top)
    return SectionState(flow_m3s, depth, area, top, velocity, celerity)


def flow_at_celerity(
    celerity_ms: float, bottom_width_m: float, side_slope: float, slope: float, manning_n: float
) -> float | None:
    """The flow whose wave speed on the section is ``celerity_ms``, by bisection in log flow; None when the section
    never reaches it between :data:`FLOW_BRACKET`."""
    low, high = FLOW_BRACKET

    def over(flow: float) -> bool:
        return section_state(flow, bottom_width_m, side_slope, slope, manning_n).celerity_ms > celerity_ms

    if over(low) or not over(high):
        return None
    for _ in range(CELERITY_BISECTIONS):
        middle = math.sqrt(low * high)
        low, high = (low, middle) if over(middle) else (middle, high)
    return math.sqrt(low * high)


@dataclass(frozen=True)
class Proposal:
    """K, X and subreaches for one reach, how they were derived, and whether a subreach is stable at the step."""

    k_hours: float
    x: float
    subreaches: int
    basis: str
    words: str
    stable: bool
    celerity_ms: float | None = None
    reference_flow_m3s: float | None = None
    x_cunge: float | None = None
    """Cunge's X before it was brought into 0 to 0.5; None when X is a default."""

    def as_dict(self) -> dict:
        return asdict(self)


def _count(k_hours: float, dt_minutes: float) -> int:
    """About K over the step, at least one."""
    return max(1, math.floor(k_hours * MINUTES_PER_HOUR / dt_minutes + 0.5))


def _stable_ceiling(k_hours: float, count: int, dt_minutes: float) -> float:
    """The highest X a subreach is stable at: 2KX <= step and step <= 2K(1-X) both ask X no higher than a bound,
    K the subreach's. Below zero when the wave crosses a subreach in under half a step: then no X is stable."""
    ratio = dt_minutes * count / (2.0 * k_hours * MINUTES_PER_HOUR)
    return min(X_MAX, ratio, 1.0 - ratio)


def _settle(k_hours: float, x: float, count: int, dt_minutes: float) -> tuple[float, bool]:
    """X brought into what HMS takes and, where the step allows it, down to the highest stable value; and whether
    it was lowered for the step. X is cut, not rounded, to the digits shown, so the number shown is stable too."""
    ceiling = _stable_ceiling(k_hours, count, dt_minutes)
    shown = round(min(max(x, X_MIN), X_MAX), X_DIGITS)
    if not X_MIN <= ceiling < shown:
        return shown, False
    unit = 10.0**-X_DIGITS
    cut = round(math.floor(ceiling / unit + CUT_GUARD) * unit, X_DIGITS)
    return cut, x - cut > unit  # a cut inside the last digit shown is rounding, not a lowering


def _stability_words(k_hours: float, x: float, subreaches: int, dt_minutes: float) -> tuple[bool, str]:
    method = Muskingum(k_hours, x, subreaches)
    low, high = method.stable_range_minutes()
    if method.is_stable(dt_minutes):
        return True, f"a subreach is stable at steps of {low:.3g} to {high:.3g} min (2KX to 2K(1-X))"
    return False, (
        f"NOT stable at the {dt_minutes:g} min step: the wave crosses the reach in {k_hours * MINUTES_PER_HOUR:.3g} "
        "min, under half a step, so no X routes it without a negative coefficient: a shorter step, or no routing on "
        "this reach"
    )


def _lowered_words(x: float) -> str:
    return (
        f"; no count of subreaches is stable with it at this step, so X is lowered to {x:g}, the highest that is: "
        "a little more attenuation than Cunge's"
    )


def at_reference_flow(
    length_m: float,
    slope: float,
    manning_n: float,
    bottom_width_m: float,
    side_slope: float,
    reference_flow_m3s: float,
    dt_minutes: float,
    basis: str = BASIS_FLOW,
    lead: str = "",
) -> Proposal:
    """Cunge's K and X on a trapezoid at a reference flow.

    The subreaches are K over the step, or the nearest count at which Cunge's X is not negative (HMS takes none below
    0, and X falls as a subreach shortens) and a subreach is stable. Where no count does both: fewer subreaches until
    X is not negative, one subreach with X = 0 where even that asks a negative X (the most attenuation Muskingum has),
    and X lowered to the highest stable value where the step asks it. The words say which.
    """
    if reference_flow_m3s <= 0.0:
        raise ValueError(f"reference flow {reference_flow_m3s!r}: above zero, m3/s")
    state = section_state(reference_flow_m3s, bottom_width_m, side_slope, slope, manning_n)
    k_hours = round(length_m / state.celerity_ms / SECONDS_PER_HOUR, K_DIGITS)
    if k_hours <= 0.0:
        raise ValueError(f"a reach of {length_m:g} m at {state.celerity_ms:.2f} m/s has no travel time to route")
    reynolds_length = reference_flow_m3s / (state.top_width_m * slope * state.celerity_ms)

    def cunge(count: int) -> float:
        return 0.5 * (1.0 - reynolds_length * count / length_m)

    def fits(count: int) -> bool:
        return cunge(count) >= X_MIN and Muskingum(k_hours, cunge(count), count).is_stable(dt_minutes)

    wanted = _count(k_hours, dt_minutes)
    nearest = sorted(range(1, 2 * wanted + 2), key=lambda count: (abs(count - wanted), count))
    count = next((count for count in nearest if fits(count)), None)
    if count is None:
        count = wanted
        while count > 1 and cunge(count) < X_MIN:
            count -= 1
    raw = cunge(count)
    x, lowered = _settle(k_hours, raw, count, dt_minutes)
    stable, range_words = _stability_words(k_hours, x, count, dt_minutes)
    words = (
        f"{lead}Cunge (1969) at {reference_flow_m3s:,.4g} m3/s: normal depth {state.depth_m:.2f} m, top width "
        f"{state.top_width_m:.1f} m, mean velocity {state.velocity_ms:.2f} m/s, wave speed {state.celerity_ms:.2f} m/s "
        f"(Seddon, c = dQ/dy / B). K = L / c = {k_hours:g} h. {count} subreach{'es' if count > 1 else ''} of "
        f"{length_m / count:,.0f} m"
    )
    if count != wanted:
        words += f" (K over the {dt_minutes:g} min step is {wanted}; {count} keeps X at or above 0 and the step stable)"
    words += f". X = 1/2 (1 - Q / (B S c dx)) = {raw:.3f}"
    if raw < X_MIN:
        words += f", below what HMS takes: set to {X_MIN:g}, and the reach attenuates more than Muskingum can show"
    elif lowered:
        words += _lowered_words(x)
    words += f"; {range_words}."
    return Proposal(k_hours, x, count, basis, words, stable, state.celerity_ms, reference_flow_m3s, raw)


def at_index_celerity(
    length_m: float,
    slope: float,
    manning_n: float,
    bottom_width_m: float,
    side_slope: float,
    index_celerity: float,
    dt_minutes: float,
) -> Proposal | None:
    """Cunge's K and X at the flow whose wave speed is the reach's index celerity, the speed its Muskingum-Cunge
    cells were laid out for; None when the section never carries a wave that fast or that slow."""
    flow = flow_at_celerity(index_celerity, bottom_width_m, side_slope, slope, manning_n)
    if flow is None:
        return None
    lead = (
        f"No reference flow given, so the flow whose wave speed is the reach's index celerity, {index_celerity:g} m/s, "
        "stands in; if that flow is far from the flood to be routed, give a reference flow (EM 1110-2-1417: midway "
        "between base flow and peak suits best in general). "
    )
    return at_reference_flow(
        length_m, slope, manning_n, bottom_width_m, side_slope, flow, dt_minutes, BASIS_INDEX, lead
    )


def _default_x_words(x: float) -> str:
    return (
        f"X = {x:g}, a default and not a property of this reach: 0.0 (most attenuation) to 0.5 (none) is the range "
        "(EM 1110-2-1417, 9-3c), mild slopes with overbank flow nearer 0.0, steep well defined channels nearer 0.5"
    )


def at_travel_time(
    travel_minutes: float, dt_minutes: float, source: str, x: float = DEFAULT_X, basis: str = BASIS_TRAVEL_TIME,
    celerity_ms: float | None = None,
) -> Proposal:
    """K as a travel time someone gives or estimates, in ``source``'s words; X a stated default."""
    if travel_minutes <= 0.0:
        raise ValueError(f"travel time {travel_minutes!r}: above zero, minutes")
    k_hours = round(travel_minutes / MINUTES_PER_HOUR, K_DIGITS)
    if k_hours <= 0.0:
        raise ValueError(f"travel time {travel_minutes!r} min rounds to no K: too short a reach to route")
    count = _count(k_hours, dt_minutes)
    given = x
    x, lowered = _settle(k_hours, x, count, dt_minutes)
    stable, range_words = _stability_words(k_hours, x, count, dt_minutes)
    words = (
        f"{source} K = {k_hours:g} h. {count} subreach{'es' if count > 1 else ''} (K over the {dt_minutes:g} min "
        f"step). {_default_x_words(given)}"
    )
    if lowered:
        words += f"; that is not stable at this step, so X is lowered to {x:g}, the highest that is"
    return Proposal(k_hours, x, count, basis, f"{words}; {range_words}.", stable, celerity_ms)


def at_velocity(
    length_m: float, velocity_ms: float, dt_minutes: float, ratio: float = NATURAL_WAVE_RATIO, x: float = DEFAULT_X
) -> Proposal:
    """K from the reach's length over a wave speed of ``ratio`` times a mean velocity the user gives."""
    if velocity_ms <= 0.0:
        raise ValueError(f"velocity {velocity_ms!r}: above zero, m/s")
    celerity = ratio * velocity_ms
    source = (
        f"Wave speed {ratio:g} x the mean velocity given, {velocity_ms:g} m/s = {celerity:g} m/s (EM 1110-2-1417, "
        f"9-3c(2)(b): {NATURAL_WAVE_RATIO:g} for natural channels); L / c over {length_m:,.0f} m:"
    )
    return at_travel_time(
        length_m / celerity / SECONDS_PER_MINUTE, dt_minutes, source, x, BASIS_VELOCITY, celerity
    )
