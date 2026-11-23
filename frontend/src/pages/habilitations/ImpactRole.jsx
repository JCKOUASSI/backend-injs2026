/** ImpactRole — « Que se passe-t-il si j'attribue ce rôle ? » (couche IMPACT).
 *
 * Additive : réutilise les composants et classes de la console CURP.
 * Le code initial peut venir d'un lien contextuel (?code=CODE) déposé par le
 * référentiel des rôles ou la matrice, ou de la prop `codeInitial`.
 */
import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { impactRole, messageErreur } from '@/services/habilitations'
import { libelleDomaine } from '@/utils/habilitations'
import { EnChargement } from './partages'
import SensibleBadge from './SensibleBadge'
import './habilitations.css'

export default function ImpactRole({ codeInitial: codeInitialProp = '' }) {
  const [params] = useSearchParams()
  const codeInitial = codeInitialProp || params.get('code') || ''
  const [code, setCode] = useState(codeInitial)
  const [donnees, setDonnees] = useState(null)
  const [chargement, setChargement] = useState(false)
  const [erreur, setErreur] = useState('')

  const analyser = async (cible) => {
    const cibleNettoyee = (cible ?? code).trim()
    if (!cibleNettoyee) return
    setChargement(true)
    setErreur('')
    try {
      setDonnees(await impactRole(cibleNettoyee))
    } catch (e) {
      setDonnees(null)
      setErreur(messageErreur(e, 'Rôle introuvable ou accès refusé.'))
    } finally {
      setChargement(false)
    }
  }

  useEffect(() => {
    if (codeInitial) analyser(codeInitial)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [codeInitial])

  return (
    <section data-testid="ecran-impact-role">
      <div className="hab-carte">
        <h2 className="h5">
          <i className="bi bi-person-badge me-2" />Impact d'un rôle
        </h2>
        <p className="hab-muted">
          Répond à : « si j'attribue ce rôle à quelqu'un, que pourra-t-il
          faire ? » et « que se passe-t-il si je le retire ? ». Dérivé du
          référentiel CURP et des attributions réelles.
        </p>
        <div className="hab-filtres">
          <input
            className="form-control"
            placeholder="ex. SCOLARITE"
            data-testid="impact-role-code"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && analyser()}
          />
          <button
            className="btn btn-primary btn-sm"
            data-testid="impact-role-analyser"
            onClick={() => analyser()}
            disabled={!code.trim() || chargement}
          >
            Analyser
          </button>
        </div>
      </div>

      {chargement && <EnChargement message="Calcul de l'impact…" />}
      {erreur && (
        <div className="hab-carte hab-avertissement" data-testid="impact-role-erreur">
          {erreur}
        </div>
      )}

      {donnees && !chargement && (
        <div className="hab-carte" data-testid="impact-role-resultat">
          <h3 className="h6 mb-2">
            {donnees.libelle} <code>{donnees.code}</code>{' '}
            <SensibleBadge type="role" niveau={donnees.sensible} />
            {!donnees.disponible && (
              <span className="text-danger ms-2" title="Module requis absent">
                Module absent
              </span>
            )}
          </h3>
          <p className="mb-1">{donnees.description}</p>
          <p className="hab-muted mb-2">
            Domaine : {libelleDomaine(donnees.domaine)} · Niveau par défaut :{' '}
            {donnees.niveau_defaut} · Périmètre par défaut :{' '}
            {donnees.perimetre_defaut}
            {donnees.canal_impose ? ` · Canal imposé : ${donnees.canal_impose}` : ''}
          </p>

          <h4 className="h6 mt-3">
            Permissions portées ({donnees.total_permissions})
          </h4>
          {donnees.total_permissions === 0 ? (
            <p className="hab-muted" data-testid="impact-role-sans-permissions">
              Ce rôle ne porte aucune permission dans le référentiel chargé.
            </p>
          ) : (
            <div style={{ maxHeight: 340, overflow: 'auto' }}>
              <table className="hab-table" data-testid="impact-role-permissions">
                <thead>
                  <tr><th>Module</th><th>Permissions</th></tr>
                </thead>
                <tbody>
                  {donnees.permissions_par_module.map((groupe) => (
                    <tr key={`module-${groupe.module}`}>
                      <td>{groupe.module_libelle}</td>
                      <td>
                        {groupe.permissions.map((codeP) => (
                          <code key={codeP} className="me-1">{codeP}</code>
                        ))}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {donnees.permissions_sensibles.length > 0 && (
            <div className="hab-avertissement" data-testid="impact-role-sensibles">
              <SensibleBadge type="permission" critique /> Actes sensibles portés
              par ce rôle :{' '}
              {donnees.permissions_sensibles.map((c) => (
                <code key={c} className="me-1">{c}</code>
              ))}
            </div>
          )}

          <h4 className="h6 mt-3">Comptes titulaires ({donnees.total_titulaires})</h4>
          {donnees.total_titulaires === 0 ? (
            <p className="hab-muted" data-testid="impact-role-sans-titulaires">
              Aucun titulaire actif aujourd'hui.
            </p>
          ) : (
            <div style={{ maxHeight: 320, overflow: 'auto' }}>
              <table className="hab-table" data-testid="impact-role-comptes">
                <thead>
                  <tr><th>Identifiant</th><th>Nom</th><th>Statut</th></tr>
                </thead>
                <tbody>
                  {donnees.titulaires.map((c) => (
                    <tr key={`titulaire-${c.id}`}>
                      <td>{c.username}</td>
                      <td>{[c.prenoms, c.nom].filter(Boolean).join(' ') || '—'}</td>
                      <td>{c.statut}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </section>
  )
}
