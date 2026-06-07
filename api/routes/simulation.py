"""Router /simulation — contrôle du simulateur depuis l'API.

Endpoints (Phase 4.4) :
  POST   /simulation/fault                → injecte une panne sur une machine
  DELETE /simulation/fault/{machine_id}   → annule toutes les pannes d'une machine
  PUT    /simulation/scenario             → change le scénario de charge à chaud

Endpoints (Phase 8.4) :
  GET    /simulation/speed                → infos vitesse de simulation
  PUT    /simulation/speed                → change la vitesse
  POST   /simulation/speed/reset          → réinitialise temps + énergie

Endpoints (Phase 8.13) :
  GET    /simulation/status               → état de la simulation (running/paused/stopped)
  POST   /simulation/start                → démarre ou reprend la simulation
  POST   /simulation/pause                → met en pause (conserve l'état)
  POST   /simulation/resume               → reprend depuis la pause
  POST   /simulation/stop                 → arrête la simulation (détruit la boucle)
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Body, HTTPException

from api import deps
from api.models import CommandResponse, FaultInjectCommand, ScenarioChangeCommand

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/fault", response_model=CommandResponse)
async def inject_fault(cmd: FaultInjectCommand) -> CommandResponse:
    """Injecte une panne sur une machine."""
    simulator = deps.get_cluster()
    machine = simulator.machines.get(cmd.machine_id)
    if machine is None:
        raise HTTPException(status_code=404, detail=f"Machine '{cmd.machine_id}' inconnue.")
    machine.inject_fault(
        fault_type=cmd.fault_type,
        duration_s=cmd.duration_s,
        magnitude=cmd.magnitude,
    )
    return CommandResponse(
        ok=True,
        message=(
            f"Panne '{cmd.fault_type}' injectée sur '{cmd.machine_id}' "
            f"(durée={cmd.duration_s}s, magnitude={cmd.magnitude})."
        ),
    )


@router.delete("/fault/{machine_id}", response_model=CommandResponse)
async def cancel_fault(machine_id: str) -> CommandResponse:
    """Annule toutes les pannes actives d'une machine."""
    simulator = deps.get_cluster()
    machine = simulator.machines.get(machine_id)
    if machine is None:
        raise HTTPException(status_code=404, detail=f"Machine '{machine_id}' inconnue.")
    machine.cancel_fault()
    return CommandResponse(ok=True, message=f"Pannes annulées sur '{machine_id}'.")


@router.get("/scenarios")
async def list_scenarios() -> dict:
    """Liste les scénarios disponibles."""
    from pathlib import Path

    scenarios_dir = Path(__file__).parent.parent.parent / "config" / "scenarios"
    scenarios = []
    if scenarios_dir.exists():
        scenarios = sorted(f.stem for f in scenarios_dir.glob("*.yaml") if f.is_file())

    return {
        "available_scenarios": scenarios if scenarios else ["nominal", "stress"],
        "count": len(scenarios) if scenarios else 2
    }


