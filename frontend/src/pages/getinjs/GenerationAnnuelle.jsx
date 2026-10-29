import { useEffect, useMemo, useRef, useState } from 'react'
import api from '../../services/api'
import { useToast } from '../../context/ToastContext'
import { formatApiErrors } from '../../utils/apiErrors'

/**
 * GET-INJS — écran unique « Import des inscrits » + « Génération annuelle ».
 *
 * Deux situations du commanditaire :
 *
 * 1. générer les emplois du temps d'une année académique pour toutes les
 *    cohortes (filière, formation, groupe, vague, semestre) ;
 * 2. importer un fichier externe d'inscrits — y compris lorsque l'inscription
 *    n'est pas passée par la chaîne de parcours — puis générer les EDT.
 *
 * L'écran ne calcule rien : il expose ce que le backend décide et affiche
 * **tous** les comptes rendus réels (lignes rejetées avec motif, groupes non
 * planifiés, séances non placées). Aucune donnée n'est inventée côté interface.
 */

const STATUTS_LISIBLES = {
  GENERATION_OK: { libelle: 'Planifié', classe: 'badge-success' },
  GENERATION_PARTIELLE: { libelle: 'Partiel', classe: 'badge-warning' },
  GENERATION_IMPOSSIBLE: { libelle: 'Impossible', classe: 'badge-danger' },
  NON_PLANIFIE: { libelle: 'Non planifié', classe: 'badge-neutral' },
  NON_PERSISTE: { libelle: 'Non enregistré', classe: 'badge-danger' },
}

const STATUT_GLOBAL = {
  COMPLETE: { libelle: 'Complet', classe: 'badge-success' },
  PARTIELLE: { libelle: 'Partiel', classe: 'badge-warning' },
  IMPOSSIBLE: { libelle: 'Impossible', classe: 'badge-danger' },
}

