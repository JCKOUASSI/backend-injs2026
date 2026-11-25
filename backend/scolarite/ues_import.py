"""Import des UE/ECUE d'une maquette depuis un fichier Excel ou CSV.

Même contrat que l'import des référentiels : **analyse en deux temps**, aucune
écriture pendant l'aperçu, puis application du plan dans une transaction
unique. L'import est borné à *une* maquette : le fichier ne peut ni créer ni
modifier une maquette, seulement ses UE et leurs ECUE.

Colonnes (en-tête technique ou libellé humain) :

``SEMESTRE`` (numéro, ``S1`` ou libellé), ``UE_CODE``, ``UE_INTITULE``,
``UE_CREDITS``, ``UE_CARACTERE``, ``ECUE_CODE``, ``ECUE_INTITULE``,
``ECUE_CREDITS``, ``COEFFICIENT``, ``HEURES_CM``, ``HEURES_TD``, ``HEURES_TP``.

Une ligne = une ECUE ; répéter une même ``UE_CODE`` sur plusieurs lignes
regroupe les ECUE sous une seule UE. Une ligne sans ``ECUE_CODE`` crée (ou met
à jour) l'UE seule.
"""

from __future__ import annotations

import csv
import io
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction

from .maquettes_export import CONTENT_TYPES, EXTENSIONS
from .maquettes_import import (
    LIGNES_APERCU,
    TAILLE_MAX,
    FichierInvalide,
    _lignes_csv,
    _lignes_excel,
    _texte,
)
from .models import ECUE, UE

COLONNES = [
    'SEMESTRE', 'UE_CODE', 'UE_INTITULE', 'UE_CREDITS', 'UE_CARACTERE',
    'ECUE_CODE', 'ECUE_INTITULE', 'ECUE_CREDITS', 'COEFFICIENT',
    'HEURES_CM', 'HEURES_TD', 'HEURES_TP',
]
OBLIGATOIRES = ('UE_CODE', 'UE_INTITULE')

ALIAS = {
    'SEMESTRE': 'SEMESTRE', 'SEMESTRE_NUMERO': 'SEMESTRE',
    'UE': 'UE_CODE', 'UE_CODE': 'UE_CODE', 'CODE_UE': 'UE_CODE',
    'INTITULE_UE': 'UE_INTITULE', 'UE_INTITULE': 'UE_INTITULE', 'LIBELLE_UE': 'UE_INTITULE',
    'CREDITS_UE': 'UE_CREDITS', 'UE_CREDITS': 'UE_CREDITS',
    'CARACTERE': 'UE_CARACTERE', 'UE_CARACTERE': 'UE_CARACTERE',
    'ECUE': 'ECUE_CODE', 'ECUE_CODE': 'ECUE_CODE', 'CODE_ECUE': 'ECUE_CODE',
    'INTITULE_ECUE': 'ECUE_INTITULE', 'ECUE_INTITULE': 'ECUE_INTITULE',
    'LIBELLE_ECUE': 'ECUE_INTITULE',
    'CREDITS_ECUE': 'ECUE_CREDITS', 'ECUE_CREDITS': 'ECUE_CREDITS',
    'COEFFICIENT': 'COEFFICIENT', 'COEF': 'COEFFICIENT',
    'HEURES_CM': 'HEURES_CM', 'CM': 'HEURES_CM', 'VOLUME_CM': 'HEURES_CM',
    'HEURES_TD': 'HEURES_TD', 'TD': 'HEURES_TD', 'VOLUME_TD': 'HEURES_TD',
    'HEURES_TP': 'HEURES_TP', 'TP': 'HEURES_TP', 'VOLUME_TP': 'HEURES_TP',
}

EXEMPLE = [
    {
        'SEMESTRE': 'S1', 'UE_CODE': 'UE-STAT', 'UE_INTITULE': 'Statistiques appliquées',
        'UE_CREDITS': 6, 'UE_CARACTERE': 'OBLIGATOIRE',
        'ECUE_CODE': 'EC-STAT-1', 'ECUE_INTITULE': 'Statistiques descriptives',
        'ECUE_CREDITS': 3, 'COEFFICIENT': 1, 'HEURES_CM': 20, 'HEURES_TD': 10, 'HEURES_TP': 0,
    },
    {
        'SEMESTRE': 'S1', 'UE_CODE': 'UE-STAT', 'UE_INTITULE': 'Statistiques appliquées',
        'UE_CREDITS': 6, 'UE_CARACTERE': 'OBLIGATOIRE',
        'ECUE_CODE': 'EC-STAT-2', 'ECUE_INTITULE': 'Probabilités',
        'ECUE_CREDITS': 3, 'COEFFICIENT': 1, 'HEURES_CM': 20, 'HEURES_TD': 15, 'HEURES_TP': 0,
    },
]


