# PHASE 5 — chantier 2 : indicateurs de pilotage (§10)

**Statut : livré et vérifié** — base locale uniquement, aucune intervention production.

Objet : donner à un responsable les chiffres qui lui permettent d'arbitrer un
emploi du temps, au lieu de le laisser juger à l'œil.

---

## 1. Le problème

Aucun indicateur EDT n'existait. Le `dashboard` de l'application couvre
l'établissement (finances, admissions, examens, logistique, présences) — pas
l'emploi du temps. Pour répondre à « cet EDT est-il complet ? », « telle salle
est-elle sous-employée ? », « tel enseignant est-il surchargé ? », il fallait
compter à la main.

Le moteur produisait déjà des métriques (`taux_couverture`, `heures_placees`,
`seances_non_placees`, `nb_conflits_critiques`) dans `GenerationResult`, mais
uniquement **à l'issue d'une génération**, en mémoire, jamais persistées ni
exposées pour un EDT déjà publié.

## 2. Ce qui a été ajouté

Un module de calcul **`edts/moteur/indicateurs.py`** et deux endpoints. Aucun
fichier existant n'a été modifié en profondeur : `api_lmd.py` et `urls.py` ont
reçu un ajout en fin de fichier (ou une ligne de route).

### Sept familles

| Famille | Ce qu'elle répond |
|---|---|
| **couverture** | Cet EDT est-il complet ? Combien manque-t-il, en séances et en heures ? |
| **occupation des salles** | Telle salle est-elle sous-employée ? Trop grande pour ce qu'on y met ? |
| **charge des enseignants** | La répartition est-elle équilibrée ? |
| **répartition** | Le vendredi est-il vide ? Tel niveau est-il sous-doté ? |
| **conflits** | Combien de conflits ouverts, et lesquels ? |
| **assiduité** | Les séances sont-elles effectivement suivies ? |
| **mutualisation** | Combien de séances partagées — donc de salles économisées ? |

## 3. Quatre décisions structurantes

### Le volume attendu n'est pas recalculé

Les besoins viennent de `besoins.calculate_teaching_needs`, qui est déjà la
référence du moteur (`nb_seances = max(1, round(volume / duree))`). Un
indicateur qui produirait un chiffre différent du moteur serait un mensonge de
pilotage. Un test vérifie l'égalité.

### Le périmètre des besoins suit la population de l'EDT

C'est la correction la plus importante du chantier. Calculés sur l'année
entière alors que l'EDT ne couvre qu'un groupe, les besoins donnaient une
couverture de **0,08 % pour un EDT réellement complet** — un chiffre faux, donc
pire qu'une absence d'indicateur.

Les besoins sont désormais filtrés sur le groupe (population `GROUPE`) ou la
formation (population `FORMATION`). Quand la population n'est pas filtrable par
le moteur (population `ENSEIGNANT`), le calcul reste annuel **et le fait est
dit** via la clé `perimetre_besoins` (`EDT` / `ANNEE` / `GLOBAL`), afin que le
taux ne soit pas pris pour une contre-performance.

### Le tableau de bord ne déclenche aucune écriture

`services.detecter_conflits` **crée et réactive** des lignes `ConflitCreneau`.
Un tableau de bord ne doit jamais modifier ce qu'il mesure : les conflits sont
donc comptés depuis l'existant. Un test l'atteste.

Par la même logique, `deja_calcule` distingue « aucun conflit » de « jamais
contrôlé » : sans cette clé, un zéro affiché avant la première détection
laisserait croire à un EDT vérifié alors qu'il n'a jamais été contrôlé.

### Une donnée absente est `None`, jamais `0`

Un taux sur une base inconnue vaut `None` : afficher « 0 % » pour une capacité
de salle absente ferait croire à une contre-performance réelle. Même motif que
la contrainte C4, qui ne traite jamais une capacité NULL comme « suffisante ».

## 4. API

Deux routes, déclarées **avant** `lmd/<int:pk>/…` pour que le littéral
`indicateurs` ne soit pas capté comme un identifiant d'emploi du temps.

| Route | Objet |
|---|---|
| `GET /api/edts/lmd/indicateurs/` | Périmètre libre — filtres `annee`, `groupe`, `formation`, `emploi_du_temps` |
| `GET /api/edts/lmd/<pk>/indicateurs/` | Un EDT, périmètre de besoins aligné sur sa population |

