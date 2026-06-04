# Résumé : Configuration de vitesse et date de départ

**Date :** 3 juin 2026  
**Format :** Quick reference  
**Audience :** Tous

---

## Tableau d'accès complet

### Configuration : Où et comment

| Paramètre | Fichier YAML | Valeur | Éditable | Endroit |
|-----------|-------------|--------|----------|---------|
| **start_time** | `config/base.yaml` | "2005-01-01T00:00:00Z" | ❌ JAMAIS | Ligne 3 |
| **speed_multiplier** | `config/scenarios/*.yaml` | 1.0 | ✅ À chaud | dashboard UI |
| **tick_rate_hz** | `config/scenarios/*.yaml` | 10.0 | ❌ Init only | — |
| **cpu_throttle_enabled** | `config/scenarios/*.yaml` | true | ❌ Init only | — |
| **cpu_throttle_target_hz** | `config/scenarios/*.yaml` | 100.0 | ❌ Init only | — |

---

## Accès depuis Streamlit

### Charger les paramètres

```
Dashboard > Onglet "Simulation" > "⚙️ Contrôle de vitesse"
│
├─ Affiche: vitesse actuelle (via GET /simulation/speed)
└─ Affiche: temps écoulé, CPU throttle, etc.
```

**API endpoint :** `GET /simulation/speed`

**Informations retournées :**
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

---

### Modifier la vitesse

```
Dashboard > Onglet "Simulation"
│
├─ Sélectionner vitesse: [Dropdown]
│  ├─ Real-time (1x)
│  ├─ 1 min/sec (60x)
│  ├─ 1 hour/sec (3600x)
│  ├─ 1 day/sec (86400x)
│  └─ Personnalisé: [Number input]
│
└─ [✓ Appliquer vitesse] → PUT /simulation/speed
```

**API endpoint :** `PUT /simulation/speed`

**Payload :**
```json
{
  "speed_multiplier": 3600.0
}
```

---

### Reset : Soft (simulation)

```
Dashboard > Onglet "Simulation"
│
└─ [🔄 Reset temps] → POST /simulation/speed/reset
   │
   ├─ Réinitialise: _t_elapsed_s = 0
   ├─ Réinitialise: energy_kwh_total = 0
   ├─ Snapshots ts: revient à 2005-01-01T00:00:00
   └─ TimescaleDB: ❌ PAS AFFECTÉE
```

**API endpoint :** `POST /simulation/speed/reset`

---

### Reset : Hard (TimescaleDB)

```
❌ PAS ACCESSIBLE DEPUIS STREAMLIT ACTUELLEMENT

Pour vider manuellement:
$ docker exec -it timescaledb psql -U jumeaux -d jumeaux \
  -c "TRUNCATE TABLE telemetry; TRUNCATE TABLE events;"

OU via build-clean-app.bat (supprime/recrée les volumes)
```

**Voir :** `PROPOSAL_RESET_TIMESCALEDB_UI_2026_06_03.md` pour implémentation future

---

## Flux de données

### 1️⃣ Configuration YAML → ClusterSimulator

```
config/base.yaml
└─ simulation.start_time: "2005-01-01T00:00:00Z"
   │
   └─ ClusterSimulator.__init__()
      ├─ self._start_time = parse_start_time(...)
      └─ logger.info("Start time: 2005-01-01T00:00:00Z")

config/scenarios/{scenario}.yaml
└─ simulation.speed_multiplier: 1.0
   │
   └─ ClusterSimulator.__init__()
      ├─ self._speed_multiplier = 1.0
      └─ À chaque tick: self._t_elapsed_s += dt * self._speed_multiplier
```

---

### 2️⃣ ClusterSimulator → API

```
GET /simulation/speed
│
└─ simulator.get_speed_info()
   └─ Retourne {speed_multiplier, speed_name, elapsed_time_s, ...}

PUT /simulation/speed
│
├─ simulator.set_speed_multiplier(new_value)
└─ Immédiat: _speed_multiplier = new_value

POST /simulation/speed/reset
│
└─ simulator.reset_time_and_energy()
   ├─ self._t_elapsed_s = 0.0
   └─ self.energy_kwh_total = 0.0
```

---

### 3️⃣ API → Dashboard Streamlit

```
GET /simulation/speed
│
└─ dashboard/api_client.py._get("/simulation/speed")
   │
   └─ dashboard/app.py:tab_simulation()
      ├─ Affiche current_speed_name
      ├─ Affiche elapsed_time_formatted
      └─ Affiche cpu_throttle_enabled

PUT /simulation/speed
│
└─ dashboard/api_client.py._put("/simulation/speed", {...})
   │
   └─ User clicks button
      └─ st.success("✅ Vitesse appliquée")

POST /simulation/speed/reset
│
└─ dashboard/api_client.py._post("/simulation/speed/reset", {})
   │
   └─ User clicks button
      └─ st.success("✅ Temps réinitialisé")
```

---

## Cas d'usage courants

### 👤 Utilisateur 1 : Test rapide

```
1. Lancer dashboard
2. Vérifier snapshot actuel (GET /simulation/speed)
3. Voir: elapsed_time_s = 0, speed_name = "Real-time"
4. Mettre vitesse à "1 hour/sec (3600x)" [PUT]
5. Attendre 10 secondes (= 10 heures simulées)
6. Reset temps [POST]
7. Recommencer avec autre scénario
```

---

### 👤 Utilisateur 2 : Génération données ML

```
1. Charger scénario "busy_weeks" (7 jours)
2. Mettre vitesse à "1 day/sec (86400x)"
3. Attendre 7 secondes (= 7 jours simulés)
4. Export snapshots depuis buffer (~10K snapshots)
5. Répéter 30 fois → 300K snapshots pour ML
```

