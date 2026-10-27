import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import api from '@/services/api'
import { useVisibilityPolling } from '@/hooks/useVisibilityPolling'
import '@/styles/dashboardEngine.css'

/**
 * Bloc « Séances en direct » — supervision LMD des séances du jour.
 *
 * Source unique : `GET /api/presences/seances-edt/supervision/`
 * (`presences.seances_supervision`). Une ligne = **une séance** (`edts.
 * AffectationCreneau`) de l'emploi du temps, pas un pointage : le suivi des
 * présences est celui des `Pointage` réellement rattachés à cette séance.
 *
 * Règles d'affichage tenues par ce composant :
 * - le statut (« En cours », « À venir », « Terminée », « Annulée ») vient du
 *   backend, qui le déduit des **horaires planifiés** ; le nombre de pointages
 *   ne l'influence jamais ;
 * - une valeur `null` (effectif inconnu, taux indisponible) s'affiche
 *   « Non disponible », jamais `0` ni `0 %` ;
 * - la console est **consultative** : uniquement des `GET`. Ouvrir, filtrer ou
 *   rafraîchir ne déclenche aucune écriture (pas de QR, pas d'émargement).
 *
 * Le backend n'expose pas de WebSocket/SSE : le « temps réel » est un
 * rafraîchissement périodique explicite (et mis en pause quand l'onglet est
 * masqué), avec l'horodatage de la dernière mise à jour affiché à l'écran.
 */

const API_SUPERVISION = '/presences/seances-edt/supervision'

/** Intervalle de rafraîchissement : 60 s, uniquement onglet visible. */
const PERIODE_RAFRAICHISSEMENT_MS = 60_000

const LIBELLES_STATUT = {
  A_VENIR: 'À venir',
  EN_COURS: 'En cours',
  TERMINEE: 'Terminée',
  ANNULEE: 'Annulée',
}

/** Classe de badge — alignée sur les couleurs de statut du dashboard. */
const CLASSE_STATUT = {
  A_VENIR: 'seance-statut--avenir',
  EN_COURS: 'seance-statut--encours',
  TERMINEE: 'seance-statut--terminee',
  ANNULEE: 'seance-statut--annulee',
}

/**
 * Affichage d'une valeur numérique ou `null`.
 * `null`/undefined → « Non disponible » : on ne fabrique jamais un 0.
 */
function valeurOuIndisponible(valeur, suffixe = '') {
  if (valeur === null || valeur === undefined || Number.isNaN(valeur)) {
    return <span className="seance-vide">Non disponible</span>
  }
  return <>{valeur}{suffixe}</>
}

/** Un libellé métier absent ne devient jamais « undefined ». */
function texteOuIndisponible(valeur) {
  if (valeur === null || valeur === undefined || valeur === '') {
    return <span className="seance-vide">Non renseigné</span>
  }
  return <>{valeur}</>
}

function heure(iso) {
  if (!iso) return <span className="seance-vide">Non renseigné</span>
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return <span className="seance-vide">Non renseigné</span>
  return d.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })
}

function dateDuJour() {
  return new Date().toLocaleDateString('en-CA')
}

/**
 * Requête de supervision. Le rafraîchissement de fond (`silencieux`) ne
 * ré-affiche pas l'écran de chargement : la dernière consultation lisible
 * reste à l'écran pendant la mise à jour.
 */
function useSupervisionSeances({ date, statut, formationId, groupeId, enseignantId }) {
  const [donnees, setDonnees] = useState(null)
  const [chargement, setChargement] = useState(true)
  const [erreur, setErreur] = useState('')
  const [dernierRafraichissement, setDernierRafraichissement] = useState(null)

  const charger = useCallback(async (silencieux = false) => {
    if (!silencieux) setChargement(true)
    setErreur('')
    try {
      const params = new URLSearchParams()
      if (date) params.set('date', date)
      if (statut) params.set('statut', statut)
      if (formationId) params.set('formation_id', formationId)
      if (groupeId) params.set('groupe_id', groupeId)
      if (enseignantId) params.set('enseignant_id', enseignantId)
      const reponse = await api.get(`${API_SUPERVISION}/?${params.toString()}`)
      setDonnees(reponse.data)
      setDernierRafraichissement(new Date())
    } catch (err) {
      const detail = err?.response?.data?.detail
      setErreur(detail || 'Impossible de charger les séances du jour.')
    } finally {
      if (!silencieux) setChargement(false)
    }
  }, [date, statut, formationId, groupeId, enseignantId])

  useEffect(() => { charger(false) }, [charger])

  // « Temps réel » honnête : pas de WebSocket/SSE côté INJS, donc un
  // rafraîchissement périodique, suspendu quand l'onglet n'est pas visible.
  useVisibilityPolling(charger, PERIODE_RAFRAICHISSEMENT_MS, true)

  return { donnees, chargement, erreur, dernierRafraichissement, recharger: charger }
}

