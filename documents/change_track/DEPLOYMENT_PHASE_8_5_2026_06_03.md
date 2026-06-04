# Guide de déploiement — Phase 8.5

**Date :** 3 juin 2026  
**Version :** Phase 8.5 (Configuration éditable)  
**Durée estimée :** 5-10 minutes

---

## 📋 Checklist pre-déploiement

- [x] Tous les changements implémentés
- [x] Tests ajoutés et vérifiés
- [x] Documentation complète
- [x] Dépendances (asyncpg) ajoutées à requirements.txt

---

## 🚀 Étapes de déploiement

### Étape 1 : Build Docker complet

Depuis le dossier racine du projet :

```bash
# Option A : Script Windows
build-clean-app.bat

# Option B : Docker compose manuel
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

**Ce que cela fait :**
- Télécharge asyncpg (nouvelle dépendance)
- Recompile API, Dashboard, Consumer
- Redémarre tous les services
- Crée volumes TimescaleDB frais (si spécifié)

**Temps :** ~3-5 minutes (dépend du cache Docker)

---

### Étape 2 : Vérifier services au démarrage

Une fois Docker up, vérifier les logs :

```bash
# Vérifier API
docker logs jumeaux-chauds-api-1 | grep "Uvicorn"
# Doit afficher : "Uvicorn running on http://0.0.0.0:8000"

# Vérifier Dashboard
docker logs jumeaux-chauds-dashboard-1 | grep "Streamlit"
# Doit afficher : "You can now view your Streamlit app in your browser"

# Vérifier consumer (si profil storage)
docker logs jumeaux-chauds-consumer-1 | grep "Consumer"
```

---

### Étape 3 : Tester endpoints API

```bash
# Health check
curl http://localhost:8000/docs
# Ouvre Swagger UI — vérifier endpoints visibles

# Test GET start_time
curl http://localhost:8000/simulation/config/start_time
# Retourne :
# {
#   "start_time_iso": "2005-01-01T00:00:00Z",
#   "start_time_unix": 1104537600.0,
#   "start_time_readable": "2005-01-01 00:00:00 UTC",
#   "description": "..."
# }

# Test PUT start_time
curl -X PUT http://localhost:8000/simulation/config/start_time \
  -H "Content-Type: application/json" \
  -d '{"start_time_iso": "2010-06-15T12:30:45Z"}'
# Retourne :
# {
#   "ok": true,
#   "message": "Date de départ changée : 2005-01-01 00:00:00 UTC → 2010-06-15 12:30:45 UTC ..."
# }

# Test GET speed
curl http://localhost:8000/simulation/speed
# Retourne dict avec vitesse actuelle

# Test POST reset complet
curl -X POST http://localhost:8000/simulation/reset
# Retourne :
# {
#   "ok": true,
#   "message": "Reset complet effectué : ..."
# }
```

---

### Étape 4 : Tester Dashboard Streamlit

Accéder à : http://localhost:8501

**Onglet "Simulation" doit afficher :**

1. **⚙️ Contrôle de vitesse de simulation** (inchangé)
   - Dropdown vitesse
   - Bouton "✓ Appliquer vitesse"
   - Affichage vitesse courante

2. **📅 Configuration date de départ** (NOUVEAU)
   - Affiche date actuelle : "Date actuelle : 2005-01-01 00:00:00 UTC"
   - Date picker pour sélectionner nouvelle date
   - Bouton "✓ Appliquer date"

3. **Bouton Reset** (MODIFIÉ)
   - Ancien texte : "🔄 Reset temps"
   - Nouveau texte : "🗑️ Reset complet"
   - Comportement : appelle POST /simulation/reset (au lieu de /speed/reset)

---

### Étape 5 : Exécuter tests unitaires

```bash
# Tests Phase 8.4 (start_time)
pytest tests/test_simulated_time.py::TestStartTimeConfiguration -v
pytest tests/test_simulated_time.py::TestStartTimeProtection -v
pytest tests/test_simulated_time.py::TestScenarioChaining -v

# Tests Phase 8.5 (speed_multiplier) — NOUVEAUX
pytest tests/test_simulated_time.py::TestSpeedMultiplierProtection -v

# Tests Phase 8.5 (start_time modifiable) — NOUVEAUX
pytest tests/test_simulated_time.py::TestStartTimeModification -v

