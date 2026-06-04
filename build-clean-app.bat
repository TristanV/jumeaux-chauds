@echo off
REM ─────────────────────────────────────────────────────────────────────────
REM Jumeaux Chauds — Script de reconstruction complète
REM ─────────────────────────────────────────────────────────────────────────
REM Fonction: Réinitialiser l'application à un état propre
REM 1. Arrêter tous les conteneurs Docker
REM 2. Supprimer les volumes persistants (données)
REM 3. Nettoyer les images non utilisées
REM 4. Reconstruire l'image sans cache
REM 5. Lancer Docker Compose en mode storage
REM ─────────────────────────────────────────────────────────────────────────

setlocal enabledelayedexpansion

echo.
echo ══════════════════════════════════════════════════════════════════════
echo  🔥 Jumeaux Chauds — RECONSTRUCTION COMPLÈTE
echo ══════════════════════════════════════════════════════════════════════
echo.

REM Vérifier que Docker est disponible
docker --version >nul 2>&1
if errorlevel 1 (
    echo ❌ ERREUR: Docker n'est pas installé ou pas accessible.
    echo    Veuillez installer Docker Desktop et relancer le script.
    pause
    exit /b 1
)

echo [1/5] ⏹️  Arrêt de tous les conteneurs...
docker compose --profile storage down --remove-orphans 2>nul
if errorlevel 1 (
    echo ⚠️  Pas de conteneurs actifs (c'est normal au premier lancement)
)

echo.
echo [2/5] 🗑️  Vérification et vidage des tables TimescaleDB...
REM Essayer de vider les tables si TimescaleDB est actif
docker compose exec -T timescaledb psql -U jumeaux -d jumeaux -c "TRUNCATE TABLE telemetry; TRUNCATE TABLE events;" 2>nul
if errorlevel 1 (
    echo       ⚠️  TimescaleDB pas encore actif (c'est normal)
) else (
    echo       ✓ Tables vidées
)

echo.
echo [2/5] 🗑️  Suppression des volumes persistants...
echo       - Suppression: mosquitto_data, mosquitto_log
echo       - Suppression: timescale_data
echo       - Suppression: grafana_data

for /f "tokens=*" %%i in ('docker volume ls -q 2^>nul ^| findstr "jumeaux-chauds"') do (
    echo       → Suppression volume: %%i
    docker volume rm %%i 2>nul
)

REM Suppression explicite des volumes nommés
docker volume rm jumeaux-chauds_mosquitto_data 2>nul
docker volume rm jumeaux-chauds_mosquitto_log 2>nul
docker volume rm jumeaux-chauds_timescale_data 2>nul
docker volume rm jumeaux-chauds_grafana_data 2>nul

echo       ✓ Volumes supprimés

echo.
echo [3/5] 🧹 Nettoyage des images orphelines...
docker image prune -f 2>nul
echo       ✓ Nettoyage terminé

echo.
echo [3/5] 🧹 Nettoyage des réseaux...
docker network prune -f 2>nul
echo       ✓ Nettoyage réseau terminé


echo.
echo [4/5] 🔨 Reconstruction des images (--no-cache)...
docker compose build --no-cache
if errorlevel 1 (
    echo ❌ ERREUR lors de la reconstruction des images.
    pause
    exit /b 1
)
echo       ✓ Images reconstruites avec succès

echo.
echo [5/5] 🚀 Lancement de l'application (profil storage)...
docker compose --profile storage up -d
if errorlevel 1 (
    echo ❌ ERREUR lors du lancement des conteneurs.
    pause
    exit /b 1
)

echo       ✓ Conteneurs lancés
echo.
echo ══════════════════════════════════════════════════════════════════════
echo  ✅ RECONSTRUCTION COMPLÈTE RÉUSSIE
echo ══════════════════════════════════════════════════════════════════════
echo.
echo 📊 Points d'accès:
echo    • Dashboard Streamlit  → http://localhost:8501
echo    • API FastAPI          → http://localhost:8000/docs
echo    • Grafana              → http://localhost:3000 (admin/admin)
echo    • MQTT Broker          → localhost:1883
echo    • TimescaleDB          → localhost:5432
echo.
echo ⏳ Attente de 30 secondes pour que les services soient prêts...
timeout /t 30

echo.
echo 🧪 Vérification des services...
docker compose ps
echo.
echo 💡 Conseil: Utilisez 'docker compose logs -f' pour voir les logs en temps réel.
echo.
pause
