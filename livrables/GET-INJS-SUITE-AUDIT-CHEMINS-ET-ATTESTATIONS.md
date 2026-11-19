# GET-INJS — suite sans interruption : audit des écritures et préalables métier

**Périmètre : préparation locale, non-production.** Après validation de la qualification PostgreSQL **isolée**, cet audit examine les chemins de mutation et ajoute une protection défensive au persisteur historique. Il **n'atteste** ni les données institutionnelles, ni la configuration d'un serveur cible, ni les identités Présences QR. Aucune activation, publication, connexion à une base réelle ou migration supplémentaire.

## Référence et séparation des données

Référence imposée : commit déployé `70d08dad1821caceb61b22fe22cf70e13155bf18`, migrations `edts.0012`, `scolarite.0020`. Les essais utilisent l'extraction isolée de cette référence enrichie sélectivement des phases GET-INJS, **sans** la migration locale `scolarite.0021` ni les propositions horaires non attestées. Les modifications hors GET-INJS déjà présentes dans le working tree sont conservées sans être revendiquées par cet audit. Le code v2 reste sous les gardes `DEBUG`, année `BENCHMARK-*` et `GETINJS_V2_EXPERIMENTAL_WRITE` ; le présent travail ne change pas ces conditions.

## Inventaire des chemins de mutation

| Chemin | Comportement constaté / garde existante | Reste à démontrer |
|---|---|---|
| `api.py` : édition, suppression d'EDT et d'affectation ; déplacement ; génération, transition vers publication | `_peut_editer` refuse les EDT contenant une occurrence v2 ; suppression de l'EDT et génération ont des refus dédiés ; publication directe est refusée. Les anciennes affectations restent accessibles par leurs routes existantes. | Vérification exhaustive des clients externes et des appels directs qui ignorent les routes HTTP. |
| `api_lmd.py` : déplacement, annulation, génération simple et coordonnée | Mutations d'une occurrence v2 refusées ; la persistance sur une année portant du v2 est refusée en amont des moteurs. Les prévisualisations restent distinctes de la persistance. | L'état lu dans l'API ne suffit pas à exclure une course entre contrôles et écriture : verrou nécessaire au service de persistance. |
| `api_getinjs.py` : génération annuelle et suppression héritée | Persistance annuelle refusée si l'année porte du v2 ; suppression héritée contrôlée. | Les autres accès hors API demeurent hors périmètre des gardes HTTP. |
| `moteur/publication.py:persister_plan` : persistance appelée par LMD, génération coordonnée et annuelle | **Protection ajoutée** : verrou transactionnel sur l'année académique, puis refus `QR_V2_CHEMIN_HERITE_REFUSE` si une occurrence datée v2 est présente **sur l'année**, même dans un autre EDT et même sans `remplacer`. Vérification avant désactivation ou création de séance. Les placements v2 verrouillent déjà cette même année. Si l'année est sans v2, comportement legacy inchangé. Test de course PostgreSQL isolé réussi (voir complément). | Couvrir d'autres interleavings de moteurs et les appels hors API ; un appel direct rejeté peut produire une erreur technique plutôt qu'une réponse HTTP dédiée s'il contourne les contrôles des routes. |
| `moteur/annee.py`, `orchestration.py`, `campagnes.py` | Appels indirects au persisteur central ; en cas d'écriture directe hors API, le refus est désormais au niveau du service. L'exécution de campagne trace ses erreurs. | Réexécuter avec scénarios d'interruption et interleaving de plusieurs moteurs sur PostgreSQL cible de test ; aucun worker durable n'est livré. |
| `moteur/application_v2.py` et `qr_v2.py` | Verrouillage de l'année et revalidation sous transaction ; clé métier stable, UUID et instantané QR préservés ; déplacement d'une séance pointée ou publiée refusé et reprogrammation par nouvelle séance liée. | Cycle réel des personnes, pointages et géolocalisation non rapproché sur données institutionnelles. |
| `presences/`, commandes administratives et écritures ORM directes | Le contrôle des routes EDT n'est **pas** une contrainte universelle de base de données : `QuerySet.update`, autres services et commandes peuvent contourner les gardes applicatives. Certaines opérations métier de Présences modifient leurs propres pointages/tokens et exigent un audit dédié avant interconnexion effective. | Cartographie intégrale de tous les acteurs et contrats d'API ; protections transverses supplémentaires/contraintes DB seulement après analyse de compatibilité et validation métier. |

La nouvelle garde bloque délibérément **toute** persistance legacy dans une année v2, pas seulement l'EDT concerné : un ajout indépendant dans la même année pourrait sinon produire une occupation incohérente que le chemin historique ne revalide pas contre les séances v2. Cela peut empêcher des opérations legacy sur un jeu mixte, par choix conservateur ; aucun mécanisme de conversion automatique n'est proposé.

## Contrôles locaux réalisés

Depuis la copie isolée enrichie, avec `USE_SQLITE=1`, `SQLITE_PATH` local jetable et `DJANGO_DEBUG=1` :

