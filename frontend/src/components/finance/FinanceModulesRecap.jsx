import { formatMoney } from '../FinanceStatsGrid'
import FinanceToleranceBadge from './FinanceToleranceBadge'

export default function FinanceModulesRecap({ modules, formatDuration }) {
  const list = Array.isArray(modules) ? modules : []
  const showTolerance = list.some((m) => m.tolerance?.tolerance_active)
  if (list.length === 0) {
    return (
      <div className="finance-empty">
        <i className="bi bi-journal-x"></i>
        Aucun module dispensé sur cette période
      </div>
    )
  }

  return (
    <div className="finance-table-wrap">
      <table className="finance-table">
        <thead>
          <tr>
            <th>Module</th>
            <th>Formation</th>
            <th>Grade</th>
            <th>Groupe</th>
            <th>Séances</th>
            <th>Planifié</th>
            <th>Réalisé</th>
            <th>Taux</th>
            {showTolerance && <th>Statut</th>}
            <th style={{ textAlign: 'right' }}>Montant prévu</th>
            <th style={{ textAlign: 'right' }}>Montant réalisé</th>
          </tr>
        </thead>
        <tbody>
          {list.map((m) => (
            <tr key={m.module_id}>
              <td><strong>{m.module_intitule || '—'}</strong></td>
              <td className="small text-muted">{m.formation_intitule || '—'}</td>
              <td>{m.grade || '—'}</td>
              <td>{m.groupe || '—'}</td>
              <td><span className="badge-bg-secondary">{m.sessions_count ?? 0}</span></td>
              <td>{formatDuration(m.total_duree_minutes)}</td>
              <td>{formatDuration(m.total_duree_realisee_minutes)}</td>
              <td>{m.taux_realisation_pct ?? 0}%</td>
              {showTolerance && (
                <td><FinanceToleranceBadge tolerance={m.tolerance} showInactive /></td>
              )}
              <td style={{ textAlign: 'right', fontWeight: 600 }}>
                {formatMoney(m.montant_prevu ?? 0)} F
              </td>
              <td style={{ textAlign: 'right', fontWeight: 600, color: 'var(--fin-accent)' }}>
                {formatMoney(m.montant_realise ?? 0)} F
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
