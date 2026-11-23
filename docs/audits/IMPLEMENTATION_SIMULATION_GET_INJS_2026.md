# GET INJS — audit et implémentation du module Simulation (2026-11-23)

## Décision d’architecture

L’audit a confirmé que le dépôt n’avait pas d’écran GET INJS Simulation raccordé au parcours manuel. En revanche, le projet dispose déjà :

- du moteur EDT annuel et de ses paramètres de périmètre dans `edts.moteur.annee.generer_annee` ;
- des campagnes et exécutions persistantes (`CampagneGeneration`, `ExecutionCampagne`) avec suivi, bilan et historique ;
- du préremplissage manuel de Génération et d’une prévisualisation sans persistance.

L’implémentation réutilise ces éléments. Elle n’ajoute ni second solveur, ni modèle, ni migration. Une simulation est une campagne marquée `simulation`, exécutée par le même moteur mais avec `persister=False` imposé côté API **et** au point d’appel du moteur. Seuls la campagne, l’exécution et leur bilan sont enregistrés pour la traçabilité ; l’exécution simulée ne crée ni ne remplace d’EDT. La validation/publication d’une campagne Simulation est refusée.

## Parcours livré

1. Nouvelle page GET INJS `/edt/simulation`, accessible depuis la navigation et le hub.
2. Sélection de référentiels réels : une année académique par exécution (limite du modèle campagne actuel), filières, formations, niveaux, groupes, semestres, semaines et options prises en charge par le moteur.
3. Le serveur contrôle les identifiants, l’année, le caractère actif du groupe, le périmètre INJS, la cohérence des niveaux/formations/semestres et les bornes de semaines/quotas. Aucun ID client inconnu n’est silencieusement accepté.
4. Création d’une campagne Simulation, préparation, exécution asynchrone par les endpoints existants, interrogation du statut et affichage du bilan réel par groupe, couverture, séances, conflits, motifs et anomalies.
5. Le rapport détaille des pistes d’amélioration dérivées des motifs réels par groupe : par exemple une cause C4/C7 de salle bloque le conseil « ajouter des semaines » et dirige d’abord vers la capacité/compatibilité des salles ; une couverture partielle sans cause structurelle suggère de tester des variantes de semaines/options, à périmètre constant. Les propositions sont explicitement des heuristiques à rejouer, pas un optimum annoncé. Les groupes partiellement couverts sont identifiés pour une simulation diagnostique de sous-périmètre, avec avertissement sur le dénominateur.
6. L’utilisateur habilité peut enregistrer une revue/acceptation humaine. Cette acceptation **n’est pas** la validation réglementaire d’un EDT et ne publie rien.
7. Le transfert vers `/edt/generation-annuelle?simulation_id=<id>` relit la campagne côté serveur, n’accepte que les simulations acceptées, restaure le périmètre/options, et exige une nouvelle prévisualisation avant l’activation du lancement. Le paramètre reste récupérable après actualisation.
8. L’historique est conservé et filtrable sur les campagnes Simulation existantes.

## Corrections connexes découvertes en test

- `generer_annee` calculait une estimation avant l’initialisation de `besoins_par_groupe`, ce qui provoquait `NameError` pendant une exécution réelle. Le calcul a été déplacé après le calcul des besoins et adapté au sous-périmètre choisi.
- Le dictionnaire de bilan déclarait deux fois la clé `sources` : la seconde entrée écrasait les métriques agrégées prévues. Les compteurs réels (groupes, séances, conflits, effectifs, heures, persistance et contraintes souples) sont maintenant restitués dans `totaux`; les informations de provenance restent dans `sources`. Cela alimente aussi correctement les bilans de campagne et de Simulation.

## Rapport de vérification

| Contrôle | État | Preuve |
|---|---|---|
| Tests backend ciblés campagnes + moteur annuel | **VERT** | `manage.py test edts.tests.test_campagnes edts.tests.test_generation_annee` — 76 tests réussis. Le scénario Simulation exerce le moteur en synchrone et vérifie l’absence de nouvelles lignes EDT/séances, même si `persister` est altéré dans les paramètres stockés. |
| Tests frontend GET INJS | **VERT** | `vitest run src/pages/getinjs src/menu/arborescence.test.js` — 159 tests, 13 fichiers réussis (dont cases à cocher, sélection/désélection multiple et diagnostics de recommandations). Le transfert/rehydratation avec une route initiale `simulation_id` est couvert. |
| Tests frontend de retouche finale | **VERT** | Tests ciblés Simulation, Génération et arborescence après le changement de cases à cocher — 109 tests réussis. |
| Construction frontend | **VERT** | `npm run build` terminé. |
| ESLint ciblé / syntaxe Python / `git diff --check` | **VERT** | Contrôles ciblés réussis. |
| Django `check` | **VERT** | « System check identified no issues ». |
| Modèles et migrations | **VERT** | `makemigrations --check --dry-run` : « No changes detected » ; aucune migration ajoutée. |
| Génération annuelle institutionnelle complète | **ORANGE — non qualifiée** | Les tests ne prouvent pas la couverture/qualité de toute une année réelle. Le périmètre et les limites de calendrier déjà documentés par l’audit moteur restent en vigueur. Aucun lancement annuel réel n’a été fait. |
| Simulation couvrant plusieurs années dans une seule exécution | **ORANGE — non prise en charge** | Une campagne est rattachée à une seule année. L’écran dit explicitement « une année par calcul » ; lancer des années séparées donne des historiques distincts plutôt que d’inventer une campagne multi-années. |
| Années protégées par le garde-fou QR v2 | **ORANGE — contrainte héritée** | L’endpoint de démarrage existant refuse le chemin hérité sur une année détectée QR v2. Le nouveau module ne contourne pas cette protection et remonte le refus serveur. |
| Données de production, charge à l’échelle réelle, reprise après redémarrage/plusieurs workers, validation métier et publication réelle | **NON TESTÉ** | Aucune base, aucun compte ni aucune donnée de production n’ont été utilisés ; aucune publication ni aucun déploiement n’a été effectué. |

Aucun échec restant n’a été constaté dans les suites ciblées ci-dessus. Les avertissements React Router de migration future et les avertissements JSDOM sur la navigation déclenchée par les tests de téléchargement sont non bloquants et préexistants aux cas Simulation.

## Fichiers principaux

- Backend : `backend/edts/api_getinjs.py`, `backend/edts/urls.py`, `backend/edts/moteur/campagnes.py`, `backend/edts/moteur/annee.py`, tests `backend/edts/tests/test_campagnes.py`.
- Frontend : `frontend/src/pages/getinjs/Simulation.jsx`, `Simulation.test.jsx`, `GenerationAnnuelle.jsx` et son test, `frontend/src/App.jsx`, `frontend/src/menu/arborescence.js`.

Aucune modification de production, aucun reset et aucune publication d’EDT n’ont été réalisés.
