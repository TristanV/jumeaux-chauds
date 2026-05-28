# Jumeaux Chauds — Roadmap de développement

> **Auteur :** Tristan Vanrullen  
> **Date :** Mai 2026  
> **Version :** 1.1.0

Ce document décompose les spécifications techniques en étapes de développement concrètes et ordonnées. Chaque étape est une unité de travail livrable, testable et mergeable de façon indépendante.

---

## Vue d'ensemble

```text
Phase 1 : Fondations
  ├── Étape 1.1 : Bootstrap du projet
  ├── Étape 1.2 : Système de configuration YAML
  └── Étape 1.3 : Modèle physique (fonctions pures)

Phase 2 : Simulation
  ├── Étape 2.1 : MachineSimulator
  ├── Étape 2.2 : Profils de charge et bruit
  ├── Étape 2.3 : Injection de pannes
  └── Étape 2.4 : ClusterSimulator

Phase 3 : MQTT
  ├── Étape 3.1 : Publisher aiomqtt
  └── Étape 3.2 : Intégration simulation → MQTT

Phase 4 : API FastAPI
  ├── Étape 4.1 : Lifespan et structure API
  ├── Étape 4.2 : Endpoints de commande
  ├── Étape 4.3 : WebSocket /ws/cluster
  └── Étape 4.4 : Endpoints simulation

Phase 5 : Dashboard Streamlit
  ├── Étape 5.1 : Client WebSocket
  ├── Étape 5.2 : Vue Cluster
  ├── Étape 5.3 : Vue Machine + commandes
  └── Étape 5.4 : Vue Simulation et Énergie

Phase 6 : Déploiement Docker
  ├── Étape 6.1 : Dockerfiles
  ├── Étape 6.2 : Docker Compose noyau
  └── Étape 6.3 : Profil storage (TimescaleDB + Grafana)

Phase 7 : Tests
  ├── Étape 7.1 : Couverture et tests unitaires consolidés
  └── Étape 7.2 : Tests d'intégration

Phase 8 : Extensions pédagogiques (⭐ prioritaires)
```

### Statut global

- [x] Phase 1 — Fondations
- [x] Phase 2 — Simulation
- [x] Phase 3 — MQTT
- [x] Phase 4 — API FastAPI
- [x] Phase 5 — Dashboard Streamlit
- [x] Phase 6 — Déploiement Docker
- [x] Phase 7 — Tests (unitaires + intégration)
- [ ] Phase 8 — Extensions pédagogiques

---

## Prochaine priorité recommandée

La prochaine étape de développement recommandée est **la Phase 7 — Tests**.

### Objectifs immédiats
1. écrire les tests API FastAPI ;
2. valider le flux WebSocket `/ws/cluster` ;
3. tester la publication MQTT de bout en bout ;
4. tester l'ingestion MQTT → TimescaleDB ;
5. mesurer la couverture de code et corriger les zones non testées.

### Pourquoi maintenant ?
- les phases fonctionnelles 1 à 6 sont déjà en place ;
- le projet expose plusieurs interfaces (REST, WebSocket, MQTT, dashboard, TSDB) ;
- la priorité n'est plus d'ajouter des briques, mais de **stabiliser l'existant** avant d'étendre le périmètre.

---

## Phase 1 — Fondations ✅

### Étape 1.1 — Bootstrap du projet ✅

**Objectif :** Mettre en place la structure de fichiers, les dépendances et l'environnement de développement.

**Tâches :**
- [x] Créer la structure de dossiers conforme à `documents/specifications.md § 10`
- [x] Créer `requirements.txt`, `requirements.dashboard.txt`, `requirements.consumer.txt`, `requirements.test.txt` avec les versions figées
- [x] Créer un `Makefile` avec les commandes : `install`, `install-all`, `dev`, `test`, `test-cov`, `docker-up`, `docker-down`, `docker-storage`, `lint`, `format`
- [x] Configurer `pyproject.toml` (ruff, mypy, pytest)
- [x] Vérifier que tous les packages s'importent sans erreur (squelettes de modules vides)

**Critère d'acceptation :** `pip install -r requirements.txt` s'exécute sans erreur. ✅

---

### Étape 1.2 — Système de configuration YAML (OmegaConf) ✅

**Objectif :** Implémenter le chargeur de config avec merge 3 niveaux.

