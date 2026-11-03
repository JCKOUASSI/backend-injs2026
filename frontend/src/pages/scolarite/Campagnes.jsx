import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import api from '../../services/api'
import { canActScolarite } from '../../utils/roles'
import { useAuth } from '../../context/AuthContext'
import { useToast } from '../../context/ToastContext'
import StatutBadge from '../../components/scolarite/StatutBadge'
import ChampDate, {
  dateFrancaiseVersIso, erreurDateFrancaise,
} from '../../components/scolarite/ChampDate'
import '../../styles/candidatures.css'
import '../../styles/campagnes.css'

const LIBELLES_STATUT = {
  BROUILLON: 'Brouillon', PLANIFIEE: 'Planifiée', OUVERTE: 'Ouverte',
  SUSPENDUE: 'Suspendue', CLOTUREE: 'Clôturée', ANNULEE: 'Annulée', ARCHIVEE: 'Archivée',
}

/* Une transition = un bouton : libellé court, icône décorative et variante de
   couleur cohérente avec le statut visé. */
const ACTIONS = {
  PLANIFIEE: { libelle: 'Planifier', icone: 'bi-calendar-check', variante: 'info' },
  OUVERTE: { libelle: 'Ouvrir', icone: 'bi-door-open', variante: 'succes' },
  SUSPENDUE: { libelle: 'Suspendre', icone: 'bi-pause-circle', variante: 'attention' },
  CLOTUREE: { libelle: 'Clôturer', icone: 'bi-lock', variante: 'neutre' },
  ARCHIVEE: { libelle: 'Archiver', icone: 'bi-archive', variante: 'neutre' },
  ANNULEE: { libelle: 'Annuler', icone: 'bi-x-octagon', variante: 'danger' },
}

const formaterDate = (iso) => {
  if (!iso) return null
  const [a, m, j] = String(iso).split('-')
  return (a && m && j) ? `${j}/${m}/${a}` : iso
}

const formVide = {
  libelle: '', annee_academique_id: '', ref_formation_id: '',
  date_ouverture: '', date_fermeture: '', quota_admissibles: '', quota_admis: '',
}

