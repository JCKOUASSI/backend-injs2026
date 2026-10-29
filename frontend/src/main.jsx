import React from 'react'
import ReactDOM from 'react-dom/client'
import { QueryClientProvider } from '@tanstack/react-query'
import App from './App.jsx'
import ErreurFatale from './components/ErreurFatale.jsx'
import { queryClient } from './lib/queryClient.js'
// Icônes servies EN LOCAL (embarquées par Vite) : plus aucune dépendance
// à un CDN externe qui pourrait être bloqué et gêner le chargement.
import 'bootstrap-icons/font/bootstrap-icons.css'
import './index.css'
import './styles/finance.css'
import './styles/login.css'
// Doit être importé EN DERNIER : cette feuille harmonise le design de
// référence (Dashboard Engine) sur tous les autres tableaux de bord et
// fenêtres. Chargée après index.css / finance.css, elle prend donc le
// dessus sur la cascade. Ne jamais la remonter.
import './styles/harmonisation.css'
// Socle de design institutionnel INJS-LMD 2026 (tokens + composants).
// Importé APRÈS les feuilles historiques : il unifie la palette autour du
// bleu officiel du logo (#283A87) et prend le dessus sur la cascade.
// Ne pas le remonter avant index.css, sinon les anciens tokens gagnent.
import './styles/designSystem.css'
// Écran GET-INJS (demande 21) : feuille strictement locale à cet écran.
import './styles/getinjs.css'
// Garde-fous d'affichage (page blanche → message lisible).
import './styles/erreurFatale.css'

/**
 * Erreurs hors rendu React : promesses rejetées, erreurs d'événement, échec
 * de chargement d'un module. Sans cela, elles ne laissaient aucune trace
 * visible et l'écran restait blanc.
 */
function signalerErreurGlobale(message) {
  let bandeau = document.getElementById('bandeau-erreur-globale')
  if (!bandeau) {
    bandeau = document.createElement('div')
    bandeau.id = 'bandeau-erreur-globale'
    bandeau.className = 'bandeau-erreur-globale'
    bandeau.setAttribute('role', 'alert')
    const fermer = document.createElement('button')
    fermer.type = 'button'
    fermer.setAttribute('aria-label', 'Masquer ce message')
    fermer.textContent = '×'
    fermer.addEventListener('click', () => bandeau.remove())
    bandeau.appendChild(document.createElement('span'))
    bandeau.appendChild(fermer)
    document.body.appendChild(bandeau)
  }
  bandeau.firstChild.textContent = message
}

if (typeof window !== 'undefined') {
  window.addEventListener('unhandledrejection', (evenement) => {
    const raison = evenement?.reason
    const message = raison?.message || String(raison || 'Promesse rejetée')
    console.error('[INJS-LMD] Promesse rejetée :', raison)
    signalerErreurGlobale(`Opération interrompue : ${message}`)
  })
  window.addEventListener('error', (evenement) => {
    // Les erreurs de chargement de ressource sont déjà traitées par le
    // garde-fou de index.html ; on ne double pas le message.
    if (evenement?.target && evenement.target !== window) return
    const message = evenement?.message || 'Erreur inattendue'
    console.error('[INJS-LMD] Erreur :', evenement?.error || message)
    signalerErreurGlobale(`Erreur : ${message}`)
  })
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    {/* Le garde-fou est le plus HAUT possible : une erreur dans un
        fournisseur de contexte (client de requêtes, authentification) doit
        aussi produire un message au lieu d'une page blanche. */}
    <ErreurFatale>
      <QueryClientProvider client={queryClient}>
        <App />
      </QueryClientProvider>
    </ErreurFatale>
  </React.StrictMode>,
)
