import { useMemo, useState } from 'react'
import { fmtDuration, formatMoney } from '../FinanceStatsGrid'

const DRILL_CONFIG = {
  planifie: {
    title: 'Volume horaire planifié par module',
    icon: 'bi-clock',
    valueKey: 'total_duree_minutes',
    format: 'duration',
    sortKey: 'total_duree_minutes',
  },
  realise: {
    title: 'Volume horaire réalisé par module',
    icon: 'bi-clock-history',
    valueKey: 'total_duree_realisee_minutes',
    format: 'duration',
    sortKey: 'total_duree_realisee_minutes',
  },
  taux: {
    title: 'Taux de réalisation par module',
    icon: 'bi-percent',
    valueKey: 'taux_realisation_pct',
    format: 'pct',
    sortKey: 'taux_realisation_pct',
  },
  cout: {
    title: 'Coût du volume horaire réalisé par module',
    icon: 'bi-cash-stack',
    valueKey: 'montant_realise',
    format: 'money',
    sortKey: 'montant_realise',
  },
  cout_prevu: {
    title: 'Coût prévisionnel du volume horaire par module',
    icon: 'bi-calculator',
    valueKey: 'montant_prevu',
    format: 'money',
    sortKey: 'montant_prevu',
  },
}

function formatDetailValue(mod, cfg) {
  const v = mod[cfg.valueKey]
  if (cfg.format === 'duration') return fmtDuration(v)
  if (cfg.format === 'pct') return `${v ?? 0} %`
  if (cfg.format === 'money') return `${formatMoney(v ?? 0)} FCFA`
  return v ?? '—'
}

function sumBreakdown(rows, cfg, drillType) {
  if (drillType === 'planifie') {
    return rows.reduce((s, m) => s + Number(m.total_duree_minutes || 0), 0)
  }
  if (drillType === 'realise') {
    return rows.reduce((s, m) => s + Number(m.total_duree_realisee_minutes || 0), 0)
  }
  if (drillType === 'taux') {
    const planned = rows.reduce((s, m) => s + Number(m.total_duree_minutes || 0), 0)
    const realized = rows.reduce((s, m) => s + Number(m.total_duree_realisee_minutes || 0), 0)
    return planned > 0 ? Math.min(100, Math.round((realized / planned) * 1000) / 10) : 0
  }
  if (drillType === 'cout') {
    return rows.reduce((s, m) => s + Number(m.montant_realise || 0), 0)
  }
  if (drillType === 'cout_prevu') {
    return rows.reduce((s, m) => s + Number(m.montant_prevu || 0), 0)
  }
  return rows.reduce((s, m) => s + Number(m[cfg.valueKey] || 0), 0)
}

function formatFooterTotal(total, drillType) {
  if (drillType === 'planifie' || drillType === 'realise') return fmtDuration(total)
  if (drillType === 'taux') return `${total} %`
  if (drillType === 'cout' || drillType === 'cout_prevu') return `${formatMoney(total)} FCFA`
  return total
}

function matchesSearch(mod, query) {
  if (!query) return true
  const q = query.toLowerCase()
  const haystack = [
    mod.module_intitule,
    mod.formation_intitule,
    mod.secretariat_nom,
    mod.grade,
    mod.groupe,
  ].filter(Boolean).join(' ').toLowerCase()
  return haystack.includes(q)
}

