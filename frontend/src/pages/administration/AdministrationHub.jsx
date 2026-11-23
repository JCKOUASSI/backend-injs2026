/**
 * Hub Administration générale premium : panorama + un onglet par
 * sous-module (courrier, documents officiels, réunions, missions et
 * organigramme directions → départements → services). Consultation ;
 * les transitions métier restent dans les flux dédiés.
 */
import ModuleHub from '@/components/hub/ModuleHub'
import '../../styles/administration.css'

const TONS_DOC = { BROUILLON: 'slate', EN_VALIDATION: 'amber', SIGNE: 'green', PUBLIE: 'green', ARCHIVE: 'slate' }

export default function AdministrationHub({ ongletInitial = 'courrier' }) {
  return (
    <ModuleHub
      titre="Administration générale"
      badge="Administration"
      icone="bi-building"
      introduction="Courrier, documents officiels, réunions, missions et organigramme de l’établissement : une vision d’ensemble de l’activité administrative. Données fictives de démonstration étiquetées [Démo fictive] : organigramme INJS du processus LMD avec responsables désignés (comptes fictifs), budgets de mission à 0 — aucun montant inventé."
      statsEndpoint="/administrations/stats/"
      pastilles={(s) => [
        { icone: 'bi-building', texte: `${s.directions ?? 0} directions · ${s.departements ?? 0} départements · ${s.services ?? 0} services` },
        { icone: 'bi-envelope', texte: `${s.courriers ?? 0} courriers (${s.courriers_par_sens?.ENTRANT ?? 0} entrants · ${s.courriers_par_sens?.SORTANT ?? 0} sortants)` },
        { icone: 'bi-calendar-check', texte: `${s.reunions_a_venir ?? 0} réunion(s) à venir` },
        { icone: 'info', texte: 'Les transitions (réponse au courrier, PV, validation) restent dans les écrans métier dédiés.' },
      ]}
      tuiles={(s) => [
        { valeur: s.courriers, libelle: 'Courriers', sub: `${s.courriers_en_traitement ?? 0} en traitement`, icone: 'bi-envelope', ton: 'blue' },
        { valeur: s.documents, libelle: 'Documents officiels', sub: `${s.documents_publies ?? 0} publiés`, icone: 'bi-file-earmark-text', ton: 'indigo' },
        { valeur: s.reunions, libelle: 'Réunions & commissions', sub: `${s.reunions_a_venir ?? 0} à venir`, icone: 'bi-people', ton: 'cyan' },
        { valeur: s.missions, libelle: 'Missions', sub: `${s.missions_en_cours ?? 0} en cours`, icone: 'bi-geo-alt', ton: 'amber' },
        { valeur: s.services, libelle: 'Services actifs', sub: `${s.directions ?? 0} directions`, icone: 'bi-diagram-3', ton: 'violet' },
      ]}
      onglets={[
        {
          id: 'courrier', libelle: 'Courrier', icone: 'bi-envelope',
          endpoint: '/administrations/courriers/',
          rechercheLocale: ['reference', 'objet', 'expediteur', 'destinataire'],
          recherchePlaceholder: 'Référence, objet, expéditeur…',
          filtres: [
            { param: 'sens', libelle: 'Sens', tousLibelle: 'Entrants et sortants', options: [
              { valeur: 'ENTRANT', libelle: 'Entrants' },
              { valeur: 'SORTANT', libelle: 'Sortants' },
            ] },
            { param: 'statut', libelle: 'Statut', options: [
              { valeur: 'RECU', libelle: 'Reçu' }, { valeur: 'EN_COURS', libelle: 'En cours de traitement' },
              { valeur: 'REPONDU', libelle: 'Répondu' }, { valeur: 'CLASSE', libelle: 'Classé' },
              { valeur: 'ARCHIVE', libelle: 'Archivé' },
            ] },
          ],
          colonnes: [
            { cle: 'reference', libelle: 'Référence', format: 'mono' },
            { cle: 'objet', libelle: 'Objet', gras: true },
            { cle: 'sens', libelle: 'Sens', format: 'badge', libelleCle: 'sens_display', tons: { ENTRANT: 'cyan', SORTANT: 'violet' } },
            { cle: 'expediteur', libelle: 'Expéditeur', format: 'muted' },
            { cle: 'destinataire', libelle: 'Destinataire', format: 'muted' },
            { cle: 'date_courrier', libelle: 'Date', format: 'date' },
            { cle: 'statut', libelle: 'Statut', format: 'badge', libelleCle: 'statut_display' },
          ],
          videTitre: 'Aucun courrier',
          videTexte: 'Les courriers entrants et sortants enregistrés par le service courrier apparaîtront ici.',
        },
        {
          id: 'documents', libelle: 'Documents officiels', icone: 'bi-file-earmark-text',
          endpoint: '/administrations/documents/',
          rechercheLocale: ['titre', 'reference'],
          recherchePlaceholder: 'Titre du document…',
          filtres: [{ param: 'statut', libelle: 'Statut', options: [
            { valeur: 'BROUILLON', libelle: 'Brouillon' }, { valeur: 'EN_VALIDATION', libelle: 'En validation' },
            { valeur: 'SIGNE', libelle: 'Signé' }, { valeur: 'PUBLIE', libelle: 'Publié' },
            { valeur: 'ARCHIVE', libelle: 'Archivé' },
          ] }],
          colonnes: [
            { cle: 'titre', libelle: 'Document', gras: true },
            { cle: 'type_document', libelle: 'Type', format: 'badge', libelleCle: 'type_document_display', tons: { NOTE_SERVICE: 'blue', ARRETE: 'indigo', DECISION: 'cyan', CIRCULAIRE: 'amber', AUTRE: 'slate' } },
            { cle: 'reference', libelle: 'Référence', format: 'mono' },
            { cle: 'signe_par', libelle: 'Signé par', format: 'muted' },
            { cle: 'statut', libelle: 'Statut', format: 'badge', libelleCle: 'statut_display', tons: TONS_DOC },
          ],
          videTitre: 'Aucun document officiel',
          videTexte: 'Notes de service, décisions, circulaires et arrêtés apparaîtront ici.',
        },
        {
          id: 'reunions', libelle: 'Réunions & commissions', icone: 'bi-people',
          endpoint: '/administrations/reunions/',
          rechercheLocale: ['titre', 'type_reunion', 'lieu'],
          recherchePlaceholder: 'Intitulé, type de réunion…',
          colonnes: [
            { cle: 'titre', libelle: 'Réunion', gras: true },
            { cle: 'type_reunion', libelle: 'Type', format: 'muted' },
            { cle: 'date_reunion', libelle: 'Date', format: 'date' },
            { cle: 'lieu', libelle: 'Lieu', format: 'muted' },
            { cle: 'statut', libelle: 'Statut', format: 'badge', libelleCle: 'statut_display', tons: { PLANIFIEE: 'blue', TENUE: 'cyan', PV_EMIS: 'green', ANNULEE: 'red' } },
          ],
          videTitre: 'Aucune réunion',
          videTexte: 'Conseils, commissions et comités planifiés apparaîtront ici.',
        },
        {
          id: 'missions', libelle: 'Missions', icone: 'bi-geo-alt',
          endpoint: '/administrations/missions/',
          rechercheLocale: ['objet', 'lieu'],
          recherchePlaceholder: 'Objet ou lieu de mission…',
          note: 'Budgets non renseignés (0) : aucun montant de mission n’est inventé dans les données de démonstration.',
          colonnes: [
            { cle: 'objet', libelle: 'Mission', gras: true },
            { cle: 'lieu', libelle: 'Lieu', format: 'muted' },
            { cle: 'date_debut', libelle: 'Début', format: 'date' },
            { cle: 'date_fin', libelle: 'Fin', format: 'date' },
            { cle: 'statut', libelle: 'Statut', format: 'badge', libelleCle: 'statut_display' },
          ],
          videTitre: 'Aucune mission',
          videTexte: 'Les ordres de mission proposés et validés apparaîtront ici.',
        },
        {
          id: 'directions', libelle: 'Directions', icone: 'bi-building',
          endpoint: '/administrations/organigramme/directions/',
          rechercheParam: 'q', recherchePlaceholder: 'Libellé ou code…',
          note: 'Organigramme générique de démonstration ; les responsables ne sont pas désignés dans les données d’exemple.',
          colonnes: [
            { cle: 'code', libelle: 'Code', format: 'mono' },
            { cle: 'libelle', libelle: 'Direction', gras: true },
            { libelle: 'Responsable', texte: (l) => l.responsable?.nom || '—', format: 'muted' },
            { cle: 'nb_departements', libelle: 'Départements', format: 'nombre' },
            { cle: 'effectif', libelle: 'Comptes rattachés', format: 'nombre' },
            { cle: 'actif', libelle: 'Active', format: 'booleen' },
          ],
          videTitre: 'Aucune direction',
          videTexte: 'Les directions de l’organigramme apparaîtront ici.',
        },
        {
          id: 'departements', libelle: 'Départements', icone: 'bi-layers',
          endpoint: '/administrations/organigramme/departements/',
          rechercheParam: 'q', recherchePlaceholder: 'Libellé ou code…',
          colonnes: [
            { cle: 'code', libelle: 'Code', format: 'mono' },
            { cle: 'libelle', libelle: 'Département', gras: true },
            { cle: 'direction_libelle', libelle: 'Direction', format: 'muted' },
            { libelle: 'Responsable', texte: (l) => l.responsable?.nom || '—', format: 'muted' },
            { cle: 'nb_services', libelle: 'Services', format: 'nombre' },
            { cle: 'actif', libelle: 'Actif', format: 'booleen' },
          ],
          videTitre: 'Aucun département',
          videTexte: 'Les départements rattachés aux directions apparaîtront ici.',
        },
        {
          id: 'services', libelle: 'Services', icone: 'bi-diagram-3',
          endpoint: '/administrations/organigramme/services/',
          rechercheParam: 'q', recherchePlaceholder: 'Nom ou code du service…',
          colonnes: [
            { cle: 'code', libelle: 'Code', format: 'mono' },
            { cle: 'libelle', libelle: 'Service', gras: true },
            { cle: 'type_unite', libelle: 'Type', format: 'badge', tons: { SERVICE: 'blue', BUREAU: 'cyan', UNITE: 'indigo', CELLULE: 'amber', AUTRE: 'slate' } },
            { cle: 'departement_libelle', libelle: 'Département', format: 'muted' },
            { libelle: 'Responsable', texte: (l) => l.responsable?.nom || '—', format: 'muted' },
            { cle: 'effectif', libelle: 'Comptes rattachés', format: 'nombre' },
            { cle: 'actif', libelle: 'Actif', format: 'booleen' },
          ],
          videTitre: 'Aucun service',
          videTexte: 'Les services et bureaux des départements apparaîtront ici.',
        },
      ]}
      ongletInitial={ongletInitial}
      classePage="hub-administration"
    />
  )
}
