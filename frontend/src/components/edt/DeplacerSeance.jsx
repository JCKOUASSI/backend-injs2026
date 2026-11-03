import { useCallback, useEffect, useMemo, useState } from 'react'
import api from '../../services/api'
import { formatHeure, libelleJour, messageErreurApi } from '../../utils/edts'

/**
 * GET-INJS — déplacement d'une séance, **revalidé par le moteur**.
 *
 * L'écran ne calcule aucune compatibilité lui-même : il demande au serveur la
 * liste des positions acceptables (`GET /api/edts/lmd/items/<id>/move/`) puis
 * soumet la position choisie (`POST` sur la même route). Le serveur rejoue
 * C1→C10 sur le plan complet ; un refus revient en **409** avec le code de la
 * contrainte violée.
 *
 * Règles visibles :
 *  - aucune position n'est proposée « au hasard » : seules les positions que le
 *    moteur a validées apparaissent ;
 *  - un refus est affiché comme un refus, avec ses codes — jamais converti en
 *    succès partiel ;
 *  - si la liste est vide, le message le dit (aucune place compatible) au lieu
 *    d'afficher un écran blanc.
 */

function grouperParJour(candidats) {
  const parJour = new Map()
  for (const c of candidats) {
    const cle = c.jour
    if (!parJour.has(cle)) parJour.set(cle, [])
    parJour.get(cle).push(c)
  }
  return [...parJour.entries()]
}

function libelleCandidat(c) {
  return `${libelleJour(c.jour)} ${formatHeure(c.heure_debut)}–${formatHeure(c.heure_fin)}`
}

