# Livrable 13 — Anomalies restantes

Aucune anomalie n'a été « corrigée » par supposition. La commande
`verifier_coherence_referentiels` produit le constat ; la décision reste humaine.

## 13.1 Anomalies ouvertes

| Code | Gravité | Constat mesuré | Cause | Décision proposée | Bloquant ? |
|---|---|---|---|---|---|
| **A-53-01** | Majeure | « Formation continue » existe à la fois dans `scolarite.TypeFormation` et `referentiels.RefTypeCursus` | Le référentiel hérité mélange niveau de diplôme (LICENCE/MASTER) et modalité (INITIALE/CONTINUE) | Fusionner à terme : `TypeFormation` doit devenir un alias de `RefTypeCursus`. Nécessite la migration des FK `admissions.ReglePiece` et `scolarite.Parcours` | Non (les deux tables coexistent sans conflit d'écriture) |
| **A-53-02** | Mineure | 3 vagues existent (`PREMIERE VAGUE`, `DEUXIEME VAGUE`, `TROISIEME VAGUE`) sans code, sans dates et sans statut rattaché | Ces lignes ont été créées avant la refonte ; le document ne donne qu'un exemple illustratif (« Vague 1 », « Vague 2 »…) et aucune date | Qualifier ces vagues depuis la source réelle (calendrier de recrutement) puis rattacher `statut` | Non |
| **A-53-03** | Mineure | 1 cycle sans filière : « Licence STAPS — Sciences et Techniques des Activités Physiques et Sportives » (ligne importée avant la refonte) | Ligne historique antérieure à `RefFiliere` | Rattacher manuellement à STAPS/ENSEPS après validation INJS | Non |
| **A-53-04** | Mineure | Les 3 vagues portent `statut = NULL` alors que le référentiel des statuts existe | Le champ est nouveau (`formations.0099`) ; aucune valeur n'est déductible de la source | Saisie métier | Non |
| **A-53-05** | Majeure | **20 valeurs sans `source_document`** : 6 types d'espace sportif, 1 site, 3 bâtiments, 7 salles, 3 vagues | Ces lignes ont été créées par les missions précédentes, avant l'introduction de la provenance ; l'import ne les a pas écrasées (il n'écrase jamais une donnée qu'il ne produit pas) | Compléter la source au fil de l'eau ; l'écran les affiche comme non sourcées | Non |
| **A-53-06** | Mineure | Aucun module officiel n'est ventilé en UE/ECUE (227 en `A_VENTILER`) | Le document source donne des listes de modules par semestre, pas une ventilation UE/ECUE | Décision pédagogique INJS ; la ventilation sera saisie dans le module Maquettes | Non (mais bloque la génération automatique de maquettes) |
| **A-53-07** | Mineure | `scolarite.pedagogie_validateur.FILIERES` et `scolarite.management.commands.import_referentiel_injs_lmd.FILIERES` dupliquent la liste des 8 filières au lieu de lire `RefFiliere` | Les deux modules sont antérieurs à la table ; un accès DB à l'import de module casserait le chemin « fichier seul » | Remplacer par une lecture paresseuse (cache) quand le chargement applicatif est garanti | Non — **contrôlé** : la commande de cohérence compare code et base et signale toute divergence |
| **A-53-08** | Mineure | Le code `filiere_code` de `RefModuleOfficiel` porte `EM/APA/ES/MS` alors que `RefFormation.filiere_code` porte `F01…F08` | Deux conventions coexistent (héritage) | Conservé : le premier suit la source, le second la nomenclature A-4.5 ; le `help_text` documente explicitement l'écart | Non |
| **A-53-09** | Mineure | 103 modules officiels ont un semestre vide (`''`) | Les listes ES, MS et APA du document ne précisent pas le semestre | Décision pédagogique INJS ; la valeur vide est affichée « — », jamais devinée | Non |

## 13.2 Anomalies corrigées pendant la mission

| # | Anomalie | Correction | Preuve |
|---|---|---|---|
| 1 | Rattachement des modules déduit du **libellé** de filière → APA rattachée à ES, MS rattachée à APA | Réconciliation **exclusive** par `RefFiliere.code_dossier` (F01…F08) + champ dédié (migration `0004`) | `test_filieres_rattachees_par_code_dossier` : 0 module mal rattaché sur 227 |
| 2 | Bloc ES/MS/APA ignoré : seule une clé du dictionnaire était lue → 2 modules importés au lieu de 53/33/60 | Lecture explicite des sous-listes Licence/Master | Comptes finaux conformes à la source |
| 3 | Les modules basés sur `formation__filiere__code` restaient mal rattachés en base | `.exclude(filiere=filiere).update(filiere=filiere)` (convergence) | Bilan d'import : 0 incohérence |
| 4 | `RefModuleOfficiel.semestre` limité aux semestres `S…` : perte des niveaux `M1`/`M2` et des plages `S1-S3` | Champ ouvert à `S\d`, `S\d-S\d`, `M1`, `M2` | APA conserve `S1-S3` / `S4-S6` ; EM Master conserve M1/M2 |
| 5 | Import non reproductible sur base neuve : aucune formation LMD → 0 module importé silencieusement | Étape « Cycles LMD documentés » créant **uniquement** les cycles absents | Base neuve : 227 modules importés |
| 6 | Routes génériques `404`, actions `405`, ViewSets historiques masqués | Cf. livrable 9 | Tests + requêtes réelles |
| 7 | 6 modèles de la refonte absents de l'admin Django | 6 Admin classes enregistrées | `core.tests` complet au vert |

## 13.3 Anomalies corrigées lors de la recette de bout en bout

| Code | Constat mesuré | Correction | Preuve |
|---|---|---|---|
| **A-53-09 (corr.)** | Après « Réactiver », la valeur quittait l'archive mais restait `actif = False` : absente du filtre « Actifs » et de `usables()` | `RefSocle.reactiver()` symétrique de `archiver()` + journal `REACTIVATION` (migration `0006`) | `test_reactivation_remet_la_valeur_en_service` ; recette `200 {archive:false, actif:true}` |
| **A-53-10 (corr.)** | `fiabilite` et `source_document` absents du sérialiseur du socle : la provenance saisie était ignorée sur les 8 routes historiques | Contrat unique dans `RefSocleSerializer` | `test_tracabilite_ecrite_et_relue_sur_toutes_les_routes` |
| **A-53-11 (corr.)** | 6 liens « Consulter » du tableau de bord menaient à des routes React inexistantes ; `filieres` visait `/referentiels/filieres` | Défaut calculé `/referentiels/gestion/{slug}` ; `route_ui=None` → « Sans écran dédié » | `test_route_ui_ne_pointe_que_vers_des_ecrans_existants`, `test_route_api_declaree_existe_vraiment` |
| **A-53-12 (corr.)** | Chaque écriture remplaçait le tableau par un état de chargement | Rechargement silencieux + pastille « Actualisation… » | Recette : filtre utilisable pendant le rechargement |
| **A-53-13 (corr.)** | `smoke_test_injs` figeait sa campagne au 31/10/2026 → 4 tests en erreur dès le 1ᵉʳ novembre | Fenêtre glissante autour du jour courant | `scolarite.tests.test_smoke_command` : 5 tests au vert |

## 13.4 Incohérences documentaires à trancher par l'INJS

| # | Question posée par les sources | Impact |
|---|---|---|
| D-1 | Les listes ES, MS et APA ne précisent **pas** le semestre des modules | Impossible de ventiler ces modules sans décision pédagogique |
| D-2 | F05 (Andragogie), F06 (Loisir), F07 (ECJP), F08 (Gérontologie) n'ont **aucun cycle** LMD documenté, alors qu'elles sont rattachées à l'ENSEP | Le module n'invente ni durée ni diplôme : ces filières restent sans cycle |
| D-3 | Le document des volumes horaires est une **proposition** et ne couvre que 4 cursus | Toute utilisation automatique (charge, EDT) exige validation |
| D-4 | Les « vagues 2026 » ne portent ni dates ni effectifs (exemple illustratif) | Les champs restent vides ; seuls les statuts sont importés comme référentiel |
| D-5 | Les décisions académiques V01→V14 citées par la mission ne figurent dans aucun des cinq documents fournis | Aucune valeur n'est créée : le référentiel `RefTypeDecision` reste vide et l'écran l'annonce honnêtement |

## 13.5 Écarts volontaires entre source et application

| Écart | Justification |
|---|---|
| Le bloc « Maître(sse) d'Éducation Physique et Sportive » (14 modules, doc 3) n'est pas importé | Corpus **CPFAE**, hors périmètre INJS ; l'exclusion est affichée par la commande d'import |
| Les 4 blocs « Professorat Lycée / Collège » ne sont pas importés | Même raison : préparation aux concours du corpus historique |
| Les espaces sans capacité dans le document sont importés sans capacité | Aucune valeur inventée (`null` assumé) |
| Les 3 vagues illustratives du document ne sont pas recréées | Le document précise « Supposons » : ce sont des exemples, pas des données INJS |
