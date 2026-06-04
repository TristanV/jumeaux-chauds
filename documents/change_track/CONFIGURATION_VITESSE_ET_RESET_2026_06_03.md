# Configuration de vitesse et reset de simulation

**Date :** 3 juin 2026  
**Statut :** ✅ Entièrement implémenté et accessible  
**Audience :** Développeurs et utilisateurs du dashboard

---

## Vue d'ensemble

| Question | Réponse | Détail |
|----------|---------|--------|
| **Où est la vitesse définie ?** | Fichier YAML | `config/scenarios/*.yaml` |
| **Peut-on la charger depuis Streamlit ?** | ✅ **OUI** | Via endpoint API GET `/simulation/speed` |
| **Peut-on la modifier depuis Streamlit ?** | ✅ **OUI** | Via endpoint API PUT `/simulation/speed` |
| **Reset complet possible ?** | ✅ **OUI** | Endpoint API POST `/simulation/speed/reset` |
| **Tables vidées au reset ?** | ❌ **NON** | Juste le temps et l'énergie de la sim |

---

## 1. Configuration de la vitesse

### 1.1 Emplacement dans les fichiers

**Fichier :** `config/scenarios/{scenario}.yaml`

**Exemple (nominal.yaml) :**
```yaml
simulation:
  mode: "nominal"
  tick_rate_hz: 10.0
  events_per_sec: 1.0
  duration: "0"

  # Phase 8.4 — Contrôle de vitesse de simulation
  speed_multiplier: 1.0              # ← VITESSE (défaut: real-time)
                                     # 60.0 = 1 min/sec
                                     # 3600.0 = 1 hour/sec
                                     # 86400.0 = 1 day/sec

  cpu_throttle_enabled: true         # ← Limiter fréquence réelle
  cpu_throttle_target_hz: 100.0      # ← Fréquence cible réelle
```

### 1.2 Paramètres configurables

| Paramètre | Type | Défaut | Plage | Rôle |
|-----------|------|--------|-------|------|
| `speed_multiplier` | float | 1.0 | > 0 | Accélération du temps simulé |
| `cpu_throttle_enabled` | bool | true | — | Activer limitation CPU |
| `cpu_throttle_target_hz` | float | 100.0 | [50, 500] | Max ticks/sec réels |
| `tick_rate_hz` | float | 10.0 | > 0 | Fréquence base simulation |

### 1.3 Prédéfinies

```
1.0         → Real-time (1 sec/sec)
60.0        → 1 min/sec
3600.0      → 1 hour/sec
86400.0     → 1 day/sec
Personnalisé → Toute valeur > 0
```

---

## 2. Accès depuis le dashboard Streamlit

### 2.1 Section UI existante

**Fichier :** `dashboard/app.py` (lignes 366-417)

**Onglet :** "🎬 Simulation"

**Interface :**
```
┌─────────────────────────────────────────┐
│ ⚙️  Contrôle de vitesse de simulation    │
├─────────────────────────────────────────┤
│ Sélectionner vitesse:                   │
│ ┌──────────────────────────────────┐    │
│ │ Real-time (1x)                   │ ◄──┤ Dropdown avec
│ │ 1 min/sec (60x)                  │    │ options prédéfinies
│ │ 1 hour/sec (3600x)               │    │ ou personnalisée
│ │ 1 day/sec (86400x)               │    │
│ │ Personnalisé                     │    │
│ └──────────────────────────────────┘    │
│                                         │
│ Multiplier personnalisé: [________]     │
│ (Min: 0.1, Max: 1000000)               │
│                                         │
│ [✓ Appliquer vitesse]  [🔄 Reset temps]│
│                                         │
│ ℹ️ Vitesse courante: Real-time (1.0x)  │
└─────────────────────────────────────────┘
```

### 2.2 Code de chargement

