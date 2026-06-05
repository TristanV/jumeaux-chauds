"""Fonctions pures du modèle physique thermique.

Toutes les fonctions sont sans effets de bord et déterministes.
Elles constituent le noyau mathématique du simulateur.

Modèle thermique du 1er ordre (lumped-parameter) — Phase 8.7 Refined :

    P_elec(t) = P_idle + (P_max - P_idle) * L(t)^alpha
    Q_in(t)   = P_elec(t) * heat_ratio
    tau(t)    = tau_max / (1 + k_cool * (mean_fan_rpm / RPM_max)^1.5)  <- Phase 8.7: exposant 1.5 (réaliste)
    T(t+dt)   = T(t) + dt * [Q_in(t)/C_th - (T(t)-T_amb)/tau(t)]
    T clamped  = clamp(T, T_amb, T_max)  <- Phase 8.7: limites physiques

Améliorations Phase 8.7 :
- Formule tau améliorée avec exposant 1.5 (échange thermique convectif réaliste)
- Clamp de température à [T_amb, T_max] (jamais négatif, jamais dépassé)
- Sous-pas d'intégration pour stabilité numérique (speed_multiplier élevé)
"""
from __future__ import annotations

import math


def compute_load_power(
    load_factor: float,
    idle_w: float,
    max_w: float,
    alpha: float = 1.5,
) -> float:
    """Calcule la puissance électrique consommée en fonction de la charge.

    P = P_idle + (P_max - P_idle) * load_factor^alpha

    Args:
        load_factor: Facteur de charge dans [0, 1].
        idle_w:      Puissance au repos (W).
        max_w:       Puissance maximale (W).
        alpha:       Exposant de non-linéarité (>= 1).

    Returns:
        Puissance instantanée en watts.
    """
    load_factor = max(0.0, min(1.0, load_factor))
    return idle_w + (max_w - idle_w) * (load_factor ** alpha)


def compute_heat_input(power_w: float, heat_ratio: float) -> float:
    """Calcule la chaleur produite par la machine.

    Q_in = P_elec * heat_ratio

    Args:
        power_w:    Puissance électrique consommée (W).
        heat_ratio: Fraction de la puissance convertie en chaleur [0, 1].

    Returns:
        Puissance thermique dissipée (W).
    """
    return power_w * heat_ratio


def compute_tau(
    tau_max: float,
    fan_rpm_mean: float,
    k_cool: float,
    fan_max_rpm: int = 5000,
) -> float:
    """Calcule la constante de temps thermique dynamique (Phase 8.7 Refined).

    Phase 8.7 Amélioration : formule réaliste avec exposant 1.5

    tau(RPM) = tau_max / (1 + k_cool * (RPM / RPM_max)^1.5)

    Justification physique :
    - Puissance aérodynamique prop RPM^3 (loi du cube du ventilateur)
    - Échange thermique convectif prop (débit air)^0.6 (corrélation Colburn)
    - Combinaison : refroidissement effectif prop RPM^1.5 (plus réaliste que linéaire)

    Comportement:
    - À RPM=0: tau = tau_max (refroidissement passif uniquement)
    - À RPM=RPM_max: tau = tau_max / (1 + k_cool) ~= tau_max/3 (refroidissement 3x plus rapide)

    Args:
        tau_max:      Constante de temps maximale (fans arrêtés), en secondes.
        fan_rpm_mean: Vitesse moyenne des fans (RPM).
        k_cool:       Facteur de contribution des fans au refroidissement (typiquement 2.0).
        fan_max_rpm:  RPM maximum du ventilateur (default=5000).

    Returns:
        Constante de temps effective en secondes (> 0).
    """
    # Calculer le ratio RPM/RPM_max pour la formule adimensionnelle
    rpm_ratio = fan_rpm_mean / max(fan_max_rpm, 1)

    # Phase 8.7: Exposant 1.5 pour refroidissement réaliste
    # (ancien: linéaire, nouveau: non-linéaire comme aérodynamique réelle)
    multiplier = 1.0 + k_cool * (rpm_ratio ** 1.5)

    return tau_max / max(multiplier, 1e-6)


# Constantes physiques globales (Phase 8.7)
T_MIN_C = 0.0              # Température minimum (jamais < T_amb)
T_MAX_C = 100.0            # Température maximum (arrêt thermique)
DT_INTEGRATION_MAX_S = 0.1  # Pas d'intégration max pour stabilité numérique


