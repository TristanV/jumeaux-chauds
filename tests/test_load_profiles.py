"""Tests des profils de charge Phase 8.14.

Valide les 4 nouveaux profils (8.14A) + trace_replay (8.14B) :
  - multi_scale_sine  : superposition de 3 sinusoïdes
  - perlin_noise      : bruit de Perlin multi-octaves
  - markov_chain      : chaîne de Markov 4 états
  - composite_stress  : profil composite haute fidélité
  - trace_replay      : rejeu de trace CSV (8.14B)

Propriétés testées :
  1. Sortie dans [0, 1] pour tout t
  2. Variation effective (pas de signal constant)
  3. Reproductibilité (même seed → même trajectoire Perlin)
  4. Markov : transitions entre états valides
  5. composite_stress : dérive monotone sur la composante drift
  6. Rétrocompatibilité : sine_wave et ramp_with_spikes inchangés
  7. trace_replay : chargement CSV, interpolation, loop, normalisation
"""
from __future__ import annotations

import csv
import tempfile
from pathlib import Path

import numpy as np
import pytest

from simulation.scenarios import LoadProfileConfig, ScenarioEngine, _Perlin1D, _TraceReplay


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_engine(ptype: str, **params) -> ScenarioEngine:
    return ScenarioEngine(LoadProfileConfig(type=ptype, params=params))


def sample_loads(engine: ScenarioEngine, n: int = 500, dt: float = 10.0) -> list[float]:
    """Échantillonne n valeurs avec un pas dt secondes."""
    return [engine.get_load_factor(i * dt) for i in range(n)]


# ---------------------------------------------------------------------------
# Bruit de Perlin — tests unitaires
# ---------------------------------------------------------------------------

class TestPerlin1D:
    """Tests de l'implémentation interne du bruit de Perlin."""

    def test_output_range(self) -> None:
        """Le bruit brut est dans [-1, 1]."""
        p = _Perlin1D(seed=0)
        for x in np.linspace(0, 1000, 200):
            v = p.noise(x)
            assert -1.0 <= v <= 1.0, f"noise({x}) = {v} hors [-1, 1]"

    def test_octaves_range(self) -> None:
        """Le bruit multi-octaves est dans [-1, 1]."""
        p = _Perlin1D(seed=42)
        for x in np.linspace(0, 10000, 300):
            v = p.octaves(x, n_octaves=4)
            assert -1.01 <= v <= 1.01, f"octaves({x}) = {v}"

    def test_deterministic(self) -> None:
        """Même seed → même séquence."""
        p1 = _Perlin1D(seed=7)
        p2 = _Perlin1D(seed=7)
        for x in np.linspace(0, 500, 100):
            assert p1.noise(x) == pytest.approx(p2.noise(x))

    def test_different_seeds_differ(self) -> None:
        """Seeds différentes produisent des gradients différents (tables de permutation distinctes)."""
        p1 = _Perlin1D(seed=1)
        p2 = _Perlin1D(seed=2)
        # Les gradients internes doivent différer entre deux seeds distinctes
        assert not np.array_equal(p1._grad, p2._grad), \
            "Deux seeds différentes produisent les mêmes gradients"

    def test_continuity(self) -> None:
        """Le bruit est continu : pas de sauts brutaux entre points proches."""
        p = _Perlin1D(seed=42)
        xs = np.linspace(0, 100, 1000)
        vals = [p.noise(x) for x in xs]
        diffs = [abs(vals[i+1] - vals[i]) for i in range(len(vals)-1)]
        assert max(diffs) < 0.15, f"Saut max trop grand : {max(diffs):.4f}"


# ---------------------------------------------------------------------------
# multi_scale_sine
# ---------------------------------------------------------------------------