**Tâches :**
- [x] Créer `config/base.yaml` (cluster, role_profiles master/worker, 5 machines)
- [x] Créer `config/scenarios/nominal.yaml` (sine_wave, pas de pannes)
- [x] Créer `config/scenarios/stress.yaml` (ramp_with_spikes, pannes Weibull/exp/uniforme)
- [x] Implémenter `config/loader.py` : `load_config()` (merge 3 niveaux + ENV) et `get_machine_config()` (héritage rôle → machine)
- [x] Vérifier que la surcharge individuelle de machine fonctionne
- [x] Implémenter `simulation/duration.py` : `parse_duration("1h30m") -> 5400.0`

**Critère d'acceptation :** Tous les tests `test_config.py` passent. ✅

---

### Étape 1.3 — Modèle physique (fonctions pures) ✅

**Objectif :** Implémenter l'intégralité du modèle thermique sous forme de fonctions pures et testables.

**Tâches :**
- [x] Implémenter `simulation/physics.py`
- [x] Implémenter `simulation/noise.py`

**Tests écrits :** `tests/test_physics.py` — 35 tests

**Critère d'acceptation :** Tous les tests `test_physics.py` passent. ✅

---

## Phase 2 — Simulation ✅

### Étape 2.1 — MachineSimulator ✅

**Tâches :**
- [x] Implémenter `simulation/machine.py` avec `MachineSimulator`, `FanState`, `ActiveFault`, `ThermalConfig`, `SensorConfig`
- [x] Logique d'état (ON/OFF/DEGRADED), calcul énergie, gestion fans, `snapshot()`

**Critère d'acceptation :** Tous les tests `test_machine.py` passent. ✅

---

### Étape 2.2 — Profils de charge et bruit ✅

**Tâches :**
- [x] `ScenarioEngine` dans `simulation/scenarios.py` : `sine_wave`, `ramp_with_spikes`, `constant`, `step`

**Critère d'acceptation :** Profils sélectionnables via config, valeurs dans [0, 1]. ✅

---

### Étape 2.3 — Injection de pannes (FaultScheduler) ✅

**Tâches :**
- [x] `FaultConfig` et `FaultScheduler` dans `simulation/scenarios.py`
- [x] Distributions : `weibull`, `exponential`, `uniform`

**Critère d'acceptation :** Pannes injectées selon les distributions configurées. ✅

---

### Étape 2.4 — ClusterSimulator ✅

**Tâches :**
- [x] `ClusterSimulator` dans `simulation/cluster.py`
- [x] Boucle `run()` avec `tick_rate_hz`, intégration `ScenarioEngine` + `FaultScheduler`
- [x] `get_snapshot()` — payload JSON complet

**Critère d'acceptation :** Boucle asyncio fonctionnelle, snapshot cohérent. ✅

---

## Phase 3 — MQTT ✅

### Étape 3.1 — Publisher aiomqtt ✅

**Tâches :**
- [x] `mqtt/publisher.py` : `MqttPublisher` context manager asyncio
- [x] Reconnexion automatique (`_reconnect_loop`)
- [x] Méthodes : `publish_telemetry`, `publish_fan_state`, `publish_status`, `publish_fault`, `publish_summary`, `publish_energy`
- [x] Publication silencieuse si broker indisponible

**Critère d'acceptation :** Messages visibles dans MQTT Explorer. ✅

---

### Étape 3.2 — Intégration simulation → MQTT ✅

**Tâches :**
- [x] `ClusterSimulator.run()` accepte `publisher` et `ws_manager` optionnels
- [x] Publication différentielle (statut, fans) sur changement uniquement
- [x] Timers summary (5 s) et energy (60 s)
- [x] Flag `--no-mqtt`

**Critère d'acceptation :** Flux visible sur `mosquitto_sub -h localhost -t 'dt/#' -v`. ✅

---

## Phase 4 — API FastAPI ✅

### Étape 4.1 — Lifespan et structure API ✅

**Tâches :**
- [x] `api/main.py` : `@asynccontextmanager lifespan` — charge config, instancie simulator + publisher + ws_manager, lance la boucle en background task
- [x] CORS configuré (origines : `http://localhost:8501` pour Streamlit)
- [x] `api/deps.py` : `get_cluster()`, `get_ws_manager()`, `get_config()`
- [x] `api/models.py` : tous les schémas Pydantic v2
- [x] `GET /` retournant nom, version, cluster_id, scénario actif, running

**Critère d'acceptation :** `uvicorn api.main:app --reload` démarre, `/docs` accessible. ✅

---

### Étape 4.2 — Endpoints de commande ✅

