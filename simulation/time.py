"""Gestion du temps simulé pour Jumeaux Chauds.

Ce module fournit des utilitaires pour :
- Convertir un temps écoulé en timestamp absolu simulé
- Parser la date de départ depuis le YAML
- Générer des timestamps ISO pour MQTT/API/snapshots

Convention : tout le temps dans la simulation est relatif à une date de
départ (défaut: datetime.now(UTC) si non configurée) + temps écoulé en secondes.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Optional


def parse_start_time(start_time_str: Optional[str]) -> datetime:
    """Parse une date de départ depuis le YAML.

    Args:
        start_time_str: String ISO 8601 ou None → défaut = datetime.now(UTC)

    Returns:
        datetime (timezone-aware UTC)

    Raises:
        ValueError: Si le format est invalide
    """
    if start_time_str is None:
        # Défaut : maintenant (heure réelle UTC)
        return datetime.now(timezone.utc).replace(microsecond=0)

    try:
        # Parse ISO 8601 (avec ou sans Z)
        if start_time_str.endswith("Z"):
            start_time_str = start_time_str[:-1] + "+00:00"
        dt = datetime.fromisoformat(start_time_str)

        # Forcer UTC si pas de timezone
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        return dt
    except (ValueError, AttributeError) as e:
        raise ValueError(
            f"Invalid start_time format: {start_time_str!r}. "
            f"Expected ISO 8601 (e.g., '2005-01-01T00:00:00Z')"
        ) from e


def get_simulated_time(start_time: datetime, elapsed_s: float) -> datetime:
    """Calcule le temps simulé absolu.

    Args:
        start_time: Date de départ (ex: 2005-01-01)
        elapsed_s: Secondes écoulées depuis le départ

    Returns:
        datetime absolue (timezone-aware UTC)
    """
    return start_time + timedelta(seconds=elapsed_s)


def get_simulated_time_iso(start_time: datetime, elapsed_s: float) -> str:
    """Retourne le timestamp simulé au format ISO 8601 avec Z.

    Args:
        start_time: Date de départ
        elapsed_s: Secondes écoulées

    Returns:
        String ISO 8601 (ex: "2005-01-01T12:34:56.789Z")
    """
    dt = get_simulated_time(start_time, elapsed_s)
    # Format ISO avec milliseconde et Z
    iso_str = dt.isoformat(timespec="milliseconds")
    if not iso_str.endswith("Z"):
        iso_str = iso_str.replace("+00:00", "Z")
    return iso_str


def get_simulated_time_iso_seconds(start_time: datetime, elapsed_s: float) -> str:
    """Retourne le timestamp simulé au format ISO 8601 sans milliseconde.

    Args:
        start_time: Date de départ
        elapsed_s: Secondes écoulées

    Returns:
        String ISO 8601 (ex: "2005-01-01T12:34:56Z")
    """
    dt = get_simulated_time(start_time, elapsed_s)
    # Format ISO sans millisecondes
    iso_str = dt.isoformat(timespec="seconds")
    if not iso_str.endswith("Z"):
        iso_str = iso_str.replace("+00:00", "Z")
    return iso_str
