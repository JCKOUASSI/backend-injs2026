/**
 * Descripteurs des **écrans génériques** de la navigation réorganisée.
 *
 * Chaque descripteur branche une entrée du menu sur un endpoint **existant** du
 * backend (aucune donnée inventée, aucun mock) : liste filtrable, fiche de
 * détail, actions de workflow, exports. Le rendu est assuré par
 * `components/generique/EcranRessource.jsx` (listes, onglets, indicateurs) et
 * `EcranDocuments.jsx` (génération de fichiers).
 *
 * Le champ `note` documente la source serveur de l'écran : c'est la trace, côté
 * interface, de l'endpoint réellement appelé (transparence d'audit).
 *
 * Approfondissement prévu « par lots » : un écran peut être remplacé par une
 * page dédiée (CRUD complet) sans toucher aux autres — il suffit de retirer son
 * `ecran` dans `menu/arborescence.js` et d'ajouter sa route.
 */

/** Ressources référentielles partagées (options de filtres et de documents). */
export const RESSOURCES = {
  formations: {
    optionsEndpoint: '/formations/ref/formations/',
    optionsCleValeur: 'id',
    optionsCleLibelle: 'intitule',
  },
  niveaux: {
    optionsEndpoint: '/scolarite/ref/niveaux/',
    optionsCleValeur: 'id',
    optionsCleLibelle: 'libelle',
  },
  annees: {
    optionsEndpoint: '/scolarite/ref/annees/',
    optionsCleValeur: 'id',
    optionsCleLibelle: 'libelle',
  },
  parcours: {
    optionsEndpoint: '/scolarite/ref/parcours/',
    optionsCleValeur: 'id',
    optionsCleLibelle: 'intitule',
  },
  groupes: {
    optionsEndpoint: '/scolarite/ref/groupes/',
    optionsCleValeur: 'id',
    optionsCleLibelle: 'nom',
  },
  etudiants: {
    optionsEndpoint: '/formations/participants/list/',
    optionsCleValeur: 'id',
    optionsCleLibelle: 'nom_complet',
  },
  directions: {
    optionsEndpoint: '/habilitations/organisation/directions/',
    optionsCleValeur: 'id',
    optionsCleLibelle: 'libelle',
  },
  departements: {
    optionsEndpoint: '/habilitations/organisation/departements/',
    optionsCleValeur: 'id',
    optionsCleLibelle: 'libelle',
  },
  maquettes: {
    optionsEndpoint: '/scolarite/maquettes/',
    optionsCleValeur: 'id',
    optionsCleLibelle: 'intitule',
  },
}

/** Actions d'audit disponibles (codes `presences.AuditLog.Action`). */
const ACTIONS_AUDIT_MODIFICATIONS = [
  { valeur: 'FORMATION_CREATE', libelle: 'Création de formation' },
  { valeur: 'FORMATION_UPDATE', libelle: 'Modification de formation' },
  { valeur: 'FORMATION_DELETE', libelle: 'Suppression de formation' },
  { valeur: 'FORMATION_STATUT', libelle: 'Changement de statut de formation' },
  { valeur: 'MODULE_CREATE', libelle: 'Création de module' },
  { valeur: 'MODULE_UPDATE', libelle: 'Modification de module' },
  { valeur: 'MODULE_DELETE', libelle: 'Suppression de module' },
  { valeur: 'MODULE_ARCHIVE', libelle: 'Archivage de module' },
  { valeur: 'MODULE_UNARCHIVE', libelle: 'Désarchivage de module' },
  { valeur: 'PARTICIPANT_CREATE', libelle: "Création d'auditeur" },
  { valeur: 'PARTICIPANT_UPDATE', libelle: "Modification d'auditeur" },
  { valeur: 'PARTICIPANT_DELETE', libelle: "Suppression d'auditeur" },
  { valeur: 'SEANCE_CREATE', libelle: 'Création de séance' },
  { valeur: 'SEANCE_UPDATE', libelle: 'Modification de séance' },
  { valeur: 'SEANCE_DELETE', libelle: 'Suppression de séance' },
]

const ACTIONS_AUDIT_SECURITE = [
  { valeur: 'USER_LOGIN', libelle: 'Connexion utilisateur' },
  { valeur: 'SCAN_SECURE_ENTREE', libelle: 'Scan sécurisé entrée (mobile)' },
  { valeur: 'SCAN_SECURE_SORTIE', libelle: 'Scan sécurisé sortie (mobile)' },
  { valeur: 'FORCE_ENTREE', libelle: 'Entrée forcée (encadrant/DFRC)' },
  { valeur: 'FORCE_SORTIE', libelle: 'Sortie forcée (encadrant/DFRC)' },
  { valeur: 'DEVICE_UNBIND', libelle: "Déliaison d'appareil" },
  { valeur: 'OUT_OF_GEOFENCE', libelle: 'Sortie du périmètre géographique' },
  { valeur: 'NO_HEARTBEAT', libelle: 'Alerte absence heartbeat' },
  { valeur: 'AUTO_EXIT', libelle: 'Sortie automatique' },
]

const FILTRES_AUDIT = [
  { param: 'date_debut', libelle: 'Depuis le', type: 'date' },
  { param: 'date_fin', libelle: "Jusqu'au", type: 'date' },
  { param: 'acteur_id', libelle: 'Auteur (id)', type: 'nombre' },
]

