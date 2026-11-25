"""
Services de l'app auditeurs.
Import depuis Excel, création manuelle, gestion du référentiel auditeurs.
"""

import datetime
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Optional

from django.db import transaction

from shared.utils.grades import deduire_categorie

from .matricule import generer_matricule
from .models import Auditeur
from .repositories import AuditeurRepository


@dataclass
class ImportReport:
    """Rapport d'import d'auditeurs depuis un fichier Excel."""

    nb_crees: int = 0
    nb_ignores: int = 0
    nb_erreurs: int = 0
    nb_inscriptions: int = 0
    erreurs: list = field(default_factory=list)
    avertissements: list = field(default_factory=list)

    @property
    def total_traites(self) -> int:
        """Nombre total de lignes traitées."""
        return self.nb_crees + self.nb_ignores + self.nb_erreurs

    def to_csv(self) -> str:
        """Export CSV du rapport (résumé + détail erreurs/avertissements)."""
        import csv
        from io import StringIO

        buf = StringIO()
        writer = csv.writer(buf)
        writer.writerow(["Type", "Message"])
        writer.writerow(["Résumé", f"Créés={self.nb_crees} Ignorés={self.nb_ignores} Erreurs={self.nb_erreurs}"])
        writer.writerow(["Résumé", f"Inscriptions={self.nb_inscriptions}"])
        for err in self.erreurs:
            writer.writerow(["Erreur", err])
        for av in self.avertissements:
            writer.writerow(["Avertissement", av])
        return buf.getvalue()


