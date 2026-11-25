"""Import de maquettes pédagogiques depuis un fichier Excel ou CSV.

Réutilise **le même format de fichier** que la commande
``manage.py import_maquette`` (:data:`COLONNES`, :data:`OBLIGATOIRES`,
:data:`EXEMPLE`), afin qu'un fichier préparé pour l'interface soit aussi
importable en ligne de commande — et inversement.

Le flux est en deux temps, comme l'exige l'interface :

1. :func:`analyser` — lecture pure, **aucune écriture** : résolution des
   référentiels (année, formation, parcours, niveau, semestre), contrôle des
   nombres, détection des doublons et des maquettes verrouillées. Le résultat
   est un rapport complet (lignes valides, erreurs, avertissements, résumé) et
   un plan d'import ;
2. :func:`appliquer` — exécution du plan dans **une seule transaction** : si
   une seule écriture échoue, rien n'est conservé.

Aucune donnée invalide n'est jamais intégrée silencieusement : un fichier
comportant au moins une erreur bloquante est refusé en bloc.
"""

from __future__ import annotations

import csv
import io

from django.db import transaction

from formations.models import RefFormation, RefModule
from scolarite.management.commands.import_maquette import (
    COLONNES,
    EXEMPLE,
    OBLIGATOIRES,
    ErreurLigne,
    _decimal,
    _entier,
    _numero_semestre,
    _texte,
)
from scolarite.models import (
    ECUE,
    UE,
    AnneeAcademique,
    Maquette,
    MaquetteJournal,
    Niveau,
    Parcours,
    Semestre,
)

#: Taille maximale acceptée (protège la mémoire du serveur).
TAILLE_MAX = 5 * 1024 * 1024
EXTENSIONS = {'.csv', '.xlsx', '.xlsm'}
#: Nombre de lignes renvoyées en prévisualisation (le rapport, lui, est complet).
LIGNES_APERCU = 300
#: Une maquette d'un niveau LMD vaut 60 crédits ; au-delà on avertit.
CREDITS_ATTENDUS = 60


class FichierInvalide(ValueError):
    """Fichier refusé avant toute analyse (format, taille, structure)."""


# ── Lecture ─────────────────────────────────────────────────────────────────
def lire(nom_fichier, contenu):
    """Lit un CSV/XLSX en mémoire et retourne les lignes sous forme de dicts.

    Lève :class:`FichierInvalide` si le format, la taille ou la structure ne
    permettent pas une analyse fiable.
    """
    if not contenu:
        raise FichierInvalide('Le fichier est vide.')
    if len(contenu) > TAILLE_MAX:
        raise FichierInvalide(
            f'Fichier trop volumineux ({len(contenu) // 1024} Ko) : maximum '
            f'{TAILLE_MAX // (1024 * 1024)} Mo.',
        )
    extension = ('.' + nom_fichier.rsplit('.', 1)[-1].lower()) if '.' in nom_fichier else ''
    if extension not in EXTENSIONS:
        raise FichierInvalide(
            'Format non pris en charge : utilisez un fichier .xlsx (Excel) ou .csv.',
        )

    lignes = _lignes_csv(contenu) if extension == '.csv' else _lignes_excel(contenu)
    lignes = [ligne for ligne in lignes if not _ligne_vide(ligne)]
    if not lignes:
        raise FichierInvalide('Le fichier ne contient aucune ligne exploitable.')
    manquantes = [colonne for colonne in OBLIGATOIRES if colonne not in lignes[0]]
    if manquantes:
        raise FichierInvalide(
            'Colonnes obligatoires absentes : ' + ', '.join(manquantes)
            + '. Téléchargez le modèle d’import pour obtenir la structure attendue.',
        )
    return lignes


def _ligne_vide(ligne):
    return all(_texte(valeur) == '' for valeur in ligne.values())


