import React from 'react'

/**
 * Utilitaires partagés du hub « Présences QR » (affichage uniquement —
 * le serveur reste l'autorité : aucun de ces helpers ne décide d'un droit
 * ni d'un verdict de présence).
 */

// Erreur affichable : code métier + message + action recommandée
// (jamais de HTML brut ni de détail technique brut).
export function messageErreur(err, repli) {
  const d = err?.response?.data || {}
  const code = d.code_normalise || d.code || ''
  const message = d.message || d.detail || repli
  const action = d.action_recommandee ? ` — ${d.action_recommandee}` : ''
  return `${code ? `[${code}] ` : ''}${message}${action}`
}

export function formatHeure(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  return Number.isNaN(d.getTime())
    ? '—'
    : d.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })
}

// Canal d'une présence : badgeage QR automatique vs badgeage manuel
// identifiable sans ambiguïté (mode explicite posé par le serveur).
export function badgeCanal(ligne) {
  if (!ligne.pointage_id) return <span className="text-muted">—</span>
  if (ligne.mode === 'MANUEL') {
    return (
      <span className="badge text-bg-warning" title={`Motif : ${ligne.motif_manuel || '—'}`}>
        <i className="bi bi-pencil-square me-1"></i>Manuel{ligne.motif_manuel ? ` · ${ligne.motif_manuel}` : ''}
      </span>
    )
  }
  if (ligne.mode === 'QR_AUTOMATIQUE') {
    return (
      <span className="badge text-bg-success">
        <i className="bi bi-qr-code me-1"></i>QR
        {ligne.type_sortie === 'SORTIE_AUTOMATIQUE_FIN_SEANCE' ? ' · sortie auto.' : ''}
      </span>
    )
  }
  return <span className="badge text-bg-secondary">Non renseigné</span>
}

export const STATUTS_ASSIDUITE = {
  PRESENT: { libelle: 'Présent', classe: 'text-bg-success' },
  RETARD: { libelle: 'Retard', classe: 'text-bg-warning' },
  ABSENT: { libelle: 'Absent', classe: 'text-bg-danger' },
  ABSENCE_JUSTIFIEE: { libelle: 'Absence justifiée', classe: 'text-bg-info' },
  EXCUSE: { libelle: 'Excusé', classe: 'text-bg-info' },
  NON_RENSEIGNE: { libelle: 'Non renseigné', classe: 'text-bg-secondary' },
}

export function badgeStatut(statut) {
  if (!statut) return <span className="text-muted">— non pointé —</span>
  const conf = STATUTS_ASSIDUITE[statut] || { libelle: statut, classe: 'text-bg-secondary' }
  return <span className={`badge ${conf.classe}`}>{conf.libelle}</span>
}

/** Identifiant permanent d'une séance LMD : `INJS-S-######` (stable). */
export function identifiantPermanent(id) {
  return `INJS-S-${String(id).padStart(6, '0')}`
}

/** Distance haversine (m) — AFFICHAGE/simulation uniquement. */
export function distanceMetres(lat1, lon1, lat2, lon2) {
  const R = 6371000
  const rad = (deg) => (deg * Math.PI) / 180
  const dPhi = rad(lat2 - lat1)
  const dLambda = rad(lon2 - lon1)
  const a = Math.sin(dPhi / 2) ** 2
    + Math.cos(rad(lat1)) * Math.cos(rad(lat2)) * Math.sin(dLambda / 2) ** 2
  return 2 * R * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a))
}
