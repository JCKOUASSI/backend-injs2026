# ADR-003 — Emploi du temps : contrat externe conservé, moteur natif complémentaire

- **Statut :** Accepté (décision d'architecture imposée DA-09)
- **Date :** 2026-09-11
- **Décision liée :** DA-09 ; module de référence n°06 (emplois du temps)

## Contexte

Deux dispositifs coexistent :

- **Un planificateur externe** (`app-ept-injs-lmd 2026`) déjà utilisé, alimenté par un
  **contrat de données strictement en lecture seule** exposé par le backend :
  `GET /api/scolarite/edt/` (`contrat`, `groupes/`, `enseignements/`, `etudiants/`,
  `indisponibilites/`, `creneaux/`, `affectations/`, `espaces/<id>/occupation/`),
  avec export JSON/CSV (voir `backend/scolarite/edt_export.py` et `scolarite/urls.py`).
  Le paramètre `edt_source_externe` est verrouillé dans le seed
  (`parametres/migrations/0003_categories_mvp_seed.py`, non modifiable).
- **Une application native `edts`** partielle : `CreneauTemplate`, `EmploiDuTemps`,
  `AffectationCreneau`, `ConflitCreneau` (services de détection de conflits), qui doit
  accueillir au LOT 6 un moteur de **génération automatique** de brouillons avec
  contraintes et workflow de validation.

La tentation serait de remplacer l'outil externe par le moteur natif, ou à l'inverse de
ne rien développer en natif.

## Décision

1. Le **contrat externe v1.1 est conservé, versionné et reste strictement en lecture
   seule** : l'application externe ne peut pas écrire dans le backend via ce contrat.
2. Le **moteur natif est complémentaire, pas concurrent** : il produit des **brouillons**
   d'emploi du temps (`BROUILLON → GÉNÉRÉ → À CONTRÔLER → VALIDÉ → PUBLIÉ → ACTIF`) qui
   doivent être validés par un rôle habilité ; les emplois du temps actifs continuent de
   provenir de l'ingestion/du planificateur externe tant que la bascule n'est pas actée.
3. Le retour de l'outil externe vers l'application reste un **import manuel Excel**
   (`ImportExcel.jsx`), pas une API d'écriture temps réel.
4. Les deux lectures s'appuient sur les mêmes sources de vérité (`Groupe`, `Module`,
   `SessionModule`, `AffectationGroupe`, `InscriptionPedagogique`) afin d'éviter tout
   écart de jeu de données.

## Conséquences

- Aucune régression pour les planifications déjà produites par l'outil externe.
- Le moteur natif peut être développé et testé sans impacter les séances actives ; il ne
  devient source d'emplois « actifs » qu'après validation explicite et feu de bascule
  (DA-06, DA-12).
- Le contrat doit rester stable et documenté (versionnement des colonnes/endpoints).

## Alternatives rejetées

- **Rendre le contrat d'échange bidirectionnel (écriture depuis l'outil externe).**
  Rejeté : contournement des permissions et du workflow de validation, risque d'écritures
  non journalisées.
- **Abandonner le moteur natif et dépendre uniquement de l'outil externe.** Rejeté :
  dépendance externe pour une fonction cœur, pas de génération assistée ni d'explication
  des conflits.
- **Imposer le moteur natif dès sa livraison et débrancher l'externe.** Rejeté : contredit
  DA-12 (retrait/bascule en dernier, après observation) et la pratique des utilisateurs.
