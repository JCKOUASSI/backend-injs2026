import { useLocation } from 'react-router-dom'
import EcranRessource from '../components/generique/EcranRessource'
import EcranDocuments from '../components/generique/EcranDocuments'
import { useMenuAutorise } from '../hooks/useMenuAutorise'
import { ecranParId } from '../menu/ecrans'
import { ARBORESCENCE, PIED_DE_BARRE, aplatir } from '../menu/arborescence'
import { droitRequis } from '../menu/autorisation'
import '../styles/ecransGeneriques.css'

/**
 * Libellé de la famille de vue rendue par le moteur générique : sert de
 * plaquette de synthèse dans le bandeau d'accueil (aucune donnée serveur).
 */
function libelleVue(ecran) {
  if (ecran.type === 'documents') return 'Générateur de documents'
  if (ecran.type === 'indicateurs') return 'Indicateurs consolidés'
  if (ecran.recherche || (ecran.filtres || []).length) return 'Liste filtrable'
  return 'Consultation'
}

/**
 * Page hôte des **écrans génériques** de la navigation réorganisée.
 *
 * Elle fait trois choses, dans cet ordre :
 *
 * 1. **résout** le descripteur (`src/menu/ecrans.js`) à partir de l'identifiant
 *    porté par la route — une seule source pour le menu et les routes ;
 * 2. **revérifie l'autorisation** pour le chemin courant : une URL saisie à la
 *    main vers une entrée masquée par le menu affiche un refus explicite plutôt
 *    que des données. Cette défense en profondeur côté interface ne remplace
 *    jamais le contrôle serveur (règle S3 : chaque vue DRF garde ses
 *    `permission_classes`, et c'est elle qui décide) ;
 * 3. **rend** l'écran (liste, onglets, indicateurs ou génération de documents).
 */
export default function EcranGenerique({ id }) {
  const ecran = ecranParId(id)
  const location = useLocation()
  const { parChemin, source } = useMenuAutorise()

  if (!ecran) {
    return (
      <div className="alert alert-warning">
        <strong>Écran inconnu.</strong> Aucun descripteur ne correspond à
        l'identifiant <code>{id}</code>.
      </div>
    )
  }

  const entree = parChemin.get(location.pathname)
  if (!entree) {
    // Le droit requis est porté par l'entrée de menu (pas par le descripteur) :
    // on le retrouve dans l'arborescence complète, non filtrée.
    const entreeComplete = aplatir(ARBORESCENCE, PIED_DE_BARRE)
      .find((e) => e.ecran === id)
    const requis = droitRequis(entreeComplete)
    return (
      <div className="card border-warning">
        <div className="card-body">
          <h5 className="card-title">
            <i className="bi bi-shield-exclamation text-warning me-2"></i>
            Accès non autorisé
          </h5>
          <p className="mb-2">
            Cette entrée ne fait pas partie des droits affichés pour votre compte
            (source : <strong>{source === 'CURP' ? 'permissions effectives CURP' : 'capacités projetées'}</strong>).
            Le serveur reste seul juge : si vous pensez disposer de ce droit,
            contactez un administrateur d'habilitation.
          </p>
          {requis.curp.length > 0 && (
            <p className="small text-muted mb-1">
              Permissions CURP requises : {requis.curp.map((c) => <code key={c} className="me-1">{c}</code>)}
            </p>
          )}
          {requis.legacy.length > 0 && (
            <p className="small text-muted mb-0">
              Capacités requises : {requis.legacy.map((c) => <code key={c} className="me-1">{c}</code>)}
            </p>
          )}
        </div>
      </div>
    )
  }

  return (
    <div data-testid={`ecran-${id}`}>
      <div className="gen-hero">
        {ecran.icone && (
          <span className="gen-hero-icon" aria-hidden="true">
            <i className={`bi ${ecran.icone}`}></i>
          </span>
        )}
        <div className="gen-hero-text">
          {ecran.fil && <span className="gen-hero-eyebrow">{ecran.fil}</span>}
          <h1 className="gen-hero-title">{ecran.titre}</h1>
          {ecran.introduction && (
            <p className="gen-hero-intro">{ecran.introduction}</p>
          )}
        </div>
        <div className="gen-hero-side">
          {ecran.type === 'documents' && (ecran.documents || []).length > 0 && (
            <span className="gen-plaquette gen-plaquette--accent">
              <i className="bi bi-collection" aria-hidden="true"></i>
              {ecran.documents.length} document{ecran.documents.length > 1 ? 's' : ''}
            </span>
          )}
          <span className="gen-plaquette gen-plaquette--soft">
            <i className="bi bi-layers" aria-hidden="true"></i>
            {libelleVue(ecran)}
          </span>
        </div>
      </div>

      {ecran.type === 'documents'
        ? <EcranDocuments ecran={ecran} />
        : <EcranRessource ecran={ecran} cleBase={['ecran-generique', id]} />}
    </div>
  )
}
