"""LOT 3 — couche API LMD GET-INJS (``/api/edts/lmd/…``).

Couche **ajoutée** : aucune route existante n'est supprimée, renommée ou
modifiée. Elle expose le moteur du LOT 2 (``edts.moteur.*``) sur des chemins
dédiés, préfixés ``lmd/`` : audit, contraintes, versions, disponibilités,
créneaux, génération, validation, publication, résultat, grille, déplacement
et annulation.

L'ancien ``generer_brouillon`` (``POST /api/edts/emplois/{id}/generer/``) est
**conservé tel quel** et reste le chemin contractuel historique ; cette couche
ne le remplace pas, elle le complète.

Aucun second RBAC n'est créé : les permissions ``edts.permissions`` (L8)
s'appliquent telles quelles.
"""

from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from edts.moteur import contraintes as C
from edts.moteur import generation as G
from edts.moteur import publication as P
from edts.moteur import validation as V
from edts.moteur.besoins import calculate_teaching_needs, duree_canevas_heures
from edts.permissions import (
    IsEdtPlanification,
    IsEdtReadOnlyOrPlanification,
    IsEdtValidation,
)

# Severités d'audit : jamais présenter une donnée absente comme valide.
OK = 'OK'
WARNING = 'WARNING'
BLOCKING = 'BLOCKING'

#: Libellés métier des contraintes fortes. Une préférence n'apparaît PAS dans
#: cette liste : elle ne doit jamais être présentée comme une contrainte dure.
LIBELLES_CONTRAINTES = {
    C.C1_CONFLIT_ENSEIGNANT: 'C1 — Un enseignant ne peut pas dispenser deux séances simultanément.',
    C.C2_CONFLIT_GROUPE: 'C2 — Un groupe ne peut pas suivre deux séances simultanément.',
    C.C3_CONFLIT_SALLE: 'C3 — Une salle ne peut pas accueillir deux séances simultanément.',
    C.C4_CAPACITE: 'C4 — La capacité de la salle doit couvrir l’effectif du groupe.',
    C.C5_DISPONIBILITE_ENSEIGNANT: 'C5 — L’enseignant ne doit pas être déclaré indisponible sur le créneau.',
    C.C6_DISPONIBILITE_SALLE: 'C6 — La salle ne doit pas être déclarée indisponible sur le créneau.',
    C.C7_COMPATIBILITE_SALLE: 'C7 — Le type de salle doit être compatible avec la nature de la séance.',
    C.C8_COHERENCE_PEDAGOGIQUE: 'C8 — Chaque séance conserve son affectation pédagogique d’origine.',
    C.C9_CALENDRIER: 'C9 — La séance doit tenir dans la période dordanée (semaines de l’EDT).',
    C.C10_VOLUME: 'C10 — Le volume horaire attendu doit être entièrement couvert.',
}

LIBELLE_PREFERENCES = (
    'Préférence (non bloquante) — disponibilité « PREFERENCE » : pénalité de '
    'placement, jamais un blocage.'
)


def _int(valeur):
    try:
        return int(valeur)
    except (TypeError, ValueError):
        return None


def _booleen(valeur):
    return str(valeur).lower() in ('1', 'true', 'oui', 'yes')


def _semaines_de_requete(request):
    semaines = request.data.get('semaines')
    if isinstance(semaines, str):
        semaines = [s for s in semaines.replace(' ', '').split(',') if s]
    return [int(s) for s in semaines if str(s).isdigit()] if semaines else None


def _reponse_erreur(motif, detail, code_http=status.HTTP_409_CONFLICT):
    """Réponse métier explicite — jamais un 500 opaque."""
    return Response(
        {'status': BLOCKING, 'motif_echec': motif, 'detail': detail},
        status=code_http,
    )



def _parametres_lmd(request):
    """Récupère et valide les paramètres de périmètre LMD.

    La cohérence Année → Formation → Parcours → Niveau → Semestre → Groupe est
    vérifiée **côté serveur** : aucun dropdown ne doit proposer de valeurs
    incohérentes.
    """
    from formations.referentiel_injs_l6 import formations_injs
    from scolarite.models import AnneeAcademique, Groupe, Niveau, Parcours, Semestre

    p = request.query_params if request.method == 'GET' else request.data
    formation_id = _int(p.get('ref_formation_id') or p.get('formation'))
    parcours_id = _int(p.get('parcours_id') or p.get('parcours'))
    niveau_id = _int(p.get('niveau_id') or p.get('niveau'))
    semestre_id = _int(p.get('semestre_id') or p.get('semestre'))
    groupe_ids = p.get('groupe_ids') or p.get('groupes')
    if isinstance(groupe_ids, str):
        groupe_ids = [g for g in groupe_ids.replace(' ', '').split(',') if g]
    groupe_ids = ([g for g in (_int(x) for x in groupe_ids) if g]
                  if groupe_ids else None)

    incoherence = []
    if formation_id is not None and not formations_injs().filter(pk=formation_id).exists():
        incoherence.append(
            f'La formation #{formation_id} n’est pas une formation INJS validée '
            '(périmètre L6). Les cycles legacy CPFAE/professorat sont exclus.'
        )
        formation_id = None
    if parcours_id is not None and formation_id is not None:
        if not Parcours.objects.filter(pk=parcours_id,
                                       ref_formation_id=formation_id).exists():
            incoherence.append(
                f'Le parcours #{parcours_id} n’appartient pas à la formation '
                f'#{formation_id}.'
            )
            parcours_id = None
    if niveau_id is not None and not Niveau.objects.filter(pk=niveau_id).exists():
        incoherence.append(f'Le niveau #{niveau_id} est introuvable.')
        niveau_id = None
    if semestre_id is not None and niveau_id is not None:
        if not Semestre.objects.filter(pk=semestre_id, niveau_id=niveau_id).exists():
            incoherence.append(
                f'Le semestre #{semestre_id} n’appartient pas au niveau #{niveau_id}.'
            )
            semestre_id = None
    if groupe_ids:
        qs = Groupe.objects.filter(pk__in=groupe_ids)
        if formation_id and not qs.filter(ref_formation_id=formation_id).exists():
            incoherence.append(
                'Un ou plusieurs groupes sélectionnés n’appartiennent pas à la formation.')
            groupe_ids = None
        elif niveau_id and not qs.filter(niveau_id=niveau_id).exists():
            incoherence.append(
                'Un ou plusieurs groupes sélectionnés n’appartiennent pas au niveau.')
            groupe_ids = None
        elif parcours_id and not qs.filter(parcours_id=parcours_id).exists():
            incoherence.append(
                'Un ou plusieurs groupes sélectionnés n’appartiennent pas au parcours.')
            groupe_ids = None

    annee_id = _int(p.get('annee_academique_id') or p.get('annee'))
    if annee_id is None:
        # PRAGMATIQUE : si les seules affectations planifiables du périmètre
        # relèvent d'une seule année, c'est elle — l'assistant frontend la
        # propose de toute façon en choix n°1. À défaut, l'année courante.
        from edts.moteur.besoins import affectations_planifiables

        candidats = affectations_planifiables(
            ref_formation_id=formation_id, parcours_id=parcours_id,
            niveau_id=niveau_id, semestre_id=semestre_id, groupe_ids=groupe_ids,
        )
        annees_trouvees = sorted({a.annee_academique_id for a in candidats})
        if len(annees_trouvees) == 1:
            annee_id = annees_trouvees[0]
        else:
            courante = AnneeAcademique.objects.filter(courante=True).first()
            annee_id = courante.pk if courante else None
    if annee_id is not None and not AnneeAcademique.objects.filter(
            pk=annee_id).exists():
        incoherence.append(f'L’année académique #{annee_id} est introuvable.')
        annee_id = None
    return {
        'annee_academique_id': annee_id,
        'ref_formation_id': formation_id,
        'parcours_id': parcours_id,
        'niveau_id': niveau_id,
        'semestre_id': semestre_id,
        'groupe_ids': groupe_ids,
    }, incoherence



