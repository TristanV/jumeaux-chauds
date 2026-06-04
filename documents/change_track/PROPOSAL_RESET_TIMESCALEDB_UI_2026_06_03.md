# Proposition : Reset complet TimescaleDB depuis Streamlit

**Date :** 3 juin 2026  
**Statut :** 📋 Proposition (non implémentée)  
**Audience :** Architectes / PM

---

## Situation actuelle

| Action | Accessible | Lieu |
|--------|-----------|------|
| Reset soft (temps + énergie sim) | ✅ OUI | Dashboard, onglet "Simulation" |
| Reset TimescaleDB (tables) | ❌ NON | Ligne de commande Docker uniquement |

**Problème :** Utilisateur doit quitter Streamlit et utiliser le terminal pour reset complet

---

## Solution proposée

### Option A : Reset TimescaleDB via API (RECOMMANDÉE)

#### 1. Nouveau endpoint API

**Fichier :** `api/routes/simulation.py` (après `reset_time_and_energy`)

```python
@router.post("/reset/timescaledb", response_model=CommandResponse)
async def reset_timescaledb() -> CommandResponse:
    """Vide les tables TimescaleDB (telemetry et events).
    
    ⚠️ DESTRUCTIVE - Supprime tous les historiques.
    
    Returns:
        CommandResponse avec confirmation
    """
    import asyncpg
    from api.config import TIMESCALE_DSN  # À ajouter
    
    try:
        # Connecter à TimescaleDB
        conn = await asyncpg.connect(TIMESCALE_DSN)
        
        # Vider les tables (cascade)
        await conn.execute("TRUNCATE TABLE events CASCADE;")
        await conn.execute("TRUNCATE TABLE telemetry CASCADE;")
        
        await conn.close()
        
        logger.info("TimescaleDB tables truncated")
        
        return CommandResponse(
            ok=True,
            message="Tables TimescaleDB vidées (telemetry, events)"
        )
        
    except Exception as exc:
        logger.error(f"TimescaleDB reset failed: {exc}")
        raise HTTPException(
            status_code=500,
            detail=f"Erreur reset TimescaleDB: {str(exc)}"
        ) from exc
```

#### 2. Client API dans Streamlit

**Fichier :** `dashboard/api_client.py` (ajouter méthode)

```python
def reset_timescaledb(self) -> dict:
    """Appelle POST /simulation/reset/timescaledb."""
    return self._post("/simulation/reset/timescaledb", {})
```

#### 3. UI dans Streamlit

**Fichier :** `dashboard/app.py` (onglet Simulation, après reset temps)

```python
st.divider()
st.subheader("🗑️ Reset complet (destructif)")

col_reset = st.columns([2, 1])
with col_reset[0]:
    st.warning(
        "⚠️ **Reset complet** : Vide la simulation ET l'historique TimescaleDB. "
        "Impossible à annuler.",
        icon="⚠️"
    )

with col_reset[1]:
    if st.button("🗑️ Reset COMPLET", key="btn_reset_complete"):
        with st.spinner("Reset en cours..."):
            try:
                # 1. Reset soft (simulation)
                res1 = api._post("/simulation/speed/reset", {})
                
                # 2. Reset hard (TimescaleDB)
                res2 = api.reset_timescaledb()
                
                if res1.get("ok") and res2.get("ok"):
                    log_event("Reset COMPLET effectué")
                    st.success(
                        "✅ Reset complet réussi :\n"
                        "- Temps simulation → 0\n"
                        "- Énergie → 0\n"
                        "- TimescaleDB vidée"
                    )
                else:
                    st.error(f"❌ Erreur : {res1.get('message')} + {res2.get('message')}")
            except Exception as e:
                st.error(f"❌ Erreur reset : {e}")
```

---

### Option B : Deux boutons séparés (ALTERNATIVE)

**Si tu préfères garder les resets séparés :**

