/**
 * Hub Personnel premium (RH administrative et technique) : panorama,
 * agents, affectations, disponibilités, documents RH, fonctions et
 * services. Les enseignants restent au registre Formateurs.
 */
import ModuleHub from '@/components/hub/ModuleHub'
import '../../styles/personnel.css'

const parContrat = (s) =>
  `${s.par_contrat?.FONCTIONNAIRE ?? 0} fonctionnaires · ${s.par_contrat?.CONTRAT ?? 0} contractuels · ${s.par_contrat?.VACATAIRE ?? 0} vacataires`

export default function PersonnelHub({ ongletInitial = 'agents' }) {
  return (
    <ModuleHub
      titre="Personnel administratif & technique"
      badge="Personnel"
      icone="bi-person-badge"
      introduction="Agents, affectations et disponibilités du personnel administratif et technique. Les données fictives de démonstration sont étiquetées [Démo fictive] (matricules PERS-DEMO-…, aucun compte réel) ; les enseignants disposent de leur registre dédié (Formateurs, grades métier)."
      statsEndpoint="/rh/stats/"
      pastilles={(s) => [
        { icone: 'bi-people', texte: `${s.agents_actifs ?? 0} agents actifs sur ${s.agents ?? 0}` },
        { icone: 'bi-briefcase', texte: parContrat(s) },
        { icone: 'bi-diagram-3', texte: `${s.fonctions ?? 0} fonctions dans ${s.services ?? 0} services` },
        { icone: 'bi-info-circle', texte: 'Créations, affectations et dépôts restent dans les flux RH dédiés.' },
      ]}
      tuiles={(s) => [
        { valeur: s.agents, libelle: 'Agents', sub: `${s.agents_actifs ?? 0} actifs`, icone: 'bi-person-badge', ton: 'blue' },
        { valeur: s.fonctions, libelle: 'Fonctions', sub: `${s.services ?? 0} services`, icone: 'briefcase', ton: 'indigo' },
        { valeur: s.indisponibilites_en_cours, libelle: 'Absences en cours', sub: 'congés, missions, formations', icone: 'bi-calendar-x', ton: 'amber' },
        { valeur: s.documents, libelle: 'Documents RH', sub: 'métadonnées classées', icone: 'bi-folder2-open', ton: 'cyan' },
      ]}
      onglets={[
        {
          id: 'agents', libelle: 'Agents', icone: 'bi-person-badge',
          endpoint: '/rh/agents/',
          rechercheLocale: ['nom', 'prenom', 'matricule', 'email'],
          recherchePlaceholder: 'Nom, matricule…',
          filtres: [{ param: 'statut', libelle: 'Statut', options: [
            { valeur: 'ACTIF', libelle: 'Actifs' }, { valeur: 'INACTIF', libelle: 'Inactifs' },
          ] }],
          colonnes: [
            { cle: 'matricule', libelle: 'Matricule', format: 'mono' },
            { cle: 'nom', libelle: 'Agent', gras: true, sousCle: 'prenom' },
            { cle: 'type_contrat', libelle: 'Contrat', format: 'badge', libelleCle: 'type_contrat_display', tons: { FONCTIONNAIRE: 'blue', CONTRAT: 'cyan', VACATAIRE: 'amber', BENEVOLE: 'slate' } },
            { libelle: 'Fonction actuelle', texte: (l) => l.affectations?.find((a) => !a.date_fin)?.fonction || l.affectations?.[0]?.fonction || '—', format: 'muted' },
            { libelle: 'Service', texte: (l) => l.affectations?.find((a) => !a.date_fin)?.service || l.affectations?.[0]?.service || '—', format: 'muted' },
            { cle: 'date_entree', libelle: 'Prise de service', format: 'date' },
            { cle: 'statut', libelle: 'Statut', format: 'badge', libelleCle: 'statut_display', tons: { ACTIF: 'green', INACTIF: 'slate' } },
          ],
          videTitre: 'Aucun agent',
          videTexte: 'Les agents du personnel administratif et technique apparaîtront ici.',
        },
        {
          id: 'affectations', libelle: 'Affectations', icone: 'bi-diagram-3',
          endpoint: '/rh/affectations/',
          paramsBase: { actives: '1' },
          rechercheLocale: ['agent', 'agent_matricule', 'fonction', 'service'],
          recherchePlaceholder: 'Agent, fonction, service…',
          note: 'Affectations en cours (sans date de fin).',
          colonnes: [
            { cle: 'agent', libelle: 'Agent', gras: true, sousCle: 'agent_matricule' },
            { cle: 'fonction', libelle: 'Fonction' },
            { cle: 'service', libelle: 'Service', format: 'muted' },
            { cle: 'date_debut', libelle: 'Depuis le', format: 'date' },
          ],
          videTitre: 'Aucune affectation active',
          videTexte: 'Les affectations en cours des agents apparaîtront ici.',
        },
        {
          id: 'disponibilites', libelle: 'Disponibilités', icone: 'bi-calendar-x',
          endpoint: '/rh/disponibilites/',
          rechercheLocale: ['agent', 'agent_matricule', 'motif'],
          recherchePlaceholder: 'Agent ou motif…',
          filtres: [{ param: 'type_indispo', libelle: 'Type', tousLibelle: 'Tous types', options: [
            { valeur: 'CONGE', libelle: 'Congés' }, { valeur: 'MISSION', libelle: 'Missions' },
            { valeur: 'FORMATION', libelle: 'Formations' }, { valeur: 'MALADIE', libelle: 'Maladies' },
            { valeur: 'AUTRE', libelle: 'Autres' },
          ] }],
          colonnes: [
            { cle: 'agent', libelle: 'Agent', gras: true, sousCle: 'agent_matricule' },
            { cle: 'type_indispo', libelle: 'Type', format: 'badge', libelleCle: 'type_indispo_display', tons: { CONGE: 'cyan', MISSION: 'blue', FORMATION: 'indigo', MALADIE: 'amber', AUTRE: 'slate' } },
            { cle: 'motif', libelle: 'Motif', format: 'muted' },
            { cle: 'date_debut', libelle: 'Début', format: 'date' },
            { cle: 'date_fin', libelle: 'Fin', format: 'date' },
          ],
          videTitre: 'Aucune indisponibilité',
          videTexte: 'Congés, missions et formations déclarés apparaîtront ici.',
        },
        {
          id: 'documents', libelle: 'Documents RH', icone: 'bi-folder2-open',
          endpoint: '/rh/documents/',
          rechercheLocale: ['agent', 'intitule'],
          recherchePlaceholder: 'Agent ou document…',
          note: 'Références documentaires des dossiers d’agents ; les fichiers ne sont pas importés dans les données d’exemple.',
          colonnes: [
            { cle: 'intitule', libelle: 'Document', gras: true },
            { cle: 'type_document', libelle: 'Type', format: 'badge', libelleCle: 'type_document_display', tons: { CONTRAT: 'blue', AVIS: 'cyan', EVALUATION: 'indigo', ATTESTATION: 'green', AUTRE: 'slate' } },
            { cle: 'agent', libelle: 'Agent', format: 'muted' },
            { cle: 'created_at', libelle: 'Classé le', format: 'datetime' },
          ],
          videTitre: 'Aucun document RH',
          videTexte: 'Contrats, avis et attestations classés apparaîtront ici.',
        },
        {
          id: 'fonctions', libelle: 'Fonctions', icone: 'bi-briefcase',
          endpoint: '/rh/fonctions/',
          rechercheLocale: ['intitule', 'service_nom'],
          recherchePlaceholder: 'Intitulé de fonction…',
          colonnes: [
            { cle: 'intitule', libelle: 'Fonction', gras: true },
            { cle: 'service_nom', libelle: 'Service', format: 'muted' },
            { cle: 'actif', libelle: 'Active', format: 'booleen' },
          ],
          videTitre: 'Aucune fonction',
          videTexte: 'Les fonctions rattachées aux services apparaîtront ici.',
        },
        {
          id: 'services', libelle: 'Services', icone: 'bi-diagram-3',
          endpoint: '/rh/services/',
          rechercheLocale: ['nom'],
          recherchePlaceholder: 'Nom du service…',
          colonnes: [
            { cle: 'nom', libelle: 'Service', gras: true },
            { cle: 'description', libelle: 'Description', format: 'muted' },
            { cle: 'actif', libelle: 'Actif', format: 'booleen' },
          ],
          videTitre: 'Aucun service',
          videTexte: 'Les services actifs de l’organigramme apparaîtront ici.',
        },
      ]}
      ongletInitial={ongletInitial}
      classePage="hub-personnel"
    />
  )
}
