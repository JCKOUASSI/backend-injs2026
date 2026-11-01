# Mission 53 — Refonte du module « Référentiels » INJS

Dossier des livrables. Code concerné : `backend/referentiels/`, `backend/formations/` (provenance), `frontend/src/pages/referentiels/`, `frontend/src/styles/referentiels.css`.

## Sommaire

| # | Livrable | Fichier |
|---|---|---|
| — | Schéma synthétique de l'architecture finale | [`00-schema-architecture-finale.md`](00-schema-architecture-finale.md) |
| 1 | Inventaire des 5 fichiers sources | [`01-inventaire-fichiers-sources.md`](01-inventaire-fichiers-sources.md) |
| 2 | Matrice de correspondance documents → référentiels | [`02-matrice-correspondance.md`](02-matrice-correspondance.md) |
| 3 | Architecture fonctionnelle définitive | [`03-architecture-fonctionnelle.md`](03-architecture-fonctionnelle.md) |
| 4 | Anciens sous-modules : conservés / modifiés / supprimés | [`04-sous-modules-anciens.md`](04-sous-modules-anciens.md) |
| 5 | Nouveaux sous-modules | [`05-nouveaux-sous-modules.md`](05-nouveaux-sous-modules.md) |
| 6 | Modèles et relations | [`06-modeles-et-relations.md`](06-modeles-et-relations.md) |
| 7 | Migrations | [`07-migrations.md`](07-migrations.md) |
| 8 | Volumes importés par référentiel | [`08-volumes-importes.md`](08-volumes-importes.md) |
| 9 | API créées et modifiées | [`09-api.md`](09-api.md) |
| 10 | Bilan frontend | [`10-bilan-frontend.md`](10-bilan-frontend.md) |
| 11 | Bilan des intégrations intermodules | [`11-integrations.md`](11-integrations.md) |
| 12 | Rapport détaillé des tests | [`12-tests.md`](12-tests.md) |
| 13 | Anomalies restantes | [`13-anomalies.md`](13-anomalies.md) |
| 14 | Fichiers modifiés et créés | [`14-fichiers-modifies.md`](14-fichiers-modifies.md) |
| 15 | Commits | [`15-commits.md`](15-commits.md) |

Preuves visuelles : [`captures/`](captures) (bureau 1440 × 960) et [`captures/mobile/`](captures/mobile) (émulation 390 × 844).

## En bref

- **26 référentiels** déclarés dans un registre unique, répartis en **7 catégories**.
- **227 modules officiels**, **51 volumes horaires**, **1 site / 16 bâtiments / 166 espaces**, **8 filières**, **8 cycles LMD** : tous issus des documents, avec provenance.
- **2 729 tests backend** et **2 073 tests frontend** exécutés, **0 échec**.
- **22 constats de cohérence** (3 familles) documentés, aucun corrigé par supposition.

## Reproduire

```bash
# Backend
cd backend
USE_SQLITE=1 SECRET_KEY=x DEBUG=1 .venv/bin/python manage.py migrate
USE_SQLITE=1 SECRET_KEY=x DEBUG=1 .venv/bin/python manage.py importer_referentiels_injs --dry-run
USE_SQLITE=1 SECRET_KEY=x DEBUG=1 .venv/bin/python manage.py importer_referentiels_injs
USE_SQLITE=1 SECRET_KEY=x DEBUG=1 .venv/bin/python manage.py verifier_coherence_referentiels
USE_SQLITE=1 SECRET_KEY=x DEBUG=1 .venv/bin/python manage.py test referentiels

# Preuve visuelle (Chromium fourni par @sparticuz/chromium — aucun root requis)
cd frontend
npm i -D puppeteer-core @sparticuz/chromium
LD_LIBRARY_PATH=/tmp/chlibs node scripts/capture-referentiels.cjs
```
