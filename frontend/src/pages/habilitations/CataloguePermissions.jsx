/** CataloguePermissions — catalogue humain des permissions CURP
 * (module.ressource.action, criticité, rôles octroyants, impact).
 *
 * Additive : consomme l'API existante GET /api/habilitations/permissions/
 * (pagination serveur, filtres serveur module/ressource/action/criticité/q)
 * et ouvre la vue d'impact de chaque permission (?code=…). Chaque ligne
 * porte le nombre RÉEL de rôles qui l'octroient (M2M du référentiel).
 * Aucune logique métier dupliquée.
 */
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { listerPermissions } from '@/services/habilitations'
import { EnChargement } from './partages'
import SensibleBadge from './SensibleBadge'
import './habilitations.css'

const CRITICITES = ['', 'NORMALE', 'SENSIBLE', 'CRITIQUE']

export default function CataloguePermissions() {
  const [page, setPage] = useState(1)
  const [donnees, setDonnees] = useState(null)
  const [filtres, setFiltres] = useState({
    q: '', module: '', ressource: '', action: '', criticite: '',
  })
  const [erreur, setErreur] = useState('')

  const majFiltre = (cle) => (e) => {
    setFiltres((f) => ({ ...f, [cle]: e.target.value }))
    setPage(1)
  }

  useEffect(() => {
    const actifs = Object.fromEntries(
      Object.entries(filtres).filter(([, v]) => v !== ''),
    )
    listerPermissions({ page, ...actifs })
      .then(setDonnees)
      .catch((e) => setErreur(
        e?.response?.data?.detail || 'Catalogue des permissions indisponible.'
      ))
  }, [page, filtres])

  if (erreur) {
    return (
      <section data-testid="ecran-catalogue-permissions">
        <div className="hab-carte hab-avertissement" data-testid="catalogue-erreur">
          {erreur}
        </div>
      </section>
    )
  }
  if (!donnees) {
    return (
      <section data-testid="ecran-catalogue-permissions">
        <EnChargement message="Chargement du catalogue…" />
      </section>
    )
  }

  const lignes = donnees.results

  return (
    <section data-testid="ecran-catalogue-permissions">
      <div className="hab-carte">
        <h2 className="h5">
          <i className="bi bi-list-columns me-2" />Catalogue des permissions
        </h2>
        <p className="hab-muted">
          Décomposition humaine <code>module.ressource.action</code> du
          référentiel CURP. La criticité provient du référentiel chargé ; le
          lien d'impact ouvre la vue « qui est concerné » de chaque permission.
        </p>
        <div className="hab-filtres">
          <div>
            <label className="form-label hab-muted mb-1" htmlFor="catalogue-q">Recherche</label>
            <input
              id="catalogue-q" className="form-control"
              placeholder="Code ou libellé…"
              data-testid="catalogue-filtre"
              value={filtres.q}
              onChange={majFiltre('q')}
            />
          </div>
          <div>
            <label className="form-label hab-muted mb-1" htmlFor="catalogue-module">Module</label>
            <input
              id="catalogue-module" className="form-control" style={{ maxWidth: 160 }}
              placeholder="ex. scolarite" data-testid="catalogue-module"
              value={filtres.module} onChange={majFiltre('module')}
            />
          </div>
          <div>
            <label className="form-label hab-muted mb-1" htmlFor="catalogue-ressource">Ressource</label>
            <input
              id="catalogue-ressource" className="form-control" style={{ maxWidth: 140 }}
              placeholder="ex. note" data-testid="catalogue-ressource"
              value={filtres.ressource} onChange={majFiltre('ressource')}
            />
          </div>
          <div>
            <label className="form-label hab-muted mb-1" htmlFor="catalogue-action">Action</label>
            <input
              id="catalogue-action" className="form-control" style={{ maxWidth: 130 }}
              placeholder="ex. valider" data-testid="catalogue-action"
              value={filtres.action} onChange={majFiltre('action')}
            />
          </div>
          <div>
            <label className="form-label hab-muted mb-1" htmlFor="catalogue-criticite">Criticité</label>
            <select
              id="catalogue-criticite" className="form-select"
              data-testid="catalogue-criticite" value={filtres.criticite}
              onChange={majFiltre('criticite')}
            >
              {CRITICITES.map((c) => (
                <option key={c} value={c}>{c || 'Toutes'}</option>
              ))}
            </select>
          </div>
        </div>
        <table className="hab-table" data-testid="catalogue-table">
          <thead>
            <tr><th>Code</th><th>Libellé</th><th>Module</th><th>Sensibilité</th><th>Rôles octroyants</th><th>Impact</th></tr>
          </thead>
          <tbody>
            {lignes.map((p) => (
              <tr key={p.code} data-testid={`catalogue-ligne-${p.code}`}>
                <td><code>{p.code}</code></td>
                <td>{p.libelle}</td>
                <td>{p.module}</td>
                <td>
                  <SensibleBadge type="permission" niveau={p.criticite} />
                  {p.necessite_motif && (
                    <span className="hab-muted ms-1" title="Motif obligatoire">
                      <i className="bi bi-chat-left-text" />
                    </span>
                  )}
                </td>
                <td data-testid={`catalogue-roles-${p.code}`}>
                  {p.total_roles ?? '—'}
                </td>
                <td>
                  <Link
                    className="hab-lien-impact"
                    title={`Impact de la permission ${p.code}`}
                    data-testid={`catalogue-impact-${p.code}`}
                    to={`/administration/comptes/impact-permission?code=${encodeURIComponent(p.code)}`}
                  >
                    <i className="bi bi-crosshair" aria-hidden="true" />
                  </Link>
                </td>
              </tr>
            ))}
            {lignes.length === 0 && (
              <tr><td colSpan="6" className="hab-muted">Aucune permission ne correspond aux filtres.</td></tr>
            )}
          </tbody>
        </table>
        <div className="d-flex justify-content-between align-items-center mt-2">
          <span className="hab-muted" data-testid="catalogue-total">
            {donnees.count} permissions au total — page {page} sur{' '}
            {Math.max(1, Math.ceil(donnees.count / 50))}
          </span>
          <div>
            <button className="btn btn-sm btn-outline-secondary me-1"
                    data-testid="catalogue-precedente"
                    disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
              Précédente
            </button>
            <button className="btn btn-sm btn-outline-secondary"
                    data-testid="catalogue-suivante"
                    disabled={page * 50 >= donnees.count}
                    onClick={() => setPage((p) => p + 1)}>
              Suivante
            </button>
          </div>
        </div>
      </div>
    </section>
  )
}
