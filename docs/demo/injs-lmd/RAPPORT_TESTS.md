# Rapport de validation

- `python manage.py test edts.tests presences --verbosity 1` sur PostgreSQL : **788 tests réussis, zéro échec, zéro ignoré** (163,876 s). La base de test isolée `test_injs_lmd_audit_20261120` a été créée puis supprimée par Django; la base applicative n’a reçu aucune migration ni écriture de test. Les 9 scénarios de concurrence précédemment ignorés sur SQLite ont donc été exécutés.
- Suite frontend complète : **615 fichiers de test, 2 256 tests réussis, zéro échec**. La première passe a révélé une fonction de sélection totale non déclarée dans Maquettes; elle a été corrigée, puis la suite entière a été relancée avec succès.
- `python manage.py check` : aucun problème.
- `python manage.py makemigrations --check --dry-run` : aucune migration manquante.
- `npm run build` : réussi. Le chunk d’entrée est de 311 Ko (environ 71 Ko gzip); les fournisseurs React, Router et TanStack sont séparés. Le bundle corrigé a été redéployé.
- Après redémarrage, frontend et backend ont répondu HTTP 200.

Les six tests ciblés de récupération d’exécutions orphelines passent également sur PostgreSQL.
