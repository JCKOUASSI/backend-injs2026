# GET INJS APP — Gestion des emplois du temps LMD de l'INJS

Module de génération et de gestion des emplois du temps de l'INJS
d'Abidjan (Marcory, Côte d'Ivoire), intégré à `backend-injs2026`.

## Socle réel de ce dépôt (adaptation documentée)

Le prompt maître décrivait un socle Next.js/Drizzle ; le socle **réel** de
`backend-injs2026` est **Django (API REST) + React** avec une base SQLite
de démonstration (PostgreSQL supporté par les migrations). Conformément à
la directive de l'extension (« réutiliser les modèles existants de
scolarite, formations, admissions, edts »), le module est implémenté dans
l'application Django `edts` et l'interface React existante (`/edt`), sans
dupliquer aucun référentiel. Ce dossier `get-injs-app/` isole les
livrables documentaires et contractuels du module.

## Où vit chaque livrable

| Livrable du prompt | Réalisation dans ce dépôt |
|---|---|
| Référentiels normalisés | Base de données (`scolarite`, `formations`) — source de vérité ; export figé dans `data/referentiel.json` |
| Tables `gi_*` | Tables annexes d'interopérabilité : `gi_seance_registre`, `gi_seance_historique`, `gi_seance_evenement`, `gi_salle_geolocalisation`, `gi_seance_instantane` (migration `edts/0010`) ; les tables GET historiques restent celles de l'app `edts` |
| Domaine pur | `backend/edts/moteur/` (génération déterministe, besoins, contraintes, validation indépendante, import, orchestration, campagnes, interop présences) |
| API | `/api/edts/` (alias `/api/timetable/`) : audit, génération, campagnes, publication, exports CSV/XLSX/PDF, `lmd/conception/`, `interop/…` |
| Interface | React : `/edt`, `/edt/generation-annuelle`, `/edt/campagnes`, `/edt/versions`, `/edt/audit`, `/edt/presences` |
| Santé | `GET /api/health/` → `{status: "ok", database: "ok", timestamp}` |
| Conception téléchargeable | `Conception-GET-INJS.txt` (ce dossier, racine du dépôt et `docs/getinjs/` — copies synchronisées) servi par `GET /api/edts/lmd/conception/` |

## Extension Présences (préparation, pas le module)

GET est la source de référence des séances publiées. L'interopérabilité
avec le futur module de présence (QR Code, pointage manuel,
géolocalisation) est préparée par : identité permanente des séances
(UUID + clé métier), cycle de vie explicite avec historique et
événements, étudiants attendus calculés depuis les groupes, instantanés
historiques, configuration géographique des salles et garde
anti-suppression des séances pointées.

➡️ Voir **`INTEGRATION-PRESENCES.md`** (contrat API, dictionnaire des
données, cycle de vie, matrice des permissions, guide d'intégration).

## Import d'inscrits externes

`modele-import-inscrits.csv` : en-têtes reconnus (alias insensibles aux
accents/casse) — obligatoires : `matricule`, `nom`, `formation`,
`niveau`. Import CSV/XLSX idempotent via `POST /api/edts/lmd/import/inscrits/`
(analyse préalable : `…/import/inscrits/analyser/`).

## Documents

- `Conception-GET-INJS.txt` — conception complète (processus + commandes).
- `PROMPT-MAITRE-GET-INJS.txt` — prompt maître transmis, extension incluse.
- `INTEGRATION-PRESENCES.md` — livrables architecturaux de l'extension.
- `data/referentiel.json` — photographie des référentiels en base.
