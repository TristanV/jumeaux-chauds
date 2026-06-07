#!/usr/bin/env python3
"""Analyse du risque thermique par scénario — Jumeaux Chauds.

Pour chaque scénario disponible, simule une durée configurable et produit :
  - % du temps passé en zone DANGER (T >= 95% * t_shutdown_c → état "degraded")
  - % du temps passé en SURCHAUFFE (T >= t_shutdown_c → état "off" par overheat)
  - nombre d'événements overheat par machine et par heure simulée
  - température moyenne, max, min pendant les phases actives
  - énergie consommée totale et par machine
  - taux de pannes injectées (fan_failure, power_surge, etc.) si scénario avec injection

Usage :
    python scripts/analyze_thermal_risk.py
    python scripts/analyze_thermal_risk.py --duration 2h --scenarios stress heatwave
    python scripts/analyze_thermal_risk.py --duration 30m --output rapport_thermique.txt

Options :
    --duration     Durée simulée par scénario (ex: 30m, 1h, 6h). Défaut: 1h
    --scenarios    Scénarios à analyser (défaut: tous)
    --output       Chemin fichier de sortie (défaut: affichage console uniquement)
    --tick-rate    Ticks/s simulée (défaut: 10, idem simulation normale)
    --no-color     Désactiver la colorisation ANSI (pour export fichier)
"""
from __future__ import annotations

import argparse
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).parent.parent.absolute()
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from config.loader import load_config
from simulation.cluster import ClusterSimulator
from simulation.duration import parse_duration
from omegaconf import OmegaConf


# ── ANSI colors ───────────────────────────────────────────────────────────────

USE_COLOR = True

def c(text: str, code: str) -> str:
    if not USE_COLOR:
        return text
    return f"\033[{code}m{text}\033[0m"

RED    = "31;1"
YELLOW = "33;1"
GREEN  = "32;1"
CYAN   = "36;1"
BOLD   = "1"
DIM    = "2"


# ── Structures de résultats ───────────────────────────────────────────────────

@dataclass
class MachineStats:
    machine_id: str
    role: str
    t_shutdown_c: float
    t_danger_c: float  # 95% * t_shutdown_c

    # Compteurs de ticks (machine active = status "on" ou "degraded")
    ticks_total: int = 0
    ticks_active: int = 0          # status "on" ou "degraded"
    ticks_off_voluntary: int = 0   # status "off" non lié à surchauffe
    ticks_off_overheat: int = 0    # status "off" par surchauffe
    ticks_degraded: int = 0        # status "degraded" (zone danger)

    # Températures (sur ticks actifs uniquement)
    temp_sum: float = 0.0
    temp_max: float = 0.0
    temp_min: float = 999.0
    ticks_above_danger: int = 0    # T >= t_danger_c pendant phase active

    # Énergie
    energy_kwh_start: float = 0.0
    energy_kwh_end: float = 0.0

    # Événements
    overheat_events: int = 0       # transitions → off par overheat
    degraded_events: int = 0       # transitions → degraded
    fault_events: int = 0          # pannes injectées détectées

    # Fan stats
    fan_rpm_sum: float = 0.0
    fan_rpm_count: int = 0

    def record_tick(self, snapshot: dict, prev_status: str) -> None:
        self.ticks_total += 1
        status = snapshot["status"]
        temp = snapshot["temperature_c"]

        if status in ("on", "degraded"):
            self.ticks_active += 1
            self.temp_sum += temp
            self.temp_max = max(self.temp_max, temp)
            self.temp_min = min(self.temp_min, temp)
            if temp >= self.t_danger_c:
                self.ticks_above_danger += 1
            # Fan rpm moyen
            for fan in snapshot.get("fans", []):
                self.fan_rpm_sum += fan.get("rpm", 0)
                self.fan_rpm_count += 1

        if status == "degraded":
            self.ticks_degraded += 1
            if prev_status == "on":
                self.degraded_events += 1

        if status == "off":
            # Détecter si c'est un arrêt par surchauffe
            # (la machine était active avant et la temp est encore élevée)
            if prev_status in ("on", "degraded") and temp >= self.t_danger_c * 0.85:
                self.ticks_off_overheat += 1
                if prev_status in ("on", "degraded"):
                    self.overheat_events += 1
            else:
                self.ticks_off_voluntary += 1

        # Pannes actives
        if snapshot.get("faults"):
            self.fault_events = max(self.fault_events, len(snapshot["faults"]))

    @property
    def temp_mean(self) -> float:
        return self.temp_sum / self.ticks_active if self.ticks_active else 0.0

    @property
    def pct_active(self) -> float:
        return 100.0 * self.ticks_active / self.ticks_total if self.ticks_total else 0.0

    @property
    def pct_danger(self) -> float:
        """% du temps actif passé en zone danger (T >= 95% t_shutdown)."""
        return 100.0 * self.ticks_above_danger / self.ticks_active if self.ticks_active else 0.0

    @property
    def pct_degraded(self) -> float:
        return 100.0 * self.ticks_degraded / self.ticks_total if self.ticks_total else 0.0

    @property
    def pct_off_overheat(self) -> float:
        return 100.0 * self.ticks_off_overheat / self.ticks_total if self.ticks_total else 0.0

    @property
    def energy_kwh(self) -> float:
        return self.energy_kwh_end - self.energy_kwh_start

    @property
    def fan_rpm_mean(self) -> float:
        return self.fan_rpm_sum / self.fan_rpm_count if self.fan_rpm_count else 0.0


