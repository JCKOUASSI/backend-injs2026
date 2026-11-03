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

# ── Inscriptions administratives d'exemple (module « Inscriptions ») ─────────
# Étudiants créés directement (sans candidature) pour couvrir TOUTES les
# dimensions de l'écran : les 8 filières × Licence/Master, les niveaux L1→M2,
# les 6 types d'inscription, les 8 statuts du cycle de vie, les vagues, les
# catégories/grades de profil et les régimes d'études. Chaque inscription est
# portée sur l'année courante (les années clôturées refusent les validations)
# et suit la machine à états officielle (appliquer_transition).
# (nom/prenoms/sexe/année de naissance, filière, diplôme, niveau, type,
#  statut cible, vague n°, (rang catégorie, rang grade) ou None, régime)
INSCRIPTIONS_DEMO = [
    (('Konan', 'Yao Jean-Marc', 'M', 2006), 'F01', 'LICENCE', 'L1', 'PREMIERE', 'VALIDEE', 1, (1, 0), 'INITIAL'),
    (('Diallo', 'Fatoumata', 'F', 2005), 'F02', 'LICENCE', 'L1', 'PREMIERE', 'VALIDEE', 1, (0, 0), 'INITIAL'),
    (('Touré', 'Ibrahim', 'M', 2006), 'F03', 'LICENCE', 'L1', 'PREMIERE', 'EN_ATTENTE', 2, None, 'INITIAL'),
    (('Kacou', 'Affoué Nadia', 'F', 2005), 'F04', 'LICENCE', 'L1', 'PREMIERE', 'A_VALIDER', 2, (1, 1), 'INITIAL'),
    (('Yao', 'Kouadio Olivier', 'M', 2006), 'F05', 'LICENCE', 'L1', 'PREMIERE', 'BROUILLON', None, None, 'INITIAL'),
    (('Bamba', 'Tenin', 'F', 1999), 'F06', 'LICENCE', 'L1', 'PREMIERE', 'VALIDEE', 3, None, 'PROFESSIONNEL'),
    (('Gbocho', 'Guy Martial', 'M', 2005), 'F07', 'LICENCE', 'L1', 'PREMIERE', 'REJETEE', None, None, 'INITIAL'),
    (('Sylla', 'Mariam', 'F', 2001), 'F08', 'LICENCE', 'L1', 'PREMIERE', 'VALIDEE', 1, (0, 0), 'CONTINU'),
    (('Oka', 'Jean Emmanuel', 'M', 2004), 'F01', 'LICENCE', 'L2', 'REINSCRIPTION', 'VALIDEE', 1, (1, 0), 'INITIAL'),
    (('Sangaré', 'Mory', 'M', 2004), 'F03', 'LICENCE', 'L2', 'REINSCRIPTION', 'VALIDEE', None, None, 'INITIAL'),
    (('Aka', 'Kouakou Guy', 'M', 2004), 'F04', 'LICENCE', 'L2', 'REDOUBLEMENT', 'EN_ATTENTE', None, None, 'INITIAL'),
    (('Bakayoko', 'Salimata', 'F', 2003), 'F06', 'LICENCE', 'L2', 'REINSCRIPTION', 'SUSPENDUE', None, None, 'INITIAL'),
    (('Toh', 'Olivia', 'F', 2003), 'F02', 'LICENCE', 'L3', 'REINSCRIPTION', 'VALIDEE', 1, (1, 0), 'INITIAL'),
    (('Dié', 'Alain', 'M', 2002), 'F05', 'LICENCE', 'L3', 'REINSCRIPTION', 'TERMINEE', None, None, 'INITIAL'),
    (('Doumbia', 'Makan', 'M', 2003), 'F07', 'LICENCE', 'L3', 'REPRISE', 'VALIDEE', None, None, 'INITIAL'),
    (('Gnagne', 'Prisca Emmanuelle', 'F', 2002), 'F02', 'MASTER', 'M1', 'PREMIERE', 'VALIDEE', 1, (1, 1), 'INITIAL'),
    (('Coumba', 'El Hadj', 'M', 2002), 'F03', 'MASTER', 'M1', 'PREMIERE', 'A_VALIDER', 2, None, 'INITIAL'),
    (('Ouédraogo', 'Bernice', 'F', 2000), 'F05', 'MASTER', 'M1', 'PREMIERE', 'VALIDEE', None, (0, 0), 'ALTERNANCE'),
    (('Kande', 'Hawa', 'F', 2001), 'F08', 'MASTER', 'M1', 'PREMIERE', 'ANNULEE', None, None, 'CONTINU'),
    (('Mahamadou', 'Souley', 'M', 2001), 'F01', 'MASTER', 'M2', 'REINSCRIPTION', 'VALIDEE', 1, (1, 0), 'INITIAL'),
    (('Loris', 'Cheick Ahmed', 'M', 2000), 'F04', 'MASTER', 'M2', 'TRANSFERT', 'VALIDEE', None, (1, 1), 'INITIAL'),
    (('Diawara', 'Adjaratou', 'F', 2001), 'F06', 'MASTER', 'M2', 'REORIENTATION', 'EN_ATTENTE', None, None, 'INITIAL'),
    (('Gassama', 'Yakhouba', 'M', 2001), 'F07', 'MASTER', 'M2', 'REINSCRIPTION', 'VALIDEE', None, (0, 0), 'INITIAL'),
    (('Kone', 'Tiemoko', 'M', 2000), 'F08', 'MASTER', 'M2', 'REDOUBLEMENT', 'BROUILLON', None, None, 'CONTINU'),
]

