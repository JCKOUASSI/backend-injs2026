import React, { useState } from 'react'
import { FORMATS_EXPORT, exporterReferentiel } from '../../services/referentiels'

/**
 * Barre d'export d'un référentiel : Word, Excel, CSV et PDF.
 *
 * Le périmètre exporté est celui affiché à l'écran : les filtres courants
 * sont transmis au serveur, qui applique exactement les mêmes critères.
 * Le composant n'élabore aucun document lui-même — le backend produit le
 * fichier (en-têtes institutionnels, colonnes, total, pagination PDF).
 */
export default function BarreExport({ slug, filtres = {}, total = 0, onMessage }) {
  const [enCours, setEnCours] = useState('')

  const lancer = async (formatCible) => {
    if (enCours) return
    setEnCours(formatCible)
    try {
      const nom = await exporterReferentiel(slug, formatCible, filtres)
      onMessage?.('ok', `Export ${formatCible.toUpperCase()} généré : ${nom}`)
    } catch (e) {
      onMessage?.(
        'erreur',
        e.response?.data?.detail ||
          (e.response?.status === 403
            ? "Vous n'avez pas la permission d'exporter ce référentiel."
            : "Export impossible."),
      )
    } finally {
      setEnCours('')
    }
  }

  return (
    <div className="ref-export" role="group" aria-label="Exporter le référentiel">
      <span className="ref-export-libelle">
        <i className="bi bi-download" aria-hidden="true" /> Exporter
        {total > 0 && <em> ({total} enregistrement{total > 1 ? 's' : ''})</em>}
      </span>
      {FORMATS_EXPORT.map((format) => (
        <button
          key={format.cle}
          type="button"
          className="ref-btn ref-btn--export"
          onClick={() => lancer(format.cle)}
          disabled={Boolean(enCours)}
          title={`Télécharger au format ${format.libelle}`}
          aria-label={`Exporter au format ${format.libelle}`}
        >
          <i className={`bi ${format.icone}`} aria-hidden="true" />{' '}
          {enCours === format.cle ? '…' : format.libelle}
        </button>
      ))}
    </div>
  )
}
