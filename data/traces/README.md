# Traces de charge datacenter — Jumeaux Chauds Phase 8.14B

Ce dossier contient des traces de charge prêtes à être rejouées par le profil `trace_replay`.

## Fichiers embarqués

| Fichier | Durée | Points | Taille | Type de VM |
|---------|-------|--------|--------|-----------|
| `bitbrains_compute_vm01.csv` | 72h (3 jours) | 864 | ~26 KB | VM compute-intensive |
| `bitbrains_memory_vm07.csv`  | 72h (3 jours) | 864 | ~26 KB | VM memory-intensive |
| `bitbrains_mixed_vm14.csv`   | 72h (3 jours) | 864 | ~26 KB | VM charge mixte |
| `bitbrains_week_vm00.csv`    | 168h (1 semaine) | 2016 | ~61 KB | VM charge mixte, 1 semaine |

Ces traces sont des données **synthétiques** générées à partir des statistiques publiées du
dataset Bitbrains FastStorage (Shen et al., 2015). Elles reproduisent fidèlement :
- Cycles journaliers (pics 10h et 15h)
- Cycles hebdomadaires (weekday vs weekend)
- Bruit organique Perlin (corrélation temporelle réaliste)
- Distribution bimodale CPU typique d'un datacenter de production

## Format CSV

```
timestamp_s,cpu_percent,mem_percent,net_in_kbps,net_out_kbps
0,40.15,32.67,60.07,13.51
300,29.38,16.44,29.19,19.03
...
```

- `timestamp_s` : temps relatif en secondes depuis le début de la trace
- `cpu_percent` : utilisation CPU [0–100]
- `mem_percent` : utilisation mémoire [0–100]
- `net_in_kbps` / `net_out_kbps` : trafic réseau en kbps

Le profil `trace_replay` utilise `cpu_percent` normalisé comme `load_factor ∈ [0, 1]`.

## Télécharger le vrai dataset Bitbrains

```bash
python scripts/download_traces.py --target data/traces/
```

Ce script télécharge les traces réelles depuis le dépôt public Bitbrains (~30 MB).
Les traces téléchargées sont converties au format CSV standard et placées dans ce dossier.

## Ajouter ses propres traces

Le profil `trace_replay` accepte n'importe quel CSV avec au minimum :
- `timestamp_s` (int ou float, secondes relatives)
- `cpu_percent` (float, 0–100)

ou alternativement :
- `timestamp_s` + `load_factor` (float, 0.0–1.0) — utilisé directement sans normalisation

## Utiliser les traces dans generate_dataset.py

Les simulations Jumeaux Chauds peuvent aussi être exportées comme traces rejouables :

```bash
python scripts/generate_dataset.py --scenario nominal --duration 7d --output data/traces/my_sim_trace.csv --format csv
```

La colonne `load_factor` du CSV exporté est directement rejouable par `trace_replay`.
