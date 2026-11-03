import React from 'react'
import ModuleHub from '../../components/hub/ModuleHub'

/**
 * Hub Stages premium — remplace les 5 écrans génériques du module, dont
 * plusieurs lisaient la même source (suivi = conventions) ou une source
 * voisine (affectations = tuteurs). Un onglet par sous-module, alimenté par
 * les vraies API de l'app `stages`.
 */

const STATUTS_CONVENTION = [
  { valeur: 'BROUILLON', libelle: 'Brouillon' },
  { valeur: 'SOUMISE', libelle: 'Soumise (à valider)' },
  { valeur: 'VALIDEE', libelle: 'Validée (admin)' },
  { valeur: 'REFUSEE', libelle: 'Refusée' },
  { valeur: 'SIGNEE', libelle: 'Signée' },
  { valeur: 'EN_COURS', libelle: 'En cours' },
  { valeur: 'TERMINEE', libelle: 'Terminée (rapport rendu)' },
  { valeur: 'SOUTENUE', libelle: 'Soutenue' },
  { valeur: 'VALIDEE_JURY', libelle: 'Validée par jury' },
  { valeur: 'ARCHIVEE', libelle: 'Archivée' },
]

const ONGLETS = [
  {
    id: 'conventions',
    libelle: 'Conventions',
    icone: 'bi-file-earmark-text',
    endpoint: '/stages/conventions/',
    rechercheLocale: ['etudiant_nom_complet', 'etudiant_matricule', 'organisme_nom', 'intitule'],
    recherchePlaceholder: 'Étudiant, matricule, organisme…',
    filtres: [{ param: 'statut', libelle: 'Statut', options: STATUTS_CONVENTION }],
    colonnes: [
      { cle: 'etudiant_nom_complet', libelle: 'Étudiant', format: 'lienEtudiant', sousCle: 'etudiant_matricule' },
      { cle: 'organisme_nom', libelle: 'Organisme d’accueil', gras: true },
      { cle: 'intitule', libelle: 'Intitulé du stage' },
      { cle: 'date_debut', libelle: 'Début', format: 'date' },
      { cle: 'date_fin', libelle: 'Fin', format: 'date' },
      { cle: 'statut', libelle: 'Statut', format: 'badge', libelleCle: 'statut_display' },
      { cle: 'ref_formation', libelle: 'Formation' },
    ],
    videTitre: 'Aucune convention de stage.',
    videTexte: 'Les conventions validées des étudiants en stage apparaîtront ici.',
  },
  {
    id: 'organismes',
    libelle: 'Organismes d’accueil',
    icone: 'bi-building',
    endpoint: '/stages/organismes/',
    rechercheLocale: ['nom', 'ville', 'raison_sociale'],
    recherchePlaceholder: 'Nom, ville, activité…',
    colonnes: [
      { cle: 'nom', libelle: 'Organisme', gras: true },
      { cle: 'raison_sociale', libelle: 'Activité' },
      { cle: 'ville', libelle: 'Ville' },
      { cle: 'contact_nom', libelle: 'Contact' },
      { cle: 'contact_email', libelle: 'Courriel' },
      { cle: 'contact_telephone', libelle: 'Téléphone' },
      { cle: 'actif', libelle: 'Actif', format: 'booleen' },
    ],
    videTitre: 'Aucun organisme partenaire.',
    videTexte: 'Les organismes accueillant des stagiaires apparaîtront ici.',
  },
  {
    id: 'tuteurs',
    libelle: 'Affectations & tuteurs',
    icone: 'bi-person-badge',
    endpoint: '/stages/tuteurs/',
    rechercheLocale: ['nom', 'prenom', 'organisme_nom'],
    recherchePlaceholder: 'Tuteur, organisme…',
    colonnes: [
      { cle: 'nom', libelle: 'Tuteur externe', gras: true, texte: (l) => `${l.nom} ${l.prenom || ''}`.trim() },
      { cle: 'organisme_nom', libelle: 'Organisme' },
      { cle: 'fonction', libelle: 'Fonction' },
      { cle: 'email', libelle: 'Courriel' },
      { cle: 'telephone', libelle: 'Téléphone' },
      { cle: 'actif', libelle: 'Actif', format: 'booleen' },
    ],
    note: 'Le tuteur externe encadre l’étudiant dans l’organisme ; l’encadrant interne INJS suit la convention côté institut.',
    videTitre: 'Aucun tuteur enregistré.',
  },
  {
    id: 'suivi',
    libelle: 'Suivi des stages',
    icone: 'bi-clipboard2-pulse',
    endpoint: '/stages/conventions/',
    rechercheLocale: ['etudiant_nom_complet', 'etudiant_matricule', 'organisme_nom'],
    filtres: [{
      param: 'statut', libelle: 'Statut', options: STATUTS_CONVENTION,
      valeurInitiale: 'EN_COURS', tousLibelle: 'Tous les statuts',
    }],
    colonnes: [
      { cle: 'etudiant_nom_complet', libelle: 'Étudiant', format: 'lienEtudiant', sousCle: 'etudiant_matricule' },
      { cle: 'organisme_nom', libelle: 'Organisme', gras: true },
      { cle: 'tuteur_externe', libelle: 'Tuteur externe' },
      { cle: 'date_debut', libelle: 'Début', format: 'date' },
      { cle: 'date_fin', libelle: 'Fin prévue', format: 'date' },
      { cle: 'lieu', libelle: 'Lieu' },
      { cle: 'statut', libelle: 'Statut', format: 'badge', libelleCle: 'statut_display' },
    ],
    note: 'Vue de suivi : par défaut les stages « En cours » ; changez le filtre pour les autres étapes du cycle (signature, soutenance, validation jury).',
    videTitre: 'Aucun stage à suivre.',
  },
  {
    id: 'evaluations',
    libelle: 'Évaluations',
    icone: 'bi-clipboard2-check',
    endpoint: '/stages/evaluations/',
    colonnes: [
      { cle: 'convention_id', libelle: 'Convention', format: 'nombre', texte: (l) => l.convention_id },
      { cle: 'note_aptitude', libelle: 'Aptitude /20', format: 'nombre' },
      { cle: 'note_integration', libelle: 'Intégration /20', format: 'nombre' },
      { cle: 'note_autonomie', libelle: 'Autonomie /20', format: 'nombre' },
      { cle: 'note_production', libelle: 'Production /20', format: 'nombre' },
      { cle: 'note_rapport', libelle: 'Rapport /20', format: 'nombre' },
      { cle: 'note_finale', libelle: 'Note finale', gras: true },
      { cle: 'mention', libelle: 'Mention', format: 'badge', libelleCle: 'mention_display' },
      { cle: 'date_evaluation', libelle: 'Évaluée le', format: 'datetime' },
    ],
    note: 'L’évaluation du tuteur externe (5 critères) est complétée par la validation INJS qui arrête la note finale et la mention.',
    videTitre: 'Aucune évaluation de stage.',
    videTexte: 'Les évaluations apparaissent à la fin des stages terminés.',
  },
]

