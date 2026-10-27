import React from 'react'
import { Link } from 'react-router-dom'

/**
 * Composant « Activité récente »
 * Conforme à la maquette INJS : flux avec horodatage, icône de catégorie et intitulé précis.
 */
export function RecentActivityTimeline({
  title = 'Activité récente',
  items = [
    { time: '10:42', text: 'Nouvelle inscription – Licence STAPS (Étudiant : M. Sarr)', icon: 'bi-person-plus-fill', color: '#2F80ED' },
    { time: '10:31', text: 'Note publiée – UE Théorie du Sport (Groupe : L2-A)', icon: 'bi-clipboard-check-fill', color: '#10B981' },
    { time: '10:17', text: 'Groupe créé – L1 STAPS (Responsable : Dr. Keita)', icon: 'bi-people-fill', color: '#38BDF8' },
    { time: '09:58', text: 'Jury validé – Master Management du Sport (PV en cours)', icon: 'bi-award-fill', color: '#8B5CF6' },
    { time: '09:44', text: 'Paiement enregistré – 125 000 FCFA (Étudiant : A. Traoré)', icon: 'bi-credit-card-2-front-fill', color: '#F59E0B' },
  ],
}) {
  return (
    <div className="glass-panel" style={{ height: '100%', display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
        <h3 style={{ fontSize: '0.92rem', fontWeight: 800, color: '#0B1F3A', margin: 0 }}>
          {title}
        </h3>
        <Link to="/scolarite" style={{ fontSize: '0.75rem', fontWeight: 700, color: '#2F80ED', textDecoration: 'none' }}>
          Voir tout →
        </Link>
      </div>

      <div className="recent-activity-timeline">
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
  rate = 87,
  recettes = '248 500 000 FCFA',
  paiements = '215 780 000 FCFA',
  impayes = '32 720 000 FCFA',
}) {
  const radius = 24
  const strokeWidth = 6
  const circumference = 2 * Math.PI * radius
  const strokeDashoffset = circumference - (rate / 100) * circumference

  return (
    <div className="glass-panel" style={{ height: '100%', display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '0.25rem' }}>
        <h3 style={{ fontSize: '0.92rem', fontWeight: 800, color: '#0B1F3A', margin: 0 }}>
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
              stroke="#2F80ED"
              strokeWidth={strokeWidth}
              strokeDasharray={circumference}
              strokeDashoffset={strokeDashoffset}
              strokeLinecap="round"
              transform="rotate(-90 31 31)"
            />
          </svg>
          <div style={{ position: 'absolute', textAlign: 'center', lineHeight: 1 }}>
            <span style={{ fontSize: '0.95rem', fontWeight: 800, color: '#0B1F3A' }}>{rate}%</span>
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
            <span style={{ color: '#38BDF8', fontSize: '0.75rem' }}>◆</span> Recettes
          </span>
          <strong style={{ color: '#0F172A', fontWeight: 700 }}>{recettes}</strong>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span style={{ color: '#475569', display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
            <span style={{ color: '#10B981', fontSize: '0.75rem' }}>◆</span> Paiements
          </span>
          <strong style={{ color: '#0F172A', fontWeight: 700 }}>{paiements}</strong>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span style={{ color: '#475569', display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
            <span style={{ color: '#EF4444', fontSize: '0.75rem' }}>◆</span> Impayés
          </span>
          <strong style={{ color: '#DC2626', fontWeight: 700 }}>{impayes}</strong>
        </div>
      </div>
    </div>
  )
}
