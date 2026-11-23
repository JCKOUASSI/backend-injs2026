# Rapport — Mission 41 : CRUD des UE / ECUE et cycle de vie Brouillon → Activé → Désactivé

**Dépôt :** `JCKOUASSI/backend-injs2026` · **branche :** `arena/d40e4a41-backend-injs2026`
**Date :** 31 octobre 2026 · **Base de travail :** développement SQLite (`arena.settings_sandbox`), année `2026-2027`
**Périmètre :** dépôt uniquement — aucun environnement de production touché.

---

## 1. Demande et résultat

**Demande.** Sur l'écran « Référentiels → UE / ECUE », pouvoir **créer, visualiser,
modifier et supprimer** les UE et les ECUE, avec les **trois statuts** *Brouillon*,
*Actif* et *Désactivé* — sans bouton inerte, sans statut inventé, sans suppression
destructrice, et sans désactiver aucun test.

**Résultat.** L'écran est passé de la consultation à la gestion réelle. Chaque action
visible a un effet persistant vérifié en base ; les règles métier qui protègent les
données pédagogiques sont tenues **côté serveur** (le serveur reste seul juge) et
l'interface ne propose que ce qui est permis.

| Livrable | État | Preuve |
|---|---|---|
| Créer une UE, la visualiser, la modifier, la supprimer | **Livré et vérifié** | `docs/getinjs/preuves-ue-ecue/01 → 05`, `16` |
| Créer un ECUE sous son UE, le modifier, le supprimer | **Livré et vérifié** | `docs/getinjs/preuves-ue-ecue/06 → 07`, `15` |
| Trois statuts exacts : Brouillon / Activé / Désactivé | **Livré** — aucune autre valeur acceptée ni affichée | `08 → 12` |
| Transitions contrôlées (matrice explicite, refus motivés) | **Livré** | `08`, `14`, tests backend |
| Suppression protégée, jamais en cascade | **Livré** | `13 → 14` |
| Maquette non brouillon → écran gelé, expliqué | **Livré** | `17` |
| Utilisable par un véritable `SECRETARIAT` (pas seulement admin) | **Livré et vérifié** | `18` |
| Tests backend dédiés | **22 / 22 OK** | `scolarite.tests.test_ue_ecue_crud` |
| Tests frontend dédiés | **23 / 23 OK** | `frontend/src/pages/EcranUeEcue.test.jsx` |
| Captures navigateur réelles | **19 JPEG + journaux JSON** | `docs/getinjs/preuves-ue-ecue/` |

---

## 2. Ce qui existait, ce qui manquait

Les API `POST /maquettes/<id>/ues/`, `PATCH/DELETE /ues/<id>/`, `POST /ues/<id>/ecues/`,
`PATCH/DELETE /ecues/<id>/` existaient déjà, mais :

1. **aucun écran ne les appelait** — l'écran « UE / ECUE » affichait deux listes en
   lecture seule : impossible d'ajouter une unité, impossible de la retirer ;
2. **aucun statut** n'existait sur `UE` ni sur `ECUE` : le cycle de vie demandé
   (brouillon → activé → désactivé) n'était pas représentable ;
3. **la suppression d'une UE emportait ses ECUE en cascade** (`on_delete=CASCADE`) :
   un clic pouvait effacer plusieurs lignes pédagogiques sans que rien ne le dise ;
4. **la modification ne vérifiait pas l'état de publication** : un élément publié
   pouvait être réécrit en place ;
5. **les codes en doublon** produisaient une erreur 500 (`IntegrityError` non capturée)
   là où l'utilisateur attend une explication.

---

## 3. Modèle de données

**Migration** `scolarite/migrations/0018_ue_ecue_statut.py` — deux `AddField`, sans
réécriture de données :

```python
statut = models.CharField(
    max_length=20, db_index=True, default='BROUILLON',
    choices=[('BROUILLON', 'Brouillon'), ('ACTIVE', 'Activé'), ('DESACTIVEE', 'Désactivé')],
)
```

- Ajoutée **à l'identique** sur `UE` et sur `ECUE` (`UE.Statut`, `ECUE.Statut`) ;
- défaut `BROUILLON` : les 326 UE et 400 ECUE existants deviennent des brouillons —
  aucune donnée pédagogique n'est déclarée publiée rétroactivement ;
