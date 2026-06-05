"""Simulateur de machine individuelle.

Cette classe encapsule l'état d'une machine, sa dynamique thermique
et la gestion des ventilateurs / pannes.

Elle ne connaît pas MQTT ni FastAPI : uniquement de la logique métier.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from .physics import (
    compute_energy_kwh,
    compute_fan_auto_speed,
    compute_fan_power_rpm,
    compute_heat_input,
    compute_load_power,
    compute_thermal_step,
)
from .noise import gaussian_noise


MachineStatus = Literal["on", "off", "degraded"]
FanMode = Literal["auto", "manual"]


@dataclass
class FanState:
    """État d'un ventilateur individuel."""

    rpm: int = 0
    mode: FanMode = "auto"


@dataclass
class ActiveFault:
    """Représente une panne injectée sur une machine."""

    fault_type: str
    remaining_s: float
    magnitude: float


@dataclass
class ThermalConfig:
    """Paramètres thermiques d'une machine.

    Ces champs sont extraits depuis la configuration YAML mergée.

    Changes Phase 7.2 :
    - Ajout de power_std_w et fan_speed_std_rpm pour le bruit réaliste
    """

    idle_w: float
    max_w: float
    alpha: float
    heat_ratio: float
    tau_max_s: float
    k_cool: float
    c_th_j_per_c: float
    ambient_temp_c: float
    t_shutdown_c: float
    t_restart_c: float
    recovery_delay_s: float
    fan_gain_rpm_per_c: float
    fan_max_rpm: int
    fan_power_w: float
    tick_rate_hz: float
    power_std_w: float = 0.0  # Phase 7.2 : bruit sur puissance (W)
    fan_speed_std_rpm: float = 0.0  # Phase 7.2 : bruit sur RPM (RPM)


@dataclass
class SensorConfig:
    """Paramètres d'une sonde de température."""

    sensor_id: str
    bias_c: float = 0.0
    noise_std_c: float = 0.0
    drift_rate_c_per_s: float = 0.0


@dataclass
class SensorState:
    """État interne associé à une sonde (pour la dérive)."""

    config: SensorConfig
    drift_c: float = 0.0


