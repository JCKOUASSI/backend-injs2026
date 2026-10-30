import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import api from '../../services/api'
import { useToast } from '../../context/ToastContext'
import { formatApiErrors } from '../../utils/apiErrors'
import '../../styles/ecransGeneriques.css'

/**
 * GET-INJS APP — « Campagnes de génération ».
 *
 * Une campagne est la trace persistante d'une génération : périmètre, auteur,
 * bilan, anomalies, durée, historique d'exécutions. L'écran ne calcule rien :
 * il crée la campagne, la lance, interroge son état réel et affiche le bilan
 * tel que le moteur le produit — y compris les anomalies et les refus.
 *
 * Règles visibles à l'écran :
 *  - aucun chiffre n'est inventé : avant la première exécution, les compteurs
 *    affichent « — » ;
 *  - une génération impossible est montrée comme un échec, jamais comme un
 *    succès partiel déguisé ;
 *  - valider et publier restent des gestes explicites, réservés à la Direction.
 */

const STATUTS = {
  BROUILLON: { libelle: 'Brouillon', classe: 'badge-neutral' },
  VALIDATION_DONNEES: { libelle: 'Validation des données', classe: 'badge-info' },
  PRET: { libelle: 'Prêt', classe: 'badge-info' },
  EN_COURS: { libelle: 'En cours', classe: 'badge-warning' },
  TERMINE: { libelle: 'Terminé', classe: 'badge-success' },
  TERMINE_AVEC_ANOMALIES: { libelle: 'Terminé avec anomalies', classe: 'badge-warning' },
  ECHEC: { libelle: 'Échec', classe: 'badge-danger' },
  VALIDE: { libelle: 'Validé', classe: 'badge-success' },
  PUBLIE: { libelle: 'Publié', classe: 'badge-success' },
}

const STATUT_GROUPE = {
  GENERATION_OK: 'Planifié',
  GENERATION_PARTIELLE: 'Partiel',
  GENERATION_IMPOSSIBLE: 'Impossible',
  NON_PLANIFIE: 'Non planifié',
  NON_PERSISTE: 'Non enregistré',
}

function Badge({ statut }) {
  const info = STATUTS[statut] || { libelle: statut || '—', classe: 'badge-neutral' }
  return <span className={`badge ${info.classe}`}>{info.libelle}</span>
}

function Compte({ libelle, valeur }) {
  return (
    <div className="getinjs-compte">
      <span className="getinjs-compte-valeur">{valeur ?? '—'}</span>
      <span className="getinjs-compte-libelle">{libelle}</span>
    </div>
  )
}

function dureeLisible(ms) {
  if (ms === null || ms === undefined) return '—'
  if (ms < 1000) return `${ms} ms`
  return `${(ms / 1000).toFixed(1)} s`
}

