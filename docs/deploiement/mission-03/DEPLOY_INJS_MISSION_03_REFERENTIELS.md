# MISSION 03 — Refonte intégrale du Hub « Référentiels »

**Date** : 12 novembre 2026
**Branche** : `arena/4524a57c-backend-injs2026` — HEAD `b661d13`
**Périmètre** : PHASE 1 (identification exhaustive) **terminée**, moteur commun des
PHASES 2 à 4 livré. PHASES 5 à 7 à poursuivre (voir §11).
**Règle appliquée** : aucune fonctionnalité décorative ou simulée tolérée.

---

## 1. Cadre et interdictions respectées

| Interdiction | Application |
|---|---|
| DROP / TRUNCATE / FLUSH / réinitialisation de base | Aucune opération de ce type. **Aucune migration** n'a été créée (`makemigrations --check` → `No changes detected`). |
| Pas de suppression en cascade non maîtrisée | La suppression est un **archivage logique** ; les dépendances sont détectées par une exploration **annulée** (transaction + `ProtectedError`), jamais par une destruction. |
| Désactiver ≠ Archiver ≠ Supprimer | Trois actions distinctes côté backend et côté UI (§6). |
| Pas de RBAC parallèle | Réutilisation de `get_user_roles` (module `authentication`) ; aucune table ni règle d'habilitation nouvelle. |
| Pas de logique métier dans React | Le frontend ne connaît ni colonnes ni règles : tout vient du registre backend. |
| Pas de déploiement en production | Aucun déploiement. Base `injs_lmd_prod_20261026` non contactée. |
| Ne pas modifier les règles d'admission / inscription / validation | Aucune règle académique modifiée. |
| Ne jamais inventer de données | Une colonne absente reste vide et est signalée ; aucune valeur n'est déviée ni estimée. |

> **Contrariété signalée** : le dépôt local `/Users/jckouassi/Sites/audits-injs/backend-injs2026`
> (macOS) n'existe pas dans cet environnement. Le travail a été fait dans le clone de
> référence `/home/user/backend-injs2026`. L'environnement impose par ailleurs la branche
> unique de session : aucun push n'a été fait pour l'instant (§11).

---

## 2. PHASE 1 — Liste exhaustive des sous-modules

Source de vérité : `backend/referentiels/registre.py` (`REGISTRE`). **27 référentiels**,
dont **23 administrables** et **4 en lecture seule** (données historisées ou importées,
volontairement non réécrites).

