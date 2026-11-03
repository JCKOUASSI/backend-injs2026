# Livrable 1 — Inventaire des fichiers sources

**Mission 53 — Refonte du module « Référentiels » INJS**
Sources examinées : 5 fichiers texte déposés par le commanditaire (dossier `/tmp/arena-coding-uploads`, non persisté). Toutes les feuilles ont été lues intégralement, y compris les sections hors sujet signalées plus bas.

> Convention de fiabilité reprise dans tout le module :
> `OFFICIEL` = la source l'atteste explicitement · `MODELISE` = la source le présente comme une proposition ou une reconstitution · `CADRAGE` = valeur nécessaire au fonctionnement mais non attestée par un document · `A_RENSEIGNER` = aucune source, aucune supposition.

---

## F1 — « Formations et Modules INJS »

| Élément | Contenu observé | Exploitation |
|---|---|---|
| 1. Établissements | 2 écoles supérieures : **ENSEPS** (Éducation physique et sportive) et **ENSEP** (Éducation permanente) | `RefEcole` (2) |
| 2. Mentions | **STAPS** (rattachée ENSEPS), **STASE** (rattachée ENSEP) | `RefMention` (2) + FK école |
| 3. Filières | 8 filières métier numérotées **F01 → F08** : Éducation et Motricité, Entraînement Sportif, Management du Sport, Activités Physiques Adaptées, Andragogie, Loisir, Entrepreneuriat jeunesse, Gérontologie | `RefFiliere` (8) + `code_dossier` |
| 4. Cycles | F01–F04 ouvrent chacune un cycle **Licence** et un cycle **Master** (soit 8 cycles LMD) ; F05–F08 n'ont **aucun** cycle LMD documenté | 8 `RefFormation` (créés uniquement s'ils manquent) |
| 5. Modules | Nomenclature **module par module**, semestre par semestre pour EM ; listes Licence et Master pour ES, MS, APA ; aucune ventilation UE/ECUE fournie | `RefModuleOfficiel` (**227**) |
| 6. Absences notables | Pas de crédits ECTS, pas de volumes horaires, pas de règles de jury, pas de maquettes UE/ECUE | **Non importé** : ces données n'existent pas dans la source |

**Total exploité : 227 modules officiels**, répartis EM L 58 / EM M 23 / ES L 41 / ES M 12 / MS L 22 / MS M 11 / APA L 43 / APA M 17.

---

## F2 — « Liste des Bâtiments, salles et espaces de formation de l'INJS »

| Élément | Contenu observé | Exploitation |
|---|---|---|
| Site | **INJS Marcory**, Abidjan | `formations.RefSite` (1, `OFFICIEL`) |
| Bâtiments | 16 bâtiments nommés (administratif, amphis, salles de cours, labos, gymnases, terrains…) | `formations.RefBatiment` (16, `MODELISE`) |
| Espaces | **166 espaces** décrits avec type, étage et capacité parfois renseignée | `formations.RefSalle` (166, `MODELISE`) |
| Nomenclature de codes | La source proposait elle-même des préfixes (AMPHI, COURS, TD, TP, LABORATOIRE…) | `PREFIXES_CODES` de l'import → `AMP-001`, `SC-001`, `TD-001`, `TP-001`, `LAB-001`, `GYM-001`, `SPORT-001`… |
| Limite déclarée par la source | L'inventaire est présenté comme partiellement reconstitué | Fiabilité `MODELISE`, jamais `OFFICIEL` |

---

## F3 — « Modéliser les volumes horaires (proposition) »

| Élément | Contenu observé | Exploitation |
|---|---|---|
| Répartition horaire | CM / TD / TP / Stage / Total par module, pour **4 cursus** : EM Licence (16), EM Master (12), APA Licence (12), APA Master (11) | `RefVolumeHoraireFormation` (**51**) |
| Statut du document | Intitulé « proposition » : ce sont des valeurs de **modélisation**, pas une norme | Fiabilité `MODELISE`, source conservée |
| Périmètre exclu | Bloc « 8. Maître(sse) d'Éducation Physique et Sportive » (14 modules) → corpus **CPFAE**, hors INJS | **Non importé**, exclusion tracée dans le bilan de la commande |

---

## F4 — « Vagues INJS 2026 »

| Élément | Contenu observé | Exploitation |
|---|---|---|
| Cycle de vie d'une vague | Ouverte → En cours → Clôturée → Terminée, plus l'état Prévisionnelle | `RefStatutVague` (5, `OFFICIEL`) |
| Vagues nommées | Première, deuxième et troisième vague 2026 | `formations.RefVague` (3, existantes, gérées par l'écran historique) |
| Absence | Aucun effectif, aucune date contractuelle dans le texte | Non inventé |

---

## F5 — « En m'appuyant sur l'organisation actuelle de l'INJS »

| Élément | Contenu observé | Exploitation |
|---|---|---|
| Inventaire physique | Reprise quasi intégrale de F2 (mêmes bâtiments, mêmes espaces) | **Aucun import** : doublon strict de F2 → conserver une seule fois |
| Contexte conversationnel | Le fichier mêle à l'inventaire des échanges sans rapport avec les référentiels (cohortes de démonstration, modules d'interface) | Écarté : aucune valeur de référentiel |
| Décision | F5 confirme F2 sans l'enrichir ; il n'est pas une source de vérité supplémentaire | Traçabilité notée, pas de doublon créé |

---

## Synthèse

| Document | Référentiels alimentés | Volume |
|---|---|---|
| F1 Formations et Modules INJS | écoles, mentions, natures de cursus, filières, cycles LMD, modules officiels | 2 / 2 / 5 / 8 / 8 / 227 |
| F2 Bâtiments, salles et espaces | site, bâtiments, espaces | 1 / 16 / 166 |
| F3 Volumes horaires | volumes horaires (modélisation), types d'enseignement (CM/TD/TP/STAGE) | 51 / 4 |
| F4 Vagues INJS 2026 | statuts de vague | 5 |
| F5 Organisation actuelle | — (doublon de F2) | 0 |

**Ce qui n'a pas été importé faute de source** : crédits ECTS par module, maquettes UE/ECUE, règles de jury, décisions académiques V01–V14, effectifs par vague, calendrier des vagues. Le module les présente explicitement comme « Non renseigné » plutôt que de les inventer.
