"""Import Excel/CSV des référentiels — analyse en deux temps, puis écriture.

Le contrat est celui de l'écran : l'utilisateur choisit un fichier, l'API en
donne un **aperçu complet** (lignes valides, mises à jour, rejets, erreurs,
avertissements) sans rien écrire, puis un second appel applique le plan dans
**une seule transaction** — une seule ligne invalide annule tout.

Lecture des colonnes : l'en-tête peut être le nom technique (``NIVEAU_ID``,
``NIVEAU``) ou le libellé humain produit par l'export (``NIVEAU``,
``CREDITS_REQUIS``). Les clés étrangères acceptent l'identifiant numérique
**ou** le code/libellé (``L1``, ``Licence 1``) : un fichier réexporté depuis
l'application reste donc réimportable tel quel.

Aucune écriture silencieuse : un fichier portant au moins une erreur
bloquante est refusé en bloc (``importable: false``), et l'application
refuse de démarrer sur un plan non importable.
"""

from __future__ import annotations

import csv
import io
from datetime import datetime

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q

from .maquettes_import import (
    LIGNES_APERCU,
    TAILLE_MAX,
    FichierInvalide,
    _lignes_csv,
    _lignes_excel,
    _texte,
)
from .referentiels_export import libelle_champ

CHAMPS_IGNORES = {'id'}

#: Exemples proposés dans le fichier modèle, par ressource.
EXEMPLES = {
    # Les exemples portent volontairement des valeurs neuves (L9, S9, 2099…) :
    # réimporter le modèle tel quel ne doit jamais écraser une ligne réelle.
    'types-formation': [
        {'CODE': 'TYPE-EXEMPLE', 'LIBELLE': 'Type de formation (exemple)', 'ACTIF': 'OUI'},
    ],
    'niveaux': [
        {'CODE': 'L9', 'LIBELLE': 'Licence 9 (exemple)', 'CYCLE': 'LICENCE', 'ORDRE': 9,
         'CREDITS_REQUIS': 60, 'ACTIF': 'OUI'},
    ],
    'semestres': [
        {'NIVEAU': 'L9', 'NUMERO': 9, 'LIBELLE': 'Semestre 9 (exemple)', 'ACTIF': 'OUI'},
    ],
    'annees': [
        {'LIBELLE': '2099-2100', 'DATE_DEBUT': '2099-09-01', 'DATE_FIN': '2100-07-31',
         'COURANTE': 'NON', 'ACTIF': 'OUI'},
    ],
    'regimes': [
        {'CODE': 'REG-EXEMPLE', 'LIBELLE': 'Régime (exemple)', 'ACTIF': 'OUI'},
    ],
    'statuts-etudiant': [
        {'CODE': 'STATUT-EXEMPLE', 'LIBELLE': 'Statut (exemple)',
         'BLOQUE_INSCRIPTION': 'NON', 'ACTIF': 'OUI'},
    ],
}

VRAIS = {'1', 'OUI', 'O', 'TRUE', 'VRAI', 'YES', 'Y', 'X'}
FAUX = {'0', 'NON', 'N', 'FALSE', 'FAUX', 'NO', 'NØ'}

#: Champs servant à reconnaître une ligne existante (dans l'ordre de priorité).
CLES_NATURELLES = ('code', 'numero', 'libelle', 'intitule', 'nom')


class PlanInvalide(ValueError):
    """Plan refusé : le fichier contient au moins une erreur bloquante."""


def champs_importables(fields):
    """Champs écrivables (l'identifiant n'est jamais importé comme valeur)."""
    return [champ for champ in fields if champ not in CHAMPS_IGNORES]


def _entetes_acceptees(fields):
    """Table ``EN-TÊTE NORMALISÉ → champ`` (nom technique ou libellé humain)."""
    correspondance = {}
    for champ in fields:
        for entete in (champ, champ[:-3] if champ.endswith('_id') else champ, libelle_champ(champ)):
            correspondance[entete.upper()] = champ
    return correspondance


def _normaliser(texte):
    return ' '.join(str(texte or '').replace('\u00a0', ' ').split()).upper()


