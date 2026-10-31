import { useEffect, useMemo, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../services/api'
import { messageErreur } from '../services/scolarite'
import { useToast } from '../context/ToastContext'
import { useAuth } from '../context/AuthContext'
import ConfirmModal from '../components/ConfirmModal'
import { ADMIN_LEVEL_ROLES } from '../utils/roles'
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

function BadgeStatut({ statut }) {
  const definition = STATUTS.find((s) => s.valeur === statut) || {
    libelle: statut || '—', classe: 'text-bg-light',
  }
  return (
    <span className={`badge ${definition.classe}`} data-testid={`statut-${statut}`}>
      {definition.libelle}
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
 * La base stocke donc 0, ce qui ne veut pas dire « zéro crédit » mais « non
 * documenté ». On affiche « — » et une légende l'explique : un 0 affiché
 * serait une donnée inventée, exactement ce qu'il faut éviter.
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
  const [ueId, setUeId] = useState(null)
  const [formulaire, setFormulaire] = useState(null)
  const [suppression, setSuppression] = useState(null)
  const [recherche, setRecherche] = useState('')

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

  const maquettes = useMemo(() => maquettesQuery.data || [], [maquettesQuery.data])
  const maquette = maquettes.find((m) => String(m.id) === String(maquetteId)) || null
  const maquetteEditable = maquette?.statut === 'BROUILLON'

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

  // Sélection par défaut : la première maquette, puis sa première UE.
  useEffect(() => {
    if (!maquetteId && maquettes.length) setMaquetteId(String(maquettes[0].id))
  }, [maquettes, maquetteId])
  useEffect(() => {
    if (ueId && !ues.some((u) => Number(u.id) === Number(ueId))) setUeId(null)
  }, [ues, ueId])
  useEffect(() => {
    if (!ueId && ues.length) setUeId(ues[0].id)
  }, [ues, ueId])
  useEffect(() => { setUeId(null) }, [maquetteId])

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

  const chargement = maquettesQuery.isLoading

  return (
    <div className="ecran-generique" data-testid="ecran-ue-ecue">
      <div className="ue-ecue-toolbar">
        <div className="ue-ecue-champ ue-ecue-champ--large">
          <label htmlFor="choix-maquette">Maquette</label>
          <select
            id="choix-maquette"
            className="form-select form-select-sm"
            data-testid="choix-maquette"
            value={maquetteId}
            onChange={(e) => setMaquetteId(e.target.value)}
            disabled={chargement}
          >
            <option value="">
              {chargement ? 'Chargement…' : 'Choisir une maquette'}
            </option>
            {maquettes.map((m) => (
              <option key={m.id} value={m.id}>
                {m.ref_formation} — {m.niveau} — {m.annee_academique} (v{m.version})
              </option>
            ))}
          </select>
        </div>
        <div className="ue-ecue-champ">
          <label htmlFor="recherche-ue">Rechercher une UE</label>
          <input
            id="recherche-ue"
            type="search"
            className="form-control form-control-sm"
            placeholder="Code ou intitulé…"
            value={recherche}
            onChange={(e) => setRecherche(e.target.value)}
            data-testid="recherche-ue"
          />
        </div>
        {maquette && (
          <span className="ue-ecue-etat gen-count-pill" data-testid="etat-maquette">
            {STATUT_MAQUETTE[maquette.statut] || maquette.statut}
          </span>
        )}
      </div>

      {maquettesQuery.isError && (
        <div className="alert alert-danger py-2" role="alert" data-testid="erreur-maquettes">
          Impossible de charger les maquettes : {erreurLisible(maquettesQuery.error, 'accès refusé.')}
        </div>
      )}

      {maquettesQuery.isSuccess && maquettes.length === 0 && (
        <div className="alert alert-info py-2" role="status" data-testid="aucune-maquette">
          Aucune maquette n’est encore définie : les UE et ECUE se rattachent à une
          maquette, il faut d’abord en créer une.
        </div>
      )}

      {maquette && !maquetteEditable && (
        <div className="alert alert-warning py-2" role="status" data-testid="maquette-verrouillee">
          Cette maquette est <strong>{STATUT_MAQUETTE[maquette.statut]?.toLowerCase()}</strong> :
          son contenu ne peut plus être modifié. Créez une nouvelle version (clonage) pour
          faire évoluer le programme.
        </div>
      )}

      <div className="ue-ecue-colonnes">
        {/* ── Niveau 2 : les UE de la maquette ─────────────────────────── */}
        <div className="ue-ecue-panneau">
          <div className="gen-panel">
            <div className="gen-panel-head">
              <h2 className="gen-panel-title">
                <i className="bi bi-collection"></i>
                Unités d’enseignement
              </h2>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <span className="gen-count-pill">
                  {uesQuery.isLoading ? 'Chargement…' : `${uesFiltrees.length} UE`}
                </span>
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
            <div className="table-responsive gen-table-wrap">
              <table className="table table-sm table-hover align-middle mb-0 gen-table">
                <thead>
                  <tr>
                    <th scope="col">Code</th>
                    <th scope="col">Intitulé</th>
                    <th scope="col">Sem.</th>
                    <th scope="col">ECTS</th>
                    <th scope="col">Statut</th>
                    <th scope="col" className="text-end">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {uesFiltrees.map((ligne) => (
                    <tr
                      key={ligne.id}
                      className={Number(ligne.id) === Number(ueId) ? 'table-active' : ''}
                      onClick={() => setUeId(ligne.id)}
                      style={{ cursor: 'pointer' }}
                      data-testid={`ligne-ue-${ligne.id}`}
                    >
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
                      <td>{ligne.intitule}</td>
                      <td>{ligne.semestre?.libelle || '—'}</td>
                      <td>{afficherValeur(ligne.credits)}</td>
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
                      <td colSpan={6}>
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
            <div className="gen-panel-foot">
              <span className="gen-panel-foot-info">
                <i className="bi bi-info-circle"></i>
                <code className="gen-endpoint-chip">
                  /api/scolarite/maquettes/&lt;id&gt;/ues/
                </code>
              </span>
            </div>
          </div>
        </div>

        {/* ── Niveau 3 : les ECUE de l'UE sélectionnée ─────────────────── */}
        <div className="ue-ecue-panneau">
          <div className="gen-panel">
            <div className="gen-panel-head">
              <h2 className="gen-panel-title">
                <i className="bi bi-list-check"></i>
                ECUE {ue ? `— ${ue.code}` : ''}
              </h2>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
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
            <div className="table-responsive gen-table-wrap">
              <table className="table table-sm table-hover align-middle mb-0 gen-table">
                <thead>
                  <tr>
                    <th scope="col">Code</th>
                    <th scope="col">Intitulé</th>
                    <th scope="col">ECTS</th>
                    <th scope="col">Volumes</th>
                    <th scope="col">Statut</th>
                    <th scope="col" className="text-end">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {(ue?.ecues || []).map((ecue) => (
                    <tr key={ecue.id} data-testid={`ligne-ecue-${ecue.id}`}>
                      <td><span className="gen-code-chip">{ecue.code}</span></td>
                      <td>{ecue.intitule}</td>
                      <td>{afficherValeur(ecue.credits)}</td>
                      <td className="small text-muted">
                        {Number(ecue.volume_cm) || Number(ecue.volume_td) || Number(ecue.volume_tp)
                          ? `CM ${Number(ecue.volume_cm)} · TD ${Number(ecue.volume_td)} · TP ${Number(ecue.volume_tp)}`
                          : '—'}
                      </td>
                      <td><BadgeStatut statut={ecue.statut} /></td>
                      <td>
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
                      </td>
                    </tr>
                  ))}
                  {(!ue || ue.ecues.length === 0) && (
                    <tr>
                      <td colSpan={6}>
                        <div className="gen-empty">
                          <i className="bi bi-inbox" aria-hidden="true"></i>
                          <span className="gen-empty-title">Aucun ECUE</span>
                          <span className="gen-empty-text">
                            {ue
                              ? 'Sélectionnez « Nouvel ECUE » pour ajouter le premier élément constitutif.'
                              : 'Sélectionnez une UE à gauche pour voir ses éléments constitutifs.'}
                          </span>
                        </div>
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
            <div className="gen-panel-foot">
              <span className="gen-panel-foot-info">
                <i className="bi bi-info-circle"></i>
                <span className="ue-ecue-legende">
                  « — » : valeur non publiée par la source officielle (les crédits
                  le sont au niveau de l’UE, pas de l’ECUE). Aucun zéro n’est inventé.
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
    </div>
  )
}
