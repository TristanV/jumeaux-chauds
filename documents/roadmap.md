# Jumeaux Chauds — Roadmap de développement

> **Auteur :** Tristan Vanrullen  
> **Date :** Juin 2026  
> **Version :** 1.2.0

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
  ├── Étape 7.2 : Corrections du modèle physique
  ├── Étape 7.3 : Tests API FastAPI
  ├── Étape 7.4 : Tests MQTT e2e
  └── Étape 7.5 : Tests TimescaleDB consumer

Phase 8 : Extensions pédagogiques (⭐ prioritaires)
  ├── Étape 8.1 : Scénarios avancés + MQTT Observer ✅
  ├── Étape 8.4 : Contrôle de vitesse de simulation (🔥 ML Data Gen) ✅
  ├── Étape 8.5 : Bug fixes dashboard + simulation ✅
  ├── Étape 8.6 : Bug fixes tests + config (317/317 tests) ✅
  ├── Étape 8.7 : Affinage thermique (physique réaliste) ✅
  ├── Étape 8.8 : Corrections tests Phase 8.7 (désync k_cool, fault_injection) ✅
  ├── Étape 8.9 : Corrections bugs comportementaux (auto-restart, dashboard, Grafana) ✅
  ├── Étape 8.12 : Refonte architecture speed_multiplier ✅
  │   ├── 8.12A : Correction boucle temps réel (dt_sim fixe, CPU throttle, batch) ✅
  │   └── 8.12B : Script génération corpus ML (batch synchrone, CSV/Parquet) ✅
  ├── Étape 8.2 : Régulateur PID configurable ⏳
  └── Étape 8.3 : Coût électrique mensuel ⏳
