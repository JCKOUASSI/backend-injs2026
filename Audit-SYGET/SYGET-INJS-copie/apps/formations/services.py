"""
Services de l'app formations.
Logique métier pour la gestion des formations et de leurs modules.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Optional

from django.db import transaction

from shared.utils.grades import encode_grade_cibles, split_grade_cibles
from shared.utils.groupes import nom_groupe_sans_grade

from .models import (
    Formateur,
    Formation,
    FormationModule,
    FormationPeriode,
    Inscription,
)
from .repositories import (
    FormationModuleRepository,
    FormationRepository,
    InscriptionRepository,
)


@dataclass
class ImportFormateursReport:
    """Rapport d'import des formateurs."""

    nb_lignes: int = 0
    nb_formateurs_importes: int = 0
    nb_formateurs_mis_a_jour: int = 0
    nb_erreurs: int = 0
    erreurs: list[str] = None

    def __post_init__(self):
        if self.erreurs is None:
            self.erreurs = []


class FormationService:
    """Logique métier pour la gestion des formations."""

    def __init__(
        self,
        repo: FormationRepository,
        module_repo: FormationModuleRepository,
    ) -> None:
        self._repo = repo
        self._module_repo = module_repo

    def _volume_horaire_stocke_depuis_parametrage(
        self, formation: Formation, module_id: int, grade_cible: str
    ) -> int | None:
        """
        Volume à enregistrer sur FormationModule (heures ou None).

        None : volumes différents selon les grades au paramétrage — le planning résoudra
        pour chaque groupe via type × module × grade.
        """
        from apps.parametrage.models import ModuleTypeFormation
        from apps.parametrage.services import resolve_module_type_formation_association

        assoc_qs = ModuleTypeFormation.objects.filter(
            module_id=module_id,
            type_formation_id=formation.type_formation_id,
        )
        grades_cibles = split_grade_cibles(grade_cible)
        if grades_cibles:
            assoc_par_grade = []
            for grade in grades_cibles:
                assoc = resolve_module_type_formation_association(assoc_qs, grade, allow_generic_fallback=True)
                if assoc is None:
                    raise ValueError(f"Volume horaire introuvable dans le paramétrage pour le grade {grade}.")
                assoc_par_grade.append(assoc)
            volumes = {a.volume_horaire_defaut for a in assoc_par_grade}
            if len(volumes) > 1:
                return None
            return int(assoc_par_grade[0].volume_horaire_defaut)

        specifications = list(assoc_qs.exclude(grade_cible=""))
        vols_spec = {s.volume_horaire_defaut for s in specifications}
        if len(vols_spec) > 1:
            return None
        if len(vols_spec) == 1:
            return int(next(iter(vols_spec)))

        generic = assoc_qs.filter(grade_cible="").first()
        if generic is None:
            raise ValueError("Volume horaire introuvable dans le paramétrage pour ce module et ce type de formation.")
        return int(generic.volume_horaire_defaut)

    @staticmethod
    def _join_noms_pour_stockage(noms: list[str], field_name: str, libelle: str) -> str:
        """
        Joint une liste de noms en CSV et valide la longueur du champ cible.
        """
        joined = ", ".join(noms)
        max_len = FormationModule._meta.get_field(field_name).max_length or 0
        if max_len and len(joined) > max_len:
            raise ValueError(
                f"La liste des {libelle} est trop longue ({len(joined)} caractères, max {max_len}). "
                "Réduisez la sélection."
            )
        return joined

    def get_all(self) -> list[Formation]:
        """Retourne toutes les formations."""
        return self._repo.list_all()

    def get_by_id(self, pk: int) -> Formation:
        """
        Retourne une formation par pk.
        Lève ValueError si introuvable.
        """
        f = self._repo.get_by_id(pk)
        if f is None:
            raise ValueError(f"Formation {pk} introuvable.")
        return f

    @transaction.atomic
    def creer(
        self,
        type_formation_id: int,
        intitule: str,
        vague: str,
        date_debut,
        date_fin,
        *,
        rythme_mensuel: str = Formation.RythmeMensuel.TOUT_LE_MOIS,
        responsable=None,
    ) -> Formation:
        """Crée une nouvelle formation."""
        if date_fin < date_debut:
            raise ValueError("La date de fin doit être postérieure à la date de début.")
        formation = Formation(
            type_formation_id=type_formation_id,
            intitule=intitule.strip(),
            vague=vague.strip(),
            date_debut=date_debut,
            date_fin=date_fin,
            rythme_mensuel=rythme_mensuel or Formation.RythmeMensuel.TOUT_LE_MOIS,
            planning_union_sites_programme=False,
            responsable=responsable,
        )
        formation = self._repo.save(formation)
        from apps.parametrage.models import ParametreFormation

        ParametreFormation.creer_depuis_generaux(formation)
        FormationPeriode.objects.create(
            formation=formation,
            libelle="Période 1",
            date_debut=date_debut,
            date_fin=date_fin,
            rythme_mensuel=formation.rythme_mensuel,
            ordre=0,
        )
        return formation

    @staticmethod
    def _get_periode(formation_id: int, periode_id: int) -> FormationPeriode:
        periode = FormationPeriode.objects.filter(formation_id=formation_id, pk=periode_id).first()
        if periode is None:
            raise ValueError("Période introuvable pour cette formation.")
        return periode

    @staticmethod
    def _resolve_periode(formation_id: int, periode_id: int | None) -> FormationPeriode:
        if periode_id:
            return FormationService._get_periode(formation_id, periode_id)
        periode = (
            FormationPeriode.objects.filter(formation_id=formation_id).order_by("ordre", "date_debut", "pk").first()
        )
        if periode is None:
            raise ValueError("Aucune période définie pour cette formation.")
        return periode

    @transaction.atomic
    def ajouter_periode(
        self,
        formation_id: int,
        libelle: str,
        date_debut,
        date_fin,
        *,
        rythme_mensuel: str = Formation.RythmeMensuel.TOUT_LE_MOIS,
    ) -> FormationPeriode:
        """Ajoute une période pédagogique à une formation."""
        formation = self._repo.get_by_id(formation_id)
        if formation is None:
            raise ValueError(f"Formation {formation_id} introuvable.")
        if date_fin < date_debut:
            raise ValueError("La date de fin de la période doit être postérieure à sa date de début.")
        ordre = FormationPeriode.objects.filter(formation_id=formation_id).count()
        return FormationPeriode.objects.create(
            formation_id=formation_id,
            libelle=(libelle or "").strip() or f"Période {ordre + 1}",
            date_debut=date_debut,
            date_fin=date_fin,
            rythme_mensuel=rythme_mensuel or Formation.RythmeMensuel.TOUT_LE_MOIS,
            ordre=ordre,
        )

    @transaction.atomic
    def modifier_periode(
        self,
        periode_id: int,
        formation_id: int,
        libelle: str,
        date_debut,
        date_fin,
        *,
        rythme_mensuel: str = Formation.RythmeMensuel.TOUT_LE_MOIS,
    ) -> FormationPeriode:
        """Met à jour une période et resynchronise les dates des modules rattachés."""
        periode = self._get_periode(formation_id, periode_id)
        if date_fin < date_debut:
            raise ValueError("La date de fin de la période doit être postérieure à sa date de début.")
        periode.libelle = (libelle or "").strip() or periode.libelle
        periode.date_debut = date_debut
        periode.date_fin = date_fin
        periode.rythme_mensuel = rythme_mensuel or Formation.RythmeMensuel.TOUT_LE_MOIS
        periode.save()
        FormationModule.objects.filter(periode_id=periode.pk).update(date_debut=date_debut, date_fin=date_fin)
        return periode

    @transaction.atomic
    def supprimer_periode(self, formation_id: int, periode_id: int) -> None:
        """Supprime une période sans module ; refuse si des modules y sont encore rattachés."""
        periode = self._get_periode(formation_id, periode_id)
        if FormationModule.objects.filter(periode_id=periode.pk).exists():
            raise ValueError("Impossible de supprimer une période qui contient encore des modules.")
        nb_periodes = FormationPeriode.objects.filter(formation_id=formation_id).count()
        if nb_periodes <= 1:
            raise ValueError("La formation doit conserver au moins une période.")
        periode.delete()

    @transaction.atomic
    def modifier(
        self,
        formation_id: int,
        type_formation_id: int,
        intitule: str,
        vague: str,
        date_debut,
        date_fin,
        *,
        rythme_mensuel: str = Formation.RythmeMensuel.TOUT_LE_MOIS,
    ) -> Formation:
        """
        Met à jour les informations générales d'une formation.
        Les périodes des modules ne contraignent plus ces dates : le calendrier effectif
        est porté par chaque module ; la génération de planning vérifie les disponibilités.
        """
        formation = self._repo.get_by_id(formation_id)
        if formation is None:
            raise ValueError(f"Formation {formation_id} introuvable.")
        if date_fin < date_debut:
            raise ValueError("La date de fin doit être postérieure à la date de début.")

        formation.type_formation_id = type_formation_id
        formation.intitule = intitule.strip()
        formation.vague = (vague or "").strip()
        formation.date_debut = date_debut
        formation.date_fin = date_fin
        formation.rythme_mensuel = rythme_mensuel or Formation.RythmeMensuel.TOUT_LE_MOIS
        formation.planning_union_sites_programme = False
        return self._repo.save(formation)

    @transaction.atomic
    def supprimer(self, formation_id: int) -> None:
        """Supprime une formation existante."""
        formation = self._repo.get_by_id(formation_id)
        if formation is None:
            raise ValueError(f"Formation {formation_id} introuvable.")
        self._repo.delete(formation_id)

    @transaction.atomic
    def importer_formateurs_depuis_excel(
        self,
        fichier,
    ) -> ImportFormateursReport:
        """
        Importe le référentiel global des formateurs depuis un Excel (.xlsx).
        Colonnes **obligatoires** sur la ligne d'en-têtes et sur chaque ligne de données :
        **numero**, **nom**, **prenom**.

        Champs optionnels : email, telephone, organisation ; **specialites** (codes séparés par virgule
        ou point-virgule) ou **module_titre** pour déduire la spécialité — à défaut la spécialité **GENERAL**
        est appliquée.

        L'import ne crée pas d'affectation groupe/module : le rattachement se fait ensuite
        (page « Mon module » pour les RUP, ou génération automatique des groupes).
        """
        import openpyxl

        report = ImportFormateursReport()

        def _normalize_header(name: str) -> str:
            raw = str(name or "").replace("\ufeff", "").strip()
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

        aliases = {
            "numero": "numero",
            "no": "numero",
            "matricule": "numero",
            "n_inscription": "numero",
            "numero_inscription": "numero",
            "n_d_inscription": "numero",
            "numero_formateur": "numero",
            "no_formateur": "numero",
            "id_formateur": "numero",
            "telephone": "telephone",
            "telephone_1": "telephone",
            "tel": "telephone",
            "portable": "telephone",
            "telephone_formateur": "telephone",
            "telephone_2": "telephone",
            "gsm": "telephone",
            "mobile": "telephone",
            "tel_portable": "telephone",
            "telephone_portable": "telephone",
            "numero_de_telephone": "telephone",
            "nom": "nom",
            "nom_de_famille": "nom",
            "prenom": "prenom",
            "prenoms": "prenom",
            "prenom_s": "prenom",
            "prenom_usuel": "prenom",
            "email": "email",
            "e_mail": "email",
            "mail": "email",
            "courriel": "email",
            "adresse_email": "email",
            "adresse_mail": "email",
            "mail_pro": "email",
            "organisation": "organisation",
            "organisme": "organisation",
            "structure": "organisation",
            "employeur": "organisation",
            "societe": "organisation",
            "entreprise": "organisation",
            "module_titre": "module_titre",
            "module": "module_titre",
            "titre_module": "module_titre",
            "intitule_module": "module_titre",
            "libelle_module": "module_titre",
            "nom_module": "module_titre",
            "groupe": "groupe",
            "groupe_nom": "groupe",
            "nom_groupe": "groupe",
            "libelle_groupe": "groupe",
            "specialites": "specialites",
            "specialite": "specialites",
            "specialites_codes": "specialites",
            "codes_specialites": "specialites",
            "domaines": "specialites",
            "domaine": "specialites",
        }

        required_base = {"numero", "nom", "prenom"}
        # Colonnes reconnues sur la ligne d'en-tête (les autres sont optionnelles).
        header_recognized = required_base | {
            "email",
            "telephone",
            "organisation",
            "specialites",
            "module_titre",
            "groupe",
        }
        max_header_scan = 100

        def _header_indices(header_cells: list) -> dict[str, int] | None:
            idx_map: dict[str, int] = {}
            for idx, h in enumerate(header_cells):
                raw = h
                if raw is not None and hasattr(raw, "item"):
                    try:
                        raw = raw.item()
                    except Exception:
                        pass
                canon = aliases.get(_normalize_header(raw), _normalize_header(raw))
                if canon not in header_recognized or canon in idx_map:
                    continue
                idx_map[canon] = idx
            if not required_base.issubset(idx_map.keys()):
                return None
            return idx_map

        def _find_header_row(rows: list) -> tuple[int, dict[str, int]] | None:
            max_scan = min(max_header_scan, len(rows))
            for i in range(max_scan):
                raw_row = rows[i]
                row = list(raw_row) if raw_row is not None else []
                idx_map = _header_indices(row)
                if idx_map is not None:
                    return i, idx_map
            return None

        def _cell_to_str(value) -> str:
            if value is None:
                return ""
            if isinstance(value, float) and value == int(value):
                value = int(value)
            text = str(value).strip()
            return "" if text.upper() == "NAN" else text

        def _val(row: list, idx_map: dict[str, int], key: str) -> str:
            idx = idx_map.get(key)
            if idx is None or idx >= len(row):
                return ""
            return _cell_to_str(row[idx])

        try:
            fichier.seek(0)
            wb = openpyxl.load_workbook(fichier, data_only=True)
        except Exception as e:
            report.nb_erreurs += 1
            report.erreurs.append(f"Impossible de lire le fichier Excel (.xlsx) : {e}")
            return report

        rows: list | None = None
        found: tuple[int, dict[str, int]] | None = None
        had_non_empty_sheet = False
        for ws in wb.worksheets:
            candidate = list(ws.iter_rows(values_only=True))
            if not candidate:
                continue
            had_non_empty_sheet = True
            found_here = _find_header_row(candidate)
            if found_here is not None:
                rows = candidate
                found = found_here
                break

        if not had_non_empty_sheet:
            report.nb_erreurs += 1
            report.erreurs.append("Fichier vide ou sans donnée lisible sur aucune feuille.")
            return report

        if found is None or rows is None:
            report.nb_erreurs += 1
            report.erreurs.append(
                "Ligne d’en-têtes introuvable sur aucune feuille du classeur. Colonnes obligatoires : "
                "**numero**, **nom**, **prenom**. Colonnes optionnelles reconnues : email, telephone, "
                "organisation, specialites, module_titre, etc. "
                f"Les {max_header_scan} premières lignes de chaque feuille sont analysées ; "
                f"placez la ligne des intitulés de colonnes avant la ligne {max_header_scan + 1} "
                "ou déplacez le tableau sur une autre feuille (ex. « Formateurs »)."
            )
            return report

        header_row_idx, idx_map = found

        max_col = max(idx_map.values(), default=-1) + 1

        from apps.referentiels.models import Module, Specialite

        module_cache = list(Module.objects.select_related("specialite").only("titre", "specialite__code"))

        def _match_module_depuis_titre(titre: str):
            vn = (titre or "").strip().upper()
            if not vn:
                return None
            best = None
            best_rank = 99
            for m in module_cache:
                tn = (m.titre or "").strip().upper()
                if not tn:
                    continue
                if tn == vn:
                    rank = 0
                elif tn.startswith(vn):
                    rank = 1
                elif vn.startswith(tn):
                    rank = 2
                else:
                    continue
                if best is None:
                    best = m
                    best_rank = rank
                    continue
                if rank < best_rank:
                    best = m
                    best_rank = rank
                elif rank == best_rank and len(m.titre) < len(best.titre):
                    best = m
            return best

        def _codes_depuis_module(mod) -> list[str]:
            if mod is None:
                return []
            code = (mod.specialite.code or "").strip().upper()
            return [code] if code else []

        nb_module_titre_fallback_general = 0

        valid_rows: list[dict] = []

        for line_no in range(header_row_idx + 1, len(rows)):
            raw_row = rows[line_no]
            row = list(raw_row) if raw_row is not None else []
            if len(row) < max_col:
                row = row + [None] * (max_col - len(row))
            feuille_ligne = line_no + 1  # numéro de ligne « Excel » (1-based)
            if not row or all(_cell_to_str(c) == "" for c in row):
                continue

            nom = _val(row, idx_map, "nom")
            prenom = _val(row, idx_map, "prenom")
            numero = _val(row, idx_map, "numero")
            email = _val(row, idx_map, "email")
            telephone = _val(row, idx_map, "telephone")
            organisation = _val(row, idx_map, "organisation")
            if not nom and not prenom and not numero and not email and not telephone and not organisation:
                continue

            report.nb_lignes += 1
            if not numero or not nom or not prenom:
                report.nb_erreurs += 1
                report.erreurs.append(f"Ligne {feuille_ligne} : numero, nom et prenom sont obligatoires.")
                continue

            brut = _val(row, idx_map, "specialites")
            codes = [p.strip().upper() for p in brut.replace(";", ",").split(",") if p.strip()]
            if not codes:
                titre_mod = _val(row, idx_map, "module_titre")
                tm = titre_mod.strip()
                if tm:
                    mod_obj = _match_module_depuis_titre(tm)
                    if mod_obj:
                        codes = _codes_depuis_module(mod_obj)
                    if not codes:
                        codes = ["GENERAL"]
                        nb_module_titre_fallback_general += 1
            if not codes:
                codes = ["GENERAL"]

            valid_rows.append(
                {
                    "numero": numero,
                    "nom": nom,
                    "prenom": prenom,
                    "email": email,
                    "telephone": telephone,
                    "organisation": organisation,
                    "codes": codes,
                }
            )

        if nb_module_titre_fallback_general > 0:
            report.erreurs.append(
                f"Note : {nb_module_titre_fallback_general} ligne(s) : module_titre sans correspondance "
                "dans le référentiel ; spécialité GENERAL appliquée. Utilisez la colonne specialites ou "
                "des titres identiques aux modules référentiels."
            )

        if not valid_rows:
            return report

        # Dernière ligne gagne pour un même numéro (évite milliers de requêtes ligne à ligne).
        by_numero: dict[str, dict] = {}
        for item in valid_rows:
            by_numero[item["numero"]] = item

        numeros = list(by_numero.keys())
        numeros_existants = set(Formateur.objects.filter(numero__in=numeros).values_list("numero", flat=True))

        all_codes: set[str] = set()
        for item in by_numero.values():
            all_codes.update(item["codes"])

        existing_spec_codes = set(Specialite.objects.filter(code__in=all_codes).values_list("code", flat=True))
        missing_codes = sorted(all_codes - existing_spec_codes)
        if missing_codes:
            Specialite.objects.bulk_create([Specialite(code=c, libelle=c) for c in missing_codes])

        spec_map = {s.code.upper(): s for s in Specialite.objects.filter(code__in=all_codes)}

        existing_formateurs = {f.numero: f for f in Formateur.objects.filter(numero__in=numeros)}
        to_create: list[Formateur] = []
        to_update: list[Formateur] = []

        for numero, item in by_numero.items():
            defaults = {
                "nom": item["nom"],
                "prenom": item["prenom"],
                "email": item["email"],
                "telephone": item["telephone"],
                "organisation": item["organisation"],
            }
            if numero in existing_formateurs:
                obj = existing_formateurs[numero]
                for key, val in defaults.items():
                    setattr(obj, key, val)
                to_update.append(obj)
            else:
                to_create.append(Formateur(numero=numero, **defaults))

        Formateur.objects.bulk_create(to_create)
        Formateur.objects.bulk_update(
            to_update,
            fields=["nom", "prenom", "email", "telephone", "organisation"],
        )

        formateurs_by_numero = {f.numero: f for f in Formateur.objects.filter(numero__in=numeros)}

        Through = Formateur.specialites.through
        formateur_ids = [formateurs_by_numero[n].pk for n in numeros]
        Through.objects.filter(formateur_id__in=formateur_ids).delete()

        links: list = []
        for numero, item in by_numero.items():
            fid = formateurs_by_numero[numero].pk
            seen_sid: set[int] = set()
            for code in item["codes"]:
                sid = spec_map[code].pk
                if sid not in seen_sid:
                    seen_sid.add(sid)
                    links.append(Through(formateur_id=fid, specialite_id=sid))

        if links:
            Through.objects.bulk_create(links)

        report.nb_formateurs_importes = sum(1 for n in by_numero if n not in numeros_existants)
        report.nb_formateurs_mis_a_jour = sum(1 for n in by_numero if n in numeros_existants)

        return report

    @transaction.atomic
    def ajouter_module(
        self,
        formation_id: int,
        module_id: int,
        volume_horaire: Optional[int] = None,
        grade_cible: str | list[str] = "",
        creneau_mode: str = Formation.CreneauMode.MATIN_ET_SOIR,
        formateur_nom: str = "",
        formateur_prenom: str = "",
        formateur_numero: str = "",
        formateur_email: str = "",
        formateur_telephone: str = "",
        formateur_organisation: str = "",
        periode_id: int | None = None,
        site_noms: Optional[list[str]] = None,
        batiment_noms: Optional[list[str]] = None,
        salle_noms: Optional[list[str]] = None,
    ) -> FormationModule:
        """
        Ajoute un module à une formation.
        Lève ValueError si l'association existe déjà ou si les données sont incohérentes.
        """
        formation = self._repo.get_by_id(formation_id)
        if formation is None:
            raise ValueError(f"Formation {formation_id} introuvable.")
        periode = self._resolve_periode(formation_id, periode_id)
        date_debut = periode.date_debut
        date_fin = periode.date_fin

        site_noms = [s.strip() for s in (site_noms or []) if s.strip()]
        batiment_noms = [b.strip() for b in (batiment_noms or []) if b.strip()]
        salle_noms = [s.strip() for s in (salle_noms or []) if s.strip()]
        grade_cible = encode_grade_cibles(grade_cible)
        if volume_horaire is None:
            volume_horaire = self._volume_horaire_stocke_depuis_parametrage(formation, module_id, grade_cible)
        if not site_noms:
            raise ValueError("Le site doit être renseigné pour ce module.")
        if date_debut and date_fin:
            requested_salles = set(salle_noms)
            creneau_mode = creneau_mode or Formation.CreneauMode.MATIN_ET_SOIR
            for existing in FormationModule.objects.filter(formation_id=formation_id):
                if not existing.date_debut or not existing.date_fin:
                    continue
                if not self._date_ranges_overlap(date_debut, date_fin, existing.date_debut, existing.date_fin):
                    continue
                if not self._creneaux_se_chevauchent(creneau_mode, existing.creneau_mode):
                    continue
                existing_salles = {name.strip() for name in (existing.salle_nom or "").split(",") if name.strip()}
                conflit_salles = requested_salles.intersection(existing_salles)
                if conflit_salles:
                    raise ValueError(
                        "Conflit de salle: "
                        + ", ".join(sorted(conflit_salles))
                        + " est déjà assignée sur cette période pour la formation."
                    )
        fm = FormationModule(
            formation_id=formation_id,
            periode_id=periode.pk,
            module_id=module_id,
            volume_horaire=volume_horaire,
            grade_cible=grade_cible,
            creneau_mode=creneau_mode or Formation.CreneauMode.MATIN_ET_SOIR,
            formateur_nom="",
            formateur_prenom="",
            formateur_numero="",
            formateur_email="",
            formateur_telephone="",
            formateur_organisation="",
            date_debut=date_debut,
            date_fin=date_fin,
            site_nombre=len(site_noms),
            site_nom=self._join_noms_pour_stockage(site_noms, "site_nom", "sites"),
            batiment_nombre=len(batiment_noms),
            batiment_nom=self._join_noms_pour_stockage(batiment_noms, "batiment_nom", "bâtiments"),
            salle_nombre=len(salle_noms),
            salle_nom=self._join_noms_pour_stockage(salle_noms, "salle_nom", "salles"),
        )
        return self._module_repo.save(fm)

    @staticmethod
    def _date_ranges_overlap(start_a, end_a, start_b, end_b) -> bool:
        """Retourne True si deux intervalles de dates se chevauchent."""
        return max(start_a, start_b) <= min(end_a, end_b)

    @staticmethod
    def _creneaux_se_chevauchent(mode_a: str, mode_b: str) -> bool:
        """Retourne True si deux modes de créneau utilisent la salle en même temps."""
        slots = {
            Formation.CreneauMode.MATIN: {"matin"},
            Formation.CreneauMode.SOIR: {"soir"},
            Formation.CreneauMode.MATIN_ET_SOIR: {"matin", "soir"},
        }
        default = Formation.CreneauMode.MATIN_ET_SOIR
        return bool(slots.get(mode_a or default, slots[default]) & slots.get(mode_b or default, slots[default]))

    @transaction.atomic
    def supprimer_module(self, formation_module_id: int) -> None:
        """Supprime un module d'une formation."""
        self._module_repo.delete(formation_module_id)

    @transaction.atomic
    def modifier_module(
        self,
        formation_module_id: int,
        module_id: int,
        volume_horaire: Optional[int] = None,
        grade_cible: str | list[str] = "",
        creneau_mode: str = Formation.CreneauMode.MATIN_ET_SOIR,
        formateur_nom: str = "",
        formateur_prenom: str = "",
        formateur_numero: str = "",
        formateur_email: str = "",
        formateur_telephone: str = "",
        formateur_organisation: str = "",
        periode_id: int | None = None,
        site_noms: Optional[list[str]] = None,
        batiment_noms: Optional[list[str]] = None,
        salle_noms: Optional[list[str]] = None,
    ) -> FormationModule:
        """
        Modifie un module d'une formation avec les mêmes règles que l'ajout.
        """
        fm = FormationModule.objects.select_related("formation", "periode").filter(pk=formation_module_id).first()
        if fm is None:
            raise ValueError(f"Module de formation {formation_module_id} introuvable.")

        formation = fm.formation
        periode = self._resolve_periode(formation.pk, periode_id or fm.periode_id)
        date_debut = periode.date_debut
        date_fin = periode.date_fin

        site_noms = [s.strip() for s in (site_noms or []) if s.strip()]
        batiment_noms = [b.strip() for b in (batiment_noms or []) if b.strip()]
        salle_noms = [s.strip() for s in (salle_noms or []) if s.strip()]
        grade_cible = encode_grade_cibles(grade_cible)

        if volume_horaire is None:
            volume_horaire = self._volume_horaire_stocke_depuis_parametrage(formation, module_id, grade_cible)

        if not site_noms:
            raise ValueError("Le site doit être renseigné pour ce module.")

        if date_debut and date_fin:
            requested_salles = set(salle_noms)
            creneau_mode = creneau_mode or Formation.CreneauMode.MATIN_ET_SOIR
            for existing in FormationModule.objects.filter(formation_id=formation.pk).exclude(pk=fm.pk):
                if not existing.date_debut or not existing.date_fin:
                    continue
                if not self._date_ranges_overlap(date_debut, date_fin, existing.date_debut, existing.date_fin):
                    continue
                if not self._creneaux_se_chevauchent(creneau_mode, existing.creneau_mode):
                    continue
                existing_salles = {name.strip() for name in (existing.salle_nom or "").split(",") if name.strip()}
                conflit_salles = requested_salles.intersection(existing_salles)
                if conflit_salles:
                    raise ValueError(
                        "Conflit de salle: "
                        + ", ".join(sorted(conflit_salles))
                        + " est déjà assignée sur cette période pour la formation."
                    )

        fm.module_id = module_id
        fm.periode_id = periode.pk
        fm.volume_horaire = volume_horaire
        fm.grade_cible = grade_cible
        fm.creneau_mode = creneau_mode or Formation.CreneauMode.MATIN_ET_SOIR
        fm.formateur_nom = ""
        fm.formateur_prenom = ""
        fm.formateur_numero = ""
        fm.formateur_email = ""
        fm.formateur_telephone = ""
        fm.formateur_organisation = ""
        fm.date_debut = date_debut
        fm.date_fin = date_fin
        fm.site_nombre = len(site_noms)
        fm.site_nom = self._join_noms_pour_stockage(site_noms, "site_nom", "sites")
        fm.batiment_nombre = len(batiment_noms)
        fm.batiment_nom = self._join_noms_pour_stockage(batiment_noms, "batiment_nom", "bâtiments")
        fm.salle_nombre = len(salle_noms)
        fm.salle_nom = self._join_noms_pour_stockage(salle_noms, "salle_nom", "salles")
        return self._module_repo.save(fm)


