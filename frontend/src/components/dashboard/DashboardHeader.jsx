import React from 'react'
import { anneeAcademiqueAffichee } from '../../utils/anneeAcademique'

export default function DashboardHeader({
  title,
  subtitle,
  academicYear = anneeAcademiqueAffichee(),
  badgeText = 'Campus INJS Marcory',
  actions,
}) {
  return (
    <div className="dashboard-header">
      <div className="dashboard-title-group">
        <div className="d-flex align-items-center gap-2 mb-1">
          <span className="dashboard-header-badge">
            <i className="bi bi-mortarboard-fill"></i>
            {badgeText} · {academicYear}
          </span>
        </div>
        <h1>{title}</h1>
        {subtitle && <p className="dashboard-subtitle">{subtitle}</p>}
      </div>
      {actions && (
        <div className="d-flex align-items-center gap-2 flex-wrap">
          {actions}
        </div>
      )}
    </div>
  )
}
