/** MatricePermissions — visualisation croisée rôle × module, filtrable, exportable.
 *
 * Couche IMPACT (additive) : chaque rôle porte un lien direct vers sa vue
 * d'impact (?code=…) — la matrice reste une lecture niveaux uniquement.
 */
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { recupererMatrice } from '@/services/habilitations'
import { telechargerCsv } from '@/utils/habilitations'
import { EnChargement } from './partages'
import './habilitations.css'

const exporter = (matrice) => {
  telechargerCsv(
    'matrice_habilitations_injs.csv',
    ['role', ...matrice.modules.map((m) => m.code)],
    matrice.lignes.map((l) => [
      l.code,
      ...matrice.modules.map((m) => l.niveaux[m.code]?.niveau || ''),
    ]),
  )
}

export default function MatricePermissions() {
  const [matrice, setMatrice] = useState(null)
  const [filtre, setFiltre] = useState('')
  const [domaine, setDomaine] = useState('')
  const [detaillee, setDetaillee] = useState(false)

  useEffect(() => { recupererMatrice().then(setMatrice).catch(() => setMatrice(null)) }, [])

  const domaines = useMemo(
    () => (matrice ? Array.from(new Set(matrice.lignes.map((l) => l.domaine))) : []),
    [matrice],
  )
  const lignes = useMemo(() => {
    if (!matrice) return []
    return matrice.lignes.filter((l) =>
      (!domaine || l.domaine === domaine) &&
      (!filtre || `${l.code} ${l.libelle}`.toLowerCase().includes(filtre.toLowerCase())))
  }, [matrice, filtre, domaine])

  if (!matrice) return <EnChargement message="Chargement de la matrice…" />

  return (
    <section data-testid="ecran-matrice">
      <div className="hab-carte">
        <div className="d-flex justify-content-between align-items-center flex-wrap gap-2">
          <h2 className="h5 mb-0">Matrice rôle × module</h2>
          <div className="d-flex gap-2 align-items-center">
            <div className="form-check" title="Afficher les actions réellement octroyées (source : rôles du référentiel)">
              <input
                className="form-check-input" type="checkbox" id="matrice-detaillee"
                data-testid="matrice-detaillee" checked={detaillee}
                onChange={(e) => setDetaillee(e.target.checked)}
              />
              <label className="form-check-label hab-muted" htmlFor="matrice-detaillee">
                Vue détaillée (actions réelles)
              </label>
            </div>
            <button className="btn btn-outline-success btn-sm" data-testid="export-matrice"
                    onClick={() => exporter(matrice)}>
              <i className="bi bi-download me-1" />Exporter (CSV)
            </button>
          </div>
        </div>
        <p className="hab-muted mt-1 mb-2">
          Les niveaux provisoires (modules hors annexe A2, à valider à l'atelier J2) sont
          signalés par un contour pointillé. N0 lecture très limitée → N4 administration.
          En vue détaillée, chaque cellule liste les actions réellement octroyées par le
          rôle pour le module (source de vérité : permissions du rôle), avec le nombre de
          comptes titulaires.
        </p>
        <div className="hab-filtres">
          <input className="form-control" placeholder="Rechercher un rôle…" value={filtre}
                 data-testid="filtre-matrice" onChange={(e) => setFiltre(e.target.value)} />
          <select className="form-select" value={domaine} onChange={(e) => setDomaine(e.target.value)}>
            <option value="">Tous domaines</option>
            {domaines.map((d) => <option key={d} value={d}>{d}</option>)}
          </select>
        </div>
        <div style={{ overflow: 'auto', maxHeight: '68vh' }}>
          <table className="hab-matrice">
            <thead>
              <tr>
                <th style={{ position: 'sticky', left: 0, background: '#f4f7fb' }}>Rôle</th>
                {matrice.modules.map((m) => <th key={m.code} title={m.libelle}>{m.code}</th>)}
              </tr>
            </thead>
            <tbody>
              {lignes.map((l) => (
                <tr key={l.code}>
                  <td style={{ position: 'sticky', left: 0, background: '#fff', textAlign: 'left', whiteSpace: 'nowrap' }}>
                    {l.sensible && <i className="bi bi-shield-exclamation text-danger me-1" title="Sensible" />}
                    {l.libelle}
                    {typeof l.comptes_titulaires === 'number' && (
                      <span className="hab-muted ms-1" data-testid={`matrice-titulaires-${l.code}`}
                            title="Comptes titulaires (attributions actives)">
                        ({l.comptes_titulaires})
                      </span>
                    )}
                    <Link
                      className="hab-lien-impact ms-1"
                      title={`Impact du rôle ${l.code}`}
                      data-testid={`lien-impact-matrice-${l.code}`}
                      to={`/administration/comptes/impact-role?code=${encodeURIComponent(l.code)}`}
                    >
                      <i className="bi bi-crosshair" aria-hidden="true" />
                    </Link>
                  </td>
                  {matrice.modules.map((m) => {
                    const case_ = l.niveaux[m.code]
                    if (!case_) return <td key={m.code}>—</td>
                    const actions = detaillee ? (l.actions_par_module?.[m.code] || []) : null
                    return (
                      <td key={m.code} className={`hab-niveau-${case_.niveau} ${case_.origine === 'J2' ? 'hab-provisoire' : ''}`}
                          title={case_.origine === 'J2' ? `Provisoire J2 — ${m.libelle}` : m.libelle}>
                        {case_.niveau}
                        {detaillee && (
                          <div className="hab-matrice-actions" data-testid={`matrice-actions-${l.code}-${m.code}`}>
                            {actions.length === 0
                              ? <span className="hab-muted">aucune</span>
                              : actions.map((a) => <div key={a}>{a}</div>)}
                          </div>
                        )}
                      </td>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  )
}