# ── Audit de pré-génération ──────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsEdtReadOnlyOrPlanification])
def audit_api(request):
    """GET /api/edts/lmd/audit/ — « puis-je générer ? ».

    Distingue strictement ``OK`` / ``WARNING`` / ``BLOCKING``. **Une donnée
    absente n'est jamais présentée comme valide** : elle produit un WARNING ou
    un BLOCKING avec son code, son explication et l'action recommandée.
    """
    from edts.models import CreneauTemplate
    from formations.models import RefSalle

    params, incoherences = _parametres_lmd(request)
    controles = []

    def ajouter(niveau, code, message, action='', detail=None):
        controles.append({
            'niveau': niveau, 'code': code, 'message': message,
            'action_recommandee': action, 'detail': detail or {},
        })

    if params['annee_academique_id'] is None:
        ajouter(BLOCKING, 'ANNEE_ACADEMIQUE_ABSENTE',
                'Aucune année académique sélectionnée ou courante.',
                'Sélectionnez une année académique avant de générer.')
    for message in incoherences:
        ajouter(BLOCKING, 'CHAINE_LMD_INCOHERENTE', message,
                'Corrigez la sélection Année → Formation → Parcours → Niveau → '
                'Semestre → Groupe.')

    resultat = calculate_teaching_needs(**params)
    if resultat.vide:
        ajouter(BLOCKING, resultat.motif_echec,
                resultat.detail.get('explication', 'Aucun besoin calculable.'),
                resultat.detail.get('action_recommandee', ''), resultat.detail)
    else:
        ajouter(OK, 'AFFECTATIONS_PEDAGOGIQUES_OK',
                f'{len(resultat.besoins)} besoin(s) d’enseignement calculé(s), '
                f'{resultat.total_heures_attendues} h attendues.',
                detail=resultat.as_dict())

    nb_creneaux = CreneauTemplate.objects.count()
    if nb_creneaux == 0:
        ajouter(BLOCKING, 'CANEVAS_HORAIRE_VIDE',
                'Aucun créneau type défini : impossible de découper les volumes '
                'horaires sans inventer une durée de séance.',
                'Configurer les créneaux horaires avant de lancer la génération.',
                {'duree_canevas_heures': duree_canevas_heures()})
    else:
        ajouter(OK, 'CANEVAS_HORAIRE_OK',
                f'{nb_creneaux} créneau(x) type(s) — durée moyenne '
                f'{duree_canevas_heures()} h.')
        # Le canevas existe, mais est-il CELUI du référentiel ? Un canevas qui
        # dérive produit des plannings plausibles et faux : le dire ici, c'est
        # le dire là où l'utilisateur pose la question « puis-je générer ? ».
        from edts.moteur import canevas_officiel as CO

        comparaison = CO.comparer_canevas([
            (c.jour, c.heure_debut, c.heure_fin)
            for c in CreneauTemplate.objects.all()
        ])
        if comparaison['chevauchements']:
            ajouter(WARNING, 'CANEVAS_CHEVAUCHEMENT',
                    f'{len(comparaison["chevauchements"])} paire(s) de créneaux se '
                    'recouvrent : les contrôles de conflit (C1/C2/C3) ne sont pas '
                    'garantis sur les intervalles communs.',
                    'Supprimer ou corriger les créneaux qui se chevauchent.',
                    {'chevauchements': comparaison['chevauchements'][:10]})
        if comparaison['manquants'] or comparaison['non_prevus']:
            ajouter(WARNING, 'CANEVAS_HORS_REFERENTIEL',
                    f'Le canevas diffère du référentiel officiel : '
                    f'{len(comparaison["manquants"])} créneau(x) officiel(s) '
                    f'manquant(s), {len(comparaison["non_prevus"])} non prévu(s).',
                    'Aligner les créneaux sur le canevas officiel '
                    '(manage.py verifier_canevas).',
                    {'manquants': comparaison['manquants'][:10],
                     'non_prevus': comparaison['non_prevus'][:10]})

    salles = list(RefSalle.objects.filter(actif=True))
    if not salles:
        ajouter(WARNING, 'AUCUNE_SALLE',
                'Aucune salle active au référentiel : les séances seront sans salle.',
                'Renseigner les salles de l’INJS au référentiel.')
    capacites_inconnues = [s for s in salles if s.capacite is None]
    if capacites_inconnues:
        ajouter(WARNING, 'CAPACITE_INCONNUE',
                f'{len(capacites_inconnues)} salle(s) sans capacité renseignée : '
                'la contrainte C4 ne peut pas être vérifiée.',
                'Renseigner la capacité des salles pour rendre C4 vérifiable.',
                {'salles_sans_capacite': [s.nom for s in capacites_inconnues[:20]]})

    if resultat.besoins:
        sans_enseignant = [b for b in resultat.besoins if not b.enseignant_id]
        if sans_enseignant:
            ajouter(WARNING, 'BESOIN_SANS_ENSEIGNANT',
                    f'{len(sans_enseignant)} besoin(s) sans enseignant : les '
                    'conflits C1/C5 ne sont pas garantis pour ces séances.',
                    'Affecter un enseignant à ces affectations pédagogiques.',
                    {'affectation_pedagogique_ids': [
                        b.affectation_pedagogique_id for b in sans_enseignant]})

    ajouter(OK, 'RESSOURCES',
            f'{len(salles)} salle(s) active(s) au référentiel.',
            detail={
                'salles_compatibles_tp': len(
                    [s for s in salles if C.compatible_salle(s, 'TP')]),
                'salles_compatibles_cm': len(
                    [s for s in salles if C.compatible_salle(s, 'COURS')]),
            })

    bloquants = [c for c in controles if c['niveau'] == BLOCKING]
    avertissements = [c for c in controles if c['niveau'] == WARNING]
    return Response({
        'statut': BLOCKING if bloquants else (WARNING if avertissements else OK),
        'generable': not bloquants,
        'controles': controles,
        'resume': {
            'ok': len(controles) - len(bloquants) - len(avertissements),
            'warning': len(avertissements),
            'blocking': len(bloquants),
        },
        'parametres': params,
    })


# ── Disponibilités (modèle LOT 1) ────────────────────────────────────────────

def _disponibilites(request, cible):
    """Lecture des disponibilités — **aucune disponibilité n'est inventée**."""
    from edts.models import DisponibiliteHoraire

    params, _incoherences = _parametres_lmd(request)
    annee_id = params['annee_academique_id']
    porteur = 'enseignant' if cible == 'enseignants' else 'salle'
    qs = DisponibiliteHoraire.objects.filter(**{f'{porteur}__isnull': False})
    if annee_id:
        qs = qs.filter(annee_academique_id=annee_id)
    qs = qs.select_related(porteur, 'annee_academique')

    lignes = [{
        'id': d.pk,
        'cible_id': getattr(d, f'{porteur}_id', None),
        'cible_nom': str(getattr(d, porteur, '')),
        'jour': d.jour,
        'heure_debut': d.heure_debut.isoformat(timespec='minutes'),
        'heure_fin': d.heure_fin.isoformat(timespec='minutes'),
        'statut': d.statut,
        'bloquant': d.statut == 'INDISPONIBLE',
        'motif': d.motif,
    } for d in qs.order_by('jour', 'heure_debut')]

    if not lignes:
        return Response({
            'cible': cible,
            'statut': WARNING,
            'code': 'AUCUNE_DISPONIBILITE',
            'message': (
                'Aucune disponibilité configurée. Le moteur la traitera comme '
                '« aucune contrainte déclarée » : ni les indisponibilités '
                '(C5/C6) ni les préférences ne pourront être vérifiées.'
            ),
            'explication': (
                'Ce n’est pas un blocage : une ressource sans déclaration est '
                'considérée comme disponible, faute de donnée métier.'
            ),
            'action_recommandee': (
                f'Déclarer les disponibilités des {cible} pour rendre les '
                'contraintes C5/C6 et les préférences vérifiables.'
            ),
            'disponibilites': [],
        })
    return Response({
        'cible': cible,
        'statut': OK,
        'nb_disponibilites': len(lignes),
        'nb_indisponibilites': len([d for d in lignes if d['bloquant']]),
        'disponibilites': lignes,
    })


@api_view(['GET'])
@permission_classes([IsEdtReadOnlyOrPlanification])
def disponibilites_enseignants_api(request):
    """GET /api/edts/lmd/availability/teachers/ — modèle ``DisponibiliteHoraire``."""
    return _disponibilites(request, 'enseignants')


@api_view(['GET'])
@permission_classes([IsEdtReadOnlyOrPlanification])
def disponibilites_salles_api(request):
    """GET /api/edts/lmd/availability/rooms/ — modèle ``DisponibiliteHoraire``."""
    return _disponibilites(request, 'salles')


# ── Créneaux (modèle CreneauTemplate unique) ─────────────────────────────────

