# GET-INJS — phase 6 : charge synthétique annuelle et validation locale

**Statut : essais locaux achevés sur SQLite isolée ; résultats limités, validation métier demandée. Aucune activation ni donnée de production. Aucun commit/push de cette phase.** Date de référence de la mission : 15 novembre 2026.

## Cadre strict du banc

Extraction isolée du commit déployé `70d08dad1821caceb61b22fe22cf70e13155bf18`, complétée **sélectivement** par les fichiers nécessaires des phases 2 à 6. Schéma de test : `edts.0013`, `scolarite.0020` ; la migration locale `scolarite.0021` n'est ni copiée ni appliquée. Aucune connexion à une base réelle, serveur/VPS ou PostgreSQL de production. Le garde du banc exige `DEBUG`, le marqueur `GETINJS_PHASE6_ISOLATED=1`, SQLite et un fichier de base temporaire hors dépôt ; le flag d'écriture v2 est activé uniquement **dans ce processus isolé**. Les CSV 5 000, 10 000 et 15 000 étudiants sont entièrement fictifs et non importables en production.

Scénario de test : année artificielle 2098–2099, graine 42, groupes de capacité 60 (dernier groupe partiel aux tailles 5k/10k, même si la charge de planification utilise 60), 4 besoins fictifs de 12 séances de 120 minutes par groupe, type CM/TD/TP déduit du gabarit, 40 formateurs partagés, 20 salles, créneaux sur six jours, une indisponibilité, vacances ciblées et jour fermé **fictifs**. Les valeurs `source_confirmee`/`OFFICIEL` ne sont que des entrées techniques de simulation : **aucun volume ni calendrier institutionnel n'est confirmé ici**. Les étiquettes ECUE des CSV n'ont pas de FK à une maquette réelle ; des ordinaux techniques distincts empêchent de confondre ces unités.

Deux parcours distincts : *simulation annuelle* (décisions incrémentales, aucune affectation/QR en base) et *commit annuel* (proposition, revalidation SQL/transaction, création d'une affectation datée, registre QR, instantané d'effectif sans participant inventé). Le chronomètre d'import mesure l'insertion en lots des inscrits fictifs **après** création des groupes, et le chronomètre de calcul/commit commence après création des ressources et périodes. Les temps de migration, de fabrication des CSV et de préparation des référentiels ne sont donc **pas inclus**. Mémoire = `ru_maxrss` Linux du processus, non mémoire globale du serveur. SQL = compteur de requêtes du seul calcul/commit, sans la préparation de base.

## Résultats finaux (une exécution par taille, SQLite)

| Étudiants synthétiques | Groupes | Occurrences | Import (s) | Simulation annuelle (s) | SQL simulation | Commit annuel (s) | SQL commit | Placements et QR | RSS max commit (KiB) |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 5 000 | 84 | 4 032 | 0,713 | 38,484 | 673 | **139,220** | 134 961 | 4 032 / 4 032 | 90 832 |
| 10 000 | 167 | 8 016 | 1,365 | 140,312 | 1 337 | **377,537** | 268 264 | 8 016 / 8 016 | 94 280 |
| 15 000 | 250 | 12 000 | 2,212 | 310,190 | 2 001 | **722,496** | 401 320 | 12 000 / 12 000 | 98 860 |

Les durées d'import sont celles du parcours *commit* ; celles des simulations (0,715 / 1,459 / 2,171 s) et tous les détails machine-parseables sont dans `livrables/GET-INJS-PHASE-6-RESULTATS.json`. Chaque simulation s'est achevée sans persister, avec 100 % des propositions « placées » ; chaque commit s'est achevé avec 100 % des occurrences de ce scénario placées, mais **toutes restent des brouillons `PLACEE_QR_A_REVOIR`, non publiables**, faute de rapprochement attesté des participants et de géolocalisation configurée.

Vérification séparée des trois bases : 5 000/10 000/15 000 inscrits fictifs, 48 occurrences par groupe, respectivement 4 032/8 016/12 000 affectations, registres et instantanés ; zéro conflit détecté par l'index exact groupe/formateur/salle/date ; zéro clé QR divergente ; zéro participant QR inventé ; zéro pointage. **Cette vérification ne valide ni les volumes officiels ni la concurrence multi-auteurs.**

Fenêtre manuelle simulée *après* le commit annuel : 30 groupes, 4 nouvelles lignes sur la semaine fictive du 14 au 17 septembre 2099, 120/120 placements et QR sans publication à chaque taille. p95 d'un groupe/une semaine : **0,160 / 0,187 / 0,222 s** pour 5k / 10k / 15k ; SQL 5 112 pour les 120 lignes. Fenêtre sur base neuve : p95 **0,116 / 0,131 / 0,133 s**. Ces mesures appellent les services directement (pas de navigateur, API ou worker concurrent), et la semaine tardive est peu occupée : **ne pas les généraliser à une semaine saturée**.

## Anomalie de couverture découverte et correction conservatrice

Le premier commit annuel de 5k avec le même jeu synthétique ne plaçait que **2 747 / 4 032** séances (1 285 `PROPOSITION_EXPIREE`, 118,794 s). Le simulateur annuel et la revalidation sur une *seule date* ne classaient pas les candidats dans la même fenêtre : un candidat dur valide pouvait sortir du **top 4 des alternatives du jour** puis être rejeté à tort. Les refus suivants pouvaient aussi venir de l'occupation modifiée par les commits précédents.

