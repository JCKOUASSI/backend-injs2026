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

> **Relevé historique** : cette section décrit l'état mesuré au commit `b661d13`
> (PHASES 1 à 4). Les chiffres **finaux**, relevés après les PHASES 5 à 7, sont
> au §16.

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

## 11. Tableau de conformité des 27 référentiels

**Méthode** : le tableau ci-dessous n'est pas une déclaration d'intention. Il est produit par
`backend/referentiels/tests/test_rapport_conformite.py`, qui rejoue chaque référentiel par le
HTTP réel (routes, verbes, permissions, formats) et imprime le résultat mesuré. Chaque case
correspond à un appel exécuté, pas à une lecture de code.

**Légende** — `✓` opérationnel et vérifié · `n/a` non applicable (le modèle ne porte pas le
champ, ou le référentiel est en lecture seule) · `refusé` refusé **et** prouvé par un test.

### 11.1 Synthèse

| Référentiel | Modèle | CRUD | Consult. | Recherche | Tri | Pagination | Export | Import | Activation | Archivage | Suppr. sécurisée | Non-habilité |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `ecoles` | Référentiel – École | ✓ | ✓ | ✓ | ✓ | ✓ | 4/4 | ✓ | ✓ | ✓ | ✓ | refusé |
| `mentions` | Référentiel – Mention | ✓ | ✓ | ✓ | ✓ | ✓ | 4/4 | ✓ | ✓ | ✓ | ✓ | refusé |
| `types-cursus` | Référentiel – Type de cursus | ✓ | ✓ | ✓ | ✓ | ✓ | 4/4 | ✓ | ✓ | ✓ | ✓ | refusé |
| `filieres` | Référentiel – Filière | ✓ | ✓ | ✓ | ✓ | ✓ | 4/4 | ✓ | ✓ | ✓ | ✓ | refusé |
| `types-enseignement` | Référentiel – Type d'enseignement | ✓ | ✓ | ✓ | ✓ | ✓ | 4/4 | ✓ | ✓ | ✓ | ✓ | refusé |
| `statuts-vague` | Référentiel – Statut de vague | ✓ | ✓ | ✓ | ✓ | ✓ | 4/4 | ✓ | ✓ | ✓ | ✓ | refusé |
| `types-evaluation` | Référentiel – Type d'évaluation | ✓ | ✓ | ✓ | ✓ | ✓ | 4/4 | ✓ | ✓ | ✓ | ✓ | refusé |
| `types-decision` | Référentiel – Type de décision | ✓ | ✓ | ✓ | ✓ | ✓ | 4/4 | ✓ | ✓ | ✓ | ✓ | refusé |
| `types-espace-sportif` | Référentiel – Type d'espace sportif | ✓ | ✓ | ✓ | ✓ | ✓ | 4/4 | ✓ | ✓ | ✓ | ✓ | refusé |
| `grades-enseignant` | Référentiel – Grade enseignant | ✓ | ✓ | ✓ | ✓ | ✓ | 4/4 | ✓ | ✓ | ✓ | ✓ | refusé |
| `types-document` | Référentiel – Type de document | ✓ | ✓ | ✓ | ✓ | ✓ | 4/4 | ✓ | ✓ | ✓ | ✓ | refusé |
| `types-frais` | Référentiel – Type de frais | ✓ | ✓ | ✓ | ✓ | ✓ | 4/4 | ✓ | ✓ | ✓ | ✓ | refusé |
| `modes-paiement` | Référentiel – Mode de paiement | ✓ | ✓ | ✓ | ✓ | ✓ | 4/4 | ✓ | ✓ | ✓ | ✓ | refusé |
| `types-notification` | Référentiel – Type de notification | ✓ | ✓ | ✓ | ✓ | ✓ | 4/4 | ✓ | ✓ | ✓ | ✓ | refusé |
| `niveaux` | LMD – Niveau | ✓ | ✓ | ✓ | ✓ | ✓ | 4/4 | ✓ | ✓ | n/a | ✓ | refusé |
| `semestres` | LMD – Semestre | ✓ | ✓ | ✓ | ✓ | ✓ | 4/4 | ✓ | ✓ | n/a | ✓ | refusé |
| `parcours` | LMD – Parcours | ✓ | ✓ | ✓ | ✓ | ✓ | 4/4 | ✓ | ✓ | n/a | ✓ | refusé |
| `types-formation` | LMD – Type de formation | ✓ | ✓ | ✓ | ✓ | ✓ | 4/4 | ✓ | ✓ | n/a | ✓ | refusé |
| `annees` | LMD – Année académique | ✓ | ✓ | ✓ | ✓ | ✓ | 4/4 | ✓ | ✓ | n/a | ✓ | refusé |
| `sites` | Référentiel – Site | ✓ | ✓ | ✓ | ✓ | ✓ | 4/4 | ✓ | ✓ | n/a | ✓ | refusé |
| `batiments` | Référentiel – Bâtiment | ✓ | ✓ | ✓ | ✓ | ✓ | 4/4 | ✓ | ✓ | n/a | ✓ | refusé |
| `salles` | Référentiel – Salle | ✓ | ✓ | ✓ | ✓ | ✓ | 4/4 | ✓ | ✓ | n/a | ✓ | refusé |
| `vagues` | Référentiel – Vague | ✓ | ✓ | ✓ | ✓ | ✓ | 4/4 | ✓ | ✓ | n/a | ✓ | refusé |
| `formations` | Référentiel – Formation (cycle) | refusé | ✓ | ✓ | ✓ | ✓ | 4/4 | refusé | n/a | n/a | n/a | refusé |
| `ue-ecue` | LMD – Unité d'enseignement | refusé | ✓ | ✓ | ✓ | ✓ | 4/4 | refusé | n/a | n/a | n/a | refusé |
| `modules-officiels` | Référentiel – Module officiel | refusé | ✓ | ✓ | ✓ | ✓ | 4/4 | refusé | n/a | n/a | n/a | refusé |
| `volumes-modules` | Référentiel – Volume horaire | refusé | ✓ | ✓ | ✓ | ✓ | 4/4 | refusé | n/a | n/a | n/a | refusé |

