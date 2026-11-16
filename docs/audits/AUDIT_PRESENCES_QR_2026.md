# Audit ciblé — Présences QR (15 novembre 2026)

**Périmètre :** code local de la branche ; tests Django isolés ; aucun scan réel ni accès à des comptes de production. **Verdict : ORANGE** (flux testés mais garanties anti-fraude et concurrence insuffisamment prouvées).

## Chaîne et fonctionnalités observées

- Deux canaux historiques **réutilisés**, non doublés : `formations.SessionModule` pour l'ancien badgeage ; `edts.AffectationCreneau` publié pour LMD. Jeton commun `formations.QRToken`, pointage `presences.Pointage`, journal `presences.AuditLog` ; vues `presences/views.py`, `seances_edt_api.py`, services `seances_edt_services.py`, `geofence.py`, `participant_scope.py`, statistiques, rattrapages, auto-clôture et heartbeat. Frontend : `frontend/src/pages/presences/`, Flutter : `qr_badge_mobile/lib/pages/scan_page.dart` et `services/scan_service.dart`. **Flutter non exécuté** (SDK non vérifié).
- Génération QR par enseignant/agent habilité (`qr_seance`), vérification de séance du jour, expiration à la fin de la fenêtre et désactivation à la clôture. Scan mobile authentifié `/api/scan/secure/` (identité issue du compte), ou canal LMD `/api/presences/seances-edt/scan/`. Flux entrée → sortie, doublon après sortie refusé ; émargement manuel à motif, registre et export ; géofence et heartbeat côté serveur. Le scan public `/api/scan/` est `AllowAny` mais **désactivé par défaut hors DEBUG** (`PUBLIC_QR_SCAN_ENABLED`) ; état effectif de cette variable en production inconnu.
- **214/214 tests** du paquet `presences` passent sur la base de test isolée ; les tests couvrent scan, hors-groupe, expiration, historique, géofence, heartbeat, émargement et clôture. Cela ne prouve ni la conformité des appareils réels ni les courses concurrentes en PostgreSQL, ni la configuration du VPS.

## Risques précis

| ID | Gravité | Observation vérifiable | Conséquence / action |
|---|---|---|---|
| QR-01 | P1, **LMD corrigé localement** | `seances_edt_services.resoudre_jeton_lmd` redirigeait un jeton **inactif** vers le dernier actif ; la voie legacy `views.secure_scan_view` le fait encore. | La voie LMD refuse désormais l'ancien jeton (test ancien rejeté / nouveau accepté). Le comportement legacy reste à arbitrer et corriger avec tests dédiés. Le mobile doit scanner le QR régénéré. |
| QR-02 | P1, **atténué localement** | `badger_scan` verrouillait seulement les pointages existants, sans contrainte DB unique `(séance, date, personne)` sur `Pointage`. | Un verrou `select_for_update()` sur la ligne de la personne précède maintenant le premier scan (76 tests QR ciblés OK). Il reste à prouver deux requêtes simultanées sous PostgreSQL et à auditer les doublons historiques avant d'envisager une contrainte DB. |
| QR-03 | P1 | `geofence.verifier_position` autorise si aucun site localisé. `site_de_seance_edt` tente un rapprochement par **nom de salle**, puis l'unique site actif ; plusieurs sites ou nom ambigu peuvent laisser le site indéterminé. | Une absence de géofence n'atteste pas la présence physique. Associer la salle par FK quand possible, rendre la situation visible, déterminer la politique de refus avant changement. GPS est falsifiable ; contrôle sur place proportionné indispensable. |
| QR-04 | P1, **corrigé localement** | `generer_jeton` journalisait la valeur complète du jeton QR dans `AuditLog.extra['token']`. | Le journal des **nouvelles** générations ne stocke plus le secret (48 tests QR/EDT passent après correction). Les anciennes valeurs restent en base et ne doivent être traitées qu'avec une procédure de production autorisée. |
| QR-05 | P1 | `ecue_de_seance` ne déduit l'ECUE que de `affectation_pedagogique_id` ; les séances issues des maquettes importées ont `None`. | `Pointage.ecue_lmd` peut rester vide bien que la séance soit issue d'une ECUE ; risque pour statistiques/notes par ECUE. Tester la chaîne import → EDT → pointage, puis décider d'une FK ECUE explicite sur séance avant tout backfill. |
| QR-06 | P2 | `device_id` est fourni par le client ; `DeviceBinding` bloque un identifiant déjà rattaché à un autre compte, mais ne constitue pas une attestation matérielle. | Partage d'identifiants ou clients modifiés restent possibles. Auth forte/MFA, renouvellement, contrôle d'appareil et revue humaine ; ne jamais prétendre prouver une présence physique par QR seul. |
| QR-07 | P2 | Scan public configurable, durée de session et positions mobiles ; bascule production non inspectée. | Vérifier `PUBLIC_QR_SCAN_ENABLED`, la durée réelle des jetons, la rétention GPS et les habilitations de lecture du journal ; tests manuels sur appareils et fuseaux. |
| QR-08 | P1 à confirmer | `seances_edt_api.qr_seance` protège GET par `ExigePermission('presences.qr.generer')` mais vérifie `service.peut_gerer_seance(user, affectation)` uniquement pour POST. | Si cette permission est plus large que l'habilitation à **cette** séance, un lecteur peut récupérer son jeton actif. Écrire un test avec utilisateur autorisé globalement mais non affecté, puis aligner GET sur la garde objet sans casser les usages légitimes. |

## Scénarios et intégration

| Scénario | Preuve/état |
|---|---|
| QR généré, ouvert, expiré et fermé | Tests `test_seances_edt.py` / `test_seances_edt_mobile.py` et services : couvert en isolation. |
| Inscription/groupe, statut et identité du compte | `autorisation_badgeage`, `membres_groupe` et tests hors-groupe : couverts sur fixtures ; cas multi-cohorte importée non démontré de bout en bout. |
| Double scan séquentiel / scan après sortie | Tests et logique `badger_scan` : couverts ; **simultané non prouvé** (QR-02). |
| Réseau absent / mode dégradé | Offline-data et commandes présents ; synchronisation sûre d'une entrée hors ligne non établie dans cet audit. |
| Fraude par partage | Jeton de séance partagé ; auth, groupe, fenêtre, GPS réduisent le risque mais photo du QR + appareil/position falsifiés ne sont pas exclus. |

**Avant usage institutionnel :** traiter le canal QR legacy (QR-01), terminer la preuve de concurrence PostgreSQL et d'unicité (QR-02), l'intégration QR-05, prévoir le traitement contrôlé des anciens secrets QR-04, puis effectuer une validation fonctionnelle encadrée sur appareils réels. Ne pas modifier la production pendant cet audit.
