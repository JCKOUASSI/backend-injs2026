import React, { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import api from '../../services/api'
import { canActScolarite } from '../../utils/roles'
import { useAuth } from '../../context/AuthContext'
import { useToast } from '../../context/ToastContext'

const LISTE_BADGE = {
  ADMISSIBLE: 'success',
  LISTE_ATTENTE: 'warning',
  NON_ADMIS: 'secondary',
}

export default function CampagneDetail() {
  const { id } = useParams()
  const { user } = useAuth()
  const toast = useToast()
  const peutAgir = canActScolarite(user)

  const [campagne, setCampagne] = useState(null)
  const [enCours, setEnCours] = useState(false)
  const [formEpreuve, setFormEpreuve] = useState({
    type: 'ECRIT', intitule: '', date: '', heure_debut: '08:00',
    duree_minutes: 60, salle_id: '', coefficient: 1,
  })
  const [salles, setSalles] = useState([])
  const [formNote, setFormNote] = useState({ epreuve_id: '', candidature_id: '', note: '' })
  const [candidatures, setCandidatures] = useState([])
  const [classement, setClassement] = useState([])

  const charger = useCallback(async () => {
    try {
      const [res, resCand, resClassement] = await Promise.all([
        api.get(`/admissions/campagnes/${id}/`),
        api.get('/admissions/candidatures/'),
        api.get(`/admissions/campagnes/${id}/classement/`),
      ])
      setCampagne(res.data)
      setCandidatures(resCand.data.filter((c) => c.campagne_id === Number(id)))
      setClassement(resClassement.data)
    } catch (err) {
      toast.showToast(err.response?.data?.error || 'Chargement impossible.', 'error')
    }
  }, [id, toast])

  useEffect(() => { charger() }, [charger])

  useEffect(() => {
    if (!peutAgir) return
    api.get('/scolarite/ref/salles/')
      .then((res) => setSalles(res.data))
      .catch(() => {})
  }, [peutAgir])

  if (!campagne) {
    return <div className="container-fluid py-4"><div className="spinner-border" /></div>
  }

  const action = async (url, confirmation) => {
    if (confirmation && !window.confirm(confirmation)) return
    setEnCours(true)
    try {
      const res = await api.post(url, {})
      toast.showToast(res.data?.detail || 'Opération effectuée.')
      charger()
    } catch (err) {
      toast.showToast(err.response?.data?.error || 'Action impossible.', 'error')
    } finally {
      setEnCours(false)
    }
  }

  const ajouterEpreuve = async (e) => {
    e.preventDefault()
    setEnCours(true)
    try {
      await api.post(`/admissions/campagnes/${id}/epreuves/`, {
        ...formEpreuve,
        salle_id: Number(formEpreuve.salle_id) || undefined,
        coefficient: Number(formEpreuve.coefficient) || 1,
      })
      toast.showToast('Épreuve ajoutée.')
      setFormEpreuve({ type: 'ECRIT', intitule: '', date: '', heure_debut: '08:00', duree_minutes: 60, salle_id: '', coefficient: 1 })
      charger()
    } catch (err) {
      toast.showToast(JSON.stringify(err.response?.data) || 'Ajout impossible.', 'error')
    } finally {
      setEnCours(false)
    }
  }

  const enregistrerNote = async (e) => {
    e.preventDefault()
    setEnCours(true)
    try {
      await api.post(`/admissions/epreuves/${formNote.epreuve_id}/notes/`, {
        candidature_id: Number(formNote.candidature_id),
        note: formNote.note,
      })
      toast.showToast('Note enregistrée.')
      setFormNote({ epreuve_id: '', candidature_id: '', note: '' })
      charger()
    } catch (err) {
      toast.showToast(err.response?.data?.error || 'Enregistrement impossible.', 'error')
    } finally {
      setEnCours(false)
    }
  }

  const campagneFermee = ['CLOTUREE', 'ANNULEE', 'ARCHIVEE'].includes(campagne.statut)

  return (
    <div className="container-fluid py-4">
      <div className="d-flex justify-content-between align-items-start mb-3 flex-wrap gap-2">
        <div>
          <h1 className="h4 mb-1">{campagne.libelle}</h1>
          <div className="text-muted">
            <span className={`badge text-bg-secondary me-2`}>{campagne.statut}</span>
            {campagne.nb_candidatures} candidature(s) · {campagne.nb_epreuves} épreuve(s)
            {campagne.quota_admissibles != null && <> · quota admissibles : {campagne.quota_admissibles}</>}
          </div>
        </div>
        <Link className="btn btn-outline-secondary btn-sm" to="/scolarite/campagnes">← Retour</Link>
      </div>

      {peutAgir && (
        <div className="card mb-3">
          <div className="card-body">
            <h2 className="h6 card-title">Épreuves de concours</h2>
            {campagne.epreuves.map((e) => (
              <div className="d-flex justify-content-between align-items-center border-bottom py-2" key={e.id}>
                <div>
                  <strong>{e.intitule}</strong> <span className="badge text-bg-light">{e.type}</span>
                  {' '}· {e.date} {e.heure_debut} ({e.duree_minutes} min) · coeff. {e.coefficient}
                  {' '}· {e.nb_convocations} convocation(s)
                  {e.verrouillee && <span className="badge text-bg-danger ms-1">verrouillée</span>}
                </div>
                <div className="btn-group btn-group-sm">
                  {!e.verrouillee && !campagneFermee && (
                    <>
                      <button className="btn btn-outline-primary" disabled={enCours}
                              onClick={() => action(`/admissions/epreuves/${e.id}/convocations/generer/`,
                                                    'Générer les convocations ?')}>Convocations</button>
                      <button className="btn btn-outline-dark" disabled={enCours}
                              onClick={() => action(`/admissions/epreuves/${e.id}/verrouiller/`,
                                                    'Verrouiller les résultats ? Irréversible.')}>Verrouiller</button>
                    </>
                  )}
                </div>
              </div>
            ))}
            {!campagneFermee && (
              <form className="row g-2 mt-2" onSubmit={ajouterEpreuve}>
                <div className="col-md-2">
                  <select className="form-select" value={formEpreuve.type}
                          onChange={(e) => setFormEpreuve({ ...formEpreuve, type: e.target.value })}>
                    <option value="ECRIT">Écrit</option><option value="ORAL">Oral</option>
                    <option value="PRATIQUE">Pratique</option><option value="PHYSIQUE">Physique</option>
                  </select>
                </div>
                <div className="col-md-3">
                  <input className="form-control" placeholder="Intitulé" required value={formEpreuve.intitule}
                         onChange={(e) => setFormEpreuve({ ...formEpreuve, intitule: e.target.value })} />
                </div>
                <div className="col-md-2">
                  <input type="date" className="form-control" required value={formEpreuve.date}
                         onChange={(e) => setFormEpreuve({ ...formEpreuve, date: e.target.value })} />
                </div>
                <div className="col-md-2">
                  <input type="time" className="form-control" required value={formEpreuve.heure_debut}
                         onChange={(e) => setFormEpreuve({ ...formEpreuve, heure_debut: e.target.value })} />
                </div>
                <div className="col-md-2">
                  <select className="form-select" value={formEpreuve.salle_id}
                          onChange={(e) => setFormEpreuve({ ...formEpreuve, salle_id: e.target.value })}>
                    <option value="">Salle…</option>
                    {salles.map((s) => <option key={s.id} value={s.id}>{s.nom} ({s.capacite || '?'} pl.)</option>)}
                  </select>
                </div>
                <div className="col-md-1">
                  <button className="btn btn-primary w-100" disabled={enCours}>+</button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}


      {peutAgir && !campagneFermee && (
        <div className="card mb-3">
          <div className="card-body">
            <h2 className="h6 card-title">Saisie des notes</h2>
            <form className="row g-2" onSubmit={enregistrerNote}>
              <div className="col-md-4">
                <select className="form-select" required value={formNote.epreuve_id}
                        onChange={(e) => setFormNote({ ...formNote, epreuve_id: e.target.value })}>
                  <option value="">Épreuve…</option>
                  {campagne.epreuves.filter((e) => !e.verrouillee).map((e) => (
                    <option key={e.id} value={e.id}>{e.intitule} ({e.date})</option>
                  ))}
                </select>
              </div>
              <div className="col-md-4">
                <select className="form-select" required value={formNote.candidature_id}
                        onChange={(e) => setFormNote({ ...formNote, candidature_id: e.target.value })}>
                  <option value="">Candidature…</option>
                  {candidatures.map((c) => <option key={c.id} value={c.id}>{c.numero} — {c.candidat}</option>)}
                </select>
              </div>
              <div className="col-md-2">
                <input type="number" step="0.25" min="0" max="20" className="form-control" required
                       placeholder="Note /20" value={formNote.note}
                       onChange={(e) => setFormNote({ ...formNote, note: e.target.value })} />
              </div>
              <div className="col-md-2">
                <button className="btn btn-primary w-100" disabled={enCours}>Enregistrer</button>
              </div>
            </form>
            <div className="mt-2">
              <button className="btn btn-sm btn-outline-primary me-2" disabled={enCours}
                      onClick={() => action(`/admissions/campagnes/${id}/classement/calculer/`)}>
                <i className="bi bi-calculator me-1"></i>Calculer le classement
              </button>
              <button className="btn btn-sm btn-outline-success" disabled={enCours}
                      onClick={() => action('/admissions/campagnes/' + id + '/classement/publier/',
                                            'Publier les listes d’admissibilité ? Plus de recalcul possible.')}>
                <i className="bi bi-megaphone me-1"></i>Publier les listes
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="card">
        <div className="card-header"><i className="bi bi-sort-numeric-down me-1"></i>Classement</div>
        <div className="table-responsive">
          <table className="table table-sm table-hover align-middle mb-0">
            <thead className="table-light">
              <tr><th>Rang</th><th>Candidature</th><th>Candidat</th><th>Score</th><th>Liste</th><th>Publié</th></tr>
            </thead>
            <tbody>
              {classement.length === 0 ? (
                <tr><td colSpan={6} className="text-muted small ps-2">
                  Aucun classement calculé pour le moment.
                </td></tr>
              ) : classement.map((c) => (
                <tr key={c.rang}>
                  <td>{c.rang}</td>
                  <td>{c.candidature}</td>
                  <td>{c.candidat}</td>
                  <td>{c.score_total}</td>
                  <td><span className={`badge text-bg-${LISTE_BADGE[c.liste] || 'secondary'}`}>{c.liste}</span></td>
                  <td>{c.publie ? <span className="badge text-bg-success">oui</span> : <span className="text-muted">non</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