# Tous les tests
pytest tests/test_simulated_time.py -v
# Attendu : 23 tests passing
```

---

## 🔍 Tests fonctionnels manuels

### Test 1 : Changer date sans reset temps écoulé

```
1. Naviguer à http://localhost:8501
2. Onglet "Simulation"
3. Lancer simulation pendant 10 secondes (observe temps écoulé)
4. Onglet "Simulation" → Date picker → sélectionner 2020-06-15
5. Cliquer "✓ Appliquer date"
6. Dashboard refresh
7. Vérifier : timestamp dans snapshot commence maintenant par 2020
8. Vérifier : temps écoulé INCHANGÉ (toujours ~10 secondes)
```

**Validation :**
- [ ] API retourne start_time_readable = "2020-06-15 00:00:00 UTC"
- [ ] get_snapshot()["ts"] commence par "2020-06-15"
- [ ] get_snapshot()["t_elapsed_s"] ≈ 10.0 (inchangé)

---

### Test 2 : Speed global + reset complet

```
1. Onglet "Simulation"
2. Dropdown vitesse → "1 hour/sec (3600x)"
3. Cliquer "✓ Appliquer vitesse"
4. Observer : elapsed_time_s augmente rapidement
5. Attendre 5 secondes (= 5 heures simulées)
6. Cliquer "🗑️ Reset complet"
7. Vérifier message : "Reset complet effectué..."
8. Vérifier elapsed_time_s = 0
9. Vérifier TimescaleDB vidée (si data disponible)
```

**Validation :**
- [ ] Speed change immédiat (prochain tick)
- [ ] Reset retourne message détaillé
- [ ] elapsed_time_s revient à 0
- [ ] energy_kwh_total revient à 0

---

### Test 3 : Scénario → speed persiste → reset

```
1. Onglet "Simulation" → Scénario "nominal"
2. Changer speed à 60.0x
3. Onglet "Simulation" → Scénario "stress"
4. Cliquer "🔄 Changer de scénario"
5. Vérifier : speed toujours 60.0x (pas reset par changement scénario)
6. Cliquer "🗑️ Reset complet"
7. Vérifier : speed revient-il au défaut base.yaml (1.0x) ? ❌ NON
   (reset ne change pas speed, juste elapsed/energy)
```

**Validation :**
- [ ] Changement scénario ne reset pas speed
- [ ] Reset complet ne change pas speed (feature future possible)

---

## 🐛 Troubleshooting

### Symptôme : Bouton "🗑️ Reset complet" retourne erreur TimescaleDB

**Cause :** TimescaleDB non accessible (démarrage lent)

**Solution :**
```bash
# Option 1 : Vérifier TimescaleDB en cours d'exécution
docker ps | grep timescaledb
# Doit afficher : "timescaledb ... Up"

# Option 2 : Attendre quelques secondes (startup time)
sleep 5
# Puis réessayer

# Option 3 : Vérifier logs TimescaleDB
docker logs jumeaux-chauds-timescaledb-1
# Chercher "ready to accept"
```

**Fallback :** Reset soft (temps + énergie) réussit même si TimescaleDB échoue.
Log affiche l'erreur mais le soft reset persiste.

---

### Symptôme : Date picker dans Streamlit ne fonctionne pas

**Cause :** Streamlit cache (version ancienne)

**Solution :**
```bash
# Forcer refresh Streamlit
docker restart jumeaux-chauds-dashboard-1

# Ou via UI Streamlit
# Bouton "⋮" (menu) → "Clear cache" → Rerun
```

---

### Symptôme : API retourne 422 Unprocessable Entity sur PUT start_time

**Cause :** Format date incorrect

**Solution :**
```bash
# Vérifier format ISO 8601 :
# ✅ "2005-01-01T00:00:00Z"
# ✅ "2010-06-15T12:30:45Z"
# ❌ "2005-01-01"  (pas de time)
# ❌ "01/01/2005"  (format US)

# Corriger la requête :
curl -X PUT http://localhost:8000/simulation/config/start_time \
  -H "Content-Type: application/json" \
  -d '{"start_time_iso": "2010-06-15T12:30:45Z"}'
```

---

## 📊 Vérifications post-déploiement

### Configuration YAML

```bash
# Vérifier speed_multiplier en base.yaml
grep -A 10 "^simulation:" config/base.yaml
# Doit contenir : speed_multiplier: 1.0

