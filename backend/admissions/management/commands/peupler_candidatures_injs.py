"""Couverture massive des candidatures INJS (année académique courante).

Complète ``seed_candidatures_demo`` (scénarios officiels) par un jeu
systématique : **chaque formation active × chaque niveau cohérent avec
son diplôme × chacun des 12 statuts** du workflow, à raison de
``--par-combo`` dossiers par case (2 par défaut, soit 960 dossiers).

- Autant d'étudiants fictifs que de dossiers : un candidat distinct par
  dossier, **parité hommes/femmes exacte** (alternance déterministe).
- Toutes les zones de la fiche du module « Candidatures » sont remplies :
  identité complète du candidat (nom, prénoms, sexe, naissance,
  nationalité, contacts, adresse), formation, parcours, niveau, type de
  candidature, voie d'accès, régime, vague, date de dépôt, score pour
  les dossiers en étude/décidés, observations, et pièces justificatives
  au profil cohérent avec le statut (déposées, vérifiées, refusées ou
  manquantes selon l'avancement).
- Tout passe par les services métier (``services.creer_candidature``,
  ``deposer_piece``, ``verifier_piece``, ``workflow.appliquer_transition``)
  : dossiers journalisés, transitions légales uniquement.
- Cohérence LMD : Licence → L1-L3, Master → M1-M2 (l'offre INJS ne
  comporte pas de formation doctorale en base ; aucune candidature
  n'est créée sur un niveau sans formation correspondante).

Idempotent (candidat identifié par un email déterministe ``@exemple.ci``)
et réversible par ``--purger`` (marqueur « [Exemple] Couverture INJS »).
"""
import re
import unicodedata
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from admissions import services, workflow
from admissions.models import (
    Candidat, Candidature, PieceCandidature, TypeCandidature, VoieAcces,
)
from formations.models import RefFormation, RefVague
from scolarite.models import (
    AnneeAcademique, Niveau, Parcours, RegimeEtudes,
)

User = get_user_model()
MARQUEUR = '[Exemple] Couverture INJS'
S = Candidature.Statut

# Chemins de transitions légaux depuis BROUILLON (machine à états officielle).
CHEMINS = {
    S.BROUILLON: [],
    S.SOUMISE: [S.SOUMISE],
    S.EN_ATTENTE_DE_VERIFICATION: [S.SOUMISE, S.EN_ATTENTE_DE_VERIFICATION],
    S.PIECES_INCOMPLETES: [
        S.SOUMISE, S.EN_ATTENTE_DE_VERIFICATION, S.PIECES_INCOMPLETES,
    ],
    S.PIECES_VALIDEES: [
        S.SOUMISE, S.EN_ATTENTE_DE_VERIFICATION, S.PIECES_VALIDEES,
    ],
    S.EN_ETUDE: [
        S.SOUMISE, S.EN_ATTENTE_DE_VERIFICATION, S.PIECES_VALIDEES, S.EN_ETUDE,
    ],
    S.ADMISSIBLE: [
        S.SOUMISE, S.EN_ATTENTE_DE_VERIFICATION, S.PIECES_VALIDEES,
        S.EN_ETUDE, S.ADMISSIBLE,
    ],
    S.ADMIS: [
        S.SOUMISE, S.EN_ATTENTE_DE_VERIFICATION, S.PIECES_VALIDEES,
        S.EN_ETUDE, S.ADMISSIBLE, S.ADMIS,
    ],
    S.ADMIS_SOUS_RESERVE: [
        S.SOUMISE, S.EN_ATTENTE_DE_VERIFICATION, S.PIECES_VALIDEES,
        S.EN_ETUDE, S.ADMISSIBLE, S.ADMIS_SOUS_RESERVE,
    ],
    S.LISTE_ATTENTE: [
        S.SOUMISE, S.EN_ATTENTE_DE_VERIFICATION, S.PIECES_VALIDEES,
        S.EN_ETUDE, S.LISTE_ATTENTE,
    ],
    S.REFUSE: [
        S.SOUMISE, S.EN_ATTENTE_DE_VERIFICATION, S.PIECES_VALIDEES,
        S.EN_ETUDE, S.REFUSE,
    ],
    S.ANNULE: [S.ANNULE],
}

