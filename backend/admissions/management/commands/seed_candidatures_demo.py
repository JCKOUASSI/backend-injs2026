"""Jeu de données d'exemple pour le module Admissions & Candidatures.

Alimente les écrans « Candidatures », « Admissions » et « Campagnes » avec des
dossiers de démonstration couvrant **les 12 statuts** du workflow, les pièces
justificatives (fichiers PDF d'exemple téléchargeables), les décisions
d'admission et le concours dans tous ses états : **7 campagnes** (brouillon,
planifiée, ouverte, suspendue, clôturée, archivée, annulée), les 4 types
d’épreuves (écrit, physique, oral, pratique),
convocations, présences, notes (complètes, partielles, corrigées, absences),
verrouillage, classement calculé **et classement publié** sur la cohorte de
l’année précédente.

Tout passe par les services métier de l'application
(``services.creer_candidature``, ``deposer_piece``, ``verifier_piece``,
``workflow.appliquer_transition``, ``admission_services``,
``concours_services``) : les dossiers créés sont journalisés et se comportent
exactement comme des dossiers saisis à l'écran.

Identification des données d'exemple : candidats en ``@exemple.ci`` et
observations préfixées « [Exemple] ». Commande **idempotente** (une seconde
exécution ne crée rien) et réversible :

    python manage.py seed_candidatures_demo            # peuplement
    python manage.py seed_candidatures_demo --purger   # retrait complet
"""

import unicodedata
from datetime import date, time, timedelta
from decimal import Decimal

from django.core.files.base import ContentFile
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from admissions import admission_services, concours_services, services, workflow
from admissions.models import (
    Admission, CampagneAdmission, Candidat, Candidature, ClassementConcours,
    ConvocationEpreuve, Epreuve, NoteConcours, PieceCandidature,
    SurveillanceEpreuve, TypeCandidature, TypePiece, VoieAcces,
)
from authentication.models import User
from formations.models import (
    Participant, RefCategorie, RefFormation, RefGrade, RefSalle, RefSite,
    RefVague,
)
from scolarite import inscription_services
from scolarite.models import (
    AnneeAcademique, DossierEtudiant, InscriptionAdministrative, Niveau,
    Parcours, RegimeEtudes,
)

DOMAINE_EXEMPLE = '@exemple.ci'
PREFIXE_OBSERVATION = '[Exemple] '

LIBELLE_CAMPAGNE_CONCOURS = 'Concours direct — Licence Éducation et Motricité'
LIBELLE_CAMPAGNE_TITRE = 'Admission sur titre — Master Management du Sport'
LIBELLE_CAMPAGNE_ANCIENNE = 'Concours direct — Licence Entraînement Sportif'
LIBELLE_CAMPAGNE_BROUILLON = 'Admission sur titre — Licence Entrepreneuriat Jeunesse et Conduite de Projets'
LIBELLE_CAMPAGNE_SUSPENDUE = 'Admission sur titre — Master Andragogie'
LIBELLE_CAMPAGNE_ARCHIVEE = 'Concours direct — Licence Loisir'
LIBELLE_CAMPAGNE_ANNULEE = 'Admission sur titre — Master Gérontologie'

LIBELLES_CAMPAGNES = (
    LIBELLE_CAMPAGNE_CONCOURS, LIBELLE_CAMPAGNE_TITRE,
    LIBELLE_CAMPAGNE_ANCIENNE, LIBELLE_CAMPAGNE_BROUILLON,
    LIBELLE_CAMPAGNE_SUSPENDUE, LIBELLE_CAMPAGNE_ARCHIVEE,
    LIBELLE_CAMPAGNE_ANNULEE,
)

S = Candidature.Statut

# Chemins de transitions légaux vers chaque statut d'arrivée (depuis BROUILLON).
_CHEMIN_BASE = [S.SOUMISE, S.EN_ATTENTE_DE_VERIFICATION]
CHEMINS = {
    S.BROUILLON: [],
    S.SOUMISE: [S.SOUMISE],
    S.EN_ATTENTE_DE_VERIFICATION: _CHEMIN_BASE,
    S.PIECES_INCOMPLETES: _CHEMIN_BASE + [S.PIECES_INCOMPLETES],
    S.PIECES_VALIDEES: _CHEMIN_BASE + [S.PIECES_VALIDEES],
    S.EN_ETUDE: _CHEMIN_BASE + [S.PIECES_VALIDEES, S.EN_ETUDE],
    S.ADMISSIBLE: _CHEMIN_BASE + [S.PIECES_VALIDEES, S.EN_ETUDE, S.ADMISSIBLE],
    S.LISTE_ATTENTE: _CHEMIN_BASE + [S.PIECES_VALIDEES, S.EN_ETUDE, S.LISTE_ATTENTE],
    S.ANNULE: [S.SOUMISE, S.ANNULE],
}

ORDRE_PIECES_OBLIGATOIRES = [
    'ACTE_NAISSANCE', 'PIECE_IDENTITE', 'DIPLOME', 'RELEVE_NOTES',
    'PHOTO', 'CERTIFICAT_MEDICAL', 'RECU_PAIEMENT',
]


def _sans_accents(texte):
    return ''.join(
        c for c in unicodedata.normalize('NFKD', texte)
        if not unicodedata.combining(c)
    )


def _slug_email(nom, prenom):
    base = f'{prenom.split()[0]}.{nom.split()[0]}'
    base = _sans_accents(base).lower().replace("'", '').replace('-', '.')
    return f'{base}{DOMAINE_EXEMPLE}'


def pdf_exemple(lignes):
    """PDF A4 minimal d'une page — lisible partout, sans librairie externe."""
    operations = []
    ordonnee = 786
    for ligne in lignes:
        propre = _sans_accents(ligne).replace('\\', ' ').replace('(', ' ').replace(')', ' ')
        operations.append(f'BT /F1 12 Tf 56 {ordonnee} Td ({propre}) Tj ET')
        ordonnee -= 19
    contenu = '\n'.join(operations).encode('latin-1', errors='ignore')
    objets = [
        b'<< /Type /Catalog /Pages 2 0 R >>',
        b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] '
        b'/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>',
        b'<< /Length ' + str(len(contenu)).encode() + b' >>\nstream\n' + contenu + b'\nendstream',
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
    ]
    pdf = bytearray(b'%PDF-1.4\n')
    decalages = []
    for numero, objet in enumerate(objets, start=1):
        decalages.append(len(pdf))
        pdf += f'{numero} 0 obj\n'.encode() + objet + b'\nendobj\n'
    xref = len(pdf)
    pdf += f'xref\n0 {len(objets) + 1}\n'.encode()
    pdf += b'0000000000 65535 f \n'
    for decalage in decalages:
        pdf += f'{decalage:010d} 00000 n \n'.encode()
    pdf += (
        f'trailer\n<< /Size {len(objets) + 1} /Root 1 0 R >>\n'
        f'startxref\n{xref}\n%%EOF'
    ).encode()
    return bytes(pdf)


