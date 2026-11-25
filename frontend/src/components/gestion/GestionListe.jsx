/**
 * Briques communes de gestion des listes : sélection, panneau d'actions,
 * exports, import en deux temps et bilan de retrait.
 *
 * Un seul implémenteur pour tous les écrans (Référentiels, UE/ECUE, Maquettes) :
 * les libellés, les formats, l'ordre des boutons et les règles d'activation
 * sont donc strictement identiques d'une liste à l'autre. Les composants ne
 * connaissent ni les modèles ni les droits : ils reçoivent des URL et des
 * callbacks, et n'affichent jamais une action que l'écran n'a pas autorisée.
 *
 * Sécurité : aucune décision n'est prise ici. Les URL d'import/export
 * pointent sur des routes qui re-vérifient les droits côté serveur, et un
 * import n'est appliqué qu'après un aperçu explicite (`mode=importer`).
 */
import { useEffect, useRef, useState } from 'react'
import api from '../../services/api'
import { useToast } from '../../context/ToastContext'
import '../../styles/maquettes.css'

export const FORMATS_EXPORT = [
  { valeur: 'docx', libelle: 'Export Word', icone: 'bi-file-earmark-word', ton: 'word' },
  { valeur: 'pdf', libelle: 'Export PDF', icone: 'bi-file-earmark-pdf', ton: 'pdf' },
  { valeur: 'xlsx', libelle: 'Export Excel', icone: 'bi-file-earmark-excel', ton: 'excel' },
  { valeur: 'csv', libelle: 'Export CSV', icone: 'bi-filetype-csv', ton: 'csv' },
]

export const FORMATS_IMPORT = [
  { valeur: 'xlsx', libelle: 'Importer un fichier Excel', accept: '.xlsx', icone: 'bi-file-earmark-excel' },
  { valeur: 'csv', libelle: 'Importer un fichier CSV', accept: '.csv', icone: 'bi-filetype-csv' },
]

/** Déclenche le téléchargement d'un blob déjà récupéré par l'API. */
export function telechargerBlob(blob, nom) {
  const url = URL.createObjectURL(blob)
  const lien = document.createElement('a')
  lien.href = url
  lien.download = nom || 'export'
  document.body.appendChild(lien)
  lien.click()
  lien.remove()
  // Laisse au navigateur le temps d'ouvrir le flux avant révocation.
  setTimeout(() => URL.revokeObjectURL(url), 2000)
}

/** Libellé humain d'une clé de résumé (`ues_creees` → « UES créées »). */
export function libelleResume(cle) {
  const connus = {
    lignes: 'ligne(s) analysée(s)',
    creations: 'création(s)',
    mises_a_jour: 'mise(s) à jour',
    rejets: 'rejet(s)',
    avertissements: 'avertissement(s)',
    demandees: 'valeur(s) demandée(s)',
    supprimees: 'retirée(s)',
    bloquees: 'non retirée(s)',
    introuvables: 'introuvable(s)',
    ues_creees: 'UE créée(s)',
    ues_mises_a_jour: 'UE mise(s) à jour',
    ecues_creees: 'ECUE créée(s)',
    ecues_mises_a_jour: 'ECUE mise(s) à jour',
    maquettes_creees: 'maquette(s) créée(s)',
    maquettes_completees: 'maquette(s) complétée(s)',
    doublons: 'doublon(s) ignoré(s)',
  }
  return connus[cle] || cle.replace(/_/g, ' ')
}

/** Résumé chiffré d'un rapport d'import ou d'un bilan de retrait. */
export function ResumeChiffre({ resume }) {
  if (!resume) return null
  return (
    <ul className="maq-bilan-liste">
      {Object.entries(resume).map(([cle, valeur]) => (
        <li key={cle}>
          <strong>{valeur}</strong> {libelleResume(cle)}
        </li>
      ))}
    </ul>
  )
}

