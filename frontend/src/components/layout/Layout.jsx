import { Fragment, useState, useEffect } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../../context/AuthContext'
import { hasAppRole, peut, getUserRoles } from '../../utils/roles'
import { LIBELLES_ROLES } from '../../menu/arborescence'
import AppNotificationsBell from '../AppNotificationsBell'
import Sidebar from './Sidebar'
import { FINANCE_MODULE_ROLES } from '../../utils/roles'
import avatarDirector from '../../assets/avatar-director.jpg'

/**
 * Coquille de l'application : barre latérale RBAC + barre supérieure Glassmorphism.
 *
 * Conforme au design institutionnel INJS Marcory :
 * - Gestion du masquage/déploiement de la sidebar (bureau et mobile/tablette)
 * - Barre de recherche globale (« Rechercher un étudiant, une formation, un cours... »)
 * - Sélecteur d'année académique (« 2026 – 2027 »)
 * - Cloche de notification temps réel
 * - Plaquette utilisateur avec avatar exécutif, nom complet et badge de rôle
 */
export default function Layout({ children, breadcrumb }) {
  const { user } = useAuth()
  const navigate = useNavigate()
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [isMobile, setIsMobile] = useState(() =>
    typeof window !== 'undefined' ? window.innerWidth <= 992 : false
  )
  const [searchTerm, setSearchTerm] = useState('')

  useEffect(() => {
    const handleResize = () => {
      const mobile = window.innerWidth <= 992
      setIsMobile(mobile)
      if (!mobile) {
        setSidebarOpen(false)
      }
    }
    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [])

  const isSidebarHidden = isMobile ? !sidebarOpen : sidebarCollapsed

  const toggleSidebar = () => {
    if (isMobile) {
      setSidebarOpen((prev) => !prev)
    } else {
      setSidebarCollapsed((prev) => !prev)
    }
  }

  const handleSidebarClose = () => {
    if (isMobile) {
      setSidebarOpen(false)
    } else {
      setSidebarCollapsed(true)
    }
  }

  // Gardes de notification
  const isDirection = hasAppRole(user, ['DIRECTION'])
  const isChaineAbsences = hasAppRole(user, ['DIRECTION', 'SECRETARIAT', 'CHEF_SECRETARIAT'])
  const canViewStatistiques = peut(user, 'statistiques', 'voir')
  const canViewFinanceNotifications = hasAppRole(user, FINANCE_MODULE_ROLES)
    && !hasAppRole(user, ['ARCHIVE'])
  const showAppNotifications = isDirection || canViewStatistiques || canViewFinanceNotifications

  const userInitials = `${(user?.first_name || '')[0] || ''}${(user?.last_name || '')[0] || ''}`.toUpperCase() || 'MD'
  
  // Nom d'affichage aligné sur la maquette pour la Direction ou nom réel
  const isUserDirection = user?.role === 'DIRECTION' || !user?.role
  const displayName = isUserDirection && (!user?.first_name || user?.username === 'admin')
    ? 'Dr. Mamadou Diallo'
    : (user?.get_full_name ? user.get_full_name() : `${user?.first_name || ''} ${user?.last_name || ''}`.trim() || user?.username || 'Dr. Mamadou Diallo')

  const roleLabel = getUserRoles(user)
    .map((r) => LIBELLES_ROLES[r] || r)
    .join(', ') || (isUserDirection ? 'Direction' : user?.role || 'Direction')

  const handleSearchSubmit = (e) => {
    e.preventDefault()
    if (!searchTerm.trim()) return
    const term = searchTerm.trim().toLowerCase()
    if (term.includes('formation') || term.includes('staps') || term.includes('licence') || term.includes('master')) {
      navigate('/formations')
    } else if (term.includes('cours') || term.includes('module')) {
      navigate('/cours')
    } else {
      navigate('/participants')
    }
  }

  return (
    <div className={`app-container${sidebarCollapsed ? ' sidebar-collapsed' : ''}`}>
      {/* Fond dépoli pour mobile lorsque la barre est ouverte */}
      {isMobile && sidebarOpen && (
        <div
          className="sidebar-backdrop"
          onClick={() => setSidebarOpen(false)}
          data-testid="sidebar-backdrop"
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(6, 21, 45, 0.45)',
            backdropFilter: 'blur(4px)',
            WebkitBackdropFilter: 'blur(4px)',
            zIndex: 90,
            display: 'block',
          }}
        />
      )}

      <Sidebar
        open={sidebarOpen}
        onClose={handleSidebarClose}
      />

      <main className="main-content">
        <header className="top-bar" style={{
          background: 'rgba(237, 244, 251, 0.82)',
          backdropFilter: 'blur(16px)',
          WebkitBackdropFilter: 'blur(16px)',
          borderBottom: '1px solid rgba(215, 227, 240, 0.75)',
          padding: '0.65rem 1.5rem',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          position: 'sticky',
          top: 0,
          zIndex: 95,
          gap: '1rem',
          boxShadow: '0 4px 20px -4px rgba(11, 31, 58, 0.03)',
        }}>
          {/* Côté Gauche : Bouton repli + Barre de recherche globale */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.85rem', flex: '1 1 auto', maxWidth: '580px' }}>
            <button
              type="button"
              className="btn btn-sm btn-outline-secondary sidebar-toggle"
              onClick={toggleSidebar}
              data-testid="sidebar-toggle"
              style={{
                borderRadius: '10px',
                border: '1px solid #E2E8F0',
                background: '#FFFFFF',
                color: '#475569',
                padding: '0.45rem 0.65rem',
                cursor: 'pointer',
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                transition: 'all 0.2s ease',
              }}
              title={isSidebarHidden ? 'Afficher le menu latéral' : 'Masquer le menu latéral'}
              aria-label={isSidebarHidden ? 'Afficher le menu latéral' : 'Masquer le menu latéral'}
              aria-expanded={!isSidebarHidden}
              aria-controls="sidebar"
            >
              <i className={`bi ${isSidebarHidden ? 'bi-layout-sidebar' : 'bi-layout-sidebar-inset'}`}></i>
            </button>

            {/* Barre de recherche avec pilule dépolie */}
            <form onSubmit={handleSearchSubmit} style={{ position: 'relative', width: '100%', maxWidth: '420px' }}>
              <i
                className="bi bi-search"
                style={{
                  position: 'absolute',
                  left: '14px',
                  top: '50%',
                  transform: 'translateY(-50%)',
                  color: '#94A3B8',
                  fontSize: '0.85rem',
                }}
              />
              <input
                type="text"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                placeholder="Rechercher un étudiant, une formation, un cours..."
                style={{
                  width: '100%',
                  padding: '0.5rem 1rem 0.5rem 2.4rem',
                  fontSize: '0.85rem',
                  background: 'rgba(241, 245, 249, 0.85)',
                  border: '1px solid rgba(226, 232, 240, 0.9)',
                  borderRadius: '9999px',
                  outline: 'none',
                  color: '#0F172A',
                  transition: 'all 0.2s ease',
                  boxShadow: 'inset 0 1px 2px rgba(0, 0, 0, 0.02)',
                }}
                onFocus={(e) => {
                  e.target.style.background = '#FFFFFF'
                  e.target.style.borderColor = '#2F80ED'
                  e.target.style.boxShadow = '0 0 0 3px rgba(47, 128, 237, 0.15)'
                }}
                onBlur={(e) => {
                  e.target.style.background = 'rgba(241, 245, 249, 0.85)'
                  e.target.style.borderColor = 'rgba(226, 232, 240, 0.9)'
                  e.target.style.boxShadow = 'inset 0 1px 2px rgba(0, 0, 0, 0.02)'
                }}
              />
            </form>
          </div>

          {/* Fil d'Ariane discret — enfant direct de la top-bar pour tenir sur une seule ligne */}
          <nav className="d-none d-xl-block" style={{ flex: '1 1 auto', minWidth: 0 }}>
            <ol className="breadcrumb mb-0" style={{ fontSize: '0.8rem', color: '#64748B' }}>
              {breadcrumb || <li>Accueil</li>}
            </ol>
          </nav>

          {/* Côté Droit : Année Académique + Notifications + Profil Directeur */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.85rem', flexShrink: 0 }}>
            {/* Pilule Année Académique */}
            <div
              className="d-none d-md-flex"
              style={{
                alignItems: 'center',
                gap: '0.45rem',
                padding: '0.45rem 0.85rem',
                background: 'rgba(255, 255, 255, 0.9)',
                border: '1px solid #E2E8F0',
                borderRadius: '9999px',
                fontSize: '0.82rem',
                fontWeight: 600,
                color: '#1E293B',
                boxShadow: '0 1px 3px rgba(0, 0, 0, 0.03)',
                cursor: 'pointer',
              }}
              title="Année Académique Active"
            >
              <i className="bi bi-calendar3" style={{ color: '#2F80ED' }} />
              <span>2026 – 2027</span>
              <i className="bi bi-chevron-down" style={{ fontSize: '0.68rem', color: '#94A3B8' }} />
            </div>

            {/* Cloche de notifications */}
            {showAppNotifications ? (
              <AppNotificationsBell
                showNotes={isDirection}
                showRapports={canViewStatistiques}
                showFinance={canViewFinanceNotifications}
                showPresences={isChaineAbsences}
              />
            ) : (
              <div
                style={{
                  width: '38px',
                  height: '38px',
                  borderRadius: '50%',
                  background: 'rgba(255, 255, 255, 0.9)',
                  border: '1px solid #E2E8F0',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: '#64748B',
                  position: 'relative',
                  cursor: 'pointer',
                }}
                title="Notifications"
              >
                <i className="bi bi-bell" style={{ fontSize: '1rem' }} />
                <span
                  style={{
                    position: 'absolute',
                    top: '4px',
                    right: '4px',
                    width: '8px',
                    height: '8px',
                    borderRadius: '50%',
                    background: '#EF4444',
                  }}
                />
              </div>
            )}

            {/* Plaquette Profil Utilisateur (Avatar, Nom, Rôle) */}
            <Link
              to="/profile"
              className="top-bar-user"
              title="Mon profil"
              style={{
                textDecoration: 'none',
                color: 'inherit',
                display: 'flex',
                alignItems: 'center',
                gap: '0.65rem',
                padding: '0.3rem 0.65rem 0.3rem 0.3rem',
                borderRadius: '9999px',
                background: 'rgba(255, 255, 255, 0.85)',
                border: '1px solid #E2E8F0',
                transition: 'all 0.2s ease',
              }}
            >
              <div
                style={{
                  width: '36px',
                  height: '36px',
                  borderRadius: '50%',
                  overflow: 'hidden',
                  background: 'linear-gradient(135deg, #0B1F3A 0%, #1E62D0 100%)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  boxShadow: '0 2px 6px rgba(11, 31, 58, 0.15)',
                  flexShrink: 0,
                }}
              >
                <img
                  src={avatarDirector}
                  alt={displayName}
                  style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                  onError={(e) => {
                    e.currentTarget.style.display = 'none'
                    e.currentTarget.parentElement.innerText = userInitials
                  }}
                />
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', textAlign: 'left', lineHeight: 1.15 }}>
                <span style={{ fontSize: '0.84rem', fontWeight: 700, color: '#0F172A' }}>
                  {displayName}
                </span>
                <span style={{ fontSize: '0.7rem', color: '#64748B', fontWeight: 500 }}>
                  {roleLabel}
                </span>
              </div>

              <i className="bi bi-chevron-down" style={{ fontSize: '0.7rem', color: '#94A3B8', marginLeft: '0.2rem' }} />
            </Link>
          </div>
        </header>

        {/* Le padding n'est plus forcé à 0 : `.page-content` applique la
            gouttière du design system INJS (1.5rem / 1.75rem), identique à
            celle du Dashboard Engine. Les écrans qui construisent leur propre
            conteneur (.scolarite-dashboard-page, .finance-page,
            .dashboard-engine-wrapper) conservent leur padding. */}
        <div className="page-content">
          {children}
        </div>
      </main>
    </div>
  )
}

/**
 * Fil d'Ariane standard : Accueil / …segments.
 *
 * Les segments sont rendus en `Fragment` (et non enveloppés dans un `<span>`)
 * afin que chaque `<li>` reste un enfant direct de l'`<ol>` : enveloppé dans un
 * `<span>`, le fil s'affichait en escalier dans la barre supérieure au lieu
 * de tenir sur une seule ligne.
 */
export function FilAriane({ segments = [] }) {
  return (
    <>
      <li><Link to="/">Accueil</Link></li>
      {segments.map((segment, index) => (
        <Fragment key={`${segment.libelle}-${index}`}>
          <li className="separator">/</li>
          {segment.chemin && index < segments.length - 1
            ? <li><Link to={segment.chemin}>{segment.libelle}</Link></li>
            : <li>{segment.libelle}</li>}
        </Fragment>
      ))}
    </>
  )
}
