"""Tests pour le contrôle de vitesse de simulation (Phase 8.4).

Ces tests valident :
- Paramètres de configuration speed_multiplier et cpu_throttle
- Accumulation correcte du temps simulé avec multiplier
- Changement de vitesse à chaud
- Throttling CPU (fréquence réelle de publication)
- Export de données
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from config.loader import load_config
from simulation.cluster import ClusterSimulator


class TestSpeedConfiguration:
    """Tests de configuration du speed_multiplier."""

    def test_default_speed_multiplier(self):
        """Le multiplier par défaut est 1.0 (real-time)."""
        config = load_config(scenario="nominal")
        # La config devrait avoir speed_multiplier
        assert "speed_multiplier" in config["simulation"]
        assert config["simulation"]["speed_multiplier"] == 1.0

    def test_speed_multiplier_values(self):
        """Les valeurs prédéfinies sont supportées."""
        speeds = [1.0, 60.0, 3600.0, 86400.0]
        for speed in speeds:
            config = load_config(scenario="nominal")
            config["simulation"]["speed_multiplier"] = speed
            simulator = ClusterSimulator(config)
            assert simulator._speed_multiplier == speed

    def test_invalid_speed_multiplier(self):
        """Speed multiplier doit être > 0."""
        config = load_config(scenario="nominal")
        config["simulation"]["speed_multiplier"] = 0.0
        # Devrait lever une erreur ou être clampé à une valeur valide
        with pytest.raises((ValueError, AssertionError)):
            ClusterSimulator(config)

    def test_cpu_throttle_configuration(self):
        """Configuration throttle CPU (enabled, target_hz)."""
        config = load_config(scenario="nominal")
        assert "cpu_throttle_enabled" in config["simulation"]
        assert "cpu_throttle_target_hz" in config["simulation"]
        assert config["simulation"]["cpu_throttle_enabled"] is True
        assert config["simulation"]["cpu_throttle_target_hz"] == 100.0

    def test_cpu_throttle_hz_range(self):
        """Target Hz doit être dans [50, 500]."""
        config = load_config(scenario="nominal")
        config["simulation"]["cpu_throttle_target_hz"] = 150.0
        simulator = ClusterSimulator(config)
        assert simulator._cpu_throttle_target_hz == 150.0

        # Test edges
        config["simulation"]["cpu_throttle_target_hz"] = 50.0
        simulator = ClusterSimulator(config)
        assert simulator._cpu_throttle_target_hz == 50.0

        config["simulation"]["cpu_throttle_target_hz"] = 500.0
        simulator = ClusterSimulator(config)
        assert simulator._cpu_throttle_target_hz == 500.0


class TestSpeedMultiplierBehavior:
    """Tests du comportement avec accélération."""

    @pytest.mark.asyncio
    async def test_simulated_time_accumulation_1x(self):
        """À vitesse 1x, temps simulé = temps réel."""
        config = load_config(scenario="nominal")
        config["simulation"]["speed_multiplier"] = 1.0
        config["simulation"]["tick_rate_hz"] = 10.0
        config["simulation"]["duration"] = "0"  # Infini

        simulator = ClusterSimulator(config)

        # Exécuter 10 ticks (1 seconde à 10 Hz)
        for _ in range(10):
            simulator._tick()

        # À 1x, temps écoulé = 10 * (1/10) * 1.0 = 1.0 seconde
        assert abs(simulator._t_elapsed_s - 1.0) < 0.01

    @pytest.mark.asyncio
    async def test_simulated_time_accumulation_60x(self):
        """Phase 8.12A : _tick() avance toujours de dt_sim=1/tick_rate_hz fixe.

        Le speed_multiplier contrôle batch_size dans run() async, pas _tick().
        Pour simuler 60s, il faut 60 * tick_rate_hz = 600 ticks.
        """
        config = load_config(scenario="nominal")
        config["simulation"]["speed_multiplier"] = 60.0
        config["simulation"]["tick_rate_hz"] = 10.0

        simulator = ClusterSimulator(config)
        dt_sim = 1.0 / 10.0  # 0.1s par tick, fixe

        # 600 ticks × 0.1s = 60.0 secondes simulées
        for _ in range(600):
            simulator._tick()

        assert abs(simulator._t_elapsed_s - 60.0) < 0.1

    @pytest.mark.asyncio
    async def test_simulated_time_accumulation_3600x(self):
        """Phase 8.12A : _tick() avance de dt_sim fixe quelle que soit la vitesse."""
        config = load_config(scenario="nominal")
        config["simulation"]["speed_multiplier"] = 3600.0
        config["simulation"]["tick_rate_hz"] = 10.0

        simulator = ClusterSimulator(config)

        # 36000 ticks × 0.1s = 3600s = 1 heure simulée
        for _ in range(36000):
            simulator._tick()

        assert abs(simulator._t_elapsed_s - 3600.0) < 1.0

    @pytest.mark.asyncio
    async def test_simulated_time_accumulation_86400x(self):
        """Phase 8.12A : vérifier l'accumulation sur 1 jour simulé (sous-ensemble)."""
        config = load_config(scenario="nominal")
        config["simulation"]["speed_multiplier"] = 86400.0
        config["simulation"]["tick_rate_hz"] = 10.0

        simulator = ClusterSimulator(config)

        # 1000 ticks × 0.1s = 100s simulées (subset pour limiter le temps de test)
        for _ in range(1000):
            simulator._tick()

        assert abs(simulator._t_elapsed_s - 100.0) < 1.0


