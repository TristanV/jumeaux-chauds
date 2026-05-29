# 🐛 LAST_BUGS.md — Bugs à Corriger

**Date :** 28 mai 2026  
**Total tests :** 264 (235 ✅ / 29 ❌)  
**Taux de réussite :** 89%

---

## 📋 Résumé des Problèmes

| Catégorie | Nombre | Sévérité |
|-----------|--------|----------|
| **Power/Status** | 5 bugs | 🔴 Critique |
| **Energy** | 10 bugs | 🔴 Critique |
| **Sensors/Telemetry** | 5 bugs | 🟡 Majeure |
| **Fan Power** | 4 bugs | 🟡 Majeure |
| **Config** | 3 bugs | 🟡 Majeure |
| **API Methods** | 2 bugs | 🟡 Majeure |

---

## 🔴 BUGS CRITIQUES — Power/Status

### ✅ Bug #1 : Machines démarrent en "on" au lieu de "off"
**Fichier :** `simulation/machine.py` ou `simulation/cluster.py`  
**Tests échouant :**
- `test_power_on_starts_machine` — Machine doit commencer "off", elle commence "on"
- `test_power_on_fails_when_too_hot` — `power_on()` retourne False mais machine reste "on"
- `test_power_on_fails_when_hot` (telemetry) — Même problème

**Symptôme :**
```
AssertionError: assert 'on' == 'off'
```

**Détails :**
- Lors de l'initialisation du cluster, les machines sont créées avec `status = "on"` au lieu de `"off"`
- Vérifier `ClusterSimulator.__init__()` et `MachineSimulator.__init__()`
- Le statut initial devrait dépendre de la config YAML (`initial_status`)

**À corriger :**
- [ ] Vérifier `simulation/machine.py` - constructeur `__init__()`
- [ ] Vérifier `simulation/cluster.py` - initialisation des machines

---

### ✅ Bug #2 : `power_off()` ne réduit pas la puissance à 0
**Fichier :** `simulation/machine.py`  
**Tests échouant :**
- `test_power_off_decreases_power_consumption` — P_off doit être 0, obtient ~200W
- `test_power_when_off` (telemetry) — Snapshot power doit être 0 quand status="off"

**Symptôme :**
```
assert 199.72347139765762 == 0.0  # power_off n'a pas réduit à 0
assert 200.99342830602245 == 0.0  # power reste non-zéro
```

**Détails :**
- Quand `status = "off"`, la puissance devrait être 0 W
- La méthode `snapshot()` retourne `power_w` basée sur la charge, ignorant le statut
- Le calcul de puissance dans `tick()` ne tient pas compte du `status`

**À corriger :**
- [ ] `simulation/machine.py` - méthode `snapshot()` → vérifier logique power_w quand status="off"
- [ ] `simulation/machine.py` - méthode `tick()` → appliquer status="off" AVANT calcul de puissance

---

### ✅ Bug #3 : Tentative de redémarrage machine trop chaude (power_on() ignore t_restart_c)
**Fichier :** `simulation/machine.py`  
**Tests échouant :**
- `test_power_on_fails_when_too_hot` — power_on() retourne False mais status reste "on"

**Symptôme :**
```
success = machine.power_on()  # Retourne False
assert success is False        # ✅ OK
assert machine.status == "off" # ❌ FAIL: status est "on"
```

**Détails :**
- `power_on()` teste correctement si T > t_restart_c et retourne False
- Mais le statut n'est pas resté "off" (car il a commencé "on" — Bug #1)
- Le statut ne devrait changer que si `power_on()` réussit

**À corriger :**
- [ ] Résoudre Bug #1 d'abord
- [ ] `simulation/machine.py` - method `power_on()` → vérifier que status reste "off" si échec

---

## 🔴 BUGS CRITIQUES — Energy

### ✅ Bug #4 : Énergie accumulée ne correspond pas à l'intégration P·dt
**Fichier :** `simulation/machine.py` ou `simulation/physics.py`  
**Tests échouant :**
- `test_energy_accumulation_matches_power` — Énergie mesurée vs calculée : 0.002 vs 2.018 kWh

**Symptôme :**
```
AssertionError: Énergie incohérente : 0.002 vs 2.018 kWh
assert 20.159526787528414 < 0.1  # Erreur relative > 2000% !
```

**Détails :**
- L'accumulateur d'énergie dans `energy_kwh_cumulated` n'est pas mis à jour correctement
- Ou le calcul de ΔE dans `tick()` est faux
- Vérifier : où et comment `energy_kwh_cumulated` est incrémenté

