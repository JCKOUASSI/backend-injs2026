# GET INJS APP — Phase 2 : fondations (arrêt avant phase 3)

Référence : code déployé `70d08dad1821caceb61b22fe22cf70e13155bf18`, schéma `edts.0012` / `scolarite.0020`. Conception approuvée : `GET-INJS-REFONTE-PHASE-1-CONCEPTION.md`. La branche Arena est autorisée ; les changements locaux préexistants sur les volumes/UE/ECUE et la migration **locale non déployée** `scolarite.0021` ne sont ni utilisés, ni réécrits, ni inclus au commit de cette phase. Aucun accès au VPS/production, aucune connexion à une base réelle, aucun calendrier institutionnel injecté.

## 1. Résumé

Fondations additives, encore **inactives** pour la génération : quatre nouvelles tables techniques/calendrier, colonnes facultatives sur les affectations et exécutions, lecture conservatrice du calendrier daté, index d'occupation par date et ressources, générateur de charge fictive hors base. Le moteur actuel, ses routes, ses campagnes, ses modifications manuelles et le module QR ne sont **pas raccordés** à ces fondations dans cette phase. Aucun nouvel EDT/registre/instantané n'est créé et aucune publication n'est déclenchée.

## 2. Décisions et justifications

- `edts.0013` dépend seulement des migrations déployées : `edts.0012`, `scolarite.0020`, `formations.0102` et utilisateur substituable. Opérations : **4 CreateModel, 24 AddField, 7 AddIndex, 7 AddConstraint** ; aucun Remove/Rename/RunPython/RunSQL. Les colonnes historiques ajoutées à `AffectationCreneau` sont NULL ; les plages et liens QR existants sont intacts. Index partiels pour les trois ressources quand date présente et placement actif ; contraintes de semaines/horaires pour les occurrences nouvelles.
- Calendrier : périodes COURS/VACANCES/EXAMENS/FERIE/FERMETURE liées à une année et une révision, portée GLOBAL/FORMATION/NIVEAU/GROUPE, avec source, fiabilité et validation. Les checks DB protègent bornes et exclusivité des portées ; `full_clean()` vérifie source officielle, année et groupe. À l'évaluation, **aucune période validée = refus** ; toute période applicable non confirmée = refus ; fermeture/férié prévaut ; une contradiction de même portée est `CALENDRIER_AMBIGU`. Dates fériées mobiles : aucune valeur codée ni chargée dans la vraie année.
- Semaine : numéro académique à partir de `date_debut`, bornes inclusives, dernière semaine potentiellement incomplète. Pas de numéro ISO ni déduction du semestre depuis le seul calendrier provisoire.
- Occupation : bitsets minute sur 1 440 minutes par `(date, GROUPE/FORMATEUR/SALLE, identifiant)` ; intervalle `[début, fin)`, refus des plages historiques non datées. **Ce n'est pas encore un service d'écriture concurrent** : le verrou SQL `VerrouJour` est défini mais aucun chemin n'y écrit. Il sera activé en phase 3 après redirection de toutes les écritures.
- Checkpoints : `ExecutionLigne` conserve résultat technique et code d'anomalie par clé unique d'exécution, sans persister un volume institutionnel. `ExecutionCampagne` reçoit les compteurs, le lease et le heartbeat facultatifs ; **aucun worker nouveau n'est démarré**.
- Charge : `scripts/generer_charge_getinjs_v2.py` écrit des CSV fictifs non importables en base. Gabarit FERIE mobile **sans date et à confirmer**, pas d'ensemencement d'une année réelle. Les besoins test utilisent seulement le type CM fictif, pas une ventilation officielle CM/TD/TP.

## 3. Fichiers concernés

