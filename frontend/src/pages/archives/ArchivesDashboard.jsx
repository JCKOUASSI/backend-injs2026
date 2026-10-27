import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import api from '../../services/api'
import { useAuth } from '../../context/AuthContext'

const STAT_CARDS = [
  { key: 'modules', label: 'Modules archivés', icon: 'bi-journal-bookmark', color: '#1565c0' },
  { key: 'participants', label: 'Étudiants', icon: 'bi-people', color: '#125a99' },
  { key: 'formateurs', label: 'Enseignants', icon: 'bi-person-video3', color: '#6a1b9a' },
]

const DOC_CARDS = [
  {
    to: '/archives/listes-notes',
    label: 'Listes de note',
    desc: 'Relevés de notes et moyennes par module, catégorie et grade.',
    icon: 'bi-card-checklist',
    color: '#1565c0',
  },
  {
    to: '/archives/cahiers-appel',
    label: "Cahiers d'appel",
    desc: "Registres de présence (émargement) par séance, avec export PDF/Excel.",
    icon: 'bi-journal-check',
    color: '#125a99',
  },
]

const QUICK_LINKS = [
  { to: '/participants', label: 'Étudiants', icon: 'bi-people' },
  { to: '/statistiques', label: 'Statistiques', icon: 'bi-bar-chart-line' },
]

export default function ArchivesDashboard() {
  const { user } = useAuth()
  const [counts, setCounts] = useState({ modules: null, participants: null, formateurs: null })

  useEffect(() => {
    const ac = new AbortController()
    const opts = { signal: ac.signal }
    const load = async () => {
      try {
        const res = await api.get('/formations/archives/stats/', opts)
        setCounts({
          modules: res.data.modules ?? null,
          participants: res.data.participants ?? null,
          formateurs: res.data.formateurs ?? null,
        })
      } catch { /* ignore */ }
    }
    load()
    return () => ac.abort()
  }, [])

  const firstName = user?.first_name || user?.username || ''

  return (
    <div>
      {/* En-tête */}
      <div style={{
        background: 'linear-gradient(120deg, #001a33 0%, #0a2a4d 100%)',
        borderRadius: 18, padding: '1.75rem 2rem', color: '#fff', marginBottom: '1.5rem',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.4rem' }}>
          <i className="bi bi-archive" style={{ fontSize: '1.6rem' }}></i>
          <h1 style={{ margin: 0, fontWeight: 700, fontSize: '1.6rem' }}>Espace Archives</h1>
        </div>
        <p style={{ margin: 0, opacity: 0.9, fontSize: '0.95rem' }}>
          Bienvenue{firstName ? `, ${firstName}` : ''}. Consultez et exportez les documents pédagogiques archivés
          (listes de note, cahiers d'appel) classés par formation, catégorie et grade.
        </p>
      </div>

      {/* Statistiques */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem', marginBottom: '1.75rem' }}>
        {STAT_CARDS.map(c => (
          <div key={c.key} className="card" style={{ padding: '1.1rem 1.25rem', display: 'flex', alignItems: 'center', gap: '1rem' }}>
            <div style={{ width: 48, height: 48, borderRadius: 12, background: `${c.color}1a`, color: c.color, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '1.4rem' }}>
              <i className={`bi ${c.icon}`}></i>
            </div>
            <div>
              <div style={{ fontSize: '1.6rem', fontWeight: 800, lineHeight: 1 }}>
                {counts[c.key] == null ? '—' : counts[c.key].toLocaleString('fr-FR')}
              </div>
              <div style={{ fontSize: '0.82rem', color: 'var(--text-muted)', marginTop: 2 }}>{c.label}</div>
            </div>
          </div>
        ))}
      </div>

      {counts.modules === 0 && (
        <div className="card" style={{ padding: '1.25rem 1.5rem', marginBottom: '1.75rem', borderLeft: '4px solid #f5c10b', background: '#fffceb' }}>
          <p style={{ margin: 0, fontWeight: 600, color: '#92660e' }}>
            <i className="bi bi-info-circle me-2"></i>Aucun module archivé pour l'instant
          </p>
          <p style={{ margin: '0.5rem 0 0', fontSize: '0.9rem', color: '#78540f' }}>
            En tant qu'<strong>archiviste</strong>, vous consultez ici les modules déjà transférés aux archives.
            L'archivage est effectué par le <strong>secrétariat</strong> ou la <strong>direction</strong> depuis la page
            <strong> Modules</strong> (bouton orange « Archiver », avec 3 confirmations).
          </p>
        </div>
      )}

      {/* Documents d'archives */}
      <h2 style={{ fontSize: '1.1rem', fontWeight: 700, marginBottom: '0.9rem' }}>Documents d'archives</h2>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '1rem', marginBottom: '1.75rem' }}>
        {DOC_CARDS.map(c => (
          <Link
            key={c.to}
            to={c.to}
            className="card"
            style={{ padding: '1.4rem', textDecoration: 'none', color: 'inherit', display: 'flex', flexDirection: 'column', gap: '0.6rem', transition: 'box-shadow .15s, transform .15s' }}
            onMouseEnter={e => { e.currentTarget.style.boxShadow = '0 8px 26px rgba(0,0,0,0.10)'; e.currentTarget.style.transform = 'translateY(-3px)' }}
            onMouseLeave={e => { e.currentTarget.style.boxShadow = ''; e.currentTarget.style.transform = '' }}
          >
            <div style={{ width: 52, height: 52, borderRadius: 14, background: `${c.color}1a`, color: c.color, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '1.6rem' }}>
              <i className={`bi ${c.icon}`}></i>
            </div>
            <h3 style={{ margin: 0, fontSize: '1.05rem', fontWeight: 700 }}>{c.label}</h3>
            <p style={{ margin: 0, fontSize: '0.85rem', color: 'var(--text-muted)' }}>{c.desc}</p>
            <span style={{ marginTop: 'auto', color: c.color, fontWeight: 600, fontSize: '0.85rem' }}>
              Ouvrir <i className="bi bi-arrow-right ms-1"></i>
            </span>
          </Link>
        ))}
      </div>

      {/* Accès rapides */}
      <h2 style={{ fontSize: '1.1rem', fontWeight: 700, marginBottom: '0.9rem' }}>Accès rapides</h2>
      <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap' }}>
        {QUICK_LINKS.map(l => (
          <Link key={l.to} to={l.to} className="btn btn-outline-secondary btn-sm">
            <i className={`bi ${l.icon} me-1`}></i>{l.label}
          </Link>
        ))}
      </div>
    </div>
  )
}
