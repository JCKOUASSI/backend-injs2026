import { useEffect, useMemo, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import api from '../services/api'
import { useToast } from '../context/ToastContext'
import { formatApiErrors } from '../utils/apiErrors'
import { FLAGS_QUERY_KEY } from '../lib/queryClient'

/**
 * P00-08 — Écran d'administration des feature flags (ADMIN uniquement, la
 * route est gardée par ProtectedRoute/ADMIN_LEVEL_ROLES).
 *
 * Réutilise l'API Paramètres existante : les flags sont des Parametre de
 * catégorie « flags ». Chaque bascule est historisée (ParametreHistorique)
 * et prise en compte immédiatement (invalidation du cache serveur par signal,
 * et de la carte React Query du frontend).
 */
const ROLE_OPTIONS = [
  'ADMIN', 'DIRECTION', 'CHEF_INJS_ADMIN', 'INJS_ADMIN', 'CHEF_SECRETARIAT',
  'SECRETARIAT', 'FINANCE', 'ARCHIVE', 'ENCADRANT', 'SUPERVISEUR', 'FORMATEUR', 'AUDITEUR',
]

function parseRoles(valeur) {
  try {
    const parsed = JSON.parse(valeur || '[]')
    return Array.isArray(parsed) ? parsed.filter((r) => typeof r === 'string') : []
  } catch {
    return null
  }
}

function StatusBadge({ on }) {
  return on
    ? <span className="badge badge-en-cours ms-2"><i className="bi bi-toggle-on me-1"></i>Activé</span>
    : <span className="badge bg-secondary ms-2"><i className="bi bi-toggle-off me-1"></i>Désactivé</span>
}

function FlagRow({ row, onSaved }) {
  const { showToast } = useToast()
  const rolesBased = row.type === 'text' && parseRoles(row.valeur) !== null
  const [valeur, setValeur] = useState(
    rolesBased ? JSON.stringify(parseRoles(row.valeur), null, 0) : row.valeur,
  )
  const [motif, setMotif] = useState('')
  const [saving, setSaving] = useState(false)
  const [history, setHistory] = useState(null)
  const [historyLoading, setHistoryLoading] = useState(false)

  const isOn = rolesBased ? parseRoles(valeur).length > 0 : ['true', '1', 'oui'].includes(String(valeur).toLowerCase())
  const changed = valeur !== row.valeur

  const save = async () => {
    setSaving(true)
    try {
      if (rolesBased) {
        // Valide le JSON de rôles avant envoi.
        const parsed = parseRoles(valeur)
        if (parsed === null) throw new Error('Liste JSON de rôles invalide')
        const inconnus = parsed.filter((r) => !ROLE_OPTIONS.includes(r))
        if (inconnus.length) throw new Error(`Rôles inconnus : ${inconnus.join(', ')}`)
      }
      await api.patch(`/parametres/${row.id}/`, {
        valeur,
        motif_modification: motif || '',
      })
      showToast(`Flag ${row.cle} enregistré`)
      setMotif('')
      await onSaved()
    } catch (err) {
      showToast(
        err?.response
          ? formatApiErrors(err.response.data, { fallback: "Erreur lors de l'enregistrement du flag" })
          : err.message,
        'error',
      )
    } finally {
      setSaving(false)
    }
  }

  const toggleHistory = async () => {
    if (history) { setHistory(null); return }
    setHistoryLoading(true)
    try {
      const res = await api.get(`/parametres/${row.id}/historique/`)
      setHistory(res.data ?? [])
    } catch {
      showToast("Erreur de chargement de l'historique.", 'error')
    } finally {
      setHistoryLoading(false)
    }
  }

  return (
    <tr data-testid={`flag-row-${row.cle}`}>
      <td style={{ width: '46%' }}>
        <div className="fw-semibold">
          {row.libelle}
          <StatusBadge on={isOn} />
        </div>
        <div><code className="small text-muted">{row.cle}</code></div>
        {row.description && <div className="small text-muted mt-1">{row.description}</div>}
        {history !== null && (
          <div className="mt-2" data-testid="flag-history">
            {historyLoading ? (
              <span className="small text-muted">Chargement…</span>
            ) : history.length === 0 ? (
              <span className="small text-muted">Aucune bascule enregistrée.</span>
            ) : (
              <ul className="small mb-0 ps-3">
                {history.map((h) => (
                  <li key={h.id}>
                    <strong>{h.nouvelle_valeur === 'true' ? 'Activé' : h.ancienne_valeur === 'true' ? 'Désactivé' : `${h.ancienne_valeur} → ${h.nouvelle_valeur}`}</strong>
                    {' '}par {h.modifie_par_username || '—'} le{' '}
                    {new Date(h.modifie_le).toLocaleString('fr-FR')}
                    {h.motif_modification ? ` — ${h.motif_modification}` : ''}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </td>
      <td style={{ width: '26%' }}>
        {rolesBased ? (
          <textarea
            className="form-control"
            rows={2}
            aria-label={`Rôles habilités pour ${row.cle}`}
            value={valeur}
            onChange={(e) => setValeur(e.target.value)}
            placeholder='["ADMIN"]'
          />
        ) : (
          <select
            className="form-select"
            aria-label={`État du flag ${row.cle}`}
            value={isOn ? 'true' : 'false'}
            onChange={(e) => setValeur(e.target.value)}
          >
            <option value="true">Activé</option>
            <option value="false">Désactivé</option>
          </select>
        )}
        <input
          className="form-control form-control-sm mt-2"
          type="text"
          placeholder="Motif de la bascule (recommandé)"
          value={motif}
          onChange={(e) => setMotif(e.target.value)}
          aria-label={`Motif pour ${row.cle}`}
        />
      </td>
      <td style={{ width: '28%', textAlign: 'right' }}>
        <button
          type="button"
          className="btn btn-primary btn-sm me-2"
          onClick={save}
          disabled={saving || !changed}
        >
          {saving ? '…' : 'Enregistrer'}
        </button>
        <button type="button" className="btn btn-outline-secondary btn-sm" onClick={toggleHistory}>
          {history !== null ? 'Masquer' : 'Historique'}
        </button>
      </td>
    </tr>
  )
}

export default function FeatureFlags() {
  const { showToast } = useToast()
  const queryClient = useQueryClient()
  const [flags, setFlags] = useState([])
  const [loading, setLoading] = useState(true)

  const load = async () => {
    try {
      const res = await api.get('/parametres/', { params: { categorie: 'flags', actif: 'true' } })
      setFlags(res.data?.results ?? res.data ?? [])
    } catch {
      showToast('Erreur de chargement des feature flags.', 'error')
    } finally {
      setLoading(false)
    }
  }

  // eslint-disable-next-line react-hooks/exhaustive-deps -- chargement initial unique
  useEffect(() => { load() }, [])

  const onSaved = async () => {
    // Le signal backend invalide déjà son cache ; on force aussi la carte
    // frontend pour un effet immédiat sur les écrans consommateurs.
    await queryClient.invalidateQueries({ queryKey: FLAGS_QUERY_KEY })
    await load()
  }

  const actifs = useMemo(() => flags.filter((f) => {
    if (f.type === 'text') return (parseRoles(f.valeur) || []).length > 0
    return ['true', '1', 'oui'].includes(String(f.valeur).toLowerCase())
  }), [flags])

  return (
    <div className="page-container">
      <div className="page-header">
        <div>
          <h1 className="page-title"><i className="bi bi-toggles me-2"></i>Fonctionnalités (feature flags)</h1>
          <p className="page-subtitle">
            Activez ou éteignez en urgence les fonctionnalités livrées derrière un interrupteur.
            Les flags sont livrés <strong>désactivés</strong> ; chaque bascule est tracée dans
            l’historique et appliquée immédiatement.
          </p>
        </div>
        <span className="text-muted small">{actifs.length}/{flags.length} activé(s)</span>
      </div>

      <div className="card">
        <div className="card-header">
          <span><i className="bi bi-flag me-2"></i>Flags par lot de la refonte</span>
        </div>
        <div className="card-body" style={{ padding: 0 }}>
          {loading ? (
            <div className="loading py-5"><div className="spinner"></div></div>
          ) : flags.length === 0 ? (
            <div className="text-center py-5 text-muted">
              <i className="bi bi-inbox" style={{ fontSize: '2rem' }}></i>
              <p className="mt-2">Aucun feature flag.</p>
            </div>
          ) : (
            <div className="table-responsive">
              <table className="table" style={{ width: '100%' }}>
                <thead>
                  <tr>
                    <th>Fonctionnalité</th>
                    <th>État</th>
                    <th style={{ textAlign: 'right' }}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {flags.map((row) => <FlagRow key={row.id} row={row} onSaved={onSaved} />)}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
