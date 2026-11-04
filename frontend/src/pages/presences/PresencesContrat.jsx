import React from 'react'
import '../../styles/presences.css'

/**
 * Contrat API du hub Présences QR — documentation intégrée, alignée sur
 * les endpoints réellement exposés par le backend Django du dépôt et sur
 * les codes d'erreur normalisés renvoyés aux clients (web et mobile).
 */

const ENDPOINTS = [
  ['GET', '/api/presences/seances-edt/du-jour/', 'Séances LMD du jour du périmètre utilisateur (date optionnelle).'],
  ['GET|POST', '/api/presences/seances-edt/{id}/qr/', 'QR de séance : lecture (enseignants/encadrants de la séance) / ouverture-régénération (enseignant).'],
  ['POST', '/api/presences/seances-edt/scan/', 'Badgeage web/app authentifié : entrée/sortie alternée par session QR.'],
  ['GET', '/api/presences/seances-edt/{id}/presences/', 'Registre d’une séance : lignes nominatives + synthèse serveur.'],
  ['POST', '/api/presences/seances-edt/{id}/emargement/', 'Émargement de masse des non-encore-pointés (enseignant de la séance, motif global).'],
  ['POST', '/api/presences/seances-edt/emargement/unitaire/', 'Badgeage manuel unitaire d’un participant (motif obligatoire).'],
  ['POST', '/api/presences/seances-edt/{id}/cloturer/', 'Clôture : sorties automatiques + absents non badgés, sur confirmation.'],
  ['GET', '/api/presences/seances-edt/supervision/', 'Supervision temps réel des séances du jour + résumé ; avec &limite=200, chargement explicite des 200 séances les plus proches de la date (horizon ±120 j, bloc periode).'],
  ['GET', '/api/presences/seances-edt/historique/', 'Registre historique transversal : ?date_debut=&date_fin=&type=&mode=&nom=&groupe=&seance_id= ; verdict de périmètre déduit, auteur manuel depuis l’audit (FORCE_ENTREE), aucune coordonnée exposée.'],
  ['POST', '/api/scan/secure/enter/', 'Entrée mobile sécurisée (jeton, position, appareil).'],
  ['POST', '/api/scan/secure/heartbeat/', 'Heartbeat géolocalisé (évaluation serveur, sortie auto après confirmations).'],
  ['POST', '/api/scan/secure/exit/', 'Sortie mobile sécurisée (jamais inventée : position ou fin de séance tracée).'],
  ['GET', '/api/scan/secure/status/', 'Statut de badgeage du participant pour une formation.'],
  ['GET', '/api/audit-logs/', 'Journal d’audit (filtres action, cible, période ; limite d’extraction, l’écran du hub charge 200 événements) — lecture seule.'],
  ['GET|POST|PUT', '/api/formations/ref/sites/', 'Sites géofence (coordonnées, rayon) — DFRC uniquement.'],
]

const CODES = [
  ['QR_INVALIDE', 'Jeton illisible, expiré ou séance annulée', 'Régénérer le QR de la séance avant de badger.'],
  ['PARTICIPANT_NON_BADGEABLE', 'Aucun lien vérifiable (inscription, affectation, encadrement)', 'Se présenter à l’enseignant pour un émargement manuel motivé.'],
  ['GPS_INDISPONIBLE', 'Aucune position exploitable', 'Activer la localisation ; à défaut, émargement manuel (motif GPS_INDISPONIBLE).'],
  ['PRECISION_GPS_INSUFFISANTE', 'Précision au-delà du seuil projet (80 m)', 'Se rapprocher d’une zone dégagée puis réessayer.'],
  ['HORS_PERIMETRE', 'Position hors du rayon autorisé du site', 'Rejoindre le périmètre de la salle puis rebadger.'],
  ['DOUBLE_ENTREE', 'Une entrée est déjà ouverte pour ce participant', 'Terminer la session en cours (sortie) avant de rebadger.'],
  ['DEVICE_NON_AUTORISE', 'Appareil non reconnu', 'Utiliser l’appareil habituel ou contacter l’administration.'],
  ['MOTIF_ABSENT', 'Badgeage manuel sans motif', 'Choisir un motif dans le catalogue avant validation.'],
  ['MOTIF_AUTRE_SANS_COMMENTAIRE', 'Motif AUTRE sans commentaire', 'Préciser la situation dans le commentaire.'],
]

