# Changelog — 3 juin 2026

## Modification : Dashboard Streamlit — Liens rapides vers services externes

### Objectif
Améliorer l'expérience utilisateur en ajoutant des liens directs vers :
1. API FastAPI (base) : `http://localhost:8000`
2. **API Docs (Swagger UI)** : `http://localhost:8000/docs` ✅ Nouvelle
3. **Grafana Dashboard** : `http://localhost:3000` ✅ Nouvelle

### Changements effectués

#### Fichier : `dashboard/app.py`
**Fonction modifiée :** `render_sidebar()`

**Avant :**
```python
st.divider()
st.caption("API : http://localhost:8000")
st.caption(f"Refresh : {REFRESH_INTERVAL_S}s")
```

**Après :**
```python
st.divider()

# Liens vers les services externes
st.subheader("🔗 Services externes")
col1, col2, col3 = st.columns(3)

with col1:
    st.markdown(
        "[🌐 API](http://localhost:8000)",
        unsafe_allow_html=True
    )
with col2:
    st.markdown(
        "[📖 API Docs](http://localhost:8000/docs)",
        unsafe_allow_html=True
    )
with col3:
    st.markdown(
        "[📊 Grafana](http://localhost:3000)",
        unsafe_allow_html=True
    )

st.divider()
st.caption(f"Refresh : {REFRESH_INTERVAL_S}s")
```

#### Fichier : `README.md`
Mise à jour de la section "Démarrer en 5 minutes" pour noter la présence des liens rapides dans le menu latéral.

### Détails techniques
- **Liens Markdown** : Utilisation de `st.markdown()` pour afficher des liens cliquables
- **Layout** : 3 colonnes pour bien espacer les liens
- **Icônes** : Emojis pour améliorer la visibilité
- **Comportement** : Les liens s'ouvrent dans un nouvel onglet (comportement par défaut du navigateur)

### Bénéfices pédagogiques
✅ Navigation facilitée entre les composants (Dashboard → API Docs → Grafana)  
✅ Découverte intuitive de la Swagger UI (documentation interactive)  
✅ Accès rapide aux dashboards analytiques Grafana  
✅ Meilleure compréhension de l'architecture globale (tous les services visibles)

### Aucun changement de comportement
- Pas d'impact sur la simulation
- Pas de dépendances nouvelles
- Pas de test affecté
- Compatibilité Streamlit : ✅ (markdown + columns sont standards)

### Comment tester
1. Lancer le dashboard : `streamlit run dashboard/app.py`
2. Ouvrir un navigateur : `http://localhost:8501`
3. Vérifier le menu latéral : section "🔗 Services externes" avec 3 liens
4. Cliquer sur chaque lien et confirmer qu'ils ouvrent les bonnes URLs

### Statut
✅ **Implémenté et testé**
- Code modifié : 1 fichier
- Tests : Aucun cassé
- Documentation : À jour (README.md)

---

*Tristan Vanrullen — La Plateforme, Marseille — 3 juin 2026*
