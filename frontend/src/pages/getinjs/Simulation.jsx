import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import api from '../../services/api'
import { formatApiErrors } from '../../utils/apiErrors'
import './Simulation.css'

const SEMESTRES = Array.from({ length: 10 }, (_, i) => i + 1)
const BILAN_VIDE = {}
const STATUTS = {
  GENERATION_OK: 'Planifié',
  GENERATION_PARTIELLE: 'Partiel',
  GENERATION_IMPOSSIBLE: 'Impossible',
  NON_PLANIFIE: 'Non planifié',
  HORS_SEMESTRE: 'Hors semestre',
  NON_PERSISTE: 'Non persisté',
}
const liste = (data) => Array.isArray(data) ? data : (data?.results || [])
const nombres = (value) => value.split(',').map((x) => x.trim()).filter(Boolean)
  .map(Number).filter((x) => Number.isInteger(x) && x > 0)

function recommandationsPour(bilan, options) {
  const groupes = bilan?.groupes || []
  const causes = new Map()
  for (const groupe of groupes) {
    const cause = groupe.motif_echec || (groupe.seances_non_placees ? groupe.statut : '')
    if (!cause) continue
    if (!causes.has(cause)) causes.set(cause, [])
    causes.get(cause).push(groupe)
  }
  const pistes = []
  const salle = causes.get('AUCUNE_SALLE_COMPATIBLE') || []
  if (salle.length) {
    pistes.push({
      niveau: 'bloquant',
      titre: 'Corriger d’abord les salles compatibles',
      texte: `${salle.length} groupe(s) ont échoué pour AUCUNE_SALLE_COMPATIBLE${salle.length ? ` : ${salle.map((g) => g.groupe).join(', ')}` : ''}. Le moteur attribue cette cause aux contraintes de capacité ou de compatibilité de salle (C4/C7). Vérifiez les salles actives, leur capacité réelle et leur type par rapport aux séances de la maquette. Changer les semaines, le semestre ou les cases de groupe ne corrigera pas cette cause à lui seul. Relancez ensuite la même sélection pour mesurer l’effet.`,
    })
  }
  for (const [cause, titre, texte] of [
    ['AUCUNE_MAQUETTE_ACTIVE', 'Vérifier les maquettes actives', 'Le bilan indique qu’aucune maquette active n’alimente ces groupes. Vérifiez les maquettes publiées pour leur formation et leur niveau, puis relancez la même simulation.'],
    ['VOLUMES_HORAIRES_ABSENTS', 'Renseigner les volumes pédagogiques attestés', 'Le moteur ne trouve pas de volumes CM/TD/TP planifiables. Vérifiez les volumes des ECUE concernés dans la maquette réelle ; aucune séance ne peut être déduite sans ces données.'],
    ['AUCUN_BESOIN_PLANIFIABLE', 'Vérifier les besoins du groupe', 'Aucun besoin horaire calculable n’est remonté pour ces groupes. Vérifiez les affectations pédagogiques et la maquette active avant de modifier le périmètre.'],
  ]) {
    const lignes = causes.get(cause) || []
    if (lignes.length) pistes.push({
      niveau: 'bloquant', titre,
      texte: `${lignes.length} groupe(s) concerné(s) : ${lignes.map((g) => g.groupe).join(', ')}. ${texte}`,
    })
  }

  const groupesSansCauseStructurelle = groupes.filter((g) =>
    (g.seances_non_placees || 0) > 0
      && !['AUCUNE_SALLE_COMPATIBLE', 'AUCUNE_MAQUETTE_ACTIVE',
        'VOLUMES_HORAIRES_ABSENTS', 'AUCUN_BESOIN_PLANIFIABLE'].includes(g.motif_echec))
  if (groupesSansCauseStructurelle.length) {
    const variantes = []
    if (!options.inclureSamedi) variantes.push('inclure le samedi si le canevas réel contient des créneaux ce jour-là')
    if (options.eviterPause) variantes.push('autoriser les créneaux de pause méridienne si le canevas réel en propose')
    if (Number(options.maxSeances) < 60) variantes.push('tester un quota hebdomadaire plus élevé, dans la limite de 60')
    variantes.push('ajouter des semaines valides du calendrier de l’année')
    pistes.push({
      niveau: 'essai',
      titre: 'Comparer une variante de contraintes, sans changer le périmètre',
      texte: `${groupesSansCauseStructurelle.length} groupe(s) gardent des séances non placées. À tester une modification à la fois : ${variantes.join('; ')}. Rejouez ensuite exactement les mêmes groupes et semestres pour comparer les séances placées. Ces essais sont des pistes heuristiques : ils ne garantissent pas un optimum.`,
    })
  }

  const couverts = groupes.filter((g) => (g.seances_placees || 0) > 0)
  if (couverts.length && couverts.length < groupes.length) {
    pistes.push({
      niveau: 'comparaison', titre: 'Comparer les groupes qui ont déjà des séances placées',
      texte: `${couverts.map((g) => g.groupe).join(', ')} ont au moins une séance placée. Vous pouvez les isoler avec les cases à cocher pour une simulation diagnostique séparée. Attention : réduire le périmètre réduit aussi le dénominateur et ne résout pas les causes des groupes exclus.`,
    })
  }

  if (!pistes.length && bilan?.status_global === 'COMPLETE') {
    pistes.push({ niveau: 'positif', titre: 'Périmètre complet selon le moteur',
      texte: 'Toutes les séances attendues de cette sélection ont été placées dans ce calcul. Cela décrit ce périmètre et ne prouve pas un optimum global.' })
  }
  if (!pistes.length) {
    pistes.push({ niveau: 'essai', titre: 'Vérifier le périmètre et les données sources',
      texte: 'Le bilan ne permet pas d’identifier une modification de sélection qui améliorerait la couverture. Consultez les motifs par groupe, puis testez séparément toute modification de périmètre ; le pourcentage ne se compare qu’à périmètre identique.' })
  }
  return pistes
}

