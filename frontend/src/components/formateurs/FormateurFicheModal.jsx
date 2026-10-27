import { useEffect, useState, useCallback } from 'react'
import api from '../../services/api'
import { useToast } from '../../context/ToastContext'
import { FinanceStatsGrid, fmtDuration } from '../FinanceStatsGrid'
import { FinanceSessionsByGroupeTable } from '../finance/FinanceSessionsByGroupe'

const TABS = [
  { id: 'statistiques', label: 'Statistiques', icon: 'bi-graph-up' },
  { id: 'identite', label: 'Identité', icon: 'bi-person-badge' },
  { id: 'modules', label: 'Modules', icon: 'bi-journal-bookmark' },
  { id: 'notes', label: 'Notes', icon: 'bi-pencil-square' },
  { id: 'seances', label: 'Séances', icon: 'bi-clock-history' },
]

const STATUT_LABELS = {
  PLANIFIEE: 'Planifiée', EN_COURS: 'En cours', TERMINEE: 'Terminée', SUSPENDUE: 'Suspendue',
}

const fmtDate = (v) => {
  if (!v) return '-'
  const d = new Date(v)
  return Number.isNaN(d.getTime()) ? '-' : d.toLocaleDateString('fr-FR')
}

/**
 * Fiche formateur à onglets (consultation, sans données financières).
 * Onglets : Statistiques · Identité · Modules · Notes (observations) · Séances.
 * Données chargées via le rapport formateur (toutes périodes), montants masqués.
 */
