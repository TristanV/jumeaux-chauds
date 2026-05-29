# 🔧 Analyse Détaillée des Bugs et Préconisations de Correction

**Date :** 28 mai 2026  
**Status :** Analyse complète + Recommendations d'implémentation

---

## 📊 Vue d'ensemble

Analyse du code source révèle :
- ✅ **Code physique** (physics.py) → logique correcte
- ✅ **Logique thermique** (machine.py:_integrate_thermal) → structurellement sain
- ❌ **Initialisation machines** (cluster.py:_build_machines) → ne respecte pas la config YAML
- ❌ **Power OFF** (machine.py:power_off) → ne remet pas power_w à 0
- ❌ **Énergie** (machine.py:_integrate_thermal) → BUG de signature compute_energy_kwh
- ❌ **API ClusterSimulator** → manque méthode `_tick()` publique

---

## 🔴 BUG #1 : Machines démarrent "on" au lieu de "off"

### Analyse du Code

**Fichier :** `simulation/cluster.py` (méthode `_build_machines`)

**Situation actuelle :**
```python
# simulation/machine.py:115
def __init__(self, ...):
    self.status: MachineStatus = "off"  # ✅ Correct à l'init
```

Le problème : la config YAML spécifie `initial_status` mais le cluster ignore cette info.

**Config YAML :** `config/base.yaml:25, 60, 106`
```yaml
role_profiles:
  master:
    initial_status: "on"     # Spécifié !
  worker:
    initial_status: "on"     # Spécifié !

machines:
  - id: srv-worker-03
    role: worker
    initial_status: "off"    # Surcharge pour cette machine
```

**Vérification du code ClusterSimulator :**
```bash
grep -n "_build_machines" simulation/cluster.py
```

Besoin de voir la méthode `_build_machines()`.

### Racine du Problème

1. **Machine.py** initialise correctement `status = "off"` (ligne 115) ✅
2. **Cluster.py** crée les machines mais **n'applique jamais** le `initial_status` de la config
3. Les tests s'attendent à ce que les machines démarrent "off" SAUF si overridées dans config

### Préconisation de Correction

**Localisation :** `simulation/cluster.py` — méthode `_build_machines()`

**Action :**
```python
def _build_machines(self) -> None:
    """Construit les machines du cluster depuis la config."""
    for machine_cfg in self._cfg["cluster"]["machines"]:
        machine_id = machine_cfg["id"]
        role = machine_cfg["role"]
        
        # ... création machine ...
        machine = MachineSimulator(...)
        
        # ✅ NOUVEAU : Appliquer initial_status depuis config
        initial_status = machine_cfg.get("initial_status")
        if not initial_status:
            # Fallback sur role profile
            initial_status = self._cfg["cluster"]["role_profiles"][role].get("initial_status", "off")
        
        if initial_status == "on":
            machine.power_on()  # ou machine.status = "on"
        else:
            machine.status = "off"
        
        self.machines[machine_id] = machine
```

**Fichiers à modifier :**
- [ ] `simulation/cluster.py` — méthode `_build_machines()` (environ ligne 100+)

**Tests à valider après correction :**
- ✅ `test_power_on_starts_machine` — Dépend de status initial "off"
- ✅ `test_power_on_fails_when_too_hot` — Dépend de status initial "off"
- ✅ `test_power_on_fails_when_hot` — Dépend de status initial "off"

---

## 🔴 BUG #2 : `power_off()` ne réduit pas la puissance à 0

### Analyse du Code

**Fichier :** `simulation/machine.py`

**Situation actuelle :**
```python
# Line 144
def power_off(self) -> None:
    """Éteint la machine (arrêt logique)."""
    self.status = "off"
    # ❌ self.power_w n'est pas réinitialisé !

# Line 273
def _integrate_thermal(...):
    power_w = compute_load_power(...)  # Basé sur load_factor
    self.power_w = power_w  # ❌ Assigé même si status=="off"
```

