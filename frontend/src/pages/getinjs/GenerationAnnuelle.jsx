import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import api from '../../services/api'
import { useToast } from '../../context/ToastContext'
import { formatApiErrors } from '../../utils/apiErrors'

/**
 * GET-INJS — « Générer les emplois du temps » (moteur LMD) + import des
 * inscrits (le menu « Import étudiants » mène au même écran, zone d'import).
 *
 * L'écran ne calcule rien : il expose ce que le backend décide et affiche
 * **tous** les comptes rendus réels (lignes rejetées avec motif, groupes non
 * planifiés, séances non placées). Le lancement persiste une génération
 * traçable (campagne + exécution horodatée) ; la prévisualisation, elle,
 * n'écrit rien. Aucune donnée n'est inventée côté interface.
 */

const STATUTS_LISIBLES = {
  GENERATION_OK: { libelle: 'Planifié', classe: 'badge-success' },
  GENERATION_PARTIELLE: { libelle: 'Partiel', classe: 'badge-warning' },
  GENERATION_IMPOSSIBLE: { libelle: 'Impossible', classe: 'badge-danger' },
  NON_PLANIFIE: { libelle: 'Non planifié', classe: 'badge-neutral' },
  NON_PERSISTE: { libelle: 'Non enregistré', classe: 'badge-danger' },
}

const STATUT_GLOBAL = {
  COMPLETE: { libelle: 'Complet', classe: 'badge-success' },
  PARTIELLE: { libelle: 'Partiel', classe: 'badge-warning' },
  IMPOSSIBLE: { libelle: 'Impossible', classe: 'badge-danger' },
}

const STATUTS_EXECUTION = {
  TERMINE: { libelle: 'terminée', classe: 'badge-success' },
  TERMINE_AVEC_ANOMALIES: { libelle: 'terminée avec anomalies', classe: 'badge-warning' },
  ECHEC: { libelle: 'échec', classe: 'badge-danger' },
  EN_COURS: { libelle: 'en cours', classe: 'badge-primary' },
}

// Motifs d'échec du moteur traduits en langage métier. Un code inconnu est
// affiché tel quel : l'interface ne masque jamais la cause renvoyée.
const MOTIFS_LISIBLES = {
  AUCUNE_SALLE_COMPATIBLE: 'Aucune salle compatible (type ou capacité)',
  PLACEMENT_IMPOSSIBLE: 'Aucune combinaison créneau/salle ne satisfait les contraintes',
  AUCUN_PLACEMENT_POSSIBLE: 'Aucun placement possible',
  AUCUN_BESOIN_PLANIFIABLE: 'Aucun besoin horaire calculable (ni affectation, ni maquette)',
  AUCUN_GROUPE_INJS: 'Aucun groupe dans le périmètre INJS',
  CANEVAS_HORAIRE_VIDE: 'Canevas horaire vide (aucun créneau type)',
  AFFECTATIONS_PEDAGOGIQUES_VIDES: 'Aucune affectation pédagogique',
  HORS_PERIMETRE_INJS: 'Hors périmètre INJS',
  C9_CALENDRIER: 'Aucune période de planification autorisée',
  AUCUNE_MAQUETTE_ACTIVE: 'Aucune maquette active pour cette cohorte',
  VOLUMES_HORAIRES_ABSENTS: 'Volumes horaires absents de la maquette',
  VOLUME_HORAIRE_INCONNU: 'Volume horaire inconnu',
  AUCUN_GROUPE_IMPORTE: 'Aucun groupe importé',
  EDT_STATUT_NON_MODIFIABLE: 'EDT non modifiable (statut actuel)',
  VALIDATION_BLOQUANTE: 'Validation bloquante',
  GROUPES_INCOMPLETS_OU_NON_PERSISTES: 'Certains groupes sont incomplets ou non enregistrés',
  REPARTITION_ANNUELLE_NON_CONFORME: 'Répartition annuelle non conforme',
  OCCURRENCES_NON_PLACEES: 'Séances non placées',
  ANNEE_INCOMPLETE: 'Année incomplète',
  PLAN_INCOMPLET: 'Plan incomplet (vérifiez les séances et les conflits)',
}

function libelleMotif(code) {
  if (!code) return null
  return MOTIFS_LISIBLES[code] || code
}

function Statut({ statut }) {
  const info = STATUTS_LISIBLES[statut] || { libelle: statut || '—', classe: 'badge-neutral' }
  return <span className={`badge ${info.classe}`}>{info.libelle}</span>
}

function ChoixMultiples({ titre, options, selection, onChange, onChangeTout, disabled = false }) {
  const tousVisiblesCoches = options.length > 0 && options.every(({ id }) => selection.includes(id))
  return (
    <fieldset className="gen-choix-multiples" disabled={disabled}>
      <legend className="form-label gen-label">{titre}</legend>
      <div className="gen-choix-liste">
        {options.length > 0 && <label className="form-check gen-choix-item gen-choix-tout">
          <input type="checkbox" className="form-check-input"
            checked={tousVisiblesCoches} onChange={() => onChangeTout(!tousVisiblesCoches)} />
          <span className="form-check-label">Tout sélectionner (options visibles)</span>
        </label>}
        {options.length ? options.map(({ id, label }) => (
          <label key={id} className="form-check gen-choix-item">
            <input type="checkbox" className="form-check-input"
              checked={selection.includes(id)} onChange={() => onChange(id)} />
            <span className="form-check-label">{label}</span>
          </label>
        )) : <span className="text-muted small">Aucune option disponible</span>}
      </div>
      <small className="text-muted">{selection.length} sélectionné(s) sur {options.length}</small>
    </fieldset>
  )
}

function ListeSallesCadrage({ salles, titre, details = false }) {
  const [ouverte, setOuverte] = useState(false)
  return (
    <details className="mt-1" onToggle={(event) => setOuverte(event.currentTarget.open)}>
      <summary>{titre}</summary>
      {ouverte && <ul className="mb-0">
        {salles.map((salle) => (
          <li key={salle.id}>{salle.nom}{details && ` (${salle.type_lieu}, ${salle.capacite ?? 'capacité inconnue'} places)`}</li>
        ))}
      </ul>}
    </details>
  )
}

function Compte({ libelle, valeur }) {
  return (
    <div className="getinjs-compte">
      <span className="getinjs-compte-valeur">{valeur ?? '—'}</span>
      <span className="getinjs-compte-libelle">{libelle}</span>
    </div>
  )
}

function formatDateHeure(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  const jour = d.toLocaleDateString('fr-FR', { day: '2-digit', month: '2-digit' })
  const heure = d.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })
  return `${jour} ${heure}`
}

function formatDuree(ms) {
  if (ms == null) return '—'
  if (ms < 1000) return `${ms} ms`
  const secondes = (ms / 1000).toLocaleString('fr-FR', {
    minimumFractionDigits: 1, maximumFractionDigits: 1,
  })
  return `${secondes} s`
}