def _lignes_csv(contenu):
    # Détection du séparateur : « ; » (convention projet) mais aussi « , » et
    # tabulation, pour ne pas refuser un fichier exporté par un autre outil.
    try:
        texte = contenu.decode('utf-8-sig')
    except UnicodeDecodeError:
        try:
            texte = contenu.decode('cp1252')
        except UnicodeDecodeError:
            raise FichierInvalide(
                'Encodage illisible : enregistrez le fichier en UTF-8 (CSV UTF-8).',
            )
    echantillon = texte[:4096]
    try:
        dialecte = csv.Sniffer().sniff(echantillon, delimiters=';,\t')
        delimiteur = dialecte.delimiter
    except csv.Error:
        delimiteur = ';'
    lecteur = csv.DictReader(io.StringIO(texte), delimiter=delimiteur)
    if not lecteur.fieldnames:
        raise FichierInvalide('Aucune colonne détectée : le fichier semble vide.')
    return [
        {(_texte(cle).upper()): valeur for cle, valeur in ligne.items() if cle}
        for ligne in lecteur
    ]


def _lignes_excel(contenu):
    try:
        from openpyxl import load_workbook
    except ImportError:  # pragma: no cover - dépendance déclarée dans requirements
        raise FichierInvalide('openpyxl est requis pour lire un fichier Excel.')

    try:
        classeur = load_workbook(io.BytesIO(contenu), data_only=True, read_only=True)
    except Exception:
        raise FichierInvalide(
            'Fichier Excel illisible ou corrompu : vérifiez qu’il s’agit bien '
            'd’un classeur .xlsx non protégé.',
        )
    feuille = classeur.active
    iterateur = feuille.iter_rows(values_only=True)
    entetes = [_texte(cellule).upper() for cellule in next(iterateur, ())]
    lignes = []
    for valeurs in iterateur:
        if not valeurs or all(_texte(valeur) == '' for valeur in valeurs):
            continue
        lignes.append(dict(zip(entetes, valeurs)))
    classeur.close()
    return lignes


def modele(fmt='csv'):
    """Génère le fichier modèle (CSV ou XLSX) prérempli avec deux lignes."""
    if fmt == 'csv':
        tampon = io.StringIO()
        redacteur = csv.DictWriter(tampon, fieldnames=COLONNES, delimiter=';', lineterminator='\r\n')
        redacteur.writeheader()
        redacteur.writerows(EXEMPLE)
        return tampon.getvalue().encode('utf-8-sig')

    if fmt == 'xlsx':
        from openpyxl import Workbook
        from openpyxl.styles import Font

        classeur = Workbook()
        feuille = classeur.active
        feuille.title = 'Maquette'
        feuille.append(COLONNES)
        for cellule in feuille[1]:
            cellule.font = Font(bold=True)
        for exemple in EXEMPLE:
            feuille.append([exemple[colonne] for colonne in COLONNES])
        flux = io.BytesIO()
        classeur.save(flux)
        return flux.getvalue()

    raise FichierInvalide('Modèle disponible en CSV ou Excel uniquement.')


