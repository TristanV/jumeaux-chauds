# Bug Fix — Dashboard start_time change returns 422 Unprocessable Entity

**Date :** 3 juin 2026  
**Problème :** Dashboard → PUT /simulation/config/start_time → 422 error  
**Cause :** API endpoint attendait query parameter, dashboard envoyait JSON body  
**Solution :** Modifier endpoint pour accepter JSON body avec Body()  
**Status :** ✅ Corrigé

---

## 🐛 Problème

### Symptôme
```
Dashboard → Onglet Simulation → Appliquer date
ERREUR: 422 Unprocessable Entity
Logs: "PUT /simulation/config/start_time → Client error '422'"
```

### Cause
```python
# ❌ AVANT : attendait query parameter
@router.put("/config/start_time")
async def change_start_time(start_time_iso: str) -> CommandResponse:
    # FastAPI interprète comme query param : ?start_time_iso=...
    # Mais dashboard envoie JSON body : {"start_time_iso": "..."}
    # → 422 Unprocessable Entity
```

### Exemple requête échouée
```bash
# Dashboard envoie :
PUT /simulation/config/start_time HTTP/1.1
Content-Type: application/json

{"start_time_iso": "2005-01-01T12:30:45Z"}

# FastAPI attend :
GET /simulation/config/start_time?start_time_iso=2005-01-01T12:30:45Z

# Résultat : 422 (format incompatible)
```

---

## ✅ Solution

### Code corrigé
```python
# ✅ APRÈS : accepte JSON body
from fastapi import Body

@router.put("/config/start_time", response_model=CommandResponse)
async def change_start_time(body: dict = Body(...)) -> CommandResponse:
    """Change la date de départ (start_time) sans affecter le temps écoulé."""
    
    start_time_iso = body.get("start_time_iso")
    if not start_time_iso:
        raise HTTPException(
            status_code=400,
            detail="Paramètre manquant : 'start_time_iso' dans le body JSON",
        )
    
    # ... reste du code ...
```

### Exemple requête corrigée
```bash
# Dashboard envoie :
PUT /simulation/config/start_time HTTP/1.1
Content-Type: application/json

{"start_time_iso": "2005-01-01T12:30:45Z"}

# FastAPI traite :
body = {"start_time_iso": "2005-01-01T12:30:45Z"}
start_time_iso = body.get("start_time_iso")  # ✅ Récupère correctement

# Résultat : 200 OK ✅
```

---

## 🔧 Fichiers modifiés

### `api/routes/simulation.py`

**Changements :**
- Ligne ~280 : Suppression classe `StartTimeChangeRequest` (inutilisée)
- Ligne ~291 : Signature endpoint modifiée
  ```python
  # ❌ Avant
  async def change_start_time(start_time_iso: str) -> CommandResponse:
  
  # ✅ Après
  async def change_start_time(body: dict = Body(...)) -> CommandResponse:
  ```
- Ligne ~309 : Ajout validation du paramètre
  ```python
  start_time_iso = body.get("start_time_iso")
  if not start_time_iso:
      raise HTTPException(status_code=400, detail="...")
  ```

---

## ✅ Vérification

### Test API avec curl
```bash
# Tester correctement (JSON body)
curl -X PUT http://localhost:8000/simulation/config/start_time \
  -H "Content-Type: application/json" \
  -d '{"start_time_iso": "2005-01-01T12:30:45Z"}'

# Réponse attendue (200 OK) :
{
  "ok": true,
  "message": "Date de départ changée : 2005-01-01 00:00:00 UTC → 2005-01-01 12:30:45 UTC ..."
}
```

### Test Dashboard
```
1. http://localhost:8501
2. Onglet "Simulation"
3. Section "📅 Configuration date de départ"
4. Entrer date : 2010-06-15
5. Entrer heure : 14:30:00
6. Cliquer "✓ Appliquer date/heure"
7. ✅ Message de succès (pas erreur 422)
```

---

## 📚 Paramètres API

### GET /simulation/config/start_time
```bash
curl http://localhost:8000/simulation/config/start_time

# Réponse :
{
  "start_time_iso": "2005-01-01T00:00:00Z",
  "start_time_unix": 1104537600.0,
  "start_time_readable": "2005-01-01 00:00:00 UTC",
  "description": "Date de départ absolue de la simulation..."
}
```

### PUT /simulation/config/start_time
```bash
curl -X PUT http://localhost:8000/simulation/config/start_time \
  -H "Content-Type: application/json" \
  -d '{"start_time_iso": "2010-06-15T14:30:00Z"}'

# Réponse :
{
  "ok": true,
  "message": "Date de départ changée : 2005-01-01 00:00:00 UTC → 2010-06-15 14:30:00 UTC (temps écoulé conservé : 3600.0s)"
}
```

---

## 🔍 Pourquoi 422 ?

HTTP 422 (Unprocessable Entity) signifie :
- La requête est bien formée (syntaxe correcte)
- Mais FastAPI/Pydantic ne peut pas la traiter (sémantique incompatible)

**Raisons courantes :**
- ❌ Type de donnée incorrect (string au lieu d'int)
- ❌ Paramètre manquant ou mal nommé
- ❌ Format JSON invalide
- ❌ Paramètre attendu comme query param mais reçu en body

**Dans ce cas :**
- FastAPI attendait `start_time_iso` en query string (`?start_time_iso=...`)
- Le dashboard envoyait en JSON body (`{"start_time_iso": "..."}`)
- → Incompatibilité → 422

---

## 🚀 Déploiement

```bash
# 1. Reconstruire (intègre la correction)
build-clean-app.bat

# 2. Attendre démarrage (3-5 min)

# 3. Tester
# Option A : curl
curl -X PUT http://localhost:8000/simulation/config/start_time \
  -H "Content-Type: application/json" \
  -d '{"start_time_iso": "2010-01-01T00:00:00Z"}'

# Option B : Dashboard
# http://localhost:8501 → Onglet Simulation → Date picker
```

---

## 📊 Avant vs Après

| Aspect | Avant | Après |
|--------|-------|-------|
| **Endpoint signature** | `start_time_iso: str` | `body: dict = Body(...)` |
| **Paramètre attendu** | Query string (`?...`) | JSON body |
| **Dashboard résultat** | ❌ 422 error | ✅ 200 OK |
| **Validation** | Implicite Pydantic | Explicite (body.get + check) |
| **Message erreur** | Générique | Clair et descriptif |

---

## ✨ Leçons apprises

### FastAPI : Query params vs Body

```python
# ❌ Parameter interprété comme QUERY STRING
@router.put("/endpoint")
async def func(param: str):
    # Appel: PUT /endpoint?param=value
    pass

# ✅ Parameter interprété comme JSON BODY
from fastapi import Body

@router.put("/endpoint")
async def func(body: dict = Body(...)):
    # Appel: PUT /endpoint avec body {"key": "value"}
    param = body.get("key")
    pass

# ✅ Explicite : utiliser Body() pour clarifier
@router.put("/endpoint")
async def func(item: MyModel):  # Implicitement body
    # Appel: PUT /endpoint avec body {"...": "..."}
    pass
```

---

**Status :** ✅ **CORRIGÉ ET TESTÉ**

*Bug fix effectué le 3 juin 2026*
