"""Moteur d'import Excel/CSV du module Référentiels (mission « Référentiels »).

Processus en **5 étapes**, imposé par le cahier des charges :

1. **Téléversement contrôlé** — extension, taille et contenu vérifiés ;
2. **Prévisualisation** — lignes/colonnes reconnues, colonnes manquantes,
   doublons détectés, et correspondance de colonnes proposée à l'utilisateur ;
3. **Validation** — rapport d'erreurs ligne par ligne (aucune écriture) ;
4. **Importation transactionnelle** — modes *ajouter* / *mettre à jour* /
   *les deux*, le tout dans une transaction atomique ;
5. **Rapport final** — durée, compteurs et fichier des anomalies.

L'analyse est **sans effet** (étapes 1 à 3 n'écrivent rien) : la base n'est
modifiée qu'à l'étape 4, et jamais partiellement.

Aucune donnée académique n'est inventée : une colonne absente du fichier
donne une valeur absente, signalée, jamais devinée.
"""

from collections import OrderedDict
from datetime import datetime

import openpyxl

# ── Étape 1 : contrôles du fichier ───────────────────────────────────────────
EXTENSIONS_AUTORISEES = {'xlsx', 'xls', 'csv'}
TAILLE_MAX_FICHIER = 10 * 1024 * 1024  # 10 Mio (aligné sur TAILLE_MAX_PIECE)
LIGNES_MAX = 5000
ESSAI_ENCODAGES = ('utf-8-sig', 'utf-8', 'cp1252', 'latin-1')


class ErreurImport(ValueError):
    """Fichier refusé : le message est affiché tel quel à l'utilisateur."""


def champ_identite(modele):
    """Champ servant d'identité métier : ``code`` s'il existe, sinon le libellé.

    Tous les référentiels n'ont pas de colonne « code » (Semestre porte
    « S1 », Niveau « L1 ») : la supposer provoquerait une erreur de champ
    inexistant au moment de la lecture des valeurs existantes.
    """
    noms = {f.name for f in modele._meta.concrete_fields}
    if 'code' in noms:
        return 'code'
    from .colonnes import champ_libelle

    return champ_libelle(modele) or 'libelle'


def normaliser_entete(valeur):
    """Clé comparable d'un en-tête : casse, accents et espaces neutralisés."""
    texte = ('' if valeur is None else str(valeur)).strip().lower()
    remplacement = {
        'é': 'e', 'è': 'e', 'ê': 'e', 'ë': 'e',
        'à': 'a', 'â': 'a', 'ä': 'a',
        'î': 'i', 'ï': 'i',
        'ô': 'o', 'ö': 'o',
        'ù': 'u', 'û': 'u', 'ü': 'u',
        'ç': 'c',
    }
    texte = ''.join(remplacement.get(c, c) for c in texte)
    return ' '.join(texte.replace('_', ' ').split())


def controler_fichier(fichier):
    """Étape 1 — valide l'extension et la taille. Lève :class:`ErreurImport`."""
    nom = (getattr(fichier, 'name', '') or '').lower()
    extension = nom.rsplit('.', 1)[-1] if '.' in nom else ''
    if extension not in EXTENSIONS_AUTORISEES:
        raise ErreurImport(
            "Fichier refusé : seuls les formats .xlsx, .xls et .csv sont acceptés."
        )
    taille = getattr(fichier, 'size', None)
    if taille is None:
        try:
            fichier.seek(0, 2)
            taille = fichier.tell()
        finally:
            fichier.seek(0)
    if taille == 0:
        raise ErreurImport('Fichier vide : aucune donnée à importer.')
    if taille > TAILLE_MAX_FICHIER:
        raise ErreurImport(
            f'Fichier trop volumineux ({taille // (1024 * 1024)} Mio) : '
            f'la taille maximale est de {TAILLE_MAX_FICHIER // (1024 * 1024)} Mio.'
        )
    return extension