# ── Analyse (aucune écriture) ───────────────────────────────────────────────
def analyser(lignes):
    """Analyse les lignes et prépare un plan d'import sans toucher à la base.

    Retourne un dict sérialisable : ``lignes`` (aperçu), ``maquettes`` (plan
    lisible), ``erreurs``, ``avertissements``, ``resume``, ``importable`` et
    ``plan`` (structures internes prêtes pour :func:`appliquer`).
    """
    erreurs = []
    avertissements = []
    apercu = []
    plan = {}
    doublons = set()
    compteurs = {
        'lignes_lues': 0, 'lignes_valides': 0, 'lignes_ignorees': 0,
        'doublons': 0, 'maquettes': 0, 'ue': 0, 'ecue': 0,
        'modules_lies': 0, 'modules_absents': set(),
    }

    for index, ligne in enumerate(lignes, start=2):
        compteurs['lignes_lues'] += 1
        ligne_apercu = {
            'ligne': index,
            'annee': _texte(ligne.get('ANNEE')),
            'formation': _texte(ligne.get('FORMATION')),
            'parcours': _texte(ligne.get('PARCOURS')),
            'niveau': _texte(ligne.get('NIVEAU')).upper(),
            'semestre': _texte(ligne.get('SEMESTRE')),
            'ue_code': _texte(ligne.get('UE_CODE')),
            'ue_intitule': _texte(ligne.get('UE_INTITULE')),
            'ecue_code': _texte(ligne.get('ECUE_CODE')),
            'ecue_intitule': _texte(ligne.get('ECUE_INTITULE')),
            'messages': [],
        }
        try:
            cle_doublon = _cle_ligne(ligne)
            if cle_doublon in doublons:
                compteurs['doublons'] += 1
                compteurs['lignes_ignorees'] += 1
                ligne_apercu['statut'] = 'doublon'
                ligne_apercu['messages'].append(
                    'Ligne identique à une précédente (même UE/ECUE) : ignorée.',
                )
                avertissements.append({'ligne': index, 'message': ligne_apercu['messages'][0]})
                apercu.append(ligne_apercu)
                continue
            doublons.add(cle_doublon)

            _integrer_ligne(ligne, index, plan, compteurs)
            compteurs['lignes_valides'] += 1
            ligne_apercu['statut'] = 'ok'
        except ErreurLigne as erreur:
            compteurs['lignes_ignorees'] += 1
            ligne_apercu['statut'] = 'erreur'
            ligne_apercu['messages'].append(str(erreur))
            erreurs.append({'ligne': index, 'message': str(erreur)})

        apercu.append(ligne_apercu)

    # Avertissements de cohérence, calculés une fois toutes les lignes connues.
    for maquette in plan.values():
        total_credits = 0
        for ue in maquette['ue'].values():
            total_credits += ue['credits'] or 0
            somme_ecue = sum(ecue['credits'] or 0 for ecue in ue['ecue'].values())
            if somme_ecue and ue['credits'] and somme_ecue != ue['credits']:
                avertissements.append({
                    'ligne': None,
                    'message': (
                        f"{maquette['libelle']} / {ue['code']} : la somme des crédits des "
                        f"ECUE ({somme_ecue}) diffère des crédits de l'UE ({ue['credits']})."
                    ),
                })
            for ecue in ue['ecue'].values():
                if ecue['volume_cm'] == 0 and ecue['volume_td'] == 0 and ecue['volume_tp'] == 0:
                    avertissements.append({
                        'ligne': None,
                        'message': (
                            f"{maquette['libelle']} / {ecue['code']} : aucun volume horaire "
                            'CM/TD/TP renseigné.'
                        ),
                    })
        if total_credits and total_credits != CREDITS_ATTENDUS:
            avertissements.append({
                'ligne': None,
                'message': (
                    f"{maquette['libelle']} : {total_credits} crédits au total "
                    f'(attendu {CREDITS_ATTENDUS} pour un niveau LMD).'
                ),
            })

    if compteurs['modules_absents']:
        avertissements.append({
            'ligne': None,
            'message': 'Modules opérationnels introuvables (non rattachés) : '
                       + ', '.join(sorted(compteurs['modules_absents'])),
        })

    compteurs['maquettes'] = len(plan)
    compteurs['modules_absents'] = len(compteurs['modules_absents'])
    resume = {cle: valeur for cle, valeur in compteurs.items()}
    resume['erreurs'] = len(erreurs)
    resume['avertissements'] = len(avertissements)

    return {
        'importable': not erreurs and bool(plan),
        'lignes': apercu[:LIGNES_APERCU],
        'lignes_tronquees': max(0, len(apercu) - LIGNES_APERCU),
        'maquettes': [_resume_maquette(maquette) for maquette in plan.values()],
        'erreurs': erreurs,
        'avertissements': avertissements,
        'resume': resume,
        'plan': plan,
    }


