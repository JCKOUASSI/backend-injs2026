/**
 * NotificationsHabilitation (U5) — consultation des notifications internes
 * (préavis de suspension, échéances J-7, alertes de plafond, invitations
 * expirées). Aucun courriel n'est envoyé dans le sandbox : les messages sont
 * conservés en base et lisibles ici.
 */
import { useCallback, useEffect, useState } from 'react'
import {
  listerNotifications,
  lireNotification,
  toutLireNotifications,
} from '@/services/habilitations'
import { EnChargement } from './partages'
import './habilitations.css'

const ICONE_CATEGORIE = {
  PREAVIS_SUSPENSION: 'bi-exclamation-triangle text-warning',
  ECHEANCE_ATTRIBUTION: 'bi-clock-history text-info',
  ECHEANCE_DEROGATION: 'bi-clock-history text-info',
  ECHEANCE_DELEGATION: 'bi-clock-history text-info',
  ECHEANCE_COMPTE: 'bi-clock-history text-info',
  EXPIRATION_INVITATION: 'bi-envelope-x text-secondary',
  ALERTE_PLAFOND: 'bi-triangle-fill text-danger',
  PROPOSITION: 'bi-inbox text-primary',
  AUTRE: 'bi-bell text-muted',
}

export default function NotificationsHabilitation() {
  const [donnees, setDonnees] = useState(null)
  const [filtreLu, setFiltreLu] = useState('')

  const charger = useCallback(() => {
    const filtres = { page_size: 50 }
    if (filtreLu) filtres.lu = filtreLu === 'lus'
    listerNotifications(filtres).then(setDonnees)
  }, [filtreLu])
  useEffect(() => { charger() }, [charger])

  const marquerLu = async (id) => {
    await lireNotification(id)
    charger()
  }
  const toutMarquer = async () => {
    await toutLireNotifications()
    charger()
  }

  if (!donnees) return <EnChargement />
  const nonLues = donnees.results.filter((n) => !n.lu).length
  return (
    <section data-testid="ecran-notifications">
      <div className="hab-carte">
        <div className="d-flex justify-content-between align-items-center flex-wrap gap-2">
          <h2 className="h5 mb-0">Notifications d'habilitation</h2>
          <div className="d-flex gap-2">
            <select className="form-select form-select-sm" style={{ width: 'auto' }}
                    value={filtreLu} onChange={(e) => setFiltreLu(e.target.value)}
                    data-testid="filtre-notifications">
              <option value="">Toutes</option>
              <option value="non-lues">Non lues</option>
              <option value="lus">Lues</option>
            </select>
            <button className="btn btn-sm btn-outline-secondary" data-testid="tout-lire"
                    disabled={nonLues === 0} onClick={toutMarquer}>
              Tout marquer comme lu
            </button>
          </div>
        </div>
      </div>
      <ul className="list-group" data-testid="liste-notifications">
        {donnees.results.map((n) => (
          <li key={n.id}
              className={`list-group-item d-flex gap-3 ${n.lu ? '' : 'list-group-item-warning'}`}
              data-testid={`notification-${n.id}`}>
            <i className={`bi ${ICONE_CATEGORIE[n.categorie] || ICONE_CATEGORIE.AUTRE} fs-5`} />
            <div className="flex-grow-1">
              <div className="d-flex justify-content-between gap-2">
                <strong>{n.titre}</strong>
                <span className="hab-muted small">{n.date_creation?.slice(0, 16).replace('T', ' ')}</span>
              </div>
              {n.message && <p className="mb-1 small">{n.message}</p>}
              <span className="hab-muted small">{n.categorie_libelle}</span>
            </div>
            {!n.lu && (
              <button className="btn btn-sm btn-outline-primary align-self-center"
                      data-testid={`marquer-lu-${n.id}`} onClick={() => marquerLu(n.id)}>
                Marquer comme lu
              </button>
            )}
          </li>
        ))}
        {donnees.results.length === 0 && (
          <li className="list-group-item text-center hab-muted py-4">Aucune notification.</li>
        )}
      </ul>
    </section>
  )
}
