import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useToast } from '../../context/ToastContext'
import ConfirmModal from '../../components/ConfirmModal'
import StatutBadge from '../../components/scolarite/StatutBadge'
import ChampDate, {
  dateFrancaiseVersIso, erreurDateFrancaise, isoVersDateFrancaise,
} from '../../components/scolarite/ChampDate'
import '../../styles/candidatures.css'
import '../../styles/modale-premium.css'
import '../../styles/campagnes.css'
import '../../styles/admissions.css'
import {
  annulerAdmission,
  decisionAdmission,
  getAnneeCourante,
  getRefCategories,
  getRefFormations,
  getRefGrades,
  getRefScolarite,
  getStatsAdmissions,
  inscrireDepuisAdmission,
  listAdmissions,
  messageErreur,
  updateAdmission,
} from '../../services/scolarite'

const DECISIONS = [
  ['EN_ATTENTE', 'En attente'],
  ['ADMIS', 'Admis'],
  ['ADMIS_SOUS_RESERVE', 'Admis sous réserve'],
  ['REFUSEE', 'Refusée'],
  ['ANNULEE', 'Annulée'],
]

/** Réponses liste de l'API : tableau nu ou enveloppe paginée `{results}`. */
const enListe = (res) => (Array.isArray(res?.data) ? res.data : (res?.data?.results || []))

/** '2026-12-17T10:30:00Z' → '17/12/2026' (vide si absent). */
const formaterDateHeure = (iso) => {
  if (!iso) return ''
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleDateString('fr-FR')
}

/** Jours restants avant une date ISO (négatif si dépassée). */
const joursRestants = (iso) => {
  if (!iso) return null
  const cible = new Date(`${String(iso).slice(0, 10)}T00:00:00`)
  const aujourdhui = new Date()
  aujourdhui.setHours(0, 0, 0, 0)
  return Math.round((cible - aujourdhui) / 86400000)
}

const COULEURS_AVATAR = [
  'linear-gradient(135deg, #1D4ED8, #3B82F6)',
  'linear-gradient(135deg, #047857, #10B981)',
  'linear-gradient(135deg, #B45309, #F59E0B)',
  'linear-gradient(135deg, #6D28D9, #A78BFA)',
  'linear-gradient(135deg, #BE123C, #FB7185)',
  'linear-gradient(135deg, #0F766E, #2DD4BF)',
]

/** Avatar à initiales : couleur déterministe dérivée du nom du candidat. */
function AvatarCandidat({ nom }) {
  const morceaux = String(nom || '?').trim().split(/\s+/)
  const initiales = ((morceaux[0]?.[0] || '?') + (morceaux[1]?.[0] || '')).toUpperCase()
  const somme = [...String(nom || '')].reduce((s, c) => s + c.charCodeAt(0), 0)
  return (
    <span
      className="adm-avatar" aria-hidden="true"
      style={{ background: COULEURS_AVATAR[somme % COULEURS_AVATAR.length] }}
    >
      {initiales}
    </span>
  )
}

/**
 * Panneau de décision : profil administratif (catégorie / grade) puis décision
 * (référence, date limite, observations). La date limite se saisit en
 * JJ/MM/AAAA (champ partagé ChampDate), convertie en ISO pour l'API.
 */