export const ECRANS = {

  // ---------------------------------------------------------------- SCOLARITÉ
  controle_dossiers: {
    id: 'controle_dossiers',
    titre: 'Contrôle des dossiers',
    titreListe: 'Dossiers de candidature',
    fil: 'Scolarité',
    icone: 'bi-folder-check',
    introduction: 'Dossiers de candidature et pièces déposées : consulter, '
      + 'vérifier la conformité puis valider ou rejeter chaque pièce.',
    endpoint: '/admissions/candidatures/',
    recherche: { param: 'search', libelle: 'Rechercher un dossier', placeholder: 'N°, nom, courriel…' },
    priorite: ['numero', 'candidat', 'statut', 'formation', 'type_candidature', 'date_creation'],
    detail: {
      titre: (l) => `Pièces du dossier ${l.numero || l.id}`,
      sousTitre: 'Pièces déposées',
      endpoint: (l) => `/admissions/candidatures/${l.id}/pieces/`,
      priorite: ['type_piece', 'statut', 'date_depot', 'obligatoire', 'motif'],
    },
    note: 'Source : /api/admissions/candidatures/ + /pieces/',
  },

  resultats_concours: {
    id: 'resultats_concours',
    titre: 'Résultats concours',
    titreListe: 'Résultats',
    fil: 'Scolarité',
    icone: 'bi-trophy',
    introduction: 'Campagnes de concours : classement calculé puis publié. '
      + 'Le calcul et la publication sont des actes tracés côté serveur.',
    endpoint: '/admissions/campagnes/',
    // La colonne « Libellé » (donnée de test « Debug ») est volontairement
    // exclue : la campagne est identifiée par sa formation + son année.
    exclure: ['libelle', 'code'],
    priorite: ['ref_formation_id', 'annee_academique_id', 'statut', 'nb_candidatures', 'nb_epreuves', 'date_ouverture', 'date_fermeture', 'quota_admissibles'],
    // 8 colonnes explicites : `colonnesPour` renvoie `ecran.colonnes` tel quel
    // quand il est renseigné (aucune troncature `maxColonnes`, aucune déduction).
    recherche: { param: 'search', libelle: 'Rechercher une campagne', placeholder: 'Formation, statut…' },
    filtres: [
      {
        param: 'statut', libelle: 'Statut', type: 'select',
        options: [
          { valeur: 'BROUILLON', libelle: 'Brouillon' },
          { valeur: 'PLANIFIEE', libelle: 'Planifiée' },
          { valeur: 'OUVERTE', libelle: 'Ouverte' },
          { valeur: 'SUSPENDUE', libelle: 'Suspendue' },
          { valeur: 'CLOTUREE', libelle: 'Clôturée' },
          { valeur: 'ANNULEE', libelle: 'Annulée' },
          { valeur: 'ARCHIVEE', libelle: 'Archivée' },
        ],
      },
      {
        param: 'ref_formation_id', libelle: 'Formation', type: 'select',
        optionsEndpoint: '/scolarite/ref/formations/',
        optionsCleValeur: 'id',
        optionsCleLibelle: 'intitule',
      },
      {
        param: 'annee_academique_id', libelle: 'Année', type: 'select',
        options: [
          { valeur: '2026-2027', libelle: '2026 – 2027' },
          { valeur: '2025-2026', libelle: '2025 – 2026' },
        ],
      },
    ],
    colonnes: [
      { cle: 'ref_formation_id', libelle: 'Formation' },
      { cle: 'annee_academique_id', libelle: 'Année' },
      {
        cle: 'statut', libelle: 'Statut', format: 'badge',
        couleurs: {
          BROUILLON: 'text-bg-secondary', PLANIFIEE: 'text-bg-info',
          OUVERTE: 'text-bg-success', SUSPENDUE: 'text-bg-warning',
          CLOTUREE: 'text-bg-dark', ANNULEE: 'text-bg-danger',
          ARCHIVEE: 'text-bg-dark',
        },
      },
      { cle: 'nb_candidatures', libelle: 'Candidatures' },
      { cle: 'nb_epreuves', libelle: 'Épreuves' },
      { cle: 'date_ouverture', libelle: 'Ouverture', format: 'date' },
      { cle: 'date_fermeture', libelle: 'Fermeture', format: 'date' },
      { cle: 'quota_admissibles', libelle: 'Quota admis.' },
    ],
    vide: 'Aucune campagne de concours pour ces critères.',
    detail: {
      titre: (l) => `Classement — ${l.ref_formation || l.annee_academique || `campagne ${l.id}`}`,
      sousTitre: 'Candidats classés',
      endpoint: (l) => `/admissions/campagnes/${l.id}/classement/`,
      priorite: ['rang', 'candidat', 'note', 'total', 'admissible', 'decision'],
    },
    actions: [
      {
        libelle: 'Calculer le classement',
        icone: 'bi-calculator',
        apparence: 'btn-outline-primary',
        methode: 'POST',
        chemin: (l) => `/admissions/campagnes/${l.id}/classement/calculer/`,
        confirmation: 'Calculer le classement de cette campagne ?',
        detail: 'Les notes des épreuves sont agrégées et les rangs recalculés.',
        succes: 'Classement calculé.',
      },
      {
        libelle: 'Publier',
        icone: 'bi-megaphone',
        apparence: 'btn-outline-success',
        methode: 'POST',
        chemin: (l) => `/admissions/campagnes/${l.id}/classement/publier/`,
        confirmation: 'Publier les résultats de cette campagne ?',
        detail: 'Acte officiel : la publication est journalisée et notifiée.',
        variant: 'danger',
        succes: 'Résultats publiés.',
      },
    ],
    note: 'Source : /api/admissions/campagnes/ + /classement/',
  },

  reinscriptions: {
    id: 'reinscriptions',
    titre: 'Réinscriptions & transferts',
    fil: 'Scolarité',
    icone: 'bi-arrow-repeat',
    introduction: 'Demandes de réinscription, transferts et passerelles entre '
      + 'parcours, telles que déposées dans le cycle de vie de scolarité.',
    endpoint: '/scolarite/reinscriptions/',
    recherche: { param: 'search', libelle: 'Rechercher', placeholder: 'Matricule, nom…' },
    priorite: [
      'matricule',
      'etudiant',
      'type_inscription_libelle',
      'ref_formation',
      'niveau',
      'annee_academique',
      'statut_libelle',
      'date_inscription',
    ],
    exclure: [
      'etudiant_id',
      'annee_academique_id',
      'ref_formation_id',
      'parcours_id',
      'niveau_id',
      'vague_id',
      'categorie_id',
      'grade_id',
      'regime_id',
      'admission_id',
      'type_inscription',
      'statut',
      'date_validation',
    ],
    vide: 'Aucune réinscription, transfert ou réorientation enregistré pour le moment.',
    note: 'Source : /api/scolarite/reinscriptions/',
  },

  journal_scolarite: {
    id: 'journal_scolarite',
    titre: 'Journal de scolarité',
    fil: 'Scolarité',
    icone: 'bi-journal-text',
    introduction: 'Événements du cycle de vie de chaque dossier étudiant '
      + '(inscriptions, transferts, radiations, décisions).',
    endpoint: '/scolarite/etudiants/',
    recherche: { param: 'search', libelle: 'Rechercher un étudiant', placeholder: 'Matricule, nom…' },
    priorite: ['matricule', 'nom', 'prenoms', 'statut', 'niveau', 'parcours'],
    detail: {
      titre: (l) => `Journal — ${l.nom || ''} ${l.prenoms || ''}`.trim(),
      sousTitre: 'Événements du dossier',
      endpoint: (l) => `/scolarite/etudiants/${l.id}/evenements/`,
      priorite: ['horodatage', 'type_evenement', 'libelle', 'auteur', 'motif'],
    },
    note: 'Source : /api/scolarite/etudiants/ + /evenements/',
  },

  documents_scolaires: {
    id: 'documents_scolaires',
    type: 'documents',
    titre: 'Documents scolaires',
    fil: 'Scolarité',
    icone: 'bi-file-earmark-text',
    introduction: 'Documents produits par le serveur (listes de classe, fiches '
      + 'de notes, relevés). Le droit de générer chaque document est vérifié '
      + 'côté backend à chaque appel.',
    documents: [
      {
        id: 'liste_classe',
        libelle: 'Liste de classe',
        icone: 'bi-people',
        description: 'Auditeurs par groupe pédagogique (PDF ou Excel).',
        parametres: [
          { cle: 'groupe', libelle: 'Groupe (facultatif)', type: 'select', requis: false, ...RESSOURCES.groupes },
          { cle: 'annee_academique_id', libelle: 'Année académique', type: 'select', requis: false, ...RESSOURCES.annees },
        ],
        formats: [
          { id: 'pdf', libelle: 'PDF', suffixe: 'pdf', icone: 'bi-file-earmark-pdf' },
          { id: 'excel', libelle: 'Excel', suffixe: 'xlsx', icone: 'bi-file-earmark-excel' },
        ],
        chemin: (v, f) => `/exports/participants/liste-classe/${f.id}/?${new URLSearchParams(
          Object.fromEntries(Object.entries(v).filter(([, x]) => x)),
        ).toString()}`,
      },
      {
        id: 'fiche_notes_module',
        libelle: 'Fiche de notes d\'un module',
        icone: 'bi-card-checklist',
        description: 'Fiche de notes par formation et module.',
        parametres: [
          { cle: 'formation', libelle: 'Formation', type: 'select', ...RESSOURCES.formations },
          { cle: 'module', libelle: 'Module (id)', type: 'nombre' },
        ],
        formats: [{ id: 'pdf', libelle: 'PDF', suffixe: 'pdf', icone: 'bi-file-earmark-pdf' }],
        chemin: (v) => `/formations/${v.formation}/modules/${v.module}/notes/fiche/pdf/`,
      },
      {
        id: 'releve_etudiant',
        libelle: "Relevé d'un étudiant",
        icone: 'bi-person-lines-fill',
        description: 'Fiche de notes individuelle (relevé).',
        parametres: [{ cle: 'etudiant', libelle: 'Étudiant', type: 'select', ...RESSOURCES.etudiants }],
        formats: [
          { id: 'pdf', libelle: 'PDF', suffixe: 'pdf', icone: 'bi-file-earmark-pdf' },
          { id: 'excel', libelle: 'Excel', suffixe: 'xlsx', icone: 'bi-file-earmark-excel' },
        ],
        chemin: (v, f) => `/participant/${v.etudiant}/notes-fiche/export/${f.id}/`,
      },
    ],
    note: 'Sources : /api/exports/, /api/formations/, /api/participant/',
  },

  // --------------------------------------------------------------- FORMATIONS
  filieres: {
    id: 'filieres',
    titre: 'Filières',
    fil: 'Formations',
    icone: 'bi-signpost-split',
    introduction: 'Types de formation (filières) du référentiel LMD.',
    endpoint: '/scolarite/ref/types-formation/',
    colonnes: [
      { cle: 'code', libelle: 'Code', largeur: '26%' },
      { cle: 'libelle', libelle: 'Libellé', largeur: '52%' },
      { cle: 'actif', libelle: 'Actif', format: 'booleen', largeur: '150px' },
    ],
    note: 'Source : /api/scolarite/ref/types-formation/',
  },

  parcours: {
    id: 'parcours',
    titre: 'Parcours',
    fil: 'Formations',
    icone: 'bi-diagram-3',
    introduction: 'Parcours rattachés aux formations et aux types de formation.',
    endpoint: '/scolarite/ref/parcours/',
    filtres: [
      { param: 'ref_formation_id', libelle: 'Formation', type: 'select', ...RESSOURCES.formations },
      { param: 'actif', libelle: 'Actifs seulement', type: 'select', options: [{ valeur: 'true', libelle: 'Oui' }] },
    ],
    colonnes: [
      { cle: 'code', libelle: 'Code' },
      { cle: 'intitule', libelle: 'Intitulé' },
      { cle: 'ref_formation_id', libelle: 'Formation' },
      { cle: 'type_formation_id', libelle: 'Filière' },
      { cle: 'actif', libelle: 'Actif', format: 'booleen' },
    ],
    note: 'Source : /api/scolarite/ref/parcours/',
  },

  niveaux: {
    id: 'niveaux',
    titre: 'Niveaux',
    fil: 'Formations',
    icone: 'bi-bar-chart-steps',
    introduction: 'Niveaux LMD (L1…M2), cycles et crédits requis.',
    endpoint: '/scolarite/ref/niveaux/',
    filtres: [{ param: 'cycle', libelle: 'Cycle', type: 'select', options: [
      { valeur: 'LICENCE', libelle: 'Licence' },
      { valeur: 'MASTER', libelle: 'Master' },
    ] }],
    colonnes: [
      { cle: 'code', libelle: 'Code' },
      { cle: 'libelle', libelle: 'Libellé' },
      { cle: 'cycle', libelle: 'Cycle' },
      { cle: 'ordre', libelle: 'Ordre' },
      { cle: 'credits_requis', libelle: 'Crédits requis' },
      { cle: 'actif', libelle: 'Actif', format: 'booleen' },
    ],
    note: 'Source : /api/scolarite/ref/niveaux/',
  },

  semestres: {
    id: 'semestres',
    titre: 'Semestres',
    fil: 'Formations',
    icone: 'bi-calendar3',
    introduction: 'Semestres par niveau.',
    endpoint: '/scolarite/ref/semestres/',
    filtres: [{ param: 'niveau_id', libelle: 'Niveau', type: 'select', ...RESSOURCES.niveaux }],
    colonnes: [
      { cle: 'numero', libelle: 'N°' },
      { cle: 'libelle', libelle: 'Libellé' },
      { cle: 'niveau_id', libelle: 'Niveau' },
      { cle: 'actif', libelle: 'Actif', format: 'booleen' },
    ],
    note: 'Source : /api/scolarite/ref/semestres/',
  },

  ue_ecue: {
    id: 'ue_ecue',
    titre: 'UE / ECUE',
    fil: 'Formations',
    icone: 'bi-collection',
    introduction: "Unités d'enseignement et éléments constitutifs, lus depuis "
      + 'les maquettes LMD validées. Sélectionner une maquette pour dérouler '
      + 'ses UE, puis une UE pour ses ECUE.',
    endpoint: '/scolarite/maquettes/',
    priorite: ['code', 'intitule', 'statut', 'annee_academique', 'niveau', 'version'],
    detail: {
      titre: (l) => `UE de la maquette ${l.code || l.id}`,
      sousTitre: "Unités d'enseignement",
      endpoint: (l) => `/scolarite/maquettes/${l.id}/ues/`,
      priorite: ['code', 'intitule', 'semestre', 'credits', 'heures', 'statut'],
    },
    note: 'Source : /api/scolarite/maquettes/ + /ues/',
  },

  // ----------------------------------------------------------------- GET-INJS
  salles_espaces: {
    id: 'salles_espaces',
    titre: 'Salles & espaces',
    fil: 'GET-INJS',
    icone: 'bi-door-open',
    introduction: 'Espaces physiques mobilisables par les emplois du temps : '
      + 'salles, bâtiments, sites et espaces sportifs.',
    onglets: [
      {
        id: 'salles',
        libelle: 'Salles',
        icone: 'bi-door-closed',
        endpoint: '/formations/ref/salles/',
        note: 'Source : /api/formations/ref/salles/',
      },
      {
        id: 'batiments',
        libelle: 'Bâtiments',
        icone: 'bi-buildings',
        endpoint: '/formations/ref/batiments/',
        note: 'Source : /api/formations/ref/batiments/',
      },
      {
        id: 'sites',
        libelle: 'Sites',
        icone: 'bi-geo-alt',
        endpoint: '/formations/ref/sites/',
        note: 'Source : /api/formations/ref/sites/',
      },
      {
        id: 'espaces_sportifs',
        libelle: 'Espaces sportifs',
        icone: 'bi-dribbble',
        endpoint: '/referentiels/types-espace-sportif/',
        note: 'Source : /api/referentiels/types-espace-sportif/',
      },
    ],
  },

  disponibilites: {
    id: 'disponibilites',
    titre: 'Disponibilités',
    fil: 'GET-INJS',
    icone: 'bi-calendar-check',
    introduction: 'Indisponibilités déclarées des enseignants (socle scolarité) '
      + 'et créneaux indisponibles, prises en compte par la génération '
      + 'automatique des emplois du temps. Les congés/absences du personnel '
      + 'relèvent du module RH (onglet supprimé ici faute de données '
      + 'd’indisponibilité exposées par /api/rh/).',
    onglets: [
      {
        id: 'enseignants',
        libelle: 'Enseignants',
        icone: 'bi-person-video3',
        endpoint: '/enseignants/indisponibilites/',
        note: 'Source : /api/enseignants/indisponibilites/',
      },
      {
        id: 'edt',
        libelle: 'Créneaux EDT',
        icone: 'bi-calendar-week',
        endpoint: '/scolarite/edt/indisponibilites/',
        note: 'Source : /api/scolarite/edt/indisponibilites/',
      },
    ],
  },

  conflits_edt: {
    id: 'conflits_edt',
    titre: 'Conflits & contraintes',
    fil: 'GET-INJS',
    icone: 'bi-exclamation-octagon',
    introduction: 'Conflits détectés sur les emplois du temps (chevauchements '
      + 'd\'enseignants, de groupes ou de salles, y compris entre emplois du '
      + 'temps distincts). La détection se relance depuis l\'écran '
      + '« Tableau des emplois du temps ».',
    endpoint: '/edts/conflits/',
    filtres: [
      { param: 'actif', libelle: 'Statut', type: 'select', options: [
        { valeur: 'true', libelle: 'Actifs' },
        { valeur: 'false', libelle: 'Clôturés' },
      ] },
      { param: 'type_conflit', libelle: 'Type', type: 'select', options: [
        { valeur: 'HORAIRE_ENSEIGNANT', libelle: 'Enseignant' },
        { valeur: 'HORAIRE_GROUPETUDIANT', libelle: 'Groupe' },
        { valeur: 'HORAIRE_SALLE', libelle: 'Salle' },
        { valeur: 'HORAIRE_MODULE', libelle: 'Formation' },
        { valeur: 'MANUEL', libelle: 'Signalement manuel' },
      ] },
    ],
    colonnes: [
      { cle: 'type_conflit', libelle: 'Type', format: 'badge', valeurs: {
        HORAIRE_ENSEIGNANT: 'Enseignant', HORAIRE_GROUPETUDIANT: 'Groupe',
        HORAIRE_SALLE: 'Salle', HORAIRE_MODULE: 'Formation', MANUEL: 'Manuel',
      }, couleurs: {
        HORAIRE_ENSEIGNANT: 'text-bg-danger',
        HORAIRE_GROUPETUDIANT: 'text-bg-warning',
        HORAIRE_SALLE: 'text-bg-info',
        HORAIRE_MODULE: 'text-bg-secondary',
        MANUEL: 'text-bg-dark',
      } },
      { cle: 'emploi_du_temps', libelle: 'Emploi du temps' },
      { cle: 'description', libelle: 'Explication' },
      { cle: 'actif', libelle: 'Actif', format: 'booleen' },
      { cle: 'signale_par', libelle: 'Signalé par' },
      { cle: 'recalcule_le', libelle: 'Détecté le' },
    ],
    actions: [
      {
        libelle: 'Résoudre',
        icone: 'bi-check2-circle',
        apparence: 'btn-outline-success',
        methode: 'POST',
        chemin: (l) => `/edts/conflits/${l.id}/resoudre/`,
        confirmation: 'Marquer ce conflit comme résolu ?',
        detail: 'La résolution est enregistrée et tracée côté serveur.',
        succes: 'Conflit résolu.',
        visible: (l) => l.actif !== false,
      },
    ],
    note: 'Source : /api/edts/conflits/',
  },

  export_edt: {
    id: 'export_edt',
    type: 'documents',
    titre: 'Export / Impression',
    fil: 'GET-INJS',
    icone: 'bi-printer',
    introduction: "Contrats d'export des emplois du temps produits par le "
      + 'serveur au format CSV (ouverture directe dans Excel, accents '
      + 'préservés) : groupes, enseignements, étudiants, créneaux, '
      + 'affectations et indisponibilités.',
    documents: [
      ...[
        ['groupes', 'Groupes', 'bi-people'],
        ['enseignements', 'Enseignements', 'bi-book'],
        ['etudiants', 'Étudiants', 'bi-person'],
        ['creneaux', 'Créneaux', 'bi-clock'],
        ['affectations', 'Affectations', 'bi-diagram-2'],
        ['indisponibilites', 'Indisponibilités', 'bi-calendar-x'],
      ].map(([ressource, libelle, icone]) => ({
        id: ressource,
        libelle: `${libelle} (CSV)`,
        icone,
        description: `Export CSV — ${libelle.toLowerCase()} de l'année courante.`,
        parametres: [
          { cle: 'annee_academique_id', libelle: 'Année académique', type: 'select', requis: false, ...RESSOURCES.annees },
        ],
        formats: [{ id: 'csv', libelle: 'CSV', suffixe: 'csv', icone: 'bi-filetype-csv' }],
        chemin: (v) => `/scolarite/edt/${ressource}/?export=csv&${new URLSearchParams(
          Object.fromEntries(Object.entries(v).filter(([, x]) => x)),
        ).toString()}`,
      })),
    ],
    note: 'Source : /api/scolarite/edt/* (paramètre export=csv)',
  },

  // --------------------------------------------------------------- ÉVALUATIONS
  saisie_notes: {
    id: 'saisie_notes',
    titre: 'Saisie des notes',
    fil: 'Évaluations',
    icone: 'bi-pencil-square',
    introduction: 'Modules du catalogue : ouvrir la grille de saisie des notes '
      + "d'un module pour une formation. La saisie elle-même reste sur l'écran "
      + 'dédié, gardé par le backend.',
    endpoint: '/formations/ref/modules/',
    recherche: { param: 'search', libelle: 'Rechercher un module', placeholder: 'Intitulé…' },
    colonnes: [
      { cle: 'intitule', libelle: 'Module' },
      {
        cle: 'formations',
        libelle: 'Formations',
        valeur: (l) => (l.formations || []).map((f) => f.intitule).join(', '),
      },
      { cle: 'volume_horaire', libelle: 'Volume horaire' },
      { cle: 'actif', libelle: 'Actif', format: 'booleen' },
    ],
    actions: [
      {
        libelle: 'Saisir les notes',
        icone: 'bi-pencil-square',
        apparence: 'btn-outline-primary',
        vers: (l) => ((l.formation_ids || [])[0]
          ? `/formations/${l.formation_ids[0]}/modules/${l.id}/notes`
          : null),
      },
    ],
    note: 'Source : /api/formations/ref/modules/',
  },

  controle_notes: {
    id: 'controle_notes',
    titre: 'Contrôle des notes',
    fil: 'Évaluations',
    icone: 'bi-clipboard-data',
    introduction: 'Contrôle et validation des notes saisies : historique et '
      + 'workflow de validation par module.',
    endpoint: '/formations/ref/modules/',
    recherche: { param: 'search', libelle: 'Rechercher un module', placeholder: 'Intitulé…' },
    colonnes: [
      { cle: 'intitule', libelle: 'Module' },
      {
        cle: 'formations',
        libelle: 'Formations',
        valeur: (l) => (l.formations || []).map((f) => f.intitule).join(', '),
      },
      { cle: 'actif', libelle: 'Actif', format: 'booleen' },
    ],
    actions: [
      {
        libelle: 'Ouvrir le contrôle',
        icone: 'bi-box-arrow-up-right',
        apparence: 'btn-outline-secondary',
        vers: (l) => ((l.formation_ids || [])[0]
          ? `/formations/${l.formation_ids[0]}/modules/${l.id}/notes`
          : null),
      },
    ],
    note: 'Source : /api/formations/ref/modules/ + workflow de notes',
  },

  // NOTE — `deliberations_notes` et `resultats_notes` ont été SUPPRIMÉS.
  // Ces descripteurs pointaient sur `/formations/list/` (des formations, pas
  // des délibérations ni des résultats) et déclaraient une route concurrente
  // pour `/evaluations/deliberations` et `/evaluations/resultats`.
  // Ces sous-modules sont désormais rendus par les composants métier dédiés
  // d'App.jsx, branchés sur la VRAIE API :
  //   - Délibérations → `/api/jurys/` (moteur LMD/ECTS, source de vérité) ;
  //   - Résultats    → `/api/evaluations-academiques/resultats/{ecue,ue,semestre}/`.

  releves_notes: {
    id: 'releves_notes',
    type: 'documents',
    titre: 'Relevés de notes',
    fil: 'Évaluations',
    icone: 'bi-file-earmark-ruled',
    introduction: 'Relevés individuels produits par le serveur. Un étudiant '
      + 'doit être sélectionné : le fichier est généré puis téléchargé.',
    documents: [
      {
        id: 'releve_individuel',
        libelle: 'Relevé individuel',
        icone: 'bi-person-lines-fill',
        description: 'Fiche de notes complète (PDF ou Excel).',
        parametres: [{ cle: 'etudiant', libelle: 'Étudiant', type: 'select', ...RESSOURCES.etudiants }],
        formats: [
          { id: 'pdf', libelle: 'PDF', suffixe: 'pdf', icone: 'bi-file-earmark-pdf' },
          { id: 'excel', libelle: 'Excel', suffixe: 'xlsx', icone: 'bi-file-earmark-excel' },
        ],
        chemin: (v, f) => `/participant/${v.etudiant}/notes-fiche/export/${f.id}/`,
      },
      {
        id: 'liste_classe_notes',
        libelle: 'Liste de classe',
        icone: 'bi-people',
        description: 'Liste des auditeurs par groupe (PDF ou Excel).',
        parametres: [
          { cle: 'groupe', libelle: 'Groupe (facultatif)', type: 'select', requis: false, ...RESSOURCES.groupes },
        ],
        formats: [
          { id: 'pdf', libelle: 'PDF', suffixe: 'pdf', icone: 'bi-file-earmark-pdf' },
          { id: 'excel', libelle: 'Excel', suffixe: 'xlsx', icone: 'bi-file-earmark-excel' },
        ],
        chemin: (v, f) => `/exports/participants/liste-classe/${f.id}/?${new URLSearchParams(
          Object.fromEntries(Object.entries(v).filter(([, x]) => x)),
        ).toString()}`,
      },
    ],
    note: 'Sources : /api/participant/, /api/exports/',
  },

  // -------------------------------------------------------------------- JURYS
  jury_composition: {
    id: 'jury_composition',
    titre: 'Composition des jurys',
    fil: 'Jurys',
    icone: 'bi-people',
    introduction: 'Membres de chaque session de jury (président, membres, '
      + 'suppléants) et leur rôle.',
    endpoint: '/juries/sessions/',
    // Priorités alignées sur le CONTRAT RÉEL de `_serializer_session` :
    // SessionJury n'a pas de `reference`/`date_debut`/`date_fin`.
    priorite: ['libelle', 'statut', 'type_session', 'annee_academique_id', 'niveau_id', 'ref_formation_id'],
    detail: {
      titre: (l) => `Composition — ${l.libelle || l.id}`,
      sousTitre: 'Membres du jury',
      endpoint: (l) => `/juries/sessions/${l.id}/membres/`,
      // Contrat réel de `_serializer_membre` (nom + nom_affiche + fonction).
      priorite: ['nom', 'nom_affiche', 'fonction', 'user_id'],
    },
    note: 'Source : /api/juries/sessions/ + /membres/',
  },

  jury_deliberations: {
    id: 'jury_deliberations',
    titre: 'Délibérations de jury',
    fil: 'Jurys',
    icone: 'bi-chat-square-text',
    introduction: 'Propositions calculées et décisions prises en délibération. '
      + 'Les propositions et décisions ne sont jamais supprimées (append-only).',
    endpoint: '/juries/sessions/',
    priorite: ['libelle', 'statut', 'type_session', 'annee_academique_id', 'niveau_id', 'ref_formation_id'],
    detail: {
      titre: (l) => `Délibération — ${l.libelle || l.id}`,
      sousTitre: 'Décisions de la session',
      // `/decisions/` est une saisie (POST) : la consultation passe par le
      // détail de session, qui expose déjà `decisions` et `propositions`.
      endpoint: (l) => `/juries/sessions/${l.id}/`,
      // Champs réels de `_serializer_session(detail=True)`.
      priorite: ['matricule', 'nom', 'decision', 'moyenne_generale', 'credits_acquis', 'mention', 'decision_manuelle', 'justification'],
    },
    actions: [
      {
        libelle: 'Calculer les propositions',
        icone: 'bi-calculator',
        apparence: 'btn-outline-primary',
        methode: 'POST',
        chemin: (l) => `/juries/sessions/${l.id}/action/`,
        corps: { action: 'calcul' },
        confirmation: 'Calculer les propositions de cette session ?',
        succes: 'Propositions calculées.',
      },
    ],
    note: 'Source : /api/juries/sessions/ + /decisions/ + /action/',
  },

  jury_pv: {
    id: 'jury_pv',
    titre: 'PV de jury',
    fil: 'Jurys',
    icone: 'bi-file-earmark-text',
    introduction: 'Procès-verbaux : génération, signature et publication. Actes '
      + 'réservés au personnel autorisé et tracés côté serveur.',
    endpoint: '/juries/sessions/',
    priorite: ['libelle', 'statut', 'type_session', 'annee_academique_id', 'niveau_id', 'ref_formation_id'],
    detail: {
      titre: (l) => `PV — ${l.libelle || l.id}`,
      sousTitre: 'Procès-verbal',
      // `/pv/` renvoie un FICHIER (FileResponse) : il ne peut pas alimenter
      // un tableau de détail JSON. Le PV est exposé par le détail de session.
      endpoint: (l) => `/juries/sessions/${l.id}/`,
      // Champs réels de `_serializer_pv` (exposés sous `pv`).
      priorite: ['sha256', 'genere_le', 'fichier'],
    },
    actions: [
      {
        libelle: 'Générer le PV',
        icone: 'bi-file-earmark-plus',
        apparence: 'btn-outline-primary',
        methode: 'POST',
        chemin: (l) => `/juries/sessions/${l.id}/action/`,
        corps: { action: 'generer_pv' },
        confirmation: 'Générer le procès-verbal de cette session ?',
        detail: 'Réservé au personnel autorisé (contrôle serveur).',
        succes: 'PV généré.',
      },
    ],
    note: 'Source : /api/juries/sessions/ + /pv/ + /action/',
  },

  jury_validation: {
    id: 'jury_validation',
    titre: 'Validation des résultats',
    fil: 'Jurys',
    icone: 'bi-patch-check',
    introduction: 'Transition, vérification des décisions puis publication des '
      + 'résultats de la session.',
    endpoint: '/juries/sessions/',
    priorite: ['libelle', 'statut', 'type_session', 'annee_academique_id', 'niveau_id', 'ref_formation_id'],
    actions: [
      {
        libelle: 'Vérifier les décisions',
        icone: 'bi-list-check',
        apparence: 'btn-outline-secondary',
        methode: 'POST',
        chemin: (l) => `/juries/sessions/${l.id}/action/`,
        corps: { action: 'verifier_decisions' },
        succes: 'Décisions vérifiées.',
      },
      {
        libelle: 'Transition',
        icone: 'bi-arrow-right-circle',
        apparence: 'btn-outline-primary',
        methode: 'POST',
        chemin: (l) => `/juries/sessions/${l.id}/action/`,
        corps: { action: 'transition' },
        confirmation: 'Faire avancer la session à l\'étape suivante ?',
        succes: 'Session mise à jour.',
      },
      {
        libelle: 'Publier',
        icone: 'bi-megaphone',
        apparence: 'btn-outline-success',
        methode: 'POST',
        chemin: (l) => `/juries/sessions/${l.id}/action/`,
        corps: { action: 'publier' },
        confirmation: 'Publier les résultats de cette session ?',
        detail: 'Acte officiel : publication journalisée, réservée au personnel autorisé.',
        variant: 'danger',
        succes: 'Résultats publiés.',
      },
    ],
    note: 'Source : /api/juries/sessions/ + /action/',
  },

  // -------------------------------------------------------------- DIPLÔMATION
  eligibilite_diplome: {
    id: 'eligibilite_diplome',
    titre: 'Éligibilité aux diplômes',
    fil: 'Diplômation',
    icone: 'bi-person-check',
    introduction: 'Dossiers de diplôme constitués et leur état de validation '
      + '(crédits acquis, décisions de jury, pièces).',
    endpoint: '/graduation/diplomes/',
    recherche: { param: 'search', libelle: 'Rechercher', placeholder: 'Nom, matricule…' },
    priorite: ['reference', 'etudiant', 'diplome', 'statut', 'annee_academique', 'date_validation'],
    note: 'Source : /api/graduation/diplomes/',
  },

  attestations: {
    id: 'attestations',
    titre: 'Attestations',
    fil: 'Diplômation',
    icone: 'bi-file-earmark-check',
    introduction: 'Attestations de réussite produites à partir des diplômes '
      + 'validés (édition PDF serveur).',
    endpoint: '/graduation/diplomes/',
    priorite: ['reference', 'etudiant', 'diplome', 'statut', 'date_validation'],
    actions: [
      {
        libelle: 'Attestation PDF',
        icone: 'bi-file-earmark-pdf',
        apparence: 'btn-outline-primary',
        telechargement: true,
        chemin: (l) => `/graduation/diplomes/${l.id}/pdf/`,
        succes: 'Attestation téléchargée.',
      },
    ],
    note: 'Source : /api/graduation/diplomes/ + /pdf/',
  },

  certificats: {
    id: 'certificats',
    titre: 'Certificats & modèles',
    fil: 'Diplômation',
    icone: 'bi-patch-plus',
    introduction: 'Modèles de documents officiels (diplômes, attestations, '
      + 'certificats) utilisés pour la génération.',
    endpoint: '/graduation/modeles/',
    priorite: ['code', 'libelle', 'type', 'actif', 'version'],
    note: 'Source : /api/graduation/modeles/',
  },

  registres_diplomes: {
    id: 'registres_diplomes',
    titre: 'Registres des diplômes',
    fil: 'Diplômation',
    icone: 'bi-journals',
    introduction: 'Registres officiels de délivrance (numérotation, mentions, '
      + 'vérification par jeton).',
    endpoint: '/graduation/registres/',
    priorite: ['reference', 'libelle', 'annee_academique', 'statut', 'nombre_diplomes'],
    note: 'Source : /api/graduation/registres/',
  },

  // ------------------------------------------------------- FINANCES ÉTUDIANTES
  frais_scolarite: {
    id: 'frais_scolarite',
    titre: 'Frais de scolarité',
    fil: 'Finances étudiantes',
    icone: 'bi-receipt',
    introduction: 'Échéanciers de frais par étudiant : montants, échéances et '
      + 'soldes.',
    endpoint: '/finances-etudiantes/echeanciers/',
    recherche: { param: 'search', libelle: 'Rechercher', placeholder: 'Étudiant, référence…' },
    priorite: ['reference', 'etudiant', 'montant_total', 'montant_paye', 'statut', 'annee_academique'],
    detail: {
      titre: (l) => `Échéances — ${l.reference || l.id}`,
      sousTitre: 'Lignes de l\'échéancier',
      endpoint: (l) => `/finances-etudiantes/echeanciers/${l.id}/lignes/`,
      priorite: ['libelle', 'montant', 'date_echeance', 'statut', 'paye'],
    },
    note: 'Source : /api/finances-etudiantes/echeanciers/ + /lignes/',
  },

  factures: {
    id: 'factures',
    titre: 'Factures',
    fil: 'Finances étudiantes',
    icone: 'bi-file-earmark-plus',
    introduction: 'Facturation des échéanciers : la facture est générée par le '
      + 'serveur à partir des lignes de l\'échéancier.',
    endpoint: '/finances-etudiantes/echeanciers/',
    priorite: ['reference', 'etudiant', 'montant_total', 'statut', 'annee_academique'],
    actions: [
      {
        libelle: 'Générer la facture',
        icone: 'bi-receipt-cutoff',
        apparence: 'btn-outline-primary',
        methode: 'POST',
        chemin: (l) => `/finances-etudiantes/echeanciers/${l.id}/facture/`,
        confirmation: 'Générer la facture de cet échéancier ?',
        succes: 'Facture générée.',
      },
    ],
    note: 'Source : /api/finances-etudiantes/echeanciers/ + /facture/',
  },

  paiements: {
    id: 'paiements',
    titre: 'Paiements',
    fil: 'Finances étudiantes',
    icone: 'bi-cash-stack',
    introduction: 'Paiements enregistrés et leur confirmation (validation '
      + 'serveur, acte tracé).',
    endpoint: '/finances-etudiantes/paiements/',
    recherche: { param: 'search', libelle: 'Rechercher', placeholder: 'Référence, étudiant…' },
    filtres: [
      { param: 'date_debut', libelle: 'Depuis le', type: 'date' },
      { param: 'date_fin', libelle: 'Jusqu\'au', type: 'date' },
    ],
    priorite: ['reference', 'etudiant', 'montant', 'mode_paiement', 'date_paiement', 'statut'],
    actions: [
      {
        libelle: 'Confirmer',
        icone: 'bi-check2-circle',
        apparence: 'btn-outline-success',
        methode: 'POST',
        chemin: (l) => `/finances-etudiantes/paiements/${l.id}/confirmer/`,
        confirmation: 'Confirmer ce paiement ?',
        detail: 'La confirmation met à jour l\'échéancier et le reçu.',
        succes: 'Paiement confirmé.',
      },
    ],
    note: 'Source : /api/finances-etudiantes/paiements/ + /confirmer/',
  },

  recus: {
    id: 'recus',
    titre: 'Reçus & quittances',
    fil: 'Finances étudiantes',
    icone: 'bi-receipt-cutoff',
    introduction: 'Quittances émises pour les paiements confirmés.',
    endpoint: '/finances-etudiantes/quittances/',
    recherche: { param: 'search', libelle: 'Rechercher', placeholder: 'N° de quittance…' },
    priorite: ['numero', 'etudiant', 'paiement', 'montant', 'date_emission'],
    note: 'Source : /api/finances-etudiantes/quittances/',
  },

  bourses: {
    id: 'bourses',
    titre: 'Bourses & remboursements',
    fil: 'Finances étudiantes',
    icone: 'bi-gift',
    introduction: 'Remboursements et régularisations (bourses, trop-perçus, '
      + 'annulations).',
    endpoint: '/finances-etudiantes/remboursements/',
    priorite: ['reference', 'etudiant', 'montant', 'motif', 'statut', 'date_creation'],
    note: 'Source : /api/finances-etudiantes/remboursements/',
  },

  situation_financiere: {
    id: 'situation_financiere',
    titre: 'Situation financière',
    fil: 'Finances étudiantes',
    icone: 'bi-clipboard-data',
    introduction: 'Suivi des impayés (relances) et rapprochements bancaires.',
    onglets: [
      {
        id: 'relances',
        libelle: 'Relances',
        icone: 'bi-bell',
        endpoint: '/finances-etudiantes/relances/',
        priorite: ['reference', 'etudiant', 'niveau', 'montant_du', 'date_envoi', 'statut'],
        note: 'Source : /api/finances-etudiantes/relances/',
      },
      {
        id: 'rapprochements',
        libelle: 'Rapprochements',
        icone: 'bi-bank',
        endpoint: '/finances-etudiantes/rapprochements/',
        priorite: ['reference', 'date', 'montant', 'statut', 'banque'],
        note: 'Source : /api/finances-etudiantes/rapprochements/',
      },
    ],
  },

  // ------------------------------------------------------------------- STAGES
  stages_conventions: {
    id: 'stages_conventions',
    titre: 'Conventions de stage',
    fil: 'Stages',
    icone: 'bi-file-earmark-text',
    introduction: 'Conventions : création, validation, signature et édition PDF.',
    endpoint: '/stages/conventions/',
    recherche: { param: 'search', libelle: 'Rechercher', placeholder: 'Étudiant, structure…' },
    priorite: ['reference', 'etudiant', 'organisme', 'date_debut', 'date_fin', 'statut'],
    actions: [
      {
        libelle: 'Étape suivante',
        icone: 'bi-arrow-right-circle',
        apparence: 'btn-outline-primary',
        methode: 'POST',
        chemin: (l) => `/stages/conventions/${l.id}/transition/`,
        confirmation: 'Faire avancer cette convention ?',
        succes: 'Convention mise à jour.',
      },
      {
        libelle: 'PDF',
        icone: 'bi-file-earmark-pdf',
        apparence: 'btn-outline-secondary',
        telechargement: true,
        chemin: (l) => `/stages/conventions/${l.id}/pdf/`,
        succes: 'Convention téléchargée.',
      },
    ],
    note: 'Source : /api/stages/conventions/',
  },

  stages_organismes: {
    id: 'stages_organismes',
    titre: "Structures d'accueil",
    fil: 'Stages',
    icone: 'bi-building',
    introduction: 'Structures d\'accueil référencées (entreprises, clubs, '
      + 'administrations).',
    endpoint: '/stages/organismes/',
    recherche: { param: 'search', libelle: 'Rechercher', placeholder: 'Raison sociale…' },
    priorite: ['nom', 'raison_sociale', 'type', 'ville', 'contact', 'actif'],
    note: 'Source : /api/stages/organismes/',
  },

  stages_affectations: {
    id: 'stages_affectations',
    titre: 'Affectations & tuteurs',
    fil: 'Stages',
    icone: 'bi-person-badge',
    introduction: 'Tuteurs (pédagogiques et professionnels) et affectations des '
      + 'stagiaires.',
    endpoint: '/stages/tuteurs/',
    priorite: ['nom', 'prenoms', 'type', 'organisme', 'email', 'telephone'],
    note: 'Source : /api/stages/tuteurs/',
  },

  stages_suivi: {
    id: 'stages_suivi',
    titre: 'Suivi des stages',
    fil: 'Stages',
    icone: 'bi-eye',
    introduction: 'Conventions en cours : suivi des périodes, des validations '
      + 'et des alertes.',
    endpoint: '/stages/conventions/',
    recherche: { param: 'search', libelle: 'Rechercher', placeholder: 'Étudiant, structure…' },
    priorite: ['reference', 'etudiant', 'organisme', 'date_debut', 'date_fin', 'statut'],
    note: 'Source : /api/stages/conventions/',
  },

  stages_evaluations: {
    id: 'stages_evaluations',
    titre: 'Évaluations de stage',
    fil: 'Stages',
    icone: 'bi-star',
    introduction: 'Évaluations renseignées par les tuteurs et les jurys de stage.',
    endpoint: '/stages/evaluations/',
    priorite: ['convention', 'etudiant', 'evaluateur', 'note', 'statut', 'date_evaluation'],
    note: 'Source : /api/stages/evaluations/',
  },

  // ----------------------------------------------------------------- PERSONNEL
  rh_agents: {
    id: 'rh_agents',
    titre: 'Personnel administratif',
    fil: 'Personnel',
    icone: 'bi-person-badge',
    introduction: 'Agents de l\'établissement : fonctions, services et '
      + 'affectations.',
    endpoint: '/rh/agents/',
    recherche: { param: 'search', libelle: 'Rechercher', placeholder: 'Nom, matricule…' },
    priorite: ['matricule', 'nom', 'prenoms', 'fonction', 'service', 'statut'],
    detail: {
      titre: (l) => `Disponibilités — ${l.nom || ''} ${l.prenoms || ''}`.trim(),
      sousTitre: 'Disponibilités déclarées',
      endpoint: (l) => `/rh/agents/${l.id}/disponibilites/`,
      priorite: ['date', 'jour', 'heure_debut', 'heure_fin', 'type', 'motif'],
    },
    actions: [
      {
        libelle: 'Affecter',
        icone: 'bi-arrow-left-right',
        apparence: 'btn-outline-primary',
        methode: 'POST',
        chemin: (l) => `/rh/agents/${l.id}/affecter/`,
        confirmation: 'Ouvrir l\'affectation de cet agent ?',
        detail: 'L\'affectation effective est enregistrée par le serveur après contrôle.',
        erreur: 'Affectation refusée par le serveur.',
        succes: 'Affectation enregistrée.',
      },
    ],
    note: 'Source : /api/rh/agents/ + /disponibilites/',
  },

  rh_affectations: {
    id: 'rh_affectations',
    titre: 'Affectations du personnel',
    fil: 'Personnel',
    icone: 'bi-diagram-2',
    introduction: 'Services et fonctions du référentiel RH utilisés pour les '
      + 'affectations.',
    onglets: [
      {
        id: 'services',
        libelle: 'Services',
        icone: 'bi-building',
        endpoint: '/rh/services/',
        recherche: { param: 'q', libelle: 'Rechercher un service' },
        note: 'Source : /api/rh/services/',
      },
      {
        id: 'fonctions',
        libelle: 'Fonctions',
        icone: 'bi-briefcase',
        endpoint: '/rh/fonctions/',
        note: 'Source : /api/rh/fonctions/',
      },
    ],
  },

  rh_disponibilites: {
    id: 'rh_disponibilites',
    titre: 'Disponibilités des agents',
    fil: 'Personnel',
    icone: 'bi-calendar-check',
    introduction: 'Disponibilités déclarées par agent (sélectionner un agent '
      + 'pour voir ses créneaux).',
    endpoint: '/rh/agents/',
    recherche: { param: 'search', libelle: 'Rechercher', placeholder: 'Nom, matricule…' },
    priorite: ['matricule', 'nom', 'prenoms', 'fonction', 'service'],
    detail: {
      titre: (l) => `Disponibilités — ${l.nom || ''} ${l.prenoms || ''}`.trim(),
      sousTitre: 'Créneaux déclarés',
      endpoint: (l) => `/rh/agents/${l.id}/disponibilites/`,
      priorite: ['date', 'jour', 'heure_debut', 'heure_fin', 'type', 'motif'],
    },
    note: 'Source : /api/rh/agents/ + /disponibilites/',
  },

  rh_documents: {
    id: 'rh_documents',
    titre: 'Documents RH',
    fil: 'Personnel',
    icone: 'bi-folder-symlink',
    introduction: 'Documents administratifs du personnel déposés et classés.',
    endpoint: '/rh/documents/',
    priorite: ['reference', 'type', 'agent', 'date_depot', 'statut'],
    note: 'Source : /api/rh/documents/',
  },

  // ------------------------------------------------------------ ADMINISTRATION
  organisation_directions: {
    id: 'organisation_directions',
    titre: 'Directions',
    fil: 'Administration',
    icone: 'bi-diagram-3-fill',
    introduction: 'Directions de l\'établissement (créées au LOT 1 du module '
      + 'Utilisateurs).',
    endpoint: '/habilitations/organisation/directions/',
    colonnes: [
      { cle: 'code', libelle: 'Code' },
      { cle: 'libelle', libelle: 'Libellé' },
      { cle: 'description', libelle: 'Description' },
      { cle: 'actif', libelle: 'Actif', format: 'booleen' },
    ],
    detail: {
      titre: (l) => `Départements — ${l.libelle || l.code}`,
      sousTitre: 'Départements rattachés',
      endpoint: (l) => `/habilitations/organisation/departements/?direction=${l.id}`,
      colonnes: [
        { cle: 'code', libelle: 'Code' },
        { cle: 'libelle', libelle: 'Libellé' },
        { cle: 'actif', libelle: 'Actif', format: 'booleen' },
      ],
    },
    note: 'Source : /api/habilitations/organisation/directions/',
  },

  organisation_departements: {
    id: 'organisation_departements',
    titre: 'Départements',
    fil: 'Administration',
    icone: 'bi-diagram-3',
    introduction: 'Départements rattachés aux directions.',
    endpoint: '/habilitations/organisation/departements/',
    filtres: [{ param: 'direction', libelle: 'Direction', type: 'select', ...RESSOURCES.directions }],
    colonnes: [
      { cle: 'code', libelle: 'Code' },
      { cle: 'libelle', libelle: 'Libellé' },
      { cle: 'direction_libelle', libelle: 'Direction' },
      { cle: 'actif', libelle: 'Actif', format: 'booleen' },
    ],
    detail: {
      titre: (l) => `Comptes rattachés — ${l.libelle || l.code}`,
      sousTitre: 'Comptes utilisateurs',
      endpoint: (l) => `/habilitations/organisation/departements/${l.id}/comptes/`,
      priorite: ['username', 'nom', 'prenoms', 'statut', 'roles'],
    },
    note: 'Source : /api/habilitations/organisation/departements/',
  },

  organisation_services: {
    id: 'organisation_services',
    titre: 'Services',
    fil: 'Administration',
    icone: 'bi-building',
    introduction: 'Services et secrétariats, hiérarchisés sous les départements.',
    endpoint: '/habilitations/organisation/services/',
    recherche: { param: 'q', libelle: 'Rechercher un service' },
    filtres: [{ param: 'departement', libelle: 'Département', type: 'select', ...RESSOURCES.departements }],
    colonnes: [
      { cle: 'numero', libelle: 'Numéro' },
      { cle: 'nom', libelle: 'Nom' },
      { cle: 'departement_libelle', libelle: 'Département' },
      { cle: 'actif', libelle: 'Actif', format: 'booleen' },
    ],
    detail: {
      titre: (l) => `Comptes rattachés — ${l.nom || l.numero}`,
      sousTitre: 'Comptes utilisateurs',
      endpoint: (l) => `/habilitations/organisation/services/${l.id}/comptes/`,
      priorite: ['username', 'nom', 'prenoms', 'statut', 'roles'],
    },
    note: 'Source : /api/habilitations/organisation/services/',
  },

  courrier_documents: {
    id: 'courrier_documents',
    titre: 'Courrier / Documents',
    fil: 'Administration',
    icone: 'bi-envelope-paper',
    introduction: 'Courriers entrants/sortants et documents officiels, avec '
      + 'leurs circuits de validation.',
    onglets: [
      {
        id: 'courriers',
        libelle: 'Courriers',
        icone: 'bi-envelope',
        endpoint: '/administrations/courriers/',
        priorite: ['reference', 'objet', 'sens', 'date', 'statut', 'destinataire'],
        actions: [
          {
            libelle: 'Étape suivante',
            icone: 'bi-arrow-right-circle',
            apparence: 'btn-outline-primary',
            methode: 'POST',
            chemin: (l) => `/administrations/courriers/${l.id}/transition/`,
            confirmation: 'Faire avancer ce courrier ?',
            succes: 'Courrier mis à jour.',
          },
        ],
        note: 'Source : /api/administrations/courriers/',
      },
      {
        id: 'documents',
        libelle: 'Documents officiels',
        icone: 'bi-file-earmark-text',
        endpoint: '/administrations/documents/',
        priorite: ['reference', 'titre', 'type', 'date', 'statut', 'version'],
        actions: [
          {
            libelle: 'Étape suivante',
            icone: 'bi-arrow-right-circle',
            apparence: 'btn-outline-primary',
            methode: 'POST',
            chemin: (l) => `/administrations/documents/${l.id}/transition/`,
            confirmation: 'Faire avancer ce document ?',
            succes: 'Document mis à jour.',
          },
        ],
        note: 'Source : /api/administrations/documents/',
      },
    ],
  },

  reunions_missions: {
    id: 'reunions_missions',
    titre: 'Réunions & missions',
    fil: 'Administration',
    icone: 'bi-calendar-event',
    introduction: 'Réunions institutionnelles et ordres de mission.',
    onglets: [
      {
        id: 'reunions',
        libelle: 'Réunions',
        icone: 'bi-people',
        endpoint: '/administrations/reunions/',
        priorite: ['objet', 'date', 'lieu', 'statut', 'organisateur'],
        note: 'Source : /api/administrations/reunions/',
      },
      {
        id: 'missions',
        libelle: 'Missions',
        icone: 'bi-airplane',
        endpoint: '/administrations/missions/',
        priorite: ['objet', 'agent', 'date_debut', 'date_fin', 'lieu', 'statut'],
        note: 'Source : /api/administrations/missions/',
      },
    ],
  },

  // -------------------------------------------------------------- STATISTIQUES
  stats_candidatures: {
    id: 'stats_candidatures',
    type: 'indicateurs',
    titre: 'Statistiques — Candidatures',
    fil: 'Statistiques',
    icone: 'bi-file-earmark-person',
    introduction: 'Indicateurs de candidature calculés par le serveur.',
    endpoint: '/admissions/candidatures/stats/',
    note: 'Source : /api/admissions/candidatures/stats/',
  },

  stats_admissions: {
    id: 'stats_admissions',
    type: 'indicateurs',
    titre: 'Statistiques — Admissions',
    fil: 'Statistiques',
    icone: 'bi-check2-circle',
    introduction: 'Indicateurs d\'admission (décisions, taux, répartitions).',
    endpoint: '/admissions/admissions/stats/',
    note: 'Source : /api/admissions/admissions/stats/',
  },

  stats_inscriptions: {
    id: 'stats_inscriptions',
    type: 'indicateurs',
    titre: 'Statistiques — Inscriptions',
    fil: 'Statistiques',
    icone: 'bi-journal-check',
    introduction: 'Indicateurs d\'inscription administrative et pédagogique.',
    endpoint: '/scolarite/inscriptions/stats/',
    note: 'Source : /api/scolarite/inscriptions/stats/',
  },

  stats_effectifs: {
    id: 'stats_effectifs',
    titre: 'Effectifs',
    fil: 'Statistiques',
    icone: 'bi-people-fill',
    introduction: 'Effectifs par groupe pédagogique et capacités.',
    endpoint: '/scolarite/groupes/effectifs/',
    note: 'Source : /api/scolarite/groupes/effectifs/',
  },

  stats_resultats: {
    id: 'stats_resultats',
    titre: 'Résultats',
    fil: 'Statistiques',
    icone: 'bi-graph-up-arrow',
    introduction: 'Bilans de résultats publiés par le service statistiques.',
    endpoint: '/statistiques/bilans/',
    note: 'Source : /api/statistiques/bilans/',
  },

  stats_finances: {
    id: 'stats_finances',
    type: 'indicateurs',
    titre: 'Statistiques — Finances',
    fil: 'Statistiques',
    icone: 'bi-cash-coin',
    introduction: 'Bilan financier des formations (FAC) calculé par le serveur.',
    endpoint: '/statistiques/bilan-fac/',
    // L'endpoint exige formation_id (400 sinon) : le descripteur impose le
    // filtre et le moteur attend sa valeur avant d'appeler le serveur.
    filtres: [
      {
        param: 'formation_id',
        libelle: 'Formation',
        type: 'select',
        requis: true,
        tous: 'Choisir une formation…',
        ...RESSOURCES.formations,
      },
    ],
    note: 'Source : /api/statistiques/bilan-fac/',
  },

  stats_rapports: {
    id: 'stats_rapports',
    titre: 'Rapports',
    fil: 'Statistiques',
    icone: 'bi-file-earmark-bar-graph',
    introduction: 'Rapports statistiques et leur circuit de validation '
      + '(observations, workflow).',
    endpoint: '/statistiques/rapports/',
    priorite: ['reference', 'titre', 'periode', 'statut', 'date_creation', 'auteur'],
    detail: {
      titre: (l) => `Rapport — ${l.reference || l.titre || l.id}`,
      sousTitre: 'Observations',
      endpoint: (l) => `/statistiques/rapports/${l.id}/observations/`,
      priorite: ['date', 'auteur', 'commentaire', 'statut'],
    },
    note: 'Source : /api/statistiques/rapports/ + /observations/',
  },

  stats_alertes: {
    id: 'stats_alertes',
    titre: 'Alertes & seuils',
    fil: 'Statistiques',
    icone: 'bi-bell',
    introduction: 'Seuils d\'alerte paramétrés et alertes déclenchées.',
    onglets: [
      {
        id: 'seuils',
        libelle: 'Seuils',
        icone: 'bi-sliders',
        endpoint: '/statistiques/alertes/seuils/',
        note: 'Source : /api/statistiques/alertes/seuils/',
      },
      {
        id: 'alertes',
        libelle: 'Alertes',
        icone: 'bi-exclamation-triangle',
        endpoint: '/stats/alertes/',
        note: 'Source : /api/stats/alertes/',
      },
    ],
  },

  // -------------------------------------------------------------- RÉFÉRENTIELS
  ref_annees: {
    id: 'ref_annees',
    titre: 'Années académiques',
    fil: 'Référentiels',
    icone: 'bi-calendar-range',
    introduction: 'Années académiques : période, année courante, clôture et '
      + 'réouverture (actes tracés).',
    endpoint: '/scolarite/ref/annees/',
    colonnes: [
      { cle: 'libelle', libelle: 'Libellé' },
      { cle: 'date_debut', libelle: 'Début', format: 'date' },
      { cle: 'date_fin', libelle: 'Fin', format: 'date' },
      { cle: 'courante', libelle: 'Courante', format: 'booleen' },
      { cle: 'actif', libelle: 'Actif', format: 'booleen' },
    ],
    actions: [
      {
        libelle: 'Clôturer',
        icone: 'bi-lock',
        apparence: 'btn-outline-warning',
        methode: 'POST',
        chemin: (l) => `/scolarite/annees/${l.id}/cloturer/`,
        confirmation: 'Clôturer cette année académique ?',
        detail: 'La clôture bloque les saisies de l\'année.',
        variant: 'danger',
        succes: 'Année clôturée.',
      },
      {
        libelle: 'Rouvrir',
        icone: 'bi-unlock',
        apparence: 'btn-outline-secondary',
        methode: 'POST',
        chemin: (l) => `/scolarite/annees/${l.id}/rouvrir/`,
        confirmation: 'Rouvrir cette année académique ?',
        succes: 'Année rouverte.',
      },
    ],
    note: 'Source : /api/scolarite/ref/annees/ + /cloturer/ + /rouvrir/',
  },

  ref_etablissements: {
    id: 'ref_etablissements',
    titre: 'Établissements & sites',
    fil: 'Référentiels',
    icone: 'bi-geo-alt',
    introduction: 'Implantations de l\'établissement : sites, bâtiments et salles.',
    onglets: [
      {
        id: 'sites',
        libelle: 'Sites',
        icone: 'bi-geo',
        endpoint: '/formations/ref/sites/',
        note: 'Source : /api/formations/ref/sites/',
      },
      {
        id: 'batiments',
        libelle: 'Bâtiments',
        icone: 'bi-buildings',
        endpoint: '/formations/ref/batiments/',
        note: 'Source : /api/formations/ref/batiments/',
      },
      {
        id: 'salles',
        libelle: 'Salles',
        icone: 'bi-door-closed',
        endpoint: '/formations/ref/salles/',
        note: 'Source : /api/formations/ref/salles/',
      },
    ],
  },

  ref_formations: {
    id: 'ref_formations',
    titre: 'Formations (référentiel)',
    fil: 'Référentiels',
    icone: 'bi-book',
    introduction: 'Référentiel des formations LMD.',
    endpoint: '/formations/ref/formations/',
    colonnes: [
      { cle: 'id', libelle: 'ID' },
      { cle: 'code', libelle: 'Code' },
      { cle: 'intitule', libelle: 'Intitulé' },
      { cle: 'type_diplome', libelle: 'Diplôme' },
      { cle: 'domaine', libelle: 'Domaine' },
      { cle: 'mention', libelle: 'Mention' },
      { cle: 'duree_annees', libelle: 'Durée (ans)' },
      { cle: 'nb_credites', libelle: 'Crédits ECTS' },
      { cle: 'actif', libelle: 'Actif', format: 'booleen' },
    ],
    note: 'Source : /api/formations/ref/formations/ — descripteur de cycle (modèle 04.4).',
  },

  ref_filieres: {
    id: 'ref_filieres',
    titre: 'Filières (référentiel)',
    fil: 'Référentiels',
    icone: 'bi-signpost-split',
    introduction: 'Types de formation du référentiel.',
    endpoint: '/scolarite/ref/types-formation/',
    colonnes: [
      { cle: 'code', libelle: 'Code', largeur: '26%' },
      { cle: 'libelle', libelle: 'Libellé', largeur: '52%' },
      { cle: 'actif', libelle: 'Actif', format: 'booleen', largeur: '150px' },
    ],
    note: 'Source : /api/scolarite/ref/types-formation/',
  },

  ref_ue_ecue: {
    id: 'ref_ue_ecue',
    titre: 'UE / ECUE (référentiel)',
    fil: 'Référentiels',
    icone: 'bi-collection',
    introduction: "Unités d'enseignement et ECUE portés par les maquettes LMD.",
    endpoint: '/scolarite/maquettes/',
    priorite: ['code', 'intitule', 'statut', 'niveau', 'annee_academique'],
    detail: {
      titre: (l) => `UE — maquette ${l.code || l.id}`,
      sousTitre: "Unités d'enseignement",
      endpoint: (l) => `/scolarite/maquettes/${l.id}/ues/`,
      priorite: ['code', 'intitule', 'semestre', 'credits'],
    },
    note: 'Source : /api/scolarite/maquettes/ + /ues/',
  },

  ref_niveaux: {
    id: 'ref_niveaux',
    titre: 'Niveaux (référentiel)',
    fil: 'Référentiels',
    icone: 'bi-bar-chart-steps',
    introduction: 'Niveaux du cursus (L1, L2, L3, M1, M2…) rattachés à un cycle. '
      + 'Lecture et mise à jour du référentiel partagé par toutes les maquettes.',
    endpoint: '/scolarite/ref/niveaux/',
    colonnes: [
      { cle: 'code', libelle: 'Code' },
      { cle: 'libelle', libelle: 'Libellé' },
      { cle: 'cycle', libelle: 'Cycle' },
      { cle: 'ordre', libelle: 'Ordre' },
      { cle: 'credits_requis', libelle: 'Crédits requis' },
      { cle: 'actif', libelle: 'Actif', format: 'booleen' },
    ],
    note: 'Source : /api/scolarite/ref/niveaux/',
  },

  ref_semestres: {
    id: 'ref_semestres',
    titre: 'Semestres (référentiel)',
    fil: 'Référentiels',
    icone: 'bi-calendar3',
    introduction: 'Semestres d\'enseignement rattachés à un niveau : base de la '
      + 'répartition des unités d\'enseignement et des sessions d\'examen.',
    endpoint: '/scolarite/ref/semestres/',
    filtres: [{ param: 'niveau_id', libelle: 'Niveau', type: 'select', ...RESSOURCES.niveaux }],
    colonnes: [
      { cle: 'numero', libelle: 'N°' },
      { cle: 'libelle', libelle: 'Libellé' },
      { cle: 'niveau_id', libelle: 'Niveau' },
      { cle: 'actif', libelle: 'Actif', format: 'booleen' },
    ],
    note: 'Source : /api/scolarite/ref/semestres/',
  },

  ref_types_cours: {
    id: 'ref_types_cours',
    titre: 'Types de cours & catégories',
    fil: 'Référentiels',
    icone: 'bi-tags',
    introduction: 'Catégories de cours, types de candidature, voies d\'accès, '
      + 'types d\'évaluation et de document.',
    onglets: [
      {
        id: 'categories',
        libelle: 'Catégories de cours',
        icone: 'bi-tag',
        endpoint: '/formations/ref/categories/',
        note: 'Source : /api/formations/ref/categories/',
      },
      {
        id: 'grades',
        libelle: 'Grades',
        icone: 'bi-award',
        endpoint: '/formations/ref/grades/',
        note: 'Source : /api/formations/ref/grades/',
      },
      {
        id: 'vagues',
        libelle: 'Vagues',
        icone: 'bi-water',
        endpoint: '/formations/ref/vagues/',
        note: 'Source : /api/formations/ref/vagues/',
      },
      {
        id: 'types_evaluation',
        libelle: "Types d'évaluation",
        icone: 'bi-clipboard-check',
        endpoint: '/referentiels/types-evaluation/',
        note: 'Source : /api/referentiels/types-evaluation/',
      },
      {
        id: 'types_document',
        libelle: 'Types de document',
        icone: 'bi-file-earmark',
        endpoint: '/referentiels/types-document/',
        note: 'Source : /api/referentiels/types-document/',
      },
      {
        id: 'voies_acces',
        libelle: "Voies d'accès",
        icone: 'bi-signpost',
        endpoint: '/admissions/ref/voies-acces/',
        note: 'Source : /api/admissions/ref/voies-acces/',
      },
    ],
  },

  // ------------------------------------------------------- AUDIT & TRAÇABILITÉ
  audit_journal: {
    id: 'audit_journal',
    titre: "Journal d'audit",
    fil: 'Audit & Traçabilité',
    icone: 'bi-journal-text',
    introduction: 'Journal unifié des actions critiques (badgeage, formations, '
      + 'séances, auditeurs, connexions). Lecture seule : aucune ligne ne peut '
      + 'être modifiée ou supprimée.',
    endpoint: '/audit-logs/',
    recherche: { param: 'cible_numero', libelle: 'Rechercher une cible', placeholder: 'N° auditeur, formateur…' },
    filtres: FILTRES_AUDIT,
    colonnes: [
      { cle: 'timestamp', libelle: 'Horodatage', format: 'datetime' },
      { cle: 'action_label', libelle: 'Action' },
      { cle: 'acteur_label', libelle: 'Auteur' },
      { cle: 'acteur_role', libelle: 'Rôle' },
      { cle: 'cible_nom', libelle: 'Cible' },
      { cle: 'cible_numero', libelle: 'N° cible' },
      { cle: 'ip_address', libelle: 'IP' },
    ],
    note: 'Source : /api/audit-logs/ (journal append-only)',
  },

  audit_actions: {
    id: 'audit_actions',
    titre: 'Actions utilisateurs',
    fil: 'Audit & Traçabilité',
    icone: 'bi-person-lines-fill',
    introduction: 'Actions filtrées par auteur : qui a fait quoi, quand, depuis '
      + 'quelle adresse IP.',
    endpoint: '/audit-logs/',
    recherche: { param: 'cible_numero', libelle: 'Rechercher une cible' },
    filtres: [
      { param: 'acteur_id', libelle: 'Auteur (identifiant)', type: 'nombre' },
      { param: 'date_debut', libelle: 'Depuis le', type: 'date' },
      { param: 'date_fin', libelle: 'Jusqu\'au', type: 'date' },
    ],
    colonnes: [
      { cle: 'timestamp', libelle: 'Horodatage', format: 'datetime' },
      { cle: 'acteur_label', libelle: 'Auteur' },
      { cle: 'acteur_role', libelle: 'Rôle' },
      { cle: 'action_label', libelle: 'Action' },
      { cle: 'cible_nom', libelle: 'Cible' },
      { cle: 'ip_address', libelle: 'IP' },
    ],
    note: 'Source : /api/audit-logs/?acteur_id=…',
  },

  audit_modifications: {
    id: 'audit_modifications',
    titre: 'Modifications',
    fil: 'Audit & Traçabilité',
    icone: 'bi-pencil-square',
    introduction: 'Créations, modifications et suppressions enregistrées dans '
      + 'le journal d\'audit. Choisir un type de modification pour filtrer.',
    endpoint: '/audit-logs/',
    filtres: [
      {
        param: 'action',
        libelle: 'Type de modification',
        type: 'select',
        tous: 'Toutes les modifications',
        options: ACTIONS_AUDIT_MODIFICATIONS,
      },
      ...FILTRES_AUDIT,
    ],
    colonnes: [
      { cle: 'timestamp', libelle: 'Horodatage', format: 'datetime' },
      { cle: 'action_label', libelle: 'Modification' },
      { cle: 'acteur_label', libelle: 'Auteur' },
      { cle: 'cible_type', libelle: 'Type de cible' },
      { cle: 'cible_nom', libelle: 'Cible' },
    ],
    note: 'Source : /api/audit-logs/?action=…',
  },

  audit_securite: {
    id: 'audit_securite',
    titre: 'Événements de sécurité',
    fil: 'Audit & Traçabilité',
    icone: 'bi-shield-exclamation',
    introduction: 'Connexions, forçages, déliaisons d\'appareils et sorties de '
      + 'périmètre géographique.',
    endpoint: '/audit-logs/',
    filtres: [
      {
        param: 'action',
        libelle: 'Événement',
        type: 'select',
        tous: 'Tous les événements de sécurité',
        options: ACTIONS_AUDIT_SECURITE,
      },
      ...FILTRES_AUDIT,
    ],
    colonnes: [
      { cle: 'timestamp', libelle: 'Horodatage', format: 'datetime' },
      { cle: 'action_label', libelle: 'Événement' },
      { cle: 'acteur_label', libelle: 'Auteur' },
      { cle: 'device_id', libelle: 'Appareil' },
      { cle: 'ip_address', libelle: 'IP' },
    ],
    note: 'Source : /api/audit-logs/?action=USER_LOGIN|FORCE_ENTREE|DEVICE_UNBIND…',
  },

  audit_integrite: {
    id: 'audit_integrite',
    type: 'indicateurs',
    titre: "Intégrité de la chaîne d'audit",
    fil: 'Audit & Traçabilité',
    icone: 'bi-shield-lock',
    introduction: 'Contrôle du chaînage SHA-256 du journal des habilitations : '
      + 'toute rupture, tout trou ou toute altération apparaît ici. Nécessite '
      + 'la console CURP (drapeau « flag.curp_ui_admin » ouvert).',
    endpoint: '/habilitations/journal/integrite/',
    note: 'Source : /api/habilitations/journal/integrite/ (verifier_chaine)',
  },

  audit_archives: {
    id: 'audit_archives',
    titre: "Archives d'audit",
    fil: 'Audit & Traçabilité',
    icone: 'bi-archive',
    introduction: 'Journal des habilitations (CURP) : gestes d\'attribution, '
      + 'révocations, dérogations, statuts de compte et accès refusés. '
      + 'Append-only et chaîné. Nécessite la console CURP ouverte.',
    endpoint: '/habilitations/journal/',
    recherche: { param: 'q', libelle: 'Rechercher', placeholder: 'Objet, auteur, motif…' },
    filtres: [
      { param: 'date_min', libelle: 'Depuis le', type: 'date' },
      { param: 'date_max', libelle: 'Jusqu\'au', type: 'date' },
      { param: 'compte', libelle: 'Compte (id)', type: 'nombre' },
    ],
    priorite: ['numero', 'horodatage', 'type_evenement', 'objet_libelle', 'acteur_label', 'motif'],
    taillePage: 50,
    note: 'Source : /api/habilitations/journal/',
  },
}

/** Récupère un descripteur par identifiant (ou `null`). */
export function ecranParId(id) {
  return ECRANS[id] || null
}

/** Liste des identifiants déclarés (contrôle de cohérence avec l'arborescence). */
export function idsEcrans() {
  return Object.keys(ECRANS)
}

export default ECRANS
