import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { useToast } from '../../context/ToastContext'
import CompletudeBar from '../../components/scolarite/CompletudeBar'
import StatutBadge from '../../components/scolarite/StatutBadge'
import {
  createAdmission,
  createCandidat,
  createCandidature,
  deposerPiece,
  getAnneeCourante,
  getCandidature,
  getPieces,
  getRefFormations,
  getRefScolarite,
  listCandidatures,
  messageErreur,
  transitionCandidature,
  verifierPiece,
} from '../../services/scolarite'
import '../../styles/candidatures.css'

const STATUTS = [
  ['BROUILLON', 'Brouillon'],
  ['SOUMISE', 'Soumise'],
  ['EN_ATTENTE_DE_VERIFICATION', 'En attente de vérification'],
  ['PIECES_INCOMPLETES', 'Pièces incomplètes'],
  ['PIECES_VALIDEES', 'Pièces validées'],
  ['EN_ETUDE', 'En étude'],
  ['ADMISSIBLE', 'Admissible'],
  ['ADMIS', 'Admis'],
  ['ADMIS_SOUS_RESERVE', 'Admis sous réserve'],
  ['LISTE_ATTENTE', "Liste d'attente"],
  ['REFUSE', 'Refusé'],
  ['ANNULE', 'Annulé'],
]

const LIBELLES_STATUT = Object.fromEntries(STATUTS)

const candidatVide = {
  nom: '', prenom: '', sexe: '', date_naissance: '', lieu_naissance: '',
  nationalite: '', email: '', telephone: '',
}

