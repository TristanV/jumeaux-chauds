# Analyse complète : Gestion du temps simulé et des événements

**Date :** 3 juin 2026  
**Auteur :** Claude (analyse automatisée)  
**Statut :** Point diagnostic complet

---

## 1. État global actuel

La simulation comporte **2 problèmes majeurs** dans la gestion du temps :

| Aspect | Statut | Détail |
|--------|--------|--------|
| **Base de temps simulé (2005)** | ❌ **NON IMPLÉMENTÉ** | Aucune date de départ définie — le temps est relatif depuis t=0 |
| **Accumulation du temps simulé** | ✅ **OK** | `_t_elapsed_s` s'accumule correctement avec `speed_multiplier` |
| **Paramétrage vitesse (YAML)** | ✅ **OK** | `speed_multiplier` transmis depuis config → simulation |
| **Événements chronologiquement situés** | ⚠️ **PARTIEL** | Événements existent mais timestamps utilisent heure réelle |
| **Vitesse paramétrée et appliquée** | ✅ **OK** | `speed_multiplier` affecte bien `_t_elapsed_s` |

---

## 2. Gestion du temps simulé (détails techniques)

### 2.1 Accumulation du temps (`_t_elapsed_s`)

**Fichier :** `simulation/cluster.py`

```python
# Initialisation (ligne 125)
self._t_elapsed_s: float = 0.0

# Tick avec vitesse (ligne 377)
self._t_elapsed_s += dt * self._speed_multiplier
```

**Comportement :**
- `dt = 1.0 / tick_rate_hz` (ex: 0.1 s à 10 Hz)
- À chaque tick : `_t_elapsed_s` augmente de `dt × speed_multiplier`
- **Correct !** ✅

**Exemples :**
- Vitesse 1x (real-time) : `0.1 * 1.0 = 0.1 s par tick`
- Vitesse 60x : `0.1 * 60.0 = 6.0 s par tick`
- Vitesse 86400x : `0.1 * 86400.0 = 8640.0 s par tick = 2.4 heures par tick`

---

### 2.2 Date de départ (2005)

**Problème trouvé :** Aucune date de départ n'est définie !

**Fichiers impliqués :**
- `config/base.yaml` — Aucune clé `simulation_start_date` ou `base_timestamp`
- `config/scenarios/*.yaml` — Idem

**Conséquence :**
- Les événements n'ont pas de date absolue
- Seul le temps relatif (`_t_elapsed_s`) est connu
- Les timestamps dans les événements MQTT utilisent `datetime.now()` (heure réelle système)

**Impact :**
```
Temps simulé: 2005-01-01 00:00:00 + 3600 secondes = 2005-01-01 01:00:00
Timestamp réel: 2024-06-03 14:25:37.123 (heure système actuelle)
                              ↑ INCOHÉRENCE CHRONOLOGIQUE
```

---

## 3. Transmission du paramétrage YAML → Application

### 3.1 Chaîne de transmission du `speed_multiplier`

✅ **ENTIÈREMENT FONCTIONNELLE**

```
config/scenarios/nominal.yaml
    ↓ (ligne 8: speed_multiplier: 1.0)
config/loader.py (load_config())
    ↓ (charge OmegaConf)
simulation/cluster.py.__init__()
    ↓ (ligne 93-99: récupère et valide)
self._speed_multiplier: float
    ↓ (ligne 377: utilisé dans tick)
_t_elapsed_s += dt * self._speed_multiplier
```

**Code source :** `cluster.py` lignes 93-99

```python
self._speed_multiplier: float = float(
    config["simulation"].get("speed_multiplier", 1.0)
)
if self._speed_multiplier <= 0:
    raise ValueError(
        f"speed_multiplier must be > 0, got {self._speed_multiplier}"
    )
```

**Validation :** ✅ Valide les valeurs (doit être > 0)

### 3.2 Autres paramètres YAML correctement transmis

| Paramètre YAML | Type | Utilisation | Statut |
|----------------|------|-------------|--------|
| `speed_multiplier` | float | Multiplication du temps | ✅ OK |
| `tick_rate_hz` | float | Fréquence de tick | ✅ OK |
| `events_per_sec` | float | Fréquence d'événements | ✅ OK |
| `cpu_throttle_enabled` | bool | Limiter publication CPU | ✅ OK |
| `cpu_throttle_target_hz` | float | Fréquence max cible | ✅ OK |
| `load_profile.type` | str | Profil de charge | ✅ OK |
| `load_profile.params.*` | float/str | Paramètres charge | ✅ OK |
| `fault_injection.*` | dict | Config pannes | ✅ OK |

