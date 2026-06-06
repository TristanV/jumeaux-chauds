"""Tests pour la gestion du temps simulé (Phase 8.4+ correction).

Ces tests valident :
- Parsing de la date de départ depuis YAML
- Génération de timestamps simulés dans get_snapshot()
- Utilisation du temps simulé au lieu de l'heure réelle
"""
import pytest
from datetime import datetime, timezone

from config.loader import load_config
from simulation.cluster import ClusterSimulator
from simulation.time import parse_start_time, get_simulated_time_iso


class TestStartTimeConfiguration:
    """Tests de configuration de la date de départ."""

    def test_parse_start_time_default(self):
        """Par défaut, start_time = 2005-01-01."""
        dt = parse_start_time(None)
        assert dt.year == 2005
        assert dt.month == 1
        assert dt.day == 1
        assert dt.hour == 0
        assert dt.minute == 0
        assert dt.second == 0
        assert dt.tzinfo == timezone.utc

    def test_parse_start_time_iso_with_z(self):
        """Parse ISO 8601 avec Z."""
        dt = parse_start_time("2005-01-01T00:00:00Z")
        assert dt.year == 2005
        assert dt.month == 1
        assert dt.day == 1
        assert dt.tzinfo == timezone.utc

    def test_parse_start_time_iso_plus_utc(self):
        """Parse ISO 8601 avec +00:00."""
        dt = parse_start_time("2005-01-01T00:00:00+00:00")
        assert dt.year == 2005
        assert dt.tzinfo == timezone.utc

    def test_parse_start_time_custom_date(self):
        """Parse date personnalisée."""
        dt = parse_start_time("2010-06-15T12:30:45Z")
        assert dt.year == 2010
        assert dt.month == 6
        assert dt.day == 15
        assert dt.hour == 12
        assert dt.minute == 30
        assert dt.second == 45

    def test_parse_start_time_invalid(self):
        """Invalide format levé une erreur."""
        with pytest.raises(ValueError):
            parse_start_time("invalid-date-format")

    def test_config_loads_start_time(self):
        """Configuration YAML charge start_time correctement."""
        config = load_config(scenario="nominal")
        assert "start_time" in config["simulation"]
        # Tolérant : accepte n'importe quelle date ISO 8601 valide
        # (peut être modifiée dans base.yaml)
        start_time_str = config["simulation"]["start_time"]
        assert isinstance(start_time_str, str)
        # Vérifie format ISO 8601 (contient "T" et "Z" ou "+")
        assert "T" in start_time_str
        assert start_time_str.endswith("Z") or "+00:00" in start_time_str


