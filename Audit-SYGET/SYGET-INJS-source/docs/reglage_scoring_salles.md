# Reglage du scoring des salles (Planning v2)

Document court pour regler le choix automatique des salles dans la generation des seances.

## 1) Objectif

Le moteur de planning choisit une salle candidate en combinant 3 criteres:

- proximite de capacite avec l'effectif du groupe
- rotation des salles pour un meme module
- equilibrage global d'usage des salles

Le moteur garde les regles metier existantes:

- site obligatoire
- pas de conflit horaire sur une salle
- pas de meme module le meme jour sur 2 groupes
- un seul module par jour pour un groupe
- respect du max de seances par jour

## 2) Parametres disponibles

Dans les Parametres generaux:

- `poids_score_ecart_capacite`
- `poids_score_rotation_module`
- `poids_score_equilibrage_global`

Plus un poids est eleve, plus le critere influence le choix final.

## 3) Presets recommandes

### A. Conservateur (priorite capacite)

- `poids_score_ecart_capacite = 12`
- `poids_score_rotation_module = 2`
- `poids_score_equilibrage_global = 1`

Usage: limiter le gaspillage de grandes salles.

### B. Equilibre (recommande)

- `poids_score_ecart_capacite = 10`
- `poids_score_rotation_module = 4`
- `poids_score_equilibrage_global = 2`

Usage: bon compromis entre capacite, rotation et repartition.

### C. Rotation forte (anti-redondance)

- `poids_score_ecart_capacite = 6`
- `poids_score_rotation_module = 10`
- `poids_score_equilibrage_global = 4`

Usage: alterner les salles autant que possible.

## 4) Grille d'ajustement rapide

- meme salle trop souvent pour un module:
  - augmenter `poids_score_rotation_module` de `+2`
- une salle surchargee globalement:
  - augmenter `poids_score_equilibrage_global` de `+1` ou `+2`
- petits groupes dans de tres grandes salles:
  - augmenter `poids_score_ecart_capacite` de `+2`
- alternance trop forte (besoin de stabilite):
  - baisser `poids_score_rotation_module` de `-2`
- capacite trop dominante:
  - baisser `poids_score_ecart_capacite` de `-2`
  - augmenter `poids_score_equilibrage_global` de `+1`

## 5) Procedure de reglage (3 cycles)

1. Demarrer a `10 / 4 / 2`.
2. Observer 1 cycle de generation (ou 1 vague) puis ajuster un seul poids a la fois.
3. Stabiliser les valeurs 1 a 2 vagues avant un nouveau changement.

Regle pratique: eviter les sauts > 30% d'un coup.

## 6) Symptomes et actions

- Trop de redondance de salle:
  - priorite a `rotation_module`
- Trop de gaspillage de capacite:
  - priorite a `ecart_capacite`
- Trop de concentration sur certaines salles:
  - priorite a `equilibrage_global`

## 7) Valeurs de depart conseillees

Pour CPFAE, commencer par:

- `poids_score_ecart_capacite = 10`
- `poids_score_rotation_module = 4`
- `poids_score_equilibrage_global = 2`

Puis ajuster selon les symptomes observes.
