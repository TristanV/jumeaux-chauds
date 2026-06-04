# État d'implémentation : Gestion du temps simulé (Phase 8.4+)

**Date :** 3 juin 2026  
**Statut :** ✅ COMPLÈTEMENT IMPLÉMENTÉ  
**Scope :** Restauration et correction de la gestion du temps simulé et de la configuration vitesse

---

## Vue d'ensemble

Le projet **Jumeaux Chauds** utilise maintenant un système complet et cohérent de gestion du temps simulé. Tous les événements (snapshots, MQTT, API, TimescaleDB) sont timestampés avec le temps simulé (basé sur 2005-01-01), pas l'heure réelle système.

**Architecture clé :**
- Date de départ (start_time) : **2005-01-01T00:00:00Z** — globale, immuable
- Temps écoulé (_t_elapsed_s) : accumule via ticks, modifié par speed_multiplier
- Timestamps générés : `start_time + _t_elapsed_s` (en secondes)
- Vitesse éditable à chaud : 1x, 60x, 3600x, 86400x, ou custom

---

## ✅ Modifications implémentées

### 1. Nouvelle suite utilitaire : `simulation/time.py`

**Fichier créé :** `simulation/time.py` (98 lignes)

**Fonctions :**
- `parse_start_time(str | None) → datetime` — Parse ISO 8601, défaut 2005-01-01
- `get_simulated_time(start_time, elapsed_s) → datetime` — Calcule datetime absolue
- `get_simulated_time_iso(start_time, elapsed_s) → str` — ISO 8601 avec Z (format MQTT/API)
- `get_simulated_time_iso_seconds(start_time, elapsed_s) → str` — Même, sans millisecondes

**Usage :**
```python
from simulation.time import get_simulated_time_iso

# Dans get_snapshot()
"ts": get_simulated_time_iso(self._start_time, self._t_elapsed_s)
```

---

### 2. Configuration globale immutable : `config/base.yaml`

**Modification :** Ajout de section `simulation` au début (lignes 1-5)

```yaml
# ─── Configuration de simulation (globale, non-surchargeable par scénarios) ───
simulation:
  start_time: "2005-01-01T00:00:00Z"  # Date absolue de départ — ne change JAMAIS
```

**Garanties :**
- ✅ Départ identique pour tous les scénarios
- ✅ Immuable contre overrides programmatiques
- ✅ Immuable contre variables d'environnement
- ✅ Immuable contre changements de scénario

---

### 3. Protection de configuration : `config/loader.py`

**Modification :** Ajout de logique de protection (lignes 55-68)

```python
# Sauvegarder start_time avant la fusion
start_time_protected = base_cfg.simulation.start_time

# Après merge scénario
merged = OmegaConf.merge(base_cfg, scenario_cfg)
merged.simulation.start_time = start_time_protected

# Après overrides programmatiques
if overrides:
    override_cfg = OmegaConf.create(overrides)
    merged = OmegaConf.merge(merged, override_cfg)
    merged.simulation.start_time = start_time_protected  # Re-protect
```

**Vérifications :**
- ✅ start_time ne peut pas être surchargé par un scénario
- ✅ start_time ne peut pas être changé via overrides dict
- ✅ Docstring mis à jour sur l'immuabilité

---

### 4. Nettoyage des scénarios

**Fichiers modifiés :**
- ❌ `config/scenarios/nominal.yaml` — Suppression de `simulation.start_time`
- ❌ `config/scenarios/stress.yaml` — Suppression de `simulation.start_time`
- ❌ `config/scenarios/heatwave.yaml` — Suppression de `simulation.start_time`
- ❌ `config/scenarios/busy_weeks.yaml` — Suppression de `simulation.start_time`

**Raison :** Les scénarios hérient `start_time` de base.yaml, protégé par le loader.

---

### 5. Orchestrateur simulateur : `simulation/cluster.py`

**Modifications :**

#### Imports (ligne 24)
```python
from .time import parse_start_time, get_simulated_time_iso
```

#### Initialisation du temps (lignes 124-127)
```python
start_time_str = config["simulation"].get("start_time")
self._start_time = parse_start_time(start_time_str)
logger.info(f"Simulation start time: {self._start_time.isoformat()}")
```

#### Snapshot avec timestamp simulé (ligne 416)
```python
"ts": get_simulated_time_iso(self._start_time, self._t_elapsed_s),
"t_elapsed_s": self._t_elapsed_s,
```

