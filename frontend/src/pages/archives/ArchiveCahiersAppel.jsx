import { useState, useEffect, useCallback } from 'react'
import api from '../../services/api'
import { useToast } from '../../context/ToastContext'
import { formatDate } from '../../utils/dates'
import ArchiveModuleBrowser from '../../components/archives/ArchiveModuleBrowser'
import '../../styles/archives.css'

const ACCENT = '#001a33'
const SET_VIDE = new Set()

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

/** Libellé de séance sans le suffixe « (archivée) » : tout le cahier est archivé. */
function sessionLabel(s) {
  const brut = (s.intitule || `Séance ${s.numero}`).replace(/\s*\((?:archivée?|archive)\)\s*$/i, '').trim()
  return brut || `Séance ${s.numero}`
}

function tauxClasse(taux) {
  if (taux >= 80) return 'archives-taux--bon'
  if (taux >= 50) return 'archives-taux--moyen'
  return 'archives-taux--faible'
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

  // Indicateurs calculés sur les données réelles du cahier
  const nbSeances = sessions.length
  const totalPresences = participants.reduce(
    (acc, p) => acc + sessions.filter(s => (presenceIndex[p.id] || SET_VIDE).has(s.id)).length,
    0,
  )
  const attendues = participants.length * nbSeances
  const tauxGlobal = attendues ? Math.round((totalPresences / attendues) * 100) : 0
  const presentsParSeance = sessions.map(s =>
    participants.filter(p => (presenceIndex[p.id] || SET_VIDE).has(s.id)).length,
  )
  const periode = nbSeances
    ? `${sessions[0].date ? formatDate(sessions[0].date) : '—'} → ${sessions[nbSeances - 1].date ? formatDate(sessions[nbSeances - 1].date) : '—'}`
    : null

  return (
    <div className="archives-cahier">
      <section className="archives-cahier-hero">
        <button type="button" className="archives-cahier-retour" onClick={onBack}>
          <i className="bi bi-arrow-left"></i>Retour aux modules
        </button>
        <div className="archives-cahier-hero-main">
          <span className="archives-cahier-icone"><i className="bi bi-journal-check"></i></span>
          <div className="archives-cahier-titres">
            <span className="archives-hero-badge"><i className="bi bi-archive"></i>Archives · Émargement</span>
            <h2>Cahier d'appel</h2>
            <p>
              <strong>{module.module}</strong> · {module.formation}
              {module.grade && <> · {module.grade}</>}{module.groupe && <> · {module.groupe}</>}
              {module.secretariat_nom && <> · {module.secretariat_nom}</>}
            </p>
          </div>
          <div className="archives-cahier-exports">
            <button type="button" className="archives-export archives-export--pdf" onClick={() => handleExport('pdf')} disabled={exporting === 'pdf'}>
              {exporting === 'pdf' ? <span className="spinner-border spinner-border-sm"></span> : <i className="bi bi-file-earmark-pdf"></i>}PDF
            </button>
            <button type="button" className="archives-export archives-export--excel" onClick={() => handleExport('excel')} disabled={exporting === 'excel'}>
              {exporting === 'excel' ? <span className="spinner-border spinner-border-sm"></span> : <i className="bi bi-file-earmark-excel"></i>}Excel
            </button>
          </div>
        </div>
        <div className="archives-cahier-kpis">
          <div className="archives-cahier-kpi">
            <i className="bi bi-people"></i>
            <div><strong>{participants.length}</strong><span>étudiant{participants.length !== 1 ? 's' : ''}</span></div>
          </div>
          <div className="archives-cahier-kpi">
            <i className="bi bi-calendar3-week"></i>
            <div><strong>{nbSeances}</strong><span>séance{nbSeances !== 1 ? 's' : ''}{periode ? ` · ${periode}` : ''}</span></div>
          </div>
          <div className="archives-cahier-kpi">
            <i className="bi bi-check2-square"></i>
            <div><strong>{totalPresences}/{attendues}</strong><span>présences émargées</span></div>
          </div>
          <div className="archives-cahier-kpi archives-cahier-kpi--taux">
            <div className="archives-cahier-taux-tete">
              <i className="bi bi-graph-up"></i>
              <div><strong>{tauxGlobal}%</strong><span>taux de présence global</span></div>
            </div>
            <div className="archives-cahier-jauge" role="progressbar" aria-valuenow={tauxGlobal} aria-valuemin={0} aria-valuemax={100} aria-label="Taux de présence global">
              <span style={{ width: `${tauxGlobal}%` }}></span>
            </div>
          </div>
        </div>
      </section>

      <div className="archives-cahier-toolbar">
        <label className="archives-cahier-recherche">
          <i className="bi bi-search"></i>
          <input
            className="form-control"
            placeholder="Rechercher un étudiant…"
            value={search}
            onChange={e => setSearch(e.target.value)}
            aria-label="Rechercher un étudiant"
          />
        </label>
        <span className="archives-cahier-compteur">
          {filtered.length} étudiant{filtered.length !== 1 ? 's' : ''} affiché{filtered.length !== 1 ? 's' : ''}
        </span>
        <div className="archives-cahier-legende">
          <span><span className="archives-presence archives-presence--oui"><i className="bi bi-check"></i></span>Présent</span>
          <span><span className="archives-presence--non">—</span>Absent</span>
        </div>
      </div>

      {loading ? (
        <div className="loading"><div className="spinner"></div></div>
      ) : participants.length === 0 ? (
        <div className="empty-state archives-cahier-vide">
          <i className="bi bi-people"></i>
          <p>Aucun étudiant inscrit à ce module.</p>
        </div>
      ) : sessions.length === 0 ? (
        <div className="empty-state archives-cahier-vide">
          <i className="bi bi-calendar-x"></i>
          <p>Aucune séance enregistrée pour ce module.</p>
        </div>
      ) : filtered.length === 0 ? (
        <div className="empty-state archives-cahier-vide">
          <i className="bi bi-search"></i>
          <p>Aucun étudiant ne correspond à « {search} ».</p>
        </div>
      ) : (
        <div className="archives-cahier-carte">
          <table className="archives-cahier-table">
            <thead>
              <tr>
                <th className="col-rang">#</th>
                <th className="col-etudiant">Étudiant</th>
                {sessions.map(s => (
                  <th key={s.id} className="col-seance" title={s.intitule || `Séance ${s.numero}`}>
                    <span className="seance-date">{s.date ? formatDate(s.date) : `S${s.numero}`}</span>
                    <span className="seance-libelle">{sessionLabel(s)}</span>
                  </th>
                ))}
                <th className="col-total">Présences</th>
                <th className="col-total">Taux</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((p, idx) => {
                const set = presenceIndex[p.id] || SET_VIDE
                const nbPres = sessions.filter(s => set.has(s.id)).length
                const taux = nbSeances ? Math.round((nbPres / nbSeances) * 100) : 0
                return (
                  <tr key={p.id} className="archives-cahier-ligne" style={{ animationDelay: `${Math.min(idx * 35, 350)}ms` }}>
                    <td className="col-rang">{idx + 1}</td>
                    <td className="col-etudiant">
                      <span className="etudiant-nom">{p.nom} {p.prenom}</span>
                      <span className="etudiant-matricule">{p.matricule}</span>
                    </td>
                    {sessions.map(s => {
                      const present = set.has(s.id)
                      return (
                        <td key={s.id} className="col-seance">
                          {present
                            ? <span className="archives-presence archives-presence--oui" title="Présent"><i className="bi bi-check"></i></span>
                            : <span className="archives-presence--non" title="Absent">—</span>}
                        </td>
                      )
                    })}
                    <td className="col-total"><span className="archives-presences-nb">{nbPres}/{nbSeances}</span></td>
                    <td className="col-total"><span className={`archives-taux ${tauxClasse(taux)}`}>{taux}%</span></td>
                  </tr>
                )
              })}
            </tbody>
            <tfoot>
              <tr>
                <td className="col-rang"></td>
                <td className="col-etudiant">Présents par séance</td>
                {presentsParSeance.map((n, i) => (
                  <td key={sessions[i].id} className="col-seance">{n}/{participants.length}</td>
                ))}
                <td className="col-total">{totalPresences}/{attendues}</td>
                <td className="col-total"><span className={`archives-taux ${tauxClasse(tauxGlobal)}`}>{tauxGlobal}%</span></td>
              </tr>
            </tfoot>
          </table>
        </div>
      )}
    </div>
  )
}

export default function ArchiveCahiersAppel() {
  return (
    <ArchiveModuleBrowser
      title="Cahiers d'appel"
      description="Consultez les registres de présence (émargement) archivés par module — le classement de référence des archives de la scolarité. Export PDF/Excel disponible."
      icon="bi-journal-check"
      accent={ACCENT}
      documentVerb="Voir le cahier d'appel"
      renderDocument={(module, onBack) => <CahierAppelDocument module={module} onBack={onBack} />}
    />
  )
}
