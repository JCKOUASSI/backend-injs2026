import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import api from '../../services/api'
import { useToast } from '../../context/ToastContext'
import '../../styles/candidatures.css'
import '../../styles/referentiels.css'

/**
 * Écran de gestion d'un référentiel du registre.
 *
 * Le composant est générique : le slug d'URL désigne l'entrée du registre
 * backend, qui fournit ses champs métier, ses clés étrangères et sa
 * description. Aucun formulaire n'est écrit en dur par référentiel, et les
 * sélecteurs dépendants (école → mention, école → filière) sont pilotés par la
 * relation réelle entre les données.
 */

const LIBELLES_CHAMPS = {
  code: 'Code',
  libelle: 'Libellé',
  description: 'Description',
  actif: 'Actif',
  source_document: 'Source documentaire',
  fiabilite: 'Fiabilité',
  nom_complet: 'Dénomination complète',
  ordre: "Ordre d'affichage",
  abrege: 'Abréviation',
  est_stage: 'Correspond à un stage',
  est_ouvert: 'Autorise les candidatures',
  ecole: 'École',
  mention: 'Mention',
  type_cursus: 'Nature de cursus',
  code_dossier: 'Code dossier',
  etat_ventilation: 'État de ventilation',
  cycle: 'Cycle',
  credits_requis: 'Crédits ECTS requis',
  numero: 'Numéro global',
  niveau: 'Niveau',
  ref_formation: 'Cycle de formation',
  type_formation: 'Type de formation',
  type_lieu: 'Type de lieu',
  capacite: 'Capacité',
  equipements: 'Équipements',
  indisponible_du: 'Indisponible du',
  indisponible_au: 'Indisponible au',
  geofence_latitude: 'Latitude (géorepérage)',
  geofence_longitude: 'Longitude (géorepérage)',
  geofence_rayon_m: 'Rayon de géorepérage (m)',
  site: 'Site',
  batiment: 'Bâtiment',
  type_espace: "Type d'espace sportif",
  formation: 'Formation (cycle)',
  statut: 'Statut',
  periode_debut: 'Début de période',
  periode_fin: 'Fin de période',
  effectif_prevu: 'Effectif prévu',
  effectif_reel: 'Effectif réel',
  date_debut: 'Date de début',
  date_fin: 'Date de fin',
  courante: 'Année courante',
  cloturee: 'Clôturée',
  date_cloture: 'Date de clôture',
}

/** Ordre de lecture imposé aux tables importées, du plus signifiant au détail. */
const ORDRE_LECTURE_SEULE = [
  'filiere_code', 'semestre', 'libelle', 'formation_intitule', 'ordre',
  'etat_ventilation', 'intitule_module', 'heures_cm', 'heures_td', 'heures_tp',
  'heures_stage', 'heures_total', 'source_document', 'fiabilite',
]

/** Libellés humains des codes techniques servis par l'API d'import. */
const VALEURS_TECHNIQUES = {
  A_VENTILER: 'À ventiler',
  VENTILE: 'Ventilé',
  HORS_MAQUETTE: 'Hors maquette',
}

/** Met en forme une valeur brute d'API sans jamais en inventer une. */
function formaterValeur(valeur) {
  if (valeur === null || valeur === undefined || valeur === '') return null
  if (typeof valeur === 'boolean') return valeur
  const texte = String(valeur)
  if (VALEURS_TECHNIQUES[texte]) return VALEURS_TECHNIQUES[texte]
  if (/^-?\d+\.\d{2}$/.test(texte)) return texte.replace(/\.00$/, '')
  return texte
}

const FIABILITES = [
  { value: 'OFFICIEL', label: 'Officiel (attesté par la source)' },
  { value: 'MODELISE', label: 'Modélisé (proposition de la source)' },
  { value: 'CADRAGE', label: 'Cadrage fonctionnel (à valider)' },
  { value: 'A_RENSEIGNER', label: 'À renseigner' },
]

const LIBELLE_FIABILITE = {
  OFFICIEL: 'Officiel',
  MODELISE: 'Modélisé',
  CADRAGE: 'Cadrage',
  A_RENSEIGNER: 'À renseigner',
}

