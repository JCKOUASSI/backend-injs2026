# GET-INJS — qualification PostgreSQL locale isolée (suite de la phase 6)

**Statut : essais synthétiques PostgreSQL achevés ; validation demandée. Aucun déploiement, migration ou accès de production.** Ce document complète, sans réécrire rétroactivement, le rapport de phase 6 SQLite déjà validé. Date de référence de la mission : 15 novembre 2026.

## Environnement et sécurité

- Extraction isolée du commit déployé `70d08dad1821caceb61b22fe22cf70e13155bf18`, enrichie **sélectivement** des fichiers phases 2–6 nécessaires. Le working tree local comporte d'autres changements non déployés : `scolarite.0021` **n'a été ni utilisée ni appliquée**. Schéma de test : `edts.0013`, `scolarite.0020`.
- PostgreSQL **17.11** fourni par un paquet binaire de test local (`@embedded-postgres/linux-x64`, version du paquet `17.11.0-beta.19`), UTF-8, `fsync=on`, `synchronous_commit=on`. Serveur limité à un **socket Unix local**, sans écoute TCP ; bases fictives jetables distinctes. Aucun identifiant réel ou accès réseau de production. Le serveur d'essai a été **arrêté après les tests**.
- Les scripts n'autorisent PostgreSQL que si des gardes cumulatifs sont satisfaits : `DEBUG`, marqueur d'isolation explicite, base de test au nom réservé et socket local ; **le script de mesure annuelle exige en plus une base BENCH sans année, affectation ni inscription préexistante**. Le drapeau d'écriture v2 n'est activé qu'**à l'intérieur** du processus de mesure. Le calendrier artificiel 2098–2099 et les inscrits, ressources et besoins fictifs ne sont pas des données institutionnelles.
- **Correction de portabilité du banc** : `AnneeAcademique.libelle` est limité à 20 caractères. SQLite avait accepté une étiquette trop longue ; PostgreSQL l'a refusée. L'étiquette technique a été raccourcie sans changer la graine, les 48 occurrences/groupe, les types et ressources du scénario. L'initialisation PostgreSQL a ensuite été faite en UTF-8 : un premier cluster SQL_ASCII refusait les chaînes Unicode des tests ; c'était un défaut du banc, pas une raison de modifier les données métier.

## Mesures annuelles PostgreSQL — une exécution par taille

| Étudiants fictifs | Groupes | Occurrences | Simulation (s) | Import du jeu (s) | Calcul + commit (s) | SQL commit | RSS max processus (KiB) | Affectations / QR |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 5 000 | 84 | 4 032 | 37,644 | 1,050 | **182,139** | 130 904 | 84 080 | 4 032 / 4 032 |
| 10 000 | 167 | 8 016 | 142,949 | 2,081 | **450,383** | 260 199 | 87 224 | 8 016 / 8 016 |
| 15 000 | 250 | 12 000 | 311,594 | 3,233 | **823,683** | 389 255 | 91 940 | 12 000 / 12 000 |

L'import mesure les insertions en lots des étudiants fictifs **après** la préparation des groupes ; la création des ressources, la migration et la génération des CSV ne sont pas incluses dans le chrono annuel. Les simulations ne persistent aucune occurrence ni QR. Les trois commits complets ont placé toutes les occurrences **de ce seul scénario** ; elles restent toutes des **brouillons QR à revoir, non publiables**.

Vérification séparée *avant* la fenêtre manuelle : 5 000/10 000/15 000 inscriptions synthétiques, 48 occurrences par groupe ; respectivement 4 032/8 016/12 000 affectations, registres et instantanés, clés QR cohérentes, **zéro participant QR inventé et zéro pointage**. Le contrôle a construit l'index d'occupation daté et compté ses ressources ; il **ne prouve pas à lui seul** l'absence de tous conflits entre séances. La mémoire indiquée est le RSS maximum **du processus client seulement** : le serveur PostgreSQL est un processus séparé ; elle ne mesure donc **pas** le RSS total du système ou d'un déploiement.

Sur chaque base annuelle déjà remplie, 30 groupes ont reçu quatre nouvelles lignes fictives dans une semaine tardive peu chargée (120/120 placements). Le p95 de cette opération de service par groupe/semaine vaut **0,187 / 0,210 / 0,224 seconde** respectivement à 5k/10k/15k. Aucun trajet navigateur, authentification HTTP ou worker distant n'est compris dans cette mesure.

Après `ANALYZE` sur 4 032 et 12 000 affectations, `EXPLAIN (ANALYZE, BUFFERS)` de trois requêtes représentatives `(date, groupe)`, `(date, formateur)`, `(date, salle)` a utilisé les index partiels `edt_v2_groupe_date_idx`, `edt_v2_prof_date_idx`, `edt_v2_salle_date_idx`. Sur 15k, temps d'exécution SQL échantillonnés **0,026 / 0,019 / 0,021 ms**. Ces trois plans ne constituent pas le profilage de **toutes** les ~389k requêtes de l'année. Détails et résultats bruts agrégés : `livrables/GET-INJS-POSTGRESQL-ISOLE-RESULTATS.json`.

