import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import api from '../../services/api'
import {
  createEvenement, getJournalAudit, getJournalEvenements, getJournalStats,
} from '../../services/scolarite'
import { canActScolarite } from '../../utils/roles'
import { useAuth } from '../../context/AuthContext'
import { useToast } from '../../context/ToastContext'
import { useDebounce } from '../../hooks/useDebounce'
import '../../styles/candidatures.css'
import '../../styles/journal-scolarite.css'

/** Les 12 types d'événements de parcours (miroir du modèle), avec habillage. */
const TYPES = [
  { value: 'PASSAGE', label: 'Passage en année supérieure', icone: 'bi-arrow-up-circle', ton: 'green' },
  { value: 'REDOUBLEMENT', label: 'Redoublement', icone: 'bi-arrow-counterclockwise', ton: 'amber' },
  { value: 'TRANSFERT', label: 'Transfert', icone: 'bi-arrow-left-right', ton: 'indigo' },
  { value: 'REORIENTATION', label: 'Changement de parcours', icone: 'bi-signpost-split', ton: 'indigo' },
  { value: 'CHANGEMENT_FORMATION', label: 'Changement de formation', icone: 'bi-diagram-3', ton: 'blue' },
  { value: 'CHANGEMENT_GROUPE', label: 'Changement de groupe', icone: 'bi-people', ton: 'slate' },
  { value: 'REPRISE', label: 'Reprise après suspension', icone: 'bi-play-circle', ton: 'blue' },
  { value: 'SUSPENSION', label: 'Suspension', icone: 'bi-pause-circle', ton: 'red' },
  { value: 'RADIATION', label: 'Radiation', icone: 'bi-x-octagon', ton: 'red' },
  { value: 'ABANDON', label: 'Abandon', icone: 'bi-box-arrow-right', ton: 'slate' },
  { value: 'EQUIVALENCE_DISPENSE', label: 'Équivalence ou dispense', icone: 'bi-award', ton: 'cyan' },
  { value: 'DIPLOMATION', label: 'Obtention du diplôme', icone: 'bi-mortarboard', ton: 'green' },
]

const TYPE_PAR_CODE = Object.fromEntries(TYPES.map((t) => [t.value, t]))

const formatNombre = (n) => Number(n || 0).toLocaleString('fr-FR')

/** « 2026-09-25 » → « jeudi 25 septembre 2026 ». */
const formatJourLong = (iso) => {
  if (!iso) return 'Date inconnue'
  const date = new Date(`${iso}T00:00:00`)
  if (Number.isNaN(date.getTime())) return iso
  const texte = new Intl.DateTimeFormat('fr-FR', {
    weekday: 'long', day: 'numeric', month: 'long', year: 'numeric',
  }).format(date)
  return texte.charAt(0).toUpperCase() + texte.slice(1)
}

/** Horodatage ISO complet → JJ/MM/AAAA HH:mm (heure réelle de l'audit). */
const formatHorodatage = (iso) => {
  if (!iso) return '—'
  const [datePart, heurePart = ''] = String(iso).split('T')
  const [annee, mois, jour] = datePart.split('-')
  if (!annee || !mois || !jour) return '—'
  const heure = heurePart.slice(0, 5)
  return `${jour}/${mois}/${annee}${heure ? ` ${heure}` : ''}`
}

const messageErreur = (err, repli) => {
  const data = err.response?.data
  if (!data) return repli
  if (typeof data.error === 'string') return data.error
  for (const valeur of Object.values(data)) {
    if (Array.isArray(valeur) && valeur.length) return valeur[0]
    if (typeof valeur === 'string') return valeur
  }
  return repli
}

