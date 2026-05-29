"""Router /simulation — contrôle du simulateur depuis l'API.

Endpoints (Phase 4.4) :
  POST   /simulation/fault                → injecte une panne sur une machine
  DELETE /simulation/fault/{machine_id}   → annule toutes les pannes d'une machine
  PUT    /simulation/scenario             → change le scénario de charge à chaud

Endpoints (Phase 8.4) :
  GET    /simulation/speed                → infos vitesse de simulation
  PUT    /simulation/speed                → change la vitesse
  POST   /simulation/speed/reset          → réinitialise temps + énergie
"""
from __future__ import annotations

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
    simulator._scenario_engine = ScenarioEngine(profile_cfg=lp_cfg)

    # Mettre à jour le scénario actif dans deps
    deps._scenario_active = cmd.scenario

    logger.info("Scénario changé → '%s'", cmd.scenario)

    return CommandResponse(
        ok=True,
        message=f"Scénario changé vers '{cmd.scenario}' (profil: {lp['type']}).",
    )


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
async def change_speed(
    speed_multiplier: float | None = None,
    speed_name: str | None = None,
) -> CommandResponse:
    """Change la vitesse de simulation à chaud.

    Args:
        speed_multiplier: Multiplier (1.0, 60.0, 3600.0, 86400.0, ou autre)
        speed_name: Nom prédéfini (alternative à multiplier)

    Returns:
        CommandResponse avec confirmation du changement
    """
    simulator = deps.get_cluster()

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
            detail="Fournir 'speed_multiplier' ou 'speed_name'",
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
    """Réinitialise le temps écoulé et l'énergie accumulée.

    Utile après une longue simulation pour recommencer une nouvelle expérience.

    Returns:
        CommandResponse avec confirmation
    """
    simulator = deps.get_cluster()
    simulator.reset_time_and_energy()

    return CommandResponse(
        ok=True,
        message="Temps écoulé et énergie réinitialisés",
    )
