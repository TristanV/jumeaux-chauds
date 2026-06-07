# 🔥 Jumeaux Chauds — Digital Twin pour Clusters IoT

**Plateforme pédagogique de simulation thermique pour serveurs en cluster avec télémétrie MQTT en temps réel.**

Un projet de Master 2 conçu pour enseigner l'IoT, les modèles thermiques, MQTT, les bases de données de séries temporelles, FastAPI, et les dashboards interactifs.

---

## 🎯 Vue d'ensemble

**Jumeaux Chauds** simule un cluster de serveurs physiques avec :

- 🌡️ **Modèle thermique réaliste** — Équations différentielles 1er ordre avec charge CPU, refroidissement par fans, bruit gaussien
- 📡 **Télémétrie MQTT multi-canaux** — 5 routes de données distinctes (direct MQTT, API REST, TimescaleDB, Grafana, Streamlit)
- ⚙️ **Scénarios de charge avancés** — basic (baseline), nominal, stress, heatwave, busy_weeks, trace_replay — avec 6 profils de charge dont un rejeu de traces CSV réelles (Bitbrains FastStorage)
- 🎮 **Contrôle et observation** — FastAPI REST + WebSocket, MQTT observer en temps réel, injection de pannes
- 📊 **Dashboards interactifs** — Streamlit pour monitoring temps réel, Grafana pour analytics historiques
- 🧪 **Suite de tests complète** — 330+ tests (couverture ≥ 85%), tests par couche d'architecture

---

## 📚 Documentation Complète

Cette documentation est organisée en 6 sections. Choisissez votre point d'entrée :

| Section | Lien | Pour qui ? | Temps |
|---------|------|-----------|-------|
| **Démarrage rapide** | [📖 QUICK_START.md](documents/QUICK_START.md) | Développeurs : installer & lancer en 5 min | 5 min |
| **Spécifications techniques** | [📋 specifications.md](documents/specifications.md) | Architectes & devs : comprendre le design | 20 min |
| **Architecture en couches** | [📋 ARCHITECTURE_LAYERS.md](documents/ARCHITECTURE_LAYERS.md) | Architectes & devs : comprendre l'architecture | 15 min |
| **Flux de données** | [🔀 TELEMETRY_FLOWS.md](documents/TELEMETRY_FLOWS.md) | Devs intégration : 5 routes de télémétrie | 15 min |
| **Guide de test** | [🧪 TESTING_GUIDE.md](documents/TESTING_GUIDE.md) | QA & devs : tester par couche d'architecture | 10 min |
| **Résumé flux** | [📊 DATA_FLOWS_SUMMARY.md](documents/DATA_FLOWS_SUMMARY.md) | Tous : carte de référence imprimable | 2 min |
| **Trace Replay** | [🔁 TRACE_REPLAY_GUIDE.md](documents/TRACE_REPLAY_GUIDE.md) | ML/data : rejouer des traces réelles (Bitbrains, export sim) | 10 min |
| **Roadmap & Phases** | [🗺️ roadmap.md](documents/roadmap.md) | Chef de projet : suivi du développement | 10 min |

---

## 🚀 Démarrer en 5 minutes

```bash
# 1. Environnement
conda create -n jumeaux-chauds python=3.12 -y
conda activate jumeaux-chauds
pip install -r requirements.txt

# 2. Tests unitaires (optionnel)
pytest tests/ -v

# 3. Broker MQTT (Terminal 1)
docker run -d --name mosquitto -p 1883:1883 eclipse-mosquitto:2

# 4. Simulation (Terminal 2)
python scripts/run_simulator.py --scenario nominal --duration 1m

# 5. Observer MQTT (Terminal 3)
python scripts/mqtt_observer.py --host localhost

# 6. API (Terminal 4, optionnel)
export MQTT_ENABLED=0
uvicorn api.main:app --port 8000
# → Docs : http://localhost:8000/docs

# 7. Dashboard (Terminal 5, optionnel)
streamlit run dashboard/app.py
# → http://localhost:8501
# → Menu latéral : liens rapides vers API, API Docs et Grafana
```

**→ Pour instructions détaillées, voir [QUICK_START.md](documents/QUICK_START.md)**


---

## 🎓 Architecture en 8 Couches

```
┌─────────────────────────────────────────────────────────────────┐
│ Layer 8 : Dashboards (Streamlit, Grafana)                      │
├─────────────────────────────────────────────────────────────────┤
│ Layer 7 : API Gateway (FastAPI REST + WebSocket)               │
├─────────────────────────────────────────────────────────────────┤
│ Layer 6 : Simulation Core (ClusterSimulator, ScenarioEngine)    │
├─────────────────────────────────────────────────────────────────┤
│ Layer 5 : MQTT Publisher (aiomqtt)                             │
├─────────────────────────────────────────────────────────────────┤
│ Layer 4 : MQTT Broker (Mosquitto)  ← Route 1                   │
├─────────────────────────────┬───────────────────────────────────┤
│ Layer 3 : Consumer (TS) ←─┘ │ Observer (Display)  ← Route 1     │
│           ← Route 3          └─→ (mqtt_observer.py, mosquitto)   │
├─────────────────────────────────────────────────────────────────┤
│ Layer 2 : TimescaleDB (hypertable)  ← Routes 3, 4              │
├─────────────────────────────────────────────────────────────────┤
│ Layer 1 : Physics & Config (Foundation)                        │
└─────────────────────────────────────────────────────────────────┘
```

