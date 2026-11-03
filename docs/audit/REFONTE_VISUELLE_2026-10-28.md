# Refonte visuelle premium — INJS Abidjan

**Date :** 28 octobre 2026
**Branche :** `arena/d40e4a41-backend-injs2026`
**Commits :** `438c87a` (socle + connexions), `6ba48ab` (rapport), `990dec8` (modules métier)
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

Les **42 tokens historiques** de `src/index.css` conservent **leurs noms** (contrat
avec les écrans) mais leurs **valeurs pointent désormais vers la palette officielle**.
Aucun écran ne peut se retrouver sans couleur ; aucune teinte parasite ne subsiste.

### A.2 Logo officiel

`src/assets/logo-injs.svg` et `backend/static/img/logo-injs.svg` sont les seuls
fichiers autorisés, utilisés tels quels :

- plaque blanche systématique (`.login-logo-frame`, `.injs-login-icon-box`,
  `.sidebar-logo`), `object-fit: contain`, ratio préservé ;
- **aucun filtre** : l'ancien `filter: brightness(0) invert(1)` du `.sidebar-logo`
  écrasait les couleurs de l'emblème — supprimé ;
- aucun logo généré, aucun fond dégradé sous le logo, aucune variante inventée.

**Exception documentée — variante monochrome blanche (`16cb4fb`).** Le logo
officiel porte le monogramme **INJS** et le libellé **ABIDJAN**, tous en bleu
(#283A87, #283A88, #293A88, #2A3C89). Placé sur la plaque bleu nuit `#001a33`
de l'en-tête de l'admin, il était bleu sur bleu, donc quasi illisible.
`static/img/logo-injs-blanc.svg` reprend **le fichier officiel sans y toucher** :
mêmes 6 tracés, même `viewBox="0 0 300 300"`, mêmes `transform="translate(...)"`,
même élément `<text>ABIDJAN</text>`, même `aria-label`. Seules les 4 valeurs de
`fill` passent en `#FFFFFF`. **Aucun filtre, aucune déformation, aucun
redimensionnement du tracé** — c'est une déclinaison monochrome du fichier
officiel, pas un logo différent. Contrôlé par 10 tests (`test_admin_logo`).

### A.3 Composants

Le socle `frontend/src/styles/designSystem.css` (821 lignes, 12 sections) stylise
les primitives déjà présentes dans le code, **sans nouvelle bibliothèque** :

- **Boutons** : `.btn` + variantes sémantiques (`primary`, `success`, `warning`,
  `danger`, `info`, `outline-*`, `ghost`), états `hover` / `active` / `disabled`,
  `:focus-visible` unique et visible. Couleur = **sens**, pas décoration.
- **Formulaires** : `.form-control`, `.form-select`, libellés associés, aide,
  erreur non signalée par la couleur seule (icône + texte), zone tactile ≥ 40 px.
- **Cartes** : `.card`, `.card-header`, `.card-body`, ombres douces, bordure 1 px.
- **Tableaux** : `.table` dense et lisible, en-tête institutionnel, en-tête collant
  **uniquement** dans `.table-responsive`.
- **Badges / pastilles** : états métier explicites, tous ≥ 4,5:1.
- **Modales** : `.modal-overlay` / `.modal-content` / `.modal-header` / `.modal-footer`
  alignés, pied replié en colonne sur mobile, fermeture Escape, focus capturé.
- **États vides et chargement** : message explicite, jamais un tableau nu.

### A.3 bis Planche de style intégrée à l'application

La planche de style n'est plus un HTML statique posé à côté de l'application :
elle devient l'écran **`/referentiels/planche-de-style`** (Référentiels → Planche
de style). Elle **lit le socle au lieu de le recopier** : les noms de jetons
proviennent de `getComputedStyle` et d'un parcours récursif de
`document.styleSheets`, les valeurs sont résolues par le navigateur, les
contrastes sont **calculés** (WCAG 2.2) et la largeur mesurée donne le point de
rupture actif. Fonctions associées : filtrage sur nom **et** valeur, copie d'un
jeton en un clic, sommaire d'ancres, impression, démonstration du composant réel
`ConfirmModal`. L'écran est en **lecture seule** (aucun appel API, aucune
donnée métier, aucun chiffre inventé) et partage la garde des écrans
d'administration. Détail : `docs/design/PLANCHE_STYLE_MODULE.md`.