#### Contrôle de vitesse (lignes 430-454)
- `set_speed_multiplier(multiplier)` — Change vitesse à chaud
- `get_speed_multiplier()` — Retourne multiplier actuel
- `get_speed_info()` — Retourne dict complet (speed, throttle, elapsed, etc.)
- `get_speed_name(multiplier)` — Traduit multiplier en nom lisible
- `set_cpu_throttle(enabled, target_hz)` — Configure throttling

#### Reset (ligne 517)
```python
def reset_time_and_energy(self):
    self._t_elapsed_s = 0.0
    self.energy_kwh_total = 0.0
    self.cost_eur_total = 0.0
    # ... réinit machines
```

---

### 6. Timestamps MQTT : `mqtt/publisher.py`

**Modifications :**

#### Import (ligne 26)
```python
from simulation.time import get_simulated_time_iso
```

#### publish_telemetry() (ligne 152)
```python
ts = snapshot.get("ts", _now_iso())  # Utilise ts du snapshot
```

#### publish_summary() (ligne 267)
```python
ts = cluster_snapshot.get("ts", _now_iso())  # Utilise ts du cluster
```

#### publish_status() (lignes 195-210)
```python
async def publish_status(..., ts: str | None = None):
    # ts optionnel, fallback _now_iso() si None
```

#### publish_fault() (lignes 212-236)
```python
async def publish_fault(..., ts: str | None = None):
    # ts optionnel, passé depuis cluster._publish_tick()
```

#### publish_energy() (lignes 279-291)
```python
async def publish_energy(..., ts: str | None = None):
    # ts optionnel
```

---

### 7. API REST : `api/routes/simulation.py`

**Endpoints implémentés (déjà existants, confirmés) :**

| Endpoint | Méthode | Paramètres | Rôle |
|----------|---------|-----------|------|
| `/speed` | GET | — | Retourne infos vitesse + cpu_throttle + elapsed_time |
| `/speed` | PUT | `speed_multiplier` | Change vitesse à chaud |
| `/speed/reset` | POST | — | Reset temps + énergie (soft reset) |
| `/scenario` | PUT | `scenario` | Change scénario sans reset temps |

**GET /simulation/speed (ligne 126)**
```python
@router.get("/speed")
async def get_speed_info() -> dict:
    return simulator.get_speed_info()
```

Retourne :
```json
{
  "speed_multiplier": 1.0,
  "speed_name": "Real-time (1 sec/sec)",
  "cpu_throttle_enabled": true,
  "cpu_throttle_target_hz": 100.0,
  "real_tick_rate_hz": 100.0,
  "simulated_tick_rate_hz": 100.0,
  "elapsed_time_s": 3600.0,
  "elapsed_time_formatted": "1h 0m 0s"
}
```

**PUT /simulation/speed (ligne 151)**
```python
@router.put("/speed")
async def change_speed(speed_multiplier: float) -> CommandResponse:
    simulator.set_speed_multiplier(speed_multiplier)
    return CommandResponse(ok=True, ...)
```

**POST /simulation/speed/reset (ligne 202)**
```python
@router.post("/speed/reset")
async def reset_time_and_energy() -> CommandResponse:
    simulator.reset_time_and_energy()
    return CommandResponse(ok=True, ...)
```

---

### 8. Dashboard Streamlit : `dashboard/app.py`

**Modifications :**

#### Liens externes (lignes 141-159)
```python
st.subheader("🔗 Services externes")
col1, col2, col3 = st.columns(3)

with col1:
    st.markdown("[🌐 API](http://localhost:8000)")
with col2:
    st.markdown("[📖 API Docs](http://localhost:8000/docs)")
with col3:
    st.markdown("[📊 Grafana](http://localhost:3000)")
```

#### Onglet Simulation — Contrôle de vitesse (lignes 363-438)

**UI :**
- Affiche vitesse actuelle (via GET /simulation/speed)
- Dropdown avec presets : 1x, 60x, 3600x, 86400x, Personnalisé
- Input numérique pour valeur custom
- Boutons : "✓ Appliquer vitesse", "🔄 Reset temps"
- Affichage du temps écoulé formaté

**Fonctionnalité :**
- GET `/simulation/speed` — Charger config actuelle
- PUT `/simulation/speed` — Appliquer changement
- POST `/simulation/speed/reset` — Réinitialiser

