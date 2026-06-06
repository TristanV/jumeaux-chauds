"""Tests de continuité temporelle lors des changements de vitesse.

Vérifie que :
1. Les timestamps simulés sont strictement croissants avant/après changement de vitesse
2. Aucune discontinuité (saut ou retour en arrière) dans les timestamps
3. La densité de points (gap entre deux timestamps consécutifs) reste constante
4. Le changement de vitesse n'affecte pas _t_elapsed_s (pas de reset)
"""
from __future__ import annotations

import pytest
from config.loader import load_config
from simulation.cluster import ClusterSimulator
from simulation.time import get_simulated_time_iso


class TestTimestampContinuity:
    """Vérifie la continuité stricte des timestamps simulés."""

    def test_timestamps_strictly_increasing_1x(self):
        """À 1x, les timestamps simulés sont strictement croissants."""
        config = load_config("nominal")
        config["simulation"]["speed_multiplier"] = 1.0
        config["simulation"]["tick_rate_hz"] = 10.0
        sim = ClusterSimulator(config)

        timestamps = []
        for _ in range(20):
            sim._tick()
            ts = get_simulated_time_iso(sim._start_time, sim._t_elapsed_s)
            timestamps.append(ts)

        for i in range(1, len(timestamps)):
            assert timestamps[i] > timestamps[i - 1], (
                f"Timestamp non croissant à i={i}: {timestamps[i-1]} >= {timestamps[i]}"
            )

    def test_no_timestamp_reset_after_speed_change(self):
        """Changer la vitesse NE réinitialise PAS _t_elapsed_s."""
        config = load_config("nominal")
        config["simulation"]["speed_multiplier"] = 1.0
        config["simulation"]["tick_rate_hz"] = 10.0
        sim = ClusterSimulator(config)

        # Avancer de 10 ticks à 1x
        for _ in range(10):
            sim._tick()
        t_before = sim._t_elapsed_s
        assert t_before > 0, "t_elapsed_s doit être > 0 après des ticks"

        # Changer la vitesse
        sim.set_speed_multiplier(60.0)

        # _t_elapsed_s doit être inchangé
        assert sim._t_elapsed_s == t_before, (
            f"set_speed_multiplier a réinitialisé _t_elapsed_s : "
            f"{t_before} → {sim._t_elapsed_s}"
        )

    def test_timestamps_continuous_across_speed_change(self):
        """Les timestamps restent continus avant et après changement de vitesse."""
        config = load_config("nominal")
        config["simulation"]["speed_multiplier"] = 1.0
        config["simulation"]["tick_rate_hz"] = 10.0
        sim = ClusterSimulator(config)
        dt_sim = 1.0 / 10.0  # 0.1s par tick

        # Phase 1 : 10 ticks à 1x
        ts_phase1 = []
        for _ in range(10):
            sim._tick()
            ts_phase1.append(sim._t_elapsed_s)

        last_t_phase1 = sim._t_elapsed_s

        # Changer à 60x
        sim.set_speed_multiplier(60.0)

        # Phase 2 : 10 ticks à 60x — dt_sim toujours 0.1s, pas de saut
        ts_phase2 = []
        for _ in range(10):
            sim._tick()
            ts_phase2.append(sim._t_elapsed_s)

        first_t_phase2 = ts_phase2[0]

        # Pas de saut : le premier tick phase 2 = last_t_phase1 + dt_sim
        expected_first = last_t_phase1 + dt_sim
        assert abs(first_t_phase2 - expected_first) < 1e-9, (
            f"Saut de timestamp au changement de vitesse : "
            f"attendu {expected_first:.3f}s, obtenu {first_t_phase2:.3f}s"
        )

        # Tous les timestamps phase 2 sont croissants
        for i in range(1, len(ts_phase2)):
            assert ts_phase2[i] > ts_phase2[i - 1], (
                f"Timestamp non croissant en phase 2 à i={i}"
            )

        # Continuité entre phase 1 et phase 2
        assert ts_phase2[0] > ts_phase1[-1], (
            f"Timestamp phase 2 ({ts_phase2[0]}) <= dernier phase 1 ({ts_phase1[-1]})"
        )

    def test_constant_dt_sim_across_speeds(self):
        """dt_sim = 1/tick_rate_hz est constant quelle que soit la vitesse."""
        config = load_config("nominal")
        config["simulation"]["tick_rate_hz"] = 10.0
        dt_sim_expected = 1.0 / 10.0  # 0.1s

        for speed in [1.0, 60.0, 3600.0]:
            config["simulation"]["speed_multiplier"] = speed
            sim = ClusterSimulator(config)

            t_before = sim._t_elapsed_s
            sim._tick()
            t_after = sim._t_elapsed_s

            dt_actual = t_after - t_before
            assert abs(dt_actual - dt_sim_expected) < 1e-9, (
                f"À speed={speed}x : dt_sim={dt_actual:.6f}s "
                f"(attendu {dt_sim_expected:.6f}s)"
            )

    def test_timestamp_gap_in_timescaledb_format(self):
        """Simule ce que TimescaleDB voit : timestamps ISO en ordre croissant.

        Ce test reproduit le comportement observé dans Grafana :
        vérifie qu'il n'y a pas deux séries parallèles (timestamps qui se
        recoupent) lors d'un changement de vitesse.
        """
        config = load_config("nominal")
        config["simulation"]["tick_rate_hz"] = 10.0
        config["simulation"]["speed_multiplier"] = 1.0
        sim = ClusterSimulator(config)

        all_timestamps = []

        # Simuler 20 ticks à 1x
        for _ in range(20):
            sim._tick()
            all_timestamps.append(
                get_simulated_time_iso(sim._start_time, sim._t_elapsed_s)
            )

        # Changer à 60x
        sim.set_speed_multiplier(60.0)

        # Simuler 20 ticks à 60x
        for _ in range(20):
            sim._tick()
            all_timestamps.append(
                get_simulated_time_iso(sim._start_time, sim._t_elapsed_s)
            )

        # TOUS les timestamps doivent être strictement croissants
        # (pas deux séries parallèles qui se recoupent)
        for i in range(1, len(all_timestamps)):
            assert all_timestamps[i] > all_timestamps[i - 1], (
                f"Timestamps non monotones à i={i} (changement de vitesse à i=20) :\n"
                f"  t[{i-1}] = {all_timestamps[i-1]}\n"
                f"  t[{i}]   = {all_timestamps[i]}\n"
                "→ Cela provoquerait deux séries parallèles dans Grafana."
            )

    def test_no_duplicate_timestamps(self):
        """Aucun timestamp dupliqué (ce qui créerait deux points au même instant)."""
        config = load_config("nominal")
        config["simulation"]["tick_rate_hz"] = 10.0
        config["simulation"]["speed_multiplier"] = 1.0
        sim = ClusterSimulator(config)

        timestamps = []
        for _ in range(10):
            sim._tick()
            timestamps.append(
                get_simulated_time_iso(sim._start_time, sim._t_elapsed_s)
            )

        sim.set_speed_multiplier(3600.0)

        for _ in range(10):
            sim._tick()
            timestamps.append(
                get_simulated_time_iso(sim._start_time, sim._t_elapsed_s)
            )

        assert len(timestamps) == len(set(timestamps)), (
            "Timestamps dupliqués détectés — deux points au même instant simulé."
        )


