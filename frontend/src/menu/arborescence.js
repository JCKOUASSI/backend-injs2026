/**
 * Arborescence de navigation — INJS UFR STAPS-JL.
 *
 * **Source unique de la barre latérale ET des routes génériques** : chaque
 * entrée déclare son chemin, son icône et le droit qui la conditionne. Le
 * composant `Sidebar` n'affiche que ce que l'utilisateur détient ; les routes
 * des écrans génériques sont dérivées de cette même arborescence (aucune
 * liste dupliquée).
 *
 * ## Pilotage par les droits (RBAC)
 *
 * Chaque entrée porte un descripteur `droit` à deux volets, évalués en OU :
 *
 * - `curp`   : codes de permissions du référentiel CURP
 *              (`<module>.<ressource>.<action>`, 1 155 codes). Utilisés pour un
 *              compte **gouverné** (profil `CompteUtilisateur`), à partir de
 *              `GET /api/habilitations/mes-acces/ → permissions_effectives`.
 * - `legacy` : couples `[module, action]` des capacités projetées par
 *              `GET /api/auth/capabilities/` (12 modules), évalués par
 *              `peut(user, module, action)` — repli statique inclus.
 * - `roles`  : liste de rôles legacy acceptés, en secours quand aucune
 *              capacité n'est chargée (mêmes constantes que `utils/roles.js`).
 *
 * Règle de résolution (hybride, décidée avec le commanditaire) :
 * **compte gouverné → CURP fait foi ; sinon → capacités legacy**. Une entrée
 * sans volet `curp` (écran purement legacy, ex. module Finance historique)
 * reste évaluée par le volet legacy, quel que soit le compte : personne ne perd
 * d'accès du fait de la réorganisation.
 *
 * **L'interface n'accorde jamais rien** (règle S3) : masquer une entrée ne
 * change aucune décision du backend, et l'afficher ne dispense d'aucun contrôle
 * serveur. Les vues gardent leurs `permission_classes`.
 *
 * Vocabulaire CURP utilisé ci-dessous : celui de
 * `backend/habilitations/referentiel/catalogue_modules.py` (RESSOURCES).
 */

