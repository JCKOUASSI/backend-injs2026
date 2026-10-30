import React from 'react'
import { Link } from 'react-router-dom'

export default function AlertPanel({ alerts = [] }) {
  // Aucune alerte par défaut : cet écran affichait cinq alertes inventées
  // (« 4 jurys non finalisés », « 18 dossiers incomplets », « 94 % des dossiers
  // validés ») présentées comme l'état réel de l'établissement. Les alertes
  // proviennent désormais uniquement de l'API.
  const displayAlerts = (alerts || []).map((al, idx) => ({
    id: `dyn-${idx}`,
    icon: al.icon || 'bi-info-circle-fill',
    iconColor: al.type === 'critical' ? '#EF4444' : al.type === 'warning' ? '#F59E0B' : '#1267D6',
    message: al.message,
    tag: al.type === 'critical' ? 'Urgent' : al.type === 'warning' ? 'Attention' : 'Info',
    tagClass: al.type === 'critical' ? 'plaquette-urgent' : al.type === 'warning' ? 'plaquette-scolarite' : 'plaquette-pedagogie',
    link: al.link || '/scolarite',
  }))

  return (
    <div className="glass-panel" style={{ height: '100%', display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
        <h3 style={{ fontSize: '0.92rem', fontWeight: 800, color: '#071B3A', margin: 0, display: 'flex', alignItems: 'center', gap: '0.45rem' }}>
          <i className="bi bi-bell-fill" style={{ color: '#EF4444' }} />
          Alertes institutionnelles
        </h3>
        <Link to="/scolarite" style={{ fontSize: '0.75rem', fontWeight: 700, color: '#1267D6', textDecoration: 'none' }}>
          Voir tout →
        </Link>
      </div>

      <div className="institutional-alerts-list">
        {displayAlerts.length === 0 && (
          <p style={{ fontSize: '0.8rem', color: '#64748B', margin: 0 }}>
            Aucune alerte en cours.
          </p>
        )}
        {displayAlerts.map((al) => {
          const itemContent = (
            <div className="institutional-alert-item" key={al.id}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', overflow: 'hidden' }}>
                <i className={`bi ${al.icon}`} style={{ color: al.iconColor, fontSize: '0.9rem', flexShrink: 0 }} />
                <span style={{ color: '#1E293B', whiteSpace: 'nowrap', textOverflow: 'ellipsis', overflow: 'hidden' }}>
                  {al.message}
                </span>
              </div>
              <span className={`plaquette ${al.tagClass}`} style={{ flexShrink: 0 }}>
                {al.tag}
              </span>
            </div>
          )

          return al.link ? (
            <Link key={al.id} to={al.link} style={{ textDecoration: 'none' }}>
              {itemContent}
            </Link>
          ) : (
            <div key={al.id}>{itemContent}</div>
          )
        })}
      </div>
    </div>
  )
}
