"""Import d'une maquette pédagogique LMD depuis un fichier Excel ou CSV.

Une ligne du fichier = un ECUE. Les UE sont déduites des colonnes UE_* et
regroupées automatiquement. La commande est transactionnelle : en cas d'erreur
sur une seule ligne, rien n'est écrit.

    python manage.py import_maquette --modele maquette.xlsx
    python manage.py import_maquette maquette.xlsx --dry-run
    python manage.py import_maquette maquette.xlsx --activer

Les référentiels LMD (années, niveaux, semestres) doivent exister au préalable :
lancer ``init_referentiels_lmd`` si ce n'est pas le cas. La commande ne crée
jamais de RefFormation ni de RefModule : elle se contente de s'y rattacher, afin
de ne pas polluer les référentiels opérationnels existants.
"""

import csv
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from formations.models import RefFormation, RefModule
from scolarite.models import (
    ECUE,
    UE,
    AnneeAcademique,
    Maquette,
    Niveau,
    Parcours,
    Semestre,
)

COLONNES = [
    'ANNEE',
    'FORMATION',
    'PARCOURS',
    'NIVEAU',
    'SEMESTRE',
    'UE_CODE',
    'UE_INTITULE',
    'UE_CREDITS',
    'UE_CARACTERE',
    'ECUE_CODE',
    'ECUE_INTITULE',
    'ECUE_CREDITS',
    'COEFFICIENT',
    'CM',
    'TD',
    'TP',
    'MODULE',
]

OBLIGATOIRES = [
    'ANNEE', 'FORMATION', 'NIVEAU', 'SEMESTRE',
    'UE_CODE', 'UE_INTITULE', 'ECUE_CODE', 'ECUE_INTITULE',
]

EXEMPLE = [
    {
        'ANNEE': '2026-2027',
        'FORMATION': 'FORMATION EN ADMINISTRATION DE BASE',
        'PARCOURS': '',
        'NIVEAU': 'L1',
        'SEMESTRE': 'S1',
        'UE_CODE': 'UE1',
        'UE_INTITULE': 'Fondamentaux du droit public',
        'UE_CREDITS': '9',
        'UE_CARACTERE': 'OBLIGATOIRE',
        'ECUE_CODE': 'UE1-1',
        'ECUE_INTITULE': 'Droit constitutionnel',
        'ECUE_CREDITS': '5',
        'COEFFICIENT': '2',
        'CM': '20',
        'TD': '10',
        'TP': '0',
        'MODULE': '',
    },
    {
        'ANNEE': '2026-2027',
        'FORMATION': 'FORMATION EN ADMINISTRATION DE BASE',
        'PARCOURS': '',
        'NIVEAU': 'L1',
        'SEMESTRE': 'S1',
        'UE_CODE': 'UE1',
        'UE_INTITULE': 'Fondamentaux du droit public',
        'UE_CREDITS': '9',
        'UE_CARACTERE': 'OBLIGATOIRE',
        'ECUE_CODE': 'UE1-2',
        'ECUE_INTITULE': 'Droit administratif',
        'ECUE_CREDITS': '4',
        'COEFFICIENT': '2',
        'CM': '20',
        'TD': '10',
        'TP': '0',
        'MODULE': '',
    },
]


class ErreurLigne(Exception):
    """Erreur métier rattachée à une ligne du fichier."""


def _texte(valeur):
    if valeur is None:
        return ''
    return str(valeur).strip()


def _entier(valeur, colonne, defaut=0):
    brut = _texte(valeur)
    if not brut:
        return defaut
    try:
        return int(float(brut.replace(',', '.')))
    except ValueError:
        raise ErreurLigne(f'{colonne} : « {brut} » n\'est pas un nombre entier.')


def _decimal(valeur, colonne, defaut='0'):
    brut = _texte(valeur)
    if not brut:
        return Decimal(defaut)
    try:
        return Decimal(brut.replace(',', '.'))
    except InvalidOperation:
        raise ErreurLigne(f'{colonne} : « {brut} » n\'est pas un nombre.')


def _numero_semestre(valeur):
    """Accepte « S1 », « 1 » ou « Semestre 1 » et retourne le numéro global."""
    brut = _texte(valeur).upper().replace('SEMESTRE', '').replace('S', '').strip()
    if not brut.isdigit():
        raise ErreurLigne(f'SEMESTRE : « {_texte(valeur)} » est illisible (attendu S1, S2…).')
    return int(brut)


