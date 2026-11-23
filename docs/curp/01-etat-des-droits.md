# U0 — État des droits existants (photographie du 2026-09-13)

> Extraction complète et régénérable :
> [`inventaires/2026-09-13-etat-des-droits.md`](inventaires/2026-09-13-etat-des-droits.md),
> produit par `python manage.py inventaire_habilitation`.
> Ce document en est la synthèse lisible et le registre des écarts à
> instruire. **Aucun des écarts ci-dessous n'est corrigé en U0** (règles
> R2/R3 : additif d'abord, observation avant tout refus).

## 1. Principe d'habilitation en vigueur

- Les **groupes Django** `ROLE_<code>` sont la source de vérité des rôles ;
  le champ `User.role` est une dénormalisation du rôle principal,
  synchronisée par signaux (`authentication/apps.py`).
- Les permissions des groupes dérivent de `ROLE_POLICY`
  (`authentication/role_groups.py`) : applications × actions modèles +
  permissions métier `authentication.*` (10), avec d'éventuelles
  `exclude_codenames`.
- Les permissions DRF (`IsDFRC`, `IsEncadrant`, `IsSecretariat`,
  `CanListParticipants`…) appliquent les contrôles sur chaque vue ; le
  backend reste la seule autorité (S3).
- `compute_capabilities` projette ces droits pour l'affichage React sans
  jamais accorder quoi que ce soit.

## 2. Les 12 rôles actuels

| Code | Libellé | Groupe | Canal | `is_staff` | Niveau provisoire | Périmètre données |
|---|---|---|---|---:|---|---|
| ADMIN | Administrateur | ROLE_ADMIN | web + admin | oui | N4 | global |
| DIRECTION | Direction | ROLE_DIRECTION | web | non | N4 | global |
| CHEF_CPFAE_ADMIN | Chef INJS Admin | ROLE_CHEF_CPFAE_ADMIN | web + admin | oui | N4 | global (rôle unique plateforme) |
| CPFAE_ADMIN | INJS Admin | ROLE_CPFAE_ADMIN | web + admin | oui | N4 | global |
| CHEF_SECRETARIAT | Chef Secrétariat | ROLE_CHEF_SECRETARIAT | web | non | N3 | son secrétariat (un seul chef par secrétariat) |
| SECRETARIAT | Secrétariat | ROLE_SECRETARIAT | web | non | N2 | son secrétariat |
| FINANCE | Finance | ROLE_FINANCE | web | non | N3 | lecture fiches, module finance |
| ARCHIVE | Archiviste | ROLE_ARCHIVE | web | non | N1 | global (lecture) |
| ENCADRANT | Encadrant | ROLE_ENCADRANT | web (badgeage mobile possible) | non | N2 | modules dont il est superviseur |
| SUPERVISEUR | Superviseur | ROLE_SUPERVISEUR | web | non | N2 | `suiviEvaluation` |
| FORMATEUR | Formateur | ROLE_FORMATEUR | **mobile uniquement** | non | N2 | application mobile |
| AUDITEUR | Étudiant | ROLE_AUDITEUR | **mobile uniquement** | non | N1 | application mobile |

- 10 rôles web (`ALLOWED_WEB_ROLES`), 2 rôles mobile-only
  (`MOBILE_ONLY_ROLES`) : partition sans recouvrement.
- 5 combinaisons multi-rôles sont explicitement ouvertes aujourd'hui
  (`ALLOWED_MULTI_ROLE_COMBINATIONS`) : chef/secrétariat + encadrant ou
  superviseur, encadrant + superviseur.

## 3. Synthèse de la politique de permissions

- **Trio admin (ADMIN, CHEF_CPFAE_ADMIN, CPFAE_ADMIN)** : toutes les
  permissions métier sauf `finance_module`, CRUD complet sur les
  applications cœur (`authentication`, `formations`, `presences`,
  `exports`) ; `is_staff=True`.
- **DIRECTION** : lecture seule sur les applications cœur ;
  `global_scope` ; pas de `mutate_users` ; relève du module finance par
  ensemble de rôles (voir écart E2).
- **CHEF_SECRETARIAT / SECRETARIAT** : CRAD `formations`, `presences`,
  `suiviEvaluation`, à l'exception de `add_participant` ; peuvent muter les
  comptes (`mutate_users`) ; pas de `global_scope`.
- **FINANCE** : lecture sur `formations`, `presences`, `exports` ;
  `finance_module` ; ni `operational_web`, ni `list_participants`, ni
  `mutate_users`.
- **ARCHIVE** : lecture globale, `global_scope` et `finance_module`.
- **ENCADRANT** : CRUD `formations`/`presences`/`suiviEvaluation`,
  `operational_web`, pas de `mutate_users`.
- **SUPERVISEUR** : CRUD `suiviEvaluation` uniquement ; pas de
  `list_participants`, pas d'accès modèles `formations`.
