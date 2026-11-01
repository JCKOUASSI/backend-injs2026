"""Complète le référentiel LMD depuis le « RÉFÉRENTIEL COMPLET DU SYSTÈME LMD » (PDF).

Commande **idempotente** et **non destructive** : relançable sans doublon,
elle ne supprime rien et n'active aucune maquette.

Source de vérité
----------------
``dossier_trvx/RÉFÉRENTIEL COMPLET DU SYSTÈME LMD.pdf`` (document du projet,
1er novembre 2026), transcrit dans ``scolarite/data/complement_referentiel_lmd_pdf.json``.
Ce complément ne couvre que ce que le jeu de données du classeur officiel
(``referentiel_offre_formation.json``, consommé par
``configurer_referentiel_injs``) ne contient pas.

Prérequis (dans l'ordre) : ``init_referentiels_lmd``,
``importer_referentiels_injs`` puis ``configurer_referentiel_injs``.

Ce que la commande écrit
------------------------
* les niveaux de doctorat D1, D2, D3 et les semestres S11 à S16 (PDF §4–§5) ;
* les cycles (coquilles ``RefFormation``) Licence/Master des filières ENSEP
  F05–F08, sans maquette — leurs tableaux UE/ECUE ne sont pas publiés (PDF §12) ;
* un ``Parcours`` par cycle (16), code = sigle de la filière (PDF §6 : les
  8 spécialisations, déclinées en Licence et Master) ;
* les 8 UE / 10 ECUE de la maquette MS-S8 du PDF (§8.3) dans la maquette
  MS Master 1 existante — **reconstitution à confirmer par la DENSEPS** :
  le classeur officiel publié présente l'en-tête « Semestre 2 (M1/S8) » de MS
  sans aucune UE. La provenance est inscrite dans le commentaire de la maquette.

Ce qu'elle n'écrit jamais
-------------------------
* aucune maquette STASE ni doctorale (aucun contenu publié) ;
* aucun rattachement ``Maquette.parcours`` : ``configurer_referentiel_injs``
  recherche ses maquettes avec ``parcours__isnull=True`` — y toucher
  casserait son idempotence (doublons silencieux) ;
* aucun dédoublement des ECUE de sports de combat du S3, que le PDF compte
  double là où la base normalisée du classeur compte un intitulé combiné
  (écart documenté dans le jeu de données : 415 ECUE au PDF, 407 en base) ;
* aucune activation de maquette (décision institutionnelle).

Exemples
--------
    python manage.py completer_referentiel_lmd --dry-run
    python manage.py completer_referentiel_lmd
    python manage.py completer_referentiel_lmd --annee 2026-2027
"""

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from formations.models import RefFormation
from referentiels.models import RefFiliere
from scolarite.models import (
    ECUE,
    UE,
    AnneeAcademique,
    FamilleModule,
    Maquette,
    Niveau,
    Parcours,
    Semestre,
    TypeFormation,
)

DONNEES = Path(__file__).resolve().parents[2] / 'data' / 'complement_referentiel_lmd_pdf.json'

SOURCE_CYCLES = 'RÉFÉRENTIEL COMPLET DU SYSTÈME LMD (PDF, 01/11/2026) — §6/§12'
NOTE_MS_S8 = (
    "Semestre S8 complété depuis le « RÉFÉRENTIEL COMPLET DU SYSTÈME LMD » "
    "(PDF du 01/11/2026, §8.3) : absent du classeur officiel publié, "
    "à confirmer par la DENSEPS avant validation."
)


