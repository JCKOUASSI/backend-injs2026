/** GestionRoles — consultation du référentiel, description et titulaires.
 *
 * Couche IMPACT (additive) : chaque rôle ouvre sa vue d'impact
 * (?code=…) — aucune seconde page équivalente n'est créée.
 * Lot B : versionnement (capture/restauration avec motif obligatoire)
 * et comparaison de deux rôles du référentiel.
 */
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  listerRolesCurp,
  recupererRole,
  listerVersionsRole,
  capturerVersionRole,
  restaurerVersionRole,
  comparerRoles,
  messageErreur,
} from '@/services/habilitations'
import { libelleDomaine } from '@/utils/habilitations'
import { BadgeSensible, BadgeCanal, EnChargement } from './partages'
import './habilitations.css'

export default function GestionRoles() {
  const [roles, setRoles] = useState([])
  const [chargement, setChargement] = useState(true)
  const [erreur, setErreur] = useState('')
  const [detail, setDetail] = useState(null)
  const [versions, setVersions] = useState([])
  const [motif, setMotif] = useState('')
  const [message, setMessage] = useState('')
  const [compareA, setCompareA] = useState('')
  const [compareB, setCompareB] = useState('')
  const [comparaison, setComparaison] = useState(null)
  const [erreurComparaison, setErreurComparaison] = useState('')
  const [filtre, setFiltre] = useState('')

  const chargerRoles = async () => {
    setChargement(true)
    setErreur('')
    try {
      setRoles(await listerRolesCurp())
    } catch (e) {
      setErreur(messageErreur(e, 'Référentiel des rôles indisponible.'))
    } finally {
      setChargement(false)
    }
  }

  useEffect(() => { chargerRoles() }, [])

  const chargerVersions = async (code) => {
    const reponse = await listerVersionsRole(code)
    setVersions(reponse.versions || [])
  }

  const ouvrir = async (code) => {
    setDetail(await recupererRole(code))
    setMotif('')
    setMessage('')
    await chargerVersions(code)
  }

  const capturer = async () => {
    if (!motif.trim()) {
      setMessage('Un motif est obligatoire pour capturer une version.')
      return
    }
    try {
      const version = await capturerVersionRole(detail.code, motif.trim())
      setMessage(`Version ${version.numero} capturée.`)
      setMotif('')
      await chargerVersions(detail.code)
    } catch (e) {
      setMessage(messageErreur(e, 'Capture impossible.'))
    }
  }

  const restaurer = async (numero) => {
    if (!motif.trim()) {
      setMessage('Un motif est obligatoire pour restaurer une version.')
      return
    }
    try {
      await restaurerVersionRole(detail.code, numero, motif.trim())
      setMessage(`Version ${numero} restaurée.`)
      setMotif('')
      setDetail(await recupererRole(detail.code))
      await chargerVersions(detail.code)
    } catch (e) {
      setMessage(messageErreur(e, 'Restauration impossible.'))
    }
  }

  const comparer = async () => {
    setComparaison(null)
    setErreurComparaison('')
    if (!compareA || !compareB || compareA === compareB) {
      setErreurComparaison('Sélectionner deux rôles différents.')
      return
    }
    try {
      setComparaison(await comparerRoles(compareA, { avec: compareB }))
    } catch (e) {
      setErreurComparaison(messageErreur(e, 'Comparaison impossible.'))
    }
  }

  const rolesFiltres = roles.filter((r) =>
    !filtre || `${r.code} ${r.libelle} ${r.domaine}`.toLowerCase().includes(filtre.toLowerCase()))

  if (chargement) return <EnChargement />
  if (erreur) return (
    <section data-testid="ecran-roles">
      <div className="hab-carte hab-avertissement" role="alert" data-testid="roles-erreur">
        <p>{erreur}</p>
        <button type="button" className="btn btn-sm btn-outline-primary" onClick={chargerRoles}>Réessayer</button>
      </div>
    </section>
  )
  return (
    <section data-testid="ecran-roles">
      <div className="hab-carte">
        <h2 className="h5">Référentiel des rôles ({roles.length})</h2>
        <p className="hab-muted">Rôles métier du recueil (annexe A1). Les rôles sensibles sont signalés en rouge.</p>
        <input className="form-control mb-2" placeholder="Filtrer par code, libellé ou domaine…"
               data-testid="filtre-roles" value={filtre}
               onChange={(e) => setFiltre(e.target.value)} />
        <div style={{ maxHeight: 620, overflow: 'auto' }}>
          <table className="hab-table">
            <thead><tr><th>Code</th><th>Libellé</th><th>Domaine</th><th>Niv.</th><th>Permissions</th><th>Disponible</th><th>Impact</th></tr></thead>
            <tbody>
              {rolesFiltres.map((r) => (
                <tr key={r.code} style={{ cursor: 'pointer' }} onClick={() => ouvrir(r.code)}
                    data-testid={`ligne-role-${r.code}`}>
                  <td><code>{r.code}</code>{r.sensible && <BadgeSensible avecLabel={false} />}</td>
                  <td>{r.libelle} <BadgeCanal canal={r.canal_impose} /></td>
                  <td>{libelleDomaine(r.domaine)}</td>
                  <td>{r.niveau_defaut}</td>
                  <td>{r.permissions_count}</td>
                  <td>{r.disponible ? 'Oui' : <span className="text-danger">Module absent</span>}</td>
                  <td>
                    <Link
                      className="hab-lien-impact"
                      title={`Impact du rôle ${r.code}`}
                      data-testid={`lien-impact-role-${r.code}`}
                      to={`/administration/comptes/impact-role?code=${encodeURIComponent(r.code)}`}
                      onClick={(e) => e.stopPropagation()}
                    >
                      <i className="bi bi-crosshair" aria-hidden="true" />
                    </Link>
                  </td>
                </tr>
              ))}
              {rolesFiltres.length === 0 && (
                <tr><td colSpan="7" className="hab-muted text-center py-3">Aucun rôle ne correspond au filtre.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
      {detail && (
        <div className="hab-carte" data-testid="detail-role">
          <h3 className="h6">{detail.libelle} <code>{detail.code}</code></h3>
          <p>{detail.description}</p>
          <div className="hab-muted">Domaine : {libelleDomaine(detail.domaine)} · Périmètre par défaut : {detail.perimetre_defaut}</div>
          {detail.incompatible_avec.length > 0 && (
            <div className="hab-avertissement">
              Incompatible avec : {detail.incompatible_avec.join(', ')}
            </div>
          )}
          <h4 className="h6 mt-2">Comptes titulaires ({detail.comptes_titulaires.length})</h4>
          {detail.comptes_titulaires.length === 0 ? <p className="hab-muted">Aucun titulaire pour l'instant.</p> : (
            <ul className="mb-0">
              {detail.comptes_titulaires.map((c) => (
                <li key={c.compte}>{c.prenoms} {c.nom} ({c.username}) — {c.statut}</li>
              ))}
            </ul>
          )}
          <Link
            className="btn btn-sm btn-outline-primary mt-2"
            data-testid="detail-role-impact"
            to={`/administration/comptes/impact-role?code=${encodeURIComponent(detail.code)}`}
          >
            <i className="bi bi-crosshair me-1" />Voir l'impact de ce rôle
          </Link>
          <button className="btn btn-secondary btn-sm mt-2 ms-2" onClick={() => setDetail(null)}>Fermer</button>

          <hr />
          <h4 className="h6 mt-2">
            <i className="bi bi-clock-history me-2" />Versions ({versions.length})
          </h4>
          {message && (
            <div className="hab-muted" data-testid="versions-message" role="status">{message}</div>
          )}
          <div className="hab-filtres mb-2">
            <div>
              <label className="form-label hab-muted mb-1" htmlFor="motif-version">
                Motif (obligatoire pour capturer ou restaurer)
              </label>
              <input
                id="motif-version"
                className="form-control"
                data-testid="motif-version"
                value={motif}
                onChange={(e) => setMotif(e.target.value)}
                placeholder="Ex. : décision de gouvernance du 06/10…"
              />
            </div>
            <div className="align-self-end">
              <button
                type="button"
                className="btn btn-sm btn-dfrc"
                data-testid="capturer-version"
                onClick={capturer}
              >
                <i className="bi bi-camera me-1" />Capturer une version
              </button>
            </div>
          </div>
          {versions.length === 0 ? (
            <p className="hab-muted mb-0" data-testid="versions-vide">
              Aucune version capturée pour ce rôle.
            </p>
          ) : (
            <table className="hab-table" data-testid="versions-liste">
              <thead>
                <tr><th>N°</th><th>Date</th><th>Source</th><th>Auteur</th><th>Motif</th><th>Action</th></tr>
              </thead>
              <tbody>
                {versions.map((v) => (
                  <tr key={v.numero} data-testid={`version-${v.numero}`}>
                    <td>v{v.numero}</td>
                    <td>{v.instant.replace('T', ' ').slice(0, 16)}</td>
                    <td>{v.source_libelle}</td>
                    <td>{v.auteur || '—'}</td>
                    <td>{v.motif || '—'}</td>
                    <td>
                      <button
                        type="button"
                        className="btn btn-sm btn-outline-danger"
                        data-testid={`restaurer-version-${v.numero}`}
                        title="Restaurer cette version (motif requis)"
                        onClick={() => restaurer(v.numero)}
                      >
                        <i className="bi bi-arrow-counterclockwise me-1" />Restaurer
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      <div className="hab-carte" data-testid="comparaison-roles">
        <h4 className="h6">
          <i className="bi bi-columns-gap me-2" />Comparer deux rôles
        </h4>
        <div className="hab-filtres">
          <div>
            <label className="form-label hab-muted mb-1" htmlFor="comparer-a">Rôle A</label>
            <select
              id="comparer-a"
              className="form-control"
              data-testid="comparer-a"
              value={compareA}
              onChange={(e) => setCompareA(e.target.value)}
            >
              <option value="">— Sélectionner —</option>
              {roles.map((r) => <option key={r.code} value={r.code}>{r.code}</option>)}
            </select>
          </div>
          <div>
            <label className="form-label hab-muted mb-1" htmlFor="comparer-b">Rôle B</label>
            <select
              id="comparer-b"
              className="form-control"
              data-testid="comparer-b"
              value={compareB}
              onChange={(e) => setCompareB(e.target.value)}
            >
              <option value="">— Sélectionner —</option>
              {roles.map((r) => <option key={r.code} value={r.code}>{r.code}</option>)}
            </select>
          </div>
          <div className="align-self-end">
            <button type="button" className="btn btn-sm btn-dfrc" data-testid="lancer-comparaison" onClick={comparer}>
              <i className="bi bi-columns-gap me-1" />Comparer
            </button>
          </div>
        </div>
        {erreurComparaison && (
          <div className="hab-avertissement" data-testid="comparaison-erreur">{erreurComparaison}</div>
        )}
        {comparaison && (
          <div data-testid="comparaison-resultat">
            <p className="hab-muted mb-1">
              <code>{comparaison.role_a.code}</code> → <code>{comparaison.role_b.code}</code>
            </p>
            {comparaison.champs.length > 0 && (
              <table className="hab-table hab-diff-table">
                <thead><tr><th>Champ</th><th>Rôle A</th><th>Rôle B</th></tr></thead>
                <tbody>
                  {comparaison.champs.map((c) => (
                    <tr key={c.champ}>
                      <td>{c.champ}</td>
                      <td>{String(c.avant)}</td>
                      <td>{String(c.apres)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            <div className="hab-diff-listes">
              <div className="hab-diff-ajouts" data-testid="comparaison-ajouts">
                Permissions ajoutées (A → B) :{' '}
                {comparaison.permissions_ajoutees.length === 0
                  ? <em className="hab-muted">aucune</em>
                  : comparaison.permissions_ajoutees.join(', ')}
              </div>
              <div className="hab-diff-retraits" data-testid="comparaison-retraits">
                Permissions retirées (A → B) :{' '}
                {comparaison.permissions_retirees.length === 0
                  ? <em className="hab-muted">aucune</em>
                  : comparaison.permissions_retirees.join(', ')}
              </div>
            </div>
          </div>
        )}
      </div>
    </section>
  )
}