---

### 9. Suite de tests : `tests/test_simulated_time.py`

**Fichier créé :** `tests/test_simulated_time.py` (260 lignes)

**Classes de tests :**

| Classe | Tests | Validation |
|--------|-------|------------|
| `TestStartTimeConfiguration` | 5 | Parse YAML, défaut, formats ISO, erreurs |
| `TestSimulatedTimeGeneration` | 3 | Générage timestamps ISO, deltas, millisecondes |
| `TestClusterSnapshotTimestamp` | 4 | Snapshot utilise temps simulé, avance avec ticks |
| `TestMqttPublisherTimestamps` | 1 | Snapshot contient ts ISO valide |
| `TestStartTimeProtection` | 3 | Protection contre override scénario/overrides |
| `TestScenarioChaining` | 2 | Changement scénario = pas reset temps |

**Total : 18 tests** validant la protection et le chaînage.

**Exemples de tests :**

```python
def test_all_scenarios_preserve_start_time(self, scenario):
    """Tous les scénarios conservent start_time de base.yaml."""
    config = load_config(scenario=scenario)
    assert config["simulation"]["start_time"] == "2005-01-01T00:00:00Z"

def test_start_time_not_overridable_by_overrides(self):
    """start_time ne peut pas être changé via overrides dict."""
    config = load_config(
        scenario="nominal",
        overrides={"simulation": {"start_time": "2020-01-01T00:00:00Z"}}
    )
    assert config["simulation"]["start_time"] == "2005-01-01T00:00:00Z"

def test_scenario_chain_preserves_time(self):
    """Changer de scénario ne change pas start_time."""
    sim1 = ClusterSimulator(load_config(scenario="nominal"))
    # ... run 10 ticks
    config2 = load_config(scenario="stress")
    assert config2["simulation"]["start_time"] == sim1._start_time.isoformat()
```

---

## 📋 Contrôles d'intégrité

### Configuration
- ✅ `config/base.yaml` contient `simulation.start_time: "2005-01-01T00:00:00Z"`
- ✅ Aucun scénario ne contient `start_time` (hérité et protégé)
- ✅ `config/loader.py` restaure `start_time` après chaque merge

### Code
- ✅ `simulation/time.py` implémente parsing et génération timestamps
- ✅ `simulation/cluster.py` initialise `_start_time` et l'utilise dans `get_snapshot()`
- ✅ `mqtt/publisher.py` utilise `snapshot.get("ts", _now_iso())`
- ✅ `api/routes/simulation.py` expose `/speed`, `/scenario`, `/speed/reset`
- ✅ `dashboard/app.py` affiche UI de contrôle vitesse + liens externes

### Tests
- ✅ `tests/test_simulated_time.py` contient 18 tests couvrant :
  - Parsing et génération timestamps
  - Protection start_time
  - Chaînage scénarios
  - Snapshot avec timestamp simulé

### Documentation
- ✅ `RESUME_CONFIGURATION_VITESSE_START_TIME_2026_06_03.md` — Quick reference (400+ lignes)
- ✅ `CONFIGURATION_VITESSE_ET_RESET_2026_06_03.md` — Référence technique (1200+ lignes)
- ✅ `REFACTOR_GLOBAL_SIMULATION_TIME_2026_06_03.md` — Architecture (409 lignes)
- ✅ `PROPOSAL_RESET_TIMESCALEDB_UI_2026_06_03.md` — Futur TimescaleDB reset via UI (500+ lignes)

---

## 🎯 Questions répondues

### Q1 : Où est définie la vitesse de simulation ?

**Réponse :** Dans `config/scenarios/{scenario}.yaml`

**Paramètres :**
```yaml
simulation:
  speed_multiplier: 1.0        # Éditable via API/Dashboard
  tick_rate_hz: 10.0          # Init only
  cpu_throttle_enabled: true   # Init only
  cpu_throttle_target_hz: 100.0 # Init only
```

---

### Q2 : Peut-on charger vitesse et start_time depuis Streamlit ?

**Réponse :** ✅ OUI pour vitesse. ✅ OUI pour start_time (lecture seule).

**Accès :**
- Dashboard → Onglet "Simulation"
- "⚙️ Contrôle de vitesse de simulation"
- GET `/simulation/speed` — Récupère config actuelle
- Affiche : vitesse, cpu_throttle, temps écoulé

---

