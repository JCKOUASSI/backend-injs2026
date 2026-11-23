import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import api from '../../services/api'
import { downloadFile } from '../../utils/downloadFile'
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
  const peutAgir = canActScolarite(user)

  const [maquettes, setMaquettes] = useState([])
  const [chargement, setChargement] = useState(true)
  const [filtreStatut, setFiltreStatut] = useState('')
  const [filtreFormation, setFiltreFormation] = useState('')
  const [recherche, setRecherche] = useState('')
  const [enCours, setEnCours] = useState(false)
  const [selectionIds, setSelectionIds] = useState([])
  const [exportDetaille, setExportDetaille] = useState(false)
  const [fichierImport, setFichierImport] = useState(null)
  const [apercuImport, setApercuImport] = useState(null)
  const [importEnCours, setImportEnCours] = useState(false)
  const [maquetteEditee, setMaquetteEditee] = useState(null)
  const [formEdition, setFormEdition] = useState({ libelle: '', commentaire_validation: '' })
  const [form, setForm] = useState({
    annee_academique_id: '', ref_formation_id: '', niveau_id: '', libelle: '',
  })
  const [options, setOptions] = useState({ annees: [], formations: [], niveaux: [] })
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

  const editer = (maquette) => {
    setMaquetteEditee(maquette)
    setFormEdition({
      libelle: maquette.libelle_personnalise || '',
      commentaire_validation: maquette.commentaire_validation || '',
    })
  }

  const enregistrerEdition = async (e) => {
    e.preventDefault()
    if (!maquetteEditee) return
    setEnCours(true)
    try {
      await api.patch(`/scolarite/maquettes/${maquetteEditee.id}/modifier/`, formEdition)
      toast.showToast('Maquette modifiée.')
      setMaquetteEditee(null)
      setSelectionIds([])
      charger()
    } catch (err) {
      toast.showToast(err.response?.data?.error || 'Modification impossible.', 'error')
    } finally {
      setEnCours(false)
    }
  }

  const supprimerMaquette = async (maquette) => {
    if (!window.confirm(`Supprimer le brouillon « ${maquette.ref_formation} » ?`)) return
    setEnCours(true)
    try {
      await api.delete(`/scolarite/maquettes/${maquette.id}/`)
      toast.showToast('Maquette supprimée.')
      setSelectionIds((ids) => ids.filter((id) => id !== maquette.id))
      await charger()
    } catch (err) {
      toast.showToast(err.response?.data?.error || 'Suppression impossible.', 'error')
    } finally {
      setEnCours(false)
    }
  }

  const supprimerSelection = async () => {
    if (!selectionIds.length) return
    if (!window.confirm(`Supprimer les ${selectionIds.length} maquette(s) brouillon sélectionnée(s) sans UE ?`)) return
    setEnCours(true)
    const supprimees = []
    const erreurs = []
    for (const maquette of maquettes.filter((m) => selectionIds.includes(m.id))) {
      try {
        await api.delete(`/scolarite/maquettes/${maquette.id}/`)
        supprimees.push(maquette.id)
      } catch (err) {
        erreurs.push(`${maquette.ref_formation} : ${err.response?.data?.error || 'suppression impossible'}`)
      }
    }
    if (erreurs.length) {
      toast.showToast(
        `${supprimees.length} maquette(s) supprimée(s). ${erreurs.join(' ')}`,
        'error',
      )
    } else if (supprimees.length) {
      toast.showToast(`${supprimees.length} maquette(s) supprimée(s).`)
    }
    setSelectionIds((ids) => ids.filter((id) => !supprimees.includes(id)))
    try {
      await charger()
    } finally {
      setEnCours(false)
    }
  }

  const exporter = async (format) => {
    if (!selectionIds.length) return
    const params = new URLSearchParams({ ids: selectionIds.join(',') })
    if (exportDetaille) params.set('detaille', '1')
    try {
      const { blob, fileName } = await api.getBlob(
        `/scolarite/maquettes/export/${format}/?${params.toString()}`,
      )
      downloadFile(blob, fileName || `maquettes.${format === 'word' ? 'docx' : format}`)
      toast.showToast('Export téléchargé.')
    } catch (err) {
      toast.showToast(err.response?.data?.error || err.message || 'Export impossible.', 'error')
    }
  }

  const formulaireImport = (fichier, etape, empreinte) => {
    const donnees = new FormData()
    donnees.append('fichier', fichier)
    donnees.append('etape', etape)
    if (empreinte) donnees.append('empreinte', empreinte)
    return donnees
  }

  const cheminImport = () => {
    const extension = fichierImport?.name.toLowerCase().endsWith('.xlsx') ? 'excel' : 'csv'
    return `/scolarite/maquettes/import/${extension}/`
  }

  const previsualiserImport = async () => {
    if (!fichierImport) return
    setImportEnCours(true)
    setApercuImport(null)
    try {
      const res = await api.post(
        cheminImport(),
        formulaireImport(fichierImport, 'previsualiser'),
      )
      setApercuImport(res.data)
    } catch (err) {
      toast.showToast(err.response?.data?.error || 'Prévisualisation impossible.', 'error')
    } finally {
      setImportEnCours(false)
    }
  }

  const confirmerImport = async () => {
    if (!fichierImport || !apercuImport?.valide || !apercuImport.empreinte) return
    setImportEnCours(true)
    try {
      const res = await api.post(
        cheminImport(),
        formulaireImport(fichierImport, 'confirmer', apercuImport.empreinte),
      )
      toast.showToast(res.data?.detail || 'Import effectué.')
      setFichierImport(null)
      setApercuImport(null)
      const input = document.getElementById('maq-import-fichier')
      if (input) input.value = ''
      await charger()
    } catch (err) {
      toast.showToast(err.response?.data?.error || 'Import impossible.', 'error')
    } finally {
      setImportEnCours(false)
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

  const maquettesSelectionnees = useMemo(
    () => maquettes.filter((m) => selectionIds.includes(m.id)),
    [maquettes, selectionIds],
  )
  const selectionComplete = maquettesFiltrees.length > 0
    && maquettesFiltrees.every((m) => selectionIds.includes(m.id))
  const selectionSupprimable = maquettesSelectionnees.length > 0
    && maquettesSelectionnees.every((m) => m.statut === 'BROUILLON' && m.nb_ue === 0)

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

  const basculerStatut = (value) => {
    setSelectionIds([])
    setFiltreStatut((actuel) => (actuel === value ? '' : value))
  }

  const selectionnerToutes = (cocher) => {
    const idsVisibles = maquettesFiltrees.map((m) => m.id)
    setSelectionIds((actuels) => cocher
      ? [...new Set([...actuels, ...idsVisibles])]
      : actuels.filter((id) => !idsVisibles.includes(id)))
  }

  const selectionner = (id, cocher) => {
    setSelectionIds((actuels) => cocher
      ? [...new Set([...actuels, id])]
      : actuels.filter((selectionne) => selectionne !== id))
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
                onChange={(e) => {
                  setSelectionIds([])
                  setFiltreStatut(e.target.value)
                }}
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
                onChange={(e) => {
                  setSelectionIds([])
                  setFiltreFormation(e.target.value)
                }}
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
                  onChange={(e) => {
                    setSelectionIds([])
                    setRecherche(e.target.value)
                  }}
                />
                {recherche && (
                  <button
                    type="button"
                    className="maq-effacer"
                    onClick={() => {
                      setSelectionIds([])
                      setRecherche('')
                    }}
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

      {peutAgir && (
        <section className="cand-panel" aria-labelledby="titre-actions-maquettes">
          <header className="cand-panel-head">
            <h2 className="cand-panel-title" id="titre-actions-maquettes">
              <i className="bi bi-check2-square" aria-hidden="true"></i>Actions sur la sélection
            </h2>
            <span className="cand-count-pill">
              {selectionIds.length} sélectionnée{selectionIds.length > 1 ? 's' : ''}
            </span>
          </header>
          <div className="cand-panel-body maq-outils">
            <div className="maq-outils-actions">
              {maquettesSelectionnees.length === 1 && (
                <>
                  <Link
                    className="maq-action"
                    to={`/scolarite/maquettes/${maquettesSelectionnees[0].id}`}
                  >
                    <i className="bi bi-eye" aria-hidden="true"></i>Consulter
                  </Link>
                  {maquettesSelectionnees[0].statut === 'BROUILLON' && (
                    <button
                      type="button"
                      className="maq-action"
                      disabled={enCours}
                      onClick={() => editer(maquettesSelectionnees[0])}
                    >
                      <i className="bi bi-pencil" aria-hidden="true"></i>Modifier
                    </button>
                  )}
                </>
              )}
              {selectionSupprimable && (
                <button
                  type="button"
                  className="maq-action maq-action--danger"
                  disabled={enCours}
                  onClick={supprimerSelection}
                >
                  <i className="bi bi-trash" aria-hidden="true"></i>
                  Supprimer la sélection
                </button>
              )}
            </div>
            <div className="maq-outils-export">
              <label className="maq-detaille">
                <input
                  type="checkbox"
                  checked={exportDetaille}
                  onChange={(e) => setExportDetaille(e.target.checked)}
                />
                Inclure les UE/ECUE et volumes horaires
              </label>
              {[
                ['word', 'Word', 'bi-file-earmark-word'],
                ['pdf', 'PDF', 'bi-file-earmark-pdf'],
                ['excel', 'Excel', 'bi-file-earmark-excel'],
                ['csv', 'CSV', 'bi-filetype-csv'],
              ].map(([format, label, icone]) => (
                <button
                  type="button"
                  className="maq-action"
                  key={format}
                  disabled={!selectionIds.length || enCours}
                  onClick={() => exporter(format)}
                >
                  <i className={`bi ${icone}`} aria-hidden="true"></i>{label}
                </button>
              ))}
            </div>
            <div className="maq-import">
              <label className="cand-etiquette" htmlFor="maq-import-fichier">
                Importer une maquette (.xlsx ou .csv)
              </label>
              <div className="maq-import-actions">
                <input
                  id="maq-import-fichier"
                  type="file"
                  accept=".xlsx,.csv"
                  onChange={(e) => {
                    setFichierImport(e.target.files?.[0] || null)
                    setApercuImport(null)
                  }}
                />
                <button
                  type="button"
                  className="maq-action"
                  disabled={!fichierImport || importEnCours}
                  onClick={previsualiserImport}
                >
                  <i className="bi bi-search" aria-hidden="true"></i>Prévisualiser
                </button>
              </div>
              <p className="maq-import-aide">
                L’import est d’abord vérifié sans écriture. Les maquettes confirmées sont créées en brouillon.
              </p>
              {apercuImport && (
                <div className={`maq-apercu${apercuImport.valide ? ' is-valide' : ' is-invalide'}`} aria-live="polite">
                  {apercuImport.valide ? (
                    <>
                      <strong>
                        Aperçu valide : {apercuImport.maquettes} maquette(s), {apercuImport.ues} UE et {apercuImport.ecues} ECUE.
                      </strong>
                      {apercuImport.deja_importe && (
                        <p>Ce fichier a déjà été importé ; aucune donnée ne sera créée.</p>
                      )}
                      {apercuImport.avertissements?.length > 0 && (
                        <ul>{apercuImport.avertissements.map((message, index) => <li key={`${index}-${message}`}>{message}</li>)}</ul>
                      )}
                      <div className="maq-apercu-exemples">
                        {apercuImport.exemples?.map((ligne, index) => (
                          <span key={`${ligne.ue}-${ligne.ecue}-${index}`}>
                            {ligne.formation} · {ligne.niveau} · {ligne.ue || 'Sans UE'} / {ligne.ecue || 'Sans ECUE'}
                          </span>
                        ))}
                      </div>
                      <button
                        type="button"
                        className="maq-action maq-action--valider"
                        disabled={importEnCours || apercuImport.deja_importe}
                        onClick={confirmerImport}
                      >
                        <i className="bi bi-check2-circle" aria-hidden="true"></i>Confirmer l’import
                      </button>
                    </>
                  ) : (
                    <>
                      <strong>Le fichier contient des erreurs et ne peut pas être importé.</strong>
                      <ul>{(apercuImport.erreurs || []).map((message, index) => <li key={`${index}-${message}`}>{message}</li>)}</ul>
                    </>
                  )}
                </div>
              )}
            </div>
          </div>
        </section>
      )}

      {/* ── Création ── */}
      {peutAgir && (
        <section className="cand-panel" aria-labelledby="titre-nouvelle-maquette">
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
                  id="maq-annee" className="cand-saisie" required value={form.annee_academique_id}
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

      {/* ── Tableau des maquettes ── */}
      <section className="cand-panel" aria-labelledby="titre-liste-maquettes">
        <header className="cand-panel-head">
          <h2 className="cand-panel-title" id="titre-liste-maquettes">
            <i className="bi bi-table" aria-hidden="true"></i>Maquettes
          </h2>
          <span className="cand-count-pill">
            {maquettesFiltrees.length} maquette{maquettesFiltrees.length > 1 ? 's' : ''}
          </span>
        </header>

        <div className="cand-table-wrap">
          <table className="cand-table cand-table--maquettes">
            <thead>
              <tr>
                {peutAgir && (
                  <th scope="col" className="maq-col-selection">
                    <input
                      type="checkbox"
                      aria-label="Sélectionner toutes les maquettes affichées"
                      checked={selectionComplete}
                      onChange={(e) => selectionnerToutes(e.target.checked)}
                      disabled={!maquettesFiltrees.length}
                    />
                  </th>
                )}
                <th scope="col" className="maq-col-formation">Formation</th>
                <th scope="col" className="maq-col-niveau">Niveau</th>
                <th scope="col" className="maq-col-parcours">Parcours</th>
                <th scope="col" className="maq-col-annee">Année</th>
                <th scope="col" className="maq-col-version">Version</th>
                <th scope="col" className="maq-col-statut">Statut</th>
                <th scope="col" className="maq-col-ue">UE</th>
                <th scope="col" className="maq-col-credits">Crédits</th>
                {peutAgir && <th scope="col" className="cand-th-actions maq-col-actions">Actions</th>}
              </tr>
            </thead>
            <tbody>
              {chargement ? (
                <tr>
                  <td colSpan={peutAgir ? 10 : 8}>
                    <div className="cand-chargement">
                      <span className="spinner-border" role="status" aria-hidden="true"></span>
                      Chargement des maquettes…
                    </div>
                  </td>
                </tr>
              ) : maquettesFiltrees.length === 0 ? (
                <tr>
                  <td colSpan={peutAgir ? 10 : 8}>
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
                return (
                  <tr key={m.id} className={`maq-ligne--${(m.statut || '').toLowerCase()}`}>
                    {peutAgir && (
                      <td className="maq-col-selection">
                        <input
                          type="checkbox"
                          aria-label={`Sélectionner ${m.ref_formation} ${m.niveau}`}
                          checked={selectionIds.includes(m.id)}
                          onChange={(e) => selectionner(m.id, e.target.checked)}
                        />
                      </td>
                    )}
                    <td className="maq-col-formation">
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
                    <td className="maq-col-niveau"><span className="cand-badge-neutre">{m.niveau}</span></td>
                    <td className="maq-col-parcours">
                      {m.parcours
                        ? <span className="maq-parcours">{m.parcours}</span>
                        : <span className="cand-texte-doux">—</span>}
                    </td>
                    <td className="cand-col-etroit maq-col-annee"><span className="maq-annee">{m.annee_academique}</span></td>
                    <td className="maq-col-version"><span className="maq-chip">v{m.version}</span></td>
                    <td className="maq-col-statut">
                      <span className={`maq-statut text-bg-${BADGE_STATUT[m.statut] || 'secondary'}`}>
                        <i className={`bi ${ICONE_STATUT[m.statut] || 'bi-question-circle'}`} aria-hidden="true"></i>
                        {m.statut}
                      </span>
                    </td>
                    <td className="cand-col-etroit maq-col-ue"><span className="maq-nombre">{m.nb_ue}</span></td>
                    <td className="cand-col-etroit maq-col-credits">
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
                      <td className="cand-col-actions maq-col-actions">
                        <div className="cand-actions maq-actions">
                          {m.statut === 'BROUILLON' && (
                            <button
                              type="button" className="maq-action maq-action--valider" disabled={enCours}
                              title="Valider cette maquette (contenu gelé)"
                              onClick={() => action(m, 'valider', 'Valider cette maquette (contenu gelé) ?')}>
                              <i className="bi bi-check2-circle" aria-hidden="true"></i>Valider
                            </button>
                          )}
                          {m.statut === 'BROUILLON' && (
                            <>
                              <button
                                type="button"
                                className="maq-action"
                                disabled={enCours}
                                title="Modifier cette maquette"
                                aria-label={`Modifier ${m.ref_formation}`}
                                onClick={() => editer(m)}>
                                <i className="bi bi-pencil" aria-hidden="true"></i>Modifier
                              </button>
                              <button
                                type="button"
                                className="maq-action maq-action--danger"
                                disabled={enCours || m.nb_ue > 0}
                                title={m.nb_ue > 0 ? 'Une maquette contenant des UE ne peut pas être supprimée.' : 'Supprimer ce brouillon'}
                                aria-label={`Supprimer ${m.ref_formation}`}
                                onClick={() => supprimerMaquette(m)}>
                                <i className="bi bi-trash" aria-hidden="true"></i>Supprimer
                              </button>
                            </>
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
      </section>
      {maquetteEditee && (
        <div className="maq-modal-fond" role="presentation">
          <section
            className="maq-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="titre-modifier-maquette"
          >
            <header className="maq-modal-entete">
              <h2 id="titre-modifier-maquette">Modifier la maquette</h2>
              <button
                type="button"
                className="maq-modal-fermer"
                aria-label="Fermer"
                onClick={() => setMaquetteEditee(null)}
              >
                <i className="bi bi-x-lg" aria-hidden="true"></i>
              </button>
            </header>
            <form onSubmit={enregistrerEdition}>
              <label className="cand-etiquette" htmlFor="maq-edition-libelle">Libellé personnalisé</label>
              <input
                id="maq-edition-libelle"
                className="cand-saisie"
                value={formEdition.libelle}
                onChange={(e) => setFormEdition({ ...formEdition, libelle: e.target.value })}
              />
              <label className="cand-etiquette" htmlFor="maq-edition-commentaire">Commentaire</label>
              <textarea
                id="maq-edition-commentaire"
                className="cand-saisie"
                rows="3"
                value={formEdition.commentaire_validation}
                onChange={(e) => setFormEdition({ ...formEdition, commentaire_validation: e.target.value })}
              />
              <footer className="maq-modal-actions">
                <button type="button" className="maq-action" onClick={() => setMaquetteEditee(null)}>
                  Annuler
                </button>
                <button type="submit" className="maq-action maq-action--valider" disabled={enCours}>
                  Enregistrer
                </button>
              </footer>
            </form>
          </section>
        </div>
      )}
    </div>
  )
}
