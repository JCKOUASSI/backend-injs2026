# État avant déploiement — branche `arena/a8060ecf-backend-injs2026`

**Conclusion : déploiement NON exécuté, porte de déploiement fermée.** L'autorisation de l'utilisateur pour déployer est actée ; elle ne remplace ni un calendrier S1/S2 institutionnel, ni une CI réussie, ni la preuve de publication des images immuables et des contrôles de sauvegarde/preflight du serveur. Aucune commande n'a été envoyée au VPS, à Docker Hub ou à PostgreSQL de production.

## Preuves contrôlées localement

- Branche courante : `arena/a8060ecf-backend-injs2026`, commit de départ `2b445cb`, arbre propre avant cet audit.
- Validation statique de la chaîne de déploiement : `./scripts/valider-deploiement-injs.sh` → **96 OK, 0 échec, 3 ignorés** (journal local `/tmp/injs-deploy-static-check.log`).
- Tests fonctionnels locaux de la chaîne : `PYTHON=backend/.venv/bin/python ./scripts/tester-deploiement-injs.sh` → **173 passés, 0 échoué** (journal local `/tmp/injs-deploy-functional-check-venv.log`). La première invocation sans PyYAML s'était arrêtée au contrôle de dépendance et n'est pas comptée réussie. Ni SSH réel, ni sauvegarde réelle, ni image Docker, ni migration de production n'ont été exercés.
- État CI : `gh run list --branch arena/a8060ecf-backend-injs2026` → `[]` ; `gh workflow run ci.yml --ref arena/a8060ecf-backend-injs2026` → HTTP **403 `Resource not accessible by integration`**. Ce n'est pas une validation CI.
- Résultats métier antérieurs à ce document : Présences/EDT PostgreSQL isolé UTF8 **714/714 OK** ; suite backend globale SQLite **3 162 recensés, 3 149 OK, 13 ignorés**, effectuée avant deux tests ajoutés ; la suite backend globale PostgreSQL a été interrompue au-delà de 30 minutes et n'a pas de verdict. Les deux générations manuelles S1/S2 de test (12 h/6 occurrences persistées) ne prouvent pas l'annuel automatique. Cf. `FINALISATION_QR_EDT_CI_2026.md`.

## Pourquoi la commande « déployer » n'est pas lancée

1. **Critère fonctionnel absent :** `scolarite.Semestre` n'a pas de dates de début/fin. Le moteur refuse l'année automatique S1/S2 sans semaines institutionnelles approuvées ; impossible de qualifier un EDT annuel réel ou les interruptions de cours.
2. **CI bloquée :** aucune exécution sur cette branche. Le 403 provient de l'intégration GitHub actuelle, pas d'un échec avéré du code ; il faut un acteur habilité Actions pour lancer et vérifier la CI.
3. **Chaîne de publication non démontrée :** `publish-injs-lmd.yml` doit publier les images backend/frontend liées au SHA Git, avec ses secrets Docker Hub ; `deploy-injs-lmd.yml` exige une publication réussie, un tag SHA immuable, l'accès SSH et des garde-fous de préflight, sauvegarde et migrations. Aucun de ces résultats distants n'est disponible dans cette session. Le workflow de déploiement automatique est limité aux publications réussies de `main` ; la branche de travail ne doit pas être présentée comme déjà déployable par ce déclencheur. Ne pas contourner les prérequis par un appel SSH direct.
4. **Accès sensible :** la rotation des identifiants de démonstration anciennement affichés sur le site public n'est pas confirmée ; ne pas supposer les comptes sécurisés. Le scan QR legacy, les terminaux réels et les données institutionnelles restent hors des preuves locales.

## Suite autorisable après levée des blocages

- Fournir et valider le calendrier S1/S2 de l'année cible (dates, semaines de cours, fériés/interruptions, reprise des séances) et arbitrer les séances déjà pointées qui sont modifiées.
- Faire exécuter par une personne habilitée la CI `ci.yml` sur `arena/a8060ecf-backend-injs2026`, vérifier les jobs Backend PostgreSQL et Frontend, puis l'artefact de tests ; analyser les éventuels échecs sans modifier la protection Actions.
- Valider la publication d'images immuables correspondant au SHA retenu, les sauvegardes vérifiées et le preflight de production **avant** tout mode `deployer`, conformément à `deploy/production/RUNBOOK.md`. La bascule de domaine reste une étape distincte et manuelle.

**Aucun déploiement n'a été exécuté.** L'autorisation utilisateur ne vaut pas preuve que les portes techniques et métier sont franchies.
