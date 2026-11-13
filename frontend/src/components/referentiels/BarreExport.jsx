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
  // Document prêt mais non remis : voir le commentaire de `lancer`.
  const [fichierPret, setFichierPret] = useState(null)

  const lancer = async (formatCible) => {
    if (enCours) return
    setEnCours(formatCible)
    setFichierPret(null)
    try {
      let diagnostic = null
      const nom = await exporterReferentiel(slug, formatCible, filtres, {
        onDiagnostic: (d) => { diagnostic = d },
      })
      // Dans un aperçu intégré (iframe), le téléchargement peut être bloqué
      // par le navigateur : le document est alors aussi ouvert dans un
      // onglet. Le dire évite le « je clique et rien ne se passe ».
      // Dans un aperçu intégré (iframe), l'ouverture automatique d'un onglet
      // est presque toujours refusée : elle est déclenchée après `await`, donc
      // hors du geste de l'utilisateur, et le bloqueur de fenêtres la rejette.
      // On garde alors le document à portée de clic : un lien cliqué **par
      // l'utilisateur** dispose, lui, de l'activation requise.
      const ouvertAilleurs = diagnostic?.ongletOuvert
        ? ' — ouvert dans un nouvel onglet'
        : diagnostic?.dansUneIframe
          ? ' — utilisez le lien affiché pour le récupérer'
          : ''
      if (diagnostic?.dansUneIframe && !diagnostic?.ongletOuvert) {
        setFichierPret({ nom, url: diagnostic.url })
      }
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

      {fichierPret && (
        <div className="ref-export-repli" role="status">
          <div className="ref-export-repli-entete">
            <span className="ref-export-repli-nom">
              <i className="bi bi-file-earmark-check" aria-hidden="true" /> {fichierPret.nom}
            </span>
            <button
              type="button"
              className="ref-export-repli-fermer"
              onClick={() => setFichierPret(null)}
              aria-label="Masquer le bloc de récupération"
            >
              <i className="bi bi-x" aria-hidden="true" />
            </button>
          </div>

          <p className="ref-export-repli-aide">
            Le téléchargement est bloqué dans cet aperçu intégré. Récupérez le
            fichier, ou ouvrez l’application dans un onglet — les téléchargements
            y fonctionnent normalement.
          </p>

          <div className="ref-export-repli-actions">
            {/* Lien vers une vraie ressource serveur (Content-Disposition:
                attachment) : le clic de l'utilisateur déclenche un
                téléchargement ordinaire, sans dépendre d'un blob ni d'une
                fenêtre surgissée. */}
            <a
              className="ref-export-repli-lien"
              href={fichierPret.url}
              download={fichierPret.nom}
              onClick={() => setFichierPret(null)}
            >
              <i className="bi bi-download" aria-hidden="true" /> Récupérer le fichier
            </a>
            {/* Sortir de l'iframe : hors aperçu intégré, plus aucune
                restriction de téléchargement ne s'applique. */}
            <a
              className="ref-export-repli-lien ref-export-repli-lien--secondaire"
              href={typeof window === 'undefined' ? '#' : window.location.href}
              target="_blank"
              rel="noreferrer"
            >
              <i className="bi bi-box-arrow-up-right" aria-hidden="true" /> Ouvrir l’application dans un onglet
            </a>
          </div>
        </div>
      )}
    </div>
  )
}
