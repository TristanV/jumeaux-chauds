"""Profils de charge et planification des pannes.

Ce module fournit :
- `ScenarioEngine` : génère un facteur de charge en fonction du temps.
- `FaultScheduler` : déclenche des pannes sur les machines selon des distributions.

Bibliothèque de profils (Phase 8.14)
=====================================
Type YAML         | Description
----------------- | -------------------------------------------------------
sine_wave         | Sinusoïde simple — pédagogie, baseline (conservé)
constant          | Charge fixe
step              | Échelon à t_switch_s
ramp_with_spikes  | Rampe + spikes Poisson (conservé)
multi_scale_sine  | 3 sinusoïdes superposées (journalier + hebdo + rapide)
perlin_noise      | Bruit de Perlin multi-octaves (organique, non-répétitif)
markov_chain      | Chaîne de Markov à 4 états (idle/moderate/heavy/burst)
composite_stress  | multi_scale_sine + heatwave drift + spikes — scénario stress réaliste
trace_replay      | Rejoue une trace CSV réelle (Bitbrains ou export generate_dataset.py)
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from .machine import MachineSimulator
from .noise import exponential_event, uniform_event, weibull_event


@dataclass
class LoadProfileConfig:
    """Configuration d'un profil de charge."""

    type: str
    params: dict[str, Any]


# ---------------------------------------------------------------------------
# Bruit de Perlin 1D — implémentation légère sans dépendance externe
# ---------------------------------------------------------------------------

class _Perlin1D:
    """Bruit de Perlin 1D, implémentation pure-numpy (pas de dépendance externe).

    Utilise des vecteurs de gradient aléatoires interpolés en mode smoothstep.
    La graine est fixe pour reproductibilité.
    """

    def __init__(self, seed: int = 42, table_size: int = 256) -> None:
        rng = np.random.default_rng(seed)
        perm = rng.permutation(table_size).astype(np.int32)
        # Table de permutation doublée pour éviter les modulos
        self._perm = np.concatenate([perm, perm])
        self._size = table_size
        # Gradients 1D : +1 ou -1
        self._grad = (rng.integers(0, 2, table_size) * 2 - 1).astype(np.float64)

    def _fade(self, t: float) -> float:
        """Courbe de lissage 5e degré (Ken Perlin 2002)."""
        return t * t * t * (t * (t * 6 - 15) + 10)

    def _lerp(self, a: float, b: float, t: float) -> float:
        return a + t * (b - a)

    def noise(self, x: float) -> float:
        """Retourne une valeur de bruit dans [-1, 1] pour la coordonnée x."""
        xi = int(np.floor(x)) & (self._size - 1)
        xf = x - np.floor(x)
        u = self._fade(xf)
        g0 = self._grad[self._perm[xi]]
        g1 = self._grad[self._perm[xi + 1]]
        n0 = g0 * xf
        n1 = g1 * (xf - 1.0)
        return self._lerp(n0, n1, u)

    def octaves(self, x: float, n_octaves: int = 4, persistence: float = 0.5) -> float:
        """Somme de n_octaves harmoniques (bruit fractal).

        Retourne une valeur approximativement dans [-1, 1].
        """
        total = 0.0
        amplitude = 1.0
        frequency = 1.0
        max_value = 0.0
        for _ in range(n_octaves):
            total += self.noise(x * frequency) * amplitude
            max_value += amplitude
            amplitude *= persistence
            frequency *= 2.0
        return total / max_value if max_value > 0 else 0.0


# Instance globale partagée (initialisée une seule fois, graine fixe)
_PERLIN = _Perlin1D(seed=42)


# ---------------------------------------------------------------------------
# Trace replay — chargeur et interpolateur de traces CSV
# ---------------------------------------------------------------------------

