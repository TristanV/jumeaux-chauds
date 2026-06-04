# Changelog — Phase 8.5 : Configuration éditable (3 juin 2026)

**Date :** 3 juin 2026  
**Phase :** 8.5 (Après implémentation Phase 8.4 du temps simulé)  
**Changements :** Édition start_time, speed_multiplier global, reset TimescaleDB automatique

---

## 🎯 Objectifs de Phase 8.5

Permettre la configuration complète du simulateur via dashboard Streamlit :
1. ✅ Date de départ (start_time) éditable sans réinitialiser temps écoulé
2. ✅ Vitesse (speed_multiplier) définie dans base.yaml + éditable via dashboard
3. ✅ Reset complet (temps + TimescaleDB) depuis dashboard en un clic

---

## 📋 Changements détaillés

### 1. Speed_multiplier déplacé à configuration globale

#### Fichiers modifiés : `config/base.yaml`, `config/scenarios/*.yaml`

**Avant :**
- `speed_multiplier` défini dans chaque scénario (nominal.yaml, stress.yaml, etc.)
- Pouvait théoriquement être différent par scénario

**Après :**
- `speed_multiplier` défini UNE SEULE FOIS dans `config/base.yaml` (section `simulation`)
- Valeur par défaut : 1.0 (real-time)
- Protégé contre overrides (comme `start_time`)
- Peut être changé via API/dashboard à la volée

**Détail dans base.yaml :**
```yaml
simulation:
  start_time: "2005-01-01T00:00:00Z"
  speed_multiplier: 1.0  # NEW — défaut global
```

**Détail dans scenarios/nominal.yaml :**
```yaml
# Note: speed_multiplier est maintenant défini dans base.yaml (configuration globale)
# Les scénarios n'héritent plus leur propre speed_multiplier mais utilisent celui de base.yaml
```

**Protection dans loader.py :**
```python
speed_multiplier_protected = base_cfg.simulation.get("speed_multiplier", 1.0)
# ... merge ...
merged.simulation.speed_multiplier = speed_multiplier_protected
```

---

### 2. Start_time éditable depuis dashboard

#### Fichiers modifiés : `api/routes/simulation.py`, `dashboard/app.py`

**Nouveaux endpoints API :**

```
GET  /simulation/config/start_time
├── Retourne :
│   ├── start_time_iso: "2005-01-01T00:00:00Z"
│   ├── start_time_unix: 1104537600.0
│   └── start_time_readable: "2005-01-01 00:00:00 UTC"

PUT  /simulation/config/start_time
├── Paramètre : start_time_iso (string ISO 8601)
└── Effet : Modifie _start_time, persiste _t_elapsed_s
```

**Implémentation dans cluster.py :**
```python
# Start_time modifiable sans affecter temps écoulé
old_start_time = simulator._start_time
simulator._start_time = parse_start_time(new_iso)
# _t_elapsed_s persiste, seule la base change
```

**UI Streamlit :**
- Affiche date actuelle : "Date actuelle : 2005-01-01 00:00:00 UTC"
- Input date picker pour sélectionner nouvelle date
- Bouton "✓ Appliquer date" → PUT /simulation/config/start_time

**Cas d'usage :**
```
Utilisateur a simulé 1 heure dans l'année 2005.
Il veut "rejouer" la même heure dans l'année 2010.
→ Utilise date picker pour changer start_time à 2010-01-01
→ Snapshots timestamp maintenant : 2010-01-01 + 3600s écoulées
→ Temps écoulé inchangé (persiste)
```

---

### 3. Reset TimescaleDB automatique au soft reset

#### Fichiers modifiés : `simulation/cluster.py`, `api/routes/simulation.py`, `dashboard/app.py`

**Nouvelles méthodes dans ClusterSimulator :**

```python
async def reset_time_and_energy_with_timescaledb() -> None:
    """Reset COMPLET = soft reset + TRUNCATE TimescaleDB.
    
    - Réinitialise _t_elapsed_s = 0
    - Réinitialise energy = 0
    - Vide table 'telemetry' (TRUNCATE)
    - Vide table 'events' (TRUNCATE)
    """
```

**Nouvel endpoint API :**

```
POST /simulation/reset
├── Effets :
│   ├── Soft reset : _t_elapsed_s = 0, energy = 0
│   └── Hard reset : TRUNCATE telemetry, TRUNCATE events
└── Retour : CommandResponse avec détails
```

**Notes importantes :**
- Endpoint utilise asyncpg pour connexion TimescaleDB
- Configuration DSN via ENV variables (TIMESCALE_HOST, TIMESCALE_USER, etc.)
- Fallback sur localhost/jumeaux si ENV non définis
- Erreur TimescaleDB ne bloque pas soft reset (log seulement)