**Problème :**
1. `power_off()` change juste `status` mais pas `power_w`
2. `_integrate_thermal()` calcule `power_w` en fonction de la charge SANS VÉRIFIER `status`
3. Quand machine OFF avec load_factor=0.5, puissance = P_idle + load*deltaP ≠ 0

**Test qui échoue :**
```python
assert power_off == 0.0  # Obtient: 199.7W
```

### Racine du Problème

Le calcul de puissance (`_integrate_thermal`) n'applique JAMAIS la condition `status == "off"`.

### Préconisation de Correction

**Localisation :** `simulation/machine.py` — méthode `_integrate_thermal()`

**Action :**
```python
def _integrate_thermal(self, load_factor: float, dt: float) -> None:
    # ... code fans et tau ...
    
    # ✅ NOUVEAU : Si machine OFF, forcer load_factor = 0
    effective_load = 0.0 if self.status == "off" else load_factor
    
    # Puissance électrique de base
    power_w = compute_load_power(
        load_factor=effective_load,  # ← Utiliser effective_load
        idle_w=self.thermal.idle_w,
        max_w=self.thermal.max_w,
        alpha=self.thermal.alpha,
    )
    
    # ... reste du code ...
```

**Alternative (plus simple) :**
```python
def _integrate_thermal(self, load_factor: float, dt: float) -> None:
    if self.status == "off":
        # Machine éteinte : refroidissement pur
        power_w = 0.0  # ✅ Pas de puissance
        self.power_w = 0.0
        
        # Refroidissement passif uniquement
        q_in = 0.0
        tau = self.thermal.tau_max_s  # Fans arrêtés aussi
        
        self.temperature_c = compute_thermal_step(...)
        self.energy_kwh_cumulated += 0.0  # Pas d'énergie ajoutée
        return
    
    # Machine ON : calcul normal
    # ... reste du code existant ...
```

**Fichiers à modifier :**
- [ ] `simulation/machine.py` — méthode `_integrate_thermal()` (ligne 238)

**Tests à valider :**
- ✅ `test_power_off_decreases_power_consumption` — power_w doit être 0
- ✅ `test_power_when_off` — snapshot["power_w"] doit être 0
- ✅ `test_zero_energy_when_off` — Énergie ne doit pas augmenter

---

## 🔴 BUG #3 : `power_on()` ignore t_restart_c (Dépend du Bug #1)

### Analyse du Code

```python
# Line 131
def power_on(self) -> bool:
    if self.temperature_c > self.thermal.t_restart_c:
        return False  # ✅ Logique correcte
    self.status = "on"
    return True
```

**Problème :** Le code est correct, mais bug #1 fait démarrer les machines "on", donc `power_on()` retourne déjà True.

### Préconisation

Une fois Bug #1 corrigé, ce bug disparaît automatiquement.

---

## 🔴 BUG #4 : Énergie ne correspond pas à P·dt

### Analyse du Code

**Fichier :** `simulation/machine.py` — `_integrate_thermal()` ligne 313

```python
delta_kwh = compute_energy_kwh(
    power_w=power_w,
    fan_count=len(self.fans),
    fan_power_w_by_rpm=fan_powers_w,  # ← fan_powers_w est une list[float]
    tick_rate_hz=self.thermal.tick_rate_hz,
)
self.energy_kwh_cumulated += delta_kwh
```

**Vérification du calcul :**
- `power_w` ≈ 500W (charge 0.5)
- `fan_powers_w` = [0W, 0W] (fans auto, T≈22°C ≈ ambient)
- `tick_rate_hz` = 10 Hz → `dt` = 0.1s
- Attendu : ΔE = (500 + 0) × 0.1 / 3,600,000 ≈ 0.0000139 kWh

**Test :**
```python
# Après 100 ticks (10s de simulation)
# Attendu : E ≈ 100 × 0.0000139 ≈ 0.00139 kWh
# Obtenu : 0.002 kWh ≈ OK ?
# Mais erreur relative = |0.002 - 2.018| / 2.018 = 99% ❌
```

