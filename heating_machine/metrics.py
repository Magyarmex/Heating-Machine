from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class MetricEvent:
    message: str
    details: Dict[str, float | int | str]
    level: str = "info"


@dataclass
class MetricsCollector:
    events: List[MetricEvent] = field(default_factory=list)

    def record_event(self, message: str, **details: float | int | str) -> None:
        self.events.append(MetricEvent(message=message, details=details, level="info"))

    def record_error(self, message: str, **details: float | int | str) -> None:
        self.events.append(MetricEvent(message=message, details=details, level="error"))

    def record_health(self, status: str, **details: float | int | str) -> None:
        self.events.append(MetricEvent(message=status, details=details, level="health"))

    def latest_by_level(self, level: str) -> List[MetricEvent]:
        return [event for event in self.events if event.level == level]