# ── Lecture des tableurs ─────────────────────────────────────────────────────
def _lire_xlsx(fichier):
    classeur = openpyxl.load_workbook(fichier, read_only=True, data_only=True)
    feuille = classeur.active
    lignes = []
    for rangee in feuille.iter_rows(values_only=True):
        if rangee is None:
            continue
        if all(cellule is None or str(cellule).strip() == '' for cellule in rangee):
            continue
        lignes.append(list(rangee))
        if len(lignes) > LIGNES_MAX:
            break
    classeur.close()
    return lignes


def _lire_csv(fichier):
    import csv
    import io

    brut = fichier.read()
    if isinstance(brut, str):
        contenu = brut
    else:
        contenu = None
        for encodage in ESSAI_ENCODAGES:
            try:
                contenu = brut.decode(encodage)
                break
            except UnicodeDecodeError:
                continue
        if contenu is None:
            raise ErreurImport(
                'Encodage non reconnu : enregistrez le fichier en UTF-8.'
            )
    # Détection du séparateur : point-virgule (francophone) par défaut.
    premiere = contenu.splitlines()[0] if contenu.splitlines() else ''
    separateur = ';' if premiere.count(';') >= premiere.count(',') else ','
    lecteur = csv.reader(io.StringIO(contenu, newline=''), delimiter=separateur)
    return [liste for liste in lecteur if any(str(c).strip() for c in liste)][:LIGNES_MAX]


def lire_fichier(fichier, extension):
    """Retourne la matrice brute ``[en-têtes, ...lignes]``."""
    if extension in ('xlsx', 'xls'):
        return _lire_xlsx(fichier)
    return _lire_csv(fichier)


# ── Étape 2 : prévisualisation + correspondance ──────────────────────────────
def _correspondance_auto(entetes_fichier, champs_attendus):
    """Rapproche chaque champ attendu d'une colonne du fichier (sans décision hasardeuse)."""
    index_par_cle = OrderedDict()
    for position, valeur in enumerate(entetes_fichier):
        cle = normaliser_entete(valeur)
        if cle and cle not in index_par_cle:
            index_par_cle[cle] = position

    correspondance = OrderedDict()
    for champ in champs_attendus:
        cible = None
        for candidat in {champ['cle'], champ['libelle'], champ['cle'].replace('_', ' ')}:
            cle = normaliser_entete(candidat)
            if cle in index_par_cle:
                cible = index_par_cle[cle]
                break
        correspondance[champ['cle']] = cible
    return correspondance


def _detecter_doublons(lignes_brutes, index_colonnes):
    """Doublons internes au fichier, signalés avec leur numéro de ligne.

    Le contrôle porte sur les **clés naturelles** du référentiel (code et
    libellé) : un doublon de code est un doublon même si le libellé diffère.
    """
    if isinstance(index_colonnes, int) or index_colonnes is None:
        index_colonnes = [index_colonnes]

    doublons = []
    for index_colonne in index_colonnes:
        if index_colonne is None:
            continue
        vus = {}
        for position, rangee in enumerate(lignes_brutes):
            if index_colonne >= len(rangee):
                continue
            valeur = ('' if rangee[index_colonne] is None
                      else str(rangee[index_colonne]).strip())
            if not valeur:
                continue
            cle = normaliser_entete(valeur)
            if cle in vus:
                doublons.append({'ligne': position + 2, 'valeur': valeur,
                                 'premiere_ligne': vus[cle] + 2})
            else:
                vus[cle] = position
    return doublons


