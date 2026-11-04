"""GET-INJS — API d'import des inscrits et de génération annuelle.

Routes **ajoutées** (aucune route existante modifiée) :

* ``POST /api/edts/lmd/import/inscrits/analyser/``  — analyse d'un fichier, sans écriture ;
* ``POST /api/edts/lmd/import/inscrits/``           — import réel du fichier ;
* ``GET  /api/edts/lmd/import/inscrits/synthese/``  — effectifs importés par cohorte ;
* ``POST /api/edts/lmd/generate-annee/``            — génération des EDT de l'année ;
* ``GET  /api/edts/lmd/conception/``                — téléchargement de la conception.

Garde : les permissions existantes ``edts.permissions`` s'appliquent telles
quelles (lecture pour la synthèse et la conception, planification pour l'import
et la génération). Aucun second RBAC n'est créé.
"""

from pathlib import Path

from django.conf import settings
from django.http import FileResponse
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from edts.permissions import (
    IsEdtPlanification, IsEdtReadOnlyOrPlanification, IsEdtValidation,
)

#: Taille maximale acceptée pour un fichier d'inscrits (protection mémoire).
TAILLE_MAX_FICHIER = 20 * 1024 * 1024  # 20 Mo

#: Emplacement du document de conception, servi en téléchargement.
#: Le document **livré** est à la racine du dépôt (exigence de la mission) ;
#: ``docs/getinjs/Conception-GET-INJS.txt`` reste servi en repli pour ne pas
#: casser les liens existants.
RACINE_DEPOT = Path(settings.BASE_DIR).parent
CHEMIN_CONCEPTION = RACINE_DEPOT / 'Conception-GET-INJS.txt'
CHEMIN_CONCEPTION_REPLI = RACINE_DEPOT / 'docs' / 'getinjs' / 'Conception-GET-INJS.txt'


def _int(valeur):
    try:
        return int(valeur)
    except (TypeError, ValueError):
        return None


def _booleen(valeur):
    return str(valeur).lower() in ('1', 'true', 'oui', 'yes')


def _fichier_de_requete(request):
    """Extrait (nom, contenu) du fichier transmis — ``None`` si absent."""
    fichier = request.FILES.get('fichier') or request.FILES.get('file')
    if fichier is not None:
        if fichier.size > TAILLE_MAX_FICHIER:
            return None, None, {
                'motif_echec': 'FICHIER_TROP_VOLUMINEUX',
                'detail': {
                    'explication': (
                        f'Le fichier dépasse la limite de '
                        f'{TAILLE_MAX_FICHIER // (1024 * 1024)} Mo.'
                    ),
                    'taille_recue': fichier.size,
                },
            }
        return fichier.name, fichier.read(), None
    # Repli texte : contenu CSV transmis directement dans le corps.
    contenu = request.data.get('contenu')
    if contenu:
        return request.data.get('nom_fichier') or 'inscrits.csv', contenu, None
    return None, None, None


def _annee_de_requete(request):
    annee_id = _int(request.data.get('annee_academique_id') or request.query_params.get('annee'))
    if annee_id is None:
        return None, Response({
            'status': 'BLOCKING',
            'motif_echec': 'ANNEE_ACADEMIQUE_REQUISE',
            'detail': {
                'explication': (
                    'annee_academique_id est requis : un import et une génération '
                    'portent toujours sur une année académique précise.'
                ),
                'action_recommandee': 'Transmettre l’identifiant de l’année.',
            },
        }, status=status.HTTP_400_BAD_REQUEST)

    from scolarite.models import AnneeAcademique

    if not AnneeAcademique.objects.filter(pk=annee_id).exists():
        return None, Response({
            'status': 'BLOCKING',
            'motif_echec': 'ANNEE_ACADEMIQUE_INTROUVABLE',
            'detail': {
                'explication': f'L’année académique #{annee_id} est introuvable.',
                'action_recommandee': 'Vérifier l’identifiant transmis.',
            },
        }, status=status.HTTP_404_NOT_FOUND)
    return annee_id, None


