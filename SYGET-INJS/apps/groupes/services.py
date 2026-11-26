"""
Services de l'app groupes.
Logique métier pour la création et configuration des groupes.
"""

import logging
from typing import Dict, Iterable, Optional

from django.db import transaction
from django.db.models import Count, Q

from shared.utils.grades import deduire_categorie, grade_cible_matches
from shared.utils.groupes import (
    grade_principal_groupe,
    nom_groupe_standard,
    normaliser_nom_groupe_vers_canonique,
)

from .models import ConfigGroupe, Groupe, GroupeAuditeur, JourCours
from .repositories import ConfigGroupeRepository, GroupeRepository, JourCoursRepository

logger = logging.getLogger(__name__)


class GroupeService:
    """Logique métier pour la gestion des groupes."""

    @staticmethod
    def _grade_cible_compatible(grade_cible: str, grade_auditeur: str) -> bool:
        """
        Vérifie la compatibilité module/auditeur.
        Exemples: B couvre B3/B4 ; A3 ne couvre pas A4.
        """
        return grade_cible_matches(grade_cible, grade_auditeur)

    def __init__(
        self,
        repo: GroupeRepository,
        config_repo: ConfigGroupeRepository,
        jours_repo: JourCoursRepository,
    ) -> None:
        self._repo = repo
        self._config_repo = config_repo
        self._jours_repo = jours_repo

    def list_par_formation(self, formation_id: int) -> list[Groupe]:
        """Retourne les groupes d'une formation."""
        return self._repo.list_by_formation(formation_id)

    @staticmethod
    def auditeurs_par_nom_groupe_formation(formation_id: int) -> dict[str, set[int]]:
        """Retourne les auditeurs regroupés par nom de groupe pour une formation."""
        result: dict[str, set[int]] = {}
        for nom, auditeur_id in GroupeAuditeur.objects.filter(groupe__formation_id=formation_id).values_list(
            "groupe__nom", "auditeur_id"
        ):
            result.setdefault(nom, set()).add(auditeur_id)
        return result

    @staticmethod
    def nom_groupe_source_pour_auditeur(source_formation_id: int, auditeur_id: int) -> Optional[str]:
        """Nom du groupe source d'un auditeur, ou ``None`` s'il n'est dans aucun groupe."""
        return (
            GroupeAuditeur.objects.filter(
                auditeur_id=auditeur_id,
                groupe__formation_id=source_formation_id,
            )
            .values_list("groupe__nom", flat=True)
            .first()
        )

    @transaction.atomic
    def assurer_groupes_homologues_depuis_source(
        self,
        formation_id: int,
        source_formation_id: int,
        noms_requis: Optional[Iterable[str]] = None,
    ) -> int:
        """
        Crée sur la formation cible les groupes absents mais présents à la source.

        Appariement par ``Groupe.nom`` ; reprend la capacité max, les horaires, les jours actifs
        et la cadence mensuelle de chaque groupe source.
        """
        from apps.parametrage.repositories import ParametreFormationRepository

        groupes_source = (
            Groupe.objects.filter(formation_id=source_formation_id)
            .select_related("config")
            .prefetch_related("jours_cours")
        )
        if noms_requis is not None:
            noms = {n.strip() for n in noms_requis if (n or "").strip()}
            if noms:
                groupes_source = groupes_source.filter(nom__in=noms)
            else:
                return 0

        existants = set(Groupe.objects.filter(formation_id=formation_id).values_list("nom", flat=True))
        params = ParametreFormationRepository().get_for_formation(formation_id)
        max_defaut = params.max_auditeurs_groupe_defaut or 25
        nb_crees = 0
        for g_src in groupes_source.order_by("nom", "pk"):
            if g_src.nom in existants:
                continue
            groupe = self.creer(
                formation_id=formation_id,
                nom=g_src.nom,
                max_auditeurs=g_src.max_auditeurs or max_defaut,
            )
            self._copier_config_depuis_groupe_source(g_src, groupe)
            existants.add(g_src.nom)
            nb_crees += 1
        return nb_crees

    @staticmethod
    def _copier_config_depuis_groupe_source(groupe_source: Groupe, groupe_cible: Groupe) -> None:
        """Recopie horaires, jours actifs et cadence mensuelle depuis le groupe source."""
        config_src = getattr(groupe_source, "config", None)
        if config_src is not None:
            config_dst = getattr(groupe_cible, "config", None)
            if config_dst is None:
                config_dst = ConfigGroupe.objects.create(groupe=groupe_cible)
            for field in (
                "matin_actif",
                "matin_heure_debut",
                "matin_heure_fin",
                "soir_actif",
                "soir_heure_debut",
                "soir_heure_fin",
            ):
                setattr(config_dst, field, getattr(config_src, field))
            config_dst.save()

        jours = sorted(jc.jour for jc in groupe_source.jours_cours.all())
        if jours:
            JourCours.objects.filter(groupe_id=groupe_cible.pk).delete()
            JourCours.objects.bulk_create([JourCours(groupe_id=groupe_cible.pk, jour=j) for j in jours])

        if groupe_source.rythme_mensuel:
            groupe_cible.rythme_mensuel = groupe_source.rythme_mensuel
            groupe_cible.save(update_fields=["rythme_mensuel"])

    @transaction.atomic
    def reporter_membres_depuis_formation_source(
        self,
        formation_id: int,
        source_formation_id: int,
        auditeur_ids: Optional[Iterable[int]] = None,
    ) -> Dict[str, int]:
        """
        Recopie les affectations groupe depuis la formation source vers la formation cible.

        Crée d'abord les groupes homologues manquants (même nom que la source), puis affecte
        les auditeurs. Les auditeurs déjà dans un groupe de la cible ou sans groupe source
        sont ignorés.
        """
        noms_requis: Optional[set[str]] = None
        if auditeur_ids is not None:
            noms_requis = set(
                GroupeAuditeur.objects.filter(
                    groupe__formation_id=source_formation_id,
                    auditeur_id__in=list(auditeur_ids),
                )
                .values_list("groupe__nom", flat=True)
                .distinct()
            )

        groupes_crees = self.assurer_groupes_homologues_depuis_source(
            formation_id,
            source_formation_id,
            noms_requis=noms_requis,
        )

        groupes_cible = {
            g.nom: g for g in Groupe.objects.filter(formation_id=formation_id).only("pk", "nom", "max_auditeurs")
        }
        qs = GroupeAuditeur.objects.filter(groupe__formation_id=source_formation_id).select_related("groupe")
        if auditeur_ids is not None:
            qs = qs.filter(auditeur_id__in=list(auditeur_ids))

        ajoutes = 0
        ignores = 0
        for ga in qs:
            groupe_cible = groupes_cible.get(ga.groupe.nom)
            if groupe_cible is None:
                ignores += 1
                continue
            try:
                self.ajouter_auditeur(groupe_cible.pk, ga.auditeur_id)
                ajoutes += 1
            except ValueError:
                ignores += 1
        return {"ajoutes": ajoutes, "ignores": ignores, "groupes_crees": groupes_crees}

    def _affecter_formateurs_manquants_pour_formation(self, formation_id: int) -> int:
        """
        Crée les ``AffectationFormateurGroupe`` manquantes pour chaque groupe de la formation
        et chaque module du programme.

        **Nombre de modules par groupe** : un formateur ne peut être affecté qu'à **autant de
        modules** sur un même groupe qu'il a de **spécialités** (ex. 2 spécialités → au plus 2
        modules). Avec une seule spécialité : au plus un module par groupe.

        Pour une même spécialité de module, on **réutilise** l'intervenant déjà choisi pour ce
        groupe tant qu'il reste de la « capacité » (affectations ``<`` nombre de spécialités).

        Choix en **round-robin** sur l'ordre des groupes (``pk``), reprise cyclique parmi les
        candidats filtrés. Éligibilité : spécialité portée par le module **ou** spécialité du
        référentiel dont le **code** ou le **libellé** correspond au **titre** du module (insensible
        à la casse). Repli **uniquement** : formateurs **GENERAL** (si elle existe et n'est pas
        déjà dans cet ensemble), lorsqu'aucun intervenant éligible. Sinon numéros saisis sur les
        ``FormationModule`` (même filtre d'éligibilité). Aucun élargissement arbitraire vers tous
        les formateurs.

        Retourne le nombre d'affectations insérées (hors conflits d'unicité).
        """
        from collections import defaultdict

        from apps.formations.models import AffectationFormateurGroupe, FormationModule, Formateur
        from apps.referentiels.models import Specialite

        all_groupes = list(Groupe.objects.filter(formation_id=formation_id).order_by("pk"))
        if not all_groupes:
            return 0

        formation_modules = list(FormationModule.objects.filter(formation_id=formation_id).select_related("module"))
        if not formation_modules:
            return 0

        distinct_mids = sorted({fm.module_id for fm in formation_modules})
        existing_afgs = list(
            AffectationFormateurGroupe.objects.filter(groupe__formation_id=formation_id).select_related("module")
        )
        existing = {(a.groupe_id, a.module_id) for a in existing_afgs}
        to_create: list[AffectationFormateurGroupe] = []

        sc_cache: dict[int, int] = {}
        fids_pre = {a.formateur_id for a in existing_afgs}
        if fids_pre:
            for row in (
                Formateur.objects.filter(pk__in=fids_pre)
                .annotate(_sc=Count("specialites", distinct=True))
                .values("pk", "_sc")
            ):
                sc_cache[row["pk"]] = row["_sc"]

        def nb_specs(fid: int) -> int:
            if fid not in sc_cache:
                sc_cache[fid] = (
                    Formateur.objects.filter(pk=fid)
                    .annotate(_sc=Count("specialites", distinct=True))
                    .values_list("_sc", flat=True)
                    .first()
                    or 0
                )
            return sc_cache[fid]

        def peut_encore_sur_groupe(fid: int, gid: int) -> bool:
            n = nb_specs(fid)
            return n > 0 and usage_fg[(fid, gid)] < n

        usage_fg: dict[tuple[int, int], int] = defaultdict(int)
        groupe_spec_multi: dict[tuple[int, int], int] = {}
        for aff in existing_afgs:
            fid, gid = aff.formateur_id, aff.groupe_id
            usage_fg[(fid, gid)] += 1
            key = (gid, aff.module.specialite_id)
            if key not in groupe_spec_multi:
                groupe_spec_multi[key] = fid

        modules_by_id = {fm.module_id: fm.module for fm in formation_modules}
        formateurs_by_id: dict[int, object] = {}
        numeros_fm: set[str] = set()
        for fm in formation_modules:
            n = (fm.formateur_numero or "").strip()
            if n:
                numeros_fm.add(n)

        for mid in sorted(distinct_mids):
            module = modules_by_id[mid]
            spec_ids = list(module.ids_specialites_pour_matching_formateurs())
            for f in Formateur.objects.filter(specialites__id__in=spec_ids).distinct():
                formateurs_by_id[f.pk] = f
        if numeros_fm:
            for f in Formateur.objects.filter(numero__in=numeros_fm):
                formateurs_by_id[f.pk] = f

        for mid in sorted(distinct_mids):
            module = modules_by_id[mid]
            spec_id_fk = module.specialite_id
            spec_ids = list(module.ids_specialites_pour_matching_formateurs())
            spec_id_set = set(spec_ids)
            nums_from_fm: list[str] = []
            for fm in formation_modules:
                if fm.module_id != mid:
                    continue
                n = (fm.formateur_numero or "").strip()
                if n and n not in nums_from_fm:
                    nums_from_fm.append(n)

            eligible = list(
                Formateur.objects.filter(specialites__id__in=spec_ids).distinct().order_by("nom", "prenom", "pk")
            )
            if not eligible:
                gen = Specialite.objects.filter(code="GENERAL").only("pk").first()
                if gen and gen.pk not in spec_id_set:
                    eligible = list(
                        Formateur.objects.filter(specialites__id=gen.pk).distinct().order_by("nom", "prenom", "pk")
                    )
            # Pas d'élargissement « n'importe quelle spécialité » ni « tous les formateurs » :
            # un module ne reçoit que des intervenants dont la M2M couvre l'une des spécialités
            # alignées sur le module (FK + titre, repli GENERAL ci-dessus).

            for gi, groupe in enumerate(all_groupes):
                gid = groupe.pk
                if (gid, mid) in existing:
                    continue

                chosen_obj = None
                fid_reuse = groupe_spec_multi.get((gid, spec_id_fk))
                if fid_reuse is not None and peut_encore_sur_groupe(fid_reuse, gid):
                    chosen_obj = formateurs_by_id.get(fid_reuse)

                if chosen_obj is None:

                    def _filtered(pool: list[Formateur]) -> list[Formateur]:
                        return [f for f in pool if peut_encore_sur_groupe(f.pk, gid)]

                    pool = _filtered(eligible)
                    if pool:
                        chosen_obj = pool[gi % len(pool)]
                    else:
                        for num in nums_from_fm:
                            cand = next((f for f in formateurs_by_id.values() if f.numero == num), None)
                            if cand and peut_encore_sur_groupe(cand.pk, gid):
                                nb_specs(cand.pk)
                                chosen_obj = cand
                                break

                if chosen_obj is None:
                    continue

                fid = chosen_obj.pk
                to_create.append(
                    AffectationFormateurGroupe(
                        groupe_id=gid,
                        module_id=mid,
                        formateur_id=fid,
                    )
                )
                existing.add((gid, mid))
                usage_fg[(fid, gid)] += 1
                groupe_spec_multi[(gid, spec_id_fk)] = fid

        if not to_create:
            return 0
        AffectationFormateurGroupe.objects.bulk_create(to_create, ignore_conflicts=True)
        logger.warning(
            "GROUPES_AUTO_FORMATEUR_AFFECT formation_id=%s created=%s",
            formation_id,
            len(to_create),
        )
        return len(to_create)

    @transaction.atomic
    def generer_automatiquement_par_grade(
        self,
        formation_id: int,
        reset: bool = False,
        mixage_grades: Optional[bool] = None,
        *,
        actor=None,
    ) -> int:
        """
        Génère automatiquement des groupes.

        Règles:
          - ``mixage_grades=False`` (défaut) : un groupe par grade ; répartition tournante
            des types de concours à l'intérieur de chaque grade.
          - ``mixage_grades=True`` : groupes multi-grades par catégorie (noms « Groupe N {cat} ») ;
            répartition tournante des auditeurs de même catégorie (grades et types de concours
            mélangés à l'intérieur de chaque catégorie, jamais entre catégories).
          - La capacité d'un groupe suit ParametreGeneral.max_auditeurs_groupe_defaut.
          - Si reset=False et qu'il existe déjà des groupes, aucune génération n'est faite.
          - Si reset=True, les groupes existants de la formation sont supprimés puis régénérés.
          - Si aucune inscription n'existe, des inscriptions sont auto-créées à partir
            des auditeurs importés et des modules de la formation compatibles avec leur grade.
          - Avant le planning : affectations formateur/groupe/module manquantes complétées
            automatiquement (plafond : au plus autant de modules par groupe que de spécialités
            du formateur ; réutilisation par spécialité tant qu'il reste de la capacité).

        Retourne le nombre de groupes créés.
        """
        from apps.auditeurs.models import Auditeur
        from apps.formations.models import Inscription
        from apps.formations.models import FormationModule
        from apps.parametrage.repositories import ParametreFormationRepository

        logger.warning(
            "GROUPES_AUTO_START formation_id=%s reset=%s",
            formation_id,
            reset,
        )

        existing = Groupe.objects.filter(formation_id=formation_id)
        existing_count = existing.count()
        logger.warning(
            "GROUPES_AUTO_EXISTING formation_id=%s existing_count=%s",
            formation_id,
            existing_count,
        )
        if existing.exists() and not reset:
            logger.warning(
                "GROUPES_AUTO_CONTINUE formation_id=%s reason=existing_groups_present",
                formation_id,
            )
        if reset:
            existing.delete()
            logger.warning(
                "GROUPES_AUTO_RESET_DONE formation_id=%s deleted_groups=%s",
                formation_id,
                existing_count,
            )

        modules = list(FormationModule.objects.filter(formation_id=formation_id).only("id", "grade_cible"))
        logger.warning(
            "GROUPES_AUTO_MODULES formation_id=%s modules_count=%s",
            formation_id,
            len(modules),
        )
        if not modules:
            logger.warning(
                "GROUPES_AUTO_EMPTY formation_id=%s reason=no_modules",
                formation_id,
            )
            return 0

        inscriptions = list(
            Inscription.objects.filter(formation_id=formation_id)
            .select_related("auditeur")
            .order_by("auditeur__grade", "auditeur__nom", "auditeur__prenom")
        )
        logger.warning(
            "GROUPES_AUTO_INSCRIPTIONS formation_id=%s inscriptions_count=%s",
            formation_id,
            len(inscriptions),
        )

        # Complète les inscriptions manquantes dans un périmètre contrôlé:
        # - s'il existe déjà des inscrits dans la formation: uniquement ces auditeurs
        # - sinon: uniquement les auditeurs non encore rattachés à une formation
        #   (évite de "capturer" des auditeurs déjà engagés ailleurs).
        auditeur_scope_qs = Auditeur.objects.only("id", "grade", "categorie", "type_concours")
        if inscriptions:
            auditeur_ids_formation = {ins.auditeur_id for ins in inscriptions}
            auditeur_scope_qs = auditeur_scope_qs.filter(
                Q(id__in=auditeur_ids_formation) | (Q(inscriptions__isnull=True) & Q(groupes__isnull=True))
            ).distinct()
        else:
            auditeur_scope_qs = auditeur_scope_qs.filter(
                inscriptions__isnull=True,
                groupes__isnull=True,
            ).distinct()
        auditeurs = list(auditeur_scope_qs)
        logger.warning(
            "GROUPES_AUTO_AUDITEURS_SCOPE formation_id=%s auditeurs_count=%s",
            formation_id,
            len(auditeurs),
        )
        auditeurs_deja_inscrits = {ins.auditeur_id for ins in inscriptions}
        inscriptions_to_create: list[Inscription] = []
        skipped_no_module = 0
        skipped_already_inscrit = 0
        for aud in auditeurs:
            if aud.id in auditeurs_deja_inscrits:
                skipped_already_inscrit += 1
                continue
            aud_grade = (aud.grade or "").strip().upper()
            modules_eligibles = [fm for fm in modules if self._grade_cible_compatible(fm.grade_cible, aud_grade)]
            if not modules_eligibles:
                skipped_no_module += 1
                continue
            for fm in modules_eligibles:
                inscriptions_to_create.append(
                    Inscription(
                        formation_id=formation_id,
                        formation_module_id=fm.id,
                        auditeur_id=aud.id,
                    )
                )
        if inscriptions_to_create:
            Inscription.objects.bulk_create(inscriptions_to_create, ignore_conflicts=True)
        logger.warning(
            "GROUPES_AUTO_INSCRIPTIONS_BACKFILL formation_id=%s attempted=%s skipped_no_module=%s skipped_already_inscrit=%s",
            formation_id,
            len(inscriptions_to_create),
            skipped_no_module,
            skipped_already_inscrit,
        )
        if inscriptions_to_create:
            inscriptions = list(
                Inscription.objects.filter(formation_id=formation_id)
                .select_related("auditeur")
                .order_by("auditeur__grade", "auditeur__nom", "auditeur__prenom")
            )
            logger.warning(
                "GROUPES_AUTO_INSCRIPTIONS_AFTER_BACKFILL formation_id=%s inscriptions_count=%s",
                formation_id,
                len(inscriptions),
            )

        if not inscriptions:
            logger.warning(
                "GROUPES_AUTO_EMPTY formation_id=%s reason=no_inscriptions",
                formation_id,
            )
            return 0

        params = ParametreFormationRepository().get_for_formation(formation_id)
        max_auditeurs = params.max_auditeurs_groupe_defaut or 25
        if mixage_grades is None:
            mixage_grades = bool(getattr(params, "groupes_auto_mixage_grades", False))
        logger.warning(
            "GROUPES_AUTO_PARAMS formation_id=%s max_auditeurs=%s mixage_grades=%s",
            formation_id,
            max_auditeurs,
            mixage_grades,
        )

        auditeurs_uniques = {}
        for ins in inscriptions:
            if ins.auditeur_id not in auditeurs_uniques:
                auditeurs_uniques[ins.auditeur_id] = ins.auditeur

        if existing_count and not reset:
            auditeurs_deja_affectes = set(
                GroupeAuditeur.objects.filter(groupe__formation_id=formation_id).values_list(
                    "auditeur_id",
                    flat=True,
                )
            )
            auditeurs_uniques = {
                aud_id: auditeur
                for aud_id, auditeur in auditeurs_uniques.items()
                if aud_id not in auditeurs_deja_affectes
            }
            logger.warning(
                "GROUPES_AUTO_FILTER_UNASSIGNED formation_id=%s remaining=%s already_assigned=%s",
                formation_id,
                len(auditeurs_uniques),
                len(auditeurs_deja_affectes),
            )
            if not auditeurs_uniques:
                logger.warning(
                    "GROUPES_AUTO_SKIP formation_id=%s reason=all_auditeurs_already_assigned",
                    formation_id,
                )
                return 0

        groupes = []
        affectations: dict[int, list[int]] = {}
        noms_existants = set(Groupe.objects.filter(formation_id=formation_id).values_list("nom", flat=True))

        if mixage_grades:
            auditeurs_par_categorie: dict[str, list] = {}
            for aud in auditeurs_uniques.values():
                cat = deduire_categorie(aud.categorie, aud.grade) or "SANS_CATEGORIE"
                auditeurs_par_categorie.setdefault(cat, []).append(aud)

            for categorie in sorted(auditeurs_par_categorie.keys()):
                tous_auditeurs = sorted(
                    auditeurs_par_categorie[categorie],
                    key=lambda a: (
                        (a.type_concours or "").strip().upper(),
                        (a.grade or "").strip().upper(),
                        (a.nom or "").strip().upper(),
                        (a.prenom or "").strip().upper(),
                    ),
                )
                logger.warning(
                    "GROUPES_AUTO_MIXAGE_GRADES formation_id=%s categorie=%s total_auditeurs=%s",
                    formation_id,
                    categorie,
                    len(tous_auditeurs),
                )
                nb_groupes = max(1, (len(tous_auditeurs) + max_auditeurs - 1) // max_auditeurs)
                groupes_pool: list[Groupe] = []
                num = 1
                prefix_cat = categorie if categorie != "SANS_CATEGORIE" else "SANS"
                for _ in range(nb_groupes):
                    while True:
                        nom_groupe = nom_groupe_standard(prefix_cat, num)
                        if nom_groupe not in noms_existants:
                            break
                        num += 1
                    groupe = self.creer(
                        formation_id=formation_id,
                        nom=nom_groupe,
                        max_auditeurs=max_auditeurs,
                    )
                    noms_existants.add(nom_groupe)
                    groupes.append(groupe)
                    groupes_pool.append(groupe)
                    affectations[groupe.pk] = []
                    num += 1
                for idx, auditeur in enumerate(tous_auditeurs):
                    groupe_cible = groupes_pool[idx % nb_groupes]
                    affectations[groupe_cible.pk].append(auditeur.id)
        else:
            auditeurs_par_grade: dict[str, list] = {}
            for aud in auditeurs_uniques.values():
                grade = (aud.grade or "").strip().upper() or "SANS_GRADE"
                auditeurs_par_grade.setdefault(grade, []).append(aud)
            for grade in list(auditeurs_par_grade.keys()):
                auditeurs_par_grade[grade] = sorted(
                    auditeurs_par_grade[grade],
                    key=lambda a: (
                        (a.type_concours or "").strip().upper(),
                        (a.nom or "").strip().upper(),
                        (a.prenom or "").strip().upper(),
                    ),
                )
            logger.warning(
                "GROUPES_AUTO_BUCKETS formation_id=%s buckets=%s",
                formation_id,
                {grade: len(items) for grade, items in auditeurs_par_grade.items()},
            )
            for grade in sorted(auditeurs_par_grade.keys()):
                auditeurs_grade = auditeurs_par_grade[grade]
                nb_groupes_grade = (len(auditeurs_grade) + max_auditeurs - 1) // max_auditeurs
                groupes_grade: list[Groupe] = []
                num = 1
                for _ in range(nb_groupes_grade):
                    while nom_groupe_standard(grade, num) in noms_existants:
                        num += 1
                    nom_groupe = nom_groupe_standard(grade, num)
                    groupe = self.creer(
                        formation_id=formation_id,
                        nom=nom_groupe,
                        max_auditeurs=max_auditeurs,
                    )
                    noms_existants.add(nom_groupe)
                    groupes.append(groupe)
                    groupes_grade.append(groupe)
                    affectations[groupe.pk] = []
                    num += 1

                for idx, auditeur in enumerate(auditeurs_grade):
                    groupe_cible = groupes_grade[idx % nb_groupes_grade]
                    affectations[groupe_cible.pk].append(auditeur.id)

        nb_groupes_crees = len(groupes)
        for groupe in groupes:
            aud_ids = affectations[groupe.pk]
            GroupeAuditeur.objects.bulk_create(
                [GroupeAuditeur(groupe_id=groupe.pk, auditeur_id=aid) for aid in aud_ids]
            )
            logger.warning(
                "GROUPES_AUTO_CREATED formation_id=%s groupe_id=%s groupe_nom=%s members=%s",
                formation_id,
                groupe.pk,
                groupe.nom,
                len(aud_ids),
            )

        self._affecter_formateurs_manquants_pour_formation(formation_id)

        # Génère automatiquement le planning de **tous** les groupes nouvellement créés,
        # dans un ordre intelligent (par difficulté décroissante : gros effectif et peu de
        # jours actifs en premier), en mode "best_effort" pour ne pas tout bloquer si un
        # module précis se révèle non planifiable.
        from apps.seances.repositories import SeanceRepository
        from apps.seances.services import PlanningService

        planning_service = PlanningService(SeanceRepository())
        rapport = planning_service.generer_pour_formation(
            formation_id,
            mode="best_effort",
            actor=actor,
        )
        # Expose les détails au consommateur (vue / API) sans rompre la signature retournant
        # le nombre de groupes créés.
        self.dernier_rapport_planning: dict = rapport
        echecs_groupes: list[dict] = []
        for grp in rapport.get("groupes", []):
            if grp["status"] == "ok":
                logger.warning(
                    "GROUPES_AUTO_PLANNING_DONE formation_id=%s groupe_id=%s seances=%s",
                    formation_id,
                    grp["groupe_id"],
                    grp["nb_seances"],
                )
                continue
            if grp["status"] == "partiel":
                logger.warning(
                    "GROUPES_AUTO_PLANNING_PARTIEL formation_id=%s groupe_id=%s seances=%s " "nb_modules_echec=%s",
                    formation_id,
                    grp["groupe_id"],
                    grp["nb_seances"],
                    len(grp["echecs_modules"]),
                )
            else:
                logger.warning(
                    "GROUPES_AUTO_PLANNING_ERROR formation_id=%s groupe_id=%s reason=%s",
                    formation_id,
                    grp["groupe_id"],
                    grp.get("error"),
                )
            echecs_groupes.append(grp)
        self.derniers_echecs_planning: list[dict] = echecs_groupes

        logger.warning(
            "GROUPES_AUTO_DONE formation_id=%s created=%s",
            formation_id,
            nb_groupes_crees,
        )
        return nb_groupes_crees

    @transaction.atomic
    def creer(self, formation_id: int, nom: str, max_auditeurs: int = 25) -> Groupe:
        """
        Crée un groupe et initialise sa configuration depuis les paramètres de la formation.
        Lève ValueError si le nom est déjà utilisé dans cette formation.
        """
        from apps.parametrage.repositories import ParametreFormationRepository

        nom = normaliser_nom_groupe_vers_canonique(nom)
        if Groupe.objects.filter(formation_id=formation_id, nom=nom).exists():
            raise ValueError(f"Le groupe '{nom}' existe déjà dans cette formation.")

        groupe = self._repo.save(Groupe(formation_id=formation_id, nom=nom, max_auditeurs=max_auditeurs))

        params = ParametreFormationRepository().get_for_formation(formation_id)
        config = ConfigGroupe(
            groupe=groupe,
            matin_heure_debut=params.matin_heure_debut_defaut,
            matin_heure_fin=params.matin_heure_fin_defaut,
            soir_heure_debut=params.soir_heure_debut_defaut,
            soir_heure_fin=params.soir_heure_fin_defaut,
        )
        self._config_repo.save(config)

        if params.jours_defaut:
            self._jours_repo.remplacer_pour_groupe(groupe.pk, params.jours_defaut)

        return groupe

    @transaction.atomic
    def normaliser_noms_groupes_formation(self, formation_id: int) -> int:
        """
        Renomme les groupes existants vers le format ``A4_GROUPE1``.
        Retourne le nombre de groupes renommés.
        """
        modifies = 0
        for groupe in Groupe.objects.filter(formation_id=formation_id).prefetch_related("membres__auditeur"):
            grade = grade_principal_groupe(groupe)
            nouveau = normaliser_nom_groupe_vers_canonique(groupe.nom, grade=grade)
            if nouveau == groupe.nom:
                continue
            if Groupe.objects.filter(formation_id=formation_id, nom=nouveau).exclude(pk=groupe.pk).exists():
                continue
            groupe.nom = nouveau
            groupe.save(update_fields=["nom"])
            modifies += 1
        return modifies

    @transaction.atomic
    def supprimer(self, groupe_id: int) -> str:
        """
        Supprime un groupe et ses données associées (membres, config, séances).
        Retourne le nom du groupe supprimé.
        """
        groupe = self._repo.get_by_id(groupe_id)
        if groupe is None:
            raise ValueError(f"Groupe {groupe_id} introuvable.")
        nom = groupe.nom
        formation_id = groupe.formation_id
        self._repo.delete(groupe_id)
        logger.warning(
            "GROUPE_DELETE groupe_id=%s formation_id=%s nom=%s",
            groupe_id,
            formation_id,
            nom,
        )
        return nom

    @transaction.atomic
    def configurer_horaires(
        self,
        groupe_id: int,
        matin_actif: bool,
        matin_heure_debut,
        matin_heure_fin,
        soir_actif: bool,
        soir_heure_debut,
        soir_heure_fin,
    ) -> ConfigGroupe:
        """Met à jour la configuration horaire d'un groupe."""
        config = self._config_repo.get_by_groupe(groupe_id)
        if config is None:
            groupe = self._repo.get_by_id(groupe_id)
            config = ConfigGroupe(groupe=groupe)
        config.matin_actif = matin_actif
        config.matin_heure_debut = matin_heure_debut
        config.matin_heure_fin = matin_heure_fin
        config.soir_actif = soir_actif
        config.soir_heure_debut = soir_heure_debut
        config.soir_heure_fin = soir_heure_fin
        return self._config_repo.save(config)

    @transaction.atomic
    def configurer_jours(self, groupe_id: int, jours: list[int]) -> None:
        """Remplace les jours de cours actifs d'un groupe."""
        self._jours_repo.remplacer_pour_groupe(groupe_id, jours)

    @transaction.atomic
    def configurer_rythme_mensuel(self, groupe_id: int, rythme: str) -> Groupe:
        """Met à jour la cadence mensuelle d'un groupe.

        - Une chaîne vide ``""`` signifie « hérite de la cadence de la formation ».
        - Une valeur valide de ``Groupe.RythmeMensuel`` remplace celle de la formation.
        - Toute autre valeur invalide retombe sur ``""`` (héritage).
        """
        groupe = self._repo.get_by_id(groupe_id)
        if groupe is None:
            raise ValueError(f"Groupe {groupe_id} introuvable.")
        valides = {choice for choice, _ in Groupe.RythmeMensuel.choices}
        groupe.rythme_mensuel = rythme if rythme in valides else ""
        groupe.save(update_fields=["rythme_mensuel"])
        return groupe

    @transaction.atomic
    def affecter_ou_deplacer_auditeur(self, groupe_id: int, auditeur_id: int) -> GroupeAuditeur:
        """
        Affecte un auditeur au groupe, en le retirant d'un autre groupe de la même formation si besoin.
        """
        groupe = self._repo.get_by_id(groupe_id)
        if groupe is None:
            raise ValueError(f"Groupe {groupe_id} introuvable.")
        GroupeAuditeur.objects.filter(
            auditeur_id=auditeur_id,
            groupe__formation_id=groupe.formation_id,
        ).exclude(groupe_id=groupe_id).delete()
        return self.ajouter_auditeur(groupe_id=groupe_id, auditeur_id=auditeur_id)

    @transaction.atomic
    def ajouter_auditeur(self, groupe_id: int, auditeur_id: int) -> GroupeAuditeur:
        """
        Ajoute un auditeur à un groupe.
        Lève ValueError si le groupe est plein ou si l'auditeur est déjà membre
        d'un groupe de la même formation.
        """
        groupe = self._repo.get_by_id(groupe_id)
        if groupe is None:
            raise ValueError(f"Groupe {groupe_id} introuvable.")
        if GroupeAuditeur.objects.filter(groupe_id=groupe_id, auditeur_id=auditeur_id).exists():
            raise ValueError("Cet auditeur est déjà dans ce groupe.")
        if GroupeAuditeur.objects.filter(
            auditeur_id=auditeur_id,
            groupe__formation_id=groupe.formation_id,
        ).exists():
            raise ValueError("Cet auditeur appartient déjà à un autre groupe de cette formation.")
        if groupe.nb_auditeurs >= groupe.max_auditeurs:
            raise ValueError(f"Le groupe a atteint sa capacité maximale ({groupe.max_auditeurs}).")
        return GroupeAuditeur.objects.create(groupe_id=groupe_id, auditeur_id=auditeur_id)

    @transaction.atomic
    def retirer_auditeur(self, groupe_id: int, auditeur_id: int) -> None:
        """Retire un auditeur d'un groupe. Lève ValueError si le groupe est introuvable."""
        groupe = self._repo.get_by_id(groupe_id)
        if groupe is None:
            raise ValueError(f"Groupe {groupe_id} introuvable.")
        deleted, _ = GroupeAuditeur.objects.filter(groupe_id=groupe_id, auditeur_id=auditeur_id).delete()
        if not deleted:
            raise ValueError("Cet auditeur n'est pas membre de ce groupe.")