export default function FinanceModuleBreakdownModal({ drillType, modules, onClose }) {
  const cfg = DRILL_CONFIG[drillType]
  const [search, setSearch] = useState('')

  const allRows = useMemo(() => {
    if (!cfg) return []
    return [...(modules || [])].sort(
      (a, b) => Number(b[cfg.sortKey] || 0) - Number(a[cfg.sortKey] || 0),
    )
  }, [modules, cfg])

  const rows = useMemo(
    () => allRows.filter(m => matchesSearch(m, search.trim())),
    [allRows, search],
  )

  if (!cfg) return null

  const filteredTotal = sumBreakdown(rows, cfg, drillType)
  const globalTotal = sumBreakdown(allRows, cfg, drillType)
  const isFiltered = Boolean(search.trim()) && rows.length !== allRows.length

  return (
    <div className="modal-overlay finance-modal" onClick={onClose}>
      <div
        className="modal-content"
        style={{ maxWidth: '920px', width: '95%', maxHeight: '90vh', display: 'flex', flexDirection: 'column' }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-header">
          <div>
            <h5 className="modal-title mb-1">
              <i className={`bi ${cfg.icon} me-2`}></i>
              {cfg.title}
            </h5>
            <div className="text-muted small">
              {allRows.length} module{allRows.length !== 1 ? 's' : ''} sur la période
              {isFiltered && (
                <span> · {rows.length} affiché{rows.length !== 1 ? 's' : ''}</span>
              )}
            </div>
          </div>
          <button type="button" className="btn-close" aria-label="Fermer" onClick={onClose}></button>
        </div>
        <div className="modal-body" style={{ overflowY: 'auto', flex: 1, padding: '1rem 1.25rem' }}>
          {allRows.length > 0 && (
            <div className="mb-3">
              <input
                type="search"
                className="form-control form-control-sm"
                placeholder="Filtrer par module, formation, secrétariat, grade, groupe…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                autoFocus
              />
            </div>
          )}
          {allRows.length === 0 ? (
            <div className="finance-empty">
              <i className="bi bi-inbox"></i>
              Aucun module sur cette période
            </div>
          ) : rows.length === 0 ? (
            <div className="finance-empty">
              <i className="bi bi-search"></i>
              Aucun module ne correspond au filtre
            </div>
          ) : (
            <>
              {(drillType === 'cout' || drillType === 'cout_prevu') && (
                <p className="text-muted small mb-2">
                  <i className="bi bi-info-circle me-1"></i>
                  Chaque ligne est facturée au tarif horaire du cycle de formation associé au module
                  {drillType === 'cout_prevu' ? ', appliqué au volume planifié.' : '.'}
                </p>
              )}
              <div className="finance-table-wrap">
              <table className="finance-table">
                <thead>
                  <tr>
                    <th>Module</th>
                    <th>Formation (cycle)</th>
                    <th>Grade</th>
                    <th>Groupe</th>
                    <th>Séances</th>
                    {(drillType === 'cout' || drillType === 'cout_prevu') && <th style={{ textAlign: 'right' }}>Tarif / h</th>}
                    <th style={{ textAlign: 'right' }}>
                      {drillType === 'planifie' && 'Planifié'}
                      {drillType === 'realise' && 'Réalisé'}
                      {drillType === 'taux' && 'Taux'}
                      {drillType === 'cout' && 'Coût réalisé'}
                      {drillType === 'cout_prevu' && 'Coût prévisionnel'}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((m) => (
                    <tr key={m.module_id}>
                      <td>
                        <strong>{m.module_intitule || '—'}</strong>
                        {m.secretariat_nom && (
                          <div className="text-muted small">{m.secretariat_nom}</div>
                        )}
                      </td>
                      <td className="small">{m.formation_intitule || '—'}</td>
                      <td className="small">{m.grade || '—'}</td>
                      <td className="small">{m.groupe || '—'}</td>
                      <td><span className="badge-bg-secondary">{m.sessions_count ?? 0}</span></td>
                      {(drillType === 'cout' || drillType === 'cout_prevu') && (
                        <td style={{ textAlign: 'right', whiteSpace: 'nowrap' }}>
                          {m.prix_heure_realisee != null
                            ? `${formatMoney(m.prix_heure_realisee)} F`
                            : '—'}
                        </td>
                      )}
                      <td style={{ textAlign: 'right', fontWeight: 600, whiteSpace: 'nowrap' }}>
                        {formatDetailValue(m, cfg)}
                      </td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr style={{ background: 'var(--fin-light-orange, #fff8e0)' }}>
                    <td colSpan={(drillType === 'cout' || drillType === 'cout_prevu') ? 6 : 5}>
                      <strong>TOTAL{isFiltered ? ' (filtre)' : ''}</strong>
                      {isFiltered && (
                        <div className="text-muted small fw-normal">
                          Global : {formatFooterTotal(globalTotal, drillType)}
                        </div>
                      )}
                    </td>
                    <td style={{ textAlign: 'right', fontWeight: 700 }}>
                      {formatFooterTotal(filteredTotal, drillType)}
                    </td>
                  </tr>
                </tfoot>
              </table>
              </div>
            </>
          )}
        </div>
        <div className="modal-footer">
          <button type="button" className="btn btn-secondary btn-sm" onClick={onClose}>
            Fermer
          </button>
        </div>
      </div>
    </div>
  )
}
