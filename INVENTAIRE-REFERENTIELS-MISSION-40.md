# Inventaire et classement du module « Référentiels »

**Mission 40 — phases 2 et 3** · base de développement `arena.settings_sandbox` · année `2026-2027`
**Sources :** classeur `INJS D'ABIDJAN — RÉFÉRENTIEL EXHAUSTIF DE L'OFFRE DE FORMATION2.xlsx`
(19 feuilles, 1 masquée `Listes`), `RÉFÉRENTIEL EXHAUSTIF DE L'OFFRE DE FORMATION.docx`,
`Dossier_documentaire_officiel_INJS_Cote_d_Ivoire_2026.pdf`, `MODÈLE-DE-RELEVE-DE-NOTESdocx.docx`,
`TEST E2E COMPLET.docx`, et les 18 `.txt` de `dossier_trvx/`.

Ce document répond à une seule question : **que contient réellement le module Référentiels,
et que faut-il garder, compléter ou retirer ?** Chaque ligne est mesurée en base, pas estimée.

---

## 1. Méthode de classement

| Classe | Définition | Règle appliquée |
|---|---|---|
| **A — indispensable** | Le référentiel porte des données dont dépendent les maquettes, les groupes, les emplois du temps ou les inscriptions. | Conservé, éditable, **suppression protégée** côté serveur. |
| **B — transversal** | Utile aux autres modules (admission, finance, évaluation) mais **vide** ou partiel : la source officielle ne fournit pas encore la nomenclature. | Conservé en lecture/écriture, **aucune valeur inventée** ; à alimenter quand la source l'établira. |
| **C — hors référentiel / à retirer** | Ligne ou écran étranger au référentiel INJS : jeu de démonstration, corpus legacy, écran mal libellé. | Écarté du décompte officiel, jamais supprimé en masse ; un écran mal libellé est **renommé**, pas masqué. |

Le décompte des dépendances est calculé en base (`_meta.related_objects`) : c'est ce qui décide
si une suppression est sûre, pas une intuition.

---

## 2. Référentiels de classe A (indispensables)

| Référentiel | Endpoint d'écriture | Lignes | Dépendants mesurés | Décision |
|---|---|---:|---:|---|
| Années académiques | `/scolarite/ref/annees/` | 2 | 41 (groupes 4, maquettes 21, affectations 12, EDT 4) | Conservé — socle temporel |
| Niveaux (L1→M2) | `/scolarite/ref/niveaux/` | 5 | 47 (semestres 10, groupes 4, maquettes 21, affectations 12) | Conservé, suppression refusée si dépendants |
| Semestres | `/scolarite/ref/semestres/` | 10 | 338 (UE 326, affectations 12) | Conservé |
| Cycles de formation (`RefFormation`) | `/formations/ref/formations/` | 13 (12 officiels + 1 démonstration) | 63 (règles LMD 13, parcours 1, groupes 4, maquettes 21) | Conservé ; qualification F01–F08 **en lecture seule** |
| Maquettes / UE / ECUE | `/scolarite/maquettes/` (lecture, détail `/ues/`) | 21 / 326 / 400 | — | Conservé ; l'écriture passe par les commandes d'import, pas par un formulaire libre |
| Parcours | `/scolarite/ref/parcours/` | 1 | 17 (groupes 4, maquettes 1, affectations 12) | Conservé |
| Groupes | `/scolarite/ref/groupes/` | 4 | 24 (affectations 12, créneaux 12) | Conservé |
| Sites / bâtiments / salles | `/formations/ref/sites/`, `/batiments/`, `/salles/` | 1 / 1 / 4 | 5 / 4 / 12 | Conservé (ressource EDT) |

**Volumétrie officielle vérifiée** (`controler_referentiel_injs`, 0 anomalie) : 20 maquettes,
**323 UE**, **397 ECUE**, **1 170 crédits**, 8 filières qualifiées sur 8, 12 familles, 24 créneaux.

---

## 3. Référentiels de classe B (transversaux, à alimenter par la source)

