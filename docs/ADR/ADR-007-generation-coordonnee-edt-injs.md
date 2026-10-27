# ADR-007 — Génération des EDT INJS : orchestration séquentielle déterministe, périmètre dérivé des données

- **Statut :** Accepté (LOT 3, 2026-10-20)
- **Date :** 2026-10-20
- **Décision liée :** DA-09 (complémentarité du moteur natif — voir [ADR-003](ADR-003-edt-externe-et-moteur-natif-complementaires.md)) ; LOT 1 (contrôles C1→C10, conflits inter-EDT), LOT 2 (publication sécurisée)

## Contexte

Les filières INJS d'Abidjan partagent des ressources : un même enseignant couvre
plusieurs formations, une salle est réutilisée, un groupe peut suivre deux UE. Le moteur
`edts.moteur.generation.generate_schedule()` place les besoins d'**un** périmètre dans un
espace d'occupations qui ne voit que le run courant : générer donc les EDT filière par
filière laissait possible des chevauchements C1 (enseignant), C2 (groupe) et C3 (salle)
**entre** EDT, seulement détectés a posteriori par `conflits_inter_edt` (LOT 1).

Trois questions structurent le lot :

1. **Quel périmètre traiter ?** Une liste de formations transmise par le client serait un
   vecteur d'arbitraire : le client pourrait cibler un périmètre arbitraire ou des
   formations hors référentiel INJS (cycles legacy CPFAE / Sygepcpfae).
2. **Quel ordre de traitement ?** Un ordre non déterministe rendrait le résultat
   irreproductible (deux exécutions sur les mêmes données ne donneraient pas le même EDT).
3. **Quelle atomicité ?** Une opération multi-EDT qui échoue en cours de route ne doit
   laisser ni un EDT à moitié écrit, ni un bilan annonçant un succès partiel comme total.

## Décision

1. **Périmètre dérivé des données, jamais de la requête.** `formations_a_planifier()`
   retient les formations du référentiel L6 (`referentiel_injs_l6`) portant des affectations
   pédagogiques `VALIDEE`/`PLANIFIABLE` pour l'année académique visée. La route
   `POST /api/edts/lmd/generate-coordinated/` n'accepte **aucune** liste de formations :
   les cycles legacy n'entrent jamais dans l'opération.

2. **Orchestration séquentielle déterministe.** `edts.moteur.orchestration.generer_coordonne()`
   traite les formations **triées par identifiant croissant**. Chaque run reçoit l'état
   d'occupation global : les placements des runs antérieurs de la même opération **plus**
   les séances persistées des autres EDT de l'année (`occupations_persistees()`). Le moteur
   existant est réutilisé tel quel via un paramètre **additif** `occupations_initiales`
   (défaut `None` ⇒ comportement des LOTS 1 et 2 strictement inchangé). Aucun nouveau
   modèle, aucun solveur parallèle, aucune duplication des contrôles C1→C10.

3. **Atomicité par EDT, bilan global honnête.** Chaque persistance est une transaction
   Django atomique (`transaction.atomic()` + `publication.persister_plan`) : un échec au
   milieu n'écrit rien pour l'EDT concerné, sans masquer la persistance des autres. Le
   statut global (`COORDONNEE_OK` / `COORDONNEE_PARTIELLE` / `COORDONNEE_CONFLITS` /
   `COORDONNEE_IMPOSSIBLE`) et les motifs d'échec sont explicites : **une opération dont un
   seul EDT est incomplet, non persisté ou en conflit n'est jamais présentée comme
   pleinement réussie.**

4. **Idempotence.** `remplacer=True` (défaut) désactive les séances générées antérieures de
   l'EDT cible avant ré-écriture : relancer l'opération ne duplique jamais de séance.

5. **Aucune publication.** L'orchestrateur ne publie pas. Le parcours reste
   `POST /api/edts/lmd/{id}/publish/` (LOT 2), seul chemin vers un EDT publiable.

## Conséquences

- Les chevauchements inter-filières sont **prévenus** au lieu d'être détectés après coup ;
  le contrôle inter-EDT du LOT 1 reste en place comme garde finale (lecture seule).
- Un seul appel API coordonne l'année : le pilotage reste explicite, traçable et borné.
- Le temps de génération croît linéairement avec le nombre de filières (8 formations
  synthétiques, 16 séances placées en ~0,9 s) ; à l'échelle réelle (3 500 étudiants) la mesure
  reste **à établir** — le test de charge livré est volontairement réduit et le dit.
- La coordination est **séquentielle, pas parallèle** : elle privilégie le déterminisme et
  la lisibilité du bilan sur le temps de calcul.
- Le LOT 1 et le LOT 2 ne sont pas modifiés dans leur comportement : `occupations_initiales`
  vaut `None` partout ailleurs.

## Alternatives rejetées

- **Paralléliser les générations par filière.** Rejeté : l'ordre des placements deviendrait
  non déterministe, le bilan difficile à expliquer, et la coordination exigerait un
  mécanisme de résolution de conflits entre runs simultanés — un second solveur, que le
  projet refuse par principe.
- **Accepter une liste de formations dans la requête.** Rejeté : vecteur d'arbitraire et
  porte d'entrée pour cibler des formations hors périmètre INJS ; le périmètre doit
  être dérivé des données validées.
- **Corriger les chevauchements a posteriori (résolution de conflits LOT 1).** Rejeté : la
  correction se paie en temps de secrétariat et en illisibilité du planning ; la
  coordination évite le conflit en amont.
- **Écrire un solveur global (backtracking multi-EDT).** Rejeté : duplication du moteur
  et perte de la référence unique des contrôles C1→C10 et de la traçabilité des refus.