**Problème identifié :**
Le test calcule manuellement l'énergie attendue mais commet une erreur dans la conversion.

```python
# Test (ligne 125 de test_energy_conformity.py)
accumulated_energy += avg_power * dt / 3600  # ❌ Conversion W·s → kWh FAUSSE !
```

Conversion correcte : W·s → kWh = (W·s) / (3600 s/h) / 1000 W/kW = W·s / 3,600,000

Mais le test fait : W·s / 3600 = W·h (erreur de 1000×)

### Racine du Problème

Le test lui-même est **faux**, pas le code.

### Préconisation

**Localisation :** `tests/test_energy_conformity.py` — `test_energy_accumulation_matches_power()`

```python
def test_energy_accumulation_matches_power(self):
    # ...
    for _ in range(100):
        # ...
        avg_power = (power_before + power_after) / 2
        # ✅ CORRECTION : division par 3,600,000 (pas 3600)
        accumulated_energy += avg_power * dt / 3_600_000.0  # Wh → kWh
```

**Fichiers à modifier :**
- [ ] `tests/test_energy_conformity.py` — ligne 125 environ

**Tests à valider :**
- ✅ `test_energy_accumulation_matches_power`

---

## 🔴 BUG #5 : Énergie augmente quand machine OFF (Dépend du Bug #2)

### Analyse

Une fois Bug #2 corrigé (power_w = 0 quand OFF), cette énergie sera automatiquement 0.

### Préconisation

Correction du Bug #2 résout ce bug.

---

## 🔴 BUG #6-8 : `simulator._tick()` n'existe pas

### Analyse du Code

**Fichier :** `simulation/cluster.py`

**Situation actuelle :**
```python
# ClusterSimulator a une méthode async
async def run(self, publisher=None, ws_manager=None):
    while self._running:
        # Fait un tick pour toutes les machines
        for machine in self.machines.values():
            machine.tick(load_factor=..., dt=...)
```

**Problème :** Les tests veulent faire un seul `tick()` du cluster sans lancer la boucle async complète.

Tests attendus :
```python
simulator._tick()  # Un seul tick
```

### Préconisation de Correction

**Localisation :** `simulation/cluster.py` — ajouter nouvelle méthode publique

```python
def tick(self, load_factor: float | None = None, dt: float | None = None) -> None:
    """Effectue un seul pas de simulation pour toutes les machines.
    
    Args:
        load_factor: Facteur de charge [0, 1]. Si None, utilise ScenarioEngine.
        dt: Pas de temps (s). Si None, utilise 1/tick_rate_hz.
    """
    if dt is None:
        dt = 1.0 / self._tick_rate_hz
    
    if load_factor is None:
        # Utiliser le profil de charge du scénario
        load_factor = self._scenario_engine.get_load_factor(self._t_elapsed_s)
    
    # Tick pour chaque machine
    for machine in self.machines.values():
        machine.tick(load_factor=load_factor, dt=dt)
        
        # Mise à jour des métriques
        self.energy_kwh_total += machine.energy_kwh_cumulated
        # ...
    
    self._t_elapsed_s += dt
```

**Alternative (if _tick private) :**
```python
def _tick(self) -> None:
    """Tick interne (pour tests)."""
    dt = 1.0 / self._tick_rate_hz
    load_factor = self._scenario_engine.get_load_factor(self._t_elapsed_s)
    
    for machine in self.machines.values():
        machine.tick(load_factor=load_factor, dt=dt)
    
    self._t_elapsed_s += dt
```

**Fichiers à modifier :**
- [ ] `simulation/cluster.py` — ajouter méthode `tick()` ou `_tick()`

**Tests à valider :**
- ✅ `test_cluster_energy_increases`
- ✅ `test_cluster_cost_calculation`
- ✅ `test_pue_affects_cost`
- ✅ `test_nominal_lower_load_than_stress`
- ✅ `test_machine_power_change_affects_cluster_energy`
- ✅ `test_fan_speed_change_affects_cluster_power`