# ── Scénarios ────────────────────────────────────────────────────────────────
# (nom, prénom, sexe, naissance, lieu, nationalité, filière, diplôme, niveau,
#  type de candidature, voie d'accès, profil de pièces, statut final,
#  campagne ?, admission, observation)
# Profils de pièces : complet | deposees | partiel | expiree | vides
# Admission : None | 'ouverte' | 'ADMIS' | 'ADMIS_SOUS_RESERVE' | 'REFUSEE'
SCENARIOS = [
    # — Campagne concours (EM Licence) : 6 dossiers convoquables et notés —
    ('KOUADIO', 'Aya Marie', 'F', date(2007, 3, 14), 'Abidjan', 'Ivoirienne',
     'F01', 'LICENCE', 'L1', 'CONCOURS_DIRECT', 'BAC', 'complet', S.ADMISSIBLE,
     True, None, 'Premier dossier reçu de la campagne.'),
    ('TRAORÉ', 'Ibrahim', 'M', date(2006, 11, 2), 'Bouaké', 'Ivoirienne',
     'F01', 'LICENCE', 'L1', 'CONCOURS_DIRECT', 'BAC', 'complet', S.EN_ETUDE,
     True, None, ''),
    ("N'GUESSAN", 'Michel Arnaud', 'M', date(2005, 6, 27), 'Yamoussoukro', 'Ivoirienne',
     'F01', 'LICENCE', 'L1', 'CONCOURS_DIRECT', 'BAC', 'complet', S.EN_ETUDE,
     True, None, 'Absent aux tests physiques (certificat en cours).'),
    ('Diallo', 'Tenin Aïssatou', 'F', date(2007, 9, 8), 'Korhogo', 'Ivoirienne',
     'F01', 'LICENCE', 'L1', 'CONCOURS_DIRECT', 'BAC', 'complet',
     S.PIECES_VALIDEES, True, None, ''),
    ('BAKAYOKO', 'Sékou', 'M', date(2006, 1, 19), 'San-Pédro', 'Ivoirienne',
     'F01', 'LICENCE', 'L1', 'CONCOURS_DIRECT', 'BAC', 'complet',
     S.PIECES_VALIDEES, True, None, ''),
    ('FOFANA', 'Aminata', 'F', date(2008, 4, 30), 'Abidjan', 'Ivoirienne',
     'F01', 'LICENCE', 'L1', 'CONCOURS_DIRECT', 'BAC', 'partiel',
     S.PIECES_INCOMPLETES, True, None, 'Relevé de notes rejeté : scan illisible.'),
    # — Décisions prononcées —
    ('Koné', 'Adjoua Patricia', 'F', date(2006, 8, 15), 'Abidjan', 'Ivoirienne',
     'F03', 'LICENCE', 'L1', 'CONCOURS_DIRECT', 'BAC', 'complet', S.ADMISSIBLE,
     False, 'ADMIS', ''),
    ('Touré', 'Mamadou', 'M', date(2001, 2, 11), 'Daloa', 'Ivoirienne',
     'F03', 'MASTER', 'M1', 'SUR_TITRE', 'DIPLOME_EQUIVALENT', 'complet',
     S.ADMISSIBLE, False, 'ADMIS', 'Licence STAPS obtenue à Abidjan.'),
    ('Yao', "N'goran", 'M', date(2007, 12, 5), 'Abengourou', 'Ivoirienne',
     'F04', 'LICENCE', 'L1', 'CONCOURS_DIRECT', 'BAC', 'complet', S.ADMISSIBLE,
     False, 'ADMIS_SOUS_RESERVE',
     'Réserve : certificat médical à renouveler avant la rentrée.'),
    # — Admissions ouvertes, décision en attente —
    ('BAMBA', 'Fatou', 'M', date(2007, 5, 23), 'Man', 'Ivoirienne',
     'F02', 'LICENCE', 'L1', 'CONCOURS_DIRECT', 'BAC', 'complet', S.ADMISSIBLE,
     False, 'ouverte', ''),
    ('Sangaré', 'Oumar Sidiki', 'M', date(1999, 10, 3), 'Abidjan', 'Ivoirienne',
     'F04', 'MASTER', 'M1', 'CONCOURS_PROFESSIONNEL', 'DETACHEMENT', 'complet',
     S.LISTE_ATTENTE, False, 'ouverte', 'Enseignant en fonction (détachement).'),
    ('CISSÉ', 'Mariam', 'F', date(2002, 7, 17), 'Gagnoa', 'Ivoirienne',
     'F01', 'MASTER', 'M1', 'SUR_TITRE', 'DIPLOME_EQUIVALENT', 'complet',
     S.EN_ETUDE, False, 'ouverte', ''),
    # — Dossiers à des stades variés —
    ('Koffi', 'Larissa', 'F', date(2005, 9, 9), 'Grand-Bassam', 'Ivoirienne',
     'F06', 'LICENCE', 'L2', 'REORIENTATION', 'PASSERELLE', 'complet',
     S.PIECES_VALIDEES, False, None, 'Réorientation depuis une autre université.'),
    ('Diabaté', 'Moussa', 'M', date(2004, 1, 28), 'Abidjan', 'Malienne',
     'F03', 'LICENCE', 'L3', 'TRANSFERT', 'PASSERELLE', 'expiree',
     S.PIECES_INCOMPLETES, False, None,
     'Transfert : certificat médical expiré, à renouveler.'),
    ('OUATTARA', 'Jean', 'F', date(1998, 6, 12), 'Odienné', 'Ivoirienne',
     'F08', 'LICENCE', 'L1', 'CONCOURS_PROFESSIONNEL', 'VAE', 'partiel',
     S.PIECES_INCOMPLETES, False, None, 'Dossier VAE en cours de complétion.'),
    ('GUEU', 'Marie Laure', 'F', date(2000, 3, 21), 'Touba', 'Ivoirienne',
     'F05', 'MASTER', 'M1', 'CONCOURS_PROFESSIONNEL', 'DETACHEMENT', 'deposees',
     S.EN_ATTENTE_DE_VERIFICATION, False, None,
     'Pièces déposées au secrétariat, vérification en attente.'),
    ('Silué', 'Tiéné', 'M', date(2008, 2, 2), 'Ferkessédougou', 'Ivoirienne',
     'F07', 'LICENCE', 'L1', 'CONCOURS_DIRECT', 'BAC', 'vides', S.SOUMISE,
     False, None, 'Dossier transmis sans pièce pour le moment.'),
    ('Ballet', 'Brou', 'M', date(2000, 11, 16), 'Soubré', 'Ivoirienne',
     'F02', 'MASTER', 'M2', 'TRANSFERT', 'PASSERELLE', 'vides', S.BROUILLON,
     False, None, 'Saisie commencée au secrétariat.'),
    ('KEÏTA', 'Aïcha', 'F', date(2006, 4, 7), 'Abidjan', 'Ivoirienne',
     'F03', 'LICENCE', 'L1', 'CONCOURS_DIRECT', 'BAC', 'complet', S.ADMISSIBLE,
     False, 'REFUSEE', ''),
    ("N'DIAYE", 'Sokhna', 'F', date(2007, 8, 24), 'Dakar', 'Sénégalaise',
     'F04', 'LICENCE', 'L1', 'SUR_TITRE', 'DIPLOME_EQUIVALENT', 'partiel',
     S.ANNULE, False, None, 'Désistement de la candidate (admission à Dakar).'),
]