export default function GenerationAnnuelle() {
  const { showToast } = useToast()
  const [annees, setAnnees] = useState([])
  const [anneeId, setAnneeId] = useState('')
  const [fichier, setFichier] = useState(null)
  const [rapport, setRapport] = useState(null)
  const [synthese, setSynthese] = useState(null)
  const [bilan, setBilan] = useState(null)
  const [erreurGeneration, setErreurGeneration] = useState('')
  const [enCours, setEnCours] = useState('')
  const [semaines, setSemaines] = useState('1')
  const [telechargement, setTelechargement] = useState(false)
  const inputFichier = useRef(null)

  // Paramètres de génération (maquette) et référentiels de périmètre.
  const [formationsRef, setFormationsRef] = useState([])
  const [niveauxRef, setNiveauxRef] = useState([])
  const [groupesRef, setGroupesRef] = useState([])
  const [filieresSel, setFilieresSel] = useState([])
  const [formationsSel, setFormationsSel] = useState([])
  const [niveauxSel, setNiveauxSel] = useState([])
  const [groupesSel, setGroupesSel] = useState([])
  const [semestresSel, setSemestresSel] = useState([])
  const [dernierApercu, setDernierApercu] = useState(null)
  const [inclureSamedi, setInclureSamedi] = useState(true)
  const [eviterPause, setEviterPause] = useState(true)
  const [publierDirect, setPublierDirect] = useState(false)
  const [modeGeneration, setModeGeneration] = useState('manuel')
  const anneeSelectionnee = annees.find((a) => String(a.id) === String(anneeId))
  const calendrierPropose = useMemo(() => {
    if (!anneeSelectionnee?.date_debut || !anneeSelectionnee?.date_fin) return null
    const debut = Date.parse(`${anneeSelectionnee.date_debut}T12:00:00Z`)
    const fin = Date.parse(`${anneeSelectionnee.date_fin}T12:00:00Z`)
    const total = Math.ceil((fin - debut + 86400000) / (7 * 86400000))
    if (!Number.isFinite(total) || total < 4 || total > 53) return null
    const impairs = Math.floor(total / 2)
    return { total, impairs, pairs: total - impairs,
      bascule: new Date(debut + impairs * 7 * 86400000).toISOString().slice(0, 10) }
  }, [anneeSelectionnee])

  const [maxSeances, setMaxSeances] = useState('30')

  useEffect(() => { setDernierApercu(null) }, [
    anneeId, filieresSel, formationsSel, niveauxSel, groupesSel, semestresSel,
    semaines, inclureSamedi, eviterPause, maxSeances,
  ])

  // Historique des générations et emplois du temps versionnés (réels).
  const [historique, setHistorique] = useState([])
  const [pageHistorique, setPageHistorique] = useState(1)
  const [versions, setVersions] = useState([])

  useEffect(() => {
    let actif = true
    api.get('/scolarite/ref/annees/')
      .then(({ data }) => {
        if (!actif) return
        const liste = Array.isArray(data) ? data : (data?.results || [])
        setAnnees(liste)
        const courante = liste.find((a) => a.courante) || liste[0]
        if (courante) setAnneeId(String(courante.id))
      })
      .catch(() => showToast('Impossible de charger les années académiques.', 'error'))
    return () => { actif = false }
  }, [showToast])

  useEffect(() => {
    let actif = true
    Promise.all([
      api.get('/formations/ref/formations/').catch(() => null),
      api.get('/scolarite/ref/niveaux/').catch(() => null),
    ]).then(([formationsRes, niveauxRes]) => {
      if (!actif) return
      if (formationsRes) {
        setFormationsRef(Array.isArray(formationsRes.data)
          ? formationsRes.data : (formationsRes.data?.results ?? []))
      }
      if (niveauxRes) {
        setNiveauxRef(Array.isArray(niveauxRes.data)
          ? niveauxRes.data : (niveauxRes.data?.results ?? []))
      }
    })
    return () => { actif = false }
  }, [])

  useEffect(() => {
    if (!anneeId) { setGroupesRef([]); return }
    let actif = true
    api.get('/scolarite/ref/groupes/', { params: { annee_academique_id: anneeId } })
      .then(({ data }) => {
        if (!actif) return
        setGroupesRef(Array.isArray(data) ? data : (data?.results ?? []))
      })
      .catch(() => { if (actif) setGroupesRef([]) })
    return () => { actif = false }
  }, [anneeId])

  const chargerHistorique = useCallback(async () => {
    try {
      // Chargement explicite : 500 événements de génération (le serveur
      // plafonne à 500 ; défaut historique 20 conservé pour les autres
      // consommateurs de l'endpoint).
      const { data } = await api.get('/edts/campagnes/historique/', { params: { limite: 500 } })
      setHistorique(Array.isArray(data?.executions) ? data.executions : [])
    } catch { setHistorique([]) }
  }, [])

  const chargerVersions = useCallback(async () => {
    try {
      const { data } = await api.get('/edts/lmd/versions/')
      setVersions(Array.isArray(data?.versions) ? data.versions : [])
    } catch { setVersions([]) }
  }, [])

  useEffect(() => { chargerHistorique(); chargerVersions() }, [chargerHistorique, chargerVersions])

  // Pagination de l'historique chargé (15 par page, test inclus).
  const PAR_PAGE_HISTORIQUE = 15
  const pagesHistoriqueTotal = Math.max(1, Math.ceil(historique.length / PAR_PAGE_HISTORIQUE))
  const pageHistoriqueSure = Math.min(pageHistorique, pagesHistoriqueTotal)
  const debutHistorique = (pageHistoriqueSure - 1) * PAR_PAGE_HISTORIQUE
  const historiqueAffiche = historique.slice(debutHistorique, debutHistorique + PAR_PAGE_HISTORIQUE)

  const chargerSynthese = useCallback(async (id) => {
    if (!id) return
    try {
      const { data } = await api.get('/edts/lmd/import/inscrits/synthese/', { params: { annee: id } })
      // Seule une vraie synthèse porte la liste des cohortes : une réponse
      // d'erreur (404 motivé, objet vide) ne doit jamais devenir un compteur.
      setSynthese(data && Array.isArray(data.cohortes) ? data : null)
    } catch (err) {
      // Un effectif absent n'est pas une erreur bloquante : on le signale.
      setSynthese(null)
      if (err?.response?.status !== 404) {
        showToast(formatApiErrors(err?.response?.data) || 'Synthèse indisponible.', 'error')
      }
    }
  }, [showToast])

  useEffect(() => { chargerSynthese(anneeId) }, [anneeId, chargerSynthese])

  const envoyerFichier = async (mode) => {
    if (!anneeId) return showToast('Choisissez une année académique.', 'error')
    if (!fichier) return showToast('Choisissez un fichier (.csv ou .xlsx).', 'error')

    setEnCours(mode)
    setRapport(null)
    const donnees = new FormData()
    donnees.append('annee_academique_id', anneeId)
    donnees.append('fichier', fichier)

    const chemin = mode === 'analyse'
      ? '/edts/lmd/import/inscrits/analyser/'
      : '/edts/lmd/import/inscrits/'

    try {
      const { data } = await api.post(chemin, donnees)
      setRapport(data)
      if (mode === 'import') {
        showToast(`${data.creees || 0} inscription(s) créée(s), ${data.mises_a_jour || 0} mise(s) à jour.`, 'success')
        chargerSynthese(anneeId)
      } else {
        showToast(`Analyse terminée : ${data.lignes_valides} ligne(s) exploitable(s).`, 'info')
      }
    } catch (err) {
      const corps = err?.response?.data
      if (corps && typeof corps === 'object') setRapport(corps)
      showToast(corps?.motif_echec || formatApiErrors(err?.response?.data) || 'Import refusé.', 'error')
    } finally {
      setEnCours('')
    }
  }

  const semainesListe = () => {
    const valeurs = semaines
      .split(',')
      .map((s) => s.trim())
      .filter((s) => /^\d+$/.test(s))
      .map(Number)
    return valeurs.length > 0 ? valeurs : [1]
  }

  const semainesSaisieInvalide = () =>
    semaines.split(',').map((s) => s.trim()).some(
      (s) => s.length > 0 && !/^\d+$/.test(s)
    )

  const basculer = (setter, id) => setter((ids) => ids.includes(id)
    ? ids.filter((valeur) => valeur !== id) : [...ids, id])

  const construirePerimetre = (mode = 'manuel') => {
    if (mode === 'automatique') return { formations: [], niveaux: [], groupes: [], semestres: [] }
    const formations = formationsSel.length ? formationsSel
      : formationsRef.filter((f) => filieresSel.includes(f.filiere_code)).map((f) => f.id)
    return {
      formations,
      niveaux: niveauxSel,
      groupes: groupesSel,
      semestres: semestresSel,
    }
  }

  // P0-1 + P0-2 : garde-fous avant lancement — périmètre non vide, pas trop large
  // sans confirmation, et avertissement si peu de semaines sur un vaste périmètre.
  const perimetreTropLarge = (perimetre) => {
    return perimetre.formations.length > 20
  }

  const semainesPeuPourPerimetre = (perimetre, nbSemaines) => {
    return nbSemaines <= 4 && (perimetre.formations.length > 5
      || perimetre.niveaux.length > 2
      || perimetre.groupes.length > 10)
  }

  const confirmationPerimetreLarge = (perimetre) => {
    if (!perimetreTropLarge(perimetre)) return true
    const taille = perimetre.formations.length + perimetre.groupes.length
    return window.confirm(
      `Le périmètre sélectionne ${taille} élément(s) de formation/groupe. ` +
      'La génération peut être longue et la couverture partielle. Continuer ?'
    )
  }

  const alerteSemainesPeu = (perimetre, nbSemaines) => {
    if (!semainesPeuPourPerimetre(perimetre, nbSemaines)) return true
    return window.confirm(
      `Vous planifiez ${nbSemaines} semaine(s) sur un périmètre de ` +
      `${perimetre.formations.length} formation(s) et ${perimetre.groupes.length} groupe(s). ` +
      'La couverture risque d’être très faible. Continuer quand même ?'
    )
  }

  const perimetreManuelValide = (groupesOptionsRef) => {
    const perimetre = construirePerimetre()
    if (!perimetre.formations.length || !perimetre.niveaux.length
        || !perimetre.groupes.length || !perimetre.semestres.length) {
      showToast('Sélectionnez au moins une formation (ou filière), un niveau, un groupe et un semestre avec les cases à cocher.', 'error')
      return false
    }
    if (!perimetre.groupes.every((id) => groupesOptionsRef.some((g) => g.id === id))) {
      showToast('Un groupe ne correspond plus au périmètre choisi : vérifiez la sélection.', 'error')
      return false
    }
    return true
  }

  const signatureApercu = () => JSON.stringify({
    anneeId, perimetre: construirePerimetre(), semaines: semainesListe(),
    inclureSamedi, eviterPause, maxSeances,
  })

  const lancerGeneration = async (mode) => {
    if (!anneeId) return showToast('Choisissez une année académique.', 'error')
    if (mode === 'manuel') {
      if (semainesSaisieInvalide()) {
        return showToast('Saisissez uniquement des numéros de semaines (ex. 1,2,3).', 'error')
      }
      if (!perimetreManuelValide(groupesOptions)) return
      const perimetre = construirePerimetre()
      if (!confirmationPerimetreLarge(perimetre)) return
      if (!alerteSemainesPeu(perimetre, semainesListe().length)) return
      if (dernierApercu !== signatureApercu()) {
        showToast('Prévisualisez d’abord ce périmètre exact ; la sélection ou les contraintes ont changé.', 'error')
        return
      }
      // P0-3 : si la prévisualisation montre une couverture très faible, confirmer.
      if (bilan?.status_global === 'PARTIELLE' && dernierApercu === signatureApercu()) {
        const totaux = bilan.totaux || {}
        const placees = totaux.seances_placees ?? 0
        const attendues = totaux.seances_attendues ?? 0
        const couverture = attendues ? Math.round(placees / attendues * 100) : 0
        if (couverture < 50 && !window.confirm(
          `La prévisualisation n’atteint que ${couverture} % de couverture (${placees}/${attendues} séances). ` +
          'Lancer la génération quand même ?'
        )) return
      }
    } else if (!calendrierPropose) {
      const message = 'Dates de l’année absentes ou incompatibles avec une proposition (4 à 53 semaines).'
      setErreurGeneration(message)
      showToast(message, 'error')
      return
    } else if (!window.confirm(
      `CALENDRIER PROVISOIRE NON OFFICIEL pour ${anneeSelectionnee?.libelle || anneeId}.\n`
      + `Du ${anneeSelectionnee.date_debut} au ${anneeSelectionnee.date_fin} : `
      + `semaines 1 à ${calendrierPropose.impairs} (semestres impairs), `
      + `${calendrierPropose.impairs + 1} à ${calendrierPropose.total} (semestres pairs).\n`
      + `Bascule estimée : ${calendrierPropose.bascule}. Confirmer ce découpage ? `
      + 'Les EDT resteront en brouillon ; aucune publication automatique.',
    )) return
    setEnCours('generation')
    setBilan(null)
    setErreurGeneration('')
    let etape = 'création de la campagne'
    try {
      const annee = annees.find((a) => String(a.id) === String(anneeId))
      const horodatage = new Date().toLocaleString('fr-FR')
      const { data: campagne } = await api.post('/edts/campagnes/', {
        annee_academique_id: Number(anneeId),
        libelle: `Génération ${mode} ${annee?.libelle || anneeId} — ${horodatage}`,
        semaines: mode === 'automatique' ? [] : semainesListe(),
        perimetre: construirePerimetre(mode),
        parametres: {
          mode_generation: mode,
          ...(mode === 'automatique' ? {
            calendrier_previsionnel_confirme: true,
            calendrier_dates_confirmees: [annee.date_debut, annee.date_fin],
          } : {}),
          persister: true,
          remplacer: true,
          inclure_maquette: true,
          inclure_samedi: inclureSamedi,
          eviter_pause_meridienne: eviterPause,
          max_seances_par_groupe_semaine: mode === 'automatique' ? null : (maxSeances ? Number(maxSeances) : null),
          publier_direct: mode === 'manuel' && publierDirect,
        },
      })
      etape = 'préparation des données'
      await api.post(`/edts/campagnes/${campagne.id}/donnees-pretes/`, {})
      etape = 'démarrage du calcul'
      // Démarrage ASYNCHRONE : la génération peut durer plusieurs minutes
      // sur un périmètre complet — l'exécuter dans la requête HTTP la
      // faisait expirer (toast « Une erreur est survenue »). Le serveur
      // répond 202 immédiatement et l'avancement se suit sur /statut/.
      await api.post(`/edts/campagnes/${campagne.id}/demarrer/`, { asynchrone: true })
      etape = 'suivi du calcul'
      const statutFinal = await attendreFinGeneration(campagne.id)
      if (statutFinal?.en_cours !== false) {
        // Une attente expirée n'est pas une campagne terminée : ne jamais
        // interroger /resultat/ ni afficher un bilan provisoire comme final.
        chargerHistorique()
        return
      }
      if (statutFinal?.erreur) {
        throw new Error(statutFinal.erreur)
      }
      if (statutFinal?.statut === 'ECHEC') {
        const { data: echec } = await api.get(`/edts/campagnes/${campagne.id}/resultat/`)
        const motif = echec?.campagne?.anomalies?.[0]?.explication
          || echec?.campagne?.execution_courante?.erreur
          || echec?.campagne?.status_global || 'Consultez le bilan et les groupes dans l’historique.'
        setBilan({ status_global: 'IMPOSSIBLE', motif_echec: motif,
          totaux: echec?.totaux, groupes: echec?.groupes,
          detail: { explication: motif } })
        showToast(`Génération échouée : ${motif}`, 'error')
        chargerHistorique()
        return
      }
      const { data: resultat } = await api.get(`/edts/campagnes/${campagne.id}/resultat/`)
      const bilanCampagne = {
        status_global: resultat.campagne?.status_global,
        totaux: resultat.totaux,
        groupes: resultat.groupes,
        persistence_demandee: true,
      }
      setBilan(bilanCampagne)
      showToast(
        `Génération ${STATUT_GLOBAL[bilanCampagne.status_global]?.libelle || bilanCampagne.status_global || 'terminée'} : `
        + `${resultat.totaux?.seances_persistees ?? resultat.totaux?.seances_placees ?? 0} séance(s) enregistrée(s).`,
        bilanCampagne.status_global === 'COMPLETE' ? 'success' : 'warning',
      )
      if (mode === 'manuel' && publierDirect) {
        try {
          await api.post(`/edts/campagnes/${campagne.id}/valider/`, {})
          await api.post(`/edts/campagnes/${campagne.id}/publier/`, {})
          showToast('Emplois du temps validés puis publiés.', 'success')
        } catch (err) {
          showToast('EDT valide mais publication echec. Consultez l’historique.', 'warning')
          throw err
        }
      }
      chargerHistorique()
      chargerVersions()
    } catch (err) {
      const corps = err?.response?.data
      const motif = err?.suiviIndisponible ? err.message : (
        corps?.detail?.explication || corps?.motif_echec
        || formatApiErrors(corps)
        || (err?.message && err.message !== 'Network Error' ? err.message : null)
        || 'Erreur réseau/serveur (vérifiez l’historique de la campagne).'
      )
      const message = err?.suiviIndisponible
        ? `Suivi indisponible pour la campagne : ${motif}`
        : `Échec à l’étape « ${etape} » : ${motif}`
      setErreurGeneration(message)
      showToast(message, 'error')
      chargerHistorique()
    } finally {
      setEnCours('')
    }
  }

  const attendreFinGeneration = async (campagneId) => {
    const delaiMax = 20 * 60 * 1000
    const debutAttente = Date.now()
    let erreursConsecutives = 0
    const controller = new AbortController()
    for (;;) {
      if (Date.now() - debutAttente > delaiMax) {
        showToast(
          'La génération est toujours en cours après 20 minutes : '
          + 'son résultat apparaîtra dans l’historique des générations.',
          'warning',
        )
        return statut
      }
      let statut = null
      try {
        const { data } = await api.get(`/edts/campagnes/${campagneId}/statut/`, {
          signal: controller.signal,
        })
        if (!data || typeof data.en_cours !== 'boolean') throw new Error('Réponse de suivi invalide')
        statut = data
        erreursConsecutives = 0
      } catch (err) {
        if (err.name === 'AbortError') throw err
        const http = err?.response?.status
        erreursConsecutives += 1
        if ([401, 403, 404].includes(http) || erreursConsecutives >= 3) {
          const raison = http ? `HTTP ${http}` : 'réseau ou réponse invalide'
          const erreur = new Error(
            `lecture du statut impossible (${raison}). Le calcul peut encore être en cours ; `
            + 'consultez l’historique avant toute relance.',
          )
          erreur.suiviIndisponible = true
          throw erreur
        }
      }
      if (statut && statut.en_cours === false) return statut
      await new Promise((resolve) => { setTimeout(resolve, 2000) })
    }
  }

  const previsualiser = async () => {
    if (!anneeId) return showToast('Choisissez une année académique.', 'error')
    if (semainesSaisieInvalide()) {
      return showToast('Saisissez uniquement des numéros de semaines (ex. 1,2,3).', 'error')
    }
    if (!perimetreManuelValide(groupesOptions)) return
    setEnCours('previsualisation')
    setDernierApercu(null)
    setErreurGeneration('')
    setBilan(null)
    try {
      const perimetre = construirePerimetre()
      const { data } = await api.post('/edts/lmd/generate-annee/', {
        annee_academique_id: Number(anneeId),
        semaines: semainesListe().length ? semainesListe() : [1],
        persister: false,
        remplacer: true,
        inclure_maquette: true,
        formations: perimetre.formations,
        niveaux: perimetre.niveaux,
        groupes: perimetre.groupes,
        semestres: perimetre.semestres,
        inclure_samedi: inclureSamedi,
        eviter_pause_meridienne: eviterPause,
        max_seances_par_groupe_semaine: maxSeances ? Number(maxSeances) : null,
      })
      setBilan(data && Array.isArray(data.groupes) ? data : null)
      setDernierApercu(signatureApercu())
      showToast(
        `Prévisualisation ${STATUT_GLOBAL[data.status_global]?.libelle || data.status_global} : `
        + `${data.totaux?.seances_placees ?? 0} séance(s) placée(s) (rien n'a été écrit).`,
        data.status_global === 'COMPLETE' ? 'success' : 'warning',
      )
    } catch (err) {
      const corps = err?.response?.data
      if (corps && typeof corps === 'object' && corps.status_global) setBilan(corps)
      else setErreurGeneration(corps?.motif_echec || formatApiErrors(corps) || 'Génération impossible.')
      showToast(corps?.motif_echec || formatApiErrors(err?.response?.data) || 'Génération impossible.', 'error')
    } finally {
      setEnCours('')
    }
  }

  const telechargerConception = async () => {
    setTelechargement(true)
    try {
      const { blob, fileName } = await api.getBlob('/edts/lmd/conception/')
      const url = URL.createObjectURL(blob)
      const lien = document.createElement('a')
      lien.href = url
      lien.download = fileName || 'Conception-GET-INJS.txt'
      document.body.appendChild(lien)
      lien.click()
      lien.remove()
      URL.revokeObjectURL(url)
    } catch {
      showToast('Document de conception indisponible.', 'error')
    } finally {
      setTelechargement(false)
    }
  }

  const cohortes = useMemo(() => synthese?.cohortes || [], [synthese])
  const groupes = useMemo(() => bilan?.groupes || [], [bilan])
  const motifsPartiels = useMemo(() => {
    if (bilan?.status_global !== 'PARTIELLE') return []
    const motifs = bilan.detail?.motifs_groupes
    if (motifs && Object.keys(motifs).length) return Object.entries(motifs)
    const comptes = groupes.reduce((acc, groupe) => {
      const persiste = bilan.persistence_demandee ? groupe.persistance?.effectuee : true
      if (groupe.statut === 'GENERATION_OK' && persiste && (groupe.seances_non_placees || 0) === 0) return acc
      const motif = groupe.motif_echec || groupe.persistance?.motif_refus || 'PLAN_INCOMPLET'
      acc[motif] = (acc[motif] || 0) + 1
      return acc
    }, {})
    return Object.entries(comptes).sort(([a], [b]) => a.localeCompare(b))
  }, [bilan, groupes])

  const couvertureBilan = useMemo(() => {
    if (!bilan?.totaux) return null
    const attendues = bilan.totaux.seances_attendues ?? 0
    const placees = bilan.totaux.seances_placees ?? 0
    return attendues ? Math.round(placees / attendues * 100) : null
  }, [bilan])

  const filieresRef = useMemo(
    () => [...new Set(formationsRef.map((f) => f.filiere_code).filter(Boolean))].sort(),
    [formationsRef],
  )
  const formationsFiltrees = useMemo(
    () => (filieresSel.length
      ? formationsRef.filter((f) => filieresSel.includes(f.filiere_code))
      : formationsRef),
    [formationsRef, filieresSel],
  )
  const groupesOptions = useMemo(
    () => groupesRef.filter((g) => (
      (!formationsSel.length || formationsSel.includes(g.ref_formation_id))
      && (!filieresSel.length || formationsFiltrees.some((f) => f.id === g.ref_formation_id))
      && (!niveauxSel.length || niveauxSel.includes(g.niveau_id))
    )),
    [groupesRef, formationsSel, filieresSel, formationsFiltrees, niveauxSel],
  )

  return (
    <div className="getinjs gen-page">
      <div className="gen-entete">
        <div>
          <span className="gen-sur">Moteur LMD</span>
          <h2 className="gen-titre">Générer les emplois du temps</h2>
          <p className="gen-sous">
            Un seul passage pour toute l'année académique ou pour un périmètre
            ciblé (filière, formation, niveau, groupe, semestre). Le moteur
            garantit l'absence de double réservation de salle, d'enseignant
            et de groupe.
          </p>
        </div>
        <div className="gen-actions">
          <Link to="/edt" className="btn btn-outline-primary btn-sm">
            <i className="bi bi-grid-3x3 me-1" aria-hidden="true"></i>
            Consulter les grilles
          </Link>
          <Link to="/edt/salles-espaces" className="btn btn-outline-secondary btn-sm">
            <i className="bi bi-collection me-1" aria-hidden="true"></i>
            Vérifier les référentiels
          </Link>
          <button
            type="button"
            className="btn btn-outline-secondary btn-sm"
            onClick={telechargerConception}
            disabled={telechargement}
          >
            <i className="bi bi-download me-1" aria-hidden="true"></i>
            {telechargement ? 'Téléchargement…' : 'Conception GET-INJS'}
          </button>
        </div>
      </div>

      <div className="row g-3 mb-3">
        <div className="col-xl-8">
          <div className="card h-100 gen-card-main">
            <div className="card-header">
              <strong>Paramètres de génération</strong>
              <div className="text-muted small">
                La génération crée des EDT brouillons traçables. Une relance remplace
                les séances générées des brouillons modifiables (version 1), sans créer
                automatiquement une nouvelle version ; les EDT validés ou publiés ne sont pas écrasés.
              </div>
            </div>
            <div className="card-body">
              <fieldset className="mb-3" disabled={enCours !== ''}>
                <legend className="form-label gen-label">Mode de génération</legend>
                <label className="form-check form-check-inline">
                  <input className="form-check-input" type="radio" name="mode-generation"
                    checked={modeGeneration === 'manuel'} onChange={() => setModeGeneration('manuel')} />
                  <span className="form-check-label">Manuel (périmètre ciblé)</span>
                </label>
                <label className="form-check form-check-inline">
                  <input className="form-check-input" type="radio" name="mode-generation"
                    checked={modeGeneration === 'automatique'} onChange={() => setModeGeneration('automatique')} />
                  <span className="form-check-label">Automatique (toute l’année)</span>
                </label>
              </fieldset>
              <div className="row g-3">
                <div className="col-md-6">
                  <label className="form-label gen-label" htmlFor="gen-annee">Année académique *</label>
                  <select
                    id="gen-annee"
                    className="form-select"
                    value={anneeId}
                    onChange={(e) => setAnneeId(e.target.value)}
                  >
                    <option value="">— choisir —</option>
                    {annees.map((a) => (
                      <option key={a.id} value={a.id}>
                        {`Année académique ${a.libelle}`}{a.courante ? ' (courante)' : ''}
                      </option>
                    ))}
                  </select>
                </div>
                {modeGeneration === 'manuel' && <>
                <div className="col-md-6">
                  <ChoixMultiples titre="Filières (sélection multiple)"
                    options={filieresRef.map((code) => ({ id: code, label: code }))}
                    selection={filieresSel}
                    onChange={(id) => { basculer(setFilieresSel, id); setFormationsSel([]); setGroupesSel([]) }}
                    onChangeTout={(cocher) => {
                      setFilieresSel(cocher ? filieresRef : []); setFormationsSel([]); setGroupesSel([])
                    }} />
                </div>
                <div className="col-md-6">
                  <ChoixMultiples titre="Formations / parcours (sélection multiple)"
                    options={formationsFiltrees.map((f) => ({ id: f.id, label: f.intitule }))}
                    selection={formationsSel}
                    onChange={(id) => { basculer(setFormationsSel, id); setGroupesSel([]) }}
                    onChangeTout={(cocher) => {
                      setFormationsSel(cocher ? formationsFiltrees.map((f) => f.id) : []); setGroupesSel([])
                    }} />
                </div>
                <div className="col-md-6">
                  <ChoixMultiples titre="Niveaux (sélection multiple)"
                    options={niveauxRef.map((n) => ({ id: n.id, label: `${n.code} — ${n.libelle}` }))}
                    selection={niveauxSel}
                    onChange={(id) => { basculer(setNiveauxSel, id); setGroupesSel([]) }}
                    onChangeTout={(cocher) => {
                      setNiveauxSel(cocher ? niveauxRef.map((n) => n.id) : []); setGroupesSel([])
                    }} />
                </div>
                <div className="col-md-6">
                  <ChoixMultiples titre="Groupes (sélection multiple)"
                    options={groupesOptions.map((g) => ({ id: g.id,
                      label: `${g.nom} — ${formationsRef.find((f) => f.id === g.ref_formation_id)?.intitule || g.ref_formation_id}` }))}
                    selection={groupesSel} onChange={(id) => basculer(setGroupesSel, id)}
                    onChangeTout={(cocher) => setGroupesSel(cocher ? groupesOptions.map((g) => g.id) : [])} />
                </div>
                <div className="col-md-6">
                  <ChoixMultiples titre="Semestres (sélection multiple)"
                    options={Array.from({ length: 10 }, (_, i) => ({ id: i + 1, label: `Semestre ${i + 1} (S${i + 1})` }))}
                    selection={semestresSel} onChange={(id) => basculer(setSemestresSel, id)}
                    onChangeTout={(cocher) => setSemestresSel(cocher
                      ? Array.from({ length: 10 }, (_, i) => i + 1) : [])} />
                </div>
                </>}
              </div>

              <div className="gen-contraintes">
                <span className="gen-label d-block mb-2">Contraintes et options</span>
                <div className="row g-2">
                  <div className="col-md-5">
                    <div className="form-check">
                      <input
                        className="form-check-input" type="checkbox" id="gen-samedi"
                        checked={inclureSamedi}
                        onChange={(e) => setInclureSamedi(e.target.checked)}
                      />
                      <label className="form-check-label" htmlFor="gen-samedi">
                        Inclure le samedi (créneaux du matin)
                      </label>
                    </div>
                    {modeGeneration === 'manuel' && <div className="form-check">
                      <input
                        className="form-check-input" type="checkbox" id="gen-publier"
                        checked={publierDirect}
                        onChange={(e) => setPublierDirect(e.target.checked)}
                      />
                      <label className="form-check-label" htmlFor="gen-publier">
                        Publier directement l'emploi du temps
                      </label>
                    </div>}
                  </div>
                  <div className="col-md-4">
                    <div className="form-check">
                      <input
                        className="form-check-input" type="checkbox" id="gen-pause"
                        checked={eviterPause}
                        onChange={(e) => setEviterPause(e.target.checked)}
                      />
                      <label className="form-check-label" htmlFor="gen-pause">
                        Éviter la pause méridienne (12h-14h)
                      </label>
                    </div>
                    {modeGeneration === 'manuel' && <>
                      <label className="form-label gen-label mt-2" htmlFor="getinjs-semaines">Semaines planifiées</label>
                      <input
                        id="getinjs-semaines"
                        className="form-control form-control-sm"
                        value={semaines}
                        onChange={(e) => setSemaines(e.target.value)}
                        placeholder="ex. 1,2,3"
                        pattern="^\d+(,\s*\d+)*$"
                        title="Saisissez uniquement des numeros de semaines separees par des virgules (ex. 1,2,3)"
                      />
                    </>}
                  </div>
                  {modeGeneration === 'manuel' && <div className="col-md-3">
                    <label className="form-label gen-label" htmlFor="gen-max">Séances max / groupe / semaine</label>
                    <input
                      id="gen-max"
                      type="number" min="1" max="60"
                      className="form-control"
                      value={maxSeances}
                      onChange={(e) => setMaxSeances(e.target.value)}
                    />
                  </div>}
                </div>
              </div>

              <div className="alert alert-info small mt-3 mb-0" role="note">
                {modeGeneration === 'manuel'
                  ? 'Mode manuel : sélectionnez une formation ou filière, un niveau, un groupe et un semestre, puis prévisualisez avant de générer.'
                  : 'Mode automatique : tout le périmètre de l’année, sans sélection manuelle, sans quota hebdomadaire ni publication automatique. Confirmation obligatoire.'}
                {' '}Une génération partielle ne couvre pas toutes les séances ou tous les groupes.
              </div>
              {modeGeneration === 'automatique' && <div className="alert alert-warning small mt-3 mb-0" role="note">
                <strong>Calendrier automatique provisoire — NON OFFICIEL.</strong>{' '}
                {calendrierPropose ? <>
                  Année {anneeSelectionnee?.libelle} : {anneeSelectionnee.date_debut} au {anneeSelectionnee.date_fin}.
                  Semestres impairs : semaines 1–{calendrierPropose.impairs} ; semestres pairs :
                  semaines {calendrierPropose.impairs + 1}–{calendrierPropose.total}.
                  Bascule estimée : {calendrierPropose.bascule}. Confirmation requise au lancement.
                </> : 'Renseignez les dates de l’année académique (4 à 53 semaines).'}
                {' '}Le calendrier provient des dates de l’année, pas des semaines du mode manuel.
                Les EDT automatiques restent en brouillon, sans publication.
              </div>}
              {erreurGeneration && <div className="alert alert-danger mt-3" role="alert">{erreurGeneration}</div>}
              <div className="d-flex flex-wrap align-items-center gap-2 mt-3">
                <button type="button" className="btn btn-dark gen-btn-lancer"
                  onClick={() => lancerGeneration(modeGeneration)}
                  disabled={enCours !== '' || (modeGeneration === 'manuel' && !dernierApercu)}>
                  <i className="bi bi-play-fill me-1" aria-hidden="true"></i>
                  {enCours === 'generation' ? 'Génération…' : modeGeneration === 'manuel'
                    ? 'Lancer la génération manuelle' : 'Lancer la génération automatique (toute l’année)'}
                </button>
                {modeGeneration === 'manuel' && <button
                  type="button"
                  className="btn btn-outline-primary"
                  onClick={previsualiser}
                  disabled={enCours !== ''}
                >
                  <i className="bi bi-eye me-1" aria-hidden="true"></i>
                  {enCours === 'previsualisation' ? 'Prévisualisation…' : 'Prévisualiser sans persister'}
                </button>}
                <span className="text-muted small">
                  Déterministe · CM mutualisés · TD/TP par groupe · contrôle des conflits
                </span>
              </div>
            </div>
          </div>
        </div>

        <div className="col-xl-4">
          <div className="card h-100">
            <div className="card-header"><strong>Comment le moteur décide</strong></div>
            <div className="card-body">
              <ol className="gen-etapes">
                <li>Lecture des groupes inscrits, de leur vague et effectif réel.</li>
                <li>CM mutualisés par promotion, découpés si l'effectif dépasse la plus grande salle.</li>
                <li>TD et TP par groupe, avec meilleur ajustement de capacité.</li>
                <li>Vérification croisée salle / enseignant / groupe, puis persistance.</li>
                <li>Rapport de couverture, conflits et séances non placées.</li>
              </ol>
              <h3 className="gen-sous-titre">Bon à savoir</h3>
              <ul className="gen-savoir">
                <li>La répartition S1/S2 exige des bornes institutionnelles ; elle ne se déduit pas du numéro de semestre.</li>
                <li>Le nombre de créneaux dépend du canevas horaire enregistré, jamais d’un total fixe.</li>
                <li>Les quotas par groupe évitent les semaines surchargées.</li>
                <li>Une relance actualise les séances d’un brouillon modifiable V1 ; elle ne crée pas de V2 et ne remplace pas un EDT validé ou publié.</li>
              </ul>
            </div>
          </div>
        </div>
      </div>

      {bilan && (
        <div className="card mb-3">
          <div className="card-header">
            <strong>Bilan de la génération</strong>
          </div>
          <div className="card-body">
            <p className="mb-2">
              Statut global :{' '}
              <span className={`badge ${STATUT_GLOBAL[bilan.status_global]?.classe || 'badge-neutral'}`}>
                {STATUT_GLOBAL[bilan.status_global]?.libelle || bilan.status_global}
              </span>
              {bilan.motif_echec && <span className="ms-2 text-danger">{libelleMotif(bilan.motif_echec)}</span>}
            </p>

            {bilan.detail?.explication && (
              <div className="alert alert-warning" role="alert">
                {bilan.detail.explication}
                {bilan.detail.action_recommandee && <div>{bilan.detail.action_recommandee}</div>}
              </div>
            )}

            {bilan.status_global === 'PARTIELLE' && (
              <div className="alert alert-warning" role="alert">
                <strong>Pourquoi ce bilan est partiel :</strong>{' '}
                certains groupes sont incomplets ou n’ont pas été enregistrés.
                {motifsPartiels.length > 0 ? (
                  <ul className="mb-0 mt-1">
                    {motifsPartiels.map(([motif, nombre]) => (
                      <li key={motif}>{libelleMotif(motif)} : {nombre} groupe(s)</li>
                    ))}
                  </ul>
                ) : <div>Consultez les statuts et motifs par groupe ci-dessous.</div>}
              </div>
            )}

            {(bilan.totaux?.affectations_salle_cadrage_calculees ?? bilan.totaux?.affectations_salle_cadrage ?? 0) > 0 && (
              <div className="alert alert-warning" role="status">
                <strong>Salles CADRAGE :</strong>{' '}
                {bilan.totaux.affectations_salle_cadrage_calculees ?? bilan.totaux.affectations_salle_cadrage} bloc(s)
                {' '}calculé(s){bilan.persistence_demandee && <>
                  , {bilan.totaux.affectations_salle_cadrage_persistees ?? '—'} bloc(s) enregistré(s)
                </>}. Type et capacité estimatifs, à valider par l’INJS.
                {Array.isArray(bilan.totaux.salles_cadrage_utilisees) && <div className="small mt-1">
                  {bilan.totaux.salles_cadrage_utilisees.length} salle(s) distincte(s)
                  {bilan.persistence_demandee ? ' utilisée(s) par les blocs enregistrés' : ' utilisée(s) par les blocs calculés'}.
                  {bilan.totaux.salles_cadrage_utilisees.length > 0 &&
                    <ListeSallesCadrage salles={bilan.totaux.salles_cadrage_utilisees}
                      titre="Afficher les salles CADRAGE concernées" details />}
                </div>}
              </div>
            )}

            {bilan.totaux && (
              <div className="getinjs-comptes">
                <Compte libelle="groupes" valeur={bilan.totaux.nb_groupes} />
                <Compte libelle={bilan.persistence_demandee ? 'groupes planifiés (calculés)' : 'planifiés'}
                  valeur={bilan.totaux.nb_groupes_planifies_calcules ?? bilan.totaux.nb_groupes_planifies} />
                {bilan.persistence_demandee && <Compte libelle="groupes enregistrés"
                  valeur={bilan.totaux.nb_groupes_planifies} />}
                <Compte libelle={bilan.persistence_demandee ? 'groupes non enregistrés' : 'non planifiés'}
                  valeur={bilan.totaux.nb_groupes_non_planifies} />
                <Compte libelle="complets" valeur={bilan.totaux.nb_groupes_complets} />
                <Compte libelle={bilan.persistence_demandee ? 'étudiants couverts (calculés)' : 'étudiants couverts'}
                  valeur={bilan.totaux.etudiants_couverts_calcules ?? bilan.totaux.etudiants_couverts} />
                {bilan.persistence_demandee && <Compte libelle="étudiants couverts (enregistrés)"
                  valeur={bilan.totaux.etudiants_couverts} />}
                <Compte libelle={bilan.persistence_demandee ? 'séances placées (calculées)' : 'séances placées'}
                  valeur={bilan.totaux.seances_calculees ?? bilan.totaux.seances_placees} />
                {bilan.persistence_demandee && <Compte libelle="séances enregistrées"
                  valeur={bilan.totaux.seances_persistees} />}
                <Compte libelle={bilan.persistence_demandee ? 'séances non enregistrées' : 'séances non placées'}
                  valeur={bilan.totaux.seances_non_placees} />
                {bilan.persistence_demandee && <Compte libelle="EDT enregistrés" valeur={bilan.totaux.edts_persistes} />}
              </div>
            )}

            {couvertureBilan !== null && couvertureBilan < 50 && <div className="alert alert-danger mt-3" role="alert">
              <strong>Couverture critique ({couvertureBilan} %) :</strong> seul(es) {bilan.totaux.seances_placees ?? 0} séance(s) sur {bilan.totaux.seances_attendues ?? 0} ont été placée(s).
              Cette génération ne couvre pas les besoins horaires du périmètre.
              Consultez les groupes ci-dessous et envisagez une relance ciblée.
            </div>}

            {groupes.length > 0 && (
              <div className="table-responsive mt-3">
                <table className="table table-sm" aria-label="Bilan par groupe — aucune ligne n’est masquée">
                  <caption className="text-muted small">
                    Bilan par groupe — aucune ligne n’est masquée
                  </caption>
                  <thead>
                    <tr>
                      <th scope="col">Formation</th>
                      <th scope="col">Niveau</th>
                      <th scope="col">Groupe</th>
                      <th scope="col">Vague</th>
                      <th scope="col" className="text-end">Effectif</th>
                      <th scope="col" className="text-end">Placées (calculées)</th>
                      {bilan.persistence_demandee && <th scope="col" className="text-end">Enregistrées</th>}
                      <th scope="col" className="text-end">Non placées (calculées)</th>
                      <th scope="col">Statut</th>
                    </tr>
                  </thead>
                  <tbody>
                    {groupes.map((g) => (
                      <tr key={g.groupe_id}>
                        <td>{g.formation}</td>
                        <td>{g.niveau}</td>
                        <td>{g.groupe}</td>
                        <td>{g.vague || '—'}</td>
                        <td className="text-end">{g.effectif ?? '—'}</td>
                        <td className="text-end">{g.seances_placees}</td>
                        {bilan.persistence_demandee && <td className="text-end">{g.seances_persistees ?? '—'}</td>}
                        <td className="text-end">{g.seances_non_placees}</td>
                        <td>
                          <Statut statut={g.statut} />
                          {g.motif_echec && (
                            <div className="small text-muted">{libelleMotif(g.motif_echec)}</div>
                          )}
                          {(g.affectations_salle_cadrage_calculees ?? g.affectations_salle_cadrage ?? 0) > 0 && (
                            <div className="small text-warning">
                              Salle CADRAGE : {g.affectations_salle_cadrage_calculees ?? g.affectations_salle_cadrage} bloc(s) calculé(s)
                              {bilan.persistence_demandee && <>
                                , {g.affectations_salle_cadrage_persistees ?? '—'} enregistré(s)
                              </>}
                              {(g.salles_cadrage_calculees ?? g.salles_cadrage)?.length > 0 &&
                                <ListeSallesCadrage salles={g.salles_cadrage_calculees ?? g.salles_cadrage}
                                  titre="Voir les salles CADRAGE du groupe" />}
                            </div>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}

      <div className="row g-3 mb-3">
        <div className="col-xl-8">
          <div className="card h-100">
            <div className="card-header d-flex flex-wrap align-items-center gap-2">
              <div>
                <strong>Historique des générations</strong>
                <div className="text-muted small">
                  Traçabilité complète : périmètre, volumes, conflits, durée
                </div>
              </div>
              <span className="badge text-bg-warning ms-auto">
                <i className="bi bi-cloud-download me-1"></i>Chargement explicite : 500 événements
              </span>
              <span className="badge text-bg-primary">{historique.length} chargé(s)</span>
            </div>
            <div className="table-responsive">
              <table className="table table-hover align-middle mb-0 gen-table">
                <thead>
                  <tr>
                    <th scope="col">Date</th>
                    <th scope="col">Périmètre</th>
                    <th scope="col">Semestres</th>
                    <th scope="col">Séances</th>
                    <th scope="col">Couverture</th>
                    <th scope="col">Conflits</th>
                    <th scope="col">Durée</th>
                    <th scope="col">Statut</th>
                  </tr>
                </thead>
                <tbody>
                  {historique.length === 0 ? (
                    <tr>
                      <td colSpan="8" className="text-center text-muted py-4">
                        Aucune génération exécutée pour le moment : lancez une
                        génération pour alimenter cet historique.
                      </td>
                    </tr>
                  ) : historiqueAffiche.map((ligne) => (
                    <tr key={ligne.id}>
                      <td className="text-nowrap">{formatDateHeure(ligne.date)}</td>
                      <td>
                        <span className="d-block fw-semibold">
                          {ligne.perimetre.formations.length > 0
                            ? ligne.perimetre.formations.join(', ')
                            : ligne.perimetre.filieres.length > 0
                              ? `Filière(s) ${ligne.perimetre.filieres.join(', ')}`
                              : 'Toutes filières'}
                        </span>
                        <span className="d-block small text-muted">
                          {ligne.perimetre.niveaux.length > 0
                            ? ligne.perimetre.niveaux.join(', ')
                            : 'Tous niveaux'}
                          {ligne.perimetre.groupes.length > 0
                            && ` · ${ligne.perimetre.groupes.join(', ')}`}
                        </span>
                      </td>
                      <td>{ligne.semestres.length > 0 ? ligne.semestres.join(', ') : '—'}</td>
                      <td className="fw-bold">{ligne.seances_placees ?? '—'}</td>
                      <td>{ligne.couverture_pct != null ? `${ligne.couverture_pct} %` : '—'}</td>
                      <td>
                        <span className={`gen-conflits ${ligne.conflits ? 'is-alert' : ''}`}>
                          {ligne.conflits ?? '—'}
                        </span>
                      </td>
                      <td className="text-nowrap">{formatDuree(ligne.duree_ms)}</td>
                      <td>
                        <span className={`badge ${STATUTS_EXECUTION[ligne.statut]?.classe || 'badge-neutral'}`}>
                          {STATUTS_EXECUTION[ligne.statut]?.libelle || ligne.statut}
                        </span>
                        {ligne.statut === 'ECHEC' && (ligne.erreur || ligne.explication || ligne.motif_echec) && (
                          <span className="d-block small text-danger mt-1" role="alert">
                            {ligne.erreur || ligne.explication || libelleMotif(ligne.motif_echec)}
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {historique.length > 0 && (
              <div className="card-footer gen-pagination">
                <span>
                  Événements {debutHistorique + 1} à {debutHistorique + historiqueAffiche.length} sur {historique.length}
                </span>
                {pagesHistoriqueTotal > 1 && (
                  <span className="gen-pagination-nav">
                    <button type="button" className="btn btn-outline-secondary btn-sm"
                            disabled={pageHistoriqueSure <= 1}
                            onClick={() => setPageHistorique(pageHistoriqueSure - 1)}>
                      <i className="bi bi-chevron-left me-1"></i>Précédent
                    </button>
                    <strong>Page {pageHistoriqueSure} sur {pagesHistoriqueTotal}</strong>
                    <button type="button" className="btn btn-outline-secondary btn-sm"
                            disabled={pageHistoriqueSure >= pagesHistoriqueTotal}
                            onClick={() => setPageHistorique(pageHistoriqueSure + 1)}>
                      Suivant<i className="bi bi-chevron-right ms-1"></i>
                    </button>
                  </span>
                )}
              </div>
            )}
          </div>
        </div>

        <div className="col-xl-4">
          <div className="card h-100">
            <div className="card-header">
              <strong>Emplois du temps versionnés</strong>
              <div className="text-muted small">Chaque passage crée une version horodatée</div>
            </div>
            <div className="card-body">
              {versions.length === 0 ? (
                <p className="text-muted small mb-0">
                  Aucun emploi du temps versionné pour le moment.
                </p>
              ) : (
                <ul className="gen-versions">
                  {versions.slice(0, 5).map((v) => (
                    <li key={v.id} className="gen-version">
                      <div className="d-flex align-items-start gap-2">
                        <span className="gen-version-code">{v.titre}</span>
                        <span className={`badge ${v.statut === 'PUBLIE' ? 'badge-success' : v.statut === 'VALIDE' ? 'badge-primary' : 'badge-neutral'}`}>
                          {(v.statut_libelle || v.statut || '').toLowerCase()}
                        </span>
                      </div>
                      <span className="gen-version-date">{formatDateHeure(v.creee_le)}</span>
                      <span className="gen-version-desc">
                        {`Emploi du temps ${v.annee_academique} · ${v.nb_seances} séances · ${v.libelle}`}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
              <Link to="/edt/versions" className="btn btn-link btn-sm px-0">
                Versions &amp; publication
                <i className="bi bi-arrow-right ms-1" aria-hidden="true"></i>
              </Link>
            </div>
          </div>
        </div>
      </div>

      <div className="card mb-3">
        <div className="card-header"><strong>Règles métier appliquées par le moteur</strong></div>
        <div className="card-body">
          <div className="row">
            <div className="col-md-6">
              <ul className="gen-regles">
                <li>Un enseignant ne peut pas être affecté à deux séances au même créneau.</li>
                <li>Un groupe ne peut pas suivre deux cours simultanément.</li>
                <li>Le meilleur ajustement de capacité est utilisé pour les TD et TP.</li>
              </ul>
            </div>
            <div className="col-md-6">
              <ul className="gen-regles">
                <li>Une salle ne peut accueillir qu'une séance par créneau et par semestre.</li>
                <li>Le CM est mutualisé au niveau de la promotion puis découpé selon la capacité des amphis.</li>
                <li>Les quotas par groupe limitent la charge hebdomadaire à 30 séances par défaut.</li>
              </ul>
            </div>
          </div>
        </div>
      </div>

      <div className="card mb-3">
        <div className="card-header">
          <strong>Import du fichier des inscrits</strong>
          <div className="text-muted small">
            Même écran que le menu « Import étudiants » : fichier externe
            (CSV / XLSX), y compris hors chaîne de parcours.
          </div>
        </div>
        <div className="card-body">
          {synthese && (
            <div className="getinjs-comptes mb-3">
              <Compte libelle="étudiants importés" valeur={synthese.effectif_total} />
              <Compte libelle="cohortes" valeur={synthese.nb_cohortes} />
            </div>
          )}
          <p className="text-muted small">
            Formats acceptés : CSV (séparateur « ; » ou « , ») et Excel (.xlsx).
            Colonnes attendues : matricule, nom, formation, niveau — les autres
            (prénoms, sexe, date de naissance, parcours, semestre, groupe, vague)
            sont reconnues par synonymes. L’analyse n’écrit <strong>rien</strong>.
          </p>
          <div className="row g-2 align-items-end">
            <div className="col-md-5">
              <label className="form-label" htmlFor="getinjs-fichier">Fichier des inscrits</label>
              <input
                id="getinjs-fichier"
                ref={inputFichier}
                type="file"
                className="form-control"
                accept=".csv,.txt,.xlsx,.xlsm"
                onChange={(e) => setFichier(e.target.files?.[0] || null)}
              />
            </div>
            <div className="col-md-7 d-flex flex-wrap gap-2">
              <button
                type="button"
                className="btn btn-outline-primary"
                onClick={() => envoyerFichier('analyse')}
                disabled={enCours !== ''}
              >
                <i className="bi bi-search me-1" aria-hidden="true"></i>
                {enCours === 'analyse' ? 'Analyse…' : 'Analyser sans importer'}
              </button>
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => envoyerFichier('import')}
                disabled={enCours !== ''}
              >
                <i className="bi bi-upload me-1" aria-hidden="true"></i>
                {enCours === 'import' ? 'Import…' : 'Importer'}
              </button>
            </div>
          </div>

          {rapport && (
            <div className="mt-3">
              <div className="getinjs-comptes">
                <Compte libelle="lignes lues" valeur={rapport.lignes_lues} />
                <Compte libelle="valides" valeur={rapport.lignes_valides} />
                <Compte libelle="rejetées" valeur={rapport.lignes_rejetees} />
                <Compte libelle="créées" valeur={rapport.creees} />
                <Compte libelle="mises à jour" valeur={rapport.mises_a_jour} />
                <Compte libelle="effectif" valeur={rapport.effectif_total} />
              </div>

              {rapport.motif_echec && (
                <div className="alert alert-danger mt-3" role="alert">
                  <strong>Import refusé — {rapport.motif_echec}</strong>
                  {rapport.detail?.explication && <div>{rapport.detail.explication}</div>}
                  {rapport.detail?.colonnes_manquantes && (
                    <div>Colonnes manquantes : {rapport.detail.colonnes_manquantes.join(', ')}</div>
                  )}
                </div>
              )}

              {rapport.erreurs?.length > 0 && (
                <div className="table-responsive mt-3">
                  <table className="table table-sm">
                    <caption className="text-muted small">
                      Lignes rejetées — chaque rejet est motivé
                      {rapport.erreurs_tronquees > 0 && ` (${rapport.erreurs_tronquees} de plus non affichées)`}
                    </caption>
                    <thead>
                      <tr>
                        <th scope="col">Ligne</th>
                        <th scope="col">Motif</th>
                        <th scope="col">Détail</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rapport.erreurs.map((erreur) => (
                        <tr key={`${erreur.ligne}-${erreur.motif}`}>
                          <td>{erreur.ligne}</td>
                          <td><span className="badge badge-danger">{erreur.motif}</span></td>
                          <td>{erreur.detail}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {rapport.cohortes?.length > 0 && (
                <div className="table-responsive mt-3">
                  <table className="table table-sm">
                    <caption className="text-muted small">Cohortes reconnues</caption>
                    <thead>
                      <tr>
                        <th scope="col">Formation</th>
                        <th scope="col">Niveau</th>
                        <th scope="col">Groupe</th>
                        <th scope="col">Vague</th>
                        <th scope="col" className="text-end">Effectif</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rapport.cohortes.map((c, index) => (
                        <tr key={`${c.formation}-${c.groupe}-${c.vague}-${index}`}>
                          <td>{c.formation}</td>
                          <td>{c.niveau}</td>
                          <td>{c.groupe || '—'}</td>
                          <td>{c.vague || '—'}</td>
                          <td className="text-end">{c.effectif}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {cohortes.length > 0 && (
        <div className="card">
          <div className="card-header"><strong>Cohortes importées pour cette année</strong></div>
          <div className="card-body">
            <div className="table-responsive">
              <table className="table table-sm" aria-label="Cohortes importées — effectif dénombré, jamais déclaré">
                <caption className="text-muted small">
                  Cohortes importées — effectif dénombré, jamais déclaré
                </caption>
                <thead>
                  <tr>
                    <th scope="col">Formation</th>
                    <th scope="col">Parcours</th>
                    <th scope="col">Niveau</th>
                    <th scope="col">Groupe</th>
                    <th scope="col">Vague</th>
                    <th scope="col" className="text-end">Effectif</th>
                  </tr>
                </thead>
                <tbody>
                  {cohortes.map((c, index) => (
                    <tr key={`${c.formation}-${c.groupe}-${index}`}>
                      <td>{c.formation}</td>
                      <td>{c.parcours || '—'}</td>
                      <td>{c.niveau || '—'}</td>
                      <td>{c.groupe || '—'}</td>
                      <td>{c.vague || '—'}</td>
                      <td className="text-end">{c.effectif}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
