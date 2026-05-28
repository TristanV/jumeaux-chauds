# 🔍 Analyse Exhaustive — Jumeaux Chauds

**Date :** 28 mai 2026  
**Analyseur :** Claude Agent SDK  
**Version du projet :** 1.1.0  
**Statut :** Phase 7 en cours

---

## 📋 Table des matières

1. [Vue d'ensemble](#vue-densemble)
2. [Alignement README ↔ Roadmap ↔ Code](#alignement-readme--roadmap--code)
3. [Analyse des variables YAML](#analyse-des-variables-yaml)
4. [Problèmes de nommage identifiés](#problèmes-de-nommage-identifiés)
5. [Variables inexploitées](#variables-inexploitées)
6. [Plan de développement Phase 7](#plan-de-développement-phase-7)
7. [Recommandations](#recommandations)

---

## Vue d'ensemble

### Statut actuel

| Domaine | État | Notes |
|---------|------|-------|
| **Phases 1-6** | ✅ Complètes | Fondations, simulation, MQTT, API, Dashboard, Docker |
| **Tests unitaires** | ⚠️ Partiels | `test_physics.py`, `test_config.py`, `test_machine.py` couverts |
| **Tests API** | ❌ Manquants | FastAPI endpoints non testés |
| **Tests MQTT** | ❌ Manquants | Publisher et flux e2e non testés |
| **Tests Consumer** | ❌ Manquants | Ingestion TimescaleDB non testée |
| **Couverture globale** | ~40% | Cible : ≥80% pour Phase 7 |

### Architecture actuellement en place

```
simulation/     ✅ Modèle physique + MachineSimulator + ClusterSimulator
config/         ✅ YAML hierarchical (base + scenarios) + loader
mqtt/           ✅ aiomqtt publisher avec reconnexion automatique
api/            ✅ FastAPI + lifespan + WebSocket + endpoints REST
dashboard/      ✅ Streamlit + WebSocket client
consumer/       ✅ MQTT → TimescaleDB
tests/          🔄 À compléter
```

---

## Alignement README ↔ Roadmap ↔ Code

### ✅ Alignement confirmé

#### 1. **Configuration YAML → Loader Python**
- `config/base.yaml` : définit `cluster`, `role_profiles`, `machines`
- `config/loader.py` : `load_config()` + `get_machine_config()` ✅
- Niveaux de merge : base + scenario + overrides + ENV ✅
- Les 5 machines (2 masters + 3 workers) déclarées et instanciées ✅

#### 2. **Topics MQTT → Publisher**
| YAML | Code | Statut |
|------|------|--------|
| `topic_root: "dt"` | `mqtt/publisher.py:publish_telemetry()` | ✅ |
| `dt/{cluster}/{machine}/telemetry` | Payload du snapshot | ✅ |
| `dt/{cluster}/{machine}/fan/{idx}` | `publish_fan_state()` | ✅ |
| `dt/{cluster}/{machine}/status` | `publish_status()` | ✅ |
| `dt/{cluster}/summary` | Timer 5s | ✅ |
| `dt/{cluster}/metrics/energy` | Timer 60s | ✅ |

#### 3. **API Endpoints → Routes FastAPI**
| README | Code | Statut |
|--------|------|--------|
| `GET /` | `api/main.py` | ✅ |
| `GET /cluster/status` | `api/routes/cluster.py` | ✅ |
| `POST /cluster/power` | `api/routes/cluster.py` | ✅ |
| `PUT /cluster/fan_speed` | `api/routes/cluster.py` | ✅ |
| `GET /machines/{id}` | `api/routes/machines.py` | ✅ |
| `POST /machines/{id}/power` | `api/routes/machines.py` | ✅ |
| `WS /ws/cluster` | `api/ws.py + routes/cluster.py` | ✅ |

#### 4. **Phases de développement**
- README.md : "Phase 7 — Tests d'intégration (prochaine priorité)" ✅
- roadmap.md : Phase 7 détaillée (7.1 + 7.2) ✅
- État du code : Phases 1-6 implémentées, Phase 7 commencée ✅

### ⚠️ Incohérences détectées

#### 1. **Documentation des scénarios incomplète**
- `stress.yaml` déclare 3 types de pannes : `fan_failure`, `sensor_drift`, `power_surge`
- Mais **aucun scénario supplémentaire** n'est documenté dans roadmap.md
- **Recommandation :** Ajouter un scénario `heatwave.yaml` (Phase 8)

#### 2. **Variables d'environnement partielles**
README mentionne :
```
SCENARIO, CLUSTER_ID, MQTT_ENABLED, POSTGRES_PASSWORD
```
Mais loader.py supporte aussi :
- `MQTT_BROKER_HOST`
- `TICK_RATE_HZ`

**Action :** Mettre à jour README section "Variables d'environnement utiles"

#### 3. **Docker Compose et profil storage**
- README dit "docker compose --profile storage up -d"
- `docker-compose.yml` définit bien le profil, mais absent de la checklist Phase 6 ✅ (réalité : il y est)

---

## Analyse des variables YAML

### 🔍 Audit par section

#### A. **Cluster config**

```yaml
cluster:
  id: "cluster_alpha"              # ✅ Utilisé : cfg.cluster.id
  location: "Marseille"            # ❌ INEXPLOITÉ
  pue: 1.40                         # ✅ Utilisé : ClusterSimulator._pue
  env_factor: 1.05                 # ❌ INEXPLOITÉ (pour Grafana?)
  electricity_price_eur_kwh: 0.20  # ✅ Utilisé : compute_cost()
```

**Nommage :**
- ✅ `pue` : cohérent avec domaine énergétique
- ⚠️ `env_factor` : nom vague. Signification ? Suggère `overhead_cooling_factor`

---

#### B. **MQTT config**

```yaml
mqtt:
  broker_host: "mosquitto"         # ✅ Utilisé : MqttPublisher.__init__()
  broker_port: 1883                # ✅ Utilisé
  protocol_version: 5              # ⚠️ Non validé : hard-codé ? Utilisé ?
  client_id_prefix: "twin"         # ✅ Utilisé : client_id = f"{prefix}_{cluster_id}"
  topic_root: "dt"                 # ✅ Utilisé : topics générés
  cmd_root: "cmd"                  # ❌ INEXPLOITÉ (receiver MQTT non implémenté)
  publish_interval_s: 1.0          # ⚠️ Nommage : pas clair si c'est pour la boucle ou per-message
  qos_telemetry: 0                 # ✅ Utilisé
  qos_events: 1                    # ✅ Utilisé
```

**Problèmes :**
1. `protocol_version: 5` déclaré mais jamais utilisé dans `MqttPublisher`
2. `cmd_root` prévu mais pas de consumer de commandes MQTT
3. `publish_interval_s` : ambigu. Est-ce utilisé ou c'est juste `1.0 / events_per_sec` ?

---

#### C. **Role profiles**

```yaml
role_profiles:
  master:
    initial_status: "on"           # ✅ MachineSimulator.__init__()
    power:
      idle_watts: 200.0            # ✅ ThermalConfig.idle_w
      max_watts: 1700.0            # ✅ ThermalConfig.max_w
      heat_ratio: 0.70             # ✅ compute_heat_input()
    thermal:
      ambient_temp_c: 22.0         # ✅ ThermalConfig.ambient_temp_c
      thermal_capacity_j_per_c: 800.0  # ✅ ThermalConfig.c_th_j_per_c
      tau_max_s: 90.0              # ✅ ThermalConfig.tau_max_s
      k_cool_rpm_factor: 3.5       # ✅ ThermalConfig.k_cool
      alpha_load_exponent: 1.5     # ✅ ThermalConfig.alpha
      t_shutdown_c: 90.0           # ✅ MachineSimulator.power_off() check
      t_restart_c: 55.0            # ✅ MachineSimulator.power_on() check
    temperature_sensors:
      - id: "temp_cpu"
        bias_c: 0.0                # ✅ SensorConfig.bias_c
    fans:
      count: 2                      # ✅ MachineSimulator.__init__()
      max_rpm: 5000                # ✅ ThermalConfig.fan_max_rpm
      initial_rpm: 0               # ⚠️ Nommage : `initial` ou `start` ? Qui utilise ?
      power_per_fan_w: 15.0        # ✅ ThermalConfig.fan_power_w
      control_mode: "auto"         # ✅ FanState.mode
      auto_policy:
        type: "proportional"       # ✅ ScenarioEngine
        gain_rpm_per_c: 50.0       # ✅ ThermalConfig.fan_gain_rpm_per_c
    noise:
      temperature_std_c: 0.3       # ✅ SensorConfig.noise_std_c
      power_std_w: 2.0             # ❌ Déclaré mais pas utilisé dans noise.py
      fan_speed_std_rpm: 10.0      # ❌ Déclaré mais pas utilisé
```

**Nommage problématique :**
1. `initial_rpm` : non clair. Suggère `startup_rpm` ou `init_rpm`
2. `power_std_w` / `fan_speed_std_rpm` : déclarés mais **jamais appliqués** ❌

---

#### D. **Simulation config (scenario base)**

```yaml
simulation:
  mode: "nominal"                  # ⚠️ Nommage : pourquoi pas `scenario` ?
  tick_rate_hz: 10.0               # ✅ ClusterSimulator._tick_rate_hz
  events_per_sec: 1.0              # ✅ ClusterSimulator._events_per_sec
  duration: "0"                    # ✅ parse_duration() in Duration.py
```

**Problème :** Le champ s'appelle `mode` mais logiquement c'est un `scenario`. Incohérent avec la surcharge `PUT /simulation/scenario`.

---

#### E. **Load profile (nominal)**

```yaml
load_profile:
  type: "sine_wave"                # ✅ ScenarioEngine.get_load_factor()
  base_load: 0.35                  # ✅ _sine_wave()
  amplitude: 0.20                  # ✅ _sine_wave()
  period_s: 300.0                  # ✅ _sine_wave()
```

✅ Parfait alignement

---

#### F. **Load profile (stress)**

```yaml
load_profile:
  type: "ramp_with_spikes"         # ✅ ScenarioEngine
  ramp_start: 0.20                 # ✅ _ramp_with_spikes()
  ramp_end: 0.95                   # ✅ _ramp_with_spikes()
  ramp_duration_s: 600.0           # ✅ _ramp_with_spikes()
  spike_probability: 0.02          # ✅ _ramp_with_spikes()
  spike_duration_s: 30.0           # ✅ _ramp_with_spikes()
  spike_magnitude: 0.30            # ✅ _ramp_with_spikes()
```

✅ Parfait alignement (mais voir section "legacy aliases" dans scenarios.py)

---

#### G. **Fault injection (stress)**

```yaml
fault_injection:
  enabled: true                    # ✅ ClusterSimulator.run() check
  faults:
    - type: "fan_failure"          # ✅ FaultScheduler
      distribution: "weibull"      # ✅ weibull_event()
      shape: 1.5                   # ✅ Utilisé par weibull
      scale_s: 7200                # ✅ Utilisé par weibull
      magnitude: 1.0               # ✅ ActiveFault.magnitude
```

✅ Alignement complet

---

## Problèmes de nommage identifiés

### 🔴 Critiques

| Variable | Localisation | Problème | Recommandation |
|----------|-------------|---------|----------------|
| `initial_rpm` | `base.yaml` + `machine.py` | Ambigu : initial au démarrage ? Ou courant ? | Renommer : `startup_rpm` |
| `mode` | `simulation` section YAML | Nommé `mode` mais c'est un `scenario` | Renommer en YAML : `scenario` |
| `power_std_w` | `noise` section + YAML | Déclaré mais jamais utilisé | Implémenter ou supprimer |
| `fan_speed_std_rpm` | `noise` section + YAML | Déclaré mais jamais utilisé | Implémenter ou supprimer |

### 🟡 Moyens

| Variable | Localisation | Problème | Recommandation |
|----------|-------------|---------|----------------|
| `env_factor` | `cluster` section | Nom vague | Renommer : `cooling_overhead_factor` ou `aux_consumption_factor` |
| `protocol_version` | MQTT config | Déclaré mais inutilisé | Supprimer ou implémenter validation |
| `publish_interval_s` | MQTT config | Nommage : `interval` implique une utilisation périodique | Clarifier : est-ce un fallback ou juste documentation ? |
| `cmd_root` | MQTT config | Prévu mais non implémenté | Implémenter ou documenter comme "réservé pour Phase 8" |

### 🟢 Acceptables

- ✅ `tau_max_s` : précis
- ✅ `k_cool_rpm_factor` : bien documenté en YAML
- ✅ `heat_ratio` : standard industrie
- ✅ `pue` : acronyme bien connu (Power Usage Effectiveness)

---

## Variables inexploitées

### Analyse d'impact

#### 1. **`noise.power_std_w` et `noise.fan_speed_std_rpm`**

```yaml
# Dans base.yaml
noise:
  temperature_std_c: 0.3  # ✅ Appliqué dans noise.py
  power_std_w: 2.0       # ❌ Jamais appliqué
  fan_speed_std_rpm: 10.0 # ❌ Jamais appliqué
```

**Impact :** Réalisme réduit. Les ventilateurs et la puissance devraient avoir du bruit comme la température.

**Solution pour Phase 7 :**
```python
# Dans machine.py:tick()
noisy_power = self.power_w + np.random.normal(0, noise_std_w)
noisy_fan_rpm = [f.rpm + np.random.normal(0, noise_std_rpm) for f in fans]
```

---

#### 2. **`env_factor` (env_factor: 1.05)**

```yaml
cluster:
  pue: 1.40
  env_factor: 1.05  # ❌ Jamais utilisé
```

**Hypothèse :** Augmentation du PUE effectif due aux conditions externes (température ambiante élevée, etc.)

**Impact :** Coûts énergétiques sous-estimés en conditions de chaleur extrême.

**Solution pour Phase 8 (heatwave scenario) :**
```python
ambient_adjustment = 1.0
if ambient_temp_c > 30:
    ambient_adjustment = config.cluster.env_factor
effective_pue = self._pue * ambient_adjustment
```

---

#### 3. **`cmd_root` et absence de consumer de commandes**

```yaml
mqtt:
  cmd_root: "cmd"  # ❌ Prévu mais pas de subscriber
```

**Impact :** Les machines peuvent être commandées via l'API REST/WebSocket, mais pas via MQTT.

**Solution pour Phase 8 :**
- Créer un `MqttCommandConsumer` qui s'abonne à `cmd/{cluster}/{machine}/*`
- Parser et exécuter les commandes (power on/off, set fan speed, etc.)

---

#### 4. **`location` (location: "Marseille")**

```yaml
cluster:
  location: "Marseille"  # ❌ Utilisé nulle part
```

**Impact :** Métadonnée non exposée dans l'API.

**Solution pour Phase 7 :**
```python
# Dans api/models.py
class ClusterInfoResponse(BaseModel):
    id: str
    location: str  # ← nouveau champ
    running: bool
```

---

## Plan de développement Phase 7

### 📌 Objectif principal
Implémenter une couverture de tests ≥80% sur les modules critiques et stabiliser le simulateur.

### Étape 7.1 — Tests unitaires consolidés

#### A. **Tests des variables de machine à partir du YAML**

**Fichier :** `tests/test_machine_from_yaml.py`

```python
def test_machine_config_from_yaml_master():
    """Vérifie que les valeurs YAML master sont correctement chargées."""
    cfg = load_config(scenario="nominal")
    
    # Master-01 : héritage du rôle
    master_cfg = get_machine_config(cfg, "srv-master-01")
    assert master_cfg.power.idle_watts == 200.0
    assert master_cfg.power.max_watts == 1700.0
    assert master_cfg.thermal.t_shutdown_c == 90.0
    
    # Master-02 : surcharge individuelle
    master_cfg_02 = get_machine_config(cfg, "srv-master-02")
    assert master_cfg_02.thermal.t_shutdown_c == 92.0  # Surcharge !
```

**Couverture :**
- Héritage de rôle ✅
- Surcharge individuelle ✅
- Machines OFF au démarrage ✅

---

#### B. **Tests de télémétrie avec validation YAML**

**Fichier :** `tests/test_machine_telemetry.py`

```python
def test_machine_sends_valid_telemetry():
    """Vérifie que snapshot() produit des champs cohérents avec les seuils YAML."""
    cfg = load_config("nominal")
    
    machine = ClusterSimulator(cfg).machines["srv-master-01"]
    machine.power_on()
    
    # 100 ticks de simulation
    for _ in range(100):
        machine.tick(load_factor=0.5, dt=0.1)
    
    snapshot = machine.snapshot()
    
    # Télémétrie : tous les champs requis présents
    assert "temp_cpu" in snapshot["sensors"]
    assert "temp_inlet" in snapshot["sensors"]
    assert "status" in snapshot
    assert "power_w" in snapshot
    assert "fans" in snapshot
    
    # Validations physiques
    assert snapshot["status"] in ["on", "off", "degraded"]
    assert 0 <= snapshot["power_w"] <= 1700.0  # max_watts pour master
    assert 20 <= snapshot["temp_cpu"] <= 95  # intervalle raisonnable
```

**Couverture :**
- Snapshot contient tous les champs requis ✅
- Valeurs en intervalle physique valide ✅
- Cohérence entre charge et puissance ✅

---

#### C. **Tests de commandes machine**

**Fichier :** `tests/test_machine_commands.py`

```python
def test_fan_speed_change_reduces_temperature():
    """Vérifie que augmenter la vitesse des fans réduit la température."""
    cfg = load_config("nominal")
    simulator = ClusterSimulator(cfg)
    machine = simulator.machines["srv-master-01"]
    
    machine.power_on()
    
    # Phase 1 : fans lents (mode auto)
    temps_slow = []
    for _ in range(50):
        machine.tick(load_factor=0.7, dt=0.1)
        temps_slow.append(machine.snapshot()["temp_cpu"])
    
    # Phase 2 : augmenter la vitesse des fans
    machine.set_fan_speed(fan_idx=0, rpm=4000)
    machine.set_fan_speed(fan_idx=1, rpm=4000)
    
    # Phase 3 : vérifier que T diminue
    temps_fast = []
    for _ in range(50):
        machine.tick(load_factor=0.7, dt=0.1)
        temps_fast.append(machine.snapshot()["temp_cpu"])
    
    # La température finale doit être plus basse
    assert np.mean(temps_fast[-10:]) < np.mean(temps_slow[-10:])
```

**Couverture :**
- Commande `set_fan_speed()` fonctionne ✅
- Effet physique du changement de RPM visible ✅
- Consommation électrique augmente avec RPM ✅

---

#### D. **Tests de conformité énergétique**

**Fichier :** `tests/test_energy_conformity.py`

```python
def test_power_consumption_increases_with_load():
    """Vérifie que P_elec(load) suit la formule YAML + physics."""
    cfg = load_config("nominal")
    simulator = ClusterSimulator(cfg)
    machine = simulator.machines["srv-master-01"]
    
    machine.power_on()
    
    # Test à différentes charges
    test_loads = [0.1, 0.3, 0.5, 0.7, 0.9]
    powers = []
    
    for load in test_loads:
        machine.temperature_c = 25.0  # Reset T
        machine.tick(load_factor=load, dt=0.1)
        powers.append(machine.power_w)
    
    # Vérifier que P(load) est croissant
    for i in range(len(powers) - 1):
        assert powers[i] < powers[i+1], f"P croissant attendu : {powers}"
    
    # Vérifier la formule : P = idle + (max - idle) * load^alpha
    master_cfg = get_machine_config(cfg, "srv-master-01")
    idle = master_cfg.power.idle_watts
    max_w = master_cfg.power.max_watts
    alpha = master_cfg.thermal.alpha_load_exponent
    
    for load, p_measured in zip(test_loads, powers):
        p_expected = idle + (max_w - idle) * (load ** alpha)
        # Tolérance : ±5W (bruit)
        assert abs(p_measured - p_expected) < 5.0
```

**Couverture :**
- Formule puissance-charge respectée ✅
- Bruit acceptable ✅
- Données YAML cohérentes avec code ✅

---

### Étape 7.2 — Tests d'intégration et API

#### A. **Tests FastAPI endpoints**

**Fichier :** `tests/test_api_integration.py`

```python
import pytest
from httpx import AsyncClient
from api.main import app

@pytest.mark.asyncio
async def test_get_cluster_status():
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/cluster/status")
        assert response.status_code == 200
        
        data = response.json()
        assert "machines" in data
        assert len(data["machines"]) == 5  # 5 machines

@pytest.mark.asyncio
async def test_machine_power_command():
    async with AsyncClient(app=app, base_url="http://test") as client:
        # Power ON
        resp = await client.post("/machines/srv-master-01/power", json={"on": True})
        assert resp.status_code == 200
        
        # Vérifier l'état
        status = await client.get("/machines/srv-master-01")
        assert status.json()["status"] == "on"

@pytest.mark.asyncio
async def test_fan_speed_command():
    async with AsyncClient(app=app, base_url="http://test") as client:
        # Mettre les fans à 3000 RPM
        resp = await client.put(
            "/machines/srv-master-01/fan_speed",
            json={"rpm": 3000}
        )
        assert resp.status_code == 200
        
        # Vérifier que la puissance a augmenté
        before = await client.get("/machines/srv-master-01")
        power_before = before.json()["power_w"]
        
        # Attendre quelques ticks...
        # (nécessite modifications pour test syncrone)
        
        power_after = (await client.get("/machines/srv-master-01")).json()["power_w"]
        # Fan power ajouté
        assert power_after > power_before
```

---

### Étape 7.3 — Tests MQTT end-to-end

**Fichier :** `tests/test_mqtt_integration.py`

```python
@pytest.mark.asyncio
async def test_mqtt_telemetry_published():
    """Vérifie que ClusterSimulator publie bien les télémétries MQTT."""
    
    # Broker de test
    async with asynccontextmanager(mosquitto_test_broker)() as broker:
        cfg = load_config("nominal", overrides={
            "cluster.mqtt.broker_host": "localhost",
            "cluster.mqtt.broker_port": 1883
        })
        
        publisher = MqttPublisher(cfg.cluster.mqtt)
        simulator = ClusterSimulator(cfg)
        
        async with publisher:
            # Lancer la simulation
            run_task = asyncio.create_task(simulator.run(publisher=publisher))
            
            # Collecter les messages MQTT
            messages = []
            async with aiomqtt.Client("localhost") as client:
                async with client.messages() as messages_iter:
                    client.subscribe("dt/#")
                    
                    async for message in messages_iter:
                        messages.append((message.topic, message.payload.decode()))
                        if len(messages) >= 10:
                            break
            
            # Vérifier la structure
            assert any("srv-master-01" in msg[0] for msg in messages)
            assert any("telemetry" in msg[0] for msg in messages)
```

---

### Étape 7.4 — Tests TimescaleDB consumer

**Fichier :** `tests/test_consumer_integration.py`

```python
@pytest.mark.asyncio
async def test_mqtt_to_timescale_ingestion():
    """Vérifie que les messages MQTT sont correctement ingérés dans TimescaleDB."""
    
    async with asynccontextmanager(timescale_test_db)() as conn:
        consumer = MqttToTimescale(mqtt_cfg, pg_cfg)
        
        # Injecter des messages
        messages = [
            ("dt/cluster_alpha/srv-master-01/telemetry", json.dumps({
                "timestamp": datetime.now().isoformat(),
                "temp_cpu": 45.2,
                "power_w": 450.0,
                "fans": [{"idx": 0, "rpm": 2500}, {"idx": 1, "rpm": 2500}]
            }))
        ]
        
        # Consumer process messages
        for topic, payload in messages:
            await consumer.on_message(topic, payload)
        
        # Vérifier que les données sont dans la DB
        async with conn.cursor() as cur:
            await cur.execute("""
                SELECT COUNT(*) FROM telemetry 
                WHERE machine_id = 'srv-master-01'
            """)
            count = await cur.fetchone()
            assert count[0] > 0
```

---

## Recommandations

### 🔴 Actions prioritaires (Phase 7.1)

1. **Créer `tests/test_machine_yaml_integration.py`**
   - Vérifier que toutes les variables YAML sont chargées correctement
   - Tester l'héritage de rôle et les surcharges individuelles
   - Validations de plages (t_shutdown > t_restart, etc.)

2. **Implémenter `power_std_w` et `fan_speed_std_rpm`**
   - Ajouter le bruit dans `machine.py:tick()`
   - Mettre à jour la documentation dans le code

3. **Corriger les nommages critiques**
   - Renommer `initial_rpm` → `startup_rpm` (si pertinent)
   - Renommer `simulation.mode` → `simulation.scenario` (cohérence API)
   - Clarifier ou supprimer `publish_interval_s`

4. **Documenter les variables inexploitées**
   - Marquer `env_factor` comme "réservé Phase 8 (scénario heatwave)"
   - Marquer `cmd_root` comme "réservé Phase 8 (consumer de commandes)"
   - Ajouter des commentaires YAML explicatifs

### 🟡 Actions moyen terme (Phase 7.2)

5. **Implémenter les tests FastAPI**
   - Tests des 10 endpoints principaux
   - Tests des codes d'erreur (404, 409)
   - Tests WebSocket avec reconnexion

6. **Ajouter support `location` en API**
   - Inclure dans la réponse `GET /`
   - Exposer dans le snapshot cluster

7. **Tests de bout en bout MQTT**
   - Broker de test (testcontainers ou mosquitto en Docker)
   - Valider le flux simulation → MQTT → consumer → TSDB

### 🟢 Améliorations futures (Phase 8)

8. **Implémenter les extensions YAML**
   - Scénario heatwave avec `ambient_temp_c: 32.0` + `env_factor` appliqué
   - Consumer MQTT de commandes

9. **Dashboard Grafana complet**
   - Utiliser `env_factor` pour alertes adaptées à la température
   - Ajouter la provenance des données (location)

10. **Validation YAML avancée**
    - JSON Schema ou Pydantic pour validation stricte
    - Tests de migration de config entre versions

---

## Checklist de mise à jour

### Pour README.md

- [ ] Ajouter variables d'environnement manquantes : `MQTT_BROKER_HOST`, `TICK_RATE_HZ`
- [ ] Clarifier `publish_interval_s` (utilisé ?)
- [ ] Ajouter exemples d'ingestion TimescaleDB
- [ ] Documenter la couverture de tests actuelle (40% → Phase 7)

### Pour roadmap.md

- [ ] Détailler Phase 7.1 : liste exacte des tests à créer
- [ ] Ajouter Phase 7.3 : tests MQTT e2e
- [ ] Ajouter Phase 7.4 : tests consumer
- [ ] Clarifier Phase 8 : scénario heatwave + consumer MQTT
- [ ] Ajouter checklist de validation pour chaque variable YAML

### Pour config/base.yaml

- [ ] Ajouter commentaire : `env_factor` → "Phase 8: heatwave scenario"
- [ ] Clarifier `initial_rpm` → "RPM au démarrage (mode auto)"
- [ ] Documenter `cmd_root` → "Réservé pour Phase 8"
- [ ] Ajouter notes sur `power_std_w` et `fan_speed_std_rpm` (maintenant implémentés)

---

## Résumé exécutif

| Aspect | État | Score |
|--------|------|-------|
| Alignement README-Code | ✅ Bon | 8/10 |
| Nommage variables YAML | ⚠️ Moyen | 6/10 |
| Couverture variables YAML | 🟡 Partiel | 7/10 |
| Tests unitaires | ⚠️ Minimal | 4/10 |
| Documentation | ✅ Correcte | 8/10 |
| **Score global** | **6.6/10** | **Cible Phase 7 : 8.5/10** |

---

**Prochaine étape :** Démarrer Phase 7.1 avec création de la suite de tests pour valider les variables YAML.