# Notes du concours (clé = rang du scénario 1..6) : (écrit /20, physique /20 ou None si absent)
NOTES_CONCOURS = {
    1: ('16.50', '17.00'),
    2: ('12.75', '14.00'),
    3: ('14.00', None),
    4: ('15.25', '16.50'),
    5: ('11.00', '12.75'),
    6: ('9.50', '11.00'),
}

# Épreuve pratique de la campagne ouverte : saisie PARTIELLE (3 notes sur 6 —
# le scénario 5 était absent, les scénarios 3 et 6 restent à saisir).
NOTES_PRATIQUE = {1: '15.50', 2: '12.00', 4: '16.25'}

# Scénarios 21 à 26 — cohorte de l'année précédente (campagne historique
# Entraînement Sportif) : concours terminé, classement PUBLIÉ, admissions
# prononcées pour les deux premiers. Même format que SCENARIOS.
SCENARIOS_HISTORIQUE = [
    ("N'DRI", 'Armel', 'M', date(2003, 1, 9), 'Bouaké', 'CI',
     'F03', 'LICENCE', 'L1', 'CONCOURS_DIRECT', 'CONCOURS', 'complet',
     'ADMISSIBLE', True, 'ADMIS', 'Major du concours (cohorte précédente).'),
    ('TOURÉ', 'Salimata', 'F', date(2004, 6, 26), 'Korhogo', 'CI',
     'F03', 'LICENCE', 'L1', 'CONCOURS_DIRECT', 'CONCOURS', 'complet',
     'ADMISSIBLE', True, 'ADMIS', 'Admise au concours (cohorte précédente).'),
    ('Yao', 'Fatoumata', 'F', date(2003, 11, 30), 'Yamoussoukro', 'CI',
     'F03', 'LICENCE', 'L1', 'CONCOURS_DIRECT', 'CONCOURS', 'complet',
     'ADMISSIBLE', True, 'ouverte',
     'Admissible, décision en attente (cohorte précédente).'),
    ('Yao', 'Kouakou Christian', 'M', date(2002, 3, 2), 'Man', 'CI',
     'F03', 'LICENCE', 'L1', 'CONCOURS_DIRECT', 'CONCOURS', 'complet',
     'LISTE_ATTENTE', True, None,
     "En liste d'attente après classement (cohorte précédente)."),
    ('DIOMANDÉ', 'Souleymane', 'M', date(2004, 8, 17), 'Daloa', 'CI',
     'F03', 'LICENCE', 'L1', 'CONCOURS_DIRECT', 'CONCOURS', 'complet',
     'LISTE_ATTENTE', True, None,
     "Absent à l’épreuve pratique (cohorte précédente)."),
    ('TANOH', 'Aya Marcelle', 'F', date(2005, 2, 11), 'Abidjan', 'CI',
     'F03', 'LICENCE', 'L1', 'CONCOURS_DIRECT', 'CONCOURS', 'partiel',
     'PIECES_INCOMPLETES', True, None,
     'Dossier incomplet, non admise (cohorte précédente).'),
]

# Notes (écrit coef 2, physique coef 3, pratique coef 2) : l’ordre de mérite
# suit l’ordre des scénarios 21 → 26 (None = absent).
NOTES_HISTORIQUE = {
    21: ('16.00', '17.50', '15.00'),
    22: ('15.00', '16.00', '14.50'),
    23: ('13.50', '15.00', '13.00'),
    24: ('12.00', '13.00', '12.50'),
    25: ('11.50', '14.00', None),
    26: ('8.00', '9.50', '7.00'),
}

# Scénarios 29 à 36 — renfort du module Admissions : dossiers complets et
# admissibles dans des formations variées. Le champ admission reste à None :
# les décisions (variées, voir COMPLEMENT_ADMISSIONS) sont prononcées par
# _complement_admissions, qui gère aussi l'inscription et l'annulation.
SCENARIOS_ADMISSIONS = [
    ('Diabaté', 'Aboubacar', 'M', date(2003, 4, 12), 'Bouaké', 'CI',
     'F02', 'LICENCE', 'L1', 'ADMISSION_SUR_TITRE', 'TITRE', 'complet',
     'ADMISSIBLE', False, None, 'Admis avec profil administratif renseigné.'),
    ('KONAN', 'Affoué Patricia', 'F', date(2002, 9, 3), 'Abidjan', 'CI',
     'F01', 'MASTER', 'M1', 'ADMISSION_SUR_TITRE', 'TITRE', 'complet',
     'ADMISSIBLE', False, None, 'Admise puis inscrite (dossier étudiant créé).'),
    ('Koffi', 'Jean-Marc', 'M', date(2001, 1, 27), 'Yamoussoukro', 'CI',
     'F06', 'LICENCE', 'L1', 'CONCOURS_DIRECT', 'CONCOURS', 'complet',
     'ADMISSIBLE', False, None, 'Admis sous réserve de complément de dossier.'),
    ('Touré', 'Aminata', 'F', date(2004, 5, 16), 'Korhogo', 'CI',
     'F08', 'LICENCE', 'L1', 'ADMISSION_SUR_TITRE', 'TITRE', 'complet',
     'ADMISSIBLE', False, None, 'Admission ouverte, décision non prononcée.'),
    ('Koné', 'Ibrahim', 'M', date(2000, 8, 30), 'Man', 'CI',
     'F07', 'MASTER', 'M1', 'ADMISSION_SUR_TITRE', 'TITRE', 'complet',
     'ADMISSIBLE', False, None, 'Avis défavorable de la commission.'),
    ('Sangaré', 'Fatou', 'F', date(2003, 12, 5), 'Abidjan', 'CI',
     'F04', 'LICENCE', 'L1', 'CONCOURS_DIRECT', 'CONCOURS', 'complet',
     'ADMISSIBLE', False, None, 'Admise mais délai d’inscription dépassé.'),
    ('OUATTARA', 'Nagnin Crépin', 'M', date(2002, 2, 19), 'Daloa', 'CI',
     'F02', 'MASTER', 'M1', 'ADMISSION_SUR_TITRE', 'TITRE', 'complet',
     'ADMISSIBLE', False, None, 'Désistement après admission (annulée).'),
    ('GBAKOU', 'Marie Laure', 'F', date(2001, 7, 22), 'San Pedro', 'CI',
     'F05', 'LICENCE', 'L1', 'ADMISSION_SUR_TITRE', 'TITRE', 'complet',
     'ADMISSIBLE', False, None, 'Profil renseigné, en attente de décision.'),
]

