# PHASE 5 — chantier 1 : identité de séance et mutualisation

**Statut : livré et vérifié** — base locale uniquement, aucune intervention production.

Objet : doter la séance d'une identité stable et persistée, et permettre à
plusieurs groupes de partager **une même** séance sans duplication.

---

## 1. Le problème

Une séance (`edts.AffectationCreneau`) n'était identifiable que par le triplet
`(emploi_du_temps, creneau_template, semaine)`. Conséquences :

* aucune **date civile** persistée — elle se recalculait à l'affichage ;
* aucun **statut de cycle de vie** (planifiée, confirmée, reportée, réalisée) ;
* aucun **rattachement pédagogique propre** (semestre, UE, ECUE) — il fallait
  repasser par l'affectation ;
* aucun **identifiant durable** pour le QR : le lien vers la présence
  s'appuyait sur la clé primaire, exposée et instable ;
* la **mutualisation** obligeait à créer une séance par groupe, ce qui
  éclatait les présences sur plusieurs objets et rendait le suivi impossible.

## 2. Ce qui a été ajouté

Huit champs **additifs** sur `AffectationCreneau`. Aucun champ existant n'est
supprimé, renommé ni altéré.

| Champ | Rôle |
|---|---|
| `annee_academique` | Repère annuel |
| `semestre` | Repère semestriel |
| `ue` | Unité d'enseignement |
| `ecue` | Élément constitutif d'UE |
| `date` | Date civile, **persistée** |
| `statut` | Cycle de vie : `PLANIFIEE` → `CONFIRMEE` / `REPORTEE` / `ANNULEE` / `REALISEE` |
| `jeton_qr` | Identifiant durable et non devinable, unique |
| `groupes_lies` | M2M — groupes **supplémentaires** de la séance |

### Trois décisions structurantes

**Le jeton est un défaut appelable, pas une valeur calculée dans `save()`.**
`persister_plan` écrit les séances en `bulk_create` (`moteur/publication.py`) :
ni `save()` ni signaux ne s'exécutent. Le jeton est donc
`default=nouveau_jeton_seance`, soit `secrets.token_urlsafe(32)` — environ 43
caractères, imprévisible, donc non forgeable pour pointer une séance tierce.

**`groupe` reste le groupe porteur ; `groupes_lies` ne porte que les
groupes supplémentaires.** Il n'y a ainsi jamais deux façons de désigner le
groupe principal, et un seul objet séance.

**Le contexte pédagogique est dénormalisé, jamais autoritaire.**
`AffectationPedagogique` (779 lignes) porte déjà parcours, niveau, semestre, UE
et ECUE. Les champs de la séance en sont une copie alimentée automatiquement,
comme `enseignant_nom` et `salle_nom` l'étaient déjà. `completer_contexte()`
comble les vides et n'écrase jamais une valeur déjà posée.

### Le cycle de vie ne remplace pas l'activation

La restitution exposait déjà une clé `statut` valant `ACTIVE` / `ANNULEE`,
dérivée de `a.actif`, dont dépendent les écrans existants. **Cette clé n'est
pas touchée** : le cycle de vie est exposé sous une clé distincte,
`statut_seance`. Les deux cohabitent et sont indépendantes — annuler au sens
`actif` reste l'affaire de `item_cancel_api`.

## 3. Migration

`edts/migrations/0010_seance_identite_et_mutualisation.py`.

Deux pièges traités :

* **Unicité et défaut appelable.** Un `default` appelable sur une colonne
  unique est évalué **une seule fois** par SQLite puis appliqué à toutes les
  lignes : l'unicité serait violée dès la deuxième séance. `jeton_qr` est donc
  ajouté sans `default` (lignes existantes à `NULL`), la fonction
  `_remplir_identite_seances` attribue ensuite un jeton distinct à chacune, et
  l'unicité n'est posée qu'ensuite (`AlterField` final).
* **Migration et modèle courant.** Une migration opère sur des modèles
  historiques, qui n'exposent pas les méthodes du modèle actuel. Le calcul de
  date est donc recopié dans `_date_de_seance`.

**Réversibilité vérifiée** sur la base de développement : `migrate edts 0009`
supprime les huit champs, les 34 séances et 3 390 pointages sont intégralement
conservés ; `migrate edts` les restaure avec 34 jetons uniques, 0 doublon, et
les 3 359 pointages rattachés toujours en place.

## 4. API

Trois routes, ajoutées dans `edts/urls.py` **avant** `lmd/<int:pk>/…` — sinon
le littéral `seances` serait capté comme un identifiant d'emploi du temps.

| Route | Méthodes | Permission | Objet |
|---|---|---|---|
| `/api/edts/lmd/seances/<pk>/qr/` | GET | lecture authentifiée | Contrat de données de la séance pour le module de présence |
| `/api/edts/lmd/seances/<pk>/groupes/` | GET, POST | planification | Lecture et ajout de groupes mutualisés |
| `/api/edts/lmd/seances/<pk>/groupes/<id>/` | DELETE | planification | Retrait d'un groupe |

