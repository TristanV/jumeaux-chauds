# Spécifications — Transitions d'état des machines du simulateur

> **Auteur :** Tristan Vanrullen  
> **Date :** 5 juin 2026  
> **Version :** 1.0  
> **Fichiers de référence :** `simulation/machine.py`, `config/base.yaml`

---

## 1. Vue d'ensemble des statuts

Chaque machine du simulateur est à tout instant dans l'un des trois états suivants :

| Statut | Signification | Couleur dashboard |
|--------|--------------|-------------------|
| `on` | Machine en fonctionnement normal | 🟢 Vert |
| `degraded` | Machine en fonctionnement dégradé (température critique) | 🟠 Orange |
| `off` | Machine éteinte (volontaire ou protection thermique) | ⚫ Gris |

---

## 2. Matrice des transitions d'état

Le tableau ci-dessous liste toutes les transitions possibles. Chaque cellule indique les **conditions exactes** qui déclenchent la transition.

| État d'origine → État d'arrivée | `on` | `degraded` | `off` |
|---|---|---|---|
| **`on`** | *(état stable)* | `T ≥ t_shutdown_c × 0.95` (surchauffe partielle, automatique) | `T ≥ t_shutdown_c` (surchauffe complète, automatique) **ou** `power_off()` (manuel) |
| **`degraded`** | `T < t_shutdown_c × 0.95` pendant `recovery_delay_s` secondes consécutives (automatique) | *(état stable)* | `T ≥ t_shutdown_c` (surchauffe complète, automatique) |
| **`off`** | `T ≤ t_restart_c` après extinction par surchauffe (automatique) **ou** `power_on()` si `T ≤ t_restart_c` (manuel) | *(impossible)* | *(état stable)* |

### Notes importantes

- La transition `off → degraded` est **impossible** : une machine éteinte ne peut pas entrer directement en mode dégradé.
- La transition `degraded → off` **est possible** : si la température continue de monter en mode dégradé jusqu'à `t_shutdown_c`, la machine s'éteint par protection thermique.
- `power_on()` manuel **échoue** (retourne `False`) si `T > t_restart_c` — l'opérateur doit attendre le refroidissement.

---

## 3. Description détaillée de chaque transition

### 3.1 `on → degraded` (surchauffe partielle, automatique)

**Condition :** `temperature_c ≥ t_shutdown_c × 0.95`

**Variable de déclenchement :** `temperature_c` — température interne de la machine, calculée par intégration numérique du modèle thermique du 1er ordre à chaque tick.

**Mécanisme simulateur :**
À chaque appel de `machine.tick()`, après `_integrate_thermal()`, le simulateur évalue :
```python
if temperature_c >= t_shutdown_c * 0.95 and status == "on":
    status = "degraded"
    last_status_cause = "overheat_partial"
```

**Exemple (rôle master) :** `t_shutdown_c = 90°C` → seuil dégradé = **85.5°C**

**Cause MQTT :** `"overheat_partial"`

---

### 3.2 `on → off` ou `degraded → off` (surchauffe complète, automatique)

**Condition :** `temperature_c ≥ t_shutdown_c`

**Variable de déclenchement :** `temperature_c` — même variable que 3.1, seuil supérieur.

**Mécanisme simulateur :**
```python
if temperature_c >= t_shutdown_c:
    status = "off"
    _shutdown_by_overheat = True
    last_status_cause = "overheat"
```
Le flag `_shutdown_by_overheat = True` distingue cet arrêt d'un arrêt volontaire et autorise le redémarrage automatique ultérieur.

**Exemple (rôle master) :** seuil shutdown = **90°C**, seuil worker = **88°C**

**Cause MQTT :** `"overheat"`

---

### 3.3 `on → off` ou `degraded → off` (arrêt manuel)

**Condition :** appel explicite de `machine.power_off()` via l'API REST (`POST /machines/{id}/power {"action": "off"}`) ou le dashboard.

