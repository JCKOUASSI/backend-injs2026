# GET-INJS — phase 4 : intégration Présences QR (locale, isolée)

**Statut : implémentée et testée sur une copie isolée ; validation métier demandée avant toute phase 5. Aucun déploiement, commit ni push de phase 4.**

## Périmètre et décision

Référence de production imposée : `70d08dad1821caceb61b22fe22cf70e13155bf18`, à `edts.0012` et `scolarite.0020`. Le banc est une extraction isolée de cette référence, enrichie uniquement des fichiers des phases 2–3 puis des fichiers phase 4 concernés. Le dépôt de travail contient par ailleurs des changements locaux de volumes/maquette, notamment `scolarite.0021` : **ils ne font pas partie de ce test ni de la refonte**. Aucun service de production ni donnée réelle n'a été consulté.

Le prototype est limité aux écritures `DEBUG=True`, `GETINJS_V2_EXPERIMENTAL_WRITE=True`, années `BENCHMARK-*`. Aucun EDT complet n'est généré ni publié automatiquement. Les dates académiques 2026–2027 et les propositions de volumes ne deviennent pas officielles.

- À la création d'une occurrence datée : création transactionnelle d'un registre QR brouillon à clé v2 et UUID stable, et d'un instantané **d'effectif importé uniquement**. Aucun identifiant `Participant` n'est fabriqué à partir des imports.
- Rejeu : réutilise le même registre et le même instantané ; collision de clé, registre orphelin ou registre legacy de clé différente : refus, sans réattribution silencieuse.
- Déplacement : seulement pour une séance brouillon future sans pointage, avec la même affectation et le même UUID ; version/historique et nouvel instantané daté, ancien instantané préservé. Publication, date passée et pointages bloquent le déplacement.
- Rattrapage : nouvelle affectation, nouveau registre/UUID et lien à la séance d'origine annulée ou terminée, même cohorte et même année ; pointages, événements et historique de l'origine restent en place. Motif exigé.
- Compatibilité : les points d'entrée existants de réconciliation QR reconnaissent les clés v2 sans retomber sur la clé legacy. Le parcours legacy sans occurrence v2 conserve son comportement.
- Publication : contrôle en lecture seule des occurrences v2 ; registre/instantané absent, géolocalisation manquante et identités QR non rapprochées refusent la publication, même avec `force=True`. **L'instantané d'effectif importé reste non attesté même si sa liste `participants` était modifiée manuellement** ; aucun processus d'attestation d'identités QR n'est fourni par cette phase.

## Fichiers de phase 4

- `backend/edts/moteur/qr_v2.py` (nouveau) ;
- `backend/edts/moteur/application_v2.py`, `campagnes_v2.py`, `interop_presences.py`, `publication.py` ;
- `backend/edts/tests/test_qr_v2_phase4.py` (nouveau), `test_moteur_v2_phase3.py` (contrat adapté) ;
- ce rapport.

Aucune migration ajoutée en phase 4. Les autres modifications locales du dépôt ne sont pas revendiquées dans ce périmètre.

## Contrôles exécutés — copie isolée SQLite

Variables : `DJANGO_SETTINGS_MODULE=config.settings DJANGO_DEBUG=1 USE_SQLITE=1` et `SQLITE_PATH` sous `/tmp`. Interpréteur `.venv/bin/python` ; exécution depuis le dossier `backend` de la copie de `70d08da` enrichie sélectivement. Commandes :

```sh
python manage.py check
python manage.py makemigrations edts --check --dry-run
python manage.py migrate --noinput
python manage.py test edts.tests.test_qr_v2_phase4 edts.tests.test_moteur_v2_phase3 edts.tests.test_fondations_v2 edts.tests.test_interop_presences edts.tests.test_generation_annee edts.tests.test_campagnes edts.tests.test_lot2_publication_api presences.test_seances_supervision --noinput
```

Résultat final : **170 tests réussis**, zéro échec ; `check` sans anomalie ; aucune migration supplémentaire détectée pour `edts` ; migrations jusqu'à `edts.0013` et **`scolarite.0020` seulement** appliquées sur la base SQLite isolée. `git diff --check` sans anomalie. Un avertissement de répertoire `staticfiles` absent apparaît pendant les tests, sans échec.

## Limites et risques à valider

1. **Publication volontairement bloquée pour les occurrences v2 à effectif importé** : rapprochement attesté `Participant`/inscriptions, contrôle administratif des participants et activation explicite requis avant toute publication. Le prototype ne prétend pas délivrer ce processus.
2. Verrouillage concurrent PostgreSQL, déduplication sous forte concurrence, intégration réelle du lecteur de présence et performance annuelle 5 000/10 000/15 000 étudiants restent non prouvés ; les résultats SQLite ne sont pas une qualification production.
3. L'EDT legacy, les écrans et les routes existantes ne sont pas supprimés, mais les protections v2 doivent être auditées de bout en bout avant exploitation. Une réconciliation manuelle reste requise pour les registres historiques incompatibles ou orphelins.
4. Pas de mesure des cibles ≤ 10 min/an (5 000 étudiants), RSS < 1 Gio et ≤ 10 s groupe/semaine dans cette phase.

**Point de validation demandé : acceptez-vous la phase 4 comme prototype conservateur, publication v2 bloquée jusqu'à rapprochement QR attesté, avant d'autoriser éventuellement la phase 5 ?**