def _cle_ligne(ligne):
    """Clé normalisée servant à repérer les doublons stricts du fichier."""
    champs = ('ANNEE', 'FORMATION', 'PARCOURS', 'NIVEAU', 'SEMESTRE', 'UE_CODE', 'ECUE_CODE')
    return tuple(_texte(ligne.get(champ)).casefold() for champ in champs)


def _integrer_ligne(ligne, index, plan, compteurs):
    """Valide une ligne et l'ajoute au plan (aucune écriture en base)."""
    annee_libelle = _texte(ligne.get('ANNEE'))
    formation_intitule = _texte(ligne.get('FORMATION'))
    parcours_code = _texte(ligne.get('PARCOURS'))
    niveau_code = _texte(ligne.get('NIVEAU')).upper()

    for nom, valeur in (
        ('ANNEE', annee_libelle), ('FORMATION', formation_intitule),
        ('NIVEAU', niveau_code), ('SEMESTRE', _texte(ligne.get('SEMESTRE'))),
        ('UE_CODE', _texte(ligne.get('UE_CODE'))), ('UE_INTITULE', _texte(ligne.get('UE_INTITULE'))),
        ('ECUE_CODE', _texte(ligne.get('ECUE_CODE'))),
        ('ECUE_INTITULE', _texte(ligne.get('ECUE_INTITULE'))),
    ):
        if not valeur:
            raise ErreurLigne(f'{nom} est obligatoire.')

    annee = AnneeAcademique.objects.filter(libelle=annee_libelle).first()
    if not annee:
        raise ErreurLigne(f'année académique « {annee_libelle} » inconnue.')

    formation = RefFormation.objects.filter(intitule__iexact=formation_intitule).first()
    if not formation:
        raise ErreurLigne(f'formation « {formation_intitule} » absente du référentiel.')

    niveau = Niveau.objects.filter(code__iexact=niveau_code).first()
    if not niveau:
        raise ErreurLigne(f'niveau « {niveau_code} » inconnu.')

    parcours = None
    if parcours_code:
        parcours = Parcours.objects.filter(
            ref_formation=formation, code__iexact=parcours_code,
        ).first()
        if not parcours:
            raise ErreurLigne(f'parcours « {parcours_code} » inconnu pour cette formation.')

    numero = _numero_semestre(ligne.get('SEMESTRE'))
    semestre = Semestre.objects.filter(niveau=niveau, numero=numero).first()
    if not semestre:
        raise ErreurLigne(f'semestre S{numero} non défini pour le niveau {niveau.code}.')

    ue_code = _texte(ligne.get('UE_CODE'))
    ecue_code = _texte(ligne.get('ECUE_CODE'))

    cle_maquette = (annee.pk, formation.pk, parcours.pk if parcours else None, niveau.pk)
    maquette = plan.get(cle_maquette)
    if maquette is None:
        existante, verrouillee = _maquette_cible(annee, formation, parcours, niveau)
        maquette = {
            'annee': annee, 'formation': formation, 'parcours': parcours, 'niveau': niveau,
            'libelle': f'{formation.intitule} – {niveau.code}',
            'existante': existante, 'verrouillee': verrouillee, 'ue': {},
        }
        plan[cle_maquette] = maquette

    if maquette['verrouillee']:
        # Une maquette validée/active/archivée est immuable (garde-fou R4) :
        # l'import ne la modifie pas, il doit passer par une nouvelle version.
        raise ErreurLigne(
            f"maquette « {maquette['libelle']} » verrouillée "
            f"(statut {maquette['existante'].statut}) : exportez-la puis importez "
            'une nouvelle version (clonage) avant de la modifier.',
        )

    caractere = _texte(ligne.get('UE_CARACTERE')).upper() or UE.Caractere.OBLIGATOIRE
    if caractere not in UE.Caractere.values:
        raise ErreurLigne(
            f'UE_CARACTERE « {caractere} » invalide (attendu : {", ".join(UE.Caractere.values)}).',
        )
    credits_ue = _entier(ligne.get('UE_CREDITS'), 'UE_CREDITS')
    if credits_ue < 0:
        raise ErreurLigne('UE_CREDITS ne peut pas être négatif.')

    ue = maquette['ue'].get(ue_code.casefold())
    if ue is None:
        ue = {
            'code': ue_code, 'intitule': _texte(ligne.get('UE_INTITULE')),
            'credits': credits_ue, 'caractere': caractere,
            'semestre': semestre, 'ecue': {},
        }
        maquette['ue'][ue_code.casefold()] = ue
        compteurs['ue'] += 1
    else:
        # Une même UE écrite deux fois : l'intitulé et le semestre doivent
        # concorder, sinon le fichier est ambigu.
        if _texte(ligne.get('UE_INTITULE')).casefold() != ue['intitule'].casefold():
            raise ErreurLigne(
                f"UE {ue_code} déclarée avec deux intitulés différents "
                f"(« {ue['intitule']} » puis « {_texte(ligne.get('UE_INTITULE'))} »).",
            )
        if ue['semestre'].pk != semestre.pk:
            raise ErreurLigne(f'UE {ue_code} rattachée à deux semestres différents.')

    if ecue_code.casefold() in ue['ecue']:
        raise ErreurLigne(
            f'ECUE {ecue_code} déjà rencontrée dans l’UE {ue_code} : ligne en doublon.',
        )

    credits_ecue = _entier(ligne.get('ECUE_CREDITS'), 'ECUE_CREDITS')
    if credits_ecue < 0:
        raise ErreurLigne('ECUE_CREDITS ne peut pas être négatif.')
    coefficient = _decimal(ligne.get('COEFFICIENT'), 'COEFFICIENT', defaut='1')
    if coefficient <= 0:
        raise ErreurLigne('COEFFICIENT doit être strictement positif.')
    volumes = {}
    for colonne in ('CM', 'TD', 'TP'):
        volume = _decimal(ligne.get(colonne), colonne)
        if volume < 0:
            raise ErreurLigne(f'{colonne} ne peut pas être négatif.')
        volumes[colonne.lower()] = volume

    module = None
    module_intitule = _texte(ligne.get('MODULE'))
    if module_intitule:
        module = RefModule.objects.filter(intitule__iexact=module_intitule).first()
        if module:
            compteurs['modules_lies'] += 1
        else:
            compteurs['modules_absents'].add(module_intitule)

    ue['ecue'][ecue_code.casefold()] = {
        'code': ecue_code, 'intitule': _texte(ligne.get('ECUE_INTITULE')),
        'credits': credits_ecue, 'coefficient': coefficient,
        'volume_cm': volumes['cm'], 'volume_td': volumes['td'], 'volume_tp': volumes['tp'],
        'ref_module': module,
    }
    compteurs['ecue'] += 1