# Profil de remplissage des pièces selon le statut visé.
PROFILS = {
    S.BROUILLON: 'vides',
    S.SOUMISE: 'deposees',
    S.EN_ATTENTE_DE_VERIFICATION: 'deposees',
    S.PIECES_INCOMPLETES: 'partiel',
    S.PIECES_VALIDEES: 'complet',
    S.EN_ETUDE: 'complet',
    S.ADMISSIBLE: 'complet',
    S.ADMIS: 'complet',
    S.ADMIS_SOUS_RESERVE: 'complet',
    S.LISTE_ATTENTE: 'complet',
    S.REFUSE: 'complet',
    S.ANNULE: 'partiel',
}

STATUTS_AVEC_SCORE = {
    S.EN_ETUDE, S.ADMISSIBLE, S.ADMIS, S.ADMIS_SOUS_RESERVE,
    S.LISTE_ATTENTE, S.REFUSE,
}

NIVEAUX_PAR_DIPLOME = {
    'LICENCE': ['L1', 'L2', 'L3'],
    'MASTER': ['M1', 'M2'],
}
ANNEE_NAISSANCE_BASE = {'L1': 2007, 'L2': 2006, 'L3': 2005, 'M1': 2003, 'M2': 2002}

NOMS = [
    'Kouassi', 'Koné', 'Touré', 'Diabaté', 'Coulibaly', 'Traoré', 'Cissé',
    'Fofana', 'Bamba', 'Sangaré', 'Yao', "N'Guessan", 'Koffi', 'Brou',
    'Gnahoré', 'Diby', 'Kra', 'Assalé', 'Yoboué', 'Séri', 'Ouattara',
    'Bakayoko', 'Kouadio', 'Konan', 'Diallo', 'Camara', 'Sylla', 'Doumbia',
    'Keïta', 'Savané', 'Sanogo', 'Soro', 'Silué', 'Diomandé', 'Kamagate',
    'Aka', 'Kacou', 'Zadi', 'Tano', 'Ehouman',
]
PRENOMS_F = [
    'Adjoua', 'Fatou', 'Mariam', 'Aya', 'Akissi', 'Nadia', 'Grâce',
    'Esther', 'Rebecca', 'Sandrine', 'Larissa', 'Aïcha', 'Fatoumata',
    'Aminata', 'Salimata', 'Kadidja', 'Maïmouna', 'Nafissatou', 'Rokia',
    'Tenin',
]
PRENOMS_M = [
    'Jean-Marc', 'Mohamed', 'Ibrahim', 'Serge', 'Franck', 'Wilfried',
    'Ange', 'Boris', 'Cédric', 'Landry', 'Olivier', 'Sékou', 'Moussa',
    'Abdoulaye', 'Cheick', 'Ismaël', 'Emmanuel', 'Fabrice', 'Yacouba',
    'Daouda',
]
VILLES = [
    'Abidjan', 'Bouaké', 'Yamoussoukro', 'Korhogo', 'Man', 'San-Pédro',
    'Daloa', 'Gagnoa', 'Abengourou', 'Grand-Bassam',
]


def _slug(texte):
    return (
        unicodedata.normalize('NFKD', texte)
        .encode('ascii', 'ignore').decode().lower().replace(' ', '').replace('-', '')
    )


def _identite(seq, sexe):
    nom = NOMS[seq % len(NOMS)]
    prenoms = PRENOMS_F if sexe == 'F' else PRENOMS_M
    prenom = prenoms[(seq * 7) % len(prenoms)]
    return nom, prenom


