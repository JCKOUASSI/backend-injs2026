# Vérification phase 2 — INJS-LMD (23 novembre 2026)

## Cible, garde-fous et restauration

- Environnement : aperçu local, SQLite `backend/db.sqlite3` (`arena.settings_sandbox`, `USE_SQLITE=1`). Aucune écriture dans une base de production.
- Année académique courante : **2026-2027**, du **1 octobre 2026 au 31 juillet 2027**; les champs de calendrier sont restés inchangés.
- Avant l'orchestration du seed, une copie SQLite cohérente a été créée en `/tmp/injs-demo-preseed-20261123.sqlite3` (14 315 520 octets, 227 tables, `PRAGMA integrity_check = ok`). Une seconde copie avant restauration, `/tmp/injs-demo-prerestore-stages-20261123.sqlite3`, a également passé `integrity_check`.

### Incident constaté et correction compensatoire

L'orchestration `seed_plateforme_demo` a été lancée deux fois avec un seed Stages préexistant qui supprimait puis recréait ses conventions `[Exemple]`. C'était incompatible avec la consigne de ne pas supprimer de données. L'instantané pré-seed contenait 160 conventions et 56 évaluations de stage; la correspondance étudiant/année entre l'instantané et la base courante a été vérifiée.

Pour compenser sans restaurer toute la base ni supprimer de lignes, les champs métier de ces 160 conventions et 56 évaluations ont été réconciliés depuis l'instantané vérifié par mises à jour, en conservant les identifiants techniques courants. Contrôles après restauration : `integrity_check = ok`, aucune erreur de clé étrangère, aucun enregistrement supprimé durant cette restauration. Les identifiants techniques des conventions avaient changé lors du remplacement antérieur; ils ont été conservés tels quels pour ne pas perturber les références courantes.

Le seed Stages a été corrigé : il ne supprime ni ne remplace les conventions existantes; il ne crée que les conventions manquantes et ignore celles qui ne portent pas la marque DEMO. Les tests vérifient la stabilité des identifiants et la préservation d'une convention métier. **La commande `--purger` existante n'a pas été exécutée sur la base de démonstration.**

## Population démonstration observée

Les enregistrements de personnes de démo sont fictifs; l'import GET INJS est une recette fictive distincte. Ces volumes décrivent la base d'aperçu observée après le seed et sa vérification, et non un référentiel officiel de statistiques institutionnelles.

| Domaine | Résultat vérifié |
|---|---|
| Population académique | 3 500 personnes fictives DEMO, parité 1 750 / 1 750; 3 500 inscriptions administratives validées de la cohorte DEMO. |
| Inscriptions de l'ensemble de la base | 3 516 inscriptions validées (dont les dossiers d'exemple admissions en plus de la cohorte principale). |
| Import GET INJS | 70 inscriptions fictives importées; synthèse API : base 3 516, import distinct 70, population combinée dédoublonnée 3 586. |
| Offre LMD | 16 formations, 40 maquettes actives, 531 UE et 779 ECUE observées pour l'année cible; 8 niveaux, 16 parcours et 16 semestres. |
| Groupes | 135 groupes pédagogiques et 3 468 affectations de groupe observés dans la base. |
| Couverture pédagogique | 17 enseignants DEMO et 779 ECUE affectées. |
| Emplois du temps / Présences | 16 EDT publiés (17 EDT en tout), 180 placements actifs, 176 séances au registre prêtes à être consommées, 12 salles géolocalisées. |
| Admissions | 36 candidatures; les statuts du cycle de candidature sont représentés. |
| Équivalences | 80 demandes d'exemple. |
| Stages | 20 organismes, 160 conventions, 56 évaluations de stage. |
| Administration / RH | 5 directions, 10 départements, 14 services; 24 agents DEMO, 22 affectations. |
| Jurys / diplomation | 16 sessions de jury, 48 membres, 84 décisions; 60 diplômes d'exemple non validés et 4 gabarits. |
| Évaluations académiques | 8 sessions, 32 évaluations, 800 participants. Aucune note officielle validée/verrouillée n'a été créée par le seed. |
| Finances étudiantes | 80 lignes de barème inactives, 60 échéanciers, 30 factures brouillon, 40 paiements non confirmés, 4 remboursements initialisés, 12 relances. Aucun paiement réel confirmé ni quittance officielle n'est créé par ce jeu de démo. |