def modele(ressource, fields, fmt='csv'):
    """Fichier modèle (CSV ou XLSX) : en-têtes attendus + une ligne d'exemple."""
    colonnes = [libelle_champ(champ) for champ in champs_importables(fields)]
    exemples = EXEMPLES.get(ressource, [])
    if fmt == 'csv':
        tampon = io.StringIO()
        redacteur = csv.DictWriter(
            tampon, fieldnames=colonnes, delimiter=';', lineterminator='\r\n',
            extrasaction='ignore',
        )
        redacteur.writeheader()
        for exemple in exemples:
            redacteur.writerow(exemple)
        return tampon.getvalue().encode('utf-8-sig')

    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter

    classeur = Workbook()
    feuille = classeur.active
    feuille.title = 'Référentiel'
    feuille.append(colonnes)
    for exemple in exemples:
        feuille.append([exemple.get(colonne, '') for colonne in colonnes])
    for cellule in feuille[1]:
        cellule.font = Font(bold=True, color='FFFFFF')
        cellule.fill = PatternFill('solid', fgColor='1A68AC')
    for index, colonne in enumerate(colonnes, start=1):
        feuille.column_dimensions[get_column_letter(index)].width = max(len(colonne) + 4, 14)
    infos = classeur.create_sheet('Informations')
    infos.append(('Référentiel', ressource))
    infos.append(('Colonnes', ', '.join(colonnes)))
    infos.append(('Clés étrangères', 'indiquer l’identifiant, le code ou le libellé (ex. L1)'))
    infos.append(('Formats', '.xlsx, .csv (UTF-8, séparateur ;)'))
    infos.column_dimensions['A'].width = 22
    infos.column_dimensions['B'].width = 90
    flux = io.BytesIO()
    classeur.save(flux)
    return flux.getvalue()


def lire(ressource, fields, nom_fichier, contenu):
    """Lit un CSV/XLSX et renvoie les lignes brutes normalisées par en-tête."""
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
    lignes = [ligne for ligne in lignes if any(_texte(v) for v in ligne.values())]
    if not lignes:
        raise FichierInvalide('Le fichier ne contient aucune ligne exploitable.')

    correspondance = _entetes_acceptees(fields)
    entetes_fichier = list(lignes[0].keys())
    inconnues = [
        entete for entete in entetes_fichier
        if entete and entete not in correspondance and entete != 'ID'
    ]
    normalisees = []
    for ligne in lignes:
        valeurs = {}
        for entete, valeur in ligne.items():
            champ = correspondance.get(entete)
            if champ and _texte(valeur) != '':
                valeurs[champ] = valeur
        normalisees.append(valeurs)
    if not any(normalisees):
        raise FichierInvalide(
            'Aucune colonne reconnue : téléchargez le modèle d’import pour obtenir '
            'la structure attendue (colonnes : '
            + ', '.join(libelle_champ(c) for c in champs_importables(fields)[:8])
            + '…).',
        )
    return normalisees, inconnues


def _departager(valeur):
    return _normaliser(valeur)


def _resoudre_cle(champ, valeur, model):
    """Résout une clé étrangère par identifiant, code, libellé, nom ou intitulé."""
    relation = model._meta.get_field(champ).related_model
    texte = _texte(valeur)
    if texte == '':
        return None
    if texte.isdigit():
        return relation.objects.filter(pk=int(texte)).first()
    filtre = Q()
    for attribut in ('code', 'libelle', 'nom', 'intitule'):
        if any(field.name == attribut for field in relation._meta.concrete_fields):
            filtre |= Q(**{f'{attribut}__iexact': texte})
    if not filtre:
        return None
    return relation.objects.filter(filtre).first()


def _booleen(texte):
    normalise = _normaliser(texte)
    if normalise in VRAIS:
        return True
    if normalise in FAUX:
        return False
    raise ValueError('valeur booléenne attendue (OUI/NON).')


def _date(texte):
    texte = _texte(texte)
    for format_ in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y', '%Y/%m/%d'):
        try:
            return datetime.strptime(texte, format_).date()
        except ValueError:
            continue
    raise ValueError('date attendue au format AAAA-MM-JJ ou JJ/MM/AAAA.')