- `backend/edts/models.py` — ajout de champs optionnels/index/checks et enregistrement des modèles v2.
- `backend/edts/models_fondations.py` — `RevisionCalendrier`, `PeriodeAcademique`, `ExecutionLigne`, `VerrouJour`.
- `backend/edts/migrations/0013_executionligne_periodeacademique_revisioncalendrier_and_more.py` — schéma additif.
- `backend/edts/moteur/calendrier_v2.py` — règles pures de semaines/périodes, lecteur `.iterator(chunk_size=...)`.
- `backend/edts/moteur/occupation_v2.py` — index daté in-memory, aucune écriture DB.
- `backend/edts/tests/test_fondations_v2.py` — tests calendrier, contraintes SQL, checkpoints et conflits.
- `scripts/generer_charge_getinjs_v2.py` — données de charge fictives hors dépôt.
- `livrables/GET-INJS-REFONTE-PHASE-2-FONDATIONS.md` — rapport de phase.

## 4. Commandes de vérification (copie du commit exact + SEULS les fichiers de la phase 2)

- `manage.py makemigrations --check --dry-run` → **No changes detected** ; `manage.py check` → **aucune erreur**.
- `manage.py test edts.tests.test_fondations_v2` → **14 tests OK** sur SQLite isolée.
- `manage.py test edts.tests.test_fondations_v2 edts.tests.test_generation_annee edts.tests.test_campagnes edts.tests.test_interop_presences` → **90 tests OK** sur SQLite isolée (avant ajout du 14e test de checkpoint ; ce dernier a ensuite été testé séparément). Avertissement sans effet de dossier `staticfiles` absent dans l'archive.
- Sur une **copie** de SQLite de test migrée jusqu'à `edts.0012` : migration `edts.0013` → **OK**, présence des quatre tables et de `date_seance` vérifiée ; migration inverse vers `edts.0012` → **OK**, tables antérieures préservées. **Aucune migration exécutée en production.**
- Générateur : sorties `/tmp` 5 000 / 10 000 / 15 000 étudiants synthétiques, respectivement 84 / 167 / 250 groupes et 336 / 668 / 1 000 besoins fictifs ; compte des lignes CSV et manifeste vérifiés. **Aucun essai de génération annuelle/mesure de performance v2** : les mesures avant/après restent une tâche de phase 6.
- Audit statique de la migration : uniquement `CreateModel`/`AddField`/`AddIndex`/`AddConstraint` ; pas de dépendance à `scolarite.0021`. `git diff --check` : sans erreur.

## 5. Risques, limites et décisions à valider

1. **Tests PostgreSQL requis avant toute activation/déploiement** : SQLite ne prouve pas `SELECT FOR UPDATE`, le comportement des index partiels et l'absence de conflits sous concurrence réelle. L'environnement de cette phase ne dispose pas d'un serveur PostgreSQL local ; la migration SQL PostgreSQL et l'éventuel `btree_gist` sont à évaluer dans un environnement de test isolé. Les nouvelles colonnes ne garantissent pas à elles seules l'absence de conflit entre anciens endpoints SQL directs.
2. Les `CHECK` SQL ne peuvent pas garantir une cohérence entre deux tables (année/révision/groupe), ni rendre immuables les lignes de révision : utiliser `full_clean()`/service transactionnel et verrouillage dans les phases 3–5 ; tout autre client contournant ce service devra être bloqué avant activation. Les périodes ne sont accessibles par aucune nouvelle interface dans cette phase.
3. Les plages historiques non datées et `cle_metier` QR ambiguës sont laissées intactes ; l'index v2 les **refuse explicitement** jusqu'à audit. Aucun backfill implicite, aucun faux participant QR, aucun volume institutionnel inventé.
4. La structure de révision existe mais le service de création/activation atomique de calendrier, le calcul des différences et la régénération partielle restent à réaliser. Les données provisoires `2026-2027` ne constituent pas une validation institutionnelle.

**Point d'arrêt :** valider ces fondations avant d'entamer la phase 3 (worker durable, génération et édition manuelle). Ne pas migrer la production ni activer la génération v2 à ce stade.
