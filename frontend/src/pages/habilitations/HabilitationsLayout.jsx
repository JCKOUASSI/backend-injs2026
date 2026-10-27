/**
 * Gabarit de la console CURP (U4) : garde dérivée des capacités backend
 * (``habilitations_admin.gerer``), bandeau de traçabilité permanent et
 * navigation latérale entre les onze écrans. La console est entièrement
 * nouvelle ; elle ne remplace pas l'écran Utilisateurs existant.
 */
import { Outlet } from 'react-router-dom'
import { useDroits } from '@/hooks/useDroits'
import { BandeauTraçabilite, Message403 } from './partages'
import NavigationUtilisateursAcces from './NavigationUtilisateursAcces'

export default function HabilitationsLayout() {
  const droits = useDroits()
  const autorise = droits.peut('habilitations_admin', 'gerer')

  if (!droits.charge) {
    return <p className="hab-muted"><div className="spinner-border spinner-border-sm me-2" />Vérification des droits…</p>
  }
  if (!autorise) {
    return (
      <div className="container py-3">
        <Message403 detail="La console est réservée aux administrateurs de l'habilitation et doit être activée par le drapeau CURP_UI_ADMIN." />
      </div>
    )
  }

  return (
    <div className="container-fluid py-3">
      <BandeauTraçabilite />
      <h2 className="h4 mt-2 mb-3">
        <i className="bi bi-shield-lock me-2" />Administration des comptes — CURP
      </h2>
      <div className="hab-layout">
        <NavigationUtilisateursAcces />
        <div className="hab-contenu">
          <Outlet />
        </div>
      </div>
    </div>
  )
}