# Vérifier pas de speed_multiplier en scénarios
grep "speed_multiplier" config/scenarios/*.yaml
# Doit retourner RIEN

# Vérifier start_time en base.yaml
grep "start_time:" config/base.yaml
# Doit retourner : start_time: "2005-01-01T00:00:00Z"
```

---

### Code

```bash
# Vérifier imports asyncpg dans cluster.py
grep "asyncpg" simulation/cluster.py
# Doit afficher : import asyncpg

# Vérifier endpoints API
grep "POST.*reset" api/routes/simulation.py
# Doit montrer 2 endpoints : /speed/reset, /reset

# Vérifier UI dashboard
grep "Reset complet" dashboard/app.py
# Doit afficher : 🗑️ Reset complet

# Vérifier date picker UI
grep "start_date_input" dashboard/app.py
# Doit afficher : st.date_input (date picker)
```

---

### Tests

```bash
# Exécuter tous les tests de temps simulé
pytest tests/test_simulated_time.py -v --tb=short
# Attendu : 23 passed

# Filtrer par classe pour debug
pytest tests/test_simulated_time.py::TestSpeedMultiplierProtection -v
pytest tests/test_simulated_time.py::TestStartTimeModification -v
```

---

## 🔐 Sécurité

### ⚠️ Points d'attention

1. **Reset TimescaleDB destructif**
   - ✅ Pas de confirmation stricte (sera ajoutée en Phase 8.6)
   - ❌ Possible depuis dashboard sans auth
   - 📌 Recommendation : ajouter authentification

2. **Modification start_time sans audit**
   - ✅ Modifiable depuis dashboard
   - ❌ Pas de logging d'audit
   - 📌 Recommendation : ajouter audit trail dans logs

3. **Asyncpg credentials non chiffrées**
   - ✅ Défaut localhost (safe en dev)
   - ❌ Password possible en clair si ENV var
   - 📌 Recommendation : utiliser .env sécurisé en prod

---

## 📝 Migration depuis Phase 8.4

**Si vous avez Phase 8.4 en prod :**

1. Backup TimescaleDB (optionnel mais recommandé)
   ```bash
   docker exec timescaledb pg_dump -U jumeaux jumeaux > backup_2026_06_03.sql
   ```

2. Backup config (optionnel)
   ```bash
   cp -r config config.backup_2026_06_03
   ```

3. Exécuter build Phase 8.5
   ```bash
   build-clean-app.bat
   ```

4. Tester endpoints (voir "Tester endpoints API" ci-dessus)

5. Migration données : **Aucune migration requise**
   - TimescaleDB schema inchangé
   - Config YAML compatible (speed_multiplier optionnel)

---

## 🎯 Checklist de vérification finale

### Avant de considérer le déploiement complet

- [ ] `docker-compose ps` — Tous les services UP
- [ ] `curl http://localhost:8000/docs` — Swagger UI accessible
- [ ] `curl http://localhost:8501` — Dashboard accessible
- [ ] Endpoints API testés (curl GET/PUT /simulation/config/start_time)
- [ ] Endpoints reset testés (curl POST /simulation/reset)
- [ ] Dashboard UI affiche date picker + reset button
- [ ] Tests `pytest tests/test_simulated_time.py` — 23 passing
- [ ] Logs vérifiés (pas d'erreurs critiques)
- [ ] Configuration YAML vérifiée (speed_multiplier en base.yaml)

---

## 📞 Support

### Si quelque chose ne fonctionne pas

1. Vérifier logs Docker
   ```bash
   docker logs jumeaux-chauds-api-1
   docker logs jumeaux-chauds-dashboard-1
   ```

2. Vérifier Swagger API docs
   ```
   http://localhost:8000/docs
   ```

3. Rechercher endpoint dans le code
   ```bash
   grep -r "config/start_time" api/
   grep -r "/reset" api/
   ```

4. Exécuter test spécifique
   ```bash
   pytest tests/test_simulated_time.py::TestStartTimeModification::test_change_start_time_preserves_elapsed -vv
   ```

---

## 📚 Documentation associée

- `CHANGELOG_PHASE_8_5_2026_06_03.md` — Détail complet des changements
- `IMPLEMENTATION_STATUS_2026_06_03.md` — État global (à mettre à jour)
- Swagger UI : http://localhost:8000/docs

---

**Durée estimée total :** 5-10 minutes (build + tests)

*Guide généré le 3 juin 2026*
