import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import api from '../../services/api'
import ConfirmModal from '../../components/ConfirmModal'
import { canActScolarite } from '../../utils/roles'
import { useAuth } from '../../context/AuthContext'
import { useToast } from '../../context/ToastContext'
import '../../styles/candidatures.css'
import '../../styles/maquettes.css'

const STATUTS = [
  { value: '', label: 'Tous les statuts' },
  { value: 'BROUILLON', label: 'Brouillons' },
  { value: 'VALIDEE', label: 'Validées' },
  { value: 'ACTIVE', label: 'Actives' },
  { value: 'ARCHIVEE', label: 'Archivées' },
]

const BADGE_STATUT = {
  BROUILLON: 'secondary',
  VALIDEE: 'info',
  ACTIVE: 'success',
  ARCHIVEE: 'dark',
}

const ICONE_STATUT = {
  BROUILLON: 'bi-pencil-square',
  VALIDEE: 'bi-lock',
  ACTIVE: 'bi-check2-circle',
  ARCHIVEE: 'bi-archive',
}

/** Étapes du cycle de validation, dans l'ordre du workflow. */
const ETAPES = [
  { value: 'BROUILLON', label: 'Brouillon', icone: 'bi-pencil-square', ton: 'amber', aide: 'Modifiable' },
  { value: 'VALIDEE', label: 'Validée', icone: 'bi-lock', ton: 'blue', aide: 'Contenu gelé' },
  { value: 'ACTIVE', label: 'Active', icone: 'bi-lightning-charge', ton: 'green', aide: 'Applicable, immuable' },
  { value: 'ARCHIVEE', label: 'Archivée', icone: 'bi-archive', ton: 'slate', aide: 'Historique' },
]

const NIVEAUX_MATRICE = ['L1', 'L2', 'L3', 'M1', 'M2']

/** Formats d'export proposés sous la liste (ordre : Word, PDF, Excel, CSV). */
const FORMATS_EXPORT = [
  { valeur: 'docx', libelle: 'Export Word', icone: 'bi-file-earmark-word', ton: 'word' },
  { valeur: 'pdf', libelle: 'Export PDF', icone: 'bi-file-earmark-pdf', ton: 'pdf' },
  { valeur: 'xlsx', libelle: 'Export Excel', icone: 'bi-file-earmark-excel', ton: 'excel' },
  { valeur: 'csv', libelle: 'Export CSV', icone: 'bi-file-earmark-text', ton: 'csv' },
]

/** Extensions acceptées par chaque bouton d'import. */
const FORMATS_IMPORT = [
  { valeur: 'xlsx', libelle: 'Importer Excel', accept: '.xlsx,.xlsm', icone: 'bi-file-earmark-excel' },
  { valeur: 'csv', libelle: 'Importer CSV', accept: '.csv', icone: 'bi-file-earmark-text' },
]

/** Déclenche le téléchargement d'un blob (nom fourni par le serveur). */
function telechargerBlob(blob, nom) {
  const url = URL.createObjectURL(blob)
  const lien = document.createElement('a')
  lien.href = url
  lien.download = nom || 'export'
  document.body.appendChild(lien)
  lien.click()
  lien.remove()
  URL.revokeObjectURL(url)
}
const CREDITS_PAR_NIVEAU = 60

/** « Licence 2 » → « L2 », « Master 1 » → « M1 », sinon le code tel quel. */
const codeNiveau = (niveau) => {
  const texte = (niveau || '').trim()
  const licence = texte.match(/^(?:licence|l)\s*([1-3])$/i)
  if (licence) return `L${licence[1]}`
  const master = texte.match(/^(?:master|m)\s*([1-2])$/i)
  if (master) return `M${master[1]}`
  return texte.toUpperCase()
}

/** « ÉDUCATION ET MOTRICITÉ — LICENCE » → « ÉDUCATION ET MOTRICITÉ ». */
const baseFormation = (intitule) => (intitule || '').split(/\s+—\s+/)[0].trim()

const formatNombre = (n) => Number(n || 0).toLocaleString('fr-FR')

