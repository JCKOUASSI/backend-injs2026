"""
Services de l'app parametrage.
Logique métier pour Grade, Vague, ParametreGeneral et associations modules/types.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from django.db import transaction

from apps.referentiels.repositories import ModuleRepository, TypeFormationRepository
from shared.utils.grades import grade_cible_matches

from .models import (
    Batiment,
    Grade,
    JourFerie,
    ModuleTypeFormation,
    ParametreFormation,
    ParametreGeneral,
    PeriodeDisponibiliteSite,
    Salle,
    Site,
    Vague,
    get_parametres_pour_formation,
)
from .repositories import (
    GradeRepository,
    ParametreFormationRepository,
    ParametreGeneralRepository,
    VagueRepository,
)

logger = logging.getLogger("apps.parametrage")


@dataclass
class ParametrageContext:
    """
    Agrège toutes les données nécessaires à l'affichage de la page paramétrage.
    Construit par ParametrageService.get_context().
    """

    types_formation: list
    modules: list
    grades: list
    vagues: list
    sites: list
    batiments: list
    salles: list
    jours_feries: list
    periodes_disponibilite_sites: list
    parametres_defaut: ParametreGeneral
    formations: list
    formation_selectionnee: object | None
    parametres_formation: ParametreFormation | None
    stats: dict


@dataclass
class ModuleAssociationData:
    """Données pour associer un module à un type de formation avec volume horaire par défaut."""

    module_id: int
    type_formation_id: int
    grade_cible: str
    volume_horaire_defaut: int


class ParametrageService:
    """
    Service principal de la page paramétrage.
    Agrège et orchestre tous les référentiels configurables.
    """

    def __init__(
        self,
        grade_repo: GradeRepository,
        vague_repo: VagueRepository,
        parametre_repo: ParametreGeneralRepository,
        type_form_repo: TypeFormationRepository,
        module_repo: ModuleRepository,
    ) -> None:
        self._grade_repo = grade_repo
        self._vague_repo = vague_repo
        self._parametre_repo = parametre_repo
        self._type_form_repo = type_form_repo
        self._module_repo = module_repo

    def get_context(self, user, formation_id: int | None = None) -> ParametrageContext:
        """
        Retourne toutes les données nécessaires à la page paramétrage en un seul appel.
        Utilisé par la vue GET.
        """
        from shared.formations_scope import queryset_formations

        types = list(self._type_form_repo.list_all())
        modules = list(self._module_repo.list_all_with_associations())
        grades = list(self._grade_repo.list_all())
        vagues = list(self._vague_repo.list_all())
        sites = list(Site.objects.order_by("-actif", "nom"))
        batiments = list(Batiment.objects.select_related("site").order_by("-actif", "nom"))
        salles = list(Salle.objects.select_related("batiment", "batiment__site").order_by("-actif", "nom"))
        jours_feries = list(JourFerie.objects.filter(actif=True).order_by("date"))
        periodes_disponibilite_sites = list(
            PeriodeDisponibiliteSite.objects.select_related("site")
            .filter(site__actif=True)
            .order_by("site__nom", "date_debut")
        )
        params_defaut = self._parametre_repo.get()
        formations = list(queryset_formations(user).order_by("-date_debut", "intitule"))
        formation_selectionnee = None
        parametres_formation = None
        if formations:
            if formation_id is not None:
                formation_selectionnee = next((f for f in formations if f.pk == formation_id), None)
            if formation_selectionnee is None:
                formation_selectionnee = formations[0]
            parametres_formation = get_parametres_pour_formation(formation_selectionnee.pk)

        stats = {
            "nb_types": len(types),
            "nb_modules": len(modules),
            "nb_grades": len(grades),
            "nb_vagues": len(vagues),
            "nb_sites": sum(1 for s in sites if s.actif),
            "nb_sites_total": len(sites),
            "nb_batiments": sum(1 for b in batiments if b.actif),
            "nb_batiments_total": len(batiments),
            "nb_salles": sum(1 for sl in salles if sl.actif),
            "nb_salles_total": len(salles),
            "nb_jours_feries": len(jours_feries),
            "nb_periodes_disponibilite_sites": len(periodes_disponibilite_sites),
        }

        return ParametrageContext(
            types_formation=types,
            modules=modules,
            grades=grades,
            vagues=vagues,
            sites=sites,
            batiments=batiments,
            salles=salles,
            jours_feries=jours_feries,
            periodes_disponibilite_sites=periodes_disponibilite_sites,
            parametres_defaut=params_defaut,
            formations=formations,
            formation_selectionnee=formation_selectionnee,
            parametres_formation=parametres_formation,
            stats=stats,
        )


class GradeService:
    """Logique métier pour la gestion des grades."""

    def __init__(self, repo: GradeRepository) -> None:
        self._repo = repo

    def creer(self, libelle: str, ordre: int = 0) -> Grade:
        """
        Crée un grade.
        Lève ValueError si le libellé existe déjà.
        """
        if Grade.objects.filter(libelle__iexact=libelle).exists():
            raise ValueError(f"Le grade '{libelle}' existe déjà.")
        return self._repo.save(Grade(libelle=libelle.strip().upper(), ordre=ordre))

    @transaction.atomic
    def supprimer(self, pk: int) -> None:
        """
        Supprime un grade.
        Lève ValueError si des auditeurs l'utilisent.
        """
        from apps.auditeurs.models import Auditeur

        grade = Grade.objects.filter(pk=pk).first()
        if grade is None:
            raise ValueError(f"Grade {pk} introuvable.")
        if Auditeur.objects.filter(grade=grade.libelle).exists():
            raise ValueError("Ce grade est utilisé par des auditeurs et ne peut pas être supprimé.")
        self._repo.delete(pk)

    def toggle_actif(self, pk: int) -> Grade:
        """Active ou désactive un grade."""
        grade = self._repo.get_by_id(pk)
        if grade is None:
            raise ValueError(f"Grade {pk} introuvable.")
        grade.actif = not grade.actif
        return self._repo.save(grade)

    def list_all(self):
        """Retourne tous les grades."""
        return self._repo.list_all()


class VagueService:
    """Logique métier pour la gestion des vagues."""

    def __init__(self, repo: VagueRepository) -> None:
        self._repo = repo

    def creer(self, libelle: str) -> Vague:
        """
        Crée une vague.
        Lève ValueError si le libellé existe déjà.
        """
        if Vague.objects.filter(libelle__iexact=libelle).exists():
            raise ValueError(f"La vague '{libelle}' existe déjà.")
        return self._repo.save(Vague(libelle=libelle.strip()))

    @transaction.atomic
    def supprimer(self, pk: int) -> None:
        """
        Supprime une vague.
        Lève ValueError si des formations l'utilisent.
        """
        from apps.formations.models import Formation

        vague = Vague.objects.filter(pk=pk).first()
        if vague is None:
            raise ValueError(f"Vague {pk} introuvable.")
        if Formation.objects.filter(vague=vague.libelle).exists():
            raise ValueError("Cette vague est utilisée par des formations existantes.")
        self._repo.delete(pk)

    def list_all(self):
        """Retourne toutes les vagues."""
        return self._repo.list_all()


class ParametreGeneralService:
    """Logique métier pour les paramètres généraux (singleton)."""

    def __init__(self, repo: ParametreGeneralRepository) -> None:
        self._repo = repo

    def get(self) -> ParametreGeneral:
        """Retourne l'instance singleton des paramètres généraux."""
        return self._repo.get()

    @transaction.atomic
    def mettre_a_jour(self, data: dict) -> ParametreGeneral:
        """
        Met à jour les paramètres généraux.
        data keys : max_auditeurs_groupe_defaut, matin_heure_debut_defaut,
                    matin_heure_fin_defaut, soir_heure_debut_defaut,
                    soir_heure_fin_defaut, jours_defaut (list[int])
        """
        params = self._repo.get()
        for key, value in data.items():
            if hasattr(params, key):
                setattr(params, key, value)
        return self._repo.save(params)