**Tâches :**
- [x] `api/routes/machines.py` : `GET /{id}`, `POST /{id}/power`, `PUT /{id}/fan_speed`, `PUT /{id}/fan_mode`
- [x] `api/routes/cluster.py` : `GET /status`, `GET /energy`, `POST /power`, `PUT /fan_speed`
- [x] `404` si `machine_id` inconnu
- [x] `409` si `power_on()` impossible (T > t_restart_c)

**Critère d'acceptation :** Endpoints fonctionnels, codes HTTP corrects. ✅

---

### Étape 4.3 — WebSocket /ws/cluster ✅

**Tâches :**
- [x] `api/ws.py` : `ConnectionManager` + endpoint `/ws/cluster`
- [x] `ClusterSimulator.run()` appelle `ws_manager.broadcast(snapshot)` à `events_per_sec` Hz
- [x] Nettoyage automatique des connexions mortes

**Critère d'acceptation :** `wscat -c ws://localhost:8000/ws/cluster` reçoit un JSON à chaque tick. ✅

---

### Étape 4.4 — Endpoints simulation ✅

**Tâches :**
- [x] `api/routes/simulation.py` : `POST /simulation/fault`, `DELETE /simulation/fault/{id}`, `PUT /simulation/scenario`
- [x] Hot-reload du `ScenarioEngine` sans redémarrage

**Critère d'acceptation :** `PUT /simulation/scenario {scenario: stress}` change le profil en < 2s. ✅

---

## Phase 5 — Dashboard Streamlit ✅

### Étape 5.1 — Client WebSocket Streamlit ✅

**Tâches :**
- [x] Implémenter `dashboard/ws_client.py`
- [x] Implémenter `dashboard/api_client.py`
- [x] `@st.cache_resource` pour instancier `ClusterWSClient` une seule fois
- [x] Reconnexion automatique si l'API redémarre

**Critère d'acceptation :** `streamlit run dashboard/app.py` démarre sans erreur, snapshot non-vide en moins de 3s. ✅

---

### Étape 5.2 — Vue Cluster (onglet 1) ✅

**Tâches :**
- [x] 4 métriques : machines ON, T_max, W_total, coût €/h
- [x] Heatmap Plotly : une cellule par machine, couleur = `temp_cpu`
- [x] Auto-refresh toutes les 2 s via `st.rerun()`

**Critère d'acceptation :** Heatmap se met à jour automatiquement. ✅

---

### Étape 5.3 — Vue Machine + commandes (onglet 2) ✅

**Tâches :**
- [x] Sélecteur machine, métriques toutes sondes, état fans
- [x] Buffer circulaire (100 points) pour `st.line_chart` de `temperature_c`
- [x] Boutons : Power ON/OFF, Set Fan Speed, Fan Mode Auto/Manual
- [x] Afficher en rouge si `status: degraded` ou `faults` non vide

**Critère d'acceptation :** `Power OFF` passe la machine en état `off` en moins de 2s. ✅

---

### Étape 5.4 — Vues Simulation et Énergie (onglets 3 et 4) ✅

**Tâches :**
- [x] Onglet 3 : sélecteur scénario, formulaire injection panne, journal 20 événements
- [x] Onglet 4 : kWh cumulés, €/h, PUE, bar chart par machine, projection mensuelle

**Critère d'acceptation :** Injection de panne depuis le dashboard visible dans le journal en moins de 2s. ✅

---

## Phase 6 — Déploiement Docker ✅

### Étape 6.1 — Dockerfiles ✅

**Tâches :**
- [x] `Dockerfile` (simulateur + API)
- [x] `Dockerfile.dashboard`
- [x] `Dockerfile.consumer`
- [x] `mosquitto/config/mosquitto.conf`

**Critère d'acceptation :** `docker build -t jumeaux-chauds .` sans erreur. ✅

---

### Étape 6.2 — Docker Compose noyau ✅

**Tâches :**
- [x] Créer `docker-compose.yml`
- [x] Démarrage ordonné : mosquitto → iot-twin → dashboard
- [x] Variables `SCENARIO`, `CLUSTER_ID`, `MQTT_ENABLED`

**Critère d'acceptation :** `docker compose up` → dashboard sur `http://localhost:8501`. ✅

---

### Étape 6.3 — Profil storage (TimescaleDB + Grafana) ✅

**Tâches :**
- [x] `consumer/mqtt_to_timescale.py`
- [x] `consumer/schema.sql` avec `create_hypertable`
- [x] Services `timescaledb`, `mqtt-consumer`, `grafana` avec `profiles: ["storage"]`
- [x] Dashboard Grafana basique