class TestTimescaleDBInsertOrder:
    """Vérifie l'ordre d'insertion dans TimescaleDB lors de changements de vitesse."""

    def test_elapsed_time_monotone_with_speed_changes(self):
        """_t_elapsed_s est strictement croissant même après plusieurs changements."""
        config = load_config("nominal")
        config["simulation"]["tick_rate_hz"] = 10.0
        config["simulation"]["speed_multiplier"] = 1.0
        sim = ClusterSimulator(config)

        elapsed_times = []

        # 5 ticks à 1x
        for _ in range(5):
            sim._tick()
            elapsed_times.append(sim._t_elapsed_s)

        # Passer à 60x
        sim.set_speed_multiplier(60.0)
        for _ in range(5):
            sim._tick()
            elapsed_times.append(sim._t_elapsed_s)

        # Passer à 3600x
        sim.set_speed_multiplier(3600.0)
        for _ in range(5):
            sim._tick()
            elapsed_times.append(sim._t_elapsed_s)

        # Revenir à 1x
        sim.set_speed_multiplier(1.0)
        for _ in range(5):
            sim._tick()
            elapsed_times.append(sim._t_elapsed_s)

        # Strictement croissant tout au long
        for i in range(1, len(elapsed_times)):
            assert elapsed_times[i] > elapsed_times[i - 1], (
                f"_t_elapsed_s non croissant à i={i} "
                f"(changements de vitesse aux i=5,10,15) : "
                f"{elapsed_times[i-1]:.4f} >= {elapsed_times[i]:.4f}"
            )

    def test_batch_size_reflects_speed_change(self):
        """Vérifie que batch_size dans run() refléterait bien le changement de vitesse.

        Teste indirectement en vérifiant que set_speed_multiplier modifie
        _speed_multiplier qui est lu à chaque itération de run().
        """
        config = load_config("nominal")
        config["simulation"]["tick_rate_hz"] = 10.0
        config["simulation"]["cpu_throttle_target_hz"] = 100.0
        config["simulation"]["cpu_throttle_enabled"] = True
        config["simulation"]["speed_multiplier"] = 1.0
        sim = ClusterSimulator(config)

        dt_real_loop = 1.0 / 100.0  # throttle 100Hz

        # À 1x : batch_size = 1 * 0.01 * 10 = 0.1 → arrondi à 1
        batch_1x = max(1, round(sim._speed_multiplier * dt_real_loop * sim._tick_rate_hz))
        assert batch_1x == 1, f"batch_size attendu 1, obtenu {batch_1x}"

        # Changer à 60x
        sim.set_speed_multiplier(60.0)
        batch_60x = max(1, round(sim._speed_multiplier * dt_real_loop * sim._tick_rate_hz))
        assert batch_60x == 6, f"batch_size attendu 6, obtenu {batch_60x}"

        # Changer à 3600x
        sim.set_speed_multiplier(3600.0)
        batch_3600x = max(1, round(sim._speed_multiplier * dt_real_loop * sim._tick_rate_hz))
        assert batch_3600x == 360, f"batch_size attendu 360, obtenu {batch_3600x}"