CHEMINS_INSCRIPTIONS = {
    'BROUILLON': [],
    'EN_ATTENTE': ['EN_ATTENTE'],
    'A_VALIDER': ['EN_ATTENTE', 'A_VALIDER'],
    'VALIDEE': ['EN_ATTENTE', 'A_VALIDER', 'VALIDEE'],
    'REJETEE': ['EN_ATTENTE', 'REJETEE'],
    'ANNULEE': ['ANNULEE'],
    'SUSPENDUE': ['EN_ATTENTE', 'A_VALIDER', 'VALIDEE', 'SUSPENDUE'],
    'TERMINEE': ['EN_ATTENTE', 'A_VALIDER', 'VALIDEE', 'TERMINEE'],
}




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


# ── Effectifs étudiants d'exemple (module « Étudiants ») ─────────────────────
# Registre complet de 3 500 étudiants — parité femmes/hommes exacte — répartis
# sur les 8 filières × Licence/Master et les niveaux L1→M2, avec grades de la
# fonction publique pour les étudiants fonctionnaires, groupes pédagogiques,
# vagues, types de concours et secrétariats (exemple). Génération
# déterministe (graine fixe) et création en masse (bulk_create) ; chaque
# étudiant possède candidat @exemple.ci (purge), participant (matricule),
# dossier étudiant et inscription VALIDEE sur l'année courante.
EFFECTIF_CIBLE = 3500
POIDS_NIVEAUX = {'L1': 0.30, 'L2': 0.22, 'L3': 0.18, 'M1': 0.17, 'M2': 0.13}
PROBA_FONCTIONNAIRE = {'L1': 0.08, 'L2': 0.10, 'L3': 0.12, 'M1': 0.55, 'M2': 0.60}
GRADES_FP = [
    ('A4', 0.06), ('A3', 0.14), ('A2', 0.12), ('A1', 0.10),
    ('B3', 0.16), ('B2', 0.12), ('B1', 0.08),
    ('C3', 0.08), ('C2', 0.07), ('C1', 0.05), ('D1', 0.02),
]
NOMS_EFFECTIFS = [
    'Abé', 'Aboa', 'Aboua', 'Achi', 'Adjé', 'Adjoussou',
    'Adom', 'Adou', 'Adoubi', 'Affian', 'Ahoussou', 'Aka',
    'Akaffou', 'Allou', 'Aman', 'Amara', 'Amani', 'Assemien',
    'Assi', 'Assié', 'Atta', 'Ayé', 'Ayémou', 'Bah',
    'Bakayoko', 'Bamba', 'Berté', 'Blé', 'Bouabré', 'Brou',
    'Camara', 'Cissé', 'Coulibaly', 'Dadié', 'Dagbo', 'Dago',
    'Diallo', 'Diabaté', 'Diakité', 'Dié', 'Diomandé', 'Diawara',
    'Doué', 'Doumbia', 'Dramé', 'Ehouman', 'Ekissi', 'Fofana',
    'Gassama', 'Glé', 'Gnagne', 'Guéï', 'Kacou', 'Kadio',
    'Kadjo', 'Kamara', 'Kamagate', 'Kanaté', 'Kande', 'Kanté',
    'Keïta', 'Koffi', 'Komenan', 'Konan', 'Konaté', 'Koné',
    'Kouadio', 'Kouadio Koné', 'Kouakou', 'Kouadio', 'Kouassi', 'Loris',
    'Mahamadou', 'Maho', "N'Dri", "N'Goran", "N'Guessan", 'Ouattara',
    'Ouédraogo', 'Oka', 'Sangaré', 'Sanogo', 'Savané', 'Séry',
    'Sidibé', 'Silué', 'Sissoko', 'Soro', 'Soumahoro', 'Sylla',
    'Tanoh', 'Toh', 'Touré', 'Traoré', 'Yao', 'Yéo',
    'Zadi', 'Zahoui', 'Zamblé',
]

