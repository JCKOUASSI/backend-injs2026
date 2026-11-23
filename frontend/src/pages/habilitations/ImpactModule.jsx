/** ImpactModule — « Que gouverne ce module ? » (couche IMPACT, chaînon §28).
 *
 * Additive : réutilise les composants et classes de la console CURP.
 * Le code initial peut venir d'un lien contextuel (?code=module) déposé par
 * le dashboard ou la matrice, ou de la prop `codeInitial`.
 *
 * Contrat backend : GET /api/habilitations/impact/module/<code>/ →
 * { type: 'module', module, module_libelle, catalogue, permissions[],
 *   total_permissions, roles[], total_roles, total_comptes,
 *   criticite_max, roles_sensibles[], comptes[] }.
 */
import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { impactModule, messageErreur } from '@/services/habilitations'
import { EnChargement } from './partages'
import SensibleBadge from './SensibleBadge'
import './habilitations.css'

export default function ImpactModule({ codeInitial: codeInitialProp = '' }) {
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
      setDonnees(await impactModule(cibleNettoyee))
    } catch (e) {
      setDonnees(null)
      setErreur(messageErreur(e, 'Module introuvable ou accès refusé.'))
    } finally {
      setChargement(false)
    }
  }

  useEffect(() => {
    if (codeInitial) analyser(codeInitial)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [codeInitial])

  return (
    <section data-testid="ecran-impact-module">
      <div className="hab-carte">
        <h2 className="h5">
          <i className="bi bi-boxes me-2" />Impact d'un module
        </h2>
        <p className="hab-muted">
          Répond à : « qui peut agir dans ce module, avec quels rôles et
          quelles permissions ? ». Dérivé du référentiel CURP et des
          attributions réelles : MODULE → PERMISSIONS → RÔLES → COMPTES.
        </p>
        <div className="hab-filtres">
          <input
            className="form-control"
            placeholder="ex. evaluations"
            data-testid="impact-module-code"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && analyser()}
          />
          <button
            className="btn btn-primary btn-sm"
            data-testid="impact-module-analyser"
            onClick={() => analyser()}
            disabled={!code.trim() || chargement}
          >
            Analyser
          </button>
        </div>
      </div>

      {chargement && <EnChargement message="Calcul de l'impact…" />}
      {erreur && (
        <div className="hab-carte hab-avertissement" data-testid="impact-module-erreur">
          {erreur}
        </div>
      )}

      {donnees && !chargement && (
        <div className="hab-carte" data-testid="impact-module-resultat">
          <h3 className="h6 mb-2">
            {donnees.module_libelle} <code>{donnees.module}</code>{' '}
            <SensibleBadge type="permission" niveau={donnees.criticite_max} />
            {!donnees.catalogue && (
              <span className="text-warning ms-2" title="Module hors catalogue mais présent en base">
                Hors catalogue
              </span>
            )}
          </h3>
          <p className="hab-muted mb-2">
            {donnees.total_permissions} permission(s) · {donnees.total_roles} rôle(s)
            porteur(s) · {donnees.total_comptes} compte(s) titulaire(s) ·
            Criticité maximale : {donnees.criticite_max}
          </p>
          <h4 className="h6 mt-3">
            Permissions du module ({donnees.total_permissions})
          </h4>
          {donnees.total_permissions === 0 ? (
            <p className="hab-muted" data-testid="impact-module-sans-permissions">
              Ce module ne porte aucune permission dans le référentiel chargé.
            </p>
          ) : (
            <div style={{ maxHeight: 340, overflow: 'auto' }}>
              <table className="hab-table" data-testid="impact-module-permissions">
                <thead>
                  <tr><th>Permission</th><th>Ressource</th><th>Action</th><th>Criticité</th></tr>
                </thead>
                <tbody>
                  {donnees.permissions.map((p) => (
                    <tr key={`perm-${p.code}`}>
                      <td><code>{p.code}</code></td>
                      <td>{p.ressource}</td>
                      <td>{p.action}</td>
                      <td>
                        <SensibleBadge type="permission" niveau={p.criticite} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {donnees.roles_sensibles.length > 0 && (
            <div className="hab-avertissement" data-testid="impact-module-sensibles">
              <SensibleBadge type="role" critique /> Rôles sensibles portant
              ce module :{' '}
              {donnees.roles_sensibles.map((c) => (
                <code key={c} className="me-1">{c}</code>
              ))}
            </div>
          )}
          <h4 className="h6 mt-3">Rôles porteurs ({donnees.total_roles})</h4>
          {donnees.total_roles === 0 ? (
            <p className="hab-muted" data-testid="impact-module-sans-roles">
              Aucun rôle actif ne porte ce module aujourd'hui.
            </p>
          ) : (
            <div style={{ maxHeight: 320, overflow: 'auto' }}>
              <table className="hab-table" data-testid="impact-module-roles">
                <thead>
                  <tr><th>Rôle</th><th>Libellé</th><th>Titulaires</th></tr>
                </thead>
                <tbody>
                  {donnees.roles.map((r) => (
                    <tr key={`role-${r.code}`}>
                      <td>
                        <code>{r.code}</code>{' '}
                        <SensibleBadge type="role" niveau={r.sensible} />
                      </td>
                      <td>{r.libelle}</td>
                      <td>{r.comptes_titulaires ?? '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <h4 className="h6 mt-3">Comptes titulaires ({donnees.total_comptes})</h4>
          {donnees.total_comptes === 0 ? (
            <p className="hab-muted" data-testid="impact-module-sans-comptes">
              Aucun compte titulaire actif aujourd'hui.
            </p>
          ) : (
            <div style={{ maxHeight: 320, overflow: 'auto' }}>
              <table className="hab-table" data-testid="impact-module-comptes">
                <thead>
                  <tr><th>Identifiant</th><th>Nom</th><th>Statut</th></tr>
                </thead>
                <tbody>
                  {donnees.comptes.map((c) => (
                    <tr key={`compte-${c.id}`}>
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
