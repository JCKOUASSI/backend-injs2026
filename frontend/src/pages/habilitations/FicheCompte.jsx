/** FicheCompte — identité, rôles, dérogations, délégations, MFA,
 * permissions effectives, journal. */
import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  recupererCompte, changerStatutCompte, messageErreur, permissionsEffectives,
} from '@/services/habilitations'
import { mfaSetup, mfaConfirm, mfaDisable, messageErreurMfa } from '@/services/mfa'
import { useToast } from '@/context/ToastContext'
import { BadgeCanal, BadgeSensible, BadgeStatut, EnChargement } from './partages'
import SensibleBadge from './SensibleBadge'
import MotifModal from './MotifModal'
import './habilitations.css'

const TRANSITIONS = [
  { transition: 'suspendre', label: 'Suspendre', variant: 'danger' },
  { transition: 'desactiver', label: 'Désactiver', variant: 'danger' },
  { transition: 'verrouiller', label: 'Verrouiller', variant: 'danger' },
  { transition: 'activer', label: 'Réactiver / activer', variant: 'success' },
]

function Section({ titre, valeur, children }) {
  return (
    <div className="hab-carte">
      <h3 className="h6">{titre}</h3>
      {valeur ? <p className="hab-muted mb-0">{valeur}</p> : children}
    </div>
  )
}