class Command(BaseCommand):
    help = 'Candidatures fictives de couverture (formations × niveaux × statuts).'

    def add_arguments(self, parser):
        parser.add_argument('--par-combo', type=int, default=2)
        parser.add_argument('--purger', action='store_true')

    def handle(self, *args, **options):
        if options['purger']:
            dossiers = Candidature.objects.filter(
                observations__startswith=MARQUEUR,
            )
            nombre = dossiers.count()
            dossiers.delete()
            candidats = Candidat.objects.filter(
                email__regex=r'\.[0-9]+@exemple\.ci$', candidatures__isnull=True,
            )
            candidats.delete()
            self.stdout.write(self.style.SUCCESS(
                f'Purge couverture candidatures : {nombre} dossier(s) retiré(s).',
            ))
            return

        if not TypeCandidature.objects.exists():
            call_command('init_referentiels_admission', stdout=self.stdout)

        annee = AnneeAcademique.objects.filter(courante=True).first()
        if annee is None:
            raise CommandError('Aucune année académique courante.')
        acteur = (
            User.objects.filter(username='admin').first()
            or User.objects.filter(is_superuser=True, is_active=True).order_by('id').first()
            or User.objects.filter(is_active=True).order_by('id').first()
        )
        niveaux = {n.code: n for n in Niveau.objects.all()}
        types = {t.code: t for t in TypeCandidature.objects.all()}
        voies = {v.code: v for v in VoieAcces.objects.all()}
        regimes = {r.code: r for r in RegimeEtudes.objects.all()}
        vagues = list(RefVague.objects.order_by('id'))
        formations = list(RefFormation.objects.filter(actif=True).order_by('intitule', 'id'))

        cases = []
        for formation in formations:
            codes = NIVEAUX_PAR_DIPLOME.get(formation.type_diplome, [])
            for code in codes:
                if code in niveaux:
                    cases.append((formation, niveaux[code]))
        if not cases:
            raise CommandError('Aucune case formation × niveau cohérente.')

        par_combo = max(1, options['par_combo'])
        statuts = list(Candidature.Statut.values)
        nb = {'candidats': 0, 'dossiers': 0, 'pieces': 0}
        seq = 0
        debut_campagne = date(2026, 9, 1)

        with transaction.atomic():
            for formation, niveau in cases:
                parcours = Parcours.objects.filter(ref_formation=formation).first()
                for statut_code in statuts:
                    for rang in range(par_combo):
                        seq += 1
                        sexe = 'F' if seq % 2 == 0 else 'M'
                        nom, prenom = _identite(seq, sexe)
                        email = f'{_slug(prenom)}.{_slug(nom)}.{seq}@exemple.ci'
                        candidat, cree = Candidat.objects.get_or_create(
                            email=email,
                            defaults={
                                'nom': nom.upper(), 'prenom': prenom, 'sexe': sexe,
                                'date_naissance': date(
                                    ANNEE_NAISSANCE_BASE[niveau.code] - (seq % 3),
                                    1 + seq % 12, 1 + seq % 27,
                                ),
                                'lieu_naissance': VILLES[seq % len(VILLES)],
                                'nationalite': 'CI',
                                'telephone': f'+225 07 {seq % 90 + 10:02d} {seq % 90 + 10:02d} {seq % 90 + 10:02d} {seq % 90 + 10:02d}',
                                'telephone2': f'+225 01 {seq % 90 + 10:02d} {seq % 90 + 10:02d} {seq % 90 + 10:02d} {seq % 90 + 10:02d}',
                                'adresse': f"{VILLES[seq % len(VILLES)]}, Côte d'Ivoire (adresse d'exemple)",
                            },
                        )
                        nb['candidats'] += int(cree)
                        # Idempotence stricte : un dossier (même annulé)
                        # déjà créé pour ce candidat ne doit pas être recréé.
                        if Candidature.objects.filter(
                            candidat=candidat, annee_academique=annee,
                            ref_formation=formation, niveau=niveau,
                        ).exists():
                            continue

                        # Type de candidature et voie d'accès plausibles :
                        # concours direct en entrée de Licence, sur titre
                        # ensuite ; VAE en Master de temps en temps.
                        if niveau.code == 'L1':
                            type_c = types.get('CONCOURS_DIRECT')
                            voie = voies.get('BAC')
                        elif niveau.code in ('L2', 'L3'):
                            type_c = types.get('SUR_TITRE')
                            voie = voies.get('PASSERELLE' if seq % 4 == 0 else 'DIPLOME_EQUIVALENT')
                        else:
                            type_c = types.get('SUR_TITRE')
                            voie = voies.get('VAE' if seq % 5 == 0 else 'DIPLOME_EQUIVALENT')
                        regime = regimes.get(
                            'PROFESSIONNEL' if seq % 11 == 0
                            else 'CONTINU' if seq % 7 == 0 else 'INITIAL',
                        )
                        date_candidature = debut_campagne + timedelta(days=seq % 75)
                        candidature = services.creer_candidature(
                            candidat, acteur=acteur,
                            annee_academique=annee, ref_formation=formation,
                            niveau=niveau, parcours=parcours,
                            type_candidature=type_c, voie_acces=voie,
                            regime=regime,
                            vague=vagues[seq % len(vagues)] if vagues else None,
                            date_candidature=date_candidature,
                            observations=(
                                f'{MARQUEUR} — dossier fictif {formation.intitule} '
                                f'({niveau.code}), statut visé '
                                f'{Candidature.Statut(statut_code).label}.'
                            ),
                        )
                        nb['dossiers'] += 1
                        nb['pieces'] += self._remplir_pieces(
                            candidature, PROFILS[S(statut_code)], date_candidature, acteur,
                        )
                        for etape in CHEMINS[S(statut_code)]:
                            workflow.appliquer_transition(
                                candidature, etape, acteur=acteur,
                                commentaire='Avancement du dossier (donnée d’exemple).',
                            )
                        if S(statut_code) in STATUTS_AVEC_SCORE:
                            candidature.score = Decimal('10.0') + Decimal(seq % 90) / Decimal('10')
                            candidature.save(update_fields=['score', 'updated_at'])

        self.stdout.write(self.style.SUCCESS(
            f'Couverture candidatures {annee.libelle} : {nb["dossiers"]} '
            f'dossier(s) créé(s) sur {len(cases)} cases formation × niveau '
            f'et {len(statuts)} statuts ({nb["candidats"]} candidat(s) '
            f'fictifs, parité F/M), {nb["pieces"]} pièce(s) déposée(s).',
        ))

    def _remplir_pieces(self, candidature, profil, date_candidature, acteur):
        """Dépose/vérifie les pièces selon le profil d'avancement du dossier."""
        PS = PieceCandidature.Statut
        if profil == 'vides':
            return 0
        obligatoires = list(
            candidature.pieces.filter(obligatoire=True).select_related('type_piece'),
        )
        delivrance = date_candidature - timedelta(days=25)
        deposees = 0

        def deposer(piece, valider=False, refuser=False):
            nonlocal deposees
            expiration = None
            if piece.type_piece.code == 'CERTIFICAT_MEDICAL':
                expiration = delivrance + timedelta(days=365)
            elif piece.type_piece.code == 'PIECE_IDENTITE':
                expiration = delivrance + timedelta(days=1825)
            services.deposer_piece(
                piece, acteur=acteur,
                numero_document=f'EXEMPLE-{piece.type_piece.code}-{candidature.numero}',
                date_delivrance=delivrance, date_expiration=expiration,
            )
            deposees += 1
            if valider:
                services.verifier_piece(piece, PS.VALIDEE, acteur=acteur)
            elif refuser:
                services.verifier_piece(
                    piece, PS.REFUSEE, acteur=acteur,
                    commentaire='Document illisible : merci de redéposer un scan net.',
                )

        if profil == 'complet':
            for piece in obligatoires:
                deposer(piece, valider=True)
            cv = candidature.pieces.filter(
                type_piece__code='CV', obligatoire=False,
            ).first()
            if cv is not None:
                deposer(cv, valider=True)
        elif profil == 'deposees':
            for piece in obligatoires:
                deposer(piece)
        elif profil == 'partiel':
            for rang, piece in enumerate(obligatoires):
                if rang < 3:
                    deposer(piece, valider=True)
                elif rang < 5:
                    deposer(piece)
                elif rang == 5:
                    deposer(piece, refuser=True)
                # rang >= 6 : pièce laissée manquante
        return deposees