- **FORMATEUR / AUDITEUR** : lecture `formations`/`presences`, **aucune
  permission métier web** (d'où le refus du canal web).

## 4. Canaux de connexion (gelé par les tests `test_03`)

- Web sans `device_id` : 200 pour les 10 rôles web ; 403 avec message
  « …réservé à l'application mobile » pour FORMATEUR/AUDITEUR.
- Mobile avec `device_id` : 200 pour les deux rôles mobiles ; premier
  appareil verrouillé au compte (`DeviceBinding`), tout autre compte sur
  le même appareil → 403 `DEVICE_LOCKED` ; le titulaire peut se ré-appairer.
- Jeton de rafraîchissement en cookie HttpOnly, chemin `/api/auth/` ;
  conservé dans le corps pour la rétrocompatibilité mobile.
- Limiteur de connexion : 20 tentatives/minute/IP (`login`, 429 au-delà).
- Compte inactif ou mauvais mot de passe → 401 « Identifiants invalides » ;
  payload incomplet → 400 ; drapeau `must_change_password` exposé à la
  connexion.

## 5. Cloisonnement par secrétariat (gelé par les tests `test_05`)

- Rôles globaux (trio admin, DIRECTION, ARCHIVE) : tous les participants.
- CHEF_SECRETARIAT/SECRETARIAT rattachés : participants de LEUR secrétariat
  (rattachement direct ou module d'inscription) ; sans rattachement :
  uniquement les participants sans secrétariat.
- FINANCE : aucun participant dans le queryset opérationnel, mais une voie
  de lecture dérogatoire `participant_fiche_accessible`.
- ENCADRANT : participants des modules dont il est superviseur ; aucune
  donnée tant qu'aucun module ne lui est affecté.
- Preuve croisée : le secrétariat A ne voit jamais le participant B (y
  compris en devinant l'identifiant), et inversement.

## 6. Registre des écarts constatés (à instruire, aucune correction en U0)

| Réf. | Constat | Impact potentiel | Unité pressentie |
|---|---|---|---|
| **E1** | Un `user.role = X ; user.save()` AJOUTE le groupe cible **sans retirer l'ancien** (`sync_user_role_group`) ; le rôle principal devient le plus élevé des deux. Les bascules propres passent par les serializers. | Multi-appartenance technique involontaire si une vue oublie le remplacement ; l'inventaire compte déjà les comptes multi-groupes. | U1/U2 |
| **E2** | Accès finance de DIRECTION/ARCHIVE régi par l'ensemble `FINANCE_MODULE_ROLES`, alors que la permission Django `authentication.finance_module` n'est accordée qu'à FINANCE et ARCHIVE (pas DIRECTION). Double source de vérité. | Divergence entre `has_perm` et les contrôles de vues. | U2 |
| **E3** | Les secrétariats ont `add_participant` exclu mais conservent **`delete_participant`** (et add/change sur les autres modèles). | Asymétrie non explicitée entre création et suppression. | U2 |
| **E4** | `ROLE_POLICY` ADMIN n'accorde pas `finance_module` (seul un `is_superuser` l'a par contournement Django). | Selon les comptes admin réellement déployés, l'écran finance peut être masqué pour un admin non super-utilisateur. | U3 |
| **E5** | `participants_queryset_for_user` **renvoie tous les participants par repli** pour les rôles sans branche (SUPERVISEUR, FORMATEUR, AUDITEUR) ; seule FINANCE est explicitement vide. Les vues se protègent en aval (`IsDFRC`, `CanListParticipants` → 403 vérifié), mais la fonction censée filtrer « à la source » est permissive. | Fuite si une nouvelle vue réutilisait la fonction sans garde ; défense en profondeur fragile. | **U2 (mode observation d'abord)** |
| **E6** | `get_user_role()` renvoie une chaîne vide `''` (et non `None`) pour un compte sans groupe ni rôle. | Cosmétique/contrats d'affichage. | U1 |
| **E7** | Miroir de rôles côté interface : `frontend/src/utils/roles.js` (411 lignes) duplique la logique serveur. | Risque de divergence d'affichage ; ne peut pas ouvrir de droit. | retrait après E4 |
| **E8** | Deux endpoints liste participants coexistent avec des permissions différentes : `/api/formations/participants/` (`IsDFRC`/`IsEncadrant` : les secrétariats ont 403) et `/api/formations/participants/list/` (`CanListParticipants` : les secrétariats ont 200). | Hétérogénéité des contrôles selon la route. | U2/U4 |
| **E9** | Aucune garde technique aujourd'hui pour S6 (pas d'auto-élévation) et S7 (≥ 2 administrateurs actifs) ni pour la désactivation du dernier administrateur. | Verrouillage possible par erreur d'administration. | U4 (+ secours hors app, voir `00-restauration.md` §5) |
| **E10** | L'inventaire signale les comptes jamais connectés, multi-groupes et les secrétariats sans rattachement, mais pas les comptes partagés ni les doublons d'identité. | Assainissement du parc à réaliser. | U8 |
| **E11** | La connexion JWT (`login_view`) n'appelle pas `update_last_login` : `last_login` n'est alimenté que par une session d'admin Django, pas par les connexions web/mobiles applicatives. | La métrique « comptes jamais connectés » ne reflète pas l'usage réel ; détection des comptes dormants impossible en l'état. | U4/U8 |

Chaque écart ci-dessus est déjà couvert par un test de caractérisation
(gelé au comportement actuel) : toute résorption devra modifier le test en
connaissance de cause, jamais en silence.

## 7. Régénération

```bash
cd backend
python manage.py inventaire_habilitation --sortie <sortie-droits>.md
```

La comparaison de deux rapports datés fait apparaître toute évolution du
dispositif par simple différence de texte.