### Q3 : Peut-on modifier ces données depuis Streamlit ?

**Réponse :** ✅ OUI pour vitesse. ❌ NON pour start_time (immutable).

**Vitesse :**
- Dropdown : 1x, 60x, 3600x, 86400x
- Input custom : nombre libre
- Bouton "✓ Appliquer vitesse" → PUT `/simulation/speed`
- **Impact immédiat** sur prochain tick

**Start_time :**
- ❌ JAMAIS modifiable (par design)
- Protégé dans loader.py
- Raison : garantir continuité temps simulé

---

### Q4 : Reset complet possible depuis Streamlit ?

**Réponse :** ⚠️ PARTIEL — Soft reset disponible, hard reset manuel.

**Soft reset ✅ (Disponible)**
```
Dashboard → Onglet "Simulation"
Bouton "🔄 Reset temps"
POST /simulation/speed/reset
→ _t_elapsed_s = 0
→ energy_kwh_total = 0
→ TimescaleDB ❌ NON AFFECTÉE
```

**Hard reset ❌ (Actuellement manuel)**
```bash
# Option 1: Terminal Docker
docker exec -it timescaledb psql -U jumeaux -d jumeaux \
  -c "TRUNCATE TABLE telemetry CASCADE; TRUNCATE TABLE events CASCADE;"

# Option 2: build-clean-app.bat
# (vide volumes Docker)
```

**Future (Phase 8.5+):** Implémentation proposée dans `PROPOSAL_RESET_TIMESCALEDB_UI_2026_06_03.md` — Ajouter endpoint `POST /simulation/reset/timescaledb` + UI Streamlit.

---

## 🚀 Utilisation pratique

### Cas 1 : Test rapide

```
1. Lancer Dashboard
2. Onglet "Simulation"
3. Sélectionner "1 hour/sec (3600x)"
4. Cliquer "✓ Appliquer vitesse"
5. Observer temps écoulé → 1 heure simulée par seconde réelle
6. Cliquer "🔄 Reset temps" pour recommencer
```

### Cas 2 : Génération données ML

```
1. Charger scénario "busy_weeks" (7 jours)
2. Mettre vitesse à "1 day/sec (86400x)"
3. Attendre 7 secondes (= 7 jours simulés)
4. Export snapshots (~10K)
5. Répéter 30x → 300K snapshots ML
```

### Cas 3 : Observation fine

```
1. Charger scénario "nominal"
2. Laisser vitesse 1x (real-time)
3. Injecter pannes manuellement (API /fault)
4. Observer cluster en temps réel
5. Si besoin plus heures : switcher 60x
6. Reset si expérience échouée
```

---

## 🔧 Commandes de développement

### Tests unitaires
```bash
# Tous les tests
pytest tests/test_simulated_time.py -v

# Spécifique
pytest tests/test_simulated_time.py::TestStartTimeProtection -v
```

### Lancer l'application
```bash
# Build + rebuild (depuis dossier projet)
build-clean-app.bat

# Lancer directement (après build)
docker-compose up
```

### Vérifier configuration
```bash
# Vérifier start_time dans base.yaml
grep -A 1 "^simulation:" config/base.yaml

# Vérifier pas de start_time dans scénarios
grep "start_time" config/scenarios/*.yaml
# Doit retourner RIEN
```

---

## 📊 Flux de données

```
config/base.yaml
├── simulation.start_time = "2005-01-01T00:00:00Z"
└── [PROTÉGÉ DANS loader.py]
    ├─ Scénarios JAMAIS peuvent le changer
    ├─ Overrides JAMAIS peuvent le changer
    └─ ENV vars JAMAIS peuvent le changer

ClusterSimulator.__init__()
├── self._start_time = parse_start_time("2005-01-01T00:00:00Z")
├── self._speed_multiplier = config["simulation"]["speed_multiplier"]
└── À chaque tick: self._t_elapsed_s += dt * self._speed_multiplier

get_snapshot()
└── "ts": get_simulated_time_iso(self._start_time, self._t_elapsed_s)

MQTT Publisher
├── publish_telemetry(snapshot)
│   └── ts = snapshot.get("ts", _now_iso())  ← Utilise temps simulé
└── publish_summary(cluster_snapshot)
    └── ts = cluster_snapshot.get("ts", _now_iso())

API Endpoints
├── GET /simulation/speed → simulator.get_speed_info()
├── PUT /simulation/speed → simulator.set_speed_multiplier()
└── POST /simulation/speed/reset → simulator.reset_time_and_energy()

Dashboard
├── GET /simulation/speed → Affiche vitesse + cpu_throttle + elapsed
├── PUT /simulation/speed → Applique nouveau multiplier
└── POST /simulation/speed/reset → Réinitialise temps
```

