"""Moteur commun du module « Référentiels » (mission « Référentiels »).

Un seul jeu de comportements pour les 27 référentiels du registre :

* :mod:`colonnes` — découverte des champs exportables et importables ;
* :mod:`exportations` — génération Word, Excel, CSV et PDF ;
* :mod:`importations` — import Excel/CSV en cinq étapes, transactionnel ;
* :mod:`mixins` — branchement de ces comportements sur les ViewSets.

Chaque référentiel conserve ses règles métier propres ; rien n'est dupliqué
et aucune liste de colonnes n'est écrite en dur.
"""