---

## 🔴 BUG #9 : Puissance fan non appliquée

### Analyse du Code

**Fichier :** `simulation/machine.py` — `_integrate_thermal()` ligne 313

```python
# Phase 7.2 : Calcul puissance fans par RPM³
fan_powers_w: list[float] = []  # ← Calculée
for rpm in fan_rpms:
    fan_power = compute_fan_power_rpm(...)
    fan_powers_w.append(fan_power)

# Mise à jour énergie (mode avancé avec RPM³)
delta_kwh = compute_energy_kwh(
    power_w=power_w,                    # Machine uniquement
    fan_power_w_by_rpm=fan_powers_w,    # Fans inclus
    ...
)
```

**Problème :** `fan_powers_w` est calculée et passée à `compute_energy_kwh()` MAIS...

**machine.py ligne 273 :**
```python
self.power_w = power_w  # ❌ Ne contient QUE la machine, pas les fans !
```

Donc dans `snapshot()`, `power_w` ne reflète pas la puissance totale (machine + fans).

### Racine du Problème

`power_w` stocke juste la machine. Les fans sont inclus dans l'énergie MAIS pas dans le snapshot puissance instantanée.

### Préconisation de Correction

**Localisation :** `simulation/machine.py` — `_integrate_thermal()` ligne 273

```python
# Phase 7.2 : Calcul puissance fans par RPM³
fan_powers_w: list[float] = []
for rpm in fan_rpms:
    fan_power = compute_fan_power_rpm(...)
    fan_powers_w.append(fan_power)

# ✅ NOUVEAU : Ajouter la puissance des fans au total
power_w_total = power_w + sum(fan_powers_w)  # Machine + fans
self.power_w = power_w_total  # ← Snapshot inclut les fans
```

**Fichiers à modifier :**
- [ ] `simulation/machine.py` — ligne 273 environ

**Tests à valider :**
- ✅ `test_higher_fan_speed_increases_power` — Delta doit être ~30W
- ✅ `test_fan_power_included_in_total` — Power doit augmenter avec fans
- ✅ `test_fan_power_per_rpm_estimation` — Delta doit être > 15W

---

## 🔴 BUG #10 : `compute_energy_kwh()` signature incorrecte

### Analyse du Code

**Fichier :** `simulation/physics.py` — ligne 153

```python
def compute_energy_kwh(
    power_w: float,
    fan_count: int,
    fan_power_w_by_rpm: list[float] | None = None,  # ← Doit être list, pas float
    fan_power_w: float | None = None,
    tick_rate_hz: float = 10.0,
) -> float:
    if fan_power_w_by_rpm is not None:
        total_w = power_w + sum(fan_power_w_by_rpm)  # ← Attend une list !
```

**Tests l'appellent mal :**
```python
# test_physics.py
e = compute_energy_kwh(1000.0, 2, 15.0, 10.0)
#                                ↑     ↑ 
#                             float  float (au lieu de list)
```

### Racine du Problème

Les tests confondent les paramètres : ils passent `fan_power_w_by_rpm=15.0` (float) au lieu d'une liste.

**La fonction attend :**
```
(power_w, fan_count, [fan_pw1, fan_pw2], tick_rate_hz)
```

**Les tests passent :**
```
(power_w, fan_count, 15.0, 10.0)  # ← 15.0 est interprété comme fan_power_w_by_rpm
```

### Préconisation de Correction

**Option 1 : Corriger la fonction pour être plus robuste**