class TestMultiScaleSine:

    def test_output_in_range(self) -> None:
        eng = make_engine("multi_scale_sine",
            base_load=0.38, fast_amplitude=0.08, fast_period_s=3600,
            fast_phase_s=-900, daily_amplitude=0.15, daily_period_s=86400,
            daily_phase_s=-21600, weekly_amplitude=0.07,
            weekly_period_s=604800, weekly_phase_s=0.0, noise_std=0.02)
        loads = sample_loads(eng, n=500, dt=600.0)
        assert all(0.0 <= v <= 1.0 for v in loads), "Valeur hors [0, 1]"

    def test_varies_over_time(self) -> None:
        """Le signal n'est pas constant."""
        eng = make_engine("multi_scale_sine",
            base_load=0.38, fast_amplitude=0.08, fast_period_s=3600,
            fast_phase_s=0, daily_amplitude=0.15, daily_period_s=86400,
            daily_phase_s=0, weekly_amplitude=0.07, weekly_period_s=604800,
            weekly_phase_s=0.0, noise_std=0.0)
        loads = sample_loads(eng, n=200, dt=1800.0)
        assert max(loads) - min(loads) > 0.05, "Signal trop plat"

    def test_three_components_independent(self) -> None:
        """Les 3 amplitudes contribuent séparément."""
        # Sans hebdo : variance réduite
        eng_full = make_engine("multi_scale_sine",
            base_load=0.4, fast_amplitude=0.10, fast_period_s=3600,
            fast_phase_s=0, daily_amplitude=0.15, daily_period_s=86400,
            daily_phase_s=0, weekly_amplitude=0.10, weekly_period_s=604800,
            weekly_phase_s=0.0, noise_std=0.0)
        eng_no_weekly = make_engine("multi_scale_sine",
            base_load=0.4, fast_amplitude=0.10, fast_period_s=3600,
            fast_phase_s=0, daily_amplitude=0.15, daily_period_s=86400,
            daily_phase_s=0, weekly_amplitude=0.0, weekly_period_s=604800,
            weekly_phase_s=0.0, noise_std=0.0)
        loads_full = sample_loads(eng_full, n=100, dt=86400.0)
        loads_noweekly = sample_loads(eng_no_weekly, n=100, dt=86400.0)
        var_full = np.var(loads_full)
        var_reduced = np.var(loads_noweekly)
        # weekly_amplitude=0 → variance réduite (ou égale si signe s'annule)
        assert var_full >= var_reduced or abs(var_full - var_reduced) < 0.005

    def test_base_load_respected(self) -> None:
        """La moyenne est proche de base_load quand les amplitudes sont symétriques."""
        eng = make_engine("multi_scale_sine",
            base_load=0.50, fast_amplitude=0.10, fast_period_s=3600,
            fast_phase_s=0, daily_amplitude=0.10, daily_period_s=86400,
            daily_phase_s=0, weekly_amplitude=0.05, weekly_period_s=604800,
            weekly_phase_s=0.0, noise_std=0.0)
        # Sur un multiple entier de toutes les périodes, la moyenne est base_load
        # Ici on approche avec 7 cycles journaliers (604800s)
        loads = [eng.get_load_factor(t) for t in range(0, 604800, 600)]
        assert abs(np.mean(loads) - 0.50) < 0.03, f"Moyenne : {np.mean(loads):.3f}"


# ---------------------------------------------------------------------------
# perlin_noise
# ---------------------------------------------------------------------------

class TestPerlinNoise:

    def test_output_in_range(self) -> None:
        eng = make_engine("perlin_noise",
            base_load=0.48, amplitude=0.32, scale=0.00005,
            n_octaves=5, persistence=0.55, drift_rate=0.0, drift_max=0.0)
        loads = sample_loads(eng, n=500, dt=1000.0)
        assert all(0.0 <= v <= 1.0 for v in loads), "Valeur hors [0, 1]"

    def test_smooth_no_jumps(self) -> None:
        """Pas de sauts brutaux entre ticks consécutifs (lissage Perlin)."""
        eng = make_engine("perlin_noise",
            base_load=0.5, amplitude=0.3, scale=0.0001,
            n_octaves=3, persistence=0.5, drift_rate=0.0, drift_max=0.0)
        loads = [eng.get_load_factor(t) for t in range(0, 5000, 10)]
        diffs = [abs(loads[i+1] - loads[i]) for i in range(len(loads)-1)]
        assert max(diffs) < 0.15, f"Saut max : {max(diffs):.4f}"

    def test_drift_increases_load(self) -> None:
        """drift_rate > 0 → charge croissante dans le temps."""
        eng = make_engine("perlin_noise",
            base_load=0.2, amplitude=0.05, scale=0.00001,
            n_octaves=2, persistence=0.5,
            drift_rate=1e-4, drift_max=0.5)
        load_early = eng.get_load_factor(100.0)
        load_late = eng.get_load_factor(4000.0)
        # Avec dérive, la tendance doit monter (tolérance pour le bruit)
        assert load_late > load_early - 0.1

    def test_drift_capped_by_drift_max(self) -> None:
        """La dérive ne dépasse pas drift_max."""
        eng = make_engine("perlin_noise",
            base_load=0.1, amplitude=0.01, scale=0.000001,
            n_octaves=1, persistence=0.5,
            drift_rate=1e-3, drift_max=0.2)
        # À t=10 000s, drift_rate*t = 10 > drift_max=0.2 → bridé
        load = eng.get_load_factor(10000.0)
        assert load <= 0.1 + 0.01 + 0.2 + 0.05  # base + amplitude + drift_max + marge bruit

    def test_varies_over_time(self) -> None:
        """Le signal n'est pas constant."""
        eng = make_engine("perlin_noise",
            base_load=0.5, amplitude=0.3, scale=0.0001,
            n_octaves=4, persistence=0.5, drift_rate=0.0, drift_max=0.0)
        loads = sample_loads(eng, n=200, dt=500.0)
        assert max(loads) - min(loads) > 0.05


