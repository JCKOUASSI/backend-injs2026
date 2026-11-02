import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import api from '../../services/api'
import {
  getAnneeCourante, getReinscriptions, getReinscriptionsStats, reinscrire,
} from '../../services/scolarite'
import { canActScolarite } from '../../utils/roles'
import { useAuth } from '../../context/AuthContext'
import { useToast } from '../../context/ToastContext'
import { useDebounce } from '../../hooks/useDebounce'
import '../../styles/candidatures.css'
import '../../styles/reinscriptions.css'

/** Flux de continuité (hors premières inscriptions) : code, libellé, ton. */
const FLUX = [
  { value: '', label: 'Tous les flux', icone: 'bi-arrow-repeat', ton: 'blue' },
  { value: 'REINSCRIPTION', label: 'Réinscriptions', icone: 'bi-arrow-clockwise', ton: 'green' },
  { value: 'REDOUBLEMENT', label: 'Redoublements', icone: 'bi-arrow-counterclockwise', ton: 'amber' },
  { value: 'TRANSFERT', label: 'Transferts', icone: 'bi-arrow-left-right', ton: 'indigo' },
  { value: 'REORIENTATION', label: 'Réorientations', icone: 'bi-signpost-split', ton: 'cyan' },
  { value: 'REPRISE', label: 'Reprises', icone: 'bi-play-circle', ton: 'slate' },
]

const TON_TYPE = {
  REINSCRIPTION: 'green', REDOUBLEMENT: 'amber', TRANSFERT: 'indigo',
  REORIENTATION: 'cyan', REPRISE: 'slate', PREMIERE: 'blue',
}

const TON_STATUT = {
  VALIDEE: 'green', BROUILLON: 'amber', EN_ATTENTE: 'blue', A_VALIDER: 'indigo',
  REJETEE: 'red', ANNULEE: 'slate', SUSPENDUE: 'red', TERMINEE: 'slate',
}

const STATUTS = [
  { value: '', label: 'Tous les statuts' },
  { value: 'BROUILLON', label: 'Brouillon' },
  { value: 'EN_ATTENTE', label: 'En attente' },
  { value: 'A_VALIDER', label: 'À valider' },
  { value: 'VALIDEE', label: 'Validée' },
  { value: 'REJETEE', label: 'Rejetée' },
  { value: 'ANNULEE', label: 'Annulée' },
  { value: 'SUSPENDUE', label: 'Suspendue' },
  { value: 'TERMINEE', label: 'Terminée' },
]

const ORDRE_NIVEAUX = ['L1', 'L2', 'L3', 'M1', 'M2', 'D1', 'D2', 'D3']

/** Date ISO « AAAA-MM-JJ… » → JJ/MM/AAAA ('—' si absente), sans heure. */
const formatDate = (iso) => {
  if (!iso) return '—'
  const [annee, mois, jour] = String(iso).slice(0, 10).split('-')
  return annee && mois && jour ? `${jour}/${mois}/${annee}` : '—'
}

const formatNombre = (n) => Number(n || 0).toLocaleString('fr-FR')

/** Premier message exploitable d'une erreur API (409 simple ou dict de champs). */
const messageErreur = (err, repli) => {
  const data = err.response?.data
  if (!data) return repli
  if (typeof data.error === 'string') return data.error
  if (Array.isArray(data.error) && data.error.length) return data.error[0]
  for (const valeur of Object.values(data)) {
    if (Array.isArray(valeur) && valeur.length) return valeur[0]
    if (typeof valeur === 'string') return valeur
  }
  return repli
}