export default function Maquettes() {
  const { user } = useAuth()
  const toast = useToast()
  const navigate = useNavigate()
  const peutAgir = canActScolarite(user)

  const [maquettes, setMaquettes] = useState([])
  const [chargement, setChargement] = useState(true)
  const [filtreStatut, setFiltreStatut] = useState('')
  const [filtreFormation, setFiltreFormation] = useState('')
  const [recherche, setRecherche] = useState('')
  const [enCours, setEnCours] = useState(false)
  const [form, setForm] = useState({
    annee_academique_id: '', ref_formation_id: '', niveau_id: '', libelle: '',
  })
  const [options, setOptions] = useState({ annees: [], formations: [], niveaux: [] })

  // ── Sélection (conservée lors des filtres, de la recherche et des exports) ──
  const [selection, setSelection] = useState([])
  const sectionCreationRef = useRef(null)
  const champAnneeRef = useRef(null)
  const toutRef = useRef(null)
  const fichierRef = useRef(null)
  const formatCourantRef = useRef('xlsx')
  // Fichier réellement choisi : conservé pour rejouer l'import (mode
  // « importer ») après l'analyse, sans redemander le fichier à l'utilisateur.
  const fichierChoisiRef = useRef(null)

  // ── Export / import ──
  const [exportEnCours, setExportEnCours] = useState('')
  const [avecDetail, setAvecDetail] = useState(false)
  const [importEnCours, setImportEnCours] = useState(false)
  const [analyseImport, setAnalyseImport] = useState(null)
  const [rapportImport, setRapportImport] = useState(null)
  const [erreurImport, setErreurImport] = useState('')

  // ── Modification / suppression ──
  const [edition, setEdition] = useState(null)
  const [editionEnCours, setEditionEnCours] = useState(false)
  const [suppression, setSuppression] = useState(null)
  const [bilanSuppression, setBilanSuppression] = useState(null)

  const charger = useCallback(async () => {
    setChargement(true)
    try {
      const params = {}
      if (filtreStatut) params.statut = filtreStatut
      const res = await api.get('/scolarite/maquettes/', { params })
      setMaquettes(res.data)
    } catch (err) {
      toast.showToast(err.response?.data?.error || 'Chargement des maquettes impossible.', 'error')
    } finally {
      setChargement(false)
    }
  }, [filtreStatut, toast])

  useEffect(() => { charger() }, [charger])

  useEffect(() => {
    if (!peutAgir) return
    ;(async () => {
      try {
        const [annees, formations, niveaux] = await Promise.all([
          api.get('/scolarite/ref/annees/', { params: { actif: 'true' } }),
          api.get('/scolarite/ref/formations/'),
          api.get('/scolarite/ref/niveaux/', { params: { actif: 'true' } }),
        ])
        setOptions({ annees: annees.data, formations: formations.data, niveaux: niveaux.data })
      } catch {
        toast.showToast('Chargement des référentiels impossible.', 'error')
      }
    })()
  }, [peutAgir, toast])

  const creer = async (e) => {
    e.preventDefault()
    setEnCours(true)
    try {
      const res = await api.post('/scolarite/maquettes/creer/', {
        ...form,
        annee_academique_id: Number(form.annee_academique_id) || undefined,
        ref_formation_id: Number(form.ref_formation_id) || undefined,
        niveau_id: Number(form.niveau_id) || undefined,
      })
      toast.showToast(`Maquette v${res.data.version} créée en brouillon.`)
      setForm({ annee_academique_id: '', ref_formation_id: '', niveau_id: '', libelle: '' })
      charger()
    } catch (err) {
      toast.showToast(err.response?.data?.error || 'Création impossible.', 'error')
    } finally {
      setEnCours(false)
    }
  }

  const action = async (maquette, verbe, confirmation) => {
    if (confirmation && !window.confirm(confirmation)) return
    setEnCours(true)
    try {
      const res = await api.post(`/scolarite/maquettes/${maquette.id}/${verbe}/`, {})
      toast.showToast(res.data?.detail || 'Opération effectuée.')
      charger()
    } catch (err) {
      const problemes = err.response?.data?.problemes
      toast.showToast(
        problemes?.length ? problemes.join(' ') : (err.response?.data?.error || 'Action impossible.'),
        'error',
      )
    } finally {
      setEnCours(false)
    }
  }

  /** Validation en lot : ventilation ECUE + gel de tous les brouillons cohérents. */
  const validerTout = async () => {
    if (!window.confirm('Valider toutes les maquettes en brouillon (contenu gelé) ?')) return
    setEnCours(true)
    try {
      const res = await api.post('/scolarite/maquettes/valider-toutes/', {})
      const echecs = res.data?.echecs || []
      toast.showToast(res.data?.detail || 'Validation en lot terminée.')
      if (echecs.length) {
        toast.showToast(
          `${echecs.length} maquette(s) en échec : ouvrez le détail pour corriger les incohérences.`,
          'error',
        )
      }
      charger()
    } catch (err) {
      toast.showToast(err.response?.data?.error || 'Validation en lot impossible.', 'error')
    } finally {
      setEnCours(false)
    }
  }

  // Indicateurs de la vue courante (la liste est déjà filtrée côté serveur).
  const stats = useMemo(() => {
    const total = maquettes.length
    const actives = maquettes.filter((m) => m.statut === 'ACTIVE').length
    const validees = maquettes.filter((m) => m.statut === 'VALIDEE').length
    const brouillons = maquettes.filter((m) => m.statut === 'BROUILLON').length
    const archivees = maquettes.filter((m) => m.statut === 'ARCHIVEE').length
    const credits = maquettes.reduce((somme, m) => somme + (m.total_credits || 0), 0)
    const finalisees = actives + validees
    return {
      total, actives, validees, brouillons, archivees, credits,
      pctFinalisees: total ? Math.round((finalisees / total) * 100) : 0,
    }
  }, [maquettes])

  const parStatut = useMemo(
    () => ({
      BROUILLON: stats.brouillons,
      VALIDEE: stats.validees,
      ACTIVE: stats.actives,
      ARCHIVEE: stats.archivees,
    }),
    [stats],
  )

  // Formations présentes dans la vue, pour le filtre local.
  const formationsPresentes = useMemo(() => {
    const compte = new Map()
    for (const m of maquettes) {
      if (m.ref_formation) compte.set(m.ref_formation, (compte.get(m.ref_formation) || 0) + 1)
    }
    return [...compte.entries()].sort((a, b) => a[0].localeCompare(b[0], 'fr'))
  }, [maquettes])

  // Filtrage local : formation + recherche textuelle.
  const maquettesFiltrees = useMemo(() => {
    let liste = maquettes
    if (filtreFormation) liste = liste.filter((m) => m.ref_formation === filtreFormation)
    if (recherche.trim()) {
      const q = recherche.toLowerCase()
      liste = liste.filter(
        (m) =>
          (m.ref_formation || '').toLowerCase().includes(q) ||
          (m.niveau || '').toLowerCase().includes(q) ||
          (m.parcours || '').toLowerCase().includes(q) ||
          (m.annee_academique || '').toLowerCase().includes(q),
      )
    }
    return liste
  }, [maquettes, filtreFormation, recherche])

  // Matrice de couverture : filière (base de l'intitulé) × niveau L1–M2.
  const couverture = useMemo(() => {
    const groupes = new Map()
    for (const m of maquettesFiltrees) {
      const base = baseFormation(m.ref_formation)
      const code = codeNiveau(m.niveau)
      if (!base || !NIVEAUX_MATRICE.includes(code)) continue
      if (!groupes.has(base)) groupes.set(base, new Map())
      const parNiveau = groupes.get(base)
      if (!parNiveau.has(code)) parNiveau.set(code, [])
      parNiveau.get(code).push(m)
    }
    return [...groupes.entries()]
      .filter(([, parNiveau]) => [...parNiveau.values()].reduce((n, l) => n + l.length, 0) >= 2)
      .sort((a, b) => a[0].localeCompare(b[0], 'fr'))
  }, [maquettesFiltrees])

  const basculerStatut = (value) => setFiltreStatut((actuel) => (actuel === value ? '' : value))

  // ── Sélection ────────────────────────────────────────────────────────────
  const maquettesParId = useMemo(
    () => new Map(maquettes.map((m) => [m.id, m])),
    [maquettes],
  )
  const maquettesSelectionnees = useMemo(
    () => selection.map((id) => maquettesParId.get(id)).filter(Boolean),
    [selection, maquettesParId],
  )
  const toutVisibleSelectionne =
    maquettesFiltrees.length > 0 && maquettesFiltrees.every((m) => selection.includes(m.id))
  const selectionPartielle = maquettesSelectionnees.length > 0 && !toutVisibleSelectionne

  // Une sélection partielle doit être visible sur la case d'en-tête (état
  // « indéterminé » de HTML, non pilotable par attribut React).
  useEffect(() => {
    if (toutRef.current) toutRef.current.indeterminate = selectionPartielle
  }, [selectionPartielle])

  const basculerSelection = (id) => {
    setSelection((actuelle) => (
      actuelle.includes(id) ? actuelle.filter((element) => element !== id) : [...actuelle, id]
    ))
  }

  /** Case d'en-tête : sélectionne tout le visible, ou désélectionne tout. */
  const basculerTout = () => {
    if (toutVisibleSelectionne) {
      setSelection([])
      return
    }
    setSelection(maquettesFiltrees.map((m) => m.id))
  }

  // ── Panneau d'actions ────────────────────────────────────────────────────
  const allerVersCreation = () => {
    sectionCreationRef.current?.scrollIntoView?.({ behavior: 'smooth', block: 'start' })
    champAnneeRef.current?.focus?.()
  }

  const ouvrirVisualisation = () => {
    if (maquettesSelectionnees.length !== 1) return
    navigate(`/scolarite/maquettes/${maquettesSelectionnees[0].id}`)
  }

  const ouvrirEdition = async () => {
    const maquette = maquettesSelectionnees[0]
    if (maquettesSelectionnees.length !== 1 || !maquette) return
    setEdition({
      id: maquette.id,
      libelle: maquette.libelle || '',
      libelleAffiche: maquette.libelle,
      statut: maquette.statut,
      ref_formation_id: maquette.ref_formation_id,
      parcours_id: maquette.parcours_id || '',
      parcours: [],
      chargementParcours: true,
    })
    try {
      const res = await api.get('/scolarite/ref/parcours/', {
        params: { ref_formation_id: maquette.ref_formation_id },
      })
      const liste = Array.isArray(res.data) ? res.data : (res.data?.results || [])
      setEdition((actuel) => (actuel ? { ...actuel, parcours: liste, chargementParcours: false } : actuel))
    } catch {
      setEdition((actuel) => (actuel ? { ...actuel, chargementParcours: false } : actuel))
    }
  }

  const enregistrerEdition = async (evenement) => {
    evenement.preventDefault()
    if (!edition) return
    setEditionEnCours(true)
    try {
      await api.patch(`/scolarite/maquettes/${edition.id}/modifier/`, {
        libelle: edition.libelle,
        parcours_id: edition.parcours_id ? Number(edition.parcours_id) : null,
      })
      toast.showToast('Maquette modifiée.')
      setEdition(null)
      charger()
    } catch (err) {
      const data = err.response?.data
      const message = typeof data === 'string'
        ? data
        : (data?.error || data?.detail || Object.values(data || {})?.flat?.()?.join?.(' ') || 'Modification impossible.')
      toast.showToast(String(message), 'error')
    } finally {
      setEditionEnCours(false)
    }
  }

  // ── Suppression ──────────────────────────────────────────────────────────
  const demanderSuppression = () => {
    if (!maquettesSelectionnees.length) return
    setSuppression({ ids: maquettesSelectionnees.map((m) => m.id) })
  }

  const confirmerSuppression = async () => {
    if (!suppression) return
    const ids = suppression.ids
    setSuppression(null)
    setEnCours(true)
    try {
      const res = await api.post('/scolarite/maquettes/supprimer/', { ids })
      const bilan = res.data || {}
      const supprimees = bilan.supprimees || []
      const bloquees = bilan.bloquees || []
      if (supprimees.length) {
        toast.showToast(
          `${supprimees.length} maquette${supprimees.length > 1 ? 's' : ''} supprimée${supprimees.length > 1 ? 's' : ''}.`,
        )
      }
      if (bloquees.length) {
        setBilanSuppression(bilan)
        toast.showToast(
          `${bloquees.length} maquette${bloquees.length > 1 ? 's' : ''} non supprimée${bloquees.length > 1 ? 's' : ''} : voir le bilan.`,
          'error',
        )
      }
      setSelection((actuelle) => actuelle.filter((id) => !supprimees.some((s) => s.id === id)))
      charger()
    } catch (err) {
      const data = err.response?.data
      if (data?.bloquees || data?.introuvables) setBilanSuppression(data)
      toast.showToast(data?.error || 'Suppression impossible.', 'error')
      charger()
    } finally {
      setEnCours(false)
    }
  }

  // ── Export ───────────────────────────────────────────────────────────────
  const exporter = async (format) => {
    setExportEnCours(format)
    try {
      const params = new URLSearchParams()
      if (selection.length) {
        params.set('ids', selection.join(','))
      } else {
        // Aucune sélection : tout le périmètre courant (filtres de l'écran).
        if (filtreStatut) params.set('statut', filtreStatut)
        if (filtreFormation) {
          const reference = maquettes.find((m) => m.ref_formation === filtreFormation)
          if (reference?.ref_formation_id) {
            params.set('ref_formation_id', String(reference.ref_formation_id))
          }
        }
      }
      if (avecDetail) params.set('detail', '1')
      const { blob, fileName } = await api.getBlob(
        `/scolarite/maquettes/exporter/${format}/?${params.toString()}`,
      )
      telechargerBlob(blob, fileName || `maquettes.${format}`)
      toast.showToast(`Export ${format.toUpperCase()} généré pour ${selection.length || maquettes.length} maquette(s).`)
    } catch (err) {
      toast.showToast(
        err.response?.data?.error || `Export ${format.toUpperCase()} impossible.`,
        'error',
      )
    } finally {
      setExportEnCours('')
    }
  }

  // ── Import ───────────────────────────────────────────────────────────────
  const ouvrirSelecteurFichier = (format) => {
    formatCourantRef.current = format
    const champ = fichierRef.current
    if (!champ) return
    champ.accept = FORMATS_IMPORT.find((f) => f.valeur === format)?.accept || '.csv,.xlsx'
    champ.click()
  }

  const surFichierChoisi = async (evenement) => {
    const fichier = evenement.target.files?.[0]
    // Réinitialise pour permettre de rechoisir le même fichier après correction.
    evenement.target.value = ''
    if (!fichier) return
    setImportEnCours(true)
    setErreurImport('')
    setRapportImport(null)
    fichierChoisiRef.current = fichier
    const donnees = new FormData()
    donnees.append('fichier', fichier)
    donnees.append('mode', 'apercu')
    try {
      const res = await api.post('/scolarite/maquettes/importer/', donnees)
      setAnalyseImport(res.data)
    } catch (err) {
      const data = err.response?.data
      if (data?.resume) {
        // Le serveur a analysé le fichier mais refuse l'intégration : on
        // affiche le rapport complet plutôt qu'un simple message d'erreur.
        setAnalyseImport(data)
      } else {
        const message = data?.error || "Analyse du fichier impossible (format, taille ou structure)."
        setErreurImport(message)
        toast.showToast(message, 'error')
      }
    } finally {
      setImportEnCours(false)
    }
  }

  const telechargerModele = async (format) => {
    try {
      const { blob, fileName } = await api.getBlob(
        `/scolarite/maquettes/importer/modele/${format}/`,
      )
      telechargerBlob(blob, fileName || `modele_maquettes.${format}`)
    } catch {
      toast.showToast('Téléchargement du modèle impossible.', 'error')
    }
  }

  const confirmerImport = async () => {
    if (!analyseImport) return
    setImportEnCours(true)
    try {
      const donnees = new FormData()
      donnees.append('fichier', fichierChoisiRef.current)
      donnees.append('mode', 'importer')
      const res = await api.post('/scolarite/maquettes/importer/', donnees)
      setAnalyseImport(null)
      setRapportImport(res.data)
      fichierChoisiRef.current = null
      setSelection([])
      charger()
    } catch (err) {
      const data = err.response?.data
      if (data?.resume) setAnalyseImport(data)
      toast.showToast(data?.error || "Import impossible : aucune donnée n'a été enregistrée.", 'error')
    } finally {
      setImportEnCours(false)
    }
  }

  return (
    <div className="cand-page maq-page">
      {/* ── Bandeau d'accueil ── */}
      <div className="cand-hero">
        <div className="cand-hero-identite">
          <span className="cand-hero-icone" aria-hidden="true">
            <i className="bi bi-diagram-3"></i>
          </span>
          <div className="cand-hero-text">
            <span className="cand-hero-badge">Scolarité — Maquettes LMD</span>
            <h1 className="cand-hero-title">Maquettes pédagogiques LMD</h1>
            <p className="cand-hero-sub">
              Conception, structuration des parcours (UE/ECUE/ECTS) et cycles de validation académique.
            </p>
          </div>
        </div>
        <div className="maq-hero-pastilles">
          <span className="maq-pastille maq-pastille--primary">
            <i className="bi bi-mortarboard" aria-hidden="true"></i>
            {maquettes.length} maquette{maquettes.length > 1 ? 's' : ''}
          </span>
          <span className="maq-pastille maq-pastille--neutre">
            <i className="bi bi-collection" aria-hidden="true"></i>
            {formatNombre(stats.credits)} crédits ECTS
          </span>
          <span className="maq-pastille maq-pastille--neutre">
            <i className="bi bi-shield-lock" aria-hidden="true"></i>
            {stats.pctFinalisees} % finalisées
          </span>
        </div>
      </div>

      {/* ── Indicateurs ── */}
      <div className="cand-kpi-row">
        <div className="cand-kpi">
          <span className="cand-kpi-icon is-blue" aria-hidden="true"><i className="bi bi-mortarboard"></i></span>
          <div className="cand-kpi-texte">
            <span className="cand-kpi-value">{stats.total}</span>
            <span className="cand-kpi-label">Total maquettes</span>
            <span className="maq-kpi-sub">{formatNombre(stats.credits)} ECTS documentés</span>
          </div>
        </div>
        <div className="cand-kpi">
          <span className="cand-kpi-icon is-green" aria-hidden="true"><i className="bi bi-check2-circle"></i></span>
          <div className="cand-kpi-texte">
            <span className="cand-kpi-value">{stats.actives}</span>
            <span className="cand-kpi-label">Actives (immuables)</span>
            <span className="maq-kpi-sub">
              {stats.total ? Math.round((stats.actives / stats.total) * 100) : 0} % du catalogue
            </span>
          </div>
        </div>
        <div className="cand-kpi">
          <span className="cand-kpi-icon is-slate" aria-hidden="true"><i className="bi bi-lock"></i></span>
          <div className="cand-kpi-texte">
            <span className="cand-kpi-value">{stats.validees}</span>
            <span className="cand-kpi-label">Validées (gelées)</span>
            <span className="maq-kpi-sub">Prêtes à activer</span>
          </div>
        </div>
        <div className="cand-kpi">
          <span className="cand-kpi-icon is-amber" aria-hidden="true"><i className="bi bi-pencil-square"></i></span>
          <div className="cand-kpi-texte">
            <span className="cand-kpi-value">{stats.brouillons}</span>
            <span className="cand-kpi-label">Brouillons</span>
            <span className="maq-kpi-sub">
              {stats.brouillons ? 'En attente de validation' : 'Aucun en attente'}
            </span>
          </div>
        </div>
      </div>

      {/* ── Cycle de validation académique ── */}
      <section className="cand-panel" aria-labelledby="titre-cycle-maquettes">
        <header className="cand-panel-head">
          <h2 className="cand-panel-title" id="titre-cycle-maquettes">
            <i className="bi bi-bezier2" aria-hidden="true"></i>Cycle de validation académique
          </h2>
          <span className="cand-count-pill">{stats.pctFinalisees} % finalisées</span>
        </header>
        <div className="cand-panel-body">
          <div className="maq-cycle" role="group" aria-label="Filtrer par étape du cycle">
            {ETAPES.map((etape, rang) => (
              <React.Fragment key={etape.value}>
                {rang > 0 && (
                  <span className="maq-cycle-lien" aria-hidden="true">
                    <i className="bi bi-chevron-right"></i>
                  </span>
                )}
                <button
                  type="button"
                  className={
                    `maq-etape is-${etape.ton}` +
                    (filtreStatut === etape.value ? ' is-active' : '')
                  }
                  aria-pressed={filtreStatut === etape.value}
                  title={`Filtrer : ${etape.label}`}
                  onClick={() => basculerStatut(etape.value)}
                >
                  <span className="maq-etape-icone" aria-hidden="true">
                    <i className={`bi ${etape.icone}`}></i>
                  </span>
                  <span className="maq-etape-texte">
                    <span className="maq-etape-label">{etape.label}</span>
                    <span className="maq-etape-aide">{etape.aide}</span>
                  </span>
                  <span className="maq-etape-nb">{parStatut[etape.value] ?? 0}</span>
                </button>
              </React.Fragment>
            ))}
          </div>
          <div
            className="maq-progression"
            role="progressbar"
            aria-valuenow={stats.pctFinalisees}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label="Part des maquettes finalisées"
          >
            <span className="maq-progression-barre" style={{ width: `${stats.pctFinalisees}%` }}></span>
          </div>
          {peutAgir && stats.brouillons > 0 && (
            <div className="maq-lot">
              <p className="maq-lot-texte">
                <i className="bi bi-exclamation-circle" aria-hidden="true"></i>
                <span>
                  <strong>{stats.brouillons} brouillon{stats.brouillons > 1 ? 's' : ''}</strong> en
                  attente : la validation ventile les crédits des UE vers leurs ECUE, contrôle la
                  cohérence LMD puis gèle le contenu (toute correction passera par un clonage).
                </span>
              </p>
              <button
                type="button"
                className="cand-btn-principal maq-lot-btn"
                disabled={enCours}
                onClick={validerTout}
              >
                <i className="bi bi-check2-all" aria-hidden="true"></i>
                Valider tous les brouillons
              </button>
            </div>
          )}
          {stats.total > 0 && stats.brouillons === 0 && (
            <p className="maq-cycle-ok">
              <i className="bi bi-patch-check" aria-hidden="true"></i>
              Toutes les maquettes de la vue sont finalisées : aucune n’attend de validation.
            </p>
          )}
        </div>
      </section>

      {/* ── Couverture par formation ── */}
      {couverture.length > 0 && (
        <section className="cand-panel" aria-labelledby="titre-couverture-maquettes">
          <header className="cand-panel-head">
            <h2 className="cand-panel-title" id="titre-couverture-maquettes">
              <i className="bi bi-grid-3x3-gap" aria-hidden="true"></i>Couverture par formation
            </h2>
            <span className="cand-count-pill">
              {couverture.length} filière{couverture.length > 1 ? 's' : ''} · L1 → M2
            </span>
          </header>
          <div className="cand-table-wrap">
            <table className="maq-matrice">
              <thead>
                <tr>
                  <th scope="col">Filière</th>
                  {NIVEAUX_MATRICE.map((code) => <th key={code} scope="col">{code}</th>)}
                </tr>
              </thead>
              <tbody>
                {couverture.map(([base, parNiveau]) => (
                  <tr key={base}>
                    <th scope="row" className="maq-matrice-filiere">{base}</th>
                    {NIVEAUX_MATRICE.map((code) => {
                      const liste = parNiveau.get(code) || []
                      const m = liste[0]
                      return (
                        <td key={code}>
                          {m ? (
                            <Link
                              to={`/scolarite/maquettes/${m.id}`}
                              className={`maq-cellule is-${(m.statut || '').toLowerCase()}`}
                              aria-label={`Détail de la maquette ${base} ${code}`}
                              title={`${m.ref_formation} — ${m.statut}`}
                            >
                              <i className={`bi ${ICONE_STATUT[m.statut] || 'bi-file-earmark'}`} aria-hidden="true"></i>
                              <span className="maq-cellule-cr">{m.total_credits} cr.</span>
                              {liste.length > 1 && <span className="maq-cellule-x">×{liste.length}</span>}
                            </Link>
                          ) : (
                            <span className="maq-cellule maq-cellule--vide" aria-hidden="true">—</span>
                          )}
                        </td>
                      )
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="cand-panel-body maq-legende">
            <span><span className="maq-point is-active"></span>Active</span>
            <span><span className="maq-point is-validee"></span>Validée</span>
            <span><span className="maq-point is-brouillon"></span>Brouillon</span>
            <span><span className="maq-point is-archivee"></span>Archivée</span>
            <span className="maq-legende-note">Cliquez une case pour ouvrir la maquette.</span>
          </div>
        </section>
      )}

      {/* ── Filtres et recherche ── */}
      <section className="cand-panel" aria-labelledby="titre-filtres-maquettes">
        <header className="cand-panel-head">
          <h2 className="cand-panel-title" id="titre-filtres-maquettes">
            <i className="bi bi-funnel" aria-hidden="true"></i>Filtres et recherche
          </h2>
          <span className="cand-count-pill">
            {maquettesFiltrees.length} résultat{maquettesFiltrees.length > 1 ? 's' : ''}
          </span>
        </header>
        <div className="cand-panel-body">
          <div className="cand-filters maq-filtres">
            <div className="maq-filtre">
              <label className="cand-etiquette" htmlFor="maq-filtre-statut">Filtrer par statut</label>
              <select
                id="maq-filtre-statut"
                className="cand-filter-select"
                value={filtreStatut}
                onChange={(e) => setFiltreStatut(e.target.value)}
              >
                {STATUTS.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
              </select>
            </div>
            <div className="maq-filtre">
              <label className="cand-etiquette" htmlFor="maq-filtre-formation">Filtrer par formation</label>
              <select
                id="maq-filtre-formation"
                className="cand-filter-select"
                value={filtreFormation}
                onChange={(e) => setFiltreFormation(e.target.value)}
              >
                <option value="">Toutes les formations</option>
                {formationsPresentes.map(([intitule, nb]) => (
                  <option key={intitule} value={intitule}>{intitule} ({nb})</option>
                ))}
              </select>
            </div>
            <div className="maq-filtre maq-filtre--large">
              <label className="cand-etiquette" htmlFor="maq-recherche">Rechercher une formation ou un parcours</label>
              <div className="cand-search maq-recherche">
                <i className="bi bi-search" aria-hidden="true"></i>
                <input
                  id="maq-recherche"
                  type="search"
                  className="cand-input"
                  placeholder="Filtrer par intitulé, niveau, parcours…"
                  value={recherche}
                  onChange={(e) => setRecherche(e.target.value)}
                />
                {recherche && (
                  <button
                    type="button"
                    className="maq-effacer"
                    onClick={() => setRecherche('')}
                    aria-label="Effacer la recherche"
                  >
                    <i className="bi bi-x-lg" aria-hidden="true"></i>
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── Création ── */}
      {peutAgir && (
        <section
          className="cand-panel"
          aria-labelledby="titre-nouvelle-maquette"
          ref={sectionCreationRef}
        >
          <header className="cand-panel-head">
            <h2 className="cand-panel-title" id="titre-nouvelle-maquette">
              <i className="bi bi-plus-circle" aria-hidden="true"></i>Nouvelle maquette
            </h2>
            <span className="cand-count-pill">Brouillon v1</span>
          </header>
          <div className="cand-panel-body">
            <form className="cand-grille-form maq-form" onSubmit={creer}>
              <div className="cand-champ">
                <label className="cand-etiquette" htmlFor="maq-annee">
                  Année académique *
                </label>
                <select
                  id="maq-annee" ref={champAnneeRef}
                  className="cand-saisie" required value={form.annee_academique_id}
                  onChange={(e) => setForm({ ...form, annee_academique_id: e.target.value })}>
                  <option value="">Année académique…</option>
                  {options.annees.map((a) => <option key={a.id} value={a.id}>{a.libelle}</option>)}
                </select>
              </div>
              <div className="cand-champ">
                <label className="cand-etiquette" htmlFor="maq-formation">
                  Formation *
                </label>
                <select
                  id="maq-formation" className="cand-saisie" required value={form.ref_formation_id}
                  onChange={(e) => setForm({ ...form, ref_formation_id: e.target.value })}>
                  <option value="">Formation…</option>
                  {options.formations.map((f) => <option key={f.id} value={f.id}>{f.intitule}</option>)}
                </select>
              </div>
              <div className="cand-champ">
                <label className="cand-etiquette" htmlFor="maq-niveau">
                  Niveau *
                </label>
                <select
                  id="maq-niveau" className="cand-saisie" required value={form.niveau_id}
                  onChange={(e) => setForm({ ...form, niveau_id: e.target.value })}>
                  <option value="">Niveau…</option>
                  {options.niveaux.map((n) => <option key={n.id} value={n.id}>{n.code}</option>)}
                </select>
              </div>
              <div className="cand-champ">
                <label className="cand-etiquette" htmlFor="maq-libelle">Libellé</label>
                <input
                  id="maq-libelle" className="cand-saisie" placeholder="Libellé (optionnel)"
                  value={form.libelle} onChange={(e) => setForm({ ...form, libelle: e.target.value })}
                />
              </div>
              <div className="maq-form-pied">
                <p className="maq-note">
                  <i className="bi bi-info-circle" aria-hidden="true"></i>
                  La maquette est enregistrée au statut brouillon : ajoutez les UE/ECUE puis validez avant activation (immuable).
                </p>
                <button type="submit" className="cand-btn-principal maq-creer" disabled={enCours}>
                  <i className="bi bi-plus-lg" aria-hidden="true"></i>Créer
                </button>
              </div>
            </form>
          </div>
        </section>
      )}

      {/* ── Liste, panneau d'actions, exports et imports ── */}
      <section className="cand-panel" aria-labelledby="titre-liste-maquettes">
        <header className="cand-panel-head">
          <h2 className="cand-panel-title" id="titre-liste-maquettes">
            <i className="bi bi-table" aria-hidden="true"></i>Maquettes
          </h2>
          <span className="cand-count-pill" data-testid="maq-compteur-selection">
            {maquettesFiltrees.length} maquette{maquettesFiltrees.length > 1 ? 's' : ''}
            {' · '}
            <strong>{maquettesSelectionnees.length}</strong> sélectionnée
            {maquettesSelectionnees.length > 1 ? 's' : ''}
          </span>
        </header>

        <div className="maq-gestion">
          {/* ── Liste ── */}
          <div className="maq-gestion-liste">
            <div className="cand-table-wrap">
              <table className="cand-table cand-table--maquettes">
                <thead>
                  <tr>
                    <th scope="col" className="maq-col-case">
                      <input
                        ref={toutRef}
                        type="checkbox"
                        className="maq-case"
                        checked={toutVisibleSelectionne}
                        onChange={basculerTout}
                        disabled={maquettesFiltrees.length === 0}
                        aria-label="Sélectionner toutes les maquettes"
                        title="Sélectionner / désélectionner toutes les maquettes affichées"
                      />
                    </th>
                    <th scope="col">Formation</th>
                    <th scope="col">Niveau</th>
                    <th scope="col">Parcours</th>
                    <th scope="col">Année</th>
                    <th scope="col">Version</th>
                    <th scope="col">Statut</th>
                    <th scope="col">UE</th>
                    <th scope="col">Crédits</th>
                    {peutAgir && <th scope="col" className="cand-th-actions">Actions</th>}
                  </tr>
                </thead>
                <tbody>
                  {chargement ? (
                    <tr>
                      <td colSpan={peutAgir ? 10 : 9}>
                        <div className="cand-chargement">
                          <span className="spinner-border" role="status" aria-hidden="true"></span>
                          Chargement des maquettes…
                        </div>
                      </td>
                    </tr>
                  ) : maquettesFiltrees.length === 0 ? (
                    <tr>
                      <td colSpan={peutAgir ? 10 : 9}>
                        <div className="cand-vide">
                          <span className="cand-vide-icone" aria-hidden="true">
                            <i className="bi bi-inbox"></i>
                          </span>
                          <p className="cand-vide-titre">Aucune maquette.</p>
                          <p className="cand-vide-texte">
                            {recherche || filtreStatut || filtreFormation
                              ? 'Aucune maquette ne correspond aux filtres sélectionnés.'
                              : 'Créez une première maquette pour structurer les UE/ECUE d’un parcours.'}
                          </p>
                        </div>
                      </td>
                    </tr>
                  ) : maquettesFiltrees.map((m) => {
                    const estExemple = (m.libelle || '').startsWith('[Exemple]')
                    const credits = m.total_credits || 0
                    const conforme = credits === CREDITS_PAR_NIVEAU
                    const choisie = selection.includes(m.id)
                    return (
                      <tr
                        key={m.id}
                        className={`maq-ligne--${(m.statut || '').toLowerCase()}${choisie ? ' is-selectionnee' : ''}`}
                      >
                        <td className="maq-col-case">
                          <input
                            type="checkbox"
                            className="maq-case"
                            checked={choisie}
                            onChange={() => basculerSelection(m.id)}
                            aria-label={`Sélectionner la maquette ${m.libelle}`}
                          />
                        </td>
                        <td>
                          <span className="maq-formation">
                            <span className="maq-formation-icone" aria-hidden="true">
                              <i className="bi bi-mortarboard"></i>
                            </span>
                            <Link to={`/scolarite/maquettes/${m.id}`} className="maq-lien">
                              {m.ref_formation}
                            </Link>
                            {estExemple && <span className="maq-exemple">Exemple</span>}
                          </span>
                        </td>
                        <td><span className="cand-badge-neutre">{m.niveau}</span></td>
                        <td>
                          {m.parcours
                            ? <span className="maq-parcours">{m.parcours}</span>
                            : <span className="cand-texte-doux">—</span>}
                        </td>
                        <td className="cand-col-etroit"><span className="maq-annee">{m.annee_academique}</span></td>
                        <td><span className="maq-chip">v{m.version}</span></td>
                        <td>
                          <span className={`maq-statut text-bg-${BADGE_STATUT[m.statut] || 'secondary'}`}>
                            <i className={`bi ${ICONE_STATUT[m.statut] || 'bi-question-circle'}`} aria-hidden="true"></i>
                            {m.statut}
                          </span>
                        </td>
                        <td className="cand-col-etroit"><span className="maq-nombre">{m.nb_ue}</span></td>
                        <td className="cand-col-etroit">
                          <span className="maq-credits">
                            <span>
                              <span className="maq-nombre">{m.total_credits}</span>
                              <span className="maq-unite"> cr.</span>
                            </span>
                            <span className="maq-jauge" aria-hidden="true">
                              <span
                                className={`maq-jauge-barre${conforme ? ' is-conforme' : ''}`}
                                style={{ width: `${Math.min(100, (credits / CREDITS_PAR_NIVEAU) * 100)}%` }}
                              ></span>
                            </span>
                            <span className={`maq-conformite${conforme ? ' is-ok' : ' is-ko'}`}>
                              {conforme ? 'Conforme' : 'À compléter'}
                            </span>
                          </span>
                        </td>
                        {peutAgir && (
                          <td className="cand-col-actions">
                            <div className="cand-actions maq-actions">
                              {m.statut === 'BROUILLON' && (
                                <button
                                  type="button" className="maq-action maq-action--valider" disabled={enCours}
                                  title="Valider cette maquette (contenu gelé)"
                                  onClick={() => action(m, 'valider', 'Valider cette maquette (contenu gelé) ?')}>
                                  <i className="bi bi-check2-circle" aria-hidden="true"></i>Valider
                                </button>
                              )}
                              {m.statut === 'VALIDEE' && (
                                <button
                                  type="button" className="maq-action maq-action--activer" disabled={enCours}
                                  title="Activer cette maquette (immuable)"
                                  onClick={() => action(m, 'activer', 'Activer cette maquette (immuable) ?')}>
                                  <i className="bi bi-lightning-charge" aria-hidden="true"></i>Activer
                                </button>
                              )}
                              {m.statut === 'ACTIVE' && (
                                <button
                                  type="button" className="maq-action maq-action--archiver" disabled={enCours}
                                  title="Archiver cette maquette"
                                  onClick={() => action(m, 'archiver', 'Archiver cette maquette ?')}>
                                  <i className="bi bi-archive" aria-hidden="true"></i>Archiver
                                </button>
                              )}
                              {m.statut !== 'BROUILLON' && (
                                <button
                                  type="button" className="maq-action maq-action--cloner" disabled={enCours}
                                  title="Créer une nouvelle version (clonage)"
                                  onClick={() => action(m, 'cloner', 'Créer une nouvelle version (clonage) ?')}>
                                  <i className="bi bi-copy" aria-hidden="true"></i>Cloner
                                </button>
                              )}
                            </div>
                          </td>
                        )}
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
            <p className="cand-defile" aria-hidden="true">
              <i className="bi bi-arrow-left-right"></i>
              Faites défiler le tableau horizontalement
            </p>
          </div>

          {/* ── Panneau d'actions (à droite de la liste) ── */}
          {peutAgir && (
            <aside className="maq-panneau" aria-label="Actions sur les maquettes sélectionnées">
              <h3 className="maq-panneau-titre">
                <i className="bi bi-sliders" aria-hidden="true"></i>Actions
              </h3>

              <p className="maq-panneau-selection" role="status" aria-live="polite">
                {maquettesSelectionnees.length === 0 ? (
                  <>Aucune maquette sélectionnée</>
                ) : maquettesSelectionnees.length === 1 ? (
                  <><strong>1</strong> maquette sélectionnée</>
                ) : (
                  <><strong>{maquettesSelectionnees.length}</strong> maquettes sélectionnées</>
                )}
              </p>

              <div className="maq-panneau-boutons">
                <button
                  type="button"
                  className="maq-btn-action is-creer"
                  onClick={allerVersCreation}
                  aria-label="Créer une maquette"
                >
                  <i className="bi bi-plus-lg" aria-hidden="true"></i>
                  <span>Créer</span>
                </button>

                <button
                  type="button"
                  className="maq-btn-action is-visualiser"
                  disabled={maquettesSelectionnees.length !== 1}
                  onClick={ouvrirVisualisation}
                  aria-label="Visualiser la maquette sélectionnée"
                  title={
                    maquettesSelectionnees.length === 1
                      ? 'Consulter la maquette en lecture seule'
                      : 'Sélectionnez exactement une maquette'
                  }
                >
                  <i className="bi bi-eye" aria-hidden="true"></i>
                  <span>Visualiser</span>
                </button>

                <button
                  type="button"
                  className="maq-btn-action is-modifier"
                  disabled={
                    maquettesSelectionnees.length !== 1
                    || maquettesSelectionnees[0]?.statut !== 'BROUILLON'
                  }
                  onClick={ouvrirEdition}
                  aria-label="Modifier la maquette sélectionnée"
                  title={
                    maquettesSelectionnees.length === 1
                      ? (maquettesSelectionnees[0].statut === 'BROUILLON'
                        ? 'Modifier le libellé et le parcours'
                        : 'Maquette gelée : créez une nouvelle version (clonage)')
                      : 'Sélectionnez une seule maquette'
                  }
                >
                  <i className="bi bi-pencil-square" aria-hidden="true"></i>
                  <span>Modifier</span>
                </button>

                <button
                  type="button"
                  className="maq-btn-action is-supprimer"
                  disabled={maquettesSelectionnees.length === 0}
                  onClick={demanderSuppression}
                  aria-label="Supprimer les maquettes sélectionnées"
                  title={
                    maquettesSelectionnees.length
                      ? 'Supprimer les maquettes sélectionnées (confirmation demandée)'
                      : 'Sélectionnez au moins une maquette'
                  }
                >
                  <i className="bi bi-trash3" aria-hidden="true"></i>
                  <span>Supprimer</span>
                </button>
              </div>

              <p className="maq-panneau-aide">
                <i className="bi bi-info-circle" aria-hidden="true"></i>
                La modification n’est possible que sur une maquette en brouillon ; une maquette
                validée ou active se décline en nouvelle version.
              </p>
            </aside>
          )}
        </div>

        {/* ── Barre d'exports / d'imports (sous la liste) ── */}
        {peutAgir && (
          <div className="maq-barre-outils">
            <div className="maq-barre-groupe" aria-label="Exporter les maquettes">
              <span className="maq-barre-titre">
                <i className="bi bi-box-arrow-down" aria-hidden="true"></i>Exporter
              </span>
              <div className="maq-barre-boutons">
                {FORMATS_EXPORT.map((format) => (
                  <button
                    key={format.valeur}
                    type="button"
                    className={`maq-btn-export is-${format.ton}`}
                    onClick={() => exporter(format.valeur)}
                    disabled={Boolean(exportEnCours) || importEnCours}
                    aria-label={format.libelle}
                  >
                    <i className={`bi ${format.icone}`} aria-hidden="true"></i>
                    <span>{format.libelle.replace('Export ', '')}</span>
                    {exportEnCours === format.valeur && (
                      <span className="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span>
                    )}
                  </button>
                ))}
              </div>
              <label className="maq-case-detail">
                <input
                  type="checkbox"
                  checked={avecDetail}
                  onChange={(e) => setAvecDetail(e.target.checked)}
                />
                Inclure le détail pédagogique (UE/ECUE)
              </label>
              <p className="maq-barre-note">
                {selection.length
                  ? `${selection.length} maquette(s) sélectionnée(s) seront exportées.`
                  : 'Aucune sélection : toutes les maquettes du périmètre (filtres) seront exportées.'}
              </p>
            </div>

            <div className="maq-barre-groupe" aria-label="Importer des maquettes">
              <span className="maq-barre-titre">
                <i className="bi bi-box-arrow-in-down" aria-hidden="true"></i>Importer
              </span>
              <div className="maq-barre-boutons">
                {FORMATS_IMPORT.map((format) => (
                  <button
                    key={format.valeur}
                    type="button"
                    className="maq-btn-import"
                    onClick={() => ouvrirSelecteurFichier(format.valeur)}
                    disabled={importEnCours}
                    aria-label={format.libelle}
                  >
                    <i className={`bi ${format.icone}`} aria-hidden="true"></i>
                    <span>{format.libelle.replace('Importer ', 'Import ')}</span>
                  </button>
                ))}
                <button
                  type="button"
                  className="maq-btn-modele"
                  onClick={() => telechargerModele('csv')}
                  aria-label="Télécharger le modèle d’import CSV"
                >
                  <i className="bi bi-download" aria-hidden="true"></i>
                  <span>Modèle</span>
                </button>
              </div>
              {importEnCours && (
                <p className="maq-barre-note" role="status">
                  <span className="spinner-border spinner-border-sm" aria-hidden="true"></span>
                  Analyse du fichier…
                </p>
              )}
              {erreurImport && (
                <p className="maq-barre-erreur" role="alert">
                  <i className="bi bi-exclamation-triangle" aria-hidden="true"></i>
                  {erreurImport}
                </p>
              )}
              <input
                ref={fichierRef}
                type="file"
                className="maq-champ-fichier"
                onChange={surFichierChoisi}
                tabIndex={-1}
                aria-hidden="true"
              />
            </div>
          </div>
        )}
      </section>

      {/* ── Boîte de modification ── */}
      {edition && (
        <div className="modal-overlay" onClick={() => setEdition(null)}>
          <div
            className="modal-content maq-modale"
            role="dialog"
            aria-modal="true"
            aria-labelledby="titre-edition-maquette"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="modal-header">
              <h5 id="titre-edition-maquette">
                <i className="bi bi-pencil-square me-2" aria-hidden="true"></i>
                Modifier la maquette
              </h5>
              <button
                type="button"
                className="btn-close"
                onClick={() => setEdition(null)}
                aria-label="Fermer la boîte de dialogue"
              >&times;</button>
            </div>
            <form onSubmit={enregistrerEdition}>
              <div className="modal-body">
                <p className="maq-modale-note">
                  Maquette <strong>{edition.libelleAffiche}</strong> — les UE/ECUE se modifient
                  depuis la fiche détaillée.
                </p>
                <div className="cand-champ">
                  <label className="cand-etiquette" htmlFor="maq-edit-libelle">Libellé</label>
                  <input
                    id="maq-edit-libelle"
                    className="cand-saisie"
                    value={edition.libelle}
                    maxLength={255}
                    onChange={(e) => setEdition({ ...edition, libelle: e.target.value })}
                  />
                </div>
                <div className="cand-champ">
                  <label className="cand-etiquette" htmlFor="maq-edit-parcours">Parcours</label>
                  <select
                    id="maq-edit-parcours"
                    className="cand-saisie"
                    value={edition.parcours_id}
                    disabled={edition.chargementParcours}
                    onChange={(e) => setEdition({ ...edition, parcours_id: e.target.value })}
                  >
                    <option value="">Aucun parcours (tronc commun)</option>
                    {edition.parcours.map((parcours) => (
                      <option key={parcours.id} value={parcours.id}>
                        {parcours.intitule}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-outline-secondary" onClick={() => setEdition(null)}>
                  Annuler
                </button>
                <button type="submit" className="btn btn-primary" disabled={editionEnCours}>
                  {editionEnCours
                    ? <><span className="spinner-border spinner-border-sm" aria-hidden="true"></span> Enregistrement…</>
                    : 'Enregistrer'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ── Confirmation de suppression ── */}
      {suppression && (
        <ConfirmModal
          message={`Supprimer ${suppression.ids.length} maquette${suppression.ids.length > 1 ? 's' : ''} ?`}
          detail="Seules les maquettes en brouillon sans donnée liée sont supprimées ; les autres sont refusées et listées dans le bilan. Cette action est irréversible."
          confirmLabel={suppression.ids.length > 1 ? 'Supprimer ces maquettes' : 'Supprimer'}
          onConfirm={confirmerSuppression}
          onCancel={() => setSuppression(null)}
        />
      )}

      {/* ── Bilan de suppression ── */}
      {bilanSuppression && (
        <div className="modal-overlay" onClick={() => setBilanSuppression(null)}>
          <div
            className="modal-content maq-modale"
            role="dialog"
            aria-modal="true"
            aria-labelledby="titre-bilan-suppression"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="modal-header">
              <h5 id="titre-bilan-suppression">
                <i className="bi bi-clipboard-check me-2" aria-hidden="true"></i>
                Bilan de la suppression
              </h5>
              <button
                type="button"
                className="btn-close"
                onClick={() => setBilanSuppression(null)}
                aria-label="Fermer la boîte de dialogue"
              >&times;</button>
            </div>
            <div className="modal-body">
              <ul className="maq-bilan-liste">
                <li>
                  <i className="bi bi-check2-circle is-ok" aria-hidden="true"></i>
                  {(bilanSuppression.supprimees || []).length} supprimée(s)
                </li>
                <li>
                  <i className="bi bi-shield-exclamation is-ko" aria-hidden="true"></i>
                  {(bilanSuppression.bloquees || []).length} bloquée(s)
                </li>
                {(bilanSuppression.introuvables || []).length > 0 && (
                  <li>
                    <i className="bi bi-question-circle is-ko" aria-hidden="true"></i>
                    {(bilanSuppression.introuvables || []).length} introuvable(s)
                  </li>
                )}
              </ul>
              {(bilanSuppression.bloquees || []).length > 0 && (
                <div className="maq-bilan-blocages">
                  <h6>Maquettes conservées</h6>
                  <ul>
                    {bilanSuppression.bloquees.map((element) => (
                      <li key={element.id}>
                        <strong>{element.libelle}</strong> — {element.motif}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
            <div className="modal-footer">
              <button type="button" className="btn btn-primary" onClick={() => setBilanSuppression(null)}>
                Fermer
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Prévisualisation avant import ── */}
      {analyseImport && (
        <div className="modal-overlay" onClick={() => setAnalyseImport(null)}>
          <div
            className="modal-content maq-modale maq-modale--large"
            role="dialog"
            aria-modal="true"
            aria-labelledby="titre-apercu-import"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="modal-header">
              <h5 id="titre-apercu-import">
                <i className="bi bi-file-earmark-spreadsheet me-2" aria-hidden="true"></i>
                Prévisualisation de l’import — {analyseImport.fichier}
              </h5>
              <button
                type="button"
                className="btn-close"
                onClick={() => setAnalyseImport(null)}
                aria-label="Fermer la boîte de dialogue"
              >&times;</button>
            </div>
            <div className="modal-body">
              <div className="maq-apercu-resume" role="status">
                <span className="maq-pastille maq-pastille--neutre">
                  {(analyseImport.resume?.lignes_lues) || 0} lignes lues
                </span>
                <span className="maq-pastille maq-pastille--ok">
                  {(analyseImport.resume?.lignes_valides) || 0} valides
                </span>
                <span className="maq-pastille maq-pastille--attention">
                  {(analyseImport.resume?.doublons) || 0} doublons
                </span>
                <span className={`maq-pastille ${analyseImport.erreurs?.length ? 'maq-pastille--ko' : 'maq-pastille--neutre'}`}>
                  {analyseImport.erreurs?.length || 0} erreurs
                </span>
                <span className="maq-pastille maq-pastille--neutre">
                  {analyseImport.avertissements?.length || 0} avertissements
                </span>
              </div>

              {analyseImport.maquettes?.length > 0 && (
                <div className="maq-apercu-maquettes">
                  <h6>Maquettes détectées</h6>
                  <ul>
                    {analyseImport.maquettes.map((maquette) => (
                      <li key={`${maquette.libelle}-${maquette.version || 'new'}`}>
                        <strong>{maquette.libelle}</strong> — {maquette.nb_ue} UE, {maquette.nb_ecue} ECUE,{' '}
                        {maquette.credits} crédits
                        <span className={`maq-etiquette-action is-${maquette.action}`}>
                          {maquette.action === 'creation' ? 'création' : 'mise à jour'}
                        </span>
                        {maquette.verrouillee && (
                          <span className="maq-etiquette-action is-bloquee">verrouillée</span>
                        )}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {analyseImport.lignes?.length > 0 && (
                <div className="cand-table-wrap maq-apercu-table">
                  <table className="cand-table">
                    <thead>
                      <tr>
                        <th scope="col">Ligne</th>
                        <th scope="col">Formation</th>
                        <th scope="col">Niveau</th>
                        <th scope="col">Semestre</th>
                        <th scope="col">UE</th>
                        <th scope="col">ECUE</th>
                        <th scope="col">État</th>
                      </tr>
                    </thead>
                    <tbody>
                      {analyseImport.lignes.map((ligne) => (
                        <tr key={ligne.ligne} className={`maq-apercu-ligne is-${ligne.statut}`}>
                          <td>{ligne.ligne}</td>
                          <td>{ligne.formation}</td>
                          <td>{ligne.niveau}</td>
                          <td>{ligne.semestre}</td>
                          <td>{ligne.ue_code}</td>
                          <td>{ligne.ecue_code}</td>
                          <td>
                            <span className={`maq-etat is-${ligne.statut}`}>
                              {ligne.statut === 'ok' ? 'Valide' : ligne.statut === 'doublon' ? 'Doublon' : 'Erreur'}
                            </span>
                            {ligne.messages?.length > 0 && (
                              <span className="maq-apercu-message">{ligne.messages.join(' ')}</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              {analyseImport.lignes_tronquees > 0 && (
                <p className="maq-barre-note">
                  {analyseImport.lignes_tronquees} ligne(s) supplémentaire(s) non affichée(s) ;
                  elles sont bien prises en compte dans le rapport.
                </p>
              )}

              {analyseImport.erreurs?.length > 0 && (
                <div className="maq-rapport-bloc is-erreur" role="alert">
                  <h6>Erreurs bloquantes</h6>
                  <ul>
                    {analyseImport.erreurs.map((erreur, index) => (
                      <li key={`${erreur.ligne}-${index}`}>Ligne {erreur.ligne} : {erreur.message}</li>
                    ))}
                  </ul>
                </div>
              )}

              {analyseImport.avertissements?.length > 0 && (
                <div className="maq-rapport-bloc is-avertissement">
                  <h6>Avertissements</h6>
                  <ul>
                    {analyseImport.avertissements.map((element, index) => (
                      <li key={`${element.ligne || 'global'}-${index}`}>{element.message}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
            <div className="modal-footer">
              <button type="button" className="btn btn-outline-secondary" onClick={() => setAnalyseImport(null)}>
                Annuler
              </button>
              <button
                type="button"
                className="btn btn-primary"
                disabled={!analyseImport.importable || importEnCours}
                onClick={confirmerImport}
              >
                {importEnCours
                  ? <><span className="spinner-border spinner-border-sm" aria-hidden="true"></span> Import…</>
                  : "Confirmer l'import"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Rapport final d'import ── */}
      {rapportImport && (
        <div className="modal-overlay" onClick={() => setRapportImport(null)}>
          <div
            className="modal-content maq-modale"
            role="dialog"
            aria-modal="true"
            aria-labelledby="titre-rapport-import"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="modal-header">
              <h5 id="titre-rapport-import">
                <i className="bi bi-check2-circle me-2" aria-hidden="true"></i>
                Import terminé
              </h5>
              <button
                type="button"
                className="btn-close"
                onClick={() => setRapportImport(null)}
                aria-label="Fermer la boîte de dialogue"
              >&times;</button>
            </div>
            <div className="modal-body">
              <ul className="maq-bilan-liste">
                <li><strong>{rapportImport.bilan?.maquettes_creees || 0}</strong> maquette(s) créée(s)</li>
                <li><strong>{rapportImport.bilan?.maquettes_completees || 0}</strong> maquette(s) complétée(s)</li>
                <li>
                  <strong>{(rapportImport.bilan?.ue_creees || 0) + (rapportImport.bilan?.ue_mises_a_jour || 0)}</strong> UE
                  ({(rapportImport.bilan?.ue_creees || 0)} créée(s), {(rapportImport.bilan?.ue_mises_a_jour || 0)} mise(s) à jour)
                </li>
                <li>
                  <strong>{(rapportImport.bilan?.ecue_creees || 0) + (rapportImport.bilan?.ecue_mises_a_jour || 0)}</strong> ECUE
                  ({(rapportImport.bilan?.ecue_creees || 0)} créée(s), {(rapportImport.bilan?.ecue_mises_a_jour || 0)} mise(s) à jour)
                </li>
                <li><strong>{rapportImport.resume?.doublons || 0}</strong> ligne(s) ignorée(s) (doublons)</li>
                <li><strong>{rapportImport.resume?.avertissements || 0}</strong> avertissement(s)</li>
              </ul>
              {rapportImport.bilan?.maquettes?.length > 0 && (
                <div className="maq-rapport-bloc">
                  <h6>Maquettes importées (brouillon)</h6>
                  <ul>
                    {rapportImport.bilan.maquettes.map((maquette) => (
                      <li key={maquette.id}>
                        <Link to={`/scolarite/maquettes/${maquette.id}`} onClick={() => setRapportImport(null)}>
                          {maquette.libelle}
                        </Link>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
            <div className="modal-footer">
              <button type="button" className="btn btn-primary" onClick={() => setRapportImport(null)}>
                Fermer
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