```

### Statut global

- [x] Phase 1 — Fondations ✅
- [x] Phase 2 — Simulation ✅
- [x] Phase 3 — MQTT ✅
- [x] Phase 4 — API FastAPI ✅
- [x] Phase 5 — Dashboard Streamlit ✅
- [x] Phase 6 — Déploiement Docker ✅
- [x] Phase 7 — Tests (unitaires + intégration) ✅ — 7.1 à 7.5 complets
- [🔄] Phase 8 — Extensions pédagogiques
  - [x] 8.1 — Scénarios avancés + MQTT Observer ✅ (26-28 mai 2026)
  - [x] 8.4 — Contrôle de vitesse de simulation ✅ (29 mai 2026)
  - [x] 8.5 — Bug fixes (pannes, speed multiplier) ✅ (3-4 juin 2026)
  - [x] 8.6 — Bug fixes (Tests + Config) ✅ (4 juin 2026) — **317/317 tests, 0 warnings**
    - [x] 8.6.1 — Fix stress.yaml (fault_injection, ramp_duration)
    - [x] 8.6.2 — Fix test_snapshot_with_speed_multiplier (NameError)
    - [x] 8.6.3 — Fix ISO format timestamp comparison
    - [x] 8.6.4 — Fix start_time modification test logic
    - [x] 8.6.5 — Fix test_nominal_lower_load_than_stress (durée insuffisante)
    - [x] 8.6.6 — Fix test_change_start_time_preserves_elapsed (timestamps identiques)
    - [x] 8.6.7 — Fix pytest warnings (asyncio_default_fixture_loop_scope, aiomqtt filter)
    - [x] 8.6.8 — Validation complète (317/317 tests passants, 0 warnings) ✅
  - [x] 8.7 — Affinage thermique (comportement réaliste) ✅ (4-5 juin 2026) — **20/20 tests**
    - [x] 8.7.1 — Formule tau améliorée avec exponent 1.5 (RPM^1.5)
    - [x] 8.7.2 — Clamp de température [T_amb, T_max]
    - [x] 8.7.3 — Sous-pas d'intégration pour stabilité numérique
    - [x] 8.7.4 — Constraints thermiques testées (1x, 60x, 3600x speed_multiplier)
    - [x] 8.7.5 — Suite 20 tests complets (bounds, fans, équilibre, contrôle) ✅
  - [x] 8.8 — Corrections tests désynchronisés Phase 8.7 ✅ (5 juin 2026)
    - [x] 8.8.1 — k_cool_rpm_factor 3.5→2.0 dans test_machine_yaml_integration.py
    - [x] 8.8.2 — k_cool 3.5→2.0 + seuil tau recalibré dans test_phase_7_2_corrections.py
    - [x] 8.8.3 — Désactivation fault_injection dans test_energy_conformity.py
    - [x] 8.8.4 — Correction test fan cooling (ticks insuffisants pour équilibre thermique)
    - [x] 8.8.5 — Fix cluster.py : respect du flag fault_injection.enabled
    - [x] 8.8.6 — Fix conftest.py : k_cool_rpm_factor 3.5→2.0 dans master_thermal_params
  - [x] 8.9 — Corrections bugs comportementaux ✅ (5 juin 2026)
    - [x] 8.9.1 — Fix machine.py : auto-redémarrage après surchauffe (flag _shutdown_by_overheat, OFF→ON si T<t_restart_c)
    - [x] 8.9.2 — Fix machine.py : distinction OFF volontaire vs OFF par surchauffe
    - [x] 8.9.3 — Fix machine.py : état degraded pour surchauffe partielle (95% seuil)
    - [x] 8.9.4 — Fix cluster.py : fréquence publication MQTT proportionnelle au speed_multiplier (Grafana dents de scie)
    - [x] 8.9.5 — Fix dashboard : journal événements permanent dans sidebar (visible tous onglets)
    - [x] 8.9.6 — Fix dashboard : détection automatique transitions (surchauffe, redémarrage, pannes) via diff snapshot
    - [x] 8.9.7 — Fix dashboard : courbes par capteur et par fan dans vue machine (Plotly)
    - [x] 8.9.8 — Fix dashboard : titre graphique "Télémétrie — {machine_id}" (était None/undefined)
    - [x] 8.9.9 — Fix dashboard : onglet Énergie et point d'entrée main() reconstitués (fichier tronqué)
  - [x] 8.10 — Grafana : panel vitesse moyenne ventilateurs par machine ✅ (5 juin 2026)
    - [x] 8.10.1 — Ajout panel timeseries "Vitesse fans (RPM) par machine" (id=5, y=8, h=8)
    - [x] 8.10.2 — Requête SQL sur fan_rpm_avg par machine_id avec $__timeFilter
    - [x] 8.10.3 — Décalage panels existants puissance/stat/pannes de y=8 → y=16
  - [x] 8.11 — Traçabilité des causes de transition d'état + documentation ✅ (5 juin 2026)
    - [x] 8.11.1 — machine.py : attribut last_status_cause renseigné à chaque transition
    - [x] 8.11.2 — publisher.py : paramètre cause dans publish_status() (6 valeurs distinctes)
    - [x] 8.11.3 — cluster.py : transmission de machine.last_status_cause au publisher
    - [x] 8.11.4 — schema.sql : colonne cause TEXT dans table events
    - [x] 8.11.5 — consumer : insertion de la cause dans la table events
    - [x] 8.11.6 — Grafana : remplacement panel "Machines actives" par pie chart 3 secteurs (on/degraded/off)
    - [x] 8.11.7 — Création SPECS_MACHINE_STATUS_TRANSITIONS.md (matrices transitions, comportement, télémétries, comptage)
    - [x] 8.11.8 — Mise à jour specifications.md (section 5.3 + lien vers specs transitions)
  - [x] 8.12 — Refonte architecture speed_multiplier ✅ (6-7 juin 2026)
    - [x] 8.12A — Correction boucle temps réel ✅
      - [x] 8.12A.1 — cluster.py : dt_sim = 1/tick_rate_hz constant (indépendant de speed)
      - [x] 8.12A.2 — cluster.py : CPU throttle branché (asyncio.sleep = 1/throttle_hz)
      - [x] 8.12A.3 — cluster.py : batch_size recalculé à chaque itération (hot-reload vitesse)
      - [x] 8.12A.4 — cluster.py : publier dernier snapshot seulement (pas tous les ticks)
      - [x] 8.12A.5 — machine.py : fault_id UUID — fix dédup pannes (ts_start=None)
      - [x] 8.12A.6 — cluster.py : _format_duration restaurée (fichier tronqué)
      - [x] 8.12A.7 — tests/test_speed_continuity.py : 8 tests monotonie timestamps
    - [x] 8.12B — Script génération corpus ML ✅ (7 juin 2026)
      - [x] 8.12B.1 — scripts/generate_dataset.py : boucle synchrone pure, pas d'asyncio
      - [x] 8.12B.2 — Export CSV et Parquet (pandas/pyarrow)
      - [x] 8.12B.3 — Insert bulk TimescaleDB optionnel (asyncpg COPY)
      - [x] 8.12B.4 — CLI complet : --scenario, --duration, --output, --format, --timescaledb, --no-faults
      - [x] 8.12B.5 — Performance mesurée : ~3 700 ticks/s (1h simulée en 10s, 1j en ~4min)
      - [x] 8.12B.6 — requirements.txt : ajout pandas>=2.0, pyarrow>=14.0
  - [ ] 8.2 — Régulateur PID configurable ⏳ (À démarrer)
  - [ ] 8.3 — Coût électrique mensuel ⏳ (À démarrer)

---

## Prochaine priorité recommandée

La prochaine étape de développement recommandée est **la Phase 8.2 — Régulateur PID configurable**.

> **État au 7 juin 2026 :** Phase 8.12 complète — architecture speed_multiplier corrigée, script génération corpus ML opérationnel (~3 700 ticks/s).

### Contexte Phase 8.12 — Pourquoi cette refonte

**Diagnostic :** l'implémentation actuelle du `speed_multiplier` souffre de deux bugs fondamentaux :

1. **`dt_sim` croît avec la vitesse** : à 3600x, chaque tick représente `dt_sim = 360s` simulés, forçant 3600 sous-pas thermiques par tick. La charge CPU croît linéairement avec la vitesse → crash asyncio à 3600x.

2. **CPU throttle non branché** : `_throttle_interval_s` est calculé à l'init mais jamais utilisé dans la boucle `run()`. La boucle tourne toujours à `tick_rate_hz=10Hz` fixe, ignorant la config throttle.

**Spécification correcte** : `dt_sim = 1/tick_rate_hz = 0.1s` constant. La vitesse multiplie le nombre de ticks simulés par unité de temps réel, pas la taille du pas. La charge CPU reste identique à toutes les vitesses.

**Deux modes distincts :**
- **Mode temps réel/monitoring** (speed ≤ quelques centaines) : boucle asyncio throttlée, batch de ticks simulés par itération, publication du dernier snapshot seulement.
- **Mode génération corpus ML** (besoin : 1 semaine à 1 an de données en quelques minutes) : script synchrone pur sans asyncio/MQTT, boucle Python libre, export direct CSV/Parquet ou bulk insert TimescaleDB. Objectif : ~100k ticks/s → 1 mois de données en ~4 minutes.

### ✅ Phase 8.7 Complétée — Affinage Thermique

**Résultats :**
- ✅ 20/20 tests passants (Temperature bounds, Fan cooling, Numerical stability, Thermal equilibrium, Energy/cooling coherence, Fan auto control, Shutdown/restart)
- ✅ Formule tau améliorée : `tau = tau_max / (1 + k_cool * (RPM/RPM_max)^1.5)`
- ✅ Clamp température [T_amb, 100°C] empêchant T < 0
- ✅ Sous-pas d'intégration pour stabilité numérique (dt_max = 0.1s)
- ✅ Testé jusqu'à 3600x speed_multiplier sans divergence
- ✅ Configuration physique centralisée dans `config/base.yaml`

**Fichiers livrés :**
- `simulation/physics.py` — Modèle thermique Phase 8.7 (277 lignes)
- `simulation/machine.py` — Intégration fan_max_rpm (404 lignes)
- `tests/test_thermal_refinement.py` — Suite 20 tests (455 lignes)
- `config/base.yaml` — Constantes physiques + k_cool=2.0

### Objectifs Phase 8.2 : Régulateur PID
1. Implémenter classe `PIDController` dans `simulation/pid.py` (Kp, Ki, Kd, anti-windup)
2. Ajouter paramètres YAML : setpoint_c, gains, limites RPM
3. Intégrer dans `MachineSimulator._update_fan_speed()`
4. Écrire 15+ tests (stabilisation, overshoot, réaction charge)
5. Valider intégration dashboard (dropdown PID settings)

### Calendrier restant
- Phase 8.2 — Régulateur PID configurable (4-6h)
- Phase 8.3 — Coût électrique mensuel (2-3h)
- Livraison Master 2

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

### Étape 7.3 — Tests API FastAPI ✅

**Tâches :**
- [x] Créer `tests/test_api_integration.py` avec `httpx` AsyncClient — **23 tests**
- [x] Tester 10 endpoints principaux :
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
- [x] Tester erreurs HTTP :
  - `404` si machine_id invalide
  - `409` si power_on() échoue (T > t_restart)
- [x] Tester WebSocket `/ws/cluster` :
  - Connexion et réception de snapshots
  - Déconnexion et reconnexion
  - Broadcast à tous les clients

**Critère d'acceptation :** 23 tests, couverture API ✅

---

### Étape 7.4 — Tests MQTT e2e ✅

**Tâches :**
- [x] Créer `tests/test_mqtt_integration.py` — **18 tests**
- [x] Vérifier topics publiés :
  - `dt/{cluster}/srv-master-01/telemetry` → payload JSON valide
  - `dt/{cluster}/srv-master-01/fan/{idx}` → changements détectés
  - `dt/{cluster}/summary` → structure validée
  - `dt/{cluster}/metrics/energy` → structure validée
- [x] Valider payloads MQTT :
  - Structure complète (id, status, power_w, sensors, fans)
  - Types corrects (bool, float, list)
  - Sérialisation JSON valide
- [x] Convention de nommage topics (machine-level et cluster-level)
- [x] Configuration QoS validée

Note : tests en mode unitaire (sans broker réel) — la connexion broker réelle est couverte par l'intégration Docker.

**Critère d'acceptation :** 18 tests, topics et payloads validés ✅

---

### Étape 7.5 — Tests TimescaleDB consumer ✅

**Tâches :**
- [x] Créer `tests/test_consumer_integration.py` — **28 tests**
- [x] Vérifier `consumer/mqtt_to_timescale.py` :
  - Parsing messages MQTT (telemetry, fault, status, unknown)
  - Regex topics (telemetry, temperature, fault, status, cluster)
  - Extraction données (power, temperature, event_type, fan RPM)
  - Gestion JSON invalide et champs optionnels manquants
  - Timestamps ISO 8601 (format Z et UTC)
- [x] Configuration broker et DSN PostgreSQL validés
- [x] Pattern de souscription MQTT validé

Note : tests en mode unitaire (sans TimescaleDB réel) — l'ingestion e2e est couverte par le profil Docker storage.

**Critère d'acceptation :** 28 tests, logique consumer validée ✅

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

### Étape 8.7 — Affinage Thermique (Comportement Réaliste) ⭐⭐⭐ (À démarrer)

**Objectif :** Corriger les comportements thermiques irréalistes et implémenter des contraintes physiques réalistes.

**Problèmes observés :**
1. Températures deviennent négatives (< 0°C, impossible)
2. Refroidissement par ventilateurs insuffisant
3. Instabilité numérique avec speed_multiplier élevé (> 1s/tick)
4. Équilibre thermique oscille plutôt que converger

**Tâches :**

- [ ] **8.7.1 — Améliorer formule refroidissement fan** (1h)
  - Changer `compute_tau()` : tau = tau_max / (1 + k_cool × (RPM/RPM_max)^1.5)
  - Justification : échange thermique convectif ∝ débit_air^0.6 ≈ RPM^1.5 (plus réaliste)
  - Impact : fans refroidissent 2-3x plus efficacement à RPM max

- [ ] **8.7.2 — Implémenter clamp de température** (1h)
  - Ajouter T_min, T_max en constantes `physics.py`
  - Clamp dans `compute_thermal_step()` : T ∈ [T_amb, T_max]
  - Jamais T < T_amb (température ambiante est limite physique)
  - Jamais T > T_max (arrêt thermique garantit cela)

- [ ] **8.7.3 — Ajouter sous-pas d'intégration numérique** (1.5h)
  - Implémenter dt_max = 0.1s dans `compute_thermal_step()`
  - Si dt > dt_max, subdiviser en sous-pas (stabilité Euler explicite)
  - Essentiel pour speed_multiplier > 1 (dt_simulé peut atteindre 1-600s)

- [ ] **8.7.4 — Écrire tests thermiques complets** (2h)
  - 20+ tests couvrant : limites T, refroidissement fan, stabilité numérique, équilibre
  - Fichier : `tests/test_thermal_refinement.py` (déjà créé)
  - Tests paramétrés : plusieurs speed_multiplier (1x, 60x, 3600x)

- [ ] **8.7.5 — Valider et ajuster paramètres** (1h)
  - Vérifier tau values réalistes (10-100s typiquement)
  - Vérifier k_cool values (1.0-3.0 appropriés)
  - Tester tous les scénarios (nominal, stress, heatwave, busy_weeks)

**Configuration YAML (nouvelles constantes) :**

```yaml
# config/base.yaml — ajouter section physique