# Complément d'admissions : (rang de scénario, décision ou None si ouverte,
# décalage de la date limite en jours, inscrire, annuler ensuite, profil).
# Le rang 1 (major du classement calculé, admissible) reçoit une admission
# ouverte ; le rang
# 7 (admise 2026-2027) est inscrite — le major de la cohorte précédente
# (rang 21) ne peut plus l'être, son année étant clôturée.
CATEGORIES_EXEMPLE = {
    'Catégorie A (exemple)': ['Grade A3 (exemple)', 'Grade A4 (exemple)'],
    'Catégorie B (exemple)': ['Grade B3 (exemple)'],
}

COMPLEMENT_ADMISSIONS = [
    (1, None, None, False, False, False),
    (7, None, None, True, False, False),
    (29, 'ADMIS', 30, False, False, True),
    (30, 'ADMIS', 60, True, False, False),
    (31, 'ADMIS_SOUS_RESERVE', 21, False, False, False),
    (32, None, None, False, False, False),
    (33, 'REFUSEE', None, False, False, False),
    (34, 'ADMIS', -10, False, False, False),
    (35, 'ADMIS', 45, False, True, False),
    (36, None, None, False, False, True),
]

# Scénarios 27 et 28 — campagne suspendue (Master Andragogie) : dossiers déposés
# avant la suspension de la campagne.
SCENARIOS_SUSPENDUE = [
    ('Yao', 'Marie-Noël', 'F', date(2001, 12, 25), 'Grand-Bassam', 'CI',
     'F05', 'MASTER', 'M1', 'ADMISSION_SUR_TITRE', 'TITRE', 'complet',
     'PIECES_VALIDEES', True, None, 'Campagne suspendue (dossier validé).'),
    ('Koffi', 'Jean-Marie', 'M', date(2000, 5, 19), 'San Pedro', 'CI',
     'F05', 'MASTER', 'M1', 'ADMISSION_SUR_TITRE', 'TITRE', 'en_cours',
     'EN_ATTENTE_DE_VERIFICATION', True, None,
     'Campagne suspendue (dossier en vérification).'),
]