**Mécanisme simulateur :**
```python
def power_off():
    status = "off"
    _shutdown_by_overheat = False   # ← distinction clé
    last_status_cause = "manual_off"
```

Le flag `_shutdown_by_overheat = False` **empêche tout redémarrage automatique** : la machine restera `off` jusqu'à un `power_on()` explicite.

**Cause MQTT :** `"manual_off"`

---

### 3.4 `degraded → on` (récupération thermique automatique)

**Condition :** `temperature_c < t_shutdown_c × 0.95` pendant une durée ≥ `recovery_delay_s` secondes consécutives.

**Mécanisme simulateur :**
```python
elif status == "degraded":
    _time_since_overheat_s += dt
    if _time_since_overheat_s >= recovery_delay_s:
        status = "on"
        last_status_cause = "degraded_recovery"
```

**Valeur par défaut :** `recovery_delay_s = 120s` (configurable dans `scenarios/nominal.yaml` et `stress.yaml`)

**Cause MQTT :** `"degraded_recovery"`

---

### 3.5 `off → on` (redémarrage automatique après surchauffe)

**Condition :** `temperature_c ≤ t_restart_c` **et** `_shutdown_by_overheat == True`

**Mécanisme simulateur :**
Pendant que la machine est `off` par surchauffe, le refroidissement passif est simulé à chaque tick (sans consommation électrique). Dès que :
```python
if temperature_c <= t_restart_c and _shutdown_by_overheat:
    status = "on"
    _shutdown_by_overheat = False
    last_status_cause = "thermal_recovery"
```

**Hystérésis thermique :** `t_restart_c < t_shutdown_c` garantit que la machine ne s'allume pas immédiatement après s'être éteinte. Exemple (master) : éteinte à 90°C, redémarre à **55°C**.

**Cause MQTT :** `"thermal_recovery"`

---

### 3.6 `off → on` (démarrage manuel)

**Condition :** appel de `machine.power_on()` **et** `temperature_c ≤ t_restart_c`

**Mécanisme simulateur :**
```python
def power_on():
    if temperature_c > t_restart_c:
        return False   # Refus : trop chaud
    status = "on"
    _shutdown_by_overheat = False
    last_status_cause = "manual_on"
    return True
```

**Cause MQTT :** `"manual_on"`

**Code HTTP :** `409 Conflict` si `T > t_restart_c` (endpoint `POST /machines/{id}/power`)

---

## 4. Matrice du comportement par état

Le tableau ci-dessous décrit le comportement des composants physiques de la machine dans chacun des trois états.

| Composant | `on` | `degraded` | `off` |
|-----------|------|------------|-------|
| **CPU / charge** | Actif — `load_factor` fourni par `ScenarioEngine` | Actif — même `load_factor` (pas de throttling CPU dans le simulateur actuel) | Inactif — `load_factor = 0`, `power_w = 0` |
| **Consommation électrique** | `P = P_idle + (P_max - P_idle) × load^alpha` | Identique à `on` | `P = 0 W` |
| **Accumulation d'énergie** | Oui — `energy_kwh_cumulated += delta_kwh` | Oui | Non |
| **Ventilateurs** | Actifs — mode `auto` (régulation proportionnelle T - T_amb) ou `manual` | Actifs — même comportement qu'en `on` | Arrêtés — `fan_rpm = 0` (refroidissement passif uniquement) |
| **Modèle thermique** | Intégration complète : chaleur CPU + refroidissement fans | Identique à `on` | Refroidissement passif uniquement : `q_in = 0`, `tau = tau_max` (fans à 0) |
| **Capteurs de température** | Actifs avec bruit gaussien et biais de sonde | Actifs | Actifs (la température redescend vers `T_amb`) |
| **Pannes actives** | Peuvent être injectées et expirer | Peuvent être injectées et expirer | Expirent mais ne peuvent pas être injectées (le FaultScheduler tourne toujours) |
| **Publication MQTT télémétrie** | Oui | Oui | Oui (snapshot publié avec `status: "off"`, `power_w: 0`) |