## Vérifications exécutées

- `seed_plateforme_demo --base ...` en lecture seule avant application, puis exécution avec confirmation explicite `DEMO_FICTIVE`; contrôles chiffrés terminaux OK. L'orchestrateur a aussi été relancé une fois pour vérifier l'idempotence de ses composants.
- `verifier_coherence_referentiels --strict` : **aucun constat**; provenance renseignée pour les catégories contrôlées, 8 filières alignées sur le code et 16 formations rattachées.
- Endpoints GET authentifiés retournés HTTP 200 : Hub Référentiels, statistiques, candidatures, EDT, interop séances publiées GET INJS, synthèse d'import GET INJS, taux de présence, statistiques de finances, évaluations académiques et statistiques de stages.
- Tests backend ciblés : Admissions / évaluations / finances **9 OK**; GET INJS / interop Présences / refonte Référentiels **68 OK**; QR EDT **31 OK**; statistiques **74 OK**; seed Stages **3 OK**. Soit **185 tests backend réussis** dans les suites ciblées (une suite a été relancée après le correctif du seed Stages).
- Tests frontend : **2 299 tests Vitest réussis sur 148 fichiers**, dont le smoke test du composant racine `App`. Build frontend Vite réussi; `git diff --check` est propre.
- Contrôle final du seed Stages sur la base : **0 nouvelle convention, 160 conservées, 0 convention métier ignorée**, confirmant qu'il ne réécrit plus les lignes présentes.

## Limites connues et éléments à ne pas présenter comme achevés

- Les 176 séances publiées constituent une source consommable par Présences; aucun pointage QR fictif n'a été forgé. Les tests de contrat QR passent, mais un parcours réel de scan sur mobile n'a pas été simulé. Flutter n'est pas disponible dans cet environnement.
- Les évaluations académiques sont des scénarios de démo sans notes officielles validées. Les objets financiers restent explicitement inactifs, brouillons ou non confirmés.
- Les données reconstruites à partir de sources modélisées ou de cadrages ne sont pas réputées officielles sans validation du service INJS concerné. En particulier, les réserves historiques des référentiels LMD (maquettes verrouillées, MS-S8 à confirmer) restent applicables.
- Après la capture d'écran et la pile confirmant l'échec dans `CapabilitiesSync → useCapabilities/useQuery`, le cache optimisé Vite a été recréé, `resolve.dedupe` configuré pour partager une instance React/ReactDOM entre les providers et React Query (dev/test), et l'hôte `*.arena.site` autorisé. Comme l'aperçu utilisait encore les imports pré-optimisés du mode dev, le port 3000 sert maintenant le bundle de production (`vite preview`) : le HTML référence `/assets/...` et non `/node_modules/.vite/deps/...`. `arena/lancer-front.sh` démarre désormais ce mode de production par défaut (avec `--dev` en option pour le HMR); le proxy vers l'API a également été vérifié HTTP 200 avec l'hôte de la capture. Un smoke test du shell `App` a été ajouté. ESLint, build et les 2 299 tests Vitest passent. Le navigateur headless local n'a pas pu être lancé (`libnspr4.so` absent), donc le rendu visuel n'a pas été directement rejoué.
- Ce rapport couvre les scénarios exécutés et les modules réellement alimentés ci-dessus; il ne certifie pas un audit fonctionnel exhaustif de chaque écran ou parcours de toute la plateforme.
