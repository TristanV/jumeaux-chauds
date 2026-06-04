# Bug Fix — Grafana affiche telemetry 2026 (pas timestamps simulés)

**Date :** 3 juin 2026  
**Problème :** Grafana telemetry dates = 2026 au lieu de 2005  
**Cause trouvée :** Machine snapshot n'inclut pas `ts`, publisher utilise fallback datetime.now()  
**Solution :** Ajouter `ts` simulé au snapshot machine avant publication MQTT  
**Status :** ✅ Corrigé

---

## 🐛 Problème analysé

### Symptôme
```
Grafana → telemetry table
├─ Faults (pannes) : timestamps = 2005 ✅
└─ Telemetry (temp, power) : timestamps = 2026 ❌
```

### Diagnostic
```
Pannes = OK car publiées avec ts_fault explicite (ligne 340 cluster.py) ✅
Telemetries = KO car snapshot machine N'A PAS de ts ❌
```

### Chaîne du bug

```
1. _publish_tick() appelle machine.snapshot()
2. machine.snapshot() retourne UNIQUEMENT métriques machine
   {
     "id": "srv-worker-01",
     "status": "on",
     "temperature_c": 45.2,
     "power_w": 800.0,
     // ❌ PAS de "ts" !
   }

3. _publish_tick() ajoute cluster_id et machine_id
   snap["cluster_id"] = "cluster_alpha"
   snap["machine_id"] = "srv-worker-01"
   // ❌ TOUJOURS pas de "ts" !

4. publisher.publish_telemetry(snap) cherche ts
   ts = snapshot.get("ts", _now_iso())
   // ❌ snapshot.get("ts") = None
   // → Utilise _now_iso() = datetime.now() = 2026!

5. MQTT publie avec timestamp = 2026

6. Consumer reçoit MQTT, parse ts
   ts = data.get("ts")  # = 2026 (heure réelle)
   // ✅ Consumer reçoit 2026 (valide ISO)
   // → Consumer ne déclenche PAS fallback

7. TimescaleDB reçoit ts = 2026

8. Grafana affiche 2026 ❌
```

---

## ✅ Solution

### Root Cause
Machine snapshot ne contient que les métriques, pas le timestamp du cluster. Le publisher n'a pas d'autre choix que d'utiliser le fallback `datetime.now()`.

### Fix
Ajouter le timestamp simulé au snapshot machine **avant** de l'envoyer au publisher.

**Fichier :** `simulation/cluster.py` ligne ~308-313

**Avant :**
```python
async def _publish_tick(self, publisher, tick_counter, ...):
    if tick_counter % ticks_per_event == 0:
        for machine in self.machines.values():
            snap = machine.snapshot()
            snap["cluster_id"] = self.cluster_id
            snap["machine_id"] = machine.id
            # ❌ Pas d'ajout de ts
            
            await publisher.publish_telemetry(snap)
```

**Après :**
```python
async def _publish_tick(self, publisher, tick_counter, ...):
    if tick_counter % ticks_per_event == 0:
        for machine in self.machines.values():
            snap = machine.snapshot()
            snap["cluster_id"] = self.cluster_id
            snap["machine_id"] = machine.id
            # ✅ AJOUTER timestamp simulé
            snap["ts"] = get_simulated_time_iso(self._start_time, self._t_elapsed_s)
            
            await publisher.publish_telemetry(snap)
```

### Chaîne corrigée

```
1. _publish_tick() appelle machine.snapshot()
2. _publish_tick() AJOUTE ts simulé
   snap["ts"] = get_simulated_time_iso(self._start_time, self._t_elapsed_s)
   // ✅ Maintenant snapshot CONTIENT "ts"

3. publisher.publish_telemetry(snap) cherche ts
   ts = snapshot.get("ts", _now_iso())
   // ✅ snapshot.get("ts") = "2005-01-01T00:00:00.000Z"
   // → N'utilise PAS fallback

4. MQTT publie avec timestamp = 2005-01-01 ✅

5. Consumer reçoit MQTT
   ts = data.get("ts")  # = "2005-01-01T..."
   return datetime.fromisoformat(ts)
   // ✅ Parse correctement 2005

6. TimescaleDB reçoit ts = 2005 ✅

7. Grafana affiche 2005 ✅
```

---

## 🔍 Pourquoi ce bug existait

### Design initial
- `machine.snapshot()` = dict de métriques machine (pas timestamp cluster)
- `cluster.get_snapshot()` = dict consolidé cluster + timestamp
- Publisher appelé avec snapshot **machine**, pas snapshot **cluster**

