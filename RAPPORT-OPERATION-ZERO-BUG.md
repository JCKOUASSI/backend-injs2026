# Rapport — Opération « Zéro Bug » INJS-LMD

**Application** : plateforme LMD de l'Institut National de la Jeunesse et des Sports (INJS), Abidjan
**Dépôt** : `JCKOUASSI/backend-injs2026` — branche `arena/9ed4df1d-backend-injs2026`
**Commit de départ** : `003c600` — *docs(referentiels): livrables 9 à 14 et commande de contrôle de cohérence*
**Date de validation** : 1er novembre 2026
**Nature du document** : rapport de validation final, sections A à H, avec résultats de tests **réellement exécutés**.

---

## A. Contexte, périmètre et méthode

La mission porte sur une application Django + React servant le système LMD de l'INJS : référentiel
d'offre de formation, admissions, inscriptions administratives et pédagogiques, emplois du temps,
présences, évaluations et jurys, diplômes, finances étudiantes, stages, administration, RH,
patrimoine et statistiques.

Le travail s'est déroulé en lots successifs (LOT 01 → LOT 15), selon trois règles constantes :

1. **Corriger, pas seulement constater** — chaque anomalie relevée a été soit corrigée, soit
   documentée comme décision métier en attente, jamais laissée en zone grise.
2. **Ne jamais verdir artificiellement** — aucune règle métier n'a été assouplie pour faire passer un
   test, aucun test n'a été supprimé ou désactivé, aucune donnée métier n'a été inventée.
3. **Preuve d'exécution** — chaque chiffre de ce rapport provient d'une commande réellement lancée
   dans cet environnement ; les commandes sont reprises en section G pour être rejouées.

### Environnement d'exécution

| Élément | Valeur constatée |
|---|---|
| Python / Django | 3.11 / Django 5.1.4 (`.venv` du dépôt) |
| Node / Vite | Node 22.22.3 / Vite 7.3.2 |
| Base de développement | SQLite (`backend/db.sqlite3`) |
| Base de recette | PostgreSQL 16 (instance locale `pgserver`, socket `/tmp/pgdata_qr`) |
| API de démonstration | `arena/lancer-api.sh` → `0.0.0.0:8000` (profil `arena.settings_sandbox`) |
| Site de démonstration | `arena/lancer-front.sh` → `0.0.0.0:3000` (proxy `/api` → 8000) |

---

## B. État initial constaté (LOT 01)

### B.1 Dépôt et hygiène

| Contrôle | Commande | Résultat initial |
|---|---|---|
| Configuration Django | `manage.py check` | OK (après création de `backend/.env`) |
| Dérive de migrations | `makemigrations --check --dry-run` | Aucun changement détecté |
| Hygiène du dépôt | `manage.py check_repo_hygiene` | CONFORME |
| Lint frontend | `eslint src --ext js,jsx` | 0 erreur |
| Build frontend | `npm run build` | OK |

### B.2 Anomalies structurantes relevées

1. **Runner de tests cassé en parallèle** : `manage.py test --parallel 4` échouait sur
   `Missing staticfiles manifest entry` — l'environnement de test héritait de la configuration
   `STORAGES` de production.
2. **Faille d'accès aux données financières** : les vues du module « Finances étudiantes » ne
   portaient que `IsAuthenticated`. Un compte étudiant (`AUDITEUR`) lisait, par appel direct de
   l'API, l'intégralité des paiements, échéanciers et quittances de l'établissement — alors que
   l'interface lui masque le module. Le fichier `finances_etudiantes/permissions.py` existait mais
   **n'était branché nulle part**.
3. **Rôle corrompu** : `finances_etudiantes/permissions.py` contenait la chaîne `CHEF_SE   TARIAT`.
4. **Sigle transverse erroné** : cinq modules d'habilitation testaient le rôle `DFRC`, qui n'existe
   plus dans le modèle de rôles canoniques — la permission était donc silencieusement inopérante.
