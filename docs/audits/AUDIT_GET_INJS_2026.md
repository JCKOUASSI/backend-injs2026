# Audit ciblé — GET INJS / EDT (15 novembre 2026)

**Périmètre vérifié :** branche `arena/a8060ecf-backend-injs2026`, code local `/home/user/backend-injs2026` ; production non modifiée. La copie macOS mentionnée dans la demande n'est pas accessible ici. Les mesures VPS ci-dessous viennent du diagnostic antérieur de la session ; **aucune nouvelle génération globale n'a été lancée**.

## Architecture réellement présente

- `backend/edts/moteur/` : `besoins`, `besoins_maquette`, `canevas_officiel`, `constitution`, `contraintes`, `generation`, `annee`, `orchestration`, `validation`, `publication`, `campagnes`, `dimensionnement`, `import_inscrits`, `interop_presences`. `backend/edts/models.py` porte EDT, affectations, créneaux, campagnes, exécutions et inscrits importés.
- `backend/edts/api_getinjs.py`, `api_lmd.py`, `api_interop.py`, `urls.py` : imports, prévisualisation/génération, campagnes, publication et interop présences. `edts.permissions` : lecture authentifiée ; planification restreinte ; validation/publication direction/admin. **Les permissions sont côté serveur**, pas seulement dans React.
- `frontend/src/pages/getinjs/` : accueil, audit des données, dimensionnement, import, étudiants, génération annuelle, campagnes, référentiels, versions/publication, conception. `get-injs-app/` est principalement documentation/référentiel, **pas un moteur concurrent à recréer**.
- Le solveur est un backtracking déterministe à budget (`generation.py`) sur créneaux et salles réels ; C1–C10 dans `contraintes.py` et `validation.py`. Règles souples configurables via `PolitiqueContraintesSouples`. Les plans partiels ne passent pas la validation C10 en écriture ; la publication demeure distincte et contrôlée.

## Preuves et verdict : **ROUGE pour « génération complète de l'année » ; ORANGE pour le moteur ciblé**

| Vérification | Résultat / limite |
|---|---|
| Campagnes de démo 2 et 3, 177 groupes | Chacune : **90/39 146 séances attendues**, 3 groupes avec placement, 174 sans, 0 groupe complet. Les bilans ne sont pas cumulables. Campagne ciblée 4 : 6/140. Quatre brouillons et 25 affectations actives constatées lors du diagnostic antérieur. |
| Génération et contraintes en tests | Suite locale `edts.tests` + `presences.tests` : 518 tests, 3 erreurs de rendu admin sous stockage statique manifeste sans `collectstatic` ; 24/24 admin passent avec `STORAGES=STORAGE_DE_TEST`. 106 tests ciblés EDT/campagnes passaient avant cet audit. Aucun essai de production. |
| Décompte annuel | `besoins_maquette.py` convertit le volume ECUE en `nb_seances`, mais `generation.candidats` produit **un bloc sur `[semaines[0], semaines[-1]]`** par besoin. `annee.py` transmet tous les besoins dans cette même fenêtre ; quota « hebdomadaire » appliqué au total. Le modèle ne répartit pas les occurrences réelles entre semaines/semestres. |
| Conflits | `contraintes.conflit_ressource` compare jour/heure mais pas semaines ; `orchestration.occupations_persistees` ne retient que celles qui chevauchent l'intervalle global. Une occupation disjointe dans la fenêtre peut être traitée comme un conflit. Le validateur `validation.verifier_conflits` regroupe par `semaine_debut` seulement, pas par chevauchement complet. |
| Écriture | `validation.C10_VOLUME` refuse la persistance d'un plan incomplet ; cela protège contre une fausse publication, mais le résultat « partiel calculé » n'est **pas** une séance écrite. `annee.py` prévalide pour éviter un nouveau brouillon vide (commit antérieur `19b79f7`). |
| Échelle | Tests synthétiques de 480 étudiants rapportés par la suite ; cela ne constitue pas un test de couverture annuelle de 5 000 étudiants. Budget par groupe et backtracking peuvent devenir coûteux en impasse ; pas de mesure de mémoire/latence réelle à 39 146 demandes. |

### Points à ne pas confondre

Le commit `19b79f7` conserve des placements **en prévisualisation** même si une partie échoue, corrige le suivi des besoins de maquette dont l'ID d'affectation est `None` et évite un brouillon vide si C10 refuse. Il ne résout **ni** la répartition annuelle **ni** la publication d'un EDT complet. Les deux boutons manuel/automatique et les cases à cocher de la génération annuelle existent dans la branche, mais la route publique effective du VPS candidat n'a pas été confirmée. Les tests locaux ne prouvent pas le déploiement.

### Priorités

1. **Indispensable (P0 métier) :** modéliser/tester une occurrence par semaine/semaine de semestre, calculer la couverture sur les lignes persistées, comparer les intervalles pour C1/C2/C3, assurer le respect C10 sans fausse récurrence. Ne pas lancer de campagne globale avant validation d'un échantillon et sauvegarde.
2. **Important (P1) :** mesurer durée, budget et mémoire sur échantillons croissants ; bilan « calculé / persisté / publié » distinct, cause d'impasse par groupe, protection des brouillons existants et validation des capacités/disponibilités sur les occurrences.
3. **Souhaitable (P2) :** rapport explicable des conflits et estimation de faisabilité avant campagne ; reprise de campagne persistante, supervision hors threads locaux ; indicateurs par semestre.
4. **Évolution (P3) :** optimiseur spécialisé seulement après preuve qu'une formulation temporelle testée et le moteur actuel ne suffisent pas ; ne pas créer de deuxième moteur sans arbitrage.