function DecisionPanel({ admission, categories, grades, onClose, onChange }) {
  const { showToast } = useToast()
  const [form, setForm] = useState({
    decision: admission.decision === 'EN_ATTENTE' ? 'ADMIS' : admission.decision,
    reference_decision: admission.reference_decision || '',
    date_limite_inscription: isoVersDateFrancaise(admission.date_limite_inscription),
    observations: admission.observations || '',
  })
  const [profil, setProfil] = useState({
    categorie_id: admission.categorie_id || '',
    grade_id: admission.grade_id || '',
  })
  const [envoi, setEnvoi] = useState(false)
  const [erreur, setErreur] = useState('')

  const gradesFiltres = profil.categorie_id
    ? grades.filter((g) => String(g.categorie) === String(profil.categorie_id)
      || String(g.categorie_id) === String(profil.categorie_id))
    : grades

  const enregistrerProfil = async () => {
    setErreur('')
    setEnvoi(true)
    try {
      await updateAdmission(admission.id, profil)
      showToast('Catégorie et grade enregistrés')
      onChange()
    } catch (err) {
      setErreur(messageErreur(err, 'Enregistrement impossible'))
    } finally {
      setEnvoi(false)
    }
  }

  const prononcer = async () => {
    const erreurDate = erreurDateFrancaise(form.date_limite_inscription, 'La date limite')
    if (erreurDate) {
      setErreur(erreurDate)
      return
    }
    setErreur('')
    setEnvoi(true)
    try {
      await decisionAdmission(admission.id, {
        ...form,
        date_limite_inscription: dateFrancaiseVersIso(form.date_limite_inscription) || '',
      })
      showToast('Décision enregistrée')
      onChange()
      onClose()
    } catch (err) {
      setErreur(messageErreur(err, 'Décision refusée'))
    } finally {
      setEnvoi(false)
    }
  }

  return (
    <section className="cand-panel cand-dossier card" aria-labelledby="titre-decision-admission">
      <header className="cand-dossier-entete">
        <div>
          <span className="cand-dossier-numero">{admission.candidature_numero}</span>
          <span className="cand-dossier-nom" id="titre-decision-admission">{admission.candidat}</span>
          <span className="cand-dossier-sous">Décision d’admission</span>
        </div>
        <div className="camp-entete-fin">
          <StatutBadge statut={admission.decision} libelle={admission.decision_libelle} />
          <button type="button" className="mp-fermer" onClick={onClose} aria-label="Fermer">
            <i className="bi bi-x-lg" aria-hidden="true"></i>
          </button>
        </div>
      </header>

      <div className="cand-panel-body">
        {erreur && (
          <div className="cand-alerte" role="alert" style={{ whiteSpace: 'pre-line' }}>{erreur}</div>
        )}

        <h3 className="cand-section-titre">
          <i className="bi bi-person-vcard" aria-hidden="true"></i>Profil administratif
        </h3>
        <div className="cand-grille-form camp-grille-profil">
          <div className="cand-champ">
            <label className="cand-etiquette" htmlFor="adm-categorie">Catégorie</label>
            <select
              id="adm-categorie" className="cand-saisie" value={profil.categorie_id}
              onChange={(e) => setProfil({ categorie_id: e.target.value, grade_id: '' })}
            >
              <option value="">—</option>
              {categories.map((c) => <option key={c.id} value={c.id}>{c.libelle}</option>)}
            </select>
          </div>
          <div className="cand-champ">
            <label className="cand-etiquette" htmlFor="adm-grade">Grade</label>
            <select
              id="adm-grade" className="cand-saisie" value={profil.grade_id}
              onChange={(e) => setProfil({ ...profil, grade_id: e.target.value })}
            >
              <option value="">—</option>
              {gradesFiltres.map((g) => <option key={g.id} value={g.id}>{g.libelle}</option>)}
            </select>
          </div>
          <div className="cand-champ camp-champ--action">
            <button type="button" className="cand-btn-fantome" disabled={envoi} onClick={enregistrerProfil}>
              <i className="bi bi-save2" aria-hidden="true"></i>
              Enregistrer le profil
            </button>
          </div>
        </div>

        <h3 className="cand-section-titre">
          <i className="bi bi-check2-square" aria-hidden="true"></i>Décision
        </h3>
        <div className="cand-grille-form">
          <div className="cand-champ">
            <label className="cand-etiquette" htmlFor="adm-decision">Décision</label>
            <select
              id="adm-decision" className="cand-saisie" value={form.decision}
              onChange={(e) => setForm({ ...form, decision: e.target.value })}
            >
              {DECISIONS.map(([valeur, libelle]) => (
                <option key={valeur} value={valeur}>{libelle}</option>
              ))}
            </select>
          </div>
          <div className="cand-champ">
            <label className="cand-etiquette" htmlFor="adm-reference">Référence</label>
            <input
              id="adm-reference" className="cand-saisie" placeholder="DEC-2026-001"
              value={form.reference_decision}
              onChange={(e) => setForm({ ...form, reference_decision: e.target.value })}
            />
          </div>
          <div className="cand-champ">
            <label className="cand-etiquette" htmlFor="adm-limite">Date limite d’inscription</label>
            <ChampDate
              id="adm-limite"
              valeur={form.date_limite_inscription}
              onChange={(texte) => setForm({ ...form, date_limite_inscription: texte })}
              reculAnnees={0} futurInterdit={false}
              etiquetteCalendrier="Choisir la date limite d’inscription"
            />
          </div>
          <div className="cand-champ cand-champ--4">
            <label className="cand-etiquette" htmlFor="adm-observations">Observations</label>
            <textarea
              id="adm-observations" className="cand-saisie cand-zone-texte" rows={2}
              value={form.observations}
              onChange={(e) => setForm({ ...form, observations: e.target.value })}
            />
          </div>
        </div>

        <div className="cand-form-actions">
          <button type="button" className="cand-btn-principal" disabled={envoi} onClick={prononcer}>
            {envoi
              ? <span className="spinner-border" aria-hidden="true"></span>
              : <i className="bi bi-check2-circle" aria-hidden="true"></i>}
            Prononcer
          </button>
        </div>
      </div>
    </section>
  )
}

