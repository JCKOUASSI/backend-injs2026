# Refonte visuelle premium — INJS Abidjan

**Date :** 28 octobre 2026
**Commit :** `438c87a` (branche `arena/d40e4a41-backend-injs2026`)
**Périmètre :** frontend React (Vite 7) + écran de connexion de l'admin Django
**Statut global :** **VALIDÉ AVEC RÉSERVES** — voir section E.

---

## A. Design

### A.1 Palette

Le brief imposait `#1267D6` / `#35BDF5`. Le logo officiel de l'INJS est en
`#283A87` (indigo institutionnel). **La palette a été harmonisée autour du logo**,
pas l'inverse : une charte qui jure avec l'emblème officiel est une charte fausse.

| Rôle | Valeur | Usage |
|---|---|---|
| Indigo officiel (pivot) | `#283A87` | identité, logo, titres forts |
| Navy profond | `#071B3A` → `#0B2D5B` → `#1D2B66` | barres latérales, fonds de connexion |
| Bleu institutionnel | `#104A8E` | en-têtes, liens sur fond clair |
| Bleu royal (action) | `#1267D6` | bouton principal, focus |
| Bleu ciel | `#35BDF5` | accents, survols, séparateurs |
| Succès | `#0A6340` → `#0F8152` | validation, confirmations |
| Attention | `#8A5A00` sur `#FFF4DF` | avertissements |
| Destructif | `#DC3545` / `#A3222F` | suppressions, refus |
| Info | `#5AE0E0` sur navy | messages informatifs |
| Analytique | violet | graphiques uniquement |

Les **42 tokens historiques** de `src/index.css` et les classes `.px-*` de
`premiumCommun.css` et `harmonisation.css` ne sont pas supprimés : les nouveaux
tokens les **aliasent**. Aucun écran existant ne peut se retrouver sans couleur.

### A.2 Logo officiel

`src/assets/logo-injs.svg` et `backend/static/img/logo-injs.svg` sont les seuls
fichiers autorisés, utilisés tels quels :

- plaque blanche systématique (`.login-logo-frame`, `.injs-login-icon-box`,
  `.sidebar-logo`), `object-fit: contain`, ratio préservé ;
- **aucun filtre** : l'ancien `filter: brightness(0) invert(1)` du `.sidebar-logo`
  écrasait les couleurs de l'emblème — supprimé ;
- aucun logo généré, aucun fond dégradé sous le logo, aucune variante inventée.

### A.3 Composants

Le socle `frontend/src/styles/designSystem.css` (812 lignes, 12 sections) stylise
les primitives déjà présentes dans le code, **sans nouvelle bibliothèque** :

- **Boutons** : `.btn` + variantes sémantiques (`primary`, `success`, `warning`,
  `danger`, `info`, `outline-*`, `ghost`), états `hover` / `active` / `disabled`,
  `:focus-visible` unique et visible. Couleur = **sens**, pas décoration.
- **Formulaires** : `.form-control`, `.form-select`, libellés associés, aide,
  erreur non signalée par la couleur seule (icône + texte), zone tactile ≥ 40 px.
- **Cartes** : `.card`, `.card-header`, `.card-body`, ombres douces, 1 px de bordure.
- **Tableaux** : `.table` dense et lisible, en-tête institutionnel, en-tête collant
  **uniquement** dans `.table-responsive` (sinon il flotte sur la page).
- **Badges / pastilles** : états métier explicites.
- **Modales** : `.modal-overlay` / `.modal-content` / `.modal-header` / `.modal-footer`
  alignés, pied replié en colonne sur mobile, fermeture Escape, focus capturé.
- **États vides et chargement** : message explicite, jamais un tableau nu.

### A.4 Glassmorphism maîtrisé