PRENOMS_F_EFFECTIFS = [
    'Adjaratou', 'Adjoua', 'Affoué', 'Aïcha', 'Aïchata', 'Aïchatou',
    'Aïda', 'Aïssa', 'Aïssata', 'Aïssatou', 'Akissi', 'Amenan',
    'Aminata', 'Awa', 'Aya', 'Bernadette', 'Bernice', 'Blandine',
    'Christelle', 'Clarisse', 'Deborah', 'Diane', 'Edith', 'Emmanuelle',
    'Esther', 'Evelyne', 'Fatou', 'Fatoumata', 'Flore', 'Gisèle',
    'Grâce', 'Hawa', 'Hélène', 'Honorine', 'Inès', 'Jacqueline',
    'Jeanne', 'Josiane', 'Judith', 'Kadidja', 'Kadiatou', 'Karidja',
    'Larissa', 'Laure', 'Linda', 'Maïmouna', 'Mariam', 'Mariama',
    'Marie', 'Marina', 'Martine', 'Mélanie', 'Mireille', 'Monique',
    'Nadia', 'Nadège', 'Nafissatou', 'Nathalie', 'Nicole', 'Nina',
    'Olivia', 'Oumou', 'Patricia', 'Pauline', 'Prisca', 'Rachel',
    'Rama', 'Ramata', 'Reine', 'Rita', 'Rokia', 'Rosine',
    'Ruth', 'Safiatou', 'Salimata', 'Sandra', 'Sandrine', 'Sara',
    'Saran', 'Séverine', 'Sidonie', 'Simone', 'Sophie', 'Stéphanie',
    'Suzanne', 'Tenin', 'Thérèse', 'Vanessa', 'Véronique', 'Viviane',
    'Yasmina', 'Yolande', 'Yvette',
]

PRENOMS_M_EFFECTIFS = [
    'Abdoulaye', 'Abou', 'Abraham', 'Adam', 'Adama', 'Alain',
    'Albert', 'Alexandre', 'Alfred', 'Ali', 'Aliou', 'Alphonse',
    'Amadou', 'Ambroise', 'Amos', 'André', 'Ange', 'Antoine',
    'Armand', 'Armel', 'Arnaud', 'Arsène', 'Arthur', 'Auguste',
    'Augustin', 'Aurélien', 'Bakary', 'Basile', 'Benjamin', 'Benoît',
    'Bernard', 'Bertrand', 'Blaise', 'Boris', 'Boubacar', 'Brahima',
    'Brice', 'Bruno', 'Casimir', 'Charles', 'Cheick', 'Christian',
    'Christophe', 'Claude', 'Clément', 'Constant', 'Cyrille', 'Cédric',
    'Damien', 'Daniel', 'Daouda', 'David', 'Denis', 'Didier',
    'Dieudonné', 'Djibril', 'Dominique', 'Désiré', 'Edmond', 'Edouard',
    'Elie', 'Emmanuel', 'Eric', 'Ernest', 'Etienne', 'Eugène',
    'Fabrice', 'Fernand', 'Florent', 'Franck', 'François', 'Frédéric',
    'Félix', 'Gabriel', 'Gaël', 'Gaston', 'Georges', 'Germain',
    'Gilbert', 'Gilles', 'Gildas', 'Grégoire', 'Guillaume', 'Guy',
    'Habib', 'Hamadou', 'Hamed', 'Hamidou', 'Hamza', 'Harouna',
    'Hassan', 'Ibrahim', 'Ibrahima', 'Idrissa', 'Ignace', 'Ilyas',
    'Innocent', 'Isaac', 'Ismaël', 'Jacob', 'Jacques', 'Jean',
    'Jean-Baptiste', 'Jean-Marc', 'Jean-Marie', 'Jean-Paul', 'Jean-Pierre', 'Jean-Yves',
    'Joachim', 'Jonathan', 'Joseph', 'Josias', 'Joël',
]