export default function Reinscriptions() {
  const { user } = useAuth()
  const toast = useToast()
  const peutAgir = canActScolarite(user)

  const [resultats, setResultats] = useState([])
  const [total, setTotal] = useState(0)
  const [totalPages, setTotalPages] = useState(1)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(25)
  const [chargement, setChargement] = useState(true)
  const [stats, setStats] = useState(null)

  const [anneeId, setAnneeId] = useState('')
  const [typeFiltre, setTypeFiltre] = useState('')
  const [statut, setStatut] = useState('')
  const [formationId, setFormationId] = useState('')
  const [niveauId, setNiveauId] = useState('')
  const [recherche, setRecherche] = useState('')
  const rechercheAttendue = useDebounce(recherche)
  const [options, setOptions] = useState({ annees: [], formations: [], niveaux: [] })
  const [refsPretes, setRefsPretes] = useState(false)

  // ── Formulaire « Réinscrire un étudiant » ──
  const [saisieEtudiant, setSaisieEtudiant] = useState('')
  const saisieAttendue = useDebounce(saisieEtudiant)
  const [propositions, setPropositions] = useState([])
  const [etudiantChoisi, setEtudiantChoisi] = useState(null)
  const [formReins, setFormReins] = useState({
    annee_academique_id: '', niveau_id: '', type_inscription: 'REINSCRIPTION', valider: false,
  })
  const [enCours, setEnCours] = useState(false)

  const allerPage1 = useCallback((setter) => (valeur) => {
    setter(valeur)
    setPage(1)
  }, [])

  // Référentiels + année courante par défaut.
  useEffect(() => {
    ;(async () => {
      try {
        const [annees, formations, niveaux, courante] = await Promise.all([
          api.get('/scolarite/ref/annees/'),
          api.get('/scolarite/ref/formations/'),
          api.get('/scolarite/ref/niveaux/', { params: { actif: 'true' } }),
          getAnneeCourante(),
        ])
        setOptions({
          annees: Array.isArray(annees.data) ? annees.data : [],
          formations: Array.isArray(formations.data) ? formations.data : [],
          niveaux: Array.isArray(niveaux.data) ? niveaux.data : [],
        })
        if (courante?.id) {
          setAnneeId(String(courante.id))
          setFormReins((f) => ({ ...f, annee_academique_id: String(courante.id) }))
        }
      } catch {
        toast.showToast('Chargement des référentiels impossible.', 'error')
      } finally {
        setRefsPretes(true)
      }
    })()
  }, [toast])

  // Panorama des flux (compteurs exacts, indépendants de la pagination).
  const chargerStats = useCallback(async () => {
    try {
      const res = await getReinscriptionsStats(
        anneeId ? { annee_academique_id: anneeId } : undefined,
      )
      const data = res.data
      if (data && !Array.isArray(data) && typeof data.total_flux === 'number') {
        setStats(data)
      }
    } catch {
      setStats(null)
    }
  }, [anneeId])

  useEffect(() => { if (refsPretes) chargerStats() }, [chargerStats, refsPretes])

  // Liste paginée côté serveur (total réel, pas de plafond à 500).
  const chargerListe = useCallback(async () => {
    setChargement(true)
    try {
      const params = { page, page_size: pageSize }
      if (anneeId) params.annee_academique_id = anneeId
      if (typeFiltre) params.type_inscription = typeFiltre
      if (statut) params.statut = statut
      if (formationId) params.ref_formation_id = formationId
      if (niveauId) params.niveau_id = niveauId
      if (rechercheAttendue.trim()) params.search = rechercheAttendue.trim()
      const res = await getReinscriptions(params)
      const data = res.data || {}
      setResultats(Array.isArray(data.results) ? data.results : [])
      setTotal(typeof data.count === 'number' ? data.count : 0)
      setTotalPages(Math.max(1, typeof data.total_pages === 'number' ? data.total_pages : 1))
    } catch (err) {
      toast.showToast(messageErreur(err, 'Chargement des flux impossible.'), 'error')
    } finally {
      setChargement(false)
    }
  }, [page, pageSize, anneeId, typeFiltre, statut, formationId, niveauId, rechercheAttendue, toast])

  useEffect(() => { if (refsPretes) chargerListe() }, [chargerListe, refsPretes])

  // Recherche d'étudiant pour la réinscription.
  useEffect(() => {
    const terme = (saisieAttendue || '').trim()
    if (!peutAgir || terme.length < 2 || etudiantChoisi) {
      setPropositions([])
      return
    }
    let annule = false
    api.get('/scolarite/etudiants/', { params: { q: terme, page: 1, page_size: 10 } })
      .then((res) => {
        if (annule) return
        const liste = Array.isArray(res.data) ? res.data : (res.data?.results || [])
        setPropositions(Array.isArray(liste) ? liste : [])
      })
      .catch(() => {})
    return () => { annule = true }
  }, [saisieAttendue, peutAgir, etudiantChoisi])

  const soumettreReinscription = async (e) => {
    e.preventDefault()
    if (!etudiantChoisi) {
      toast.showToast('Choisissez d’abord l’étudiant à réinscrire.', 'error')
      return
    }
    setEnCours(true)
    try {
      await reinscrire({
        etudiant_id: etudiantChoisi.id,
        annee_academique_id: Number(formReins.annee_academique_id) || undefined,
        niveau_id: Number(formReins.niveau_id) || undefined,
        type_inscription: formReins.type_inscription,
        valider: formReins.valider,
      })
      toast.showToast(
        `Réinscription enregistrée pour ${etudiantChoisi.nom_complet}${formReins.valider ? ' (validée)' : ''}.`,
      )
      setEtudiantChoisi(null)
      setSaisieEtudiant('')
      chargerListe()
      chargerStats()
    } catch (err) {
      toast.showToast(messageErreur(err, 'Réinscription impossible.'), 'error')
    } finally {
      setEnCours(false)
    }
  }

  const compteFlux = (value) => {
    if (!stats) return null
    return value ? (stats.par_type?.[value] || 0) : stats.total_flux
  }

  const niveauxPanorama = useMemo(() => {
    if (!stats?.par_niveau) return []
    const max = Math.max(1, ...Object.values(stats.par_niveau))
    return ORDRE_NIVEAUX
      .filter((code) => stats.par_niveau[code])
      .map((code) => ({ code, total: stats.par_niveau[code], pct: (stats.par_niveau[code] / max) * 100 }))
  }, [stats])

  const autresFlux = stats
    ? (stats.par_type?.TRANSFERT || 0) + (stats.par_type?.REORIENTATION || 0) + (stats.par_type?.REPRISE || 0)
    : 0

  return (
    <div className="cand-page rei-page">
      {/* ── Bandeau d'accueil ── */}
      <div className="cand-hero">
        <div className="cand-hero-identite">
          <span className="cand-hero-icone" aria-hidden="true">
            <i className="bi bi-arrow-repeat"></i>
          </span>
          <div className="cand-hero-text">
            <span className="cand-hero-badge">Scolarité — Continuité de parcours</span>
            <h1 className="cand-hero-title">Réinscriptions &amp; transferts</h1>
            <p className="cand-hero-sub">
              Flux de continuité des étudiants déjà inscrits : réinscriptions, redoublements,
              transferts, réorientations et reprises (hors premières inscriptions).
            </p>
          </div>
        </div>
        <div className="cand-hero-actions">
          <span className="rei-pastille rei-pastille--primary">
            <i className="bi bi-calendar3" aria-hidden="true"></i>
            {stats?.annee_academique || 'Année en cours'}
          </span>
          <span className="rei-pastille rei-pastille--neutre">
            <i className="bi bi-arrow-repeat" aria-hidden="true"></i>
            {formatNombre(stats?.total_flux)} flux
          </span>
          <span className="rei-pastille rei-pastille--neutre">
            <i className="bi bi-graph-up-arrow" aria-hidden="true"></i>
            {stats ? `${stats.taux_continuite} % de continuité` : 'Continuité…'}
          </span>
        </div>
      </div>

      {/* ── Indicateurs ── */}
      <div className="cand-kpi-row">
        <div className="cand-kpi">
          <span className="cand-kpi-icon is-blue" aria-hidden="true"><i className="bi bi-arrow-repeat"></i></span>
          <div className="cand-kpi-texte">
            <span className="cand-kpi-value">{stats ? formatNombre(stats.total_flux) : '—'}</span>
            <span className="cand-kpi-label">Flux de continuité</span>
            <span className="rei-kpi-sub">
              {stats ? `${formatNombre(stats.total_inscriptions)} inscriptions au total` : 'Chargement…'}
            </span>
          </div>
        </div>
        <div className="cand-kpi">
          <span className="cand-kpi-icon is-green" aria-hidden="true"><i className="bi bi-arrow-clockwise"></i></span>
          <div className="cand-kpi-texte">
            <span className="cand-kpi-value">{stats ? formatNombre(stats.par_type?.REINSCRIPTION) : '—'}</span>
            <span className="cand-kpi-label">Réinscriptions</span>
            <span className="rei-kpi-sub">Passages en année supérieure</span>
          </div>
        </div>
        <div className="cand-kpi">
          <span className="cand-kpi-icon is-amber" aria-hidden="true"><i className="bi bi-arrow-counterclockwise"></i></span>
          <div className="cand-kpi-texte">
            <span className="cand-kpi-value">{stats ? formatNombre(stats.par_type?.REDOUBLEMENT) : '—'}</span>
            <span className="cand-kpi-label">Redoublements</span>
            <span className="rei-kpi-sub">Reprises du même niveau</span>
          </div>
        </div>
        <div className="cand-kpi">
          <span className="cand-kpi-icon is-slate" aria-hidden="true"><i className="bi bi-arrow-left-right"></i></span>
          <div className="cand-kpi-texte">
            <span className="cand-kpi-value">{stats ? formatNombre(autresFlux) : '—'}</span>
            <span className="cand-kpi-label">Transferts &amp; passerelles</span>
            <span className="rei-kpi-sub">
              {stats
                ? `${formatNombre(stats.par_type?.TRANSFERT)} transfert(s) · ${formatNombre(stats.par_type?.REORIENTATION)} réorientation(s) · ${formatNombre(stats.par_type?.REPRISE)} reprise(s)`
                : 'Chargement…'}
            </span>
          </div>
        </div>
      </div>

      {/* ── Panorama par niveau ── */}
      {niveauxPanorama.length > 0 && (
        <section className="cand-panel" aria-labelledby="titre-panorama-reinscriptions">
          <header className="cand-panel-head">
            <h2 className="cand-panel-title" id="titre-panorama-reinscriptions">
              <i className="bi bi-bar-chart-steps" aria-hidden="true"></i>Flux par niveau d’arrivée
            </h2>
            <span className="cand-count-pill">{stats?.annee_academique}</span>
          </header>
          <div className="cand-panel-body">
            <div className="rei-niveaux">
              {niveauxPanorama.map((n) => (
                <div className="rei-niveau" key={n.code}>
                  <span className="rei-niveau-code">{n.code}</span>
                  <span className="rei-niveau-barre" aria-hidden="true">
                    <span className="rei-niveau-remplissage" style={{ width: `${n.pct}%` }}></span>
                  </span>
                  <span className="rei-niveau-total">{formatNombre(n.total)}</span>
                </div>
              ))}
            </div>
            <p className="rei-note">
              <i className="bi bi-info-circle" aria-hidden="true"></i>
              Les premières inscriptions (nouveaux entrants) se gèrent dans
              {' '}<Link to="/scolarite/inscriptions">Inscriptions administratives</Link> ; cet
              écran ne présente que la continuité des parcours déjà ouverts.
            </p>
          </div>
        </section>
      )}

      {/* ── Réinscrire un étudiant ── */}
      {peutAgir && (
        <section className="cand-panel" aria-labelledby="titre-reinscrire">
          <header className="cand-panel-head">
            <h2 className="cand-panel-title" id="titre-reinscrire">
              <i className="bi bi-person-plus" aria-hidden="true"></i>Réinscrire un étudiant
            </h2>
            <span className="cand-count-pill">Dossier existant requis</span>
          </header>
          <div className="cand-panel-body">
            <form className="cand-grille-form rei-form" onSubmit={soumettreReinscription}>
              <div className="cand-champ rei-champ-recherche">
                <label className="cand-etiquette" htmlFor="rei-recherche-etudiant">Étudiant *</label>
                {etudiantChoisi ? (
                  <div className="rei-etudiant-choisi">
                    <span>
                      <strong>{etudiantChoisi.nom_complet}</strong>
                      <small>{etudiantChoisi.matricule}</small>
                    </span>
                    <button
                      type="button" className="rei-retirer" aria-label="Changer d’étudiant"
                      onClick={() => { setEtudiantChoisi(null); setSaisieEtudiant('') }}>
                      <i className="bi bi-x-lg" aria-hidden="true"></i>
                    </button>
                  </div>
                ) : (
                  <>
                    <input
                      id="rei-recherche-etudiant" type="search" className="cand-saisie"
                      placeholder="Nom ou matricule…"
                      value={saisieEtudiant}
                      onChange={(e) => setSaisieEtudiant(e.target.value)}
                    />
                    {propositions.length > 0 && (
                      <div className="rei-propositions">
                        {propositions.map((e) => (
                          <button
                            type="button" key={e.id} className="rei-proposition"
                            onClick={() => { setEtudiantChoisi(e); setPropositions([]) }}>
                            <span className="rei-proposition-nom">{e.nom_complet}</span>
                            <span className="rei-proposition-matricule">{e.matricule}</span>
                          </button>
                        ))}
                      </div>
                    )}
                  </>
                )}
              </div>
              <div className="cand-champ">
                <label className="cand-etiquette" htmlFor="rei-annee">Année académique *</label>
                <select
                  id="rei-annee" className="cand-saisie" required value={formReins.annee_academique_id}
                  onChange={(e) => setFormReins({ ...formReins, annee_academique_id: e.target.value })}>
                  <option value="">Année…</option>
                  {options.annees.map((a) => <option key={a.id} value={a.id}>{a.libelle}</option>)}
                </select>
              </div>
              <div className="cand-champ">
                <label className="cand-etiquette" htmlFor="rei-niveau">Niveau d’arrivée *</label>
                <select
                  id="rei-niveau" className="cand-saisie" required value={formReins.niveau_id}
                  onChange={(e) => setFormReins({ ...formReins, niveau_id: e.target.value })}>
                  <option value="">Niveau…</option>
                  {options.niveaux.map((n) => <option key={n.id} value={n.id}>{n.code}</option>)}
                </select>
              </div>
              <div className="cand-champ">
                <label className="cand-etiquette" htmlFor="rei-type">Type de flux</label>
                <select
                  id="rei-type" className="cand-saisie" value={formReins.type_inscription}
                  onChange={(e) => setFormReins({ ...formReins, type_inscription: e.target.value })}>
                  {FLUX.filter((f) => f.value).map((f) => (
                    <option key={f.value} value={f.value}>{f.label.replace(/s$/, '')}</option>
                  ))}
                </select>
              </div>
              <div className="rei-form-pied">
                <label className="rei-valider">
                  <input
                    type="checkbox" checked={formReins.valider}
                    onChange={(e) => setFormReins({ ...formReins, valider: e.target.checked })}
                  />
                  Valider immédiatement l’inscription
                </label>
                <p className="rei-note">
                  <i className="bi bi-info-circle" aria-hidden="true"></i>
                  La formation, le parcours et le profil sont repris de la dernière inscription
                  validée de l’étudiant ; aucun nouveau dossier n’est créé.
                </p>
                <button type="submit" className="cand-btn-principal" disabled={enCours}>
                  <i className="bi bi-arrow-repeat" aria-hidden="true"></i>Réinscrire
                </button>
              </div>
            </form>
          </div>
        </section>
      )}

      {/* ── Filtres ── */}
      <section className="cand-panel" aria-labelledby="titre-filtres-reinscriptions">
        <header className="cand-panel-head">
          <h2 className="cand-panel-title" id="titre-filtres-reinscriptions">
            <i className="bi bi-funnel" aria-hidden="true"></i>Filtres et recherche
          </h2>
          <span className="cand-count-pill">{formatNombre(total)} flux</span>
        </header>
        <div className="cand-panel-body">
          <div className="rei-segments" role="group" aria-label="Filtrer par type de flux">
            {FLUX.map((f) => (
              <button
                key={f.value || 'tous'}
                type="button"
                className={`rei-segment is-${f.ton}${typeFiltre === f.value ? ' is-active' : ''}`}
                aria-pressed={typeFiltre === f.value}
                onClick={() => allerPage1(setTypeFiltre)(f.value)}
              >
                <i className={`bi ${f.icone}`} aria-hidden="true"></i>
                {f.label}
                {compteFlux(f.value) !== null && (
                  <span className="rei-segment-nb">{formatNombre(compteFlux(f.value))}</span>
                )}
              </button>
            ))}
          </div>
          <div className="rei-filtres">
            <div className="rei-filtre">
              <label className="cand-etiquette" htmlFor="rei-filtre-annee">Année académique</label>
              <select
                id="rei-filtre-annee" className="cand-filter-select" value={anneeId}
                onChange={(e) => allerPage1(setAnneeId)(e.target.value)}>
                <option value="">Toutes les années</option>
                {options.annees.map((a) => <option key={a.id} value={a.id}>{a.libelle}</option>)}
              </select>
            </div>
            <div className="rei-filtre">
              <label className="cand-etiquette" htmlFor="rei-filtre-formation">Formation</label>
              <select
                id="rei-filtre-formation" className="cand-filter-select" value={formationId}
                onChange={(e) => allerPage1(setFormationId)(e.target.value)}>
                <option value="">Toutes les formations</option>
                {options.formations.map((f) => <option key={f.id} value={f.id}>{f.intitule}</option>)}
              </select>
            </div>
            <div className="rei-filtre">
              <label className="cand-etiquette" htmlFor="rei-filtre-niveau">Niveau</label>
              <select
                id="rei-filtre-niveau" className="cand-filter-select" value={niveauId}
                onChange={(e) => allerPage1(setNiveauId)(e.target.value)}>
                <option value="">Tous les niveaux</option>
                {options.niveaux.map((n) => <option key={n.id} value={n.id}>{n.code}</option>)}
              </select>
            </div>
            <div className="rei-filtre">
              <label className="cand-etiquette" htmlFor="rei-filtre-statut">Statut</label>
              <select
                id="rei-filtre-statut" className="cand-filter-select" value={statut}
                onChange={(e) => allerPage1(setStatut)(e.target.value)}>
                {STATUTS.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
              </select>
            </div>
            <div className="rei-filtre rei-filtre--large">
              <label className="cand-etiquette" htmlFor="rei-recherche">Rechercher un étudiant</label>
              <div className="cand-search rei-recherche">
                <i className="bi bi-search" aria-hidden="true"></i>
                <input
                  id="rei-recherche" type="search" className="cand-input"
                  placeholder="Matricule, nom…"
                  value={recherche}
                  onChange={(e) => allerPage1(setRecherche)(e.target.value)}
                />
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── Liste paginée des flux ── */}
      <section className="cand-panel" aria-labelledby="titre-flux">
        <header className="cand-panel-head">
          <h2 className="cand-panel-title" id="titre-flux">
            <i className="bi bi-table" aria-hidden="true"></i>Flux enregistrés
          </h2>
          <span className="cand-count-pill">{formatNombre(total)} élément{total > 1 ? 's' : ''}</span>
        </header>
        <div className="cand-table-wrap">
          <table className="cand-table rei-table">
            <thead>
              <tr>
                <th scope="col">Étudiant</th>
                <th scope="col">Type de flux</th>
                <th scope="col">Formation</th>
                <th scope="col">Niveau</th>
                <th scope="col">Année</th>
                <th scope="col">Statut</th>
                <th scope="col">Date d’inscription</th>
              </tr>
            </thead>
            <tbody>
              {chargement && resultats.length === 0 ? (
                <tr>
                  <td colSpan={7}>
                    <div className="cand-chargement">
                      <span className="spinner-border" role="status" aria-hidden="true"></span>
                      Chargement des flux…
                    </div>
                  </td>
                </tr>
              ) : resultats.length === 0 ? (
                <tr>
                  <td colSpan={7}>
                    <div className="cand-vide">
                      <span className="cand-vide-icone" aria-hidden="true">
                        <i className="bi bi-inbox"></i>
                      </span>
                      <p className="cand-vide-titre">Aucun flux enregistré.</p>
                      <p className="cand-vide-texte">
                        Aucune réinscription, transfert ou réorientation ne correspond
                        aux critères sélectionnés.
                      </p>
                    </div>
                  </td>
                </tr>
              ) : resultats.map((r) => (
                <tr key={r.id}>
                  <td>
                    <Link to={`/scolarite/etudiants/${r.etudiant_id}`} className="rei-etudiant">
                      <span className="rei-etudiant-nom">{r.etudiant}</span>
                      <span className="rei-etudiant-matricule">{r.matricule}</span>
                    </Link>
                  </td>
                  <td>
                    <span className={`rei-type is-${TON_TYPE[r.type_inscription] || 'blue'}`}>
                      {r.type_inscription_libelle || r.type_inscription}
                    </span>
                  </td>
                  <td><span className="rei-formation">{r.ref_formation}</span></td>
                  <td><span className="cand-badge-neutre">{r.niveau}</span></td>
                  <td><span className="rei-annee">{r.annee_academique}</span></td>
                  <td>
                    <span className={`rei-statut is-${TON_STATUT[r.statut] || 'slate'}`}>
                      {r.statut_libelle || r.statut}
                    </span>
                  </td>
                  <td><span className="rei-date">{formatDate(r.date_inscription)}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="rei-pagination">
          <span className="rei-pagination-infos">
            Page <strong>{page}</strong> sur <strong>{formatNombre(totalPages)}</strong>
            {' '}— {formatNombre(total)} flux au total
          </span>
          <div className="rei-pagination-actions">
            <label className="rei-page-size">
              Par page
              <select
                className="cand-filter-select" value={pageSize}
                onChange={(e) => { setPageSize(Number(e.target.value)); setPage(1) }}
                aria-label="Nombre d’éléments par page">
                {[10, 25, 50, 100].map((n) => <option key={n} value={n}>{n}</option>)}
              </select>
            </label>
            <button
              type="button" className="cand-btn-fantome" disabled={page <= 1 || chargement}
              onClick={() => setPage((p) => Math.max(1, p - 1))}>
              <i className="bi bi-chevron-left" aria-hidden="true"></i>Précédent
            </button>
            <button
              type="button" className="cand-btn-fantome" disabled={page >= totalPages || chargement}
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}>
              Suivant<i className="bi bi-chevron-right" aria-hidden="true"></i>
            </button>
          </div>
        </div>
        <p className="cand-defile" aria-hidden="true">
          <i className="bi bi-arrow-left-right"></i>
          Faites défiler le tableau horizontalement
        </p>
      </section>
    </div>
  )
}
