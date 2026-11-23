import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import api from '../services/api'
import { useToast } from '../context/ToastContext'
import { formatApiErrors } from '../utils/apiErrors'
import '../styles/parametres.css'

const CATEGORIES = [
  { value: 'general', label: 'Général', icon: 'bi-building' },
  { value: 'scolarite', label: 'Scolarité / LMD', icon: 'bi-mortarboard' },
  { value: 'presences', label: 'Présences', icon: 'bi-qr-code' },
  { value: 'edt', label: 'EDT (import)', icon: 'bi-calendar3' },
  { value: 'notifications', label: 'Notifications', icon: 'bi-bell' },
  { value: 'securite', label: 'Sécurité', icon: 'bi-shield-lock' },
  { value: 'interface', label: 'Interface', icon: 'bi-palette' },
]

function parseChoices(json) {
  try {
    const parsed = JSON.parse(json || '{}')
    return parsed && typeof parsed === 'object' ? parsed : null
  } catch {
    return null
  }
}

function displayValue(row) {
  if (row.type === 'bool') {
    const v = String(row.valeur || '').toLowerCase()
    return ['true', '1', 'yes', 'oui'].includes(v) ? 'Oui' : 'Non'
  }
  return row.valeur || '—'
}

function ParamValueInput({ type, value, choices, onChange, disabled }) {
  if (type === 'bool') {
    return (
      <select className="form-select" value={value} onChange={e => onChange(e.target.value)} disabled={disabled}>
        <option value="true">Oui</option>
        <option value="false">Non</option>
      </select>
    )
  }
  if (type === 'choice' && choices) {
    return (
      <select className="form-select" value={value} onChange={e => onChange(e.target.value)} disabled={disabled}>
        <option value="">—</option>
        {Object.entries(choices).map(([k, v]) => (
          <option key={k} value={k}>{v}</option>
        ))}
      </select>
    )
  }
  if (type === 'integer' || type === 'decimal') {
    return (
      <input
        type="number"
        className="form-control"
        step={type === 'decimal' ? '0.01' : '1'}
        min="0"
        value={value}
        onChange={e => onChange(e.target.value)}
        disabled={disabled}
      />
    )
  }
  if (type === 'email') {
    return (
      <input type="email" className="form-control" value={value} onChange={e => onChange(e.target.value)} disabled={disabled} />
    )
  }
  if (type === 'date') {
    return (
      <input type="date" className="form-control" value={value} onChange={e => onChange(e.target.value)} disabled={disabled} />
    )
  }
  return (
    <input type="text" className="form-control" value={value} onChange={e => onChange(e.target.value)} disabled={disabled} />
  )
}

