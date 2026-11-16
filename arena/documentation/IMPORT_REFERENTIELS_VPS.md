# Import des référentiels sur le VPS — précaution calendrier

**Ne pas lancer** `python manage.py importer_referentiels_injs` sans option sur la base `injs_lmd_prod_20261026` : la simulation a montré qu'il modifierait l'année académique courante. Son calendrier présent sur le VPS est `2026-01-01 → 2027-11-30`, tandis que le document importé prévoit `2026-10-01 → 2027-07-31`. Il modifierait aussi les codes des trois vagues (initialement vides). L'import ajoute également des valeurs explicitement marquées `MODELISE` ou `CADRAGE` : elles ne doivent pas être présentées comme des décisions institutionnelles validées.

Le nouvel argument `--preserver-calendrier` évite **toute création et toute modification** dans `scolarite.AnneeAcademique`, tout en conservant l'import des autres nomenclatures. Il n'est utilisable sur le VPS **qu'après déploiement vérifié d'une image backend contenant ce changement** : le fichier présent sur le poste local ne modifie pas automatiquement le conteneur `injs-be-next`. Ne pas remplacer une image en production sans suivre le processus de déploiement et de revue des migrations.

## Vérifications avant l'import réel

1. Confirmer le routage du domaine vers `injs-fe-next`, puis `/api` vers `injs-be-next`, et la base de celui-ci (`injs_lmd_prod_20261026` sur `injs-db`).
2. Conserver hors Git une sauvegarde `pg_dump -Fc` de cette base et vérifier `pg_restore -l` ainsi que sa taille et son empreinte SHA-256. Le dump contient des données privées.
3. Après déploiement contrôlé, vérifier la présence de l'option :

   ```sh
   docker exec injs-be-next python manage.py help importer_referentiels_injs
   ```

4. Effectuer d'abord la simulation **avec la nouvelle option** et contrôler que la ligne `annees_academiques` affiche « préservées » :

   ```sh
   docker exec injs-be-next python manage.py importer_referentiels_injs --preserver-calendrier --dry-run
   ```

5. Après revue humaine des mises à jour des trois vagues et de la provenance des valeurs de cadrage/modélisées, lancer éventuellement l'import réel avec la **même option**, puis contrôler cohérence, années et vagues :

   ```sh
   docker exec injs-be-next python manage.py importer_referentiels_injs --preserver-calendrier
   docker exec injs-be-next python manage.py verifier_coherence_referentiels
   ```

**Ne pas lancer** `arena/remplir-base-locale.py`, `seed_data.py`, `finaliser_maquettes_injs` ni les `seed_*_demo` sur cette base de production. Pour voir des dossiers, étudiants et notes fictifs, créer une base de démonstration isolée avec des comptes distincts, après vérification du routage, plutôt que polluer la base active.
