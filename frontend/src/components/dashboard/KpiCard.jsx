import React from 'react'

export default function KpiCard({
  title,
  value,
  subText,
  icon = 'bi-activity',
  trend,
  trendLabel = 'vs 2025 – 2026',
  trendPositive = true,
  onClick,
}) {
  return (
    <div
      className={`top-kpi-card ${onClick ? 'glass-panel-hover' : ''}`}
      onClick={onClick}
      style={onClick ? { cursor: 'pointer' } : undefined}
    >
      <div style={{ flex: 1 }}>
        <div className="top-kpi-label">{title}</div>
        <div className="top-kpi-value">{value ?? '—'}</div>
        {(trend || subText) && (
          <div style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap' }}>
            {trend && (
              <span className={`trend-pill ${trendPositive ? 'positive' : 'neutral'}`}>
                <i className={`bi ${trendPositive ? 'bi-arrow-up-short' : 'bi-arrow-down-short'}`} />
                {trend}
              </span>
            )}
            {trendLabel && <span className="trend-comparison">{trendLabel}</span>}
            {!trend && subText && <span className="trend-comparison">{subText}</span>}
          </div>
        )}
      </div>

      <div className="top-kpi-icon-wrapper">
        <i className={`bi ${icon}`}></i>
      </div>
    </div>
  )
}
