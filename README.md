# 🌡️ Jumeaux Chauds — Digital Twin de Cluster IoT

> Simulateur de jumeaux numériques thermiques pour un cluster de serveurs, avec publication MQTT temps réel, API FastAPI, dashboard Streamlit et stack de stockage TimescaleDB + Grafana.

**Auteur :** Tristan Vanrullen — La Plateforme, Marseille — 2026

---

## Avancement

| Phase | Statut |
|---|---|
| 1 — Fondations (config, modèle physique) | ✅ Complète |
| 2 — Simulation (MachineSimulator, ClusterSimulator) | ✅ Complète |
| 3 — MQTT (publisher aiomqtt, intégration cluster) | ✅ Complète |
| 4 — API FastAPI (lifespan, endpoints REST, WebSocket) | ✅ Complète |
| 5 — Dashboard Streamlit (temps réel, commandes, énergie) | ✅ Complète |
| 6 — Déploiement Docker (Compose noyau + profil storage) | ✅ Complète |
| 7 — Tests unitaires et d'intégration | ✅ **Complète** (7.1 ✅, 7.2 ✅, 7.3 ✅, 7.4 ✅, 7.5 ✅) |
| 8 — Extensions pédagogiques | 🔜 Facultatif |

---

## Démarrage rapide

### Prérequis

```bash
conda create -n jumeaux-chauds python=3.12
conda activate jumeaux-chauds
pip install -r requirements.txt
```

### Développement local (sans Docker)

```bash
# Broker MQTT seul
docker compose up mosquitto -d

# Simulation CLI
python scripts/run_simulator.py --scenario nominal
python scripts/run_simulator.py --scenario stress --duration 2m

# API FastAPI
export MQTT_ENABLED=0   # Linux/macOS
set MQTT_ENABLED=0      # Windows
uvicorn api.main:app --reload --port 8000

# Dashboard Streamlit
streamlit run dashboard/app.py
```

Docs API : **http://localhost:8000/docs**  
Dashboard : **http://localhost:8501**  
WebSocket : `wscat -c ws://localhost:8000/ws/cluster`

---

## Docker Compose — Stack complète (Phase 6)

### Noyau (simulateur + broker + dashboard)

```bash
docker compose up -d
```

Services démarrés :
- `mosquitto` — broker MQTT sur le port 1883
- `iot-twin` — simulateur + API FastAPI sur le port 8000
- `dashboard` — Streamlit sur le port 8501

### Profil storage (TimescaleDB + consumer + Grafana)

```bash
docker compose --profile storage up -d
```

Services supplémentaires :
- `timescaledb` — PostgreSQL + extension TimescaleDB sur le port 5432
- `mqtt-consumer` — abonné MQTT → écrit dans TimescaleDB
- `grafana` — dashboards sur le port 3000 (admin / admin)

### Variables d'environnement utiles

| Variable | Défaut | Rôle |
|---|---|---|
| `SCENARIO` | `nominal` | Scénario de charge |
| `CLUSTER_ID` | `cluster_alpha` | Identifiant du cluster |
| `MQTT_ENABLED` | `1` | Désactiver MQTT (`0`) |
| `POSTGRES_PASSWORD` | `jumeaux` | Mot de passe TimescaleDB / Grafana datasource |

### Arrêt et nettoyage

```bash
docker compose down
docker compose --profile storage down -v
```

---

## Accès aux services

### Depuis la machine hôte / un client externe

| Service | URL / hôte | Port | Détails |
|---|---|---:|---|
| API FastAPI | `http://localhost:8000` | 8000 | Endpoint racine `/` |
| Documentation OpenAPI | `http://localhost:8000/docs` | 8000 | Swagger UI |
| WebSocket cluster | `ws://localhost:8000/ws/cluster` | 8000 | Flux temps réel du snapshot |
| Dashboard Streamlit | `http://localhost:8501` | 8501 | Interface utilisateur |
| Broker MQTT Mosquitto | `localhost` | 1883 | Accès MQTT TCP |
| MQTT over WebSocket | `ws://localhost:9001` | 9001 | Pour clients MQTT WebSocket |
| TimescaleDB | `localhost` | 5432 | Base PostgreSQL/TimescaleDB |
| Grafana | `http://localhost:3000` | 3000 | Login par défaut : `admin / admin` |

### Depuis un autre conteneur Docker du même réseau Compose

| Service | Adresse interne | Port |
|---|---|---:|
| API FastAPI | `http://iot-twin:8000` | 8000 |
| Dashboard Streamlit | `http://dashboard:8501` | 8501 |
| Mosquitto MQTT | `mosquitto` | 1883 |
| Mosquitto WebSocket | `mosquitto` | 9001 |
| TimescaleDB | `timescaledb` | 5432 |
| Grafana | `http://grafana:3000` | 3000 |