@api_view(['GET'])
@permission_classes([IsEdtReadOnlyOrPlanification])
def slots_api(request):
    """GET /api/edts/lmd/slots/ — canevas ``CreneauTemplate``.

    Aucun deuxième modèle de créneaux. Canevas vide → ``CANEVAS_HORAIRE_VIDE``
    explicite, jamais un horaire par défaut.
    """
    from edts.models import JOUR_CHOICES, CreneauTemplate

    creneaux = list(CreneauTemplate.objects.order_by('jour', 'heure_debut'))
    if not creneaux:
        return Response({
            'statut': BLOCKING,
            'motif_echec': 'CANEVAS_HORAIRE_VIDE',
            'explication': (
                'Aucun créneau type n’est défini. Sans canevas horaire réel, le '
                'moteur ne peut pas découper les volumes horaires.'
            ),
            'action_recommandee': (
                'Configurer les créneaux horaires avant de lancer la génération.'
            ),
            'creneaux': [],
        })
    jours = dict(JOUR_CHOICES)
    ordre = {j: i for i, (j, _lib) in enumerate(JOUR_CHOICES)}
    return Response({
        'statut': OK,
        'nb_creneaux': len(creneaux),
        'duree_moyenne_heures': duree_canevas_heures(),
        'jours': sorted({c.jour for c in creneaux}, key=lambda j: ordre.get(j, 99)),
        'creneaux': [{
            'id': c.pk,
            'jour': c.jour,
            'jour_libelle': jours.get(c.jour, c.jour),
            'heure_debut': c.heure_debut.isoformat(timespec='minutes'),
            'heure_fin': c.heure_fin.isoformat(timespec='minutes'),
            'duree_heures': c.duree_heures,
        } for c in creneaux],
    })



@api_view(['GET'])
@permission_classes([IsEdtReadOnlyOrPlanification])
def contraintes_api(request):
    """GET /api/edts/lmd/constraints/ — C1→C10, souples et préférences.

    Expose la **politique effective** des contraintes souples : l'utilisateur
    voit si elles sont actives, avec quelles bornes et quels poids. Aucune
    valeur n'est appliquée sans être affichée ici.
    """
    from edts.moteur import contraintes as C

    effectif = C.politique_effective()
    return Response({
        'dures': [{'code': code, 'libelle': libelle}
                  for code, libelle in LIBELLES_CONTRAINTES.items()],
        'avertissements': [LIBELLE_PREFERENCES],
        'souples': {
            'politique': C.politique_lisible(effectif['politique']),
            # D'où viennent réellement les règles appliquées : sans cette
            # information, un utilisateur ne peut pas savoir si le moteur suit
            # les défauts du code, un réglage de déploiement ou SA décision.
            'origine': effectif['origine'],
            'reglage': (
                {**effectif['reglage'],
                 'politique': C.politique_lisible(
                     effectif['reglage']['politique'])}
                if effectif['reglage'] else None
            ),
            'actives_par_defaut': C.SOUPLES_DEFAUT['actives'],
            'explication': (
                'Contraintes souples (trous, séries de plus de '
                'max_heures_consecutives, journées de plus de '
                'max_heures_par_jour). Désactivées par défaut : aucune '
                'pondération officielle n’est fournie par le référentiel, donc '
                'les activer revient à une décision explicite de l’INJS. '
                'Elles ne bloquent jamais un placement : elles produisent des '
                'pénalités visibles (score).'),
            'activation': (
                'Admin Django › « GET-INJS – Politique des contraintes '
                'souples » (sans redéploiement). Le réglage de déploiement '
                'EDTS_CONTRAINTES_SOUPLES reste possible ; il est alors '
                'surchargé par la ligne enregistrée.'),
            'codes': list(C.CODES_SOUPLES),
        },
        'capacite_inconnue': (
            'Une salle sans capacité renseignée (NULL) n’est jamais considérée '
            'comme « capacité suffisante » : C4 n’est pas vérifiable et le '
            'moteur émet un avertissement.'),
    })


# ── Génération (moteur LOT 2) ────────────────────────────────────────────────

def _resume_resultat(resultat):
    """Projection sérialisable du résultat du moteur LOT 2."""
    return {
        'status': resultat.status,
        'motif_echec': resultat.motif_echec,
        'metrics': resultat.metrics,
        'warnings': resultat.warnings,
        'detail': resultat.detail,
        'nb_besoins': len({p.besoin.affectation_pedagogique_id
                           for p in resultat.placements}
                          | {n.besoin.affectation_pedagogique_id
                             for n in resultat.non_places}),
        'creneaux_generes': len(resultat.placements),
        'seances': [p.as_dict() for p in resultat.placements],
        'non_placees': [n.as_dict() for n in resultat.non_places],
        'affectation_pedagogique_ids': sorted(
            {p.besoin.affectation_pedagogique_id for p in resultat.placements}),
    }


@api_view(['POST'])
@permission_classes([IsEdtPlanification])
def generate_api(request):
    """POST /api/edts/lmd/generate/ — génération via le moteur du LOT 2.

    Appelle **exclusivement** ``generate_schedule`` ; elle ne réutilise pas
    ``generer_brouillon`` (conservé pour la route historique
    ``POST /api/edts/emplois/{id}/generer/``). Le moteur n'écrit rien :
    ``persister=true`` matérialise le plan, sinon la génération reste une
    prévisualisation.
    """
    params, incoherences = _parametres_lmd(request)
    if incoherences:
        return _reponse_erreur('CHAINE_LMD_INCOHERENTE', {
            'explication': incoherences[0],
            'action_recommandee': (
                'Corrigez la sélection Année → Formation → Parcours → Niveau → '
                'Semestre → Groupe.'),
            'incoherences': incoherences,
        }, status.HTTP_400_BAD_REQUEST)

    persister = _booleen(request.data.get('persister'))
    remplacer = _booleen(request.data.get('remplacer'))
    edt_id = _int(request.data.get('emploi_du_temps_id'))

    resultat = G.generate_schedule(semaines=_semaines_de_requete(request), **params)
    if resultat.status == G.GENERATION_IMPOSSIBLE:
        return _reponse_erreur(
            resultat.motif_echec,
            resultat.detail or {
                'explication': 'Aucune séance n’a pu être placée.',
                'action_recommandee': "Consulter l'audit pour identifier la cause.",
            },
            status.HTTP_409_CONFLICT,
        )

    reponse = _resume_resultat(resultat)
    reponse['persiste'] = False
    if persister:
        from edts.models import EmploiDuTemps

        edt = EmploiDuTemps.objects.filter(pk=edt_id).first() if edt_id else None
        if edt is None:
            return _reponse_erreur('EDT_INTROUVABLE', {
                'explication': 'emploi_du_temps_id est requis pour persister le plan.',
                'action_recommandee': (
                    "Créez d'abord l'EDT (POST /api/edts/emplois/) puis relancez "
                    "la génération avec son identifiant."),
            }, status.HTTP_404_NOT_FOUND)
        if edt.statut not in ('BROUILLON', 'EN_VALIDATION'):
            return _reponse_erreur('STATUT_EDT_INVALIDE', {
                'explication': (
                    f"Le statut « {edt.get_statut_display()} » ne permet pas "
                    "d'écrire des séances."),
                'action_recommandee': (
                    "Dépubliez l'EDT ou créez une nouvelle version (V+1)."),
                'statut': edt.statut,
            }, status.HTTP_409_CONFLICT)
        rapport = V.validate_schedule(resultat.placements, resultat.non_places)
        reponse['audit'] = {
            'valide': rapport.valide,
            'statut': rapport.statut,
            'violations': [v.as_dict() for v in rapport.violations],
            'warnings': rapport.warnings,
            'couverture': rapport.couverture,
        }
        if rapport.valide:
            nb = P.persister_plan(edt, resultat.placements, remplacer=remplacer)
            reponse.update({'persiste': True, 'emploi_du_temps_id': edt.pk,
                            'version': edt.version, 'nb_seances': nb})
        else:
            reponse.update({
                'persiste': False,
                'raison_refus_persistance': (
                    'Le validateur a relevé des violations bloquantes : rien '
                    "n'a été écrit."),
                'violations': [v.as_dict() for v in rapport.violations],
            })
    return Response(
        reponse,
        status=status.HTTP_201_CREATED if reponse['persiste'] else status.HTTP_200_OK,
    )


# ── Validation / publication (réutilise LOT 2, aucune seconde logique) ───────

