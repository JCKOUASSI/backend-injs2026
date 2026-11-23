# GET INJS APP — paquet de mise en recette isolée, **pas de déploiement**

**Objet.** Cet overlay de 28 fichiers s'applique uniquement à un **checkout propre** du commit de référence déployé `70d08dad1821caceb61b22fe22cf70e13155bf18`. Il ne constitue ni une image prête à publier, ni un export de base, ni une attestation métier. Aucun accès au site public, au VPS ou à une base de production n'a été effectué. La branche Arena courante possède des modifications locales non validées pour un déploiement global ; **ne pas déployer la branche entière**.

## Contenu vérifié

- `getinjs-v2-overlay-recette.tar.gz` : code GET INJS et protections Présences QR, tests ciblés, migration additive `edts.0013`, écran fictif accessible uniquement au frontend **en mode développement**. Les routes du backend v2 refusent l'écriture hors `DEBUG`, drapeau expérimental et année `BENCHMARK-*`. Aucun worker annuel de production n'est démarré.
- `manifest.json` : commit de base, SHA-256 de chacun des 28 fichiers. `SHA256SUMS.txt` : empreinte de l'archive **et** du manifeste. Génération déterministe : `python scripts/preparer_recette_getinjs_v2.py` depuis ce dépôt.
- **Exclus** : `scolarite.0021` non déployée, modifications locales des volumes/maquettes, jeux CSV, identifiants réels, bases et secrets. Un premier overlay ayant recopié par erreur trois fichiers de volumes dépendant de `scolarite.0021` a échoué à deux tests historiques ; il a été **abandonné et remplacé** par cet overlay corrigé. `annee.py`, `besoins_maquette.py` et `campagnes.py` restent exactement ceux du commit de référence.

## Reconstitution et contrôles, sur une machine de test locale seulement

Depuis le dossier contenant le paquet, vérifier `sha256sum -c SHA256SUMS.txt`. Préparer un clone **jetable** et propre du commit de référence (ne jamais appliquer l'overlay au checkout de production ni à cette branche de travail), puis extraire l'archive dans ce clone. Contrôler chaque SHA-256 du manifeste et refuser toute autre modification ou migration que `edts.0013` ; ne pas faire confiance à un fichier ajouté à la main. Les chemins de l'archive sont relatifs au dépôt.

Sur cette candidate isolée, avec une base de test vide, synthétique et autorisée :

```sh
python backend/manage.py check
python backend/manage.py makemigrations edts scolarite --check --dry-run
python backend/manage.py test edts.tests.test_api edts.tests.test_api_getinjs \
  edts.tests.test_lot3_api_lmd edts.tests.test_lot3_generation_coordonnee --noinput
python backend/manage.py test edts.tests.test_qr_v2_phase4 \
  edts.tests.test_interop_presences edts.tests.test_api_v2_phase5 \
  presences.test_seances_edt presences.test_seances_edt_mobile --noinput
# Sur PostgreSQL de test isolé seulement, ajouter :
python backend/manage.py test edts.tests.test_qr_v2_phase4 \
  edts.tests.test_phase6_postgres_concurrency \
  edts.tests.test_interop_presences presences.test_seances_edt --noinput
# Dans frontend/ : npm run build ; npm run test:run -- src/pages/getinjs/BenchV2.test.jsx
```

Adapter uniquement l'interpréteur et les variables Django de **test** du projet, jamais les utiliser avec une URL ou une base institutionnelle. Dans la recette reconstruite localement ici : `manage.py check` et `makemigrations --check` OK, **109/109 tests API historiques**, **110/110 tests QR/API/Présences** sur SQLite synthétique (dont le refus v2 avec `DEBUG=False` même si le drapeau expérimental est activé), **81/81 tests QR/concurrence/Présences** sur PostgreSQL local UTF-8 (socket Unix exclusivement), frontend construit et **1/1 test** du prototype. Le serveur PostgreSQL de test a été arrêté. L'avertissement de taille du bundle frontend subsiste. Les suites se chevauchent : ces totaux ne sont pas additionnables.

La migration `edts.0013` a été appliquée, annulée et réappliquée **sur une base SQLite jetable vide** ; cela établit sa réversibilité technique dans cette condition, pas l'innocuité d'un retour arrière après création de données v2. **Un rollback d'exploitation doit revenir au code stable sans annuler mécaniquement une migration qui pourrait contenir des séances ou des registres.** Toute procédure de sauvegarde/restauration sur une cible réelle doit être arrêtée par son administrateur et vérifiée hors de cette conversation. Ne jamais supprimer de volume, de pointage, de registre ou d'instantané pour « nettoyer » une recette.

## Portes bloquantes avant mise en ligne

1. Calendrier académique et volumes CM/TD/TP officiels 2026–2027, pièce source et validation humaine ; les bornes provisoires et propositions horaires locales ne valent pas approbation.
2. Rapprochement administratif démontré `InscriptionImportee` ↔ `Participant`, états historiques de séances et géolocalisation des salles attestés. Le moteur v2 **refuse toujours sa publication et son badgeage** ; on ne peut pas qualifier l'écran `/edt/generation-annuelle` de « nouveau moteur annuel institutionnel » avec ce paquet.
3. Recette de bout en bout sur la configuration cible de **test**, sauvegardes et restauration prouvées, audit des chemins ORM tiers, supervision d'un worker durable, mesures RSS du système entier et test du rollback sur données de test. Les chronos du PostgreSQL éphémère ne qualifient pas un hébergement réel.
4. Décision séparée et explicite de publication du code par les responsables du site, après comparaison de la version réellement installée avec la référence. Le domaine public n'a pas été contacté ici ; il peut différer de la référence supposée.

**Conclusion : paquet de mise en recette techniquement vérifié, NON publiable tel quel.** Aucune migration sur site ni bascule de trafic n'a été lancée. Le chemin de production conserve ses URLs et le mode `DEBUG=False` doit rester en vigueur.
