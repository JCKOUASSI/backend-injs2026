import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useToast } from '../../context/ToastContext'
import StatutBadge from '../../components/scolarite/StatutBadge'
import '../../styles/candidatures.css'
import '../../styles/modale-premium.css'
import {
  createInscription, deleteInscription, getAnneeCourante, getInscription,
  getRefFormations, getRefScolarite, listEtudiants, listInscriptions,
  messageErreur, transitionInscription, updateInscription,
} from '../../services/scolarite'

const TYPES_INSCRIPTION = [
  ['PREMIERE', 'Première inscription'],
  ['REINSCRIPTION', 'Réinscription'],
  ['REDOUBLEMENT', 'Redoublement'],
  ['REPRISE', 'Reprise après suspension'],
  ['REORIENTATION', 'Réorientation'],
  ['TRANSFERT', 'Transfert'],
]

const STATUTS = [
  ['BROUILLON', 'Brouillon'], ['EN_ATTENTE', 'En attente'], ['A_VALIDER', 'À valider'],
  ['VALIDEE', 'Validée'], ['REJETEE', 'Rejetée'], ['ANNULEE', 'Annulée'],
  ['SUSPENDUE', 'Suspendue'], ['TERMINEE', 'Terminée'],
]
const CHEMIN_VALIDATION = {
  BROUILLON: ['EN_ATTENTE', 'A_VALIDER', 'VALIDEE'],
  EN_ATTENTE: ['A_VALIDER', 'VALIDEE'], A_VALIDER: ['VALIDEE'],
}

