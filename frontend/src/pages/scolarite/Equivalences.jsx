import React, { useCallback, useEffect, useMemo, useState } from 'react'
import api from '../../services/api'
import { canActScolarite } from '../../utils/roles'
import { useAuth } from '../../context/AuthContext'
import { useToast } from '../../context/ToastContext'
import '../../styles/candidatures.css'
import '../../styles/equivalences.css'

const BADGE_STATUT = {
  BROUILLON: 'secondary', SOUMISE: 'info', EN_INSTRUCTION: 'info',
  A_COMPLETER: 'warning', AVIS_PEDAGOGIQUE: 'primary', DECISION: 'primary',
  VALIDEE: 'success', REJETEE: 'danger', APPLIQUEE: 'dark',
}

// Teinte du chip de décision : lecture immédiate du sens (visuel seul).
const BADGE_DECISION = { FAVORABLE: 'text-bg-success', DEFAVORABLE: 'text-bg-danger' }

// Étapes « vivantes » du cycle : la demande n'est pas encore tranchée.
const STATUTS_EN_COURS = ['SOUMISE', 'EN_INSTRUCTION', 'AVIS_PEDAGOGIQUE', 'DECISION']
// Étapes abouties : décision rendue puis (éventuellement) appliquée.
const STATUTS_ABOUTIES = ['VALIDEE', 'APPLIQUEE']

