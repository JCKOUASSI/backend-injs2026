# U0 — Inventaire des comptes (photographie du 2026-09-13)

> Extraction chiffrée régénérable :
> [`inventaires/2026-09-13-inventaire-comptes.md`](inventaires/2026-09-13-inventaire-comptes.md),
> produit par `python manage.py inventaire_habilitation --comptes`.
> Ce document décrit la méthode, le parc de démonstration et les
> conventions ; les chiffres exacts sont dans le rapport daté en annexe.

## 1. Méthode

```bash
cd backend
python manage.py inventaire_habilitation --comptes \
  --sortie ../docs/curp/inventaires/$(date +%F)-inventaire-comptes.md
```

La commande est **strictement en lecture seule**. Elle compte :

- les totaux (comptes actifs/inactifs, `is_staff`, super-utilisateurs) ;
- la répartition par rôle (`User.role`) et les comptes sans rôle ;
- les comptes jamais connectés ;
- les comptes de secrétariat sans rattachement (anomalie potentielle) ;
- les comptes portant plusieurs groupes `ROLE_*` (voir écart E1 dans
  `01-etat-des-droits.md`) ;
- la base inspectée.

Les doublons d'identité, comptes partagés et comptes sans titulaire sont
hors d'U0 : ils seront instruits en U8 (la commande les signale, elle ne
les corrige pas).

## 2. Parc au moment de la photographie

Base de démonstration SQLite (assimilée recette) après ensemencement U0 :

- **15 comptes au total, 15 actifs, 0 inactif** ;
- **4 accès admin Django (`is_staff`)** : `admin` (super-utilisateur),
  `temoin_admin`, `temoin_chef_cpfae_admin`, `temoin_cpfae_admin` ;
- **1 super-utilisateur** : `admin` ;
- répartition couvrant les 12 rôles (les rôles de secrétariat ont deux
  comptes, un par secrétariat) ;
- 2 secrétariats de démonstration : `SECR-DEMO-A`, `SECR-DEMO-B` ;
- 2 participants témoins : `TEMOIN-PART-A`, `TEMOIN-PART-B` ;
- 0 compte de secrétariat sans rattachement, 0 compte multi-groupes.

## 3. Les 14 comptes témoins

| Identifiant | Rôle | Secrétariat | Canal attendu |
|---|---|---|---|
| `temoin_admin` | ADMIN | — | web |
| `temoin_chef_cpfae_admin` | CHEF_CPFAE_ADMIN | — | web |
| `temoin_cpfae_admin` | CPFAE_ADMIN | — | web |
| `temoin_direction` | DIRECTION | — | web |
| `temoin_chef_secretariat_a` | CHEF_SECRETARIAT | SECR-DEMO-A | web |
| `temoin_chef_secretariat_b` | CHEF_SECRETARIAT | SECR-DEMO-B | web |
| `temoin_secretariat_a` | SECRETARIAT | SECR-DEMO-A | web |
| `temoin_secretariat_b` | SECRETARIAT | SECR-DEMO-B | web |
| `temoin_finance` | FINANCE | — | web |
| `temoin_archive` | ARCHIVE | — | web |
| `temoin_encadrant` | ENCADRANT | — | web (badgeage mobile possible) |
| `temoin_superviseur` | SUPERVISEUR | — | web |
| `temoin_formateur` | FORMATEUR | — | **mobile uniquement** |
| `temoin_auditeur` | AUDITEUR | — | **mobile uniquement** |

Adresses de démonstration : `<identifiant>@recette.injs.local` (domaine
réservé, aucune adresse réelle).

### Secret des mots de passe

- Les mots de passe ne sont **pas documentés dans le dépôt**. En
  démonstration locale, ils sont communiqués sous pli séparé (document
  hors dépôt remis avec la procédure de démo) et surchargés par la variable
  `COMPTE_TEMOIN_MOT_DE_PASSE`.
- En **intégration continue**, un mot de passe jetable est injecté par
  variable d'environnement dans l'étape de fumée (`.github/workflows/ci.yml`)
  ; il ne vaut que pour la base PostgreSQL éphémère du build.
- Sur une future vraie base de recette, la variable
  `COMPTE_TEMOIN_MOT_DE_PASSE` est **obligatoire** (le défaut de code n'a
  vocation qu'à faciliter la démonstration locale) ; ces comptes n'ont pas
  vocation à être créés en production.
- La commande ne modifie **jamais** le mot de passe d'un compte existant
  (idempotence sans écrasement).

## 4. Création et rejeu

```bash
cd backend
# Création / mise à jour idempotente (jamais de suppression, S5) :
python manage.py creer_comptes_temoins

# Parcours de fumée complet (91 vérifications), auto-création incluse :
python manage.py fumee_authentification --tous --creer
```

Le retrait des comptes témoins et la restauration de la base sont décrits
dans [`00-restauration.md`](00-restauration.md) : désactivation plutôt que
suppression physique, ou réinitialisation de la base jetable.

## 5. Limites connues de l'inventaire U0

- L'inventaire caractérise l'état, il ne détecte pas encore la qualité des
  titulaires (comptes partagés, doublons, comptes orphelins) → U8.
- Les garde-fous d'administration (interdiction de désactiver le dernier
  administrateur, S7 ; interdiction d'auto-élévation, S6) n'existent pas
  encore en U0 → U4.
