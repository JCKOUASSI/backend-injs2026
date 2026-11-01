# Livrable 14 — Fichiers modifiés et créés

Périmètre mesuré : `git diff 98f6121..HEAD` → **73 fichiers, 8 936 insertions,
9 suppressions** (les 16 PNG de preuve comptent pour ~1,5 Mo).

## 14.1 Backend — code

| Fichier | État | Nature |
|---|---|---|
| `backend/referentiels/models.py` | modifié | `fiabilite` sur les 8 référentiels du socle ; 6 nouveaux modèles (`RefEcole`, `RefMention`, `RefTypeCursus`, `RefFiliere`, `RefStatutVague`, `RefTypeEnseignement`) ; 2 modèles de données importées (`RefModuleOfficiel`, `RefVolumeHoraireFormation`) ; `RefSocle.reactiver()` ; action de journal `REACTIVATION` ; contraintes anti-doublon |
| `backend/referentiels/registre.py` | **créé** | Registre unique : 7 catégories, 26 référentiels, `modele_de()`, `entrees_par_categorie()`, routes UI/API par entrée |
| `backend/referentiels/serializers.py` | modifié | Sérialiseur du socle (`source_document` + `fiabilite`) et fabrique `serializer_pour_ref(slug)` mémoïsée, libellés de clés étrangères |
| `backend/referentiels/views.py` | modifié | `RefGeneriqueViewSet`, `TableauDeBordReferentielsView`, ViewSets de lecture, `RefPagination`, `_routes_selecteurs()`, `_a_le_champ()` |
| `backend/referentiels/urls.py` | modifié | Route `tableau-de-bord/`, génération des routes par slug éditable, exclusion des entrées à `route_api` propre |
| `backend/referentiels/admin.py` | modifié | 15 Admin classes (9 référentiels du socle + 6 nouveaux + lecture seule) |
| `backend/referentiels/management/commands/importer_referentiels_injs.py` | **créé** | Import idempotent des 5 blocs documentaires (`--dry-run`, `--sans-lieux`, `--sans-cycles`) |
| `backend/referentiels/management/commands/verifier_coherence_referentiels.py` | **créé** | Contrôle lecture seule (provenance, duplication de référentiel, rattachement) ; `--strict` → code de retour 1 |
| `backend/referentiels/data/{institutions,lieux,modules_officiels,volumes_horaires}.json` | **créés** | Les données extraites des documents, sans valeur inventée |
| `backend/formations/models.py` | modifié | `RefFormation.filiere` → `RefFiliere`, `RefVague.statut` → `RefStatutVague`, provenance sur `RefSite`/`RefBatiment`/`RefSalle` |
| `backend/scolarite/management/commands/smoke_test_injs.py` | modifié | Fenêtre de campagne glissante (correction A-53-13) |

## 14.2 Backend — migrations

| Fichier | Rôle |
|---|---|
| `referentiels/0002_refgradeenseignant_fiabilite_and_more.py` | Fiabilité + 6 modèles de la refonte |
| `referentiels/0003_refmoduleofficiel.py` | Modules officiels |
| `referentiels/0004_reffiliere_code_dossier.py` | Code dossier F01…F08 (réconciliation exclusive) |
| `referentiels/0005_alter_refmoduleofficiel_filiere_code_and_more.py` | `help_text` conformes aux valeurs réelles |
| `referentiels/0006_reactivation_action.py` | Valeur de journal `REACTIVATION` |
| `formations/0099_refformation_filiere_refvague_categorie_and_more.py` | FK filière, catégorie et statut de vague |
| `formations/0100_refbatiment_fiabilite_refbatiment_source_document_and_more.py` | Provenance des lieux |

## 14.3 Backend — tests

| Fichier | État | Contenu |
|---|---|---|
| `referentiels/tests/test_refonte.py` | **créé** | 28 tests : registre, CRUD générique, cycle de vie, traçabilité, import, cohérence |

## 14.4 Frontend

| Fichier | État | Nature |
|---|---|---|
| `src/pages/referentiels/TableauDeBordReferentiels.jsx` | **créé** | Tableau de bord : KPI, recherche, filtres par catégorie, cartes de complétude, liens contextuels |
| `src/pages/referentiels/ReferentielGenerique.jsx` | **créé** | CRUD générique piloté par le registre (modale, sélecteurs dépendants, archivage confirmé, lecture seule, rechargement silencieux) |
| `src/styles/referentiels.css` | **créé** | Styles `.ref-*` additifs sur le socle `.cand-*` |
| `src/App.jsx` | modifié | `/referentiels` → tableau de bord, `/referentiels/edition` → écran historique, `/referentiels/gestion/:slug` → gestion générique |
| `src/menu/arborescence.js` | modifié | « Tous les référentiels » devient « Tableau de bord » ; ajout de « Édition des tables » |
| `scripts/capture-referentiels.cjs` | **créé** | Preuve visuelle reproductible (Chromium headless, connexion réelle) |
| `scripts/recette-referentiels.cjs` | **créé** | Recette de bout en bout agie (création → modification → archivage → réactivation, journal, lecture seule) |
| `package.json` / `package-lock.json` | modifiés | `puppeteer-core` + `@sparticuz/chromium` en `devDependencies` (outil de capture, hors bundle) |

## 14.5 Documentation et preuves

| Fichier | Rôle |
|---|---|
| `docs/audits/53/00-schema-architecture-finale.md` | Schéma synthétique (Mermaid) de l'architecture finale |
| `docs/audits/53/01-…-16-…` | Les 16 livrables |
| `docs/audits/53/captures/*.png` | 8 captures bureau + 2 captures de contrôle (liens, sans écran dédié) |
| `docs/audits/53/captures/mobile/*.png` | 8 captures en **émulation** 390 × 844 |
| `docs/audits/53/captures/recette/*.png` | 5 captures du parcours agi et des écrans en lecture seule |

## 14.6 Fichiers volontairement **non** modifiés

| Fichier | Raison |
|---|---|
| `backend/scolarite/models.py`, `api_views.py` | Les référentiels LMD existants (niveaux, semestres, parcours, UE) restent la référence ; le module les référence sans les dupliquer |
| `backend/admissions/*` | Consomme déjà `formations.RefVague` ; aucune rupture d'API |
| `frontend/src/pages/Referentiels.jsx` | Conservé : il reste la seule saisie des catégories, grades, vagues, sites. Il perd son statut de point d'entrée |
| `frontend/src/pages/scolarite/Maquettes.jsx`, `Equivalences.jsx` | Hors périmètre ; leurs tests restent au vert |
| `backend/config/settings.py` | Aucun réglage de déploiement modifié |
| Tout test existant | Aucun test n'a été affaibli, désactivé ou réécrit ; 8 tests ont été **ajoutés** |
