# Livrable 14 — Fichiers modifiés et créés

## 14.1 Backend — fichiers modifiés

| Fichier | Nature de la modification |
|---|---|
| `backend/referentiels/models.py` | `fiabilite` sur les 8 référentiels du socle ; nouveaux modèles `RefEcole`, `RefMention`, `RefTypeCursus`, `RefFiliere` (+ `code_dossier`), `RefStatutVague`, `RefTypeEnseignement`, `RefTypeEspaceSportif`, `RefModuleOfficiel`, `RefVolumeHoraireFormation` ; contraintes anti-doublon |
| `backend/referentiels/serializers.py` | `CHAMPS_SOCLE`, `serializer_pour_ref(slug)` (fabrique mémoïsée), libellés de clés étrangères, sérialiseurs lecture seule des modules et volumes |
| `backend/referentiels/views.py` | `RefGeneriqueViewSet` (CRUD par slug + archivage), `TableauDeBordReferentielsView`, `RefModuleOfficielViewSet`, `RefVolumeHoraireFormationViewSet`, `RefPagination`, `_routes_selecteurs()`, `_a_le_champ()` |
| `backend/referentiels/urls.py` | Route `tableau-de-bord/`, génération des routes par slug éditable, exclusion des entrées à `route_api`, enregistrement des deux ViewSets en lecture seule |
| `backend/referentiels/admin.py` | Enregistrement de `RefModuleOfficiel`, `RefVolumeHoraireFormation` (lecture seule) et des 6 référentiels métier |
| `backend/formations/models.py` | FK `RefFormation.filiere`, `RefVague.categorie`, `source_document` + `fiabilite` sur `RefSite`/`RefBatiment`/`RefSalle` |

## 14.2 Backend — fichiers créés

| Fichier | Rôle |
|---|---|
| `backend/referentiels/registre.py` | **Registre central** : 7 catégories, 26 référentiels, `modele_de()`, `entrees_par_categorie()` |
| `backend/referentiels/management/commands/importer_referentiels_injs.py` | Import idempotent des 5 blocs documentaires, `--dry-run`, `--sans-lieux`, `--sans-cycles` |
| `backend/referentiels/management/commands/verifier_coherence_referentiels.py` | Contrôle de cohérence en lecture seule (familles A-53-01 → A-53-07) |
| `backend/referentiels/data/institutions.json` | Écoles, mentions, natures de cursus, filières, statuts de vague, types d'enseignement |
| `backend/referentiels/data/modules_officiels.json` | 227 modules officiels avec leur localisation documentée |
| `backend/referentiels/data/lieux.json` | Site, 16 bâtiments, 166 espaces |
| `backend/referentiels/data/volumes_horaires.json` | 51 répartitions horaires (proposition) |
| `backend/referentiels/migrations/0002_refgradeenseignant_fiabilite_and_more.py` | Fiabilité + modèles de la refonte |
| `backend/referentiels/migrations/0003_refmoduleofficiel.py` | Modules officiels |
| `backend/referentiels/migrations/0004_reffiliere_code_dossier.py` | Code dossier F01…F08 |
| `backend/referentiels/migrations/0005_alter_refmoduleofficiel_filiere_code_and_more.py` | `help_text` conformes aux valeurs réelles |
| `backend/formations/migrations/0099_refformation_filiere_refvague_categorie_and_more.py` | FK filière + catégorie de vague |
| `backend/formations/migrations/0100_refbatiment_fiabilite_refbatiment_source_document_and_more.py` | Provenance des lieux |
| `backend/referentiels/migrations/0006_reactivation_action.py` | Action de journal `REACTIVATION` (correction A-53-09) |
| `backend/referentiels/tests/test_refonte.py` | 24 tests dédiés à la refonte (lot total `referentiels` : 44) |

## 14.3 Frontend — fichiers modifiés

| Fichier | Modification |
|---|---|
| `frontend/src/App.jsx` | Import des deux écrans ; `/referentiels` → tableau de bord ; `/referentiels/edition` → écran historique ; `/referentiels/gestion/:slug` → écran générique |
| `frontend/src/pages/referentiels/ReferentielGenerique.jsx` | Rechargement silencieux après écriture (A-53-12) ; filtre d'état masqué en lecture seule |
| `frontend/src/pages/referentiels/TableauDeBordReferentiels.jsx` | Lien « Consulter » seulement si l'écran existe ; mention « Sans écran dédié » sinon (A-53-11) |
| `frontend/src/menu/arborescence.js` | Entrée « Tous les référentiels » renommée « Tableau de bord » ; ajout de « Édition des tables » (`/referentiels/edition`) |
| `frontend/package.json` / `package-lock.json` | Ajout de `puppeteer-core` et `@sparticuz/chromium` en `devDependencies` (outil de capture, absent du bundle) |

## 14.4 Frontend — fichiers créés

| Fichier | Rôle |
|---|---|
| `frontend/src/pages/referentiels/TableauDeBordReferentiels.jsx` | Cartographie, KPI, recherche, filtres, cartes de complétude |
| `frontend/src/pages/referentiels/ReferentielGenerique.jsx` | CRUD générique, sélecteurs dépendants, archivage, lecture seule |
| `frontend/src/styles/referentiels.css` | Styles `.ref-*` du module (s'appuie sur le socle `.cand-*`) |
| `frontend/scripts/capture-referentiels.cjs` | Preuve visuelle reproductible (Chromium headless, connexion réelle à l'API) |
| `frontend/scripts/recette-referentiels.cjs` | Recette de bout en bout **agie** (création, modification, archivage, réactivation, contrôle lecture seule, journal) — livrable 16 |

## 14.5 Documentation

| Fichier | Rôle |
|---|---|
| `docs/audits/53/01-…-16-…` | Les 16 livrables de la mission (16 = recette de bout en bout) |
| `docs/audits/53/00-schema-architecture-finale.md` | Schéma synthétique de l'architecture fonctionnelle |
| `docs/audits/53/captures/*.png` | 8 preuves visuelles bureau + 8 émulations mobiles + 7 captures de recette (`captures/recette/`) |

## 14.6 Fichiers volontairement **non** modifiés

| Fichier | Raison |
|---|---|
| `backend/scolarite/models.py`, `api_views.py` | Aucune modification : les référentiels LMD existants restent la référence pour les niveaux, semestres, parcours et UE |
| `backend/admissions/*` | Le module consomme déjà `formations.RefVague` ; aucune rupture d'API |
| `frontend/src/pages/scolarite/Maquettes.jsx`, `Equivalences.jsx` | Écrans hors périmètre ; leurs tests restent au vert |
| `backend/config/settings.py` | Aucun réglage de déploiement modifié |
| Tout test existant | Aucun test n'a été affaibli, désactivé ou réécrit |