/** Un champ de type clé étrangère dépend-il d'un autre champ du formulaire ? */
const DEPENDANCES = {
  mention: 'ecole',
  batiment: 'site',
}

const CHAMPS_BOOLEENS = ['actif', 'est_stage', 'est_ouvert', 'courante', 'cloturee']

const LIBELLE_TECHNIQUE = {
  formation_intitule: 'Cycle de rattachement',
  filiere_code: 'Filière',
  semestre: 'Semestre',
  ordre: 'Ordre',
  etat_ventilation: 'État de ventilation',
  intitule_module: 'Module',
  heures_cm: 'Heures CM',
  heures_td: 'Heures TD',
  heures_tp: 'Heures TP',
  heures_stage: 'Heures stage',
  heures_total: 'Total',
  fiabilite: 'Fiabilité',
  source_document: 'Source documentaire',
}

/**
 * DRF pagine par défaut : on normalise `{count, results}` et le tableau nu
 * pour que l'écran fonctionne quel que soit le réglage du serveur.
 */
function listeRecue(donnees) {
  if (Array.isArray(donnees)) return donnees
  if (donnees && Array.isArray(donnees.results)) return donnees.results
  return []
}

function valeurInitiale(champ, entree) {
  if (CHAMPS_BOOLEENS.includes(champ)) {
    if (entree?.id) return Boolean(entree[champ])
    return champ === 'actif'
  }
  if (entree?.id) return entree[champ] ?? ''
  return ''
}

