# Livrable 4 — Anciens sous-modules : conservés, modifiés, supprimés

## 4.1 Méthode de décision

Un sous-module n'est conservé que s'il correspond à **un besoin métier réel attesté** (document source, chaîne LMD, ou dépendance technique d'un autre module). Il est supprimé s'il porte une logique étrangère à l'INJS (SYGEP, CPFAE, concours externes) ou s'il fait doublon avec un référentiel unique.

## 4.2 Tableau de décision

| # | Ancien sous-module | Écran / route | Devenir | Motif |
|---|---|---|---|---|
| 1 | Tous les référentiels | `/referentiels` | **Remplacé** | Devient le *Tableau de bord* de la refonte : cartographie catégorisée, complétude, provenance. L'ancien écran à onglets est conservé sous `/referentiels/edition` |
| 2 | Années académiques | `/referentiels/annees` | **Conservé** | Cycle de vie riche (clôture, réouverture, acte courant) non reproductible en CRUD simple ; déclaré `editable = False` dans le registre |
| 3 | Établissements & sites | `/referentiels/etablissements` | **Conservé** | Gestion hiérarchique site → bâtiment → salle ; la refonte apporte la provenance (`source_document`, `fiabilite`) |
| 4 | Formations (cycles) | `/referentiels/formations` | **Conservé + enrichi** | Le modèle `RefFormation` gagne la FK `filiere` et `RefVague.categorie` ; l'écran reste l'écran métier |
| 5 | « Types de formation » | `/referentiels/filieres` | **Signalé comme doublon** | L'écran édite `scolarite.TypeFormation` (Licence/Master/Initiale/Continue) qui recouvre partiellement `RefTypeCursus`. Il reste en place (dépendances FK) mais ne doit plus faire foi (anomalie **A-53-01**) |
| 6 | UE / ECUE | `/referentiels/ue-ecue` | **Conservé** | Seul écran capable d'éditer la ventilation UE → ECUE ; aucun écran générique ne peut le remplacer |
| 7 | Niveaux | `/referentiels/niveaux` | **Conservé** | Référentiel partagé par les maquettes ; déclaré non éditable dans le registre |
| 8 | Semestres | `/referentiels/semestres` | **Conservé** | Idem niveaux |
| 9 | « Types de cours & catégories » | `/referentiels/types-cours` | **Conservé** | Écran multi-onglets (catégories, types de candidature, voies d'accès, évaluations, documents) : ne correspond à aucun référentiel unique |
| 10 | Paramètres LMD | `/parametres` | **Conservé** | Paramétrage réglementaire (ECTS, seuils) hors périmètre référentiels |
| 11 | Fonctionnalités (drapeaux) | `/parametres/flags` | **Conservé** | Pilotage d'activation, pas un référentiel métier |
| 12 | Planche de style | `/referentiels/planche-de-style` | **Conservé** | Documentation vivante du socle visuel |
| 13 | Imports de données (Excel) | `/import` | **Conservé** | Import opérationnel (participants, séances) distinct de l'import de référentiels |
| 14 | Écran « Édition des tables » | `/referentiels/edition` (nouveau chemin pour l'ancien écran) | **Conservé, rétrogradé** | Reste utile pour catégories, types de secrétariat, vagues, sites/bâtiments/salles, formations et modules |

## 4.3 Suppressions

Aucune suppression d'écran ni de table n'a été effectuée. Deux suppressions **fonctionnelles** ont été actées, sans destruction de données :

| Élément | Traitement |
|---|---|
| Référentiel « types de formation » comme source de vérité | Retiré de la chaîne décisionnelle : `RefTypeCursus` fait foi. Table conservée (FK `admissions.ReglePiece`, `scolarite.Parcours`) |
| Duplication documentaire F5 (organisation actuelle) | Non importé : F2 est la source retenue |

## 4.4 Ce qui a été corrigé dans les sous-modules conservés

| Sous-module | Correction apportée |
|---|---|
| Formations (cycles) | FK `filiere` ajoutée ; la réconciliation des cycles passe par `RefFiliere.code_dossier` (F01…F08), plus jamais par le libellé |
| Sites / Bâtiments / Salles | Champs `source_document` + `fiabilite` ajoutés (migration `formations.0100`) |
| Vagues | `categorie` ajouté (migration `formations.0099`) |
| Référentiels du socle | `fiabilite` ajoutée aux 8 tables historiques (migration `referentiels.0002`) |