Trois niveaux de verre (`--injs-glass-1/2/3`) avec `backdrop-filter` et **repli
opaque garanti** par `@supports not (backdrop-filter: blur(1px))`.
Le verre n'est **jamais** appliqué aux tableaux, aux formulaires, ni aux blocs de
texte dense : ces zones restent opaques pour la lisibilité.
Pas de pulsation permanente, pas de néon, pas d'ombre à plus de 30 px de flou.

---

## B. Périmètre traité

| Zone | État |
|---|---|
| Socle de design central | **créé** — 812 lignes, importé en dernier dans `main.jsx` |
| Connexion React | **refondue** — carte verre, plaque logo, champs, erreurs, responsive |
| Connexion admin Django | **refondue** — template + CSS servis par `collectstatic` |
| Barre latérale | **alignée** — dégradé institutionnel, logo sans filtre |
| Tableaux de bord | **alignés** — tokens `dashboardEngine` dédupliqués vers le socle |
| Modales, tableaux, formulaires, boutons, badges | **couverts** par le socle |
| Modules métier (15 CSS de module) | **héritent** des primitives ; leurs règles propres sont conservées |

Couverture mesurée sur le code réel : **117 fichiers d'écran/composant sur 141
(82 %)** utilisent au moins une primitive stylée par le socle — 694 boutons,
408 cartes, 340 champs, 193 tableaux, 139 badges, 47 en-têtes de modale.

Aucune route, aucun contrat API, aucune règle d'authentification, aucun filtre,
aucune pagination et aucune validation n'a été modifié. Le backend n'a été touché
que sur **deux fichiers de présentation** (`templates/admin/login.html`,
`static/admin/login.css`).

---

## C. Fichiers

### Créés

| Fichier | Justification |
|---|---|
| `frontend/src/styles/designSystem.css` | socle unique : tokens, primitives, responsive, accessibilité, impression |

### Modifiés

