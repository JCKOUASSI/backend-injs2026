---
titre: Génération automatique des emplois du temps
soustitre: Quatre moteurs, un seul jeu de contraintes, aucune publication implicite
surtitre: INJS-LMD 2026 · DOSSIER 3 SUR 3
objet: Décrire les quatre niveaux de génération automatique du socle — brouillon glouton, moteur LMD, génération coordonnée, génération annuelle et campagnes — avec leurs entrées, leurs contrôles, leurs statuts de bilan, leurs cas pratiques et leurs limites mesurées.
public: Direction, DFRC, INJS-Admin, chefs de secrétariat, équipe technique
perimetre: backend/injs2026 — application edts (moteur/*, api_lmd.py, api_getinjs.py) et écrans /edt/generation-annuelle et /edt/campagnes
date: 24 novembre 2026
header: Génération automatique des emplois du temps
resume: Le dépôt contient quatre moteurs de génération automatique, de portée croissante : le brouillon glouton d'un EDT existant, le moteur LMD à backtracking, la génération coordonnée de toutes les formations INJS, et la génération annuelle pilotée par campagnes. Tous partagent dix contraintes (C1 à C10) et une règle d'or : générer n'est jamais publier. Ce dossier décrit chaque niveau, ses garde-fous, ses statuts de bilan, ses cas concrets et les limites réellement mesurées du solveur.
sommaire: 1. Les quatre niveaux et la règle d'or; 2. Entrées du moteur — besoins et contraintes C1 à C10; 3. Niveau A — le brouillon glouton; 4. Niveau B — le moteur LMD; 5. Niveau C — la génération coordonnée; 6. Niveau D — la génération annuelle; 7. Niveau D.3 — les campagnes; 8. Amont — dimensionnement et import; 9. Sécurité et traçabilité; 10. Cas pratiques complets; 11. Limites mesurées du solveur; 12. Manuel et automatique en regard; 13. Où lire le code
---

# 1. Les quatre niveaux et la règle d'or

Le dépôt ne contient pas un moteur mais quatre, chacun répondant à une question différente :

| Niveau | Entrée HTTP | Service | Portée |
|---|---|---|---|
| A — brouillon glouton | POST /api/edts/emplois/{id}/generer/ | edts/services.generer_brouillon | un EDT existant |
| B — moteur LMD | POST /api/edts/lmd/generate/ | moteur/generation.generate_schedule | un périmètre LMD, de la formation au groupe |
| C — coordonné | POST /api/edts/lmd/generate-coordinated/ | moteur/orchestration.generer_coordonne | toutes les formations INJS de l'année |
| D — annuel et campagnes | POST /api/edts/lmd/generate-annee/ et /api/edts/campagnes/... | moteur/annee.generer_annee et moteur/campagnes.py | tous les groupes de l'année, piloté par campagne |

note:: La règle d'or est identique aux quatre niveaux : **générer n'est jamais publier**. Le moteur écrit au mieux des brouillons ; la publication reste l'action explicite d'un rôle Direction décrite dans le dossier 2. Aucune route de génération ne publie.

---

# 2. Entrées du moteur — besoins et contraintes

## 2.1 Les besoins horaires

`moteur/besoins.py`, fonction `calculate_teaching_needs`, construit un besoin par ligne d'`AffectationPedagogique` retenue. Seuls les statuts `VALIDEE` et `PLANIFIEE` sont planifiables (`STATUTS_PLANIFIABLES`). Le nombre de séances est calculé par `max(1, round(volume_horaire / durée_moyenne_canevas))`, et le besoin porte aussi l'effectif du groupe, la salle compatible, la nature d'enseignement et le semestre.

Des besoins peuvent être fournis **déjà calculés** (argument `besoins`) : c'est ainsi que sont planifiées les cohortes importées qui n'ont pas d'affectation pédagogique, via `inclure_maquette` et `moteur/besoins_maquette.py`.

Motifs d'exclusion, toujours explicites et jamais silencieux :

| Motif | Signification |
|---|---|
| AFFECTATIONS_PEDAGOGIQUES_VIDES | aucune entrée pédagogique planifiable |
| HORS_PERIMETRE_INJS | entrées hors référentiel INJS-LMD (cycles legacy exclus) |
| CANEVAS_HORAIRE_VIDE | aucun créneau type réel |
| VOLUME_HORAIRE_INCONNU | volume non exploitable |
| C9_CALENDRIER | aucune période autorisée |

## 2.2 Les dix contraintes

| Code | Contrainte |
|---|---|
| C1 | conflit enseignant |
| C2 | conflit groupe |
| C3 | conflit salle |
| C4 | capacité de salle |
| C5 | disponibilité enseignant |
| C6 | disponibilité salle |
| C7 | compatibilité salle / type d'enseignement |
| C8 | cohérence pédagogique |
| C9 | calendrier |
| C10 | volume |

Les contraintes dures bloquent. Les contraintes souples sont paramétrables par `PolitiqueContraintesSouples` : ligne unique en base, désactivée par défaut, avec auteur, date et motif. La priorité effective est : défauts du code < réglage Django < ligne PolitiqueContraintesSouples < paramètre explicite d'une génération.

note:: Le paramètre de génération l'emporte sur tout le reste parce qu'il est explicite et local ; la ligne en base l'emporte sur le réglage Django parce qu'elle est la décision opérationnelle la plus récente, et qu'elle ne demande pas de redéploiement.

## 2.3 Le contrôle des chevauchements

Un correctif documenté dans l'audit : le validateur compare désormais les **intervalles de semaines complets** de deux récurrences, et non plus seulement la semaine de début. Trois tests vérifient le conflit entre [1,4] et [2,3], l'absence de faux conflit entre [1,2] et [3,4], et la conservation de la semaine de fin dans l'adaptateur de séances persistées.

---

# 3. Niveau A — le brouillon glouton

## 3.1 Le service

`POST /api/edts/emplois/<pk>/generer/` appelle `services.generer_brouillon(emploi_du_temps, remplace_existant, max_par_semaine=2)`. L'algorithme est glouton et déterministe :

1. source = affectations pédagogiques VALIDEE ou PLANIFIEE de l'année de l'EDT, restreintes à sa population (formation ou groupe) ;
2. volume horaire converti en nombre de séances hebdomadaires, divisé par la durée moyenne des créneaux types et borné par `max_par_semaine` ;
3. placement sur la grille des créneaux types en évitant l'enseignant occupé, le groupe occupé, la salle déjà prise et les indisponibilités datées quand la rentrée est connue ;
4. regroupement des semaines libres contiguës en un intervalle `[semaine_debut, semaine_fin]` ;
5. écriture dans l'EDT, **uniquement s'il est en BROUILLON**.

## 3.2 Les garde-fous

| Situation | Réponse |
|---|---|
| référentiel horaire vide | statistiques à zéro et motif_echec « Aucun créneau type disponible » |
| séances v2 dans l'EDT | 409 QR_V2_CHEMIN_HERITE_REFUSE |
| statut différent de BROUILLON | 409 « La génération ne s'applique qu'à un emploi du temps en brouillon » |

## 3.3 Ce que « remplacer » veut dire

`remplace_existant=True` supprime **uniquement les lignes générées** (`cree_par=None`). Les poses manuelles d'un agent sont toujours conservées. Relancer la génération ne détruit donc jamais le travail humain.

cas:: **Cas 1 — le brouillon d'appoint.** Sur l'EDT du L1-G1, l'agent lance la génération automatique après avoir posé à la main deux séances de TP. Résultat : six séances générées, deux conservées, deux échecs expliqués (salle Gymnasium déjà occupée sur les semaines 3 à 10). L'agent corrige les deux échecs à la main. Le journal porte `EDT_GENERATION` avec les statistiques, sans le détail des explications d'échec (volontairement exclu du journal pour ne pas le gonfler).

---

# 4. Niveau B — le moteur LMD

## 4.1 Un moteur distinct

`POST /api/edts/lmd/generate/` appelle **exclusivement** `moteur/generation.generate_schedule`. La docstring de la route le dit : elle ne réutilise pas `generer_brouillon`, conservé pour la route historique. Le moteur fait du backtracking borné par un budget de placements (200 000 par défaut).

## 4.2 Paramètres

| Paramètre | Rôle |
|---|---|
| annee_academique_id, ref_formation_id, parcours_id, niveau_id, semestre_id, groupe_ids | périmètre LMD |
| semaines | semaines académiques visées |
| creneaux, salles, duree_seance_heures | ressources et granularité |
| budget | plafond de recherche |
| perimetre_injs_seulement | exclut les cycles legacy (défaut vrai) |
| occupations_initiales | état d'occupation déjà consommé ailleurs |
| besoins | besoins déjà calculés |
| contraintes_souples | politique locale de contraintes souples |

La cohérence de la chaîne Année → Formation → Parcours → Niveau → Semestre → Groupe est vérifiée **côté serveur**. Une formation hors référentiel L6 est refusée : « la formation #N n'est pas une formation INJS validée (périmètre L6) ; les cycles legacy CPFAE/professorat sont exclus. »

## 4.3 Une sortie toujours structurée

`status` prend l'une des valeurs :

| Statut | Signification |
|---|---|
| GENERATION_OK | plan complet |
| GENERATION_PARTIELLE | une partie des besoins n'a pas pu être placée |
| GENERATION_IMPOSSIBLE | aucune séance placée |
| GENERATION_BUDGET_EXHAUSTED | budget de recherche épuisé |

La réponse porte aussi les placements, les non-placés, les conflits, les avertissements, les métriques et le motif d'échec éventuel.

## 4.4 Persistance en deux temps

- `persister=false` (défaut) : **prévisualisation**, le moteur n'écrit rien ;
- `persister=true` : `emploi_du_temps_id` devient obligatoire, l'EDT doit être BROUILLON ou EN_VALIDATION, puis `validation.validate_schedule` est exécuté :
  - rapport **valide** → `publication.persister_plan` écrit les séances dans une transaction, après verrou sur l'année ; réponse **201** ;
  - rapport **invalide** → **rien n'est écrit**, réponse 200 avec `raison_refus_persistance` et la liste des violations.

`remplacer=true` désactive les séances existantes avant réécriture : relancer une génération identique ne duplique jamais.

cas:: **Cas 2 — la prévisualisation qui évite une bêtise.** La DFRC lance une génération sur la formation Management du Sport, niveau L1, semestre 1, semaines 1 à 8, avec persister=false. Bilan : 18 séances attendues, 18 placées, 0 conflit, statut GENERATION_OK. Elle rejoue avec persister=true et emploi_du_temps_id de l'EDT du L1-G1 : 201, 18 séances écrites, statut de l'EDT inchangé (BROUILLON). Elle devra encore soumettre, faire valider et publier.

cas:: **Cas 3 — le refus d'écriture.** Même opération, mais le moteur place 12 séances sur 18 : `validate_schedule` relève une violation C10. Réponse 200, `persiste: false`, `raison_refus_persistance` : « Le validateur a relevé des violations bloquantes : rien n'a été écrit. » L'EDT n'a pas été modifié d'une ligne.

## 4.5 occupations_initiales

Le moteur accepte un état d'occupation déjà consommé ailleurs : séances persistées d'autres EDT, placements de runs antérieurs. Ces entrées participent aux contrôles C1/C2/C3 comme n'importe quel placement du run, sans jamais être modifiées ni persistées. C'est la brique qui rend possible le niveau C.

---

# 5. Niveau C — la génération coordonnée

## 5.1 Le principe

`POST /api/edts/lmd/generate-coordinated/` → `orchestration.generer_coordonne(annee_id, semaines, persister, remplacer)`. La conception est documentée dans `docs/ADR/ADR-007`.

Cinq principes :

1. **périmètre dérivé, jamais fourni** : `formations_a_planifier` retourne les formations INJS qualifiées qui portent des affectations planifiables, triées par identifiant. Aucune liste de formations n'est acceptée de la requête — ce serait un vecteur d'arbitraire ;
2. **ordre déterministe** : les formations sont traitées séquentiellement ; chaque run reçoit l'état d'occupation global (placements des runs précédents et séances persistées des autres EDT de l'année, hors EDT que le remplacement va désactiver) ;
3. **atomicité par EDT** : `persister_plan` est transactionnel pour chaque EDT ;
4. **idempotence** : `remplacer=True` désactive les séances générées antérieures ; relancer ne duplique rien ;
5. **aucune publication** : le parcours de publication reste `/api/edts/lmd/{id}/publish/`.

## 5.2 Les statuts de bilan

| Statut | Signification |
|---|---|
| COORDONNEE_OK | toutes les formations ont un plan complet |
| COORDONNEE_PARTIELLE | au moins un EDT est incomplet |
| COORDONNEE_CONFLITS | des conflits inter-EDT subsistent |
| COORDONNEE_IMPOSSIBLE | rien n'a pu être produit |
| ERREUR | exception pendant un run |

Le bilan expose, par EDT, les besoins, placements, non-placements et motifs ; et globalement, les conflits inter-EDT (lecture seule) et les données inconnues. Une opération dont un EDT est incomplet, non persisté ou en conflit n'est jamais présentée comme pleinement réussie.

## 5.3 Les refus

| Situation | Réponse |
|---|---|
| annee_academique_id absent | 400 ANNEE_ACADEMIQUE_REQUISE |
| année introuvable | 404 ANNEE_ACADEMIQUE_INTROUVABLE |
| année portant des occurrences v2 et persister=true | 409 QR_V2_CHEMIN_HERITE_REFUSE |
| aucune formation planifiable | COORDONNEE_IMPOSSIBLE + MOTIF_AUCUNE_FORMATION + action recommandée |

limite:: Le composant d'interface GenerationCoordonnee.jsx existe et connaît tous ces statuts et motifs, mais il n'est monté dans aucune page : il n'apparaît que dans ses tests. La route est utilisable, l'écran dédié ne l'est pas.

---

# 6. Niveau D — la génération annuelle

## 6.1 La route

`POST /api/edts/lmd/generate-annee/` → `moteur/annee.generer_annee(...)`. Paramètres notables :

| Paramètre | Effet |
|---|---|
| annee_academique_id | année cible, obligatoire |
| semaines | semaines réelles, entiers de 1 à 53 |
| persister, remplacer | écriture dans des EDT BROUILLON, idempotence |
| inclure_maquette | complète les cohortes sans affectation pédagogique (défaut vrai) |
| formation_ids, niveau_ids, groupe_ids, semestre_numeros | périmètre restreint |
| inclure_samedi | retire les créneaux du samedi du canevas |
| eviter_pause_meridienne | retire les créneaux chevauchant 12h-14h |
| max_seances_par_groupe_semaine | quota hebdomadaire, sans masquer les séances écrêtées |
| salle_ids, batiment_ids | lieux autorisés |
| autoriser_plan_partiel | écriture des seules séances conformes, sur accord explicite |

## 6.2 Contrôles d'entrée

Les semaines doivent être des entiers de 1 à 53. Une liste vide est refusée avec « Indiquez au moins une semaine réelle ». Une chaîne « 8 » désigne la seule semaine n°8, pas huit semaines : l'écran le rappelle explicitement. Bâtiments et salles doivent être des listes d'entiers existants et actifs ; un local sélectionné doit appartenir à un bâtiment sélectionné.

## 6.3 Statuts de bilan

| Statut | Signification |
|---|---|
| COMPLETE | tous les groupes du périmètre ont leur plan |
| PARTIELLE | au moins un groupe est incomplet |
| IMPOSSIBLE | rien n'a pu être produit |

Le bilan expose par groupe le statut, les séances attendues, placées et non placées, et le motif d'échec. Un quota hebdomadaire écrêté reste compté comme **attendu non placé** : le quota ne masque aucune séance.

## 6.4 Le garde-fou anti-faux-succès

Avant toute création d'EDT, `annee.py` mesure le nombre d'occurrences et les heures implicites des placements multi-semaines. En cas d'écart de volume, de semaine hors sélection ou de semestres non répartis, le groupe porte `REPARTITION_ANNUELLE_NON_CONFORME`, l'année n'est plus COMPLETE et la persistance est refusée : aucun brouillon n'est créé.

La planification par occurrences unitaires n'est activée que si l'appelant a explicitement ciblé **un seul semestre** et fourni plusieurs semaines. C'est une exigence de qualification, pas un confort.

cas:: **Cas 4 — l'écran de génération annuelle, mode manuel.** La DFRC choisit l'année 2026-2027, filière F04 (Management du Sport), niveau L1, groupe L1-G1, semestre 1, semaines 1 à 8, sans samedi, en évitant la pause méridienne. Elle prévisualise : 24 séances attendues, 24 placées. Elle lance la génération manuelle : l'écran crée une **campagne** puis la démarre, le suivi interroge `/statut/` toutes les 2 secondes et abandonne au bout de 20 minutes. La campagne apparaît ensuite dans `/edt/campagnes` avec son bilan.

cas:: **Cas 5 — le périmètre large refusé sans prévisualisation.** L'agent modifie la sélection après avoir prévisualisé. L'écran invalide la signature d'aperçu et refuse le lancement : « Prévisualisez d'abord ce périmètre exact ». De même, si le bilan annoncé est PARTIELLE, une confirmation explicite affiche la couverture en pourcentage avant toute écriture partielle.

---

# 7. Niveau D.3 — les campagnes

## 7.1 La machine à états

```
BROUILLON → VALIDATION_DONNEES → PRET → EN_COURS
              → TERMINE | TERMINE_AVEC_ANOMALIES | ECHEC
              → VALIDE → PUBLIE
```

## 7.2 Le déroulé, étape par étape

| Étape | Route | Points de contrôle |
|---|---|---|
| créer | POST /api/edts/campagnes/ | année et libellé requis ; libellé unique ; effectif importé mesuré à la création ; autoriser_plan_partiel accepté seulement si booléen JSON explicite, en mode manuel ou automatique, hors simulation ; en mode automatique, calendrier provisoire confirmé et dates confirmées exigés |
| préparer | .../donnees-pretes/, valider_donnees, marquer_pret | aucune donnée manquante ne doit devenir une génération réussie |
| démarrer | POST .../<pk>/demarrer/ | verrou select_for_update, refus CAMPAGNE_DEJA_EN_COURS ; thread getinjs-campagne-*, réponse 202 ; une simulation force persister=false ; refus si année v2 |
| suivre | GET .../<pk>/statut/ | interrogation toutes les 2 s, délai maximal 20 min côté écran |
| lire le bilan | GET .../<pk>/resultat/ | séances attendues, placées, non placées par groupe, motifs et anomalies |
| valider | POST .../<pk>/valider/ | Direction/Admin ; refus si statut différent de TERMINE, si status_global différent de COMPLETE, s'il existe des anomalies, ou si un EDT échoue aux contraintes ; refus si simulation ; refus si aucun EDT persisté ; chaque EDT est revalidé |
| publier | POST .../<pk>/publier/ | atomique : transaction.atomic, puis publication de chaque EDT ; un seul échec lève PUBLICATION_INCOMPLETE et annule tout le lot |

Autres routes : liste (filtre année et simulation, `?limite=` défaut 200, maximum 1000), historique, détail.

## 7.3 Pourquoi une publication atomique

Un semestre à moitié publié est pire qu'un semestre non publié : les étudiants verraient une partie de leurs séances, les présences ouvriraient des QR sur un périmètre incomplet, et la correction demanderait une dépublication manuelle EDT par EDT. Le lot est donc indivisible.

cas:: **Cas 6 — la campagne partielle refusée.** Une campagne terminée affiche 90 séances placées sur 39 146 attendues, statut PARTIELLE. La Direction tente de valider : refus `VALIDATION_BLOQUANTE` avec statut courant, statut global, nombre d'anomalies. La campagne reste TERMINE et ne peut pas être publiée. C'est le comportement correct : un bilan partiel n'est jamais maquillé en réussite.

cas:: **Cas 7 — la simulation.** L'équipe lance une campagne de simulation pour estimer la faisabilité. Les paramètres portent simulation=true : la génération force persister=false, la validation et la publication sont ensuite refusées (`SIMULATION_NON_PUBLIABLE`), avec l'invitation à transférer le périmètre vers Génération pour créer une campagne distincte.

---

# 8. Amont — dimensionnement et import

Rien ne sert de générer pour une population mal connue. Deux outils précèdent la génération.

| Outil | Route | Ce qu'il produit |
|---|---|---|
| dimensionnement | GET /api/edts/lmd/dimensionnement/?annee=&capacite= | promotions à planifier, groupes nécessaires pour la capacité cible (défaut 60), EDT de groupe à produire (dérivés, jamais imposés), séances attendues d'après les maquettes actives, anomalies à traiter |
| constitution des groupes | POST /api/edts/lmd/dimensionnement/constituer/ | groupes créés, idempotent, mode simulation disponible |
| analyse d'import | POST /api/edts/lmd/import/inscrits/analyser/ | analyse du fichier **sans écriture**, résolution formation / niveau / parcours, motifs de rejet |
| import | POST /api/edts/lmd/import/inscrits/ | import idempotent, journalisé, clé sur année et matricule |
| lecture | GET .../inscrits/, .../inscrits/journal/ | population consolidée, journal des imports |

---

# 9. Sécurité et traçabilité

| Mécanisme | Effet |
|---|---|
| habilitations serveur | IsEdtPlanification, IsEdtValidation, IsEdtReadOnlyOrPlanification : jamais un simple masquage de bouton |
| journal | chaque génération, affectation, transition, résolution et publication laisse une ligne avec acteur et paramètres |
| empreinte | EmploiDuTemps.empreinte, SHA-256 des paramètres de génération |
| isolation v2 | toute année à occurrences v2 refuse les chemins historiques : QR_V2_CHEMIN_HERITE_REFUSE |
| simulation | une campagne de simulation ne valide ni ne publie jamais |
| verrou | select_for_update sur l'année lors de la persistance, pour éviter deux écritures concurrentes |

---

# 10. Cas pratiques complets

## 10.1 Cas A — une génération coordonnée réussie sur deux formations

| Étape | Action | Résultat attendu |
|---|---|---|
| 1 | vérifier que les affectations pédagogiques des deux formations sont VALIDEE | sinon MOTIF_AUCUNE_FORMATION |
| 2 | POST generate-coordinated avec annee, semaines [1..8], persister=false | bilan COORDONNEE_OK, placements par EDT |
| 3 | relire le bilan : besoins, placés, non placés, conflits inter-EDT | conflits OK |
| 4 | relancer avec persister=true, remplacer=true | deux EDT BROUILLON, séances écrites, bilan identique |
| 5 | valider chaque EDT via /lmd/{id}/validate/ | rapports valides |
| 6 | publier via /lmd/{id}/publish/ | PUBLIE, contrôle de complétude indiqué |

## 10.2 Cas B — la couverture réelle, mesurée

Le test de diagnostic reproduit dans l'audit crée 20 inscrits, une maquette active, une UE avec deux volumes (CM 4 h, TD 2 h), un groupe L1 S1, une salle et quatre créneaux de 2 h sur quatre semaines.

| Formation | Niveau | UE / ECUE | Volume prévu | Volume réellement persisté | Couverture |
|---|---|---|---|---|---|
| formation de test | L1 S1 | UE1 / ECUE1 (CM 4 h + TD 2 h) | 6 h / 3 séances | 6 h / 3 occurrences (semaines 1 et 3) | 100 % |
| deux groupes de 12 | L1 S1 | UE1 / ECUE1 × 2 | 12 h / 6 séances | 12 h / 6 occurrences | 100 % |

Aucun conflit C1/C2/C3 du validateur, aucune double occupation de salle, brouillon non publié. Ce résultat qualifie un **périmètre ciblé mono-semestre**, pas une année entière.

## 10.3 Cas C — le contre-exemple qui a motivé le garde-fou

Sur le chemin historique, un besoin de 6 h réparti sur quatre semaines produisait deux blocs récurrents couvrant [1,4], soit 8 occurrences et 16 h : la surprogrammation atteignait 266 % du volume demandé, alors que le bilan annonçait COMPLETE et 3/3 séances, parce que le compteur provenait des besoins et non des occurrences persistées. Depuis, `REPARTITION_ANNUELLE_NON_CONFORME` bloque ce cas avant toute création d'EDT.

---

# 11. Limites mesurées du solveur

Ces limites sont dans le dépôt (`docs/audits/AUDIT_GET_INJS_2026.md`) et sont reprises sans atténuation.

limite:: **Verdict ROUGE pour la génération complète de l'année.** Les campagnes globales de démonstration atteignaient 90 séances placées sur 39 146 attendues, sans groupe complet. Le modèle scolarite.Semestre ne contient pas de dates de début et de fin : découper S1 et S2 par hypothèse serait trompeur, et le socle refuse de le faire.

limite:: **Répartition temporelle.** Le solveur historique représente plusieurs séances demandées par un bloc récurrent couvrant l'intervalle global, sans comptabilité des occurrences matérialisées. La correction existe sous forme de garde-fou (REPARTITION_ANNUELLE_NON_CONFORME) et de chemin par occurrences unitaires, mais l'index d'occupations du solveur ignore encore la distribution temporelle réelle.

limite:: **Échelle.** 5 000 inscrits et 39 146 demandes n'ont pas été rejoués. Aucune mesure de latence ni de mémoire à l'échelle cible n'est disponible. Les tests passent sur fixtures isolées.

limite:: **Interface.** GenerationCoordonnee.jsx n'est monté dans aucune page. La route coordonnée est utilisable par API, sans écran dédié.

note:: Conclusion opérationnelle : la génération automatique est fiable en prévisualisation et sur un périmètre ciblé validé. Elle ne doit pas être présentée comme productrice d'un EDT annuel complet et publiable. Une campagne annuelle globale ne doit pas être lancée sans échantillon validé et sauvegarde préalable.

---

# 12. Manuel et automatique en regard

| Critère | Manuel | Automatique |
|---|---|---|
| Point d'entrée | /edt, puis création et affectations | /edt/generation-annuelle et /edt/campagnes |
| Qui décide du placement | l'agent, sur le référentiel de créneaux types | le moteur, par backtracking borné |
| Contrôles | avertissements à la pose, détection persistée des conflits, C1 à C10 au déplacement LMD et à la validation | C1 à C10 pendant la recherche, puis audit avant écriture |
| Écriture | immédiate, séance par séance, journalisée | seulement si persister=true et si l'audit est valide |
| Statut produit | BROUILLON | BROUILLON, jamais plus |
| Régénération | geste manuel | remplacer=true, idempotent |
| Publication | soumettre, valider, publier | identique, plus le contrôle de complétude, plus la campagne atomique |
| Traçabilité | journal EDT_* et motif de forçage | journal EDT_GENERATION, empreinte, bilan de campagne |

---

# 13. Où lire le code

| Sujet | Fichier |
|---|---|
| Moteur de placement | backend/edts/moteur/generation.py |
| Contraintes C1 à C10 | backend/edts/moteur/contraintes.py, validation.py |
| Besoins horaires | backend/edts/moteur/besoins.py, besoins_maquette.py |
| Canevas officiel | backend/edts/moteur/canevas_officiel.py |
| Persistance d'un plan | backend/edts/moteur/publication.py |
| Génération coordonnée | backend/edts/moteur/orchestration.py, docs/ADR/ADR-007 |
| Génération annuelle | backend/edts/moteur/annee.py |
| Campagnes | backend/edts/moteur/campagnes.py |
| Dimensionnement | backend/edts/moteur/dimensionnement.py |
| Import des inscrits | backend/edts/moteur/import_inscrits.py |
| Routes LMD | backend/edts/api_lmd.py |
| Routes GET INJS | backend/edts/api_getinjs.py |
| Écrans | frontend/src/pages/getinjs/GenerationAnnuelle.jsx, CampagnesGeneration.jsx |
| Limites mesurées | docs/audits/AUDIT_GET_INJS_2026.md |
