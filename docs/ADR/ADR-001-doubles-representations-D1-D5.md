# ADR-001 — Traitement des doubles représentations D1 à D5

- **Statut :** Accepté (décision d'architecture imposée, reprise dans DA-02)
- **Date :** 2026-09-11
- **Décision liée :** DA-02 (une seule source de vérité par objet)
- **Documents de référence :** [CARTOGRAPHIE_CIBLE_INJS_LMD.md](../CARTOGRAPHIE_CIBLE_INJS_LMD.md), [BASELINE_2026-09.md](../audits/BASELINE_2026-09.md)

## Contexte

L'audit a mis en évidence cinq zones où une même notion métier est représentée deux
fois dans le code existant (socle « formation continue » historique d'une part, socle
LMD d'autre part) :

| # | Notion | Représentation LMD (cible) | Représentation historique |
|---|--------|----------------------------|---------------------------|
| D1 | Groupes | `scolarite.Groupe` + `AffectationGroupe` | `formations.Participant.groupe` et `Module.groupe` (texte libre) |
| D2 | Catégorisation d'un participant | `RefCategorie`, `RefGrade`, `RefVague`, `RefSite`, `RefSalle` (clés étrangères) | champs texte legacy (`categorie`, `grade`, `vague`, `site`, `salle`, …) sur `Participant` |
| D3 | Formation | `formations.RefFormation` (référentiel), déjà référencée par `Maquette.ref_formation` et `Groupe.ref_formation` | `formations.Formation` sans clé étrangère vers `RefFormation` |
| D4 | Notes / ECUE | `scolarite.ECUE` (passerelle vers `RefModule`) | `formations.NoteModule` non rattaché à l'ECUE |
| D5 | Finances | `finances_etudiantes` (frais de scolarité LMD) | `formations.FinanceSettings` / `FinanceAjustement` (rémunération des formateurs) — voir ADR-002 |

L'application est en service : aucune de ces zones ne peut subir de bascule brutale
(règle « ne pas détruire l'existant », migrations réversibles uniquement).

## Décision

1. **Une seule source de vérité par objet** : la représentation LMD référentielle
   (`scolarite.*`, les `Ref*`, `ECUE`, `RefFormation`) devient la source de vérité.
2. **Ponts additifs et nullables** : la convergence passe par des clés étrangères
   ajoutées sans contrainte cassante (ex. `Formation.ref_formation` nullable), jamais
   par suppression ou réécriture des champs historiques.
3. **Affichage dual temporaire** : le temps de la migration, les écrans peuvent afficher
   la valeur référentielle et, en repli, le texte legacy ; celui-ci passe en lecture
   seule (jamais saisi de nouveau).
4. **Migration progressive des données** texte → clé étrangère, par lots réversibles et
   derrière feu de bascule (DA-06), avec commandes de vérification en lecture.
5. D4 (rattachement `NoteModule → ECUE`) et le verrouillage des notes sont des
   prérequis du module Jurys ; D5 fait l'objet de l'ADR-002 (les deux finances restent
   séparées, il ne s'agit pas d'une fusion).

## Conséquences

- Les modèles et écrans legacy restent en place et fonctionnels pendant toute la
  transition ; aucun écran ni aucune importation Excel historique n'est cassé.
- De nouveaux garde-fous d'unicité référentielle sont ajoutés (cf. ADR-006 sur
  l'anti-doublon de libellé insensible à la casse).
- La suppression effective des champs texte legacy n'intervient qu'en fin de course,
  après bascule vérifiée et fenêtre d'observation (DA-12).

## Alternatives rejetées

- **Big-bang : supprimer les champs legacy et migrer les données en une fois.** Rejeté :
  risque d'interruption de service, imports Excel et écrans existants cassés, retour
  arrière impossible.
- **Tout laisser en double sans désigner de source de vérité.** Rejeté : incohérences
  durables, impossibilité de calculer l'ECTS (D4) et de fiabiliser les statistiques.
- **Fusionner les deux modèles de finance (D5).** Rejeté explicitement (ADR-002 / DA-07) :
  des domaines comptables distincts ne doivent pas partager un même modèle.