@dataclass
class ScenarioReport:
    scenario: str
    duration_s: float
    tick_rate_hz: float
    ticks_total: int = 0
    machine_stats: dict[str, MachineStats] = field(default_factory=dict)
    energy_kwh_total: float = 0.0
    cost_eur_total: float = 0.0
    wall_time_s: float = 0.0
    error: str = ""

    @property
    def machines_count(self) -> int:
        return len(self.machine_stats)

    @property
    def overheat_events_total(self) -> int:
        return sum(s.overheat_events for s in self.machine_stats.values())

    @property
    def overheat_events_per_hour(self) -> float:
        duration_h = self.duration_s / 3600.0
        return self.overheat_events_total / duration_h if duration_h else 0.0

    @property
    def pct_danger_mean(self) -> float:
        vals = [s.pct_danger for s in self.machine_stats.values()]
        return sum(vals) / len(vals) if vals else 0.0

    @property
    def risk_level(self) -> str:
        """Niveau de risque global : LOW / MEDIUM / HIGH / CRITICAL."""
        oh_per_h = self.overheat_events_per_hour
        pct = self.pct_danger_mean
        if oh_per_h >= 2.0 or pct >= 30.0:
            return "CRITICAL"
        if oh_per_h >= 0.5 or pct >= 10.0:
            return "HIGH"
        if oh_per_h >= 0.1 or pct >= 3.0:
            return "MEDIUM"
        return "LOW"


# ── Simulation synchrone ──────────────────────────────────────────────────────

SCENARIOS_AVAILABLE = ["basic", "nominal", "heatwave", "busy_weeks", "stress"]