**Totaux** : 27 consultables · 27 exportables dans les 4 formats · 23 éditables (CRUD + import)
· 4 en lecture seule · 0 référentiel sans export · 0 référentiel dont la lecture est bloquée.

### 11.2 Justification des « non applicable »

| Colonne | Référentiels concernés | Raison exacte |
|---|---|---|
| Archivage `n/a` | 9 modèles hors socle (`niveaux`, `semestres`, `parcours`, `types-formation`, `annees`, `sites`, `batiments`, `salles`, `vagues`) | Ces modèles n'ont **pas de champ `archive`**. L'action existe mais répond `400` avec un message explicite, au lieu de lever une erreur inattendue. Aucune réécriture de modèle n'a été faite : ajouter un champ relève d'une migration de schéma, interdite sans arbitrage. |
| Archivage / activation `n/a` | les 4 lecture seule | Aucun cycle de vie n'est exposé : le référentiel n'est pas géré par le Hub. |
| Import `refusé` | les 4 lecture seule | Aucune route d'import n'est créée (`404`). C'est la restriction métier attendue, et non un blocage de lecture. |
| CRUD `refusé` | les 4 lecture seule | `POST` renvoie `405 Method Not Allowed` (ou `404` si la route n'existe pas). Les deux statuts sont acceptés par les tests ; dans tous les cas **aucune ligne n'est écrite** — c'est ce que vérifie l'assertion ajoutée. |

### 11.3 Point de vigilance levé pendant la recette

La recette a révélé que **3 des 4 référentiels en lecture seule n'avaient aucune route de
consultation** sous leur slug de registre (`formations`, `ue-ecue`, `volumes-modules`). L'écran
du Hub qui référence `volumes-modules` (`route_ui` = `/referentiels/gestion/volumes-modules`)
appelait donc une API inexistante : la page ne pouvait pas afficher une seule ligne. Le
caractère lecture seule bloquait la **lecture**, ce que la consigne interdit expressément.

Correctif (`backend/referentiels/urls.py`) : une route de consultation en lecture seule
(`GET` liste et détail uniquement) est désormais ouverte pour chaque référentiel non éditable,
servie par `ReferentielLectureSeuleViewSet` — un `ReadOnlyModelViewSet`, qui n'expose par
construction aucun verbe d'écriture. La route d'export reste ouverte à tous.

---

## 12. PHASE 5 — Résolution des clés étrangères à l'import

### 12.1 Ce qui a été construit

`backend/referentiels/moteur/relations.py` (nouveau) introduit un résolveur générique, piloté
par l'introspection des modèles et non par une liste codée en dur :

| Fonction | Rôle |
|---|---|
| `cles_etrangeres(modele)` | toutes les FK du modèle, y compris vers d'autres applications (`scolarite`, `formations`) |
| `cles_metier(modele)` | les champs par lesquels une valeur est reconnaissable : identifiant, `code`, `libelle`, `nom_complet`, `intitule_module`… |
| `groupes_uniques(modele)` | les index d'unicité composites du modèle lié |
| `ResolveurRelations` | indexe une fois chaque modèle lié, puis résout champ par champ |

### 12.2 Comportement garanti

1. **Résolution par identifiant *et* par champ métier** — « ENSEPS », « enseps », « 1 » et
   « École ENSEPS » retrouvent la même école. La normalisation est insensible à la casse, aux
   accents et aux espaces superflus.
2. **Référence inexistante** → anomalie nommée (`nature: 'relation'`), ligne et colonne
   renseignées, **aucune association**. Le message indique quoi créer au préalable.
3. **Référence ambiguë** → **jamais** de correspondance inventée. Le résolveur renvoie
   `AMBIGU`, la ligne est rejetée, et l'anomalie liste les candidats.
4. **Ambiguïté levée par le rattachement** — un libellé unique *par parent* (deux « Bâtiment A »
   sur deux sites différents) est résolu dès que la ligne porte le site. L'unicité composite est
   lue dans les index du modèle, et le rattachement est déclaré par le registre
   (`unicite_par`).
5. **Respect des contraintes d'unicité** — la résolution s'appuie sur les index réels du modèle
   lié, pas sur une convention supposée.
6. **Intégrité transactionnelle** — la résolution se fait à l'étape de validation, sans aucune
   écriture ; l'import n'a lieu que dans une transaction unique.

### 12.3 Ce que voit l'utilisateur

L'endpoint d'analyse renvoie désormais la description des colonnes de rattachement, et l'assistant
d'import les affiche explicitement (modèle rattaché, clés métier reconnues, caractère
obligatoire, nombre de références non résolues). L'utilisateur n'a plus à deviner qu'il peut
écrire « ENSEPS » au lieu d'un identifiant.