**À corriger :**
- [ ] `simulation/machine.py` - vérifier calcul ΔE dans `tick()`
- [ ] `simulation/physics.py` - vérifier `compute_energy_kwh()` 
- [ ] S'assurer que ΔE = ∫P(t)·dt / 3600 (conversion W·s → kWh)

---

### ✅ Bug #5 : Énergie augmente quand la machine est OFF
**Fichier :** `simulation/machine.py`  
**Tests échouant :**
- `test_zero_energy_when_off` — Energy augmente de 0.000555 kWh quand machine OFF

**Symptôme :**
```
assert 0.0005549787220133417 <= (0.0 + 0.0001)
AssertionError: Énergie a augmenté quand machine OFF
```

**Détails :**
- Quand `status = "off"`, `power_w` devrait être 0
- Donc ΔE = 0 · dt / 3600 = 0
- Mais l'énergie augmente → `power_w` n'est pas 0 quand OFF

**À corriger :**
- [ ] Résoudre Bug #2 d'abord (power_w doit être 0 quand OFF)
- [ ] Vérifier que `tick()` applique `status == "off"` AVANT calcul de puissance

---

### ✅ Bug #6-8 : `simulator._tick()` n'existe pas
**Fichier :** `simulation/cluster.py`  
**Tests échouant :**
- `test_cluster_energy_increases` — AttributeError: '_tick'
- `test_cluster_cost_calculation` — AttributeError: '_tick'
- `test_pue_affects_cost` — AttributeError: '_tick'
- `test_nominal_lower_load_than_stress` — AttributeError: '_tick'
- `test_machine_power_change_affects_cluster_energy` — AttributeError: '_tick'
- `test_fan_speed_change_affects_cluster_power` — AttributeError: '_tick'

**Symptôme :**
```
simulator._tick()
AttributeError: 'ClusterSimulator' object has no attribute '_tick'
```

**Détails :**
- Les tests appellent `simulator._tick()` pour un seul tick
- Mais `ClusterSimulator` n'a que `run(async)`, pas `_tick()`
- Solution : ajouter une méthode publique `tick()` à ClusterSimulator

**À corriger :**
- [ ] `simulation/cluster.py` - ajouter méthode `tick(load_factor, dt)` ou `_tick()`
- [ ] Cette méthode doit faire un seul tick pour toutes les machines

---

### ✅ Bug #9 : Puissance fan non appliquée (fan_power_w ignoré)
**Fichier :** `simulation/machine.py` ou `simulation/physics.py`  
**Tests échouant :**
- `test_higher_fan_speed_increases_power` — Delta puissance fans = 0.8W au lieu de 30W
- `test_fan_power_included_in_total` — Delta = -1.27W au lieu de +30W

**Symptôme :**
```
assert 0.8425699850544106 > (30.0 * 0.8)  # Delta trop petit
assert -1.2699569083648612 > (30.0 * 0.8) # Delta négatif !
```

**Détails :**
- Quand RPM augmente de 0 à 5000, la puissance totale devrait augmenter de ~30W (2 fans × 15W)
- Mais n'augmente que de 0.8W → fans ne contribuent pas à la puissance
- Vérifier : où la puissance fan est calculée et ajoutée au total

**À corriger :**
- [ ] `simulation/machine.py` - `compute_power_w()` ou `tick()` → ajouter puissance fan au total
- [ ] `simulation/physics.py` - `compute_energy_kwh()` → inclure puissance fan

---

### ✅ Bug #10 : Fonction `compute_energy_kwh()` ne gère pas la signature correctement
**Fichier :** `simulation/physics.py`  
**Tests échouant :**
- `test_energy_is_positive` — TypeError: 'float' object is not iterable
- `test_energy_grows_with_power` — TypeError: 'float' object is not iterable
- `test_energy_cumulates_over_ticks` — TypeError: 'float' object is not iterable
- `test_fans_contribute_to_energy` — TypeError: 'float' object is not iterable

**Symptôme :**
```python
e = compute_energy_kwh(1000.0, 2, 15.0, 10.0)
#                      power   fans  ???   ???
# Line: total_w = power_w + sum(fan_power_w_by_rpm)
# Error: TypeError: 'float' object is not iterable
```

**Détails :**
- Signature : `compute_energy_kwh(power_w, fan_count, fan_power_w_by_rpm=None, fan_power_w=None, ...)`
- Tests appellent avec `(1000.0, 2, 15.0, 10.0)` → 3ème arg (15.0) est un float, pas une liste
- La fonction s'attend à une liste pour `fan_power_w_by_rpm`
- Tests passent une valeur scalaire au mauvais paramètre

**À corriger :**
- [ ] `simulation/physics.py` - revoir signature et logique de `compute_energy_kwh()`
- [ ] Clarifier : fan_power_w_by_rpm doit être None ou list[float]
- [ ] Tests : corriger les appels à `compute_energy_kwh()`