# ---------------------------------------------------------------------------
# markov_chain
# ---------------------------------------------------------------------------

class TestMarkovChain:

    def test_output_in_range(self) -> None:
        eng = make_engine("markov_chain", mean_dwell_s=100.0, noise_std=0.03)
        loads = sample_loads(eng, n=300, dt=50.0)
        assert all(0.0 <= v <= 1.0 for v in loads), "Valeur hors [0, 1]"

    def test_state_changes_occur(self) -> None:
        """Des transitions d'état se produisent sur une longue simulation."""
        eng = make_engine("markov_chain", mean_dwell_s=50.0, noise_std=0.0)
        loads = [eng.get_load_factor(t) for t in range(0, 5000, 10)]
        unique_rounded = set(round(v, 2) for v in loads)
        assert len(unique_rounded) > 1, "Aucune transition détectée"

    def test_all_four_states_reachable(self) -> None:
        """Les 4 états sont atteints sur une simulation suffisamment longue."""
        state_loads = [0.15, 0.45, 0.72, 0.95]
        eng = make_engine("markov_chain", mean_dwell_s=30.0, noise_std=0.0)
        loads = [eng.get_load_factor(t) for t in range(0, 50000, 10)]
        # Chaque état doit apparaître au moins une fois (avec tolérance bruit)
        for target in state_loads:
            found = any(abs(v - target) < 0.02 for v in loads)
            assert found, f"État {target} jamais atteint"

    def test_transition_matrix_custom(self) -> None:
        """Une matrice avec un état absorbant force l'état 0."""
        absorbing = [
            [1.0, 0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0, 0.0],
        ]
        eng = make_engine("markov_chain",
            state_loads=[0.10, 0.50, 0.80, 0.99],
            transition_matrix=absorbing,
            mean_dwell_s=10.0,
            noise_std=0.0)
        loads = [eng.get_load_factor(t) for t in range(100, 5000, 50)]
        # Après la première transition, tous les états convergent vers 0 (load=0.10)
        assert all(abs(v - 0.10) < 0.01 for v in loads), \
            f"État absorbant non respecté : {set(round(v,2) for v in loads)}"

    def test_dwell_affects_transition_frequency(self) -> None:
        """mean_dwell_s élevé → moins de transitions."""
        eng_fast = make_engine("markov_chain", mean_dwell_s=10.0, noise_std=0.0)
        eng_slow = make_engine("markov_chain", mean_dwell_s=2000.0, noise_std=0.0)

        loads_fast = [eng_fast.get_load_factor(t) for t in range(0, 3000, 10)]
        loads_slow = [eng_slow.get_load_factor(t) for t in range(0, 3000, 10)]

        # Compter les transitions (changements de valeur)
        transitions_fast = sum(1 for i in range(1, len(loads_fast))
                               if loads_fast[i] != loads_fast[i-1])
        transitions_slow = sum(1 for i in range(1, len(loads_slow))
                               if loads_slow[i] != loads_slow[i-1])

        assert transitions_fast > transitions_slow, \
            f"mean_dwell élevé devrait produire moins de transitions: {transitions_fast} vs {transitions_slow}"


