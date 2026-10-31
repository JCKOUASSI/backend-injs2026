import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useToast } from '../../context/ToastContext'
import ConfirmModal from '../../components/ConfirmModal'
import StatutBadge from '../../components/scolarite/StatutBadge'
import '../../styles/candidatures.css'
import '../../styles/modale-premium.css'
import '../../styles/campagnes.css'
import {
  annulerAdmission,
  decisionAdmission,
  getAnneeCourante,
  getRefCategories,
  getRefGrades,
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

/**
 * Panneau de décision : profil administratif (catégorie / grade) puis décision
 * (référence, date limite, observations).
 *
 * Le balisage reposait sur la grille Bootstrap (`row g-3`, `col-md-*`,
 * `form-select`, `btn-close`) absente du bundle : champs natifs empilés sans
 * gouttière et bouton de fermeture invisible. Il suit désormais le même
 * canevas que le panneau « Dossier » des Candidatures.
 */
function DecisionPanel({ admission, categories, grades, onClose, onChange }) {
  const { showToast } = useToast()
  const [form, setForm] = useState({
    decision: admission.decision === 'EN_ATTENTE' ? 'ADMIS' : admission.decision,
    reference_decision: admission.reference_decision || '',
    date_limite_inscription: admission.date_limite_inscription || '',
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
    setErreur('')
    setEnvoi(true)
    try {
      await decisionAdmission(admission.id, form)
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
            <input
              id="adm-limite" type="date" className="cand-saisie"
              value={form.date_limite_inscription || ''}
              onChange={(e) => setForm({ ...form, date_limite_inscription: e.target.value })}
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
  const [annee, setAnnee] = useState(null)
  const [categories, setCategories] = useState([])
  const [grades, setGrades] = useState([])
  const [filtreDecision, setFiltreDecision] = useState('')
  const [selection, setSelection] = useState(null)
  const [confirmation, setConfirmation] = useState(null)
  const [loading, setLoading] = useState(true)

  const charger = useCallback(async () => {
    setLoading(true)
    try {
      const res = await listAdmissions(filtreDecision ? { decision: filtreDecision } : undefined)
      setAdmissions(res.data)
    } catch (err) {
      showToast(messageErreur(err, 'Chargement des admissions impossible'), 'error')
    } finally {
      setLoading(false)
    }
  }, [filtreDecision, showToast])

  useEffect(() => {
    (async () => {
      const [anneeCourante, categoriesRes, gradesRes] = await Promise.all([
        getAnneeCourante().catch(() => null),
        getRefCategories().catch(() => ({ data: [] })),
        getRefGrades().catch(() => ({ data: [] })),
      ])
      setAnnee(anneeCourante)
      setCategories(categoriesRes.data || [])
      setGrades(gradesRes.data || [])
    })()
  }, [])

  useEffect(() => { charger() }, [charger])

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
          charger()
        } catch (err) {
          showToast(messageErreur(err, 'Annulation impossible'), 'error')
        }
      },
    })
  }

  const kpis = useMemo(() => ({
    total: admissions.length,
    admis: admissions.filter((a) => ['ADMIS', 'ADMIS_SOUS_RESERVE'].includes(a.decision)).length,
    attente: admissions.filter((a) => a.decision === 'EN_ATTENTE').length,
    aInscrire: admissions.filter((a) => a.permet_inscription).length,
  }), [admissions])

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
              {annee ? `Année ${annee.libelle}` : 'Année courante non définie'}
              {' · '}Décisions prononcées puis inscription des admis
            </p>
          </div>
        </div>
        <div className="camp-pastilles">
          <span className="cand-count-pill">
            <i className="bi bi-mortarboard" aria-hidden="true"></i>
            {annee?.libelle || 'Année en cours'}
          </span>
          <span className="cand-count-pill">
            <i className="bi bi-people" aria-hidden="true"></i>
            {admissions.length} admission{admissions.length > 1 ? 's' : ''}
          </span>
        </div>
      </div>

      {/* ── Indicateurs ── */}
      <div className="cand-kpi-row">
        <div className="cand-kpi">
          <span className="cand-kpi-icon is-blue" aria-hidden="true"><i className="bi bi-clipboard-check"></i></span>
          <div className="cand-kpi-texte">
            <span className="cand-kpi-value">{kpis.total}</span>
            <span className="cand-kpi-label">Décisions</span>
          </div>
        </div>
        <div className="cand-kpi">
          <span className="cand-kpi-icon is-green" aria-hidden="true"><i className="bi bi-award"></i></span>
          <div className="cand-kpi-texte">
            <span className="cand-kpi-value">{kpis.admis}</span>
            <span className="cand-kpi-label">Admis</span>
          </div>
        </div>
        <div className="cand-kpi">
          <span className="cand-kpi-icon is-amber" aria-hidden="true"><i className="bi bi-hourglass-split"></i></span>
          <div className="cand-kpi-texte">
            <span className="cand-kpi-value">{kpis.attente}</span>
            <span className="cand-kpi-label">En attente</span>
          </div>
        </div>
        <div className="cand-kpi">
          <span className="cand-kpi-icon is-slate" aria-hidden="true"><i className="bi bi-person-plus"></i></span>
          <div className="cand-kpi-texte">
            <span className="cand-kpi-value">{kpis.aInscrire}</span>
            <span className="cand-kpi-label">À inscrire</span>
          </div>
        </div>
      </div>

      {selection && (
        <DecisionPanel
          admission={selection}
          categories={categories}
          grades={grades}
          onClose={() => setSelection(null)}
          onChange={charger}
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
            <select
              className="cand-filter-select" aria-label="Filtrer par décision"
              value={filtreDecision} onChange={(e) => setFiltreDecision(e.target.value)}
            >
              <option value="">Toutes les décisions</option>
              {DECISIONS.map(([valeur, libelle]) => (
                <option key={valeur} value={valeur}>{libelle}</option>
              ))}
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
                      <th scope="col">Niveau</th>
                      <th scope="col">Décision</th>
                      <th scope="col">Référence</th>
                      <th scope="col">Limite</th>
                      <th scope="col" className="cand-th-actions">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {admissions.map((a) => (
                      <tr key={a.id}>
                        <td>
                          <span className="cand-etudiant">{a.candidat}</span>
                          <span className="cand-numero camp-numero">{a.candidature_numero}</span>
                        </td>
                        <td className="cand-col-formation">
                          <span className="cand-texte-formation" title={a.ref_formation}>{a.ref_formation}</span>
                        </td>
                        <td><span className="cand-badge-neutre">{a.niveau}</span></td>
                        <td>
                          <div className="camp-decision">
                            <StatutBadge statut={a.decision} libelle={a.decision_libelle} />
                            {a.est_expiree && <span className="cand-puce-alerte">Expirée</span>}
                          </div>
                        </td>
                        <td>
                          {a.reference_decision
                            ? <span className="camp-reference">{a.reference_decision}</span>
                            : <span className="cand-texte-doux">—</span>}
                        </td>
                        <td className="cand-col-etroit">
                          {a.date_limite_inscription || <span className="cand-texte-doux">—</span>}
                        </td>
                        <td className="cand-col-actions">
                          <div className="cand-actions">
                            <button
                              type="button"
                              className="cand-action cand-action--ouvrir"
                              onClick={() => setSelection(a)}
                              aria-label="Décision"
                              title="Prononcer ou modifier la décision"
                            >
                              <i className="bi bi-clipboard-check" aria-hidden="true"></i>
                            </button>
                            <button
                              type="button"
                              className="cand-action cand-action--succes"
                              disabled={!a.permet_inscription}
                              title={a.permet_inscription ? 'Créer le dossier étudiant' : "L'admission ne permet pas l'inscription"}
                              aria-label="Inscrire"
                              onClick={() => inscrire(a)}
                            >
                              <i className="bi bi-person-plus" aria-hidden="true"></i>
                            </button>
                            <button
                              type="button"
                              className="cand-action cand-action--danger"
                              disabled={a.decision === 'ANNULEE'}
                              title="Annuler l’admission"
                              aria-label="Annuler"
                              onClick={() => annuler(a)}
                            >
                              <i className="bi bi-x-circle" aria-hidden="true"></i>
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
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
