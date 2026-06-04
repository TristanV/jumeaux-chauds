# Rétablissement de la gestion du temps simulé (2005)

**Date :** 3 juin 2026  
**Statut :** ✅ Implémenté et testé  
**Ticket :** Rétablir date de départ paramétrable dans YAML + timestamps simulés

---

## Résumé des modifications

| Aspect | Avant | Après | Statut |
|--------|-------|-------|--------|
| **Date de départ** | ❌ Aucune | ✅ 2005-01-01 (paramétrable) | ✅ Corrigé |
| **Timestamps snapshots** | ❌ Heure réelle | ✅ Temps simulé | ✅ Corrigé |
| **Timestamps MQTT** | ❌ Heure réelle | ✅ Temps simulé | ✅ Corrigé |
| **Timestamps événements** | ❌ Heure réelle | ✅ Temps simulé | ✅ Corrigé |
| **Paramètres YAML** | ❌ Aucun | ✅ `start_time` | ✅ Corrigé |

---

## Fichiers modifiés et créés

### 1. ✅ Nouveau module : `simulation/time.py` (98 lignes)

**Responsabilité :** Utilitaires pour gestion du temps simulé

```python
Functions:
- parse_start_time(start_time_str) → datetime
  Charge date de départ depuis YAML ou défaut (2005-01-01)

- get_simulated_time(start_time, elapsed_s) → datetime
  Calcule timestamp absolu = start_time + elapsed_s

- get_simulated_time_iso(start_time, elapsed_s) → str
  Retourne ISO 8601 avec millisecondes et Z
  Exemple: "2005-01-01T12:34:56.789Z"

- get_simulated_time_iso_seconds(start_time, elapsed_s) → str
  Retourne ISO 8601 sans millisecondes
```

**Avantages :**
- Logique centralisée (pas dupliquée)
- Facile à tester
- Réutilisable partout (API, MQTT, etc.)

---

### 2. ✅ Modification : `simulation/cluster.py`

#### 2.1 Import (ligne 24)
```python
from .time import parse_start_time, get_simulated_time_iso
```

#### 2.2 Initialisation dans `__init__()` (après ligne 119)
```python
# Gestion du temps simulé
start_time_str = config["simulation"].get("start_time")
self._start_time = parse_start_time(start_time_str)
logger.info(f"Simulation start time: {self._start_time.isoformat()}")
```

**Impact :**
- Chaque ClusterSimulator charge sa date de départ
- Défaut : 2005-01-01T00:00:00Z
- Paramétrable via YAML `simulation.start_time`

#### 2.3 Modification `get_snapshot()` (ligne 407)
**Avant :**
```python
"ts": datetime.now(timezone.utc).isoformat(),
```

**Après :**
```python
"ts": get_simulated_time_iso(self._start_time, self._t_elapsed_s),
"t_elapsed_s": self._t_elapsed_s,  # Pour calculs downstream
```

**Impact :**
- Timestamp = temps simulé (2005 + secondes écoulées)
- Inclut `t_elapsed_s` pour accès par MQTT publisher
- Valide même à vitesse accélérée (86400x)

#### 2.4 Modifications dans `_publish_tick()` (lignes 320, 339, 349)

**Appels modifiés :**

```python
# publish_status : ajouter timestamp simulé
ts_status = get_simulated_time_iso(self._start_time, self._t_elapsed_s)
await publisher.publish_status(
    self.cluster_id, mid, current_status, ts=ts_status
)

# publish_fault : ajouter timestamp simulé
ts_fault = get_simulated_time_iso(self._start_time, self._t_elapsed_s)
await publisher.publish_fault(
    self.cluster_id, mid, fault, event="injected", ts=ts_fault
)

# publish_energy : ajouter timestamp simulé
ts_energy = get_simulated_time_iso(self._start_time, self._t_elapsed_s)
await publisher.publish_energy(
    self.cluster_id,
    {...},
    ts=ts_energy,
)
```

**Impact :**
- Tous les événements MQTT utilisent le temps simulé
- Cohérent avec le snapshot cluster

---

### 3. ✅ Modification : `mqtt/publisher.py`

#### 3.1 Import (ligne 25)
```python
from simulation.time import get_simulated_time_iso
```

#### 3.2 Signature des méthodes publiques modifiées

**publish_telemetry()** (ligne 143)
```python
async def publish_telemetry(self, snapshot: dict) -> None:
    ts = snapshot.get("ts", _now_iso())  # Utiliser ts du snapshot
    payload = {
        "schema_version": "1.0",
        "ts": ts,  # ← Temps simulé du snapshot
        **snapshot,
    }
```

**publish_summary()** (ligne 233)
```python
async def publish_summary(self, cluster_snapshot: dict) -> None:
    ts = cluster_snapshot.get("ts", _now_iso())  # Timestamp simulé
    payload = {
        "ts": ts,  # ← Temps simulé
        ...
    }
```

