/**
 * Hub Évaluations premium (consultation) : sessions, évaluations,
 * avancement de la saisie des notes, contrôle et relevés. La saisie
 * officielle et la validation restent dans les flux dédiés (les notes
 * d’exemple demeurent en brouillon et n’alimentent aucun résultat).
 */
import ModuleHub from '@/components/hub/ModuleHub'
import '@/styles/evaluationsHub.css'

const TONS_SESSION = {
  BROUILLON: 'slate', PLANIFIEE: 'cyan', PUBLIEE: 'blue',
  OUVERTE: 'green', CLOTUREE: 'amber', CALCULS: 'indigo',
  RESULTATS_VALIDES: 'green', VERROUILLEE: 'violet',
}
const TONS_NOTE = {
  BROUILLON: 'slate', SOUMISE: 'amber',
  CORRECTION_DEMANDEE: 'red', VALIDEE: 'green',
}

const COLONNES_NOTES = [
  { cle: 'matricule', libelle: 'Étudiant', format: 'lienEtudiant', idCle: 'etudiant_id', sousCle: 'nom_complet' },
  { cle: 'evaluation', libelle: 'Évaluation', gras: true },
  { cle: 'ecue', libelle: 'ECUE', format: 'mono' },
  { cle: 'formation', libelle: 'Formation', format: 'muted' },
  { cle: 'niveau', libelle: 'Niveau', format: 'badge', tons: {} },
  { cle: 'valeur', libelle: 'Note /20', format: 'nombre' },
  { cle: 'statut', libelle: 'Statut', format: 'badge', libelleCle: 'statut_display', tons: TONS_NOTE },
  { cle: 'verrouillee', libelle: 'Verrouillée', format: 'booleen' },
]