---

## 🟡 BUGS MAJEURS — Sensors/Telemetry

### ✅ Bug #11 : Structure des capteurs changée (dict → list)
**Fichier :** `simulation/machine.py`  
**Tests échouant :**
- `test_snapshot_sensors_structure` — `sensors.items()` échoue car sensors est une list
- `test_worker_two_sensors` — `"temp_cpu" in sensors` échoue (list, pas dict)
- `test_sensor_bias_applied` — `sensors["temp_cpu"]` échoue (list, pas dict)
- `test_sensors_initialized` — `"temp_cpu" in snapshot["sensors"]` échoue

**Symptôme :**
```python
sensors = snapshot["sensors"]  # Obtient: [{'sensor_id': 'temp_cpu', ...}, ...]
sensors.items()  # AttributeError: 'list' object has no attribute 'items'
"temp_cpu" in sensors  # False (c'est une list, pas un dict)
sensors["temp_cpu"]  # TypeError: list indices must be integers or slices
```

**Détails :**
- Anciennement : `sensors = {"temp_cpu": {...}, "temp_inlet": {...}}`
- Maintenant : `sensors = [{"sensor_id": "temp_cpu", ...}, {"sensor_id": "temp_inlet", ...}]`
- Tests attendent l'ancien format dict, pas list

**À corriger :**
- [ ] `simulation/machine.py` - `snapshot()` méthode → revoir structure `sensors`
- [ ] Soit revenir au format dict, soit mettre à jour tous les tests pour list
- [ ] Décider : quel format est préféré pour la telemetry MQTT ?

---

### ✅ Bug #12 : Température n'augmente plus quand machine OFF
**Fichier :** `simulation/machine.py` ou `simulation/physics.py`  
**Tests échouant :**
- `test_temperature_decreases_when_machine_off` — T augmente au lieu de diminuer (27.3 → 27.8°C)

**Symptôme :**
```
assert temps[-1] < temps[0]  # Attends T à baisser
# Mais: T après = 27.8°C, T avant = 27.3°C (augmente !)
```

**Détails :**
- Quand machine OFF et load_factor=0, température devrait décroître vers ambient
- Mais elle augmente légèrement
- Possible : bruit ou dérive accumulée même quand OFF

**À corriger :**
- [ ] `simulation/physics.py` - `compute_thermal_step()` → vérifier que T → T_ambient quand OFF + load=0

---

## 🟡 BUGS MAJEURS — Fan Power

### ✅ Bug #13 : Effet des fans sur température inversé
**Fichier :** `simulation/machine.py` ou `simulation/physics.py`  
**Tests échouant :**
- `test_higher_fan_speed_reduces_temperature` — T_fast > T_slow au lieu de < (26.8 vs 26.1°C)

**Symptôme :**
```
assert temp_fast_avg < temp_slow_avg
# Fans rapides n'ont pas baissé T : 26.8°C vs 26.1°C
# (c'est pire avec fans rapides !)
```

**Détails :**
- Quand on augmente vitesse fans, température devrait BAISSER
- Mais elle augmente légèrement
- Possible : constante tau_max n'est pas appliquée correctement ou fans n'ajustent pas tau

**À corriger :**
- [ ] `simulation/physics.py` - `compute_tau()` → vérifier dépendance RPM
- [ ] `simulation/machine.py` - `tick()` → vérifier que tau_effective diminue avec RPM

---

### ✅ Bug #14 : `fan_power_per_rpm_estimation` — Delta trop petit
**Fichier :** `simulation/machine.py`  
**Tests échouant :**
- `test_fan_power_per_rpm_estimation` — Delta = 2.5W au lieu de 15W minimum

**Symptôme :**
```
assert 2.534477753831311 > (30.0 * 0.5)  # 2.5W < 15W
```

**Détails :**
- Attendu : 2 fans × 15W = 30W de contribution additionnelle
- Obtenu : 2.5W seulement
- Même problème que Bug #9 (fans ne contribuent pas à la puissance)

**À corriger :**
- [ ] Résoudre Bug #9 d'abord

---

### ✅ Bug #15 : `fan_speed_zero_uses_no_power` — Power trop haut
**Fichier :** `simulation/machine.py`  
**Tests échouant :**
- `test_fan_speed_zero_uses_no_power` — P = 729W au lieu de < 400W

**Symptôme :**
```
assert 729.7466983903241 < (200.0 + 200.0)  # 729W > 400W
```

**Détails :**
- Master idle = 200W, charge 0.5 → devrait faire ~200-500W
- Mais 729W → charge est appliquée même avec load_factor=0.5 bas
- Possible : formule puissance ou paramètres thermiques corrompus

