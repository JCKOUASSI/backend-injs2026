import { Fragment } from 'react'

function groupeLabel(grade, groupe) {
  const parts = []
  if (grade) parts.push(`Grade ${grade}`)
  if (groupe) parts.push(groupe)
  return parts.join(' — ') || 'Sans groupe'
}

export function FinanceSessionsByGroupeTable({
  groups,
  formatDuration,
  formatMoney,
  showMontant = false,
  showPointage = false,
  showAjustement = false,
  onProposeAjustement,
}) {
  const list = Array.isArray(groups) ? groups : []
  if (list.length === 0) {
    return (
      <div className="finance-empty">
        <i className="bi bi-calendar-x"></i>
        Aucune séance sur cette période
      </div>
    )
  }

  const colCount = (showMontant ? 6 : 7) + (showAjustement ? 1 : 0)

  return (
    <div className="finance-table-wrap">
      <table className="finance-table">
        <thead>
          <tr>
            <th>Date</th>
            <th>Séance</th>
            <th>Module</th>
            {!showMontant && <th>Formation</th>}
            <th>Créneau</th>
            <th>Réalisé</th>
            {showMontant && <th style={{ textAlign: 'right' }}>Montant</th>}
            {showPointage && <th>Pointage</th>}
            {showAjustement && <th style={{ width: '1%' }}></th>}
          </tr>
        </thead>
        <tbody>
          {list.map((block, blockIdx) => {
            const st = block.sous_total || {}
            const label = groupeLabel(block.grade, block.groupe)
            return (
              <Fragment key={`grp-${blockIdx}-${label}`}>
                <tr className="finance-groupe-header-row">
                  <td colSpan={colCount}>
                    <i className="bi bi-people me-2"></i>
                    <strong>{label}</strong>
                    <span className="text-muted small ms-2">({st.sessions_count ?? 0} séance(s))</span>
                  </td>
                </tr>
                {(block.sessions || []).map((s) => (
                  <tr key={s.session_id}>
                    <td>{s.date_journee || '—'}</td>
                    <td>{s.intitule || `Session ${s.numero ?? ''}`}</td>
                    <td>{s.module_intitule || '—'}</td>
                    {!showMontant && <td className="small text-muted">{s.formation_intitule || '—'}</td>}
                    <td>{formatDuration(s.duree_minutes)}</td>
                    <td>{formatDuration(s.duree_realisee_minutes)}</td>
                    {showMontant && (
                      <td style={{ textAlign: 'right', fontWeight: 600 }}>
                        {formatMoney(s.montant_realise ?? 0)} F
                      </td>
                    )}
                    {showPointage && (
                      <td>
                        {s.a_pointage
                          ? <span className="badge-bg-success">Oui</span>
                          : <span className="badge-bg-secondary">Non</span>}
                      </td>
                    )}
                    {showAjustement && (
                      <td className="text-end text-nowrap">
                        {(s.duree_realisee_minutes ?? 0) > 0 && (
                          <button
                            type="button"
                            className="btn btn-outline-warning btn-sm py-0 px-2"
                            title="Proposer un ajustement horaire"
                            onClick={() => onProposeAjustement?.(s)}
                          >
                            <i className="bi bi-arrow-left-right"></i>
                          </button>
                        )}
                      </td>
                    )}
                  </tr>
                ))}
                <tr className="finance-groupe-subtotal-row">
                  <td colSpan={showMontant ? 3 : 4} style={{ fontWeight: 700 }}>
                    Sous-total — {label}
                  </td>
                  <td style={{ fontWeight: 700 }}>{formatDuration(st.creneau_minutes)}</td>
                  <td style={{ fontWeight: 700 }}>{formatDuration(st.realise_minutes)}</td>
                  {showMontant && (
                    <td style={{ textAlign: 'right', fontWeight: 700 }}>
                      {formatMoney(st.montant ?? 0)} F
                    </td>
                  )}
                  {showPointage && <td />}
                  {showAjustement && <td />}
                </tr>
              </Fragment>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