@api_view(['POST'])
@permission_classes([IsEdtPlanification])
def generate_coordinated_api(request):
    """POST /api/edts/lmd/generate-coordinated/ — génération coordonnée (LOT 3).

    Traite en une seule opération **toutes** les formations INJS de l'année
    académique qui portent des affectations pédagogiques planifiables. Le
    périmètre est dérivé des données validées de l'application (référentiel
    L6) : aucune liste de formations n'est acceptée de la requête, qui serait
    un vecteur d'arbitraire.

    Paramètres : ``annee_academique_id`` (requis), ``semaines`` (optionnelles),
    ``persister`` (bool, défaut faux = prévisualisation), ``remplacer`` (bool,
    défaut vrai en persistance — idempotence, jamais de doublons).

    La coordination garantit qu'aucun placement d'un EDT de l'opération n'est
    en conflit C1/C2/C3 avec un autre EDT de la même opération ni avec les
    séances déjà persistées. Le bilan expose, par EDT et globalement, les
    besoins, les placements, les non-placements et les conflits : une
    opération incomplète n'est jamais présentée comme réussie. Aucune
    publication n'est effectuée (le parcours publication LOT 2 reste
    ``POST /api/edts/lmd/{id}/publish/``).
    """
    from edts.moteur import orchestration as O

    annee_id = _int(request.data.get('annee_academique_id'))
    if annee_id is None:
        return _reponse_erreur('ANNEE_ACADEMIQUE_REQUISE', {
            'explication': (
                'annee_academique_id est requis : la génération coordonnée '
                'porte sur toutes les formations INJS d’une année académique.'),
            'action_recommandee': (
                'Transmettre l’identifiant de l’année académique concernée.'),
        }, status.HTTP_400_BAD_REQUEST)

    from scolarite.models import AnneeAcademique

    if not AnneeAcademique.objects.filter(pk=annee_id).exists():
        return _reponse_erreur('ANNEE_ACADEMIQUE_INTROUVABLE', {
            'explication': f'L’année académique #{annee_id} est introuvable.',
            'action_recommandee': 'Vérifier l’identifiant transmis.',
        }, status.HTTP_404_NOT_FOUND)

    bilan = O.generer_coordonne(
        annee_id,
        semaines=_semaines_de_requete(request),
        persister=_booleen(request.data.get('persister')),
        remplacer=_booleen(request.data.get('remplacer', True)),
    )
    if bilan['status_global'] == O.COORDONNEE_IMPOSSIBLE:
        return _reponse_erreur(
            bilan.get('motif_echec') or 'GENERATION_IMPOSSIBLE',
            bilan.get('detail') or {
                'explication': 'Aucun EDT n’a pu être généré.',
                'action_recommandee': "Consulter l'audit pour identifier la cause.",
            }, status.HTTP_409_CONFLICT)
    # 201 si tout est complet et persisté (quand persistance demandée),
    # sinon 200 : le bilan reste consultable, jamais masqué.
    complet = bilan['status_global'] == O.COORDONNEE_OK
    code = (status.HTTP_201_CREATED
            if complet and bilan.get('persistence_demandee')
            else status.HTTP_200_OK)
    return Response(bilan, status=code)


@api_view(['POST'])
@permission_classes([IsEdtValidation])
def validate_api(request, pk):
    """POST /api/edts/lmd/{id}/validate/ — validation par le moteur LOT 2."""
    from edts.models import EmploiDuTemps

    edt = EmploiDuTemps.objects.filter(pk=pk).first()
    if edt is None:
        return Response({'detail': 'EDT introuvable'},
                        status=status.HTTP_404_NOT_FOUND)
    rapport = V.valider_emploi_du_temps(edt)
    edt.statut = 'VALIDE' if rapport.valide else 'EN_VALIDATION'
    edt.valide_le = timezone.now() if rapport.valide else None
    edt.valide_par = request.user if rapport.valide else None
    edt.save(update_fields=['statut', 'valide_le', 'valide_par', 'updated_at'])
    return Response({
        'valide': rapport.valide,
        'statut_edt': edt.statut,
        'version': edt.version,
        'statut': rapport.statut,
        'violations': [v.as_dict() for v in rapport.violations],
        'warnings': rapport.warnings,
        'couverture': rapport.couverture,
    })


def _besoins_attendus_pour_publication(edt):
    """Périmètre attendu d'un EDT — dérivé de sa population déclarée (LOT 2).

    Le contrôle de complétude ne s'applique que si le périmètre est dérivable
    **sans ambiguïté** depuis l'EDT lui-même — jamais depuis la requête, qui
    serait un vecteur de contournement (ex. omettre des groupes pour réduire
    le nombre de séances attendues) :

    * ``FORMATION`` — toutes les séances planifiables de la formation ;
    * ``GROUPE``    — toutes les séances planifiables du groupe ;
    * ``ENSEIGNANT`` / ``SALLE`` — vue croisée dont le périmètre de besoins
      n'est pas défini au référentiel LMD : aucun besoin n'est inventé et le
      contrôle reste non applicable (état explicite renvoyé au client).

    Retourne ``(liste_des_seances_attendues_ou_None, motif_non_applicabilite)``.
    La couverture du moteur compte en séances (``len``) : un besoin de N
    séances attend N placements, la liste est donc aplatie en séances.
    """
    if edt.population_type == 'FORMATION':
        params = {'annee_academique_id': edt.annee_academique_id,
                  'ref_formation_id': edt.population_id}
    elif edt.population_type == 'GROUPE':
        params = {'annee_academique_id': edt.annee_academique_id,
                  'groupe_ids': [edt.population_id]}
    else:
        return None, 'POPULATION_SANS_PERIMETRE'
    resultat = calculate_teaching_needs(**params)
    if resultat.vide:
        # Périmètre sans besoin calculable : aucune attente démontrable, le
        # contrôle ne peut pas être appliqué (jamais de besoin inventé).
        return None, resultat.motif_echec
    seances_attendues = []
    for besoin in resultat.besoins:
        seances_attendues.extend([besoin] * besoin.nb_seances)
    return seances_attendues, None


@api_view(['POST'])
@permission_classes([IsEdtValidation])
def publish_api(request, pk):
    """POST /api/edts/lmd/{id}/publish/ — publication idempotente (LOT 2).

    LOT 2 : le contrôle de complétude du moteur est désormais appliqué sur le
    parcours API normal. Les besoins attendus sont recalculés depuis le
    périmètre déclaré de l'EDT (``_besoins_attendus_pour_publication``) et
    transmis à ``publier_emploi_du_temps`` : un plan incomplet est refusé
    (``PLAN_INCOMPLET``) sans aucun effet de bord. ``force`` n'est pas exposé
    sur cette route : aucune publication forcée n'est possible ici.
    """
    from edts.models import EmploiDuTemps

    edt = EmploiDuTemps.objects.filter(pk=pk).first()
    if edt is None:
        return Response({'detail': 'EDT introuvable'},
                        status=status.HTTP_404_NOT_FOUND)
    besoins_attendus, motif_non_applicabilite = (
        _besoins_attendus_pour_publication(edt))
    resultat = P.publier_emploi_du_temps(
        pk, user=request.user,
        version_attendue=_int(request.data.get('version')),
        besoins_attendus=besoins_attendus,
    )
    # Champ additif (traçabilité) : le client sait si le contrôle de
    # complétude a pu être appliqué, et pourquoi sinon.
    resultat['controle_completude'] = {
        'statut': ('APPLIQUE' if besoins_attendus is not None
                   else 'NON_APPLICABLE'),
        'motif_non_applicabilite': motif_non_applicabilite,
    }
    code = status.HTTP_200_OK if resultat['publie'] else status.HTTP_409_CONFLICT
    if resultat['motif_echec'] == 'EDT_INTROUVABLE':
        code = status.HTTP_404_NOT_FOUND
    return Response(resultat, status=code)


# ── Adaptateurs de revalidation C1→C10 sur un EDT persisté ───────────────────

