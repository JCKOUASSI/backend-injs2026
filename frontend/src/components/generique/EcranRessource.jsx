import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../../services/api'
import { useToast } from '../../context/ToastContext'
import ConfirmModal from '../ConfirmModal'
import { parsePaginatedResponse } from '../../utils/paginatedResponse'
import { messageErreur } from '../../services/scolarite'
import { useDebounce } from '../../hooks/useDebounce'

/**
 * Écran générique piloté par un **descripteur** (`src/menu/ecrans.js`).
 *
 * Objectif : exposer les dizaines d'écrans demandés par la réorganisation de la
 * navigation sur les endpoints **existants** du backend, avec un rendu homogène
 * (liste filtrable, pagination, fiche de détail, actions de workflow, export),
 * sans dupliquer trente fois le même code. Chaque écran reste approfondissable
 * individuellement (CRUD complet) sans toucher aux autres : c'est le
 * fonctionnement « par lots » retenu.
 *
 * Règles respectées :
 * - **lecture seule par défaut** : aucune écriture n'est déclenchée sans action
 *   explicite de l'utilisateur, et toute action passe par le backend (qui reste
 *   la seule autorité — un bouton affiché ne dispense d'aucun contrôle) ;
 * - tolérance aux formes de réponse : tableau nu, `{results}`, ou DRF paginé
 *   `{count, next, previous, results}` ;
 * - aucun repli sur des données fictives : une réponse vide affiche un état
 *   vide explicite, une erreur affiche le message du serveur.
 */

/** Lit une valeur éventuellement imbriquée (`a.b.c`). */
export function lireChemin(objet, chemin) {
  if (!objet || !chemin) return undefined
  if (!String(chemin).includes('.')) return objet[chemin]
  return String(chemin).split('.').reduce((acc, cle) => (
    acc == null ? undefined : acc[cle]
  ), objet)
}

const MOIS = {
  montant: (v) => (v == null || v === '' ? '—'
    : `${Number(v).toLocaleString('fr-FR', { maximumFractionDigits: 0 })} F`),
  // Certains endpoints renvoient déjà une date française (jj/mm/aaaa) :
  // `new Date` échoue alors silencieusement — on affiche la valeur brute.
  date: (v) => {
    if (!v) return '—'
    const d = new Date(v)
    return Number.isNaN(d.getTime()) ? String(v) : d.toLocaleDateString('fr-FR')
  },
  datetime: (v) => {
    if (!v) return '—'
    const d = new Date(v)
    return Number.isNaN(d.getTime())
      ? String(v)
      : d.toLocaleString('fr-FR', { dateStyle: 'short', timeStyle: 'short' })
  },
  booleen: (v) => (v ? 'Oui' : 'Non'),
  pourcentage: (v) => (v == null || v === '' ? '—' : `${Number(v).toLocaleString('fr-FR')} %`),
}

/** Formate une valeur de cellule selon le format déclaré du descripteur. */
export function formater(valeur, format, colonne) {
  if (format && MOIS[format]) return MOIS[format](valeur)
  if (format === 'badge' && colonne?.badges) {
    const cle = String(valeur ?? '').toUpperCase()
    return colonne.badges[cle] ?? colonne.badges[valeur] ?? valeur ?? '—'
  }
  if (valeur == null || valeur === '') return '—'
  if (typeof valeur === 'boolean') return valeur ? 'Oui' : 'Non'
  if (Array.isArray(valeur)) return valeur.length ? valeur.join(', ') : '—'
  if (typeof valeur === 'object') return valeur.libelle || valeur.nom || valeur.code || JSON.stringify(valeur)
  return String(valeur)
}

