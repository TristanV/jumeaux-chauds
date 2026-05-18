#!/usr/bin/env python
"""Script de lancement du simulateur Jumeaux Chauds en mode standalone.

Usage:
    python scripts/run_simulator.py [OPTIONS]

Options:
    --scenario   Scenario YAML a charger (nominal|stress|custom)  [default: nominal]
    --cluster    ID du cluster                                      [default: cluster_alpha]
    --duration   Duree de simulation (ex: 1h30m, 90s, 0=infini)   [default: 0]
    --events-per-sec  Nombre d evenements MQTT par machine/sec     [default: 1]
    --no-mqtt    Desactiver la publication MQTT (dry-run)

Exemples:
    python scripts/run_simulator.py
    python scripts/run_simulator.py --scenario stress --duration 30m
    python scripts/run_simulator.py --scenario nominal --cluster cluster_beta --events-per-sec 2
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
import sys
from pathlib import Path

# Ajouter la racine du projet au PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.loader import load_config
from simulation.cluster import ClusterSimulator
from simulation.duration import parse_duration

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("jumeaux-chauds.simulator")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Simulateur de jumeaux numeriques IoT - Jumeaux Chauds",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--scenario",
        default=os.getenv("SCENARIO", "nominal"),
        help="Scenario de simulation (nominal|stress|custom) [default: nominal]",
    )
    parser.add_argument(
        "--cluster",
        default=os.getenv("CLUSTER_ID", "cluster_alpha"),
        help="Identifiant du cluster [default: cluster_alpha]",
    )
    parser.add_argument(
        "--duration",
        default=os.getenv("SIM_DURATION", "0"),
        help="Duree de simulation (1h30m, 90s, 0=infini) [default: 0]",
    )
    parser.add_argument(
        "--events-per-sec",
        type=float,
        default=float(os.getenv("EVENTS_PER_SEC", "1")),
        help="Evenements MQTT publies par machine par seconde [default: 1]",
    )
    parser.add_argument(
        "--no-mqtt",
        action="store_true",
        default=os.getenv("NO_MQTT", "false").lower() == "true",
        help="Desactiver la publication MQTT (mode dry-run)",
    )
    parser.add_argument(
        "--log-level",
        default=os.getenv("LOG_LEVEL", "INFO"),
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Niveau de log [default: INFO]",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()

    # Configurer le niveau de log
    logging.getLogger().setLevel(getattr(logging, args.log_level))

    # Charger la configuration
    logger.info("Chargement de la configuration: scenario=%s, cluster=%s", args.scenario, args.cluster)
    try:
        cfg = load_config(scenario=args.scenario, cluster_id=args.cluster)
    except FileNotFoundError as e:
        logger.error("Fichier de configuration introuvable: %s", e)
        sys.exit(1)
    except Exception as e:
        logger.error("Erreur de configuration: %s", e)
        sys.exit(1)

    # Parser la duree
    duration_s = parse_duration(args.duration)
    if duration_s is None:
        logger.info("Duree: infinie (Ctrl+C pour arreter)")
    else:
        logger.info("Duree: %.0f secondes (%.1f minutes)", duration_s, duration_s / 60)

    logger.info("Events par seconde: %.1f | MQTT: %s", args.events_per_sec, "desactive" if args.no_mqtt else "active")

    # Creer le simulateur
    simulator = ClusterSimulator(
        cfg=cfg,
        cluster_id=args.cluster,
        events_per_sec=args.events_per_sec,
        mqtt_enabled=not args.no_mqtt,
    )

    # Gestion du signal SIGINT (Ctrl+C)
    loop = asyncio.get_event_loop()
    stop_event = asyncio.Event()

    def _signal_handler() -> None:
        logger.info("Signal d arret recu, arret propre en cours...")
        stop_event.set()

    loop.add_signal_handler(signal.SIGINT, _signal_handler)
    loop.add_signal_handler(signal.SIGTERM, _signal_handler)

    # Lancer la simulation
    logger.info("Demarrage du simulateur pour le cluster '%s'...", args.cluster)
    try:
        if duration_s is not None:
            await asyncio.wait_for(
                simulator.run(stop_event=stop_event),
                timeout=duration_s,
            )
        else:
            await simulator.run(stop_event=stop_event)
    except asyncio.TimeoutError:
        logger.info("Duree de simulation atteinte, arret propre.")
    except asyncio.CancelledError:
        logger.info("Simulation annulee.")
    finally:
        snapshot = simulator.get_snapshot()
        logger.info(
            "Simulation terminee | Machines: %d | Energie totale: %.3f kWh | Cout: %.4f EUR",
            len(snapshot.get("machines", {})),
            snapshot.get("metrics", {}).get("total_energy_kwh", 0.0),
            snapshot.get("metrics", {}).get("total_cost_eur", 0.0),
        )


if __name__ == "__main__":
    asyncio.run(main())
