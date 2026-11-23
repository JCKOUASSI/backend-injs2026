# Rapport de seeding

## Cible et sauvegarde

- Cible candidate identifiée : SQLite `/app/db.sqlite3` dans `injs-be-candidate`.
- Année courante préservée : 2026-2027, du 2026-10-01 au 2027-07-31.
- Sauvegarde vérifiée avant les écritures : `/private/tmp/injs-demo-preseed-20261120.sqlite3`; `PRAGMA integrity_check` a renvoyé `ok` dans le conteneur et après copie hors conteneur.
- La commande centrale exige le nom exact de la base, `--appliquer` et `--confirmer DEMO_FICTIVE`.

## Résultats vérifiés

- 16 formations, 40 maquettes actives; 679 UE et 1 055 ECUE pour l’année.
- 5 000 étudiants DEMO (2 500 femmes, 2 500 hommes), 5 000 inscriptions validées et 130 enseignants DEMO.
- 1 055 ECUE couvertes par des affectations pédagogiques.
- GET INJS : 16 EDT publiés, 176 affectations de créneaux, 176 séances prêtes pour Présences, 4 campagnes, 12 salles géolocalisées.
- Autres jeux DEMO : admissions, équivalences (80 demandes), stages (160 conventions), administration, personnel, jurys, diplômation, évaluations (32 évaluations/800 notes brouillon), finances (échéanciers, factures brouillon, paiements non confirmés).
- Les pointages QR n’ont pas été simulés; les secrets de jetons ne sont ni exportés ni consignés.

## Reproductibilité

```sh
python manage.py seed_plateforme_demo --base /app/db.sqlite3
python manage.py seed_plateforme_demo --base /app/db.sqlite3 --effectif 5000 --appliquer --confirmer DEMO_FICTIVE
```

Le premier appel est en lecture seule. Pour les écritures, faire et vérifier une sauvegarde externe. La commande est idempotente; ses contrôles utilisent désormais des seuils de couverture car les volumes dépendent des sources versionnées. Elle inclut `peupler_getinjs_exemples --sans-import` pour créer les EDT et séances sans ajouter une cohorte secondaire.

## Contenu nominatif du classeur

Après approbation explicite, `DATASET_GLOBAL_DEMO.xlsx` inclut les 5 000 lignes de la cohorte fictive `@exemple.ci` (nom, prénom, matricule, sexe, email, groupe/vague) et les inscriptions correspondantes. Téléphones, dates et lieux de naissance, coordonnées, données hors cohorte et secrets QR sont exclus.