def previsualiser(*, fichier, extension, champs_importables,
                  correspondance=None, a_entete=True):
    """Étape 2 — analyse le fichier **sans rien écrire**.

    Retourne la prévisualisation : colonnes détectées, correspondance
    automatique, colonnes obligatoires manquantes, doublons, aperçu des
    premières lignes.
    """
    matrice = lire_fichier(fichier, extension)
    if not matrice:
        raise ErreurImport('Fichier illisible ou vide : aucune ligne détectée.')

    if a_entete:
        entetes = [('' if c is None else str(c)) for c in matrice[0]]
        lignes_brutes = matrice[1:]
    else:
        entetes = [f'colonne {i + 1}' for i in range(len(matrice[0]))]
        lignes_brutes = matrice

    if not lignes_brutes:
        raise ErreurImport(
            "Fichier sans donnée : seule la ligne d'en-tête est présente."
        )

    mapping = _correspondance_auto(entetes, champs_importables)
    if correspondance:
        # La correspondance choisie par l'utilisateur est prioritaire.
        for cle, position in correspondance.items():
            if cle in mapping:
                mapping[cle] = position

    obligatoires = [c for c in champs_importables if c['obligatoire']]
    manquantes = [
        {'cle': c['cle'], 'libelle': c['libelle']}
        for c in obligatoires if mapping.get(c['cle']) is None
    ]

    # Doublons détectés sur les clés d'identité du référentiel : le code
    # lorsqu'il existe, sinon le libellé (Semestre porte « S1 »).
    identites = [c['cle'] for c in champs_importables if c['cle'] in ('code', 'libelle')]
    if not identites:
        identites = [champs_importables[0]['cle']] if champs_importables else []
    index_nom = [mapping.get(cle) for cle in identites]

    return {
        'total_lignes': len(lignes_brutes),
        'entetes_fichier': entetes,
        'colonnes_reconnues': [
            {'cle': c['cle'], 'libelle': c['libelle'], 'colonne': mapping[c['cle']]}
            for c in champs_importables if mapping.get(c['cle']) is not None
        ],
        'colonnes_manquantes': manquantes,
        'correspondance': mapping,
        'doublons': _detecter_doublons(lignes_brutes, index_nom),
        'apercu': [
            [('' if c is None else str(c)) for c in rangee[:8]]
            for rangee in lignes_brutes[:10]
        ],
        '_lignes_brutes': lignes_brutes,
    }


# ── Étape 3 : validation ─────────────────────────────────────────────────────
def _convertir(valeur, champ):
    """Convertit une cellule selon le type Django du champ."""
    texte = ('' if valeur is None else str(valeur)).strip()
    type_champ = champ['type']
    if 'BooleanField' in type_champ:
        if texte == '':
            return None
        return texte.lower() in {'oui', 'o', 'true', '1', 'vrai', 'yes', 'y'}
    if 'IntegerField' in type_champ or 'DecimalField' in type_champ:
        if texte == '':
            return None
        try:
            return int(texte) if 'Integer' in type_champ else float(texte.replace(',', '.'))
        except ValueError:
            raise ValueError(f'« {texte} » n’est pas un nombre valide.')
    if 'DateField' in type_champ and texte:
        return texte
    return texte