class _BesoinAffectation:
    """Adaptateur ``AffectationCreneau`` → vue ``TeachingNeed``.

    Permet de rejouer **exactement** ``validate_schedule`` (donc C1→C10) sur un
    EDT déjà persisté, y compris après une modification manuelle. Le besoin est
    reconstruit depuis l'affectation pédagogique d'origine : la traçabilité
    TeachingNeed → AffectationPedagogique est préservée.
    """

    # ``ecue_id`` est nécessaire : la validation (C8) distingue deux ancrages
    # pédagogiques — l'affectation pédagogique, ou l'ECUE pour les cohortes
    # importées. Sans cet attribut, rejouer la validation sur un EDT persisté
    # levait un AttributeError (500) au lieu de rendre un verdict.
    __slots__ = ('affectation_pedagogique_id', 'annee_academique_id',
                 'ref_formation_id', 'groupe_id', 'enseignant_id', 'nature',
                 'type_enseignement', 'intitule', 'effectif', 'nb_seances',
                 'duree_seance_heures', 'credits', 'volume_horaire',
                 'ecue_id')

    def __init__(self, affectation, duree_heures, effectif):
        ap = affectation.affectation_pedagogique
        self.affectation_pedagogique_id = affectation.affectation_pedagogique_id
        self.annee_academique_id = (
            ap.annee_academique_id if ap
            else affectation.emploi_du_temps.annee_academique_id)
        self.ref_formation_id = ap.ref_formation_id if ap else affectation.formation_id
        self.groupe_id = affectation.groupe_id
        self.enseignant_id = ap.enseignant_id if ap else None
        self.nature = affectation.nature
        self.type_enseignement = ap.type_enseignement if ap else 'CM'
        self.intitule = affectation.intitule or 'Enseignement'
        self.effectif = effectif
        self.nb_seances = 1
        self.duree_seance_heures = duree_heures
        self.credits = 0
        self.volume_horaire = duree_heures
        # Ancrage ECUE : connu via l'affectation pédagogique quand elle existe ;
        # sinon `None` et C8 tranchera sur l'absence d'ancrage — jamais deviné.
        self.ecue_id = ap.ecue_id if ap else None


class _PlacementAffectation:
    """Placement non persisté reconstruit depuis une ``AffectationCreneau``."""

    __slots__ = ('besoin', 'creneau', 'salle', 'semaine_debut', 'semaine_fin')

    def __init__(self, besoin, creneau, salle, semaine_debut, semaine_fin):
        self.besoin = besoin
        self.creneau = creneau
        self.salle = salle
        self.semaine_debut = semaine_debut
        self.semaine_fin = semaine_fin

    @property
    def enseignant_id(self):
        return self.besoin.enseignant_id

    @property
    def groupe_id(self):
        return self.besoin.groupe_id

    @property
    def salle_id(self):
        return self.salle.pk if self.salle is not None else None

    @property
    def jour(self):
        return self.creneau.jour

    @property
    def heure_debut(self):
        return self.creneau.heure_debut

    @property
    def heure_fin(self):
        return self.creneau.heure_fin


def _effectif_de(affectation):
    groupe = affectation.groupe
    return getattr(groupe, 'capacite_max', None) if groupe is not None else None


def _placements_edt(emploi_du_temps, semaines=None, exclure_id=None):
    """Reconstruit les placements d'un EDT persisté pour revalidation C1→C10."""
    from edts.models import AffectationCreneau
    from edts.moteur.besoins import duree_canevas_heures

    duree = duree_canevas_heures() or 1.0
    qs = (AffectationCreneau.objects
          .filter(emploi_du_temps=emploi_du_temps, actif=True)
          .select_related('creneau_template', 'salle', 'groupe',
                          'affectation_pedagogique'))
    placements = []
    for affectation in qs:
        if exclure_id and affectation.pk == exclure_id:
            continue
        ct = affectation.creneau_template
        d = ct.duree_heures if ct is not None else duree
        besoin = _BesoinAffectation(affectation, d, _effectif_de(affectation))
        placements.append(_PlacementAffectation(
            besoin, ct, affectation.salle,
            semaines[0] if semaines else affectation.semaine_debut,
            semaines[1] if semaines else affectation.semaine_fin,
        ))
    return placements


# ── Déplacement manuel revalidé C1→C10 ───────────────────────────────────────

def _candidats_deplacement(affectation):
    """Créneaux compatibles — proposition, jamais une écriture."""
    from edts.moteur.besoins import duree_canevas_heures
    from edts.models import CreneauTemplate
    from formations.models import RefSalle

    besoin = _BesoinAffectation(affectation, duree_canevas_heures() or 1.0,
                                _effectif_de(affectation))
    salles = list(RefSalle.objects.filter(actif=True))
    edt = affectation.emploi_du_temps
    occupation = _placements_edt(edt, exclure_id=affectation.pk)
    propositions = []
    for creneau in CreneauTemplate.objects.order_by('jour', 'heure_debut'):
        for salle in salles:
            candidat = _PlacementAffectation(
                besoin, creneau, salle,
                affectation.semaine_debut, affectation.semaine_fin)
            if V.validate_schedule(occupation + [candidat]).valide:
                propositions.append({
                    'creneau_template_id': creneau.pk,
                    'jour': creneau.jour,
                    'heure_debut': creneau.heure_debut.isoformat(timespec='minutes'),
                    'heure_fin': creneau.heure_fin.isoformat(timespec='minutes'),
                    'salle_id': salle.pk, 'salle_nom': salle.nom,
                    'salle_capacite': salle.capacite,
                })
    # Le plan EXISTANT est validé pour lui-même : quand il est déjà en
    # violation, aucun déplacement ne peut être accepté (le candidat serait
    # rejeté à cause d'une faute qu'il n'a pas causée). On renvoie donc la
    # cause réelle au lieu d'une liste vide sans explication.
    rapport_plan = V.validate_schedule(occupation)
    violations_plan = [v.as_dict() for v in rapport_plan.violations]
    reponse = {
        'affectation_id': affectation.pk,
        'nb_candidats': len(propositions),
        'candidats': propositions,
        'plan_valide': rapport_plan.valide,
        'violations_plan': violations_plan,
        'warnings_plan': rapport_plan.warnings,
    }
    if not rapport_plan.valide:
        codes = sorted({v['contrainte'] for v in violations_plan})
        reponse['explication'] = (
            'Le plan actuel de cet emploi du temps viole déjà '
            f'{len(violations_plan)} contrainte(s) ({", ".join(codes)}). '
            'Aucun déplacement ne peut être validé tant que ces points ne sont '
            'pas corrigés : la position demandée serait refusée pour une faute '
            'qu’elle n’a pas causée.'
        )
        reponse['action_recommandee'] = (
            'Corrigez d’abord les séances signalées (ancrage pédagogique, salle '
            'compatible, conflits), puis relancez le déplacement.'
        )
    return Response(reponse)


@api_view(['GET', 'POST'])
@permission_classes([IsEdtPlanification])
def item_move_api(request, pk):
    """``GET`` candidats compatibles / ``POST`` déplacement revalidé C1→C10.

    La route historique ``POST /api/edts/affectations/{id}/deplacer/`` est
    **conservée** ; cette route applique en plus la revalidation complète du
    moteur LOT 2 et refuse tout déplacement provoquant une violation bloquante.
    """
    from edts.models import AffectationCreneau, CreneauTemplate

    affectation = (AffectationCreneau.objects
                   .select_related('emploi_du_temps', 'creneau_template', 'salle',
                                   'groupe', 'affectation_pedagogique')
                   .filter(pk=pk).first())
    if affectation is None:
        return Response({'detail': 'Affectation introuvable'},
                        status=status.HTTP_404_NOT_FOUND)
    if request.method == 'GET':
        return _candidats_deplacement(affectation)

    edt = affectation.emploi_du_temps
    if edt.statut in ('PUBLIE', 'ARCHIVE'):
        return _reponse_erreur('STATUT_EDT_INVALIDE', {
            'explication': f'Le statut « {edt.statut} » interdit toute modification.',
            'action_recommandee': (
                'Dépubliez l’EDT, ou créez une nouvelle version (V+1).'),
        })
    creneau_id = _int(request.data.get('creneau_template_id'))
    salle_id = _int(request.data.get('salle_id'))
    creneau = (CreneauTemplate.objects.filter(pk=creneau_id).first()
               if creneau_id else affectation.creneau_template)
    if creneau is None:
        return Response({'detail': 'Créneau cible introuvable.'},
                        status=status.HTTP_400_BAD_REQUEST)
    salle = affectation.salle
    if salle_id is not None:
        from formations.models import RefSalle

        salle = RefSalle.objects.filter(pk=salle_id).first()
        if salle is None:
            return Response({'detail': 'Salle cible introuvable.'},
                            status=status.HTTP_400_BAD_REQUEST)
    semaines = _semaines_de_requete(request)

    # Revalidation C1→C10 sur le plan complet, l'affectation déplacée occupant
    # sa nouvelle position : un refus n'écrit rien.
    candidat = _PlacementAffectation(
        _BesoinAffectation(affectation, creneau.duree_heures,
                           _effectif_de(affectation)),
        creneau, salle,
        semaines[0] if semaines else affectation.semaine_debut,
        semaines[1] if semaines else affectation.semaine_fin,
    )
    rapport = V.validate_schedule(
        _placements_edt(edt, semaines=semaines, exclure_id=affectation.pk) + [candidat])
    reponse = {
        'accepted': rapport.valide,
        'affectation_id': affectation.pk,
        'creneau_template_id': creneau.pk,
        'salle_id': salle.pk if salle is not None else None,
        'valide': rapport.valide,
        'statut': rapport.statut,
        'violations': [v.as_dict() for v in rapport.violations],
        'warnings': rapport.warnings,
        'couverture': rapport.couverture,
    }
    if not rapport.valide:
        reponse['explication'] = (
            'Déplacement refusé : la position demandée viole une contrainte forte.')
        reponse['action_recommandee'] = (
            'Choisissez un autre créneau ou une autre salle parmi les créneaux '
            'compatibles (GET sur cette route).')
        return Response(reponse, status=status.HTTP_409_CONFLICT)

    affectation.creneau_template = creneau
    affectation.salle = salle
    affectation.salle_nom = salle.nom if salle is not None else affectation.salle_nom
    if semaines:
        affectation.semaine_debut, affectation.semaine_fin = semaines
    affectation.save(update_fields=[
        'creneau_template', 'salle', 'salle_nom', 'semaine_debut', 'semaine_fin'])
    from scolarite.models import journaliser

    journaliser(action='EDT_AFFECTATION_MODIFIEE', objet=edt, acteur=request.user,
                nouvelle_valeur=f'créneau #{creneau.pk} / salle #{reponse["salle_id"]}',
                commentaire='Déplacement LMD revalidé C1→C10 : accepté.',
                extra={'affectation_id': affectation.pk,
                       'creneau_template_id': creneau.pk,
                       'salle_id': reponse['salle_id'],
                       'revalidation': {
                           'valide': rapport.valide,
                           'statut': rapport.statut,
                           'violations': [v.as_dict()
                                          for v in rapport.violations],
                           'warnings': rapport.warnings,
                           'couverture': rapport.couverture,
                       }})
    return Response(reponse)


