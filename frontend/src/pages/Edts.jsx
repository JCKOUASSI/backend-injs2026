import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import api from '../services/api'
import { useToast } from '../context/ToastContext'
import { useAuth } from '../context/AuthContext'
import ConfirmModal from '../components/ConfirmModal'
import {
  ROLES_PLANIFICATION, ROLES_VALIDATION,
  construireMatriceGrille, classeBadgeStatut, formatDuree, formatHeure,
  libelleJour, libelleStatut, LIBELLES_CONFLITS, LIBELLES_NATURES,
  messageErreurApi, lireMutationAffectation, COULEURS_NATURES,
} from '../utils/edts'
import '../styles/edts.css'

const NATURES = Object.keys(LIBELLES_NATURES)

function ModalEditionAffectation({ affectation, creneaux, enseignants, onClose, onSaved, showToast }) {
  const [form, setForm] = useState({
    creneau_template_id: affectation.creneau_template_id || '',
    semaine_debut: affectation.semaine_debut || 1,
    semaine_fin: affectation.semaine_fin || affectation.semaine_debut || 1,
    nature: affectation.nature || 'COURS',
    intitule: affectation.intitule || '',
    enseignant_id: affectation.enseignant_id || '',
    enseignant_nom: affectation.enseignant_nom || '',
    groupe_id: affectation.groupe_id || '',
    salle_nom: affectation.salle_nom || '',
    commentaire: affectation.commentaire || '',
    actif: affectation.actif !== false,
  })
  const [busy, setBusy] = useState(false)

  const set = (cle) => (e) => {
    const valeur = e.target.type === 'checkbox' ? e.target.checked : e.target.value
    setForm((prev) => ({ ...prev, [cle]: valeur }))
  }

  const choisirEnseignant = (e) => {
    const id = e.target.value
    const trouve = (enseignants || []).find((u) => String(u.id) === String(id))
    setForm((prev) => ({ ...prev, enseignant_id: id, enseignant_nom: trouve ? trouve.nom_complet : prev.enseignant_nom }))
  }

  const soumettre = async () => {
    setBusy(true)
    try {
      const reponse = await api.patch(`/edts/affectations/${affectation.id}/`, form)
      const { avertissements } = lireMutationAffectation(reponse)
      if (avertissements.length) {
        showToast(`Affectation modifiée, mais ${avertissements.length} conflit(s) détecté(s).`, 'info')
      } else {
        showToast('Affectation modifiée')
      }
      onSaved()
    } catch (err) {
      showToast(messageErreurApi(err, 'Modification refusée'), 'error')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" style={{ maxWidth: 720 }} onClick={(e) => e.stopPropagation()}>
          <div className="modal-header">
            <h5 className="modal-title"><i className="bi bi-pencil-square me-2" />Modifier l’affectation #{affectation.id}</h5>
            <button type="button" className="btn-close" onClick={onClose} aria-label="Fermer" />
          </div>
          <div className="modal-body">
            <div className="row g-3">
              <div className="col-md-6">
                <label className="form-label">Créneau horaire</label>
                <select className="form-select" value={form.creneau_template_id} onChange={set('creneau_template_id')}>
                  <option value="">— aucun —</option>
                  {(creneaux || []).map((c) => (
                    <option key={c.id} value={c.id}>
                      {libelleJour(c.jour)} {formatHeure(c.heure_debut)}–{formatHeure(c.heure_fin)} ({formatDuree(c.duree_prevue_minutes)})
                    </option>
                  ))}
                </select>
              </div>
              <div className="col-md-3">
                <label className="form-label">Semaine début</label>
                <input type="number" className="form-control" min="1" max="60" value={form.semaine_debut} onChange={set('semaine_debut')} />
              </div>
              <div className="col-md-3">
                <label className="form-label">Semaine fin</label>
                <input type="number" className="form-control" min="1" max="60" value={form.semaine_fin} onChange={set('semaine_fin')} />
              </div>
              <div className="col-md-3">
                <label className="form-label">Nature</label>
                <select className="form-select" value={form.nature} onChange={set('nature')}>
                  {NATURES.map((n) => <option key={n} value={n}>{LIBELLES_NATURES[n]}</option>)}
                </select>
              </div>
              <div className="col-md-9">
                <label className="form-label">Intitulé</label>
                <input className="form-control" value={form.intitule} onChange={set('intitule')} placeholder="Ex : Algorithmique" />
              </div>
              <div className="col-md-6">
                <label className="form-label">Enseignant</label>
                <select className="form-select" value={form.enseignant_id} onChange={choisirEnseignant}>
                  <option value="">— aucun —</option>
                  {(enseignants || []).map((u) => <option key={u.id} value={u.id}>{u.nom_complet}</option>)}
                </select>
              </div>
              <div className="col-md-6">
                <label className="form-label">Groupe (id)</label>
                <input type="number" className="form-control" value={form.groupe_id} onChange={set('groupe_id')} placeholder="Laisser vide si N/A" />
              </div>
              <div className="col-md-6">
                <label className="form-label">Salle</label>
                <input className="form-control" value={form.salle_nom} onChange={set('salle_nom')} placeholder="Ex : A101" />
              </div>
              <div className="col-md-6">
                <label className="form-label">Commentaire</label>
                <input className="form-control" value={form.commentaire} onChange={set('commentaire')} />
              </div>
              <div className="col-12">
                <div className="form-check form-switch">
                  <input className="form-check-input" type="checkbox" checked={form.actif} onChange={set('actif')} id="affActif" />
                  <label className="form-check-label" htmlFor="affActif">Affectation active (décocher = annulation posée)</label>
                </div>
              </div>
            </div>
          </div>
          <div className="modal-footer">
            <button className="btn btn-outline-secondary" onClick={onClose}>Annuler</button>
            <button className="btn btn-primary" onClick={soumettre} disabled={busy}>
              {busy ? <><span className="spinner-border spinner-border-sm me-2" />Enregistrement…</> : <><i className="bi bi-check2 me-1" />Enregistrer</>}
            </button>
          </div>
        </div>
      </div>
  )
}

export default function Edts() {
  const [searchParams, setSearchParams] = useSearchParams()
  const { showToast } = useToast()
  const { user } = useAuth()
  const role = user?.role || ''
  const peutPlanifier = ROLES_PLANIFICATION.includes(role) || Boolean(user?.is_superuser)
  const peutValider = ROLES_VALIDATION.includes(role) || Boolean(user?.is_superuser)

  const [loading, setLoading] = useState(true)
  const [edts, setEdts] = useState([])
  const [annees, setAnnees] = useState([])
  const [creneaux, setCreneaux] = useState([])
  const [enseignants, setEnseignants] = useState([])
  const [filtreAnnee, setFiltreAnnee] = useState(searchParams.get('annee') || '')
  const [filtreStatut, setFiltreStatut] = useState(searchParams.get('statut') || '')
  const [recherche, setRecherche] = useState(searchParams.get('q') || '')
  const [selectedId, setSelectedId] = useState(Number(searchParams.get('selection')) || null)
  const [detail, setDetail] = useState(null)
  const [affectations, setAffectations] = useState([])
  const [grille, setGrille] = useState({ jours: [] })
  const [conflits, setConflits] = useState([])
  const [chargementDetail, setChargementDetail] = useState(false)
  const [vue, setVue] = useState('grille')
  const [semaine, setSemaine] = useState(null)
  const [edition, setEdition] = useState(null)
  const [confirmation, setConfirmation] = useState(null)
  const [busy, setBusy] = useState(false)

  const selectionner = useCallback((id) => {
    setSelectedId(id)
    setSearchParams((prev) => {
      const suivant = new URLSearchParams(prev)
      if (id) suivant.set('selection', String(id))
      else suivant.delete('selection')
      return suivant
    }, { replace: true })
  }, [setSearchParams])

  const chargerListe = useCallback(async () => {
    setLoading(true)
    try {
      const params = {}
      if (filtreAnnee) params.annee_academique_id = filtreAnnee
      if (filtreStatut) params.statut = filtreStatut
      if (recherche.trim()) params.q = recherche.trim()
      // Les enseignants voient d'office leur périmètre ; les autres tout (filtre serveur).
      if (!peutPlanifier) params.selon_role = '1'
      const res = await api.get('/edts/emplois/', { params })
      const data = Array.isArray(res.data) ? res.data : (res.data?.results ?? [])
      setEdts(data)
      if (!selectedId && data.length) selectionner(data[0].id)
      if (selectedId && !data.some((e) => e.id === selectedId)) selectionner(data[0]?.id || null)
    } catch (err) {
      showToast(messageErreurApi(err, 'Erreur de chargement des emplois du temps'), 'error')
    } finally {
      setLoading(false)
    }
  }, [filtreAnnee, filtreStatut, recherche, selectedId, showToast, selectionner, peutPlanifier])

  useEffect(() => {
    let actif = true
    ;(async () => {
      try {
        const [anneesRes, creneauxRes, enseignantsRes] = await Promise.all([
          api.get('/scolarite/ref/annees/').catch(() => null),
          api.get('/edts/creneaux-types/').catch(() => null),
          api.get('/edts/referentiel-enseignants/').catch(() => null),
        ])
        if (!actif) return
        if (anneesRes) setAnnees(Array.isArray(anneesRes.data) ? anneesRes.data : (anneesRes.data?.results ?? []))
        if (creneauxRes) setCreneaux(Array.isArray(creneauxRes.data) ? creneauxRes.data : [])
        if (enseignantsRes) setEnseignants(Array.isArray(enseignantsRes.data) ? enseignantsRes.data : [])
      } catch { /* référentiels optionnels pour l'affichage liste */ }
    })()
    return () => { actif = false }
  }, [])

  // chargerListe n'est pas mémoïsé sur selectedId pour éviter une boucle sélection→liste.
  // eslint-disable-next-line react-hooks/exhaustive-deps -- rechargement à la demande (filtres/montée) ;
  useEffect(() => { chargerListe() }, [filtreAnnee, filtreStatut, recherche])

  const chargerDetail = useCallback(async (id, semaineChoisie) => {
    if (!id) return
    setChargementDetail(true)
    try {
      const requeteSemaine = semaineChoisie ? { semaine: semaineChoisie } : {}
      const [edtRes, affRes, grilleRes, conflitsRes] = await Promise.all([
        api.get(`/edts/emplois/${id}/`),
        api.get('/edts/affectations/', { params: { emploi_du_temps_id: id, actif: 'true' } }),
        api.get(`/edts/emplois/${id}/grille/`, { params: requeteSemaine }),
        api.get('/edts/conflits/', { params: { emploi_du_temps_id: id } }),
      ])
      setDetail(edtRes.data)
      setAffectations(Array.isArray(affRes.data) ? affRes.data : [])
      setGrille(grilleRes.data || { jours: [] })
      setConflits(Array.isArray(conflitsRes.data) ? conflitsRes.data : [])
      if (semaineChoisie == null && semaine == null) {
        setSemaine(edtRes.data.semaine_debut || 1)
      }
    } catch (err) {
      showToast(messageErreurApi(err, 'Erreur de chargement du détail'), 'error')
    } finally {
      setChargementDetail(false)
    }
  }, [showToast, semaine])

  useEffect(() => {
    chargerDetail(selectedId, vue === 'grille' ? semaine : null)
  }, [selectedId, semaine, vue, chargerDetail])

  const edtsAffiches = edts
  const selectedEdt = useMemo(
    () => edtsAffiches.find((e) => e.id === selectedId) || detail,
    [edtsAffiches, selectedId, detail],
  )
  const gele = selectedEdt ? ['VALIDE', 'PUBLIE', 'ARCHIVE', 'EN_VALIDATION'].includes(selectedEdt.statut) : true
  const modifiable = peutPlanifier && !gele
  const matrice = useMemo(() => construireMatriceGrille(grille, conflits), [grille, conflits])
  const nbSemaines = selectedEdt ? (selectedEdt.semaine_fin || 1) - (selectedEdt.semaine_debut || 1) + 1 : 0

  const action = async (chemin, corps, succesMessage, apresRechargement = true) => {
    setBusy(true)
    try {
      await api.post(chemin, corps || {})
      showToast(succesMessage)
      if (apresRechargement) {
        await chargerListe()
        await chargerDetail(selectedId, vue === 'grille' ? semaine : null)
      }
      return true
    } catch (err) {
      showToast(messageErreurApi(err, 'Action refusée'), 'error')
      return false
    } finally {
      setBusy(false)
    }
  }

  const detecterConflits = async () => {
    setBusy(true)
    try {
      const res = await api.post(`/edts/emplois/${selectedId}/conflits/`)
      const stats = res.data?.stats || {}
      showToast(`Détection terminée : ${stats.conflits_detectes ?? 0} conflit(s), ${stats.conflits_clotures ?? 0} closé(s)`)
      await chargerDetail(selectedId, vue === 'grille' ? semaine : null)
      await chargerListe()
    } catch (err) {
      showToast(messageErreurApi(err, 'Échec de la détection'), 'error')
    } finally {
      setBusy(false)
    }
  }

  const exporterCsv = async () => {
    try {
      const { blob, fileName } = await api.getBlob(`/edts/emplois/${selectedId}/export.csv/`)
      const url = URL.createObjectURL(blob)
      const lien = document.createElement('a')
      lien.href = url
      lien.download = fileName || `edt-${selectedId}.csv`
      document.body.appendChild(lien)
      lien.click()
      lien.remove()
      URL.revokeObjectURL(url)
      showToast('Export CSV téléchargé')
    } catch (err) {
      showToast(messageErreurApi(err, 'Export impossible'), 'error')
    }
  }

  const basculerAffectation = async (aff) => {
    try {
      await api.patch(`/edts/affectations/${aff.id}/`, { actif: !aff.actif })
      showToast(aff.actif ? 'Créneau désactivé' : 'Créneau réactivé')
      chargerDetail(selectedId, vue === 'grille' ? semaine : null)
    } catch (err) {
      showToast(messageErreurApi(err, 'Modification refusée'), 'error')
    }
  }

  const demanderConfirmation = (config) => setConfirmation(config)

  return (
    <div className="container-fluid pb-5 edt-page">
      <div className="edt-hero">
        <div className="edt-hero-text">
          <span className="edt-hero-badge"><i className="bi bi-calendar-week" /> GET-INJS</span>
          <h2 className="edt-hero-title"><i className="bi bi-calendar-week" />Emplois du temps <span className="edt-hero-title-sub">(GET-INJS)</span></h2>
          <p className="edt-hero-intro">Planification hebdomadaire des créneaux, affectation des salles et détection des conflits (enseignant · salle · groupe).</p>
        </div>
        <div className="edt-hero-actions">
          <Link to="/edt/conflits" className="btn btn-outline-danger"><i className="bi bi-exclamation-octagon"></i> Conflits globaux</Link>
          <Link to="/edt/salles-espaces" className="btn btn-outline-secondary"><i className="bi bi-door-open"></i> Salles</Link>
          {peutPlanifier && (
            <Link to="/edt/nouveau" className="btn btn-primary"><i className="bi bi-plus-circle"></i> Nouvel EDT</Link>
          )}
        </div>
      </div>

      <div className="card mb-3 edt-toolbar">
        <div className="card-body row g-2 align-items-end">
          <div className="col-md-3">
            <label className="form-label small text-muted mb-1">Année académique</label>
            <select className="form-select form-select-sm" value={filtreAnnee} onChange={(e) => setFiltreAnnee(e.target.value)}>
              <option value="">Toutes</option>
              {annees.map((a) => <option key={a.id} value={a.id}>{a.libelle}</option>)}
            </select>
          </div>
          <div className="col-md-3">
            <label className="form-label small text-muted mb-1">Statut</label>
            <select className="form-select form-select-sm" value={filtreStatut} onChange={(e) => setFiltreStatut(e.target.value)}>
              <option value="">Tous</option>
              {['BROUILLON', 'EN_VALIDATION', 'VALIDE', 'PUBLIE', 'ARCHIVE'].map((s) => (
                <option key={s} value={s}>{libelleStatut(s)}</option>
              ))}
            </select>
          </div>
          <div className="col-md-4">
            <label className="form-label small text-muted mb-1">Recherche</label>
            <input className="form-control form-control-sm" placeholder="Titre ou population…"
                   value={recherche} onChange={(e) => setRecherche(e.target.value)} />
          </div>
          <div className="col-md-2 d-grid">
            <button className="btn btn-sm btn-outline-secondary" onClick={chargerListe}>
              <i className="bi bi-arrow-clockwise"></i> Actualiser
            </button>
          </div>
        </div>
      </div>

      <div className="row g-3">
        <div className="col-xl-3">
          <div className="card edt-panel">
            <div className="card-header edt-panel-head">
              <span className="edt-panel-title"><i className="bi bi-calendar3" /> Emplois du temps</span>
              <span className="edt-count-pill">{edts.length}</span>
            </div>
            <div className="list-group list-group-flush edt-list" style={{ maxHeight: 480, overflowY: 'auto' }}>
              {loading ? (
                <div className="text-center py-4"><div className="spinner-border text-primary" /></div>
              ) : edts.length === 0 ? (
                <div className="text-center py-4 text-muted edt-empty">
                  <i className="bi bi-calendar-x fs-1 d-block mb-2" />
                  Aucun emploi du temps
                  {peutPlanifier && <div className="small mt-2">Créez-en un avec « Nouvel EDT ».</div>}
                </div>
              ) : edts.map((edt) => (
                <button key={edt.id} type="button"
                        className={`edt-item list-group-item list-group-item-action d-flex justify-content-between align-items-center gap-2 ${selectedId === edt.id ? 'active' : ''}`}
                        onClick={() => selectionner(edt.id)}>
                  <span className="text-truncate text-start">
                    <span className="d-block fw-semibold">{edt.titre || edt.population_label}</span>
                    <small className={selectedId === edt.id ? 'opacity-75' : 'text-muted d-block'}>
                      {edt.annee_academique} · s{edt.semaine_debut}–s{edt.semaine_fin} · {edt.affectations_count ?? '—'} créneaux
                    </small>
                  </span>
                  <span className={classeBadgeStatut(edt.statut)}>{libelleStatut(edt.statut)}</span>
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="col-xl-9">
          {!selectedId ? (
            <div className="card edt-empty-panel"><div className="card-body text-center py-5 text-muted">
              <i className="bi bi-calendar-week fs-1 d-block mb-3" />Sélectionnez un emploi du temps.
            </div></div>
          ) : (
            <>
              <div className="card mb-3 edt-detail">
                <div className="card-body d-flex flex-wrap justify-content-between align-items-center gap-2">
                  <div className="edt-detail-text">
                    <h5 className="edt-detail-title mb-1">
                      {selectedEdt?.titre || selectedEdt?.population_label}{' '}
                      <span className={classeBadgeStatut(selectedEdt?.statut)}>{libelleStatut(selectedEdt?.statut)}</span>
                    </h5>
                    <div className="text-muted small edt-detail-meta">
                      {selectedEdt?.population_label} · {selectedEdt?.annee_academique} · Semaines {selectedEdt?.semaine_debut} à {selectedEdt?.semaine_fin}
                      {selectedEdt?.conflits_count ? ` · ${selectedEdt.conflits_count} conflit(s) actif(s)` : ''}
                    </div>
                  </div>
                  <div className="d-flex flex-wrap gap-2">
                    {vue === 'grille' && nbSemaines > 0 && (
                      <div className="input-group input-group-sm" style={{ width: 190 }}>
                        <button className="btn btn-outline-secondary" disabled={!semaine || semaine <= (selectedEdt?.semaine_debut || 1)}
                                onClick={() => setSemaine((s) => Math.max((selectedEdt?.semaine_debut || 1), s - 1))}>◀</button>
                        <span className="input-group-text">Semaine</span>
                        <input type="number" className="form-control" min={selectedEdt?.semaine_debut || 1} max={selectedEdt?.semaine_fin || 60}
                               value={semaine ?? ''} onChange={(e) => setSemaine(Number(e.target.value) || null)} />
                        <button className="btn btn-outline-secondary" disabled={!semaine || semaine >= (selectedEdt?.semaine_fin || 60)}
                                onClick={() => setSemaine((s) => Math.min((selectedEdt?.semaine_fin || 60), s + 1))}>▶</button>
                      </div>
                    )}
                    <div className="btn-group btn-group-sm">
                      <button className={`btn btn-outline-primary ${vue === 'grille' ? 'active' : ''}`} onClick={() => setVue('grille')}>
                        <i className="bi bi-grid-3x3" /> Grille
                      </button>
                      <button className={`btn btn-outline-primary ${vue === 'tableau' ? 'active' : ''}`} onClick={() => setVue('tableau')}>
                        <i className="bi bi-table" /> Tableau
                      </button>
                    </div>
                    <button className="btn btn-sm btn-outline-dark" onClick={detecterConflits} disabled={busy}>
                      <i className="bi bi-search" /> Détection
                    </button>
                    {modifiable && (
                      <Link to={`/edt/${selectedId}/affectation/nouveau${semaine ? `?semaine=${semaine}` : ''}`}
                            className="btn btn-sm btn-outline-primary">
                        <i className="bi bi-plus-circle" /> Créneau
                      </Link>
                    )}
                    <button className="btn btn-sm btn-outline-success" onClick={exporterCsv}>
                      <i className="bi bi-filetype-csv" /> Export
                    </button>
                  </div>
                </div>
                {modifiable && selectedEdt?.statut === 'BROUILLON' && (
                  <div className="card-footer bg-transparent d-flex flex-wrap gap-2 border-top">
                    <button className="btn btn-sm btn-outline-warning" disabled={busy}
                            onClick={() => action(`/edts/emplois/${selectedId}/soumettre/`, {}, 'Emploi du temps soumis à validation')}>
                      <i className="bi bi-send" /> Soumettre à validation
                    </button>
                    <button className="btn btn-sm btn-outline-primary" disabled={busy}
                            onClick={() => demanderConfirmation({
                              message: 'Générer un brouillon à partir des affectations pédagogiques validées du socle ?',
                              detail: 'Les créneaux posés manuellement sont conservés ; les lignes déjà générées sont remplacées.',
                              confirmLabel: 'Générer',
                              variante: 'primary',
                              action: () => action(`/edts/emplois/${selectedId}/generer/`, { remplace_existant: true }, 'Brouillon généré — à contrôler avant soumission'),
                            })}>
                      <i className="bi bi-magic" /> Générer le brouillon
                    </button>
                    <button className="btn btn-sm btn-outline-danger" disabled={busy}
                            onClick={() => demanderConfirmation({
                              message: 'Supprimer définitivement cet emploi du temps ?',
                              detail: 'Réservé aux brouillons. Cette action est tracée dans le journal.',
                              confirmLabel: 'Supprimer',
                              action: async () => {
                                try {
                                  await api.delete(`/edts/emplois/${selectedId}/`)
                                  showToast('Emploi du temps supprimé')
                                  selectionner(null)
                                  await chargerListe()
                                } catch (err) {
                                  showToast(messageErreurApi(err, 'Suppression refusée'), 'error')
                                }
                              },
                            })}>
                      <i className="bi bi-trash" /> Supprimer
                    </button>
                  </div>
                )}
                {peutPlanifier && selectedEdt?.statut === 'EN_VALIDATION' && !peutValider && (
                  <div className="card-footer bg-transparent border-top">
                    <button className="btn btn-sm btn-outline-warning" disabled={busy}
                            onClick={() => action(`/edts/emplois/${selectedId}/valider/`, { statut: 'BROUILLON' }, 'Soumission retirée')}
                            title="EN_VALIDATION → BROUILLON">
                      <i className="bi bi-arrow-counterclockwise" /> Retirer de la file de validation
                    </button>
                  </div>
                )}
                {peutValider && (
                  <div className="card-footer bg-transparent d-flex flex-wrap gap-2 border-top">
                    {selectedEdt?.statut === 'EN_VALIDATION' && (
                      <button className="btn btn-sm btn-outline-info" disabled={busy}
                              onClick={() => action(`/edts/emplois/${selectedId}/valider/`, { statut: 'VALIDE' }, 'Emploi du temps validé')}>
                        <i className="bi bi-check2-all" /> Valider
                      </button>
                    )}
                    {selectedEdt?.statut === 'VALIDE' && (
                      <button className="btn btn-sm btn-outline-success" disabled={busy}
                              onClick={() => action(`/edts/emplois/${selectedId}/publier/`, {}, 'Emploi du temps publié')}>
                        <i className="bi bi-globe2" /> Publier
                      </button>
                    )}
                    {selectedEdt?.statut === 'PUBLIE' && (
                      <button className="btn btn-sm btn-outline-warning" disabled={busy}
                              onClick={() => demanderConfirmation({
                                message: 'Cet emploi du temps publié redeviendra un brouillon éditable.',
                                detail: 'Les auditeurs ne le verront plus dans les EDT publiés tant qu’il n’est pas republié.',
                                confirmLabel: 'Dépublier',
                                variante: 'warning',
                                action: () => action(`/edts/emplois/${selectedId}/depublier/`, {}, 'Emploi du temps dépublié (retourné en brouillon)'),
                              })}>
                        <i className="bi bi-arrow-down-circle" /> Dépublier
                      </button>
                    )}
                    {['BROUILLON', 'EN_VALIDATION', 'VALIDE', 'PUBLIE'].includes(selectedEdt?.statut) && (
                      <button className="btn btn-sm btn-outline-dark" disabled={busy}
                              onClick={() => demanderConfirmation({
                                message: 'Archiver cet emploi du temps ?',
                                detail: 'Il sort du circuit actif ; seule la Direction peut le rouvrir ou le supprimer.',
                                confirmLabel: 'Archiver',
                                variante: 'secondary',
                                action: () => action(`/edts/emplois/${selectedId}/archiver/`, {}, 'Emploi du temps archivé'),
                              })}>
                        <i className="bi bi-archive" /> Archiver
                      </button>
                    )}
                    {selectedEdt?.statut === 'ARCHIVE' && (
                      <button className="btn btn-sm btn-outline-secondary" disabled={busy}
                              onClick={() => action(`/edts/emplois/${selectedId}/depublier/`, {}, 'Emploi du temps rouvert en brouillon')}>
                        <i className="bi bi-arrow-counterclockwise" /> Rouvrir
                      </button>
                    )}
                  </div>
                )}
              </div>

              {gele && peutPlanifier && !peutValider && (
                <div className="alert alert-warning py-2">
                  <i className="bi bi-lock me-1" />
                  Édition verrouillée par le statut « {libelleStatut(selectedEdt?.statut)} » — demandez la dépublication à la Direction.
                </div>
              )}

              {chargementDetail ? (
                <div className="card"><div className="card-body text-center py-5"><div className="spinner-border text-primary" /></div></div>
              ) : vue === 'grille' ? (
                <div className="card mb-3 edt-panel">
                  <div className="card-header edt-panel-head">
                    <span className="edt-panel-title"><i className="bi bi-grid-3x3" /> Semaine {semaine ?? '—'}</span>
                    <span className={`edt-count-pill ${conflits.length ? 'is-danger' : ''}`}>{conflits.length} conflit(s) actif(s)</span>
                  </div>
                  <div className="table-responsive">
                    {matrice.length === 0 ? (
                      <div className="text-center text-muted py-5">
                        <i className="bi bi-calendar-x fs-1 d-block mb-2" />
                        Aucun créneau occupé {semaine ? `en semaine ${semaine}` : ''}.
                      </div>
                    ) : (
                      <table className="table table-bordered align-top mb-0 edt-table">
                        <thead className="table-light">
                          <tr>{matrice.map((col) => <th key={col.jour}>{col.libelle}</th>)}</tr>
                        </thead>
                        <tbody>
                          {(() => {
                            const heures = [...new Set(matrice.flatMap((col) => col.lignes.map((c) => `${c.heure_debut}-${c.heure_fin}`)))].sort()
                            return heures.map((plage) => (
                              <tr key={plage}>
                                {matrice.map((col) => {
                                  const cellule = col.lignes.find((c) => `${c.heure_debut}-${c.heure_fin}` === plage)
                                  return (
                                    <td key={col.jour} className={cellule?.enConflit ? 'table-danger align-top' : 'align-top'}
                                        style={{ minWidth: 180, ...(cellule ? { cursor: 'pointer' } : {}) }}
                                        onClick={() => cellule && setVue('tableau')}>
                                      {cellule ? (
                                        <>
                                          <div className="text-muted small">{formatHeure(cellule.heure_debut)}–{formatHeure(cellule.heure_fin)}</div>
                                          {cellule.affectations.map((a) => (
                                            <div key={a.id} className="mb-2 p-2 rounded border edt-cell">
                                              <span className={`badge ${COULEURS_NATURES[a.nature] || 'text-bg-secondary'} me-1`}>
                                                {LIBELLES_NATURES[a.nature] || a.nature}
                                              </span>
                                              <span className="small fw-semibold">{a.intitule || '—'}</span>
                                              <div className="small text-muted">
                                                {[a.enseignant_nom, a.groupe, a.salle_nom && `salle ${a.salle_nom}`].filter(Boolean).join(' · ')}
                                              </div>
                                              <div className="small text-muted">s{a.semaine_debut}–s{a.semaine_fin}</div>
                                            </div>
                                          ))}
                                        </>
                                      ) : <span className="text-muted">—</span>}
                                    </td>
                                  )
                                })}
                              </tr>
                            ))
                          })()}
                        </tbody>
                      </table>
                    )}
                  </div>
                </div>
              ) : (
                <div className="card mb-3 edt-panel">
                  <div className="card-header edt-panel-head">
                    <span className="edt-panel-title"><i className="bi bi-table" /> Créneaux posés ({affectations.length})</span>
                  </div>
                  <div className="table-responsive">
                    <table className="table table-hover align-middle mb-0 edt-table">
                      <thead className="table-light">
                        <tr>
                          <th>Créneau</th><th>Semaines</th><th>Nature</th><th>Contenu</th>
                          <th>Enseignant</th><th>Groupe</th><th>Salle</th>
                          <th className="text-end">Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {affectations.length === 0 ? (
                          <tr><td colSpan="8" className="text-center text-muted py-4">Aucune affectation active.</td></tr>
                        ) : affectations.map((aff) => (
                          <tr key={aff.id} className={conflits.some((c) => (c.lignes_creneaux || []).includes(aff.id)) ? 'table-warning' : ''}>
                            <td className="text-nowrap">{aff.horaire || <span className="text-muted">—</span>}</td>
                            <td>s{aff.semaine_debut}–s{aff.semaine_fin}</td>
                            <td><span className={`badge ${COULEURS_NATURES[aff.nature] || 'text-bg-secondary'}`}>{LIBELLES_NATURES[aff.nature] || aff.nature}</span></td>
                            <td>{aff.intitule || <span className="text-muted">—</span>}{aff.commentaire && <div className="small text-muted">{aff.commentaire}</div>}</td>
                            <td>{aff.enseignant_nom || <span className="text-muted">—</span>}</td>
                            <td>{aff.groupe || <span className="text-muted">—</span>}</td>
                            <td>{aff.salle_nom || <span className="text-muted">—</span>}</td>
                            <td className="text-end text-nowrap">
                              {modifiable ? (
                                <>
                                  <button className="btn btn-sm btn-outline-primary me-1" title="Modifier" onClick={() => setEdition(aff)}>
                                    <i className="bi bi-pencil" />
                                  </button>
                                  <button className="btn btn-sm btn-outline-secondary me-1" title="Désactiver / réactiver" onClick={() => basculerAffectation(aff)}>
                                    <i className={`bi ${aff.actif ? 'bi-pause-circle' : 'bi-play-circle'}`} />
                                  </button>
                                  <button className="btn btn-sm btn-outline-danger" title="Supprimer"
                                          onClick={() => demanderConfirmation({
                                            message: 'Supprimer définitivement cette affectation ?',
                                            detail: 'Préférez la désactivation pour une annulation justifiée (traçable).',
                                            confirmLabel: 'Supprimer',
                                            action: async () => {
                                              try {
                                                await api.delete(`/edts/affectations/${aff.id}/`)
                                                showToast('Affectation supprimée')
                                                chargerDetail(selectedId, vue === 'grille' ? semaine : null)
                                              } catch (err) {
                                                showToast(messageErreurApi(err, 'Suppression refusée'), 'error')
                                              }
                                            },
                                          })}>
                                    <i className="bi bi-trash" />
                                  </button>
                                </>
                              ) : <span className="text-muted small">verrouillé</span>}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              <div className="card edt-panel">
                <div className="card-header edt-panel-head">
                  <span className="edt-panel-title is-danger"><i className="bi bi-exclamation-triangle" /> Conflits de cet emploi du temps</span>
                  <span className="edt-count-pill is-danger">{conflits.length}</span>
                </div>
                <div className="card-body">
                  {conflits.length === 0 ? (
                    <p className="text-muted mb-0"><i className="bi bi-check2-circle text-success me-1" /> Aucun conflit actif.</p>
                  ) : (
                    <ul className="list-group list-group-flush">
                      {conflits.map((c) => (
                        <li key={c.id} className="list-group-item d-flex justify-content-between align-items-start gap-2 px-0">
                          <div>
                            <span className="badge text-bg-danger me-2">{LIBELLES_CONFLITS[c.type_conflit] || c.type_conflit}</span>
                            <span className="small text-muted">détecté le {new Date(c.recalcule_le).toLocaleString('fr-FR')}</span>
                            <div className="mt-1">{c.description}</div>
                          </div>
                          {peutPlanifier && (
                            <button className="btn btn-sm btn-outline-success text-nowrap" disabled={busy}
                                    onClick={() => demanderConfirmation({
                                      message: 'Confirmer la résolution de ce conflit ?',
                                      detail: 'La résolution est tracée dans le journal de scolarité.',
                                      confirmLabel: 'Résolu',
                                      variante: 'success',
                                      action: async () => {
                                        try {
                                          await api.post(`/edts/conflits/${c.id}/resoudre/`, { motif: 'Résolu depuis l’écran EDT' })
                                          showToast('Conflit marqué résolu')
                                          chargerDetail(selectedId, vue === 'grille' ? semaine : null)
                                          chargerListe()
                                        } catch (err) {
                                          showToast(messageErreurApi(err, 'Résolution refusée'), 'error')
                                        }
                                      },
                                    })}>
                              <i className="bi bi-check2" /> Résoudre
                            </button>
                          )}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </div>
            </>
          )}
        </div>
      </div>

      {edition && (
        <ModalEditionAffectation
          affectation={edition}
          creneaux={creneaux}
          enseignants={enseignants}
          onClose={() => setEdition(null)}
          onSaved={() => { setEdition(null); chargerDetail(selectedId, vue === 'grille' ? semaine : null); chargerListe() }}
          showToast={showToast}
        />
      )}

      {confirmation && (
        <ConfirmModal
          message={confirmation.message}
          detail={confirmation.detail}
          confirmLabel={confirmation.confirmLabel || 'Confirmer'}
          variant={confirmation.variante || 'danger'}
          onCancel={() => setConfirmation(null)}
          onConfirm={async () => { await confirmation.action(); setConfirmation(null) }}
        />
      )}
    </div>
  )
}