Règles de l'ajout de groupes (`POST`) :

* le groupe porteur est refusé (il l'est déjà) ;
* un groupe déjà lié est refusé — **jamais de doublon** ;
* un groupe inexistant est refusé, sans trace d'audit ;
* la capacité de la salle est confrontée à l'**effectif cumulé** (et non à
  celui d'un seul groupe) : si elle est insuffisante, une alerte est renvoyée
  sans bloquer — l'arbitrage reste au gestionnaire habilité.

Chaque mutation est journalisée dans `presences.AuditLog` avec l'action
`SEANCE_UPDATE` déjà usitée par l'application. Aucun journal parallèle n'a été
créé.

La grille (`result_api`) expose en plus l'identité : `date`, `jeton_qr`,
`statut_seance`, `est_mutualisee`, `groupes`, `groupes_lies`,
`effectif_cumule`.

## 5. Vérifications exécutées

Toutes les commandes ci-dessous ont été **réellement exécutées**.

### Tests

| Portée | Résultat |
|---|---|
| Nouveaux — `edts.tests.test_phase5_seance` | **59 tests OK** |
| Non-régression — `edts` | **474 tests OK** (415 avant le chantier + 59) |
| Non-régression — `presences` | **176 tests OK** |
| `manage.py check` | 0 problème |
| `makemigrations --check` | *No changes detected* |

Les 59 nouveaux tests couvrent : jeton (unicité, longueur, durabilité,
non-séquentialité), identité persistée (date selon rentrée / semaine / jour,
contexte pédagogique, séance sans affectation), mutualisation (un seul objet,
addition des effectifs, refus du porteur et des doublons, retrait),
rattachement des présences (survit à la mutualisation, au retrait, au
changement de statut), non-régression de la clé `statut` historique, routes,
API, permissions et audit.

### Performance

Référence relevée **avant** toute modification, rejouée **après** :

| Mesure | Avant | Après |
|---|---|---|
| Import 3 500 étudiants | 16 132 ms | 16 886 ms |
| Génération | 17 942 ms | 16 788 ms |
| **Séances placées** | **2 360** | **2 360** |
| Non placées | 0 | 0 |
| Groupes | 59 | 59 |
| Statut global | COMPLETE | COMPLETE |

Les résultats sont **identiques** ; le temps total passe de 34 074 ms à
33 674 ms (écart de mesure, pas de dégradation).

### Absence de N+1

`prefetch_related('groupes_lies')` a été ajouté à `_seances_filtrees`, qui
prévenait déjà le N+1 du contexte pédagogique. Mesuré sur les 7 EDT réels :

```
EDT       séances  mutual.   requêtes  par séance
7               5        —          3         0.6
6               5        —          3         0.6
5               5        —          3         0.6
4               5        —          3         0.6
3               5        —          3         0.6
2               5        —          3         0.6
1               4        —          3         0.8
7               5        2          3         0.6   ← avec mutualisation
```

**3 requêtes constantes**, quel que soit le volume et même mutualisé : le
compteur ne dépend pas du nombre de lignes, qui est le signe attendu.

### Démonstration sur données réelles

Scénario complet exécuté sur la base locale, en transaction annulée :

```
1. ÉTAT RÉEL : 34 séances, 34 jetons, 34 dates, 30 avec UE, 3 390 pointages
2. Séance n°5 — « Biomécanique du geste »
   Jeton 0MxUzYuQZ5MBvkowvTceQlDK2cq_3zpYKp777qtrzkM · 2026-09-28
   S3 · EM-S3-UE01 · L2-G2 · effectif 30 · non mutualisée
3. MUTUALISATION avec L1-G1, L1-G2
   Séances avant 34 → après 34   → UN SEUL OBJET ✔
   Groupes concernés ['L2-G2', 'L1-G1', 'L1-G2'] · effectif cumulé 100
4. PARCOURS EDT → séance → QR → pointage
   Jeton scanné → séance n°5 résolue (2026-09-28, LUNDI 06:00–07:00, Amphi 300)
   Pointage créé → rattaché à la séance : OUI ✔ · atteignable par le jeton : 121
   Statut porté à CONFIRMEE → jeton inchangé : OUI ✔
5. BASE INCHANGÉE (transaction annulée) : 34 séances, 3 390 pointages, 0 groupe lié
```

## 6. Ce qui n'a PAS été fait

* **Le canevas des créneaux n'est pas touché.** L'écart entre les 24 créneaux
  officiels et les 56 présents en base reste en attente de l'arbitrage de
  l'utilisateur. Aucune commande `--creer-manquants` n'a été lancée.
* Aucune suppression de données, aucune purge, aucune intervention sur la VPS.
* Les trois API existantes conservent leur contrat : la clé `statut`
  (ACTIVE/ANNULEE) est inchangée, `Pointage.seance_edt` reste la source du
  lien vers la présence.

## 7. Prochains chantiers

Dans l'ordre validé : **indicateurs (§10)** → campagne complète → tests de
charge 3 500 puis 15 000 → arbitrage du canevas.