@api_view(['POST'])
@permission_classes([IsEdtPlanification])
def item_cancel_api(request, pk):
    """POST /api/edts/lmd/items/{id}/cancel/ — annulation traçable et réversible.

    Désactivation logique (``actif=False``) : **aucune suppression physique**,
    l'historique des séances est conservé. L'opération reste réversible via
    ``reactiver=true``.
    """
    from edts.models import AffectationCreneau

    affectation = (AffectationCreneau.objects
                   .select_related('emploi_du_temps', 'creneau_template')
                   .filter(pk=pk).first())
    if affectation is None:
        return Response({'detail': 'Affectation introuvable'},
                        status=status.HTTP_404_NOT_FOUND)
    edt = affectation.emploi_du_temps
    if edt.statut in ('PUBLIE', 'ARCHIVE'):
        return _reponse_erreur('STATUT_EDT_INVALIDE', {
            'explication': f'Le statut « {edt.statut} » interdit toute modification.',
            'action_recommandee': 'Dépubliez l’EDT avant d’annuler une séance.',
        })
    reactiver = _booleen(request.data.get('reactiver'))
    motif = str(request.data.get('motif') or '').strip()
    if not motif:
        return _reponse_erreur('MOTIF_ANNULATION_REQUIS', {
            'explication': (
                'Une annulation doit être motivée : elle modifie un EDT '
                'planifiable et reste dans l’historique.'),
            'action_recommandee': 'Renseignez un motif explicite (champ « motif »).',
        }, status.HTTP_400_BAD_REQUEST)
    # `reactiver` absent ⇒ POST = annulation (désactivation logique) ;
    # `reactiver=true` ⇒ remise en service de la séance.
    affectation.actif = reactiver
    affectation.commentaire = (
        f'[LMD] {"Réactivée" if reactiver else "Annulée"} — {motif}')
    affectation.save(update_fields=['actif', 'commentaire'])
    from scolarite.models import journaliser

    journaliser(
        action='EDT_AFFECTATION_MODIFIEE', objet=edt, acteur=request.user,
        nouvelle_valeur='ACTIVE' if affectation.actif else 'INACTIVE',
        commentaire=('Réactivation LMD — ' if reactiver else 'Annulation LMD — ')
                     + motif,
        extra={'affectation_id': affectation.pk, 'motif': motif,
               'actif': affectation.actif,
               'affectation_pedagogique_id': affectation.affectation_pedagogique_id})
    return Response({
        'annulee': not affectation.actif,
        'reactivee': affectation.actif,
        'affectation_id': affectation.pk,
        'affectation_pedagogique_id': affectation.affectation_pedagogique_id,
        'motif': motif,
        'reversible': True,
    })


# ── Versionnement, résultat et grille ────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsEdtReadOnlyOrPlanification])
def versions_api(request):
    """GET /api/edts/lmd/versions/ — historique V1, V2, V3…

    Une version publiée n'est jamais écrasée : chaque ligne expose statut,
    dates, auteurs et motif de modification.
    """
    from edts.models import EmploiDuTemps

    qs = EmploiDuTemps.objects.select_related(
        'annee_academique', 'cree_par', 'valide_par', 'publie_par')
    annee_id = _int(request.query_params.get('annee_academique_id'))
    if annee_id:
        qs = qs.filter(annee_academique_id=annee_id)
    return Response({
        'versions': [{
            'id': e.pk,
            'version': e.version,
            'libelle': f'V{e.version}',
            'titre': e.titre or e.population_label,
            'statut': e.statut,
            'statut_libelle': e.get_statut_display(),
            'annee_academique': e.annee_academique.libelle,
            'creee_le': e.created_at,
            'creee_par': e.cree_par.username if e.cree_par else '',
            'motif_modification': e.motif_modification,
            'validee_le': e.valide_le,
            'validee_par': e.valide_par.username if e.valide_par else '',
            'publiee_le': e.publie_le,
            'publiee_par': e.publie_par.username if e.publie_par else '',
            'nb_seances': e.affectations.filter(actif=True).count(),
        } for e in qs.order_by('annee_academique_id', '-version')],
    })


def _contexte_pedagogique(a):
    """Contexte UE/ECUE/enseignant d'une séance, traçable à l'affectation."""
    ap = a.affectation_pedagogique
    return {
        'parcours': ap.parcours.code if ap and ap.parcours_id else '',
        'niveau': ap.niveau.code if ap and ap.niveau_id else '',
        'semestre': ap.semestre.libelle if ap and ap.semestre_id else '',
        'ue': ap.ue.intitule if ap and ap.ue_id else '',
        'ecue': ap.ecue.intitule if ap and ap.ecue_id else '',
        'enseignant': ap.enseignant.nom if ap and ap.enseignant_id else '',
    }


def _seances_filtrees(request, edt):
    """Séances actives d'un EDT, filtrées par la requête — source unique.

    Utilisée par la restitution JSON (``result_api``) ET par l'export XLSX :
    un export ne peut donc pas contenir autre chose que ce que l'écran affiche
    pour les mêmes filtres.
    """
    from edts.models import AffectationCreneau

    qp = request.query_params
    # Toutes les relations lues à l'affichage sont jointes ici : sans elles,
    # `_contexte_pedagogique` (parcours, niveau, semestre, UE, ECUE, enseignant)
    # émettait SIX requêtes par séance dans l'export XLSX (mesuré : 14 requêtes
    # pour 2 séances, 134 pour 22 — `manage.py compteur_sql_getinjs`).
    qs = (AffectationCreneau.objects
          .filter(emploi_du_temps=edt, actif=True)
          .select_related(
              'creneau_template', 'salle', 'groupe', 'formation',
              'groupe__annee_academique', 'affectation_pedagogique',
              'affectation_pedagogique__parcours',
              'affectation_pedagogique__niveau',
              'affectation_pedagogique__semestre',
              'affectation_pedagogique__ue',
              'affectation_pedagogique__ecue',
              'affectation_pedagogique__enseignant',
          ))
    for champ in ('groupe_id', 'salle_id', 'formation_id'):
        valeur = _int(qp.get(champ))
        if valeur:
            qs = qs.filter(**{champ: valeur})
    semaine = _int(qp.get('semaine'))
    if semaine:
        qs = qs.filter(semaine_debut__lte=semaine, semaine_fin__gte=semaine)
    if qp.get('jour'):
        qs = qs.filter(creneau_template__jour=qp['jour'])
    enseignant = _int(qp.get('enseignant_id'))
    if enseignant:
        qs = qs.filter(affectation_pedagogique__enseignant_id=enseignant)
    return qs.order_by('creneau_template__jour',
                       'creneau_template__heure_debut', 'semaine_debut',
                       'intitule')


