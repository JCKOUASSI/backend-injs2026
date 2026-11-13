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
      let diagnostic = null
      const nom = await exporterReferentiel(slug, formatCible, filtres, {
        onDiagnostic: (d) => { diagnostic = d },
      })
      // Dans un aperçu intégré (iframe), le téléchargement peut être bloqué
      // par le navigateur : le document est alors aussi ouvert dans un
      // onglet. Le dire évite le « je clique et rien ne se passe ».
      const ouvertAilleurs = diagnostic?.ongletOuvert
        ? ' — ouvert dans un nouvel onglet'
        : diagnostic?.dansUneIframe
          ? ' — si aucun fichier n’apparaît, autorisez les téléchargements pour ce site'
          : ''
      onMessage?.(
        'ok',
        `Export ${formatCible.toUpperCase()} généré : ${nom}${ouvertAilleurs}`,
      )
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

      <div className="ref-export-formats">
        {FORMATS_EXPORT.map((format) => {
          const actif = enCours === format.cle
          return (
            <button
              key={format.cle}
              type="button"
              className={`ref-export-btn ref-export-btn--${format.cle}`}
              onClick={() => lancer(format.cle)}
              disabled={Boolean(enCours)}
              aria-busy={actif || undefined}
              title={`Télécharger au format ${format.libelle}`}
              aria-label={`Exporter au format ${format.libelle}`}
            >
              <span className="ref-export-btn-icone" aria-hidden="true">
                {actif ? (
                  <span className="ref-export-spinner" />
                ) : (
                  <i className={`bi ${format.icone}`} />
                )}
              </span>
              <span className="ref-export-btn-texte">
                {actif ? 'Génération…' : format.libelle}
              </span>
            </button>
          )
        })}
      </div>
    </div>
  )
}
