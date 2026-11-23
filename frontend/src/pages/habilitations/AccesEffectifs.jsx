/** AccesEffectifs — arbre Utilisateur → Rôle → Module → Permission
 * (couche IMPACT, additive).
 *
 * L'arbre est alimenté par le service de résolution effective CURP
 * (impact utilisateur = attributions actives + dérogations, retraits
 * prioritaires). Aucun accès n'est simulé côté frontend.
 */
import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { impactUtilisateur, listerComptes, messageErreur } from '@/services/habilitations'
import { EnChargement } from './partages'
import SensibleBadge from './SensibleBadge'
import './habilitations.css'

function NoeudRepliable({ ouvert, onBasculer, id, contenu, enfants }) {
  return (
    <li className="hab-arbre-noeud">
      <button
        type="button"
        className="hab-arbre-bascule"
        onClick={onBasculer}
        data-testid={`arbre-bascule-${id}`}
        aria-expanded={ouvert}
      >
        <i className={`bi ${ouvert ? 'bi-dash-square' : 'bi-plus-square'} me-1`} />
        {contenu}
      </button>
      {ouvert && enfants && <ul className="hab-arbre">{enfants}</ul>}
    </li>
  )
}

export default function AccesEffectifs({ userIdInitial: userIdInitialProp = '' }) {
  const [params] = useSearchParams()
  const userIdInitial = userIdInitialProp || params.get('user') || ''
  const [userId, setUserId] = useState(userIdInitial)
  const [donnees, setDonnees] = useState(null)
  const [chargement, setChargement] = useState(false)
  const [erreur, setErreur] = useState('')
  const [ouverts, setOuverts] = useState({})
  const [comptes, setComptes] = useState([])

  const analyser = async (cible) => {
    const cibleNettoyee = (cible ?? userId).trim()
    if (!cibleNettoyee) return
    setChargement(true)
    setErreur('')
    try {
      setDonnees(await impactUtilisateur(cibleNettoyee))
      setOuverts({})
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

  // Sélecteur d'utilisateur : premières comptes de la liste réelle
  // (pagination console). La saisie manuelle de l'identifiant reste possible.
  useEffect(() => {
    listerComptes({ page: 1 }).then((r) => {
      setComptes(r.results || r || [])
    }).catch(() => {})
    // eslint-disable-next-line react-hooks/exhaustive-deps -- chargement initial uniquement
  }, [])

  const basculer = (cle) =>
    setOuverts((etat) => ({ ...etat, [cle]: !etat[cle] }))

  return (
    <section data-testid="ecran-acces-effectifs">
      <div className="hab-carte">
        <h2 className="h5">
          <i className="bi bi-diagram-2 me-2" />Accès effectifs
        </h2>
        <p className="hab-muted">
          Utilisateur → Rôle → Module → Permission. Chaque branche est dérivée
          des attributions et dérogations effectives du compte (moteur CURP) ;
          les octrois directs et retraits actifs sont distingués, avec la
          période de validité, l'attribuant et le périmètre.
        </p>
        <div className="hab-filtres">
          <div>
            <label className="form-label hab-muted mb-1" htmlFor="acces-effectifs-choix">
              Choisir un compte
            </label>
            <select
              id="acces-effectifs-choix"
              className="form-control"
              data-testid="acces-effectifs-choix"
              value={comptes.some((c) => String(c.user_id) === userId) ? userId : ''}
              onChange={(e) => { setUserId(e.target.value); analyser(e.target.value) }}
            >
              <option value="">— Sélectionner —</option>
              {comptes.map((c) => {
                // L'endpoint impact/utilisateur attend la PK Django, pas la PK CURP.
                const identifiant = String(c.user_id)
                return (
                  <option key={identifiant} value={identifiant}>
                    {identifiant} — {c.username}{c.nom ? ` (${c.nom})` : ''}
                  </option>
                )
              })}
            </select>
          </div>
          <div>
            <label className="form-label hab-muted mb-1" htmlFor="acces-effectifs-id-label">
              Ou saisir un identifiant
            </label>
            <input
              id="acces-effectifs-id-label"
              className="form-control"
              placeholder="Identifiant du compte Django…"
              data-testid="acces-effectifs-id"
              value={userId}
              onChange={(e) => setUserId(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && analyser()}
            />
          </div>
          <div className="align-self-end">
            <button
              className="btn btn-primary btn-sm"
              data-testid="acces-effectifs-analyser"
              onClick={() => analyser()}
              disabled={!userId.trim() || chargement}
            >
              Analyser
            </button>
          </div>
        </div>
      </div>

      {chargement && <EnChargement message="Construction de l'arbre…" />}
      {erreur && (
        <div
          className="hab-carte hab-avertissement"
          data-testid="acces-effectifs-erreur"
        >
          {erreur}
        </div>
      )}

      {donnees && !chargement && <Arbre donnees={donnees} ouverts={ouverts} basculer={basculer} />}
    </section>
  )
}

function Arbre({ donnees, ouverts, basculer }) {
  return (
    <div className="hab-carte" data-testid="acces-effectifs-resultat">
      <h3 className="h6 mb-2">
        {donnees.username}{' '}
        <span className={`hab-statut hab-statut-${donnees.statut}`}>
          {donnees.statut}
        </span>{' '}
        — {donnees.total_effectives} accès effectifs
      </h3>
      <ul className="hab-arbre" data-testid="arbre-acces">
        {donnees.arbre.roles.length === 0 &&
          donnees.arbre.derogations.length === 0 &&
          donnees.arbre.retraits.length === 0 && (
            <li className="hab-muted" data-testid="arbre-acces-vide">
              Aucun accès attribué.
            </li>
          )}
        {donnees.arbre.roles.map((r) => {
          const cle = `role-${r.code}`
          return (
            <NoeudRepliable
              key={cle}
              ouvert={ouverts[cle] !== false}
              onBasculer={() => basculer(cle)}
              id={`role-${r.code}`}
              contenu={
                <span>
                  {r.libelle} <code>{r.code}</code>{' '}
                  <SensibleBadge type="role" niveau={r.sensible} />
                  <span className="hab-muted ms-1">
                    Niv. {r.niveau_effectif}
                  </span>
                  <span
                    className="hab-muted ms-2 d-inline-block"
                    data-testid={`acces-effectifs-meta-${r.code}`}
                  >
                    {(r.date_debut || r.date_fin) && (
                      <span data-testid={`acces-effectifs-periode-${r.code}`}>
                        <i className="bi bi-calendar3 me-1" aria-hidden="true" />
                        {r.date_debut || '…'} → {r.date_fin || 'sans échéance'}
                      </span>
                    )}
                    {r.attribue_par && (
                      <span className="ms-2" data-testid={`acces-effectifs-attribue-par-${r.code}`}>
                        <i className="bi bi-person-check me-1" aria-hidden="true" />
                        par {r.attribue_par}
                      </span>
                    )}
                    {(r.perimetres?.length ?? 0) > 0 && (
                      <span className="ms-2" data-testid={`acces-effectifs-perimetres-${r.code}`}>
                        <i className="bi bi-geo me-1" aria-hidden="true" />
                        {r.perimetres.map((p) => p.libelle).join(', ')}
                      </span>
                    )}
                  </span>
                </span>
              }
              enfants={r.modules.map((m) => (
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
            />
          )
        })}
        {donnees.arbre.derogations.map((codeP) => (
          <li key={`arbre-octroi-${codeP}`}>
            <span className="hab-arbre-role">
              <i className="bi bi-key me-1" />Octroi direct (dérogation)
            </span>
            <ul><li><code>{codeP}</code></li></ul>
          </li>
        ))}
        {donnees.arbre.retraits.map((codeP) => (
          <li key={`arbre-retrait-${codeP}`}>
            <span className="hab-arbre-role text-danger">
              <i className="bi bi-slash-circle me-1" />Retrait actif
            </span>
            <ul><li><code>{codeP}</code></li></ul>
          </li>
        ))}
      </ul>

      {(donnees.delegations_recues?.length ?? 0) > 0 && (
        <div className="mt-2" data-testid="acces-effectifs-delegations">
          <h4 className="h6">
            <i className="bi bi-person-check me-1" />Délégations reçues
            ({donnees.delegations_recues.length})
          </h4>
          <ul className="mb-0">
            {donnees.delegations_recues.map((d, index) => (
              <li key={`delegation-${d.id ?? index}`}>
                {d.delegant?.username
                  ? `${d.delegant.username} → ${donnees.username}`
                  : `Délégation #${d.id ?? index}`}
                {d.roles?.length ? ` — rôles : ${d.roles.join(', ')}` : ''}
                {d.date_fin ? ` — jusqu'au ${d.date_fin}` : ''}
              </li>
            ))}
          </ul>
        </div>
      )}

      {(donnees.actions_sensibles_effectives?.length ?? 0) > 0 && (
        <div className="mt-2" data-testid="acces-effectifs-actions-sensibles">
          <h4 className="h6 text-danger">
            <i className="bi bi-exclamation-triangle me-1" />Actions sensibles effectives
            ({donnees.actions_sensibles_effectives.length})
          </h4>
          <ul className="mb-0">
            {donnees.actions_sensibles_effectives.map((codeP) => (
              <li key={codeP}><code>{codeP}</code></li>
            ))}
          </ul>
        </div>
      )}

      {donnees.modules_effectifs && donnees.modules_effectifs.length > 0 && (
        <div className="mt-2" data-testid="acces-effectifs-modules">
          <h4 className="h6">
            <i className="bi bi-grid me-1" />Modules accessibles
            ({donnees.modules_effectifs.length})
          </h4>
          <ul className="mb-0">
            {donnees.modules_effectifs.map((m) => (
              <li key={`module-${m.module}`}>
                {m.module_libelle || m.module}{' '}
                <span className="hab-muted">({m.permissions?.length ?? '?'} permission(s))</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
