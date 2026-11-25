"""Orchestration de la planification d'un groupe (génération et prévisualisation)."""

from __future__ import annotations

import datetime
import logging
from collections import Counter
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from apps.formations.rythme import rythme_mensuel_effectif_pour_module
from apps.parametrage.services import volume_horaire_effectif_formation_module_pour_dispatch
from apps.seances.models import Seance
from apps.seances.planning import trainer_allocator as planning_trainers

if TYPE_CHECKING:
    from apps.seances.services import PlanningService

logger = logging.getLogger("apps.seances")


@dataclass
class PlanificationGroupeResult:
    """Résultat d'une exécution de planification pour un groupe."""

    seances: list
    echecs_modules: list[dict] = field(default_factory=list)
    preview_report: list[dict] | None = None


class GroupePlanningOrchestrator:
    """Factorise la boucle de planification partagée par génération et prévisualisation."""

    def __init__(self, service: PlanningService) -> None:
        self._service = service

    def executer(
        self,
        groupe_id: int,
        *,
        dry_run: bool = False,
        mode: str = "strict",
        actor=None,
        for_preview: bool = False,
    ) -> PlanificationGroupeResult:
        from apps.groupes.models import Groupe
        from apps.parametrage.models import JourFerie, get_parametres_pour_formation
        from shared.formations_scope import utilisateur_voit_toutes_les_formations

        contexte = "previsualiser_pour_groupe" if for_preview else "generer_pour_groupe"
        log_prefix = "previsualiser " if for_preview else ""

        masquer_noms_formations = bool(
            actor and getattr(actor, "is_authenticated", False) and not utilisateur_voit_toutes_les_formations(actor)
        )

        groupe = (
            Groupe.objects.select_related("formation", "config")
            .prefetch_related(
                "jours_cours",
                "formation__modules__module",
                "formation__modules__module__specialite",
                "membres__auditeur",
            )
            .get(pk=groupe_id)
        )

        config = groupe.config
        jours_actifs = sorted(jc.jour for jc in groupe.jours_cours.all())

        if not config or not jours_actifs:
            raise ValueError("Le groupe n'est pas encore configuré (horaires ou jours manquants).")

        grade_principal = self._service._grade_principal_groupe(groupe)
        formation_modules = list(
            groupe.formation.modules.select_related("periode", "formation").order_by("date_debut", "module__titre")
        )
        params = get_parametres_pour_formation(groupe.formation_id)
        jours_feries = set(JourFerie.objects.filter(actif=True).values_list("date", flat=True))
        max_seances_jour = params.max_seances_par_jour_defaut or 2
        max_salles_simultanees_module = int(getattr(params, "max_salles_simultanees_module", 10) or 10)
        tolerance_capacite_salle = max(0, int(getattr(params, "tolerance_capacite_salle", 0) or 0))
        duree_seance_minutes = params.duree_seance_defaut_minutes or 240
        verrou_salle_groupe_actif = bool(getattr(params, "verrouiller_salle_groupe_formation", False))
        repartir_reliquat_actif = bool(getattr(params, "repartir_reliquat_sur_seances", False))
        score_weights = (
            int(getattr(params, "poids_score_ecart_capacite", 10) or 10),
            int(getattr(params, "poids_score_rotation_module", 2) or 2),
            int(getattr(params, "poids_score_equilibrage_global", 1) or 1),
        )
        effectif_groupe = groupe.nb_auditeurs

        if not dry_run and not for_preview:
            self._service._repo.supprimer_pour_groupe(groupe_id)

        seances: list[Seance] = []
        echecs_modules: list[dict] = []
        preview_report: list[dict] | None = [] if for_preview else None
        formation = groupe.formation
        not_before_dt = self._service._planning_not_before_datetime(formation.pk)

        if for_preview:
            logger.info(
                "planning previsualiser_pour_groupe init groupe_id=%s groupe=%r formation_id=%s "
                "grade_principal=%r effectif=%s jours_actifs=%s max_seances_jour=%s duree_seance_min=%s "
                "not_before_dt=%s nb_modules_formation=%s",
                groupe_id,
                groupe.nom,
                formation.pk,
                grade_principal,
                effectif_groupe,
                jours_actifs,
                max_seances_jour,
                duree_seance_minutes,
                not_before_dt.isoformat() if not_before_dt else None,
                len(formation_modules),
            )
        else:
            logger.info(
                "planning generer_pour_groupe init groupe_id=%s groupe=%r formation_id=%s dry_run=%s "
                "grade_principal=%r effectif=%s jours_actifs=%s max_seances_jour=%s duree_seance_min=%s "
                "not_before_dt=%s nb_modules_formation=%s",
                groupe_id,
                groupe.nom,
                formation.pk,
                dry_run,
                grade_principal,
                effectif_groupe,
                jours_actifs,
                max_seances_jour,
                duree_seance_minutes,
                not_before_dt.isoformat() if not_before_dt else None,
                len(formation_modules),
            )

        occupations = self._service._charger_occupations_existantes(groupe_id)
        occupations_modules_triples, occupations_modules_sans_salle = (
            self._service._charger_occupations_modules_existantes(groupe_id, formation.pk)
        )
        occupations_modules_par_jour = self._service._indexer_occupations_modules_triples(occupations_modules_triples)
        occupations_formateurs = self._service._charger_occupations_formateurs_existantes(groupe_id)
        formateurs_par_module_date_salle_formation = self._service._charger_formateurs_par_module_date_salle_formation(
            formation.pk, groupe_id
        )
        formateurs_pool = self._service._build_formateurs_pool(groupe)
        salle_localisations, salle_ids_by_name = self._service._charger_localisations_salles()
        periodes_disponibilite_sites = self._service._charger_periodes_disponibilite_sites()
        salles_par_site_batiment = self._service._indexer_salles_par_site_batiment(salle_localisations)
        formateurs_par_specialites_cache: dict[tuple[int, ...], list[dict[str, str]]] = {}
        module_salle_counts: dict[tuple[datetime.date, int, str], int] = {}
        salle_usage_counts: dict[str, int] = {}
        module_salle_usage_counts: dict[tuple[int, str], int] = {}
        module_par_date: dict[datetime.date, int] = {}

        modules_avec_volume: list[tuple[object, int]] = []
        for fm in formation_modules:
            if not getattr(fm.module, "actif", True):
                logger.info(
                    "planning %sskip module fm_id=%s titre=%r raison=module_inactif",
                    log_prefix,
                    fm.pk,
                    fm.module.titre,
                )
                continue
            if not self._service._grade_cible_compatible(fm.grade_cible, grade_principal):
                logger.debug(
                    "planning %sskip module fm_id=%s titre=%r raison=grade_cible_module incompatible "
                    "grade_groupe=%r grade_fm=%r",
                    log_prefix,
                    fm.pk,
                    fm.module.titre,
                    grade_principal,
                    fm.grade_cible,
                )
                continue
            heures_vol = volume_horaire_effectif_formation_module_pour_dispatch(
                fm.module_id,
                fm.volume_horaire,
                formation.type_formation_id,
                grade_principal,
                fm.module.titre,
            )
            if heures_vol is None or heures_vol <= 0:
                logger.info(
                    "planning %sskip module fm_id=%s titre=%r raison=pas_de_volume_dispatch "
                    "type_formation_id=%s grade_groupe=%r volume_fm_stocke=%s",
                    log_prefix,
                    fm.pk,
                    fm.module.titre,
                    formation.type_formation_id,
                    grade_principal,
                    fm.volume_horaire,
                )
                continue
            modules_avec_volume.append((fm, heures_vol))

        if not modules_avec_volume:
            if for_preview:
                logger.error(
                    "planning previsualiser abandon groupe_id=%s groupe=%r formation_id=%s : aucun module planifiable",
                    groupe_id,
                    groupe.nom,
                    formation.pk,
                )
            else:
                logger.error(
                    "planning abandon groupe_id=%s groupe=%r formation_id=%s : aucun module planifiable "
                    "(grades cibles ou paramétrage type×module×grade / volume)",
                    groupe_id,
                    groupe.nom,
                    formation.pk,
                )
            raise ValueError(
                "Aucun module planifiable pour ce groupe : vérifiez les grades cibles des modules "
                "et le paramétrage (type × module × grade du groupe, ou volume fixe sur le module de formation)."
            )

        union_sites_programme: Optional[frozenset[str]] = None
        salle_verrou_groupe: str = ""

        for fm, heures_vol in modules_avec_volume:
            module_date_debut = fm.date_debut or formation.date_debut
            module_date_fin = fm.date_fin or formation.date_fin
            heures_prevues = float(heures_vol)

            if module_date_fin < module_date_debut:
                if for_preview:
                    preview_report.append(
                        {
                            "module_titre": fm.module.titre,
                            "heures_prevues": heures_prevues,
                            "heures_placees": 0.0,
                            "heures_restantes": heures_prevues,
                            "couverture": 0.0,
                            "reason": "période invalide (date de fin antérieure à la date de début)",
                        }
                    )
                    continue

                reason = "période invalide (date de fin antérieure à la date de début)"
                self._service._log_echec_planning_module(
                    contexte=contexte,
                    groupe_id=groupe_id,
                    groupe_nom=groupe.nom or "",
                    formation_id=formation.pk,
                    module_id=fm.module_id,
                    module_titre=fm.module.titre,
                    module_date_debut=module_date_debut,
                    module_date_fin=module_date_fin,
                    grade_principal=grade_principal,
                    minutes_initial=heures_vol * 60,
                    minutes_restants=heures_vol * 60,
                    reason=reason,
                    diag=Counter(),
                    salles_module=[],
                    not_before_dt=not_before_dt,
                    niveau=logging.ERROR if mode == "strict" else logging.WARNING,
                )
                message = (
                    f"Module '{fm.module.titre}' non planifiable sur {module_date_debut:%d/%m/%Y}–"
                    f"{module_date_fin:%d/%m/%Y}: {reason} "
                    f"Reste {heures_vol}h à placer."
                )
                echecs_modules.append(
                    {
                        "module_id": fm.module_id,
                        "module_titre": fm.module.titre,
                        "module_date_debut": module_date_debut,
                        "module_date_fin": module_date_fin,
                        "heures_initial": heures_vol,
                        "heures_placees": 0,
                        "heures_restantes": heures_vol,
                        "reason": reason,
                        "diag": {},
                        "message": message,
                    }
                )
                if mode == "strict":
                    raise ValueError(message)
                continue

            salles_module = self._service._salles_candidates(
                fm,
                salle_localisations,
                salles_par_site_batiment=salles_par_site_batiment,
                union_sites_programme=union_sites_programme,
            )
            sites_module = self._service._split_noms(fm.site_nom)
            batiments_module = self._service._split_noms(fm.batiment_nom)
            minutes_restants = heures_vol * 60
            minutes_initial = minutes_restants
            current_date = module_date_debut
            premiere_salle_choisie = salle_verrou_groupe if verrou_salle_groupe_actif else ""
            fallback_formateur = {
                "nom": (fm.formateur_nom or "").strip(),
                "prenom": (fm.formateur_prenom or "").strip(),
                "numero": (fm.formateur_numero or "").strip(),
                "email": (fm.formateur_email or "").strip(),
                "telephone": (fm.formateur_telephone or "").strip(),
                "organisation": (fm.formateur_organisation or "").strip(),
            }
            creneau_mode_module = (getattr(fm, "creneau_mode", "") or "").strip() or "matin_et_soir"
            matin_autorise_module = creneau_mode_module in {"matin", "matin_et_soir"}
            soir_autorise_module = creneau_mode_module in {"soir", "matin_et_soir"}

            diag: Counter[str] = Counter()
            while minutes_restants > 0:
                if current_date > module_date_fin:
                    break

                if current_date.weekday() not in jours_actifs:
                    diag["jour_hors_jours_actifs"] += 1
                    current_date += datetime.timedelta(days=1)
                    continue
                if current_date in jours_feries:
                    diag["jour_ferie"] += 1
                    current_date += datetime.timedelta(days=1)
                    continue
                rythme_module = rythme_mensuel_effectif_pour_module(groupe, fm)
                if not self._service._date_autorisee_par_rythme_mensuel(current_date, rythme_module):
                    diag["jour_hors_rythme_mensuel"] += 1
                    current_date += datetime.timedelta(days=1)
                    continue
                if salles_module:
                    salles_planif = self._service._salles_eligibles_hors_occupation_module_intergroupes(
                        salles_module,
                        current_date,
                        fm.module_id,
                        occupations_modules_par_jour,
                        occupations_modules_sans_salle,
                        max_salles_simultanees_module,
                        salle_localisations,
                    )
                    if not salles_planif:
                        diag["inter_groupes_pool_module_epuise_ce_jour"] += 1
                        current_date += datetime.timedelta(days=1)
                        continue
                else:
                    salles_planif = salles_module

                module_jour = module_par_date.get(current_date)
                if module_jour is not None and module_jour != fm.module_id:
                    diag["autre_module_deja_ce_jour"] += 1
                    current_date += datetime.timedelta(days=1)
                    continue

                seances_jour = 0

                if (
                    config.matin_actif
                    and matin_autorise_module
                    and minutes_restants > 0
                    and seances_jour < max_seances_jour
                ):
                    debut = config.matin_heure_debut
                    fin = config.matin_heure_fin
                    if self._service._creneau_commence_apres_plancher(current_date, debut, not_before_dt):
                        duree = self._service._duree_minutes(debut, fin)
                        consommee = min(duree, minutes_restants, duree_seance_minutes)
                        fin_effective = self._service._ajouter_minutes(debut, consommee)
                        salle_choisie, salle_id_choisie = self._service._choisir_salle_disponible(
                            occupations,
                            current_date,
                            salles_planif,
                            debut,
                            fin_effective,
                            effectif_groupe,
                            salle_localisations,
                            fm.module_id,
                            max_seances_jour,
                            module_salle_counts,
                            salle_usage_counts,
                            module_salle_usage_counts,
                            score_weights,
                            salle_ids_by_name,
                            premiere_salle_choisie,
                            tolerance_capacite_salle,
                            periodes_disponibilite_sites,
                        )
                        if salle_choisie:
                            formateur_choisi = self._service._choisir_formateur_disponible(
                                occupations_formateurs=occupations_formateurs,
                                affectations_formateur=formateurs_pool,
                                module_id=fm.module_id,
                                module_specialite_id=fm.module.specialite_id,
                                date=current_date,
                                max_seances_jour=max_seances_jour,
                                fallback=fallback_formateur,
                                specialite_ids=fm.module.ids_specialites_pour_matching_formateurs(),
                                salle_nom=salle_choisie,
                                occ_formateur_par_salle_meme_module=formateurs_par_module_date_salle_formation,
                                formateurs_par_specialites_cache=formateurs_par_specialites_cache,
                            )
                            if not self._service._formateur_dict_est_renseigne(formateur_choisi):
                                logger.info(
                                    "planning %sséance sans formateur assigné groupe_id=%s date=%s module_id=%s "
                                    "specialite_id=%s",
                                    log_prefix,
                                    groupe_id,
                                    current_date.isoformat(),
                                    fm.module_id,
                                    fm.module.specialite_id,
                                )
                            if not premiere_salle_choisie:
                                premiere_salle_choisie = salle_choisie
                            module_par_date.setdefault(current_date, fm.module_id)
                            seances.append(
                                Seance(
                                    groupe_id=groupe_id,
                                    module_id=fm.module_id,
                                    site_nom=self._service._site_pour_salle(
                                        salle_choisie, salle_localisations, sites_module
                                    ),
                                    batiment_nom=self._service._batiment_pour_salle(
                                        salle_choisie, salle_localisations, batiments_module
                                    ),
                                    salle_nom=salle_choisie,
                                    salle_id=salle_id_choisie,
                                    formateur_nom=formateur_choisi.get("nom", ""),
                                    formateur_prenom=formateur_choisi.get("prenom", ""),
                                    formateur_numero=formateur_choisi.get("numero", ""),
                                    formateur_email=formateur_choisi.get("email", ""),
                                    formateur_telephone=formateur_choisi.get("telephone", ""),
                                    formateur_organisation=formateur_choisi.get("organisation", ""),
                                    formateur_referentiel_id=planning_trainers.formateur_pk_from_dict(formateur_choisi),
                                    date=current_date,
                                    heure_debut=debut,
                                    heure_fin=fin_effective,
                                    duree_minutes=consommee,
                                )
                            )
                            self._service._reserver_creneau(
                                occupations,
                                current_date,
                                salle_choisie,
                                debut,
                                fin_effective,
                                salle_id=salle_id_choisie,
                            )
                            if self._service._formateur_dict_est_renseigne(formateur_choisi):
                                self._service._reserver_formateur(
                                    occupations_formateurs, current_date, formateur_choisi
                                )
                                self._service._enregistrer_formateur_meme_module_autre_salle(
                                    formateurs_par_module_date_salle_formation,
                                    current_date,
                                    fm.module_id,
                                    salle_choisie,
                                    formateur_choisi,
                                )
                            cle = (current_date, fm.module_id, salle_choisie.strip().upper())
                            module_salle_counts[cle] = module_salle_counts.get(cle, 0) + 1
                            cle_salle = salle_choisie.strip().upper()
                            salle_usage_counts[cle_salle] = salle_usage_counts.get(cle_salle, 0) + 1
                            cle_module_salle = (fm.module_id, cle_salle)
                            module_salle_usage_counts[cle_module_salle] = (
                                module_salle_usage_counts.get(cle_module_salle, 0) + 1
                            )
                            minutes_restants -= consommee
                            seances_jour += 1
                        else:
                            diag["pas_de_salle_matin"] += 1
                            logger.debug(
                                "planning %spas de salle matin groupe_id=%s date=%s module_id=%s "
                                "nb_salles_candidates=%s effectif=%s",
                                log_prefix,
                                groupe_id,
                                current_date.isoformat(),
                                fm.module_id,
                                len(salles_module),
                                effectif_groupe,
                            )
                    else:
                        diag["plancher_bloque_matin"] += 1

                if (
                    config.soir_actif
                    and soir_autorise_module
                    and minutes_restants > 0
                    and seances_jour < max_seances_jour
                ):
                    debut = config.soir_heure_debut
                    fin = config.soir_heure_fin
                    if self._service._creneau_commence_apres_plancher(current_date, debut, not_before_dt):
                        duree = self._service._duree_minutes(debut, fin)
                        consommee = min(duree, minutes_restants, duree_seance_minutes)
                        fin_effective = self._service._ajouter_minutes(debut, consommee)
                        salle_choisie, salle_id_choisie = self._service._choisir_salle_disponible(
                            occupations,
                            current_date,
                            salles_planif,
                            debut,
                            fin_effective,
                            effectif_groupe,
                            salle_localisations,
                            fm.module_id,
                            max_seances_jour,
                            module_salle_counts,
                            salle_usage_counts,
                            module_salle_usage_counts,
                            score_weights,
                            salle_ids_by_name,
                            premiere_salle_choisie,
                            tolerance_capacite_salle,
                            periodes_disponibilite_sites,
                        )
                        if salle_choisie:
                            formateur_choisi = self._service._choisir_formateur_disponible(
                                occupations_formateurs=occupations_formateurs,
                                affectations_formateur=formateurs_pool,
                                module_id=fm.module_id,
                                module_specialite_id=fm.module.specialite_id,
                                date=current_date,
                                max_seances_jour=max_seances_jour,
                                fallback=fallback_formateur,
                                specialite_ids=fm.module.ids_specialites_pour_matching_formateurs(),
                                salle_nom=salle_choisie,
                                occ_formateur_par_salle_meme_module=formateurs_par_module_date_salle_formation,
                                formateurs_par_specialites_cache=formateurs_par_specialites_cache,
                            )
                            if not self._service._formateur_dict_est_renseigne(formateur_choisi):
                                logger.info(
                                    "planning %sséance sans formateur assigné groupe_id=%s date=%s module_id=%s "
                                    "specialite_id=%s",
                                    log_prefix,
                                    groupe_id,
                                    current_date.isoformat(),
                                    fm.module_id,
                                    fm.module.specialite_id,
                                )
                            if not premiere_salle_choisie:
                                premiere_salle_choisie = salle_choisie
                            module_par_date.setdefault(current_date, fm.module_id)
                            seances.append(
                                Seance(
                                    groupe_id=groupe_id,
                                    module_id=fm.module_id,
                                    site_nom=self._service._site_pour_salle(
                                        salle_choisie, salle_localisations, sites_module
                                    ),
                                    batiment_nom=self._service._batiment_pour_salle(
                                        salle_choisie, salle_localisations, batiments_module
                                    ),
                                    salle_nom=salle_choisie,
                                    salle_id=salle_id_choisie,
                                    formateur_nom=formateur_choisi.get("nom", ""),
                                    formateur_prenom=formateur_choisi.get("prenom", ""),
                                    formateur_numero=formateur_choisi.get("numero", ""),
                                    formateur_email=formateur_choisi.get("email", ""),
                                    formateur_telephone=formateur_choisi.get("telephone", ""),
                                    formateur_organisation=formateur_choisi.get("organisation", ""),
                                    formateur_referentiel_id=planning_trainers.formateur_pk_from_dict(formateur_choisi),
                                    date=current_date,
                                    heure_debut=debut,
                                    heure_fin=fin_effective,
                                    duree_minutes=consommee,
                                )
                            )
                            self._service._reserver_creneau(
                                occupations,
                                current_date,
                                salle_choisie,
                                debut,
                                fin_effective,
                                salle_id=salle_id_choisie,
                            )
                            if self._service._formateur_dict_est_renseigne(formateur_choisi):
                                self._service._reserver_formateur(
                                    occupations_formateurs, current_date, formateur_choisi
                                )
                                self._service._enregistrer_formateur_meme_module_autre_salle(
                                    formateurs_par_module_date_salle_formation,
                                    current_date,
                                    fm.module_id,
                                    salle_choisie,
                                    formateur_choisi,
                                )
                            cle = (current_date, fm.module_id, salle_choisie.strip().upper())
                            module_salle_counts[cle] = module_salle_counts.get(cle, 0) + 1
                            cle_salle = salle_choisie.strip().upper()
                            salle_usage_counts[cle_salle] = salle_usage_counts.get(cle_salle, 0) + 1
                            cle_module_salle = (fm.module_id, cle_salle)
                            module_salle_usage_counts[cle_module_salle] = (
                                module_salle_usage_counts.get(cle_module_salle, 0) + 1
                            )
                            minutes_restants -= consommee
                            seances_jour += 1
                        else:
                            diag["pas_de_salle_soir"] += 1
                            logger.debug(
                                "planning %spas de salle soir groupe_id=%s date=%s module_id=%s "
                                "nb_salles_candidates=%s effectif=%s",
                                log_prefix,
                                groupe_id,
                                current_date.isoformat(),
                                fm.module_id,
                                len(salles_module),
                                effectif_groupe,
                            )
                    else:
                        diag["plancher_bloque_soir"] += 1

                current_date += datetime.timedelta(days=1)

            if not for_preview and not dry_run and premiere_salle_choisie:
                self._service._auto_renseigner_localisation_module(fm, premiere_salle_choisie, salle_localisations)

            if not for_preview and verrou_salle_groupe_actif and not salle_verrou_groupe and premiere_salle_choisie:
                salle_verrou_groupe = premiere_salle_choisie
                logger.info(
                    "planning verrou salle groupe activé groupe_id=%s salle_verrou=%r (1er module=%r)",
                    groupe_id,
                    salle_verrou_groupe,
                    fm.module.titre,
                )

            if repartir_reliquat_actif and minutes_restants > 0:
                seances_module_courant = [se for se in seances if se.module_id == fm.module_id]
                avant = minutes_restants
                minutes_restants = self._service._etendre_seances_avec_reliquat(
                    seances_module_courant, seances, minutes_restants, occupations
                )
                if not for_preview and minutes_restants < avant:
                    logger.info(
                        "planning reliquat réparti groupe_id=%s module_id=%s minutes_absorbees=%s "
                        "minutes_restantes=%s nb_seances=%s",
                        groupe_id,
                        fm.module_id,
                        avant - minutes_restants,
                        minutes_restants,
                        len(seances_module_courant),
                    )

            reason = ""
            if minutes_restants > 0:
                jours_actifs_dans_fenetre = 0
                jours_ouvrables_dans_fenetre = 0
                d = module_date_debut
                while d <= module_date_fin:
                    if d.weekday() in jours_actifs:
                        jours_actifs_dans_fenetre += 1
                        if d not in jours_feries:
                            jours_ouvrables_dans_fenetre += 1
                    d += datetime.timedelta(days=1)

                if not salles_module:
                    reason = (
                        "aucune salle candidate (salles explicites incompatibles site/bâtiment avec le "
                        "référentiel, ou noms vides et aucune salle active sur le site du module)"
                    )
                elif jours_actifs_dans_fenetre == 0:
                    reason = "aucun jour actif du groupe dans la période du module"
                elif jours_ouvrables_dans_fenetre == 0:
                    reason = "tous les jours actifs de la période sont fériés"
                elif minutes_restants == minutes_initial:
                    reason = self._service._raison_echec_planning_aucune_minute_placee(
                        diag, salles_module, not_before_dt
                    )
                else:
                    reason = self._service._raison_echec_planning_partielle_reliquat(diag, salles_module, not_before_dt)

                reason = self._service._raison_planning_avec_diag(reason, diag)

                if salles_module:
                    _, at_max, _ = self._service._diag_dominant_planning(diag)
                    if "salles" in at_max or "module_occupe" in at_max:
                        details = self._service._occupation_details_salles(
                            salles_module,
                            module_date_debut,
                            module_date_fin,
                            groupe_id,
                            masquer_noms_formations=masquer_noms_formations,
                        )
                        if details:
                            reason = reason + " " + details

                if for_preview:
                    self._service._log_echec_planning_module(
                        contexte=contexte,
                        groupe_id=groupe_id,
                        groupe_nom=groupe.nom or "",
                        formation_id=formation.pk,
                        module_id=fm.module_id,
                        module_titre=fm.module.titre,
                        module_date_debut=module_date_debut,
                        module_date_fin=module_date_fin,
                        grade_principal=grade_principal,
                        minutes_initial=minutes_initial,
                        minutes_restants=minutes_restants,
                        reason=reason,
                        diag=diag,
                        salles_module=salles_module,
                        not_before_dt=not_before_dt,
                        niveau=logging.WARNING,
                    )
                else:
                    heures_restantes = minutes_restants // 60
                    self._service._log_echec_planning_module(
                        contexte=contexte,
                        groupe_id=groupe_id,
                        groupe_nom=groupe.nom or "",
                        formation_id=formation.pk,
                        module_id=fm.module_id,
                        module_titre=fm.module.titre,
                        module_date_debut=module_date_debut,
                        module_date_fin=module_date_fin,
                        grade_principal=grade_principal,
                        minutes_initial=minutes_initial,
                        minutes_restants=minutes_restants,
                        reason=reason,
                        diag=diag,
                        salles_module=salles_module,
                        not_before_dt=not_before_dt,
                        niveau=logging.ERROR if mode == "strict" else logging.WARNING,
                    )
                    message = (
                        f"Module '{fm.module.titre}' non planifiable sur {module_date_debut:%d/%m/%Y}–"
                        f"{module_date_fin:%d/%m/%Y}: {reason} "
                        f"Reste {heures_restantes}h à placer."
                    )
                    echecs_modules.append(
                        {
                            "module_id": fm.module_id,
                            "module_titre": fm.module.titre,
                            "module_date_debut": module_date_debut,
                            "module_date_fin": module_date_fin,
                            "heures_initial": minutes_initial // 60,
                            "heures_placees": (minutes_initial - minutes_restants) // 60,
                            "heures_restantes": heures_restantes,
                            "reason": reason,
                            "diag": dict(diag),
                            "message": message,
                        }
                    )
                    if mode == "strict":
                        raise ValueError(message)
            else:
                if for_preview:
                    logger.info(
                        "planning previsualiser module termine groupe_id=%s module_id=%s titre=%r "
                        "minutes_planifiees=%s",
                        groupe_id,
                        fm.module_id,
                        fm.module.titre,
                        minutes_initial,
                    )
                else:
                    logger.info(
                        "planning module termine groupe_id=%s module_id=%s titre=%r minutes_planifiees=%s",
                        groupe_id,
                        fm.module_id,
                        fm.module.titre,
                        minutes_initial,
                    )

            if for_preview and verrou_salle_groupe_actif and not salle_verrou_groupe and premiere_salle_choisie:
                salle_verrou_groupe = premiere_salle_choisie

            if for_preview:
                heures_placees = round((minutes_initial - minutes_restants) / 60, 2)
                heures_restantes = round(minutes_restants / 60, 2)
                couverture = round((heures_placees / heures_prevues) * 100, 1) if heures_prevues else 100.0
                preview_report.append(
                    {
                        "module_titre": fm.module.titre,
                        "heures_prevues": heures_prevues,
                        "heures_placees": heures_placees,
                        "heures_restantes": heures_restantes,
                        "couverture": couverture,
                        "reason": reason,
                    }
                )

        if not for_preview and not dry_run:
            seances = self._service._repo.bulk_create(seances)

        return PlanificationGroupeResult(
            seances=seances,
            echecs_modules=echecs_modules,
            preview_report=preview_report,
        )