5. **Identité institutionnelle** : des exports (liste de participants, fiche de paie formateur,
   point journalier) imprimaient encore l'en-tête et l'adresse du CPFAE, établissement auquel
   l'application ne se destine plus.
6. **Commande de fumée inutilisable en pré-production** : `smoke_test_injs` plantait dès l'étape 1
   sur `UNIQUE constraint failed: scolarite_anneeacademique.libelle` sur toute base déjà initialisée.
7. **Aucune maquette officielle ne pouvait être validée** : la règle de cohérence exigeait que la
   somme des crédits ECTS des ECUE égale les crédits de l'UE, alors que le référentiel officiel
   **ne publie que des crédits par UE**. Toute maquette issue de la source institutionnelle était
   donc rejetée : `« ECUE … : crédits ECTS non renseignés »`, `« UE … : la somme des crédits ECUE (0)
   ne correspond pas aux crédits de l'UE (6) »`.

---

## C. Défauts corrigés et preuves de correction

| # | Défaut | Fichier(s) | Correction | Test de non-régression |
|---|---|---|---|---|
| C1 | Manifeste staticfiles absent en mode test | `config/settings.py` | `STORAGES` de test explicite quand `_RUNNING_TESTS` | Suites complètes exécutées en `--parallel 4` |
| C2 | Données financières accessibles à tout compte authentifié | `finances_etudiantes/permissions.py`, `api.py` | Trois niveaux branchés : lecture (`IsFinancesLectureOuGestion`), écriture, validation (confirmation, remboursement, rapprochement) | `finances_etudiantes/tests/test_permissions_et_garanties.py` |
| C3 | Rôle corrompu `CHEF_SE   TARIAT` | `finances_etudiantes/permissions.py` | Rôle canonique rétabli | idem C2 |
| C4 | Rôle `DFRC` inexistant dans cinq modules | `administrations`, `graduation`, `patrimoine`, `ressources_humaines`, `stages` | Remplacement par `CHEF_INJS_ADMIN`/`INJS_ADMIN` (ensemble canonique) | `core/tests/test_permissions_roles_canoniques.py` |
| C5 | En-têtes et pieds de page CPFAE | `core/institution.py` (nouveau), `exports/`, `statistiques/` | Source unique `lignes_entete()` / `pied_de_page()` ; adresse jamais inventée | `core/tests/test_identite_documents.py` (PDF et Excel réellement produits et inspectés) |
| C6 | `smoke_test_injs` non idempotent | `scolarite/management/commands/smoke_test_injs.py` | `get_or_create` sur les 12 ressources du parcours | Exécution réelle : 23/23 étapes |
| C7 | Maquettes officielles invalides (crédits ECUE non publiés) | `scolarite/models.py` (`Maquette.verifier_coherence`) | Les crédits ECUE deviennent **facultatifs** ; dès qu'ils sont déclarés, la répartition doit être complète et égale aux crédits de l'UE | `scolarite/tests/test_maquettes_workflow.py` (3 tests) + parcours HTTP réel |
| C8 | Signature « L'équipe DFRC — INJS » dans les e-mails | `authentication/emails.py` | Signature et bandeau en identité INJS | `core/tests/test_identite_emails.py` |
| C9 | Codes bruts affichés au guichet (`ELEPHANT_MONEY`, `CARTE_BANCAIRE`, `DOSSIER`) | `finances_etudiantes/api.py`, `frontend/src/pages/scolarite/FinancesEtudiantes.jsx` | L'API expose `mode_libelle` / `nature_libelle` / `statut_libelle` ; l'écran affiche les libellés, les listes déroulantes aussi | Backend : `test_permissions_et_garanties.py` ; frontend : `FinancesEtudiantes.test.jsx` |
| C10 | Fenêtres `alert()` bloquantes sur l'écran Statistiques | `frontend/src/pages/Statistiques.jsx`, `Statistiques.test.jsx` | Remplacement par le système de notifications de l'application (`useToast`) | `Statistiques.test.jsx` (126 tests, assertions adaptées au comportement corrigé) |
| C11 | `INJS_ADRESSE_OFFICIELLE` / `INJS_NOM_OFFICIEL` documentées mais jamais lues | `config/settings.py`, `core/institution.py`, `.env.example` | Réglages réellement exposés ; un réglage vide n'efface pas le nom officiel | `core/tests/test_identite_documents.py` (test en sous-processus avec variables posées) |
| C12 | `RuntimeWarning` datetime naïf sur les comptes d'habilitation | `habilitations/tests/test_cycle_vie_u5.py` | Fixtures en datetime conscient du fuseau | `habilitations.tests.test_cycle_vie_u5` : 0 avertissement, 32 tests OK |
| C13 | Nom d'utilisateur portant le sigle historique | `backend/seed_data.py` | Compte de démonstration renommé en identité INJS | `core/tests/test_identite_documents.py` (libellés de rôles sans sigle hérité) |
| C14 | Scripts jetables versionnés | `backend/smoke_audit.py`, `backend/smoke_audit2.py` | Supprimés (non versionnés, aucune référence) | `check_repo_hygiene` : CONFORME |