export default function Admissions() {
  const { showToast } = useToast()
  const navigate = useNavigate()
  const [admissions, setAdmissions] = useState([])
  const [stats, setStats] = useState(null)
  const [annee, setAnnee] = useState(null)
  const [annees, setAnnees] = useState([])
  const [formations, setFormations] = useState([])
  const [categories, setCategories] = useState([])
  const [grades, setGrades] = useState([])
  const [filtres, setFiltres] = useState({
    q: '', decision: '', anneeId: '', formationId: '',
  })
  const [anneeInitialisee, setAnneeInitialisee] = useState(false)
  const [selection, setSelection] = useState(null)
  const [confirmation, setConfirmation] = useState(null)
  const [loading, setLoading] = useState(true)

  const charger = useCallback(async () => {
    setLoading(true)
    try {
      const params = {}
      if (filtres.decision) params.decision = filtres.decision
      if (filtres.anneeId) params.annee_academique_id = filtres.anneeId
      if (filtres.formationId) params.ref_formation_id = filtres.formationId
      if (filtres.q.trim()) params.q = filtres.q.trim()
      const res = await listAdmissions(Object.keys(params).length ? params : undefined)
      setAdmissions(enListe(res))
    } catch (err) {
      showToast(messageErreur(err, 'Chargement des admissions impossible'), 'error')
    } finally {
      setLoading(false)
    }
  }, [filtres, showToast])

  // Les indicateurs portent sur l'année sélectionnée (endpoint stats) et ne
  // dépendent donc pas des autres filtres du tableau.
  const chargerStats = useCallback(async () => {
    try {
      const res = await getStatsAdmissions(
        filtres.anneeId ? { annee_academique_id: filtres.anneeId } : undefined)
      setStats(res.data)
    } catch {
      setStats(null)
    }
  }, [filtres.anneeId])

  useEffect(() => {
    (async () => {
      const [anneeCourante, anneesRes, formationsRes, categoriesRes, gradesRes] = await Promise.all([
        getAnneeCourante().catch(() => null),
        getRefScolarite('annees', { actif: true }).catch(() => ({ data: [] })),
        getRefFormations().catch(() => ({ data: [] })),
        getRefCategories().catch(() => ({ data: [] })),
        getRefGrades().catch(() => ({ data: [] })),
      ])
      setAnnee(anneeCourante)
      setAnnees(enListe(anneesRes))
      setFormations(enListe(formationsRes))
      setCategories(enListe(categoriesRes))
      setGrades(enListe(gradesRes))
      // Par défaut, la page se concentre sur l'année courante (comme
      // l'annonce le bandeau) ; « Toutes les années » reste un choix du filtre.
      setFiltres((f) => ({ ...f, anneeId: anneeCourante?.id ? String(anneeCourante.id) : '' }))
      setAnneeInitialisee(true)
    })()
  }, [])

  useEffect(() => {
    if (anneeInitialisee) charger()
  }, [anneeInitialisee, charger])

  useEffect(() => {
    if (anneeInitialisee) chargerStats()
  }, [anneeInitialisee, chargerStats])

  const rechargerTout = useCallback(() => {
    charger()
    chargerStats()
  }, [charger, chargerStats])

  const inscrire = (admission) => {
    setConfirmation({
      message: `Inscrire ${admission.candidat} ?`,
      detail: "Un matricule sera généré et le dossier étudiant créé. L'opération est enregistrée dans le journal de scolarité.",
      onConfirm: async () => {
        try {
          const res = await inscrireDepuisAdmission({
            admission_id: admission.id,
            valider: true,
          })
          showToast(`Inscription créée — matricule ${res.data.matricule}`)
          navigate(`/scolarite/etudiants/${res.data.etudiant_id}`)
        } catch (err) {
          showToast(messageErreur(err, 'Inscription impossible'), 'error')
        }
      },
    })
  }

  const annuler = (admission) => {
    setConfirmation({
      message: `Annuler l’admission de ${admission.candidat} ?`,
      detail: 'La candidature associée sera également annulée.',
      onConfirm: async () => {
        try {
          await annulerAdmission(admission.id, {})
          showToast('Admission annulée')
          rechargerTout()
        } catch (err) {
          showToast(messageErreur(err, 'Annulation impossible'), 'error')
        }
      },
    })
  }

  const kpis = useMemo(() => {
    if (stats) {
      const parDecision = stats.par_decision || {}
      return {
        total: stats.total || 0,
        admis: (parDecision.ADMIS || 0) + (parDecision.ADMIS_SOUS_RESERVE || 0),
        attente: parDecision.EN_ATTENTE || 0,
        aInscrire: stats.a_inscrire || 0,
        inscrits: stats.inscrits || 0,
      }
    }
    return {
      total: admissions.length,
      admis: admissions.filter((a) => ['ADMIS', 'ADMIS_SOUS_RESERVE'].includes(a.decision)).length,
      attente: admissions.filter((a) => a.decision === 'EN_ATTENTE').length,
      aInscrire: admissions.filter((a) => a.permet_inscription && !a.inscrit).length,
      inscrits: admissions.filter((a) => a.inscrit).length,
    }
  }, [stats, admissions])
  const tauxAdmis = kpis.total ? Math.round((kpis.admis / kpis.total) * 100) : 0

  const libelleAnnee = (annees.find((a) => String(a.id) === String(filtres.anneeId))?.libelle)
    || (filtres.anneeId ? annee?.libelle : null)

  return (
    <div className="cand-page">
      {/* ── Bandeau d'accueil, même matière que Candidatures / Campagnes ── */}
      <div className="cand-hero">
        <div className="cand-hero-identite">
          <span className="cand-hero-icone" aria-hidden="true">
            <i className="bi bi-patch-check"></i>
          </span>
          <div className="cand-hero-text">
            <span className="cand-hero-badge">Scolarité — Admissions</span>
            <h1 className="cand-hero-title">Admissions</h1>
            <p className="cand-hero-sub">
              {libelleAnnee ? `Année ${libelleAnnee}` : 'Toutes les années'}
              {' · '}Décisions prononcées puis inscription des admis
            </p>
            <span className="camp-cycle">
              {['Candidature', "Décision d'admission", 'Inscription'].map((etape, i) => (
                <React.Fragment key={etape}>
                  {i > 0 && <i className="bi bi-chevron-right" aria-hidden="true"></i>}
                  <span className="camp-cycle-etape">{etape}</span>
                </React.Fragment>
              ))}
            </span>
          </div>
        </div>
        <div className="camp-pastilles">
          <span className="cand-count-pill">
            <i className="bi bi-mortarboard" aria-hidden="true"></i>
            {libelleAnnee || 'Toutes les années'}
          </span>
          <span className="cand-count-pill">
            <i className="bi bi-people" aria-hidden="true"></i>
            {kpis.total} admission{kpis.total > 1 ? 's' : ''}
          </span>
        </div>
      </div>

      {/* ── Indicateurs (périmètre : année sélectionnée) ── */}
      <div className="cand-kpi-row adm-kpi-row">
        <div className="cand-kpi">
          <span className="cand-kpi-icon is-blue" aria-hidden="true"><i className="bi bi-clipboard-check"></i></span>
          <div className="cand-kpi-texte">
            <span className="cand-kpi-value">{kpis.total}</span>
            <span className="cand-kpi-label">Décisions</span>
            <span className="adm-kpi-sous">{libelleAnnee || 'toutes années'}</span>
          </div>
        </div>
        <div className="cand-kpi">
          <span className="cand-kpi-icon is-green" aria-hidden="true"><i className="bi bi-award"></i></span>
          <div className="cand-kpi-texte">
            <span className="cand-kpi-value">{kpis.admis}</span>
            <span className="cand-kpi-label">Admis</span>
            <span className="adm-kpi-sous">{tauxAdmis} % des décisions</span>
          </div>
        </div>
        <div className="cand-kpi">
          <span className="cand-kpi-icon is-amber" aria-hidden="true"><i className="bi bi-hourglass-split"></i></span>
          <div className="cand-kpi-texte">
            <span className="cand-kpi-value">{kpis.attente}</span>
            <span className="cand-kpi-label">En attente</span>
            <span className="adm-kpi-sous">à décider par la commission</span>
          </div>
        </div>
        <div className="cand-kpi">
          <span className="cand-kpi-icon is-slate" aria-hidden="true"><i className="bi bi-person-plus"></i></span>
          <div className="cand-kpi-texte">
            <span className="cand-kpi-value">{kpis.aInscrire}</span>
            <span className="cand-kpi-label">À inscrire</span>
            <span className="adm-kpi-sous">admis en attente d’inscription</span>
          </div>
        </div>
        <div className="cand-kpi">
          <span className="cand-kpi-icon is-green" aria-hidden="true"><i className="bi bi-mortarboard"></i></span>
          <div className="cand-kpi-texte">
            <span className="cand-kpi-value">{kpis.inscrits}</span>
            <span className="cand-kpi-label">Inscrits</span>
            <span className="adm-kpi-sous">dossiers étudiants créés</span>
          </div>
        </div>
      </div>

      {selection && (
        <DecisionPanel
          admission={selection}
          categories={categories}
          grades={grades}
          onClose={() => setSelection(null)}
          onChange={rechargerTout}
        />
      )}

      <section className="cand-panel" aria-labelledby="titre-decisions-admission">
        <header className="cand-panel-head">
          <h2 className="cand-panel-title" id="titre-decisions-admission">
            <i className="bi bi-list-check" aria-hidden="true"></i>Décisions d&apos;admission
          </h2>
          <span className="cand-count-pill">
            {admissions.length} dossier{admissions.length > 1 ? 's' : ''}
          </span>
        </header>

        <div className="cand-panel-body">
          <div className="cand-filters">
            <label className="adm-recherche">
              <i className="bi bi-search" aria-hidden="true"></i>
              <input
                type="search" value={filtres.q}
                onChange={(e) => setFiltres({ ...filtres, q: e.target.value })}
                placeholder="Rechercher (nom, N° dossier, référence)…"
                aria-label="Rechercher une admission"
              />
            </label>
            <select
              className="cand-filter-select" aria-label="Filtrer par année"
              value={filtres.anneeId}
              onChange={(e) => setFiltres({ ...filtres, anneeId: e.target.value })}
            >
              <option value="">Toutes les années</option>
              {annees.map((a) => <option key={a.id} value={a.id}>{a.libelle}</option>)}
            </select>
            <select
              className="cand-filter-select" aria-label="Filtrer par décision"
              value={filtres.decision}
              onChange={(e) => setFiltres({ ...filtres, decision: e.target.value })}
            >
              <option value="">Toutes les décisions</option>
              {DECISIONS.map(([valeur, libelle]) => (
                <option key={valeur} value={valeur}>{libelle}</option>
              ))}
            </select>
            <select
              className="cand-filter-select" aria-label="Filtrer par formation"
              value={filtres.formationId}
              onChange={(e) => setFiltres({ ...filtres, formationId: e.target.value })}
            >
              <option value="">Toutes les formations</option>
              {formations.map((f) => <option key={f.id} value={f.id}>{f.intitule}</option>)}
            </select>
          </div>

          {loading ? (
            <div className="cand-chargement">
              <span className="spinner-border" aria-hidden="true"></span>Chargement des admissions…
            </div>
          ) : (
            <>
              <div className="cand-table-wrap">
                <table className="cand-table cand-table--admissions">
                  <thead>
                    <tr>
                      <th scope="col">Candidat</th>
                      <th scope="col">Formation</th>
                      <th scope="col">Décision</th>
                      <th scope="col">Référence</th>
                      <th scope="col">Limite d’inscription</th>
                      <th scope="col">Inscription</th>
                      <th scope="col" className="cand-th-actions">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {admissions.map((a) => {
                      const jours = joursRestants(a.date_limite_inscription)
                      return (
                        <tr key={a.id}>
                          <td>
                            <div className="adm-candidat">
                              <AvatarCandidat nom={a.candidat} />
                              <span className="adm-candidat-noms">
                                <span className="cand-etudiant">{a.candidat}</span>
                                <span className="cand-numero camp-numero">{a.candidature_numero}</span>
                              </span>
                            </div>
                          </td>
                          <td className="cand-col-formation">
                            <span className="cand-texte-formation" title={a.ref_formation}>{a.ref_formation}</span>
                            <span className="adm-meta">
                              <span className="cand-badge-neutre">{a.niveau}</span>
                              {a.annee_academique}
                            </span>
                          </td>
                          <td>
                            <div className="camp-decision">
                              <StatutBadge statut={a.decision} libelle={a.decision_libelle} />
                              {a.est_expiree && !a.inscrit && <span className="cand-puce-alerte">Expirée</span>}
                            </div>
                            {a.date_decision && (
                              <span className="adm-meta">
                                {formaterDateHeure(a.date_decision)}
                                {a.decide_par ? ` · par ${a.decide_par}` : ''}
                              </span>
                            )}
                          </td>
                          <td>
                            {a.reference_decision
                              ? <span className="camp-reference">{a.reference_decision}</span>
                              : <span className="cand-texte-doux">—</span>}
                          </td>
                          <td className="cand-col-etroit">
                            {a.date_limite_inscription ? (
                              <span className="adm-limite">
                                <span>{isoVersDateFrancaise(a.date_limite_inscription)}</span>
                                {!a.inscrit && a.est_expiree && (
                                  <span className="adm-urgence adm-urgence--depassee">dépassée</span>)}
                                {!a.inscrit && !a.est_expiree && jours != null && jours <= 15 && (
                                  <span className="adm-urgence adm-urgence--proche">J-{jours}</span>)}
                              </span>
                            ) : <span className="cand-texte-doux">—</span>}
                          </td>
                          <td>
                            {a.inscrit ? (
                              <button
                                type="button" className="adm-inscrit"
                                onClick={() => navigate(`/scolarite/etudiants/${a.etudiant_id}`)}
                                title="Ouvrir la fiche étudiant"
                              >
                                <i className="bi bi-mortarboard" aria-hidden="true"></i>
                                {a.matricule}
                              </button>
                            ) : a.permet_inscription ? (
                              <span className="adm-a-inscrire">À inscrire</span>
                            ) : <span className="cand-texte-doux">—</span>}
                          </td>
                          <td className="cand-col-actions">
                            <div className="cand-actions adm-actions">
                              <button
                                type="button"
                                className="camp-action camp-action--info"
                                onClick={() => setSelection(a)}
                                aria-label="Décision"
                                title="Prononcer ou modifier la décision"
                              >
                                <i className="bi bi-clipboard-check" aria-hidden="true"></i>Décision
                              </button>
                              {!a.inscrit && (
                                <button
                                  type="button"
                                  className="camp-action camp-action--succes"
                                  disabled={!a.permet_inscription}
                                  title={a.permet_inscription ? 'Créer le dossier étudiant' : "L'admission ne permet pas l'inscription"}
                                  aria-label="Inscrire"
                                  onClick={() => inscrire(a)}
                                >
                                  <i className="bi bi-person-plus" aria-hidden="true"></i>Inscrire
                                </button>
                              )}
                              <button
                                type="button"
                                className="camp-action camp-action--danger"
                                disabled={a.decision === 'ANNULEE'}
                                title="Annuler l’admission"
                                aria-label="Annuler"
                                onClick={() => annuler(a)}
                              >
                                <i className="bi bi-x-circle" aria-hidden="true"></i>Annuler
                              </button>
                            </div>
                          </td>
                        </tr>
                      )
                    })}
                    {admissions.length === 0 && (
                      <tr>
                        <td colSpan={7}>
                          <div className="cand-vide">
                            <span className="cand-vide-icone" aria-hidden="true">
                              <i className="bi bi-patch-check"></i>
                            </span>
                            <p className="cand-vide-titre">Aucune admission</p>
                            <p className="cand-vide-texte">
                              Aucune admission pour ces critères. Les décisions prononcées apparaîtront ici.
                            </p>
                          </div>
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
              <p className="cand-defile" aria-hidden="true">
                <i className="bi bi-arrow-left-right"></i>
                Faites défiler le tableau horizontalement
              </p>
            </>
          )}
        </div>
      </section>

      {confirmation && (
        <ConfirmModal
          message={confirmation.message}
          detail={confirmation.detail}
          onConfirm={async () => { await confirmation.onConfirm(); setConfirmation(null) }}
          onCancel={() => setConfirmation(null)}
        />
      )}
    </div>
  )
}
