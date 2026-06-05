"""Debug version of FanCoolingEffectiveness tests."""
from config.loader import load_config
from simulation.physics import compute_tau

class TestFanCoolingEffectiveness:
    """Tests que les ventilateurs refroidissent effectivement."""

    def test_zero_rpm_no_active_cooling(self):
        """Avec RPM=0, refroidissement uniquement passif (tau = tau_max)."""
        cfg = load_config("nominal")

        # Access role profile directly
        master_profile = cfg["cluster"]["role_profiles"]["master"]
        machine_thermal = master_profile["thermal"]
        fan_max_rpm = master_profile["fans"]["max_rpm"]

        tau_with_fans_off = compute_tau(
            tau_max=machine_thermal["tau_max_s"],
            fan_rpm_mean=0,
            k_cool=machine_thermal["k_cool_rpm_factor"],
            fan_max_rpm=fan_max_rpm,
        )
        expected = machine_thermal["tau_max_s"]
        assert abs(tau_with_fans_off - expected) < 0.01, \
            f"tau(0 RPM) = {tau_with_fans_off}s != tau_max={expected}s"
