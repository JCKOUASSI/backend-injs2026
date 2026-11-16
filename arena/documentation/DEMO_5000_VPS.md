# Démonstration complète sur le VPS de test

Le domaine `injs.badge-qr-code.pro` a été explicitement déclaré **environnement de test** par son propriétaire. Le remplissage n'est autorisé qu'après sauvegarde complète vérifiée de la base réellement utilisée (`injs_lmd_prod_20261026`) et vérification du routage public. Ne jamais lancer `seed_data.py` sur cette base : ce script réinitialise des comptes existants à des mots de passe connus.

## Portée et chiffres vérifiés sur SQLite isolée

`seed_plateforme_demo` enchaîne les commandes versionnées des référentiels LMD, maquettes, charges pédagogiques, admissions, équivalences, journal de scolarité, stages, administration, personnel, jurys, diplômation, évaluations et finances. L'import préalable des référentiels généraux a déjà été fait avec `--preserver-calendrier`. Les données officielles et les valeurs modélisées restent distinguées par leur provenance. Le calendrier 2026-2027 déjà défini (`2026-01-01 → 2027-11-30`) reste inchangé.

Sur une base de test isolée et neuve avec cette année et les référentiels importés, un passage puis un second passage idempotent ont donné : **16 formations**, **40 maquettes actives**, **531 UE**, **779 ECUE**, **8 niveaux**, **16 parcours**, **16 semestres**, **4 types de formation**, **5 000 étudiants fictifs inscrits** (2 500 femmes et 2 500 hommes), **99 enseignants fictifs** créés selon le plafond de 192 h/an, et **779 ECUE affectées**. Les 25 inscriptions *scénarios Admissions* créées en plus par le module sont distinctes de la cohorte des 5 000 ; si le besoin est **exactement 5 000 inscriptions toutes catégories confondues**, il faut adapter le périmètre avant exécution. Aucun nombre arbitraire d'enseignants ne peut être qualifié de « maximum » : ici ils sont créés jusqu'à couvrir toutes les ECUE sans dépasser le plafond de charge.

Les comptes d'enseignants fictifs générés par la nouvelle version ont un **mot de passe inutilisable** (pas d'identifiant public partagé). Les scénarios financiers gardent des barèmes inactifs et des paiements non confirmés.

## Déploiement, sauvegarde et exécution

**Ne pas utiliser l'ancienne image** `injs-be:calendrier-a21b9c2` : elle ne contient pas l'orchestrateur ni le paramètre `--effectif 5000`. Construire une nouvelle image backend et une image frontend depuis un **commit immuable** de la branche mise à jour. Ne pas écraser `injs-be-next`/`injs-fe-next` par une commande improvisée : le frontend public doit être déployé lui aussi pour afficher les trois liens « Gérer ». Avant toute modification de la pile, relever ports, réseaux, variables, commandes de démarrage et configuration proxy (sans divulguer les secrets), puis tester les nouvelles images en parallèle.

Avant `--appliquer` : refaire un `pg_dump -Fc` de `injs_lmd_prod_20261026`, vérifier `pg_restore -l`, `sha256sum`, l'espace libre et les médias existants ; ne pas rendre le dump public. Si des étudiants fictifs de **3 500** sont déjà présents, l'orchestrateur refuse de les mélanger aux **5 000** : ne pas purger sans étude des dépendances.

Avec l'image backend à jour, sa configuration DB d'origine et un conteneur conservé jusqu'à la copie des médias :

```text
python manage.py seed_plateforme_demo --base injs_lmd_prod_20261026
python manage.py seed_plateforme_demo --base injs_lmd_prod_20261026 --effectif 5000 --appliquer --confirmer DEMO_FICTIVE
python manage.py seed_plateforme_demo --base injs_lmd_prod_20261026
python manage.py verifier_coherence_referentiels
```

La première commande ne fait qu'un état des lieux. Le remplissage est réexécutable mais **pas atomique sur l'ensemble des modules** ; si une étape échoue, ne pas relancer aveuglément, vérifier le bilan puis corriger. Les pièces des dossiers Admissions sont écrites dans `/app/media` du **conteneur qui exécute le seed** : si ce conteneur est jetable sans volume commun, les fichiers seront perdus malgré les références en base. Le conserver et copier ses médias vers le conteneur web ou, mieux, partager un volume média persistant avant le seed. Ne supprimer le conteneur temporaire qu'après vérification de ces fichiers. Ne pas afficher de `.env`, de mots de passe ou de dump dans le chat.
