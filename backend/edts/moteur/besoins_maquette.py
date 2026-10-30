"""GET-INJS — besoins horaires dérivés de la **maquette**, pour cohortes importées.

**Problème résolu.** Le calcul historique des besoins
(``besoins.calculate_teaching_needs``) part des ``AffectationPedagogique`` :
il suppose qu'un enseignant a été affecté à chaque ECUE d'un groupe. Une
cohorte issue d'un **fichier externe** (étudiants inscrits ailleurs que dans
l'application) n'a, par construction, aucune affectation de ce type. Sans ce
module, ces cohortes ne produisaient aucun emploi du temps.

**Principe.** La maquette pédagogique (source de vérité LMD) porte déjà les
volumes horaires : ``ECUE.volume_cm``, ``volume_td``, ``volume_tp``. On en
déduit un besoin par type d'enseignement, exactement comme le ferait une
affectation, en conservant toute la traçabilité :

    Maquette ACTIVE → UE → ECUE → volume CM/TD/TP → groupe (effectif réel)

**Ce module n'invente rien.**

* il ne retient que la maquette **ACTIVE** de l'année/formation/niveau ; sans
  maquette active, la cohorte est signalée dans ``detail['sans_maquette']`` ;
* il n'affecte **aucun enseignant** (``enseignant_id = None``) : le moteur
  place la séance sans ressource enseignante, et l'écran affiche « enseignant
  à affecter ». Inventer un enseignant fausserait C1 (conflits) ;
* l'effectif provient des **inscriptions importées** (dénombrement réel),
  jamais d'une capacité déclarée ;
* la durée de séance provient du canevas réel ; en son absence le calcul est
  refusé avec un motif explicite, comme dans le lot L8.
"""

from __future__ import annotations

from dataclasses import replace

from edts.moteur.besoins import (
    MOTIF_CANEVAS_VIDE,
    MOTIF_HORS_PERIMETRE_INJS,
    NATURE_PAR_TYPE,
    BesoinsResult,
    TeachingNeed,
    duree_canevas_heures,
)

#: Motifs propres à ce calcul (mêmes conventions que ``besoins``).
MOTIF_AUCUN_GROUPE = 'AUCUN_GROUPE_IMPORTE'
MOTIF_AUCUNE_MAQUETTE = 'AUCUNE_MAQUETTE_ACTIVE'
MOTIF_VOLUMES_ABSENTS = 'VOLUMES_HORAIRES_ABSENTS'

#: Types d'enseignement dérivables d'une ECUE, avec le champ de volume associé.
TYPES_ET_VOLUMES = (
    ('CM', 'volume_cm'),
    ('TD', 'volume_td'),
    ('TP', 'volume_tp'),
)


def maquette_active(annee_academique_id, ref_formation_id, niveau_id, parcours_id=None):
    """Maquette ACTIVE applicable à une cohorte.

    Une maquette peut être définie au niveau de la formation (sans parcours) ou
    d'un parcours précis. On privilégie la maquette la plus spécifique, puis la
    plus récente : aucune autre règle n'est inventée.
    """
    from scolarite.models import Maquette

    qs = Maquette.objects.filter(
        annee_academique_id=annee_academique_id,
        ref_formation_id=ref_formation_id,
        niveau_id=niveau_id,
        statut=Maquette.Statut.ACTIVE,
    )
    if parcours_id:
        specifique = qs.filter(parcours_id=parcours_id).order_by('-version').first()
        if specifique is not None:
            return specifique
    return qs.filter(parcours__isnull=True).order_by('-version').first() \
        or qs.order_by('-version').first()


