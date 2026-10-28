import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import logo from '../../assets/logo-injs.svg'
import ConfirmModal from '../../components/ConfirmModal'
import {
  CATEGORIES,
  extraireJetons,
  filtrerJetons,
  jetonsDepuisStyleCalcule,
  jetonsDepuisFeuilles,
  largeurDisponible,
  pointDeRupture,
  regrouperParCategorie,
  tableContraste,
} from '../../lib/plancheStyle'
import '../../styles/plancheDeStyle.css'

/**
 * Planche de style du socle visuel — écran `/referentiels/planche-de-style`.
 *
 * **Ce que fait cet écran.** Il rend visible le socle `designSystem.css` tel
 * qu'il est réellement chargé par l'application : les jetons affichés sont
 * **lus dans le CSS par le navigateur** (`getComputedStyle` + parcours des
 * feuilles de style), leurs valeurs sont **copiables**, les ratios de
 * contraste sont **calculés** (WCAG 2.2) et la largeur de la fenêtre pilote un
 * repère responsive en direct.
 *
 * **Ce que cet écran ne fait pas.** Aucune requête API (l'apparence ne dépend
 * d'aucune donnée serveur), aucune donnée métier, aucun chiffre inventé : les
 * exemples de composants sont des libellés neutres, et les seuls nombres
 * affichés sont mesurés ou calculés ici.
 *
 * L'écran ne modifie rien : il ne fait qu'observer le socle. Il est donc sans
 * effet sur les règles d'authentification, de permissions et les contrats API.
 */