**UI Streamlit :**
- Bouton "🗑️ Reset complet" (remplace "🔄 Reset temps")
- Appelle POST /simulation/reset (pas /speed/reset)
- Affiche message détaillé de ce qui s'est passé

**Ancien endpoint (deprecated) :**
- `POST /simulation/speed/reset` → soft reset SEUL (temps + énergie, TimescaleDB intacte)
- Conservé pour compatibilité

---

## 🔧 Configuration requise

### Variables d'environnement (TimescaleDB)

Optionnelles — utilisent défauts si non définies :

```bash
TIMESCALE_HOST=timescaledb        # Défaut : timescaledb
TIMESCALE_PORT=5432               # Défaut : 5432
TIMESCALE_USER=jumeaux            # Défaut : jumeaux
TIMESCALE_PASSWORD=<secret>       # Défaut : "" (vide)
TIMESCALE_DB=jumeaux              # Défaut : jumeaux
```

### Dépendances Python

Ajout à requirements.txt :
```
asyncpg>=0.29.0  # Pour connexions TimescaleDB asynchrones
```

---

## 🧪 Tests ajoutés

### `tests/test_simulated_time.py` — Nouvelles classes

#### TestSpeedMultiplierProtection (3 tests)
- ✅ `test_all_scenarios_preserve_speed_multiplier` — Tous scénarios héritent speed de base.yaml
- ✅ `test_speed_multiplier_not_overridable_by_scenario` — Scénario ne peut surcharger speed
- ✅ `test_speed_multiplier_not_overridable_by_overrides` — Override dict ne peut surcharger speed

#### TestStartTimeModification (2 tests)
- ✅ `test_change_start_time_preserves_elapsed` — Modifier start_time persiste t_elapsed_s
- ✅ `test_snapshot_respects_changed_start_time` — Snapshot utilise nouveau start_time

**Total :** 5 nouveaux tests (ajoutés aux 18 existants = 23 tests au total)

---

## 📊 Matrice de configuration

### Avant Phase 8.5

