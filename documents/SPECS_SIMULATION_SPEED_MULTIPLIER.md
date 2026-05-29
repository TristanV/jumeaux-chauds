# Spécifications — Contrôle de vitesse de simulation

**Document :** Spécifications techniques pour l'implémentation du contrôle de vitesse de simulation  
**Auteur :** Tristan Vanrullen  
**Date :** 29 mai 2026  
**Phase :** 8.4 — Extensions pédagogiques  
**Statut :** 📋 À développer

---

## 1. Objectif

Permettre d'**accélérer ou ralentir** la production de données de simulation pour :
- Générer de **grandes quantités de données** pour entraînement ML (objectif principal)
- Tester les comportements long-terme (dérives, usure) sans attendre des jours/semaines
- Étudier l'impact de différents scénarios sur périodes élargies (mois, années)

**Limitation :** Éviter la surchauffe de la machine exécutant la simulation lors d'accélération.

---

## 2. Concept

Introduire un paramètre **`simulation_speed_multiplier`** qui représente le ratio :
```
vitesse_simulation = 1 seconde_réelle × simulation_speed_multiplier secondes_simulées
```

### Valeurs prédéfinies

| Nom | Multiplier | Temps réel → Temps simulé | Cas d'usage |
|-----|-----------|---------------------------|------------|
| **Real-time** | 1.0 | 1 s → 1 s | Monitoring en direct |
| **1 min/sec** | 60 | 1 s → 1 min | Accélération modérée |
| **1 hour/sec** | 3600 | 1 s → 1 h | Étude jour complet en 24s |
| **1 day/sec** | 86400 | 1 s → 1 jour | Étude mois en 30s |

### Exemple

**Scénario :** Produire 30 jours de données thermiques à vitesse "1 jour/sec"
- Temps réel : 30 secondes
- Données générées : 30 jours × 86400 s/jour × 1 tick/s = 2,592,000 snapshots (si tick_rate_hz=1)
- Taille MQTT : ~2,592,000 snapshots × 5 KB ≈ 13 GB (+ compression réelle)
- CPU : impact modéré (voir § 5)

---

## 3. Architecture

### 3.1 Configuration YAML

Ajouter au `config/base.yaml` :

```yaml
simulation:
  # ... sections existantes ...
  
  # Phase 8.4 — Contrôle de vitesse
  speed_multiplier: 1.0              # défaut : real-time (1s/s)
  # Valeurs prédéfinies :
  # - 1.0    : real-time (1 s → 1 s)
  # - 60.0   : 1 min par sec
  # - 3600.0 : 1 hour par sec
  # - 86400.0: 1 day par sec
  
  # Throttling pour éviter la surchauffe CPU
  cpu_throttle_enabled: true         # active le throttle
  cpu_throttle_target_hz: 100.0      # freq effective véritable (ticks/s réels)
  # Calcul : tick_interval_s_real = 1.0 / cpu_throttle_target_hz
```

### 3.2 Moteur de simulation (cluster.py)

**Modification :** Adapter la boucle `run()` pour respecter le multiplier et le throttle.

```python
class ClusterSimulator:
    def __init__(self, config: dict):
        # ... existant ...
        self._speed_multiplier: float = float(
            config["simulation"].get("speed_multiplier", 1.0)
        )
        self._cpu_throttle_enabled: bool = config["simulation"].get(
            "cpu_throttle_enabled", True
        )
        self._cpu_throttle_target_hz: float = float(
            config["simulation"].get("cpu_throttle_target_hz", 100.0)
        )
        
        # Tick réel en secondes (avant application du multiplier)
        self._tick_interval_s_real: float = 1.0 / self._tick_rate_hz
        
        # Intervalle de throttle CPU
        if self._cpu_throttle_enabled:
            self._throttle_interval_s: float = 1.0 / self._cpu_throttle_target_hz
        else:
            self._throttle_interval_s: float = 0.0  # pas de throttle
    
    async def run(self, publisher=None, ws_manager=None):
        """Boucle de simulation avec speed_multiplier et throttling."""
        self._running = True
        last_throttle_time = time.time()
        
        while self._running:
            # --- Tick de simulation (accéléré)
            tick_start = time.time()
            self._tick()  # exécute un tick
            tick_elapsed = time.time() - tick_start
            
            # --- Accumulation de temps simulé
            self._t_elapsed_s += self._tick_interval_s_real * self._speed_multiplier
            
            # --- Publication MQTT / WebSocket (throttlée)
            now = time.time()
            if (now - last_throttle_time) >= self._throttle_interval_s:
                if publisher:
                    await publisher.publish_telemetry(...)
                if ws_manager:
                    ws_manager.broadcast(...)
                last_throttle_time = now
            
            # --- Sleep si nécessaire (throttle CPU)
            if self._cpu_throttle_enabled:
                sleep_time = self._throttle_interval_s - (now - tick_start)
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)
```

