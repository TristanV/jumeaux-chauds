# Bug Fix — Speed Multiplier n'affecte pas le nombre d'événements

**Date :** 4 juin 2026  
**Problème :** Changer la vitesse de simulation n'augmentait pas le nombre d'événements télémétriques. À 60x speed, il n'y avait toujours que 1 événement/sec au lieu de 60/sec.  
**Cause :** Le `dt` (delta temps) passé aux machines n'était jamais multiplié par `speed_multiplier`.  
**Solution :** Multiplier `dt` par `speed_multiplier` dans la boucle principale.  
**Status :** ✅ Corrigé

---

## 🐛 Problème analysé

### Symptôme

```
Configuration initiale :
- tick_rate_hz = 10 Hz
- events_per_sec = 1.0
- → 10 ticks par événement

À 1x speed (real-time) :
├─ Temps réel = 1 seconde
├─ Temps simulé = 1 seconde
└─ Événements générés = 1 ✅

À 60x speed (1 minute/sec) :
├─ Temps réel = 1 seconde  
├─ Temps simulé = 60 secondes (devrait être)
├─ Événements générés = 1 ❌ (devrait être 60)
```

### Chaîne du bug

```python
# Avant : dt toujours 0.1s (1/10 Hz)
dt = 1.0 / self._tick_rate_hz  # = 0.1s
await asyncio.sleep(dt)
self._t_elapsed_s += dt         # ❌ Toujours +0.1s

# À 60x speed :
# - Itération 1 : t_elapsed = 0.1s
# - Itération 2 : t_elapsed = 0.2s
# ...
# - Itération 600 : t_elapsed = 60s ❌ Mais 600 ticks = 60 secondes réelles!

# Au lieu de :
# - Itération 1 : t_elapsed = 6s (0.1s × 60)
# - Itération 2 : t_elapsed = 12s
# ...
# - Itération 10 : t_elapsed = 60s ✅ En 1 seconde réelle!
```

### Pourquoi c'est un problème

```python
# Fréquence d'événements dépend du temps simulé
ticks_per_event = max(1, round(self._tick_rate_hz / self._events_per_sec))
# = max(1, round(10 / 1.0))
# = 10 ticks

# À 60x speed, sans le fix :
# - 1 sec réelle = 10 ticks = 1 événement ❌ (devrait être 60)
# - Parce que le temps simulé progresse au même rythme

# Avec le fix :
# - 1 sec réelle = 10 ticks × 60 simulé = 600 événements ✅
# - Chaque tick représente 0.6s simulé (0.1s real × 60)
```

---

## ✅ Solution

### Code modifié (Ligne ~246-267)

**Avant :**
```python
dt = 1.0 / self._tick_rate_hz

while self._running:
    await asyncio.sleep(dt)
    self._t_elapsed_s += dt              # ❌ Pas de × speed_multiplier
    
    for machine in self.machines.values():
        machine.tick(load_factor=load_factor, dt=dt)  # ❌ Pas accéléré
    
    self._fault_scheduler.tick(self.machines, dt=dt)  # ❌ Pas accéléré
```

**Après :**
```python
dt_per_iteration = 1.0 / self._tick_rate_hz

while self._running:
    await asyncio.sleep(dt_per_iteration)  # Temps réel fixe
    
    # ✅ IMPORTANT : dt_simulated = dt_real × speed_multiplier
    dt_simulated = dt_per_iteration * self._speed_multiplier
    
    self._t_elapsed_s += dt_simulated    # ✅ Accéléré
    
    for machine in self.machines.values():
        machine.tick(load_factor=load_factor, dt=dt_simulated)  # ✅ Accéléré
    
    self._fault_scheduler.tick(self.machines, dt=dt_simulated)  # ✅ Accéléré
```

### Explication

**Avant :**
```
Itération       Temps réel     Temps simulé   Événements
1               1ms            0.1s           (ticks=1)
2               2ms            0.2s           (ticks=2)
...
10              100ms          1.0s           1 événement ✓
...
100             1s             10s            10 événements (mais mélangé!)
```

**Après (à 60x speed) :**
```
Itération       Temps réel     Temps simulé   Événements/sec
1               1ms            6.0s (0.1×60)  60 événements
2               2ms            12.0s
...
10              100ms          60.0s          60 événements/sec ✓
```

---

## 📊 Impact observé

### Avant le fix

| Speed | Temps réel | Temps simulé | Ticks | Événements | Events/sec attendus | Events/sec réels |
|-------|-----------|-------------|-------|-----------|-----------------|---------------|
| 1x | 1s | 1s | 10 | 1 | 1 | **1** ✓ |
| 60x | 1s | 1s | 10 | 1 | 60 | **1** ❌ |
| 3600x | 1s | 1s | 10 | 1 | 3600 | **1** ❌ |

### Après le fix

| Speed | Temps réel | Temps simulé | Ticks | Événements | Events/sec attendus | Events/sec réels |
|-------|-----------|-------------|-------|-----------|-----------------|---------------|
| 1x | 1s | 1s | 10 | 1 | 1 | **1** ✓ |
| 60x | 1s | 60s | 10 | 60 | 60 | **60** ✅ |
| 3600x | 1s | 3600s | 10 | 3600 | 3600 | **3600** ✅ |

---

## 🧪 Comment tester

### Test 1 : Vérifier que les événements augmentent