**5 routes de télémétrie :**
1. **MQTT Direct** — Real-time <100ms
2. **API REST** — Control ~50ms
3. **MQTT→TimescaleDB** — Historical ~1s
4. **TimescaleDB→Grafana** — Executive ~500ms
5. **Streamlit+WebSocket** — Interactive <500ms

**→ Comparaison complète : [DATA_FLOWS_SUMMARY.md](documents/DATA_FLOWS_SUMMARY.md) (2 min) ou [TELEMETRY_FLOWS.md](documents/TELEMETRY_FLOWS.md) (20 min)**

---

## 🧪 Tester par Couche d'Architecture

```bash
# Layer 1 (Physics & Config) — 0 dépendances
pytest tests/test_physics.py tests/test_config.py -v     # 1 min

# Layer 2 (Simulation Core) — 0 dépendances
pytest tests/test_machine*.py tests/test_energy*.py -v   # 2 min

# Layer 3 (MQTT) — 0 dépendances
pytest tests/test_mqtt_integration.py tests/test_consumer_integration.py -v  # 1 min

# Layer 5 (API) — API running
pytest tests/test_api_integration.py -v                  # 2 min

# Tous les tests
pytest tests/ -v --cov=simulation --cov=config          # 5 min
```

**→ Tous les détails : [TESTING_GUIDE.md](documents/TESTING_GUIDE.md)**

---

## 🔌 Scénarios Disponibles

| Scénario | Profil de charge | Cas d'usage |
|----------|-----------------|-----------|
| **basic** | `sine_wave` | Baseline pédagogique — motif périodique simple, aucune panne |
| **nominal** | `multi_scale_sine` | Charge réaliste datacenter (3 sinusoïdes incommensurables : horaire, journalière, hebdomadaire) |
| **heatwave** | `multi_scale_sine` | Vague de chaleur — charge de fond élevée + pics journaliers marqués |
| **busy_weeks** | `perlin_noise` | Semaines chargées — charge organique continue, aucun motif répétitif détectable |
| **stress** | `composite_stress` | Stress haute fidélité — cycles + dérive thermique progressive + spikes incidents + texture Perlin |
| **trace_replay** | `trace_replay` | Rejoue une trace CSV réelle (Bitbrains FastStorage ou export `generate_dataset.py`) |

**Profils de charge disponibles :**

| Profil | Description |
|--------|-------------|
| `sine_wave` | Sinusoïde pure — référence pédagogique |
| `ramp_with_spikes` | Montée progressive + spikes aléatoires |
| `multi_scale_sine` | Superposition de 3 sinusoïdes (horaire, journalière, hebdomadaire) |
| `perlin_noise` | Bruit Perlin multifractal — organique et non répétitif |
| `markov_chain` | Chaîne de Markov 4 états (idle/moderate/heavy/burst) |
| `composite_stress` | Combinaison : cycles + dérive + spikes + texture Perlin |
| `trace_replay` | Rejeu CSV : interpolation linéaire, loop, speed_factor configurable |

```bash
# Exemples
python scripts/run_simulator.py --scenario basic --duration 5m
python scripts/run_simulator.py --scenario nominal --duration 10m
python scripts/run_simulator.py --scenario heatwave --duration 24h
python scripts/run_simulator.py --scenario busy_weeks --duration 7d
python scripts/run_simulator.py --scenario stress --duration 1h
python scripts/run_simulator.py --scenario trace_replay --duration 72h
```

---

## 🔁 Trace Replay — Rejouer des données réelles

Le scénario `trace_replay` permet de piloter la simulation avec une **vraie trace de charge**
au lieu d'une fonction mathématique. Trois sources sont supportées :

| Mode | Source | Prérequis | Taille |
|------|--------|-----------|--------|
| **A — Embarqué** | `data/traces/*.csv` (4 traces synthétiques) | Aucun | ~138 KB inclus |
| **B — Bitbrains réel** | Dataset Bitbrains FastStorage | Téléchargement (~30 MB) | ~30 MB |
| **C — Export sim** | `generate_dataset.py` → CSV | Python seul | Variable |

