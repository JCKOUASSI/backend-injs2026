/** ImpactUtilisateur — « Que peut réellement faire cet utilisateur ? »
 * (couche IMPACT, additive).
 *
 * Distincte clairement :
 * - ce qui est ATTRIBUÉ (rôles actifs, dérogations) ;
 * - ce qui est EFFECTIF (résolution CURP : comptes_admin.permissions_effectives,
 *   retraits prioritaires) — jamais recalculé côté frontend.
 *
 * L'identifiant peut venir d'un lien contextuel depuis la fiche du compte
 * (?user=<user_id>) ou de la prop `userIdInitial`.
 */
import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { impactUtilisateur, messageErreur } from '@/services/habilitations'
import { libelleStatut } from '@/utils/habilitations'
import { EnChargement } from './partages'
import SensibleBadge from './SensibleBadge'
import './habilitations.css'

function BlocRoles({ roles }) {
  if (!roles || roles.length === 0) {
    return (
      <p className="hab-muted" data-testid="impact-utilisateur-sans-roles">
        Aucun rôle actif.
      </p>
    )
  }
  return (
    <table className="hab-table" data-testid="impact-utilisateur-roles">
      <thead>
        <tr><th>Rôle</th><th>Niveau</th><th>Périmètres</th><th>Jusqu'au</th></tr>
      </thead>
      <tbody>
        {roles.map((r) => (
          <tr key={`role-${r.code}`}>
            <td>
              {r.libelle} <code>{r.code}</code>{' '}
              <SensibleBadge type="role" niveau={r.sensible} />
            </td>
            <td>{r.niveau_effectif}</td>
            <td>
              {r.perimetres.length === 0
                ? <span className="hab-muted">Périmètre par défaut du rôle</span>
                : r.perimetres.map((p) => (
                  <span key={`perim-${p.id}`} className="me-2">
                    {p.libelle || p.type}
                  </span>
                ))}
            </td>
            <td>{r.date_fin || '—'}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export default function ImpactUtilisateur({ userIdInitial: userIdInitialProp = '' }) {
  const [params] = useSearchParams()
  const userIdInitial = userIdInitialProp || params.get('user') || ''
  const [userId, setUserId] = useState(userIdInitial)
  const [donnees, setDonnees] = useState(null)
  const [chargement, setChargement] = useState(false)
  const [erreur, setErreur] = useState('')

  const analyser = async (cible) => {
    const cibleNettoyee = (cible ?? userId).trim()
    if (!cibleNettoyee) return
    setChargement(true)
    setErreur('')
    try {
      setDonnees(await impactUtilisateur(cibleNettoyee))
    } catch (e) {
      setDonnees(null)
      setErreur(messageErreur(e, 'Utilisateur introuvable ou accès refusé.'))
    } finally {
      setChargement(false)
    }
  }

  useEffect(() => {
    if (userIdInitial) analyser(userIdInitial)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userIdInitial])

  return (
    <section data-testid="ecran-impact-utilisateur">
      <div className="hab-carte">
        <h2 className="h5">
          <i className="bi bi-person-check me-2" />Impact d'un utilisateur
        </h2>
        <p className="hab-muted">
          Identifiant du compte Django (clé primaire). L'accès effectif est
          résolu par le moteur CURP : attributions actives + dérogations,
          retraits prioritaires. Le frontend n'invente jamais un accès.
        </p>
        <div className="hab-filtres">
          <input
            className="form-control"
            placeholder="Identifiant du compte Django…"
            data-testid="impact-utilisateur-id"
            value={userId}
            onChange={(e) => setUserId(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && analyser()}
          />
          <button
            className="btn btn-primary btn-sm"
            data-testid="impact-utilisateur-analyser"
            onClick={() => analyser()}
            disabled={!userId.trim() || chargement}
          >
            Analyser
          </button>
        </div>
      </div>

      {chargement && <EnChargement message="Calcul des accès effectifs…" />}
      {erreur && (
        <div
          className="hab-carte hab-avertissement"
          data-testid="impact-utilisateur-erreur"
        >
          {erreur}
        </div>
      )}

      {donnees && !chargement && <Resultats donnees={donnees} />}
    </section>
  )
}

function Resultats({ donnees }) {
  const arbre = donnees.arbre
  return (
    <>
      <div className="hab-carte" data-testid="impact-utilisateur-identite">
        <h3 className="h6 mb-2">
          {donnees.username}{' '}
          <span className={`hab-statut hab-statut-${donnees.statut}`}>
            {libelleStatut(donnees.statut)}
          </span>
          {donnees.mfa_actif && (
            <span className="hab-muted ms-2">
              <i className="bi bi-shield-lock me-1" />MFA actif
            </span>
          )}
        </h3>
        <p className="hab-muted mb-0">
          Nom : {[donnees.prenoms, donnees.nom].filter(Boolean).join(' ') || '—'} ·
          Rôles actifs : {donnees.total_roles} · Permissions directes
          (dérogations) : {donnees.total_directes} · Héritées :{' '}
          {donnees.total_heritees} · Accès effectifs :{' '}
          <strong data-testid="impact-utilisateur-effectives">
            {donnees.total_effectives}
          </strong>
        </p>
      </div>

      {donnees.permissions_retraits.length > 0 && (
        <div
          className="hab-carte hab-avertissement"
          data-testid="impact-utilisateur-retraits"
        >
          Retraits actifs (déduits de l'effectif) :{' '}
          {donnees.permissions_retraits.map((r) => (
            <code key={r.code} className="me-1">{r.code}</code>
          ))}
        </div>
      )}

      <div className="hab-carte">
        <h4 className="h6">Rôles attribués</h4>
        <BlocRoles roles={donnees.roles} />
      </div>

      <div className="hab-carte">
        <h4 className="h6">Accès effectifs par module</h4>
        {donnees.modules_effectifs.length === 0 ? (
          <p
            className="hab-muted"
            data-testid="impact-utilisateur-sans-effectifs"
          >
            Aucun accès effectif aujourd'hui.
          </p>
        ) : (
          <ul className="mb-0" data-testid="impact-utilisateur-modules">
            {donnees.modules_effectifs.map((m) => (
              <li key={`module-${m.module}`}>
                {m.module_libelle}{' '}
                <code className="hab-muted">{m.module}</code>
              </li>
            ))}
          </ul>
        )}
        {donnees.actions_sensibles_effectives.length > 0 && (
          <div
            className="hab-avertissement mt-2"
            data-testid="impact-utilisateur-sensibles"
          >
            <SensibleBadge type="acces" critique /> Actions sensibles
            effectives :{' '}
            {donnees.actions_sensibles_effectives.map((c) => (
              <code key={c} className="me-1">{c}</code>
            ))}
          </div>
        )}
      </div>

      <div className="hab-carte">
        <h4 className="h6">Arbre des accès (rôle → module → permission)</h4>
        {(!arbre || (arbre.roles.length === 0 && arbre.derogations.length === 0)) ? (
          <p className="hab-muted" data-testid="impact-utilisateur-arbre-vide">
            Aucun accès attribué ni dérogation directe.
          </p>
        ) : (
          <ul className="hab-arbre mb-0" data-testid="impact-utilisateur-arbre">
            {arbre.roles.map((r) => (
              <li key={`arbre-role-${r.code}`}>
                <span className="hab-arbre-role">
                  <i className="bi bi-person-badge me-1" />{r.libelle}
                  <code className="ms-1">{r.code}</code>
                  <SensibleBadge type="role" niveau={r.sensible} />
                </span>
                <ul>
                  {r.modules.map((m) => (
                    <li key={`arbre-module-${r.code}-${m.module}`}>
                      {m.module_libelle}
                      <ul>
                        {m.permissions.map((codeP) => (
                          <li key={`arbre-perm-${codeP}`}>
                            <code>{codeP}</code>
                          </li>
                        ))}
                      </ul>
                    </li>
                  ))}
                </ul>
              </li>
            ))}
            {arbre.derogations.map((codeP) => (
              <li key={`arbre-octroi-${codeP}`}>
                <span className="hab-arbre-role">
                  <i className="bi bi-key me-1" />Octroi direct (dérogation)
                </span>
                <ul><li><code>{codeP}</code></li></ul>
              </li>
            ))}
            {arbre.retraits.map((codeP) => (
              <li key={`arbre-retrait-${codeP}`}>
                <span className="hab-arbre-role text-danger">
                  <i className="bi bi-slash-circle me-1" />Retrait actif
                </span>
                <ul><li><code>{codeP}</code></li></ul>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="hab-carte">
        <h4 className="h6">
          Délégations reçues ({donnees.delegations_recues.length})
        </h4>
        {donnees.delegations_recues.length === 0 ? (
          <p className="hab-muted">Aucune délégation active reçue.</p>
        ) : (
          <table
            className="hab-table"
            data-testid="impact-utilisateur-delegations"
          >
            <thead>
              <tr><th>Délégant</th><th>Rôles délégués</th><th>Jusqu'au</th></tr>
            </thead>
            <tbody>
              {donnees.delegations_recues.map((d) => (
                <tr key={`deleg-${d.id}`}>
                  <td>{d.delegant.username}</td>
                  <td>{d.roles.join(', ') || '—'}</td>
                  <td>{d.date_fin}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  )
}