def _executer_import(request, *, appliquer):
    """Tronc commun de l'analyse et de l'import réel."""
    from edts.moteur.import_inscrits import importer_inscrits

    annee_id, erreur = _annee_de_requete(request)
    if erreur is not None:
        return erreur

    nom_fichier, contenu, erreur_fichier = _fichier_de_requete(request)
    if erreur_fichier is not None:
        return Response({'status': 'BLOCKING', **erreur_fichier},
                        status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)
    if contenu is None:
        return Response({
            'status': 'BLOCKING',
            'motif_echec': 'FICHIER_REQUIS',
            'detail': {
                'explication': (
                    'Aucun fichier reçu. Formats acceptés : CSV (séparateur « ; » '
                    'ou « , ») et Excel (.xlsx).'
                ),
                'action_recommandee': (
                    'Joindre le fichier dans le champ multipart « fichier ».'
                ),
            },
        }, status=status.HTTP_400_BAD_REQUEST)

    rapport = importer_inscrits(
        annee_academique_id=annee_id,
        nom_fichier=nom_fichier,
        contenu=contenu,
        appliquer=appliquer,
        acteur=request.user if request.user.is_authenticated else None,
        # Écran « Importer les étudiants inscrits » : décocher « Reconstruire
        # le parcours » interdit la création des groupes/vagues absents.
        reconstruire_parcours=_booleen(
            request.data.get('reconstruire_parcours', True)),
    )
    donnees = rapport.as_dict()

    # Ordre volontaire : « aucune ligne exploitable » est une erreur de
    # CONTENU (422), avant les échecs de format/données référentielles (409).
    if not rapport.lignes_valides:
        return Response(donnees, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
    if rapport.motif_echec is not None:
        return Response(donnees, status=status.HTTP_409_CONFLICT)
    return Response(donnees, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsEdtPlanification])
def analyser_import_api(request):
    """POST /api/edts/lmd/import/inscrits/analyser/ — analyse SANS écriture.

    Le rapport est identique à celui de l'import réel (lignes lues, valides,
    rejetées avec motif, cohortes, effectifs) : il permet de valider un fichier
    client avant de l'intégrer, sans créer de groupes ni d'inscriptions.
    """
    return _executer_import(request, appliquer=False)


@api_view(['POST'])
@permission_classes([IsEdtPlanification])
def importer_inscrits_api(request):
    """POST /api/edts/lmd/import/inscrits/ — import réel, idempotent.

    Idempotence : la clé est le couple (année académique, matricule) ; réimporter
    le même fichier met à jour les lignes existantes sans en créer de nouvelles.
    L'écriture est transactionnelle : si aucune ligne n'est exploitable, aucune
    cohorte partielle n'est laissée en base.
    """
    return _executer_import(request, appliquer=True)


@api_view(['GET'])
@permission_classes([IsEdtReadOnlyOrPlanification])
def synthese_import_api(request):
    """GET /api/edts/lmd/import/inscrits/synthese/ — effectifs importés.

    Retourne le dénombrement **réel** des inscriptions importées, par filière,
    formation, parcours, niveau, groupe et vague — c'est l'effectif utilisé
    comme contrainte de capacité lors de la génération.
    """
    from edts.moteur.annee import effectif_importe, repartition_importee

    annee_id, erreur = _annee_de_requete(request)
    if erreur is not None:
        return erreur

    repartition = repartition_importee(annee_id)
    return Response({
        'annee_academique_id': annee_id,
        'effectif_total': effectif_importe(annee_id),
        'cohortes': repartition,
        'nb_cohortes': len(repartition),
    })


@api_view(['GET'])
@permission_classes([IsEdtReadOnlyOrPlanification])
def journal_imports_api(request):
    """GET /api/edts/lmd/import/inscrits/journal/ — journal des imports.

    Reconstruit les lots d'import depuis les inscriptions rattachées
    (``fichier`` + ``empreinte`` du fichier source) : seules des données
    réellement tracées sont exposées — lignes rattachées, étudiants
    inscrits, date de réception du lot. Aucune durée ni aucun rejet
    n'est inventé : l'import ne persiste que les lignes rattachées.
    """
    from django.db.models import Count, Min, Q

    from edts.models import InscriptionImportee

    annee_id, erreur = _annee_de_requete(request)
    if erreur is not None:
        return erreur

    lignes = (
        InscriptionImportee.objects.filter(annee_academique_id=annee_id)
        .values('fichier', 'empreinte')
        .annotate(
            lignes=Count('id'),
            inscrits=Count('id', filter=Q(statut=InscriptionImportee.Statut.INSCRIT)),
            formations=Count('ref_formation', distinct=True),
            groupes=Count('groupe', distinct=True),
            vagues=Count('vague', distinct=True),
            recu_le=Min('created_at'),
        )
        .order_by('-recu_le')[:10]
    )
    lots = [{
        'fichier': l['fichier'] or '(sans nom de fichier)',
        'empreinte': (l['empreinte'] or '')[:12],
        'lignes': l['lignes'],
        'inscrits': l['inscrits'],
        # Lignes du lot non comptées comme inscrites (radiées) : le journal
        # ne connaît que les lignes rattachées, aucun rejet n'est inventé.
        'ignores': l['lignes'] - l['inscrits'],
        'formations': l['formations'],
        'groupes': l['groupes'],
        'vagues': l['vagues'],
        'recu_le': l['recu_le'].isoformat() if l['recu_le'] else None,
    } for l in lignes]
    return Response({
        'annee_academique_id': annee_id,
        'lots': lots,
        'nb_lots': len(lots),
    })