const tuiles = (s) => [
  {
    valeur: Number(s.conventions || 0).toLocaleString('fr-FR'), libelle: 'Conventions',
    sub: `${Number(s.etudiants_en_stage || 0).toLocaleString('fr-FR')} étudiants concernés`,
    icone: 'bi-file-earmark-text', ton: 'blue',
  },
  {
    valeur: Number(s.en_cours || 0).toLocaleString('fr-FR'), libelle: 'Stages en cours',
    sub: 'Suivi actif des encadrants', icone: 'bi-hourglass-split', ton: 'green',
  },
  {
    valeur: Number(s.organismes || 0).toLocaleString('fr-FR'), libelle: 'Organismes partenaires',
    sub: `${Number(s.tuteurs || 0).toLocaleString('fr-FR')} tuteurs externes`,
    icone: 'bi-building', ton: 'amber',
  },
  {
    valeur: s.note_moyenne !== null && s.note_moyenne !== undefined
      ? `${Number(s.note_moyenne).toLocaleString('fr-FR')} /20` : '—',
    libelle: 'Note moyenne des stages',
    sub: `${Number(s.evaluations || 0).toLocaleString('fr-FR')} évaluations`,
    icone: 'bi-clipboard2-check', ton: 'slate',
  },
]

const pastilles = (s) => [
  { icone: 'bi-file-earmark-text', texte: `${Number(s.conventions || 0).toLocaleString('fr-FR')} conventions` },
  { icone: 'bi-hourglass-split', texte: `${Number(s.en_cours || 0).toLocaleString('fr-FR')} en cours` },
  { icone: 'bi-building', texte: `${Number(s.organismes || 0).toLocaleString('fr-FR')} organismes` },
]

export default function StagesHub({ ongletInitial = 'conventions' }) {
  return (
    <ModuleHub
      titre="Stages & conventions"
      badge="Stages — Vie professionnelle"
      icone="bi-briefcase"
      introduction="Conventions de stage des étudiants, organismes partenaires, tuteurs et évaluations — du dépôt de la convention à la validation par le jury."
      statsEndpoint="/stages/stats/"
      tuiles={tuiles}
      pastilles={pastilles}
      onglets={ONGLETS}
      ongletInitial={ongletInitial}
    />
  )
}