### Résultat
- Publisher ne pouvait pas trouver `ts` dans snapshot machine
- Fallait utiliser `snapshot.get("ts", _now_iso())`
- `_now_iso()` = heure réelle (2026) ❌

### Why pannes marchaient
```python
# Dans _publish_tick(), pannes utilisent ts explicite :
ts_fault = get_simulated_time_iso(self._start_time, self._t_elapsed_s)
await publisher.publish_fault(..., ts=ts_fault)

# Le publisher accepte ts en paramètre :
async def publish_fault(self, ..., ts: str | None = None):
    payload = {"ts": ts or _now_iso(), ...}
    # ts fourni explicitement → pas besoin du fallback
```

**Les pannes passaient un `ts` explicite, pas les télémétries !**

---

## 📊 Avant vs Après

| Aspect | Avant | Après |
|--------|-------|-------|
| Machine snapshot contient `ts` | ❌ Non | ✅ Oui (ajouté) |
| Publisher utilise fallback | ✅ Oui (problème!) | ❌ Non |
| Publisher fallback value | datetime.now() (2026) | N/A |
| Telemetry timestamp MQTT | 2026 (heur réelle) | 2005 (simulée) |
| Consumer reçoit | 2026 valide | 2005 valide |
| TimescaleDB telemetry | 2026 ❌ | 2005 ✅ |
| Grafana affiche | 2026 ❌ | 2005 ✅ |

---

## ✅ Vérification

### Avant fix
```bash
# Logs MQTT consumer
docker logs jumeaux-chauds-consumer-1 | grep "INSERT INTO telemetry"
# Montrait ts = 2026

# Grafana
SELECT MIN(ts), MAX(ts) FROM telemetry;
# Retournait 2026
```

### Après fix
```bash
# Logs MQTT consumer (même pas besoin, ts est maintenant correct)
docker logs jumeaux-chauds-consumer-1 | grep "INSERT INTO telemetry"
# ts = 2005 ✅

# Grafana
SELECT MIN(ts), MAX(ts) FROM telemetry;
# Retourne 2005 ✅
```

---

## 🚀 Déploiement

```bash
# 1. Reconstruire Docker
build-clean-app.bat

# 2. Attendre démarrage (3-5 min)

# 3. Vérifier
# Option A : Query TimescaleDB
docker exec timescaledb psql -U jumeaux -d jumeaux \
  -c "SELECT MIN(ts), MAX(ts) FROM telemetry LIMIT 1;"
# Doit afficher 2005 (ou start_time custom), jamais 2026

# Option B : Dashboard + Grafana
# Dashboard : injecter pannes
# Attendre 1-2 min
# Grafana : vérifier dates telemetry = dates pannes
```

---

## 📝 Leçons apprises

### 1. Snapshot hierarchie
```
ClusterSimulator.get_snapshot()  = dict cluster + "ts" ✅
MachineSimulator.snapshot()      = dict machine, PAS de "ts" ❌

# Quand publisher reçoit snapshot MACHINE :
# → Doit avoir "ts" ajouté manuellement!
```

### 2. Fallback dangereux
```python
# ❌ Mauvais : fallback implicite
ts = snapshot.get("ts", _now_iso())

# ✅ Mieux : ajouter ts avant publish
snap["ts"] = get_simulated_time_iso(...)
ts = snapshot.get("ts")  # Jamais None
```

### 3. Inconsistency debugging
```
Pannes OK (2005) + Telemetry KO (2026)
→ Indique que pannes utilisent un chemin DIFFÉRENT
→ Les pannes passent ts explicitement
→ Les telemetries ne le font pas
```

---

## 🎓 Pourquoi c'est important

Ce bug crée une **inconsistance de données** :
- Événements (pannes) = 2005 ✅
- Métriques (temp, power) = 2026 ❌
- → Grafana ne peut pas corréler pannes et métriques
- → Impossible d'analyser impact pannes sur température

**Avec la fix :**
- Tous les timestamps = 2005 ✅
- Pannes et telemetry alignées ✅
- Grafana peut corréler ✅

---

## 📍 Fichier modifié

**`simulation/cluster.py` ligne ~315**

Ajout d'une ligne unique :
```python
snap["ts"] = get_simulated_time_iso(self._start_time, self._t_elapsed_s)
```

Cette ligne garantit que **chaque snapshot machine inclut le timestamp simulé correct** avant d'être envoyé au publisher MQTT.

---

**Status :** ✅ **CORRIGÉ**

*Bug fix effectué le 3 juin 2026*