**Complément après seconde passe (branche locale) :** `validation.verifier_conflits` compare maintenant les intervalles complets de semaines de deux récurrences, y compris pour les séances déjà persistées. Trois tests vérifient le conflit C1/C2/C3 entre `[1,4]` et `[2,3]`, l'absence de faux conflit entre `[1,2]` et `[3,4]`, ainsi que la conservation de la semaine de fin via l'adaptateur de séances persistées (3/3 OK). La suite `edts.tests` + `presences` passe (693 tests) et la suite backend globale passe (3 143 tests, 9 ignorés). Cela **ne corrige pas** le solveur annuel : il continue de représenter plusieurs séances demandées par un bloc récurrent couvrant `[semaines[0], semaines[-1]]`, sans comptabilité des occurrences matérialisées. Ni les volumes horaires annuels persistés, ni les conflits entre toutes les formations sur un calendrier réel, ni une couverture annuelle complète n'ont été prouvés sur un périmètre représentatif de la démo. Ne pas lancer de campagne annuelle globale ni publier un résultat sur la foi de ces tests synthétiques.

**Conclusion :** prévisualisation et génération réduite testées ; **aucune preuve d'un EDT annuel complet, valide et publié**. Cf. `arena/documentation/DIAGNOSTIC_EDT_ANNUEL_2026.md` pour la chronologie et les chiffres.

## Troisième passe : mesure réelle des occurrences (15 novembre 2026)

**Procédure reproductible :** `cd backend && STORAGES=STORAGE_DE_TEST .venv/bin/python manage.py test edts.tests.test_generation_annee.GenerationAnneeTests.test_diagnostic_couverture_reelle_sur_quatre_semaines --noinput`. La fixture crée dans la base de test 20 inscrits, une maquette active, une UE/ECUE, deux volumes (CM 4 h, TD 2 h), 1 groupe L1 S1, 1 salle et quatre créneaux de 2 h sur quatre semaines. Le test persiste un brouillon, lit les lignes réellement actives et développe chaque intervalle `[semaine_debut,semaine_fin]` en occurrences. Mesure locale du moteur : ~0,02 s (hors montage de la base). Résultat : **test diagnostique 1/1 OK, comportement métier NON conforme**.

| Formation | Niveau | UE/ECUE | Volume prévu | Volume généré récurrent | Écart | Couverture brute |
|---|---|---|---:|---:|---:|---:|
| FORMATION TEST INJS (synthétique) | L1 / S1 | UE1 / ECUE1, CM + TD | 6 h / 3 séances demandées | 16 h / 8 occurrences (2 blocs × 4 semaines) | +10 h / +5 occurrences | 266,7 % (surprogrammation) |

Le bilan du moteur annonce néanmoins `COMPLETE`, `3/3` séances : **le compteur provient des besoins et non des occurrences persistées**. Ni les durées par semestre ni les volumes de l'année complète ne sont validés ; la persistance des deux blocs en BROUILLON ne signifie pas publication. Les anciennes campagnes globales atteignaient seulement 90/39 146 séances attendues chacune ; ce contre-exemple local ne doit pas être extrapolé à ces campagnes.

**Conflits :** les tests déjà exécutés de `edts.tests` (capacité C4, disponibilités C5/C6, cohérence C8, calendrier C9, volume C10, scénarios impossibles, non-publication et protection des versions) et les 3 tests d'intervalles C1/C2/C3 passent sur fixtures isolées ; ce n'est pas une vérification de tous les groupes/enseignants/salles/semestres de l'année. Les périodes disjointes sont autorisées par le validateur ; l'index d'occupations du solveur ignore encore les semaines. Aucune exécution multi-école/multi-semestre représentative n'a été démontrée. **Verdict annuel : ROUGE**, correction temporelle et couverture persistée à concevoir/tester avant toute qualification institutionnelle.

## Quatrième passe : garde contre un faux succès annuel

Le contre-exemple précédent (6 h demandées / 16 h récurrentes proposées sur 4 semaines) reste **vrai pour le solveur**. Dans `annee.generer_annee`, un contrôle conservateur mesure maintenant le nombre d'occurrences et les heures implicites des placements multi-semaines **avant toute création d'EDT**. En cas d'écart de volume, de semaine hors sélection ou de plusieurs semestres non répartis, le groupe porte `REPARTITION_ANNUELLE_NON_CONFORME`, l'année n'est plus `COMPLETE` et la persistance est refusée. Test isolé après correctif : 20 étudiants, 1 ECUE, 3 séances / 6 h demandées ; 8 occurrences / 16 h proposées ; **0 h persistée**, **aucun brouillon créé**, statut `PARTIELLE`, durée moteur ~0,015 s. Un test distinct vérifie qu'un brouillon antérieur reste inchangé. Les appels sur **une seule semaine** conservent provisoirement leur contrat historique ; cela n'établit aucune couverture annuelle. Il s'agit d'une **protection contre des résultats faux**, pas d'une génération annuelle résolue. Le solveur et son index ignorent toujours la distribution temporelle réelle ; pas de qualification multi-école/multi-semestre.

L'ECUE issue de la maquette est désormais copiée dans une FK **nullable** sur `AffectationCreneau` lors de la persistance et consultable par le pointage QR et la supervision, sans déduction par nom. La migration additive `edts.0012` a été créée et testée uniquement dans les bases de tests Django ; **aucune migration en production**, aucun backfill historique. Tests : cohorte importée → séance ECUE, séance explicite → pointage ECUE. Les séances historiques sans FK ni affectation restent non rattachées.