---

## 4. Positionnement chronologique des événements

### 4.1 Où les timestamps des événements sont générés

**Problème :** Tous les timestamps utilisent l'heure réelle système !

#### Événement 1 : Télémétrie machine
**Fichier :** `mqtt/publisher.py:141-157`

```python
async def publish_telemetry(self, snapshot: dict) -> None:
    payload = {
        "ts": _now_iso(),  # ← HEURE RÉELLE SYSTÈME
        **snapshot,
    }
```

Fonction helper (ligne 30-31) :
```python
def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime(...)  # ← datetime.now() = HEURE RÉELLE
```

#### Événement 2 : Changement d'état
**Fichier :** `mqtt/publisher.py:190-198`

```python
async def publish_status(self, cluster_id, machine_id, status):
    await self._publish(
        ...,
        {"ts": _now_iso(), "status": status},  # ← HEURE RÉELLE
        ...
    )
```

#### Événement 3 : Pannes
**Fichier :** `mqtt/publisher.py:200-222`

```python
async def publish_fault(self, cluster_id, machine_id, fault_data, event="injected"):
    payload = {
        "ts": _now_iso(),  # ← HEURE RÉELLE
        "event": event,
        **fault_data,
    }
```

#### Événement 4 : Snapshot cluster (WebSocket + API)
**Fichier :** `simulation/cluster.py:397-408`

```python
def get_snapshot(self) -> dict:
    return {
        "cluster_id": self.cluster_id,
        "ts": datetime.now(timezone.utc).isoformat(),  # ← HEURE RÉELLE (ligne 401)
        "metrics": {...},
        "machines": {...},
    }
```

### 4.2 Tableau : Où viennent les timestamps

| Événement | Source | Code | Timestamp |
|-----------|--------|------|-----------|
| Télémétrie machine | MQTT publisher | `_now_iso()` | Heure réelle |
| État machine (on/off/degraded) | MQTT publisher | `_now_iso()` | Heure réelle |
| Panne (injection/recovery) | MQTT publisher | `_now_iso()` | Heure réelle |
| Snapshot cluster (WS/API) | Cluster simulator | `datetime.now()` | Heure réelle |
| Résumé cluster (MQTT) | MQTT publisher | `_now_iso()` | Heure réelle |
| Métriques énergie (MQTT) | MQTT publisher | `_now_iso()` | Heure réelle |

**Problème :** ❌ Aucun timestamp ne vient de `_t_elapsed_s` !

---

## 5. Vitesse de simulation : Paramétrage et prise en compte

### 5.1 Configuration YAML

**Fichier :** `config/scenarios/nominal.yaml` (ligne 8)

```yaml
simulation:
  speed_multiplier: 1.0              # défaut : real-time (1s/s)
                                     # 60.0 = 1 min/sec
                                     # 3600.0 = 1 hour/sec
                                     # 86400.0 = 1 day/sec
  cpu_throttle_enabled: true
  cpu_throttle_target_hz: 100.0      # ~100 ticks réels/s max
```

### 5.2 Prise en compte dans les calculs de temps

**OUI, correctement pris en compte :**

```python
# Dans cluster.py:377
self._t_elapsed_s += dt * self._speed_multiplier

# Où dt = 1.0 / tick_rate_hz
# Exemple: tick_rate_hz = 10 Hz → dt = 0.1 s
```

### 5.3 Impact sur la charge/scénario

✅ **Correctement appliqué :**

```python
# Dans cluster.py:254
load_factor = self._scenario_engine.get_load_factor(self._t_elapsed_s)
```

Le `_t_elapsed_s` multiplié par `speed_multiplier` est utilisé pour calculer la charge du scénario. Cela signifie que :

- À vitesse 60x, les vagues de charge se passent **60× plus vite**
- À vitesse 86400x, un jour simulé se fait en 1 seconde réelle

### 5.4 Impact sur les pannes

✅ **Correctement appliqué :**

