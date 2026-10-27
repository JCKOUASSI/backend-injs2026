/**
 * Point journalier — reproduction visuelle du modèle Excel INJS
 * (FAC — POINT JOURNALIER CAT A, une feuille par grade).
 */

const C = {
  header: '#EDB131',
  groupe: '#FBFDBB',
  total: '#F7FA82',
  sidebar: '#FFFF00',
  absence: '#EDB131',
  absenceJour: '#BDD7EE',
  border: '#000',
}

export function pjPct(n) {
  if (n == null || Number.isNaN(Number(n))) return '—'
  return `${(Number(n) * 100).toFixed(2).replace('.', ',')}%`
}

function td(extra = {}) {
  return {
    border: `1px solid ${C.border}`,
    textAlign: 'center',
    verticalAlign: 'middle',
    padding: '5px 6px',
    fontSize: '0.72rem',
    ...extra,
  }
}

function BlocCreneau({ label, bloc, nGroups }) {
  if (!bloc) return null
  const groupes = bloc.groupes || []
  const total = bloc.total || {}
  const pad = Math.max(0, nGroups - groupes.length)

  const dataRows = [
    { key: 'effectif', label: 'ÉFFECTIF', pct: false, bold: false, absence: false },
    { key: 'presents', label: 'PRÉSENTS', pct: false, bold: false, absence: false },
    { key: 'absents', label: 'ABSENTS', pct: false, bold: true, absence: false },
    { key: 'taux_presence', label: 'TAUX DE PRÉSENCE', pct: true, bold: true, absence: false },
    { key: 'taux_absence', label: "TAUX D'ABSENCE", pct: true, bold: true, absence: true },
  ]

  const renderVal = (val, row) => (row.pct ? pjPct(val) : String(val ?? 0))

  return (
    <>
      <tr>
        <td colSpan={1 + nGroups + 1} style={td({ background: C.header, fontWeight: 700, fontSize: '0.85rem' })}>
          {label}: {bloc.horaire || '—'}
        </td>
      </tr>
      <tr>
        <td colSpan={1 + nGroups} style={td({ height: 6, padding: 2 })} />
        <td rowSpan={2} style={td({ background: C.total })} />
      </tr>
      <tr>
        <td style={td({ fontWeight: 600, textAlign: 'left', minWidth: 115 })}>GROUPES</td>
        {groupes.map(g => (
          <td key={g.module_id || g.label} style={td({ background: C.groupe, fontWeight: 700 })}>
            {g.label}
          </td>
        ))}
        {Array.from({ length: pad }).map((_, i) => (
          <td key={`pg-${i}`} style={td({ background: C.groupe })} />
        ))}
      </tr>
      <tr>
        <td style={td({ fontWeight: 600, textAlign: 'left' })}>SALLES</td>
        {groupes.map(g => (
          <td key={`s-${g.module_id || g.label}`} style={td({ fontSize: '0.65rem', lineHeight: 1.25 })}>
            {g.salle || '—'}
          </td>
        ))}
        {Array.from({ length: pad }).map((_, i) => (
          <td key={`ps-${i}`} style={td()} />
        ))}
        <td style={td({ background: C.total })} />
      </tr>
      {dataRows.map(row => (
        <tr key={row.key}>
          <td style={td({
            fontWeight: 700,
            textAlign: 'left',
            background: row.absence ? C.absence : '#fff',
            color: row.absence ? '#fff' : '#000',
          })}>
            {row.label}
          </td>
          {groupes.map(g => (
            <td
              key={`${row.key}-${g.module_id || g.label}`}
              style={td({
                fontWeight: row.bold ? 700 : 400,
                background: row.absence ? C.absence : '#fff',
                color: row.absence ? '#fff' : '#000',
              })}
            >
              {renderVal(g[row.key], row)}
            </td>
          ))}
          {Array.from({ length: pad }).map((_, i) => (
            <td key={`pd-${row.key}-${i}`} style={td({ background: row.absence ? C.absence : '#fff' })} />
          ))}
          <td style={td({
            background: row.absence ? C.absence : C.total,
            fontWeight: 700,
            color: row.absence ? '#fff' : '#000',
          })}>
            {renderVal(total[row.key], row)}
          </td>
        </tr>
      ))}
    </>
  )
}