## Concurrence réelle et non-régression

Un premier essai PostgreSQL a révélé un défaut caché par SQLite : `SELECT FOR UPDATE` joint à une affectation **nullable** produisait `FOR UPDATE cannot be applied to the nullable side of an outer join` lors d'un rattrapage QR. Le service verrouille désormais l'année puis le registre dans le même ordre que les autres écritures, sans jointure nullable sous `FOR UPDATE`. Les tests QR de rattrapage passent sur PostgreSQL. La fixture de test a également été rendue indépendante des valeurs de séquence PostgreSQL : le candidat de rattrapage est toujours choisi à une autre date que l'origine.

Quatre scénarios `TransactionTestCase` réellement exécutés sous PostgreSQL :

1. Deux auteurs avec la même clé → **une affectation, un UUID, un instantané** ; le second rejoue sans dupliquer.
2. Deux groupes demandant le même jour/salle/formateur → **une seule séance acceptée**.
3. Huit auteurs concurrents sur une ressource commune → **une seule séance acceptée**, sans collision persistée.
4. Deux workers sur la même exécution → le **lease actif refuse le second** ; un seul checkpoint, une seule séance et un seul registre.

Suite ciblée fondations, moteur, Présences QR, API v2 et ancienne génération : **181 tests réussis sur PostgreSQL, aucun ignoré** après corrections. Suite indépendante des routes historiques/LMD/annuelles : **109 tests réussis**. `manage.py check`, `makemigrations edts --check --dry-run` et `git diff --check` : OK, **aucune nouvelle migration**. Les premiers essais ayant détecté les problèmes de banc et le rattrapage n'étaient **pas** verts ; seuls les derniers résultats réussis sont retenus comme preuves.

## Fichiers et reproduction

- `backend/edts/moteur/application_v2.py` : correction ciblée de l'ordre et de la portée des verrous du rattrapage QR.
- `backend/edts/tests/test_phase6_postgres_concurrency.py` : quatre scénarios PostgreSQL concurrents.
- `backend/edts/tests/test_qr_v2_phase4.py` : fixture de rattrapage non dépendante des séquences.
- `scripts/mesurer_charge_getinjs_v2.py`, `scripts/mesurer_semaine_apres_charge_v2.py`, `scripts/verifier_charge_getinjs_v2.py` : gardes explicites et mesures sur base PostgreSQL **locale jetable**. Le script initial SQLite garde son mode historique et son refus de toute autre base.
- Ce rapport et `livrables/GET-INJS-POSTGRESQL-ISOLE-RESULTATS.json`. Les données synthétiques volumineuses et les bases restent hors dépôt.

Lancement représentatif, exclusivement sur une base locale vide **dont le nom et le socket répondent aux gardes des scripts**, schéma préalablement migré depuis la copie isolée :

```sh
# Depuis la copie isolée ; $REPO désigne uniquement les scripts de cette branche.
GETINJS_PHASE6_ISOLATED=1 GETINJS_PG_ISOLATED=1 DJANGO_DEBUG=1 \
  DJANGO_SETTINGS_MODULE=config.settings PYTHONPATH="$BACKEND_ISOLE" \
  POSTGRES_DB=getinjs_bench_5000 POSTGRES_HOST="$SOCKET_ISOLE" \
  POSTGRES_PORT="$PORT_ISOLE" POSTGRES_USER="$UTILISATEUR_LOCAL_DE_TEST" \
  python "$REPO/scripts/mesurer_charge_getinjs_v2.py" \
  --csv-dir /tmp/getinjs-phase6-csv-5000 --etudiants 5000 \
  --mode commit --budget-secondes 600
```

## Décision et limites

**Sur cette base PostgreSQL locale seulement**, la cible de 10 minutes à 5 000 étudiants fictifs est respectée (182,139 s). La cible de service groupe/semaine est respectée sur une semaine tardive peu occupée. **La cible RSS < 1 Gio du système complet n'est pas vérifiée** : seul le processus client a été mesuré. Les résultats 10k/15k sont des observations, pas une garantie de délai sur données réelles.

La concurrence testée couvre quelques transactions contrôlées, **pas** des campagnes concurrentes à 15 000 étudiants, des écritures SQL tierces, des routes historiques non basculées, un worker durable supervisé, une panne pendant checkpoint ou la charge réseau de production. La version/configuration du PostgreSQL déployé peut différer. Les sources de volumes CM/TD/TP et du calendrier 2026–2027 ne sont pas approuvées ; les identités `Participant` et la géolocalisation QR ne sont pas rapprochées. **La publication v2 et toute activation de production restent bloquées.**

**Point à valider : acceptez-vous cette qualification PostgreSQL exclusivement locale comme franchissement du blocage “tests PostgreSQL isolés”, tout en maintenant l'attestation métier, le rapprochement QR, l'audit des autres chemins d'écriture et la qualification sur une configuration cible parmi les préalables à une activation séparée ?**
