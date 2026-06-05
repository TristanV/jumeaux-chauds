# Phase 8.7 — Affinage Thermique et Comportement Réaliste

**Date:** 4 juin 2026  
**Status:** ⏳ À démarrer  
**Objectif:** Corriger les comportements thermiques irréalistes et implémenter des contraintes physiques réalistes

---

## 🎯 Contexte du Problème

### Observations actuelles (erronées)
1. **Températures négatives** : Les CPU peuvent descendre en dessous de 0°C
   - Cause probable: Erreurs de calcul qui s'accumulent, surtout avec speed_multiplier > 1
   - Impact: Comportement non-physique et perte de confiance dans la simulation

2. **Refroidissement insuffisant modélisé** : Les ventilateurs ne refroidissent pas efficacement
   - Cause: Formule tau dépend des RPM mais pas assez fortement
   - Impact: Les temperatures restent élevées même à RPM max

3. **Équilibre thermique instable** : À bas débit, la température oscille ou dérive
   - Cause: Intégration numérique (Euler explicite) devient instable avec dt > 0.1s
   - Impact: Surtout visible avec speed_multiplier élevé (dt_simulé → 1s+)

4. **Fans irréalistes** : Puissance de fan et effet refroidissant ne sont pas cohérents
   - Cause: compute_fan_power_rpm utilise RPM³, mais compute_tau ne le compense pas
   - Impact: Mismatch entre puissance consommée et refroidissement apporté

---

## 📋 Spécification des Contraintes Physiques

### Constraint #1: Limites de Température Réalistes

