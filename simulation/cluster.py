"""Orchestrateur de cluster de machines.

Ce module fournit `ClusterSimulator`, responsable de :
- instancier les `MachineSimulator` à partir de la config mergée,
- orchestrer la boucle de simulation (ticks),
- calculer les métriques agrégées (énergie, coût, PUE effectif),
- exposer un snapshot consolidé pour MQTT / WebSocket / API.

Phase 3 : la méthode ``run()`` accepte un ``MqttPublisher`` optionnel et
un ``ConnectionManager`` WebSocket optionnel (branché en Phase 4).
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from config.loader import get_machine_config
from .machine import MachineSimulator, SensorConfig, ThermalConfig
from .physics import compute_cost
from .scenarios import FaultConfig, FaultScheduler, LoadProfileConfig, ScenarioEngine
from .time import parse_start_time, get_simulated_time_iso

if TYPE_CHECKING:
    from mqtt.publisher import MqttPublisher

logger = logging.getLogger(__name__)


@dataclass
class ClusterMetrics:
    """Métriques agrégées du cluster."""

    energy_kwh_total: float
    cost_eur_total: float
    pue_effective: float


class ClusterSimulator:
    """Orchestrateur de N machines simulées."""

    def __init__(self, config: dict[str, Any]) -> None:
        self._cfg = config
        self.cluster_id: str = config["cluster"]["id"]
        self._tick_rate_hz: float = float(config["simulation"]["tick_rate_hz"])
        self._events_per_sec: float = float(
            config["simulation"].get("events_per_sec", 1.0)
        )

        # PUE et coût
        self._pue: float = float(config["cluster"].get("pue", 1.4))
        self._price_eur_kwh: float = float(
            config["cluster"].get("electricity_price_eur_kwh", 0.2)
        )

        # Construction des machines
        self.machines: dict[str, MachineSimulator] = {}
        self._build_machines()

        # Scénario de charge (global pour le cluster)
        lp_cfg = LoadProfileConfig(
            type=config["simulation"]["load_profile"]["type"],
            params={
                k: v
                for k, v in config["simulation"]["load_profile"].items()
                if k != "type"
            },
        )
        self._scenario_engine = ScenarioEngine(profile_cfg=lp_cfg)

        # Scheduler de pannes
        fault_cfgs: list[FaultConfig] = []
        fault_section = config["simulation"].get("fault_injection", {})
        fault_enabled = fault_section.get("enabled", True)
        for raw in (fault_section.get("faults", []) if fault_enabled else []):
            fault_cfgs.append(
                FaultConfig(
                    type=raw["type"],
                    distribution=raw["distribution"],
                    shape=raw.get("shape"),
                    scale_s=raw.get("scale_s"),
                    probability_per_tick=raw.get("probability_per_tick"),
                    magnitude=raw.get("magnitude", 1.0),
                )
            )

        self._fault_scheduler = FaultScheduler(
            fault_configs=fault_cfgs,
            recovery_delay_s=float(fault_section.get("recovery_delay_s", 60.0)),
        )

        # Phase 8.4 — Contrôle de vitesse de simulation
        self._speed_multiplier: float = float(
            config["simulation"].get("speed_multiplier", 1.0)
        )
        if self._speed_multiplier <= 0:
            raise ValueError(
                f"speed_multiplier must be > 0, got {self._speed_multiplier}"
            )

        self._cpu_throttle_enabled: bool = config["simulation"].get(
            "cpu_throttle_enabled", True
        )
        self._cpu_throttle_target_hz: float = float(
            config["simulation"].get("cpu_throttle_target_hz", 100.0)
        )
        if not (50.0 <= self._cpu_throttle_target_hz <= 500.0):
            logger.warning(
                f"cpu_throttle_target_hz {self._cpu_throttle_target_hz} "
                "outside recommended range [50, 500]"
            )

        # Intervalle throttle (en secondes réelles)
        if self._cpu_throttle_enabled:
            self._throttle_interval_s: float = 1.0 / self._cpu_throttle_target_hz
        else:
            self._throttle_interval_s: float = 0.0

        # Buffer circulaire pour export données ML
        from collections import deque
        self._snapshot_buffer = deque(maxlen=100000)

        # Gestion du temps simulé
        start_time_str = config["simulation"].get("start_time")
        self._start_time = parse_start_time(start_time_str)
        logger.info(f"Simulation start time: {self._start_time.isoformat()}")

        # Temps et métriques agrégées
        self._running = False
        self._t_elapsed_s: float = 0.0
        self.energy_kwh_total: float = 0.0
        self.cost_eur_total: float = 0.0
        self.pue_effective: float = self._pue

        # Mémorisation des états précédents (détection de changements)
        self._prev_status: dict[str, str] = {}
        self._prev_fans: dict[str, list[dict]] = {}

    # ------------------------------------------------------------------
    # Construction des machines
    # ------------------------------------------------------------------
    def _build_machines(self) -> None:
        """Instancie les MachineSimulator à partir des role_profiles.

        Utilise get_machine_config() pour merger le profil de rôle avec
        les surcharges individuelles de chaque machine, conformément à la
        structure de base.yaml (cluster.role_profiles.{role}.thermal / .fans).

        L'état initial de chaque machine est déterminé par la clé
        ``initial_status`` (priorité : machine > role_profile, défaut : "off").
        """
        cluster_cfg = self._cfg["cluster"]
        tick_rate_hz = float(self._cfg["simulation"]["tick_rate_hz"])

        for m_entry in cluster_cfg["machines"]:
            machine_id = m_entry["id"]
            role = m_entry.get("role", "worker")

            # Merge role_profile + surcharges individuelles
            m_cfg = get_machine_config(self._cfg, machine_id)

            th = m_cfg["thermal"]
            fans = m_cfg["fans"]
            power = m_cfg["power"]

            # Phase 7.2 : Extraire noise.power_std_w et noise.fan_speed_std_rpm
            noise_cfg = m_cfg.get("noise", {})

            thermal_cfg = ThermalConfig(
                idle_w=float(power["idle_watts"]),
                max_w=float(power["max_watts"]),
                alpha=float(th.get("alpha_load_exponent", 1.5)),
                heat_ratio=float(power.get("heat_ratio", 0.9)),
                tau_max_s=float(th["tau_max_s"]),
                k_cool=float(th["k_cool_rpm_factor"]),
                c_th_j_per_c=float(th["thermal_capacity_j_per_c"]),
                ambient_temp_c=float(th["ambient_temp_c"]),
                t_shutdown_c=float(th["t_shutdown_c"]),
                t_restart_c=float(th["t_restart_c"]),
                recovery_delay_s=float(th.get("recovery_delay_s", 60.0)),
                fan_gain_rpm_per_c=float(fans["auto_policy"]["gain_rpm_per_c"]),
                fan_max_rpm=int(fans["max_rpm"]),
                fan_power_w=float(fans["power_per_fan_w"]),
                tick_rate_hz=tick_rate_hz,
                power_std_w=float(noise_cfg.get("power_std_w", 0.0)),  # Phase 7.2
                fan_speed_std_rpm=float(noise_cfg.get("fan_speed_std_rpm", 0.0)),  # Phase 7.2
            )

            sensor_configs: list[SensorConfig] = []
            for s_cfg in m_cfg.get("temperature_sensors", []):
                sensor_configs.append(
                    SensorConfig(
                        sensor_id=s_cfg["id"],
                        bias_c=float(s_cfg.get("bias_c", 0.0)),
                        noise_std_c=float(s_cfg.get("noise_std_c", 0.0)),
                        drift_rate_c_per_s=float(s_cfg.get("drift_rate_c_per_s", 0.0)),
                    )
                )

            fan_count = int(fans.get("count", 2))

            machine = MachineSimulator(
                machine_id=machine_id,
                role=role,
                thermal=thermal_cfg,
                sensor_configs=sensor_configs,
                fan_count=fan_count,
            )

            # ── État initial ──────────────────────────────────────────────────
            # Priorité : surcharge individuelle > role_profile > défaut "off"
            role_profile = cluster_cfg["role_profiles"].get(role, {})
            initial_status = (
                m_entry.get("initial_status")
                or role_profile.get("initial_status", "off")
            )
            if initial_status == "on":
                machine.power_on()
                logger.debug("Machine %s démarrée (initial_status=on)", machine_id)
            # ─────────────────────────────────────────────────────────────────

            self.machines[machine_id] = machine

    # ------------------------------------------------------------------
    # Boucle principale
    # ------------------------------------------------------------------
    async def run(
        self,
        publisher: "MqttPublisher | None" = None,
        ws_manager: Any = None,
    ) -> None:  # pragma: no cover - testé via intégration
        """Boucle de simulation principale.

        Parameters
        ----------
        publisher :
            Instance de :class:`mqtt.publisher.MqttPublisher` injecte dans
            la boucle pour la publication MQTT. Si ``None`` (flag --no-mqtt),
            la publication est silencieusement ignorée.
        ws_manager :
            ``ConnectionManager`` FastAPI (branché en Phase 4). Ignoré si
            ``None``.
        """
        self._running = True

        # ── Phase 8.12A — Architecture corrigée ─────────────────────────
        # INVARIANT : dt_sim = 1/tick_rate_hz = constant (indépendant de speed)
        # La vitesse multiplie le NOMBRE de ticks simulés par itération réelle.
        # Charge CPU par tick : identique à toutes les vitesses.
        dt_sim = 1.0 / self._tick_rate_hz  # pas temporel fixe (0.1s simulé)

        # Cadence réelle de la boucle (CPU throttle enfin branché)
        if self._cpu_throttle_enabled:
            dt_real_loop = 1.0 / self._cpu_throttle_target_hz
        else:
            dt_real_loop = dt_sim  # fallback : même cadence que tick_rate

        # Nombre de ticks simulés par itération réelle
        batch_size = max(1, round(self._speed_multiplier * dt_real_loop * self._tick_rate_hz))

        # Timers publications périodiques (en ticks simulés cumulés)
        ticks_per_summary = max(1, round(5.0 * self._tick_rate_hz))
        ticks_per_energy = max(1, round(60.0 * self._tick_rate_hz))
        tick_counter: int = 0  # ticks simulés cumulés

        logger.info(
            "run() — speed=%.1fx | dt_sim=%.3fs | throttle=%s@%.0fHz | batch=%d ticks/iter",
            self._speed_multiplier, dt_sim,
            "ON" if self._cpu_throttle_enabled else "OFF",
            self._cpu_throttle_target_hz, batch_size,
        )

        while self._running:
            await asyncio.sleep(dt_real_loop)

            # ── Batch de ticks simulés ──────────────────────────────────
            status_transitions: list[tuple[str, str, str]] = []

            for _ in range(batch_size):
                self._t_elapsed_s += dt_sim
                tick_counter += 1

                load_factor = self._scenario_engine.get_load_factor(self._t_elapsed_s)

                # Capturer statuts avant ce tick individuel
                pre_tick_statuses = {mid: m.status for mid, m in self.machines.items()}

                for machine in self.machines.values():
                    machine.tick(load_factor=load_factor, dt=dt_sim)

                # Détecter transitions immédiatement après chaque tick
                for machine in self.machines.values():
                    mid = machine.id
                    if pre_tick_statuses.get(mid) != machine.status:
                        status_transitions.append(
                            (mid, machine.status, machine.last_status_cause)
                        )

                self._fault_scheduler.tick(self.machines, dt=dt_sim)

            # Métriques agrégées (une fois par batch)
            self._update_metrics()

            # ── Publications MQTT (une fois par batch) ──────────────────
            if publisher is not None:
                ts_now = get_simulated_time_iso(self._start_time, self._t_elapsed_s)

                # Transitions de statut (QoS 1)
                for mid, new_status, cause in status_transitions:
                    self._prev_status[mid] = new_status
                    await publisher.publish_status(
                        self.cluster_id, mid, new_status,
                        cause=cause, ts=ts_now,
                    )

                # Télémétrie + summary + energy
                await self._publish_tick(
                    publisher,
                    tick_counter,
                    ticks_per_summary,
                    ticks_per_energy,
                )

            # ── Broadcast WebSocket (à chaque itération) ────────────────
            if ws_manager is not None:
                try:
                    await ws_manager.broadcast(self.get_snapshot())
                except Exception as exc:  # noqa: BLE001
                    logger.debug("WS broadcast échec : %s", exc)

    async def _publish_tick(
        self,
        publisher: "MqttPublisher",
        tick_counter: int,
        ticks_per_summary: int,
        ticks_per_energy: int,
    ) -> None:
        """Gère toutes les publications MQTT pour une itération de la boucle.

        Phase 8.12A : appelé à chaque itération réelle (cadencée par cpu_throttle).
        La télémétrie est publiée à chaque appel.
        """
        # --- Télémétrie par machine (à chaque itération) -----------------
        for machine in self.machines.values():
                snap = machine.snapshot()
                snap["cluster_id"] = self.cluster_id
                snap["machine_id"] = machine.id
                # ✅ IMPORTANT : Ajouter timestamp simulé (sinon publisher utilise datetime.now() = 2026!)
                snap["ts"] = get_simulated_time_iso(self._start_time, self._t_elapsed_s)
                # Bug #11 Fix : sensors est maintenant dict, pas list
                sensors_dict = snap.get("sensors", {})
                snap["temperatures"] = {
                    sensor_id: {"value_c": sensor_data["temp_c"]}
                    for sensor_id, sensor_data in sensors_dict.items()
                }
                snap["power_w"] = snap.get("power_w", 0.0)


                await publisher.publish_telemetry(snap)

                # Note : la détection des changements de statut est gérée dans la
                # boucle principale (avant _publish_tick) pour capturer last_status_cause
                # immédiatement après machine.tick(), évitant qu'il soit écrasé.
                mid = machine.id

                # Changement d'état des fans ?
                current_fans = snap.get("fans", [])
                if self._prev_fans.get(mid) != current_fans:
                    self._prev_fans[mid] = current_fans
                    await publisher.publish_fan_state(
                        self.cluster_id, mid, current_fans
                    )

                # Panne active ?
                for fault in snap.get("faults", []):
                    fault_key = f"{mid}:{fault.get('type')}:{fault.get('ts_start')}"
                    if not hasattr(self, "_published_faults"):
                        self._published_faults: set[str] = set()
                    if fault_key not in self._published_faults:
                        self._published_faults.add(fault_key)
                        ts_fault = get_simulated_time_iso(self._start_time, self._t_elapsed_s)
                        await publisher.publish_fault(
                            self.cluster_id, mid, fault, event="injected", ts=ts_fault
                        )

        # --- Summary cluster (toutes les 5 s) ----------------------
        if tick_counter % ticks_per_summary == 0:
            await publisher.publish_summary(self.get_snapshot())

        # --- Métriques énergétiques (toutes les 60 s) ---------------
        if tick_counter % ticks_per_energy == 0:
            # Calculer le timestamp simulé pour les métriques énergétiques
            ts_energy = get_simulated_time_iso(self._start_time, self._t_elapsed_s)
            await publisher.publish_energy(
                self.cluster_id,
                {
                    "energy_kwh_total": round(self.energy_kwh_total, 6),
                    "cost_eur_total": round(self.cost_eur_total, 4),
                    "pue_effective": self.pue_effective,
                },
                ts=ts_energy,
            )

    def stop(self) -> None:
        """Demande l'arrêt de la boucle de simulation."""

        self._running = False

    def _tick(self) -> None:
        """Effectue un seul pas de simulation pour toutes les machines.

        Utile pour les tests : permet de simuler un tick sans lancer la boucle async.
        Phase 8.2 : Bug #6-8 fix — ajouter cette méthode pour les tests.
        """
        # Phase 8.12A : dt_sim fixe = 1/tick_rate_hz (indépendant de speed_multiplier)
        # Le speed_multiplier est géré par batch_size dans run() async.
        dt_sim = 1.0 / self._tick_rate_hz
        load_factor = self._scenario_engine.get_load_factor(self._t_elapsed_s)

        for machine in self.machines.values():
            machine.tick(load_factor=load_factor, dt=dt_sim)

        self._fault_scheduler.tick(self.machines, dt=dt_sim)
        self._update_metrics()
        self._t_elapsed_s += dt_sim

    # ------------------------------------------------------------------
    # Métriques & snapshot
    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    # Métriques & snapshot
    # ------------------------------------------------------------------
    def _update_metrics(self) -> None:
        """Recalcule les métriques agrégées du cluster."""
        self.energy_kwh_total = sum(
            m.energy_kwh_cumulated for m in self.machines.values()
        )
        self.cost_eur_total = compute_cost(
            energy_kwh=self.energy_kwh_total,
            pue=self._pue,
            price_eur_kwh=self._price_eur_kwh,
        )
        self.pue_effective = self._pue

    def get_snapshot(self) -> dict:
        """Retourne un snapshot consolidé du cluster.

        Le timestamp utilise le temps simulé (start_time + _t_elapsed_s),
        pas l'heure réelle système.
        """
        return {
            "cluster_id": self.cluster_id,
            "ts": get_simulated_time_iso(self._start_time, self._t_elapsed_s),
            "t_elapsed_s": self._t_elapsed_s,  # Pour calculs downstream
            "metrics": {
                "energy_kwh_total": self.energy_kwh_total,
                "cost_eur_total": self.cost_eur_total,
                "pue_effective": self.pue_effective,
            },
            "machines": {mid: m.snapshot() for mid, m in self.machines.items()},
        }

    # ------------------------------------------------------------------
    # Phase 8.4 — Contrôle de vitesse de simulation
    # ------------------------------------------------------------------

    def set_speed_multiplier(self, multiplier: float) -> None:
        """Change la vitesse de simulation à chaud.

        Args:
            multiplier: Multiplicateur de vitesse (doit être > 0)
                       1.0 = real-time
                       60.0 = 1 min/sec
                       3600.0 = 1 hour/sec
                       86400.0 = 1 day/sec

        Raises:
            ValueError: Si multiplier <= 0
        """
        if multiplier <= 0:
            raise ValueError(
                f"speed_multiplier must be > 0, got {multiplier}"
            )

        old_multiplier = self._speed_multiplier
        self._speed_multiplier = multiplier

        logger.info(
            f"Speed multiplier changed from {old_multiplier}x to {multiplier}x "
            f"({self.get_speed_name(multiplier)})"
        )

    def get_speed_multiplier(self) -> float:
        """Retourne le multiplier de vitesse actuel."""
        return self._speed_multiplier

    def get_speed_info(self) -> dict[str, Any]:
        """Retourne les informations complètes sur la vitesse de simulation.

        Returns:
            dict avec :
            - speed_multiplier: multiplier actuel
            - speed_name: nom lisible (ex: "1 hour/sec")
            - cpu_throttle_enabled: true si throttle activé
            - cpu_throttle_target_hz: fréquence cible réelle
            - real_tick_rate_hz: fréquence réelle de ticks
            - simulated_tick_rate_hz: fréquence simulée de ticks
        """
        real_tick_hz = (
            self._cpu_throttle_target_hz
            if self._cpu_throttle_enabled
            else self._tick_rate_hz
        )
        simulated_tick_hz = real_tick_hz * self._speed_multiplier

        return {
            "speed_multiplier": self._speed_multiplier,
            "speed_name": self.get_speed_name(self._speed_multiplier),
            "cpu_throttle_enabled": self._cpu_throttle_enabled,
            "cpu_throttle_target_hz": self._cpu_throttle_target_hz,
            "real_tick_rate_hz": real_tick_hz,
            "simulated_tick_rate_hz": simulated_tick_hz,
            "elapsed_time_s": self._t_elapsed_s,
            "elapsed_time_formatted": self._format_duration(self._t_elapsed_s),
        }

    def set_cpu_throttle(
        self, enabled: bool, target_hz: float | None = None
    ) -> None:
        """Configure le throttling CPU.

        Args:
            enabled: True pour activer throttle
            target_hz: Fréquence cible (50-500 Hz), ignoré si enabled=False
        """
        self._cpu_throttle_enabled = enabled

        if enabled and target_hz is not None:
            if not (50.0 <= target_hz <= 500.0):
                logger.warning(
                    f"cpu_throttle_target_hz {target_hz} outside "
                    "recommended range [50, 500]"
                )
            self._cpu_throttle_target_hz = target_hz
            self._throttle_interval_s = 1.0 / target_hz
        elif enabled:
            self._throttle_interval_s = 1.0 / self._cpu_throttle_target_hz

        logger.info(
            f"CPU throttle {'enabled' if enabled else 'disabled'}"
            + (f" (target: {target_hz} Hz)" if enabled and target_hz else "")
        )

    def reset_time_and_energy(self) -> None:
        """Réinitialise le temps écoulé et l'énergie accumulée.

        Utile pour recommencer une expérience après une longue simulation.
        """
        self._t_elapsed_s = 0.0
        self.energy_kwh_total = 0.0
        self.cost_eur_total = 0.0

        for machine in self.machines.values():
            machine.energy_kwh_cumulated = 0.0

        logger.info("Time and energy metrics reset")

    async def reset_time_and_energy_with_timescaledb(self) -> None:
        """Réinitialise le temps + énergie + vide TimescaleDB (reset complet).

        Utile pour recommencer une expérience avec historique propre.
        Cette méthode est asynchrone car elle appelle TimescaleDB.
        """
        import asyncpg
        import os

        # Soft reset
        self.reset_time_and_energy()

        # Hard reset — vider TimescaleDB
        try:
            # Configuration TimescaleDB depuis ENV ou défauts
            tsdb_host = os.getenv("TIMESCALE_HOST", "timescaledb")
            tsdb_port = int(os.getenv("TIMESCALE_PORT", "5432"))
            tsdb_user = os.getenv("TIMESCALE_USER", "jumeaux")
            tsdb_password = os.getenv("TIMESCALE_PASSWORD", "jumeaux")  # Défaut: "jumeaux"
            tsdb_db = os.getenv("TIMESCALE_DB", "jumeaux")

            # Construire DSN avec authentification
            if tsdb_password:
                dsn = f"postgresql://{tsdb_user}:{tsdb_password}@{tsdb_host}:{tsdb_port}/{tsdb_db}"
            else:
                dsn = f"postgresql://{tsdb_user}@{tsdb_host}:{tsdb_port}/{tsdb_db}"

            logger.info(f"Connecting to TimescaleDB: {tsdb_host}:{tsdb_port}/{tsdb_db} as {tsdb_user}")

            # Connexion et truncate
            conn = await asyncpg.connect(dsn)
            try:
                await conn.execute("TRUNCATE TABLE events CASCADE;")
                await conn.execute("TRUNCATE TABLE telemetry CASCADE;")
                logger.info("TimescaleDB tables truncated (events, telemetry)")
            finally:
                await conn.close()

        except Exception as exc:
            logger.error(f"TimescaleDB reset failed: {exc}")
            # Ne pas lever l'exception — le soft reset a réussi
            # Log seulement pour avertir l'utilisateur

    def get_snapshot_buffer_info(self) -> dict[str, Any]:
        """Retourne des infos sur le buffer de snapshots pour export ML.

        Returns:
            dict avec :
            - buffer_size: nombre de snapshots en buffer
            - buffer_maxlen: taille max du buffer
            - estimated_size_gb: estimation de taille si exportés
        """
        snapshot_count = len(self._snapshot_buffer)
        estimated_size_bytes = snapshot_count * 5000  # ~5 KB par snapshot
        estimated_size_gb = estimated_size_bytes / (1024**3)

        return {
            "buffer_size": snapshot_count,
            "buffer_maxlen": self._snapshot_buffer.maxlen,
            "estimated_size_gb": round(estimated_size_gb, 2),
            "estimated_size_mb": round(estimated_size_bytes / (1024**2), 2),
        }

    @staticmethod
    def get_speed_name(multiplier: float) -> str:
        """Retourne un nom lisible pour le multiplier."""
        if multiplier == 1.0:
            return "Real-time (1 sec/sec)"
        elif multiplier == 60.0:
            return "1 min/sec"
        elif multiplier == 3600.0:
            return "1 hour/sec"
        elif multiplier == 86400.0:
            return "1 day/sec"
        else:
            return f"{multiplier:.1f}x"

    @staticmethod
    def _format_duration(seconds: float) -> str:
        """Formate une durée en secondes en chaîne lisible.

        Ex: 3661.5 → "1h 1m 1s"
        """
        if seconds < 60:
            return f"{seconds:.1f}s"

        days = int(seconds // 86400)
        remaining = seconds % 86400

        hours = int(remaining // 3600)
        remaining = remaining % 3600

        minutes = int(remaining // 60)
        secs = remaining % 60

        parts = []
        if days > 0:
            parts.append(f"{days}d")
        if hours > 0:
            parts.append(f"{hours}h")
        if minutes > 0:
            parts.append(f"{minutes}m")
        if secs > 0 or not parts:
            parts.append(f"{secs:.0f}s")

        return " ".join(parts)