def _maquette_cible(annee, formation, parcours, niveau):
    """Maquette existante à compléter, ou maquette verrouillée à signaler.

    Reprend la règle de la commande ``import_maquette`` : le dernier brouillon
    est complété ; une maquette validée/active/archivée est immuable.
    """
    dernieres = (
        Maquette.objects
        .filter(
            annee_academique=annee, ref_formation=formation,
            parcours=parcours, niveau=niveau,
        )
        .order_by('-version')
    )
    existante = dernieres.first()
    if existante is None:
        return None, False
    if existante.statut in Maquette.STATUTS_VERROUILLES:
        return existante, True
    return existante, False


def _resume_maquette(maquette):
    """Vue lisible d'une entrée du plan (pour la prévisualisation)."""
    existante = maquette['existante']
    return {
        'libelle': maquette['libelle'],
        'annee': maquette['annee'].libelle,
        'formation': maquette['formation'].intitule,
        'parcours': maquette['parcours'].intitule if maquette['parcours'] else None,
        'niveau': maquette['niveau'].code,
        'action': 'mise_a_jour' if existante else 'creation',
        'version': existante.version if existante else None,
        'verrouillee': maquette['verrouillee'],
        'nb_ue': len(maquette['ue']),
        'nb_ecue': sum(len(ue['ecue']) for ue in maquette['ue'].values()),
        'credits': sum(ue['credits'] or 0 for ue in maquette['ue'].values()),
    }