**À corriger :**
- [ ] `simulation/machine.py` - vérifier paramètres idle_w et max_w du master
- [ ] `simulation/physics.py` - `compute_load_power()` → vérifier formule

---

## 🟡 BUGS MAJEURS — Configuration

### ✅ Bug #16 : Configuration YAML manque `temperature_std_c`
**Fichier :** `config/base.yaml` ou scénarios  
**Tests échouant :**
- `test_noise_enabled_nominal` — ConfigAttributeError: Missing key temperature_std_c

**Symptôme :**
```python
assert cfg.simulation.noise.temperature_std_c == 0.3
# ConfigAttributeError: Missing key temperature_std_c
```

**Détails :**
- Configuration bruit attend `temperature_std_c` (écart-type bruit température)
- Mais n'existe pas dans YAML
- Vérifier structure `simulation.noise` dans base.yaml

**À corriger :**
- [ ] `config/base.yaml` - ajouter `temperature_std_c` sous `simulation.noise`
- [ ] Valeur suggérée : 0.3°C (conforme test)

---

## 📋 Checklist de Corrections

### Phase 1 : Bugs Critiques Power/Status (URGENT)
- [ ] **Bug #1** : Machines démarrent en "on" au lieu de "off"
  - Fichiers : `simulation/machine.py`, `simulation/cluster.py`
  - Impact : 3 tests échouent
  
- [ ] **Bug #2** : `power_off()` ne réduit pas puissance à 0
  - Fichiers : `simulation/machine.py`
  - Impact : 2 tests échouent
  
- [ ] **Bug #3** : power_on() ignore t_restart_c
  - Fichiers : `simulation/machine.py`
  - Impact : 1 test échoue (résolvable après Bug #1)

### Phase 2 : Bugs Critiques Energy (URGENT)
- [ ] **Bug #4** : Énergie ne correspond pas à P·dt
  - Fichiers : `simulation/machine.py`, `simulation/physics.py`
  - Impact : 1 test échoue
  
- [ ] **Bug #5** : Énergie augmente quand OFF
  - Fichiers : `simulation/machine.py`
  - Impact : 1 test échoue (résolvable après Bug #2)
  
- [ ] **Bug #6-8** : `simulator._tick()` n'existe pas
  - Fichiers : `simulation/cluster.py`
  - Impact : 6 tests échouent
  - Correction : ajouter méthode `tick(load_factor, dt)` ou `_tick()`
  
- [ ] **Bug #9** : Puissance fan non appliquée
  - Fichiers : `simulation/machine.py`, `simulation/physics.py`
  - Impact : 3 tests échouent
  
- [ ] **Bug #10** : `compute_energy_kwh()` signature incorrecte
  - Fichiers : `simulation/physics.py`
  - Impact : 4 tests échouent

### Phase 3 : Bugs Majeurs Sensors
- [ ] **Bug #11** : Structure sensors dict → list (breaking change)
  - Fichiers : `simulation/machine.py`
  - Impact : 4 tests échouent
  - Décision : revert dict ou update tests ?
  
- [ ] **Bug #12** : Température n'augmente pas quand OFF
  - Fichiers : `simulation/physics.py`
  - Impact : 1 test échoue

### Phase 4 : Bugs Majeurs Fans & Config
- [ ] **Bug #13** : Fans n'abaissent pas température
  - Fichiers : `simulation/physics.py`, `simulation/machine.py`
  - Impact : 1 test échoue
  
- [ ] **Bug #14** : Fan power estimation trop bas
  - Fichiers : `simulation/machine.py`
  - Impact : 1 test échoue (dépend Bug #9)
  
- [ ] **Bug #15** : Power trop haut avec fans arrêtés
  - Fichiers : `simulation/machine.py`
  - Impact : 1 test échoue
  
- [ ] **Bug #16** : Config YAML manque `temperature_std_c`
  - Fichiers : `config/base.yaml`
  - Impact : 1 test échoue
  - Correction : ajouter clé manquante

---

## 📊 Priorisation Recommandée

**Jour 1 (Critiques):**
1. Bug #1 — Status initial
2. Bug #2 — Power OFF = 0
3. Bug #6-8 — Ajouter `_tick()` à ClusterSimulator
4. Bug #10 — Fixer `compute_energy_kwh()` signature

**Jour 2 (Majeurs):**
5. Bug #4 — Énergie accumulation
6. Bug #9 — Fan power contribution
7. Bug #11 — Sensors structure

**Jour 3 (Validation):**
8. Bug #12, #13, #14, #15 — Physics fine-tuning
9. Bug #16 — Config YAML

---

*Document généré automatiquement — à mettre à jour après chaque correction*
