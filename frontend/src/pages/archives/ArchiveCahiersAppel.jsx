import { useState, useEffect, useCallback } from 'react'
import api from '../../services/api'
import { useToast } from '../../context/ToastContext'
import { formatDate } from '../../utils/dates'
import ArchiveModuleBrowser from '../../components/archives/ArchiveModuleBrowser'

const ACCENT = '#001a33'

function _downloadBlob(blob, fileName) {
  const url = window.URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = fileName
  document.body.appendChild(a)
  a.click()
  a.remove()
  window.URL.revokeObjectURL(url)
}

/** Vue cahier d'appel : grille d'émargement (auditeurs × séances) + exports. */
function CahierAppelDocument({ module, onBack }) {
  const { showToast } = useToast()
  const formationId = module.id
  const moduleId = module.module_id

  const [sessions, setSessions] = useState([])
  const [participants, setParticipants] = useState([])
  const [presences, setPresences] = useState([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [exporting, setExporting] = useState('')

  const fetchData = useCallback(async (signal) => {
    setLoading(true)
    try {
      const res = await api.get(`/formations/${formationId}/modules/${moduleId}/archives/cahier/`, signal ? { signal } : {})
      setSessions((res.data.sessions || []).slice().sort((a, b) =>
        (a.date || '').localeCompare(b.date || '') || (a.numero || 0) - (b.numero || 0)
      ))
      setParticipants(res.data.participants || [])
      setPresences(res.data.presences || [])
    } catch (err) {
      if (err?.name !== 'AbortError' && err?.code !== 'ERR_CANCELED' && err?.name !== 'CanceledError') {
        showToast('Erreur lors du chargement du cahier d\'appel.', 'error')
      }
    } finally {
      setLoading(false)
    }
  }, [formationId, moduleId, showToast])

  useEffect(() => {
    const ac = new AbortController()
    fetchData(ac.signal)
    return () => ac.abort()
  }, [fetchData])

  // Index présences participant → set de session_id
  const presenceIndex = {}
  presences.forEach(p => {
    if (p.type_personne === 'participant' && p.participant_id != null && p.session_id != null) {
      if (!presenceIndex[p.participant_id]) presenceIndex[p.participant_id] = new Set()
      presenceIndex[p.participant_id].add(p.session_id)
    }
  })

  const handleExport = async (type) => {
    setExporting(type)
    try {
      const { blob, fileName } = await api.getBlob(`/exports/module/${moduleId}/${type === 'pdf' ? 'pdf' : 'excel'}/`)
      const safe = (module.module || 'cahier_appel').replace(/[^a-z0-9]/gi, '_').toLowerCase()
      _downloadBlob(blob, fileName || `cahier_appel_${safe}.${type === 'pdf' ? 'pdf' : 'xlsx'}`)
    } catch (err) {
      showToast(err?.response?.data?.detail || `Erreur export ${type.toUpperCase()}.`, 'error')
    } finally {
      setExporting('')
    }
  }

  const filtered = participants.filter(p =>
    !search ||
    `${p.nom} ${p.prenom}`.toLowerCase().includes(search.toLowerCase()) ||
    (p.matricule || '').toLowerCase().includes(search.toLowerCase())
  )

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '0.75rem', flexWrap: 'wrap', marginBottom: '1.25rem' }}>
        <div>
          <button className="btn btn-outline-secondary btn-sm" onClick={onBack} style={{ marginBottom: '0.6rem' }}>
            <i className="bi bi-arrow-left me-1"></i>Retour aux modules
          </button>
          <h2 style={{ margin: 0, fontWeight: 700 }}>
            <i className="bi bi-journal-check me-2" style={{ color: ACCENT }}></i>Cahier d'appel
          </h2>
          <p style={{ margin: '0.25rem 0 0', color: 'var(--text-muted)', fontSize: '0.9rem' }}>
            <strong>{module.module}</strong> · {module.formation}
            {module.grade && <> · {module.grade}</>}{module.groupe && <> · {module.groupe}</>}
            {module.secretariat_nom && <> · {module.secretariat_nom}</>}
          </p>
          <p style={{ margin: '0.25rem 0 0', color: 'var(--text-muted)', fontSize: '0.82rem' }}>
            {participants.length} étudiant{participants.length !== 1 ? 's' : ''} · {sessions.length} séance{sessions.length !== 1 ? 's' : ''}
          </p>
        </div>
        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
          <button className="btn btn-outline-danger btn-sm" onClick={() => handleExport('pdf')} disabled={exporting === 'pdf'}>
            {exporting === 'pdf' ? <span className="spinner-border spinner-border-sm me-1"></span> : <i className="bi bi-file-earmark-pdf me-1"></i>}PDF
          </button>
          <button className="btn btn-outline-success btn-sm" onClick={() => handleExport('excel')} disabled={exporting === 'excel'}>
            {exporting === 'excel' ? <span className="spinner-border spinner-border-sm me-1"></span> : <i className="bi bi-file-earmark-excel me-1"></i>}Excel
          </button>
        </div>
      </div>

      <div style={{ marginBottom: '1rem' }}>
        <input
          className="form-control"
          placeholder="Rechercher un étudiant…"
          value={search}
          onChange={e => setSearch(e.target.value)}
          style={{ maxWidth: 360 }}
        />
      </div>

      {loading ? (
        <div className="loading"><div className="spinner"></div></div>
      ) : participants.length === 0 ? (
        <div className="empty-state">
          <i className="bi bi-people" style={{ fontSize: '3rem', color: 'var(--text-muted)' }}></i>
          <p>Aucun étudiant inscrit à ce module.</p>
        </div>
      ) : sessions.length === 0 ? (
        <div className="empty-state">
          <i className="bi bi-calendar-x" style={{ fontSize: '3rem', color: 'var(--text-muted)' }}></i>
          <p>Aucune séance enregistrée pour ce module.</p>
        </div>
      ) : (
        <div className="card" style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.84rem' }}>
            <thead>
              <tr style={{ borderBottom: '2px solid var(--border)', background: 'var(--bg-secondary, #f9fafb)' }}>
                <th style={{ ...thStyle('left'), position: 'sticky', left: 0, background: 'var(--bg-secondary, #f9fafb)', zIndex: 1 }}>#</th>
                <th style={{ ...thStyle('left'), position: 'sticky', left: 36, background: 'var(--bg-secondary, #f9fafb)', zIndex: 1 }}>Étudiant</th>
                {sessions.map(s => (
                  <th key={s.id} style={{ ...thStyle('center'), minWidth: 64 }} title={s.intitule || `Séance ${s.numero}`}>
                    <div style={{ fontSize: '0.72rem' }}>{s.date ? formatDate(s.date) : `S${s.numero}`}</div>
                    <div style={{ fontSize: '0.66rem', color: 'var(--text-muted)', fontWeight: 500 }}>{s.intitule || `Séance ${s.numero}`}</div>
                  </th>
                ))}
                <th style={thStyle('center')}>Présences</th>
                <th style={thStyle('center')}>Taux</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((p, idx) => {
                const set = presenceIndex[p.id] || new Set()
                const nbPres = sessions.filter(s => set.has(s.id)).length
                const taux = sessions.length ? Math.round((nbPres / sessions.length) * 100) : 0
                return (
                  <tr key={p.id} style={{ borderBottom: '1px solid var(--border)', background: idx % 2 === 0 ? 'transparent' : 'var(--bg-secondary, #fafafa)' }}>
                    <td style={{ ...tdStyle, position: 'sticky', left: 0, background: idx % 2 === 0 ? '#fff' : 'var(--bg-secondary, #fafafa)' }}>{idx + 1}</td>
                    <td style={{ ...tdStyle, fontWeight: 600, whiteSpace: 'nowrap', position: 'sticky', left: 36, background: idx % 2 === 0 ? '#fff' : 'var(--bg-secondary, #fafafa)' }}>
                      {p.nom} {p.prenom}
                      <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', fontWeight: 400 }}>{p.matricule}</div>
                    </td>
                    {sessions.map(s => {
                      const present = set.has(s.id)
                      return (
                        <td key={s.id} style={{ ...tdStyle, textAlign: 'center' }}>
                          {present
                            ? <i className="bi bi-check-circle-fill" style={{ color: '#125a99' }} title="Présent"></i>
                            : <span style={{ color: '#cfcfcf' }} title="Absent">—</span>}
                        </td>
                      )
                    })}
                    <td style={{ ...tdStyle, textAlign: 'center', fontWeight: 600 }}>{nbPres}/{sessions.length}</td>
                    <td style={{ ...tdStyle, textAlign: 'center', fontWeight: 700, color: taux >= 80 ? '#125a99' : (taux >= 50 ? '#f5b417' : '#b71c1c') }}>{taux}%</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

const thStyle = (align) => ({ padding: '0.65rem 0.5rem', textAlign: align, fontWeight: 700, whiteSpace: 'nowrap' })
const tdStyle = { padding: '0.55rem 0.5rem' }

export default function ArchiveCahiersAppel() {
  return (
    <ArchiveModuleBrowser
      title="Cahiers d'appel"
      description="Consultez les registres de présence (émargement) archivés par module, à l'image du classement « CAHIERS D'APPEL » des archives. Export PDF/Excel disponible."
      icon="bi-journal-check"
      accent={ACCENT}
      documentVerb="Voir le cahier d'appel"
      renderDocument={(module, onBack) => <CahierAppelDocument module={module} onBack={onBack} />}
    />
  )
}