/** Libellés français des champs fréquents (en-têtes de colonnes lisibles). */
export const LIBELLES_CHAMPS = {
  id: 'ID', code: 'Code', libelle: 'Libellé', nom: 'Nom', prenoms: 'Prénoms',
  prenom: 'Prénom', titre: 'Titre', objet: 'Objet', statut: 'Statut',
  etat: 'État', type: 'Type', date_creation: 'Créé le', date_debut: 'Début',
  date_fin: 'Fin', date_naissance: 'Naissance', created_at: 'Créé le',
  updated_at: 'Modifié le', timestamp: 'Horodatage', action: 'Action',
  action_label: 'Action', acteur_label: 'Auteur', acteur_role: 'Rôle auteur',
  cible_type: 'Cible', cible_numero: 'N° cible', cible_nom: 'Libellé cible',
  ip_address: 'Adresse IP', extra: 'Détails', actif: 'Actif', courante: 'Courante',
  annee_academique: 'Année', annee_academique_id: 'Année', niveau: 'Niveau',
  niveau_id: 'Niveau', semestre: 'Semestre', numero: 'Numéro',
  ref_formation: 'Formation', ref_formation_id: 'Formation',
  formation: 'Formation', formation_titre: 'Formation', parcours: 'Parcours',
  parcours_id: 'Parcours', groupe: 'Groupe', groupe_id: 'Groupe',
  matricule: 'Matricule', email: 'Courriel', telephone: 'Téléphone',
  montant: 'Montant', montant_du: 'Reste dû', montant_paye: 'Payé',
  reste_a_payer: 'Reste à payer', total: 'Total', prix: 'Prix',
  quantite: 'Quantité', capacite_max: 'Capacité', effectif: 'Effectif',
  credits_requis: 'Crédits requis', cycle: 'Cycle', ordre: 'Ordre',
  moyenne: 'Moyenne', note: 'Note', rang: 'Rang', classement: 'Classement',
  decision: 'Décision', motif: 'Motif', motifs: 'Motifs',
  observations: 'Observations', commentaire: 'Commentaire',
  utilisateur: 'Utilisateur', username: 'Identifiant', compte: 'Compte',
  role: 'Rôle', roles: 'Rôles', service: 'Service', service_id: 'Service',
  fonction: 'Fonction', direction: 'Direction', departement: 'Département',
  site: 'Site', salle: 'Salle', batiment: 'Bâtiment',
  reference: 'Référence', reference_decision: 'Référence décision',
  date_limite_inscription: 'Limite d\'inscription', categorie: 'Catégorie',
  grade: 'Grade', voie_acces: 'Voie d\'accès', obligatoire: 'Obligatoire',
  valide: 'Validé', verrouille: 'Verrouillé', publie: 'Publié',
  signe: 'Signé', signature: 'Signature', fichier: 'Fichier',
  description: 'Description', volume_horaire: 'Volume horaire',
  heures: 'Heures', enseignant: 'Enseignant', formateur: 'Formateur',
  agent: 'Agent', candidat: 'Candidat', etudiant: 'Étudiant',
  organisme: 'Organisme', structure: "Structure", tuteur: 'Tuteur',
  convention: 'Convention', stage: 'Stage', entreprise: 'Entreprise',
  adresse: 'Adresse', ville: 'Ville', pays: 'Pays',
  date_paiement: 'Date de paiement', mode_paiement: 'Mode de paiement',
  reference_paiement: 'Référence paiement', echeancier: 'Échéancier',
  facture: 'Facture', quittance: 'Quittance', relance: 'Relance',
  periode: 'Période', exercice: 'Exercice',
}

/** Champs techniques jamais affichés en colonne automatique. */
const CHAMPS_TECHNIQUES = new Set([
  'id', 'pk', 'url', 'ressource_type', 'content_type', 'object_id',
  'content_type_id', 'extra', 'hash', 'empreinte', 'empreinte_precedente',
])

function infererFormat(cle, valeur) {
  if (typeof valeur === 'boolean') return 'booleen'
  if (/(_at$|^date_|_date$|timestamp)/.test(cle)) return 'datetime'
  if (/^(montant|total|prix|reste|solde)|_montant$|_prix$/.test(cle)) return 'montant'
  if (/(statut|etat|decision|type|niveau|categorie|grade)/.test(cle)
      && (typeof valeur === 'string')) return 'texte'
  return undefined
}

/**
 * Colonnes déclarées par le descripteur, ou **dérivées de la première ligne**
 * (ordre du serveur, champs techniques exclus, libellés français connus,
 * formats inferés). La dérivation évite tout écran vide ou muet quand la forme
 * exacte d'un endpoint n'est pas documentée : ce qui est affiché vient
 * toujours du serveur, jamais d'une donnée inventée.
 */
