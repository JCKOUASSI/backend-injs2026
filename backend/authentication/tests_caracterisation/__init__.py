"""Tests de CARACTÉRISATION de l'unité U0 (chantier CURP-INJS).

Ces tests ne décrivent aucun comportement SOUHAITÉ : ils figent le
comportement EXISTANT du dispositif d'habilitation au démarrage du chantier,
pour garantir que les unités ultérieures (U1+) ne font pas dériver
silencieusement le socle (règle S2 : zéro élargissement silencieux).

Ils sont volontairement isolés dans un paquet dédié afin de ne jamais
modifier les tests existants (règle R5). Tout écart constaté pendant U1+ fera
échouer un test de ce paquet ; le correctif doit alors être EXPLICITE et
documenté.

Modules :
* test_01_referentiel_roles  — les 12 rôles, ensembles, politique, groupes ;
* test_02_synchronisation_groupes — signaux Django (groupes ROLE_*, is_staff) ;
* test_03_canaux_connexion   — web (10 rôles) vs mobile (2 rôles), cookie,
  verrouillage appareil, limitation de débit ;
* test_04_permissions_effectives — permissions Django dérivées de ROLE_POLICY ;
* test_05_cloisonnement_secretariats — filtrage par périmètre (formations.access) ;
* test_06_endpoints_reference — me / roles / capabilities (lecture seule).
"""
