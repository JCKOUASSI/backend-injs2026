# Couverture de la refonte visuelle — par module

**Date :** 28 octobre 2026
**Branche :** `arena/d40e4a41-backend-injs2026`
**Méthode :** mesure automatique sur le code réel (92 pages React, 25 fichiers CSS),
pas une déclaration d'intention. Chaque ligne est calculée à partir des imports
CSS et des classes effectivement utilisées dans les fichiers.

## 1. Couverture mesurée

| Famille de pages | Pages | Usages de primitives du socle | CSS importés | Couleurs littérales restantes |
|---|---|---|---|---|
| `archives` | 3 | 15 | — (socle global) | 46 |
| `habilitations` | 30 | 215 | habilitations.css | 6 |
| `racine` | 43 | 1363 | campagnes.css, coursLmd.css, dashboardEngine.css, ecransGeneriques.css, edts.css, evaluations.css, finance.css, formateurs.css, formationsLmd.css, habilitations.css, login.css, organigramme.css, parametres.css, premiumCommun.css, profils.css | 1225 |
| `scolarite` | 16 | 388 | campagnes.css, candidatures.css, chargesEnseignants.css, equivalences.css, groupes.css, maquettes.css, premiumCommun.css, scolariteDashboard.css | 5 |

**Lecture :** 87 pages sur 92 utilisent au moins une primitive du socle
(`btn`, `card`, `form-control`, `table`, `badge`, `alert`, `modal`), soit
**1 981 usages** au total. Les 5 pages restantes sont des conteneurs de mise en
page (`HabilitationsLayout`, `NavigationUtilisateursAcces`, `DifferentialPanel`,
`SensibleBadge`) ou une page de routage (`Formations`) qui délègue aux composants.

Les « couleurs littérales restantes » sont désormais **aux valeurs de la charte**
(elles ont été harmonisées) ; elles restent en dur dans des objets de style inline,
ce qui n'est pas idéal mais n'introduit plus d'incohérence de teinte.

## 2. Ce qui reste à faire, sans faux-semblant

1. **Migrer les styles inline vers des classes.** 1 400 valeurs subsistent dans
   des objets `style={...}`, majoritairement dans `Statistiques.jsx`,
   `ModuleDetail.jsx` et `FormationDetail.jsx`. Les teintes sont bonnes, la
   maintenance ne l'est pas.
2. **Revue visuelle humaine.** Aucun navigateur n'est disponible dans
   l'environnement d'exécution (voir le rapport principal, section D.3) : la
   conformité esthétique réelle n'est pas prouvée, seulement la cohérence mesurée.
3. **Composants à fort contenu** (`Statistiques`, `ModuleDetail`) : leur densité
   mérite une revue dédiée écran par écran.

## 3. Contrôles effectués par lot

| Lot | Contrôle exécuté | Résultat |
|---|---|---|
| 1 — Socle | `npm run build` | ✅ 3,8 s |
| 1 — Socle | Intégrité des tokens (cycles, non-définis, doublons) | ✅ 0 / 0 / 0 |
| 2 — Connexions | Rendu Django `/admin/login/` sans auto-connexion | ✅ 200, 0 préremplissage |
| 3 — Navigation | Échap + verrouillage du défilement du menu mobile | ✅ ajouté, 25 tests layout verts |
| 4 — Composants | `ConfirmModal` : rôle, Échap, focus, nom accessible | ✅ 9 tests (4 ajoutés) |
| 4 — Composants | Panneau de notifications à 360 px | ✅ largeur bornée, 4 tests verts |
| 5 — Modules | Matrice ci-dessus | ✅ 87/92 pages |
| 6 — Validation | `npx vitest run` | ✅ 101 fichiers / 1 916 tests |
| 6 — Validation | Serveurs réels (`/`, `/login`, `/api/health/`, `/admin/`) | ✅ 200 |
| 6 — Validation | CI GitHub sur le commit précédent | ✅ backend + frontend |