class AuditeurService:
    """Logique métier pour la gestion des auditeurs."""

    def __init__(self, repo: AuditeurRepository) -> None:
        self._repo = repo

    def get_all(self):
        """Retourne tous les auditeurs."""
        return self._repo.list_all()

    @transaction.atomic
    def creer(
        self,
        nom: str,
        prenom: str,
        genre: str = "",
        date_naissance: Optional[datetime.date] = None,
        lieu_naissance: str = "",
        telephone_1: str = "",
        telephone_2: str = "",
        type_concours: str = "",
        libelle_concours: str = "",
        categorie: str = "",
        grade: str = "",
        email: str = "",
        matricule: str = "",
    ) -> Auditeur:
        """
        Crée un auditeur.
        Génère un matricule si non fourni.
        Lève ValueError si le matricule existe déjà.
        """
        matricule = matricule.strip() or generer_matricule(nom, prenom)
        if self._repo.get_by_matricule(matricule):
            raise ValueError(f"Le matricule '{matricule}' est déjà utilisé.")
        grade_norm = grade.strip().upper()
        auditeur = Auditeur(
            matricule=matricule,
            nom=nom.strip().upper(),
            prenom=prenom.strip(),
            genre=genre.strip(),
            date_naissance=date_naissance,
            lieu_naissance=lieu_naissance.strip(),
            telephone_1=telephone_1.strip(),
            telephone_2=telephone_2.strip(),
            type_concours=type_concours.strip(),
            libelle_concours=libelle_concours.strip(),
            categorie=deduire_categorie(categorie, grade_norm),
            grade=grade_norm,
            email=email.strip(),
        )
        return self._repo.save(auditeur)

    @transaction.atomic
    def modifier(
        self,
        pk: int,
        nom: str,
        prenom: str,
        genre: str = "",
        date_naissance: Optional[datetime.date] = None,
        lieu_naissance: str = "",
        telephone_1: str = "",
        telephone_2: str = "",
        type_concours: str = "",
        libelle_concours: str = "",
        categorie: str = "",
        grade: str = "",
        email: str = "",
    ) -> Auditeur:
        """
        Modifie un auditeur existant.
        Lève ValueError si l'auditeur est introuvable.
        """
        auditeur = self._repo.get_by_id(pk)
        if auditeur is None:
            raise ValueError(f"Auditeur {pk} introuvable.")
        auditeur.nom = nom.strip().upper()
        auditeur.prenom = prenom.strip()
        auditeur.genre = genre.strip()
        auditeur.date_naissance = date_naissance
        auditeur.lieu_naissance = lieu_naissance.strip()
        auditeur.telephone_1 = telephone_1.strip()
        auditeur.telephone_2 = telephone_2.strip()
        auditeur.type_concours = type_concours.strip()
        auditeur.libelle_concours = libelle_concours.strip()
        grade_norm = grade.strip().upper()
        auditeur.categorie = deduire_categorie(categorie, grade_norm)
        auditeur.grade = grade_norm
        auditeur.email = email.strip()
        return self._repo.save(auditeur)

    @transaction.atomic
    def supprimer(self, pk: int) -> None:
        """
        Supprime un auditeur.
        Lève ValueError si l'auditeur est inscrit à un ou plusieurs modules.
        """
        from apps.formations.models import Inscription

        if Inscription.objects.filter(auditeur_id=pk).exists():
            raise ValueError("Cet auditeur est inscrit à un ou plusieurs modules.")
        self._repo.delete(pk)

    def _inscrire_nouveaux_a_formation(self, matricules: list[str], formation_id: int) -> tuple[int, list[str]]:
        """
        Inscrit les auditeurs identifiés par matricule aux modules de la formation
        dont le grade cible est compatible avec le grade de l'auditeur.
        Retourne (nombre d'inscriptions créées, messages d'avertissement).
        """
        from apps.formations.models import FormationModule, Inscription

        from shared.utils.grades import grade_cible_matches

        if not matricules:
            return 0, []

        modules = list(FormationModule.objects.filter(formation_id=formation_id))
        if not modules:
            return 0, []

        auditeurs = list(Auditeur.objects.filter(matricule__in=matricules).only("id", "matricule", "grade"))
        inscriptions: list[Inscription] = []
        for aud in auditeurs:
            aud_grade = (aud.grade or "").strip().upper()
            for fm in modules:
                if grade_cible_matches(fm.grade_cible, aud_grade):
                    inscriptions.append(
                        Inscription(
                            formation_id=formation_id,
                            formation_module_id=fm.id,
                            auditeur_id=aud.id,
                        )
                    )

        if not inscriptions:
            warn = (
                "Aucune inscription n'a été créée : vérifiez les grades des lignes importées "
                "et les grades cibles des modules de la formation."
            )
            return 0, [warn] if auditeurs else []

        fm_ids = {ins.formation_module_id for ins in inscriptions}
        aud_ids = {ins.auditeur_id for ins in inscriptions}
        deja = set(
            Inscription.objects.filter(
                formation_module_id__in=fm_ids,
                auditeur_id__in=aud_ids,
            ).values_list("formation_module_id", "auditeur_id")
        )
        a_creer: list[Inscription] = []
        for ins in inscriptions:
            cle = (ins.formation_module_id, ins.auditeur_id)
            if cle not in deja:
                a_creer.append(ins)
                deja.add(cle)
        if not a_creer:
            return 0, []
        Inscription.objects.bulk_create(a_creer)
        return len(a_creer), []

    @transaction.atomic
    def importer_depuis_excel(self, fichier, formation_id: int) -> ImportReport:
        """
        Importe des auditeurs depuis un fichier Excel (.xlsx).
        Inscrit chaque fiche **nouvellement créée** aux modules de la formation
        ``formation_id`` compatibles avec le grade de l'auditeur.

        Colonnes attendues :
          matricule, nom, prenom, genre, date_naissance, lieu_naissance,
          telephone_1, telephone_2, type_concours, libelle_concours,
          categorie, grade, email.
        Valide les grades via le référentiel parametrage.Grade.
        """
        import pandas as pd

        from apps.parametrage.models import Grade

        report = ImportReport()

        from apps.formations.models import FormationModule

        if not FormationModule.objects.filter(formation_id=formation_id).exists():
            report.erreurs.append("La formation sélectionnée n'a aucun module : ajoutez des modules avant d'importer.")
            report.nb_erreurs += 1
            return report

        grades_valides = {
            str(g).strip().upper() for g in Grade.objects.filter(actif=True).values_list("libelle", flat=True)
        }

        def _normalize_header(name: str) -> str:
            raw = str(name or "").replace("\ufeff", "").strip()
            # Doublons Excel fusionnés : "NOM", "NOM.1"
            raw = re.sub(r"\.\d+$", "", raw)
            txt = unicodedata.normalize("NFKD", raw)
            txt = "".join(ch for ch in txt if not unicodedata.combining(ch))
            txt = txt.lower().strip()
            for ch in ("°", "º", "\u00ba", "\u00b0"):
                txt = txt.replace(ch, " ")
            for u in ("\xa0", "\u2007", "\u202f", "\u2009", "\u2008"):
                txt = txt.replace(u, " ")
            txt = re.sub(r"[^a-z0-9]+", "_", txt)
            return re.sub(r"_+", "_", txt).strip("_")

        header_aliases = {
            "n_inscription": "matricule",
            "no_inscription": "matricule",
            "numero_inscription": "matricule",
            "num_inscription": "matricule",
            "numero_d_inscription": "matricule",
            "n_d_inscription": "matricule",
            "no_d_inscription": "matricule",
            "matricule": "matricule",
            "nom": "nom",
            "prenom": "prenom",
            "prenoms": "prenom",
            "prenom_s": "prenom",
            "genre": "genre",
            "sexe": "genre",
            "categorie": "categorie",
            "categorie_corps": "categorie",
            "cat_corps": "categorie",
            "grade": "grade",
            "concours": "libelle_concours",
            "libelle_concours": "libelle_concours",
            "type_concours": "type_concours",
            "date_naissance": "date_naissance",
            "date_de_naissance": "date_naissance",
            "lieu_naissance": "lieu_naissance",
            "lieu_de_naissance": "lieu_naissance",
            "telephone": "telephone_1",
            "telephone_1": "telephone_1",
            "telephone_2": "telephone_2",
            "email": "email",
        }

        def _alias_columns(frame):
            out = frame.copy()
            out.columns = [header_aliases.get(_normalize_header(c), _normalize_header(c)) for c in out.columns]
            return out

        colonnes_requises = {"matricule", "nom", "prenom"}

        def _colonnes_ok(frame):
            return colonnes_requises.issubset(set(frame.columns))

        try:
            fichier.seek(0)
            df_raw = pd.read_excel(fichier, engine="openpyxl")
        except Exception as e:
            try:
                fichier.seek(0)
                df_raw = pd.read_excel(fichier)
            except Exception:
                report.erreurs.append(f"Impossible de lire le fichier : {e}")
                report.nb_erreurs += 1
                return report

        df = _alias_columns(df_raw)
        if not _colonnes_ok(df):
            try:
                fichier.seek(0)
                df_alt = _alias_columns(pd.read_excel(fichier, header=1, engine="openpyxl"))
                if _colonnes_ok(df_alt):
                    df = df_alt
            except Exception:
                try:
                    fichier.seek(0)
                    df_alt = _alias_columns(pd.read_excel(fichier, header=1))
                    if _colonnes_ok(df_alt):
                        df = df_alt
                except Exception:
                    pass

        if not _colonnes_ok(df) and len(df_raw) >= 1:
            first = df_raw.iloc[0]
            headers = [str(x).strip() if pd.notna(x) else "" for x in first.values]
            body = df_raw.iloc[1:].copy()
            body.columns = headers
            df_promoted = _alias_columns(body)
            if _colonnes_ok(df_promoted):
                df = df_promoted

        if not _colonnes_ok(df):
            detectees = sorted(set(df.columns))
            report.erreurs.append(
                "Colonnes obligatoires introuvables (attendu : N° d'inscription / matricule, nom, prénom). "
                f"Détectées après normalisation : {detectees}"
            )
            return report

        def _val(row, key, default=""):
            v = str(row.get(key, default) or default).strip()
            return "" if v.upper() == "NAN" else v

        colonnes = list(df.columns)

        def _cell_brut(v):
            """Aligné sur _val pour une cellule seule (liste issue du Excel/pandas)."""
            if v is None:
                return ""
            try:
                if pd.isna(v):
                    return ""
            except TypeError:
                pass
            s = str(v).strip()
            return "" if s.upper() == "NAN" else s

        matricules_fichier = [_cell_brut(x) for x in df["matricule"].tolist()]
        deja_en_base: set[str] = set()
        if matricules_fichier:
            uniques = list(dict.fromkeys(m for m in matricules_fichier if m))
            deja_en_base = set(Auditeur.objects.filter(matricule__in=uniques).values_list("matricule", flat=True))
        vus_dans_import: set[str] = set()

        nouveaux = []
        for idx_label, tup in zip(df.index, df.itertuples(index=False, name=None)):
            row = dict(zip(colonnes, tup))
            matricule = _val(row, "matricule")
            nom = _val(row, "nom").upper()
            prenom = _val(row, "prenom")

            if not matricule or not nom or not prenom:
                report.erreurs.append(f"Ligne {idx_label + 2} : données obligatoires manquantes.")
                report.nb_erreurs += 1
                continue

            grade = _val(row, "grade").upper()
            if grade and grade not in grades_valides:
                report.erreurs.append(f"Ligne {idx_label + 2} : grade '{grade}' non reconnu.")
                report.nb_ignores += 1
                continue

            if matricule in deja_en_base or matricule in vus_dans_import:
                report.nb_ignores += 1
                continue

            # Parsing date de naissance
            date_naissance = None
            raw_date = _val(row, "date_naissance") or _val(row, "date_de_naissance")
            if raw_date:
                for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
                    try:
                        date_naissance = datetime.datetime.strptime(raw_date, fmt).date()
                        break
                    except ValueError:
                        continue

            genre_raw = _val(row, "genre").upper()
            if genre_raw in {"M", "H", "HOMME", "MASCULIN", "MASCULIN(E)"}:
                genre = "M"
            elif genre_raw in {"F", "FEMME", "FEMININ", "FÉMININ", "FEMININ(E)", "FÉMININ(E)"}:
                genre = "F"
            else:
                genre = ""

            nouveaux.append(
                Auditeur(
                    matricule=matricule,
                    nom=nom,
                    prenom=prenom,
                    genre=genre,
                    date_naissance=date_naissance,
                    lieu_naissance=_val(row, "lieu_naissance") or _val(row, "lieu_de_naissance"),
                    telephone_1=_val(row, "telephone_1") or _val(row, "telephone"),
                    telephone_2=_val(row, "telephone_2"),
                    type_concours=_val(row, "type_concours"),
                    libelle_concours=_val(row, "libelle_concours"),
                    categorie=deduire_categorie(_val(row, "categorie"), grade),
                    grade=grade,
                    email=_val(row, "email"),
                )
            )

        if nouveaux:
            self._repo.bulk_create(nouveaux)
            report.nb_crees = len(nouveaux)
            matricules_crees = [a.matricule for a in nouveaux]
            ins_count, warns = self._inscrire_nouveaux_a_formation(matricules_crees, formation_id)
            report.nb_inscriptions = ins_count
            report.avertissements.extend(warns)

        return report
