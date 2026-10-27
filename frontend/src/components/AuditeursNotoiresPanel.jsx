/**
 * Absents notoires — inscrits sans pointage ou avec motif_notoire (définition CPFAE unifiée).
 * Données API : { total, inscrits, pct, liste[] }
 */

const TH = {
  padding: '0.45rem 0.55rem',
  background: '#fef2f2',
  borderBottom: '2px solid #fecaca',
  fontSize: '0.72rem',
  fontWeight: 700,
  color: '#991b1b',
  textAlign: 'left',
  whiteSpace: 'nowrap',
}

const TD = {
  padding: '0.4rem 0.55rem',
  borderBottom: '1px solid #f1f5f9',
  fontSize: '0.73rem',
  color: '#334155',
  verticalAlign: 'top',
}

export function filterAuditeursNotoires(data, opts = {}) {
  if (!data) return null
  const { secretariatId, grade, groupe } = opts
  let liste = data.liste || []
  if (secretariatId != null) {
    liste = liste.filter(r => String(r.secretariat_id) === String(secretariatId))
  }
  if (grade) {
    liste = liste.filter(r => (r.grade || '—') === grade)
  }
  if (groupe) {
    liste = liste.filter(r => (r.groupe || '—') === groupe)
  }
  const total = liste.length
  const inscrits = opts.inscrits ?? data.inscrits ?? 0
  const pct = inscrits > 0 ? Math.round((total / inscrits) * 1000) / 10 : 0
  return { ...data, total, inscrits, pct, liste }
}

export function AuditeursNotoiresKpiStrip({ data }) {
  if (!data) return null
  const total = data.total ?? 0
  const pct = Number(data.pct ?? 0).toFixed(1).replace('.', ',')
  const inscrits = data.inscrits ?? 0

  if (total === 0) {
    return (
      <div style={{
        display: 'flex', alignItems: 'center', gap: '0.65rem',
        padding: '0.65rem 0.85rem', marginBottom: '0.85rem',
        background: '#f0f6fd', border: '1px solid #bbd7f7', borderRadius: 8,
        fontSize: '0.8rem', color: '#0b478a',
      }}>
        <i className="bi bi-check-circle-fill" style={{ fontSize: '1.1rem' }}/>
        Aucun absent notoire — tous les inscrits ont au moins une présence sur un module démarré.
      </div>
    )
  }

  return (
    <div style={{
      display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '0.75rem 1.25rem',
      padding: '0.65rem 0.85rem', marginBottom: '0.85rem',
      background: 'linear-gradient(135deg, #fef2f2 0%, #fffaed 100%)',
      border: '1px solid #fecaca', borderRadius: 8,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem' }}>
        <i className="bi bi-person-x-fill" style={{ fontSize: '1.15rem', color: '#C62828' }}/>
        <span style={{ fontSize: '0.95rem', fontWeight: 800, color: '#C62828' }}>{total}</span>
        <span style={{ fontSize: '0.78rem', color: '#64748b' }}>
          absent{total > 1 ? 's' : ''} notoire{total > 1 ? 's' : ''}
        </span>
      </div>
      <div style={{ fontSize: '0.78rem', color: '#64748b' }}>
        <b style={{ color: '#C62828' }}>{pct}%</b> des inscrits ({inscrits})
      </div>
      <div style={{ fontSize: '0.72rem', color: '#94a3b8', marginLeft: 'auto' }}>
        Module démarré · aucune présence enregistrée
      </div>
    </div>
  )
}

export function AuditeursNotoiresPanel({ data, maxHeight = 360, compact = false }) {
  if (!data) {
    return (
      <div style={{ textAlign: 'center', padding: '1.5rem', color: '#94a3b8', fontSize: '0.82rem' }}>
        Données non disponibles.
      </div>
    )
  }

  const liste = data.liste || []

  if (liste.length === 0) {
    return (
      <div style={{ textAlign: 'center', padding: '1.75rem', color: '#2277C1', fontSize: '0.85rem' }}>
        <i className="bi bi-check-circle" style={{ fontSize: '2rem', display: 'block', marginBottom: '0.5rem' }}/>
        Aucun absent notoire sur ce périmètre.
      </div>
    )
  }

  const cols = compact
    ? [
        { key: 'idx', label: 'N°', width: 36 },
        { key: 'matricule', label: 'Matricule', width: 110 },
        { key: 'nom', label: 'Nom', width: 90 },
        { key: 'prenom', label: 'Prénom', width: 100 },
        { key: 'grade_groupe', label: 'Grade / Groupe', width: 100 },
        { key: 'secretariat', label: 'Secrétariat', width: 120 },
        { key: 'motif', label: 'Motif', width: 140 },
      ]
    : [
        { key: 'idx', label: 'N°', width: 36 },
        { key: 'matricule', label: 'Matricule', width: 110 },
        { key: 'nom', label: 'Nom', width: 90 },
        { key: 'prenom', label: 'Prénom', width: 100 },
        { key: 'sexe', label: 'Sexe', width: 55 },
        { key: 'categorie', label: 'Catégorie', width: 75 },
        { key: 'grade_groupe', label: 'Grade / Groupe', width: 100 },
        { key: 'vague', label: 'Vague', width: 60 },
        { key: 'secretariat', label: 'Secrétariat', width: 120 },
        { key: 'libelle_concours', label: 'Libellé concours', width: 150 },
        { key: 'contacts', label: 'Contacts', width: 120 },
        { key: 'motif', label: 'Motif / Obs.', width: 140 },
      ]

  const cellValue = (row, key, i) => {
    switch (key) {
      case 'idx': return i + 1
      case 'grade_groupe':
        return row.grade && row.groupe && row.grade !== '—' && row.groupe !== '—'
          ? `${row.grade} / ${row.groupe}`
          : row.grade !== '—' ? row.grade : row.groupe !== '—' ? row.groupe : '—'
      case 'contacts': {
        const parts = [row.telephone, row.email].filter(v => v && v !== '—')
        return parts.length ? parts.join(' · ') : '—'
      }
      case 'motif':
        return row.motif || '—'
      default:
        return row[key] ?? '—'
    }
  }

  return (
    <div>
      <div style={{ overflowX: 'auto', overflowY: 'auto', maxHeight }}>
        <table style={{ borderCollapse: 'collapse', minWidth: compact ? 680 : 1100, width: '100%' }}>
          <thead>
            <tr>
              {cols.map(c => (
                <th key={c.key} style={{ ...TH, minWidth: c.width }}>{c.label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {liste.map((row, i) => (
              <tr key={row.id ?? i} style={{ background: i % 2 === 0 ? '#fff' : '#fffbfb' }}>
                {cols.map(c => (
                  <td
                    key={c.key}
                    style={{
                      ...TD,
                      fontWeight: c.key === 'nom' ? 700 : 400,
                      fontFamily: c.key === 'matricule' ? 'monospace' : TD.fontFamily,
                      fontSize: c.key === 'matricule' ? '0.68rem' : TD.fontSize,
                      color: c.key === 'motif' && row.motif && row.motif !== '—' ? '#C62828' : TD.color,
                    }}
                  >
                    {cellValue(row, c.key, i)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div style={{ fontSize: '0.7rem', color: '#64748b', marginTop: '0.5rem', textAlign: 'right' }}>
        {liste.length} absent{liste.length > 1 ? 's' : ''} notoire{liste.length > 1 ? 's' : ''}
        {data.inscrits ? ` · ${Number(data.pct || 0).toFixed(1).replace('.', ',')}% des ${data.inscrits} inscrits` : ''}
      </div>
    </div>
  )
}
