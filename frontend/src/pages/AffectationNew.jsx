import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import api from '../services/api'
import { useToast } from '../context/ToastContext'
import {
  formatHeure, libelleJour, libelleStatut, messageErreurApi, lireMutationAffectation,
} from '../utils/edts'

const NATURES = [
  ['COURS', 'Cours'], ['TD', 'Travaux dirigés'], ['TP', 'Travaux pratiques'],
  ['EVALUATION', 'Évaluation'], ['REMPLACEMENT', 'Remplacement'], ['AUTRE', 'Autre'],
]

export default function AffectationNew() {
  const navigate = useNavigate()
  const { edtId } = useParams()
  const [searchParams] = useSearchParams()
  const { showToast } = useToast()
  const [submitting, setSubmitting] = useState(false)
  const [edt, setEdt] = useState(null)
  const [creneaux, setCreneaux] = useState([])
  const [groupes, setGroupes] = useState([])
  const [enseignants, setEnseignants] = useState([])
  const [salles, setSalles] = useState([])
  const [avertissements, setAvertissements] = useState([])
  const [form, setForm] = useState(() => ({
    creneau_template_id: searchParams.get('creneau') || '',
    semaine_debut: searchParams.get('semaine') || '1',
    semaine_fin: searchParams.get('semaine') || '1',
    nature: 'COURS',
    intitule: '',
    enseignant_id: '',
    groupe_id: '',
    salle_nom: '',
    commentaire: '',
  }))

  const enseignantChoisi = useMemo(
    () => enseignants.find((u) => String(u.id) === String(form.enseignant_id)) || null,
    [enseignants, form.enseignant_id],
  )

  useEffect(() => {
    (async () => {
      const [edtRes, creneauxRes, groupesRes, enseignantsRes, sallesRes] = await Promise.all([
        api.get(`/edts/emplois/${edtId}/`).catch(() => null),
        api.get('/edts/creneaux-types/').catch(() => null),
        api.get('/scolarite/ref/groupes/').catch(() => null),
        api.get('/edts/referentiel-enseignants/').catch(() => null),
        api.get('/formations/ref/salles/').catch(() => null),
      ])
      if (edtRes) {
        setEdt(edtRes.data)
        if (!searchParams.get('semaine')) {
          setForm((prev) => ({ ...prev, semaine_debut: String(edtRes.data.semaine_debut || 1),
                                                semaine_fin: String(edtRes.data.semaine_debut || 1) }))
        }
      }
      if (creneauxRes) setCreneaux(Array.isArray(creneauxRes.data) ? creneauxRes.data : [])
      if (groupesRes) setGroupes(Array.isArray(groupesRes.data) ? groupesRes.data : (groupesRes.data?.results ?? []))
      if (enseignantsRes) setEnseignants(Array.isArray(enseignantsRes.data) ? enseignantsRes.data : [])
      if (sallesRes) setSalles(Array.isArray(sallesRes.data) ? sallesRes.data : (sallesRes.data?.results ?? []))
    })()
    // eslint-disable-next-line react-hooks/exhaustive-deps -- initialisation unique au montage (edtId stable sur la route).
  }, [edtId])

  const handleChange = (e) => {
    const { name, value } = e.target
    setForm((prev) => ({ ...prev, [name]: value }))
  }

  const gel = edt && !['BROUILLON', 'EN_VALIDATION'].includes(edt.statut)

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!form.creneau_template_id) {
      showToast('Choisissez un créneau horaire', 'error')
      return
    }
    setSubmitting(true)
    setAvertissements([])
    try {
      const payload = {
        ...form,
        emploi_du_temps_id: parseInt(edtId, 10),
        enseignant_nom: enseignantChoisi ? enseignantChoisi.nom_complet : '',
      }
      const res = await api.post('/edts/affectations/', payload)
      const { avertissements: warns } = lireMutationAffectation(res)
      if (warns.length) {
        setAvertissements(warns)
        showToast('Créneau posé, mais des conflits ont été détectés — révisez la fiche.', 'info')
      } else {
        showToast('Affectation créée')
        navigate(`/edt?selection=${edtId}`)
      }
    } catch (err) {
      const data = err?.response?.data
      if (data?.conflits) {
        setAvertissements(data.conflits)
        showToast(messageErreurApi(err, 'Placement refusé'), 'error')
      } else {
        showToast(messageErreurApi(err, 'Création refusée'), 'error')
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="container-fluid">
      <div className="row justify-content-center">
        <div className="col-lg-9">
          <div className="card">
            <div className="card-header d-flex justify-content-between align-items-center">
              <h5 className="mb-0">
                <i className="bi bi-calendar-plus me-2"></i>Nouveau créneau
                {edt && <small className="text-muted ms-2">→ {edt.titre || edt.population_label}</small>}
              </h5>
              <Link to={`/edt?selection=${edtId}`} className="btn btn-outline-secondary btn-sm">
                <i className="bi bi-arrow-left"></i> Retour à l’EDT
              </Link>
            </div>
            {gel && (
              <div className="alert alert-warning mb-0 py-2 small">
                <i className="bi bi-lock me-1"></i>
                Cet emploi du temps est {libelleStatut(edt.statut)} : les placements sont verrouillés
                tant que la Direction ne l’a pas dépublié.
              </div>
            )}
            <form onSubmit={handleSubmit}>
              <div className="card-body">
                <div className="row g-3">
                  <div className="col-md-8">
                    <label className="form-label">Créneau horaire <span className="text-danger">*</span></label>
                    <select className="form-select" name="creneau_template_id"
                            value={form.creneau_template_id} onChange={handleChange} required>
                      <option value="">Sélectionnez un créneau…</option>
                      {creneaux.map((c) => (
                        <option key={c.id} value={c.id}>
                          {libelleJour(c.jour)} {formatHeure(c.heure_debut)}–{formatHeure(c.heure_fin)}
                        </option>
                      ))}
                    </select>
                    <div className="form-text">
                      {creneaux.length ? `${creneaux.length} créneaux au référentiel` :
                        'Référentiel de créneaux vide — voyez « Créneaux EDT » ou l’admin Django.'}
                    </div>
                  </div>
                  <div className="col-md-4">
                    <label className="form-label">Nature</label>
                    <select className="form-select" name="nature" value={form.nature} onChange={handleChange}>
                      {NATURES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                    </select>
                  </div>
                  <div className="col-md-3">
                    <label className="form-label">Semaine début <span className="text-danger">*</span></label>
                    <input type="number" className="form-control" name="semaine_debut" value={form.semaine_debut}
                           onChange={handleChange} min={edt?.semaine_debut || 1} max={edt?.semaine_fin || 60} required />
                  </div>
                  <div className="col-md-3">
                    <label className="form-label">Semaine fin <span className="text-danger">*</span></label>
                    <input type="number" className="form-control" name="semaine_fin" value={form.semaine_fin}
                           onChange={handleChange} min={edt?.semaine_debut || 1} max={edt?.semaine_fin || 60} required />
                    {edt && Number(form.semaine_fin) > (edt.semaine_fin || 60) && (
                      <div className="text-danger small mt-1">Hors période de l’EDT (fin : s{edt.semaine_fin}).</div>
                    )}
                  </div>
                  <div className="col-md-6">
                    <label className="form-label">Intitulé</label>
                    <input className="form-control" name="intitule" value={form.intitule}
                           onChange={handleChange} placeholder="Ex : Algorithmique — CM1" />
                  </div>
                  <div className="col-md-6">
                    <label className="form-label">Enseignant / encadrant</label>
                    <select className="form-select" name="enseignant_id" value={form.enseignant_id} onChange={handleChange}>
                      <option value="">— aucun —</option>
                      {enseignants.map((u) => <option key={u.id} value={u.id}>{u.nom_complet}</option>)}
                    </select>
                    <div className="form-text">{enseignantChoisi ? `Rôle : ${enseignantChoisi.role}` : 'Le nom sera reporté automatiquement.'}</div>
                  </div>
                  <div className="col-md-6">
                    <label className="form-label">Groupe</label>
                    <select className="form-select" name="groupe_id" value={form.groupe_id} onChange={handleChange}>
                      <option value="">— aucun —</option>
                      {groupes.map((g) => (
                        <option key={g.id} value={g.id}>
                          {g.nom}{g.annee_academique_id && edt && String(g.annee_academique_id) !== String(edt.annee_academique_id) ? ' (hors année)' : ''}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="col-md-6">
                    <label className="form-label">Salle</label>
                    <input className="form-control" name="salle_nom" value={form.salle_nom} onChange={handleChange}
                           placeholder="Ex : A101" list="salles-referentiel" />
                    <datalist id="salles-referentiel">
                      {salles.map((s) => <option key={s.id} value={s.nom} />)}
                    </datalist>
                  </div>
                  <div className="col-12">
                    <label className="form-label">Commentaire</label>
                    <textarea className="form-control" name="commentaire" value={form.commentaire}
                              onChange={handleChange} rows="2" placeholder="Observations optionnelles (motif d’annulation, prérequis…)"></textarea>
                  </div>
                </div>

                {avertissements.length > 0 && (
                  <div className="alert alert-warning mt-3 mb-0">
                    <strong><i className="bi bi-exclamation-triangle me-1"></i>Conflits détectés :</strong>
                    <ul className="mb-0 mt-1">
                      {avertissements.map((a, i) => <li key={i} className="small">{a}</li>)}
                    </ul>
                  </div>
                )}
              </div>
              <div className="card-footer d-flex justify-content-between">
                <button type="button" className="btn btn-outline-secondary" onClick={() => navigate(`/edt?selection=${edtId}`)}>
                  Annuler
                </button>
                <button type="submit" className="btn btn-primary" disabled={submitting || gel}>
                  {submitting
                    ? <><span className="spinner-border spinner-border-sm me-2"></span>Création…</>
                    : <><i className="bi bi-check2-circle me-1"></i>Poser ce créneau</>}
                </button>
              </div>
            </form>
          </div>
        </div>
      </div>
    </div>
  )
}
