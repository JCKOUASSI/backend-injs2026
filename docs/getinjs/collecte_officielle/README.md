# Données institutionnelles requises avant recette annuelle et déploiement

Ces modèles sont **vides** : ils ne constituent ni un calendrier validé ni des volumes pédagogiques. Les remplir uniquement à partir de documents approuvés par l'INJS, avec la référence et la fonction du valideur. Ne pas transférer ici de noms d'étudiants, de jetons, de mots de passe ou de fichiers `.env`. Remplir une **copie hors du dépôt** et la remettre par canal institutionnel sécurisé : ne pas commiter la version renseignée (les CSV sont normalement ignorés par Git).

## 1. Volumes par ECUE

Modèle `volumes_ecue_officiels.csv.template.txt` (à copier hors dépôt en `.csv`) : une ligne par ECUE et par année/formation/niveau/semestre ; heures **CM, TD, TP** distinctes, y compris les zéros confirmés. Une valeur vide signifie « non fournie », pas zéro. Le stage a sa propre colonne de collecte mais son mode de planification reste à arbitrer : ne pas le convertir automatiquement en TP. Fournir la maquette approuvée et la page de chaque ligne. Les crédits ECTS ne permettent pas de déduire les heures.

Le classeur du dépôt `dossier_trvx/INJS D'ABIDJAN — RÉFÉRENTIEL EXHAUSTIF DE L'OFFRE DE FORMATION2.xlsx` documente des UE/ECUE et des crédits ; la feuille « 8. Base UE (source TCD) » n'a pas de colonnes d'heures CM/TD/TP. `dossier_trvx/Modéliser les volumes horaires au niveau “Formation → Catégorie → Module”.txt` se présente lui-même comme **proposition non certifiée** : interdiction de le charger comme volume officiel.

## 2. Calendrier par semestre

Modèle `calendrier_semestres_officiel.csv.template.txt` (à copier hors dépôt en `.csv`) : une ligne par semestre/niveau/année avec dates de début et fin, semaines académiques d'enseignement effectivement ouvertes, interruptions et référence du calendrier approuvé. La `date_debut` de l'année et le numéro du semestre ne suffisent pas à calculer S1/S2. Les semaines ne doivent pas être attribuées par simple moitié d'année. Documenter la règle des jours fériés, des séances annulées ou reportées et du rattrapage, sans modifier les séances déjà pointées sans arbitrage.

**Avant toute ingestion :** rapprocher les identifiants des ECUE et des niveaux des maquettes actives, contrôler l'unicité et la couverture des deux semestres de chaque niveau, les totaux d'heures, les plages disjointes et les interruptions. Rejouer la génération sur une copie isolée fidèle de la base réelle ; vérifier les occurrences/heures effectivement persistées, zéro conflit enseignant/groupe/salle, les effets sur QR et les statuts de chaque campagne. Ne pas basculer d'anciennes campagnes en `VALIDE` par modification de statut.

## 3. Essais de terminaux QR physiques

La suite automatisée et les appareils simulés ne remplacent pas une recette physique. Pour chaque terminal réellement utilisé (modèle/OS/version applicative consignés **sans identifiant privé**), tester avec des comptes habilités et des séances de recette : QR actif, remplacé, expiré, scan simultané, double tap inférieur au seuil, entrée puis sortie, coupure et retour réseau, GPS absent/imprécis/hors zone, appartenance au groupe, droits enseignant/encadrant, et séance hors calendrier. Conserver le code HTTP et le code métier, l'heure locale, le résultat attendu/observé et un identifiant de preuve anonymisé. Exécuter sur un environnement de recette ou après validation explicite d'un protocole non destructif sur le site ; ne pas produire de pointages factices en production.

## 4. Porte de déploiement

Le domaine visé est `injs.badge-qr-code.pro`. Aucune bascule tant que les données institutionnelles, la recette réelle et la CI du SHA cible ne sont pas validées ; la PR n'est pas fusionnée et aucune image de ce SHA n'a été prouvée publiée depuis `main`. L'installation `/opt/injs/injs-lmd` n'était pas présente dans l'inventaire VPS transmis ; la cible du proxy et les sauvegardes restaurables de la base réellement servie restent à prouver. Le déclenchement du workflow `deploy-injs-lmd.yml` en mode **preflight** sur la branche courante a retourné `HTTP 403 Resource not accessible by integration` ; il n'a rien exécuté sur le VPS. Ne pas contourner ce refus ni déployer à la main depuis une arborescence supposée. Une fois les prérequis prouvés, suivre `deploy/production/RUNBOOK.md` : inventaire, sauvegarde vérifiée, plan de migration, images immuables, validation sur port parallèle, recette, puis bascule proxy explicite et retour arrière disponible.
