# Bug Fix — Injection de pannes sans effet sur le comportement des machines

**Date :** 4 juin 2026  
**Problème :** Les pannes injectées depuis le dashboard (fan_failure, sensor_drift, etc.) n'avaient aucun effet observable sur les machines.  
**Cause :** Seul le type `power_surge` était appliqué. Les autres pannes étaient stockées mais jamais utilisées.  
**Solution :** Implémenter le traitement complet des pannes dans `_integrate_thermal()`.  
**Status :** ✅ Corrigé

---

## 🐛 Problème analysé

### Symptôme
```
Dashboard → Injection panne (ex: fan_failure)
├─ Panne ajoutée avec succès ✅ (confirmée dans events)
├─ Mais : température = inchangée ❌
├─ Et : puissance = inchangée ❌
└─ Aucun impact observable sur la machine
```

### Cause identifiée
```python
# Avant : seul power_surge était traité
for fault in self.faults:
    if fault.fault_type == "power_surge":
        power_w *= 1.0 + fault.magnitude
    # ❌ Autres types (fan_failure, sensor_drift) : IGNORÉS
```

### Types de pannes définis

**Dans `config/scenarios/stress.yaml` :**
1. **`fan_failure`** (Weibull) → Ventilateurs arrêtés
2. **`sensor_drift`** (Exponentiel) → Capteur biaisé
3. **`power_surge`** (Uniforme) → Surconsommation électrique ✅ Déjà implémenté

---

## ✅ Solution

### Implémentation dans `simulation/machine.py`

#### 1. **`fan_failure` — Arrêt du refroidissement actif**

**Avant :**
```python
# Les fans restaient actifs même avec une panne
fan_rpm_mean = float(sum(fan_rpms) / len(fan_rpms)) if fan_rpms else 0.0
```

**Après :**
```python
fan_rpm_mean = float(sum(fan_rpms) / len(fan_rpms)) if fan_rpms else 0.0

# --- APPLICATION DES PANNES ---
for fault in self.faults:
    if fault.fault_type == "power_surge":
        power_w *= 1.0 + fault.magnitude
    elif fault.fault_type == "fan_failure":
        # ✅ Ventilateurs arrêtés → zéro refroidissement actif
        fan_rpm_mean = 0.0
```

**Effet :** 
- `fan_rpm_mean` devient 0 → Constante de temps `tau` augmente (moins de refroidissement)
- Température monte progressivement pendant la panne
- Puissance électrique inchangée

---

#### 2. **`sensor_drift` — Dérive de capteur (lecture biaisée)**

**Avant :**
```python
def snapshot(self) -> dict:
    return {
        "temperature_c": self.temperature_c,  # ❌ Toujours exacte
        ...
    }
```

**Après :**
```python
def snapshot(self) -> dict:
    # Calculer la température lue (avec dérive capteur si panne active)
    temperature_read = self.temperature_c
    for fault in self.faults:
        if fault.fault_type == "sensor_drift":
            # sensor_drift ajoute un décalage à la température lue
            # magnitude = décalage (ex: 0.5 → +5°C d'erreur)
            temperature_read += fault.magnitude * 10.0
    
    return {
        "temperature_c": temperature_read,  # ✅ Biaisée si panne active
        ...
    }
```

**Effet :**
- Température interne reste exacte dans la simulation
- Mais la **lecture capteur** affichée dans Grafana est biaisée
- Permet de tester des alertes basées sur des capteurs défaillants

---

## 📊 Comportements des pannes

### `fan_failure` (Défaillance des ventilateurs)

| Paramètre | Sans panne | Avec panne |
|-----------|-----------|-----------|
| **RPM ventilateurs** | Auto-régulé | 0 |
| **Refroidissement** | Actif (tau réduit) | Passif (tau élevé) |
| **Température** | Stabilisée | **Augmente rapidement** ↑ |
| **Puissance** | Inchangée | Inchangée |
| **Durée** | N/A | `recovery_delay_s` (120s par défaut) |

**Exemple :**
```
T(0s) = 45°C
fan_failure injectée
T(30s) = 65°C (sans ventilation)
T(60s) = 75°C
T(120s) = 45°C (panne terminée, refroidissement reprend)
```

