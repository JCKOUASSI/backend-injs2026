# ADR-002 — Deux domaines financiers distincts, jamais fusionnés

- **Statut :** Accepté (décision d'architecture imposée DA-07, règle métier n°13)
- **Date :** 2026-09-11
- **Décision liée :** DA-07 ; module de référence n°11 (finances étudiantes) et n°12 (direction financière & comptabilité)

## Contexte

Le dépôt porte deux réalités financières sans rapport fonctionnel :

1. **Finances étudiantes** — application `finances_etudiantes` (9 modèles :
   `Tarification`, `Echeancier`, `LigneEcheancier`, `Facture`, `Paiement`,
   `Quittance`, `Remboursement`, `Relance`, `RapprochementComptable`) : frais de
   scolarité LMD perçus auprès des étudiants, rattachés à l'inscription administrative.
2. **Rémunération des formateurs** — modèles `formations.FinanceSettings`,
   `FinanceAjustement` et `NotificationFinanceAjustement` : calcul et ajustement de la
   rémunération horaire des intervenants.

Une opération financière validée n'est jamais supprimée physiquement (annulation,
régularisation ou remboursement uniquement). Le module 12 (comptabilité générale,
budget, engagements, fournisseurs, trésorerie, écritures, rapprochement bancaire)
n'existe pas encore et sera créé dans une application dédiée (`comptabilite`).

## Décision

- Les deux sous-systèmes restent **autonomes** : modèles, écrans, permissions et exports
  strictement séparés.
  - finances étudiantes : écriture/validation par les rôles `FINANCE`, `DIRECTION`
    (et `ADMIN`), lecture étendue au secrétariat (cf. `finances_etudiantes/permissions.py`) ;
  - rémunération des formateurs : reste dans le périmètre `formations`.
- **Aucun modèle, table ou écran ne fusionne les deux.** Le seul lien autorisé est
  **analytique** : une remontée agrégée, en lecture seule, vers le futur module 12.
- La future application `comptabilite` n'écrit pas dans les tables étudiantes ni dans
  `formations.Finance*` ; elle consolide, elle ne duplique pas les écritures.

## Conséquences

- Les workflows (quittances, remboursements, relances d'un côté ; ajustements horaires de
  l'autre) évoluent indépendamment, sans risque de confusion d'écritures.
- Le module 12 peut être construit sans migration de données financières existantes.
- Les permissions restent par domaine ; un même utilisateur peut cumuler des droits sans
  que les modèles ne se rejoignent.

## Alternatives rejetées

- **Une table unique « mouvements financiers » avec un champ discriminant.** Rejeté :
  mélange des créances étudiantes et des dettes envers les formateurs, référentiels
  comptables différents, règle métier n°13 contredite.
- **Rattacher la rémunération des formateurs à `finances_etudiantes`.** Rejeté : fait
  dépendre la paie des intervenants d'un module centré sur les étudiants.
- **Créer la comptabilité générale dans l'application finances étudiantes.** Rejeté :
  la consolidation est un métier distinct (DA-01 prévoit une application `comptabilite`).
