import { useEffect, useMemo, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../services/api'
import { getAnneeCourante, messageErreur } from '../services/scolarite'
import { useToast } from '../context/ToastContext'
import { useAuth } from '../context/AuthContext'
import ConfirmModal from '../components/ConfirmModal'
import { ADMIN_LEVEL_ROLES } from '../utils/roles'
import { downloadFile } from '../utils/downloadFile'
import '../styles/ueEcue.css'

/**
 * Écran **UE / ECUE** — le référentiel pédagogique, éditable.
 *
 * Jusqu'ici cet écran affichait des listes : la maquette, puis ses unités.
 * On pouvait constater, jamais corriger. Or c'est précisément ici qu'un
 * responsable pédagogique doit pouvoir créer une unité, la modifier, la
 * publier ou la retirer.
 *
 * Trois niveaux, trois décisions :
 *
 * 1. **la maquette** donne le contexte (année, cycle, niveau, version) et son
 *    statut. Tant qu'elle est en brouillon, son contenu est éditable ; validée,
 *    active ou archivée, elle est gelée — l'interface le dit et n'affiche pas
 *    de boutons qui échoueraient côté serveur ;
 * 2. **l'UE** (unité d'enseignement) porte les crédits et la famille ;
 * 3. **l'ECUE** (élément constitutif) porte les volumes horaires.
 *
 * Les deux derniers suivent le même cycle de vie : Brouillon (modifiable et
 * supprimable) → Activé (publié, gelé) → Désactivé (retiré, conservé).
 * Le serveur applique la matrice de transitions ; l'écran ne fait que proposer
 * les transitions autorisées, et affiche ses refus tels quels.
 */

const STATUTS = [
  { valeur: 'BROUILLON', libelle: 'Brouillon', classe: 'text-bg-secondary' },
  { valeur: 'ACTIVE', libelle: 'Activé', classe: 'text-bg-success' },
  { valeur: 'DESACTIVEE', libelle: 'Désactivé', classe: 'text-bg-warning' },
]

const STATUT_MAQUETTE = {
  BROUILLON: 'Brouillon — contenu modifiable',
  VALIDEE: 'Validée — contenu gelé',
  ACTIVE: 'Active — contenu gelé',
  ARCHIVEE: 'Archivée — contenu gelé',
}

/** Transitions proposées à l'utilisateur (le serveur reste seul juge). */
const TRANSITIONS = {
  BROUILLON: ['ACTIVE'],
  ACTIVE: ['DESACTIVEE'],
  DESACTIVEE: ['ACTIVE', 'BROUILLON'],
}

const LIBELLE_ACTION = {
  ACTIVE: 'Activer',
  DESACTIVEE: 'Désactiver',
  BROUILLON: 'Repasser en brouillon',
}

const ICONE_ACTION = {
  ACTIVE: 'bi-check-circle',
  DESACTIVEE: 'bi-pause-circle',
  // Retour en brouillon : flèche de retour, jamais un crayon — le crayon est
  // déjà le bouton « modifier », deux icônes identiques pour deux actes
  // différents seraient un piège.
  BROUILLON: 'bi-arrow-counterclockwise',
}

const estMaquetteDemo = (maquette) => /\[(?:exemple|demo)\]/i.test(maquette?.libelle || '')

function BadgeStatut({ statut }) {
  const definition = STATUTS.find((s) => s.valeur === statut) || {
    libelle: statut || '—', classe: 'text-bg-light',
  }
  return (
    <span
      className={`badge ${definition.classe} uex-badge uex-badge--${String(statut || 'inconnu').toLowerCase()}`}
      data-testid={`statut-${statut}`}
    >
      {definition.libelle}
    </span>
  )
}

/** Barre empilée CM/TD/TP d'un ECUE : la répartition des volumes en un coup d'œil. */
function BarreVolumes({ ecue }) {
  const cm = Number(ecue.volume_cm) || 0
  const td = Number(ecue.volume_td) || 0
  const tp = Number(ecue.volume_tp) || 0
  const total = cm + td + tp
  if (!total) return <span className="uex-volumes-vide">—</span>
  const part = (v) => `${Math.round((v / total) * 1000) / 10}%`
  return (
    <span className="uex-volumes">
      <span className="uex-volumes-barre" role="img" aria-label={`Volumes : CM ${cm} h, TD ${td} h, TP ${tp} h`}>
        {cm > 0 && <span className="uex-volumes-seg is-cm" style={{ width: part(cm) }}></span>}
        {td > 0 && <span className="uex-volumes-seg is-td" style={{ width: part(td) }}></span>}
        {tp > 0 && <span className="uex-volumes-seg is-tp" style={{ width: part(tp) }}></span>}
      </span>
      <span className="uex-volumes-texte">
        CM {cm} · TD {td} · TP {tp}
        <strong> — {total} h</strong>
      </span>
    </span>
  )
}

const nombre = (valeur) => (valeur === '' || valeur === null || valeur === undefined
  ? null : Number(valeur))

/**
 * Affiche une valeur pédagogique sans mentir sur son absence.
 *
 * La source officielle ne publie les crédits qu'au niveau de l'**UE** : elle
 * donne les intitulés des ECUE sans leurs crédits ni leurs volumes horaires.
 * L'import officiel laisse donc ces champs à 0 ; toute valeur ajoutée ensuite
 * doit être vérifiée contre une source. On affiche « — » pour les zéros, qui
 * signifient « non documenté » et non « zéro crédit ».
 */
const afficherValeur = (valeur) => {
  const n = Number(valeur)
  return Number.isFinite(n) && n !== 0 ? String(n) : '—'
}

/** Formulaire modal d'UE ou d'ECUE (création / modification). */
function FormulaireElement({ type, initial, semestres, familles, enCours, onFermer, onValider }) {
  const creation = !initial
  const [valeurs, setValeurs] = useState(() => ({
    code: initial?.code || '',
    intitule: initial?.intitule || '',
    credits: initial?.credits ?? 0,
    ...(type === 'ue'
      ? {
        semestre_id: initial?.semestre?.id ?? semestres[0]?.id ?? '',
        caractere: initial?.caractere || 'OBLIGATOIRE',
        famille_id: initial?.famille_code
          ? familles.find((f) => f.code === initial.famille_code)?.id || ''
          : '',
        ordre: initial?.ordre ?? 1,
      }
      : {
        coefficient: initial?.coefficient ?? 1,
        volume_cm: initial?.volume_cm ?? 0,
        volume_td: initial?.volume_td ?? 0,
        volume_tp: initial?.volume_tp ?? 0,
        ordre: initial?.ordre ?? 1,
      }),
  }))
  const [message, setMessage] = useState('')

  useEffect(() => {
    const surTouche = (e) => { if (e.key === 'Escape') onFermer() }
    window.addEventListener('keydown', surTouche)
    return () => window.removeEventListener('keydown', surTouche)
  }, [onFermer])

  const modifier = (cle, valeur) => {
    setValeurs((prec) => ({ ...prec, [cle]: valeur }))
    setMessage('')
  }

  const soumettre = async (evenement) => {
    evenement.preventDefault()
    if (!valeurs.code.trim()) {
      setMessage('Le code est obligatoire.')
      return
    }
    if (!valeurs.intitule.trim()) {
      setMessage("L'intitulé est obligatoire.")
      return
    }
    const corps = {
      code: valeurs.code.trim(),
      intitule: valeurs.intitule.trim(),
      credits: nombre(valeurs.credits) ?? 0,
      ordre: nombre(valeurs.ordre) ?? 1,
    }
    if (type === 'ue') {
      corps.caractere = valeurs.caractere
      corps.famille_id = valeurs.famille_id || null
      if (valeurs.semestre_id) corps.semestre_id = nombre(valeurs.semestre_id)
    } else {
      corps.coefficient = nombre(valeurs.coefficient) ?? 1
      corps.volume_cm = nombre(valeurs.volume_cm) ?? 0
      corps.volume_td = nombre(valeurs.volume_td) ?? 0
      corps.volume_tp = nombre(valeurs.volume_tp) ?? 0
    }
    const resultat = await onValider(corps, creation)
    if (resultat) setMessage(resultat)
  }

  const champ = (cle, libelle, options = {}) => (
    <div className={options.large ? 'ue-ecue-pleine-largeur' : ''}>
      <label className="form-label" htmlFor={`el-${cle}`}>{libelle}</label>
      <input
        id={`el-${cle}`}
        data-testid={`element-${cle}`}
        className="form-control"
        type={options.nombre ? 'number' : 'text'}
        min={options.min}
        max={options.max}
        value={valeurs[cle]}
        onChange={(e) => modifier(cle, e.target.value)}
      />
    </div>
  )

  return (
    <div className="modal-overlay" onClick={onFermer} role="presentation">
      <div
        className="modal-content"
        style={{ maxWidth: 720 }}
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby="form-element-titre"
      >
        <div className="modal-header">
          <h5 className="modal-title" id="form-element-titre">
            {creation
              ? (type === 'ue' ? 'Créer une unité d’enseignement' : 'Créer un ECUE')
              : (type === 'ue' ? 'Modifier l’unité d’enseignement' : 'Modifier l’ECUE')}
          </h5>
          <button type="button" className="btn-close" onClick={onFermer} aria-label="Fermer" />
        </div>
        <form onSubmit={soumettre} data-testid="formulaire-element">
          <div className="modal-body">
            {message && (
              <div className="alert alert-danger py-2" role="alert" data-testid="element-erreur">
                {message}
              </div>
            )}
            {!creation && (
              <p className="small text-muted">
                La modification n’est possible qu’en <strong>brouillon</strong> : un
                élément activé est publié et ne se réécrit pas en place.
              </p>
            )}
            <div className="ue-ecue-formulaire">
              {champ('code', 'Code')}
              {champ('ordre', 'Ordre', { nombre: true, min: 1 })}
              {champ('intitule', 'Intitulé', { large: true })}
              {champ('credits', type === 'ue' ? 'Crédits ECTS' : 'Crédits ECTS (facultatif)', {
                nombre: true, min: 0, max: 60,
              })}
              {type === 'ue' && (
                <div>
                  <label className="form-label" htmlFor="el-semestre">Semestre</label>
                  <select
                    id="el-semestre"
                    data-testid="element-semestre_id"
                    className="form-select"
                    value={valeurs.semestre_id}
                    onChange={(e) => modifier('semestre_id', e.target.value)}
                  >
                    <option value="">—</option>
                    {semestres.map((s) => (
                      <option key={s.id} value={s.id}>{s.libelle}</option>
                    ))}
                  </select>
                </div>
              )}
              {type === 'ue' && (
                <div>
                  <label className="form-label" htmlFor="el-caractere">Caractère</label>
                  <select
                    id="el-caractere"
                    data-testid="element-caractere"
                    className="form-select"
                    value={valeurs.caractere}
                    onChange={(e) => modifier('caractere', e.target.value)}
                  >
                    <option value="OBLIGATOIRE">Obligatoire</option>
                    <option value="OPTIONNELLE">Optionnelle</option>
                    <option value="LIBRE">Libre</option>
                  </select>
                </div>
              )}
              {type === 'ue' && (
                <div>
                  <label className="form-label" htmlFor="el-famille">Famille de modules</label>
                  <select
                    id="el-famille"
                    data-testid="element-famille_id"
                    className="form-select"
                    value={valeurs.famille_id}
                    onChange={(e) => modifier('famille_id', e.target.value)}
                  >
                    <option value="">—</option>
                    {familles.map((f) => (
                      <option key={f.id} value={f.id}>{f.libelle}</option>
                    ))}
                  </select>
                  <div className="form-text">Axe d’analyse des crédits (source officielle).</div>
                </div>
              )}
              {type === 'ecue' && champ('coefficient', 'Coefficient', { nombre: true, min: 0 })}
              {type === 'ecue' && champ('volume_cm', 'Volume CM (h)', { nombre: true, min: 0 })}
              {type === 'ecue' && champ('volume_td', 'Volume TD (h)', { nombre: true, min: 0 })}
              {type === 'ecue' && champ('volume_tp', 'Volume TP (h)', { nombre: true, min: 0 })}
            </div>
          </div>
          <div className="modal-footer">
            <button type="button" className="btn btn-outline-secondary" onClick={onFermer}>
              Annuler
            </button>
            <button type="submit" className="btn btn-primary" disabled={enCours} data-testid="element-enregistrer">
              {enCours ? 'Enregistrement…' : (creation ? 'Créer' : 'Enregistrer')}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

/** Boutons de changement de statut d'un élément (UE ou ECUE). */
function ActionsStatut({ element, type, enCours, onChanger }) {
  const transitions = TRANSITIONS[element.statut] || []
  return (
    <>
      {transitions.map((statut) => (
        <button
          key={statut}
          type="button"
          className={`btn btn-sm me-1 ${statut === 'DESACTIVEE'
            ? 'btn-outline-warning' : 'btn-outline-success'}`}
          onClick={() => onChanger(element, statut)}
          disabled={enCours}
          title={`${LIBELLE_ACTION[statut]} ${type === 'ue' ? 'l’UE' : 'l’ECUE'} ${element.code}`}
          aria-label={`${LIBELLE_ACTION[statut]} ${element.code}`}
          data-testid={`${type}-statut-${statut}-${element.id}`}
        >
          <i className={`bi ${ICONE_ACTION[statut]}`} aria-hidden="true"></i>
        </button>
      ))}
    </>
  )
}

export default function EcranUeEcue() {
  const { showToast } = useToast()
  const queryClient = useQueryClient()
  const { user } = useAuth()
  const [maquetteId, setMaquetteId] = useState('')
  const [selectionMaquettes, setSelectionMaquettes] = useState([])
  const [ueId, setUeId] = useState(null)
  const [formulaire, setFormulaire] = useState(null)
  const [formulaireMaquette, setFormulaireMaquette] = useState(null)
  const [valeursMaquette, setValeursMaquette] = useState({
    annee_academique_id: '',
    ref_formation_id: '',
    niveau_id: '',
    libelle: '',
    commentaire_validation: '',
  })
  const [maquetteEnCours, setMaquetteEnCours] = useState(false)
  const [fichierImport, setFichierImport] = useState(null)
  const [apercuImport, setApercuImport] = useState(null)
  const [importEnCours, setImportEnCours] = useState(false)
  const [exportDetaille, setExportDetaille] = useState(false)
  const [suppression, setSuppression] = useState(null)
  const [suppressionMasse, setSuppressionMasse] = useState(null)
  const [activationTotaleDemandee, setActivationTotaleDemandee] = useState(false)
  const [activationTotaleEnCours, setActivationTotaleEnCours] = useState(false)
  const [recherche, setRecherche] = useState('')
  // Sélection multiple (cases à cocher) : ids des UE et des ECUE cochés.
  const [selectionUe, setSelectionUe] = useState([])
  const [selectionEcue, setSelectionEcue] = useState([])

  // Écriture : mêmes rôles que le serveur (IsSecretariatOrDFRC), sans créer de
  // système d'habilitation parallèle. Le refus réel vient toujours de l'API.
  const peutGerer = [
    ...ADMIN_LEVEL_ROLES, 'SECRETARIAT', 'CHEF_SECRETARIAT',
  ].includes(user?.role)

  const maquettesQuery = useQuery({
    queryKey: ['ue-ecue', 'maquettes'],
    queryFn: async () => {
      const res = await api.get('/scolarite/maquettes/')
      return Array.isArray(res.data) ? res.data : (res.data?.results || [])
    },
    staleTime: 60_000,
  })
  const anneeCouranteQuery = useQuery({
    queryKey: ['ue-ecue', 'annee-courante'],
    queryFn: getAnneeCourante,
    staleTime: 60_000,
  })
  const referencesMaquettesQuery = useQuery({
    queryKey: ['ue-ecue', 'references-maquettes'],
    enabled: peutGerer && formulaireMaquette?.mode === 'creation',
    queryFn: async () => {
      const [annees, formations, niveaux] = await Promise.all([
        api.get('/scolarite/ref/annees/', { params: { actif: 'true' } }),
        api.get('/scolarite/ref/formations/'),
        api.get('/scolarite/ref/niveaux/', { params: { actif: 'true' } }),
      ])
      return {
        annees: annees.data || [],
        formations: formations.data || [],
        niveaux: niveaux.data || [],
      }
    },
    staleTime: 10 * 60_000,
  })

  const maquettes = useMemo(() => maquettesQuery.data || [], [maquettesQuery.data])
  const anneeCourante = anneeCouranteQuery.data?.libelle || null
  const maquettesOrdonnees = useMemo(() => {
    const anneeDebut = (libelle) => Number(String(libelle || '').match(/^(\d{4})/)?.[1]) || 0
    return [...maquettes].sort((a, b) => {
      const courantA = a.annee_academique === anneeCourante ? 1 : 0
      const courantB = b.annee_academique === anneeCourante ? 1 : 0
      return courantB - courantA
        || anneeDebut(b.annee_academique) - anneeDebut(a.annee_academique)
        || Number(estMaquetteDemo(a)) - Number(estMaquetteDemo(b))
        || Number(b.statut === 'BROUILLON') - Number(a.statut === 'BROUILLON')
        || (Number(b.version) || 0) - (Number(a.version) || 0)
    })
  }, [maquettes, anneeCourante])
  const maquette = maquettes.find((m) => String(m.id) === String(maquetteId)) || null
  const maquetteEditable = maquette?.statut === 'BROUILLON'
  const maquettesSelectionnees = useMemo(
    () => maquettes.filter((m) => selectionMaquettes.includes(m.id)),
    [maquettes, selectionMaquettes],
  )
  const selectionComplete = maquettes.length > 0
    && maquettes.every((m) => selectionMaquettes.includes(m.id))
  const selectionModifiable = maquettesSelectionnees.length === 1
    && maquettesSelectionnees[0].statut === 'BROUILLON'
  const selectionSupprimable = maquettesSelectionnees.length > 0
    && maquettesSelectionnees.every(
      (m) => m.statut === 'BROUILLON' && Number(m.nb_ue || 0) === 0,
    )

  const famillesQuery = useQuery({
    queryKey: ['ue-ecue', 'familles'],
    queryFn: async () => {
      const res = await api.get('/scolarite/familles/')
      return Array.isArray(res.data) ? res.data : []
    },
    enabled: peutGerer,
    staleTime: 10 * 60_000,
  })
  const familles = famillesQuery.data || []

  const semestresQuery = useQuery({
    queryKey: ['ue-ecue', 'semestres', maquette?.niveau_id],
    enabled: Boolean(maquette?.niveau_id),
    queryFn: async () => {
      const res = await api.get('/scolarite/ref/semestres/', {
        params: { niveau_id: maquette.niveau_id },
      })
      return Array.isArray(res.data) ? res.data : []
    },
    staleTime: 10 * 60_000,
  })
  const semestres = semestresQuery.data || []

  const uesQuery = useQuery({
    queryKey: ['ue-ecue', 'ues', maquetteId],
    enabled: Boolean(maquetteId),
    queryFn: async () => {
      const res = await api.get(`/scolarite/maquettes/${maquetteId}/ues/`)
      return Array.isArray(res.data) ? res.data : []
    },
  })

  const ues = useMemo(() => uesQuery.data || [], [uesQuery.data])
  const uesFiltrees = useMemo(() => {
    const terme = recherche.trim().toLowerCase()
    if (!terme) return ues
    return ues.filter((ue) => `${ue.code} ${ue.intitule}`.toLowerCase().includes(terme))
  }, [ues, recherche])

  const ue = ues.find((u) => Number(u.id) === Number(ueId)) || null
  const nbElementsAActiver = ues.reduce((total, unite) => (
    total
      + Number(unite.statut !== 'ACTIVE')
      + (unite.ecues || []).filter((ecue) => ecue.statut !== 'ACTIVE').length
  ), 0)

  // Synthèse de la maquette sélectionnée, calculée sur les UE déjà chargées.
  const synthese = useMemo(() => {
    const ecues = ues.flatMap((u) => u.ecues || [])
    const volumes = ecues.reduce(
      (acc, e) => ({
        cm: acc.cm + (Number(e.volume_cm) || 0),
        td: acc.td + (Number(e.volume_td) || 0),
        tp: acc.tp + (Number(e.volume_tp) || 0),
      }),
      { cm: 0, td: 0, tp: 0 },
    )
    return {
      nbEcue: ecues.length,
      ects: ues.reduce((s, u) => s + (Number(u.credits) || 0), 0),
      volumes,
      volumeTotal: volumes.cm + volumes.td + volumes.tp,
      semestres: new Set(ues.map((u) => u.semestre?.id).filter(Boolean)).size,
    }
  }, [ues])

  // Choisir d'abord une maquette de l'année courante ; ne jamais ouvrir par
  // défaut une archive plus ancienne simplement parce qu'elle vient en premier.
  useEffect(() => {
    if (!maquetteId && maquettesOrdonnees.length && !anneeCouranteQuery.isLoading) {
      const maquettesPrioritaires = anneeCourante
        ? maquettesOrdonnees.filter((m) => m.annee_academique === anneeCourante)
        : maquettesOrdonnees
      const candidates = maquettesPrioritaires.length ? maquettesPrioritaires : maquettesOrdonnees
      const maquettesOfficielles = candidates.filter((m) => !estMaquetteDemo(m))
      const candidatesParDefaut = maquettesOfficielles.length ? maquettesOfficielles : candidates
      const copieTravail = peutGerer
        ? candidatesParDefaut.find((m) => m.statut === 'BROUILLON')
        : null
      const maquetteDefaut = copieTravail || candidatesParDefaut[0]
      setMaquetteId(String(maquetteDefaut.id))
      setSelectionMaquettes([maquetteDefaut.id])
    }
  }, [anneeCourante, anneeCouranteQuery.isLoading, maquettesOrdonnees, maquetteId, peutGerer])
  useEffect(() => {
    const idsDisponibles = new Set(maquettes.map((m) => m.id))
    setSelectionMaquettes((selection) => selection.filter((id) => idsDisponibles.has(id)))
  }, [maquettes])
  useEffect(() => {
    if (ueId && !ues.some((u) => Number(u.id) === Number(ueId))) setUeId(null)
  }, [ues, ueId])
  useEffect(() => {
    if (!ueId && ues.length) setUeId(ues[0].id)
  }, [ues, ueId])
  useEffect(() => { setUeId(null) }, [maquetteId])
  // La sélection multiple ne survit ni au changement de maquette (UE),
  // ni au changement d'UE sélectionnée (ECUE) : cocher dans un contexte
  // puis agir dans un autre serait un piège.
  useEffect(() => { setSelectionUe([]); setSelectionEcue([]) }, [maquetteId])
  useEffect(() => { setSelectionEcue([]) }, [ueId])

  const rafraichir = () => {
    queryClient.invalidateQueries({ queryKey: ['ue-ecue'] })
  }

  const erreurLisible = (erreur, defaut) => {
    const donnees = erreur?.response?.data
    if (donnees?.error) {
      return Array.isArray(donnees.error) ? donnees.error.join(' ') : String(donnees.error)
    }
    // DRF répond « {"detail": …} » pour un refus de permission : sans ce cas,
    // l'utilisateur lirait « detail : Vous n'avez pas la permission… ».
    if (typeof donnees?.detail === 'string') return donnees.detail
    return messageErreur(erreur, defaut)
  }

  const basculerSelectionMaquette = (id, coche) => {
    setSelectionMaquettes((selection) => (coche
      ? [...new Set([...selection, id])]
      : selection.filter((selectionne) => selectionne !== id)))
  }

  const selectionnerToutesLesMaquettes = (coche) => {
    setSelectionMaquettes(coche ? maquettes.map((m) => m.id) : [])
  }

  const visualiserSelection = () => {
    if (maquettesSelectionnees.length === 1) {
      setMaquetteId(String(maquettesSelectionnees[0].id))
    }
  }

  const ouvrirCreationMaquette = () => {
    setValeursMaquette({
      annee_academique_id: '',
      ref_formation_id: '',
      niveau_id: '',
      libelle: '',
      commentaire_validation: '',
    })
    setFormulaireMaquette({ mode: 'creation', maquette: null })
  }

  const ouvrirEditionMaquette = () => {
    if (!selectionModifiable) return
    const cible = maquettesSelectionnees[0]
    setValeursMaquette({
      annee_academique_id: '',
      ref_formation_id: '',
      niveau_id: '',
      libelle: cible.libelle_personnalise || '',
      commentaire_validation: cible.commentaire_validation || '',
    })
    setFormulaireMaquette({ mode: 'edition', maquette: cible })
  }

  const soumettreMaquette = async (e) => {
    e.preventDefault()
    if (!formulaireMaquette) return
    setMaquetteEnCours(true)
    try {
      if (formulaireMaquette.mode === 'creation') {
        const res = await api.post('/scolarite/maquettes/creer/', {
          annee_academique_id: Number(valeursMaquette.annee_academique_id),
          ref_formation_id: Number(valeursMaquette.ref_formation_id),
          niveau_id: Number(valeursMaquette.niveau_id),
          libelle: valeursMaquette.libelle,
        })
        const idCree = res.data?.id
        showToast(`Maquette v${res.data?.version ?? ''} créée en brouillon.`)
        setFormulaireMaquette(null)
        await queryClient.invalidateQueries({ queryKey: ['ue-ecue', 'maquettes'] })
        if (idCree) {
          setSelectionMaquettes([idCree])
          setMaquetteId(String(idCree))
        }
      } else {
        const cible = formulaireMaquette.maquette
        await api.patch(`/scolarite/maquettes/${cible.id}/modifier/`, {
          libelle: valeursMaquette.libelle,
          commentaire_validation: valeursMaquette.commentaire_validation,
        })
        showToast('Maquette modifiée.')
        setFormulaireMaquette(null)
        await queryClient.invalidateQueries({ queryKey: ['ue-ecue', 'maquettes'] })
      }
    } catch (erreur) {
      showToast(
        erreurLisible(erreur, formulaireMaquette.mode === 'creation'
          ? 'Création de la maquette refusée.' : 'Modification de la maquette refusée.'),
        'error',
      )
    } finally {
      setMaquetteEnCours(false)
    }
  }

  const supprimerSelectionMaquettes = async () => {
    if (!selectionSupprimable || !window.confirm(
      `Supprimer les ${maquettesSelectionnees.length} maquette(s) brouillon sélectionnée(s) sans UE ?`,
    )) return
    setMaquetteEnCours(true)
    const supprimees = []
    const erreurs = []
    for (const cible of maquettesSelectionnees) {
      try {
        await api.delete(`/scolarite/maquettes/${cible.id}/`)
        supprimees.push(cible.id)
      } catch (erreur) {
        erreurs.push(`${cible.ref_formation} : ${erreurLisible(erreur, 'suppression impossible')}`)
      }
    }
    setSelectionMaquettes((selection) => selection.filter((id) => !supprimees.includes(id)))
    if (supprimees.includes(Number(maquetteId))) setMaquetteId('')
    if (erreurs.length) {
      showToast(`${supprimees.length} maquette(s) supprimée(s). ${erreurs.join(' ')}`, 'error')
    } else {
      showToast(`${supprimees.length} maquette(s) supprimée(s).`)
    }
    try {
      await queryClient.invalidateQueries({ queryKey: ['ue-ecue', 'maquettes'] })
    } finally {
      setMaquetteEnCours(false)
    }
  }

  const exporterMaquettes = async (format) => {
    if (!selectionMaquettes.length) return
    setMaquetteEnCours(true)
    const params = new URLSearchParams({ ids: selectionMaquettes.join(',') })
    if (exportDetaille) params.set('detaille', '1')
    try {
      const { blob, fileName } = await api.getBlob(
        `/scolarite/maquettes/export/${format}/?${params.toString()}`,
      )
      downloadFile(blob, fileName || `maquettes.${format === 'word' ? 'docx' : format}`)
      showToast('Export téléchargé.')
    } catch (erreur) {
      showToast(erreurLisible(erreur, 'Export impossible.'), 'error')
    } finally {
      setMaquetteEnCours(false)
    }
  }

  const donneesImportMaquette = (fichier, etape, empreinte) => {
    const donnees = new FormData()
    donnees.append('fichier', fichier)
    donnees.append('etape', etape)
    if (empreinte) donnees.append('empreinte', empreinte)
    return donnees
  }

  const cheminImportMaquette = () =>
    `/scolarite/maquettes/import/${fichierImport?.name.toLowerCase().endsWith('.xlsx') ? 'excel' : 'csv'}/`

  const previsualiserImportMaquette = async () => {
    if (!fichierImport) return
    setImportEnCours(true)
    setApercuImport(null)
    try {
      const res = await api.post(
        cheminImportMaquette(),
        donneesImportMaquette(fichierImport, 'previsualiser'),
      )
      setApercuImport(res.data)
    } catch (erreur) {
      showToast(erreurLisible(erreur, 'Prévisualisation impossible.'), 'error')
    } finally {
      setImportEnCours(false)
    }
  }

  const confirmerImportMaquette = async () => {
    if (!fichierImport || !apercuImport?.valide || !apercuImport.empreinte) return
    setImportEnCours(true)
    try {
      const res = await api.post(
        cheminImportMaquette(),
        donneesImportMaquette(fichierImport, 'confirmer', apercuImport.empreinte),
      )
      showToast(res.data?.detail || 'Import effectué.')
      setFichierImport(null)
      setApercuImport(null)
      const input = document.getElementById('uex-maquette-import')
      if (input) input.value = ''
      await queryClient.invalidateQueries({ queryKey: ['ue-ecue', 'maquettes'] })
    } catch (erreur) {
      showToast(erreurLisible(erreur, 'Import impossible.'), 'error')
    } finally {
      setImportEnCours(false)
    }
  }

  const enregistrer = useMutation({
    mutationFn: async ({ type, corps, creation, cible }) => {
      if (creation) {
        const url = type === 'ue' ? `/scolarite/maquettes/${maquetteId}/ues/` : `/scolarite/ues/${ueId}/ecues/`
        return api.post(url, corps)
      }
      const url = type === 'ue' ? `/scolarite/ues/${cible.id}/` : `/scolarite/ecues/${cible.id}/`
      return api.patch(url, corps)
    },
  })

  const changerStatut = useMutation({
    mutationFn: async ({ type, element, statut }) => {
      const url = type === 'ue'
        ? `/scolarite/ues/${element.id}/statut/`
        : `/scolarite/ecues/${element.id}/statut/`
      return api.post(url, { statut })
    },
  })

  const supprimer = useMutation({
    mutationFn: async ({ type, element }) => {
      const url = type === 'ue' ? `/scolarite/ues/${element.id}/` : `/scolarite/ecues/${element.id}/`
      return api.delete(url)
    },
  })

  // Clonage : seule voie pour modifier le contenu d'une maquette gelée —
  // le clone naît en brouillon (version suivante), l'original reste intact.
  const cloner = useMutation({
    mutationFn: async () => api.post(`/scolarite/maquettes/${maquetteId}/cloner/`),
  })

  const soumettreFormulaire = async (corps, creation) => {
    try {
      await enregistrer.mutateAsync({
        type: formulaire.type,
        corps,
        creation,
        cible: formulaire.element,
      })
      showToast(creation ? 'Élément créé.' : 'Modification enregistrée.')
      rafraichir()
      setFormulaire(null)
      return null
    } catch (erreur) {
      // L'erreur reste dans le formulaire : la saisie n'est pas perdue.
      return erreurLisible(erreur, 'Enregistrement refusé par le serveur.')
    }
  }

  const executerStatut = async (type, element, statut) => {
    try {
      const res = await changerStatut.mutateAsync({ type, element, statut })
      const desactivees = res?.data?.ecues_desactivees || []
      // L'accord se calcule : « 1 ECUE active a été désactivée » n'est pas
      // « 2 ECUE actives ont été désactivées ».
      const cascade = desactivees.length === 0
        ? ''
        : desactivees.length === 1
          ? ' L’ECUE active a été désactivée avec l’UE.'
          : ` ${desactivees.length} ECUE actives ont été désactivées avec l’UE.`;
      showToast(`Statut modifié.${cascade}`)
      rafraichir()
    } catch (erreur) {
      showToast(erreurLisible(erreur, 'Changement de statut refusé.'), 'error')
    }
  }

  const confirmerSuppression = async () => {
    try {
      await supprimer.mutateAsync(suppression)
      showToast('Élément supprimé.')
      rafraichir()
    } catch (erreur) {
      showToast(erreurLisible(erreur, 'Suppression refusée.'), 'error')
    } finally {
      setSuppression(null)
    }
  }

  const executerClonage = async () => {
    try {
      const res = await cloner.mutateAsync()
      const clone = res?.data
      showToast('Version brouillon créée par clonage : son contenu est modifiable.')
      await queryClient.invalidateQueries({ queryKey: ['ue-ecue', 'maquettes'] })
      if (clone?.id) setMaquetteId(String(clone.id))
    } catch (erreur) {
      showToast(erreurLisible(erreur, 'Clonage refusé par le serveur.'), 'error')
    }
  }

  /** Coche/décoche un élément (sélection individuelle). */
  const basculerSelection = (setSelection) => (id, coche) => {
    setSelection((prec) => (coche
      ? [...new Set([...prec, id])]
      : prec.filter((x) => x !== id)))
  }
  const basculerUe = basculerSelection(setSelectionUe)
  const basculerEcue = basculerSelection(setSelectionEcue)

  /**
   * Action de masse sur la sélection : seuls les éléments dont la
   * transition est autorisée sont traités ; les autres sont comptés comme
   * ignorés, les refus serveur comme échecs — le bilan dit tout.
   */
  const executerMasse = async (type, elements, action) => {
    const eligibles = action === 'SUPPRIMER'
      ? elements.filter((el) => el.statut === 'BROUILLON')
      : elements.filter((el) => (TRANSITIONS[el.statut] || []).includes(action))
    let reussis = 0
    let echecs = 0
    for (const element of eligibles) {
      try {
        if (action === 'SUPPRIMER') {
          await supprimer.mutateAsync({ type, element })
        } else {
          await changerStatut.mutateAsync({ type, element, statut: action })
        }
        reussis += 1
      } catch {
        echecs += 1
      }
    }
    const ignores = elements.length - eligibles.length
    const libelleAction = { ACTIVE: 'Activation', DESACTIVEE: 'Désactivation', SUPPRIMER: 'Suppression' }[action]
    const genre = type === 'ue' ? 'UE' : 'ECUE'
    let message = `${libelleAction} groupée : ${reussis} ${genre} traitée${reussis > 1 ? 's' : ''}.`
    if (ignores) message += ` ${ignores} ignorée${ignores > 1 ? 's' : ''} (transition non autorisée).`
    if (echecs) message += ` ${echecs} refusée${echecs > 1 ? 's' : ''} par le serveur.`
    showToast(message, echecs ? 'error' : 'success')
    if (type === 'ue') setSelectionUe([])
    else setSelectionEcue([])
    rafraichir()
  }

  const activerTouteLaMaquette = async () => {
    setActivationTotaleDemandee(false)
    setActivationTotaleEnCours(true)
    let actives = 0
    let refusees = 0
    let ecuesBloqueesParLeurUe = 0

    try {
      // L’API impose l’ordre métier : l’UE doit être ACTIVE avant ses ECUE.
      // Les éléments déjà actifs sont conservés; les autres suivent leur
      // transition explicite et chaque refus est comptabilisé sans interrompre
      // les autres UE de la maquette.
      for (const unite of ues) {
        let ueActive = unite.statut === 'ACTIVE'
        if (!ueActive) {
          try {
            await changerStatut.mutateAsync({ type: 'ue', element: unite, statut: 'ACTIVE' })
            actives += 1
            ueActive = true
          } catch {
            refusees += 1
          }
        }
        if (!ueActive) {
          ecuesBloqueesParLeurUe += (unite.ecues || []).filter((ecue) => ecue.statut !== 'ACTIVE').length
          continue
        }
        for (const ecue of unite.ecues || []) {
          if (ecue.statut === 'ACTIVE') continue
          try {
            await changerStatut.mutateAsync({ type: 'ecue', element: ecue, statut: 'ACTIVE' })
            actives += 1
          } catch {
            refusees += 1
          }
        }
      }

      let bilan = `Activation de la maquette : ${actives} élément${actives > 1 ? 's' : ''} activé${actives > 1 ? 's' : ''} (UE/ECUE).`
      if (refusees) bilan += ` ${refusees} refusée${refusees > 1 ? 's' : ''} par le serveur.`
      if (ecuesBloqueesParLeurUe) {
        bilan += ` ${ecuesBloqueesParLeurUe} ECUE non traitée${ecuesBloqueesParLeurUe > 1 ? 's' : ''} car leur UE n’a pas pu être activée.`
      }
      showToast(bilan, refusees || ecuesBloqueesParLeurUe ? 'error' : 'success')
      rafraichir()
    } finally {
      setActivationTotaleEnCours(false)
    }
  }

  const confirmerSuppressionMasse = async () => {
    const { type, elements } = suppressionMasse
    setSuppressionMasse(null)
    await executerMasse(type, elements, 'SUPPRIMER')
  }

  const chargement = maquettesQuery.isLoading

  return (
    <div className="ecran-generique uex-page" data-testid="ecran-ue-ecue">
      <div className="uex-toolbar">
        <div className="uex-toolbar-head">
          <span className="uex-toolbar-icone" aria-hidden="true">
            <i className="bi bi-diagram-3"></i>
          </span>
          <div>
            <h2>Maquettes</h2>
            <p data-testid="compte-selection-maquettes">
              {selectionMaquettes.length}/{maquettes.length} sélectionnée(s)
            </p>
          </div>
        </div>
        <div className="uex-toolbar-controls">
          <div className="uex-maquettes-zone">
            <section className="uex-maquettes-liste" aria-labelledby="titre-liste-maquettes-uex">
              <div className="uex-maquettes-liste-entete">
                <div>
                  <h3 id="titre-liste-maquettes-uex">Liste des maquettes</h3>
                  <span>{selectionMaquettes.length} sélectionnée(s)</span>
                </div>
                <label className="uex-maquettes-tout">
                  <input
                    type="checkbox"
                    data-testid="tout-cocher-maquettes"
                    aria-label="Sélectionner toutes les maquettes"
                    checked={selectionComplete}
                    onChange={(e) => selectionnerToutesLesMaquettes(e.target.checked)}
                    disabled={chargement || maquettes.length === 0}
                  />
                  Tout sélectionner
                </label>
              </div>
              <div
                className="uex-maquettes-choix"
                role="group"
                aria-label="Maquettes disponibles"
                data-testid="liste-maquettes"
              >
                {maquettesOrdonnees.map((m) => (
                  <label
                    className={`uex-maquette-option${String(m.id) === String(maquetteId) ? ' is-affichee' : ''}`}
                    key={m.id}
                    data-testid={`option-maquette-${m.id}`}
                  >
                    <input
                      type="checkbox"
                      checked={selectionMaquettes.includes(m.id)}
                      aria-label={`Sélectionner la maquette ${estMaquetteDemo(m) ? 'de démonstration ' : ''}${m.ref_formation} ${m.niveau}`}
                      data-testid={`maquette-selection-${m.id}`}
                      onChange={(e) => basculerSelectionMaquette(m.id, e.target.checked)}
                    />
                    <span className="uex-maquette-option-texte">
                      <strong>
                        {estMaquetteDemo(m) ? '[DÉMO] ' : ''}
                        {m.ref_formation} — {m.niveau}
                      </strong>
                      <small>
                        {m.annee_academique} · v{m.version} · {m.statut}
                      </small>
                    </span>
                  </label>
                ))}
                {maquettesQuery.isSuccess && maquettes.length === 0 && (
                  <p className="uex-maquettes-vide" role="status" data-testid="aucune-maquette">
                    Aucune maquette disponible.
                  </p>
                )}
              </div>
            </section>
            <div className="uex-maquettes-actions" aria-label="Actions sur les maquettes">
              {peutGerer && (
                <button
                  type="button"
                  className="btn btn-sm btn-primary"
                  onClick={ouvrirCreationMaquette}
                  disabled={maquetteEnCours}
                  data-testid="creer-maquette"
                >
                  <i className="bi bi-plus-lg me-1" aria-hidden="true"></i>Créer
                </button>
              )}
              <button
                type="button"
                className="btn btn-sm btn-outline-primary"
                onClick={visualiserSelection}
                disabled={maquettesSelectionnees.length !== 1}
                data-testid="visualiser-maquette"
              >
                <i className="bi bi-eye me-1" aria-hidden="true"></i>Visualiser
              </button>
              {peutGerer && (
                <>
                  <button
                    type="button"
                    className="btn btn-sm btn-outline-secondary"
                    onClick={ouvrirEditionMaquette}
                    disabled={!selectionModifiable || maquetteEnCours}
                    title="Modifier une maquette en brouillon sélectionnée"
                    data-testid="modifier-maquette"
                  >
                    <i className="bi bi-pencil me-1" aria-hidden="true"></i>Modifier
                  </button>
                  <button
                    type="button"
                    className="btn btn-sm btn-outline-danger"
                    onClick={supprimerSelectionMaquettes}
                    disabled={!selectionSupprimable || maquetteEnCours}
                    title="Seules les maquettes brouillon sans UE peuvent être supprimées"
                    data-testid="supprimer-maquette"
                  >
                    <i className="bi bi-trash me-1" aria-hidden="true"></i>Supprimer
                  </button>
                </>
              )}
            </div>
          </div>

          {peutGerer && (
            <div className="uex-maquettes-fichiers">
              <div className="uex-maquettes-export">
                <div className="uex-maquettes-outil-entete">
                  <strong>Exporter la sélection</strong>
                  <label>
                    <input
                      type="checkbox"
                      checked={exportDetaille}
                      onChange={(e) => setExportDetaille(e.target.checked)}
                      data-testid="export-maquettes-detaille"
                    />
                    Inclure les UE/ECUE
                  </label>
                </div>
                <div className="uex-maquettes-boutons">
                  {[
                    ['word', 'Word', 'bi-file-earmark-word'],
                    ['pdf', 'PDF', 'bi-file-earmark-pdf'],
                    ['excel', 'Excel', 'bi-file-earmark-excel'],
                    ['csv', 'CSV', 'bi-filetype-csv'],
                  ].map(([format, libelle, icone]) => (
                    <button
                      type="button"
                      className="btn btn-sm btn-outline-primary"
                      key={format}
                      disabled={!selectionMaquettes.length || maquetteEnCours}
                      onClick={() => exporterMaquettes(format)}
                      data-testid={`export-maquettes-${format}`}
                    >
                      <i className={`bi ${icone} me-1`} aria-hidden="true"></i>{libelle}
                    </button>
                  ))}
                </div>
              </div>
              <div className="uex-maquettes-import">
                <label htmlFor="uex-maquette-import">Importer une liste (Excel ou CSV)</label>
                <div className="uex-maquettes-import-actions">
                  <input
                    id="uex-maquette-import"
                    type="file"
                    accept=".xlsx,.csv"
                    onChange={(e) => {
                      setFichierImport(e.target.files?.[0] || null)
                      setApercuImport(null)
                    }}
                    data-testid="fichier-import-maquettes"
                  />
                  <button
                    type="button"
                    className="btn btn-sm btn-outline-secondary"
                    disabled={!fichierImport || importEnCours}
                    onClick={previsualiserImportMaquette}
                    data-testid="previsualiser-import-maquettes"
                  >
                    <i className="bi bi-search me-1" aria-hidden="true"></i>
                    {importEnCours ? 'Vérification…' : 'Prévisualiser'}
                  </button>
                </div>
                <small>
                  Le fichier est vérifié avant toute création; l’import confirmé crée des brouillons.
                </small>
                {apercuImport && (
                  <div
                    className={`uex-maquettes-apercu${apercuImport.valide ? ' is-valide' : ' is-invalide'}`}
                    aria-live="polite"
                    data-testid="apercu-import-maquettes"
                  >
                    {apercuImport.valide ? (
                      <>
                        <strong>
                          Aperçu valide : {apercuImport.maquettes} maquette(s), {apercuImport.ues} UE et {apercuImport.ecues} ECUE.
                        </strong>
                        {apercuImport.erreurs?.length > 0 && (
                          <ul>{apercuImport.erreurs.map((message, index) => <li key={`${index}-${message}`}>{message}</li>)}</ul>
                        )}
                        {apercuImport.avertissements?.length > 0 && (
                          <ul>{apercuImport.avertissements.map((message, index) => <li key={`${index}-${message}`}>{message}</li>)}</ul>
                        )}
                        <button
                          type="button"
                          className="btn btn-sm btn-success"
                          disabled={importEnCours || apercuImport.deja_importe}
                          onClick={confirmerImportMaquette}
                          data-testid="confirmer-import-maquettes"
                        >
                          Confirmer l’import
                        </button>
                      </>
                    ) : (
                      <>
                        <strong>Le fichier contient des erreurs et ne peut pas être importé.</strong>
                        <ul>{(apercuImport.erreurs || []).map((message, index) => <li key={`${index}-${message}`}>{message}</li>)}</ul>
                      </>
                    )}
                  </div>
                )}
              </div>
            </div>
          )}

          {maquette && (
            <span
              className={`ue-ecue-etat uex-etat uex-etat--${String(maquette.statut || '').toLowerCase()}`}
              data-testid="etat-maquette"
            >
              <i className="bi bi-lock-fill" aria-hidden="true"></i>
              {STATUT_MAQUETTE[maquette.statut] || maquette.statut}
            </span>
          )}
          {maquette && (
            <span className="uex-maquette-affichee" data-testid="maquette-affichee">
              Affichée : {maquette.ref_formation} — {maquette.niveau} — {maquette.annee_academique} (v{maquette.version})
            </span>
          )}
          {maquette && !maquetteEditable && peutGerer && (
            <button
              type="button"
              className="btn btn-warning uex-btn-edition"
              onClick={executerClonage}
              disabled={cloner.isPending}
              data-testid="cloner-maquette-barre"
            >
              <i className="bi bi-pencil-square me-1" aria-hidden="true"></i>
              {cloner.isPending ? 'Clonage…' : 'Passer en mode édition (cloner)'}
            </button>
          )}
          {maquette && (
            <div className="uex-meta">
              <span><i className="bi bi-mortarboard"></i>{maquette.ref_formation}</span>
              <span><i className="bi bi-layers"></i>Niveau {maquette.niveau}</span>
              <span><i className="bi bi-calendar3"></i>{maquette.annee_academique}</span>
              <span><i className="bi bi-git"></i>Version {maquette.version}</span>
              {estMaquetteDemo(maquette) && (
                <span className="badge text-bg-warning" data-testid="badge-maquette-demo">
                  Données de démonstration — non officielles
                </span>
              )}
            </div>
          )}
        </div>
      </div>

      {maquette && !uesQuery.isLoading && (
        <div className="uex-kpis">
          <div className="uex-kpi">
            <span className="uex-kpi-icone is-blue"><i className="bi bi-collection"></i></span>
            <div><strong>{ues.length}</strong><span>unités d’enseignement</span></div>
          </div>
          <div className="uex-kpi">
            <span className="uex-kpi-icone is-indigo"><i className="bi bi-list-check"></i></span>
            <div><strong>{synthese.nbEcue}</strong><span>ECUE au total</span></div>
          </div>
          <div className="uex-kpi">
            <span className="uex-kpi-icone is-cyan"><i className="bi bi-award"></i></span>
            <div><strong>{synthese.ects}</strong><span>crédits ECTS</span></div>
          </div>
          <div className="uex-kpi uex-kpi--volumes">
            <div className="uex-kpi-volumes-tete">
              <span className="uex-kpi-icone is-amber"><i className="bi bi-clock-history"></i></span>
              <div><strong>{synthese.volumeTotal} h</strong><span>volume horaire (CM {synthese.volumes.cm} · TD {synthese.volumes.td} · TP {synthese.volumes.tp})</span></div>
            </div>
            {synthese.volumeTotal > 0 && (
              <span className="uex-volumes-barre uex-volumes-barre--kpi" role="img" aria-label="Répartition des volumes de la maquette">
                <span className="uex-volumes-seg is-cm" style={{ width: `${(synthese.volumes.cm / synthese.volumeTotal) * 100}%` }}></span>
                <span className="uex-volumes-seg is-td" style={{ width: `${(synthese.volumes.td / synthese.volumeTotal) * 100}%` }}></span>
                <span className="uex-volumes-seg is-tp" style={{ width: `${(synthese.volumes.tp / synthese.volumeTotal) * 100}%` }}></span>
              </span>
            )}
          </div>
        </div>
      )}
      {maquette && synthese.volumeTotal > 0 && (
        <div className="uex-alerte" role="note" data-testid="volumes-a-confirmer">
          <i className="bi bi-exclamation-triangle" aria-hidden="true"></i>
          <span>
            La source officielle disponible ne documente pas la répartition CM/TD/TP.
            La provenance des volumes affichés reste à confirmer avant de les considérer comme officiels.
          </span>
        </div>
      )}

      {maquettesQuery.isError && (
        <div className="alert alert-danger py-2" role="alert" data-testid="erreur-maquettes">
          Impossible de charger les maquettes : {erreurLisible(maquettesQuery.error, 'accès refusé.')}
        </div>
      )}

      {maquette && !maquetteEditable && (
        <div className="uex-alerte" role="status" data-testid="maquette-verrouillee">
          <i className="bi bi-lock-fill" aria-hidden="true"></i>
          <span>
            Cette maquette est <strong>{STATUT_MAQUETTE[maquette.statut]?.toLowerCase()}</strong> :
            son contenu ne peut plus être modifié. Créez une nouvelle version (clonage) pour
            faire évoluer le programme.
          </span>
          {peutGerer && (
            <button
              type="button"
              className="btn btn-sm btn-warning uex-btn-cloner"
              onClick={executerClonage}
              disabled={cloner.isPending}
              data-testid="cloner-maquette"
            >
              <i className="bi bi-copy me-1" aria-hidden="true"></i>
              {cloner.isPending ? 'Clonage…' : 'Créer une version brouillon (cloner)'}
            </button>
          )}
        </div>
      )}

      <div className="ue-ecue-colonnes">
        {/* ── Niveau 2 : les UE de la maquette ─────────────────────────── */}
        <div className="ue-ecue-panneau">
          <div className="gen-panel uex-panel">
            <div className="gen-panel-head">
              <h2 className="gen-panel-title">
                <i className="bi bi-collection"></i>
                Unités d’enseignement
              </h2>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <span className="gen-count-pill">
                  {uesQuery.isLoading ? 'Chargement…' : `${uesFiltrees.length} UE`}
                </span>
                {peutGerer && maquetteEditable && nbElementsAActiver > 0 && (
                  <button
                    type="button"
                    className="btn btn-sm btn-outline-success"
                    onClick={() => setActivationTotaleDemandee(true)}
                    disabled={activationTotaleEnCours || changerStatut.isPending}
                    data-testid="activer-toute-maquette"
                    title={`Activer ${nbElementsAActiver} UE/ECUE de la maquette affichée`}
                  >
                    <i className="bi bi-check2-all me-1" aria-hidden="true"></i>
                    {activationTotaleEnCours ? 'Activation…' : 'Tout activer'}
                  </button>
                )}
                {peutGerer && maquetteEditable && (
                  <button
                    type="button"
                    className="btn btn-sm btn-primary"
                    onClick={() => setFormulaire({ type: 'ue', element: null })}
                    disabled={!maquetteId}
                    data-testid="nouvelle-ue"
                  >
                    <i className="bi bi-plus-lg me-1"></i>Nouvelle UE
                  </button>
                )}
              </div>
            </div>
            {peutGerer && maquetteEditable && selectionUe.length > 0 && (
              <div className="uex-bulkbar" data-testid="barre-actions-ue">
                <span className="uex-bulkbar-compte">
                  <i className="bi bi-check2-square" aria-hidden="true"></i>
                  {selectionUe.length} UE sélectionnée{selectionUe.length > 1 ? 's' : ''}
                </span>
                <div className="uex-bulkbar-actions">
                  <button
                    type="button" className="btn btn-sm btn-success"
                    disabled={changerStatut.isPending || supprimer.isPending}
                    onClick={() => executerMasse('ue', ues.filter((u) => selectionUe.includes(u.id)), 'ACTIVE')}
                    data-testid="masse-ue-activer"
                  >
                    <i className="bi bi-check-circle me-1" aria-hidden="true"></i>Activer
                  </button>
                  <button
                    type="button" className="btn btn-sm btn-warning"
                    disabled={changerStatut.isPending || supprimer.isPending}
                    onClick={() => executerMasse('ue', ues.filter((u) => selectionUe.includes(u.id)), 'DESACTIVEE')}
                    data-testid="masse-ue-desactiver"
                  >
                    <i className="bi bi-pause-circle me-1" aria-hidden="true"></i>Désactiver
                  </button>
                  <button
                    type="button" className="btn btn-sm btn-danger"
                    disabled={changerStatut.isPending || supprimer.isPending}
                    onClick={() => setSuppressionMasse({
                      type: 'ue',
                      elements: ues.filter((u) => selectionUe.includes(u.id)),
                    })}
                    data-testid="masse-ue-supprimer"
                  >
                    <i className="bi bi-trash me-1" aria-hidden="true"></i>Supprimer
                  </button>
                  <button
                    type="button" className="btn btn-sm btn-outline-secondary"
                    onClick={() => setSelectionUe([])}
                    data-testid="masse-ue-effacer"
                  >
                    Tout désélectionner
                  </button>
                </div>
              </div>
            )}
            <div className="uex-recherche-ligne">
              <label htmlFor="recherche-ue">Rechercher une UE</label>
              <span className="uex-recherche">
                <i className="bi bi-search" aria-hidden="true"></i>
                <input
                  id="recherche-ue"
                  type="search"
                  className="form-control form-control-sm"
                  placeholder="Code ou intitulé…"
                  value={recherche}
                  onChange={(e) => setRecherche(e.target.value)}
                  data-testid="recherche-ue"
                />
              </span>
            </div>
            <div className="table-responsive gen-table-wrap">
              <table className="table table-sm table-hover align-middle mb-0 gen-table">
                <thead>
                  <tr>
                    {peutGerer && (
                      <th scope="col" className="uex-col-check">
                        <input
                          type="checkbox"
                          className="uex-check"
                          disabled={!maquetteEditable}
                          title={maquetteEditable ? 'Tout cocher ou décocher les UE affichées' : 'Maquette gelée : clonez-la en version brouillon pour sélectionner et modifier'}
                          aria-label="Tout cocher ou décocher les UE affichées"
                          data-testid="tout-cocher-ue"
                          checked={uesFiltrees.length > 0 && uesFiltrees.every((u) => selectionUe.includes(u.id))}
                          ref={(el) => {
                            if (el) {
                              el.indeterminate = uesFiltrees.some((u) => selectionUe.includes(u.id))
                                && !uesFiltrees.every((u) => selectionUe.includes(u.id))
                            }
                          }}
                          onChange={(e) => {
                            setSelectionUe((prec) => (e.target.checked
                              ? [...new Set([...prec, ...uesFiltrees.map((u) => u.id)])]
                              : prec.filter((id) => !uesFiltrees.some((u) => u.id === id))))
                          }}
                        />
                      </th>
                    )}
                    <th scope="col">Code</th>
                    <th scope="col">Intitulé</th>
                    <th scope="col">Sem.</th>
                    <th scope="col">ECTS</th>
                    <th scope="col">Statut</th>
                    <th scope="col" className="text-end">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {uesFiltrees.map((ligne, index) => (
                    <tr
                      key={ligne.id}
                      className={`uex-ligne${Number(ligne.id) === Number(ueId) ? ' table-active uex-ligne--active' : ''}`}
                      onClick={() => setUeId(ligne.id)}
                      style={{ cursor: 'pointer', animationDelay: `${Math.min(index * 40, 400)}ms` }}
                      data-testid={`ligne-ue-${ligne.id}`}
                    >
                      {peutGerer && (
                        <td onClick={(e) => e.stopPropagation()}>
                          <input
                            type="checkbox"
                            className="uex-check"
                            disabled={!maquetteEditable}
                            title={maquetteEditable ? `Sélectionner l’UE ${ligne.code}` : 'Maquette gelée : clonez-la en version brouillon pour sélectionner et modifier'}
                            aria-label={`Sélectionner l’UE ${ligne.code}`}
                            data-testid={`cocher-ue-${ligne.id}`}
                            checked={selectionUe.includes(ligne.id)}
                            onChange={(e) => basculerUe(ligne.id, e.target.checked)}
                          />
                        </td>
                      )}
                      <td>
                        {/* Seul contrôle focusable de la ligne : au clavier,
                            c'est le code qui « ouvre » l'UE. */}
                        <button
                          type="button"
                          className="ue-ecue-choix"
                          onClick={(e) => { e.stopPropagation(); setUeId(ligne.id) }}
                          aria-pressed={Number(ligne.id) === Number(ueId)}
                          aria-label={`Afficher les ECUE de l’UE ${ligne.code}`}
                          data-testid={`selectionner-ue-${ligne.id}`}
                        >
                          <span className="gen-code-chip">{ligne.code}</span>
                        </button>
                      </td>
                      <td className="uex-intitule">{ligne.intitule}</td>
                      <td>
                        {ligne.semestre?.libelle
                          ? <span className="uex-sem">{ligne.semestre.libelle}</span>
                          : '—'}
                      </td>
                      <td><span className="uex-ects">{afficherValeur(ligne.credits)}</span></td>
                      <td><BadgeStatut statut={ligne.statut} /></td>
                      <td onClick={(e) => e.stopPropagation()}>
                        <div className="ue-ecue-actions">
                          {peutGerer && maquetteEditable && ligne.statut === 'BROUILLON' && (
                            <>
                              <button
                                type="button"
                                className="btn btn-sm btn-outline-primary"
                                title="Modifier l’UE"
                                aria-label={`Modifier l’UE ${ligne.code}`}
                                onClick={() => setFormulaire({ type: 'ue', element: ligne })}
                                data-testid={`modifier-ue-${ligne.id}`}
                              >
                                <i className="bi bi-pencil" aria-hidden="true"></i>
                              </button>
                              <button
                                type="button"
                                className="btn btn-sm btn-outline-danger"
                                title="Supprimer l’UE"
                                aria-label={`Supprimer l’UE ${ligne.code}`}
                                onClick={() => setSuppression({ type: 'ue', element: ligne })}
                                data-testid={`supprimer-ue-${ligne.id}`}
                              >
                                <i className="bi bi-trash" aria-hidden="true"></i>
                              </button>
                            </>
                          )}
                          {peutGerer && maquetteEditable && (
                            <ActionsStatut
                              element={ligne}
                              type="ue"
                              enCours={changerStatut.isPending}
                              onChanger={(el, statut) => executerStatut('ue', el, statut)}
                            />
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                  {!uesQuery.isLoading && uesFiltrees.length === 0 && (
                    <tr>
                      <td colSpan={peutGerer ? 7 : 6}>
                        <div className="gen-empty">
                          <i className="bi bi-inbox" aria-hidden="true"></i>
                          <span className="gen-empty-title">
                            {maquetteId ? 'Aucune UE' : 'Choisissez une maquette'}
                          </span>
                          <span className="gen-empty-text">
                            {maquetteId
                              ? 'Cette maquette ne contient encore aucune unité d’enseignement.'
                              : 'Sélectionnez la maquette dont vous voulez gérer le contenu.'}
                          </span>
                        </div>
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
            <div className="gen-panel-foot uex-foot">
              <span className="gen-panel-foot-info">
                <i className="bi bi-info-circle"></i>
                {ues.length} UE · {synthese.nbEcue} ECUE · {synthese.ects} ECTS · {synthese.volumeTotal} h de cours
              </span>
            </div>
          </div>
        </div>

        {/* ── Niveau 3 : les ECUE de l'UE sélectionnée ─────────────────── */}
        <div className="ue-ecue-panneau">
          <div className="gen-panel uex-panel">
            <div className="gen-panel-head">
              <h2 className="gen-panel-title">
                <i className="bi bi-list-check"></i>
                ECUE {ue ? `— ${ue.code}` : ''}
              </h2>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                {peutGerer && ue && ue.ecues.length > 0 && (
                  <label className="uex-tout-cocher">
                    <input
                      type="checkbox"
                      className="uex-check"
                      disabled={!maquetteEditable}
                      title={maquetteEditable ? 'Tout cocher ou décocher les ECUE affichés' : 'Maquette gelée : clonez-la en version brouillon pour sélectionner et modifier'}
                      aria-label="Tout cocher ou décocher les ECUE affichés"
                      data-testid="tout-cocher-ecue"
                      checked={ue.ecues.every((e) => selectionEcue.includes(e.id))}
                      ref={(el) => {
                        if (el) {
                          el.indeterminate = ue.ecues.some((e) => selectionEcue.includes(e.id))
                            && !ue.ecues.every((e) => selectionEcue.includes(e.id))
                        }
                      }}
                      onChange={(e) => {
                        setSelectionEcue(e.target.checked ? ue.ecues.map((x) => x.id) : [])
                      }}
                    />
                    Tout cocher
                  </label>
                )}
                <span className="gen-count-pill">
                  {ue ? `${ue.ecues.length} ECUE` : 'Aucune UE sélectionnée'}
                </span>
                {peutGerer && maquetteEditable && ue && (
                  <button
                    type="button"
                    className="btn btn-sm btn-primary"
                    onClick={() => setFormulaire({ type: 'ecue', element: null })}
                    data-testid="nouvel-ecue"
                  >
                    <i className="bi bi-plus-lg me-1"></i>Nouvel ECUE
                  </button>
                )}
              </div>
            </div>
            {peutGerer && maquetteEditable && ue && selectionEcue.length > 0 && (
              <div className="uex-bulkbar" data-testid="barre-actions-ecue">
                <span className="uex-bulkbar-compte">
                  <i className="bi bi-check2-square" aria-hidden="true"></i>
                  {selectionEcue.length} ECUE sélectionnée{selectionEcue.length > 1 ? 's' : ''}
                </span>
                <div className="uex-bulkbar-actions">
                  <button
                    type="button" className="btn btn-sm btn-success"
                    disabled={changerStatut.isPending || supprimer.isPending}
                    onClick={() => executerMasse('ecue', ue.ecues.filter((e) => selectionEcue.includes(e.id)), 'ACTIVE')}
                    data-testid="masse-ecue-activer"
                  >
                    <i className="bi bi-check-circle me-1" aria-hidden="true"></i>Activer
                  </button>
                  <button
                    type="button" className="btn btn-sm btn-warning"
                    disabled={changerStatut.isPending || supprimer.isPending}
                    onClick={() => executerMasse('ecue', ue.ecues.filter((e) => selectionEcue.includes(e.id)), 'DESACTIVEE')}
                    data-testid="masse-ecue-desactiver"
                  >
                    <i className="bi bi-pause-circle me-1" aria-hidden="true"></i>Désactiver
                  </button>
                  <button
                    type="button" className="btn btn-sm btn-danger"
                    disabled={changerStatut.isPending || supprimer.isPending}
                    onClick={() => setSuppressionMasse({
                      type: 'ecue',
                      elements: ue.ecues.filter((e) => selectionEcue.includes(e.id)),
                    })}
                    data-testid="masse-ecue-supprimer"
                  >
                    <i className="bi bi-trash me-1" aria-hidden="true"></i>Supprimer
                  </button>
                  <button
                    type="button" className="btn btn-sm btn-outline-secondary"
                    onClick={() => setSelectionEcue([])}
                    data-testid="masse-ecue-effacer"
                  >
                    Tout désélectionner
                  </button>
                </div>
              </div>
            )}
            {ue && ue.ecues.length > 0 && (
              <div className="uex-legende-volumes" aria-hidden="true">
                <span><i className="uex-pastille is-cm"></i>Cours magistraux</span>
                <span><i className="uex-pastille is-td"></i>Travaux dirigés</span>
                <span><i className="uex-pastille is-tp"></i>Travaux pratiques</span>
              </div>
            )}
            <div className="uex-ecue-grille" key={ue?.id || 'aucune'}>
              {(ue?.ecues || []).map((ecue, index) => (
                <article
                  key={ecue.id}
                  className="uex-ecue-carte"
                  style={{ animationDelay: `${Math.min(index * 60, 360)}ms` }}
                  data-testid={`ligne-ecue-${ecue.id}`}
                >
                  <header className="uex-ecue-entete">
                    {peutGerer && (
                      <input
                        type="checkbox"
                        className="uex-check"
                        disabled={!maquetteEditable}
                        title={maquetteEditable ? `Sélectionner l’ECUE ${ecue.code}` : 'Maquette gelée : clonez-la en version brouillon pour sélectionner et modifier'}
                        aria-label={`Sélectionner l’ECUE ${ecue.code}`}
                        data-testid={`cocher-ecue-${ecue.id}`}
                        checked={selectionEcue.includes(ecue.id)}
                        onChange={(e) => basculerEcue(ecue.id, e.target.checked)}
                      />
                    )}
                    <span className="gen-code-chip">{ecue.code}</span>
                    <BadgeStatut statut={ecue.statut} />
                  </header>
                  <h3 className="uex-ecue-intitule">{ecue.intitule}</h3>
                  <div className="uex-ecue-volumes">
                    <BarreVolumes ecue={ecue} />
                  </div>
                  <footer className="uex-ecue-pied">
                    <span className="uex-ects" title="Crédits ECTS">{afficherValeur(ecue.credits)} ECTS</span>
                    <div className="ue-ecue-actions">
                          {peutGerer && maquetteEditable && ecue.statut === 'BROUILLON' && (
                            <>
                              <button
                                type="button"
                                className="btn btn-sm btn-outline-primary"
                                title="Modifier l’ECUE"
                                aria-label={`Modifier l’ECUE ${ecue.code}`}
                                onClick={() => setFormulaire({ type: 'ecue', element: ecue })}
                                data-testid={`modifier-ecue-${ecue.id}`}
                              >
                                <i className="bi bi-pencil" aria-hidden="true"></i>
                              </button>
                              <button
                                type="button"
                                className="btn btn-sm btn-outline-danger"
                                title="Supprimer l’ECUE"
                                aria-label={`Supprimer l’ECUE ${ecue.code}`}
                                onClick={() => setSuppression({ type: 'ecue', element: ecue })}
                                data-testid={`supprimer-ecue-${ecue.id}`}
                              >
                                <i className="bi bi-trash" aria-hidden="true"></i>
                              </button>
                            </>
                          )}
                          {peutGerer && maquetteEditable && (
                            <ActionsStatut
                              element={ecue}
                              type="ecue"
                              enCours={changerStatut.isPending}
                              onChanger={(el, statut) => executerStatut('ecue', el, statut)}
                            />
                          )}
                    </div>
                  </footer>
                </article>
              ))}
              {(!ue || ue.ecues.length === 0) && (
                <div className="gen-empty uex-vide">
                  <i className="bi bi-inbox" aria-hidden="true"></i>
                  <span className="gen-empty-title">Aucun ECUE</span>
                  <span className="gen-empty-text">
                    {ue
                      ? 'Sélectionnez « Nouvel ECUE » pour ajouter le premier élément constitutif.'
                      : 'Sélectionnez une UE à gauche pour voir ses éléments constitutifs.'}
                  </span>
                </div>
              )}
            </div>
            <div className="gen-panel-foot">
              <span className="gen-panel-foot-info">
                <i className="bi bi-info-circle"></i>
                <span className="ue-ecue-legende">
                  « — » : valeur non publiée par la source officielle. Les crédits
                  sont documentés au niveau de l’UE, pas de l’ECUE ; les volumes CM/TD/TP
                  présents restent à confirmer. Aucun zéro n’est inventé.
                </span>
              </span>
            </div>
          </div>
        </div>
      </div>

      {formulaire && (
        <FormulaireElement
          type={formulaire.type}
          initial={formulaire.element}
          semestres={semestres}
          familles={familles}
          enCours={enregistrer.isPending}
          onFermer={() => setFormulaire(null)}
          onValider={soumettreFormulaire}
        />
      )}

      {formulaireMaquette && (
        <div className="uex-maquette-modal-fond" role="presentation">
          <section
            className="uex-maquette-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="titre-formulaire-maquette"
            data-testid="formulaire-maquette"
          >
            <header>
              <h2 id="titre-formulaire-maquette">
                {formulaireMaquette.mode === 'creation' ? 'Créer une maquette' : 'Modifier la maquette'}
              </h2>
              <button
                type="button"
                className="btn btn-sm btn-outline-secondary"
                aria-label="Fermer"
                onClick={() => setFormulaireMaquette(null)}
              >
                <i className="bi bi-x-lg" aria-hidden="true"></i>
              </button>
            </header>
            {formulaireMaquette.mode === 'creation' && referencesMaquettesQuery.isLoading && (
              <p role="status">Chargement des référentiels…</p>
            )}
            {formulaireMaquette.mode === 'creation' && referencesMaquettesQuery.isError && (
              <p className="alert alert-danger" role="alert">
                Impossible de charger les référentiels : {erreurLisible(referencesMaquettesQuery.error, 'accès refusé.')}
              </p>
            )}
            <form onSubmit={soumettreMaquette}>
              {formulaireMaquette.mode === 'creation' ? (
                <>
                  <label htmlFor="uex-maquette-annee">Année académique *</label>
                  <select
                    id="uex-maquette-annee"
                    required
                    value={valeursMaquette.annee_academique_id}
                    onChange={(e) => setValeursMaquette({ ...valeursMaquette, annee_academique_id: e.target.value })}
                    data-testid="annee-maquette"
                  >
                    <option value="">Choisir une année</option>
                    {(referencesMaquettesQuery.data?.annees || []).map((annee) => (
                      <option key={annee.id} value={annee.id}>{annee.libelle}</option>
                    ))}
                  </select>
                  <label htmlFor="uex-maquette-formation">Formation *</label>
                  <select
                    id="uex-maquette-formation"
                    required
                    value={valeursMaquette.ref_formation_id}
                    onChange={(e) => setValeursMaquette({ ...valeursMaquette, ref_formation_id: e.target.value })}
                    data-testid="formation-maquette"
                  >
                    <option value="">Choisir une formation</option>
                    {(referencesMaquettesQuery.data?.formations || []).map((formation) => (
                      <option key={formation.id} value={formation.id}>{formation.intitule}</option>
                    ))}
                  </select>
                  <label htmlFor="uex-maquette-niveau">Niveau *</label>
                  <select
                    id="uex-maquette-niveau"
                    required
                    value={valeursMaquette.niveau_id}
                    onChange={(e) => setValeursMaquette({ ...valeursMaquette, niveau_id: e.target.value })}
                    data-testid="niveau-maquette"
                  >
                    <option value="">Choisir un niveau</option>
                    {(referencesMaquettesQuery.data?.niveaux || []).map((niveau) => (
                      <option key={niveau.id} value={niveau.id}>{niveau.code}</option>
                    ))}
                  </select>
                </>
              ) : null}
              <label htmlFor="uex-maquette-libelle">
                {formulaireMaquette.mode === 'creation' ? 'Libellé (facultatif)' : 'Libellé personnalisé'}
              </label>
              <input
                id="uex-maquette-libelle"
                value={valeursMaquette.libelle}
                onChange={(e) => setValeursMaquette({ ...valeursMaquette, libelle: e.target.value })}
                data-testid="libelle-maquette"
              />
              {formulaireMaquette.mode === 'edition' && (
                <>
                  <label htmlFor="uex-maquette-commentaire">Commentaire</label>
                  <textarea
                    id="uex-maquette-commentaire"
                    rows="3"
                    value={valeursMaquette.commentaire_validation}
                    onChange={(e) => setValeursMaquette({
                      ...valeursMaquette,
                      commentaire_validation: e.target.value,
                    })}
                    data-testid="commentaire-maquette"
                  />
                </>
              )}
              <footer>
                <button
                  type="button"
                  className="btn btn-sm btn-outline-secondary"
                  onClick={() => setFormulaireMaquette(null)}
                >
                  Annuler
                </button>
                <button
                  type="submit"
                  className="btn btn-sm btn-primary"
                  disabled={
                    maquetteEnCours
                    || (formulaireMaquette.mode === 'creation' && referencesMaquettesQuery.isError)
                  }
                  data-testid="enregistrer-maquette"
                >
                  {maquetteEnCours ? 'Enregistrement…' : 'Enregistrer'}
                </button>
              </footer>
            </form>
          </section>
        </div>
      )}

      {activationTotaleDemandee && (
        <ConfirmModal
          message={`Activer toutes les UE et tous les ECUE de la maquette ${maquette?.ref_formation || 'affichée'} — ${maquette?.niveau || ''} ?`}
          detail={`${nbElementsAActiver} UE/ECUE à activer. Chaque UE sera activée avant ses ECUE; les statuts et le journal métier seront mis à jour. Les éléments déjà actifs ne seront pas modifiés.`}
          confirmLabel="Activer toutes les UE et ECUE"
          variant="success"
          onConfirm={activerTouteLaMaquette}
          onCancel={() => setActivationTotaleDemandee(false)}
        />
      )}

      {suppression && (
        <ConfirmModal
          message={`Supprimer ${suppression.type === 'ue' ? 'l’UE' : 'l’ECUE'} ${suppression.element.code} ?`}
          detail={
            suppression.type === 'ue'
              ? 'La suppression est refusée si l’UE porte encore des ECUE ou si elle n’est pas en brouillon : aucune suppression en cascade n’est effectuée.'
              : 'La suppression est refusée si l’ECUE n’est pas en brouillon.'
          }
          confirmLabel="Supprimer"
          onConfirm={confirmerSuppression}
          onCancel={() => setSuppression(null)}
        />
      )}

      {suppressionMasse && (
        <ConfirmModal
          message={`Supprimer les ${suppressionMasse.elements.length} ${suppressionMasse.type === 'ue' ? 'UE' : 'ECUE'} sélectionnée${suppressionMasse.elements.length > 1 ? 's' : ''} ?`}
          detail={
            suppressionMasse.type === 'ue'
              ? 'Seuls les éléments en brouillon sans dépendance sont supprimés : le serveur refuse les autres et le bilan final le signalera. Aucune suppression en cascade n’est effectuée.'
              : 'Seuls les ECUE en brouillon sont supprimés : le serveur refuse les autres et le bilan final le signalera.'
          }
          confirmLabel="Supprimer la sélection"
          onConfirm={confirmerSuppressionMasse}
          onCancel={() => setSuppressionMasse(null)}
        />
      )}
    </div>
  )
}