### `sensor_drift` (Dérive de capteur)

| Paramètre | Sans panne | Avec panne |
|-----------|-----------|-----------|
| **Température réelle** | 45°C | 45°C (inchangée) |
| **Température lue** | 45°C | 45°C + (magnitude × 10) |
| **Grafana affiche** | 45°C | **Valeur biaisée** ⚠️ |
| **Puissance** | Inchangée | Inchangée |
| **Refroidissement** | Normal | Normal |

**Exemple (magnitude=0.5) :**
```
Température réelle = 45°C
sensor_drift injectée (magnitude=0.5)
Température lue dans Grafana = 45°C + 5°C = 50°C
→ Alerte déclenchée à tort
```

### `power_surge` (Surconsommation électrique)

| Paramètre | Sans panne | Avec panne |
|-----------|-----------|-----------|
| **Puissance** | 500W | **500W × (1 + magnitude)** |
| **Chaleur injectée** | Normale | **Augmentée** |
| **Température** | Stabilisée | **Augmente** ↑ |
| **Refroidissement** | Normal | Dépend des fans |
| **Durée** | N/A | `recovery_delay_s` |

**Exemple (magnitude=0.3) :**
```
Puissance = 500W
power_surge injectée (magnitude=0.3)
Puissance = 500W × 1.3 = 650W
Chaleur supplémentaire → Température augmente
```

---

## 🧪 Comment tester

### Test 1 : `fan_failure`

1. **Dashboard → Simulation → Onglet Machines**
2. Sélectionner une machine (ex: `srv-master-01`)
3. **Injecter panne :**
   - Type : `fan_failure`
   - Durée : `120` (secondes)
   - Magnitude : `1.0`
4. **Observer Grafana :**
   - Panneau "Température CPU par machine"
   - La courbe de `srv-master-01` doit **monter** progressivement
   - Apres 120s, elle redescend progressivement

**Logs API attendus :**
```
Panne 'fan_failure' injectée sur 'srv-master-01' (durée=120s, magnitude=1.0)
```

**Grafana attendu :**
```
T(0s) = 45°C ─────────┐
T(30s) = 62°C ─────── │ Panne active
T(60s) = 72°C ─────┐  │ (fan_rpm_mean = 0)
T(120s) = 68°C ────┼──┘ Panne terminée
T(180s) = 50°C ─────── Refroidissement reprend
```

---

### Test 2 : `sensor_drift`

1. **Dashboard → Simulation → Onglet Machines**
2. Sélectionner une machine
3. **Injecter panne :**
   - Type : `sensor_drift`
   - Durée : `60` (secondes)
   - Magnitude : `0.5`
4. **Observer Grafana :**
   - La température lue augmente de ~5°C (0.5 × 10)
   - Mais la puissance et le ventilateur restent normaux
   - Après 60s, la température revient à la normale

**Grafana attendu :**
```
Température réelle = 45°C ───────────────────
Température lue    = 45°C ─┐                  
(avec panne)       = 50°C ─┼─ Panne active
                   = 50°C ─┘
(après panne)      = 45°C ─── Revient normal
```

---

### Test 3 : `power_surge`

1. **Dashboard → Simulation → Onglet Machines**
2. Sélectionner une machine
3. **Injecter panne :**
   - Type : `power_surge`
   - Durée : `120`
   - Magnitude : `0.3`
4. **Observer Grafana :**
   - Panneau "Puissance totale du cluster"
   - La puissance augmente de 30%
   - Panneau "Température CPU"
   - La température augmente (chaleur supplémentaire)

**Logs API attendus :**
```
Panne 'power_surge' injectée sur 'srv-worker-01' (durée=120s, magnitude=0.3)
```

**Grafana attendu :**
```
Puissance = 500W ─────────┐
Puissance = 650W (1.3×) ──┼─ Panne active
Puissance = 500W ─────────┘
                          Panne terminée

Température = 45°C ──────┐
Température = 62°C ──────┼─ Panne active
Température = 50°C ──────┘
(refroidit lentement)
```