```python
# dashboard/app.py:369-375
try:
    speed_info = api._get("/simulation/speed")
    current_speed = speed_info.get("speed_multiplier", 1.0)
    current_speed_name = speed_info.get("speed_name", "Real-time")
except Exception:
    current_speed = 1.0
    current_speed_name = "Real-time"
```

**Endpoint appelé :** `GET /simulation/speed`

**Réponse :**
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

## 3. Modification depuis Streamlit

### 3.1 Interface de contrôle

**Code (dashboard/app.py:388-420) :**

```python
# 1. Sélectionner la vitesse (prédéfinie ou custom)
selected_speed_name = st.selectbox(
    "Sélectionner vitesse",
    ["Real-time (1x)", "1 min/sec (60x)", "1 hour/sec (3600x)", 
     "1 day/sec (86400x)", "Personnalisé"],
    key="speed_select"
)

# 2. Si personnalisée, input numérique
if selected_speed_name == "Personnalisé":
    speed_to_apply = st.number_input("Multiplier personnalisé", 
                                     min_value=0.1, max_value=1000000.0)
else:
    speed_to_apply = speed_options[selected_speed_name]

# 3. Bouton d'application
if st.button("✓ Appliquer vitesse", key="btn_apply_speed"):
    res = api._put("/simulation/speed", {"speed_multiplier": speed_to_apply})
    if res.get("ok"):
        st.success(f"✅ Vitesse appliquée : {speed_to_apply}x")
```

### 3.2 Endpoint API utilisé

**URL :** `PUT /simulation/speed`

**Payload :**
```json
{
  "speed_multiplier": 3600.0
}
```

**Réponse :**
```json
{
  "ok": true,
  "message": "Vitesse changée à 3600.0x (1 hour/sec)"
}
```

### 3.3 Implémentation backend

**Fichier :** `api/routes/simulation.py:151-199`

```python
@router.put("/speed", response_model=CommandResponse)
async def change_speed(speed_multiplier: float | None = None) -> CommandResponse:
    """Change la vitesse de simulation à chaud."""
    simulator = deps.get_cluster()
    
    if speed_multiplier is None or speed_multiplier <= 0:
        raise HTTPException(status_code=400)
    
    simulator.set_speed_multiplier(speed_multiplier)
    
    return CommandResponse(
        ok=True,
        message=f"Vitesse changée à {speed_multiplier}x"
    )
```

**Implémentation Simulator (cluster.py:430-454) :**

```python
def set_speed_multiplier(self, multiplier: float) -> None:
    """Change la vitesse à chaud sans réinitialiser la simulation."""
    if multiplier <= 0:
        raise ValueError(f"speed_multiplier must be > 0")
    
    self._speed_multiplier = multiplier
    logger.info(f"Speed changed to {multiplier}x")
```

---

## 4. Reset de la simulation

### 4.1 Deux niveaux de reset possibles

| Niveau | Scope | Bouton UI | Endpoint |
|--------|-------|-----------|----------|
| **Soft reset** | Temps + énergie sim | 🔄 Reset temps | POST `/simulation/speed/reset` |
| **Hard reset** | Tables TimescaleDB | ❌ Pas d'UI | Manuel (Docker/psql) |

### 4.2 Soft reset (dans Streamlit)

**Interface :**
```python
# dashboard/app.py:405-414
if st.button("🔄 Reset temps", key="btn_reset_time"):
    try:
        res = api._post("/simulation/speed/reset", {})
        if res.get("ok"):
            st.success("✅ Temps et énergie réinitialisés")
    except Exception as e:
        st.error(f"❌ Erreur : {e}")
```

**Endpoint :** `POST /simulation/speed/reset`

**Réponse :**
```json
{
  "ok": true,
  "message": "Temps écoulé et énergie réinitialisés"
}
```

**Impact :**
```
Avant:  _t_elapsed_s = 3600.0 sec,  energy_kwh_total = 5.2 kWh
        └─ Snapshot ts = 2005-01-01T01:00:00

Après:  _t_elapsed_s = 0.0 sec,     energy_kwh_total = 0.0 kWh
        └─ Snapshot ts = 2005-01-01T00:00:00  ← Temps recommence
```