export default function EvaluationsHub({ ongletInitial = 'sessions' }) {
  return (
    <ModuleHub
      titre="Évaluations académiques"
      badge="Évaluations"
      icone="bi-clipboard-check"
      introduction="Sessions d’examen, évaluations par ECUE et avancement de la saisie des notes. Les notes d’exemple restent en brouillon (brouillons de démonstration, jamais soumises ni verrouillées) : seuls des relevés calculés par le moteur officiel produisent des résultats."
      statsEndpoint="/evaluations-academiques/hub/stats/"
      pastilles={(s) => [
        { icone: 'bi-calendar-range', texte: `${s.sessions ?? 0} sessions · ${s.evaluations ?? 0} évaluations` },
        { icone: 'bi-people', texte: `${s.participants ?? 0} participations suivies` },
        { icone: 'bi-percent', texte: s.avancement_validation != null ? `${String(s.avancement_validation).replace('.', ',')} % des notes validées` : 'Aucune note saisie' },
        { icone: 'bi-info-circle', texte: 'Saisie et validation officielles : écran Évaluations (liste).' },
      ]}
      tuiles={(s) => [
        { valeur: s.sessions, libelle: 'Sessions', sub: `${s.sessions_par_statut?.OUVERTE ?? 0} ouvertes`, icone: 'bi-calendar-range', ton: 'blue' },
        { valeur: s.evaluations, libelle: 'Évaluations', sub: 'reliées aux ECUE et enseignants', icone: 'bi-clipboard-check', ton: 'indigo' },
        { valeur: s.notes, libelle: 'Notes saisies', sub: `${s.notes_par_statut?.VALIDEE ?? 0} validées · ${s.notes_par_statut?.BROUILLON ?? 0} brouillons`, icone: 'bi-pencil-square', ton: 'amber' },
        { valeur: s.releves, libelle: 'Relevés émis', sub: 'versionnés et hachés', icone: 'bi-file-earmark-lock', ton: 'violet' },
        { valeur: s.types_actifs, libelle: 'Types d’évaluation', sub: 'paramétrables', icone: 'bi-sliders', ton: 'cyan' },
      ]}
      onglets={[
        {
          id: 'sessions', libelle: 'Sessions', icone: 'bi-calendar-range',
          endpoint: '/evaluations-academiques/hub/sessions/',
          rechercheLocale: ['libelle', 'formation', 'niveau'],
          recherchePlaceholder: 'Formation ou session…',
          filtres: [{ param: 'statut', libelle: 'Statut', options: [
            { valeur: 'BROUILLON', libelle: 'Brouillon' }, { valeur: 'PLANIFIEE', libelle: 'Planifiée' },
            { valeur: 'PUBLIEE', libelle: 'Publiée' }, { valeur: 'OUVERTE', libelle: 'Ouverte' },
            { valeur: 'CLOTUREE', libelle: 'Clôturée' }, { valeur: 'VERROUILLEE', libelle: 'Verrouillée' },
          ] }],
          colonnes: [
            { cle: 'libelle', libelle: 'Session', gras: true },
            { cle: 'formation', libelle: 'Formation', format: 'muted' },
            { cle: 'niveau', libelle: 'Niveau', format: 'badge', tons: {} },
            { cle: 'date_debut', libelle: 'Début', format: 'date' },
            { cle: 'date_fin', libelle: 'Fin', format: 'date' },
            { cle: 'nb_evaluations', libelle: 'Évaluations', format: 'nombre' },
            { cle: 'statut', libelle: 'Statut', format: 'badge', libelleCle: 'statut_display', tons: TONS_SESSION },
          ],
          videTitre: 'Aucune session d’évaluation',
          videTexte: 'Les sessions créées depuis l’écran Évaluations apparaîtront ici.',
        },
        {
          id: 'evaluations', libelle: 'Évaluations', icone: 'bi-clipboard-check',
          endpoint: '/evaluations-academiques/hub/evaluations/',
          rechercheLocale: ['libelle', 'ecue', 'formation', 'enseignant'],
          recherchePlaceholder: 'ECUE, enseignant, formation…',
          filtres: [{ param: 'statut', libelle: 'Statut', options: [
            { valeur: 'BROUILLON', libelle: 'Brouillon' }, { valeur: 'PUBLIEE', libelle: 'Publiée' },
            { valeur: 'CLOTUREE', libelle: 'Clôturée' }, { valeur: 'ANNULEE', libelle: 'Annulée' },
          ] }],
          colonnes: [
            { cle: 'libelle', libelle: 'Évaluation', gras: true },
            { cle: 'ecue', libelle: 'ECUE', format: 'muted' },
            { cle: 'type', libelle: 'Type', format: 'muted' },
            { cle: 'enseignant', libelle: 'Enseignant', format: 'muted' },
            { cle: 'nb_participants', libelle: 'Participants', format: 'nombre' },
            { cle: 'date_prevue', libelle: 'Date prévue', format: 'date' },
            { cle: 'statut', libelle: 'Statut', format: 'badge', libelleCle: 'statut_display', tons: { BROUILLON: 'slate', PUBLIEE: 'blue', CLOTUREE: 'amber', ANNULEE: 'red' } },
          ],
          videTitre: 'Aucune évaluation',
          videTexte: 'Les évaluations planifiées par ECUE apparaîtront ici.',
        },
        {
          id: 'notes', libelle: 'Saisie des notes', icone: 'bi-pencil-square',
          endpoint: '/evaluations-academiques/hub/notes/',
          rechercheLocale: ['nom_complet', 'matricule', 'evaluation', 'ecue'],
          recherchePlaceholder: 'Étudiant, évaluation…',
          note: 'Vue de suivi de l’avancement ; les notes [Exemple] sont des brouillons fictifs. La saisie et la correction se font dans l’écran de saisie officiel (historisées).',
          colonnes: COLONNES_NOTES,
          videTitre: 'Aucune note saisie',
          videTexte: 'Les notes saisies par les enseignants apparaîtront ici.',
        },
        {
          id: 'controle', libelle: 'Contrôle & validation', icone: 'bi-patch-check',
          endpoint: '/evaluations-academiques/hub/notes/',
          paramsBase: { statut: 'SOUMISE' },
          rechercheLocale: ['nom_complet', 'matricule', 'evaluation', 'ecue'],
          recherchePlaceholder: 'Étudiant, évaluation…',
          note: 'Notes soumises par les enseignants en attente de validation pédagogique. Le contrôle et la validation se font dans l’écran Résultats / délibérations.',
          colonnes: COLONNES_NOTES,
          videTitre: 'Aucune note en attente de validation',
          videTexte: 'Les notes soumises à valider apparaîtront ici — les notes d’exemple restent volontairement en brouillon.',
        },
        {
          id: 'releves', libelle: 'Relevés de notes', icone: 'bi-file-earmark-lock',
          endpoint: '/evaluations-academiques/hub/releves/',
          rechercheLocale: ['nom_complet', 'matricule', 'formation'],
          recherchePlaceholder: 'Étudiant…',
          note: 'Relevés versionnés générés par le moteur de résultats (PDF haché SHA-256). Aucune génération n’est lancée par les données d’exemple.',
          colonnes: [
            { cle: 'matricule', libelle: 'Étudiant', format: 'lienEtudiant', idCle: 'etudiant_id', sousCle: 'nom_complet' },
            { cle: 'formation', libelle: 'Formation', format: 'muted' },
            { cle: 'niveau', libelle: 'Niveau', format: 'badge', tons: {} },
            { cle: 'version', libelle: 'Version', format: 'nombre' },
            { cle: 'sha256', libelle: 'Empreinte', format: 'mono' },
            { cle: 'verrouillee', libelle: 'Verrouillé', format: 'booleen' },
            { cle: 'genere_le', libelle: 'Généré le', format: 'datetime' },
          ],
          videTitre: 'Aucun relevé émis',
          videTexte: 'Les relevés naissent du calcul officiel des résultats à partir de notes validées et verrouillées.',
        },
        {
          id: 'types', libelle: 'Types d’évaluation', icone: 'bi-sliders',
          endpoint: '/evaluations-academiques/types-evaluation/',
          rechercheLocale: ['libelle', 'code', 'categorie'],
          recherchePlaceholder: 'Type ou catégorie…',
          note: 'Référentiel paramétrable (aucun type officiel n’est imposé par le code) : les types [Exemple] portent des codes EX-*.',
          colonnes: [
            { cle: 'code', libelle: 'Code', format: 'mono' },
            { cle: 'libelle', libelle: 'Type', gras: true },
            { cle: 'categorie', libelle: 'Catégorie', format: 'badge', tons: { CONTINU: 'cyan', TERMINAL: 'indigo', PRATIQUE: 'amber' } },
            { cle: 'actif', libelle: 'Actif', format: 'booleen' },
          ],
          videTitre: 'Aucun type d’évaluation',
          videTexte: 'Les types paramétrés par la pédagogie apparaîtront ici.',
        },
      ]}
      classePage="evalx-page"
      ongletInitial={ongletInitial}
    />
  )
}
