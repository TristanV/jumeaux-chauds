# 🚀 Jumeaux Chauds — Quick Start (Tests & Démarrage)

> Référence rapide des commandes pour tester et lancer l'application sans Docker.

---

## ✅ Phase 0 : Setup

```bash
# Environnement
conda create -n jumeaux-chauds python=3.12 -y
conda activate jumeaux-chauds
pip install -r requirements.txt
pip install -r requirements.test.txt
```

---

## 🧪 Phase 1 : Tests Unitaires (5 min)

```bash
# Tous les tests (155+ tests, 85% couverture)
pytest tests/ -v --cov=simulation --cov=config --cov-report=term-missing

# Tests spécifiques
pytest tests/test_physics.py -v                    # 35 tests physique
pytest tests/test_config.py -v                     # Tests config YAML
pytest tests/test_machine_telemetry.py -v          # 50 tests snapshot
pytest tests/test_machine_commands.py -v           # 30 tests commandes
pytest tests/test_energy_conformity.py -v          # 35 tests énergie
pytest tests/test_mqtt_integration.py -v           # 18 tests MQTT
pytest tests/test_consumer_integration.py -v       # 28 tests consumer
pytest tests/test_api_integration.py -v            # 23 tests API
```

---

## 🌐 Phase 2 : Broker MQTT

### Option A : Docker (recommandé, single command)
```bash
# Terminal 1 — Broker MQTT
docker run --rm --name mosquitto -p 1883:1883 -p 9001:9001 eclipse-mosquitto:2
```

### Option B : Native (Linux/macOS)
```bash
# Installation
brew install mosquitto                    # macOS
sudo apt install mosquitto mosquitto-clients  # Ubuntu

# Démarrer
mosquitto -v

# Test connectivité (autre terminal)
mosquitto_sub -h localhost -t '$SYS/#' -v
```

---

## 📊 Phase 3 : Simulation + MQTT

**Terminal 2 — Lancer simulateur**

```bash
# Nominal (par défaut, 1 minute)
python scripts/run_simulator.py --scenario nominal --duration 1m

# Autres durées
python scripts/run_simulator.py --scenario nominal --duration 10s   # 10 sec
python scripts/run_simulator.py --scenario nominal --duration 5m    # 5 min
python scripts/run_simulator.py --scenario nominal --duration 1h    # 1 heure

# Scénarios différents
python scripts/run_simulator.py --scenario stress --duration 2m
python scripts/run_simulator.py --scenario heatwave --duration 24h  # Vague de chaleur
python scripts/run_simulator.py --scenario busy_weeks --duration 7d # Semaines chargées
```

**Output attendu :**
```
✓ Config loaded: cluster_alpha
✓ ClusterSimulator initialized (5 machines)
✓ MQTT Publisher connecting to localhost:1883
✓ Publishing to dt/cluster_alpha/... topics

[tick 0] avg_temp=22.5°C, power=250W
[tick 1] avg_temp=22.6°C, power=251W
...
```

---

## 👁️ Phase 4 : Observer MQTT

**Terminal 3 — Observer les messages MQTT**

```bash
# Option 1 : Notre script Python (JSON pretty-print)
python scripts/mqtt_observer.py --host localhost

# Topics spécifiques
python scripts/mqtt_observer.py --host localhost --topics "dt/+/+/telemetry"
python scripts/mqtt_observer.py --host localhost --topics "dt/+/summary" "dt/+/+/fault"

# Verbose (montre tailles payloads)
python scripts/mqtt_observer.py --host localhost -v

# Option 2 : mosquitto_sub (native, simple)
mosquitto_sub -h localhost -t "dt/#" -v

# Sauvegarder dans fichier log
mosquitto_sub -h localhost -t "dt/#" -v > mqtt.log &

# Option 3 : MQTT Explorer (GUI, https://mqtt-explorer.com/)
mqtt-explorer
# Config: Broker=localhost, Port=1883, Topic=dt/#
```

---

