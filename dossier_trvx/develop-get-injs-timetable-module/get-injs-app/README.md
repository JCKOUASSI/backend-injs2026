# GET INJS APP — module Emplois du temps LMD (INJS Marcory)

Module de gestion et de génération des emplois du temps de l'Institut National de la
Jeunesse et des Sports (Abidjan), intégrable à `backend-injs2026`.

## Contenu du dossier

| Chemin | Rôle |
| --- | --- |
| `Conception-GET-INJS.txt` | Documentation complète (processus, modèle, commandes) |
| `PROMPT-MAITRE-GET-INJS.txt` | Prompt groupé de la mission, réutilisable par un agent de build |
| `data/referentiel.ts` | Référentiels INJS normalisés (filières, formations, maquettes, salles, groupes, vagues) |
| `data/exemple-etudiants-injs.csv` | Modèle de fichier d'import externe |
| `lib/engine.ts` | Moteur de génération LMD déterministe, sans dépendance framework |
| `lib/import-parser.ts` | Parseur CSV tolérant + normalisation des parcours |
| `lib/types.ts` | Types du domaine |

Les pages et routes Next.js (obligatoirement sous `src/app`) consomment ce domaine via
`src/lib/get-injs/{seed,generation-service,import-service,queries}.ts`.

## Démarrage

```bash
npm install
npm install xlsx
npx drizzle-kit push
npm run build && npm run start
curl -X POST http://localhost:3000/api/seed
curl -X POST http://localhost:3000/api/generation -H "Content-Type: application/json" \
  -d '{"anneeCode":"2026-2027","inclureSamedi":true}'
```

Interface : `/` (tableau de bord), `/emplois-du-temps`, `/generation`, `/import`, `/etudiants`,
`/referentiels`, `/conception`.

## Import externe (situation 2)

```bash
curl -X POST http://localhost:3000/api/import \
  -F "fichier=@get-injs-app/data/exemple-etudiants-injs.csv" \
  -F "anneeCode=2026-2027" -F "autoCreer=true" -F "generer=true"
```

Colonnes principales : `matricule`, `nom`, `prenom`, `filiere`, `formation`, `niveau`,
`groupe`, `vague`, `semestre`. Les référentiels manquants (filière, formation, vague,
groupe, maquette) sont créés automatiquement.

Documentation téléchargeable : `/api/artifacts/conception?download=1`.
