#!/usr/bin/env python3
"""Quatre éditions synchronisées du manuel INJS, sans accès réseau ni base.

Réutilise le corpus éditorial archivé du 9 novembre 2026 et les référentiels
RBAC/navigation extraits du dépôt. Les opérations nouvelles sont croisées avec
les routes actuelles. Ce programme n'écrit que dans dossier_trvx/Manuel_utilisateurs.
"""
from __future__ import annotations

import base64
from collections import Counter
from datetime import date
import html
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'dossier_trvx' / 'Manuel_utilisateurs'
SOURCES = ROOT / 'arena' / 'documentation' / 'manuel_utilisateur' / 'sources'
sys.path.insert(0, str(SOURCES / 'contenu'))
sys.path.insert(0, str(ROOT / 'backend'))  # le générateur historique résout un mauvais parent
from socle import MODULES, SECTIONS, CAPTURES, LISTE_PROFILS, RBAC, META  # noqa: E402
from fiches import construire_fiches  # noqa: E402
from matrice import construire_matrice, PROFIL_VERS_ROLES, SANS_ACCES_WEB  # noqa: E402
from parties_1_3 import PARTIE_I, PARTIE_II, PARTIE_III  # noqa: E402
from parties_4_7 import PARTIE_IV, PARTIE_V, PARTIE_VI, PARTIE_VII  # noqa: E402
from parties_8_12 import PARTIE_VIII, PARTIE_IX, PARTIE_X, PARTIE_XI, PARTIE_XII  # noqa: E402

PARTIES = [PARTIE_I, PARTIE_II, PARTIE_III, PARTIE_IV, PARTIE_V, PARTIE_VI,
           PARTIE_VII, PARTIE_VIII, PARTIE_IX, PARTIE_X, PARTIE_XI, PARTIE_XII]
PROFILS = construire_fiches()
MENU = (ROOT / 'frontend/src/menu/arborescence.js').read_text(encoding='utf-8')
CHEMINS = set(re.findall(r"chemin:\s*'([^']+)'", MENU))
TITRE = 'MANUEL UTILISATEUR INJS LMD 2026'
SOUS_TITRE = ('Guide complet d’exploitation, de configuration et de gestion '
              'administrative, académique et pédagogique de l’INJS d’Abidjan')
DATE = '15 novembre 2026'
VERSION = '2.0 — édition documentaire avec réserves'

# Toute route ci-dessous est testée contre le menu courant ; les opérations
# restent conditionnées aux autorisations réellement accordées à l'utilisateur.
CONFIG = [
 ('Sécuriser les accès', '/administration/comptes', 'ADMIN', 'Compte administrateur habilité et politique de sécurité établie', 'Vérifier les comptes et leurs rattachements ; limiter les rôles au besoin métier ; exiger le changement des secrets initiaux.', 'Reconnexion avec un compte de test autorisé ; contrôle du journal des accès.'),
 ('Structures institutionnelles', '/administration/directions', 'ADMIN', 'Accès à l’administration générale', 'Contrôler directions, départements, services et rattachements avant de créer des agents.', 'Vérifier l’organigramme et l’absence de doublons.'),
 ('Écoles, filières et formations', '/referentiels', 'ADMIN', 'Structure institutionnelle validée', 'Contrôler les écoles, filières, cycles, intitulés et états actifs dans le Hub Référentiels.', 'Consulter la fiche de chaque objet ; éviter archivage/suppression en présence de dépendances.'),
 ('Année, niveaux et semestres', '/scolarite/maquettes', 'INJS_ADMIN', 'Calendrier institutionnel approuvé', 'Vérifier l’année courante, les niveaux et les semestres du référentiel ; saisir les dates officielles avant toute génération annuelle.', 'Comparer les dates aux décisions officielles ; sans bornes S1/S2, ne pas lancer de génération annuelle.'),
 ('Maquettes, UE et ECUE', '/scolarite/maquettes', 'INJS_ADMIN', 'Formations et niveaux renseignés', 'Contrôler crédits, volumes et cohérence UE–ECUE avant validation d’une maquette ; une version publiée ne se réécrit pas.', 'Vérifier les totaux par semestre et le statut actif.'),
 ('Campagnes et concours', '/scolarite/campagnes', 'CHEF_SECRETARIAT', 'Année et formations ouvertes', 'Contrôler périodes, voies d’accès, épreuves et capacité avant d’ouvrir une campagne.', 'Tester un dossier fictif dans un environnement de formation ; vérifier les dates d’ouverture.'),
 ('Inscriptions et groupes', '/scolarite/inscriptions', 'SECRETARIAT', 'Admission et pièces contrôlées', 'Contrôler le dossier puis valider l’inscription ; affecter à une formation et à un groupe sans dépasser la capacité.', 'Vérifier l’état VALIDEE, le niveau et la liste des groupes.'),
 ('Emploi du temps', '/edt', 'INJS_ADMIN', 'Maquettes, groupes, enseignants, salles et calendrier disponibles', 'Vérifier les contraintes et conflits ; générer en brouillon, relire puis soumettre à validation avant publication.', 'Comparer grille, conflits et disponibilité des intervenants ; ne pas publier une période ambiguë.'),
 ('Évaluations et jurys', '/evaluations', 'SUPERVISEUR', 'Inscription pédagogique, maquette et règles de calcul validées', 'Contrôler composants et barèmes puis préparer les sessions ; séparer saisie, contrôle et décision.', 'Vérifier les notes non saisies et le périmètre avant verrouillage.'),
 ('Finances et mise en service', '/finances-etudiantes/frais', 'FINANCE', 'Tarifs validés par l’administration', 'Vérifier les frais, échéanciers et modes de paiement ; ouvrir ensuite les accès progressivement.', 'Tester la consultation d’une situation financière sans confirmer un paiement fictif.'),
]

