import React from 'react'
import { anneeAcademiquePrecedente } from '../../utils/anneeAcademique'

export default function KpiCard({
  title,
  value,
  subText,
  icon = 'bi-activity',
  trend,
  // La comparaison « vs <année précédente> » n'a de sens que si une variation
  // est réellement fournie : sinon on affichait une comparaison imaginaire
  // sous des indicateurs qui n'en avaient aucune.
  trendLabel,
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
            {trend && (
              <span className="trend-comparison">
                {trendLabel || `vs ${anneeAcademiquePrecedente(new Date(), true)}`}
              </span>
            )}
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
