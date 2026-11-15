#!/usr/bin/env python3
"""Remplit une base de développement locale avec les démos reproductibles du dépôt.

Depuis la racine du projet, dans le terminal Cline / VS Code :
    python arena/remplir-base-locale.py --sqlite                  # aperçu, sans écriture
    python arena/remplir-base-locale.py --sqlite --apply --confirm-demo

Pour la base définie dans backend/.env (SQLite ou PostgreSQL sur localhost) :
    python arena/remplir-base-locale.py                          # aperçu
    python arena/remplir-base-locale.py --apply --confirm-demo

Pré-requis : Python, backend/requirements.txt installé dans l'interpréteur
utilisé, et backend/.env configuré (voir backend/.env.example). Ce script ne
copie PAS la base de la session Arena : il recrée des données représentatives.
Il ne lance ni le profil d'aperçu Arena, ni npm, ni un serveur web.
"""

import argparse
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
COMMANDS = [
    ("Référentiels officiels INJS", "importer_referentiels_injs"),
    ("Niveaux et semestres LMD", "init_referentiels_lmd"),
    ("Maquettes de référence", "configurer_referentiel_injs"),
    ("Compléments LMD", "completer_referentiel_lmd"),
    ("Activation des maquettes", "finaliser_maquettes_injs"),
    ("Référentiels admissions", "init_referentiels_admission"),
    ("Candidatures", "seed_candidatures_demo"),
    ("Équivalences", "seed_equivalences_demo"),
    ("Journal de scolarité", "reconstruire_journal_parcours"),
    ("Enseignants", "seed_enseignants_demo"),
    ("Stages", "seed_stages_demo"),
    ("Administration", "seed_administration_demo"),
    ("Personnel", "seed_personnel_demo"),
    ("Jurys", "seed_jurys_demo"),
    ("Diplômation", "seed_diplomation_demo"),
    ("Évaluations", "seed_evaluations_demo"),
    ("Finances étudiantes", "seed_finances_demo"),
]


def fail(message):
    raise SystemExit(f"ERREUR : {message}")


def execute(env, *args):
    subprocess.run([sys.executable, *map(str, args)], cwd=BACKEND, env=env, check=True)


def db_config(env):
    # Le même interpréteur, environnement et settings sont utilisés pour le
    # contrôle, la sauvegarde et les migrations. Aucun identifiant n'est affiché.
    os.environ.update(env)
    sys.path.insert(0, str(BACKEND))
    import django
    django.setup()
    from django.conf import settings
    if settings.DEBUG is False:
        fail("DJANGO_DEBUG doit être vrai : script réservé au développement local.")
    return settings.DATABASES["default"]


def local_target(db):
    engine = db["ENGINE"]
    if engine == "django.db.backends.sqlite3":
        filename = Path(db["NAME"]).expanduser().resolve()
        if str(db["NAME"]) == ":memory:":
            fail("SQLite en mémoire non pris en charge.")
        # Évite de toucher accidentellement une base située hors du projet.
        if not filename.is_relative_to(ROOT):
            fail(f"Base SQLite hors du dépôt : {filename}")
        return "sqlite", str(filename)
    if engine == "django.db.backends.postgresql":
        host = db.get("HOST", "")
        if host not in ("localhost", "127.0.0.1", "::1"):
            fail(f"PostgreSQL distant/interdit : hôte {host!r}. Utilisez une base locale.")
        return "postgres", f"{db['NAME']} sur {host}:{db.get('PORT') or 5432}"
    fail(f"Moteur non pris en charge : {engine}")