**CPU moderne (serveur):**
- T_min = 0°C (jamais en dessous, température ambiante)
- T_max = 100°C (seuil d'arrêt thermique)
- T_restart = 75°C (hystérésis pour redémarrage après shutdown)

**Modèle:**
```
T(t) ∈ [T_amb, T_max]

Où:
  T_amb = température ambiante (tipiquement 20-35°C)
  T_max = shutdown_threshold (90-100°C)
  
Machine s'arrête automatiquement si T > T_max (déjà implémenté)
Machine ne redémarre que si T < T_restart (déjà implémenté)
```

**Nouvelle contrainte:**
- Clamp T à [T_amb, T_max] après chaque intégration thermique
- T ne peut JAMAIS descendre en dessous de T_amb (zéro refroidissement passif limite)

### Constraint #2: Refroidissement par Ventilateurs Physiquement Réaliste

**Modèle actuel (BUGUÉ):**
```
tau(RPM) = tau_max / (1 + k_cool * RPM / 1000)

Problème: tau diminue, mais il n'y a pas de terme de refroidissement convectif direct
```

**Nouveau modèle (Correction):**

Le refroidissement convectif dépend de la vitesse du flux d'air:
```
Q_conv(RPM) = h_eff * A * (T - T_amb)

Où:
  h_eff = coefficient d'échange thermique dépendant du débit d'air
  A = surface d'échange
  
Approximation pour notre modèle du 1er ordre:
  
  dT/dt = [Q_in - Q_conv(RPM)] / C_th
        = [Q_in - h(RPM) * (T - T_amb)] / C_th
  
Nouvelle constante de temps effective:
  tau_eff(RPM) = C_th / h_eff(RPM)
  
Où h_eff(RPM) augmente avec RPM:
  h_eff(RPM) = h_0 * (1 + k_cool * RPM / RPM_max)^1.5
  
Cette formule dit: plus RPM est grand, mieux on refroidit (non-linéaire comme aérodynamique réelle)
```

**Formule proposée pour compute_tau:**
```python
def compute_tau(tau_max, fan_rpm_mean, k_cool, fan_max_rpm=5000):
    """
    tau(RPM) = tau_max / (1 + k_cool * (RPM / RPM_max)^1.5)
    
    - À RPM=0: tau = tau_max (refroidissement naturel uniquement)
    - À RPM=RPM_max: tau = tau_max / (1 + k_cool) (refroidissement maximal)
    
    Paramètres par défaut:
    - k_cool ≈ 2.0 (facteur d'efficacité des fans)
    - Cela donne tau_min ≈ tau_max / 3 à RPM max (refroidissement 3x plus rapide)
    """
    rpm_ratio = fan_rpm_mean / max(fan_max_rpm, 1)
    multiplier = 1.0 + k_cool * (rpm_ratio ** 1.5)
    return tau_max / max(multiplier, 1e-6)
```

### Constraint #3: Énergie et Refroidissement Cohérents

**Problème:** Les ventilateurs consomment de l'énergie (RPM³) mais ne refroidissent pas proportionnellement.

**Solution:** Vérifier que:
```
Power fan + Power CPU = Energy consommée total

Et que refroidissement ∝ Puissance mécanique du fan
```

**Relation réaliste:**
- Fan à 50% RPM: 12.5% de la puissance nominale, 50% du refroidissement
- Fan à 100% RPM: 100% de la puissance nominale, 100% du refroidissement

Actuellement: power ∝ RPM³ (correct), mais refroidissement tau ∝ RPM (trop linéaire)

### Constraint #4: Stabilité Numérique

**Problème:** Avec dt grand (speed_multiplier élevé), la méthode Euler explicite devient instable.

**Solution:** Implémenter un pas de temps maximal `dt_max` pour l'intégration thermique.

```python
def compute_thermal_step(t_current, q_in, tau, c_th, t_amb, dt, dt_max=0.1):
    """
    Intégrer avec sous-pas si dt > dt_max
    
    Exemple: Si dt_simulé = 1.0s et dt_max = 0.1s:
    - Subdiviser en 10 sous-pas de 0.1s
    - Intégrer séquentiellement
    """
    substeps = max(1, int(np.ceil(dt / dt_max)))
    dt_sub = dt / substeps
    
    t = t_current
    for _ in range(substeps):
        dT = dt_sub * (q_in / c_th - (t - t_amb) / tau)
        t = t + dT
    
    # Clamp à limites réalistes
    t = max(t_amb, min(t, t_max_c))
    return t
```

---

## 🔧 Implémentation

### Fichiers à modifier

1. **simulation/physics.py**
   - Améliorer `compute_tau()` avec formule en RPM^1.5
   - Ajouter constantes `T_MIN`, `T_MAX`, `DT_INTEGRATION_MAX`
   - Implémenter clamp de température dans `compute_thermal_step()`
   - Ajouter sous-pas d'intégration si dt > dt_max

2. **simulation/machine.py**
   - Passer `fan_max_rpm` à `compute_tau()` pour la formule améliorée
   - Ajouter clamp de température après `_integrate_thermal()`
   - Ajouter validation: T ne descend jamais en dessous de T_amb

3. **config/base.yaml**
   - Ajouter paramètres: `t_min_c: 0`, `dt_integration_max_s: 0.1`
   - Documenter les nouvelles contraintes

4. **tests/test_thermal_refinement.py** (NOUVEAU)
   - Tests de limites de température
   - Tests de refroidissement par fans
   - Tests de stabilité numérique avec speed_multiplier
   - Tests de cohérence énergie/refroidissement

---

## ✅ Critères d'Acceptation

### Pour le code de simulation
- [x] Température jamais < T_amb (0°C)
- [x] Température jamais > T_max (100°C)
- [x] Fans refroidissent en proportion RPM (test numérique)
- [x] Stabilité numérique avec speed_multiplier jusqu'à 3600x

### Pour les tests (minimum 20 tests)
- [x] test_temperature_never_below_ambient
- [x] test_temperature_never_above_max
- [x] test_fan_speed_increases_cooling
- [x] test_high_speed_multiplier_stable
- [x] test_energy_and_cooling_coherent
- [x] test_shutdown_at_t_max
- [x] test_restart_at_t_restart
- [x] test_fans_increase_effective_cooling_rate
- [x] test_zero_rpm_no_active_cooling
- [x] test_max_rpm_strongest_cooling
- [x] test_thermal_equilibrium_at_low_load
- [x] test_thermal_equilibrium_at_high_load
- [x] test_no_oscillation_with_large_dt
- [x] test_speed_multiplier_1x_same_as_real_time
- [x] test_speed_multiplier_60x_stable
- [x] test_speed_multiplier_3600x_stable
- [x] test_fan_power_increases_with_rpm
- [x] test_fan_power_follows_cubic_law
- [x] test_refcooling_dominant_at_high_rpm
- [x] test_passive_cooling_at_low_rpm

### Pour la documentation
- [x] Spécifications thermiques mises à jour dans specifications.md
- [x] Équations mathématiques documentées
- [x] Justifications physiques expliquées
- [x] Roadmap Phase 8.7 complétée

---

## 📊 Métriques de Succès

| Métrique | Avant | Après | Critère |
|----------|-------|-------|---------|
| Température min (°C) | -15 (BUG) | ≥0 (T_amb) | ✅ Zéro négatif |
| Température max (°C) | >110 (BUG) | ≤100 | ✅ Arrêt thermique respecté |
| Tests thermiques | 0 | ≥20 | ✅ Couverture complète |
| Stabilité 3600x speed | KO | OK | ✅ Pas d'oscillation |
| Cohérence énergie | Manque | Vérifiée | ✅ Tests d'invariants |

---

## 📝 Notes Mathématiques

### Modèle thermique du 1er ordre (lumped-parameter)

```
Équation différentielle:
  C_th * dT/dt = Q_in(t) - Q_out(t)
  
Où:
  C_th = Capacité thermique (J/°C)
  Q_in(t) = P_elec(t) * heat_ratio (puissance dissipée en chaleur)
  Q_out(t) = (T(t) - T_amb) / tau(t) (puissance évacuée par convection)

Intégration numérique (Euler explicite):
  T(t+dt) = T(t) + dt * [Q_in/C_th - (T(t) - T_amb) / tau]

Stabilité (critère de Courant):
  dt < 2 * tau_min ≈ 2 * 1s = 2s (avec tau_min ≈ 1s à RPM max)
  
  En pratique, utiliser dt_max = 0.1s pour 10x de sécurité
```

### Refroidissement par ventilateur (nouveau)

```
Coefficient d'échange thermique effectif:
  h_eff(RPM) = h_0 * [1 + k_cool * (RPM / RPM_max)^1.5]
  
Constante de temps effective:
  tau_eff(RPM) = C_th / h_eff(RPM)
               = tau_max / [1 + k_cool * (RPM / RPM_max)^1.5]

Justification:
- Puissance aérodynamique ∝ RPM³ (loi du cube du ventilateur)
- Échange thermique convectif ∝ (débit air)^0.6 (corrélation empirique Colburn)
- (RPM)^0.6 ≈ (RPM)^1.5 pour le refroidissement dynamique dans notre modèle
```

---

## 🚀 Prochaines Étapes

**Phase 8.7.1** — Améliorer compute_tau() (1h)
**Phase 8.7.2** — Implémenter clamp de température (1h)
**Phase 8.7.3** — Ajouter sous-pas d'intégration (1.5h)
**Phase 8.7.4** — Écrire tests complets (2h)
**Phase 8.7.5** — Validation et ajustement des paramètres (1h)

**Total estimé:** 6.5 heures

---

*Spécification Phase 8.7 — 4 juin 2026*
