import { lazy, Suspense } from 'react'
import { Route } from 'react-router-dom'
import ProtectedRoute from '../components/auth/ProtectedRoute'
import Layout, { FilAriane } from '../components/layout/Layout'
import EcranGenerique from '../pages/EcranGenerique'
import { ARBORESCENCE, PIED_DE_BARRE } from './arborescence'

/**
 * Routes des écrans génériques, **dérivées de l'arborescence** du menu.
 *
 * Une seule source de vérité : `menu/arborescence.js`. Toute entrée déclarant
 * un `ecran` obtient automatiquement sa route, son fil d'Ariane et son garde
 * d'authentification — ajouter un écran au menu suffit à l'exposer, et le
 * retirer du menu (ou du descripteur) suffit à le fermer.
 *
 * Garde en deux niveaux, conformément à la règle S3 :
 * 1. `ProtectedRoute` exige une session authentifiée (et le changement de mot
 *    de passe obligatoire le cas échéant) ;
 * 2. `EcranGenerique` revérifie que le chemin courant figure bien dans le menu
 *    autorisé du compte — une URL saisie à la main n'ouvre pas un écran masqué.
 *
 * Le contrôle **réel** reste côté serveur : chaque endpoint appelé applique ses
 * propres `permission_classes`.
 */

const Aide = lazy(() => import('../pages/Aide'))

const REPLI_CHARGEMENT = <div className="loading"><div className="spinner" /></div>

/** Construit le tableau d'éléments `<Route>` à insérer dans `<Routes>`. */
export function routesGeneriques(arbre = ARBORESCENCE, pied = PIED_DE_BARRE) {
  const routes = []
  const cheminsVus = new Set()

  const ajouter = (item, section) => {
    if (!item?.ecran || !item?.chemin) return
    if (cheminsVus.has(item.chemin)) return
    cheminsVus.add(item.chemin)

    const segments = []
    if (section && section.id !== item.id) segments.push({ libelle: section.libelle })
    segments.push({ libelle: item.libelle })

    routes.push(
      <Route
        key={item.chemin}
        path={item.chemin}
        element={(
          <ProtectedRoute>
            <Layout breadcrumb={<FilAriane segments={segments} />}>
              <Suspense fallback={REPLI_CHARGEMENT}>
                {item.ecran === 'aide' ? <Aide /> : <EcranGenerique id={item.ecran} />}
              </Suspense>
            </Layout>
          </ProtectedRoute>
        )}
      />,
    )
  }

  for (const section of arbre) {
    ajouter(section, null)
    for (const enfant of section.enfants || []) ajouter(enfant, section)
  }
  for (const item of pied) ajouter(item, null)

  return routes
}

export default routesGeneriques