# ── Application (transactionnelle) ──────────────────────────────────────────
def appliquer(plan, utilisateur=None):
    """Écrit le plan d'import dans **une seule transaction**.

    Le plan ayant déjà été validé par :func:`analyser`, une erreur ici relève
    d'un conflit de concurrence : la transaction est annulée en bloc.
    """
    bilan = {
        'maquettes_creees': 0, 'maquettes_completees': 0,
        'ue_creees': 0, 'ue_mises_a_jour': 0,
        'ecue_creees': 0, 'ecue_mises_a_jour': 0,
        'maquettes': [],
    }
    with transaction.atomic():
        for maquette_plan in plan.values():
            existante = maquette_plan['existante']
            if existante is not None:
                maquette = existante
                maquette.libelle = maquette_plan['libelle'] or maquette.libelle
                maquette.save(update_fields=['libelle', 'updated_at'])
                bilan['maquettes_completees'] += 1
                action = MaquetteJournal.Action.MODIFICATION
            else:
                version = (
                    Maquette.objects
                    .filter(
                        annee_academique=maquette_plan['annee'],
                        ref_formation=maquette_plan['formation'],
                        parcours=maquette_plan['parcours'],
                        niveau=maquette_plan['niveau'],
                    )
                    .order_by('-version')
                    .values_list('version', flat=True)
                    .first() or 0
                ) + 1
                maquette = Maquette.objects.create(
                    annee_academique=maquette_plan['annee'],
                    ref_formation=maquette_plan['formation'],
                    parcours=maquette_plan['parcours'],
                    niveau=maquette_plan['niveau'],
                    version=version,
                    statut=Maquette.Statut.BROUILLON,
                    libelle=maquette_plan['libelle'],
                )
                bilan['maquettes_creees'] += 1
                action = MaquetteJournal.Action.CREATION

            MaquetteJournal.objects.create(
                maquette=maquette, action=action, utilisateur=utilisateur,
                detail={'origine': 'import_excel_csv'},
            )

            for ordre_ue, ue_plan in enumerate(maquette_plan['ue'].values(), start=1):
                ue, creee = UE.objects.update_or_create(
                    maquette=maquette,
                    code__iexact=ue_plan['code'],
                    defaults={
                        'code': ue_plan['code'],
                        'semestre': ue_plan['semestre'],
                        'intitule': ue_plan['intitule'],
                        'credits': ue_plan['credits'],
                        'caractere': ue_plan['caractere'],
                        'ordre': ordre_ue,
                    },
                )
                bilan['ue_creees' if creee else 'ue_mises_a_jour'] += 1

                for ordre_ecue, ecue_plan in enumerate(ue_plan['ecue'].values(), start=1):
                    _, creee = ECUE.objects.update_or_create(
                        ue=ue,
                        code__iexact=ecue_plan['code'],
                        defaults={
                            'code': ecue_plan['code'],
                            'intitule': ecue_plan['intitule'],
                            'credits': ecue_plan['credits'],
                            'coefficient': ecue_plan['coefficient'],
                            'volume_cm': ecue_plan['volume_cm'],
                            'volume_td': ecue_plan['volume_td'],
                            'volume_tp': ecue_plan['volume_tp'],
                            'ref_module': ecue_plan['ref_module'],
                            'ordre': ordre_ecue,
                        },
                    )
                    bilan['ecue_creees' if creee else 'ecue_mises_a_jour'] += 1

            bilan['maquettes'].append({
                'id': maquette.id,
                'libelle': str(maquette),
                'statut': maquette.statut,
                'action': action,
            })
    return bilan