### Remarque sur le mode `degraded`

Le mode `degraded` est une **alarme de surveillance** : la machine continue de fonctionner normalement (CPU actif, même consommation, mêmes fans). Le simulateur ne throttle pas le CPU ni ne réduit la charge en mode dégradé. C'est intentionnel pour modéliser une situation réaliste où la production continue malgré une alerte thermique.

---

## 5. Transitions automatiques vs manuelles

### 5.1 Une machine peut-elle se rallumer automatiquement après une extinction manuelle ?

**Non.** Le flag `_shutdown_by_overheat` en est le mécanisme clé :

- Extinction **manuelle** → `_shutdown_by_overheat = False` → le bloc de redémarrage automatique (`off → on` si `T ≤ t_restart_c`) n'est jamais évalué → la machine reste `off` indéfiniment.
- Extinction **par surchauffe** → `_shutdown_by_overheat = True` → redémarrage automatique dès refroidissement.

### 5.2 Situations intéressantes

**Boucle surchauffe infinie :** Si `t_restart_c` est proche de `t_shutdown_c × 0.95` et que la charge reste élevée après redémarrage, la machine peut osciller : `on → degraded → off → on → degraded...`. Ce comportement est physiquement réaliste (serveur qui s'emballe thermiquement sous forte charge).

**Blocage en `degraded` :** Si la charge reste durablement élevée et que les fans ne suffisent pas à refroidir sous le seuil `t_shutdown_c × 0.95`, la machine reste en `degraded` indéfiniment — puis finit par atteindre `t_shutdown_c` et s'éteint.

**Extinction manuelle pendant surchauffe :** Si un opérateur éteint manuellement une machine qui était en train de surchauffer (`_shutdown_by_overheat` aurait été mis à `True`), l'appel `power_off()` force `_shutdown_by_overheat = False` — la machine ne redémarrera pas automatiquement même après refroidissement.

**Tentative de rallumage trop tôt :** `power_on()` retourne `False` et l'API répond `409` si la machine est encore trop chaude. L'opérateur doit attendre que `T ≤ t_restart_c`.

**Scénario heatwave :** La température ambiante `T_amb` monte progressivement. Les seuils `t_shutdown_c` et `t_restart_c` sont **absolus** (pas relatifs à `T_amb`). Dans un scénario de vague de chaleur, `T_amb` peut approcher `t_restart_c`, ce qui empêche le redémarrage automatique même après extinction par surchauffe.

---

## 6. Télémétries associées aux transitions

### 6.1 Publications MQTT lors d'une transition

À chaque changement de statut détecté dans `cluster.py` (comparaison `_prev_status[mid] != current_status`), le publisher envoie :

**Topic :** `dt/{cluster_id}/{machine_id}/status`  
**QoS :** 1 (au moins une fois)  
**Payload :**
```json
{
  "ts": "2005-03-15T14:23:01Z",
  "status": "off",
  "cause": "overheat"
}
```

**Valeurs possibles de `cause` :**

| `cause` | Transition | Déclencheur |
|---------|-----------|-------------|
| `"overheat"` | `on/degraded → off` | `T ≥ t_shutdown_c` (automatique) |
| `"overheat_partial"` | `on → degraded` | `T ≥ t_shutdown_c × 0.95` (automatique) |
| `"thermal_recovery"` | `off → on` | `T ≤ t_restart_c` après overheat (automatique) |
| `"degraded_recovery"` | `degraded → on` | `recovery_delay_s` écoulé sous le seuil (automatique) |
| `"manual_off"` | `on/degraded → off` | `power_off()` utilisateur |
| `"manual_on"` | `off → on` | `power_on()` utilisateur |
| `"unknown"` | toute | Cause non renseignée (rétro-compatibilité) |

### 6.2 Stockage dans TimescaleDB

Les événements `status_change` sont insérés dans la table `events` :

```sql
-- Structure (schema.sql Phase 8.11)
CREATE TABLE events (
    ts          TIMESTAMPTZ NOT NULL,
    cluster_id  TEXT        NOT NULL,
    machine_id  TEXT        NOT NULL,
    event_type  TEXT        NOT NULL,  -- 'fault' | 'status_change'
    cause       TEXT,                  -- voir valeurs ci-dessus
    payload     JSONB
);
```

### 6.3 Comptage des extinctions et passages en mode dégradé

**Comptage par cause dans TimescaleDB :**
```sql
-- Nombre d'extinctions par surchauffe par machine
SELECT machine_id, COUNT(*) AS nb_extinctions_overheat
FROM events
WHERE event_type = 'status_change'
  AND cause = 'overheat'
  AND $__timeFilter(ts)
GROUP BY machine_id
ORDER BY nb_extinctions_overheat DESC;

-- Nombre de passages en mode dégradé
SELECT machine_id, COUNT(*) AS nb_degraded
FROM events
WHERE event_type = 'status_change'
  AND cause = 'overheat_partial'
  AND $__timeFilter(ts)
GROUP BY machine_id;

-- Toutes les causes, par machine
SELECT machine_id, cause, COUNT(*) AS nb
FROM events
WHERE event_type = 'status_change'
  AND $__timeFilter(ts)
GROUP BY machine_id, cause
ORDER BY machine_id, nb DESC;
```

### 6.4 Comptage via d'autres consommateurs

| Consommateur | Méthode | Granularité |
|---|---|---|
| **TimescaleDB** (profil storage) | Requête SQL sur `events` (voir 6.3) | Historique complet |
| **Grafana** | Panel table ou stat sur requête SQL `events` | Fenêtre de temps configurable |
| **API REST** | `GET /cluster/status` → champ `faults` par machine dans le snapshot (pannes actives uniquement, pas historique) | Temps réel |
| **WebSocket** | Snapshot JSON à `events_per_sec` Hz — field `faults` par machine | Temps réel |
| **MQTT subscriber** | Topic `dt/{cluster}/+/status` — comptage côté abonné sur `cause` | Temps réel + agrégation custom |
| **Data warehouse (stockage froid)** | Consommer le topic MQTT `dt/#` ou l'API `/cluster/status` périodiquement → incrémenter compteurs dans une table externe | Long terme |

**Limitation actuelle :** il n'existe pas de compteur cumulé `overheat_count` ou `fault_count` dans le snapshot temps réel (API/WebSocket). Seule la table `events` de TimescaleDB permet un comptage historique. Pour un comptage temps réel sans TimescaleDB, il faudrait ajouter ces compteurs dans `MachineSimulator` et les exposer dans le snapshot.

---

## 7. Paramètres de configuration YAML

| Paramètre | Rôle | Valeur master | Valeur worker | Configurable |
|---|---|---|---|---|
| `t_shutdown_c` | Seuil d'extinction automatique (°C) | 90.0 | 88.0 | Par machine ou par rôle |
| `t_restart_c` | Seuil de redémarrage (°C) — hystérésis | 55.0 | 50.0 | Par machine ou par rôle |
| `recovery_delay_s` | Durée minimale sous le seuil dégradé avant retour `on` (s) | 120 | 120 | Par scénario |
| `ambient_temp_c` | Température ambiante — limite basse de refroidissement (°C) | 22.0 | 22.0 | Par rôle |
| `tau_max_s` | Constante de temps thermique sans fans (s) | 90.0 | 100.0 | Par rôle |
| `k_cool_rpm_factor` | Coefficient d'efficacité des fans sur le refroidissement | 2.0 | 2.0 | Par rôle |

Le seuil de passage en `degraded` n'est pas configurable directement : il est calculé dynamiquement à `t_shutdown_c × 0.95`.
