# Quelle base porte réellement GET INJS APP et Présences QR ?

**Date** : 2026-11-05
**Question posée** : identifier la base qui correspond **fonctionnellement** à l'application cible (et non celle qui contient le plus de données).
**Référentiel de vérité** : le code de `main@767dabf` (`backend-injs2026`), qui définit ce que chaque module **exige** comme schéma.
**Nature** : audit, lecture seule. Aucune opération corrective.

---

## 0. Ce qui est mesuré ici, et ce qui ne l'est pas

| Élément | État |
|---|---|
| Tables exigées par chaque module | ✅ **établi par le code** (introspection Django + migrations) |
| Fichier de vérification (présence + volumes ciblés) | ✅ **écrit et validé** (`docs/audits/sql/20_empreinte_modules.sql`) |
| Présence réelle de ces tables dans chaque base du VPS | ❌ **non mesurée** — VPS inaccessible depuis l'environnement d'audit (`kex_exchange_identification: Connection reset by peer`, tentative unique) |
| Backend exposé par Nginx Proxy Manager et sa base | ❌ **non vérifié** — même cause ; commandes de vérification fournies au §4 |
| Volumes réels des tables structurantes | ❌ **non mesurés** — script prêt, à exécuter sur le VPS |

**Aucune valeur estimée n'est présentée comme mesurée.** La conclusion distingue explicitement ce qui est *démontré par la structure du code* de ce qui *reste à confirmer par une mesure*.

---

## 1. Ce que chaque module exige (établi par le code)

### 1.1 GET INJS APP — emplois du temps, référentiels LMD, maquettes, séances, simulations

- **Applications porteuses** : `edts` (14 modèles, 11 migrations), `scolarite` (22 modèles), `referentiels` (17), `formations` (27).
- **Surface d'API réelle** : `api/edts/` et `api/timetable/` (`config/urls.py`), soit **73 routes** déclarées dans `edts/urls.py`. La simulation est un paramètre explicite du moteur : `simulation` (booléen) dans `edts/api_getinjs.py`, et une commande dédiée `compteur_sql_getinjs` qui exécute une génération annuelle **sans écriture**.
- **Tables structurantes (24)** :

| Famille | Tables exigées |
|---|---|
| Emplois du temps / génération | `edts_emploidutemps`, `edts_affectationcreneau`, `edts_creneautemplate`, `edts_campagnegeneration`, `edts_executioncampagne`, `edts_conflitcreneau`, `edts_disponibilitehoraire`, `edts_inscriptionimportee`, `edts_politiquecontraintessouples` |
| Référentiels et maquettes | `referentiels_reffiliere`, `scolarite_anneeacademique`, `scolarite_niveau`, `scolarite_semestre`, `scolarite_parcours`, `scolarite_maquette`, `scolarite_ue`, `scolarite_ecue`, `scolarite_groupe`, `scolarite_affectationpedagogique` |
| Socle | `formations_refformation`, `formations_refsalle`, `formations_refsite`, `formations_formateur`, `formations_refmodule` |

**Sans ces 24 tables, le module ne peut pas démarrer** : ses vues, ses serializers et ses règles de conflit (C1 enseignant, C2 groupe, C3 salle — `edts/api_lmd.py`) reposent directement sur elles.

### 1.2 PRÉSENCES QR — pointages, géolocalisation, justificatifs, audit

- **Applications porteuses** : `presences` (6 modèles, 30 migrations), `edts` (registre de séance + géolocalisation), `formations` (jetons QR, participants, séances de module), `scolarite` (dossiers, groupes, ECUE, inscriptions pédagogiques).
- **Surface d'API réelle** : `api/` (`presences/urls.py`), **43 routes**.
- **Tables structurantes (19)** :

| Famille | Tables exigées |
|---|---|
| Pointage et encadrement | `presences_pointage`, `presences_encadrantseance`, `presences_devicebinding`, `presences_auditlog`, `presences_rattrapage`, `presences_notificationabsence` |
| QR et géolocalisation | `formations_qrtoken`, `gi_salle_geolocalisation`, `gi_seance_registre`, `gi_seance_evenement`, `gi_seance_historique`, `gi_seance_instantane` |
| Rattachement pédagogique et étudiant | `edts_affectationcreneau`, `formations_participant`, `formations_sessionmodule`, `scolarite_dossieretudiant`, `scolarite_groupe`, `scolarite_ecue`, `scolarite_inscriptionpedagogique` |

