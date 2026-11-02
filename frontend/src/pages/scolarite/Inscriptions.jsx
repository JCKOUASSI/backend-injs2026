import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useToast } from '../../context/ToastContext'
import StatutBadge from '../../components/scolarite/StatutBadge'
import ChampDate, { dateFrancaiseVersIso, isoVersDateFrancaise } from '../../components/scolarite/ChampDate'
import '../../styles/candidatures.css'
import '../../styles/admissions.css'
import '../../styles/inscriptions.css'
import '../../styles/modale-premium.css'
import {
  createInscription, deleteInscription, getAnneeCourante, getInscription,
  getRefCategories, getRefFormations, getRefGrades, getRefScolarite,
  getRefVagues, getStatsInscriptions, listEtudiants, listInscriptions,
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
const LIBELLES_STATUT = Object.fromEntries(STATUTS)

/** Réponses API tantôt liste, tantôt objet paginé : toujours une liste. */
const enListe = (res) => {
  const data = res?.data
  if (Array.isArray(data)) return data
  if (Array.isArray(data?.resultats)) return data.resultats
  if (Array.isArray(data?.results)) return data.results
  return []
}

/** Initiales (2 lettres) pour l'avatar d'un étudiant. */
const initiales = (nom) => String(nom || '?').trim().split(/\s+/)
  .slice(0, 2).map((m) => m[0]).join('').toUpperCase()

/** Date ISO → JJ/MM/AAAA ('—' si absente). */
const dateFR = (valeur) => isoVersDateFrancaise(valeur) || '—'

export default function Inscriptions() {
  const { showToast } = useToast()
  const [inscriptions, setInscriptions] = useState([])
  const [loading, setLoading] = useState(true)
  const [enCours, setEnCours] = useState(null)
  const [creation, setCreation] = useState(false)
  const [modification, setModification] = useState(null)
  const [dossier, setDossier] = useState(null)
  const [filtres, setFiltres] = useState({
    statut: '', q: '', annee_academique_id: '', ref_formation_id: '',
    niveau_id: '', type_inscription: '',
  })
  const [annees, setAnnees] = useState([])
  const [formations, setFormations] = useState([])
  const [niveaux, setNiveaux] = useState([])
  const [stats, setStats] = useState(null)

  const charger = useCallback(async () => {
    setLoading(true)
    try {
      const params = Object.fromEntries(Object.entries(filtres).filter(([, v]) => v !== ''))
      const res = await listInscriptions(params)
      setInscriptions(enListe(res))
    } catch (err) {
      showToast(messageErreur(err, 'Chargement des inscriptions impossible'), 'error')
    } finally { setLoading(false) }
  }, [filtres, showToast])

  useEffect(() => { charger() }, [charger])

  // Référentiels des filtres + année courante par défaut (une seule fois).
  useEffect(() => {
    (async () => {
      const [anneeCourante, anneesRes, formationsRes, niveauxRes] = await Promise.all([
        getAnneeCourante().catch(() => null),
        getRefScolarite('annees', { actif: true }).catch(() => ({ data: [] })),
        getRefFormations().catch(() => ({ data: [] })),
        getRefScolarite('niveaux', { actif: 1 }).catch(() => ({ data: [] })),
      ])
      setAnnees(enListe(anneesRes))
      setFormations(enListe(formationsRes))
      setNiveaux(enListe(niveauxRes))
      const courante = anneeCourante?.data?.annee ?? anneeCourante?.annee
      if (courante?.id) {
        setFiltres((f) => (f.annee_academique_id
          ? f
          : { ...f, annee_academique_id: String(courante.id) }))
      }
    })()
  }, [])

  // Statistiques de l'année sélectionnée (KPI stables pendant la recherche).
  useEffect(() => {
    (async () => {
      try {
        const params = filtres.annee_academique_id
          ? { annee_academique_id: filtres.annee_academique_id }
          : {}
        const res = await getStatsInscriptions(params)
        setStats(res.data || null)
      } catch { setStats(null) }
    })()
  }, [filtres.annee_academique_id, inscriptions.length])

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

  const kpis = useMemo(() => {
    const compter = (statut) => (stats?.par_statut
      ? (stats.par_statut[statut] || 0)
      : inscriptions.filter((i) => i.statut === statut).length)
    const total = stats?.total ?? inscriptions.length
    const validees = stats?.inscrits ?? compter('VALIDEE')
    return {
      total,
      validees,
      attente: compter('BROUILLON') + compter('EN_ATTENTE') + compter('A_VALIDER'),
      rejetees: compter('REJETEE'),
      annulees: compter('ANNULEE'),
      taux: total ? Math.round((validees / total) * 100) : 0,
    }
  }, [inscriptions, stats])

  const libelleAnnee = annees.find(
    (a) => String(a.id) === String(filtres.annee_academique_id),
  )?.libelle
  const reinitialiser = () => setFiltres((f) => ({
    statut: '', q: '', annee_academique_id: f.annee_academique_id,
    ref_formation_id: '', niveau_id: '', type_inscription: '',
  }))


  return (
    <div className="cand-page">
      <div className="cand-hero">
        <div className="cand-hero-identite">
          <span className="cand-hero-icone" aria-hidden="true">
            <i className="bi bi-person-badge"></i>
          </span>
          <div className="cand-hero-text">
            <span className="insc-badge">Scolarité — Inscriptions</span>
            <h1 className="cand-hero-title">Inscriptions administratives</h1>
            <p className="cand-hero-sub">
              Suivez le cycle de vie de chaque dossier — brouillon, instruction,
              validation — jusqu’à l’ouverture du parcours pédagogique
              {libelleAnnee ? <> pour l’année <strong>{libelleAnnee}</strong></> : ''}.
            </p>
            <div className="insc-etapes" aria-label="Parcours de l’étudiant">
              <span className="insc-etape">
                <i className="bi bi-award" aria-hidden="true"></i> Admission
              </span>
              <i className="bi bi-arrow-right insc-etape-fleche" aria-hidden="true"></i>
              <span className="insc-etape insc-etape--actuelle" aria-current="step">
                <i className="bi bi-person-badge" aria-hidden="true"></i> Inscription
              </span>
              <i className="bi bi-arrow-right insc-etape-fleche" aria-hidden="true"></i>
              <span className="insc-etape">
                <i className="bi bi-journal-check" aria-hidden="true"></i> Parcours pédagogique
              </span>
            </div>
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
            <span className="adm-kpi-sous">{libelleAnnee ? `année ${libelleAnnee}` : 'toutes années'}</span>
          </div>
        </div>
        <div className="cand-kpi">
          <span className="cand-kpi-icon is-green" aria-hidden="true"><i className="bi bi-check2-circle"></i></span>
          <div>
            <span className="cand-kpi-value">{kpis.validees}</span>
            <span className="cand-kpi-label">Validées</span>
            <span className="adm-kpi-sous">{kpis.taux} % des dossiers</span>
          </div>
        </div>
        <div className="cand-kpi">
          <span className="cand-kpi-icon is-amber" aria-hidden="true"><i className="bi bi-hourglass-split"></i></span>
          <div>
            <span className="cand-kpi-value">{kpis.attente}</span>
            <span className="cand-kpi-label">En attente</span>
            <span className="adm-kpi-sous">brouillon, en attente, à valider</span>
          </div>
        </div>
        <div className="cand-kpi">
          <span className="cand-kpi-icon is-red" aria-hidden="true"><i className="bi bi-x-circle"></i></span>
          <div>
            <span className="cand-kpi-value">{kpis.rejetees}</span>
            <span className="cand-kpi-label">Rejetées</span>
            <span className="adm-kpi-sous">+ {kpis.annulees} annulée{kpis.annulees > 1 ? 's' : ''}</span>
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
          <div className="cand-filters insc-filtres">
            <div className="adm-recherche">
              <i className="bi bi-search" aria-hidden="true"></i>
              <input
                type="search"
                aria-label="Rechercher un étudiant"
                placeholder="Rechercher un étudiant, un matricule…"
                value={filtres.q}
                onChange={(e) => setFiltres({ ...filtres, q: e.target.value })}
              />
            </div>
            <select
              className="cand-filter-select"
              aria-label="Filtrer par année académique"
              value={filtres.annee_academique_id}
              onChange={(e) => setFiltres({ ...filtres, annee_academique_id: e.target.value })}
            >
              <option value="">Toutes les années</option>
              {annees.map((a) => (
                <option key={a.id} value={a.id}>{a.libelle}</option>
              ))}
            </select>
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
            <select
              className="cand-filter-select"
              aria-label="Filtrer par formation"
              value={filtres.ref_formation_id}
              onChange={(e) => setFiltres({ ...filtres, ref_formation_id: e.target.value })}
            >
              <option value="">Toutes les formations</option>
              {formations.map((f) => (
                <option key={f.id} value={f.id}>{f.intitule}</option>
              ))}
            </select>
            <select
              className="cand-filter-select"
              aria-label="Filtrer par niveau"
              value={filtres.niveau_id}
              onChange={(e) => setFiltres({ ...filtres, niveau_id: e.target.value })}
            >
              <option value="">Tous les niveaux</option>
              {niveaux.map((n) => (
                <option key={n.id} value={n.id}>{n.code}</option>
              ))}
            </select>
            <select
              className="cand-filter-select"
              aria-label="Filtrer par type d’inscription"
              value={filtres.type_inscription}
              onChange={(e) => setFiltres({ ...filtres, type_inscription: e.target.value })}
            >
              <option value="">Tous les types</option>
              {TYPES_INSCRIPTION.map(([valeur, libelle]) => (
                <option key={valeur} value={valeur}>{libelle}</option>
              ))}
            </select>
            <button className="cand-btn-recherche" onClick={charger}>
              <i className="bi bi-search" aria-hidden="true"></i>
              Rechercher
            </button>
            <button className="insc-btn-reinitialiser" onClick={reinitialiser}>
              <i className="bi bi-arrow-counterclockwise" aria-hidden="true"></i>
              Réinitialiser
            </button>
          </div>
        </div>

        {loading ? (
          <div className="cand-chargement"><span className="spinner-border" aria-hidden="true"></span>Chargement des dossiers…</div>
        ) : (
          <div className="cand-table-wrap">
            <table className="cand-table cand-table--inscriptions insc-table">
              <thead>
                <tr>
                  <th scope="col">Étudiant</th>
                  <th scope="col">Formation</th>
                  <th scope="col">Type</th>
                  <th scope="col">Date</th>
                  <th scope="col">Statut</th>
                  <th scope="col" className="cand-col-actions">Actions</th>
                </tr>
              </thead>
              <tbody>
                {inscriptions.map((i) => (
                  <tr key={i.id}>
                    <td>
                      <div className="adm-candidat">
                        <span className="adm-avatar" aria-hidden="true">{initiales(i.etudiant)}</span>
                        <span className="adm-candidat-noms">
                          <span className="insc-etudiant-nom">{i.etudiant}</span>
                          <code className="insc-matricule">{i.matricule}</code>
                        </span>
                      </div>
                    </td>
                    <td className="cand-col-formation">
                      <span className="cand-texte-formation" title={i.ref_formation}>
                        {i.ref_formation}
                      </span>
                      <span className="adm-meta">
                        <span className="cand-badge-neutre">{i.niveau}</span>
                        {i.parcours ? ` · ${i.parcours}` : ''}
                        {` · ${i.annee_academique}`}
                      </span>
                    </td>
                    <td>
                      <span className="insc-type">{i.type_inscription_libelle}</span>
                      {(i.vague || i.grade) && (
                        <span className="adm-meta">
                          {[i.vague, i.grade].filter(Boolean).join(' · ')}
                        </span>
                      )}
                    </td>
                    <td className="insc-date">
                      {dateFR(i.date_inscription)}
                      {i.date_validation && (
                        <span className="adm-meta">validée le {dateFR(i.date_validation)}</span>
                      )}
                    </td>
                    <td><StatutBadge statut={i.statut} libelle={i.statut_libelle} /></td>
                    <td className="cand-col-actions">
                      <div className="adm-actions">
                        {CHEMIN_VALIDATION[i.statut] && (
                          <button
                            className="insc-action insc-action--succes"
                            disabled={enCours === i.id}
                            onClick={() => valider(i)}
                            aria-label="Valider"
                            title="Valider l’inscription (enchaîne les transitions)"
                          >
                            {enCours === i.id
                              ? <span className="spinner-border" aria-hidden="true"></span>
                              : <i className="bi bi-check2-circle" aria-hidden="true"></i>}
                            Valider
                          </button>
                        )}
                        <button
                          className="insc-action"
                          disabled={enCours === i.id}
                          onClick={() => { setDossier(i.id); setModification(null) }}
                          aria-label="Dossier"
                          title="Ouvrir le dossier d’inscription"
                        >
                          <i className="bi bi-folder2-open" aria-hidden="true"></i>
                          Dossier
                        </button>
                        <Link
                          className="cand-action"
                          to={`/scolarite/etudiants/${i.etudiant_id}`}
                          aria-label="Fiche étudiant"
                          title="Ouvrir la fiche de l’étudiant"
                        >
                          <i className="bi bi-person-lines-fill" aria-hidden="true"></i>
                        </Link>
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

  const transiter = async (statut) => {
    setEnCours(id)
    try {
      await transitionInscription(id, { statut })
      showToast(`Inscription : ${LIBELLES_STATUT[statut] || statut}`)
      onRefresh()
      charger()
    } catch (err) { showToast(messageErreur(err, 'Transition impossible'), 'error') }
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
          {(data.transitions_possibles || []).map((cible) => (
            <button
              key={cible}
              type="button"
              className={cible === 'VALIDEE' ? 'mp-bouton mp-bouton--succes' : 'mp-bouton mp-bouton--fantome'}
              disabled={enCours === id}
              onClick={() => transiter(cible)}
            >
              {enCours === id && <span className="spinner-border" aria-hidden="true"></span>}
              {cible === 'VALIDEE' && <i className="bi bi-check2-circle" aria-hidden="true"></i>}
              {LIBELLES_STATUT[cible] || cible}
            </button>
          ))}
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
            <span className="mp-fiche-valeur">{dateFR(data.date_inscription)}</span>
          </div>
          <div className="mp-fiche-item">
            <span className="mp-fiche-cle">Parcours</span>
            <span className="mp-fiche-valeur">{data.parcours || '—'}</span>
          </div>
          <div className="mp-fiche-item">
            <span className="mp-fiche-cle">Vague</span>
            <span className="mp-fiche-valeur">{data.vague || '—'}</span>
          </div>
          <div className="mp-fiche-item">
            <span className="mp-fiche-cle">Régime d’études</span>
            <span className="mp-fiche-valeur">{data.regime || '—'}</span>
          </div>
          <div className="mp-fiche-item">
            <span className="mp-fiche-cle">Catégorie</span>
            <span className="mp-fiche-valeur">{data.categorie || '—'}</span>
          </div>
          <div className="mp-fiche-item">
            <span className="mp-fiche-cle">Grade</span>
            <span className="mp-fiche-valeur">{data.grade || '—'}</span>
          </div>
          {data.date_validation && (
            <div className="mp-fiche-item">
              <span className="mp-fiche-cle">Validée le</span>
              <span className="mp-fiche-valeur">
                {dateFR(data.date_validation)}
                {data.valide_par ? ` — par ${data.valide_par}` : ''}
              </span>
            </div>
          )}
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

/** Champs de profil administratif partagés par création et modification. */
function ChampsProfil({ prefixe, form, changer, vagues, categories, grades, regimes }) {
  const gradesFiltres = form.categorie_id
    ? grades.filter((g) => String(g.categorie) === String(form.categorie_id)
      || String(g.categorie_id) === String(form.categorie_id))
    : grades
  return (
    <>
      <div className="mp-champ">
        <label className="mp-etiquette" htmlFor={`${prefixe}-vague`}>Vague</label>
        <select
          id={`${prefixe}-vague`}
          className="mp-controle"
          value={form.vague_id}
          onChange={(e) => changer('vague_id', e.target.value)}
        >
          <option value="">Aucune vague</option>
          {vagues.map((v) => (<option key={v.id} value={v.id}>{v.libelle}</option>))}
        </select>
      </div>
      <div className="mp-champ">
        <label className="mp-etiquette" htmlFor={`${prefixe}-regime`}>Régime d’études</label>
        <select
          id={`${prefixe}-regime`}
          className="mp-controle"
          value={form.regime_id}
          onChange={(e) => changer('regime_id', e.target.value)}
        >
          <option value="">Non renseigné</option>
          {regimes.map((r) => (<option key={r.id} value={r.id}>{r.libelle}</option>))}
        </select>
      </div>
      <div className="mp-champ">
        <label className="mp-etiquette" htmlFor={`${prefixe}-categorie`}>Catégorie</label>
        <select
          id={`${prefixe}-categorie`}
          className="mp-controle"
          value={form.categorie_id}
          onChange={(e) => { changer('categorie_id', e.target.value); changer('grade_id', '') }}
        >
          <option value="">Non renseignée</option>
          {categories.map((c) => (<option key={c.id} value={c.id}>{c.libelle}</option>))}
        </select>
      </div>
      <div className="mp-champ">
        <label className="mp-etiquette" htmlFor={`${prefixe}-grade`}>Grade</label>
        <select
          id={`${prefixe}-grade`}
          className="mp-controle"
          value={form.grade_id}
          onChange={(e) => changer('grade_id', e.target.value)}
        >
          <option value="">Non renseigné</option>
          {gradesFiltres.map((g) => (<option key={g.id} value={g.id}>{g.libelle}</option>))}
        </select>
      </div>
    </>
  )
}

function NouvelleInscription({ onClose, onSuccess }) {
  const { showToast } = useToast()
  const [enCours, setEnCours] = useState(false)
  const [form, setForm] = useState({
    etudiant_id: '', annee_academique_id: '', ref_formation_id: '',
    niveau_id: '', parcours_id: '', type_inscription: 'PREMIERE',
    date_inscription: '', observations: '',
    vague_id: '', categorie_id: '', grade_id: '', regime_id: '',
  })
  const [etudiants, setEtudiants] = useState([])
  const [annee, setAnnee] = useState(null)
  const [formations, setFormations] = useState([])
  const [niveaux, setNiveaux] = useState([])
  const [parcours, setParcours] = useState([])
  const [vagues, setVagues] = useState([])
  const [categories, setCategories] = useState([])
  const [grades, setGrades] = useState([])
  const [regimes, setRegimes] = useState([])

  useEffect(() => {
    (async () => {
      const [eRes, aRes, fRes, nRes, pRes, vRes, cRes, gRes, rRes] = await Promise.all([
        listEtudiants().catch(() => ({ data: [] })),
        getAnneeCourante().catch(() => null),
        getRefFormations().catch(() => ({ data: [] })),
        getRefScolarite('niveaux', { actif: 1 }).catch(() => ({ data: [] })),
        getRefScolarite('parcours', { actif: 1 }).catch(() => ({ data: [] })),
        getRefVagues().catch(() => ({ data: [] })),
        getRefCategories().catch(() => ({ data: [] })),
        getRefGrades().catch(() => ({ data: [] })),
        getRefScolarite('regimes', { actif: 1 }).catch(() => ({ data: [] })),
      ])
      setEtudiants(enListe(eRes))
      setAnnee(aRes?.data?.annee ?? aRes?.annee ?? null)
      setFormations(enListe(fRes))
      setNiveaux(enListe(nRes))
      setParcours(enListe(pRes))
      setVagues(enListe(vRes))
      setCategories(enListe(cRes))
      setGrades(enListe(gRes))
      setRegimes(enListe(rRes))
    })()
  }, [])

  const changer = (champ, valeur) => setForm((f) => ({ ...f, [champ]: valeur }))

  const valide = form.etudiant_id && form.ref_formation_id && form.niveau_id
    && dateFrancaiseVersIso(form.date_inscription)

  const soumettre = async (e) => {
    e.preventDefault()
    setEnCours(true)
    try {
      await createInscription({
        ...form,
        date_inscription: dateFrancaiseVersIso(form.date_inscription),
        annee_academique_id: form.annee_academique_id || annee?.id,
      })
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
            <ChampDate
              id="ins-date"
              valeur={form.date_inscription}
              onChange={(valeur) => changer('date_inscription', valeur)}
            />
          </div>

          <ChampsProfil
            prefixe="ins" form={form} changer={changer}
            vagues={vagues} categories={categories} grades={grades} regimes={regimes}
          />

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
    vague_id: '', categorie_id: '', grade_id: '', regime_id: '',
  })
  const [formations, setFormations] = useState([])
  const [niveaux, setNiveaux] = useState([])
  const [parcours, setParcours] = useState([])
  const [vagues, setVagues] = useState([])
  const [categories, setCategories] = useState([])
  const [grades, setGrades] = useState([])
  const [regimes, setRegimes] = useState([])

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
      vague_id: d.vague_id || '',
      categorie_id: d.categorie_id || '',
      grade_id: d.grade_id || '',
      regime_id: d.regime_id || '',
    })
  }, [id])

  useEffect(() => {
    (async () => {
      await charger()
      const [fRes, nRes, pRes, vRes, cRes, gRes, rRes] = await Promise.all([
        getRefFormations().catch(() => ({ data: [] })),
        getRefScolarite('niveaux', { actif: 1 }).catch(() => ({ data: [] })),
        getRefScolarite('parcours', { actif: 1 }).catch(() => ({ data: [] })),
        getRefVagues().catch(() => ({ data: [] })),
        getRefCategories().catch(() => ({ data: [] })),
        getRefGrades().catch(() => ({ data: [] })),
        getRefScolarite('regimes', { actif: 1 }).catch(() => ({ data: [] })),
      ])
      setFormations(enListe(fRes))
      setNiveaux(enListe(nRes))
      setParcours(enListe(pRes))
      setVagues(enListe(vRes))
      setCategories(enListe(cRes))
      setGrades(enListe(gRes))
      setRegimes(enListe(rRes))
    })()
  }, [charger])

  const changer = (champ, valeur) => setForm((f) => ({ ...f, [champ]: valeur }))

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

          <ChampsProfil
            prefixe="mod" form={form} changer={changer}
            vagues={vagues} categories={categories} grades={grades} regimes={regimes}
          />

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