### A.4 Glassmorphism maîtrisé

Trois niveaux de verre (`--injs-glass-1/2/3`) avec `backdrop-filter` et **repli
opaque garanti** par `@supports not (backdrop-filter: blur(1px))`.
Le verre n'est **jamais** appliqué aux tableaux, aux formulaires, ni aux blocs de
texte dense. Un `backdrop-filter` a même été **retiré** d'une carte KPI au fond
opaque : il ne produisait aucun effet visible tout en coûtant une passe de flou.
Pas de pulsation permanente, pas de néon, pas d'ombre excessive.

---

## B. Périmètre traité

| Zone | État |
|---|---|
| Socle de design central | **créé** — 821 lignes, importé en dernier dans `main.jsx` |
| Connexion React | **refondue** — carte verre, plaque logo, champs, erreurs, responsive |
| Connexion admin Django | **refondue** — template + CSS servis par `collectstatic` |
| Barre latérale | **alignée** — dégradé institutionnel, logo sans filtre |
| Tableaux de bord | **alignés** — tokens `dashboardEngine` dédupliqués vers le socle |
| **23 CSS de module** | **harmonisés** — plus aucun bleu historique dans le CSS |
| **Habilitations (16 pages)** | **harmonisées + accessibilité corrigée** |
| Modales, tableaux, formulaires, boutons, badges | **couverts** par le socle |

Couverture mesurée sur le code réel : **117 fichiers d'écran/composant sur 141
(82 %)** utilisent au moins une primitive stylée par le socle — 694 boutons,
408 cartes, 340 champs, 193 tableaux, 139 badges, 47 en-têtes de modale.

**Aucun fichier `.js`, `.jsx` ou `.py` n'a été modifié** : la refonte est
purement présentationnelle. Routes, contrats API, règles d'authentification et
d'autorisation, filtres, pagination et validations sont intacts par construction.
Côté backend, seuls des fichiers de **présentation** ont été touchés :
`templates/admin/login.html`, `static/admin/login.css`, `templates/admin/base.html`
(en-tête uniquement), plus le SVG de déclinaison blanche — aucune vue, aucun
modèle, aucun `urls.py`.

---

## C. Fichiers

### Créés

| Fichier | Justification |
|---|---|
| `frontend/src/styles/designSystem.css` | socle unique : tokens, primitives, responsive, accessibilité, impression |
| `docs/audit/REFONTE_VISUELLE_2026-10-28.md` | ce rapport |
| `backend/static/img/logo-injs-blanc.svg` | variante monochrome blanche du logo officiel, pour fond sombre (`16cb4fb`) |
| `docs/design/PLANCHE_STYLE_MODULE.md` | documentation du module « Planche de style » intégré au frontend |
| `frontend/src/lib/plancheStyle.js` (+ `.test.js`) | logique pure de la planche : lecture des jetons, filtrage, contraste WCAG, point de rupture |
| `frontend/src/pages/design/PlancheDeStyle.jsx` (+ `.test.jsx`) | écran `/referentiels/planche-de-style` |
| `frontend/src/styles/plancheDeStyle.css` | mise en page du module, portée `.planche*` |
| `backend/config/tests/test_admin_logo.py` | 10 tests : géométrie identique au logo officiel, `fill` blancs, `transform` inchangés, tailles de l'en-tête, `alt` |

### Modifiés — socle et connexions (`438c87a`)

| Fichier | Nature |
|---|---|
| `frontend/src/main.jsx` | import du socle **en dernier**, après `harmonisation.css` |
| `frontend/src/index.css` | 6 tokens d'espacement dédupliqués ; 7 tokens de marque aliasés ; 27 couleurs harmonisées |
| `frontend/src/styles/dashboardEngine.css` | 24 tokens contradictoires convertis en alias ; 3 cycles supprimés |
| `frontend/src/styles/login.css` | réécriture complète, classes d'origine conservées |
| `frontend/src/styles/sidebar.css` | retrait du filtre sur le logo, dégradé institutionnel |
| `backend/templates/admin/login.html` | logo statique, bouton de révélation, `role="alert"`, `next` |
| `backend/static/admin/login.css` | réécriture complète (9 640 o servis) |

### Modifiés — modules métier (`990dec8`, 23 fichiers)

