import { useState, useEffect, useCallback } from 'react'
import api from '../../services/api'
import { useToast } from '../../context/ToastContext'
import ArchiveModuleBrowser from '../../components/archives/ArchiveModuleBrowser'

const ACCENT = '#1565c0'

const MENTION_LABELS = {
  TRES_BIEN: 'Très bien', BIEN: 'Bien', ASSEZ_BIEN: 'Assez bien',
  PASSABLE: 'Passable', INSUFFISANT: 'Insuffisant', '': '—',
}
const MENTION_COLORS = {
  TRES_BIEN: { background: '#e8eff5', color: '#093f70' },
  BIEN: { background: '#e3f2fd', color: '#0d47a1' },
  ASSEZ_BIEN: { background: '#e8eaf6', color: '#283593' },
  PASSABLE: { background: '#fffae1', color: '#f5b417' },
  INSUFFISANT: { background: '#ffebee', color: '#b71c1c' },
  '': { background: '#f5f5f5', color: '#9e9e9e' },
}

function MentionBadge({ mention }) {
  const style = MENTION_COLORS[mention] || MENTION_COLORS['']
  return (
    <span style={{ ...style, fontSize: '0.72rem', fontWeight: 700, padding: '2px 9px', borderRadius: 20, whiteSpace: 'nowrap' }}>
      {MENTION_LABELS[mention] || '—'}
    </span>
  )
}

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