# Cas concrets : le chemin est un écran constaté, les étapes décrivent des
# vérifications reproductibles sans présumer qu'un bouton existe pour tout rôle.
CAS = [
 ('C01','Contrôler une année académique','ADMIN','/scolarite/maquettes','Calendrier approuvé','Ouvrir le référentiel des années depuis la zone Scolarité ; vérifier année courante et dates ; comparer aux actes officiels.','Une seule année courante cohérente ; dates S1/S2 requises pour une génération annuelle.'),
 ('C02','Vérifier une formation','INJS_ADMIN','/referentiels','Filière et cycle connus','Rechercher la filière dans le Hub ; consulter le cycle, le statut et le rattachement institutionnel ; soumettre une création uniquement si autorisée.','Formation visible dans la liste ; aucun doublon.'),
 ('C03','Contrôler les groupes et capacités','SECRETARIAT','/scolarite/groupes','Année et niveau sélectionnés','Filtrer les groupes ; comparer effectif actif et capacité ; signaler un groupe saturé avant nouvelle affectation.','Capacité respectée ; effectifs mis à jour.'),
 ('C04','Préparer une maquette','INJS_ADMIN','/scolarite/maquettes','Formation, niveau et semestre établis','Ouvrir une maquette brouillon ; saisir UE et ECUE disponibles selon les droits ; contrôler les crédits et volumes ; faire valider.','Maquette active seulement après validation ; conserver les versions anciennes.'),
 ('C05','Examiner une candidature','SECRETARIAT','/scolarite/candidatures','Campagne ouverte','Rechercher le dossier fictif ; vérifier statut et pièces ; corriger les pièces refusées avant transition autorisée.','Statut cohérent et journal de traitement consultable.'),
 ('C06','Contrôler un dossier de candidature','CHEF_SECRETARIAT','/scolarite/controle-dossiers','Pièces déposées','Filtrer les dossiers à vérifier ; ouvrir une pièce ; consigner motif de refus ou contrôle selon le rôle.','Une décision traçable, sans acceptation d’une pièce non vérifiée.'),
 ('C07','Vérifier une campagne de concours','CHEF_SECRETARIAT','/scolarite/campagnes','Référentiels et calendrier approuvés','Contrôler période, formation, épreuves et état ; demander validation avant ouverture.','Campagne consultable ; dates compatibles avec l’année.'),
 ('C08','Contrôler les résultats de concours','INJS_ADMIN','/scolarite/resultats-concours','Épreuves terminées','Consulter les classements et données manquantes ; différer la publication si une note reste à vérifier.','Classement cohérent et publication explicite par profil habilité.'),
 ('C09','Consulter une admission','SECRETARIAT','/scolarite/admissions','Décision prononcée','Rechercher le candidat fictif ; contrôler la décision et sa validité ; ne pas confondre admission et inscription.','Décision affichée ; aucune inscription implicite.'),
 ('C10','Valider une inscription','SECRETARIAT','/scolarite/inscriptions','Admission et pièces conformes','Retrouver le dossier fictif ; saisir année, formation, niveau et régime ; soumettre à validation dans le périmètre autorisé.','Statut VALIDEE puis dossier étudiant retrouvé.'),
 ('C11','Préparer une réinscription','CHEF_SECRETARIAT','/scolarite/reinscriptions','Décision de passage connue','Contrôler l’historique, l’année suivante et la décision officielle ; préparer la réinscription sans inventer les crédits.','Nouvelle inscription rattachée à la bonne année et au bon niveau.'),
 ('C12','Affecter un étudiant à un groupe','SECRETARIAT','/scolarite/groupes','Inscription validée','Vérifier la capacité ; choisir le groupe compatible avec formation/niveau ; conserver l’historique lors d’un changement.','Une seule affectation active pour cette inscription.'),
 ('C13','Lire le journal de scolarité','ARCHIVE','/scolarite/journal','Accès d’audit','Filtrer par période et opération ; consulter le contexte sans diffuser des données personnelles.','Traçabilité conservée ; aucune modification du journal.'),
 ('C14','Dimensionner un EDT','INJS_ADMIN','/edt/dimensionnement','Année, groupes et salles renseignés','Examiner le besoin horaire et les capacités ; vérifier les alertes de données manquantes.','Dimensionnement cohérent avant génération.'),
 ('C15','Générer un brouillon EDT','INJS_ADMIN','/edt/generation-annuelle','Bornes semestrielles officielles et maquettes actives','Choisir automatique (année entière) ou manuel (sélection explicite) selon le contexte ; relire les périodes et les conflits.','Brouillon seulement ; aucune publication automatique.'),
 ('C16','Traiter un conflit de salle','INJS_ADMIN','/edt/conflits','Brouillon et salles actives','Identifier les chevauchements ; vérifier disponibilité de la salle et de l’enseignant ; résoudre puis recalculer les conflits.','Conflit levé avant publication ; historique conservé.'),
 ('C17','Consulter l’EDT publié','ENCADRANT','/edt','EDT validé et publié','Filtrer par semaine/formation ; contrôler les séances et les annulations de la période consultée.','Une séance hors période n’est pas comptée comme prévue aujourd’hui.'),
 ('C18','Contrôler les séances du jour','ENCADRANT','/presences/seances','EDT publié et groupe connu','Comparer la liste des séances planifiées à la date sélectionnée et leurs effectifs attendus.','Les annulations hors date sont exclues de la journée.'),
 ('C19','Contrôler un pointage QR','ENCADRANT','/presences/poste','Séance ouverte, autorisation de badgeage','Lire les indications du poste ; utiliser uniquement un jeton de séance valide ; vérifier statut et heure.','Pointage rattaché à la séance, sans recopier de jeton dans le manuel.'),
 ('C20','Signaler un double scan','ENCADRANT','/presences/registre','Pointage initial enregistré','Rechercher le pointage ; vérifier si le second passage est rejeté ou interprété selon la fenêtre prévue ; consulter l’audit.','Ne jamais contourner l’anti-double-tap ou fabriquer un pointage.'),
 ('C21','Examiner une absence','SECRETARIAT','/presences/registre','Séance du jour terminée','Filtrer le registre par séance ; distinguer absence, retard et justificatif ; orienter la correction au responsable habilité.','Statut et justification traçables.'),
 ('C22','Contrôler les paramètres de présence','ADMIN','/presences/configuration','Politique d’assiduité approuvée','Consulter la durée du jeton, règles de localisation et périmètre ; ne pas modifier sans validation.','Configuration active contrôlée sans divulgation des secrets.'),
 ('C23','Préparer une session d’évaluation','SUPERVISEUR','/evaluations','Maquette et composants approuvés','Vérifier session, ECUE, composant et barème ; laisser brouillon tant que le périmètre n’est pas confirmé.','Session correctement rattachée aux inscrits.'),
 ('C24','Saisir une note','ENCADRANT','/evaluations/saisie','Affectation pédagogique et droit de saisie','Choisir son ECUE ; saisir les valeurs dans le barème ; vérifier l’absence distincte d’un zéro.','Contrôle de saisie réussi ; auteur et date enregistrés.'),
 ('C25','Contrôler les notes','SUPERVISEUR','/evaluations/controle','Saisie terminée','Examiner valeurs hors barème, notes manquantes et absences ; demander correction avant verrouillage.','Aucune anomalie bloquante non résolue.'),
 ('C26','Préparer une délibération','DIRECTION','/jurys/deliberations','Résultats calculés et jury constitué','Consulter les propositions, vérifier crédits et décisions ; demander la validation selon les pouvoirs accordés.','Décision humaine tracée ; pas de validation automatique supposée.'),
 ('C27','Vérifier les crédits ECTS','SUPERVISEUR','/evaluations/resultats','Règle de calcul versionnée','Consulter résultats par ECUE, UE et semestre ; comparer au référentiel du programme.','Aucune compensation inventée si la règle n’est pas configurée.'),
 ('C28','Consulter la situation financière','FINANCE','/finances-etudiantes/situation','Échéancier enregistré','Sélectionner un dossier fictif ; contrôler facturé, encaissé confirmé et solde ; distinguer paiement saisi et confirmé.','Solde cohérent ; aucune comptabilité générale inférée.'),
 ('C29','Contrôler un paiement','FINANCE','/finances-etudiantes/paiements','Dossier et frais identifiés','Vérifier référence, montant, statut et pièce avant toute confirmation selon les droits.','Paiement confirmé uniquement après contrôle ; reçu disponible si configuré.'),
 ('C30','Préparer la diplomation','DIRECTION','/scolarite/graduation','PV et décisions officiels','Contrôler éligibilité et documents ; demander validation du diplôme au service habilité.','Diplôme délivré seulement après décision officielle.'),
 ('C31','Examiner une convention de stage','SECRETARIAT','/stages/conventions','Organisme et tuteur identifiés','Vérifier dates, signatures et étudiant concerné ; suivre le statut de la convention.','Convention consultable ; état contractuel cohérent.'),
 ('C32','Exporter un EDT','INJS_ADMIN','/edt/export','EDT dans le périmètre du compte','Choisir la période et le format proposé à l’écran ; vérifier le fichier téléchargé.','Export conforme au filtre et sans données hors périmètre.'),
 ('C33','Vérifier un import d’étudiants EDT','INJS_ADMIN','/edt/import-etudiants','Fichier préparé selon modèle du module','Téléverser dans un environnement de test ; examiner prévisualisation et anomalies avant validation.','Doublons et lignes rejetées documentés ; aucun import aveugle.'),
 ('C34','Auditer les habilitations','ADMIN','/administration/comptes/journal','Console CURP activée et droit administrateur','Consulter le journal ; comparer droits effectifs et rôles avant délégation ; conserver une preuve de la décision.','Drapeau de console actif ; aucune attribution hors procédure.'),
]