export function colonnesPour(ecran, lignes) {
  if (Array.isArray(ecran.colonnes) && ecran.colonnes.length) return ecran.colonnes
  const echantillon = (lignes || [])[0]
  if (!echantillon || typeof echantillon !== 'object') return []
  const exclus = new Set([...CHAMPS_TECHNIQUES, ...(ecran.exclure || [])])
  const priorite = ecran.priorite || []
  const cles = Object.keys(echantillon).filter((c) => !exclus.has(c))
  cles.sort((a, b) => {
    const ia = priorite.indexOf(a)
    const ib = priorite.indexOf(b)
    if (ia !== -1 || ib !== -1) {
      if (ia === -1) return 1
      if (ib === -1) return -1
      return ia - ib
    }
    return 0
  })
  const retenues = cles.slice(0, ecran.maxColonnes || 8)
  // Écarte les clés « X_id » quand la clé « X » est déjà retenue : la FK
  // n'apporte rien à l'écran et occupait une colonne entière (X, X id).
  const retenuesFiltrees = retenues.filter(
    (cle) => !(cle.endsWith('_id') && retenues.includes(cle.slice(0, -3))),
  )
  // Déduplication des libellés : un même libellé ne peut pas apparaître deux
  // fois (ex. « Année » et « Année id » déduits par la déduction
  // automatique). Sans cela, l'écran affiche des colonnes redondantes.
  const vus = new Set()
  return retenuesFiltrees
    .map((cle) => ({
      cle,
      libelle: LIBELLES_CHAMPS[cle] || cle.replace(/_/g, ' ').replace(/^./, (c) => c.toUpperCase()),
      format: infererFormat(cle, echantillon[cle]),
    }))
    .filter((colonne) => {
      const libelle = colonne.libelle.toLowerCase()
      if (vus.has(libelle)) return false
      vus.add(libelle)
      return true
    })
}

function Cellule({ ligne, colonne }) {
  const valeur = colonne.valeur ? colonne.valeur(ligne) : lireChemin(ligne, colonne.cle)
  const texte = formater(valeur, colonne.format, colonne)
  if (colonne.format === 'badge' && colonne.couleurs) {
    const cle = String(valeur ?? '').toUpperCase()
    return <span className={`badge ${colonne.couleurs[cle] || 'text-bg-secondary'}`}>{texte}</span>
  }
  if (colonne.format === 'booleen') {
    // Pastille explicite (« Actif / Inactif ») plutôt qu'une icône nue : le
    // libellé suit celui de la colonne (« Courante » → « Non courante »…).
    const libelleOn = colonne.libelle || 'Oui'
    const libelleOff = libelleOn === 'Actif' ? 'Inactif' : `Non ${libelleOn.toLowerCase()}`
    return (
      <span className={`gen-bool-pill ${valeur ? 'gen-bool-pill--on' : 'gen-bool-pill--off'}`}>
        <i className={`bi ${valeur ? 'bi-check-circle-fill' : 'bi-dash-circle'}`}></i>
        {valeur ? libelleOn : libelleOff}
      </span>
    )
  }
  if (colonne.cle === 'code' && texte !== '—') {
    return <span className="gen-code-chip">{texte}</span>
  }
  return texte
}

/** Charge les options d'un filtre adossé à un endpoint référentiel. */
function useOptionsFiltre(filtre) {
  const endpoint = filtre?.optionsEndpoint
  return useQuery({
    queryKey: ['ecran-generique', 'options', endpoint, filtre?.optionsCleLibelle],
    queryFn: async () => {
      const res = await api.get(endpoint)
      const brut = Array.isArray(res?.data) ? res.data : (res?.data?.results || [])
      return brut.map((o) => ({
        valeur: String(o[filtre.optionsCleValeur || 'id']),
        libelle: o[filtre.optionsCleLibelle || 'libelle'] || o.nom || o.code || o[filtre.optionsCleValeur || 'id'],
      }))
    },
    enabled: Boolean(endpoint),
    staleTime: 10 * 60 * 1000,
    retry: false,
  })
}

function Filtre({ filtre, valeur, onChange }) {
  const { data: options } = useOptionsFiltre(filtre)
  if (filtre.type === 'select') {
    const choix = filtre.options || options || []
    return (
      <select
        className="form-select form-select-sm"
        value={valeur ?? ''}
        onChange={(e) => onChange(e.target.value)}
        aria-label={filtre.libelle}
      >
        <option value="">{filtre.tous || `Tous les ${filtre.libelle.toLowerCase()}`}</option>
        {choix.map((o) => (
          <option key={o.valeur} value={o.valeur}>{o.libelle}</option>
        ))}
      </select>
    )
  }
  if (filtre.type === 'date') {
    return (
      <input
        type="date"
        className="form-control form-control-sm"
        value={valeur ?? ''}
        onChange={(e) => onChange(e.target.value)}
        aria-label={filtre.libelle}
      />
    )
  }
  return (
    <input
      type={filtre.type === 'nombre' ? 'number' : 'text'}
      className="form-control form-control-sm"
      placeholder={filtre.libelle}
      value={valeur ?? ''}
      onChange={(e) => onChange(e.target.value)}
      aria-label={filtre.libelle}
    />
  )
}