## 🔌 Phase 5 : API FastAPI

**Terminal 4 — Lancer API**

```bash
# Sans MQTT (plus rapide)
export MQTT_ENABLED=0
uvicorn api.main:app --reload --port 8000

# Avec MQTT (si broker tourne)
uvicorn api.main:app --reload --port 8000
```

**Puis :**
- 📖 Docs interactive : http://localhost:8000/docs
- 🔗 Info API : http://localhost:8000/
- 📊 Status : http://localhost:8000/cluster/status

**Tests rapides (curl)**
```bash
# Info cluster
curl http://localhost:8000/

# Status complet
curl http://localhost:8000/cluster/status

# Power ON cluster
curl -X POST http://localhost:8000/cluster/power \
  -H "Content-Type: application/json" -d '{"power_on": true}'

# Power OFF cluster
curl -X POST http://localhost:8000/cluster/power \
  -d '{"power_on": false}'

# Info machine
curl http://localhost:8000/machines/srv-master-01

# Power ON machine
curl -X POST http://localhost:8000/machines/srv-master-01/power \
  -d '{"power_on": true}'

# Fan speed
curl -X PUT http://localhost:8000/machines/srv-master-01/fan_speed \
  -d '{"target_rpm": 3000}'

# Injecter panne
curl -X POST http://localhost:8000/simulation/fault \
  -d '{"machine_id": "srv-master-01", "fault_type": "cpu_throttle"}'

# Changer scénario
curl -X PUT http://localhost:8000/simulation/scenario \
  -d '{"scenario": "stress"}'
```

---

## 📊 Phase 6 : Dashboard Streamlit

**Terminal 5 — Lancer dashboard**

```bash
streamlit run dashboard/app.py

# Ouvrir http://localhost:8501
```

**Onglets disponibles :**
- 📈 **Cluster** : Vue globale, heatmap température
- 🖥️ **Machines** : Détail machine, commandes power/fans
- ⚙️ **Simulation** : Sélecteur scénario, injection pannes
- ⚡ **Énergie** : kWh, PUE, coût

---

## 🔥 Phase 7 : Scénarios Avancés (Phase 8.1)

### Heatwave (Vague de chaleur)

```bash
# Terminal 2 : Vague de chaleur 24h
python scripts/run_simulator.py --scenario heatwave --duration 24h

# Attend : T_amb 28°C→35°C, pannes ×3 quand T>32°C, rush hours
```

**Analyser :**
- Temperature augmente progressivement
- Taux de pannes explose à T > 32°C
- Fans au max mais refroidissement insuffisant

### Busy Weeks (Semaines chargées)

```bash
# Terminal 2 : 7 jours réalistes
python scripts/run_simulator.py --scenario busy_weeks --duration 7d

# Test rapide : 1 jour (~60s)
python scripts/run_simulator.py --scenario busy_weeks --duration 1d

# Test ultra-rapide : 1 heure (~10s)
python scripts/run_simulator.py --scenario busy_weeks --duration 1h

# Attend : Cycles weekday (rush 9-12h, 14-18h), weekend calme (5%)
```

**Analyser :**
- Lundi-vendredi : pics de charge visibles
- Samedi-dimanche : charge minimale
- Rush hours 9-12h et 14-18h : puissance +50%

---

## 📋 Workflow complet (demo rapide 5 min)

```bash
# Terminal 1
docker run --rm --name mosquitto -p 1883:1883 eclipse-mosquitto:2

# Terminal 2 (attendre "ready" dans Terminal 1)
python scripts/run_simulator.py --scenario nominal --duration 1m

# Terminal 3 (pendant que Sim tourne)
python scripts/mqtt_observer.py --host localhost

# Terminal 4 (optionnel, pendant la simulation)
export MQTT_ENABLED=0
uvicorn api.main:app --port 8000

# Puis ouvrir http://localhost:8000/docs dans navigateur
```

---

## 🧪 Tests spécifiques par couche