LIMITES = [
 ('L01','L’accès à la production authentifiée n’a pas été exercé ; captures historiques et code ne prouvent pas le comportement de chaque compte réel.','À valider avec des comptes de recette par profil.'),
 ('L02','Le manuel antérieur date du 9 novembre 2026 ; ses menus et affirmations peuvent diverger des routes actuelles.','Les chemins pratiques ci-dessous sont vérifiés dans l’arborescence courante.'),
 ('L03','La matrice N0–N4 du catalogue n’est pas une autorisation API globale : restrictions d’objet, drapeaux et permissions explicites restent déterminants.','Consulter permission_classes et droits effectifs du compte avant opération sensible.'),
 ('L04','Génération annuelle S1/S2 : sans calendrier officiel déclaré, ne pas inventer les bornes ; aucune génération n’est garantie.','Faire approuver les dates puis contrôler brouillon et conflits.'),
 ('L05','Badgeage web public potentiellement désactivé ; jeton QR expirant et droits par séance.','Vérifier la configuration active et le statut de séance.'),
 ('L06','Le tableau de bord peut retourner HTTP 500 indépendamment des autres onglets sur un environnement non diagnostiqué.','Collecter l’exception serveur expurgée ; ne pas affirmer que le problème public est résolu.'),
 ('L07','Finances étudiantes : suivi de factures/paiements, pas une comptabilité générale démontrée.','Faire valider les écritures comptables hors de ce module si nécessaire.'),
 ('L08','Certaines fonctions et menus CURP dépendent du drapeau flag.curp_ui_admin et des droits effectifs.','Ne pas annoncer la console comme ouverte à tous.'),
 ('L09','Une inscription pédagogique, une décision jury et un diplôme suivent des états distincts ; aucun passage automatique universel n’est démontré.','Vérifier chaque transition et son signataire.'),
 ('L10','Les imports/exports varient selon le module et le rôle ; PDF, XLSX et CSV ne sont pas interchangeables.','Lire les options disponibles sur l’écran concerné.'),
 ('L11','Les profils FORMATEUR et AUDITEUR sont mobiles uniquement dans role_groups.py ; un écran web enseignant/étudiant n’ouvre pas automatiquement leur rôle mobile.','Utiliser les comptes et accès réellement autorisés.'),
]

IMPORTS = [
 ('Import Excel legacy','/import','XLSX (champ .xlsx/.xls)','Formations, participants ou séances selon type choisi','Vérifier les colonnes affichées sur l’écran et tester avec un petit fichier','frontend/src/pages/ImportExcel.jsx ; accès/menu conditionnels'),
 ('Import d’étudiants EDT','/edt/import-etudiants','Selon modèle affiché par le module','Étudiants et rattachements EDT','Prévisualiser et vérifier doublons avant validation','frontend/src/menu/arborescence.js ; backend/edts'),
 ('Export EDT','/edt/export','Formats proposés par l’écran, XLSX présent dans la grille','Séances filtrées','Comparer année, période et filtre avec le fichier obtenu','frontend/src/pages/Edts.jsx ; GET-INJS'),
 ('Export listes EDT','/edt','CSV lorsque export=csv est exposé','Listes selon ressource','Contrôler périmètre et encodage','frontend/src/menu/ecrans.js'),
 ('Documents scolaires','/scolarite/documents-scolaires','Format selon document proposé','Certificats/attestations selon droits','Vérifier identité et année avant diffusion','frontend/src/menu/arborescence.js'),
 ('Rapports statistiques','/statistiques/rapports','Non déterminé pour chaque rapport','Agrégats filtrés','Vérifier que le bouton et le format sont effectivement disponibles','frontend/src/menu/arborescence.js'),
]

DEPANNAGE = [
 ('Connexion impossible','Identifiants, mot de passe à renouveler ou compte inactif','Vérifier le message sans divulguer le mot de passe','Réinitialisation selon politique officielle','Administrateur'),
 ('Menu absent','Rôle, capacité ou drapeau non accordé','Comparer accès effectifs et route du menu','Faire valider la demande de droit, ne pas contourner le filtre','Administrateur habilitations'),
 ('Inscription refusée','Admission, pièces ou référentiel manquant','Contrôler statut et année','Compléter le dossier puis relancer la validation autorisée','Scolarité'),
 ('Doublon étudiant','Identité ou matricule déjà lié','Rechercher le dossier existant','Rapprocher sans créer un second dossier','Scolarité'),
 ('Groupe saturé','Capacité maximale atteinte','Contrôler effectif actif et capacité','Choisir un autre groupe approuvé','Scolarité'),
 ('Conflit EDT','Salle, enseignant ou groupe indisponible','Examiner /edt/conflits et contraintes','Déplacer en brouillon, relancer le contrôle','Gestionnaire EDT'),
 ('Génération annuelle refusée','Calendrier S1/S2 absent ou incohérent','Vérifier les bornes officielles','Configurer selon décision institutionnelle, puis réessayer','Direction des études'),
 ('QR invalide','Jeton expiré, séance fermée ou contexte non autorisé','Contrôler date et état de séance sans copier le jeton','Regénérer via l’interface habilitée','Gestionnaire présences'),
 ('Double pointage','Fenêtre anti-double-tap ou entrée déjà enregistrée','Consulter registre et audit','Ne pas forcer une seconde saisie ; traiter l’anomalie','Gestionnaire présences'),
 ('Absence incorrecte','Séance ou justification non rattachée','Vérifier séance, groupe et période','Soumettre la justification via le flux autorisé','Scolarité/encadrant'),
 ('Note non enregistrable','Barème, verrouillage ou périmètre enseignant','Contrôler session et statut du composant','Demander réouverture/correction selon workflow','Responsable évaluations'),
 ('Résultat incohérent','Règle versionnée ou note manquante','Comparer règle et composants de la session','Ne pas recalculer hors moteur ; instruire la correction','Jury/évaluations'),
 ('Paiement absent','Paiement non confirmé ou dossier différent','Vérifier référence et statut','Faire confirmer selon procédure sans créer de doublon','Finances'),
 ('Export indisponible','Droit ou filtre/format absent','Vérifier format et accès de la page','Faire demander le droit ou utiliser format disponible','Responsable module'),
 ('Import rejeté','Colonnes, valeurs ou doublons non conformes','Consulter rapport de validation','Corriger le fichier et prévisualiser à nouveau','Gestionnaire de données'),
 ('Vue d’ensemble HTTP 500','Exception serveur non identifiée','Noter heure UTC et trace expurgée côté serveur','Corriger la cause observée, ne pas déduire de /api/health/','Équipe technique'),
]

