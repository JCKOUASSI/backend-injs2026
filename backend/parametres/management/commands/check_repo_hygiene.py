"""Garde-fou d'hygiène du dépôt (P00-02, étendu P00-05).

Deux familles de vérifications, chacune traitée par une fonction PURE
(testable sans disque) :

1. ``find_violations`` : aucun fichier de données nominatives, aucun classeur
   d'import réel ni aucun artefact de build (staticfiles) suivi par Git. Les
   modèles vides d'import sont autorisés dans ``docs/modeles/`` et les fixtures
   synthétiques (``test_*.xlsx``) dans les applications.

2. ``find_print_violations`` (P00-05) : aucun appel ``print()`` dans le code
   Python du *runtime* Django — le logging structuré (configuration ``LOGGING``
   : console en DEBUG, fichier rotatif sinon) est la seule sortie attendue, et
   les commandes de gestion utilisent ``self.stdout.write``. Les scripts
   manuels d'import/reprise (CLI opérateur hors runtime), les tests et les
   migrations sont exclus explicitement.

La commande sort en code 1 dès qu'une violation est détectée (elle est
branchée dans la CI, job Backend, avant les tests).
"""
from __future__ import annotations

import ast
import fnmatch
import subprocess

from django.conf import settings
from django.core.management.base import BaseCommand

# Dossier unique autorisé pour les modèles d'import versionnés.
MODELS_DIR = "docs/modeles/"
# Fichiers de données interdits partout, sauf exceptions ci-dessous.
DATA_PATTERNS = ("*.xlsx", "*.xls", "*.csv", "*.numbers")
FORBIDDEN_NAMES = (".env",)
FORBIDDEN_SUFFIXES = (".sqlite3",)
FORBIDDEN_PATH_PARTS = ("staticfiles/", "importverif/", "assets/app.env")

# --- P00-05 : périmètre « runtime » pour l'interdiction de print() ---------
# Le contrôle porte sur tout le Python versionné sous backend/, à l'exception :
RUNTIME_EXCLUDED_PARTS = (
    "/migrations/",          # migrations : sorties historiques figées
    "/scripts/",             # CLI manuels d'import/reprise (backend/scripts/)
    "/__pycache__/",
)
RUNTIME_EXCLUDED_SUFFIXES = ("_test.py",)
RUNTIME_TEST_PATH_MARKERS = ("/tests/", "/test/")
# Scripts manuels historiques placés à la racine de backend/ (sortie opérateur
# légitime, hors runtime serveur) — liste explicite et fermée.
RUNTIME_EXCLUDED_ROOT_SCRIPTS = (
    "backend/analyse_dossier.py",
    "backend/analyze_edt.py",
    "backend/build_import_from_donnees.py",
    "backend/count_groups.py",
    "backend/count_seances.py",
    "backend/extract_modules_edt.py",
    "backend/generate_import_files.py",
    "backend/generate_import_formateurs.py",
    "backend/seed_data.py",
    "backend/tests_e2e_injs_2026_2027.py",
    "backend/verify_import_files.py",
)


def _is_synthetic_test_fixture(path: str) -> bool:
    """Fixture de test générée et non nominative (ex: backend/test_*.xlsx)."""
    name = path.rsplit("/", 1)[-1]
    return name.startswith("test_") and name.endswith((".xlsx", ".xls", ".csv"))


def find_violations(tracked_files):
    """Renvoie la liste des chemins suivis qui violent les règles de fichiers.

    Pur (pas d'E/S) pour être testable directement.
    """
    violations = []
    for raw in tracked_files:
        path = raw.strip().replace("\\", "/")
        if not path:
            continue
        name = path.rsplit("/", 1)[-1]

        if any(part in path for part in FORBIDDEN_PATH_PARTS):
            violations.append(path)
            continue
        if name in FORBIDDEN_NAMES or path.endswith(FORBIDDEN_SUFFIXES):
            violations.append(path)
            continue
        if any(fnmatch.fnmatch(name, pat) for pat in DATA_PATTERNS):
            if path.startswith(MODELS_DIR):
                continue
            if _is_synthetic_test_fixture(path):
                continue
            violations.append(path)
    return sorted(set(violations))


