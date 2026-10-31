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
import '../../styles/modale-premium.css'

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
    <section className="cand-panel cand-dossier" aria-labelledby="titre-dossier-candidature">
      <header className="cand-dossier-entete">
        <div>
          <span className="cand-dossier-numero">{detail.numero}</span>
          <span className="cand-dossier-nom" id="titre-dossier-candidature">{detail.candidat}</span>
          <span className="cand-dossier-sous">Dossier de candidature</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', marginLeft: 'auto' }}>
          <StatutBadge statut={detail.statut} libelle={detail.statut_libelle} />
          <button type="button" className="mp-fermer" onClick={onClose} aria-label="Fermer le dossier">
            <i className="bi bi-x-lg" aria-hidden="true"></i>
          </button>
        </div>
      </header>

      <div className="cand-panel-body">
        {chargement ? (
          <div className="cand-chargement">
            <span className="spinner-border" aria-hidden="true"></span>Chargement du dossier…
          </div>
        ) : (
          <>
            <div className="mp-fiche">
              <div className="mp-fiche-item">
                <span className="mp-fiche-cle">Formation</span>
                <span className="mp-fiche-valeur">{detail.ref_formation || '—'}</span>
              </div>
              <div className="mp-fiche-item">
                <span className="mp-fiche-cle">Niveau</span>
                <span className="mp-fiche-valeur">{detail.niveau || '—'}</span>
              </div>
              <div className="mp-fiche-item">
                <span className="mp-fiche-cle">Année académique</span>
                <span className="mp-fiche-valeur">{detail.annee_academique || '—'}</span>
              </div>
              <div className="mp-fiche-item">
                <span className="mp-fiche-cle">Pièces attendues</span>
                <span className="mp-fiche-valeur">{detail.pieces_obligatoires ?? 0}</span>
              </div>
            </div>

            <h3 className="cand-section-titre">
              <i className="bi bi-paperclip" aria-hidden="true"></i>Pièces justificatives
            </h3>
            <div className="cand-table-wrap">
              <table className="cand-table cand-table--simple">
                <thead>
                  <tr>
                    <th scope="col">Pièce</th>
                    <th scope="col">Statut</th>
                    <th scope="col">Fichier</th>
                    <th scope="col" className="cand-col-actions">Vérification</th>
                  </tr>
                </thead>
                <tbody>
                  {pieces.map((piece) => (
                    <tr key={piece.id}>
                      <td>
                        {piece.type_piece}
                        {piece.obligatoire && <span className="mp-requis" title="Obligatoire">*</span>}
                        {piece.est_expiree && <span className="cand-puce-alerte">Expirée</span>}
                      </td>
                      <td><StatutBadge statut={piece.statut} libelle={piece.statut_libelle} /></td>
                      <td>
                        <label className="cand-televerser">
                          <input
                            type="file"
                            className="cand-televerser-input"
                            aria-label={`Téléverser la pièce ${piece.type_piece}`}
                            onChange={(e) => televerser(piece, e.target.files?.[0])}
                          />
                          <i className="bi bi-cloud-arrow-up" aria-hidden="true"></i>
                          <span>{piece.a_fichier ? 'Remplacer' : 'Téléverser'}</span>
                        </label>
                      </td>
                      <td className="cand-col-actions">
                        <div className="cand-actions">
                          <button
                            className="cand-action cand-action--succes"
                            disabled={action !== null || !piece.a_fichier}
                            onClick={() => statuerPiece(piece, 'VALIDEE')}
                            aria-label="Valider la pièce"
                            title="Valider la pièce"
                          >
                            <i className="bi bi-check2" aria-hidden="true"></i>
                          </button>
                          <button
                            className="cand-action cand-action--danger"
                            disabled={action !== null || !piece.a_fichier}
                            onClick={() => statuerPiece(piece, 'REFUSEE')}
                            aria-label="Refuser la pièce"
                            title="Rejeter la pièce"
                          >
                            <i className="bi bi-x-lg" aria-hidden="true"></i>
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                  {pieces.length === 0 && (
                    <tr><td colSpan={4}><span className="cand-texte-doux">Aucune pièce attendue.</span></td></tr>
                  )}
                </tbody>
              </table>
            </div>

            <h3 className="cand-section-titre">
              <i className="bi bi-graph-up" aria-hidden="true"></i>Complétude du dossier
            </h3>
            <div className="cand-completude">
              <span className="cand-completude-label">Pièces obligatoires validées</span>
              <div className="cand-completude-jauge">
                <CompletudeBar
                  validees={detail.pieces_validees}
                  total={detail.pieces_obligatoires}
                  taux={detail.taux_completude}
                />
              </div>
            </div>

            <h3 className="cand-section-titre">
              <i className="bi bi-signpost-split" aria-hidden="true"></i>Suite du parcours
            </h3>
            <div className="cand-transitions">
              {transitions.map((statut) => (
                <button
                  key={statut}
                  className={`cand-btn-fantome${statut === 'ANNULE' ? ' cand-btn-fantome--danger' : ''}`}
                  disabled={action !== null}
                  onClick={() => appliquerTransition(statut)}
                >
                  {action === statut && <span className="spinner-border" aria-hidden="true"></span>}
                  {LIBELLES_STATUT[statut] || statut}
                </button>
              ))}
              {transitions.length === 0 && (
                <span className="cand-texte-doux">Aucune transition possible depuis ce statut.</span>
              )}
              {peutOuvrirAdmission && (
                <button
                  className="cand-btn-principal"
                  disabled={action !== null}
                  onClick={ouvrirAdmission}
                >
                  <i className="bi bi-arrow-right-circle" aria-hidden="true"></i>
                  Ouvrir une admission
                </button>
              )}
            </div>
          </>
        )}
      </div>
    </section>
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
    <section className="cand-panel cand-form" aria-labelledby="titre-nouvelle-candidature">
      <header className="cand-panel-head">
        <h2 className="cand-panel-title" id="titre-nouvelle-candidature">
          <i className="bi bi-person-plus" aria-hidden="true"></i>Nouvelle candidature
        </h2>
        <button type="button" className="mp-fermer" onClick={onAnnuler} aria-label="Fermer le formulaire">
          <i className="bi bi-x-lg" aria-hidden="true"></i>
        </button>
      </header>

      <form className="cand-panel-body" onSubmit={soumettre}>
        {erreur && <div className="cand-alerte" role="alert">{erreur}</div>}

        <div className="cand-grille-form">
          <div className="cand-champ cand-champ--2">
            <label className="cand-etiquette" htmlFor="cand-nom">Nom</label>
            <input
              id="cand-nom" className="cand-saisie" required value={candidat.nom}
              onChange={(e) => setCandidat({ ...candidat, nom: e.target.value })}
            />
          </div>
          <div className="cand-champ cand-champ--2">
            <label className="cand-etiquette" htmlFor="cand-prenom">Prénoms</label>
            <input
              id="cand-prenom" className="cand-saisie" required value={candidat.prenom}
              onChange={(e) => setCandidat({ ...candidat, prenom: e.target.value })}
            />
          </div>

          <div className="cand-champ">
            <label className="cand-etiquette" htmlFor="cand-sexe">Sexe</label>
            <select
              id="cand-sexe" className="cand-saisie" value={candidat.sexe}
              onChange={(e) => setCandidat({ ...candidat, sexe: e.target.value })}
            >
              <option value="">—</option>
              <option value="M">Masculin</option>
              <option value="F">Féminin</option>
            </select>
          </div>
          <div className="cand-champ">
            <label className="cand-etiquette" htmlFor="cand-naissance">Date de naissance</label>
            <input
              id="cand-naissance" type="date" className="cand-saisie" value={candidat.date_naissance}
              onChange={(e) => setCandidat({ ...candidat, date_naissance: e.target.value })}
            />
          </div>
          <div className="cand-champ cand-champ--2">
            <label className="cand-etiquette" htmlFor="cand-telephone">Téléphone</label>
            <input
              id="cand-telephone" className="cand-saisie" value={candidat.telephone}
              onChange={(e) => setCandidat({ ...candidat, telephone: e.target.value })}
            />
          </div>

          <div className="cand-champ cand-champ--2">
            <label className="cand-etiquette" htmlFor="cand-email">Email</label>
            <input
              id="cand-email" type="email" className="cand-saisie" value={candidat.email}
              onChange={(e) => setCandidat({ ...candidat, email: e.target.value })}
            />
          </div>
          <div className="cand-champ cand-champ--2">
            <label className="cand-etiquette" htmlFor="cand-formation">Formation demandée</label>
            <select
              id="cand-formation" className="cand-saisie" required value={dossier.ref_formation_id}
              onChange={(e) => setDossier({ ...dossier, ref_formation_id: e.target.value })}
            >
              <option value="">Choisir une formation…</option>
              {formations.map((f) => <option key={f.id} value={f.id}>{f.intitule}</option>)}
            </select>
          </div>

          <div className="cand-champ cand-champ--2">
            <label className="cand-etiquette" htmlFor="cand-niveau">Niveau demandé</label>
            <select
              id="cand-niveau" className="cand-saisie" required value={dossier.niveau_id}
              onChange={(e) => setDossier({ ...dossier, niveau_id: e.target.value })}
            >
              <option value="">Choisir un niveau…</option>
              {niveaux.map((n) => <option key={n.id} value={n.id}>{n.code} — {n.libelle}</option>)}
            </select>
          </div>
        </div>

        {!annee && (
          <div className="cand-alerte cand-alerte--attention" role="status">
            Aucune année académique courante n’est définie. Créez-la dans l’administration
            avant d’enregistrer une candidature.
          </div>
        )}

        <div className="cand-form-actions">
          <button type="button" className="cand-btn-fantome" onClick={onAnnuler}>
            Annuler
          </button>
          <button className="cand-btn-principal" disabled={envoi || !annee}>
            {envoi && <span className="spinner-border" aria-hidden="true"></span>}
            <i className="bi bi-check2" aria-hidden="true"></i>
            Enregistrer la candidature
          </button>
        </div>
      </form>
    </section>
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
        <div className="cand-hero-identite">
          <span className="cand-hero-icone" aria-hidden="true">
            <i className="bi bi-mortarboard"></i>
          </span>
          <div className="cand-hero-text">
            <span className="cand-hero-badge">Scolarité — Admissions</span>
            <h1 className="cand-hero-title">Candidatures</h1>
            <p className="cand-hero-sub">
              {annee ? `Année ${annee.libelle}` : 'Année courante non définie'}
              {' · '}Dossiers d’admission et pièces justificatives
            </p>
          </div>
        </div>
        <button className="btn-premium-primary" onClick={() => setCreation((c) => !c)}>
          <i className="bi bi-plus-lg"></i>
          {creation ? 'Fermer le formulaire' : 'Nouvelle candidature'}
        </button>
      </div>

      {/* ── Tuiles KPI ── */}
      <div className="cand-kpi-row">
        <div className="cand-kpi">
          <span className="cand-kpi-icon is-blue" aria-hidden="true"><i className="bi bi-folder2-open"></i></span>
          <div className="cand-kpi-texte">
            <span className="cand-kpi-value">{indicateurs.total}</span>
            <span className="cand-kpi-label">Dossiers reçus</span>
          </div>
        </div>
        <div className="cand-kpi">
          <span className="cand-kpi-icon is-green" aria-hidden="true"><i className="bi bi-check2-circle"></i></span>
          <div className="cand-kpi-texte">
            <span className="cand-kpi-value">{indicateurs.complets}</span>
            <span className="cand-kpi-label">Dossiers complets</span>
          </div>
        </div>
        <div className="cand-kpi">
          <span className="cand-kpi-icon is-amber" aria-hidden="true"><i className="bi bi-hourglass-split"></i></span>
          <div className="cand-kpi-texte">
            <span className="cand-kpi-value">{indicateurs.enCours}</span>
            <span className="cand-kpi-label">En cours de traitement</span>
          </div>
        </div>
        <div className="cand-kpi">
          <span className="cand-kpi-icon is-slate" aria-hidden="true"><i className="bi bi-award"></i></span>
          <div className="cand-kpi-texte">
            <span className="cand-kpi-value">{indicateurs.admis}</span>
            <span className="cand-kpi-label">Admis</span>
          </div>
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
                className="cand-input"
                type="search"
                placeholder="Rechercher un numéro, un nom…"
                aria-label="Rechercher une candidature"
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
              {STATUTS.map(([valeur, libelle]) => (
                <option key={valeur} value={valeur}>{libelle}</option>
              ))}
            </select>
          </div>

          {loading ? (
            <div className="cand-chargement"><span className="spinner-border" aria-hidden="true"></span>Chargement des candidatures…</div>
          ) : (
            <>
              <div className="cand-table-wrap">
              <table className="cand-table cand-table--candidatures">
                <thead>
                  <tr>
                    <th>N°</th><th>Candidat</th><th>Formation</th><th>Niveau</th>
                    <th>Statut</th><th>Dossier</th><th className="cand-th-actions"><span className="cand-sr-only">Actions</span></th>
                  </tr>
                </thead>
                <tbody>
                  {candidatures.map((c) => (
                    <tr key={c.id}>
                      <td className="cand-col-etroit"><span className="cand-numero">{c.numero}</span></td>
                      <td><span className="cand-etudiant">{c.candidat}</span></td>
                      <td className="cand-col-formation">
                        <span className="cand-texte-formation" title={c.ref_formation}>{c.ref_formation}</span>
                      </td>
                      <td><span className="cand-badge-neutre">{c.niveau}</span></td>
                      <td><StatutBadge statut={c.statut} libelle={c.statut_libelle} /></td>
                      <td className="cand-progress">
                        <CompletudeBar
                          validees={c.pieces_validees}
                          total={c.pieces_obligatoires}
                          taux={c.taux_completude}
                        />
                      </td>
                      <td className="cand-col-actions">
                        <div className="cand-actions">
                          <button
                            className="cand-action cand-action--ouvrir"
                            onClick={() => setSelection(c)}
                            aria-label={`Ouvrir le dossier ${c.numero}`}
                            title="Ouvrir le dossier"
                          >
                            <i className="bi bi-folder2-open" aria-hidden="true"></i>
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                  {candidatures.length === 0 && (
                    <tr>
                      <td colSpan={7}>
                        <div className="cand-vide">
                          <span className="cand-vide-icone" aria-hidden="true">
                            <i className="bi bi-inbox"></i>
                          </span>
                          <p className="cand-vide-titre">Aucune candidature</p>
                          <p className="cand-vide-texte">
                            Aucun dossier ne correspond à la recherche ou au statut sélectionné.
                            Vous pouvez déposer une nouvelle candidature.
                          </p>
                          <div className="cand-vide-actions">
                            <button className="cand-btn-principal" onClick={() => setCreation(true)}>
                              <i className="bi bi-plus-lg" aria-hidden="true"></i>
                              Nouvelle candidature
                            </button>
                          </div>
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
      </div>
    </div>
  )
}