GLOSS = [
 ('LMD','Licence–Master–Doctorat : organisation des cycles ; paramètres effectifs à vérifier dans la maquette.'),
 ('ECTS','Crédits pédagogiques ; 30 par semestre dans le référentiel courant, sous réserve de la version approuvée.'),
 ('UE','Unité d’enseignement regroupant des ECUE.'),
 ('ECUE','Élément constitutif d’une UE, affecté à une maquette et à un volume.'),
 ('Maquette','Version de la structure UE/ECUE d’une formation et d’un niveau.'),
 ('Filière','Domaine de formation institutionnel.'),
 ('Formation','Cycle et offre pédagogique rattachés au référentiel.'),
 ('Niveau','Année du cycle L ou M, rattachée aux semestres.'),
 ('Semestre','Période pédagogique déclarée ; ses dates ne sont pas déduites automatiquement.'),
 ('Promotion','Cohorte administrative, à distinguer du groupe d’enseignement.'),
 ('Groupe','Section pédagogique pour l’affectation des inscrits.'),
 ('Inscription administrative','Acte de scolarité validant le dossier, l’année et la formation.'),
 ('Inscription pédagogique','Rattachement aux unités d’enseignement selon maquette et cursus.'),
 ('Capitalisation','Conservation d’un résultat validé selon la règle académique en vigueur.'),
 ('Compensation','Règle académique de calcul : ne s’applique que si configurée et versionnée.'),
 ('Jury','Instance humaine de délibération et décision.'),
 ('Délibération','Examen officiel des propositions de résultats par le jury.'),
 ('Occurrence','Séance datée issue d’un créneau ; ne pas confondre avec le modèle récurrent.'),
 ('Séance','Cours prévu sur un jour donné, avec statut et groupe.'),
 ('Pointage','Enregistrement d’une présence ou d’un passage, rattaché à une séance.'),
 ('Justification','Motif et preuve d’une absence traités selon le circuit autorisé.'),
 ('Périmètre','Limite organisationnelle et personnelle d’une permission.'),
]

# Format éditorial unique, réutilisé dans les quatre livrables.
E = []
def H(text, level=1, anchor=None): E.append(dict(type='heading', text=text, level=level, anchor=anchor or f's{len(E)}'))
def P(text): E.append(dict(type='paragraph', text=str(text)))
def T(headers, rows): E.append(dict(type='table', headers=[str(v) for v in headers], rows=[[str(v) for v in row] for row in rows]))
def I(path, caption):
    if path.exists(): E.append(dict(type='image', path=str(path), caption=caption))

def plain(v):
    return re.sub(r'\*\*|`', '', str(v)).replace('\n',' ')

def old_block(block):
    genre, val = block[0], block[1]
    if genre == 'h3': H(plain(val), 3)
    elif genre == 'p': P(plain(val))
    elif genre in ('liste', 'etapes'):
        for j, item in enumerate(val, 1): P(f'{j}. {plain(item)}' if genre == 'etapes' else f'• {plain(item)}')
    elif genre == 'encadre': P(f"ATTENTION / {val.get('titre', 'Information')} — {plain(val.get('texte',''))}")
    elif genre == 'figure':
        if val['image'] in ('02-referentiels.png','05-edt-grille.png','16-candidatures.png','19-mobile.png'):
            I(SOURCES/'captures'/val['image'], f"Capture d’interface archivée : {val.get('titre','')} — {plain(val.get('legende',''))}")
    elif genre == 'tableau': T(val['entetes'], val['lignes'])
    elif genre == 'formule': P('Formule : '+str(val))
    elif genre == 'tableau_modules_navigation': T(['Section','Entrées','Chemin'], [[s['libelle'],len(s['enfants']),s.get('chemin') or '—'] for s in SECTIONS])
    elif genre == 'tableau_modules_rbac': T(['Code','Domaine','Application'], [[m['code'],m['libelle'],m['app']] for m in MODULES])
    elif genre == 'tableau_permissions_critiques': T(['Permission critique','Domaine'], [[p,p.split('.')[0]] for p in RBAC.get('permissions_critiques',[])])
    elif genre == 'roles_par_famille': T(['Rôle catalogue','Libellé','Périmètre'], [[r['code'],r['libelle'],r['perimetre']] for r in RBAC['roles']])
    elif genre == 'glossaire': T(['Terme','Définition opérationnelle'], GLOSS)
    elif genre == 'problemes': T(['Problème','Cause','Vérification','Solution','Responsable'], [[v['symptome'],v['cause'],v['verification'],v['solution'],v['contact']] for v in val])
    else: P(f'[Contenu ancien à vérifier : {genre}]')