@router.put("/scenario", response_model=CommandResponse)
async def change_scenario(cmd: ScenarioChangeCommand) -> CommandResponse:
    """Change le scénario de charge à chaud.

    Recharge la config depuis le YAML correspondant et reconstruit
    le ScenarioEngine du simulateur sans redémarrer la boucle.
    """
    from config.loader import load_config
    from simulation.scenarios import LoadProfileConfig, ScenarioEngine
    from omegaconf import OmegaConf

    try:
        new_cfg = load_config(scenario=cmd.scenario)
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Scénario '{cmd.scenario}' invalide ou introuvable : {exc}",
        ) from exc

    simulator = deps.get_cluster()

    # Récupération sécurisée de la config simulation
    lp = OmegaConf.select(new_cfg, "simulation.load_profile")
    if lp is None:
        raise HTTPException(
            status_code=400,
            detail=f"Scénario '{cmd.scenario}' ne contient pas 'simulation.load_profile'",
        )

    lp_cfg = LoadProfileConfig(
        type=lp["type"],
        params={k: v for k, v in lp.items() if k != "type"},
    )

    # Vérification anticipée pour trace_replay : avertir si le fichier CSV est absent
    # (ne bloque pas — la boucle run() continuera en fallback load_factor=0.5)
    warning = None
    if lp["type"] == "trace_replay":
        from pathlib import Path
        trace_file = lp.get("trace_file", "data/traces/bitbrains_week_vm00.csv")
        trace_path = Path(trace_file)
        if not trace_path.is_absolute():
            project_root = Path(__file__).parent.parent.parent
            trace_path = project_root / trace_file
        if not trace_path.exists():
            warning = (
                f"Fichier de trace introuvable : {trace_file}. "
                f"La simulation tourne en fallback (load_factor=0.5). "
                f"Lancez scripts/download_traces.py pour télécharger les traces Bitbrains."
            )
            logger.warning(warning)

    simulator._scenario_engine = ScenarioEngine(profile_cfg=lp_cfg)

    # Mettre à jour le scénario actif dans deps
    deps._scenario_active = cmd.scenario

    logger.info("Scénario changé → '%s'", cmd.scenario)

    msg = f"Scénario changé vers '{cmd.scenario}' (profil: {lp['type']})."
    if warning:
        msg += f" ⚠️ {warning}"
    return CommandResponse(ok=True, message=msg)


# ------------------------------------------------------------------
# Phase 8.13 — Contrôle démarrage / pause / arrêt de la simulation
# ------------------------------------------------------------------


@router.get("/status")
async def get_simulation_status() -> dict:
    """Retourne l'état de la simulation : running, paused ou stopped."""
    simulator = deps.get_cluster()
    return {
        "simulation_status": simulator.get_status(),
        "running": simulator.is_running(),
        "paused": simulator.is_paused(),
        "elapsed_time_s": simulator._t_elapsed_s,
        "elapsed_time_formatted": simulator._format_duration(simulator._t_elapsed_s),
    }


@router.post("/start", response_model=CommandResponse)
async def start_simulation() -> CommandResponse:
    """Démarre la simulation si elle est arrêtée, ou reprend si elle est en pause.

    - Si arrêtée (stopped) → crée une nouvelle boucle asyncio
    - Si en pause (paused)  → reprend la boucle existante (équivalent à /resume)
    - Si déjà en cours     → no-op, retourne l'état actuel
    """
    simulator = deps.get_cluster()

    if simulator.is_running() and not simulator.is_paused():
        return CommandResponse(ok=True, message="Simulation déjà en cours.")

    if simulator.is_paused():
        # Juste lever la pause
        simulator.resume()
        return CommandResponse(ok=True, message="Simulation reprise depuis la pause.")

    # Stopped → lancer une nouvelle boucle
    ws_manager = deps._ws_manager
    publisher = deps._publisher

    sim_task = asyncio.create_task(
        simulator.run(publisher=publisher, ws_manager=ws_manager)
    )
    deps._sim_task = sim_task
    logger.info("Simulation démarrée manuellement via POST /simulation/start")
    return CommandResponse(ok=True, message="Simulation démarrée.")


@router.post("/pause", response_model=CommandResponse)
async def pause_simulation() -> CommandResponse:
    """Met la simulation en pause. L'état thermique et le temps simulé sont conservés."""
    simulator = deps.get_cluster()

    if not simulator.is_running():
        raise HTTPException(status_code=409, detail="La simulation n'est pas en cours.")
    if simulator.is_paused():
        return CommandResponse(ok=True, message="Simulation déjà en pause.")

    simulator.pause()
    return CommandResponse(ok=True, message="Simulation mise en pause.")


@router.post("/resume", response_model=CommandResponse)
async def resume_simulation() -> CommandResponse:
    """Reprend la simulation après une pause."""
    simulator = deps.get_cluster()

    if not simulator.is_running():
        raise HTTPException(status_code=409, detail="La simulation n'est pas en cours.")
    if not simulator.is_paused():
        return CommandResponse(ok=True, message="Simulation déjà en cours (non pausée).")

    simulator.resume()
    return CommandResponse(ok=True, message="Simulation reprise.")


