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
      <div className="cand-hero">
        <div className="cand-hero-identite">
          <span className="cand-hero-icone" aria-hidden="true">
            <i className="bi bi-person-badge"></i>
          </span>
          <div className="cand-hero-text">
            <h1 className="cand-hero-title">Inscriptions administratives</h1>
            <p className="cand-hero-sub">
              Créer, modifier, supprimer et suivre les inscriptions administratives des étudiants.
            </p>
          </div>
        </div>
        <div className="cand-hero-actions">
          <Link className="cand-btn-fantome" to="/scolarite/admissions">
            <i className="bi bi-person-plus" aria-hidden="true"></i>
            Inscrire un admis
          </Link>
          <button className="cand-btn-principal" onClick={() => setCreation(true)}>
            <i className="bi bi-plus-lg" aria-hidden="true"></i>
            Nouvelle inscription
          </button>
        </div>
      </div>

      <div className="cand-kpi-row">
        <div className="cand-kpi">
          <span className="cand-kpi-icon is-blue" aria-hidden="true"><i className="bi bi-folder2-open"></i></span>
          <div>
            <span className="cand-kpi-value">{kpis.total}</span>
            <span className="cand-kpi-label">Dossiers</span>
          </div>
        </div>
        <div className="cand-kpi">
          <span className="cand-kpi-icon is-green" aria-hidden="true"><i className="bi bi-check2-circle"></i></span>
          <div>
            <span className="cand-kpi-value">{kpis.validees}</span>
            <span className="cand-kpi-label">Validées</span>
          </div>
        </div>
        <div className="cand-kpi">
          <span className="cand-kpi-icon is-amber" aria-hidden="true"><i className="bi bi-hourglass-split"></i></span>
          <div>
            <span className="cand-kpi-value">{kpis.attente}</span>
            <span className="cand-kpi-label">En attente</span>
          </div>
        </div>
        <div className="cand-kpi">
          <span className="cand-kpi-icon is-red" aria-hidden="true"><i className="bi bi-x-circle"></i></span>
          <div>
            <span className="cand-kpi-value">{kpis.rejectees}</span>
            <span className="cand-kpi-label">Rejetées</span>
          </div>
        </div>
      </div>

      <div className="cand-panel">
        <div className="cand-panel-head">
          <h2 className="cand-panel-title">
            <i className="bi bi-journal-text" aria-hidden="true"></i>
            Dossiers d’inscription
          </h2>
          <span className="cand-count-pill">
            {inscriptions.length} dossier{inscriptions.length > 1 ? 's' : ''}
          </span>
        </div>
        <div className="cand-panel-body">
          <div className="cand-filters">
            <div className="cand-search">
              <i className="bi bi-search" aria-hidden="true"></i>
              <input
                className="cand-input"
                type="search"
                aria-label="Rechercher un étudiant"
                placeholder="Rechercher un étudiant…"
                value={filtres.q}
                onChange={(e) => setFiltres({ ...filtres, q: e.target.value })}
              />
            </div>
            <select
              className="cand-filter-select"
              aria-label="Filtrer par statut"
              value={filtres.statut}
              onChange={(e) => setFiltres({ ...filtres, statut: e.target.value })}
            >
              <option value="">Tous les statuts</option>
              {STATUTS.map(([value, libelle]) => (
                <option key={value} value={value}>{libelle}</option>
              ))}
            </select>
            <button className="cand-btn-recherche" onClick={charger}>
              <i className="bi bi-search" aria-hidden="true"></i>
              Rechercher
            </button>
          </div>
        </div>

        {loading ? (
          <div className="cand-chargement"><span className="spinner-border" aria-hidden="true"></span>Chargement des dossiers…</div>
        ) : (
          <div className="cand-table-wrap">
            <table className="cand-table cand-table--inscriptions">
              <thead>
                <tr>
                  <th scope="col">Matricule</th>
                  <th scope="col">Étudiant</th>
                  <th scope="col">Formation</th>
                  <th scope="col">Niveau</th>
                  <th scope="col">Type</th>
                  <th scope="col">Année</th>
                  <th scope="col">Statut</th>
                  <th scope="col" className="cand-col-actions">Actions</th>
                </tr>
              </thead>
              <tbody>
                {inscriptions.map((i) => (
                  <tr key={i.id}>
                    <td className="cand-col-etroit"><code className="cand-numero">{i.matricule}</code></td>
                    <td><span className="cand-etudiant">{i.etudiant}</span></td>
                    <td className="cand-col-formation">
                      <span className="cand-texte-formation" title={i.ref_formation}>
                        {i.ref_formation}
                      </span>
                    </td>
                    <td><span className="cand-badge-neutre">{i.niveau}</span></td>
                    <td><span className="cand-texte-doux">{i.type_inscription_libelle}</span></td>
                    <td className="cand-col-etroit">{i.annee_academique}</td>
                    <td><StatutBadge statut={i.statut} libelle={i.statut_libelle} /></td>
                    <td className="cand-col-actions">
                      <div className="cand-actions">
                        {CHEMIN_VALIDATION[i.statut] && (
                          <button
                            className="cand-action cand-action--succes"
                            disabled={enCours === i.id}
                            onClick={() => valider(i)}
                            aria-label="Valider"
                            title="Valider l’inscription"
                          >
                            {enCours === i.id
                              ? <span className="spinner-border" aria-hidden="true"></span>
                              : <i className="bi bi-check2-circle" aria-hidden="true"></i>}
                          </button>
                        )}
                        <Link
                          className="cand-action"
                          to={`/scolarite/etudiants/${i.etudiant_id}`}
                          aria-label="Fiche étudiant"
                          title="Ouvrir la fiche de l’étudiant"
                        >
                          <i className="bi bi-person-lines-fill" aria-hidden="true"></i>
                        </Link>
                        <button
                          className="cand-action"
                          disabled={enCours === i.id}
                          onClick={() => { setDossier(i.id); setModification(null) }}
                          aria-label="Modifier"
                          title="Ouvrir le dossier d’inscription"
                        >
                          <i className="bi bi-pencil-square" aria-hidden="true"></i>
                        </button>
                        <button
                          className="cand-action cand-action--danger"
                          disabled={enCours === i.id}
                          onClick={() => supprimer(i.id)}
                          aria-label="Supprimer"
                          title="Supprimer l’inscription"
                        >
                          <i className="bi bi-trash3" aria-hidden="true"></i>
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {inscriptions.length === 0 && (
              <div className="cand-vide">
                <span className="cand-vide-icone" aria-hidden="true"><i className="bi bi-inbox"></i></span>
                <p className="cand-vide-titre">Aucune inscription pour ces critères</p>
                <p className="cand-vide-texte">
                  Ajustez la recherche ou le statut, ou créez une nouvelle inscription administrative.
                </p>
                <button className="cand-btn-principal" onClick={() => setCreation(true)}>
                  <i className="bi bi-plus-lg" aria-hidden="true"></i>
                  Nouvelle inscription
                </button>
              </div>
            )}
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