def _sexe_court(valeur):
    """Normalise le sexe vers « M » / « F » (la base stocke MASCULIN/FEMININ)."""
    texte = (valeur or '').strip().upper()
    if texte.startswith('M'):
        return 'M'
    if texte.startswith('F'):
        return 'F'
    return ''


@api_view(['GET'])
@permission_classes([IsEdtReadOnlyOrPlanification])
def inscrits_population_api(request):
    """GET /api/edts/lmd/inscrits/?annee=&q=&formation=&niveau=&page=

    Population des étudiants inscrits d'une année, toutes origines, pour
    l'écran « Étudiants inscrits » (POPULATIONS LMD) : inscriptions
    administratives **validées** du processus INJS2026 (source « Base »)
    et inscriptions lues dans un fichier externe (source « Import »),
    fusionnées, triées par nom, puis paginées à 25 par page.

    Règles métier :
    - un même matricule présent dans les deux origines n'apparaît qu'une
      fois : l'inscription administrative, dossier métier de référence,
      fait foi (la ligne importée reste consultable dans la synthèse et
      le journal des imports) ;
    - une inscription administrative non validée n'est pas un étudiant
      inscrit : elle reste dans le circuit de validation de la scolarité ;
    - aucune donnée n'est inventée : le groupe d'un inscrit de la base
      est son affectation active, la vague son rattachement ; à défaut,
      le champ est vide et l'écran affiche « — ».

    Les facettes ``formations`` / ``niveaux`` décrivent la population de
    l'année (avant filtres) pour alimenter les listes déroulantes.
    """
    annee_id, erreur = _annee_de_requete(request)
    if erreur is not None:
        return erreur

    from edts.models import InscriptionImportee
    from scolarite.models import InscriptionAdministrative

    lignes = []
    matricules_base = set()
    for ins in (
        InscriptionAdministrative.objects.filter(
            annee_academique_id=annee_id,
            statut=InscriptionAdministrative.Statut.VALIDEE,
        )
        .select_related('etudiant__participant', 'ref_formation', 'niveau', 'vague')
        .prefetch_related('affectations__groupe')
    ):
        participant = ins.etudiant.participant
        matricules_base.add(participant.matricule)
        groupe = next(
            (a.groupe.nom for a in ins.affectations.all()
             if a.active and a.groupe_id),
            '',
        )
        lignes.append({
            'matricule': participant.matricule,
            'nom': participant.nom,
            'prenoms': participant.prenom,
            'sexe': _sexe_court(participant.sexe),
            'formation_id': ins.ref_formation_id,
            'formation_code': ins.ref_formation.code or '',
            'formation': ins.ref_formation.intitule,
            'niveau_id': ins.niveau_id,
            'niveau': ins.niveau.code,
            'niveau_ordre': ins.niveau.ordre,
            'groupe': groupe,
            'vague': ins.vague.libelle if ins.vague_id else '',
            'statut': 'Inscrit',
            'source': 'Base',
        })

    for ins in (
        InscriptionImportee.objects.filter(annee_academique_id=annee_id)
        .select_related('ref_formation', 'niveau', 'groupe', 'vague')
    ):
        if ins.matricule in matricules_base:
            continue
        lignes.append({
            'matricule': ins.matricule,
            'nom': ins.nom,
            'prenoms': ins.prenoms,
            'sexe': _sexe_court(ins.sexe),
            'formation_id': ins.ref_formation_id,
            'formation_code': ins.ref_formation.code or '',
            'formation': ins.ref_formation.intitule,
            'niveau_id': ins.niveau_id,
            'niveau': ins.niveau.code,
            'niveau_ordre': ins.niveau.ordre,
            'groupe': ins.groupe.nom if ins.groupe_id else '',
            'vague': ins.vague.libelle if ins.vague_id else '',
            'statut': ins.get_statut_display(),
            'source': 'Import',
        })

    formations = sorted(
        {
            l['formation_id']: {
                'id': l['formation_id'],
                'code': l['formation_code'],
                'intitule': l['formation'],
            }
            for l in lignes
        }.values(),
        key=lambda f: f['intitule'],
    )
    niveaux = sorted(
        {
            l['niveau_id']: {
                'id': l['niveau_id'],
                'code': l['niveau'],
                'ordre': l['niveau_ordre'],
            }
            for l in lignes
        }.values(),
        key=lambda n: (n['ordre'], n['code']),
    )

    recherche = (request.query_params.get('q') or '').strip().casefold()
    formation_id = _int(request.query_params.get('formation'))
    niveau_id = _int(request.query_params.get('niveau'))
    if recherche:
        lignes = [
            l for l in lignes
            if recherche in l['matricule'].casefold()
            or recherche in l['nom'].casefold()
            or recherche in l['prenoms'].casefold()
        ]
    if formation_id is not None:
        lignes = [l for l in lignes if l['formation_id'] == formation_id]
    if niveau_id is not None:
        lignes = [l for l in lignes if l['niveau_id'] == niveau_id]

    lignes.sort(key=lambda l: (l['nom'].casefold(), l['prenoms'].casefold(),
                               l['matricule']))

    taille_page = 25
    total = len(lignes)
    total_pages = (total + taille_page - 1) // taille_page
    try:
        page = int(request.query_params.get('page', 1))
    except (TypeError, ValueError):
        page = 1
    page = min(max(page, 1), total_pages) if total_pages else 1
    debut = (page - 1) * taille_page
    resultats = [
        {cle: ligne[cle] for cle in (
            'matricule', 'nom', 'prenoms', 'sexe', 'formation_code', 'formation',
            'niveau', 'groupe', 'vague', 'statut', 'source',
        )}
        for ligne in lignes[debut:debut + taille_page]
    ]
    return Response({
        'annee_academique_id': annee_id,
        'total': total,
        'page': page,
        'taille_page': taille_page,
        'total_pages': total_pages,
        'formations': formations,
        'niveaux': niveaux,
        'resultats': resultats,
    })