def lire_lignes(chemin):
    """Retourne la liste des lignes du fichier sous forme de dictionnaires."""
    suffixe = chemin.suffix.lower()

    if suffixe == '.csv':
        with chemin.open(encoding='utf-8-sig', newline='') as fichier:
            return [dict(ligne) for ligne in csv.DictReader(fichier, delimiter=';')]

    if suffixe not in ('.xlsx', '.xlsm'):
        raise CommandError(f'Format non supporté : {suffixe}. Utiliser .xlsx ou .csv.')

    try:
        from openpyxl import load_workbook
    except ImportError:
        raise CommandError('openpyxl est requis pour lire un fichier Excel.')

    feuille = load_workbook(chemin, data_only=True).active
    iterateur = feuille.iter_rows(values_only=True)
    entetes = [_texte(cellule).upper() for cellule in next(iterateur, ())]
    lignes = []
    for valeurs in iterateur:
        if all(_texte(valeur) == '' for valeur in valeurs):
            continue
        lignes.append(dict(zip(entetes, valeurs)))
    return lignes


def ecrire_modele(chemin):
    """Génère un fichier modèle prérempli avec deux lignes d'exemple."""
    if chemin.suffix.lower() == '.csv':
        with chemin.open('w', encoding='utf-8-sig', newline='') as fichier:
            redacteur = csv.DictWriter(fichier, fieldnames=COLONNES, delimiter=';')
            redacteur.writeheader()
            redacteur.writerows(EXEMPLE)
        return

    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font
    except ImportError:
        raise CommandError('openpyxl est requis pour générer un modèle Excel.')

    classeur = Workbook()
    feuille = classeur.active
    feuille.title = 'Maquette'
    feuille.append(COLONNES)
    for cellule in feuille[1]:
        cellule.font = Font(bold=True)
    for exemple in EXEMPLE:
        feuille.append([exemple[colonne] for colonne in COLONNES])
    for index, colonne in enumerate(COLONNES, start=1):
        feuille.column_dimensions[feuille.cell(row=1, column=index).column_letter].width = max(len(colonne) + 4, 14)
    classeur.save(chemin)