export default function Equivalences() {
  const { user } = useAuth()
  const toast = useToast()
  const peutAgir = canActScolarite(user)

  const [demandes, setDemandes] = useState([])
  const [chargement, setChargement] = useState(true)
  const [enCours, setEnCours] = useState(false)
  const [selection, setSelection] = useState(null)
  const [form, setForm] = useState({
    type_demande: 'DISPENSE', etudiant_id: '', annee_academique_id: '',
    ref_formation_id: '', niveau_id: '', etablissement_origine: '', diplome_origine: '',
  })
  const [formDecision, setFormDecision] = useState({
    decision: 'FAVORABLE', credits_reconnus: '', note_transferee: '',
    autorite_validation: 'Direction des études INJS', analyse_pedagogique: '',
  })
  const [options, setOptions] = useState({ annees: [], formations: [], niveaux: [], etudiants: [] })

  const charger = useCallback(async () => {
    setChargement(true)
    try {
      const res = await api.get('/equivalences/demandes/')
      setDemandes(res.data)
    } catch (err) {
      toast.showToast(err.response?.data?.error || 'Chargement impossible.', 'error')
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
      api.get('/scolarite/ref/niveaux/', { params: { actif: 'true' } }),
      api.get('/scolarite/etudiants/'),
    ])
      .then(([annees, formations, niveaux, etudiants]) => setOptions({
        annees: annees.data, formations: formations.data,
        niveaux: niveaux.data, etudiants: etudiants.data,
      }))
      .catch(() => toast.showToast('Chargement des référentiels impossible.', 'error'))
  }, [peutAgir, toast])

  const creer = async (e) => {
    e.preventDefault()
    setEnCours(true)
    try {
      await api.post('/equivalences/demandes/', {
        ...form,
        annee_academique_id: Number(form.annee_academique_id) || undefined,
        ref_formation_id: Number(form.ref_formation_id) || undefined,
        niveau_id: Number(form.niveau_id) || undefined,
        etudiant_id: Number(form.etudiant_id) || undefined,
      })
      toast.showToast('Demande créée en brouillon.')
      charger()
    } catch (err) {
      toast.showToast(JSON.stringify(err.response?.data) || 'Création impossible.', 'error')
    } finally {
      setEnCours(false)
    }
  }

  const transition = async (demande, statut) => {
    setEnCours(true)
    try {
      await api.post(`/equivalences/demandes/${demande.id}/transition/`, { statut })
      toast.showToast(`Demande ${statut.toLowerCase()}.`)
      charger()
    } catch (err) {
      toast.showToast(err.response?.data?.error || 'Transition impossible.', 'error')
    } finally {
      setEnCours(false)
    }
  }

  const decider = async (demande) => {
    setEnCours(true)
    try {
      await api.post(`/equivalences/demandes/${demande.id}/decision/`, {
        ...formDecision,
        credits_reconnus: formDecision.credits_reconnus || undefined,
        note_transferee: formDecision.note_transferee || undefined,
      })
      toast.showToast('Décision enregistrée.')
      setSelection(null)
      charger()
    } catch (err) {
      toast.showToast(err.response?.data?.error || 'Décision impossible.', 'error')
    } finally {
      setEnCours(false)
    }
  }

  const appliquer = async (demande) => {
    if (!window.confirm('Appliquer cette dispense/équivalence (effet académique) ?')) return
    setEnCours(true)
    try {
      await api.post(`/equivalences/demandes/${demande.id}/appliquer/`, {})
      toast.showToast('Dispense/équivalence appliquée.')
      charger()
    } catch (err) {
      toast.showToast(err.response?.data?.error || 'Application impossible.', 'error')
    } finally {
      setEnCours(false)
    }
  }

  // Indicateurs de pilotage : calcul d'affichage, aucun appel supplémentaire.
  const stats = useMemo(() => ({
    total: demandes.length,
    enCours: demandes.filter((d) => STATUTS_EN_COURS.includes(d.statut)).length,
    abouties: demandes.filter((d) => STATUTS_ABOUTIES.includes(d.statut)).length,
    credits: demandes.reduce((somme, d) => somme + (Number(d.credits_reconnus) || 0), 0),
  }), [demandes])
  return (
    <div className="cand-page eq-page">
      {/* ── Bandeau d'accueil ── */}
      <div className="cand-hero">
        <div className="cand-hero-identite">
          <span className="cand-hero-icone" aria-hidden="true">
            <i className="bi bi-award"></i>
          </span>
          <div className="cand-hero-text">
            <span className="cand-hero-badge">Passerelles et continuité de parcours</span>
            <h1 className="cand-hero-title">Équivalences et dispenses</h1>
            <p className="cand-hero-sub">
              Reconnaissance des acquis antérieurs : instruction, avis pédagogique,
              décision motivée puis application au dossier de l&apos;étudiant.
            </p>
          </div>
        </div>
        <div className="eq-hero-pastilles">
          <span className="eq-pastille eq-pastille--primary">
            <i className="bi bi-collection" aria-hidden="true"></i>
            {demandes.length} demande{demandes.length > 1 ? 's' : ''}
          </span>
          <span className="eq-pastille eq-pastille--neutre">
            <i className="bi bi-shield-check" aria-hidden="true"></i>
            Application sous confirmation
          </span>
        </div>
      </div>

      {/* ── Indicateurs du cycle de vie ── */}
      <div className="cand-kpi-row">
        <div className="cand-kpi">
          <span className="cand-kpi-icon is-blue" aria-hidden="true"><i className="bi bi-collection"></i></span>
          <div className="cand-kpi-texte">
            <span className="cand-kpi-value">{stats.total}</span>
            <span className="cand-kpi-label">Demandes</span>
          </div>
        </div>
        <div className="cand-kpi">
          <span className="cand-kpi-icon is-amber" aria-hidden="true"><i className="bi bi-hourglass-split"></i></span>
          <div className="cand-kpi-texte">
            <span className="cand-kpi-value">{stats.enCours}</span>
            <span className="cand-kpi-label">En cours d&apos;instruction</span>
          </div>
        </div>
        <div className="cand-kpi">
          <span className="cand-kpi-icon is-green" aria-hidden="true"><i className="bi bi-patch-check"></i></span>
          <div className="cand-kpi-texte">
            <span className="cand-kpi-value">{stats.abouties}</span>
            <span className="cand-kpi-label">Validées / appliquées</span>
          </div>
        </div>
        <div className="cand-kpi">
          <span className="cand-kpi-icon is-slate" aria-hidden="true"><i className="bi bi-award"></i></span>
          <div className="cand-kpi-texte">
            <span className="cand-kpi-value">{stats.credits}</span>
            <span className="cand-kpi-label">Crédits reconnus</span>
          </div>
        </div>
      </div>

      {/* ── Création d'une demande ── */}
      {peutAgir && (
        <section className="cand-panel card eq-panneau" aria-labelledby="titre-nouvelle-demande">
          <header className="cand-panel-head">
            <h2 className="cand-panel-title" id="titre-nouvelle-demande">
              <i className="bi bi-plus-circle" aria-hidden="true"></i>
              Nouvelle demande
            </h2>
            <span className="cand-count-pill">Statut initial : brouillon</span>
          </header>
          <div className="cand-panel-body">
            <form className="cand-grille-form eq-form" onSubmit={creer}>
              <div className="cand-champ">
                <label className="cand-etiquette" htmlFor="eq-type">Type de demande</label>
                <select
                  id="eq-type" className="cand-saisie" value={form.type_demande}
                  onChange={(e) => setForm({ ...form, type_demande: e.target.value })}>
                  <option value="DISPENSE">Dispense</option>
                  <option value="EQUIVALENCE">Équivalence</option>
                </select>
              </div>
              <div className="cand-champ">
                <label className="cand-etiquette" htmlFor="eq-etudiant">Étudiant *</label>
                <select
                  id="eq-etudiant" className="cand-saisie" required value={form.etudiant_id}
                  onChange={(e) => setForm({ ...form, etudiant_id: e.target.value })}>
                  <option value="">Étudiant…</option>
                  {options.etudiants.map((e) => (
                    <option key={e.id} value={e.id}>{e.matricule} — {e.nom_complet}</option>
                  ))}
                </select>
              </div>
              <div className="cand-champ">
                <label className="cand-etiquette" htmlFor="eq-annee">Année académique *</label>
                <select
                  id="eq-annee" className="cand-saisie" required value={form.annee_academique_id}
                  onChange={(e) => setForm({ ...form, annee_academique_id: e.target.value })}>
                  <option value="">Année…</option>
                  {options.annees.map((a) => <option key={a.id} value={a.id}>{a.libelle}</option>)}
                </select>
              </div>
              <div className="cand-champ">
                <label className="cand-etiquette" htmlFor="eq-formation">Formation *</label>
                <select
                  id="eq-formation" className="cand-saisie" required value={form.ref_formation_id}
                  onChange={(e) => setForm({ ...form, ref_formation_id: e.target.value })}>
                  <option value="">Formation…</option>
                  {options.formations.map((f) => <option key={f.id} value={f.id}>{f.intitule}</option>)}
                </select>
              </div>
              <div className="cand-champ">
                <label className="cand-etiquette" htmlFor="eq-niveau">Niveau *</label>
                <select
                  id="eq-niveau" className="cand-saisie" required value={form.niveau_id}
                  onChange={(e) => setForm({ ...form, niveau_id: e.target.value })}>
                  <option value="">Niveau…</option>
                  {options.niveaux.map((n) => <option key={n.id} value={n.id}>{n.code}</option>)}
                </select>
              </div>
              <div className="eq-form-pied">
                <p className="eq-hint">
                  <i className="bi bi-info-circle" aria-hidden="true"></i>
                  La demande est ouverte au statut brouillon puis instruite tout au long du
                  cycle : soumission, instruction, avis pédagogique, décision, application.
                </p>
                <button
                  type="submit" className="eq-add-btn" aria-label="+"
                  title="Ajouter la demande" disabled={enCours}>
                  <i className="bi bi-plus-lg" aria-hidden="true"></i>
                </button>
              </div>
            </form>
          </div>
        </section>
      )}

      {/* ── Demandes : cycle de vie complet ── */}
      <section className="cand-panel" aria-labelledby="titre-demandes">
        <header className="cand-panel-head">
          <h2 className="cand-panel-title" id="titre-demandes">
            <i className="bi bi-table" aria-hidden="true"></i>
            Demandes
          </h2>
          <span className="cand-count-pill">
            {demandes.length} demande{demandes.length > 1 ? 's' : ''}
          </span>
        </header>

        <div className="cand-table-wrap">
          <table className="cand-table eq-table">
            <thead>
              <tr>
                <th scope="col">Type</th>
                <th scope="col">Matricule</th>
                <th scope="col">Formation</th>
                <th scope="col">Décision</th>
                <th scope="col">Statut</th>
                <th scope="col">Crédits</th>
                {peutAgir && <th scope="col" className="cand-th-actions">Actions</th>}
              </tr>
            </thead>
            <tbody>
              {chargement ? (
                <tr>
                  <td colSpan={peutAgir ? 7 : 6}>
                    <div className="cand-chargement">
                      <span className="spinner-border" role="status" aria-hidden="true"></span>
                      Chargement des demandes…
                    </div>
                  </td>
                </tr>
              ) : demandes.length === 0 ? (
                <tr>
                  <td colSpan={peutAgir ? 7 : 6}>
                    <div className="cand-vide">
                      <span className="cand-vide-icone" aria-hidden="true">
                        <i className="bi bi-inbox"></i>
                      </span>
                      <p className="cand-vide-titre">Aucune demande.</p>
                      <p className="cand-vide-texte">
                        Ouvrez une première demande de dispense ou d&apos;équivalence :
                        elle suivra le cycle d&apos;instruction jusqu&apos;à l&apos;application.
                      </p>
                    </div>
                  </td>
                </tr>
              ) : demandes.map((d) => (
                <tr key={d.id}>
                  <td>
                    <span className={`eq-type eq-type--${d.type_demande === 'EQUIVALENCE' ? 'equivalence' : 'dispense'}`}>
                      <i
                        className={`bi ${d.type_demande === 'EQUIVALENCE' ? 'bi-arrow-left-right' : 'bi-slash-circle'}`}
                        aria-hidden="true"
                      ></i>
                      {d.type_demande}
                    </span>
                  </td>
                  <td><span className="eq-matricule">{d.matricule}</span></td>
                  <td>
                    <span className="eq-formation" title={d.ref_formation}>{d.ref_formation}</span>
                  </td>
                  <td>
                    {d.decision ? (
                      <span className={`eq-decision ${BADGE_DECISION[d.decision] || 'text-bg-secondary'}`}>
                        {d.decision}
                      </span>
                    ) : (
                      <span className="cand-texte-doux">—</span>
                    )}
                  </td>
                  <td>
                    <span className={`eq-statut text-bg-${BADGE_STATUT[d.statut] || 'secondary'}`}>
                      {d.statut}
                    </span>
                  </td>
                  <td className="cand-col-etroit">
                    {d.credits_reconnus === null || d.credits_reconnus === undefined ? (
                      <span className="cand-texte-doux">—</span>
                    ) : (
                      <>
                        <span className="eq-credits">{d.credits_reconnus}</span>
                        <span className="eq-unite"> cr.</span>
                      </>
                    )}
                  </td>
                  {peutAgir && (
                    <td className="cand-col-actions">
                      <div className="cand-actions eq-actions">
                        {d.statut === 'BROUILLON' && (
                          <button
                            type="button" className="eq-action eq-action--soumettre" disabled={enCours}
                            title="Soumettre la demande à l'instruction"
                            onClick={() => transition(d, 'SOUMISE')}>
                            <i className="bi bi-send" aria-hidden="true"></i>Soumettre
                          </button>
                        )}
                        {d.statut === 'SOUMISE' && (
                          <button
                            type="button" className="eq-action eq-action--instruire" disabled={enCours}
                            title="Passer la demande en instruction"
                            onClick={() => transition(d, 'EN_INSTRUCTION')}>
                            <i className="bi bi-clipboard-check" aria-hidden="true"></i>Instruire
                          </button>
                        )}
                        {d.statut === 'EN_INSTRUCTION' && (
                          <button
                            type="button" className="eq-action eq-action--avis" disabled={enCours}
                            title="Saisir l'avis pédagogique"
                            onClick={() => transition(d, 'AVIS_PEDAGOGIQUE')}>
                            <i className="bi bi-mortarboard" aria-hidden="true"></i>Avis pédagogique
                          </button>
                        )}
                        {(d.statut === 'AVIS_PEDAGOGIQUE' || d.statut === 'DECISION') && (
                          <button
                            type="button" className="eq-action eq-action--decider"
                            title="Rendre la décision pédagogique"
                            onClick={() => setSelection(d)}>
                            <i className="bi bi-check2-square" aria-hidden="true"></i>Décider
                          </button>
                        )}
                        {d.statut === 'VALIDEE' && (
                          <button
                            type="button" className="eq-action eq-action--appliquer" disabled={enCours}
                            title="Appliquer la dispense ou l'équivalence au dossier"
                            onClick={() => appliquer(d)}>
                            <i className="bi bi-lightning-charge" aria-hidden="true"></i>Appliquer
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

      {/* ── Décision pédagogique ── */}
      {selection && (
        <section className="cand-panel card eq-panneau eq-panneau--decision" aria-labelledby="titre-decision">
          <header className="cand-panel-head">
            <h2 className="cand-panel-title" id="titre-decision">
              <i className="bi bi-clipboard2-check" aria-hidden="true"></i>
              Décision — demande #{selection.id}
            </h2>
            <span className="cand-count-pill">{selection.ref_formation}</span>
          </header>
          <div className="cand-panel-body">
            <form className="cand-grille-form eq-form eq-form--decision" onSubmit={(e) => { e.preventDefault(); decider(selection) }}>
              <div className="cand-champ">
                <label className="cand-etiquette" htmlFor="eq-decision">Décision</label>
                <select
                  id="eq-decision" className="cand-saisie" value={formDecision.decision}
                  onChange={(e) => setFormDecision({ ...formDecision, decision: e.target.value })}>
                  <option value="FAVORABLE">Favorable</option>
                  <option value="DEFAVORABLE">Défavorable</option>
                </select>
              </div>
              <div className="cand-champ">
                <label className="cand-etiquette" htmlFor="eq-credits">Crédits reconnus</label>
                <input
                  id="eq-credits" type="number" min="0" className="cand-saisie" placeholder="Crédits reconnus"
                  value={formDecision.credits_reconnus}
                  onChange={(e) => setFormDecision({ ...formDecision, credits_reconnus: e.target.value })}
                />
              </div>
              <div className="cand-champ">
                <label className="cand-etiquette" htmlFor="eq-note">Note transférée</label>
                <input
                  id="eq-note" type="number" step="0.25" min="0" max="20" className="cand-saisie"
                  placeholder="Note transférée" value={formDecision.note_transferee}
                  onChange={(e) => setFormDecision({ ...formDecision, note_transferee: e.target.value })}
                />
              </div>
              <div className="cand-champ">
                <label className="cand-etiquette" htmlFor="eq-autorite">Autorité de validation</label>
                <input
                  id="eq-autorite" className="cand-saisie" placeholder="Autorité de validation"
                  value={formDecision.autorite_validation}
                  onChange={(e) => setFormDecision({ ...formDecision, autorite_validation: e.target.value })}
                />
              </div>
              <div className="eq-form-pied">
                <p className="eq-hint">
                  <i className="bi bi-info-circle" aria-hidden="true"></i>
                  La décision est horodatée et rattachée à la demande ; l&apos;application au dossier
                  reste soumise à confirmation.
                </p>
                <div className="eq-form-boutons">
                  <button
                    type="button" className="cand-btn-fantome" disabled={enCours}
                    onClick={() => setSelection(null)}>
                    Annuler
                  </button>
                  <button type="submit" className="cand-btn-principal" disabled={enCours}>
                    <i className="bi bi-check2-circle" aria-hidden="true"></i>Enregistrer
                  </button>
                </div>
              </div>
            </form>
          </div>
        </section>
      )}
    </div>
  )
}