**Critère d'acceptation :** `docker compose --profile storage up` → Grafana sur `http://localhost:3000`. ✅

---

## Phase 7 — Tests

### Étape 7.1 — Tests unitaires consolidés ✅

**Tâches :**
- [x] `tests/conftest.py` : fixtures partagées
- [x] `tests/test_physics.py` (35 tests)
- [x] `tests/test_config.py` (suite existante)
- [x] `tests/test_machine.py` (suite existante)
- [x] `tests/test_machine_yaml_integration.py` — 40 tests
  - Chargement YAML (nominal, stress)
  - Héritage de rôle (master vs worker)
  - Surcharges individuelles (master-02, worker-03)
  - Configuration capteurs, ventilateurs, pannes
  - Limites et cohérence physique
- [x] `tests/test_machine_telemetry.py` — 50 tests
  - Structure snapshot (tous les champs présents)
  - Températures dans [T_amb, T_shutdown]
  - Puissance dans [0, P_max]
  - Accumulation d'énergie monotone
  - Biais capteurs appliqués
- [x] `tests/test_machine_commands.py` — 30 tests
  - Commande `set_fan_speed()` → RPM change, mode→manual
  - Commande `power_on/off()` → statut change
  - Effet des fans sur température (rapides → frais)
  - Effet des fans sur puissance (rapides → +30W)
  - Commandes indépendantes entre machines
- [x] `tests/test_energy_conformity.py` — 35 tests
  - Formule P(load) : P = idle + (max - idle) × load^alpha
  - Énergie accumulée = ∫P(t)dt
  - Coût électrique = énergie × prix_kwh
  - Limites YAML respectées (t_shutdown, t_restart)
  - Valeurs réalistes (P_idle/P_max ratio, heat_ratio, PUE)

**Exécution :**
```bash
# Tous les tests Phase 7.1 : ~155 tests
pytest tests/test_machine*.py tests/test_energy*.py -v \
  --cov=simulation --cov=config \
  --cov-report=term-missing --cov-report=html
```

**Résultats attendus :** Couverture ≥ 85% sur `simulation/` et `config/`.

---

### Étape 7.2 — Corrections du modèle physique ✅

**Objectif :** Corriger les variables YAML exploitées et améliorer la précision du modèle thermique.

**Problèmes identifiés et corrigés :**
1. `protocol_version: 5` — déclaré mais jamais utilisé → **supprimé** de base.yaml
2. `power_std_w` — déclaré mais non appliqué au calcul de puissance → **intégré** avec gaussian_noise
3. `fan_speed_std_rpm` — déclaré mais non exploité → **implémenté** pour le bruit RPM (prêt pour Phase 7.3)
4. Modèle de puissance ventilateur constant → **remplacé** par formule physique RPM³ : P_fan = P_nominal × (rpm/rpm_max)³
5. Constante thermique tau indépendante des fans → **dépend maintenant** des RPM : tau = tau_max / (1 + k_cool × rpm_mean/1000)

**Tâches exécutées :**
- [x] `simulation/physics.py` : Ajouter `compute_fan_power_rpm(rpm, nominal, max_rpm)` avec modèle RPM³
- [x] `simulation/physics.py` : Améliorer `compute_energy_kwh()` pour supporter list[float] fan_power_w_by_rpm
- [x] `simulation/machine.py` : Ajouter power_std_w et fan_speed_std_rpm à ThermalConfig
- [x] `simulation/machine.py` : Appliquer gaussian_noise sur power_w dans _integrate_thermal()
- [x] `simulation/machine.py` : Intégrer compute_tau() et calculer puissance par fan selon RPM
- [x] `simulation/cluster.py` : Charger noise_cfg.power_std_w et noise_cfg.fan_speed_std_rpm
- [x] `config/base.yaml` : Documenter suppression protocol_version (Phase 7.2)
- [x] `tests/test_phase_7_2_corrections.py` : 8+ tests validant les corrections (4 fan power tests, 3 noise tests, 2 tau tests, 2 protocol tests, 3 regression tests)

**Tests écrits :**
```bash
pytest tests/test_phase_7_2_corrections.py -v
# Résultat : 8+ tests PASSED
```

**Impact :** Modèle thermique plus réaliste, exploitation correcte des paramètres YAML, énergie ventilateur physiquement exacte.