class _TraceReplay:
    """Charge une trace CSV et retourne un load_factor interpolé pour tout t.

    Colonnes CSV attendues (au choix) :
      - timestamp_s + cpu_percent  → load_factor = cpu_percent / 100
      - timestamp_s + load_factor  → utilisé directement

    Paramètres :
      - trace_file   : chemin du fichier CSV (absolu ou relatif à la racine projet)
      - loop         : si True, la trace se répète en boucle (défaut True)
      - speed_factor : étire ou compresse la trace dans le temps (défaut 1.0 = durée réelle)
                       ex: 2.0 → la trace dure 2× plus longtemps dans la simulation

    La valeur est interpolée linéairement entre les deux points de trace encadrant t.
    """

    def __init__(
        self,
        trace_file: str,
        loop: bool = True,
        speed_factor: float = 1.0,
    ) -> None:
        self._loop = loop
        self._speed_factor = max(0.001, float(speed_factor))

        # Résolution du chemin : absolu ou relatif à la racine du projet
        path = Path(trace_file)
        if not path.is_absolute():
            # Chercher depuis la racine du projet (2 niveaux au-dessus de simulation/)
            project_root = Path(__file__).parent.parent
            path = project_root / trace_file

        if not path.exists():
            raise FileNotFoundError(
                f"Fichier de trace introuvable : {path}\n"
                f"  (chemin fourni : {trace_file})\n"
                f"  Les traces sont dans data/traces/. "
                f"Lancez scripts/download_traces.py pour télécharger Bitbrains."
            )

        self._timestamps: list[float] = []
        self._loads: list[float] = []
        self._load_csv(path)

        if len(self._timestamps) < 2:
            raise ValueError(f"La trace {trace_file} contient moins de 2 points — invalide.")

        self._duration = self._timestamps[-1] - self._timestamps[0]

    def _load_csv(self, path: Path) -> None:
        """Charge le CSV et détecte la colonne de charge."""
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames or []

            # Détecter la colonne de charge
            if "load_factor" in fieldnames:
                load_col = "load_factor"
                scale = 1.0
            elif "cpu_percent" in fieldnames:
                load_col = "cpu_percent"
                scale = 0.01  # ÷100 pour normaliser
            else:
                raise ValueError(
                    f"Le CSV {path.name} doit contenir 'load_factor' ou 'cpu_percent'. "
                    f"Colonnes trouvées : {fieldnames}"
                )

            if "timestamp_s" not in fieldnames:
                raise ValueError(
                    f"Le CSV {path.name} doit contenir 'timestamp_s'. "
                    f"Colonnes trouvées : {fieldnames}"
                )

            for row in reader:
                try:
                    ts = float(row["timestamp_s"])
                    load = float(row[load_col]) * scale
                    self._timestamps.append(ts)
                    self._loads.append(float(np.clip(load, 0.0, 1.0)))
                except (ValueError, KeyError):
                    continue  # Ignorer les lignes malformées

    def get(self, t_elapsed_s: float) -> float:
        """Retourne le load_factor interpolé pour t_elapsed_s.

        Si loop=True, la trace se répète après sa durée totale.
        Si loop=False, reste sur la dernière valeur après la fin.

        speed_factor > 1 → la trace dure plus longtemps (lecture ralentie)
        speed_factor < 1 → la trace dure moins longtemps (lecture accélérée)
        """
        # Diviser par speed_factor : à t_sim=300 avec speed_factor=2.0,
        # on est à t_trace=150 (la trace avance 2× plus lentement)
        t_trace = t_elapsed_s / self._speed_factor

        t_origin = self._timestamps[0]

        if self._loop and self._duration > 0:
            # Modulo sur le temps relatif à l'origine
            t_rel = t_trace - t_origin
            t_mod = t_rel % self._duration
            # Si t_mod == 0 et on n'est pas au tout début, on est exactement
            # à la fin d'un cycle → pointer sur le dernier point de la trace
            if t_mod == 0.0 and t_rel > 0.0:
                t = self._timestamps[-1]
            else:
                t = t_origin + t_mod
        else:
            t = min(t_trace, self._timestamps[-1])

        # Interpolation linéaire
        idx = np.searchsorted(self._timestamps, t, side="right") - 1
        idx = int(np.clip(idx, 0, len(self._timestamps) - 2))

        t0 = self._timestamps[idx]
        t1 = self._timestamps[idx + 1]
        v0 = self._loads[idx]
        v1 = self._loads[idx + 1]

        if t1 == t0:
            return float(v0)

        alpha = (t - t0) / (t1 - t0)
        return float(np.clip(v0 + alpha * (v1 - v0), 0.0, 1.0))

    @property
    def n_points(self) -> int:
        return len(self._timestamps)

    @property
    def duration_s(self) -> float:
        return self._duration


