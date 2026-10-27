const CHART_COLORS = ['#4f46e5', '#e69700', '#0f4fbd', '#6a1b9a', '#1565c0', '#c62828', '#0f70ab', '#ffbf00']
const NOTE_COLORS = ['#ef5350', '#ffbf00', '#fde135', '#4895d9', '#0f4fbd']

export function ChartEmpty({ label = 'Aucune donnée' }) {
  return (
    <div style={{ textAlign: 'center', padding: '1.5rem', color: '#94a3b8', fontSize: '0.82rem' }}>
      <i className="bi bi-bar-chart" style={{ fontSize: '1.8rem', display: 'block', marginBottom: '0.4rem' }} />
      {label}
    </div>
  )
}

/** Graphique en disque (donut) */
export function DonutChart({ data, labelKey = 'label', valueKey = 'value', size = 160, colors = CHART_COLORS }) {
  if (!data?.length) return <ChartEmpty />
  const total = data.reduce((s, d) => s + (d[valueKey] || 0), 0)
  if (!total) return <ChartEmpty label="Aucune réponse" />

  const r = size / 2 - 18
  const cx = size / 2
  const cy = size / 2
  let angle = -Math.PI / 2
  const slices = data.map((d, i) => {
    const val = d[valueKey] || 0
    const arc = (val / total) * 2 * Math.PI
    const x1 = cx + r * Math.cos(angle)
    const y1 = cy + r * Math.sin(angle)
    angle += arc
    return {
      ...d,
      x1, y1,
      x2: cx + r * Math.cos(angle),
      y2: cy + r * Math.sin(angle),
      large: arc > Math.PI ? 1 : 0,
      color: d.color || colors[i % colors.length],
      val,
    }
  })

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', flexWrap: 'wrap' }}>
      <svg width={size} height={size} style={{ flexShrink: 0 }}>
        {slices.map((s, i) => (
          <path
            key={i}
            d={`M${cx} ${cy} L${s.x1} ${s.y1} A${r} ${r} 0 ${s.large} 1 ${s.x2} ${s.y2}Z`}
            fill={s.color}
            opacity={0.9}
            stroke="#fff"
            strokeWidth={2}
          />
        ))}
        <circle cx={cx} cy={cy} r={r * 0.55} fill="#fff" />
        <text x={cx} y={cy + 5} textAnchor="middle" fontSize={14} fontWeight={700} fill="#1e293b">{total}</text>
      </svg>
      <ul style={{ listStyle: 'none', padding: 0, margin: 0, fontSize: '0.76rem', maxWidth: 240 }}>
        {slices.map((s, i) => (
          <li key={i} style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', marginBottom: '0.3rem' }}>
            <span style={{ width: 9, height: 9, borderRadius: '50%', background: s.color, flexShrink: 0, display: 'inline-block' }} />
            <span style={{ color: '#475569', flex: 1 }}>{s[labelKey]}</span>
            <b style={{ color: '#1e293b' }}>{s.val}</b>
            <span style={{ color: '#94a3b8', fontSize: '0.7rem' }}>({Math.round((s.val / total) * 100)}%)</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

/** Histogramme vertical */
export function HistogramChart({ data, labelKey = 'label', valueKey = 'value', color = '#4f46e5', height = 150, unit = '' }) {
  if (!data?.length) return <ChartEmpty />
  const max = Math.max(...data.map(d => d[valueKey] || 0), 1)
  const barW = Math.max(22, Math.min(48, Math.floor(480 / data.length) - 10))
  const w = data.length * (barW + 10) + 40

  return (
    <div style={{ overflowX: 'auto' }}>
      <svg width={Math.max(w, 280)} height={height + 52} style={{ display: 'block' }}>
        {data.map((d, i) => {
          const v = d[valueKey] || 0
          const bH = v > 0 ? Math.max(6, Math.round((v / max) * (height - 24))) : 0
          const x = 20 + i * (barW + 10)
          const y = height - bH
          return (
            <g key={i}>
              <rect x={x} y={y} width={barW} height={bH || 2} rx={4} fill={d.color || color} opacity={v ? 0.88 : 0.35} />
              {v > 0 && (
                <text x={x + barW / 2} y={y - 4} textAnchor="middle" fontSize={10} fill="#1e293b" fontWeight={600}>
                  {v}{unit}
                </text>
              )}
              <text x={x + barW / 2} y={height + 14} textAnchor="middle" fontSize={9} fill="#64748b">
                {String(d[labelKey]).length > 10 ? `${String(d[labelKey]).slice(0, 9)}…` : d[labelKey]}
              </text>
            </g>
          )
        })}
      </svg>
    </div>
  )
}

/** Barres horizontales */
export function HorizontalBarChart({ data, labelKey = 'label', valueKey = 'value', color = 'var(--primary)', showPct = true }) {
  if (!data?.length) return <ChartEmpty />
  const max = Math.max(...data.map(d => d[valueKey] || 0), 1)
  const total = data.reduce((s, d) => s + (d[valueKey] || 0), 0)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.55rem' }}>
      {data.map((d, i) => {
        const v = d[valueKey] || 0
        const pct = total > 0 ? Math.round((v / total) * 100) : 0
        return (
          <div key={i}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem', marginBottom: '3px' }}>
              <span style={{ color: '#334155', fontWeight: 500, maxWidth: '70%', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={d[labelKey]}>
                {d[labelKey]}
              </span>
              <span style={{ fontWeight: 600, color: '#1e293b' }}>
                {v}{showPct && total > 0 && <span style={{ color: '#94a3b8', fontWeight: 400 }}> ({pct}%)</span>}
              </span>
            </div>
            <div style={{ height: 10, borderRadius: 5, background: '#eee', overflow: 'hidden' }}>
              <div style={{ width: `${(v / max) * 100}%`, height: '100%', background: d.color || color, borderRadius: 5, transition: 'width .4s' }} />
            </div>
          </div>
        )
      })}
    </div>
  )
}

/** Tendance temporelle (soumissions par jour) */
export function TrendChart({ data, valueKey = 'nb', color = '#0f4fbd', height = 140 }) {
  if (!data?.length) return <ChartEmpty label="Pas encore de tendance (soumissions)" />

  const max = Math.max(...data.map(d => d[valueKey] || 0), 1)
  const barW = Math.max(18, Math.min(36, Math.floor(520 / data.length) - 8))
  const w = data.length * (barW + 8) + 36

  const fmtDate = (iso) => {
    if (!iso) return ''
    const [, m, d] = iso.split('-')
    return `${d}/${m}`
  }

  return (
    <div style={{ overflowX: 'auto' }}>
      <svg width={Math.max(w, 300)} height={height + 48} style={{ display: 'block' }}>
        {data.map((d, i) => {
          const v = d[valueKey] || 0
          const bH = v > 0 ? Math.max(6, Math.round((v / max) * (height - 20))) : 0
          const x = 18 + i * (barW + 8)
          const y = height - bH
          return (
            <g key={i}>
              <rect x={x} y={y} width={barW} height={bH || 2} rx={3} fill={color} opacity={v ? 0.85 : 0.3} />
              {v > 0 && (
                <text x={x + barW / 2} y={y - 3} textAnchor="middle" fontSize={9} fill="#1e293b" fontWeight={600}>{v}</text>
              )}
              <text x={x + barW / 2} y={height + 16} textAnchor="middle" fontSize={8} fill="#64748b">
                {fmtDate(d.date)}
              </text>
            </g>
          )
        })}
      </svg>
    </div>
  )
}

/** Distribution des notes 1-5 en histogramme coloré */
export function NoteHistogram({ distribution, total }) {
  const data = [1, 2, 3, 4, 5].map(n => ({
    label: String(n),
    value: distribution?.[String(n)] || 0,
    color: NOTE_COLORS[n - 1],
  }))
  if (!total) return <ChartEmpty label="Aucune note" />
  return <HistogramChart data={data} color="#4f46e5" height={130} />
}

/** Distribution des notes 1-5 en disque */
export function NoteDonut({ distribution }) {
  const data = [1, 2, 3, 4, 5]
    .map(n => ({
      label: `Note ${n}`,
      value: distribution?.[String(n)] || 0,
      color: NOTE_COLORS[n - 1],
    }))
    .filter(d => d.value > 0)
  return <DonutChart data={data} />
}

export { NOTE_COLORS, CHART_COLORS }