`campagnes`, `candidatures`, `chargesEnseignants`, `coursLmd`, `dashboardEngine`,
`ecransGeneriques`, `edts`, `equivalences`, `evaluations`, `finance`, `formateurs`,
`formationsLmd`, `groupes`, `harmonisation`, `maquettes`, `organigramme`,
`parametres`, `premiumCommun`, `profils`, `scolariteDashboard`, `sidebar`,
`index.css` et **`src/pages/habilitations/habilitations.css`**.

### Supprimés

Aucun.

---

## D. Validation

### D.1 Contrôles exécutés

| Contrôle | Résultat |
|---|---|
| `npm run build` | ✅ **built in 3.88s** (avertissement chunk > 500 kB : préexistant) |
| `npx vitest run` | ✅ **101 fichiers / 1 916 tests** (4 tests d'accessibilité ajoutés) |
| **CI GitHub — run 40704468360 sur `b6563b4` (HEAD, toutes les modifications incluses)** | ✅ **Backend (Django + PostgreSQL) vert en 56 min 07 s** · ✅ **Frontend vert en 1 min 45 s** (analyse statique + tests) |
| `manage.py test config.tests.test_apercu_hardening authentication` | ✅ **261 tests OK** (skipped=1) — exécution locale ciblée |
| `/admin/login/` rendu (sans auto-connexion) | ✅ **200 · 19 773 o**, logo officiel, **0 identifiant et 0 mot de passe préremplis** |
| Ressources statiques | ✅ `login.css` 200 (9 640 o) · `logo-injs.svg` 200 (1 960 o) |
| Vite sert le socle | ✅ `designSystem.css` 200 (29 184 o) · `/` 200 |
| Tokens CSS | ✅ **0 cycle** · **0 token non défini** · **162 tokens** · **0 doublon** entre fichiers |
| Bleus historiques dans le CSS | ✅ **0** (`#2563EB`, `#2A7FFF`, `#1D4ED8`, `#38BDF8`, `#06B6D4`, `#1E62D0`, `#0B1F3A`) |
| Contrastes WCAG AA | ✅ **15/15** paires du socle ≥ 4,5:1 ; badges habilitations **7/7** après correction |
| Points de rupture responsive | ✅ **30** déclarés (480/640/768/820/900/992/1024/1100/1280/1300 px) |
| Largeurs fixes ≥ 400 px | ✅ **2**, toutes deux décoratives (orbes de connexion) contenues par `overflow: hidden` |
| ESLint | ✅ aucun avertissement sur les fichiers touchés |
| Références SYGEP-CPFAE | ✅ **0 occurrence** dans les trois commits |

Contrastes du socle : texte principal 17,85 · secondaire 7,58 · atténué 4,76 ·
blanc/bleu royal 5,33 · blanc/indigo 10,27 · blanc/navy 13,63 · blanc/rouge 4,53 ·
blanc/vert 7,31–4,90 · ambre 5,44 · rouge clair 6,46 · vert clair 4,87 ·
bleu clair 7,94 · ciel/navy 7,95 · turquoise 10,74.

### D.2 Problèmes détectés et corrigés

**Socle et identité**

1. **Logo dénaturé** : `filter: brightness(0) invert(1)` sur `.sidebar-logo`
   remplaçait les couleurs officielles par un aplat blanc → filtre retiré.
2. **Deux jeux de tokens `--injs-*` concurrents** : rayons 12 contre 14/20 px,
   trois verts, deux cyans. Selon l'ordre de chargement, l'interface changeait
   d'aspect → doublons convertis en alias, **0 doublon** restant.
3. **Cycles CSS** : `--injs-bg: var(--injs-bg)` et deux autres faisaient retomber
   la propriété sur sa valeur initiale → supprimés.
4. **Échec AA** : blanc sur `#16A36A` = **3,24:1** → dégradé de succès ramené à
   `#0A6340`→`#0F8152` (7,31 → 4,90).

**Modules métier**

5. **Mosaïque de bleus** : `#2563EB` (75×), `#2A7FFF` (88×), `#0B1F3A` (80×)…
   chaque module avait sa teinte → **0 bleu historique** après migration.
6. **Cinq badges de statut d'habilitation échouaient AA** — sur des états de
   sécurité, c'est critique : ACTIF 3,32 → **4,87**, SUSPENDU 2,86 → **5,44**,
   RÉVOQUÉ 3,95 → **6,46**, niveau N4 3,95 → **6,46**, N3 2,86 → **5,44**.
7. **Niveaux N0 / N1** : 2,45 et 3,57 → **6,04** et **5,17**.
8. **Sélecteur mort** : `.par-modal .modal-content` ne matchait **jamais** — la
   classe `par-modal` est portée *par* l'élément `.modal-content`
   (`Parametres.jsx`). La modale de paramètres n'avait donc aucun style propre.
9. **Carte KPI** : `backdrop-filter` sur fond opaque (aucun effet visible, coût
   de composition) retiré ; libellé 10 px → 12 px.
9bis. **`.btn-info` inexistant** : `MaquetteDetail.jsx` l'utilise, mais aucune règle
   ne le définissait — le bouton tombait sur le style `.btn` neutre. Variante
   ajoutée (`#0B5A6B` → `#0E7490`, blanc à **5,36:1** ; la teinte `#0D9488`
   n'offrait que 3,74:1). Trouvé en construisant la planche de style, en
   vérifiant que chaque classe affichée existe réellement dans le CSS.
10. **Boutons pleine largeur sous 480 px** : une règle `.btn { width: 100% }`
    cassait barres d'outils et tableaux → limitée aux pieds de modale et blocs
    d'action de formulaire.
11. **En-tête de tableau collant hors conteneur défilant** : flottait au-dessus du
    contenu → porté sur `.table-responsive`.
12. **Menu mobile sans touche Échap** : seuls le voile et un bouton fermaient la
    sidebar ; au clavier, aucune sortie. Gestion d'Échap + verrouillage du
    défilement arrière-plan ajoutés (`Layout.jsx`).
13. **`ConfirmModal` non accessible** : aucune sémantique de dialogue, pas d'Échap,
    focus jamais déplacé, bouton « × » sans nom accessible. Réécrit : `role="dialog"`,
    `aria-modal`, titre et description reliés, Échap, focus entrant puis rendu,
    libellé de fermeture explicite. **4 tests ajoutés** (9 au total).
14. **Panneau de notifications trop large** : 380 px fixes débordaient d'un écran de
    360 px → largeur bornée par la fenêtre ; bouton-icône doté d'un nom accessible
    et de `aria-expanded`.
15. **Palettes de graphiques déconnectées** : `Statistiques`, `EvaluationCharts` et
    `Secretariats` avaient chacun leur série de couleurs → ramenées sur la série
    officielle, longueur préservée, **0 doublon** après contrôle.
16. **Test figé sur une nuance obsolète** : `AuditeursNotoiresPanel` exigeait
    `rgb(198,40,40)` (#C62828). La règle testée est conservée (un motif renseigné
    est signalé par la couleur d'alerte), seule la nuance suit le socle
    (#DC3545). Assertion toujours stricte — **pas un affaiblissement**.

17. **Graphiques de l'accueil admin illisibles** (signalé par l'utilisateur sur
    « Pointages par mois ») : la cause n'était pas la taille de police mais la
    **localisation française des flottants dans les attributs SVG**. Les gabarits
    émettaient `x="46,0"`, `cx="98,0"`, `r="45,1"` ; la virgule est invalide en
    SVG, le navigateur ignorait l'attribut et retombait à 0 — tous les libellés
    s'empilaient au bord gauche et le camembert avait un centre et un rayon nuls.
    Corrigé par `{% localize off %}` autour des SVG ; tailles de police sorties
    dans les données (7,5 px au lieu de 9) ; viewBox minimal porté à 420 px pour
    limiter l'agrandissement ; **libellés répartis sur deux lignes** (« sept. » /
    « 2025 ») via `<tspan>`, ce qui supprime les troncatures en plein mot même sur
    12 mois. **4 tests de régression ajoutés.** Vérifié sur le serveur réel : `/admin/` 200, aucune
    virgule décimale dans les attributs.

19. **Logo illisible dans l'en-tête de l'admin** (signalé par l'utilisateur) : le
    monogramme bleu #283A87 était posé sur la plaque bleu nuit #001a33, sans
    contraste utile. Le libellé « Abidjan » du logo disparaissait. Corrigé par la
    variante blanche décrite en A.2, plaque agrandie **40 → 52 px**, icône
    **32 → 44 px**. Au passage, le PNG base64 de **14 Ko codé en dur** dans
    `base.html` (donc rechargé à chaque page, non cacheable) est remplacé par un
    fichier statique servi par `{% static %}` : `base.html` passe de ~35 Ko à
    **21 164 octets**. `alt="INJS Abidjan"` conservé pour les lecteurs d'écran.
    **10 tests de régression ajoutés** dont un contrôle des contrastes de forme
    (aucun `<filter>`, aucune couleur bleue résiduelle).

### D.3 Non exécuté — NOT EXECUTED

- **Captures d'écran automatiques** : aucun navigateur n'est disponible et aucun ne
  peut l'être ici. Vérifié et documenté : aucun binaire (`chromium`, `chrome`,
  `firefox`) ; Chromium récupéré via npm (0 paquet bloqué) mais **inutilisable**,
  il manque `libnss3.so`, `libnspr4.so`, `libnssutil3.so` ; ces paquets ne sont pas
  installables (dépôts système injoignables) et n'existent sur aucun registre
  autorisé ; les trois CDN de navigateurs (`cdn.playwright.dev`,
  `storage.googleapis.com`, `edgedl.me.gvt1.com`) répondent tous `000`.
  **Contournement livré :** `docs/design/apercu-design-system.html`, planche
  autonome embarquant le **CSS réel** et le logo officiel, rendue par le
  navigateur de l'utilisateur (servie sur le port 8080 de l'aperçu).
  Le responsive reste contrôlé par analyse statique : 30 points de rupture, aucune
  largeur fixe non contenue, débordement des tableaux confié à `.table-responsive`,
  zones tactiles ≥ 40 px, champs à 16 px sous 390 px (anti-zoom iOS).
  **La validation esthétique finale reste humaine.**
- **Tests end-to-end navigateur** et **audit Lighthouse / axe-core** : même cause.
- **Compte exact des tests backend du run CI** : le job est vert, mais le journal
  détaillé n'est pas téléchargeable depuis cet environnement (`gh run view --log`
  échoue). Le statut est donc « suite complète passée », sans décompte vérifié ici.