# ---------------------------------------------------------------------------
# Moteur de scénarios
# ---------------------------------------------------------------------------

class ScenarioEngine:
    """Moteur de scénarios de charge.

    Les paramètres proviennent du YAML (`config/scenarios/*.yaml`).
    """

    def __init__(self, profile_cfg: LoadProfileConfig) -> None:
        self.profile_cfg = profile_cfg
        # État interne pour les profils avec mémoire (Markov)
        self._markov_state: int = 1       # état courant (0=idle, 1=moderate, 2=heavy, 3=burst)
        self._markov_next_change: float = 0.0  # prochain changement d'état (en t_elapsed_s)
        # Trace replay : chargée paresseusement à la première utilisation
        self._trace: _TraceReplay | None = None

    def get_load_factor(self, t_elapsed_s: float) -> float:
        """Retourne un facteur de charge dans [0, 1] pour un temps donné."""

        t = max(0.0, float(t_elapsed_s))
        ptype = self.profile_cfg.type
        params = self.profile_cfg.params

        # ── Profils historiques (conservés intacts) ─────────────────────
        if ptype == "sine_wave":
            return self._sine_wave(t, **params)
        if ptype == "ramp_with_spikes":
            return self._ramp_with_spikes(t, **params)
        if ptype == "constant":
            return float(np.clip(params.get("value", 0.0), 0.0, 1.0))
        if ptype == "step":
            return self._step(t, **params)

        # ── Nouveaux profils Phase 8.14A ─────────────────────────────────
        if ptype == "multi_scale_sine":
            return self._multi_scale_sine(t, **params)
        if ptype == "perlin_noise":
            return self._perlin_noise(t, **params)
        if ptype == "markov_chain":
            return self._markov_chain(t, **params)
        if ptype == "composite_stress":
            return self._composite_stress(t, **params)

        # ── Phase 8.14B : trace replay ───────────────────────────────────
        if ptype == "trace_replay":
            return self._trace_replay(t, **params)

        # Profil inconnu → charge nulle (comportement sûr)
        return 0.0

    # ------------------------------------------------------------------
    # Profils historiques (inchangés)
    # ------------------------------------------------------------------

    @staticmethod
    def _sine_wave(
        t: float,
        base_load: float,
        amplitude: float,
        period_s: float,
    ) -> float:
        """Sinusoïde pure. Pédagogique, reproductible."""
        if period_s <= 0:
            return float(np.clip(base_load, 0.0, 1.0))
        omega = 2.0 * np.pi / period_s
        value = base_load + amplitude * np.sin(omega * t)
        return float(np.clip(value, 0.0, 1.0))

    @staticmethod
    def _ramp_with_spikes(
        t: float,
        ramp_start: float = 0.20,
        ramp_end: float = 0.95,
        ramp_duration_s: float = 600.0,
        spike_probability: float = 0.02,
        spike_duration_s: float = 30.0,
        spike_magnitude: float = 0.30,
        # alias legacy (anciens noms internes — ignorés silencieusement)
        ramp_start_s: float | None = None,
        ramp_end_s: float | None = None,
        spike_rate_hz: float | None = None,
        base_load: float | None = None,
        max_load: float | None = None,
    ) -> float:
        """Rampe linéaire + spikes Poisson stochastiques."""
        if ramp_duration_s <= 0:
            load = ramp_end
        elif t >= ramp_duration_s:
            load = ramp_end
        else:
            alpha = t / ramp_duration_s
            load = ramp_start + alpha * (ramp_end - ramp_start)

        if spike_probability > 0 and np.random.random() < spike_probability:
            load += spike_magnitude

        return float(np.clip(load, 0.0, 1.0))

    @staticmethod
    def _step(
        t: float,
        t_switch_s: float,
        low_load: float = 0.1,
        high_load: float = 0.9,
    ) -> float:
        if t < t_switch_s:
            return float(np.clip(low_load, 0.0, 1.0))
        return float(np.clip(high_load, 0.0, 1.0))

    # ------------------------------------------------------------------
    # Phase 8.14 — Nouveaux profils
    # ------------------------------------------------------------------

    @staticmethod
    def _multi_scale_sine(
        t: float,
        base_load: float = 0.35,
        # Cycle rapide (ex: rush matinal dans la journée simulée)
        fast_amplitude: float = 0.12,
        fast_period_s: float = 3600.0,        # 1h simulée
        fast_phase_s: float = -900.0,          # pic à 15 min après le début
        # Cycle journalier (pic en milieu de journée)
        daily_amplitude: float = 0.18,
        daily_period_s: float = 86400.0,       # 24h simulées
        daily_phase_s: float = -21600.0,       # pic à 6h (midi si départ 6h)
        # Cycle hebdomadaire (weekend vs semaine)
        weekly_amplitude: float = 0.08,
        weekly_period_s: float = 604800.0,     # 7 jours simulés
        weekly_phase_s: float = 0.0,
        # Bruit gaussien résiduel
        noise_std: float = 0.03,
    ) -> float:
        """Superposition de 3 sinusoïdes à périodes distinctes + bruit résiduel.

        Reproduit la structure multi-échelle d'un vrai datacenter d'entreprise :
        - Cycle rapide  : fluctuations intra-horaires (crons, batch courts)
        - Cycle journalier : pic de milieu de journée
        - Cycle hebdomadaire : weekend calme vs semaine chargée

        Aucune répétition apparente à courte échelle (les 3 périodes sont
        incommensurables si on laisse les valeurs par défaut).
        """
        fast   = fast_amplitude   * np.sin(2*np.pi*(t + fast_phase_s)   / fast_period_s)
        daily  = daily_amplitude  * np.sin(2*np.pi*(t + daily_phase_s)  / daily_period_s)
        weekly = weekly_amplitude * np.sin(2*np.pi*(t + weekly_phase_s) / weekly_period_s)
        noise  = np.random.normal(0.0, noise_std) if noise_std > 0 else 0.0
        return float(np.clip(base_load + fast + daily + weekly + noise, 0.0, 1.0))

    @staticmethod
    def _perlin_noise(
        t: float,
        base_load: float = 0.45,
        amplitude: float = 0.35,
        scale: float = 0.0001,       # fréquence spatiale (plus petit = plus lent)
        n_octaves: int = 4,          # nombre d'harmoniques
        persistence: float = 0.5,    # poids de chaque harmonique
        # Dérive lente optionnelle (simule tendance longue durée)
        drift_rate: float = 0.0,     # charge ajoutée par seconde
        drift_max: float = 0.0,      # plafond de la dérive (0 = sans limite)
    ) -> float:
        """Bruit de Perlin 1D multi-octaves.

        Produit une charge continue, lisse, non-périodique et visuellement
        organique — idéal pour simuler un cluster sans pattern évident,
        ce qui rend la détection d'anomalies non-triviale.

        Paramètres :
        - scale : fréquence temporelle. 0.0001 → variation sur ~10 000 s.
                  0.001 → variation sur ~1 000 s. À ajuster selon speed_multiplier.
        - n_octaves : 1 = très lisse, 6 = très texturé.
        - drift_rate : dérive additionnelle (positif = charge croissante).
        """
        raw = _PERLIN.octaves(t * scale, n_octaves=n_octaves, persistence=persistence)
        load = base_load + amplitude * raw

        if drift_rate > 0:
            drift = drift_rate * t
            if drift_max > 0:
                drift = min(drift, drift_max)
            load += drift

        return float(np.clip(load, 0.0, 1.0))

    def _markov_chain(
        self,
        t: float,
        # Valeurs de charge par état
        state_loads: list[float] | None = None,
        # Matrice de transition (lignes = état courant, colonnes = état suivant)
        transition_matrix: list[list[float]] | None = None,
        # Durée moyenne dans chaque état (en secondes simulées)
        mean_dwell_s: float = 300.0,
        # Bruit gaussien ajouté à la valeur d'état
        noise_std: float = 0.04,
    ) -> float:
        """Chaîne de Markov à 4 états : idle / moderate / heavy / burst.

        La simulation saute d'état en état selon une matrice de transition
        stochastique, avec une durée d'occupation distribuée exponentiellement.

        États :
            0 = idle    (~15% charge)
            1 = moderate (~45% charge)
            2 = heavy    (~72% charge)
            3 = burst    (~95% charge)

        La matrice de transition par défaut favorise les transitions vers les
        états adjacents (comportement réaliste : la charge monte/descend
        progressivement plutôt que de sauter de idle à burst directement).

        Valeur pédagogique : introduit les processus stochastiques à mémoire.
        Bon sujet de TP sur les modèles HMM (Hidden Markov Models).
        """
        if state_loads is None:
            state_loads = [0.15, 0.45, 0.72, 0.95]

        if transition_matrix is None:
            # Matrice calibrée : transitions préférentiellement vers états adjacents
            transition_matrix = [
                [0.85, 0.12, 0.03, 0.00],  # depuis idle
                [0.08, 0.76, 0.14, 0.02],  # depuis moderate
                [0.02, 0.18, 0.70, 0.10],  # depuis heavy
                [0.01, 0.05, 0.24, 0.70],  # depuis burst
            ]

        # Changement d'état si le timer est écoulé
        if t >= self._markov_next_change:
            row = transition_matrix[self._markov_state]
            self._markov_state = int(np.random.choice(len(row), p=row))
            # Durée exponentielle dans le nouvel état
            dwell = np.random.exponential(mean_dwell_s)
            self._markov_next_change = t + max(1.0, dwell)

        load = state_loads[self._markov_state]
        if noise_std > 0:
            load += np.random.normal(0.0, noise_std)
        return float(np.clip(load, 0.0, 1.0))

    @staticmethod
    def _composite_stress(
        t: float,
        # Base multi-échelle (cycle journalier + hebdo)
        base_load: float = 0.45,
        daily_amplitude: float = 0.20,
        daily_period_s: float = 86400.0,
        daily_phase_s: float = -21600.0,
        weekly_amplitude: float = 0.10,
        weekly_period_s: float = 604800.0,
        # Dérive thermique progressive (simule montée en charge sur la durée)
        drift_rate: float = 2e-5,          # +0.02 par 1000s (ex: surchauffe progressive)
        drift_max: float = 0.25,           # plafond de dérive
        # Spikes de charge (incidents, batch jobs, DDOS…)
        spike_probability: float = 0.005,  # par tick (~0.5% de chance)
        spike_magnitude: float = 0.25,
        # Bruit perlin superposé (texture fine)
        perlin_scale: float = 0.0003,
        perlin_amplitude: float = 0.08,
        perlin_octaves: int = 3,
    ) -> float:
        """Profil composite haute fidélité pour le scénario stress.

        Combine :
        1. Cycles multi-échelle (journalier + hebdomadaire)
        2. Dérive thermique progressive bornée (charge croissante)
        3. Spikes stochastiques (incidents de production)
        4. Texture fine par bruit de Perlin (variabilité instantanée)

        Ce profil cumulatif force le système à gérer simultanément :
        - Une charge de fond élevée et croissante
        - Des pics imprévisibles
        - Une variabilité fine qui rend les seuils d'alerte non-triviaux

        Cas d'usage pédagogique : tester les algorithmes de maintenance
        prédictive face à un signal multi-composantes réaliste.
        """
        # Composante 1 : cycles temporels
        daily  = daily_amplitude  * np.sin(2*np.pi*(t + daily_phase_s)  / daily_period_s)
        weekly = weekly_amplitude * np.sin(2*np.pi * t / weekly_period_s)
        cyclic = base_load + daily + weekly

        # Composante 2 : dérive progressive bornée
        drift = min(drift_rate * t, drift_max)

        # Composante 3 : spike stochastique
        spike = spike_magnitude if np.random.random() < spike_probability else 0.0

        # Composante 4 : texture Perlin fine
        perlin_raw = _PERLIN.octaves(t * perlin_scale, n_octaves=perlin_octaves)
        texture = perlin_amplitude * perlin_raw

        return float(np.clip(cyclic + drift + spike + texture, 0.0, 1.0))

    def _trace_replay(
        self,
        t: float,
        trace_file: str = "data/traces/bitbrains_week_vm00.csv",
        loop: bool = True,
        speed_factor: float = 1.0,
    ) -> float:
        """Rejoue une trace CSV réelle comme profil de charge.

        Paramètres YAML :
          trace_file   : chemin du CSV (relatif à la racine du projet ou absolu)
          loop         : si True, la trace se répète en boucle (défaut : True)
          speed_factor : compression/dilatation temporelle de la trace (défaut : 1.0)
                         ex: 0.5 → la trace est jouée 2× plus vite

        Colonnes CSV supportées :
          - timestamp_s + cpu_percent  → normalisé ÷ 100
          - timestamp_s + load_factor  → utilisé directement

        Cas d'usage pédagogiques :
          1. Rejouer le dataset Bitbrains FastStorage pour un réalisme maximal
          2. Rejouer une simulation Jumeaux Chauds exportée par generate_dataset.py
          3. Comparer différentes traces sur le même modèle physique

        La trace est chargée paresseusement (premier appel) et mise en cache
        pour toute la durée de la simulation.
        """
        # Chargement paresseux et mise en cache
        if self._trace is None:
            self._trace = _TraceReplay(
                trace_file=trace_file,
                loop=loop,
                speed_factor=speed_factor,
            )
        return self._trace.get(t)