export default function ReferentielGenerique() {
  const { slug } = useParams()
  const toast = useToast()

  const [entree, setEntree] = useState(null)
  const [lignes, setLignes] = useState([])
  const [options, setOptions] = useState({})
  const [chargement, setChargement] = useState(true)
  const [rafraichissement, setRafraichissement] = useState(false)
  const [erreur, setErreur] = useState('')
  const [recherche, setRecherche] = useState('')
  const [filtreActif, setFiltreActif] = useState('actifs')
  const [modal, setModal] = useState(null)
  const [form, setForm] = useState({})
  const [erreursForm, setErreursForm] = useState({})
  const [envoi, setEnvoi] = useState(false)
  const [confirmation, setConfirmation] = useState(null)
  const [lectureSeule, setLectureSeule] = useState(false)

  // Capacités réelles du modèle, annoncées par le registre backend : les
  // référentiels hors socle (scolarité LMD) n'ont ni provenance ni
  // archivage, et le semestre n'a pas de colonne code distincte.
  const provenanceSuivie = entree ? entree.provenance_suivie !== false : true
  const archivageSupporte = entree ? entree.archivage_supporte !== false : true
  const aUnCode = entree ? entree.a_un_code !== false : true
  const champsChoix = entree?.champs_choix || {}
  const champsNumeriques = entree?.champs_numeriques || []
  const champsDates = entree?.champs_dates || []
  // Certains modèles tracent leur provenance sans porter de description
  // (sites, bâtiments, salles, vagues) : ne pas afficher un champ mort.
  const aUneDescription = entree ? entree.a_une_description !== false : true

  const afficherCellule = (ligne, cle) => {
    const choix = champsChoix[cle]
    if (choix && ligne[cle] !== null && ligne[cle] !== undefined) {
      const retenue = choix.find((o) => o.value === String(ligne[cle]))
      if (retenue) return retenue.label
    }
    return formaterValeur(ligne[cle]) ?? '—'
  }

  const chargerCatalogue = useCallback(async () => {
    const res = await api.get('/referentiels/tableau-de-bord/')
    const toutes = (res.data.categories || []).flatMap((c) => c.entrees)
    return toutes.find((e) => e.slug === slug) || null
  }, [slug])

  /**
   * Charge (ou recharge) le référentiel.
   *
   * `silencieux` sert aux rechargements consécutifs à une écriture : le tableau
   * reste affiché et seule une pastille « Actualisation… » signale l'attente,
   * au lieu de remplacer tout l'écran par un chargement.
   */
  const charger = useCallback(async ({ silencieux = false } = {}) => {
    if (silencieux) setRafraichissement(true)
    else setChargement(true)
    setErreur('')
    try {
      // 1. La carte du référentiel vient du registre backend : elle dit si la
      //    table est modifiable et quelle route API la sert réellement.
      const courante = await chargerCatalogue()
      if (!courante) {
        setErreur("Ce référentiel n'existe pas ou n'est pas éditable depuis cet écran.")
        setEntree(null)
        return
      }
      setEntree(courante)
      const modifiable = Boolean(courante.editable)
      setLectureSeule(!modifiable)

      if (!modifiable) {
        // 2a. Référentiel historisé ou importé : lecture de sa propre route.
        const source = courante.route_api || `/referentiels/${slug}/`
        const donnees = await api.get(source, { params: { page_size: 1000 } })
        setLignes(listeRecue(donnees.data))
        setOptions({})
        return
      }

      // 2b. Référentiel modifiable : la route générique et les options des
      //     sélecteurs (dont le chemin est fourni par le registre).
      const routes = courante.selecteurs_routes || {}
      const [liste, ...paires] = await Promise.all([
        api.get(`/referentiels/${slug}/`, { params: { archives: 1, page_size: 1000 } }),
        ...(courante.selecteurs || []).map(async (fk) => {
          const route = routes[fk]?.route
          if (!route) return [fk, []]
          const res = await api.get(route, { params: { page_size: 1000 } })
          return [fk, listeRecue(res.data)]
        }),
      ])
      setLignes(listeRecue(liste.data))
      setOptions(Object.fromEntries(paires))
    } catch (e) {
      setErreur(
        e.response?.data?.detail
        || 'Chargement du référentiel impossible.',
      )
    } finally {
      setChargement(false)
      setRafraichissement(false)
    }
  }, [slug, chargerCatalogue])

  useEffect(() => {
    charger()
  }, [charger])

  const lignesFiltrees = useMemo(() => {
    const q = recherche.trim().toLowerCase()
    return lignes
      .filter((l) => {
        // Les tables importées ne portent ni « actif » ni « archive » : le
        // filtre d'état ne s'y applique pas et n'est pas affiché.
        if (lectureSeule) return true
        if (filtreActif === 'actifs') return l.actif && !l.archive
        if (filtreActif === 'inactifs') return !l.actif && !l.archive
        if (filtreActif === 'archives') return l.archive
        return true
      })
      .filter((l) => {
        if (!q) return true
        const valeurs = [l.code, l.libelle, l.description]
        ;(entree?.selecteurs || []).forEach((fk) => valeurs.push(l[`${fk}_libelle`]))
        return valeurs.filter(Boolean).some((v) => String(v).toLowerCase().includes(q))
      })
  }, [lignes, recherche, filtreActif, entree, lectureSeule])

  const ouvrirCreation = () => {
    const base = { fiabilite: 'A_RENSEIGNER', actif: true }
    ;(entree?.champs || []).forEach((champ) => {
      base[champ] = valeurInitiale(champ, null)
    })
    ;(entree?.selecteurs || []).forEach((fk) => {
      base[fk] = ''
    })
    setForm(base)
    setErreursForm({})
    setModal({ mode: 'creation' })
  }

  const ouvrirEdition = (ligne) => {
    const base = {
      code: ligne.code,
      libelle: ligne.libelle,
      description: ligne.description || '',
      actif: ligne.actif,
      source_document: ligne.source_document || '',
      fiabilite: ligne.fiabilite || 'A_RENSEIGNER',
    }
    ;(entree?.champs || []).forEach((champ) => {
      base[champ] = valeurInitiale(champ, ligne)
    })
    ;(entree?.selecteurs || []).forEach((fk) => {
      base[fk] = ligne[fk] ?? ''
    })
    setForm(base)
    setErreursForm({})
    setModal({ mode: 'edition', ligne })
  }

  const fermerModal = () => {
    if (envoi) return
    setModal(null)
    setErreursForm({})
  }

  const enregistrer = async (evenement) => {
    evenement.preventDefault()
    const erreurs = {}
    if (!String(form.libelle || '').trim()) erreurs.libelle = 'Le libellé est obligatoire.'
    if (aUnCode && modal.mode === 'creation' && !String(form.code || '').trim()) {
      erreurs.code = 'Le code métier est obligatoire.'
    }
    if (Object.keys(erreurs).length) {
      setErreursForm(erreurs)
      return
    }
    setEnvoi(true)
    setErreursForm({})
    const corps = { ...form }
    if (!aUnCode) delete corps.code
    if (!provenanceSuivie) {
      delete corps.fiabilite
      delete corps.source_document
    }
    if (!provenanceSuivie || !aUneDescription) delete corps.description
    champsDates.forEach((champ) => {
      if (corps[champ] === '') corps[champ] = null
    })
    ;(entree?.selecteurs || []).forEach((fk) => {
      corps[fk] = corps[fk] === '' ? null : Number(corps[fk])
    })
    Object.keys(champsChoix).forEach((champ) => {
      if (corps[champ] === '') delete corps[champ]
    })
    champsNumeriques.forEach((champ) => {
      if (corps[champ] === '' || corps[champ] === null || corps[champ] === undefined) {
        delete corps[champ]
      } else {
        corps[champ] = Number(corps[champ])
      }
    })
    if (corps.ordre !== undefined && corps.ordre !== '') corps.ordre = Number(corps.ordre)
    try {
      if (modal.mode === 'creation') {
        await api.post(`/referentiels/${slug}/`, corps)
        toast.success?.('Référentiel enregistré.')
      } else {
        delete corps.code
        await api.patch(`/referentiels/${slug}/${modal.ligne.id}/`, corps)
        toast.success?.('Référentiel mis à jour.')
      }
      setModal(null)
      await charger({ silencieux: true })
    } catch (e) {
      const data = e.response?.data
      if (data && typeof data === 'object') {
        const champs = Object.entries(data)
          .filter(([cle]) => cle !== 'detail')
          .map(([, valeur]) => (Array.isArray(valeur) ? valeur.join(' ') : String(valeur)))
        if (champs.length) {
          setErreursForm({ general: champs.join(' ') })
        } else {
          setErreursForm({ general: data.detail || 'Enregistrement impossible.' })
        }
      } else {
        setErreursForm({ general: 'Enregistrement impossible.' })
      }
    } finally {
      setEnvoi(false)
    }
  }

  const basculerStatut = async (ligne) => {
    try {
      await api.patch(`/referentiels/${slug}/${ligne.id}/`, { actif: !ligne.actif })
      await charger({ silencieux: true })
    } catch {
      toast.error?.('Changement de statut impossible.')
    }
  }

  const archiver = async () => {
    if (!confirmation) return
    setEnvoi(true)
    try {
      await api.post(`/referentiels/${slug}/${confirmation.id}/archiver/`, {})
      toast.success?.('Valeur archivée — elle reste consultable.')
      setConfirmation(null)
      await charger({ silencieux: true })
    } catch {
      toast.error?.('Archivage impossible.')
    } finally {
      setEnvoi(false)
    }
  }

  const reactiver = async (ligne) => {
    try {
      await api.post(`/referentiels/${slug}/${ligne.id}/reactiver/`, {})
      await charger({ silencieux: true })
    } catch {
      toast.error?.('Réactivation impossible.')
    }
  }

  const colonnes = useMemo(() => {
    if (!entree) return []
    if (lectureSeule) {
      const premiere = lignes[0] || {}
      const disponibles = Object.keys(premiere).filter(
        (cle) => !['id', 'formation', 'cree_le', 'modifie_le', 'annee_academique'].includes(cle),
      )
      // Une colonne constante n'apprend rien : la source documentaire unique
      // est déjà rappelée par le bandeau de provenance.
      const constantes = new Set(
        disponibles.filter((cle) => (
          cle === 'source_document'
          && new Set(lignes.map((l) => l[cle])).size <= 1
        )),
      )
      const ordonnees = [
        ...ORDRE_LECTURE_SEULE.filter((cle) => disponibles.includes(cle) && !constantes.has(cle)),
        ...disponibles.filter((cle) => !ORDRE_LECTURE_SEULE.includes(cle) && !constantes.has(cle)),
      ]
      return ordonnees.map((cle) => ({
        cle,
        libelle: LIBELLE_TECHNIQUE[cle] || LIBELLES_CHAMPS[cle] || cle,
      }))
    }
    return [
      { cle: 'code', libelle: 'Code' },
      { cle: 'libelle', libelle: 'Libellé' },
      ...(entree.champs || [])
        .filter((c) => c !== 'actif' && c !== 'description' && c !== 'source_document')
        .map((c) => ({ cle: c, libelle: LIBELLES_CHAMPS[c] || c })),
      ...(entree.selecteurs || []).map((fk) => ({ cle: `${fk}_libelle`, libelle: LIBELLES_CHAMPS[fk] || fk })),
      ...(provenanceSuivie ? [{ cle: 'fiabilite', libelle: 'Fiabilité' }] : []),
    ]
  }, [entree, lectureSeule, lignes, provenanceSuivie])

  const optionsPour = (fk) => {
    const dependDe = DEPENDANCES[fk]
    const liste = options[fk] || []
    if (dependDe && form[dependDe]) {
      return liste.filter((o) => String(o[dependDe]) === String(form[dependDe]))
    }
    return liste
  }

  if (chargement) {
    return (
      <div className="cand-page ref-page">
        <section className="cand-panel" aria-live="polite">
          <div className="cand-chargement">
            <span className="spinner-border" role="status" aria-hidden="true"></span>
            Chargement du référentiel…
          </div>
        </section>
      </div>
    )
  }

  if (erreur || !entree) {
    return (
      <div className="cand-page ref-page">
        <div className="cand-alerte" role="alert">
          <i className="bi bi-exclamation-octagon" aria-hidden="true"></i>
          <span>{erreur || 'Référentiel introuvable.'}</span>
        </div>
        <Link className="cand-btn-fantome" to="/referentiels">
          Retour au catalogue
        </Link>
      </div>
    )
  }

  return (
    <div className="cand-page ref-page">
      <header className="cand-hero">
        <div className="cand-hero-identite">
          <span className="cand-hero-icone" aria-hidden="true">
            <i className={`bi ${entree.icone}`}></i>
          </span>
          <div className="cand-hero-text">
            <span className="cand-hero-badge">
              <Link to="/referentiels" className="ref-fil">
                <i className="bi bi-chevron-left" aria-hidden="true"></i>
                Référentiels
              </Link>
            </span>
            <h1 className="cand-hero-title">{entree.libelle}</h1>
            <p className="cand-hero-sub">{entree.description}</p>
          </div>
        </div>
        <div className="ref-hero-pastilles">
          <span className="ref-pastille ref-pastille--primary">
            <i className="bi bi-collection" aria-hidden="true"></i>
            {lignes.length} valeur{lignes.length > 1 ? 's' : ''}
          </span>
        </div>
      </header>

      <section className="cand-panel">
        <header className="cand-panel-head">
          <h2 className="cand-panel-title">
            <i className="bi bi-table" aria-hidden="true"></i>
            {entree.libelle}
          </h2>
          <div className="ref-panel-actions">
            {rafraichissement && (
              <span className="ref-pastille ref-pastille--neutre" role="status" aria-live="polite">
                <i className="bi bi-arrow-repeat" aria-hidden="true"></i>
                Actualisation…
              </span>
            )}
            <span className="cand-count-pill">
              {lignesFiltrees.length} / {lignes.length}
            </span>
            {lectureSeule ? (
              <span className="ref-pastille ref-pastille--neutre">
                <i className="bi bi-lock" aria-hidden="true"></i>
                Lecture seule
              </span>
            ) : (
              <button type="button" className="cand-btn-principal" onClick={ouvrirCreation}>
                <i className="bi bi-plus-lg" aria-hidden="true"></i>
                Ajouter
              </button>
            )}
          </div>
        </header>
        <div className="cand-panel-body">
          {lectureSeule && (
            <p className="ref-note-texte ref-note-bandeau">
              <i className="bi bi-shield-lock" aria-hidden="true"></i>
              <span>
                Données issues de l’import documentaire
                {entree.source ? ` — ${entree.source}` : ''}. Elles ne sont pas
                modifiables ici : une correction passe par la source puis par un
                nouvel import, afin de préserver la traçabilité.
              </span>
            </p>
          )}
          <div className="ref-filtres">
            <div className="cand-champ ref-champ-recherche">
              <label className="cand-etiquette" htmlFor="ref-recherche-liste">
                Rechercher
              </label>
              <div className="cand-search">
                <i className="bi bi-search" aria-hidden="true"></i>
                <input
                  id="ref-recherche-liste"
                  type="search"
                  className="cand-input"
                  placeholder="Code, libellé…"
                  value={recherche}
                  onChange={(e) => setRecherche(e.target.value)}
                />
              </div>
            </div>
            {!lectureSeule && (
            <div className="cand-champ ref-champ-etat">
              <label className="cand-etiquette" htmlFor="ref-filtre-etat">Afficher</label>
              <select
                id="ref-filtre-etat"
                className="cand-saisie"
                value={filtreActif}
                onChange={(e) => setFiltreActif(e.target.value)}
              >
                <option value="actifs">Actifs</option>
                <option value="inactifs">Inactifs</option>
                {archivageSupporte && <option value="archives">Archivés</option>}
                <option value="tous">Tous</option>
              </select>
            </div>
            )}
          </div>
        </div>

        {lignesFiltrees.length === 0 ? (
          <div className="cand-vide">
            <span className="cand-vide-icone" aria-hidden="true">
              <i className="bi bi-inbox"></i>
            </span>
            <p className="cand-vide-titre">Aucune valeur</p>
            <p className="cand-vide-texte">
              {lignes.length === 0
                ? (lectureSeule
                  ? 'Aucune donnée importée pour ce référentiel : exécutez la commande d’import des référentiels INJS.'
                  : 'Ce référentiel est vide : ajoutez une première valeur ou lancez l’import des documents officiels.')
                : 'Aucune valeur ne correspond au filtre courant.'}
            </p>
          </div>
        ) : (
          <div className="cand-table-wrap">
            <table className={`cand-table ref-table${lectureSeule ? ' ref-table--lecture' : ''}`}>
              <thead>
                <tr>
                  {colonnes.map((c) => (
                    <th key={c.cle} scope="col" data-colonne={c.cle}>{c.libelle}</th>
                  ))}
                  {!lectureSeule && (
                    <th scope="col" className="cand-th-actions">Actions</th>
                  )}
                </tr>
              </thead>
              <tbody>
                {lignesFiltrees.map((ligne) => (
                  <tr key={ligne.id} className={ligne.archive ? 'is-archive' : ''}>
                    {colonnes.map((c) => (
                      <td
                        key={c.cle}
                        data-colonne={c.cle}
                        title={typeof ligne[c.cle] === 'string' ? ligne[c.cle] : undefined}
                      >
                        {c.cle === 'fiabilite' ? (
                          <span className={`ref-fiab ref-fiab--${String(ligne.fiabilite).toLowerCase()}`}>
                            {LIBELLE_FIABILITE[ligne.fiabilite] || '—'}
                          </span>
                        ) : typeof ligne[c.cle] === 'boolean' ? (
                          ligne[c.cle] ? <i className="bi bi-check2" aria-label="Oui"></i> : '—'
                        ) : (
                          afficherCellule(ligne, c.cle)
                        )}
                      </td>
                    ))}
                    {!lectureSeule && (
                    <td className="cand-td-actions">
                      <div className="cand-actions">
                        <button
                          type="button"
                          className="ref-action"
                          onClick={() => ouvrirEdition(ligne)}
                          title="Modifier"
                          aria-label={`Modifier ${ligne.libelle}`}
                        >
                          <i className="bi bi-pencil" aria-hidden="true"></i>
                        </button>
                        <button
                          type="button"
                          className={`ref-action ref-action--statut${ligne.actif ? ' is-actif' : ''}`}
                          onClick={() => basculerStatut(ligne)}
                          title={ligne.actif ? 'Désactiver' : 'Activer'}
                          aria-label={`${ligne.actif ? 'Désactiver' : 'Activer'} ${ligne.libelle}`}
                        >
                          <i className={`bi ${ligne.actif ? 'bi-toggle-on' : 'bi-toggle-off'}`} aria-hidden="true"></i>
                        </button>
                        {archivageSupporte && (ligne.archive ? (
                          <button
                            type="button"
                            className="ref-action ref-action--reactiver"
                            onClick={() => reactiver(ligne)}
                            title="Réactiver"
                            aria-label={`Réactiver ${ligne.libelle}`}
                          >
                            <i className="bi bi-arrow-counterclockwise" aria-hidden="true"></i>
                          </button>
                        ) : (
                          <button
                            type="button"
                            className="ref-action ref-action--archiver"
                            onClick={() => setConfirmation(ligne)}
                            title="Archiver"
                            aria-label={`Archiver ${ligne.libelle}`}
                          >
                            <i className="bi bi-archive" aria-hidden="true"></i>
                          </button>
                        ))}
                      </div>
                    </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {modal && (
        <div className="ref-modale-voile" role="presentation" onClick={fermerModal}>
          <div
            className="ref-modale"
            role="dialog"
            aria-modal="true"
            aria-labelledby="ref-modale-titre"
            onClick={(e) => e.stopPropagation()}
          >
            <header className="ref-modale-head">
              <h2 className="ref-modale-titre" id="ref-modale-titre">
                {modal.mode === 'creation' ? 'Nouvelle valeur' : 'Modifier la valeur'}
                <span>{entree.libelle}</span>
              </h2>
              <button
                type="button"
                className="ref-modale-fermer"
                onClick={fermerModal}
                aria-label="Fermer"
              >
                <i className="bi bi-x-lg" aria-hidden="true"></i>
              </button>
            </header>
            <form onSubmit={enregistrer} className="ref-form">
              <div className="cand-grille-form">
                {aUnCode && (
                <div className="cand-champ">
                  <label className="cand-etiquette" htmlFor="ref-code">
                    Code métier <span className="ref-requis" aria-hidden="true">*</span>
                  </label>
                  <input
                    id="ref-code"
                    className="cand-saisie"
                    value={form.code || ''}
                    onChange={(e) => setForm({ ...form, code: e.target.value.toUpperCase() })}
                    readOnly={modal.mode === 'edition'}
                    required
                    aria-required="true"
                  />
                  <span className="ref-aide">Fourni à la création, immuable ensuite.</span>
                  {erreursForm.code && <span className="ref-erreur">{erreursForm.code}</span>}
                </div>
                )}
                <div className="cand-champ">
                  <label className="cand-etiquette" htmlFor="ref-libelle">
                    Libellé officiel <span className="ref-requis" aria-hidden="true">*</span>
                  </label>
                  <input
                    id="ref-libelle"
                    className="cand-saisie"
                    value={form.libelle || ''}
                    onChange={(e) => setForm({ ...form, libelle: e.target.value })}
                    required
                    aria-required="true"
                  />
                  {erreursForm.libelle && <span className="ref-erreur">{erreursForm.libelle}</span>}
                </div>

                {(entree.champs || []).map((champ) => (
                  <div className="cand-champ" key={champ}>
                    <label className="cand-etiquette" htmlFor={`ref-${champ}`}>
                      {LIBELLES_CHAMPS[champ] || champ}
                    </label>
                    {CHAMPS_BOOLEENS.includes(champ) ? (
                      <label className="ref-case" htmlFor={`ref-${champ}`}>
                        <input
                          id={`ref-${champ}`}
                          type="checkbox"
                          checked={Boolean(form[champ])}
                          onChange={(e) => setForm({ ...form, [champ]: e.target.checked })}
                        />
                        Oui
                      </label>
                    ) : champsChoix[champ] ? (
                      <select
                        id={`ref-${champ}`}
                        className="cand-saisie"
                        value={form[champ] ?? ''}
                        onChange={(e) => setForm({ ...form, [champ]: e.target.value })}
                      >
                        <option value="">— Choisir —</option>
                        {champsChoix[champ].map((option) => (
                          <option key={option.value} value={option.value}>{option.label}</option>
                        ))}
                      </select>
                    ) : (
                      <input
                        id={`ref-${champ}`}
                        type={champsDates.includes(champ)
                          ? 'date'
                          : (champsNumeriques.includes(champ) || champ === 'ordre' ? 'number' : 'text')}
                        step="any"
                        className="cand-saisie"
                        value={form[champ] ?? ''}
                        onChange={(e) => setForm({ ...form, [champ]: e.target.value })}
                      />
                    )}
                  </div>
                ))}

                {(entree.selecteurs || []).map((fk) => (
                  <div className="cand-champ" key={fk}>
                    <label className="cand-etiquette" htmlFor={`ref-${fk}`}>
                      {LIBELLES_CHAMPS[fk] || fk}
                    </label>
                    <select
                      id={`ref-${fk}`}
                      className="cand-saisie"
                      value={form[fk] ?? ''}
                      onChange={(e) => setForm({ ...form, [fk]: e.target.value })}
                    >
                      <option value="">— Aucun —</option>
                      {optionsPour(fk).map((option) => (
                        <option key={option.id} value={option.id}>
                          {option.libelle || option.intitule || option.nom || `#${option.id}`}
                        </option>
                      ))}
                    </select>
                  </div>
                ))}

                {provenanceSuivie && (
                <>
                <div className="cand-champ">
                  <label className="cand-etiquette" htmlFor="ref-fiabilite">Fiabilité</label>
                  <select
                    id="ref-fiabilite"
                    className="cand-saisie"
                    value={form.fiabilite || 'A_RENSEIGNER'}
                    onChange={(e) => setForm({ ...form, fiabilite: e.target.value })}
                  >
                    {FIABILITES.map((f) => (
                      <option key={f.value} value={f.value}>{f.label}</option>
                    ))}
                  </select>
                </div>
                <div className="cand-champ ref-champ-large">
                  <label className="cand-etiquette" htmlFor="ref-source">Source documentaire</label>
                  <input
                    id="ref-source"
                    className="cand-saisie"
                    value={form.source_document || ''}
                    onChange={(e) => setForm({ ...form, source_document: e.target.value })}
                    placeholder="Document officiel attestant la valeur"
                  />
                </div>
                {aUneDescription && (
                <div className="cand-champ ref-champ-large">
                  <label className="cand-etiquette" htmlFor="ref-description">Description</label>
                  <textarea
                    id="ref-description"
                    className="cand-saisie"
                    rows={2}
                    value={form.description || ''}
                    onChange={(e) => setForm({ ...form, description: e.target.value })}
                  />
                </div>
                )}
                </>
                )}
              </div>

              {erreursForm.general && (
                <p className="ref-erreur ref-erreur--general" role="alert">
                  <i className="bi bi-exclamation-circle" aria-hidden="true"></i>
                  {erreursForm.general}
                </p>
              )}

              <footer className="ref-modale-pied">
                <label className="ref-case" htmlFor="ref-actif">
                  <input
                    id="ref-actif"
                    type="checkbox"
                    checked={Boolean(form.actif)}
                    onChange={(e) => setForm({ ...form, actif: e.target.checked })}
                  />
                  Valeur active
                </label>
                <div className="ref-modale-boutons">
                  <button type="button" className="cand-btn-fantome" onClick={fermerModal}>
                    Annuler
                  </button>
                  <button type="submit" className="cand-btn-principal" disabled={envoi}>
                    {envoi ? 'Enregistrement…' : 'Enregistrer'}
                  </button>
                </div>
              </footer>
            </form>
          </div>
        </div>
      )}

      {confirmation && (
        <div className="ref-modale-voile" role="presentation">
          <div className="ref-modale ref-modale--etroite" role="alertdialog" aria-modal="true">
            <header className="ref-modale-head">
              <h2 className="ref-modale-titre">Archiver cette valeur ?</h2>
            </header>
            <div className="ref-modale-corps">
              <p>
                <strong>{confirmation.libelle}</strong> ne sera plus proposée dans les
                nouvelles opérations. Les dossiers existants la conservent : aucune
                donnée n’est supprimée, l’archivage est réversible.
              </p>
            </div>
            <footer className="ref-modale-pied">
              <div className="ref-modale-boutons">
                <button type="button" className="cand-btn-fantome" onClick={() => setConfirmation(null)}>
                  Annuler
                </button>
                <button type="button" className="ref-btn-danger" onClick={archiver} disabled={envoi}>
                  {envoi ? 'Archivage…' : 'Archiver'}
                </button>
              </div>
            </footer>
          </div>
        </div>
      )}
    </div>
  )
}