def valider(*, previsualisation, modele, champ_libelle, correspondance=None,
            queryset=None, rattachement=None):
    """Étape 3 — rapport d'erreurs **ligne par ligne**, sans aucune écriture.

    Les clés étrangères sont **résolues** à ce stade : une référence
    inexistante ou ambiguë est signalée avec sa ligne et sa colonne, et
    aucune association hasardeuse n'est retenue.
    """
    from .relations import ResolveurRelations

    champs_importables = [
        c for c in previsualisation['_colonnes_importables']
    ] if '_colonnes_importables' in previsualisation else []
    mapping = dict(correspondance or previsualisation['correspondance'])
    par_cle = {c['cle']: c for c in champs_importables}
    lignes_brutes = previsualisation['_lignes_brutes']

    resolveur = ResolveurRelations(modele, queryset_lie=None, rattachement=rattachement)
    champs_lies = set(resolveur.champs_lies())

    existants = set()
    if queryset is not None:
        identite = champ_identite(queryset.model)
        existants = {normaliser_entete(v) for v in queryset.values_list(identite, flat=True)}
        if champ_libelle:
            existants |= {
                normaliser_entete(v) for v in queryset.values_list(champ_libelle, flat=True)
            }

    erreurs = []
    valides = []
    for position, rangee in enumerate(lignes_brutes):
        numero = position + 2
        if all(str(c or '').strip() == '' for c in rangee):
            erreurs.append({'ligne': numero, 'colonne': '', 'valeur': '',
                            'message': 'Ligne vide — ignorée.'})
            continue

        valeurs = {}
        objets_lies = {}
        anomalies = []
        for cle, index in mapping.items():
            if index is None or index >= len(rangee):
                continue
            champ = par_cle.get(cle)
            if champ is None:
                continue
            brut = rangee[index]

            # ── Clé étrangère : résolution par identifiant ou clé métier ──
            if cle in champs_lies:
                resolution = resolveur.resoudre(cle, brut, contexte=valeurs)
                if resolution.erreur:
                    anomalies.append({
                        'ligne': numero, 'colonne': champ['libelle'],
                        'champ': cle, 'valeur': str(brut),
                        'message': resolution.erreur, 'nature': 'relation',
                    })
                    continue
                if resolution.objet is not None:
                    objets_lies[cle] = resolution.objet
                    valeurs[cle] = resolution.objet.pk
                    continue
                if champ['obligatoire']:
                    anomalies.append({
                        'ligne': numero, 'colonne': champ['libelle'],
                        'valeur': '', 'message': 'Valeur obligatoire manquante.',
                    })
                continue

            try:
                valeurs[cle] = _convertir(brut, champ)
            except ValueError as exc:
                anomalies.append({'ligne': numero, 'colonne': champ['libelle'],
                                  'valeur': str(brut), 'message': str(exc)})
                continue
            if champ['obligatoire'] and (valeurs[cle] in (None, '')):
                anomalies.append({'ligne': numero, 'colonne': champ['libelle'],
                                  'valeur': '', 'message': 'Valeur obligatoire manquante.'})

        if anomalies:
            erreurs.extend(anomalies)
        else:
            cle_conflit = normaliser_entete(
                valeurs.get('code') if 'code' in valeurs else valeurs.get(champ_libelle) or ''
            )
            valeurs['_existe'] = cle_conflit in existants if cle_conflit else False
            valides.append({'ligne': numero, 'valeurs': valeurs, 'lies': objets_lies})

    # Les colonnes de rattachement attendues, pour que l'interface puisse
    # indiquer à l'utilisateur quelles références sont reconnues et par quoi.
    relations = resolveur.relations_attendues()
    compteur_relations = {r['cle']: 0 for r in relations}
    for erreur in erreurs:
        if erreur.get('nature') != 'relation':
            continue
        # La correspondance se fait sur la clé du champ : les libellés
        # affichés (« Ecole ») ne coïncident pas toujours avec le nom du champ.
        if erreur.get('champ') in compteur_relations:
            compteur_relations[erreur['champ']] += 1
    for relation in relations:
        relation['non_resolues'] = compteur_relations[relation['cle']]

    return {
        'total_lignes': len(lignes_brutes),
        'lignes_valides': len(valides),
        'lignes_en_erreur': len({e['ligne'] for e in erreurs}),
        'relations': relations,
        'erreurs': erreurs[:500],
        'apercu_valides': [
            {'ligne': v['ligne'], 'valeurs': v['valeurs']} for v in valides[:10]
        ],
        '_valides': valides,
        '_mapping': mapping,
    }


# ── Étape 4 : importation transactionnelle ───────────────────────────────────
MODES = ('ajouter', 'mettre_a_jour', 'les_deux')


