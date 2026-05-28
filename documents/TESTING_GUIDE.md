# Jumeaux Chauds — Guide Complet de Test et Démarrage

> **Objectif :** Tester toutes les couches de l'application étape par étape, sans Docker, en suivant l'architecture.

**Table des matières :**
1. [Configuration initiale](#1-configuration-initiale)
2. [Phase 1 : Tests unitaires (fondations)](#2-phase-1--tests-unitaires-fondations)
3. [Phase 2 : Tests du modèle physique](#3-phase-2--tests-du-modèle-physique)
4. [Phase 3 : Tests de la simulation](#4-phase-3--tests-de-la-simulation)
5. [Phase 4 : Démarrage du broker MQTT](#5-phase-4--démarrage-du-broker-mqtt)
6. [Phase 5 : Lancement de la simulation avec publication MQTT](#6-phase-5--lancement-de-la-simulation-avec-publication-mqtt)
7. [Phase 6 : Observation MQTT](#7-phase-6--observation-mqtt)
8. [Phase 7 : Tests API FastAPI](#8-phase-7--tests-api-fastapi)
9. [Phase 8 : Dashboard Streamlit](#9-phase-8--dashboard-streamlit)
10. [Scénarios avancés (Phase 8.1)](#10-scénarios-avancés-phase-81)

---

## 1. Configuration initiale

### 1.1 Prérequis
```bash
# Créer/activer l'environnement Conda
conda create -n jumeaux-chauds python=3.12 -y
conda activate jumeaux-chauds

# Installer les dépendances
pip install -r requirements.txt

# Optionnel : dépendances de test
pip install -r requirements.test.txt
```

### 1.2 Vérifier l'installation
```bash
# Vérifier que tous les imports fonctionnent
python -c "from simulation.cluster import ClusterSimulator; print('✓ Imports OK')"

# Vérifier la config
python -c "from config.loader import load_config; cfg = load_config('nominal'); print(f'✓ Config loaded: {cfg.cluster_id}')"
```

---

## 2. Phase 1 — Tests unitaires (fondations)

### 2.1 Tests de configuration YAML
```bash
# Tester le chargement et merge de la configuration
pytest tests/test_config.py -v

# Résultat attendu : ✅ tous les tests PASSED
```

**Cas testés :**
- Chargement base.yaml
- Merge avec scénarios (nominal, stress, heatwave, busy_weeks)
- Héritage de rôle (master → worker surcharge)
- Surcharges individuelles

### 2.2 Tests du modèle physique
```bash
# Tester les fonctions pures d'équation thermique
pytest tests/test_physics.py -v

# Résultat attendu : ✅ 35 tests PASSED
```

**Cas testés :**
- Stabilisation température sous différentes charges
- Effet des fans sur refroidissement
- Limites physiques (T_shutdown, P_max)
- Bruit thermique

### 2.3 Tous les tests Phase 7.1
```bash
# Couverture complète des fondations (155+ tests)
pytest tests/test_machine*.py tests/test_energy*.py -v --cov=simulation --cov=config --cov-report=term-missing

# Résultat attendu : ✅ ~155 tests PASSED, 85%+ coverage
```

---

## 3. Phase 2 — Tests du modèle physique

### 3.1 Tests spécifiques aux machines
```bash
# Tests snapshot structure, limites physiques
pytest tests/test_machine_telemetry.py -v

# Tests commandes (power, fan_speed, mode)
pytest tests/test_machine_commands.py -v

# Tests conformité énergétique
pytest tests/test_energy_conformity.py -v

# Résultat attendu : ✅ ~115 tests PASSED
```

---

## 4. Phase 3 — Tests de la simulation

### 4.1 Tests MQTT Publisher (sans broker requis)
```bash
# Tests configuration MQTT, topic construction, payloads
pytest tests/test_mqtt_integration.py -v

# Résultat attendu : ✅ 18 tests PASSED
```

**Cas testés :**
- Construction topics (dt/cluster/machine/*)
- Structure payloads JSON
- QoS levels (0 pour telemetry, 1 pour events)
- Sérialisation JSON

### 4.2 Tests Consumer MQTT (sans broker ni TimescaleDB requis)
```bash
# Tests parsing topics, payloads, conversion timestamps, dispatch
pytest tests/test_consumer_integration.py -v

# Résultat attendu : ✅ 28 tests PASSED
```

**Cas testés :**
- Regex topic parsing
- Extraction cluster/machine/kind
- JSON payload parsing
- Conversion ISO 8601 timestamps
- Calcul fan RPM average
- Message dispatch logic

---

## 5. Phase 4 — Démarrage du broker MQTT

### 5.1 Lancer Mosquitto seul (sans Docker Compose)

**Option A : Avec Docker (broker seul)**
```bash
# Démarrer Mosquitto en background
docker run -d --name mosquitto -p 1883:1883 -p 9001:9001 \
  eclipse-mosquitto:2

# Vérifier la connexion
mosquitto_sub -h localhost -t '$SYS/#' -v &
sleep 2

# Arrêter le test
pkill mosquitto_sub

# Nettoyer
docker stop mosquitto
docker rm mosquitto
```

**Option B : Installation native (Linux/macOS)**
```bash
# Installation
brew install mosquitto  # macOS
# ou
sudo apt-get install mosquitto mosquitto-clients  # Linux

# Démarrer le service
mosquitto -v

# Dans un autre terminal, vérifier
mosquitto_sub -h localhost -t '$SYS/#'
```

### 5.2 Tester la connectivité MQTT
```bash
# Terminal 1 : Subscribe à tous les topics
mosquitto_sub -h localhost -t "dt/#" -v

# Terminal 2 : Publier un message de test
mosquitto_pub -h localhost -t "dt/test/topic" -m '{"test": "message"}'

# Résultat : Terminal 1 reçoit "dt/test/topic {"test": "message"}"
```

---

## 6. Phase 5 — Lancement de la simulation avec publication MQTT

### 6.1 Démarrer le broker MQTT d'abord
```bash
# Terminal 1 : Broker MQTT
docker run --name mosquitto -p 1883:1883 eclipse-mosquitto:2
# (garder ouvert)
```

### 6.2 Lancer le simulateur avec MQTT activé

**Scénario nominal (par défaut)**
```bash
# Terminal 2 : Simulateur + Publisher MQTT
python scripts/run_simulator.py --scenario nominal --duration 1m

# Résultat attendu :
# ✓ Config loaded: cluster_alpha
# ✓ ClusterSimulator initialized
# ✓ MQTT Publisher connecting to localhost:1883
# ✓ Publishing to dt/cluster_alpha/... topics
# [tick 0] 5 machines, avg_temp=22.5°C, power=250W
# [tick 1] 5 machines, avg_temp=22.6°C, power=251W
# ... (continue pour 1 minute)
```

**Durées possibles :**
```bash
python scripts/run_simulator.py --scenario nominal --duration 10s   # 10 secondes
python scripts/run_simulator.py --scenario nominal --duration 1m    # 1 minute
python scripts/run_simulator.py --scenario nominal --duration 5m    # 5 minutes
python scripts/run_simulator.py --scenario nominal --duration 1h    # 1 heure
```

### 6.3 Vérifier la publication MQTT

**Terminal 3 : Observer les messages**
```bash
# Option 1 : observer simple
mosquitto_sub -h localhost -t "dt/#" -v

# Option 2 : observer avec notre script
python scripts/mqtt_observer.py --host localhost --topics "dt/#"

# Option 3 : observer spécifique (telemetry only)
mosquitto_sub -h localhost -t "dt/cluster_alpha/+/telemetry" -v
```

**Messages attendus :**
```
dt/cluster_alpha/srv-master-01/telemetry {"id":"srv-master-01","status":"on","temperature_c":35.2,...}
dt/cluster_alpha/srv-master-01/power {"power_w":180.5,"energy_kwh_cumulated":0.051}
dt/cluster_alpha/srv-master-01/temp/cpu {"sensor_id":"temp_cpu","temp_c":35.2}
dt/cluster_alpha/summary {"timestamp":"2026-05-28T14:30:00.000Z","machines_on":5,"avg_temp_c":35.1,...}
```

---

## 7. Phase 6 — Observation MQTT

### 7.1 Observer MQTT Explorer (GUI recommandée)

**Installation :**
```bash
# Télécharger depuis https://mqtt-explorer.com/
# Ou via Snap (Linux) :
snap install mqtt-explorer

# Lancer MQTT Explorer
mqtt-explorer
```

**Configuration :**
- Broker: `localhost`
- Port: `1883`
- Protocol: `mqtt://`
- Topic filter: `dt/#`

### 7.2 Observer avec mosquitto_sub (CLI simple)
```bash
# Observer tous les topics
mosquitto_sub -h localhost -t "dt/#" -v

# Observer topics spécifiques
mosquitto_sub -h localhost -t "dt/cluster_alpha/srv-master-01/telemetry" -v
mosquitto_sub -h localhost -t "dt/cluster_alpha/+/fault" -v
mosquitto_sub -h localhost -t "dt/cluster_alpha/summary" -v

# Sauvegarder dans un fichier log
mosquitto_sub -h localhost -t "dt/#" -v > mqtt_log.txt &
```

### 7.3 Observer avec notre script mqtt_observer.py
```bash
# Observer tous les topics (défaut)
python scripts/mqtt_observer.py --host localhost

# Observer topics spécifiques
python scripts/mqtt_observer.py --host localhost \
  --topics "dt/+/+/telemetry" "dt/+/summary"

# Mode verbose (affiche tailles payloads)
python scripts/mqtt_observer.py --host localhost -v

# Aide
python scripts/mqtt_observer.py --help
```

**Output attendu :**
```
✓ Connected to localhost:1883
✓ Subscribing to: dt/#
--------------------------------------------------------------------------------

[14:30:45.123] Topic: dt/cluster_alpha/srv-master-01/telemetry (QoS 0)
  {
    "id": "srv-master-01",
    "status": "on",
    "temperature_c": 42.5,
    "power_w": 180.3,
    ...
  }
```

---

## 8. Phase 7 — Tests API FastAPI

### 8.1 Démarrer l'API FastAPI

**Sans MQTT (plus rapide pour tester API seule)**
```bash
# Terminal : API seule (MQTT disabled)
export MQTT_ENABLED=0
uvicorn api.main:app --reload --port 8000

# Résultat attendu :
# INFO:     Uvicorn running on http://127.0.0.1:8000
# INFO:     Application startup complete
```

**Avec MQTT (si broker disponible)**
```bash
# Terminal (broker MQTT doit tourner)
uvicorn api.main:app --reload --port 8000

# Résultat attendu :
# ✓ MQTT Publisher connected to localhost:1883
# INFO:     Uvicorn running on http://127.0.0.1:8000
```

### 8.2 Tester les endpoints REST

**Documentation interactive (recommandé)**
```bash
# Ouvrir dans navigateur
open http://localhost:8000/docs
# ou
xdg-open http://localhost:8000/docs  # Linux
```

**Tests via curl**

```bash
# 1. Info cluster
curl http://localhost:8000/

# 2. Status complet
curl http://localhost:8000/cluster/status

# 3. Métriques énergétiques
curl http://localhost:8000/cluster/energy

# 4. Allumer tout le cluster
curl -X POST http://localhost:8000/cluster/power -H "Content-Type: application/json" \
  -d '{"power_on": true}'

# 5. Éteindre tout le cluster
curl -X POST http://localhost:8000/cluster/power \
  -d '{"power_on": false}'

# 6. Vitesse fans homogène
curl -X PUT http://localhost:8000/cluster/fan_speed \
  -d '{"target_rpm": 3000}'

# 7. Info machine spécifique
curl http://localhost:8000/machines/srv-master-01

# 8. Power ON une machine
curl -X POST http://localhost:8000/machines/srv-master-01/power \
  -d '{"power_on": true}'

# 9. Power OFF une machine
curl -X POST http://localhost:8000/machines/srv-master-01/power \
  -d '{"power_on": false}'

# 10. Fan speed individuelle
curl -X PUT http://localhost:8000/machines/srv-master-01/fan_speed \
  -d '{"target_rpm": 2500}'

# 11. Fan mode (auto/manual)
curl -X PUT http://localhost:8000/machines/srv-master-01/fan_mode \
  -d '{"mode": "manual"}'

# 12. Injecter une panne
curl -X POST http://localhost:8000/simulation/fault \
  -d '{"machine_id": "srv-master-01", "fault_type": "cpu_throttle"}'

# 13. Changer de scénario
curl -X PUT http://localhost:8000/simulation/scenario \
  -d '{"scenario": "stress"}'
```

### 8.3 Tests avec pytest

```bash
# Tests API complets (23 tests)
pytest tests/test_api_integration.py -v

# Résultat attendu : ✅ 23 tests PASSED
```

**Cas testés :**
- Endpoints REST (GET, POST, PUT)
- Erreurs HTTP (404, 409)
- WebSocket connexion
- Format réponses

### 8.4 Tester WebSocket

**Via wscat (npm install -g wscat)**
```bash
# Connection WebSocket
wscat -c ws://localhost:8000/ws/cluster

# Résultat attendu : reçoit JSON snapshot chaque seconde
# {"cluster_id":"cluster_alpha","machines":{...},"timestamp":"2026-05-28T14:30:00Z"}
```

---

## 9. Phase 8 — Dashboard Streamlit

### 9.1 Démarrer le dashboard

**Prérequis : API FastAPI doit tourner**
```bash
# Terminal 1 : API (MQTT optionnel)
export MQTT_ENABLED=0
uvicorn api.main:app --port 8000
```

**Lancer le dashboard**
```bash
# Terminal 2 : Dashboard
streamlit run dashboard/app.py

# Résultat attendu :
# Collecting usage statistics ...
# Watching .../dashboard/app.py to reload :)
# Local URL: http://localhost:8501
```

### 9.2 Accéder au dashboard
```bash
# Ouvrir dans navigateur
open http://localhost:8501
# ou
xdg-open http://localhost:8501  # Linux
```

### 9.3 Fonctionnalités du dashboard

| Onglet | Fonction | Tester |
|--------|----------|--------|
| **Cluster** | Vue globale, heatmap température | Vérifier couleurs changent |
| **Machines** | Détail machine, commandes | Cliquer Power ON/OFF |
| **Simulation** | Scénarios, injection pannes | Changer scénario, injecter panne |
| **Énergie** | kWh cumulés, PUE, coût | Vérifier accumulation |

---

## 10. Scénarios avancés (Phase 8.1)

### 10.1 Scénario Heatwave (vague de chaleur)

**Lancer 24h de simulation**
```bash
# Terminal 1 : Broker MQTT
docker run --name mosquitto -p 1883:1883 eclipse-mosquitto:2

# Terminal 2 : Simulateur heatwave (24 heures)
python scripts/run_simulator.py --scenario heatwave --duration 24h

# Résultat : T_amb progresse 28→35°C, pannes accélérées à T>32°C
```

**Observer en temps réel**
```bash
# Terminal 3 : Observer MQTT
python scripts/mqtt_observer.py --host localhost \
  --topics "dt/+/+/telemetry" "dt/+/+/fault"

# Ou avec dashboard Streamlit
streamlit run dashboard/app.py
```

**Analyse :**
- Observer T_amb monter progressivement
- Compter augmentation du taux de pannes
- Voir fans accélérer sans suffisamment refroidir

### 10.2 Scénario Busy Weeks (semaines chargées)

**Lancer 7 jours de simulation**
```bash
# Terminal 1 : Broker MQTT
docker run --name mosquitto -p 1883:1883 eclipse-mosquitto:2

# Terminal 2 : Simulateur busy_weeks (7 jours)
python scripts/run_simulator.py --scenario busy_weeks --duration 7d

# Résultat : Cycles lundi-vendredi vs samedi-dimanche, rush hours
```

**Durée personnalisée pour tests rapides**
```bash
# Simuler 1 jour (pour test rapide ~60s simulation time)
python scripts/run_simulator.py --scenario busy_weeks --duration 1d

# Simuler 1 heure (pour test ultra-rapide ~10s simulation time)
python scripts/run_simulator.py --scenario busy_weeks --duration 1h
```

**Observer et analyser**
```bash
# Observer rush hours (pics de charge)
python scripts/mqtt_observer.py --host localhost

# Dans le dashboard : observer puissance augmenter 9-12h et 14-18h
```

---

## 📋 Résumé des commandes par étape

### Étape 1 : Tests unitaires (5 min)
```bash
pytest tests/ -v --cov=simulation --cov=config
```

### Étape 2 : Broker MQTT (5 min)
```bash
# Terminal 1
docker run --name mosquitto -p 1883:1883 eclipse-mosquitto:2

# Terminal 2 (vérifier connectivité)
mosquitto_sub -h localhost -t '$SYS/#'
```

### Étape 3 : Simulation + MQTT (1-5 min)
```bash
# Terminal 2 (arrêter avant ou dans un autre)
python scripts/run_simulator.py --scenario nominal --duration 1m
```

### Étape 4 : Observer MQTT (pendant la simulation)
```bash
# Terminal 3
python scripts/mqtt_observer.py --host localhost
```

### Étape 5 : API FastAPI (continu)
```bash
# Terminal 4
export MQTT_ENABLED=0
uvicorn api.main:app --port 8000

# Puis tester sur http://localhost:8000/docs
```

### Étape 6 : Dashboard Streamlit (continu)
```bash
# Terminal 5
streamlit run dashboard/app.py

# Puis ouvrir http://localhost:8501
```

### Étape 7 : Scénarios avancés (30 min)
```bash
# Terminal 2 (avec broker déjà lancé)
python scripts/run_simulator.py --scenario heatwave --duration 24h
# ou
python scripts/run_simulator.py --scenario busy_weeks --duration 7d
```

---

## 🔍 Dépannage

### Problème : "Connection refused" MQTT
```bash
# Vérifier que Mosquitto tourne
docker ps | grep mosquitto

# Ou si installé nativement
brew services list | grep mosquitto
```

### Problème : "Address already in use" port 8000
```bash
# Tuer le processus existant
lsof -i :8000
kill -9 <PID>

# Ou utiliser un port différent
uvicorn api.main:app --port 8001
```

### Problème : TimeoutError dans le simulateur
```bash
# Réduire la durée de test
python scripts/run_simulator.py --scenario nominal --duration 10s
```

### Problème : MQTT Publisher connection timeout
```bash
# Vérifier broker accessible
telnet localhost 1883
# Ou
python -c "import socket; socket.create_connection(('localhost', 1883))"
```

---

*Tristan Vanrullen — La Plateforme, Marseille — 2026*