class ParametreFormationService:
    """Logique métier pour les paramètres de planification d'une formation."""

    def __init__(self, repo: ParametreFormationRepository) -> None:
        self._repo = repo

    def get_for_formation(self, formation_id: int) -> ParametreFormation:
        """Retourne les paramètres de la formation."""
        return self._repo.get_for_formation(formation_id)

    @transaction.atomic
    def mettre_a_jour(self, formation_id: int, data: dict) -> ParametreFormation:
        """Met à jour les paramètres de planification d'une formation."""
        params = self._repo.get_for_formation(formation_id)
        for key, value in data.items():
            if hasattr(params, key):
                setattr(params, key, value)
        return self._repo.save(params)


class ModuleParametrageService:
    """
    Logique métier pour la gestion des modules dans le paramétrage.
    Gère le référentiel global ET les associations par type de formation.
    """

    def __init__(
        self,
        module_repo: ModuleRepository,
        type_form_repo: TypeFormationRepository,
    ) -> None:
        self._module_repo = module_repo
        self._type_form_repo = type_form_repo

    def creer_module(self, titre: str) -> object:
        """Crée un module dans le référentiel global."""
        from apps.referentiels.models import Module
        from apps.referentiels.services import ModuleService

        if Module.objects.filter(titre__iexact=titre).exists():
            raise ValueError(f"Le module '{titre}' existe déjà.")
        service = ModuleService(self._module_repo)
        return service.get_or_create(titre).module

    @transaction.atomic
    def associer_a_type(self, data: ModuleAssociationData) -> ModuleTypeFormation:
        """
        Associe un module à un type de formation avec un volume horaire par défaut.
        Crée ou met à jour le ModuleTypeFormation correspondant.
        """
        obj, _ = ModuleTypeFormation.objects.update_or_create(
            module_id=data.module_id,
            type_formation_id=data.type_formation_id,
            grade_cible=(data.grade_cible or "").strip().upper(),
            defaults={"volume_horaire_defaut": data.volume_horaire_defaut},
        )
        return obj

    @transaction.atomic
    def dissocier(self, association_id: int) -> None:
        """Supprime l'association identifiée par son id."""
        ModuleTypeFormation.objects.filter(pk=association_id).delete()