class Command(BaseCommand):
    help = ("Complète le référentiel LMD (doctorat, cycles ENSEP, parcours, "
            "maquette MS-S8) depuis le PDF de référence — idempotent.")

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help="Simule : aucune écriture en base.")
        parser.add_argument('--annee',
                            help="Année académique cible (défaut : l'année courante).")

    # ── Prérequis ────────────────────────────────────────────────────────────
    def _prerequis(self, annee):
        manquants = []
        codes_niveaux = set(Niveau.objects.values_list('code', flat=True))
        absents = {'L1', 'L2', 'L3', 'M1', 'M2'} - codes_niveaux
        if absents:
            manquants.append(f"niveaux {', '.join(sorted(absents))} "
                             "(lancer init_referentiels_lmd)")
        dossiers = set(RefFiliere.objects.exclude(code_dossier='')
                       .values_list('code_dossier', flat=True))
        absents = {f'F0{i}' for i in range(1, 9)} - dossiers
        if absents:
            manquants.append(f"filières {', '.join(sorted(absents))} "
                             "(lancer importer_referentiels_injs)")
        if not Maquette.objects.filter(annee_academique=annee).exists():
            manquants.append(f"aucune maquette pour {annee.libelle} "
                             "(lancer configurer_referentiel_injs)")
        if manquants:
            raise CommandError('Prérequis manquants : ' + ' ; '.join(manquants))

    # ── Blocs ────────────────────────────────────────────────────────────────
    def _doctorat(self, data, bilan):
        for spec in data['niveaux_doctorat']:
            niveau, cree = Niveau.objects.get_or_create(
                code=spec['code'],
                defaults={
                    'libelle': spec['libelle'],
                    'cycle': Niveau.Cycle.DOCTORAT,
                    'ordre': spec['ordre'],
                    'credits_requis': spec['credits_requis'],
                    'actif': True,
                },
            )
            bilan['niveaux'] += cree
            for numero in spec['semestres']:
                _, cree_s = Semestre.objects.get_or_create(
                    niveau=niveau, numero=numero,
                    defaults={'libelle': f'S{numero}', 'actif': True},
                )
                bilan['semestres'] += cree_s

    def _cycles_sans_maquette(self, data, bilan):
        spec = data['cycles_sans_maquette_publiee']
        for code_dossier in spec['codes_dossier']:
            filiere = RefFiliere.objects.filter(code_dossier=code_dossier).first()
            if filiere is None:
                continue
            for diplome in spec['diplomes']:
                existant = RefFormation.objects.filter(
                    filiere_code=code_dossier, type_diplome=diplome,
                ).first()
                if existant is not None:
                    if existant.filiere_id is None:
                        existant.filiere = filiere
                        existant.save(update_fields=['filiere'])
                    continue
                intitule = f'{filiere.libelle.upper()} — {diplome}'
                if RefFormation.objects.filter(intitule=intitule).exists():
                    bilan['cycles_ignores'].append(intitule)
                    continue
                RefFormation.objects.create(
                    intitule=intitule,
                    actif=True,
                    perimetre=RefFormation.Perimetre.INJS,
                    filiere_code=code_dossier,
                    filiere=filiere,
                    type_diplome=diplome,
                    source=SOURCE_CYCLES,
                )
                bilan['cycles'] += 1

    def _parcours(self, bilan):
        types = {}
        formations = (RefFormation.objects
                      .filter(filiere__isnull=False,
                              type_diplome__in=('LICENCE', 'MASTER'))
                      .select_related('filiere')
                      .order_by('filiere__code_dossier', 'type_diplome'))
        for formation in formations:
            type_formation = types.get(formation.type_diplome)
            if type_formation is None:
                type_formation, _ = TypeFormation.objects.get_or_create(
                    code=formation.type_diplome,
                    defaults={'libelle': formation.type_diplome.capitalize()},
                )
                types[formation.type_diplome] = type_formation
            parcours = Parcours.objects.filter(
                ref_formation=formation, code=formation.filiere.code,
            ).first()
            if parcours is None:
                Parcours.objects.create(
                    ref_formation=formation,
                    type_formation=type_formation,
                    code=formation.filiere.code,
                    intitule=formation.filiere.libelle,
                    actif=True,
                )
                bilan['parcours'] += 1
                continue
            a_jour = (
                parcours.intitule == formation.filiere.libelle
                and parcours.type_formation_id == type_formation.id
                and parcours.actif
            )
            if not a_jour:
                parcours.intitule = formation.filiere.libelle
                parcours.type_formation = type_formation
                parcours.actif = True
                parcours.save(update_fields=['intitule', 'type_formation', 'actif'])
                bilan['parcours_maj'] += 1

    def _ms_s8(self, data, annee, bilan):
        spec = data['ms_s8']
        formation = (RefFormation.objects
                     .filter(filiere__code=spec['filiere'], type_diplome='MASTER')
                     .first())
        if formation is None:
            raise CommandError('Cycle MS — MASTER introuvable '
                               '(lancer importer_referentiels_injs).')
        maquette = (Maquette.objects
                    .filter(annee_academique=annee, ref_formation=formation,
                            parcours__isnull=True, niveau__code='M1', version=1)
                    .first())
        if maquette is None:
            raise CommandError('Maquette MS Master 1 introuvable pour '
                               f'{annee.libelle} (lancer configurer_referentiel_injs).')
        if maquette.statut in Maquette.STATUTS_VERROUILLES:
            bilan['ms_s8'] = ('ignoré : maquette MS Master 1 verrouillée '
                               f'(statut {maquette.statut}) — cloner une version '
                               'pour y intégrer MS-S8')
            return
        semestre = Semestre.objects.filter(numero=spec['semestre_numero']).first()
        if semestre is None:
            raise CommandError('Semestre S8 absent (lancer init_referentiels_lmd).')

        familles = {f.code: f for f in FamilleModule.objects.all()}
        for rang, spec_ue in enumerate(spec['ues'], 1):
            famille = familles.get(spec_ue['famille_code'])
            if famille is None:
                raise CommandError(
                    f"Famille de modules absente : {spec_ue['famille_code']} "
                    '(lancer configurer_referentiel_injs).')
            code_ue = f"MS-S8-UE{rang:02d}"
            ue, cree = UE.objects.update_or_create(
                maquette=maquette, code=code_ue,
                defaults={
                    'semestre': semestre,
                    'intitule': spec_ue['intitule'],
                    'credits': spec_ue['credits'],
                    'ordre': rang,
                    'famille': famille,
                },
            )
            bilan['ue_creees' if cree else 'ue_maj'] += 1
            for rang_ecue, intitule in enumerate(spec_ue['ecues'], 1):
                _, cree_e = ECUE.objects.update_or_create(
                    ue=ue, code=f'{code_ue}-EC{rang_ecue:02d}',
                    defaults={'intitule': intitule, 'ordre': rang_ecue},
                )
                bilan['ecue_creees' if cree_e else 'ecue_maj'] += 1

        if 'RÉFÉRENTIEL COMPLET' not in (maquette.commentaire_validation or ''):
            commentaire = (maquette.commentaire_validation or '').strip()
            maquette.commentaire_validation = (
                f'{commentaire}\n{NOTE_MS_S8}'.strip()
            )
            maquette.save(update_fields=['commentaire_validation'])
        bilan['ms_s8'] = 'appliqué (maquette MS Master 1, statut BROUILLON conservé)'

    # ── Orchestration ────────────────────────────────────────────────────────
    def handle(self, *args, **options):
        data = json.loads(DONNEES.read_text(encoding='utf-8'))
        if options['annee']:
            annee = AnneeAcademique.objects.filter(libelle=options['annee']).first()
            if annee is None:
                raise CommandError(f"Année académique inconnue : {options['annee']}")
        else:
            annee = AnneeAcademique.courante_ou_none()
            if annee is None:
                raise CommandError('Aucune année académique courante '
                                   '(préciser --annee AAAA-AAAA).')

        dry_run = options['dry_run']
        self.stdout.write(self.style.MIGRATE_HEADING(
            'Complément LMD depuis le PDF de référence — '
            + ('SIMULATION (aucune écriture)' if dry_run else 'application réelle')
            + f' · année cible : {annee.libelle}'
        ))

        bilan = {'niveaux': 0, 'semestres': 0, 'cycles': 0, 'cycles_ignores': [],
                 'parcours': 0, 'parcours_maj': 0,
                 'ue_creees': 0, 'ue_maj': 0, 'ecue_creees': 0, 'ecue_maj': 0,
                 'ms_s8': ''}
        with transaction.atomic():
            self._prerequis(annee)
            self._doctorat(data, bilan)
            self._cycles_sans_maquette(data, bilan)
            self._parcours(bilan)
            self._ms_s8(data, annee, bilan)
            if dry_run:
                transaction.set_rollback(True)

        lignes = [
            ('Niveaux doctorat créés', bilan['niveaux']),
            ('Semestres doctorat créés', bilan['semestres']),
            ('Cycles ENSEP créés (coquilles)', bilan['cycles']),
            ('Parcours créés', bilan['parcours']),
            ('Parcours mis à jour', bilan['parcours_maj']),
            ('UE MS-S8 créées / mises à jour', f"{bilan['ue_creees']} / {bilan['ue_maj']}"),
            ('ECUE MS-S8 créées / mises à jour', f"{bilan['ecue_creees']} / {bilan['ecue_maj']}"),
            ('MS-S8', bilan['ms_s8']),
        ]
        for libelle, valeur in lignes:
            self.stdout.write(f'  {libelle:<38} {valeur}')
        for intitule in bilan['cycles_ignores']:
            self.stdout.write(self.style.WARNING(
                f'  Cycle ignoré (intitulé déjà utilisé) : {intitule}'))
        self.stdout.write(self.style.WARNING(
            '  Réserve : MS-S8 est une reconstitution du PDF, absente du '
            'classeur officiel publié — à confirmer par la DENSEPS.'))
        self.stdout.write(self.style.SUCCESS(
            'Complément terminé.' + (' Simulation annulée : base inchangée.' if dry_run else '')))
