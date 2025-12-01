from dataclasses import dataclass


@dataclass
class MachineConfig:
    """Configuration contract for the heating machine safety envelope."""

    max_temperature: float
    max_runtime_seconds: float
    heartbeat_timeout_seconds: float
    sensor_threshold: float
    max_load: float = 1.0

    def validate(self) -> None:
        """Ensure the configuration is sane before running."""
        for field_name, value in (
            ("max_temperature", self.max_temperature),
            ("max_runtime_seconds", self.max_runtime_seconds),
            ("heartbeat_timeout_seconds", self.heartbeat_timeout_seconds),
            ("sensor_threshold", self.sensor_threshold),
            ("max_load", self.max_load),
        ):
            if value <= 0:
                raise ValueError(f"{field_name} must be greater than zero")

        if self.sensor_threshold > self.max_temperature:
            raise ValueError("sensor_threshold cannot exceed max_temperature")
