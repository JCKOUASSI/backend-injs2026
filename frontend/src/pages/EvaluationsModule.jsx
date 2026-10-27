import { useState, useEffect, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useToast } from '../context/ToastContext'
import { useDroits } from '../hooks/useDroits'
import {
  getEvaluations, getSessions, getEvaluation, getComposants,
  getParticipants, getResultatsEcue, getResultatsUe, getResultatsSemestre,
  getJurySessions, getJuryAnomalies, getJuryStatistiques,
  saisirNotes, getReleves, getReleve, getPassageNiveau,
} from '../services/evaluations'
import '../styles/evaluations.css'

/**
 * Module Évaluations — INJS-LMD 2026 / INJS Abidjan (Marcory).
 *
 * Invariants :
 * - aucun calcul académique dans React (moyenne, seuil, validation,
 *   crédits, compensation) : le backend calcule, la page affiche ;
 * - `null` n'est JAMAIS rendu ni converti en 0 (D2 / D6) ;
 * - aucune règle de rattrapage (D3) : rien n'est supposé côté client.
 * - aucun indicateur absent de l'API n'est inventé : la tuile affiche
 *   « Non disponible » plutôt qu'un chiffre plausible (E1.3 §8).
 */

/** Valeur sûre — usage interdit : `note || 0`. */
function affichage(v) {
  if (v === null || v === undefined || v === '') return 'Non renseigné'
  return v
}

/**
 * Volumétrie d'une page paginée DRF.
 *
 * `count` est l'effectif TOTAL renvoyé par l'API ; `results.length` ne porte
 * que sur la page courante (50 par défaut). Afficher `results.length` dans un
 * compteur d'indicateur donnerait un chiffre faux dès la première page
 * suivante : on lit donc `count` quand l'API le fournit.
 */
function volumetrie(donnees) {
  const lignes = donnees?.results ?? []
  const total = Number.isFinite(Number(donnees?.count)) ? Number(donnees.count) : lignes.length
  return { lignes, total }
}