export default function CampagnesGeneration() {
  const { showToast } = useToast()
  const [annees, setAnnees] = useState([])
  const [anneeId, setAnneeId] = useState('')
  const [libelle, setLibelle] = useState('')
  const [semaines, setSemaines] = useState('1')
  const [persister, setPersister] = useState(true)
  const [campagnes, setCampagnes] = useState([])
  const [selection, setSelection] = useState(null)
  const [resultat, setResultat] = useState(null)
  const [chargement, setChargement] = useState(true)
  const [action, setAction] = useState('')
  const [erreur, setErreur] = useState('')
  const minuteur = useRef(null)

  const chargerCampagnes = useCallback(async (annee) => {
    try {
      const { data } = await api.get('/edts/campagnes/', {
        params: annee ? { annee } : {},
      })
      setCampagnes(data?.results || [])
    } catch (err) {
      setErreur(formatApiErrors(err?.response?.data, {
        fallback: 'Impossible de charger les campagnes.',
      }))
    }
  }, [])

  useEffect(() => {
    let annule = false
    api.get('/scolarite/ref/annees/')
      .then(({ data }) => {
        if (annule) return
        const liste = Array.isArray(data) ? data : (data?.results || [])
        setAnnees(liste)
        const courante = liste.find((a) => a.courante) || liste[0]
        if (courante) setAnneeId(String(courante.id))
      })
      .catch(() => { if (!annule) setAnnees([]) })
    return () => { annule = true }
  }, [])

  useEffect(() => {
    setChargement(true)
    chargerCampagnes(anneeId).finally(() => setChargement(false))
  }, [anneeId, chargerCampagnes])

  // Interrogation périodique tant qu'une campagne est en cours. Aucun
  // « pourcentage » n'est fabriqué : on affiche l'état réel et la durée.
  useEffect(() => {
    const enCours = campagnes.some((c) => c.statut === 'EN_COURS')
    if (!enCours) return undefined
    minuteur.current = setInterval(async () => {
      await chargerCampagnes(anneeId)
      if (selection) await ouvrirResultat(selection.id, { silencieux: true })
    }, 3000)
    return () => clearInterval(minuteur.current)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [campagnes, anneeId, chargerCampagnes, selection])

  const ouvrirResultat = async (id, { silencieux = false } = {}) => {
    try {
      const { data } = await api.get(`/edts/campagnes/${id}/resultat/`)
      setResultat(data)
      setSelection(data.campagne)
    } catch (err) {
      if (!silencieux) {
        setErreur(formatApiErrors(err?.response?.data, {
          fallback: 'Résultat indisponible.',
        }))
      }
    }
  }

  const creer = async (evenement) => {
    evenement.preventDefault()
    setErreur('')
    if (!anneeId || !libelle.trim()) {
      setErreur('Choisissez une année académique et saisissez un libellé.')
      return
    }
    setAction('creation')
    try {
      const { data } = await api.post('/edts/campagnes/', {
        annee_academique_id: Number(anneeId),
        libelle: libelle.trim(),
        semaines: semaines.split(',').map((s) => parseInt(s.trim(), 10)).filter(Boolean),
        parametres: { persister, remplacer: true, inclure_maquette: true },
      })
      setLibelle('')
      await chargerCampagnes(anneeId)
      showToast(`Campagne « ${data.libelle} » créée.`, 'success')
    } catch (err) {
      setErreur(formatApiErrors(err?.response?.data, {
        fallback: 'Création impossible.',
      }))
    } finally {
      setAction('')
    }
  }

  const agir = async (campagne, chemin, corps, message) => {
    setAction(`${campagne.id}:${chemin}`)
    setErreur('')
    try {
      const { data } = await api.post(`/edts/campagnes/${campagne.id}/${chemin}/`, corps || {})
      await chargerCampagnes(anneeId)
      await ouvrirResultat(campagne.id, { silencieux: true })
      if (message) showToast(message, 'success')
      return data
    } catch (err) {
      // Les refus métier (409) portent une explication : on l'affiche telle quelle.
      const motif = err?.response?.data?.detail?.explication
      setErreur(motif || formatApiErrors(err?.response?.data, {
        fallback: 'Opération refusée.',
      }))
      await chargerCampagnes(anneeId)
      return null
    } finally {
      setAction('')
    }
  }

  const groupes = useMemo(() => resultat?.groupes || [], [resultat])
  const anomalies = useMemo(() => resultat?.anomalies || [], [resultat])
  const totaux = useMemo(() => resultat?.totaux || {}, [resultat])

  const actionsPossibles = (campagne) => ({
    demarrer: ['PRET', 'TERMINE', 'TERMINE_AVEC_ANOMALIES', 'ECHEC'].includes(campagne.statut),
    valider: ['TERMINE', 'TERMINE_AVEC_ANOMALIES'].includes(campagne.statut),
    publier: campagne.statut === 'VALIDE',
  })

  return (
    <div className="getinjs">
      <div className="d-flex flex-wrap align-items-center gap-2 mb-3">
        <h4 className="mb-0">
          <i className="bi bi-collection-play me-2 text-primary" aria-hidden="true"></i>
          GET-INJS — Campagnes de génération
        </h4>
        <Link to="/edt/generation-annuelle" className="btn btn-outline-secondary btn-sm ms-auto">
          <i className="bi bi-upload me-1" aria-hidden="true"></i>
          Import des inscrits &amp; génération directe
        </Link>
      </div>

      {erreur && (
        <div className="alert alert-danger" role="alert">
          <i className="bi bi-exclamation-triangle me-1" aria-hidden="true"></i>
          {erreur}
        </div>
      )}

      <form className="card mb-3" onSubmit={creer}>
        <div className="card-header"><strong>1. Nouvelle campagne</strong></div>
        <div className="card-body">
          <div className="row g-3 align-items-end">
            <div className="col-md-3">
              <label className="form-label" htmlFor="campagne-annee">Année académique</label>
              <select
                id="campagne-annee"
                className="form-select"
                value={anneeId}
                onChange={(e) => setAnneeId(e.target.value)}
              >
                <option value="">— choisir —</option>
                {annees.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.libelle}{a.courante ? ' (courante)' : ''}
                  </option>
                ))}
              </select>
            </div>
            <div className="col-md-4">
              <label className="form-label" htmlFor="campagne-libelle">Libellé</label>
              <input
                id="campagne-libelle"
                className="form-control"
                value={libelle}
                maxLength={255}
                placeholder="Ex. Génération annuelle — session 1"
                onChange={(e) => setLibelle(e.target.value)}
              />
            </div>
            <div className="col-md-2">
              <label className="form-label" htmlFor="campagne-semaines">Semaines</label>
              <input
                id="campagne-semaines"
                className="form-control"
                value={semaines}
                placeholder="1, 2, 3"
                onChange={(e) => setSemaines(e.target.value)}
              />
            </div>
            <div className="col-md-2">
              <div className="form-check">
                <input
                  id="campagne-persister"
                  className="form-check-input"
                  type="checkbox"
                  checked={persister}
                  onChange={(e) => setPersister(e.target.checked)}
                />
                <label className="form-check-label" htmlFor="campagne-persister">
                  Enregistrer les EDT
                </label>
              </div>
            </div>
            <div className="col-md-1 text-end">
              <button className="btn btn-primary" type="submit" disabled={action === 'creation'}>
                {action === 'creation' ? 'Création…' : 'Créer'}
              </button>
            </div>
          </div>
          <p className="text-muted small mb-0 mt-2">
            Créer une campagne n’écrit aucun emploi du temps : la génération est un
            second geste, et la publication un troisième.
          </p>
        </div>
      </form>

      <div className="card mb-3">
        <div className="card-header d-flex justify-content-between align-items-center">
          <strong>2. Campagnes de l’année</strong>
          <button
            type="button"
            className="btn btn-outline-secondary btn-sm"
            onClick={() => chargerCampagnes(anneeId)}
          >
            <i className="bi bi-arrow-clockwise me-1" aria-hidden="true"></i>Actualiser
          </button>
        </div>
        <div className="card-body p-0">
          {chargement ? (
            <p className="p-3 mb-0 text-muted">Chargement…</p>
          ) : campagnes.length === 0 ? (
            <p className="p-3 mb-0 text-muted">Aucune campagne pour cette année académique.</p>
          ) : (
            <div className="table-responsive">
              <table className="table table-sm align-middle mb-0">
                <thead>
                  <tr>
                    <th>Libellé</th>
                    <th>Statut</th>
                    <th>Créée le</th>
                    <th>Durée</th>
                    <th className="text-end">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {campagnes.map((campagne) => {
                    const possibles = actionsPossibles(campagne)
                    return (
                      <tr key={campagne.id}>
                        <td>
                          <button
                            type="button"
                            className="btn btn-link p-0"
                            onClick={() => ouvrirResultat(campagne.id)}
                          >
                            {campagne.libelle}
                          </button>
                        </td>
                        <td><Badge statut={campagne.statut} /></td>
                        <td>{campagne.created_at
                          ? new Date(campagne.created_at).toLocaleDateString('fr-FR')
                          : '—'}</td>
                        <td>{dureeLisible(campagne.statistiques?.duree_ms)}</td>
                        <td className="text-end">
                          <div className="btn-group btn-group-sm">
                            <button
                              type="button"
                              className="btn btn-outline-primary"
                              disabled={!possibles.demarrer || Boolean(action)}
                              onClick={() => agir(campagne, 'demarrer', { asynchrone: true }, 'Génération lancée.')}
                            >
                              Générer
                            </button>
                            <button
                              type="button"
                              className="btn btn-outline-success"
                              disabled={!possibles.valider || Boolean(action)}
                              onClick={() => agir(campagne, 'valider', {}, 'Campagne validée.')}
                            >
                              Valider
                            </button>
                            <button
                              type="button"
                              className="btn btn-outline-dark"
                              disabled={!possibles.publier || Boolean(action)}
                              onClick={() => agir(campagne, 'publier', {}, 'Campagne publiée.')}
                            >
                              Publier
                            </button>
                          </div>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {resultat && (
        <div className="card mb-3">
          <div className="card-header d-flex justify-content-between align-items-center">
            <strong>3. Résultat — {resultat.campagne.libelle}</strong>
            <Badge statut={resultat.campagne.statut} />
          </div>
          <div className="card-body">
            <div className="getinjs-comptes mb-3">
              <Compte libelle="groupes" valeur={totaux.nb_groupes} />
              <Compte libelle="planifiés" valeur={totaux.nb_groupes_planifies} />
              <Compte libelle="complets" valeur={totaux.nb_groupes_complets} />
              <Compte libelle="séances placées" valeur={totaux.seances_placees} />
              <Compte libelle="séances non placées" valeur={totaux.seances_non_placees} />
              <Compte libelle="étudiants couverts" valeur={totaux.etudiants_couverts} />
              <Compte libelle="durée" valeur={dureeLisible(resultat.campagne.statistiques?.duree_ms)} />
              <Compte libelle="requêtes SQL" valeur={resultat.campagne.statistiques?.requetes_sql} />
            </div>

            {anomalies.length > 0 ? (
              <div className="alert alert-warning" role="status">
                <strong>{anomalies.length} anomalie(s) détectée(s).</strong>
                <ul className="mb-0 mt-2 small">
                  {anomalies.map((a, i) => (
                    <li key={`${a.nature}-${a.groupe_id ?? i}`}>
                      <span className="badge badge-neutral me-1">{a.niveau}</span>
                      {a.nature === 'GROUPE_NON_PLANIFIE'
                        ? `Groupe ${a.groupe || a.groupe_id} — ${a.motif} : ${a.explication}`
                        : a.explication}
                    </li>
                  ))}
                </ul>
              </div>
            ) : (
              <p className="text-muted small">Aucune anomalie enregistrée pour cette campagne.</p>
            )}

            {resultat.campagne.execution_courante?.erreur && (
              <div className="alert alert-danger" role="alert">
                <strong>Dernière exécution en échec :</strong>
                <pre className="mb-0 small">{resultat.campagne.execution_courante.erreur}</pre>
              </div>
            )}

            {groupes.length > 0 && (
              <div className="table-responsive">
                <table className="table table-sm">
                  <thead>
                    <tr>
                      <th>Groupe</th>
                      <th>Formation</th>
                      <th>Niveau</th>
                      <th>Effectif</th>
                      <th>Statut</th>
                      <th>Séances</th>
                      <th>Motif</th>
                    </tr>
                  </thead>
                  <tbody>
                    {groupes.map((g) => (
                      <tr key={g.groupe_id}>
                        <td>{g.groupe}</td>
                        <td>{g.formation}</td>
                        <td>{g.niveau}</td>
                        <td>{g.effectif ?? '—'}</td>
                        <td>{STATUT_GROUPE[g.statut] || g.statut}</td>
                        <td>{g.seances_placees}/{g.seances_attendues}</td>
                        <td>{g.motif_echec || '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            <h6 className="mt-3">Historique des exécutions</h6>
            {resultat.executions?.length ? (
              <ul className="small mb-0">
                {resultat.executions.map((e) => (
                  <li key={e.id}>
                    Exécution {e.numero} — {e.statut}
                    {e.duree_ms != null && ` · ${dureeLisible(e.duree_ms)}`}
                    {e.erreur && ` · ${e.erreur}`}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-muted small mb-0">Aucune exécution pour l’instant.</p>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