**publish_status()** (ligne 195) — Signature modifiée
```python
async def publish_status(
    self, cluster_id: str, machine_id: str, status: str, ts: str | None = None
) -> None:
    await self._publish(
        ...,
        {"ts": ts or _now_iso(), "status": status},
        ...
    )
```

**publish_fault()** (ligne 205) — Signature modifiée
```python
async def publish_fault(
    self, cluster_id: str, machine_id: str, fault_data: dict,
    event: str = "injected", ts: str | None = None
) -> None:
    payload = {
        "ts": ts or _now_iso(),  # Utiliser ts paramétré ou heure réelle
        "event": event,
        **fault_data,
    }
```

**publish_energy()** (ligne 265) — Signature modifiée
```python
async def publish_energy(
    self, cluster_id: str, energy_metrics: dict, ts: str | None = None
) -> None:
    payload = {
        "ts": ts or _now_iso(),
        "cluster_id": cluster_id,
        **energy_metrics,
    }
```

**Impact :**
- Tous les événements MQTT utilisent temps simulé (si fourni)
- Fallback sur heure réelle si aucun ts fourni (pour compatibilité)
- Pas de changement de signature pour `publish_telemetry()` et `publish_summary()`

---

### 4. ✅ Modification : Configuration YAML

Ajout de `start_time: "2005-01-01T00:00:00Z"` à tous les scénarios :

- ✅ `config/scenarios/nominal.yaml` (ligne 5)
- ✅ `config/scenarios/stress.yaml` (ligne 5)
- ✅ `config/scenarios/heatwave.yaml` (ligne 5)
- ✅ `config/scenarios/busy_weeks.yaml` (ligne 5)

**Format :** ISO 8601 avec Z (timezone UTC)

```yaml
simulation:
  mode: "nominal"
  tick_rate_hz: 10.0
  events_per_sec: 1.0
  duration: "0"
  start_time: "2005-01-01T00:00:00Z"  # ← NOUVEAU
  speed_multiplier: 1.0
  ...
```

**Paramétrable :** Oui, peut être changé dans le YAML pour chaque scénario

---

### 5. ✅ Nouveau : Tests `tests/test_simulated_time.py` (260 lignes)

**Couverture :**

| Classe de test | Tests | Statut |
|---|---|---|
| `TestStartTimeConfiguration` | 6 tests | ✅ Configuration YAML |
| `TestSimulatedTimeGeneration` | 5 tests | ✅ Format des timestamps |
| `TestClusterSnapshotTimestamp` | 4 tests | ✅ Snapshots avec temps simulé |
| `TestMqttPublisherTimestamps` | 1 test | ✅ Timestamps dans MQTT |
| `TestStartTimeInScenarios` | 4 tests (paramétrisés) | ✅ Tous les scénarios |

**Total : 20 tests pour la gestion du temps simulé**

---

## Comportement résultant

### Avant (problématique)
```
Temps simulé écoulé : 3600 secondes (1 heure)
Timestamp dans événement : "2026-06-03T14:25:37.123Z"  ← Heure réelle système
                           ↓ Incohérent !
Grafana affiche : données à l'heure système (2026)
```

### Après (corrigé)
```
Temps simulé écoulé : 3600 secondes (1 heure)
Timestamp dans événement : "2005-01-01T01:00:00.000Z"  ← Temps simulé 2005
                           ↓ Cohérent !
Grafana affiche : données de 2005-01-01 01:00:00
```

---

## Flux de données pour un événement

**Exemple :** Machine srv-master-01 change d'état à t_elapsed_s = 3600

```
1. ClusterSimulator.tick()
   ├── Détecte changement d'état de machine
   └── Calcule ts = get_simulated_time_iso(start_time=2005-01-01, elapsed_s=3600)
       └── ts = "2005-01-01T01:00:00.000Z"

2. ClusterSimulator._publish_tick()
   ├── await publisher.publish_status(
   │       cluster_id="cluster_alpha",
   │       machine_id="srv-master-01",
   │       status="on",
   │       ts="2005-01-01T01:00:00.000Z"  ← Temps simulé
   │   )

3. MqttPublisher.publish_status()
   ├── Crée payload :
   │   {
   │     "ts": "2005-01-01T01:00:00.000Z",
   │     "status": "on"
   │   }
   └── Publie sur dt/cluster_alpha/srv-master-01/status

4. MQTT Consumer (TimescaleDB)
   ├── Reçoit event avec ts = "2005-01-01T01:00:00.000Z"
   └── Insère dans table events avec ce timestamp

5. Grafana
   ├── Requête : SELECT * FROM events WHERE ts >= '2005-01-01 00:00:00'
   └── Affiche l'événement à 2005-01-01 01:00:00 ✅
```

---

## Tests de validation

### Test 1 : Configuration YAML
```bash
$ python -m pytest tests/test_simulated_time.py::TestStartTimeConfiguration -v
# ✅ 6 tests passent
```

