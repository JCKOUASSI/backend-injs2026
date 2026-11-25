"""
Services de l'app seances.
Génération du planning, calcul du volume horaire, export Excel.
"""

import datetime
import logging
from collections import Counter
from dataclasses import dataclass
from typing import Optional

from django.db import transaction

from shared.utils.grades import grade_cible_matches

from apps.seances.planning import diagnostics as planning_diagnostics
from apps.seances.planning import locations as planning_locations
from apps.seances.planning import occupations as planning_occupations
from apps.seances.planning.orchestrator import GroupePlanningOrchestrator
from apps.seances.planning import room_allocator as planning_rooms
from apps.seances.planning import trainer_allocator as planning_trainers

from .models import Seance
from .repositories import SeanceRepository

logger = logging.getLogger("apps.seances")


@dataclass
class SeanceGenereeDTO:
    """Donnée d'une séance à créer (avant persistance)."""

    groupe_id: int
    module_id: int
    date: datetime.date
    heure_debut: datetime.time
    heure_fin: datetime.time
    duree_minutes: int


class PlanningService:
    """
    Génère le planning de séances d'un groupe à partir de sa configuration.
    Répartit les modules sur les jours de cours disponibles en respectant
    les volumes horaires définis dans FormationModule ou, à défaut, une règle
    de paramétrage type × module **compatible avec le grade du groupe** (le volume
    « tous grades » du paramétrage ne suffit pas lorsque ce grade est connu).

    Ordre entre formations dont les périodes se chevauchent : tri par
    (date_debut de formation, id). Une formation « plus récente » ne place
    aucune séance avant la fin de la dernière séance déjà planifiée des
    formations prioritaires qui se chevauchent avec elle.

    Les **salles** et la charge **formateur** tiennent compte de toutes les séances
    existantes (toutes formations). La contrainte « ce module référentiel déjà ce jour
    pour un autre groupe » s'applique uniquement aux **autres groupes de la même formation**.
    """

    def __init__(self, repo: SeanceRepository) -> None:
        self._repo = repo

    @staticmethod
    def _formations_periodes_se_chevauchent(
        a_debut: datetime.date,
        a_fin: datetime.date,
        b_debut: datetime.date,
        b_fin: datetime.date,
    ) -> bool:
        return a_debut <= b_fin and b_debut <= a_fin

    def _planning_not_before_datetime(self, formation_id: int) -> Optional[datetime.datetime]:
        """Voir ``apps.seances.planning.constraints.planning_not_before_datetime``."""
        from apps.seances.planning.constraints import planning_not_before_datetime

        return planning_not_before_datetime(formation_id)

    @staticmethod
    def _creneau_commence_apres_plancher(
        jour: datetime.date,
        heure_debut: datetime.time,
        plancher: Optional[datetime.datetime],
    ) -> bool:
        """True si le créneau (jour, heure_debut) commence strictement après ``plancher``."""
        if plancher is None:
            return True
        return datetime.datetime.combine(jour, heure_debut) > plancher

    @staticmethod
    def _grade_cible_compatible(grade_cible: str, grade_groupe: str) -> bool:
        """
        Vérifie la compatibilité module/groupe.
        Exemples: B couvre B3/B4 ; A3 ne couvre pas A4.
        """
        return grade_cible_matches(grade_cible, grade_groupe)

    @staticmethod
    def _date_autorisee_par_rythme_mensuel(jour: datetime.date, rythme_mensuel: str) -> bool:
        """
        Contrainte mensuelle de formation.
        - "1" => 1re semaine du mois
        - "2" => 1res 2 semaines
        - "3" => 1res 3 semaines
        - "4"/autre => tout le mois
        """
        rythme = (rythme_mensuel or "").strip()
        if rythme not in {"1", "2", "3"}:
            return True
        semaine_du_mois = ((jour.day - 1) // 7) + 1
        return semaine_du_mois <= int(rythme)

    @staticmethod
    def _log_echec_planning_module(
        *,
        contexte: str,
        groupe_id: int,
        groupe_nom: str,
        formation_id: int,
        module_id: int,
        module_titre: str,
        module_date_debut: datetime.date,
        module_date_fin: datetime.date,
        grade_principal: str,
        minutes_initial: int,
        minutes_restants: int,
        reason: str,
        diag: Counter[str],
        salles_module: list[str],
        not_before_dt: Optional[datetime.datetime],
        niveau: int = logging.ERROR,
    ) -> None:
        planning_diagnostics.log_echec_planning_module(
            contexte=contexte,
            groupe_id=groupe_id,
            groupe_nom=groupe_nom,
            formation_id=formation_id,
            module_id=module_id,
            module_titre=module_titre,
            module_date_debut=module_date_debut,
            module_date_fin=module_date_fin,
            grade_principal=grade_principal,
            minutes_initial=minutes_initial,
            minutes_restants=minutes_restants,
            reason=reason,
            diag=diag,
            salles_module=salles_module,
            not_before_dt=not_before_dt,
            niveau=niveau,
        )

    @staticmethod
    def _raison_planning_avec_diag(reason: str, diag: Counter[str]) -> str:
        return planning_diagnostics.raison_planning_avec_diag(reason, diag)

    @staticmethod
    def _diag_dominant_planning(
        diag: Counter[str],
    ) -> tuple[int, frozenset[str], dict[str, int]]:
        return planning_diagnostics.diag_dominant_planning(diag)

    @staticmethod
    def _raison_echec_planning_aucune_minute_placee(
        diag: Counter[str],
        salles_module: list[str],
        not_before_dt: Optional[datetime.datetime],
    ) -> str:
        return planning_diagnostics.raison_echec_planning_aucune_minute_placee(diag, salles_module, not_before_dt)

    @staticmethod
    def _raison_echec_planning_partielle_reliquat(
        diag: Counter[str],
        salles_module: list[str],
        not_before_dt: Optional[datetime.datetime],
    ) -> str:
        return planning_diagnostics.raison_echec_planning_partielle_reliquat(diag, salles_module, not_before_dt)

    @transaction.atomic
    def generer_pour_groupe(
        self,
        groupe_id: int,
        dry_run: bool = False,
        mode: str = "strict",
        *,
        actor=None,
    ) -> list[Seance]:
        """
        Génère (ou régénère) les séances d'un groupe.
        En mode normal, supprime les séances existantes puis crée les nouvelles.
        En mode dry_run, calcule seulement les séances sans rien persister.

        Paramètre ``mode``:
          - ``"strict"`` (défaut, rétrocompatible) : lève ``ValueError`` au premier module
            qui ne peut pas être entièrement planifié ; la transaction est annulée.
          - ``"best_effort"`` : poursuit avec les modules suivants même si un module est en
            échec. Les séances qui ont pu être placées sont persistées. Le rapport des modules
            en échec est exposé via ``self._derniers_echecs_modules`` (liste de dicts).

        Algorithme :
          - Itère les modules de la formation par date_debut puis titre
          - Pour chaque module, crée des créneaux matin/après-midi sur les jours actifs
          - Utilise la fenêtre de dates du module si définie, sinon celle de la formation
          - S'arrête quand le volume horaire du module est épuisé
          - Si d'autres formations ont une période qui chevauche la sienne et sont prioritaires
            (tri date_debut, id), aucune séance ne commence avant la fin de leur dernière séance existante
        """
        self._derniers_echecs_modules: list[dict] = []
        result = GroupePlanningOrchestrator(self).executer(
            groupe_id,
            dry_run=dry_run,
            mode=mode,
            actor=actor,
            for_preview=False,
        )
        self._derniers_echecs_modules = result.echecs_modules
        return result.seances

    @transaction.atomic
    def previsualiser_pour_groupe(self, groupe_id: int, *, actor=None) -> tuple[list[Seance], list[dict[str, object]]]:
        """
        Prévisualise le planning sans persistance, avec un diagnostic par module.

        Retour:
          - séances potentielles (non sauvegardées)
          - rapport modules [{module_titre, heures_prevues, heures_placees, heures_restantes, couverture, reason}]
        """
        result = GroupePlanningOrchestrator(self).executer(
            groupe_id,
            dry_run=True,
            actor=actor,
            for_preview=True,
        )
        return result.seances, result.preview_report or []

    @staticmethod
    def ordonner_groupes_par_difficulte(formation_id: int) -> list[int]:
        """
        Retourne les IDs des groupes d'une formation, triés du plus difficile au plus facile
        à planifier.

        Heuristique :
          - effectif élevé = moins de salles compatibles capacité = plus difficile
          - peu de jours actifs par semaine = fenêtre de placement plus étroite = plus difficile

        Les groupes les plus difficiles passent en premier : ils choisissent parmi les ressources
        encore peu contraintes (grandes salles, formateurs rares). Évite le cas où le dernier
        groupe traité ne trouve plus aucune salle compatible.

        Retourne une liste d'IDs ordonnée (score décroissant, puis pk croissant pour stabilité).
        """
        from apps.groupes.models import Groupe

        groupes = list(
            Groupe.objects.filter(formation_id=formation_id).prefetch_related("jours_cours", "membres").order_by("pk")
        )
        scored: list[tuple[int, int]] = []
        for g in groupes:
            effectif = g.membres.count()
            nb_jours = g.jours_cours.count() or 5
            # Effectif domine (×100) ; pénalité 10 pts par jour actif manquant sous 7.
            score = effectif * 100 - nb_jours * 10
            scored.append((score, g.pk))
        scored.sort(key=lambda item: (-item[0], item[1]))
        return [pk for _, pk in scored]

    def generer_pour_formation(
        self,
        formation_id: int,
        mode: str = "best_effort",
        *,
        actor=None,
        persister_run: bool = True,
    ) -> dict:
        """
        Génère le planning de **tous les groupes** d'une formation dans un ordre intelligent.

        Étapes :
          1. Ordonnance les groupes par difficulté décroissante
             (cf. ``ordonner_groupes_par_difficulte``).
          2. Pour chaque groupe, appelle ``generer_pour_groupe`` avec le mode demandé.
          3. Agrège un rapport structuré (statut par groupe, échecs par module, synthèse).

        En ``best_effort`` (défaut) : un groupe en erreur fatale (config invalide) n'arrête
        pas la génération des suivants ; un module non planifiable est consigné dans le
        rapport sans interrompre. Les séances réussies de chaque groupe sont persistées
        (transactions distinctes via ``generer_pour_groupe``).

        En ``strict`` : remonte la première ``ValueError``.

        Retour :
            {
              "formation_id": int,
              "mode": str,
              "ordre_groupes": list[int],
              "groupes": [
                {
                  "groupe_id": int,
                  "nom": str,
                  "status": "ok" | "partiel" | "erreur",
                  "nb_seances": int,
                  "echecs_modules": list[dict],
                  "error": str | None,
                },
                ...
              ],
              "synthese": {
                "nb_groupes": int,
                "nb_groupes_ok": int,
                "nb_groupes_partiels": int,
                "nb_groupes_erreur": int,
                "nb_seances_total": int,
              },
            }
        """
        from django.utils import timezone

        from apps.groupes.models import Groupe

        from .models import PlanningRun

        ordre = self.ordonner_groupes_par_difficulte(formation_id)
        noms = dict(Groupe.objects.filter(pk__in=ordre).values_list("pk", "nom"))

        run: Optional[PlanningRun] = None
        if persister_run:
            run = PlanningRun.objects.create(
                formation_id=formation_id,
                actor=actor,
                mode=mode,
                statut=PlanningRun.Statut.EN_COURS,
            )

        try:
            rapport_groupes: list[dict] = []
            nb_seances_total = 0
            for gid in ordre:
                try:
                    seances = self.generer_pour_groupe(gid, mode=mode, actor=actor)
                except ValueError as exc:
                    rapport_groupes.append(
                        {
                            "groupe_id": gid,
                            "nom": noms.get(gid, ""),
                            "status": "erreur",
                            "nb_seances": 0,
                            "echecs_modules": list(getattr(self, "_derniers_echecs_modules", [])),
                            "error": str(exc),
                        }
                    )
                    if mode == "strict":
                        raise
                    continue
                echecs = list(getattr(self, "_derniers_echecs_modules", []))
                status = "ok" if not echecs else "partiel"
                rapport_groupes.append(
                    {
                        "groupe_id": gid,
                        "nom": noms.get(gid, ""),
                        "status": status,
                        "nb_seances": len(seances),
                        "echecs_modules": echecs,
                        "error": None,
                    }
                )
                nb_seances_total += len(seances)
        except Exception as exc:
            if run is not None:
                run.statut = PlanningRun.Statut.ERREUR
                run.synthese = {"error": str(exc)}
                run.finished_at = timezone.now()
                run.save(update_fields=["statut", "synthese", "finished_at"])
            raise

        synthese = {
            "nb_groupes": len(ordre),
            "nb_groupes_ok": sum(1 for r in rapport_groupes if r["status"] == "ok"),
            "nb_groupes_partiels": sum(1 for r in rapport_groupes if r["status"] == "partiel"),
            "nb_groupes_erreur": sum(1 for r in rapport_groupes if r["status"] == "erreur"),
            "nb_seances_total": nb_seances_total,
        }
        logger.info(
            "planning generer_pour_formation formation_id=%s mode=%s synthese=%s ordre_groupes=%s "
            "planning_run_id=%s",
            formation_id,
            mode,
            synthese,
            ordre,
            run.pk if run is not None else None,
        )

        if run is not None:
            run.statut = PlanningRun.Statut.TERMINE
            run.synthese = synthese
            # JSONField : sérialisation compatible — on simplifie les types non sérialisables.
            run.groupes = self._planning_run_serialiser_groupes(rapport_groupes)
            run.finished_at = timezone.now()
            run.save(update_fields=["statut", "synthese", "groupes", "finished_at"])

        return {
            "formation_id": formation_id,
            "mode": mode,
            "ordre_groupes": ordre,
            "groupes": rapport_groupes,
            "synthese": synthese,
            "planning_run_id": run.pk if run is not None else None,
        }

    @staticmethod
    def _planning_run_serialiser_groupes(rapport_groupes: list[dict]) -> list[dict]:
        """Sérialise les dates et Counter en types JSON-compatibles pour PlanningRun.groupes."""
        out: list[dict] = []
        for grp in rapport_groupes:
            echecs_clean: list[dict] = []
            for e in grp.get("echecs_modules", []) or []:
                e_copy = dict(e)
                for k in ("module_date_debut", "module_date_fin"):
                    v = e_copy.get(k)
                    if hasattr(v, "isoformat"):
                        e_copy[k] = v.isoformat()
                diag = e_copy.get("diag")
                if diag is not None and not isinstance(diag, dict):
                    e_copy["diag"] = dict(diag)
                echecs_clean.append(e_copy)
            out.append({**grp, "echecs_modules": echecs_clean})
        return out

    @staticmethod
    def _grade_principal_groupe(groupe) -> str:
        """Retourne le grade principal d'un groupe (majoritaire), sinon chaîne vide."""
        grades = [
            (m.auditeur.grade or "").strip().upper() for m in groupe.membres.all() if (m.auditeur.grade or "").strip()
        ]
        if grades:
            return Counter(grades).most_common(1)[0][0]
        nom = (groupe.nom or "").strip().upper()
        if "-" in nom:
            prefix = nom.split("-", 1)[0].strip()
            if prefix:
                return prefix
        return ""

    @staticmethod
    def _duree_minutes(debut: datetime.time, fin: datetime.time) -> int:
        """Calcule la durée en minutes entre deux heures."""
        d = datetime.datetime.combine(datetime.date.today(), fin) - datetime.datetime.combine(
            datetime.date.today(), debut
        )
        return max(0, int(d.total_seconds() // 60))

    @staticmethod
    def _ajouter_minutes(heure: datetime.time, minutes: int) -> datetime.time:
        """Retourne l'heure résultant de l'ajout de minutes."""
        dt = datetime.datetime.combine(datetime.date.today(), heure) + datetime.timedelta(minutes=minutes)
        return dt.time()

    @staticmethod
    def _occupation_details_salles(
        salles_module: list[str],
        date_debut: datetime.date,
        date_fin: datetime.date,
        groupe_id: int,
        *,
        masquer_noms_formations: bool = False,
    ) -> str:
        """Résumé des occupations de salles (délègue à ``planning.occupations``)."""
        return planning_occupations.occupation_details_salles(
            salles_module,
            date_debut,
            date_fin,
            groupe_id,
            masquer_noms_formations=masquer_noms_formations,
        )

    @staticmethod
    def _charger_occupations_existantes(
        groupe_id: int,
    ) -> dict[tuple[datetime.date, str], list[tuple[datetime.time, datetime.time]]]:
        return planning_occupations.charger_occupations_existantes(groupe_id)

    @staticmethod
    def _charger_occupations_modules_existantes(
        groupe_id: int, formation_id: int
    ) -> tuple[set[tuple[datetime.date, int, str, str]], set[tuple[datetime.date, int]]]:
        return planning_occupations.charger_occupations_modules_existantes(groupe_id, formation_id)

    @staticmethod
    def _salles_eligibles_hors_occupation_module_intergroupes(
        salles_module: list[str],
        current_date: datetime.date,
        module_id: int,
        occ_par_jour: dict[tuple[datetime.date, int, str], set[str]],
        occ_sans_salle: set[tuple[datetime.date, int]],
        max_salles_simultanees_module: int,
        salle_localisations: dict[str, tuple[str, str, int]],
    ) -> list[str]:
        return planning_occupations.salles_eligibles_hors_occupation_module_intergroupes(
            salles_module,
            current_date,
            module_id,
            occ_par_jour,
            occ_sans_salle,
            max_salles_simultanees_module,
            salle_localisations,
        )

    @staticmethod
    def _indexer_occupations_modules_triples(
        occ_quadruples: set[tuple[datetime.date, int, str, str]],
    ) -> dict[tuple[datetime.date, int, str], set[str]]:
        return planning_occupations.indexer_occupations_modules_triples(occ_quadruples)

    def _charger_occupations_formateurs_existantes(self, groupe_id: int) -> dict[tuple[datetime.date, str], int]:
        return planning_trainers.charger_occupations_formateurs_existantes(groupe_id)

    def _charger_formateurs_par_module_date_salle_formation(
        self, formation_id: int, groupe_id: int
    ) -> dict[tuple[datetime.date, int], dict[str, str]]:
        return planning_trainers.charger_formateurs_par_module_date_salle_formation(formation_id, groupe_id)

    def _enregistrer_formateur_meme_module_autre_salle(
        self,
        mapping: dict[tuple[datetime.date, int], dict[str, str]],
        date_val: datetime.date,
        module_id: int,
        salle_nom: str,
        formateur: dict[str, str],
    ) -> None:
        planning_trainers.enregistrer_formateur_meme_module_autre_salle(
            mapping, date_val, module_id, salle_nom, formateur
        )

    @staticmethod
    def _formateur_key(formateur: dict[str, str]) -> str:
        return planning_trainers.formateur_key(formateur)

    @staticmethod
    def _formateur_from_seance(seance: Seance) -> dict[str, str]:
        return planning_trainers.formateur_from_seance(seance)

    def _formateur_disponible(
        self,
        occupations: dict[tuple[datetime.date, str], int],
        date: datetime.date,
        formateur: dict[str, str],
        max_seances_jour: int,
    ) -> bool:
        return planning_trainers.formateur_disponible(occupations, date, formateur, max_seances_jour)

    def _reserver_formateur(
        self,
        occupations: dict[tuple[datetime.date, str], int],
        date: datetime.date,
        formateur: dict[str, str],
    ) -> None:
        planning_trainers.reserver_formateur(occupations, date, formateur)

    @staticmethod
    def _dict_formateur_depuis_instance(formateur) -> dict[str, str]:
        return planning_trainers.dict_formateur_depuis_instance(formateur)

    @staticmethod
    def _dict_formateur_vide() -> dict[str, str]:
        return planning_trainers.dict_formateur_vide()

    @staticmethod
    def _formateur_dict_est_renseigne(f: dict[str, str]) -> bool:
        return planning_trainers.formateur_dict_est_renseigne(f)

    @staticmethod
    def _build_formateurs_pool(groupe) -> dict[int, dict[str, str]]:
        return planning_trainers.build_formateurs_pool(groupe)

    def _choisir_formateur_disponible(
        self,
        occupations_formateurs: dict[tuple[datetime.date, str], int],
        affectations_formateur: dict[int, dict[str, str]],
        module_id: int,
        module_specialite_id: Optional[int],
        date: datetime.date,
        max_seances_jour: int,
        fallback: dict[str, str],
        *,
        specialite_ids: Optional[frozenset[int]] = None,
        salle_nom: str = "",
        occ_formateur_par_salle_meme_module: Optional[dict[tuple[datetime.date, int], dict[str, str]]] = None,
        formateurs_par_specialites_cache: Optional[dict[tuple[int, ...], list[dict[str, str]]]] = None,
    ) -> dict[str, str]:
        return planning_trainers.choisir_formateur_disponible(
            occupations_formateurs,
            affectations_formateur,
            module_id,
            module_specialite_id,
            date,
            max_seances_jour,
            fallback,
            specialite_ids=specialite_ids,
            salle_nom=salle_nom,
            occ_formateur_par_salle_meme_module=occ_formateur_par_salle_meme_module,
            formateurs_par_specialites_cache=formateurs_par_specialites_cache,
        )

    @staticmethod
    def _salle_disponible(
        occupations: dict[tuple[datetime.date, str], list[tuple[datetime.time, datetime.time]]],
        date: datetime.date,
        salle_nom: str,
        heure_debut: datetime.time,
        heure_fin: datetime.time,
        *,
        salle_id: Optional[int] = None,
    ) -> bool:
        return planning_occupations.salle_disponible(
            occupations, date, salle_nom, heure_debut, heure_fin, salle_id=salle_id
        )

    @staticmethod
    def _reserver_creneau(
        occupations: dict[tuple[datetime.date, str], list[tuple[datetime.time, datetime.time]]],
        date: datetime.date,
        salle_nom: str,
        heure_debut: datetime.time,
        heure_fin: datetime.time,
        *,
        salle_id: Optional[int] = None,
    ) -> None:
        planning_occupations.reserver_creneau(occupations, date, salle_nom, heure_debut, heure_fin, salle_id=salle_id)

    @staticmethod
    def _etendre_seances_avec_reliquat(
        seances_module: list,
        seances_groupe: list,
        minutes_restants: int,
        occupations: dict[tuple[datetime.date, str], list[tuple[datetime.time, datetime.time]]],
    ) -> int:
        """
        Étend les séances déjà placées d'un module pour absorber le reliquat d'heures non
        planifié, par paliers de 30 min, avec un maximum de +60 min cumulés par séance.

        Les horaires matin/soir par défaut du groupe ne sont plus prioritaires : ils ont déjà
        servi de base à la planification. Le complément peut donc déborder la borne du créneau
        matin/soir tant que :
          - la séance ne dépasse pas minuit ;
          - la salle reste libre sur l'extension (aucune réservation tierce) ;
          - aucune autre séance du même groupe sur la même date n'est chevauchée.

        Retourne le reliquat restant après extension (peut rester > 0 si toutes les séances
        sont saturées ou bloquées par un chevauchement).
        """
        if minutes_restants <= 0 or not seances_module:
            return minutes_restants

        pas = 30
        max_extension_par_seance = 60
        extensions: dict[int, int] = {id(s): 0 for s in seances_module}
        minuit = datetime.time(23, 59)

        for _ in range(max_extension_par_seance // pas):
            if minutes_restants <= 0:
                break
            progres = False
            for s in seances_module:
                if minutes_restants <= 0:
                    break
                deja_etendu = extensions[id(s)]
                if deja_etendu >= max_extension_par_seance:
                    continue
                ajout = min(pas, minutes_restants, max_extension_par_seance - deja_etendu)
                new_fin = PlanningService._ajouter_minutes(s.heure_fin, ajout)
                # Ne pas franchir minuit (sinon date wrap involontaire)
                if new_fin <= s.heure_fin or new_fin > minuit:
                    continue
                # Pas de chevauchement avec une autre séance du même groupe le même jour.
                conflit_groupe = False
                for autre in seances_groupe:
                    if autre is s or autre.date != s.date:
                        continue
                    if s.heure_fin < autre.heure_fin and new_fin > autre.heure_debut:
                        conflit_groupe = True
                        break
                if conflit_groupe:
                    continue
                # Pas de chevauchement avec une autre réservation (autres groupes) sur la salle.
                salle = (s.salle_nom or "").strip().upper()
                salle_id = getattr(s, "salle_id", None)
                if salle and not PlanningService._salle_disponible(
                    occupations, s.date, salle, s.heure_fin, new_fin, salle_id=salle_id
                ):
                    continue
                if salle or salle_id:
                    PlanningService._reserver_creneau(
                        occupations, s.date, salle, s.heure_fin, new_fin, salle_id=salle_id
                    )
                s.heure_fin = new_fin
                s.duree_minutes = (s.duree_minutes or 0) + ajout
                extensions[id(s)] = deja_etendu + ajout
                minutes_restants -= ajout
                progres = True
            if not progres:
                break

        return minutes_restants

    @staticmethod
    def _split_noms(valeur: str) -> list[str]:
        return planning_locations.split_noms(valeur)

    @staticmethod
    def _split_noms_salles_uniques(valeur: str) -> list[str]:
        return planning_locations.split_noms_salles_uniques(valeur)

    @staticmethod
    def _auto_renseigner_localisation_module(
        formation_module,
        salle_nom: str,
        localisations: dict[str, tuple[str, str, int]],
    ) -> None:
        """
        Intentionnellement vide : l'auto-complétion du bâtiment sur le FormationModule
        a été supprimée car elle réduisait le pool de salles lors des générations suivantes.

        Chaque séance porte déjà son propre ``batiment_nom`` résolu depuis la salle choisie
        (via ``_batiment_pour_salle``). Il n'est pas nécessaire de persister ce champ sur
        le programme pédagogique — cela figerait le bâtiment et ignorerait les autres
        bâtiments du site lors des regénérations.
        """

    def _choisir_salle_disponible(
        self,
        occupations: dict[tuple[datetime.date, str], list[tuple[datetime.time, datetime.time]]],
        date: datetime.date,
        salles: list[str],
        heure_debut: datetime.time,
        heure_fin: datetime.time,
        effectif: int,
        localisations: dict[str, tuple[str, str, int]],
        module_id: int,
        max_seances_jour: int,
        module_salle_counts: dict[tuple[datetime.date, int, str], int],
        salle_usage_counts: dict[str, int],
        module_salle_usage_counts: dict[tuple[int, str], int],
        score_weights: tuple[int, int, int],
        salle_ids: Optional[dict[str, int]] = None,
        salle_fixe_module: str = "",
        tolerance_capacite_salle: int = 0,
        periodes_disponibilite_sites: Optional[dict[str, list[tuple[datetime.date, datetime.date]]]] = None,
    ) -> tuple[str, Optional[int]]:
        """Retourne (nom_salle, salle_id) de la meilleure salle disponible."""
        return planning_rooms.choisir_salle_disponible(
            occupations,
            date,
            salles,
            heure_debut,
            heure_fin,
            effectif,
            localisations,
            module_id,
            max_seances_jour,
            module_salle_counts,
            salle_usage_counts,
            module_salle_usage_counts,
            score_weights,
            salle_ids=salle_ids,
            salle_fixe_module=salle_fixe_module,
            tolerance_capacite_salle=tolerance_capacite_salle,
            periodes_disponibilite_sites=periodes_disponibilite_sites,
        )

    @staticmethod
    def _score_salle_candidate(
        salle_nom: str,
        effectif: int,
        localisations: dict[str, tuple[str, str, int]],
        module_id: int,
        salle_usage_counts: dict[str, int],
        module_salle_usage_counts: dict[tuple[int, str], int],
        score_weights: tuple[int, int, int],
    ) -> tuple[int, int, str]:
        return planning_rooms.score_salle_candidate(
            salle_nom,
            effectif,
            localisations,
            module_id,
            salle_usage_counts,
            module_salle_usage_counts,
            score_weights,
        )

    def _filtrer_salles_explicites_dispatch_site_batiment(
        self,
        salles: list[str],
        sites_module: set[str],
        batiments_module: set[str],
        localisations: dict[str, tuple[str, str, int]],
        formation_module,
    ) -> list[str]:
        return planning_rooms.filtrer_salles_explicites_dispatch_site_batiment(
            salles, sites_module, batiments_module, localisations, formation_module
        )

    def _salles_candidates(
        self,
        formation_module,
        localisations: dict[str, tuple[str, str, int]],
        *,
        salles_par_site_batiment: Optional[dict[str, dict[str, list[str]]]] = None,
        union_sites_programme: Optional[frozenset[str]] = None,
    ) -> list[str]:
        return planning_rooms.salles_candidates(
            formation_module,
            localisations,
            salles_par_site_batiment=salles_par_site_batiment,
            union_sites_programme=union_sites_programme,
        )

    @staticmethod
    def _indexer_salles_par_site_batiment(
        localisations: dict[str, tuple[str, str, int]],
    ) -> dict[str, dict[str, list[str]]]:
        return planning_locations.indexer_salles_par_site_batiment(localisations)

    @staticmethod
    def _charger_periodes_disponibilite_sites() -> dict[str, list[tuple[datetime.date, datetime.date]]]:
        return planning_locations.charger_periodes_disponibilite_sites()

    @staticmethod
    def _site_disponible_a_date(
        site_nom: str,
        date: datetime.date,
        periodes_par_site: dict[str, list[tuple[datetime.date, datetime.date]]],
    ) -> bool:
        return planning_locations.site_disponible_a_date(site_nom, date, periodes_par_site)

    @staticmethod
    def _charger_localisations_salles() -> tuple[dict[str, tuple[str, str, int]], dict[str, int]]:
        return planning_locations.charger_localisations_salles()

    @staticmethod
    def _site_pour_salle(salle_nom: str, mapping: dict[str, tuple[str, str, int]], fallback_sites: list[str]) -> str:
        return planning_locations.site_pour_salle(salle_nom, mapping, fallback_sites)

    @staticmethod
    def _batiment_pour_salle(
        salle_nom: str, mapping: dict[str, tuple[str, str, int]], fallback_batiments: list[str]
    ) -> str:
        return planning_locations.batiment_pour_salle(salle_nom, mapping, fallback_batiments)