# ---------------------------------------------------------------------------
# composite_stress
# ---------------------------------------------------------------------------

class TestCompositeStress:

    def test_output_in_range(self) -> None:
        eng = make_engine("composite_stress",
            base_load=0.55, daily_amplitude=0.18, daily_period_s=86400,
            daily_phase_s=-21600, weekly_amplitude=0.08, weekly_period_s=604800,
            drift_rate=2e-5, drift_max=0.25,
            spike_probability=0.0, spike_magnitude=0.25,
            perlin_scale=0.0003, perlin_amplitude=0.08, perlin_octaves=3)
        loads = sample_loads(eng, n=500, dt=600.0)
        assert all(0.0 <= v <= 1.0 for v in loads), "Valeur hors [0, 1]"

    def test_drift_monotonically_increases_baseline(self) -> None:
        """La composante de dérive croît avec le temps (sans spikes ni Perlin)."""
        eng = make_engine("composite_stress",
            base_load=0.3, daily_amplitude=0.0, daily_period_s=86400,
            daily_phase_s=0, weekly_amplitude=0.0, weekly_period_s=604800,
            drift_rate=1e-4, drift_max=0.5,
            spike_probability=0.0, spike_magnitude=0.0,
            perlin_scale=0.0003, perlin_amplitude=0.0, perlin_octaves=1)
        # Sans cycles ni Perlin, seule la dérive contribue
        load_t0 = eng.get_load_factor(0.0)
        load_t1000 = eng.get_load_factor(1000.0)
        load_t5000 = eng.get_load_factor(5000.0)
        assert load_t1000 >= load_t0, "Dérive doit croître"
        assert load_t5000 >= load_t1000, "Dérive doit croître"

    def test_drift_capped(self) -> None:
        """La dérive est bornée par drift_max."""
        eng = make_engine("composite_stress",
            base_load=0.3, daily_amplitude=0.0, daily_period_s=86400,
            daily_phase_s=0, weekly_amplitude=0.0, weekly_period_s=604800,
            drift_rate=1e-2, drift_max=0.1,
            spike_probability=0.0, spike_magnitude=0.0,
            perlin_scale=0.0, perlin_amplitude=0.0, perlin_octaves=1)
        # À t très grand, drift = min(1e-2 * t, 0.1) → plafonné à 0.1
        load_large_t = eng.get_load_factor(100000.0)
        assert load_large_t <= 0.3 + 0.1 + 0.01  # base + drift_max + marge

    def test_higher_than_nominal_on_average(self) -> None:
        """La charge composite_stress est en moyenne > multi_scale_sine nominal."""
        eng_stress = make_engine("composite_stress",
            base_load=0.55, daily_amplitude=0.18, daily_period_s=86400,
            daily_phase_s=-21600, weekly_amplitude=0.08, weekly_period_s=604800,
            drift_rate=2e-5, drift_max=0.25,
            spike_probability=0.0,  # désactiver spikes pour test déterministe
            spike_magnitude=0.25,
            perlin_scale=0.0003, perlin_amplitude=0.08, perlin_octaves=3)

        eng_nominal = make_engine("multi_scale_sine",
            base_load=0.38, fast_amplitude=0.08, fast_period_s=3600,
            fast_phase_s=-900, daily_amplitude=0.15, daily_period_s=86400,
            daily_phase_s=-21600, weekly_amplitude=0.07, weekly_period_s=604800,
            weekly_phase_s=0.0, noise_std=0.0)

        loads_stress = [eng_stress.get_load_factor(t) for t in range(0, 60000, 600)]
        loads_nominal = [eng_nominal.get_load_factor(t) for t in range(0, 60000, 600)]

        assert np.mean(loads_stress) > np.mean(loads_nominal), \
            f"stress mean={np.mean(loads_stress):.3f} <= nominal mean={np.mean(loads_nominal):.3f}"

    def test_varies_over_time(self) -> None:
        """Le signal n'est pas constant."""
        eng = make_engine("composite_stress",
            base_load=0.55, daily_amplitude=0.18, daily_period_s=86400,
            daily_phase_s=0, weekly_amplitude=0.08, weekly_period_s=604800,
            drift_rate=0.0, drift_max=0.0,
            spike_probability=0.0, spike_magnitude=0.0,
            perlin_scale=0.0003, perlin_amplitude=0.08, perlin_octaves=3)
        loads = sample_loads(eng, n=200, dt=3600.0)
        assert max(loads) - min(loads) > 0.05


