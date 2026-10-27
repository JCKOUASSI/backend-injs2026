import { useState, useEffect, useCallback } from 'react'
import api from '../../services/api'
import { useReferentiels } from '../../hooks/useReferentiels'
import { useDebounce } from '../../hooks/useDebounce'
import { formatDate } from '../../utils/dates'
import { parsePaginatedResponse } from '../../utils/paginatedResponse'
import { useAuth } from '../../context/AuthContext'
import { useToast } from '../../context/ToastContext'
import { canArchiveModuleFromUser } from '../../utils/roles'
import ConfirmModal from '../ConfirmModal'
import Pagination from '../Pagination'

const STATUT_LABELS = {
  PLANIFIEE: 'Planifiée',
  EN_COURS: 'En cours',
  SUSPENDUE: 'Suspendue',
  TERMINEE: 'Terminée',
}

const STATUT_COLORS = {
  PLANIFIEE: { background: '#e3f2fd', color: '#0d47a1' },
  EN_COURS: { background: '#fffae1', color: '#f5b417' },
  SUSPENDUE: { background: '#fce4ec', color: '#ad1457' },
  TERMINEE: { background: '#e8eff5', color: '#093f70' },
}

/**
 * Navigateur de modules pour les écrans archiviste.
 * Reproduit la logique de classement (Secrétariat / Catégorie-Grade / Groupe → Module),
 * puis délègue l'affichage du document via `renderDocument(module, onBack)`.
 */