class Command(BaseCommand):
    help = "Importe une maquette pédagogique LMD (UE et ECUE) depuis un fichier Excel ou CSV."

    def add_arguments(self, parser):
        parser.add_argument('fichier', nargs='?', help='Fichier .xlsx ou .csv à importer.')
        parser.add_argument(
            '--modele',
            metavar='CHEMIN',
            help='Génère un fichier modèle vierge à ce chemin, puis quitte.',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Analyse le fichier et affiche le résultat sans rien enregistrer.',
        )
        parser.add_argument(
            '--activer',
            action='store_true',
            help='Passe les maquettes importées au statut ACTIVE (sinon BROUILLON).',
        )
        parser.add_argument(
            '--version-maquette',
            type=int,
            default=None,
            help='Version de maquette à créer ou compléter (par défaut : nouvelle version).',
        )

    def handle(self, *args, **options):
        if options['modele']:
            chemin = Path(options['modele'])
            ecrire_modele(chemin)
            self.stdout.write(self.style.SUCCESS(f'Modèle écrit : {chemin}'))
            return

        if not options['fichier']:
            raise CommandError('Indiquer un fichier à importer, ou utiliser --modele.')

        chemin = Path(options['fichier'])
        if not chemin.exists():
            raise CommandError(f'Fichier introuvable : {chemin}')

        lignes = lire_lignes(chemin)
        if not lignes:
            raise CommandError('Le fichier ne contient aucune ligne exploitable.')

        manquantes = [colonne for colonne in OBLIGATOIRES if colonne not in lignes[0]]
        if manquantes:
            raise CommandError('Colonnes obligatoires absentes : ' + ', '.join(manquantes))

        try:
            with transaction.atomic():
                resume = self._importer(lignes, options)
                if options['dry_run']:
                    self._afficher(resume, simule=True)
                    raise _Annulation()
        except _Annulation:
            return

        # Lot L1 (R4) : l'activation est différée — les maquettes sont créées
        # en BROUILLON puis passées ACTIVE une fois UE/ECUE en place, car une
        # maquette validée/active est immuable.
        if options['activer']:
            for maquette in resume['maquettes']:
                maquette.statut = Maquette.Statut.ACTIVE
                maquette.save()

        self._afficher(resume, simule=False)

    def _importer(self, lignes, options):
        maquettes = {}
        ues = {}
        erreurs = []
        compteurs = {'ue': 0, 'ecue': 0, 'modules_lies': 0, 'modules_absents': set()}

        for index, ligne in enumerate(lignes, start=2):
            try:
                self._traiter_ligne(ligne, maquettes, ues, compteurs, options)
            except ErreurLigne as erreur:
                erreurs.append(f'Ligne {index} : {erreur}')

        if erreurs:
            raise CommandError('Import annulé.\n  ' + '\n  '.join(erreurs))

        return {'maquettes': list(maquettes.values()), 'compteurs': compteurs}

    def _traiter_ligne(self, ligne, maquettes, ues, compteurs, options):
        annee_libelle = _texte(ligne.get('ANNEE'))
        formation_intitule = _texte(ligne.get('FORMATION'))
        parcours_code = _texte(ligne.get('PARCOURS'))
        niveau_code = _texte(ligne.get('NIVEAU')).upper()

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

        cle_maquette = (annee.pk, formation.pk, parcours.pk if parcours else None, niveau.pk)
        maquette = maquettes.get(cle_maquette)
        if maquette is None:
            maquette = self._maquette(annee, formation, parcours, niveau, options)
            maquettes[cle_maquette] = maquette

        ue_code = _texte(ligne.get('UE_CODE'))
        cle_ue = (cle_maquette, ue_code.lower())
        ue = ues.get(cle_ue)
        if ue is None:
            caractere = _texte(ligne.get('UE_CARACTERE')).upper() or UE.Caractere.OBLIGATOIRE
            if caractere not in UE.Caractere.values:
                raise ErreurLigne(
                    f'UE_CARACTERE « {caractere} » invalide '
                    f'(attendu : {", ".join(UE.Caractere.values)}).'
                )
            ue, cree = UE.objects.update_or_create(
                maquette=maquette,
                code__iexact=ue_code,
                defaults={
                    'code': ue_code,
                    'semestre': semestre,
                    'intitule': _texte(ligne.get('UE_INTITULE')),
                    'credits': _entier(ligne.get('UE_CREDITS'), 'UE_CREDITS'),
                    'caractere': caractere,
                    'ordre': len([c for c in ues if c[0] == cle_maquette]) + 1,
                },
            )
            ues[cle_ue] = ue
            if cree:
                compteurs['ue'] += 1

        module = None
        module_intitule = _texte(ligne.get('MODULE'))
        if module_intitule:
            module = RefModule.objects.filter(intitule__iexact=module_intitule).first()
            if module:
                compteurs['modules_lies'] += 1
            else:
                compteurs['modules_absents'].add(module_intitule)

        ecue_code = _texte(ligne.get('ECUE_CODE'))
        _, cree = ECUE.objects.update_or_create(
            ue=ue,
            code__iexact=ecue_code,
            defaults={
                'code': ecue_code,
                'intitule': _texte(ligne.get('ECUE_INTITULE')),
                'credits': _entier(ligne.get('ECUE_CREDITS'), 'ECUE_CREDITS'),
                'coefficient': _decimal(ligne.get('COEFFICIENT'), 'COEFFICIENT', defaut='1'),
                'volume_cm': _decimal(ligne.get('CM'), 'CM'),
                'volume_td': _decimal(ligne.get('TD'), 'TD'),
                'volume_tp': _decimal(ligne.get('TP'), 'TP'),
                'ref_module': module,
                'ordre': ue.ecues.count() + 1,
            },
        )
        if cree:
            compteurs['ecue'] += 1

    def _maquette(self, annee, formation, parcours, niveau, options):
        filtre = {
            'annee_academique': annee,
            'ref_formation': formation,
            'parcours': parcours,
            'niveau': niveau,
        }

        if options['version_maquette'] is not None:
            version = options['version_maquette']
        else:
            derniere = (
                Maquette.objects.filter(**filtre)
                .order_by('-version').values_list('version', flat=True).first()
            )
            version = (derniere or 0) + 1

        # Lot L1 (R4) : une maquette validée/active/archivée est immuable —
        # le réimport est refusé ; il faut créer une nouvelle version.
        existante = Maquette.objects.filter(**filtre, version=version).first()
        if existante is not None:
            if existante.statut in Maquette.STATUTS_VERROUILLES:
                raise CommandError(
                    f'Maquette {existante} verrouillée ({existante.statut}) : réimport refusé. '
                    'Utilisez --version pour créer une nouvelle version.'
                )
            existante.libelle = f'{formation.intitule} – {niveau.code}'
            existante.save()
            return existante

        # L'import crée toujours en BROUILLON : l'activation éventuelle
        # (--activer) est appliquée après création des UE/ECUE (cf. handle).
        return Maquette.objects.create(
            **filtre,
            version=version,
            statut=Maquette.Statut.BROUILLON,
            libelle=f'{formation.intitule} – {niveau.code}',
        )

    def _afficher(self, resume, simule):
        entete = 'Simulation (aucune écriture)' if simule else 'Import terminé'
        self.stdout.write(self.style.MIGRATE_HEADING(entete))

        for maquette in resume['maquettes']:
            self.stdout.write(f'  • {maquette} [{maquette.get_statut_display()}]')

        compteurs = resume['compteurs']
        self.stdout.write(
            f"  {compteurs['ue']} UE et {compteurs['ecue']} ECUE créés, "
            f"{compteurs['modules_lies']} rattachements à un module opérationnel."
        )

        absents = compteurs['modules_absents']
        if absents:
            self.stdout.write(self.style.WARNING(
                f'  {len(absents)} module(s) du fichier absent(s) du référentiel, '
                'ECUE créés sans rattachement :'
            ))
            for intitule in sorted(absents):
                self.stdout.write(f'    - {intitule}')

        if not simule:
            self.stdout.write(self.style.SUCCESS('  Les inscriptions pédagogiques peuvent être générées.'))


class _Annulation(Exception):
    """Sentinelle interne pour annuler la transaction en mode --dry-run."""
