import { Component } from 'react'

/**
 * Garde-fou d'affichage : remplacer la page blanche par un message lisible.
 *
 * Constat du 2026-10-29 : lorsqu'un composant levait une exception au rendu,
 * React démontait l'arbre entier et `#root` devenait vide. L'utilisateur ne
 * voyait alors **rien** — ni erreur, ni écran de connexion — et n'avait aucun
 * moyen de signaler ce qui s'était passé.
 *
 * Ce composant n'intercepte que les erreurs de RENDU (les erreurs asynchrones
 * et les rejets de promesse sont traités par les écouteurs de `main.jsx`).
 * Il n'invente aucun repli fonctionnel : il affiche le fait constaté, le
 * message d'erreur réel et une action (recharger).
 */
export default class ErreurFatale extends Component {
  constructor(props) {
    super(props)
    this.state = { erreur: null, info: null }
  }

  static getDerivedStateFromError(erreur) {
    return { erreur }
  }

  componentDidCatch(erreur, info) {
    // Trace complète en console pour le diagnostic technique ; l'écran, lui,
    // reste lisible par un utilisateur non technique.
    console.error('[INJS-LMD] Erreur fatale au rendu :', erreur, info?.componentStack)
    this.setState({ info })
  }

  render() {
    const { erreur, info } = this.state
    if (!erreur) return this.props.children

    return (
      <div className="erreur-fatale" role="alert" aria-live="assertive">
        <div className="erreur-fatale-carte">
          <h1>L’application n’a pas pu s’afficher</h1>
          <p>
            Une erreur est survenue pendant l’affichage de cette page. Aucune
            donnée n’a été modifiée. Rechargez la page ; si le problème
            persiste, transmettez le message ci-dessous au service informatique.
          </p>
          <p className="erreur-fatale-message">
            <strong>{erreur.name || 'Erreur'} :</strong> {erreur.message || String(erreur)}
          </p>
          {info?.componentStack && (
            <details>
              <summary>Détail technique</summary>
              <pre>{info.componentStack.trim()}</pre>
            </details>
          )}
          <div className="erreur-fatale-actions">
            <button type="button" onClick={() => window.location.reload()}>
              Recharger la page
            </button>
            <button type="button" onClick={() => { window.location.href = '/' }}>
              Revenir à l’accueil
            </button>
          </div>
        </div>
      </div>
    )
  }
}