/** Case à cocher de sélection, avec libellé accessible explicite. */
export function CaseSelection({ coche, onChange, libelle, indeterinee = false, disabled = false }) {
  const ref = useRef(null)
  useEffect(() => {
    if (ref.current) ref.current.indeterminate = indeterinee
  }, [indeterinee, coche])
  return (
    <input
      ref={ref}
      type="checkbox"
      className="maq-case"
      checked={Boolean(coche)}
      onChange={onChange}
      disabled={disabled}
      aria-label={libelle}
    />
  )
}

/**
 * Panneau d'actions à droite de la liste.
 *
 * `actions` : tableau d'objets `{ cle, libelle, icone, onClick, desactive, titre }`
 * — l'ordre est celui de la spécification : Créer, Visualiser, Modifier,
 * Supprimer. `nombreSelection` vient de l'écran, jamais du composant.
 */
export function PanneauActions({
  nombreSelection,
  actions,
  singulier = 'valeur',
  pluriel = 'valeurs',
  aide = '',
  ariaLabel,
}) {
  const message = nombreSelection === 0
    ? `Aucune ${singulier} sélectionnée`
    : nombreSelection === 1
      ? <><strong>1</strong> {singulier} sélectionnée</>
      : <><strong>{nombreSelection}</strong> {pluriel} sélectionnées</>

  return (
    <aside className="maq-panneau" aria-label={ariaLabel || 'Actions sur la sélection'}>
      <h3 className="maq-panneau-titre">
        <i className="bi bi-sliders" aria-hidden="true"></i>Actions
      </h3>
      <p
        className="maq-panneau-selection"
        role="status"
        aria-live="polite"
        data-testid="gestion-compteur-selection"
      >
        {message}
      </p>
      <div className="maq-panneau-boutons">
        {actions.map((action) => (
          <button
            key={action.cle}
            type="button"
            className={`maq-btn-action is-${action.cle}`}
            onClick={action.onClick}
            disabled={Boolean(action.desactive)}
            aria-label={action.ariaLabel || action.libelle}
            title={action.titre || action.libelle}
          >
            <i className={`bi ${action.icone}`} aria-hidden="true"></i>
            <span>{action.libelle}</span>
          </button>
        ))}
      </div>
      {aide && (
        <p className="maq-panneau-aide">
          <i className="bi bi-info-circle" aria-hidden="true"></i>
          {aide}
        </p>
      )}
    </aside>
  )
}

/**
 * Barre d'outils sous la liste : exports (Word/PDF/Excel/CSV) et import
 * Excel/CSV en deux temps, avec aperçu, rapport et modèle téléchargeable.
 *
 * Props :
 * - `exporterUrl(format)` : URL de l'export pour le format demandé ;
 * - `importerUrl`, `modeleUrl(format)` : routes d'import et de modèle ;
 * - `selection` : identifiants sélectionnés (l'écran décide du périmètre) ;
 * - `onImporte(rapport)` : appelé après un import appliqué ;
 * - `detail` : `{ actif, onChange, libelle }` pour l'option « détail » ;
 * - `noteExport` : texte d'aide sur le périmètre exporté.
 */