```python
col_a, col_b = st.columns(2)

with col_a:
    if st.button("🔄 Reset temps", key="btn_reset_time"):
        # Reset soft seulement
        res = api._post("/simulation/speed/reset", {})
        if res.get("ok"):
            st.success("✅ Temps + énergie réinitialisés")

with col_b:
    if st.button("🗑️ Vider TimescaleDB", key="btn_reset_tsdb"):
        # Reset hard seulement
        if st.checkbox("Confirmer suppression des données ?", key="confirm_tsdb"):
            res = api.reset_timescaledb()
            if res.get("ok"):
                st.success("✅ TimescaleDB vidée")
```

---

### Option C : Reset COMPLET unique (SIMPLIFIÉE)

**Un seul bouton qui fait tout :**

```python
if st.button("⚡ Reset COMPLET simulateur + données", key="btn_full_reset"):
    if st.checkbox("Je confirme : ceci supprimera TOUTES les données", key="confirm"):
        with st.spinner("Reset en cours..."):
            try:
                # Soft reset
                api._post("/simulation/speed/reset", {})
                # Hard reset
                api.reset_timescaledb()
                # Reload page
                st.rerun()
            except Exception as e:
                st.error(f"Erreur : {e}")
```

---

## Avantages / Inconvénients

### Option A (Reset TimescaleDB seul via API)
| Aspect | Avis |
|--------|------|
| Complexité | 🟡 Moyenne (ajouter endpoint API) |
| UX | 🟢 Flexible (soft + hard séparés) |
| Sécurité | 🟡 Besoin de vérification confirmation |
| Maintenance | 🟢 Cohésif (tout dans Streamlit) |

### Option B (Deux boutons)
| Aspect | Avis |
|--------|------|
| Complexité | 🟢 Simple |
| UX | 🟡 Deux étapes nécessaires |
| Sécurité | 🟢 Confirmation séparée |
| Maintenance | 🟢 Clair et séparé |

### Option C (Un bouton tout-en-un)
| Aspect | Avis |
|--------|------|
| Complexité | 🟢 Très simple |
| UX | 🟢 Une seule action |
| Sécurité | 🟡 Besoin confirmation stricte |
| Maintenance | 🟠 Trop magique |

---

## Recommandation

**Je propose Option A + Option C combinées :**

```python
# Dans tab_simulation(), après le reset temps :

st.divider()
st.subheader("🗑️ Reset complet (destructif)")

with st.expander("⚠️ OPTIONS DE RESET AVANCÉES"):
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**Reset soft** (simulation seule)")
        if st.button("🔄 Reset temps + énergie"):
            api._post("/simulation/speed/reset", {})
            st.success("✅ Temps simulé réinitialisé")
    
    with col2:
        st.markdown("**Reset hard** (données historiques)")
        if st.button("🗑️ Vider TimescaleDB"):
            if st.checkbox("Confirmer suppression", key="confirm_db"):
                api.reset_timescaledb()
                st.success("✅ TimescaleDB vidée")

st.markdown("---")
st.markdown("**Reset COMPLET** (simulation + données)")
if st.button("⚡ RESET COMPLET", key="btn_complete_reset"):
    confirm = st.checkbox(
        "⚠️ Je confirme : ceci supprimera TOUTES les données de simulation ET d'historique",
        key="confirm_complete"
    )
    if confirm:
        with st.spinner("Reset complet en cours..."):
            api._post("/simulation/speed/reset", {})
            api.reset_timescaledb()
            log_event("RESET COMPLET effectué")
            st.success("✅ RESET COMPLET réussi. Rechargement...")
            st.rerun()
```

---

## Implémentation : Checklist

### Backend (API)

- [ ] Ajouter endpoint `POST /simulation/reset/timescaledb`
- [ ] Importer asyncpg et configurer TimescaleDB DSN
- [ ] Gestion d'erreur si TimescaleDB non accessible
- [ ] Logging des operations
- [ ] Tests unitaires