export function PointJournalierTableauCPFAE({ tb }) {
  if (!tb) return null

  const nGroups = Math.max(
    tb.matin?.groupes?.length || 0,
    tb.soir?.groupes?.length || 0,
    1,
  )
  const sidebar = (tb.vague_sidebar || 'SECONDE VAGUE').trim()
  const bodyRows = 22
  const dataCols = 1 + nGroups + 1 // libellés + groupes + TOTAL (hors bande jaune)
  const orgColSpan = Math.max(1, dataCols - 4) // après DATE · jour · mois · année

  return (
    <div style={{
      overflowX: 'auto',
      background: '#fff',
      borderRadius: 8,
      boxShadow: '0 1px 4px rgba(0,0,0,0.08)',
      border: `2px solid ${C.header}`,
    }}>
      <table style={{
        borderCollapse: 'collapse',
        width: '100%',
        minWidth: 130 + nGroups * 88 + 120,
        fontFamily: 'Calibri, Tahoma, Arial, sans-serif',
        tableLayout: 'fixed',
      }}>
        <colgroup>
          <col style={{ width: 115 }} />
          {Array.from({ length: nGroups }).map((_, i) => (
            <col key={i} style={{ minWidth: 72 }} />
          ))}
          <col style={{ width: 72 }} />
          <col style={{ width: 40 }} />
        </colgroup>
        <tbody>
          <tr>
            <td colSpan={1 + nGroups + 1} style={td({ background: C.header, fontWeight: 700, fontSize: '0.88rem', padding: '8px' })}>
              {tb.titre_ligne1}
            </td>
            <td rowSpan={bodyRows} style={td({
              background: C.sidebar,
              fontWeight: 700,
              fontSize: '1rem',
              writingMode: 'vertical-rl',
              transform: 'rotate(180deg)',
              letterSpacing: 2,
            })}>
              {sidebar}
            </td>
          </tr>
          <tr>
            <td style={td({ fontWeight: 700, fontSize: '0.82rem', textAlign: 'left' })}>DATE</td>
            <td style={td({ fontWeight: 700 })}>{tb.jour}</td>
            <td style={td({ fontWeight: 700 })}>{tb.mois_libelle}</td>
            <td style={td({ fontWeight: 700 })}>{tb.annee}</td>
            <td
              colSpan={orgColSpan}
              style={td({
                fontWeight: 700,
                fontSize: '0.72rem',
                lineHeight: 1.25,
                textAlign: 'center',
                whiteSpace: 'normal',
              })}
            >
              {tb.organisme}
            </td>
          </tr>
          <BlocCreneau label="MATIN" bloc={tb.matin} nGroups={nGroups} />
          <tr><td colSpan={1 + nGroups + 1} style={{ height: 4, border: 'none' }} /></tr>
          <BlocCreneau label="SOIR" bloc={tb.soir} nGroups={nGroups} />
          <tr>
            <td colSpan={2} style={td({ fontWeight: 700, textAlign: 'left', padding: '10px 6px' })}>
              Taux de présence du jour
            </td>
            <td colSpan={2} style={td({ background: C.header, fontWeight: 700, fontSize: '1.05rem' })}>
              {pjPct(tb.taux_presence_jour)}
            </td>
            <td colSpan={2} style={td({ fontWeight: 700, textAlign: 'left' })}>
              Taux d&apos;absence du jour
            </td>
            <td colSpan={Math.max(1, nGroups - 2)} style={td({ background: C.absenceJour, fontWeight: 700, fontSize: '1.05rem' })}>
              {pjPct(tb.taux_absence_jour)}
            </td>
            <td style={td()} />
          </tr>
        </tbody>
      </table>
    </div>
  )
}

export default PointJournalierTableauCPFAE
