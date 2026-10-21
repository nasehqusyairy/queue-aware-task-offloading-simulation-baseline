"""Paper-aligned experiment configuration helpers.

Choices here are implementation decisions, not claims that the paper mandates
an integer rounding rule or PureEdgeSim architecture label.
"""
from __future__ import annotations

PAPER_TARGETS = {
    "ALL_DEVICES": "ALL",
    "EDGE_AND_EDGE_DC": "MIST_AND_EDGE",
    "EDGE_AND_CLOUD": "MIST_AND_CLOUD",
    "EDGE_DC_AND_CLOUD": "EDGE_AND_CLOUD",
    "EDGE_ONLY": "MIST_ONLY",
    "EDGE_DC_ONLY": "EDGE_ONLY",
}


def allocate_profile_counts(total: int, percentages: list[int]) -> list[int]:
    """Allocate integer profile counts by largest remainder, stable on ties."""
    if total < 0:
        raise ValueError("total must be non-negative")
    if not percentages or any(p < 0 for p in percentages):
        raise ValueError("percentages must be a non-empty sequence of non-negative values")
    if sum(percentages) != 100:
        raise ValueError("profile percentages must sum to 100")

    quotas = [total * p / 100 for p in percentages]
    counts = [int(q) for q in quotas]
    remaining = total - sum(counts)
    order = sorted(range(len(quotas)), key=lambda i: (-(quotas[i] - counts[i]), i))
    for i in order[:remaining]:
        counts[i] += 1
    return counts


def coverage_summary(points: list[tuple[float, float]], centers: list[tuple[float, float]], radius: float,
                     area_length: float, area_width: float) -> dict[str, int | float | None]:
    """Check sampled UE positions against circular EDC reach and the area bounds."""
    import math

    if not centers:
        raise ValueError("at least one EDC center is required")
    if radius < 0 or area_length <= 0 or area_width <= 0:
        raise ValueError("radius and area dimensions must be positive")
    distances = [min(math.hypot(x - cx, y - cy) for cx, cy in centers) for x, y in points]
    area_violations = sum(not (0 <= x <= area_length and 0 <= y <= area_width) for x, y in points)
    coverage_violations = sum(distance > radius for distance in distances)
    return {
        "points_checked": len(points),
        "coverage_violation_count": coverage_violations,
        "area_violation_count": area_violations,
        "max_nearest_distance": max(distances) if distances else None,
    }


def expected_task_count(device_count: int, app_percentages: list[int], rates_per_second: list[int], duration_seconds: int) -> int:
    """Expected count under the documented per-app-user, per-second rate mapping."""
    if len(app_percentages) != len(rates_per_second):
        raise ValueError("app percentages and rates must have equal lengths")
    if duration_seconds <= 0 or any(rate < 0 for rate in rates_per_second):
        raise ValueError("duration must be positive and rates non-negative")
    app_users = allocate_profile_counts(device_count, app_percentages)
    return sum(users * rate * duration_seconds for users, rate in zip(app_users, rates_per_second))


def target_architecture(target: str) -> str:
    """Map the six paper target groups to PureEdgeSim's built-in layer names."""
    try:
        return PAPER_TARGETS[target.upper()]
    except KeyError as exc:
        raise ValueError(f"unknown offloading target {target!r}; expected one of {', '.join(PAPER_TARGETS)}") from exc


def target_allowed_types(target: str) -> set[str]:
    """Return the actual PureEdgeSim node categories permitted by a paper target."""
    allowed = {
        "ALL_DEVICES": {"CLOUD", "EDGE_DATACENTER", "EDGE_DEVICE"},
        "EDGE_AND_EDGE_DC": {"EDGE_DATACENTER", "EDGE_DEVICE"},
        "EDGE_AND_CLOUD": {"CLOUD", "EDGE_DEVICE"},
        "EDGE_DC_AND_CLOUD": {"CLOUD", "EDGE_DATACENTER"},
        "EDGE_ONLY": {"EDGE_DEVICE"},
        "EDGE_DC_ONLY": {"EDGE_DATACENTER"},
    }
    try:
        return allowed[target.upper()]
    except KeyError as exc:
        raise ValueError(f"unknown offloading target {target!r}; expected one of {', '.join(PAPER_TARGETS)}") from exc


def initial_matrix() -> list[dict[str, object]]:
    """Return one smoke-validation run per requested initial combination."""
    return [
        {"method": method, "devices": devices, "destination_config": target}
        for method in ("trade-off", "round-robin")
        for devices in (10, 20, 30)
        for target in PAPER_TARGETS
    ]