- `db_index=True` : le filtrage par statut est une requête courante (listes, cascades).

**Garde-fous modèle** (`scolarite/models.py`) :

| Règle | Où | Effet |
|---|---|---|
| Maquette non brouillon ⇒ écriture refusée | `_verifier_maquette_modifiable` (déjà là) + statut | 400 côté API |
| Suppression d'UE : statut ≠ brouillon refusé | `UE.delete()` | message explicite |
| Suppression d'UE portant des ECUE refusée | `UE.delete()` | « supprimez-les d'abord (aucune cascade) » |
| Suppression d'ECUE : statut ≠ brouillon refusé | `ECUE.delete()` | message explicite |
| ECUE non brouillon listées | `UE.ecues_non_supprimables()` | lecture pour l'API |

La cascade technique reste déclarée (`CASCADE`) — c'est la suppression *applicative*
qui est protégée : on ne change pas le schéma historique, on empêche d'y arriver.

---

## 4. Contrat d'API

### 4.1 Endpoints

| Méthode | URL | Rôle requis | Rôle |
|---|---|---|---|
| `GET` | `/api/scolarite/maquettes/` | Secrétariat / DFRC | **portée élargie** — le contenant suit le contenu (voir 4.5) |
| `GET` | `/api/scolarite/maquettes/<id>/` | Secrétariat / DFRC | **portée élargie** — idem |
| `GET` | `/api/scolarite/familles/` | Secrétariat / DFRC | **nouveau** — familles de modules (lecture seule) |
| `POST` | `/api/scolarite/maquettes/<id>/ues/` | Secrétariat / DFRC | créer une UE |
| `PATCH` `DELETE` | `/api/scolarite/ues/<id>/` | Secrétariat / DFRC | modifier / supprimer |
| `POST` | `/api/scolarite/ues/<id>/statut/` | Secrétariat / DFRC | **nouveau** — changer de statut |
| `POST` | `/api/scolarite/ues/<id>/ecues/` | Secrétariat / DFRC | créer un ECUE |
| `PATCH` `DELETE` | `/api/scolarite/ecues/<id>/` | Secrétariat / DFRC | modifier / supprimer |
| `POST` | `/api/scolarite/ecues/<id>/statut/` | Secrétariat / DFRC | **nouveau** — changer de statut |

`statut` est désormais sérialisé dans `_serialize_ue` et `_serialize_ecue` : l'écran
n'a pas besoin d'un appel supplémentaire pour connaître l'état d'une ligne.

### 4.2 Matrice de transitions

```python
TRANSITIONS_STATUT = {
    'BROUILLON':  {'ACTIVE'},
    'ACTIVE':     {'DESACTIVEE'},
    'DESACTIVEE': {'ACTIVE', 'BROUILLON'},
}
```

| De → vers | `BROUILLON` | `ACTIVE` | `DESACTIVEE` |
|---|---|---|---|
| `BROUILLON` | — (400 « déjà ») | ✅ | ❌ 409 |
| `ACTIVE` | ❌ 409 | — (400) | ✅ |
| `DESACTIVEE` | ✅ | ✅ | — (400) |

`ACTIVE → BROUILLON` est **refusé** : repasser directement en brouillon un élément
publié effacerait la trace de la publication. Le chemin prévu passe par
« Désactivé » (retiré mais conservé), puis brouillon.

### 4.3 Règles croisées UE ↔ ECUE

- une **ECUE ne s'active pas** sous une UE qui n'est pas `ACTIVE` → 409 ;
- **désactiver une UE désactive ses ECUE actives**, et la réponse **liste les codes
  désactivés** (`ecues_desactivees`) : aucune conséquence muette ;
- **modifier** un élément non brouillon → 409 avec le statut courant ;
- **supprimer** un élément non brouillon, ou une UE portant des ECUE → 400 explicite ;
- maquette `VALIDEE` / `ACTIVE` / `ARCHIVEE` → 400 sur toute écriture (statut compris).

### 4.4 Erreurs rendues lisibles

| Cas | Avant | Maintenant |
|---|---|---|
| Code d'UE déjà présent dans la maquette | `500 IntegrityError` | `400` : « Le code « X » existe déjà dans cette maquette. » |
| Code d'ECUE déjà présent sous l'UE | `500 IntegrityError` | `400` : « Le code « X » existe déjà sous cette UE. » |
| Champs manquants | 400 générique | 400 nommant le champ |
| Statut inconnu | — | 400 + `statuts_possibles` |
| Transition interdite | — | 409 + `transitions_autorisees` |