@api_view(['GET'])
@permission_classes([IsEdtReadOnlyOrPlanification])
def referentiels_api(request):
    """GET /api/edts/lmd/referentiels/?annee= — données de référence INJS.

    Alimente l'écran « Référentiels » du hub GET-INJS (onglets Filières &
    formations, Maquettes & modules, Bâtiments & salles, Enseignants,
    Groupes & vagues) avec les référentiels réels qui nourrissent le
    moteur de génération :

    - « filières » du compteur = mentions officielles (STAPS, STASE) et
      « formations » = filières métier (parcours) — vocabulaire de l'écran ;
    - une maquette est « publiée » lorsqu'elle est ACTIVE pour l'année,
      « paramétrable » lorsqu'elle est encore en brouillon (les autres
      statuts affichent leur libellé réel) ;
    - « modules » = ECUE des maquettes actives de l'année, c'est-à-dire
      exactement ce que le moteur transforme en besoins ;
    - l'effectif d'un groupe compte ses affectations actives et ses
      inscriptions importées rattachées — deux sources réelles, jamais
      d'estimation.
    """
    annee_id, erreur = _annee_de_requete(request)
    if erreur is not None:
        return erreur

    from django.db.models import Count, Sum

    from edts.models import InscriptionImportee
    from formations.models import (
        Formateur, RefBatiment, RefSalle, RefSite, RefVague,
    )
    from referentiels.models import RefFiliere, RefMention
    from scolarite.models import AffectationGroupe, ECUE, Groupe, Maquette

    mentions = [
        {
            'code': m.code,
            'nom': m.nom_complet or m.libelle,
            'ecole': m.ecole.code if m.ecole_id else '',
        }
        for m in RefMention.objects.filter(actif=True, archive=False)
        .select_related('ecole').order_by('code')
    ]

    groupes_par_filiere = {
        ligne['ref_formation__filiere_id']: ligne['n']
        for ligne in Groupe.objects.filter(annee_academique_id=annee_id)
        .values('ref_formation__filiere_id').annotate(n=Count('id'))
    }
    filieres_publiees = set(
        Maquette.objects.filter(
            annee_academique_id=annee_id, statut=Maquette.Statut.ACTIVE,
        ).values_list('ref_formation__filiere_id', flat=True),
    )
    parcours = [
        {
            'code': f.code,
            'libelle': f.libelle,
            'mention': f.mention.code if f.mention_id else '',
            'maquette': 'publiée' if f.pk in filieres_publiees else 'paramétrable',
            'groupes': groupes_par_filiere.get(f.pk, 0),
        }
        for f in RefFiliere.objects.filter(actif=True, archive=False)
        .select_related('mention').order_by('code')
    ]

    maquettes = [
        {
            'id': m.pk,
            'formation': m.ref_formation.intitule,
            'niveau': m.niveau.code,
            'version': m.version,
            'statut': m.statut,
            'statut_libelle': (
                'Publiée' if m.statut == Maquette.Statut.ACTIVE
                else 'Paramétrable' if m.statut == Maquette.Statut.BROUILLON
                else m.get_statut_display()
            ),
            'publiee': m.statut == Maquette.Statut.ACTIVE,
            'ues': m.nb_ues,
            'modules': m.nb_modules,
            'credits': m.credits or 0,
        }
        for m in Maquette.objects.filter(annee_academique_id=annee_id)
        .select_related('ref_formation', 'niveau')
        .annotate(
            nb_ues=Count('unites_enseignement', distinct=True),
            nb_modules=Count('unites_enseignement__ecues', distinct=True),
            credits=Sum('unites_enseignement__credits'),
        )
        .order_by('ref_formation__intitule', 'niveau__ordre')
    ]
    modules = ECUE.objects.filter(
        ue__maquette__annee_academique_id=annee_id,
        ue__maquette__statut=Maquette.Statut.ACTIVE,
    ).count()

    salles = [
        {
            'code': s.code,
            'nom': s.nom,
            'batiment': s.batiment.nom if s.batiment_id else '',
            'site': s.site.nom if s.site_id else '',
            'capacite': s.capacite,
            'type': s.get_type_lieu_display(),
        }
        for s in RefSalle.objects.filter(actif=True)
        .select_related('batiment', 'site')
        .order_by('batiment__nom', 'nom')
    ]

    enseignants = [
        {
            'nom': f.nom,
            'prenom': f.prenom,
            'specialite': f.specialite or '',
            'grade': f.grade_ref.libelle if f.grade_ref_id else '',
            'statut': f.statut_enseignant or '',
        }
        for f in Formateur.objects.select_related('grade_ref')
        .order_by('nom', 'prenom')
    ]

    effectifs = {}
    for source in (
        AffectationGroupe.objects.filter(
            inscription__annee_academique_id=annee_id, active=True,
        ).values('groupe_id').annotate(n=Count('id')),
        InscriptionImportee.objects.filter(
            annee_academique_id=annee_id, groupe__isnull=False,
        ).values('groupe_id').annotate(n=Count('id')),
    ):
        for ligne in source:
            effectifs[ligne['groupe_id']] = (
                effectifs.get(ligne['groupe_id'], 0) + ligne['n']
            )
    groupes = [
        {
            'nom': g.nom,
            'formation': g.ref_formation.intitule,
            'niveau': g.niveau.code,
            'vague': g.vague.libelle if g.vague_id else '',
            'capacite': g.capacite_max,
            'effectif': effectifs.get(g.pk, 0),
        }
        for g in Groupe.objects.filter(annee_academique_id=annee_id)
        .select_related('ref_formation', 'niveau', 'vague')
        .order_by('ref_formation__intitule', 'niveau__ordre', 'nom')
    ]

    groupes_par_vague = {
        ligne['vague_id']: ligne['n']
        for ligne in Groupe.objects.filter(
            annee_academique_id=annee_id, vague__isnull=False,
        ).values('vague_id').annotate(n=Count('id'))
    }
    vagues = [
        {
            'code': v.code or '',
            'libelle': v.libelle,
            'groupes': groupes_par_vague.get(v.pk, 0),
        }
        for v in RefVague.objects.filter(actif=True).order_by('ordre', 'libelle')
    ]

    return Response({
        'annee_academique_id': annee_id,
        'compteurs': {
            'filieres': len(mentions),
            'formations': len(parcours),
            'modules': modules,
            'groupes': len(groupes),
            'vagues': len(vagues),
            'salles': len(salles),
            'enseignants': len(enseignants),
        },
        'mentions': mentions,
        'parcours': parcours,
        'maquettes': maquettes,
        'infrastructure': {
            'sites': RefSite.objects.count(),
            'batiments': RefBatiment.objects.count(),
            'salles': salles,
        },
        'enseignants': enseignants,
        'groupes': groupes,
        'vagues': vagues,
    })