---

### 👤 Utilisateur 3 : Observation fine

```
1. Charger scénario "nominal"
2. Laisser vitesse à 1x (real-time)
3. Injecter pannes manuellement (dashboard)
4. Observer réaction cluster en temps réel
5. Si besoin plus d'heures: switcher à 60x
6. Reset si expérience échouée
```

---

## Questions-réponses

### Q: Peut-on changer de scénario sans reset du temps ?
**R:** ✅ OUI
```
t_elapsed_s = 3600
├─ Changer scénario: nominal → stress [PUT /scenario]
├─ load_config("stress") → start_time reste 2005 (protégé)
└─ t_elapsed_s continue à 3600 (pas touché)
    → Temps continue de la même place ✅
```

---

### Q: La date 2005 peut-elle être changée ?
**R:** ❌ NON, c'est immutable
```
start_time = "2005-01-01T00:00:00Z"
│
├─ Défini dans: config/base.yaml
├─ Protégé par: config/loader.py (restauration post-merge)
├─ Impossible à changer par: scénario, override, ENV
└─ Raison: Garantir continuité temps simulé
```

---

### Q: Vitesse peut être appliquée sans reboot ?
**R:** ✅ OUI, à chaud
```
speed_multiplier = 1.0
│
├─ Utilisateur: PUT /simulation/speed (3600.0)
├─ Simulator: self._speed_multiplier = 3600.0
└─ Dès prochain tick: dt × 3600.0 (au lieu de × 1.0)
   → Impact immédiat observable ✅
```

---

### Q: Reset complet possible ?
**R:** ⚠️ PARTIEL
```
Reset soft: ✅ Streamlit
├─ Temps simulé → 0
├─ Énergie → 0
└─ API: POST /simulation/speed/reset

Reset hard: ❌ Manuel
├─ TimescaleDB tables → vides
└─ Terminal: docker exec ... TRUNCATE
```

---

## Cheat sheet API

### Endpoints simulation

```bash
# Lire infos vitesse
curl -X GET http://localhost:8000/simulation/speed

# Changer vitesse
curl -X PUT http://localhost:8000/simulation/speed \
  -H "Content-Type: application/json" \
  -d '{"speed_multiplier": 3600.0}'

# Reset soft
curl -X POST http://localhost:8000/simulation/speed/reset

# Changer scénario
curl -X PUT http://localhost:8000/simulation/scenario \
  -H "Content-Type: application/json" \
  -d '{"scenario": "stress"}'

# Lister scénarios
curl -X GET http://localhost:8000/simulation/scenarios
```

---

## Architecture de configuration

```
config/base.yaml
├─ simulation.start_time = "2005-01-01T00:00:00Z"  ← GLOBAL & IMMUTABLE
├─ cluster.id = "cluster_alpha"
└─ cluster.role_profiles.*

config/scenarios/{scenario}.yaml
├─ simulation.mode = {scenario}
├─ simulation.speed_multiplier = 1.0  ← ÉDITABLE VIA UI
├─ simulation.tick_rate_hz = 10.0     ← STARTUP ONLY
├─ simulation.load_profile.*
└─ ⚠️ start_time ABSENT (hérité & protégé)

config/loader.py
├─ load base.yaml
├─ load scenarios/{scenario}.yaml
├─ merge avec PROTECTION: start_time toujours = base.yaml
└─ merge overrides avec re-protection
```

---

## Fichiers clés

| Fichier | Rôle | Pertinent |
|---------|------|-----------|
| `config/base.yaml` | Configuration globale | ✅ start_time |
| `config/scenarios/*.yaml` | Configuration scénarios | ✅ speed_multiplier |
| `config/loader.py` | Protection start_time | ✅ Logic |
| `simulation/cluster.py` | Simulateur | ✅ Tout |
| `api/routes/simulation.py` | Endpoints REST | ✅ /simulation/speed* |
| `dashboard/app.py` | UI Streamlit | ✅ tab_simulation() |
| `dashboard/api_client.py` | Client HTTP | ✅ Appels API |

---

## Pour aller plus loin

📖 **Lectures recommandées :**

1. `CONFIGURATION_VITESSE_ET_RESET_2026_06_03.md` — Détail complet
2. `RESTORATION_TEMPS_SIMULE_2026_06_03.md` — Implémentation temps simulé
3. `REFACTOR_GLOBAL_SIMULATION_TIME_2026_06_03.md` — Pourquoi start_time global
4. `PROPOSAL_RESET_TIMESCALEDB_UI_2026_06_03.md` — Futur : reset complet

---

## Checklist pour utilisateur

- [ ] J'ai lu ce document
- [ ] Je sais accéder à la vitesse dans Streamlit
- [ ] Je peux changer la vitesse
- [ ] Je comprends que start_time = 2005 (immutable)
- [ ] Je sais faire un reset soft
- [ ] Je sais comment faire un reset hard (manuel)

---

## Checklist pour développeur

- [ ] J'ai accès aux sources `/api`, `/dashboard`, `/config`
- [ ] Je comprends architecture loader + protection
- [ ] Je sais comment ajouter nouvel endpoint REST
- [ ] Je peux tester localement via `build-clean-app.bat`
- [ ] Je connais les endpoints Streamlit actuels

---

**Dernière mise à jour :** 3 juin 2026  
**Prochaine révision :** Après implémentation reset TimescaleDB UI

*Ce document récapitule la situation actuelle complète sur la configuration de vitesse et la date de départ de la simulation.*