### 4.3 Implémentation backend

**Fichier :** `api/routes/simulation.py:202-217`

```python
@router.post("/speed/reset", response_model=CommandResponse)
async def reset_time_and_energy() -> CommandResponse:
    """Réinitialise temps écoulé et énergie.
    
    Note: Ne touche pas aux tables TimescaleDB.
    """
    simulator = deps.get_cluster()
    simulator.reset_time_and_energy()
    
    return CommandResponse(
        ok=True,
        message="Temps écoulé et énergie réinitialisés"
    )
```

**Implémentation Simulator (cluster.py:517-529) :**

```python
def reset_time_and_energy(self) -> None:
    """Réinitialise le temps écoulé et l'énergie."""
    self._t_elapsed_s = 0.0
    self.energy_kwh_total = 0.0
    self.cost_eur_total = 0.0
    
    for machine in self.machines.values():
        machine.energy_kwh_cumulated = 0.0
    
    logger.info("Time and energy metrics reset")
```

---

## 5. Reset complet (tables TimescaleDB)

### 5.1 Situation actuelle

**❌ Pas accessible depuis le dashboard Streamlit**

**Raison :** Consommateur MQTT écrit dans la BDD indépendamment.  
Vider les tables de la UI serait incohérent avec les données qui arrivent du MQTT.

### 5.2 Reset manuel de TimescaleDB

**Commande :**
```bash
docker exec -it timescaledb psql -U jumeaux -d jumeaux \
  -c "TRUNCATE TABLE telemetry; TRUNCATE TABLE events;"
```

**Ou depuis build-clean-app.bat :**
- Les volumes sont supprimés et recréés
- ✅ Tables vidées automatiquement

### 5.3 Recommandation

**Pour reset complet :**
1. Reset soft dans Streamlit (`🔄 Reset temps`)
2. Vider TimescaleDB manuellement :
   ```bash
   docker compose down
   docker volume rm jumeaux-chauds_timescale_data
   docker compose up -d
   ```

---

## 6. Flux complet : Changement de vitesse en direct

### Scénario : Accélérer simulation de 1x vers 3600x

```
1. Utilisateur sur dashboard, onglet "Simulation"
   ↓

2. Dropdown "Sélectionner vitesse" → "1 hour/sec (3600x)"
   ↓

3. Bouton "✓ Appliquer vitesse"
   ↓ (asynchrone)

4. Dashboard appelle: PUT /simulation/speed
   └─ Payload: {"speed_multiplier": 3600.0}
   ↓

5. API route (simulation.py:151) reçoit
   └─ Valide speed_multiplier > 0
   └─ Appelle simulator.set_speed_multiplier(3600.0)
   ↓

6. ClusterSimulator met à jour:
   self._speed_multiplier = 3600.0
   └─ À partir du PROCHAIN tick:
      _t_elapsed_s += dt * 3600.0  (au lieu de * 1.0)
   ↓

7. API retourne: {"ok": true, "message": "..."}
   ↓

8. Dashboard affiche: ✅ Vitesse appliquée : 3600.0x
   ↓

9. Résultat observable:
   - Snapshot ts change 3600× plus vite
   - MQTT publie données avec timestamps qui avancent vite
   - TimescaleDB reçoit events avec timestamps 2005+heure
   - Grafana affiche données en temps "rapide"
```

---

## 7. Cas d'usage courants

### Cas 1 : Test rapide d'une journée complète

```
1. Lancer simulation: nominal (1x real-time)
2. Vérifier quelques minutes de données
3. Switcher vers: "1 day/sec (86400x)"
   → 1 journée simulée = 1 seconde réelle
4. Attendre 10 secondes → 10 jours simulés
5. Reset temps avec 🔄 Reset temps
6. Recommencer
```

**Avantage :** Voir des jours de données en secondes

---

### Cas 2 : Génération massive de données ML