/** Sections et entrées de la barre latérale, dans l'ordre d'affichage. */
export const ARBORESCENCE = [
  {
    id: 'tableau_de_bord',
    libelle: 'Tableau de bord',
    icone: 'bi-speedometer2',
    chemin: '/dashboard',
    droit: {
      curp: ['statistiques.tableau_bord.consulter'],
      legacy: [['web', 'operationnel']],
    },
  },

  // ------------------------------------------------------------------ SCOLARITÉ
  {
    id: 'scolarite',
    libelle: 'Scolarité',
    icone: 'bi-mortarboard',
    droit: { legacy: [['scolarite', 'voir']] },
    enfants: [
      {
        id: 'scolarite.tableau_bord',
        libelle: 'Tableau de bord',
        chemin: '/scolarite',
        droit: {
          curp: ['scolarite.dossier_etudiant.consulter'],
          legacy: [['scolarite', 'voir']],
        },
      },
      {
        id: 'scolarite.candidatures',
        libelle: 'Candidatures',
        chemin: '/scolarite/candidatures',
        droit: {
          curp: ['candidatures.candidature.consulter'],
          legacy: [['scolarite', 'voir']],
        },
      },
      {
        id: 'scolarite.controle_dossiers',
        libelle: 'Contrôle des dossiers',
        chemin: '/scolarite/controle-dossiers',
        ecran: 'controle_dossiers',
        droit: {
          curp: [
            'candidatures.piece.consulter',
            'candidatures.piece.valider',
            'candidatures.piece.rejeter',
          ],
          legacy: [['scolarite', 'voir']],
        },
      },
      {
        id: 'scolarite.concours',
        libelle: 'Concours & Sélection',
        chemin: '/scolarite/campagnes',
        droit: {
          curp: [
            'candidatures.concours.consulter',
            'candidatures.campagne.consulter',
            'candidatures.epreuve.consulter',
          ],
          legacy: [['scolarite', 'voir']],
        },
      },
      {
        id: 'scolarite.resultats_concours',
        libelle: 'Résultats concours',
        chemin: '/scolarite/resultats-concours',
        ecran: 'resultats_concours',
        droit: {
          curp: [
            'candidatures.classement.calculer',
            'candidatures.classement.publier',
            'candidatures.note_concours.consulter',
          ],
          legacy: [['scolarite', 'voir']],
        },
      },
      {
        id: 'scolarite.admissions',
        libelle: 'Admissions',
        chemin: '/scolarite/admissions',
        droit: {
          curp: [
            'candidatures.eligibilite.valider',
            'candidatures.candidature.valider',
          ],
          legacy: [['scolarite', 'voir']],
        },
      },
      {
        id: 'scolarite.inscriptions',
        libelle: 'Inscriptions',
        chemin: '/scolarite/inscriptions',
        droit: {
          curp: ['scolarite.inscription_administrative.consulter'],
          legacy: [['scolarite', 'voir']],
        },
      },
      {
        id: 'scolarite.etudiants',
        libelle: 'Étudiants',
        chemin: '/participants',
        droit: {
          curp: ['scolarite.dossier_etudiant.consulter'],
          legacy: [['participants', 'lister']],
        },
      },
      {
        id: 'scolarite.groupes',
        libelle: 'Groupes pédagogiques',
        chemin: '/scolarite/groupes',
        droit: {
          curp: ['scolarite.groupe.consulter'],
          legacy: [['scolarite', 'voir']],
        },
      },
      {
        id: 'scolarite.documents',
        libelle: 'Documents scolaires',
        chemin: '/scolarite/documents-scolaires',
        ecran: 'documents_scolaires',
        droit: {
          curp: [
            'exports.export.generer',
            'exports.export.imprimer',
            'diplomation.releve_notes.consulter',
          ],
          legacy: [['exports', 'liste_classe'], ['scolarite', 'voir']],
        },
      },
      {
        id: 'scolarite.maquettes',
        libelle: 'Maquettes LMD',
        chemin: '/scolarite/maquettes',
        droit: {
          curp: ['pedagogie.maquette.consulter'],
          legacy: [['scolarite', 'voir']],
        },
      },
      {
        id: 'scolarite.equivalences',
        libelle: 'Équivalences & dispenses',
        chemin: '/scolarite/equivalences',
        droit: {
          curp: ['scolarite.equivalence.consulter'],
          legacy: [['scolarite', 'voir']],
        },
      },
      {
        id: 'scolarite.reinscriptions',
        libelle: 'Réinscriptions & transferts',
        chemin: '/scolarite/reinscriptions',
        ecran: 'reinscriptions',
        droit: {
          curp: [
            'scolarite.transfert.consulter',
            'scolarite.reorientation.consulter',
          ],
          legacy: [['scolarite', 'voir']],
        },
      },
      {
        id: 'scolarite.journal',
        libelle: 'Journal de scolarité',
        chemin: '/scolarite/journal',
        ecran: 'journal_scolarite',
        droit: {
          curp: ['scolarite.journal_scolarite.consulter'],
          legacy: [['scolarite', 'voir']],
        },
      },
    ],
  },

  // ----------------------------------------------------------------- FORMATIONS
  {
    id: 'formations',
    libelle: 'Formations',
    icone: 'bi-book',
    droit: { legacy: [['web', 'operationnel']] },
    enfants: [
      {
        id: 'formations.lmd',
        libelle: 'Formations LMD',
        chemin: '/formations',
        droit: {
          curp: ['pedagogie.maquette.consulter', 'referentiels.referentiel.consulter'],
          legacy: [['web', 'operationnel']],
        },
      },
      {
        id: 'formations.filieres',
        libelle: 'Filières',
        chemin: '/formations/filieres',
        ecran: 'filieres',
        droit: {
          curp: ['referentiels.referentiel.consulter'],
          legacy: [['web', 'operationnel']],
        },
      },
      {
        id: 'formations.parcours',
        libelle: 'Parcours',
        chemin: '/formations/parcours',
        ecran: 'parcours',
        droit: {
          curp: ['referentiels.referentiel.consulter'],
          legacy: [['web', 'operationnel']],
        },
      },
      {
        id: 'formations.niveaux',
        libelle: 'Niveaux',
        chemin: '/formations/niveaux',
        ecran: 'niveaux',
        droit: {
          curp: ['referentiels.referentiel.consulter'],
          legacy: [['web', 'operationnel']],
        },
      },
      {
        id: 'formations.semestres',
        libelle: 'Semestres',
        chemin: '/formations/semestres',
        ecran: 'semestres',
        droit: {
          curp: ['referentiels.referentiel.consulter'],
          legacy: [['web', 'operationnel']],
        },
      },
      {
        id: 'formations.ue_ecue',
        libelle: 'UE / ECUE',
        chemin: '/formations/ue-ecue',
        ecran: 'ue_ecue',
        droit: {
          curp: ['pedagogie.ue.consulter', 'pedagogie.ecue.consulter'],
          legacy: [['web', 'operationnel']],
        },
      },
      {
        id: 'formations.cours_lmd',
        libelle: 'Cours (LMD)',
        chemin: '/cours',
        droit: {
          curp: ['pedagogie.volume_horaire.consulter'],
          legacy: [['web', 'operationnel']],
        },
      },
      {
        id: 'formations.enseignants',
        libelle: 'Enseignants',
        chemin: '/formateurs',
        droit: {
          curp: ['enseignants.enseignant.consulter'],
          legacy: [['web', 'operationnel']],
        },
      },
      {
        id: 'formations.affectations',
        libelle: 'Affectations pédagogiques',
        chemin: '/scolarite/charges',
        droit: {
          curp: [
            'pedagogie.affectation_pedagogique.consulter',
            'enseignants.charge.consulter',
          ],
          legacy: [['scolarite', 'voir']],
        },
      },
    ],
  },

  // ------------------------------------------------------------------ GET-INJS
  {
    id: 'get_injs',
    libelle: 'GET-INJS',
    sousTitre: 'Gestion des Emplois du Temps',
    icone: 'bi-calendar-week',
    droit: { legacy: [['web', 'operationnel']] },
    enfants: [
      {
        id: 'get_injs.tableau',
        libelle: 'Tableau des emplois du temps',
        chemin: '/edt',
        droit: {
          curp: ['edt.creneau.consulter', 'edt.emploi_du_temps.generer'],
          legacy: [['web', 'operationnel']],
        },
      },
      {
        id: 'get_injs.generation',
        libelle: 'Créer un emploi du temps',
        chemin: '/edt/nouveau',
        droit: {
          curp: ['edt.emploi_du_temps.generer', 'edt.emploi_du_temps.creer'],
          legacy: [['web', 'operationnel']],
        },
      },
      {
        id: 'get_injs.presences_seance',
        libelle: 'Présences de séance (QR & émargement)',
        chemin: '/edt/presences',
        droit: {
          curp: ['presences.emargement.consulter'],
          legacy: [['web', 'operationnel']],
        },
      },
      {
        id: 'get_injs.cours',
        libelle: 'Cours',
        chemin: '/cours',
        droit: {
          curp: ['edt.seance.creer'],
          legacy: [['web', 'operationnel']],
        },
      },
      {
        id: 'get_injs.salles',
        libelle: 'Salles & espaces',
        chemin: '/edt/salles-espaces',
        ecran: 'salles_espaces',
        droit: {
          curp: ['patrimoine.espace.consulter'],
          legacy: [['web', 'operationnel']],
        },
      },
      {
        id: 'get_injs.disponibilites',
        libelle: 'Disponibilités',
        chemin: '/edt/disponibilites',
        ecran: 'disponibilites',
        droit: {
          curp: [
            'enseignants.disponibilite.consulter',
            'enseignants.indisponibilite.consulter',
          ],
          legacy: [['web', 'operationnel']],
        },
      },
      {
        id: 'get_injs.enseignants',
        libelle: 'Enseignants',
        chemin: '/formateurs',
        droit: {
          curp: ['enseignants.enseignant.consulter'],
          legacy: [['web', 'operationnel']],
        },
      },
      {
        id: 'get_injs.conflits',
        libelle: 'Conflits & contraintes',
        chemin: '/edt/conflits',
        ecran: 'conflits_edt',
        droit: {
          curp: ['edt.conflit.resoudre', 'edt.contrainte.consulter'],
          legacy: [['web', 'operationnel']],
        },
      },
      {
        id: 'get_injs.rattrapages',
        libelle: 'Rattrapages & examens',
        chemin: '/rattrapages',
        droit: {
          curp: ['edt.rattrapage.consulter', 'edt.examen.consulter'],
          legacy: [['presences', 'voir']],
        },
      },
      {
        id: 'get_injs.export',
        libelle: 'Export / Impression',
        chemin: '/edt/export',
        ecran: 'export_edt',
        droit: {
          curp: ['exports.export.generer', 'exports.export.imprimer'],
          legacy: [['web', 'operationnel']],
        },
      },
    ],
  },

  // ----------------------------------------------------------------- ÉVALUATIONS
  {
    id: 'evaluations',
    libelle: 'Évaluations',
    icone: 'bi-clipboard-check',
    droit: { legacy: [['evaluations', 'consulter']] },
    enfants: [
      {
        // E1.3 : le tableau de bord est l'entrée analytique du module et
        // doit précéder « Évaluations » dans la barre latérale.
        id: 'evaluations.tableau',
        libelle: 'Tableau de bord des évaluations',
        chemin: '/evaluations/tableau-de-bord',
        droit: {
          curp: ['evaluations.questionnaire.consulter'],
          legacy: [['evaluations', 'consulter']],
        },
      },
      {
        id: 'evaluations.liste',
        libelle: 'Évaluations',
        chemin: '/evaluations',
        droit: {
          curp: ['evaluations.questionnaire.consulter'],
          legacy: [['evaluations', 'consulter']],
        },
      },
      {
        id: 'evaluations.saisie_notes',
        libelle: 'Saisie des notes',
        chemin: '/evaluations/saisie',
        ecran: 'saisie_notes',
        droit: {
          curp: ['evaluations.note.saisir'],
          legacy: [['evaluations', 'consulter']],
        },
      },
      {
        id: 'evaluations.controle_notes',
        libelle: 'Contrôle des notes',
        chemin: '/evaluations/controle',
        ecran: 'controle_notes',
        droit: {
          curp: [
            'evaluations.note.valider',
            'evaluations.correction_note.consulter',
          ],
          legacy: [['evaluations', 'consulter']],
        },
      },
      {
        id: 'evaluations.deliberations',
        libelle: 'Délibérations',
        chemin: '/evaluations/deliberations',
        // Pas d'`ecran` : la route est rendue par App.jsx (`<Deliberations />`,
        // branché sur l'API Jurys). Déclarer ici un écran générique créait une
        // SECONDE route pour le même chemin — code mort, la première gagnait.
        droit: {
          curp: ['evaluations.decision_pedagogique.consulter'],
          legacy: [['evaluations', 'consulter']],
        },
      },
      {
        id: 'evaluations.resultats',
        libelle: 'Résultats',
        chemin: '/evaluations/resultats',
        // Idem Délibérations : rendu par App.jsx (`<ResultatsEvaluations />`).
        droit: {
          curp: ['evaluations.moyenne.calculer', 'evaluations.moyenne.publier'],
          legacy: [['evaluations', 'consulter']],
        },
      },
      {
        id: 'evaluations.releves',
        libelle: 'Relevés de notes',
        chemin: '/evaluations/releves',
        ecran: 'releves_notes',
        droit: {
          curp: ['diplomation.releve_notes.consulter'],
          legacy: [['notes', 'gerer'], ['exports', 'liste_classe']],
        },
      },
    ],
  },

  // --------------------------------------------------------------------- JURYS
  {
    id: 'jurys',
    libelle: 'Jurys',
    icone: 'bi-mortarboard-fill',
    droit: { legacy: [['scolarite', 'voir']] },
    enfants: [
      {
        id: 'jurys.sessions',
        libelle: 'Jurys',
        chemin: '/scolarite/jurys',
        droit: {
          curp: ['jurys.session_jury.consulter'],
          legacy: [['scolarite', 'voir']],
        },
      },
      {
        id: 'jurys.composition',
        libelle: 'Composition',
        chemin: '/jurys/composition',
        ecran: 'jury_composition',
        droit: {
          curp: ['jurys.membre_jury.consulter'],
          legacy: [['scolarite', 'voir']],
        },
      },
      {
        id: 'jurys.deliberations',
        libelle: 'Délibérations',
        chemin: '/jurys/deliberations',
        ecran: 'jury_deliberations',
        droit: {
          curp: ['jurys.deliberation.consulter', 'jurys.decision.consulter'],
          legacy: [['scolarite', 'voir']],
        },
      },
      {
        id: 'jurys.pv',
        libelle: 'PV de jury',
        chemin: '/jurys/pv',
        ecran: 'jury_pv',
        droit: {
          curp: ['jurys.pv.generer', 'jurys.pv.signer', 'jurys.pv.publier'],
          legacy: [['scolarite', 'voir']],
        },
      },
      {
        id: 'jurys.validation',
        libelle: 'Validation',
        chemin: '/jurys/validation',
        ecran: 'jury_validation',
        droit: {
          curp: ['jurys.resultat.publier', 'jurys.decision.valider'],
          legacy: [['scolarite', 'voir']],
        },
      },
    ],
  },

  // ----------------------------------------------------------------- DIPLÔMATION
  {
    id: 'diplomation',
    libelle: 'Diplômation',
    icone: 'bi-award',
    droit: { legacy: [['scolarite', 'voir']] },
    enfants: [
      {
        id: 'diplomation.eligibilite',
        libelle: 'Éligibilité',
        chemin: '/diplomation/eligibilite',
        ecran: 'eligibilite_diplome',
        droit: {
          curp: ['diplomation.diplome.consulter'],
          legacy: [['scolarite', 'voir']],
        },
      },
      {
        id: 'diplomation.diplomes',
        libelle: 'Diplômes',
        chemin: '/scolarite/graduation',
        droit: {
          curp: ['diplomation.diplome.consulter', 'diplomation.diplome.valider'],
          legacy: [['scolarite', 'voir']],
        },
      },
      {
        id: 'diplomation.attestations',
        libelle: 'Attestations',
        chemin: '/diplomation/attestations',
        ecran: 'attestations',
        droit: {
          curp: ['diplomation.attestation.consulter', 'diplomation.attestation.imprimer'],
          legacy: [['scolarite', 'voir']],
        },
      },
      {
        id: 'diplomation.certificats',
        libelle: 'Certificats',
        chemin: '/diplomation/certificats',
        ecran: 'certificats',
        droit: {
          curp: ['diplomation.modele_document.consulter'],
          legacy: [['scolarite', 'voir']],
        },
      },
      {
        id: 'diplomation.registres',
        libelle: 'Registres & modèles',
        chemin: '/diplomation/registres',
        ecran: 'registres_diplomes',
        droit: {
          curp: ['diplomation.registre.consulter'],
          legacy: [['scolarite', 'voir']],
        },
      },
      {
        id: 'diplomation.archives',
        libelle: 'Archives',
        chemin: '/archives',
        droit: {
          curp: ['diplomation.registre.consulter'],
          legacy: [['scolarite', 'voir']],
          roles: ['ARCHIVE', 'DIRECTION', 'ADMIN', 'CHEF_INJS_ADMIN', 'INJS_ADMIN'],
        },
      },
    ],
  },

  // -------------------------------------------------------- FINANCES ÉTUDIANTES
  {
    id: 'finances_etudiantes',
    libelle: 'Finances étudiantes',
    icone: 'bi-cash-coin',
    droit: { legacy: [['scolarite', 'voir'], ['finance', 'voir']] },
    enfants: [
      {
        id: 'finances_etudiantes.tableau',
        libelle: 'Vue d\'ensemble',
        chemin: '/scolarite/finances',
        droit: {
          curp: ['finances_etud.echeancier.consulter'],
          legacy: [['scolarite', 'voir']],
        },
      },
      {
        id: 'finances_etudiantes.frais',
        libelle: 'Frais de scolarité',
        chemin: '/finances-etudiantes/frais',
        ecran: 'frais_scolarite',
        droit: {
          curp: ['finances_etud.tarification.consulter', 'finances_etud.echeancier.consulter'],
          legacy: [['scolarite', 'voir'], ['finance', 'voir']],
        },
      },
      {
        id: 'finances_etudiantes.factures',
        libelle: 'Factures',
        chemin: '/finances-etudiantes/factures',
        ecran: 'factures',
        droit: {
          curp: ['finances_etud.facture.consulter'],
          legacy: [['scolarite', 'voir'], ['finance', 'voir']],
        },
      },
      {
        id: 'finances_etudiantes.paiements',
        libelle: 'Paiements',
        chemin: '/finances-etudiantes/paiements',
        ecran: 'paiements',
        droit: {
          curp: ['finances_etud.paiement.saisir', 'finances_etud.paiement.valider'],
          legacy: [['scolarite', 'voir'], ['finance', 'voir']],
        },
      },
      {
        id: 'finances_etudiantes.recus',
        libelle: 'Reçus',
        chemin: '/finances-etudiantes/recus',
        ecran: 'recus',
        droit: {
          curp: ['finances_etud.quittance.editer', 'finances_etud.paiement.valider'],
          legacy: [['scolarite', 'voir'], ['finance', 'voir']],
        },
      },
      {
        id: 'finances_etudiantes.bourses',
        libelle: 'Bourses & remboursements',
        chemin: '/finances-etudiantes/bourses',
        ecran: 'bourses',
        droit: {
          curp: ['finances_etud.remboursement.consulter'],
          legacy: [['scolarite', 'voir'], ['finance', 'voir']],
        },
      },
      {
        id: 'finances_etudiantes.situation',
        libelle: 'Situation financière',
        chemin: '/finances-etudiantes/situation',
        ecran: 'situation_financiere',
        droit: {
          curp: ['finances_etud.relance.consulter', 'finances_etud.rapprochement.consulter'],
          legacy: [['scolarite', 'voir'], ['finance', 'voir']],
        },
      },
      {
        id: 'finances_etudiantes.vacations',
        libelle: 'Vacations & encadrants',
        chemin: '/finance-encadrants',
        droit: {
          curp: ['finances_form.etat_vacation.editer', 'finances_form.heures_certifiees.consulter'],
          legacy: [['finance', 'exporter']],
        },
      },
      {
        id: 'finances_etudiantes.parametrage',
        libelle: 'Paramétrage finance',
        chemin: '/finance-parametrage',
        droit: {
          curp: ['finances_form.parametrage.administrer'],
          legacy: [['finance', 'parametrer']],
        },
      },
    ],
  },

  // -------------------------------------------------------------------- STAGES
  {
    id: 'stages',
    libelle: 'Stages',
    icone: 'bi-building',
    droit: { legacy: [['scolarite', 'voir']], curp: ['stages.organisme.consulter', 'stages.convention.creer'] },
    enfants: [
      {
        id: 'stages.conventions',
        libelle: 'Conventions',
        chemin: '/stages/conventions',
        ecran: 'stages_conventions',
        droit: {
          curp: ['stages.convention.creer', 'stages.convention.signer', 'stages.convention.valider'],
          legacy: [['scolarite', 'voir']],
        },
      },
      {
        id: 'stages.organismes',
        libelle: "Structures d'accueil",
        chemin: '/stages/organismes',
        ecran: 'stages_organismes',
        droit: {
          curp: ['stages.organisme.consulter'],
          legacy: [['scolarite', 'voir']],
        },
      },
      {
        id: 'stages.affectations',
        libelle: 'Affectations & tuteurs',
        chemin: '/stages/affectations',
        ecran: 'stages_affectations',
        droit: {
          curp: ['stages.tuteur.consulter'],
          legacy: [['scolarite', 'voir']],
        },
      },
      {
        id: 'stages.suivi',
        libelle: 'Suivi des stages',
        chemin: '/stages/suivi',
        ecran: 'stages_suivi',
        droit: {
          curp: ['stages.convention.valider', 'stages.convention.signer'],
          legacy: [['scolarite', 'voir']],
        },
      },
      {
        id: 'stages.evaluations',
        libelle: 'Évaluations',
        chemin: '/stages/evaluations',
        ecran: 'stages_evaluations',
        droit: {
          curp: ['stages.evaluation_stage.consulter'],
          legacy: [['scolarite', 'voir']],
        },
      },
    ],
  },

  // ------------------------------------------------------------------ PERSONNEL
  {
    id: 'personnel',
    libelle: 'Personnel',
    icone: 'bi-person-video3',
    droit: { legacy: [['web', 'operationnel']] },
    enfants: [
      {
        id: 'personnel.enseignants',
        libelle: 'Enseignants',
        chemin: '/formateurs',
        droit: {
          curp: ['enseignants.enseignant.consulter'],
          legacy: [['web', 'operationnel']],
        },
      },
      {
        id: 'personnel.agents',
        libelle: 'Personnel administratif',
        chemin: '/personnel/agents',
        ecran: 'rh_agents',
        droit: {
          curp: ['rh.agent.consulter'],
          legacy: [['web', 'operationnel']],
        },
      },
      {
        id: 'personnel.affectations',
        libelle: 'Affectations',
        chemin: '/personnel/affectations',
        ecran: 'rh_affectations',
        droit: {
          curp: ['rh.affectation_rh.consulter'],
          legacy: [['web', 'operationnel']],
        },
      },
      {
        id: 'personnel.charges',
        libelle: 'Charges / volumes horaires',
        chemin: '/scolarite/charges',
        droit: {
          curp: ['enseignants.charge.consulter', 'pedagogie.volume_horaire.consulter'],
          legacy: [['scolarite', 'voir']],
        },
      },
      {
        id: 'personnel.disponibilites',
        libelle: 'Disponibilités agents',
        chemin: '/personnel/disponibilites',
        ecran: 'rh_disponibilites',
        droit: {
          curp: ['rh.disponibilite_agent.consulter'],
          legacy: [['web', 'operationnel']],
        },
      },
      {
        id: 'personnel.documents',
        libelle: 'Documents RH',
        chemin: '/personnel/documents',
        ecran: 'rh_documents',
        droit: {
          curp: ['rh.document_rh.consulter', 'rh.document_rh.deposer'],
          legacy: [['web', 'operationnel']],
        },
      },
    ],
  },

  // --------------------------------------------------------------- ADMINISTRATION
  {
    id: 'administration',
    libelle: 'Administration',
    icone: 'bi-bank',
    droit: { legacy: [['web', 'operationnel']] },
    enfants: [
      {
        id: 'administration.services',
        libelle: 'Services',
        console: true,
        chemin: '/administration/services',
        ecran: 'organisation_services',
        droit: {
          // Console CURP : la garde serveur (`ExigeDrapeauAdmin`) exige le
          // drapeau `flag.curp_ui_admin` **et** le trio d'administration de
          // l'habilitation ; elle ne consulte aucune permission CURP. Aucun
          // volet `curp` n'est donc déclaré ici — en afficher un ferait voir
          // l'entrée à un compte gouverné qui recevrait un 403. La capacité
          // projetée `habilitations_admin.gerer` reproduit exactement la garde.
          legacy: [['habilitations_admin', 'gerer']],
        },
      },
      {
        id: 'administration.departements',
        libelle: 'Départements',
        console: true,
        chemin: '/administration/departements',
        ecran: 'organisation_departements',
        droit: {
          // Console CURP : la garde serveur (`ExigeDrapeauAdmin`) exige le
          // drapeau `flag.curp_ui_admin` **et** le trio d'administration de
          // l'habilitation ; elle ne consulte aucune permission CURP. Aucun
          // volet `curp` n'est donc déclaré ici — en afficher un ferait voir
          // l'entrée à un compte gouverné qui recevrait un 403. La capacité
          // projetée `habilitations_admin.gerer` reproduit exactement la garde.
          legacy: [['habilitations_admin', 'gerer']],
        },
      },
      {
        id: 'administration.directions',
        libelle: 'Directions',
        console: true,
        chemin: '/administration/directions',
        ecran: 'organisation_directions',
        droit: {
          // Console CURP : la garde serveur (`ExigeDrapeauAdmin`) exige le
          // drapeau `flag.curp_ui_admin` **et** le trio d'administration de
          // l'habilitation ; elle ne consulte aucune permission CURP. Aucun
          // volet `curp` n'est donc déclaré ici — en afficher un ferait voir
          // l'entrée à un compte gouverné qui recevrait un 403. La capacité
          // projetée `habilitations_admin.gerer` reproduit exactement la garde.
          legacy: [['habilitations_admin', 'gerer']],
        },
      },
      {
        id: 'administration.organisation',
        libelle: 'Directions / Départements / Services',
        chemin: '/organisation',
        droit: {
          curp: ['administrations.organigramme.consulter'],
          legacy: [['web', 'operationnel']],
        },
      },
      {
        id: 'administration.personnel',
        libelle: 'Personnel',
        chemin: '/personnel/agents',
        droit: {
          curp: ['rh.agent.consulter'],
          legacy: [['web', 'operationnel']],
        },
      },
      {
        id: 'administration.courrier',
        libelle: 'Courrier / Documents',
        chemin: '/administration/courrier',
        ecran: 'courrier_documents',
        droit: {
          curp: [
            'administrations.courrier.consulter',
            'administrations.document_officiel.consulter',
          ],
          legacy: [['web', 'operationnel']],
        },
      },
      {
        id: 'administration.reunions',
        libelle: 'Réunions & missions',
        chemin: '/administration/reunions',
        ecran: 'reunions_missions',
        droit: {
          curp: ['administrations.reunion.consulter', 'administrations.mission.consulter'],
          legacy: [['web', 'operationnel']],
        },
      },
      {
        id: 'administration.archives',
        libelle: 'Archives',
        chemin: '/archives',
        droit: {
          curp: ['administrations.version_document.consulter'],
          legacy: [['web', 'operationnel']],
          roles: ['ARCHIVE', 'DIRECTION', 'ADMIN', 'CHEF_INJS_ADMIN', 'INJS_ADMIN'],
        },
      },
      {
        // Sous-écrans de l'espace d'archivage (rôle ARCHIVE) : conservés tels
        // quels depuis l'ancienne barre latérale, aucun accès retiré.
        id: 'administration.archives_listes',
        libelle: 'Listes de notes archivées',
        chemin: '/archives/listes-notes',
        droit: {
          curp: ['administrations.version_document.consulter'],
          legacy: [['web', 'operationnel']],
          roles: ['ARCHIVE', 'DIRECTION', 'ADMIN', 'CHEF_INJS_ADMIN', 'INJS_ADMIN'],
        },
      },
      {
        id: 'administration.archives_cahiers',
        libelle: "Cahiers d'appel archivés",
        chemin: '/archives/cahiers-appel',
        droit: {
          curp: ['administrations.version_document.consulter'],
          legacy: [['web', 'operationnel']],
          roles: ['ARCHIVE', 'DIRECTION', 'ADMIN', 'CHEF_INJS_ADMIN', 'INJS_ADMIN'],
        },
      },
    ],
  },

  // ---------------------------------------------------------- UTILISATEURS & ACCÈS
  {
    id: 'utilisateurs',
    libelle: 'Utilisateurs & Accès',
    icone: 'bi-shield-lock',
    droit: { legacy: [['utilisateurs', 'voir'], ['habilitations_admin', 'gerer']] },
    enfants: [
      {
        id: 'utilisateurs.comptes',
        libelle: 'Comptes utilisateurs',
        console: true,
        chemin: '/administration/comptes',
        droit: {
          // Console CURP : la garde serveur (`ExigeDrapeauAdmin`) exige le
          // drapeau `flag.curp_ui_admin` **et** le trio d'administration de
          // l'habilitation ; elle ne consulte aucune permission CURP. Aucun
          // volet `curp` n'est donc déclaré ici — en afficher un ferait voir
          // l'entrée à un compte gouverné qui recevrait un 403. La capacité
          // projetée `habilitations_admin.gerer` reproduit exactement la garde.
          legacy: [['habilitations_admin', 'gerer']],
        },
      },
      {
        id: 'utilisateurs.roles',
        libelle: 'Rôles',
        console: true,
        chemin: '/administration/comptes/roles',
        droit: {
          // Console CURP : la garde serveur (`ExigeDrapeauAdmin`) exige le
          // drapeau `flag.curp_ui_admin` **et** le trio d'administration de
          // l'habilitation ; elle ne consulte aucune permission CURP. Aucun
          // volet `curp` n'est donc déclaré ici — en afficher un ferait voir
          // l'entrée à un compte gouverné qui recevrait un 403. La capacité
          // projetée `habilitations_admin.gerer` reproduit exactement la garde.
          legacy: [['habilitations_admin', 'gerer']],
        },
      },
      {
        id: 'utilisateurs.permissions',
        libelle: 'Permissions',
        console: true,
        chemin: '/administration/comptes/matrice',
        droit: {
          // Console CURP : la garde serveur (`ExigeDrapeauAdmin`) exige le
          // drapeau `flag.curp_ui_admin` **et** le trio d'administration de
          // l'habilitation ; elle ne consulte aucune permission CURP. Aucun
          // volet `curp` n'est donc déclaré ici — en afficher un ferait voir
          // l'entrée à un compte gouverné qui recevrait un 403. La capacité
          // projetée `habilitations_admin.gerer` reproduit exactement la garde.
          legacy: [['habilitations_admin', 'gerer']],
        },
      },
      {
        id: 'utilisateurs.catalogue_permissions',
        libelle: 'Catalogue des permissions',
        console: true,
        chemin: '/administration/comptes/permissions',
        droit: {
          // Couche IMPACT (additive) : mêmes garde et conventions que la
          // console CURP (voir commentaire ci-dessus).
          legacy: [['habilitations_admin', 'gerer']],
        },
      },
      {
        id: 'utilisateurs.organisation',
        libelle: 'Départements & Services',
        console: true,
        chemin: '/administration/comptes/organisation',
        droit: {
          // Console CURP : la garde serveur (`ExigeDrapeauAdmin`) exige le
          // drapeau `flag.curp_ui_admin` **et** le trio d'administration de
          // l'habilitation ; elle ne consulte aucune permission CURP. Aucun
          // volet `curp` n'est donc déclaré ici — en afficher un ferait voir
          // l'entrée à un compte gouverné qui recevrait un 403. La capacité
          // projetée `habilitations_admin.gerer` reproduit exactement la garde.
          legacy: [['habilitations_admin', 'gerer']],
        },
      },
      {
        id: 'utilisateurs.profils',
        libelle: 'Profils',
        chemin: '/users',
        droit: {
          curp: ['administration.personne.consulter'],
          legacy: [['utilisateurs', 'voir']],
        },
      },
      {
        id: 'utilisateurs.derogations',
        libelle: 'Dérogations',
        console: true,
        chemin: '/administration/comptes/derogations',
        droit: {
          // Console CURP : la garde serveur (`ExigeDrapeauAdmin`) exige le
          // drapeau `flag.curp_ui_admin` **et** le trio d'administration de
          // l'habilitation ; elle ne consulte aucune permission CURP. Aucun
          // volet `curp` n'est donc déclaré ici — en afficher un ferait voir
          // l'entrée à un compte gouverné qui recevrait un 403. La capacité
          // projetée `habilitations_admin.gerer` reproduit exactement la garde.
          legacy: [['habilitations_admin', 'gerer']],
        },
      },
      {
        id: 'utilisateurs.delegations',
        libelle: 'Délégations',
        console: true,
        chemin: '/administration/comptes/delegations',
        droit: {
          // Console CURP : la garde serveur (`ExigeDrapeauAdmin`) exige le
          // drapeau `flag.curp_ui_admin` **et** le trio d'administration de
          // l'habilitation ; elle ne consulte aucune permission CURP. Aucun
          // volet `curp` n'est donc déclaré ici — en afficher un ferait voir
          // l'entrée à un compte gouverné qui recevrait un 403. La capacité
          // projetée `habilitations_admin.gerer` reproduit exactement la garde.
          legacy: [['habilitations_admin', 'gerer']],
        },
      },
      {
        id: 'utilisateurs.revue',
        libelle: 'Revue des habilitations',
        console: true,
        chemin: '/administration/comptes/revue',
        droit: {
          // Console CURP : la garde serveur (`ExigeDrapeauAdmin`) exige le
          // drapeau `flag.curp_ui_admin` **et** le trio d'administration de
          // l'habilitation ; elle ne consulte aucune permission CURP. Aucun
          // volet `curp` n'est donc déclaré ici — en afficher un ferait voir
          // l'entrée à un compte gouverné qui recevrait un 403. La capacité
          // projetée `habilitations_admin.gerer` reproduit exactement la garde.
          legacy: [['habilitations_admin', 'gerer']],
        },
      },
      {
        id: 'utilisateurs.provisionnement',
        libelle: 'File de provisionnement',
        console: true,
        chemin: '/administration/comptes/provisionnement',
        droit: {
          // Console CURP : la garde serveur (`ExigeDrapeauAdmin`) exige le
          // drapeau `flag.curp_ui_admin` **et** le trio d'administration de
          // l'habilitation ; elle ne consulte aucune permission CURP. Aucun
          // volet `curp` n'est donc déclaré ici — en afficher un ferait voir
          // l'entrée à un compte gouverné qui recevrait un 403. La capacité
          // projetée `habilitations_admin.gerer` reproduit exactement la garde.
          legacy: [['habilitations_admin', 'gerer']],
        },
      },
      {
        id: 'utilisateurs.operations_masse',
        libelle: 'Opérations en masse',
        console: true,
        chemin: '/administration/comptes/operations-masse',
        droit: {
          // Console CURP : la garde serveur (`ExigeDrapeauAdmin`) exige le
          // drapeau `flag.curp_ui_admin` **et** le trio d'administration de
          // l'habilitation ; elle ne consulte aucune permission CURP. Aucun
          // volet `curp` n'est donc déclaré ici — en afficher un ferait voir
          // l'entrée à un compte gouverné qui recevrait un 403. La capacité
          // projetée `habilitations_admin.gerer` reproduit exactement la garde.
          legacy: [['habilitations_admin', 'gerer']],
        },
      },
      {
        id: 'utilisateurs.notifications',
        libelle: 'Notifications d\'échéance',
        console: true,
        chemin: '/administration/comptes/notifications',
        droit: {
          // Console CURP : la garde serveur (`ExigeDrapeauAdmin`) exige le
          // drapeau `flag.curp_ui_admin` **et** le trio d'administration de
          // l'habilitation ; elle ne consulte aucune permission CURP. Aucun
          // volet `curp` n'est donc déclaré ici — en afficher un ferait voir
          // l'entrée à un compte gouverné qui recevrait un 403. La capacité
          // projetée `habilitations_admin.gerer` reproduit exactement la garde.
          legacy: [['habilitations_admin', 'gerer']],
        },
      },
      {
        id: 'utilisateurs.journal',
        libelle: 'Journal des accès',
        console: true,
        chemin: '/administration/comptes/journal',
        droit: {
          // Console CURP : la garde serveur (`ExigeDrapeauAdmin`) exige le
          // drapeau `flag.curp_ui_admin` **et** le trio d'administration de
          // l'habilitation ; elle ne consulte aucune permission CURP. Aucun
          // volet `curp` n'est donc déclaré ici — en afficher un ferait voir
          // l'entrée à un compte gouverné qui recevrait un 403. La capacité
          // projetée `habilitations_admin.gerer` reproduit exactement la garde.
          legacy: [['habilitations_admin', 'gerer']],
        },
      },
      {
        id: 'utilisateurs.dashboard',
        libelle: 'Dashboard habilitations',
        console: true,
        chemin: '/administration/comptes/dashboard',
        droit: {
          // Couche IMPACT (additive) : mêmes garde et conventions que les
          // autres écrans de la console CURP (voir commentaire ci-dessus).
          legacy: [['habilitations_admin', 'gerer']],
        },
      },
      {
        id: 'utilisateurs.impact_permission',
        libelle: "Impact d'une permission",
        console: true,
        chemin: '/administration/comptes/impact-permission',
        droit: {
          legacy: [['habilitations_admin', 'gerer']],
        },
      },
      {
        id: 'utilisateurs.impact_role',
        libelle: "Impact d'un rôle",
        console: true,
        chemin: '/administration/comptes/impact-role',
        droit: {
          legacy: [['habilitations_admin', 'gerer']],
        },
      },
      {
        id: 'utilisateurs.impact_utilisateur',
        libelle: "Impact d'un utilisateur",
        console: true,
        chemin: '/administration/comptes/impact-utilisateur',
        droit: {
          legacy: [['habilitations_admin', 'gerer']],
        },
      },
      {
        id: 'utilisateurs.acces_effectifs',
        libelle: 'Accès effectifs',
        console: true,
        chemin: '/administration/comptes/acces-effectifs',
        droit: {
          legacy: [['habilitations_admin', 'gerer']],
        },
      },
      {
        id: 'utilisateurs.politique',
        libelle: 'Politique de sécurité',
        chemin: '/parametres',
        droit: {
          curp: ['administration.politique.administrer', 'parametres.parametre.administrer'],
          legacy: [['habilitations_admin', 'gerer']],
          roles: ['ADMIN', 'CHEF_INJS_ADMIN', 'INJS_ADMIN'],
        },
      },
    ],
  },

  // ---------------------------------------------------------------- STATISTIQUES
  {
    id: 'statistiques',
    libelle: 'Statistiques',
    icone: 'bi-bar-chart-line',
    droit: { legacy: [['statistiques', 'voir']] },
    enfants: [
      {
        id: 'statistiques.tableau',
        libelle: 'Tableau de bord',
        chemin: '/statistiques',
        droit: {
          curp: ['statistiques.tableau_bord.consulter'],
          legacy: [['statistiques', 'voir']],
        },
      },
      {
        id: 'statistiques.candidatures',
        libelle: 'Candidatures',
        chemin: '/statistiques/candidatures',
        ecran: 'stats_candidatures',
        droit: {
          curp: ['statistiques.indicateur.consulter'],
          legacy: [['statistiques', 'voir']],
        },
      },
      {
        id: 'statistiques.admissions',
        libelle: 'Admissions',
        chemin: '/statistiques/admissions',
        ecran: 'stats_admissions',
        droit: {
          curp: ['statistiques.indicateur.consulter'],
          legacy: [['statistiques', 'voir']],
        },
      },
      {
        id: 'statistiques.inscriptions',
        libelle: 'Inscriptions',
        chemin: '/statistiques/inscriptions',
        ecran: 'stats_inscriptions',
        droit: {
          curp: ['statistiques.indicateur.consulter'],
          legacy: [['statistiques', 'voir']],
        },
      },
      {
        id: 'statistiques.effectifs',
        libelle: 'Effectifs',
        chemin: '/statistiques/effectifs',
        ecran: 'stats_effectifs',
        droit: {
          curp: ['statistiques.indicateur.consulter'],
          legacy: [['statistiques', 'voir']],
        },
      },
      {
        id: 'statistiques.resultats',
        libelle: 'Résultats',
        chemin: '/statistiques/resultats',
        ecran: 'stats_resultats',
        droit: {
          curp: ['statistiques.indicateur.consulter'],
          legacy: [['statistiques', 'voir']],
        },
      },
      {
        id: 'statistiques.finances',
        libelle: 'Finances',
        chemin: '/statistiques/finances',
        ecran: 'stats_finances',
        droit: {
          curp: ['statistiques.bilan.editer', 'statistiques.indicateur.consulter'],
          legacy: [['statistiques', 'voir'], ['finance', 'voir']],
        },
      },
      {
        id: 'statistiques.rapports',
        libelle: 'Rapports',
        chemin: '/statistiques/rapports',
        ecran: 'stats_rapports',
        droit: {
          curp: ['statistiques.rapport.generer', 'statistiques.rapport.publier'],
          legacy: [['statistiques', 'voir']],
        },
      },
      {
        id: 'statistiques.alertes',
        libelle: 'Alertes & seuils',
        chemin: '/statistiques/alertes',
        ecran: 'stats_alertes',
        droit: {
          curp: ['statistiques.alerte.configurer'],
          legacy: [['statistiques', 'voir_globales']],
        },
      },
    ],
  },

  // ---------------------------------------------------------------- RÉFÉRENTIELS
  {
    id: 'referentiels',
    libelle: 'Référentiels',
    icone: 'bi-sliders',
    droit: {
      legacy: [['web', 'operationnel']],
      roles: ['ADMIN', 'CHEF_INJS_ADMIN', 'INJS_ADMIN'],
    },
    enfants: [
      {
        id: 'referentiels.tous',
        libelle: 'Tous les référentiels',
        chemin: '/referentiels',
        droit: {
          curp: ['referentiels.referentiel.consulter'],
          legacy: [['web', 'operationnel']],
          roles: ['ADMIN', 'CHEF_INJS_ADMIN', 'INJS_ADMIN'],
        },
      },
      {
        id: 'referentiels.annees',
        libelle: 'Années académiques',
        chemin: '/referentiels/annees',
        ecran: 'ref_annees',
        droit: {
          curp: ['scolarite.annee.consulter', 'referentiels.referentiel.consulter'],
          legacy: [['scolarite', 'voir']],
        },
      },
      {
        id: 'referentiels.etablissements',
        libelle: 'Établissements & sites',
        chemin: '/referentiels/etablissements',
        ecran: 'ref_etablissements',
        droit: {
          curp: ['referentiels.referentiel.consulter'],
          legacy: [['web', 'operationnel']],
        },
      },
      {
        id: 'referentiels.formations',
        libelle: 'Formations',
        chemin: '/referentiels/formations',
        ecran: 'ref_formations',
        droit: {
          curp: ['referentiels.referentiel.consulter'],
          legacy: [['web', 'operationnel']],
        },
      },
      {
        id: 'referentiels.filieres',
        libelle: 'Filières',
        chemin: '/referentiels/filieres',
        ecran: 'ref_filieres',
        droit: {
          curp: ['referentiels.referentiel.consulter'],
          legacy: [['web', 'operationnel']],
        },
      },
      {
        id: 'referentiels.ue_ecue',
        libelle: 'UE / ECUE',
        chemin: '/referentiels/ue-ecue',
        ecran: 'ref_ue_ecue',
        droit: {
          curp: ['pedagogie.ue.consulter', 'pedagogie.ecue.consulter'],
          legacy: [['web', 'operationnel']],
        },
      },
      {
        id: 'referentiels.niveaux',
        libelle: 'Niveaux',
        chemin: '/referentiels/niveaux',
        ecran: 'ref_niveaux',
        droit: {
          curp: ['referentiels.referentiel.consulter'],
          legacy: [['web', 'operationnel']],
        },
      },
      {
        id: 'referentiels.semestres',
        libelle: 'Semestres',
        chemin: '/referentiels/semestres',
        ecran: 'ref_semestres',
        droit: {
          curp: ['referentiels.referentiel.consulter'],
          legacy: [['web', 'operationnel']],
        },
      },
      {
        id: 'referentiels.types_cours',
        libelle: 'Types de cours',
        chemin: '/referentiels/types-cours',
        ecran: 'ref_types_cours',
        droit: {
          curp: ['referentiels.referentiel.consulter'],
          legacy: [['web', 'operationnel']],
        },
      },
      {
        id: 'referentiels.parametres_lmd',
        libelle: 'Paramètres LMD',
        chemin: '/parametres',
        droit: {
          curp: ['parametres.parametre.consulter'],
          legacy: [['web', 'operationnel']],
          roles: ['ADMIN', 'CHEF_INJS_ADMIN', 'INJS_ADMIN'],
        },
      },
      {
        id: 'referentiels.fonctionnalites',
        libelle: 'Fonctionnalités (drapeaux)',
        chemin: '/parametres/flags',
        droit: {
          curp: ['parametres.parametre.administrer'],
          legacy: [['web', 'operationnel']],
          roles: ['ADMIN', 'CHEF_INJS_ADMIN', 'INJS_ADMIN'],
        },
      },
      {
        // Import Excel (formations, modules, séances, participants) : même garde
        // que l'ancienne barre latérale (`peut(user, 'participants', 'gerer')`).
        id: 'referentiels.imports',
        libelle: 'Imports de données (Excel)',
        chemin: '/import',
        droit: {
          curp: ['scolarite.dossier_etudiant.creer', 'scolarite.inscription_administrative.creer'],
          legacy: [['participants', 'gerer']],
          roles: ['ADMIN', 'CHEF_INJS_ADMIN', 'INJS_ADMIN', 'CHEF_SECRETARIAT', 'SECRETARIAT'],
        },
      },
    ],
  },

  // ------------------------------------------------------------ AUDIT & TRAÇABILITÉ
  {
    id: 'audit',
    libelle: 'Audit & Traçabilité',
    icone: 'bi-search',
    droit: {
      legacy: [['habilitations_admin', 'gerer'], ['statistiques', 'voir_globales']],
      roles: ['ADMIN', 'CHEF_INJS_ADMIN', 'INJS_ADMIN', 'DIRECTION'],
    },
    enfants: [
      {
        id: 'audit.journal',
        libelle: "Journal d'audit",
        chemin: '/audit/journal',
        ecran: 'audit_journal',
        droit: {
          curp: ['administration.journal.consulter'],
          legacy: [['habilitations_admin', 'gerer']],
        },
      },
      {
        id: 'audit.actions',
        libelle: 'Actions utilisateurs',
        chemin: '/audit/actions',
        ecran: 'audit_actions',
        droit: {
          curp: ['administration.journal.consulter'],
          legacy: [['habilitations_admin', 'gerer']],
        },
      },
      {
        id: 'audit.modifications',
        libelle: 'Modifications',
        chemin: '/audit/modifications',
        ecran: 'audit_modifications',
        droit: {
          curp: ['administration.journal.consulter'],
          legacy: [['habilitations_admin', 'gerer']],
        },
      },
      {
        id: 'audit.securite',
        libelle: 'Événements de sécurité',
        chemin: '/audit/securite',
        ecran: 'audit_securite',
        droit: {
          curp: ['administration.journal.consulter'],
          legacy: [['habilitations_admin', 'gerer']],
        },
      },
      {
        id: 'audit.integrite',
        libelle: 'Intégrité de la chaîne',
        console: true,
        chemin: '/audit/integrite',
        ecran: 'audit_integrite',
        droit: {
          // Console CURP : la garde serveur (`ExigeDrapeauAdmin`) exige le
          // drapeau `flag.curp_ui_admin` **et** le trio d'administration de
          // l'habilitation ; elle ne consulte aucune permission CURP. Aucun
          // volet `curp` n'est donc déclaré ici — en afficher un ferait voir
          // l'entrée à un compte gouverné qui recevrait un 403. La capacité
          // projetée `habilitations_admin.gerer` reproduit exactement la garde.
          legacy: [['habilitations_admin', 'gerer']],
        },
      },
      {
        id: 'audit.archives',
        libelle: "Archives d'audit",
        console: true,
        chemin: '/audit/archives',
        ecran: 'audit_archives',
        droit: {
          // Console CURP : la garde serveur (`ExigeDrapeauAdmin`) exige le
          // drapeau `flag.curp_ui_admin` **et** le trio d'administration de
          // l'habilitation ; elle ne consulte aucune permission CURP. Aucun
          // volet `curp` n'est donc déclaré ici — en afficher un ferait voir
          // l'entrée à un compte gouverné qui recevrait un 403. La capacité
          // projetée `habilitations_admin.gerer` reproduit exactement la garde.
          legacy: [['habilitations_admin', 'gerer']],
        },
      },
    ],
  },
]