---

## D. Référentiel métier LMD vérifié

| Exigence | Vérification | État |
|---|---|---|
| 8 filières | `controler_referentiel_injs` sur la base de démonstration | Conforme pour F01–F04 ; F05–F08 (Andragogie, Loisir, Entrepreneuriat, Gérontologie) **sans maquette** dans la source |
| Licence S1–S6 / Master S7–S10 | `init_referentiels_lmd --annee 2026-2027` | 5 niveaux, 10 semestres créés |
| 30 ECTS / semestre, 60 ECTS / niveau | `completude` exposée par la maquette ACTIVE | 2 semestres, 30 crédits documentés (S8 absent de la source pour M1 — signalé, non comblé) |
| Chaîne Formation → Parcours → Promotion → Groupe → Maquette → UE → ECUE | `smoke_test_injs` (23 étapes) et E2E HTTP | Conforme |
| Inscriptions administratives ≠ pédagogiques | Modèle et transitions verrouillés | Conforme |
| Délibérations et jurys traçables | Étape `SMOKE-17-JURY` : décision « ADMIS », session VERROUILLE | Conforme |
| Diplôme + empreinte | Étape `SMOKE-18-DIPLOME` : `VALIDATED`, PDF + SHA-256 | Conforme |
| Admission ≠ inscription | Parcours `inscriptions/depuis-admission/` | Conforme |
| Aucun retour de SYGEP/CPFAE | Balayage code + tests dédiés (C5, C8, C13) | Conforme |

**Décision métier en attente (non tranchée par le développeur)** : 34 éléments du classeur officiel
hors LMD ne sont pas importés ; les filières F05 à F08 n'ont pas de maquette dans la source. Ces
points relèvent du commanditaire et ne peuvent pas être comblés sans inventer des données.

---

## E. Sécurité et habilitations

| Contrôle | Méthode | Résultat |
|---|---|---|
| Matrice d'accès sur 12 rôles × 10 points d'entrée sensibles | `core/tests/test_matrice_acces_api.py` | Conforme : aucune permission déclarée mais non branchée |
| Comptes mobiles (`AUDITEUR`, `FORMATEUR`) | Connexion web + appels API | Refus 403 sur le web (usage mobile), 403 sur toutes les routes financières |
| Compte `AUDITEUR` sur les données financières | Requête directe | 403 (auparavant 200) |
| Secrétariat et confirmation de paiement | E2E HTTP | 403 (acte réservé FINANCE/DIRECTION/Administration) |
| Journal d'audit | `/api/audit-logs/` | Accessible aux rôles habilités uniquement |
| Comptes témoins | `creer_comptes_temoins` | 14 comptes, 12 rôles, 2 secrétariats cloisonnés |

---

## F. Identité institutionnelle