```bash
# Mode A : traces embarquées — prêt à l'emploi
SCENARIO=trace_replay docker compose up -d

# Mode B : télécharger le vrai dataset Bitbrains
python scripts/download_traces.py
python scripts/download_traces.py --list        # lister les traces disponibles

# Mode C : exporter une simulation et la rejouer
python scripts/generate_dataset.py --scenario nominal --duration 7d \
  --output data/traces/ma_trace.csv --format csv
# → modifier config/scenarios/trace_replay.yaml : trace_file: "data/traces/ma_trace.csv"
# → curl -X PUT http://localhost:8000/simulation/scenario -d '{"scenario":"trace_replay"}'
```

**→ Guide complet avec toutes les options : [TRACE_REPLAY_GUIDE.md](documents/TRACE_REPLAY_GUIDE.md)**

---

## 💾 Stockage & Persistence

### Sans stockage (5 min setup)
- MQTT direct (en mémoire)
- FastAPI cache
- Streamlit UI state

### Avec stockage (30 min setup)
```bash
docker compose --profile storage up -d
# Lance : Mosquitto + TimescaleDB + Consumer + Grafana
```


---

## 📊 État du Projet

### Phases 1–7 ✅ COMPLÈTES
Fondations pédagogiques solides avec 330+ tests (couverture ≥ 85%)

### Phase 8 🔄 En cours
Extensions pédagogiques prioritaires

- 8.1 Scénarios avancés + MQTT observer ✅ (heatwave 24h, busy_weeks 7j, mqtt_observer.py)
- 8.4 Contrôle de vitesse de simulation ✅ (speed_multiplier, génération données ML)
- 8.5 Bug fixes dashboard + simulation ✅
- 8.6 Bug fixes tests + config ✅ — **317/317 tests, 0 warnings**
- 8.7 Affinage thermique ✅ — modèle physique réaliste (RPM^1.5, clamp T, sous-pas)
- 8.8/8.9/8.10/8.11 — Corrections bugs comportementaux, traçabilité, Grafana ✅
- 8.12 Refonte architecture speed_multiplier ✅
  - 8.12A : correction boucle temps réel (dt_sim fixe, CPU throttle, batch, fault_id)
  - 8.12B : script génération corpus ML (~3 700 ticks/s, CSV/Parquet, bulk TimescaleDB)
- 8.13 Contrôle start/pause/stop simulation ✅
  - Simulation **OFF par défaut** au lancement Docker (variable `SIMULATION_AUTOSTART=0`)
  - Bandeau de contrôle rapide Streamlit : ▶ Démarrer / ⏸ Pause / ▶ Reprendre / ⏹ Arrêter / 🗑 Reset
  - API : `GET /simulation/status`, `POST /simulation/start|pause|resume|stop`
- 8.14 Bibliothèque de profils de charge réalistes ✅ (8.14A + 8.14B)
  - 5 nouveaux profils : `multi_scale_sine`, `perlin_noise`, `markov_chain`, `composite_stress`, `trace_replay`
  - Implémentation pure numpy — aucune dépendance externe (`_Perlin1D` intégré)
  - 6 scénarios : `basic` (nouveau), `nominal`, `heatwave`, `busy_weeks`, `stress`, `trace_replay` (nouveau)
  - Dataset Bitbrains synthétique embarqué dans `data/traces/` (~138 KB, 4 traces)
  - `scripts/download_traces.py` pour télécharger le vrai dataset Bitbrains (~30 MB)
  - 52 nouveaux tests (`tests/test_load_profiles.py`)
- 8.2 Régulateur PID configurable ⏳ (planifié)
- 8.3 Projection coût électrique mensuel ⏳ (planifié)

**→ Détails complets : [roadmap.md](documents/roadmap.md)**
---

## 📖 Ressources Additionnelles


- [change_track/PHASE_8_1_COMPLETION.md](documents/change_track/PHASE_8_1_COMPLETION.md) — Détails Phase 8.1
- [change_track/INDEX.md](documents/change_track/INDEX.md) — Historique des changements
- [worklog.md](documents/worklog.md) — Journal des implémentations

---

## 👤 Auteur

**Tristan Vanrullen** — La Plateforme, Marseille — 2026  
*Master 2 Informatique — Spécialité IoT & Systèmes Distribués*

---

## 📋 Checklist Rapide

- [ ] Lire [QUICK_START.md](documents/QUICK_START.md) (5 min)
- [ ] Installer & tester Phase 1 (5 min)
- [ ] Lancer un scénario + observer MQTT (5 min)
- [ ] Consulter [TELEMETRY_FLOWS.md](documents/TELEMETRY_FLOWS.md) pour comprendre les routes (15 min)
- [ ] Lancer l'API & le Dashboard (5 min)
- [ ] Lire [specifications.md](documents/specifications.md) pour comprendre le design (20 min)
- [ ] Consulter [TESTING_GUIDE.md](documents/TESTING_GUIDE.md) pour tester par couche (10 min)
- [ ] Vérifier [roadmap.md](documents/roadmap.md) pour les prochaines phases (10 min)

**Temps total : ~75 minutes pour complète maîtrise de la plateforme**

---

*Dernière mise à jour : 7 juin 2026*