def compute_thermal_step(
    t_current: float,
    q_in: float,
    tau: float,
    c_th: float,
    t_amb: float,
    dt: float,
    dt_max: float = DT_INTEGRATION_MAX_S,
) -> float:
    """Intègre l'équation thermique du 1er ordre avec sous-pas et clamp (Phase 8.7 Refined).

    Phase 8.7 Améliorations :
    1. Sous-pas d'intégration : si dt > dt_max, subdiviser pour stabilité numérique
    2. Clamp de température : jamais T < T_amb (physiquement impossible)
       et jamais T > T_max (arrêt thermique garantit)

    Équation différentielle (1er ordre, lumped-parameter):
        dT/dt = [Q_in/C_th - (T - T_amb) / tau]

    Intégration numérique (Euler explicite avec sous-pas) :
        T(t+dt) = T(t) + dt_sub * [Q_in/C_th - (T(t) - T_amb) / tau]
        (répété pour chaque sous-pas si dt > dt_max)

    Stabilité (critère de Courant) :
        dt < 2 * tau_min ~= 2 * 0.5s = 1s (avec tau_min ~= 0.5s à RPM max)
        En pratique, dt_max = 0.1s donne 10x de sécurité

    Args:
        t_current: Température interne actuelle (°C).
        q_in:      Puissance thermique injectée (W).
        tau:       Constante de temps thermique effective (s).
        c_th:      Capacité thermique (J/°C).
        t_amb:     Température ambiante (°C).
        dt:        Pas de temps à intégrer (s).
        dt_max:    Pas d'intégration maximum pour stabilité (default=0.1s).

    Returns:
        Nouvelle température interne (°C), clampée à [T_amb, T_max].
    """
    # Phase 8.7: Nombre de sous-pas pour stabilité numérique
    # Si dt = 1.0s et dt_max = 0.1s, subdiviser en 10 sous-pas de 0.1s
    num_substeps = max(1, math.ceil(dt / dt_max))
    dt_substep = dt / num_substeps

    # Intégrer par sous-pas
    t = t_current
    for _ in range(num_substeps):
        # Équation du 1er ordre : dT/dt = [apport_chaleur - évacuation_chaleur]
        dT = dt_substep * (q_in / c_th - (t - t_amb) / tau)
        t = t + dT

    # Phase 8.7: Clamp de température aux limites réalistes
    # - Jamais < T_amb (température ambiante est limite physique)
    # - Jamais > T_max (arrêt thermique + clamp de sécurité)
    t = max(t_amb, min(t, T_MAX_C))

    return t


def compute_fan_auto_speed(
    t_current: float,
    t_amb: float,
    gain_rpm_per_c: float,
    f_max: int,
) -> int:
    """Calcule la consigne automatique des fans (régulateur proportionnel).

    f_auto = clip(gain * max(0, T - T_amb), 0, f_max)

    Args:
        t_current:     Température interne actuelle (°C).
        t_amb:         Température ambiante (°C).
        gain_rpm_per_c: Gain proportionnel (RPM/°C).
        f_max:         Vitesse maximale des fans (RPM).

    Returns:
        Consigne de vitesse (RPM), entier dans [0, f_max].
    """
    raw = gain_rpm_per_c * max(0.0, t_current - t_amb)
    return int(max(0, min(f_max, raw)))


def compute_fan_power_rpm(
    rpm: int,
    fan_power_w_nominal: float,
    fan_max_rpm: int,
) -> float:
    """Calcule la puissance consommée par un ventilateur en fonction du RPM.

    Modèle cubique : P_fan(rpm) = P_nominal * (rpm / rpm_max)^3

    Justification physique : la puissance aérodynamique augmente avec le cube
    de la vitesse (loi du cube du ventilateur).

    Args:
        rpm:                   Vitesse instantanée (RPM).
        fan_power_w_nominal:   Puissance à RPM max (W).
        fan_max_rpm:           RPM maximal du ventilateur.

    Returns:
        Puissance consommée par ce ventilateur (W).
    """
    if fan_max_rpm <= 0 or rpm <= 0:
        return 0.0
    ratio = float(rpm) / float(fan_max_rpm)
    return fan_power_w_nominal * (ratio ** 3)


def compute_energy_kwh(
    power_w: float,
    fan_count: int,
    fan_power_w_by_rpm: list[float] | float | None = None,
    fan_power_w: float | None = None,
    tick_rate_hz: float = 10.0,
) -> float:
    """Calcule l'incrément d'énergie consommée pendant un tick.

    Support de deux modes :
    - Mode simple (rétro-compatible) : E = (P_machine + n_fans * P_fan_constant) / tick_rate
    - Mode avancé : E = (P_machine + sum(P_fan(rpm_i))) / tick_rate

    Bug #10 Fix : Gérer les deux cas pour fan_power_w_by_rpm (list ou float)

    Args:
        power_w:              Puissance électrique de la machine (W).
        fan_count:            Nombre de fans (ignoré si fan_power_w_by_rpm fourni comme list).
        fan_power_w_by_rpm:   Liste des puissances par fan calculées (W), ou float legacy.
                              Si list, utilise mode avancé. Si float, interprète comme fan_power_w.
        fan_power_w:          Puissance constante par fan pour le mode simple (W).
                              Ignoré si fan_power_w_by_rpm est fourni comme list.
        tick_rate_hz:         Fréquence de simulation (Hz).

    Returns:
        Énergie incrémentale en kWh.
    """
    if fan_power_w_by_rpm is not None:
        if isinstance(fan_power_w_by_rpm, list):
            # Mode avancé : puissance réelle par RPM
            total_w = power_w + sum(fan_power_w_by_rpm)
        else:
            # Mode legacy : float reçu au lieu de list
            # Interprète comme puissance constante par fan
            total_w = power_w + fan_count * float(fan_power_w_by_rpm)
    else:
        # Mode simple (rétro-compatible)
        fan_power_w = fan_power_w or 0.0
        total_w = power_w + fan_count * fan_power_w

    dt = 1.0 / tick_rate_hz
    return total_w * dt / 3_600_000.0


def compute_cost(
    energy_kwh: float,
    pue: float,
    price_eur_kwh: float,
) -> float:
    """Calcule le coût électrique total avec PUE.

    C = E_IT * PUE * prix_kWh

    Args:
        energy_kwh:    Énergie IT cumulée (kWh).
        pue:           Power Usage Effectiveness (>= 1.0).
        price_eur_kwh: Tarif électrique (€/kWh).

    Returns:
        Coût en euros.
    """
    return energy_kwh * pue * price_eur_kwh
