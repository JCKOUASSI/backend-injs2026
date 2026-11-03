# Peuplement des référentiels INJS — journal d'exécution (03/11/2026)

Base de démonstration remplie à partir des documents du dossier
`dossier_trvx` (dont « Formations et Modules INJS », « Vagues INJS 2026 »,
le classeur « RÉFÉRENTIEL EXHAUSTIF DE L'OFFRE DE FORMATION », le « RÉFÉRENTIEL
COMPLET DU SYSTÈME LMD » et le PDF « Referentiels_de_l_INJS_Tableau_de_bord »),
en respectant le registre du module « Référentiels »
(`backend/referentiels/registre.py` : 27 référentiels, 7 catégories).

> La base SQLite (`backend/db.sqlite3`) est ignorée par Git : ce journal est
> la trace versionnée de l'opération. Les quatre commandes ci-dessous sont
> idempotentes et rejouables sur toute base neuve.

## Chaîne exécutée (dans l'ordre prescrit par les commandes)

```bash
cd backend
.venv/bin/python manage.py init_referentiels_lmd
.venv/bin/python manage.py importer_referentiels_injs
.venv/bin/python manage.py configurer_referentiel_injs --annee 2026-2027
.venv/bin/python manage.py completer_referentiel_lmd --annee 2026-2027
```

## Résultat — `GET /api/referentiels/tableau-de-bord/`

27 référentiels · **1104 valeurs** · 0 à renseigner · 0 sans source ·
traçabilité 100 % (identique au PDF de référence du 02/11/2026).

| Référentiel | Valeurs | Référentiel | Valeurs |
|---|---:|---|---:|
| Mentions (STAPS/STASE) | 2 | Types d'enseignement (CM/TD/TP/stage) | 4 |
| Écoles (ENSEPS/ENSEP) | 2 | Types d'espace sportif | 18 |
| Filières (8 officielles) | 8 | Types d'évaluation | 20 |
| Natures de cursus | 5 | Types de décision (jury) | 4 |
| Formations — cycles Licence/Master | 16 | Grades enseignants | 28 |
| Modules officiels des maquettes | 227 | Bâtiments | 16 |
| Volumes horaires (modélisation) | 51 | Salles et espaces | 166 |
| Niveaux L1→D3 (60 ECTS/an) | 8 | Sites (INJS Marcory) | 1 |
| Parcours (8 filières × L/M) | 16 | Statuts de vague | 5 |
| Semestres S1→S16 (30 ECTS) | 16 | Vagues | 3 |
| Types de formation (hérité) | 4 | Années académiques | 8 |
| UE (maquettes, + 407 ECUE) | 331 | Modes de paiement | 14 |
| Types de document | 56 | Types de frais | 28 |
| Types de notification | 47 | | |

## Contrôles passés

- `verifier_coherence_referentiels` : aucun constat (provenance complète,
  filières alignées, 16/16 formations rattachées).
- `verifier_doublons_referentiels` : aucun doublon (ADR-006).
- `controler_referentiel_injs` : seuls écarts = la maquette **MS-S8**
  (8 UE / 10 ECUE / 30 ECTS) issue du PDF §8.3, absente du classeur officiel
  publié — reconstitution **à confirmer par la DENSEPS**, documentée comme telle.
- Idempotence : seconde exécution complète = 0 création.
- Tests `referentiels` : OK.

## Réserves métier (rien n'a été inventé)

- Filières ENSEP F05–F08 (Andragogie, Loisir, EJCP, Gérontologie) : cycles
  Licence/Master créés en coquilles, **sans maquette** (UE/ECUE non publiés).
- Volumes horaires : fiabilité **MODELISE** (proposition du document de
  cadrage, jamais réglementaire) ; bloc « Maître(sse) d'EPS » exclu (hors INJS).
- Bâtiments/salles : inventaire **MODELISE** de la source.
- Maquettes importées en statut **BROUILLON** : ni validation ni activation
  automatiques (décision institutionnelle).
- Écart avec les captures fournies (1304 valeurs / UE-ECUE 531) : +200 UE
  correspondent aux maquettes **[Exemple]** que `finaliser_maquettes_injs`
  génère pour F05–F08 — données de démonstration, volontairement non créées
  ici pour ne pas fabriquer un référentiel non publié.
