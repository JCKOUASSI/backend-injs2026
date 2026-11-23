# Frontend INJS-LMD — application web React

Interface web de l'application **INJS-LMD 2026** (INJS Marcory). Elle consomme
uniquement l'API Django/DRF (jamais la base directement) et respecte le principe :
l'interface ne masque pas les droits, elle les affiche selon les permissions renvoyées
par le backend.

> Documentation principale : [`../README.md`](../README.md) ·
> architecture : [`../docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md).

## Pile technique (versions vérifiées dans `package.json`)

- Node.js **22** (CI) / **20** (image Docker de build) · npm
- React **18.2** · React Router **6.22** · Vite **7**
- TanStack Query **5.101** · icônes Bootstrap Icons
- ESLint **8.56** (`eslint-plugin-react`, `react-hooks`)

## Arborescence

```
frontend/
├── src/
│   ├── pages/        # Écrans (Formations, Scolarité, Statistiques, Jurys, Finances…)
│   ├── components/   # Composants réutilisables (dont le gabarit d'écrans, DA-08)
│   ├── context/      # AuthContext (session JWT)
│   ├── services/     # Client API (api.js)
│   └── utils/        # roles.js (matrice de rôles alignée sur le backend)
├── .env.example
├── Dockerfile        # Build Vite servi par Nginx
└── vite.config.js
```

## Démarrage

```bash
cd frontend
cp .env.example .env     # adapter VITE_API_URL si besoin
npm install
npm run dev              # http://localhost:3000 (Vite, HMR)
```

En développement avec API séparée, `VITE_API_URL` pointe vers la racine Django (le
préfixe `/api` est porté par le backend), par ex. `http://127.0.0.1:8001/api`, et
`CORS_ALLOWED_ORIGINS` côté backend doit inclure `http://localhost:3000`.

En démonstration, le build peut aussi être servi par Django sous une seule origine
(`PREVIEW_SPA=1`, voir [`../scripts/start_dev.sh`](../scripts/start_dev.sh)).

## Scripts

| Commande | Rôle |
|---|---|
| `npm run dev` | Serveur de développement Vite |
| `npm run build` | Build de production (`dist/`) |
| `npm run preview` | Prévisualisation du build |
| `npm run lint` | Analyse statique ESLint (0 erreur bloquante exigée en CI) |

> Aucun framework de tests frontend n'est encore en place dans ce lot ; son ajout est
> prévu (tâche P00-04 du plan de refonte).

## Identité visuelle

Les règles de couleurs (bleus INJS, accent ambre) et de glassmorphism sont celles des
règles maîtresses du projet ; le logo utilisé est `src/assets/logo-injs.svg`. Aucun actif
de l'ancien produit ne doit être réintroduit.

## Construction Docker

```bash
docker compose up --build      # voir compose.yml (build multi-stage Nginx, port 80)
```

Les variables `VITE_API_URL`, `VITE_BADGE_BASE_URL` et `VERSION` sont passées en arguments
de build (voir [`Dockerfile`](Dockerfile)).

> **Note technique héritée** : certains noms d'artefacts d'infrastructure gardent un
> libellé antérieur (image Docker `qr-badge-frontend`, dossier du client mobile). Ils ne
> sont pas renommés en phase documentaire ; leur bascule relève de DA-12 (retrait du
> legacy en dernier, derrière feu de bascule).