class MachineSimulator:
    """Simulation d'une machine unique.

    La simulation est pilotée par :
    - un `ThermalConfig` (paramètres physiques)
    - une liste de `SensorConfig` pour les sondes
    - un nombre de ventilateurs.

    La méthode principale est : `tick(load_factor, dt)`.
    """

    def __init__(
        self,
        machine_id: str,
        role: str,
        thermal: ThermalConfig,
        sensor_configs: list[SensorConfig],
        fan_count: int,
    ) -> None:
        self.id = machine_id
        self.role = role
        self.thermal = thermal

        self.status: MachineStatus = "off"
        self.temperature_c: float = thermal.ambient_temp_c
        self.power_w: float = 0.0
        self.energy_kwh_cumulated: float = 0.0
        self._time_since_overheat_s: float = 0.0
        self._shutdown_by_overheat: bool = False  # True = éteinte par surchauffe, False = OFF volontaire
        self.last_status_cause: str = "unknown"   # Cause de la dernière transition de statut

        self.fans: list[FanState] = [FanState() for _ in range(fan_count)]
        self._sensors: list[SensorState] = [
            SensorState(config=sc) for sc in sensor_configs
        ]

        self.faults: list[ActiveFault] = []

    # ---------------------------------------------------------------------
    # API de commande
    # ---------------------------------------------------------------------
    def power_on(self) -> bool:
        """Tente d'allumer la machine.

        Retourne False si la température est encore trop élevée pour un
        redémarrage (hystérésis thermique).
        """

        if self.temperature_c > self.thermal.t_restart_c:
            return False
        self.status = "on"
        self._time_since_overheat_s = 0.0
        self._shutdown_by_overheat = False
        self.last_status_cause = "manual_on"
        return True

    def power_off(self) -> None:
        """Éteint la machine (arrêt logique volontaire)."""

        self.status = "off"
        self._shutdown_by_overheat = False  # Arrêt volontaire : pas de redémarrage auto
        self.last_status_cause = "manual_off"

    def set_fan_speed(self, fan_idx: int, rpm: int) -> None:
        """Fixe manuellement la vitesse d'un ventilateur.

        Place automatiquement le fan en mode "manual".
        """

        if not 0 <= fan_idx < len(self.fans):
            return
        rpm_clamped = max(0, min(self.thermal.fan_max_rpm, int(rpm)))
        fan = self.fans[fan_idx]
        fan.mode = "manual"
        fan.rpm = rpm_clamped

    def set_fan_mode(self, fan_idx: int, mode: FanMode) -> None:
        """Change le mode d'un ventilateur (auto / manual).

        En mode auto, la consigne rpm sera recalculée à chaque tick.
        """

        if not 0 <= fan_idx < len(self.fans):
            return
        self.fans[fan_idx].mode = mode

    def inject_fault(self, fault_type: str, duration_s: float, magnitude: float) -> None:
        """Ajoute une panne active.

        L'interprétation précise de `fault_type` et `magnitude` est laissée
        au `tick()`, qui applique les effets (ex: fan_failure, power_surge...).
        """

        self.faults.append(
            ActiveFault(
                fault_type=fault_type,
                remaining_s=max(0.0, duration_s),
                magnitude=magnitude,
            )
        )

    def cancel_fault(self) -> None:
        """Annule toutes les pannes actives."""

        self.faults.clear()

    # ---------------------------------------------------------------------
    # Boucle de simulation
    # ---------------------------------------------------------------------
    def tick(self, load_factor: float, dt: float) -> None:
        """Effectue un pas de simulation.

        - Met à jour la température interne selon le modèle thermique.
        - Applique les pannes actives.
        - Met à jour l'énergie cumulée.
        - Gère les transitions d'état (on/off/degraded).
        """

        # Mise à jour des durées restantes des pannes
        for fault in list(self.faults):
            fault.remaining_s -= dt
            if fault.remaining_s <= 0:
                self.faults.remove(fault)

        # Si la machine est éteinte volontairement (power_off utilisateur) :
        # refroidissement passif uniquement, pas de redémarrage automatique.
        if self.status == "off" and not self._shutdown_by_overheat:
            self.power_w = 0.0
            from .physics import compute_tau, compute_thermal_step
            tau = compute_tau(
                tau_max=self.thermal.tau_max_s,
                fan_rpm_mean=0.0,
                k_cool=self.thermal.k_cool,
            )
            self.temperature_c = compute_thermal_step(
                t_current=self.temperature_c,
                q_in=0.0,
                tau=tau,
                c_th=self.thermal.c_th_j_per_c,
                t_amb=self.thermal.ambient_temp_c,
                dt=dt,
            )
            return

        # Si la machine est éteinte par surchauffe : refroidissement passif
        # puis redémarrage automatique dès que T < t_restart_c.
        if self.status == "off" and self._shutdown_by_overheat:
            self.power_w = 0.0
            from .physics import compute_tau, compute_thermal_step
            tau = compute_tau(
                tau_max=self.thermal.tau_max_s,
                fan_rpm_mean=0.0,
                k_cool=self.thermal.k_cool,
            )
            self.temperature_c = compute_thermal_step(
                t_current=self.temperature_c,
                q_in=0.0,
                tau=tau,
                c_th=self.thermal.c_th_j_per_c,
                t_amb=self.thermal.ambient_temp_c,
                dt=dt,
            )
            # Redémarrage automatique si T suffisamment basse
            if self.temperature_c <= self.thermal.t_restart_c:
                self.status = "on"
                self._shutdown_by_overheat = False
                self._time_since_overheat_s = 0.0
                self.last_status_cause = "thermal_recovery"
            return

        # Machine en fonctionnement (on ou degraded)
        self._integrate_thermal(load_factor=load_factor, dt=dt)

        # Gestion de la surchauffe : passage en OFF avec flag overheat
        if self.temperature_c >= self.thermal.t_shutdown_c:
            self.status = "off"
            self._shutdown_by_overheat = True
            self._time_since_overheat_s = 0.0
            self.last_status_cause = "overheat"
            return

        # Gestion de l'état degraded (surchauffe partielle sans shutdown)
        if self.temperature_c >= self.thermal.t_shutdown_c * 0.95:
            # Zone de danger : 95% du seuil → mode dégradé
            if self.status == "on":
                self.status = "degraded"
                self._time_since_overheat_s = 0.0
                self.last_status_cause = "overheat_partial"
        elif self.status == "degraded":
            self._time_since_overheat_s += dt
            if self._time_since_overheat_s >= self.thermal.recovery_delay_s:
                self.status = "on"
                self._time_since_overheat_s = 0.0
                self.last_status_cause = "degraded_recovery"

    # ------------------------------------------------------------------
    # Détails internes
    # ------------------------------------------------------------------
    def _integrate_thermal(self, load_factor: float, dt: float) -> None:
        """Met à jour température et énergie en tenant compte des fans/pannes.

        Changes Phase 7.2 :
        - Ajoute du bruit sur power_w et fan RPM (via gaussian_noise)
        - Calcule la puissance des fans selon RPM³ (formule réaliste)
        - Constante de temps tau dépend maintenant des RPM (fans -> refroidissement)
        """

        # Vitesse des fans (auto vs manual)
        fan_rpms: list[int] = []
        for fan in self.fans:
            if fan.mode == "auto":
                fan.rpm = compute_fan_auto_speed(
                    t_current=self.temperature_c,
                    t_amb=self.thermal.ambient_temp_c,
                    gain_rpm_per_c=self.thermal.fan_gain_rpm_per_c,
                    f_max=self.thermal.fan_max_rpm,
                )
            fan_rpms.append(fan.rpm)

        fan_rpm_mean = float(sum(fan_rpms) / len(fan_rpms)) if fan_rpms else 0.0

        # Puissance électrique de base en fonction de la charge
        power_w = compute_load_power(
            load_factor=load_factor,
            idle_w=self.thermal.idle_w,
            max_w=self.thermal.max_w,
            alpha=self.thermal.alpha,
        )

        # Phase 7.2 : Ajouter du bruit sur la puissance (capteur réaliste)
        # power_std_w est maintenant exploité
        power_w = gaussian_noise(power_w, std=getattr(self.thermal, 'power_std_w', 0.0))

        self.power_w = power_w

        # --- APPLICATION DES PANNES ---
        # Gestion des différents types de pannes
        for fault in self.faults:
            if fault.fault_type == "power_surge":
                # Surconsommation électrique
                power_w *= 1.0 + fault.magnitude
            elif fault.fault_type == "fan_failure":
                # Ventilateurs arrêtés → zéro refroidissement actif
                fan_rpm_mean = 0.0

        # Chaleur injectée (après application des pannes power_surge)
        q_in = compute_heat_input(power_w=power_w, heat_ratio=self.thermal.heat_ratio)

        # Phase 8.7 : Constante de temps améliorée avec formule réaliste
        # tau(RPM) = tau_max / (1 + k_cool * (RPM / RPM_max)^1.5)
        from .physics import compute_tau
        tau = compute_tau(
            tau_max=self.thermal.tau_max_s,
            fan_rpm_mean=fan_rpm_mean,
            k_cool=self.thermal.k_cool,
            fan_max_rpm=self.thermal.fan_max_rpm,  # Phase 8.7: nouveau paramètre
        )

        # Intégration de la température
        self.temperature_c = compute_thermal_step(
            t_current=self.temperature_c,
            q_in=q_in,
            tau=tau,
            c_th=self.thermal.c_th_j_per_c,
            t_amb=self.thermal.ambient_temp_c,
            dt=dt,
        )

        # Phase 7.2 : Calculer la puissance réelle de chaque fan selon RPM³
        fan_powers_w: list[float] = []
        for rpm in fan_rpms:
            fan_power = compute_fan_power_rpm(
                rpm=rpm,
                fan_power_w_nominal=self.thermal.fan_power_w,
                fan_max_rpm=self.thermal.fan_max_rpm,
            )
            fan_powers_w.append(fan_power)

        # Bug #9 Fix : Inclure la puissance des fans dans le snapshot
        power_w_total = power_w + sum(fan_powers_w)
        self.power_w = power_w_total

        # Mise à jour de l'énergie consommée (mode avancé avec RPM³)
        delta_kwh = compute_energy_kwh(
            power_w=power_w,
            fan_count=len(self.fans),
            fan_power_w_by_rpm=fan_powers_w,  # Nouveau paramètre
            tick_rate_hz=self.thermal.tick_rate_hz,
        )
        self.energy_kwh_cumulated += delta_kwh

    # ------------------------------------------------------------------
    # Observation pour MQTT / API
    # ------------------------------------------------------------------
    def snapshot(self) -> dict:
        """Retourne un snapshot JSON-serialisable de la machine.

        Le format est volontairement générique, le mapping exact vers les
        topics MQTT est effectué par la couche publisher.

        Les pannes sont appliquées à la lecture des capteurs :
        - sensor_drift : ajoute un décalage supplémentaire à la température lue
        """

        # Calculer la température lue (avec dérive capteur si panne active)
        temperature_read = self.temperature_c
        for fault in self.faults:
            if fault.fault_type == "sensor_drift":
                # sensor_drift ajoute un offset à la température lue
                # magnitude = décalage en °C (ex: 0.5 = +0.5°C d'erreur)
                temperature_read += fault.magnitude * 10.0  # Amplifier l'effet

        # Bug #11 Fix : Retourner sensors comme dict (clé = sensor_id)
        sensors_payload: dict[str, dict] = {}
        for sensor in self._sensors:
            sensors_payload[sensor.config.sensor_id] = {
                "temp_c": temperature_read + sensor.config.bias_c,
                "bias_c": sensor.config.bias_c,
            }

        fans_payload = [
            {"idx": idx, "rpm": fan.rpm, "mode": fan.mode}
            for idx, fan in enumerate(self.fans)
        ]

        faults_payload = [
            {
                "type": fault.fault_type,
                "remaining_s": max(0.0, fault.remaining_s),
                "magnitude": fault.magnitude,
            }
            for fault in self.faults
        ]

        return {
            "id": self.id,
            "role": self.role,
            "status": self.status,
            "temperature_c": temperature_read,
            "power_w": self.power_w,
            "energy_kwh_cumulated": self.energy_kwh_cumulated,
            "fans": fans_payload,
            "sensors": sensors_payload,
            "faults": faults_payload,
        }