@api_view(['POST'])
@permission_classes([IsEdtPlanification])
def generate_annee_api(request):
    """POST /api/edts/lmd/generate-annee/ — EDT de TOUS les groupes de l'année.

    Paramètres : ``annee_academique_id`` (requis), ``semaines`` (optionnelles),
    ``persister`` (bool, défaut faux = prévisualisation), ``remplacer`` (défaut
    vrai — idempotence), ``inclure_maquette`` (défaut vrai : complète les
    cohortes sans affectation pédagogique à partir de la maquette active).

    Une année incomplète n'est **jamais** présentée comme réussie : le bilan
    expose par groupe le statut, les séances attendues/placées/non placées et le
    motif d'échec éventuel. Aucune publication n'est effectuée ici.
    """
    from edts.moteur.annee import ANNEE_IMPOSSIBLE, generer_annee

    annee_id, erreur = _annee_de_requete(request)
    if erreur is not None:
        return erreur

    semaines = request.data.get('semaines')
    if isinstance(semaines, str):
        semaines = [s for s in semaines.replace(' ', '').split(',') if s]
    semaines = [int(s) for s in semaines if str(s).isdigit()] if semaines else None

    def _ids(cle):
        brut = request.data.get(cle)
        if isinstance(brut, str):
            brut = [x for x in brut.replace(' ', '').split(',') if x]
        return [int(x) for x in brut if str(x).isdigit()] if brut else None

    bilan = generer_annee(
        annee_id,
        semaines=semaines,
        persister=_booleen(request.data.get('persister')),
        remplacer=_booleen(request.data.get('remplacer', True)),
        inclure_maquette=_booleen(request.data.get('inclure_maquette', True)),
        formation_ids=_ids('formation_ids') or _ids('formations'),
        niveau_ids=_ids('niveau_ids') or _ids('niveaux'),
        groupe_ids=_ids('groupe_ids') or _ids('groupes'),
        semestre_numeros=_ids('semestre_numeros') or _ids('semestres'),
        inclure_samedi=_booleen(request.data.get('inclure_samedi', True)),
        eviter_pause_meridienne=_booleen(
            request.data.get('eviter_pause_meridienne')),
        max_seances_par_groupe_semaine=_int(
            request.data.get('max_seances_par_groupe_semaine')),
    )

    if bilan['status_global'] == ANNEE_IMPOSSIBLE:
        return Response(bilan, status=status.HTTP_409_CONFLICT)
    persiste = bilan.get('persistence_demandee')
    complet = bilan['status_global'] == 'COMPLETE'
    return Response(
        bilan,
        status=status.HTTP_201_CREATED if (complet and persiste) else status.HTTP_200_OK,
    )