/** Entrées de pied de barre (hors arborescence, toujours présentes si autorisées). */
export const PIED_DE_BARRE = [
  {
    id: 'pied.notifications',
    libelle: 'Notifications',
    console: true,
    icone: 'bi-bell',
    chemin: '/administration/comptes/notifications',
    droit: {
      // Console CURP : la garde serveur (`ExigeDrapeauAdmin`) exige le
          // drapeau `flag.curp_ui_admin` **et** le trio d'administration de
          // l'habilitation ; elle ne consulte aucune permission CURP. Aucun
          // volet `curp` n'est donc déclaré ici — en afficher un ferait voir
          // l'entrée à un compte gouverné qui recevrait un 403. La capacité
          // projetée `habilitations_admin.gerer` reproduit exactement la garde.
      legacy: [['habilitations_admin', 'gerer']],
    },
  },
  {
    id: 'pied.aide',
    libelle: 'Aide',
    icone: 'bi-question-circle',
    chemin: '/aide',
    ecran: 'aide',
    droit: { legacy: [['web', 'acceder']] },
  },
]

/** Libellés de rôles legacy affichés sous l'identité (alignés App.jsx). */
export const LIBELLES_ROLES = {
  ADMIN: 'Administrateur',
  DIRECTION: 'Direction',
  CHEF_INJS_ADMIN: 'Chef INJS Admin',
  INJS_ADMIN: 'INJS Admin',
  CHEF_SECRETARIAT: 'Chef Secrétariat',
  SECRETARIAT: 'Secrétariat',
  FINANCE: 'Finance',
  ARCHIVE: 'Archiviste',
  ENCADRANT: 'Encadrant',
  SUPERVISEUR: 'Superviseur',
  FORMATEUR: 'Enseignant',
  AUDITEUR: 'Étudiant',
}

/** Aplati l'arborescence (sections + enfants + pied de barre). */
export function aplatir(arbre = ARBORESCENCE, pied = PIED_DE_BARRE) {
  const plat = []
  for (const section of arbre) {
    plat.push(section)
    for (const enfant of section.enfants || []) plat.push(enfant)
  }
  return [...plat, ...pied]
}

/** Entrées déclarant un écran générique (donc une route à enregistrer). */
export function entreesGeneriques(arbre = ARBORESCENCE, pied = PIED_DE_BARRE) {
  return aplatir(arbre, pied).filter((e) => e.ecran && e.chemin)
}

/** Toutes les entrées portant un chemin (pour la détection d'activité). */
export function cheminsConnus(arbre = ARBORESCENCE, pied = PIED_DE_BARRE) {
  return aplatir(arbre, pied)
    .map((e) => e.chemin)
    .filter(Boolean)
}

export default ARBORESCENCE