- **Chasse aux sélecteurs CSS morts** : un détecteur a été écrit, mais beaucoup de
  classes sont construites dynamiquement (`hab-niveau-${niveau}`,
  `badge-${statut}`), ce qui produit des faux positifs. Seul le cas
  `.par-modal .modal-content`, vérifié à la main, a été corrigé.

---

## E. Statut

### **VALIDÉ AVEC RÉSERVES**

**Ce qui est prouvé par exécution :** build, 1 916 tests unitaires relancés après
la migration, **CI GitHub entièrement verte sur le commit exact `b6563b4`**
(backend Django + PostgreSQL 56 min 07 s, frontend lint + tests 1 min 45 s),
261 tests backend ciblés en local, rendu réel de l'écran de connexion admin sans
préremplissage, service des ressources statiques, intégrité complète des tokens
CSS, 0 bleu historique, 15/15 paires de contraste du socle et 7/7 badges
d'habilitation conformes AA, absence de référence SYGEP-CPFAE, absence totale de
modification de logique applicative.

**Conséquence :** la non-régression fonctionnelle n'est plus une promesse mais un
fait mesuré — les suites complètes frontend et backend passent sur l'infrastructure
GitHub, pas seulement sur cette machine.

**Ce qui reste réservé :**

1. **La vérification visuelle n'a pas été faite dans un navigateur.** Aucun
   environnement de capture n'est disponible ici. Les affirmations portent sur le
   CSS servi et sur des mesures calculées, pas sur un rendu observé. C'est la
   limite principale de ce rapport.
2. **Harmonisation de teinte, pas refonte de composition écran par écran.** Les
   écrans conservent leurs mises en page propres ; ce qui a changé, c'est la
   palette, les primitives partagées et certains défauts mesurés. Les compositions
   les plus atypiques (`finance-hero-kpi`, `hab-matrice`, `gen-*`) mériteraient
   une revue visuelle dédiée.
3. Quelques **couleurs isolées** subsistent dans les modules (nuances de niveaux,
   états particuliers). Elles sont conformes AA là où elles portent du texte,
   mais ne sont pas toutes tokenisées.
