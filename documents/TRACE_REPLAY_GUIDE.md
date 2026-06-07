# Guide Trace Replay — Jumeaux Chauds

> **Phase 8.14B** — Rejouer des traces de charge datacenter réelles ou simulées.

Le scénario `trace_replay` permet de piloter la simulation avec une **trace temporelle CSV**
plutôt qu'une fonction mathématique. Cela offre trois avantages pédagogiques majeurs :

- Les algorithmes de maintenance prédictive sont évalués sur des données **non-synthétisables**
- Il est impossible de sur-apprendre un motif périodique (pas de sinusoïde cachée)
- Les résultats sont **reproductibles et comparables** entre expériences

---

## Table des matières

1. [Mode A — Traces embarquées (aucun prérequis)](#mode-a--traces-embarquées)
2. [Mode B — Dataset Bitbrains réel (~30 MB, téléchargement)](#mode-b--dataset-bitbrains-réel)
3. [Mode C — Trace exportée depuis Jumeaux Chauds](#mode-c--trace-exportée-depuis-jumeaux-chauds)
4. [Référence : paramètres YAML](#référence--paramètres-yaml)
5. [Format CSV attendu](#format-csv-attendu)
6. [Changer de trace sans rebuild](#changer-de-trace-sans-rebuild)

---

## Mode A — Traces embarquées

**Aucun téléchargement. Disponibles dès le clone du dépôt.**

Le dossier `data/traces/` contient 4 traces synthétiques générées à partir des statistiques
publiées du dataset Bitbrains FastStorage (Shen et al., 2015) :

| Fichier | Durée | Points | Type de VM |
|---------|-------|--------|-----------|
| `bitbrains_week_vm00.csv` | 168h (1 semaine) | 2 016 | Mixte — **recommandé** |
| `bitbrains_compute_vm01.csv` | 72h (3 jours) | 864 | Compute-intensive |
| `bitbrains_memory_vm07.csv` | 72h (3 jours) | 864 | Memory-intensive |
| `bitbrains_mixed_vm14.csv` | 72h (3 jours) | 864 | Mixte (charge modérée) |

### Lancement rapide

```bash
# 1. Build et démarrage (première fois)
docker compose down
docker compose build --no-cache
docker compose up -d

# 2. Activer le scénario trace_replay
curl -X PUT http://localhost:8000/simulation/scenario \
  -H "Content-Type: application/json" \
  -d '{"scenario": "trace_replay"}'

# 3. Observer la charge via MQTT
python scripts/mqtt_observer.py --host localhost --topics "dt/+/+/telemetry"
```

Ou directement au démarrage :

```bash
SCENARIO=trace_replay docker compose up -d
```

### Choisir une trace embarquée

Modifier `config/scenarios/trace_replay.yaml` :

```yaml
load_profile:
  type: "trace_replay"
  trace_file: "data/traces/bitbrains_compute_vm01.csv"  # ← changer ici
  loop: true
  speed_factor: 1.0
```

Puis recharger :

```bash
curl -X PUT http://localhost:8000/simulation/scenario \
  -H "Content-Type: application/json" \
  -d '{"scenario": "trace_replay"}'
```

### Lancement sans Docker (mode standalone)

```bash
conda activate jumeaux-chauds
python scripts/run_simulator.py --scenario trace_replay --duration 72h
```

---

## Mode B — Dataset Bitbrains réel

**Téléchargement une seule fois (~30 MB). Donne accès aux vraies traces de production.**

Le dataset **Bitbrains FastStorage** est un corpus public de traces de VMs en datacenter
de production, enregistrées sur plusieurs semaines à une granularité de 5 minutes.

Référence : *Shen, W. et al. (2015). "Statistiques des charges de travail dans les clouds.*
*Comparaison Bitbrains." ICSOC 2015.*

### Téléchargement et conversion

```bash
conda activate jumeaux-chauds

# Télécharger et convertir automatiquement
python scripts/download_traces.py

# Vérifier les traces disponibles
python scripts/download_traces.py --list

# Télécharger dans un autre dossier
python scripts/download_traces.py --target /chemin/vers/traces/
```

Le script :
1. Tente plusieurs sources connues (GitHub mirror, ibiblio)
2. Convertit le format brut Bitbrains (séparateur `;`, millisecondes, MHz) au format CSV standard
3. Dépose les fichiers dans `data/traces/`

**Colonnes du format brut Bitbrains :**

```
Timestamp [ms]; CPU cores; CPU usage [MHZ]; CPU capacity [MHZ];
Memory usage [KB]; Memory capacity [KB]; Disk read [KB/s]; Disk write [KB/s];
Network received [KB/s]; Network transmitted [KB/s]
```

**Colonnes après conversion :**

```
timestamp_s, cpu_percent, mem_percent, net_in_kbps, net_out_kbps, load_factor
```

### Utiliser une trace Bitbrains réelle

Après téléchargement, les fichiers apparaissent dans `data/traces/` sous la forme
`bitbrains_<nom_vm>.csv`. Pointer vers l'un d'eux dans le YAML :

```yaml
load_profile:
  type: "trace_replay"
  trace_file: "data/traces/bitbrains_rnd_1.csv"
  loop: true
  speed_factor: 1.0
```

### Réglage de la vitesse de replay

Les traces Bitbrains ont une granularité de 5 minutes (300 s entre points).
Avec `speed_factor: 1.0`, 1 heure simulée = 1 heure réelle.

Pour accélérer :

```yaml
speed_factor: 0.1   # 10× plus rapide : 1 semaine simulée en ~17h réelles
speed_factor: 0.01  # 100× : 1 semaine en ~1h40 réelle
```

Combiner avec `speed_multiplier` (boucle de simulation) pour un contrôle fin :

```bash
# Changer la vitesse de la boucle simulation à chaud
curl -X PUT http://localhost:8000/simulation/speed \
  -H "Content-Type: application/json" \
  -d '{"speed_multiplier": 60}'
```

---

## Mode C — Trace exportée depuis Jumeaux Chauds

**Boucle complète : simuler → exporter → rejouer. Idéal pour valider la reproductibilité.**

### Étape 1 — Générer une trace

```bash
conda activate jumeaux-chauds

# Exemple : 7 jours de scénario nominal (~1 minute de calcul)
python scripts/generate_dataset.py \
  --scenario nominal \
  --duration 7d \
  --output data/traces/ma_sim_nominal_7j.csv \
  --format csv

# Exemple : 30 jours de scénario stress (~4 minutes)
python scripts/generate_dataset.py \
  --scenario stress \
  --duration 30d \
  --output data/traces/ma_sim_stress_30j.csv \
  --format csv \
  --no-faults   # optionnel : désactiver les pannes pour un signal pur
```

Le CSV exporté contient les colonnes suivantes (parmi d'autres) :

```
ts, timestamp_s, cluster_id, machine_id, role, status,
temperature_c, power_w, energy_kwh, load_factor, fan_rpm_avg,
fault_active, fault_types
```

La colonne `load_factor` (valeur `[0.0, 1.0]`) est directement rejouable.
La colonne `timestamp_s` contient le temps simulé relatif en secondes.

### Étape 2 — Rejouer la trace

Modifier `config/scenarios/trace_replay.yaml` :

```yaml
load_profile:
  type: "trace_replay"
  trace_file: "data/traces/ma_sim_nominal_7j.csv"
  loop: false       # false = s'arrête à la fin de la trace
  speed_factor: 1.0
```

Puis recharger le scénario :

```bash
curl -X PUT http://localhost:8000/simulation/scenario \
  -H "Content-Type: application/json" \
  -d '{"scenario": "trace_replay"}'
```

### Pourquoi rejouer une simulation ?

Ce mode est utile pour :

- **Reproduire exactement** une séquence de charge et comparer deux configurations physiques
- **Isoler l'effet du profil de charge** de la variabilité stochastique des pannes
- **Benchmarker** un algorithme de maintenance prédictive sur une trace fixe et publiée
- **Enseigner** la différence entre un signal de charge synthétique et une trace réelle

### Sélectionner une seule machine dans un export multi-machines

Le CSV `generate_dataset.py` contient une ligne par tick **par machine**. Pour ne garder
qu'une machine avant de rejouer :

```bash
# Filtrer sur machine srv-master-01 (Linux/macOS)
head -1 data/traces/ma_sim_nominal_7j.csv > data/traces/master01_7j.csv
grep "srv-master-01" data/traces/ma_sim_nominal_7j.csv >> data/traces/master01_7j.csv
```

```powershell
# Windows PowerShell
$header = Get-Content data\traces\ma_sim_nominal_7j.csv | Select-Object -First 1
$rows   = Get-Content data\traces\ma_sim_nominal_7j.csv | Select-String "srv-master-01"
($header + $rows) | Set-Content data\traces\master01_7j.csv
```

---

## Référence — Paramètres YAML

```yaml
load_profile:
  type: "trace_replay"

  # Chemin vers le fichier CSV (relatif à la racine du projet ou absolu)
  trace_file: "data/traces/bitbrains_week_vm00.csv"

  # Si true : la trace recommence en boucle après la fin
  # Si false : la dernière valeur est maintenue indéfiniment
  loop: true

  # Facteur de dilatation/compression temporelle de la trace
  # 1.0 = durée réelle de la trace
  # 0.5 = trace jouée 2× plus vite (les 5 min entre points deviennent 2.5 min)
  # 2.0 = trace jouée 2× plus lentement
  speed_factor: 1.0
```

---

## Format CSV attendu

Le profil `trace_replay` accepte deux formats :

### Format A — `cpu_percent` (Bitbrains converti)

```csv
timestamp_s,cpu_percent,mem_percent,net_in_kbps,net_out_kbps
0,40.15,32.67,60.07,13.51
300,29.38,16.44,29.19,19.03
600,26.58,30.31,38.35,30.29
```

`cpu_percent` est normalisé automatiquement (`÷ 100`) pour produire `load_factor ∈ [0, 1]`.

### Format B — `load_factor` (generate_dataset.py)

```csv
timestamp_s,load_factor,temperature_c,power_w,...
0,0.401500,45.2,210.5,...
0.1,0.401489,45.3,210.6,...
```

`load_factor` est utilisé directement. Les autres colonnes sont ignorées.

**Colonnes obligatoires :** `timestamp_s` + (`cpu_percent` **ou** `load_factor`)

Les colonnes supplémentaires sont ignorées silencieusement.

---

## Changer de trace sans rebuild

Le profil `trace_replay` est chargé **paresseusement** (au premier tick après activation).
Il est possible de changer de trace à chaud :

```bash
# 1. Modifier le fichier YAML
#    config/scenarios/trace_replay.yaml → trace_file: "data/traces/autre.csv"

# 2. Recharger le scénario (sans redémarrer le simulateur)
curl -X PUT http://localhost:8000/simulation/scenario \
  -H "Content-Type: application/json" \
  -d '{"scenario": "trace_replay"}'

# 3. Vérifier le statut
curl http://localhost:8000/simulation/status
```

Pour basculer entre scénarios (ex: `trace_replay` → `nominal` → `trace_replay`) :

```bash
curl -X PUT http://localhost:8000/simulation/scenario \
  -d '{"scenario": "nominal"}'

curl -X PUT http://localhost:8000/simulation/scenario \
  -d '{"scenario": "trace_replay"}'
```

Chaque rechargement repart du début de la trace (t=0).

---

## Résumé des dossiers et fichiers

```
jumeaux-chauds/
├── data/
│   └── traces/
│       ├── README.md                     ← description des traces
│       ├── bitbrains_week_vm00.csv       ← trace 1 semaine (défaut)
│       ├── bitbrains_compute_vm01.csv    ← 3 jours, compute
│       ├── bitbrains_memory_vm07.csv     ← 3 jours, memory
│       └── bitbrains_mixed_vm14.csv      ← 3 jours, mixte
│
├── config/scenarios/
│   └── trace_replay.yaml                 ← scénario YAML (modifier trace_file ici)
│
├── scripts/
│   ├── download_traces.py                ← télécharger le vrai dataset Bitbrains
│   └── generate_dataset.py               ← exporter une simulation comme trace
│
└── simulation/
    └── scenarios.py                      ← _TraceReplay + profil trace_replay
```

---

*Tristan Vanrullen — La Plateforme, Marseille — 2026*
