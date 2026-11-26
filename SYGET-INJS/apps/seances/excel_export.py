"""Exports Excel des séances (groupe ou formation)."""

import datetime
from collections import Counter, defaultdict
from io import BytesIO
from typing import Optional

import openpyxl

from apps.parametrage.services import (
    volume_horaire_effectif_formation_module,
    volume_horaire_effectif_formation_module_pour_dispatch,
)

from .models import Seance
from .repositories import SeanceRepository


class ExportSeancesService:
    """Génère des exports Excel des séances (groupe ou formation)."""

    def __init__(self, repo: SeanceRepository) -> None:
        self._repo = repo

    def exporter(self, groupe_id: int, format_export: str = "cours") -> bytes:
        """
        Retourne le contenu XLSX des séances d'un groupe.
        format_export:
          - "cours" : onglet "Formations" uniquement
          - "seances" : onglet "Séances" uniquement (colonnes grade / groupe en fin de ligne)
          - "formateurs" : onglet "Formateurs" (formateur / grade / groupe / date / module)
        """
        seances = self._repo.list_by_groupe(groupe_id)
        return self._exporter_depuis_seances(
            seances,
            format_export=format_export,
            groupe_ids_fallback=[groupe_id],
        )

    def exporter_par_formation(self, formation_id: int, format_export: str = "cours") -> bytes:
        """
        Retourne le contenu XLSX des séances de tous les groupes d'une formation.
        format_export:
          - "cours" : onglet "Formations" uniquement
          - "seances" : onglet "Séances" uniquement (colonnes grade / groupe en fin de ligne)
          - "formateurs" : onglet "Formateurs" (formateur / grade / groupe / date / module)
        """
        seances = self._repo.list_by_formation(formation_id)
        return self._exporter_depuis_seances(
            seances,
            format_export=format_export,
            formation_id=formation_id,
        )

    def _exporter_depuis_seances(
        self,
        seances: list[Seance],
        format_export: str = "cours",
        *,
        formation_id: Optional[int] = None,
        groupe_ids_fallback: Optional[list[int]] = None,
    ) -> bytes:
        """
        Construit le classeur d'export à partir d'une liste de séances.

        Export « formateurs » : lignes issues des champs formateur des séances, complétées par les
        ``AffectationFormateurGroupe`` des mêmes groupes (utile si le planning n'a pas encore
        recopié l'identité sur les séances). Colonne **Date** : jour de la séance si la ligne vient
        d'une séance avec formateur renseigné ; pour une ligne issue d'une affectation seule,
        ``date_debut`` puis ``date_fin`` du ``FormationModule``, sinon la date la plus tôt parmi
        les séances du groupe sur ce module, sinon la date de début de la formation.
        """

        from apps.formations.models import AffectationFormateurGroupe, FormationModule
        from apps.groupes.models import Groupe

        format_export = (format_export or "cours").strip().lower()
        # "complet" est conservé en compatibilité et redirigé vers "cours".
        if format_export == "complet":
            format_export = "cours"
        if format_export not in {"cours", "seances", "formateurs"}:
            format_export = "cours"

        entetes = [
            "Module (titre)",
            "date_journee",
            "N°",
            "intitule",
            "heure_debut",
            "heure_fin",
            "grade",
            "groupe",
        ]
        entetes_formateurs = [
            "Numéro",
            "Nom",
            "Prénom",
            "E-mail",
            "Téléphone",
            "Organisation",
            "Spécialité",
            "Grade",
            "Groupe",
            "Date",
            "module_titre",
        ]

        seance_groupe_ids = sorted({s.groupe_id for s in seances}) if seances else []
        fallback_ids = list(groupe_ids_fallback or [])
        if format_export == "formateurs":
            groupe_ids_union = sorted(set(seance_groupe_ids) | set(fallback_ids))
            if not seance_groupe_ids and formation_id is not None:
                groupe_ids_union = sorted(Groupe.objects.filter(formation_id=formation_id).values_list("pk", flat=True))
        else:
            groupe_ids_union = seance_groupe_ids

        formation_ids_pour_fm: set[int] = set()
        if formation_id is not None:
            formation_ids_pour_fm.add(formation_id)
        if seances:
            formation_ids_pour_fm.update(s.groupe.formation_id for s in seances)
        if groupe_ids_union:
            formation_ids_pour_fm.update(
                Groupe.objects.filter(pk__in=groupe_ids_union).values_list("formation_id", flat=True)
            )
        date_ref_fm_par_formation_module: dict[tuple[int, int], datetime.date] = {}
        if formation_ids_pour_fm:
            for fm in (
                FormationModule.objects.filter(formation_id__in=formation_ids_pour_fm)
                .only("formation_id", "module_id", "date_debut", "date_fin", "pk")
                .order_by("formation_id", "module_id", "date_debut", "pk")
            ):
                key_fm = (fm.formation_id, fm.module_id)
                if key_fm in date_ref_fm_par_formation_module:
                    continue
                ref = fm.date_debut or fm.date_fin
                if ref is not None:
                    date_ref_fm_par_formation_module[key_fm] = ref

        seance_date_min_par_groupe_module: dict[tuple[int, int], datetime.date] = {}
        if seances:
            for s in seances:
                key_gs = (s.groupe_id, s.module_id)
                d = s.date
                ex = seance_date_min_par_groupe_module.get(key_gs)
                if ex is None or d < ex:
                    seance_date_min_par_groupe_module[key_gs] = d

        grades_par_groupe: dict[int, str] = {}
        if groupe_ids_union:
            for groupe in (
                Groupe.objects.filter(pk__in=groupe_ids_union).prefetch_related("membres__auditeur").only("pk", "nom")
            ):
                grades = [
                    (m.auditeur.grade or "").strip().upper()
                    for m in groupe.membres.all()
                    if (m.auditeur.grade or "").strip()
                ]
                grades_par_groupe[groupe.pk] = Counter(grades).most_common(1)[0][0] if grades else ""

        lignes: list[list] = []
        if seances:
            # Numérotation des séances à la journée (1,2,...) par groupe.
            seances_par_groupe_date: dict[tuple[int, datetime.date], list[Seance]] = defaultdict(list)
            for seance in seances:
                seances_par_groupe_date[(seance.groupe_id, seance.date)].append(seance)
            numero_par_seance: dict[int, int] = {}
            for groupe_date in sorted(seances_par_groupe_date.keys(), key=lambda x: (x[0], x[1])):
                jour = sorted(
                    seances_par_groupe_date[groupe_date],
                    key=lambda s: (s.heure_debut, s.heure_fin),
                )
                for idx, seance in enumerate(jour, start=1):
                    numero_par_seance[seance.pk] = idx

            lignes = [
                [
                    s.module.titre,
                    datetime.datetime.combine(s.date, datetime.time(0, 0)),
                    numero_par_seance.get(s.pk, 1),
                    f"{s.heure_debut.strftime('%H:%M')}-{s.heure_fin.strftime('%H:%M')}",
                    s.heure_debut,
                    s.heure_fin,
                    grades_par_groupe.get(s.groupe_id, ""),
                    self._libelle_groupe_export(
                        (s.groupe.nom or "").strip(),
                        grades_par_groupe.get(s.groupe_id, ""),
                    ),
                ]
                for s in seances
            ]

        # Cache des spécialités du référentiel Formateur, indexé par numero (clé d'unicité).
        from apps.formations.models import Formateur as _FormateurRef

        specialites_par_numero: dict[str, str] = {}
        numeros_a_resoudre: set[str] = set()
        if seances:
            numeros_a_resoudre.update(
                (s.formateur_numero or "").strip() for s in seances if (s.formateur_numero or "").strip()
            )
        if format_export == "formateurs" and numeros_a_resoudre:
            for f_ref in _FormateurRef.objects.filter(numero__in=numeros_a_resoudre).prefetch_related("specialites"):
                libelles = [(sp.libelle or "").strip() for sp in f_ref.specialites.all() if (sp.libelle or "").strip()]
                specialites_par_numero[f_ref.numero] = ", ".join(sorted(set(libelles)))

        uniques: set[tuple] = set()
        if seances:
            for s in seances:
                nom = (s.formateur_nom or "").strip()
                prenom = (s.formateur_prenom or "").strip()
                numero = (s.formateur_numero or "").strip()
                email = (s.formateur_email or "").strip()
                telephone = (s.formateur_telephone or "").strip()
                organisation = (s.formateur_organisation or "").strip()
                if not nom:
                    continue
                specialite = specialites_par_numero.get(numero, "")
                grade_groupe = grades_par_groupe.get(s.groupe_id, "")
                nom_groupe = self._libelle_groupe_export((s.groupe.nom or "").strip(), grade_groupe)
                uniques.add(
                    (
                        numero,
                        nom,
                        prenom,
                        email,
                        telephone,
                        organisation,
                        specialite,
                        grade_groupe,
                        nom_groupe,
                        s.date,
                        s.module.titre,
                    )
                )

        if format_export == "formateurs" and groupe_ids_union:
            for aff in (
                AffectationFormateurGroupe.objects.filter(groupe_id__in=groupe_ids_union)
                .select_related("formateur", "module", "groupe", "groupe__formation")
                .prefetch_related("formateur__specialites")
                .order_by("groupe__nom", "formateur__nom", "formateur__prenom", "module__titre")
            ):
                f = aff.formateur
                nom = (f.nom or "").strip()
                if not nom:
                    continue
                numero = (f.numero or "").strip()
                prenom = (f.prenom or "").strip()
                email = (f.email or "").strip()
                telephone = (f.telephone or "").strip()
                organisation = (f.organisation or "").strip()
                libelles_spec = [(sp.libelle or "").strip() for sp in f.specialites.all() if (sp.libelle or "").strip()]
                specialite = ", ".join(sorted(set(libelles_spec)))
                if numero and numero not in specialites_par_numero:
                    specialites_par_numero[numero] = specialite
                grade_groupe = grades_par_groupe.get(aff.groupe_id, "")
                nom_groupe = self._libelle_groupe_export((aff.groupe.nom or "").strip(), grade_groupe)
                d_row = seance_date_min_par_groupe_module.get((aff.groupe_id, aff.module_id))
                if d_row is None:
                    d_row = date_ref_fm_par_formation_module.get((aff.groupe.formation_id, aff.module_id))
                if d_row is None:
                    d_row = aff.groupe.formation.date_debut
                uniques.add(
                    (
                        numero,
                        nom,
                        prenom,
                        email,
                        telephone,
                        organisation,
                        specialite,
                        grade_groupe,
                        nom_groupe,
                        d_row,
                        (aff.module.titre or "").strip(),
                    )
                )

        def _cle_tri_formateur(t: tuple) -> tuple:
            num, nom, prenom, em, tel, org, spec, gr, grp, dt, mod = t
            dt_k = dt if isinstance(dt, datetime.date) else datetime.date.min
            # Date avant le module : ordre lisible (planning), pas l’ordre alphabétique des intitulés.
            return (grp, dt_k, nom, prenom, mod or "", num or "")

        lignes_formateurs = [list(item) for item in sorted(uniques, key=_cle_tri_formateur)]

        if format_export == "seances":
            wb = openpyxl.Workbook()
            ws_seances = wb.active
            ws_seances.title = "Séances"
            ws_seances.append(entetes)
            for ligne in lignes:
                ws_seances.append(ligne)
            buffer = BytesIO()
            wb.save(buffer)
            return buffer.getvalue()

        if format_export == "formateurs":
            wb = openpyxl.Workbook()
            ws_formateurs = wb.active
            ws_formateurs.title = "Formateurs"
            ws_formateurs.append(entetes_formateurs)
            for ligne in lignes_formateurs:
                ws_formateurs.append(ligne)
            buffer = BytesIO()
            wb.save(buffer)
            return buffer.getvalue()

        if not seances:
            # Classeur minimal conforme, même sans données, en mode "cours".
            wb = openpyxl.Workbook()
            ws_formations = wb.active
            ws_formations.title = "Formations"
            ws_formations.append(
                [
                    "N°",
                    "Formation",
                    "Module (titre)",
                    "Site",
                    "Bâtiment",
                    "Salle",
                    "Date début",
                    "Date fin",
                    "Volume horaire (h)",
                    "Catégorie",
                    "Grade",
                    "Groupe",
                    "Vague",
                ]
            )
            buffer = BytesIO()
            wb.save(buffer)
            return buffer.getvalue()

        formation = seances[0].groupe.formation

        # Prépare l'onglet "Formations" selon le format de référence.
        seances_par_module_groupe: dict[tuple[int, int], list[Seance]] = defaultdict(list)
        for seance in seances:
            seances_par_module_groupe[(seance.groupe_id, seance.module_id)].append(seance)

        formation_modules = list(
            FormationModule.objects.filter(formation_id=formation.pk)
            .select_related("module")
            .order_by("date_debut", "module__titre")
        )

        groupes = {
            s.groupe_id: s.groupe for s in sorted(seances, key=lambda seance: (seance.groupe.nom, seance.groupe_id))
        }
        lignes_formations: list[list] = []
        idx_ligne = 1
        for groupe_id, groupe in groupes.items():
            grade_principal = grades_par_groupe.get(groupe_id, "")
            categorie = (
                f"{formation.type_formation.code} {grade_principal[:1]}".strip()
                if grade_principal
                else formation.type_formation.code
            )
            for fm in formation_modules:
                seances_module = sorted(
                    seances_par_module_groupe.get((groupe_id, fm.module_id), []),
                    key=lambda s: (s.date, s.heure_debut, s.heure_fin),
                )
                if seances_module:
                    dt_debut = datetime.datetime.combine(
                        seances_module[0].date,
                        seances_module[0].heure_debut,
                    )
                    dt_fin = datetime.datetime.combine(
                        seances_module[-1].date,
                        seances_module[-1].heure_fin,
                    )
                else:
                    date_debut = fm.date_debut or formation.date_debut
                    date_fin = fm.date_fin or formation.date_fin
                    dt_debut = datetime.datetime.combine(date_debut, datetime.time(8, 0))
                    dt_fin = datetime.datetime.combine(date_fin, datetime.time(17, 0))

                site_l, bat_l, salle_l = self._lieux_pour_ligne_export(fm, seances_module)

                lignes_formations.append(
                    [
                        idx_ligne,
                        formation.intitule,
                        fm.module.titre,
                        site_l,
                        bat_l,
                        salle_l,
                        dt_debut,
                        dt_fin,
                        self._volume_horaire_ligne_onglet_formations(
                            fm,
                            formation,
                            grade_principal,
                        ),
                        categorie,
                        grade_principal,
                        self._libelle_groupe_export(groupe.nom, grade_principal),
                        formation.vague,
                    ]
                )
                idx_ligne += 1

        # Génère un classeur avec uniquement l'onglet "Formations".
        wb = openpyxl.Workbook()
        ws_formations = wb.active
        ws_formations.title = "Formations"
        ws_formations.append(
            [
                "N°",
                "Formation",
                "Module (titre)",
                "Site",
                "Bâtiment",
                "Salle",
                "Date début",
                "Date fin",
                "Volume horaire (h)",
                "Catégorie",
                "Grade",
                "Groupe",
                "Vague",
            ]
        )
        for ligne in lignes_formations:
            ws_formations.append(ligne)

        buffer = BytesIO()
        wb.save(buffer)
        return buffer.getvalue()

    def _lieux_pour_ligne_export(self, fm, seances_module: list) -> tuple[str, str, str]:
        """
        Site / bâtiment / salle pour l'onglet « Formations ».

        Les séances planifiées portent les lieux réels ; le ``FormationModule`` sert de repli
        (souvent ``salle_nom`` vide sur le module alors que les ``Seance`` sont renseignées).
        """
        if seances_module:

            def first_lieu(getter) -> str:
                for s in seances_module:
                    v = getter(s)
                    if (v or "").strip():
                        return self._premier_nom(v)
                return ""

            salles: list[str] = []
            vues: set[str] = set()
            for s in seances_module:
                sn = (s.salle_nom or "").strip()
                if not sn:
                    continue
                cle = sn.upper()
                if cle not in vues:
                    vues.add(cle)
                    salles.append(sn)

            site = first_lieu(lambda s: s.site_nom) or self._premier_nom(fm.site_nom)
            batiment = first_lieu(lambda s: s.batiment_nom) or self._premier_nom(fm.batiment_nom)
            salle = ", ".join(salles) if salles else self._premier_nom(fm.salle_nom)
            return site, batiment, salle

        return (
            self._premier_nom(fm.site_nom),
            self._premier_nom(fm.batiment_nom),
            self._premier_nom(fm.salle_nom),
        )

    @staticmethod
    def _volume_horaire_ligne_onglet_formations(fm, formation, grade_principal: str) -> int:
        """
        Volume horaire affiché dans l'export « Formations ».

        Le dispatch planning peut refuser un couple groupe / module (``pour_dispatch`` → ``None``)
        même lorsqu'un volume est saisi sur le module de formation ; l'export doit tout de même
        refléter ce volume explicite, puis à défaut le paramétrage type × module (repli affichage).
        """
        if fm.volume_horaire is not None:
            return int(fm.volume_horaire)
        v = volume_horaire_effectif_formation_module_pour_dispatch(
            fm.module_id,
            None,
            formation.type_formation_id,
            grade_principal,
            fm.module.titre,
        )
        if v is not None:
            return int(v)
        try:
            return int(
                volume_horaire_effectif_formation_module(
                    fm.module_id,
                    None,
                    formation.type_formation_id,
                    grade_principal,
                    fm.module.titre,
                )
            )
        except ValueError:
            return 0

    @staticmethod
    def _premier_nom(valeur: str) -> str:
        """Retourne le premier nom d'une liste CSV, sinon chaîne vide."""
        noms = [v.strip() for v in (valeur or "").split(",") if v.strip()]
        return noms[0] if noms else ""

    @staticmethod
    def _libelle_groupe_export(nom_groupe: str, grade: str) -> str:
        from shared.utils.groupes import libelle_groupe_export

        return libelle_groupe_export(nom_groupe, grade)

    def exporter_formation_zip(self, formation_id: int, format_export: str = "cours") -> bytes:
        """
        Retourne une archive ZIP contenant un fichier Excel par groupe
        (``A4_EMP_GROUPE1.xlsx``, etc.).
        """
        import zipfile
        from io import BytesIO

        from apps.groupes.models import Groupe
        from shared.utils.groupes import nom_fichier_emploi_du_temps

        format_export = (format_export or "cours").strip().lower()
        if format_export == "complet":
            format_export = "cours"
        if format_export not in {"cours", "seances", "formateurs"}:
            format_export = "cours"

        buffer = BytesIO()
        groupes = list(
            Groupe.objects.filter(formation_id=formation_id)
            .select_related("formation")
            .prefetch_related("membres__auditeur")
            .order_by("nom", "pk")
        )
        variante = format_export if format_export in {"seances", "formateurs"} else ""
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for groupe in groupes:
                contenu = self.exporter(groupe.pk, format_export=format_export)
                nom_fichier = nom_fichier_emploi_du_temps(
                    groupe=groupe,
                    extension="xlsx",
                    variante=variante,
                )
                archive.writestr(nom_fichier, contenu)
        return buffer.getvalue()
