"""Lot L8 (GET-INJS) — Moteur d'emploi du temps.

Paquet de services métier, **découplé de l'API HTTP** (étape 7). Le moteur
historique `edts/services.py` (détection de conflits, grille, brouillon P06)
est conservé tel quel : ce paquet le complète sans le modifier.

    besoins.py      ECUE → volume → type → groupe = TeachingNeed traçable
    contraintes.py  C1→C10 dures (bloquantes) + pénalités souples (K)
    generation.py   backtracking déterministe + heuristique de difficulté
    validation.py   audit de couverture / conflits / volumes / capacités
    publication.py  publication transactionnelle, idempotente, verrouillée

Aucun de ces services n'invente de donnée : il ne fait que lire la chaîne LMD
réelle et la qualifier. En l'absence de données métier, chaque service renvoie
une **cause de blocage explicite** (voir `besoins.MOTIF_*`) — jamais de repli
ni d'horaire fictif (arbitrage du commanditaire, 2026-09-28).

Chaîne canonique (aucune table `Promotion` — `Groupe` porte la promotion) :
    Année → Formation → Parcours → Niveau → Semestre → Groupe → Maquette
    → UE → ECUE → AffectationPedagogique → TeachingNeed → Séance planifiable
"""