def backup(db, kind):
    # backups/ est ignoré par Git. Ne jamais y placer des fichiers versionnés.
    folder = ROOT / "backups" / ("base-locale-avant-demo-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f"))
    folder.mkdir(parents=True, mode=0o700)
    if kind == "sqlite":
        source_path = Path(db["NAME"]).expanduser().resolve()
        if not source_path.exists():
            print("Base SQLite absente : elle sera créée par les migrations.", flush=True)
            folder.rmdir()
            return None
        source = sqlite3.connect(source_path.as_uri() + "?mode=ro", uri=True)
        try:
            destination = sqlite3.connect(folder / "db.sqlite3")
            try:
                source.backup(destination)  # cohérent même avec journal WAL
            finally:
                destination.close()
        finally:
            source.close()
        saved = folder / "db.sqlite3"
    else:
        if not shutil.which("pg_dump"):
            folder.rmdir()
            fail("pg_dump introuvable : installez le client PostgreSQL avant d'écrire.")
        saved = folder / "base.dump"
        credentials = os.environ.copy()
        if db.get("PASSWORD"):
            credentials["PGPASSWORD"] = db["PASSWORD"]
        cmd = ["pg_dump", "--format=custom", "--no-owner", "--no-acl", "--file", str(saved),
               "--host", db["HOST"], "--port", str(db.get("PORT") or 5432),
               "--username", db["USER"], "--dbname", db["NAME"]]
        try:
            subprocess.run(cmd, env=credentials, check=True)
        except (OSError, subprocess.CalledProcessError):
            saved.unlink(missing_ok=True)
            folder.rmdir()
            fail("Sauvegarde PostgreSQL échouée : aucune donnée de démonstration ajoutée.")
    saved.chmod(0o600)
    print(f"Sauvegarde préalable : {saved} (privée, hors Git)", flush=True)
    return saved


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sqlite", action="store_true", help="utiliser backend/db.sqlite3 au lieu de la base de backend/.env")
    parser.add_argument("--apply", action="store_true", help="exécuter migrations et remplissage (sinon aperçu seul)")
    parser.add_argument("--confirm-demo", action="store_true", help="confirmer les comptes et mots de passe de démonstration")
    args = parser.parse_args()
    if args.apply and not args.confirm_demo:
        fail("ajoutez --confirm-demo après lecture de l'avertissement affiché en mode aperçu.")
    if not (BACKEND / "manage.py").is_file():
        fail("dépôt incomplet : backend/manage.py introuvable.")
    env = os.environ.copy()
    env["DJANGO_SETTINGS_MODULE"] = "config.settings"  # jamais le profil Arena
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    if args.sqlite:
        env["USE_SQLITE"] = "1"
        env["SQLITE_PATH"] = str(BACKEND / "db.sqlite3")
    # Écarte toute substitution de base par le profil d'aperçu.
    try:
        db = db_config(env)
    except (ImportError, ModuleNotFoundError) as error:
        fail(f"Dépendances Python manquantes ({error}). Installez backend/requirements.txt.")
    kind, target = local_target(db)
    print(f"Base cible : {target} ({kind})", flush=True)
    print("ATTENTION : données de démonstration uniquement, jamais en production.", flush=True)
    print("seed_data.py remet aussi les mots de passe de certains comptes démo à des valeurs connues.", flush=True)
    print("Les commandes ajoutent ou mettent à jour des enregistrements ; ne les lancez pas sur des données réelles.", flush=True)
    print("Étapes : sauvegarde préalable → migrate → seed_data.py →", flush=True)
    for label, command in COMMANDS:
        print(f"  {label} : manage.py {command}", flush=True)
    print("  Contrôle : manage.py verifier_coherence_referentiels", flush=True)
    if not args.apply:
        print("Aucune écriture effectuée. Pour lancer : répétez avec --apply --confirm-demo", flush=True)
        return
    saved = backup(db, kind)
    if saved:
        print("Conservez cette sauvegarde avant toute autre opération.", flush=True)
    print("Migrations…", flush=True)
    execute(env, "manage.py", "migrate", "--noinput")
    print("Données de base…", flush=True)
    execute(env, "seed_data.py")
    for label, command in COMMANDS:
        print(f"\n{label}…", flush=True)
        execute(env, "manage.py", command)
    print("\nContrôle final…", flush=True)
    execute(env, "manage.py", "verifier_coherence_referentiels")
    print("Remplissage terminé. Sauvegarde :", saved or "base SQLite neuve", flush=True)


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as error:
        fail(f"étape échouée (code {error.returncode}). Sauvegarde conservée dans backups/. "
             "Corrigez le problème puis relancez ; les seeds sont conçus pour être réexécutés.")