def _normaliser(texte):
    return ' '.join(str(texte or '').replace('\u00a0', ' ').split()).upper()


def modele(fmt='csv'):
    """Fichier modèle (CSV ou XLSX) avec deux lignes d'exemple."""
    if fmt == 'csv':
        tampon = io.StringIO()
        redacteur = csv.DictWriter(tampon, fieldnames=COLONNES, delimiter=';', lineterminator='\r\n')
        redacteur.writeheader()
        redacteur.writerows(EXEMPLE)
        return tampon.getvalue().encode('utf-8-sig')

    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter

    classeur = Workbook()
    feuille = classeur.active
    feuille.title = 'UE et ECUE'
    feuille.append(COLONNES)
    for exemple in EXEMPLE:
        feuille.append([exemple.get(colonne, '') for colonne in COLONNES])
    for cellule in feuille[1]:
        cellule.font = Font(bold=True, color='FFFFFF')
        cellule.fill = PatternFill('solid', fgColor='1A68AC')
    for index, colonne in enumerate(COLONNES, start=1):
        feuille.column_dimensions[get_column_letter(index)].width = max(len(colonne) + 4, 12)
    infos = classeur.create_sheet('Informations')
    infos.append(('Objet', 'UE et ECUE de la maquette sélectionnée'))
    infos.append(('Clé de regroupement', 'UE_CODE : répéter la même valeur pour plusieurs ECUE'))
    infos.append(('Semestre', 'numéro (1), S1, ou libellé exact du semestre du niveau'))
    infos.append(('Formats', '.xlsx, .csv (UTF-8, séparateur ;)'))
    infos.column_dimensions['A'].width = 24
    infos.column_dimensions['B'].width = 80
    flux = io.BytesIO()
    classeur.save(flux)
    return flux.getvalue()


def lire(nom_fichier, contenu):
    """Lit le fichier et renvoie les lignes normalisées sur :data:`COLONNES`."""
    if not contenu:
        raise FichierInvalide('Le fichier est vide.')
    if len(contenu) > TAILLE_MAX:
        raise FichierInvalide(
            f'Fichier trop volumineux ({len(contenu) // 1024} Ko) : maximum '
            f'{TAILLE_MAX // (1024 * 1024)} Mo.',
        )
    extension = ('.' + nom_fichier.rsplit('.', 1)[-1].lower()) if '.' in nom_fichier else ''
    if extension not in ('.csv', '.xlsx'):
        raise FichierInvalide('Format non pris en charge : utilisez un fichier .xlsx ou .csv.')

    lignes = _lignes_csv(contenu) if extension == '.csv' else _lignes_excel(contenu)
    lignes = [ligne for ligne in lignes if any(_texte(valeur) for valeur in ligne.values())]
    if not lignes:
        raise FichierInvalide('Le fichier ne contient aucune ligne exploitable.')
    entetes = {cle for ligne in lignes for cle in ligne}
    if not any(ALIAS.get(entete) for entete in entetes):
        raise FichierInvalide(
            'Aucune colonne reconnue : téléchargez le modèle d’import pour obtenir '
            'la structure attendue (' + ', '.join(COLONNES) + ').',
        )
    normalisees = []
    for ligne in lignes:
        valeurs = {}
        for entete, valeur in ligne.items():
            champ = ALIAS.get(entete)
            if champ and _texte(valeur) != '':
                valeurs[champ] = _texte(valeur)
        normalisees.append(valeurs)
    return normalisees


def _entier(texte, libelle, erreurs, maximum=200):
    try:
        valeur = int(str(texte).replace(' ', ''))
    except (TypeError, ValueError):
        erreurs.append(f'{libelle} : nombre entier attendu (reçu « {texte} »).')
        return None
    if valeur < 0 or valeur > maximum:
        erreurs.append(f'{libelle} : valeur hors limites (0 à {maximum}).')
        return None
    return valeur


