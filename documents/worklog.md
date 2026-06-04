# Jumeaux Chauds — Journal de développement

> **Auteur :** Tristan Vanrullen  
> **Démarrage :** Mai 2026

Ce fichier trace chronologiquement les développements réalisés, les décisions techniques prises et les écarts éventuels par rapport aux spécifications initiales.

---

## 2026-05-18 — Phase 1 : Fondations

### Étape 1.1 — Bootstrap du projet ✅

**Fichiers créés :**
- `requirements.txt` — dépendances simulateur + API (versions figées)
- `requirements.dashboard.txt` — dépendances dashboard Streamlit
- `requirements.consumer.txt` — dépendances consumer TimescaleDB
- `requirements.test.txt` — dépendances de test (ajout de `pytest-cov`)
- `pyproject.toml` — configuration ruff, mypy, pytest
- `Makefile` — commandes : `install`, `install-all`, `dev`, `test`, `test-cov`, `docker-up`, `docker-down`, `docker-storage`, `lint`, `format`
- Squelettes `__init__.py` pour tous les packages : `simulation/`, `mqtt/`, `api/`, `api/routes/`, `consumer/`, `dashboard/`, `dashboard/components/`, `tests/`
- Squelettes vides pour tous les modules futurs (commentaire indiquant la phase d'implémentation)
- `mosquitto/config/mosquitto.conf` — configuration broker dev (allow_anonymous, TCP 1883 + WS 9001)
- `grafana/provisioning/.gitkeep` — répertoire versionnable

**Notes :**
- `pytest-cov==5.0.0` ajouté à `requirements.test.txt` (non mentionné dans les specs initiales mais nécessaire pour `make test-cov`)
- Les squelettes permettent d'importer tous les packages sans erreur dès maintenant

---

### Étape 1.2 — Système de configuration YAML (OmegaConf) ✅

**Fichiers créés :**
- `config/__init__.py`
- `config/base.yaml` — configuration complète du cluster (rôles master/worker, 5 machines, MQTT, paramètres thermiques)
- `config/scenarios/nominal.yaml` — profil sine_wave, pas de pannes
- `config/scenarios/stress.yaml` — profil ramp_with_spikes, pannes Weibull/exponentielle/uniforme
- `config/loader.py` — `load_config()` avec merge 3 niveaux + surcharges ENV, `get_machine_config()` avec héritage rôle → machine
- `simulation/duration.py` — `parse_duration()` supportant `"0"`, `"30s"`, `"5m"`, `"1h30m"`, `"2h15m30s"`, nombres purs
- `tests/conftest.py` — fixtures `fix_random_seed` (autouse), `nominal_config`, `stress_config`, `master_thermal_params`
- `tests/test_config.py` — 14 tests couvrant : chargement nominal/stress, merge, surcharges programmatiques, surcharge individuelle `srv-master-02`, erreurs

**Décisions techniques :**
- `get_machine_config()` utilise `OmegaConf.masked_copy()` pour extraire les surcharges individuelles sans inclure `id` et `role`
- La surcharge ENV (`CLUSTER_ID`, `MQTT_BROKER_HOST`, `TICK_RATE_HZ`) est appliquée après le merge YAML
- `parse_duration("0")` et `parse_duration("")` retournent `0.0` (durée infinie)

---

### Étape 1.3 — Modèle physique (fonctions pures) ✅

**Fichiers créés :**
- `simulation/physics.py` — 7 fonctions pures : `compute_load_power`, `compute_heat_input`, `compute_tau`, `compute_thermal_step`, `compute_fan_auto_speed`, `compute_energy_kwh`, `compute_cost`
- `simulation/noise.py` — 6 fonctions : `gaussian_noise`, `add_spike`, `accumulate_drift`, `weibull_event`, `exponential_event`, `uniform_event`
- `tests/test_physics.py` — 35 tests couvrant toutes les fonctions physiques et de bruit

**Décisions techniques :**
- `weibull_event()` implémenté via le taux de défaillance instantané h(t) = (β/η)(t/η)^(β-1), approche standard en fiabilité industrielle
- `exponential_event()` : P = 1 - exp(-dt/scale_s), processus de Poisson homogène
- `uniform_event()` ajouté (non dans les specs initiales) pour supporter le type `power_surge` du scénario stress
- Toutes les fonctions sont purement déterministes quand numpy seed est fixé

---

## 2026-05-26 — Phase 8.1 : Scénarios avancés + MQTT Observer ✅

### Étape 8.1 — Scénarios avancés + MQTT Observer ✅

**Fichiers créés :**
- `config/scenarios/heatwave.yaml` — Vague de chaleur 24h (T_amb progressive 28°C → 35°C, pannes accélérées T > 32°C)
- `config/scenarios/busy_weeks.yaml` — Cycles réalistes 7 jours (weekday/weekend, rush hours, anomalies hebdomadales)
- `scripts/mqtt_observer.py` — Observer MQTT léger (affichage JSON formaté, filtrage topics, verbose optionnel)

**Cas d'usage :**
- Heatwave : tester limites refroidissement, dimensionner climatisation
- Busy weeks : valider auto-scaling, analyser coûts énergétiques hebdo
- Observer : déboguer topics, inspecter payloads temps réel (alternative à MQTT Explorer)

**Statut :** ✅ Complète — Deux scénarios chargent sans erreur, observer MQTT fonctionne

---

## 2026-05-29 — Phase 8.4 : Contrôle de vitesse de simulation ✅

### Étape 8.4 — Speed Multiplier pour ML Data Gen ✅

**Objectif :** Accélérer simulation pour générer mois/années de données en secondes.

**Fichiers modifiés :**
- `config/base.yaml` — Ajout `simulation.speed_multiplier: 1.0`, `cpu_throttle_enabled: true`, `cpu_throttle_target_hz: 100.0`
- `simulation/cluster.py` — Implémentation :
  - Accumulation temps : `dt_simulated = dt_real × speed_multiplier`
  - Buffer snapshots circulaire (100K max)
  - Méthodes publiques : `set_speed_multiplier()`, `get_speed_info()`, `set_cpu_throttle()`, `reset_time_and_energy()`
- `api/routes/simulation.py` — 3 nouveaux endpoints :
  - `GET /simulation/speed` → infos vitesse + throttle
  - `PUT /simulation/speed` → change vitesse (multiplier ou preset name)
  - `POST /simulation/speed/reset` → réinitialise temps + énergie
- `tests/test_speed_multiplier.py` — 20+ tests (config, 1x/60x/3600x/86400x, hot reload, throttling)

**Impact :** 30 jours simulés en 30 secondes (86400x speed), idéal pour entraînement ML.

**Statut :** ✅ Complète — Changement vitesse à chaud, accumulation temps correcte, throttle CPU fonctionne

---

## 2026-06-03 — Phase 8.5 Partie 1 : Dashboard Enhancement

### Dashboard — Liens rapides vers services externes ✅

**Fichier modifié :**
- `dashboard/app.py` — Fonction `render_sidebar()` :
  - Ajout section "🔗 Services externes" avec 3 liens cliquables
  - 🌐 API (http://localhost:8000)
  - 📖 API Docs (http://localhost:8000/docs) **← NOUVEAU**
  - 📊 Grafana (http://localhost:3000) **← NOUVEAU**

**Bénéfice pédagogique :** Navigation facilitée, découverte Swagger UI, accès rapide dashboards analytiques, meilleure compréhension de l'architecture globale.

**Statut :** ✅ Implémenté et testé

---

## 2026-06-04 — Phase 8.5 Partie 2 : Bug Fixes (Pannes + Speed Multiplier)

### Bug Fix #1 : Injection de pannes sans effet ✅

**Problème :** Pannes injectées (fan_failure, sensor_drift) n'avaient aucun effet observable.

**Cause :** Seul `power_surge` était appliqué. Les autres types de pannes étaient stockées mais jamais utilisées dans le modèle physique.

**Solution implémentée dans `simulation/machine.py` (_integrate_thermal) :**
1. **fan_failure** → `fan_rpm_mean = 0.0` (arrêt ventilateurs)
   - Constante thermique tau augmente (moins de refroidissement actif)
   - Température monte progressivement pendant la panne
   
2. **sensor_drift** → Biais aléatoire appliqué à snapshot()
   - Lecture biaisée : -5% à +20% par rapport à T réelle
   - Simule dérive capteur de température
   
3. **power_surge** → Surconsommation électrique (déjà existant, validé)
   - Multiplication puissance : `P = P × (1.0 + fault.magnitude)`

**Fichier modifié :** `simulation/machine.py` (_integrate_thermal, snapshot)

**Tests :** Validé via dashboard injection panne + observation température/puissance en temps réel

**Statut :** ✅ Corrigé et fonctionnel

### Bug Fix #2 : Speed Multiplier n'affecte pas la fréquence d'événements ✅

**Problème :** À 60x speed, fréquence d'événements MQTT restait 1/sec au lieu de 60/sec.

**Cause :** Le `dt` (delta temps) passé aux machines n'était jamais multiplié par `speed_multiplier`.

**Chaîne du bug :**
```python
# Avant : dt toujours 0.1s (1/10 Hz)
dt = 1.0 / self._tick_rate_hz
self._t_elapsed_s += dt  # ❌ Pas de × speed_multiplier

# À 60x speed :
# 1 sec réelle = 10 ticks = 0.1s simulé CHAQUE FOIS
# → 1 événement/sec (devrait être 60)
```

**Solution implémentée dans `simulation/cluster.py` (lignes ~246-267) :**
```python
dt_per_iteration = 1.0 / self._tick_rate_hz
dt_simulated = dt_per_iteration * self._speed_multiplier  # ✅ KEY FIX
self._t_elapsed_s += dt_simulated
```

**Impact :** À 60x speed, chaque tick représente 0.6s simulé (0.1s réel × 60)
→ 1 sec réelle = 10 ticks = 6 secondes simulées = 6 événements ✅

**Fichier modifié :** `simulation/cluster.py` (boucle `_tick()`)

**Tests :** `tests/test_speed_multiplier.py` — 20+ tests validant accumulation temps :
- 1x speed : 1 sec = 0.1s simulé per tick
- 60x speed : 1 sec = 6s simulé per tick
- 3600x speed : 1 sec = 60s simulé per tick
- 86400x speed : 1 sec = 24h simulé per tick

**Statut :** ✅ Corrigé et validé par tests

---

## Prochaine étape

**Phase 8.2 — Régulateur PID configurable** ⏳ (À démarrer)
- Implémenter `simulation/pid.py` avec classe `PIDController` (Kp, Ki, Kd, anti-windup)
- Ajouter paramètres YAML : setpoint_c, gains, limites RPM
- Intégrer dans `MachineSimulator._update_fan_speed()`
- Écrire 15+ tests (stabilisation, overshoot < 10%, réaction charge)

**Phase 8.3 — Coût électrique mensuel** ⏳ (À démarrer)
- Implémenter calcul coûts dans `simulation/energy.py` (énergie + PUE + tarif)
- Ajouter endpoint API `/cluster/energy/projection?period=month|quarter|year`
- Dashboard : onglet "Energy Cost" (graphes kWh/jour, PUE, €, projection)