# ---------------------------------------------------------------------------
# Rétrocompatibilité — profils historiques inchangés
# ---------------------------------------------------------------------------

class TestBackwardCompatibility:

    def test_sine_wave_unchanged(self) -> None:
        """sine_wave produit les mêmes valeurs qu'avant Phase 8.14."""
        eng = make_engine("sine_wave", base_load=0.35, amplitude=0.20, period_s=300.0)
        # Pic à t = T/4 (sin = 1)
        load_peak = eng.get_load_factor(75.0)   # 300/4
        assert load_peak == pytest.approx(0.55, abs=0.01)
        # Creux à t = 3T/4 (sin = -1)
        load_trough = eng.get_load_factor(225.0)
        assert load_trough == pytest.approx(0.15, abs=0.01)

    def test_ramp_with_spikes_reaches_ramp_end(self) -> None:
        """ramp_with_spikes atteint ramp_end après ramp_duration_s."""
        eng = make_engine("ramp_with_spikes",
            ramp_start=0.20, ramp_end=0.95,
            ramp_duration_s=600.0, spike_probability=0.0,
            spike_duration_s=30.0, spike_magnitude=0.30)
        load = eng.get_load_factor(700.0)
        assert load == pytest.approx(0.95, abs=0.01)

    def test_constant_profile(self) -> None:
        eng = make_engine("constant", value=0.42)
        for t in [0, 100, 1000, 86400]:
            assert eng.get_load_factor(t) == pytest.approx(0.42)

    def test_step_profile(self) -> None:
        eng = make_engine("step", t_switch_s=500.0, low_load=0.1, high_load=0.9)
        assert eng.get_load_factor(499.0) == pytest.approx(0.1)
        assert eng.get_load_factor(501.0) == pytest.approx(0.9)

    def test_unknown_profile_returns_zero(self) -> None:
        eng = make_engine("nonexistent_profile", foo=1)
        assert eng.get_load_factor(100.0) == 0.0


# ---------------------------------------------------------------------------
# Tous les profils restent dans [0, 1] — test paramétrique
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Fixtures CSV temporaires pour trace_replay
# ---------------------------------------------------------------------------

@pytest.fixture
def cpu_trace_csv(tmp_path: Path) -> Path:
    """Crée un CSV avec colonne cpu_percent (format Bitbrains converti)."""
    path = tmp_path / "test_cpu_trace.csv"
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp_s", "cpu_percent", "mem_percent", "net_in_kbps", "net_out_kbps"])
        for i in range(20):
            ts = i * 300  # 5 min entre points
            cpu = 20.0 + 60.0 * (i / 19.0)  # montée de 20% à 80%
            writer.writerow([ts, round(cpu, 2), 50.0, 10.0, 5.0])
    return path


@pytest.fixture
def load_factor_csv(tmp_path: Path) -> Path:
    """Crée un CSV avec colonne load_factor (format generate_dataset.py)."""
    path = tmp_path / "test_load_factor.csv"
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp_s", "load_factor", "temperature_c", "power_w"])
        for i in range(10):
            ts = i * 100
            load = 0.3 + 0.05 * i  # montée de 0.30 à 0.75
            writer.writerow([ts, round(load, 4), 45.0, 200.0])
    return path


# ---------------------------------------------------------------------------
# Tests _TraceReplay (unitaires)
# ---------------------------------------------------------------------------