```
1. Lancer: busy_weeks (7 jours de charge réaliste)
2. Vitesse: "1 day/sec (86400x)"
   → 7 jours simulés = 7 secondes réelles
3. Lancer 30 fois pour 30×7 = 210 jours de données
4. Export snapshots pour ML training
5. Exporter depuis buffer: /snapshots/export
```

**Avantage :** Millions de snapshots en minutes

---

### Cas 3 : Analyse thermique d'une vague de chaleur

```
1. Scénario: heatwave (24h de chaleur croissante)
2. Vitesse: 1x (real-time) pour observation fine
3. Injecter pannes manuellement
4. Observer réaction cluster
5. Si besoin plus d'heures: Switcher à 60x (1 min/sec)
6. Reset temps pour nouvelle expérience
```

**Avantage :** Contrôle précis + accélération possible

---

## 8. Tableau récapitulatif

### Où configurer quoi

| Élément | Fichier YAML | API endpoint | Streamlit UI | Éditable |
|---------|-------------|---|---|---|
| **start_time** | config/base.yaml | ❌ | ❌ | ❌ Immutable |
| **speed_multiplier** | config/scenarios/*.yaml | ✅ PUT | ✅ | ✅ À chaud |
| **cpu_throttle_enabled** | config/scenarios/*.yaml | ❌ | ❌ | ❌ Startup only |
| **tick_rate_hz** | config/scenarios/*.yaml | ❌ | ❌ | ❌ Startup only |
| **Temps écoulé** | — (mémoire) | ✅ GET | ✅ | — (calculé) |
| **Énergie cumulée** | — (mémoire) | ✅ GET | ✅ | ✅ Reset seulement |

---

## 9. Points importants

### ✅ Changements à chaud (sans restart)
- `speed_multiplier` — Peut changer à tout moment
- Snapshot/MQTT timestamps — Recalculés à chaque tick

### ❌ Changements startup only
- `tick_rate_hz`
- `cpu_throttle_enabled` / `cpu_throttle_target_hz`
- `start_time` (immutable pour toujours)

### ⚠️ Reset partiel (soft)
- `_t_elapsed_s` → réinitialisé à 0
- `energy_kwh_total` → réinitialisé à 0
- **Mais :** `start_time` inchangé → temps recommence à 2005-01-01
- **Mais :** Tables TimescaleDB **pas** vidées

---

## 10. Prochaines évolutions possibles

### Si tu veux un reset complet depuis Streamlit:

**Option A : Endpoint pour vider TimescaleDB**
```python
@router.post("/reset/timescaledb")
async def reset_timescaledb():
    """Vide les tables telemetry et events."""
    # Connecter à TimescaleDB, TRUNCATE tables
    return CommandResponse(ok=True)
```

**Option B : Endpoint pour soft+hard reset**
```python
@router.post("/reset/complete")
async def reset_complete():
    """Soft reset + hard reset TimescaleDB."""
    simulator.reset_time_and_energy()
    timescaledb.truncate_all()
    return CommandResponse(ok=True)
```

**Option C : Ajouter contrôle throttle en direct**
```python
@router.put("/cpu-throttle")
async def set_cpu_throttle(enabled: bool, target_hz: float | None = None):
    simulator.set_cpu_throttle(enabled, target_hz)
```

---

## Résumé des réponses à tes questions

| Question | Réponse | Détail |
|----------|---------|--------|
| **Où est définie la vitesse ?** | `config/scenarios/*.yaml` | `speed_multiplier: 1.0` |
| **Chargeable depuis Streamlit ?** | ✅ OUI | `GET /simulation/speed` |
| **Modifiable depuis Streamlit ?** | ✅ OUI | `PUT /simulation/speed` + UI onglet "Simulation" |
| **Reset complet possible ?** | ⚠️ PARTIEL | Soft reset via UI, hard reset manuel |
| **Tables vidées au reset ?** | ❌ NON | Juste temps + énergie simulateur |

---

*Document actualisé le 3 juin 2026*
