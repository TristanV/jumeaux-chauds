#!/usr/bin/env python3
"""Téléchargeur de traces Bitbrains FastStorage — Jumeaux Chauds Phase 8.14B.

Télécharge et convertit les traces réelles du dataset Bitbrains FastStorage
au format CSV standard attendu par le profil `trace_replay`.

Référence dataset :
  Shen, Wenji et al. (2015). "Statistical Analysis of Large-Scale Cloud Infrastructure"
  Disponible : https://github.com/All-less/trace-generator / Bitbrains public traces

Usage :
    python scripts/download_traces.py
    python scripts/download_traces.py --target data/traces/
    python scripts/download_traces.py --list
"""
from __future__ import annotations

import argparse
import csv
import sys
import zipfile
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent.parent
_DEFAULT_TARGET = _PROJECT_ROOT / "data" / "traces"

# URLs connues du dataset Bitbrains FastStorage
# (plusieurs miroirs car la disponibilité varie)
_BITBRAINS_SOURCES = [
    {
        "name": "Bitbrains FastStorage (GitHub mirror)",
        "url": "https://raw.githubusercontent.com/All-less/trace-generator/master/data/fastStorage.zip",
        "type": "zip",
    },
    {
        "name": "Bitbrains FastStorage (ibiblio)",
        "url": "http://www.ibiblio.org/pub/linux/system/admin/Bitbrains/fastStorage.zip",
        "type": "zip",
    },
]


def list_available_traces(target: Path) -> None:
    """Liste les traces disponibles dans le dossier cible."""
    print(f"\n📂 Traces dans {target}:\n")
    csvs = sorted(target.glob("*.csv"))
    if not csvs:
        print("  (aucune trace trouvée)")
        return
    for f in csvs:
        size_kb = f.stat().st_size / 1024
        # Compter les points
        with open(f) as fp:
            n = sum(1 for _ in fp) - 1  # -1 pour l'en-tête
        print(f"  {f.name:40s} {n:5d} points  {size_kb:6.1f} KB")


def convert_bitbrains_csv(src_path: Path, dst_path: Path) -> int:
    """Convertit une trace Bitbrains brute au format standard.

    Format brut Bitbrains :
      Timestamp [ms];CPU cores;CPU usage [MHZ];CPU capacity provisioned [MHZ];
      Memory usage [KB];Memory capacity provisioned [KB];Disk read throughput [KB/s];
      Disk write throughput [KB/s];Network received throughput [KB/s];
      Network transmitted throughput [KB/s]

    Format converti :
      timestamp_s,cpu_percent,mem_percent,net_in_kbps,net_out_kbps,load_factor
    """
    rows_out = []
    t0 = None

    with open(src_path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("Timestamp"):
                continue
            parts = line.replace(",", ".").split(";")
            if len(parts) < 10:
                continue
            try:
                ts_ms = float(parts[0])
                cpu_mhz_used = float(parts[2])
                cpu_mhz_cap = float(parts[3])
                mem_kb_used = float(parts[4])
                mem_kb_cap = float(parts[5])
                net_in = float(parts[8])
                net_out = float(parts[9])
            except (ValueError, IndexError):
                continue

            if t0 is None:
                t0 = ts_ms

            ts_s = (ts_ms - t0) / 1000.0
            cpu_pct = (cpu_mhz_used / cpu_mhz_cap * 100) if cpu_mhz_cap > 0 else 0.0
            mem_pct = (mem_kb_used / mem_kb_cap * 100) if mem_kb_cap > 0 else 0.0
            load_factor = round(min(cpu_pct / 100.0, 1.0), 6)

            rows_out.append({
                "timestamp_s": round(ts_s, 1),
                "cpu_percent": round(cpu_pct, 2),
                "mem_percent": round(mem_pct, 2),
                "net_in_kbps": round(net_in, 2),
                "net_out_kbps": round(net_out, 2),
                "load_factor": load_factor,
            })

    with open(dst_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["timestamp_s", "cpu_percent", "mem_percent", "net_in_kbps", "net_out_kbps", "load_factor"]
        )
        writer.writeheader()
        writer.writerows(rows_out)

    return len(rows_out)


def download_and_extract(target: Path) -> bool:
    """Tente de télécharger les traces Bitbrains depuis les sources connues."""
    try:
        import urllib.request
    except ImportError:
        print("❌ urllib non disponible")
        return False

    target.mkdir(parents=True, exist_ok=True)
    tmp_zip = target / "_bitbrains_download.zip"

    for source in _BITBRAINS_SOURCES:
        print(f"\n⬇️  Tentative : {source['name']}")
        print(f"   URL : {source['url']}")
        try:
            urllib.request.urlretrieve(source["url"], tmp_zip)
            print(f"   ✅ Téléchargé ({tmp_zip.stat().st_size / 1024:.0f} KB)")
            break
        except Exception as e:
            print(f"   ❌ Échec : {e}")
            if tmp_zip.exists():
                tmp_zip.unlink()
    else:
        print("\n❌ Aucune source disponible.")
        print("\nTéléchargement manuel :")
        print("  1. Récupérer les traces depuis : https://bitbrains.nl/datasets/")
        print("  2. Placer les fichiers .csv dans data/traces/")
        print("  3. Renommer au format : bitbrains_<vm_name>.csv")
        return False

    # Extraction et conversion
    print(f"\n📦 Extraction et conversion...")
    converted = 0
    try:
        with zipfile.ZipFile(tmp_zip, "r") as zf:
            for name in zf.namelist():
                if not name.endswith(".csv"):
                    continue
                stem = Path(name).stem
                dst_name = f"bitbrains_{stem}.csv"
                dst_path = target / dst_name

                # Extraire vers un fichier temporaire
                tmp_src = target / f"_tmp_{stem}.csv"
                with zf.open(name) as src_f, open(tmp_src, "wb") as dst_f:
                    dst_f.write(src_f.read())

                # Convertir au format standard
                n = convert_bitbrains_csv(tmp_src, dst_path)
                tmp_src.unlink()
                size_kb = dst_path.stat().st_size / 1024
                print(f"  ✅ {dst_name}: {n} points, {size_kb:.1f} KB")
                converted += 1

    except zipfile.BadZipFile:
        print("❌ Fichier ZIP invalide. Le fichier téléchargé est peut-être corrompu.")
        return False
    finally:
        if tmp_zip.exists():
            tmp_zip.unlink()

    print(f"\n🎉 {converted} traces converties dans {target}")
    return converted > 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Télécharge et convertit les traces Bitbrains FastStorage",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples :
  python scripts/download_traces.py              # télécharger dans data/traces/
  python scripts/download_traces.py --list       # lister les traces disponibles
  python scripts/download_traces.py --target /tmp/traces/
        """,
    )
    parser.add_argument(
        "--target", default=str(_DEFAULT_TARGET),
        help=f"Dossier de destination (défaut: {_DEFAULT_TARGET})",
    )
    parser.add_argument(
        "--list", action="store_true",
        help="Lister les traces disponibles dans le dossier cible",
    )

    args = parser.parse_args()
    target = Path(args.target)

    print("=" * 60)
    print("🔥 Jumeaux Chauds — Téléchargeur de traces Bitbrains")
    print("=" * 60)

    if args.list:
        list_available_traces(target)
        return

    if not download_and_extract(target):
        print("\n💡 Les traces synthétiques embarquées dans data/traces/ restent disponibles.")
        sys.exit(1)

    print()
    list_available_traces(target)


if __name__ == "__main__":
    main()