| Fichier | Nature |
|---|---|
| `frontend/src/main.jsx` | import du socle **en dernier**, après `harmonisation.css` (commentaire d'avertissement pour éviter une remontée accidentelle) |
| `frontend/src/index.css` | 6 tokens d'espacement dupliqués retirés — source unique désormais dans le socle |
| `frontend/src/styles/dashboardEngine.css` | 24 tokens `--injs-*` contradictoires (rayons 12 px, vert `#10B981`, cyan `#38BDF8`) convertis en **alias** ; 3 cycles `--x: var(--x)` supprimés |
| `frontend/src/styles/login.css` | réécriture complète, classes d'origine conservées |
| `frontend/src/styles/sidebar.css` | retrait du filtre sur le logo, dégradé institutionnel |
| `backend/templates/admin/login.html` | réécriture : logo statique, bouton de révélation, `role="alert"`, `next` |
| `backend/static/admin/login.css` | réécriture complète (9 640 o servis) |

### Supprimés

Aucun.

---

## D. Validation

### D.1 Contrôles exécutés

| Contrôle | Résultat |
|---|---|
| `npm run build` | ✅ **built in 3.75s** (avertissement chunk > 500 kB : préexistant) |
| `npx vitest run` | ✅ **101 fichiers / 1 912 tests** |
| `manage.py test config.tests.test_apercu_hardening authentication` | ✅ **261 tests OK** (skipped=1) |
| `/admin/login/` rendu (sans auto-connexion) | ✅ **200 · 19 773 o**, logo officiel, `login.css` lié, libellés conformes, **0 identifiant et 0 mot de passe préremplis** |
| Ressources statiques | ✅ `login.css` 200 (9 640 o) · `logo-injs.svg` 200 (1 960 o) |
| Vite sert le socle | ✅ `designSystem.css` 200 (29 184 o) · `/` 200 |
| Tokens CSS | ✅ **0 cycle** `--x: var(--x)` · **0 token utilisé non défini** · **0 doublon** entre fichiers |
| Contrastes WCAG AA | ✅ **15/15 paires ≥ 4,5:1** (voir ci-dessous) |
| ESLint | ✅ aucun avertissement sur les fichiers touchés |
| Références SYGEP-CPFAE | ✅ **0 occurrence** dans le diff |

Contrastes mesurés : texte principal 17,85 · secondaire 7,58 · atténué 4,76 ·
blanc/bleu royal 5,33 · blanc/indigo 10,27 · blanc/navy 13,63 · blanc/rouge 4,53 ·
blanc/vert 7,31–4,90 · ambre 5,44 · rouge clair 6,46 · vert clair 4,87 ·
bleu clair 7,94 · ciel/navy 7,95 · turquoise 10,74.

### D.2 Problèmes détectés et corrigés en cours de route

1. **Logo dénaturé** : `filter: brightness(0) invert(1)` sur `.sidebar-logo`
   remplaçait les couleurs officielles par un aplat blanc → filtre retiré, plaque blanche.
2. **Deux jeux de tokens `--injs-*` concurrents** : rayons 12 px contre 14/20 px,
   trois verts différents, deux cyans. Selon l'ordre de chargement, l'interface
   changeait d'aspect → doublons convertis en alias, 0 doublon restant.
3. **Cycles CSS** : `--injs-bg: var(--injs-bg)` et deux autres faisaient retomber
   la propriété sur sa valeur initiale (fond transparent) → supprimés.
4. **Échec AA** : blanc sur `#16A36A` = **3,24:1** → dégradé de succès ramené à
   `#0A6340`→`#0F8152` (7,31 → 4,90).
5. **Boutons pleine largeur sous 480 px** : une règle `.btn { width: 100% }`
   cassait barres d'outils et tableaux → limitée aux pieds de modale et
   aux blocs d'action de formulaire.
6. **En-tête de tableau collant hors conteneur défilant** : flottait au-dessus du
   contenu → porté sur `.table-responsive`.

### D.3 Non exécuté — NOT EXECUTED

- **Captures d'écran aux 7 largeurs (360, 390, 768, 1024, 1366, 1440, 1920 px)** :
  Playwright et les navigateurs headless ne sont pas installables dans cet
  environnement (`npx playwright --version` échoue). Le responsive a été contrôlé
  par **analyse statique** : points de rupture 1024/768/480 px, aucune largeur
  fixe supérieure à 360 px, débordement des tableaux confié à `.table-responsive`,
  zones tactiles ≥ 40 px, champs à 16 px sous 390 px (anti-zoom iOS).
  **Une validation visuelle humaine reste nécessaire.**
- **Tests end-to-end navigateur** : non exécutables (même cause).
- **Audit Lighthouse / axe-core** : non exécutés.

---

## E. Statut

### **VALIDÉ AVEC RÉSERVES**

**Ce qui est prouvé par exécution :** build, 1 912 tests unitaires, 261 tests
backend, rendu réel de l'écran de connexion admin sans préremplissage, service des
ressources statiques, intégrité complète des tokens CSS, 15/15 paires de contraste
conformes AA, absence de référence SYGEP-CPFAE.

**Ce qui reste réservé :**

1. **La vérification visuelle n'a pas été faite dans un navigateur.** Aucun
   environnement de capture n'est disponible ici. Les affirmations portent sur le
   CSS servi et sur des mesures calculées, pas sur un rendu observé.
2. **Les 15 CSS de module conservent leurs règles propres.** Ils héritent des
   primitives du socle (boutons, champs, tableaux, modales), mais une harmonisation
   écran par écran reste à mener pour les compositions spécifiques
   (KPI, `finance-modal`, `par-modal`, `hab-table`).
3. Le socle est volontairement **peu spécifique** (aucun `!important`, sélecteurs
   courts) afin de ne pas écraser l'existant : c'est ce qui le rend sûr, et c'est
   aussi ce qui limite sa portée sur les écrans les plus atypiques.

Aucune régression fonctionnelle n'a été observée sur les suites exécutées.