class InscriptionService:
    """Logique métier pour les inscriptions des auditeurs aux formations."""

    def __init__(self, repo: InscriptionRepository, formation_repo: FormationRepository) -> None:
        self._repo = repo
        self._formation_repo = formation_repo

    @transaction.atomic
    def inscrire(self, formation_module_id: int, auditeur_id: int) -> Inscription:
        """
        Inscrit un auditeur à un module de formation.
        Lève ValueError si déjà inscrit à ce module.
        """
        formation_module = FormationModule.objects.select_related("formation").filter(pk=formation_module_id).first()
        if formation_module is None:
            raise ValueError(f"Module de formation {formation_module_id} introuvable.")
        if Inscription.objects.filter(formation_module_id=formation_module_id, auditeur_id=auditeur_id).exists():
            raise ValueError("Cet auditeur est déjà inscrit à ce module.")
        return self._repo.save(
            Inscription(
                formation_id=formation_module.formation_id,
                formation_module_id=formation_module_id,
                auditeur_id=auditeur_id,
            )
        )

    @transaction.atomic
    def desinscrire(self, formation_module_id: int, auditeur_id: int) -> None:
        """Désinscrit un auditeur d'un module."""
        Inscription.objects.filter(formation_module_id=formation_module_id, auditeur_id=auditeur_id).delete()