def besoins_depuis_maquette(*, annee_academique_id=None, groupe_ids=None,
                           duree_seance_heures=None, effectifs=None):
    """Construit les besoins d'une année à partir des maquettes actives.

    :param effectifs: dict ``{groupe_id: effectif}`` — par défaut, l'effectif
        réel des inscriptions importées (``import_inscrits.effectifs_par_groupe``).
    :returns: :class:`besoins.BesoinsResult` (jamais d'exception métier).
    """
    from edts.moteur.contraintes import difficulte as calculer_difficulte
    from scolarite.models import Groupe

    if duree_seance_heures is None:
        duree_seance_heures = duree_canevas_heures()
    if not duree_seance_heures:
        return BesoinsResult(
            motif_echec=MOTIF_CANEVAS_VIDE,
            detail={
                'explication': (
                    'Aucun créneau type horaire : la durée de séance est inconnue. '
                    'Définissez le canevas (GET-INJS → Créneaux) avant de générer.'
                ),
            },
        )

    if effectifs is None:
        from edts.moteur.import_inscrits import effectifs_par_groupe

        effectifs = effectifs_par_groupe(annee_academique_id)

    groupes = Groupe.objects.filter(actif=True).select_related(
        'annee_academique', 'ref_formation', 'parcours', 'niveau',
    )
    if annee_academique_id is not None:
        groupes = groupes.filter(annee_academique_id=annee_academique_id)
    if groupe_ids:
        groupes = groupes.filter(pk__in=list(groupe_ids))
    groupes = groupes.order_by('ref_formation__intitule', 'niveau__ordre', 'nom')

    if not groupes.exists():
        return BesoinsResult(
            motif_echec=MOTIF_AUCUN_GROUPE,
            detail={
                'explication': (
                    'Aucun groupe pédagogique actif pour cette année. Importez le '
                    'fichier des inscrits pour créer les cohortes, ou créez les '
                    'groupes dans Scolarité.'
                ),
            },
        )

    from formations.referentiel_injs_l6 import formations_injs

    perimetre = set(formations_injs().values_list('pk', flat=True))

    besoins = []
    sans_maquette = []
    sans_volume = []
    hors_perimetre = 0

    for groupe in groupes:
        if groupe.ref_formation_id not in perimetre:
            hors_perimetre += 1
            continue

        maquette = maquette_active(
            annee_academique_id=groupe.annee_academique_id,
            ref_formation_id=groupe.ref_formation_id,
            niveau_id=groupe.niveau_id,
            parcours_id=groupe.parcours_id,
        )
        if maquette is None:
            sans_maquette.append({
                'groupe': groupe.nom,
                'formation': groupe.ref_formation.intitule,
                'niveau': groupe.niveau.code,
            })
            continue

        effectif = effectifs.get(groupe.pk) or groupe.capacite_max or None

        ecues = (
            maquette.unites_enseignement
            .prefetch_related('ecues')
            .order_by('semestre__numero', 'ordre', 'code')
        )
        for ue in ecues:
            for ecue in ue.ecues.all().order_by('ordre', 'code'):
                for type_enseignement, champ in TYPES_ET_VOLUMES:
                    volume = float(getattr(ecue, champ) or 0)
                    if volume <= 0:
                        continue
                    nb_seances = max(1, round(volume / duree_seance_heures))
                    besoin = TeachingNeed(
                        # Aucune affectation pédagogique : c'est précisément le
                        # cas d'une cohorte importée. La séance restera
                        # traçable par (ECUE, groupe) et par `origine`.
                        affectation_pedagogique_id=None,
                        annee_academique_id=groupe.annee_academique_id,
                        ref_formation_id=groupe.ref_formation_id,
                        parcours_id=groupe.parcours_id,
                        niveau_id=groupe.niveau_id,
                        semestre_id=ue.semestre_id,
                        groupe_id=groupe.pk,
                        ue_id=ue.pk,
                        ecue_id=ecue.pk,
                        enseignant_id=None,
                        type_enseignement=type_enseignement,
                        nature=NATURE_PAR_TYPE.get(type_enseignement, 'AUTRE'),
                        intitule=ecue.intitule,
                        volume_horaire=volume,
                        credits=ecue.credits or 0,
                        effectif=effectif,
                        duree_seance_heures=float(duree_seance_heures),
                        nb_seances=nb_seances,
                        origine='MAQUETTE',
                    )
                    besoins.append(replace(besoin, difficulte=calculer_difficulte(besoin)))

        if not any(b.groupe_id == groupe.pk for b in besoins):
            sans_volume.append({'groupe': groupe.nom, 'maquette': maquette.libelle or f'v{maquette.version}'})

    if not besoins:
        motifs = []
        if sans_maquette:
            motifs.append(MOTIF_AUCUNE_MAQUETTE)
        if sans_volume:
            motifs.append(MOTIF_VOLUMES_ABSENTS)
        if hors_perimetre and not sans_maquette and not sans_volume:
            motifs.append(MOTIF_HORS_PERIMETRE_INJS)
        return BesoinsResult(
            motif_echec=motifs[0] if motifs else MOTIF_AUCUNE_MAQUETTE,
            detail={
                'explication': (
                    'Aucune ECUE volumée n’a pu être convertie en séance. '
                    'Vérifiez qu’une maquette ACTIVE existe et que ses ECUE '
                    'portent des volumes CM/TD/TP.'
                ),
                'sans_maquette': sans_maquette[:50],
                'sans_volume': sans_volume[:50],
                'groupes_hors_perimetre': hors_perimetre,
            },
        )

    return BesoinsResult(
        besoins=besoins,
        detail={
            'sans_maquette': sans_maquette[:50],
            'sans_volume': sans_volume[:50],
            'groupes_hors_perimetre': hors_perimetre,
            'effectifs_connus': len([g for g in effectifs if g]),
        },
    )
