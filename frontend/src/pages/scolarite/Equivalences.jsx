import React, { useCallback, useEffect, useMemo, useState } from 'react'
import api from '../../services/api'
import { canActScolarite } from '../../utils/roles'
import { useAuth } from '../../context/AuthContext'
import { useToast } from '../../context/ToastContext'
import { useDebounce } from '../../hooks/useDebounce'
import '../../styles/candidatures.css'
import '../../styles/equivalences.css'

const BADGE_STATUT = {
  BROUILLON: 'secondary', SOUMISE: 'info', EN_INSTRUCTION: 'info',
  A_COMPLETER: 'warning', AVIS_PEDAGOGIQUE: 'primary', DECISION: 'primary',
  VALIDEE: 'success', REJETEE: 'danger', APPLIQUEE: 'dark',
}

const ICONE_STATUT = {
  BROUILLON: 'bi-pencil-square', SOUMISE: 'bi-send', EN_INSTRUCTION: 'bi-clipboard-check',
  A_COMPLETER: 'bi-folder2-open', AVIS_PEDAGOGIQUE: 'bi-mortarboard', DECISION: 'bi-check2-square',
  VALIDEE: 'bi-patch-check', REJETEE: 'bi-x-octagon', APPLIQUEE: 'bi-lightning-charge',
}

// Teinte du chip de décision : lecture immédiate du sens (visuel seul).
const BADGE_DECISION = { FAVORABLE: 'text-bg-success', DEFAVORABLE: 'text-bg-danger' }

// Étapes « vivantes » du cycle : la demande n'est pas encore tranchée.
const STATUTS_EN_COURS = ['SOUMISE', 'EN_INSTRUCTION', 'A_COMPLETER', 'AVIS_PEDAGOGIQUE', 'DECISION']
// Étapes abouties : décision rendue puis (éventuellement) appliquée.
const STATUTS_ABOUTIES = ['VALIDEE', 'APPLIQUEE']

/** Étapes du cycle d'instruction cliquables (filtrage local), rejet à part. */
const ETAPES = [
  { value: 'BROUILLON', label: 'Brouillon', ton: 'amber' },
  { value: 'SOUMISE', label: 'Soumise', ton: 'blue' },
  { value: 'EN_INSTRUCTION', label: 'Instruction', ton: 'cyan' },
  { value: 'A_COMPLETER', label: 'À compléter', ton: 'amber' },
  { value: 'AVIS_PEDAGOGIQUE', label: 'Avis pédagogique', ton: 'indigo' },
  { value: 'DECISION', label: 'Décision', ton: 'indigo' },
  { value: 'VALIDEE', label: 'Validée', ton: 'green' },
  { value: 'APPLIQUEE', label: 'Appliquée', ton: 'slate' },
  { value: 'REJETEE', label: 'Rejetée', ton: 'red' },
]

