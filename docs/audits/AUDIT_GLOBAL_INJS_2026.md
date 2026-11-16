# Audit global INJS-LMD 2026 — état vérifiable

**Date de référence : 15 novembre 2026.** Source : branche `arena/a8060ecf-backend-injs2026`, dépôt accessible dans cette session **`/home/user/backend-injs2026`** (le chemin macOS `/Users/jckouassi/Sites/audits-injs/backend-injs2026` indiqué dans la demande n'est pas monté ici). Git était propre avant l'audit ; aucun reset, migration, seed ni déploiement effectué. Production consultée **uniquement en GET public** (`/login`, `/admin/login/`, `/api/health/`). Les tests Django utilisent la base de test distincte, pas la base démo. **Le code local peut différer du code actuellement routé en production.**

## A. Synthèse exécutive et verdict

| Question | Réponse étayée |
|---|---|
| Globalement vert ? | **Non. Verdict global : ROUGE pour préparation institutionnelle sans réserves**, ORANGE pour fonctionnement général de la branche testée. |
| Fonctionnelle ? | De nombreux flux et 2 246 tests frontend passent ; Présences QR 214 tests passent ; l'EDT de l'année **n'est pas fonctionnel à l'échelle de la démo**. |
| Techniquement propre ? | Django `check` OK, migrations `makemigrations --check --dry-run` : aucune à créer. Build frontend OK, lint 0 erreur/0 avertissement après nettoyage (7 initialement) ; suite backend globale **3 137 tests OK, 9 sautés** après les correctifs. Contrat OpenAPI et protection des trois référentiels vérifiés (77 tests ciblés OK). |
| Suffisamment sécurisée ? | **Non démontré** : la page de connexion publique de production affichait des identifiants de démonstration, dont un compte d'administration ; la correction locale supprime leur affichage mais **ne révoque pas les secrets déjà divulgués**. Risques QR de révocation/concurrence/journal détaillés ci-dessous. |
| Prête pour une démonstration ? | **Démonstration encadrée de parcours ciblés seulement**, pas présentation d'un EDT annuel complet ou d'une présence infalsifiable. Ne pas mettre en production les corrections de cet audit sans procédure séparée et tests de non-régression sur la cible. |

### Contrôles effectivement exécutés

| Contrôle | Résultat |
|---|---|
| `backend/.venv/bin/python manage.py check` | 0 problème. |
| `manage.py makemigrations --check --dry-run --noinput` | « No changes detected ». Aucune migration créée/appliquée. |
| `STORAGES=STORAGE_DE_TEST backend/.venv/bin/python manage.py test --keepdb --noinput` (depuis `backend/`) | **Initial :** 3 136 tests, 4 échecs, 9 sautés (~856 s) : trois DELETE et un snapshot OpenAPI. **Après correctifs : 3 137 tests OK, 9 sautés (~847 s)** ; SQLite/test DB, pas preuve de concurrence PostgreSQL. |
| `manage.py test edts.tests presences.tests --keepdb --noinput` (sans `STORAGES`) | 518 tests, **3 erreurs** de rendu admin dues au manifeste de statiques manquant dans cette configuration de test ; 24/24 tests admin repassent avec `STORAGES=STORAGE_DE_TEST`. Ce n'est pas une preuve de panne admin en production (page de connexion GET répond). |
| `manage.py test presences --keepdb --noinput` | **214/214 réussis après révocation LMD**. |
| Après correction du serializer : `STORAGES=STORAGE_DE_TEST manage.py test config.tests.test_api_contract referentiels.tests.test_gestion_offre --keepdb --noinput` | **20/20 réussis**, snapshot de contrat inclus. |
| `frontend/npm run test:run` avant correction locale de Login | **143 fichiers / 2 245 tests réussis**. `npm run lint` initial : 0 erreur, 7 avertissements ; build OK (chunk principal >500 kB). |
| Après corrections frontend : test Login ciblé **10/10**, suite complète **143 fichiers / 2 246 tests OK** ; lint 0 erreur/0 avertissement ; build OK (chunk principal 1 661 kB). |
| GET production `/api/health/`, `/login`, `/admin/login/` | 200 pour santé (`database: ok`) et pages consultables au moment du GET ; **aucun test authentifié ou d'écriture**. Health ne certifie pas la fonctionnalité métier. |
| Mobile Flutter | SDK/build, tests appareils, réseau et magasins **non exécutés**. |

## B. Cartographie et matrice de santé

**Légende :** B/F/API/T/P : backend, frontend, routes API, tests présents, permissions repérées (`✓` code présent, `—` non constaté dans cette passe, `?` non établi). **Statut** : VERT = fonctionnalité réellement vérifiée ; ORANGE = preuves partielles ; ROUGE = anomalie importante ; NON VÉRIFIÉ = non vérifié. La présence d'un test dans une app ne signifie pas validation de tous ses sous-parcours. Aucune ligne VERT n'est attribuée au seul inventaire du code.

| Module Django / périmètre | B | F | API | T | P | Fonctionnel / statut | Anomalie ou limite principale |
|---|---:|---:|---:|---:|---:|---|---|
| `authentication` / utilisateurs, MFA | ✓ | ✓ | ✓ | ✓ | ✓ | **ROUGE** | Identifiants démo affichés sur le login public ; rotation obligatoire si utilisables. |
| `habilitations` / rôles et droits | ✓ | ✓ | ✓ | ✓ | ✓ | **ORANGE** | Moteur CURP et projection des capacités présents ; tests de profils réels non exhaustifs. |
| `administrations` | ✓ | ✓ | ✓ | ? | ? | **ORANGE** | CRUD/autorisation effectifs non parcourus de bout en bout. |
| `dashboard` | ✓ | ✓ | ✓ | ✓ | ? | **ORANGE** | Indicateurs et vues présents, vérité des agrégats VPS non validée. |
| `core` / services communs | ✓ | ✓ | ✓ | ? | ? | **ORANGE** | Infrastructure transversale ; validation ciblée insuffisante. |
| `referentiels` / nomenclatures, lieux, années | ✓ | ✓ | ✓ | ✓ | ✓ | **ORANGE** | DELETE interdit localement pour type d’évaluation, année et salle ; 77 tests ciblés OK ; branche non déployée. |
| `referentiel_injs` / sources officielles | ✓ | ✓ | ? | ? | ? | **ORANGE** | Exhaustivité et provenance de chaque ligne non revérifiées sur VPS. |
| `formations` / offre, salles, enseignants | ✓ | ✓ | ✓ | ✓ | ✓ | **ORANGE** | Données démo antérieures, pas de validation des 779 ECUE et ressources actuelles par cette mission. |
| `scolarite` / étudiants, groupes, inscriptions, maquettes, UE/ECUE | ✓ | ✓ | ✓ | ✓ | ✓ | **ORANGE** | Inscription pédagogique distincte et explicite par défaut ; intégration annuelle à vérifier. |
| `admissions` / candidatures, concours | ✓ | ✓ | ✓ | ✓ | ✓ | **ORANGE** | Chaîne admission→scolarité partiellement testée en isolation, non rejouée en production. |
| `edts` / GET INJS, génération, publication | ✓ | ✓ | ✓ | ✓ | ✓ | **ROUGE** | 90/39 146 séances par campagne globale antérieure ; manque la répartition temporelle annuelle. |
| `presences` / QR, émargement, absences | ✓ | ✓ | ✓ | ✓ | ✓ | **ORANGE** | Voies QR révoquées refusées localement ; concurrence PostgreSQL non démontrée. |
| `suiviEvaluation` / évaluations historiques | ✓ | ✓ | ✓ | ✓ | ? | **ORANGE** | Coexistence avec `evaluations` à expliciter ; contrats distincts. |
| `evaluations` / évaluations académiques | ✓ | ✓ | ✓ | ? | ? | **ORANGE** | Tests de flux notes→jury non complets dans cet audit. |
| `jurys` / délibérations | ✓ | ✓ | ✓ | ? | ? | **ORANGE** | Validation métier et droits par statut à compléter. |
| `graduation` / résultats, diplômes | ✓ | ✓ | ✓ | ? | ? | **ORANGE** | Éditions et publications non rejouées en conditions institutionnelles. |
| `equivalences` | ✓ | ✓ | ✓ | ? | ? | **ORANGE** | Équivalences et leur effet sur résultats non vérifiés de bout en bout. |
| `finances_etudiantes` / frais | ✓ | ✓ | ✓ | ? | ✓ | **ORANGE** | Paiements et rapprochement non testés contre système financier réel. |
| `exports` / documents et éditions | ✓ | ✓ | ✓ | ✓ | ? | **ORANGE** | Contenu des fichiers/export PII non relu intégralement. |
| `statistiques` / rapports | ✓ | ✓ | ✓ | ? | ? | **ORANGE** | Chiffres croisés avec production non vérifiés. |
| `ressources_humaines` / personnels | ✓ | ✓ | ✓ | ? | ? | **ORANGE** | Habilitations et cycle de vie non testés sur rôles réels. |
| `patrimoine` / sites et salles | ✓ | ✓ | ✓ | ? | ? | **ORANGE** | Cohérence des sites géolocalisés avec les salles QR à contrôler. |
| `parametres` / configuration | ✓ | ✓ | ✓ | ? | ✓ | **ORANGE** | Paramètres d'environnement effectifs sur VPS inconnus. |
| `stages` | ✓ | ✓ | ✓ | ? | ? | **ORANGE** | Flux stage→jury/notes non vérifié sur données réelles. |
| `qr_badge_mobile` / Flutter | — | ✓ | client | ? | client | **NON VÉRIFIÉ** | Aucune compilation ni test sur appareil exécutés ici. |
| Archives, notifications, imports/exports transversaux | ✓ | ✓ | ✓ | ? | ? | **ORANGE** | Tests automatiques globaux ≠ revue complète d'archivage, de données personnelles et d'intégrité. |

**Architecture :** Django/DRF, app `backend/config/urls.py` + sous-routeurs, JWT/session, middleware CSRF/CORS configurables, rôles legacy et CURP, PostgreSQL par défaut (SQLite seulement opt-in sandbox), cache Redis ou fichier, uploads protégés par vues authentifiées selon `settings.py`, frontend React/Vite sous `frontend/src/menu/` et `pages/`, Flutter à part. Journaux métier `ReferentielJournal`, `AuditLog`, campagnes. Des commandes planifiées existent (auto-clôture, heartbeat), mais l'ordonnanceur et leur exécution VPS ne sont pas attestés. La génération de campagne repose sur des threads locaux et suivi d'exécution par PID/hôte : reprise multi-worker non équivalente à une file de tâches durable.

## C. Sécurité et intégration — constats prioritaires

1. **SEC-01 — P0 :** `/login` public de production affiche les identifiants de comptes démo administratifs. Le code local `frontend/src/pages/Login.jsx` contenait également le bloc. **Correction locale testée : retirer le bloc**, sans changer les comptes. L'exposition passée persiste : faire tourner les mots de passe et vérifier MFA/permissions/logs dans une procédure de production autorisée séparée. **Aucune tentative de connexion** n'a été faite pendant l'audit.
2. **QR-01 à QR-08 — P1/P2 :** anciens QR refusés dans le code local (déploiement non vérifié), absence de contrainte DB anti-concurrence, jeton complet dans les **anciens** journaux d'audit (nouvelles écritures corrigées localement), géofence facultative, rattachement ECUE manquant pour cohorte maquette. Détails et niveau de preuve dans [AUDIT_PRESENCES_QR_2026.md](AUDIT_PRESENCES_QR_2026.md). Un QR n'est pas preuve de présence physique.
3. **EDT-01 — P0 métier :** génération annuelle incomplète avec couverture très faible ; description et causes dans [AUDIT_GET_INJS_2026.md](AUDIT_GET_INJS_2026.md). Ne pas confondre « terminé avec anomalies », placements calculés, séances persistées et emplois publiés.
4. **REF-01 — P1 corrigée localement :** DELETE de trois référentiels dont les tests et le processus interdisent la suppression répondait 204 pour une valeur isolée. Un garde par modèle bloque désormais type d’évaluation, année et salle (ainsi que la suppression en lot via le hub), sans retirer le DELETE conditionnel des autres référentiels. **77 tests ciblés OK** ; aucune donnée existante touchée.
5. **INT-01 — P1 :** chaîne admission → inscription administrative validée → inscription pédagogique **explicite** (`INJS_AUTO_INSCRIPTION_PEDAGOGIQUE=False`) → groupe → besoins/EDT publié → séance/QR → `Pointage` → statistiques/notes. Une étape non exécutée peut casser la chaîne ; cohorte importée sans affectation peut perdre son ECUE dans le pointage QR (`ecue_de_seance`). Tests d'intégration réels bout en bout recommandés.
6. **API-01 — P1 corrigée localement :** nom de serializer dynamique collisionnait avec sérialiseurs historiques `RefModuleOfficiel` et `RefVolumeHoraireFormation` et supprimait 12 champs du **schéma** OpenAPI (pas nécessairement des JSON réellement servis). Le préfixe `Gestion` unique résout le snapshot ; 20 tests ciblés réussis. Pas de régénération opportuniste du snapshot.
7. **PERF-01 — P2 :** `frontend` a un chunk principal ~1,66 Mo avant gzip ; coût de génération annuel et mémoire à 5 000 étudiants non démontrés ; index d'occupations et cache de disponibilité déjà présents, ne pas les réimplémenter.

### Tableau des anomalies

| ID | Module | Anomalie | Gravité | Impact | Correction | Statut |
|---|---|---|---|---|---|---|
| SEC-01 | Authentification | Identifiants démo publiés sur le login public | P0 | Accès possibles aux comptes si identifiants valides | Affichage retiré localement ; rotation et audit des accès à faire séparément | Partiel, production non modifiée |
| EDT-01 | GET INJS | Année non répartie en occurrences hebdomadaires ; 90/39 146 calculées par campagne | P0 métier | EDT annuel non démontrable | Refonte temporelle testée, sans génération globale prématurée | Ouvert |
| QR-01 | Présences | Ancien QR redirigé vers jeton neuf | P1 | Révocation inefficace | LMD et voies legacy corrigés/testés dans le code ; vérifier copies offline et production séparément | Corrigé localement, production inconnue |
| QR-02 | Présences | Pas d'unicité DB sur pointage d'entrée LMD | P1 | Risque de double scan concurrent | Verrou sur personne ajouté ; tester simultané sous PostgreSQL et auditer avant contrainte | Atténué localement, concurrence non prouvée |
| QR-03 | Présences | Géofence permissive sans site localisé | P1 | Présence physique non prouvée | FK site et politique institutionnelle | Ouvert |
| QR-04 | Présences | Jeton en clair dans anciens logs | P1 | Secret réutilisable | Nouvelles écritures corrigées, historique à traiter sous procédure | Partiel |
| QR-05 | Présences/EDT | Cohorte importée : pointage sans ECUE via affectation pédagogique absente | P1 | Analyses par ECUE incomplètes | FK explicite et test bout en bout | Ouvert |
| QR-08 | Présences | GET du jeton QR sans garde objet explicite | P1 | Divulgation possible si permission globale plus large | GET aligné sur la garde objet POST, test de refus ajouté | Corrigé localement |
| REF-01 | Référentiels | Contrat 405 contredit DELETE 204 sur trois ressources | P1 | Suppression isolée non attendue | Garde par modèle sur DELETE et lot ; 77 tests ciblés OK | Corrigé localement |
| API-01 | Référentiels | Collision noms serializers OpenAPI, 12 clés de schéma supprimées | P1 | Contrat clients incorrect | Noms uniques pour serializers de gestion | Corrigé localement, 20 tests OK |
| PERF-01 | Frontend/EDT | Chunk principal >500 kB ; charge annuelle non mesurée | P2 | Latence et risque saturation | Profilage ciblé | Ouvert |

### Tableau des améliorations

| Priorité | Module | Amélioration | Valeur ajoutée | Complexité |
|---|---|---|---|---|
| P0 | Authentification | Rotation des accès démo compromis et MFA/contrôle des journaux | Réduit le risque d'accès indu | Moyenne, procédure de production |
| P0 | GET INJS | Calendrier d'occurrences et comptage des séances persistées | EDT annuel vérifiable | Élevée |
| P1 | Présences QR | Unicité DB + révocation des QR remplacés | Anti-fraude et résistance aux courses | Moyenne/élevée |
| P1 | Intégration | Traçabilité ECUE de la maquette jusqu'au pointage | Statistiques/notes cohérentes | Moyenne |
| P1 | Référentiels | Confirmer la politique par type et tester toutes les routes de suppression | Évite destruction imprévue | Faible/moyenne |
| P2 | Frontend | Découpage des bundles et parcours par rôle automatisés | Vitesse et maintenabilité | Moyenne |

## D. Modifications locales de cette mission

| Fichiers | Correction | Vérification |
|---|---|---|
| `frontend/src/pages/Login.jsx`, `Login.test.jsx` | Retire l'affichage de comptes/mots de passe de démonstration du formulaire de connexion, **sans toucher aux comptes** ; test de non-affichage. | 10/10 tests Login et build OK. Production toujours inchangée. |
| `backend/referentiels/serializers.py`, `views.py`, `referentiels/tests/test_gestion_annees.py`, `test_gestion_lieux.py` | Sérialiseurs dynamiques renommés pour lever collision OpenAPI ; DELETE et lot bloqués pour trois référentiels à cycle protégé. | 77/77 tests référentiels/contrat ciblés, `check` OK. |
| `backend/presences/seances_edt_services.py`, `views.py`, `test_seances_edt.py`, `test_seances_edt_mobile.py` | Nouvelles générations sans secret journalisé ; ancien QR LMD refusé ; verrou de personne sur scan. | 214 tests présences et 3 137 backend OK ; concurrence PostgreSQL non testée, historique inchangé. |
| `docs/audits/AUDIT_*.md` | Présent audit et suites. | Pas d'effet exécutable. |

Aucune migration créée, aucun compte/donnée/sauvegarde de production modifié. Suites frontend (2 246 tests) et backend (3 137 tests, 9 sautés) réussies **après** les corrections locales, sous leurs configurations de test. Ce résultat ne valide ni la production ni la concurrence PostgreSQL ni l’EDT annuel. La production peut encore afficher les identifiants jusqu'à un déploiement autorisé, et il faudra surtout les révoquer.

### Seconde passe sur la branche courante (sans production)

- **EDT :** le validateur C1/C2/C3 compare les semaines de début **et** de fin des récurrences, y compris les lignes persistées ; trois tests vérifient les périodes `[1,4]`/`[2,3]`, les périodes disjointes et l'adaptateur des séances persistées (3/3 OK). Le solveur annuel, la comptabilité des occurrences et la couverture horaire persistée restent **non résolus** ; aucune campagne annuelle représentative n'a été relancée.
- **QR :** refus des anciens jetons legacy dans les scans public/sécurisé, le heartbeat, l'endpoint offline-data et la consultation d'état ; GET du secret EDT protégé par la garde objet du POST. Tests de régression ancien refusé/nouveau accepté. Les caches clients déjà hors ligne restent hors du contrôle de la révocation serveur. Les courses de deux premières entrées sur PostgreSQL et l'unicité des pointages restent non prouvées ; géofence, ECUE et anciens journaux toujours à traiter.
- **Résultats après corrections :** une première suite ciblée (693 tests) a relevé 2 erreurs sur l'adaptateur de séance persistée ; corrigées, la seconde suite ciblée passe **693/693**. Django `check` OK ; aucune migration détectée. Suite backend complète **3 143 tests OK, 9 ignorés** (avant l'ajout du troisième test d'adaptateur, relancé séparément : 3/3 OK) ; frontend inchangé **2 246 tests OK**, lint 0 erreur/0 avertissement et build OK (avertissement de bundle ~1,66 Mo). Ces tests ne valident ni la production ni un EDT annuel complet.

## E. Plan d'action priorisé

| Horizon | Action et critère de sortie |
|---|---|
| **Immédiat, avant démonstration institutionnelle** | Rotation/révocation des identifiants démo exposés, revue des comptes/MFA et des accès, dans une intervention de production autorisée (pas cet audit). Confirmer la règle de non-suppression appliquée localement aux années, salles et types d’évaluation ; vérifier les autres routes de suppression et les imports. Ne pas présenter l'EDT annuel comme complet. Vérifier séparément la route publique réellement déployée et préparer sauvegarde/retour arrière. |
| **Court terme, jours suivants** | Tests de planification multi-semaines et d'occurrences persistées, contrôle anti-doublon QR concurrent sur PostgreSQL, révocation réelle des QR régénérés, traitement contrôlé des anciens journaux contenant un jeton, test étudiant importé → présence ECUE ; revoir les paramètres effectifs de prod sans les publier. Suite de tests complète après arbitrages. |
| **Moyen terme** | Qualification de bout en bout admission→diplôme, scénarios utilisateurs réels par rôle, tests appareils Flutter, observabilité du scheduler et tâches planifiées, mesure de charge à 5 000 étudiants, collecte de preuves d'exports et d'archivage, analyse de conservation PII et refonte du calendrier EDT validée métier. |

**Limites de méthode :** audit statique + tests isolés + trois GET publics ; aucune certification de tous les CRUD/endpoints, aucune authentification sur le VPS, aucun test d'attaque, de charge réelle ou de panne réseau. Une matrice exhaustive du code **ne** certifie **pas** 100 % des parcours utilisateurs.

## F. Clôture de la troisième passe — preuves nouvelles et limites (15 novembre 2026)

**Environnement :** uniquement `/home/user/backend-injs2026`, pas le disque macOS `/Users/jckouassi/...` ; aucun accès en écriture à la production. Branche conservée. Aucun serveur PostgreSQL de test ni binaires `postgres`/`initdb`/`pg_ctl` trouvés dans ce sandbox ; le réglage `USE_SQLITE` est actif ici. Deux tests `TransactionTestCase` PostgreSQL ont été préparés, mais sont **ignorés sur SQLite** : **0 preuve de concurrence PostgreSQL**. Ne pas utiliser un serveur de production pour les exécuter.

**Nouvelle preuve EDT (test isolé reproductible) :** `manage.py test edts.tests.test_generation_annee.GenerationAnneeTests.test_diagnostic_couverture_reelle_sur_quatre_semaines` : 20 inscrits synthétiques, 1 formation, 1 groupe, 1 ECUE, S1, 4 semaines ; **6 h théoriques**, 3 séances attendues/3 déclarées placées, 2 lignes récurrentes persistées sur 4 semaines chacune → **8 occurrences / 16 h réellement programmées** (écart **+10 h**, volume programmé / prévu = **266,7 %**, et non une couverture conforme malgré « COMPLETE »). Mesure moteur : ~0,02 s sur cette petite fixture (hors installation DB), non extrapolable à l'année complète. Aucune preuve multi-école/multi-semestre ; ce contre-exemple suffit à **réfuter** une garantie de couverture annuelle. L'incohérence n'est pas corrigée : toute modification temporelle exige une conception et des tests métier supplémentaires.

**Nouvelles corrections sûres :** résolution du site géofence via la FK de salle explicite avant son libellé ambigu (test de refus d'un scan au mauvais site) ; secrets `extra.token`, `token_qr`, `qr_token` masqués dans l'API des journaux (modes paginé et historique) sans modifier les anciens enregistrements. Les salles sans FK et homonymes restent ambiguës ; la politique d'absence de site géolocalisé reste permissive. Aucun rapprochement ECUE conjectural ni traitement destructif des journaux.

**Tests fraîchement exécutés :** Django `check` OK ; `makemigrations --check --dry-run` : aucune migration requise ; suite backend **3 149 tests recensés, 3 138 exécutés OK, 11 ignorés** (dont les 2 PostgreSQL) ; frontend **143 fichiers / 2 246 tests OK**, lint 0 erreur/0 avertissement, build OK avec avertissement chunk 1,66 Mo. Test diagnostic annuel isolé 1/1 OK ; tests ciblés correctifs 5/5 OK. TypeScript non configuré (`frontend/tsconfig.json` absent). Tests PostgreSQL **non exécutés** ; aucune validation du mode réseau interrompu sur appareil.

### Verdict requis (preuves locales, non certification de production)

| Domaine | Verdict | Preuves | Risques résiduels |
|---|---|---|---|
| Backend | ORANGE | `check`, migrations ; 3 138 tests exécutés OK sur 3 149 recensés | 11 ignorés, concurrence et parcours réels non couverts |
| Frontend | ORANGE | 2 246 tests, lint et build OK | Chunk lourd, rôles et appareils réels non testés |
| Référentiels | ORANGE | Contrat OpenAPI et DELETE protégés testés | Catalogue réel et autres suppressions non revérifiés |
| Admissions | ORANGE | Tests locaux de la suite globale | Chaîne complète jusqu'à scolarité non prouvée |
| Scolarité | ORANGE | Modèles et tests isolés présents | Synchronisation des cohortes/enseignants à vérifier |
| Maquettes | ORANGE | Besoins ECUE synthétiques et tests existants | Volumes semestriels et cohérence annuelle non prouvés |
| GET INJS | ROUGE | Contre-exemple 6 h prévues / 16 h programmées | Le solveur ne distribue pas les occurrences réelles |
| EDT annuel | ROUGE | 8 occurrences persistées contre 3 attendues, « COMPLETE » erroné ; campagnes antérieures 90/39 146 | Publication interdite avant reprise temporelle et validation |
| Présences QR | ROUGE | Révocation séquentielle testée, PG : 2 tests ignorés | Doubles scans PostgreSQL/non-unicité non démontrés ; second scan peut être une sortie |
| Géofence | ORANGE | FK salle prioritaire et test mauvais site refusé | Site absent/ambigu, GPS falsifiable, données de localisation |
| Rattachement ECUE | ROUGE | `ecue_de_seance` dépend de `affectation_pedagogique` absente pour les cohortes importées | Pointages sans ECUE ; FK explicite à concevoir/tester |
| Sécurité | ROUGE | Affichage démo retiré localement, historique QR masqué à l'API | Identifiants déjà exposés ; rotation/MFA hors mission ; secrets toujours en base |
| Intégration globale | ROUGE | Suites locales OK mais test annuel contradictoire | Aucune preuve bout en bout ni production validée |

**Décisions :** GET INJS annuel **non validé** ; Présences QR **non validées pour usage institutionnel** sans preuve PostgreSQL et intégrité des pointages ; INJS-LMD 2026 **non prêt pour déploiement institutionnel**. Démonstration **encadrée des parcours ciblés** possible sur une instance de test sans présenter d'EDT annuel complet ni la présence comme infalsifiable. Fiables en isolation : contrat API référentiels, révocation serveur QR séquentielle, tests de formulaires et écrans. Avant déploiement : calendrier d'occurrences/volumes avec preuve persistée, tests PostgreSQL réels et politique anti-double-tap/contrainte, rotation des accès exposés, rattachement ECUE et règle géofence validée métier ; les optimisations de bundle et fonctionnalités de confort peuvent attendre. Aucun déploiement autorisé ni exécuté.

## G. Quatrième passe — corrections et résultats (15 novembre 2026)

- **EDT annuel :** sur plusieurs semaines, contrôle des occurrences/heures récurrentes réelles avant écriture ; refuse les plans non conformes (`REPARTITION_ANNUELLE_NON_CONFORME`), n'annonce plus `COMPLETE` sur le contre-exemple et préserve les brouillons existants. Il **ne produit toujours pas** d'EDT annuel complet. Sur une seule semaine, contrat historique conservé, qui ne valide pas une année.
- **ECUE :** FK nullable `edts.AffectationCreneau.ecue` ; propagation du besoin de maquette vers la séance puis le pointage QR et la supervision. Migration `edts.0012` appliquée seulement aux **bases de test** ; aucune donnée historique réécrite. Test cohorte importée → séance et test mobile séance → pointage passants. Les anciennes séances sans rattachement restent incomplètes.
- **Résultats nouveaux après code :** Django `check` OK et `makemigrations --check --dry-run` sans modification supplémentaire ; suite complète backend **3 150 recensés, 3 139 exécutés OK, 11 ignorés** (dont 2 PostgreSQL), suite frontend **2 246 tests OK**, lint sans erreur/avertissement, build OK (avertissement bundle). Deux tests supplémentaires de non-écrasement et de scan ECUE ont été exécutés séparément **après** cette suite : 2/2 OK. PostgreSQL véritable absent ; concurrence **non validée**. Ni déploiement, ni écriture dans une base de production.

**Verdicts révisés :** GET INJS / EDT annuel **ROUGE** : faux succès bloqué mais couverture annuelle non obtenue ; Présences QR **ROUGE pour usage institutionnel** : ECUE nouvellement tracée pour les séances générées, mais concurrence PostgreSQL et géofence incomplètes ; INJS-LMD **ROUGE pour déploiement**, démonstration encadrée de parcours ciblés seulement. La matrice ci-dessus reste applicable sauf QR-05 désormais **partiellement corrigé localement** sur les nouveaux enregistrements ; historiques et preuve métier complète ouverts. Avant déploiement : solution temporelle mesurée sur semestre/année, tests PostgreSQL réels/anti-double-tap et audit des doublons, vérification des rattachements historiques, décision géofence, rotation des accès exposés. Optimisation bundle et évolutions de confort peuvent attendre.

**Accès CI PostgreSQL :** workflow `ci.yml` présent avec PostgreSQL 16 isolé, mais déclenchement manuel via `gh workflow run` refusé (HTTP 403 : `Resource not accessible by integration`) ; aucune exécution CI sur cette branche au moment de la vérification. Le push de code sur la branche a réussi ; aucun workflow de déploiement lancé. Les deux tests concurrentiels demeurent non exécutés : **ne pas lever le verdict ROUGE QR**. Déclenchement manuel CI par un utilisateur habilité requis, sans partager de secret dans le chat.

## H. Cinquième passe — périmètre mono-semestre planifié (15 novembre 2026)

L'orchestration annuelle réutilise maintenant le solveur existant **par semaine** sur un seul semestre explicite, au lieu d'interpréter un besoin entier comme une récurrence de toutes les semaines. Preuve de base de test : 6 h attendues → 6 h / 3 occurrences persistées sur 4 semaines ; deux groupes partageant une salle : 12 h → 12 h / 6 occurrences, aucun conflit de salle même semaine/créneau, chacun dans son brouillon. Un plan multi-semestre sans dates institutionnelles reste explicitement non persisté ; une année à 39 146 demandes **n'est pas qualifiée**. Voir le tableau détaillé dans le rapport GET INJS. La matrice ci-dessus reste ROUGE pour **GET INJS annuel / intégration globale**, malgré une avancée ORANGE sur le sous-périmètre mono-semestre.

Derniers contrôles : Django `check` et migrations OK ; suite backend **3 154 recensés, 3 143 exécutés OK, 11 ignorés** (les deux tests PostgreSQL sont toujours ignorés) ; suite frontend **2 246 tests OK**, lint propre, build OK. Après un ajustement limité aux métadonnées de résultat, tests ciblés annuels **26/26 OK**. La tentative de déclenchement du workflow CI PostgreSQL reste bloquée par HTTP 403 ; aucune preuve PostgreSQL nouvelle ni déploiement effectué. Risques toujours prioritaires : calendrier S1/S2 arrêté, couverture multi-école et volumes persistés à l'échelle réelle ; double scan PostgreSQL et règle anti-double-tap ; rotation des comptes de démonstration précédemment exposés.

## I. Qualification finale de cette itération

Le calendrier des semestres n'existe pas dans `scolarite.Semestre` (numéro et niveau, **sans dates**). Pour éviter une nouvelle fausse validation, le chemin d'occurrences unitaires n'est activé que pour la sélection manuelle **explicite d'un semestre et de ses semaines**. Un test prouve qu'une génération « automatique » sans cette sélection refuse l'année plutôt que d'étaler S1 arbitrairement ; un autre refuse S1+S2 sans bornes. Ces refus protègent les données, mais ne réalisent **pas** l'EDT annuel automatique demandé. Résultat final local : `check` OK, migrations sans dérive ; backend **3 155 recensés, 3 144 exécutés OK, 11 ignorés** ; frontend **2 246 tests OK**, lint propre et build OK. Concurrence PostgreSQL toujours non testée : tentative CI bloquée par droits Actions (HTTP 403). **GET INJS annuel : ROUGE ; QR institutionnel : ROUGE ; déploiement : non autorisé/non réalisé.**

## J. Sixième passe — concurrence QR sur PostgreSQL local isolé (16 novembre 2026)

Un serveur PostgreSQL 16.15 **local et jetable**, sans accès aux données de production, a permis d'exécuter `presences.test_concurrence_postgresql` avec des connexions indépendantes. Les deux tests initiaux passent : des étudiants différents créent chacun leur pointage ; deux scans rapides du **même** étudiant créent une seule ligne mais une **entrée puis une sortie**. Ce dernier résultat n'est **pas** une protection anti-double-tap : l'arbitrage métier de la temporisation reste ouvert.

Un nouveau test a reproduit une faille de temps de vérification/temps d'écriture : lorsque le QR est révoqué après sa première validation mais avant `badger_scan`, le scan retournait 201 et enregistrait le pointage. Les deux routes de scan transmettent maintenant le jeton au service ; dans la transaction du pointage, le jeton est verrouillé et revérifié (séance, validité, expiration). Les tests de révocation et d'expiration entre validation et écriture passent désormais, ainsi que les deux tests initiaux : **4/4 OK** sur PostgreSQL local. Le jeton retiré entre-temps est aussi refusé. Cela n'établit ni l'anti-double-tap ni la sécurité du terminal/GPS ou du QR en mode offline.

**Campagnes effectuées :** après le correctif initial, suite backend SQLite **3 157 recensés, 3 144 exécutés OK, 13 ignorés** (dont 4 scénarios PostgreSQL) ; Django `check` et `makemigrations --check --dry-run` OK. Un premier essai PostgreSQL `presences edts.tests` (708 tests, 41 erreurs) était **inexploitable** : cluster initialisé en `SQL_ASCII`, incompatible avec les textes JSON accentués. Après réinitialisation **UTF8** de `template1` et de la base de test Django, la même commande `STORAGES=STORAGE_DE_TEST USE_SQLITE=0 POSTGRES_HOST=127.0.0.1 POSTGRES_PORT=55439 POSTGRES_DB=injs_audit_temp POSTGRES_USER=postgres .venv/bin/python manage.py test presences edts.tests --noinput` (depuis `backend/`) a passé **708/708 tests en 198 s**, sans tests ignorés rapportés. Ces résultats sont locaux ; la CI GitHub n'a toujours aucune exécution vérifiée sur cette branche (déclenchement manuel refusé HTTP 403). Le serveur local de test sera arrêté après validation.

**Verdicts inchangés :** QR institutionnel ROUGE malgré une meilleure preuve transactionnelle ; EDT annuel multi-semestre ROUGE malgré 6 h/3 occurrences persistées sur un **semestre manuel** synthétique ; déploiement non autorisé et non réalisé. Calendrier S1/S2, règle anti-double-tap et exécution CI par une personne habilitée restent requis. Les chiffres des campagnes antérieures dans ce document sont historiques, non des résultats de cette passe.