### 3.3 API FastAPI

Ajouter deux endpoints :

#### GET `/simulation/speed`
```json
Response 200:
{
  "speed_multiplier": 3600.0,
  "speed_name": "1 hour/sec",
  "cpu_throttle_enabled": true,
  "cpu_throttle_target_hz": 100.0,
  "real_tick_rate_hz": 100.0,
  "simulated_tick_rate_hz": 360000.0
}
```

#### PUT `/simulation/speed`
```json
Request:
{
  "speed_multiplier": 86400.0
}
or
{
  "speed_name": "1 day/sec"
}

Response 200:
{
  "speed_multiplier": 86400.0,
  "speed_name": "1 day/sec",
  "message": "Speed multiplier changed to 1 day/sec"
}

Response 400:
{
  "detail": "Invalid speed_multiplier (must be > 0)"
}
```

#### Changement à chaud

Le changement de vitesse doit :
- S'appliquer immédiatement (sans redémarrer la simulation)
- Affecter uniquement les **nouveaux** snapshots
- **Ne pas** perdre l'historique d'énergie/coût/temps_écoulé accumulé

Implémentation :

```python
async def set_simulation_speed(speed_multiplier: float):
    """Change vitesse à chaud."""
    if speed_multiplier <= 0:
        raise ValueError("speed_multiplier must be > 0")
    
    simulator = get_cluster()
    simulator._speed_multiplier = speed_multiplier
    
    logger.info(f"Speed changed to {speed_multiplier}x")
    return {
        "speed_multiplier": speed_multiplier,
        "speed_name": get_speed_name(speed_multiplier),
        "message": f"Speed changed to {get_speed_name(speed_multiplier)}"
    }
```

### 3.4 Dashboard Streamlit

Ajouter dans l'onglet "Simulation" un **panneau de contrôle vitesse** :

```
┌─────────────────────────────────────────┐
│ ⚙️ SIMULATION SPEED CONTROL              │
├─────────────────────────────────────────┤
│                                          │
│ Current speed: [dropdown]                │
│   ○ 1x (Real-time)                      │
│   ○ 60x (1 min/sec)                     │
│   ● 3600x (1 hour/sec)                  │
│   ○ 86400x (1 day/sec)                  │
│   ○ Custom: [text input] x              │
│                                          │
│ CPU Throttle:  [toggle] enabled         │
│ Target Hz:     [slider] 50 - 500 Hz     │
│                                          │
│ 📊 METRICS                               │
│   Real time elapsed: 1m 23s              │
│   Simulated time: 23 days 5h 30m         │
│   Data points: 1,234,567 snapshots       │
│   Est. data size: 6.2 GB (compressed)    │
│                                          │
│ [Export to CSV] [Reset Time]             │
└─────────────────────────────────────────┘
```

#### Composants

1. **Dropdown prédéfini** : 4 vitesses + Custom
2. **Toggle CPU Throttle** : activer/désactiver
3. **Slider Target Hz** : 50 à 500 Hz (défaut 100)
4. **Métriques en direct** :
   - Temps réel écoulé (depuis démarrage)
   - Temps simulé accumulé (formaté lisiblement)
   - Nombre total de snapshots
   - Estimation taille données (basée sur snapshots × 5 KB/snapshot)
5. **Boutons** :
   - **Export CSV** : sauve snapshots accumulés dans CSV
   - **Reset Time** : remet `t_elapsed_s` à 0 et `energy_kwh_total` à 0

#### Implémentation (pseudocode)

