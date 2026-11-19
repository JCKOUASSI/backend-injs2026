# GET-INJS APP ↔ Présences QR — état technique du durcissement continu

**Périmètre validé :** essais locaux synthétiques et code conservateur, sans données personnelles réelles, accès production, activation institutionnelle ou nouvelle migration. La référence déployée reste `70d08dad1821caceb61b22fe22cf70e13155bf18` (`edts.0012`, `scolarite.0020`) ; la copie de test enrichie sélectivement exclut la migration locale non déployée `scolarite.0021`. Les résultats SQLite et PostgreSQL ci-dessous ne certifient pas la configuration cible.

## Problèmes concrets corrigés

1. **Préflight QR faussement vert par modification d'un champ libre.** `anomalies_publication_v2` refusait l'instantané d'effectif importé, mais une autre chaîne `base_calculee` pouvait supprimer ce motif sans véritable attestation. Désormais toute base non reconnue produit `QR_V2_ATTESTATION_NON_PROUVEE` ; l'effectif importé conserve `QR_V2_PARTICIPANTS_NON_RAPPROCHES`. Il n'existe pas encore de flux administratif attestant les identités, donc **aucune publication v2 autorisée**. `force=True` ne contourne pas cette protection.
2. **Transition de registre directe.** `transitionner(..., PUBLIEE)` passait par l'API interop sans le préflight de publication de l'EDT. Les transitions d'une occurrence datée v2 refusent désormais si la ligne est inactive, si l'EDT n'est pas publié ou si le préflight QR présente une anomalie. Le parcours des séances historiques non datées demeure inchangé.
3. **Réconciliation d'un EDT dont le statut aurait été forcé.** Le service traite toutes ses lignes dans une transaction ; en cas de refus QR v2, l'API interop renvoie désormais **409** et le traitement est annulé, plutôt qu'un 500. Aucun événement `SEANCE_PUBLIEE` n'est créé.
4. **Consommation Présences QR.** Le contrat `peut_ouvrir_session_presence`, la liste des séances publiées interop et la garde centrale `est_seance_du_jour` des routes de jeton, scan, émargement et clôture refusent une occurrence v2 non attestée, y compris si ses statuts ont été forcés directement en base. Tant que le flux d'attestation n'existe pas, le refus v2 est en temps constant, sans requête QR supplémentaire par séance (pas de préflight répété N²). Les pointages historiques ne sont ni modifiés ni supprimés. Les séances legacy restent sur leur chemin existant.
5. **Persistance et concurrence.** La garde ajoutée précédemment dans `persister_plan` verrouille l'année et refuse le chemin historique en présence d'occurrences v2. Une course avec un placement v2 a été testée sous PostgreSQL isolé : le persisteur attend puis refuse sans désactiver la séance ni changer son registre.

La règle reste volontairement **fail-closed** : aucune automatisation ne devine un `Participant` depuis une inscription importée, aucune géolocalisation manquante n'est fabriquée, et aucune publication ne peut être obtenue en renommant seulement la base d'un instantané. Les UUID, clés métier, événements, instantanés et pointages existants sont préservés.

## Vérifications exécutées sur la copie isolée

| Banc | Commande/suite | Résultat |
|---|---|---|
| SQLite local fictif | Fondations, moteur, QR, API expérimentale, génération annuelle, publication héritée et Présences (supervision, EDT, mobile, complétion) | **287 tests exécutés, 282 OK, 5 ignorés exclusivement PostgreSQL** avant le dernier contrôle `inactive` ; puis **31/31** tests QR incluant ce cas |
| SQLite local fictif | QR, interop et Présences EDT/mobile après le refus v2 en temps constant | **105/105** sur la version finale du code |
| PostgreSQL 17.11 local isolé UTF-8, socket Unix uniquement | QR, interop, Présences EDT/mobile et cinq scénarios de concurrence | **109/109** avant le dernier contrôle `inactive` ; le serveur de test a été arrêté |
| Schéma et propreté | `manage.py check`, `manage.py makemigrations edts --check --dry-run`, `git diff --check` | OK ; **aucune migration supplémentaire** |

La dernière petite garde « occurrence v2 inactive » a été retestée sur SQLite dans les 31 tests QR, **pas** sur PostgreSQL. Les nombres de suites se chevauchent et ne doivent pas être additionnés. Aucune campagne de charge 5k/10k/15k n'a été rejouée après ces changements ; les résultats antérieurs mesurent le moteur de placement, pas la nouvelle garde des lectures QR. Le diagnostic agrégé `scripts/diagnostiquer_qr_getinjs_v2.py` reste non destructif et réservé au banc.

Fichiers de cette étape : `backend/edts/moteur/qr_v2.py`, `backend/edts/moteur/interop_presences.py`, `backend/edts/api_interop.py`, `backend/presences/seances_edt_services.py`, `backend/edts/tests/test_qr_v2_phase4.py` et ce rapport. Les autres changements locaux antérieurs, y compris `scolarite.0021`, ne sont pas prétendus déployés ni validés par ce rapport.

## Conditions externes toujours bloquantes

Pour une **GET INJS APP complète, officiellement publiée et synchronisée avec Présences QR** : calendrier et volumes CM/TD/TP 2026–2027 sourcés et approuvés ; correspondance attestée `InscriptionImportee` ↔ `Participant` et gestion des changements de groupe/doublons ; géolocalisation validée des salles ; recette de bout en bout avec de vrais rôles habilités sur une copie de test autorisée ; revue des autres écritures ORM, du worker durable et de la reprise sur incident ; mesures système complètes sur une configuration PostgreSQL cible, puis décision d'activation distincte. Les 779 propositions locales demeurent **hypothétiques et non importables**. Rien dans cette étape ne fournit ni ne remplace ces attestations.

**Décision technique : protections QR conservatrices et régressions ciblées vertes ; validation de production et publication v2 non acquises.**
