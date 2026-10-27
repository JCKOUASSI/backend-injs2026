import React from 'react'
import { Link } from 'react-router-dom'

export default function AlertPanel({ alerts = [] }) {
  // 5 alertes de référence de la maquette INJS
  const defaultAlerts = [
    {
      id: 'jurys',
      icon: 'bi-exclamation-triangle-fill',
      iconColor: '#EF4444',
      message: '4 jurys non finalisés',
      tag: 'Urgent',
      tagClass: 'plaquette-urgent',
      link: '/scolarite/jurys',
    },
    {
      id: 'dossiers',
      icon: 'bi-folder-x',
      iconColor: '#F59E0B',
      message: '18 dossiers incomplets',
      tag: 'Scolarité',
      tagClass: 'plaquette-scolarite',
      link: '/scolarite/inscriptions',
    },
    {
      id: 'groupes',
      icon: 'bi-people-fill',
      iconColor: '#2F80ED',
      message: '7 groupes sans enseignant',
      tag: 'Pédagogie',
      tagClass: 'plaquette-pedagogie',
      link: '/scolarite/groupes',
    },
    {
      id: 'cours',
      icon: 'bi-book-half',
      iconColor: '#64748B',
      message: '12 cours sans volume horaire',
      tag: 'Organisation',
      tagClass: 'plaquette-organisation',
      link: '/cours',
    },
    {
      id: 'validation',
      icon: 'bi-check-circle-fill',
      iconColor: '#10B981',
      message: '94% des dossiers validés',
      tag: 'Excellent',
      tagClass: 'plaquette-excellent',
      link: '/scolarite/admissions',
    },
  ]

  // Intégration des alertes dynamiques (passées par les tests ou l'API)
  const displayAlerts = alerts && alerts.length > 0
    ? alerts.map((al, idx) => ({
        id: `dyn-${idx}`,
        icon: al.icon || 'bi-info-circle-fill',
        iconColor: al.type === 'critical' ? '#EF4444' : al.type === 'warning' ? '#F59E0B' : '#2F80ED',
        message: al.message,
        tag: al.type === 'critical' ? 'Urgent' : al.type === 'warning' ? 'Attention' : 'Info',
        tagClass: al.type === 'critical' ? 'plaquette-urgent' : al.type === 'warning' ? 'plaquette-scolarite' : 'plaquette-pedagogie',
        link: al.link || '/scolarite',
      }))
    : defaultAlerts

  return (
    <div className="glass-panel" style={{ height: '100%', display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
        <h3 style={{ fontSize: '0.92rem', fontWeight: 800, color: '#0B1F3A', margin: 0, display: 'flex', alignItems: 'center', gap: '0.45rem' }}>
          <i className="bi bi-bell-fill" style={{ color: '#EF4444' }} />
          Alertes institutionnelles
        </h3>
        <Link to="/scolarite" style={{ fontSize: '0.75rem', fontWeight: 700, color: '#2F80ED', textDecoration: 'none' }}>
          Voir tout →
        </Link>
      </div>

      <div className="institutional-alerts-list">
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