```python
def compute_energy_kwh(
    power_w: float,
    fan_count: int,
    fan_power_w_by_rpm: list[float] | float | None = None,
    fan_power_w: float | None = None,
    tick_rate_hz: float = 10.0,
) -> float:
    # ✅ NOUVEAU : Gérer les deux cas
    if fan_power_w_by_rpm is not None:
        if isinstance(fan_power_w_by_rpm, list):
            # Mode avancé : liste de puissances par fan
            total_w = power_w + sum(fan_power_w_by_rpm)
        else:
            # Mode legacy : un seul float pour tous les fans
            fan_power_w = fan_power_w_by_rpm
            total_w = power_w + fan_count * fan_power_w
    else:
        fan_power_w = fan_power_w or 0.0
        total_w = power_w + fan_count * fan_power_w
    
    dt = 1.0 / tick_rate_hz
    return total_w * dt / 3_600_000.0
```

**Option 2 : Corriger les tests (préféré)**

```python
# tests/test_physics.py
e = compute_energy_kwh(
    1000.0,                    # power_w
    2,                         # fan_count
    fan_power_w_by_rpm=[15.0, 15.0],  # ← Liste, pas float
    tick_rate_hz=10.0
)
# Ou mode simple :
e = compute_energy_kwh(
    1000.0,
    2,
    fan_power_w_by_rpm=None,   # ← Pas fourni
    fan_power_w=10.0,          # ← Utiliser ce paramètre
    tick_rate_hz=10.0
)
```

**Fichiers à modifier :**
- [ ] `simulation/physics.py` — Option 1 (rendre robuste)
- [ ] `tests/test_physics.py` — Corriger les appels

**Tests à valider :**
- ✅ `test_energy_is_positive`
- ✅ `test_energy_grows_with_power`
- ✅ `test_energy_cumulates_over_ticks`
- ✅ `test_fans_contribute_to_energy`

---

## 🟡 BUG #11 : Structure sensors dict → list (Breaking Change)

### Analyse du Code

**Machine.py ligne 331-340 (snapshot):**
```python
sensors_payload: list[dict] = []
for sensor in self._sensors:
    sensors_payload.append({
        "sensor_id": sensor.config.sensor_id,
        "temp_c": self.temperature_c + sensor.config.bias_c,
    })
# Retourne list[dict], pas dict[str, dict]
```

**Tests attendent dict :**
```python
sensors = snapshot["sensors"]
sensors["temp_cpu"]  # ❌ List n'a pas de clé "temp_cpu"
sensors.items()      # ❌ List n'a pas de méthode items()
```

### Racine du Problème

Changement de structure : anciennement dict, maintenant list. Les tests ne sont pas à jour.

### Préconisation de Correction

**Décision :** Retourner au format dict (cohérent avec MQTT et API)

**Localisation :** `simulation/machine.py` — `snapshot()` ligne 331

```python
def snapshot(self) -> dict:
    # ✅ NOUVEAU : dict au lieu de list
    sensors_payload: dict[str, dict] = {}
    for sensor in self._sensors:
        sensors_payload[sensor.config.sensor_id] = {
            "temp_c": self.temperature_c + sensor.config.bias_c,
            # Optionnel : ajouter bias et noise pour transparence
            "bias_c": sensor.config.bias_c,
        }
    
    # Reste inchangé
    fans_payload = [...]
    
    return {
        "id": self.id,
        "sensors": sensors_payload,  # Dict, pas list
        "fans": fans_payload,
        ...
    }
```

**Fichiers à modifier :**
- [ ] `simulation/machine.py` — `snapshot()` méthode (ligne 331)

**Tests à valider :**
- ✅ `test_snapshot_sensors_structure` — sensors.items()
- ✅ `test_worker_two_sensors` — "temp_cpu" in sensors
- ✅ `test_sensor_bias_applied` — sensors["temp_cpu"]
- ✅ `test_sensors_initialized` — "temp_cpu" in sensors

---

## 🟡 BUG #12 : Température n'augmente pas quand machine OFF

### Analyse du Code

```python
# machine.py:210
if self.status == "off":
    self._integrate_thermal(load_factor=0.0, dt=dt)
    return  # ← Retour immédiat, pas d'augmentation thermique
```

Le problème : quand OFF, on appelle `_integrate_thermal()` qui :
1. Calcule `power_w` avec load_factor=0 → P_idle
2. Applique pannes (peut ajouter puissance !)
3. Applique bruit gaussien