@api_view(['GET'])
@permission_classes([IsEdtReadOnlyOrPlanification])
def conception_api(request):
    """GET /api/edts/lmd/conception/ — télécharge ``Conception-GET-INJS.txt``.

    Le document de conception est **le fichier du dépôt**
    (``docs/getinjs/Conception-GET-INJS.txt``) : il n'existe pas de copie en
    base qui pourrait diverger. S'il est absent, la réponse le dit
    explicitement (404 motivé) au lieu de servir un contenu vide.
    """
    chemin = CHEMIN_CONCEPTION if CHEMIN_CONCEPTION.is_file() else CHEMIN_CONCEPTION_REPLI
    if not chemin.is_file():
        return Response({
            'status': 'BLOCKING',
            'motif_echec': 'CONCEPTION_INTROUVABLE',
            'detail': {
                'explication': 'Le document de conception est absent du dépôt.',
                'chemins_attendus': [str(CHEMIN_CONCEPTION), str(CHEMIN_CONCEPTION_REPLI)],
            },
        }, status=status.HTTP_404_NOT_FOUND)

    reponse = FileResponse(
        chemin.open('rb'),
        as_attachment=True,
        filename='Conception-GET-INJS.txt',
        content_type='text/plain; charset=utf-8',
    )
    return reponse


# ══════════════════════════════════════════════════════════════════════════════
# LOT 2 — CAMPAGNES DE GÉNÉRATION
# ══════════════════════════════════════════════════════════════════════════════
#
# Routes AJOUTÉES sous ``campagnes/`` : aucune route existante n'est renommée ni
# supprimée. Les permissions existantes (``edts.permissions``) restent seules
# juges : planification pour créer/lancer, validation pour valider/publier,
# lecture pour consulter.

def _refus(exc):
    """Traduit un refus métier en réponse HTTP structurée (jamais un 500)."""
    statuts_http = {
        'CAMPAGNE_INTROUVABLE': status.HTTP_404_NOT_FOUND,
        'ANNEE_ACADEMIQUE_INTROUVABLE': status.HTTP_404_NOT_FOUND,
        'CAMPAGNE_DEJA_EN_COURS': status.HTTP_409_CONFLICT,
        'CAMPAGNE_DEJA_EXISTANTE': status.HTTP_409_CONFLICT,
        'TRANSITION_REFUSEE': status.HTTP_409_CONFLICT,
        'VALIDATION_BLOQUANTE': status.HTTP_409_CONFLICT,
        'PUBLICATION_INCOMPLETE': status.HTTP_409_CONFLICT,
        'PUBLICATION_ECHOUEE': status.HTTP_409_CONFLICT,
        'AUCUN_EDT_A_VALIDER': status.HTTP_409_CONFLICT,
        'AUCUN_EDT_A_PUBLIER': status.HTTP_409_CONFLICT,
    }
    return Response(
        {'status': 'BLOCKING', 'motif_echec': exc.motif, 'detail': exc.detail},
        status=statuts_http.get(exc.motif, status.HTTP_400_BAD_REQUEST),
    )


