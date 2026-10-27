import React from 'react'

/**
 * Graphique de lignes courbes lissées (Spline Area Chart)
 * pour « Évolution des effectifs » (6 ans : 2021 à 2026).
 */
export function VectorSplineAreaChart({
  title = 'Évolution des effectifs',
  period = '6 ans',
}) {
  const years = ['2021', '2022', '2023', '2024', '2025', '2026']
  const series = [
    {
      name: 'Étudiants',
      color: '#2F80ED',
      data: [820, 950, 1040, 1120, 1180, 1248],
    },
    {
      name: 'Candidats',
      color: '#38BDF8',
      data: [1450, 1680, 1890, 2050, 2200, 2340],
    },
    {
      name: 'Enseignants',
      color: '#06B6D4',
      data: [142, 155, 164, 172, 179, 186],
    },
  ]

  // Dimensions SVG
  const width = 480
  const height = 180
  const paddingX = 40
  const paddingY = 25
  const maxY = 2500

  const getCoordinates = (val, idx) => {
    const x = paddingX + idx * ((width - paddingX * 2) / (years.length - 1))
    const y = height - paddingY - (val / maxY) * (height - paddingY * 2)
    return { x, y }
  }

  // Génération d'une courbe de Bézier cubique douce
  const buildSmoothPath = (data) => {
    const points = data.map((val, idx) => getCoordinates(val, idx))
    if (!points.length) return ''
    let d = `M ${points[0].x} ${points[0].y}`
    for (let i = 0; i < points.length - 1; i++) {
      const p0 = points[i === 0 ? 0 : i - 1]
      const p1 = points[i]
      const p2 = points[i + 1]
      const p3 = points[i + 2 < points.length ? i + 2 : i + 1]
      const cp1x = p1.x + (p2.x - p0.x) / 6
      const cp1y = p1.y + (p2.y - p0.y) / 6
      const cp2x = p2.x - (p3.x - p1.x) / 6
      const cp2y = p2.y - (p3.y - p1.y) / 6
      d += ` C ${cp1x} ${cp1y}, ${cp2x} ${cp2y}, ${p2.x} ${p2.y}`
    }
    return d
  }

  return (
    <div className="glass-panel" style={{ height: '100%', display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
        <div>
          <h3 style={{ fontSize: '0.95rem', fontWeight: 800, color: '#0B1F3A', margin: 0 }}>
            {title}
          </h3>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          {/* Légende */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem', fontSize: '0.72rem', fontWeight: 600 }}>
            {series.map((s) => (
              <span key={s.name} style={{ display: 'flex', alignItems: 'center', gap: '0.3rem', color: '#475569' }}>
                <span style={{ width: 8, height: 8, borderRadius: '50%', backgroundColor: s.color }} />
                {s.name}
              </span>
            ))}
          </div>
          {/* Sélecteur de période */}
          <span className="btn-premium-glass" style={{ padding: '0.2rem 0.6rem', fontSize: '0.72rem' }}>
            {period} <i className="bi bi-chevron-down" style={{ fontSize: '0.6rem' }} />
          </span>
        </div>
      </div>

      <div style={{ width: '100%', height: '140px' }}>
        <svg viewBox={`0 0 ${width} ${height}`} width="100%" height="100%" style={{ overflow: 'visible' }}>
          {/* Lignes de grille horizontales */}
          {[0, 500, 1000, 1500, 2000, 2500].map((gridVal) => {
            const y = height - paddingY - (gridVal / maxY) * (height - paddingY * 2)
            return (
              <g key={gridVal}>
                <line x1={paddingX} y1={y} x2={width - paddingX} y2={y} stroke="#E2E8F0" strokeWidth="1" strokeDasharray="3 3" />
                <text x={paddingX - 8} y={y + 3} textAnchor="end" fontSize="9" fill="#94A3B8" fontWeight="600">
                  {gridVal === 0 ? '0' : gridVal >= 1000 ? `${gridVal / 1000}k` : gridVal}
                </text>
              </g>
            )
          })}

          {/* Années sur l'axe X */}
          {years.map((yr, idx) => {
            const x = paddingX + idx * ((width - paddingX * 2) / (years.length - 1))
            return (
              <text key={yr} x={x} y={height - 6} textAnchor="middle" fontSize="10" fill="#64748B" fontWeight="600">
                {yr}
              </text>
            )
          })}

          {/* Courbes des séries */}
          {series.map((s) => {
            const path = buildSmoothPath(s.data)
            return (
              <g key={s.name}>
                <path
                  d={path}
                  fill="none"
                  stroke={s.color}
                  strokeWidth="2.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
                {s.data.map((val, idx) => {
                  const pt = getCoordinates(val, idx)
                  return (
                    <circle
                      key={idx}
                      cx={pt.x}
                      cy={pt.y}
                      r="3.5"
                      fill="#FFFFFF"
                      stroke={s.color}
                      strokeWidth="2"
                    >
                      <title>{`${s.name} (${years[idx]}): ${val}`}</title>
                    </circle>
                  )
                })}
              </g>
            )
          })}
        </svg>
      </div>
    </div>
  )
}

/**
 * Donut SVG avec total centré et légende détaillée
 */
export function VectorDonutChart({
  title,
  data = [],
  totalLabel = 'Étudiants',
  centerTotal,
}) {
  const total = centerTotal ?? data.reduce((acc, d) => acc + d.value, 0)
  let cumulative = 0

  return (
    <div className="glass-panel" style={{ height: '100%', display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
      {title && (
        <h3 style={{ fontSize: '0.92rem', fontWeight: 800, color: '#0B1F3A', margin: '0 0 0.75rem 0' }}>
          {title}
        </h3>
      )}

      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '1rem', flex: 1 }}>
        <div style={{ width: 110, height: 110, position: 'relative', flexShrink: 0 }}>
          <svg viewBox="0 0 100 100" width="100%" height="100%">
            <circle cx="50" cy="50" r="38" fill="transparent" stroke="#E2E8F0" strokeWidth="15" />
            {data.map((slice, idx) => {
              if (total === 0) return null
              const pct = slice.value / total
              const strokeDasharray = `${pct * 238.7} 238.7`
              const strokeDashoffset = -cumulative * 238.7
              cumulative += pct
              return (
                <circle
                  key={idx}
                  cx="50"
                  cy="50"
                  r="38"
                  fill="transparent"
                  stroke={slice.color || '#2F80ED'}
                  strokeWidth="15"
                  strokeDasharray={strokeDasharray}
                  strokeDashoffset={strokeDashoffset}
                  transform="rotate(-90 50 50)"
                  strokeLinecap="round"
                />
              )
            })}
            <text x="50" y="47" textAnchor="middle" fontSize="13" fontWeight="800" fill="#0B1F3A">
              {typeof total === 'number' ? total.toLocaleString('fr-FR') : total}
            </text>
            <text x="50" y="61" textAnchor="middle" fontSize="8" fill="#64748B" fontWeight="600">
              {totalLabel}
            </text>
          </svg>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem', flex: 1, fontSize: '0.78rem' }}>
          {data.map((item, idx) => (
            <div key={idx} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '0.5rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                <span
                  style={{
                    width: 8,
                    height: 8,
                    borderRadius: '50%',
                    backgroundColor: item.color || '#2F80ED',
                    flexShrink: 0,
                  }}
                />
                <span style={{ color: '#475569', fontWeight: 500 }}>{item.label}</span>
              </div>
              <strong style={{ color: '#0F172A' }}>{item.display ?? item.value}</strong>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

/**
 * Jauge radiale circulaire pour taux de réussite, d'abandon, diplomation
 */
export function RadialGaugeCard({
  title,
  value = 75,
  color = '#10B981',
  trend = '+5%',
  trendComparison = 'vs 2025',
  trendPositive = true,
}) {
  const radius = 34
  const strokeWidth = 9
  const circumference = 2 * Math.PI * radius
  const strokeDashoffset = circumference - (value / 100) * circumference

  return (
    <div className="glass-panel radial-gauge-card" style={{ height: '100%', justifyContent: 'space-between' }}>
      <div className="gauge-title">{title}</div>

      <div className="gauge-svg-container">
        <svg width="86" height="86" viewBox="0 0 86 86">
          <circle
            cx="43"
            cy="43"
            r={radius}
            fill="transparent"
            stroke="#E2E8F0"
            strokeWidth={strokeWidth}
          />
          <circle
            cx="43"
            cy="43"
            r={radius}
            fill="transparent"
            stroke={color}
            strokeWidth={strokeWidth}
            strokeDasharray={circumference}
            strokeDashoffset={strokeDashoffset}
            strokeLinecap="round"
            transform="rotate(-90 43 43)"
            style={{ transition: 'stroke-dashoffset 0.8s ease' }}
          />
        </svg>
        <span className="gauge-pct-text">{value}%</span>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.25rem', fontSize: '0.72rem', marginTop: '0.25rem' }}>
        <span className={`trend-pill ${trendPositive ? 'positive' : 'neutral'}`}>
          <i className={`bi ${trendPositive ? 'bi-arrow-up-short' : 'bi-arrow-down-short'}`} />
          {trend}
        </span>
        <span className="trend-comparison" style={{ color: '#10B981', fontWeight: 600 }}>✓ {trendComparison}</span>
      </div>
    </div>
  )
}

/**
 * Diagramme en barres groupées pour la charge d'enseignement (CM, TD, TP)
 */
export function TeachingLoadBarChart({
  title = "Charge d'enseignement",
}) {
  const categories = ['Licence', 'Master', 'Doctorat']
  const series = [
    { name: 'CM', color: '#0B1F3A', values: [340, 210, 85] },
    { name: 'TD', color: '#2F80ED', values: [290, 175, 45] },
    { name: 'TP', color: '#38BDF8', values: [220, 130, 20] },
  ]
  const maxVal = 400

  return (
    <div className="glass-panel" style={{ height: '100%', display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
        <h3 style={{ fontSize: '0.92rem', fontWeight: 800, color: '#0B1F3A', margin: 0 }}>
          {title}
        </h3>
        <div style={{ display: 'flex', gap: '0.65rem', fontSize: '0.72rem', fontWeight: 600 }}>
          {series.map((s) => (
            <span key={s.name} style={{ display: 'flex', alignItems: 'center', gap: '0.3rem', color: '#475569' }}>
              <span style={{ width: 8, height: 8, borderRadius: 2, backgroundColor: s.color }} />
              {s.name}
            </span>
          ))}
        </div>
      </div>

      <div style={{ width: '100%', height: '120px' }}>
        <svg viewBox="0 0 320 120" width="100%" height="100%">
          {/* Lignes horizontales */}
          {[0, 100, 200, 300, 400].map((val) => {
            const y = 95 - (val / maxVal) * 85
            return (
              <g key={val}>
                <line x1="30" y1={y} x2="310" y2={y} stroke="#F1F5F9" strokeWidth="1" />
                <text x="24" y={y + 3} textAnchor="end" fontSize="8" fill="#94A3B8">
                  {val}
                </text>
              </g>
            )
          })}

          {/* Groupes de barres */}
          {categories.map((cat, catIdx) => {
            const groupX = 55 + catIdx * 90
            return (
              <g key={cat}>
                {series.map((s, sIdx) => {
                  const barW = 12
                  const barX = groupX + sIdx * 14
                  const h = (s.values[catIdx] / maxVal) * 85
                  const y = 95 - h
                  return (
                    <rect
                      key={s.name}
                      x={barX}
                      y={y}
                      width={barW}
                      height={Math.max(2, h)}
                      fill={s.color}
                      rx="3"
                    >
                      <title>{`${cat} - ${s.name}: ${s.values[catIdx]}h`}</title>
                    </rect>
                  )
                })}
                <text x={groupX + 21} y="112" textAnchor="middle" fontSize="9" fontWeight="600" fill="#64748B">
                  {cat}
                </text>
              </g>
            )
          })}
        </svg>
      </div>
    </div>
  )
}

/**
 * Graphique en barres classique (conservé pour rétro-compatibilité)
 */
export function VectorBarChart({
  title,
  subtitle,
  data = [],
  height = 180,
  barColor = '#2F80ED',
}) {
  const maxVal = Math.max(...data.map((d) => d.value), 5)

  return (
    <div className="glass-panel" style={{ height: '100%' }}>
      {title && (
        <div style={{ marginBottom: '0.75rem' }}>
          <h3 style={{ fontSize: '0.92rem', fontWeight: 800, color: '#0B1F3A', margin: 0 }}>
            {title}
          </h3>
          {subtitle && <span style={{ fontSize: '0.75rem', color: '#64748B' }}>{subtitle}</span>}
        </div>
      )}
      <div style={{ width: '100%', height }}>
        <svg viewBox="0 0 500 180" width="100%" height="100%" style={{ overflow: 'visible' }}>
          <line x1="40" y1="140" x2="480" y2="140" stroke="#CBD5E1" strokeWidth="1" />
          {data.map((item, idx) => {
            const barWidth = Math.min(40, 360 / Math.max(data.length, 1))
            const spacing = 400 / Math.max(data.length, 1)
            const x = 60 + idx * spacing
            const h = (item.value / maxVal) * 110
            const y = 140 - h
            return (
              <g key={idx}>
                <rect
                  x={x}
                  y={y}
                  width={barWidth}
                  height={Math.max(2, h)}
                  fill={item.color || barColor}
                  rx="4"
                />
                <text x={x + barWidth / 2} y={Math.max(15, y - 6)} textAnchor="middle" fontSize="11" fontWeight="700" fill="#0B1F3A">
                  {item.value}
                </text>
                <text x={x + barWidth / 2} y="160" textAnchor="middle" fontSize="11" fill="#64748B" fontWeight="600">
                  {item.label}
                </text>
              </g>
            )
          })}
        </svg>
      </div>
    </div>
  )
}
