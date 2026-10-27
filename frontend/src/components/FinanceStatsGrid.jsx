import Pagination from './Pagination'
import { useClientPagination, TABLE_PAGE_SIZE } from '../hooks/useClientPagination'

const fmtDuration = (minutes) => {
  const total = Math.round(Number(minutes || 0))
  const h = Math.floor(total / 60)
  const m = total % 60
  if (m === 0) return `${h}h`
  return `${h}h ${m}min`
}

const fmtHeures = (heures) => `${Math.round(Number(heures) || 0)}`

const formatMoney = (value) => {
  const n = Number(value || 0)
  return new Intl.NumberFormat('fr-FR', { minimumFractionDigits: 0, maximumFractionDigits: 2 }).format(n)
}

const STATUT_LABELS = {
  PLANIFIEE: 'Planifiée',
  EN_COURS: 'En cours',
  TERMINEE: 'Terminée',
  SUSPENDUE: 'Suspendue',
}

export function FinanceStatsGrid({ stats, montant }) {
  if (!stats) return null
  const items = [
    { label: 'Séances totales', value: stats.sessions_count ?? '—', icon: 'bi-calendar3' },
    { label: 'Avec pointage', value: stats.sessions_avec_pointage ?? 0, icon: 'bi-check-circle' },
    { label: 'Sans pointage', value: stats.sessions_sans_pointage ?? 0, icon: 'bi-x-circle' },
    { label: 'Taux réalisation', value: `${stats.taux_realisation_pct ?? 0}%`, icon: 'bi-percent' },
    { label: 'Temps planifié', value: fmtDuration(stats.total_duree_minutes), icon: 'bi-clock' },
    { label: 'Temps réalisé', value: fmtDuration(stats.total_duree_realisee_minutes), icon: 'bi-clock-history' },
    { label: 'Écart planifié / réalisé', value: fmtDuration(Math.abs(stats.ecart_planifie_realise_minutes ?? 0)), icon: 'bi-arrow-left-right' },
    { label: 'Moy. / séance (planifié)', value: fmtDuration(stats.moyenne_duree_seance_minutes), icon: 'bi-bar-chart' },
    { label: 'Moy. / séance (réalisé)', value: fmtDuration(stats.moyenne_realisee_seance_minutes), icon: 'bi-graph-up' },
  ]
  if (stats.premiere_seance_date) {
    items.push({
      label: 'Première séance',
      value: new Date(stats.premiere_seance_date).toLocaleDateString('fr-FR'),
      icon: 'bi-calendar-event',
    })
  }
  if (stats.derniere_seance_date) {
    items.push({
      label: 'Dernière séance',
      value: new Date(stats.derniere_seance_date).toLocaleDateString('fr-FR'),
      icon: 'bi-calendar-check',
    })
  }
  if (montant != null) {
    items.push(
      { label: 'Montant total', value: `${formatMoney(montant)} FCFA`, icon: 'bi-cash-stack', highlight: true },
      { label: 'Moy. / séance', value: `${formatMoney(stats.moyenne_montant_par_seance)} FCFA`, icon: 'bi-currency-exchange' },
    )
  }

  return (
    <div className="finance-stat-grid">
      {items.map((item) => (
        <div
          key={item.label}
          className={`finance-stat-item${item.highlight ? ' finance-stat-item--highlight' : ''}`}
        >
          <div className="finance-stat-item-label">
            <i className={`bi ${item.icon}`}></i>
            {item.label}
          </div>
          <div className="finance-stat-item-value">{item.value}</div>
        </div>
      ))}
    </div>
  )
}

export function FinanceModulesList({ modules, formatDuration }) {
  const list = Array.isArray(modules) ? modules : []
  const {
    page,
    setPage,
    totalPages,
    totalItems,
    pageItems,
    pageSize,
  } = useClientPagination(list, TABLE_PAGE_SIZE, [list.length])

  if (list.length === 0) {
    return (
      <div className="finance-empty">
        <i className="bi bi-journal-x"></i>
        Aucun module sur cette période
      </div>
    )
  }

  return (
    <>
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.65rem' }}>
      {pageItems.map((m) => (
        <div key={m.module_id} className="finance-module-card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '0.5rem', flexWrap: 'wrap' }}>
            <div>
              <strong style={{ fontSize: '0.95rem' }}>{m.module_intitule || '—'}</strong>
              {m.formation_intitule && (
                <span className="text-muted" style={{ fontSize: '0.82rem' }}> — {m.formation_intitule}</span>
              )}
              {(m.grade || m.groupe) && (
                <div className="text-muted" style={{ fontSize: '0.78rem', marginTop: '0.15rem' }}>
                  {m.grade && <span><i className="bi bi-award me-1"></i>{m.grade}</span>}
                  {m.grade && m.groupe && ' · '}
                  {m.groupe && <span><i className="bi bi-people me-1"></i>{m.groupe}</span>}
                </div>
              )}
              <div className="text-muted" style={{ fontSize: '0.78rem', marginTop: '0.25rem' }}>
                {(m.site || m.salle) && <span><i className="bi bi-building me-1"></i>{[m.site, m.salle].filter(Boolean).join(' / ')} </span>}
                {m.secretariat_nom && <span><i className="bi bi-briefcase me-1"></i>{m.secretariat_nom} </span>}
                {m.date_debut && (
                  <span><i className="bi bi-calendar3 me-1"></i>
                    {new Date(m.date_debut).toLocaleDateString('fr-FR')}
                    {m.date_fin ? ` → ${new Date(m.date_fin).toLocaleDateString('fr-FR')}` : ''}
                  </span>
                )}
              </div>
            </div>
            <span className="badge-bg-secondary" style={{ whiteSpace: 'nowrap' }}>
              {STATUT_LABELS[m.statut] || m.statut || '—'}
            </span>
          </div>
          <div className="finance-module-metrics">
            <span><i className="bi bi-calendar3 me-1"></i><strong>{m.sessions_count}</strong> séance(s)</span>
            <span>Planifié <strong>{formatDuration(m.total_duree_minutes)}</strong></span>
            <span>Réalisé <strong>{formatDuration(m.total_duree_realisee_minutes)}</strong></span>
            <span>Taux <strong>{m.taux_realisation_pct ?? 0}%</strong></span>
            <span className="text-success"><strong>{formatMoney(m.montant_realise)} FCFA</strong></span>
          </div>
        </div>
      ))}
    </div>
    <Pagination
      page={page}
      totalPages={totalPages}
      onPageChange={setPage}
      totalItems={totalItems}
      pageSize={pageSize}
      activeClassName="pagination-num--active pagination-num--finance"
    />
    </>
  )
}

export { fmtDuration, fmtHeures, formatMoney, STATUT_LABELS }