@api_view(['GET', 'POST'])
@permission_classes([IsEdtReadOnlyOrPlanification])
def campagnes_api(request):
    """GET liste / POST crée une campagne de génération.

    GET : ``?annee=<id>`` filtre par année académique.
    POST : ``annee_academique_id`` et ``libelle`` requis ; ``semaines``,
    ``perimetre`` et ``parametres`` optionnels.
    """
    from edts.moteur.campagnes import (
        TransitionRefusee, campagne_en_dict, creer_campagne,
    )
    from edts.models import CampagneGeneration

    if request.method == 'GET':
        qs = CampagneGeneration.objects.select_related('annee_academique', 'cree_par')
        annee_id = _int(request.query_params.get('annee'))
        if annee_id:
            qs = qs.filter(annee_academique_id=annee_id)
        donnees = [campagne_en_dict(c) for c in qs[:200]]
        return Response({'count': qs.count(), 'results': donnees})

    annee_id = _int(request.data.get('annee_academique_id'))
    libelle = (request.data.get('libelle') or '').strip()
    if annee_id is None or not libelle:
        return Response({
            'status': 'BLOCKING',
            'motif_echec': 'PARAMETRES_INCOMPLETS',
            'detail': {
                'explication': 'annee_academique_id et libelle sont requis.',
                'champs_attendus': ['annee_academique_id', 'libelle'],
            },
        }, status=status.HTTP_400_BAD_REQUEST)

    semaines = request.data.get('semaines') or []
    if isinstance(semaines, str):
        semaines = [s for s in semaines.replace(' ', '').split(',') if s]
    perimetre = request.data.get('perimetre') or {}
    parametres = request.data.get('parametres') or {}
    try:
        campagne = creer_campagne(
            annee_academique_id=annee_id,
            libelle=libelle,
            user=request.user,
            semaines=semaines,
            perimetre=perimetre if isinstance(perimetre, dict) else {},
            parametres=parametres if isinstance(parametres, dict) else {},
        )
    except TransitionRefusee as exc:
        return _refus(exc)
    return Response(campagne_en_dict(campagne), status=status.HTTP_201_CREATED)


@api_view(['GET'])
@permission_classes([IsEdtReadOnlyOrPlanification])
def historique_generations_api(request):
    """GET /api/edts/campagnes/historique/ — historique des générations.

    Une ligne par **exécution** de campagne (les campagnes jamais lancées
    n'y figurent pas : il n'y a rien à tracer). Chaque ligne est calculée
    depuis le bilan réellement persisté de l'exécution : séances placées /
    attendues, couverture, conflits cumulés des groupes, semestres
    couverts (déduits des niveaux du bilan, S1/S2 pour le premier niveau,
    etc.) et durée mesurée. Le périmètre est résolu en noms lisibles.
    """
    from edts.models import ExecutionCampagne
    from scolarite.models import Groupe, Niveau

    executions = (
        ExecutionCampagne.objects
        .select_related('campagne', 'campagne__annee_academique')
        .order_by('-demarree_le')[:20]
    )

    # Résolution des noms du périmètre (identifiants → libellés réels).
    from formations.referentiel_injs_l6 import formations_injs

    formations_par_id = {
        f.pk: f for f in formations_injs()
    }
    niveaux_par_code = {n.code: n for n in Niveau.objects.all()}
    groupes_par_id = {
        g.pk: g.nom for g in Groupe.objects.all().only('pk', 'nom')
    }

    lignes = []
    for execution in executions:
        campagne = execution.campagne
        perimetre = campagne.perimetre or {}
        bilan = execution.bilan or {}
        groupes_bilan = bilan.get('groupes') or []
        totaux = bilan.get('totaux') or {}

        formation_ids = perimetre.get('formations') or []
        formations = [
            formations_par_id[fid].intitule
            for fid in formation_ids if fid in formations_par_id
        ]
        filieres = sorted({
            formations_par_id[fid].filiere_code
            for fid in formation_ids
            if fid in formations_par_id and formations_par_id[fid].filiere_code
        })
        niveau_ids = perimetre.get('niveaux') or []
        niveaux = sorted({
            n.code for n in Niveau.objects.filter(pk__in=niveau_ids)
        }) if niveau_ids else []
        groupe_ids = perimetre.get('groupes') or []
        groupes = [
            groupes_par_id[gid] for gid in groupe_ids if gid in groupes_par_id
        ]

        # Semestres couverts : déduits des niveaux présents dans le bilan
        # (niveau d'ordre k → semestres S(2k-1) et S(2k)).
        semestres = set()
        for ligne_bilan in groupes_bilan:
            niveau = niveaux_par_code.get(ligne_bilan.get('niveau'))
            if niveau is not None and niveau.ordre:
                semestres.add(f'S{2 * niveau.ordre - 1}')
                semestres.add(f'S{2 * niveau.ordre}')

        placees = totaux.get('seances_placees')
        attendues = totaux.get('seances_attendues')
        couverture = (
            round(placees / attendues * 100, 1)
            if placees is not None and attendues else None
        )
        lignes.append({
            'id': execution.pk,
            'campagne_id': campagne.pk,
            'libelle': campagne.libelle,
            'annee_academique': campagne.annee_academique.libelle,
            'date': execution.demarree_le.isoformat() if execution.demarree_le else None,
            'statut': execution.statut,
            'duree_ms': execution.duree_ms,
            'perimetre': {
                'filieres': filieres,
                'formations': formations,
                'niveaux': niveaux,
                'groupes': groupes,
            },
            'semestres': sorted(semestres, key=lambda x: int(x[1:])),
            'seances_placees': placees,
            'seances_attendues': attendues,
            'couverture_pct': couverture,
            'conflits': sum((l.get('conflits') or 0) for l in groupes_bilan),
        })
    return Response({'executions': lignes, 'count': len(lignes)})


