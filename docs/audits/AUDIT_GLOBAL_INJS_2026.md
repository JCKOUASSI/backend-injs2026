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

**Légende :** B/F/API/T/P : backend, frontend, routes API, tests présents, permissions repérées (`✓` code présent, `—` non constaté dans cette passe, `?` non établi). **Statut** : VERT = fonctionnalité réellement vérifiée ; ORANGE = preuves partielles ; ROUGE = anomalie importante ; GRIS = non vérifié. La présence d'un test dans une app ne signifie pas validation de tous ses sous-parcours. Aucune ligne VERT n'est attribuée au seul inventaire du code.

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
| `presences` / QR, émargement, absences | ✓ | ✓ | ✓ | ✓ | ✓ | **ORANGE** | 214 tests OK ; ancien QR LMD refusé, legacy et concurrence PostgreSQL non résolus. |
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
| `qr_badge_mobile` / Flutter | — | ✓ | client | ? | client | **GRIS** | Aucune compilation ni test sur appareil exécutés ici. |
| Archives, notifications, imports/exports transversaux | ✓ | ✓ | ✓ | ? | ? | **ORANGE** | Tests automatiques globaux ≠ revue complète d'archivage, de données personnelles et d'intégrité. |

**Architecture :** Django/DRF, app `backend/config/urls.py` + sous-routeurs, JWT/session, middleware CSRF/CORS configurables, rôles legacy et CURP, PostgreSQL par défaut (SQLite seulement opt-in sandbox), cache Redis ou fichier, uploads protégés par vues authentifiées selon `settings.py`, frontend React/Vite sous `frontend/src/menu/` et `pages/`, Flutter à part. Journaux métier `ReferentielJournal`, `AuditLog`, campagnes. Des commandes planifiées existent (auto-clôture, heartbeat), mais l'ordonnanceur et leur exécution VPS ne sont pas attestés. La génération de campagne repose sur des threads locaux et suivi d'exécution par PID/hôte : reprise multi-worker non équivalente à une file de tâches durable.

## C. Sécurité et intégration — constats prioritaires

1. **SEC-01 — P0 :** `/login` public de production affiche les identifiants de comptes démo administratifs. Le code local `frontend/src/pages/Login.jsx` contenait également le bloc. **Correction locale testée : retirer le bloc**, sans changer les comptes. L'exposition passée persiste : faire tourner les mots de passe et vérifier MFA/permissions/logs dans une procédure de production autorisée séparée. **Aucune tentative de connexion** n'a été faite pendant l'audit.
2. **QR-01 à QR-08 — P1/P2 :** anciens QR legacy encore redirigés (LMD corrigé localement), absence de contrainte DB anti-concurrence, jeton complet dans les **anciens** journaux d'audit (nouvelles écritures corrigées localement), géofence facultative, rattachement ECUE manquant pour cohorte maquette. Détails et niveau de preuve dans [AUDIT_PRESENCES_QR_2026.md](AUDIT_PRESENCES_QR_2026.md). Un QR n'est pas preuve de présence physique.
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
| QR-01 | Présences | Ancien QR redirigé vers jeton neuf | P1 | Révocation legacy inefficace | LMD : ancien refusé et nouveau accepté (test) ; traiter legacy séparément | LMD corrigé localement, legacy ouvert |
| QR-02 | Présences | Pas d'unicité DB sur pointage d'entrée LMD | P1 | Risque de double scan concurrent | Verrou sur personne ajouté ; tester simultané sous PostgreSQL et auditer avant contrainte | Atténué localement, concurrence non prouvée |
| QR-03 | Présences | Géofence permissive sans site localisé | P1 | Présence physique non prouvée | FK site et politique institutionnelle | Ouvert |
| QR-04 | Présences | Jeton en clair dans anciens logs | P1 | Secret réutilisable | Nouvelles écritures corrigées, historique à traiter sous procédure | Partiel |
| QR-05 | Présences/EDT | Cohorte importée : pointage sans ECUE via affectation pédagogique absente | P1 | Analyses par ECUE incomplètes | FK explicite et test bout en bout | Ouvert |
| QR-08 | Présences | GET du jeton QR sans garde objet explicite | P1 à confirmer | Divulgation possible si permission globale plus large | Test de rôles puis aligner GET/POST | Non démontré |
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

## E. Plan d'action priorisé

| Horizon | Action et critère de sortie |
|---|---|
| **Immédiat, avant démonstration institutionnelle** | Rotation/révocation des identifiants démo exposés, revue des comptes/MFA et des accès, dans une intervention de production autorisée (pas cet audit). Confirmer la règle de non-suppression appliquée localement aux années, salles et types d’évaluation ; vérifier les autres routes de suppression et les imports. Ne pas présenter l'EDT annuel comme complet. Vérifier séparément la route publique réellement déployée et préparer sauvegarde/retour arrière. |
| **Court terme, jours suivants** | Tests de planification multi-semaines et d'occurrences persistées, contrôle anti-doublon QR concurrent sur PostgreSQL, révocation réelle des QR régénérés, traitement contrôlé des anciens journaux contenant un jeton, test étudiant importé → présence ECUE ; revoir les paramètres effectifs de prod sans les publier. Suite de tests complète après arbitrages. |
| **Moyen terme** | Qualification de bout en bout admission→diplôme, scénarios utilisateurs réels par rôle, tests appareils Flutter, observabilité du scheduler et tâches planifiées, mesure de charge à 5 000 étudiants, collecte de preuves d'exports et d'archivage, analyse de conservation PII et refonte du calendrier EDT validée métier. |

**Limites de méthode :** audit statique + tests isolés + trois GET publics ; aucune certification de tous les CRUD/endpoints, aucune authentification sur le VPS, aucun test d'attaque, de charge réelle ou de panne réseau. Une matrice exhaustive du code **ne** certifie **pas** 100 % des parcours utilisateurs.
