# GET-INJS — diagnostic QR agrégé sur données synthétiques isolées

**Statut : diagnostic local en lecture seule ; aucune réconciliation des identités, publication ou activation.** Suite de la qualification PostgreSQL isolée et de l'audit des chemins d'écriture. Référence déployée de la mission : `70d08dad1821caceb61b22fe22cf70e13155bf18` (`edts.0012`, `scolarite.0020`) ; tests sur extraction isolée enrichie, sans la migration locale `scolarite.0021`.

## Outil

`scripts/diagnostiquer_qr_getinjs_v2.py` restitue uniquement des **comptages** : occurrences v2 (y compris inactives), registres liés et leurs clés, instantanés d'effectif importé, pointages et anomalies de prépublication des séances actives. Il appelle le préflight métier existant `anomalies_publication_v2`, sans le modifier. Aucun nom, matricule, UUID, identifiant individuel, coordonnée GPS ou liste de participants n'est exporté.

Gardes cumulatives : `DEBUG`, `GETINJS_PHASE6_ISOLATED=1`, une base locale SQLite sous `/tmp/` ou une base PostgreSQL BENCH locale sur le socket de test explicitement prévu et `GETINJS_PG_ISOLATED=1` ; **une seule année et libellé BENCHMARK**. Le script active en outre le mode SQL **lecture seule** pour sa connexion (`PRAGMA query_only` ou `default_transaction_read_only`). Il ne met jamais `GETINJS_V2_EXPERIMENTAL_WRITE` à vrai. Les gardes ne sont pas une autorisation de consulter des données institutionnelles : l'outil est réservé au jeu synthétique isolé.

Exécution représentative sur la copie isolée avec `PYTHONPATH` pointant vers son répertoire `backend` :

```sh
USE_SQLITE=1 SQLITE_PATH=/tmp/getinjs-phase6-commit4-5000.sqlite3 \
 GETINJS_PHASE6_ISOLATED=1 DJANGO_DEBUG=1 \
 DJANGO_SETTINGS_MODULE=config.settings PYTHONPATH="$BACKEND_ISOLE" \
 python "$REPO/scripts/diagnostiquer_qr_getinjs_v2.py"
```

## Résultat des bases SQLite BENCH déjà disponibles (et non de production)

| Étudiants fictifs | Occurrences v2 | Registres et instantanés | Clés liées incohérentes | Pointages | Identités non rapprochées | Géolocalisation incomplète |
|---:|---:|---:|---:|---:|---:|---:|
| 5 000 | 4 032 | 4 032 / 4 032 | 0 | 0 | 4 032 | 4 032 |
| 15 000 | 12 000 | 12 000 / 12 000 | 0 | 0 | 12 000 | 12 000 |

Les 4 032 et 12 000 instantanés reposent uniquement sur l'**effectif importé**, sans liste QR attestée. La sortie déclare toujours `publication_autorisee: false` : un diagnostic n'est jamais une attestation. Le décompte d'anomalies du préflight concerne les **occurrences actives**, tandis que les autres compteurs indiquent leur propre périmètre. Ces données ne constituent pas une estimation du nombre de personnes réelles à rapprocher.

Contrôles : exécution sur deux bases BENCH synthétiques préexistantes ; empreintes SHA-256 des deux fichiers SQLite **inchangées** entre avant et après les diagnostics ; refus attendu lorsque `GETINJS_PHASE6_ISOLATED` est absent ; `git diff --check` sans anomalie. Aucun test de ce nouvel outil n'a été réalisé sur PostgreSQL ni sur données institutionnelles, et aucune preuve de correspondance `InscriptionImportee` ↔ `Participant` n'a été produite.

## Suite conditionnée

L'attestation du calendrier et des volumes 2026–2027, le rapprochement contrôlé des identités QR, la configuration géographique des salles et l'essai sur une infrastructure cible de test requièrent des pièces/validations externes et un périmètre explicitement autorisé. **Ne pas importer les propositions locales hypothétiques ni publier l'EDT v2 sur la base de ce diagnostic.**