def build():
    H('Informations documentaires et portée',1,'informations')
    P(f'{TITRE} — {VERSION} — {DATE}. Document de formation ; exemples fictifs. Source de vérité : dépôt JCKOUASSI/backend-injs2026, branche documentaire courante. Aucune connexion authentifiée de production n’a été effectuée.')
    P('Méthode : routes du frontend, modèles/services/API Django, catalogue des habilitations, tests et manuel antérieur du 9 novembre 2026. Une route de menu ne prouve ni la présence d’un bouton ni l’autorisation de son action : vérifier la permission côté serveur et les drapeaux effectifs.')
    P('Statuts de preuve : présent dans le code ; conditionnel à une configuration ; partiellement implémenté ; non validé dans le navigateur ; absent du périmètre observé. Les procédures historiques reproduites plus bas sont des aides de formation, pas une recette complète en production.')
    H('Cartographie et architecture fonctionnelle',1,'cartographie')
    T(['Domaine RBAC','Application Django','Sensibilité','Preuve'], [[m['libelle'],m['app'], 'Sensible' if m['sensible'] else 'Standard','backend/habilitations/referentiel/catalogue_modules.py'] for m in MODULES])
    T(['Section de navigation','Route','Écrans déclarés','Statut'], [[s['libelle'],s.get('chemin') or '—', len(s['enfants']),'Présent ; accès conditionnel'] for s in SECTIONS])
    P('Flux transversaux : candidature → admission → inscription administrative → inscription pédagogique → groupe et EDT → séance et présence → évaluations → jury → diplôme ; finances et stages se rattachent au dossier. Le passage entre étapes exige les statuts et décisions propres à chaque module.')
    H('Mise en service — ordre et contrôles',1,'configuration')
    for i,(name,path,role,pre,action,control) in enumerate(CONFIG,1):
        H(f'{i}. {name}',2,f'config-{i}')
        P(f'Acteur indicatif : {role} (sous réserve des droits effectifs). Accès : {path}. Prérequis : {pre}.')
        P(f'Opérations : {action} Contrôle : {control}')
    H('Corpus fonctionnel audité — édition antérieure commentée',1,'corpus')
    P('Les chapitres suivants reprennent le corpus du manuel du 9 novembre 2026. Ils éclairent le métier ; leurs affirmations de disponibilité et libellés de boutons ne sont pas des preuves d’accès dans la version actuelle. Les parcours pratiques actualisés suivent plus bas avec routes contrôlées.')
    for idx,part in enumerate(PARTIES,1):
        H(f'{idx}. {part["titre"]}',2,part['id'])
        for ch in part['chapitres']:
            H(ch['titre'],3,ch['id'])
            P('Statut documentaire : chapitre repris du manuel antérieur (9 novembre 2026), non validé sur chaque rôle dans la version courante. Vérifier route, droit API et configuration avant toute opération décrite ci-dessous.')
            for b in ch['blocs']:old_block(b)
    H('Guides par profil utilisateur',1,'profils')
    P('Les 12 codes ci-dessous sont les choix User.Role. Les 81 rôles du catalogue RBAC sont des rôles métiers attribuables, et non 81 types de compte. Les profils FORMATEUR et AUDITEUR sont mobiles uniquement dans le code analysé. Le droit effectif varie selon la portée, l’objet et les drapeaux.')
    for f in PROFILS:
        H(f"{f['nom']} ({f['code']})",2,'profil-'+f['code'])
        P(f"Métier : {f['fonction']}. Accès web : {'oui, sous conditions' if f['web'] else 'non (mobile seulement)'}. Catalogue projeté : {', '.join(PROFIL_VERS_ROLES.get(f['code'], [])) or 'non déterminé'}. Source : authentication/models.py, role_groups.py et habilitations/referentiel/catalogue_matrice.py.")
        P('Tâches et contrôle : consulter les écrans autorisés ; vérifier le périmètre de chaque dossier ; faire approuver les opérations sensibles par le rôle prévu. Une entrée masquée ou un 403 exige un contrôle des droits, pas un contournement.')
        P('Menus observés dans la version documentaire antérieure (à confirmer sur le compte courant) : '+', '.join(f"{e['libelle']} ({e['chemin']})" for _,es in f['sections'] for e in es[:2])[:1000])
        if f['interdits']: P('Restrictions remarquables : '+' ; '.join(f['interdits']))
        associes=[id for id,title,role,*_ in CAS if role==f['code']]
        P('Procédures détaillées contrôlées dans cette édition : '+(', '.join(associes) if associes else 'aucune action web confirmée pour ce profil ; consulter les limites de son accès mobile.'))
    H('Parcours de formation : étudiant fictif',1,'parcours-etudiant')
    P('KOUASSI Jean-Baptiste, matricule pédagogique fictif INJS-2026-0001, formation Licence Éducation et Motricité, année 2026-2027. Cet exemple n’est pas une donnée d’un étudiant réel ni une garantie que ce matricule existe dans le système.')
    sequence=[('Candidature','C05','Contrôler les pièces avant décision'),('Admission','C09','Contrôler la validité de la décision'),('Inscription administrative','C10','Valider l’année, la formation et le niveau'),('Inscription pédagogique et groupe','C12','Rattacher à la maquette et vérifier la capacité'),('Enseignements/EDT','C17','Consulter uniquement un EDT publié'),('Présences','C19','Pointer uniquement durant une séance autorisée'),('Évaluation','C24','Saisir puis contrôler les notes'),('Délibération','C26','Décision du jury, distincte du calcul'),('Semestre et crédits','C27','Appliquer seulement les règles versionnées'),('Passage','C11','Vérifier la décision officielle'),('Réinscription','C11','Créer l’inscription de l’année suivante selon droits'),('Diplôme','C30','Valider l’éligibilité et la délivrance')]
    for n,(name,ref,check) in enumerate(sequence,1):
        H(f'{n}. {name}',2,f'etudiant-{n}')
        P(f'Cas associé : {ref}. Acteur et chemin à consulter dans le cas pratique. Données : dossier fictif, année, statut et historique. Action : {check}. Contrôle : comparer état avant/après ; si l’automatisme est indisponible, saisir la décision par le responsable habilité sans inventer une validation.')
    H('Cas pratiques reproductibles',1,'cas-pratiques')
    P('Tous les exemples utilisent des données fictives et doivent être exercés en recette, jamais sur des dossiers réels. Un écran consultable ne confère pas automatiquement le droit de créer, valider, supprimer ou exporter.')
    for id,title,role,path,pre,steps,result in CAS:
        H(id+' — '+title,2,id)
        P(f'Contexte : exercice de formation. Objectif : {title.lower()}. Acteur indicatif : {role}, si autorisé. Route constatée : {path}. Prérequis : {pre}.')
        P('1. Vérifier le compte, l’année et le périmètre affiché. 2. '+steps+' 3. Relire les données avant toute confirmation. 4. Contrôler le résultat et la trace sans divulguer de données personnelles.')
        P('Résultat attendu : '+result+' Erreur fréquente : droit absent, statut ou référentiel non préparé ; correction : contrôler l’API et solliciter le responsable habilité, sans contourner les validations.')
    H('Importations, exportations et modèles',1,'import-export')
    T(['Flux','Route','Format attesté / à vérifier','Contenu','Contrôle','Source'], IMPORTS)
    P('Exemple de préparation CSV (illustratif, pas un modèle d’import accepté sans validation) : une ligne d’en-tête conforme au modèle proposé par l’écran, encodage UTF-8, identifiants uniques, dates ISO si demandées. Utiliser la prévisualisation et traiter les rejets ; ne jamais importer de données de production dans une démo.')
    H('Dépannage, sécurité et responsabilités',1,'depannage')
    T(['Symptôme','Cause possible','Vérification','Solution','Responsable'], DEPANNAGE)
    P('Sécurité : ne jamais joindre un mot de passe, un jeton QR, un cookie ou un extrait nominatif à un ticket. Conserver les journaux et les décisions métier. Les sauvegardes/restaurations relèvent des opérateurs autorisés, pas d’un bouton de l’application métier.')
    H('Glossaire',1,'glossaire')
    T(['Terme','Définition — ne pas confondre avec une règle automatiquement configurée'],GLOSS)
    H('Matrice indicative des droits — profil × module',1,'matrice')
    P('Projection des niveaux N0–N4 du catalogue et des verbes minimums : « Conditionnel » signifie possibilité théorique dans au moins une ressource ; la permission effective API, le périmètre, le drapeau et l’état de l’objet doivent être contrôlés. « Non déterminé » lorsque le catalogue ne suffit pas. Ce n’est pas une validation de chaque endpoint.')
    cols,lignes,modules=construire_matrice()
    from matrice import _niveau_min, _verbe_requis  # noqa
    for f in PROFILS:
        code=f['code'];H(f'Matrice — {code}',2,'matrice-'+code)
        lignes_m=[]
        for mcode,label in modules:
            n=_niveau_min(PROFIL_VERS_ROLES.get(code,[]),mcode) if code not in SANS_ACCES_WEB else None
            statuses=[]
            for verbes in (('consulter',),('creer','saisir'),('modifier','soumettre'),('valider','publier'),('supprimer',),('exporter',)):
                req=_verbe_requis(verbes)
                statuses.append('Conditionnel' if n is not None and req is not None and n>=req and code not in SANS_ACCES_WEB else 'Non')
            lignes_m.append([mcode]+statuses+['catalogue_matrice.py ; catalogue_modules.py ; permission_classes API'])
        T(['Module','Lire','Créer','Modifier','Valider','Supprimer','Exporter','Preuve / réserve'],lignes_m)
    H('Limites fonctionnelles et validation documentaire',1,'limites')
    T(['ID','Réserve vérifiée','Action de validation'],LIMITES)
    P('Les résultats de recette, comptes réels, formats disponibles par écran et signatures administratives doivent être validés par le service concerné avant adoption institutionnelle. Le manuel ne déclenche aucune opération sur le serveur public.')
    H('Index des fonctionnalités et preuves',1,'index')
    T(['Module catalogue','Application','Source technique'], [[m['code'],m['app'],'backend/'+(m['app'] or 'habilitations')+'/ ; frontend/src/menu/arborescence.js'] for m in MODULES])
    assert len(CAS)>=25 and len(PROFILS)==12 and len(MODULES)>=20
    missing=[p for _,_,_,p,*_ in CAS if p not in CHEMINS and p!='/import']
    assert not missing, 'Routes des cas absentes du menu courant : '+str(missing)
    return E