---

## 13. Anomalies découvertes et corrigées pendant les PHASES 5 à 7

Ces anomalies sont des **bugs de production réels**, trouvés en écrivant les tests — pas des
ajustements de style.

| # | Anomalie | Gravité | Symptôme observable | Correctif |
|---|---|---|---|---|
| B1 | `mixins._journaliser_import` avalait les `Exception` ; `journaliser` levait `TypeError: Object of type RefEcole is not JSON serializable` | **Critique** | L'import répondait `crees: 2` **sans aucune ligne en base** : la transaction était annulée en silence et l'utilisateur croyait l'import réussi | Helper `payload_jsonisable()` (modèle → `str`, date → `isoformat`, `Decimal` → `float`) ; suppression du `except Exception` : une erreur de journal ne doit jamais être avalée |
| B2 | Les lignes rejetées dès la validation n'apparaissaient pas dans le rapport final | Haute | Un lot partiellement invalide affichait `nb_anomalies: 0` | `anomalies` pré-remplies depuis `validation['erreurs']` avec `phase='validation'`, et nouvelle clé `lignes_rejetees` |
| B3 | Le cache du résolveur de relations était insensible au contexte | Haute | Une résolution ambiguë (`None`) était remise en cache et réutilisée pour une résolution contextualisée qui, elle, avait une réponse unique | Clé de cache `(champ, valeur_normalisée, signature_du_contexte)` |
| B4 | 3 référentiels en lecture seule sans route de consultation (voir §11.3) | Haute | Écran du Hub vide : le lecture seule bloquait la lecture | Routes `GET` liste/détail en lecture seule |
| B5 | `relations_attendues()` n'était exposée par aucun endpoint : l'interface ne pouvait pas afficher les colonnes de rattachement | Moyenne | Fonctionnalité annoncée mais non branchée | `relations` intégré au rapport de validation, avec le compteur `non_resolues` par colonne |
| B6 | Correspondance anomaly ↔ colonne faite sur le libellé affiché (`Ecole`) au lieu de la clé de champ (`ecole`) | Moyenne | Le compteur de références non résolues restait à 0 | Ajout de `'champ'` aux anomalies de relation ; comptage par clé |