def _convertir(champ, valeur, model):
    """Convertit une valeur texte vers le type du champ, ou lève ``ValueError``."""
    field = model._meta.get_field(champ)
    texte = _texte(valeur)
    if texte == '':
        if field.null:
            return None
        raise ValueError('valeur obligatoire manquante.')
    if champ.endswith('_id'):
        lie = _resoudre_cle(champ, valeur, model)
        if lie is None:
            raise ValueError(
                f'« {texte} » ne correspond à aucun {libelle_champ(champ).lower()} existant.',
            )
        return lie.pk
    if field.get_internal_type() == 'BooleanField':
        return _booleen(texte)
    if field.get_internal_type() == 'DateField':
        return _date(texte)
    if field.get_internal_type() in ('IntegerField', 'PositiveSmallIntegerField', 'PositiveIntegerField',
                                     'SmallIntegerField', 'BigIntegerField'):
        try:
            return int(texte.replace(' ', '').replace(',', ''))
        except ValueError:
            raise ValueError(f'nombre entier attendu (reçu : « {texte} »).')
    if field.get_internal_type() == 'DecimalField':
        try:
            return float(texte.replace(',', '.').replace(' ', ''))
        except ValueError:
            raise ValueError(f'nombre attendu (reçu : « {texte} »).')
    if field.choices:
        for valeur_choix, libelle in field.choices:
            if _normaliser(valeur_choix) == _normaliser(texte) or _normaliser(libelle) == _normaliser(texte):
                return valeur_choix
        raise ValueError(
            f'valeur inconnue « {texte} » (attendu : '
            + ', '.join(str(choix) for choix, _ in field.choices) + ').',
        )
    return texte


def _cle_ligne(model, valeurs):
    """Clé naturelle d'une ligne, pour repérer une mise à jour."""
    for champ in CLES_NATURELLES:
        if champ in valeurs and _texte(valeurs[champ]) != '':
            if model._meta.object_name == 'Semestre' and champ == 'numero':
                niveau = _texte(valeurs.get('niveau_id'))
                return f'{niveau}|{valeurs[champ]}'
            return f'{champ}:{_normaliser(valeurs[champ])}'
    return None


def _candidats_existants(model, valeurs, pk):
    """Lignes existantes correspondant à la clé naturelle (0, 1 ou plusieurs)."""
    if pk is not None:
        return list(model.objects.filter(pk=pk)[:2])
    if hasattr(model, 'code') and valeurs.get('code'):
        return list(model.objects.filter(code__iexact=_texte(valeurs['code']))[:2])
    if model._meta.object_name == 'Semestre' and valeurs.get('niveau_id') and valeurs.get('numero'):
        try:
            return list(model.objects.filter(
                niveau_id=int(valeurs['niveau_id']), numero=int(valeurs['numero']),
            )[:2])
        except (TypeError, ValueError):
            return []
    for champ in ('libelle', 'intitule', 'nom'):
        if valeurs.get(champ) and any(field.name == champ for field in model._meta.concrete_fields):
            return list(model.objects.filter(**{f'{champ}__iexact': _texte(valeurs[champ])})[:2])
    return []


