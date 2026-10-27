import React, { useCallback, useEffect, useState } from 'react'
import api from '../../services/api'
import { canActScolarite } from '../../utils/roles'
import { useAuth } from '../../context/AuthContext'
import { useToast } from '../../context/ToastContext'
import '../../styles/premiumCommun.css'
import '../../styles/chargesEnseignants.css'

export default function ChargesEnseignants() {
  const { user } = useAuth()
  const toast = useToast()
  const peutAgir = canActScolarite(user)

  const [annee, setAnnee] = useState(null)
  const [enseignantChoisi, setEnseignantChoisi] = useState('')
  const [charge, setCharge] = useState(null)
  const [occupation, setOccupation] = useState([])
  const [anomalies, setAnomalies] = useState([])
  const [affectations, setAffectations] = useState([])
  const [chargement, setChargement] = useState(true)
  const [enCours, setEnCours] = useState(false)
  const [form, setForm] = useState({
    ref_formation_id: '', niveau_id: '', semestre_id: '', ecue_id: '',
    groupe_id: '', enseignant_id: '', type_enseignement: 'CM', volume_horaire: '',
  })
  // §10.13 (LOT 34) : l'état initial doit déclarer TOUTES les clés lues au
  // rendu (dont `formateurs` et `annees`, peuplées après coup) ; sinon, si le
  // chargement des référentiels échoue (ou répond après l'occupation), la
  // carte de création appelle `.map()` sur `undefined` et toute la page
  // crashe au lieu d'afficher des sélecteurs vides.
  const [options, setOptions] = useState({
    annees: [], formateurs: [], formations: [], niveaux: [], semestres: [], ecues: [], groupes: [],
  })

  // §10.8 (LOT 7) : ce chargement de l'année courante existait mais n'était
  // jamais appelé : `annee` restait à null et toute la page (occupation,
  // anomalies, création) restait inactive. Câblé sur un effet de montage.
  const chargerAnnee = useCallback(async () => {
    try {
      const res = await api.get('/scolarite/annee-courante/')
      const anneeData = res.data?.annee || res.data
      setAnnee(anneeData)
      return anneeData
    } catch {
      toast.showToast('Aucune année académique courante.', 'error')
      return null
    }
  }, [toast])

  const chargerTout = useCallback(async (anneeCourante) => {
    setChargement(true)
    try {
      const [occupationRes, anomaliesRes] = await Promise.all([
        api.get('/enseignants/occupation/', { params: { annee_id: anneeCourante.id } }),
        api.get('/enseignants/anomalies/', { params: { annee_id: anneeCourante.id } }),
      ])
      setOccupation(occupationRes.data.occupation || [])
      setAnomalies(anomaliesRes.data.anomalies || [])
    } catch (err) {
      toast.showToast('Chargement des charges impossible.', 'error')
    } finally {
      setChargement(false)
    }
  }, [toast])

  useEffect(() => {
    if (!peutAgir) return
    Promise.all([
      api.get('/scolarite/ref/annees/', { params: { actif: 'true' } }),
      api.get('/scolarite/ref/formations/'),
      api.get('/scolarite/ref/niveaux/', { params: { actif: 'true' } }),
      api.get('/scolarite/ref/semestres/'),
      api.get('/formateurs/list/'),
    ])
      .then(([annees, formations, niveaux, semestres, formateurs]) => setOptions({
        annees: Array.isArray(annees.data) ? annees.data : (annees.data?.results || []),
        formations: Array.isArray(formations.data) ? formations.data : (formations.data?.results || []),
        niveaux: Array.isArray(niveaux.data) ? niveaux.data : (niveaux.data?.results || []),
        semestres: Array.isArray(semestres.data) ? semestres.data : (semestres.data?.results || []),
        formateurs: Array.isArray(formateurs.data) ? formateurs.data : (formateurs.data?.results || []),
      }))
      .catch(() => toast.showToast('Chargement des référentiels impossible.', 'error'))
  }, [peutAgir, toast])

  // Au montage, résoudre l'année académique courante ; l'effet suivant
  // ([annee, chargerTout]) charge alors l'occupation et les anomalies.
  useEffect(() => {
    chargerAnnee()
  }, [chargerAnnee])

  useEffect(() => {
    if (!annee) return
    chargerTout(annee)
  }, [annee, chargerTout])

  const choisirEnseignant = async (enseignantId) => {
    setEnseignantChoisi(enseignantId)
    if (!enseignantId || !annee) { setCharge(null); return }
    try {
      const res = await api.get(`/enseignants/charges/${enseignantId}/`, { params: { annee_id: annee.id } })
      setCharge(res.data)
      const aff = await api.get('/enseignants/affectations/', {
        params: { enseignant_id: enseignantId, annee_academique_id: annee.id },
      })
      setAffectations(aff.data)
    } catch {
      toast.showToast('Chargement de la charge impossible.', 'error')
    }
  }

  const creerAffectation = async (e) => {
    e.preventDefault()
    setEnCours(true)
    try {
      await api.post('/enseignants/affectations/', {
        ...form,
        annee_academique_id: annee?.id,
        ref_formation_id: Number(form.ref_formation_id) || undefined,
        niveau_id: Number(form.niveau_id) || undefined,
        semestre_id: Number(form.semestre_id) || undefined,
        enseignant_id: Number(form.enseignant_id) || undefined,
        volume_horaire: Number(form.volume_horaire) || 0,
      })
      toast.showToast('Affectation créée.')
      setForm({ ...form, ecue_id: '', enseignant_id: '', volume_horaire: '' })
      if (annee) chargerTout(annee)
      if (enseignantChoisi) choisirEnseignant(enseignantChoisi)
    } catch (err) {
      toast.showToast(JSON.stringify(err.response?.data) || 'Création impossible.', 'error')
    } finally {
      setEnCours(false)
    }
  }


  if (chargement) {
    return <div className="container-fluid py-4"><div className="spinner-border" /></div>
  }

  return (
    <div className="container-fluid py-4 chg-page">
      {/* Hero — Variante A « Clair raffiné » */}
      <header className="px-hero">
        <span className="px-hero-icon"><i className="bi bi-person-workspace"></i></span>
        <div className="px-hero-text">
          <span className="px-hero-eyebrow">Scolarité · Charges LMD</span>
          <h1 className="px-hero-title">Charges pédagogiques des enseignants</h1>
          <p className="px-hero-intro">Volumes prévus, affectés, planifiés et réalisés par enseignant sur l'année académique courante.</p>
        </div>
        <div className="px-hero-side">
          <span className="px-plaquette">{annee ? `Année ${annee.libelle}` : 'Année courante'}</span>
          <span className="px-plaquette px-plaquette--soft">{occupation.length} enseignant(s)</span>
        </div>
      </header>

      {anomalies.length > 0 && (
        <div className="alert alert-warning px-alert">
          <strong><i className="bi bi-exclamation-triangle me-1"></i>
            {anomalies.length} anomalie(s) détectée(s) :</strong>
          <ul className="mb-0 mt-1">
            {anomalies.slice(0, 8).map((a, i) => <li key={i}>{a.detail}</li>)}
          </ul>
        </div>
      )}

      <div className="card px-panel mb-3 chg-occ">
        <div className="px-panel-head">
          <div className="px-panel-headtext">
            <h2 className="px-panel-title"><i className="bi bi-graph-up"></i>Occupation par enseignant — {annee?.libelle}</h2>
            <p className="px-panel-sub">Cliquez sur une ligne pour afficher le détail des affectations.</p>
          </div>
          <div className="px-panel-tools">
            <span className="px-count-pill">{occupation.length} enseignant(s)</span>
          </div>
        </div>
        <div className="card-body">
          <div className="table-responsive">
            <table className="table table-sm table-hover mb-0 px-table chg-occ-table">
              <thead className="table-light">
                <tr>
                  <th>Enseignant</th><th>Prévue (h)</th><th>Affectée (h)</th>
                  <th>Planifiée (h)</th><th>Réalisée (h)</th><th>Charge</th>
                </tr>
              </thead>
              <tbody>
                {occupation.length === 0 ? (
                  <tr><td colSpan={6} className="text-muted">Aucune affectation.</td></tr>
                ) : occupation.map((o) => (
                  <tr key={o.enseignant_id} style={{ cursor: 'pointer' }}
                      className={o.enseignant_id === Number(enseignantChoisi) ? 'table-active' : ''}
                      onClick={() => choisirEnseignant(o.enseignant_id)}>
                    <td>{o.enseignant}</td>
                    <td className="px-num">{o.prevue}</td>
                    <td className="px-num">{o.affectee}</td>
                    <td className="px-num">{o.planifiee}</td>
                    <td className="px-num">{o.realisee}</td>
                    <td>{o.surcharge
                      ? <span className="badge text-bg-danger px-state px-state--danger">Surcharge</span>
                      : <span className="badge text-bg-success px-state px-state--ok">OK</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {charge && (
        <div className="card px-panel mb-3 chg-detail">
          <div className="px-panel-head">
            <div className="px-panel-headtext">
              <h2 className="px-panel-title"><i className="bi bi-person-badge"></i>Détail — {charge.enseignant}</h2>
              <p className="px-panel-sub">Volumes de l'année pour cet enseignant.</p>
            </div>
            <div className="px-panel-tools">
              <span className="px-count-pill px-count-pill--muted">{affectations.length} affectation(s)</span>
            </div>
          </div>
          <div className="card-body">
            <ul className="list-unstyled mb-2 chg-recap">
              <li>Prévue : {charge.prevue} h · Affectée : {charge.affectee} h ·
                Planifiée : {charge.planifiee} h · Réalisée : {charge.realisee} h</li>
            </ul>
            <table className="table table-sm mb-0 px-table chg-aff-table">
              <thead className="table-light">
                <tr><th>ECUE</th><th>Type</th><th>Volume (h)</th><th>Statut</th></tr>
              </thead>
              <tbody>
                {affectations.map((a) => (
                  <tr key={a.id}>
                    <td>{a.ecue || '—'}</td>
                    <td><span className="chg-type">{a.type_enseignement}</span></td>
                    <td className="px-num">{a.volume_horaire}</td>
                    <td className="chg-statut">{a.statut}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {peutAgir && (
        <div className="card px-panel mb-3 chg-create">
          <div className="px-panel-head">
            <div className="px-panel-headtext">
              <h2 className="px-panel-title"><i className="bi bi-plus-circle me-1"></i>Nouvelle affectation pédagogique</h2>
              <p className="px-panel-sub">Rattachez un enseignant à une ECUE de l'année académique courante.</p>
            </div>
          </div>
          <div className="card-body">
            <form className="chg-form-grid" onSubmit={creerAffectation}>
              <label className="px-field">
                <span className="px-field-label">Enseignant à affecter</span>
                <select className="px-input px-select" required value={form.enseignant_id}
                        onChange={(e) => setForm({ ...form, enseignant_id: e.target.value })}>
                  <option value="">Enseignant…</option>
                  {options.formateurs.map((f) => (
                    <option key={f.id} value={f.id}>{f.nom} {f.prenom}</option>
                  ))}
                </select>
              </label>
              <label className="px-field">
                <span className="px-field-label">Formation</span>
                <select className="px-input px-select" required value={form.ref_formation_id}
                        onChange={(e) => setForm({ ...form, ref_formation_id: e.target.value })}>
                  <option value="">Formation…</option>
                  {options.formations.map((f) => <option key={f.id} value={f.id}>{f.intitule}</option>)}
                </select>
              </label>
              <label className="px-field">
                <span className="px-field-label">Niveau</span>
                <select className="px-input px-select" required value={form.niveau_id}
                        onChange={(e) => setForm({ ...form, niveau_id: e.target.value })}>
                  <option value="">Niveau…</option>
                  {options.niveaux.map((n) => <option key={n.id} value={n.id}>{n.code}</option>)}
                </select>
              </label>
              <label className="px-field">
                <span className="px-field-label">Semestre</span>
                <select className="px-input px-select" required value={form.semestre_id}
                        onChange={(e) => setForm({ ...form, semestre_id: e.target.value })}>
                  <option value="">Semestre…</option>
                  {options.semestres.filter((s) => s.niveau_id === Number(form.niveau_id)).map((s) => (
                    <option key={s.id} value={s.id}>{s.libelle}</option>
                  ))}
                </select>
              </label>
              <label className="px-field">
                <span className="px-field-label">Volume (h)</span>
                <input type="number" min="0" step="0.5" className="px-input" placeholder="Volume (h)"
                       required value={form.volume_horaire}
                       onChange={(e) => setForm({ ...form, volume_horaire: e.target.value })} />
              </label>
              <div className="chg-form-actions">
                <button className="btn btn-dfrc" disabled={enCours || !annee}>
                  <i className="bi bi-check2-circle me-1"></i>Créer l'affectation {annee ? `(${annee.libelle})` : ''}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
