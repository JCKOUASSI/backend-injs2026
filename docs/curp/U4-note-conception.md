# U4 — Note de conception : écrans web d'administration des comptes (prompt C2)

> Unité I4, dépend d'U3, bloque U5. Statut de cette note : **hypothèses de
> réalisation pour la tranche démo < 24 h**, à contresigner par le RS et
> l'EF. Aucune décision non écrite dans les prompts n'est introduite ; les
> replis et attentes d'unités ultérieures sont explicités.

## 1. Principe directeur et périmètre

Tout l'affichage **dérive des capacités servies par le backend**
(`/api/auth/capacites/`, clé ajoutée ci-dessous) et des endpoints
`/api/habilitations/` ; **aucune liste de rôles n'est codée en dur dans le
React** (risque principal de la fiche C2). L'ancien écran `Utilisateurs`
reste en place et reste seul décideur : U4 ajoute une console **à côté**,
désactivée par défaut.

- **Drapeau de repli** : `flag.curp_ui_admin` (booléen, **OFF par défaut**,
  graine `parametres`), ajouté aux feature flags existants. Éteint → les
  routes renvoient 404 côté API et le menu/les routes ne s'affichent pas ;
  l'administration Django et l'écran Utilisateurs existants reprennent la
  main, exactement comme l'exige la fiche (« repli »).
- **Capacité UI** : nouveau module de capacités `habilitations_admin`
  (action `gerer`), une **callable** qui exige à la fois le drapeau **et**
  le trio d'administration legacy (`EstAdministrateurHabilitations`). Le
  menu et les routes ne se montrent que si cette capacité est vraie ; les
  vues DRF la revérifient (l'API reste l'autorité).
- **Mode moteur** : toujours **OBSERVATION/OFF**. U4 écrit dans les tables
  de *gouvernance* CURP (personnes, comptes, attributions, dérogations,
  délégations, journal) mais ne touche aucune vue legacy ni aucun refus
  appliqué.

## 2. Les onze écrans et leur niveau de service démo

Sous `/administration/comptes` (préfixe commun), neuf écrans sont
**pleinement opérationnels** sur la couverture livrée ; deux écrans dont le
moteur relève d'unités ultérieures sont livrés en **consultation/geste
borné**, sans feindre la fonctionnalité :

