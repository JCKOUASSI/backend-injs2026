import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useToast } from '../../context/ToastContext'
import ConfirmModal from '../../components/ConfirmModal'
import StatutBadge from '../../components/scolarite/StatutBadge'
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

/** Formulaire de décision : référence, date limite d'inscription, catégorie et grade. */
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
    <div className="card mb-3 border-primary">
      <div className="card-header d-flex justify-content-between align-items-center">
        <div>
          <strong>{admission.candidat}</strong>
          <span className="ms-2 text-muted small">{admission.candidature_numero}</span>
          <span className="ms-2"><StatutBadge statut={admission.decision} libelle={admission.decision_libelle} /></span>
        </div>
        <button className="btn-close" onClick={onClose} aria-label="Fermer"></button>
      </div>
      <div className="card-body">
        {erreur && <div className="alert alert-danger" style={{ whiteSpace: 'pre-line' }}>{erreur}</div>}

        <h6>Profil administratif</h6>
        <div className="row g-3 align-items-end mb-4">
          <div className="col-md-4">
            <label className="form-label">Catégorie</label>
            <select
              className="form-select" value={profil.categorie_id}
              onChange={(e) => setProfil({ categorie_id: e.target.value, grade_id: '' })}
            >
              <option value="">—</option>
              {categories.map((c) => <option key={c.id} value={c.id}>{c.libelle}</option>)}
            </select>
          </div>
          <div className="col-md-4">
            <label className="form-label">Grade</label>
            <select
              className="form-select" value={profil.grade_id}
              onChange={(e) => setProfil({ ...profil, grade_id: e.target.value })}
            >
              <option value="">—</option>
              {gradesFiltres.map((g) => <option key={g.id} value={g.id}>{g.libelle}</option>)}
            </select>
          </div>
          <div className="col-md-4">
            <button className="btn btn-outline-secondary" disabled={envoi} onClick={enregistrerProfil}>
              Enregistrer le profil
            </button>
          </div>
        </div>

        <h6>Décision</h6>
        <div className="row g-3">
          <div className="col-md-3">
            <label className="form-label">Décision</label>
            <select
              className="form-select" value={form.decision}
              onChange={(e) => setForm({ ...form, decision: e.target.value })}
            >
              {DECISIONS.map(([valeur, libelle]) => (
                <option key={valeur} value={valeur}>{libelle}</option>
              ))}
            </select>
          </div>
          <div className="col-md-3">
            <label className="form-label">Référence</label>
            <input
              className="form-control" placeholder="DEC-2026-001"
              value={form.reference_decision}
              onChange={(e) => setForm({ ...form, reference_decision: e.target.value })}
            />
          </div>
          <div className="col-md-3">
            <label className="form-label">Date limite d’inscription</label>
            <input
              type="date" className="form-control" value={form.date_limite_inscription || ''}
              onChange={(e) => setForm({ ...form, date_limite_inscription: e.target.value })}
            />
          </div>
          <div className="col-md-3 d-flex align-items-end">
            <button className="btn btn-primary w-100" disabled={envoi} onClick={prononcer}>
              {envoi && <span className="spinner-border spinner-border-sm me-1"></span>}
              Prononcer
            </button>
          </div>
          <div className="col-12">
            <label className="form-label">Observations</label>
            <textarea
              className="form-control" rows={2} value={form.observations}
              onChange={(e) => setForm({ ...form, observations: e.target.value })}
            />
          </div>
        </div>
      </div>
    </div>
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
    <div className="camp-page">
      <div className="camp-hero">
        <div className="camp-hero-text">
          <h1 className="camp-hero-title"><i className="bi bi-patch-check"></i>Admissions</h1>
          <p className="camp-hero-sub">{annee ? `Année ${annee.libelle}` : 'Année courante non définie'} · Décisions prononcées puis inscription des admis.</p>
        </div>
        <div className="camp-hero-side">
          <span className="plaquette plaquette-primary"><i className="bi bi-mortarboard"></i>{annee?.libelle || 'Année en cours'}</span>
          <span className="plaquette plaquette-soft"><i className="bi bi-people"></i>{admissions.length} admission{admissions.length > 1 ? 's' : ''}</span>
        </div>
      </div>

      <div className="camp-kpi-row">
        <div className="camp-kpi">
          <div><span className="camp-kpi-label">Décisions</span><span className="camp-kpi-value">{kpis.total}</span></div>
          <span className="camp-kpi-icon is-blue"><i className="bi bi-clipboard-check"></i></span>
        </div>
        <div className="camp-kpi">
          <div><span className="camp-kpi-label">Admis</span><span className="camp-kpi-value">{kpis.admis}</span></div>
          <span className="camp-kpi-icon is-green"><i className="bi bi-award"></i></span>
        </div>
        <div className="camp-kpi">
          <div><span className="camp-kpi-label">En attente</span><span className="camp-kpi-value">{kpis.attente}</span></div>
          <span className="camp-kpi-icon is-amber"><i className="bi bi-hourglass-split"></i></span>
        </div>
        <div className="camp-kpi">
          <div><span className="camp-kpi-label">À inscrire</span><span className="camp-kpi-value">{kpis.aInscrire}</span></div>
          <span className="camp-kpi-icon is-slate"><i className="bi bi-person-plus"></i></span>
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

      <div className="camp-panel card">
        <div className="camp-panel-head">
          <h2 className="camp-panel-title"><i className="bi bi-list-check"></i>Décisions d&apos;admission</h2>
          <div className="camp-filters">
            <select
              className="form-select form-select-sm camp-filter-select" aria-label="Filtrer par décision"
              value={filtreDecision} onChange={(e) => setFiltreDecision(e.target.value)}
            >
              <option value="">Toutes les décisions</option>
              {DECISIONS.map(([valeur, libelle]) => (
                <option key={valeur} value={valeur}>{libelle}</option>
              ))}
            </select>
            <span className="camp-count-pill">{admissions.length} dossier{admissions.length > 1 ? 's' : ''}</span>
          </div>
        </div>
        <div className="camp-panel-body">
          {loading ? (
            <div className="text-center py-4"><div className="spinner-border"></div></div>
          ) : (
            <div className="table-responsive">
              <table className="table table-hover align-middle mb-0 camp-table">
                <thead className="table-light">
                  <tr>
                    <th>Candidat</th><th>Formation</th><th>Niveau</th><th>Décision</th>
                    <th>Référence</th><th>Limite</th><th className="text-end">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {admissions.map((a) => (
                    <tr key={a.id}>
                      <td>
                        <span className="camp-link">{a.candidat}</span>
                        <span className="camp-sub">{a.candidature_numero}</span>
                      </td>
                      <td>{a.ref_formation}</td>
                      <td>{a.niveau}</td>
                      <td>
                        <StatutBadge statut={a.decision} libelle={a.decision_libelle} />
                        {a.est_expiree && <span className="badge bg-danger ms-1">Expirée</span>}
                      </td>
                      <td>{a.reference_decision || <span className="text-muted">—</span>}</td>
                      <td className="text-nowrap">{a.date_limite_inscription || <span className="text-muted">—</span>}</td>
                      <td className="text-end">
                        <div className="btn-group btn-group-sm">
                          <button className="btn btn-outline-primary camp-action-btn" onClick={() => setSelection(a)}>
                            <i className="bi bi-gavel me-1"></i>Décision
                          </button>
                          <button
                            className="btn btn-outline-success camp-action-btn"
                            disabled={!a.permet_inscription}
                            title={a.permet_inscription ? 'Créer le dossier étudiant' : "L'admission ne permet pas l'inscription"}
                            onClick={() => inscrire(a)}
                          >
                            <i className="bi bi-person-plus me-1"></i>Inscrire
                          </button>
                          <button
                            className="btn btn-outline-danger camp-action-btn"
                            disabled={a.decision === 'ANNULEE'}
                            onClick={() => annuler(a)}
                          >
                            <i className="bi bi-x-circle me-1"></i>Annuler
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                  {admissions.length === 0 && (
                    <tr><td colSpan={7}>
                      <div className="camp-empty"><i className="bi bi-inbox"></i>Aucune admission pour ces critères. Les décisions prononcées apparaîtront ici.</div>
                    </td></tr>
                  )}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

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
