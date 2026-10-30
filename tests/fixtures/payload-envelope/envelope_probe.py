"""Record runtime evaluations and whole payload values."""

calls = 0
kept: list[object] = []


def sample(value: int) -> int:
    """Count one evaluation; fold the count into the result."""
    global calls
    calls += 1
    return value * 10 + calls


def keep(payload: object) -> bool:
    """Record a whole payload value."""
    kept.append(payload)
    return True


def keep_marker(payload: object) -> bool:
    """Record a whole marker payload value."""
    kept.append(payload)
    return True