/** Liste (ou onglets) générique — cœur du moteur d'écrans. */
export function ListeGenerique({ ecran, cleBase }) {
  const { showToast } = useToast()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [filtres, setFiltres] = useState({})
  const [recherche, setRecherche] = useState('')
  const [page, setPage] = useState(1)
  const [selection, setSelection] = useState(null)
  const [confirmation, setConfirmation] = useState(null)
  const rechercheDebounced = useDebounce(recherche, 350)

  useEffect(() => { setPage(1) }, [rechercheDebounced, filtres, ecran.id])

  const params = useMemo(() => {
    const base = { ...(ecran.params || {}) }
    for (const filtre of ecran.filtres || []) {
      const valeur = filtres[filtre.param]
      if (valeur !== undefined && valeur !== '') base[filtre.param] = valeur
    }
    if (rechercheDebounced && ecran.recherche) base[ecran.recherche.param] = rechercheDebounced
    if (ecran.pagination !== false) {
      base[ecran.paramPage || 'page'] = page
      if (ecran.taillePage) base[ecran.paramTaille || 'page_size'] = ecran.taillePage
    }
    return base
  }, [ecran, filtres, rechercheDebounced, page])

  // Filtres marqués `requis: true` : la requête attend leur valeur — un appel
  // sans paramètre obligatoire renverrait une erreur 400 serveur inutile.
  const filtresManquants = useMemo(
    () => (ecran.filtres || []).filter((f) => {
      if (!f.requis) return false
      const v = params[f.param]
      return v === undefined || v === null || v === ''
    }),
    [ecran, params],
  )

  const cle = useMemo(
    () => [...cleBase, ecran.id, params],
    [cleBase, ecran.id, params],
  )

  const { data, isFetching, error } = useQuery({
    queryKey: cle,
    queryFn: async ({ signal }) => {
      const res = await api.get(ecran.endpoint, { params, signal })
      const brut = res?.data
      // Réponse « objet » (statistiques, synthèse, contrôle d'intégrité) :
      // aucune liste à afficher, mais des indicateurs à présenter tels quels.
      const estObjet = brut && !Array.isArray(brut) && !Array.isArray(brut.results)
      if (estObjet && (ecran.type === 'indicateurs' || !brut.results)) {
        return { results: [], count: 0, totalPages: 1, indicateurs: brut }
      }
      return parsePaginatedResponse(brut, ecran.taillePage || 50)
    },
    enabled: Boolean(ecran.endpoint) && filtresManquants.length === 0,
    retry: false,
  })

  const lignes = useMemo(() => data?.results || [], [data])
  const colonnes = useMemo(() => colonnesPour(ecran, lignes), [ecran, lignes])

  const mutation = useMutation({
    mutationFn: async ({ action, ligne }) => {
      const chemin = typeof action.chemin === 'function' ? action.chemin(ligne) : action.chemin
      if (action.telechargement) {
        const { blob, fileName } = await api.getBlob(chemin)
        const url = URL.createObjectURL(blob)
        const lien = document.createElement('a')
        lien.href = url
        lien.download = fileName || `${action.id || 'document'}`
        document.body.appendChild(lien)
        lien.click()
        lien.remove()
        URL.revokeObjectURL(url)
        return { telecharge: true }
      }
      const corps = typeof action.corps === 'function' ? action.corps(ligne) : action.corps
      const methode = (action.methode || 'POST').toLowerCase()
      if (methode === 'get') return api.get(chemin)
      if (methode === 'patch') return api.patch(chemin, corps ?? {})
      if (methode === 'put') return api.put(chemin, corps ?? {})
      if (methode === 'delete') return api.delete(chemin)
      return api.post(chemin, corps ?? {})
    },
    onSuccess: (_res, variables) => {
      showToast(variables.action.succes || 'Action enregistrée.')
      queryClient.invalidateQueries({ queryKey: cleBase })
      setConfirmation(null)
      setSelection(null)
    },
    onError: (err, variables) => {
      showToast(messageErreur(err, variables.action.erreur || 'Action refusée par le serveur.'), 'error')
      setConfirmation(null)
    },
  })

  const demander = (action, ligne) => {
    if (action.confirmation) {
      setConfirmation({ action, ligne })
      return
    }
    mutation.mutate({ action, ligne })
  }

  // Critères renseignés (recherche + filtres) : indicateur de lecture calculé
  // en local, aucun appel serveur supplémentaire.
  const nbCriteres = (recherche ? 1 : 0)
    + Object.values(filtres).filter((v) => v !== '' && v != null).length
  const aDesCriteres = Boolean(ecran.recherche) || (ecran.filtres || []).length > 0
  // La barre n'a de sens que s'il y a un contenu à afficher (critère ou
  // action globale) : sinon elle se réduisait à une carte quasi vide ne
  // contenant que le bouton de rechargement — le rechargement vit désormais
  // dans l'en-tête du panneau de résultats pour les listes.
  const aBarre = aDesCriteres || (ecran.actionsGlobales || []).length > 0
  const indicateurs = data?.indicateurs

  // Rechargement manuel : dans la barre pour les écrans d'indicateurs (sans
  // panneau de liste), dans l'en-tête du panneau pour les listes.
  const recharger = (
    <button
      type="button"
      className="btn btn-sm gen-refresh"
      onClick={() => queryClient.invalidateQueries({ queryKey: cle })}
      title="Recharger depuis le serveur"
      aria-label="Recharger depuis le serveur"
    >
      <i className={`bi bi-arrow-clockwise${isFetching ? ' spin' : ''}`}></i>
    </button>
  )

  // Barre d'outils commune : recherche, filtres, actions globales, rechargement.
  const barre = (
    <div className="gen-toolbar">
      {aDesCriteres && (
        <div className="gen-toolbar-head">
          <h2 className="gen-panel-title">
            <i className="bi bi-funnel" aria-hidden="true"></i>
            Filtres et recherche
          </h2>
          <span className="gen-count-pill">
            {nbCriteres === 0
              ? 'Aucun critère'
              : `${nbCriteres} critère${nbCriteres > 1 ? 's' : ''} actif${nbCriteres > 1 ? 's' : ''}`}
          </span>
        </div>
      )}
      <div className="gen-toolbar-body">
        {ecran.recherche && (
          <div className="gen-field gen-field--recherche">
            <label className="gen-field-label" htmlFor="gen-recherche">
              {ecran.recherche.libelle || 'Rechercher'}
            </label>
            <div className="gen-search">
              <i className="bi bi-search" aria-hidden="true"></i>
              <input
                id="gen-recherche"
                type="search"
                className="form-control form-control-sm"
                placeholder={ecran.recherche.placeholder || 'Rechercher…'}
                value={recherche}
                onChange={(e) => setRecherche(e.target.value)}
              />
            </div>
          </div>
        )}
        {(ecran.filtres || []).map((filtre) => (
          <div className="gen-field gen-field--filtre" key={filtre.param}>
            <label className="gen-field-label">{filtre.libelle}</label>
            <Filtre
              filtre={filtre}
              valeur={filtres[filtre.param]}
              onChange={(v) => setFiltres((p) => ({ ...p, [filtre.param]: v }))}
            />
          </div>
        ))}
        <div className="gen-toolbar-actions">
          {(ecran.actionsGlobales || []).map((action) => (
            <button
              key={action.libelle}
              type="button"
              className="btn btn-sm btn-outline-primary"
              onClick={() => demander(action, null)}
              disabled={mutation.isPending}
            >
              {action.icone && <i className={`bi ${action.icone} me-1`}></i>}
              {action.libelle}
            </button>
          ))}
          {indicateurs && recharger}
        </div>
      </div>
    </div>
  )

  // Filtre requis encore vide : barre de sélection + invite neutre, sans appel
  // serveur (un appel sans paramètre obligatoire renverrait une erreur 400).
  if (filtresManquants.length) {
    return (
      <div className="ecran-generique">
        {barre}
        <div className="alert alert-info" role="status" data-testid="ecran-parametres-requis">
          <strong>Sélection requise.</strong>{' '}
          {filtresManquants.length === 1
            ? `Choisissez « ${filtresManquants[0].libelle} » pour charger les données.`
            : `Choisissez ${filtresManquants.map((f) => `« ${f.libelle} »`).join(', ')} pour charger les données.`}
          <div className="small text-muted mt-1">Endpoint appelé : <code>{ecran.endpoint}</code></div>
        </div>
        {ecran.note && <p className="gen-note mt-3">{ecran.note}</p>}
      </div>
    )
  }

  if (indicateurs) {
    // Sans recherche, filtre ni action, la barre ne contiendrait que le
    // rechargement : on la masque pour préserver l'aspect des écrans purs.
    const sansBarre = !ecran.recherche
      && !(ecran.filtres || []).length
      && !(ecran.actionsGlobales || []).length
    return (
      <div className="ecran-generique">
        {!sansBarre && barre}
        <div className="gen-kpi-grid">
          {Object.entries(indicateurs).map(([cle, valeur]) => {
            // Un nombre reste un gros chiffre KPI ; un booléen, un objet ou une
            // chaîne longue est un texte et prend le même corps que la liste des
            // cartes voisines (sinon JSON et « Non » s'affichent en 1,6 rem).
            const estDetail = typeof valeur === 'boolean'
              || (typeof valeur === 'object' && !Array.isArray(valeur))
              || (typeof valeur === 'string' && valeur.length > 40)
            return (
              <div className="card h-100 gen-kpi" key={cle}>
                <div className="card-body">
                  <span className="gen-kpi-label">
                    {LIBELLES_CHAMPS[cle] || cle.replace(/_/g, ' ')}
                  </span>
                  <div className={`gen-kpi-value${estDetail ? ' gen-kpi-value--texte' : ''}`}>
                    {typeof valeur === 'boolean'
                      ? (valeur
                        ? <span className="text-success"><i className="bi bi-check-circle-fill me-1"></i>Oui</span>
                        : <span className="text-danger"><i className="bi bi-x-circle-fill me-1"></i>Non</span>)
                      : Array.isArray(valeur)
                        ? (valeur.length
                          ? <span className="badge text-bg-warning">{valeur.length} élément(s)</span>
                          : <span className="text-success"><i className="bi bi-shield-check me-1"></i>Aucune</span>)
                        : formater(valeur, /_le$|_at$|date/.test(cle) ? 'datetime' : undefined)}
                  </div>
                  {Array.isArray(valeur) && valeur.length > 0 && (
                    <ul className="gen-kpi-list">
                      {valeur.slice(0, 6).map((a, i) => (
                        <li key={i}>{typeof a === 'object' ? JSON.stringify(a) : String(a)}</li>
                      ))}
                      {valeur.length > 6 && <li>… {valeur.length - 6} autres</li>}
                    </ul>
                  )}
                </div>
              </div>
            )
          })}
        </div>
        {ecran.note && <p className="gen-note mt-3">{ecran.note}</p>}
      </div>
    )
  }

  return (
    <div className="ecran-generique">
      {aBarre && barre}

      {error && (
        <div
          className={`alert ${error?.response?.status === 403 ? 'alert-warning' : 'alert-danger'}`}
          role="alert"
          data-testid="ecran-erreur"
          data-statut={error?.response?.status ?? 'inconnu'}
        >
          <strong>
            {error?.response?.status === 403
              ? 'Accès refusé par le serveur.'
              : 'Données indisponibles.'}
          </strong>{' '}
          {messageErreur(error, 'Le serveur a refusé la requête.')}
          {error?.response?.status === 403 && (
            <div className="small mt-1">
              Le droit d'ouvrir ces données est vérifié par le serveur à chaque
              appel ; le menu masque normalement les entrées que votre compte ne
              peut pas consulter. Certaines consoles exigent en plus un drapeau
              d'activation ouvert. Si ce refus vous semble injustifié, contactez
              un administrateur d'habilitation.
            </div>
          )}
          <div className="small text-muted mt-1">Endpoint appelé : <code>{ecran.endpoint}</code></div>
        </div>
      )}

      <div className="gen-panel">
        <div className="gen-panel-head">
          <h2 className="gen-panel-title">
            <i className="bi bi-list-ul"></i>
            {ecran.titreListe || 'Résultats'}
          </h2>
          <div className="d-flex align-items-center gap-2 flex-wrap">
            <span className="gen-count-pill">
              {isFetching ? 'Chargement…' : `${data?.count ?? lignes.length} élément(s)`}
            </span>
            {recharger}
          </div>
        </div>
        <div className="table-responsive gen-table-wrap">
          <table className="table table-sm table-hover align-middle mb-0 gen-table">
            <thead>
              <tr>
                {colonnes.map((c) => (
                  <th key={c.cle || c.libelle} scope="col" style={c.largeur ? { width: c.largeur } : undefined}>
                    {c.libelle}
                  </th>
                ))}
                {(ecran.actions || []).length > 0 && <th scope="col" className="text-end">Actions</th>}
              </tr>
            </thead>
            <tbody>
              {lignes.map((ligne, index) => (
                <tr
                  key={ligne.id ?? index}
                  className={selection === ligne ? 'table-active' : ''}
                  onClick={() => ecran.detail && setSelection(ligne)}
                  style={ecran.detail ? { cursor: 'pointer' } : undefined}
                >
                  {colonnes.map((c) => (
                    <td key={c.cle || c.libelle}><Cellule ligne={ligne} colonne={c} /></td>
                  ))}
                  {(ecran.actions || []).length > 0 && (
                    <td className="text-end" onClick={(e) => e.stopPropagation()}>
                      {(ecran.actions || []).map((action) => {
                        if (action.visible && !action.visible(ligne)) return null
                        const cible = action.vers ? action.vers(ligne) : null
                        return (
                          <button
                            key={action.libelle}
                            type="button"
                            className={`btn btn-sm ${action.apparence || 'btn-outline-secondary'} me-1`}
                            onClick={() => (action.vers
                              ? (cible ? navigate(cible) : showToast(action.indisponible || 'Cible incomplète pour cette action.', 'error'))
                              : demander(action, ligne))}
                            disabled={mutation.isPending || (action.vers && !cible)}
                            title={action.libelle}
                            data-testid={`action-${action.libelle}`}
                          >
                            {action.icone && <i className={`bi ${action.icone}`}></i>}
                            {!action.icone && action.libelle}
                          </button>
                        )
                      })}
                    </td>
                  )}
                </tr>
              ))}
              {lignes.length === 0 && !isFetching && (
                <tr>
                  <td colSpan={Math.max(1, colonnes.length) + 1}>
                    <div className="gen-empty">
                      <i className="bi bi-inbox" aria-hidden="true"></i>
                      <span className="gen-empty-title">Aucun résultat</span>
                      <span className="gen-empty-text">
                        {ecran.vide || "Aucun élément à afficher pour ces critères."}
                      </span>
                    </div>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        <div className="gen-panel-foot">
          {ecran.note ? (
            <span className="gen-panel-foot-info">
              <i className="bi bi-info-circle"></i>
              <code className="gen-endpoint-chip">{ecran.note}</code>
            </span>
          ) : <span />}
          {data && data.count > (ecran.taillePage || 50) && (
            <nav aria-label="Pagination">
              <ul className="pagination pagination-sm mb-0 gen-pagination">
                <li className={`page-item${page <= 1 ? ' disabled' : ''}`}>
                  <button className="page-link" onClick={() => setPage((p) => Math.max(1, p - 1))}>Précédent</button>
                </li>
                <li className="page-item disabled">
                  <span className="page-link">{page}</span>
                </li>
                <li className={`page-item${page * (ecran.taillePage || 50) >= data.count ? ' disabled' : ''}`}>
                  <button className="page-link" onClick={() => setPage((p) => p + 1)}>Suivant</button>
                </li>
              </ul>
            </nav>
          )}
        </div>
      </div>

      {selection && ecran.detail && (
        <DetailGenerique
          ecran={ecran}
          ligne={selection}
          onFermer={() => setSelection(null)}
        />
      )}

      {confirmation && (
        <ConfirmModal
          message={
            typeof confirmation.action.confirmation === 'function'
              ? confirmation.action.confirmation(confirmation.ligne)
              : confirmation.action.confirmation
          }
          detail={confirmation.action.detail || null}
          variant={confirmation.action.variant || 'primary'}
          confirmLabel={confirmation.action.libelle}
          onConfirm={() => mutation.mutate(confirmation)}
          onCancel={() => setConfirmation(null)}
        />
      )}
    </div>
  )
}

/** Fiche de détail : sous-ressource ou champs de la ligne courante. */
function DetailGenerique({ ecran, ligne, onFermer }) {
  const detail = ecran.detail
  const endpoint = typeof detail.endpoint === 'function' ? detail.endpoint(ligne) : detail.endpoint
  const { data, isFetching, error } = useQuery({
    queryKey: ['ecran-generique', 'detail', ecran.id, ligne?.id, endpoint],
    queryFn: async () => {
      const res = await api.get(endpoint)
      const brut = res?.data
      if (Array.isArray(brut)) return brut
      if (Array.isArray(brut?.results)) return brut.results
      return [brut]
    },
    enabled: Boolean(endpoint),
    retry: false,
  })

  // Colonnes du détail : déclarées (`detail.colonnes`) ou **déduites** des
  // champs prioritaires puis du premier enregistrement, exactement comme pour
  // la liste principale — la plupart des descripteurs de `menu/ecrans.js`
  // déclarent `detail.priorite` plutôt qu'une liste de colonnes.
  const colonnesDetail = useMemo(
    () => (Array.isArray(detail.colonnes) && detail.colonnes.length
      ? detail.colonnes
      : colonnesPour(detail, data || [])),
    [detail, data],
  )

  return (
    <div className="modal d-block" tabIndex="-1" role="dialog" style={{ background: 'rgba(0,0,0,0.45)' }}>
      <div className="modal-dialog modal-lg modal-dialog-scrollable">
        <div className="modal-content">
          <div className="modal-header">
            <h5 className="modal-title">
              {typeof detail.titre === 'function' ? detail.titre(ligne) : (detail.titre || 'Détail')}
            </h5>
            <button type="button" className="btn-close" aria-label="Fermer" onClick={onFermer}></button>
          </div>
          <div className="modal-body">
            {detail.champs && (
              <dl className="row mb-3">
                {detail.champs.map((c) => (
                  <div key={c.libelle} className="col-sm-6">
                    <dt className="small text-muted">{c.libelle}</dt>
                    <dd className="mb-2">{formater(
                      c.valeur ? c.valeur(ligne) : lireChemin(ligne, c.cle),
                      c.format,
                      c,
                    )}</dd>
                  </div>
                ))}
              </dl>
            )}
            {endpoint && (
              <>
                <h6 className="text-muted small text-uppercase">{detail.sousTitre || 'Éléments rattachés'}</h6>
                {isFetching && <div className="text-muted small">Chargement…</div>}
                {error && (
                  <div className="alert alert-warning py-2 small">
                    {messageErreur(error, 'Sous-ressource indisponible.')}
                  </div>
                )}
                {!isFetching && !error && (
                  <table className="table table-sm">
                    <thead>
                      <tr>{colonnesDetail.map((c) => <th key={c.cle || c.libelle}>{c.libelle}</th>)}</tr>
                    </thead>
                    <tbody>
                      {(data || []).map((sous, i) => (
                        <tr key={sous?.id ?? i}>
                          {colonnesDetail.map((c) => (
                            <td key={c.cle || c.libelle}><Cellule ligne={sous} colonne={c} /></td>
                          ))}
                        </tr>
                      ))}
                      {(data || []).length === 0 && (
                        <tr><td colSpan={(detail.colonnes || []).length} className="text-muted text-center">
                          Aucun élément rattaché.
                        </td></tr>
                      )}
                    </tbody>
                  </table>
                )}
              </>
            )}
          </div>
          <div className="modal-footer">
            <button type="button" className="btn btn-sm btn-secondary" onClick={onFermer}>Fermer</button>
          </div>
        </div>
      </div>
    </div>
  )
}

/**
 * Écran à onglets : chaque onglet porte son propre descripteur de liste et son
 * propre cache. Utilisé quand une entrée de menu regroupe plusieurs ressources
 * (ex. « Courrier / Documents », « Réunions & missions », « Journal d'audit »).
 */
export function EcranOnglets({ ecran, cleBase }) {
  const [actif, setActif] = useState(ecran.onglets[0].id)
  const courant = ecran.onglets.find((o) => o.id === actif) || ecran.onglets[0]
  return (
    <div>
      <ul className="gen-onglets-bar" role="tablist">
        {ecran.onglets.map((o) => (
          <li className="nav-item" key={o.id} role="presentation">
            <button
              type="button"
              role="tab"
              aria-selected={o.id === actif}
              className={`nav-link${o.id === actif ? ' active' : ''}`}
              onClick={() => setActif(o.id)}
              data-testid={`onglet-${o.id}`}
            >
              {o.icone && <i className={`bi ${o.icone} me-1`}></i>}{o.libelle}
            </button>
          </li>
        ))}
      </ul>
      <ListeGenerique ecran={{ ...courant, id: `${ecran.id}.${courant.id}` }} cleBase={cleBase} />
    </div>
  )
}

/** Point d'entrée : choisit le rendu selon le type déclaré du descripteur. */
export default function EcranRessource({ ecran, cleBase = ['ecran-generique'] }) {
  if (ecran.onglets) return <EcranOnglets ecran={ecran} cleBase={cleBase} />
  return <ListeGenerique ecran={ecran} cleBase={cleBase} />
}