def render_html(elements):
    import mimetypes
    esc=html.escape
    nav=''.join(f'<a href="#{esc(e["anchor"])}">{esc(e["text"])}</a>' for e in elements if e['type']=='heading' and e['level']<=2)
    body=[]
    for e in elements:
        typ=e['type']
        if typ=='heading':
            level=min(4,e['level']+1);body.append(f'<h{level} id="{esc(e["anchor"])}">{esc(e["text"])}</h{level}>')
        elif typ=='paragraph':body.append('<p>'+esc(e['text'])+'</p>')
        elif typ=='table':
            rows=''.join('<tr>'+''.join('<th>'+esc(x)+'</th>' for x in e['headers'])+'</tr>')
            rows+=''.join('<tr>'+''.join('<td>'+esc(x)+'</td>' for x in row)+'</tr>' for row in e['rows'])
            body.append('<div class="scroll"><table>'+rows+'</table></div>')
        elif typ=='image':
            path=Path(e['path']); mime=mimetypes.guess_type(path)[0] or 'image/png'
            b64=base64.b64encode(path.read_bytes()).decode()
            body.append(f'<figure><img alt="{esc(e["caption"])}" src="data:{mime};base64,{b64}"><figcaption>{esc(e["caption"])}</figcaption></figure>')
    css='''*{box-sizing:border-box}body{margin:0;background:#eef4fb;color:#193047;font:15px/1.65 system-ui,Arial}header{position:sticky;top:0;background:#092e59;color:white;padding:12px 24px;z-index:4;display:flex;gap:20px;align-items:center}header strong{font-size:16px}input{width:min(460px,45vw);border:0;border-radius:8px;padding:9px}button{border:0;border-radius:8px;padding:9px;cursor:pointer}aside{position:fixed;top:60px;bottom:0;left:0;width:280px;overflow:auto;background:#fff;padding:16px;border-right:1px solid #d5e4f1}aside a{display:block;color:#14528c;padding:6px 9px;text-decoration:none;border-radius:6px;font-size:13px}aside a:hover{background:#e8f3ff}main{margin:0 auto 0 280px;max-width:1400px;padding:36px 6vw;background:white;min-height:100vh}h1{font-size:32px;color:#0c3b70}h2{border-top:2px solid #d8e9f8;padding-top:25px;margin-top:46px;color:#0c3b70}h3{color:#14619a;margin-top:28px}h4{color:#315575}.scroll{overflow:auto;margin:15px 0 25px}table{border-collapse:collapse;min-width:600px;width:100%;font-size:12px}td,th{padding:8px 10px;border:1px solid #dbe5ef;vertical-align:top;text-align:left}th{background:#0f477c;color:#fff;position:sticky;top:0}tr:nth-child(even){background:#f4f8fc}p{max-width:95ch}figure{margin:24px auto;text-align:center}figure img{max-width:100%;max-height:380px;border:1px solid #bed4ec;border-radius:7px}figcaption{font-size:12px;color:#536b82}.hidden{display:none!important}.top{font-size:12px;color:#668;letter-spacing:.1em}@media(max-width:850px){aside{position:relative;top:0;width:auto;height:220px}main{margin:0;padding:20px}header{flex-wrap:wrap}input{width:100%}}@media print{header,aside{display:none}main{margin:0;padding:0;max-width:none}h2,h3{break-after:avoid}tr{break-inside:avoid}table{font-size:9px}}'''
    js='''const q=document.getElementById('q');q.addEventListener('input',()=>{let v=q.value.toLocaleLowerCase('fr');for(let x of document.querySelectorAll('main>h2,main>h3,main>h4,main>p,main>.scroll,main>figure')){x.classList.toggle('hidden',!!v&&!x.textContent.toLocaleLowerCase('fr').includes(v))}document.getElementById('count').textContent=v?'Recherche active — effacer pour retrouver la lecture continue':'Navigation par chapitre et par profil'});'''
    logo=base64.b64encode((ROOT/'dossier_trvx/logo1-INJS.png').read_bytes()).decode()
    s=f'<!doctype html><html lang="fr"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{TITRE}</title><style>{css}</style><header><img src="data:image/png;base64,{logo}" alt="INJS Abidjan" width="32" height="32"><strong>INJS · LMD 2026</strong><input id="q" type="search" placeholder="Rechercher une procédure, un profil, une notion…" aria-label="Rechercher"><span id="count">Navigation par chapitre et par profil</span><button onclick="window.print()">Imprimer</button></header><aside><div class="top">SOMMAIRE · {VERSION}</div>{nav}</aside><main><h1>{TITRE}</h1><p>{SOUS_TITRE}<br>{DATE}</p>{"".join(body)}</main><script>{js}</script></html>'
    (OUT/'Manuel_Utilisateur_INJS_LMD_2026.html').write_text(s,encoding='utf-8')

