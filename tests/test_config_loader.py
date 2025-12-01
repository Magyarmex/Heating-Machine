from heating_machine.config_loader import ConfigLoader


def test_loads_environment_profile_with_min_heat():
    loader = ConfigLoader()
    profile = loader.load("development")

    assert profile.name == "development"
    assert profile.min_heat == 10
    assert profile.increment > 0
