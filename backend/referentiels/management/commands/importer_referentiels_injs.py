"""Import idempotent des référentiels INJS depuis les cinq documents sources.

Le commandement ne fabrique aucune donnée : chaque bloc importé porte la
référence du document qui l'atteste et son degré de fiabilité. Une exécution
répétée met à jour sans créer de doublon (clés métier : code ou intitulé).

Blocs importés
--------------
1. `institutions.json` — écoles, mentions, natures de cursus, 8 filières,
   statuts de vague, types d'enseignement (documents « Formations et Modules
   INJS », « Vagues INJS 2026 », « Modéliser les volumes horaires »).
2. `modules_officiels.json` — nomenclature officielle des modules des
   maquettes ENSEPS, avec le semestre lorsqu'il est documenté (Éducation et
   Motricité) et sans semestre sinon (jamais inventé).
3. `lieux.json` — bâtiments et espaces de formation du document d'inventaire.
   L'inventaire est explicitement partiellement « modélisé » par sa source :
   il est donc importé en fiabilité MODELISE, jamais comme officiel.
4. `volumes_horaires.json` — répartition CM/TD/TP/stage du document de
   cadrage, déclarée par sa source comme **proposition** : importée en
   MODELISE et limitée aux quatre cursus INJS (les cycles « professorat » et
   « maître d'EPS » relèvent du corpus CPFAE, exclu du périmètre).
5. `nomenclatures_pedagogiques.json` — types d'évaluation (nomenclature du
   document « Refonte du Module Évaluations », fiabilité CADRAGE), types de
   décision (décisions officielles des jurys de délibération, OFFICIEL) et
   types d'espace sportif (catégories de l'inventaire des installations,
   MODELISE comme sa source). Voir les arbitrages dans le bloc `_meta`.

Usage
-----
    python manage.py importer_referentiels_injs --dry-run
    python manage.py importer_referentiels_injs
"""

import json
import re
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction

from formations.models import RefBatiment, RefFormation, RefSalle, RefSite
from referentiels.models import (
    RefEcole,
    RefFiliere,
    RefMention,
    RefModuleOfficiel,
    RefStatutVague,
    RefTypeCursus,
    RefTypeDecision,
    RefTypeEnseignement,
    RefTypeEspaceSportif,
    RefTypeEvaluation,
    RefVolumeHoraireFormation,
)

DONNEES = Path(__file__).resolve().parents[2] / 'data'

SOURCE_MODULES = 'Formations et Modules INJS'
SOURCE_LIEUX = "Liste des Bâtiments, salles et espaces de formation de l'INJS"
SOURCE_VOLUMES = 'Modéliser les volumes horaires (proposition)'

# Codes de la nomenclature recommandée par le document d'inventaire.
PREFIXES_CODES = {
    'AMPHI': 'AMP',
    'COURS': 'SC',
    'TD': 'TD',
    'TP': 'TP',
    'LABORATOIRE': 'LAB',
    'INFORMATIQUE': 'INF',
    'GYMNASE': 'GYM',
    'SPORT': 'SPORT',
    'REUNION': 'REU',
    'CONFERENCE': 'CONF',
    'SALLE': 'SAL',
}

# Correspondence document → cycle du référentiel (filière + diplôme).
CURSUS_INJS = {
    ('EM', 'LICENCE'): 'EM',
    ('EM', 'MASTER'): 'EM',
    ('ES', 'LICENCE'): 'ES',
    ('ES', 'MASTER'): 'ES',
    ('MS', 'LICENCE'): 'MS',
    ('MS', 'MASTER'): 'MS',
    ('APA', 'LICENCE'): 'APA',
    ('APA', 'MASTER'): 'APA',
}


