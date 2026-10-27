import React from 'react'
import ReactDOM from 'react-dom/client'
import { QueryClientProvider } from '@tanstack/react-query'
import App from './App.jsx'
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

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </React.StrictMode>,
)