def run_scenario(
    scenario_name: str,
    duration_s: float,
    tick_rate_hz: float = 10.0,
) -> ScenarioReport:
    """Simule un scénario de manière synchrone et collecte les statistiques."""

    report = ScenarioReport(
        scenario=scenario_name,
        duration_s=duration_s,
        tick_rate_hz=tick_rate_hz,
    )

    try:
        cfg = load_config(scenario=scenario_name)
    except Exception as exc:
        report.error = f"Chargement config échoué : {exc}"
        return report

    # Forcer tick_rate et speed_multiplier — garder DictConfig (get_machine_config en a besoin)
    cfg = OmegaConf.merge(cfg, OmegaConf.create({
        "simulation": {
            "tick_rate_hz": tick_rate_hz,
            "speed_multiplier": 1.0,
        }
    }))

    # Override heatwave : ambient_temp_c ne peut pas venir de heatwave.yaml (OmegaConf
    # corrompt cluster.machines lors du merge d'une section cluster:). On l'applique ici.
    if scenario_name == "heatwave":
        heatwave_ambient = 32.0
        for role in ("master", "worker"):
            OmegaConf.update(
                cfg,
                f"cluster.role_profiles.{role}.thermal.ambient_temp_c",
                heatwave_ambient,
                merge=True,
            )

    try:
        sim = ClusterSimulator(cfg)  # passer DictConfig, pas dict
    except Exception as exc:
        report.error = f"Init simulateur échoué : {exc}"
        return report

    # Allumer toutes les machines si elles sont off par défaut
    for machine in sim.machines.values():
        if machine.status == "off":
            machine.power_on()

    # Initialiser les stats par machine
    for mid, machine in sim.machines.items():
        t_shutdown = machine.thermal.t_shutdown_c
        stats = MachineStats(
            machine_id=mid,
            role=machine.role,
            t_shutdown_c=t_shutdown,
            t_danger_c=t_shutdown * 0.95,
        )
        stats.energy_kwh_start = machine.energy_kwh_cumulated
        report.machine_stats[mid] = stats

    # Boucle synchrone
    dt = 1.0 / tick_rate_hz
    n_ticks = int(duration_s * tick_rate_hz)
    prev_statuses: dict[str, str] = {mid: m.status for mid, m in sim.machines.items()}

    t_wall_start = time.monotonic()
    LOG_EVERY = max(1, n_ticks // 20)  # log toutes les 5%

    for tick_i in range(n_ticks):
        # Tick de simulation
        sim._tick()

        # Collecter les stats
        for mid, machine in sim.machines.items():
            snap = machine.snapshot()
            report.machine_stats[mid].record_tick(snap, prev_statuses[mid])
            prev_statuses[mid] = machine.status

        report.ticks_total += 1

        if tick_i % LOG_EVERY == 0:
            pct = 100.0 * tick_i / n_ticks
            elapsed = time.monotonic() - t_wall_start
            eta = (elapsed / (tick_i + 1)) * (n_ticks - tick_i - 1)
            print(
                f"  {scenario_name:15s} [{pct:5.1f}%] "
                f"t_sim={sim._t_elapsed_s/3600:.2f}h | "
                f"ETA {eta:.0f}s     ",
                end="\r",
                flush=True,
            )

    print(" " * 70, end="\r")  # Effacer la ligne de progression

    # Métriques finales
    report.wall_time_s = time.monotonic() - t_wall_start
    report.energy_kwh_total = sim.energy_kwh_total
    report.cost_eur_total = sim.cost_eur_total

    for mid, machine in sim.machines.items():
        report.machine_stats[mid].energy_kwh_end = machine.energy_kwh_cumulated

    return report


# ── Rendu du rapport ──────────────────────────────────────────────────────────

RISK_COLORS = {
    "LOW": GREEN,
    "MEDIUM": YELLOW,
    "HIGH": RED,
    "CRITICAL": "35;1",  # magenta bold
}


def format_report(report: ScenarioReport) -> str:
    lines: list[str] = []

    def line(s: str = "") -> None:
        lines.append(s)

    if report.error:
        line(c(f"✗ ERREUR [{report.scenario}] : {report.error}", RED))
        return "\n".join(lines)

    risk = report.risk_level
    risk_col = RISK_COLORS.get(risk, BOLD)

    # ── En-tête scénario ──
    line(c("─" * 72, DIM))
    line(c(f"  SCÉNARIO : {report.scenario.upper():<20}", BOLD) +
         c(f"  RISQUE : {risk}", risk_col))
    line(c("─" * 72, DIM))

    dur_h = report.duration_s / 3600.0
    line(f"  Durée simulée  : {dur_h:.1f}h  |  "
         f"Ticks : {report.ticks_total:,}  |  "
         f"Wall time : {report.wall_time_s:.1f}s  |  "
         f"Perf : {report.ticks_total/report.wall_time_s:.0f} ticks/s")
    line(f"  Énergie totale : {report.energy_kwh_total:.4f} kWh  |  "
         f"Coût : {report.cost_eur_total:.4f} €")
    line(f"  Overheats      : {report.overheat_events_total} événements "
         f"({report.overheat_events_per_hour:.2f}/h simulée)")

    # ── Tableau par machine ──
    line("")
    line(c(
        f"  {'Machine':<18} {'Rôle':<8} {'Actif%':>6} {'T_moy':>7} {'T_max':>7} "
        f"{'Danger%':>8} {'Dégradé%':>9} {'Overheat':>9} {'Fan_RPM':>8} {'Énergie':>9}",
        BOLD
    ))
    line(c("  " + "-" * 90, DIM))

    for mid, s in sorted(report.machine_stats.items()):
        danger_str = f"{s.pct_danger:.1f}%"
        danger_col = (
            RED if s.pct_danger >= 10.0 else
            YELLOW if s.pct_danger >= 3.0 else
            GREEN
        )
        overheat_col = RED if s.overheat_events > 0 else GREEN
        line(
            f"  {mid:<18} {s.role:<8} "
            f"{s.pct_active:>5.1f}% "
            f"{s.temp_mean:>6.1f}°C "
            f"{s.temp_max:>6.1f}°C "
            f"{c(f'{danger_str:>8}', danger_col)} "
            f"{s.pct_degraded:>8.1f}% "
            f"{c(f'{s.overheat_events:>8}', overheat_col)} "
            f"{s.fan_rpm_mean:>7.0f} "
            f"{s.energy_kwh:>8.4f} kWh"
        )

    # ── Synthèse risque ──
    line("")
    line(c("  SYNTHÈSE RISQUE :", BOLD))
    max_temp_machine = max(report.machine_stats.values(), key=lambda s: s.temp_max)
    most_overheat = max(report.machine_stats.values(), key=lambda s: s.overheat_events)

    if report.overheat_events_total == 0:
        line(c("  ✓ Aucun événement de surchauffe détecté.", GREEN))
        if report.pct_danger_mean < 1.0:
            line(c("  ✓ Températures largement en dessous des seuils.", GREEN))
        else:
            line(c(f"  ⚠ Temps moyen en zone danger : {report.pct_danger_mean:.1f}% — surveiller.", YELLOW))
    else:
        line(c(
            f"  ✗ {report.overheat_events_total} surchauffe(s) — "
            f"{report.overheat_events_per_hour:.2f}/heure simulée.", RED
        ))
        line(c(
            f"  ✗ Machine la plus impactée : {most_overheat.machine_id} "
            f"({most_overheat.overheat_events} overheats)", RED
        ))

    line(c(
        f"  ℹ T_max absolue : {max_temp_machine.temp_max:.1f}°C "
        f"sur {max_temp_machine.machine_id} "
        f"(seuil = {max_temp_machine.t_shutdown_c:.0f}°C, "
        f"danger = {max_temp_machine.t_danger_c:.1f}°C)",
        CYAN
    ))

    line("")
    return "\n".join(lines)


def format_global_summary(reports: list[ScenarioReport]) -> str:
    lines: list[str] = []

    lines.append("")
    lines.append(c("═" * 72, BOLD))
    lines.append(c("  COMPARAISON GLOBALE — RISQUE THERMIQUE PAR SCÉNARIO", BOLD))
    lines.append(c("═" * 72, BOLD))
    lines.append(c(
        f"  {'Scénario':<18} {'Risque':<10} {'Overheats':>10} {'OH/heure':>10} "
        f"{'Danger%moy':>12} {'T_max':>8} {'Énergie':>12}",
        BOLD
    ))
    lines.append(c("  " + "-" * 72, DIM))

    for r in reports:
        if r.error:
            lines.append(f"  {r.scenario:<18} {'ERREUR':<10}  {r.error}")
            continue
        risk = r.risk_level
        risk_col = RISK_COLORS.get(risk, BOLD)
        t_max_all = max((s.temp_max for s in r.machine_stats.values()), default=0.0)
        lines.append(
            f"  {r.scenario:<18} {c(f'{risk:<10}', risk_col)} "
            f"{r.overheat_events_total:>10} "
            f"{r.overheat_events_per_hour:>10.2f} "
            f"{r.pct_danger_mean:>11.1f}% "
            f"{t_max_all:>7.1f}°C "
            f"{r.energy_kwh_total:>10.4f} kWh"
        )

    lines.append("")
    lines.append(c("  Légende :", DIM))
    lines.append(c("    Danger%   = % du temps actif avec T >= 95% du seuil de shutdown", DIM))
    lines.append(c("    OH/heure  = nombre d'overheats par heure simulée", DIM))
    lines.append(c("    CRITICAL  : OH/h >= 2.0 ou Danger% >= 30%", DIM))
    lines.append(c("    HIGH      : OH/h >= 0.5 ou Danger% >= 10%", DIM))
    lines.append(c("    MEDIUM    : OH/h >= 0.1 ou Danger% >= 3%", DIM))
    lines.append(c("    LOW       : en-dessous de ces seuils", DIM))
    lines.append("")

    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    global USE_COLOR

    parser = argparse.ArgumentParser(
        description="Analyse du risque thermique par scénario — Jumeaux Chauds",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--duration", default="1h",
        help="Durée simulée par scénario (ex: 30m, 1h, 6h). Défaut: 1h"
    )
    parser.add_argument(
        "--scenarios", nargs="+", default=SCENARIOS_AVAILABLE,
        help=f"Scénarios à analyser. Disponibles: {', '.join(SCENARIOS_AVAILABLE)}"
    )
    parser.add_argument(
        "--output", default=None,
        help="Fichier de sortie (en plus de la console)"
    )
    parser.add_argument(
        "--tick-rate", type=float, default=10.0,
        help="Ticks/s simulée (défaut: 10)"
    )
    parser.add_argument(
        "--no-color", action="store_true",
        help="Désactiver les couleurs ANSI"
    )
    args = parser.parse_args()

    if args.no_color or args.output:
        USE_COLOR = False

    duration_s = parse_duration(args.duration)
    if duration_s <= 0:
        duration_s = 3600.0  # 1h par défaut si "0" passé

    print(c(f"\n  Analyse thermique — durée: {args.duration} ({duration_s:.0f}s) "
            f"— scénarios: {', '.join(args.scenarios)}\n", BOLD))

    reports: list[ScenarioReport] = []

    for scenario in args.scenarios:
        print(c(f"  → Simulation {scenario}...", CYAN))
        t0 = time.monotonic()
        report = run_scenario(scenario, duration_s, tick_rate_hz=args.tick_rate)
        elapsed = time.monotonic() - t0
        if report.error:
            print(c(f"  ✗ {scenario} : {report.error}", RED))
        else:
            print(c(f"  ✓ {scenario} terminé en {elapsed:.1f}s "
                    f"({report.ticks_total/elapsed:.0f} ticks/s)", GREEN))
        reports.append(report)

    # Affichage
    output_lines: list[str] = []
    for report in reports:
        block = format_report(report)
        print(block)
        output_lines.append(block)

    summary = format_global_summary(reports)
    print(summary)
    output_lines.append(summary)

    # Export fichier
    if args.output:
        # Désactiver couleurs pour le fichier
        saved = USE_COLOR
        USE_COLOR = False
        file_content: list[str] = []
        for report in reports:
            file_content.append(format_report(report))
        file_content.append(format_global_summary(reports))
        USE_COLOR = saved

        out_path = Path(args.output)
        full_text = "\n".join(file_content)
        out_path.write_text(full_text, encoding="utf-8")
        print(c(f"  Rapport sauvegardé : {out_path.resolve()}", CYAN))


if __name__ == "__main__":
    main()