def render_docx(elements):
    from docx import Document
    from docx.shared import Cm,Pt,RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.enum.table import WD_TABLE_ALIGNMENT
    doc=Document(); section=doc.sections[0];section.top_margin=Cm(2);section.bottom_margin=Cm(2)
    section.header.paragraphs[0].text='INJS · MANUEL UTILISATEUR LMD 2026'
    footer=section.footer.paragraphs[0];footer.text='INJS — édition documentaire avec réserves · '+DATE+'  |  Page '
    style=doc.styles['Normal'];style.font.name='Calibri';style.font.size=Pt(9)
    cover_logo=doc.add_paragraph();cover_logo.alignment=WD_ALIGN_PARAGRAPH.CENTER
    cover_logo.add_run().add_picture(str(ROOT/'dossier_trvx/logo1-INJS.png'),width=Cm(4))
    doc.add_heading(TITRE,0);doc.add_paragraph(SOUS_TITRE,'Subtitle');doc.add_paragraph('Édition '+VERSION+' · '+DATE)
    doc.add_paragraph('Institut National de la Jeunesse et des Sports d’Abidjan')
    doc.add_page_break();doc.add_heading('Sommaire',1)
    doc.add_paragraph('Dans Microsoft Word : clic droit sur la table des matières → Mettre à jour les champs.')
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    pg=OxmlElement('w:fldSimple');pg.set(qn('w:instr'),'PAGE');footer._p.append(pg)
    doc.add_paragraph('Repères de lecture (chapitres principaux) :')
    for ent in (x for x in elements if x['type']=='heading' and x['level']==1):
        doc.add_paragraph('• '+ent['text'])
    p=doc.add_paragraph();run=p.add_run();begin=OxmlElement('w:fldChar');begin.set(qn('w:fldCharType'),'begin');run._r.append(begin)
    instr=OxmlElement('w:instrText');instr.set(qn('xml:space'),'preserve');instr.text='TOC \\o "1-3" \\h \\z \\u';run._r.append(instr)
    sep=OxmlElement('w:fldChar');sep.set(qn('w:fldCharType'),'separate');run._r.append(sep)
    p.add_run('Sommaire automatique — actualiser les champs dans Word.')
    end=OxmlElement('w:fldChar');end.set(qn('w:fldCharType'),'end');p.add_run()._r.append(end)
    doc.add_page_break()
    for e in elements:
        typ=e['type']
        if typ=='heading':doc.add_heading(e['text'], min(4,e['level']))
        elif typ=='paragraph':doc.add_paragraph(e['text'])
        elif typ=='table':
            table=doc.add_table(rows=1, cols=len(e['headers']));table.style='Light Shading Accent 1';table.alignment=WD_TABLE_ALIGNMENT.CENTER
            for cell,text in zip(table.rows[0].cells,e['headers']):cell.text=text
            for row in e['rows']:
                for cell,text in zip(table.add_row().cells,row):cell.text=text
            for row in table.rows:
                for cell in row.cells:
                    for para in cell.paragraphs:
                        for run in para.runs:run.font.size=Pt(7)
            doc.add_paragraph('')
        elif typ=='image':
            try:
                from PIL import Image
                im=Image.open(e['path']);im.thumbnail((1400,900))
                doc.add_picture(e['path'],width=Cm(14));doc.add_paragraph(e['caption'],'Caption')
            except Exception:doc.add_paragraph('Capture disponible : '+e['caption'])
    doc.save(OUT/'Manuel_Utilisateur_INJS_LMD_2026.docx')

def render_pdf(elements):
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.styles import getSampleStyleSheet,ParagraphStyle
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,PageBreak,LongTable,TableStyle,Image as PdfImage,KeepTogether
    from reportlab.lib.utils import ImageReader
    font='/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
    pdfmetrics.registerFont(TTFont('DejaVu',font))
    styles=getSampleStyleSheet();styles.add(ParagraphStyle(name='INJS',fontName='DejaVu',fontSize=8.5,leading=12,spaceAfter=6))
    for level,size in ((1,15),(2,12),(3,10),(4,9)):
        styles.add(ParagraphStyle(name='Titre'+str(level),fontName='DejaVu',fontSize=size,leading=size+4,textColor=colors.HexColor('#0b437a'),spaceBefore=16,spaceAfter=9,keepWithNext=True))
    styles.add(ParagraphStyle(name='Cell',fontName='DejaVu',fontSize=6.3,leading=8))
    story=[Spacer(1,70),PdfImage(str(ROOT/'dossier_trvx/logo1-INJS.png'),width=105,height=105),
           Spacer(1,35),Paragraph(TITRE,styles['Titre1']),Paragraph(SOUS_TITRE,styles['INJS']),
           Paragraph('Institut National de la Jeunesse et des Sports d’Abidjan',styles['INJS']),
           Paragraph(VERSION+' · '+DATE,styles['INJS']),PageBreak()]
    headings=[e for e in elements if e['type']=='heading' and e['level']<=2]
    story.append(Paragraph('Sommaire',styles['Titre1']))
    for e in headings:story.append(Paragraph(f'<link href="#{e["anchor"]}" color="#175f9f">{html.escape(e["text"])}</link>',styles['INJS']))
    story.append(PageBreak())
    for e in elements:
        typ=e['type']
        if typ=='heading':
            story.append(Paragraph(f'<a name="{e["anchor"]}"/>'+html.escape(e['text']),styles['Titre'+str(min(4,e['level']))]))
        elif typ=='paragraph':story.append(Paragraph(html.escape(e['text']),styles['INJS']))
        elif typ=='table':
            n=len(e['headers']); avail=495
            widths=[avail/n]*n
            if n>=6:widths=[avail*.14]+[avail*.105]*(n-2)+[avail-(avail*.14+avail*.105*(n-2))]
            def cell(x):return Paragraph(html.escape(str(x)).replace('\n','<br/>'),styles['Cell'])
            rows=[[cell(v) for v in e['headers']]]+[[cell(v) for v in row] for row in e['rows']]
            table=LongTable(rows,colWidths=widths,repeatRows=1,hAlign='LEFT')
            table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#0c447c')),('TEXTCOLOR',(0,0),(-1,0),colors.white),('VALIGN',(0,0),(-1,-1),'TOP'),('GRID',(0,0),(-1,-1),.25,colors.HexColor('#c7d5e5')),('BOTTOMPADDING',(0,0),(-1,-1),5),('TOPPADDING',(0,0),(-1,-1),5)]))
            story.extend((table,Spacer(1,10)))
        elif typ=='image':
            try:
                from PIL import Image
                im=Image.open(e['path']);w,h=im.size;factor=min(1,430/w,320/h)
                story.extend((PdfImage(e['path'],width=w*factor,height=h*factor),Paragraph(html.escape(e['caption']),styles['Cell']),Spacer(1,8)))
            except Exception:story.append(Paragraph('Capture : '+html.escape(e['caption']),styles['INJS']))
    def draw(canvas,doc):
        canvas.saveState()
        if doc.page==1:
            canvas.setFillColor(colors.HexColor('#0b3c70'));canvas.rect(0,A4[1]-85,A4[0],85,fill=1,stroke=0)
            canvas.setFillColor(colors.HexColor('#d6e8f7'));canvas.rect(50,235,A4[0]-100,3,fill=1,stroke=0)
        canvas.setFont('DejaVu',7);canvas.setFillColor(colors.HexColor('#456581'))
        canvas.drawString(50,30,'INJS · '+VERSION);canvas.drawRightString(A4[0]-50,30,str(doc.page));canvas.restoreState()
    pdf=SimpleDocTemplate(str(OUT/'Manuel_Utilisateur_INJS_LMD_2026.pdf'),pagesize=A4,rightMargin=50,leftMargin=50,topMargin=48,bottomMargin=48,title=TITRE,author='INJS · documentation')
    pdf.build(story,onFirstPage=draw,onLaterPages=draw)