class Command(BaseCommand):
    help = "Importe les référentiels INJS depuis les cinq documents sources (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help="Simule l'import : aucune écriture en base.",
        )
        parser.add_argument(
            '--sans-lieux', action='store_true',
            help="Ignore le bloc bâtiments / salles.",
        )
        parser.add_argument(
            '--sans-cycles', action='store_true',
            help="N'exige pas la création préalable des 8 cycles LMD documentés.",
        )

    # ── Utilitaires ────────────────────────────────────────────────────────
    def _upsert(self, modele, cle, valeurs):
        """Crée ou met à jour une ligne ; retourne (objet, cree)."""
        obj = modele.objects.filter(**cle).first()
        if obj is None:
            return modele(**cle, **valeurs), True
        for champ, valeur in valeurs.items():
            setattr(obj, champ, valeur)
        return obj, False

    def _compter(self, cree, mis_a_jour):
        return f'{cree} créé(s), {mis_a_jour} mis à jour'

    # ── Bloc 1 : institutions ─────────────────────────────────────────────
    def _importer_institutions(self):
        data = json.loads((DONNEES / 'institutions.json').read_text(encoding='utf-8'))
        bilan = {}
        cree = maj = 0
        ecoles = {}
        for item in data['ecoles']:
            obj, c = self._upsert(RefEcole, {'code': item['code']}, {
                'libelle': item['libelle'],
                'nom_complet': item.get('nom_complet', ''),
                'description': item.get('description', ''),
                'source_document': item.get('source_document', ''),
                'fiabilite': item.get('fiabilite', 'A_RENSEIGNER'),
            })
            obj.save()
            ecoles[item['code']] = obj
            cree += c
            maj += not c
        bilan['ecoles'] = self._compter(cree, maj)

        cree = maj = 0
        mentions = {}
        for item in data['mentions']:
            obj, c = self._upsert(RefMention, {'code': item['code']}, {
                'libelle': item['libelle'],
                'nom_complet': item.get('nom_complet', ''),
                'ecole': ecoles.get(item.get('ecole')),
                'source_document': item.get('source_document', ''),
                'fiabilite': item.get('fiabilite', 'A_RENSEIGNER'),
            })
            obj.save()
            mentions[item['code']] = obj
            cree += c
            maj += not c
        bilan['mentions'] = self._compter(cree, maj)

        cree = maj = 0
        cursus = {}
        for item in data['types_cursus']:
            obj, c = self._upsert(RefTypeCursus, {'code': item['code']}, {
                'libelle': item['libelle'],
                'description': item.get('description', ''),
                'source_document': item.get('source_document', ''),
                'fiabilite': item.get('fiabilite', 'A_RENSEIGNER'),
            })
            obj.save()
            cursus[item['code']] = obj
            cree += c
            maj += not c
        bilan['types_cursus'] = self._compter(cree, maj)

        cree = maj = 0
        filieres = {}
        for item in data['filieres']:
            obj, c = self._upsert(RefFiliere, {'code': item['code']}, {
                'libelle': item['libelle'],
                'code_dossier': item.get('code_dossier', ''),
                'description': item.get('description', ''),
                'ordre': item.get('ordre', 1),
                'ecole': ecoles[item['ecole']],
                'mention': mentions.get(item.get('mention')),
                'type_cursus': cursus.get(item.get('type_cursus')),
                'source_document': item.get('source_document', ''),
                'fiabilite': item.get('fiabilite', 'A_RENSEIGNER'),
            })
            obj.save()
            filieres[item['code']] = obj
            cree += c
            maj += not c
        bilan['filieres'] = self._compter(cree, maj)

        cree = maj = 0
        for item in data['statuts_vague']:
            obj, c = self._upsert(RefStatutVague, {'code': item['code']}, {
                'libelle': item['libelle'],
                'description': item.get('description', ''),
                'est_ouvert': item.get('est_ouvert', False),
                'source_document': item.get('source_document', ''),
                'fiabilite': item.get('fiabilite', 'A_RENSEIGNER'),
            })
            obj.save()
            cree += c
            maj += not c
        bilan['statuts_vague'] = self._compter(cree, maj)

        cree = maj = 0
        for item in data['types_enseignement']:
            obj, c = self._upsert(RefTypeEnseignement, {'code': item['code']}, {
                'libelle': item['libelle'],
                'description': item.get('description', ''),
                'abrege': item.get('abrege', ''),
                'est_stage': item.get('est_stage', False),
                'source_document': item.get('source_document', ''),
                'fiabilite': item.get('fiabilite', 'A_RENSEIGNER'),
            })
            obj.save()
            cree += c
            maj += not c
        bilan['types_enseignement'] = self._compter(cree, maj)

        # Rattachement des cycles déjà présents aux filières officielles.
        rattaches = 0
        for filiere in filieres.values():
            if not filiere.code_dossier:
                continue
            # Convergence : le code de dossier est la clé d'autorité, un
            # rattachement erroné d'une exécution précédente est corrigé.
            rattaches += RefFormation.objects.filter(
                filiere_code=filiere.code_dossier,
            ).exclude(filiere=filiere).update(filiere=filiere)
        bilan['formations_rattachees'] = f'{rattaches} cycle(s)'
        return bilan, filieres

    # ── Bloc 2 : modules officiels des maquettes ──────────────────────────
    def _cycle(self, filiere_code, diplome):
        """Cycle du référentiel correspondant à une filière et un diplôme.

        La réconciliation passe par le code de dossier (F01…F08) : c'est la clé
        posée par l'import A-4.5, jamais un rapprochement approximatif sur le
        libellé. Si le diplôme n'est pas documenté pour la filière (cas des
        quatre filières ENSEP), le cycle unique de la filière est retenu.
        """
        filiere = RefFiliere.objects.filter(code=filiere_code).first()
        qs = RefFormation.objects.all()
        if filiere and filiere.code_dossier:
            qs = qs.filter(filiere_code=filiere.code_dossier)
        elif filiere:
            qs = qs.filter(filiere=filiere)
        else:
            qs = qs.filter(filiere_code=filiere_code)
        if diplome:
            candidat = qs.filter(type_diplome=diplome).first()
            if candidat:
                return candidat
            prefixe = 'LICENCE' if diplome == 'LICENCE' else 'MASTER'
            return qs.filter(intitule__icontains=prefixe).first()
        return qs.first()

    def _importer_modules(self):
        data = json.loads((DONNEES / 'modules_officiels.json').read_text(encoding='utf-8'))
        bilan = {}
        total_cree = total_maj = 0
        manquants = []

        plan = [
            ('EM_LICENCE', 'EM', 'LICENCE', None),
            ('EM_MASTER', 'EM', 'MASTER', None),
            ('ES', 'ES', 'LICENCE', 'LICENCE'),
            ('ES', 'ES', 'MASTER', 'MASTER'),
            ('MS', 'MS', 'LICENCE', 'LICENCE'),
            ('MS', 'MS', 'MASTER', 'MASTER'),
            ('APA', 'APA', 'LICENCE', None),
            ('APA', 'APA', 'MASTER', 'MASTER'),
        ]
        for cle, filiere_code, diplome, sous_cle in plan:
            if cle not in data:
                continue
            bloc = data[cle]
            if sous_cle:
                # Le document distingue Licence et Master dans un même bloc.
                niveaux = [(sous_cle, bloc[sous_cle])]
            elif isinstance(bloc, dict):
                # Un bloc peut mêler les listes Licence et Master (cas APA) :
                # seules les clés du diplôme traité sont retenues.
                veut_master = diplome == 'MASTER'
                niveaux = [
                    (cle_niveau, liste)
                    for cle_niveau, liste in bloc.items()
                    if cle_niveau.startswith('M') == veut_master
                ]
            else:
                niveaux = [('', bloc)]
            cycle = self._cycle(filiere_code, diplome)
            if cycle is None:
                manquants.append(f'{filiere_code} {diplome}')
                continue
            cree = maj = 0
            for semestre, libelles in niveaux:
                # La localisation n'est retenue que si la source la documente :
                # semestre (S1…S10), plage de semestres (S1-S3) ou niveau
                # (M1/M2). Sinon elle reste vide — jamais inventée.
                libelle_localisation = str(semestre).strip()
                semestre_code = (
                    libelle_localisation
                    if re.fullmatch(r'S\d(-S\d)?', libelle_localisation)
                    or re.fullmatch(r'M[12]', libelle_localisation)
                    else ''
                )
                for ordre, libelle in enumerate(libelles, start=1):
                    obj, c = self._upsert(
                        RefModuleOfficiel,
                        {'formation': cycle, 'semestre': semestre_code, 'libelle': libelle},
                        {'filiere_code': filiere_code, 'ordre': ordre,
                         'source_document': SOURCE_MODULES, 'fiabilite': 'OFFICIEL'},
                    )
                    obj.save()
                    cree += c
                    maj += not c
            bilan[f'{filiere_code} {diplome}'] = self._compter(cree, maj)
            total_cree += cree
            total_maj += maj
        if manquants:
            bilan['cycles_absents'] = ', '.join(manquants)
        bilan['TOTAL'] = self._compter(total_cree, total_maj)
        return bilan

    # ── Étape préalable : les cycles LMD que documente la source ──────────
    #: Couples filière × diplôme attestés par le document « Formations et
    #: Modules INJS » : seules F01 à F04 ouvrent un cursus LMD. F05 à F08
    #: n'ont, dans la source, aucun cycle LMD — rien n'est créé pour elles.
    CYCLES_LMD = ('F01', 'F02', 'F03', 'F04')
    DIPLOMES_LMD = ('LICENCE', 'MASTER')

    def _creer_cycles_lmd(self):
        """Crée les cycles LMD manquants, sans inventer de crédits ni de durée.

        Sans cette étape, l'import ne serait pas reproductible : sur une base
        neuve, les modules officiels et les volumes horaires n'auraient aucun
        cycle auquel se rattacher. Les cycles déjà présents ne sont jamais
        modifiés (l'intitulé et les crédits peuvent avoir été affinés depuis).
        """
        bilan = {}
        cree = 0
        for diplome in self.DIPLOMES_LMD:
            for code_dossier in self.CYCLES_LMD:
                filiere = RefFiliere.objects.filter(code_dossier=code_dossier).first()
                if filiere is None:
                    bilan[f'{code_dossier} {diplome}'] = 'filière absente — ignoré'
                    continue
                existant = RefFormation.objects.filter(
                    filiere_code=code_dossier, type_diplome=diplome,
                ).first()
                if existant is not None:
                    bilan[f'{code_dossier} {diplome}'] = 'déjà présent'
                    continue
                intitule = f'{filiere.libelle.upper()} — {diplome}'
                if RefFormation.objects.filter(intitule=intitule).exists():
                    bilan[f'{code_dossier} {diplome}'] = 'intitulé déjà utilisé'
                    continue
                RefFormation.objects.create(
                    intitule=intitule,
                    actif=True,
                    perimetre=RefFormation.Perimetre.INJS,
                    filiere_code=code_dossier,
                    filiere=filiere,
                    type_diplome=diplome,
                    source=SOURCE_MODULES,
                )
                cree += 1
                bilan[f'{code_dossier} {diplome}'] = 'créé'
        bilan['TOTAL'] = f'{cree} cycle(s) créé(s)'
        return bilan

    # ── Bloc 3 : bâtiments et espaces ─────────────────────────────────────
    def _importer_lieux(self):
        data = json.loads((DONNEES / 'lieux.json').read_text(encoding='utf-8'))
        bilan = {}
        site_data = data['site']
        site, c = self._upsert(RefSite, {'nom': site_data['nom']}, {
            'actif': True,
            'source_document': site_data.get('source_document', ''),
            'fiabilite': site_data.get('fiabilite', 'A_RENSEIGNER'),
        })
        site.save()
        bilan['site'] = '1 créé' if c else '1 mis à jour'

        total_bat = total_salles = 0
        crees = majs = 0
        for bloc_bat in data['batiments']:
            batiment, c = self._upsert(
                RefBatiment, {'site': site, 'nom': bloc_bat['nom']},
                {'actif': True,
                 'source_document': bloc_bat.get('source_document', ''),
                 'fiabilite': bloc_bat.get('fiabilite', 'A_RENSEIGNER')},
            )
            batiment.save()
            total_bat += 1
            compteur_par_type = {}
            for espace in bloc_bat['espaces']:
                type_lieu = espace.get('type_lieu', 'SALLE')
                compteur_par_type[type_lieu] = compteur_par_type.get(type_lieu, 0) + 1
                prefixe = PREFIXES_CODES.get(type_lieu, 'SAL')
                code = f'{prefixe}-{compteur_par_type[type_lieu]:03d}'
                salle, cree = self._upsert(
                    RefSalle,
                    {'site': site, 'batiment': batiment, 'nom': espace['nom']},
                    {'code': code,
                     'type_lieu': type_lieu,
                     'capacite': espace.get('capacite'),
                     'source_document': SOURCE_LIEUX,
                     'fiabilite': 'MODELISE',
                     'actif': True},
                )
                salle.save()
                total_salles += 1
                crees += cree
                majs += not cree
        bilan['batiments'] = f'{total_bat} traité(s)'
        bilan['salles'] = f'{total_salles} traité(s) — {self._compter(crees, majs)}'
        return bilan

    # ── Bloc 4 : volumes horaires (proposition de la source) ──────────────
    def _importer_volumes(self):
        data = json.loads((DONNEES / 'volumes_horaires.json').read_text(encoding='utf-8'))
        perimetre = {
            '1. Éducation et Motricité — Licence': ('EM', 'LICENCE'),
            '2. Éducation et Motricité — Master': ('EM', 'MASTER'),
            '3. Activités Physiques Adaptées — Licence': ('APA', 'LICENCE'),
            '4. Activités Physiques Adaptées — Master': ('APA', 'MASTER'),
        }
        bilan = {}
        total_cree = total_maj = 0
        exclus = [cle for cle in data if cle not in perimetre]
        for cle, (filiere_code, diplome) in perimetre.items():
            modules = data.get(cle, [])
            cycle = self._cycle(filiere_code, diplome)
            if cycle is None:
                bilan[f'{filiere_code} {diplome}'] = 'cycle absent — ignoré'
                continue
            cree = maj = 0
            for module in modules:
                obj, c = self._upsert(
                    RefVolumeHoraireFormation,
                    {'formation': cycle, 'intitule_module': module['intitule']},
                    {'heures_cm': module.get('cm'), 'heures_td': module.get('td'),
                     'heures_tp': module.get('tp'), 'heures_stage': module.get('stage'),
                     'heures_total': module.get('total'),
                     'source_document': SOURCE_VOLUMES, 'fiabilite': 'MODELISE'},
                )
                obj.save()
                cree += c
                maj += not c
            bilan[f'{filiere_code} {diplome}'] = self._compter(cree, maj)
            total_cree += cree
            total_maj += maj
        if exclus:
            bilan['exclus_hors_perimetre'] = ', '.join(exclus)
        bilan['TOTAL'] = self._compter(total_cree, total_maj)
        return bilan

    # ── Bloc 5 : nomenclatures pédagogiques ───────────────────────────────
    def _importer_pedagogiques(self):
        """Types d'évaluation, de décision de jury et d'espace sportif.

        Chaque bloc du fichier porte sa propre source et sa propre
        fiabilité : elles sont recopiées sur chaque valeur, jamais
        homogénéisées (la nomenclature des évaluations relève du cadrage,
        celle des jurys est la nomenclature officielle en vigueur).
        """
        data = json.loads(
            (DONNEES / 'nomenclatures_pedagogiques.json').read_text(encoding='utf-8')
        )
        plan = (
            ('types_evaluation', RefTypeEvaluation),
            ('types_decision', RefTypeDecision),
            ('types_espace_sportif', RefTypeEspaceSportif),
        )
        bilan = {}
        for cle_bloc, modele in plan:
            bloc = data[cle_bloc]
            cree = maj = 0
            for item in bloc['valeurs']:
                obj, c = self._upsert(modele, {'code': item['code']}, {
                    'libelle': item['libelle'],
                    'description': item.get('description', ''),
                    'source_document': bloc.get('source_document', ''),
                    'fiabilite': bloc.get('fiabilite', 'A_RENSEIGNER'),
                })
                obj.save()
                cree += c
                maj += not c
            bilan[cle_bloc] = self._compter(cree, maj)
        return bilan

    # ── Orchestration ─────────────────────────────────────────────────────
    def handle(self, *args, **options):
        dry_run = options['dry_run']
        self.stdout.write(self.style.MIGRATE_HEADING(
            'Import des référentiels INJS — ' + ('SIMULATION (aucune écriture)' if dry_run else 'application réelle')
        ))

        with transaction.atomic():
            bilan_institutions, _ = self._importer_institutions()
            bilan_cycles = (
                {} if options['sans_cycles'] else self._creer_cycles_lmd()
            )
            bilan_modules = self._importer_modules()
            bilan_lieux = {} if options['sans_lieux'] else self._importer_lieux()
            bilan_volumes = self._importer_volumes()
            bilan_pedagogiques = self._importer_pedagogiques()

            if dry_run:
                transaction.set_rollback(True)

        for titre, bilan in (
            ('1. Institutions (écoles, mentions, filières, cursus)', bilan_institutions),
            ('2. Cycles LMD documentés', bilan_cycles),
            ('3. Modules officiels des maquettes', bilan_modules),
            ('4. Bâtiments et espaces de formation', bilan_lieux),
            ('5. Volumes horaires (proposition de la source)', bilan_volumes),
            ('6. Nomenclatures pédagogiques (évaluations, jurys, espaces sportifs)', bilan_pedagogiques),
        ):
            self.stdout.write(self.style.HTTP_INFO(f'\n{titre}'))
            for cle, valeur in bilan.items():
                self.stdout.write(f'  {cle:<22} {valeur}')

        self.stdout.write(self.style.SUCCESS(
            '\nImport terminé.' + (' Simulation annulée : base inchangée.' if dry_run else '')
        ))