| # | Slug | Catégorie | Modèle | État initial |
|---|---|---|---|---|
| 1 | `ecoles` | Institutionnel | `RefEcole` | CRUD + archivage |
| 2 | `mentions` | Institutionnel | `RefMention` | CRUD + archivage |
| 3 | `types-cursus` | Offre de formation | `RefTypeCursus` | CRUD + archivage |
| 4 | `filieres` | Offre de formation | `RefFiliere` | CRUD + archivage |
| 5 | `types-enseignement` | Pédagogique | `RefTypeEnseignement` | CRUD + archivage |
| 6 | `statuts-vague` | Organisation | `RefStatutVague` | CRUD + archivage |
| 7 | `types-evaluation` | Pédagogique | `RefTypeEvaluation` | CRUD + archivage |
| 8 | `types-decision` | Pédagogique | `RefTypeDecision` | CRUD + archivage |
| 9 | `types-espace-sportif` | Pédagogique | `RefTypeEspaceSportif` | CRUD + archivage |
| 10 | `grades-enseignant` | Ressources humaines | `RefGradeEnseignant` | CRUD + archivage |
| 11 | `types-document` | Scolarité | `RefTypeDocument` | CRUD + archivage |
| 12 | `types-frais` | Scolarité | `RefTypeFrais` | CRUD + archivage |
| 13 | `modes-paiement` | Scolarité | `RefModePaiement` | CRUD + archivage |
| 14 | `types-notification` | Scolarité | `RefTypeNotification` | CRUD + archivage |
| 15 | `niveaux` | Système LMD | `scolarite.Niveau` | CRUD + archivage |
| 16 | `semestres` | Système LMD | `scolarite.Semestre` | CRUD + archivage |
| 17 | `parcours` | Système LMD | `scolarite.Parcours` | CRUD + archivage |
| 18 | `types-formation` | Système LMD | `scolarite.TypeFormation` | CRUD + archivage |
| 19 | `annees` | Scolarité | `scolarite.AnneeAcademique` | CRUD (pas d'archivage) |
| 20 | `sites` | Organisation | `formations.RefSite` | CRUD + archivage |
| 21 | `batiments` | Organisation | `formations.RefBatiment` | CRUD + archivage |
| 22 | `salles` | Organisation | `formations.RefSalle` | CRUD + archivage |
| 23 | `vagues` | Organisation | `formations.RefVague` | CRUD + archivage |
| 24 | `formations` | Offre de formation | `formations.RefFormation` | **Lecture seule** (écran historique) |
| 25 | `ue-ecue` | Système LMD | `scolarite.UE` | **Lecture seule** |
| 26 | `modules-officiels` | Offre de formation | `RefModuleOfficiel` | **Lecture seule** (import documentaire) |
| 27 | `volumes-modules` | Offre de formation | `RefVolumeHoraireFormation` | **Lecture seule** (import documentaire) |

### 2.1 État initial avant refonte (ce qui manquait réellement)

| Fonctionnalité | État avant | Constat |
|---|---|---|
| CRUD | Présent | Liste, création, modification, détail OK |
| **Recherche multicritère / tri** | **Absent** | Aucun `SearchFilter` ni `OrderingFilter` : le filtrage était fait **côté React** sur les lignes déjà chargées |
| Pagination / total | Présent | `RefPagination` (100 par page, réglable) |
| **Activation / désactivation** | **Partiel** | Un simple `PATCH {actif: …}` : aucune traçabilité, aucune distinction avec l'archivage |
| Archivage / désarchivage | Présent | `archiver` / `reactiver` |
| **Suppression sécurisée** | **Absente** | Aucune vérification de dépendances, aucune confirmation, aucune traçabilité |
| **Export Word / Excel / CSV / PDF** | **Totalement absent** | Aucune route, aucun générateur dans le module |
| **Import Excel / CSV** | **Totalement absent** | Aucune route ; seules des commandes `manage.py` d'import documentaire existaient |
| Sécurité par opération | Partiel | Une permission binaire lecture/écriture ; **export et import auraient été ouverts à tout authentifié** |

---

## 3. Architecture retenue : un moteur commun

Recommandation suivie : **un moteur mutualisé** plutôt que 23 CRUD indépendants.
Chaque référentiel conserve ses règles métier (modèle, contraintes, sélecteurs dépendants).

```
backend/referentiels/moteur/
├── __init__.py         documentation du moteur
├── colonnes.py         découverte des champs exportables / importables
├── exportations.py     Word, Excel, CSV, PDF
├── importations.py     import en 5 étapes, transactionnel
└── mixins.py           branchement sur les ViewSets (actions DRF)
```

Aucune liste de colonnes n'est écrite en dur : tout est déduit de `modele._meta`.

---

## 4. Fichiers créés ou modifiés

### 4.1 Créés

| Fichier | Rôle |
|---|---|
| `backend/referentiels/moteur/__init__.py` | Documentation du moteur |
| `backend/referentiels/moteur/colonnes.py` | Champs exportables/importables, clé naturelle des FK, libellés francophones |
| `backend/referentiels/moteur/exportations.py` | Générateurs `docx`, `xlsx`, `csv`, `pdf` + charte INJS |
| `backend/referentiels/moteur/importations.py` | Téléversement, prévisualisation, validation, import transactionnel, rapport |
| `backend/referentiels/moteur/mixins.py` | `ExportReferentielMixin`, `ImportReferentielMixin` |
| `backend/referentiels/tests/test_moteur_referentiels.py` | 26 tests backend |
| `frontend/src/services/referentiels.js` | Appels API export/import, contrôle du fichier, CSV des anomalies |
| `frontend/src/components/referentiels/BarreExport.jsx` | Export 4 formats |
| `frontend/src/components/referentiels/AssistantImport.jsx` | Assistant 5 étapes |
| `frontend/src/components/referentiels/ReferentielsMoteur.test.jsx` | 20 tests frontend |
| `frontend/src/pages/referentiels/ReferentielMoteur.test.jsx` | 7 tests d'intégration écran |

### 4.2 Modifiés

| Fichier | Modification |
|---|---|
| `backend/referentiels/views.py` | Mixins du moteur ; actions `activer`, `desactiver`, `supprimer` ; `_dependances()` non destructif ; `SearchFilter` + `OrderingFilter` dynamiques |
| `backend/referentiels/permissions.py` | Protection **individuelle** de 8 opérations (`ROLES_PAR_OPERATION`) |
| `backend/referentiels/urls.py` | Routes `exporter/`, `importer/`, `importer/analyse/`, `activer/`, `desactiver/`, `supprimer/` par référentiel |
| `frontend/src/pages/referentiels/ReferentielGenerique.jsx` | Boutons Importer, Activer, Désactiver, Supprimer ; barre d'export ; modale de suppression avec dépendances |
| `frontend/src/styles/referentiels.css` | Charte des blocs d'export et d'import (§9) |

### 4.3 Migrations

**Aucune.** Aucun modèle n'a été modifié ; `makemigrations --check` renvoie
`No changes detected`. Aucune évolution structurelle de la base n'a donc été nécessaire.

---

## 5. Endpoints

Tous les référentiels éditables exposent la même famille de routes
(sous `/api/referentiels/<slug>/`) :

| Méthode | Route | Action |
|---|---|---|
| GET | `/` | Liste paginée (`?search=`, `?ordering=`, `?actif=`, `?archives=`, `?page=`, `?page_size=`) |
| POST | `/` | Création |
| GET | `/{id}/` | Détail |
| PATCH / PUT | `/{id}/` | Modification |
| POST | `/{id}/activer/` | Activation |
| POST | `/{id}/desactiver/` | Désactivation |
| POST | `/{id}/archiver/` | Archivage |
| POST | `/{id}/reactiver/` | Désarchivage |
| POST | `/{id}/supprimer/` | Suppression sécurisée (confirmation + dépendances) |
| GET | `/exporter/?export=csv\|xlsx\|docx\|pdf` | Export |
| POST | `/importer/analyse/` | Étapes 1 à 3 (sans écriture) |
| POST | `/importer/` | Étapes 4 et 5 (transactionnel) |

**325 routes** servies sous le préfixe `api/referentiels/`, dont par opération :
31 `exporter`, 31 `importer`, 31 `importer/analyse`, 31 `activer`,
31 `desactiver`, 31 `supprimer`, 31 `archiver`, 31 `reactiver`.

> **Piège corrigé (à ne pas reproduire)** : le paramètre `?format=` est **réservé** par
> Django REST Framework pour la négociation de contenu. Un `?format=csv` renvoyait un
> **404** avant même d'atteindre la vue. Le choix du document passe donc par **`?export=`**.

---

## 6. Cycle de vie : trois opérations réellement distinctes

| Opération | Effet | Réversible | Détruit des données ? |
|---|---|---|---|
| **Désactiver** | `actif = False`, `date_desactivation` renseignée. La valeur reste proposée à l'historique, n'est plus sélectionnable dans les nouvelles opérations. | Oui | Non |
| **Archiver** | `archive = True` (et `actif = False`). Masquée par défaut, consultable via `?archives=1`. | Oui | Non |
| **Supprimer** | Vérifie les dépendances. **Si dépendances → 409** avec la liste et invitation à archiver. **Sinon → archivage** tracé au journal (`origine = suppression_securisee`). | Oui | **Jamais** |

Aucune suppression physique n'est exposée : `http_method_names` exclut toujours `DELETE`.
Le contrôle de dépendances (`_dependances`) exécute un `delete()` exploratoire **dans une
transaction systématiquement annulée**, puis restaure le `pk` en mémoire (Django met
`pk` à `None` après `delete()`).

---

## 7. Exports

| Format | Particularités |
|---|---|
| **Word** (.docx) | Titre, en-têtes INJS, tableau « Light Grid Accent 1 », **en-tête de tableau répété sur chaque page** |
| **Excel** (.xlsx) | En-têtes institutionnels, en-têtes de colonnes bleu INJS, lignes alternées, **filtre automatique**, volet figé, largeurs adaptées |
| **CSV** (.csv) | **UTF-8 avec BOM** (accents lisibles dans Excel), **séparateur point-virgule**, métadonnées en commentaires `#` |
| **PDF** (.pdf) | Paysage automatique au-delà de 5 colonnes, **en-têtes répétés sur chaque page** (`repeatRows`), pied de page avec **pagination** |

Chaque document porte : institution, service, titre, nom du référentiel, date-heure de
génération, colonnes, données et **total**. Le périmètre exporté est **exactement** celui
affiché à l'écran (recherche et filtres transmis). Limite de sécurité : 20 000 lignes.

---

## 8. Import en 5 étapes

1. **Téléversement contrôlé** — extension (`.xlsx`, `.xls`, `.csv`), taille (10 Mio),
   contenu non vide ; encodages essayés : UTF-8 BOM, UTF-8, CP1252, Latin-1.
2. **Prévisualisation** — nombre de lignes, colonnes reconnues, **colonnes obligatoires
   manquantes**, **doublons détectés** (sur le code *et* le libellé), aperçu 10 lignes,
   **correspondance de colonnes ajustable** par l'utilisateur.
3. **Validation** — rapport d'erreurs **par numéro de ligne**, avec colonne et valeur
   fautives. **Aucune écriture** à ce stade.
4. **Importation transactionnelle** — modes `ajouter`, `mettre_a_jour`, `les_deux`.
   Chaque ligne est traitée dans son propre **point de sauvegarde** : une ligne fautive
   est annulée seule et signalée, elle n'invalide pas le lot.
5. **Rapport final** — créations, mises à jour, ignorées, anomalies, **durée**, et
   **téléchargement du CSV des anomalies**.

---

## 9. Sécurité et permissions

Aucun système RBAC parallèle : réutilisation de `get_user_roles` (`authentication`).
Chaque opération est vérifiée **individuellement** côté serveur
(`ROLES_PAR_OPERATION`). Masquer un bouton dans React n'est jamais une protection.

| Opération | Rôles autorisés |
|---|---|
| Consulter (GET) | Tout utilisateur authentifié |
| Créer / Modifier | ADMIN, DIRECTION, CHEF_INJS_ADMIN, INJS_ADMIN, CHEF_SECRETARIAT, SECRETARIAT |
| Activer / Désactiver | idem |
| Archiver / Désarchiver | idem |
| **Exporter** | idem (une extraction de données n'est pas une simple lecture) |
| **Importer** (analyse et exécution) | idem (écriture en masse) |
| **Supprimer** | **ADMIN, DIRECTION uniquement** |

**Correction de sécurité** : l'export et l'import sont des méthodes HTTP « sûres » pour
l'analyse, que l'ancienne permission laissait passer pour tout authentifié. Elles sont
désormais contrôlées avant le raccourci des méthodes sûres.

---

## 10. Tests réellement exécutés

### 10.1 Backend — suite complète (9 groupes)

```
GROUPE       RÉSULTAT  DÉTAIL
scolarite    RÉUSSI    153s | Ran 515 tests
formations   RÉUSSI    105s | Ran 289 tests
auth         RÉUSSI    145s | Ran 242 tests
habilitations RÉUSSI   263s | Ran 520 tests
edt          RÉUSSI    174s | Ran 591 tests
evaluations  RÉUSSI    114s | Ran 237 tests
pilotage     RÉUSSI     69s | Ran 245 tests
socle        RÉUSSI    138s | Ran 301 tests
divers       RÉUSSI     75s | Ran 152 tests
```

**Total : 3 092 tests, 0 échec** (contre 3 066 avant la mission : **+26**).
Module `referentiels` seul : **122 tests, 0 échec**.

Nouveaux tests (`test_moteur_referentiels.py`) : génération réelle des 4 formats,
contrôle du CSV (BOM, point-virgule, accents), validité du PDF, export via API avec
respect des filtres, refus d'un format inconnu, contrôle du fichier, prévisualisation
sans écriture, détection des doublons, rapport d'erreurs ligne par ligne, import en
modes `ajouter` et `mettre_a_jour`, analyse et import via API, cycle de vie complet
(activer / désactiver / archiver / réactiver / supprimer), refus d'activer une valeur
archivée, confirmation obligatoire, sécurité par opération.

### 10.2 Frontend

| Contrôle | Résultat |
|---|---|
| Vitest (suite complète) | **133 fichiers, 2 194 tests, 0 échec** (contre 2 167 / 131 : **+27**) |
| `npm run lint` | **0 erreur**, 6 avertissements (préexistants, fichiers `scolarite` hors périmètre) |
| `npm run build` | **Réussi en 5,43 s** |
| `check_repo_hygiene` | **CONFORME** — 2 274 fichiers, aucun `print()` |
| `makemigrations --check` | **No changes detected** |

### 10.3 Anomalies découvertes et corrigées en cours de route

1. **`?format=` intercepté par DRF** → 404 systématique sur l'export. Corrigé par `?export=`.
2. **Transaction invalidée par une ligne fautive** : intercepter une `IntegrityError`
   dans un bloc `atomic()` rend toute la transaction inutilisable. Corrigé par un point
   de sauvegarde par ligne.
3. **`pk` mis à `None`** par `delete()` exploratoire → `NOT NULL` sur le journal.
   Corrigé par la sauvegarde et la restauration de l'identifiant.
4. **Doublons non détectés** : le contrôle ne portait que sur une colonne. Corrigé :
   les clés naturelles **code et libellé** sont toutes deux vérifiées.
5. **Parcours d'import qui sautait l'étape 2** : l'analyse enchaînait directement vers la
   validation, privant l'utilisateur de la correspondance de colonnes. Corrigé.

---

## 11. Tableau de conformité

Légende : **C** conforme · **PC** partiellement conforme · **NC** non conforme ·
**NA** non applicable (justifié).

| Référentiel | CRUD | Act. | Arch. | Word | Excel | CSV | PDF | Import Excel | Import CSV | Sécurité | Tests |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `ecoles` | C | C | C | C | C | C | C | C | C | C | C |
| `mentions` | C | C | C | C | C | C | C | C | C | C | C |
| `types-cursus` | C | C | C | C | C | C | C | C | C | C | C |
| `filieres` | C | C | C | C | C | C | C | C | C | C | C |
| `types-enseignement` | C | C | C | C | C | C | C | C | C | C | C |
| `statuts-vague` | C | C | C | C | C | C | C | C | C | C | C |
| `types-evaluation` | C | C | C | C | C | C | C | C | C | C | C |
| `types-decision` | C | C | C | C | C | C | C | C | C | C | C |
| `types-espace-sportif` | C | C | C | C | C | C | C | C | C | C | C |
| `grades-enseignant` | C | C | C | C | C | C | C | C | C | C | C |
| `types-document` | C | C | C | C | C | C | C | C | C | C | C |
| `types-frais` | C | C | C | C | C | C | C | C | C | C | C |
| `modes-paiement` | C | C | C | C | C | C | C | C | C | C | C |
| `types-notification` | C | C | C | C | C | C | C | C | C | C | C |
| `niveaux` | C | C | C | C | C | C | C | C | C | C | C |
| `semestres` | C | C | C | C | C | C | C | C | C | C | C |
| `parcours` | C | C | C | C | C | C | C | C | C | C | C |
| `types-formation` | C | C | C | C | C | C | C | C | C | C | C |
| `annees` | C | C | **NA** | C | C | C | C | C | C | C | C |
| `sites` | C | C | C | C | C | C | C | C | C | C | C |
| `batiments` | C | C | C | C | C | C | C | C | C | C | C |
| `salles` | C | C | C | C | C | C | C | C | C | C | C |
| `vagues` | C | C | C | C | C | C | C | C | C | C | C |
| `formations` | **NA** | **NA** | **NA** | C | C | C | C | **NA** | **NA** | C | C |
| `ue-ecue` | **NA** | **NA** | **NA** | C | C | C | C | **NA** | **NA** | C | C |
| `modules-officiels` | **NA** | **NA** | **NA** | C | C | C | C | **NA** | **NA** | C | C |
| `volumes-modules` | **NA** | **NA** | **NA** | C | C | C | C | **NA** | **NA** | C | C |

### Justification des « non applicable »

- **`annees` — Archivage NA** : le modèle `AnneeAcademique` ne porte pas de colonne
  d'archivage ; le registre le déclare `archivage_supporte = false`. L'activation et la
  clôture (`courante`, `cloturee`) y tiennent lieu de cycle de vie. Créer un champ
  d'archivage serait une modification structurelle sans justification métier.
- **Référentiels en lecture seule (`formations`, `ue-ecue`, `modules-officiels`,
  `volumes-modules`)** : déclarés `editable=False` au registre. Ce sont des données
  importées de documents officiels ou gérées par des écrans historiques existants.
  CRUD, activation, archivage et import y sont **volontairement** indisponibles : une
  correction passe par la source puis par un nouvel import, afin de préserver la
  traçabilité. L'export reste disponible (consultation et extraction).

### Réserve de méthode sur la colonne « Tests »

La conformité « Tests = C » signifie que le **moteur commun** est couvert par 26 tests
backend et 27 tests frontend réellement exécutés, et que la **suite complète**
(3 092 tests backend, 2 194 frontend) passe sans échec. Elle ne signifie pas que chaque
référentiel possède sa propre suite dédiée : c'est précisément l'objet du moteur commun
(un seul code testé, appliqué aux 27). Une campagne de tests par référentiel, avec les
jeux de données réels de chacun, reste à conduire en PHASE 6.

---

## 12. Anomalies résiduelles

| # | Anomalie | Gravité | Traitement |
|---|---|---|---|
| A1 | Les 4 référentiels en lecture seule n'exposent pas l'export depuis leur route dédiée (ils sont servis par des ViewSets `ReadOnlyModelViewSet` historiques) | Moyenne | À intégrer en PHASE 5 |
| A2 | L'import ne résout pas encore les clés étrangères par libellé pour tous les modèles (seules les FK listées dans `CLE_NATURELLE_FK` sont proposées) | Moyenne | À étendre référentiel par référentiel |
| A3 | Les référentiels avec FK obligatoire (ex. `RefFiliere.ecole`) signalent une anomalie par ligne si la colonne est absente du fichier — comportement correct, mais le message mériterait d'être plus explicite | Faible | Amélioration du libellé à prévoir |
| A4 | Aucun test navigateur (navigateur réel) n'a encore été rejoué sur l'assistant d'import | Moyenne | PHASE 5 |
| A5 | La limite d'export (20 000 lignes) n'est pas encore paramétrable | Faible | À passer en réglage |

---

## 13. Risques

| Risque | Probabilité | Impact | Parade |
|---|---|---|---|
| Import massif créant des doublons métier | Moyenne | Moyen | Détection des doublons en étape 2 + contrainte d'unicité insensible à la casse sur le libellé (déjà en base) |
| Export volumineux saturant la mémoire | Faible | Moyen | Limite à 20 000 lignes, refus explicite plutôt que troncature silencieuse |
| Fichier importé malveillant | Faible | Élevé | Contrôle d'extension et de taille, lecture `read_only` d'openpyxl, aucune macro exécutée, aucune évaluation de formule |
| Régression sur les écrans existants | Faible | Élevé | Suite complète 3 092 + 2 194 tests, 0 échec |
| Confusion activer / archiver / supprimer par les utilisateurs | Moyenne | Faible | Trois boutons distincts, libellés et modales de confirmation différents |

---

## 14. Sauvegarde et déploiement

Aucun déploiement n'a été effectué et aucune évolution structurelle n'a été appliquée.
La procédure à suivre le moment venu (après autorisation explicite) :

1. **Sauvegarde préalable** : `pg_dump` complet de la base, horodaté et conservé hors
   du serveur. Aucune migration n'étant nécessaire, le risque structurel est nul, mais
   la sauvegarde reste obligatoire avant toute mise en production.
2. **Point de retour** : tag `mission-02-point-restauration` (commit `08e2f4e`) ;
   point courant `b661d13`.
3. **Vérification** : `makemigrations --check` (aucune migration),
   `check_repo_hygiene`, suite backend 9 groupes, `npm run lint`, `npm run build`.
4. **Déploiement** : à autoriser explicitement. Interdiction de toute opération
   destructive (DROP, TRUNCATE, FLUSH, réinitialisation des migrations).

---

## 15. Suite du travail (PHASES 5 à 7)

- **PHASE 5 — Intégration** : brancher l'export/import sur les 4 référentiels en lecture
  seule (A1) ; étendre la résolution des clés étrangères (A2) ; vérifier chaque
  référentiel avec ses données réelles.
- **PHASE 6 — Tests** : campagne par référentiel (jeux de données réels, FK obligatoires,
  imports réels), tests navigateur sur l'assistant, tests de charge sur les exports.
- **PHASE 7 — Validation globale** : reprise de la `PR #5` (restée CONFLICTING,
  décision laissée au responsable fonctionnel) et relecture du présent tableau.

**Aucun push n'a été effectué** : l'environnement impose la branche unique de session, et
un push annulerait l'exécution CI en cours (`concurrency: cancel-in-progress`). Le commit
`b661d13` est prêt à être poussé sur demande.