def _decimal(texte, libelle, erreurs):
    try:
        valeur = Decimal(str(texte).replace(',', '.').replace(' ', ''))
    except (InvalidOperation, TypeError, ValueError):
        erreurs.append(f'{libelle} : nombre attendu (reçu « {texte} »).')
        return None
    if valeur < 0 or valeur > 1000:
        erreurs.append(f'{libelle} : valeur hors limites (0 à 1000).')
        return None
    return valeur


def _semestre(maquette, texte):
    """Semestre du niveau de la maquette : ``1``, ``S1`` ou libellé."""
    normalise = _normaliser(texte).replace('SEMESTRE', '').strip()
    if normalise.startswith('S'):
        normalise = normalise[1:].strip()
    semestres = maquette.niveau.semestres.all() if maquette.niveau_id else []
    if normalise.isdigit():
        return next((s for s in semestres if s.numero == int(normalise)), None)
    return next((s for s in semestres if _normaliser(s.libelle) == _normaliser(texte)), None)


def analyser(maquette, lignes):
    """Analyse sans écrire : rapport détaillé + plan groupé par UE."""
    erreurs, avertissements, apercu = [], [], []
    groupes = {}
    ordre = []
    rejets = 0

    for index, ligne in enumerate(lignes, start=1):
        erreurs_ligne = []
        code = _texte(ligne.get('UE_CODE'))
        intitule = _texte(ligne.get('UE_INTITULE'))
        if not code:
            erreurs_ligne.append('UE_CODE obligatoire.')
        if not intitule:
            erreurs_ligne.append('UE_INTITULE obligatoire.')

        semestre = None
        if _texte(ligne.get('SEMESTRE')):
            semestre = _semestre(maquette, ligne['SEMESTRE'])
            if semestre is None:
                erreurs_ligne.append(
                    f'SEMESTRE : « {ligne["SEMESTRE"]} » introuvable pour le niveau '
                    f'{maquette.niveau}.',
                )

        credits_ue = (
            _entier(ligne['UE_CREDITS'], 'UE_CREDITS', erreurs_ligne, maximum=120)
            if _texte(ligne.get('UE_CREDITS')) else None
        )
        caractere = None
        if _texte(ligne.get('UE_CARACTERE')):
            voulu = _normaliser(ligne['UE_CARACTERE'])
            for valeur, libelle in UE.Caractere.choices:
                if _normaliser(valeur) == voulu or _normaliser(libelle) == voulu:
                    caractere = valeur
                    break
            if caractere is None:
                erreurs_ligne.append(
                    'UE_CARACTERE : valeur inconnue (attendu : '
                    + ', '.join(str(valeur) for valeur, _ in UE.Caractere.choices) + ').',
                )

        ecue_code = _texte(ligne.get('ECUE_CODE'))
        ecue_intitule = _texte(ligne.get('ECUE_INTITULE'))
        credits_ecue = coefficient = heures = None
        if ecue_code:
            if not ecue_intitule:
                erreurs_ligne.append('ECUE_INTITULE obligatoire dès qu’une ECUE_CODE est fournie.')
            credits_ecue = (
                _entier(ligne['ECUE_CREDITS'], 'ECUE_CREDITS', erreurs_ligne, maximum=120)
                if _texte(ligne.get('ECUE_CREDITS')) else None
            )
            coefficient = (
                _decimal(ligne['COEFFICIENT'], 'COEFFICIENT', erreurs_ligne)
                if _texte(ligne.get('COEFFICIENT')) else None
            )
            heures = {
                champ: _decimal(ligne[champ], champ, erreurs_ligne) if _texte(ligne.get(champ)) else None
                for champ in ('HEURES_CM', 'HEURES_TD', 'HEURES_TP')
            }

        if erreurs_ligne:
            rejets += 1
            for message in erreurs_ligne:
                erreurs.append({'ligne': index, 'message': message})
            if len(apercu) < LIGNES_APERCU:
                apercu.append({
                    'ligne': index, 'action': 'rejet',
                    'cle': code or f'ligne {index}',
                    'libelle': ecue_code or code or f'ligne {index}',
                    'erreurs': erreurs_ligne, 'avertissements': [],
                })
            continue

        cle = _normaliser(code)
        if cle not in groupes:
            groupes[cle] = {
                'code': code,
                'intitule': intitule,
                'semestre': semestre,
                'credits': credits_ue,
                'caractere': caractere,
                'ligne': index,
                'ecues': [],
            }
            ordre.append(cle)
        else:
            groupe = groupes[cle]
            if _normaliser(groupe['intitule']) != _normaliser(intitule):
                erreurs_ligne.append(
                    f'UE_CODE {code} réutilisé avec un intitulé différent '
                    f'(ligne {groupe["ligne"]} : « {groupe["intitule"]} »).',
                )
            if credits_ue is not None and groupe['credits'] is not None and credits_ue != groupe['credits']:
                erreurs_ligne.append(f'UE_CODE {code} : crédits différents selon les lignes.')
            if semestre is not None and groupe['semestre'] is not None and semestre.pk != groupe['semestre'].pk:
                erreurs_ligne.append(f'UE_CODE {code} : semestres différents selon les lignes.')

        if ecue_code:
            deja = next(
                (e for e in groupes[cle]['ecues'] if _normaliser(e['code']) == _normaliser(ecue_code)),
                None,
            )
            if deja:
                erreurs_ligne.append(
                    f'ECUE_CODE {ecue_code} en doublon sous {code} (déjà ligne {deja["ligne"]}).',
                )
            if not erreurs_ligne:
                groupes[cle]['ecues'].append({
                    'code': ecue_code,
                    'intitule': ecue_intitule,
                    'credits': credits_ecue,
                    'coefficient': coefficient,
                    'heures': heures,
                    'ligne': index,
                })

        if erreurs_ligne:
            rejets += 1
            for message in erreurs_ligne:
                erreurs.append({'ligne': index, 'message': message})
            if len(apercu) < LIGNES_APERCU:
                apercu.append({
                    'ligne': index, 'action': 'rejet', 'cle': code,
                    'libelle': ecue_code or code,
                    'erreurs': erreurs_ligne, 'avertissements': [],
                })
        elif len(apercu) < LIGNES_APERCU:
            apercu.append({
                'ligne': index, 'action': 'création', 'cle': code,
                'libelle': f'{code} — {ecue_code or "UE seule"}',
                'erreurs': [], 'avertissements': [],
            })

    # ── Plan : existence en base + cohérence des crédits ──────────────────
    plan = []
    creations, mises_a_jour = 0, 0

    for cle in ordre:
        groupe = groupes[cle]
        ue = maquette.unites_enseignement.filter(code__iexact=groupe['code']).first()
        if ue is None:
            if groupe['semestre'] is None:
                erreurs.append({
                    'ligne': groupe['ligne'],
                    'message': f'UE_CODE {groupe["code"]} : SEMESTRE obligatoire pour une nouvelle UE.',
                })
                rejets += 1
                continue
            ue = UE(
                maquette=maquette, semestre=groupe['semestre'], code=groupe['code'],
                intitule=groupe['intitule'], credits=groupe['credits'] or 0,
                caractere=groupe['caractere'] or UE.Caractere.OBLIGATOIRE,
                ordre=maquette.unites_enseignement.count() + creations + 1,
            )
            action = 'création'
            creations += 1
        else:
            ue.intitule = groupe['intitule'] or ue.intitule
            if groupe['credits'] is not None:
                ue.credits = groupe['credits']
            if groupe['caractere']:
                ue.caractere = groupe['caractere']
            if groupe['semestre'] is not None:
                ue.semestre = groupe['semestre']
            action = 'mise à jour'
            mises_a_jour += 1

        etapes_ecue = []
        existants = ue.ecues.count() if ue.pk else 0
        for rang, info in enumerate(groupe['ecues'], start=1):
            ecue = ue.ecues.filter(code__iexact=info['code']).first() if ue.pk else None
            if ecue is None:
                ecue = ECUE(
                    ue=ue, code=info['code'], intitule=info['intitule'],
                    credits=info['credits'] or 0, ordre=existants + rang,
                    statut=ECUE.Statut.BROUILLON,
                )
                action_ecue = 'création'
            else:
                action_ecue = 'mise à jour'
            ecue.intitule = info['intitule']
            if info['credits'] is not None:
                ecue.credits = info['credits']
            if info['coefficient'] is not None:
                ecue.coefficient = info['coefficient']
            for champ, valeur in (info['heures'] or {}).items():
                if valeur is not None:
                    setattr(ecue, 'volume_' + champ.rsplit('_', 1)[-1].lower(), valeur)
            etapes_ecue.append({
                'obj': ecue, 'action': action_ecue, 'ligne': info['ligne'], 'cle': info['code'],
            })

        plan.append({'ue': ue, 'action': action, 'cle': groupe['code'],
                     'ecues': etapes_ecue, 'ligne': groupe['ligne']})

    # ── Validation finale : la ligne n'est retenue que si l'objet est valide ─
    valide = []
    for etape in plan:
        motifs = []
        try:
            etape['ue'].full_clean()
        except ValidationError as erreur:
            for champ, messages in erreur.message_dict.items():
                prefixe = '' if champ == '__all__' else f'{champ} : '
                motifs.extend(prefixe + message for message in messages)
        for sous_etape in etape['ecues']:
            try:
                # Une ECUE d'une UE encore non enregistrée ne peut pas valider
                # sa clé étrangère : on l'exclut, elle sera écrite juste après.
                sous_etape['obj'].full_clean(
                    exclude=['ue'] if sous_etape['obj'].ue.pk is None else None,
                )
            except ValidationError as erreur:
                for champ, messages in erreur.message_dict.items():
                    prefixe = '' if champ == '__all__' else f'{champ} : '
                    motifs.extend(prefixe + message for message in messages)
        if motifs:
            rejets += 1
            if etape['action'] == 'création':
                creations -= 1
            else:
                mises_a_jour -= 1
            for message in motifs:
                erreurs.append({'ligne': etape['ligne'], 'message': f'{etape["cle"]} : {message}'})
            continue
        total = sum(sous['obj'].credits for sous in etape['ecues'])
        if etape['ecues'] and etape['ue'].credits and total != etape['ue'].credits:
            avertissements.append(
                f'{etape["cle"]} : {etape["ue"].credits} crédit(s) pour '
                f'{total} réparti(s) entre les ECUE.',
            )
        valide.append(etape)

    ecues_crees = sum(1 for etape in valide for sous in etape['ecues'] if sous['action'] == 'création')
    ecues_maj = sum(1 for etape in valide for sous in etape['ecues'] if sous['action'] != 'création')

    # Les actions affichées dans l'aperçu reflètent l'état réel (création/mise à jour).
    for ligne in apercu:
        for etape in valide:
            if etape['ligne'] == ligne['ligne']:
                ligne['action'] = 'création' if etape['action'] == 'création' else 'mise à jour'
        for etape in valide:
            for sous in etape['ecues']:
                if sous['ligne'] == ligne['ligne']:
                    ligne['action'] = sous['action']

    if rejets:
        avertissements.append(
            f'{rejets} ligne(s) en erreur : l’import sera refusé en bloc tant qu’elles '
            'ne sont pas corrigées.',
        )

    return {
        'importable': rejets == 0,
        'resume': {
            'lignes': len(lignes),
            'ues_creees': creations,
            'ues_mises_a_jour': mises_a_jour,
            'ecues_creees': ecues_crees,
            'ecues_mises_a_jour': ecues_maj,
            'rejets': rejets,
            'avertissements': len(avertissements),
        },
        'lignes': apercu,
        'erreurs': erreurs,
        'avertissements': avertissements,
        'objets': [
            {'ligne': etape['ligne'], 'action': etape['action'],
             'libelle': f'{etape["ue"].code} — {etape["ue"].intitule}'}
            for etape in valide
        ],
        'plan': valide,
    }


