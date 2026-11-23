import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import api from '../../services/api'
import { useToast } from '../../context/ToastContext'
import { messageErreur } from '../../services/scolarite'

/**
 * Écran de **génération de documents** (documents scolaires, exports EDT,
 * relevés de notes).
 *
 * Chaque carte décrit un document produit par un endpoint d'export existant du
 * backend (`/api/exports/…`, `/api/formations/{id}/modules/{id}/notes/fiche/pdf/`,
 * `/api/participant/{id}/notes-fiche/export/{fmt}/`…) : l'écran ne fabrique aucun
 * document côté client, il paramètre l'appel et télécharge le fichier renvoyé.
 * Le serveur reste seul juge du droit (règle S3) : un 403 s'affiche tel quel.
 */

function useOptions(parametre) {
  return useQuery({
    queryKey: ['ecran-documents', 'options', parametre?.optionsEndpoint, parametre?.optionsCleLibelle],
    queryFn: async () => {
      const res = await api.get(parametre.optionsEndpoint)
      const brut = Array.isArray(res?.data) ? res.data : (res?.data?.results || [])
      return brut.map((o) => ({
        valeur: String(o[parametre.optionsCleValeur || 'id']),
        libelle: o[parametre.optionsCleLibelle || 'libelle'] || o.nom || o.code
          || o[parametre.optionsCleValeur || 'id'],
      }))
    },
    enabled: Boolean(parametre?.optionsEndpoint),
    staleTime: 10 * 60 * 1000,
    retry: false,
  })
}

function CarteDocument({ document: doc }) {
  const { showToast } = useToast()
  const [valeurs, setValeurs] = useState({})
  const [enCours, setEnCours] = useState(null)
  const parametres = doc.parametres || []

  const manquants = parametres
    .filter((p) => p.requis !== false && !valeurs[p.cle])
    .map((p) => p.libelle)

  const generer = async (format) => {
    if (manquants.length) {
      showToast(`Renseigner : ${manquants.join(', ')}.`, 'error')
      return
    }
    setEnCours(format.id)
    try {
      const chemin = typeof doc.chemin === 'function'
        ? doc.chemin(valeurs, format)
        : doc.chemin
      const { blob, fileName } = await api.getBlob(chemin)
      const url = URL.createObjectURL(blob)
      const lien = window.document.createElement('a')
      lien.href = url
      lien.download = fileName || `${doc.id || 'document'}.${format.suffixe || 'pdf'}`
      window.document.body.appendChild(lien)
      lien.click()
      lien.remove()
      URL.revokeObjectURL(url)
      showToast(`${doc.libelle} (${format.libelle}) téléchargé.`)
    } catch (err) {
      showToast(messageErreur(err, 'Génération refusée par le serveur.'), 'error')
    } finally {
      setEnCours(null)
    }
  }

  const styleBouton = (format) => {
    if (format.id === 'excel') return 'btn-outline-success'
    if (format.id === 'pdf') return 'btn-outline-danger'
    return 'btn-outline-primary'
  }

  return (
    <article className="gen-doc-card">
      <div className="gen-doc-head">
        <span className="gen-doc-icon" aria-hidden="true">
          <i className={`bi ${doc.icone || 'bi-file-earmark-text'}`}></i>
        </span>
        <div className="gen-doc-head-text">
          <h2 className="gen-doc-title">{doc.libelle}</h2>
          {doc.description && <p className="gen-doc-desc">{doc.description}</p>}
        </div>
      </div>
      {parametres.length > 0 && (
        <div className="gen-doc-body">
          {parametres.map((p) => (
            <Parametre
              key={p.cle}
              parametre={p}
              valeur={valeurs[p.cle]}
              onChange={(v) => setValeurs((prev) => ({ ...prev, [p.cle]: v }))}
            />
          ))}
          {manquants.length > 0 && (
            <p className="gen-doc-hint">
              <i className="bi bi-info-circle me-1"></i>
              Champs requis : {manquants.join(', ')}.
            </p>
          )}
        </div>
      )}
      <div className="gen-doc-foot">
        {(doc.formats || [{ id: 'pdf', libelle: 'PDF', suffixe: 'pdf' }]).map((format) => (
          <button
            key={format.id}
            type="button"
            className={`btn btn-sm gen-doc-btn ${styleBouton(format)}`}
            onClick={() => generer(format)}
            disabled={enCours === format.id}
            data-testid={`doc-${doc.id}-${format.id}`}
          >
            {enCours === format.id
              ? <span className="spinner-border spinner-border-sm me-1"></span>
              : <i className={`bi ${format.icone || 'bi-download'} me-1`}></i>}
            {format.libelle}
          </button>
        ))}
      </div>
    </article>
  )
}

function Parametre({ parametre, valeur, onChange }) {
  const { data: options } = useOptions(parametre)
  const choix = parametre.options || options || []
  return (
    <div className="gen-doc-field">
      <label className="gen-doc-label">
        {parametre.libelle}
        {parametre.requis !== false && <span className="gen-doc-required"> *</span>}
      </label>
      {parametre.type === 'select' ? (
        <select
          className="form-select"
          value={valeur ?? ''}
          onChange={(e) => onChange(e.target.value)}
        >
          <option value="">— choisir —</option>
          {choix.map((o) => <option key={o.valeur} value={o.valeur}>{o.libelle}</option>)}
        </select>
      ) : (
        <input
          type={parametre.type === 'nombre' ? 'number' : 'text'}
          className="form-control"
          value={valeur ?? ''}
          placeholder={parametre.placeholder || ''}
          onChange={(e) => onChange(e.target.value)}
        />
      )}
    </div>
  )
}

export default function EcranDocuments({ ecran }) {
  return (
    <div className="gen-docs">
      <div className="gen-docs-grid">
        {(ecran.documents || []).map((doc) => (
          <CarteDocument key={doc.id || doc.libelle} document={doc} />
        ))}
      </div>
      {ecran.note && <p className="gen-panel-foot-note gen-docs-note">{ecran.note}</p>}
    </div>
  )
}
