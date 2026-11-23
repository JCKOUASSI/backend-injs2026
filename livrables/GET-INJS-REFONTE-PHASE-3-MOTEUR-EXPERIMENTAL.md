# GET INJS APP — Phase 3 : moteur expérimental, sans activation production

Référence fonctionnelle : commit déployé `70d08dad1821caceb61b22fe22cf70e13155bf18` ; phase 2 validée. **Aucun déploiement, aucune migration exécutée en production, aucune donnée personnelle réelle.** Ce livrable ne prétend pas que l'année réelle est générée ou publiable : les volumes officiels et l'intégration QR de phase 4 manquent toujours.

## 1. Résumé

Un noyau de planification **par ligne** est disponible pour des essais isolés : sélection datée de candidats, contrôle calendrier/salle/effectif/disponibilité/occupation, classement déterministe par graine, score souple pondéré, résultat `PLACEE`, `ECHEC` ou `A_REVOIR` avec cause. Le manuel et l'automatique appellent le même solveur. Le mode simulation n'écrit aucune séance ni checkpoint. Un worker exécutable en arrière-plan traite une exécution par groupes avec lease, heartbeat et checkpoint transactionnel ; une interruption contrôlée reprend sans doublonner les lignes déjà validées. L'édition manuelle permet ajout, proposition d'alternatives et déplacement **uniquement sur une base BENCHMARK sans registre QR**.

**Verrou de sécurité obligatoire :** toute écriture v2 vérifie simultanément `DEBUG=True`, `GETINJS_V2_EXPERIMENTAL_WRITE=True` (désactivé par défaut) et un libellé d'année commençant par `BENCHMARK-`. Le worker CLI n'est **pas** lancé automatiquement par le site, et aucune route/API existante n'est modifiée. Même si un paramètre de campagne était présent, la source DB disponible en phase 3 refuse de qualifier seule les volumes d'officiels : elle produit `A_REVOIR/VOLUME_NON_CONFIRME` et **zéro placement**. Seuls les travaux d'essai explicitement attestés en mémoire des tests peuvent placer une ligne dans la base isolée. Ne jamais activer ce flag en production.

## 2. Décisions et justification

- `TravailSeance` est identifié par hash stable `(année, groupe, ECUE, type, ordinal)` : aucun intitulé seul, horaire, salle ou enseignant n'entre dans sa clé. Un calendrier sans période officielle validée, un volume sans preuve, un enseignant absent ou une plage historique active sont bloquants ; pas de zéro CM/TD/TP interprété comme inapplicable.
- La simulation maintient un index de placements virtuels au fil des lignes ; deux groupes ne peuvent recevoir la même salle/enseignant simultanément même sans écriture. Le solveur évalue les dates ouvrées une à une, les salles compatibles/capacités et les disponibilités `INDISPONIBLE`. Les préférences, surcharge, consécutivité et trous sont des **pénalités souples**, non des exemptions de contraintes dures. La graine et l'ordre des candidats déterminent le choix ; alternatives bornées renvoyées au manuel.
- Une application BENCH transactionnelle verrouille l'année puis la ligne `(année, date)`, recharge l'occupation et le calendrier, revalide le candidat, vérifie l'EDT `BROUILLON` et écrit une affectation **datée** seulement si aucun conflit. Rejouer la même clé et la même position retourne `DEJA_PLACEE`. Un changement de position avec clé existante n'est pas remplacé silencieusement.
- Un déplacement BENCH verrouille les deux dates dans l'ordre, exclut l'ancienne ligne de l'index puis revalide avec le même solveur. **Tout registre QR ou pointage bloque le déplacement** ; aucun registre, événement, historique, instantané ou affectation QR n'est supprimé, désactivé ou recréé. Les séances BENCH placées ne sont **pas publiables** avant l'intégration QR : elles n'ont pas de registre. La phase 4 doit fournir l'UPSERT QR et les tests de préservation avant toute levée du verrou.
- L'exécution groupe par groupe emploie `.iterator(chunk_size=256)` pour les groupes/affectations DB, `itertools.groupby` pour les travaux ordonnés, `bulk_create(batch_size=256)` pour les résultats, et une transaction par groupe. Le lease est enregistré sur `ExecutionCampagne`; un second worker le refuse tant qu'il est actif. La reprise ignore les clés déjà checkpointées. Le bilan final a `statistiques.non_publiable_sans_qr=True`, le score souple et les compteurs. Aucun besoin horaire calculé n'est persisté comme vérité institutionnelle.