- Source unique : `core/institution.py` (nom officiel, ministère de tutelle, ville, adresse
  optionnelle).
- Documents vérifiés **dans leur binaire** : exports Excel (openpyxl) et PDF (flux ASCII85 +
  Flate décodés) — mention INJS présente, aucun sigle historique.
- E-mails utilisateur : objet, corps texte et corps HTML contrôlés.
- Adresse postale : **vide par défaut**, aucune adresse inventée ; désormais réglable par
  `INJS_ADRESSE_OFFICIELLE` sans modification de code.

---

## G. Validation technique — résultats réels

> Toutes les commandes ci-dessous ont été exécutées dans cet environnement. Les chiffres reportés
> sont ceux affichés par les runners.

### G.1 Tableau de synthèse

| Suite | Total | Réussis | Échoués | Ignorés | Verdict |
|---|---|---|---|---|---|
| Backend Django — SQLite | 2 891 | 2 882 | 0 | 9 | ✅ VERT (`Ran 2891 tests in 512.058s`) |
| Backend Django — PostgreSQL 16 | 2 891 | 2 882 | 0 | 9 | ✅ VERT (`Ran 2891 tests in 498.753s`) |
| Frontend — Vitest | 2 075 | 2 075 | 0 | 0 | ✅ VERT |
| Parcours E2E HTTP (aperçu réel :3000 → API :8000) | 22 | 22 | 0 | 0 | ✅ VERT |
| Commande de fumée LMD (`smoke_test_injs`) | 23 | 23 | 0 | 0 | ✅ VERT |
| Docker / docker-compose | — | — | — | — | ⚠️ NON EXÉCUTÉ (binaire `docker` absent du bac à sable) |

### G.2 Commandes de rejeu

```bash
# Backend — SQLite
cd backend && .venv/bin/python manage.py test --parallel 4

# Backend — PostgreSQL
cd backend && DB_ENGINE=django.db.backends.postgresql DB_NAME=postgres DB_USER=postgres \
  DB_PASSWORD= DB_HOST=/tmp/pgdata_qr DB_PORT=5432 .venv/bin/python manage.py test --parallel 4

# Frontend
cd frontend && npx vitest run && npx eslint src --ext js,jsx && npm run build

# Parcours de fumée métier (base déjà initialisée : idempotent)
cd backend && PYTHONPATH=.. DJANGO_SETTINGS_MODULE=arena.settings_sandbox \
  .venv/bin/python manage.py smoke_test_injs

# Hygiène et migrations
cd backend && .venv/bin/python manage.py check_repo_hygiene
cd backend && .venv/bin/python manage.py makemigrations --check --dry-run
```

### G.3 Détail du parcours E2E HTTP (22 vérifications)

