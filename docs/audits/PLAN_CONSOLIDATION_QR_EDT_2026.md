# Plan de consolidation GET INJS/EDT et Présences QR

**État au 23 novembre 2026 — branche locale seulement.** Aucun accès ni changement de production. Les audits sources restent `AUDIT_GET_INJS_2026.md`, `AUDIT_PRESENCES_QR_2026.md` et `FINALISATION_QR_EDT_CI_2026.md` ; ce plan ne remplace pas leurs constats ni leurs preuves historiques.

## Priorités et critères de sortie

| Priorité | Chantier | Critère de sortie | État actuel |
|---|---|---|---|
| P0 métier | EDT annuel : répartition d'occurrences par semaines/semestres, heures et couverture calculées sur lignes persistées, conflits sur périodes réelles | Calendrier institutionnel S1/S2 approuvé ; tests multi-formations/enseignants/salles ; volumes persistés conformes ; publication contrôlée | **Ouvert, ROUGE**. La garde refuse les scénarios non conformes ; les tests synthétiques mono-semestre ne certifient pas l'annuel. |
| P1 opérationnel | Fermeture automatique des occurrences EDT/LMD (absences, sorties ouvertes, révocation QR), reprise sans doublons | Commande planifiée, dry-run, clôture des occurrences publiées échues, reprise sans répéter les écritures métier | **Corrigé localement et testé SQLite** par cette itération ; disponibilité de l'ordonnanceur en production non attestée. |
| P1 intégrité QR | Courses concurrentes de scan, révocation et clôture, unicité ou stratégie transactionnelle | Tests simultanés sur PostgreSQL isolé, audit des doublons historiques avant toute contrainte DB | **Ouvert / non qualifié sur PostgreSQL** dans cette itération. |
| P1 sécurité présence | Politique de géofence si site/salle non localisé, durée et révocation côté serveur et appareils | Décision institutionnelle documentée, scénarios de salle ambiguë/non localisée et appareils réels | **Ouvert** ; GPS seul ne prouve pas la présence physique. |
| P1 interop | Parcours inscrit/groupe → séance publiée → QR/pointage → ECUE/statistiques | Test d'intégration représentatif avec cohortes issues des différents parcours et vérification des données académiques | FK ECUE et tests ciblés existent dans l'état antérieur ; **parcours bout en bout institutionnel non rejoué ici**. |
| P1 exploitation | Reprise multi-worker durable des campagnes EDT et supervision des tâches | File/lease durable, métriques et exécution CI PostgreSQL complète vérifiée | **Ouvert** ; threads locaux, CI GitHub historiquement bloquée par 403. |

## Correctif appliqué cette itération — clôture automatique LMD

L'automatisation Compose exécutait `process_mobile_heartbeats`, `auto_close_pointages` et `auto_sessions`, mais `auto_close_pointages` exclut explicitement les pointages LMD (`session__isnull=False`). Le service de clôture LMD existait, sans commande planifiée dans le cycle Compose. Les absences des occurrences EDT pouvaient donc ne pas être matérialisées par l'automatisation existante.

Changements :

- Ajout de `presences/management/commands/auto_close_seances_edt.py` : la date locale courante par défaut, occurrence du jour dans la plage de semaines, affectation active, EDT au statut `VALIDE` ou `PUBLIE` et fenêtre de scan échue. `--dry-run` n'écrit rien ; `--date AAAA-MM-JJ` permet une reprise contrôlée d'une date passée et refuse les dates invalides ou futures.
- Ajout de cette commande à la boucle du service cron Compose, après la clôture legacy.
- `auto_clore` verrouille la ligne d'affectation dans sa transaction. Les reprises concurrentes de la même clôture se sérialisent sur PostgreSQL. Une reprise sans nouvel effet n'ajoute pas un second événement de fermeture ; nouveaux pointages, absences ou QR révoqués restent traités et journalisés.
- Aucun changement de schéma, migration, backfill ou modification de données existantes.

**Contrat d'exploitation :** le cron appelle cette commande toutes les cinq minutes dans la configuration Compose. Elle agit uniquement sur les occurrences LMD acceptées par `est_seance_du_jour`; les séances v2 que ce service refuse actuellement ne sont pas rendues badgeables par ce patch. Le statut de la commande dans un déploiement réel, sa supervision et sa reprise après incident doivent être confirmés par l'équipe d'exploitation avant de revendiquer l'automatisation en production.

## Preuves et limites de cette itération

- Tests ciblés de la nouvelle commande et clôture : **6/6 OK** (base Django de test SQLite).
- Suite `presences` avant l'ajout du cas de course PostgreSQL : **237 tests recensés, 233 exécutés OK, 4 ignorés**. Après l'ajout du test de concurrence et l'ajustement de l'ordre des verrous, la passe ciblée commande + course : **3/3 OK, 1 ignoré sur SQLite**. Cela ne prouve pas les courses PostgreSQL.
- `manage.py check` : aucun problème.
- `makemigrations --check --dry-run --noinput` : aucune migration à créer.
- `git diff --check` : OK ; le YAML Compose se parse et la commande est enregistrée par Django.
- Un test PostgreSQL de deux clôtures simultanées a été ajouté au banc `test_concurrence_postgresql.py`, mais **n'a pas été exécuté** dans cette itération ; SQLite ignore les verrous `select_for_update`.
- Validation sémantique Docker Compose **non exécutée** : binaire Docker absent du sandbox.
- Aucune CI GitHub déclenchée, aucun essai de PostgreSQL dans cette itération, aucun test appareil/mobile réel, aucune modification de production.

**Verdict de la mission : ORANGE pour ce correctif de clôture locale ; statut institutionnel global inchangé et non GREEN.** Les risques P0 EDT annuel, concurrence PostgreSQL, géofence et parcours académique bout en bout restent des conditions bloquantes avant qualification ou déploiement.
