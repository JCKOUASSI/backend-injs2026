import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import api from '../services/api'
import { useToast } from '../context/ToastContext'
import { useAuth } from '../context/AuthContext'
import ConfirmModal from '../components/ConfirmModal'
import DeplacerSeance from '../components/edt/DeplacerSeance'
import AnnulerSeance from '../components/edt/AnnulerSeance'
import {
  ROLES_PLANIFICATION, ROLES_VALIDATION,
  construireMatriceGrille, classeBadgeStatut, formatDuree, formatHeure,
  libelleJour, libelleStatut, LIBELLES_CONFLITS, LIBELLES_NATURES,
  messageErreurApi, lireMutationAffectation,
} from '../utils/edts'
import '../styles/edts.css'

const NATURES = Object.keys(LIBELLES_NATURES)

const JOURS_GRILLE = ['LUNDI', 'MARDI', 'MERCREDI', 'JEUDI', 'VENDREDI', 'SAMEDI']

/** Pastilles de nature aux couleurs INJS (bleu foncé → bleu clair). */
const CLASSES_NATURES = {
  CM: 'nat-cm', COURS: 'nat-cm', TD: 'nat-td', TP: 'nat-tp',
  EVALUATION: 'nat-eval', REMPLACEMENT: 'nat-autre', AUTRE: 'nat-autre',
}

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
  const [filtreFiliere, setFiltreFiliere] = useState('')
  const [filtreFormation, setFiltreFormation] = useState('')
  const [filtreNiveau, setFiltreNiveau] = useState('')
  const [filtreSemestre, setFiltreSemestre] = useState('')
  const [filtreGroupe, setFiltreGroupe] = useState('')
  const [formationsRef, setFormationsRef] = useState([])
  const [niveauxRef, setNiveauxRef] = useState([])
  const [recherche, setRecherche] = useState(searchParams.get('q') || '')
  const [selectedId, setSelectedId] = useState(Number(searchParams.get('selection')) || null)
  const [detail, setDetail] = useState(null)
  const [affectations, setAffectations] = useState([])
  const [grille, setGrille] = useState({ jours: [] })
  const [conflits, setConflits] = useState([])
  const [chargementDetail, setChargementDetail] = useState(false)
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
        const [anneesRes, creneauxRes, enseignantsRes, formationsRes, niveauxRes] = await Promise.all([
          api.get('/scolarite/ref/annees/').catch(() => null),
          api.get('/edts/creneaux-types/').catch(() => null),
          api.get('/edts/referentiel-enseignants/').catch(() => null),
          api.get('/formations/ref/formations/').catch(() => null),
          api.get('/scolarite/ref/niveaux/').catch(() => null),
        ])
        if (!actif) return
        if (anneesRes) setAnnees(Array.isArray(anneesRes.data) ? anneesRes.data : (anneesRes.data?.results ?? []))
        if (creneauxRes) setCreneaux(Array.isArray(creneauxRes.data) ? creneauxRes.data : [])
        if (enseignantsRes) setEnseignants(Array.isArray(enseignantsRes.data) ? enseignantsRes.data : [])
        if (formationsRes) setFormationsRef(Array.isArray(formationsRes.data) ? formationsRes.data : (formationsRes.data?.results ?? []))
        if (niveauxRes) setNiveauxRef(Array.isArray(niveauxRes.data) ? niveauxRes.data : (niveauxRes.data?.results ?? []))
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
    chargerDetail(selectedId, semaine)
  }, [selectedId, semaine, chargerDetail])

  const edtsAffiches = edts
  const selectedEdt = useMemo(
    () => edtsAffiches.find((e) => e.id === selectedId) || detail,
    [edtsAffiches, selectedId, detail],
  )
  const gele = selectedEdt ? ['VALIDE', 'PUBLIE', 'ARCHIVE', 'EN_VALIDATION'].includes(selectedEdt.statut) : true
  // Modales de modification réglementée (déplacement revalidé / annulation motivée).
  const [aDeplacer, setADeplacer] = useState(null)
  const [aAnnuler, setAAnnuler] = useState(null)
  const [aReactiver, setAReactiver] = useState(null)
  const modifiable = peutPlanifier && !gele
  const nbSemaines = selectedEdt ? (selectedEdt.semaine_fin || 1) - (selectedEdt.semaine_debut || 1) + 1 : 0

  // ── Exploitation (maquette validée) : filtres référentiels et séances ──
  const filieresRef = useMemo(
    () => [...new Set(formationsRef.map((f) => f.filiere_code).filter(Boolean))].sort(),
    [formationsRef],
  )
  const formationsFiltrees = useMemo(
    () => (filtreFiliere
      ? formationsRef.filter((f) => f.filiere_code === filtreFiliere)
      : formationsRef),
    [formationsRef, filtreFiliere],
  )
  const edtsFiltres = useMemo(() => {
    const idsFormations = filtreFiliere
      ? new Set(formationsFiltrees.map((f) => f.id)) : null
    return edts.filter((e) => {
      if (filtreFormation) {
        return e.population_type === 'FORMATION'
          && String(e.population_id) === String(filtreFormation)
      }
      if (idsFormations && e.population_type === 'FORMATION') {
        return idsFormations.has(e.population_id)
      }
      return true
    })
  }, [edts, filtreFormation, filtreFiliere, formationsFiltrees])

  const seanceVisible = useCallback((contexte) => {
    if (!filtreNiveau && !filtreSemestre && !filtreGroupe) return true
    if (!contexte) return false
    if (filtreNiveau && contexte.niveau !== filtreNiveau) return false
    if (filtreSemestre && contexte.semestre !== filtreSemestre) return false
    if (filtreGroupe && contexte.groupe !== filtreGroupe) return false
    return true
  }, [filtreNiveau, filtreSemestre, filtreGroupe])

  const affectationsFiltrees = useMemo(
    () => affectations.filter((a) => seanceVisible(a.contexte)),
    [affectations, seanceVisible],
  )
  const grilleFiltree = useMemo(() => ({
    ...grille,
    jours: (grille.jours || []).map((j) => ({
      ...j,
      creneaux: (j.creneaux || []).map((c) => ({
        ...c,
        affectations: (c.affectations || []).filter((a) => seanceVisible(a.contexte)),
      })).filter((c) => c.affectations.length > 0),
    })).filter((j) => j.creneaux.length > 0),
  }), [grille, seanceVisible])
  const matriceExploit = useMemo(
    () => construireMatriceGrille(grilleFiltree, conflits),
    [grilleFiltree, conflits],
  )
  const groupesSeances = useMemo(
    () => [...new Set(affectations.map((a) => a.contexte?.groupe).filter(Boolean))].sort(),
    [affectations],
  )
  const comptesNatures = useMemo(() => {
    const comptes = {}
    for (const a of affectationsFiltrees) comptes[a.nature] = (comptes[a.nature] || 0) + 1
    return comptes
  }, [affectationsFiltrees])
  const placesCouvertes = useMemo(
    () => affectationsFiltrees.reduce((t, a) => t + (a.contexte?.effectif || 0), 0),
    [affectationsFiltrees],
  )
  const semestreAffiche = useMemo(() => {
    if (filtreSemestre) return filtreSemestre
    const comptes = {}
    for (const a of affectationsFiltrees) {
      if (a.contexte?.semestre) comptes[a.contexte.semestre] = (comptes[a.contexte.semestre] || 0) + 1
    }
    const dominant = Object.entries(comptes).sort((x, y) => y[1] - x[1])[0]
    return dominant ? dominant[0] : null
  }, [affectationsFiltrees, filtreSemestre])

  const reinitialiserFiltres = () => {
    setFiltreAnnee(''); setFiltreStatut(''); setRecherche('')
    setFiltreFiliere(''); setFiltreFormation('')
    setFiltreNiveau(''); setFiltreSemestre(''); setFiltreGroupe('')
  }
  const appliquerFiltres = () => {
    chargerListe()
    if (edtsFiltres.length && !edtsFiltres.some((e) => e.id === selectedId)) {
      selectionner(edtsFiltres[0].id)
    }
  }

  const action = async (chemin, corps, succesMessage, apresRechargement = true) => {
    setBusy(true)
    try {
      await api.post(chemin, corps || {})
      showToast(succesMessage)
      if (apresRechargement) {
        await chargerListe()
        await chargerDetail(selectedId, semaine)
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
      await chargerDetail(selectedId, semaine)
      await chargerListe()
    } catch (err) {
      showToast(messageErreurApi(err, 'Échec de la détection'), 'error')
    } finally {
      setBusy(false)
    }
  }

  /**
   * Exports de l'emploi du temps (LOT 9) : CSV, XLSX, PDF.
   *
   * Les trois documents sont produits par le serveur à partir de la même
   * donnée (séances actives, filtres courants) : l'interface ne recompose
   * jamais le contenu, ce qui garantit que l'imprimé et l'écran ne divergent
   * pas. Un refus serveur (404, 403) s'affiche comme une erreur, pas comme un
   * fichier vide.
   */
  const exporter = async (format) => {
    const suffixe = semaine ? `?semaine=${semaine}` : ''
    const chemin = format === 'csv'
      ? `/edts/emplois/${selectedId}/export.csv/`
      : `/edts/lmd/${selectedId}/export.${format}/${suffixe}`
    const libelle = { csv: 'CSV', xlsx: 'Excel', pdf: 'PDF' }[format]
    try {
      const { blob, fileName } = await api.getBlob(chemin)
      const url = URL.createObjectURL(blob)
      const lien = document.createElement('a')
      lien.href = url
      lien.download = fileName || `edt-${selectedId}.${format}`
      document.body.appendChild(lien)
      lien.click()
      lien.remove()
      URL.revokeObjectURL(url)
      showToast(`Export ${libelle} téléchargé`)
    } catch (err) {
      showToast(messageErreurApi(err, `Export ${libelle} impossible`), 'error')
    }
  }

  const basculerAffectation = async (aff) => {
    try {
      await api.patch(`/edts/affectations/${aff.id}/`, { actif: !aff.actif })
      showToast(aff.actif ? 'Créneau désactivé' : 'Créneau réactivé')
      chargerDetail(selectedId, semaine)
    } catch (err) {
      showToast(messageErreurApi(err, 'Modification refusée'), 'error')
    }
  }

  const demanderConfirmation = (config) => setConfirmation(config)

  return (
    <div className="container-fluid pb-5 edt-page">
      <div className="edt-exploit-entete edt-no-print">
        <div>
          <span className="edt-exploit-sur">Exploitation</span>
          <h2 className="edt-exploit-titre">Emplois du temps</h2>
          <p className="edt-exploit-sous">
            Grille hebdomadaire par filière, formation, groupe et semestre.
            Les cours magistraux sont mutualisés à l’échelle de la promotion ;
            les TD et TP sont propres à chaque groupe.
          </p>
        </div>
        <div className="edt-exploit-actions">
          <Link to="/edt/conflits" className="btn btn-outline-danger">
            <i className="bi bi-exclamation-octagon"></i> Conflits globaux
          </Link>
          <Link to="/edt/salles-espaces" className="btn btn-outline-secondary">
            <i className="bi bi-door-open"></i> Salles
          </Link>
          {peutPlanifier && (
            <Link to="/edt/nouveau" className="btn btn-outline-primary">
              <i className="bi bi-plus-circle"></i> Nouvel EDT
            </Link>
          )}
          <button type="button" className="btn btn-dark" disabled={!selectedId}
                  onClick={() => exporter('csv')}>
            <i className="bi bi-filetype-csv"></i> Exporter CSV
          </button>
          <button type="button" className="btn btn-outline-secondary" disabled={!selectedId}
                  onClick={() => window.print()}>
            <i className="bi bi-printer"></i> Imprimer la grille
          </button>
        </div>
      </div>

      <div className="card mb-3 edt-filtres edt-no-print">
        <div className="card-body">
          <div className="row g-2 align-items-end">
            <div className="col-md-2">
              <label className="form-label edt-filtre-label" htmlFor="filtre-annee">Année académique</label>
              <select id="filtre-annee" className="form-select form-select-sm" value={filtreAnnee}
                      onChange={(e) => setFiltreAnnee(e.target.value)}>
                <option value="">Toutes</option>
                {annees.map((a) => <option key={a.id} value={a.id}>{a.libelle}</option>)}
              </select>
            </div>
            <div className="col-md-2">
              <label className="form-label edt-filtre-label" htmlFor="filtre-filiere">Filière</label>
              <select id="filtre-filiere" className="form-select form-select-sm" value={filtreFiliere}
                      onChange={(e) => { setFiltreFiliere(e.target.value); setFiltreFormation('') }}>
                <option value="">Toutes</option>
                {filieresRef.map((code) => <option key={code} value={code}>{code}</option>)}
              </select>
            </div>
            <div className="col-md-3">
              <label className="form-label edt-filtre-label" htmlFor="filtre-formation">Formation</label>
              <select id="filtre-formation" className="form-select form-select-sm" value={filtreFormation}
                      onChange={(e) => setFiltreFormation(e.target.value)}>
                <option value="">Toutes</option>
                {formationsFiltrees.map((f) => <option key={f.id} value={f.id}>{f.intitule}</option>)}
              </select>
            </div>
            <div className="col-md-1">
              <label className="form-label edt-filtre-label" htmlFor="filtre-niveau">Niveau</label>
              <select id="filtre-niveau" className="form-select form-select-sm" value={filtreNiveau}
                      onChange={(e) => setFiltreNiveau(e.target.value)}>
                <option value="">Tout</option>
                {niveauxRef.map((n) => <option key={n.id} value={n.code}>{n.code}</option>)}
              </select>
            </div>
            <div className="col-md-2">
              <label className="form-label edt-filtre-label" htmlFor="filtre-groupe">Groupe</label>
              <select id="filtre-groupe" className="form-select form-select-sm" value={filtreGroupe}
                      onChange={(e) => setFiltreGroupe(e.target.value)}>
                <option value="">Tous</option>
                {groupesSeances.map((g) => <option key={g} value={g}>{g}</option>)}
              </select>
            </div>
            <div className="col-md-1">
              <label className="form-label edt-filtre-label" htmlFor="filtre-semestre">Semestre</label>
              <select id="filtre-semestre" className="form-select form-select-sm" value={filtreSemestre}
                      onChange={(e) => setFiltreSemestre(e.target.value)}>
                <option value="">Tous</option>
                {['S1', 'S2', 'S3', 'S4', 'S5', 'S6', 'S7', 'S8', 'S9', 'S10'].map((sem) => (
                  <option key={sem} value={sem}>{sem}</option>
                ))}
              </select>
            </div>
            <div className="col-md-1 d-grid">
              <button type="button" className="btn btn-sm btn-primary" onClick={appliquerFiltres}>
                Afficher
              </button>
            </div>
          </div>
          <div className="row g-2 align-items-end mt-1">
            <div className="col-md-3">
              <label className="form-label edt-filtre-label" htmlFor="filtre-statut">Statut</label>
              <select id="filtre-statut" className="form-select form-select-sm" value={filtreStatut}
                      onChange={(e) => setFiltreStatut(e.target.value)}>
                <option value="">Tous</option>
                {['BROUILLON', 'EN_VALIDATION', 'VALIDE', 'PUBLIE', 'ARCHIVE'].map((st) => (
                  <option key={st} value={st}>{libelleStatut(st)}</option>
                ))}
              </select>
            </div>
            <div className="col-md-6">
              <label className="form-label edt-filtre-label" htmlFor="filtre-recherche">Recherche</label>
              <input id="filtre-recherche" className="form-control form-control-sm"
                     placeholder="Titre ou population…"
                     value={recherche} onChange={(e) => setRecherche(e.target.value)} />
            </div>
            <div className="col-md-3 text-md-end">
              <button type="button" className="btn btn-link btn-sm edt-reinit" onClick={reinitialiserFiltres}>
                Réinitialiser les filtres
              </button>
            </div>
          </div>
          <div className="edt-chips-ligne">
            <span className="edt-chips-label">Emplois du temps disponibles</span>
            <div className="edt-chips" role="listbox" aria-label="Emplois du temps">
              {loading ? (
                <span className="text-muted small">Chargement…</span>
              ) : edtsFiltres.length === 0 ? (
                <span className="text-muted small">Aucun emploi du temps pour ces filtres.</span>
              ) : edtsFiltres.map((edt) => (
                <button key={edt.id} type="button" role="option" aria-selected={selectedId === edt.id}
                        className={`edt-chip ${selectedId === edt.id ? 'active' : ''}`}
                        onClick={() => selectionner(edt.id)}
                        title={edt.titre || edt.population_label}>
                  {edt.titre || edt.population_label}
                </button>
              ))}
            </div>
            <span className="edt-resume">
              <span className="edt-resume-item">{affectationsFiltrees.length} séance(s)</span>
              <span className="edt-resume-item">
                {Object.entries(comptesNatures).map(([n, c]) => `${n} : ${c}`).join(' · ') || '—'}
              </span>
              <span className="edt-resume-item">{placesCouvertes} places couvertes</span>
            </span>
          </div>
        </div>
      </div>

      <div className="edt-exploit-main">
        <div>
          {!selectedId ? (
            <div className="card edt-empty-panel"><div className="card-body text-center py-5 text-muted">
              <i className="bi bi-calendar-week fs-1 d-block mb-3" />Sélectionnez un emploi du temps.
            </div></div>
          ) : (
            <>
              <div className="card mb-3 edt-detail edt-no-print">
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
                    {nbSemaines > 0 && (
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
                    <button className="btn btn-sm btn-outline-dark" onClick={detecterConflits} disabled={busy}>
                      <i className="bi bi-search" /> Détection
                    </button>
                    {modifiable && (
                      <Link to={`/edt/${selectedId}/affectation/nouveau${semaine ? `?semaine=${semaine}` : ''}`}
                            className="btn btn-sm btn-outline-primary">
                        <i className="bi bi-plus-circle" /> Créneau
                      </Link>
                    )}
                    <button className="btn btn-sm btn-outline-success" onClick={() => exporter('csv')}>
                      <i className="bi bi-filetype-csv" /> Export
                    </button>
                    <button className="btn btn-sm btn-outline-secondary" onClick={() => exporter('xlsx')}
                            title="Tableau Excel des séances (mêmes filtres que l'écran)">
                      <i className="bi bi-filetype-xlsx" /> Excel
                    </button>
                    <button className="btn btn-sm btn-outline-secondary" onClick={() => exporter('pdf')}
                            title="Grille imprimable (PDF) générée côté serveur">
                      <i className="bi bi-filetype-pdf" /> PDF
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
              ) : (
                <>
                  <div className="card mb-3 edt-panel edt-grille-card">
                    <div className="card-header edt-panel-head">
                      <span className="edt-panel-title">
                        <i className="bi bi-grid-3x3" /> Grille hebdomadaire{semestreAffiche ? ` — Semestre ${semestreAffiche.replace('S', '')}` : ''}
                      </span>
                      <span className="edt-legende">
                        <span className="edt-legende-item"><span className="edt-nat nat-cm">CM</span> Cours magistral</span>
                        <span className="edt-legende-item"><span className="edt-nat nat-td">TD</span> Travaux dirigés</span>
                        <span className="edt-legende-item"><span className="edt-nat nat-tp">TP</span> Travaux pratiques</span>
                        <span className={`edt-count-pill ${conflits.length ? 'is-danger' : ''}`}>{conflits.length} conflit(s)</span>
                      </span>
                    </div>
                    <div className="table-responsive">
                      {matriceExploit.length === 0 ? (
                        <div className="text-center text-muted py-5">
                          <i className="bi bi-calendar-x fs-1 d-block mb-2" />
                          Aucun créneau occupé {semaine ? `en semaine ${semaine}` : ''} pour ces filtres.
                        </div>
                      ) : (
                        <table className="table align-top mb-0 edt-grille-table">
                          <thead>
                            <tr>
                              <th className="edt-grille-creneau-th">Créneau</th>
                              {JOURS_GRILLE.map((jour) => {
                                const colonne = matriceExploit.find((c) => c.jour === jour)
                                return <th key={jour}>{colonne?.libelle || libelleJour(jour)}</th>
                              })}
                            </tr>
                          </thead>
                          <tbody>
                            {(() => {
                              const colonnes = JOURS_GRILLE.map((jour) => (
                                matriceExploit.find((c) => c.jour === jour)
                                || { jour, libelle: libelleJour(jour), lignes: [] }
                              ))
                              const plages = [...new Set(colonnes.flatMap((col) => col.lignes.map((c) => `${c.heure_debut}-${c.heure_fin}`)))].sort()
                              return plages.map((plage, indexPlage) => (
                                <tr key={plage}>
                                  <td className="edt-grille-creneau-td">
                                    <span className="edt-grille-creneau-code">Créneau {indexPlage + 1}</span>
                                    <span className="edt-grille-creneau-heure">{formatHeure(plage.split('-')[0])} – {formatHeure(plage.split('-')[1])}</span>
                                  </td>
                                  {colonnes.map((col) => {
                                    const cellule = col.lignes.find((c) => `${c.heure_debut}-${c.heure_fin}` === plage)
                                    return (
                                      <td key={col.jour} className={cellule?.enConflit ? 'edt-cellule-conflit' : ''}>
                                        {cellule ? cellule.affectations.map((a) => (
                                          <div key={a.id} className="edt-seance">
                                            <div className="edt-seance-haut">
                                              <span className={`edt-nat ${CLASSES_NATURES[a.nature] || 'nat-autre'}`}>{a.nature}</span>
                                              {[a.contexte?.ue, a.contexte?.ecue].filter(Boolean).length > 0 && (
                                                <span className="edt-seance-code">{[a.contexte?.ue, a.contexte?.ecue].filter(Boolean).join(' · ')}</span>
                                              )}
                                            </div>
                                            <div className="edt-seance-titre">{a.intitule || '—'}</div>
                                            <div className="edt-seance-meta">
                                              {[a.contexte?.enseignant || a.enseignant_nom,
                                                a.contexte?.groupe || a.groupe,
                                                a.salle_nom].filter(Boolean).join(' · ')}
                                            </div>
                                            {modifiable && (
                                              <div className="edt-seance-actions">
                                                <button type="button" className="btn btn-sm btn-outline-primary py-0 px-1"
                                                        title="Déplacer (revalidation C1→C10)"
                                                        onClick={() => setADeplacer(a)}>
                                                  <i className="bi bi-arrows-move" />
                                                </button>
                                                <button type="button" className="btn btn-sm btn-outline-danger py-0 px-1"
                                                        title="Annuler la séance (motif requis)"
                                                        onClick={() => setAAnnuler(a)}>
                                                  <i className="bi bi-slash-circle" />
                                                </button>
                                              </div>
                                            )}
                                          </div>
                                        )) : <span className="text-muted">—</span>}
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

                  <div className="card mb-3 edt-panel" id="edt-detail-seances">
                    <div className="card-header edt-panel-head">
                      <span className="edt-panel-title"><i className="bi bi-table" /> Détail des séances</span>
                      <span className="edt-count-pill">{affectationsFiltrees.length} ligne(s) affichée(s)</span>
                    </div>
                    <p className="edt-detail-sous">Vue tabulaire exploitable par la scolarité et les enseignants.</p>
                    <div className="table-responsive">
                      <table className="table table-hover align-middle mb-0 edt-table edt-detail-table">
                        <thead>
                          <tr>
                            <th>Semestre</th><th>Jour</th><th>Horaire</th><th>Type</th><th>Module</th>
                            <th>Groupe</th><th>Salle</th><th>Enseignant</th><th>Effectif</th>
                            <th className="text-end">Actions</th>
                          </tr>
                        </thead>
                        <tbody>
                          {affectationsFiltrees.length === 0 ? (
                            <tr><td colSpan="10" className="text-center text-muted py-4">Aucune séance active pour ces filtres.</td></tr>
                          ) : affectationsFiltrees.map((aff) => (
                            <tr key={aff.id} className={conflits.some((c) => (c.lignes_creneaux || []).includes(aff.id)) ? 'table-warning' : ''}>
                              <td>{aff.contexte?.semestre || <span className="text-muted">—</span>}</td>
                              <td>{aff.creneau ? libelleJour(aff.creneau.jour) : <span className="text-muted">—</span>}</td>
                              <td className="text-nowrap">{aff.creneau ? `${formatHeure(aff.creneau.heure_debut)} – ${formatHeure(aff.creneau.heure_fin)}` : '—'}</td>
                              <td><span className={`edt-nat ${CLASSES_NATURES[aff.nature] || 'nat-autre'}`}>{aff.nature}</span></td>
                              <td>
                                {[aff.contexte?.ue, aff.contexte?.ecue].filter(Boolean).length > 0 && (
                                  <span className="edt-seance-code d-block">{[aff.contexte?.ue, aff.contexte?.ecue].filter(Boolean).join(' · ')}</span>
                                )}
                                {aff.intitule || <span className="text-muted">—</span>}
                                {aff.commentaire && <div className="small text-muted">{aff.commentaire}</div>}
                              </td>
                              <td>{aff.contexte?.groupe || aff.groupe || <span className="text-muted">—</span>}</td>
                              <td>{aff.salle_nom || <span className="text-muted">—</span>}</td>
                              <td>{aff.contexte?.enseignant || aff.enseignant_nom || <span className="text-muted">—</span>}</td>
                              <td>{aff.contexte?.effectif ?? <span className="text-muted">—</span>}</td>
                              <td className="text-end text-nowrap">
                                {modifiable ? (
                                  <>
                                    <button className="btn btn-sm btn-outline-primary me-1" title="Modifier" onClick={() => setEdition(aff)}>
                                      <i className="bi bi-pencil" />
                                    </button>
                                    <button className="btn btn-sm btn-outline-info me-1"
                                            title="Déplacer (revalidation C1→C10 par le serveur)"
                                            onClick={() => setADeplacer(aff)}>
                                      <i className="bi bi-arrows-move" />
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
                                                  chargerDetail(selectedId, semaine)
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
                </>
              )}

              <div className="card edt-panel edt-no-print">
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
                                          chargerDetail(selectedId, semaine)
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

      <p className="edt-pied edt-no-print">
        GET INJS APP — module intégré à INJS2026 · Institut National de la
        Jeunesse et des Sports (INJS) — Marcory · Moteur LMD déterministe
      </p>

      {aDeplacer && (
        <DeplacerSeance
          affectation={aDeplacer}
          onClose={() => setADeplacer(null)}
          onMoved={() => {
            setADeplacer(null)
            showToast('Séance déplacée : position revalidée C1→C10')
            chargerDetail(selectedId, semaine)
          }}
        />
      )}
      {(aAnnuler || aReactiver) && (
        <AnnulerSeance
          affectation={aAnnuler || aReactiver}
          reactiver={!!aReactiver}
          onClose={() => { setAAnnuler(null); setAReactiver(null) }}
          onDone={() => {
            const reactivee = !!aReactiver
            setAAnnuler(null)
            setAReactiver(null)
            showToast(reactivee ? 'Séance réactivée' : 'Séance annulée (motif journalisé)')
            chargerDetail(selectedId, semaine)
          }}
        />
      )}

      {edition && (
        <ModalEditionAffectation
          affectation={edition}
          creneaux={creneaux}
          enseignants={enseignants}
          onClose={() => setEdition(null)}
          onSaved={() => { setEdition(null); chargerDetail(selectedId, semaine); chargerListe() }}
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