export default function DeplacerSeance({ affectation, onClose, onMoved }) {
  const [etat, setEtat] = useState('chargement') // chargement | pret | erreur
  const [candidats, setCandidats] = useState([])
  const [plan, setPlan] = useState(null)
  const [erreur, setErreur] = useState('')
  const [choix, setChoix] = useState(null)
  const [envoi, setEnvoi] = useState(false)
  const [refus, setRefus] = useState(null)

  const charger = useCallback(async () => {
    setEtat('chargement')
    setErreur('')
    setRefus(null)
    try {
      const { data } = await api.get(`/edts/lmd/items/${affectation.id}/move/`)
      setCandidats(data?.candidats || [])
      setPlan(data || null)
      setEtat('pret')
    } catch (e) {
      setErreur(messageErreurApi(e, 'Impossible de calculer les positions compatibles.'))
      setEtat('erreur')
    }
  }, [affectation.id])

  useEffect(() => { charger() }, [charger])

  const parJour = useMemo(() => grouperParJour(candidats), [candidats])

  const deplacer = async () => {
    if (!choix) return
    setEnvoi(true)
    setRefus(null)
    try {
      const { data } = await api.post(`/edts/lmd/items/${affectation.id}/move/`, {
        creneau_template_id: choix.creneau_template_id,
        salle_id: choix.salle_id,
      })
      onMoved?.(data)
    } catch (e) {
      const data = e?.response?.data
      if (e?.response?.status === 409) {
        // Refus métier : le moteur explique. On ne ferme pas, on ne ment pas.
        setRefus({
          explication: data?.explication || 'Déplacement refusé par le moteur.',
          action: data?.action_recommandee || '',
          violations: data?.violations || [],
        })
      } else {
        setErreur(messageErreurApi(e, 'Déplacement refusé.'))
      }
    } finally {
      setEnvoi(false)
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="modal-content"
        style={{ maxWidth: 860 }}
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label="Déplacer la séance"
      >
        <div className="modal-header">
          <h5 className="modal-title">
            <i className="bi bi-arrows-move me-2" />
            Déplacer « {affectation.intitule || 'séance'} »
          </h5>
          <button type="button" className="btn-close" onClick={onClose} aria-label="Fermer" />
        </div>

        <div className="modal-body">
          <p className="small text-muted">
            Position actuelle :{' '}
            <strong>
              {affectation.horaire
                || (affectation.creneau_template_id ? 'créneau défini' : 'non planifiée')}
            </strong>
            {affectation.salle_nom ? ` · salle ${affectation.salle_nom}` : ''}
            {' · '}semaines s{affectation.semaine_debut}–s{affectation.semaine_fin}
          </p>

          {etat === 'chargement' && (
            <p className="text-muted mb-0">
              <span className="spinner-border spinner-border-sm me-2" aria-hidden="true" />
              Vérification des positions compatibles (C1 → C10)…
            </p>
          )}

          {etat === 'erreur' && (
            <div className="alert alert-danger mb-0" role="alert">{erreur}</div>
          )}

          {/* Le plan existant est déjà invalide : c'est la cause réelle, elle est
              affichée avant le « aucune position » qui n'en est que la conséquence. */}
          {etat === 'pret' && plan && plan.plan_valide === false && (
            <div className="alert alert-danger">
              <strong>Le plan actuel est déjà en violation.</strong>
              <div className="small mt-1">{plan.explication}</div>
              {plan.violations_plan?.length > 0 && (
                <ul className="small mb-1 mt-1">
                  {plan.violations_plan.slice(0, 8).map((v, i) => (
                    <li key={`${v.contrainte || 'V'}-${i}`}>
                      <strong>{v.contrainte}</strong>
                      {v.message ? ` — ${v.message}` : ''}
                    </li>
                  ))}
                </ul>
              )}
              {plan.action_recommandee && (
                <div className="small fst-italic">{plan.action_recommandee}</div>
              )}
            </div>
          )}

          {etat === 'pret' && candidats.length === 0 && plan?.plan_valide !== false && (
            <div className="alert alert-warning mb-0">
              <strong>Aucune position compatible.</strong> Toutes les autres plages
              horaires provoquent un conflit (enseignant, groupe ou salle) sur les
              semaines de cette séance. Changez d’abord une autre séance, la salle
              ou l’affectation pédagogique.
            </div>
          )}

          {etat === 'pret' && candidats.length > 0 && (
            <>
              <p className="small mb-2">
                {candidats.length} position(s) validée(s) par le moteur — cliquez pour choisir.
              </p>
              <div className="table-responsive" style={{ maxHeight: 340 }}>
                <table className="table table-sm align-middle mb-0">
                  <caption className="visually-hidden">
                    Positions compatibles : journée, horaire, salle et capacité
                  </caption>
                  <thead className="table-light">
                    <tr>
                      <th scope="col">Horaire</th>
                      <th scope="col">Salle</th>
                      <th scope="col">Capacité</th>
                      <th scope="col" className="text-end">Choisir</th>
                    </tr>
                  </thead>
                  <tbody>
                    {parJour.map(([jour, liste]) => (
                      liste.map((c, index) => {
                        const actif = choix
                          && choix.creneau_template_id === c.creneau_template_id
                          && choix.salle_id === c.salle_id
                        return (
                          <tr
                            key={`${c.creneau_template_id}-${c.salle_id}`}
                            className={actif ? 'table-active' : ''}
                          >
                            <td className="text-nowrap">
                              {index === 0 && (
                                <span className="badge text-bg-light me-2">
                                  {libelleJour(jour)}
                                </span>
                              )}
                              {formatHeure(c.heure_debut)}–{formatHeure(c.heure_fin)}
                            </td>
                            <td>{c.salle_nom || <span className="text-muted">sans salle</span>}</td>
                            <td>
                              {c.salle_capacite ?? (
                                <span className="text-muted" title="Capacité non renseignée — C4 non vérifiable">
                                  —
                                </span>
                              )}
                            </td>
                            <td className="text-end">
                              <input
                                type="radio"
                                className="form-check-input"
                                name={`candidat-${affectation.id}`}
                                aria-label={`Choisir ${libelleCandidat(c)} en ${c.salle_nom || 'sans salle'}`}
                                checked={!!actif}
                                onChange={() => { setChoix(c); setRefus(null) }}
                              />
                            </td>
                          </tr>
                        )
                      })
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}

          {refus && (
            <div className="alert alert-danger mt-3 mb-0" role="alert">
              <strong>Déplacement refusé par le moteur.</strong>
              <div className="small mt-1">{refus.explication}</div>
              {refus.violations.length > 0 && (
                <ul className="small mb-0 mt-1">
                  {refus.violations.map((v, i) => (
                    <li key={`${v.code || 'V'}-${i}`}>
                      <strong>{v.code || 'CONTRAINTE'}</strong>
                      {v.message ? ` — ${v.message}` : ''}
                    </li>
                  ))}
                </ul>
              )}
              {refus.action && <div className="small mt-1 fst-italic">{refus.action}</div>}
            </div>
          )}

          {erreur && etat === 'pret' && (
            <div className="alert alert-danger mt-3 mb-0" role="alert">{erreur}</div>
          )}
        </div>

        <div className="modal-footer">
          <button type="button" className="btn btn-outline-secondary" onClick={onClose}>
            Fermer
          </button>
          <button
            type="button"
            className="btn btn-primary"
            disabled={!choix || envoi}
            onClick={deplacer}
          >
            {envoi ? 'Déplacement…' : 'Déplacer ici'}
          </button>
        </div>
      </div>
    </div>
  )
}
