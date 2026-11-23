/** ImpactPermission — « Que provoque cette permission ? » (couche IMPACT).
 *
 * Additive : réutilise les composants et classes de la console CURP ;
 * aucune vue, route ou composant existant n'est modifié.
 *
 * Le code initial peut venir d'un lien contextuel (?code=module.ressource.action)
 * déposé par les écrans catalogue/matrice, ou de la prop `codeInitial`.
 */
import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { impactPermission, messageErreur } from '@/services/habilitations'
import { EnChargement } from './partages'
import SensibleBadge from './SensibleBadge'
import './habilitations.css'

export default function ImpactPermission({ codeInitial: codeInitialProp = '' }) {
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
      setDonnees(await impactPermission(cibleNettoyee))
    } catch (e) {
      setDonnees(null)
      setErreur(messageErreur(e, 'Permission introuvable ou accès refusé.'))
    } finally {
      setChargement(false)
    }
  }

  // Analyse immédiate quand un code initial est fourni (navigation croisée).
  useEffect(() => {
    if (codeInitial) analyser(codeInitial)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [codeInitial])

  return (
    <section data-testid="ecran-impact-permission">
      <div className="hab-carte">
        <h2 className="h5">
          <i className="bi bi-crosshair me-2" />Impact d'une permission
        </h2>
        <p className="hab-muted">
          Code canonique <code>module.ressource.action</code> du référentiel
          CURP. L'impact est dérivé du catalogue et des attributions réelles :
          rôles porteurs, comptes titulaires et octrois directs (dérogations).
        </p>
        <div className="hab-filtres">
          <input
            className="form-control"
            placeholder="ex. evaluations.note.modifier"
            data-testid="impact-permission-code"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && analyser()}
          />
          <button
            className="btn btn-primary btn-sm"
            data-testid="impact-permission-analyser"
            onClick={() => analyser()}
            disabled={!code.trim() || chargement}
          >
            Analyser
          </button>
        </div>
      </div>

      {chargement && <EnChargement message="Calcul de l'impact…" />}
      {erreur && (
        <div className="hab-carte hab-avertissement" data-testid="impact-permission-erreur">
          {erreur}
        </div>
      )}

      {donnees && !chargement && (
        <div className="hab-carte" data-testid="impact-permission-resultat">
          <h3 className="h6 mb-2">
            <code>{donnees.code}</code>{' '}
            <SensibleBadge type="permission" niveau={donnees.criticite} />
          </h3>
          <p className="hab-muted mb-1">
            Module : {donnees.module_libelle} · Ressource : {donnees.ressource} ·
            Action : {donnees.action} · Niveau requis :{' '}
            {donnees.niveau === null ? '—' : `N${donnees.niveau}`}
          </p>
          <p className="hab-muted mb-2">
            Motif obligatoire : {donnees.necessite_motif ? 'oui' : 'non'} ·
            Double validation : {donnees.necessite_double_validation ? 'oui' : 'non'} ·
            Journalisée : {donnees.journalisee ? 'oui' : 'non'} ·
            Portée maximale : {donnees.portee_maximale}
          </p>

          <h4 className="h6 mt-3">
            Rôles porteurs ({donnees.total_roles})
          </h4>
          {donnees.total_roles === 0 ? (
            <p className="hab-muted" data-testid="impact-permission-vide">
              Aucun rôle ne porte cette permission.
            </p>
          ) : (
            <table className="hab-table" data-testid="impact-permission-roles">
              <thead>
                <tr>
                  <th>Code</th><th>Libellé</th><th>Niv.</th><th>Comptes titulaires</th>
                </tr>
              </thead>
              <tbody>
                {donnees.roles.map((r) => (
                  <tr key={r.code}>
                    <td><code>{r.code}</code>{' '}<SensibleBadge type="role" niveau={r.sensible} /></td>
                    <td>{r.libelle}</td>
                    <td>{r.niveau_defaut}</td>
                    <td>{r.comptes_titulaires ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          <h4 className="h6 mt-3">
            Comptes impactés ({donnees.total_comptes})
          </h4>
          <p className="hab-muted mb-1">
            Via rôles : {donnees.total_comptes_roles} · Via octroi direct
            (dérogation) : {donnees.total_comptes_derogation}
          </p>
          {donnees.total_comptes === 0 ? (
            <p className="hab-muted" data-testid="impact-permission-sans-compte">
              Aucun compte ne détient cette permission aujourd'hui.
            </p>
          ) : (
            <div style={{ maxHeight: 320, overflow: 'auto' }}>
              <table className="hab-table" data-testid="impact-permission-comptes">
                <thead>
                  <tr><th>Identifiant</th><th>Nom</th><th>Statut</th></tr>
                </thead>
                <tbody>
                  {[...donnees.comptes_roles, ...donnees.comptes_derogation].map((c) => (
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