/** Vue lecture seule d'une liste de notes (modèle « LISTE DE NOTE » des archives). */
function ListeNoteDocument({ module, onBack }) {
  const { showToast } = useToast()
  const formationId = module.id
  const moduleId = module.module_id
  const [colonnes, setColonnes] = useState([])
  const [rows, setRows] = useState([])
  const [criteres, setCriteres] = useState({ seuil_admission: 12, taux_presence_min: 80 })
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [printing, setPrinting] = useState(null)

  const fetchData = useCallback(async (signal) => {
    setLoading(true)
    try {
      const res = await api.get(`/formations/${formationId}/modules/${moduleId}/notes/`, signal ? { signal } : {})
      setColonnes(res.data.colonnes || [])
      setRows(res.data.rows || [])
      if (res.data.criteres) setCriteres(res.data.criteres)
    } catch (err) {
      if (err?.name !== 'AbortError' && err?.code !== 'ERR_CANCELED' && err?.name !== 'CanceledError') {
        showToast('Erreur lors du chargement des notes.', 'error')
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

  const handlePrintFiche = async (participant = null) => {
    const key = participant ? `p-${participant.participant_id}` : 'module'
    const path = participant
      ? `/formations/${formationId}/modules/${moduleId}/notes/fiche/${participant.participant_id}/pdf/`
      : `/formations/${formationId}/modules/${moduleId}/notes/fiche/pdf/`
    const fallback = participant
      ? `fiche_notes_${participant.nom}_${participant.prenom}.pdf`.replace(/\s+/g, '_')
      : `fiche_notes_module_${moduleId}.pdf`

    setPrinting(key)
    try {
      const { blob, fileName } = await api.getBlob(path)
      downloadBlob(blob, fileName || fallback)
    } catch (err) {
      showToast(err?.response?.data?.detail || 'Erreur lors de la génération de la fiche', 'error')
    } finally {
      setPrinting(null)
    }
  }

  const filtered = rows.filter(n =>
    !search ||
    `${n.nom} ${n.prenom}`.toLowerCase().includes(search.toLowerCase()) ||
    (n.matricule || '').toLowerCase().includes(search.toLowerCase()) ||
    (n.grade || '').toLowerCase().includes(search.toLowerCase())
  )

  const nbSaisies = rows.filter(n => Object.values(n.notes || {}).some(c => c?.note != null)).length

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '0.75rem', flexWrap: 'wrap', marginBottom: '1.25rem' }}>
        <div>
          <button className="btn btn-outline-secondary btn-sm" onClick={onBack} style={{ marginBottom: '0.6rem' }}>
            <i className="bi bi-arrow-left me-1"></i>Retour aux modules
          </button>
          <h2 style={{ margin: 0, fontWeight: 700 }}>
            <i className="bi bi-card-checklist me-2" style={{ color: ACCENT }}></i>Liste de notes
          </h2>
          <p style={{ margin: '0.25rem 0 0', color: 'var(--text-muted)', fontSize: '0.9rem' }}>
            <strong>{module.module}</strong> · {module.formation}
            {module.grade && <> · {module.grade}</>}{module.groupe && <> · {module.groupe}</>}
            {module.secretariat_nom && <> · {module.secretariat_nom}</>}
          </p>
          <p style={{ margin: '0.25rem 0 0', color: 'var(--text-muted)', fontSize: '0.82rem' }}>
            {rows.length} étudiant{rows.length !== 1 ? 's' : ''} · {nbSaisies} noté{nbSaisies !== 1 ? 's' : ''} ·
            Admis si moyenne ≥ <strong>{criteres.seuil_admission}/20</strong> et présence au module ≥ <strong>{criteres.taux_presence_min}%</strong>
          </p>
        </div>
        <button
          className="btn btn-outline-secondary btn-sm"
          onClick={() => handlePrintFiche()}
          disabled={printing !== null || rows.length === 0}
          title="Imprimer la fiche de notes du module (tous les étudiants)"
        >
          {printing === 'module'
            ? <><span className="spinner-border spinner-border-sm me-1"></span>Génération…</>
            : <><i className="bi bi-printer me-1"></i>Imprimer la fiche</>}
        </button>
      </div>

      <div style={{ marginBottom: '1rem' }}>
        <input
          className="form-control"
          placeholder="Rechercher par nom, matricule, grade…"
          value={search}
          onChange={e => setSearch(e.target.value)}
          style={{ maxWidth: 360 }}
        />
      </div>

      {loading ? (
        <div className="loading"><div className="spinner"></div></div>
      ) : rows.length === 0 ? (
        <div className="empty-state">
          <i className="bi bi-people" style={{ fontSize: '3rem', color: 'var(--text-muted)' }}></i>
          <p>Aucun étudiant inscrit à ce module.</p>
        </div>
      ) : (
        <div className="card" style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.875rem' }}>
            <thead>
              <tr style={{ borderBottom: '2px solid var(--border)', background: 'var(--bg-secondary, #f9fafb)' }}>
                <th style={thStyle('left')}>#</th>
                <th style={thStyle('left')}>N° inscription</th>
                <th style={thStyle('left')}>Nom & Prénoms</th>
                <th style={thStyle('left')}>Grade</th>
                {colonnes.map(c => (
                  <th key={c.id} style={thStyle('center')}>
                    {c.libelle}<div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', fontWeight: 500 }}>/ {c.note_max}</div>
                  </th>
                ))}
                <th style={thStyle('center')}>Moy. /20</th>
                <th style={thStyle('center')}>Mention</th>
                <th style={thStyle('center')}>Présence au module</th>
                <th style={thStyle('center')}>Admis</th>
                <th style={thStyle('center')}>Fiche</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((n, idx) => {
                const moyNum = n.moyenne != null && n.moyenne !== '' ? parseFloat(n.moyenne) : null
                const taux = n.taux_presence
                return (
                  <tr key={n.participant_id} style={{ borderBottom: '1px solid var(--border)', background: idx % 2 === 0 ? 'transparent' : 'var(--bg-secondary, #fafafa)' }}>
                    <td style={tdStyle}>{idx + 1}</td>
                    <td style={{ ...tdStyle, fontSize: '0.78rem', color: 'var(--text-muted)' }}>{n.matricule || '—'}</td>
                    <td style={{ ...tdStyle, fontWeight: 600, whiteSpace: 'nowrap' }}>{n.nom} {n.prenom}</td>
                    <td style={tdStyle}>
                      {n.grade && <span style={{ fontSize: '0.78rem', background: '#e8eaf6', color: '#283593', padding: '2px 8px', borderRadius: 20, fontWeight: 600 }}>{n.grade}</span>}
                    </td>
                    {colonnes.map(c => {
                      const cell = n.notes?.[String(c.id)]
                      return (
                        <td key={c.id} style={{ ...tdStyle, textAlign: 'center', fontWeight: 600 }}>
                          {cell?.note != null ? cell.note : '—'}
                        </td>
                      )
                    })}
                    <td style={{ ...tdStyle, textAlign: 'center', fontWeight: 700, color: moyNum != null ? (moyNum >= criteres.seuil_admission ? '#125a99' : '#b71c1c') : 'var(--text-muted)' }}>
                      {moyNum != null && !isNaN(moyNum) ? moyNum.toFixed(2) : '—'}
                    </td>
                    <td style={{ ...tdStyle, textAlign: 'center' }}><MentionBadge mention={n.mention || ''} /></td>
                    <td style={{ ...tdStyle, textAlign: 'center' }}>
                      {taux != null ? (
                        <span style={{ fontWeight: 600, color: taux >= criteres.taux_presence_min ? '#125a99' : '#b71c1c' }}>{taux}%</span>
                      ) : '—'}
                    </td>
                    <td style={{ ...tdStyle, textAlign: 'center' }}>
                      {moyNum != null && taux != null ? (
                        n.admissible
                          ? <span style={{ color: '#125a99', fontWeight: 700 }}><i className="bi bi-check-circle-fill"></i> Oui</span>
                          : <span style={{ color: '#b71c1c', fontWeight: 600 }}><i className="bi bi-x-circle"></i> Non</span>
                      ) : <span style={{ color: 'var(--text-muted)' }}>—</span>}
                    </td>
                    <td style={{ ...tdStyle, textAlign: 'center' }}>
                      <button
                        type="button"
                        className="btn btn-sm btn-outline-secondary"
                        style={{ padding: '2px 8px' }}
                        onClick={() => handlePrintFiche(n)}
                        disabled={printing !== null}
                        title={`Imprimer la fiche de notes de ${n.nom} ${n.prenom}`}
                      >
                        {printing === `p-${n.participant_id}`
                          ? <span className="spinner-border spinner-border-sm"></span>
                          : <i className="bi bi-printer"></i>}
                      </button>
                    </td>
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

const thStyle = (align) => ({ padding: '0.7rem 0.6rem', textAlign: align, fontWeight: 700, whiteSpace: 'nowrap' })
const tdStyle = { padding: '0.6rem' }

export default function ArchiveListesNotes() {
  return (
    <ArchiveModuleBrowser
      title="Listes de note"
      description="Consultez les relevés de notes archivés par module (catégorie, grade, groupe), à l'image du classement « LISTES DE NOTE » des archives."
      icon="bi-card-checklist"
      accent={ACCENT}
      documentVerb="Voir les notes"
      renderDocument={(module, onBack) => <ListeNoteDocument module={module} onBack={onBack} />}
    />
  )
}
