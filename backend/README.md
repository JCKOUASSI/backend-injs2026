# Backend INJS-LMD — API Django / DRF

Backend de l'application **INJS-LMD 2026** de l'INJS Marcory (Abidjan) : gestion LMD
de A à Z (référentiels, admissions, scolarité, pédagogie, présences par QR, notes,
jurys, diplômation, finances étudiantes, administration, statistiques).

> Documentation principale : [`../README.md`](../README.md) ·
> architecture : [`../docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md) ·
> endpoints : [`../docs/API_ENDPOINTS.md`](../docs/API_ENDPOINTS.md).

## Pile technique (versions vérifiées dans `requirements.txt`)

- Python **3.12** (version cible CI/Docker) · Django **5.1.4**
- Django REST Framework **3.15.2** · SimpleJWT **5.4.0** · drf-spectacular **0.28.0**
- PostgreSQL (**16** en CI, **15** dans le Compose local) · Redis **7** pour le cache partagé
- WhiteNoise **6.8.2** (fichiers statiques) · Gunicorn **23.0.0**
- Exports : reportlab **4.2.5** (PDF), openpyxl **3.1.5** / python-docx (Excel/Word), qrcode **8.0**

## Arborescence des applications

Les applications Django sont disposées « à plat » sous `backend/` (décision **DA-01** /
ADR-005 — on ne renomme et ne déplace aucune app existante) :

`config` (réglages), `authentication` (12 rôles, JWT, permissions), `referentiels`,
`parametres`, `formations`, `presences`, `exports`, `dashboard`, `statistiques`,
`suiviEvaluation`, `scolarite`, `admissions`, `equivalences`, `jurys`, `graduation`,
`finances_etudiantes`, `stages`, `administrations`, `ressources_humaines`, `patrimoine`,
`edts`.

La correspondance modules de référence ↔ applications figure dans
[`../docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md).

## Démarrage rapide

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # renseigner SECRET_KEY et POSTGRES_* (ou USE_SQLITE=1)
python manage.py migrate
python seed_data.py             # données de démonstration (jamais en production)
python manage.py runserver 0.0.0.0:8001
```

Un démarrage complet (frontend + API + travailleur planifié) est fourni par
[`../scripts/start_dev.sh`](../scripts/start_dev.sh). En Docker : voir
[`compose.yml`](compose.yml) et le [`Dockerfile`](Dockerfile).

## Variables d'environnement

Le tableau complet (nom, rôle, défaut, obligation en production) se trouve dans
[`../README.md#variables-denvironnement`](../README.md). Un exemplaire commenté est
disponible dans [`.env.example`](.env.example).

## Tests

```bash
# Le manifeste WhiteNoise doit exister avant les tests qui rendent des templates :
SECRET_KEY=ci-secret DEBUG=True python manage.py collectstatic --noinput
python manage.py test --noinput -v 2
python manage.py check_repo_hygiene
```

La suite de référence CI s'exécute sur PostgreSQL 16 / Python 3.12.

## API

- Schéma OpenAPI / Swagger : `GET /api/schema/` et `GET /api/docs/` (drf-spectacular).
- Authentification JWT : `POST /api/auth/login/`, `POST /api/auth/token/refresh/`,
  `GET /api/auth/me/`.
- Le badgeage public par QR (`/api/scan/`) est désactivé par défaut en production
  (`PUBLIC_QR_SCAN_ENABLED=False`) ; les applications mobiles utilisent le parcours
  authentifié `/api/scan/secure/`.

> **Note sur les noms techniques hérités** : certains identifiants conservent des sigles
> antérieurs (classes de permission `IsDFRC…`, membre de statut `Pointage.Statut.FORCE_DFRC`,
> nom de base par défaut `qr_badge`, images Docker `qr-badge-*`). Ils ne sont pas renommés
> en phase documentaire (ils relèvent du code et de l'infrastructure) ; leur bascule est
> tracée par DA-12 / ADR-005 et interviendra derrière feature flag.