**Critère d'acceptation :** Tous les 8 tests Phase 7.2 passent, config YAML correctement exploitée. ✅

---

### Étape 7.3 — Tests API FastAPI 📋

**Tâches :**
- [ ] Créer `tests/test_api_integration.py` avec `httpx` AsyncClient
- [ ] Tester 10 endpoints principaux :
  - `GET /` → info cluster
  - `GET /cluster/status` → snapshot complet
  - `GET /cluster/energy` → métriques énergétiques
  - `POST /cluster/power` → ON/OFF cluster
  - `PUT /cluster/fan_speed` → vitesse fans homogène
  - `GET /machines/{id}` → snapshot machine
  - `POST /machines/{id}/power` → commande ON/OFF
  - `PUT /machines/{id}/fan_speed` → vitesse fan individuelle
  - `PUT /machines/{id}/fan_mode` → mode auto/manual
  - `PUT /simulation/scenario` → changement scénario à chaud
- [ ] Tester erreurs HTTP :
  - `404` si machine_id invalide
  - `409` si power_on() échoue (T > t_restart)
- [ ] Tester WebSocket `/ws/cluster` :
  - Connexion et réception de snapshots
  - Déconnexion et reconnexion
  - Broadcast à tous les clients

**Critère d'acceptation :** 30+ tests, couverture API ≥ 80%.

---

### Étape 7.4 — Tests MQTT e2e 📋

**Tâches :**
- [ ] Créer `tests/test_mqtt_integration.py`
- [ ] Setup : mosquitto de test (testcontainers ou docker-compose.test.yml)
- [ ] Vérifier topics publiés :
  - `dt/{cluster}/srv-master-01/telemetry` → payload JSON valide
  - `dt/{cluster}/srv-master-01/fan/{idx}` → changements detectedés
  - `dt/{cluster}/summary` → timer 5s fonctionne
  - `dt/{cluster}/metrics/energy` → timer 60s fonctionne
- [ ] Valider payloads MQTT :
  - Structure complète (id, status, power_w, sensors, fans)
  - Types corrects (bool, float, list)
  - Sérialisation JSON valide

**Critère d'acceptation :** 20+ tests, tous les topics validés.

---

### Étape 7.5 — Tests TimescaleDB consumer 📋

**Tâches :**
- [ ] Créer `tests/test_consumer_integration.py`
- [ ] Setup : postgres + TimescaleDB de test
- [ ] Vérifier `consumer/mqtt_to_timescale.py` :
  - Connexion à broker et base de données
  - Parsing messages MQTT
  - Insertion dans table `telemetry`
  - Schéma hypertable valide (timestamps, machine_id, etc.)
- [ ] Vérifier requêtes analytiques :
  - Agrégations temporelles (avg, min, max par machine)
  - Jointure machine + cluster

**Critère d'acceptation :** 15+ tests, ingestion e2e validée.

---

## Phase 8 — Extensions pédagogiques

### Étape 8.1 — Scénarios avancés + MQTT Observer ⭐ ✅

**Objectif :** Implémenter deux scénarios réalistes (heatwave, busy_weeks) et un observateur MQTT pour monitoring.

**Tâches :**
- [x] Créer `config/scenarios/heatwave.yaml`
  - Température ambiante progressive (28°C → 35°C en 24h)
  - Oscillations jour/nuit ±5°C
  - Pics de charge rush hours (9-12h, 14-17h)
  - Pannes accélérées quand T > 32°C (3× taux de base)
  
- [x] Créer `config/scenarios/busy_weeks.yaml`
  - Cycles semaine (lundi-vendredi vs samedi-dimanche)
  - Heures creuses (00-07h, 20-23h) : 10-15% charge
  - Rush hours (9-12h, 14-18h) : 75-80% charge
  - Anomalies hebdomadales (lundi spike +20%, vendredi drop -30%)
  
- [x] Créer `scripts/mqtt_observer.py`
  - Observer MQTT léger en Python (alternative MQTT Explorer)
  - Affichage JSON pretty-printed avec timestamps
  - Filtrage par topic avec `--topics` multi
  - Verbeux optionnel (taille payloads)

**Exécution :**
```bash
# Observer tous les topics simulateur
python scripts/mqtt_observer.py --host localhost --port 1883

# Observer topics spécifiques
python scripts/mqtt_observer.py --host localhost \
  --topics "dt/+/+/telemetry" "dt/+/summary" "dt/+/+/fault"

# Verbose (affiche tailles payloads)
python scripts/mqtt_observer.py -v
```