export default function Simulation() {
  const [annees, setAnnees] = useState([])
  const [anneeId, setAnneeId] = useState('')
  const [formations, setFormations] = useState([])
  const [niveaux, setNiveaux] = useState([])
  const [groupes, setGroupes] = useState([])
  const [filieresSel, setFilieresSel] = useState([])
  const [formationsSel, setFormationsSel] = useState([])
  const [niveauxSel, setNiveauxSel] = useState([])
  const [groupesSel, setGroupesSel] = useState([])
  const [semestresSel, setSemestresSel] = useState([])
  const [semaines, setSemaines] = useState('1')
  const [inclureSamedi, setInclureSamedi] = useState(true)
  const [eviterPause, setEviterPause] = useState(true)
  const [maxSeances, setMaxSeances] = useState('30')
  const [campagne, setCampagne] = useState(null)
  const [resultat, setResultat] = useState(null)
  const [historique, setHistorique] = useState([])
  const [chargement, setChargement] = useState(false)
  const [erreur, setErreur] = useState('')
  const [acceptee, setAcceptee] = useState(false)
  const timer = useRef(null)

  useEffect(() => {
    let active = true
    Promise.all([
      api.get('/scolarite/ref/annees/'),
      api.get('/formations/ref/formations/'),
      api.get('/scolarite/ref/niveaux/'),
    ]).then(([anneesRes, formationsRes, niveauxRes]) => {
      if (!active) return
      const anneeListe = liste(anneesRes.data)
      setAnnees(anneeListe)
      setAnneeId(String(anneeListe.find((a) => a.courante)?.id || anneeListe[0]?.id || ''))
      setFormations(liste(formationsRes.data))
      setNiveaux(liste(niveauxRes.data))
    }).catch((err) => { if (active) setErreur(formatApiErrors(err?.response?.data) || 'Référentiels indisponibles.') })
    return () => { active = false }
  }, [])

  useEffect(() => {
    if (!anneeId) { setGroupes([]); return undefined }
    let active = true
    api.get('/scolarite/ref/groupes/', { params: { annee_academique_id: anneeId } })
      .then(({ data }) => { if (active) setGroupes(liste(data)) })
      .catch(() => { if (active) setGroupes([]) })
    return () => { active = false }
  }, [anneeId])

  const formationsDansAnnee = useMemo(() => formations.filter((f) =>
    groupes.some((g) => Number(g.ref_formation_id) === Number(f.id))), [formations, groupes])
  const filieresDisponibles = useMemo(() => [...new Map(formationsDansAnnee
    .filter((f) => f.filiere_code).map((f) => [f.filiere_code, f.filiere_code])).values()], [formationsDansAnnee])
  const formationsDisponibles = useMemo(() => formationsDansAnnee.filter((f) =>
    !filieresSel.length || filieresSel.includes(f.filiere_code)), [formationsDansAnnee, filieresSel])
  const groupesDisponibles = useMemo(() => groupes.filter((g) =>
    (!formationsSel.length || formationsSel.includes(Number(g.ref_formation_id)))
    && (!niveauxSel.length || niveauxSel.includes(Number(g.niveau_id)))), [groupes, formationsSel, niveauxSel])

  useEffect(() => {
    const disponibles = new Set(formationsDisponibles.map((f) => Number(f.id)))
    setFormationsSel((current) => current.filter((id) => disponibles.has(Number(id))))
  }, [formationsDisponibles])

  useEffect(() => {
    const disponibles = new Set(groupesDisponibles.map((g) => Number(g.id)))
    setGroupesSel((current) => current.filter((id) => disponibles.has(Number(id))))
  }, [groupesDisponibles])

  const chargerHistorique = useCallback(async () => {
    if (!anneeId) return
    try {
      const { data } = await api.get('/edts/campagnes/', { params: { annee: anneeId, simulation: true, limite: 100 } })
      setHistorique(data?.results || [])
    } catch { setHistorique([]) }
  }, [anneeId])
  useEffect(() => { chargerHistorique() }, [chargerHistorique])

  useEffect(() => () => clearTimeout(timer.current), [])

  const chargerResultat = useCallback(async (id) => {
    const { data } = await api.get(`/edts/campagnes/${id}/resultat/`)
    setResultat(data)
    setCampagne(data.campagne)
    setAcceptee(Boolean(data.campagne?.parametres?.simulation_acceptee))
    return data
  }, [])

  const suivre = async (id) => {
    for (let i = 0; i < 180; i += 1) {
      const { data } = await api.get(`/edts/campagnes/${id}/statut/`)
      if (data.en_cours === false) {
        await chargerResultat(id)
        await chargerHistorique()
        return
      }
      await new Promise((resolve) => { timer.current = setTimeout(resolve, 2000) })
    }
    throw new Error('Le calcul continue côté serveur ; retrouvez son état dans l’historique.')
  }

  const lancer = async (event) => {
    event.preventDefault()
    setErreur('')
    const semainesListe = nombres(semaines)
    if (!anneeId || !formationsSel.length || !niveauxSel.length || !groupesSel.length || !semestresSel.length) {
      setErreur('Sélectionnez une année, au moins une formation, un niveau, un groupe et un semestre.')
      return
    }
    if (!semainesListe.length || semaines.split(',').some((s) => !/^\s*\d+\s*$/.test(s))
        || semainesListe.some((s) => s > 53)) {
      setErreur('Les semaines doivent être des numéros entiers de 1 à 53, séparés par des virgules.')
      return
    }
    setChargement(true)
    setResultat(null)
    setAcceptee(false)
    try {
      const { data: created } = await api.post('/edts/simulations/', {
        annee_academique_id: Number(anneeId), semaines: semainesListe,
        perimetre: { formations: formationsSel, niveaux: niveauxSel, groupes: groupesSel, semestres: semestresSel },
        parametres: { inclure_maquette: true, inclure_samedi: inclureSamedi,
          eviter_pause_meridienne: eviterPause, max_seances_par_groupe_semaine: Number(maxSeances) || null },
      })
      setCampagne(created)
      await api.post(`/edts/campagnes/${created.id}/donnees-pretes/`, {})
      await api.post(`/edts/campagnes/${created.id}/demarrer/`, { asynchrone: true })
      await suivre(created.id)
    } catch (err) {
      setErreur(formatApiErrors(err?.response?.data) || err?.message || 'Simulation impossible.')
    } finally {
      setChargement(false)
    }
  }

  const ouvrirHistorique = async (item) => {
    setErreur('')
    try { await chargerResultat(item.id) } catch (err) {
      setErreur(formatApiErrors(err?.response?.data) || 'Résultat indisponible.')
    }
  }

  const accepter = async () => {
    if (!campagne?.id || !window.confirm('Confirmer la revue humaine de ce résultat ? Aucun EDT ne sera créé ou publié.')) return
    try {
      const { data } = await api.post(`/edts/simulations/${campagne.id}/accepter/`, {})
      setCampagne(data)
      setAcceptee(true)
      await chargerHistorique()
    } catch (err) { setErreur(formatApiErrors(err?.response?.data) || 'Acceptation impossible.') }
  }

  const bilan = resultat || BILAN_VIDE
  const totaux = bilan.totaux || {}
  const recommandations = useMemo(() => recommandationsPour(bilan, {
    inclureSamedi, eviterPause, maxSeances,
  }), [bilan, inclureSamedi, eviterPause, maxSeances])
  const couverture = totaux.seances_attendues
    ? Math.round((totaux.seances_placees || 0) * 100 / totaux.seances_attendues) : null
  const peutAccepter = campagne?.parametres?.simulation
    && ['TERMINE', 'TERMINE_AVEC_ANOMALIES'].includes(campagne.statut)

  return (
    <main className="container-fluid py-3">
      <header className="d-flex flex-wrap justify-content-between align-items-center gap-2 mb-3">
        <div><h1 className="h3 mb-1">Simulation EDT — GET INJS</h1>
          <p className="text-muted mb-0">Même moteur que Génération manuelle. Calcul non persistant, revue humaine, transfert explicite.</p></div>
        <Link className="btn btn-outline-secondary" to="/edt/generation-annuelle">Aller à Génération</Link>
      </header>
      <div className="alert alert-info" role="note"><strong>Simulation sans écriture.</strong> Les résultats ne créent, ne remplacent, ne valident et ne publient aucun EDT. Un transfert ne lance pas la génération : il préremplit son formulaire, où une nouvelle prévisualisation reste obligatoire.</div>
      {erreur && <div className="alert alert-danger" role="alert">{erreur}</div>}
      <form className="card card-body mb-4" onSubmit={lancer}>
        <h2 className="h5">Périmètre et contraintes réels</h2>
        <div className="row g-3">
          <div className="col-md-4"><label className="form-label" htmlFor="sim-annee">Année académique (une année par calcul)</label><select id="sim-annee" className="form-select" value={anneeId} onChange={(e) => setAnneeId(e.target.value)}><option value="">Choisir…</option>{annees.map((a) => <option key={a.id} value={a.id}>{a.libelle}</option>)}</select></div>
          <ChampMultiple id="sim-filieres" label="Filières présentes dans l’année" values={filieresSel} options={filieresDisponibles.map((f) => [f, f])} numeric={false} onChange={setFilieresSel} />
          <ChampMultiple id="sim-formations" label="Formations INJS" values={formationsSel} options={formationsDisponibles.map((f) => [f.id, f.intitule || f.libelle || f.code])} onChange={setFormationsSel} />
          <ChampMultiple id="sim-niveaux" label="Niveaux" values={niveauxSel} options={niveaux.map((n) => [n.id, n.code || n.libelle])} onChange={setNiveauxSel} />
          <ChampMultiple id="sim-groupes" label="Groupes de l’année" values={groupesSel} options={groupesDisponibles.map((g) => [g.id, `${g.nom} — ${g.niveau_code || g.niveau || g.niveau_id}`])} onChange={setGroupesSel} />
          <ChampMultiple id="sim-semestres" label="Semestres" values={semestresSel} options={SEMESTRES.map((s) => [s, `Semestre ${s} (S${s})`])} onChange={setSemestresSel} />
          <div className="col-md-3"><label className="form-label" htmlFor="sim-semaines">Semaines (1–53)</label><input id="sim-semaines" className="form-control" value={semaines} onChange={(e) => setSemaines(e.target.value)} placeholder="1,2,3" /></div>
          <div className="col-md-3"><label className="form-label" htmlFor="sim-quota">Séances max / groupe / semaine</label><input id="sim-quota" type="number" min="1" max="60" className="form-control" value={maxSeances} onChange={(e) => setMaxSeances(e.target.value)} /></div>
          <div className="col-md-3 d-flex flex-column justify-content-center"><label className="form-check"><input className="form-check-input" type="checkbox" checked={inclureSamedi} onChange={(e) => setInclureSamedi(e.target.checked)} /> Inclure samedi</label><label className="form-check"><input className="form-check-input" type="checkbox" checked={eviterPause} onChange={(e) => setEviterPause(e.target.checked)} /> Éviter pause méridienne</label></div>
        </div>
        <div className="mt-3"><button className="btn btn-primary" type="submit" disabled={chargement}>{chargement ? 'Calcul en cours…' : 'Simuler avec le moteur EDT'}</button>{campagne?.statut === 'EN_COURS' && <span className="ms-3" role="status">Calcul réel en arrière-plan, suivi de son statut…</span>}</div>
      </form>

      {resultat && <section className="card card-body mb-4" aria-label="Résultat de simulation">
        <div className="d-flex flex-wrap justify-content-between gap-2"><div><h2 className="h5 mb-1">Résultat : {campagne?.status_global || campagne?.statut_libelle}</h2><p className="text-muted">{campagne?.libelle} · Simulation persistée dans l’historique · les EDT restent inchangés.</p></div><span className={`badge ${campagne?.status_global === 'COMPLETE' ? 'text-bg-success' : 'text-bg-warning'}`}>{campagne?.status_global || campagne?.statut}</span></div>
        <div className="row g-2 mb-3">
          <Indicateur label="Groupes calculés" value={bilan.sources?.nb_groupes ?? '—'} /><Indicateur label="Séances placées / attendues" value={`${totaux.seances_placees ?? '—'} / ${totaux.seances_attendues ?? '—'}`} /><Indicateur label="Couverture observée" value={couverture == null ? '—' : `${couverture} %`} /><Indicateur label="Non placées / conflits" value={`${totaux.seances_non_placees ?? '—'} / ${totaux.conflits ?? '—'}`} />
        </div>
        <p className="small text-muted">Ces valeurs proviennent du bilan réel du moteur. Elles ne démontrent pas une optimalité globale. Statut : {campagne?.statut_libelle || campagne?.statut}; anomalies : {bilan.anomalies?.length ?? '—'}.</p>
        {(bilan.detail?.explication || bilan.detail?.action_recommandee) && <div className="alert alert-warning"><strong>Analyse du moteur.</strong> {bilan.detail.explication} {bilan.detail.action_recommandee}</div>}
        <div className="table-responsive"><table className="table table-sm"><thead><tr><th>Formation</th><th>Niveau</th><th>Groupe</th><th>Statut</th><th>Séances</th><th>Non placées</th><th>Conflits</th><th>Motif</th></tr></thead><tbody>{(bilan.groupes || []).map((g) => <tr key={g.groupe_id}><td>{g.formation}</td><td>{g.niveau}</td><td>{g.groupe}</td><td>{STATUTS[g.statut] || g.statut}</td><td>{g.seances_placees ?? 0}/{g.seances_attendues ?? 0}</td><td>{g.seances_non_placees ?? 0}</td><td>{g.conflits ?? '—'}</td><td>{g.motif_echec || '—'}</td></tr>)}</tbody></table></div>
        <section className="alert alert-light border mb-3" aria-label="Pistes d’amélioration de la couverture">
          <h3 className="h6">Pistes pour améliorer la couverture</h3>
          <p className="small text-muted">Suggestions dérivées des motifs et options réels de cette simulation. Ce sont des essais à comparer, pas une promesse d’optimalité. Gardez le même périmètre pour comparer les taux.</p>
          <ul className="mb-0">{recommandations.map((piste, index) => <li className="mb-2" key={`${piste.titre}-${index}`}><strong>{piste.titre}.</strong> {piste.texte}</li>)}</ul>
        </section>
        {!!bilan.anomalies?.length && <details className="mb-3"><summary>Anomalies calculées ({bilan.anomalies.length})</summary><ul>{bilan.anomalies.map((a, i) => <li key={`${a.nature}-${i}`}>{a.nature}: {a.explication || a.motif || '—'}</li>)}</ul></details>}
        {peutAccepter && !acceptee && <button className="btn btn-outline-primary" type="button" onClick={accepter}>Accepter après revue humaine</button>}
        {acceptee && <div className="alert alert-success mb-0">Résultat accepté par un utilisateur habilité. <Link className="btn btn-sm btn-success ms-2" to={`/edt/generation-annuelle?simulation_id=${campagne.id}`}>Transférer vers Génération → Manuel</Link></div>}
      </section>}

      <section className="card card-body"><div className="d-flex justify-content-between align-items-center"><h2 className="h5">Historique des simulations</h2><button className="btn btn-sm btn-outline-secondary" onClick={chargerHistorique} type="button">Actualiser</button></div>
        {!historique.length ? <p className="text-muted mb-0">Aucune simulation enregistrée pour cette année.</p> : <div className="table-responsive"><table className="table table-sm"><thead><tr><th>Libellé</th><th>Statut</th><th>Créée</th><th>Revue</th><th></th></tr></thead><tbody>{historique.map((h) => <tr key={h.id}><td>{h.libelle}</td><td>{h.status_global || h.statut_libelle || h.statut}</td><td>{h.created_at ? new Date(h.created_at).toLocaleString('fr-FR') : '—'}</td><td>{h.parametres?.simulation_acceptee ? 'Acceptée' : 'À examiner'}</td><td><button className="btn btn-sm btn-outline-primary" type="button" onClick={() => ouvrirHistorique(h)}>Consulter</button></td></tr>)}</tbody></table></div>}
      </section>
    </main>
  )
}