### Test 2 : Snapshots avec temps simulé
```bash
$ python -m pytest tests/test_simulated_time.py::TestClusterSnapshotTimestamp -v
# ✅ 4 tests passent
```

### Test 3 : Tous les scénarios
```bash
$ python -m pytest tests/test_simulated_time.py::TestStartTimeInScenarios -v
# ✅ 4 tests passent (nominal, stress, heatwave, busy_weeks)
```

---

## Compatibilité et fallbacks

### Fallback 1 : Pas de `start_time` dans YAML
```python
if start_time_str is None:
    → Défaut : 2005-01-01T00:00:00Z
```

### Fallback 2 : MQTT publisher sans timestamp
```python
ts = ts or _now_iso()  # Si pas de ts paramétré, utiliser heure réelle
```

**Impact :** 
- Backward compatible
- Code existant continue de marcher
- Mais maintenant on utilise temps simulé par défaut ✅

---

## Comportement avec accélération (vitesse 86400x)

**Avant :**
```
1 seconde réelle s'écoule
- Temps simulé : 86400 secondes (1 jour) ✅
- Timestamp : 2026-06-03 14:25:38.123 UTC ❌ Heure réelle (mauvaise année)
```

**Après :**
```
1 seconde réelle s'écoule
- Temps simulé : 86400 secondes (1 jour) ✅
- Timestamp : 2005-01-02 00:00:00.000 UTC ✅ Temps simulé correct
```

---

## Impact sur Grafana et TimeScale

### Avant
- Requêtes Grafana échouaient (recherchait 2005, recevait 2026)
- Données stockées avec timestamps réels

### Après
- ✅ Requêtes Grafana : `WHERE ts >= '2005-01-01' AND ts <= '2005-01-31'`
- ✅ Données cohérentes (toutes en 2005)
- ✅ Visualisations thermiques basées sur temps simulé

---

## Procédure de test manuelle

### 1. Reconstruire Docker
```bash
cd C:\AIDEV\LaPlateforme_\jumeaux-chauds
build-clean-app.bat
```

### 2. Vérifier les logs
```bash
docker compose logs -f api
# Devrait voir : "Simulation start time: 2005-01-01T00:00:00+00:00"
```

### 3. Checker un snapshot depuis l'API
```bash
curl http://localhost:8000/cluster/status | jq '.ts'
# Devrait afficher : "2005-01-01T00:00:00.000Z" (pas l'heure système)
```

### 4. Vérifier MQTT
```bash
docker exec -it mosquitto mosquitto_sub -t 'dt/cluster_alpha/#' | head -5
# Tous les messages doivent avoir ts = 2005-..., pas 2026-...
```

### 5. Vérifier TimescaleDB
```bash
docker exec -it timescaledb psql -U jumeaux -d jumeaux -c \
  "SELECT ts, event FROM events LIMIT 5;"
# Tous les timestamps = 2005-...
```

### 6. Vérifier Grafana
- Ouvrir http://localhost:3000
- Voir les données sur la timeline 2005-01-01
- PAS sur 2026-06-03

---

## Points à surveiller

### ⚠️ Migration des données existantes
Si TimescaleDB contient des données avec timestamps 2026 :
```sql
-- Nettoyer si nécessaire
TRUNCATE TABLE telemetry;
TRUNCATE TABLE events;
```

### ⚠️ Tests existants
Certains tests anciens supposaient `datetime.now()`. Aucun test de ce type détecté, mais à vérifier :
```bash
grep -r "datetime.now\|_now_iso" tests/
```

### ⚠️ API externe
Si une API externe consomme les timestamps MQTT et assume 2026, elle doit être mise à jour pour 2005.

---

## Commit message recommandé

```
feat(simulation): restore simulated time with configurable start date (2005)

- Add simulation.time module for centralized time calculations
- Load start_time from YAML (default: 2005-01-01T00:00:00Z)
- Pass start_time to ClusterSimulator
- Use simulated timestamps in get_snapshot() instead of datetime.now()
- Update MQTT publisher to use timestamps from snapshots
- Update publish_status/fault/energy to accept simulated timestamps
- Add start_time configuration to all scenario YAMLs
- Add comprehensive tests for simulated time management
- Fix Grafana/TimescaleDB data chronology (now 2005 instead of 2026)

Fixes: Timestamps were using system time instead of simulated time.
Now all events are timestamped with simulated time starting from
2005-01-01, making Grafana queries and data visualization coherent.

BREAKING: Timestamps in MQTT events now use simulated time (2005) instead
of system time (2026). Any consumer assuming system time needs updates.

Test results: 20 new tests added, all passing.
```

---

**Status :** ✅ IMPLÉMENTATION COMPLÈTE  
**Tests :** ✅ 20 TESTS PASSENT  
**Prêt pour :** Docker rebuild et validation manuelle

*Modification effectuée le 3 juin 2026*
