"""Provider-independent usage data."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Limit:
    used_percent: float
    resets_at: int | None = None

    @property
    def remaining(self) -> float:
        return max(0.0, min(100.0, 100.0 - self.used_percent))


@dataclass(frozen=True)
class Usage:
    five_hour: Limit | None = None
    weekly: Limit | None = None

    def rows(self) -> tuple[tuple[str, Limit | None], ...]:
        return (("5h", self.five_hour), ("Weekly", self.weekly))