# --- P00-05 : détection AST des print() runtime ----------------------------

def est_python_runtime(path: str) -> bool:
    """Vrai si un chemin versionné relatif au dépôt est du Python runtime.

    Runtime = code susceptible d'être importé ou exécuté par Django (apps,
    ``config``, commandes de gestion, modules racine de ``backend/``). Les
    tests, migrations, scripts manuels et caches sont exclus.
    """
    path = path.replace("\\", "/")
    if not path.startswith("backend/") or not path.endswith(".py"):
        return False
    if path in RUNTIME_EXCLUDED_ROOT_SCRIPTS:
        return False
    name = path.rsplit("/", 1)[-1]
    if name.startswith("test_") or name in ("tests.py",):
        return False
    if any(marker in path for marker in RUNTIME_TEST_PATH_MARKERS):
        return False
    if any(part in path for part in RUNTIME_EXCLUDED_PARTS):
        return False
    if path.endswith(RUNTIME_EXCLUDED_SUFFIXES):
        return False
    return True


def _noms_lies_par_portee(node) -> set[str]:
    """Noms liés localement par une fonction/lambda (paramètres + assignations)."""
    noms: set[str] = set()
    args = getattr(node, "args", None)
    if args is not None:
        for argument in (
            list(getattr(args, "posonlyargs", []))
            + list(getattr(args, "args", []))
            + list(getattr(args, "kwonlyargs", []))
        ):
            noms.add(argument.arg)
        for nom in (args.vararg, args.kwarg):
            if nom is not None:
                noms.add(nom.arg)

    class LiaisonVisitor(ast.NodeVisitor):
        def visiter_liaison(self, cible):
            if isinstance(cible, ast.Name):
                noms.add(cible.id)
            elif isinstance(cible, (ast.Tuple, ast.List)):
                for element in cible.elts:
                    self.visiter_liaison(element)
            elif isinstance(cible, ast.Starred):
                self.visiter_liaison(cible.value)

        def visit_Assign(self, node):  # noqa: N802
            for cible in node.targets:
                self.visiter_liaison(cible)
            self.generic_visit(node)

        def visit_AnnAssign(self, node):  # noqa: N802
            if node.target is not None:
                self.visiter_liaison(node.target)
            self.generic_visit(node)

        def visit_For(self, node):  # noqa: N802
            self.visiter_liaison(node.target)
            self.generic_visit(node)

        def visit_withitem(self, node):  # noqa: N802
            if node.optional_vars is not None:
                self.visiter_liaison(node.optional_vars)

        def visit_FunctionDef(self, node):  # noqa: N802
            noms.add(node.name)  # fonction locale
            self.generic_visit(node)

        visit_AsyncFunctionDef = visit_FunctionDef

        def visit_Lambda(self, node):  # noqa: N802
            self.generic_visit(node)

        def visit_Import(self, node):  # noqa: N802
            for alias in node.names:
                noms.add((alias.asname or alias.name).split(".")[0])

        def visit_ImportFrom(self, node):  # noqa: N802
            for alias in node.names:
                if alias.name != "*":
                    noms.add(alias.asname or alias.name)

    LiaisonVisitor().visit(node)
    return noms


def trouver_appels_print(source: str) -> list[int]:
    """Numéros de ligne des appels ``print(...)`` qui résolvent vers le builtin.

    Un ``print`` redéfini (assignation, import, paramètre ou fonction nommée
    ``print`` dans une portée englobante) n'est PAS signalé. Les mentions dans
    les commentaires, docstrings ou chaînes (ex. ``fingerprint(``) sont
    naturellement ignorées par l'analyse syntaxique.
    """
    try:
        arbre = ast.parse(source)
    except SyntaxError:
        # Un fichier Python qui ne parse pas relève d'un autre garde-fou ;
        # inutile de faire échouer l'hygiène avec de fausses détections.
        return []

    lignes: list[int] = []

    class PrintVisitor(ast.NodeVisitor):
        def __init__(self):
            self.pile_portees: list[set[str]] = []

        def _print_est_builtin(self) -> bool:
            return not any("print" in portee for portee in self.pile_portees)

        def visit_Module(self, node):  # noqa: N802
            self.pile_portees.append(_noms_lies_par_portee(node))
            self.generic_visit(node)
            self.pile_portees.pop()

        def visiter_fonction(self, node):
            self.pile_portees.append(_noms_lies_par_portee(node))
            self.generic_visit(node)
            self.pile_portees.pop()

        visit_FunctionDef = visiter_fonction
        visit_AsyncFunctionDef = visiter_fonction
        visit_Lambda = visiter_fonction

        def visit_Call(self, node):  # noqa: N802
            func = node.func
            if (
                isinstance(func, ast.Name)
                and func.id == "print"
                and self._print_est_builtin()
            ):
                lignes.append(node.lineno)
            self.generic_visit(node)

    PrintVisitor().visit(arbre)
    return sorted(set(lignes))


