import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import api from '../../services/api'
import { useToast } from '../../context/ToastContext'
import { formatApiErrors } from '../../utils/apiErrors'

/**
 * GET-INJS — « Générer les emplois du temps » (moteur LMD) + import des
 * inscrits (le menu « Import étudiants » mène au même écran, zone d'import).
 *
 * L'écran ne calcule rien : il expose ce que le backend décide et affiche
 * **tous** les comptes rendus réels (lignes rejetées avec motif, groupes non
 * planifiés, séances non placées). Le lancement persiste une génération
 * traçable (campagne + exécution horodatée) ; la prévisualisation, elle,
 * n'écrit rien. Aucune donnée n'est inventée côté interface.
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

const STATUTS_EXECUTION = {
  TERMINE: { libelle: 'terminée', classe: 'badge-success' },
  TERMINE_AVEC_ANOMALIES: { libelle: 'terminée avec anomalies', classe: 'badge-warning' },
  ECHEC: { libelle: 'échec', classe: 'badge-danger' },
  EN_COURS: { libelle: 'en cours', classe: 'badge-primary' },
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

function formatDateHeure(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  const jour = d.toLocaleDateString('fr-FR', { day: '2-digit', month: '2-digit' })
  const heure = d.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })
  return `${jour} ${heure}`
}

function formatDuree(ms) {
  if (ms == null) return '—'
  if (ms < 100) return `${ms} ms`
  return `${(ms / 1000).toFixed(1)} s`
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
  const [telechargement, setTelechargement] = useState(false)
  const inputFichier = useRef(null)

  // Paramètres de génération (maquette) et référentiels de périmètre.
  const [formationsRef, setFormationsRef] = useState([])
  const [niveauxRef, setNiveauxRef] = useState([])
  const [groupesRef, setGroupesRef] = useState([])
  const [filiereCode, setFiliereCode] = useState('')
  const [formationId, setFormationId] = useState('')
  const [niveauId, setNiveauId] = useState('')
  const [groupeId, setGroupeId] = useState('')
  const [semestreSel, setSemestreSel] = useState('')
  const [inclureSamedi, setInclureSamedi] = useState(true)
  const [eviterPause, setEviterPause] = useState(true)
  const [publierDirect, setPublierDirect] = useState(false)
  const [maxSeances, setMaxSeances] = useState('30')

  // Historique des générations et emplois du temps versionnés (réels).
  const [historique, setHistorique] = useState([])
  const [versions, setVersions] = useState([])

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

  useEffect(() => {
    let actif = true
    Promise.all([
      api.get('/formations/ref/formations/').catch(() => null),
      api.get('/scolarite/ref/niveaux/').catch(() => null),
    ]).then(([formationsRes, niveauxRes]) => {
      if (!actif) return
      if (formationsRes) {
        setFormationsRef(Array.isArray(formationsRes.data)
          ? formationsRes.data : (formationsRes.data?.results ?? []))
      }
      if (niveauxRes) {
        setNiveauxRef(Array.isArray(niveauxRes.data)
          ? niveauxRes.data : (niveauxRes.data?.results ?? []))
      }
    })
    return () => { actif = false }
  }, [])

  useEffect(() => {
    if (!anneeId) { setGroupesRef([]); return }
    let actif = true
    api.get('/scolarite/ref/groupes/', { params: { annee_academique_id: anneeId } })
      .then(({ data }) => {
        if (!actif) return
        setGroupesRef(Array.isArray(data) ? data : (data?.results ?? []))
      })
      .catch(() => { if (actif) setGroupesRef([]) })
    return () => { actif = false }
  }, [anneeId])

  const chargerHistorique = useCallback(async () => {
    try {
      const { data } = await api.get('/edts/campagnes/historique/')
      setHistorique(Array.isArray(data?.executions) ? data.executions : [])
    } catch { setHistorique([]) }
  }, [])

  const chargerVersions = useCallback(async () => {
    try {
      const { data } = await api.get('/edts/lmd/versions/')
      setVersions(Array.isArray(data?.versions) ? data.versions : [])
    } catch { setVersions([]) }
  }, [])

  useEffect(() => { chargerHistorique(); chargerVersions() }, [chargerHistorique, chargerVersions])

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
        showToast(formatApiErrors(err?.response?.data) || 'Synthèse indisponible.', 'error')
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
      showToast(corps?.motif_echec || formatApiErrors(err?.response?.data) || 'Import refusé.', 'error')
    } finally {
      setEnCours('')
    }
  }

  const semainesListe = () => semaines
    .split(',').map((s) => s.trim()).filter((s) => /^\d+$/.test(s)).map(Number)

  const construirePerimetre = () => {
    const formations = formationId
      ? [Number(formationId)]
      : (filiereCode
        ? formationsRef.filter((f) => f.filiere_code === filiereCode).map((f) => f.id)
        : [])
    return {
      formations,
      niveaux: niveauId ? [Number(niveauId)] : [],
      groupes: groupeId ? [Number(groupeId)] : [],
      semestres: semestreSel ? [Number(semestreSel)] : [],
    }
  }

  const lancerGeneration = async () => {
    if (!anneeId) return showToast('Choisissez une année académique.', 'error')
    setEnCours('generation')
    setBilan(null)
    try {
      const annee = annees.find((a) => String(a.id) === String(anneeId))
      const horodatage = new Date().toLocaleString('fr-FR')
      const { data: campagne } = await api.post('/edts/campagnes/', {
        annee_academique_id: Number(anneeId),
        libelle: `Génération ${annee?.libelle || anneeId} — ${horodatage}`,
        semaines: semainesListe(),
        perimetre: construirePerimetre(),
        parametres: {
          persister: true,
          remplacer: true,
          inclure_maquette: true,
          inclure_samedi: inclureSamedi,
          eviter_pause_meridienne: eviterPause,
          max_seances_par_groupe_semaine: maxSeances ? Number(maxSeances) : null,
          publier_direct: publierDirect,
        },
      })
      await api.post(`/edts/campagnes/${campagne.id}/donnees-pretes/`, {})
      await api.post(`/edts/campagnes/${campagne.id}/demarrer/`, { asynchrone: false })
      const { data: resultat } = await api.get(`/edts/campagnes/${campagne.id}/resultat/`)
      const bilanCampagne = {
        status_global: resultat.campagne?.status_global,
        motif_echec: null,
        totaux: resultat.totaux,
        groupes: resultat.groupes,
        persistence_demandee: true,
      }
      setBilan(bilanCampagne)
      showToast(
        `Génération ${STATUT_GLOBAL[bilanCampagne.status_global]?.libelle || bilanCampagne.status_global || 'terminée'} : `
        + `${resultat.totaux?.seances_placees ?? 0} séance(s) placée(s).`,
        bilanCampagne.status_global === 'COMPLETE' ? 'success' : 'warning',
      )
      if (publierDirect) {
        await api.post(`/edts/campagnes/${campagne.id}/valider/`, {})
        await api.post(`/edts/campagnes/${campagne.id}/publier/`, {})
        showToast('Emplois du temps validés puis publiés.', 'success')
      }
      chargerHistorique()
      chargerVersions()
    } catch (err) {
      const corps = err?.response?.data
      showToast(
        corps?.detail?.explication || corps?.motif_echec
        || formatApiErrors(corps) || 'Génération impossible.',
        'error',
      )
    } finally {
      setEnCours('')
    }
  }

  const previsualiser = async () => {
    if (!anneeId) return showToast('Choisissez une année académique.', 'error')
    setEnCours('previsualisation')
    setBilan(null)
    try {
      const perimetre = construirePerimetre()
      const { data } = await api.post('/edts/lmd/generate-annee/', {
        annee_academique_id: Number(anneeId),
        semaines: semainesListe().length ? semainesListe() : [1],
        persister: false,
        remplacer: true,
        inclure_maquette: true,
        formations: perimetre.formations,
        niveaux: perimetre.niveaux,
        groupes: perimetre.groupes,
        semestres: perimetre.semestres,
        inclure_samedi: inclureSamedi,
        eviter_pause_meridienne: eviterPause,
        max_seances_par_groupe_semaine: maxSeances ? Number(maxSeances) : null,
      })
      setBilan(data && Array.isArray(data.groupes) ? data : null)
      showToast(
        `Prévisualisation ${STATUT_GLOBAL[data.status_global]?.libelle || data.status_global} : `
        + `${data.totaux?.seances_placees ?? 0} séance(s) placée(s) (rien n'a été écrit).`,
        data.status_global === 'COMPLETE' ? 'success' : 'warning',
      )
    } catch (err) {
      const corps = err?.response?.data
      if (corps && typeof corps === 'object') setBilan(corps)
      showToast(corps?.motif_echec || formatApiErrors(err?.response?.data) || 'Génération impossible.', 'error')
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
  const filieresRef = useMemo(
    () => [...new Set(formationsRef.map((f) => f.filiere_code).filter(Boolean))].sort(),
    [formationsRef],
  )
  const formationsFiltrees = useMemo(
    () => (filiereCode
      ? formationsRef.filter((f) => f.filiere_code === filiereCode)
      : formationsRef),
    [formationsRef, filiereCode],
  )
  const groupesOptions = useMemo(
    () => groupesRef.filter((g) => (
      (!formationId || g.ref_formation_id === Number(formationId))
      && (!niveauId || g.niveau_id === Number(niveauId))
    )),
    [groupesRef, formationId, niveauId],
  )

  return (
    <div className="getinjs">
      <div className="gen-entete">
        <div>
          <span className="gen-sur">Moteur LMD</span>
          <h2 className="gen-titre">Générer les emplois du temps</h2>
          <p className="gen-sous">
            Un seul passage pour toute l'année académique ou pour un périmètre
            ciblé (filière, formation, niveau, groupe, semestre). Le moteur
            garantit l'absence de double réservation de salle, d'enseignant
            et de groupe.
          </p>
        </div>
        <div className="gen-actions">
          <Link to="/edt" className="btn btn-outline-primary btn-sm">
            <i className="bi bi-grid-3x3 me-1" aria-hidden="true"></i>
            Consulter les grilles
          </Link>
          <Link to="/edt/salles-espaces" className="btn btn-outline-secondary btn-sm">
            <i className="bi bi-collection me-1" aria-hidden="true"></i>
            Vérifier les référentiels
          </Link>
          <button
            type="button"
            className="btn btn-outline-secondary btn-sm"
            onClick={telechargerConception}
            disabled={telechargement}
          >
            <i className="bi bi-download me-1" aria-hidden="true"></i>
            {telechargement ? 'Téléchargement…' : 'Conception GET-INJS'}
          </button>
        </div>
      </div>

      <div className="row g-3 mb-3">
        <div className="col-xl-8">
          <div className="card h-100">
            <div className="card-header">
              <strong>Paramètres de génération</strong>
              <div className="text-muted small">
                Le moteur remplace les séances existantes du périmètre
                sélectionné puis persiste la nouvelle grille (versionnée,
                horodatée et traçable).
              </div>
            </div>
            <div className="card-body">
              <div className="row g-3">
                <div className="col-md-6">
                  <label className="form-label gen-label" htmlFor="gen-annee">Année académique *</label>
                  <select
                    id="gen-annee"
                    className="form-select"
                    value={anneeId}
                    onChange={(e) => setAnneeId(e.target.value)}
                  >
                    <option value="">— choisir —</option>
                    {annees.map((a) => (
                      <option key={a.id} value={a.id}>
                        {`Année académique ${a.libelle}`}{a.courante ? ' (courante)' : ''}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="col-md-6">
                  <label className="form-label gen-label" htmlFor="gen-filiere">Filière (mention)</label>
                  <select
                    id="gen-filiere"
                    className="form-select"
                    value={filiereCode}
                    onChange={(e) => { setFiliereCode(e.target.value); setFormationId('') }}
                  >
                    <option value="">Toutes les filières</option>
                    {filieresRef.map((code) => <option key={code} value={code}>{code}</option>)}
                  </select>
                </div>
                <div className="col-md-6">
                  <label className="form-label gen-label" htmlFor="gen-formation">Formation / parcours</label>
                  <select
                    id="gen-formation"
                    className="form-select"
                    value={formationId}
                    onChange={(e) => setFormationId(e.target.value)}
                  >
                    <option value="">Toutes les formations</option>
                    {formationsFiltrees.map((f) => (
                      <option key={f.id} value={f.id}>{f.intitule}</option>
                    ))}
                  </select>
                </div>
                <div className="col-md-6">
                  <label className="form-label gen-label" htmlFor="gen-niveau">Niveau</label>
                  <select
                    id="gen-niveau"
                    className="form-select"
                    value={niveauId}
                    onChange={(e) => setNiveauId(e.target.value)}
                  >
                    <option value="">Tous les niveaux</option>
                    {niveauxRef.map((n) => (
                      <option key={n.id} value={n.id}>{n.code} — {n.libelle}</option>
                    ))}
                  </select>
                </div>
                <div className="col-md-6">
                  <label className="form-label gen-label" htmlFor="gen-groupe">Groupe (optionnel)</label>
                  <select
                    id="gen-groupe"
                    className="form-select"
                    value={groupeId}
                    onChange={(e) => setGroupeId(e.target.value)}
                  >
                    <option value="">Tous les groupes du périmètre</option>
                    {groupesOptions.map((g) => (
                      <option key={g.id} value={g.id}>{g.nom}</option>
                    ))}
                  </select>
                </div>
                <div className="col-md-6">
                  <label className="form-label gen-label" htmlFor="gen-semestre">Semestre</label>
                  <select
                    id="gen-semestre"
                    className="form-select"
                    value={semestreSel}
                    onChange={(e) => setSemestreSel(e.target.value)}
                  >
                    <option value="">Toute l'année (2 semestres par niveau)</option>
                    {['1', '2', '3', '4', '5', '6', '7', '8', '9', '10'].map((n) => (
                      <option key={n} value={n}>{`Semestre ${n} (S${n})`}</option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="gen-contraintes">
                <span className="gen-label d-block mb-2">Contraintes et options</span>
                <div className="row g-2">
                  <div className="col-md-5">
                    <div className="form-check">
                      <input
                        className="form-check-input" type="checkbox" id="gen-samedi"
                        checked={inclureSamedi}
                        onChange={(e) => setInclureSamedi(e.target.checked)}
                      />
                      <label className="form-check-label" htmlFor="gen-samedi">
                        Inclure le samedi (créneaux du matin)
                      </label>
                    </div>
                    <div className="form-check">
                      <input
                        className="form-check-input" type="checkbox" id="gen-publier"
                        checked={publierDirect}
                        onChange={(e) => setPublierDirect(e.target.checked)}
                      />
                      <label className="form-check-label" htmlFor="gen-publier">
                        Publier directement l'emploi du temps
                      </label>
                    </div>
                  </div>
                  <div className="col-md-4">
                    <div className="form-check">
                      <input
                        className="form-check-input" type="checkbox" id="gen-pause"
                        checked={eviterPause}
                        onChange={(e) => setEviterPause(e.target.checked)}
                      />
                      <label className="form-check-label" htmlFor="gen-pause">
                        Éviter la pause méridienne (12h-14h)
                      </label>
                    </div>
                    <label className="form-label gen-label mt-2" htmlFor="getinjs-semaines">Semaines planifiées</label>
                    <input
                      id="getinjs-semaines"
                      className="form-control form-control-sm"
                      value={semaines}
                      onChange={(e) => setSemaines(e.target.value)}
                      placeholder="ex. 1,2,3"
                    />
                  </div>
                  <div className="col-md-3">
                    <label className="form-label gen-label" htmlFor="gen-max">Séances max / groupe / semaine</label>
                    <input
                      id="gen-max"
                      type="number" min="1" max="60"
                      className="form-control"
                      value={maxSeances}
                      onChange={(e) => setMaxSeances(e.target.value)}
                    />
                  </div>
                </div>
              </div>

              <div className="d-flex flex-wrap align-items-center gap-2 mt-3">
                <button
                  type="button"
                  className="btn btn-dark"
                  onClick={lancerGeneration}
                  disabled={enCours !== ''}
                >
                  <i className="bi bi-play-fill me-1" aria-hidden="true"></i>
                  {enCours === 'generation' ? 'Génération…' : 'Lancer la génération'}
                </button>
                <button
                  type="button"
                  className="btn btn-outline-primary"
                  onClick={previsualiser}
                  disabled={enCours !== ''}
                >
                  <i className="bi bi-eye me-1" aria-hidden="true"></i>
                  {enCours === 'previsualisation' ? 'Prévisualisation…' : 'Prévisualiser sans persister'}
                </button>
                <span className="text-muted small">
                  Déterministe · CM mutualisés · TD/TP par groupe · contrôle des conflits
                </span>
              </div>
            </div>
          </div>
        </div>

        <div className="col-xl-4">
          <div className="card h-100">
            <div className="card-header"><strong>Comment le moteur décide</strong></div>
            <div className="card-body">
              <ol className="gen-etapes">
                <li>Lecture des groupes inscrits, de leur vague et effectif réel.</li>
                <li>CM mutualisés par promotion, découpés si l'effectif dépasse la plus grande salle.</li>
                <li>TD et TP par groupe, avec meilleur ajustement de capacité.</li>
                <li>Vérification croisée salle / enseignant / groupe, puis persistance.</li>
                <li>Rapport de couverture, conflits et séances non placées.</li>
              </ol>
              <h3 className="gen-sous-titre">Bon à savoir</h3>
              <ul className="gen-savoir">
                <li>Un semestre = une grille ; les semestres impairs et pairs ne se chevauchent pas.</li>
                <li>32 créneaux hebdomadaires (5 jours × 6 créneaux + samedi matin).</li>
                <li>Les quotas par groupe évitent les semaines surchargées.</li>
                <li>Relancer la génération remplace proprement l'ancienne version du périmètre.</li>
              </ul>
            </div>
          </div>
        </div>
      </div>

      {bilan && (
        <div className="card mb-3">
          <div className="card-header">
            <strong>Bilan de la génération</strong>
          </div>
          <div className="card-body">
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
                <table className="table table-sm" aria-label="Bilan par groupe — aucune ligne n’est masquée">
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
        </div>
      )}

      <div className="row g-3 mb-3">
        <div className="col-xl-8">
          <div className="card h-100">
            <div className="card-header">
              <strong>Historique des générations</strong>
              <div className="text-muted small">
                Traçabilité complète : périmètre, volumes, conflits, durée
              </div>
            </div>
            <div className="table-responsive">
              <table className="table table-hover align-middle mb-0 gen-table">
                <thead>
                  <tr>
                    <th scope="col">Date</th>
                    <th scope="col">Périmètre</th>
                    <th scope="col">Semestres</th>
                    <th scope="col">Séances</th>
                    <th scope="col">Couverture</th>
                    <th scope="col">Conflits</th>
                    <th scope="col">Durée</th>
                    <th scope="col">Statut</th>
                  </tr>
                </thead>
                <tbody>
                  {historique.length === 0 ? (
                    <tr>
                      <td colSpan="8" className="text-center text-muted py-4">
                        Aucune génération exécutée pour le moment : lancez une
                        génération pour alimenter cet historique.
                      </td>
                    </tr>
                  ) : historique.map((ligne) => (
                    <tr key={ligne.id}>
                      <td className="text-nowrap">{formatDateHeure(ligne.date)}</td>
                      <td>
                        <span className="d-block fw-semibold">
                          {ligne.perimetre.formations.length > 0
                            ? ligne.perimetre.formations.join(', ')
                            : ligne.perimetre.filieres.length > 0
                              ? `Filière(s) ${ligne.perimetre.filieres.join(', ')}`
                              : 'Toutes filières'}
                        </span>
                        <span className="d-block small text-muted">
                          {ligne.perimetre.niveaux.length > 0
                            ? ligne.perimetre.niveaux.join(', ')
                            : 'Tous niveaux'}
                          {ligne.perimetre.groupes.length > 0
                            && ` · ${ligne.perimetre.groupes.join(', ')}`}
                        </span>
                      </td>
                      <td>{ligne.semestres.length > 0 ? ligne.semestres.join(', ') : '—'}</td>
                      <td className="fw-bold">{ligne.seances_placees ?? '—'}</td>
                      <td>{ligne.couverture_pct != null ? `${ligne.couverture_pct} %` : '—'}</td>
                      <td>
                        <span className={`gen-conflits ${ligne.conflits ? 'is-alert' : ''}`}>
                          {ligne.conflits ?? '—'}
                        </span>
                      </td>
                      <td className="text-nowrap">{formatDuree(ligne.duree_ms)}</td>
                      <td>
                        <span className={`badge ${STATUTS_EXECUTION[ligne.statut]?.classe || 'badge-neutral'}`}>
                          {STATUTS_EXECUTION[ligne.statut]?.libelle || ligne.statut}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        <div className="col-xl-4">
          <div className="card h-100">
            <div className="card-header">
              <strong>Emplois du temps versionnés</strong>
              <div className="text-muted small">Chaque passage crée une version horodatée</div>
            </div>
            <div className="card-body">
              {versions.length === 0 ? (
                <p className="text-muted small mb-0">
                  Aucun emploi du temps versionné pour le moment.
                </p>
              ) : (
                <ul className="gen-versions">
                  {versions.slice(0, 5).map((v) => (
                    <li key={v.id} className="gen-version">
                      <div className="d-flex align-items-start gap-2">
                        <span className="gen-version-code">{v.titre}</span>
                        <span className={`badge ${v.statut === 'PUBLIE' ? 'badge-success' : v.statut === 'VALIDE' ? 'badge-primary' : 'badge-neutral'}`}>
                          {(v.statut_libelle || v.statut || '').toLowerCase()}
                        </span>
                      </div>
                      <span className="gen-version-date">{formatDateHeure(v.creee_le)}</span>
                      <span className="gen-version-desc">
                        {`Emploi du temps ${v.annee_academique} · ${v.nb_seances} séances · ${v.libelle}`}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
              <Link to="/edt/versions" className="btn btn-link btn-sm px-0">
                Versions &amp; publication
                <i className="bi bi-arrow-right ms-1" aria-hidden="true"></i>
              </Link>
            </div>
          </div>
        </div>
      </div>

      <div className="card mb-3">
        <div className="card-header"><strong>Règles métier appliquées par le moteur</strong></div>
        <div className="card-body">
          <div className="row">
            <div className="col-md-6">
              <ul className="gen-regles">
                <li>Un enseignant ne peut pas être affecté à deux séances au même créneau.</li>
                <li>Un groupe ne peut pas suivre deux cours simultanément.</li>
                <li>Le meilleur ajustement de capacité est utilisé pour les TD et TP.</li>
              </ul>
            </div>
            <div className="col-md-6">
              <ul className="gen-regles">
                <li>Une salle ne peut accueillir qu'une séance par créneau et par semestre.</li>
                <li>Le CM est mutualisé au niveau de la promotion puis découpé selon la capacité des amphis.</li>
                <li>Les quotas par groupe limitent la charge hebdomadaire à 30 séances par défaut.</li>
              </ul>
            </div>
          </div>
        </div>
      </div>

      <div className="card mb-3">
        <div className="card-header">
          <strong>Import du fichier des inscrits</strong>
          <div className="text-muted small">
            Même écran que le menu « Import étudiants » : fichier externe
            (CSV / XLSX), y compris hors chaîne de parcours.
          </div>
        </div>
        <div className="card-body">
          {synthese && (
            <div className="getinjs-comptes mb-3">
              <Compte libelle="étudiants importés" valeur={synthese.effectif_total} />
              <Compte libelle="cohortes" valeur={synthese.nb_cohortes} />
            </div>
          )}
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

      {cohortes.length > 0 && (
        <div className="card">
          <div className="card-header"><strong>Cohortes importées pour cette année</strong></div>
          <div className="card-body">
            <div className="table-responsive">
              <table className="table table-sm" aria-label="Cohortes importées — effectif dénombré, jamais déclaré">
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