@api_view(['GET'])
@permission_classes([IsEdtReadOnlyOrPlanification])
def campagne_detail_api(request, pk):
    """GET /api/edts/campagnes/<pk>/ — fiche de la campagne."""
    from edts.moteur.campagnes import TransitionRefusee, campagne_en_dict, _charger

    try:
        campagne = _charger(pk)
    except TransitionRefusee as exc:
        return _refus(exc)
    return Response(campagne_en_dict(campagne))


@api_view(['POST'])
@permission_classes([IsEdtPlanification])
def campagne_demarrer_api(request, pk):
    """POST /api/edts/campagnes/<pk>/demarrer/ — lance une exécution.

    ``asynchrone`` (défaut vrai) : la génération tourne en arrière-plan et
    l'API répond immédiatement avec l'identifiant d'exécution ; l'avancement
    s'observe sur ``/statut/``. ``asynchrone=false`` exécute dans la requête
    (utile aux petits périmètres et aux tests).
    """
    from edts.moteur.campagnes import TransitionRefusee, demarrer_campagne

    asynchrone = str(request.data.get('asynchrone', 'true')).lower() not in ('false', '0', 'non')
    try:
        resultat = demarrer_campagne(pk, user=request.user, asynchrone=asynchrone)
    except TransitionRefusee as exc:
        return _refus(exc)
    return Response(resultat, status=status.HTTP_202_ACCEPTED if asynchrone else status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsEdtReadOnlyOrPlanification])
def campagne_statut_api(request, pk):
    """GET /api/edts/campagnes/<pk>/statut/ — interrogation périodique."""
    from edts.moteur.campagnes import TransitionRefusee, statut_campagne

    try:
        return Response(statut_campagne(pk))
    except TransitionRefusee as exc:
        return _refus(exc)


@api_view(['GET'])
@permission_classes([IsEdtReadOnlyOrPlanification])
def campagne_resultat_api(request, pk):
    """GET /api/edts/campagnes/<pk>/resultat/ — bilan par groupe + historique."""
    from edts.moteur.campagnes import TransitionRefusee, resultat_campagne

    try:
        return Response(resultat_campagne(pk))
    except TransitionRefusee as exc:
        return _refus(exc)


@api_view(['POST'])
@permission_classes([IsEdtPlanification])
def campagne_donnees_pretes_api(request, pk):
    """POST /api/edts/campagnes/<pk>/donnees-pretes/ — ``BROUILLON`` → ``PRET``."""
    from edts.moteur.campagnes import TransitionRefusee, marquer_pret

    try:
        return Response(marquer_pret(pk, user=request.user))
    except TransitionRefusee as exc:
        return _refus(exc)


@api_view(['POST'])
@permission_classes([IsEdtValidation])
def campagne_valider_api(request, pk):
    """POST /api/edts/campagnes/<pk>/valider/ — contrôle et validation.

    Réservé à la Direction / Admin, comme la validation d'un EDT unitaire.
    """
    from edts.moteur.campagnes import TransitionRefusee, valider_campagne

    try:
        return Response(valider_campagne(pk, user=request.user))
    except TransitionRefusee as exc:
        return _refus(exc)


@api_view(['POST'])
@permission_classes([IsEdtValidation])
def campagne_publier_api(request, pk):
    """POST /api/edts/campagnes/<pk>/publier/ — publication atomique du périmètre."""
    from edts.moteur.campagnes import TransitionRefusee, publier_campagne

    try:
        return Response(publier_campagne(
            pk, user=request.user, motif=(request.data.get('motif') or '').strip(),
        ))
    except TransitionRefusee as exc:
        return _refus(exc)