function ChampMultiple({ id, label, values, options, onChange, numeric = true }) {
  const selection = new Set(values.map(String))
  const toutesCochees = options.length > 0 && options.every(([value]) => selection.has(String(value)))
  const valeurNormalisee = (value) => (numeric ? Number(value) : value)
  const basculer = (value, cochee) => {
    const cle = String(value)
    onChange(cochee
      ? [...values.filter((v) => String(v) !== cle), valeurNormalisee(value)]
      : values.filter((v) => String(v) !== cle))
  }

  return (
    <div className="col-md-4">
      <fieldset className="sim-multiple-fieldset">
        <legend>{label}</legend>
        <div className="d-flex justify-content-end mb-1">
          <button
            type="button"
            className="btn btn-link btn-sm p-0 text-decoration-none"
            onClick={() => onChange(toutesCochees ? [] : options.map(([value]) => valeurNormalisee(value)))}
            disabled={!options.length}
            aria-label={`${toutesCochees ? 'Tout désélectionner' : 'Tout sélectionner'} : ${label}`}
          >
            {toutesCochees ? 'Tout désélectionner' : 'Tout sélectionner'}
          </button>
        </div>
        <div className="sim-multiple-options">
          {options.length ? options.map(([value, text]) => {
            const checkboxId = `${id}-${value}`
            return (
              <div className="form-check sim-multiple-option" key={value}>
                <input
                  id={checkboxId}
                  className="form-check-input"
                  type="checkbox"
                  checked={selection.has(String(value))}
                  onChange={(event) => basculer(value, event.target.checked)}
                />
                <label className="form-check-label" htmlFor={checkboxId}>{text}</label>
              </div>
            )
          }) : <span className="small text-muted">Aucune option disponible</span>}
        </div>
        <small className="text-muted">Cochez une ou plusieurs cases.</small>
      </fieldset>
    </div>
  )
}
function Indicateur({ label, value }) { return <div className="col-md-3"><div className="border rounded p-2 h-100"><div className="h5 mb-0">{typeof value === 'number' ? value.toLocaleString('fr-FR') : value}</div><small className="text-muted">{label}</small></div></div> }