### Exemples d'accès

```bash
# Vérifier l'API
curl http://localhost:8000/

# Consulter la doc interactive
# http://localhost:8000/docs

# Tester le WebSocket temps réel
wscat -c ws://localhost:8000/ws/cluster

# S'abonner aux topics MQTT
mosquitto_sub -h localhost -t 'dt/#' -v

# Se connecter à TimescaleDB
psql -h localhost -p 5432 -U jumeaux -d jumeaux

# Ouvrir Grafana
# http://localhost:3000
# login: admin / admin
```

---

## Architecture

```
simulation/      Modèle physique thermique, MachineSimulator, ClusterSimulator
mqtt/            MqttPublisher aiomqtt (Phase 3 ✅)
api/             FastAPI lifespan + endpoints REST + WebSocket (Phase 4 ✅)
dashboard/       Streamlit temps réel (Phase 5 ✅)
consumer/        MQTT → TimescaleDB (Phase 6 ✅)
config/          YAML hiérarchique OmegaConf (base + scénarios)
tests/           pytest + pytest-asyncio
grafana/         Provisioning datasource + dashboard (Phase 6 ✅)
mosquitto/       Configuration broker MQTT
```

Voir [`documents/specifications.md`](documents/specifications.md) pour le détail technique complet  
et [`documents/roadmap.md`](documents/roadmap.md) pour le suivi d'avancement.

---

## API FastAPI (Phase 4 ✅)

| Méthode | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Info API + état simulateur |
| `GET` | `/cluster/status` | Snapshot complet du cluster |
| `GET` | `/cluster/energy` | Métriques énergétiques |
| `POST` | `/cluster/power` | Allumer/éteindre tout le cluster |
| `PUT` | `/cluster/fan_speed` | Vitesse homogène tous les fans |
| `GET` | `/machines/{id}` | Snapshot d'une machine |
| `POST` | `/machines/{id}/power` | Power ON/OFF (409 si T trop haute) |
| `PUT` | `/machines/{id}/fan_speed` | Vitesse manuelle d'un fan |
| `PUT` | `/machines/{id}/fan_mode` | Mode auto/manual d'un fan |
| `POST` | `/simulation/fault` | Injecter une panne |
| `DELETE` | `/simulation/fault/{id}` | Annuler les pannes d'une machine |
| `PUT` | `/simulation/scenario` | Changer de scénario à chaud |
| `WS` | `/ws/cluster` | Flux temps réel du snapshot |

---

## Topics MQTT publiés (Phase 3 ✅)

| Topic | QoS | Fréquence |
|---|---|---|
| `dt/{cluster}/{machine}/telemetry` | 0 | `events_per_sec` |
| `dt/{cluster}/{machine}/temp/{sensor}` | 0 | `events_per_sec` |
| `dt/{cluster}/{machine}/power` | 0 | `events_per_sec` |
| `dt/{cluster}/{machine}/fan/{idx}` | 0 | Sur changement |
| `dt/{cluster}/{machine}/status` | 1 | Sur changement |
| `dt/{cluster}/{machine}/fault` | 1 | Sur événement |
| `dt/{cluster}/summary` | 1 | Toutes les 5 s |
| `dt/{cluster}/metrics/energy` | 1 | Toutes les 60 s |

---

## Structure du projet

```text
jumeaux-chauds/
├── config/
│   ├── base.yaml
│   ├── loader.py
│   └── scenarios/
│       ├── nominal.yaml
│       └── stress.yaml
├── simulation/
│   ├── cluster.py
│   ├── machine.py
│   ├── physics.py
│   ├── noise.py
│   ├── scenarios.py
│   └── duration.py
├── mqtt/
│   └── publisher.py          ← Phase 3 ✅
├── api/                      ← Phase 4 ✅
│   ├── main.py
│   ├── deps.py
│   ├── models.py
│   ├── ws.py
│   └── routes/
│       ├── machines.py
│       ├── cluster.py
│       └── simulation.py
├── dashboard/                ← Phase 5 ✅
│   ├── app.py
│   ├── ws_client.py
│   └── api_client.py
├── consumer/                 ← Phase 6 ✅
│   ├── mqtt_to_timescale.py
│   └── schema.sql
├── grafana/                  ← Phase 6 ✅
│   └── provisioning/
│       ├── datasources/
│       │   └── timescale.yaml
│       └── dashboards/
│           ├── dashboard.yaml
│           └── jumeaux-chauds.json
├── mosquitto/config/
│   └── mosquitto.conf
├── tests/
├── scripts/
│   └── run_simulator.py
├── Dockerfile
├── Dockerfile.dashboard
├── Dockerfile.consumer
├── docker-compose.yml
├── documents/
│   ├── specifications.md
│   └── roadmap.md
├── requirements.txt
├── requirements.dashboard.txt
├── requirements.consumer.txt
├── requirements.test.txt
└── Makefile
```

