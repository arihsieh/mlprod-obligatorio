#!/usr/bin/env python3
"""Remove tuning trial checkpoints to free disk space."""
import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ROOT = Path(__file__).resolve().parents[1]
TUNING = ROOT / "models" / "tuning"


def main() -> None:
    parser = argparse.ArgumentParser(description="Delete tuning trial model files.")
    args = parser.parse_args()

    removed = 0
    freed = 0
    if TUNING.exists():
        for path in TUNING.rglob("*"):
            if path.is_file():
                freed += path.stat().st_size
                path.unlink()
                removed += 1
        shutil.rmtree(TUNING, ignore_errors=True)

    for name in ("temas-phase2", "carga-phase2"):
        target = ROOT / "models" / name
        if target.exists():
            freed += sum(f.stat().st_size for f in target.rglob("*") if f.is_file())
            shutil.rmtree(target)
            print(f"Removed {target}")

    print(f"Removed {removed} files from tuning dirs (~{freed / (1024 ** 3):.2f} GB)")


if __name__ == "__main__":
    main()