export default function Parametres() {
  const { showToast } = useToast()
  const [tab, setTab] = useState('general')
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [params, setParams] = useState([])
  const [modal, setModal] = useState(null)
  const [form, setForm] = useState({})
  const [history, setHistory] = useState([])
  const [historyLoading, setHistoryLoading] = useState(false)

  const load = async () => {
    setLoading(true)
    try {
      const res = await api.get('/parametres/', { params: { actif: 'true' } })
      setParams(res.data?.results ?? res.data ?? [])
    } catch {
      showToast('Erreur de chargement des paramètres.', 'error')
    } finally {
      setLoading(false)
    }
  }

  // eslint-disable-next-line react-hooks/exhaustive-deps -- rechargement intentionnel : la fonction de chargement n’est pas mémoïsée (l’ajouter provoquerait une boucle) ; les dépendances de données présentes pilotent déjà le (re)chargement.
  useEffect(() => { load() }, [])

  const visibleTabs = useMemo(() => {
    const counts = {}
    params.forEach(p => { counts[p.categorie] = (counts[p.categorie] || 0) + 1 })
    return CATEGORIES.filter(c => counts[c.value])
  }, [params])

  useEffect(() => {
    if (visibleTabs.length && !visibleTabs.some(c => c.value === tab)) {
      setTab(visibleTabs[0].value)
    }
  }, [visibleTabs, tab])

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    return params.filter(p => {
      if (p.categorie !== tab) return false
      if (!q) return true
      return [p.libelle, p.cle, p.description, p.valeur].some(
        v => String(v || '').toLowerCase().includes(q)
      )
    })
  }, [params, tab, query])

  // Indicateurs de pilotage, calculés sur la liste déjà chargée (aucun appel
  // API supplémentaire) : ils reprennent la logique des tuiles KPI du
  // « Tableau de bord LMD 2026 ».
  const indicateurs = useMemo(() => ({
    total: params.length,
    categories: visibleTabs.length,
    modifiables: params.filter(p => p.modifiable).length,
    critiques: params.filter(p => p.est_critique).length,
  }), [params, visibleTabs])

  const openEdit = (row) => {
    setHistory([])
    setModal({ type: 'edit', row })
    setForm({
      valeur: row.valeur,
      motif_modification: '',
      confirmation: false,
    })
  }

  const closeModal = () => {
    setModal(null)
    setForm({})
    setHistory([])
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!modal || modal.type !== 'edit') return
    const row = modal.row
    if (row.est_critique && !form.confirmation) {
      showToast('Cochez la confirmation pour ce paramètre critique.', 'error')
      return
    }
    setSaving(true)
    try {
      const payload = {
        valeur: form.valeur,
        motif_modification: form.motif_modification || '',
      }
      if (row.est_critique) payload.confirmation = true
      await api.patch(`/parametres/${row.id}/`, payload)
      showToast('Paramètre enregistré')
      closeModal()
      await load()
    } catch (err) {
      showToast(formatApiErrors(err.response?.data, { fallback: 'Erreur lors de l\'enregistrement' }), 'error')
    } finally {
      setSaving(false)
    }
  }

  const openHistory = async (row) => {
    setModal({ type: 'history', row })
    setHistoryLoading(true)
    try {
      const res = await api.get(`/parametres/${row.id}/historique/`)
      setHistory(res.data ?? [])
    } catch {
      showToast('Erreur de chargement de l\'historique.', 'error')
    } finally {
      setHistoryLoading(false)
    }
  }

  const canEdit = (row) => row.can_edit && row.modifiable
  const editing = modal?.type === 'edit' ? modal.row : null

  const currentTab = CATEGORIES.find(c => c.value === tab)

  return (
    <div className="page-container par-page">
      {/* ── Bandeau d'accueil (matière de la référence LMD2026) ── */}
      <div className="par-hero">
        <div className="par-hero-text">
          <span className="par-hero-badge">
            <i className="bi bi-sliders"></i>Administration
          </span>
          <h1 className="par-hero-title">
            <i className="bi bi-gear-fill"></i>
            Paramètres
          </h1>
          <p className="par-hero-sub">
            Paramètres fonctionnels de l’établissement. Les tarifs finance restent dans{' '}
            <Link to="/finance-parametrage">Paramétrage finance</Link>.
            Les emplois du temps sont générés dans <strong>app-ept-injs-lmd 2026</strong> puis importés dans Cours → Séances.
          </p>
        </div>
        <span className="par-hero-pill">
          {indicateurs.categories} catégorie{indicateurs.categories > 1 ? 's' : ''}
        </span>
      </div>

      {/* ── Tuiles KPI ── */}
      <div className="par-kpi-row">
        <div className="par-kpi">
          <div>
            <span className="par-kpi-label">Paramètres Actifs</span>
            <span className="par-kpi-value">{indicateurs.total}</span>
          </div>
          <div className="par-kpi-icon is-blue"><i className="bi bi-sliders"></i></div>
        </div>

        <div className="par-kpi">
          <div>
            <span className="par-kpi-label">Catégories</span>
            <span className="par-kpi-value is-slate">{indicateurs.categories}</span>
          </div>
          <div className="par-kpi-icon is-slate"><i className="bi bi-collection"></i></div>
        </div>

        <div className="par-kpi">
          <div>
            <span className="par-kpi-label">Modifiables</span>
            <span className="par-kpi-value is-green">{indicateurs.modifiables}</span>
          </div>
          <div className="par-kpi-icon is-green"><i className="bi bi-pencil-square"></i></div>
        </div>

        <div className="par-kpi">
          <div>
            <span className="par-kpi-label">Critiques</span>
            <span className={`par-kpi-value${indicateurs.critiques > 0 ? ' is-amber' : ' is-slate'}`}>
              {indicateurs.critiques}
            </span>
          </div>
          <div className="par-kpi-icon is-amber"><i className="bi bi-exclamation-triangle-fill"></i></div>
        </div>
      </div>

      {/* Onglets catégories — pilules de la référence */}
      <div className="par-tabs" role="tablist" aria-label="Catégories de paramètres">
        {visibleTabs.map(c => {
          const count = params.filter(p => p.categorie === c.value).length
          const active = tab === c.value
          return (
            <button
              key={c.value}
              type="button"
              role="tab"
              aria-selected={active}
              className={`par-tab${active ? ' is-active' : ''}`}
              onClick={() => setTab(c.value)}
            >
              <i className={`bi ${c.icon}`}></i>{c.label}
              <span className="par-tab-count">{count}</span>
            </button>
          )
        })}
      </div>

      {loading ? (
        <div className="par-loading">
          <div className="spinner"></div>
          <span>Chargement des paramètres…</span>
        </div>
      ) : (
        <div className="card par-panel">
          <div className="par-panel-head">
            <h2 className="par-panel-title">
              <i className={`bi ${currentTab?.icon ?? 'bi-gear'}`}></i>
              {currentTab?.label ?? 'Paramètres'}
            </h2>
            <div className="par-search">
              <i className="bi bi-search"></i>
              <input
                type="search"
                className="form-control form-control-sm"
                placeholder="Rechercher un paramètre…"
                aria-label="Rechercher un paramètre"
                value={query}
                onChange={e => setQuery(e.target.value)}
              />
            </div>
            <span className="par-count-pill">
              {filtered.length} entrée{filtered.length !== 1 ? 's' : ''}
            </span>
          </div>
          <div className="par-panel-body">
            {filtered.length === 0 ? (
              <div className="par-empty">
                <i className="bi bi-inbox"></i>
                <p>Aucun paramètre dans cette catégorie.</p>
              </div>
            ) : (
              <div className="par-table-wrap">
                <table className="table par-table">
                  <thead>
                    <tr>
                      <th>Libellé</th>
                      <th>Statut</th>
                      <th className="is-actions">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filtered.map(row => {
                      const editable = canEdit(row)
                      return (
                        <tr key={row.id} className={row.modifiable ? undefined : 'is-locked'}>
                          <td>
                            <div className="par-libelle">
                              {row.libelle}
                              {row.est_critique && (
                                <span className="par-badge-critique" title="Paramètre critique — confirmation requise">
                                  <i className="bi bi-exclamation-triangle-fill"></i>Critique
                                </span>
                              )}
                              {!row.modifiable && (
                                <span className="par-badge-verrou" title="Paramètre système non modifiable">
                                  <i className="bi bi-lock-fill"></i>Verrouillé
                                </span>
                              )}
                            </div>
                            {row.description && <div className="par-desc">{row.description}</div>}
                            <div>
                              <span className="par-value" title={displayValue(row)}>
                                {displayValue(row)}
                              </span>
                            </div>
                          </td>
                          <td>
                            <span className="badge badge-planifiee">Actif</span>
                          </td>
                          <td>
                            <div className="par-actions">
                              <button
                                type="button"
                                className="btn btn-outline-primary btn-sm par-icon-btn"
                                onClick={() => openEdit(row)}
                                disabled={!editable}
                                title={editable ? 'Modifier la valeur' : 'Non modifiable'}
                                aria-label={`Modifier ${row.libelle}`}
                              >
                                <i className="bi bi-pencil"></i>
                              </button>
                              <button
                                type="button"
                                className="btn btn-outline-secondary btn-sm par-icon-btn"
                                onClick={() => openHistory(row)}
                                title="Historique des modifications"
                                aria-label={`Historique de ${row.libelle}`}
                              >
                                <i className="bi bi-clock-history"></i>
                              </button>
                            </div>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}

      {editing && (
        <div className="modal-overlay" onClick={closeModal}>
          <div className="modal-content par-modal" style={{ maxWidth: 520 }} onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h5 className="modal-title">Modifier le paramètre</h5>
              <button type="button" className="btn-close" onClick={closeModal}>&times;</button>
            </div>
            <form onSubmit={handleSubmit}>
              <div className="modal-body">
                <p className="small text-muted mb-3">
                  <strong>{editing.libelle}</strong> <code>({editing.cle})</code>
                </p>
                <div className="mb-3">
                  <span className="par-old-label">Ancienne valeur</span>
                  <span className="par-old-value">{displayValue(editing)}</span>
                </div>
                <div className="form-group mb-3">
                  <label className="form-label">Nouvelle valeur</label>
                  <ParamValueInput
                    type={editing.type}
                    value={form.valeur ?? ''}
                    choices={parseChoices(editing.choices_json)}
                    onChange={val => setForm(prev => ({ ...prev, valeur: val }))}
                    disabled={saving || !editing.modifiable}
                  />
                </div>
                <div className="form-group mb-3">
                  <label className="form-label">
                    Motif de modification {editing.est_critique ? '(obligatoire)' : '(optionnel)'}
                  </label>
                  <textarea
                    className="form-control"
                    rows={2}
                    value={form.motif_modification ?? ''}
                    onChange={e => setForm(prev => ({ ...prev, motif_modification: e.target.value }))}
                    placeholder="Raison du changement..."
                    disabled={saving}
                    required={Boolean(editing.est_critique)}
                  />
                </div>
                {editing.est_critique && (
                  <div className="form-check">
                    <input
                      id="confirm-param"
                      type="checkbox"
                      className="form-check-input"
                      checked={Boolean(form.confirmation)}
                      onChange={e => setForm(prev => ({ ...prev, confirmation: e.target.checked }))}
                      disabled={saving}
                    />
                    <label className="form-check-label" htmlFor="confirm-param">
                      Je confirme le remplacement de <code>{displayValue(editing)}</code> par <code>{form.valeur || '—'}</code>
                    </label>
                  </div>
                )}
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-secondary" onClick={closeModal} disabled={saving}>Annuler</button>
                <button type="submit" className="btn btn-dfrc" disabled={saving || !editing.modifiable}>
                  {saving ? 'Enregistrement…' : 'Enregistrer'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {modal?.type === 'history' && (
        <div className="modal-overlay" onClick={closeModal}>
          <div className="modal-content par-modal par-modal-hist" style={{ maxWidth: 640 }} onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h5 className="modal-title">Historique — {modal.row.libelle}</h5>
              <button type="button" className="btn-close" onClick={closeModal}>&times;</button>
            </div>
            <div className="modal-body">
              {historyLoading ? (
                <div className="par-loading"><div className="spinner"></div></div>
              ) : history.length === 0 ? (
                <p className="text-muted mb-0">Aucune modification enregistrée.</p>
              ) : (
                <div className="par-table-wrap">
                  <table className="table table-sm par-table">
                    <thead>
                      <tr>
                        <th>Date</th>
                        <th>Utilisateur</th>
                        <th>Ancienne valeur</th>
                        <th>Nouvelle valeur</th>
                        <th>Motif</th>
                      </tr>
                    </thead>
                    <tbody>
                      {history.map(h => (
                        <tr key={h.id}>
                          <td className="small">{new Date(h.modifie_le).toLocaleString('fr-FR')}</td>
                          <td>{h.modifie_par_username ?? '—'}</td>
                          <td><code>{h.ancienne_valeur ?? '—'}</code></td>
                          <td><code>{h.nouvelle_valeur ?? '—'}</code></td>
                          <td className="small">{h.motif_modification || '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
            <div className="modal-footer">
              <button type="button" className="btn btn-secondary" onClick={closeModal}>Fermer</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
