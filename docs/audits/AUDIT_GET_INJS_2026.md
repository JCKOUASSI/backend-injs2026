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

**Conclusion :** prévisualisation et génération réduite testées ; **aucune preuve d'un EDT annuel complet, valide et publié**. Cf. `arena/documentation/DIAGNOSTIC_EDT_ANNUEL_2026.md` pour la chronologie et les chiffres.
