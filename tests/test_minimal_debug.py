from config.loader import load_config
from simulation.physics import compute_tau

def test_minimal():
    """Minimal test to debug config loading."""
    cfg = load_config("nominal")
    print(f"\nConfig type: {type(cfg)}")
    print(f"Config keys: {list(cfg.keys())}")
    print(f"'cluster' in cfg: {'cluster' in cfg}")
    
    # This should work
    master_profile = cfg["cluster"]["role_profiles"]["master"]
    machine_thermal = master_profile["thermal"]
    fan_max_rpm = master_profile["fans"]["max_rpm"]
    
    tau = compute_tau(
        tau_max=machine_thermal["tau_max_s"],
        fan_rpm_mean=0,
        k_cool=machine_thermal["k_cool_rpm_factor"],
        fan_max_rpm=fan_max_rpm,
    )
    assert abs(tau - machine_thermal["tau_max_s"]) < 0.01
    print("TEST PASSED")