```python
# Dans scenarios.py:157-159
elapsed = self._elapsed_by_machine.get(machine_id, 0.0)
elapsed += dt  # dt déjà multiplié par speed_multiplier dans le tick
self._elapsed_by_machine[machine_id] = elapsed
```

Les pannes sont déclenchées selon le temps écoulé simulé (pas réel), donc elles se passent aussi à la vitesse accélérée.

---

## 6. Tableau récapitulatif : Événements avec accélération

Voici ce qui se passe lors d'une **accélération du temps** :

### Scénario : 1 seconde réelle, vitesse 86400x (1 jour/sec)

| Aspect | Real-time (1x) | 1 jour/sec (86400x) | Ratio |
|--------|---|---|---|
| **Durée réelle** | 1 seconde | 1 seconde | Identique |
| **Temps simulé écoulé** | 1 seconde | 1 jour (86400 s) | **×86400** |
| **Ticks exécutés** | 10 ticks (à 10 Hz) | 10 ticks (à 10 Hz) | Identique |
| **Snapshots générés** | 10 snapshots | 10 snapshots | Identique |
| **Pannes déclenchées** | ~Poisson(1s) | ~Poisson(86400s) | **×86400** |
| **Données télémétrie** | ~10 points | ~10 points | Identique en nombre |
| **Charge scénario** | `sine_wave(1s)` | `sine_wave(86400s)` | **Profil avancé de 86400s** |
| **Timestamps MQTT** | `2024-06-03 14:25:37 UTC` | `2024-06-03 14:25:38 UTC` | Heure système (ignorant accélération) |
| **Énergie cumulée** | ~0.05 kWh | ~0.05 kWh | **Identique** ⚠️ PROBLÈME |

### Analyse détaillée

#### ✅ Correctement accéléré :
1. **Temps simulé (`_t_elapsed_s`)** — Accumule correctement
2. **Pannes (distribution temporelle)** — Déclenchées selon temps simulé
3. **Profils de charge** — Évoluent avec le temps simulé
4. **Nombre d'événements** — Correct (N ticks = N snapshots)

#### ❌ Problématiques :
1. **Timestamps MQTT/WebSocket** — Utilisent heure réelle, pas simulée
2. **Énergie cumulée** — **INCOHÉRENCE MAJEURE** ⚠️
   - Si 1 jour simulé passe en 1 seconde réelle
   - La machine consomme la même énergie (basée sur temps réel, pas simulé)
   - **Devrait :** 86400× plus d'énergie en 1 jour simulé
   - **Actuellement :** 1 jour de consommation étalée sur 1 seconde réelle

#### ⚠️ Effets secondaires observés :
- **Grafana affiche l'heure système** (pas le temps simulé)
- **Historique est incohérent** (horodatage réel ≠ simulation)
- **Calculs énergétiques peuvent être faux** (dépendent du dt réel vs simulé)

---

## 7. Résumé des problèmes identifiés

### Problème 1 : Pas de date de départ de simulation (2005)
**Sévérité :** 🔴 **CRITIQUE**

- Aucune configuration pour `simulation_start_date`
- Temps simulé = temps relatif depuis t=0 (pas de date absolue)
- Timestamps des événements = heure réelle système

**Correction requise :**
1. Ajouter `simulation.start_date` au YAML (ex: "2005-01-01T00:00:00Z")
2. Calculer timestamp absolu = `start_date + _t_elapsed_s`
3. Utiliser ce timestamp partout (MQTT, API, Grafana, etc.)

---

### Problème 2 : Timestamps toujours = heure réelle système
**Sévérité :** 🔴 **CRITIQUE**

- `datetime.now()` appelé dans `mqtt/publisher.py:_now_iso()`
- Ligne 401 de `simulation/cluster.py:get_snapshot()`
- Ignorent complètement `_t_elapsed_s` et `speed_multiplier`

**Correction requise :**
1. Passer `_t_elapsed_s` à ClusterSimulator → MQTT publisher
2. Calculer `timestamp = base_date + timedelta(seconds=_t_elapsed_s)`
3. Remplacer tous les `_now_iso()` par `calculate_simulated_time()`

---

### Problème 3 : Énergie cumulée incohérente avec accélération
**Sévérité :** 🟠 **MAJEURE**