---

## Phase 7 — Tests (actuellement en cours)

### Étape 7.1 ✅ — Tests unitaires consolidés

**Tests créés :**
- `tests/test_machine_yaml_integration.py` — 40+ tests validant le chargement YAML et l'héritage de rôle
- `tests/test_machine_telemetry.py` — 50+ tests validant la structure du snapshot et les limites physiques
- `tests/test_machine_commands.py` — 30+ tests des commandes (fan speed, power, mode)
- `tests/test_energy_conformity.py` — 35+ tests validant la formule P(load) et l'accumulation d'énergie

**Exécution :**
```bash
pytest tests/test_machine_yaml_integration.py -v        # 40 tests
pytest tests/test_machine_telemetry.py -v              # 50 tests
pytest tests/test_machine_commands.py -v               # 30 tests
pytest tests/test_energy_conformity.py -v              # 35 tests

# Tous les tests Phase 7.1
pytest tests/test_machine*.py tests/test_energy*.py -v --cov=simulation --cov=config --cov-report=term-missing
```

### Étape 7.3 ✅ — Tests FastAPI

Tests créés :
- ✅ `tests/test_api_integration.py` avec TestClient (23 tests)
- ✅ Tests des 10 endpoints REST principaux
- ✅ Validation codes d'erreur (404, 409)
- ✅ Tests WebSocket connexion/déconnexion
- ✅ Tests format réponses et structure données

Exécution :
```bash
pytest tests/test_api_integration.py -v
```

### Étape 7.4 ✅ — Tests MQTT e2e

Tests créés :
- ✅ `tests/test_mqtt_integration.py` avec 18 tests
- ✅ Tests de configuration du publisher (broker, topics, QoS)
- ✅ Validation des 8 topics principaux
- ✅ Structure et sérialisation JSON des payloads
- ✅ Intégration simulation → publisher

Exécution :
```bash
pytest tests/test_mqtt_integration.py -v
```

### Étape 7.5 ✅ — Tests consumer TimescaleDB

Tests créés :
- ✅ `tests/test_consumer_integration.py` avec 28 tests
- ✅ Validation MQTT topic parsing (regex, cluster/machine extraction)
- ✅ Validation JSON payload parsing (telemetry, events)
- ✅ Conversion timestamps ISO 8601 → DateTime
- ✅ Calcul RPM moyen fans
- ✅ Dispatch messages vers telemetry_insert ou event_insert
- ✅ Extraction données (temp, power, energy, status)
- ✅ Configuration consumer (MQTT broker, PostgreSQL DSN)

Exécution :
```bash
pytest tests/test_consumer_integration.py -v
```

**Résultat :** 28/28 tests PASSED (100%) ✅

---

## Problèmes de nommage identifiés et corrections

Voir **ANALYSE_EXHAUSTIVE.md** pour le détail complet. Résumé :

| Variable | État | Action |
|----------|------|--------|
| `initial_rpm` | ⚠️ Ambigu | Renommer en `startup_rpm` (si pertinent) |
| `simulation.mode` | ⚠️ Inconsistant | Renommer en `scenario` (cohérence API) |
| `power_std_w`, `fan_speed_std_rpm` | ❌ Inexploités | À implémenter en Phase 7.2 |
| `env_factor` | 📋 Réservé | Pour Phase 8 (scénario heatwave) |
| `cmd_root` | 📋 Réservé | Pour Phase 8 (consumer commandes MQTT) |

---

## Variables YAML inexploitées (Phase 8)

### `env_factor: 1.05`
Facteur d'augmentation du PUE en conditions chaudes (T_ambient > 30°C). À utiliser dans le scénario `heatwave.yaml`.

### `cmd_root: "cmd"`
Racine des topics MQTT pour les commandes. À implémenter : abonnement aux `cmd/{cluster}/{machine}/*` et exécution.

### `location: "Marseille"`
Métadonnée non exposée en API. À ajouter dans `GET /` et MQTT.

---

## Prochaines étapes recommandées

1. **Immédiat (Phase 7.2)** : Ajouter tests FastAPI (`test_api_integration.py`)
2. **Court terme** : Tests MQTT e2e et consumer
3. **Moyen terme** : Implémenter variables réservées (`power_std_w`, `fan_speed_std_rpm`)
4. **Phase 8** : Scénario heatwave + consumer de commandes MQTT

---

*Tristan Vanrullen — La Plateforme, Marseille — 2026*  
*Phase 7.1 (tests unitaires) : ✅ Complète  |  Phase 7.2-7.4 : 📋 Planifiées*