---

## 14. Fichiers créés ou modifiés (PHASES 5 à 7)

### 14.1 Créés

| Fichier | Rôle |
|---|---|
| `backend/referentiels/moteur/relations.py` | Moteur de résolution des clés étrangères (détection, indexation, levée d'ambiguïté) |
| `backend/referentiels/tests/test_relations_import.py` | 26 tests dédiés aux relations : identification, résolution, ambiguïté, import avec relations |
| `backend/referentiels/tests/test_recette_27_referentiels.py` | Recette fonctionnelle des 27 référentiels (16 tests) |
| `backend/referentiels/tests/test_rapport_conformite.py` | Génère le tableau de conformité **mesuré** du §11 |

### 14.2 Modifiés

| Fichier | Nature de la modification |
|---|---|
| `backend/referentiels/urls.py` | Routes de consultation et d'export en lecture seule pour les référentiels non éditables |
| `backend/referentiels/views.py` | `_bascule_activation`, `_a_le_champ`, refus `409` de la suppression sans archivage, gestion des dates |
| `backend/referentiels/moteur/importations.py` | `champ_identite()`, doublons sur `code` **et** `libelle`, rapport complet (`anomalies` + `lignes_rejetees` + `relations`) |
| `backend/referentiels/moteur/mixins.py` | `payload_jsonisable()`, journalisation non silencieuse, description des relations |
| `backend/referentiels/moteur/colonnes.py` | Colonnes importables et identité du référentiel |
| `backend/referentiels/tests/test_moteur_referentiels.py` | Test anti-régression « le rapport ne ment jamais » |
| `backend/referentiels/tests/test_refonte.py`, `test_gestion_lmd.py` | Tests mis à jour : le refus d'écriture passe de `404` à `405`, avec vérification qu'aucune ligne n'est écrite |
| `frontend/src/components/referentiels/AssistantImport.jsx` | Affichage des colonnes de rattachement et du détail des anomalies par phase |
| `frontend/src/components/referentiels/ReferentielsMoteur.test.jsx` | 4 nouveaux tests (relations affichées, non-résolues, absence de relations, phases d'anomalies) |
| `frontend/src/styles/referentiels.css` | Styles `.ref-badge` et `.ref-import-nonresolu` |

**Aucune migration** n'a été créée : aucun champ, index ni modèle n'a été ajouté
(`makemigrations --check` → *No changes detected*).

---

## 15. Endpoints et permissions

### 15.1 Endpoints

Aucune route nouvelle n'a été inventée en dehors des conventions déjà en vigueur. Les ajouts
sont des **routes manquantes** sur des slugs existants :

| Route | Verbes | Référentiels | Raison |
|---|---|---|---|
| `/api/referentiels/<slug>/` | `GET` | les 4 non éditables non servis par le routeur | consultation en lecture seule (§11.3) |
| `/api/referentiels/<slug>/<pk>/` | `GET` | idem | détail en lecture seule |
| `/api/referentiels/<slug>/exporter/` | `GET` | les 4 non éditables | déjà existant, désormais systématique |

L'information sur les relations transite par l'endpoint d'analyse existant
(`POST /api/referentiels/<slug>/importer/analyse/`), dans `validation.relations`.

### 15.2 Permissions

Les permissions sont contrôlées **côté serveur**, opération par opération, par
`ReferentielPermission` :

| Opération | Habilité | Non habilité | Anonyme |
|---|---|---|---|
| Consultation, recherche, tri, pagination | `200` | refusé | refusé |
| Export (4 formats) | `200` | refusé | refusé |
| Import (analyse et exécution) | `200` | refusé | refusé |
| Création, modification | `200`/`201` | refusé | refusé |
| Activation, désactivation, archivage, restauration | `200` | refusé | refusé |
| Suppression | `200` ou `409` si dépendances | refusé | refusé |

Mesuré sur les 27 référentiels : **27/27** refusent l'écriture au simple lecteur et **27/27**
refusent toute lecture à l'anonyme.

### 15.3 Suppression sécurisée : les trois opérations restent distinctes

| Opération | Effet | Réversible | Détruit la ligne |
|---|---|---|---|
| Désactivation | `actif = False`, la valeur reste utilisable en lecture et proposée dans l'historique | oui | non |
| Archivage | `archive = True`, la valeur disparaît des listes courantes | oui | non |
| Suppression | archivage + confirmation obligatoire ; `409` avec le détail si des dépendances existent | non (par conception) | **jamais** |

Aucun chemin de code n'appelle `objet.delete()`. La recette vérifie, après chaque suppression
acceptée, que la ligne existe toujours en base.

---

## 16. Résultats des tests réellement exécutés

Les chiffres ci-dessous sont les sorties réelles des commandes, relevées après le dernier
correctif.

### 16.1 Backend — suite complète (9 groupes)

| Groupe | Résultat | Tests |
|---|---|---|
| scolarite | RÉUSSI | 515 |
| formations | RÉUSSI | 289 |
| auth | RÉUSSI | 242 |
| habilitations | RÉUSSI | 520 |
| edt | RÉUSSI | 591 |
| evaluations | RÉUSSI | 237 |
| pilotage | RÉUSSI | 245 |
| socle (dont `referentiels`) | RÉUSSI | 345 |
| divers | RÉUSSI | 152 |
| **Total** | **9 groupes / 0 échec** | **3 136** |

### 16.2 Backend — suites dédiées à la mission

| Suite | Commande | Résultat |
|---|---|---|
| Recette des 27 | `manage.py test referentiels.tests.test_recette_27_referentiels` | **Ran 16 tests — OK** |
| Relations à l'import | `manage.py test referentiels.tests.test_relations_import` | **Ran 26 tests — OK** |
| Moteur (export/import/cycle) | `manage.py test referentiels.tests.test_moteur_referentiels` | **Ran 27 tests — OK** |
| Application `referentiels` entière | `manage.py test referentiels` | **Ran 166 tests — OK** |

### 16.3 Frontend

| Vérification | Résultat |
|---|---|
| `npx vitest run` | **133 fichiers / 2 198 tests — 0 échec** |
| `npx eslint src/` | 0 erreur sur les fichiers de la mission (les 4 erreurs résiduelles de `vite.config.js` et 2 avertissements de fichiers de test sont **préexistants** et hors périmètre) |
| `npx vite build` | réussi — 4,76 s |

### 16.4 Contrôles de dépôt

| Contrôle | Résultat |
|---|---|
| `manage.py makemigrations --check --dry-run` | *No changes detected* |
| `manage.py check` | *System check identified no issues* |
| `manage.py check_repo_hygiene` | **CONFORME** — 2 275 fichiers suivis, aucune donnée nominative, aucun `print()` runtime |

---

## 17. Anomalies résiduelles et limitations

| # | Limitation | Gravité | Pourquoi ce n'est pas corrigé ici |
|---|---|---|---|
| L1 | 9 modèles hors socle n'ont pas de champ `archive` : l'archivage leur est refusé (`400`), seule la désactivation est possible | Moyenne | Ajouter un champ relève d'une migration de schéma. À arbitrer avant intégration : soit on migre ces 9 modèles, soit on assume que la désactivation est leur archivage. |
| L2 | La résolution des relations indexe chaque modèle lié en mémoire | Faible | Suffisant pour les volumétries de référentiels. À revoir si un référentiel dépasse quelques dizaines de milliers de lignes. |
| L3 | La limite d'export (20 000 lignes) n'est pas paramétrable | Faible | À passer en réglage, sans urgence. |
| L4 | Aucun test exécuté dans un navigateur réel sur l'assistant d'import | Moyenne | Les 24 tests du composant rendent le DOM réel (jsdom) et vérifient les requêtes émises ; un passage manuel reste recommandé avant mise en production. |
| L5 | `test_rapport_conformite.py` écrit son relevé dans `/tmp/conformite-27.json` | Faible | Outil de recette, sans effet sur l'application. |

---

## 18. Statut Git et consignes respectées

| Consigne | Statut |
|---|---|
| Ne pas fusionner ni pousser | **respecté** — aucun `push`, aucune fusion |
| Ne pas modifier la CI, ne rien faire qui l'annule | **respecté** — `ci.yml` inchangé (`concurrency: cancel-in-progress: true`) |
| Pas de nouvelle branche | **respecté** — tout le travail est sur `arena/4524a57c-backend-injs2026` |
| Aucune modification destructive de la base | **respecté** — aucune migration, aucun `delete()` |
| Aucun déploiement en production | **respecté** |

**État du dépôt** : `b661d13` (PHASES 1 à 4) puis le commit de tête `HEAD` (PHASES 5 à 7,
intitulé « Mission 03 — PHASES 5 à 7 : relations à l'import, lecture seule consultable,
recette des 27 »). Les deux sont
**locaux et non poussés**, sur la branche de session `arena/4524a57c-backend-injs2026`.
L'arbre de travail est propre (`git status` vide après le commit).

Depuis `b661d13`, les modifications portent sur 16 fichiers
(`git diff --stat b661d13..HEAD`) : 4 créés, 12 modifiés, **aucune migration**.

### 18.1 Instructions de synchronisation (sans push)

```bash
# 1. Vérifier l'état local (doit être vide : tout est commité)
git status --porcelain
git diff --stat b661d13..HEAD

# 1 bis. Produire le tableau de conformité mesuré (§11)
cd backend && INJS_RAPPORT_CONFORMITE=1 PYTHONPATH=.. \
  DJANGO_SETTINGS_MODULE=arena.settings_sandbox \
  .venv/bin/python manage.py test referentiels.tests.test_rapport_conformite

# 2. Rejouer les contrôles avant de committer
cd backend  && PYTHONPATH=.. DJANGO_SETTINGS_MODULE=arena.settings_sandbox \
  .venv/bin/python manage.py test referentiels
cd ../frontend && npx vitest run && npx vite build

# 3. Committer sur la branche de session (PAS de push)
#    — déjà fait : le commit de tête porte les PHASES 5 à 7
git add -A
git commit -m "Mission 03 — PHASES 5 à 7 : ..."

# 4. Pousser UNIQUEMENT sur demande explicite, hors exécution CI
#    (un push annule la CI en cours : concurrency.cancel-in-progress)
git push origin arena/4524a57c-backend-injs2026
```

---

## 19. Recommandations avant intégration

1. **Arbitrer L1** (archivage des 9 modèles hors socle). C'est la seule limitation fonctionnelle
   qui se voit à l'usage : un utilisateur qui cherche « Archiver » sur un site ou un semestre
   obtient un refus. Soit on migre, soit on masque l'action pour ces référentiels.
2. **Rejouer un passage manuel** de l'assistant d'import sur un fichier réel comportant des
   colonnes de rattachement ambiguës (deux bâtiments homonymes sur deux sites) : le cas est
   couvert par les tests automatisés, mais mérite une validation fonctionnelle.
3. **Vérifier la volumétrie** des exports sur les plus gros référentiels avant d'ouvrir le Hub à
   tous les utilisateurs (L2, L3).
4. **Traiter la `PR #5`** restée `CONFLICTING` : la décision appartient au responsable
   fonctionnel, aucune fusion ne sera faite de sa propre initiative.
5. **Ne pousser qu'après la fin de l'exécution CI en cours**, pour ne pas l'annuler.

---

## 20. Conclusion

Le Hub Référentiels est livré industrialisé : un moteur commun, un registre comme source unique
de vérité, et une recette qui **exécute** les 27 référentiels au lieu de les décrire. Les
fonctionnalités annoncées sont toutes branchées et vérifiées ; les trois bugs de production
découverts pendant les tests (rapport d'import mensonger, transaction annulée en silence,
résolution insensible au contexte) sont corrigés et couverts par des tests anti-régression.

Un référentiel ajouté au registre hérite automatiquement des routes, des permissions, des
exports, des imports et de la recette — sans reprise individuelle du sous-module.