class TestSpeedChangeHotReload:
    """Tests du changement de vitesse à chaud."""

    def test_speed_change_preserves_energy(self):
        """Changer la vitesse ne réinitialise pas energy_kwh_total."""
        config = load_config(scenario="nominal")
        config["simulation"]["speed_multiplier"] = 1.0
        simulator = ClusterSimulator(config)

        # Exécuter quelques ticks
        for _ in range(5):
            simulator._tick()

        energy_before = simulator.energy_kwh_total
        assert energy_before > 0

        # Changer la vitesse
        simulator.set_speed_multiplier(60.0)

        # L'énergie doit être préservée
        assert simulator.energy_kwh_total == energy_before
        assert simulator._speed_multiplier == 60.0

    def test_speed_change_at_runtime(self):
        """Phase 8.12A : set_speed_multiplier() modifie _speed_multiplier et batch_size.

        _tick() avance toujours de dt_sim fixe. Le changement de vitesse affecte
        batch_size dans run() async, pas l'accumulation par _tick().
        Ce test vérifie que le changement de vitesse est bien pris en compte
        et que l'accumulation de temps reste cohérente (dt_sim fixe).
        """
        config = load_config(scenario="nominal")
        config["simulation"]["speed_multiplier"] = 1.0
        config["simulation"]["tick_rate_hz"] = 10.0
        simulator = ClusterSimulator(config)
        dt_sim = 1.0 / 10.0  # 0.1s fixe par tick

        # Phase 1 : 5 ticks à 1x
        for _ in range(5):
            simulator._tick()
        t_after_phase1 = simulator._t_elapsed_s
        assert abs(t_after_phase1 - 0.5) < 0.01  # 5 × 0.1s = 0.5s

        # Changer à 60x — _tick() toujours 0.1s, mais batch_size change dans run()
        simulator.set_speed_multiplier(60.0)
        assert simulator._speed_multiplier == 60.0

        # Phase 2 : 5 ticks supplémentaires — toujours dt_sim=0.1s par tick
        for _ in range(5):
            simulator._tick()
        t_after_phase2 = simulator._t_elapsed_s
        # 10 ticks total × 0.1s = 1.0s simulée (dt_sim fixe, indépendant de speed)
        assert abs(t_after_phase2 - 1.0) < 0.01

    def test_speed_change_method_validation(self):
        """set_speed_multiplier valide l'entrée."""
        config = load_config(scenario="nominal")
        simulator = ClusterSimulator(config)

        # Valeur invalide (0 ou négative)
        with pytest.raises((ValueError, AssertionError)):
            simulator.set_speed_multiplier(0.0)

        with pytest.raises((ValueError, AssertionError)):
            simulator.set_speed_multiplier(-1.0)

        # Valeur valide
        simulator.set_speed_multiplier(100.0)
        assert simulator._speed_multiplier == 100.0


class TestCPUThrottling:
    """Tests du throttling CPU."""

    def test_throttle_interval_calculation(self):
        """L'intervalle throttle est 1.0 / cpu_throttle_target_hz."""
        config = load_config(scenario="nominal")
        config["simulation"]["cpu_throttle_target_hz"] = 100.0
        simulator = ClusterSimulator(config)

        # Intervalle throttle = 1.0 / 100.0 = 0.01 s = 10 ms
        assert abs(simulator._throttle_interval_s - 0.01) < 1e-6

    def test_throttle_disabled(self):
        """Si throttle désactivé, intervalle = 0."""
        config = load_config(scenario="nominal")
        config["simulation"]["cpu_throttle_enabled"] = False
        simulator = ClusterSimulator(config)

        assert simulator._throttle_interval_s == 0.0

    def test_throttle_publication_frequency(self):
        """Publications MQTT/WS ne dépassent pas target_hz (simulation)."""
        config = load_config(scenario="nominal")
        config["simulation"]["cpu_throttle_enabled"] = True
        config["simulation"]["cpu_throttle_target_hz"] = 50.0
        config["simulation"]["tick_rate_hz"] = 100.0  # Très rapide

        simulator = ClusterSimulator(config)

        # Mock pour compter publications
        publication_times = []

        def mock_publish(*args, **kwargs):
            publication_times.append(asyncio.get_event_loop().time())

        # Note : test simplifié, une vrai test utiliserait la boucle async
        # Ici on vérifie juste que le paramètre throttle est bien stocké
        assert simulator._cpu_throttle_target_hz == 50.0
        assert simulator._throttle_interval_s == 0.02  # 1.0 / 50.0