| Couche | Commande | Temps |
|--------|----------|-------|
| **Fondations** | `pytest tests/test_config.py tests/test_physics.py -v` | 2 min |
| **Machine** | `pytest tests/test_machine*.py -v` | 2 min |
| **MQTT** | `pytest tests/test_mqtt_integration.py -v` | 30 sec |
| **Consumer** | `pytest tests/test_consumer_integration.py -v` | 30 sec |
| **API** | `pytest tests/test_api_integration.py -v` | 2 min |
| **Tous** | `pytest tests/ -v --cov=simulation --cov=config` | 5 min |

---

## ▶ Phase 8.13 : Contrôle démarrage/pause/arrêt de la simulation

### Comportement par défaut (Docker)

**La simulation est OFF au démarrage.** C'est le comportement par défaut (`SIMULATION_AUTOSTART=0`). Le serveur FastAPI démarre, les machines sont initialisées, mais la boucle de simulation n'est pas lancée. Vous devez la démarrer depuis le dashboard ou via l'API.

```bash
# Démarrage Docker (simulation OFF par défaut)
docker compose up

# Démarrage Docker avec simulation automatique
SIMULATION_AUTOSTART=1 docker compose up
```

### Depuis le Dashboard Streamlit (accès rapide)

Le bandeau en haut du dashboard contient 5 boutons de contrôle :

| Bouton | Action | Quand disponible |
|--------|--------|-----------------|
| **▶ Démarrer** | Lance la boucle de simulation | Quand arrêtée ou en pause |
| **⏸ Pause** | Suspend les ticks (état thermique conservé) | Quand en cours |
| **▶ Reprendre** | Reprend depuis la pause | Quand en pause |
| **⏹ Arrêter** | Arrête la boucle de simulation | Quand en cours |
| **🗑 Reset** | Remet temps + énergie à 0, vide TimescaleDB | Toujours disponible |

### Via l'API REST

```bash
# État de la simulation
curl http://localhost:8000/simulation/status

# Démarrer (ou reprendre si en pause)
curl -X POST http://localhost:8000/simulation/start

# Mettre en pause
curl -X POST http://localhost:8000/simulation/pause

# Reprendre
curl -X POST http://localhost:8000/simulation/resume

# Arrêter
curl -X POST http://localhost:8000/simulation/stop

# Reset complet (temps + énergie + TimescaleDB)
curl -X POST http://localhost:8000/simulation/reset
```

**Réponses attendues :**
```json
{"ok": true, "message": "Simulation démarrée."}
{"ok": true, "message": "Simulation mise en pause."}
{"ok": true, "message": "Simulation reprise."}
```

### États possibles

```
stopped  →  start  →  running
running  →  pause  →  paused
paused   →  start  →  running   (équivalent à resume)
paused   →  resume →  running
running  →  stop   →  stopped
paused   →  stop   →  stopped
```

---

## 🐛 Dépannage rapide

```bash
# Port 1883 (MQTT) occupé
lsof -i :1883
kill -9 <PID>

# Port 8000 (API) occupé
lsof -i :8000
kill -9 <PID>

# Port 8501 (Streamlit) occupé
lsof -i :8501
kill -9 <PID>

# Broker MQTT not reachable
docker ps | grep mosquitto
# Si absent, relancer Terminal 1

# Tests échouent
pip install --upgrade -r requirements.test.txt
pytest tests/ --tb=short  # Affiche plus de détails
```

---

## 📚 Documentation complète

Voir [`documents/TESTING_GUIDE.md`](TESTING_GUIDE.md) pour guide détaillé.

---

**Prêt à tester ? 🚀**

```bash
# Go ! (5 minutes pour avoir tout up)
conda activate jumeaux-chauds
docker run --rm -d --name mosquitto -p 1883:1883 eclipse-mosquitto:2
python scripts/run_simulator.py --scenario nominal --duration 1m
# Dans un autre terminal :
python scripts/mqtt_observer.py --host localhost
```