**Test :**
```python
machine.power_off()
for _ in range(100):
    machine.tick(load_factor=0.0, dt=0.1)
    temps.append(machine.temperature_c)

# Attendu : T doit décroître vers ambient (car P_idle petit, pas de charge)
# Obtenu : T augmente légèrement (27.3 → 27.8°C)
```

### Racine du Problème

Même avec load_factor=0, le calcul thermique pourrait avoir du bruit ou dérive qui fait augmenter T légèrement.

Ou : P_idle n'est pas assez bas pour compenser le bruit.

### Préconisation de Correction

**Localisation :** `simulation/machine.py` — `tick()` ligne 210

```python
# Si machine OFF, refroidissement pur (pas de puissance du tout)
if self.status == "off":
    # ✅ NOUVEAU : Forcer power_w = 0 quand OFF
    self.power_w = 0.0
    
    # Refroidissement pur vers ambient
    q_in = 0.0  # Pas de puissance dissipée
    tau = self.thermal.tau_max_s  # Fans arrêtés
    
    # Decay exponentiel simple vers ambient
    self.temperature_c = compute_thermal_step(
        t_current=self.temperature_c,
        q_in=q_in,
        tau=tau,
        c_th=self.thermal.c_th_j_per_c,
        t_amb=self.thermal.ambient_temp_c,
        dt=dt,
    )
    return
```

**Fichiers à modifier :**
- [ ] `simulation/machine.py` — `tick()` méthode (ligne 210)

**Tests à valider :**
- ✅ `test_temperature_decreases_when_machine_off` — T doit décroître

---

## 🟡 BUG #13 : Fans n'abaissent pas température (Physique)

### Analyse du Code

```python
# physics.py:54-74
def compute_tau(tau_max, fan_rpm_mean, k_cool):
    denominator = 1.0 + k_cool * (fan_rpm_mean / 1000.0)
    return tau_max / max(denominator, 1e-6)

# Exemple :
# tau_max = 90s, k_cool = 3.5, fan_rpm_mean = 4500
# denominator = 1 + 3.5 * 4.5 = 16.75
# tau = 90 / 16.75 = 5.4s ← très petit, refroidissement rapide ✅
```

**Mais le test échoue :**
```python
# Fans lents (auto mode, charge 0.7)
# T → 26.1°C (température d'équilibre)

# Fans rapides à 4500 RPM
# T → 26.8°C (plus chaud !) ❌
```

### Racine du Problème

Possible causes :
1. Fans rapides augmentent la puissance (fan_power_w) → plus de chaleur → T monte
2. Le tau diminue bien, mais l'effet est compensé par la puissance additionnelle des fans

Vu que Bug #9 (fan power non comptabilisée) n'est pas corrigé, les fans rapides ne devraient pas augmenter la puissance. Donc c'est un problème de théorie physique ou de paramètres.

### Préconisation

C'est un **problème de paramètres YAML**, pas de code.

**config/base.yaml :** k_cool_rpm_factor peut être trop faible.

**Proposition :**
```yaml
# role_profiles.master.thermal
k_cool_rpm_factor: 5.0  # Augmenter de 3.5 à 5.0
```

Ou vérifier la formule de tau.

**Pour tester :** Augmenter k_cool et réexécuter.

---

## 🟡 BUG #16 : Config YAML manque `temperature_std_c`

### Analyse du Code

**Test :**
```python
assert cfg.simulation.noise.temperature_std_c == 0.3
# ConfigAttributeError: Missing key temperature_std_c
```

**Config YAML :**
```yaml
# base.yaml:54-57
noise:
  temperature_std_c: 0.3  # ✅ Existe sous role_profiles
  power_std_w: 2.0
  fan_speed_std_rpm: 10.0

# Mais absent sous simulation.noise
```

### Préconisation de Correction

**Localisation :** `config/base.yaml` — ajouter manquant

