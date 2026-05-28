# Change Track — Index des documents de suivi

> **Dossier :** `documents/change_track/`  
> **Objectif :** Centraliser tous les documents de suivi, d'analyse et de progression du projet par phase
> **Fréquence :** Mis à jour après chaque phase majeure de développement

---

## 📋 Fichiers de suivi par phase

### Phase 7 — Tests unitaires et intégration

| Fichier | Contenu | Statut |
|---------|---------|--------|
| **PHASE_7_SUMMARY.md** | Résumé exécutif de Phase 7.1 (couverture, tests écrits, métriques) | ✅ Phase 7.1 |
| **ANALYSE_EXHAUSTIVE.md** | Audit complet : alignement README/roadmap, variables YAML, problèmes de nommage | ✅ Phase 7.1 |
| **INDEX_ANALYSIS.md** | Guide de navigation dans les documents d'analyse Phase 7.1 | ✅ Phase 7.1 |
| **DELIVERABLE_PHASE_7.md** | Livrable formel : avant/après, checklists, certification Phase 7.1 | ✅ Phase 7.1 |
| **PHASE_7_2_COMPLETION.md** | Corrections du modèle physique : RPM³, tau(RPM), noise application, protocol_version suppression | ✅ Phase 7.2 |
| **PHASE_7_3_COMPLETION.md** | Tests API FastAPI : 23 tests, 10 endpoints REST, WebSocket, format validation | ✅ Phase 7.3 |
| **PHASE_7_4_COMPLETION.md** | Tests MQTT e2e : 18 tests, 8 topics, publisher config, payload structure, integration | ✅ Phase 7.4 |
| **PHASE_7_5_COMPLETION.md** | Tests TimescaleDB consumer : 28 tests, topic parsing, payload validation, data transformation, dispatch | ✅ Phase 7.5 |

---

## 🔍 Structure des documents

### PHASE_7_SUMMARY.md
- Métriques avant/après Phase 7.1
- Coverage par module
- Résumé des 155 tests écrits
- Problèmes identifiés et actions recommandées

### ANALYSE_EXHAUSTIVE.md
- Audit complet du dépôt
- Vérification alignement README ↔ roadmap ↔ code
- Table des problèmes de nommage YAML (3 variables non exploitées)
- Solutions et priorités
- Coûts d'implémentation estimés

### INDEX_ANALYSIS.md
- Navigation rapide dans tous les documents Phase 7
- Vue d'ensemble des findings
- Liens vers sections spécifiques

### DELIVERABLE_PHASE_7.md
- Avant/Après : état du dépôt
- Checklists de validation
- Certification Phase 7.1 complète
- Signatures et approbations

### PHASE_7_2_COMPLETION.md
- Problèmes corrigés (4 variables + 1 modèle physique)
- Code changes détaillés par fichier
- Tests Phase 7.2 (8+)
- Impacts et comportements
- Prochaines étapes

---

## 📍 Documents de référence (restent dans `documents/`)

Ces fichiers **ne sont pas** dans `change_track` car ils sont des documents de référence stables :

| Fichier | Rôle |
|---------|------|
| **roadmap.md** | Feuille de route complète des phases (tâches, critères, statuts) |
| **specifications.md** | Spécifications techniques détaillées |
| **worklog.md** | Journal d'implémentation détaillé |

---

## 📄 Documents à la racine

| Fichier | Rôle |
|---------|------|
| **README.md** | Documentation principale du projet |

---

## 📚 Comment utiliser ce dossier

**Après une phase majeure :**
1. Créer un nouveau document de synthèse (ex. `PHASE_8_COMPLETION.md`)
2. L'ajouter à ce INDEX avec son statut
3. Garder les fichiers antérieurs pour historique

**Pour trouver une information spécifique :**
- Commencer par ce fichier (INDEX.md)
- Consulter PHASE_*_SUMMARY.md pour vue rapide
- Aller à ANALYSE_EXHAUSTIVE.md pour détails profonds
- Vérifier DELIVERABLE_*.md pour certification

**Pour mettre à jour la structure :**
- Respecter le naming : `PHASE_X_*.md` ou `ANALYSE_*.md`
- Ajouter entrée à ce INDEX
- Mettre à jour statuts des phases

---

## 🗂️ Historique des phases

```
Phase 1-6 : Fondations + Simulation + MQTT + API + Dashboard + Docker
Phase 7.1 : Tests unitaires consolidés (155 tests, 85% couverture) ✅
Phase 7.2 : Corrections modèle physique (RPM³, tau, noise) ✅
Phase 7.3 : Tests API FastAPI (23 tests, 10 endpoints) ✅
Phase 7.4 : Tests MQTT e2e (18 tests, 8 topics) ✅
Phase 7.5 : Tests TimescaleDB consumer (28 tests, pipeline complet) ✅
Phase 8   : Extensions pédagogiques 🔜
```

---

**Dernière mise à jour :** 28 mai 2026  
**Auteur :** Tristan Vanrullen  
**Mainteneur :** Système de documentation automatisée