function Statut({ statut }) {
  const info = STATUTS_LISIBLES[statut] || { libelle: statut || '—', classe: 'badge-neutral' }
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

export default function GenerationAnnuelle() {
  const { showToast } = useToast()
  const [annees, setAnnees] = useState([])
  const [anneeId, setAnneeId] = useState('')
  const [fichier, setFichier] = useState(null)
  const [rapport, setRapport] = useState(null)
  const [synthese, setSynthese] = useState(null)
  const [bilan, setBilan] = useState(null)
  const [enCours, setEnCours] = useState('')
  const [semaines, setSemaines] = useState('1')
  const [persister, setPersister] = useState(false)
  const [telechargement, setTelechargement] = useState(false)
  const inputFichier = useRef(null)

  useEffect(() => {
    let actif = true
    api.get('/scolarite/ref/annees/')
      .then(({ data }) => {
        if (!actif) return
        const liste = Array.isArray(data) ? data : (data?.results || [])
        setAnnees(liste)
        const courante = liste.find((a) => a.courante) || liste[0]
        if (courante) setAnneeId(String(courante.id))
      })
      .catch(() => showToast('Impossible de charger les années académiques.', 'error'))
    return () => { actif = false }
  }, [showToast])

  const chargerSynthese = async (id) => {
    if (!id) return
    try {
      const { data } = await api.get('/edts/lmd/import/inscrits/synthese/', { params: { annee: id } })
      // Seule une vraie synthèse porte la liste des cohortes : une réponse
      // d'erreur (404 motivé, objet vide) ne doit jamais devenir un compteur.
      setSynthese(data && Array.isArray(data.cohortes) ? data : null)
    } catch (err) {
      // Un effectif absent n'est pas une erreur bloquante : on le signale.
      setSynthese(null)
      if (err?.response?.status !== 404) {
        showToast(formatApiErrors(err) || 'Synthèse indisponible.', 'error')
      }
    }
  }

  useEffect(() => { chargerSynthese(anneeId) }, [anneeId]) // eslint-disable-line react-hooks/exhaustive-deps

  const envoyerFichier = async (mode) => {
    if (!anneeId) return showToast('Choisissez une année académique.', 'error')
    if (!fichier) return showToast('Choisissez un fichier (.csv ou .xlsx).', 'error')

    setEnCours(mode)
    setRapport(null)
    const donnees = new FormData()
    donnees.append('annee_academique_id', anneeId)
    donnees.append('fichier', fichier)

    const chemin = mode === 'analyse'
      ? '/edts/lmd/import/inscrits/analyser/'
      : '/edts/lmd/import/inscrits/'

    try {
      const { data } = await api.post(chemin, donnees, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      setRapport(data)
      if (mode === 'import') {
        showToast(`${data.creees || 0} inscription(s) créée(s), ${data.mises_a_jour || 0} mise(s) à jour.`, 'success')
        chargerSynthese(anneeId)
      } else {
        showToast(`Analyse terminée : ${data.lignes_valides} ligne(s) exploitable(s).`, 'info')
      }
    } catch (err) {
      const corps = err?.response?.data
      if (corps && typeof corps === 'object') setRapport(corps)
      showToast(corps?.motif_echec || formatApiErrors(err) || 'Import refusé.', 'error')
    } finally {
      setEnCours('')
    }
  }

  const generer = async () => {
    if (!anneeId) return showToast('Choisissez une année académique.', 'error')
    setEnCours('generation')
    setBilan(null)
    try {
      const listeSemaines = semaines
        .split(',')
        .map((s) => s.trim())
        .filter((s) => /^\d+$/.test(s))
        .map(Number)
      const { data } = await api.post('/edts/lmd/generate-annee/', {
        annee_academique_id: Number(anneeId),
        semaines: listeSemaines.length ? listeSemaines : [1],
        persister,
        remplacer: true,
        inclure_maquette: true,
      })
      setBilan(data && Array.isArray(data.groupes) ? data : null)
      showToast(
        `Génération ${STATUT_GLOBAL[data.status_global]?.libelle || data.status_global} : `
        + `${data.totaux?.seances_placees ?? 0} séance(s) placée(s).`,
        data.status_global === 'COMPLETE' ? 'success' : 'warning',
      )
    } catch (err) {
      const corps = err?.response?.data
      if (corps && typeof corps === 'object') setBilan(corps)
      showToast(corps?.motif_echec || formatApiErrors(err) || 'Génération impossible.', 'error')
    } finally {
      setEnCours('')
    }
  }

  const telechargerConception = async () => {
    setTelechargement(true)
    try {
      const { blob, fileName } = await api.getBlob('/edts/lmd/conception/')
      const url = URL.createObjectURL(blob)
      const lien = document.createElement('a')
      lien.href = url
      lien.download = fileName || 'Conception-GET-INJS.txt'
      document.body.appendChild(lien)
      lien.click()
      lien.remove()
      URL.revokeObjectURL(url)
    } catch {
      showToast('Document de conception indisponible.', 'error')
    } finally {
      setTelechargement(false)
    }
  }

  const cohortes = useMemo(() => synthese?.cohortes || [], [synthese])
  const groupes = useMemo(() => bilan?.groupes || [], [bilan])

  return (
    <div className="getinjs">
      <div className="d-flex flex-wrap align-items-center gap-2 mb-3">
        <h4 className="mb-0">
          <i className="bi bi-calendar2-range me-2 text-primary" aria-hidden="true"></i>
          GET-INJS — Génération annuelle
        </h4>
        <button
          type="button"
          className="btn btn-outline-secondary btn-sm ms-auto"
          onClick={telechargerConception}
          disabled={telechargement}
        >
          <i className="bi bi-download me-1" aria-hidden="true"></i>
          {telechargement ? 'Téléchargement…' : 'Conception GET-INJS'}
        </button>
      </div>

      <div className="card mb-3">
        <div className="card-header"><strong>1. Année académique</strong></div>
        <div className="card-body">
          <div className="row g-3 align-items-end">
            <div className="col-md-4">
              <label className="form-label" htmlFor="getinjs-annee">Année académique</label>
              <select
                id="getinjs-annee"
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
            <div className="col-md-8">
              {synthese && (
                <div className="getinjs-comptes">
                  <Compte libelle="étudiants importés" valeur={synthese.effectif_total} />
                  <Compte libelle="cohortes" valeur={synthese.nb_cohortes} />
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      <div className="card mb-3">
        <div className="card-header"><strong>2. Import du fichier des inscrits</strong></div>
        <div className="card-body">
          <p className="text-muted small">
            Formats acceptés : CSV (séparateur « ; » ou « , ») et Excel (.xlsx).
            Colonnes attendues : matricule, nom, formation, niveau — les autres
            (prénoms, sexe, date de naissance, parcours, semestre, groupe, vague)
            sont reconnues par synonymes. L’analyse n’écrit <strong>rien</strong>.
          </p>
          <div className="row g-2 align-items-end">
            <div className="col-md-5">
              <label className="form-label" htmlFor="getinjs-fichier">Fichier des inscrits</label>
              <input
                id="getinjs-fichier"
                ref={inputFichier}
                type="file"
                className="form-control"
                accept=".csv,.txt,.xlsx,.xlsm"
                onChange={(e) => setFichier(e.target.files?.[0] || null)}
              />
            </div>
            <div className="col-md-7 d-flex flex-wrap gap-2">
              <button
                type="button"
                className="btn btn-outline-primary"
                onClick={() => envoyerFichier('analyse')}
                disabled={enCours !== ''}
              >
                <i className="bi bi-search me-1" aria-hidden="true"></i>
                {enCours === 'analyse' ? 'Analyse…' : 'Analyser sans importer'}
              </button>
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => envoyerFichier('import')}
                disabled={enCours !== ''}
              >
                <i className="bi bi-upload me-1" aria-hidden="true"></i>
                {enCours === 'import' ? 'Import…' : 'Importer'}
              </button>
            </div>
          </div>

          {rapport && (
            <div className="mt-3">
              <div className="getinjs-comptes">
                <Compte libelle="lignes lues" valeur={rapport.lignes_lues} />
                <Compte libelle="valides" valeur={rapport.lignes_valides} />
                <Compte libelle="rejetées" valeur={rapport.lignes_rejetees} />
                <Compte libelle="créées" valeur={rapport.creees} />
                <Compte libelle="mises à jour" valeur={rapport.mises_a_jour} />
                <Compte libelle="effectif" valeur={rapport.effectif_total} />
              </div>

              {rapport.motif_echec && (
                <div className="alert alert-danger mt-3" role="alert">
                  <strong>Import refusé — {rapport.motif_echec}</strong>
                  {rapport.detail?.explication && <div>{rapport.detail.explication}</div>}
                  {rapport.detail?.colonnes_manquantes && (
                    <div>Colonnes manquantes : {rapport.detail.colonnes_manquantes.join(', ')}</div>
                  )}
                </div>
              )}

              {rapport.erreurs?.length > 0 && (
                <div className="table-responsive mt-3">
                  <table className="table table-sm">
                    <caption className="text-muted small">
                      Lignes rejetées — chaque rejet est motivé
                      {rapport.erreurs_tronquees > 0 && ` (${rapport.erreurs_tronquees} de plus non affichées)`}
                    </caption>
                    <thead>
                      <tr>
                        <th scope="col">Ligne</th>
                        <th scope="col">Motif</th>
                        <th scope="col">Détail</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rapport.erreurs.map((erreur) => (
                        <tr key={`${erreur.ligne}-${erreur.motif}`}>
                          <td>{erreur.ligne}</td>
                          <td><span className="badge badge-danger">{erreur.motif}</span></td>
                          <td>{erreur.detail}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {rapport.cohortes?.length > 0 && (
                <div className="table-responsive mt-3">
                  <table className="table table-sm">
                    <caption className="text-muted small">Cohortes reconnues</caption>
                    <thead>
                      <tr>
                        <th scope="col">Formation</th>
                        <th scope="col">Niveau</th>
                        <th scope="col">Groupe</th>
                        <th scope="col">Vague</th>
                        <th scope="col" className="text-end">Effectif</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rapport.cohortes.map((c, index) => (
                        <tr key={`${c.formation}-${c.groupe}-${c.vague}-${index}`}>
                          <td>{c.formation}</td>
                          <td>{c.niveau}</td>
                          <td>{c.groupe || '—'}</td>
                          <td>{c.vague || '—'}</td>
                          <td className="text-end">{c.effectif}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      <div className="card mb-3">
        <div className="card-header"><strong>3. Génération des emplois du temps</strong></div>
        <div className="card-body">
          <div className="row g-2 align-items-end">
            <div className="col-md-4">
              <label className="form-label" htmlFor="getinjs-semaines">Semaines planifiées</label>
              <input
                id="getinjs-semaines"
                className="form-control"
                value={semaines}
                onChange={(e) => setSemaines(e.target.value)}
                placeholder="ex. 1,2,3"
              />
            </div>
            <div className="col-md-4">
              <div className="form-check">
                <input
                  className="form-check-input"
                  type="checkbox"
                  id="getinjs-persister"
                  checked={persister}
                  onChange={(e) => setPersister(e.target.checked)}
                />
                <label className="form-check-label" htmlFor="getinjs-persister">
                  Enregistrer les brouillons (aucune publication)
                </label>
              </div>
            </div>
            <div className="col-md-4">
              <button
                type="button"
                className="btn btn-primary w-100"
                onClick={generer}
                disabled={enCours !== ''}
              >
                <i className="bi bi-magic me-1" aria-hidden="true"></i>
                {enCours === 'generation' ? 'Génération…' : 'Générer l’année'}
              </button>
            </div>
          </div>

          {bilan && (
            <div className="mt-3">
              <p className="mb-2">
                Statut global :{' '}
                <span className={`badge ${STATUT_GLOBAL[bilan.status_global]?.classe || 'badge-neutral'}`}>
                  {STATUT_GLOBAL[bilan.status_global]?.libelle || bilan.status_global}
                </span>
                {bilan.motif_echec && <span className="ms-2 text-danger">{bilan.motif_echec}</span>}
              </p>

              {bilan.detail?.explication && (
                <div className="alert alert-warning" role="alert">
                  {bilan.detail.explication}
                  {bilan.detail.action_recommandee && <div>{bilan.detail.action_recommandee}</div>}
                </div>
              )}

              {bilan.totaux && (
                <div className="getinjs-comptes">
                  <Compte libelle="groupes" valeur={bilan.totaux.nb_groupes} />
                  <Compte libelle="planifiés" valeur={bilan.totaux.nb_groupes_planifies} />
                  <Compte libelle="complets" valeur={bilan.totaux.nb_groupes_complets} />
                  <Compte libelle="étudiants couverts" valeur={bilan.totaux.etudiants_couverts} />
                  <Compte libelle="séances placées" valeur={bilan.totaux.seances_placees} />
                  <Compte libelle="séances non placées" valeur={bilan.totaux.seances_non_placees} />
                  {bilan.persistence_demandee && (
                    <Compte libelle="EDT enregistrés" valeur={bilan.totaux.edts_persistes} />
                  )}
                </div>
              )}

              {groupes.length > 0 && (
                <div className="table-responsive mt-3">
                  <table className="table table-sm">
                    <caption className="text-muted small">
                      Bilan par groupe — aucune ligne n’est masquée
                    </caption>
                    <thead>
                      <tr>
                        <th scope="col">Formation</th>
                        <th scope="col">Niveau</th>
                        <th scope="col">Groupe</th>
                        <th scope="col">Vague</th>
                        <th scope="col" className="text-end">Effectif</th>
                        <th scope="col" className="text-end">Placées</th>
                        <th scope="col" className="text-end">Non placées</th>
                        <th scope="col">Statut</th>
                      </tr>
                    </thead>
                    <tbody>
                      {groupes.map((g) => (
                        <tr key={g.groupe_id}>
                          <td>{g.formation}</td>
                          <td>{g.niveau}</td>
                          <td>{g.groupe}</td>
                          <td>{g.vague || '—'}</td>
                          <td className="text-end">{g.effectif ?? '—'}</td>
                          <td className="text-end">{g.seances_placees}</td>
                          <td className="text-end">{g.seances_non_placees}</td>
                          <td>
                            <Statut statut={g.statut} />
                            {g.motif_echec && (
                              <div className="small text-muted">{g.motif_echec}</div>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {cohortes.length > 0 && (
        <div className="card">
          <div className="card-header"><strong>Cohortes importées pour cette année</strong></div>
          <div className="card-body">
            <div className="table-responsive">
              <table className="table table-sm">
                <caption className="text-muted small">
                  Cohortes importées — effectif dénombré, jamais déclaré
                </caption>
                <thead>
                  <tr>
                    <th scope="col">Formation</th>
                    <th scope="col">Parcours</th>
                    <th scope="col">Niveau</th>
                    <th scope="col">Groupe</th>
                    <th scope="col">Vague</th>
                    <th scope="col" className="text-end">Effectif</th>
                  </tr>
                </thead>
                <tbody>
                  {cohortes.map((c, index) => (
                    <tr key={`${c.formation}-${c.groupe}-${index}`}>
                      <td>{c.formation}</td>
                      <td>{c.parcours || '—'}</td>
                      <td>{c.niveau || '—'}</td>
                      <td>{c.groupe || '—'}</td>
                      <td>{c.vague || '—'}</td>
                      <td className="text-end">{c.effectif}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
