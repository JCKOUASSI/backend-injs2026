import React from 'react'
import { Link } from 'react-router-dom'

export default function QuickActions({ actions = [], title = 'Actions Rapides de Gouvernance' }) {
  if (!actions.length) return null

  return (
    <div className="quick-actions-card">
      {title && (
        <div className="quick-actions-header">
          <i className="bi bi-lightning-charge-fill" style={{ color: '#F59E0B' }}></i>
          <span>{title}</span>
        </div>
      )}
      <div className="quick-actions-row">
        {actions.map((act, idx) => (
          <Link
            key={idx}
            to={act.to}
            className={`quick-action-link btn-quick-action ${idx === 0 ? 'btn-quick-action-primary' : 'btn-quick-action-secondary'}`}
            data-testid={`quick-action-${idx}`}
          >
            {act.icon && (
              <span className="quick-action-icon-wrap">
                <i className={`bi ${act.icon}`}></i>
              </span>
            )}
            <span className="quick-action-label">{act.label}</span>
          </Link>
        ))}
      </div>
    </div>
  )
}
