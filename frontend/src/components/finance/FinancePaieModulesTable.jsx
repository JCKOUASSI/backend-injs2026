function volumeHeures(minutes) {
  return Math.round(Number(minutes || 0) / 60)
}

export default function FinancePaieModulesTable({ modules }) {
  const list = (Array.isArray(modules) ? modules : []).filter(
    (m) => Number(m.sessions_count || 0) > 0,
  )

  if (list.length === 0) {
    return (
      <div className="finance-empty">
        <i className="bi bi-journal-x"></i>
        Aucun module sur cette période
      </div>
    )
  }

  const totalRealise = list.reduce(
    (sum, m) => sum + volumeHeures(m.total_duree_realisee_minutes),
    0,
  )
  const totalPlanifie = list.reduce(
    (sum, m) => sum + volumeHeures(m.total_creneau_periode_minutes),
    0,
  )

  return (
    <div className="finance-table-wrap mb-3">
      <table className="finance-table">
        <thead>
          <tr>
            <th>N°</th>
            <th>Module</th>
            <th>Catégorie / grade</th>
            <th>Groupe</th>
            <th>Volume réalisé</th>
            <th>Volume planifié</th>
          </tr>
        </thead>
        <tbody>
          {list.map((m, idx) => (
            <tr key={m.module_id}>
              <td>{idx + 1}</td>
              <td><strong>{m.module_intitule || '—'}</strong></td>
              <td>{m.grade || '—'}</td>
              <td>{m.groupe || '—'}</td>
              <td>{volumeHeures(m.total_duree_realisee_minutes)} h</td>
              <td>{volumeHeures(m.total_creneau_periode_minutes)} h</td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr className="finance-groupe-subtotal-row">
            <td colSpan={4} style={{ fontWeight: 700 }}>Total volume horaire</td>
            <td style={{ fontWeight: 700 }}>{totalRealise} h</td>
            <td style={{ fontWeight: 700 }}>{totalPlanifie} h</td>
          </tr>
        </tfoot>
      </table>
    </div>
  )
}