def resolve_module_type_formation_association(
    assoc_qs,
    grade_value: str,
    *,
    allow_generic_fallback: bool,
) -> ModuleTypeFormation | None:
    """
    Choisit la ligne ModuleTypeFormation pour un grade d'auditeur / groupe.

    Si ``allow_generic_fallback`` est False, on n'utilise pas la règle à grade vide
    (volume « tous grades » du paramétrage).
    """
    grade_norm = (grade_value or "").strip().upper()
    assoc = None
    if grade_norm:
        assoc = assoc_qs.filter(grade_cible=grade_norm).first()
        if assoc is None:
            associations_grade = [
                a
                for a in assoc_qs.exclude(grade_cible="")
                if grade_cible_matches((a.grade_cible or "").strip(), grade_norm)
            ]
            if associations_grade:
                assoc = sorted(
                    associations_grade,
                    key=lambda a: len((a.grade_cible or "").strip()),
                    reverse=True,
                )[0]
    if assoc is None and allow_generic_fallback:
        assoc = assoc_qs.filter(grade_cible="").first()
    return assoc


def _assoc_volume_parametrage(
    module_id: int,
    type_formation_id: int,
    grade_principal: str,
    *,
    exige_ligne_grade_si_connu: bool,
) -> ModuleTypeFormation | None:
    """
    Résout la ligne ``ModuleTypeFormation`` pour type × module × grade.

    Si ``exige_ligne_grade_si_connu`` est True et que le grade du groupe est renseigné,
    on n'utilise pas le repli sur la ligne à ``grade_cible`` vide (volume « tous grades »).
    """
    assoc_qs = ModuleTypeFormation.objects.filter(
        module_id=module_id,
        type_formation_id=type_formation_id,
    )
    grade_norm = (grade_principal or "").strip().upper()
    if exige_ligne_grade_si_connu and grade_norm:
        return resolve_module_type_formation_association(assoc_qs, grade_principal, allow_generic_fallback=False)
    assoc = resolve_module_type_formation_association(assoc_qs, grade_principal, allow_generic_fallback=False)
    if assoc is None:
        return resolve_module_type_formation_association(assoc_qs, grade_principal, allow_generic_fallback=True)
    return assoc