VILLES_EFFECTIFS = [
    'Abidjan', 'Bouaké', 'Yamoussoukro', 'Korhogo', 'Man', 'San-Pédro',
    'Daloa', 'Gagnoa', 'Abengourou', 'Grand-Bassam', 'Aboisso', 'Agboville',
    'Divo', 'Soubré', 'Odienné', 'Bondoukou', 'Ferkessédougou', 'Oumé',
    'Sinfra', 'Katiola', 'Daoukro', 'Toumodi', 'Lakota', 'Guiglo',
    'Duékoué',
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

        bilan = {'campagnes': 0, 'candidatures': 0, 'pieces': 0, 'admissions': 0,
                 'inscriptions': 0, 'etudiants': 0, 'groupes': 0,
                 'affectations': 0}
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
            self._inscriptions_demo(annee, par_cle, bilan)
            self._effectifs_etudiants(annee, bilan)
            self._groupes_demo(annee, bilan)

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
        nb_groupes_demo = 0
        if participants_ids:
            from scolarite.models import AffectationGroupe, Groupe
            groupes_demo_ids = list(AffectationGroupe.objects.filter(
                inscription__etudiant__participant_id__in=participants_ids,
            ).values_list('groupe_id', flat=True).distinct())
            InscriptionAdministrative.objects.filter(
                etudiant__participant_id__in=participants_ids).delete()
            # Les affectations ont suivi en cascade : les groupes qui ne
            # portaient que des étudiants d'exemple peuvent être retirés,
            # ainsi que les groupes inactifs vides au nom généré (L1-G3…).
            nb_groupes_demo, _ = Groupe.objects.filter(
                id__in=groupes_demo_ids).delete()
            nb_vides, _ = Groupe.objects.filter(
                affectations__isnull=True,
                nom__regex=r'^[LM][0-9]-G[0-9]+$',
            ).delete()
            nb_groupes_demo += nb_vides
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
        from formations.models import Secretariat as _Secretariat
        nb_secretariats, _ = _Secretariat.objects.filter(
            numero__startswith='SEC-EXEMPLE-',
        ).delete()
        self.stdout.write(self.style.SUCCESS(
            f'Données d’exemple retirées : {nb_candidats} candidat(s) et '
            f'leurs dossiers, {nb_fichiers} fichier(s), '
            f'{nb_campagnes} campagne(s), {nb_categories} catégorie(s), '
            f'{nb_secretariats} secrétariat(s), '
            f'{nb_groupes_demo} groupe(s) pédagogique(s) '
            f'd’exemple.'
        ))

    # ── Inscriptions administratives d'exemple ────────────────────────────────
    def _inscriptions_demo(self, annee, par_cle, bilan):
        """Inscriptions couvrant toutes les dimensions du module, plus une
        conversion d'admission supplémentaire (rang 8, ADMIS en Master).

        Les étudiants sont créés par les services métier (participant →
        dossier), le matricule reflétant leur année d'entrée (L1/M1 = année
        courante, L2/M2 = année précédente, L3 = deux ans avant)."""
        from scolarite import inscription_services
        from scolarite.models import (
            DossierEtudiant, InscriptionAdministrative, JournalScolarite,
            Niveau, Parcours, StatutEtudiant, journaliser,
        )

        vagues = list(RefVague.objects.filter(actif=True).order_by('id'))
        regimes = {r.code: r for r in RegimeEtudes.objects.all()}
        niveaux = {n.code: n for n in Niveau.objects.all()}
        statut_actif = StatutEtudiant.objects.filter(code='ACTIF').first()
        self._referentiels_profil()  # garantit l'existence des (exemple)
        # Rang 0 = catégorie B, rang 1 = catégorie A (tri décroissant des
        # libellés d'exemple) ; les grades suivent l'ordre de création.
        categories = list(RefCategorie.objects.filter(
            grades__isnull=False).distinct().order_by('-libelle', 'id'))
        # Années d'entrée déduites de l'année courante (« 2026-2027 »…).
        try:
            debut = int(str(annee.libelle)[:4])
        except (TypeError, ValueError):
            debut = None

        for rang, (identite, code_filiere, diplome, code_niveau, type_insc,
                   statut_cible, n_vague, profil, code_regime) in enumerate(
                       INSCRIPTIONS_DEMO, start=1):
            nom, prenoms, sexe, annee_naissance = identite
            formation = self._formation(code_filiere, diplome)
            niveau = niveaux.get(code_niveau)
            if formation is None or niveau is None:
                self.stdout.write(self.style.WARNING(
                    f'Inscription d’exemple n°{rang} ignorée : formation ou '
                    f'niveau introuvable ({code_filiere}/{diplome}/{code_niveau}).'
                ))
                continue
            candidat, _ = Candidat.objects.get_or_create(
                email=_slug_email(nom, prenoms),
                defaults={
                    'nom': nom, 'prenom': prenoms, 'sexe': sexe,
                    'date_naissance': date(annee_naissance, (rang % 12) + 1,
                                           (rang % 27) + 1),
                    'telephone': f'07 {40 + rang:02d} {10 + rang:02d} 60 {rang:02d}',
                },
            )
            decalage = {'L1': 0, 'M1': 0, 'L2': 1, 'M2': 1, 'L3': 2}.get(code_niveau, 0)
            annee_entree = annee
            if decalage and debut:
                libelle_entree = f'{debut - decalage}-{debut - decalage + 1}'
                annee_entree = (AnneeAcademique.objects
                                .filter(libelle=libelle_entree).first() or annee)
            participant, _ = inscription_services.creer_ou_retrouver_participant(
                candidat, annee_entree, acteur=self.acteur)
            dossier, _ = inscription_services.creer_ou_retrouver_dossier(
                participant, acteur=self.acteur)
            if InscriptionAdministrative.objects.filter(
                    etudiant=dossier, annee_academique=annee).exists():
                continue

            categorie = grade = None
            if profil is not None and categories:
                rang_cat, rang_grade = profil
                if rang_cat < len(categories):
                    categorie = categories[rang_cat]
                    grades = list(categorie.grades.order_by('id'))
                    if rang_grade < len(grades):
                        grade = grades[rang_grade]
            vague = vagues[n_vague - 1] if n_vague and n_vague <= len(vagues) else None
            inscription = InscriptionAdministrative(
                etudiant=dossier, annee_academique=annee,
                ref_formation=formation,
                parcours=Parcours.objects.filter(
                    ref_formation=formation).order_by('id').first(),
                niveau=niveau, vague=vague, categorie=categorie, grade=grade,
                regime=regimes.get(code_regime), statut_etudiant=statut_actif,
                type_inscription=type_insc,
                date_inscription=self.aujourdhui - timedelta(days=(rang % 20) + 1),
                observations=(
                    f'[Exemple] Dossier de démonstration — {diplome} '
                    f'{code_niveau}, {type_insc.lower().replace("_", " ")}.'
                ),
            )
            try:
                inscription.full_clean(exclude=['date_validation'])
            except ValidationError as erreur:
                self.stdout.write(self.style.WARNING(
                    f'Inscription d’exemple n°{rang} ignorée : {erreur.messages}'
                ))
                continue
            inscription.save()
            journaliser(
                JournalScolarite.Action.INSCRIPTION_CREEE, objet=inscription,
                acteur=self.acteur, commentaire='[Exemple] Dossier d’inscription.',
            )
            for etape in CHEMINS_INSCRIPTIONS[statut_cible]:
                inscription_services.appliquer_transition(
                    inscription, etape, acteur=self.acteur,
                    commentaire='[Exemple] Avancement du dossier.',
                )
            bilan['inscriptions'] += 1

        # Une 3ᵉ inscription issue des admissions (Touré Mamadou, rang 8, ADMIS
        # Master Entraînement Sportif) — conversion idempotente.
        from admissions.models import Admission

        candidature8 = par_cle.get(8)
        if candidature8 is not None:
            admission8 = Admission.objects.filter(
                candidature=candidature8).first()
            if admission8 is not None and admission8.permet_inscription:
                inscrit_avant = InscriptionAdministrative.objects.count()
                inscription8 = \
                    inscription_services.convertir_admission_en_inscription(
                        admission8, acteur=self.acteur)
                for etape in ['EN_ATTENTE', 'A_VALIDER', 'VALIDEE']:
                    if inscription8.statut != 'VALIDEE':
                        try:
                            inscription_services.appliquer_transition(
                                inscription8, etape, acteur=self.acteur,
                                commentaire='[Exemple] Validation du dossier.',
                            )
                        except inscription_services.InscriptionImpossible:
                            break
                if InscriptionAdministrative.objects.count() > inscrit_avant:
                    bilan['inscriptions'] += 1

        self.stdout.write(self.style.SUCCESS(
            f'Inscriptions administratives d’exemple : '
            f'{bilan["inscriptions"]} inscription(s) créée(s) (toutes filières, '
            f'niveaux, types et statuts représentés).'
        ))


    # ── Effectifs étudiants (3 500, parité exacte) ────────────────────────────
    def _effectifs_etudiants(self, annee, bilan):
        """Registre complet d'étudiants d'exemple, créé en masse.

        Répartition : 8 filières × (L1/L2/L3 + M1/M2) selon POIDS_NIVEAUX ;
        sexes alternés → parité femmes/hommes exacte. Les étudiants
        fonctionnaires (surtout en Master) portent catégorie/grade de la
        fonction publique ; groupes de ~40 par cohorte ; vagues pour les
        entrants ; secrétariats (exemple) par cycle. Idempotent par e-mail.
        """
        import random
        from datetime import datetime

        from django.utils import timezone as _tz

        from formations.models import Secretariat
        from scolarite.models import Niveau

        rng = random.Random(20261102)
        aujourdhui = self.aujourdhui
        try:
            debut_courante = int(str(annee.libelle)[:4])
        except (TypeError, ValueError):
            debut_courante = aujourdhui.year

        niveaux = {n.code: n for n in Niveau.objects.all()}
        regimes = {r.code: r for r in RegimeEtudes.objects.all()}
        vagues = list(RefVague.objects.filter(actif=True).order_by('id'))
        libelles_vague = [v.libelle for v in vagues] or [
            'PREMIERE VAGUE', 'DEUXIEME VAGUE', 'TROISIEME VAGUE']
        statut_actif = None
        from scolarite.models import StatutEtudiant as _StatutEtudiant
        statut_actif = _StatutEtudiant.objects.filter(code='ACTIF').first()
        self._referentiels_profil()
        categories_ref = {
            c.libelle[10]: c for c in RefCategorie.objects.filter(
                grades__isnull=False).distinct()
            if len(c.libelle) > 10
        }

        secretariats = {}
        for cle, nom_complet in [
            ('LICENCE', 'Secrétariat des Études — Licence (exemple)'),
            ('MASTER', 'Secrétariat des Études — Master (exemple)'),
            ('CONTINUE', 'Secrétariat de la Formation Continue (exemple)'),
        ]:
            secretariats[cle], _ = Secretariat.objects.get_or_create(
                numero=f'SEC-EXEMPLE-{cle}', defaults={'nom': nom_complet})

        # ── Cohortes : (formation, code niveau, diplôme, effectif) ───────────
        codes_filieres = [f'F0{i}' for i in range(1, 9)]
        cohortes = []
        for code_niveau, poids in POIDS_NIVEAUX.items():
            diplome = 'LICENCE' if code_niveau.startswith('L') else 'MASTER'
            total_niveau = round(EFFECTIF_CIBLE * poids)
            part, reste = divmod(total_niveau, len(codes_filieres))
            for rang_f, code_filiere in enumerate(codes_filieres):
                effectif = part + (1 if rang_f < reste else 0)
                formation = self._formation(code_filiere, diplome)
                if formation is None or code_niveau not in niveaux:
                    continue
                cohortes.append([formation, code_niveau, diplome, effectif])
        ecart = EFFECTIF_CIBLE - sum(c[3] for c in cohortes)
        if cohortes and ecart:
            max(cohortes, key=lambda c: c[3])[3] += ecart

        # ── Identités déterministes (parité stricte) ─────────────────────────
        emails_existants = set(
            Candidat.objects.filter(email__endswith=DOMAINE_EXEMPLE)
            .values_list('email', flat=True))
        # Prochain numéro de matricule par préfixe d'année d'entrée.
        prochains = {}
        for matricule_existant in Participant.objects.values_list(
                'matricule', flat=True):
            morceaux = str(matricule_existant).split('-')
            if len(morceaux) == 2 and morceaux[0].startswith('INJS') \
                    and morceaux[1].isdigit():
                prefixe = morceaux[0]
                prochains[prefixe] = max(
                    prochains.get(prefixe, 0), int(morceaux[1]))

        def matricule_suivant(annee_entree_debut):
            prefixe = f'INJS{annee_entree_debut % 100:02d}'
            prochains[prefixe] = prochains.get(prefixe, 0) + 1
            return f'{prefixe}-{prochains[prefixe]:04d}'

        def choix_grade_fp():
            tirage, cumul = rng.random(), 0.0
            for grade, proba in GRADES_FP:
                cumul += proba
                if tirage <= cumul:
                    return grade
            return 'B3'

        decalages = {'L1': 0, 'M1': 0, 'L2': 1, 'M2': 1, 'L3': 2}
        ages_base = {'L1': 18, 'L2': 19, 'L3': 20, 'M1': 22, 'M2': 23}
        participants, liens = [], []  # (participant, cohorte, méta inscription)
        indice = 0
        for formation, code_niveau, diplome, effectif in cohortes:
            liste_parcours = list(Parcours.objects.filter(
                ref_formation=formation).order_by('id'))
            for rang_cohorte in range(effectif):
                indice += 1
                sexe = 'F' if indice % 2 == 0 else 'M'
                nom = rng.choice(NOMS_EFFECTIFS)
                prenoms_pool = PRENOMS_F_EFFECTIFS if sexe == 'F' \
                    else PRENOMS_M_EFFECTIFS
                prenom = rng.choice(prenoms_pool)
                if rng.random() < 0.3:
                    prenom = f'{prenom} {rng.choice(prenoms_pool)}'
                base_email = _slug_email(nom, prenom).removesuffix(DOMAINE_EXEMPLE)
                email = f'{base_email}.{indice}{DOMAINE_EXEMPLE}'
                fonctionnaire = rng.random() < PROBA_FONCTIONNAIRE[code_niveau]
                grade_fp = choix_grade_fp() if fonctionnaire else ''
                age = ages_base[code_niveau] + rng.randint(0, 3)
                if fonctionnaire:
                    age += rng.randint(3, 14)
                naissance = date(
                    aujourdhui.year - age, rng.randint(1, 12), rng.randint(1, 28))
                annee_entree = debut_courante - decalages[code_niveau]
                entrant = code_niveau in ('L1', 'M1')
                if fonctionnaire:
                    type_concours = ('Concours professionnel'
                                     if rng.random() < 0.6
                                     else 'Examen professionnel')
                else:
                    type_concours = 'Concours direct'
                vague_str = vague_obj = ''
                vague_obj = None
                if entrant:
                    tirage_vague = rng.random()
                    rang_vague = 0 if tirage_vague < 0.6 else (
                        1 if tirage_vague < 0.85 else 2)
                    vague_str = libelles_vague[min(rang_vague, len(libelles_vague) - 1)]
                    if rang_vague < len(vagues):
                        vague_obj = vagues[rang_vague]
                groupe = f"Groupe {chr(65 + rang_cohorte // 40)}"
                if fonctionnaire:
                    secretariat = secretariats['CONTINUE']
                elif diplome == 'MASTER':
                    secretariat = secretariats['MASTER']
                else:
                    secretariat = secretariats['LICENCE']
                telephone = (
                    f"{rng.choice(['07', '05', '01'])} {rng.randint(0, 99):02d} "
                    f"{rng.randint(0, 99):02d} {rng.randint(0, 99):02d} "
                    f"{rng.randint(0, 99):02d}")
                participant = Participant(
                    matricule=matricule_suivant(annee_entree),
                    nom=nom.upper(), prenom=prenom,
                    sexe='FEMININ' if sexe == 'F' else 'MASCULIN',
                    date_naissance=naissance,
                    lieu_naissance=rng.choice(VILLES_EFFECTIFS),
                    email=email, telephone=telephone,
                    type_concours=type_concours,
                    libelle_concours=f'{type_concours} {annee_entree}',
                    categorie=f'Catégorie {grade_fp[0]}' if grade_fp else '',
                    grade=grade_fp, groupe=groupe,
                    grade_groupe=(f'{grade_fp} · {groupe}' if grade_fp
                                  else groupe),
                    vague=vague_str, secretariat=secretariat,
                )
                participants.append(participant)
                liens.append({
                    'participant': participant, 'nom': nom, 'prenom': prenom,
                    'sexe': sexe, 'email': email, 'naissance': naissance,
                    'telephone': telephone,
                    'formation': formation, 'code_niveau': code_niveau,
                    'parcours': (liste_parcours[rang_cohorte % len(liste_parcours)]
                                 if liste_parcours else None),
                    'vague': vague_obj, 'grade_fp': grade_fp,
                    'fonctionnaire': fonctionnaire, 'entrant': entrant,
                    'annee_entree': annee_entree,
                })

        # Idempotence : le filtrage a lieu APRÈS la génération complète des
        # identités (sinon les tirages aléatoires se désynchronisent et les
        # e-mails régénérés ne correspondent plus à ceux déjà en base).
        paires = [(part, lien) for part, lien in zip(participants, liens)
                  if lien['email'] not in emails_existants]
        participants = [part for part, _ in paires]
        liens = [lien for _, lien in paires]

        if not participants:
            self.stdout.write(
                'Effectifs étudiants d’exemple déjà présents (aucun ajout).')
            return

        Participant.objects.bulk_create(participants, batch_size=500)
        Candidat.objects.bulk_create([
            Candidat(
                nom=lien['nom'], prenom=lien['prenom'], sexe=lien['sexe'],
                date_naissance=lien['naissance'], email=lien['email'],
                telephone=lien['telephone'],
                participant=lien['participant'],
            ) for lien in liens
        ], batch_size=500)
        dossiers = [
            DossierEtudiant(
                participant=lien['participant'], statut=statut_actif,
                date_premiere_inscription=date(lien['annee_entree'], 9, 15),
            ) for lien in liens
        ]
        DossierEtudiant.objects.bulk_create(dossiers, batch_size=500)

        grades_ref_par_cat = {}
        for lettre, cat in categories_ref.items():
            grades_ref_par_cat[lettre] = list(cat.grades.order_by('id'))

        inscriptions = []
        for lien, dossier in zip(liens, dossiers):
            categorie_ref = grade_ref = None
            lettre = lien['grade_fp'][:1]
            if lettre in grades_ref_par_cat and grades_ref_par_cat[lettre]:
                categorie_ref = categories_ref[lettre]
                liste_g = grades_ref_par_cat[lettre]
                # A4 → dernier grade ; sinon premier grade de la catégorie.
                grade_ref = liste_g[-1] if lien['grade_fp'] == 'A4' else liste_g[0]
            if lien['fonctionnaire']:
                regime = regimes.get(
                    'CONTINU' if rng.random() < 0.6 else 'PROFESSIONNEL')
            elif lien['code_niveau'] in ('M1', 'M2') and rng.random() < 0.1:
                regime = regimes.get('ALTERNANCE')
            else:
                regime = regimes.get('INITIAL')
            type_insc = 'PREMIERE' if lien['entrant'] else (
                'REDOUBLEMENT' if rng.random() < 0.04 else 'REINSCRIPTION')
            date_insc = date(debut_courante, 9, 1) + timedelta(
                days=rng.randint(0, 45))
            inscriptions.append(InscriptionAdministrative(
                etudiant=dossier, annee_academique=annee,
                ref_formation=lien['formation'], parcours=lien['parcours'],
                niveau=niveaux[lien['code_niveau']], vague=lien['vague'],
                categorie=categorie_ref, grade=grade_ref, regime=regime,
                statut_etudiant=statut_actif, type_inscription=type_insc,
                statut=InscriptionAdministrative.Statut.VALIDEE,
                date_inscription=date_insc,
                date_validation=_tz.make_aware(datetime.combine(
                    date_insc + timedelta(days=rng.randint(1, 10)),
                    datetime.min.time().replace(hour=10))),
                valide_par=self.acteur,
                observations='[Exemple] Effectif de démonstration.',
            ))
        InscriptionAdministrative.objects.bulk_create(
            inscriptions, batch_size=500)
        bilan['etudiants'] += len(participants)
        self.stdout.write(self.style.SUCCESS(
            f'Effectifs étudiants d’exemple : {len(participants)} étudiant(s) '
            f'créé(s) (parité femmes/hommes, 8 filières, niveaux L1→M2).'
        ))

    # ── Groupes pédagogiques d'exemple ────────────────────────────────────────
    def _groupes_demo(self, annee, bilan):
        """Sections TD/TP de toutes les cohortes (formation × niveau).

        Groupes « L1-G1 »… de capacité 30/35/40 remplis à ~90 %, une cohorte
        sans limite de capacité, deux groupes inactifs (fermés) et ~2 %
        d'étudiants volontairement non affectés pour que la répartition
        automatique de l'écran reste démontrable. Création en masse,
        idempotente (les inscriptions déjà affectées sont conservées).
        """
        import math

        from scolarite.models import AffectationGroupe, Groupe

        inscriptions = list(
            InscriptionAdministrative.objects.filter(
                annee_academique=annee,
                statut=InscriptionAdministrative.Statut.VALIDEE,
            ).order_by('ref_formation_id', 'niveau_id', 'id'))
        deja_affectees = set(AffectationGroupe.objects.filter(
            active=True,
            inscription__annee_academique=annee,
        ).values_list('inscription_id', flat=True))

        cohortes = {}
        for inscription in inscriptions:
            cle = (inscription.ref_formation_id, inscription.niveau_id)
            cohortes.setdefault(cle, []).append(inscription)

        capacites_cycle = [35, 30, 40, 35]
        affectations = []
        date_affectation = self.aujourdhui - timedelta(days=20)
        for rang_cohorte, ((formation_id, niveau_id), membres) in enumerate(
                sorted(cohortes.items())):
            formation = membres[0].ref_formation
            niveau = membres[0].niveau
            a_affecter = [
                membre for rang, membre in enumerate(membres)
                if membre.id not in deja_affectees and rang % 50 != 49
            ]
            # Une cohorte sans plafond (M2 Loisir) pour illustrer « sans limite ».
            sans_limite = (formation.filiere_code == 'F06'
                           and niveau.code == 'M2')
            capacite = None if sans_limite else capacites_cycle[
                rang_cohorte % len(capacites_cycle)]
            cible = 32 if capacite is None else math.ceil(capacite * 0.9)
            nb_groupes = max(1, math.ceil(len(a_affecter) / cible))
            groupes_cohorte = []
            for numero in range(1, nb_groupes + 1):
                groupe, cree = Groupe.objects.get_or_create(
                    annee_academique=annee, ref_formation=formation,
                    niveau=niveau, nom=f'{niveau.code}-G{numero}',
                    defaults={'capacite_max': capacite},
                )
                groupes_cohorte.append(groupe)
                bilan['groupes'] += 1 if cree else 0
            for rang, membre in enumerate(a_affecter):
                affectations.append(AffectationGroupe(
                    inscription=membre,
                    groupe=groupes_cohorte[rang % nb_groupes],
                    date_debut=date_affectation,
                    motif='[Exemple] Répartition initiale des sections TD/TP.',
                    affecte_par=self.acteur,
                ))
            # Deux groupes fermés (inactifs, vides) pour l'état correspondant.
            if (formation.filiere_code in ('F01', 'F04')
                    and niveau.code in ('L1', 'M1')):
                _, cree = Groupe.objects.get_or_create(
                    annee_academique=annee, ref_formation=formation,
                    niveau=niveau, nom=f'{niveau.code}-G{nb_groupes + 1}',
                    defaults={'capacite_max': 35, 'actif': False},
                )
                bilan['groupes'] += 1 if cree else 0

        AffectationGroupe.objects.bulk_create(affectations, batch_size=500)
        bilan['affectations'] += len(affectations)
        self.stdout.write(self.style.SUCCESS(
            f'Groupes pédagogiques d’exemple : {bilan["groupes"]} groupe(s), '
            f'{bilan["affectations"]} affectation(s) créée(s) sur '
            f'{len(cohortes)} cohorte(s).'
        ))
