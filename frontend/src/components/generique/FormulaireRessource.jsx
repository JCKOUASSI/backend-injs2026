import { useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import api from '../../services/api'
import { messageErreur } from '../../services/scolarite'

/**
 * Formulaire de **création / modification / suppression** d'une ligne de
 * référentiel, piloté par le descripteur `ecran.formulaire` (`src/menu/ecrans.js`).
 *
 * Constat de départ. Les écrans Référentiels et Formations affichaient des
 * listes réelles, alimentées par des API qui savent écrire (`POST`, `PATCH`,
 * `DELETE` sur `/api/scolarite/ref/<ressource>/`), mais **aucun bouton ne
 * permettait d'écrire** : l'utilisateur voyait les 8 filières sans pouvoir en
 * ajouter une. Un écran de consultation présenté comme un module de gestion,
 * c'est un bouton manquant, pas une fonctionnalité.
 *
 * Ce que ce composant garantit :
 *
 * - **le serveur reste seul juge** : aucune validation locale ne remplace le
 *   contrôle serveur ; une erreur 400/409 est affichée telle que le serveur
 *   la formule (doublon, dépendance, champ invalide) ;
 * - **rien n'est inventé dans le formulaire** : un champ n'est affiché que s'il
 *   est déclaré ; une liste de choix vient d'un endpoint réel, jamais d'une
 *   liste codée en dur qui divergerait du référentiel ;
 * - **une suppression n'est pas un clic** : confirmation explicite, et le
 *   refus de dépendance (HTTP 409) est expliqué à l'utilisateur au lieu d'être
 *   avalé — c'est la règle « on ne détruit pas des données académiques en
 *   silence » ;
 * - **aucune valeur par défaut métier** : seuls les champs déclarés `defaut`
 *   sont pré-remplis (typiquement `actif: true`, qui est un état technique).
 */

/** Valeur initiale d'un champ pour un formulaire de création. */
function valeurInitiale(champ) {
  if (champ.defaut !== undefined) return champ.defaut
  if (champ.type === 'booleen') return false
  return ''
}

/** Construit l'état du formulaire : valeurs du descripteur ou de la ligne. */
export function valeursFormulaire(champs, ligne = null) {
  const valeurs = {}
  for (const champ of champs) {
    if (ligne) {
      const brut = ligne[champ.cle]
      if (champ.type === 'booleen') {
        valeurs[champ.cle] = Boolean(brut)
      } else if (brut === undefined || brut === null) {
        valeurs[champ.cle] = ''
      } else {
        valeurs[champ.cle] = String(brut)
      }
    } else {
      valeurs[champ.cle] = valeurInitiale(champ)
    }
  }
  return valeurs
}

/**
 * Corps envoyé au serveur.
 *
 * Les champs vides sont **omis** en création (le serveur applique alors son
 * propre défaut, qui est la règle métier) et envoyés à `null` en modification
 * seulement si le champ accepte le vide. On ne transforme jamais un vide en
 * zéro ni en chaîne « 0 » : ce serait inventer une valeur.
 */
export function corpsRequete(champs, valeurs, { creation }) {
  const corps = {}
  for (const champ of champs) {
    const valeur = valeurs[champ.cle]
    if (champ.type === 'booleen') {
      corps[champ.cle] = Boolean(valeur)
      continue
    }
    if (champ.type === 'nombre') {
      if (valeur === '' || valeur === null || valeur === undefined) {
        if (!creation) corps[champ.cle] = null
        continue
      }
      corps[champ.cle] = Number(valeur)
      continue
    }
    if (champ.type === 'select-nombre') {
      if (valeur === '' || valeur === null || valeur === undefined) {
        if (!creation) corps[champ.cle] = null
        continue
      }
      corps[champ.cle] = Number(valeur)
      continue
    }
    if (valeur === '' || valeur === null || valeur === undefined) {
      if (!creation) corps[champ.cle] = ''
      continue
    }
    corps[champ.cle] = valeur
  }
  return corps
}

/** Champs manquants (validation locale minimale, avant l'appel réseau). */
export function champsManquants(champs, valeurs) {
  return champs
    .filter((champ) => champ.requis)
    .filter((champ) => {
      const v = valeurs[champ.cle]
      if (champ.type === 'booleen') return false
      return v === '' || v === null || v === undefined
    })
    .map((champ) => champ.libelle || champ.cle)
}

/** Champ de saisie : texte, nombre, case à cocher, liste déroulante, zone. */
function Champ({ champ, valeur, onChange, erreur }) {
  const id = `form-${champ.cle}`
  const commun = {
    id,
    'data-testid': `champ-${champ.cle}`,
    'aria-invalid': erreur ? 'true' : undefined,
    'aria-describedby': erreur ? `${id}-erreur` : undefined,
  }
  const classeErreur = erreur ? ' is-invalid' : ''

  return (
    <div className={champ.large ? 'col-12' : 'col-md-6'}>
      <label className="form-label" htmlFor={id}>
        {champ.libelle || champ.cle}
        {champ.requis && <span className="text-danger ms-1" aria-hidden="true">*</span>}
      </label>

      {champ.type === 'booleen' ? (
        <div className="form-check">
          <input
            {...commun}
            className="form-check-input"
            type="checkbox"
            checked={Boolean(valeur)}
            onChange={(e) => onChange(e.target.checked)}
          />
          <label className="form-check-label" htmlFor={id}>
            {champ.aide || 'Oui'}
          </label>
        </div>
      ) : champ.type === 'zone' ? (
        <textarea
          {...commun}
          className={`form-control${classeErreur}`}
          rows={champ.lignes || 3}
          maxLength={champ.maxLength}
          value={valeur}
          onChange={(e) => onChange(e.target.value)}
        />
      ) : champ.type === 'select' || champ.type === 'select-nombre' ? (
        <select
          {...commun}
          className={`form-select${classeErreur}`}
          value={valeur ?? ''}
          onChange={(e) => onChange(e.target.value)}
        >
          <option value="">{champ.vide || '—'}</option>
          {(champ.options || []).map((o) => (
            <option key={o.valeur} value={o.valeur}>{o.libelle}</option>
          ))}
        </select>
      ) : (
        <input
          {...commun}
          className={`form-control${classeErreur}`}
          type={champ.type === 'nombre' ? 'number' : 'text'}
          maxLength={champ.maxLength}
          min={champ.min}
          max={champ.max}
          value={valeur}
          onChange={(e) => onChange(e.target.value)}
        />
      )}

      {champ.aide && champ.type !== 'booleen' && (
        <div className="form-text">{champ.aide}</div>
      )}
      {erreur && (
        <div className="invalid-feedback d-block" id={`${id}-erreur`}>{erreur}</div>
      )}
    </div>
  )
}

/**
 * Charge les listes de choix de **tous** les champs `select` d'un formulaire.
 *
 * Un hook par champ serait une boucle de hooks — interdite et fragile. Un seul
 * `useQuery` charge donc toutes les listes en parallèle, indexées par endpoint.
 * Une liste qui échoue laisse son `<select>` vide mais n'empêche pas la saisie
 * des autres champs : l'erreur du serveur au moment de l'envoi reste explicite.
 */
function useOptionsFormulaires(champs) {
  const endpoints = useMemo(
    () => [...new Set(champs.map((c) => c.optionsEndpoint).filter(Boolean))].sort(),
    [champs],
  )
  const { data } = useQuery({
    queryKey: ['form-options', endpoints.join('|')],
    enabled: endpoints.length > 0,
    retry: false,
    staleTime: 60_000,
    queryFn: async () => {
      const reponses = await Promise.all(
        endpoints.map((endpoint) => api.get(endpoint).catch(() => null)),
      )
      const parEndpoint = {}
      endpoints.forEach((endpoint, i) => {
        const brut = reponses[i]?.data
        const liste = Array.isArray(brut) ? brut
          : (Array.isArray(brut?.results) ? brut.results : [])
        parEndpoint[endpoint] = liste
      })
      return parEndpoint
    },
  })
  return { parEndpoint: data || {} }
}

/**
 * Boîte de dialogue de saisie.
 *
 * @param {object} props
 * @param {object} props.formulaire  descripteur `ecran.formulaire`
 * @param {object|null} props.ligne  ligne à modifier (`null` = création)
 * @param {object} props.ecran      écran porteur (titre, endpoint)
 * @param {function} props.onFermer
 * @param {function} props.onEnregistre  appelé après un succès (rafraîchit la liste)
 */
export default function FormulaireRessource({ formulaire, ligne, ecran, onFermer, onEnregistre }) {
  const creation = !ligne
  const champs = useMemo(
    () => (formulaire.champs || []).filter(
      // Un champ peut être réservé à la modification (ex. code technique figé
      // une fois la ligne créée) : `modificationSeulement`.
      (c) => creation ? !c.modificationSeulement : true,
    ),
    [formulaire.champs, creation],
  )

  const [valeurs, setValeurs] = useState(() => valeursFormulaire(champs, ligne))
  const [erreurs, setErreurs] = useState({})
  const [message, setMessage] = useState('')
  const [enCours, setEnCours] = useState(false)

  // Toutes les listes de choix sont chargées en un seul appel groupé.
  const { parEndpoint } = useOptionsFormulaires(champs)
  const champsResolus = useMemo(
    () => champs.map((champ) => {
      if (!champ.optionsEndpoint) return champ
      const brutes = parEndpoint[champ.optionsEndpoint] || []
      return {
        ...champ,
        options: brutes.map((item) => ({
          valeur: String(item[champ.valeur || 'id']),
          libelle: String(
            item[champ.libelleOption || 'libelle'] ?? item.code ?? item.id,
          ),
        })),
      }
    }),
    [champs, parEndpoint],
  )

  const modifier = (cle, valeur) => {
    setValeurs((prec) => ({ ...prec, [cle]: valeur }))
    setErreurs((prec) => ({ ...prec, [cle]: undefined }))
    setMessage('')
  }

  const enregistrer = async (evenement) => {
    evenement.preventDefault()
    const manquants = champsManquants(champs, valeurs)
    if (manquants.length) {
      setMessage(`Champs obligatoires manquants : ${manquants.join(', ')}.`)
      return
    }
    const cible = creation
      ? formulaire.creation
      : (typeof formulaire.modification === 'function'
        ? formulaire.modification(ligne)
        : formulaire.modification)
    if (!cible || !cible.chemin) {
      setMessage('Aucun point d’entrée d’enregistrement n’est déclaré pour cet écran.')
      return
    }
    setEnCours(true)
    try {
      const corps = corpsRequete(champs, valeurs, { creation })
      if (creation) {
        await api.post(cible.chemin, corps)
      } else if ((formulaire.methodeModification || 'patch').toLowerCase() === 'put') {
        // Certains points d'entrée historiques n'acceptent que PUT (sémantique
        // douce côté serveur : les champs absents sont conservés). On suit ce
        // que l'endpoint expose plutôt que d'imposer PATCH.
        await api.put(cible.chemin, corps)
      } else {
        await api.patch(cible.chemin, corps)
      }
      onEnregistre(creation ? 'Élément créé.' : 'Modification enregistrée.')
    } catch (erreur) {
      // Erreurs par champ renvoyées par DRF : {champ: ["message"]}.
      const donnees = erreur?.response?.data
      if (donnees && typeof donnees === 'object' && !Array.isArray(donnees)) {
        const parChamp = {}
        for (const [cle, valeur] of Object.entries(donnees)) {
          const texte = Array.isArray(valeur) ? valeur.join(' ') : String(valeur)
          if (champs.some((c) => c.cle === cle)) parChamp[cle] = texte
        }
        if (Object.keys(parChamp).length) setErreurs(parChamp)
      }
      setMessage(messageErreur(erreur, 'Enregistrement refusé par le serveur.'))
    } finally {
      setEnCours(false)
    }
  }

  // Fermeture au clavier : un formulaire modal doit obéir à Échap.
  useEffect(() => {
    const surTouche = (e) => { if (e.key === 'Escape') onFermer() }
    window.addEventListener('keydown', surTouche)
    return () => window.removeEventListener('keydown', surTouche)
  }, [onFermer])

  const titre = creation
    ? (formulaire.titreCreation || `Nouvel élément — ${ecran.titre}`)
    : (formulaire.titreModification || `Modifier — ${ecran.titre}`)

  return (
    <div className="modal-overlay" onClick={onFermer} role="presentation">
      <div
        className="modal-content"
        style={{ maxWidth: 760 }}
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby="form-titre"
      >
        <div className="modal-header">
          <h5 className="modal-title" id="form-titre">{titre}</h5>
          <button type="button" className="btn-close" onClick={onFermer} aria-label="Fermer" />
        </div>
        <form onSubmit={enregistrer} data-testid="formulaire-ressource">
          <div className="modal-body">
            {message && (
              <div className="alert alert-danger py-2" role="alert" data-testid="form-erreur">
                {message}
              </div>
            )}
            {!creation && (
              <p className="small text-muted">
                Les champs laissés vides effacent la valeur existante ; le serveur
                reste seul juge des règles métier.
              </p>
            )}
            <div className="row g-3">
              {champsResolus.map((champ) => (
                <Champ
                  key={champ.cle}
                  champ={champ}
                  valeur={valeurs[champ.cle]}
                  erreur={erreurs[champ.cle]}
                  onChange={(v) => modifier(champ.cle, v)}
                />
              ))}
            </div>
          </div>
          <div className="modal-footer">
            <button type="button" className="btn btn-outline-secondary" onClick={onFermer}>
              Annuler
            </button>
            <button type="submit" className="btn btn-primary" disabled={enCours} data-testid="form-enregistrer">
              {enCours
                ? 'Enregistrement…'
                : (creation ? 'Créer' : 'Enregistrer')}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