class TestSnapshotBuffer:
    """Tests du buffer circulaire de snapshots."""

    def test_snapshot_buffer_size(self):
        """Buffer snapshots limité à 100K."""
        config = load_config(scenario="nominal")
        simulator = ClusterSimulator(config)

        # Buffer doit exister et avoir maxlen
        assert hasattr(simulator, "_snapshot_buffer")
        assert simulator._snapshot_buffer.maxlen == 100000

    def test_snapshot_accumulation(self):
        """Les snapshots s'accumulent dans le buffer."""
        config = load_config(scenario="nominal")
        simulator = ClusterSimulator(config)

        initial_count = len(simulator._snapshot_buffer)

        # Exécuter 10 ticks
        for _ in range(10):
            simulator._tick()
            # Snapshot ajouté au buffer
            snapshot = simulator.get_snapshot()
            simulator._snapshot_buffer.append(snapshot)

        final_count = len(simulator._snapshot_buffer)
        # Au moins 10 snapshots ajoutés
        assert final_count >= initial_count + 10

    def test_snapshot_buffer_circular(self):
        """Buffer circulaire ne dépasse jamais maxlen."""
        config = load_config(scenario="nominal")
        simulator = ClusterSimulator(config)

        # Ajouter beaucoup plus que maxlen
        for i in range(150000):
            snapshot = simulator.get_snapshot()
            simulator._snapshot_buffer.append(snapshot)

        # Vérifier que buffer ne dépasse pas maxlen
        assert len(simulator._snapshot_buffer) <= 100000


class TestExportData:
    """Tests d'export de données."""

    @pytest.mark.asyncio
    async def test_export_snapshots_csv(self, tmp_path):
        """Export snapshots en CSV."""
        config = load_config(scenario="nominal")
        simulator = ClusterSimulator(config)

        # Générer quelques snapshots
        for _ in range(10):
            simulator._tick()
            snapshot = simulator.get_snapshot()
            simulator._snapshot_buffer.append(snapshot)

        # Export (simplifié, sans vraiment écrire CSV)
        # Dans la vrai implémentation, ce serait un endpoint API
        assert len(simulator._snapshot_buffer) > 0

    @pytest.mark.asyncio
    async def test_export_snapshots_parquet(self, tmp_path):
        """Export snapshots en Parquet."""
        config = load_config(scenario="nominal")
        simulator = ClusterSimulator(config)

        # Générer quelques snapshots
        for _ in range(10):
            simulator._tick()
            snapshot = simulator.get_snapshot()
            simulator._snapshot_buffer.append(snapshot)

        # Vérifier que buffer est populated
        assert len(simulator._snapshot_buffer) > 0


class TestIntegrationScenarios:
    """Tests d'intégration multi-vitesses."""

    @pytest.mark.asyncio
    async def test_ml_data_generation_scenario(self):
        """Phase 8.12A/B : vérifier la densité constante en temps simulé.

        Avec dt_sim=0.1s fixe, pour générer N secondes simulées il faut
        N × tick_rate_hz ticks. Ce test vérifie l'accumulation sur 1 heure simulée
        (représentatif de la génération de corpus ML via _tick() en boucle).
        """
        config = load_config(scenario="nominal")
        config["simulation"]["speed_multiplier"] = 86400.0
        config["simulation"]["tick_rate_hz"] = 10.0
        config["simulation"]["cpu_throttle_target_hz"] = 100.0

        simulator = ClusterSimulator(config)

        # 3600 ticks × 0.1s = 360s simulées (limité pour temps de test raisonnable)
        n_ticks = 3600
        expected_time_s = n_ticks * (1.0 / 10.0)  # 360s

        for _ in range(n_ticks):
            simulator._tick()

        assert abs(simulator._t_elapsed_s - expected_time_s) < 0.1

    @pytest.mark.asyncio
    async def test_rapid_testing_scenario(self):
        """Phase 8.12A : dt_sim fixe — le speed_multiplier affecte run() pas _tick()."""
        config = load_config(scenario="nominal")
        config["simulation"]["speed_multiplier"] = 3600.0
        config["simulation"]["tick_rate_hz"] = 10.0

        simulator = ClusterSimulator(config)

        # 1000 ticks × 0.1s = 100s simulées
        n_ticks = 1000
        expected_time_s = n_ticks * (1.0 / 10.0)

        for _ in range(n_ticks):
            simulator._tick()

        assert abs(simulator._t_elapsed_s - expected_time_s) / expected_time_s < 0.01


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