def find_print_violations(contenus: dict[str, str]) -> list[str]:
    """Pur : ``{chemin_versionné: source}`` → lignes de violation print runtime."""
    violations = []
    for chemin, source in contenus.items():
        if not est_python_runtime(chemin):
            continue
        for numero in trouver_appels_print(source):
            violations.append(
                f"{chemin}:{numero}: appel print() dans le code runtime — "
                "utiliser logging (ou self.stdout.write dans une commande)"
            )
    return sorted(violations)


def list_tracked_files():
    """Liste les fichiers suivis par Git à la racine du dépôt (chemins rel. dépôt)."""
    # settings.BASE_DIR pointe vers backend/ ; la racine du dépôt est le parent.
    repo_root = str(settings.BASE_DIR.parent)
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.splitlines()


def lire_contenus_runtime(tracked_files):
    """Lit les sources des fichiers Python runtime suivis (E/S disque)."""
    repo_root = settings.BASE_DIR.parent
    contenus = {}
    for raw in tracked_files:
        chemin = raw.strip().replace("\\", "/")
        if not est_python_runtime(chemin):
            continue
        with (repo_root / chemin).open(encoding="utf-8") as fichier:
            contenus[chemin] = fichier.read()
    return contenus


class Command(BaseCommand):
    help = (
        "Échoue si un fichier interdit est versionné ou si le code runtime "
        "contient un appel print() (P00-05 : logging obligatoire)."
    )

    def handle(self, *args, **options):
        try:
            tracked = list_tracked_files()
        except (subprocess.CalledProcessError, FileNotFoundError) as exc:
            raise SystemExit(f"Impossible de lister les fichiers suivis par Git : {exc}")

        violations_fichiers = find_violations(tracked)
        if violations_fichiers:
            self.stderr.write(
                self.style.ERROR(
                    f"Hygiène du dépôt NON CONFORME — {len(violations_fichiers)} "
                    "fichier(s) interdit(s) suivi(s) :"
                )
            )
            for path in violations_fichiers:
                self.stderr.write(f"  - {path}")
            self.stderr.write(
                "\nSortez-les du suivi avec 'git rm --cached <fichier>' (sans les supprimer "
                "du disque) ; les modèles vides vont dans docs/modeles/."
            )

        violations_print = find_print_violations(lire_contenus_runtime(tracked))
        if violations_print:
            self.stderr.write(
                self.style.ERROR(
                    f"\nHygiène du code NON CONFORME — {len(violations_print)} appel(s) "
                    "print() dans le runtime Django (P00-05) :"
                )
            )
            for ligne in violations_print:
                self.stderr.write(f"  - {ligne}")
            self.stderr.write(
                "\nUtilisez un logger (logging.getLogger(__name__)) dans le code applicatif, "
                "self.stdout.write dans une commande de gestion. Les scripts manuels "
                "(backend/scripts/, scripts racine listés dans le garde-fou) sont exclus."
            )

        if violations_fichiers or violations_print:
            raise SystemExit(1)

        self.stdout.write(
            self.style.SUCCESS(
                f"Hygiène du dépôt CONFORME — {len(tracked)} fichiers suivis vérifiés, "
                "aucune donnée nominative/artefact versionné, aucun print() runtime."
            )
        )