@api_view(['GET'])
@permission_classes([IsEdtReadOnlyOrPlanification])
def result_api(request, pk):
    """GET /api/edts/lmd/{id}/result/ — séances filtrables.

    Filtres : groupe, enseignant, salle, formation, semaine, jour. Chaque ligne
    reste traçable jusqu'à son ``AffectationPedagogique`` et donc jusqu'à la
    chaîne Séance → Présence QR.
    """
    from edts.models import AffectationCreneau, EmploiDuTemps, JOUR_CHOICES

    edt = EmploiDuTemps.objects.filter(pk=pk).first()
    if edt is None:
        return Response({'detail': 'EDT introuvable'},
                        status=status.HTTP_404_NOT_FOUND)
    qs = _seances_filtrees(request, edt)

    seances = []
    for a in qs:
        ct = a.creneau_template
        ligne = {
            'id': a.pk,
            'jour': ct.jour if ct else '',
            'heure_debut': ct.heure_debut.isoformat(timespec='minutes') if ct else '',
            'heure_fin': ct.heure_fin.isoformat(timespec='minutes') if ct else '',
            'formation': a.formation.intitule if a.formation_id else '',
            'groupe': a.groupe.nom if a.groupe_id else '',
            'intitule': a.intitule,
            'salle': a.salle_nom,
            'salle_capacite': a.salle.capacite if a.salle_id else None,
            'nature': a.nature,
            'semaine_debut': a.semaine_debut,
            'semaine_fin': a.semaine_fin,
            'statut': 'ACTIVE' if a.actif else 'ANNULEE',
            'affectation_pedagogique_id': a.affectation_pedagogique_id,
        }
        ligne.update(_contexte_pedagogique(a))
        seances.append(ligne)
    return Response({
        'emploi_du_temps_id': edt.pk,
        'version': edt.version,
        'statut': edt.statut,
        'jours': [j for j, _ in JOUR_CHOICES],
        'filtres': dict(request.query_params),
        'nb_seances': len(seances),
        'seances': seances,
    })


@api_view(['GET'])
@permission_classes([IsEdtReadOnlyOrPlanification])
def grille_api(request, pk):
    """GET /api/edts/lmd/{id}/grille/?vue=groupe|enseignant|salle|formation|semaine.

    Réutilise ``edts.services.grille_hebdomadaire`` : aucune seconde logique de
    grille n'est introduite.
    """
    from edts.models import EmploiDuTemps
    from edts.services import grille_hebdomadaire

    edt = EmploiDuTemps.objects.filter(pk=pk).first()
    if edt is None:
        return Response({'detail': 'EDT introuvable'},
                        status=status.HTTP_404_NOT_FOUND)
    vue = request.query_params.get('vue', 'groupe')
    vues = ('groupe', 'enseignant', 'salle', 'formation', 'semaine')
    if vue not in vues:
        return _reponse_erreur('VUE_INCONNUE', {
            'explication': f'Vue « {vue} » inconnue.',
            'action_recommandee': f'Vues disponibles : {", ".join(vues)}.',
        }, status.HTTP_400_BAD_REQUEST)
    semaine = _int(request.query_params.get('semaine'))
    return Response({
        'emploi_du_temps_id': edt.pk,
        'version': edt.version,
        'vue': vue,
        'semaine': semaine,
        'grille': grille_hebdomadaire(edt, semaine),
        'source': 'edts.services.grille_hebdomadaire (logique existante conservée)',
    })