physics:
  t_min_c: 0.0                    # Température minimum (température ambiante)
  t_max_c: 100.0                  # Température maximum (arrêt thermique)
  dt_integration_max_s: 0.1       # Pas max pour stabilité numérique

machines:
  srv-master-01:
    thermal:
      tau_max_s: 50.0             # Constante de temps sans fans (s)
      k_cool: 2.0                 # Facteur refroidissement (dimensionless)
      # Formule: tau(RPM) = tau_max / (1 + k_cool × (RPM/5000)^1.5)
```

**Résultats attendus :**

| Comportement | Avant (BUG) | Après (FIXÉ) |
|-------------|-----------|------------|
| T_min | -15°C | ≥ T_amb = 20°C ✅ |
| T_max | > 110°C | ≤ 100°C ✅ |
| Refroidissement fan | Faible | 2-3x plus fort ✅ |
| Stabilité 3600x speed | Oscille/diverge | Stable ✅ |
| Tests thermiques | 0 | 20+ ✅ |

**Documentation :** Fichier créé `documents/PHASE_8_7_THERMAL_REFINEMENT_SPEC.md`

**Critère d'acceptation :**
- ✅ Zéro tempérauture négative (test suit)
- ✅ Tempérauture max respectée (100°C)
- ✅ Refroidissement fan efficace (20+ tests)
- ✅ Stabilité 3600x speed multiplier (pas d'oscillation)
- ✅ 20+ tests thermiques complets, tous passants

---

### Étape 8.4 — Contrôle de vitesse de simulation (🔥 ML Data Gen) ⭐⭐⭐ ✅

**Objectif :** Permettre d'accélérer la simulation pour générer de grandes quantités de données ML rapidement, en évitant la surchauffe CPU.

**Cas d'usage principal :** Entraîner des modèles ML de maintenance prédictive sur des mois/années de données en quelques secondes.

**Tâches :**
- [ ] Ajouter paramètre `simulation.speed_multiplier` en YAML (1.0, 60.0, 3600.0, 86400.0)
- [ ] Implémenter CPU throttling pour limiter fréquence réelle publication (50-500 Hz configurable)
- [ ] Modifier boucle `ClusterSimulator.run()` :
  - Appliquer multiplier à `_t_elapsed_s` chaque tick
  - Throttler MQTT/WebSocket selon CPU throttle, pas les ticks
  - Ajouter méthode `set_speed_multiplier()` pour changement à chaud
- [ ] Ajouter endpoints API :
  - `GET /simulation/speed` → infos vitesse actuelle + throttle
  - `PUT /simulation/speed` → changer vitesse (accepte multiplier ou preset name)
  - `POST /simulation/speed/reset` → reset temps écoulé + énergie
- [ ] Intégrer dashboard Streamlit :
  - Dropdown vitesses prédéfinies (Real-time, 1 min/sec, 1 hour/sec, 1 day/sec)
  - Custom speed input
  - Toggle CPU Throttle + slider target Hz
  - Afficher : temps simulé, snapshots générés, taille estimée données
  - Boutons : Export CSV, Reset Time
- [ ] Implémenter buffer circulaire snapshots (100K max) + export CSV/Parquet
- [ ] Tests (15+ tests) :
  - Changement vitesse à chaud
  - Accumulation temps simulé cohérente
  - CPU throttle fonctionne (fréquence réelle <= target)
  - Export données valide

**Schéma de changement :**

```yaml
# config/base.yaml (nouveau)
simulation:
  speed_multiplier: 1.0              # défaut : real-time
  cpu_throttle_enabled: true
  cpu_throttle_target_hz: 100.0      # ~100 ticks/s réels max