# ---------------------------------------------------------------------------
# FaultConfig & FaultScheduler (inchangés)
# ---------------------------------------------------------------------------

@dataclass
class FaultConfig:
    """Configuration d'un type de panne."""

    type: str
    distribution: str
    shape: float | None = None
    scale_s: float | None = None
    probability_per_tick: float | None = None
    magnitude: float = 1.0


class FaultScheduler:
    """Planificateur de pannes pour un cluster de machines.

    Il est paramétré par une liste de `FaultConfig` issue du YAML.
    """

    def __init__(
        self,
        fault_configs: list[FaultConfig],
        recovery_delay_s: float,
    ) -> None:
        self._fault_configs = fault_configs
        self._recovery_delay_s = recovery_delay_s
        self._elapsed_by_machine: dict[str, float] = {}

    def tick(self, machines: dict[str, MachineSimulator], dt: float) -> None:
        """Evalue les déclenchements potentiels de pannes."""

        if dt <= 0:
            return

        for machine_id, machine in machines.items():
            elapsed = self._elapsed_by_machine.get(machine_id, 0.0)
            elapsed += dt
            self._elapsed_by_machine[machine_id] = elapsed

            for cfg in self._fault_configs:
                if cfg.distribution == "weibull":
                    if cfg.shape is None or cfg.scale_s is None:
                        continue
                    fired = weibull_event(
                        shape=cfg.shape,
                        scale_s=cfg.scale_s,
                        elapsed_s=elapsed,
                        dt=dt,
                    )
                elif cfg.distribution == "exponential":
                    if cfg.scale_s is None:
                        continue
                    fired = exponential_event(scale_s=cfg.scale_s, dt=dt)
                elif cfg.distribution == "uniform":
                    if cfg.probability_per_tick is None:
                        continue
                    fired = uniform_event(cfg.probability_per_tick)
                else:
                    fired = False

                if fired:
                    machine.inject_fault(
                        fault_type=cfg.type,
                        duration_s=self._recovery_delay_s,
                        magnitude=cfg.magnitude,
                    )