export default function ArchiveModuleBrowser({
  title,
  description,
  icon = 'bi-folder2-open',
  accent = '#001a33',
  documentVerb = 'Consulter',
  renderDocument,
}) {
  const { data: refs } = useReferentiels()
  const { user } = useAuth()
  const { showToast } = useToast()
  const canUnarchive = canArchiveModuleFromUser(user)
  const [filters, setFilters] = useState({
    search: '', formation_id: '', annee: '', secretariat_type: '', grade: '', groupe: '', vague: '', statut: '',
  })
  const debouncedSearch = useDebounce(filters.search)

  const [modules, setModules] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [page, setPage] = useState(1)
  const [totalPages, setTotalPages] = useState(1)
  const [total, setTotal] = useState(0)

  const [selected, setSelected] = useState(null)
  const [unarchiveTarget, setUnarchiveTarget] = useState(null)

  const loadModules = useCallback(async (signal) => {
    setLoading(true)
    setError('')
    try {
      const params = new URLSearchParams({ page: String(page), page_size: '24' })
      if (debouncedSearch) params.set('search', debouncedSearch)
      if (filters.formation_id) params.set('formation_id', filters.formation_id)
      if (filters.annee) params.set('annee', filters.annee)
      if (filters.secretariat_type) params.set('secretariat_type', filters.secretariat_type)
      if (filters.grade) params.set('grade', filters.grade)
      if (filters.groupe) params.set('groupe', filters.groupe)
      if (filters.vague) params.set('vague', filters.vague)
      if (filters.statut) params.set('statut', filters.statut)
      const res = await api.get(`/formations/archives/modules/?${params}`, signal ? { signal } : {})
      const { results, count, totalPages: pages } = parsePaginatedResponse(res.data, 24)
      setModules(results)
      setTotal(count)
      setTotalPages(pages)
    } catch (err) {
      if (err?.name !== 'AbortError' && err?.code !== 'ERR_CANCELED' && err?.name !== 'CanceledError') {
        setError('Erreur lors du chargement des modules archivés.')
      }
    } finally {
      setLoading(false)
    }
  }, [page, debouncedSearch, filters.formation_id, filters.annee, filters.secretariat_type, filters.grade, filters.groupe, filters.vague, filters.statut])

  const confirmUnarchive = async () => {
    const m = unarchiveTarget
    if (!m) return
    setUnarchiveTarget(null)
    try {
      await api.post(`/formations/${m.id}/modules/${m.module_id}/unarchive/`)
      showToast('Module désarchivé — de nouveau visible dans les listes opérationnelles')
      loadModules()
    } catch (err) {
      showToast(err.response?.data?.detail || 'Erreur lors du désarchivage', 'error')
    }
  }

  useEffect(() => {
    const ac = new AbortController()
    loadModules(ac.signal)
    return () => ac.abort()
  }, [loadModules])

  const updateFilter = (key, value) => {
    setPage(1)
    setFilters(f => ({ ...f, [key]: value }))
  }
  const resetFilters = () => {
    setPage(1)
    setFilters({ search: '', formation_id: '', annee: '', secretariat_type: '', grade: '', groupe: '', vague: '', statut: '' })
  }

  useEffect(() => { setPage(1) }, [debouncedSearch])

  const cycles = refs?.formations_reelles || []
  const annees = refs?.annees || []
  const types = refs?.types_secretariat || []
  const grades = refs?.grades_modules || refs?.grades || []
  const groupes = refs?.groupes || []
  const vagues = refs?.vagues || []

  // ── Vue document : un module est sélectionné ──
  if (selected) {
    return renderDocument(selected, () => setSelected(null))
  }

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: '1rem', marginBottom: '1.25rem', flexWrap: 'wrap' }}>
        <div style={{
          width: 52, height: 52, borderRadius: 14, flexShrink: 0,
          background: `${accent}1a`, color: accent,
          display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '1.5rem',
        }}>
          <i className={`bi ${icon}`}></i>
        </div>
        <div style={{ flex: 1, minWidth: 220 }}>
          <h2 style={{ margin: 0, fontWeight: 700 }}>{title}</h2>
          <p style={{ margin: '0.25rem 0 0', color: 'var(--text-muted)', fontSize: '0.9rem' }}>{description}</p>
        </div>
      </div>

      {/* Filtres */}
      <div className="card" style={{ padding: '1rem', marginBottom: '1.25rem', display: 'flex', gap: '0.75rem', flexWrap: 'wrap', alignItems: 'flex-end' }}>
        <div style={{ flex: '2 1 240px' }}>
          <label className="form-label" style={{ fontSize: '0.78rem', fontWeight: 600 }}>Rechercher</label>
          <input
            className="form-control form-control-sm"
            placeholder="Module, formation…"
            value={filters.search}
            onChange={e => updateFilter('search', e.target.value)}
          />
        </div>
        <div style={{ flex: '1 1 160px' }}>
          <label className="form-label" style={{ fontSize: '0.78rem', fontWeight: 600 }}>Cycle (formation)</label>
          <select className="form-select form-select-sm" value={filters.formation_id} onChange={e => updateFilter('formation_id', e.target.value)}>
            <option value="">Tous</option>
            {cycles.map(c => <option key={c.id} value={c.id}>{c.formation}</option>)}
          </select>
        </div>
        <div style={{ flex: '1 1 100px' }}>
          <label className="form-label" style={{ fontSize: '0.78rem', fontWeight: 600 }}>Année</label>
          <select className="form-select form-select-sm" value={filters.annee} onChange={e => updateFilter('annee', e.target.value)}>
            <option value="">Toutes</option>
            {annees.map(a => <option key={a} value={a}>{a}</option>)}
          </select>
        </div>
        <div style={{ flex: '1 1 150px' }}>
          <label className="form-label" style={{ fontSize: '0.78rem', fontWeight: 600 }}>Catégorie (secrétariat)</label>
          <select className="form-select form-select-sm" value={filters.secretariat_type} onChange={e => updateFilter('secretariat_type', e.target.value)}>
            <option value="">Toutes</option>
            {types.map(t => <option key={t.id} value={t.id}>{t.libelle}</option>)}
          </select>
        </div>
        <div style={{ flex: '1 1 120px' }}>
          <label className="form-label" style={{ fontSize: '0.78rem', fontWeight: 600 }}>Grade</label>
          <select className="form-select form-select-sm" value={filters.grade} onChange={e => updateFilter('grade', e.target.value)}>
            <option value="">Tous</option>
            {grades.map(g => <option key={g.id ?? g.libelle ?? g} value={g.libelle ?? g}>{g.libelle ?? g}</option>)}
          </select>
        </div>
        <div style={{ flex: '1 1 120px' }}>
          <label className="form-label" style={{ fontSize: '0.78rem', fontWeight: 600 }}>Groupe</label>
          <select className="form-select form-select-sm" value={filters.groupe} onChange={e => updateFilter('groupe', e.target.value)}>
            <option value="">Tous</option>
            {groupes.map(g => <option key={g.id ?? g.libelle ?? g} value={g.libelle ?? g}>{g.libelle ?? g}</option>)}
          </select>
        </div>
        <div style={{ flex: '1 1 120px' }}>
          <label className="form-label" style={{ fontSize: '0.78rem', fontWeight: 600 }}>Vague</label>
          <select className="form-select form-select-sm" value={filters.vague} onChange={e => updateFilter('vague', e.target.value)}>
            <option value="">Toutes</option>
            {vagues.map(v => <option key={v.id ?? v.libelle ?? v} value={v.libelle ?? v}>{v.libelle ?? v}</option>)}
          </select>
        </div>
        <div style={{ flex: '1 1 120px' }}>
          <label className="form-label" style={{ fontSize: '0.78rem', fontWeight: 600 }}>Statut</label>
          <select className="form-select form-select-sm" value={filters.statut} onChange={e => updateFilter('statut', e.target.value)}>
            <option value="">Tous</option>
            {Object.entries(STATUT_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </div>
        <button className="btn btn-outline-secondary btn-sm" onClick={resetFilters} title="Réinitialiser les filtres">
          <i className="bi bi-arrow-counterclockwise"></i>
        </button>
      </div>

      {loading ? (
        <div className="loading"><div className="spinner"></div></div>
      ) : error ? (
        <div className="empty-state">
          <i className="bi bi-exclamation-triangle" style={{ fontSize: '2.5rem', color: '#e53935' }}></i>
          <p>{error}</p>
        </div>
      ) : modules.length === 0 ? (
        <div className="empty-state" style={{ maxWidth: 520, margin: '0 auto', textAlign: 'center' }}>
          <i className="bi bi-inbox" style={{ fontSize: '3rem', color: 'var(--text-muted)' }}></i>
          <p style={{ fontWeight: 600, marginTop: '1rem' }}>Aucun module archivé pour le moment</p>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem', marginBottom: 0 }}>
            Les documents n'apparaissent ici qu'après archivage par le secrétariat ou la direction
            (bouton <strong>Archiver</strong> sur la page Modules).
            Tant qu'aucun module n'a été archivé, cet espace reste vide.
          </p>
        </div>
      ) : (
        <>
          <div style={{ marginBottom: '0.75rem', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
            {total} module{total !== 1 ? 's' : ''} archivé{total !== 1 ? 's' : ''}
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: '1rem' }}>
            {modules.map(m => {
              const statutStyle = STATUT_COLORS[m.statut] || STATUT_COLORS.PLANIFIEE
              return (
                <div
                  key={m.module_id}
                  className="card"
                  style={{ padding: '1rem', cursor: 'pointer', display: 'flex', flexDirection: 'column', gap: '0.6rem', transition: 'box-shadow .15s, transform .15s' }}
                  onClick={() => setSelected(m)}
                  onMouseEnter={e => { e.currentTarget.style.boxShadow = '0 6px 22px rgba(0,0,0,0.10)'; e.currentTarget.style.transform = 'translateY(-2px)' }}
                  onMouseLeave={e => { e.currentTarget.style.boxShadow = ''; e.currentTarget.style.transform = '' }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '0.5rem' }}>
                    <h3 style={{ margin: 0, fontSize: '1rem', fontWeight: 700, lineHeight: 1.3 }}>{m.module}</h3>
                    <span style={{ ...statutStyle, fontSize: '0.68rem', fontWeight: 700, padding: '2px 8px', borderRadius: 20, whiteSpace: 'nowrap' }}>
                      {STATUT_LABELS[m.statut] || m.statut}
                    </span>
                  </div>
                  <div style={{ fontSize: '0.82rem', color: 'var(--text-muted)' }}>
                    <i className="bi bi-mortarboard me-1"></i>{m.formation}
                  </div>
                  <div style={{ display: 'flex', gap: '0.4rem', flexWrap: 'wrap' }}>
                    {m.grade && <span style={badgeStyle('#e8eaf6', '#283593')}>{m.grade}</span>}
                    {m.groupe && <span style={badgeStyle('#e0f2f1', '#082961')}>{m.groupe}</span>}
                    {m.vague && <span style={badgeStyle('#fff8e0', '#e69700')}>{m.vague}</span>}
                    {m.secretariat_nom && <span style={badgeStyle('#f3e5f5', '#6a1b9a')}><i className="bi bi-building me-1"></i>{m.secretariat_nom}</span>}
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '0.78rem', color: 'var(--text-muted)', marginTop: '0.2rem' }}>
                    <span><i className="bi bi-people me-1"></i>{m.nb_participants ?? 0} étudiant{(m.nb_participants ?? 0) !== 1 ? 's' : ''}</span>
                    {(m.date_debut || m.date_fin) && (
                      <span><i className="bi bi-calendar3 me-1"></i>{m.date_debut ? formatDate(m.date_debut) : '?'}{m.date_fin ? ` → ${formatDate(m.date_fin)}` : ''}</span>
                    )}
                  </div>
                  <button
                    className="btn btn-sm w-100"
                    style={{ marginTop: '0.3rem', background: accent, color: '#fff', fontWeight: 600 }}
                    onClick={(e) => { e.stopPropagation(); setSelected(m) }}
                  >
                    <i className="bi bi-eye me-1"></i>{documentVerb}
                  </button>
                  {canUnarchive && (
                    <button
                      className="btn btn-sm btn-outline-secondary w-100"
                      style={{ marginTop: '0.35rem', fontWeight: 600 }}
                      onClick={(e) => { e.stopPropagation(); setUnarchiveTarget(m) }}
                    >
                      <i className="bi bi-box-arrow-up me-1"></i>Désarchiver
                    </button>
                  )}
                </div>
              )
            })}
          </div>
          {totalPages > 1 && (
            <div style={{ marginTop: '1.5rem' }}>
              <Pagination page={page} totalPages={totalPages} onPageChange={setPage} />
            </div>
          )}
        </>
      )}

      {unarchiveTarget && (
        <ConfirmModal
          message={`Désarchiver le module « ${unarchiveTarget.module} » ?`}
          detail="Le module réapparaîtra dans les listes opérationnelles (Modules, secrétariat, encadrants, statistiques)."
          confirmLabel="Désarchiver"
          variant="primary"
          onConfirm={confirmUnarchive}
          onCancel={() => setUnarchiveTarget(null)}
        />
      )}
    </div>
  )
}

function badgeStyle(bg, color) {
  return { background: bg, color, fontSize: '0.72rem', fontWeight: 600, padding: '2px 8px', borderRadius: 20, whiteSpace: 'nowrap' }
}