/** Page de résultats : liste + effectif total, sans jamais supposer le format. */
function useCharge(chargeur, deps = []) {
  const [donnees, setDonnees] = useState(null)
  const [chargement, setChargement] = useState(true)
  const [erreur, setErreur] = useState(null)
  // Incrémentée à chaque appel : permet à l'utilisateur de réessayer.
  const [tentative, setTentative] = useState(0)

  useEffect(() => {
    let annule = false
    setChargement(true)
    setErreur(null)
    Promise.resolve()
      .then(chargeur)
      .then((d) => { if (!annule) setDonnees(d) })
      // On conserve le statut HTTP ET le `detail` renvoyé par l'API : sans
      // cela, toute panne s'affichait comme un message unique et inexploitable.
      .catch((e) => {
        if (annule) return
        setErreur({
          statut: e?.response?.status ?? null,
          detail: e?.response?.data?.detail ?? null,
          code: e?.response?.data?.code ?? null,
        })
      })
      .finally(() => { if (!annule) setChargement(false) })
    return () => { annule = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tentative])

  const reessayer = useCallback(() => setTentative((t) => t + 1), [])
  return { donnees, chargement, erreur, reessayer }
}

/* ── Textes d'erreur par statut : chaque code a son propre message ── */
const ERREURS = {
  401: {
    titre: 'Session expirée',
    icone: 'bi-shield-lock',
    detail: "Votre session a expiré. Reconnectez-vous pour accéder aux évaluations.",
  },
  403: {
    titre: 'Accès refusé',
    icone: 'bi-lock',
    detail: "Vous ne disposez pas des droits requis pour consulter cette page.",
  },
  404: {
    titre: 'Ressource introuvable',
    icone: 'bi-question-circle',
    detail: "Les données demandées n'existent pas ou ne sont plus disponibles.",
  },
}

/** Panneau d'erreur typé — jamais « Erreur lors du chargement » seul. */
function PanneauErreur({ erreur, onReessayer }) {
  if (!erreur) return null
  const base = ERREURS[erreur.statut]
  const classe = erreur.statut ? ` ev-erreur--${erreur.statut}` : ''
  return (
    <div className={`ev-erreur${classe}`} role="alert">
      <span className="ev-erreur-titre">
        <i className={`bi ${base?.icone ?? 'bi-exclamation-octagon'}`} aria-hidden="true" />
        {base?.titre ?? 'Impossible de charger les évaluations'}
      </span>
      <span className="ev-erreur-detail">
        {erreur.detail || base?.detail || "Le service n'a pas pu répondre."}
      </span>
      {onReessayer && (
        <span className="ev-erreur-actions">
          <button type="button" className="ev-btn ev-btn--ghost" onClick={onReessayer}>
            <i className="bi bi-arrow-clockwise" aria-hidden="true" />
            Réessayer
          </button>
        </span>
      )}
    </div>
  )
}

/** Squelettes de chargement : pas d'écran blanc pendant les appels API. */
function Squelette({ lignes = 5 }) {
  return (
    <div aria-busy="true" aria-live="polite">
      <span className="visually-hidden">Chargement en cours…</span>
      <div className="ev-skeleton ev-skeleton-titre" />
      {Array.from({ length: lignes }).map((_, i) => (
        <div key={i} className="ev-skeleton ev-skeleton-ligne" style={{ width: `${100 - i * 7}%` }} />
      ))}
    </div>
  )
}

/** État vide travaillé : icône, message explicatif, action si le droit existe. */
function EtatVide({ icone, titre, message, action }) {
  return (
    <div className="px-empty">
      <span className="px-empty-badge">
        <i className={`bi ${icone}`} aria-hidden="true" />
      </span>
      <strong style={{ color: '#475569', fontSize: '0.95rem' }}>{titre}</strong>
      <span style={{ maxWidth: '46ch', textAlign: 'center', fontWeight: 500 }}>{message}</span>
      {action}
    </div>
  )
}

/**
 * Enveloppe d'état d'une page du module : squelette → erreur typée → contenu.
 * Le hero reste visible même en cas d'erreur : l'utilisateur garde le titre
 * et le fil du sous-module.
 */
function Page({ titre, icone, sousTitre, actions, chargement, erreur, reessayer, children, skeleton }) {
  return (
    <div className="page-container ev-scope">
      <header className="px-hero">
        <span className="px-hero-icon" aria-hidden="true">
          <i className={`bi ${icone}`} />
        </span>
        <div className="px-hero-text">
          <h1 className="px-hero-title ev-titre">{titre}</h1>
          {sousTitre && <p className="px-hero-intro">{sousTitre}</p>}
        </div>
        {actions && <div className="px-hero-side">{actions}</div>}
      </header>
      {chargement ? <Squelette lignes={skeleton ?? 5} /> : (
        <>
          <PanneauErreur erreur={erreur} onReessayer={erreur ? reessayer : null} />
          {!erreur && children}
        </>
      )}
    </div>
  )
}

/** Badge d'état : toujours accompagné d'un texte (jamais la couleur seule). */
function BadgeEtat({ valeur, libelle }) {
  const v = String(valeur ?? '').toUpperCase()
  let variante = ''
  if (['PLANIFIEE', 'PLANIFIÉE', 'BROUILLON', 'PREVU', 'PRÉVU'].includes(v)) variante = ' ev-badge--info'
  else if (['EN_COURS', 'COURS'].includes(v)) variante = ' ev-badge--warn'
  else if (['CORRIGEE', 'CORRIGÉE', 'VALIDE', 'VALIDÉ', 'PUBLIE', 'TERMINEE', 'TERMINÉE'].includes(v)) variante = ' ev-badge--ok'
  else if (['VERROUILLE', 'VERROUILLEE', 'ARCHIVE', 'ARCHIVEE'].includes(v)) variante = ' ev-badge--danger'
  return <span className={`ev-badge${variante}`}>{libelle ?? v.replace(/_/g, ' ')}</span>
}

/** Bandeau de verrouillage — champ réel : `composition_verrouillee`. */
function BandeauVerrou({ verrouille }) {
  return (
    <span className={`ev-verrou ${verrouille ? 'ev-verrou--bloque' : 'ev-verrou--ouvert'}`}>
      <i className={`bi ${verrouille ? 'bi-lock-fill' : 'bi-unlock'}`} aria-hidden="true" />
      {verrouille ? 'Composition verrouillée' : 'Saisie ouverte'}
    </span>
  )
}

function ColonnesEvaluations() {
  return (
    <>
      <th scope="col">ECUE</th>
      <th scope="col">Type</th>
      <th scope="col">Date prévue</th>
      <th scope="col">État</th>
      <th scope="col">Verrouillage</th>
      <th scope="col"><span className="visually-hidden">Actions</span></th>
    </>
  )
}

function ColonnesSessions() {
  return (
    <>
      <th scope="col">Année</th>
      <th scope="col">Type de session</th>
      <th scope="col">Début</th>
      <th scope="col">Fin</th>
      <th scope="col">État</th>
      <th scope="col">Évaluations</th>
    </>
  )
}

function CellulesEvaluations({ l, navigate, peutSaisir }) {
  return (
    <>
      <td><span className="ev-note-bareme">{affichage(l.ecue_code)}</span></td>
      <td>{affichage(l.type_code)}</td>
      <td>{affichage(l.date_prevue)}</td>
      <td><BadgeEtat valeur={l.statut} /></td>
      <td><BandeauVerrou verrouille={Boolean(l.composition_verrouillee)} /></td>
      <td>
        {peutSaisir ? (
          <button
            type="button"
            className="ev-btn ev-btn--ghost"
            onClick={() => navigate(`/evaluations/saisie/${l.id}`)}
            aria-label={`Saisir les notes de ${affichage(l.libelle)}`}
          >
            Saisir
          </button>
        ) : (
          <span className="px-dash" aria-label="Saisie non autorisée">—</span>
        )}
      </td>
    </>
  )
}

function CellulesSessions({ l }) {
  return (
    <>
      <td>{affichage(l.annee_libelle)}</td>
      <td>{affichage(l.type_session)}</td>
      <td>{affichage(l.date_debut)}</td>
      <td>{affichage(l.date_fin)}</td>
      <td><BadgeEtat valeur={l.statut} /></td>
      <td className="px-num">{affichage(l.nb_evaluations)}</td>
    </>
  )
}

/**
 * Champs de recherche du registre.
 *
 * On ne filtre que sur des champs RÉELLEMENT présents dans les payloads :
 * `EvaluationSerializer` ne renvoie aucun `annee_libelle` (il n'existe que sur
 * `SessionEvaluationSerializer`). Filtrer sur un champ absent rendait la
 * recherche « année » inopérante tout en l'annonçant dans le placeholder.
 */
const CHAMPS_RECHERCHE = {
  evaluations: ['libelle', 'ecue_code', 'type_code', 'statut'],
  sessions: ['libelle', 'annee_libelle', 'type_session', 'niveau_code', 'statut'],
}
const PLACEHOLDER_RECHERCHE = {
  evaluations: 'Libellé, ECUE, type, état…',
  sessions: 'Libellé, année, type de session, niveau…',
}

/**
 * Panneau « Registre » : table + état vide + segments Évaluations / Sessions.
 * Les colonnes reprennent uniquement des champs réellement présents dans les
 * payloads backend (EvaluationSerializer / SessionEvaluationSerializer).
 */
function PanneauRegistre({ onglet, setOnglet, recherche, setRecherche, lignes, navigate, peutSaisir }) {
  const estEvaluations = onglet === 'evaluations'
  return (
    <div className="card px-panel">
      <div className="px-panel-head">
        <div className="px-panel-headtext">
          <h2 className="px-panel-title">
            <i className="bi bi-folder2-open" aria-hidden="true" />
            Registre
          </h2>
          <p className="px-panel-sub">
            {estEvaluations
              ? 'Évaluations rattachées à vos affectations pédagogiques.'
              : 'Sessions d’évaluation rattachées à vos affectations pédagogiques.'}
          </p>
        </div>
        <div className="px-panel-tools">
          {/* `role="group"` + `aria-pressed` : un `role="tablist"` exigerait des
              `aria-selected` et un `tabpanel` associé, absents ici. Même
              convention que les filtres du Contrôle des notes. */}
          <div className="ev-segments" role="group" aria-label="Afficher les évaluations ou les sessions">
            {[['evaluations', 'Évaluations'], ['sessions', 'Sessions']].map(([cle, libelle]) => (
              <button
                key={cle}
                type="button"
                className="ev-segment"
                aria-pressed={estEvaluations === (cle === 'evaluations')}
                onClick={() => setOnglet(cle)}
              >
                {libelle}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="px-toolbar-body">
        <label className="px-field px-field--recherche" htmlFor="ev-recherche">
          <span className="px-field-label">Recherche</span>
          <span className="px-search">
            <i className="bi bi-search" aria-hidden="true" />
            <input
              id="ev-recherche"
              type="search"
              className="px-input"
              placeholder={PLACEHOLDER_RECHERCHE[onglet]}
              value={recherche}
              onChange={(e) => setRecherche(e.target.value)}
            />
          </span>
        </label>
        <div className="px-toolbar-actions">
          <button
            type="button"
            className="ev-btn ev-btn--ghost"
            onClick={() => setRecherche('')}
            disabled={!recherche}
          >
            <i className="bi bi-x-circle" aria-hidden="true" />
            Réinitialiser
          </button>
        </div>
      </div>

      <div className="card-body-flush">
        {lignes.length === 0 ? (
          <EtatVide
            icone={estEvaluations ? 'bi-clipboard-x' : 'bi-calendar-x'}
            titre={recherche
              ? 'Aucun résultat'
              : (estEvaluations ? 'Aucune évaluation disponible' : 'Aucune session disponible')}
            message={recherche
              ? (estEvaluations
                ? 'Aucune évaluation ne correspond à votre recherche.'
                : 'Aucune session ne correspond à votre recherche.')
              : (estEvaluations
                ? 'Aucune évaluation n’est rattachée à votre périmètre pédagogique.'
                : 'Aucune session d’évaluation n’est rattachée à votre périmètre pédagogique.')}
            /* Aucun raccourci de saisie ici : l'action « Saisir des notes » est
               déjà dans l'en-tête, et la saisie n'a rien à proposer quand le
               registre est vide (l'écran de saisie listerait le même vide). */
            action={null}
          />
        ) : (
          <div className="ev-table-scroll">
            <table className="table px-table">
              <caption className="visually-hidden">
                Registre des {estEvaluations ? 'évaluations' : 'sessions'}
              </caption>
              <thead>
                <tr>
                  <th scope="col">Libellé</th>
                  {estEvaluations ? <ColonnesEvaluations /> : <ColonnesSessions />}
                </tr>
              </thead>
              <tbody>
                {lignes.map((l) => (
                  <tr key={l.id}>
                    <td style={{ fontWeight: 600 }}>{affichage(l.libelle)}</td>
                    {estEvaluations
                      ? <CellulesEvaluations l={l} navigate={navigate} peutSaisir={peutSaisir} />
                      : <CellulesSessions l={l} />}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}

// ── 1. Évaluations (registre) ──────────────────────────────────────────────

export function ListeEvaluations() {
  const [onglet, setOnglet] = useState('evaluations')
  const navigate = useNavigate()
  const { peut } = useDroits()
  const [recherche, setRecherche] = useState('')
  const { donnees, chargement, erreur, reessayer } = useCharge(
    () => (onglet === 'evaluations' ? getEvaluations() : getSessions()),
    [onglet],
  )
  // Compteur d'effectif : `count` porte le total renvoyé par l'API, pas la
  // seule page affichée.
  const { lignes, total } = volumetrie(donnees)
  // Saisie des notes : capacité `notes.gerer` (autorité backend
  // `evaluations.permissions.peut_saisir_notes`), et non le droit de gestion
  // des QUESTIONNAIRES qui ne governait pas l'écriture des notes.
  const peutSaisir = peut('notes', 'gerer')
  const estEvaluations = onglet === 'evaluations'
  // Les deux onglets ne portent pas les mêmes champs : une recherche saisie sur
  // « Sessions » (« 2026-2027 ») ne trouve rien côté évaluations. On repart
  // d'une recherche vide à chaque changement d'onglet.
  useEffect(() => { setRecherche('') }, [onglet])
  // Filtre strictement local sur les champs réellement présents dans le payload
  // de l'onglet affiché : aucun filtre n'est proposé sans donnée source.
  const filtrees = lignes.filter((l) => {
    const cible = CHAMPS_RECHERCHE[onglet]
      .map((c) => l[c] ?? '')
      .join(' ')
      .toLowerCase()
    return cible.includes(recherche.trim().toLowerCase())
  })
  return (
    <Page
      titre="Évaluations"
      icone={estEvaluations ? 'bi-clipboard-check' : 'bi-calendar-check'}
      sousTitre={estEvaluations
        ? 'Gestion des compositions de vos affectations pédagogiques'
        : 'Gestion des sessions d’évaluation de vos affectations pédagogiques'}
      chargement={chargement}
      erreur={erreur}
      reessayer={reessayer}
      actions={(
        <>
          <span className="px-count-pill px-count-pill--muted">
            <i className="bi bi-list-check" aria-hidden="true" />
            {total} {estEvaluations ? 'évaluation(s)' : 'session(s)'}
          </span>
          {peutSaisir && estEvaluations && (
            <button
              type="button"
              className="ev-btn ev-btn--primary"
              onClick={() => navigate('/evaluations/saisie')}
            >
              <i className="bi bi-pencil-square" aria-hidden="true" />
              Saisir des notes
            </button>
          )}
        </>
      )}
    >
      <PanneauRegistre
        onglet={onglet}
        setOnglet={setOnglet}
        recherche={recherche}
        setRecherche={setRecherche}
        lignes={filtrees}
        navigate={navigate}
        peutSaisir={peutSaisir}
      />
    </Page>
  )
}

/**
 * État des évaluations + activité récente du tableau de bord.
 *
 * `lignes` est la page affichée, `total` l'effectif renvoyé par l'API.
 * `pagine` signale que la page affichée n'est pas l'ensemble : les
 * répartitions sont alors explicitement annoncées comme calculées sur la page.
 */
function PanneauActivite({ lignes, total, pagine, peutSaisir, navigate }) {
  // Aucune évaluation : pas de graphique de répartition (tout serait à 0 %)
  // et surtout PAS de raccourci vers la saisie — il n'y a rien à saisir.
  if (total === 0) {
    return (
      <div className="card px-panel">
        <EtatVide
          icone="bi-clipboard-x"
          titre="Aucune évaluation disponible"
          message="Aucune évaluation n'est rattachée à votre périmètre pédagogique. Les compositions créées pour l'année en cours y apparaîtront."
        />
      </div>
    )
  }

  const verrouillees = lignes.filter((l) => l.composition_verrouillee).length
  const ouvertes = lignes.length - verrouillees
  const parStatut = (v) => lignes.filter((l) => String(l.statut ?? '').toUpperCase() === v).length
  const corrigees = parStatut('CORRIGEE') + parStatut('CORRIGÉE')
  // Les jauges se rapportent toujours à la page affichée : le ratio reste exact.
  const base = lignes.length

  return (
    <>
      <div className="card px-panel">
        <div className="px-panel-head">
          <div className="px-panel-headtext">
            <h2 className="px-panel-title">
              <i className="bi bi-bar-chart" aria-hidden="true" />
              État des évaluations
            </h2>
            <p className="px-panel-sub">
              Répartition des compositions par verrouillage et statut.
              {pagine && ` Page affichée : ${base} composition${base > 1 ? 's' : ''} sur ${total}.`}
            </p>
          </div>
        </div>
        <div className="card-body">
          <div className="ev-repartition">
            <LigneRepartition nom="Ouvertes à la saisie" compte={ouvertes} total={base} variante="warn" />
            <LigneRepartition nom="Verrouillées" compte={verrouillees} total={base} variante="ok" />
            <LigneRepartition nom="Corrigées" compte={corrigees} total={base} variante="info" />
          </div>
        </div>
      </div>

      <div className="card px-panel">
        <div className="px-panel-head">
          <div className="px-panel-headtext">
            <h2 className="px-panel-title">
              <i className="bi bi-clock-history" aria-hidden="true" />
              Dernières évaluations
            </h2>
            <p className="px-panel-sub">
              Évaluations de votre périmètre pédagogique, de la plus récente à la plus ancienne.
            </p>
          </div>
          <div className="px-panel-tools">
            <span className="px-count-pill">{base}</span>
          </div>
        </div>
        <div className="card-body-flush">
          <div className="ev-table-scroll">
            <table className="table px-table">
              <caption className="visually-hidden">Évaluations du périmètre pédagogique</caption>
              <thead>
                <tr>
                  <th scope="col">Évaluation</th>
                  <th scope="col">ECUE</th>
                  <th scope="col">Type</th>
                  <th scope="col">Date prévue</th>
                  <th scope="col">État</th>
                  <th scope="col"><span className="visually-hidden">Actions</span></th>
                </tr>
              </thead>
              <tbody>
                {lignes.map((l) => (
                  <tr key={l.id}>
                    <td style={{ fontWeight: 600 }}>{affichage(l.libelle)}</td>
                    <td><span className="ev-note-bareme">{affichage(l.ecue_code)}</span></td>
                    <td>{affichage(l.type_code)}</td>
                    <td>{affichage(l.date_prevue)}</td>
                    <td><BadgeEtat valeur={l.statut} /></td>
                    <td>
                      {peutSaisir ? (
                        <button
                          type="button"
                          className="ev-btn ev-btn--ghost"
                          onClick={() => navigate(`/evaluations/saisie/${l.id}`)}
                          aria-label={`Saisir les notes de ${affichage(l.libelle)}`}
                        >
                          Saisir
                        </button>
                      ) : (
                        <span className="px-dash" aria-label="Saisie non autorisée">—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </>
  )
}

// ── 2. Tableau de bord ──────────────────────────────────────────────────────

/**
 * Tuile d'indicateur. Si la donnée n'est pas fournie par l'API, elle affiche
 * « Non disponible » — jamais un chiffre plausible inventé (E1.3 §8).
 */
function Tuile({ icone, label, valeur, disponible = true, variante = '' }) {
  return (
    <div className={`ev-stat${variante ? ` ev-stat--${variante}` : ''}`}>
      <span className="ev-stat-icone" aria-hidden="true">
        <i className={`bi ${icone}`} />
      </span>
      <span className="ev-stat-corps">
        <span className="ev-stat-label">{label}</span>
        {disponible ? (
          <span className="ev-stat-valeur">{valeur}</span>
        ) : (
          <span className="ev-stat-indisponible">Non disponible</span>
        )}
      </span>
    </div>
  )
}

/** Ligne de répartition : pastille + libellé + jauge + compte. */
function LigneRepartition({ nom, compte, total, variante }) {
  // Part relative : simple ratio de comptage, aucun calcul académique.
  const part = total > 0 ? Math.round((compte / total) * 100) : 0
  return (
    <div className="ev-repartition-ligne">
      <span className="ev-repartition-nom">
        <span className={`ev-dot${variante ? ` ev-dot--${variante}` : ''}`} aria-hidden="true" />
        {nom}
      </span>
      <span className="ev-jauge" role="img" aria-label={`${nom} : ${compte} sur ${total}`}>
        <span className="ev-jauge-valeur" style={{ width: `${part}%` }} />
      </span>
      <span className="ev-repartition-compte">{compte}</span>
    </div>
  )
}

export function TableauDeBordEvaluations() {
  const ev = useCharge(getEvaluations)
  const se = useCharge(getSessions)
  const navigate = useNavigate()
  const { peut } = useDroits()
  const { lignes, total } = volumetrie(ev.donnees)
  const { total: totalSessions } = volumetrie(se.donnees)
  // Les compteurs de verrouillage portent sur la page affichée ; ils ne sont
  // annoncés comme tel que si l'API renvoie effectivement une page partielle.
  const pagine = total > lignes.length
  const verrouillees = lignes.filter((l) => l.composition_verrouillee).length
  const ouvertes = lignes.length - verrouillees
  // La saisie est une autorité backend distincte de la consultation
  // (`evaluations.permissions.peut_saisir_notes` → capacité `notes.gerer`).
  // Un profil « lecture seule » ne doit pas voir d'action de saisie.
  const peutSaisir = peut('notes', 'gerer')
  // Une panne de l'API des sessions ne doit pas masquer les évaluations déjà
  // chargées : elle est signalée dans la tuile, pas en erreur de page.
  // Les deux `reessayer` sont stables (`useCallback` à tableau vide), le
  // rechargement porte donc bien sur l'ENSEMBLE des sources du tableau de bord.
  const reessayerEvaluations = ev.reessayer
  const reessayerSessions = se.reessayer
  const reessayer = useCallback(() => {
    reessayerEvaluations()
    reessayerSessions()
  }, [reessayerEvaluations, reessayerSessions])

  return (
    <Page
      titre="Tableau de bord des évaluations"
      icone="bi-speedometer2"
      sousTitre="Vue synthétique de l'activité évaluative"
      chargement={ev.chargement || se.chargement}
      erreur={ev.erreur}
      reessayer={reessayer}
      actions={(
        <>
          <button
            type="button"
            className="ev-btn ev-btn--ghost"
            onClick={reessayer}
            aria-label="Actualiser le tableau de bord"
          >
            <i className="bi bi-arrow-clockwise" aria-hidden="true" />
            Actualiser
          </button>
          <button
            type="button"
            className="ev-btn ev-btn--primary"
            onClick={() => navigate('/evaluations')}
          >
            Voir les évaluations
          </button>
        </>
      )}
    >
      <div className="ev-stats">
        <Tuile icone="bi-clipboard-check" label="Évaluations" valeur={total} />
        <Tuile icone="bi-unlock" label="Ouvertes à la saisie" valeur={ouvertes} variante="warn" />
        <Tuile icone="bi-lock" label="Verrouillées" valeur={verrouillees} variante="ok" />
        <Tuile
          icone="bi-calendar3"
          label="Sessions d’évaluation"
          valeur={totalSessions}
          disponible={!se.erreur}
        />
      </div>
      <PanneauActivite
        lignes={lignes}
        total={total}
        pagine={pagine}
        peutSaisir={peutSaisir}
        navigate={navigate}
      />
    </Page>
  )
}

// ── 3. Saisie des notes ─────────────────────────────────────────────────────

export function SaisieNotes() {
  const { id } = useParams()
  const navigate = useNavigate()
  const { showToast } = useToast()
  const { peut } = useDroits()
  const [composantId, setComposantId] = useState('')
  const [valeurs, setValeurs] = useState({})
  const meta = useCharge(async () => {
    // Sans identifiant d'évaluation (route `/evaluations/saisie`), on renvoie
    // seulement le registre : l'utilisateur choisit une évaluation à saisir.
    if (!id) return { evaluation: null, composants: [], participants: [], evaluations: await getEvaluations() }
    const [evaluation, composants, participants] = await Promise.all([
      getEvaluation(id), getComposants(id), getParticipants(id),
    ])
    // `getParticipants` renvoie déjà une liste normalisée (l'API n'a pas
    // paginé cette vue) : lire `.results` ici renvoyait toujours [].
    return { evaluation, composants, participants, evaluations: null }
  }, [id])

  // La saisie des notes est une autorité backend distincte de la consultation
  // (`evaluations.permissions.peut_saisir_notes` → capacité `notes.gerer`).
  const peutSaisir = peut('notes', 'gerer')
  const verrouille = Boolean(meta.donnees?.evaluation?.composition_verrouillee)
  const evaluation = meta.donnees?.evaluation ?? null
  const composants = meta.donnees?.composants ?? []
  const participants = meta.donnees?.participants ?? []
  const composantChoisi = composants.find((c) => String(c.id) === String(composantId))
  // `count` porte l'effectif TOTAL du registre, pas la seule page affichée.
  const { lignes: evaluations, total: nbEvaluations } = volumetrie(meta.donnees?.evaluations)

  // Changer de COMPOSANTE change la colonne notée : les valeurs déjà saisies
  // appartiennent à l'ancienne et ne doivent jamais lui être ré-écrites.
  const changerComposant = useCallback((nouvelle) => {
    setComposantId(nouvelle)
    setValeurs({})
  }, [])

  const enregistrer = async () => {
    if (!composantId) { showToast('Sélectionnez une composante.', 'error'); return }
    // Contrat réel (EvaluationGradeSaisieSerializer, many=True) : liste de
    // lignes { evaluation_participant_id, valeur }.
    //
    // Seules les lignes **explicitement saisies** sont envoyées : un champ
    // laissé vide ne doit pas effacer une note déjà enregistrée
    // (l'API accepte `null`, l'envoyer écraserait la note en base).
    const payload = (meta.donnees?.participants ?? [])
      .filter((p) => {
        const v = valeurs[p.id]
        return v !== undefined && v !== null && v !== ''
      })
      .map((p) => ({ evaluation_participant_id: p.id, valeur: Number(valeurs[p.id]) }))
    if (payload.length === 0) {
      showToast('Aucune note saisie à enregistrer.', 'error')
      return
    }
    try {
      await saisirNotes(composantId, payload)
      showToast('Notes enregistrées.', 'success')
      setValeurs({})
    } catch (e) {
      showToast(
        e.response?.status === 403 ? 'Accès refusé.'
          : e.response?.data?.detail || 'Erreur lors de la saisie.',
        'error',
      )
    }
  }

  return (
    <Page
      // E1.3 §2 : cette page s'appelle « Saisie des notes », jamais « Évaluations ».
      titre="Saisie des notes"
      icone="bi-pencil-square"
      sousTitre="Saisie et enregistrement des notes des participants"
      chargement={meta.chargement}
      erreur={meta.erreur}
      reessayer={meta.reessayer}
      skeleton={8}
      actions={evaluation ? <BandeauVerrou verrouille={verrouille} /> : null}
    >
      <button
        type="button"
        className="ev-retour"
        onClick={() => navigate('/evaluations')}
      >
        <i className="bi bi-arrow-left" aria-hidden="true" />
        Retour aux évaluations
      </button>

      {!evaluation ? (
        <ChoixEvaluation evaluations={evaluations} total={nbEvaluations} peutSaisir={peutSaisir} />
      ) : (
        <SaisieContextuelle
          evaluation={evaluation}
          verrouille={verrouille}
          peutSaisir={peutSaisir}
          composants={composants}
          participants={participants}
          composantChoisi={composantChoisi}
          composantId={composantId}
          setComposantId={changerComposant}
          valeurs={valeurs}
          setValeurs={setValeurs}
          enregistrer={enregistrer}
        />
      )}
    </Page>
  )
}

/** En-tête contextualisé + tableau : une évaluation identifiée en cours de saisie. */
function SaisieContextuelle({
  evaluation, verrouille, peutSaisir, composants, participants, composantChoisi,
  composantId, setComposantId, valeurs, setValeurs, enregistrer,
}) {
  // Sans la capacité `notes.gerer`, l'API refuse toute écriture (403) : le
  // formulaire est affiché en lecture seule plutôt que de laisser saisir pour
  // obtenir un refus à l'enregistrement.
  const lectureSeule = verrouille || !peutSaisir
  return (
    <>
      <div className="ev-contexte">
        <div className="ev-contexte-item">
          <span className="ev-contexte-label">ECUE</span>
          <span className="ev-contexte-valeur">{affichage(evaluation.ecue_code)}</span>
        </div>
        <div className="ev-contexte-item">
          <span className="ev-contexte-label">Type</span>
          <span className="ev-contexte-valeur">{affichage(evaluation.type_code)}</span>
        </div>
        <div className="ev-contexte-item">
          <span className="ev-contexte-label">Date prévue</span>
          <span className="ev-contexte-valeur">{affichage(evaluation.date_prevue)}</span>
        </div>
        <div className="ev-contexte-item">
          <span className="ev-contexte-label">Libellé</span>
          <span className="ev-contexte-valeur">{affichage(evaluation.libelle)}</span>
        </div>
      </div>

      {verrouille && (
        <div className="ev-erreur" role="status">
          <span className="ev-erreur-titre">
            <i className="bi bi-lock-fill" aria-hidden="true" />
            Évaluation verrouillée — lecture seule
          </span>
          <span className="ev-erreur-detail">
            Les notes de cette composition ne peuvent plus être modifiées.
          </span>
        </div>
      )}

      {!verrouille && !peutSaisir && (
        <div className="ev-erreur" role="status">
          <span className="ev-erreur-titre">
            <i className="bi bi-shield-lock" aria-hidden="true" />
            Saisie non autorisée — consultation seule
          </span>
          <span className="ev-erreur-detail">
            Vous ne disposez pas du droit de saisir les notes. Les valeurs existantes restent visibles.
          </span>
        </div>
      )}

      <div className="card px-panel">
        <div className="px-panel-head">
          <div className="px-panel-headtext">
            <h2 className="px-panel-title">
              <i className="bi bi-list-check" aria-hidden="true" />
              Notes des participants
            </h2>
            <p className="px-panel-sub">
              {lectureSeule
                ? 'Sélectionnez une composante pour consulter les valeurs enregistrées.'
                : 'Choisissez une composante puis saisissez les valeurs.'}
            </p>
          </div>
        </div>

        <div className="px-toolbar-body">
          <label className="px-field" htmlFor="composant">
            <span className="px-field-label">Composante</span>
            <select
              id="composant"
              className="px-input px-select"
              value={composantId}
              disabled={composants.length === 0}
              onChange={(e) => setComposantId(e.target.value)}
            >
              <option value="">— Choisir —</option>
              {composants.map((c) => (
                <option key={c.id} value={c.id}>
                  {affichage(c.code)} — barème {affichage(c.bareme)}
                </option>
              ))}
            </select>
          </label>
          {/* Le sélecteur reste actif en lecture seule : consulter les valeurs
              enregistrées d'une composante n'exige aucun droit d'écriture. */}
          <div className="px-toolbar-actions">
            {lectureSeule ? null : (
              <button
                type="button"
                className="ev-btn ev-btn--primary"
                disabled={!composantId}
                onClick={enregistrer}
              >
                <i className="bi bi-check2-circle" aria-hidden="true" />
                Enregistrer les notes
              </button>
            )}
          </div>
        </div>

        <div className="card-body-flush">
          {composants.length === 0 ? (
            <EtatVide
              icone="bi-card-list"
              titre="Aucune composante"
              message="Cette évaluation ne comporte aucune composante de notation."
            />
          ) : participants.length === 0 ? (
            <EtatVide
              icone="bi-people"
              titre="Aucun participant"
              message="Aucun participant n’est inscrit à cette évaluation."
            />
          ) : (
            <TableauSaisie
              participants={participants}
              valeurs={valeurs}
              setValeurs={setValeurs}
              lectureSeule={lectureSeule}
              bareme={composantChoisi?.bareme}
            />
          )}
        </div>
      </div>
    </>
  )
}

/** Libellé du bouton d'ouverture d'une composition : saisir ou consulter. */
function saisirableLibelle(saisissable) {
  return saisissable ? 'Saisir les notes' : 'Consulter'
}

/** Sélecteur d'évaluation : écran d'entrée de `/evaluations/saisie`. */
function ChoixEvaluation({ evaluations, total, peutSaisir }) {
  const navigate = useNavigate()
  if (evaluations.length === 0) {
    return (
      <div className="card px-panel">
        <EtatVide
          icone="bi-clipboard-x"
          titre="Aucune évaluation disponible"
          /* Le registre ne propose AUCUNE création d'évaluation (l'API
             `evaluations_create` n'est pas exposée dans l'IHM) : inviter à
             « créer depuis le registre » renvoyait vers une action inexistante.
             La composition est créée par le service académique. */
          message="Les compositions sont créées par le service académique. Dès qu’une évaluation est rattachée à vos affectations pédagogiques, elle apparaîtra ici."
          action={(
            <button
              type="button"
              className="ev-btn ev-btn--primary"
              onClick={() => navigate('/evaluations')}
            >
              <i className="bi bi-clipboard-check" aria-hidden="true" />
              Voir le registre
            </button>
          )}
        />
      </div>
    )
  }
  return (
    <div className="card px-panel">
      <div className="px-panel-head">
        <div className="px-panel-headtext">
          <h2 className="px-panel-title">
            <i className="bi bi-journal-text" aria-hidden="true" />
            Choisir une évaluation
          </h2>
          <p className="px-panel-sub">
            {peutSaisir
              ? 'Sélectionnez l’évaluation dont vous souhaitez saisir les notes.'
              : 'Sélectionnez une évaluation pour consulter les notes enregistrées.'}
          </p>
        </div>
        <div className="px-panel-tools">
          <span className="px-count-pill">
            {total} évaluation{total > 1 ? 's' : ''}
          </span>
        </div>
      </div>
      <div className="card-body">
        <div className="ev-cartes">
          {evaluations.map((e) => {
            const estVerrouillee = Boolean(e.composition_verrouillee)
            const saisissable = peutSaisir && !estVerrouillee
            return (
              <div className="ev-carte" key={e.id}>
                <span className="ev-carte-ecue">{affichage(e.ecue_code)}</span>
                <div className="ev-carte-meta">
                  <span>{affichage(e.libelle)}</span>
                  <span>Type : {affichage(e.type_code)}</span>
                  <span>Date prévue : {affichage(e.date_prevue)}</span>
                </div>
                <div className="ev-carte-pied">
                  <BandeauVerrou verrouille={estVerrouillee} />
                  {/* Une composition verrouillée s'ouvre en lecture seule :
                      le libellé « Saisir » y serait faux. */}
                  <button
                    type="button"
                    className={saisissable ? 'ev-btn ev-btn--primary' : 'ev-btn ev-btn--ghost'}
                    onClick={() => navigate(`/evaluations/saisie/${e.id}`)}
                    aria-label={saisissable
                      ? `Saisir les notes de ${affichage(e.libelle)}`
                      : `Consulter les notes de ${affichage(e.libelle)}`}
                  >
                    {saisirableLibelle(saisissable)}
                  </button>
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}

/**
 * Tableau de saisie : Matricule | Participant | Note | Absence | Statut.
 *
 * - la valeur `0` est une note réelle : elle est mise en évidence, jamais
 *   assimilée à un champ vide ;
 * - un champ vide ne produit AUCUNE ligne envoyée, donc n'efface jamais une
 *   note déjà enregistrée ;
 * - une absence est un statut métier, jamais une conversion en zéro (D2).
 */
function TableauSaisie({ participants, valeurs, setValeurs, lectureSeule, bareme }) {
  return (
    <div className="ev-table-scroll">
      <table className="table px-table">
        <caption className="visually-hidden">Saisie des notes par participant</caption>
        <thead>
          <tr>
            <th scope="col">Matricule</th>
            <th scope="col">Participant</th>
            <th scope="col">Note</th>
            <th scope="col">Absence</th>
            <th scope="col">Statut</th>
          </tr>
        </thead>
        <tbody>
          {participants.map((p) => {
            const brut = valeurs[p.id] ?? ''
            const estZero = brut !== '' && Number(brut) === 0
            const absent = String(p.statut_participation ?? '').toUpperCase().includes('ABSEN')
            return (
              <tr key={p.id}>
                <td><span className="ev-note-bareme">{affichage(p.matricule)}</span></td>
                <td style={{ fontWeight: 600 }}>{affichage(p.nom_affiche)}</td>
                <td>
                  {lectureSeule ? (
                    <span className="px-dash">—</span>
                  ) : (
                    <span className="ev-note-cellule">
                      <input
                        type="number"
                        step="0.01"
                        inputMode="decimal"
                        className={`ev-note-input${estZero ? ' ev-note-zero' : ''}`}
                        aria-label={`Note de ${affichage(p.nom_affiche)}`}
                        value={brut}
                        onChange={(e) => setValeurs({ ...valeurs, [p.id]: e.target.value })}
                      />
                      {bareme !== undefined && bareme !== null && (
                        <span className="ev-note-bareme">/ {affichage(bareme)}</span>
                      )}
                    </span>
                  )}
                </td>
                <td>
                  {absent
                    ? <span className="ev-badge ev-badge--danger">Absent</span>
                    : <span className="px-dash">—</span>}
                </td>
                <td><BadgeEtat valeur={p.statut_participation} /></td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

// ── 4. Contrôle des notes ───────────────────────────────────────────────────

export function ControleNotes() {
  const navigate = useNavigate()
  const { peut } = useDroits()
  const { donnees, chargement, erreur, reessayer } = useCharge(getEvaluations)
  const [filtre, setFiltre] = useState('a_controler')
  const { lignes, total } = volumetrie(donnees)
  // Ouvrir la saisie d'une composition relève de la capacité `notes.gerer`.
  const peutSaisir = peut('notes', 'gerer')

  // Filtres strictement dérivée du champ réel `composition_verrouillee`.
  const filtrees = lignes.filter((l) => {
    if (filtre === 'verrouillees') return Boolean(l.composition_verrouillee)
    if (filtre === 'a_controler') return !l.composition_verrouillee
    return true
  })

  const segments = [
    ['toutes', 'Toutes'],
    ['a_controler', 'À contrôler'],
    ['verrouillees', 'Verrouillées'],
  ]

  return (
    <Page
      titre="Contrôle des notes"
      icone="bi-shield-check"
      sousTitre="Vérification des évaluations avant validation"
      chargement={chargement}
      erreur={erreur}
      reessayer={reessayer}
      actions={<span className="px-count-pill px-count-pill--muted">{total}</span>}
    >
      <div className="card px-panel">
        <div className="px-panel-head">
          <div className="px-panel-headtext">
            <h2 className="px-panel-title">
              <i className="bi bi-clipboard2-check" aria-hidden="true" />
              Contrôle institutionnel
            </h2>
            <p className="px-panel-sub">
              Le contrôle porte sur les compositions de votre périmètre.
            </p>
          </div>
          <div className="px-panel-tools">
            <div className="ev-segments" role="group" aria-label="Filtrer les évaluations">
              {segments.map(([cle, libelle]) => (
                <button
                  key={cle}
                  type="button"
                  className="ev-segment"
                  aria-pressed={filtre === cle}
                  onClick={() => setFiltre(cle)}
                >
                  {libelle}
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="card-body">
          {filtrees.length === 0 ? (
            <EtatVide
              icone="bi-check2-circle"
              titre="Rien à contrôler"
              message={
                filtre === 'verrouillees'
                  ? 'Aucune composition verrouillée dans votre périmètre.'
                  : 'Toutes les compositions de votre périmètre sont verrouillées.'
              }
            />
          ) : (
            <div className="ev-cartes">
              {filtrees.map((l) => (
                <div className="ev-carte" key={l.id}>
                  <span className="ev-carte-ecue">{affichage(l.ecue_code)}</span>
                  <div className="ev-carte-meta">
                    <span>{affichage(l.libelle)}</span>
                    <span>Type : {affichage(l.type_code)}</span>
                    <span>Date prévue : {affichage(l.date_prevue)}</span>
                    <span>État : {affichage(l.statut)}</span>
                  </div>
                  <div className="ev-carte-pied">
                    <BandeauVerrou verrouille={Boolean(l.composition_verrouillee)} />
                    <button
                      type="button"
                      className="ev-btn ev-btn--ghost"
                      onClick={() => navigate(`/evaluations/saisie/${l.id}`)}
                      aria-label={`Consulter ${affichage(l.libelle)}`}
                    >
                      Consulter
                    </button>
                    {/* Écrire dans la composition est réservé à `notes.gerer`,
                        et impossible une fois la composition verrouillée
                        (l'écran de saisie passe alors en lecture seule). */}
                    {peutSaisir && !l.composition_verrouillee && (
                      <button
                        type="button"
                        className="ev-btn ev-btn--primary"
                        onClick={() => navigate(`/evaluations/saisie/${l.id}`)}
                        aria-label={`Saisir les notes de ${affichage(l.libelle)}`}
                      >
                        Saisir les notes
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </Page>
  )
}

// ── 6. Résultats ────────────────────────────────────────────────────────────

/**
 * Panneau du passage de niveau.
 *
 * Le moteur backend est l'unique source : éligibilité, ECTS, semestres et
 * décision de jury sont AFFICHÉS tels que renvoyés. Une donnée manquante
 * reste « indeterminate », jamais un 0 ni une validation supposée (D6).
 */
function PanneauPassage({ etat }) {
  if (etat.chargement) {
    return (
      <EtatVide
        icone="bi-hourglass"
        titre="Chargement…"
        message="Calcul du passage de niveau."
      />
    )
  }
  if (etat.erreur) {
    return (
      <PanneauErreur
        erreur={etat.erreur}
        onReessayer={etat.erreur ? etat.reessayer : null}
      />
    )
  }
  const d = etat.donnees
  if (!d) return null
  const decision = d.decision_jury ?? null
  return (
    <div className="card-body">
      <dl className="row mb-0">
        <dt className="col-sm-3">Éligibilité</dt>
        <dd className="col-sm-9">
          <BadgeEtat valeur={d.eligibilite} />
        </dd>
        <dt className="col-sm-3">Niveau visé</dt>
        <dd className="col-sm-9">{affichage(d.niveau_cible)}</dd>
        <dt className="col-sm-3">ECTS</dt>
        <dd className="col-sm-9">
          {affichage(d.credits_acquis)} / {affichage(d.credits_requis)}
        </dd>
        <dt className="col-sm-3">Décision du jury</dt>
        <dd className="col-sm-9">
          {decision == null
            ? <span className="px-dash">Aucune décision enregistrée</span>
            : <BadgeEtat valeur={decision.valeur} />}
        </dd>
        <dt className="col-sm-3">Motif</dt>
        <dd className="col-sm-9">{affichage(d.code)} — {affichage(d.justification)}</dd>
      </dl>

      <h3 className="px-panel-title mt-4">Semestres du niveau</h3>
      {(d.semestres ?? []).length === 0 ? (
        <EtatVide
          icone="bi-dash"
          titre="Aucun semestre"
          message="Aucun résultat de semestre pour ce niveau : le passage ne peut pas être conclu."
        />
      ) : (
        <div className="ev-table-scroll">
          <table className="table px-table">
            <thead>
              <tr>
                <th scope="col">Semestre</th>
                <th scope="col">Crédits acquis</th>
                <th scope="col">Crédits attendus</th>
                <th scope="col">Statut</th>
              </tr>
            </thead>
            <tbody>
              {d.semestres.map((s, i) => (
                <tr key={`${s.semestre}-${i}`}>
                  <td>{affichage(s.semestre)}</td>
                  <td>{affichage(s.credits_acquis)}</td>
                  <td>{affichage(s.credits_attendus)}</td>
                  <td><BadgeEtat valeur={s.statut} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

export function ResultatsEvaluations() {
  const [niveau, setNiveau] = useState('ecue')
  const [passage, setPassage] = useState(null)
  const { donnees, chargement, erreur, reessayer } = useCharge(
    () => (niveau === 'ecue' ? getResultatsEcue()
      : niveau === 'ue' ? getResultatsUe() : getResultatsSemestre()),
    [niveau],
  )
  // Passage de niveau : calcul backend, jamais recalculé ici (D10).
  const passageCharge = useCharge(
    () => (passage == null
      ? Promise.resolve(null)
      : getPassageNiveau({
        inscription_id: passage.inscription_id,
        session_id: passage.session_id,
      })),
    [passage],
  )
  const lignes = donnees?.results ?? []
  const segments = [['ecue', 'ECUE'], ['ue', 'UE'], ['semestre', 'Semestre']]
  return (
    <Page
      titre="Résultats"
      icone="bi-graph-up-arrow"
      sousTitre="Consultation des résultats calculés par le service académique"
      chargement={chargement}
      erreur={erreur}
      reessayer={reessayer}
      actions={<span className="px-count-pill px-count-pill--muted">{lignes.length}</span>}
    >
      <div className="card px-panel">
        <div className="px-panel-head">
          <div className="px-panel-headtext">
            <h2 className="px-panel-title">
              <i className="bi bi-award" aria-hidden="true" />
              Consultation
            </h2>
            <p className="px-panel-sub">
              Les valeurs affichées proviennent exclusivement du backend.
            </p>
          </div>
          <div className="px-panel-tools">
            <div className="ev-segments" role="group" aria-label="Niveau de résultat">
              {segments.map(([cle, libelle]) => (
                <button
                  key={cle}
                  type="button"
                  className="ev-segment"
                  aria-pressed={niveau === cle}
                  onClick={() => setNiveau(cle)}
                >
                  {libelle}
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="card-body-flush">
          {lignes.length === 0 ? (
            <EtatVide
              icone="bi-clipboard-x"
              titre="Aucun résultat disponible"
              message="Les résultats apparaîtront ici dès que le service académique les publiera."
            />
          ) : (
            <div className="ev-table-scroll">
              {/* Colonnes dérivées du payload réel : aucun champ n'est supposé. */}
              <table className="table px-table">
                <caption className="visually-hidden">
                  Résultats {segments.find(([c]) => c === niveau)?.[1]}
                </caption>
                <thead>
                  <tr>
                    {Object.keys(lignes[0] ?? {}).map((c) => (
                      <th scope="col" key={c}>{c.replace(/_/g, ' ')}</th>
                    ))}
                    {niveau === 'semestre' && <th scope="col">Passage</th>}
                  </tr>
                </thead>
                <tbody>
                  {lignes.map((l, i) => (
                    <tr key={l.id ?? i}>
                      {Object.keys(lignes[0] ?? {}).map((c) => (
                        <td key={c} className={typeof l[c] === 'number' ? 'px-num' : undefined}>
                          {affichage(l[c])}
                        </td>
                      ))}
                      {niveau === 'semestre' && (
                        <td className="text-end">
                          <button
                            type="button"
                            className="btn btn-sm btn-outline-secondary"
                            onClick={() => setPassage({
                              inscription_id: l.inscription,
                              session_id: l.session,
                              libelle: `${l.semestre} — ${l.statut_semestre}`,
                            })}
                            data-testid={`passage-${l.inscription}-${l.session}`}
                          >
                            Passage de niveau
                          </button>
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {passage != null && (
        <div className="card px-panel" data-testid="passage-detail">
          <div className="px-panel-head">
            <div className="px-panel-headtext">
              <h2 className="px-panel-title">
                <i className="bi bi-signpost-split" aria-hidden="true" />
                Passage de niveau — {affichage(passage.libelle)}
              </h2>
              <p className="px-panel-sub">
                Calcul technique fourni par le moteur LMD ; la décision officielle
                reste celle du jury.
              </p>
            </div>
          </div>
          <div className="card-body-flush">
            <PanneauPassage
              etat={passageCharge}
              reessayer={passageCharge.reessayer}
            />
          </div>
        </div>
      )}
    </Page>
  )
}


export function Deliberations() {
  const [selection, setSelection] = useState(null)
  const sessions = useCharge(getJurySessions)
  const charges = useCharge(
    () => (selection == null
      ? Promise.resolve(null)
      : Promise.all([getJuryAnomalies(selection), getJuryStatistiques(selection)])),
    [selection],
  )
  const lignes = sessions.donnees?.results ?? []
  const [anomalies, stats] = charges.donnees ?? []

  return (
    <Page
      titre="Délibérations"
      icone="bi-people-fill"
      sousTitre="Sessions de jury, décisions du moteur LMD/ECTS et anomalies"
      chargement={sessions.chargement}
      erreur={sessions.erreur}
      reessayer={sessions.reessayer}
      actions={<span className="px-count-pill px-count-pill--muted">{lignes.length}</span>}
    >
      <div className="card px-panel">
        <div className="px-panel-head">
          <div className="px-panel-headtext">
            <h2 className="px-panel-title">
              <i className="bi bi-mortarboard-fill" aria-hidden="true" />
              Sessions de délibération
            </h2>
            <p className="px-panel-sub">
              La décision académique provient du moteur LMD/ECTS (module Jurys).
            </p>
          </div>
        </div>
        <div className="card-body-flush">
          {lignes.length === 0 ? (
            <EtatVide
              icone="bi-clipboard-x"
              titre="Aucune session de jury"
              message="Les sessions de délibération apparaîtront ici dès leur création."
            />
          ) : (
            <div className="ev-table-scroll">
              <table className="table px-table">
                <caption className="visually-hidden">Sessions de jury</caption>
                <thead>
                  <tr>
                    <th scope="col">Libellé</th>
                    <th scope="col">Statut</th>
                    <th scope="col">Type</th>
                    <th scope="col" />
                  </tr>
                </thead>
                <tbody>
                  {lignes.map((l) => (
                    <tr key={l.id}>
                      <td>{affichage(l.libelle)}</td>
                      <td>{affichage(l.statut)}</td>
                      <td>{affichage(l.type_session)}</td>
                      <td className="text-end">
                        <button
                          type="button"
                          className="btn btn-sm btn-outline-secondary"
                          onClick={() => setSelection(l.id)}
                          data-testid={`deliberation-${l.id}`}
                        >
                          Consulter
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {selection != null && (
        <div className="card px-panel" data-testid="deliberation-detail">
          <div className="px-panel-head">
            <div className="px-panel-headtext">
              <h2 className="px-panel-title">
                <i className="bi bi-clipboard-check" aria-hidden="true" />
                Résultats de la session
              </h2>
              <p className="px-panel-sub">Statistiques et anomalies calculées par le serveur.</p>
            </div>
          </div>
          <div className="card-body-flush">
            {charges.chargement || !stats ? (
              <EtatVide icone="bi-hourglass" titre="Chargement…" message="Lecture des données de délibération." />
            ) : (
              <div className="card-body">
                <ul className="list-group list-group-flush">
                  <li className="list-group-item d-flex justify-content-between">
                    <span>Participants</span><strong>{stats.participants}</strong>
                  </li>
                  <li className="list-group-item d-flex justify-content-between">
                    <span>Admis</span><strong>{stats.admis}</strong>
                  </li>
                  <li className="list-group-item d-flex justify-content-between">
                    <span>Ajournés</span><strong>{stats.ajournes}</strong>
                  </li>
                  <li className="list-group-item d-flex justify-content-between">
                    <span>Anomalies</span><strong>{stats.anomalies?.total ?? 0}</strong>
                  </li>
                </ul>
                {(anomalies?.anomalies?.length ?? 0) > 0 && (
                  <ul className="list-group list-group-flush mt-3">
                    {anomalies.anomalies.map((a, i) => (
                      <li key={`${a.code}-${a.participant_id ?? i}`} className="list-group-item">
                        <span className={`badge me-2 ${a.bloquante ? 'bg-danger' : 'bg-warning text-dark'}`}>
                          {affichage(a.gravite)}
                        </span>
                        {affichage(a.message)}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </Page>
  )
}

/**
 * Détail d'un relevé archivé.
 *
 * Toutes les valeurs (moyennes, crédits, décision) sont AFFICHÉES telles que
 * le backend les a calculées : ce composant ne recalcule rien. Une note
 * `null` (absence, composante non notée) reste « Non renseigné », jamais
 * un 0 (D2/D6).
 */
function DetailReleve({ contenu, decision }) {
  const semestre = contenu?.semestres ?? []
  const ues = contenu?.unites_enseignement ?? []
  const ecues = ues.flatMap((u) =>
    (u.ecues ?? []).map((e) => ({ ...e, ue_code: u.ue_code })))

  return (
    <div className="card-body">
      <dl className="row mb-0">
        <dt className="col-sm-3">Participant</dt>
        <dd className="col-sm-9">
          {affichage(contenu?.participant?.nom_complet)}
          {' '}
          <span className="ev-note-bareme">
            ({affichage(contenu?.participant?.matricule)})
          </span>
        </dd>
        <dt className="col-sm-3">Niveau</dt>
        <dd className="col-sm-9">{affichage(contenu?.niveau)}</dd>
        <dt className="col-sm-3">Formation</dt>
        <dd className="col-sm-9">{affichage(contenu?.formation)}</dd>
        <dt className="col-sm-3">Décision</dt>
        <dd className="col-sm-9">
          <BadgeEtat valeur={decision ?? 'EN_ATTENTE'} />
        </dd>
      </dl>

      <h3 className="px-panel-title mt-4">Semestres</h3>
      {semestre.length === 0 ? (
        <EtatVide
          icone="bi-dash"
          titre="Aucun semestre"
          message="Aucun résultat de semestre archivé."
        />
      ) : (
        <div className="ev-table-scroll">
          <table className="table px-table">
            <thead>
              <tr>
                <th scope="col">Semestre</th>
                <th scope="col">Niveau</th>
                <th scope="col">Crédits</th>
                <th scope="col">Statut</th>
              </tr>
            </thead>
            <tbody>
              {semestre.map((s, i) => (
                <tr key={`${s.semestre}-${i}`}>
                  <td>{affichage(s.semestre)}</td>
                  <td>{affichage(s.niveau)}</td>
                  <td>{affichage(s.credits_acquis)} / {affichage(s.credits_attendus)}</td>
                  <td><BadgeEtat valeur={s.statut} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <h3 className="px-panel-title mt-4">Unités d'enseignement</h3>
      {ues.length === 0 ? (
        <EtatVide
          icone="bi-dash"
          titre="Aucune UE"
          message="Aucun résultat d'unité d'enseignement archivé."
        />
      ) : (
        <div className="ev-table-scroll">
          <table className="table px-table">
            <thead>
              <tr>
                <th scope="col">UE</th>
                <th scope="col">Intitulé</th>
                <th scope="col">Crédits</th>
                <th scope="col">Moyenne</th>
                <th scope="col">Statut</th>
              </tr>
            </thead>
            <tbody>
              {ues.map((u, i) => (
                <tr key={`${u.ue_code}-${i}`}>
                  <td><span className="ev-note-bareme">{affichage(u.ue_code)}</span></td>
                  <td>{affichage(u.ue_libelle)}</td>
                  <td>{affichage(u.credits_ue)}</td>
                  <td>{affichage(u.moyenne)}</td>
                  <td><BadgeEtat valeur={u.statut} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {ecues.length > 0 && (
        <>
          <h3 className="px-panel-title mt-4">ECUE</h3>
          <div className="ev-table-scroll">
            <table className="table px-table">
              <thead>
                <tr>
                  <th scope="col">ECUE</th>
                  <th scope="col">Intitulé</th>
                  <th scope="col">Note</th>
                  <th scope="col">Bareme</th>
                  <th scope="col">Statut</th>
                </tr>
              </thead>
              <tbody>
                {ecues.map((e, i) => (
                  <tr key={`${e.ue_code}-${e.ecue_code}-${i}`}>
                    <td><span className="ev-note-bareme">{affichage(e.ecue_code)}</span></td>
                    <td>{affichage(e.ecue_libelle)}</td>
                    <td>{affichage(e.note)}</td>
                    <td>{affichage(e.bareme)}</td>
                    <td><BadgeEtat valeur={e.statut} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  )
}

export function Reveles() {
  const [selection, setSelection] = useState(null)
  const liste = useCharge(() => getReleves(), [])
  const detail = useCharge(
    () => (selection == null ? Promise.resolve(null) : getReleve(selection)),
    [selection],
  )
  const lignes = liste.donnees?.results ?? []
  const releve = detail.donnees
  const contenu = releve?.contenu ?? null
  const decision = releve?.decision_valeur ?? null

  return (
    <Page
      titre="Relevés de notes"
      icone="bi-file-earmark-text"
      sousTitre="Relevés versionnés, produits par le service académique"
      chargement={liste.chargement}
      erreur={liste.erreur}
      reessayer={liste.reessayer}
      actions={<span className="px-count-pill px-count-pill--muted">{lignes.length}</span>}
    >
      <div className="card px-panel">
        <div className="px-panel-head">
          <div className="px-panel-headtext">
            <h2 className="px-panel-title">
              <i className="bi bi-journals" aria-hidden="true" />
              Relevés disponibles
            </h2>
            <p className="px-panel-sub">
              Chaque relevé est versionné et horodaté par une empreinte SHA-256.
            </p>
          </div>
        </div>
        <div className="card-body-flush">
          {lignes.length === 0 ? (
            <EtatVide
              icone="bi-file-earmark-text"
              titre="Aucun relevé"
              message="Les relevés apparaîtront ici dès leur génération par la scolarité."
            />
          ) : (
            <div className="ev-table-scroll">
              <table className="table px-table">
                <caption className="visually-hidden">Relevés de notes</caption>
                <thead>
                  <tr>
                    <th scope="col">Matricule</th>
                    <th scope="col">Version</th>
                    <th scope="col">Décision</th>
                    <th scope="col">Généré le</th>
                    <th scope="col" />
                  </tr>
                </thead>
                <tbody>
                  {lignes.map((r) => (
                    <tr key={r.id}>
                      <td><span className="ev-note-bareme">{affichage(r.participant_matricule)}</span></td>
                      <td>v{affichage(r.version)}</td>
                      <td><BadgeEtat valeur={r.decision_valeur ?? 'EN_ATTENTE'} /></td>
                      <td>{affichage(r.genere_le)}</td>
                      <td className="text-end">
                        <button
                          type="button"
                          className="btn btn-sm btn-outline-secondary"
                          onClick={() => setSelection(r.id)}
                          data-testid={`releve-${r.id}`}
                        >
                          Consulter
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {selection != null && (
        <div className="card px-panel" data-testid="releve-detail">
          <div className="px-panel-head">
            <div className="px-panel-headtext">
              <h2 className="px-panel-title">
                <i className="bi bi-file-earmark-text" aria-hidden="true" />
                Relevé v{affichage(releve?.version)}
              </h2>
              <p className="px-panel-sub">
                Empreinte {affichage(String(releve?.sha256 ?? '').slice(0, 12))}
              </p>
            </div>
          </div>
          <div className="card-body-flush">
            {detail.chargement || !releve ? (
              <EtatVide icone="bi-hourglass" titre="Chargement…" message="Lecture du relevé archivé." />
            ) : (
              <DetailReleve contenu={contenu} decision={decision} />
            )}
          </div>
        </div>
      )}
    </Page>
  )
}