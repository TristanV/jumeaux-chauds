#!/usr/bin/env python3
"""Générateur de corpus ML — Jumeaux Chauds (Phase 8.12B).

Génère rapidement un dataset historique de télémétrie simulée sans passer
par la stack asyncio/MQTT/WebSocket. La boucle synchrone pure permet
d'atteindre ~100 000 ticks/s, soit :
  - 1 jour simulé en ~9 secondes
  - 1 semaine  en ~1 minute
  - 1 mois     en ~4 minutes
  - 1 an       en ~52 minutes

Usage :
    python scripts/generate_dataset.py --scenario stress --duration 30d --output dataset.parquet
    python scripts/generate_dataset.py --scenario nominal --duration 7d --output dataset.csv --format csv
    python scripts/generate_dataset.py --scenario heatwave --duration 24h --output data.parquet --timescaledb

Options :
    --scenario     Scénario YAML (nominal, stress, heatwave, busy_weeks)
    --duration     Durée simulée (ex: 1h, 30d, 1y)
    --output       Chemin du fichier de sortie
    --format       Format de sortie : parquet (défaut) | csv
    --timescaledb  Insérer aussi dans TimescaleDB (profil storage requis)
    --start-time   Date de départ ISO 8601 (défaut: 2005-01-01T00:00:00Z)
    --tick-rate    Ticks par seconde simulée (défaut: 10)
    --no-faults    Désactiver l'injection automatique de pannes
    --batch-log    Afficher la progression toutes les N secondes (défaut: 5)
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

# Garantir que la racine du projet est dans le path
_PROJECT_ROOT = Path(__file__).parent.parent.absolute()
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from config.loader import load_config
from simulation.cluster import ClusterSimulator
from simulation.duration import parse_duration
from simulation.time import get_simulated_time_iso
from omegaconf import OmegaConf


# ── Parsing de la durée ────────────────────────────────────────────────────

def parse_duration_extended(s: str) -> float:
    """Parse une durée : 1h, 30d, 1y, 2w, 1d, etc.

    Étend parse_duration() avec les jours, semaines et années.
    """
    s = s.strip().lower()
    if s.endswith("y"):
        return float(s[:-1]) * 365 * 86400
    if s.endswith("w"):
        return float(s[:-1]) * 7 * 86400
    if s.endswith("d"):
        return float(s[:-1]) * 86400
    # Fallback vers parse_duration (gère 0, 30s, 5m, 1h, 1h30m, etc.)
    return parse_duration(s)


def format_duration(seconds: float) -> str:
    """Formate une durée en chaîne lisible."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    days = int(seconds // 86400)
    rem = seconds % 86400
    hours = int(rem // 3600)
    rem = rem % 3600
    minutes = int(rem // 60)
    secs = rem % 60
    parts = []
    if days:
        parts.append(f"{days}j")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if secs > 0 or not parts:
        parts.append(f"{secs:.0f}s")
    return " ".join(parts)


# ── Boucle de génération synchrone ────────────────────────────────────────

def generate(
    scenario: str,
    duration_s: float,
    tick_rate_hz: float = 10.0,
    start_time_iso: str = "2005-01-01T00:00:00Z",
    disable_faults: bool = False,
    log_interval_s: float = 5.0,
) -> list[dict[str, Any]]:
    """Boucle synchrone pure — génère les snapshots sans asyncio ni MQTT.

    Returns:
        Liste de dicts, un par tick simulé × machine.
    """
    # Charger la config
    cfg = load_config(scenario=scenario)

    # Surcharger start_time et tick_rate
    OmegaConf.update(cfg, "simulation.start_time", start_time_iso)
    OmegaConf.update(cfg, "simulation.tick_rate_hz", tick_rate_hz)
    if disable_faults:
        OmegaConf.update(cfg, "simulation.fault_injection.enabled", False)

    # Créer le simulateur
    sim = ClusterSimulator(config=cfg)

    # Allumer toutes les machines (sauf celles configurées off)
    for machine in sim.machines.values():
        if machine.status == "off":
            machine.power_on()

    dt_sim = 1.0 / tick_rate_hz
    n_ticks = int(duration_s / dt_sim)
    n_machines = len(sim.machines)
    total_rows = n_ticks * n_machines

    print(f"  Scénario       : {scenario}")
    print(f"  Durée simulée  : {format_duration(duration_s)}")
    print(f"  Tick rate      : {tick_rate_hz} Hz (dt={dt_sim}s simulé)")
    print(f"  Ticks totaux   : {n_ticks:,}")
    print(f"  Machines       : {n_machines}")
    print(f"  Lignes prévues : {total_rows:,}")
    print(f"  Date de départ : {start_time_iso}")
    print()

    rows: list[dict[str, Any]] = []
    rows_reserve = total_rows + 1000  # pré-allouer légèrement plus

    t_real_start = time.time()
    t_last_log = t_real_start
    ticks_done = 0

    for _ in range(n_ticks):
        sim._tick()
        ticks_done += 1

        # Snapshot de chaque machine à ce tick
        ts_iso = get_simulated_time_iso(sim._start_time, sim._t_elapsed_s)
        for machine in sim.machines.values():
            snap = machine.snapshot()
            fans = snap.get("fans", [])
            fan_rpm_avg = sum(f["rpm"] for f in fans) / len(fans) if fans else 0.0
            fault_active = len(snap.get("faults", [])) > 0
            fault_types = ",".join(f["type"] for f in snap.get("faults", []))

            rows.append({
                "ts":              ts_iso,
                "cluster_id":      sim.cluster_id,
                "machine_id":      machine.id,
                "role":            machine.role,
                "status":          snap["status"],
                "temperature_c":   snap["temperature_c"],
                "power_w":         snap["power_w"],
                "energy_kwh":      snap["energy_kwh_cumulated"],
                "load_factor":     sim._scenario_engine.get_load_factor(sim._t_elapsed_s),
                "fan_rpm_avg":     fan_rpm_avg,
                "fault_active":    fault_active,
                "fault_types":     fault_types,
            })

        # Log de progression
        now = time.time()
        if now - t_last_log >= log_interval_s:
            elapsed_real = now - t_real_start
            pct = ticks_done / n_ticks * 100
            ticks_per_s = ticks_done / elapsed_real if elapsed_real > 0 else 0
            eta_s = (n_ticks - ticks_done) / ticks_per_s if ticks_per_s > 0 else 0
            sim_time = format_duration(sim._t_elapsed_s)
            print(
                f"  [{pct:5.1f}%] t_sim={sim_time}  "
                f"ticks={ticks_done:,}/{n_ticks:,}  "
                f"vitesse={ticks_per_s:.0f} ticks/s  "
                f"ETA={format_duration(eta_s)}"
            )
            t_last_log = now

    t_real_total = time.time() - t_real_start
    ticks_per_s = n_ticks / t_real_total if t_real_total > 0 else 0
    print(
        f"\n  ✅ Génération terminée en {format_duration(t_real_total)} "
        f"({ticks_per_s:.0f} ticks/s)  |  {len(rows):,} lignes"
    )

    return rows


# ── Export fichier ─────────────────────────────────────────────────────────

def export_file(rows: list[dict], output_path: Path, fmt: str) -> None:
    """Exporte les données en CSV ou Parquet."""
    try:
        import pandas as pd
    except ImportError:
        print("❌ pandas non installé. Installez : pip install pandas pyarrow")
        sys.exit(1)

    print(f"\n📦 Export {fmt.upper()} → {output_path}")
    t0 = time.time()

    df = pd.DataFrame(rows)
    df["ts"] = pd.to_datetime(df["ts"])

    if fmt == "csv":
        df.to_csv(output_path, index=False)
    elif fmt == "parquet":
        try:
            df.to_parquet(output_path, index=False, engine="pyarrow")
        except ImportError:
            print("❌ pyarrow non installé. Installez : pip install pyarrow")
            sys.exit(1)
    else:
        raise ValueError(f"Format inconnu : {fmt}")

    size_mb = output_path.stat().st_size / 1024 / 1024
    elapsed = time.time() - t0
    print(f"  ✅ {len(rows):,} lignes exportées en {elapsed:.1f}s  |  {size_mb:.1f} MB")
    print(f"  Colonnes : {list(df.columns)}")


# ── Insert bulk TimescaleDB ────────────────────────────────────────────────

def insert_timescaledb(rows: list[dict]) -> None:
    """Insert bulk dans TimescaleDB via asyncpg COPY."""
    import asyncio

    try:
        import asyncpg
    except ImportError:
        print("❌ asyncpg non installé. Installez : pip install asyncpg")
        sys.exit(1)

    PG_DSN = (
        f"postgresql://{os.environ.get('POSTGRES_USER', 'jumeaux')}"
        f":{os.environ.get('POSTGRES_PASSWORD', 'jumeaux')}"
        f"@{os.environ.get('POSTGRES_HOST', 'localhost')}"
        f":{os.environ.get('POSTGRES_PORT', '5432')}"
        f"/{os.environ.get('POSTGRES_DB', 'jumeaux')}"
    )

    async def _insert() -> None:
        print(f"\n🗄️  Insert TimescaleDB → {PG_DSN.split('@')[1]}")
        t0 = time.time()

        conn = await asyncpg.connect(PG_DSN)
        try:
            # Préparer les tuples dans l'ordre des colonnes de la table
            records = [
                (
                    datetime.fromisoformat(r["ts"].replace("Z", "+00:00")),
                    r["cluster_id"],
                    r["machine_id"],
                    r["status"],
                    r["temperature_c"],
                    r["power_w"],
                    r["energy_kwh"],
                    r["load_factor"],
                    r["fan_rpm_avg"],
                )
                for r in rows
            ]

            # COPY bulk — beaucoup plus rapide que INSERT ligne par ligne
            await conn.copy_records_to_table(
                "telemetry",
                records=records,
                columns=[
                    "ts", "cluster_id", "machine_id", "status",
                    "temperature_c", "power_w", "energy_kwh",
                    "load_factor", "fan_rpm_avg",
                ],
            )

            elapsed = time.time() - t0
            rate = len(records) / elapsed if elapsed > 0 else 0
            print(f"  ✅ {len(records):,} lignes insérées en {elapsed:.1f}s  ({rate:.0f} lignes/s)")

        finally:
            await conn.close()

    asyncio.run(_insert())


# ── CLI ────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Génère un corpus ML de télémétrie simulée (Jumeaux Chauds Phase 8.12B)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples :
  python scripts/generate_dataset.py --scenario stress --duration 30d --output dataset_30j.parquet
  python scripts/generate_dataset.py --scenario nominal --duration 7d --output data.csv --format csv
  python scripts/generate_dataset.py --scenario heatwave --duration 24h --output data.parquet --timescaledb
  python scripts/generate_dataset.py --scenario busy_weeks --duration 1y --output annee.parquet --tick-rate 5
        """,
    )
    parser.add_argument(
        "--scenario", default="nominal",
        choices=["nominal", "stress", "heatwave", "busy_weeks"],
        help="Scénario de simulation (défaut: nominal)",
    )
    parser.add_argument(
        "--duration", default="1d",
        help="Durée simulée : 1h, 30d, 1w, 1y, etc. (défaut: 1d)",
    )
    parser.add_argument(
        "--output", default="dataset.parquet",
        help="Chemin du fichier de sortie (défaut: dataset.parquet)",
    )
    parser.add_argument(
        "--format", dest="fmt", default="parquet",
        choices=["parquet", "csv"],
        help="Format de sortie (défaut: parquet)",
    )
    parser.add_argument(
        "--timescaledb", action="store_true",
        help="Insérer aussi dans TimescaleDB (POSTGRES_HOST etc. via ENV)",
    )
    parser.add_argument(
        "--start-time", default="2005-01-01T00:00:00Z",
        help="Date de départ ISO 8601 (défaut: 2005-01-01T00:00:00Z)",
    )
    parser.add_argument(
        "--tick-rate", type=float, default=10.0,
        help="Ticks par seconde simulée (défaut: 10, réduire pour accélérer)",
    )
    parser.add_argument(
        "--no-faults", action="store_true",
        help="Désactiver l'injection automatique de pannes",
    )
    parser.add_argument(
        "--batch-log", type=float, default=5.0,
        help="Intervalle de log de progression en secondes (défaut: 5)",
    )

    args = parser.parse_args()

    output_path = Path(args.output)
    duration_s = parse_duration_extended(args.duration)

    print("=" * 60)
    print("🔥 Jumeaux Chauds — Générateur de corpus ML (Phase 8.12B)")
    print("=" * 60)
    print()

    # Génération
    rows = generate(
        scenario=args.scenario,
        duration_s=duration_s,
        tick_rate_hz=args.tick_rate,
        start_time_iso=args.start_time,
        disable_faults=args.no_faults,
        log_interval_s=args.batch_log,
    )

    # Export fichier
    export_file(rows, output_path, args.fmt)

    # Insert TimescaleDB optionnel
    if args.timescaledb:
        insert_timescaledb(rows)

    print("\n🎉 Terminé !")


if __name__ == "__main__":
    main()
