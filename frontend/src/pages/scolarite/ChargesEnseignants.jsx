import React, { useCallback, useEffect, useMemo, useState } from 'react'
import api from '../../services/api'
import { canActScolarite } from '../../utils/roles'
import { useAuth } from '../../context/AuthContext'
import { useToast } from '../../context/ToastContext'
import '../../styles/premiumCommun.css'
import '../../styles/chargesEnseignants.css'

const PAGE_TAILLE = 20
const SEUIL_DEFAUT = 192

const formatH = (n) => `${new Intl.NumberFormat('fr-FR').format(Math.round(Number(n) || 0))} h`

function initiales(nomComplet) {
  return String(nomComplet || '')
    .split(' ')
    .filter(Boolean)
    .slice(0, 2)
    .map((mot) => mot[0])
    .join('')
    .toUpperCase() || '—'
}

const sansAccents = (v) => String(v ?? '')
  .normalize('NFD')
  .replace(/[\u0300-\u036f]/g, '')
  .toLowerCase()

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
  const [rechercheOcc, setRechercheOcc] = useState('')
  const [triOcc, setTriOcc] = useState(null)
  const [pageOcc, setPageOcc] = useState(1)
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

  // ── Occupation : synthèse, recherche, tri et pagination (client) ──
  const seuil = occupation.find((o) => o.seuil)?.seuil || SEUIL_DEFAUT
  const synthese = useMemo(() => {
    const totalAffectee = occupation.reduce((s, o) => s + (Number(o.affectee) || 0), 0)
    return {
      totalAffectee,
      moyenne: occupation.length ? totalAffectee / occupation.length : 0,
      surcharges: occupation.filter((o) => o.surcharge).length,
      nbAffectations: occupation.reduce((s, o) => s + (Number(o.nb_affectations) || 0), 0),
    }
  }, [occupation])

  const occupationAffichee = useMemo(() => {
    const terme = sansAccents(rechercheOcc).trim()
    let liste = occupation.filter(
      (o) => !terme || sansAccents(o.enseignant).includes(terme),
    )
    if (triOcc) {
      const { cle, dir } = triOcc
      liste = [...liste].sort((a, b) => (cle === 'enseignant'
        ? dir * String(a.enseignant).localeCompare(String(b.enseignant), 'fr')
        : dir * ((Number(a[cle]) || 0) - (Number(b[cle]) || 0))))
    }
    return liste
  }, [occupation, rechercheOcc, triOcc])

  const pagesOcc = Math.max(1, Math.ceil(occupationAffichee.length / PAGE_TAILLE))
  const pageOccSure = Math.min(pageOcc, pagesOcc)
  const lignesOcc = occupationAffichee.slice(
    (pageOccSure - 1) * PAGE_TAILLE, pageOccSure * PAGE_TAILLE)

  const basculerTri = (cle) => {
    setTriOcc((t) => (t?.cle === cle
      ? { cle, dir: -t.dir }
      : { cle, dir: cle === 'enseignant' ? 1 : -1 }))
    setPageOcc(1)
  }
  const flecheTri = (cle) => (triOcc?.cle !== cle
    ? <i className="bi bi-arrow-down-up chg-tri-neutre" aria-hidden="true"></i>
    : <i className={`bi bi-arrow-${triOcc.dir === 1 ? 'up' : 'down'}`} aria-hidden="true"></i>)

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
          {occupation.length > 0 && (
            <>
              <div className="chg-kpis">
                <div className="chg-kpi">
                  <span className="chg-kpi-icon is-blue"><i className="bi bi-people"></i></span>
                  <div><strong>{occupation.length}</strong><span>enseignants occupés</span></div>
                </div>
                <div className="chg-kpi">
                  <span className="chg-kpi-icon is-indigo"><i className="bi bi-journal-check"></i></span>
                  <div><strong>{formatH(synthese.totalAffectee)}</strong><span>{synthese.nbAffectations} affectations validées</span></div>
                </div>
                <div className="chg-kpi">
                  <span className="chg-kpi-icon is-cyan"><i className="bi bi-speedometer2"></i></span>
                  <div><strong>{formatH(synthese.moyenne)}</strong><span>charge moyenne (seuil {seuil} h)</span></div>
                </div>
                <div className="chg-kpi">
                  <span className={`chg-kpi-icon ${synthese.surcharges ? 'is-red' : 'is-green'}`}><i className="bi bi-exclamation-octagon"></i></span>
                  <div><strong>{synthese.surcharges}</strong><span>{synthese.surcharges ? 'surcharge(s) à rééquilibrer' : 'surcharge — aucune'}</span></div>
                </div>
              </div>
              <div className="chg-occ-tools">
                <label className="chg-recherche">
                  <i className="bi bi-search"></i>
                  <input
                    type="search"
                    placeholder="Rechercher un enseignant…"
                    aria-label="Rechercher un enseignant"
                    value={rechercheOcc}
                    onChange={(e) => { setRechercheOcc(e.target.value); setPageOcc(1) }}
                  />
                </label>
                <span className="chg-occ-compteur">
                  {occupationAffichee.length} enseignant(s) affiché(s)
                </span>
              </div>
            </>
          )}
          <div className="table-responsive">
            <table className="table table-sm table-hover mb-0 px-table chg-occ-table">
              <thead className="table-light">
                <tr>
                  <th><button type="button" className="chg-tri" onClick={() => basculerTri('enseignant')}>Enseignant {flecheTri('enseignant')}</button></th>
                  <th><button type="button" className="chg-tri" onClick={() => basculerTri('prevue')}>Prévue (h) {flecheTri('prevue')}</button></th>
                  <th><button type="button" className="chg-tri" onClick={() => basculerTri('affectee')}>Affectée (h) {flecheTri('affectee')}</button></th>
                  <th><button type="button" className="chg-tri" onClick={() => basculerTri('planifiee')}>Planifiée (h) {flecheTri('planifiee')}</button></th>
                  <th><button type="button" className="chg-tri" onClick={() => basculerTri('realisee')}>Réalisée (h) {flecheTri('realisee')}</button></th>
                  <th>Charge</th>
                </tr>
              </thead>
              <tbody>
                {occupation.length === 0 ? (
                  <tr><td colSpan={6} className="text-muted">Aucune affectation.</td></tr>
                ) : lignesOcc.length === 0 ? (
                  <tr><td colSpan={6} className="text-muted">Aucun enseignant ne correspond à « {rechercheOcc} ».</td></tr>
                ) : lignesOcc.map((o) => {
                  const seuilO = o.seuil || seuil
                  const pct = Math.min(100, Math.round(((Number(o.affectee) || 0) / seuilO) * 100))
                  const tonJauge = o.surcharge ? 'is-danger' : pct >= 85 ? 'is-amber' : 'is-ok'
                  return (
                    <tr key={o.enseignant_id} style={{ cursor: 'pointer' }}
                        className={`${o.enseignant_id === Number(enseignantChoisi) ? 'table-active ' : ''}chg-ligne`}
                        onClick={() => choisirEnseignant(o.enseignant_id)}>
                      <td>
                        <span className="chg-ens">
                          <span className="chg-avatar" aria-hidden="true">{initiales(o.enseignant)}</span>
                          <span className="chg-ens-txt">
                            <span className="chg-ens-nom">{o.enseignant}</span>
                            {o.nb_affectations != null && (
                              <span className="chg-ens-sub">{o.nb_affectations} affectation(s)</span>
                            )}
                          </span>
                        </span>
                      </td>
                      <td className="px-num chg-prevue">{o.prevue}</td>
                      <td className="px-num">
                        <span className="chg-aff">
                          <span className="chg-aff-val">{o.affectee}</span>
                          <span className="chg-jauge" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100} aria-label={`Charge de ${o.enseignant} : ${pct} % du seuil`}>
                            <span className={tonJauge} style={{ width: `${pct}%` }}></span>
                          </span>
                          <span className="chg-aff-pct">{pct} % du seuil</span>
                        </span>
                      </td>
                      <td className="px-num">{o.planifiee ? o.planifiee : <span className="chg-zero">0</span>}</td>
                      <td className="px-num">{o.realisee ? o.realisee : <span className="chg-zero">0</span>}</td>
                      <td>{o.surcharge
                        ? <span className="badge text-bg-danger px-state px-state--danger">Surcharge</span>
                        : <span className="badge text-bg-success px-state px-state--ok">OK</span>}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          {occupation.length > 0 && pagesOcc > 1 && (
            <div className="chg-pagination">
              <span>Page <strong>{pageOccSure}</strong> sur <strong>{pagesOcc}</strong> — {occupationAffichee.length} enseignant(s)</span>
              <div className="chg-pagination-actions">
                <button type="button" className="chg-page-btn" disabled={pageOccSure <= 1}
                        onClick={() => setPageOcc((p) => Math.max(1, p - 1))}>
                  <i className="bi bi-chevron-left"></i>Précédent
                </button>
                <button type="button" className="chg-page-btn" disabled={pageOccSure >= pagesOcc}
                        onClick={() => setPageOcc((p) => Math.min(pagesOcc, p + 1))}>
                  Suivant<i className="bi bi-chevron-right"></i>
                </button>
              </div>
            </div>
          )}
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
              <li>Prévue : {charge.prevue} h</li>
              <li>Affectée : {charge.affectee} h</li>
              <li>Planifiée : {charge.planifiee} h</li>
              <li>Réalisée : {charge.realisee} h</li>
            </ul>
            <table className="table table-sm mb-0 px-table chg-aff-table">
              <thead className="table-light">
                <tr><th>ECUE</th><th>Type</th><th>Volume (h)</th><th>Statut</th></tr>
              </thead>
              <tbody>
                {affectations.map((a) => (
                  <tr key={a.id}>
                    <td>{a.ecue || '—'}</td>
                    <td><span className={`chg-type chg-type--${String(a.type_enseignement || 'CM').toLowerCase()}`}>{a.type_enseignement}</span></td>
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