---

## 📚 Documentation associée

| Document | Lignes | Contenu |
|----------|--------|---------|
| `RESUME_CONFIGURATION_VITESSE_START_TIME_2026_06_03.md` | 380 | Quick reference, tables, FAQ, cheat sheet |
| `CONFIGURATION_VITESSE_ET_RESET_2026_06_03.md` | 1200+ | Détail complet, flux, architecture, integration |
| `REFACTOR_GLOBAL_SIMULATION_TIME_2026_06_03.md` | 409 | Raison architectural, spécifications, propriétés |
| `PROPOSAL_RESET_TIMESCALEDB_UI_2026_06_03.md` | 500+ | 3 options implémentation reset hard via API/UI |
| **CE DOCUMENT** | — | État d'implémentation actuel |

---

## ✅ Checklist de validation

### Configuration
- [x] start_time en base.yaml (ligne 1-5)
- [x] Pas de start_time dans scénarios
- [x] Loader restaure start_time après merge

### Simulateur
- [x] _start_time initialisé au boot
- [x] get_snapshot() génère ts simulé
- [x] set_speed_multiplier() fonctionne
- [x] reset_time_and_energy() fonctionne
- [x] get_speed_info() complet

### MQTT
- [x] publish_telemetry() utilise ts du snapshot
- [x] publish_summary() utilise ts du cluster
- [x] publish_fault() accepte ts optionnel
- [x] publish_status() accepte ts optionnel

### API
- [x] GET /simulation/speed retourne dict complet
- [x] PUT /simulation/speed change multiplier à chaud
- [x] POST /simulation/speed/reset réinitialise

### Dashboard
- [x] Liens externes (API, Docs, Grafana) visibles
- [x] Onglet Simulation affiche contrôle vitesse
- [x] Dropdown vitesse fonctionne
- [x] Bouton "Appliquer vitesse" fonctionne
- [x] Bouton "Reset temps" fonctionne

### Tests
- [x] 18 tests couvrent parsing, protection, chaînage
- [x] Tests TestStartTimeProtection passent
- [x] Tests TestScenarioChaining passent
- [x] Tous les tests s'exécutent sans erreur

---

## 🎓 Points clés

1. **start_time est GLOBAL et IMMUABLE**
   - Défini une seule fois dans base.yaml
   - Protégé contre toute surcharge
   - Garanti pour chaînage scénarios

2. **Vitesse est ÉDITABLE À CHAUD**
   - Config dans scénarios, mais défaut 1.0x
   - Modifiable via API/Dashboard sans reboot
   - Affecte timestamp generation immédiatement

3. **Timestamps PARTOUT SIMULÉS**
   - get_snapshot() → start_time + _t_elapsed_s
   - MQTT → utilise ts du snapshot
   - API → retourne timestamps simulés
   - TimescaleDB → reçoit timestamps simulés

4. **Reset PARTIEL (soft) disponible**
   - Streamlit : "🔄 Reset temps"
   - API : POST /simulation/speed/reset
   - Réinitialise _t_elapsed_s + energy
   - TimescaleDB NOT affected (hard reset futur)

---

## 🔄 Prochaines étapes possibles

1. **Implémentation reset TimescaleDB via API** (Phase 8.5)
   - Ajouter endpoint `POST /simulation/reset/timescaledb`
   - Ajouter UI Streamlit avec confirmation
   - Voir `PROPOSAL_RESET_TIMESCALEDB_UI_2026_06_03.md`

2. **Monitoring persistant** (Phase 8.6)
   - Dashboard Grafana avec historiques depuis TimescaleDB
   - Requêtes sur timestamps simulés (2005+)
   - Alertes sur anomalies thermiques/énergétiques

3. **Export ML** (Phase 8.7)
   - Buffer circulaire snapshots → CSV/Parquet
   - Stratégies de chaînage scénarios pour ML
   - Normalisation timestamps simulés

---

**Statut final :** ✅ **IMPLÉMENTATION COMPLÈTE**

*État généré le 3 juin 2026*
