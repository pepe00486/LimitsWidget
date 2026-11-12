"""Provider-independent usage data."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Limit:
    """Store usage and the optional reset time for one quota window."""

    used_percent: float
    resets_at: int | None = None

    @property
    def remaining(self) -> float:
        """Return the remaining percentage within the range zero to 100."""
        return max(0.0, min(100.0, 100.0 - self.used_percent))


@dataclass(frozen=True)
class Usage:
    """Store the two quota windows shown by the widget."""

    five_hour: Limit | None = None
    weekly: Limit | None = None

    def rows(self) -> tuple[tuple[str, Limit | None], ...]:
        """Return the labels and limits in display order."""
        return (("5h", self.five_hour), ("Weekly", self.weekly))
