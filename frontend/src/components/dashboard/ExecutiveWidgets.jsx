import React from 'react'
import { Link } from 'react-router-dom'

/**
 * Composant « Activité récente ».
 *
 * Les entrées proviennent EXCLUSIVEMENT de l'appelant. Ce composant affichait
 * auparavant un jeu d'exemples (noms d'étudiants, montants, horodatages
 * inventés) qui se présentait comme l'activité réelle de l'établissement :
 * aucune donnée officielle ne doit être fabriquée côté interface.
 */
export function RecentActivityTimeline({
  title = 'Activité récente',
  items = [],
}) {
  return (
    <div className="glass-panel" style={{ height: '100%', display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
        <h3 style={{ fontSize: '0.92rem', fontWeight: 800, color: '#071B3A', margin: 0 }}>
          {title}
        </h3>
        <Link to="/scolarite" style={{ fontSize: '0.75rem', fontWeight: 700, color: '#1267D6', textDecoration: 'none' }}>
          Voir tout →
        </Link>
      </div>

      <div className="recent-activity-timeline">
        {items.length === 0 && (
          <p style={{ fontSize: '0.8rem', color: '#64748B', margin: 0 }}>
            Aucune activité enregistrée.
          </p>
        )}
        {items.map((item, idx) => (
          <div className="activity-timeline-row" key={idx} style={{ display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
            <span style={{ fontSize: '0.75rem', fontWeight: 600, color: '#94A3B8', minWidth: '38px' }}>
              {item.time}
            </span>
            <div style={{
              width: 24, height: 24, borderRadius: '6px',
              background: `${item.color}18`, color: item.color,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: '0.75rem', flexShrink: 0
            }}>
              <i className={`bi ${item.icon}`} />
            </div>
            <div style={{ flex: 1, minWidth: 0, color: '#1E293B', fontWeight: 500, fontSize: '0.79rem', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
              {item.text}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

/**
 * Composant « Situation financière »
 * Présente le taux de recouvrement sous forme de jauge circulaire et le bilan chiffré.
 */
export function FinancialSituationCard({
  title = 'Situation financière',
  // Aucune valeur par défaut : des montants « plausibles » codés en dur
  // s'affichaient comme la situation financière réelle de l'INJS.
  rate = null,
  recettes = null,
  paiements = null,
  impayes = null,
}) {
  const radius = 24
  const strokeWidth = 6
  const circumference = 2 * Math.PI * radius
  const affiche = (valeur) => (valeur === null || valeur === undefined || valeur === '' ? '—' : valeur)
  const taux = typeof rate === 'number' ? rate : null
  const strokeDashoffset = taux === null ? circumference : circumference - (taux / 100) * circumference

  return (
    <div className="glass-panel" style={{ height: '100%', display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '0.25rem' }}>
        <h3 style={{ fontSize: '0.92rem', fontWeight: 800, color: '#071B3A', margin: 0 }}>
          {title}
        </h3>
      </div>

      {/* Jauge et Taux de recouvrement */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.85rem', margin: '0.2rem 0' }}>
        <div style={{ width: 62, height: 62, position: 'relative', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
          <svg width="62" height="62" viewBox="0 0 62 62">
            <circle cx="31" cy="31" r={radius} fill="transparent" stroke="#E2E8F0" strokeWidth={strokeWidth} />
            <circle
              cx="31"
              cy="31"
              r={radius}
              fill="transparent"
              stroke="#1267D6"
              strokeWidth={strokeWidth}
              strokeDasharray={circumference}
              strokeDashoffset={strokeDashoffset}
              strokeLinecap="round"
              transform="rotate(-90 31 31)"
            />
          </svg>
          <div style={{ position: 'absolute', textAlign: 'center', lineHeight: 1 }}>
            <span style={{ fontSize: '0.95rem', fontWeight: 800, color: '#071B3A' }}>{taux === null ? '—' : `${taux}%`}</span>
          </div>
        </div>

        <div style={{ fontSize: '0.78rem', color: '#64748B', lineHeight: 1.25 }}>
          <div style={{ fontWeight: 600, color: '#0F172A', fontSize: '0.82rem' }}>Taux de recouvrement</div>
          <div>Frais de scolarité</div>
        </div>
      </div>

      {/* Lignes Recettes, Paiements, Impayés */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem', fontSize: '0.8rem', marginTop: '0.35rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span style={{ color: '#475569', display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
            <span style={{ color: '#35BDF5', fontSize: '0.75rem' }}>◆</span> Recettes
          </span>
          <strong style={{ color: '#0F172A', fontWeight: 700 }}>{affiche(recettes)}</strong>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span style={{ color: '#475569', display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
            <span style={{ color: '#16A36A', fontSize: '0.75rem' }}>◆</span> Paiements
          </span>
          <strong style={{ color: '#0F172A', fontWeight: 700 }}>{affiche(paiements)}</strong>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span style={{ color: '#475569', display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
            <span style={{ color: '#EF4444', fontSize: '0.75rem' }}>◆</span> Impayés
          </span>
          <strong style={{ color: '#DC2626', fontWeight: 700 }}>{affiche(impayes)}</strong>
        </div>
      </div>
    </div>
  )
}