class TestTraceReplay:
    """Tests unitaires de _TraceReplay."""

    def test_load_cpu_percent(self, cpu_trace_csv: Path) -> None:
        """Charge un CSV cpu_percent et normalise en [0,1]."""
        tr = _TraceReplay(str(cpu_trace_csv))
        assert tr.n_points == 20
        # Au début : cpu=20% → load=0.20
        assert tr.get(0.0) == pytest.approx(0.20, abs=0.01)
        # À la fin (5700s) : cpu≈80% → load≈0.80
        assert tr.get(5700.0) == pytest.approx(0.80, abs=0.02)

    def test_load_factor_direct(self, load_factor_csv: Path) -> None:
        """Charge un CSV load_factor (utilisé directement sans normalisation)."""
        tr = _TraceReplay(str(load_factor_csv))
        assert tr.n_points == 10
        assert tr.get(0.0) == pytest.approx(0.30, abs=0.01)

    def test_output_in_range(self, cpu_trace_csv: Path) -> None:
        """Toutes les valeurs interpolées sont dans [0, 1]."""
        tr = _TraceReplay(str(cpu_trace_csv))
        for t in range(0, int(tr.duration_s) + 1, 60):
            v = tr.get(float(t))
            assert 0.0 <= v <= 1.0, f"get({t}) = {v} hors [0,1]"

    def test_interpolation_monotone(self, cpu_trace_csv: Path) -> None:
        """Entre deux points de trace à charge croissante, l'interpolation est monotone."""
        tr = _TraceReplay(str(cpu_trace_csv), loop=False)
        # La trace est une montée linéaire → l'interpolation doit aussi monter
        loads = [tr.get(float(t)) for t in range(0, 5700, 100)]
        for i in range(len(loads) - 1):
            assert loads[i+1] >= loads[i] - 0.001, \
                f"Interpolation non monotone à t={i*100}: {loads[i]:.3f} → {loads[i+1]:.3f}"

    def test_loop_repeats(self, load_factor_csv: Path) -> None:
        """Avec loop=True, la valeur en t=0 et t=durée sont proches."""
        tr = _TraceReplay(str(load_factor_csv), loop=True)
        v_start = tr.get(0.0)
        v_after_loop = tr.get(tr.duration_s)
        # Après exactement une durée, on revient au début
        assert abs(v_after_loop - v_start) < 0.05, \
            f"Loop incohérent : t=0 → {v_start:.3f}, t=duration → {v_after_loop:.3f}"

    def test_no_loop_clamps_at_end(self, load_factor_csv: Path) -> None:
        """Avec loop=False, les valeurs au-delà de la trace restent constantes."""
        tr = _TraceReplay(str(load_factor_csv), loop=False)
        v_end = tr.get(tr.duration_s)
        v_beyond = tr.get(tr.duration_s * 10)
        assert v_end == pytest.approx(v_beyond, abs=0.001)

    def test_speed_factor_compression(self, cpu_trace_csv: Path) -> None:
        """speed_factor=2.0 → la trace dure 2× plus longtemps dans la simulation."""
        tr_normal = _TraceReplay(str(cpu_trace_csv), speed_factor=1.0)
        tr_slow = _TraceReplay(str(cpu_trace_csv), speed_factor=2.0)
        # À t=300s, tr_slow doit être à t_trace=150s (mi-chemin de tr_normal à t=150s)
        v_normal_150 = tr_normal.get(150.0)
        v_slow_300 = tr_slow.get(300.0)
        assert abs(v_normal_150 - v_slow_300) < 0.02, \
            f"speed_factor=2.0 : attendu {v_normal_150:.3f}, obtenu {v_slow_300:.3f}"

    def test_file_not_found_raises(self, tmp_path: Path) -> None:
        """Un chemin inexistant lève FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            _TraceReplay(str(tmp_path / "inexistant.csv"))

    def test_missing_column_raises(self, tmp_path: Path) -> None:
        """Un CSV sans colonne de charge lève ValueError."""
        bad_csv = tmp_path / "bad.csv"
        bad_csv.write_text("timestamp_s,temperature_c\n0,45.0\n300,50.0\n")
        with pytest.raises(ValueError, match="load_factor.*cpu_percent"):
            _TraceReplay(str(bad_csv))

    def test_missing_timestamp_raises(self, tmp_path: Path) -> None:
        """Un CSV sans timestamp_s lève ValueError."""
        bad_csv = tmp_path / "no_ts.csv"
        bad_csv.write_text("time,cpu_percent\n0,40\n300,50\n")
        with pytest.raises(ValueError, match="timestamp_s"):
            _TraceReplay(str(bad_csv))

    def test_duration_property(self, cpu_trace_csv: Path) -> None:
        """duration_s est correct (dernier timestamp - premier)."""
        tr = _TraceReplay(str(cpu_trace_csv))
        # 20 points à 300s d'intervalle : durée = 19 × 300 = 5700s
        assert tr.duration_s == pytest.approx(5700.0, abs=1.0)


# ---------------------------------------------------------------------------
# Tests ScenarioEngine trace_replay (intégration)
# ---------------------------------------------------------------------------

class TestTraceReplayEngine:
    """Tests d'intégration via ScenarioEngine."""

    def test_engine_trace_replay_in_range(self, cpu_trace_csv: Path) -> None:
        """Le profil trace_replay via ScenarioEngine reste dans [0, 1]."""
        eng = make_engine("trace_replay",
                          trace_file=str(cpu_trace_csv),
                          loop=True, speed_factor=1.0)
        loads = [eng.get_load_factor(float(t)) for t in range(0, 10000, 100)]
        assert all(0.0 <= v <= 1.0 for v in loads), "Valeur hors [0,1]"

    def test_engine_trace_replay_varies(self, cpu_trace_csv: Path) -> None:
        """Le profil trace_replay produit un signal non constant."""
        eng = make_engine("trace_replay",
                          trace_file=str(cpu_trace_csv),
                          loop=True, speed_factor=1.0)
        loads = [eng.get_load_factor(float(t)) for t in range(0, 6000, 300)]
        assert max(loads) - min(loads) > 0.1, "Signal trace trop plat"

    def test_engine_real_trace_embedded(self) -> None:
        """Le fichier de trace embarqué est chargeable via ScenarioEngine."""
        # Utiliser le chemin relatif depuis la racine du projet
        eng = make_engine("trace_replay",
                          trace_file="data/traces/bitbrains_week_vm00.csv",
                          loop=True, speed_factor=1.0)
        v = eng.get_load_factor(0.0)
        assert 0.0 <= v <= 1.0

    def test_engine_trace_bounded(self, load_factor_csv: Path) -> None:
        """Propriété universelle : [0,1] sur toute la durée de simulation."""
        eng = make_engine("trace_replay",
                          trace_file=str(load_factor_csv),
                          loop=True, speed_factor=1.0)
        times = list(range(0, 5000, 50))
        out = [(t, eng.get_load_factor(float(t)))
               for t in times if not (0.0 <= eng.get_load_factor(float(t)) <= 1.0)]
        assert not out, f"Valeurs hors [0,1] : {out[:3]}"


