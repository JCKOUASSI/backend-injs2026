import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import api from '../../services/api'
import { useToast } from '../../context/ToastContext'
import { formatApiErrors } from '../../utils/apiErrors'
import '../../styles/ecransGeneriques.css'

/**
 * GET INJS APP — « Versions & publication ».
 *
 * Chaque emploi du temps est versionné (V1, V2, V3…) et une version publiée
 * n'est jamais écrasée. Cet écran expose cette mémoire :
 *
 *  - la liste réelle des versions (`/api/edts/lmd/versions/`), avec statut,
 *    auteur de création, auteur de validation, auteur de publication et motif
 *    de modification ;
 *  - pour la version sélectionnée, **l'audit réel** (`/api/edts/lmd/<id>/audit/`) :
 *    violations, avertissements, couverture ;
 *  - les gestes explicites « Valider » puis « Publier », qui passent par le
 *    serveur — l'écran ne décide jamais à la place du moteur.
 *
 * Aucune donnée n'est inventée : une version sans séances affiche « — », un
 * audit en échec affiche le motif du refus tel que le serveur le renvoie.
 */

const STATUTS = {
  BROUILLON: { libelle: 'Brouillon', classe: 'badge-neutral' },
  EN_VALIDATION: { libelle: 'En validation', classe: 'badge-info' },
  VALIDE: { libelle: 'Validé', classe: 'badge-success' },
  PUBLIE: { libelle: 'Publié', classe: 'badge-success' },
  ARCHIVE: { libelle: 'Archivé', classe: 'badge-neutral' },
}

function Badge({ statut }) {
  const info = STATUTS[statut] || { libelle: statut || '—', classe: 'badge-neutral' }
  return <span className={`badge ${info.classe}`}>{info.libelle}</span>
}

function dateLisible(valeur) {
  if (!valeur) return '—'
  const d = new Date(valeur)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleString('fr-FR', { dateStyle: 'short', timeStyle: 'short' })
}

