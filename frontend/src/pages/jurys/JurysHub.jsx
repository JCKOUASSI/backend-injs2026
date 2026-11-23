/**
 * Hub Jurys premium : sessions, compositions, décisions et PV en
 * consultation. Le flux officiel (contrôle, calcul ECTS, délibération,
 * PV) reste dans l’écran « Jurys » de la scolarité.
 */
import ModuleHub from '@/components/hub/ModuleHub'
import '../../styles/jurys.css'

const TONS_STATUT = {
  PREPARATION: 'slate', CONTROLE: 'cyan', CALCUL: 'cyan',
  DELIBERATION: 'amber', DECISION: 'blue', PV_GENERE: 'indigo',
  VALIDE: 'green', VERROUILLE: 'violet', PUBLIE: 'green',
}

const OPTIONS_STATUT = [
  { valeur: 'PREPARATION', libelle: 'Préparation' },
  { valeur: 'CONTROLE', libelle: 'Contrôle' },
  { valeur: 'CALCUL', libelle: 'Calcul' },
  { valeur: 'DELIBERATION', libelle: 'Délibération' },
  { valeur: 'DECISION', libelle: 'Décision' },
  { valeur: 'PV_GENERE', libelle: 'PV généré' },
  { valeur: 'VALIDE', libelle: 'Validé' },
  { valeur: 'VERROUILLE', libelle: 'Verrouillé' },
  { valeur: 'PUBLIE', libelle: 'Publié' },
]

