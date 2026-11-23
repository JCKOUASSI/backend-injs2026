import React from 'react'

export function DashboardSkeleton() {
  return (
    <div className="dashboard-engine-wrapper">
      <div className="d-flex justify-content-between align-items-center mb-4">
        <div>
          <div className="bg-light rounded mb-2" style={{ width: 200, height: 24 }} />
          <div className="bg-light rounded" style={{ width: 350, height: 16 }} />
        </div>
      </div>
      <div className="kpi-grid-4 mb-4">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="glass-panel text-center py-4">
            <div className="spinner-border text-primary spinner-border-sm mb-2" />
            <div className="small text-muted">Chargement des métriques…</div>
          </div>
        ))}
      </div>
    </div>
  )
}

export function DashboardEmptyState({ message = 'Aucune donnée disponible pour cette période.' }) {
  return (
    <div className="glass-panel text-center py-5 my-3">
      <i className="bi bi-inbox fs-1 text-muted d-block mb-3" />
      <h3 className="h6 text-secondary mb-1">Ressource vide</h3>
      <p className="text-muted small mb-0">{message}</p>
    </div>
  )
}

export function DashboardErrorState({ message = 'Erreur lors du chargement des données.', onRetry }) {
  return (
    <div className="glass-panel border-danger text-center py-5 my-3">
      <i className="bi bi-exclamation-triangle-fill fs-1 text-danger d-block mb-3" />
      <h3 className="h6 text-danger mb-1">Impossible de charger les données</h3>
      <p className="text-muted small mb-3">{message}</p>
      {onRetry && (
        <button className="btn btn-outline-danger btn-sm" onClick={onRetry}>
          <i className="bi bi-arrow-clockwise me-1" />
          Réessayer
        </button>
      )}
    </div>
  )
}