def render_xlsx(elements):
    from openpyxl import Workbook
    from openpyxl.styles import Font,PatternFill,Alignment
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.datavalidation import DataValidation
    wb=Workbook();wb.remove(wb.active)
    def sheet(name,header,rows):
        ws=wb.create_sheet(name);ws.append(header)
        for row in rows:ws.append([str(x) if x is not None else '' for x in row])
        ws.freeze_panes='A2';ws.auto_filter.ref=ws.dimensions;ws.sheet_view.showGridLines=False
        for c in ws[1]:c.fill=PatternFill('solid',fgColor='0C447C');c.font=Font(color='FFFFFF',bold=True);c.alignment=Alignment(wrap_text=True)
        for row in ws.iter_rows(min_row=2):
            for c in row:c.alignment=Alignment(vertical='top',wrap_text=True)
            if row[0].row%2==0:
                for c in row:c.fill=PatternFill('solid',fgColor='EFF6FC')
        for j,h in enumerate(header,1):
            values=[len(str(ws.cell(i,j).value or '')) for i in range(1,min(ws.max_row+1,75))]
            ws.column_dimensions[get_column_letter(j)].width=max(16,min(62,max(values or [16])+3))
        ws.sheet_properties.pageSetUpPr.fitToPage=True
        return ws
    sheets=['SOMMAIRE','CARTOGRAPHIE_MODULES','FONCTIONNALITES','PROFILS_UTILISATEURS','MATRICE_PERMISSIONS','CONFIGURATION_INITIALE','PROCEDURES','PARCOURS_ETUDIANT','CAS_PRATIQUES','IMPORT_EXPORT','CONTROLES','DEPANNAGE','GLOSSAIRE','LIMITES_FONCTIONNELLES','VALIDATION_DOCUMENTAIRE']
    sommaire=sheet('SOMMAIRE',['Feuille','Usage','Source'],[[s,('Outil opérationnel : '+s.lower().replace('_',' ')), 'Manuel DOCX/PDF/HTML, même source de génération'] for s in sheets[1:]])
    for row in range(2,sommaire.max_row+1):
        cell=sommaire.cell(row,1);cell.hyperlink=f"#'{cell.value}'!A1";cell.font=Font(color='1761A0',underline='single',bold=True)
    sheet('CARTOGRAPHIE_MODULES',['Code','Module','Application','Statut','Preuve'],[[m['code'],m['libelle'],m['app'],'Présent dans catalogue ; opération conditionnelle','backend/habilitations/referentiel/catalogue_modules.py'] for m in MODULES])
    sheet('FONCTIONNALITES',['ID','Écran','Chemin','Statut','Preuve'],[[f'F{i:03}',p,p,'Présent au menu ; action conditionnelle','frontend/src/menu/arborescence.js'] for i,p in enumerate(sorted(CHEMINS),1)])
    sheet('PROFILS_UTILISATEURS',['Code','Profil','Accès web','Rôles catalogue','Preuve'],[[f['code'],f['nom'],'Oui, sous conditions' if f['web'] else 'Non (mobile)',', '.join(PROFIL_VERS_ROLES.get(f['code'],[])),'backend/authentication/models.py ; role_groups.py'] for f in PROFILS])
    from matrice import _niveau_min,_verbe_requis
    rows=[]
    for f in PROFILS:
        for m in MODULES:
            n=_niveau_min(PROFIL_VERS_ROLES.get(f['code'],[]),m['code']) if f['code'] not in SANS_ACCES_WEB else None
            statuses=['Conditionnel' if n is not None and n>=_verbe_requis(v) else 'Non' for v in (('consulter',),('creer',),('modifier',),('valider',),('supprimer',),('exporter',))]
            rows.append([f['code'],m['code'],*statuses,'Projection N0–N4 ; API et périmètre à vérifier','catalogue_matrice.py + catalogue_modules.py'])
    ws=sheet('MATRICE_PERMISSIONS',['Profil','Module','Consulter','Créer','Modifier','Valider','Supprimer','Exporter','Réserve','Preuve'],rows)
    dv=DataValidation(type='list',formula1='"Oui,Non,Conditionnel,Non déterminé"');ws.add_data_validation(dv);dv.add('C2:H'+str(ws.max_row))
    from openpyxl.formatting.rule import CellIsRule
    ws.conditional_formatting.add('C2:H'+str(ws.max_row),CellIsRule(operator='equal',formula=['"Conditionnel"'],fill=PatternFill('solid',fgColor='FFF0CC')))
    ws.conditional_formatting.add('C2:H'+str(ws.max_row),CellIsRule(operator='equal',formula=['"Non"'],fill=PatternFill('solid',fgColor='FBE3E3')))
    sheet('CONFIGURATION_INITIALE',['Ordre','Étape','Route','Acteur indicatif','Prérequis','Action','Contrôle'],[[i,*row] for i,row in enumerate(CONFIG,1)])
    sheet('PROCEDURES',['ID','Titre','Route','Prérequis','Instruction','Résultat'],[[i,t,p,pre,steps,result] for i,t,role,p,pre,steps,result in CAS])
    sheet('PARCOURS_ETUDIANT',['Étape','Opération','Cas associé','Statut'],[[i,t,ref,'Conditionnel ; vérifier décision officielle'] for i,(t,ref,_) in enumerate([('Candidature','C05',''),('Admission','C09',''),('Inscription','C10',''),('Groupe','C12',''),('EDT','C17',''),('Présences','C19',''),('Évaluations','C24',''),('Jury','C26',''),('Crédits','C27',''),('Passage','C11',''),('Réinscription','C11',''),('Diplôme','C30','')],1)])
    sheet('CAS_PRATIQUES',['ID','Titre','Profil indicatif','Route','Prérequis','Étapes','Contrôle'],CAS)
    sheet('IMPORT_EXPORT',['Flux','Route','Format','Données','Contrôle','Source'],IMPORTS)
    sheet('CONTROLES',['ID','Contrôle','Responsable','Statut'],[[i,t,role,'À vérifier dans l’environnement cible'] for i,t,role,*_ in CAS])
    sheet('DEPANNAGE',['Symptôme','Cause','Vérification','Solution','Responsable'],DEPANNAGE)
    sheet('GLOSSAIRE',['Terme','Définition'],GLOSS)
    sheet('LIMITES_FONCTIONNELLES',['ID','Réserve','Action à mener'],LIMITES)
    sheet('VALIDATION_DOCUMENTAIRE',['Contrôle','État','Preuve'],[['Source partagée','Vérifié','scripts/produire_manuel_injs_2026.py'],['Recette production authentifiée','Non réalisée','Accès volontairement exclu'],['Matrice API par ressource','Partielle','Contrôle des permissions effectives requis'],['Cohérence 4 formats','À vérifier','Comparer les libellés et les décomptes'],['Périodes S1/S2','Sous configuration','Calendrier institutionnel nécessaire']])
    wb.save(OUT/'Manuel_Utilisateur_INJS_LMD_2026.xlsx')
    assert set(wb.sheetnames)==set(sheets)

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    elements=build()
    render_html(elements);render_docx(elements);render_pdf(elements);render_xlsx(elements)
    print(json.dumps({'elements':len(elements),'chapitres_historiques':sum(len(p['chapitres']) for p in PARTIES),'modules':len(MODULES),'profils':len(PROFILS),'cas':len(CAS),'limitations':len(LIMITES),'formats':4},ensure_ascii=False))
if __name__=='__main__':main()
