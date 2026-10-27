import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import api from '../services/api'
import { useToast } from '../context/ToastContext'
import { messageErreurApi, libelleStatut } from '../utils/edts'
import '../styles/edts.css'

const TYPES_POPULATION = [
  { valeur: 'FORMATION', libelle: 'Formation', endpoint: '/formations/ref/formations/', cleLabel: 'intitule' },
  { valeur: 'GROUPE', libelle: 'Groupe', endpoint: '/scolarite/ref/groupes/', cleLabel: 'nom' },
  { valeur: 'ENSEIGNANT', libelle: 'Enseignant / encadrant', endpoint: '/edts/referentiel-enseignants/', cleLabel: 'nom_complet' },
  { valeur: 'SALLE', libelle: 'Salle', endpoint: '/formations/ref/salles/', cleLabel: 'nom' },
]

export default function EdtNew() {
  const navigate = useNavigate()
  const { showToast } = useToast()
  const [loading, setLoading] = useState(false)
  const [annees, setAnnees] = useState([])
  const [populationItems, setPopulationItems] = useState([])
  const [form, setForm] = useState({
    titre: '',
    annee_academique_id: '',
    population_type: 'FORMATION',
    population_id: '',
    rentree: '',
    semaine_debut: '1',
    semaine_fin: '20',
  })

  useEffect(() => {
    (async () => {
      try {
        const [anneesRes, couranteRes] = await Promise.all([
          api.get('/scolarite/ref/annees/'),
          api.get('/scolarite/annee-courante/').catch(() => null),
        ])
        const liste = Array.isArray(anneesRes.data) ? anneesRes.data : (anneesRes.data?.results ?? [])
        setAnnees(liste)
        const courante = couranteRes?.data?.annee
        if (courante?.id) setForm((prev) => ({ ...prev, annee_academique_id: String(courante.id) }))
      } catch (err) {
        showToast(messageErreurApi(err, 'Impossible de charger les années académiques — vérifiez que le référentiel est peuplé'), 'error')
      }
    })()
    // eslint-disable-next-line react-hooks/exhaustive-deps -- chargement initial unique ; showToast est stable.
  }, [])

  useEffect(() => {
    const type = TYPES_POPULATION.find((t) => t.valeur === form.population_type)
    if (!type) return
    let actif = true
    setPopulationItems([])
    setForm((prev) => ({ ...prev, population_id: '' }))
    ;(async () => {
      try {
        const params = type.valeur === 'GROUPE' && form.annee_academique_id
          ? { annee_academique_id: form.annee_academique_id }
          : undefined
        const res = await api.get(type.endpoint, { params })
        if (!actif) return
        setPopulationItems(Array.isArray(res.data) ? res.data : (res.data?.results ?? []))
      } catch (err) {
        if (actif) showToast(messageErreurApi(err, `Référentiel « ${type.libelle} » indisponible`), 'error')
      }
    })()
    return () => { actif = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- rechargement volontaire au changement de type/année.
  }, [form.population_type, form.annee_academique_id])

  const typeActif = useMemo(
    () => TYPES_POPULATION.find((t) => t.valeur === form.population_type) || TYPES_POPULATION[0],
    [form.population_type],
  )

  const itemChoisi = useMemo(
    () => populationItems.find((x) => String(x.id) === String(form.population_id)) || null,
    [populationItems, form.population_id],
  )

  const handleChange = (e) => {
    const { name, value } = e.target
    setForm((prev) => ({ ...prev, [name]: value }))
  }

  const semaineDebut = Number(form.semaine_debut) || 1
  const semaineFin = Number(form.semaine_fin) || 0
  const semainesCoherentes = semaineFin >= semaineDebut

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!form.annee_academique_id || !form.population_id) {
      showToast('Sélectionnez l’année académique et la population cible', 'error')
      return
    }
    if (!semainesCoherentes) {
      showToast('La semaine de fin doit être ≥ à la semaine de début', 'error')
      return
    }
    setLoading(true)
    try {
      const payload = { ...form, population_denominateur: itemChoisi ? String(itemChoisi[typeActif.cleLabel] || '') : '' }
      const res = await api.post('/edts/emplois/', payload)
      showToast('Emploi du temps créé — il est en brouillon')
      navigate(`/edt?selection=${res.data.id}`)
    } catch (err) {
      showToast(messageErreurApi(err, 'Création refusée'), 'error')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="container-fluid edt-page">
      <div className="row justify-content-center">
        <div className="col-lg-9 col-xxl-8">
          <div className="card">
            <div className="card-header edt-panel-head">
              <h5 className="edt-panel-title"><i className="bi bi-calendar-plus" />Nouvel emploi du temps</h5>
              <Link to="/edt" className="btn btn-outline-secondary btn-sm">
                <i className="bi bi-arrow-left"></i> Retour à la liste
              </Link>
            </div>
            <form onSubmit={handleSubmit} className="edt-form">
              <div className="card-body">
                <p className="edt-intro-note">
                  Un emploi du temps est l'espace d'édition d'une <strong>population cible</strong> (une formation,
                  un groupe, un enseignant ou une salle) pour une année académique donnée. Il naît en statut
                  {''} <span className="badge text-bg-secondary">{libelleStatut('BROUILLON')}</span> ; la soumission
                  à validation puis la publication restent du ressort des rôles habilités.
                </p>
                {annees.length === 0 && (
                  <div className="alert alert-warning small py-2">
                    <i className="bi bi-exclamation-triangle me-1"></i>
                    Aucune année académique au référentiel. Créez-en une dans
                    {' '}<a href="/admin/scolarite/anneeacademique/" className="alert-link">l’administration</a>{' '}
                    (ou le module scolarité) avant de créer un EDT.
                  </div>
                )}
                <div className="row g-3">
                  <div className="col-md-6">
                    <label className="form-label">Année académique <span className="text-danger">*</span></label>
                    <select className="form-select" name="annee_academique_id" value={form.annee_academique_id}
                            onChange={handleChange} required>
                      <option value="">Sélectionnez…</option>
                      {annees.map((a) => (
                        <option key={a.id} value={a.id}>
                          {a.libelle}{a.courante ? ' (courante)' : ''}{a.actif === false ? ' (inactive)' : ''}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="col-md-6">
                    <label className="form-label">Titre (facultatif)</label>
                    <input type="text" className="form-control" name="titre" value={form.titre}
                           onChange={handleChange} placeholder="Ex : EDT L1 MIF — 1er semestre" />
                  </div>
                  <div className="col-md-4">
                    <label className="form-label">Population cible <span className="text-danger">*</span></label>
                    <select className="form-select" name="population_type" value={form.population_type} onChange={handleChange}>
                      {TYPES_POPULATION.map((t) => <option key={t.valeur} value={t.valeur}>{t.libelle}</option>)}
                    </select>
                  </div>
                  <div className="col-md-8">
                    <label className="form-label">{typeActif.libelle} <span className="text-danger">*</span></label>
                    <select className="form-select" name="population_id" value={form.population_id} onChange={handleChange} required>
                      <option value="">Sélectionnez…</option>
                      {populationItems.map((item) => (
                        <option key={item.id} value={item.id}>
                          {String(item[typeActif.cleLabel] ?? `#${item.id}`)}
                        </option>
                      ))}
                    </select>
                    <div className="form-text">
                      {populationItems.length
                        ? `${populationItems.length} enregistrement(s) proposé(s) — libellé reporté automatiquement.`
                        : 'Référentiel vide pour ce type : alimentez-le côté socle.'}
                    </div>
                  </div>
                  <div className="col-md-4">
                    <label className="form-label">Date de rentrée</label>
                    <input type="date" className="form-control" name="rentree" value={form.rentree} onChange={handleChange} />
                  </div>
                  <div className="col-md-4">
                    <label className="form-label">Semaine début</label>
                    <input type="number" className="form-control" name="semaine_debut" value={form.semaine_debut}
                           onChange={handleChange} min="1" max="60" />
                  </div>
                  <div className="col-md-4">
                    <label className="form-label">Semaine fin</label>
                    <input type="number" className={`form-control ${semainesCoherentes ? '' : 'is-invalid'}`}
                           name="semaine_fin" value={form.semaine_fin} onChange={handleChange} min="1" max="60" />
                    {!semainesCoherentes && <div className="invalid-feedback">≥ à la semaine de début attendue.</div>}
                  </div>
                </div>
              </div>
              <div className="card-footer d-flex justify-content-between">
                <button type="button" className="btn btn-outline-secondary" onClick={() => navigate(-1)}>
                  Annuler
                </button>
                <button type="submit" className="btn btn-primary" disabled={loading}>
                  {loading
                    ? <><span className="spinner-border spinner-border-sm me-2"></span>Création…</>
                    : <><i className="bi bi-check2-circle me-1"></i>Créer l’EDT</>}
                </button>
              </div>
            </form>
          </div>
        </div>
      </div>
    </div>
  )
}
