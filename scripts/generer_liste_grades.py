#!/usr/bin/env python3
"""Génère la liste exhaustive « Grades enseignants INJS vs rôles INJS-LMD ».

Le classeur compagnon annoncé par le document « GRADES ET STATUTS DES
ENSEIGNANTS-INJS » (PDF du 1er novembre 2026, `dossier_trvx/`) : les grades
viennent de la **base** (référentiel `RefGradeEnseignant`, importé par
`importer_referentiels_injs` depuis
`backend/referentiels/data/nomenclatures_pedagogiques.json`), les autres
plans (statuts d'exercice, fonctions, habilitations, structures, profils,
règles, cas pratiques) sont transcrits du même PDF, et les rôles,
permissions et la matrice des droits sont lus dans le **code**
(`authentication`) — la matrice documentaire du PDF est restituée à part
et ses écarts avec le code sont listés dans la feuille Contrôles.

Usage (depuis la racine du dépôt) :

    backend/.venv/bin/python scripts/generer_liste_grades.py
    backend/.venv/bin/python scripts/generer_liste_grades.py --sortie /tmp/liste.xlsx

Le fichier .xlsx produit est ignoré par Git (règle « classeurs d'import ») :
ce script versionné est la source durable, le classeur se régénère.
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
BACKEND = RACINE / 'backend'
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(RACINE))
os.environ.setdefault('USE_SQLITE', '1')
os.environ.setdefault(
    'DJANGO_SETTINGS_MODULE',
    'arena.settings_sandbox' if (RACINE / 'arena' / 'settings_sandbox.py').exists()
    else 'config.settings',
)

import django  # noqa: E402

django.setup()

from authentication.models import User  # noqa: E402
from authentication.role_groups import ROLE_POLICY  # noqa: E402
from formations.models import RefGrade  # noqa: E402
from referentiels.models import RefGradeEnseignant  # noqa: E402

from openpyxl import Workbook  # noqa: E402
from openpyxl.styles import Alignment, Font, PatternFill  # noqa: E402
from openpyxl.utils import get_column_letter  # noqa: E402

JEU_DONNEES = BACKEND / 'referentiels' / 'data' / 'nomenclatures_pedagogiques.json'
SOURCE_PDF = 'GRADES ET STATUTS DES ENSEIGNANTS-INJS (PDF, 1er nov. 2026)'

BLEU = '1F3864'
GRIS_LIGNE = 'F2F6FC'
ORANGE_RESERVE = 'FFF2CC'


# ── Style (même charte que generer_liste_lmd.py) ────────────────────────────
def _titre(ws, texte, sous_titre, nb_col):
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=nb_col)
    c = ws.cell(row=1, column=1, value=texte)
    c.font = Font(size=14, bold=True, color=BLEU)
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=nb_col)
    c = ws.cell(row=2, column=1, value=sous_titre)
    c.font = Font(size=10, italic=True, color='595959')
    c.alignment = Alignment(wrap_text=True, vertical='top')
    ws.row_dimensions[2].height = 30


def _entetes(ws, ligne, colonnes):
    remplissage = PatternFill('solid', fgColor=BLEU)
    for j, nom in enumerate(colonnes, 1):
        c = ws.cell(row=ligne, column=j, value=nom)
        c.font = Font(bold=True, color='FFFFFF', size=10)
        c.fill = remplissage
        c.alignment = Alignment(wrap_text=True, vertical='center')
    ws.row_dimensions[ligne].height = 32


def _table(ws, colonnes, lignes, largeurs, reserves=()):
    _entetes(ws, 4, colonnes)
    fond = PatternFill('solid', fgColor=GRIS_LIGNE)
    fond_reserve = PatternFill('solid', fgColor=ORANGE_RESERVE)
    for i, valeurs in enumerate(lignes):
        for j, valeur in enumerate(valeurs, 1):
            c = ws.cell(row=5 + i, column=j, value=valeur)
            c.font = Font(size=10)
            c.alignment = Alignment(wrap_text=True, vertical='top')
            if i in reserves:
                c.fill = fond_reserve
            elif i % 2:
                c.fill = fond
    for j, largeur in enumerate(largeurs, 1):
        ws.column_dimensions[get_column_letter(j)].width = largeur
    ws.freeze_panes = 'A5'
    if lignes:
        ws.auto_filter.ref = f'A4:{get_column_letter(len(colonnes))}{4 + len(lignes)}'
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_setup.orientation = 'landscape'
    ws.page_setup.fitToWidth = 1
    ws.print_title_rows = '1:4'


# ── Transcriptions du PDF (plans autres que les grades) ─────────────────────
STATUTS = [
    ("Enseignant titulaire (fonctionnaire)", "Nomination après concours et titularisation ; permanence jusqu'à la retraite", "Traitement indiciaire + primes", "Plein accès aux fonctions de jury et d'encadrement", "FORMATEUR (+ SUPERVISEUR, ENCADRANT, DIRECTION selon la fonction exercée)"),
    ("Enseignant stagiaire", "Année probatoire après réussite au concours", "Traitement de stagiaire", "Enseignement encadré, évaluation par un tuteur ; pas de présidence de jury", "FORMATEUR"),
    ("Enseignant contractuel", "Contrat de droit public à durée déterminée (2 ans renouvelables)", "Rémunération contractuelle", "Assure les enseignements prévus au contrat", "FORMATEUR"),
    ("Enseignant vacataire", "Vacation : intervention ponctuelle rémunérée à l'heure réalisée", "Paiement à l'heure (barème de vacation, majoré sur plateau sportif)", "Assure une ECUE ou une partie d'ECUE ; pas de prérogative de jury sauf désignation expresse", "FORMATEUR uniquement"),
    ("Enseignant associé / invité", "Contribution pédagogique d'une personnalité qualifiée (professeur associé, MC associé, conférencier)", "Indemnités d'enseignement associé", "Interventions ciblées, sans direction de thèse de plein droit", "FORMATEUR"),
    ("Doctorant chargé d'enseignement (moniteur)", "Doctorant inscrit, chargé de TD, TP ou surveillance d'épreuves", "Indemnité de monitorat ou vacation", "Jamais seul sur un cours magistral ; sous la responsabilité d'un enseignant confirmé", "FORMATEUR (périmètre limité : ses groupes)"),
    ("Expert / intervenant fédéral ou sportif", "Entraîneur national, directeur technique national, cadre technique fédéral, arbitre-expert", "Honoraires d'expertise ou vacation", "Intervient sur les UE d'entraînement, les diplômes fédéraux (1 à 3) et la pratique sportive", "FORMATEUR (pratique sportive et entraînement)"),
    ("Maître-nageur sauveteur / encadrant aquatique", "Mise à disposition ou vacation, qualification obligatoire pour la piscine", "Vacation majorée (surveillance obligatoire)", "Encadrement et surveillance des séances de natation ; obligation réglementaire", "FORMATEUR (natation)"),
    ("Tuteur de terrain (encadrant professionnel de stage)", "Professionnel de la structure d'accueil (école, club, fédération, ministère, établissement spécialisé)", "Indemnité éventuelle versée par la structure, non par l'INJS", "Accueille, accompagne et note l'étudiant stagiaire (grille tripartite)", "ENCADRANT (périmètre : ses stagiaires)"),
    ("Professeur émérite (statut d'intervention)", "Après cessation d'activité, sur invitation", "Honoraires d'intervention", "Séminaires, conférences, participation à des soutenances", "FORMATEUR (temporaire)"),
    ("Enseignant en délégation / détachement", "Mise à disposition auprès d'un autre organisme pour une mission", "Traitement maintenu par l'organisme d'accueil", "Grade conservé ; fonctions à l'INJS suspendues pendant la délégation", "Rôle suspendu pendant la délégation"),
]

FONCTIONS = [
    ("Directeur général de l'INJS", "Direction générale", "Cadre supérieur nommé en Conseil des ministres", "Direction de l'établissement, représentation, exécution budgétaire", "Aucun rôle applicatif automatique (compte de service), ou DIRECTION sur décision"),
    ("Directeur d'école (DENSEPS / DENSEP)", "Direction d'école", "Enseignant de rang magistral (maître de conférences ou professeur titulaire)", "Pilotage pédagogique de l'école, maquettes, personnels enseignants", "DIRECTION"),
    ("Chef de Département d'Enseignement et de Recherche (DER/STAPS, DER/STASE)", "Direction de département", "Enseignant de rang magistral", "Coordination disciplinaire, répartition des enseignements, animation de la recherche", "SUPERVISEUR"),
    ("Chef de département de formation continue (DFRC)", "Direction de département", "Enseignant confirmé ou cadre", "Ingénierie des formations à la carte", "SUPERVISEUR ou INJS_ADMIN"),
    ("Directeur du CNSHN / du CNMS", "Direction de centre", "Cadre technique national / médecin", "Pilotage du centre", "DIRECTION ou SUPERVISEUR"),
    ("Responsable de formation", "Coordination pédagogique", "Enseignant permanent confirmé", "Cohérence de la formation, respect des maquettes", "SUPERVISEUR ou INJS_ADMIN"),
    ("Responsable de parcours (EM, MS, ES, APA, AND, LOI, ECJP, GER)", "Coordination pédagogique", "Enseignant permanent", "Suivi des groupes, des stages et des résultats du parcours", "SUPERVISEUR"),
    ("Coordinateur de semestre / de niveau", "Coordination pédagogique", "Enseignant désigné", "Harmonisation des ECUE et des évaluations d'un semestre", "SUPERVISEUR (périmètre semestre)"),
    ("Responsable d'UE (titulaire de la charge de cours)", "Coordination d'UE", "Enseignant de l'UE", "Contenu, supports, coordination des intervenants de l'UE", "FORMATEUR"),
    ("Responsable de la scolarité", "Administration pédagogique", "Cadre administratif", "Inscriptions, dossiers, procès-verbaux", "INJS_ADMIN ou CHEF_SECRETARIAT"),
    ("Chef de secrétariat", "Administration pédagogique", "Personnel administratif", "Encadrement d'un secrétariat et de ses dossiers", "CHEF_SECRETARIAT"),
    ("Responsable financier (DAAF)", "Administration financière", "Cadre administratif", "Budget, frais de scolarité, vacations", "FINANCE"),
    ("Responsable des archives", "Administration documentaire", "Personnel administratif", "Archivage des dossiers, diplômes et PV", "ARCHIVE"),
]

HABILITATIONS = [
    ("Cours magistral (CM)", "Maître-assistant et au-dessus ; assistant sur dérogation encadrée", "Doctorat minimum dans la discipline"),
    ("Travaux dirigés (TD)", "Assistant et au-dessus ; vacataire qualifié ; doctorant moniteur sous supervision", "Master minimum"),
    ("Travaux pratiques (TP)", "Assistant, vacataire ou technicien habilité ; doctorant moniteur", "Master + habilitation technique du plateau ou du laboratoire"),
    ("Pratique sportive sur plateau", "Enseignant d'EPS, entraîneur diplômé, expert fédéral ; MNS pour la natation", "Diplôme fédéral ou brevet exigé selon l'APS (judo : ceinture noire, natation : MNS)"),
    ("Diplômes et brevets fédéraux (1 à 3)", "Cadre technique fédéral agréé, expert fédéral", "Agrément de la fédération + convention avec l'INJS"),
    ("Séminaire de recherche", "Maître-assistant et au-dessus, directeur de mémoire", "Doctorat + expérience d'encadrement"),
    ("Encadrement de mémoire de Master", "Maître-assistant et au-dessus", "Doctorat ; désignation nominative"),
    ("Direction de thèse", "Maître de conférences et au-dessus (rang magistral)", "Habilitation à diriger des recherches ou rang magistral"),
    ("Présidence de jury de semestre / d'année", "Rang magistral ou directeur d'école", "Désignation officielle, journalisée dans le système"),
    ("Présidence de jury de diplôme (Licence / Master)", "Maître de conférences et au-dessus", "Désignation par la direction"),
    ("Encadrant académique de stage", "Enseignant permanent", "Convention de stage signée"),
    ("Tuteur de terrain (stage)", "Professionnel de la structure d'accueil", "Désignation par la structure + convention tripartite"),
    ("Épreuve de concours d'entrée", "Enseignants désignés par la direction, tous grades", "Arrêté de désignation du jury de concours"),
    ("Certificat médical d'aptitude", "Médecin du CNMS uniquement", "Diplôme de docteur en médecine + fonction au CNMS"),
]

STRUCTURES = [
    ("DENSEPS — École Normale Supérieure de l'Éducation Physique et des Sports (ENSEPS)", "STAPS : EM, MS, ES, APA", "Enseignants-chercheurs CAMES (assistant à professeur titulaire), professeurs d'EPS (A3/A4), entraîneurs et cadres techniques, intervenants fédéraux", "Directeur d'école (rang magistral) ; chef du DER/STAPS"),
    ("DENSEP — École Normale Supérieure de l'Éducation Permanente (ENSEP)", "STASE : AND, LOI, ECJP, GER", "Enseignants-chercheurs CAMES en sciences de l'éducation et sciences sociales, professeurs d'éducation permanente (A3/A4), animateurs et cadres de jeunesse", "Directeur d'école (rang magistral) ; chef du DER/STASE"),
    ("CNSHN — Centre National du Sport de Haut Niveau", "Préparation et suivi des sportifs de haut niveau", "Entraîneurs nationaux, directeurs techniques nationaux mis à disposition, cadres fédéraux", "Directeur du CNSHN"),
    ("CNMS — Centre National de la Médecine du Sport", "Certificats médicaux d'aptitude, traumatologie, suivi médical", "Médecins du sport, kinésithérapeutes, personnel paramédical", "Directeur du CNMS (médecin)"),
    ("DFRC — Direction de la Formation Continue et de la Recherche", "Formations à la carte, formation continue, recherche et publications", "Enseignants-chercheurs, experts-invités, intervenants professionnels", "Directeur (cadre supérieur, souvent rang magistral)"),
    ("Directions centrales (DAAF, DIEM, DCP)", "Affaires administratives et financières, infrastructures et maintenance, coopération", "Personnels administratifs et techniques", "Directeur central"),
]

# Détail documentaire des rôles (PDF §8) — les codes/libellés viennent du code.
ROLES_DETAIL = {
    'ADMIN': ("Technique (superutilisateur)", "Administration complète du système : comptes, référentiels, paramétrage, correction des données", "Ne confère aucun grade, aucune prérogative de jury, aucune signature institutionnelle", "Administrateur système désigné ; jamais un enseignant « par son grade »"),
    'DIRECTION': ("Institutionnel", "Validation institutionnelle : ouverture d'année académique, validation et activation des maquettes, verrouillage des PV de jury, validation et signature des diplômes", "Ne permet pas de saisir des notes, de pointer une séance ou de modifier un dossier étudiant", "Directeur général, directeur d'école, ou membre de la direction délégué"),
    'CHEF_INJS_ADMIN': ("Administratif fonctionnel élevé", "Supervision administrative : création de comptes, gestion des référentiels, contrôle des opérations de scolarité, toutes écoles", "Ne remplace pas la signature de la direction ; ne confère pas les prérogatives académiques d'un grade", "Cadre administratif de haut niveau (administration fonctionnelle)"),
    'INJS_ADMIN': ("Administratif fonctionnel", "Gestion des référentiels et de la pédagogie : maquettes, UE/ECUE, groupes, affectations, notes (contrôle), rapports", "N'ouvre ni le module Finance, ni la validation institutionnelle des décisions", "Cadre de scolarité / responsable pédagogique administratif"),
    'CHEF_SECRETARIAT': ("Administratif de proximité (encadrement)", "Encadrement d'un secrétariat : dossiers, inscriptions, pièces justificatives, listes d'étudiants, suivi des notes de son périmètre", "Ne valide pas les décisions pédagogiques ni les diplômes", "Chef de secrétariat d'école ou de département"),
    'SECRETARIAT': ("Administratif de proximité", "Saisie et suivi des dossiers étudiants, inscriptions administratives, pièces, attestations", "N'accède pas aux notes (sauf consultation encadrée), ni au module Finance, ni à la configuration", "Agent de scolarité / secrétaire"),
    'FINANCE': ("Financier", "Frais de scolarité, quittances, barèmes de vacation, ajustements horaires, états de paiement", "N'accède ni aux notes ni aux décisions de jury", "Responsable financier (DAAF) ou agent financier"),
    'ARCHIVE': ("Documentaire", "Archivage et consultation des dossiers, diplômes, PV, documents officiels", "Ne modifie aucune donnée de scolarité ou de notation", "Responsable des archives"),
    'ENCADRANT': ("Pédagogique (accompagnement)", "Suivi des stages et des mémoires, conventions tripartites, questionnaires d'évaluation, consultation des étudiants encadrés", "Ne saisit pas les notes d'ECUE et ne valide pas les décisions", "Enseignant encadrant, tuteur de terrain, superviseur de stage"),
    'SUPERVISEUR': ("Pédagogique (contrôle)", "Supervision pédagogique : contrôle des séances et des présences, consultation et contrôle des notes, gestion des questionnaires, rapports de son périmètre", "Ne signe ni les PV ni les diplômes ; n'administre pas les comptes", "Responsable de formation, de parcours, chef de DER, conseiller ou inspecteur"),
    'FORMATEUR': ("Pédagogique (exécution)", "Saisie de ses séances, badgeage, notes de SES ECUE (brouillon → soumise → validée), consultation de ses groupes et de ses affectations", "Ne modifie pas une note validée (sauf correction auditée), ne valide pas les décisions, n'accède pas aux données des autres enseignants", "TOUT ENSEIGNANT, quel que soit son grade ou son statut"),
    'AUDITEUR': ("Usager", "Consultation de son dossier, de ses notes publiées, de son emploi du temps ; badgeage QR de présence à une séance", "Aucun accès aux données des autres étudiants, ni aux notes non publiées, ni à la configuration", "Étudiant inscrit (Licence, Master, Doctorat) et auditeur de formation continue"),
}

PERMISSIONS_DETAIL = {
    'access_web': "Ouvre l'accès à l'interface web du système.",
    'operational_web': "Accès aux fonctions opérationnelles, hors module Finance.",
    'mutate_users': "Création, modification et désactivation des comptes utilisateurs.",
    'global_scope': "Accès à tous les secrétariats (au lieu du seul secrétariat de rattachement).",
    'list_participants': "Consultation des listes d'étudiants inscrits.",
    'finance_module': "Frais, vacations, ajustements horaires et états financiers.",
    'manage_questionnaires': "Création et publication des questionnaires cours / formateur.",
    'manage_notes': "Saisie, soumission et validation des notes par ECUE.",
    'validate_decisions': "Validation des décisions de jury et des délibérations.",
    'consult_evaluation': "Consultation des résultats et des indicateurs d'évaluation.",
}

ORDRE_PERMISSIONS = [
    'access_web', 'operational_web', 'mutate_users', 'global_scope',
    'list_participants', 'finance_module', 'manage_questionnaires',
    'manage_notes', 'validate_decisions', 'consult_evaluation',
]

# Matrice documentaire du PDF §9 (R = pleine portée, S = sous condition ou
# périmètre restreint, — = refusée). Ordre = ORDRE_PERMISSIONS.
MATRICE_PDF = {
    'ADMIN': 'RRRRRRRRRR',
    'DIRECTION': 'RRSRRR--RR',
    'CHEF_INJS_ADMIN': 'RRRRRSRRSR',
    'INJS_ADMIN': 'RR-RR-RR-R',
    'CHEF_SECRETARIAT': 'RRSSR-SS-S',
    'SECRETARIAT': 'RR--R----S',
    'FINANCE': 'RR-RSR----',
    'ARCHIVE': 'RR-RR----S',
    'ENCADRANT': 'RR-SS-R--R',
    'SUPERVISEUR': 'RR-SR-RSSR',
    'FORMATEUR': 'RR--S-SR-S',
    'AUDITEUR': 'R--------S',
}

PROFILS = [
    ("Professeur titulaire (CAMES)", "Grades universitaire et indiciaire maximaux", "FORMATEUR · ENCADRANT · SUPERVISEUR · DIRECTION (si directeur d'école) · présidence de jury de doctorat", "Peut tout exercer dans son champ académique ; n'a aucun rôle administratif automatique"),
    ("Maître de conférences (CAMES)", "Rang magistral", "FORMATEUR · ENCADRANT · SUPERVISEUR · DIRECTION (si nommé)", "Préside les jurys de Master ; ne peut pas présider un jury de doctorat de plein droit si non habilité"),
    ("Maître-assistant (CAMES)", "Cadre de catégorie A", "FORMATEUR · ENCADRANT · SUPERVISEUR (si fonction de coordination)", "Ne peut pas présider un jury de diplôme ; peut diriger un mémoire de Master"),
    ("Assistant (CAMES)", "Cadre de catégorie A", "FORMATEUR", "TD et TP ; CM seulement sur dérogation ; pas de direction de mémoire de plein droit"),
    ("Professeur de lycée d'EPS ou d'EP (A4)", "Corps du secondaire", "FORMATEUR · ENCADRANT (stage)", "Encadre des stagiaires ; ne devient pas maître de conférences sans doctorat et inscription CAMES"),
    ("Professeur de collège (A3)", "Corps du secondaire", "FORMATEUR", "Enseignement en collège et appui en TP"),
    ("Maître d'EPS (B3)", "Corps du secondaire, catégorie B", "FORMATEUR (pratique sportive)", "Animation et appui ; pas de CM"),
    ("Enseignant vacataire", "Statut d'exercice ponctuel", "FORMATEUR (uniquement ses ECUE)", "Ne peut ni superviser, ni valider une décision, ni administrer"),
    ("Expert fédéral / entraîneur national", "Statut d'intervention", "FORMATEUR (pratique sportive, diplômes fédéraux)", "Périmètre limité à la discipline sportive concernée"),
    ("Médecin du CNMS", "Corps médical", "FORMATEUR (santé, traumatologie, BNS) · ENCADRANT", "Seul habilité à délivrer les certificats d'aptitude — hors périmètre applicatif"),
    ("Personnel administratif", "Corps administratif", "SECRETARIAT · CHEF_SECRETARIAT · FINANCE · ARCHIVE · INJS_ADMIN selon la fonction", "Aucun accès aux notes ni aux décisions, sauf permission explicite et tracée"),
    ("Étudiant inscrit", "Usager", "AUDITEUR", "Consultation de son seul dossier"),
]

REGLES = [
    ("Un rôle ne crée jamais un grade", "L'attribution du rôle FORMATEUR à un vacataire ne fait pas de lui un professeur ; l'attribution du rôle DIRECTION à un cadre ne fait pas de lui un professeur titulaire."),
    ("Un grade ne donne jamais un rôle", "Un professeur titulaire nouvellement recruté n'a aucun accès informatique tant qu'un compte et un rôle ne lui ont pas été attribués par l'administrateur."),
    ("Une fonction se confie, un rôle s'attribue", "La nomination comme chef de DER est une décision de direction (fonction) ; l'ouverture du rôle SUPERVISEUR est une opération technique consécutive, journalisée."),
    ("Le périmètre prime sur le niveau", "Deux personnes portant le même rôle FORMATEUR peuvent avoir des périmètres très différents. C'est l'affectation pédagogique qui détermine l'accès, pas le grade."),
    ("Aucune donnée académique ne se corrige par le rôle", "Un rôle ne permet pas de contourner une règle LMD : une note éliminatoire reste bloquante, une UE capitalisée reste acquise, un PV verrouillé reste verrouillé — quel que soit le rôle du demandeur."),
    ("Toute élévation de privilège est tracée", "L'attribution, la modification et le retrait d'un rôle sont journalisés ; les opérations sensibles (notes, délibérations, diplômes) le sont également."),
    ("Les rôles sont cumulables, les grades non", "Un directeur d'école cumule DIRECTION, SUPERVISEUR et FORMATEUR ; il ne cumule pas deux grades : il détient un seul grade à un instant donné."),
    ("Le grade survit au rôle et à la fonction", "À la fin d'un mandat ou d'une délégation, la fonction cesse et le rôle est retiré ; le grade, lui, est conservé définitivement."),
]

CAS = [
    ("Un vacataire est présenté comme « professeur » dans l'emploi du temps", "Confusion entre titre honorifique, grade et statut", "Il est docteur (diplôme) et vacataire (statut). Le titre de professeur est réservé au professeur titulaire (CAMES). L'emploi du temps doit porter « M./Mme X, docteur, vacataire ».", "Aucun rôle supplémentaire : FORMATEUR avec un périmètre limité à son ECUE."),
    ("Un maître-assistant est nommé chef du DER/STAPS", "Confusion entre grade et fonction", "Il conserve son grade de maître-assistant ; il exerce une fonction de direction de département pour un mandat.", "Rôle SUPERVISEUR ouvert (ou INJS_ADMIN selon le périmètre administratif confié)."),
    ("Un professeur de lycée d'EPS (A4) demande le rôle DIRECTION « puisqu'il a le même grade qu'un directeur »", "Confusion entre catégorie indiciaire et fonction de direction", "Le grade A4 est un grade de corps du secondaire ; la fonction de direction d'école suppose une nomination et, usuellement, le rang magistral.", "Demande refusée ; rôle FORMATEUR conservé."),
    ("Une secrétaire saisit des notes pour « rendre service » à un enseignant absent", "Confusion entre rôle administratif et rôle pédagogique", "La saisie des notes relève de la responsabilité pédagogique de l'enseignant de l'ECUE.", "Rôle SECRETARIAT sans manage_notes ; la correction passe par une réaffectation pédagogique."),
    ("Un professeur titulaire part en délégation pour deux ans", "Confusion entre grade, statut et rôle", "Le grade est conservé ; le statut devient « en délégation » ; les fonctions à l'INJS sont suspendues.", "Rôle FORMATEUR suspendu (compte désactivé ou restreint) pendant la délégation."),
    ("Un doctorant moniteur se voit confier un cours magistral complet", "Confusion entre habilitation pédagogique et commodité de planning", "Le monitorat autorise TD, TP et surveillance, sous supervision — jamais un CM seul.", "Rôle FORMATEUR accordé, mais l'affectation pédagogique doit mentionner la supervision."),
    ("Un entraîneur national intervient sur le brevet fédéral 3", "Confusion entre expertise sportive et grade universitaire", "L'expert fédéral intervient au titre d'un agrément fédéral et d'une convention avec l'INJS ; il n'a aucun grade CAMES.", "Rôle FORMATEUR limité à l'ECUE concernée ; pas de voix délibérative au jury de diplôme."),
    ("Un étudiant de Master réclame l'accès au module de notes pour « vérifier » ses résultats", "Confusion entre consultation et exploitation", "L'étudiant consulte uniquement ses notes publiées ; la saisie et la validation restent internes.", "Rôle AUDITEUR ; consult_evaluation limité à ses propres résultats."),
]


# ── Données ─────────────────────────────────────────────────────────────────
def _charger_jeu():
    return json.loads(JEU_DONNEES.read_text(encoding='utf-8'))


def lignes_grades(jeu):
    """Grades en base, ordonnés comme le jeu de données, détails PDF joints."""
    bloc = jeu['grades_enseignant']['valeurs']
    en_base = {g.code: g for g in RefGradeEnseignant.objects.all()}
    lignes = []
    for i, item in enumerate(bloc, 1):
        g = en_base.get(item['code'])
        lignes.append((
            i, item['famille'], item['code'],
            g.libelle if g else item['libelle'],
            item.get('categorie', ''), item.get('voie_acces', ''),
            item.get('lieu_exercice', ''), item.get('enseignements', ''),
            item.get('roles_applicatifs', ''),
            g.description if g else '',
            g.source_document if g else '',
            g.fiabilite if g else '',
            'Oui' if (g and g.actif) else 'Non',
        ))
    return lignes, en_base


def matrice_code():
    """Matrice effective lue dans ROLE_POLICY (permissions custom des groupes)."""
    resultat = {}
    for role, politique in ROLE_POLICY.items():
        custom = set(politique.get('custom', ()))
        resultat[str(role)] = ''.join(
            '✓' if perm in custom else '—' for perm in ORDRE_PERMISSIONS
        )
    return resultat


# ── Feuilles ────────────────────────────────────────────────────────────────
def feuille_grades(wb, jeu):
    ws = wb.create_sheet('1_Grades')
    _titre(
        ws, 'Grades enseignants de l’INJS d’Abidjan (28) — référentiel en base',
        f'Source : {SOURCE_PDF} §2 (9 lignes CAMES) et §3 (11 lignes fonction publique), '
        'lignes composites éclatées en grades atomiques. Un grade est une décision officielle '
        '(CAMES ou arrêté de nomination) — jamais un rôle applicatif.',
        13,
    )
    lignes, _ = lignes_grades(jeu)
    _table(
        ws,
        ['N°', 'Famille', 'Code', 'Libellé', 'Catégorie / cauris', "Voie d'accès",
         "Où à l'INJS", 'Enseignements possibles', 'Rôles applicatifs possibles',
         'Description', 'Source documentaire', 'Fiabilité', 'Actif'],
        lignes,
        [5, 24, 24, 34, 20, 34, 36, 38, 30, 60, 34, 12, 8],
    )


def feuille_simple(wb, nom, titre, sous_titre, colonnes, lignes, largeurs):
    ws = wb.create_sheet(nom)
    _titre(ws, titre, sous_titre, len(colonnes))
    _table(ws, colonnes, [tuple(l) for l in lignes], largeurs)


def feuille_roles(wb):
    ws = wb.create_sheet('6_Roles_applicatifs')
    _titre(
        ws, 'Les 12 rôles applicatifs INJS-LMD — ce ne sont pas des grades',
        'Codes et libellés lus dans le code (authentication.User.Role) ; périmètres '
        f'documentés par {SOURCE_PDF} §8.',
        7,
    )
    lignes = []
    for code, libelle in User.Role.choices:
        nature, permet, jamais, qui = ROLES_DETAIL.get(
            code, ('— non documenté dans le PDF —', '', '', ''))
        lignes.append((str(code), str(libelle), nature, permet, jamais, qui, SOURCE_PDF + ' §8'))
    _table(
        ws,
        ['Code', 'Libellé', 'Nature', 'Ce que le rôle permet', "Ce qu'il ne permet jamais",
         'Qui le porte', 'Provenance du détail'],
        lignes,
        [20, 18, 26, 58, 50, 40, 26],
    )


def feuille_permissions(wb):
    ws = wb.create_sheet('7_Permissions')
    _titre(
        ws, 'Les 10 permissions techniques INJS-LMD',
        'Codes et libellés lus dans le code (Meta.permissions du modèle User) ; '
        f'portée documentée par {SOURCE_PDF} §9.',
        4,
    )
    lignes = [
        (perm, libelle, PERMISSIONS_DETAIL.get(perm, '— non documenté dans le PDF —'), SOURCE_PDF + ' §9')
        for perm, libelle in User._meta.permissions
    ]
    _table(ws, ['Code', 'Libellé', "Ce qu'elle autorise", 'Provenance du détail'],
           lignes, [26, 44, 70, 26])


def feuille_matrice(wb, nom, titre, sous_titre, matrice):
    ws = wb.create_sheet(nom)
    _titre(ws, titre, sous_titre, 11)
    roles = [str(code) for code, _ in User.Role.choices]
    lignes = [
        tuple([role] + list(matrice.get(role, '—' * 10)))
        for role in roles
    ]
    _table(ws, ['Rôle'] + ORDRE_PERMISSIONS, lignes,
           [22] + [13] * 10)


def feuille_controles(wb, jeu):
    ws = wb.create_sheet('13_Controles')
    _titre(
        ws, 'Contrôles de cohérence (base ↔ jeu de données ↔ PDF ↔ code)',
        'Chaque contrôle est recalculé à la génération ; les écarts sont listés, jamais masqués.',
        4,
    )
    lignes, en_base = lignes_grades(jeu)
    bloc = jeu['grades_enseignant']['valeurs']
    codes_jeu = {i['code'] for i in bloc}
    codes_base = set(en_base)
    zones_vides = [
        g.code for g in en_base.values()
        if not (g.libelle.strip() and g.description.strip() and g.source_document.strip())
    ]
    controles = []
    controles.append((
        'Grades en base (RefGradeEnseignant)', f'{len(en_base)} valeur(s)',
        'Conforme' if len(en_base) == 28 else 'Écart',
        '12 grades CAMES + 16 corps de la fonction publique attendus.',
    ))
    controles.append((
        'Codes base = codes jeu de données',
        f'{len(codes_base & codes_jeu)}/{len(codes_jeu)} communs ; '
        f'absents de la base : {sorted(codes_jeu - codes_base) or "aucun"} ; '
        f'supplémentaires en base : {sorted(codes_base - codes_jeu) or "aucun"}',
        'Conforme' if codes_base == codes_jeu else 'Écart',
        'Le classeur suit l’ordre du jeu de données (échelle CAMES puis corps).',
    ))
    controles.append((
        'Zones de la fiche renseignées (libellé, description, source)',
        f'{len(en_base) - len(zones_vides)}/{len(en_base)} complètes ; vides : {zones_vides or "aucune"}',
        'Conforme' if not zones_vides else 'Écart',
        'Fiabilités en base : ' + ', '.join(sorted({g.fiabilite for g in en_base.values()})),
    ))
    controles.append((
        'Lignes du PDF (§2 : 9, §3 : 11) vs grades atomiques (28)',
        'Écart assumé et tracé', 'Réserve',
        'Lignes composites éclatées (associés, chercheurs, EPS/EP, médecin/paramédical) ; '
        'ligne « Cadres administratifs et de direction » exclue (non enseignants).',
    ))
    roles_code = {str(c) for c, _ in User.Role.choices}
    controles.append((
        'Rôles applicatifs : code (User.Role) vs PDF §8',
        f'{len(roles_code)} dans le code, {len(ROLES_DETAIL)} documentés ; '
        f'écart : {sorted(roles_code ^ set(ROLES_DETAIL)) or "aucun"}',
        'Conforme' if roles_code == set(ROLES_DETAIL) else 'Écart', '',
    ))
    perms_code = {p for p, _ in User._meta.permissions}
    controles.append((
        'Permissions : code (Meta.permissions) vs PDF §9',
        f'{len(perms_code)} dans le code, {len(PERMISSIONS_DETAIL)} documentées ; '
        f'écart : {sorted(perms_code ^ set(PERMISSIONS_DETAIL)) or "aucun"}',
        'Conforme' if perms_code == set(PERMISSIONS_DETAIL) else 'Écart', '',
    ))
    # Divergences matrice PDF (R = pleine portée) vs politique de groupes du code.
    code_m = matrice_code()
    divergences = []
    nuances = 0
    for role in sorted(MATRICE_PDF):
        for idx, perm in enumerate(ORDRE_PERMISSIONS):
            pdf_val = MATRICE_PDF[role][idx]
            code_val = code_m.get(role, '—' * 10)[idx] == '✓'
            if pdf_val == 'S':
                nuances += 1
            elif pdf_val == 'R' and not code_val:
                divergences.append(f'{role}/{perm} : PDF « R », absent de ROLE_POLICY')
            elif pdf_val == '-' and code_val:
                divergences.append(f'{role}/{perm} : PDF « — », présent dans ROLE_POLICY')
    controles.append((
        'Matrice des droits : PDF §9 (documentaire) vs ROLE_POLICY (code effectif)',
        f'{len(divergences)} divergence(s) franche(s), {nuances} cellule(s) « S » '
        '(nuance de périmètre sans équivalent binaire dans le code)',
        'Réserve' if divergences else 'Conforme',
        ' ; '.join(divergences) or 'Aucune divergence franche.',
    ))
    controles.append((
        'Doublon dormant : formations.RefGrade (ancien référentiel « Grades »)',
        f'{RefGrade.objects.count()} valeur(s)',
        'Réserve',
        'Modèle hérité lié aux catégories de volumes, vide : le référentiel '
        'd’autorité des grades enseignants est RefGradeEnseignant.',
    ))
    controles.append((
        'Points à confirmer par la DRH de l’INJS (PDF §13.1)',
        'Non tranchés par les sources', 'Réserve',
        'Intitulés/articles exacts des statuts particuliers EPS/EP ; échelons et '
        'indices de chaque grade ; répartition réelle des enseignants par grade '
        'et par département ; règles de cumul fonction × rôle applicatif.',
    ))
    reserves = {i for i, c in enumerate(controles) if c[2] != 'Conforme'}
    _table(ws, ['Contrôle', 'Résultat', 'Verdict', 'Détail'], controles,
           [52, 64, 12, 90], reserves=reserves)


def feuille_lisez_moi(wb):
    ws = wb.active
    ws.title = 'Lisez-moi'
    ws.column_dimensions['A'].width = 26
    ws.column_dimensions['B'].width = 118
    _titre(
        ws, 'Grades enseignants INJS (Abidjan) vs rôles applicatifs INJS-LMD',
        'Liste complète, exhaustive et détaillée — générée depuis la base de '
        'l’application, le document de référence et le code du système.',
        2,
    )
    lignes = [
        ('Objet', 'Distinguer une fois pour toutes le GRADE (décision officielle : listes '
                  'd’aptitude CAMES, arrêté de nomination dans un corps), le STATUT '
                  'd’exercice, la FONCTION et le RÔLE APPLICATIF — et donner la '
                  'nomenclature complète de chacun de ces plans à l’INJS d’Abidjan.'),
        ('Feuille 1 — Grades', 'Les 28 grades du référentiel « Grades enseignants » tels '
                               'qu’ils sont EN BASE : 12 grades universitaires CAMES '
                               '(assistant → professeur titulaire, associés, chercheurs) et '
                               '16 corps/grades de la fonction publique (B3, A3, A4, '
                               'conseillers, inspecteurs, professorats, agrégations, CNMS).'),
        ('Feuilles 2 à 5', 'Statuts d’exercice (11), fonctions de direction et de '
                           'coordination (13), habilitations pédagogiques (14) et '
                           'répartition par structure (6) — transcrites du PDF ; ce ne '
                           'sont pas des référentiels de la base.'),
        ('Feuilles 6 à 9', 'Rôles applicatifs (12) et permissions (10) lus dans le CODE '
                           '(authentication), matrice des droits effective (ROLE_POLICY) '
                           'puis matrice documentaire du PDF (R/S/—).'),
        ('Feuilles 10 à 12', 'Profils enseignants → rôles possibles (12), règles de '
                             'séparation (8) et cas pratiques arbitrés (8) — PDF §10 à §12.'),
        ('Feuille 13 — Contrôles', 'Cohérence base ↔ jeu de données ↔ PDF ↔ code, écarts '
                                   'et réserves listés sans masquage.'),
        ('Source grades', SOURCE_PDF + ' §2 et §3 (sources citées : guide d’évaluation '
                          'CAMES 2023, portail des concours INJS, ministère de la Fonction '
                          'publique), chargé en base par importer_referentiels_injs depuis '
                          'backend/referentiels/data/nomenclatures_pedagogiques.json.'),
        ('Écart assumé', 'Le PDF compte 9 lignes CAMES et 11 lignes fonction publique ; '
                         'les lignes composites sont éclatées en grades atomiques '
                         '(28 au total) et la ligne « Cadres administratifs et de '
                         'direction » est exclue des grades enseignants. Détail : '
                         'feuille Contrôles.'),
        ('À confirmer (DRH)', 'Échelons, indices, statuts particuliers détaillés et '
                              'répartition réelle des enseignants par grade (PDF §13.1) : '
                              'non publiés, donc non inventés.'),
        ('Régénération', 'backend/.venv/bin/python scripts/generer_liste_grades.py'),
        ('Généré le', datetime.now().strftime('%d/%m/%Y %H:%M')),
    ]
    for i, (cle, texte) in enumerate(lignes, 5):
        a = ws.cell(row=i, column=1, value=cle)
        a.font = Font(bold=True, size=10, color=BLEU)
        a.alignment = Alignment(wrap_text=True, vertical='top')
        b = ws.cell(row=i, column=2, value=texte)
        b.font = Font(size=10)
        b.alignment = Alignment(wrap_text=True, vertical='top')
        ws.row_dimensions[i].height = 44


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--sortie',
        default=str(RACINE / 'Grades_Enseignants_INJS_vs_Roles_INJS_LMD.xlsx'),
    )
    args = parser.parse_args()
    jeu = _charger_jeu()

    wb = Workbook()
    feuille_lisez_moi(wb)
    feuille_grades(wb, jeu)
    feuille_simple(
        wb, '2_Statuts_exercice',
        'Statuts d’exercice à l’INJS (11) — le lien d’emploi, pas le grade',
        f'Transcription {SOURCE_PDF} §5. Le statut ne modifie jamais le grade.',
        ['Statut', 'Nature du lien', 'Rémunération', 'Droits et limites', 'Rôle applicatif habituel'],
        STATUTS, [34, 52, 40, 56, 42],
    )
    feuille_simple(
        wb, '3_Fonctions',
        'Fonctions de direction et de coordination (13) — des mandats, pas des grades',
        f'Transcription {SOURCE_PDF} §6. Une fonction se confie et se retire ; elle '
        'détermine le rôle applicatif ouvert.',
        ['Fonction', 'Type', 'Grade / qualité requise', 'Missions', 'Rôle applicatif'],
        FONCTIONS, [46, 24, 44, 52, 44],
    )
    feuille_simple(
        wb, '4_Habilitations',
        'Habilitations pédagogiques (14) — ce que chaque grade peut assurer',
        f'Transcription {SOURCE_PDF} §7. À renseigner dans l’affectation pédagogique '
        'avant la génération de l’emploi du temps.',
        ["Nature de l'enseignement", 'Grade / qualité requis', 'Diplôme ou agrément exigé'],
        HABILITATIONS, [46, 62, 56],
    )
    feuille_simple(
        wb, '5_Structures',
        'Structures de l’INJS et grades qu’elles emploient (6)',
        f'Transcription {SOURCE_PDF} §4.',
        ['Structure', 'Parcours / missions', 'Grades et profils enseignants', 'Encadrement'],
        STRUCTURES, [52, 40, 68, 40],
    )
    feuille_roles(wb)
    feuille_permissions(wb)
    feuille_matrice(
        wb, '8_Matrice_code',
        'Matrice des droits EFFECTIVE — lue dans le code (ROLE_POLICY)',
        '✓ = permission custom du groupe de rôle (authentication.role_groups) ; '
        'les périmètres (secrétariat, groupes, ECUE) s’appliquent en sus dans les vues.',
        matrice_code(),
    )
    feuille_matrice(
        wb, '9_Matrice_PDF',
        'Matrice des droits DOCUMENTAIRE — PDF §9 (R / S / —)',
        'R = accordée en pleine portée · S = accordée sous condition ou sur périmètre '
        'restreint · — = refusée. La nuance « S » n’a pas d’équivalent binaire dans le '
        'code : écarts détaillés en feuille Contrôles.',
        MATRICE_PDF,
    )
    feuille_simple(
        wb, '10_Profils_roles',
        'De la qualité de l’enseignant aux rôles possibles (12 profils)',
        f'Transcription {SOURCE_PDF} §10 — la pièce opérationnelle du référentiel.',
        ['Qualité / grade', 'Plan concerné', 'Rôles et prérogatives possibles', 'Limites à respecter'],
        PROFILS, [38, 34, 58, 62],
    )
    feuille_simple(
        wb, '11_Regles_separation',
        'Les 8 règles de séparation grade / statut / fonction / rôle',
        f'Transcription {SOURCE_PDF} §11.',
        ['Règle', 'Contenu'],
        REGLES, [46, 118],
    )
    feuille_simple(
        wb, '12_Cas_pratiques',
        'Cas pratiques arbitrés (8)',
        f'Transcription {SOURCE_PDF} §12.',
        ['Situation', 'Confusion commise', 'Qualification correcte', 'Conséquence applicative'],
        CAS, [46, 34, 66, 52],
    )
    feuille_controles(wb, jeu)

    wb.save(args.sortie)
    print(f'Classeur généré : {args.sortie} ({len(wb.sheetnames)} feuilles)')


if __name__ == '__main__':
    main()
