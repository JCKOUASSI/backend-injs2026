# ADR-005 — Conservation de l'arborescence Django « à plat » et des noms techniques hérités

- **Statut :** Accepté (décision d'architecture imposée DA-01)
- **Date :** 2026-09-11
- **Décisions liées :** DA-01 (arborescence), DA-12 (retrait du legacy en dernier), DA-06 (feux de bascule)

## Contexte

La cible idéale propose une arborescence hiérarchique `backend/apps/{core, identity,
students, …}` avec ~20 applications regroupées par domaine. Le dépôt réel contient au
contraire **20 applications métier disposées à plat** sous `backend/` avec une
nomenclature française (`formations`, `scolarite`, `presences`, `finances_etudiantes`,
`ressources_humaines`, …), déjà peuplées d'environ 184 migrations, de nombreux imports
absolus et plus de 900 tests.

Par ailleurs, de nombreux **identifiants techniques** portent encore des sigles ou des
noms d'anciennes versions du produit :

- dossier du client mobile `qr_badge_mobile/`, noms d'images et de conteneurs Docker
  `qr-badge-*`, image de CI `sygep-backend-ci`, nom de base PostgreSQL par défaut
  `qr_badge` ;
- classes de permission `IsDFRC`, `IsSecretariatOrDFRC`, … et membres d'énumération
  (`Pointage.Statut.FORCE_DFRC`) ;
- socle HTML legacy (`dashboard/views_legacy.py`, templates de badgeage,
  `static/sw.js` « qr-badge-v3 »), CSS d'administration, courriels transactionnels
  estampillés de l'ancien nom, fichiers et URL de pages légales ;
- les clés de rôles `CPFAE_ADMIN` / `CHEF_CPFAE_ADMIN` (les 12 rôles sont figés par DA-05).

## Décision

1. **Aucune application existante n'est renommée ni déplacée.** On conserve la structure à
   plat et la nomenclature française. Les applications manquantes sont **créées sur place
   selon cette nomenclature** (`core`, `comptabilite`, `notifications`, `portails`) ; la
   table de correspondance modules ↔ apps de
   [ARCHITECTURE.md](../ARCHITECTURE.md) est la carte officielle.
2. **Aucun identifiant technique hérité n'est renommé pendant la phase documentaire
   (P00-03)** : un tel renommage touche au code, aux migrations, aux permissions, à la CI,
   aux images, aux canaux de publication des stores et aux URLs externes. Il ne peut être
   fait que par petits lots réversibles, derrière feu de bascule (DA-06), avec mise à jour
   simultanée des données et des droits.
3. La **documentation et les libellés visibles**, eux, basculent immédiatement en
   terminologie INJS-LMD (titres, descriptions, manifestes/PWA, textes de préparation de
   magasin, fichiers d'exemple `.env`) ; les seules occurrences conservées hors archive
   sont des identifiants de code/infrastructure et les documents d'audit qui les citent
   pour être exacts.
4. Le retrait du socle legacy (HTML, service worker, écrans remplacés, courriels, anciens
   logos) intervient **en dernier**, après bascule vérifiée des fonctions correspondantes
   et fenêtre d'observation (DA-12).

## Conséquences

- Le coût et le risque d'un déménagement massif (cassure des 184 migrations, des imports,
  des tests, de la CI) sont évités ; l'application reste en service pendant toute la
  refonte.
- Les développeurs trouvent dans la documentation une table de correspondance fiable entre
  modules fonctionnels et applications réelles.
- Un inventaire des noms techniques résiduels est tenu dans
  [ARCHITECTURE.md](../ARCHITECTURE.md) ; leur disparition se fera lot par lot et sera
  révocable, jamais en grande bascule unique.
- Les nouveaux développements doivent utiliser la terminologie INJS-LMD (noms de nouveaux
  fichiers, écrans, libellés, assets), même lorsque les anciens identifiants techniques
  restent en place sous le capot.

## Alternatives rejetées

- **Réorganiser toutes les applications sous `backend/apps/` et renommer les identifiants
  d'un coup.** Rejeté : risque élevé de casse globale, migration quasi irréversible,
  contraire à la règle « préserver l'existant, ajouter progressivement ».
- **Conserver également l'ancienne identité dans les documents et libellés visibles.**
  Rejeté : la documentation doit être la vitrine exacte et actuelle du produit INJS-LMD ;
  seuls les identifiants machine incontournables sont temporairement conservés.
- **Multiplier les alias d'applications ou de modèles « pour faire joli ».** Rejeté :
  ajouter des doublons de noms contredirait DA-02 (une seule source de vérité).