Correction : la présence dans le top 4 n'est plus utilisée comme **contrainte dure** dans `appliquer_ligne`. Le service contrôle toujours explicitement calendrier, date/créneau/durée, capacité/type de salle, indisponibilité de salle/formateur et occupation SQL sous verrou avant d'écrire. Une campagne qui reçoit une proposition expirée, occupée ou indisponible recalcule **depuis l'occupation SQL actuelle** et n'applique que la nouvelle décision revalidée ; jamais de forçage ni de remplacement de registre QR. L'API manuelle conserve en outre son contrôle initial des alternatives soumises. Sur ce scénario identique, le commit final place 4 032 / 4 032 en 139,220 s : **meilleure couverture mais temps plus élevé**, sans extrapoler ce résultat à d'autres jeux.

## Contrôles logiciels

- Copie isolée : `python manage.py check` OK ; `python manage.py makemigrations edts --check --dry-run` : aucune nouvelle migration ; migration du schéma de test jusque `edts.0013` / `scolarite.0020` OK. `git diff --check` OK. Aucune migration ajoutée en phase 6.
- Tests ciblés phase 2–6, interop QR, génération historique, publication, supervision : **178 tests découverts, 177 réussis et 1 volontairement ignoré**. Le test de concurrence PostgreSQL ajouté est `TransactionTestCase`, ignoré sur SQLite : **un skip n'est pas une preuve de verrouillage**.
- API historique/LMD/annuelle : **109 tests réussis** sur la même extraction isolée. Un avertissement de répertoire de statiques absent dans la copie de test est sans effet. Build/test frontend phase 5 inchangé (déjà validé en phase 5), non relancé ici.
- Scripts livrés : `scripts/mesurer_charge_getinjs_v2.py` (simulation, commit, fenêtre courte sur base neuve), `scripts/mesurer_semaine_apres_charge_v2.py`, `scripts/verifier_charge_getinjs_v2.py` ; tests : `backend/edts/tests/test_phase6_revalidation.py` et `test_phase6_postgres_concurrency.py` ; moteurs modifiés : `backend/edts/moteur/application_v2.py` et `campagnes_v2.py`. Résultats agrégés : `livrables/GET-INJS-PHASE-6-RESULTATS.json`. Les CSV et bases volumineuses restent sous `/tmp`, hors Git.

Commandes représentatives (à lancer **uniquement** dans une copie isolée pré-migrée du commit de référence enrichie sélectivement, avec variables de test) :

```sh
python scripts/generer_charge_getinjs_v2.py --etudiants 5000 --sortie /tmp/getinjs-phase6-csv-5000
# Depuis $BACKEND_ISOLE, schéma déjà migré, avec $REPO = dépôt des scripts :
PYTHONPATH="$BACKEND_ISOLE" DJANGO_SETTINGS_MODULE=config.settings DJANGO_DEBUG=1 \
  USE_SQLITE=1 SQLITE_PATH=/tmp/getinjs-phase6-commit-5000.sqlite3 \
  GETINJS_PHASE6_ISOLATED=1 python "$REPO/scripts/mesurer_charge_getinjs_v2.py" \
  --csv-dir /tmp/getinjs-phase6-csv-5000 --etudiants 5000 \
  --mode commit --budget-secondes 600
```

## Décision et blocages avant toute activation

- La cible **≤ 10 minutes pour 5 000 étudiants fictifs** et le RSS mesuré **< 1 Gio** sont atteints **sur ce seul banc SQLite isolé** ; la cible ≤ 10 s pour un groupe/semaine l'est sur la fenêtre mesurée. Cela **ne prouve pas** les mêmes objectifs sur PostgreSQL ni avec volumes réels, calendrier institutionnel, ressources rares extrêmes, concurrence, API+worker supervisé ou charge du serveur. Les 10k/15k sont mesurés, non soumis à la cible 5k de 10 minutes (15k : 722,496 s).
- Aucun serveur PostgreSQL local disponible : pas d'`EXPLAIN ANALYZE`, pas de test de verrous concurrents ou de profilage d'index PostgreSQL. **Bloquant pour qualifier la concurrence** ; la classe de test conditionnelle est prête mais non exécutée.
- Les 134 961 requêtes SQL pour 5k (≈ 33,5 par occurrence) signalent un coût N+1/une contention potentielle à profiler avant une montée en charge réelle. Le scénario est monotone, ne garantit ni équité pédagogique ni conformité des volumes CM/TD/TP officiels.
- Pas de rapprochement certifié des identités QR ni de géolocalisation complète ; publication v2 reste bloquée, y compris en `force`. Les routes historiques ne sont pas toutes basculées sur un service d'écriture unique, et aucune campagne/worker institutionnel n'est activé.

**Validation sollicitée : acceptez-vous ces résultats phase 6 comme qualification *strictement locale et synthétique*, avec PostgreSQL/concurrence, données institutionnelles et publication toujours bloquants ?** Aucune opération de production ou déploiement ne sera engagée sur cette validation seule.