# ---------------------------------------------------------------------------
# Tous les profils restent dans [0, 1] — test paramétrique (étendu Phase 8.14B)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("ptype,params", [
    ("sine_wave",        dict(base_load=0.5, amplitude=0.5, period_s=100.0)),
    ("multi_scale_sine", dict(base_load=0.5, fast_amplitude=0.2, fast_period_s=100,
                              fast_phase_s=0, daily_amplitude=0.2, daily_period_s=1000,
                              daily_phase_s=0, weekly_amplitude=0.1, weekly_period_s=10000,
                              weekly_phase_s=0, noise_std=0.0)),
    ("perlin_noise",     dict(base_load=0.5, amplitude=0.45, scale=0.01,
                              n_octaves=4, persistence=0.5, drift_rate=0.0, drift_max=0.0)),
    ("markov_chain",     dict(mean_dwell_s=50.0, noise_std=0.0)),
    ("composite_stress", dict(base_load=0.5, daily_amplitude=0.2, daily_period_s=1000,
                              daily_phase_s=0, weekly_amplitude=0.1, weekly_period_s=10000,
                              drift_rate=0.0, drift_max=0.0,
                              spike_probability=0.0, spike_magnitude=0.2,
                              perlin_scale=0.001, perlin_amplitude=0.1, perlin_octaves=2)),
    ("ramp_with_spikes", dict(ramp_start=0.1, ramp_end=0.9, ramp_duration_s=500,
                              spike_probability=0.0, spike_duration_s=10,
                              spike_magnitude=0.1)),
    ("constant",         dict(value=0.7)),
    ("step",             dict(t_switch_s=100.0, low_load=0.2, high_load=0.8)),
])
def test_all_profiles_bounded(ptype: str, params: dict) -> None:
    """Tous les profils retournent des valeurs dans [0, 1]."""
    eng = make_engine(ptype, **params)
    times = list(range(0, 10000, 50))
    loads = [eng.get_load_factor(float(t)) for t in times]
    out_of_range = [(t, v) for t, v in zip(times, loads) if not (0.0 <= v <= 1.0)]
    assert not out_of_range, f"{ptype}: valeurs hors [0,1] : {out_of_range[:3]}"
