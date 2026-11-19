# Recette des dix espaces INJS — trame à exécuter

**Classeur à renseigner :** [`Recette_Validation_10_Hubs_INJS_2026.xlsx`](Recette_Validation_10_Hubs_INJS_2026.xlsx). Il est distinct du classeur de suivi du manuel utilisateur. Aucun cas n'est exécuté à la livraison, aucune pièce n'est jointe et aucune validation n'est signée.

## Périmètre à confirmer avant le visa

La liste des **dix Hubs** est une proposition établie à partir du code : huit composants explicitement nommés `*Hub.jsx` (Présences QR, Évaluations, Jurys, Diplômation, Finances étudiantes, Stages, Personnel, Administration) et les deux espaces transversaux Tableau de bord et Scolarité. Ce n'est **pas** une nomenclature institutionnelle attestée. Le responsable de recette doit confirmer ou corriger ce périmètre avant tout visa.

Les entrées de menu « Contrôle des dossiers », « Résultats concours », « Directions », « Départements » et « Services » n'ont pas de route correspondante dans `frontend/src/App.jsx` : le point d'entrée parent est proposé, et l'absence de fonction doit être consignée comme blocage ou non-applicabilité justifiée, **jamais comme succès**. Une route ou un onglet trouvé dans le code ne prouve pas le fonctionnement en conditions réelles.

## Exécution et preuves

1. Dans **Cas de recette**, filtrer par Hub ; une ligne représente un scénario rattaché à une fonctionnalité. Préparer un environnement isolé, un jeu de données autorisé, une version et un compte habilité. Exécuter les étapes indiquées et comparer le résultat attendu au résultat observé.
2. Saisir le statut déroulant, le testeur, la date, l'environnement/version, le résultat observé, le ticket éventuel et la référence de la preuve. Conserver la pièce réelle dans le référentiel officiel **hors du classeur**, avec accès maîtrisé ; le chemin inscrit ne constitue pas une preuve vérifiée à lui seul. Ne pas joindre de secrets ni de données personnelles non expurgées.
3. **Progression** ne compte comme réussite que les lignes « Réussi » avec date, testeur, environnement, résultat observé et référence de preuve. **Bilan par Hub** n'affiche « Visa recevable* » qu'après réussite documentée de tous les cas du Hub et saisie de la décision, du signataire, de la date et de la référence du PV signé. Le contrôle final de la réalité des pièces et de l'authenticité des signatures reste humain.
4. Un résultat « Bloqué », « Échec » ou « Non applicable » n'est pas une validation. Réviser le périmètre et décider des réserves en dehors du classeur, sans forcer le statut à « Réussi ».

**Important :** le générateur `scripts/produire_recette_hubs_2026.py` crée une trame vierge et **refuse d'écraser** ce fichier une fois créé. Ne pas remplacer une recette commencée par une nouvelle trame. Ouvrir le fichier dans un tableur qui recalcule les formules (Excel/LibreOffice) : `openpyxl` ne les évalue pas. L'ancienne copie livrée sous `dossier_trvx/Manuel_utilisateurs/` n'est pas le fichier de travail de ce nouveau dossier.