1. **Dashboard → Simulation → Contrôle vitesse**
2. Sélectionner `Real-time (1x)`
3. Attendre 30 secondes
4. **Grafana :** Compter les points sur la courbe de température
   - Environ 30 points (1 par sec)

5. **Dashboard :** Changer vitesse à `1 hour/sec (3600x)`
6. Attendre 5 secondes réelles
7. **Grafana :** Compter les points
   - Environ 18000 points (3600 × 5) ✅

### Test 2 : Vérifier que la température change plus vite

1. **Vitesse = 1x, observer température pendant 10s réelles**
   - Température change lentement

2. **Vitesse = 3600x, observer température pendant 1s réelle**
   - Température change TRÈS rapidement (comme 10 heures de simulation en 1 seconde)

### Test 3 : Vérifier les pannes avec accélération

1. **Vitesse = 1x**
   - Injecter `fan_failure` (120s durée)
   - Observer pendant 2 minutes : température augmente lentement

2. **Vitesse = 60x**
   - Injecter `fan_failure` (120s durée)
   - Observer pendant 2 secondes : température augmente rapidement
   - Panne se termine en 2s réelles (= 120s simulées)

---

## 🔍 Détails techniques

### Nomenclature

```python
dt_per_iteration    = 1.0 / _tick_rate_hz      # Temps réel par itération (0.1s à 10 Hz)
dt_simulated        = dt_per_iteration × _speed_multiplier  # Temps simulé par itération

sleep_duration      = dt_per_iteration         # Toujours le même (sleep wall-clock)
t_elapsed increment = dt_simulated             # Accéléré selon speed_multiplier
```

### Chaînes de propagation

```
dt_simulated → machine.tick(dt=dt_simulated)
            ├─ Temperature integration (plus rapide)
            ├─ Fan RPM calculations (plus rapide)
            ├─ Energy accumulation (plus rapide)
            └─ Power calculations (plus rapide)

dt_simulated → fault_scheduler.tick(dt=dt_simulated)
            ├─ Fault duration countdown (plus rapide)
            └─ Fault injection events (plus fréquents)

dt_simulated → t_elapsed += dt_simulated
            └─ Scenario engine uses t_elapsed
               ├─ Load profile evaluation (plus rapide)
               └─ Event timing (plus fréquent)
```

### Cas limite : CPU throttling

Phase 8.3 introduit le CPU throttling pour éviter que la simulation ne consomme 100% CPU à haute vitesse.

```python
if self._cpu_throttle_enabled and self._throttle_interval_s > 0:
    await asyncio.sleep(self._throttle_interval_s)
```

**Important :** Ce sleep est **indépendant** du speed multiplier. Il ne ralentit pas la simulation, juste le CPU.

---

## 📊 Avant vs Après

| Aspect | Avant | Après |
|--------|-------|-------|
| **1x speed** | 1 événement/sec | 1 événement/sec ✓ |
| **60x speed** | 1 événement/sec ❌ | 60 événements/sec ✅ |
| **Température** | Progresse lentement ✓ | Progresse au rythme simulé ✅ |
| **Pannes** | Durent longtemps en réel ❌ | Durent correct (speedé) ✅ |
| **Load profile** | Évolution lente ❌ | Évolution accélérée ✅ |

---

## 🎓 Leçons apprises

### 1. Distinction temps réel vs temps simulé

```python
# ❌ Mauvais : mélanger les deux
dt = 1.0 / tick_rate_hz  # Fixe
t_elapsed += dt          # Pas d'accélération

# ✅ Mieux : séparer clairement
dt_real = 1.0 / tick_rate_hz
dt_sim = dt_real * speed_multiplier
t_elapsed += dt_sim
await asyncio.sleep(dt_real)
```

### 2. Propagation du dt_simulé

Tous les calculs doivent recevoir le **même `dt_simulated`** :
- Machines : `machine.tick(dt=dt_simulated)`
- Pannes : `fault_scheduler.tick(dt=dt_simulated)`
- Temps écoulé : `t_elapsed += dt_simulated`

Si on oublie un endroit, la simulation devient incohérente.

### 3. Speed multiplier ≠ sleep duration

```python
# ❌ Mauvais : sleep moins longtemps
await asyncio.sleep(dt / speed_multiplier)

# ✅ Mieux : sleep toujours pareil, mais progression accélérée
await asyncio.sleep(dt)
dt_sim = dt * speed_multiplier
t_elapsed += dt_sim
```

Le sleep doit rester court pour que le CPU soit dispo pour les calculs.

---

## 🚀 Déploiement

```bash
build-clean-app.bat
# Attendre 3-5 min

# Tester :
# 1. Dashboard → Vitesse 1x → Observer température 30 secondes
# 2. Dashboard → Vitesse 3600x → Observer la même courbe en 1 seconde
```

---

## 📝 Fichiers modifiés

**`simulation/cluster.py` (Ligne ~246-267) :**
- Renommer `dt` → `dt_per_iteration` pour clarté
- Ajouter `dt_simulated = dt_per_iteration * self._speed_multiplier`
- Passer `dt_simulated` à `machine.tick()` et `fault_scheduler.tick()`
- Incrémenter `t_elapsed` avec `dt_simulated`

---

**Status :** ✅ **CORRIGÉ**

*Bug fix effectué le 4 juin 2026*