def appliquer(plan):
    """Écrit UE puis ECUE dans une transaction unique (tout ou rien)."""
    if not plan:
        raise FichierInvalide('Aucune ligne valide à importer.')
    ecrits = []
    with transaction.atomic():
        for etape in plan:
            ue = etape['ue']
            ue.save()
            ecrits.append({'id': ue.pk, 'type': 'UE', 'code': ue.code, 'action': etape['action']})
            for sous in etape['ecues']:
                ecue = sous['obj']
                ecue.ue = ue
                ecue.save()
                ecrits.append({
                    'id': ecue.pk, 'type': 'ECUE', 'code': ecue.code, 'action': sous['action'],
                })
    return ecrits


def rapport(analyse, ecrits=None, nom_fichier=''):
    """Rapport d'import renvoyé au frontend (aperçu ou application)."""
    donnees = {
        'fichier': nom_fichier,
        'importable': analyse['importable'],
        'resume': analyse['resume'],
        'lignes': analyse['lignes'],
        'erreurs': analyse['erreurs'],
        'avertissements': analyse['avertissements'],
        'objets': analyse['objets'],
    }
    if ecrits is not None:
        donnees['ecrits'] = ecrits
    return donnees


__all__ = [
    'COLONNES', 'CONTENT_TYPES', 'EXEMPLE', 'FichierInvalide', 'appliquer',
    'analyser', 'lire', 'modele', 'rapport',
]
