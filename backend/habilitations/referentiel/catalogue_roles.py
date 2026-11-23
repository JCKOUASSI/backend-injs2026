"""Les rôles métier de l'annexe A1 (35 lignes, dont 32 rôles internes et 3
destinataires du service), plus 46 rôles cibles du prompt module
Utilisateurs (section « CIBLES (J2) », provisoires — niveaux à valider en
atelier, cf. NIVEAUX_ROLES_CIBLES dans catalogue_matrice.py).

Chaque entrée porte, dans l'ordre des champs : code stable, libellé, domaine,
niveau par défaut, périmètre par défaut, application Django requise ('' =
toujours disponible), caractère sensible, canal imposé ('' = les deux),
ordre d'affichage, description en français courant.

Le recueil titre « 33 rôles » mais le tableau A1 contient 35 lignes : les
trois dernières (Étudiant, Candidat, Consultation) sont des *destinataires
du service*. Elles sont chargées par sécurité additive (note de conception
U3, §2). Les rôles cibles J2 suivent la même règle : ajout additif,
aucun doublon fonctionnel (mappages documentés dans la section).
"""

# (code, libellé, domaine, niveau, périmètre, module, sensible, canal, ordre, description)
ROLES = [
    # ── ADMINISTRATION ──────────────────────────────────────────────
    ('ADMIN_SYSTEME', 'Administrateur système', 'ADMINISTRATION', 'N4',
     'INJS_ENTIER', '', True, '', 10,
     "Gère l'ensemble des comptes, rôles et paramètres de la plateforme, "
     "sans intervenir sur les décisions métier (notes, jurys, finances)."),
    ('DIRECTION_GENERALE', 'Direction générale', 'ADMINISTRATION', 'N4',
     'INJS_ENTIER', '', True, '', 20,
     "Pilote l'institut : consultation générale, décision sur la diplomation "
     "et les statistiques, aucun acte de saisie courante."),
    ('DIRECTION_ETUDES', 'Direction des études', 'ADMINISTRATION', 'N4',
     'INJS_ENTIER', '', True, '', 30,
     "Valide l'organisation des études : scolarité, pédagogie, évaluations, "
     "jurys et emplois du temps."),
    ('SCOLARITE', 'Scolarité', 'ADMINISTRATION', 'N3',
     'SECRETARIAT', 'scolarite', False, '', 40,
     "Coordonne les inscriptions, les dossiers étudiants et le suivi de "
     "scolarité au sein d'un secrétariat."),
    ('RESPONSABLE_PEDAGOGIQUE', 'Responsable pédagogique', 'ADMINISTRATION',
     'N3', 'FORMATION', 'scolarite', False, '', 50,
     "Organise la pédagogie d'une formation : maquettes, équipes, évaluations "
     "et emploi du temps, sans valider les jurys."),
    # ── CANDIDATURES ────────────────────────────────────────────────
    ('AGENT_CANDIDATURE', 'Agent de candidature', 'CANDIDATURES', 'N2',
     'INJS_ENTIER', 'admissions', False, '', 60,
     "Saisit et instruit les dossiers de candidature et les pièces reçues."),
    ('AGENT_CONTROLE_DOSSIERS', 'Agent de contrôle des dossiers',
     'CANDIDATURES', 'N2', 'INJS_ENTIER', 'admissions', False, '', 70,
     "Contrôle la conformité et l'éligibilité des dossiers ; ce rôle est "
     "incompatible avec la saisie des candidatures (séparation des tâches)."),
    ('RESPONSABLE_CONCOURS', 'Responsable concours et sélection',
     'CANDIDATURES', 'N3', 'INJS_ENTIER', 'admissions', True, '', 80,
     "Organise les concours, épreuves et surveillances, puis arrête et publie "
     "les classements."),
    # ── SCOLARITÉ ───────────────────────────────────────────────────
    ('AGENT_ADMISSIONS', 'Agent admissions', 'SCOLARITE', 'N2',
     'SECRETARIAT', 'admissions', False, '', 90,
     "Traite les admissions des candidats retenus et leur passage en "
     "inscription."),
    ('AGENT_INSCRIPTIONS', 'Agent inscriptions', 'SCOLARITE', 'N2',
     'SECRETARIAT', 'scolarite', False, '', 100,
     "Réalise les inscriptions administratives et pédagogiques, et les "
     "affectations de groupes."),
    ('GESTIONNAIRE_ETUDIANTS', 'Gestionnaire étudiants', 'SCOLARITE', 'N2',
     'SECRETARIAT', 'scolarite', False, '', 110,
     "Tient à jour les dossiers étudiants, inscriptions, transferts et suivis "
     "au fil de l'année."),
    # ── PÉDAGOGIE ────────────────────────────────────────────────────
    ('RESPONSABLE_FORMATION', 'Responsable de formation', 'PEDAGOGIE', 'N3',
     'FORMATION', 'scolarite', False, '', 120,
     "Pilote une offre de formation : maquettes, équipes enseignantes et "
     "calendrier, en lien avec les entreprises de stage."),
    ('GESTIONNAIRE_GROUPES', 'Gestionnaire des groupes', 'PEDAGOGIE', 'N2',
     'FORMATION', 'scolarite', False, '', 130,
     "Construit et ajuste les groupes pédagogiques et leurs affectations."),
    ('GESTIONNAIRE_COURS', 'Gestionnaire des cours', 'PEDAGOGIE', 'N2',
     'FORMATION', 'scolarite', False, '', 140,
     "Renseigne les cours, volumes horaires et leur planification."),
    ('GESTIONNAIRE_MAQUETTES', 'Gestionnaire des maquettes', 'PEDAGOGIE', 'N3',
     'FORMATION', 'scolarite', False, '', 150,
     "Élabore et fait valider les maquettes, UE, ECUE et crédits ECTS."),
    # ── ENSEIGNANTS ──────────────────────────────────────────────────
    ('ENSEIGNANT', 'Enseignant', 'ENSEIGNANTS', 'N2',
     'MODULE_ECUE', 'scolarite', False, 'MOBILE', 160,
     "Intervient sur ses ECUE, groupes et séances : saisie des notes et "
     "présences qui le concernent."),
    ('RESPONSABLE_UE_ECUE', 'Responsable UE / ECUE', 'ENSEIGNANTS', 'N3',
     'MODULE_ECUE', 'scolarite', False, '', 170,
     "Coordonne une UE ou une ECUE : équipe, notes, délibérations et "
     "affectations pédagogiques."),
    ('GESTIONNAIRE_CHARGES', 'Gestionnaire des charges enseignantes',
     'ENSEIGNANTS', 'N2', 'FORMATION', 'scolarite', False, '', 180,
     "Prépare les charges et vacations des enseignants, en lien avec la "
     "rémunération des formateurs."),
    # ── ÉVALUATIONS ──────────────────────────────────────────────────
    ('GESTIONNAIRE_NOTES', 'Gestionnaire des notes', 'EVALUATIONS', 'N2',
     'FORMATION', 'suiviEvaluation', False, '', 190,
     "Saisit et corrige les notes et moyennes ; ne participe pas aux jurys "
     "(incompatibilité de séparation des tâches)."),
    ('MEMBRE_JURY', 'Membre de jury', 'EVALUATIONS', 'N2',
     'FORMATION', 'jurys', False, '', 200,
     "Participe aux délibérations d'un jury et signe les propositions "
     "collectives."),
    ('RESPONSABLE_JURY', 'Responsable de jury', 'EVALUATIONS', 'N4',
     'FORMATION', 'jurys', True, '', 210,
     "Préside le jury, arrête les délibérations et signe les procès-verbaux "
     "et résultats."),
    # ── DIPLÔMATION ──────────────────────────────────────────────────
    ('RESPONSABLE_GRADUATION', 'Responsable graduation', 'DIPLOMATION', 'N3',
     'INJS_ENTIER', 'graduation', True, '', 220,
     "Organise les cérémonies et dossiers de graduation et atteste les "
     "parcours arrivant à terme."),
    ('RESPONSABLE_DIPLOMATION', 'Responsable diplômation', 'DIPLOMATION', 'N4',
     'INJS_ENTIER', 'graduation', True, '', 230,
     "Valide, édite et, le cas échéant, révoque les diplômes et tient les "
     "registres réglementaires."),
    # ── FINANCE ──────────────────────────────────────────────────────
    ('GESTIONNAIRE_FINANCES_ETUD', 'Gestionnaire finances étudiantes',
     'FINANCE', 'N2', 'INJS_ENTIER', 'finances_etudiantes', True, '', 240,
     "Saisit les frais, factures, paiements et quittances des étudiants ; ne "
     "valide pas les encaissements (rôle séparé)."),
    ('VALIDATEUR_FINANCIER', 'Validateur financier', 'FINANCE', 'N3',
     'INJS_ENTIER', 'finances_etudiantes', True, '', 250,
     "Valide les paiements, remboursements et écritures financières ; ne "
     "saisit pas les encaissements (séparation des tâches)."),
    ('GESTIONNAIRE_VACATIONS', 'Gestionnaire vacations formateurs',
     'FINANCE', 'N2', 'INJS_ENTIER', 'formations', True, '', 260,
     "Prépare les états de vacation et la rémunération des formateurs et "
     "vacataires."),
    # ── STAGES ───────────────────────────────────────────────────────
    ('GESTIONNAIRE_STAGES', 'Gestionnaire des stages', 'STAGES', 'N2',
     'FORMATION', 'stages', False, '', 270,
     "Gère les organismes d'accueil, tuteurs, conventions et attestations de "
     "stage."),
    # ── RESSOURCES HUMAINES ──────────────────────────────────────────
    ('GESTIONNAIRE_RH', 'Gestionnaire ressources humaines', 'RH', 'N3',
     'INJS_ENTIER', 'ressources_humaines', True, '', 280,
     "Tient les dossiers des agents, services, fonctions, affectations et "
     "documents RH."),
    # ── PATRIMOINE ───────────────────────────────────────────────────
    ('GESTIONNAIRE_PATRIMOINE', 'Gestionnaire du patrimoine', 'PATRIMOINE',
     'N2', 'SITE', 'patrimoine', False, '', 290,
     "Gère les équipements, véhicules, inventaires, maintenance et mouvements "
     "de biens."),
    ('GESTIONNAIRE_ESPACES', 'Gestionnaire des espaces', 'PATRIMOINE', 'N2',
     'SITE', 'patrimoine', False, '', 300,
     "Gère les salles et leurs réservations, en lien avec les emplois du "
     "temps."),
    # ── ADMINISTRATION GÉNÉRALE ──────────────────────────────────────
    ('GESTIONNAIRE_COURRIERS', 'Gestionnaire courriers et documents',
     'ADMINISTRATION_GENERALE', 'N2', 'SERVICE', 'administrations', False,
     '', 310,
     "Enregistre et suit les courriers, documents officiels, réunions et "
     "missions."),
    ('ARCHIVISTE', 'Archiviste', 'ADMINISTRATION_GENERALE', 'N2',
     'INJS_ENTIER', '', False, '', 320,
     "Consulte et archive les dossiers de tous les services, sans droit de "
     "modification."),
    # ── DESTINATAIRES DU SERVICE (usagers, pas des rôles d'administration)
    ('ETUDIANT', 'Étudiant / auditeur', 'DESTINATAIRES', 'N1',
     'PROPRE_COMPTE', 'presences', False, 'MOBILE', 330,
     "Accède uniquement à son propre dossier, ses notes, émargements et "
     "justificatifs via l'application mobile."),
    ('CANDIDAT', 'Candidat', 'DESTINATAIRES', 'N0',
     'PROPRE_COMPTE', 'admissions', False, '', 340,
     "Dépose et suit sa propre candidature et ses pièces, sans voir les "
     "autres dossiers."),
    ('CONSULTATION', 'Consultation restreinte', 'DESTINATAIRES', 'N1',
     'INJS_ENTIER', '', False, '', 350,
     "Compte de lecture très restreinte, sans aucune action de modification, "
     "pour un besoin ponctuel de consultation."),
    # ── CIBLES PROMPT MODULE UTILISATEURS (J2 — provisoires, à valider en
    #     atelier du 2026-09) ──────────────────────────────────────────
    # Rôles de la cible institutionnelle demandée par le prompt maître du
    # module Utilisateurs/Comptes/Rôles/Permissions. Les équivalents A1
    # existants ne sont PAS recréés (mappages documentés dans la note
    # d'architecture 05) : SUPER_ADMIN/ADMIN_SI→ADMIN_SYSTEME,
    # DIRECTION→DIRECTION_GENERALE, PEDAGOGIE_MANAGER→RESPONSABLE_PEDAGOGIQUE,
    # SCOLARITE_MANAGER→SCOLARITE, ETUDIANT_MANAGER→GESTIONNAIRE_ETUDIANTS,
    # GROUPE_MANAGER→GESTIONNAIRE_GROUPES, NOTE_MANAGER→GESTIONNAIRE_NOTES,
    # JURY_PRESIDENT→RESPONSABLE_JURY, JURY_MEMBER→MEMBRE_JURY,
    # STAGE_MANAGER→GESTIONNAIRE_STAGES, LECTEUR→CONSULTATION.
    # Les niveaux de la matrice sont provisoires (J2) : voir
    # NIVEAUX_ROLES_CIBLES dans catalogue_matrice.py.
    # Gouvernance et administration
    ('SECRETARIAT_GENERAL', 'Secrétariat général', 'ADMINISTRATION', 'N3',
     'INJS_ENTIER', 'administrations', False, '', 360,
     "Assiste la direction générale : suivi des instances, du courrier "
     "officiel et des échéances institutionnelles."),
    ('QUALITE_MANAGER', 'Responsable qualité et audit',
     'ADMINISTRATION_GENERALE', 'N3', 'INJS_ENTIER', '', False, '', 370,
     "Anime le système qualité, les audits internes et le suivi des plans "
     "d'actions correctives."),
    ('AUDITEUR', 'Auditeur (qualité / audit)', 'ADMINISTRATION_GENERALE',
     'N1', 'INJS_ENTIER', '', False, '', 380,
     "Consulte l'ensemble des modules en lecture pour l'audit interne ou "
     "externe, sans aucun droit de modification. Distinct du compte "
     "« auditeur » legacy (étudiant mobile)."),
    ('AUDIT_READONLY', 'Audit lecture seule', 'ADMINISTRATION_GENERALE',
     'N1', 'INJS_ENTIER', '', False, '', 390,
     "Consulte les journaux d'audit et les traçabilités sans accès aux "
     "données de gestion."),
    ('PLANIFICATION_MANAGER', 'Responsable planification',
     'ADMINISTRATION_GENERALE', 'N3', 'INJS_ENTIER', 'edts', False, '', 400,
     "Élabore le plan annuel d'activités, les calendriers académiques et le "
     "suivi de la planification."),
    ('STATISTICIEN', 'Statisticien', 'TECHNIQUE', 'N2', 'INJS_ENTIER',
     'statistiques', False, '', 410,
     "Exploite les données de l'établissement pour les indicateurs, les "
     "rapports et les tableaux de bord officiels."),
    ('CHEF_DEPARTEMENT', 'Chef de département', 'ADMINISTRATION', 'N3',
     'DIRECTION', '', False, '', 420,
     "Pilote un département : ressources, planning des services rattachés "
     "et coordination des responsables de formation."),
    ('RESPONSABLE_PARCOURS', 'Responsable de parcours', 'PEDAGOGIE', 'N3',
     'PARCOURS', 'scolarite', False, '', 430,
     "Coordonne un parcours : maquette, équipes et cohérence des acquis sur "
     "l'ensemble du parcours."),
    # Candidatures, concours, admissions, inscriptions
    ('RESPONSABLE_CANDIDATURES', 'Responsable des candidatures',
     'CANDIDATURES', 'N3', 'INJS_ENTIER', 'admissions', False, '', 440,
     "Pilote la collecte et l'instruction des candidatures ; valide l'ouvre"
     "ture et la clôture des campagnes."),
    ('CORRECTEUR_CONCOURS', 'Correcteur de concours', 'CANDIDATURES', 'N2',
     'PROPRE_COMPTE', 'admissions', False, '', 450,
     "Corrige les épreuves qui lui sont attribuées, sans vue sur les "
     "corrections des autres correcteurs."),
    ('SURVEILLANT_CONCOURS', 'Surveillant de concours', 'CANDIDATURES',
     'N2', 'INJS_ENTIER', 'admissions', False, '', 460,
     "Assure la surveillance des épreuves et le suivi des listes de "
     "présence des candidats."),
    ('RESPONSABLE_ADMISSIONS', 'Responsable des admissions', 'CANDIDATURES',
     'N3', 'INJS_ENTIER', 'admissions', False, '', 470,
     "Arrête les listes d'admission, instruit les recours et publie les "
     "résultats des admissions."),
    ('RESPONSABLE_INSCRIPTIONS', 'Responsable des inscriptions', 'SCOLARITE',
     'N3', 'INJS_ENTIER', 'scolarite', False, '', 480,
     "Pilote les campagnes d'inscription, les affectations de groupes et "
     "la clôture administrative."),
    # Pédagogie, évaluations, jurys, diplômation
    ('VACATAIRE', 'Vacataire', 'ENSEIGNANTS', 'N2', 'MODULE_ECUE',
     'scolarite', False, '', 490,
     "Assure les cours et évaluations qui lui sont attribués, dans le "
     "périmètre de ses affectations."),
    ('RESPONSABLE_EVALUATIONS', 'Responsable des évaluations', 'EVALUATIONS',
     'N3', 'INJS_ENTIER', 'suiviEvaluation', False, '', 500,
     "Organise les calendriers d'évaluation, les barèmes et le contrôle "
     "qualité des notes."),
    ('SECRETAIRE_JURY', 'Secrétaire de jury', 'EVALUATIONS', 'N2',
     'FORMATION', 'jurys', False, '', 510,
     "Dresse le procès-verbal des délibérations et en suit le classement "
     "sous la direction du responsable de jury."),
    ('SIGNATAIRE', 'Signataire habilité', 'DIPLOMATION', 'N3', 'INJS_ENTIER',
     'jurys', True, '', 520,
     "Signe les procès-verbaux de jury et les actes officiels de "
     "diplômation qui lui sont soumis ; jamais la validation des notes."),
    ('VALIDATEUR_DIPLOMES', 'Validateur des diplômes', 'DIPLOMATION', 'N3',
     'INJS_ENTIER', 'graduation', True, '', 530,
     "Vérifie l'éligibilité et valide la délivrance des diplômes avant "
     "signature et publication."),
    # Stages, recherche, vie étudiante
    ('ENCADREUR_STAGE', 'Encadrant de stage (INJS)', 'STAGES', 'N2',
     'PROPRE_COMPTE', 'stages', False, '', 540,
     "Encadre les stages qui lui sont attribués, évalue les stagiaires et "
     "valide les notes finales."),
    ('TUTEUR_ENTREPRISE', "Tuteur d'entreprise", 'STAGES', 'N1',
     'PROPRE_COMPTE', 'stages', False, '', 550,
     "Suivi le stage qui lui est confié : convenance, suivi et évaluation "
     "du stagiaire, sans accès aux autres dossiers."),
    ('RECHERCHE_MANAGER', 'Responsable recherche et innovation', 'TECHNIQUE',
     'N3', 'INJS_ENTIER', '', False, '', 560,
     "Pilote les projets de recherche, les partenariats et les innovations "
     "pédagogiques de l'institut."),
    ('CHERCHEUR', 'Chercheur', 'TECHNIQUE', 'N2', 'PROPRE_COMPTE', '',
     False, '', 570,
     "Conduit les projets de recherche qui lui sont confiés et documente "
     "les livrables associés."),
    ('VIE_ETUDIANTE', 'Responsable de la vie étudiante',
     'ADMINISTRATION_GENERALE', 'N2', 'INJS_ENTIER', '', False, '', 580,
     "Organise les activités étudiantes, la discipline et les événements "
     "de la communauté étudiante."),
    # Finances
    ('BOURSE_MANAGER', 'Responsable des bourses', 'FINANCE', 'N3',
     'INJS_ENTIER', 'finances_etudiantes', True, '', 590,
     "Gère les dossiers de bourses, les critères d'attribution et le "
     "paiement des allocations."),
    ('RESPONSABLE_FINANCES', 'Responsable des finances', 'FINANCE', 'N4',
     'INJS_ENTIER', 'finances_etudiantes', True, '', 600,
     "Pilote le pôle finances étudiantes : recettes, dépenses et équilibre "
     "budgétaire."),
    ('COMPTABLE', 'Comptable', 'FINANCE', 'N2', 'INJS_ENTIER',
     'finances_etudiantes', False, '', 610,
     "Saisit et suit les opérations comptables ; n'ouvre ni ne clôture "
     "seul les périodes sensibles."),
    ('CAISSIER', 'Caissier', 'FINANCE', 'N2', 'INJS_ENTIER',
     'finances_etudiantes', False, '', 620,
     "Encaisse et verse les paiements courants ; sa caisse est contrôlée "
     "par le responsable finances."),
    ('RECOUVREMENT', 'Agent de recouvrement', 'FINANCE', 'N2', 'INJS_ENTIER',
     'finances_etudiantes', False, '', 630,
     "Suit les impayés, émet les relances et met à jour les situations de "
     "dettes étudiantes."),
    ('CONTROLEUR_FINANCIER', 'Contrôleur financier', 'FINANCE', 'N3',
     'INJS_ENTIER', 'finances_etudiantes', True, '', 640,
     "Contrôle a posteriori les opérations financières sensibles ; n'exécute "
     "jamais les paiements qu'il contrôle (séparation des tâches)."),
    # Ressources humaines
    ('RESPONSABLE_RH', 'Responsable des ressources humaines', 'RH', 'N3',
     'INJS_ENTIER', 'ressources_humaines', False, '', 650,
     "Pilote les recrutements, les carrières et l'organisation des services "
     "; valide les contrats."),
    ('AGENT_RH', 'Agent RH', 'RH', 'N2', 'INJS_ENTIER',
     'ressources_humaines', False, '', 660,
     "Saisit les dossiers agents, contrats et évaluations ; ne valide pas "
     "les décisions de carrière."),
    ('PAIE_MANAGER', 'Responsable de la paie', 'RH', 'N3', 'INJS_ENTIER',
     'ressources_humaines', True, '', 670,
     "Élabore et contrôle la paie ; ne perçoit jamais sa propre modification "
     "(séparation des tâches)."),
    # Administration générale, patrimoine, GED, communication
    ('RESPONSABLE_ADMINISTRATION', 'Responsable administration et moyens '
     'généraux', 'ADMINISTRATION_GENERALE', 'N3', 'INJS_ENTIER',
     'administrations', False, '', 680,
     "Pilote les moyens généraux : achats, logistique, patrimoine et "
     "services de l'administration."),
    ('ACHATS_MANAGER', 'Responsable des achats', 'ADMINISTRATION_GENERALE',
     'N3', 'INJS_ENTIER', 'administrations', False, '', 690,
     "Gère le cycle d'achat : besoins, appels d'offres, commandes et "
     "réceptions."),
    ('LOGISTICIEN', 'Logisticien', 'ADMINISTRATION_GENERALE', 'N2',
     'INJS_ENTIER', 'patrimoine', False, '', 700,
     "Assure la logistique interne : inventaire, stocks, mouvements et "
     "maintenance courante."),
    ('RESPONSABLE_PATRIMOINE', 'Responsable du patrimoine', 'PATRIMOINE',
     'N3', 'INJS_ENTIER', 'patrimoine', False, '', 710,
     "Administre le patrimoine : biens, véhicules, espaces et leur "
     "affectation."),
    ('MAINTENANCE', 'Agent de maintenance', 'PATRIMOINE', 'N2',
     'INJS_ENTIER', 'patrimoine', False, '', 720,
     "Assure la maintenance préventive et corrective des locaux et "
     "équipements."),
    ('GED_MANAGER', 'Responsable GED', 'ADMINISTRATION_GENERALE', 'N2',
     'INJS_ENTIER', 'administrations', False, '', 730,
     "Administre la gestion électronique des documents : plan de "
     "classement, droits et archivage."),
    ('COMMUNICATION_MANAGER', 'Responsable communication',
     'ADMINISTRATION_GENERALE', 'N2', 'INJS_ENTIER', '', False, '', 740,
     "Pilote la communication institutionnelle : site, réseaux et supports "
     "de l'institut."),
    # Systèmes d'information
    ('SUPPORT_IT', 'Support informatique', 'TECHNIQUE', 'N2', 'INJS_ENTIER',
     '', False, '', 750,
     "Assiste les utilisateurs et gère les incidents ; aucun droit sur les "
     "données de gestion (niveau paramètres : placeholder J2)."),
    ('SYSADMIN', 'Administrateur système', 'TECHNIQUE', 'N4', 'INJS_ENTIER',
     '', True, '', 760,
     "Administre la plateforme (comptes techniques, déploiements) ; ses "
     "actes restent journalisés et révocables, sans droits métier."),
    ('NETWORK_ADMIN', 'Administrateur réseau', 'TECHNIQUE', 'N3',
     'INJS_ENTIER', '', True, '', 770,
     "Gère la connectivité, les pare-feu et les équipements réseau de "
     "l'établissement."),
    ('DB_ADMIN', 'Administrateur de base de données', 'TECHNIQUE', 'N3',
     'INJS_ENTIER', '', True, '', 780,
     "Exploite et sauvegarde les bases de données ; aucun droit d'écriture "
     "sur les données métier."),
    ('SECURITY_ADMIN', 'Administrateur sécurité', 'TECHNIQUE', 'N4',
     'INJS_ENTIER', '', True, '', 790,
     "Surveille et renforce la sécurité du SI ; consulte les journaux sans "
     "modifier les données."),
    ('DATA_ANALYST', 'Analyste de données', 'TECHNIQUE', 'N2', 'INJS_ENTIER',
     'statistiques', False, '', 800,
     "Produit des analyses et des extractions sur les données "
     "institutionnelles."),
    ('API_MANAGER', 'Responsable des intégrations', 'TECHNIQUE', 'N3',
     'INJS_ENTIER', '', True, '', 810,
     "Gère les API d'intégration et les accès machines des partenaires."),
]

# Index rapide par code.
ROLES_PAR_CODE = {ligne[0]: ligne for ligne in ROLES}

#: Les onze rôles sensibles (colonne « Sens. » de l'annexe A1) — rappel
#: explicite, déduit aussi du fanion ``sensible`` des lignes ci-dessus.
ROLES_SENSIBLES = tuple(
    ligne[0] for ligne in ROLES if ligne[6]
)
