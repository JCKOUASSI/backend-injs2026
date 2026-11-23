import { useEffect, useState, useCallback } from 'react'
import api from '../../services/api'
import { useToast } from '../../context/ToastContext'
import { FinanceStatsGrid, fmtDuration } from '../FinanceStatsGrid'
import { FinanceSessionsByGroupeTable } from '../finance/FinanceSessionsByGroupe'
import './FormateurFicheModal.css'

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
  const initiales = [d.prenom, d.nom]
    .filter(Boolean)
    .map((nom) => nom.trim()[0])
    .join('')
    .toUpperCase() || 'F'

  return (
    <div className="modal-overlay finance-modal ffm-overlay" onClick={onClose}>
      <section
        className="modal-content ffm-modal"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby="ffm-title"
        aria-busy={loading}
      >
        <header className="ffm-header">
          <div className="ffm-identite">
            <span className="ffm-avatar" aria-hidden="true">{initiales}</span>
            <div className="ffm-identite-texte">
              <span className="ffm-surtitre">Espace enseignant</span>
              <h2 id="ffm-title">{d.prenom} {d.nom}</h2>
              <div className="ffm-identite-meta">
                {d.numerobadge && <span><i className="bi bi-person-vcard" aria-hidden="true"></i>{d.numerobadge}</span>}
                {d.specialite && <span><i className="bi bi-award" aria-hidden="true"></i>{d.specialite}</span>}
              </div>
            </div>
          </div>
          <button
            type="button"
            className="ffm-close"
            onClick={onClose}
            aria-label="Fermer la fiche formateur"
          >
            <i className="bi bi-x-lg" aria-hidden="true"></i>
          </button>
        </header>

        <div className="modal-body ffm-body">
          {loading ? (
            <div className="ffm-loading" role="status">
              <span className="spinner" aria-hidden="true"></span>
              <span>Chargement de la fiche…</span>
            </div>
          ) : (
            <>
              <div className="ffm-summary" aria-label="Résumé de l’activité">
                <div className="ffm-summary-item">
                  <span><i className="bi bi-clock" aria-hidden="true"></i>Planifié</span>
                  <strong>{fmtDuration(d.total_duree_minutes)}</strong>
                </div>
                <div className="ffm-summary-item">
                  <span><i className="bi bi-clock-history" aria-hidden="true"></i>Réalisé</span>
                  <strong>{fmtDuration(d.total_duree_realisee_minutes)}</strong>
                </div>
                <div className="ffm-summary-item">
                  <span><i className="bi bi-percent" aria-hidden="true"></i>Taux de réalisation</span>
                  <strong>{d.statistiques?.taux_realisation_pct ?? 0}%</strong>
                </div>
                <div className="ffm-summary-item">
                  <span><i className="bi bi-journal-bookmark" aria-hidden="true"></i>Modules</span>
                  <strong>{d.nb_formations ?? modules.length}</strong>
                </div>
              </div>

              <nav className="ffm-tabs" role="tablist" aria-label="Sections de la fiche formateur">
                {TABS.map((t) => (
                  <button
                    key={t.id}
                    type="button"
                    id={`ffm-tab-${t.id}`}
                    role="tab"
                    aria-controls={`ffm-panel-${t.id}`}
                    aria-selected={tab === t.id}
                    tabIndex={tab === t.id ? 0 : -1}
                    className={`ffm-tab${tab === t.id ? ' is-active' : ''}`}
                    onClick={() => setTab(t.id)}
                  >
                    <i className={`bi ${t.icon}`} aria-hidden="true"></i>
                    <span>{t.label}</span>
                  </button>
                ))}
              </nav>

              <div
                className="ffm-tab-panel"
                id={`ffm-panel-${tab}`}
                role="tabpanel"
                aria-labelledby={`ffm-tab-${tab}`}
                tabIndex={0}
              >
                {tab === 'statistiques' && <FinanceStatsGrid stats={stats} />}

                {tab === 'identite' && (
                  <div className="ffm-identite-grid">
                    <div><span>N° Badge</span><strong>{d.numerobadge || '—'}</strong></div>
                    <div><span>Spécialité</span><strong>{d.specialite || '—'}</strong></div>
                    <div><span>Nom</span><strong>{d.nom || '—'}</strong></div>
                    <div><span>Prénom</span><strong>{d.prenom || '—'}</strong></div>
                    <div><span>E-mail</span><strong>{d.email || '—'}</strong></div>
                    <div><span>Téléphone</span><strong>{d.telephone || '—'}</strong></div>
                    <div><span>Organisation</span><strong>{d.organisation || '—'}</strong></div>
                    <div><span>Modules dispensés</span><strong>{d.nb_formations ?? modules.length}</strong></div>
                    <div className="ffm-field--wide">
                      <span>Secrétariat(s)</span>
                      <strong>{(d.secretariats_noms || []).join(', ') || '—'}</strong>
                    </div>
                    {d.created_at && (
                      <div><span>Enregistré le</span><strong>{fmtDate(d.created_at)}</strong></div>
                    )}
                    {canViewSensitive && (
                      <>
                        <div className="ffm-sensitive-title">Données confidentielles</div>
                        <div><span>N° pièce d&apos;identité</span><strong>{d.numero_piece_identite || '—'}</strong></div>
                        <div><span>N° compte bancaire (RIB)</span><strong>{d.numero_compte_bancaire || '—'}</strong></div>
                      </>
                    )}
                  </div>
                )}

                {tab === 'modules' && (
                  modules.length === 0 ? (
                    <div className="ffm-empty">
                      <i className="bi bi-journal-x" aria-hidden="true"></i>
                      <strong>Aucun module enregistré</strong>
                      <span>Les modules associés apparaîtront ici.</span>
                    </div>
                  ) : (
                    <div className="ffm-module-list">
                      {modules.map((m) => (
                        <article key={m.module_id} className="finance-module-card ffm-module-card">
                          <div className="ffm-module-header">
                            <div>
                              <h3>{m.module_intitule || '—'}</h3>
                              {m.formation_intitule && <span className="ffm-module-formation">{m.formation_intitule}</span>}
                              {(m.grade || m.groupe) && (
                                <span className="ffm-module-meta">
                                  {m.grade && <span><i className="bi bi-award" aria-hidden="true"></i>{m.grade}</span>}
                                  {m.groupe && <span><i className="bi bi-people" aria-hidden="true"></i>{m.groupe}</span>}
                                </span>
                              )}
                              {m.date_debut && (
                                <span className="ffm-module-meta">
                                  <i className="bi bi-calendar3" aria-hidden="true"></i>
                                  {fmtDate(m.date_debut)}{m.date_fin ? ` → ${fmtDate(m.date_fin)}` : ''}
                                  {m.secretariat_nom && ` · ${m.secretariat_nom}`}
                                </span>
                              )}
                            </div>
                            <span className="ffm-module-statut">{STATUT_LABELS[m.statut] || m.statut || '—'}</span>
                          </div>
                          <div className="finance-module-metrics ffm-module-metrics">
                            <span><i className="bi bi-calendar3" aria-hidden="true"></i><strong>{m.sessions_count ?? 0}</strong> séance(s)</span>
                            <span>Planifié <strong>{fmtDuration(m.total_duree_minutes)}</strong></span>
                            <span>Réalisé <strong>{fmtDuration(m.total_duree_realisee_minutes)}</strong></span>
                            <span>Taux <strong>{m.taux_realisation_pct ?? 0}%</strong></span>
                          </div>
                        </article>
                      ))}
                    </div>
                  )
                )}

                {tab === 'notes' && (
                  <div className="ffm-notes">
                    <div className="ffm-notes-aide">
                      <i className="bi bi-info-circle" aria-hidden="true"></i>
                      Observations enregistrées sur le formateur.
                    </div>
                    {d.observations ? (
                      <div className="ffm-notes-contenu">{d.observations}</div>
                    ) : (
                      <div className="ffm-empty">
                        <i className="bi bi-journal-text" aria-hidden="true"></i>
                        <strong>Aucune observation enregistrée</strong>
                        <span>Aucune note n’est disponible pour ce formateur.</span>
                      </div>
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
              </div>
            </>
          )}
        </div>

        <footer className="modal-footer ffm-footer">
          <div className="ffm-export-actions">
            <button
              type="button"
              className="btn ffm-action ffm-action--pdf"
              disabled={exporting === 'pdf'}
              aria-busy={exporting === 'pdf'}
              onClick={() => onExport?.(formateur, 'pdf')}
            >
              {exporting === 'pdf'
                ? <span className="ffm-spinner" aria-hidden="true"></span>
                : <i className="bi bi-file-earmark-pdf" aria-hidden="true"></i>}
              {exporting === 'pdf' ? 'Préparation du PDF…' : 'Exporter en PDF'}
            </button>
            <button
              type="button"
              className="btn ffm-action ffm-action--excel"
              disabled={exporting === 'excel'}
              aria-busy={exporting === 'excel'}
              onClick={() => onExport?.(formateur, 'excel')}
            >
              {exporting === 'excel'
                ? <span className="ffm-spinner" aria-hidden="true"></span>
                : <i className="bi bi-file-earmark-spreadsheet" aria-hidden="true"></i>}
              {exporting === 'excel' ? 'Préparation du fichier…' : 'Exporter en Excel'}
            </button>
          </div>
          <button type="button" className="btn ffm-action ffm-action--close" onClick={onClose}>
            <i className="bi bi-check2" aria-hidden="true"></i>Fermer
          </button>
        </footer>
      </section>
    </div>
  )
}
