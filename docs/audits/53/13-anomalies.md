# Livrable 13 — Anomalies restantes

Aucune anomalie n'a été « corrigée » par supposition. Les commandes `verifier_coherence_referentiels` produit le constat ; la décision reste humaine.

## 13.1 Anomalies ouvertes

| Code | Gravité | Constat mesuré | Cause | Décision proposée | Bloquant ? |
|---|---|---|---|---|---|
| **A-53-01** | Majeure | « Formation continue » existe à la fois dans `scolarite.TypeFormation` et `referentiels.RefTypeCursus` | Le référentiel hérité mélange niveau de diplôme (LICENCE/MASTER) et modalité (INITIALE/CONTINUE) | Fusionner à terme : `TypeFormation` doit devenir un alias de `RefTypeCursus`. Nécessite la migration des FK `admissions.ReglePiece` et `scolarite.Parcours` | Non (les deux tables coexistent sans conflit d'écriture) |
| **A-53-03** | Mineure | 1 cycle sans filière : « Licence STAPS — Sciences et Techniques des Activités Physiques et Sportives » (ligne importée avant la refonte) | Ligne historique antérieure à `RefFiliere` | Rattacher manuellement à STAPS/ENSEPS après validation INJS | Non |
| **A-53-05** | Majeure | **20 valeurs sans `source_document`** : 6 types d'espace sportif, 1 site, 3 bâtiments, 7 salles, 3 vagues | Ces lignes ont été créées par les missions précédentes, avant l'introduction de la provenance ; l'import ne les a pas écrasées (il n'écrase jamais une donnée qu'il ne produit pas) | Compléter la source au fil de l'eau ; l'écran les affiche comme non sourcées | Non |
| **A-53-06** | Mineure | Aucun module officiel n'est ventilé en UE/ECUE (227 en `A_VENTILER`) | Le document source donne des listes de modules par semestre, pas une ventilation UE/ECUE | Décision pédagogique INJS ; la ventilation sera saisie dans le module Maquettes | Non (mais bloque la génération automatique de maquettes) |
| **A-53-08** | Mineure | Le code `filiere_code` de `RefModuleOfficiel` porte `EM/APA/ES/MS` alors que `RefFormation.filiere_code` porte `F01…F08` | Deux conventions coexistent (héritage) | Conservé : le premier suit la source, le second la nomenclature A-4.5 ; le `help_text` documente explicitement l'écart | Non |

## 13.2 Anomalies corrigées pendant la mission

| # | Anomalie | Correction | Preuve |
|---|---|---|---|
| 1 | Rattachement des modules déduit du **libellé** de filière → APA rattachée à ES, MS rattachée à APA | Réconciliation **exclusive** par `RefFiliere.code_dossier` (F01…F08) + champ dédié (migration `0004`) | `test_filieres_rattachees_par_code_dossier` : 0 module mal rattaché sur 227 |
| 2 | Bloc ES/MS/APA ignoré : seule une clé du dictionnaire était lue → 2 modules importés au lieu de 53/33/60 | Lecture explicite des sous-listes Licence/Master (+ filtrage par préfixe `M` pour APA qui mélange les deux) | Comptes finaux conformes à la source |
| 3 | Les modules basés sur `formation__filiere__code` restaient mal rattachés en base | `filter(...).update(...)` remplacé par `.exclude(filiere=filiere).update(filiere=filiere)` (convergence) | Bilan d'import : 0 incohérence |
| 4 | `RefModuleOfficiel.semestre` limité aux semestres `S…` : perte des niveaux `M1`/`M2` et des plages `S1-S3` | Champ ouvert à `S\d`, `S\d-S\d`, `M1`, `M2` | APA conserve `S1-S3` / `S4-S6` ; EM Master conserve M1/M2 |
| 5 | Import non reproductible sur base neuve : aucune formation LMD → 0 module importé silencieusement | Étape « Cycles LMD documentés » (8 cycles F01–F04) créant **uniquement** les cycles absents | Base neuve : 227 modules importés (tests `ImportIdempotentTests`) |
| 6 | Routes génériques `404`, actions `405`, ViewSets historiques masqués | Cf. livrable 9 §9.3 | Tests + requêtes réelles |
| 7 | 6 modèles de la refonte absents de l'admin Django | 6 Admin classes enregistrées | `core.tests` complet au vert |

## 13.3 Incohérences documentaires à trancher par l'INJS

| # | Question posée par les sources | Impact |
|---|---|---|
| D-1 | Les listes ES, MS et APA ne précisent **pas** le semestre des modules | Impossible de ventiler ces 105 modules sans décision pédagogique |
| D-2 | F05 (Andragogie), F06 (Loisir), F07 (ECJP), F08 (Gérontologie) n'ont **aucun cycle** LMD documenté, alors qu'elles sont rattachées à l'ENSEP | Le module n'invente ni durée ni diplôme : ces filières restent sans cycle |
| D-3 | Le document des volumes horaires est une **proposition** et ne couvre que 4 cursus | Toute utilisation automatique (charge, EDT) exige validation |
| D-4 | Les « vagues 2026 » ne portent ni dates ni effectifs | Les champs restent vides ; les statuts seuls sont importés |

## 13.4 Écarts volontaires entre source et application

| Écart | Justification |
|---|---|
| Le bloc « Maître(sse) d'Éducation Physique et Sportive » (14 modules, doc 3) n'est pas importé | Corpus **CPFAE**, hors périmètre INJS ; l'exclusion est affichée par la commande d'import |
| Les 4 blocs « Professorat Lycée / Collège » ne sont pas importés | Même raison : préparation aux concours du corpus historique, non rattachable aux 8 filières INJS |
| Les espaces sans capacité dans le document sont importés sans capacité | Aucune valeur inventée (`null` assumé) |
