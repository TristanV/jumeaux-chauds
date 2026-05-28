"""Fonctions pures du modèle physique thermique.

Toutes les fonctions sont sans effets de bord et déterministes.
Elles constituent le noyau mathématique du simulateur.

Modèle thermique du 1er ordre (lumped-parameter) :

    P_elec(t) = P_idle + (P_max - P_idle) * L(t)^alpha
    Q_in(t)   = P_elec(t) * heat_ratio
    tau(t)    = tau_max / (1 + k_cool * mean_fan_rpm / 1000)
    T(t+dt)   = T(t) + dt * [Q_in(t)/C_th - (T(t)-T_amb)/tau(t)]
"""
from __future__ import annotations


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
        alpha:       Exposant de non-linéarité (≥ 1).

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
) -> float:
    """Calcule la constante de temps thermique dynamique.

    tau(t) = tau_max / (1 + k_cool * fan_rpm_mean / 1000)

    Plus les fans tournent vite, plus tau est petit (refroidissement rapide).

    Args:
        tau_max:      Constante de temps maximale (fans arrêtés), en secondes.
        fan_rpm_mean: Vitesse moyenne des fans (RPM).
        k_cool:       Facteur de contribution des fans au refroidissement.

    Returns:
        Constante de temps effective en secondes (> 0).
    """
    denominator = 1.0 + k_cool * (fan_rpm_mean / 1000.0)
    return tau_max / max(denominator, 1e-6)


def compute_thermal_step(
    t_current: float,
    q_in: float,
    tau: float,
    c_th: float,
    t_amb: float,
    dt: float,
) -> float:
    """Intègre l'équation thermique du 1er ordre (méthode d'Euler explicite).

    T(t+dt) = T(t) + dt * [Q_in/C_th - (T(t) - T_amb) / tau]

    Args:
        t_current: Température interne actuelle (°C).
        q_in:      Puissance thermique injectée (W).
        tau:       Constante de temps thermique effective (s).
        c_th:      Capacité thermique (J/°C).
        t_amb:     Température ambiante (°C).
        dt:        Pas de temps (s).

    Returns:
        Nouvelle température interne (°C).
    """
    dT = dt * (q_in / c_th - (t_current - t_amb) / tau)
    return t_current + dT


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

    Modèle cubique : P_fan(rpm) = P_nominal × (rpm / rpm_max)³

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
    fan_power_w_by_rpm: list[float] | None = None,
    fan_power_w: float | None = None,
    tick_rate_hz: float = 10.0,
) -> float:
    """Calcule l'incrément d'énergie consommée pendant un tick.

    Support de deux modes :
    - Mode simple (rétro-compatible) : E = (P_machine + n_fans * P_fan_constant) / tick_rate
    - Mode avancé : E = (P_machine + sum(P_fan(rpm_i))) / tick_rate

    Args:
        power_w:              Puissance électrique de la machine (W).
        fan_count:            Nombre de fans (ignoré si fan_power_w_by_rpm fourni).
        fan_power_w_by_rpm:   Liste des puissances par fan calculées (W). Si fourni,
                              fan_power_w est ignoré.
        fan_power_w:          Puissance constante par fan pour le mode simple (W).
                              Ignoré si fan_power_w_by_rpm est fourni.
        tick_rate_hz:         Fréquence de simulation (Hz).

    Returns:
        Énergie incrémentale en kWh.
    """
    if fan_power_w_by_rpm is not None:
        # Mode avancé : puissance réelle par RPM
        total_w = power_w + sum(fan_power_w_by_rpm)
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
        pue:           Power Usage Effectiveness (≥ 1.0).
        price_eur_kwh: Tarif électrique (€/kWh).

    Returns:
        Coût en euros.
    """
    return energy_kwh * pue * price_eur_kwh