Toute écriture acceptée est **journalisée** dans `MaquetteJournal` (création,
modification, suppression incluse — la journalisation d'une suppression lit la
maquette *avant* la suppression, l'ancien code lisait `ue.maquette` après `delete()`).

### 4.5 Défaut corrigé : un secrétariat ne pouvait pas choisir sa maquette

`GET /api/scolarite/maquettes/` était réservé à `IsDFRC`, alors que **tout le contenu**
(`/maquettes/<id>/ues/`, `/ues/<id>/`, `/ecues/<id>/`) accepte `IsSecretariatOrDFRC`.
Conséquence : un secrétariat autorisé à créer des UE recevait **403** sur la liste des
maquettes, et l'écran UE/ECUE restait vide pour lui — un écran mort derrière une
permission plus étroite que ce qu'il pilote.

Correction : `maquette_list` et `maquette_detail` passent à `IsSecretariatOrDFRC`.
Aucun droit n'est élargi au-delà de ce que le rôle possède déjà sur le contenu ; les
rôles de lecture (`DIRECTION`, `FINANCE`, `ENCADRANT`, `ARCHIVE`) restent en `GET`
seulement, et un rôle sans droit sur le contenu reste refusé (`AUDITEUR` → 403, testé).

Vérifié en conditions réelles avec un compte `SECRETARIAT` (capture 18) : 21 maquettes
listées, bouton « Nouvelle UE » présent, création d'une UE effective en base
(`id=334`), puis suppression. Le compte de service utilisé pour cette preuve a été
supprimé de la base après coup ; le script (`verif_role_secretariat.mjs`) documente
comment le recréer localement, sans que son mot de passe soit versionné.

---

## 5. Interface

**Fichier neuf** `frontend/src/pages/EcranUeEcue.jsx` (≈ 640 lignes),
branché dans `EcranGenerique.jsx` via `ecran.type === 'ue_ecue'`, déclaré sur les
descripteurs `ue_ecue` et `ref_ue_ecue` de `menu/ecrans.js`.

Structure : **maquette → UE → ECUE**, deux panneaux côte à côte (empilés sous 1200 px).

| Élément | Comportement |
|---|---|
| Sélecteur de maquette | contexte + état (`Brouillon — contenu modifiable`, `Validée — contenu gelé`…) |
| Recherche d'UE | filtre sur code + intitulé |
| `Nouvelle UE` / `Nouvel ECUE` | formulaire modal (code, intitulé, crédits, ordre, semestre, caractère, famille ; coefficient et volumes pour l'ECUE) |
| Bouton crayon | modification, **uniquement en brouillon** |
| Bouton corbeille | suppression après confirmation explicite (`ConfirmModal`) |
| Boutons de statut | une seule action proposée par état : Activer / Désactiver / Repasser en brouillon |
| Bandeau `maquette-verrouillee` | maquette non brouillon : aucun bouton d'écriture n'est rendu |
| Rôle sans droit d'écriture | consultation complète, zéro bouton de gestion |
| Choix d'une UE | clic sur la ligne **ou** bouton focusable sur le code (`aria-pressed`), pour que la sélection ne soit pas réservée à la souris |
| Chargement impossible | message explicite (`erreur-maquettes`) au lieu d'un écran vide ; aucune maquette → explication, pas de bouton mort |

**Rien n'est inventé à l'écran.** La source officielle ne publie les crédits qu'au
niveau de l'**UE** : les ECUE sont donnés par intitulé, sans crédits ni volumes. La
base stocke donc `0` pour 397 ECUE sur 400 — ce qui ne veut pas dire « zéro crédit »
mais « non documenté ». L'écran affiche **« — »** et une légende l'explique, plutôt
qu'un `0` qui serait une donnée fabriquée.

**Mise en page.** Le projet n'embarque pas la grille Bootstrap (`row` / `col-lg-6`
n'y produisent aucune colonne) : les deux panneaux s'empilaient et le tableau
débordait de son cadre. Une feuille dédiée (`src/styles/ueEcue.css`) pose une grille
explicite, rend les tableaux autonomes dans leur panneau et compacte la colonne
d'actions. Mesure après correction : les deux tableaux tiennent exactement dans leur
panneau (552 px de large pour 552 px disponibles), sans débordement.

---

## 6. Preuves d'exécution

### 6.1 Navigateur réel

Parcours exécuté par script Puppeteer sur l'application servie (Vite :3000, API :8000),
compte `admin`, maquette `ÉDUCATION ET MOTRICITÉ — LICENCE — L1 — 2026-2027 (v1)`.
**Chaque étape est vérifiée deux fois** : à l'écran (capture) et par un appel direct à
l'API, indépendant de l'interface. Aucun résultat n'est déduit d'un toast.

| # | Capture | Ce qu'elle montre |
|---|---|---|
| 01 | `01-liste-ue-ecue.jpg` | écran complet : maquette, 18 UE, panneau ECUE |
| 02 | `02-formulaire-nouvelle-ue.jpg` | formulaire de création |
| 03 | `03-ue-creee.jpg` | UE `E2E-UE01` créée, en **Brouillon** |
| 04 | `04-formulaire-modification-ue.jpg` | formulaire pré-rempli |
| 05 | `05-ue-modifiee.jpg` | intitulé modifié, persisté |
| 06 | `06-formulaire-nouvel-ecue.jpg` | création d'ECUE sous l'UE |
| 07 | `07-ecue-cree.jpg` | ECUE listé sous son UE |
| 08 | `08-ecue-activation-refusee.jpg` | activation refusée : UE encore en brouillon |
| 09 | `09-ue-activee.jpg` | UE **Activé** |
| 10 | `10-ecue-active.jpg` | ECUE **Activé** sous une UE active |
| 11 | `11-ue-desactivee.jpg` | UE **Désactivé** — l'ECUE l'a suivi |
| 12 | `12-retour-brouillon.jpg` | retour en brouillon depuis désactivé |
| 13 | `13-confirmation-suppression-ue.jpg` | confirmation avant suppression |
| 14 | `14-suppression-ue-refusee.jpg` | refus serveur : l'UE porte un ECUE |
| 15 | `15-ecue-retour-brouillon.jpg` | ECUE désactivé remis en brouillon |
| 16 | `16-base-nettoyee.jpg` | ECUE puis UE supprimés — base laissée propre |
| 17 | `17-maquette-verrouillee.jpg` | maquette active : écran gelé |
| 18 | `18-role-secretariat.jpg` | même écran avec un compte **SECRETARIAT** : 21 maquettes listées, création effective |

Un second script (`verif_role_secretariat.mjs`) rejoue le parcours « rôle secrétariat »
et vérifie en base la création puis la suppression de la ligne de test : **5/5 OK**.

`journal-verifications.json` contient les 21 vérifications horodatées avec leur
détail (`id`, `statut`, valeurs) : **21 OK, 0 échec**. `journal.json` décrit chacune
des 17 captures ; `explore_ue_ecue.mjs` est le script reproductible qui les produit.

### 6.2 Tests

| Suite | Périmètre | Résultat |
|---|---|---|
| `scolarite.tests.test_ue_ecue_crud` | 22 tests dédiés UE/ECUE | **22 OK** |
| `frontend/src/pages/EcranUeEcue.test.jsx` | 23 tests dédiés à l'écran | **23 OK** |
| Suite frontend complète | 115 fichiers | **2 073 OK** |
| `eslint src` (frontend) | tout le front | **0 erreur, 0 avertissement** |
| `vite build` | production | **construit** (avertissement de taille de chunk pré-existant) |
| 25 modules `scolarite.tests.*` | tout le domaine scolarité | **OK** |
| Harnais officiel `arena/tests_par_groupe.sh` (9 groupes) | tout le backend | **2 814 tests, 9 groupes réussis** |

**Ce que couvrent les tests backend** (extraits) : création renvoyant l'objet complet
en brouillon ; unicité de code → 400 lisible ; modification brouillon acceptée puis
refusée une fois actif ; `ACTIVE → BROUILLON` refusé (409 + transitions) ; statut
inconnu et statut inchangé refusés ; ECUE non activable sous UE brouillon ;
désactivation d'UE entraînant ses ECUE actives **et les listant** ; suppression
d'ECUE actif refusée ; suppression d'UE portant des ECUE refusée **sans cascade** ;
aucune écriture sur maquette validée ; anonyme et rôle non habilité refusés.

**Ce que couvrent les tests frontend** : affichage maquette/UE/ECUE ; trois statuts
exacts, aucune autre action proposée ; filtre de recherche ; « — » au lieu de 0 ;
création d'UE et d'ECUE avec corps typé ; refus local sans appel réseau ; refus serveur
affiché **sans perdre la saisie** ; modification par `PATCH` ; activation et cascade
annoncée ; transition refusée affichée ; maquette validée sans aucun bouton ;
suppression confirmée / annulée / refusée ; rôle sans écriture.

Aucun test n'a été désactivé, ignoré ou contourné.

**Défauts trouvés après la première livraison, et corrigés**

La première version passait tous les tests. Trois défauts réels ne pouvaient pas
être vus par ces tests, et l'ont été en cherchant la faille :

1. **Un secrétariat ne pouvait pas utiliser l'écran** (§4.5) : la liste des maquettes
   lui répondait 403 alors qu'il a le droit d'écrire les UE/ECUE. Corrigé, couvert par
   un test dédié (lecture autorisée pour `SECRETARIAT`, toujours refusée pour
   `AUDITEUR`) et vérifié dans le navigateur avec un vrai compte de ce rôle (capture 18).
2. **Sélection d'UE réservée à la souris** : la ligne était cliquable mais non
   focusable. Le code est désormais un bouton nommé (`aria-pressed`), donc utilisable
   au clavier ; test ajouté.
3. **Écran muet en cas d'échec de lecture** : un refus serveur laissait une page vide,
   sans explication. Un message explicite s'affiche (`erreur-maquettes`), et l'absence
   de maquette est expliquée au lieu de laisser un sélecteur vide ; deux tests ajoutés.

### 6.3 Résultats backend détaillés

Comptes exacts, mesurés module par module (exécution directe, puis harnais officiel) :

**Harnais officiel** — `./arena/tests_par_groupe.sh`, exécuté le 31/10/2026, code de
sortie **0** :

| Groupe | Résultat | Détail |
|---|---|---|
| `scolarite` | RÉUSSI | 481 tests — `OK (skipped=2)` |
| `formations` | RÉUSSI | 272 tests |
| `auth` | RÉUSSI | 242 tests |
| `habilitations` | RÉUSSI | 480 tests |
| `edt` | RÉUSSI | 581 tests |
| `evaluations` | RÉUSSI | 230 tests |
| `pilotage` | RÉUSSI | 201 tests |
| `socle` | RÉUSSI | 188 tests |
| `divers` | RÉUSSI | 139 tests |
| **Total** | **9 / 9 groupes réussis** | **2 814 tests**, 6 ignorés préexistants |

**Modules scolarite mesurés individuellement** (avant le harnais) :

| Module | Résultat |
|---|---|
| `test_ue_ecue_crud` | OK — **22 tests** |
| `test_api_maquettes_injs` | OK — 10 tests |
| `test_maquettes_workflow` | OK — 19 tests |
| `test_pedagogie` | OK |
| `test_referentiels` | OK |
| 20 autres modules | OK (comptes dans les journaux `/tmp/injs-validation/`) |

> **Note d'environnement.** Les exécutions directes `manage.py test <app>` **sans**
> `STORAGES=STORAGE_DE_TEST` échouent sur les pages qui utilisent `{% static %}`
> (`ValueError: Missing staticfiles manifest entry for …`) : le stockage WhiteNoise
> exige un `collectstatic` absent du bac à sable. Ce n'est **pas** un défaut du code —
> c'est pourquoi le harnais officiel pose cette variable. Les résultats de référence
> sont ceux du harnais.

**NOT EXECUTED / non démontré :**

- aucune exécution sur PostgreSQL 16 dans cette session (SQLite uniquement) ;
- le rendu n'a pas été contrôlé sous un autre navigateur que Chromium headless ;
- aucune campagne de charge ni test de montée en charge ;
- l'écran n'a pas été validé sur mobile réel (seul un rendu desktop 1440 × 950 et une
  règle CSS d'empilement sous 1200 px ont été vérifiés).

---

## 7. Ce qui n'est pas fait

1. **Crédits et volumes des ECUE** : la source officielle ne les publie pas. L'écran
   les montre en « — » et permet de les saisir, mais **aucune valeur n'a été inventée**
   pour remplir les 397 ECUE concernés. La décision de saisie revient au métier.
2. **Suppression d'une UE en une seule opération** (UE + ses ECUE) : volontairement
   absente — c'était précisément la cascade que la mission demandait d'éviter.
3. **Permission dédiée « publier un référentiel »** : l'écriture s'appuie sur les rôles
   existants (`IsSecretariatOrDFRC`), sans créer de système d'habilitation parallèle.
4. **Historique de publication** au-delà de `MaquetteJournal` (pas de versionnement
   des maquettes publiées).
5. **Duplication d'UE entre maquettes** : hors périmètre.

---

## 8. Journal des vérifications

```json
{
  "execute_le": "2026-10-31T16:15:13.789Z",
  "maquette_id": "1",
  "verification": [
    {
      "nom": "maquette sélectionnée",
      "ok": true,
      "detail": "id=1"
    },
    {
      "nom": "base de départ sans reste E2E",
      "ok": true,
      "detail": "18 UE au départ"
    },
    {
      "nom": "UE créée en base (API)",
      "ok": true,
      "detail": "id=337 crédits=3 statut=BROUILLON"
    },
    {
      "nom": "statut initial = BROUILLON",
      "ok": true,
      "detail": "BROUILLON"
    },
    {
      "nom": "UE affichée à l’écran",
      "ok": true,
      "detail": ""
    },
    {
      "nom": "modification persistée (API)",
      "ok": true,
      "detail": "UE de test E2E — intitulé modifié"
    },
    {
      "nom": "ECUE créé sous l’UE (API)",
      "ok": true,
      "detail": "id=409 statut=BROUILLON CM=20"
    },
    {
      "nom": "activation ECUE sous UE brouillon refusée",
      "ok": true,
      "detail": ""
    },
    {
      "nom": "UE activée (API)",
      "ok": true,
      "detail": "ACTIVE"
    },
    {
      "nom": "UE activée : plus de bouton Supprimer",
      "ok": true,
      "detail": ""
    },
    {
      "nom": "ECUE activé sous une UE active (API)",
      "ok": true,
      "detail": ""
    },
    {
      "nom": "UE désactivée (API)",
      "ok": true,
      "detail": "DESACTIVEE"
    },
    {
      "nom": "ECUE désactivé avec son UE (API)",
      "ok": true,
      "detail": "DESACTIVEE"
    },
    {
      "nom": "retour en brouillon (API)",
      "ok": true,
      "detail": ""
    },
    {
      "nom": "suppression UE refusée car elle porte un ECUE",
      "ok": true,
      "detail": ""
    },
    {
      "nom": "ECUE désactivé : pas de bouton Supprimer",
      "ok": true,
      "detail": ""
    },
    {
      "nom": "ECUE repassé en brouillon (API)",
      "ok": true,
      "detail": ""
    },
    {
      "nom": "ECUE supprimé (API)",
      "ok": true,
      "detail": ""
    },
    {
      "nom": "UE supprimée (API) : base laissée propre",
      "ok": true,
      "detail": ""
    },
    {
      "nom": "maquette gelée : bandeau de verrouillage affiché",
      "ok": true,
      "detail": "FORMATION DÉMONSTRATION GET-INJS / L1 – DEMO-2026-2027 (v1) — ACTIVE"
    },
    {
      "nom": "maquette gelée : aucun bouton de création",
      "ok": true,
      "detail": ""
    }
  ]
}
```

---

## 9. Conclusion

L'écran « UE / ECUE » tient désormais sa promesse : on y crée, consulte, modifie et
supprime réellement, et les trois statuts demandés existent avec des transitions
contrôlées. Les boutons affichés ont tous un effet vérifié en base ; ceux qui
échoueraient ne sont pas affichés, et quand le serveur refuse, il explique pourquoi.

Ce qui reste ouvert ne relève pas de l'implémentation mais d'une décision métier :
les crédits et volumes des ECUE, non publiés par le référentiel officiel, restent
vides plutôt que remplis d'un zéro trompeur.

Le point le plus utile de cette mission n'est pas le CRUD lui-même, mais celui-ci :
la première version passait ses 41 tests et restait néanmoins inutilisable par le
rôle auquel elle était destinée. Un écran n'est livré que si le rôle qui doit s'en
servir l'ouvre et y écrit — d'où la vérification faite avec un compte `SECRETARIAT`
réel, ajoutée après coup.
