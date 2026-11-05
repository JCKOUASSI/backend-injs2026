# Rapport — Mission complémentaire moteur GET-INJS2026

**Date :** 5 novembre 2026 · **Branche :** `arena/86930808-backend-injs2026`
**Principe directeur :** renforcer le moteur existant, sans recréer l'application,
sans second module EDT, sans donnée inventée.

---

## 1. Audit ciblé (Phase 1) — moteur existant

Le moteur est substantiel et déjà structuré en services dans `backend/edts/moteur/` :

| Brique | Fichier | Rôle constaté |
|---|---|---|
| Besoins (affectations) | `besoins.py` | besoins planifiables depuis les affectations pédagogiques |
| Besoins (maquettes) | `besoins_maquette.py` | séances attendues par groupe depuis les maquettes actives |
| Contraintes | `contraintes.py` (825 l.) | contraintes bloquantes + politique de contraintes souples (`PolitiqueContraintesSouples`) |
| Génération | `generation.py`, `orchestration.py` | génération coordonnée par formation (anti-collision salles/enseignants) |
| Campagnes | `campagnes.py` | campagnes et exécutions **asynchrones**, transitions contrôlées |
| Publication | `publication.py` | publication avec empreinte de génération (traçabilité) |
| Validation | `validation.py` | contrôles avant publication |
| Interop présences | `interop_presences.py` (519 l.) | export des séances officielles vers le socle présences |
| Banc de charge | `benchmark_getinjs` | mesure rejouable en transaction annulée (base intacte) |

`SeanceRegistre` (`models_interop.py`) fournit déjà l'**identité permanente des
séances** : UUID unique, `cle_metier` déterministe (année/semestre/groupe/ECUE/type),
cycle BROUILLON → TERMINEE dont le statut **SIMULATION**, chaînage `seance_origine`
(report/rattrapage), `affectation` en OneToOne `SET_NULL`.

## 2. Cartographie des écarts (Phase 2)

| Exigence | État constaté | Écart | Action réalisée |
|---|---|---|---|
| Nombre d'EDT dérivé des données | `EmploiDuTemps` par population (GROUPE…) ; génération par groupe | Aucun service consolidé ne calcule promotions/groupes/EDT requis | **Nouveau service `dimensionnement.py`** + endpoint |
| 3 500 → 15 000 étudiants sans refonte | Banc de charge existant (paliers 100→14 000) | Palier 15 000 non démontré | **Mesures réelles exécutées** (§5) |
| Groupes paramétrables | `Groupe.capacite_max`, découpage du banc à 60 | Capacité cible non exposée comme paramètre de dimensionnement | Paramètre `capacite_cible` (défaut 60) du service et de l'API |
| Mutualisation des enseignements | **Aucune trace** dans le moteur (recherche `mutualis` vide) | À concevoir (regroupement de promotions sur un même CM) | **Non implémenté** — signalé, pas simulé |
| Contraintes bloquantes vs préférences | Distinction existante (bloquantes + politique souple paramétrable) | — | Conservé tel quel (opérationnel) |
| Simulation sans toucher la production | Statut SIMULATION des séances, campagnes en brouillon, génération non publiée par défaut | Pas d'écran « scénarios » dédié | **Préparé** par l'existant ; pas de nouveau module |
| Séances : identité stable, cycle de vie | `SeanceRegistre` complet (UUID, clé métier, origine chaînée) | — | Conservé (opérationnel) |
| Présences (QR, géoloc…) | Socle d'interop sur les séances officielles | Module de capture non développé (volontairement) | **Préparé**, pas d'application autonome créée |
| Sécurité | Permissions existantes `edts.permissions`, aucun RBAC parallèle | — | Nouvel endpoint branché sur `IsEdtReadOnlyOrPlanification` |
| Anomalies plutôt que données inventées | Motifs d'échec explicites du moteur de besoins | Le dimensionnement ne signalait pas les promotions sans groupe/maquette | Anomalies `PROMOTION_SANS_GROUPE`, `GROUPES_INSUFFISANTS`, `PROMOTION_SANS_MAQUETTE`, `BESOIN_NON_CALCULABLE`, `EFFECTIF_SUPERIEUR_PLUS_GRANDE_SALLE` |

## 3. Architecture complémentaire (Phase 3)

Un seul ajout, dans le style existant : un **service de dimensionnement**
(`backend/edts/moteur/dimensionnement.py`) qui ne crée aucun modèle et réutilise :