export default function Equivalences() {
  const { user } = useAuth()
  const toast = useToast()
  const peutAgir = canActScolarite(user)

  const [demandes, setDemandes] = useState([])
  const [chargement, setChargement] = useState(true)
  const [enCours, setEnCours] = useState(false)
  const [selection, setSelection] = useState(null)
  const [form, setForm] = useState({
    type_demande: 'DISPENSE', etudiant_id: '', annee_academique_id: '',
    ref_formation_id: '', niveau_id: '', etablissement_origine: '', diplome_origine: '',
    annee_obtention: '', ue_id: '', ecue_id: '',
  })
  const [formDecision, setFormDecision] = useState({
    decision: 'FAVORABLE', credits_reconnus: '', note_transferee: '',
    autorite_validation: 'Direction des études INJS', analyse_pedagogique: '',
  })
  const [options, setOptions] = useState({ annees: [], formations: [], niveaux: [], etudiants: [] })
  const [saisieEtudiant, setSaisieEtudiant] = useState('')
  const saisieEtudiantAttendue = useDebounce(saisieEtudiant)
  const [uesCibles, setUesCibles] = useState([])
  const [filtreStatut, setFiltreStatut] = useState('')
  const [filtreType, setFiltreType] = useState('')
  const [filtreFormation, setFiltreFormation] = useState('')
  const [recherche, setRecherche] = useState('')

  const charger = useCallback(async () => {
    setChargement(true)
    try {
      const res = await api.get('/equivalences/demandes/')
      setDemandes(res.data)
    } catch (err) {
      toast.showToast(err.response?.data?.error || 'Chargement impossible.', 'error')
    } finally {
      setChargement(false)
    }
  }, [toast])

  useEffect(() => { charger() }, [charger])

  useEffect(() => {
    if (!peutAgir) return
    Promise.all([
      api.get('/scolarite/ref/annees/', { params: { actif: 'true' } }),
      api.get('/scolarite/ref/formations/'),
      api.get('/scolarite/ref/niveaux/', { params: { actif: 'true' } }),
      api.get('/scolarite/etudiants/'),
    ])
      .then(([annees, formations, niveaux, etudiants]) => setOptions({
        annees: annees.data, formations: formations.data,
        niveaux: niveaux.data, etudiants: etudiants.data,
      }))
      .catch(() => toast.showToast('Chargement des référentiels impossible.', 'error'))
  }, [peutAgir, toast])

  // Le sélecteur d'étudiant ne reçoit que les 500 premiers dossiers :
  // la recherche interroge l'API (?q=) pour atteindre tous les étudiants.
  useEffect(() => {
    const terme = (saisieEtudiantAttendue || '').trim()
    if (!peutAgir || terme.length < 2) return
    let annule = false
    api.get('/scolarite/etudiants/', { params: { q: terme } })
      .then((res) => {
        if (!annule && Array.isArray(res.data)) {
          setOptions((prev) => ({ ...prev, etudiants: res.data }))
        }
      })
      .catch(() => {})
    return () => { annule = true }
  }, [saisieEtudiantAttendue, peutAgir])

  // Cibles UE/ECUE : maquette ACTIVE de la formation et du niveau choisis.
  useEffect(() => {
    if (!peutAgir || !form.ref_formation_id || !form.niveau_id) {
      setUesCibles([])
      return
    }
    let annule = false
    ;(async () => {
      try {
        const liste = await api.get('/scolarite/maquettes/', {
          params: {
            ref_formation_id: Number(form.ref_formation_id),
            niveau_id: Number(form.niveau_id),
            statut: 'ACTIVE',
          },
        })
        const premiere = Array.isArray(liste.data) ? liste.data[0] : null
        if (!premiere?.id) {
          if (!annule) setUesCibles([])
          return
        }
        const detail = await api.get(`/scolarite/maquettes/${premiere.id}/`)
        if (!annule) {
          setUesCibles(Array.isArray(detail.data?.unites_enseignement)
            ? detail.data.unites_enseignement : [])
        }
      } catch {
        if (!annule) setUesCibles([])
      }
    })()
    return () => { annule = true }
  }, [peutAgir, form.ref_formation_id, form.niveau_id])

  const ecuesCibles = useMemo(() => {
    const ue = uesCibles.find((u) => String(u.id) === String(form.ue_id))
    return ue?.ecues || []
  }, [uesCibles, form.ue_id])

  const creer = async (e) => {
    e.preventDefault()
    setEnCours(true)
    try {
      await api.post('/equivalences/demandes/', {
        ...form,
        annee_academique_id: Number(form.annee_academique_id) || undefined,
        ref_formation_id: Number(form.ref_formation_id) || undefined,
        niveau_id: Number(form.niveau_id) || undefined,
        etudiant_id: Number(form.etudiant_id) || undefined,
        ue_id: Number(form.ue_id) || undefined,
        ecue_id: Number(form.ecue_id) || undefined,
        annee_obtention: Number(form.annee_obtention) || undefined,
      })
      toast.showToast('Demande créée en brouillon.')
      charger()
    } catch (err) {
      toast.showToast(JSON.stringify(err.response?.data) || 'Création impossible.', 'error')
    } finally {
      setEnCours(false)
    }
  }

  const transition = async (demande, statut) => {
    setEnCours(true)
    try {
      await api.post(`/equivalences/demandes/${demande.id}/transition/`, { statut })
      toast.showToast(`Demande ${statut.toLowerCase()}.`)
      charger()
    } catch (err) {
      toast.showToast(err.response?.data?.error || 'Transition impossible.', 'error')
    } finally {
      setEnCours(false)
    }
  }

  const rejeter = async (demande) => {
    if (!window.confirm('Rejeter définitivement cette demande ?')) return
    transition(demande, 'REJETEE')
  }

  const decider = async (demande) => {
    setEnCours(true)
    try {
      await api.post(`/equivalences/demandes/${demande.id}/decision/`, {
        ...formDecision,
        credits_reconnus: formDecision.credits_reconnus || undefined,
        note_transferee: formDecision.note_transferee || undefined,
      })
      toast.showToast('Décision enregistrée.')
      setSelection(null)
      charger()
    } catch (err) {
      toast.showToast(err.response?.data?.error || 'Décision impossible.', 'error')
    } finally {
      setEnCours(false)
    }
  }

  const appliquer = async (demande) => {
    if (!window.confirm('Appliquer cette dispense/équivalence (effet académique) ?')) return
    setEnCours(true)
    try {
      await api.post(`/equivalences/demandes/${demande.id}/appliquer/`, {})
      toast.showToast('Dispense/équivalence appliquée.')
      charger()
    } catch (err) {
      toast.showToast(err.response?.data?.error || 'Application impossible.', 'error')
    } finally {
      setEnCours(false)
    }
  }

  // Indicateurs de pilotage : calcul d'affichage, aucun appel supplémentaire.
  // Les crédits ne comptent que sur les demandes abouties (validées/appliquées).
  const stats = useMemo(() => ({
    total: demandes.length,
    enCours: demandes.filter((d) => STATUTS_EN_COURS.includes(d.statut)).length,
    aCompleter: demandes.filter((d) => d.statut === 'A_COMPLETER').length,
    abouties: demandes.filter((d) => STATUTS_ABOUTIES.includes(d.statut)).length,
    appliquees: demandes.filter((d) => d.statut === 'APPLIQUEE').length,
    equivalences: demandes.filter((d) => d.type_demande === 'EQUIVALENCE').length,
    dispenses: demandes.filter((d) => d.type_demande === 'DISPENSE').length,
    credits: demandes
      .filter((d) => STATUTS_ABOUTIES.includes(d.statut))
      .reduce((somme, d) => somme + (Number(d.credits_reconnus) || 0), 0),
  }), [demandes])

  const parStatut = useMemo(() => {
    const compte = {}
    for (const d of demandes) compte[d.statut] = (compte[d.statut] || 0) + 1
    return compte
  }, [demandes])

  const pctAbouties = stats.total ? Math.round((stats.abouties / stats.total) * 100) : 0

  const formationsPresentes = useMemo(() => {
    const compte = new Map()
    for (const d of demandes) {
      if (d.ref_formation) compte.set(d.ref_formation, (compte.get(d.ref_formation) || 0) + 1)
    }
    return [...compte.entries()].sort((a, b) => a[0].localeCompare(b[0], 'fr'))
  }, [demandes])

  const demandesFiltrees = useMemo(() => {
    let liste = demandes
    if (filtreType) liste = liste.filter((d) => d.type_demande === filtreType)
    if (filtreStatut) liste = liste.filter((d) => d.statut === filtreStatut)
    if (filtreFormation) liste = liste.filter((d) => d.ref_formation === filtreFormation)
    if (recherche.trim()) {
      const q = recherche.toLowerCase()
      liste = liste.filter(
        (d) =>
          (d.matricule || '').toLowerCase().includes(q) ||
          (d.etudiant_nom || '').toLowerCase().includes(q) ||
          (d.ref_formation || '').toLowerCase().includes(q),
      )
    }
    return liste
  }, [demandes, filtreType, filtreStatut, filtreFormation, recherche])

  const filtresActifs = Boolean(filtreType || filtreStatut || filtreFormation || recherche.trim())
  const basculerStatut = (value) => setFiltreStatut((actuel) => (actuel === value ? '' : value))

  return (
    <div className="cand-page eq-page">
      {/* ── Bandeau d'accueil ── */}
      <div className="cand-hero">
        <div className="cand-hero-identite">
          <span className="cand-hero-icone" aria-hidden="true">
            <i className="bi bi-award"></i>
          </span>
          <div className="cand-hero-text">
            <span className="cand-hero-badge">Passerelles et continuité de parcours</span>
            <h1 className="cand-hero-title">Équivalences et dispenses</h1>
            <p className="cand-hero-sub">
              Reconnaissance des acquis antérieurs : instruction, avis pédagogique,
              décision motivée puis application au dossier de l&apos;étudiant.
            </p>
          </div>
        </div>
        <div className="eq-hero-pastilles">
          <span className="eq-pastille eq-pastille--primary">
            <i className="bi bi-collection" aria-hidden="true"></i>
            {demandes.length} demande{demandes.length > 1 ? 's' : ''}
          </span>
          <span className="eq-pastille eq-pastille--neutre">
            <i className="bi bi-award" aria-hidden="true"></i>
            {stats.credits} crédits reconnus
          </span>
          <span className="eq-pastille eq-pastille--neutre">
            <i className="bi bi-shield-check" aria-hidden="true"></i>
            Application sous confirmation
          </span>
        </div>
      </div>

      {/* ── Indicateurs du cycle de vie ── */}
      <div className="cand-kpi-row">
        <div className="cand-kpi">
          <span className="cand-kpi-icon is-blue" aria-hidden="true"><i className="bi bi-collection"></i></span>
          <div className="cand-kpi-texte">
            <span className="cand-kpi-value">{stats.total}</span>
            <span className="cand-kpi-label">Demandes</span>
            <span className="eq-kpi-sub">{stats.equivalences} équivalence{stats.equivalences > 1 ? 's' : ''} · {stats.dispenses} dispense{stats.dispenses > 1 ? 's' : ''}</span>
          </div>
        </div>
        <div className="cand-kpi">
          <span className="cand-kpi-icon is-amber" aria-hidden="true"><i className="bi bi-hourglass-split"></i></span>
          <div className="cand-kpi-texte">
            <span className="cand-kpi-value">{stats.enCours}</span>
            <span className="cand-kpi-label">En cours d&apos;instruction</span>
            <span className="eq-kpi-sub">
              {stats.aCompleter ? `dont ${stats.aCompleter} à compléter` : 'Aucun dossier à compléter'}
            </span>
          </div>
        </div>
        <div className="cand-kpi">
          <span className="cand-kpi-icon is-green" aria-hidden="true"><i className="bi bi-patch-check"></i></span>
          <div className="cand-kpi-texte">
            <span className="cand-kpi-value">{stats.abouties}</span>
            <span className="cand-kpi-label">Validées / appliquées</span>
            <span className="eq-kpi-sub">{stats.appliquees} déjà appliquée{stats.appliquees > 1 ? 's' : ''}</span>
          </div>
        </div>
        <div className="cand-kpi">
          <span className="cand-kpi-icon is-slate" aria-hidden="true"><i className="bi bi-award"></i></span>
          <div className="cand-kpi-texte">
            <span className="cand-kpi-value">{stats.credits}</span>
            <span className="cand-kpi-label">Crédits reconnus</span>
            <span className="eq-kpi-sub">Sur décisions abouties</span>
          </div>
        </div>
      </div>

      {/* ── Cycle d'instruction ── */}
      <section className="cand-panel" aria-labelledby="titre-cycle-equivalences">
        <header className="cand-panel-head">
          <h2 className="cand-panel-title" id="titre-cycle-equivalences">
            <i className="bi bi-diagram-2" aria-hidden="true"></i>Cycle d’instruction
          </h2>
          <span className="cand-count-pill">{pctAbouties} % abouties</span>
        </header>
        <div className="cand-panel-body">
          <div className="eq-cycle" role="group" aria-label="Filtrer par étape du cycle">
            {ETAPES.map((etape, rang) => (
              <React.Fragment key={etape.value}>
                {rang > 0 && (
                  <span className="eq-cycle-lien" aria-hidden="true">
                    <i className="bi bi-chevron-right"></i>
                  </span>
                )}
                <button
                  type="button"
                  className={
                    `eq-etape is-${etape.ton}` +
                    (filtreStatut === etape.value ? ' is-active' : '')
                  }
                  aria-pressed={filtreStatut === etape.value}
                  title={`Filtrer : ${etape.label}`}
                  onClick={() => basculerStatut(etape.value)}
                >
                  <i className={`bi ${ICONE_STATUT[etape.value]}`} aria-hidden="true"></i>
                  <span className="eq-etape-label">{etape.label}</span>
                  <span className="eq-etape-nb">{parStatut[etape.value] || 0}</span>
                </button>
              </React.Fragment>
            ))}
          </div>
          <div
            className="eq-progression"
            role="progressbar"
            aria-valuenow={pctAbouties}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label="Part des demandes abouties"
          >
            <span className="eq-progression-barre" style={{ width: `${pctAbouties}%` }}></span>
          </div>
          {stats.aCompleter > 0 && (
            <p className="eq-alerte">
              <i className="bi bi-folder2-open" aria-hidden="true"></i>
              {stats.aCompleter} demande{stats.aCompleter > 1 ? 's' : ''} en attente de
              pièces complémentaires : l’avis pédagogique exige un dossier complet.
            </p>
          )}
        </div>
      </section>

      {/* ── Création d'une demande ── */}
      {peutAgir && (
        <section className="cand-panel card eq-panneau" aria-labelledby="titre-nouvelle-demande">
          <header className="cand-panel-head">
            <h2 className="cand-panel-title" id="titre-nouvelle-demande">
              <i className="bi bi-plus-circle" aria-hidden="true"></i>
              Nouvelle demande
            </h2>
            <span className="cand-count-pill">Statut initial : brouillon</span>
          </header>
          <div className="cand-panel-body">
            <form className="cand-grille-form eq-form eq-form--creation" onSubmit={creer}>
              <div className="cand-champ">
                <label className="cand-etiquette" htmlFor="eq-type">Type de demande</label>
                <select
                  id="eq-type" className="cand-saisie" value={form.type_demande}
                  onChange={(e) => setForm({ ...form, type_demande: e.target.value })}>
                  <option value="DISPENSE">Dispense</option>
                  <option value="EQUIVALENCE">Équivalence</option>
                </select>
              </div>
              <div className="cand-champ">
                <label className="cand-etiquette" htmlFor="eq-recherche-etudiant">Rechercher un étudiant</label>
                <input
                  id="eq-recherche-etudiant" type="search" className="cand-saisie"
                  placeholder="Nom ou matricule…"
                  value={saisieEtudiant}
                  onChange={(e) => setSaisieEtudiant(e.target.value)}
                />
              </div>
              <div className="cand-champ">
                <label className="cand-etiquette" htmlFor="eq-etudiant">Étudiant *</label>
                <select
                  id="eq-etudiant" className="cand-saisie" required value={form.etudiant_id}
                  onChange={(e) => setForm({ ...form, etudiant_id: e.target.value })}>
                  <option value="">Étudiant…</option>
                  {options.etudiants.map((e) => (
                    <option key={e.id} value={e.id}>{e.matricule} — {e.nom_complet}</option>
                  ))}
                </select>
              </div>
              <div className="cand-champ">
                <label className="cand-etiquette" htmlFor="eq-annee">Année académique *</label>
                <select
                  id="eq-annee" className="cand-saisie" required value={form.annee_academique_id}
                  onChange={(e) => setForm({ ...form, annee_academique_id: e.target.value })}>
                  <option value="">Année…</option>
                  {options.annees.map((a) => <option key={a.id} value={a.id}>{a.libelle}</option>)}
                </select>
              </div>
              <div className="cand-champ">
                <label className="cand-etiquette" htmlFor="eq-formation">Formation *</label>
                <select
                  id="eq-formation" className="cand-saisie" required value={form.ref_formation_id}
                  onChange={(e) => setForm({ ...form, ref_formation_id: e.target.value, ue_id: '', ecue_id: '' })}>
                  <option value="">Formation…</option>
                  {options.formations.map((f) => <option key={f.id} value={f.id}>{f.intitule}</option>)}
                </select>
              </div>
              <div className="cand-champ">
                <label className="cand-etiquette" htmlFor="eq-niveau">Niveau *</label>
                <select
                  id="eq-niveau" className="cand-saisie" required value={form.niveau_id}
                  onChange={(e) => setForm({ ...form, niveau_id: e.target.value, ue_id: '', ecue_id: '' })}>
                  <option value="">Niveau…</option>
                  {options.niveaux.map((n) => <option key={n.id} value={n.id}>{n.code}</option>)}
                </select>
              </div>
              <div className="cand-champ">
                <label className="cand-etiquette" htmlFor="eq-ue">UE concernée (optionnel)</label>
                <select
                  id="eq-ue" className="cand-saisie" value={form.ue_id}
                  onChange={(e) => setForm({ ...form, ue_id: e.target.value, ecue_id: '' })}>
                  <option value="">UE concernée (optionnel)…</option>
                  {uesCibles.map((u) => (
                    <option key={u.id} value={u.id}>{u.code} — {u.intitule} ({u.credits} cr.)</option>
                  ))}
                </select>
              </div>
              <div className="cand-champ">
                <label className="cand-etiquette" htmlFor="eq-ecue">ECUE concernée (optionnel)</label>
                <select
                  id="eq-ecue" className="cand-saisie" value={form.ecue_id}
                  onChange={(e) => setForm({ ...form, ecue_id: e.target.value })}
                  disabled={!form.ue_id}>
                  <option value="">ECUE concernée (optionnel)…</option>
                  {ecuesCibles.map((ec) => (
                    <option key={ec.id} value={ec.id}>{ec.code} — {ec.intitule} ({ec.credits} cr.)</option>
                  ))}
                </select>
              </div>
              <div className="cand-champ">
                <label className="cand-etiquette" htmlFor="eq-etablissement">Établissement d’origine</label>
                <input
                  id="eq-etablissement" className="cand-saisie" placeholder="Établissement d’origine"
                  value={form.etablissement_origine}
                  onChange={(e) => setForm({ ...form, etablissement_origine: e.target.value })}
                />
              </div>
              <div className="cand-champ">
                <label className="cand-etiquette" htmlFor="eq-diplome">Diplôme d’origine</label>
                <input
                  id="eq-diplome" className="cand-saisie" placeholder="Diplôme d’origine"
                  value={form.diplome_origine}
                  onChange={(e) => setForm({ ...form, diplome_origine: e.target.value })}
                />
              </div>
              <div className="cand-champ">
                <label className="cand-etiquette" htmlFor="eq-obtention">Année d’obtention</label>
                <input
                  id="eq-obtention" type="number" min="1950" max="2100" className="cand-saisie"
                  placeholder="Année d’obtention"
                  value={form.annee_obtention}
                  onChange={(e) => setForm({ ...form, annee_obtention: e.target.value })}
                />
              </div>
              <div className="eq-form-pied">
                <p className="eq-hint">
                  <i className="bi bi-info-circle" aria-hidden="true"></i>
                  La demande est ouverte au statut brouillon puis instruite tout au long du
                  cycle : soumission, instruction, avis pédagogique, décision, application.
                  Sans UE/ECUE cible, la reconnaissance reste globale (crédits) et ne dispense
                  aucune inscription pédagogique.
                </p>
                <button
                  type="submit" className="eq-add-btn" aria-label="+"
                  title="Ajouter la demande" disabled={enCours}>
                  <i className="bi bi-plus-lg" aria-hidden="true"></i>
                  <span>Ouvrir la demande</span>
                </button>
              </div>
            </form>
          </div>
        </section>
      )}

      {/* ── Filtres et recherche ── */}
      <section className="cand-panel" aria-labelledby="titre-filtres-equivalences">
        <header className="cand-panel-head">
          <h2 className="cand-panel-title" id="titre-filtres-equivalences">
            <i className="bi bi-funnel" aria-hidden="true"></i>Filtres et recherche
          </h2>
          <span className="cand-count-pill">
            {demandesFiltrees.length} résultat{demandesFiltrees.length > 1 ? 's' : ''}
          </span>
        </header>
        <div className="cand-panel-body">
          <div className="eq-filtres">
            <div className="eq-segment" role="group" aria-label="Filtrer par type de demande">
              {[
                { value: '', label: 'Toutes' },
                { value: 'EQUIVALENCE', label: 'Équivalences' },
                { value: 'DISPENSE', label: 'Dispenses' },
              ].map((t) => (
                <button
                  key={t.value || 'toutes'}
                  type="button"
                  className={`eq-segment-btn${filtreType === t.value ? ' is-active' : ''}`}
                  aria-pressed={filtreType === t.value}
                  onClick={() => setFiltreType(t.value)}
                >
                  {t.label}
                </button>
              ))}
            </div>
            <div className="eq-filtre">
              <label className="cand-etiquette" htmlFor="eq-filtre-statut">Filtrer par statut</label>
              <select
                id="eq-filtre-statut" className="cand-filter-select" value={filtreStatut}
                onChange={(e) => setFiltreStatut(e.target.value)}>
                <option value="">Tous les statuts</option>
                {ETAPES.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
              </select>
            </div>
            <div className="eq-filtre">
              <label className="cand-etiquette" htmlFor="eq-filtre-formation">Filtrer par formation</label>
              <select
                id="eq-filtre-formation" className="cand-filter-select" value={filtreFormation}
                onChange={(e) => setFiltreFormation(e.target.value)}>
                <option value="">Toutes les formations</option>
                {formationsPresentes.map(([intitule, nb]) => (
                  <option key={intitule} value={intitule}>{intitule} ({nb})</option>
                ))}
              </select>
            </div>
            <div className="eq-filtre eq-filtre--large">
              <label className="cand-etiquette" htmlFor="eq-recherche">Rechercher un étudiant</label>
              <div className="cand-search eq-recherche">
                <i className="bi bi-search" aria-hidden="true"></i>
                <input
                  id="eq-recherche" type="search" className="cand-input"
                  placeholder="Matricule, nom, formation…"
                  value={recherche}
                  onChange={(e) => setRecherche(e.target.value)}
                />
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── Demandes : cycle de vie complet ── */}
      <section className="cand-panel" aria-labelledby="titre-demandes">
        <header className="cand-panel-head">
          <h2 className="cand-panel-title" id="titre-demandes">
            <i className="bi bi-table" aria-hidden="true"></i>
            Demandes
          </h2>
          <span className="cand-count-pill">
            {demandesFiltrees.length} demande{demandesFiltrees.length > 1 ? 's' : ''}
          </span>
        </header>

        <div className="cand-table-wrap">
          <table className="cand-table eq-table">
            <thead>
              <tr>
                <th scope="col">Type</th>
                <th scope="col">Étudiant</th>
                <th scope="col">Matricule</th>
                <th scope="col">Formation</th>
                <th scope="col">Niveau</th>
                <th scope="col">Cible / origine</th>
                <th scope="col">Pièces</th>
                <th scope="col">Décision</th>
                <th scope="col">Statut</th>
                <th scope="col">Crédits</th>
                {peutAgir && <th scope="col" className="cand-th-actions">Actions</th>}
              </tr>
            </thead>
            <tbody>
              {chargement ? (
                <tr>
                  <td colSpan={peutAgir ? 11 : 10}>
                    <div className="cand-chargement">
                      <span className="spinner-border" role="status" aria-hidden="true"></span>
                      Chargement des demandes…
                    </div>
                  </td>
                </tr>
              ) : demandesFiltrees.length === 0 ? (
                <tr>
                  <td colSpan={peutAgir ? 11 : 10}>
                    <div className="cand-vide">
                      <span className="cand-vide-icone" aria-hidden="true">
                        <i className="bi bi-inbox"></i>
                      </span>
                      <p className="cand-vide-titre">Aucune demande.</p>
                      <p className="cand-vide-texte">
                        {filtresActifs
                          ? 'Aucune demande ne correspond aux filtres sélectionnés.'
                          : (
                            <>
                              Ouvrez une première demande de dispense ou d&apos;équivalence :
                              elle suivra le cycle d&apos;instruction jusqu&apos;à l&apos;application.
                            </>
                          )}
                      </p>
                    </div>
                  </td>
                </tr>
              ) : demandesFiltrees.map((d) => {
                const estExemple = (d.motif || '').startsWith('[Exemple]')
                const ciblePrincipale = d.type_demande === 'DISPENSE'
                  ? (d.ecue_intitule || d.ue_intitule || '')
                  : (d.etablissement_origine || d.ue_intitule || '')
                const cibleSecondaire = d.type_demande === 'DISPENSE'
                  ? (d.ecue_code || d.ue_code || '')
                  : (d.diplome_origine || d.ue_code || '')
                return (
                  <tr key={d.id} className={`eq-ligne--${(d.statut || '').toLowerCase()}`}>
                    <td>
                      <span className="eq-type-ligne">
                        <span className={`eq-type eq-type--${d.type_demande === 'EQUIVALENCE' ? 'equivalence' : 'dispense'}`}>
                          <i
                            className={`bi ${d.type_demande === 'EQUIVALENCE' ? 'bi-arrow-left-right' : 'bi-slash-circle'}`}
                            aria-hidden="true"
                          ></i>
                          {d.type_demande}
                        </span>
                        {estExemple && <span className="eq-exemple">Exemple</span>}
                      </span>
                    </td>
                    <td>
                      {d.etudiant_nom
                        ? <span className="eq-etudiant">{d.etudiant_nom}</span>
                        : <span className="cand-texte-doux">—</span>}
                    </td>
                    <td><span className="eq-matricule">{d.matricule}</span></td>
                    <td>
                      <span className="eq-formation" title={d.ref_formation}>{d.ref_formation}</span>
                    </td>
                    <td>
                      {d.niveau
                        ? <span className="cand-badge-neutre">{d.niveau}</span>
                        : <span className="cand-texte-doux">—</span>}
                    </td>
                    <td>
                      {ciblePrincipale ? (
                        <span className="eq-cible">
                          <span className="eq-cible-principale" title={ciblePrincipale}>{ciblePrincipale}</span>
                          {cibleSecondaire && <span className="eq-cible-secondaire">{cibleSecondaire}</span>}
                        </span>
                      ) : (
                        <span className="cand-texte-doux">—</span>
                      )}
                    </td>
                    <td className="cand-col-etroit">
                      {d.nb_pieces === null || d.nb_pieces === undefined ? (
                        <span className="cand-texte-doux">—</span>
                      ) : (
                        <span className="eq-pieces">
                          <span className="eq-pieces-nb">{d.pieces_validees || 0}/{d.nb_pieces}</span>
                          <span className={`eq-completude${d.dossier_complet ? ' is-ok' : ' is-ko'}`}>
                            {d.dossier_complet ? 'Complet' : 'Incomplet'}
                          </span>
                        </span>
                      )}
                    </td>
                    <td>
                      {d.decision && d.decision !== 'EN_ATTENTE' ? (
                        <span className={`eq-decision ${BADGE_DECISION[d.decision] || 'text-bg-secondary'}`}>
                          {d.decision}
                        </span>
                      ) : (
                        <span className="cand-texte-doux">—</span>
                      )}
                    </td>
                    <td>
                      <span className={`eq-statut text-bg-${BADGE_STATUT[d.statut] || 'secondary'}`}>
                        <i className={`bi ${ICONE_STATUT[d.statut] || 'bi-question-circle'}`} aria-hidden="true"></i>
                        {d.statut}
                      </span>
                    </td>
                    <td className="cand-col-etroit">
                      {d.credits_reconnus === null || d.credits_reconnus === undefined ? (
                        <span className="cand-texte-doux">—</span>
                      ) : (
                        <>
                          <span className="eq-credits">{d.credits_reconnus}</span>
                          <span className="eq-unite"> cr.</span>
                        </>
                      )}
                    </td>
                    {peutAgir && (
                      <td className="cand-col-actions">
                        <div className="cand-actions eq-actions">
                          {d.statut === 'BROUILLON' && (
                            <button
                              type="button" className="eq-action eq-action--soumettre" disabled={enCours}
                              title="Soumettre la demande à l'instruction"
                              onClick={() => transition(d, 'SOUMISE')}>
                              <i className="bi bi-send" aria-hidden="true"></i>Soumettre
                            </button>
                          )}
                          {d.statut === 'SOUMISE' && (
                            <>
                              <button
                                type="button" className="eq-action eq-action--instruire" disabled={enCours}
                                title="Passer la demande en instruction"
                                onClick={() => transition(d, 'EN_INSTRUCTION')}>
                                <i className="bi bi-clipboard-check" aria-hidden="true"></i>Instruire
                              </button>
                              <button
                                type="button" className="eq-action eq-action--completer" disabled={enCours}
                                title="Demander des pièces complémentaires"
                                onClick={() => transition(d, 'A_COMPLETER')}>
                                <i className="bi bi-folder2-open" aria-hidden="true"></i>À compléter
                              </button>
                            </>
                          )}
                          {d.statut === 'EN_INSTRUCTION' && (
                            <>
                              <button
                                type="button" className="eq-action eq-action--avis" disabled={enCours}
                                title="Saisir l'avis pédagogique"
                                onClick={() => transition(d, 'AVIS_PEDAGOGIQUE')}>
                                <i className="bi bi-mortarboard" aria-hidden="true"></i>Avis pédagogique
                              </button>
                              <button
                                type="button" className="eq-action eq-action--completer" disabled={enCours}
                                title="Demander des pièces complémentaires"
                                onClick={() => transition(d, 'A_COMPLETER')}>
                                <i className="bi bi-folder2-open" aria-hidden="true"></i>À compléter
                              </button>
                              <button
                                type="button" className="eq-action eq-action--rejeter" disabled={enCours}
                                title="Rejeter la demande (dossier irrecevable)"
                                onClick={() => rejeter(d)}>
                                <i className="bi bi-x-octagon" aria-hidden="true"></i>Rejeter
                              </button>
                            </>
                          )}
                          {d.statut === 'A_COMPLETER' && (
                            <>
                              <button
                                type="button" className="eq-action eq-action--instruire" disabled={enCours}
                                title="Reprendre l'instruction (pièces complétées)"
                                onClick={() => transition(d, 'EN_INSTRUCTION')}>
                                <i className="bi bi-arrow-counterclockwise" aria-hidden="true"></i>Reprendre
                              </button>
                              <button
                                type="button" className="eq-action eq-action--rejeter" disabled={enCours}
                                title="Rejeter la demande"
                                onClick={() => rejeter(d)}>
                                <i className="bi bi-x-octagon" aria-hidden="true"></i>Rejeter
                              </button>
                            </>
                          )}
                          {(d.statut === 'AVIS_PEDAGOGIQUE' || d.statut === 'DECISION') && (
                            <button
                              type="button" className="eq-action eq-action--decider"
                              title="Rendre la décision pédagogique"
                              onClick={() => setSelection(d)}>
                              <i className="bi bi-check2-square" aria-hidden="true"></i>Décider
                            </button>
                          )}
                          {d.statut === 'VALIDEE' && (
                            <button
                              type="button" className="eq-action eq-action--appliquer" disabled={enCours}
                              title="Appliquer la dispense ou l'équivalence au dossier"
                              onClick={() => appliquer(d)}>
                              <i className="bi bi-lightning-charge" aria-hidden="true"></i>Appliquer
                            </button>
                          )}
                        </div>
                      </td>
                    )}
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
        <p className="cand-defile" aria-hidden="true">
          <i className="bi bi-arrow-left-right"></i>
          Faites défiler le tableau horizontalement
        </p>
      </section>

      {/* ── Décision pédagogique ── */}
      {selection && (
        <section className="cand-panel card eq-panneau eq-panneau--decision" aria-labelledby="titre-decision">
          <header className="cand-panel-head">
            <h2 className="cand-panel-title" id="titre-decision">
              <i className="bi bi-clipboard2-check" aria-hidden="true"></i>
              Décision — demande #{selection.id}
            </h2>
            <span className="cand-count-pill">{selection.ref_formation}</span>
          </header>
          <div className="cand-panel-body">
            <form className="cand-grille-form eq-form eq-form--decision" onSubmit={(e) => { e.preventDefault(); decider(selection) }}>
              <div className="cand-champ">
                <label className="cand-etiquette" htmlFor="eq-decision">Décision</label>
                <select
                  id="eq-decision" className="cand-saisie" value={formDecision.decision}
                  onChange={(e) => setFormDecision({ ...formDecision, decision: e.target.value })}>
                  <option value="FAVORABLE">Favorable</option>
                  <option value="DEFAVORABLE">Défavorable</option>
                </select>
              </div>
              <div className="cand-champ">
                <label className="cand-etiquette" htmlFor="eq-credits">Crédits reconnus</label>
                <input
                  id="eq-credits" type="number" min="0" className="cand-saisie" placeholder="Crédits reconnus"
                  value={formDecision.credits_reconnus}
                  onChange={(e) => setFormDecision({ ...formDecision, credits_reconnus: e.target.value })}
                />
              </div>
              <div className="cand-champ">
                <label className="cand-etiquette" htmlFor="eq-note">Note transférée</label>
                <input
                  id="eq-note" type="number" step="0.25" min="0" max="20" className="cand-saisie"
                  placeholder="Note transférée" value={formDecision.note_transferee}
                  onChange={(e) => setFormDecision({ ...formDecision, note_transferee: e.target.value })}
                />
              </div>
              <div className="cand-champ">
                <label className="cand-etiquette" htmlFor="eq-autorite">Autorité de validation</label>
                <input
                  id="eq-autorite" className="cand-saisie" placeholder="Autorité de validation"
                  value={formDecision.autorite_validation}
                  onChange={(e) => setFormDecision({ ...formDecision, autorite_validation: e.target.value })}
                />
              </div>
              <div className="cand-champ eq-champ-large">
                <label className="cand-etiquette" htmlFor="eq-analyse">Analyse pédagogique</label>
                <textarea
                  id="eq-analyse" className="cand-saisie" rows="3" placeholder="Analyse pédagogique"
                  value={formDecision.analyse_pedagogique}
                  onChange={(e) => setFormDecision({ ...formDecision, analyse_pedagogique: e.target.value })}
                />
              </div>
              <div className="eq-form-pied">
                <p className="eq-hint">
                  <i className="bi bi-info-circle" aria-hidden="true"></i>
                  La décision est horodatée et rattachée à la demande ; l&apos;application au dossier
                  reste soumise à confirmation.
                </p>
                <div className="eq-form-boutons">
                  <button
                    type="button" className="cand-btn-fantome" disabled={enCours}
                    onClick={() => setSelection(null)}>
                    Annuler
                  </button>
                  <button type="submit" className="cand-btn-principal" disabled={enCours}>
                    <i className="bi bi-check2-circle" aria-hidden="true"></i>Enregistrer
                  </button>
                </div>
              </div>
            </form>
          </div>
        </section>
      )}
    </div>
  )
}