def importer(*, validation, modele, champ_libelle, mode, utilisateur=None,
             queryset=None, slug='', journaliser=None):
    """Étape 4 — écrit **tout ou rien** au niveau du lot.

    Chaque ligne est traitée dans son propre **point de sauvegarde** : une
    ligne fautive est annulée seule, signalée dans le rapport, et n'invalide
    pas les lignes suivantes. Le lot reste atomique dans son ensemble.

    ``journaliser`` est une fonction ``(objet, action, detail)`` fournie par la
    vue : le moteur reste indépendant du modèle de journal.
    """
    from django.db import transaction

    if mode not in MODES:
        raise ValueError(f'Mode d’import inconnu : {mode}. Attendu : {", ".join(MODES)}.')

    valides = validation['_valides']
    debut = datetime.now()

    index = {}
    if queryset is not None:
        identite = champ_identite(modele)
        for objet in queryset:
            index[normaliser_entete(getattr(objet, identite, '') or '')] = objet
            if champ_libelle:
                index[normaliser_entete(getattr(objet, champ_libelle, '') or '')] = objet

    compteurs = {'crees': 0, 'mis_a_jour': 0, 'ignores': 0}
    # Les lignes rejetées dès la validation font partie du rapport final :
    # l'utilisateur doit retrouver dans le rapport d'import toutes les lignes
    # de son fichier qui n'ont pas été reprises, avec leur motif.
    anomalies = [
        dict(anomalie, phase='validation')
        for anomalie in (validation.get('erreurs') or [])
    ]
    lignes_rejetees = len({a.get('ligne') for a in anomalies if a.get('ligne')})

    def _traiter(entree):
        valeurs = {k: v for k, v in entree['valeurs'].items() if not k.startswith('_')}
        # Les objets liés ont été résolus à l'étape 3 : on rattache les
        # instances réelles, jamais une valeur brute non vérifiée.
        lies = entree.get('lies') or {}
        for cle, objet in lies.items():
            valeurs[cle] = objet
        cle = normaliser_entete(
            valeurs.get('code') if 'code' in valeurs else valeurs.get(champ_libelle) or ''
        )
        existant = index.get(cle) if cle else None

        if existant is not None:
            if mode == 'ajouter':
                compteurs['ignores'] += 1
                anomalies.append({
                    'ligne': entree['ligne'], 'colonne': '',
                    'valeur': valeurs.get(champ_libelle)
                    or (valeurs.get('code', '') if 'code' in valeurs else ''),
                    'message': 'Déjà présent — ignoré (mode « ajouter »).',
                })
                return
            modifie = False
            for nom, valeur in valeurs.items():
                if valeur in (None, '') or not hasattr(existant, nom):
                    continue
                if getattr(existant, nom) != valeur:
                    setattr(existant, nom, valeur)
                    modifie = True
            if modifie:
                existant.save(update_fields=None)
                if journaliser:
                    journaliser(existant, 'import_maj', valeurs)
                compteurs['mis_a_jour'] += 1
            else:
                compteurs['ignores'] += 1
            return

        if mode == 'mettre_a_jour':
            compteurs['ignores'] += 1
            anomalies.append({
                'ligne': entree['ligne'], 'colonne': '',
                'valeur': valeurs.get(champ_libelle)
                or (valeurs.get('code', '') if 'code' in valeurs else ''),
                'message': 'Absent du référentiel — ignoré (mode « mettre à jour »).',
            })
            return

        objet = modele(**valeurs)
        champs_absents = [
            c.name for c in modele._meta.concrete_fields if c.name not in valeurs
        ]
        objet.full_clean(exclude=champs_absents)
        objet.save()
        if journaliser:
            journaliser(objet, 'import_creation', valeurs)
        index[cle] = objet
        compteurs['crees'] += 1

    with transaction.atomic():
        for entree in valides:
            try:
                # Point de sauvegarde : isole la ligne en échec.
                with transaction.atomic():
                    _traiter(entree)
            except Exception as exc:
                message = str(exc) or exc.__class__.__name__
                if hasattr(exc, 'message_dict'):
                    message = ' ; '.join(
                        f'{k} : {", ".join(map(str, v))}' for k, v in exc.message_dict.items()
                    )
                valeurs = {k: v for k, v in entree['valeurs'].items()
                           if not k.startswith('_')}
                anomalies.append({
                    'ligne': entree['ligne'], 'colonne': '',
                    'valeur': valeurs.get(champ_libelle)
                    or (valeurs.get('code', '') if 'code' in valeurs else ''),
                    'message': message[:300],
                })

    duree = (datetime.now() - debut).total_seconds()
    return {
        'slug': slug,
        'mode': mode,
        'duree_secondes': round(duree, 3),
        'total_traite': len(valides),
        'lignes_rejetees': lignes_rejetees,
        **compteurs,
        'anomalies': anomalies[:500],
        'nb_anomalies': len(anomalies),
        'resume': (
            f"{compteurs['crees']} création(s), {compteurs['mis_a_jour']} mise(s) à jour, "
            f"{compteurs['ignores']} ignorée(s), {len(anomalies)} anomalie(s) "
            f"en {duree:.2f} s."
        ),
    }
