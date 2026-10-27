"""Import controle du referentiel INJS-LMD (lot A-4.4).

Perimetre strictement structurel, sans invention pedagogique :
complete les metadonnees NULL des 8 RefFormation existantes, garantit
L1/L2/L3/M1/M2 (60 credits) + S1..S10, et une RegleValidationLMD par
defaut (30 ECTS/semestre) par formation. Cree les coquilles RefFormation
manquantes (ES/MS/ENSEP) avec metadonnees NULL = A CONFIRMER.
NE cree JAMAIS : parcours, UE, ECUE, codes, credits ventiles,
affectations, rattachements, durees D9. Idempotent (--dry-run supporte).
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from formations.models import RefFormation
from scolarite.models import (
    AnneeAcademique,
    Niveau,
    RegleValidationLMD,
    Semestre,
)

FILIERES = [
    ("ÉDUCATION ET MOTRICITÉ — LICENCE", "LICENCE", "STAPS", "EM", 3, 6, 180),
    ("ÉDUCATION ET MOTRICITÉ — MASTER", "MASTER", "STAPS", "EM", 2, 4, 120),
    ("ACTIVITÉS PHYSIQUES ADAPTÉES — LICENCE", "LICENCE", "STAPS", "APA", 3, 6, 180),
    ("ACTIVITÉS PHYSIQUES ADAPTÉES — MASTER", "MASTER", "STAPS", "APA", 2, 4, 120),
    ("ENTRAÎNEMENT SPORTIF — LICENCE", None, "", "", None, None, None),
    ("ENTRAÎNEMENT SPORTIF — MASTER", None, "", "", None, None, None),
    ("MANAGEMENT DU SPORT — LICENCE", None, "", "", None, None, None),
    ("MANAGEMENT DU SPORT — MASTER", None, "", "", None, None, None),
    ("ANDRAGOGIE", None, "", "", None, None, None),
    ("LOISIR", None, "", "", None, None, None),
    ("ENTREPRENEURIAT JEUNESSE ET CONDUITE DE PROJETS", None, "", "", None, None, None),
    ("GÉRONTOLOGIE", None, "", "", None, None, None),
]

EXISTANTS_CONNUS = {
    "ÉDUCATION ET MOTRICITÉ — LICENCE": ("LICENCE", "STAPS", "EM", 3, 6, 180),
    "ÉDUCATION ET MOTRICITÉ — MASTER": ("MASTER", "STAPS", "EM", 2, 4, 120),
    "ACTIVITÉS PHYSIQUES ADAPTÉES — LICENCE": ("LICENCE", "STAPS", "APA", 3, 6, 180),
    "ACTIVITÉS PHYSIQUES ADAPTÉES — MASTER": ("MASTER", "STAPS", "APA", 2, 4, 120),
    "PROFESSORAT DE LYCÉE — EPS": (None, "", "", None, None, None),
    "PROFESSORAT DE LYCÉE — SPORT": (None, "", "", None, None, None),
    "PROFESSORAT DE COLLÈGE — EPS": (None, "", "", None, None, None),
    "MAÎTRE(SSE) D’ÉDUCATION PHYSIQUE ET SPORTIVE": (None, "", "", None, None, None),
}

NIVEAUX = [
    ("L1", "Licence 1", Niveau.Cycle.LICENCE, 1, (1, 2), 60),
    ("L2", "Licence 2", Niveau.Cycle.LICENCE, 2, (3, 4), 60),
    ("L3", "Licence 3", Niveau.Cycle.LICENCE, 3, (5, 6), 60),
    ("M1", "Master 1", Niveau.Cycle.MASTER, 4, (7, 8), 60),
    ("M2", "Master 2", Niveau.Cycle.MASTER, 5, (9, 10), 60),
]


class _AnnulationDryRun(Exception):
    pass


class Command(BaseCommand):
    help = "Import controle et idempotent du referentiel INJS-LMD (A-4.4)."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--annee", default="2026-2027")
    def handle(self, *args, **options):
        simule = options["dry_run"]
        c = {"CREATED": 0, "EXISTING": 0, "UPDATED": 0,
             "SKIPPED": 0, "REJECTED": 0, "WARNING": 0}
        lignes = []
        try:
            with transaction.atomic():
                self._importer(c, lignes, options["annee"])
                if simule:
                    raise _AnnulationDryRun()
        except _AnnulationDryRun:
            pass
        entete = "Simulation --dry-run (aucune ecriture)" if simule else "Import termine"
        self.stdout.write(self.style.MIGRATE_HEADING(entete))
        for ligne in lignes:
            self.stdout.write("  " + ligne)
        self.stdout.write("  " + " ".join(f"{k}={v}" for k, v in c.items()))
        self.stdout.write(self.style.SUCCESS(
            "  UE=0 ECUE=0 parcours=0 codes=0 (A-4.5 : non documentes, jamais inventes)."))

    def _importer(self, c, lignes, annee_libelle):
        annee = AnneeAcademique.objects.filter(libelle=annee_libelle).first()
        if annee is None:
            lignes.append(f"REJECTED annee {annee_libelle} absente.")
            c["REJECTED"] += 1
            return
        lignes.append(f"EXISTING annee {annee.libelle} (courante={annee.courante}).")
        c["EXISTING"] += 1
        self._niveaux_semestres(c, lignes)
        self._formations(c, lignes)
        self._regles(c, lignes)

    def _niveaux_semestres(self, c, lignes):
        for code, libelle, cycle, ordre, numeros, credits in NIVEAUX:
            niveau, cree = Niveau.objects.get_or_create(
                code=code,
                defaults={"libelle": libelle, "cycle": cycle,
                          "ordre": ordre, "credits_requis": credits},
            )
            if cree:
                lignes.append(f"CREATED niveau {code} ({libelle}, 60 ECTS).")
                c["CREATED"] += 1
            elif not niveau.credits_requis:
                niveau.credits_requis = credits
                niveau.save(update_fields=["credits_requis"])
                lignes.append(f"UPDATED niveau {code} : credits_requis -> 60.")
                c["UPDATED"] += 1
            else:
                lignes.append(f"EXISTING niveau {code} ({niveau.credits_requis} ECTS).")
                c["EXISTING"] += 1
            for numero in numeros:
                _, cree_sem = Semestre.objects.get_or_create(
                    niveau=niveau, numero=numero,
                    defaults={"libelle": f"S{numero}"},
                )
                if cree_sem:
                    lignes.append(f"CREATED semestre S{numero} ({code}).")
                    c["CREATED"] += 1
                else:
                    c["EXISTING"] += 1
        lignes.append("SKIPPED creation M3/M4/M5 : interdite (A-4.4 §5).")
        c["SKIPPED"] += 1

    def _formations(self, c, lignes):
        for intitule, td, dom, men, dur, nb_sem, nb_cred in FILIERES:
            formation, cree = RefFormation.objects.get_or_create(intitule=intitule)
            if cree:
                formation.type_diplome = td or ""
                formation.domaine = dom or ""
                formation.mention = men or ""
                formation.duree_annees = dur
                formation.nb_semestres = nb_sem
                formation.nb_credites = nb_cred
                formation.save()
                lignes.append(f"CREATED formation « {intitule} ».")
                c["CREATED"] += 1
                continue
            maj = self._completer_nulls(formation, td, dom, men, dur, nb_sem, nb_cred)
            if maj:
                lignes.append(f"UPDATED formation « {intitule} » : {', '.join(maj)}.")
                c["UPDATED"] += 1
            else:
                lignes.append(f"EXISTING formation « {intitule} ».")
                c["EXISTING"] += 1
        for intitule, (td, dom, men, dur, nb_sem, nb_cred) in EXISTANTS_CONNUS.items():
            formation = RefFormation.objects.filter(intitule=intitule).first()
            if formation is None:
                lignes.append(f"WARNING existant attendu absent : « {intitule} ».")
                c["WARNING"] += 1
                continue
            maj = self._completer_nulls(formation, td, dom, men, dur, nb_sem, nb_cred)
            if maj:
                lignes.append(f"UPDATED existant « {intitule} » : {', '.join(maj)}.")
                c["UPDATED"] += 1
            else:
                c["EXISTING"] += 1
        lignes.append("SKIPPED UE/ECUE/codes/parcours/affectations : 0 documente (A-4.5).")
        c["SKIPPED"] += 1
        lignes.append("SKIPPED modules P5 : non transformes en UE/ECUE.")
        c["SKIPPED"] += 1
        lignes.append("SKIPPED duree D9 : NULL (non resolue).")
        c["SKIPPED"] += 1

    @staticmethod
    def _completer_nulls(formation, td, dom, men, dur, nb_sem, nb_cred):
        maj = []
        mapping = {"type_diplome": td, "domaine": dom, "mention": men}
        for champ, valeur in mapping.items():
            if valeur and not getattr(formation, champ):
                setattr(formation, champ, valeur)
                maj.append(champ)
        if dur is not None and formation.duree_annees is None:
            formation.duree_annees = dur
            maj.append("duree_annees")
        if nb_sem is not None and formation.nb_semestres is None:
            formation.nb_semestres = nb_sem
            maj.append("nb_semestres")
        if nb_cred is not None and formation.nb_credites is None:
            formation.nb_credites = nb_cred
            maj.append("nb_credites")
        if maj:
            formation.save(update_fields=maj)
        return maj

    def _regles(self, c, lignes):
        for formation in RefFormation.objects.all():
            _, cree = RegleValidationLMD.objects.get_or_create(
                ref_formation=formation, niveau=None,
                defaults={"seuil_admission": 10, "compensation": "SEMESTRE",
                          "credits_semestre": 30, "capitalisation_activee": True},
            )
            if cree:
                c["CREATED"] += 1
            else:
                c["EXISTING"] += 1
        lignes.append("Regles LMD par defaut : 30 ECTS/semestre (ventilation UE/ECUE non inventee).")