export function BarreOutils({
  exporterUrl,
  importerUrl,
  modeleUrl,
  selection = [],
  onImporte,
  noteExport,
  detail = null,
  libelleRessource = 'valeurs',
  importDisponible = true,
  exportDisponible = true,
}) {
  const toast = useToast()
  const [exportEnCours, setExportEnCours] = useState('')
  const [importEnCours, setImportEnCours] = useState(false)
  const [analyse, setAnalyse] = useState(null)
  const [rapport, setRapport] = useState(null)
  const [erreurImport, setErreurImport] = useState('')
  const fichierRef = useRef(null)
  const fichierChoisiRef = useRef(null)

  const notifier = (message, type = 'success') => {
    toast?.showToast?.(message, type)
  }

  const exporter = async (format) => {
    setExportEnCours(format)
    try {
      const { blob, fileName } = await api.getBlob(exporterUrl(format))
      telechargerBlob(blob, fileName || `export.${format}`)
      notifier(
        `Export ${format.toUpperCase()} généré pour ${selection.length || `${libelleRessource} du périmètre`}.`,
      )
    } catch (err) {
      notifier(
        err.response?.data?.error || `Export ${format.toUpperCase()} impossible.`,
        'error',
      )
    } finally {
      setExportEnCours('')
    }
  }

  const ouvrirSelecteur = (format) => {
    const champ = fichierRef.current
    if (!champ) return
    champ.accept = FORMATS_IMPORT.find((f) => f.valeur === format)?.accept || '.csv,.xlsx'
    champ.click()
  }

  const surFichier = async (evenement) => {
    const fichier = evenement.target.files?.[0]
    evenement.target.value = ''
    if (!fichier) return
    setImportEnCours(true)
    setErreurImport('')
    setRapport(null)
    fichierChoisiRef.current = fichier
    const donnees = new FormData()
    donnees.append('fichier', fichier)
    donnees.append('mode', 'apercu')
    try {
      const res = await api.post(importerUrl, donnees)
      setAnalyse(res.data)
    } catch (err) {
      const data = err.response?.data
      if (data?.resume) {
        setAnalyse(data)
      } else {
        const message = data?.error || 'Analyse du fichier impossible (format, taille ou structure).'
        setErreurImport(message)
        notifier(message, 'error')
      }
    } finally {
      setImportEnCours(false)
    }
  }

  const telechargerModele = async (format) => {
    try {
      const { blob, fileName } = await api.getBlob(modeleUrl(format))
      telechargerBlob(blob, fileName || `modele-import.${format}`)
    } catch {
      notifier('Téléchargement du modèle impossible.', 'error')
    }
  }

  const confirmer = async () => {
    if (!analyse) return
    setImportEnCours(true)
    try {
      const donnees = new FormData()
      donnees.append('fichier', fichierChoisiRef.current)
      donnees.append('mode', 'importer')
      const res = await api.post(importerUrl, donnees)
      setAnalyse(null)
      setRapport(res.data)
      fichierChoisiRef.current = null
      notifier(res.data?.message || 'Import appliqué.')
      onImporte?.(res.data)
    } catch (err) {
      const data = err.response?.data
      if (data?.resume) setAnalyse(data)
      notifier(data?.error || "Import impossible : aucune donnée n'a été enregistrée.", 'error')
    } finally {
      setImportEnCours(false)
    }
  }

  return (
    <>
      <div className="maq-barre-outils">
        {exportDisponible && (
          <div className="maq-barre-groupe" aria-label={`Exporter les ${libelleRessource}`}>
            <span className="maq-barre-titre">
              <i className="bi bi-box-arrow-down" aria-hidden="true"></i>Exporter
            </span>
            <div className="maq-barre-boutons">
              {FORMATS_EXPORT.map((format) => (
                <button
                  key={format.valeur}
                  type="button"
                  className={`maq-btn-export is-${format.ton}`}
                  onClick={() => exporter(format.valeur)}
                  disabled={Boolean(exportEnCours) || importEnCours}
                  aria-label={format.libelle}
                >
                  <i className={`bi ${format.icone}`} aria-hidden="true"></i>
                  <span>{format.libelle.replace('Export ', '')}</span>
                  {exportEnCours === format.valeur && (
                    <span className="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span>
                  )}
                </button>
              ))}
            </div>
            {detail && (
              <label className="maq-case-detail">
                <input
                  type="checkbox"
                  checked={Boolean(detail.actif)}
                  onChange={(e) => detail.onChange?.(e.target.checked)}
                />
                {detail.libelle}
              </label>
            )}
            <p className="maq-barre-note">
              {selection.length
                ? `${selection.length} ${libelleRessource} sélectionnée(s) seront exportées.`
                : noteExport
                  || `Aucune sélection : toutes les ${libelleRessource} du périmètre (filtres) seront exportées.`}
            </p>
          </div>
        )}

        {importDisponible && (
          <div className="maq-barre-groupe" aria-label={`Importer des ${libelleRessource}`}>
            <span className="maq-barre-titre">
              <i className="bi bi-box-arrow-in-down" aria-hidden="true"></i>Importer
            </span>
            <div className="maq-barre-boutons">
              {FORMATS_IMPORT.map((format) => (
                <button
                  key={format.valeur}
                  type="button"
                  className="maq-btn-import"
                  onClick={() => ouvrirSelecteur(format.valeur)}
                  disabled={importEnCours}
                  aria-label={format.libelle}
                >
                  <i className={`bi ${format.icone}`} aria-hidden="true"></i>
                  <span>{format.libelle.replace('Importer un fichier ', 'Import ')}</span>
                </button>
              ))}
              <button
                type="button"
                className="maq-btn-modele"
                onClick={() => telechargerModele('csv')}
                aria-label="Télécharger le modèle d’import CSV"
              >
                <i className="bi bi-download" aria-hidden="true"></i>
                <span>Modèle</span>
              </button>
            </div>
            {importEnCours && (
              <p className="maq-barre-note" role="status">
                <span className="spinner-border spinner-border-sm" aria-hidden="true"></span>
                {' '}Analyse du fichier…
              </p>
            )}
            {erreurImport && !analyse && (
              <p className="maq-barre-note maq-barre-note--erreur" role="alert">{erreurImport}</p>
            )}
            <p className="maq-barre-note">
              Aperçu obligatoire avant écriture : rien n’est enregistré tant que l’import
              n’est pas confirmé.
            </p>
            <input
              ref={fichierRef}
              type="file"
              className="visually-hidden"
              data-testid="gestion-fichier-import"
              onChange={surFichier}
            />
          </div>
        )}
      </div>

      {analyse && (
        <div className="maq-modale-voile" role="presentation">
          <div
            className="maq-modale"
            role="dialog"
            aria-modal="true"
            aria-labelledby="titre-apercu-import"
          >
            <header className="maq-modale-entete">
              <h5 className="maq-modale-titre" id="titre-apercu-import">
                <i className="bi bi-clipboard-check" aria-hidden="true"></i>
                Aperçu de l’import — {analyse.fichier || 'fichier sélectionné'}
              </h5>
              <button
                type="button"
                className="maq-modale-fermer"
                onClick={() => setAnalyse(null)}
                aria-label="Fermer l’aperçu"
              >
                <i className="bi bi-x-lg" aria-hidden="true"></i>
              </button>
            </header>
            <div className="maq-modale-corps">
              <p className="maq-modale-note">
                <i className="bi bi-info-circle" aria-hidden="true"></i>
                Aucune écriture n’a encore eu lieu. Vérifiez le rapport, puis confirmez
                l’import : il sera appliqué en une seule transaction.
              </p>
              <ResumeChiffre resume={analyse.resume} />
              {analyse.erreurs?.length > 0 && (
                <div className="maq-rapport-bloc is-erreur" role="alert">
                  <h6><i className="bi bi-exclamation-triangle" aria-hidden="true"></i>Erreurs bloquantes</h6>
                  <ul>
                    {analyse.erreurs.slice(0, 30).map((erreur, index) => (
                      <li key={`${erreur.ligne}-${index}`}>
                        {erreur.ligne ? `Ligne ${erreur.ligne} : ` : ''}{erreur.message}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {analyse.avertissements?.length > 0 && (
                <div className="maq-rapport-bloc is-avertissement">
                  <h6><i className="bi bi-exclamation-circle" aria-hidden="true"></i>Avertissements</h6>
                  <ul>
                    {analyse.avertissements.map((message, index) => (
                      <li key={index}>{message}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
            <footer className="maq-modale-pied">
              <button type="button" className="cand-btn-fantome" onClick={() => setAnalyse(null)}>
                Annuler
              </button>
              <button
                type="button"
                className="maq-btn-confirmer"
                onClick={confirmer}
                disabled={!analyse.importable || importEnCours}
                title={analyse.importable
                  ? 'Appliquer l’import'
                  : 'Corrigez les erreurs du fichier avant d’importer'}
              >
                {importEnCours ? 'Import…' : 'Confirmer l’import'}
              </button>
            </footer>
          </div>
        </div>
      )}

      {rapport && (
        <div className="maq-modale-voile" role="presentation">
          <div
            className="maq-modale"
            role="dialog"
            aria-modal="true"
            aria-labelledby="titre-rapport-import"
          >
            <header className="maq-modale-entete">
              <h5 className="maq-modale-titre" id="titre-rapport-import">
                <i className="bi bi-check2-circle" aria-hidden="true"></i>
                Import terminé
              </h5>
              <button
                type="button"
                className="maq-modale-fermer"
                onClick={() => setRapport(null)}
                aria-label="Fermer le rapport"
              >
                <i className="bi bi-x-lg" aria-hidden="true"></i>
              </button>
            </header>
            <div className="maq-modale-corps">
              <p className="maq-modale-note">
                <i className="bi bi-shield-check" aria-hidden="true"></i>
                {rapport.message || 'Import appliqué en une seule transaction : en cas d’erreur, rien n’aurait été conservé.'}
              </p>
              <ResumeChiffre resume={rapport.resume} />
            </div>
            <footer className="maq-modale-pied">
              <button type="button" className="maq-btn-confirmer" onClick={() => setRapport(null)}>
                Fermer
              </button>
            </footer>
          </div>
        </div>
      )}
    </>
  )
}

/**
 * Bilan d'un retrait (ou d'un lot mixte) : retirées, bloquées avec motif,
 * introuvables. Aucun détail n'est masqué — l'utilisateur doit pouvoir dire
 * pourquoi une ligne n'a pas été retirée.
 */
export function BilanSuppression({ bilan, onFermer, titre = 'Bilan de la suppression' }) {
  if (!bilan) return null
  return (
    <div className="maq-modale-voile" role="presentation">
      <div className="maq-modale" role="dialog" aria-modal="true" aria-labelledby="titre-bilan-suppression">
        <header className="maq-modale-entete">
          <h5 className="maq-modale-titre" id="titre-bilan-suppression">
            <i className="bi bi-list-check" aria-hidden="true"></i>{titre}
          </h5>
          <button type="button" className="maq-modale-fermer" onClick={onFermer} aria-label="Fermer le bilan">
            <i className="bi bi-x-lg" aria-hidden="true"></i>
          </button>
        </header>
        <div className="maq-modale-corps">
          <ResumeChiffre resume={bilan.resume} />
          {bilan.supprimees?.length > 0 && (
            <div className="maq-rapport-bloc">
              <h6><i className="bi bi-check2" aria-hidden="true"></i>Retirée(s)</h6>
              <ul>
                {bilan.supprimees.map((element) => (
                  <li key={element.id}>
                    {element.libelle}
                    {element.mode ? ` — ${element.mode}` : ''}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {bilan.bloquees?.length > 0 && (
            <div className="maq-rapport-bloc is-erreur">
              <h6><i className="bi bi-shield-exclamation" aria-hidden="true"></i>Non retirée(s)</h6>
              <ul>
                {bilan.bloquees.map((element) => (
                  <li key={element.id}>
                    <strong>{element.libelle}</strong> — {element.motif || element.motifs?.join(' ')}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {bilan.introuvables?.length > 0 && (
            <div className="maq-rapport-bloc is-avertissement">
              <h6><i className="bi bi-question-circle" aria-hidden="true"></i>Introuvable(s)</h6>
              <ul>
                {bilan.introuvables.map((identifiant) => <li key={identifiant}>#{identifiant}</li>)}
              </ul>
            </div>
          )}
        </div>
        <footer className="maq-modale-pied">
          <button type="button" className="maq-btn-confirmer" onClick={onFermer}>Fermer</button>
        </footer>
      </div>
    </div>
  )
}

/** Bascule un identifiant dans une sélection (immuable). */
export function basculerSelection(selection, identifiant) {
  return selection.includes(identifiant)
    ? selection.filter((element) => element !== identifiant)
    : [...selection, identifiant]
}

/** Coche ou décoche toute une page : renvoie la nouvelle sélection. */
export function basculerTout(selection, identifiants) {
  const tousPresents = identifiants.length > 0 && identifiants.every((id) => selection.includes(id))
  if (tousPresents) return selection.filter((id) => !identifiants.includes(id))
  return [...new Set([...selection, ...identifiants])]
}