Permission : lecture pour tout authentifié, écriture réservée à la
planification (`IsEdtReadOnlyOrPlanification`) — mêmes droits que le reste de
la couche LMD.

`?famille=` restreint la réponse à une seule famille : un écran qui n'affiche
qu'un bloc ne paie pas le calcul des autres. Une famille inconnue renvoie
`400` avec la liste des familles disponibles, sur les deux endpoints.

## 5. Vérifications exécutées

Toutes les commandes ci-dessous ont été **réellement exécutées**.

| Portée | Résultat |
|---|---|
| Nouveaux — `edts.tests.test_phase5_indicateurs` | **67 tests OK** |
| Non-régression — `edts` + `presences` | **717 tests OK** (650 avant + 67) |
| `manage.py check` | 0 problème |

Les 67 tests ne vérifient pas que les indicateurs *se calculent*, mais qu'ils
sont *justes* : périmètre des besoins, capacité NULL, absence d'écriture,
égalité avec le moteur, chaînage des présences d'une séance mutualisée.

### Coût SQL — pas de N+1

Les durées de créneaux sont chargées en une requête (le canevas est petit :
56 lignes) puis jointes en mémoire ; les séances passent par `values_list`.

```
EDT     séances   requêtes   par séance
7             5         16          3.2
6             5         16          3.2
5             5         16          3.2
4             5         16          3.2
3             5         16          3.2
2             5         16          3.2
1             4         16          4.0
```

**16 requêtes constantes** : 4 séances ou 5, le compte est identique. Sur
l'ensemble des 34 séances (tous EDT confondus) : 14 requêtes. Le compte ne
dépend pas du volume, qui est le signe attendu en vue des 15 000 étudiants.

### Démonstration sur données réelles

Exécutée sur la base locale (34 séances, 7 EDT, 779 affectations, 3 390
pointages) :

```
1. COUVERTURE
   Séances placées .......       34
   Séances attendues .....     6222   (moteur : mêmes chiffres)
   Heures placées ........    63.00 / 12000.00 attendues

2. OCCUPATION DES SALLES — 6 salles, 55 h occupées / 107 h de canevas
   · Salle de cours LMD 04   5 séances  10.0 h  occup.  9.35 %  rempl. 100.0
   · Salle de cours LMD 03   5 séances  10.0 h  occup.  9.35 %  rempl.  75.0

3. CHARGE DES ENSEIGNANTS — 19 enseignants
   Heures min / max ......   2.0 / 10.0     Écart min-max .........     8.00
   · Bamba Wilfried    10.0 h  5 séances  5 UE
   · Jean MARTIN        8.0 h  4 séances  0 UE

4. RÉPARTITION
   Par jour    : LUNDI 8, JEUDI 7, MARDI 7, MERCREDI 6, VENDREDI 6
   Par niveau  : M1 20, L2 10, NON RENSEIGNE 4

5. ASSIDUITÉ — 3 359 pointages, 30 séances suivies, taux de présence 93.24 %

6. MUTUALISATION — 0 séance mutualisée (état réel de la base)

7. PAR EDT — le périmètre suit la population
   EDT  population    séances  attendues   taux h   périmètre
   7    GROUPE              5         60     8.7 %         EDT
   5    GROUPE              5         36   14.29 %         EDT
   1    ENSEIGNANT          4       6222    0.07 %       ANNEE

Temps de calcul complet : 110 ms
```

Deux lectures honnêtes de ces chiffres :

* La couverture globale (0,55 %) ne reflète pas un défaut de génération, mais
  le fait que la base locale ne contient que des **EDT d'exemple** (5 séances
  chacun) face aux 6 222 séances que l'année complète exige.
* « Jean MARTIN — 0 UE » correspond aux 4 séances sans rattachement
  pédagogique déjà relevées au chantier 1 : l'indicateur rend visible un écart
  de données réel, ce qui est précisément son office.

## 6. Ce qui n'a PAS été fait

* **Le canevas des créneaux n'est pas touché** (24 officiels contre 56 en base)
  — arbitrage toujours en attente.
* Aucun écran frontend : l'ordre validé place la campagne complète avant la
  consolidation de l'interface. Le socle API est prêt à être consommé.
* Aucun export (CSV/PDF) des indicateurs — à ajouter en même temps que l'écran.
* Aucune suppression, aucune purge, aucune intervention production.

## 7. Prochains chantiers

Dans l'ordre validé : **campagne complète** → tests de charge 3 500 puis
15 000 → arbitrage du canevas.