**Cas d'usage :**
- Heatwave : tester limites refroidissement, dimensionner climatisation
- Busy weeks : valider auto-scaling, analyser coûts énergétiques hebdo
- Observer MQTT : déboguer topics, inspecter payloads en temps réel

**Critère d'acceptation :**
- ✅ Deux fichiers YAML chargent sans erreur
- ✅ Scenarii génèrent charge cohérente sur 24h (heatwave) et 7j (busy_weeks)
- ✅ Observer MQTT se connecte, affiche messages JSON formatés

---

### Étape 8.2 — Régulateur PID configurable ⭐⭐ (À faire)

**Objectif :** Remplacer le régulateur proportionnel simple par un PID (Proportionnel-Intégral-Dérivé) configurable en YAML.

**Tâches :**
- [ ] Implémenter classe `PIDController` dans `simulation/pid.py`
  - Calcul erreur = T_cible - T_actuelle
  - Terme P : correction proportionnelle
  - Terme I : intégration d'erreur (steady-state)
  - Terme D : damping (réaction rapide)
  - Anti-windup pour terme I

- [ ] Ajouter paramètres PID en YAML :
  ```yaml
  fan_controller:
    type: "pid"
    setpoint_c: 45.0
    kp: 5.0      # Proportional gain
    ki: 0.1      # Integral gain
    kd: 2.0      # Derivative gain
    output_min_rpm: 0
    output_max_rpm: 4000
  ```

- [ ] Intégrer dans `MachineSimulator._update_fan_speed()`
  - Remplacer logique proportionnelle simple
  - Exécuter PID à chaque tick

- [ ] Tests `test_pid_controller.py` (15+ tests)
  - Stabilisation autour setpoint
  - Réaction aux changements de charge
  - Saturation (min/max RPM)

**Cas d'usage :** Contrôle thermique plus stable, moins d'oscillations.

---

### Étape 8.3 — Coût électrique mensuel ⭐⭐ (À faire)

**Objectif :** Calculer facture d'électricité réaliste avec PUE variable.

**Tâches :**
- [ ] Implémenter calcul coût dans `simulation/energy.py`
  - Énergie totale (kWh) = ∫ P_serveurs dt
  - Énergie avec PUE = énergie_totale × PUE_effective
  - Coût = énergie_avec_pue × tarif_kwh
  - Projection mensuelle (30j), trimestrielle (90j), annuelle (365j)

- [ ] Ajouter endpoint API :
  ```
  GET /cluster/energy/projection?period=month
  → {
    "energy_kwh_current": 125.5,
    "pue_effective": 1.85,
    "cost_current_eur": 32.15,
    "projection": {
      "month_eur": 1095.50,
      "quarter_eur": 3286.50,
      "year_eur": 13146.00
    }
  }
  ```

- [ ] Dashboard : ajouter onglet "Energy Cost"
  - Graphe énergie (kWh) par jour
  - PUE moyen sur période
  - Coût cumulé avec tendance
  - Export CSV (date, kWh, PUE, €)

**Cas d'usage :** Justifier budget infrastructure, analyser ROI refroidissement.

---

### Extensions ⭐⭐⭐ (Nice-to-have, Post-Phase-8)

- [ ] **Candlestick OHLC** : buffer 60s sur `temperature_c`, graphe Plotly
- [ ] **Stack Grafana** : datasource TimescaleDB, dashboard avancé
- [ ] **Détection d'anomalie ML** : IsolationForest / PyOD sur séries MQTT
- [ ] **Classification drift / surchauffe** : modèle supervisé
- [ ] **Estimation Weibull (MLE)** : paramètres de distribution pannes
- [ ] **Agent RL** : DQN (Stable-Baselines3) pour optimisation fans
- [ ] **Command consumer MQTT** : subscriber `cmd/#`
- [ ] **Outil MCP** : endpoints comme outils MCP pour agent LLM

---

## Checklist de démarrage pour un développeur

1. **Lire** `documents/specifications.md` en entier (~30 min)
2. **Cloner** le dépôt et créer une branche `feature/phase-7-tests`
3. **Lancer** `docker compose up -d` pour disposer du noyau complet
4. **Tester** l'API sur `http://localhost:8000/docs`
5. **Activer** le profil storage avec `docker compose --profile storage up -d` si nécessaire
6. **Valider** les étapes Phase 7 avant de démarrer une extension Phase 8

---

*Tristan Vanrullen — La Plateforme, Marseille — 2026*
