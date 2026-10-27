# U0 — Références initiales du chantier CURP-INJS

> **Unité U0** : audit des droits, inventaire des comptes, caractérisation du
> comportement existant. **Aucune modification de comportement, aucune
> migration.** Date de la photographie : **2026-09-13**.
>
> Ce document fige l'état de référence *avant* toute évolution du module
> utilisateurs. Les unités U1+ doivent laisser cet état vert ou documenter
> explicitement chaque écart.

## 1. Objet et périmètre d'U0

Livrables de l'unité :

1. une commande d'inventaire strictement **en lecture** du dispositif
   d'habilitation et du parc de comptes ;
2. une commande d'ensemencement **idempotente** de 14 comptes témoins ;
3. un parcours de **fumée** exécutable en CI sur ces 14 comptes ;
4. un paquet de **tests de caractérisation** (110 tests) isolé des tests
   existants (règle R5 : aucun test existant modifié) ;
5. la présente documentation et les rapports datés (`inventaires/`).

Hors périmètre U0 (unités suivantes) : le modèle de profil d'habilitation
(U1), le moteur d'autorisation `est_autorise()` (U2), le référentiel à 35
rôles (U3), les écrans React d'administration des comptes (U4).

## 2. Environnement de référence

| Élément | Valeur |
|---|---|
| Python | 3.11.2 (CI : 3.12) |
| Django | 5.1.4 |
| Django REST Framework | 3.15.2 |
| SimpleJWT | 5.4.0 (PyJWT 2.12.1) |
| Base de production/CI | PostgreSQL 16 |
| Base de démonstration (sandbox) | SQLite (`USE_SQLITE=1`) — considérée comme **recette** faute de base dédiée |
| Cache | LocMem (Redis absent de la sandbox ; l'abstraction Django rend Redis possible sans changement) |
| Applications Django | 26 |

Décision d'adaptation actée : en l'absence de bases recette/production
réelles dans la sandbox, la base de démonstration SQLite sert de support de
recette ; la commande d'anonymisation `anonymiser_recette` reste une dette
DSI à exécuter sur une vraie base de recette.

## 3. État des tests AVANT U0 (référence à ne pas faire régresser)

- Suite backend complète **avant U0** : **1055 tests**, dont **1 échec
  connu et hors périmètre** sur SQLite
  (`referentiels.test_regle4_doublon_libelle_casse_rejete` : 201 au lieu de
  400 ; ce test est vert sur PostgreSQL, c'est un écart de moteur de base,
  il ne doit pas être « réparé » hors de son unité), 3 ignorés ; durée
  ≈ 294 s.
- **Après U0** : **1165 tests** (1055 + 110 tests de caractérisation),
  même échec baseline SQLite unique, 3 ignorés ; durée ≈ 343 s. Le paquet
  de caractérisation pris isolément : 110 tests, tout verts.
- Total de méthodes `def test_` dans le backend : 1613.
- Frontend (`frontend` script `lint`, ESLint) : **0 erreur** sur `src`
  (4 signalements `process` dans `vite.config.js`, hors du périmètre linté) ;
  les tests Vitest et seuils de couverture passent en CI.
- Mobile : projet Flutter `qr_badge_mobile`, `flutter analyze` vert et
  attendu en CI (le canal FORMATEUR/AUDITEUR ne doit pas être touché).

## 4. Parc de comptes avant/après U0

- **Avant** ensemencement (base démo réinitialisée) : 1 compte, le
  super-utilisateur `admin`.
- **Après** `creer_comptes_temoins` : 15 comptes (l'admin + 14 témoins),
  2 secrétariats de démonstration (`SECR-DEMO-A`, `SECR-DEMO-B`) et 2
  participants témoins (`TEMOIN-PART-A/B`) pour la preuve de cloisonnement.
- En CI, la fumée crée ces données elle-même (base neuve éphémère).

## 5. Sources de vérité du code caractérisé

| Sujet | Fichier |
|---|---|
| 12 rôles, 10 permissions métier, `User.secretariat`, `must_change_password` | `backend/authentication/models.py` |
| Ensembles de rôles, hiérarchie, `ROLE_POLICY`, groupes, synchronisation | `backend/authentication/role_groups.py` |
| Permissions DRF (`IsDFRC`, `IsEncadrant`, `IsSecretariat`…) | `backend/authentication/permissions.py`, `backend/formations/api_access.py` |
| Projection pour l'UI (`compute_capabilities`) | `backend/authentication/capabilities.py` |
| Connexion, refus web mobile-only, appairage appareil, cookie HttpOnly | `backend/authentication/views.py` |
| Limiteurs de débit (20/min sur login) | `backend/authentication/throttles.py` |
| Routes auth | `backend/authentication/urls.py` |
| Périmètres par secrétariat (filtrage « à la source ») | `backend/formations/access.py` |
| Synchronisation compte ↔ groupe via signaux | `backend/authentication/apps.py` |
| Appairage des appareils mobiles | `backend/presences` (`DeviceBinding`) |
| Miroir de rôles côté interface (dette, retrait après E4) | `frontend/src/utils/roles.js` (411 lignes) |

Règle constante du chantier (S3) : **le backend reste la seule source de
vérité** ; `capabilities` ne fait que projeter pour l'affichage et aucune
dérogation d'affichage n'ouvre jamais de droit.

## 6. Outils livrés par U0

Toutes les commandes sont sous
`backend/authentication/management/commands/` :

| Commande | Rôle | Écrit en base ? |
|---|---|---|
| `inventaire_habilitation [--comptes] [--sortie F]` | Photographie droits + comptes | Non, lecture seule |
| `creer_comptes_temoins` | Crée/met à jour les 14 témoins et 2 secrétariats | Oui, idempotent, jamais de suppression |
| `fumee_authentification --tous [--creer]` | 91 vérifications de bout en bout (sortie 1 si une seule ligne rouge) | Non pour la fumée ; `--creer` relance la création |

Les tests de caractérisation vivent dans le paquet
`backend/authentication/tests_caracterisation/` (modules `test_01` à
`test_06`).

## 7. Comment rejouer la référence

```bash
cd backend

# Inventaires datés (lecture seule)
python manage.py inventaire_habilitation \
  --sortie ../docs/curp/inventaires/$(date +%F)-etat-des-droits.md
python manage.py inventaire_habilitation --comptes \
  --sortie ../docs/curp/inventaires/$(date +%F)-inventaire-comptes.md

# Tests de caractérisation
python manage.py test authentication.tests_caracterisation -v 1

# Parcours de fumée (crée les témoins si besoin)
python manage.py fumee_authentification --tous --creer
```

## 8. Garde-fous respectés par U0

- **Aucune migration**, aucun changement de modèle, aucune vue modifiée ;
- **Aucun test existant modifié** (R5) : nouveau paquet exclusivement ;
- ajout d'abord, observation avant tout refus (R2/R3) : les écarts
  constatés sont listés dans `01-etat-des-droits.md`, aucun n'est corrigé
  en U0 ;
- aucun `print()` runtime (vérifié par `check_repo_hygiene`, vert) ;
- sorties, journaux, code et commentaires en français ;
- mot de passe des comptes de démonstration non documenté dans le dépôt
  (voir `02-inventaire-comptes.md`).
