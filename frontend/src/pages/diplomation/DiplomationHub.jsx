/**
 * Hub Diplômation premium : éligibilité factuelle des étudiants en fin
 * de cycle, diplômes préparés, gabarits et registres. Les diplômes
 * d’exemple ne sont jamais validés (ils ne peuvent pas passer le
 * portail public de vérification) ; l’émission officielle reste dans
 * l’écran Diplômes de la scolarité.
 */
import ModuleHub from '@/components/hub/ModuleHub'

const TONS_STATUT = {
  BROUILLON: 'slate', VALIDATION_PENDING: 'amber',
  VALIDATED: 'green', REVOKED: 'red',
}

const COLONNES_DIPLOMES = [
  { cle: 'matricule', libelle: 'Diplômé(e)', format: 'lienEtudiant', idCle: 'etudiant_id', sousCle: 'nom_complet' },
  { cle: 'ref_formation', libelle: 'Formation', format: 'muted' },
  { cle: 'niveau', libelle: 'Niveau', format: 'badge', tons: {} },
  { cle: 'mention', libelle: 'Mention', format: 'muted' },
  { cle: 'credits_acquis', libelle: 'ECTS', format: 'nombre' },
  { cle: 'numero_unique', libelle: 'N° unique', format: 'mono' },
  { cle: 'statut', libelle: 'Statut', format: 'badge', libelleCle: 'statut_display', tons: TONS_STATUT },
]

export default function DiplomationHub({ ongletInitial = 'eligibilite' }) {
  return (
    <ModuleHub
      titre="Diplômation & documents officiels"
      badge="Diplômation"
      icone="graduationCap"
      introduction="Fin de cycle, diplômes et registre annuel. Les diplômes d’exemple restent en brouillon ou en attente de validation — aucun n’est validé, afin qu’aucun document de démonstration ne puisse être présenté comme authentique sur le portail public de vérification."
      statsEndpoint="/graduation/stats/"
      pastilles={(s) => [
        { icone: 'graduationCap', texte: `${s.etudiants_fin_cycle ?? 0} étudiants en fin de cycle (L3/M2)` },
        { icone: 'shieldCheck', texte: `${s.par_statut?.VALIDATED ?? 0} diplôme(s) validé(s) — vérifiables par QR code` },
        { icone: 'bookOpen', texte: `${s.registres ?? 0} registre(s) annuel(s)` },
        { icone: 'info', texte: 'Validation, révocation et PDF signés : écran Diplômes de la scolarité.' },
      ]}
      tuiles={(s) => [
        { valeur: s.diplomes, libelle: 'Diplômes suivis', sub: `${s.par_statut?.VALIDATED ?? 0} validés · ${s.par_statut?.REVOKED ?? 0} révoqués`, icone: 'award', ton: 'blue' },
        { valeur: s.par_statut?.VALIDATION_PENDING, libelle: 'En attente de validation', sub: 'décision de la Direction requise', icone: 'hourglass', ton: 'amber' },
        { valeur: s.reeditions, libelle: 'Rééditions', sub: 'duplicatas tracés', icone: 'copy', ton: 'cyan' },
        { valeur: s.modeles, libelle: 'Gabarits actifs', sub: 'diplôme, attestation, relevé', icone: 'layoutTemplate', ton: 'violet' },
      ]}
      onglets={[
        {
          id: 'eligibilite', libelle: 'Éligibilité', icone: 'listChecks',
          endpoint: '/graduation/eligibles/',
          rechercheLocale: ['nom_complet', 'matricule', 'formation'],
          recherchePlaceholder: 'Étudiant, matricule, formation…',
          note: 'État factuel des étudiants en fin de cycle : inscription validée, présence d’une décision de jury rattachée, diplôme préparé. Ce tableau ne prononce aucune éligibilité officielle (le contrôle complet a lieu à la validation du diplôme).',
          colonnes: [
            { cle: 'matricule', libelle: 'Étudiant', format: 'lienEtudiant', idCle: 'etudiant_id', sousCle: 'nom_complet' },
            { cle: 'formation', libelle: 'Formation', format: 'muted' },
            { cle: 'niveau', libelle: 'Niveau', format: 'badge', tons: {} },
            { cle: 'decision_jury', libelle: 'Décision de jury', format: 'booleen' },
            { cle: 'etat', libelle: 'État', format: 'badge', tons: { 'Diplôme validé': 'green', 'Diplôme préparé': 'blue', 'Décision de jury disponible': 'amber', 'En attente du jury': 'slate' } },
          ],
          videTitre: 'Aucun étudiant en fin de cycle',
          videTexte: 'Les inscriptions validées de L3 et M2 de l’année courante apparaîtront ici.',
        },
        {
          id: 'attestations', libelle: 'Diplômes & attestations', icone: 'award',
          endpoint: '/graduation/diplomes/',
          rechercheLocale: ['nom_complet', 'matricule', 'ref_formation'],
          recherchePlaceholder: 'Diplômé(e), matricule…',
          filtres: [{ param: 'statut', libelle: 'Statut', options: [
            { valeur: 'BROUILLON', libelle: 'Brouillons' },
            { valeur: 'VALIDATION_PENDING', libelle: 'En attente de validation' },
            { valeur: 'VALIDATED', libelle: 'Validés' },
            { valeur: 'REVOKED', libelle: 'Révoqués' },
          ] }],
          colonnes: COLONNES_DIPLOMES,
          videTitre: 'Aucun diplôme',
          videTexte: 'Les diplômes créés depuis l’écran Diplômes de la scolarité apparaîtront ici.',
        },
        {
          id: 'certificats', libelle: 'Certificats & gabarits', icone: 'layoutTemplate',
          endpoint: '/graduation/modeles/',
          rechercheLocale: ['libelle', 'formation'],
          recherchePlaceholder: 'Gabarit ou formation…',
          note: 'Gabarits de documents (diplôme, attestation, certificat, relevé de notes). Les gabarits [Exemple] sont des métadonnées sans fichier PDF.',
          colonnes: [
            { cle: 'libelle', libelle: 'Gabarit', gras: true },
            { cle: 'type', libelle: 'Type', format: 'badge', libelleCle: 'type_display', tons: { DIPLOME: 'indigo', ATTESTATION: 'blue', CERTIFICAT: 'cyan', RELEVE_NOTES: 'amber' } },
            { cle: 'formation', libelle: 'Formation (vide = global)', format: 'muted' },
            { cle: 'actif', libelle: 'Actif', format: 'booleen' },
            { cle: 'date_modification', libelle: 'Modifié le', format: 'datetime' },
          ],
          videTitre: 'Aucun gabarit',
          videTexte: 'Les gabarits de documents officiels apparaîtront ici.',
        },
        {
          id: 'registres', libelle: 'Registres & modèles', icone: 'bookOpen',
          endpoint: '/graduation/registres/',
          rechercheLocale: ['annee_academique'],
          recherchePlaceholder: 'Année académique…',
          note: 'Conservation longue durée : un registre par année, clôture irréversible après vérification complète.',
          colonnes: [
            { cle: 'annee_academique', libelle: 'Registre annuel', gras: true },
            { cle: 'diplomes_count', libelle: 'Diplômes inscrits', format: 'nombre' },
            { cle: 'cloture', libelle: 'Clôturé', format: 'booleen' },
            { cle: 'date_cloture', libelle: 'Date de clôture', format: 'datetime' },
          ],
          videTitre: 'Aucun registre',
          videTexte: 'Le registre de l’année courante apparaîtra ici dès les premiers diplômes.',
        },
      ]}
      ongletInitial={ongletInitial}
    />
  )
}