@router.post("/stop", response_model=CommandResponse)
async def stop_simulation() -> CommandResponse:
    """Arrête la simulation. Utilisez /start pour redémarrer."""
    simulator = deps.get_cluster()

    if not simulator.is_running():
        return CommandResponse(ok=True, message="Simulation déjà arrêtée.")

    simulator.stop()
    if deps._sim_task is not None:
        deps._sim_task.cancel()
        deps._sim_task = None
    logger.info("Simulation arrêtée manuellement via POST /simulation/stop")
    return CommandResponse(ok=True, message="Simulation arrêtée.")


# ------------------------------------------------------------------
# Phase 8.4 — Contrôle de vitesse de simulation
# ------------------------------------------------------------------


@router.get("/speed")
async def get_speed_info() -> dict:
    """Retourne les infos complètes sur la vitesse de simulation.

    Returns:
        dict avec speed_multiplier, speed_name, cpu_throttle_enabled, etc.
    """
    simulator = deps.get_cluster()
    return simulator.get_speed_info()


class SpeedChangeRequest(dict):
    """Schéma pour changement de vitesse."""

    def __init__(self, speed_multiplier: float | None = None, speed_name: str | None = None):
        """
        Args:
            speed_multiplier: Multiplier numérique (ex: 3600.0)
            speed_name: Nom prédéfini (ex: "1 hour/sec")
        """
        super().__init__()
        self["speed_multiplier"] = speed_multiplier
        self["speed_name"] = speed_name


@router.put("/speed", response_model=CommandResponse)
async def change_speed(body: dict = Body(...)) -> CommandResponse:
    """Change la vitesse de simulation à chaud.

    Args:
        body: {"speed_multiplier": 3600.0} ou {"speed_name": "1 hour/sec"}

    Returns:
        CommandResponse avec confirmation du changement
    """
    simulator = deps.get_cluster()

    speed_multiplier: float | None = body.get("speed_multiplier")
    speed_name: str | None = body.get("speed_name")

    # Convertir speed_name en multiplier si fourni
    if speed_name:
        speed_map = {
            "Real-time (1 sec/sec)": 1.0,
            "1 min/sec": 60.0,
            "1 hour/sec": 3600.0,
            "1 day/sec": 86400.0,
        }
        if speed_name not in speed_map:
            raise HTTPException(
                status_code=400,
                detail=f"speed_name '{speed_name}' invalide. "
                f"Valeurs : {list(speed_map.keys())}",
            )
        speed_multiplier = speed_map[speed_name]
    elif speed_multiplier is None:
        raise HTTPException(
            status_code=400,
            detail="Paramètre manquant : 'speed_multiplier' ou 'speed_name' dans le body JSON",
        )

    try:
        simulator.set_speed_multiplier(speed_multiplier)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return CommandResponse(
        ok=True,
        message=(
            f"Vitesse changée à {speed_multiplier}x "
            f"({simulator.get_speed_name(speed_multiplier)})"
        ),
    )


@router.post("/speed/reset", response_model=CommandResponse)
async def reset_time_and_energy() -> CommandResponse:
    """Réinitialise le temps écoulé et l'énergie accumulée (soft reset).

    NOTE: TimescaleDB n'est PAS truncatée. Utilisez POST /reset pour reset complet.

    Returns:
        CommandResponse avec confirmation
    """
    simulator = deps.get_cluster()
    simulator.reset_time_and_energy()

    return CommandResponse(
        ok=True,
        message="Temps écoulé et énergie réinitialisés (soft reset)",
    )


