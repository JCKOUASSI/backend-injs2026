import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import api from '../../services/api'
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

export default function Maquettes() {
  const { user } = useAuth()
  const toast = useToast()
  const peutAgir = canActScolarite(user)

  const [maquettes, setMaquettes] = useState([])
  const [chargement, setChargement] = useState(true)
  const [filtreStatut, setFiltreStatut] = useState('')
  const [recherche, setRecherche] = useState('')
  const [enCours, setEnCours] = useState(false)
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

  // Statistiques calculées
  const stats = useMemo(() => {
    const total = maquettes.length
    const actives = maquettes.filter((m) => m.statut === 'ACTIVE').length
    const validees = maquettes.filter((m) => m.statut === 'VALIDEE').length
    const brouillons = maquettes.filter((m) => m.statut === 'BROUILLON').length
    return { total, actives, validees, brouillons }
  }, [maquettes])

  // Filtrage local par recherche textuelle
  const maquettesFiltrees = useMemo(() => {
    if (!recherche.trim()) return maquettes
    const q = recherche.toLowerCase()
    return maquettes.filter(
      (m) =>
        (m.ref_formation || '').toLowerCase().includes(q) ||
        (m.niveau || '').toLowerCase().includes(q) ||
        (m.parcours || '').toLowerCase().includes(q) ||
        (m.annee_academique || '').toLowerCase().includes(q),    )
  }, [maquettes, recherche])

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
            <i className="bi bi-shield-lock" aria-hidden="true"></i>
            Actives immuables
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
          </div>
        </div>
        <div className="cand-kpi">
          <span className="cand-kpi-icon is-green" aria-hidden="true"><i className="bi bi-check2-circle"></i></span>
          <div className="cand-kpi-texte">
            <span className="cand-kpi-value">{stats.actives}</span>
            <span className="cand-kpi-label">Actives (immuables)</span>
          </div>
        </div>
        <div className="cand-kpi">
          <span className="cand-kpi-icon is-slate" aria-hidden="true"><i className="bi bi-lock"></i></span>
          <div className="cand-kpi-texte">
            <span className="cand-kpi-value">{stats.validees}</span>
            <span className="cand-kpi-label">Validées (gelées)</span>
          </div>
        </div>
        <div className="cand-kpi">
          <span className="cand-kpi-icon is-amber" aria-hidden="true"><i className="bi bi-pencil-square"></i></span>
          <div className="cand-kpi-texte">
            <span className="cand-kpi-value">{stats.brouillons}</span>
            <span className="cand-kpi-label">Brouillons</span>
          </div>
        </div>
      </div>

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
                  <td colSpan={peutAgir ? 9 : 8}>
                    <div className="cand-chargement">
                      <span className="spinner-border" role="status" aria-hidden="true"></span>
                      Chargement des maquettes…
                    </div>
                  </td>
                </tr>
              ) : maquettesFiltrees.length === 0 ? (
                <tr>
                  <td colSpan={peutAgir ? 9 : 8}>
                    <div className="cand-vide">
                      <span className="cand-vide-icone" aria-hidden="true">
                        <i className="bi bi-inbox"></i>
                      </span>
                      <p className="cand-vide-titre">Aucune maquette.</p>
                      <p className="cand-vide-texte">
                        {recherche || filtreStatut
                          ? 'Aucune maquette ne correspond aux filtres sélectionnés.'
                          : 'Créez une première maquette pour structurer les UE/ECUE d’un parcours.'}
                      </p>
                    </div>
                  </td>
                </tr>
              ) : maquettesFiltrees.map((m) => (
                <tr key={m.id}>
                  <td>
                    <span className="maq-formation">
                      <span className="maq-formation-icone" aria-hidden="true">
                        <i className="bi bi-mortarboard"></i>
                      </span>
                      <Link to={`/scolarite/maquettes/${m.id}`} className="maq-lien">
                        {m.ref_formation}
                      </Link>
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
                      {m.statut}
                    </span>
                  </td>
                  <td className="cand-col-etroit"><span className="maq-nombre">{m.nb_ue}</span></td>
                  <td className="cand-col-etroit">
                    <span className="maq-nombre">{m.total_credits}</span>
                    <span className="maq-unite"> cr.</span>
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
              ))}
            </tbody>
          </table>
        </div>
        <p className="cand-defile" aria-hidden="true">
          <i className="bi bi-arrow-left-right"></i>
          Faites défiler le tableau horizontalement
        </p>
      </section>
    </div>
  )
}
