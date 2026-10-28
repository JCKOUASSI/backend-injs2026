# Planche de style — module du frontend

La planche de style n'est plus un fichier HTML posé à côté de l'application :
elle est devenue un **écran de l'application**, accessible depuis le menu.

| | |
|---|---|
| **URL** | `/referentiels/planche-de-style` |
| **Menu** | Référentiels → *Planche de style* |
| **Garde** | `ProtectedRoute allowedRoles={ADMIN_LEVEL_ROLES}` + `droit` de l'entrée : `parametres.parametre.consulter` (CURP) / `web.operationnel` (legacy) / trio `ADMIN`, `CHEF_INJS_ADMIN`, `INJS_ADMIN` |
| **Écriture** | aucune — l'écran est en **lecture seule** (voir §5) |

## 1. Origine

`docs/design/apercu-design-system.html` était une planche statique : du HTML
autonome recopiant des classes et des valeurs du socle. Elle rendait service
pour montrer le design system, mais elle ne pouvait pas mentir impunément ni
rester juste dans le temps — chaque modification de `designSystem.css`
demandait de recopier les valeurs à la main.

Le module reprend son contenu (palette, boutons, formulaires, cartes, tableaux,
badges, messages, modale, surfaces en verre, état vide, repère responsive) mais
**lit le socle au lieu de le recopier**. Le fichier statique reste dans le
dépôt comme archive de la maquette validée.

## 2. Fonctionnalités

1. **Lecture réelle des jetons** — les noms proviennent de
   `getComputedStyle(document.documentElement)` **et** d'un parcours récursif de
   `document.styleSheets` (règles `@media` / `@supports` comprises) ; les valeurs
   sont résolues par le navigateur. Aucune valeur n'est écrite en dur dans la
   page. Un jeton déclaré mais non résolu s'affiche « non déclaré » plutôt que
   vide.
2. **Filtrage instantané** — la recherche porte sur le nom *et* sur la valeur
   (`danger`, `#1267D6`), avec un état vide explicite.
3. **Copie d'un jeton** — le bouton place `--nom: valeur;` dans le
   presse-papiers (`navigator.clipboard`, repli `textarea` + `execCommand` en
   contexte non sécurisé), avec retour visuel et annonce `aria-live`.
4. **Contrastes calculés (WCAG 2.2)** — ratios calculés à l'exécution
   (luminance relative officielle), verdicts AA 4,5:1 / AAA 7:1, et mention
   explicite « grand texte uniquement » quand le seuil AA du texte courant n'est
   pas atteint. Le niveau est écrit en toutes lettres : l'information ne dépend
   jamais de la couleur seule.
5. **Repère responsive en direct** — largeur disponible mesurée sur l'élément
   racine (repli sur la fenêtre) et point de rupture actif, recalculés au
   redimensionnement.
6. **Sommaire d'ancres** — navigation clavier vers les dix sections.
7. **Impression** — `window.print()` avec feuille `@media print` dédiée (barre
   de repères, recherche et boutons de copie masqués, sections non coupées).
8. **Démonstration de composants réels** — les boutons, champs, cartes,
   tableaux, badges, messages et surfaces en verre utilisent les classes du
   socle ; la modale est le **vrai** composant `ConfirmModal` (focus capturé,
   Échap = annulation, boutons nommés), borné à une scène d'aperçu.

## 3. Fichiers

| Fichier | Rôle |
|---|---|
| `frontend/src/lib/plancheStyle.js` | logique pure : classement, lecture, filtrage, contraste WCAG, point de rupture |
| `frontend/src/lib/plancheStyle.test.js` | 29 tests, dont l'invariant « aucun jeton du socle n'est non classé » et la garde `.visually-hidden` |
| `frontend/src/pages/design/PlancheDeStyle.jsx` | l'écran |
| `frontend/src/pages/design/PlancheDeStyle.test.jsx` | 14 tests (lecture, filtre, copie, contrastes, responsive, modale, impression, absence d'appel API) |
| `frontend/src/styles/plancheDeStyle.css` | mise en page, portée strictement `.planche*` |
| `frontend/src/App.jsx` | route `/referentiels/planche-de-style` |
| `frontend/src/menu/arborescence.js` | entrée de menu + droits |
| `frontend/src/test/smoke/pages.smoke.test.jsx` | l'écran rejoint les tests de fumée |

## 4. Ce que le module ne fait pas

- **aucun appel API** : l'apparence ne dépend d'aucune donnée serveur
  (un test le vérifie en espionnant `api.get`) ;
- **aucune donnée métier, aucun chiffre inventé** : les exemples de tableaux
  sont des libellés neutres (`INJS-0000-001`, `—`) ;
- **aucune règle du socle n'est redéfinie** : le CSS du module est préfixé
  `.planche` et ne touche ni `designSystem.css`, ni `harmonisation.css` ;
- **aucune nouvelle dépendance** : ni TypeScript, ni Tailwind, ni bibliothèque
  de composants.

## 5. Lecture seule

L'écran ne persiste rien, ne modifie aucun jeton, n'écrit en base ni en
`localStorage`. Il observe le CSS chargé. C'est la raison pour laquelle il
partage la garde des écrans d'administration sans exposer d'action.

## 5 bis. Défaut connexe corrigé — `.visually-hidden`

En construisant l'écran, un défaut **préexistant** a été trouvé : la classe
`.visually-hidden` était employée par plusieurs écrans (`EvaluationsModule`,
planche de style) sans **aucune définition CSS** dans le projet (Bootstrap CSS
n'est pas chargé, seules les icônes le sont). Le texte censé être réservé aux
lecteurs d'écran s'affichait donc visuellement à tout le monde.

L'utilitaire standard a été ajouté au socle (`designSystem.css`, section 13) :
ajout purement **additif**, aucune règle existante n'est modifiée. Deux tests
gardent la définition et vérifient qu'elle masque réellement le contenu.

## 6. Contrôles exécutés

- `npx vitest run` → **103 fichiers, 1 960 tests OK** ;
- `npm run build` → **OK** ;
- `config.tests` (backend) non concerné par ce module : aucun fichier Python
  modifié.

### NOT EXECUTED

- **Vérification visuelle par navigateur** : aucun navigateur ne peut être
  installé dans cet environnement (voir `docs/audit/REFONTE_VISUELLE_2026-10-28.md`,
  section D.3). Le rendu est contrôlé par les tests DOM (jsdom), par le build de
  production et par le service réel des fichiers (module JSX et feuille de
  style répondant 200 sur le serveur de développement).
