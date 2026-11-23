import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import api from '../../services/api'
import { useAuth } from '../../context/AuthContext'
import '../../styles/archives.css'

const STAT_CARDS = [
  { key: 'modules', label: 'Modules archivés', icon: 'bi-journal-bookmark', color: '#104A8E' },
  { key: 'participants', label: 'Étudiants', icon: 'bi-people', color: '#104A8E' },
  { key: 'formateurs', label: 'Enseignants', icon: 'bi-person-video3', color: '#805AD5' },
]

const DOC_CARDS = [
  {
    to: '/archives/listes-notes',
    label: 'Listes de notes',
    desc: 'Relevés de notes et moyennes par module, catégorie et grade.',
    icon: 'bi-card-checklist',
    color: '#104A8E',
  },
  {
    to: '/archives/cahiers-appel',
    label: "Cahiers d'appel",
    desc: "Registres de présence (émargement) par séance, avec export PDF/Excel.",
    icon: 'bi-journal-check',
    color: '#104A8E',
  },
]

const QUICK_LINKS = [
  { to: '/participants', label: 'Étudiants', icon: 'bi-people' },
  { to: '/statistiques', label: 'Statistiques', icon: 'bi-bar-chart-line' },
  { to: '/administration/courrier', label: 'Administration — courrier & documents', icon: 'bi-envelope-paper' },
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
    <div className="archives-page">
      {/* En-tête */}
      <header className="archives-hero">
        <span className="archives-hero-badge"><i className="bi bi-archive"></i>Archives · Documents pédagogiques</span>
        <h1 className="archives-hero-title"><i className="bi bi-archive"></i>Espace Archives</h1>
        <p className="archives-hero-sub">
          Bienvenue{firstName ? `, ${firstName}` : ''}. Consultez et exportez les documents pédagogiques archivés
          (listes de notes, cahiers d'appel) classés par formation, catégorie et grade.
        </p>
      </header>

      {/* Statistiques */}
      <div className="archives-kpis">
        {STAT_CARDS.map(c => (
          <div key={c.key} className="archives-kpi" style={{ '--accent': c.color }}>
            <span className="archives-kpi-icon"><i className={`bi ${c.icon}`}></i></span>
            <div>
              <div className="archives-kpi-value">
                {counts[c.key] == null ? '—' : counts[c.key].toLocaleString('fr-FR')}
              </div>
              <div className="archives-kpi-label">{c.label}</div>
            </div>
          </div>
        ))}
      </div>

      {counts.modules === 0 && (
        <div className="archives-note-vide">
          <p><i className="bi bi-info-circle me-2"></i>Aucun module archivé pour l'instant</p>
          <p>
            En tant qu'<strong>archiviste</strong>, vous consultez ici les modules déjà transférés aux archives.
            L'archivage est effectué par le <strong>secrétariat</strong> ou la <strong>direction</strong> depuis la page
            <strong> Modules</strong> (bouton orange « Archiver », avec 3 confirmations).
          </p>
        </div>
      )}

      {/* Documents d'archives */}
      <h2 className="archives-section-title"><i className="bi bi-folder2-open"></i>Documents d'archives</h2>
      <div className="archives-docs">
        {DOC_CARDS.map(c => (
          <Link key={c.to} to={c.to} className="archives-doc-card" style={{ '--accent': c.color }}>
            <span className="archives-doc-icon"><i className={`bi ${c.icon}`}></i></span>
            <h3>{c.label}</h3>
            <p>{c.desc}</p>
            <span className="archives-doc-ouvrir">Ouvrir <i className="bi bi-arrow-right"></i></span>
          </Link>
        ))}
      </div>

      {/* Accès rapides */}
      <h2 className="archives-section-title"><i className="bi bi-lightning-charge"></i>Accès rapides</h2>
      <div className="archives-quick">
        {QUICK_LINKS.map(l => (
          <Link key={l.to} to={l.to} className="archives-quick-link">
            <i className={`bi ${l.icon}`}></i>{l.label}
          </Link>
        ))}
      </div>
    </div>
  )
}
