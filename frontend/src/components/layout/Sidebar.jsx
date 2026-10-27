import { useEffect, useMemo, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import logo from '../../assets/logo-injs.svg'
import { useAuth } from '../../context/AuthContext'
import { useMenuAutorise } from '../../hooks/useMenuAutorise'
import { LIBELLES_ROLES } from '../../menu/arborescence'
import { droitRequis } from '../../menu/autorisation'
import { getUserRoles, peut } from '../../utils/roles'
import { LIST_STORAGE_KEYS, listHref } from '../../utils/listFilters'
import { financeNavHref } from '../../utils/financePeriod'
import '../../styles/sidebar.css'
import { safeLocalStorage } from '../../utils/safeStorage'

/**
 * Barre latérale RBAC — Thème Premium INJS Marcory.
 *
 * Entièrement pilotée par les droits (CURP pour comptes gouvernés,
 * capacités projetées pour comptes legacy).
 */

const CLE_ETAT = 'injs.sidebar.sectionsOuvertes'

/** Chemins dont les filtres de liste sont mémorisés (comportement historique). */
const LIENS_FILTRES = {
  '/dashboard': LIST_STORAGE_KEYS.dashboard,
  '/modules': LIST_STORAGE_KEYS.modules,
  '/participants': LIST_STORAGE_KEYS.participants,
  '/formateurs': LIST_STORAGE_KEYS.formateurs,
  '/users': LIST_STORAGE_KEYS.users,
  '/organisation': LIST_STORAGE_KEYS.secretariats,
  '/referentiels': LIST_STORAGE_KEYS.referentiels,
}

/** Chemins du module Finance historique : conservent la période sélectionnée. */
const LIENS_FINANCE = new Set([
  '/finance-dashboard',
  '/finance-encadrants',
  '/finance-parametrage',
  '/finance-ajustements',
])

function lireEtat() {
  try {
    const brut = safeLocalStorage.getItem(CLE_ETAT)
    return brut ? JSON.parse(brut) : null
  } catch {
    return null
  }
}

function ecrireEtat(etat) {
  try {
    safeLocalStorage.setItem(CLE_ETAT, JSON.stringify(etat))
  } catch {
    // Mode privé
  }
}

export default function Sidebar({ open = false, onClose = () => {} }) {
  const { user, logout } = useAuth()
  const location = useLocation()
  const chemin = location.pathname
  const { sections, pied, source, gouverne, nombreCodes } = useMenuAutorise()
  const [ouverts, setOuverts] = useState(() => lireEtat() ?? {})

  const moduleFinance = peut(user, 'finance', 'voir')

  /** Résout l'`href` d'une entrée en préservant filtres de liste et période. */
  const resoudreHref = useMemo(() => (item) => {
    const brut = item.chemin || '/'
    if (LIENS_FINANCE.has(brut) || (brut === '/formateurs' && moduleFinance)) {
      return financeNavHref(brut)
    }
    const cle = LIENS_FILTRES[brut]
    return cle ? listHref(brut, cle) : brut
  }, [moduleFinance])

  const estActif = useMemo(() => (item) => {
    const cible = item.chemin
    if (!cible) return false
    if (cible === '/') return chemin === '/'
    if (cible === '/formations') {
      return chemin.startsWith('/formations') && !chemin.includes('/modules/')
    }
    if (cible === '/modules') {
      return chemin === '/modules' || chemin.startsWith('/modules/')
    }
    if (cible === '/personnel/agents' || cible === '/administration/services') {
      return chemin === cible || chemin.startsWith(`${cible}/`)
    }
    return chemin === cible || chemin.startsWith(`${cible}/`)
  }, [chemin])

  /** Section contenant la route active : ouverte d'office. */
  const sectionActive = useMemo(() => {
    const trouve = sections.find((s) =>
      (s.enfants || []).some((e) => estActif(e)) || estActif(s))
    return trouve ? trouve.id : null
  }, [sections, estActif])

  useEffect(() => {
    if (sectionActive) {
      setOuverts((precedent) => (
        precedent[sectionActive] ? precedent : { ...precedent, [sectionActive]: true }
      ))
    }
  }, [sectionActive])

  useEffect(() => { ecrireEtat(ouverts) }, [ouverts])

  const basculer = (id) => setOuverts((p) => ({ ...p, [id]: !p[id] }))

  const nomComplet = user?.get_full_name
    ? user.get_full_name()
    : `${user?.first_name || ''} ${user?.last_name || ''}`.trim() || user?.username || '—'
  const libelleRole = getUserRoles(user)
    .map((r) => LIBELLES_ROLES[r] || r)
    .join(', ') || user?.role || ''

  // Fermeture lors de la navigation (sur mobile/tablette uniquement pour ne pas replier sur bureau)
  const fermerNavigation = () => {
    if (typeof window !== 'undefined' && window.innerWidth <= 992) {
      onClose()
    }
  }

  // Fermeture manuelle explicite (bouton fermer / chevron)
  const fermerManuel = () => {
    onClose()
  }

  return (
    <aside className={`sidebar${open ? ' show' : ''}`} id="sidebar" data-source-droits={source}>
      {/* Brand Header — Inspiré de la maquette INJS */}
      <div className="sidebar-brand">
        <div className="sidebar-brand-top">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
            <img src={logo} alt="INJS Abidjan" className="sidebar-logo" />
            <div>
              <div className="sidebar-brand-title">INJS</div>
              <div className="sidebar-brand-badge">INJS-LMD 2026</div>
            </div>
          </div>
          <button
            type="button"
            className="sidebar-hide-toggle"
            data-testid="sidebar-hide-toggle"
            onClick={fermerManuel}
            title="Masquer la barre latérale"
            aria-label="Masquer la barre latérale"
          >
            <i className="bi bi-chevron-left"></i>
          </button>
        </div>
        <div className="sidebar-brand-subtitle">
          Institut National de la Jeunesse et des Sports
        </div>
      </div>

      {user && (
        <div className="sidebar-user" data-testid="sidebar-identite">
          <small>Connecté en tant que</small>
          <span className="user-name">{nomComplet}</span>
          {libelleRole && <span className="user-role">{libelleRole}</span>}
          <div>
            <span
              className={`user-droits-source${gouverne ? ' curp' : ''}`}
              title={
                gouverne
                  ? `Menu filtré sur ${nombreCodes} permissions effectives CURP (compte gouverné).`
                  : 'Menu filtré sur les capacités projetées par le backend (compte non gouverné).'
              }
            >
              <i className={`bi ${gouverne ? 'bi-shield-check' : 'bi-key'}`}></i>
              {' '}{gouverne ? 'Droits CURP' : 'Droits legacy'}
            </span>
          </div>
        </div>
      )}

      <nav className="sidebar-nav" aria-label="Navigation principale">
        {sections.length === 0 && (
          <div className="nav-vide">
            <i className="bi bi-exclamation-triangle"></i>
            <p>Aucune entrée autorisée pour ce compte.</p>
            <small>
              Les droits sont accordés par le backend ; contactez un administrateur d'habilitation.
            </small>
          </div>
        )}

        {sections.map((section) => {
          const enfants = section.enfants || []
          if (enfants.length === 0) {
            return (
              <Link
                key={section.id}
                to={resoudreHref(section)}
                className={`nav-item nav-racine${estActif(section) ? ' active' : ''}`}
                onClick={fermerNavigation}
                data-testid={`nav-${section.id}`}
                title={section.libelle}
              >
                <span>
                  <i className={`bi ${section.icone || 'bi-speedometer2'}`}></i>
                  {' '}<span className="nav-label">{section.libelle}</span>
                </span>
              </Link>
            )
          }

          const ouvert = Boolean(ouverts[section.id]) || sectionActive === section.id
          return (
            <div className="nav-groupe" key={section.id} data-testid={`groupe-${section.id}`}>
              <button
                type="button"
                className={`nav-item nav-racine nav-groupe-tete${sectionActive === section.id ? ' active' : ''}`}
                onClick={() => basculer(section.id)}
                aria-expanded={ouvert}
                aria-controls={`menu-${section.id}`}
                title={section.libelle}
              >
                <span>
                  <i className={`bi ${section.icone || 'bi-folder'}`}></i>
                  {' '}<span className="nav-label">{section.libelle}</span>
                  {section.sousTitre && (
                    <span className="nav-sous-titre">{section.sousTitre}</span>
                  )}
                </span>
                <i className={`bi nav-chevron ${ouvert ? 'bi-chevron-down' : 'bi-chevron-right'}`}></i>
              </button>
              {ouvert && (
                <ul className="nav-sous-menu" id={`menu-${section.id}`}>
                  {enfants.map((enfant, index) => {
                    const requis = droitRequis(enfant)
                    return (
                      <li key={enfant.id} className="nav-sous-ligne">
                        <span
                          className="nav-connecteur"
                          aria-hidden="true"
                        >{index === enfants.length - 1 ? '└─' : '├─'}</span>
                        <Link
                          to={resoudreHref(enfant)}
                          className={`nav-sous-item${estActif(enfant) ? ' active' : ''}`}
                          onClick={fermerNavigation}
                          data-testid={`nav-${enfant.id}`}
                          title={[
                            enfant.libelle,
                            requis.curp.length ? `CURP : ${requis.curp.join(', ')}` : null,
                            requis.legacy.length ? `Capacités : ${requis.legacy.join(', ')}` : null,
                          ].filter(Boolean).join(' — ')}
                        >
                          {enfant.icone && <i className={`bi ${enfant.icone}`}></i>}
                          <span className="nav-label">{enfant.libelle}</span>
                        </Link>
                      </li>
                    )
                  })}
                </ul>
              )}
            </div>
          )
        })}
      </nav>

      <div className="sidebar-footer">
        {pied.map((item) => (
          <Link
            key={item.id}
            to={item.chemin}
            className={`nav-item${estActif(item) ? ' active' : ''}`}
            onClick={fermerNavigation}
            data-testid={`nav-${item.id}`}
          >
            <span>
              <i className={`bi ${item.icone || 'bi-dot'}`}></i>
              {' '}<span className="nav-label">{item.libelle}</span>
            </span>
          </Link>
        ))}
        <Link
          to="/profile"
          className={`nav-item${chemin === '/profile' ? ' active' : ''}`}
          onClick={fermerNavigation}
          data-testid="nav-profil"
        >
          <span><i className="bi bi-person-circle"></i> <span className="nav-label">Profil</span></span>
        </Link>
        <button
          type="button"
          className="nav-item nav-deconnexion"
          onClick={() => { fermerNavigation(); logout() }}
          data-testid="nav-deconnexion"
        >
          <span><i className="bi bi-box-arrow-right"></i> <span className="nav-label">Déconnexion</span></span>
        </button>
        <div className="nav-mention">
          Institut National de la Jeunesse et des Sports<br />
          <span>INJS-LMD 2026</span>
        </div>
      </div>
    </aside>
  )
}