Connexion admin, connexion FINANCE, refus du compte AUDITEUR sur le web, cinq écrans de pilotage
(dashboard, statistiques, étudiants, journal d'audit, référentiel des formations), liste et
complétude des maquettes, **création → UE → ECUE sans crédits → validation** d'une maquette de
recette (le défaut C7 corrigé, prouvé de bout en bout), libellés de paiement, RBAC de la
confirmation de paiement (FINANCE accepté, secrétariat 403), exports Excel du point journalier et
des bilans.

---

## H. Décision finale

### H.1 Verdict

> ## ⚠️ ORANGE — application verte sur tous les axes exécutés, un axe non exécutable ici

Aucun test en échec, aucune divergence SQLite/PostgreSQL, aucun défaut fonctionnel connu restant.
La décision n'est pas « VERT » franc pour une seule raison, factuelle : **la suite Docker n'a pas pu
être exécutée** (binaire `docker` absent de l'environnement de validation). Déclarer « VERT » sans
cette exécution reviendrait à affirmer un résultat non constaté.

### H.2 Ce qui est prouvé

| Axe | Preuve |
|---|---|
| Non-régression backend | 2 891 tests, 0 échec, sur **deux moteurs** (SQLite et PostgreSQL 16) — `OK (skipped=9)` dans les deux cas |
| Non-régression frontend | 2 075 tests sur 115 fichiers, 0 échec ; ESLint 0 ; build de production réussi |
| Chaîne métier LMD complète | `smoke_test_injs` : 23/23 étapes, de la campagne d'admission à la quittance |
| Application réellement servie | 22/22 vérifications HTTP sur l'aperçu (site :3000 → API :8000) |
| Sécurité | Matrice 12 rôles × 10 points d'entrée + tests dédiés ; données financières fermées aux comptes mobiles |
| Identité institutionnelle | PDF et Excel réellement générés et inspectés ; e-mails capturés et inspectés |
| Hygiène du dépôt | `check_repo_hygiene` CONFORME ; `makemigrations --check` : aucun changement |

### H.3 Ce qui reste ouvert (et qui ne relève pas du développeur)

| # | Point | Nature | Action attendue |
|---|---|---|---|
| H1 | Suite Docker non exécutée | Limite d'environnement | Lancer `docker compose build && docker compose up` sur un hôte disposant de Docker, puis rejouer `manage.py check` et la suite de fumée dans le conteneur |
| H2 | Filières F05 (Andragogie), F06 (Loisir), F07 (Entrepreneuriat), F08 (Gérontologie) sans maquette | Lacune de la **source officielle** | Décision et fourniture des maquettes par le commanditaire — aucune donnée n'a été inventée |
| H3 | 34 éléments du classeur officiel hors LMD non importés | Décision métier | Arbitrage du commanditaire (tableau `TABLEAU-DECISION-34-ELEMENTS.md`) |
| H4 | Maquette M1 : S8 absent de la source (30 ECTS au lieu de 60) | Lacune de la source | Signalée par `controler_referentiel_injs`, jamais comblée artificiellement |
| H5 | `INJS_ADRESSE_OFFICIELLE` vide | Donnée institutionnelle manquante | Renseigner l'adresse officielle dans l'environnement : aucune adresse n'est inventée |
| H6 | Inscriptions pédagogiques non automatiques (`INJS_AUTO_INSCRIPTION_PEDAGOGIQUE=False`) | Règle métier en vigueur | Conservation volontaire : la génération reste une action explicite du service de scolarité |
| H7 | Connexion web refusée aux comptes `AUDITEUR` et `FORMATEUR` | Comportement voulu | Ces comptes sont réservés à l'application mobile |

### H.4 Conclusion

L'application est **fonctionnellement verte** : les défauts qui empêchaient son usage réel
(maquettes officielles invalides, commande de fumée inutilisable, fuite de données financières,
permissions déclarées mais non appliquées, identité CPFAE sur les documents) sont corrigés et
couverts par des tests de non-régression.

Le passage à **VERT franc** ne dépend plus que de l'exécution de la suite Docker sur un hôte
équipé — opération de vérification, non de correction.

---

## Annexes — fichiers ajoutés au cours de la mission

| Fichier | Rôle |
|---|---|
| `backend/core/institution.py` | Source unique de l'identité institutionnelle imprimée |
| `backend/core/tests/test_matrice_acces_api.py` | Vérifie que chaque permission déclarée est réellement appliquée |
| `backend/core/tests/test_identite_documents.py` | Contrôle l'identité INJS dans les PDF/Excel réellement produits |
| `backend/core/tests/test_identite_emails.py` | Contrôle l'identité INJS dans les e-mails réellement envoyés |
| `backend/core/tests/test_permissions_roles_canoniques.py` | Rôles canoniques dans les modules d'habilitation |
| `backend/core/tests/test_performances_listes.py` | Coût constant des listes (échéanciers, diplômes) |
| `backend/finances_etudiantes/tests/test_permissions_et_garanties.py` | Permissions, idempotence et garanties monétaires |
| `arena/preparer-apercu.sh` | Remise en état idempotente de l'aperçu (venv, npm, `.env`, base, démo) |