export default function PlancheDeStyle() {
  const racineRef = useRef(null)
  const [largeur, setLargeur] = useState(0)
  const [jetons, setJetons] = useState([])
  const [recherche, setRecherche] = useState('')
  const [copie, setCopie] = useState(null)
  const [modaleOuverte, setModaleOuverte] = useState(false)

  /* ── Lecture des jetons réellement chargés ──────────────────────────────── */
  useEffect(() => {
    const racine = document.documentElement
    // Une seule lecture de la déclaration calculée : elle sert à la fois à
    // énumérer les noms et à résoudre les valeurs (pas de recalcul par jeton).
    const declaration = window.getComputedStyle(racine)

    const noms = new Set([
      ...jetonsDepuisStyleCalcule(declaration),
      ...jetonsDepuisFeuilles(document.styleSheets),
    ])

    // Le parcours des feuilles est disponible pour les styles locaux ; si un
    // navigateur ne l'expose pas, la liste connue du socle sert de repère pour
    // les noms, mais **les valeurs restent lues dans le CSS** (jamais devinées).
    const nomsTries = [...noms].sort((a, b) => a.localeCompare(b, 'fr'))
    setJetons(extraireJetons((nom) => declaration.getPropertyValue(nom), nomsTries))
  }, [])

  /* ── Repère responsive ──────────────────────────────────────────────────── */
  useEffect(() => {
    const mesurer = () => setLargeur(largeurDisponible(racineRef.current, window))
    mesurer()
    window.addEventListener('resize', mesurer)
    return () => window.removeEventListener('resize', mesurer)
  }, [])

  /* ── Copie d'un jeton (presse-papiers, avec repli) ──────────────────────── */
  const copier = useCallback(async (nom, valeur) => {
    const texte = `${nom}: ${valeur};`
    let fait = false
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(texte)
        fait = true
      }
    } catch {
      fait = false
    }
    if (!fait) {
      // Repli sans presse-papiers asynchrone (contexte non sécurisé) : on
      // sélectionne le texte dans une zone temporaire pour que l'utilisateur
      // puisse copier lui-même — le retour visuel reste identique.
      const zone = document.createElement('textarea')
      zone.value = texte
      zone.setAttribute('readonly', '')
      zone.style.position = 'fixed'
      zone.style.opacity = '0'
      document.body.appendChild(zone)
      zone.select()
      try {
        fait = document.execCommand?.('copy') ?? false
      } catch {
        fait = false
      }
      document.body.removeChild(zone)
    }
    setCopie(fait ? nom : null)
    window.setTimeout(() => setCopie(null), 2000)
  }, [])

  const jetonsFiltres = useMemo(() => filtrerJetons(jetons, recherche), [jetons, recherche])
  const groupes = useMemo(() => regrouperParCategorie(jetonsFiltres), [jetonsFiltres])
  const contrastes = useMemo(() => tableContraste(), [])
  const echappementsSelectionnes = useMemo(
    () => jetonsFiltres.filter((jeton) => jeton.categorie.id === 'couleur'),
    [jetonsFiltres],
  )

  const sections = [
    { id: 'palette', libelle: 'Palette', icone: 'bi-palette' },
    { id: 'jetons', libelle: 'Jetons', icone: 'bi-code-slash' },
    { id: 'contrastes', libelle: 'Contrastes', icone: 'bi-circle-half' },
    { id: 'boutons', libelle: 'Boutons', icone: 'bi-hand-index' },
    { id: 'formulaires', libelle: 'Formulaires', icone: 'bi-input-cursor-text' },
    { id: 'cartes', libelle: 'Cartes', icone: 'bi-grid-1x2' },
    { id: 'tableau', libelle: 'Tableaux', icone: 'bi-table' },
    { id: 'messages', libelle: 'Messages', icone: 'bi-chat-square-text' },
    { id: 'modale', libelle: 'Modale', icone: 'bi-window-stack' },
    { id: 'verre', libelle: 'Verre', icone: 'bi-layers' },
  ]

  const nombreAffiche = jetonsFiltres.length
  const nombreTotal = jetons.length

  return (
    <div className="planche" ref={racineRef}>
      <header className="planche__entete">
        <img src={logo} alt="INJS Abidjan" className="planche__logo" width="56" height="56" />
        <div className="planche__entete-texte">
          <h4 className="planche__titre">Planche de style — socle visuel INJS</h4>
          <p className="planche__sous-titre">
            Jetons lus dans le CSS de l’application (aucune valeur recopiée à la main),
            contrastes calculés selon WCAG 2.2.
          </p>
        </div>
        <button
          type="button"
          className="btn btn-outline-primary btn-sm ms-auto"
          onClick={() => window.print()}
        >
          <i className="bi bi-printer me-1" aria-hidden="true"></i>
          Imprimer la planche
        </button>
      </header>

      <div className="planche__reperes">
        <span>
          Largeur disponible : <span className="planche__repere-valeur">{largeur || '—'}</span> px
        </span>
        <span>
          Point de rupture : <span className="planche__repere-valeur">{pointDeRupture(largeur)}</span>
        </span>
        <span>
          Jetons : <span className="planche__repere-valeur">{nombreAffiche}</span>
          {nombreAffiche !== nombreTotal ? ` / ${nombreTotal}` : null}
        </span>
        <span className="planche__repere-note">
          Réduisez la fenêtre pour vérifier 360 · 390 · 768 · 1024 · 1366 · 1440 · 1920 px.
        </span>

        <div className="planche__recherche">
          <label className="form-label mb-0" htmlFor="planche-recherche">
            Filtrer les jetons
          </label>
          <input
            id="planche-recherche"
            type="search"
            className="form-control"
            placeholder="nom ou valeur (ex. danger, #1267D6)"
            value={recherche}
            onChange={(evenement) => setRecherche(evenement.target.value)}
          />
        </div>
      </div>

      <nav aria-label="Sommaire de la planche">
        <ul className="planche__sommaire">
          {sections.map((section) => (
            <li key={section.id}>
              <a href={`#planche-${section.id}`}>
                <i className={`bi ${section.icone}`} aria-hidden="true"></i>
                {section.libelle}
              </a>
            </li>
          ))}
        </ul>
      </nav>

      {/* ─────────────────────────────── Palette ─────────────────────────────── */}
      <section className="planche__section" id="planche-palette" aria-labelledby="titre-palette">
        <h5 className="planche__section-titre" id="titre-palette">Palette officielle</h5>
        <p className="planche__note">
          Une couleur = un sens : bleu pour l’action principale, vert pour le succès,
          orange pour l’attention, rouge pour le destructif, violet pour l’analytique,
          turquoise pour l’information.
        </p>
        {echappementsSelectionnes.length === 0 ? (
          <div className="planche__vide">
            Aucun jeton de couleur ne correspond au filtre « {recherche} ».
          </div>
        ) : (
          <ul className="planche__palette">
            {echappementsSelectionnes.map((jeton) => (
              <li key={jeton.nom} className="planche__teinte">
                <span
                  className="planche__teinte-echantillon"
                  style={{ background: jeton.valeur || 'transparent' }}
                  aria-hidden="true"
                ></span>
                <span className="planche__teinte-texte">
                  <span className="planche__teinte-nom">{jeton.nom.replace('--injs-', '')}</span>
                  <span className="planche__teinte-valeur">
                    {jeton.valeur || <em className="planche__valeur--absente">non déclaré</em>}
                  </span>
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* ──────────────────────────────── Jetons ─────────────────────────────── */}
      <section className="planche__section" id="planche-jetons" aria-labelledby="titre-jetons">
        <h5 className="planche__section-titre" id="titre-jetons">Jetons du socle</h5>
        <p className="planche__note">
          Valeurs résolues par le navigateur. Le bouton de copie place
          <code className="planche__code"> --nom: valeur;</code> dans le presse-papiers.
        </p>
        <p aria-live="polite" className="planche__repere-note" data-testid="retour-copie">
          {copie ? `Copié : ${copie}` : ''}
        </p>

        {groupes.length === 0 ? (
          <div className="planche__vide">
            <i className="bi bi-inbox" aria-hidden="true"></i>
            <p className="mb-0 mt-2">
              Aucun jeton à afficher. Vérifiez que <code className="planche__code">designSystem.css</code> est chargé.
            </p>
          </div>
        ) : (
          groupes.map((groupe) => (
            <div className="table-responsive mb-4" key={groupe.id}>
              <table className="planche__table-jetons">
                <caption>{groupe.libelle} ({groupe.jetons.length})</caption>
                <thead>
                  <tr>
                    <th scope="col">Jeton</th>
                    <th scope="col">Valeur</th>
                    <th scope="col">
                      <span className="visually-hidden">Copier</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {groupe.jetons.map((jeton) => (
                    <tr key={jeton.nom}>
                      <th scope="row" className="planche__code" style={{ fontWeight: 600 }}>
                        {jeton.nom}
                      </th>
                      <td className="planche__valeur">
                        {jeton.valeur || <span className="planche__valeur--absente">non déclaré</span>}
                      </td>
                      <td>
                        <button
                          type="button"
                          className={`planche__copier${copie === jeton.nom ? ' planche__copier--fait' : ''}`}
                          onClick={() => copier(jeton.nom, jeton.valeur || '')}
                          disabled={!jeton.valeur}
                          aria-label={`Copier ${jeton.nom}`}
                          title={`Copier ${jeton.nom}`}
                        >
                          <i
                            className={`bi ${copie === jeton.nom ? 'bi-check2' : 'bi-clipboard'}`}
                            aria-hidden="true"
                          ></i>
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))
        )}
      </section>

      {/* ────────────────────────────── Contrastes ───────────────────────────── */}
      <section className="planche__section" id="planche-contrastes" aria-labelledby="titre-contrastes">
        <h5 className="planche__section-titre" id="titre-contrastes">Contrastes calculés (WCAG 2.2)</h5>
        <p className="planche__note">
          Ratios calculés en direct à partir des teintes du socle. Le verdict porte sur du
          <strong> texte courant</strong> ; un écart est signalé explicitement plutôt que masqué,
          et chaque ligne reste lisible sans se fier à la couleur seule (le niveau est écrit).
        </p>
        <div className="table-responsive">
          <table className="planche__table-jetons">
            <caption>Texte sur fond — seuils AA 4,5:1 et AAA 7:1</caption>
            <thead>
              <tr>
                <th scope="col">Usage</th>
                <th scope="col">Aperçu</th>
                <th scope="col">Ratio</th>
                <th scope="col">Verdict</th>
              </tr>
            </thead>
            <tbody>
              {contrastes.map((ligne) => (
                <tr key={ligne.libelle}>
                  <th scope="row" style={{ fontWeight: 600 }}>{ligne.libelle}</th>
                  <td>
                    <span
                      className="planche__echantillon-texte"
                      style={{ color: ligne.texte, background: ligne.fond }}
                    >
                      Aa
                    </span>
                  </td>
                  <td className="planche__ratio">{ligne.ratioAffiche}</td>
                  <td>
                    <span className="planche__verdict">
                      <i
                        className={`bi ${ligne.verdict.conformeAA ? 'bi-check-circle-fill text-success' : 'bi-exclamation-triangle-fill text-warning'}`}
                        aria-hidden="true"
                      ></i>
                      {ligne.verdict.niveau}
                      <span className="planche__repere-note">— {ligne.verdict.usage}</span>
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* ─────────────────────────────── Boutons ─────────────────────────────── */}
      <section className="planche__section" id="planche-boutons" aria-labelledby="titre-boutons">
        <h5 className="planche__section-titre" id="titre-boutons">Boutons</h5>
        <p className="planche__note">Classes réelles du socle — aucune variante inventée pour la planche.</p>
        <div className="planche__ligne">
          <button type="button" className="btn btn-primary">Action principale</button>
          <button type="button" className="btn btn-secondary">Secondaire</button>
          <button type="button" className="btn btn-success">Valider</button>
          <button type="button" className="btn btn-warning">Attention</button>
          <button type="button" className="btn btn-danger">Supprimer</button>
          <button type="button" className="btn btn-info">Information</button>
          <button type="button" className="btn btn-dfrc">DFRC</button>
          <button type="button" className="btn btn-premium-primary">Premium</button>
        </div>
        <div className="planche__ligne">
          <button type="button" className="btn btn-outline-primary">Outline primaire</button>
          <button type="button" className="btn btn-outline-success">Outline succès</button>
          <button type="button" className="btn btn-outline-danger">Outline destructif</button>
          <button type="button" className="btn btn-outline-info">Outline info</button>
          <button type="button" className="btn btn-premium-glass">Verre</button>
        </div>
        <div className="planche__ligne">
          <button type="button" className="btn btn-primary btn-sm">Petit</button>
          <button type="button" className="btn btn-primary btn-lg">Grand</button>
          <button type="button" className="btn btn-primary" disabled>Désactivé</button>
          <button type="button" className="btn btn-primary is-loading">Chargement</button>
          <button type="button" className="btn btn-icon" aria-label="Bouton icône — exemple">
            <i className="bi bi-star" aria-hidden="true"></i>
          </button>
        </div>
      </section>

      {/* ───────────────────────────── Formulaires ───────────────────────────── */}
      <section className="planche__section" id="planche-formulaires" aria-labelledby="titre-formulaires">
        <h5 className="planche__section-titre" id="titre-formulaires">Formulaires</h5>
        <p className="planche__note">
          Libellés reliés aux champs ; l’erreur est portée par une icône, un texte et
          <code className="planche__code"> aria-describedby</code> — jamais par la couleur seule.
        </p>
        <div className="form-grid">
          <div>
            <label className="form-label" htmlFor="planche-champ-1">Nom d’utilisateur</label>
            <input className="form-control" id="planche-champ-1" placeholder="prenom.nom" />
          </div>
          <div>
            <label className="form-label" htmlFor="planche-champ-2">Profil</label>
            <select className="form-select" id="planche-champ-2" defaultValue="">
              <option value="" disabled>Choisir un profil</option>
              <option value="admin">Administrateur</option>
              <option value="enseignant">Enseignant</option>
              <option value="etudiant">Étudiant</option>
            </select>
          </div>
          <div>
            <label className="form-label required" htmlFor="planche-champ-3">Champ en erreur</label>
            <input
              className="form-control is-invalid"
              id="planche-champ-3"
              defaultValue="valeur invalide"
              aria-describedby="planche-erreur-3"
              aria-invalid="true"
            />
            <div className="form-error" id="planche-erreur-3" role="alert">
              <i className="bi bi-exclamation-octagon-fill me-1" aria-hidden="true"></i>
              Ce champ est obligatoire.
            </div>
          </div>
          <div>
            <label className="form-label" htmlFor="planche-champ-4">Champ désactivé</label>
            <input className="form-control" id="planche-champ-4" defaultValue="lecture seule" disabled />
          </div>
        </div>
      </section>

      {/* ──────────────────────────────── Cartes ─────────────────────────────── */}
      <section className="planche__section" id="planche-cartes" aria-labelledby="titre-cartes">
        <h5 className="planche__section-titre" id="titre-cartes">Cartes</h5>
        <p className="planche__note">
          Fond opaque, bordure 1 px, ombre douce. Aucun verre sur les zones de données.
          Les libellés sont neutres : la planche n’affiche aucune valeur métier.
        </p>
        <div className="planche__grille">
          <div className="card">
            <div className="card-header card-header-bar">Indicateur principal</div>
            <div className="card-body">
              <div style={{ fontSize: '1.9rem', fontWeight: 800, color: 'var(--injs-navy)' }}>—</div>
              <span className="badge badge-info">Valeur fournie par l’écran métier</span>
            </div>
          </div>
          <div className="card card-accent">
            <div className="card-header">Carte accentuée</div>
            <div className="card-body">
              <div style={{ fontSize: '1.9rem', fontWeight: 800, color: 'var(--injs-navy)' }}>—</div>
              <span className="badge badge-warning">À relancer</span>
            </div>
          </div>
          <div className="card">
            <div className="card-header">Carte neutre</div>
            <div className="card-body">
              <div style={{ fontSize: '1.9rem', fontWeight: 800, color: 'var(--injs-navy)' }}>—</div>
              <span className="status-pill badge-neutral">Statut</span>
            </div>
          </div>
        </div>
      </section>

      {/* ─────────────────────────────── Tableau ─────────────────────────────── */}
      <section className="planche__section" id="planche-tableau" aria-labelledby="titre-tableau">
        <h5 className="planche__section-titre" id="titre-tableau">Tableaux de données</h5>
        <p className="planche__note">
          Densité maîtrisée, en-tête institutionnel, défilement horizontal sur petit écran.
          Lignes d’exemple, sans aucune donnée réelle.
        </p>
        <div className="table-responsive">
          <table className="table">
            <caption className="visually-hidden">Exemple de tableau de données</caption>
            <thead>
              <tr>
                <th scope="col">Identifiant</th>
                <th scope="col">Libellé</th>
                <th scope="col">Statut</th>
                <th scope="col">Montant</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>INJS-0000-001</td>
                <td>Ligne d’exemple</td>
                <td><span className="badge badge-success">Validé</span></td>
                <td>—</td>
              </tr>
              <tr className="is-selected">
                <td>INJS-0000-002</td>
                <td>Ligne sélectionnée</td>
                <td><span className="badge badge-warning">En attente</span></td>
                <td>—</td>
              </tr>
              <tr>
                <td>INJS-0000-003</td>
                <td>Ligne d’exemple</td>
                <td><span className="badge badge-danger">Refusé</span></td>
                <td>—</td>
              </tr>
              <tr>
                <td>INJS-0000-004</td>
                <td>Ligne d’exemple</td>
                <td><span className="badge badge-neutral">Inactif</span></td>
                <td>—</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div className="planche__ligne mt-3">
          <span className="badge badge-success">Validé</span>
          <span className="badge badge-warning">Attention</span>
          <span className="badge badge-danger">Refusé</span>
          <span className="badge badge-info">Information</span>
          <span className="badge badge-neutral">Neutre</span>
        </div>
        <div className="planche__vide mt-3">
          <i className="bi bi-inbox" aria-hidden="true"></i> État vide : la planche n’affiche
          jamais un tableau nu, mais un message explicite.
        </div>
      </section>

      {/* ─────────────────────────────── Messages ────────────────────────────── */}
      <section className="planche__section" id="planche-messages" aria-labelledby="titre-messages">
        <h5 className="planche__section-titre" id="titre-messages">Messages</h5>
        <p className="planche__note">
          Quatre niveaux distinguables sans la couleur : icône + rôle ARIA + texte.
        </p>
        <div className="alert alert-success" role="status">
          <i className="bi bi-check-circle-fill me-1" aria-hidden="true"></i>
          Opération enregistrée avec succès.
        </div>
        <div className="alert alert-warning" role="alert">
          <i className="bi bi-exclamation-triangle-fill me-1" aria-hidden="true"></i>
          Certaines données restent à rapprocher.
        </div>
        <div className="alert alert-danger" role="alert">
          <i className="bi bi-x-octagon-fill me-1" aria-hidden="true"></i>
          Action refusée : permissions insuffisantes.
        </div>
        <div className="alert alert-info" role="status">
          <i className="bi bi-info-circle-fill me-1" aria-hidden="true"></i>
          Information à l’attention de l’utilisateur.
        </div>
      </section>

      {/* ──────────────────────────────── Modale ─────────────────────────────── */}
      <section className="planche__section" id="planche-modale" aria-labelledby="titre-modale">
        <h5 className="planche__section-titre" id="titre-modale">Modale de confirmation</h5>
        <p className="planche__note">
          Composant <strong>réel</strong> de l’application (<code className="planche__code">ConfirmModal</code>) :
          focus capturé, Échap = annulation, boutons nommés. L’aperçu est borné à la scène ci-dessous.
        </p>
        <div className="planche__ligne">
          <button type="button" className="btn btn-danger" onClick={() => setModaleOuverte(true)}>
            Ouvrir la modale de démonstration
          </button>
        </div>
        <div className="planche__scene" aria-hidden={!modaleOuverte}>
          {modaleOuverte ? (
            <ConfirmModal
              message="Confirmer la suppression"
              detail="Démonstration : cette action ne supprime aucune donnée, la planche est en lecture seule."
              confirmLabel="Supprimer"
              cancelLabel="Annuler"
              variant="danger"
              onConfirm={() => setModaleOuverte(false)}
              onCancel={() => setModaleOuverte(false)}
            />
          ) : (
            <div className="planche__vide" style={{ border: 0, background: 'transparent', height: '100%' }}>
              <i className="bi bi-window-stack" aria-hidden="true"></i>
              <p className="mb-0 mt-2">La modale s’affiche ici, à l’ouverture.</p>
            </div>
          )}
        </div>
      </section>

      {/* ──────────────────────────────── Verre ──────────────────────────────── */}
      <section className="planche__section" id="planche-verre" aria-labelledby="titre-verre">
        <h5 className="planche__section-titre" id="titre-verre">Surfaces en verre</h5>
        <p className="planche__note">
          Trois niveaux, jamais sur les tableaux, les formulaires ni les textes denses ;
          repli opaque automatique si le navigateur ne gère pas <code className="planche__code">backdrop-filter</code>.
        </p>
        <div className="planche__grille">
          <div className="glass-panel-1" style={{ padding: '1.25rem' }}>
            <strong>Verre niveau 1</strong>
            <br />
            <span className="planche__note">Barres et en-têtes flottants</span>
          </div>
          <div className="glass-panel-2" style={{ padding: '1.25rem' }}>
            <strong>Verre niveau 2</strong>
            <br />
            <span className="planche__note">Panneaux secondaires</span>
          </div>
          <div className="glass-panel-3" style={{ padding: '1.25rem' }}>
            <strong>Verre niveau 3</strong>
            <br />
            <span className="planche__note">Carte quasi opaque</span>
          </div>
        </div>
      </section>
    </div>
  )
}

/** Catégories exposées pour la documentation et les tests d’invariants. */
export { CATEGORIES }
