import React from 'react'
import { statutVariant } from '../../services/scolarite'

/** Badge coloré d'un statut de candidature, d'admission, d'inscription ou de pièce. */
export default function StatutBadge({ statut, libelle }) {
  if (!statut) return <span className="text-muted">—</span>
  return (
    <span className={`badge bg-${statutVariant(statut)}`}>
      {libelle || statut}
    </span>
  )
}