---

## 🔍 Détails d'implémentation

### Où les pannes sont appliquées

```
machine.tick(load_factor, dt)
  ├─ Mise à jour durées restantes des pannes
  ├─ Machine ON/OFF check
  └─ _integrate_thermal()
      ├─ Calcul fan RPM auto
      ├─ Calcul puissance base
      ├─ ✅ APPLICATION DES PANNES ← ICI
      │   ├─ power_surge : multiplier power_w
      │   └─ fan_failure : mettre fan_rpm_mean = 0
      ├─ Calcul constante de temps tau (dépend fan_rpm_mean)
      ├─ Intégration température
      └─ snapshot() ← sensor_drift appliquée à la lecture
```

### Fichiers modifiés

**`simulation/machine.py` (2 changements) :**

1. **Lignes ~294-300** : Ajout boucle application pannes dans `_integrate_thermal()`
   ```python
   for fault in self.faults:
       if fault.fault_type == "power_surge":
           power_w *= 1.0 + fault.magnitude
       elif fault.fault_type == "fan_failure":
           fan_rpm_mean = 0.0
   ```

2. **Lignes ~352-365** : Ajout sensor_drift dans `snapshot()`
   ```python
   temperature_read = self.temperature_c
   for fault in self.faults:
       if fault.fault_type == "sensor_drift":
           temperature_read += fault.magnitude * 10.0
   ```

---

## 📊 Avant vs Après

| Aspect | Avant | Après |
|--------|-------|-------|
| **fan_failure effet** | ❌ Aucun | ✅ Température augmente |
| **sensor_drift effet** | ❌ Aucun | ✅ Lecture biaisée |
| **power_surge effet** | ✅ Température augmente | ✅ Toujours fonctionnel |
| **Pannes visibles Grafana** | ✅ Enregistrées | ✅ Visibles + impactantes |
| **Impact observable** | ❌ Non | ✅ Oui |

---

## 🚀 Déploiement

```bash
build-clean-app.bat
# Attendre 3-5 min

# Tester chaque type de panne :
# 1. Dashboard → Simulation → Machines
# 2. Injecter fan_failure → Observer température augmente
# 3. Injecter sensor_drift → Observer température biaisée
# 4. Injecter power_surge → Observer puissance augmente + température augmente
```

---

## ✨ Leçons apprises

### 1. Pannes partiellement implémentées
```python
# ❌ Mauvais : traiter seulement un type
if fault_type == "power_surge":
    apply_power_surge()

# ✅ Mieux : boucle complète avec tous les types
for fault in self.faults:
    if fault.fault_type == "power_surge":
        apply_power_surge()
    elif fault.fault_type == "fan_failure":
        apply_fan_failure()
    elif fault.fault_type == "sensor_drift":
        apply_sensor_drift()
```

### 2. Pannes au bon endroit
- **Pannes thermiques** (fan_failure, power_surge) : dans `_integrate_thermal()` avant calcul tau
- **Pannes capteurs** (sensor_drift) : dans `snapshot()` pour affecter les lectures

### 3. Magnitude amplifiée pour sensor_drift
```python
# magnitude × 10 pour rendre l'effet observable
# Ex: magnitude=0.5 → +5°C d'erreur (significatif)
temperature_read += fault.magnitude * 10.0
```

---

## 🎓 Pourquoi c'est important

**Cas d'usage réels :**
1. **Test résilience des alertes** : Injecter sensor_drift pour tester fausses alertes
2. **Analyse impact pannes** : Comparer température avec/sans ventilation
3. **Validation monitoring** : Vérifier que Grafana capture correctement les pannes
4. **Formation** : Montrer aux étudiants effet réel des pannes matérielles

**Avant la fix :**
- Pannes enregistrées mais invisibles → confusing
- Students voient erreurs sans comprendre l'impact

**Après la fix :**
- Pannes enregistrées ET visibles dans les données
- Impact observable immédiatement dans Grafana

---

**Status :** ✅ **CORRIGÉ ET TESTABLE**

*Bug fix effectué le 4 juin 2026*