export default function FicheCompte() {
  const { id } = useParams()
  const { showToast } = useToast()
  const [compte, setCompte] = useState(null)
  const [erreur, setErreur] = useState('')
  const [action, setAction] = useState(null)
  // Permissions effectives (rôles actifs + dérogations), lecture seule.
  const [perms, setPerms] = useState(null)
  // Bloc MFA : null (masqué) | { secret, otpauth_url } (en cours d'activation).
  const [mfa, setMfa] = useState(null)
  const [codeMfa, setCodeMfa] = useState('')
  const [mfaBusy, setMfaBusy] = useState(false)

  const charger = () => {
    recupererCompte(id).then(setCompte).catch((e) => setErreur(messageErreur(e)))
    permissionsEffectives(id).then(setPerms).catch(() => setPerms(null))
  }
  // Rechargement uniquement au changement d'identifiant de compte.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { charger() }, [id])

  const genererSecretMfa = async () => {
    setMfaBusy(true)
    try {
      const donnees = await mfaSetup(compte.user_id)
      setMfa(donnees)
      setCodeMfa('')
    } catch (e) {
      showToast(messageErreurMfa(e), 'error')
    } finally {
      setMfaBusy(false)
    }
  }

  const confirmerMfa = async () => {
    setMfaBusy(true)
    try {
      await mfaConfirm(compte.user_id, codeMfa)
      showToast('MFA activé pour ce compte.', 'success')
      setMfa(null)
      setCodeMfa('')
      charger()
    } catch (e) {
      showToast(messageErreurMfa(e), 'error')
    } finally {
      setMfaBusy(false)
    }
  }

  const desactiverMfa = async () => {
    if (!window.confirm(
      `Désactiver le MFA du compte ${compte.username} ?\nCette action est tracée au journal immuable.`
    )) return
    setMfaBusy(true)
    try {
      await mfaDisable(compte.user_id)
      showToast('MFA désactivé.', 'success')
      charger()
    } catch (e) {
      showToast(messageErreurMfa(e), 'error')
    } finally {
      setMfaBusy(false)
    }
  }

  const confirmer = async (motif) => {
    try {
      await changerStatutCompte(id, action.transition, motif)
      showToast('Statut mis à jour.', 'success')
      setAction(null)
      charger()
    } catch (e) {
      showToast(messageErreur(e), 'error')
    }
  }

  if (erreur) return <p className="text-danger">{erreur}</p>
  if (!compte) return <EnChargement message="Chargement du compte…" />
  const p = compte.personne || {}

  return (
    <section data-testid="fiche-compte">
      <div className="hab-carte d-flex justify-content-between align-items-start">
        <div>
          <h2 className="h5 mb-1">
            {p.prenoms} {p.nom} <BadgeStatut statut={compte.statut} />
            {compte.nb_roles_sensibles > 0 && <BadgeSensible />}
          </h2>
          <div className="hab-muted">{compte.username} · {compte.email} · <BadgeCanal canal={compte.canal} /></div>
          <div className="hab-muted">Rôle d'accès actuel (provisoire) : {compte.role_legacy}</div>
          {p.matricule && <div className="hab-muted">Matricule personne : {p.matricule}{p.service ? ` · ${p.service}` : ''}</div>}
        </div>
        <div>
          <Link className="btn btn-success btn-sm" to={`/administration/comptes/${id}/modifier`}>
            <i className="bi bi-pencil-square me-1" />Modifier les droits
          </Link>
        </div>
      </div>

      <Section titre={`Rôles et périmètres actifs (${compte.roles_actifs.length})`}>
        <table className="hab-table">
          <thead><tr><th>Rôle</th><th>Niveau</th><th>Sensible</th><th>Périmètres</th><th>Validé</th></tr></thead>
          <tbody>
            {compte.roles_actifs.map((r) => (
              <tr key={r.id}>
                <td>{r.role_libelle} <code className="small">{r.role}</code></td>
                <td>{r.niveau}</td>
                <td>{r.sensible ? <BadgeSensible avecLabel={false} /> : '—'}</td>
                <td>{(r.perimetres || []).map((x) => x.libelle || x.reference_lisible).join(', ') || '—'}</td>
                <td>{r.validee ? 'Oui' : 'Non'}</td>
              </tr>
            ))}
            {compte.roles_actifs.length === 0 && <tr><td colSpan="5" className="hab-muted">Aucun rôle actif.</td></tr>}
          </tbody>
        </table>
        {compte.roles_inactifs?.length > 0 && (
          <details className="mt-2">
            <summary className="hab-muted">Rôles passés / révoqués ({compte.roles_inactifs.length})</summary>
            <ul className="small mb-0">{compte.roles_inactifs.map((r) => <li key={r.id}>{r.role} — {r.statut}</li>)}</ul>
          </details>
        )}
      </Section>

      <Section titre={`Dérogations (${compte.derogations?.length || 0})`}>
        {compte.derogations?.length ? (
          <ul className="mb-0">
            {compte.derogations.map((d) => (
              <li key={d.id}>{d.sens === 'OCTROI' ? 'Octroi' : 'Retrait'} de <code>{d.permission}</code> — {d.statut}</li>
            ))}
          </ul>
        ) : <p className="hab-muted mb-0">Aucune dérogation.</p>}
      </Section>

      <Section titre={`Délégations (${(compte.delegations_recues?.length || 0)})`}>
        {compte.delegations_recues?.length ? (
          <ul className="mb-0">
            {compte.delegations_recues.map((d) => (
              <li key={d.id}>De {d.delegant} jusqu'au {d.date_fin} — {d.statut}</li>
            ))}
          </ul>
        ) : <p className="hab-muted mb-0">Aucune délégation reçue.</p>}
      </Section>

      <Section titre="MFA (authentification multifacteur)">
        <div className="d-flex align-items-center gap-2">
          <span className={`badge ${compte.mfa_actif ? 'text-bg-success' : 'text-bg-secondary'}`}>
            {compte.mfa_actif ? 'Activé (TOTP)' : 'Désactivé'}
          </span>
          {compte.mfa_actif ? (
            <button
              type="button"
              className="btn btn-sm btn-outline-danger"
              data-testid="mfa-desactiver"
              disabled={mfaBusy}
              onClick={desactiverMfa}
            >
              <i className="bi bi-shield-slash me-1" />Désactiver le MFA
            </button>
          ) : (
            <button
              type="button"
              className="btn btn-sm btn-outline-primary"
              data-testid="mfa-activer"
              disabled={mfaBusy}
              onClick={() => setMfa(mfa ? null : { secret: null, otpauth_url: null })}
            >
              <i className="bi bi-shield-check me-1" />
              {mfa ? 'Fermer la configuration' : 'Activer le MFA'}
            </button>
          )}
        </div>
        {!compte.mfa_actif && mfa && (
          <div className="mt-3" data-testid="mfa-configuration">
            <ol className="small">
              <li>
                {mfa.secret ? (
                  <>Secret armé : <code>{mfa.secret}</code></>
                ) : (
                  <button
                    type="button"
                    className="btn btn-sm btn-primary"
                    data-testid="mfa-generer"
                    disabled={mfaBusy}
                    onClick={genererSecretMfa}
                  >
                    <i className="bi bi-key me-1" />Générer le secret
                  </button>
                )}
              </li>
              <li>
                {mfa.otpauth_url ? (
                  <>
                    À scanner par l'utilisateur (application TOTP) :<br />
                    <code className="small text-break">{mfa.otpauth_url}</code>
                  </>
                ) : <span className="hab-muted">L'utilisateur scannera l'URI otpauth avec son application.</span>}
              </li>
              <li>
                {mfa.secret ? (
                  <div className="d-flex gap-2 align-items-center">
                    <input
                      className="form-control form-control-sm"
                      style={{ maxWidth: '140px' }}
                      inputMode="numeric"
                      maxLength={6}
                      placeholder="Code 6 chiffres"
                      value={codeMfa}
                      data-testid="mfa-code-confirm"
                      onChange={(e) => setCodeMfa(e.target.value.replace(/\D/g, '').slice(0, 6))}
                    />
                    <button
                      type="button"
                      className="btn btn-sm btn-success"
                      data-testid="mfa-confirmer"
                      disabled={mfaBusy || codeMfa.length !== 6}
                      onClick={confirmerMfa}
                    >
                      Confirmer l'activation
                    </button>
                  </div>
                ) : <span className="hab-muted">Saisissez ensuite le code affiché dans l'application.</span>}
              </li>
            </ol>
          </div>
        )}
      </Section>

      <Section titre={`Permissions effectives (${perms ? perms.count : '…'})`}>
        {perms ? (
          <>
            <p className="hab-muted mb-1">
              Calculé par le backend : rôles actifs (périmètres et échéances)
              plus dérogations actives (octrois ajoutés, retraits soustraits).
            </p>
            {perms.count > 0 ? (
              <details>
                <summary className="hab-muted">Afficher les {perms.count} codes</summary>
                <div className="small" style={{ maxHeight: '260px', overflow: 'auto' }}>
                  {perms.codes.slice(0, 400).map((code) => (
                    <code key={code} className="me-1 mb-1 d-inline-block">{code}</code>
                  ))}
                  {perms.count > 400 && <span className="hab-muted">… et {perms.count - 400} autres.</span>}
                </div>
              </details>
            ) : <p className="hab-muted mb-0">Aucune permission effective (aucun rôle actif ni dérogation).</p>}
            {compte.impact && (
              <p className="hab-muted mb-0" data-testid="fiche-impact-compteurs">
                Origine des accès : hérités des rôles : {compte.impact.total_heritees} ·
                directes (dérogations) : {compte.impact.total_directes} ·
                retraits actifs : {compte.impact.total_retraits} ·
                effectives au total : <strong>{compte.impact.total_effectives}</strong>
              </p>
            )}
          </>
        ) : <p className="hab-muted mb-0">Chargement…</p>}
      </Section>

      {/* Couche IMPACT (additive) : liens contextuels vers l'arbre et la vue
          d'impact de cet utilisateur. Le user_id est l'identifiant attendu
          par l'API (cf. impact/utilisateur/<user_id>/). */}
      <Section titre="Accès effectifs & impact">
        <p className="hab-muted mb-2">
          Arbre lisible Utilisateur → Rôle → Module → Permission, octrois directs
          et retraits actifs distingués — résolu par le moteur CURP.
        </p>
        <Link
          className="btn btn-sm btn-outline-primary me-2"
          data-testid="fiche-lien-acces-effectifs"
          to={`/administration/comptes/acces-effectifs?user=${compte.user_id}`}
        >
          <i className="bi bi-diagram-2 me-1" />Voir l'arbre des accès effectifs
        </Link>
        <Link
          className="btn btn-sm btn-outline-secondary"
          data-testid="fiche-lien-impact-utilisateur"
          to={`/administration/comptes/impact-utilisateur?user=${compte.user_id}`}
        >
          <i className="bi bi-crosshair me-1" />Impact de cet utilisateur
        </Link>
        {compte.impact && compte.impact.actions_sensibles_effectives.length > 0 && (
          <div className="hab-avertissement mt-2" data-testid="fiche-impact-sensibles">
            <SensibleBadge type="acces" critique /> Actions sensibles effectives :{' '}
            {compte.impact.actions_sensibles_effectives.map((c) => (
              <code key={c} className="me-1">{c}</code>
            ))}
          </div>
        )}
      </Section>

      <Section titre="Chronologie (journal)">
        {compte.journal?.length ? (
          <table className="hab-table">
            <thead><tr><th>Date</th><th>Événement</th><th>Motif</th></tr></thead>
            <tbody>
              {compte.journal.map((e) => (
                <tr key={e.numero}><td>{e.horodatage.slice(0, 16).replace('T', ' ')}</td><td>{e.type_libelle}</td><td>{e.motif}</td></tr>
              ))}
            </tbody>
          </table>
        ) : <p className="hab-muted mb-0">Aucun événement.</p>}
      </Section>

      <div className="hab-carte">
        <h3 className="h6">Actions sur le statut</h3>
        {TRANSITIONS.map((t) => (
          <button key={t.transition} className={`btn btn-sm btn-${t.variant === 'danger' ? 'outline-danger' : 'outline-success'} me-2`}
                  data-testid={`action-${t.transition}`}
                  onClick={() => setAction(t)}>{t.label}</button>
        ))}
      </div>

      {action && (
        <MotifModal
          titre={action.label}
          action={`${action.label} le compte ${compte.username}`}
          consequences="Cette action est tracée au journal immuable ; elle peut empêcher la connexion."
          variant={action.variant}
          onConfirmer={confirmer}
          onAnnuler={() => setAction(null)}
        />
      )}
    </section>
  )
}
