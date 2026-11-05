/**
 * Hub Finances étudiantes premium (consultation) : barème, échéanciers,
 * factures, paiements, quittances, remboursements et situation. Les
 * données d’exemple sont inopérantes : barème inactif, factures en
 * brouillon, paiements jamais confirmés — aucun encaissement réel.
 */
import ModuleHub from '@/components/hub/ModuleHub'
import '@/styles/financesHub.css'
const fcfa = (n) => `${Number(n || 0).toLocaleString('fr-FR')} FCFA`

const TONS_GLOBAL = {
  IMPAYE: 'red', PARTIELLEMENT_PAYE: 'amber', COMPLETE: 'green',
}

const COLONNES_SITUATION = [
  { cle: 'matricule', libelle: 'Étudiant', format: 'lienEtudiant', idCle: 'etudiant_id', sousCle: 'nom_complet' },
  { cle: 'nb_lignes', libelle: 'Échéances', format: 'nombre' },
  { cle: 'total', libelle: 'Dû total', format: 'montant' },
  { cle: 'paye', libelle: 'Réglé (lignes)', format: 'montant' },
  { cle: 'reste', libelle: 'Reste à payer', format: 'montant' },
  { cle: 'statut_global', libelle: 'Situation', format: 'badge',
    libelleTexte: { IMPAYE: 'Impayé', PARTIELLEMENT_PAYE: 'Partiellement payé', COMPLETE: 'Complété' },
    tons: TONS_GLOBAL },
]

