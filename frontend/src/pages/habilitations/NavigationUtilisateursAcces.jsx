import { NavLink } from 'react-router-dom'
import { useDroits } from '@/hooks/useDroits'
import { useFlag } from '@/hooks/useFlag'

const LIENS_CONSOLE = [
  { to: '/administration/comptes', fin: true, icone: 'bi-people', libelle: 'Comptes' },
  { to: '/administration/comptes/nouveau', icone: 'bi-person-plus', libelle: 'Nouveau compte' },
  { to: '/administration/comptes/dashboard', icone: 'bi-speedometer2', libelle: 'Dashboard' },
  { to: '/administration/comptes/roles', icone: 'bi-person-badge', libelle: 'Rôles' },
  { to: '/administration/comptes/impact-role', icone: 'bi-crosshair', libelle: 'Impact rôle' },
  { to: '/administration/comptes/permissions', icone: 'bi-list-columns', libelle: 'Catalogue des permissions' },
  { to: '/administration/comptes/impact-permission', icone: 'bi-crosshair2', libelle: 'Impact permission' },
  { to: '/administration/comptes/impact-module', icone: 'bi-boxes', libelle: 'Impact module' },
  { to: '/administration/comptes/matrice', icone: 'bi-grid-3x3-gap', libelle: 'Matrice des permissions' },
  { to: '/administration/comptes/impact-utilisateur', icone: 'bi-person-check', libelle: 'Impact utilisateur' },
  { to: '/administration/comptes/acces-effectifs', icone: 'bi-diagram-2', libelle: 'Accès effectifs' },
  { to: '/administration/comptes/derogations', icone: 'bi-key', libelle: 'Dérogations' },
  { to: '/administration/comptes/delegations', icone: 'bi-person-check', libelle: 'Délégations' },
  { to: '/administration/comptes/demandes', icone: 'bi-clipboard2-check', libelle: "Demandes d'accès" },
  { to: '/administration/comptes/provisionnement', icone: 'bi-inbox', libelle: 'File de provisionnement' },
  { to: '/administration/comptes/operations-masse', icone: 'bi-upload', libelle: 'Opérations en masse' },
  { to: '/administration/comptes/notifications', icone: 'bi-bell', libelle: "Notifications d'échéance" },
  { to: '/administration/comptes/revue', icone: 'bi-clipboard-check', libelle: 'Revue des habilitations' },
  { to: '/administration/comptes/journal', icone: 'bi-journal-text', libelle: 'Journal' },
  { to: '/administration/comptes/organisation', icone: 'bi-diagram-3', libelle: 'Organisation' },
]

/** Navigation partagée. Elle n'accorde aucun droit et masque la console
 * lorsque son kill-switch ou sa capacité existante manque. */
export default function NavigationUtilisateursAcces({ compact = false }) {
  const droits = useDroits()
  const consoleActive = useFlag('flag.curp_ui_admin')
  const peutGererConsole = Boolean(droits.capacites)
    && droits.peut('habilitations_admin', 'gerer')
  const liens = [
    { to: '/users', icone: 'bi-person-vcard', libelle: 'Profils' },
    ...(consoleActive && peutGererConsole ? LIENS_CONSOLE : []),
  ]

  return (
    <nav
      className={`hab-nav${compact ? ' hab-nav-compact' : ''}`}
      aria-label="Navigation Utilisateurs et Accès"
      data-testid="navigation-utilisateurs-acces"
    >
      {liens.map((lien) => (
        <NavLink
          key={lien.to}
          to={lien.to}
          end={lien.fin}
          className={({ isActive }) => (isActive ? 'active' : '')}
        >
          <i className={`bi ${lien.icone}`} aria-hidden="true" />
          <span>{lien.libelle}</span>
        </NavLink>
      ))}
    </nav>
  )
}