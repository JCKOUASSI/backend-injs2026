# Guide de seeding DEMO

1. Confirmer que la cible est une base locale/candidate DEMO et relever son nom exact.
2. Réaliser une sauvegarde cohérente hors conteneur et vérifier son intégrité.
3. Exécuter d’abord la commande sans `--appliquer` pour inspecter les volumes.
4. Pour écrire, fournir le nom exact avec `--base`, choisir un effectif pair et préciser `--appliquer --confirmer DEMO_FICTIVE`.
5. Vérifier les compteurs imprimés et l’année courante inchangée.

La commande centrale est `seed_plateforme_demo`. Elle exécute dans l’ordre les seeds de référentiels, maquettes/charges, admissions/inscriptions, GET INJS, équivalences, stages, administration/personnel, jurys/diplômation, évaluations et finances. Le module GET INJS est créé par l’API officielle et non par insertion directe de placements.

Ne pas exécuter en production. Aucun reset global n’est fourni.
