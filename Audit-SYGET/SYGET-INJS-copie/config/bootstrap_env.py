"""
Charge le fichier `.env` à la racine du dépôt si `python-dotenv` est installé.

Les variables déjà présentes dans l'environnement ne sont pas écrasées (comportement
par défaut de `load_dotenv`), ce qui préserve la prod (systemd, Docker secrets, etc.).
"""

from pathlib import Path


def load_env() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    root = Path(__file__).resolve().parent.parent
    load_dotenv(root / ".env")