export default function JurysHub({ ongletInitial = 'sessions' }) {
  return (
    <ModuleHub
      titre="Jurys de délibération"
      badge="Jurys · Délibérations LMD"
      icone="bi-clipboard-check"
      introduction="Sessions de jury par formation et par niveau, compositions et décisions. Les données d’exemple ([Exemple]) sont des décisions manuelles de démonstration : les propositions officielles restent le produit du moteur de calcul ECTS à partir de notes réelles."
      statsEndpoint="/juries/hub/stats/"
      pastilles={(s) => [
        { icone: 'bi-clipboard-check', texte: `${s.sessions ?? 0} sessions · ${s.sessions_publiees ?? 0} publiée(s)` },
        { icone: 'bi-people', texte: `${s.membres ?? 0} membres de jury` },
        { icone: 'bi-graph-up-arrow', texte: s.taux_admis != null ? `Admission : ${String(s.taux_admis).replace('.', ',')} % des décisions` : 'Aucune décision pour le moment' },
        { icone: 'bi-info-circle', texte: 'Calcul, délibération et PV : écran Jurys de la scolarité.' },
      ]}
      tuiles={(s) => [
        { valeur: s.sessions, libelle: 'Sessions de jury', sub: `${s.sessions_publiees ?? 0} publiées`, icone: 'bi-clipboard-check', ton: 'blue' },
        { valeur: s.decisions, libelle: 'Décisions', sub: `${s.par_decision?.ADMIS ?? 0} admis · ${s.par_decision?.AJOURNE ?? 0} ajournés`, icone: 'bi-clipboard2-pulse', ton: 'indigo' },
        { valeur: s.membres, libelle: 'Membres de jury', sub: 'présidents, secrétaires, membres', icone: 'bi-people', ton: 'cyan' },
        { valeur: s.pv_generes, libelle: 'PV générés', sub: 'PDF horodatés et hachés', icone: 'bi-file-earmark-lock', ton: 'violet' },
      ]}
      onglets={[
        {
          id: 'sessions', libelle: 'Sessions', icone: 'bi-clipboard-check',
          endpoint: '/juries/hub/sessions/',
          rechercheLocale: ['libelle', 'formation', 'niveau'],
          recherchePlaceholder: 'Formation, niveau…',
          filtres: [
            { param: 'statut', libelle: 'Étape', options: OPTIONS_STATUT },
            { param: 'type_session', libelle: 'Type', options: [
              { valeur: 'NORMALE', libelle: 'Normale' },
              { valeur: 'RATTRAPAGE', libelle: 'Rattrapage' },
              { valeur: 'RECTIFICATION', libelle: 'Rectification' },
            ] },
          ],
          colonnes: [
            { cle: 'libelle', libelle: 'Session', gras: true },
            { cle: 'formation', libelle: 'Formation', format: 'muted' },
            { cle: 'niveau', libelle: 'Niveau', format: 'badge', tons: {} },
            { cle: 'semestre', libelle: 'Semestre', format: 'muted' },
            { cle: 'nb_membres', libelle: 'Membres', format: 'nombre' },
            { cle: 'nb_decisions', libelle: 'Décisions', format: 'nombre' },
            { cle: 'statut', libelle: 'Étape', format: 'badge', libelleCle: 'statut_display', tons: TONS_STATUT },
          ],
          videTitre: 'Aucune session de jury',
          videTexte: 'Les sessions créées depuis l’écran Jurys de la scolarité apparaîtront ici.',
        },
        {
          id: 'composition', libelle: 'Composition', icone: 'bi-people',
          endpoint: '/juries/hub/membres/',
          rechercheLocale: ['nom', 'session', 'formation'],
          recherchePlaceholder: 'Membre ou formation…',
          filtres: [{ param: 'fonction', libelle: 'Fonction', options: [
            { valeur: 'PRESIDENT', libelle: 'Présidents' },
            { valeur: 'SECRETAIRE', libelle: 'Secrétaires' },
            { valeur: 'MEMBRE', libelle: 'Membres' },
          ] }],
          colonnes: [
            { cle: 'nom', libelle: 'Membre', gras: true },
            { cle: 'fonction', libelle: 'Fonction', format: 'badge', libelleCle: 'fonction_display', tons: { PRESIDENT: 'indigo', SECRETAIRE: 'cyan', MEMBRE: 'slate' } },
            { cle: 'formation', libelle: 'Formation', format: 'muted' },
            { cle: 'niveau', libelle: 'Niveau', format: 'badge', tons: {} },
            { cle: 'session', libelle: 'Session', format: 'muted' },
          ],
          videTitre: 'Aucun membre de jury',
          videTexte: 'Les compositions des sessions apparaîtront ici.',
        },
        {
          id: 'decisions', libelle: 'Décisions & délibérations', icone: 'bi-clipboard2-pulse',
          endpoint: '/juries/hub/decisions/',
          rechercheLocale: ['nom', 'matricule', 'formation', 'mention'],
          recherchePlaceholder: 'Étudiant, matricule…',
          filtres: [{ param: 'decision', libelle: 'Décision', options: [
            { valeur: 'ADMIS', libelle: 'Admis' },
            { valeur: 'ADMIS_RESERVES', libelle: 'Admis avec réserves' },
            { valeur: 'AJOURNE', libelle: 'Ajournés' },
            { valeur: 'EXCLUSION', libelle: 'Exclus' },
          ] }],
          note: 'Décisions [Exemple] : moyennes de démonstration, sans notes réelles (voir justification de chaque ligne côté serveur).',
          colonnes: [
            { cle: 'matricule', libelle: 'Étudiant', format: 'lienEtudiant', idCle: 'etudiant_id', sousCle: 'nom' },
            { cle: 'formation', libelle: 'Formation', format: 'muted' },
            { cle: 'niveau', libelle: 'Niveau', format: 'badge', tons: {} },
            { cle: 'moyenne_generale', libelle: 'Moyenne /20', format: 'nombre' },
            { cle: 'credits_acquis', libelle: 'ECTS', format: 'nombre' },
            { cle: 'mention', libelle: 'Mention', format: 'muted' },
            { cle: 'decision', libelle: 'Décision', format: 'badge', libelleCle: 'decision_display', tons: { ADMIS: 'green', ADMIS_RESERVES: 'amber', AJOURNE: 'red', EXCLUSION: 'red' } },
          ],
          videTitre: 'Aucune décision de jury',
          videTexte: 'Les décisions officielles des délibérations apparaîtront ici.',
        },
        {
          id: 'pv', libelle: 'PV & publications', icone: 'bi-file-earmark-lock',
          endpoint: '/juries/hub/sessions/',
          paramsBase: { avec_pv: '1' },
          rechercheLocale: ['libelle', 'formation'],
          recherchePlaceholder: 'Formation…',
          note: 'Sessions disposant d’un procès-verbal généré (PDF haché SHA-256). Le téléchargement se fait depuis l’écran Jurys de la scolarité.',
          colonnes: [
            { cle: 'libelle', libelle: 'Session', gras: true },
            { cle: 'formation', libelle: 'Formation', format: 'muted' },
            { cle: 'niveau', libelle: 'Niveau', format: 'badge', tons: {} },
            { cle: 'nb_decisions', libelle: 'Décisions au PV', format: 'nombre' },
            { cle: 'statut', libelle: 'Étape', format: 'badge', libelleCle: 'statut_display', tons: TONS_STATUT },
          ],
          videTitre: 'Aucun PV généré',
          videTexte: 'Aucun procès-verbal n’a encore été généré : les PV naissent de l’étape « PV » du flux officiel de jury, à partir de délibérations réelles.',
        },
      ]}
      ongletInitial={ongletInitial}
      classePage="hub-jurys"
    />
  )
}