export default function Campagnes() {
  const { user } = useAuth()
  const toast = useToast()
  const peutAgir = canActScolarite(user)

  const [campagnes, setCampagnes] = useState([])
  const [chargement, setChargement] = useState(true)
  const [enCours, setEnCours] = useState(false)
  const [form, setForm] = useState({ ...formVide })
  const [options, setOptions] = useState({ annees: [], formations: [] })
  const [filtres, setFiltres] = useState({ q: '', statut: '', formation: '' })

  const charger = useCallback(async () => {
    setChargement(true)
    try {
      const res = await api.get('/admissions/campagnes/')
      setCampagnes(res.data)
    } catch (err) {
      toast.showToast(err.response?.data?.error || 'Chargement des campagnes impossible.', 'error')
    } finally {
      setChargement(false)
    }
  }, [toast])

  useEffect(() => { charger() }, [charger])

  useEffect(() => {
    if (!peutAgir) return
    Promise.all([
      api.get('/scolarite/ref/annees/', { params: { actif: 'true' } }),
      api.get('/scolarite/ref/formations/'),
    ])
      .then(([annees, formations]) => setOptions({ annees: annees.data, formations: formations.data }))
      .catch(() => toast.showToast('Chargement des référentiels impossible.', 'error'))
  }, [peutAgir, toast])

  const creer = async (e) => {
    e.preventDefault()
    // Les dates sont saisies en JJ/MM/AAAA : validation locale puis
    // conversion en ISO (AAAA-MM-JJ) pour l'API.
    const erreurDates = erreurDateFrancaise(form.date_ouverture, 'La date d’ouverture')
      || erreurDateFrancaise(form.date_fermeture, 'La date de fermeture')
    if (erreurDates) {
      toast.showToast(erreurDates, 'error')
      return
    }
    const ouvertureIso = dateFrancaiseVersIso(form.date_ouverture)
    const fermetureIso = dateFrancaiseVersIso(form.date_fermeture)
    if (ouvertureIso && fermetureIso && fermetureIso < ouvertureIso) {
      toast.showToast('La fermeture doit être postérieure ou égale à l’ouverture.', 'error')
      return
    }
    setEnCours(true)
    try {
      await api.post('/admissions/campagnes/', {
        ...form,
        date_ouverture: ouvertureIso || undefined,
        date_fermeture: fermetureIso || undefined,
        annee_academique_id: Number(form.annee_academique_id) || undefined,
        ref_formation_id: Number(form.ref_formation_id) || undefined,
        quota_admissibles: Number(form.quota_admissibles) || undefined,
        quota_admis: Number(form.quota_admis) || undefined,
      })
      toast.showToast('Campagne créée en brouillon.')
      setForm({ ...formVide })
      charger()
    } catch (err) {
      toast.showToast(err.response?.data?.error || 'Création impossible.', 'error')
    } finally {
      setEnCours(false)
    }
  }

  const transition = async (campagne, statut, confirmation) => {
    if (confirmation && !window.confirm(confirmation)) return
    setEnCours(true)
    try {
      await api.post(`/admissions/campagnes/${campagne.id}/transition/`, { statut })
      toast.showToast(`Campagne ${statut.toLowerCase()}.`)
      charger()
    } catch (err) {
      toast.showToast(err.response?.data?.error || 'Transition impossible.', 'error')
    } finally {
      setEnCours(false)
    }
  }

  const intituleFormation = (c) =>
    options.formations.find((f) => f.id === c.ref_formation_id)?.intitule
    || c.ref_formation_intitule || c.ref_formation || c.ref_formation_id || '—'
  const libelleAnnee = (c) =>
    options.annees.find((a) => a.id === c.annee_academique_id)?.libelle
    || c.annee_academique_libelle || c.annee_academique || c.annee_academique_id || '—'

  const campagnesFiltrees = useMemo(() => {
    const q = filtres.q.trim().toLowerCase()
    return campagnes.filter((c) => {
      if (filtres.statut && c.statut !== filtres.statut) return false
      if (filtres.formation && String(c.ref_formation_id) !== String(filtres.formation)) return false
      if (q && !`${c.libelle || ''} ${intituleFormation(c)}`.toLowerCase().includes(q)) return false
      return true
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [campagnes, filtres, options])

  const kpis = useMemo(() => ({
    total: campagnes.length,
    brouillons: campagnes.filter((c) => c.statut === 'BROUILLON').length,
    ouvertes: campagnes.filter((c) => ['OUVERTE', 'PLANIFIEE', 'SUSPENDUE'].includes(c.statut)).length,
    candidatures: campagnes.reduce((s, c) => s + (Number(c.nb_candidatures) || 0), 0),
  }), [campagnes])

  // L'API renvoie les années par ordre décroissant : l'année affichée est
  // celle marquée courante, pas la plus récente de la liste.
  const anneeCourante = (options.annees.find((a) => a.courante) || options.annees[0])?.libelle

  /* Actions possibles depuis chaque statut (miroir des transitions serveur). */
  const transitionsDe = (c) => {
    if (c.statut === 'BROUILLON') {
      return [
        { statut: 'PLANIFIEE' },
        { statut: 'ANNULEE', confirmation: 'Annuler cette campagne ?' },
      ]
    }
    if (c.statut === 'PLANIFIEE') {
      return [
        { statut: 'OUVERTE', confirmation: 'Ouvrir la campagne aux candidatures ?' },
        { statut: 'ANNULEE', confirmation: 'Annuler cette campagne ?' },
      ]
    }
    if (c.statut === 'OUVERTE') {
      return [
        { statut: 'SUSPENDUE' },
        { statut: 'CLOTUREE', confirmation: 'Clôturer ? Plus aucune candidature ne sera acceptée.' },
      ]
    }
    // Une campagne suspendue se rouvre (libellé explicite) ou se clôture.
    if (c.statut === 'SUSPENDUE') {
      return [
        { statut: 'OUVERTE', libelle: 'Réouvrir' },
        { statut: 'CLOTUREE', confirmation: 'Clôturer ? Plus aucune candidature ne sera acceptée.' },
      ]
    }
    if (c.statut === 'CLOTUREE') return [{ statut: 'ARCHIVEE' }]
    return []
  }

  return (
    <div className="cand-page camp-page">
      {/* ── Bandeau d'accueil, même matière que Candidatures / Inscriptions ── */}
      <div className="cand-hero">
        <div className="cand-hero-identite">
          <span className="cand-hero-icone" aria-hidden="true">
            <i className="bi bi-megaphone"></i>
          </span>
          <div className="cand-hero-text">
            <span className="cand-hero-badge">Scolarité — Admissions</span>
            <h1 className="cand-hero-title">Campagnes d&apos;admission</h1>
            <p className="cand-hero-sub">Fenêtres de candidature par formation</p>
            <span className="camp-cycle">
              {['Brouillon', 'Planifiée', 'Ouverte', 'Clôturée', 'Archivée'].map((etape, i) => (
                <React.Fragment key={etape}>
                  {i > 0 && <i className="bi bi-chevron-right" aria-hidden="true"></i>}
                  <span className="camp-cycle-etape">{etape}</span>
                </React.Fragment>
              ))}
            </span>
          </div>
        </div>
        <div className="camp-pastilles">
          <span className="cand-count-pill">
            <i className="bi bi-mortarboard" aria-hidden="true"></i>
            {anneeCourante || 'Année en cours'}
          </span>
          <span className="cand-count-pill">
            <i className="bi bi-diagram-3" aria-hidden="true"></i>
            {kpis.total} campagne{kpis.total > 1 ? 's' : ''}
          </span>
        </div>
      </div>

      {/* ── Indicateurs ── */}
      <div className="cand-kpi-row">
        <div className="cand-kpi">
          <span className="cand-kpi-icon is-blue" aria-hidden="true"><i className="bi bi-megaphone"></i></span>
          <div className="cand-kpi-texte">
            <span className="cand-kpi-value">{kpis.total}</span>
            <span className="cand-kpi-label">Campagnes</span>
          </div>
        </div>
        <div className="cand-kpi">
          <span className="cand-kpi-icon is-slate" aria-hidden="true"><i className="bi bi-pencil-square"></i></span>
          <div className="cand-kpi-texte">
            <span className="cand-kpi-value">{kpis.brouillons}</span>
            <span className="cand-kpi-label">En brouillon</span>
          </div>
        </div>
        <div className="cand-kpi">
          <span className="cand-kpi-icon is-green" aria-hidden="true"><i className="bi bi-door-open"></i></span>
          <div className="cand-kpi-texte">
            <span className="cand-kpi-value">{kpis.ouvertes}</span>
            <span className="cand-kpi-label">Actives / planifiées</span>
          </div>
        </div>
        <div className="cand-kpi">
          <span className="cand-kpi-icon is-amber" aria-hidden="true"><i className="bi bi-people"></i></span>
          <div className="cand-kpi-texte">
            <span className="cand-kpi-value">{kpis.candidatures}</span>
            <span className="cand-kpi-label">Candidatures</span>
          </div>
        </div>
      </div>

      {peutAgir && (
        <section className="cand-panel card camp-form-panel" aria-labelledby="titre-nouvelle-campagne">
          <header className="cand-panel-head">
            <h2 className="cand-panel-title" id="titre-nouvelle-campagne">
              <i className="bi bi-plus-circle" aria-hidden="true"></i>Nouvelle campagne
            </h2>
            <span className="cand-count-pill">
              <i className="bi bi-pencil-square" aria-hidden="true"></i>Créée en brouillon
            </span>
          </header>

          <form className="cand-panel-body" onSubmit={creer}>
            <div className="cand-grille-form">
              <div className="cand-champ cand-champ--2">
                <label className="cand-etiquette" htmlFor="camp-libelle">Libellé *</label>
                <input
                  id="camp-libelle" className="cand-saisie" placeholder="Libellé" required
                  value={form.libelle}
                  onChange={(e) => setForm({ ...form, libelle: e.target.value })}
                />
              </div>
              <div className="cand-champ">
                <label className="cand-etiquette" htmlFor="camp-annee">Année académique *</label>
                <select
                  id="camp-annee" className="cand-saisie" required
                  value={form.annee_academique_id}
                  onChange={(e) => setForm({ ...form, annee_academique_id: e.target.value })}
                >
                  <option value="">Année…</option>
                  {options.annees.map((a) => <option key={a.id} value={a.id}>{a.libelle}</option>)}
                </select>
              </div>
              <div className="cand-champ">
                <label className="cand-etiquette" htmlFor="camp-formation">Formation *</label>
                <select
                  id="camp-formation" className="cand-saisie" required
                  value={form.ref_formation_id}
                  onChange={(e) => setForm({ ...form, ref_formation_id: e.target.value })}
                >
                  <option value="">Formation…</option>
                  {options.formations.map((f) => <option key={f.id} value={f.id}>{f.intitule}</option>)}
                </select>
              </div>

              <fieldset className="cand-champ cand-champ--2 camp-groupe">
                <legend className="camp-groupe-titre">
                  <i className="bi bi-calendar3" aria-hidden="true"></i>
                  Période de candidature
                </legend>
                <div className="camp-duo">
                  <div className="cand-champ">
                    <label className="cand-etiquette" htmlFor="camp-ouv">Ouverture</label>
                    <ChampDate
                      id="camp-ouv"
                      valeur={form.date_ouverture}
                      onChange={(texte) => setForm({ ...form, date_ouverture: texte })}
                      reculAnnees={0} futurInterdit={false}
                      etiquetteCalendrier="Choisir la date d’ouverture"
                    />
                  </div>
                  <div className="cand-champ">
                    <label className="cand-etiquette" htmlFor="camp-ferm">Fermeture</label>
                    <ChampDate
                      id="camp-ferm"
                      valeur={form.date_fermeture}
                      onChange={(texte) => setForm({ ...form, date_fermeture: texte })}
                      reculAnnees={0} futurInterdit={false}
                      etiquetteCalendrier="Choisir la date de fermeture"
                    />
                  </div>
                </div>
              </fieldset>

              <fieldset className="cand-champ cand-champ--2 camp-groupe">
                <legend className="camp-groupe-titre">
                  <i className="bi bi-sliders2" aria-hidden="true"></i>
                  Quotas (optionnel)
                </legend>
                <div className="camp-duo">
                  <div className="cand-champ">
                    <label className="cand-etiquette" htmlFor="camp-qa">Admissibles</label>
                    <input
                      id="camp-qa" type="number" min="0" className="cand-saisie" placeholder="Quota admiss."
                      title="Quota d'admissibles (optionnel)" value={form.quota_admissibles}
                      onChange={(e) => setForm({ ...form, quota_admissibles: e.target.value })}
                    />
                  </div>
                  <div className="cand-champ">
                    <label className="cand-etiquette" htmlFor="camp-qad">Admis</label>
                    <input
                      id="camp-qad" type="number" min="0" className="cand-saisie" placeholder="Quota admis"
                      title="Quota d'admis (optionnel)" value={form.quota_admis}
                      onChange={(e) => setForm({ ...form, quota_admis: e.target.value })}
                    />
                  </div>
                </div>
              </fieldset>

              <div className="cand-champ cand-champ--4 camp-form-note">
                <p className="camp-note">
                  <i className="bi bi-info-circle" aria-hidden="true"></i>
                  Admissibles = classement · Admis = admis final. Laissez vide pour une campagne sans quota.
                </p>
              </div>
            </div>

            <div className="cand-form-actions">
              <button type="submit" className="cand-btn-principal" disabled={enCours}>
                {enCours
                  ? <span className="spinner-border" aria-hidden="true"></span>
                  : <i className="bi bi-check2-circle" aria-hidden="true"></i>}
                Créer
              </button>
            </div>
          </form>
        </section>
      )}

      <section className="cand-panel" aria-labelledby="titre-dossiers-campagne">
        <header className="cand-panel-head">
          <h2 className="cand-panel-title" id="titre-dossiers-campagne">
            <i className="bi bi-list-check" aria-hidden="true"></i>Dossiers de campagne
          </h2>
          <span className="cand-count-pill">
            {campagnesFiltrees.length} dossier{campagnesFiltrees.length > 1 ? 's' : ''}
          </span>
        </header>

        <div className="cand-panel-body">
          <div className="cand-filters">
            <div className="cand-search">
              <i className="bi bi-search"></i>
              <input
                className="cand-input" type="search"
                placeholder="Rechercher un libellé, une formation…"
                aria-label="Rechercher une campagne" value={filtres.q}
                onChange={(e) => setFiltres({ ...filtres, q: e.target.value })}
              />
            </div>
            <select
              className="cand-filter-select" aria-label="Filtrer par statut"
              value={filtres.statut}
              onChange={(e) => setFiltres({ ...filtres, statut: e.target.value })}
            >
              <option value="">Tous les statuts</option>
              {Object.entries(LIBELLES_STATUT).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
            <select
              className="cand-filter-select" aria-label="Filtrer par formation"
              value={filtres.formation}
              onChange={(e) => setFiltres({ ...filtres, formation: e.target.value })}
            >
              <option value="">Toutes les formations</option>
              {options.formations.map((f) => <option key={f.id} value={f.id}>{f.intitule}</option>)}
            </select>
          </div>

          {chargement ? (
            <div className="cand-chargement">
              <span className="spinner-border" aria-hidden="true"></span>Chargement des campagnes…
            </div>
          ) : (
            <>
              <div className="cand-table-wrap">
                <table className="cand-table cand-table--campagnes">
                  <thead>
                    <tr>
                      <th scope="col">Formation</th>
                      <th scope="col">Période de candidature</th>
                      <th scope="col">Quotas</th>
                      <th scope="col">Statut</th>
                      <th scope="col">Candidatures</th>
                      {peutAgir && <th scope="col" className="cand-th-actions">Transitions</th>}
                    </tr>
                  </thead>
                  <tbody>
                    {campagnesFiltrees.map((c) => {
                      const ouv = formaterDate(c.date_ouverture)
                      const ferm = formaterDate(c.date_fermeture)
                      const actions = peutAgir ? transitionsDe(c) : []
                      return (
                        <tr key={c.id}>
                          <td className="camp-col-formation">
                            <Link
                              className="camp-link"
                              to={`/scolarite/campagnes/${c.id}`}
                              title={intituleFormation(c)}
                            >
                              {intituleFormation(c)}
                            </Link>
                            <span className="cand-sr-only">{c.libelle}</span>
                            <span className="camp-sub">
                              <i className="bi bi-mortarboard" aria-hidden="true"></i>{libelleAnnee(c)}
                            </span>
                          </td>
                          <td>
                            {ouv || ferm ? (
                              <span className="camp-periode">
                                <span className="camp-date">{ouv || '…'}</span>
                                <i className="bi bi-arrow-right" aria-hidden="true"></i>
                                <span className="camp-date">{ferm || '…'}</span>
                              </span>
                            ) : null}
                            {!ouv && !ferm && (
                              c.statut === 'BROUILLON' ? (
                                <span className="camp-sub warn">
                                  <i className="bi bi-exclamation-circle" aria-hidden="true"></i>
                                  Dates à compléter avant planification
                                </span>
                              ) : <span className="cand-texte-doux">—</span>
                            )}
                          </td>
                          <td>
                            {(c.quota_admissibles ?? c.quota_admis) != null ? (
                              <span className="camp-quotas">
                                <span className="camp-quota">
                                  <span className="camp-quota-cle">Admissibles</span>
                                  <span className="camp-quota-valeur">{c.quota_admissibles ?? '—'}</span>
                                </span>
                                <span className="camp-quota">
                                  <span className="camp-quota-cle">Admis</span>
                                  <span className="camp-quota-valeur">{c.quota_admis ?? '—'}</span>
                                </span>
                              </span>
                            ) : <span className="cand-texte-doux">Sans quota</span>}
                          </td>
                          <td>
                            <StatutBadge statut={c.statut} libelle={LIBELLES_STATUT[c.statut] || c.statut} />
                          </td>
                          <td>
                            <span className="camp-candidatures">
                              <i className="bi bi-people" aria-hidden="true"></i>
                              {c.nb_candidatures ?? 0}
                            </span>
                          </td>
                          {peutAgir && (
                            <td className="cand-col-actions">
                              <div className="camp-actions">
                                {actions.map(({ statut, confirmation, libelle }) => {
                                  const a = ACTIONS[statut]
                                  return (
                                    <button
                                      key={statut}
                                      type="button"
                                      className={`camp-action camp-action--${a.variante}`}
                                      disabled={enCours}
                                      onClick={() => transition(c, statut, confirmation)}
                                    >
                                      <i className={`bi ${a.icone}`} aria-hidden="true"></i>
                                      {libelle || a.libelle}
                                    </button>
                                  )
                                })}
                                {actions.length === 0 && (
                                  <span className="cand-texte-doux">Aucune transition</span>
                                )}
                              </div>
                            </td>
                          )}
                        </tr>
                      )
                    })}
                    {campagnesFiltrees.length === 0 && (
                      <tr>
                        <td colSpan={peutAgir ? 6 : 5}>
                          <div className="cand-vide">
                            <span className="cand-vide-icone" aria-hidden="true">
                              <i className="bi bi-megaphone"></i>
                            </span>
                            <p className="cand-vide-titre">
                              {campagnes.length === 0 ? 'Aucune campagne' : 'Aucun résultat'}
                            </p>
                            <p className="cand-vide-texte">
                              {campagnes.length === 0
                                ? 'Créez votre première campagne avec le formulaire ci-dessus : elle démarre en brouillon.'
                                : 'Aucune campagne ne correspond à la recherche ou aux filtres sélectionnés.'}
                            </p>
                          </div>
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
              <p className="cand-defile" aria-hidden="true">
                <i className="bi bi-arrow-left-right"></i>
                Faites défiler le tableau horizontalement
              </p>
            </>
          )}
        </div>
      </section>
    </div>
  )
}