- les inscriptions administratives **VALIDÉE** (agrégats SQL `Count(distinct)`) pour
  les promotions réelles (formation × niveau × parcours) ;
- les groupes actifs et leurs capacités ;
- `besoins_depuis_maquette()` pour les séances/heures attendues (maquettes actives) ;
- les référentiels salles/formateurs.

Exposition : `GET /api/edts/lmd/dimensionnement/?annee=<id>&capacite=<n>`
(lecture = tout utilisateur authentifié, via les permissions EDT existantes ;
réponse 400 explicite `ANNEE_ACADEMIQUE_REQUISE` sans année).

## 4. Implémentation (Phase 4)

- `dimensionner(annee_id, capacite_cible=60)` → promotions, groupes
  existants/nécessaires/déficitaires, **emplois_du_temps_a_produire = groupes
  nécessaires** (dérivé, jamais imposé), séances et heures à programmer,
  capacités (salles, plus grande salle, formateurs), anomalies motivées.
- Calcul 100 % par agrégats : pas de N+1 métier, un seul passage du moteur de
  besoins par année.

## 5. Tests et charges (Phase 5) — résultats mesurés

**Tests unitaires/API** (`edts/tests/test_dimensionnement.py`, 9 tests, verts) :
groupes nécessaires dérivés (130 inscrits → 3 groupes à 60, déficit 2), capacité
paramétrable (→ 5 groupes à 30), promotion sans groupe signalée, séances dérivées
de la maquette (3 séances / 6 h), inscriptions non validées ignorées, **échelle par
agrégats (1 200 inscrits créés en masse, comptage exact)**, API 400/200/non-authentifié.

**Charges réelles** (commande existante `benchmark_getinjs`, transaction annulée,
base de démonstration intacte après chaque run) :

| Palier | Import | Génération | Séances placées | Non placées |
|---|---|---|---|---|
| 3 500 étudiants (59 groupes) | 13,4 s | 7,5 s | 2 360 | 0 |
| 15 000 étudiants | 58,3 s | 145,7 s | 10 000 | 0 |

**Vérification sur la base de démonstration réelle** (3 716 inscriptions VALIDÉE) :
48 promotions à planifier, **88 EDT de groupe à produire** (dérivés), 42 groupes
existants, déficit 80, 30 062 séances / 60 314 h attendues depuis les maquettes,
40 anomalies `PROMOTION_SANS_GROUPE`, temps de réponse de l'endpoint ≈ 1,7 s.

**Non-régression :** suite `edts` complète — 462 tests, seules 3 erreurs
`AdminPolitiqueTests` **préexistantes** (reproduites sur arbre propre via `git stash`).

## 6. Chaîne de validation (Phase 6)

Référentiels (maquettes actives, salles 166/166 complétées en cadrage) → Groupes
(dimensionnement : déficits explicites) → EDT (génération coordonnée existante) →
Séances (`SeanceRegistre` à identité permanente) → données présences (interop
existante, alimentée par les séances officielles uniquement). Aucune étape ne
fabrique de donnée : chaque manque devient une anomalie nommée.

## 7. Synthèse finale (état honnête)

- **Opérationnel (existant, conservé) :** génération coordonnée, campagnes
  asynchrones, publication à empreinte, contraintes bloquantes + souples
  paramétrables, registre de séances à identité permanente, banc de charge.
- **Renforcé :** démonstration de charge au palier 15 000 (0 séance non placée).
- **Nouvellement implémenté :** service + endpoint de dimensionnement dynamique
  (promotions/groupes/EDT/séances dérivés, capacité paramétrable, anomalies).
- **Partiel :** simulation (statut SIMULATION et brouillons de campagne existent ;
  pas d'interface de scénarios comparatifs).
- **Préparé :** présences QR/manuelle/géolocalisation — socle `SeanceRegistre` +
  `interop_presences.py` prêts ; capture non développée (conformément à la consigne).
- **Écran frontend (ajouté après arbitrage expert) :** page « Dimensionnement »
  du hub GET-INJS (`/edt/dimensionnement`, entrée de menu après « Génération ») —
  indicateurs dérivés, tableau des promotions, capacité cible paramétrable avec
  recalcul, anomalies affichées telles quelles ; 3 tests d'écran verts, suite
  frontend complète 2 215/2 215, build OK.
- **Non implémenté (assumé, non maquillé) :** mutualisation inter-promotions des
  enseignements (à concevoir à partir des chiffres que l'écran rend visibles) ;
  palier 15 000 non ajouté aux paliers standard du banc (mesure effectuée en
  exécution dédiée).