| Référentiel | Endpoint | Lignes | Dépendants | Constat honnête |
|---|---|---:|---:|---|
| Types de formation | `/scolarite/ref/types-formation/` | 4 (LICENCE, MASTER, FORMATION_INITIALE, FORMATION_CONTINUE) | 0 | Ce ne sont **pas** les filières F01–F08 : l'écran a été renommé « Types de formation ». |
| Régimes d'études | `/scolarite/ref/regimes/` | 4 | 0 | Nomenclature générique, non documentée par la source INJS. |
| Statuts étudiant | `/scolarite/ref/statuts-etudiant/` | 12 | 0 | Idem. |
| Vagues | `/formations/ref/vagues/` | 3 | 0 | Documentée par `Vagues INJS 2026.txt`, non reliée aux groupes en base. |
| Catégories de cours | `/formations/ref/categories/` | 0 | 0 | Vide — nomenclature absente de la source. |
| Grades | `/formations/ref/grades/` | 0 | 0 | Vide. |
| Types d'évaluation / de document | `/referentiels/types-evaluation/`, `/types-document/` | 0 / 0 | 0 | Vide. |
| Modes de paiement, types de frais | `/referentiels/…` | 0 | 0 | Vide — relève du module Finance, hors périmètre INJS source. |
| Types de décision, de notification | `/referentiels/…` | 0 | 0 | Vide. |
| Grades enseignant, types d'espace sportif | `/referentiels/…` | 0 / 0 | 0 | Vide. |
| Modules (`RefModule`) | `/formations/ref/modules/` | 0 | 0 | Aucun module créé : aucun doublon de module n'existe (phase 5). |

Aucune de ces lignes n'a été fabriquée pour « faire propre » : un référentiel vide est un fait
mesurable, une nomenclature inventée serait une faute.

---

## 4. Éléments de classe C (hors référentiel)

| Élément | Nature | Traitement |
|---|---|---|
| Formation `FORMATION DÉMONSTRATION GET-INJS` | jeu de démonstration (`manage.py donnees_demonstration_getinjs`) | Aucune filière F01–F08, source explicite ; exclue du décompte officiel ; supprimable par `--supprimer`. |
| 3 UE / 3 ECUE / 18 crédits de ce jeu | conséquence du point précédent | Exclus du contrôle officiel (`controler_referentiel_injs` les nomme et les écarte). |
| 34 éléments hors LMD (4 concours, 13 cycles professionnels, 17 formations à la carte) | offre réelle de l'INJS mais **non LMD** | **Non importés** : ni maquette, ni semestre, ni crédits dans la source. Décision métier tracée dans `TABLEAU-DECISION-34-ELEMENTS.md`. |
| Ancien libellé « Filières » sur `/scolarite/ref/types-formation/` | écran mal nommé | **Renommé** « Types de formation » : le référentiel F01–F08 vit sur les cycles, pas ici. |
| Écran « Type de formation (filière) » dans le formulaire Parcours | libellé ambigu | Renommé « Type de formation (filière) » → conservé mais explicité par l'écran Types de formation ; la filière métier se lit sur le cycle. |

---

## 5. Ce que la phase 3 a changé, concrètement

1. **CRUD réellement disponible** sur types de formation, parcours, niveaux, semestres et cycles
   de formation : formulaire générique branché sur les endpoints existants, sans endpoint neuf.
   Avant, ces écrans étaient des listes sans bouton d'écriture.
2. **Suppression protégée côté serveur** : un `DELETE` est refusé (HTTP 409) dès qu'une ligne
   vivante pointe vers l'objet, avec le décompte par ressource. Avant, supprimer un niveau L1
   emportait ses **10 semestres en cascade silencieuse**.
3. **Qualification lisible, jamais saisissable** : `filiere_code`, `perimetre` et `source` sont
   exposés par l'API des cycles en lecture seule. Un `POST` ne peut pas s'auto-proclamer INJS
   (test dédié) : la qualification reste décidée par `qualifier_referentiel_injs_l6`.
4. **Aucune donnée supprimée** : les éléments de classe C sont écartés du décompte, pas effacés.
5. **Écrans renommés** pour ne plus annoncer « Filières » là où l'API renvoie des types de
   formation, ni « Consultation » sur une page qui écrit en base.

---

## 6. Points ouverts (assumés, non comblés)

| Point | Pourquoi il reste ouvert |
|---|---|
| F04 M1 : 30 ECTS sur 60 | Le semestre S8 est **absent de la source officielle** ; créer des UE serait inventer. |
| F05 à F08 : cycles qualifiés, aucune maquette | La source documente les filières sans publier leurs UE/ECUE. |
| Référentiels de classe B vides | Nomenclature non fournie par la source. |
| 34 éléments hors LMD | Décision métier requise (modèle distinct). |
| Notation (`poids_controle_continu`, `poids_examen`, `seuil_validation_ue`) | Aucune valeur officielle : aucune valeur par défaut inventée. |
| UE / ECUE : pas de formulaire libre | L'écriture d'une maquette reste un acte d'import versionné (`import_maquette`, `configurer_referentiel_injs`), pas une saisie ligne à ligne. |