@api_view(['GET'])
@permission_classes([IsEdtReadOnlyOrPlanification])
def export_xlsx_api(request, pk):
    """GET /api/edts/lmd/{id}/export.xlsx/ — export tabulaire (Excel).

    Même source de vérité que ``result_api`` (``_seances_filtrees``) : un
    export ne peut pas montrer autre chose que l'écran pour les mêmes filtres
    (``groupe_id``, ``salle_id``, ``formation_id``, ``enseignant_id``,
    ``semaine``, ``jour``).

    Deux feuilles sont produites :
      - « Séances » : une ligne par séance active, en-têtes figés et filtres ;
      - « Synthèse » : métadonnées de l'EDT et **décompte réel** des lignes.
    Aucune ligne n'est ajoutée pour « remplir » un groupe absent, et un EDT
    vide produit un classeur avec ses en-têtes et zéro ligne de données.
    """
    from io import BytesIO

    from django.http import HttpResponse
    from django.utils import timezone
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    from edts.models import EmploiDuTemps, JOUR_CHOICES

    edt = EmploiDuTemps.objects.select_related('annee_academique').filter(pk=pk).first()
    if edt is None:
        return Response({'detail': 'EDT introuvable'},
                        status=status.HTTP_404_NOT_FOUND)

    seances = list(_seances_filtrees(request, edt))
    noms_jours = dict(JOUR_CHOICES)

    classeur = Workbook()
    feuille = classeur.active
    feuille.title = 'Séances'

    colonnes = [
        ('Jour', 14), ('Début', 9), ('Fin', 9), ('Semaines', 11),
        ('Nature', 12), ('Intitulé', 42), ('UE', 26), ('ECUE', 26),
        ('Enseignant', 24), ('Groupe', 22), ('Parcours', 14),
        ('Niveau', 10), ('Semestre', 12), ('Salle', 22),
        ('Capacité', 10), ('Formation', 34), ('Statut', 10),
    ]
    entete_font = Font(bold=True, color='FFFFFF')
    entete_fond = PatternFill('solid', fgColor='1F3B63')
    for index, (libelle, largeur) in enumerate(colonnes, start=1):
        cellule = feuille.cell(row=1, column=index, value=libelle)
        cellule.font = entete_font
        cellule.fill = entete_fond
        cellule.alignment = Alignment(vertical='center', wrap_text=True)
        feuille.column_dimensions[get_column_letter(index)].width = largeur
    feuille.freeze_panes = 'A2'

    for ligne, a in enumerate(seances, start=2):
        ct = a.creneau_template
        contexte = _contexte_pedagogique(a)
        feuille.cell(row=ligne, column=1,
                     value=noms_jours.get(ct.jour, ct.jour) if ct else '')
        feuille.cell(row=ligne, column=2,
                     value=ct.heure_debut.strftime('%H:%M') if ct else '')
        feuille.cell(row=ligne, column=3,
                     value=ct.heure_fin.strftime('%H:%M') if ct else '')
        feuille.cell(row=ligne, column=4,
                     value=f'S{a.semaine_debut}–S{a.semaine_fin}')
        feuille.cell(row=ligne, column=5, value=a.get_nature_display())
        feuille.cell(row=ligne, column=6, value=a.intitule)
        feuille.cell(row=ligne, column=7, value=contexte['ue'])
        feuille.cell(row=ligne, column=8, value=contexte['ecue'])
        feuille.cell(row=ligne, column=9,
                     value=a.enseignant_nom or contexte['enseignant'])
        feuille.cell(row=ligne, column=10,
                     value=a.groupe.nom if a.groupe_id else '')
        feuille.cell(row=ligne, column=11, value=contexte['parcours'])
        feuille.cell(row=ligne, column=12, value=contexte['niveau'])
        feuille.cell(row=ligne, column=13, value=contexte['semestre'])
        feuille.cell(row=ligne, column=14, value=a.salle_nom)
        capacite = a.salle.capacite if a.salle_id else None
        feuille.cell(row=ligne, column=15, value=capacite)  # NULL reste NULL
        feuille.cell(row=ligne, column=16,
                     value=a.formation.intitule if a.formation_id else '')
        feuille.cell(row=ligne, column=17, value='ACTIVE' if a.actif else 'ANNULEE')

    if seances:
        feuille.auto_filter.ref = f'A1:{get_column_letter(len(colonnes))}{len(seances) + 1}'

    synthese = classeur.create_sheet('Synthèse')
    lignes_synthese = [
        ('Emploi du temps', edt.titre or edt.population_label or f'EDT #{edt.pk}'),
        ('Année académique', edt.annee_academique.libelle),
        ('Version', f'V{edt.version}'),
        ('Statut', edt.get_statut_display()),
        ('Nombre de séances exportées', len(seances)),
        ('Filtres appliqués', ' · '.join(
            f'{cle}={valeur}' for cle, valeur in request.query_params.items()
        ) or 'aucun'),
        ('Exporté le', timezone.localtime().strftime('%d/%m/%Y à %H:%M')),
        ('Source', 'GET /api/edts/lmd/<id>/export.xlsx/ — même filtre que /result/'),
    ]
    for ligne, (cle, valeur) in enumerate(lignes_synthese, start=1):
        synthese.cell(row=ligne, column=1, value=cle).font = Font(bold=True)
        synthese.cell(row=ligne, column=2, value=valeur)
    synthese.column_dimensions['A'].width = 32
    synthese.column_dimensions['B'].width = 64

    flux = BytesIO()
    classeur.save(flux)
    contenu = flux.getvalue()
    flux.close()

    reponse = HttpResponse(
        contenu,
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    reponse['Content-Disposition'] = f'attachment; filename="edt-{edt.pk}-v{edt.version}.xlsx"'
    reponse['Content-Length'] = str(len(contenu))
    return reponse


@api_view(['GET'])
@permission_classes([IsEdtReadOnlyOrPlanification])
def export_pdf_api(request, pk):
    """GET /api/edts/lmd/{id}/export.pdf/ — emploi du temps imprimable (PDF).

    Réutilise ``edts.services.grille_hebdomadaire`` : la même logique de grille
    que l'écran et l'API JSON, donc aucune divergence possible entre ce que
    l'on voit et ce que l'on imprime.

    Le PDF est une grille hebdomadaire : colonnes = jours réellement utilisés,
    lignes = plages horaires réellement utilisées, cellules = séances. Un EDT
    sans séance produit un document qui le dit (« aucune séance ») — aucune
    ligne, aucun créneau et aucun enseignant ne sont inventés.
    """
    from io import BytesIO

    from django.http import HttpResponse
    from django.utils import timezone

    from edts.models import EmploiDuTemps
    from edts.services import grille_hebdomadaire

    # reportlab est déjà une dépendance du dépôt (exports institutionnels).
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import (Paragraph, SimpleDocTemplate, Spacer,
                                    Table, TableStyle)

    edt = EmploiDuTemps.objects.select_related('annee_academique').filter(pk=pk).first()
    if edt is None:
        return Response({'detail': 'EDT introuvable'},
                        status=status.HTTP_404_NOT_FOUND)

    semaine = _int(request.query_params.get('semaine'))
    grille = grille_hebdomadaire(edt, semaine)

    # ── Colonnes (jours) et lignes (plages horaires) réellement occupées ─────
    jours, plages = [], []
    for bloc in grille.get('jours', []):
        for creneau in bloc.get('creneaux', []):
            seances = creneau.get('affectations') or []
            if not seances:
                continue
            if bloc['jour'] not in jours:
                jours.append(bloc['jour'])
            libelle_plage = f"{creneau['heure_debut'][:5]}–{creneau['heure_fin'][:5]}"
            if libelle_plage not in plages:
                plages.append(libelle_plage)
    plages.sort()
    # Libellés de jours : source unique = le modèle (JOUR_CHOICES).
    from edts.models import JOUR_CHOICES
    noms_jours = dict(JOUR_CHOICES)

    # Index (jour, plage) -> liste de séances
    index = {}
    for bloc in grille.get('jours', []):
        for creneau in bloc.get('creneaux', []):
            plage = f"{creneau['heure_debut'][:5]}–{creneau['heure_fin'][:5]}"
            for seance in creneau.get('affectations') or []:
                index.setdefault((bloc['jour'], plage), []).append(seance)

    # ── Styles ──────────────────────────────────────────────────────────────
    styles = getSampleStyleSheet()
    style_titre = ParagraphStyle(
        'TitreEDT', parent=styles['Title'], fontSize=15, leading=18, spaceAfter=2)
    style_sous_titre = ParagraphStyle(
        'SousTitreEDT', parent=styles['Normal'], fontSize=9, leading=12,
        textColor=colors.HexColor('#444444'))
    style_entete = ParagraphStyle(
        'Entete', parent=styles['Normal'], fontSize=8.5, leading=10,
        fontName='Helvetica-Bold', textColor=colors.white)
    style_cellule = ParagraphStyle(
        'Cellule', parent=styles['Normal'], fontSize=7.4, leading=9)
    style_vide = ParagraphStyle(
        'Vide', parent=styles['Normal'], fontSize=7.4, leading=9,
        textColor=colors.HexColor('#999999'))

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=landscape(A4),
        leftMargin=1.2 * cm, rightMargin=1.2 * cm,
        topMargin=1.1 * cm, bottomMargin=1.1 * cm,
        title=f'Emploi du temps V{edt.version}',
        author='INJS d’Abidjan — GET INJS APP',
    )
    flux = [
        Paragraph('INJS d’Abidjan — Emploi du temps', style_titre),
        Paragraph(edt.titre or edt.population_label or f'EDT #{edt.pk}', style_sous_titre),
        Paragraph(
            f'Année académique : {edt.annee_academique.libelle} · '
            f'Version : V{edt.version} · Statut : {edt.get_statut_display()} · '
            + (f'Semaine : {semaine} · ' if semaine else '')
            + f'Édité le {timezone.localtime().strftime("%d/%m/%Y à %H:%M")}',
            style_sous_titre),
        Spacer(1, 8),
    ]

    if not index:
        flux.append(Paragraph(
            'Aucune séance active dans cet emploi du temps : '
            'la grille est donc vide (aucune séance n’est ajoutée pour remplir le document).',
            style_sous_titre))
    else:
        entete = [Paragraph('Horaire', style_entete)]
        entete += [Paragraph(noms_jours.get(j, j), style_entete) for j in jours]
        donnees = [entete]
        for plage in plages:
            ligne = [Paragraph(f'<b>{plage}</b>', style_cellule)]
            for jour in jours:
                seances = index.get((jour, plage), [])
                if not seances:
                    ligne.append(Paragraph('—', style_vide))
                else:
                    textes = []
                    for s in seances:
                        morceaux = [f"<b>{s['intitule']}</b>"]
                        if s.get('salle_nom'):
                            morceaux.append(s['salle_nom'])
                        if s.get('enseignant_nom'):
                            morceaux.append(s['enseignant_nom'])
                        if s.get('groupe'):
                            morceaux.append(f"Gr. {s['groupe']}")
                        textes.append(' — '.join(morceaux))
                    ligne.append(Paragraph('<br/>'.join(textes), style_cellule))
            donnees.append(ligne)

        largeur_utile = landscape(A4)[0] - 2.4 * cm
        largeur_horaire = 2.6 * cm
        largeur_jour = (largeur_utile - largeur_horaire) / max(len(jours), 1)
        table = Table(
            donnees, colWidths=[largeur_horaire] + [largeur_jour] * len(jours),
            repeatRows=1)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f3b63')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#9aa7b8')),
            ('BACKGROUND', (0, 1), (0, -1), colors.HexColor('#eef2f7')),
            ('LEFTPADDING', (0, 0), (-1, -1), 3),
            ('RIGHTPADDING', (0, 0), (-1, -1), 3),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]))
        flux.append(table)

    doc.build(flux)
    contenu = buffer.getvalue()
    buffer.close()

    nom = f"edt-{edt.pk}-v{edt.version}.pdf"
    reponse = HttpResponse(contenu, content_type='application/pdf')
    reponse['Content-Disposition'] = f'attachment; filename="{nom}"'
    reponse['Content-Length'] = str(len(contenu))
    return reponse


@api_view(['GET'])
@permission_classes([IsEdtReadOnlyOrPlanification])
def edt_audit_api(request, pk):
    """GET /api/edts/lmd/{id}/audit/ — audit d'un EDT existant."""
    from edts.models import EmploiDuTemps

    edt = EmploiDuTemps.objects.filter(pk=pk).first()
    if edt is None:
        return Response({'detail': 'EDT introuvable'},
                        status=status.HTTP_404_NOT_FOUND)
    rapport = V.valider_emploi_du_temps(edt)
    return Response({
        'emploi_du_temps_id': edt.pk,
        'version': edt.version,
        # 'statut' = verdict de validation (OK/BLOQUANT), 'statut_edt' = workflow.
        'statut': rapport.statut,
        'statut_edt': edt.statut,
        'annee_academique': edt.annee_academique.libelle,
        'titre': edt.titre or edt.population_label,
        'nb_seances_actives': edt.affectations.filter(actif=True).count(),
        'valide': rapport.valide,
        'violations': [v.as_dict() for v in rapport.violations],
        'warnings': rapport.warnings,
        'couverture': rapport.couverture,
    })