- Énergie basée sur puissance réelle × dt réel
- Quand vitesse = 86400x, 1 jour passe en 1 seconde
- Mais énergie consommée ≠ 86400 × (énergie pour 1 jour à 1x)

**Exemple :**
```
Vitesse 1x : 1 jour réel → ~2 kWh consommé
Vitesse 86400x : 1 jour simulé (1 sec réel) → ~0.03 mWh consommé ❌ FAUX
Devrait être : ~2 kWh (même qu'1 jour réel)
```

**Correction requise :**
1. Énergie = puissance × `dt * speed_multiplier` (pas seulement `dt`)
2. Ou : Énergie basée sur temps simulé, pas temps réel

---

## 8. Recommandations de correction

### Phase 8.4 (Améliorations prioritaires)

#### 1. Ajouter configuration date de départ

**Fichier :** `config/base.yaml`

```yaml
simulation:
  start_date: "2005-01-01T00:00:00Z"  # Date de départ de simulation
  speed_multiplier: 1.0
  tick_rate_hz: 10.0
```

#### 2. Créer fonction `calculate_simulated_timestamp()`

**Fichier :** Nouveau module `simulation/time.py`

```python
from datetime import datetime, timezone, timedelta

def get_simulated_time(start_date: datetime, elapsed_s: float) -> datetime:
    """Calcule le temps simulé absolu."""
    return start_date + timedelta(seconds=elapsed_s)

def get_simulated_time_iso(start_date: datetime, elapsed_s: float) -> str:
    """Retourne ISO string du temps simulé."""
    dt = get_simulated_time(start_date, elapsed_s)
    return dt.isoformat() + "Z"
```

#### 3. Passer `start_date` à ClusterSimulator

**Fichier :** `simulation/cluster.py`

```python
def __init__(self, config: dict, start_date: datetime | None = None):
    ...
    self._start_date = start_date or datetime(2005, 1, 1, tzinfo=timezone.utc)
    self._t_elapsed_s: float = 0.0
```

#### 4. Utiliser temps simulé partout

**Fichier :** `mqtt/publisher.py`

```python
async def publish_telemetry(self, snapshot: dict) -> None:
    # Au lieu de:
    # "ts": _now_iso(),
    # Utiliser:
    from simulation.time import get_simulated_time_iso
    "ts": get_simulated_time_iso(self._start_date, snapshot.get("t_elapsed_s")),
```

#### 5. Corriger le calcul d'énergie

**Fichier :** `simulation/physics.py` ou `machine.py`

```python
# Au lieu de:
# energy_kwh += power_w * dt / 3600 / 1000

# Utiliser:
# energy_kwh += power_w * (dt * speed_multiplier) / 3600 / 1000
```

---

## 9. Tests existants

**Fichier :** `tests/test_speed_multiplier.py` (374 lignes)

✅ Les tests **valident correctement** :
- Accumulation de `_t_elapsed_s` avec `speed_multiplier`
- Changement de vitesse à chaud
- Paramètres YAML transmis correctement
- CPU throttling

❌ Les tests **ne couvrent PAS** :
- Timestamps simulés (tous les tests utilisent heure réelle)
- Date de départ de simulation
- Cohérence énergétique avec accélération
- Synchronisation avec Grafana/MQTT

---

## 10. Conclusion

| Point | Verdict | Détail |
|-------|---------|--------|
| **Temps simulé accumule correctement** | ✅ OK | `_t_elapsed_s` fonctionne bien |
| **Vitesse paramétrée et appliquée** | ✅ OK | YAML → simulation fonctionne |
| **Date de départ (2005)** | ❌ MANQUANT | Aucune config `start_date` |
| **Événements datés correctement** | ❌ FAUX | Tous les timestamps = heure réelle |
| **Énergie cohérente avec accélération** | ❌ FAUX | Pas de prise en compte de `speed_multiplier` |
| **Timestamps MQTT/WebSocket** | ❌ FAUX | Heure système au lieu de temps simulé |

**Verdict global :** La gestion du **temps relatif simulé** fonctionne bien (60% des objectifs atteints), mais la **chronologie absolue** et les **événements datés** ne fonctionnent pas correctement (40%).

Pour une simulation pédagogique réaliste, les **3 problèmes critiques** doivent être corrigés.

---

*Analyse complétée le 3 juin 2026*