export default function FinancesHub({ ongletInitial = 'bareme' }) {
  return (
    <ModuleHub
      titre="Finances étudiantes"
      badge="Finances étudiantes"
      icone="bi-wallet2"
      introduction="Frais, échéanciers et encaissements des étudiants. Les données d’exemple sont volontairement inopérantes : barème indicatif INACTIF (inutilisable par la facturation), factures en brouillon et paiements jamais confirmés — aucun montant officiel n’est présenté comme arrêté."
      statsEndpoint="/finances-etudiantes/hub/stats/"
      pastilles={(s) => [
        { icone: 'bi-wallet2', texte: `Dû total suivi : ${fcfa(s.montant_attendu)} · reste ${fcfa(s.montant_reste)}` },
        { icone: 'bi-shield-check', texte: `Encaissé et confirmé : ${fcfa(s.montant_encaisse_confirme)}` },
        { icone: 'bi-exclamation-triangle', texte: s.tarifications_actives === 0
          ? 'Aucun barème officiel actif : la tarification officielle reste à arrêter.'
          : `${s.tarifications_actives} lignes de barème officiel actif` },
        { icone: 'bi-info-circle', texte: 'Confirmations, quittances et rapprochements : écrans financiers dédiés.' },
      ]}
      tuiles={(s) => [
        { valeur: s.echeanciers, libelle: 'Échéanciers', sub: 'étudiants suivis', icone: 'bi-calendar-range', ton: 'blue' },
        { valeur: s.factures, libelle: 'Factures', sub: `${s.factures_par_statut?.BROUILLON ?? 0} brouillons · ${s.factures_par_statut?.EMISE ?? 0} émises`, icone: 'bi-receipt', ton: 'indigo' },
        { valeur: s.paiements, libelle: 'Paiements', sub: `${s.paiements_par_statut?.CONFIRME ?? 0} confirmés`, icone: 'bi-bank', ton: 'green' },
        { valeur: s.quittances, libelle: 'Quittances', sub: 'reçus officiels', icone: 'bi-patch-check', ton: 'cyan' },
        { valeur: s.relances, libelle: 'Relances', sub: `${s.remboursements ?? 0} remboursements en cours`, icone: 'bi-bell', ton: 'amber' },
      ]}
      onglets={[
        {
          id: 'bareme', libelle: 'Frais & barème', icone: 'bi-list-ol',
          endpoint: '/finances-etudiantes/hub/tarifications/',
          rechercheLocale: ['formation', 'nature_display'],
          recherchePlaceholder: 'Formation ou nature de frais…',
          note: 'Barème indicatif de démonstration laissé INACTIF : il ne peut alimenter ni les échéanciers officiels ni les factures. La tarification officielle sera arrêtée par la Direction (activation explicite requise).',
          colonnes: [
            { cle: 'formation', libelle: 'Formation', gras: true },
            { cle: 'nature', libelle: 'Nature de frais', format: 'badge', libelleCle: 'nature_display', tons: { DOSSIER: 'cyan', INSCRIPTION: 'blue', SCOLARITE: 'indigo', EXAMEN: 'amber', DOCUMENT: 'slate' } },
            { cle: 'niveau', libelle: 'Niveau', format: 'muted' },
            { cle: 'montant_base', libelle: 'Montant indicatif', format: 'montant' },
            { cle: 'actif', libelle: 'Barème actif', format: 'booleen' },
          ],
          videTitre: 'Aucune ligne de barème',
          videTexte: 'Le barème de tarification apparaîtra ici.',
        },
        {
          id: 'echeanciers', libelle: 'Échéanciers', icone: 'bi-calendar-range',
          endpoint: '/finances-etudiantes/hub/echeanciers/',
          rechercheLocale: ['nom_complet', 'matricule'],
          recherchePlaceholder: 'Étudiant…',
          filtres: [{ param: 'statut', libelle: 'Situation', options: [
            { valeur: 'IMPAYE', libelle: 'Impayés' },
            { valeur: 'PARTIELLEMENT_PAYE', libelle: 'Partiellement payés' },
            { valeur: 'COMPLETE', libelle: 'Complétés' },
          ] }],
          note: 'Échéanciers d’exemple construits sur le barème indicatif inactif ; aucune ligne n’est marquée « payée ».',
          colonnes: COLONNES_SITUATION,
          videTitre: 'Aucun échéancier',
          videTexte: 'Les échéanciers générés depuis le barème officiel apparaîtront ici.',
        },
        {
          id: 'factures', libelle: 'Factures', icone: 'bi-receipt',
          endpoint: '/finances-etudiantes/hub/factures/',
          rechercheLocale: ['numero', 'nom_complet', 'matricule'],
          recherchePlaceholder: 'Numéro ou étudiant…',
          filtres: [{ param: 'statut', libelle: 'Statut', options: [
            { valeur: 'BROUILLON', libelle: 'Brouillons' },
            { valeur: 'EMISE', libelle: 'Émises' },
            { valeur: 'PAYEE', libelle: 'Payées' },
            { valeur: 'ANNULEE', libelle: 'Annulées' },
          ] }],
          colonnes: [
            { cle: 'numero', libelle: 'Facture', format: 'mono' },
            { cle: 'matricule', libelle: 'Étudiant', format: 'lienEtudiant', idCle: 'etudiant_id', sousCle: 'nom_complet' },
            { cle: 'total', libelle: 'Total', format: 'montant' },
            { cle: 'date_emission', libelle: 'Émission', format: 'date' },
            { cle: 'statut', libelle: 'Statut', format: 'badge', libelleCle: 'statut_display', tons: { BROUILLON: 'slate', EMISE: 'blue', PAYEE: 'green', ANNULEE: 'red' } },
          ],
          videTitre: 'Aucune facture',
          videTexte: 'Les factures émises depuis les échéanciers apparaîtront ici.',
        },
        {
          id: 'paiements', libelle: 'Paiements', icone: 'bi-bank',
          endpoint: '/finances-etudiantes/hub/paiements/',
          rechercheLocale: ['nom_complet', 'matricule', 'transaction_externe'],
          recherchePlaceholder: 'Étudiant ou transaction…',
          filtres: [
            { param: 'statut', libelle: 'Statut', options: [
              { valeur: 'INITIE', libelle: 'Initialisés' },
              { valeur: 'EN_ATTENTE', libelle: 'En attente' },
              { valeur: 'CONFIRME', libelle: 'Confirmés' },
              { valeur: 'ECHOUE', libelle: 'Échoués' },
              { valeur: 'ANNULE', libelle: 'Annulés' },
            ] },
            { param: 'mode', libelle: 'Moyen', tousLibelle: 'Tous moyens', options: [
              { valeur: 'CAISSE', libelle: 'Caisse' },
              { valeur: 'VIREMENT', libelle: 'Virement' },
              { valeur: 'ELEPHANT_MONEY', libelle: 'Orange Money' },
              { valeur: 'MTN_MONEY', libelle: 'MTN Mobile Money' },
              { valeur: 'MOOV_MONEY', libelle: 'Moov Money' },
              { valeur: 'CARTE_BANCAIRE', libelle: 'Carte bancaire' },
            ] },
          ],
          note: 'Aucun paiement d’exemple n’est confirmé : une confirmation exige une pièce justificative vérifiée par la finance.',
          colonnes: [
            { cle: 'matricule', libelle: 'Étudiant', format: 'lienEtudiant', idCle: 'etudiant_id', sousCle: 'nom_complet' },
            { cle: 'nature', libelle: 'Frais', format: 'badge', libelleCle: 'nature_display', tons: { SCOLARITE: 'indigo', INSCRIPTION: 'blue', DOSSIER: 'cyan', EXAMEN: 'amber', DOCUMENT: 'slate' } },
            { cle: 'montant', libelle: 'Montant', format: 'montant' },
            { cle: 'mode', libelle: 'Moyen', format: 'badge', libelleCle: 'mode_display', tons: {} },
            { cle: 'date', libelle: 'Date', format: 'datetime' },
            { cle: 'statut', libelle: 'Statut', format: 'badge', libelleCle: 'statut_display', tons: { INITIE: 'slate', EN_ATTENTE: 'amber', CONFIRME: 'green', ECHOUE: 'red', ANNULE: 'red', RAPPROCHE: 'cyan' } },
          ],
          videTitre: 'Aucun paiement',
          videTexte: 'Les paiements enregistrés (caisse, mobile money, virement) apparaîtront ici.',
        },
        {
          id: 'recus', libelle: 'Reçus & quittances', icone: 'bi-patch-check',
          endpoint: '/finances-etudiantes/hub/quittances/',
          rechercheLocale: ['matricule'],
          recherchePlaceholder: 'Matricule…',
          note: 'Une quittance naît uniquement d’un paiement confirmé avec preuve : aucun reçu n’est fabriqué par les données d’exemple.',
          colonnes: [
            { cle: 'numero', libelle: 'Quittance', format: 'mono' },
            { cle: 'matricule', libelle: 'Étudiant', format: 'lienEtudiant', idCle: 'etudiant_id' },
            { cle: 'nature_display', libelle: 'Frais', format: 'muted' },
            { cle: 'montant', libelle: 'Montant', format: 'montant' },
            { cle: 'date_echeance', libelle: 'Échéance', format: 'date' },
          ],
          videTitre: 'Aucune quittance émise',
          videTexte: 'Les quittances des paiements confirmés apparaîtront ici — les données d’exemple n’en produisent volontairement aucune.',
        },
        {
          id: 'bourses', libelle: 'Bourses & remboursements', icone: 'bi-arrow-counterclockwise',
          endpoint: '/finances-etudiantes/hub/remboursements/',
          rechercheLocale: ['matricule', 'motif'],
          recherchePlaceholder: 'Matricule ou motif…',
          note: 'Les remboursements d’exemple sont seulement initialisés (motif étiqueté) : aucun remboursement n’est exécuté. Le volet bourses relève des flux de la Direction.',
          colonnes: [
            { cle: 'matricule', libelle: 'Étudiant', format: 'lienEtudiant', idCle: 'etudiant_id' },
            { cle: 'motif', libelle: 'Motif', format: 'muted' },
            { cle: 'montant', libelle: 'Montant', format: 'montant' },
            { cle: 'date', libelle: 'Date', format: 'datetime' },
            { cle: 'statut', libelle: 'Statut', format: 'badge', libelleCle: 'statut_display', tons: { INITIE: 'slate', CONFIRME: 'green', ANNULE: 'red' } },
          ],
          videTitre: 'Aucun remboursement',
          videTexte: 'Les demandes de remboursement instruites par la finance apparaîtront ici.',
        },
        {
          id: 'situation', libelle: 'Situation financière', icone: 'bi-pie-chart',
          endpoint: '/finances-etudiantes/hub/echeanciers/',
          rechercheLocale: ['nom_complet', 'matricule'],
          recherchePlaceholder: 'Étudiant…',
          note: 'Solde par étudiant calculé en direct depuis les lignes d’échéancier (dû, réglé, reste). Base indicative tant que le barème officiel n’est pas arrêté.',
          colonnes: COLONNES_SITUATION,
          videTitre: 'Aucune situation à afficher',
          videTexte: 'Les situations financières des étudiants suivis apparaîtront ici.',
        },
        {
          id: 'relances', libelle: 'Relances & rapprochements', icone: 'bi-bell',
          endpoint: '/finances-etudiantes/hub/relances/',
          rechercheLocale: ['nom_complet', 'matricule', 'detail'],
          recherchePlaceholder: 'Étudiant ou détail…',
          note: 'Relances émises et rapprochements comptables de la période (le rapprochement d’exemple est à solde nul, sans transaction réelle).',
          colonnes: [
            { cle: 'type_display', libelle: 'Événement', gras: true },
            { cle: 'matricule', libelle: 'Étudiant', format: 'lienEtudiant', idCle: 'etudiant_id', sousCle: 'nom_complet' },
            { cle: 'detail', libelle: 'Détail', format: 'muted' },
            { cle: 'date', libelle: 'Date', format: 'datetime' },
          ],
          videTitre: 'Aucune relance ni rapprochement',
          videTexte: 'Relances et rapprochements bancaires apparaîtront ici.',
        },
      ]}
      classePage="finx-page"
      ongletInitial={ongletInitial}
    />
  )
}