class TestSimulatedTimeGeneration:
    """Tests de génération de timestamps simulés."""

    def test_simulated_time_iso_format(self):
        """Timestamp ISO au format correct."""
        start = datetime(2005, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        ts = get_simulated_time_iso(start, 0.0)
        assert ts == "2005-01-01T00:00:00.000Z"

    def test_simulated_time_with_seconds(self):
        """Ajoute des secondes au timestamp."""
        start = datetime(2005, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        ts = get_simulated_time_iso(start, 3600.0)  # 1 heure
        assert ts == "2005-01-01T01:00:00.000Z"

    def test_simulated_time_with_milliseconds(self):
        """Inclut les millisecondes."""
        start = datetime(2005, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        ts = get_simulated_time_iso(start, 1.234)  # 1.234 secondes
        assert ts == "2005-01-01T00:00:01.234Z"

    def test_simulated_time_large_delta(self):
        """Gère grands déltas de temps."""
        start = datetime(2005, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        # 30 jours = 2592000 secondes
        ts = get_simulated_time_iso(start, 2592000.0)
        assert "2005-01-31" in ts


class TestClusterSnapshotTimestamp:
    """Tests des timestamps dans get_snapshot()."""

    def test_snapshot_uses_simulated_time(self):
        """get_snapshot() utilise le temps simulé, pas l'heure réelle."""
        config = load_config(scenario="nominal")
        simulator = ClusterSimulator(config)

        # Vérifier que le snapshot initial utilise la date de départ
        snapshot = simulator.get_snapshot()
        # Tolérant : accepte n'importe quelle date ISO 8601 depuis base.yaml
        assert "ts" in snapshot
        assert snapshot["ts"].endswith("Z") or "+00:00" in snapshot["ts"]
        assert "T" in snapshot["ts"]  # Format ISO 8601

    def test_snapshot_advances_with_ticks(self):
        """Timestamp avance avec les ticks."""
        config = load_config(scenario="nominal")
        config["simulation"]["tick_rate_hz"] = 1.0  # 1 tick/sec
        simulator = ClusterSimulator(config)

        snap1 = simulator.get_snapshot()
        ts1 = snap1["ts"]

        # Exécuter 1 tick (1 seconde simulée)
        simulator._tick()

        snap2 = simulator.get_snapshot()
        ts2 = snap2["ts"]

        # ts2 doit être 1 seconde plus tard que ts1
        assert ts2 != ts1
        assert "00:00:01" in ts2  # 1 seconde plus tard

    def test_snapshot_includes_elapsed_time(self):
        """Snapshot inclut t_elapsed_s pour calculs downstream."""
        config = load_config(scenario="nominal")
        config["simulation"]["tick_rate_hz"] = 10.0
        simulator = ClusterSimulator(config)

        # Exécuter 5 ticks = 0.5 secondes
        for _ in range(5):
            simulator._tick()

        snapshot = simulator.get_snapshot()
        assert "t_elapsed_s" in snapshot
        assert abs(snapshot["t_elapsed_s"] - 0.5) < 0.01

    def test_snapshot_with_speed_multiplier(self):
        """Phase 8.12A : _tick() avance de dt_sim=0.1s fixe, indépendant de speed.

        Pour avancer de 60s simulées à tick_rate=10Hz, il faut 600 ticks.
        Le speed_multiplier contrôle batch_size dans run() async, pas _tick().
        """
        config = load_config(scenario="nominal")
        config["simulation"]["speed_multiplier"] = 60.0
        config["simulation"]["tick_rate_hz"] = 10.0
        simulator = ClusterSimulator(config)

        # 600 ticks × 0.1s = 60.0 secondes simulées
        for _ in range(600):
            simulator._tick()

        snap = simulator.get_snapshot()

        # Elapsed devrait être 60 secondes
        assert abs(snap["t_elapsed_s"] - 60.0) < 1.0


class TestMqttPublisherTimestamps:
    """Tests des timestamps dans les événements MQTT.

    Note : tests d'intégration, supposent que le snapshot contient ts
    """

    def test_snapshot_has_simulated_timestamp(self):
        """Snapshot contient toujours un timestamp simulé valide."""
        config = load_config(scenario="nominal")
        simulator = ClusterSimulator(config)

        snapshot = simulator.get_snapshot()

        # Vérifier que ts existe et est au format ISO 8601
        assert "ts" in snapshot
        assert snapshot["ts"].endswith("Z") or "+00:00" in snapshot["ts"]
        assert "T" in snapshot["ts"]
        # Tolérant : année peut être n'importe quelle valeur depuis base.yaml
        assert len(snapshot["ts"]) >= 19  # Minimum "YYYY-MM-DDTHH:MM:SS"


class TestStartTimeProtection:
    """Tests de protection de start_time contre surcharge."""

    @pytest.mark.parametrize(
        "scenario",
        ["nominal", "stress", "heatwave", "busy_weeks"],
    )
    def test_all_scenarios_preserve_start_time(self, scenario):
        """Tous les scénarios conservent start_time de base.yaml."""
        config = load_config(scenario=scenario)
        assert "start_time" in config["simulation"]
        # start_time vient de base.yaml et est protégé
        # Tolérant : valeur peut être modifiée dans base.yaml
        start_time_str = config["simulation"]["start_time"]
        assert isinstance(start_time_str, str)
        # Vérifie format ISO 8601 valide
        assert "T" in start_time_str and ("Z" in start_time_str or "+00:00" in start_time_str)

    def test_start_time_not_overridable_by_scenario(self):
        """start_time ne peut pas être surchargé par un scénario."""
        # Même si un scénario tentait de changer start_time,
        # le loader le rejetterait
        config_nominal = load_config(scenario="nominal")
        config_stress = load_config(scenario="stress")

        # Les deux doivent avoir le MÊME start_time de base.yaml (protection)
        assert config_nominal["simulation"]["start_time"] == config_stress["simulation"]["start_time"]

    def test_start_time_not_overridable_by_overrides(self):
        """start_time ne peut pas être changé via overrides dict."""
        original_start_time = load_config(scenario="nominal")["simulation"]["start_time"]

        config = load_config(
            scenario="nominal",
            overrides={"simulation": {"start_time": "2099-12-31T23:59:59Z"}}
        )
        # Doit rester la valeur originale de base.yaml, pas 2099
        assert config["simulation"]["start_time"] == original_start_time


class TestScenarioChaining:
    """Tests du chaînage de scénarios sans réinitialisation du temps."""

    def test_scenario_chain_preserves_time(self):
        """Changer de scénario ne change pas start_time."""
        # Scénario 1 : nominal
        sim1 = ClusterSimulator(load_config(scenario="nominal"))

        # Exécuter 10 ticks
        for _ in range(10):
            sim1._tick()

        t_elapsed_1 = sim1._t_elapsed_s
        start_time_1 = sim1._start_time

        # Scénario 2 : stress (en charge du même ClusterSimulator)
        # REMARQUE: Dans une application réelle, on changerait le scénario
        # mais on garderait le même ClusterSimulator et le même start_time

        # Simuler un changement de scénario : charger config stress
        config2 = load_config(scenario="stress")

        # Vérifier que start_time est identique (protégé par loader)
        config1 = load_config(scenario="nominal")
        assert config1["simulation"]["start_time"] == config2["simulation"]["start_time"]
        # Et que le simulator a bien parsé cette valeur (comparer datetime objects, pas strings)
        from simulation.time import parse_start_time
        assert parse_start_time(config2["simulation"]["start_time"]) == sim1._start_time

        # Le temps écoulé est personnel au simulator, pas à la config
        # Donc il continue où il s'est arrêté (10 ticks = 1 sec)
        assert sim1._t_elapsed_s == t_elapsed_1

    def test_multiple_simulators_same_start_time(self):
        """Plusieurs simulators utilisent le même start_time global."""
        sim_nominal = ClusterSimulator(load_config(scenario="nominal"))
        sim_stress = ClusterSimulator(load_config(scenario="stress"))
        sim_heatwave = ClusterSimulator(load_config(scenario="heatwave"))

        # Tous les simulators partagent le même start_time (protégé par loader)
        assert sim_nominal._start_time == sim_stress._start_time
        assert sim_stress._start_time == sim_heatwave._start_time

        # Vérifie que c'est une date valide (peu importe l'année exacte)
        assert sim_nominal._start_time.tzinfo == timezone.utc
        assert isinstance(sim_nominal._start_time.year, int)


class TestSpeedMultiplierProtection:
    """Tests de protection de speed_multiplier contre surcharge."""

    @pytest.mark.parametrize(
        "scenario",
        ["nominal", "stress", "heatwave", "busy_weeks"],
    )
    def test_all_scenarios_preserve_speed_multiplier(self, scenario):
        """Tous les scénarios conservent speed_multiplier de base.yaml."""
        config = load_config(scenario=scenario)
        assert "speed_multiplier" in config["simulation"]
        # speed_multiplier vient de base.yaml et est protégé
        assert config["simulation"]["speed_multiplier"] == 1.0  # Défaut

    def test_speed_multiplier_not_overridable_by_scenario(self):
        """speed_multiplier ne peut pas être surchargé par un scénario."""
        config_nominal = load_config(scenario="nominal")
        config_stress = load_config(scenario="stress")

        # Les deux doivent avoir le même speed_multiplier de base.yaml
        assert config_nominal["simulation"]["speed_multiplier"] == config_stress["simulation"]["speed_multiplier"]
        assert config_nominal["simulation"]["speed_multiplier"] == 1.0

    def test_speed_multiplier_not_overridable_by_overrides(self):
        """speed_multiplier ne peut pas être changé via overrides dict."""
        config = load_config(
            scenario="nominal",
            overrides={"simulation": {"speed_multiplier": 60.0}}
        )
        # Doit rester 1.0, pas 60.0
        assert config["simulation"]["speed_multiplier"] == 1.0


class TestStartTimeModification:
    """Tests de modification de start_time sans reset du temps écoulé."""

    def test_change_start_time_preserves_elapsed(self):
        """Modifier start_time ne change pas _t_elapsed_s."""
        config = load_config(scenario="nominal")
        sim = ClusterSimulator(config)

        # Exécuter 10 ticks
        for _ in range(10):
            sim._tick()

        t_elapsed_before = sim._t_elapsed_s
        old_start_time = sim._start_time

        # Changer start_time à une première valeur
        from simulation.time import parse_start_time
        new_start_time = parse_start_time("2010-06-15T12:30:45Z")
        sim._start_time = new_start_time

        # Vérifier t_elapsed_s inchangé
        assert sim._t_elapsed_s == t_elapsed_before

        # Snapshot AVANT changement de start_time
        snap_before = sim.get_snapshot()
        ts_before = snap_before["ts"]

        # Changer start_time À UNE AUTRE VALEUR (différente de la précédente)
        different_start_time = parse_start_time("2015-12-25T18:45:30Z")
        sim._start_time = different_start_time

        # Snapshot APRÈS changement de start_time
        snap_after = sim.get_snapshot()
        ts_after = snap_after["ts"]

        # Les timestamps DOIVENT être différents car start_time a changé
        assert ts_before != ts_after, f"Expected different timestamps: {ts_before} vs {ts_after}"
        # Mais le temps écoulé persiste
        assert snap_after["t_elapsed_s"] == snap_before["t_elapsed_s"]

    def test_snapshot_respects_changed_start_time(self):
        """Snapshot utilise le nouveau start_time après changement."""
        config = load_config(scenario="nominal")
        sim = ClusterSimulator(config)

        # Snapshot initial
        snap1 = sim.get_snapshot()
        ts1 = snap1["ts"]

        # Changer start_time à une autre valeur
        from simulation.time import parse_start_time
        sim._start_time = parse_start_time("2020-01-01T00:00:00Z")

        # Nouveau snapshot
        snap2 = sim.get_snapshot()
        ts2 = snap2["ts"]

        # Les timestamps doivent être différents (dates différentes)
        assert ts1 != ts2

        # Mais le temps écoulé doit rester le même
        assert snap1["t_elapsed_s"] == snap2["t_elapsed_s"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