## 3. Fichiers modifiés/créés

- `backend/edts/moteur/occupation_v2.py` : lecture de charge et score souple pondéré en bitsets.
- `backend/edts/moteur/planification_v2.py` : travail/décision typés, candidat par date/créneau/salle et déterminisme.
- `backend/edts/moteur/application_v2.py` : façade manuelle/automatique, revalidation sous verrou et refus QR conservateur.
- `backend/edts/moteur/campagnes_v2.py` : simulation incrémentale et worker avec reprise/checkpoint par groupe.
- `backend/edts/management/commands/traiter_campagne_v2.py` : invocation ponctuelle par un worker supervisé **de test** ; jamais appelée par HTTP ou CI.
- `backend/edts/tests/test_moteur_v2_phase3.py` : scénarios synthétiques de simulation, édition, conflit, calendrier, QR, reprise et rollback.
- `livrables/GET-INJS-REFONTE-PHASE-3-MOTEUR-EXPERIMENTAL.md` : présent rapport.

## 4. Commandes de test et résultats

Sur une copie isolée du code au commit de référence avec **seuls** les fichiers v2 des phases 2–3 copiés, base SQLite de test (aucun accès PostgreSQL ou production) :

```text
manage.py makemigrations --check --dry-run     → No changes detected
manage.py check                                 → System check identified no issues
manage.py test edts.tests.test_moteur_v2_phase3 edts.tests.test_fondations_v2
               edts.tests.test_generation_annee edts.tests.test_campagnes
               edts.tests.test_interop_presences --noinput
                                               → 105 tests OK
```

La suite de 105 comprend **14 tests v2**, **14 tests fondations** et **77 tests existants**. Elle couvre notamment disponibilité dure, politique souple, double lease, rollback d'un groupe, calendrier/conflit sous écriture, idempotence et protection QR. Après cette suite, la gestion conservatrice des occupations incohérentes et des exécutions vides a été vérifiée par la suite v2 dédiée (**15 tests OK**) et par `git diff --check`. Les 105 tests complets n'ont pas été relancés après ces ajustements. Les bancs synthétiques 5k/10k/15k produits en phase 2 **ne sont pas encore une preuve de performance annuelle** ; aucun objectif ≤10 min / <1 Gio / ≤10 s n'est revendiqué.

## 5. Limites, risques, étapes encore nécessaires

1. **Phase 3 limitée volontairement à BENCH** : aucune source vérifiable de volumes/applicabilité n'a été validée pour le moteur v2. Le flux DB produit donc des anomalies, pas des horaires. Le paramètre `source_confirmee` ne constitue pas une attestation institutionnelle en soi ; il ne peut autoriser l'écriture **que** dans les essais BENCH. Pour la vraie année, il faut une preuve de volume/type par ECUE/UE et le calendrier validé, sans dépendre de la migration locale `scolarite.0021`.
2. **Phase 4 QR indispensable** : il n'existe pas encore d'UPSERT de `SeanceRegistre`/instantanés/événements pour les nouvelles occurrences ; une séance BENCH reste non publiable. L'identité legacy `cle_metier` et les séances ouvertes/pointées exigent audit avant déverrouillage. Des séries historiques non datées bloquent conservativement les propositions.
3. **PostgreSQL de test et montée en charge** : les verrous `select_for_update` ne sont pas réellement éprouvés par SQLite ; la simulation conserve l'occupation en mémoire par date/ressource, et l'application effectue encore plusieurs relectures SQL par ligne. Profilage `EXPLAIN`, tests concurrents et mesure d'une année complète à 5k/10k/15k restent requis. Aucun serveur PostgreSQL local n'est disponible dans cet environnement ; ne pas confondre réussite SQLite et preuve de performance/concurrence.
4. **Phase 5 UI/API** : les routes historiques ne sont pas encore raccordées ; le worker est une commande ponctuelle à superviser, pas une file de tâches déployée. La régénération partielle est exprimable par un sous-flux de groupes/dates, mais le service de diff des révisions calendaires n'est pas encore construit. La correction des clés QR et les contrôles de permission viendront avant exposition HTTP.

**Arrêt de phase :** demander validation de ce prototype expérimental et de ses limites. Ne pas déployer ni activer le flag ; passer à l'intégration QR de phase 4 seulement après accord explicite. Les critères finaux de génération annuelle ne sont **pas** atteints à cette étape.
