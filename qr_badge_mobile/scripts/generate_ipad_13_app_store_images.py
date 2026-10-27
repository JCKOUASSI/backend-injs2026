#!/usr/bin/env python3
"""Compose des captures 2048×2732 px (slot App Store iPad 13") à partir des visuels téléphone."""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "play_store_assets"
OUT_DIR = ROOT / "app_store_exports" / "ipad_13inch"
CANVAS_W, CANVAS_H = 2048, 2732
BG = (248, 250, 252)  # gris très clair, lisible sur la fiche store


def compose(src: Path, dest: Path) -> None:
    phone = Image.open(src).convert("RGBA")
    phone.thumbnail((CANVAS_W, CANVAS_H), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (CANVAS_W, CANVAS_H), BG)
    x = (CANVAS_W - phone.width) // 2
    y = (CANVAS_H - phone.height) // 2
    canvas.paste(phone, (x, y), phone)
    dest.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(dest, "PNG", optimize=True)
    print(f"{src.name} → {dest} ({CANVAS_W}×{CANVAS_H})")


def main() -> int:
    pairs = [
        ("phone_01_connexion_1080x1920.png", "ipad13_01_connexion.png"),
        ("phone_02_scanner_1080x1920.png", "ipad13_02_scanner.png"),
        ("phone_03_accueil_1080x1920.png", "ipad13_03_accueil.png"),
        ("phone_04_historique_1080x1920.png", "ipad13_04_historique.png"),
    ]
    missing = [s for s, _ in pairs if not (SRC_DIR / s).exists()]
    if missing:
        print("Fichiers manquants :", missing, file=sys.stderr)
        return 1
    for src_name, out_name in pairs:
        compose(SRC_DIR / src_name, OUT_DIR / out_name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
