import { QueryClient } from '@tanstack/react-query'

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5 * 60 * 1000,
      gcTime: 15 * 60 * 1000,
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
})

export const REFERENTIELS_QUERY_KEY = ['referentiels']
export const SECRETARIATS_QUERY_KEY = ['secretariats']
// Capacités effectives dérivées du backend (P00-06) : invalidées à la
// connexion, la déconnexion et tout rafraîchissement de profil.
export const CAPABILITIES_QUERY_KEY = ['auth', 'capabilities']
// Feature flags (P00-08) : carte {cle: bool} évaluée serveur ; invalidée à
// la connexion/déconnexion et après toute bascule depuis l'écran d'admin.
export const FLAGS_QUERY_KEY = ['parametres', 'flags']

// Navigation RBAC : état gouverné du compte connecté (profil CURP, statut,
// permissions effectives). Invalider cette clé après tout geste d'habilitation
// qui touche le compte courant (attribution, révocation, suspension).
export const MES_ACCES_QUERY_KEY = ['habilitations', 'mes-acces']