```python
st.subheader("⚙️ Simulation Speed Control")

col1, col2 = st.columns(2)

with col1:
    speed_name = st.selectbox(
        "Speed preset",
        ["1x (Real-time)", "60x (1 min/sec)", "3600x (1 hour/sec)", 
         "86400x (1 day/sec)", "Custom"],
        index=2
    )
    
    if speed_name == "Custom":
        speed_mult = st.number_input("Custom multiplier", value=1.0, min_value=0.1)
    else:
        speed_mult = {"1x": 1.0, "60x": 60.0, "3600x": 3600.0, "86400x": 86400.0}[speed_name.split()[0]]
    
    if st.button("Apply Speed"):
        requests.put("http://localhost:8000/simulation/speed", 
                     json={"speed_multiplier": speed_mult})
        st.success(f"Speed set to {speed_mult}x")

with col2:
    throttle_enabled = st.checkbox("CPU Throttle", value=True)
    target_hz = st.slider("Target Hz", min_value=50, max_value=500, value=100)

# Afficher métriques
status = requests.get("http://localhost:8000/cluster/status").json()
speed_info = requests.get("http://localhost:8000/simulation/speed").json()

col1, col2 = st.columns(2)
with col1:
    st.metric("Simulated Time", format_duration(status.get("t_elapsed_s", 0)))
    st.metric("Data Points", status.get("snapshot_count", 0))

with col2:
    st.metric("Real Time (since start)", format_duration(get_real_elapsed()))
    est_size_gb = status.get("snapshot_count", 0) * 5e-6  # 5 KB per snapshot
    st.metric("Est. Data Size", f"{est_size_gb:.2f} GB")
```

---

## 4. Modifications par composant

### 4.1 `simulation/cluster.py`

- Ajouter champs `_speed_multiplier`, `_cpu_throttle_enabled`, `_cpu_throttle_target_hz`
- Modifier boucle `run()` :
  - Appliquer multiplier à `_t_elapsed_s` chaque tick
  - Throttler les publications (MQTT, WebSocket) selon CPU throttle
  - Ajouter méthode `set_speed_multiplier()`

### 4.2 `api/routes/simulation.py`

- Ajouter endpoint `GET /simulation/speed` → infos vitesse
- Ajouter endpoint `PUT /simulation/speed` → changement vitesse
- Ajouter endpoint `POST /simulation/speed/reset` → reset temps écoulé + énergie

### 4.3 `api/models.py`

Ajouter schémas Pydantic :

```python
class SpeedInfo(BaseModel):
    speed_multiplier: float
    speed_name: str
    cpu_throttle_enabled: bool
    cpu_throttle_target_hz: float
    real_tick_rate_hz: float
    simulated_tick_rate_hz: float

class SpeedChangeRequest(BaseModel):
    speed_multiplier: float | None = None
    speed_name: str | None = None
```

### 4.4 `dashboard/app.py`

- Ajouter panneau contrôle vitesse dans onglet "Simulation"
- Afficher métriques en direct (temps simulé, snapshots, taille)
- Boutons Export CSV et Reset Time

### 4.5 `config/base.yaml`

Ajouter section `simulation.speed_multiplier` et throttle

---

## 5. Gestion thermique et surchauffe CPU

### Problème

À vitesse élevée (86400x), la simulation génère :
- Ticks en continu à ~1000+ ticks/s (si pas throttle)
- Publication MQTT massive (→ broker surchargé)
- WebSocket broadcast trop fréquent (→ réseau saturé)
- CPU : 100% utilisation possible

### Solution : CPU Throttling

**Principe :** Limiter la **fréquence réelle de publication**, pas le nombre de ticks.

```
Ticks/sec réels = cpu_throttle_target_hz (ex: 100)
Ticks/sec simulés = cpu_throttle_target_hz × speed_multiplier
```

**Exemple :**

| Config | Ticks réels/s | Ticks simulés/s | Temps pour 1 jour |
|--------|---------------|-----------------|------------------|
| Real-time, throttle=100 Hz | 100 | 100 | 86400 s = 24 h |
| 1h/sec, throttle=100 Hz | 100 | 360000 | 24 s |
| 1day/sec, throttle=100 Hz | 100 | 8640000 | 2.4 s |

### Défaillance thermique modérée

À vitesse très élevée, même avec throttle :
- CPU peut rester ~60-80% utilisé (sur multi-cœurs)
- Mémoire stable (snapshots en circulation, pas accumulés)
- Réseau : dépend du broker MQTT (peut valider ~1000 msg/s)

**Recommandation :**
- Pour production long-terme : `cpu_throttle_target_hz = 50` (plus conservateur)
- Pour tests rapides : `cpu_throttle_target_hz = 200` (plus agressif)

---

## 6. Export de données

### Besoin

Produire de grandes quantités de données pour **entraînement ML** en format standard (CSV, Parquet).

### Endpoint à ajouter