export default function Inscriptions() {
  const { showToast } = useToast()
  const [inscriptions, setInscriptions] = useState([])
  const [loading, setLoading] = useState(true)
  const [enCours, setEnCours] = useState(null)
  const [creation, setCreation] = useState(false)
  const [modification, setModification] = useState(null)
  const [dossier, setDossier] = useState(null)
  const [filtres, setFiltres] = useState({ statut: '', q: '' })

  const charger = useCallback(async () => {
    setLoading(true)
    try {
      const params = Object.fromEntries(Object.entries(filtres).filter(([, v]) => v !== ''))
      const res = await listInscriptions(params)
      setInscriptions(res.data)
    } catch (err) {
      showToast(messageErreur(err, 'Chargement des inscriptions impossible'), 'error')
    } finally { setLoading(false) }
  }, [filtres, showToast])

  useEffect(() => { charger() }, [charger])

  const valider = async (inscription) => {
    const etapes = CHEMIN_VALIDATION[inscription.statut]
    if (!etapes) return
    setEnCours(inscription.id)
    try {
      for (const statut of etapes) await transitionInscription(inscription.id, { statut })
      showToast('Inscription validée')
      charger()
    } catch (err) { showToast(messageErreur(err, 'Validation impossible'), 'error') }
    finally { setEnCours(null) }
  }

  const supprimer = async (id) => {
    if (!window.confirm('Supprimer cette inscription administrative ? Irréversible.')) return
    const precedent = inscriptions
    setInscriptions(inscriptions.filter((i) => i.id !== id))
    setEnCours(id)
    try {
      await deleteInscription(id)
      showToast('Inscription supprimée')
    } catch (err) {
      showToast(messageErreur(err, 'Suppression impossible'), 'error')
      setInscriptions(precedent)
    } finally { setEnCours(null) }
  }

  const kpis = useMemo(() => ({
    total: inscriptions.length,
    validees: inscriptions.filter((i) => i.statut === 'VALIDEE').length,
    attente: inscriptions.filter((i) => ['BROUILLON', 'EN_ATTENTE', 'A_VALIDER'].includes(i.statut)).length,
    rejectees: inscriptions.filter((i) => i.statut === 'REJETEE').length,
  }), [inscriptions])


  return (
    <div className="cand-page">
      <div className="camp-hero">
        <div className="camp-hero-text">
          <h1 className="camp-hero-title"><i className="bi bi-person-badge"></i>Inscriptions administratives</h1>
          <p className="camp-hero-sub">Créer, modifier, supprimer et suivre les inscriptions administratives des étudiants.</p>
        </div>
        <div className="camp-hero-actions">
          <button className="btn btn-primary cand-btn-pill" onClick={() => setCreation(true)}>
            <i className="bi bi-plus-lg me-1"></i>Nouvelle inscription
          </button>
          <a className="btn btn-outline-primary cand-btn-pill" href="/scolarite/admissions">
            <i className="bi bi-person-plus me-1"></i>Inscrire un admis
          </a>
        </div>
      </div>

      <div className="cand-kpi">
        <div className="cand-kpi-card"><div className="cand-kpi-value">{kpis.total}</div><div className="cand-kpi-label">Dossiers</div></div>
        <div className="cand-kpi-card"><div className="cand-kpi-value">{kpis.validees}</div><div className="cand-kpi-label">Validées</div></div>
        <div className="cand-kpi-card"><div className="cand-kpi-value">{kpis.attente}</div><div className="cand-kpi-label">En attente</div></div>
        <div className="cand-kpi-card"><div className="cand-kpi-value">{kpis.rejectees}</div><div className="cand-kpi-label">Rejetées</div></div>
      </div>

      <div className="cand-panel">
        <div className="cand-panel-body">
          <div className="cand-filters">
            <input className="cand-filter-input" placeholder="Rechercher un étudiant…" value={filtres.q}
              onChange={(e) => setFiltres({ ...filtres, q: e.target.value })} />
            <select className="cand-filter-select" aria-label="Filtrer par statut" value={filtres.statut}
              onChange={(e) => setFiltres({ ...filtres, statut: e.target.value })}>
              <option value="">Tous les statuts</option>
              {STATUTS.map(([value, libelle]) => (
                <option key={value} value={value}>{libelle}</option>
              ))}
            </select>
            <button className="btn btn-outline-secondary btn-sm cand-btn-pill" onClick={charger}>
              <i className="bi bi-search me-1"></i>Rechercher
            </button>
          </div>
        </div>

        {loading ? (
          <div className="text-center py-4"><div className="spinner-border"></div></div>
        ) : (
          <div className="table-responsive">
            <table className="table table-hover align-middle mb-0 cand-table">
              <thead className="table-light">
                <tr><th>Matricule</th><th>Étudiant</th><th>Formation</th><th>Niveau</th><th>Type</th><th>Année</th><th>Statut</th><th className="text-end">Actions</th></tr>
              </thead>
              <tbody>
                {inscriptions.map((i) => (
                  <tr key={i.id}>
                    <td><code className="cand-candidatures">{i.matricule}</code></td>
                    <td><span className="cand-link">{i.etudiant}</span></td>
                    <td>{i.ref_formation}</td><td>{i.niveau}</td>
                    <td><small className="text-muted">{i.type_inscription_libelle}</small></td>
                    <td>{i.annee_academique}</td>
                    <td><StatutBadge statut={i.statut} libelle={i.statut_libelle} /></td>
                    <td className="text-end">
                      <div className="btn-group btn-group-sm">
                        {CHEMIN_VALIDATION[i.statut] && (
                          <button className="btn btn-outline-success cand-btn-pill" disabled={enCours === i.id} onClick={() => valider(i)}>
                            {enCours === i.id && <span className="spinner-border spinner-border-sm me-1"></span>}
                            <i className="bi bi-check2-circle me-1"></i>Valider
                          </button>
                        )}
                        <Link className="btn btn-outline-primary cand-btn-pill" to={`/scolarite/etudiants/${i.etudiant_id}`}>
                          <i className="bi bi-person-lines-fill me-1"></i>Fiche
                        </Link>
                        <button className="btn btn-outline-warning cand-btn-pill" disabled={enCours === i.id}
                          onClick={() => { setDossier(i.id); setModification(null); }}>
                          <i className="bi bi-pencil-square me-1"></i>Modifier
                        </button>
                        <button className="btn btn-outline-danger cand-btn-pill" disabled={enCours === i.id} onClick={() => supprimer(i.id)}>
                          <i className="bi bi-trash3 me-1"></i>Supprimer
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
                {inscriptions.length === 0 && (
                  <tr><td colSpan={7}><div className="camp-empty"><i className="bi bi-inbox"></i>Aucune inscription pour ces critères.</div></td></tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {dossier && <DossierInscription id={dossier} onClose={() => setDossier(null)} onRefresh={charger}
        onModifier={(id) => { setDossier(null); setModification(id); }} />}
      {creation && <NouvelleInscription onClose={() => setCreation(false)} onSuccess={charger} />}
      {modification !== null && <ModifierInscription id={modification} onClose={() => setModification(null)} onSuccess={charger} />}
    </div>
  )
}

function DossierInscription({ id, onClose, onRefresh, onModifier }) {
  const { showToast } = useToast()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [enCours, setEnCours] = useState(null)

  const charger = useCallback(async () => {
    setLoading(true)
    try {
      const res = await getInscription(id)
      setData(res.data)
    } catch (err) {
      showToast(messageErreur(err, 'Chargement du dossier impossible'), 'error')
    } finally { setLoading(false) }
  }, [id, showToast])

  useEffect(() => { charger() }, [charger])

  const valider = async () => {
    setEnCours(id)
    try {
      await transitionInscription(id, { statut: 'VALIDEE' })
      showToast('Inscription validée')
      onRefresh()
      charger()
    } catch (err) { showToast(messageErreur(err, 'Validation impossible'), 'error') }
    finally { setEnCours(null) }
  }

  const supprimer = async () => {
    if (!window.confirm('Supprimer cette inscription administrative ? Irréversible.')) return
    setEnCours(id)
    try {
      await deleteInscription(id)
      showToast('Inscription supprimée')
      onRefresh()
      onClose()
    } catch (err) { showToast(messageErreur(err, 'Suppression impossible'), 'error') }
    finally { setEnCours(null) }
  }

  if (loading) return <div className="cand-panel cand-form"><div className="text-center py-4"><div className="spinner-border"></div></div></div>
  if (!data) return null

  return (
    <FenetreModale
      idTitre="titre-dossier-inscription"
      titre="Dossier d’inscription"
      sousTitre="Synthèse administrative et cycle de vie du dossier."
      icone="bi bi-file-earmark-person"
      onClose={onClose}
      pied={(
        <>
          {CHEMIN_VALIDATION[data.statut] && (
            <button
              type="button"
              className="mp-bouton mp-bouton--succes"
              disabled={enCours === id}
              onClick={valider}
            >
              {enCours === id && <span className="spinner-border" aria-hidden="true"></span>}
              <i className="bi bi-check2-circle" aria-hidden="true"></i>
              Valider
            </button>
          )}
          <button
            type="button"
            className="mp-bouton mp-bouton--fantome"
            onClick={() => { onClose(); onModifier(id) }}
          >
            <i className="bi bi-pencil-square" aria-hidden="true"></i>
            Modifier
          </button>
          <button
            type="button"
            className="mp-bouton mp-bouton--danger"
            onClick={supprimer}
          >
            <i className="bi bi-trash3" aria-hidden="true"></i>
            Supprimer
          </button>
          <button type="button" className="mp-bouton mp-bouton--fantome" onClick={onClose}>
            Fermer
          </button>
        </>
      )}
    >
      <div className="mp-corps">
        <div className="mp-identite">
          <span className="mp-identite-avatar" aria-hidden="true">{String(data.etudiant || '?').trim().split(/\s+/).slice(0, 2).map((m) => m[0]).join('').toUpperCase()}</span>
          <div>
            <div className="mp-identite-nom">{data.etudiant}</div>
            <div className="mp-identite-detail">Matricule {data.matricule}</div>
          </div>
          <div style={{ marginLeft: 'auto' }}>
            <StatutBadge statut={data.statut} libelle={data.statut_libelle} />
          </div>
        </div>

        <div className="mp-fiche">
          <div className="mp-fiche-item">
            <span className="mp-fiche-cle">Formation</span>
            <span className="mp-fiche-valeur">{data.ref_formation || '—'}</span>
          </div>
          <div className="mp-fiche-item">
            <span className="mp-fiche-cle">Niveau</span>
            <span className="mp-fiche-valeur">{data.niveau || '—'}</span>
          </div>
          <div className="mp-fiche-item">
            <span className="mp-fiche-cle">Année académique</span>
            <span className="mp-fiche-valeur">{data.annee_academique || '—'}</span>
          </div>
          <div className="mp-fiche-item">
            <span className="mp-fiche-cle">Type d’inscription</span>
            <span className="mp-fiche-valeur">{data.type_inscription_libelle || '—'}</span>
          </div>
          <div className="mp-fiche-item">
            <span className="mp-fiche-cle">Date d’inscription</span>
            <span className="mp-fiche-valeur">{data.date_inscription || '—'}</span>
          </div>
          <div className="mp-fiche-item">
            <span className="mp-fiche-cle">Parcours</span>
            <span className="mp-fiche-valeur">{data.parcours || '—'}</span>
          </div>
          {data.admission_id && (
            <div className="mp-fiche-item mp-fiche-item--pleine">
              <span className="mp-fiche-cle">Admission d’origine</span>
              <span className="mp-fiche-valeur">{data.admission_id}</span>
            </div>
          )}
          {data.observations && (
            <div className="mp-fiche-item mp-fiche-item--pleine">
              <span className="mp-fiche-cle">Observations</span>
              <span className="mp-fiche-valeur">{data.observations}</span>
            </div>
          )}
        </div>
      </div>
    </FenetreModale>
  )
}

/**
 * Fenêtre modale réutilisable (voile flouté, carte premium, en-tête à icône,
 * pied d'actions aligné à droite).
 *
 * Comportements attendus d'une fenêtre : fermeture par la touche Échap et par
 * un clic sur le voile, rôle `dialog` annoncé aux lecteurs d'écran, titre
 * associé par `aria-labelledby`. Le corps (`children`) accueille le formulaire,
 * qui doit porter son propre `onSubmit`.
 */
function FenetreModale({ idTitre, titre, sousTitre, icone, onClose, children, pied }) {
  useEffect(() => {
    const surTouche = (e) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', surTouche)
    return () => document.removeEventListener('keydown', surTouche)
  }, [onClose])

  return (
    <div
      className="mp-overlay"
      onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }}
    >
      <div className="mp-modal" role="dialog" aria-modal="true" aria-labelledby={idTitre}>
        <header className="mp-entete">
          <span className="mp-entete-icone" aria-hidden="true"><i className={icone}></i></span>
          <div className="mp-entete-textes">
            <h3 className="mp-titre" id={idTitre}>{titre}</h3>
            {sousTitre && <p className="mp-sous-titre">{sousTitre}</p>}
          </div>
          <button type="button" className="mp-fermer" onClick={onClose} aria-label="Fermer la fenêtre">
            <i className="bi bi-x-lg" aria-hidden="true"></i>
          </button>
        </header>
        {children}
        <footer className="mp-pied">{pied}</footer>
      </div>
    </div>
  )
}

function NouvelleInscription({ onClose, onSuccess }) {
  const { showToast } = useToast()
  const [enCours, setEnCours] = useState(false)
  const [form, setForm] = useState({
    etudiant_id: '', annee_academique_id: '', ref_formation_id: '',
    niveau_id: '', parcours_id: '', type_inscription: 'PREMIERE',
    date_inscription: '', observations: '',
  })
  const [etudiants, setEtudiants] = useState([])
  const [annee, setAnnee] = useState(null)
  const [formations, setFormations] = useState([])
  const [niveaux, setNiveaux] = useState([])
  const [parcours, setParcours] = useState([])

  useEffect(() => {
    (async () => {
      const [eRes, aRes, fRes, nRes, pRes] = await Promise.all([
        listEtudiants().catch(() => ({ data: [] })),
        getAnneeCourante().catch(() => null),
        getRefFormations().catch(() => ({ data: [] })),
        getRefScolarite('niveaux', { actif: 1 }).catch(() => ({ data: [] })),
        getRefScolarite('parcours', { actif: 1 }).catch(() => ({ data: [] })),
      ])
      setEtudiants(eRes.data || [])
      setAnnee(aRes?.annee ?? null)
      setFormations(fRes.data || [])
      setNiveaux(nRes.data || [])
      setParcours(pRes.data || [])
    })()
  }, [])

  const changer = (champ, valeur) => setForm({ ...form, [champ]: valeur })

  const valide = form.etudiant_id && form.ref_formation_id && form.niveau_id && form.date_inscription

  const soumettre = async (e) => {
    e.preventDefault()
    setEnCours(true)
    try {
      await createInscription({ ...form, annee_academique_id: form.annee_academique_id || annee?.id })
      showToast('Inscription créée')
      onSuccess()
      onClose()
    } catch (err) { showToast(messageErreur(err, 'Création impossible'), 'error') }
    finally { setEnCours(false) }
  }


  return (
    <FenetreModale
      idTitre="titre-nouvelle-inscription"
      titre="Nouvelle inscription administrative"
      sousTitre="Les champs marqués d’un astérisque sont obligatoires."
      icone="bi bi-person-plus"
      onClose={onClose}
      pied={(
        <>
          <button type="button" className="mp-bouton mp-bouton--fantome" onClick={onClose}>
            Annuler
          </button>
          <button
            type="submit"
            form="form-nouvelle-inscription"
            className="mp-bouton mp-bouton--principal"
            disabled={enCours || !valide}
          >
            {enCours && <span className="spinner-border" aria-hidden="true"></span>}
            <i className="bi bi-check2" aria-hidden="true"></i>
            Créer l’inscription
          </button>
        </>
      )}
    >
      <form id="form-nouvelle-inscription" className="mp-corps" onSubmit={soumettre}>
        <div className="mp-grille">
          <div className="mp-champ mp-champ--pleine">
            <label className="mp-etiquette" htmlFor="ins-etudiant">
              Étudiant <span className="mp-requis" aria-hidden="true">*</span>
            </label>
            <select
              id="ins-etudiant"
              className="mp-controle"
              value={form.etudiant_id}
              onChange={(e) => changer('etudiant_id', e.target.value)}
              required
              aria-required="true"
            >
              <option value="">Sélectionner un étudiant…</option>
              {etudiants.map((et) => (<option key={et.id} value={et.id}>{et.matricule} – {et.nom_complet}</option>))}
            </select>
          </div>

          <div className="mp-champ">
            <label className="mp-etiquette" htmlFor="ins-formation">
              Formation <span className="mp-requis" aria-hidden="true">*</span>
            </label>
            <select
              id="ins-formation"
              className="mp-controle"
              value={form.ref_formation_id}
              onChange={(e) => changer('ref_formation_id', e.target.value)}
              required
              aria-required="true"
            >
              <option value="">Sélectionner une formation…</option>
              {formations.map((f) => (<option key={f.id} value={f.id}>{f.intitule}</option>))}
            </select>
          </div>

          <div className="mp-champ">
            <label className="mp-etiquette" htmlFor="ins-niveau">
              Niveau <span className="mp-requis" aria-hidden="true">*</span>
            </label>
            <select
              id="ins-niveau"
              className="mp-controle"
              value={form.niveau_id}
              onChange={(e) => changer('niveau_id', e.target.value)}
              required
              aria-required="true"
            >
              <option value="">Sélectionner un niveau…</option>
              {niveaux.map((n) => (<option key={n.id} value={n.id}>{n.code}</option>))}
            </select>
          </div>

          <div className="mp-champ">
            <label className="mp-etiquette" htmlFor="ins-annee">Année académique</label>
            <select
              id="ins-annee"
              className="mp-controle"
              value={form.annee_academique_id}
              onChange={(e) => changer('annee_academique_id', e.target.value)}
            >
              <option value="">Année courante{annee?.libelle ? ` — ${annee.libelle}` : ''}</option>
              {annee?.id && <option value={annee.id}>{annee.libelle}</option>}
            </select>
            <span className="mp-aide">Laisser sur « année courante » pour utiliser l’année active.</span>
          </div>

          <div className="mp-champ">
            <label className="mp-etiquette" htmlFor="ins-type">Type d’inscription</label>
            <select
              id="ins-type"
              className="mp-controle"
              value={form.type_inscription}
              onChange={(e) => changer('type_inscription', e.target.value)}
            >
              {TYPES_INSCRIPTION.map(([valeur, libelle]) => (
                <option key={valeur} value={valeur}>{libelle}</option>
              ))}
            </select>
          </div>

          <div className="mp-champ">
            <label className="mp-etiquette" htmlFor="ins-parcours">Parcours</label>
            <select
              id="ins-parcours"
              className="mp-controle"
              value={form.parcours_id}
              onChange={(e) => changer('parcours_id', e.target.value)}
            >
              <option value="">Aucun parcours</option>
              {parcours.map((p) => (<option key={p.id} value={p.id}>{p.intitule}</option>))}
            </select>
          </div>

          <div className="mp-champ">
            <label className="mp-etiquette" htmlFor="ins-date">
              Date d’inscription <span className="mp-requis" aria-hidden="true">*</span>
            </label>
            <input
              id="ins-date"
              className="mp-controle"
              type="date"
              value={form.date_inscription}
              onChange={(e) => changer('date_inscription', e.target.value)}
              required
              aria-required="true"
            />
          </div>

          <div className="mp-champ mp-champ--pleine">
            <label className="mp-etiquette" htmlFor="ins-observations">Observations</label>
            <textarea
              id="ins-observations"
              className="mp-controle"
              value={form.observations}
              onChange={(e) => changer('observations', e.target.value)}
              rows="3"
              placeholder="Précisions administratives éventuelles…"
            ></textarea>
          </div>
        </div>
      </form>
    </FenetreModale>
  )
}

function ModifierInscription({ id, onClose, onSuccess }) {
  const { showToast } = useToast()
  const [enCours, setEnCours] = useState(false)
  const [data, setData] = useState(null)
  const [form, setForm] = useState({
    ref_formation_id: '', niveau_id: '', parcours_id: '',
    type_inscription: 'PREMIERE', observations: '',
  })
  const [formations, setFormations] = useState([])
  const [niveaux, setNiveaux] = useState([])
  const [parcours, setParcours] = useState([])

  const charger = useCallback(async () => {
    const res = await getInscription(id)
    const d = res.data
    setData(d)
    setForm({
      ref_formation_id: d.ref_formation_id,
      niveau_id: d.niveau_id,
      parcours_id: d.parcours_id || '',
      type_inscription: d.type_inscription,
      observations: d.observations || '',
    })
  }, [id])

  useEffect(() => {
    (async () => {
      await charger()
      const [fRes, nRes, pRes] = await Promise.all([
        getRefFormations().catch(() => ({ data: [] })),
        getRefScolarite('niveaux', { actif: 1 }).catch(() => ({ data: [] })),
        getRefScolarite('parcours', { actif: 1 }).catch(() => ({ data: [] })),
      ])
      setFormations(fRes.data || [])
      setNiveaux(nRes.data || [])
      setParcours(pRes.data || [])
    })()
  }, [charger])

  const changer = (champ, valeur) => setForm({ ...form, [champ]: valeur })

  const soumettre = async (e) => {
    e.preventDefault()
    setEnCours(true)
    try {
      await updateInscription(id, form)
      showToast('Inscription modifiée')
      onSuccess()
      onClose()
    } catch (err) { showToast(messageErreur(err, 'Modification impossible'), 'error') }
    finally { setEnCours(false) }
  }

  if (!data) return <div className="cand-panel cand-form"><div className="text-center py-4"><div className="spinner-border"></div></div></div>

  return (
    <FenetreModale
      idTitre="titre-modifier-inscription"
      titre="Modifier l’inscription"
      sousTitre="Le rattachement pédagogique peut être ajusté sans perdre le dossier ni son historique."
      icone="bi bi-pencil-square"
      onClose={onClose}
      pied={(
        <>
          <button type="button" className="mp-bouton mp-bouton--fantome" onClick={onClose}>
            Annuler
          </button>
          <button
            type="submit"
            form="form-modifier-inscription"
            className="mp-bouton mp-bouton--principal"
            disabled={enCours}
          >
            {enCours && <span className="spinner-border" aria-hidden="true"></span>}
            <i className="bi bi-check2-circle" aria-hidden="true"></i>
            Enregistrer
          </button>
        </>
      )}
    >
      <form id="form-modifier-inscription" className="mp-corps" onSubmit={soumettre}>
        <div className="mp-identite">
          <span className="mp-identite-avatar" aria-hidden="true">{String(data.etudiant || '?').trim().split(/\s+/).slice(0, 2).map((m) => m[0]).join('').toUpperCase()}</span>
          <div>
            <div className="mp-identite-nom">{data.etudiant}</div>
            <div className="mp-identite-detail">Matricule {data.matricule}</div>
          </div>
        </div>

        <div className="mp-grille">
          <div className="mp-champ">
            <label className="mp-etiquette" htmlFor="mod-formation">Formation</label>
            <select
              id="mod-formation"
              className="mp-controle"
              value={form.ref_formation_id}
              onChange={(e) => changer('ref_formation_id', e.target.value)}
            >
              <option value="">Aucune formation</option>
              {formations.map((f) => (<option key={f.id} value={f.id}>{f.intitule}</option>))}
            </select>
          </div>

          <div className="mp-champ">
            <label className="mp-etiquette" htmlFor="mod-niveau">Niveau</label>
            <select
              id="mod-niveau"
              className="mp-controle"
              value={form.niveau_id}
              onChange={(e) => changer('niveau_id', e.target.value)}
            >
              <option value="">Aucun niveau</option>
              {niveaux.map((n) => (<option key={n.id} value={n.id}>{n.code}</option>))}
            </select>
          </div>

          <div className="mp-champ">
            <label className="mp-etiquette" htmlFor="mod-parcours">Parcours</label>
            <select
              id="mod-parcours"
              className="mp-controle"
              value={form.parcours_id}
              onChange={(e) => changer('parcours_id', e.target.value)}
            >
              <option value="">Aucun parcours</option>
              {parcours.map((p) => (<option key={p.id} value={p.id}>{p.intitule}</option>))}
            </select>
          </div>

          <div className="mp-champ">
            <label className="mp-etiquette" htmlFor="mod-type">Type d’inscription</label>
            <select
              id="mod-type"
              className="mp-controle"
              value={form.type_inscription}
              onChange={(e) => changer('type_inscription', e.target.value)}
            >
              {TYPES_INSCRIPTION.map(([valeur, libelle]) => (
                <option key={valeur} value={valeur}>{libelle}</option>
              ))}
            </select>
          </div>

          <div className="mp-champ mp-champ--pleine">
            <label className="mp-etiquette" htmlFor="mod-observations">Observations</label>
            <textarea
              id="mod-observations"
              className="mp-controle"
              value={form.observations}
              onChange={(e) => changer('observations', e.target.value)}
              rows="3"
              placeholder="Précisions administratives éventuelles…"
            ></textarea>
          </div>
        </div>
      </form>
    </FenetreModale>
  )
}