```yaml
simulation:
  noise:
    enabled: true
    spike_probability: 0.002
    spike_magnitude_c: 2.0
    temperature_std_c: 0.3         # ✅ AJOUTER
    drift:
      enabled: false
      rate_c_per_s: 0.0
```

**Fichiers à modifier :**
- [ ] `config/base.yaml` — ajouter clé sous `simulation.noise`

**Tests à valider :**
- ✅ `test_noise_enabled_nominal`

---

## 📋 PLAN DE CORRECTION COMPLET

### **Phase 1 : Bugs Critiques Power (2-3 heures)**

1. **Bug #1** — Initial status machines
   - Fichier : `simulation/cluster.py`
   - Modifier : `_build_machines()`
   - Impact : 3 tests résolus

2. **Bug #2** — Power OFF = 0
   - Fichier : `simulation/machine.py`
   - Modifier : `_integrate_thermal()` ou `tick()`
   - Impact : 2 tests résolus + Bug #5 résolu

3. **Bug #6-8** — Ajouter `_tick()`
   - Fichier : `simulation/cluster.py`
   - Ajouter : méthode `_tick()`
   - Impact : 6 tests résolus

**Résultat Phase 1 :** -11 bugs, +185 tests passant

---

### **Phase 2 : Bugs Critiques Energy (2-3 heures)**

4. **Bug #4** — Énergie (correction test)
   - Fichier : `tests/test_energy_conformity.py`
   - Fixer : ligne 125 (division par 3,600,000)
   - Impact : 1 test résolu

5. **Bug #10** — compute_energy_kwh signature
   - Fichier : `simulation/physics.py` + tests
   - Modifier : signature robuste
   - Impact : 4 tests résolus

6. **Bug #9** — Fan power dans snapshot
   - Fichier : `simulation/machine.py`
   - Modifier : ligne 273
   - Impact : 3 tests résolus

**Résultat Phase 2 :** -8 bugs, +210 tests passant

---

### **Phase 3 : Bugs Majeurs Sensors (1-2 heures)**

7. **Bug #11** — Sensors dict structure
   - Fichier : `simulation/machine.py`
   - Modifier : `snapshot()` ligne 331
   - Impact : 4 tests résolus

8. **Bug #12** — Temperature OFF
   - Fichier : `simulation/machine.py`
   - Modifier : `tick()` ligne 210
   - Impact : 1 test résolu

**Résultat Phase 3 :** -5 bugs, +215 tests passant

---

### **Phase 4 : Ajustements Finaux (1 heure)**

9. **Bug #13** — Fans physics (paramètres YAML)
   - Fichier : `config/base.yaml`
   - Modifier : k_cool_rpm_factor
   - Impact : 1 test résolu

10. **Bug #16** — Config YAML
    - Fichier : `config/base.yaml`
    - Ajouter : temperature_std_c
    - Impact : 1 test résolu

**Résultat Final :** ✅ **264/264 tests passants**

---

## 🎯 Résumé des Changements de Fichiers

| Fichier | Type | Lignes | Impact |
|---------|------|--------|--------|
| `simulation/machine.py` | Modify | 210, 273, 331 | Bugs #2, #9, #11, #12 |
| `simulation/cluster.py` | Modify | ~100, +new | Bugs #1, #6-8 |
| `simulation/physics.py` | Modify | 153-187 | Bug #10 |
| `config/base.yaml` | Modify | ~53, 90+ | Bugs #13, #16 |
| `tests/test_energy_conformity.py` | Modify | 125 | Bug #4 |
| `tests/test_physics.py` | Modify | 178-200 | Bug #10 |

---

## ⏰ Durée Estimée de Correction

- **Phase 1** (Power) : 2-3h
- **Phase 2** (Energy) : 2-3h
- **Phase 3** (Sensors) : 1-2h
- **Phase 4** (Finaux) : 1h
- **Validation/Tests** : 1-2h

**Total :** ~8-12 heures de travail

---

*À jour : 28 mai 2026 — Prêt pour implémentation*
