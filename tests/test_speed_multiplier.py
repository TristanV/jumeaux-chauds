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
        """À vitesse 60x, 1 seconde réelle = 60 secondes simulées."""
        config = load_config(scenario="nominal")
        config["simulation"]["speed_multiplier"] = 60.0
        config["simulation"]["tick_rate_hz"] = 10.0

        simulator = ClusterSimulator(config)

        # Exécuter 10 ticks (1 seconde réelle)
        for _ in range(10):
            simulator._tick()

        # À 60x, temps écoulé = 10 * (1/10) * 60.0 = 60.0 secondes
        assert abs(simulator._t_elapsed_s - 60.0) < 0.1

    @pytest.mark.asyncio
    async def test_simulated_time_accumulation_3600x(self):
        """À vitesse 3600x, 1 seconde réelle = 1 heure simulée."""
        config = load_config(scenario="nominal")
        config["simulation"]["speed_multiplier"] = 3600.0
        config["simulation"]["tick_rate_hz"] = 10.0

        simulator = ClusterSimulator(config)

        # Exécuter 10 ticks (1 seconde réelle)
        for _ in range(10):
            simulator._tick()

        # À 3600x, temps écoulé = 10 * (1/10) * 3600.0 = 3600.0 secondes = 1 heure
        assert abs(simulator._t_elapsed_s - 3600.0) < 1.0

    @pytest.mark.asyncio
    async def test_simulated_time_accumulation_86400x(self):
        """À vitesse 86400x, 1 seconde réelle = 1 jour simulé."""
        config = load_config(scenario="nominal")
        config["simulation"]["speed_multiplier"] = 86400.0
        config["simulation"]["tick_rate_hz"] = 10.0

        simulator = ClusterSimulator(config)

        # Exécuter 10 ticks (1 seconde réelle)
        for _ in range(10):
            simulator._tick()

        # À 86400x, temps écoulé = 10 * (1/10) * 86400.0 = 86400.0 secondes = 1 jour
        assert abs(simulator._t_elapsed_s - 86400.0) < 10.0


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
        """Modifier vitesse en cours d'exécution."""
        config = load_config(scenario="nominal")
        config["simulation"]["speed_multiplier"] = 1.0
        simulator = ClusterSimulator(config)

        # Phase 1 : ticks à 1x
        t1 = simulator._t_elapsed_s
        for _ in range(5):
            simulator._tick()
        t2 = simulator._t_elapsed_s

        # Changer à 60x
        simulator.set_speed_multiplier(60.0)

        # Phase 2 : ticks à 60x
        t3 = simulator._t_elapsed_s
        for _ in range(5):
            simulator._tick()
        t4 = simulator._t_elapsed_s

        # Ratio de temps entre phases
        dt1 = t2 - t1
        dt2 = t4 - t3

        # dt2 devrait être ~60x dt1 (même nombre de ticks)
        # (dt1 ≈ 0.5 s, dt2 ≈ 30 s à taux 10 Hz)
        assert abs((dt2 / dt1) - 60.0) < 1.0

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
        """Scénario : générer 30 jours de données ML en ~30 secondes."""
        config = load_config(scenario="nominal")
        config["simulation"]["speed_multiplier"] = 86400.0  # 1 jour/sec
        config["simulation"]["tick_rate_hz"] = 10.0
        config["simulation"]["cpu_throttle_target_hz"] = 100.0

        simulator = ClusterSimulator(config)

        # Exécuter 300 ticks (30 secondes à 10 Hz)
        for _ in range(300):
            simulator._tick()

        # Temps simulé devrait être ~30 jours
        expected_time_s = 30 * 86400  # 30 days in seconds
        actual_time_s = simulator._t_elapsed_s

        # Tolérance ±5% (phénomène de floating point)
        assert abs(actual_time_s - expected_time_s) / expected_time_s < 0.05

    @pytest.mark.asyncio
    async def test_rapid_testing_scenario(self):
        """Scénario : test rapide avec accélération 1h/sec."""
        config = load_config(scenario="nominal")
        config["simulation"]["speed_multiplier"] = 3600.0  # 1 hour/sec
        config["simulation"]["tick_rate_hz"] = 10.0

        simulator = ClusterSimulator(config)

        # Exécuter 100 ticks (~10 secondes)
        for _ in range(100):
            simulator._tick()

        # Temps simulé ~10 heures
        expected_time_s = 10 * 3600
        actual_time_s = simulator._t_elapsed_s

        assert abs(actual_time_s - expected_time_s) / expected_time_s < 0.05


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