```sh
python manage.py test edts.tests.test_qr_v2_phase4 edts.tests.test_referentiel_edt_lmd --noinput
python manage.py test edts.tests.test_phase6_revalidation edts.tests.test_phase6_postgres_concurrency edts.tests.test_api_v2_phase5 edts.tests.test_qr_v2_phase4 edts.tests.test_moteur_v2_phase3 edts.tests.test_fondations_v2 edts.tests.test_interop_presences edts.tests.test_generation_annee edts.tests.test_campagnes edts.tests.test_lot2_publication_api edts.tests.test_referentiel_edt_lmd presences.test_seances_supervision --noinput
```

**43/43**, puis **197 tests : 193 OK, 4 ignorés intentionnellement car exclusivement PostgreSQL**. Nouveau test : appel direct au persisteur legacy, avec `remplacer=True` ou `False`, sur l'EDT v2 ou un autre EDT de la même année ; refus sans désactivation, perte d'UUID ou ajout de séance. Ces résultats SQLite ne sont pas présentés comme preuve de verrouillage concurrent PostgreSQL. **Complément PostgreSQL isolé ci-dessous** : les quatre tests de concurrence antérieurs ont été rejoués et un cinquième teste la course avec le persisteur historique.

### Complément ciblé : nouvelle garde sous PostgreSQL local isolé

Le même serveur local PostgreSQL 17.11 UTF-8 a été redémarré **sur socket Unix uniquement**, puis **arrêté après les tests** ; la base de test migrée depuis la référence isolée a été utilisée via les tests Django (bases de test temporaires). Résultats : **16/16** tests de garde directe et de persistance legacy inchangée ; **5/5** tests de concurrence réelle, dont un nouveau scénario à deux connexions. Dans ce dernier, le placement v2 retient le verrou de l'année avant commit ; PostgreSQL rapporte que l'écriture legacy attend un verrou ; une fois la transaction v2 terminée, l'écriture legacy lit l'occurrence et refuse `QR_V2_CHEMIN_HERITE_REFUSE`. Il reste une affectation active et son registre QR. Une suite complémentaire API v2, QR, génération annuelle et persistance legacy : **78/78** tests réussis. Chaque suite possède son propre comptage : **ne pas additionner** ces nombres comme des tests distincts.

Commandes représentatives, uniquement depuis la copie isolée et avec une base de test locale configurée :

```sh
python manage.py test edts.tests.test_phase6_postgres_concurrency --noinput
python manage.py test edts.tests.test_qr_v2_phase4 edts.tests.test_api_v2_phase5 edts.tests.test_generation_annee edts.tests.test_referentiel_edt_lmd --noinput
```

Fichiers de cette étape : `backend/edts/moteur/publication.py`, `backend/edts/tests/test_qr_v2_phase4.py`, `backend/edts/tests/test_phase6_postgres_concurrency.py` et ce rapport. Aucune migration ni donnée institutionnelle ajoutée.

## Dossiers d'attestation à réunir hors de ce banc

1. **Calendrier 2026–2027** : autorité compétente, pièce source/version datée, bornes, semaines, semestres, jours fériés/vacances, périmètre par groupe, signature/validation. Les bornes provisoires `01/10/2026`–`30/09/2027` ne sont pas une attestation.
2. **Volumes CM/TD/TP par ECUE** : source de chaque volume, applicabilité de chaque type, justification des zéros confirmés, distinction `inapplicable`/`inconnu`, validation et version. Les 779 propositions locales sont hypothétiques et **non importables comme volumes officiels**.
3. **Identités Présences QR** : correspondance nominative attestée entre inscriptions et `Participant`, règles des doublons et changements de groupe, gel des instantanés datés, anomalies de géolocalisation, historique des séances ouvertes/pointées/clôturées et autorité d'approbation. Aucune liste de personnes ni identifiant réel ne doit être généré à partir du banc fictif ; la publication reste bloquée.
4. **Configuration PostgreSQL cible et exploitation** : version/paramètres réellement prévus, capacités CPU/RAM/disque, stratégie de sauvegarde et reprise, politiques d'isolation et verrous, nombre de workers, trafic concurrent ; mesurer RSS client **et** serveur, temps end-to-end, tests de panne/reprise et comparaison des plans SQL, exclusivement dans une infrastructure de test autorisée. Les mesures précédentes ne prouvent pas le RSS système < 1 Gio.
5. **Gouvernance de l'activation** : revue de sécurité des autres appels ORM, décision explicite sur les données mixtes legacy/v2, procédure de retour arrière additive/réversible, recette métier et autorisation distincte. Aucune décision d'activation ne découle de la validation des essais isolés.

**Statut : protection applicative locale testée sur SQLite ; publication v2 et activation toujours interdites.** La suite nécessitant des pièces institutionnelles et un environnement cible de test ne peut être déclarée terminée ni validée sans ces éléments. Cette limite est un blocage factuel, pas une présomption d'attestation.