### Frontend (Streamlit)

- [ ] Ajouter méthode `reset_timescaledb()` à `ApiClient`
- [ ] Ajouter UI dans `tab_simulation()` (onglet Simulation)
- [ ] Confirmation stricte (checkbox)
- [ ] Spinner et success messages
- [ ] Gestion des erreurs (try/except)

### Documentation

- [ ] Ajouter endpoint à API docs
- [ ] Documenter danger destructif
- [ ] Ajouter exemple d'usage

### Tests

- [ ] Test reset soft seul
- [ ] Test reset hard seul
- [ ] Test reset complet
- [ ] Vérifier que TimescaleDB est bien vidée
- [ ] Vérifier que nouvelle donnée arrive après reset

---

## Configuration TimescaleDB DSN

**À ajouter dans config :**

```python
# api/config.py ou api/deps.py

TIMESCALE_HOST = os.getenv("TIMESCALE_HOST", "timescaledb")
TIMESCALE_PORT = os.getenv("TIMESCALE_PORT", "5432")
TIMESCALE_USER = os.getenv("TIMESCALE_USER", "jumeaux")
TIMESCALE_DB = os.getenv("TIMESCALE_DB", "jumeaux")
TIMESCALE_PASSWORD = os.getenv("TIMESCALE_PASSWORD", "")

TIMESCALE_DSN = (
    f"postgresql://{TIMESCALE_USER}:{TIMESCALE_PASSWORD}"
    f"@{TIMESCALE_HOST}:{TIMESCALE_PORT}/{TIMESCALE_DB}"
)
```

---

## Sécurité

### ⚠️ Points critiques

1. **Pas de reset par erreur**
   - Confirmation checkbox obligatoire
   - Message d'avertissement clair
   - Bouton visuellement alarmant (🗑️ rouge)

2. **Logging des resets**
   ```python
   logger.warning(f"DESTRUCTIVE: TimescaleDB reset by user {request.client.host}")
   ```

3. **Optionnel : Limite d'accès**
   ```python
   # Si authentification implémentée
   @require_role("admin")
   async def reset_timescaledb():
       ...
   ```

---

## Impact utilisateur

### Avant (actuellement)
```
Utilisateur veut reset complet
    → Quitter Streamlit
    → Ouvrir terminal
    → Taper docker commands
    → Revenir à Streamlit
    → Rafraîchir page
```

### Après (avec cette implémentation)
```
Utilisateur veut reset complet
    → Streamlit, onglet "Simulation"
    → Cliquer "⚡ RESET COMPLET"
    → Cocher confirmation
    → Cliquer bouton
    → ✅ Fait, page reload auto
```

**Gain :** -5 minutes, -3 étapes, 0 ligne de commande

---

## Réponse à tes questions après implémentation

| Question | Avant | Après |
|----------|-------|-------|
| Reset complete possible ? | ⚠️ Manuel | ✅ Via UI |
| Tables vidées au reset ? | ❌ Manual | ✅ Oui |
| Accessible Streamlit ? | ❌ Non | ✅ Oui |
| Sécurisé ? | — | ✅ Confirmations strictes |

---

## Prochaines étapes

**Si tu veux implémenter :**

1. Créer task : "Implémenter reset TimescaleDB via API"
2. Suivre checklist ci-dessus
3. Tester avec docker compose (vérifier TRUNCATE fonctionne)
4. Ajouter documentation utilisateur
5. Commit message :
   ```
   feat(dashboard): add complete reset with TimescaleDB truncation
   
   - Add POST /simulation/reset/timescaledb endpoint
   - Add reset UI in Streamlit dashboard
   - Implement soft + hard reset options
   - Add safety confirmations
   ```

---

**Statut :** 📋 À discussion  
**Complexité estimée :** 2-3h de développement  
**ROI :** Très haut (meilleure UX)

*Proposition générée le 3 juin 2026*