@router.post("/reset", response_model=CommandResponse)
async def reset_complete() -> CommandResponse:
    """Réinitialise COMPLÈTEMENT : temps + énergie + TimescaleDB (hard reset).

    Vide les tables TimescaleDB (telemetry, events) et réinitialise la simulation.
    ⚠️ DESTRUCTIF — impossible à annuler.

    Returns:
        CommandResponse avec confirmation
    """
    simulator = deps.get_cluster()

    try:
        await simulator.reset_time_and_energy_with_timescaledb()
        return CommandResponse(
            ok=True,
            message=(
                "Reset complet effectué :\n"
                "- Temps écoulé → 0\n"
                "- Énergie → 0\n"
                "- TimescaleDB vidée (telemetry, events)"
            ),
        )
    except Exception as exc:
        logger.error(f"Complete reset failed: {exc}")
        raise HTTPException(
            status_code=500,
            detail=f"Erreur lors du reset complet : {str(exc)}",
        ) from exc


# ------------------------------------------------------------------
# Phase 8.5 — Configuration start_time et speed_multiplier
# ------------------------------------------------------------------


@router.get("/config/start_time")
async def get_start_time() -> dict:
    """Retourne la date de départ actuelle (start_time).

    Returns:
        dict avec :
        - start_time_iso: String ISO 8601 (ex: "2005-01-01T00:00:00Z")
        - start_time_unix: Timestamp Unix (secondes)
        - description: Explication du paramètre
    """
    from datetime import datetime
    simulator = deps.get_cluster()
    start_time_iso = simulator._start_time.isoformat().replace("+00:00", "Z")
    start_time_unix = simulator._start_time.timestamp()

    return {
        "start_time_iso": start_time_iso,
        "start_time_unix": start_time_unix,
        "start_time_readable": simulator._start_time.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "description": "Date de départ absolue de la simulation (point zéro pour tous les timestamps)",
    }


@router.put("/config/start_time", response_model=CommandResponse)
async def change_start_time(body: dict = Body(...)) -> CommandResponse:
    """Change la date de départ (start_time) et vide TimescaleDB.

    Le temps écoulé (_t_elapsed_s) persiste ; seule la date de référence change.
    Les tables telemetry et events sont purgées pour repartir de zéro avec la nouvelle date.
    Utile pour ajuster le calendrier de la simulation.

    Args:
        body: {"start_time_iso": "2005-01-01T00:00:00Z"}

    Returns:
        CommandResponse avec confirmation du changement et du reset TimescaleDB
    """
    from simulation.time import parse_start_time

    start_time_iso = body.get("start_time_iso")
    if not start_time_iso:
        raise HTTPException(
            status_code=400,
            detail="Paramètre manquant : 'start_time_iso' dans le body JSON",
        )

    simulator = deps.get_cluster()

    try:
        new_start_time = parse_start_time(start_time_iso)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Format de date invalide : {start_time_iso}. "
            f"Attendu : ISO 8601 (ex: '2005-01-01T00:00:00Z')",
        ) from exc

    old_start_time = simulator._start_time
    simulator._start_time = new_start_time

    logger.info(
        f"Start time changed from {old_start_time.isoformat()} "
        f"to {new_start_time.isoformat()} "
        f"(elapsed time {simulator._t_elapsed_s:.1f}s persists)"
    )

    # Vider TimescaleDB (telemetry et events) pour repartir de zéro
    try:
        await simulator.reset_time_and_energy_with_timescaledb()
        logger.info("TimescaleDB reset automatique après changement de date")
    except Exception as exc:
        logger.error(f"Erreur lors du reset TimescaleDB après changement de date : {exc}")
        raise HTTPException(
            status_code=500,
            detail=f"Changement de date effectué mais reset TimescaleDB échoué : {str(exc)}",
        ) from exc

    return CommandResponse(
        ok=True,
        message=(
            f"Date de départ changée : {old_start_time.strftime('%Y-%m-%d %H:%M:%S UTC')} "
            f"→ {new_start_time.strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
            f"TimescaleDB vidée (telemetry et events) — simulation repartir de zéro avec la nouvelle date."
        ),
    )