def volume_horaire_effectif_formation_module_pour_dispatch(
    module_id: int,
    volume_horaire_stocke: int | None,
    type_formation_id: int,
    grade_principal: str,
    module_titre: str = "",
) -> int | None:
    """
    Volume pour la génération de planning par groupe.

    Si le groupe a un grade connu, il faut une règle de paramétrage **compatible avec ce grade**
    (ligne dédiée ou règle parent ex. B pour B3) : le volume « tous grades » (``grade_cible`` vide)
    ne suffit pas. Sinon le module est ignoré pour ce groupe (retour ``None``).

    Si le paramétrage (type × module) ne contient **que** des lignes à grade explicite et qu’aucune
    ne couvre le grade du groupe, le module n’est pas dispatché **même** si un volume est renseigné
    sur le module de formation (évite d’appliquer un module « réservé B3 » à un groupe A3 lorsque
    le ``grade_cible`` du module de formation est trop large ou vide).

    Si le grade du groupe est inconnu (chaîne vide), le repli sur le volume « tous grades » reste autorisé.
    """
    assoc_qs = ModuleTypeFormation.objects.filter(
        module_id=module_id,
        type_formation_id=type_formation_id,
    )
    grade_norm = (grade_principal or "").strip().upper()
    if grade_norm and assoc_qs.exists():
        strict_assoc = resolve_module_type_formation_association(
            assoc_qs, grade_principal, allow_generic_fallback=False
        )
        a_ligne_tous_grades = assoc_qs.filter(grade_cible="").exists()
        if not a_ligne_tous_grades and strict_assoc is None:
            logger.info(
                "volume_dispatch refus module_id=%s type_formation_id=%s grade=%r titre=%r : "
                "parametrage grades explicites sans ligne compatible (sans volume tous grades)",
                module_id,
                type_formation_id,
                grade_principal,
                module_titre or "",
            )
            return None

    if volume_horaire_stocke is not None:
        return int(volume_horaire_stocke)
    assoc = _assoc_volume_parametrage(
        module_id,
        type_formation_id,
        grade_principal,
        exige_ligne_grade_si_connu=bool(grade_norm),
    )
    if assoc is None:
        logger.info(
            "volume_dispatch refus module_id=%s type_formation_id=%s grade=%r titre=%r : "
            "aucune association ModuleTypeFormation exploitable pour le dispatch (volume FM vide)",
            module_id,
            type_formation_id,
            grade_principal,
            module_titre or "",
        )
        return None
    return int(assoc.volume_horaire_defaut)


def volume_horaire_effectif_formation_module(
    module_id: int,
    volume_horaire_stocke: int | None,
    type_formation_id: int,
    grade_principal: str,
    module_titre: str = "",
) -> int:
    """
    Volume en heures pour un groupe : valeur explicite sur ``FormationModule`` si renseignée,
    sinon résolution depuis le paramétrage (**type de formation × module × grade**),
    avec repli sur le volume « tous grades » si aucune règle spécifique ne matche.

    Pour le **dispatch** (planning), utiliser ``volume_horaire_effectif_formation_module_pour_dispatch`` :
    le repli « tous grades » n'est pas appliqué lorsque le grade du groupe est connu.
    """
    if volume_horaire_stocke is not None:
        return int(volume_horaire_stocke)
    assoc = _assoc_volume_parametrage(
        module_id,
        type_formation_id,
        grade_principal,
        exige_ligne_grade_si_connu=False,
    )
    if assoc is None:
        titre = module_titre or f"module #{module_id}"
        raise ValueError(
            f"Volume horaire de «{titre}» : aucune règle de paramétrage (type × module) pour le grade "
            f"{grade_principal or '—'}. Complétez le paramétrage ou saisissez un volume fixe sur le module."
        )
    return int(assoc.volume_horaire_defaut)
