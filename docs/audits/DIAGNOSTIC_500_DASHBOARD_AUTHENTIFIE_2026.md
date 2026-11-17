# Diagnostic ciblé — GET authentifié `/api/dashboard/overview/` HTTP 500

**Contexte transmis par l'utilisateur :** la requête qui échoue est `GET /api/dashboard/overview/`, statut HTTP **500**. Le corps de la réponse et la trace serveur ne sont pas accessibles à l'utilisateur dans cette session. L'API publique `/api/health/` répond 200 ; l'endpoint dashboard répond normalement 401 sans authentification. Aucune consultation authentifiée de production ni intervention sur le VPS n'a été effectuée. Branche `arena/a8060ecf-backend-injs2026`, commit analysé `024514f`.

## Reproduction locale isolée

- Sur une base **de test** SQLite migrée intégralement, requête authentifiée avec utilisateur de test `ADMIN` : **HTTP 200** ; JSON avec `annee_academique: null`, `indicateurs`, `kpis`, `pipeline`, `charts`, `alerts`, `quick_actions` (base vide : effectifs 0 ou non disponibles, jamais les chiffres de production). Deux tests isolés de l'endpoint et des annulations hors semaine : **2/2 OK**. Journal temporaire `/tmp/injs-auth-dashboard-local-response.log`.
- Hypothèse **testée, non confirmée en production** : dans une autre base temporaire intégralement migrée, la requête renvoie **200**. En laissant uniquement le schéma EDT à `edts.0011` alors que le code courant attend `edts.0012` (FK nullable `AffectationCreneau.ecue`), le même GET authentifié renvoie **HTTP 500** et Django journalise `OperationalError: no such column: edts_affectationcreneau.ecue_id`. Une fois `edts.0012` réappliquée **sur cette base de test uniquement**, le GET revient à **HTTP 200**. Aucune migration existante n'a été modifiée. Journal temporaire `/tmp/injs-dashboard-schema-repro-hostfixed.log` ; la première tentative, avec `testserver` absent de `ALLOWED_HOSTS`, renvoyait 400 et n'est pas une reproduction valable (`/tmp/injs-dashboard-schema-repro.log`).
- Un état de schéma ancien est donc **une cause techniquement possible et reproduite** du 500, **pas la cause racine prouvée sur le serveur**. D'autres défauts SQL ou exceptions métier produiraient aussi 500. La capture initiale, le statut HTTP et `/api/health/` ne permettent pas de les départager. Il serait incorrect de corriger le code ou de migrer la production sur cette seule hypothèse.

## Complément — seul l'onglet « Vue d’ensemble » échoue

L'utilisateur précise que les autres onglets, **y compris Présences & Assiduité**, répondent. Comparaison du code : `get_direction_overview()` et `get_presences_dashboard()` appellent tous deux `_supervision_du_jour(today)`, qui lit les affectations EDT. Vérification expérimentale sur base SQLite temporaire, utilisateur `ADMIN` authentifié, sans accès à la production :

| Schéma de test | GET overview | GET presences |
| --- | ---: | ---: |
| Migrations complètes | 200 | 200 |
| `edts.0012` retirée volontairement | 500 | 500 |

Le journal local `/tmp/injs-dashboard-schema-both-tabs.log` confirme dans ce deuxième cas `OperationalError: no such column: edts_affectationcreneau.ecue_id`. **La seule absence de `edts.0012` est donc incompatible avec « overview 500, présences 200 » pour le même code, la même base et des appels comparables.** L'hypothèse précédente doit être rétrogradée ; elle ne constitue pas une explication du symptôme observé. Aucune migration n'a été appliquée à la production.

La comparaison des autres services révèle des opérations propres à overview : agrégation des notes d'évaluation (`F('bareme') / 2`), journal de scolarité récent et conversion de son horodatage, volumes des affectations pédagogiques par cycle, répartition des dossiers par sexe, calcul financier et comptages transversaux. Leur exécution sur la base de test migrée ne déclenche pas le 500, mais sa population ne reproduit pas les données réelles. Sans exception serveur relative à la requête en échec, il est impossible de départager un défaut de schéma propre à ces lectures, une valeur de donnée exceptionnelle, une erreur SQL ou une autre cause. Modifier arbitrairement l'une de ces opérations ne serait pas un correctif vérifié. **Aucun correctif du 500 n'est livré ni déployé.**

## Journaux et contrôles

Le journal local ne contient pas d'exception métier avec le schéma courant ; la seule exception SQL produite est volontaire, sur la base temporaire incomplète. `manage.py check` : 0 problème ; `makemigrations --check --dry-run` : aucune dérive des fichiers de migrations. Tests fonctionnels locaux du préflight de déploiement : **173 passés / 0 échec**, mais ils ne vérifient pas le serveur réel. `gh run list --branch arena/a8060ecf-backend-injs2026` : `[]` ; le déclenchement GitHub Actions depuis l'intégration Arena échoue toujours HTTP 403 `Resource not accessible by integration`. La CI n'est **pas** validée. Déploiement **non effectué**.

## Informations indispensables avant correction ou déploiement

Un opérateur autorisé doit consulter **en lecture seule** l'erreur Django correspondant au GET overview en échec (heure UTC, type d'exception et dernière ligne utile, sans données personnelles ni secrets). C'est cette trace, et non la seule réponse 500, qui permet de cibler un test de reproduction puis un correctif limité à la cause confirmée. Si elle incrimine le schéma, vérifier en lecture seule les migrations de la base visée et confronter l'explication au fonctionnement de Présences ; toute modification de production exige sauvegarde vérifiée, contrôle de compatibilité/rollback et **autorisation spécifique**. Sinon corriger uniquement l'exception effectivement observée et ajouter son test de régression. Ne jamais confondre preuve de reproduction locale et cause confirmée sur la production.

**Verdict actualisé :** la requête et son 500 sont identifiés ; la reproduction par migration EDT absente produit également un 500 sur Présences et ne correspond donc pas au symptôme « seul overview échoue ». La cause exacte en production demeure **NON DÉTERMINÉE** sans la trace expurgée de cette requête. Aucun changement de code métier, de permissions, de données de production ou de schéma de production n'a été effectué.