export default function JournalScolarite() {
  const { user } = useAuth()
  const toast = useToast()
  const peutAgir = canActScolarite(user)

  const [onglet, setOnglet] = useState('parcours')
  const [stats, setStats] = useState(null)

  // ── Vue « Événements de parcours » ──
  const [evenements, setEvenements] = useState([])
  const [totalEv, setTotalEv] = useState(0)
  const [pagesEv, setPagesEv] = useState(1)
  const [pageEv, setPageEv] = useState(1)
  const [chargementEv, setChargementEv] = useState(true)
  const [typeFiltre, setTypeFiltre] = useState('')
  const [recherche, setRecherche] = useState('')
  const rechercheAttendue = useDebounce(recherche)
  const [dateDebut, setDateDebut] = useState('')
  const [dateFin, setDateFin] = useState('')

  // ── Vue « Traçabilité des opérations » ──
  const [audits, setAudits] = useState([])
  const [totalAu, setTotalAu] = useState(0)
  const [pagesAu, setPagesAu] = useState(1)
  const [pageAu, setPageAu] = useState(1)
  const [chargementAu, setChargementAu] = useState(false)
  const [auditCharge, setAuditCharge] = useState(false)
  const [actionFiltre, setActionFiltre] = useState('')
  const [objetFiltre, setObjetFiltre] = useState('')
  const [rechercheAu, setRechercheAu] = useState('')
  const rechercheAuAttendue = useDebounce(rechercheAu)

  // ── Formulaire « Enregistrer un événement » ──
  const [saisieEtudiant, setSaisieEtudiant] = useState('')
  const saisieAttendue = useDebounce(saisieEtudiant)
  const [propositions, setPropositions] = useState([])
  const [etudiantChoisi, setEtudiantChoisi] = useState(null)
  const [formEv, setFormEv] = useState({
    type_evenement: 'PASSAGE', ancienne_valeur: '', nouvelle_valeur: '', commentaire: '',
  })
  const [enCours, setEnCours] = useState(false)

  const chargerStats = useCallback(async () => {
    try {
      const res = await getJournalStats()
      const data = res.data
      if (data && !Array.isArray(data) && typeof data.total === 'number') setStats(data)
    } catch {
      setStats(null)
    }
  }, [])

  useEffect(() => { chargerStats() }, [chargerStats])

  const chargerEvenements = useCallback(async () => {
    setChargementEv(true)
    try {
      const params = { page: pageEv, page_size: 25 }
      if (typeFiltre) params.type_evenement = typeFiltre
      if (rechercheAttendue.trim()) params.search = rechercheAttendue.trim()
      if (dateDebut) params.date_debut = dateDebut
      if (dateFin) params.date_fin = dateFin
      const res = await getJournalEvenements(params)
      const data = res.data || {}
      setEvenements(Array.isArray(data.results) ? data.results : [])
      setTotalEv(typeof data.count === 'number' ? data.count : 0)
      setPagesEv(Math.max(1, typeof data.total_pages === 'number' ? data.total_pages : 1))
    } catch (err) {
      toast.showToast(messageErreur(err, 'Chargement des événements impossible.'), 'error')
    } finally {
      setChargementEv(false)
    }
  }, [pageEv, typeFiltre, rechercheAttendue, dateDebut, dateFin, toast])

  useEffect(() => { chargerEvenements() }, [chargerEvenements])

  const chargerAudit = useCallback(async () => {
    setChargementAu(true)
    try {
      const params = { page: pageAu, page_size: 25 }
      if (actionFiltre) params.action = actionFiltre
      if (objetFiltre) params.objet_type = objetFiltre
      if (rechercheAuAttendue.trim()) params.search = rechercheAuAttendue.trim()
      const res = await getJournalAudit(params)
      const data = res.data || {}
      setAudits(Array.isArray(data.results) ? data.results : [])
      setTotalAu(typeof data.count === 'number' ? data.count : 0)
      setPagesAu(Math.max(1, typeof data.total_pages === 'number' ? data.total_pages : 1))
      setAuditCharge(true)
    } catch (err) {
      toast.showToast(messageErreur(err, 'Chargement de la traçabilité impossible.'), 'error')
    } finally {
      setChargementAu(false)
    }
  }, [pageAu, actionFiltre, objetFiltre, rechercheAuAttendue, toast])

  useEffect(() => {
    if (onglet === 'audit') chargerAudit()
  }, [onglet, chargerAudit])

  // Regroupement chronologique de la page (tri serveur : date décroissante).
  const groupes = useMemo(() => {
    const parJour = []
    const index = new Map()
    for (const ev of evenements) {
      const jour = ev.date_evenement || ''
      if (!index.has(jour)) {
        index.set(jour, { jour, items: [] })
        parJour.push(index.get(jour))
      }
      index.get(jour).items.push(ev)
    }
    return parJour
  }, [evenements])

  // Recherche d'étudiant pour le formulaire.
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

  const soumettreEvenement = async (e) => {
    e.preventDefault()
    if (!etudiantChoisi) {
      toast.showToast('Choisissez d’abord l’étudiant concerné.', 'error')
      return
    }
    setEnCours(true)
    try {
      await createEvenement(etudiantChoisi.id, {
        type_evenement: formEv.type_evenement,
        ancienne_valeur: formEv.ancienne_valeur,
        nouvelle_valeur: formEv.nouvelle_valeur,
        commentaire: formEv.commentaire,
      })
      toast.showToast(`Événement enregistré pour ${etudiantChoisi.nom_complet}.`)
      setEtudiantChoisi(null)
      setSaisieEtudiant('')
      setFormEv({ type_evenement: 'PASSAGE', ancienne_valeur: '', nouvelle_valeur: '', commentaire: '' })
      setPageEv(1)
      chargerEvenements()
      chargerStats()
    } catch (err) {
      toast.showToast(messageErreur(err, 'Enregistrement impossible.'), 'error')
    } finally {
      setEnCours(false)
    }
  }

  const compteType = (code) => (stats ? (stats.par_type?.[code] || 0) : null)
  const sensibles = stats
    ? (stats.par_type?.RADIATION || 0) + (stats.par_type?.SUSPENSION || 0) + (stats.par_type?.ABANDON || 0)
    : 0

  const pagination = (page, pages, total, setPage, chargement) => (
    <div className="jou-pagination">
      <span className="jou-pagination-infos">
        Page <strong>{page}</strong> sur <strong>{formatNombre(pages)}</strong>
        {' '}— {formatNombre(total)} entrée{total > 1 ? 's' : ''} au total
      </span>
      <div className="jou-pagination-actions">
        <button
          type="button" className="cand-btn-fantome" disabled={page <= 1 || chargement}
          onClick={() => setPage((p) => Math.max(1, p - 1))}>
          <i className="bi bi-chevron-left" aria-hidden="true"></i>Précédent
        </button>
        <button
          type="button" className="cand-btn-fantome" disabled={page >= pages || chargement}
          onClick={() => setPage((p) => Math.min(pages, p + 1))}>
          Suivant<i className="bi bi-chevron-right" aria-hidden="true"></i>
        </button>
      </div>
    </div>
  )

  return (
    <div className="cand-page jou-page">
      {/* ── Bandeau d'accueil ── */}
      <div className="cand-hero">
        <div className="cand-hero-identite">
          <span className="cand-hero-icone" aria-hidden="true">
            <i className="bi bi-journal-text"></i>
          </span>
          <div className="cand-hero-text">
            <span className="cand-hero-badge">Scolarité — Mémoire des parcours</span>
            <h1 className="cand-hero-title">Journal de scolarité</h1>
            <p className="cand-hero-sub">
              Chronologie des événements qui jalonnent la vie des dossiers étudiants
              (passages, redoublements, transferts, décisions…) et traçabilité des
              opérations enregistrées par les opérateurs.
            </p>
          </div>
        </div>
        <div className="cand-hero-actions">
          <span className="jou-pastille jou-pastille--primary">
            <i className="bi bi-diagram-3" aria-hidden="true"></i>
            {formatNombre(stats?.total)} événement{stats?.total > 1 ? 's' : ''}
          </span>
          <span className="jou-pastille jou-pastille--neutre">
            <i className="bi bi-people" aria-hidden="true"></i>
            {formatNombre(stats?.dossiers_concernes)} dossiers concernés
          </span>
          <span className="jou-pastille jou-pastille--neutre">
            <i className="bi bi-fingerprint" aria-hidden="true"></i>
            {formatNombre(stats?.audit_total)} opérations tracées
          </span>
        </div>
      </div>

      {/* ── Indicateurs ── */}
      <div className="cand-kpi-row">
        <div className="cand-kpi">
          <span className="cand-kpi-icon is-blue" aria-hidden="true"><i className="bi bi-journal-text"></i></span>
          <div className="cand-kpi-texte">
            <span className="cand-kpi-value">{stats ? formatNombre(stats.total) : '—'}</span>
            <span className="cand-kpi-label">Événements de parcours</span>
            <span className="jou-kpi-sub">
              {stats ? `dont ${formatNombre(stats.reconstitues)} reconstitués depuis les inscriptions` : 'Chargement…'}
            </span>
          </div>
        </div>
        <div className="cand-kpi">
          <span className="cand-kpi-icon is-green" aria-hidden="true"><i className="bi bi-arrow-up-circle"></i></span>
          <div className="cand-kpi-texte">
            <span className="cand-kpi-value">{stats ? formatNombre(stats.par_type?.PASSAGE) : '—'}</span>
            <span className="cand-kpi-label">Passages en année supérieure</span>
            <span className="jou-kpi-sub">Continuité normale des parcours</span>
          </div>
        </div>
        <div className="cand-kpi">
          <span className="cand-kpi-icon is-amber" aria-hidden="true"><i className="bi bi-arrow-counterclockwise"></i></span>
          <div className="cand-kpi-texte">
            <span className="cand-kpi-value">{stats ? formatNombre(stats.par_type?.REDOUBLEMENT) : '—'}</span>
            <span className="cand-kpi-label">Redoublements</span>
            <span className="jou-kpi-sub">Niveaux repris</span>
          </div>
        </div>
        <div className="cand-kpi">
          <span className="cand-kpi-icon is-slate" aria-hidden="true"><i className="bi bi-exclamation-octagon"></i></span>
          <div className="cand-kpi-texte">
            <span className="cand-kpi-value">{stats ? formatNombre(sensibles) : '—'}</span>
            <span className="cand-kpi-label">Événements sensibles</span>
            <span className="jou-kpi-sub">Radiations, suspensions, abandons</span>
          </div>
        </div>
      </div>

      {/* ── Onglets : les deux journaux, distingués ── */}
      <div className="jou-onglets" role="tablist" aria-label="Périmètre du journal">
        <button
          type="button" role="tab" aria-selected={onglet === 'parcours'}
          className={`jou-onglet${onglet === 'parcours' ? ' is-active' : ''}`}
          onClick={() => setOnglet('parcours')}>
          <i className="bi bi-diagram-3" aria-hidden="true"></i>
          Événements de parcours
          {stats && <span className="jou-onglet-nb">{formatNombre(stats.total)}</span>}
        </button>
        <button
          type="button" role="tab" aria-selected={onglet === 'audit'}
          className={`jou-onglet${onglet === 'audit' ? ' is-active' : ''}`}
          onClick={() => setOnglet('audit')}>
          <i className="bi bi-fingerprint" aria-hidden="true"></i>
          Traçabilité des opérations
          {stats && <span className="jou-onglet-nb">{formatNombre(stats.audit_total)}</span>}
        </button>
      </div>

      {onglet === 'parcours' ? (
        <>
          {/* ── Enregistrer un événement ── */}
          {peutAgir && (
            <section className="cand-panel" aria-labelledby="titre-ajout-evenement">
              <header className="cand-panel-head">
                <h2 className="cand-panel-title" id="titre-ajout-evenement">
                  <i className="bi bi-plus-circle" aria-hidden="true"></i>Enregistrer un événement
                </h2>
                <span className="cand-count-pill">Daté du jour</span>
              </header>
              <div className="cand-panel-body">
                <form className="cand-grille-form jou-form" onSubmit={soumettreEvenement}>
                  <div className="cand-champ jou-champ-recherche">
                    <label className="cand-etiquette" htmlFor="jou-recherche-etudiant">Étudiant *</label>
                    {etudiantChoisi ? (
                      <div className="jou-etudiant-choisi">
                        <span>
                          <strong>{etudiantChoisi.nom_complet}</strong>
                          <small>{etudiantChoisi.matricule}</small>
                        </span>
                        <button
                          type="button" className="jou-retirer" aria-label="Changer d’étudiant"
                          onClick={() => { setEtudiantChoisi(null); setSaisieEtudiant('') }}>
                          <i className="bi bi-x-lg" aria-hidden="true"></i>
                        </button>
                      </div>
                    ) : (
                      <>
                        <input
                          id="jou-recherche-etudiant" type="search" className="cand-saisie"
                          placeholder="Nom ou matricule…"
                          value={saisieEtudiant}
                          onChange={(e) => setSaisieEtudiant(e.target.value)}
                        />
                        {propositions.length > 0 && (
                          <div className="jou-propositions">
                            {propositions.map((e) => (
                              <button
                                type="button" key={e.id} className="jou-proposition"
                                onClick={() => { setEtudiantChoisi(e); setPropositions([]) }}>
                                <span className="jou-proposition-nom">{e.nom_complet}</span>
                                <span className="jou-proposition-matricule">{e.matricule}</span>
                              </button>
                            ))}
                          </div>
                        )}
                      </>
                    )}
                  </div>
                  <div className="cand-champ">
                    <label className="cand-etiquette" htmlFor="jou-type">Type d’événement *</label>
                    <select
                      id="jou-type" className="cand-saisie" required value={formEv.type_evenement}
                      onChange={(e) => setFormEv({ ...formEv, type_evenement: e.target.value })}>
                      {TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
                    </select>
                  </div>
                  <div className="cand-champ">
                    <label className="cand-etiquette" htmlFor="jou-ancienne">Ancienne valeur</label>
                    <input
                      id="jou-ancienne" type="text" className="cand-saisie" placeholder="Ex. : L1"
                      value={formEv.ancienne_valeur}
                      onChange={(e) => setFormEv({ ...formEv, ancienne_valeur: e.target.value })}
                    />
                  </div>
                  <div className="cand-champ">
                    <label className="cand-etiquette" htmlFor="jou-nouvelle">Nouvelle valeur</label>
                    <input
                      id="jou-nouvelle" type="text" className="cand-saisie" placeholder="Ex. : L2"
                      value={formEv.nouvelle_valeur}
                      onChange={(e) => setFormEv({ ...formEv, nouvelle_valeur: e.target.value })}
                    />
                  </div>
                  <div className="cand-champ jou-champ--large">
                    <label className="cand-etiquette" htmlFor="jou-commentaire">Commentaire</label>
                    <textarea
                      id="jou-commentaire" className="cand-saisie" rows={1}
                      placeholder="Motif, référence de décision…"
                      value={formEv.commentaire}
                      onChange={(e) => setFormEv({ ...formEv, commentaire: e.target.value })}
                    />
                  </div>
                  <div className="jou-form-pied">
                    <p className="jou-note">
                      <i className="bi bi-info-circle" aria-hidden="true"></i>
                      L’événement est rattaché au dossier, signé de votre compte et tracé
                      dans le journal des opérations (append-only).
                    </p>
                    <button type="submit" className="cand-btn-principal" disabled={enCours}>
                      <i className="bi bi-journal-plus" aria-hidden="true"></i>Enregistrer
                    </button>
                  </div>
                </form>
              </div>
            </section>
          )}

          {/* ── Filtres des événements ── */}
          <section className="cand-panel" aria-labelledby="titre-filtres-journal">
            <header className="cand-panel-head">
              <h2 className="cand-panel-title" id="titre-filtres-journal">
                <i className="bi bi-funnel" aria-hidden="true"></i>Filtres et recherche
              </h2>
              <span className="cand-count-pill">{formatNombre(totalEv)} événement{totalEv > 1 ? 's' : ''}</span>
            </header>
            <div className="cand-panel-body">
              <div className="jou-segments" role="group" aria-label="Filtrer par type d’événement">
                <button
                  type="button"
                  className={`jou-segment is-blue${typeFiltre === '' ? ' is-active' : ''}`}
                  aria-pressed={typeFiltre === ''}
                  onClick={() => { setTypeFiltre(''); setPageEv(1) }}>
                  <i className="bi bi-collection" aria-hidden="true"></i>
                  Tous les événements
                  {stats && <span className="jou-segment-nb">{formatNombre(stats.total)}</span>}
                </button>
                {TYPES.map((t) => (
                  <button
                    key={t.value}
                    type="button"
                    className={`jou-segment is-${t.ton}${typeFiltre === t.value ? ' is-active' : ''}${compteType(t.value) === 0 ? ' is-vide' : ''}`}
                    aria-pressed={typeFiltre === t.value}
                    onClick={() => { setTypeFiltre(t.value); setPageEv(1) }}>
                    <i className={`bi ${t.icone}`} aria-hidden="true"></i>
                    {t.label}
                    {compteType(t.value) !== null && (
                      <span className="jou-segment-nb">{formatNombre(compteType(t.value))}</span>
                    )}
                  </button>
                ))}
              </div>
              <div className="jou-filtres">
                <div className="jou-filtre jou-filtre--large">
                  <label className="cand-etiquette" htmlFor="jou-recherche">Rechercher un étudiant</label>
                  <div className="cand-search jou-recherche">
                    <i className="bi bi-search" aria-hidden="true"></i>
                    <input
                      id="jou-recherche" type="search" className="cand-input"
                      placeholder="Matricule, nom, commentaire…"
                      value={recherche}
                      onChange={(e) => { setRecherche(e.target.value); setPageEv(1) }}
                    />
                  </div>
                </div>
                <div className="jou-filtre">
                  <label className="cand-etiquette" htmlFor="jou-date-debut">Du</label>
                  <input
                    id="jou-date-debut" type="date" className="cand-saisie" value={dateDebut}
                    onChange={(e) => { setDateDebut(e.target.value); setPageEv(1) }}
                  />
                </div>
                <div className="jou-filtre">
                  <label className="cand-etiquette" htmlFor="jou-date-fin">Au</label>
                  <input
                    id="jou-date-fin" type="date" className="cand-saisie" value={dateFin}
                    onChange={(e) => { setDateFin(e.target.value); setPageEv(1) }}
                  />
                </div>
              </div>
            </div>
          </section>

          {/* ── Chronologie ── */}
          <section className="cand-panel" aria-labelledby="titre-chronologie">
            <header className="cand-panel-head">
              <h2 className="cand-panel-title" id="titre-chronologie">
                <i className="bi bi-clock-history" aria-hidden="true"></i>Chronologie des parcours
              </h2>
              <span className="cand-count-pill">{formatNombre(totalEv)} élément{totalEv > 1 ? 's' : ''}</span>
            </header>
            <div className="cand-panel-body">
              {chargementEv && evenements.length === 0 ? (
                <div className="cand-chargement">
                  <span className="spinner-border" role="status" aria-hidden="true"></span>
                  Chargement de la chronologie…
                </div>
              ) : groupes.length === 0 ? (
                <div className="cand-vide">
                  <span className="cand-vide-icone" aria-hidden="true">
                    <i className="bi bi-inbox"></i>
                  </span>
                  <p className="cand-vide-titre">Aucun événement enregistré.</p>
                  <p className="cand-vide-texte">
                    Aucun événement de parcours ne correspond aux critères sélectionnés.
                  </p>
                </div>
              ) : (
                <div className="jou-chronologie">
                  {groupes.map((groupe) => (
                    <div className="jou-jour" key={groupe.jour}>
                      <h3 className="jou-jour-titre">{formatJourLong(groupe.jour)}</h3>
                      <ul className="jou-fil">
                        {groupe.items.map((ev) => {
                          const type = TYPE_PAR_CODE[ev.type_evenement] || { icone: 'bi-dot', ton: 'slate' }
                          return (
                            <li className="jou-evenement" key={ev.id}>
                              <span className={`jou-icone is-${type.ton}`} aria-hidden="true">
                                <i className={`bi ${type.icone}`}></i>
                              </span>
                              <div className="jou-carte">
                                <div className="jou-carte-entete">
                                  <span className={`jou-type is-${type.ton}`}>{ev.type_libelle}</span>
                                  {ev.ancienne_valeur || ev.nouvelle_valeur ? (
                                    <span className="jou-transition">
                                      {ev.ancienne_valeur && <span className="jou-ancienne">{ev.ancienne_valeur}</span>}
                                      {ev.ancienne_valeur && ev.nouvelle_valeur && (
                                        <i className="bi bi-arrow-right" aria-hidden="true"></i>
                                      )}
                                      {ev.nouvelle_valeur && <strong>{ev.nouvelle_valeur}</strong>}
                                    </span>
                                  ) : null}
                                  {ev.reconstitue ? (
                                    <span className="jou-badge-reconstitue" title="Événement déduit d’une inscription validée">
                                      <i className="bi bi-arrow-counterclockwise" aria-hidden="true"></i>Reconstitué
                                    </span>
                                  ) : ev.enregistre_par ? (
                                    <span className="jou-auteur">par {ev.enregistre_par}</span>
                                  ) : null}
                                </div>
                                <div className="jou-carte-corps">
                                  <Link to={`/scolarite/etudiants/${ev.etudiant_id}`} className="jou-etudiant">
                                    {ev.etudiant}
                                    <span className="jou-matricule">{ev.matricule}</span>
                                  </Link>
                                  {(ev.formation || ev.niveau || ev.annee_academique) && (
                                    <span className="jou-contexte">
                                      {[ev.formation, ev.niveau, ev.annee_academique].filter(Boolean).join(' · ')}
                                    </span>
                                  )}
                                </div>
                                {ev.commentaire && !ev.reconstitue && (
                                  <p className="jou-commentaire">{ev.commentaire}</p>
                                )}
                              </div>
                            </li>
                          )
                        })}
                      </ul>
                    </div>
                  ))}
                </div>
              )}
              <p className="jou-note">
                <i className="bi bi-info-circle" aria-hidden="true"></i>
                Les événements <strong>« reconstitués »</strong> ont été déduits des
                inscriptions validées (les chargements initiaux ne journalisaient pas) ;
                les autres ont été saisis par un opérateur ou générés par un service métier.
              </p>
            </div>
            {pagination(pageEv, pagesEv, totalEv, setPageEv, chargementEv)}
          </section>
        </>
      ) : (
        <>
          {/* ── Filtres traçabilité ── */}
          <section className="cand-panel" aria-labelledby="titre-filtres-audit">
            <header className="cand-panel-head">
              <h2 className="cand-panel-title" id="titre-filtres-audit">
                <i className="bi bi-funnel" aria-hidden="true"></i>Filtres et recherche
              </h2>
              <span className="cand-count-pill">{formatNombre(totalAu)} opération{totalAu > 1 ? 's' : ''}</span>
            </header>
            <div className="cand-panel-body">
              <div className="jou-filtres">
                <div className="jou-filtre">
                  <label className="cand-etiquette" htmlFor="jou-filtre-action">Action</label>
                  <select
                    id="jou-filtre-action" className="cand-filter-select" value={actionFiltre}
                    onChange={(e) => { setActionFiltre(e.target.value); setPageAu(1) }}>
                    <option value="">Toutes les actions</option>
                    {(stats?.audit_par_action || []).map((a) => (
                      <option key={a.action} value={a.action}>
                        {a.libelle} ({formatNombre(a.total)})
                      </option>
                    ))}
                  </select>
                </div>
                <div className="jou-filtre">
                  <label className="cand-etiquette" htmlFor="jou-filtre-objet">Type d’objet</label>
                  <select
                    id="jou-filtre-objet" className="cand-filter-select" value={objetFiltre}
                    onChange={(e) => { setObjetFiltre(e.target.value); setPageAu(1) }}>
                    <option value="">Tous les objets</option>
                    {(stats?.audit_par_objet || []).map((o) => (
                      <option key={o.objet_type} value={o.objet_type}>
                        {o.objet_type} ({formatNombre(o.total)})
                      </option>
                    ))}
                  </select>
                </div>
                <div className="jou-filtre jou-filtre--large">
                  <label className="cand-etiquette" htmlFor="jou-recherche-audit">Rechercher</label>
                  <div className="cand-search jou-recherche">
                    <i className="bi bi-search" aria-hidden="true"></i>
                    <input
                      id="jou-recherche-audit" type="search" className="cand-input"
                      placeholder="Objet, auteur, commentaire…"
                      value={rechercheAu}
                      onChange={(e) => { setRechercheAu(e.target.value); setPageAu(1) }}
                    />
                  </div>
                </div>
              </div>
              <p className="jou-note">
                <i className="bi bi-shield-lock" aria-hidden="true"></i>
                Journal append-only des opérations sensibles (candidatures, pièces,
                inscriptions, jurys, EDT…) : lecture seule, aucune entrée ne peut être
                modifiée ni supprimée.
              </p>
            </div>
          </section>

          {/* ── Tableau de traçabilité ── */}
          <section className="cand-panel" aria-labelledby="titre-tracabilite">
            <header className="cand-panel-head">
              <h2 className="cand-panel-title" id="titre-tracabilite">
                <i className="bi bi-fingerprint" aria-hidden="true"></i>Opérations enregistrées
              </h2>
              <span className="cand-count-pill">{formatNombre(totalAu)} élément{totalAu > 1 ? 's' : ''}</span>
            </header>
            <div className="cand-table-wrap">
              <table className="cand-table jou-table">
                <thead>
                  <tr>
                    <th scope="col">Horodatage</th>
                    <th scope="col">Action</th>
                    <th scope="col">Objet concerné</th>
                    <th scope="col">Auteur</th>
                    <th scope="col">Changement</th>
                  </tr>
                </thead>
                <tbody>
                  {chargementAu && audits.length === 0 ? (
                    <tr>
                      <td colSpan={5}>
                        <div className="cand-chargement">
                          <span className="spinner-border" role="status" aria-hidden="true"></span>
                          Chargement de la traçabilité…
                        </div>
                      </td>
                    </tr>
                  ) : audits.length === 0 ? (
                    <tr>
                      <td colSpan={5}>
                        <div className="cand-vide">
                          <span className="cand-vide-icone" aria-hidden="true">
                            <i className="bi bi-inbox"></i>
                          </span>
                          <p className="cand-vide-titre">Aucune opération tracée.</p>
                          <p className="cand-vide-texte">
                            Aucune entrée ne correspond aux critères sélectionnés.
                          </p>
                        </div>
                      </td>
                    </tr>
                  ) : audits.map((a) => (
                    <tr key={a.id}>
                      <td><span className="jou-horodatage">{formatHorodatage(a.timestamp)}</span></td>
                      <td>
                        <span className="jou-action">{a.action_libelle}</span>
                        {a.commentaire && <span className="jou-commentaire-ligne">{a.commentaire}</span>}
                      </td>
                      <td>
                        <span className="jou-objet-type">{a.objet_type || '—'}</span>
                        <span className="jou-objet-libelle">{a.objet_libelle || (a.objet_id ? `#${a.objet_id}` : '')}</span>
                      </td>
                      <td><span className="jou-acteur">{a.acteur_label || a.acteur || 'Système'}</span></td>
                      <td>
                        {a.ancienne_valeur || a.nouvelle_valeur ? (
                          <span className="jou-transition">
                            {a.ancienne_valeur && <span className="jou-ancienne">{a.ancienne_valeur}</span>}
                            {a.ancienne_valeur && a.nouvelle_valeur && (
                              <i className="bi bi-arrow-right" aria-hidden="true"></i>
                            )}
                            {a.nouvelle_valeur && <strong>{a.nouvelle_valeur}</strong>}
                          </span>
                        ) : (
                          <span className="jou-vide-valeur">—</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {pagination(pageAu, pagesAu, totalAu, setPageAu, chargementAu)}
            <p className="cand-defile" aria-hidden="true">
              <i className="bi bi-arrow-left-right"></i>
              Faites défiler le tableau horizontalement
            </p>
          </section>
        </>
      )}
    </div>
  )
}