/** Panneau latéral d'un dossier : pièces justificatives et transitions de statut. */
function DossierPanel({ candidature, onClose, onChange }) {
  const { showToast } = useToast()
  const [detail, setDetail] = useState(candidature)
  const [pieces, setPieces] = useState([])
  const [chargement, setChargement] = useState(true)
  const [action, setAction] = useState(null)

  const recharger = useCallback(async () => {
    setChargement(true)
    try {
      const [detailRes, piecesRes] = await Promise.all([
        getCandidature(candidature.id),
        getPieces(candidature.id),
      ])
      setDetail(detailRes.data)
      setPieces(piecesRes.data.pieces || [])
    } catch (err) {
      showToast(messageErreur(err, 'Chargement du dossier impossible'), 'error')
    } finally {
      setChargement(false)
    }
  }, [candidature.id, showToast])

  useEffect(() => { recharger() }, [recharger])

  const appliquerTransition = async (statut) => {
    setAction(statut)
    try {
      await transitionCandidature(candidature.id, { statut })
      showToast(`Statut mis à jour : ${LIBELLES_STATUT[statut] || statut}`)
      await recharger()
      onChange()
    } catch (err) {
      showToast(messageErreur(err, 'Transition refusée'), 'error')
    } finally {
      setAction(null)
    }
  }

  const televerser = async (piece, fichier) => {
    if (!fichier) return
    const formData = new FormData()
    formData.append('fichier', fichier)
    try {
      await deposerPiece(piece.id, formData)
      showToast(`${piece.type_piece} déposée`)
      await recharger()
      onChange()
    } catch (err) {
      showToast(messageErreur(err, 'Dépôt impossible'), 'error')
    }
  }

  const statuerPiece = async (piece, statut) => {
    try {
      await verifierPiece(piece.id, { statut })
      await recharger()
      onChange()
    } catch (err) {
      showToast(messageErreur(err, 'Vérification impossible'), 'error')
    }
  }

  const ouvrirAdmission = async () => {
    setAction('admission')
    try {
      await createAdmission({ candidature_id: candidature.id })
      showToast('Admission ouverte. Prononcez la décision depuis l’onglet Admissions.')
      await recharger()
      onChange()
    } catch (err) {
      showToast(messageErreur(err, 'Ouverture d’admission impossible'), 'error')
    } finally {
      setAction(null)
    }
  }

  const transitions = detail.transitions_possibles || []
  const peutOuvrirAdmission = ['EN_ETUDE', 'ADMISSIBLE', 'LISTE_ATTENTE'].includes(detail.statut)

  return (
    <div className="card cand-panel cand-dossier mb-3">
      <div className="card-header d-flex justify-content-between align-items-center">
        <div>
          <strong className="cand-info-value">{detail.numero}</strong>
          <span className="ms-2">{detail.candidat}</span>
          <span className="ms-2"><StatutBadge statut={detail.statut} libelle={detail.statut_libelle} /></span>
        </div>
        <button className="btn-close" onClick={onClose} aria-label="Fermer"></button>
      </div>
      <div className="card-body">
        {chargement ? (
          <div className="text-center py-3"><div className="spinner-border spinner-border-sm"></div></div>
        ) : (
          <>
            <div className="row g-3 mb-3">
              <div className="col-md-4">
                <span className="cand-info-label">Formation</span>
                <span className="cand-info-value">{detail.ref_formation}</span>
              </div>
              <div className="col-md-4">
                <span className="cand-info-label">Niveau</span>
                <span className="cand-info-value">{detail.niveau}</span>
              </div>
              <div className="col-md-4">
                <span className="cand-info-label">Année</span>
                <span className="cand-info-value">{detail.annee_academique}</span>
              </div>
            </div>

            <h6 className="cand-section-title">Pièces justificatives</h6>
            <div className="table-responsive mb-3">
              <table className="table table-sm align-middle">
                <thead>
                  <tr>
                    <th>Pièce</th><th>Statut</th><th>Fichier</th><th className="text-end">Vérification</th>
                  </tr>
                </thead>
                <tbody>
                  {pieces.map((piece) => (
                    <tr key={piece.id}>
                      <td>
                        {piece.type_piece}
                        {piece.obligatoire && <span className="text-danger ms-1" title="Obligatoire">*</span>}
                        {piece.est_expiree && <span className="badge bg-danger ms-2">Expirée</span>}
                      </td>
                      <td><StatutBadge statut={piece.statut} libelle={piece.statut_libelle} /></td>
                      <td>
                        <input
                          type="file"
                          className="form-control form-control-sm"
                          style={{ maxWidth: '220px' }}
                          onChange={(e) => televerser(piece, e.target.files?.[0])}
                        />
                      </td>
                      <td className="text-end">
                        <div className="btn-group btn-group-sm">
                          <button
                            className="btn btn-outline-success"
                            disabled={!piece.a_fichier}
                            onClick={() => statuerPiece(piece, 'VALIDEE')}
                          >
                            Valider
                          </button>
                          <button
                            className="btn btn-outline-danger"
                            disabled={!piece.a_fichier}
                            onClick={() => statuerPiece(piece, 'REFUSEE')}
                          >
                            Refuser
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                  {pieces.length === 0 && (
                    <tr><td colSpan={4} className="text-muted">Aucune pièce attendue.</td></tr>
                  )}
                </tbody>
              </table>
            </div>

            <div className="d-flex align-items-center gap-3 mb-3">
              <span className="text-muted small">Complétude du dossier</span>
              <div style={{ maxWidth: '260px', width: '100%' }}>
                <CompletudeBar
                  validees={detail.pieces_validees}
                  total={detail.pieces_obligatoires}
                  taux={detail.taux_completude}
                />
              </div>
            </div>

            <h6 className="cand-section-title">Suite du parcours</h6>
            <div className="d-flex flex-wrap gap-2">
              {transitions.map((statut) => (
                <button
                  key={statut}
                  className={`btn btn-sm btn-outline-${statut === 'ANNULE' ? 'danger' : 'primary'}`}
                  disabled={action !== null}
                  onClick={() => appliquerTransition(statut)}
                >
                  {action === statut && <span className="spinner-border spinner-border-sm me-1"></span>}
                  {LIBELLES_STATUT[statut] || statut}
                </button>
              ))}
              {transitions.length === 0 && (
                <span className="text-muted small">Aucune transition possible depuis ce statut.</span>
              )}
              {peutOuvrirAdmission && (
                <button
                  className="btn btn-sm btn-success"
                  disabled={action !== null}
                  onClick={ouvrirAdmission}
                >
                  <i className="bi bi-arrow-right-circle me-1"></i>Ouvrir une admission
                </button>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  )
}

/** Formulaire de dépôt : crée le candidat puis sa candidature. */
function NouvelleCandidature({ annee, formations, niveaux, onCree, onAnnuler }) {
  const { showToast } = useToast()
  const [candidat, setCandidat] = useState({ ...candidatVide })
  const [dossier, setDossier] = useState({ ref_formation_id: '', niveau_id: '' })
  const [envoi, setEnvoi] = useState(false)
  const [erreur, setErreur] = useState('')

  const soumettre = async (e) => {
    e.preventDefault()
    setErreur('')
    setEnvoi(true)
    try {
      const candidatRes = await createCandidat(candidat)
      await createCandidature({
        candidat_id: candidatRes.data.id,
        annee_academique_id: annee?.id,
        ref_formation_id: dossier.ref_formation_id,
        niveau_id: dossier.niveau_id,
      })
      showToast('Candidature enregistrée')
      onCree()
    } catch (err) {
      setErreur(messageErreur(err, "Enregistrement impossible"))
    } finally {
      setEnvoi(false)
    }
  }

  return (
    <div className="card cand-panel cand-form mb-3">
      <div className="card-header"><strong>Nouvelle candidature</strong></div>
      <form className="card-body" onSubmit={soumettre}>
        {erreur && <div className="alert alert-danger" style={{ whiteSpace: 'pre-line' }}>{erreur}</div>}
        <div className="row g-3">
          <div className="col-md-3">
            <label className="form-label">Nom</label>
            <input
              className="form-control" required value={candidat.nom}
              onChange={(e) => setCandidat({ ...candidat, nom: e.target.value })}
            />
          </div>
          <div className="col-md-3">
            <label className="form-label">Prénoms</label>
            <input
              className="form-control" required value={candidat.prenom}
              onChange={(e) => setCandidat({ ...candidat, prenom: e.target.value })}
            />
          </div>
          <div className="col-md-2">
            <label className="form-label">Sexe</label>
            <select
              className="form-select" value={candidat.sexe}
              onChange={(e) => setCandidat({ ...candidat, sexe: e.target.value })}
            >
              <option value="">—</option>
              <option value="M">Masculin</option>
              <option value="F">Féminin</option>
            </select>
          </div>
          <div className="col-md-2">
            <label className="form-label">Date de naissance</label>
            <input
              type="date" className="form-control" value={candidat.date_naissance}
              onChange={(e) => setCandidat({ ...candidat, date_naissance: e.target.value })}
            />
          </div>
          <div className="col-md-2">
            <label className="form-label">Téléphone</label>
            <input
              className="form-control" value={candidat.telephone}
              onChange={(e) => setCandidat({ ...candidat, telephone: e.target.value })}
            />
          </div>
          <div className="col-md-4">
            <label className="form-label">Email</label>
            <input
              type="email" className="form-control" value={candidat.email}
              onChange={(e) => setCandidat({ ...candidat, email: e.target.value })}
            />
          </div>
          <div className="col-md-4">
            <label className="form-label">Formation demandée</label>
            <select
              className="form-select" required value={dossier.ref_formation_id}
              onChange={(e) => setDossier({ ...dossier, ref_formation_id: e.target.value })}
            >
              <option value="">Choisir…</option>
              {formations.map((f) => <option key={f.id} value={f.id}>{f.intitule}</option>)}
            </select>
          </div>
          <div className="col-md-4">
            <label className="form-label">Niveau demandé</label>
            <select
              className="form-select" required value={dossier.niveau_id}
              onChange={(e) => setDossier({ ...dossier, niveau_id: e.target.value })}
            >
              <option value="">Choisir…</option>
              {niveaux.map((n) => <option key={n.id} value={n.id}>{n.code} — {n.libelle}</option>)}
            </select>
          </div>
        </div>
        <div className="mt-3 d-flex gap-2">
          <button className="btn btn-primary" disabled={envoi || !annee}>
            {envoi && <span className="spinner-border spinner-border-sm me-1"></span>}
            Enregistrer
          </button>
          <button type="button" className="btn btn-outline-secondary" onClick={onAnnuler}>Annuler</button>
        </div>
        {!annee && (
          <div className="alert alert-warning mt-3 mb-0">
            Aucune année académique courante n’est définie. Créez-la dans l’administration
            avant d’enregistrer une candidature.
          </div>
        )}
      </form>
    </div>
  )
}

export default function Candidatures() {
  const { showToast } = useToast()
  const [candidatures, setCandidatures] = useState([])
  const [annee, setAnnee] = useState(null)
  const [formations, setFormations] = useState([])
  const [niveaux, setNiveaux] = useState([])
  const [filtres, setFiltres] = useState({ statut: '', q: '' })
  const [selection, setSelection] = useState(null)
  const [creation, setCreation] = useState(false)
  const [loading, setLoading] = useState(true)

  const charger = useCallback(async () => {
    setLoading(true)
    try {
      const params = {}
      if (filtres.statut) params.statut = filtres.statut
      if (filtres.q) params.q = filtres.q
      const res = await listCandidatures(params)
      setCandidatures(res.data)
    } catch (err) {
      showToast(messageErreur(err, 'Chargement des candidatures impossible'), 'error')
    } finally {
      setLoading(false)
    }
  }, [filtres.statut, filtres.q, showToast])

  useEffect(() => {
    (async () => {
      try {
        const [anneeCourante, formationsRes, niveauxRes] = await Promise.all([
          getAnneeCourante(),
          getRefFormations(),
          getRefScolarite('niveaux', { actif: 1 }),
        ])
        setAnnee(anneeCourante)
        setNiveaux(niveauxRes.data || [])
        setFormations(formationsRes.data || [])
      } catch {
        // Les référentiels manquants sont signalés à l'usage, dans le formulaire.
      }
    })()
  }, [])

  useEffect(() => { charger() }, [charger])

  // Indicateurs de pilotage, calculés sur la liste affichée (aucun appel API
  // supplémentaire) : ils reprennent la logique des tuiles KPI du
  // « Tableau de bord LMD 2026 ».
  const indicateurs = useMemo(() => {
    const total = candidatures.length
    const complets = candidatures.filter((c) => (c.taux_completude ?? 0) === 100).length
    const enCours = candidatures.filter((c) =>
      ['SOUMISE', 'EN_ATTENTE_DE_VERIFICATION', 'PIECES_INCOMPLETES', 'EN_ETUDE'].includes(c.statut)
    ).length
    const admis = candidatures.filter((c) =>
      ['ADMIS', 'ADMIS_SOUS_RESERVE'].includes(c.statut)
    ).length
    return { total, complets, enCours, admis }
  }, [candidatures])

  return (
    <div className="cand-page">
      {/* ── Bandeau d'accueil (matière de la référence LMD2026) ── */}
      <div className="cand-hero">
        <div className="cand-hero-text">
          <span className="plaquette plaquette-primary cand-hero-badge">
            <i className="bi bi-mortarboard"></i>Scolarité — Admissions
          </span>
          <h1 className="cand-hero-title">Candidatures</h1>
          <p className="cand-hero-sub">
            {annee ? `Année ${annee.libelle}` : 'Année courante non définie'}
            {' · '}Dossiers d'admission et pièces justificatives
          </p>
        </div>
        <button className="btn-premium-primary" onClick={() => setCreation((c) => !c)}>
          <i className="bi bi-plus-lg"></i>
          {creation ? 'Fermer le formulaire' : 'Nouvelle candidature'}
        </button>
      </div>

      {/* ── Tuiles KPI ── */}
      <div className="cand-kpi-row">
        <div className="cand-kpi">
          <div>
            <span className="cand-kpi-label">Dossiers reçus</span>
            <span className="cand-kpi-value">{indicateurs.total}</span>
          </div>
          <div className="cand-kpi-icon is-blue"><i className="bi bi-file-earmark-text-fill"></i></div>
        </div>
        <div className="cand-kpi">
          <div>
            <span className="cand-kpi-label">Dossiers complets</span>
            <span className="cand-kpi-value">{indicateurs.complets}</span>
          </div>
          <div className="cand-kpi-icon is-green"><i className="bi bi-check2-circle"></i></div>
        </div>
        <div className="cand-kpi">
          <div>
            <span className="cand-kpi-label">En cours de traitement</span>
            <span className="cand-kpi-value">{indicateurs.enCours}</span>
          </div>
          <div className="cand-kpi-icon is-amber"><i className="bi bi-hourglass-split"></i></div>
        </div>
        <div className="cand-kpi">
          <div>
            <span className="cand-kpi-label">Admis</span>
            <span className="cand-kpi-value">{indicateurs.admis}</span>
          </div>
          <div className="cand-kpi-icon is-slate"><i className="bi bi-award"></i></div>
        </div>
      </div>

      {creation && (
        <NouvelleCandidature
          annee={annee}
          formations={formations}
          niveaux={niveaux}
          onAnnuler={() => setCreation(false)}
          onCree={() => { setCreation(false); charger() }}
        />
      )}

      {selection && (
        <DossierPanel
          candidature={selection}
          onClose={() => setSelection(null)}
          onChange={charger}
        />
      )}

      {/* ── Liste des dossiers ── */}
      <div className="card cand-panel">
        <div className="cand-panel-head">
          <h2 className="cand-panel-title">
            <i className="bi bi-list-check"></i>Dossiers de candidature
          </h2>
          <span className="cand-count-pill">
            {candidatures.length} dossier{candidatures.length > 1 ? 's' : ''}
          </span>
        </div>
        <div className="cand-panel-body">
          <div className="cand-filters">
            <div className="cand-search">
              <i className="bi bi-search"></i>
              <input
                className="form-control form-control-sm"
                placeholder="Rechercher un numéro, un nom…"
                aria-label="Rechercher une candidature"
                value={filtres.q}
                onChange={(e) => setFiltres({ ...filtres, q: e.target.value })}
              />
            </div>
            <select
              className="form-select form-select-sm cand-filter-select"
              aria-label="Filtrer par statut"
              value={filtres.statut}
              onChange={(e) => setFiltres({ ...filtres, statut: e.target.value })}
            >
              <option value="">Tous les statuts</option>
              {STATUTS.map(([valeur, libelle]) => (
                <option key={valeur} value={valeur}>{libelle}</option>
              ))}
            </select>
          </div>

          {loading ? (
            <div className="text-center py-4"><div className="spinner-border"></div></div>
          ) : (
            <div className="table-responsive cand-table-wrap">
              <table className="table table-hover align-middle cand-table">
                <thead>
                  <tr>
                    <th>N°</th><th>Candidat</th><th>Formation</th><th>Niveau</th>
                    <th>Statut</th><th>Dossier</th><th></th>
                  </tr>
                </thead>
                <tbody>
                  {candidatures.map((c) => (
                    <tr key={c.id}>
                      <td className="text-nowrap"><span className="cand-numero">{c.numero}</span></td>
                      <td className="cand-candidat">{c.candidat}</td>
                      <td className="cand-formation">{c.ref_formation}</td>
                      <td>{c.niveau}</td>
                      <td><StatutBadge statut={c.statut} libelle={c.statut_libelle} /></td>
                      <td className="cand-progress">
                        <CompletudeBar
                          validees={c.pieces_validees}
                          total={c.pieces_obligatoires}
                          taux={c.taux_completude}
                        />
                      </td>
                      <td className="text-end">
                        <button
                          className="btn btn-sm cand-open-btn"
                          onClick={() => setSelection(c)}
                        >
                          <i className="bi bi-folder2-open me-1"></i>Ouvrir
                        </button>
                      </td>
                    </tr>
                  ))}
                  {candidatures.length === 0 && (
                    <tr>
                      <td colSpan={7}>
                        <div className="cand-empty">
                          <i className="bi bi-inbox"></i>
                          Aucune candidature.
                        </div>
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
