import json
import os
import tempfile
import time
import unittest

from heating_machine.config import (
    Config,
    ConfigError,
    ConfigManager,
)


class ConfigSchemaTests(unittest.TestCase):
    def _write_config(self, data):
        handle, path = tempfile.mkstemp()
        with os.fdopen(handle, "w", encoding="utf-8") as tmp:
            json.dump(data, tmp)
        return path

    def _base_config(self):
        return {
            "presets": [
                {
                    "name": "gentle",
                    "target_temperature_c": 40,
                    "ramp_rate_c_per_minute": 2,
                    "high_risk": False,
                },
                {
                    "name": "overdrive",
                    "target_temperature_c": 90,
                    "ramp_rate_c_per_minute": 10,
                    "high_risk": True,
                    "requires_elevated_approval": True,
                },
            ],
            "duration_ceiling": {"max_minutes": 20, "cooldown_minutes": 5},
            "throttle_thresholds": {
                "max_cpu_load": 0.8,
                "max_temperature_c": 95,
                "max_power_draw_watts": 600,
            },
            "flags": {"disable_high_risk_modes": True, "require_elevated_approval": False},
        }

    def test_high_risk_presets_disabled_when_flagged(self):
        config_path = self._write_config(self._base_config())
        manager = ConfigManager(config_path)
        self.assertEqual([preset.name for preset in manager.config.presets], ["gentle"])
        self.assertEqual(manager.metrics.high_risk_modes_disabled, 1)
        snapshot = manager.debug_snapshot()
        self.assertEqual(snapshot["disabled_high_risk_presets"], ["overdrive"])

    def test_missing_elevated_approval_raises_error(self):
        broken = self._base_config()
        broken["flags"]["disable_high_risk_modes"] = False
        broken["flags"]["require_elevated_approval"] = True
        broken["presets"][1]["requires_elevated_approval"] = False
        config_path = self._write_config(broken)
        with self.assertRaises(ConfigError):
            ConfigManager(config_path)

    def test_reload_when_file_changes(self):
        config_data = self._base_config()
        config_path = self._write_config(config_data)
        manager = ConfigManager(config_path)
        original_attempts = manager.metrics.reload_attempts

        # Update file to enable high risk with approval and force elevated requirement
        config_data["flags"]["disable_high_risk_modes"] = False
        config_data["flags"]["require_elevated_approval"] = True
        config_data["presets"][1]["requires_elevated_approval"] = True
        with open(config_path, "w", encoding="utf-8") as config_file:
            json.dump(config_data, config_file)
        future_time = time.time() + 1
        os.utime(config_path, (future_time, future_time))
        time.sleep(0.01)  # ensure mtime difference is detectable

        reloaded = manager.reload_if_stale()
        self.assertTrue(reloaded)
        self.assertGreater(manager.metrics.reload_attempts, original_attempts)
        self.assertTrue(manager.is_mode_allowed("overdrive"))
        self.assertTrue(manager.approval_required("overdrive"))

    def test_config_from_dict_validates_sections(self):
        base = self._base_config()
        base.pop("duration_ceiling")
        with self.assertRaises(ConfigError):
            Config.from_dict(base)


if __name__ == "__main__":
    unittest.main()
