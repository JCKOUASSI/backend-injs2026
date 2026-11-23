# GET-INJS — phase 5 : façade API/UI expérimentale

**Statut : prototype local/isolé testé ; validation de l'utilisateur demandée. Pas d'activation institutionnelle, de déploiement production, de commit ou de push de cette phase.** Phase 6 non engagée.

## Référence et écart maîtrisé

Base de référence imposée : `70d08dad1821caceb61b22fe22cf70e13155bf18`, `edts.0012` et `scolarite.0020`. Les tests backend ci-dessous ont utilisé une extraction isolée de cette référence, enrichie uniquement des fichiers phases 2–5 indispensables. Le working tree de la branche Arena contient indépendamment des changements locaux non déployés, dont `scolarite.0021` et des travaux volumes/maquette : **ni migration `0021` ni données institutionnelles non validées ne sont utilisées ou revendiquées**. Le code de phase 4 validé mais non encore commité est une dépendance de ce prototype ; le conserver avec ses nouveaux fichiers.

## Décisions et périmètre livré

- Trois routes **nouvelles** sous `/api/edts/v2/bench/` (l'alias existant `/api/timetable/` garde le même routeur) : `POST simuler-ligne/` (lecture seule), `POST placer-ligne/` (placement transactionnel BENCH, proposition revalidée, idempotence), `GET executions/<id>/` (état agrégé, lecture seule). Permissions du module EDT réutilisées : planification pour les deux POST, authentification pour la lecture. Corps typé et borné, réponse avec codes explicites et alternatives calculées par le solveur. Une entrée modifiée (formateur ou révision) ne passe pas pour une reprise identique. Aucun HTTP ne démarre le worker ; la commande ponctuelle reste séparée.
- Garde **cumulatif** sur toutes ces routes : `DEBUG=True`, `GETINJS_V2_EXPERIMENTAL_WRITE=True`, libellé de l'année `BENCHMARK-*`, groupe de cette année et révision existante. La chaîne `source_confirmee` saisie par un opérateur ne vaut **que pour une fixture fictive** : elle ne constitue jamais une validation administrative de volumes réels. La publication QR v2 reste bloquée suivant le contrat de phase 4.
- Un écran local `/edt/bench-v2`, **monté uniquement en mode développement du frontend**, permet de simuler une séance fictive, examiner le verdict/les alternatives, demander une confirmation avant de placer le brouillon, puis consulter un suivi agrégé par identifiant d'exécution. Pas de lien ni d'activation de cet écran en build de production. Le backend refuse également les opérations hors de ses propres gardes, indépendamment du frontend.
- Plusieurs anciens chemins d'édition/suppression/déplacement/annulation/génération/publication refusent désormais explicitement de modifier un EDT ou une année ayant déjà une occurrence QR v2, au lieu de réécrire une séance sans son protocole QR. Les chemins hérités sans v2 restent utilisables et leurs URLs restent stables. **Ce refus n'est pas une bascule générale des anciennes routes vers le moteur v2** : des chemins encore non audités et la concurrence entre anciens et nouveaux writers empêchent toute activation institutionnelle.

## Fichiers phase 5

`backend/edts/api_v2_experimental.py` (nouveau), `backend/edts/urls.py`, `backend/edts/api.py`, `backend/edts/api_lmd.py`, `backend/edts/api_getinjs.py`, `backend/edts/tests/test_api_v2_phase5.py` (nouveau), `frontend/src/App.jsx`, `frontend/src/pages/getinjs/BenchV2.jsx` et `BenchV2.test.jsx` (nouveaux), ce rapport. `backend/edts/moteur/application_v2.py` : docstring corrigée de la phase 4. Les autres modifications locales du dépôt sont hors périmètre.

## Contrôles sur extraction isolée (données fictives, SQLite)

Environnement backend : `DJANGO_SETTINGS_MODULE=config.settings DJANGO_DEBUG=1 USE_SQLITE=1 SQLITE_PATH=/tmp/getinjs-phase5-*.sqlite3` ; `manage.py` exécuté depuis le `backend` de la copie isolée avec l'interpréteur `.venv`. Le document de conception suivi par Git a été copié dans cette extraction pour les tests de téléchargement ; le premier passage de 109 tests avait 1 échec dû **uniquement à ce document absent de la copie**. Après correction du banc :

- `python manage.py test edts.tests.test_api_v2_phase5 edts.tests.test_qr_v2_phase4 edts.tests.test_moteur_v2_phase3 edts.tests.test_fondations_v2 edts.tests.test_interop_presences edts.tests.test_generation_annee edts.tests.test_campagnes edts.tests.test_lot2_publication_api presences.test_seances_supervision --noinput` : **174 OK**.
- `python manage.py test edts.tests.test_api edts.tests.test_api_getinjs edts.tests.test_lot3_api_lmd edts.tests.test_lot3_generation_coordonnee --noinput` : **109 OK** après ajout du document de fixture dans la copie isolée.
- Dernier ajustement de gestion d'une collision SQL en façade : **4 tests phase 5 OK** après l'ajustement ; pas de relancement de la suite complète après cet ajustement mineur.
- `python manage.py check` : OK ; `python manage.py makemigrations edts --check --dry-run` : aucune migration ; `python manage.py migrate --noinput` sur base de test : jusqu'à `edts.0013` et `scolarite.0020`, **jamais `scolarite.0021`**. `git diff --check` : OK.
- `npm run build` : OK (avertissement préexistant de taille de bundle) ; `npm run test:run -- src/pages/getinjs/BenchV2.test.jsx` : **1 test OK**. Les tests de refus HTTP journalisent des réponses 400/401/403/409 attendues ; l'avertissement `staticfiles` absent dans le banc isolé n'a pas causé d'échec.

## Limites bloquantes avant activation

1. **Pas de raccordement du générateur institutionnel ni de worker durable supervisé à ces routes.** L'écran ne prétend pas exécuter une campagne annuelle asynchrone. L'API de suivi ne démarre rien. Les anciennes routes ne sont pas toutes basculées vers un service commun ; les écritures SQL directes et une campagne héritée déjà en cours ne sont pas couvertes.
2. **Pas de flux d'attestation administratif** des volumes CM/TD/TP ou d'identités `Participant` QR. Un booléen client BENCHMARK n'est jamais une preuve institutionnelle. Sans rapprochement attesté, la publication v2 demeure refusée.
3. Concurrence PostgreSQL, verrous et isolation multi-writer non vérifiés (pas de PostgreSQL local) ; performances annuelles 5 000/10 000/15 000 et cibles ≤ 10 min/an, RSS < 1 Gio et ≤ 10 s pour un groupe/semaine non démontrées. Ces mesures relèvent notamment de la phase 6, **non autorisée**.
4. Pas de changement destructeur, de migration nouvelle, d'EDT complet ni d'utilisation de l'année 2026–2027 provisoire. Un audit exhaustif des chemins de mutation hérités reste obligatoire avant toute activation.

**Décision sollicitée : validez-vous la phase 5 comme prototype API/UI limité à des essais BENCHMARK isolés, avec les quatre limites ci-dessus, ou demandez-vous de compléter sa portée avant validation ?** Aucune phase 6 ne sera démarrée sans autorisation distincte.