export default function FormateurFicheModal({
  formateur,
  onClose,
  canViewSensitive = false,
  onExport,
  exporting = '',
}) {
  const { showToast } = useToast()
  const [tab, setTab] = useState('statistiques')
  const [detail, setDetail] = useState(null)
  const [loading, setLoading] = useState(true)

  const load = useCallback(async (signal) => {
    if (!formateur?.id) return
    setLoading(true)
    try {
      const res = await api.get(
        `/formations/formateurs/finance-report/?formateur_id=${formateur.id}&preset=tout`,
        signal ? { signal } : {},
      )
      const rows = Array.isArray(res.data) ? res.data : (res.data.results || [])
      setDetail(rows[0] || { ...formateur })
    } catch (err) {
      if (err?.name !== 'AbortError' && err?.code !== 'ERR_CANCELED' && err?.name !== 'CanceledError') {
        // Repli : afficher au moins les infos de base de la ligne
        setDetail({ ...formateur })
        showToast('Détail complet indisponible, affichage des infos de base.', 'error')
      }
    } finally {
      setLoading(false)
    }
  }, [formateur, showToast])

  useEffect(() => {
    const ac = new AbortController()
    load(ac.signal)
    return () => ac.abort()
  }, [load])

  if (!formateur) return null
  const d = detail || formateur
  const stats = { ...(d.statistiques || {}), sessions_count: d.sessions_count, total_duree_minutes: d.total_duree_minutes, total_duree_realisee_minutes: d.total_duree_realisee_minutes }
  const modules = Array.isArray(d.modules) ? d.modules : []

  return (
    <div className="modal-overlay finance-modal" onClick={onClose}>
      <div
        className="modal-content"
        style={{ width: 'min(96vw, 1000px)', maxWidth: '1000px', maxHeight: '92vh', display: 'flex', flexDirection: 'column' }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-header">
          <h5>
            <i className="bi bi-person-video3 me-2"></i>
            {d.prenom} {d.nom}
            {d.numerobadge && <small className="ms-2 opacity-75">({d.numerobadge})</small>}
          </h5>
          <button type="button" className="btn-close" onClick={onClose}>&times;</button>
        </div>

        <div className="modal-body" style={{ overflowY: 'auto', flex: 1, padding: '1rem 1.25rem' }}>
          {loading ? (
            <div className="loading py-5"><div className="spinner"></div></div>
          ) : (
            <>
              <ul className="finance-detail-tabs" role="tablist">
                {TABS.map((t) => (
                  <li key={t.id} role="presentation">
                    <button
                      type="button"
                      className={`finance-detail-tab${tab === t.id ? ' active' : ''}`}
                      onClick={() => setTab(t.id)}
                    >
                      <i className={`bi ${t.icon}`}></i>
                      <span>{t.label}</span>
                    </button>
                  </li>
                ))}
              </ul>

              <div className="finance-modal-summary">
                <span><i className="bi bi-clock"></i>Planifié <strong>{fmtDuration(d.total_duree_minutes)}</strong></span>
                <span><i className="bi bi-clock-history"></i>Réalisé <strong>{fmtDuration(d.total_duree_realisee_minutes)}</strong></span>
                <span><i className="bi bi-percent"></i>Taux <strong>{d.statistiques?.taux_realisation_pct ?? 0}%</strong></span>
                <span><i className="bi bi-journal-bookmark"></i>Modules <strong>{d.nb_formations ?? modules.length}</strong></span>
              </div>

              {tab === 'statistiques' && <FinanceStatsGrid stats={stats} />}

              {tab === 'identite' && (
                <div className="grid-2">
                  <div><small className="text-muted">N° Badge</small><div><span className="badge-bg-info">{d.numerobadge || '-'}</span></div></div>
                  <div><small className="text-muted">Spécialité</small><div>{d.specialite || '-'}</div></div>
                  <div><small className="text-muted">Nom</small><div><strong>{d.nom || '-'}</strong></div></div>
                  <div><small className="text-muted">Prénom</small><div>{d.prenom || '-'}</div></div>
                  <div><small className="text-muted">E-mail</small><div>{d.email || '-'}</div></div>
                  <div><small className="text-muted">Téléphone</small><div>{d.telephone || '-'}</div></div>
                  <div><small className="text-muted">Organisation</small><div>{d.organisation || '-'}</div></div>
                  <div><small className="text-muted">Modules dispensés</small><div><span className="badge-bg-success">{d.nb_formations ?? modules.length}</span></div></div>
                  <div style={{ gridColumn: '1 / -1' }}>
                    <small className="text-muted">Secrétariat(s)</small>
                    <div>{(d.secretariats_noms || []).join(', ') || '-'}</div>
                  </div>
                  {d.created_at && (
                    <div><small className="text-muted">Enregistré le</small><div>{fmtDate(d.created_at)}</div></div>
                  )}
                  {canViewSensitive && (
                    <>
                      <div style={{ gridColumn: '1 / -1' }}>
                        <hr className="my-2" />
                        <small className="text-muted fw-semibold">Données confidentielles</small>
                      </div>
                      <div><small className="text-muted">N° pièce d&apos;identité</small><div>{d.numero_piece_identite || '-'}</div></div>
                      <div><small className="text-muted">N° compte bancaire (RIB)</small><div>{d.numero_compte_bancaire || '-'}</div></div>
                    </>
                  )}
                </div>
              )}

              {tab === 'modules' && (
                modules.length === 0 ? (
                  <div className="finance-empty"><i className="bi bi-journal-x"></i>Aucun module enregistré</div>
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.65rem' }}>
                    {modules.map((m) => (
                      <div key={m.module_id} className="finance-module-card">
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '0.5rem', flexWrap: 'wrap' }}>
                          <div>
                            <strong style={{ fontSize: '0.95rem' }}>{m.module_intitule || '—'}</strong>
                            {m.formation_intitule && <span className="text-muted" style={{ fontSize: '0.82rem' }}> — {m.formation_intitule}</span>}
                            {(m.grade || m.groupe) && (
                              <div className="text-muted" style={{ fontSize: '0.78rem', marginTop: '0.15rem' }}>
                                {m.grade && <span><i className="bi bi-award me-1"></i>{m.grade}</span>}
                                {m.grade && m.groupe && ' · '}
                                {m.groupe && <span><i className="bi bi-people me-1"></i>{m.groupe}</span>}
                              </div>
                            )}
                            {m.date_debut && (
                              <div className="text-muted" style={{ fontSize: '0.78rem', marginTop: '0.25rem' }}>
                                <i className="bi bi-calendar3 me-1"></i>
                                {fmtDate(m.date_debut)}{m.date_fin ? ` → ${fmtDate(m.date_fin)}` : ''}
                                {m.secretariat_nom && <span className="ms-2"><i className="bi bi-briefcase me-1"></i>{m.secretariat_nom}</span>}
                              </div>
                            )}
                          </div>
                          <span className="badge-bg-secondary" style={{ whiteSpace: 'nowrap' }}>{STATUT_LABELS[m.statut] || m.statut || '—'}</span>
                        </div>
                        <div className="finance-module-metrics">
                          <span><i className="bi bi-calendar3 me-1"></i><strong>{m.sessions_count ?? 0}</strong> séance(s)</span>
                          <span>Planifié <strong>{fmtDuration(m.total_duree_minutes)}</strong></span>
                          <span>Réalisé <strong>{fmtDuration(m.total_duree_realisee_minutes)}</strong></span>
                          <span>Taux <strong>{m.taux_realisation_pct ?? 0}%</strong></span>
                        </div>
                      </div>
                    ))}
                  </div>
                )
              )}

              {tab === 'notes' && (
                <div>
                  <div className="d-flex align-items-center gap-2 mb-2 text-muted small">
                    <i className="bi bi-info-circle"></i>
                    Observations enregistrées sur le formateur.
                  </div>
                  {d.observations ? (
                    <div className="card" style={{ padding: '1rem', whiteSpace: 'pre-wrap', lineHeight: 1.5 }}>{d.observations}</div>
                  ) : (
                    <div className="finance-empty"><i className="bi bi-journal-text"></i>Aucune observation enregistrée</div>
                  )}
                </div>
              )}

              {tab === 'seances' && (
                <FinanceSessionsByGroupeTable
                  groups={d.sessions_by_groupe ?? []}
                  formatDuration={fmtDuration}
                  showMontant={false}
                  showPointage
                />
              )}
            </>
          )}
        </div>

        <div className="modal-footer" style={{ justifyContent: 'space-between', flexWrap: 'wrap', gap: '0.5rem' }}>
          <div className="d-flex gap-2 flex-wrap">
            <button type="button" className="btn btn-outline-danger btn-sm" disabled={exporting === 'pdf'} onClick={() => onExport?.(formateur, 'pdf')}>
              {exporting === 'pdf' ? <span className="spinner-border spinner-border-sm me-1" /> : <i className="bi bi-file-earmark-pdf me-1"></i>}Export PDF
            </button>
            <button type="button" className="btn btn-outline-success btn-sm" disabled={exporting === 'excel'} onClick={() => onExport?.(formateur, 'excel')}>
              {exporting === 'excel' ? <span className="spinner-border spinner-border-sm me-1" /> : <i className="bi bi-file-earmark-spreadsheet me-1"></i>}Export Excel
            </button>
          </div>
          <button type="button" className="btn btn-secondary" onClick={onClose}>Fermer</button>
        </div>
      </div>
    </div>
  )
}