```
POST /simulation/export
{
  "format": "csv" | "parquet",
  "output_path": "/tmp/data_export.csv",
  "columns": ["timestamp", "machine_id", "temperature_c", "power_w", "status"]
}

Response:
{
  "format": "csv",
  "rows": 1234567,
  "bytes": 123456789,
  "output_path": "/tmp/data_export.csv"
}
```

### Implémentation

Stocker chaque snapshot dans buffer circulaire (ex: 100K derniers snapshots) :

```python
from collections import deque

class ClusterSimulator:
    def __init__(self, config):
        # ... existant ...
        self._snapshot_buffer = deque(maxlen=100000)  # circulaire
    
    async def _tick(self):
        # ... calcul snapshot ...
        snapshot = self.get_snapshot()
        self._snapshot_buffer.append(snapshot)
        # ... publication MQTT/WS ...
```

Export :

```python
async def export_snapshots(format: str = "csv", path: str = None):
    """Exporte snapshots du buffer vers fichier."""
    import pandas as pd
    
    rows = []
    for snapshot in get_cluster()._snapshot_buffer:
        for machine_id, machine_data in snapshot["machines"].items():
            rows.append({
                "timestamp": snapshot["ts"],
                "machine_id": machine_id,
                "temperature_c": machine_data["sensors"]["temp_cpu"]["temp_c"],
                "power_w": machine_data["power_w"],
                "status": machine_data["status"],
            })
    
    df = pd.DataFrame(rows)
    
    if format == "csv":
        df.to_csv(path, index=False)
    elif format == "parquet":
        df.to_parquet(path)
    
    return {
        "format": format,
        "rows": len(df),
        "bytes": len(df.to_csv() if format == "csv" else df.to_parquet()),
        "output_path": path
    }
```

---

## 7. Tests

### Cas de test unitaires

| Cas | Entrée | Sortie attendue |
|-----|--------|-----------------|
| Vitesse par défaut | config sans speed_multiplier | speed_multiplier = 1.0 |
| Vitesse 60x | config speed_multiplier=60 | _speed_multiplier=60, t_elapsed augmente 60x plus vite |
| Vitesse 86400x | config speed_multiplier=86400 | idem |
| Changement à chaud | PUT /simulation/speed {3600} | speed change, no restart, energy intact |
| Throttle CPU | cpu_throttle=true, target=100 Hz | publication MQTT/WS à ~100 Hz max |
| Export CSV | POST /export {csv} | fichier .csv avec N snapshots, colonnes valides |

### Cas d'intégration

```bash
# Test 1 : Générer 30 jours en 30 secondes
curl -X PUT http://localhost:8000/simulation/speed \
  -d '{"speed_multiplier": 86400}' \
  -H "Content-Type: application/json"

sleep 30

curl http://localhost:8000/simulation/speed

# Vérifier : t_elapsed_s ≈ 30 * 86400 = 2,592,000 s = 30 jours
```

---

## 8. Migration et branche Git

**Branche :** `feature/phase-8-4-speed-multiplier`

**Étapes :**

1. Créer branche : `git checkout -b feature/phase-8-4-speed-multiplier`
2. Modifier `config/base.yaml` + tous les composants (§ 4)
3. Écrire tests dans `tests/test_speed_multiplier.py`
4. Valider : `pytest tests/test_speed_multiplier.py -v`
5. Commit & push
6. Merge vers `main` après review

---

## 9. Impacts identifiés

### Impact positif

✅ Production de données ML massif possible en secondes  
✅ Test long-terme (mois/ans) en minutes  
✅ Économie temps développement (itération rapide)  

### Impacts négatifs à mitiger

⚠️ CPU élevé → mitigé par throttle  
⚠️ Broker MQTT peut saturer → throttle + buffer circulaire  
⚠️ Mémoire si buffer snapshots trop grand → limiter à 100K max  

---

## 10. Timeline estimée

| Tâche | Durée estimée | Notes |
|-------|---------------|-------|
| Modification cluster.py + API | 2-3 h | boucle asyncio, throttle |
| Intégration Streamlit | 1-2 h | widgets, appels API |
| Tests unitaires + intégration | 1-2 h | 10-15 tests |
| Documentation + review | 1 h | exemples d'usage |
| **Total** | **5-8 h** | Développable sur 1 jour |

---

## Références

- **RFC 3339** (timestamps ISO) : déjà implémenté
- **asyncio throttling** : pattern standard Python
- **Pydantic v2** : schémas API
- **Pandas/Parquet** : optional, pour export ML

---

*Tristan Vanrullen — La Plateforme, Marseille — 29 mai 2026*