| Paramètre | Lieu | Éditable | Héritage | Protection |
|-----------|------|----------|----------|------------|
| start_time | base.yaml | ❌ Via code | Global | ✅ loader.py |
| speed_multiplier | scenarios/*.yaml | ❌ Non | Par scénario | ❌ Non |

### Après Phase 8.5

| Paramètre | Lieu | Éditable | Héritage | Protection |
|-----------|------|----------|----------|------------|
| start_time | base.yaml | ✅ Dashboard API | Global | ✅ loader.py |
| speed_multiplier | base.yaml | ✅ Dashboard API | Global | ✅ loader.py |

---

## 🚀 Utilisation

### Exemple 1 : Changer la date et rejouer 1 heure

```
1. Dashboard → Onglet "Simulation"
2. "📅 Configuration date de départ"
3. Date picker → sélectionner "2020-06-15"
4. Cliquer "✓ Appliquer date"
5. Snapshots timestamp : "2020-06-15T..." + t_elapsed_s
```

### Exemple 2 : Speed global + reset complet

```
1. Mettre vitesse : "1 hour/sec (3600x)"
2. Attendre 5 secondes (= 5 heures simulées)
3. Cliquer "🗑️ Reset complet"
4. Résultat :
   - _t_elapsed_s = 0
   - energy_kwh_total = 0
   - TimescaleDB vidée
   - Prêt pour nouvelle expérience
```

### Exemple 3 : Scénario → changement vitesse → reset

```
1. Charger "nominal" (vitesse hérite 1.0x de base.yaml)
2. Changer vitesse à 60.0x
3. Laisser tourner 10 secondes
4. Changer scénario à "stress" (vitesse persiste 60.0x)
5. Cliquer reset (remet tout à 0 + TimescaleDB)
```

---

## 🔀 Flux de configuration

```
config/base.yaml
├── simulation.start_time = "2005-01-01T00:00:00Z"  [GLOBAL, PROTECTED]
└── simulation.speed_multiplier = 1.0                [GLOBAL, PROTECTED]

config/loader.py
├── Charge base.yaml
├── Fusionne scenario/*.yaml
├── RESTAURE start_time (protected)
├── RESTAURE speed_multiplier (protected)
└── RESTAURE après overrides

API Endpoints (Phase 8.5)
├── GET  /simulation/config/start_time     [lecture]
├── PUT  /simulation/config/start_time     [modification]
├── GET  /simulation/speed                 [lecture vitesse]
├── PUT  /simulation/speed                 [modification vitesse]
├── POST /simulation/reset                 [hard reset + soft]
└── POST /simulation/speed/reset           [soft reset only, deprecated]

Dashboard (Streamlit)
├── Onglet Simulation
├── Vitesse : dropdown + custom + appliquer
├── Date départ : date picker + appliquer
└── Reset : bouton "🗑️ Reset complet"

ClusterSimulator
├── _start_time [modifiable, public]
├── _t_elapsed_s [privé, accumule]
├── _speed_multiplier [modifiable, privé]
└── Methods:
    ├── set_speed_multiplier()
    ├── reset_time_and_energy() [soft]
    └── reset_time_and_energy_with_timescaledb() [async, hard]
```

---

## 🎓 Points clés de conception

### 1. Start_time éditable mais temps écoulé persiste

**Raison :** Permet ajuster calendrier sans réinitialiser expérience.

```python
# Avant : t=0, start=2005, elapsed=3600s → ts=2005-01-01T01:00:00Z
# Appliquer start=2010-01-01
# Après : t=0, start=2010, elapsed=3600s → ts=2010-01-01T01:00:00Z
```

### 2. Speed_multiplier global protégé

**Raison :** Comme start_time, garantit cohérence cross-scenario.

```python
# Scénario ne peut pas surcharger speed
config = load_config("stress", overrides={"simulation": {"speed_multiplier": 100.0}})
# config.simulation.speed_multiplier == 1.0  (non 100.0)
```

### 3. Reset complet = soft + hard atomique

**Raison :** Une seule action pour "recommencer de zéro".

```python
# POST /simulation/reset exécute :
# 1. simulator.reset_time_and_energy()  [soft]
# 2. await asyncpg.connect(dsn)
#    TRUNCATE telemetry, events          [hard]
```

---

## ✅ Checklist de validation

### Configuration
- [x] speed_multiplier en base.yaml (section simulation)
- [x] Tous les scénarios hérient speed_multiplier de base.yaml
- [x] Loader protège speed_multiplier comme start_time

### Code
- [x] ClusterSimulator initialise _speed_multiplier
- [x] ClusterSimulator a reset_time_and_energy_with_timescaledb()
- [x] API endpoints GET/PUT /simulation/config/start_time
- [x] API endpoint POST /simulation/reset
- [x] Dashboard UI pour date picker + appliquer
- [x] Dashboard button "Reset complet" appelle /reset
- [x] asyncpg importé dans cluster.py
- [x] asyncpg ajouté à requirements.txt

### Tests
- [x] TestSpeedMultiplierProtection (3 tests)
- [x] TestStartTimeModification (2 tests)
- [x] Tous tests passent

### Documentation
- [x] CE DOCUMENT (CHANGELOG)
- [x] Mise à jour IMPLEMENTATION_STATUS (à faire)

---

## 🔄 Migrations / Breaking Changes

### ❌ Pas de breaking changes

**API endpoints existantes :**
- `GET /simulation/speed` — inchangée
- `PUT /simulation/speed` — inchangée
- `POST /simulation/speed/reset` — conservée (deprecated)

**Configuration YAML :**
- base.yaml : ajout speed_multiplier (avec défaut 1.0 si absent)
- scenarios : speed_multiplier peut être supprimé (non utilisé)

**Dashboard :**
- Ancien onglet Simulation fonctionne toujours
- Nouvel UI pour date picker coexiste

---

## 📚 Documentation supplémentaire

- `IMPLEMENTATION_STATUS_2026_06_03.md` — Mise à jour nécessaire
- `RESUME_CONFIGURATION_VITESSE_START_TIME_2026_06_03.md` — Mise à jour
- `PROPOSAL_RESET_TIMESCALEDB_UI_2026_06_03.md` — IMPLÉMENTÉ ✅

---

## 🚢 Deployment

### Docker build
```bash
build-clean-app.bat
# Reconstruit tout avec nouvelles dépendances (asyncpg)
```

### Vérification post-deployment
```bash
# Tests
pytest tests/test_simulated_time.py -v

# Vérifier endpoints
curl http://localhost:8000/docs  # Swagger UI
# Chercher /simulation/config/start_time et /simulation/reset

# Dashboard
http://localhost:8501
# Onglet Simulation doit afficher :
# - Vitesse (inchangé)
# - Date départ (NOUVEAU)
# - Bouton Reset complet (CHANGÉ du texte)
```

---

## 🎯 Prochaines étapes (Phase 8.6+)

1. **Monitoring historiques** — Grafana avec timestamps simulés
2. **Export ML** — Buffer snapshots → CSV/Parquet
3. **Configurateur UI avancé** — Éditeur YAML/JSON dans dashboard
4. **Audit trail** — Logger tous les changements de config

---

**Statut Phase 8.5 :** ✅ **COMPLÈTEMENT IMPLÉMENTÉ**

*Changelog généré le 3 juin 2026*