/** Résumé de pilotage : uniquement des compteurs réellement connus. */
function ResumeSeances({ resume, dernierRafraichissement, onRafraichir, rafraichissementEnCours }) {
  const cartes = [
    { cle: 'seances_en_cours', label: 'Séances en cours', icone: 'bi-broadcast', classe: 'seance-kpi--encours' },
    { cle: 'enseignants_actifs', label: 'Enseignants actifs', icone: 'bi-person-workspace', classe: 'seance-kpi--enseignant' },
    { cle: 'salles_occupees', label: 'Salles occupées', icone: 'bi-door-open', classe: 'seance-kpi--salle' },
    { cle: 'participants_presents', label: 'Participants présents', icone: 'bi-people', classe: 'seance-kpi--present' },
    { cle: 'anomalies', label: 'Anomalies (effectif)', icone: 'bi-exclamation-triangle', classe: 'seance-kpi--anomalie' },
  ]
  return (
    <div className="glass-panel seance-resume">
      <div className="seance-resume__entete">
        <div>
          <h3 className="seance-resume__titre">Résumé de la journée</h3>
          <p className="seance-resume__precision">
            {dernierRafraichissement
              ? `Dernière mise à jour : ${dernierRafraichissement.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}`
              : 'Aucune mise à jour effectuée.'}
          </p>
        </div>
        <button
          type="button"
          className="btn-premium-glass"
          onClick={() => onRafraichir(false)}
          disabled={rafraichissementEnCours}
        >
          <i className="bi bi-arrow-repeat" /> Actualiser
        </button>
      </div>
      <div className="seance-kpi-row">
        {cartes.map((carte) => (
          <div key={carte.cle} className={`seance-kpi ${carte.classe}`}>
            <span className="seance-kpi__icone"><i className={`bi ${carte.icone}`} /></span>
            <span className="seance-kpi__valeur">{valeurOuIndisponible(resume?.[carte.cle])}</span>
            <span className="seance-kpi__label">{carte.label}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

/** Une ligne de présence : libellé + compte réel. */
function CompteurPresence({ label, valeur, variante = '' }) {
  return (
    <div className={`seance-compteur ${variante}`}>
      <span className="seance-compteur__valeur">{valeur}</span>
      <span className="seance-compteur__label">{label}</span>
    </div>
  )
}

/**
 * Fiche d'une séance : statut, enseignement (ECUE/UE), public, enseignant,
 * salle, horaire, puis le suivi des présences rattachées.
 */
function CarteSeance({ seance }) {
  const presences = seance.presences || {}
  const taux = seance.taux_presence
  const sources = []
  if (presences.source_qr > 0) sources.push(`QR (${presences.source_qr})`)
  if (presences.source_manuelle > 0) sources.push(`Manuelle (${presences.source_manuelle})`)

  return (
    <article className="glass-panel seance-carte" data-testid={`seance-${seance.id}`}>
      <header className="seance-carte__entete">
        <span className={`seance-statut ${CLASSE_STATUT[seance.statut] || ''}`}>
          {LIBELLES_STATUT[seance.statut] || seance.statut}
        </span>
        <h4 className="seance-carte__titre">
          {seance.ecue_code
            ? <>{seance.ecue_code} — {texteOuIndisponible(seance.ecue_libelle)}</>
            : texteOuIndisponible(seance.intitule)}
        </h4>
        {seance.ue_code && (
          <p className="seance-carte__ue">UE {seance.ue_code} — {seance.ue_libelle}</p>
        )}
        {!seance.affectation_pedagogique_id && (
          <p className="seance-carte__alerte">
            <i className="bi bi-info-circle" /> Séance non rattachée à une affectation
            pédagogique : ECUE et UE non renseignés.
          </p>
        )}
      </header>

      <dl className="seance-carte__meta">
        <div><dt>Formation</dt><dd>{texteOuIndisponible(seance.formation_libelle)}</dd></div>
        <div><dt>Parcours</dt><dd>{texteOuIndisponible(seance.parcours_libelle)}</dd></div>
        <div><dt>Groupe</dt><dd>{texteOuIndisponible(seance.groupe_libelle)}</dd></div>
        <div><dt>Enseignant</dt><dd>{texteOuIndisponible(seance.libelle)}</dd></div>
        <div><dt>Salle</dt><dd>{texteOuIndisponible(seance.salle_libelle)}</dd></div>
        <div>
          <dt>Horaire</dt>
          <dd>{heure(seance.debut)} – {heure(seance.fin)}</dd>
        </div>
      </dl>

      <div className="seance-carte__presences">
        <div className="seance-presence-titre">
          <span>Présences</span>
          {sources.length > 0 && (
            <span className="seance-source">Source : {sources.join(' · ')}</span>
          )}
        </div>
        <div className="seance-compteurs">
          <CompteurPresence
            label="Présents"
            variante="seance-compteur--present"
            valeur={valeurOuIndisponible(presences.presents)}
          />
          <CompteurPresence label="Absents" valeur={valeurOuIndisponible(presences.absents_injustifies)} />
          <CompteurPresence label="Justifiés" valeur={valeurOuIndisponible(presences.absents_justifies)} />
          <CompteurPresence label="Dispensés" valeur={valeurOuIndisponible(presences.dispenses)} />
          <CompteurPresence label="Non pointés" valeur={valeurOuIndisponible(seance.non_pointes)} />
          <CompteurPresence label="Attendus" valeur={valeurOuIndisponible(seance.effectif_attendu)} />
        </div>
        <p className="seance-taux">
          Taux de présence :{' '}
          {taux === null || taux === undefined
            ? <span className="seance-vide">Non disponible</span>
            : `${Math.round(taux * 100)} %`}
          {presences.retards > 0 && <span className="seance-retard"> · {presences.retards} retard(s)</span>}
        </p>
      </div>

      <footer className="seance-carte__actions">
        {/* Actions consultatives : un lien vers la page d'émargement (écriture
            possible là-bas, jamais depuis cette console de supervision). */}
        <Link
          to={`/edt/presences?date=${seance.date}&seance=${seance.id}`}
          className="btn-premium-glass"
        >
          <i className="bi bi-list-check" /> Voir les présences
        </Link>
        <Link
          to={`/edt?seance=${seance.id}`}
          className="btn-premium-glass"
        >
          <i className="bi bi-calendar3" /> Détails de la séance
        </Link>
      </footer>
    </article>
  )
}

/**
 * Filtres : uniquement ce que l'API sait filtrer côté serveur
 * (date, statut, formation, groupe, enseignant). Aucun filtre décoratif.
 */
function FiltresSeances({ filtres, onChange, formations, groupes, enseignants }) {
  return (
    <div className="glass-panel seance-filtres" role="group" aria-label="Filtres des séances">
      <label className="seance-filtre">
        <span>Date</span>
        <input
          type="date"
          value={filtres.date}
          onChange={(e) => onChange({ ...filtres, date: e.target.value })}
        />
      </label>

      <label className="seance-filtre">
        <span>Statut</span>
        <select
          value={filtres.statut}
          onChange={(e) => onChange({ ...filtres, statut: e.target.value })}
        >
          <option value="">Tous les statuts</option>
          {Object.entries(LIBELLES_STATUT).map(([code, libelle]) => (
            <option key={code} value={code}>{libelle}</option>
          ))}
        </select>
      </label>

      <label className="seance-filtre">
        <span>Formation</span>
        <select
          value={filtres.formationId}
          onChange={(e) => onChange({ ...filtres, formationId: e.target.value })}
        >
          <option value="">Toutes les formations</option>
          {formations.map((f) => (
            <option key={f.id} value={f.id}>{f.intitule}</option>
          ))}
        </select>
      </label>

      <label className="seance-filtre">
        <span>Groupe</span>
        <select
          value={filtres.groupeId}
          onChange={(e) => onChange({ ...filtres, groupeId: e.target.value })}
        >
          <option value="">Tous les groupes</option>
          {groupes.map((g) => (
            <option key={g.id} value={g.id}>{g.intitule}</option>
          ))}
        </select>
      </label>

      <label className="seance-filtre">
        <span>Enseignant</span>
        <select
          value={filtres.enseignantId}
          onChange={(e) => onChange({ ...filtres, enseignantId: e.target.value })}
        >
          <option value="">Tous les enseignants</option>
          {enseignants.map((p) => (
            <option key={p.id} value={p.id}>{p.intitule}</option>
          ))}
        </select>
      </label>
    </div>
  )
}

/** Options de filtre déduites des séances réellement reçues. */
function optionsDepuisSeances(seances, cle, nom) {
  const vus = new Map()
  seances.forEach((s) => {
    const valeur = s[cle]
    if (valeur !== null && valeur !== undefined && valeur !== '') {
      vus.set(valeur, nom(s))
    }
  })
  return [...vus.entries()].map(([id, intitule]) => ({ id, intitule }))
}

export default function SeancesEnDirect() {
  const [filtres, setFiltres] = useState({
    date: dateDuJour(),
    statut: '',
    formationId: '',
    groupeId: '',
    enseignantId: '',
  })
  const [rafraichissementEnCours, setRafraichissementEnCours] = useState(false)

  const { donnees, chargement, erreur, dernierRafraichissement, recharger } =
    useSupervisionSeances({
      date: filtres.date,
      statut: filtres.statut,
      formationId: filtres.formationId,
      groupeId: filtres.groupeId,
      enseignantId: filtres.enseignantId,
    })

  const seances = useMemo(() => donnees?.seances || [], [donnees])

  // Les listes de filtres sont dérivées des séances reçues : pas de
  // référentiel parallèle inventé pour l'affichage.
  const formations = useMemo(
    () => optionsDepuisSeances(seances, 'formation_id', (s) => s.formation_libelle),
    [seances])
  const groupes = useMemo(
    () => optionsDepuisSeances(seances, 'groupe_id', (s) => s.groupe_libelle),
    [seances])
  const enseignants = useMemo(
    () => optionsDepuisSeances(seances, 'formateur_id', (s) => s.libelle),
    [seances])

  const rafraichir = useCallback(async (silencieux) => {
    setRafraichissementEnCours(true)
    try {
      await recharger(silencieux)
    } finally {
      setRafraichissementEnCours(false)
    }
  }, [recharger])
return (
    <section className="seances-en-direct" data-testid="seances-en-direct">
      <div className="seances-en-direct__entete">
        <span className="plaquette plaquette-primary">Séances en direct</span>
        <h2 className="seances-en-direct__titre">
          Suivi détaillé des séances et des présences
        </h2>
        <p className="seances-en-direct__precision">
          Séances planifiées de l&apos;emploi du temps LMD et présences
          rattachées. Rafraîchissement automatique toutes les minutes ; cette
          console est consultative.
        </p>
      </div>

      <FiltresSeances
        filtres={filtres}
        onChange={setFiltres}
        formations={formations}
        groupes={groupes}
        enseignants={enseignants}
      />

      {chargement && (
        <div className="glass-panel seance-etat" data-testid="seance-chargement">
          <span className="spinner" /> Chargement des séances…
        </div>
      )}

      {!chargement && erreur && (
        <div className="glass-panel seance-etat seance-etat--erreur" data-testid="seance-erreur">
          <p>{erreur}</p>
          <button type="button" className="btn-premium-primary" onClick={() => rafraichir(false)}>
            <i className="bi bi-arrow-repeat" /> Réessayer
          </button>
        </div>
      )}

      {!chargement && !erreur && (
        <>
          <ResumeSeances
            resume={donnees?.resume}
            dernierRafraichissement={dernierRafraichissement}
            onRafraichir={rafraichir}
            rafraichissementEnCours={rafraichissementEnCours}
          />

          {seances.length === 0 ? (
            <div className="glass-panel seance-etat" data-testid="seance-vide">
              <i className="bi bi-calendar-x" />
              <p>Aucune séance planifiée pour cette date et ces filtres.</p>
            </div>
          ) : (
            <div className="seances-en-direct__grille">
              {seances.map((seance) => (
                <CarteSeance key={seance.id} seance={seance} />
              ))}
            </div>
          )}
        </>
      )}
    </section>
  )
}