class Command(BaseCommand):
    help = (
        'Peuple le module Admissions & Candidatures avec des données '
        "d'exemple (idempotent ; --purger pour tout retirer)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--purger', action='store_true',
            help='Supprime toutes les données d’exemple (candidats '
                 '@exemple.ci, leurs dossiers et les campagnes de démonstration).',
        )

    # ── point d'entrée ──────────────────────────────────────────────────────
    def handle(self, *args, **options):
        if options['purger']:
            self._purger()
            return

        if not TypePiece.objects.exists():
            call_command('init_referentiels_admission', stdout=self.stdout)

        annee = AnneeAcademique.objects.filter(courante=True).first()
        if annee is None:
            raise CommandError(
                'Aucune année académique courante : définissez-la avant '
                'de charger les données d’exemple.'
            )
        self.acteur = (
            User.objects.filter(username='admin').first()
            or User.objects.filter(is_superuser=True).order_by('id').first()
        )
        self.aujourdhui = timezone.localdate()
        self.regime = RegimeEtudes.objects.filter(code='INITIAL').first()

        bilan = {'campagnes': 0, 'candidatures': 0, 'pieces': 0, 'admissions': 0}
        with transaction.atomic():
            campagnes = self._campagnes(annee, bilan)
            par_cle = self._candidatures(annee, campagnes, bilan)
            if campagnes.get('concours') is not None:
                self._concours(campagnes['concours'], par_cle, bilan)
            if campagnes.get('historique') is not None:
                self._concours_historique(campagnes['historique'], par_cle, bilan)
            suspendue = campagnes.get('suspendue')
            if (suspendue is not None
                    and suspendue.statut == CampagneAdmission.Statut.OUVERTE):
                concours_services.appliquer_transition_campagne(
                    suspendue, CampagneAdmission.Statut.SUSPENDUE,
                    acteur=self.acteur,
                    commentaire='Suspension (donnée d’exemple).',
                )
            self._complement_admissions(par_cle, bilan)

        total = Candidature.objects.count()
        par_statut = {
            ligne['statut']: ligne['n']
            for ligne in Candidature.objects.values('statut').annotate(n=Count('id'))
        }
        self.stdout.write(self.style.SUCCESS(
            f'Données d’exemple prêtes : {total} candidature(s) en base, '
            f'{bilan["campagnes"]} campagne(s) créée(s) ce passage, '
            f'{bilan["candidatures"]} dossier(s) créé(s), '
            f'{bilan["pieces"]} pièce(s) déposée(s), '
            f'{bilan["admissions"]} admission(s) ouverte(s).'
        ))
        self.stdout.write('  Répartition des statuts : ' + ', '.join(
            f'{Candidature.Statut(code).label} {par_statut.get(code, 0)}'
            for code in Candidature.Statut.values if par_statut.get(code)
        ))

    # ── référentiels et campagnes ───────────────────────────────────────────
    def _formation(self, filiere, diplome):
        formation = RefFormation.objects.filter(
            filiere_code=filiere, type_diplome=diplome, actif=True,
        ).order_by('id').first()
        if formation is None:
            self.stdout.write(self.style.WARNING(
                f'  formation {filiere}/{diplome} introuvable — scénario ignoré'))
        return formation

    def _creer_campagne(self, libelle, annee, formation, ouverture, fermeture,
                        transitions, bilan, quota_admissibles=None,
                        quota_admis=None):
        existante = CampagneAdmission.objects.filter(
            libelle=libelle, annee_academique=annee, ref_formation=formation,
        ).first()
        if existante is not None:
            return existante
        campagne = CampagneAdmission(
            libelle=libelle, annee_academique=annee, ref_formation=formation,
            date_ouverture=ouverture, date_fermeture=fermeture,
            quota_admissibles=quota_admissibles, quota_admis=quota_admis,
        )
        campagne.full_clean()
        campagne.save()
        bilan['campagnes'] += 1
        for statut in transitions:
            concours_services.appliquer_transition_campagne(
                campagne, statut, acteur=self.acteur,
                commentaire='Donnée d’exemple.',
            )
        return campagne

    def _campagnes(self, annee, bilan):
        """Sept campagnes d’exemple : une par état du cycle de vie."""
        CS = CampagneAdmission.Statut
        aujourd_hui = self.aujourdhui
        campagnes = {}

        formation_concours = self._formation('F01', 'LICENCE')
        if formation_concours is not None:
            campagnes['concours'] = self._creer_campagne(
                LIBELLE_CAMPAGNE_CONCOURS, annee, formation_concours,
                aujourd_hui - timedelta(days=90), aujourd_hui + timedelta(days=120),
                quota_admissibles=3, quota_admis=2,
                transitions=[CS.PLANIFIEE, CS.OUVERTE], bilan=bilan,
            )

        formation_titre = self._formation('F04', 'MASTER')
        if formation_titre is not None:
            campagnes['titre'] = self._creer_campagne(
                LIBELLE_CAMPAGNE_TITRE, annee, formation_titre,
                aujourd_hui + timedelta(days=60), aujourd_hui + timedelta(days=150),
                quota_admissibles=10, quota_admis=8,
                transitions=[CS.PLANIFIEE], bilan=bilan,
            )

        # Brouillon sans dates ni quotas : à compléter avant planification.
        formation_brouillon = self._formation('F07', 'LICENCE')
        if formation_brouillon is not None:
            campagnes['brouillon'] = self._creer_campagne(
                LIBELLE_CAMPAGNE_BROUILLON, annee, formation_brouillon,
                None, None, transitions=[], bilan=bilan,
            )

        # Suspendue : ouverte le temps de recevoir ses candidatures, puis
        # suspendue dans handle() (après le dépôt des dossiers).
        formation_suspendue = self._formation('F05', 'MASTER')
        if formation_suspendue is not None:
            campagnes['suspendue'] = self._creer_campagne(
                LIBELLE_CAMPAGNE_SUSPENDUE, annee, formation_suspendue,
                aujourd_hui - timedelta(days=45), aujourd_hui + timedelta(days=90),
                quota_admissibles=12, quota_admis=10,
                transitions=[CS.PLANIFIEE, CS.OUVERTE], bilan=bilan,
            )

        # Annulée : planifiée puis annulée (session reportée).
        formation_annulee = self._formation('F08', 'MASTER')
        if formation_annulee is not None:
            campagnes['annulee'] = self._creer_campagne(
                LIBELLE_CAMPAGNE_ANNULEE, annee, formation_annulee,
                aujourd_hui + timedelta(days=30), aujourd_hui + timedelta(days=90),
                quota_admissibles=10, quota_admis=8,
                transitions=[CS.PLANIFIEE, CS.ANNULEE], bilan=bilan,
            )

        annee_precedente = (
            AnneeAcademique.objects.filter(date_debut__lt=annee.date_debut)
            .order_by('-date_debut').first()
        )
        campagnes['annee_precedente'] = annee_precedente

        # Archivée : ancienne session sans dossier (fond d’historique).
        formation_archivee = self._formation('F06', 'LICENCE')
        if annee_precedente is not None and formation_archivee is not None:
            campagnes['archivee'] = self._creer_campagne(
                LIBELLE_CAMPAGNE_ARCHIVEE, annee_precedente, formation_archivee,
                aujourd_hui - timedelta(days=500), aujourd_hui - timedelta(days=430),
                quota_admissibles=20, quota_admis=15,
                transitions=[CS.PLANIFIEE, CS.OUVERTE, CS.CLOTUREE, CS.ARCHIVEE],
                bilan=bilan,
            )

        # Historique (année précédente) : campagne complète — candidatures,
        # épreuves, classement PUBLIÉ, admissions, puis clôture. Elle est
        # ouverte le temps de l’alimentation, puis refermée avec ses vraies
        # dates dans _concours_historique(). Une ancienne campagne vide du
        # même libellé (première version du jeu d’exemple) est remplacée.
        formation_ancienne = self._formation('F03', 'LICENCE')
        if annee_precedente is not None and formation_ancienne is not None:
            existante = CampagneAdmission.objects.filter(
                libelle=LIBELLE_CAMPAGNE_ANCIENNE,
                annee_academique=annee_precedente,
                ref_formation=formation_ancienne,
            ).first()
            if (existante is not None and existante.candidatures.count() == 0
                    and not existante.classements.exists()):
                existante.delete()
                existante = None
                self.stdout.write(
                    '  Campagne historique vide remplacée par un exemple complet.')
            campagnes['historique'] = existante or self._creer_campagne(
                LIBELLE_CAMPAGNE_ANCIENNE, annee_precedente, formation_ancienne,
                aujourd_hui - timedelta(days=430), aujourd_hui + timedelta(days=30),
                quota_admissibles=3, quota_admis=2,
                transitions=[CS.PLANIFIEE, CS.OUVERTE], bilan=bilan,
            )
        return campagnes

    # ── candidatures et pièces ──────────────────────────────────────────────
    def _pieces_obligatoires(self, candidature):
        pieces = list(candidature.pieces.filter(obligatoire=True)
                      .select_related('type_piece'))
        return sorted(
            pieces,
            key=lambda p: (ORDRE_PIECES_OBLIGATOIRES.index(p.type_piece.code)
                           if p.type_piece.code in ORDRE_PIECES_OBLIGATOIRES
                           else 99),
        )

    def _deposer(self, piece, candidature, delivrance, expiration, bilan):
        numero_document = f'EXEMPLE-{piece.type_piece.code}-{candidature.numero}'
        contenu = pdf_exemple([
            'INJS — Institut National de la Jeunesse et des Sports',
            piece.type_piece.libelle,
            '',
            f'Dossier : {candidature.numero}',
            f'Candidat : {candidature.candidat}',
            f'Reference : {numero_document}',
            f'Date de delivrance : {delivrance.strftime("%d/%m/%Y")}',
            '',
            "Document d'exemple genere pour la demonstration du module",
            'Admissions & Candidatures. Aucune valeur officielle.',
        ])
        fichier = ContentFile(
            contenu,
            name=f'{piece.type_piece.code.lower()}-{candidature.numero.lower()}.pdf',
        )
        champs = {'numero_document': numero_document, 'date_delivrance': delivrance}
        if expiration is not None:
            champs['date_expiration'] = expiration
        services.deposer_piece(piece, fichier=fichier, acteur=self.acteur, **champs)
        bilan['pieces'] += 1

    def _remplir_pieces(self, candidature, profil, date_candidature, bilan):
        PS = PieceCandidature.Statut
        if profil == 'vides':
            return
        obligatoires = self._pieces_obligatoires(candidature)
        delivrance = date_candidature - timedelta(days=25)

        def expiration_pour(piece):
            if piece.type_piece.code == 'CERTIFICAT_MEDICAL':
                if profil == 'expiree':
                    return self.aujourdhui - timedelta(days=15)
                return delivrance + timedelta(days=365)
            if piece.type_piece.code == 'PIECE_IDENTITE':
                return delivrance + timedelta(days=1825)
            return None

        def deposer_et_valider(piece):
            self._deposer(piece, candidature, delivrance,
                          expiration_pour(piece), bilan)
            services.verifier_piece(piece, PS.VALIDEE, acteur=self.acteur)

        if profil in ('complet', 'expiree'):
            for piece in obligatoires:
                deposer_et_valider(piece)
            cv = candidature.pieces.filter(
                type_piece__code='CV', obligatoire=False,
            ).select_related('type_piece').first()
            if cv is not None:
                self._deposer(cv, candidature, delivrance, None, bilan)
                services.verifier_piece(cv, PS.VALIDEE, acteur=self.acteur)
            if profil == 'expiree':
                services.rafraichir_pieces_expirees(candidature)
        elif profil == 'deposees':
            for piece in obligatoires:
                self._deposer(piece, candidature, delivrance,
                              expiration_pour(piece), bilan)
        elif profil == 'partiel':
            for rang, piece in enumerate(obligatoires):
                if rang < 3:
                    deposer_et_valider(piece)
                elif rang < 5:
                    self._deposer(piece, candidature, delivrance,
                                  expiration_pour(piece), bilan)
                elif rang == 5:
                    self._deposer(piece, candidature, delivrance,
                                  expiration_pour(piece), bilan)
                    services.verifier_piece(
                        piece, PS.REFUSEE, acteur=self.acteur,
                        commentaire='Document illisible : merci de redéposer '
                                    'un scan net et complet.',
                    )
                # rang >= 6 : pièce laissée manquante

    def _candidatures(self, annee, campagnes, bilan):
        par_cle = {}
        types = {t.code: t for t in TypeCandidature.objects.all()}
        voies = {v.code: v for v in VoieAcces.objects.all()}
        niveaux = {n.code: n for n in Niveau.objects.all()}

        # (scénarios, année, campagne du groupe, premier rang, décalage de
        # date de dépôt en jours) — la cohorte historique est reculée d’un an.
        groupes = [
            (SCENARIOS, annee, campagnes.get('concours'), 1, 0),
            (SCENARIOS_HISTORIQUE, campagnes.get('annee_precedente'),
             campagnes.get('historique'), 21, 365),
            (SCENARIOS_SUSPENDUE, annee, campagnes.get('suspendue'), 27, 0),
            (SCENARIOS_ADMISSIONS, annee, None, 29, 0),
        ]
        for scenarios, annee_groupe, campagne_groupe, rang_depart, decalage in groupes:
            if annee_groupe is None:
                continue
            for rang_local, scenario in enumerate(scenarios, start=1):
                rang = rang_depart + rang_local - 1
                (nom, prenom, sexe, naissance, lieu, nationalite, filiere,
                 diplome, code_niveau, code_type, code_voie, profil,
                 statut_final, en_campagne, admission, observation) = scenario

                formation = self._formation(filiere, diplome)
                niveau = niveaux.get(code_niveau)
                if formation is None or niveau is None:
                    continue

                email = _slug_email(nom, prenom)
                candidat, _ = Candidat.objects.get_or_create(
                    email=email,
                    defaults={
                        'nom': nom, 'prenom': prenom, 'sexe': sexe,
                        'date_naissance': naissance, 'lieu_naissance': lieu,
                        'nationalite': nationalite,
                        'telephone': f'+225 07 00 00 01 {rang:02d}',
                        'adresse': f'{lieu} (adresse d’exemple)',
                    },
                )
                existante = Candidature.objects.filter(
                    candidat=candidat, annee_academique=annee_groupe,
                    ref_formation=formation, niveau=niveau,
                ).first()
                if existante is not None:
                    par_cle[rang] = existante
                    continue

                date_candidature = self.aujourdhui - timedelta(
                    days=55 - 2 * rang_local + decalage)
                parcours = Parcours.objects.filter(ref_formation=formation).first()
                candidature = services.creer_candidature(
                    candidat, acteur=self.acteur,
                    annee_academique=annee_groupe, ref_formation=formation,
                    niveau=niveau, parcours=parcours,
                    type_candidature=types.get(code_type),
                    voie_acces=voies.get(code_voie),
                    regime=self.regime,
                    campagne=campagne_groupe if en_campagne else None,
                    date_candidature=date_candidature,
                    observations=PREFIXE_OBSERVATION + observation,
                )
                bilan['candidatures'] += 1

                self._remplir_pieces(candidature, profil, date_candidature, bilan)
                for statut in CHEMINS[statut_final]:
                    workflow.appliquer_transition(
                        candidature, statut, acteur=self.acteur,
                        commentaire='Avancement du dossier (donnée d’exemple).',
                    )

                if admission is not None:
                    ligne = admission_services.creer_admission(
                        candidature, acteur=self.acteur,
                    )
                    bilan['admissions'] += 1
                    if admission != 'ouverte':
                        admission_services.prononcer_decision(
                            ligne, admission, acteur=self.acteur,
                            reference=f'DEC-ADM-{annee_groupe.libelle}-{rang:03d}',
                            date_limite=(self.aujourdhui + timedelta(days=45)
                                         if admission.startswith('ADMIS') else None),
                            observations=('Commission d’admission (donnée d’exemple).'
                                          if admission != 'REFUSEE'
                                          else 'Avis défavorable de la commission '
                                               'd’admission (donnée d’exemple).'),
                        )
                par_cle[rang] = candidature
        return par_cle

    # ── concours : épreuves, convocations, notes, classement ────────────────
    def _concours(self, campagne, par_cle, bilan):
        aujourd_hui = self.aujourdhui
        grande_salle = (
            RefSalle.objects.filter(actif=True, capacite__gte=20)
            .order_by('-capacite').select_related('site').first()
        )
        site = (grande_salle.site if grande_salle and grande_salle.site_id
                else RefSite.objects.filter(actif=True).order_by('id').first())

        def epreuve_ou_existante(intitule, **champs):
            objet, _ = Epreuve.objects.get_or_create(
                campagne=campagne, intitule=intitule, defaults=champs,
            )
            return objet

        ecrit = epreuve_ou_existante(
            'Écrit — Culture générale et sportive',
            type=Epreuve.Type.ECRIT, coefficient=Decimal('2'),
            date=aujourd_hui - timedelta(days=21),
            heure_debut=time(8, 0), duree_minutes=120,
            centre=site, salle=grande_salle,
        )
        physique = epreuve_ou_existante(
            'Tests physiques',
            type=Epreuve.Type.PHYSIQUE, coefficient=Decimal('3'),
            date=aujourd_hui - timedelta(days=14),
            heure_debut=time(7, 30), duree_minutes=180,
            centre=site, salle=None,
        )
        oral = epreuve_ou_existante(
            'Oral de motivation',
            type=Epreuve.Type.ORAL, coefficient=Decimal('1'),
            date=aujourd_hui + timedelta(days=10),
            heure_debut=time(9, 0), duree_minutes=30,
            centre=site, salle=grande_salle,
        )
        pratique = epreuve_ou_existante(
            'Épreuve pratique — Séance encadrée',
            type=Epreuve.Type.PRATIQUE, coefficient=Decimal('2'),
            date=aujourd_hui - timedelta(days=7),
            heure_debut=time(9, 0), duree_minutes=120,
            centre=site, salle=None,
        )

        for nom_utilisateur, epreuve in (
                ('superviseur1', ecrit), ('superviseur2', physique),
                ('superviseur1', oral), ('superviseur2', pratique)):
            surveillant = User.objects.filter(username=nom_utilisateur).first()
            if surveillant is not None:
                SurveillanceEpreuve.objects.get_or_create(
                    epreuve=epreuve, surveillant=surveillant,
                )

        if not NoteConcours.objects.filter(epreuve__campagne=campagne).exists():
            # Première alimentation (jamais réécrite ensuite : une saisie
            # réelle ne doit pas être écrasée par un rejeu de la commande).
            self._premiere_notation_em(
                campagne, ecrit, physique, oral, par_cle)

        # Épreuve pratique : convocations + saisie PARTIELLE des notes.
        if not NoteConcours.objects.filter(epreuve=pratique).exists():
            concours_services.generer_convocations(
                pratique, utilisateur=self.acteur)
            absent_pratique = par_cle.get(5)
            convocations = ConvocationEpreuve.objects.filter(epreuve=pratique)
            if absent_pratique is not None:
                convocations = convocations.exclude(candidature=absent_pratique)
            convocations.update(presente=True)
            for rang, note in NOTES_PRATIQUE.items():
                candidature = par_cle.get(rang)
                if candidature is not None:
                    self._assurer_convocation(pratique, candidature, presente=True)
                    concours_services.enregistrer_note(
                        pratique, candidature, utilisateur=self.acteur,
                        note=Decimal(note),
                    )
            self.stdout.write(
                '  Épreuve pratique : saisie partielle '
                f'({len(NOTES_PRATIQUE)} notes sur {len(NOTES_CONCOURS)}).')

        # Correction de note (historisée) sur une épreuve non verrouillée.
        candidature_corrigee = par_cle.get(2)
        note_a_corriger = NoteConcours.objects.filter(
            epreuve=physique, candidature=candidature_corrigee,
        ).first()
        if (note_a_corriger is not None
                and not note_a_corriger.historique.exists()):
            concours_services.enregistrer_note(
                physique, candidature_corrigee, utilisateur=self.acteur,
                note=Decimal('14.50'),
            )
            self.stdout.write(
                '  Correction de note appliquée (historique tracé).')

        # Recalcul du classement tant qu’il n’est pas publié.
        if not ClassementConcours.objects.filter(
                campagne=campagne, publie=True).exists():
            classement = concours_services.calculer_classement(
                campagne, utilisateur=self.acteur)
            self.stdout.write(
                f'  Concours « {campagne.libelle} » : classement recalculé '
                f'({len(classement)} candidat(s), non publié).')

    def _premiere_notation_em(self, campagne, ecrit, physique, oral, par_cle):
        for epreuve in (ecrit, physique, oral):
            concours_services.generer_convocations(epreuve, utilisateur=self.acteur)

        ConvocationEpreuve.objects.filter(epreuve=ecrit).update(presente=True)
        absent_sport = par_cle.get(3)
        convocations_sport = ConvocationEpreuve.objects.filter(epreuve=physique)
        if absent_sport is not None:
            convocations_sport = convocations_sport.exclude(candidature=absent_sport)
        convocations_sport.update(presente=True)

        for rang, (note_ecrit, note_physique) in NOTES_CONCOURS.items():
            candidature = par_cle.get(rang)
            if candidature is None:
                continue
            self._assurer_convocation(ecrit, candidature, presente=True)
            self._assurer_convocation(
                physique, candidature, presente=note_physique is not None)
            concours_services.enregistrer_note(
                ecrit, candidature, utilisateur=self.acteur,
                note=Decimal(note_ecrit),
            )
            concours_services.enregistrer_note(
                physique, candidature, utilisateur=self.acteur,
                note=Decimal(note_physique) if note_physique else None,
                absent=note_physique is None,
            )
        concours_services.verrouiller_epreuve(ecrit, utilisateur=self.acteur)

    def _assurer_convocation(self, epreuve, candidature, presente=False):
        """Convocation cohérente avec les notes (le générateur automatique
        ne convoque que certains statuts ; au jour de l’épreuve passée,
        tous les notés étaient convoqués)."""
        convocation, _ = ConvocationEpreuve.objects.get_or_create(
            epreuve=epreuve, candidature=candidature)
        if presente and not convocation.presente:
            convocation.presente = True
            convocation.save(update_fields=['presente'])
        return convocation

    # ── concours historique (année précédente) : publié puis clôturé ────────
    def _concours_historique(self, campagne, par_cle, bilan):
        aujourd_hui = self.aujourdhui
        grande_salle = (
            RefSalle.objects.filter(actif=True, capacite__gte=20)
            .order_by('-capacite').select_related('site').first()
        )
        site = (grande_salle.site if grande_salle and grande_salle.site_id
                else RefSite.objects.filter(actif=True).order_by('id').first())

        def epreuve_ou_existante(intitule, **champs):
            objet, _ = Epreuve.objects.get_or_create(
                campagne=campagne, intitule=intitule, defaults=champs)
            return objet

        epreuves = (
            epreuve_ou_existante(
                'Écrit — Anatomie et culture sportive',
                type=Epreuve.Type.ECRIT, coefficient=Decimal('2'),
                date=aujourd_hui - timedelta(days=365),
                heure_debut=time(8, 0), duree_minutes=120,
                centre=site, salle=grande_salle,
            ),
            epreuve_ou_existante(
                'Tests physiques',
                type=Epreuve.Type.PHYSIQUE, coefficient=Decimal('3'),
                date=aujourd_hui - timedelta(days=350),
                heure_debut=time(7, 30), duree_minutes=180,
                centre=site, salle=None,
            ),
            epreuve_ou_existante(
                'Épreuve pratique — Séance encadrée',
                type=Epreuve.Type.PRATIQUE, coefficient=Decimal('2'),
                date=aujourd_hui - timedelta(days=335),
                heure_debut=time(9, 0), duree_minutes=120,
                centre=site, salle=None,
            ),
        )
        for nom_utilisateur, epreuve in zip(
                ('superviseur1', 'superviseur2', 'superviseur1'), epreuves):
            surveillant = User.objects.filter(username=nom_utilisateur).first()
            if surveillant is not None:
                SurveillanceEpreuve.objects.get_or_create(
                    epreuve=epreuve, surveillant=surveillant)

        if not NoteConcours.objects.filter(epreuve__campagne=campagne).exists():
            for rang, notes in NOTES_HISTORIQUE.items():
                candidature = par_cle.get(rang)
                if candidature is None:
                    continue
                for epreuve, note in zip(epreuves, notes):
                    self._assurer_convocation(
                        epreuve, candidature, presente=note is not None)
                    concours_services.enregistrer_note(
                        epreuve, candidature, utilisateur=self.acteur,
                        note=Decimal(note) if note else None,
                        absent=note is None,
                    )
            for epreuve in epreuves:
                concours_services.verrouiller_epreuve(
                    epreuve, utilisateur=self.acteur)
            concours_services.calculer_classement(
                campagne, utilisateur=self.acteur)
            concours_services.publier_classement(
                campagne, utilisateur=self.acteur)
            self.stdout.write(
                f'  Concours « {campagne.libelle} » : classement publié '
                f'({len(NOTES_HISTORIQUE)} candidats).')

        # Dates définitives (fenêtre de l’année précédente) puis clôture.
        CampagneAdmission.objects.filter(pk=campagne.pk).update(
            date_ouverture=aujourd_hui - timedelta(days=430),
            date_fermeture=aujourd_hui - timedelta(days=390),
        )
        campagne.refresh_from_db()
        if campagne.statut == CampagneAdmission.Statut.OUVERTE:
            concours_services.appliquer_transition_campagne(
                campagne, CampagneAdmission.Statut.CLOTUREE,
                acteur=self.acteur,
                commentaire='Clôture après publication (donnée d’exemple).',
            )

    # ── complément admissions : décisions variées, inscrits, profils ───────
    def _referentiels_profil(self):
        """Catégorie/grade/vague pour les profils d'exemple.

        Les référentiels étudiants (corps d'appartenance) ne sont pas
        chargés par la chaîne de reconstruction : s'ils sont vides, on crée
        des valeurs explicitement marquées « (exemple) » — codes B3/A3/A4
        de la fonction publique ivoirienne — retirées par --purger. Si des
        valeurs réelles existent, elles sont utilisées sans rien créer.
        """
        categorie = RefCategorie.objects.filter(
            grades__isnull=False).order_by('id').first()
        if categorie is None:
            for libelle_cat, libelles_grades in CATEGORIES_EXEMPLE.items():
                cat, _ = RefCategorie.objects.get_or_create(libelle=libelle_cat)
                for libelle_grade in libelles_grades:
                    RefGrade.objects.get_or_create(
                        categorie=cat, libelle=libelle_grade)
            categorie = RefCategorie.objects.filter(
                libelle=next(iter(CATEGORIES_EXEMPLE))).first()
            self.stdout.write(
                '  Référentiels catégorie/grade d’exemple créés '
                '(retirés par --purger).')
        grade = (RefGrade.objects.filter(categorie=categorie).order_by('id').first()
                 if categorie is not None else None)
        vague = RefVague.objects.filter(actif=True).order_by('id').first()
        return categorie, grade, vague

    def _complement_admissions(self, par_cle, bilan):
        categorie, grade, vague = self._referentiels_profil()

        for rang, decision, delai, inscrire, annuler, profil in COMPLEMENT_ADMISSIONS:
            candidature = par_cle.get(rang)
            if candidature is None:
                continue
            admission = Admission.objects.filter(candidature=candidature).first()
            if admission is None:
                champs = {}
                if profil:
                    champs = {'categorie': categorie, 'grade': grade, 'vague': vague}
                admission = admission_services.creer_admission(
                    candidature, acteur=self.acteur, **champs)
                bilan['admissions'] += 1
                if decision is not None:
                    admission_services.prononcer_decision(
                        admission, decision, acteur=self.acteur,
                        reference=(
                            f'DEC-ADM-{candidature.annee_academique.libelle}-{rang:03d}'),
                        date_limite=(
                            self.aujourdhui + timedelta(days=delai)
                            if delai is not None and decision.startswith('ADMIS')
                            else None),
                        observations=(
                            'Commission d’admission (donnée d’exemple).'
                            if decision != 'REFUSEE'
                            else 'Avis défavorable de la commission '
                                 'd’admission (donnée d’exemple).'),
                    )
            if profil and admission.categorie_id is None and categorie is not None:
                admission.categorie = categorie
                admission.grade = grade
                if admission.vague_id is None:
                    admission.vague = vague
                admission.save(update_fields=['categorie', 'grade', 'vague'])
            if annuler and admission.decision != Admission.Decision.ANNULEE:
                admission_services.annuler_admission(
                    admission, acteur=self.acteur,
                    motif='Désistement du candidat (donnée d’exemple).')
            if inscrire:
                # Conversion nativement idempotente : un rejeu ne crée rien.
                inscription_services.convertir_admission_en_inscription(
                    admission, acteur=self.acteur, valider=True)

    # ── purge ───────────────────────────────────────────────────────────────
    def _purger(self):
        candidats = Candidat.objects.filter(email__endswith=DOMAINE_EXEMPLE)
        # Chaîne d'inscription des admis convertis : inscriptions, dossiers
        # étudiants puis participants (le participant est PROTECT par le
        # dossier, d'où cet ordre), avant les candidats eux-mêmes.
        participants_ids = list(candidats.exclude(participant=None)
                                .values_list('participant_id', flat=True))
        if participants_ids:
            InscriptionAdministrative.objects.filter(
                etudiant__participant_id__in=participants_ids).delete()
            DossierEtudiant.objects.filter(
                participant_id__in=participants_ids).delete()
            Participant.objects.filter(id__in=participants_ids).delete()
        pieces = PieceCandidature.objects.filter(
            candidature__candidat__in=candidats,
        ).exclude(fichier='')
        nb_fichiers = 0
        for piece in pieces:
            piece.fichier.delete(save=False)
            nb_fichiers += 1
        nb_candidats = candidats.count()
        candidats.delete()  # cascade : candidatures, pièces, admissions, notes…
        nb_campagnes, _ = CampagneAdmission.objects.filter(
            libelle__in=LIBELLES_CAMPAGNES,
        ).delete()
        nb_categories, _ = RefCategorie.objects.filter(
            libelle__in=CATEGORIES_EXEMPLE,
        ).delete()
        self.stdout.write(self.style.SUCCESS(
            f'Données d’exemple retirées : {nb_candidats} candidat(s) et '
            f'leurs dossiers, {nb_fichiers} fichier(s), '
            f'{nb_campagnes} campagne(s), {nb_categories} catégorie(s) '
            f'd’exemple.'
        ))