- **Géolocalisation** : portée par `gi_salle_geolocalisation` **et** par les champs `geofence_latitude / geofence_longitude / geofence_rayon_m` de `formations_refsite`. Un site sans geofence rend le contrôle de présence géolocalisée inopérant, même si la table existe.
- **Audit** : `presences_auditlog` a été étendu au fil de 8 migrations (actions de séance, d'authentification, de secrétariat, de référentiel, de finance, de désarchivage) : la richesse de cette table est un **marqueur de version** du module.
- **Point d'attention déjà établi** : toutes les clés de `presences_pointage` sont nullables et aucune contrainte n'impose un support (ni séance EDT, ni session). La présence de la table ne garantit donc pas la cohérence des pointages : la vérification §5 du script 20 la mesure.

---

## 2. Matrice comparative des deux bases

| Critère (exigence du code) | `injs-db` (historique) | `injs_lmd_prod_20261026` |
|---|---|---|
| Applications du module EDT (`edts`) | **absente** — la base héritée est organisée en `academics`, `students`, `admissions`, `exams`, `faculty`, `accounts`, `finance`, `library` | **attendue présente** (l'application `edts` fait partie des 21 applications métier du code) |
| Applications du module Présences (`presences`) | **absente** | **attendue présente** |
| Tables `edts_*` (9) | **0/9** — aucun équivalent : l'« emploi du temps » historique est `faculty_schedule`, un simple créneau (cours, salle, jour), sans campagne, sans contrainte, sans version, sans population | **9/9 attendues** |
| Tables `gi_*` (géolocalisation, registre) | **0/5** — concept inexistant dans un schéma hérité | **5/5 attendues** |
| Jetons QR (`formations_qrtoken`) | **absente** | **attendue présente** |
| Référentiels LMD (`referentiels_reffiliere`, `scolarite_*`) | **absents** — le référentiel historique est « programmes + promotions + semestres », sans filière F01–F08, sans maquette versionnée, sans UE/ECUE | **attendus présents** |
| Couverture structurante mesurée | **à mesurer** (attendu : 0/24 et 0/19) | **à mesurer** (attendu : 24/24 et 19/19) |
| Volume de données | élevé (305 inscriptions, 1 599 présences, notes…) | quasi nul (votre constat) |
| **Verdict fonctionnel** | **structurellement incapable** de porter les deux modules | **seule base structurellement capable** |

**Point décisif** : les deux bases ne sont pas deux versions du même système. `injs-db` est une application **différente** (gestion académique classique : programmes, cours, séances, notes, bibliothèque). Aucun de ses objets ne se nomme `edts`, `presences` ou `gi_` ; aucune de ses tables ne peut servir de support à un emploi du temps versionné ni à un pointage QR géolocalisé. Sa richesse documentaire est réelle, mais elle ne la rend pas candidate : **elle ne parle pas la même langue métier**.

> Réserve de méthode, conforme à votre consigne : la colonne `injs-db` s'appuie sur l'inventaire que vous avez établi (73 tables réparties dans ces 8 domaines). Elle est **confirmée ou infirmée en une commande** par le script 20 (score attendu 0 %). Aucune table historique n'est présumée valide.

---

## 3. Volumes : pourquoi ils ne tranchent pas, et ce qu'il faut mesurer

Le volume ne prouve rien ici :
- une base remplie peut être **étrangère** au système cible (cas de `injs-db`) ;
- une base vide peut être **la bonne**, à condition d'être initialisée.

Ce qui doit être mesuré, et seulement cela, ce sont les **volumes des tables structurantes** (script 20, §4) :

| Mesure | Ce qu'elle décide |
|---|---|
| `edts_emploidutemps` > 0 | au moins un EDT a été produit dans cette base |
| `edts_campagnegeneration` / `edts_executioncampagne` > 0 | le moteur de génération a réellement servi |
| `scolarite_maquette` > 0 et `scolarite_ue` > 0 | le référentiel LMD a été initialisé (condition d'usage de GET INJS APP) |
| `formations_qrtoken` > 0, `gi_seance_registre` > 0, `presences_pointage` > 0 | la chaîne QR → séance → pointage a fonctionné au moins une fois |
| `gi_salle_geolocalisation` > 0 **et** sites avec `geofence_rayon_m` > 0 | le contrôle géographique est réellement configuré |

Une couverture de 100 % avec tous les compteurs à zéro signifie : **base correcte, application jamais initialisée** → c'est précisément l'hypothèse « base candidate à compléter ».

---

## 4. Backend exposé par Nginx Proxy Manager et base associée (non vérifié)

Je n'ai **pas** pu vérifier le routage : aucune session sur le VPS. Voici les commandes de lecture strictes, sans aucune écriture et **sans affichage de secret**, à exécuter dans l'ordre.

```sh
# 1. Quels conteneurs tournent, et lesquels sont des backends ?
ssh almalinux@152.228.233.123 'docker ps --format "{{.Names}}\t{{.Image}}\t{{.Status}}"'

# 2. Quel hôte NPM redirige vers quel conteneur (aucun secret : noms d'hôtes et cibles)
ssh almalinux@152.228.233.123 \
 'docker exec <conteneur_npm> sh -c "grep -hE \"server_name|proxy_pass\" /data/nginx/proxy_host/*.conf"'

# 3. Noms des variables d'environnement du backend (valeurs masquées)
ssh almalinux@152.228.233.123 \
 'docker inspect -f "{{range .Config.Env}}{{println .}}{{end}}" <conteneur_backend> | sed "s/=.*/=<masqué>/"'

# 4. UNIQUEMENT le nom de la base visée (ce n’est pas un secret)
ssh almalinux@152.228.233.123 \
 'docker inspect -f "{{range .Config.Env}}{{println .}}{{end}}" <conteneur_backend> | grep -E "^POSTGRES_DB="'

# 5. Ancienne base réellement utilisée par Celery (worker/beat), nom de base seulement
ssh almalinux@152.228.233.123 \
 'docker inspect -f "{{range .Config.Env}}{{println .}}{{end}}" <conteneur_celery> | grep -E "^POSTGRES_DB="'
```

**Ce que ces sorties établiront** : (a) quel backend NPM expose réellement ; (b) quelle base ce backend utilise (`POSTGRES_DB`) ; (c) si Celery — qui, selon votre constat, pointe encore l'ancienne base — divergera du backend après bascule.

⚠️ Ne pas utiliser `docker exec ... env` sans filtre : cela afficherait les secrets. Le filtre `sed "s/=.*/=<masqué>/"` de l'étape 3 ne montre que les noms.

---

## 5. Données métier réellement présentes

Non mesurées. Ce que la structure permet d'affirmer :

- **`injs_lmd_prod_20261026`** : quasi vide selon votre constat ⇒ aucun référentiel LMD, aucune maquette, aucun EDT, aucun pointage. Les fonctionnalités existent dans le code mais **ne peuvent pas être exercées** sans initialisation.
- **`injs-db`** : données métier réelles et nombreuses, mais rattachées à des objets qui **n'ont pas de correspondance** dans les deux modules (un `faculty_schedule` n'est pas un `EmploiDuTemps` versionné ; un `faculty_attendance` n'est pas un `Pointage` QR).

Distinction à conserver : `injs-db` reste une **archive métier exploitable** (étudiants, inscriptions, notes) pour une reprise partielle et conditionnelle — ce que documente le rapport comparatif du 2026-11-05. Elle n'est pas, et ne sera pas, la base applicative.

---

## 6. Écarts à corriger avant toute mise en production

| # | Écart | Preuve / mécanisme | Correction (hors audit) |
|---|---|---|---|
| 1 | Référentiels LMD absents ou incomplets | `referentiels_reffiliere`, `scolarite_*` vides ; GET INJS APP en dépend | commandes `importer_referentiels_injs`, `import_referentiel_injs_lmd`, `configurer_referentiel_injs` puis `controler_referentiel_injs` |
| 2 | Maquettes/UE/ECUE non validées | `Maquette.statut` verrouille l'édition ; UE/ECUE y sont rattachées | import des maquettes puis validation par le métier |
| 3 | Aucun compte habilité | 1 utilisateur en cible ; `habilitations` vide | création des comptes + rôles métier (`RoleMetier`), pas de réutilisation brute des 111 comptes historiques |
| 4 | Géolocalisation non configurée | `RefSite.geofence_*` + `gi_salle_geolocalisation` | renseigner les geofences par site avant d'ouvrir le pointage QR |
| 5 | Aucun jeton QR ni registre de séance | `formations_qrtoken`, `gi_seance_registre` vides | à produire par l'usage après ouverture ; contrôler la chaîne par un test encadré |
| 6 | Pointages potentiellement incohérents | aucune contrainte n'impose participant/séance sur `presences_pointage` | contrôles applicatifs + requête de surveillance (§5 du script 20) |
| 7 | Écart de schéma « 203 vs 222 tables » non tranché | référentiel `docs/audits/tables_cibles_attendues.txt` | comparaison automatique (script 00 + `consolider.py`, §6) |
| 8 | Celery pointant l'ancienne base | votre constat | à vérifier (§4, commande 5) puis à aligner **hors audit** |
| 9 | Le backend exposé n'est pas encore rattaché à la cible | à vérifier (§4) | bascule de routage = décision distincte, hors audit |

---

## 7. Conclusion et recommandation

### Réponses directes

1. **Base correspondant le mieux à GET INJS APP** → `injs_lmd_prod_20261026`. C'est la seule dont le schéma peut porter les 24 tables structurantes du module (9 tables `edts_*`, référentiels LMD, maquettes, UE/ECUE, groupes, affectations pédagogiques). `injs-db` en est structurellement dépourvue.
2. **Base correspondant le mieux à Présences QR** → la **même** : `injs_lmd_prod_20261026`, seule à pouvoir porter les 19 tables structurantes (pointages, jetons QR, registre de séance, géolocalisation, audit, justificatifs).
3. **Divergences entre les deux modules** → **aucune**. Les deux modules partagent le même socle (`formations`, `scolarite`) et se rejoignent sur `edts_affectationcreneau`. Une seule base suffit ; en séparer deux serait une erreur d'architecture.
4. **Backend exposé publiquement et sa base** → **non vérifiable dans cet audit** ; procédure fournie (§4). C'est la seule inconnue qui touche à l'exploitation.
5. **Données métier réellement présentes** → non mesurées ; la cible est réputée quasi vide, et la structure confirme qu'aucune donnée de ces modules ne peut exister sans les référentiels correspondants.
6. **Écarts à corriger** → les neuf points du §6, dont deux bloquants avant production : référentiels/maquettes (1–2) et habilitations (3).

### Recommandation

> **`injs_lmd_prod_20261026` : base candidate désignée, à COMPLÉTER.**
>
> Elle est la seule base dont la structure peut porter GET INJS APP et Présences QR — cela est démontré par le code, indépendamment de tout volume. Elle n'est **pas** prête en production : son contenu doit être initialisé (référentiels, maquettes validées, comptes habilités, geofences) avant toute bascule.
>
> **`injs-db` : écartée comme base applicative.** Elle reste une **archive métier** exploitable pour une reprise partielle et conditionnelle. La considérer comme la base de référence parce qu'elle est remplie serait l'erreur centrale à éviter.
>
> Le mot « confirmée » ne sera employé qu'après **une** mesure : l'exécution de `docs/audits/sql/20_empreinte_modules.sql` sur les deux bases. Attendu : `injs-db` 0/24 et 0/19 ; cible 24/24 et 19/19. Tout autre résultat invaliderait cette conclusion et devrait être analysé avant décision.

### Commande unique pour clore le doute

```sh
cd docs/audits/sql
MODE=docker PG_CONTAINER=<conteneur_postgres> sh run_audit.sh   # exécute 20, 00 et 10 en lecture seule
python3 consolider.py collecte -o ../202X-XX-XX-consolidation.md
```

Les scripts ouvrent `BEGIN TRANSACTION READ ONLY` et terminent par `ROLLBACK` : aucune écriture n'est possible, même par erreur. Aucune sortie ne contient de donnée nominative.

---

**Aucune opération corrective effectuée — aucune migration, aucun INSERT/UPDATE/DELETE, aucun DROP/TRUNCATE, aucun import, aucun redémarrage, aucun changement de configuration ou de routage.**