export default function PresencesContrat() {
  return (
    <div>
      <div className="pqr-hero">
        <div>
          <span className="pqr-hero-badge"><i className="bi bi-file-earmark-code me-1"></i>CONTRAT API</span>
          <h1 className="pqr-hero-title">Contrat d’intégration Présences QR</h1>
          <p className="pqr-hero-intro">
            Règles opposables aux clients web et mobile. Le serveur est l’autorité unique :
            identité, jeton, séance, périmètre, doublons et horodatages y sont calculés.
          </p>
        </div>
      </div>

      <div className="pqr-panel">
        <div className="pqr-panel-tete"><span><i className="bi bi-diagram-3 me-2"></i>Règles structurantes</span></div>
        <div className="pqr-panel-corps">
          <ul className="mb-0">
            <li>Une séance publiée ouvre une <strong>session QR</strong> : jeton UUID propre à la séance, expirant à sa clôture, invalidé si la séance est annulée.</li>
            <li>Le scan exige une <strong>session authentifiée</strong> et un lien vérifiable : étudiant inscrit au groupe, enseignant affecté au créneau, encadrant désigné. Aucun rapprochement par nom.</li>
            <li>La <strong>géolocalisation</strong> est évaluée côté serveur (rayon du site/salle, précision maximale, double confirmation de sortie de périmètre). Aucune coordonnée n’apparaît dans les réponses publiques ; seules la source et une distance éventuelle y figurent.</li>
            <li>L’<strong>entrée</strong> empêche tout doublon ; la <strong>sortie</strong> est volontaire (QR) ou automatique tracée — jamais inventée. À la clôture, les entrées sans sortie deviennent des sorties automatiques et les non-badgés des absents non badgés.</li>
            <li>Le <strong>badgeage manuel</strong> est séparé du QR (mode explicite + motif obligatoire + acteur + audit). Il ne contourne jamais silencieusement une règle technique ou métier.</li>
            <li>Le <strong>heartbeat</strong> n’a lieu que pendant une séance ouverte ; l’historique et le journal d’audit sont conservés sans destruction.</li>
          </ul>
        </div>
      </div>

      <div className="pqr-panel">
        <div className="pqr-panel-tete"><span><i className="bi bi-hdd-network me-2"></i>Endpoints</span></div>
        <div className="table-container">
          <table className="table edt-table mb-0">
            <thead><tr><th>Méthode</th><th>Chemin</th><th>Rôle</th></tr></thead>
            <tbody>
              {ENDPOINTS.map(([methode, chemin, role]) => (
                <tr key={chemin}>
                  <td><span className="badge text-bg-primary">{methode}</span></td>
                  <td><code>{chemin}</code></td>
                  <td>{role}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="pqr-panel">
        <div className="pqr-panel-tete"><span><i className="bi bi-exclamation-octagon me-2"></i>Codes d’erreur normalisés</span></div>
        <div className="pqr-panel-corps">
          <p className="text-muted">
            Toute erreur métier renvoie <code>code_normalise</code>, <code>message</code> (français)
            et <code>action_recommandee</code>. Les écrans affichent le code et le message ;
            aucune pile technique n’est exposée.
          </p>
          <div className="table-container">
            <table className="table edt-table mb-0">
              <thead><tr><th>Code</th><th>Signification</th><th>Action recommandée</th></tr></thead>
              <tbody>
                {CODES.map(([code, signification, action]) => (
                  <tr key={code}>
                    <td><code>{code}</code></td>
                    <td>{signification}</td>
                    <td>{action}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <pre className="pqr-fiche mt-3 mb-0">{`Exemple — entrée validée (POST /api/presences/seances-edt/scan/) :
{
  "statut": "IN",
  "action": "ENTREE",
  "participant": "MAT011",
  "seance_intitule": "Programmation web",
  "timestamp": "2026-04-08T08:03:00Z",
  "mode": "QR_AUTOMATIQUE",
  "type_sortie": null,
  "source_position": "POSITION_VALIDE"
}`}</pre>
        </div>
      </div>
    </div>
  )
}
