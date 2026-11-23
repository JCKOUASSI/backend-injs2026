# Guide de démonstration

## État préparé

La base candidate SQLite contient une cohorte de 5 000 étudiants fictifs, les maquettes et affectations pédagogiques de l’année 2026-2027, 16 EDT publiés, 176 séances et 12 salles géolocalisées. Le classeur `DATASET_GLOBAL_DEMO.xlsx` contient les fiches de la cohorte DEMO et ses inscriptions autorisées, sans téléphone ni date de naissance.

## Parcours conseillé

1. Depuis le menu, ouvrir **Référentiels**, puis **Scolarité** pour montrer formations, niveaux, maquettes et UE/ECUE.
2. Ouvrir **GET INJS APP → Campagnes**, consulter la campagne prête, ses contrôles et le lancement automatique.
3. Ouvrir `/edt` et `/edt/generation-annuelle` pour inspecter la génération et le placement manuel.
4. Ouvrir `/presences/seances` pour retrouver les séances publiées; `/presences/poste` sert au badgeage; `/presences/registre` au suivi.
5. Pour une démonstration QR réelle, choisir une occurrence dont la date/heure est dans la fenêtre de badgeage et utiliser un compte autorisé. Les scénarios automatisés valident le scan, l’entrée/sortie, le heartbeat, la géofence, l’autocloture et la correction manuelle.
6. Montrer ensuite les hubs Admissions, Évaluations, Jurys, Stages, Diplômation, Finances et Administration.

Les rôles et capacités de l’utilisateur connecté filtrent les écrans et actions. La génération ne vaut pas validation ni publication.