export default function VersionsPublication() {
  const { showToast } = useToast()
  const [versions, setVersions] = useState([])
  const [chargement, setChargement] = useState(true)
  const [erreur, setErreur] = useState('')
  const [selection, setSelection] = useState(null)
  const [audit, setAudit] = useState(null)
  const [auditEnCours, setAuditEnCours] = useState(false)
  const [actionEnCours, setActionEnCours] = useState('')

  const charger = useCallback(async () => {
    setChargement(true)
    setErreur('')
    try {
      const { data } = await api.get('/edts/lmd/versions/')
      setVersions(data?.versions || [])
    } catch (e) {
      setErreur(formatApiErrors(e?.response?.data, {
        fallback: 'Impossible de charger les versions.',
      }))
    } finally {
      setChargement(false)
    }
  }, [])

  useEffect(() => { charger() }, [charger])

  const auditer = useCallback(async (id) => {
    if (!id) return
    setAuditEnCours(true)
    setAudit(null)
    try {
      const { data } = await api.get(`/edts/lmd/${id}/audit/`)
      setAudit(data)
    } catch (e) {
      setErreur(formatApiErrors(e?.response?.data, {
        fallback: 'Impossible d’auditer cette version.',
      }))
    } finally {
      setAuditEnCours(false)
    }
  }, [])

  useEffect(() => {
    if (selection) auditer(selection.id)
  }, [selection, auditer])

  const agir = async (chemin, libelleSucces) => {
    if (!selection) return
    setActionEnCours(chemin)
    try {
      const { data } = await api.post(`/edts/lmd/${selection.id}/${chemin}/`, {})
      if (chemin === 'validate' && data?.valide === false) {
        // Un refus n'est pas un succès : on affiche le motif réel.
        setAudit((a) => ({ ...(a || {}), violations: data.violations || [] }))
        showToast?.('Validation refusée : des contraintes obligatoires sont violées.', 'danger')
      } else {
        showToast?.(libelleSucces, 'success')
      }
      await charger()
      await auditer(selection.id)
    } catch (e) {
      showToast?.(formatApiErrors(e?.response?.data, {
        fallback: 'L’action a été refusée par le serveur.',
      }), 'danger')
    } finally {
      setActionEnCours('')
    }
  }

  const violations = audit?.violations || []
  const warnings = audit?.warnings || []
  const couverture = audit?.couverture || null

  const lignes = useMemo(() => versions, [versions])

  return (
    <div className="getinjs-page">
      <div className="getinjs-entete">
        <div>
          <h4 className="mb-1">Versions &amp; publication</h4>
          <p className="text-muted mb-0">
            Historique des emplois du temps (V1, V2, …) — une version publiée
            n’est jamais écrasée. Valider et publier se font ici, après audit.
          </p>
        </div>
        <button className="btn btn-outline-secondary btn-sm" onClick={charger} disabled={chargement}>
          <i className="bi bi-arrow-clockwise me-1"></i>Actualiser
        </button>
      </div>

      {erreur && <div className="alert alert-danger" role="alert">{erreur}</div>}

      {chargement ? (
        <p className="text-muted">Chargement des versions…</p>
      ) : lignes.length === 0 ? (
        <div className="alert alert-info">
          Aucune version enregistrée. Générez un emploi du temps depuis{' '}
          <Link to="/edt/campagnes">Campagnes de génération</Link> ou{' '}
          <Link to="/edt/generation-annuelle">Génération annuelle</Link>.
        </div>
      ) : (
        <div className="row g-3">
          <div className="col-lg-7">
            <div className="table-responsive">
              <table className="table table-sm align-middle">
                <caption className="visually-hidden">
                  Versions d’emplois du temps, de la plus récente à la plus ancienne
                </caption>
                <thead>
                  <tr>
                    <th scope="col">Version</th>
                    <th scope="col">EDT</th>
                    <th scope="col">Année</th>
                    <th scope="col">Statut</th>
                    <th scope="col">Séances</th>
                    <th scope="col">Créée par</th>
                  </tr>
                </thead>
                <tbody>
                  {lignes.map((v) => (
                    <tr
                      key={v.id}
                      className={selection?.id === v.id ? 'table-active' : ''}
                      style={{ cursor: 'pointer' }}
                      onClick={() => setSelection(v)}
                    >
                      <td><strong>{v.libelle}</strong></td>
                      <td>{v.titre || '—'}</td>
                      <td>{v.annee_academique}</td>
                      <td><Badge statut={v.statut} /></td>
                      <td>{v.nb_seances ?? '—'}</td>
                      <td>{v.creee_par || '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="col-lg-5">
            {!selection ? (
              <div className="alert alert-secondary">
                Sélectionnez une version pour afficher son audit et les actions
                de validation / publication.
              </div>
            ) : (
              <div className="card">
                <div className="card-body">
                  <h5 className="card-title">
                    {selection.libelle} — {selection.titre || 'emploi du temps'}
                  </h5>
                  <p className="mb-1">
                    <Badge statut={selection.statut} />{' '}
                    <span className="text-muted">année {selection.annee_academique}</span>
                  </p>
                  <dl className="row mb-2 small">
                    <dt className="col-6">Créée le</dt>
                    <dd className="col-6">{dateLisible(selection.creee_le)}</dd>
                    <dt className="col-6">Validée le</dt>
                    <dd className="col-6">{dateLisible(selection.validee_le)}</dd>
                    <dt className="col-6">Publiée le</dt>
                    <dd className="col-6">{dateLisible(selection.publiee_le)}</dd>
                    <dt className="col-6">Motif</dt>
                    <dd className="col-6">{selection.motif_modification || '—'}</dd>
                  </dl>

                  {auditEnCours && <p className="text-muted">Audit en cours…</p>}

                  {audit && !auditEnCours && (
                    <div className="mb-2">
                      <p className="mb-1">
                        <strong>Audit :</strong>{' '}
                        {audit.statut === 'OK'
                          ? <span className="badge badge-success">Conforme</span>
                          : audit.statut === 'BLOQUANT'
                            ? <span className="badge badge-danger">Bloquant</span>
                            : <span className="badge badge-warning">{audit.statut || '—'}</span>}
                      </p>
                      {violations.length > 0 && (
                        <ul className="small text-danger mb-1">
                          {violations.map((v, i) => (
                            <li key={`${v.code || 'V'}-${i}`}>
                              <strong>{v.code || 'VIOLATION'}</strong> — {v.message || v.libelle || '—'}
                            </li>
                          ))}
                        </ul>
                      )}
                      {warnings.length > 0 && (
                        <ul className="small text-warning-emphasis mb-1">
                          {warnings.map((w, i) => (
                            <li key={`W-${i}`}>{typeof w === 'string' ? w : (w.message || '—')}</li>
                          ))}
                        </ul>
                      )}
                      {couverture && (
                        <p className="small text-muted mb-1">
                          Couverture : {couverture.seances_placees ?? '—'} /{' '}
                          {couverture.seances_attendues ?? '—'} séance(s)
                        </p>
                      )}
                    </div>
                  )}

                  <div className="d-flex gap-2">
                    <button
                      className="btn btn-sm btn-primary"
                      onClick={() => agir('validate', 'Version validée.')}
                      disabled={!!actionEnCours || selection.statut === 'PUBLIE'}
                    >
                      {actionEnCours === 'validate' ? 'Validation…' : 'Valider'}
                    </button>
                    <button
                      className="btn btn-sm btn-success"
                      onClick={() => agir('publish', 'Version publiée.')}
                      disabled={
                        !!actionEnCours
                        || selection.statut === 'PUBLIE'
                        || selection.statut !== 'VALIDE'
                      }
                      title={
                        selection.statut !== 'VALIDE'
                          ? 'Une version doit être validée avant publication.'
                          : undefined
                      }
                    >
                      {actionEnCours === 'publish' ? 'Publication…' : 'Publier'}
                    </button>
                  </div>
                  <p className="small text-muted mt-2 mb-0">
                    La validation revérifie chaque séance (C1 à C9) côté serveur.
                    Une contrainte obligatoire violée bloque la publication.
                  </p>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