| Écran (prompt C2) | Route | Niveau démo |
|---|---|---|
| ListeComptes | `/administration/comptes/` | **Plein** : recherche, filtres (statut, rôle, domaine, canal), colonnes, actions rapides |
| FicheCompte | `/administration/comptes/:id/` | **Plein** : identité, rôles/périmètres, dérogations, délégations, journal du compte |
| AssistantCreation | `.../nouveau/` | **Plein**, 5 étapes + récapitulatif langage clair, recherche préalable de personne |
| ModificationCompte | `.../:id/modifier/` | **Plein** avec **différentiel obligatoire** (vert gagné / rouge perdu), validation bloquante |
| GestionRoles | `.../roles/` | **Plein** : référentiel, description, sensibilité, comptes titulaires |
| MatricePermissions | `.../matrice/` | **Plein** : vue croisée rôle × module/permission filtrable (données U3) |
| Derogations | `.../derogations/` | **Plein (geste borné)** : liste, proposition avec motif/échéance, révocation ; le circuit complet d'instruction est U5 |
| Delegations | `.../delegations/` | **Plein (geste borné)** : création bornée, suivi, fin anticipée ; re-délégation et contrôle « je ne délègue que ce que je détiens » en U5/C3 |
| JournalHabilitations | `.../journal/` | **Plein** : consultation filtrable + statut du chaînage (commande existante exposée en lecture) |
| OperationsMasse | `.../operations-masse/` | **Aperçu seul** : import d'un fichier, prévisualisation intégrale et rapport ligne à ligne ; **l'écriture en une transaction et la réversibilité sont U5** (bouton d'écriture masqué, mention explicite) |
| RevueHabilitations | `.../revue/` | **Consultation** : regroupement des comptes par responsable et anomalies de premier niveau ; la campagne signée (C5/U7) n'est pas livrée, actions désactivées avec mention |

Les périmètres sont gérés dans la fiche/la modification (création de
périmètres SECRETARIAT reliés aux secrétariats connus) ; les écrans
dédiés « gestion des périmètres » du J7 ne font pas l'objet d'une route
propre en démo (ils sont dans la fiche).

## 3. Backend ajouté (2 JH DB) — strictement additif

Nouvelles vues sous `/api/habilitations/`, toutes gardées par
`ExigeDrapeauAdmin` (drapeau **et** admin habilitations), tous les gestes
**journalisés** via `services.journalisation.journaliser` :

- `GET comptes/` (recherche, filtres statut/rôle/domaine/canal, pagination) ;
- `POST comptes/` (assistant : personne existante par matricule ou création,
  création du `User` de connexion + `CompteUtilisateur` + attributions) ;
- `GET comptes/{id}/` (fiche complète, sérialiseurs U2 réutilisés) ;
- `POST comptes/{id}/simuler-modification/` → **différentiel**
  `{gagnes, perdus, conserves, avertissements}` calculé côté serveur ;
- `PATCH comptes/{id}/` (applique rôles/dérogations/canal/statut) —
  exige `differential_accepte: true` quand des droits changent et un **motif**
  pour tout geste sensible ; garde « ne pas descendre sous **2 administrateurs
  actifs** » (409 explicite) ;
- `POST comptes/{id}/statut/` (transitions A5 : activer, suspendre,
  désactiver, verrouiller, déverrouiller ; motif obligatoire) ;
- `GET roles/{code}/` (permissions du rôle + titulaires),
  `GET matrice/` (vue compacte rôle × module × niveau et volume),
  `GET journal/` + `GET journal/integrite/` ;
- `GET/POST derogations/`, `POST derogations/{id}/revoquer/` ;
- `GET/POST delegations/`, `POST delegations/{id}/terminer/` ;
- `POST comptes/import-simuler/` (valide des lignes sans rien écrire).

**Double écriture de transition (décision explicite, à valider EF/J2).** En
l'absence de migration des comptes (U8), un compte CURP sans `User.role`
cohérent ne pourrait pas se connecter utilement : l'assistant demande donc
aussi le **rôle d'accès actuel (un des 12 rôles legacy)** qui est écrit sur
`authentication.User.role`, clairement étiqueté « provisoire, remplacé par
les rôles métier à la bascule U8 ». Les rôles métier (A1) et leurs
attributions sont enregistrés dans la couche CURP ; aucun lien A6
automatique n'est déduit (le choix reste humain et tracé).

## 4. Ergonomie de sûreté (obligatoire C2 §2)

- Bandeau permanent : « Toute action sur les habilitations est tracée ».
- Les rôles sensibles portent une pastille rouge « sensible » partout.
- Tout geste irréversible nomme l'action et ses conséquences et **exige un
  motif** ; le bouton de validation reste désactivé tant que le différentiel
  n'a pas été affiché **et** acquitté (case + défilement pris en compte).
- Message explicite de refus sur 403 (l'API reste seule autorité).
- Alerte bloquante si l'opération ferait passer les administrateurs actifs
  sous deux.

## 5. Tests et qualité

- **≥ 25 tests Vitest** (les premiers du module CURP ; le dépôt a déjà des
  tests Vitest sur d'autres écrans) : assistant (étapes, recherche de
  personne, récapitulatif), différentiel (gagné/perdu, validation
  bloquante), refus 403, alignement sur les capacités, pastilles sensibles,
  garde des 2 administrateurs, aperçu d'import, filtres de liste/journal.
- Logique pure (différentiel, filtres, étapes, libellés) dans des modules
  `utils`/`services` finis, testés sans DOM ; les composants sont minces.
- Backend : tests DRF des nouveaux endpoints (visibilité du drapeau,
  différentiel obligatoire, garde des 2 administrateurs, journalisation,
  simulation d'import sans écriture).
- **Aucun fichier au-delà de 400 lignes React** (les écrans denses sont
  éclatés en composants), **zéro `print()`**, français intégral, ajoutitif.
- Le drapeau étant OFF, la CI (qui ne l'active pas) ne doit constater
  **aucune régression** : contrats d'API inchangés pour les clients existants
  (les routes sont nouvelles), ESLint sans nouveau warning au-delà de la
  référence de 89.

## 6. Ce que U4 ne fait PAS

- Aucun basculement d'autorisation (toujours observation), aucun retrait de
  l'écran Utilisateurs existant, aucun import écrit, aucune campagne de revue
  signée, aucun MFA/session/appareil (C4=U6), aucune migration A6 des comptes
  existants (U8), aucun écran mobile (Flutter hors U4).