def analyser(ressource, model, fields, lignes, inconnues=()):
    """Analyse sans écrire : rapport complet + plan d'écriture."""
    importables = champs_importables(fields)
    erreurs, avertissements, apercu = [], [], []
    plan, vus = [], {}
    creations = mises_a_jour = rejets = 0

    for index, brute in enumerate(lignes, start=1):
        valeurs = {champ: valeur for champ, valeur in brute.items() if champ in importables}
        lignes_erreurs, lignes_avertissements = [], []

        pk = None
        identifiant = _texte(brute.get('id'))
        if identifiant:
            if identifiant.isdigit():
                pk = int(identifiant)
            else:
                lignes_erreurs.append(f'identifiant « {identifiant} » non numérique.')

        converties = {}
        for champ, valeur in valeurs.items():
            try:
                converties[champ] = _convertir(champ, valeur, model)
            except ValueError as erreur:
                lignes_erreurs.append(f'{libelle_champ(champ)} : {erreur}')
            except Exception as erreur:  # pragma: no cover - relation incohérente
                lignes_erreurs.append(f'{libelle_champ(champ)} : {erreur}')

        if identifiant and pk is not None and not model.objects.filter(pk=pk).exists():
            lignes_erreurs.append(f'identifiant {pk} introuvable : la ligne serait créée à tort.')

        cle = _cle_ligne(model, valeurs)
        if cle and cle in vus:
            lignes_erreurs.append(f'doublon dans le fichier (déjà ligne {vus[cle]}).')
        elif cle:
            vus[cle] = index

        existant = None
        if not lignes_erreurs:
            candidats = _candidats_existants(model, converties, pk)
            if len(candidats) > 1:
                lignes_erreurs.append(
                    'plusieurs lignes existantes correspondent à cette clé : '
                    'ajoutez la colonne ID pour lever l’ambiguïté.',
                )
            else:
                existant = candidats[0] if candidats else None
        action = 'mise à jour' if existant else 'création'

        obj = existant or model()
        for champ, valeur in converties.items():
            setattr(obj, champ, valeur)
        if not lignes_erreurs:
            # ``full_clean`` couvre champs obligatoires, choix, plages et unicité.
            try:
                obj.full_clean()
            except ValidationError as erreur:
                for champ, messages in erreur.message_dict.items():
                    prefixe = '' if champ == '__all__' else f'{libelle_champ(champ)} : '
                    for message in messages:
                        lignes_erreurs.append(prefixe + message)

        if action == 'mise à jour':
            lignes_avertissements.append('ligne existante mise à jour.')

        if lignes_erreurs:
            rejets += 1
            for message in lignes_erreurs:
                erreurs.append({'ligne': index, 'message': message})
        elif action == 'création':
            creations += 1
        else:
            mises_a_jour += 1

        if len(apercu) < LIGNES_APERCU:
            apercu.append({
                'ligne': index,
                'action': 'rejet' if lignes_erreurs else action,
                'cle': cle or f'ligne {index}',
                'libelle': _texte(valeurs.get('libelle') or valeurs.get('intitule')
                                  or valeurs.get('nom') or cle),
                'erreurs': lignes_erreurs,
                'avertissements': lignes_avertissements,
            })
        if not lignes_erreurs:
            plan.append({'obj': obj, 'action': action, 'ligne': index, 'cle': cle})

    if inconnues:
        avertissements.append(
            'Colonnes ignorées (non reconnues) : ' + ', '.join(inconnues) + '.',
        )
    if rejets:
        avertissements.append(
            f'{rejets} ligne(s) en erreur : l’import sera refusé en bloc tant qu’elles '
            'ne sont pas corrigées.',
        )

    resume = {
        'lignes': len(lignes),
        'creations': creations,
        'mises_a_jour': mises_a_jour,
        'rejets': rejets,
        'avertissements': len(avertissements),
    }
    return {
        'ressource': ressource,
        'importable': rejets == 0,
        'resume': resume,
        'lignes': apercu,
        'erreurs': erreurs,
        'avertissements': avertissements,
        'objets': [
            {'ligne': ligne['ligne'], 'action': ligne['action'], 'libelle': ligne['libelle']}
            for ligne in apercu
        ],
        'plan': plan,
    }


def appliquer(plan):
    """Applique le plan dans une transaction unique (tout ou rien)."""
    if not plan:
        raise PlanInvalide('Aucune ligne valide à importer.')
    ecrits = []
    with transaction.atomic():
        for etape in plan:
            obj = etape['obj']
            obj.save()
            ecrits.append({'id': obj.pk, 'action': etape['action']})
    return ecrits


def rapport(analyse, ecrits=None, nom_fichier=''):
    """Rapport renvoyé au frontend (aperçu ou import appliqué)."""
    donnees = {
        'fichier': nom_fichier,
        'ressource': analyse['ressource'],
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
    'EXEMPLES', 'FichierInvalide', 'PlanInvalide', 'analyser', 'appliquer',
    'champs_importables', 'lire', 'modele', 'rapport',
]