```

**API endpoints :**

```
GET /simulation/speed
→ {
  "speed_multiplier": 3600.0,
  "speed_name": "1 hour/sec",
  "cpu_throttle_enabled": true,
  "cpu_throttle_target_hz": 100.0
}

PUT /simulation/speed
← { "speed_multiplier": 86400.0 }  or  { "speed_name": "1 day/sec" }
→ { "speed_multiplier": 86400.0, "speed_name": "1 day/sec", "message": "..." }
```

**Impact sur données :**

| Multiplier | Temps pour 30j | Snapshots | Taille (brute) | Utilisation |
|-----------|----------------|-----------|----------------|------------|
| 1.0 (real-time) | 30 jours | 2.592M | 13 GB | Monitoring |
| 60.0 (1 min/sec) | 12 heures | 2.592M | 13 GB | Tests rapides |
| 3600.0 (1 hour/sec) | 12 minutes | 2.592M | 13 GB | Prototypage ML |
| 86400.0 (1 day/sec) | 30 secondes | 2.592M | 13 GB | **Production ML** ✅ |

**Documentation :** Fichier `documents/SPECS_SIMULATION_SPEED_MULTIPLIER.md` (détails complets)

**Critère d'acceptation :**
- ✅ Vitesse change à chaud sans redémarrage
- ✅ Temps écoulé accumulé correctement
- ✅ CPU throttle limite fréquence (mesurable : `dt` entre publications)
- ✅ Export CSV contient N snapshots avec colonnes (timestamp, machine_id, temp, power, status)
- ✅ 15+ tests passent

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