def _nom_groupe_sans_grade_sur_libelle(nom_groupe: str, grade: str) -> str:
    """Alias historique — voir ``shared.utils.groupes.nom_groupe_sans_grade``."""
    return nom_groupe_sans_grade(nom_groupe, grade)


def _lignes_export_auditeurs_depuis_groupe_auditeurs(ga_rows) -> list:
    """
    Construit les lignes d'export (auditeur, nom groupe affiché, grade-groupe)
    à partir de GroupeAuditeur déjà préchargés (auditeur, groupe).
    """
    from apps.auditeurs.models import Auditeur

    seen: set[int] = set()
    lignes: list[tuple[Auditeur, str, str]] = []
    for ga in ga_rows:
        if ga.auditeur_id in seen:
            continue
        seen.add(ga.auditeur_id)
        nom_brut = (ga.groupe.nom or "").strip()
        grade_a = (ga.auditeur.grade or "").strip()
        groupe_nom = _nom_groupe_sans_grade_sur_libelle(nom_brut, grade_a)
        grade_groupe = f"{grade_a} - {groupe_nom}" if grade_a and groupe_nom else (grade_a or groupe_nom)
        lignes.append((ga.auditeur, groupe_nom, grade_groupe))
    return lignes


def _exporter_auditeurs_xlsx(
    formation: Formation,
    lignes: list,
    *,
    groupe_nom: str | None = None,
) -> bytes:
    """Écrit le classeur XLSX auditeurs (colonnes communes formation / groupe)."""
    from io import BytesIO

    import openpyxl
    from django.utils import timezone
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    from apps.auditeurs.models import Auditeur

    entetes = [
        "N° d'inscription",
        "Nom",
        "Prénoms",
        "Genre",
        "Grade",
        "Catégorie",
        "Type concours",
        "Libellé concours",
        "Email",
        "Téléphone 1",
        "Téléphone 2",
        "Date de naissance",
        "Lieu de naissance",
        "Groupe",
        "Grade-Groupe",
        "Formation(s)",
        "Vague",
    ]
    nb_cols = len(entetes)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Auditeurs"

    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=nb_cols)
    cell_titre = ws.cell(row=1, column=1, value="Export auditeurs")
    cell_titre.font = Font(size=14, bold=True, color="003366")
    cell_titre.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 24

    contexte_parts = [formation.intitule.strip()]
    vague = (formation.vague or "").strip()
    if vague:
        contexte_parts.append(f"Vague {vague}")
    if groupe_nom:
        contexte_parts.append(f"Groupe {groupe_nom.strip()}")
    contexte_parts.append(f"Exporté le {timezone.localdate():%d/%m/%Y}")
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=nb_cols)
    cell_ctx = ws.cell(row=2, column=1, value=" — ".join(contexte_parts))
    cell_ctx.font = Font(size=11, italic=True, color="334155")
    cell_ctx.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[2].height = 18

    header_row = 3
    header_fill = PatternFill(start_color="003366", end_color="003366", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True)
    for col_idx, entete in enumerate(entetes, start=1):
        cell = ws.cell(row=header_row, column=col_idx, value=entete)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    data_row = header_row + 1
    for offset, (a, groupe_nom_ligne, grade_groupe) in enumerate(lignes):
        genre_display = ""
        if a.genre:
            genre_display = dict(Auditeur.Genre.choices).get(a.genre, a.genre)
        row_idx = data_row + offset
        values = [
            a.matricule,
            a.nom,
            a.prenom,
            genre_display,
            (a.grade or "").strip(),
            (a.categorie or "").strip(),
            (a.type_concours or "").strip(),
            (a.libelle_concours or "").strip(),
            (a.email or "").strip(),
            (a.telephone_1 or "").strip(),
            (a.telephone_2 or "").strip(),
            a.date_naissance,
            (a.lieu_naissance or "").strip(),
            groupe_nom_ligne,
            grade_groupe,
            formation.intitule,
            (formation.vague or "").strip(),
        ]
        for col_idx, val in enumerate(values, start=1):
            ws.cell(row=row_idx, column=col_idx, value=val)

    for col_idx in range(1, nb_cols + 1):
        max_length = len(str(entetes[col_idx - 1]))
        for row_idx in range(data_row, ws.max_row + 1):
            val = ws.cell(row=row_idx, column=col_idx).value
            if val is not None:
                max_length = max(max_length, len(str(val)))
        ws.column_dimensions[get_column_letter(col_idx)].width = min(max_length + 4, 50)

    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def exporter_auditeurs_formation_xlsx(formation_id: int) -> bytes:
    """
    Retourne un fichier XLSX listant les auditeurs **affectés à un groupe** de la formation
    (après génération automatique ou affectation manuelle), un auditeur par ligne, tri par groupe
    puis nom. Colonne « Groupe » : nom du groupe sans répéter le grade de l'auditeur quand il
    apparaît déjà dans le libellé (ex. « Groupe 10 » au lieu de « Groupe 10 A3 » pour un A3).
    """
    from apps.groupes.models import GroupeAuditeur

    formation = Formation.objects.filter(pk=formation_id).first()
    if formation is None:
        raise ValueError(f"Formation {formation_id} introuvable.")

    ga_rows = list(
        GroupeAuditeur.objects.filter(groupe__formation_id=formation_id)
        .select_related("auditeur", "groupe")
        .order_by("groupe__nom", "auditeur__nom", "auditeur__prenom", "pk")
    )
    lignes = _lignes_export_auditeurs_depuis_groupe_auditeurs(ga_rows)
    return _exporter_auditeurs_xlsx(formation, lignes)


def exporter_auditeurs_groupe_xlsx(groupe_id: int) -> bytes:
    """Export XLSX des auditeurs d'un seul groupe (mêmes colonnes que l'export formation)."""
    from apps.groupes.models import Groupe, GroupeAuditeur

    groupe = Groupe.objects.select_related("formation").filter(pk=groupe_id).first()
    if groupe is None:
        raise ValueError(f"Groupe {groupe_id} introuvable.")

    ga_rows = list(
        GroupeAuditeur.objects.filter(groupe_id=groupe_id)
        .select_related("auditeur", "groupe")
        .order_by("auditeur__nom", "auditeur__prenom", "pk")
    )
    lignes = _lignes_export_auditeurs_depuis_groupe_auditeurs(ga_rows)
    return _exporter_auditeurs_xlsx(groupe.formation, lignes, groupe_nom=groupe.nom)
