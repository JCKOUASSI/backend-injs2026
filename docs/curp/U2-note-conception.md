# U2 — Note de conception : moteur d'autorisation en mode observation

> À contresigner par RT et RSSI. Unité **additive** : aucun refus n'est
> appliqué sur une vue existante, aucune vue existante n'est modifiée dans
> son comportement, aucun test existant n'est touché (R5). Date :
> 2026-09-14. Prompt source : recueil CURP-INJS, Partie II §3.3
> (`est_autorise`, contrôles ordonnés, mode observation) ; fiche
> d'exécution « FICHE U2 ».

## 1. Reformulation (ce qui est créé, étendu, épargné)

**Créé** :

- le service moteur `habilitations.services.moteur.est_autorise(...)` qui
  évalue une demande d'accès (compte × permission canonique × canal ×
  cible) par **dix contrôles ordonnés** et retourne une décision motivée
  et déterministe ;
- le service d'**observation** (`habilitations.services.observation`) qui
  compare la décision du moteur à la décision actuelle, compte les écarts
  via l'abstraction de cache Django (LocMem aujourd'hui, Redis sans
  changement demain) et trace les divergences dans les logs — **sans jamais
  changer une réponse** ;
- la classe DRF `ExigePermission(code)` : *no-op* totale quand le dispositif
  est éteint, **observante** en mode observation, **refusante** en mode
  application ;
- une API REST nouvelle sous `/api/habilitations/` (mes accès, évaluation à
  la demande, synthèse d'observation, référentiels en lecture) ;
- une commande `observations_habilitations` (synthèse, remise à zéro,
  campagne hors-ligne) ;
- une seule migration additive : la matrice `RoleMetier ↔ PermissionMetier`
  (M2M vide), structure dont le moteur a besoin pour résoudre les octrois
  et que **U3 se contentera de peupler** (33 rôles + permissions) ;
- au moins 45 tests.

**Étendu** (additif strict) :

- `GET /api/auth/capabilities/` gagne une clé racine `habilitations`
  (`gouverne`, `mode`, `statut`) ; toutes les clés existantes sont
  conservées à l'identique ;
- `config/urls.py` ajoute un `include` ; `config/settings.py` un bloc de
  réglages `HABILITATIONS_*` ; la CI une étape d'observation ;
- le snapshot de contrat d'API est renouvelé par la procédure officielle
  (`update_api_contract --justification`), avec pour seul changement
  l'ajout des nouvelles routes.

**Épargné (intouché)** : les 12 rôles, les groupes Django et leurs
signaux, `role_groups.py`, les classes de permission DRF existantes, les
vues et URLs d'authentification, le flux JWT/canaux/appareils, le
cloisonnement secrétariat legacy, les tests de caractérisation U0 et tous
les tests existants. Aucune permission existante n'est retirée (S2 : zéro
élargissement silencieux, et ici zéro retrait silencieux).

## 2. Les trois modes et les interrupteurs (R2/R3, « drapeau OFF = noop »)

Réglages lus dans l'environnement, sans valeur en dur dans le code :

| Réglage | Défaut | Effet |
|---|---|---|
| `HABILITATIONS_OBSERVATION` | `True` | Le moteur évalue et relève les écarts, mais **aucune réponse n'est modifiée**. |
| `HABILITATIONS_APPLICATION` | `False` | Les refus du moteur deviennent effectifs. **Jamais activé en U2**, ni en démo, ni en CI. |
| (les deux à faux) | — | **No-op total** : `ExigePermission` accorde sans évaluer, aucune lecture de cache, aucune écriture. |

En U2, `ExigePermission` n'est posée sur **aucune vue existante** : le
mode application ne pourrait de toute façon rien refuser Legacy. Les
vues nouvelles d'habilitation sont protégées par les permissions
d'administration existantes. Le passage en application sur le Legacy
s'effectuera unité par unité (U5+), après une période d'observation
exempte d'écarts et un feu vert RSSI explicite.

**Non-gouvernance = abstention, pas refus.** Tant qu'un `User` n'a pas de
`CompteUtilisateur` (aucun compte n'en a avant la migration U8), le
moteur renvoie `gouverne=False` et s'abstient : la décision continue de
relever exclusivement de l'ancien dispositif. Ces comptes ne génèrent
aucun « écart ». C'est la garantie d'un basculement progressif sans
régression (R2, S1).

## 3. Les dix contrôles ordonnés du moteur

Le moteur collecte **tous** les motifs (utile en observation) et fonde sa
décision sur la présence d'au moins un octroi couvrant non bloqué. Codes
stables en français, exposés tels quels par l'API.

| # | Contrôle | Codes de motif bloquant |
|---|---|---|
| 1 | Session authentifiée | `NON_AUTHENTIFIE` |
| 2 | Compte gouverné (profil existant) | *abstention* `gouverne=False`, jamais un refus |
| 3 | Statut du compte | `COMPTE_INVITE`, `COMPTE_SUSPENDU`, `COMPTE_DESACTIVE`, `COMPTE_VERROUILLE`, `COMPTE_EXPIRE` |
| 4 | Date d'expiration non atteinte | `COMPTE_EXPIRATION_ATTEINTE` |
| 5 | Canal autorisé (profil puis canal imposé du rôle) | `CANAL_NON_AUTORISE`, `CANAL_IMPOSE_PAR_ROLE` |
| 6 | MFA lorsque requis (politique ou rôle sensible) | `MFA_REQUIS_NON_ACTIF` |
| 7 | Existence d'un octroi valide : attribution active dont le rôle donne la permission (matrice), sous contrôles du rôle ; dérogation OCTROI active et bornée ; délégation active et signée | `PERMISSION_INCONNUE`, `AUCUNE_ATTRIBUTION_PERMETTANTE`, `MODULE_REQUIS_ABSENT`, `ROLE_SENSIBLE_SANS_SECONDE_SIGNATURE`, `ROLES_INCOMPATIBLES`, `NIVEAU_INSUFFISANT`, `PERIMETRE_SECRETARIAT_MANQUANT`, `DEROGATION_SANS_DATE_FIN`, `DEROGATION_TROP_LONGUE`, `DEROGATION_PERIODE_INCOHERENTE`, `DEROGATION_SANS_SECONDE_SIGNATURE`, `DEROGATION_HORS_PORTEE_MAXIMALE`, `DELEGATION_HORS_PERIODE`, `DELEGATION_NON_SIGNEE`, `DELEGATION_SANS_TITULAIRE_VALIDE` |
| 8 | Priorité du RETRAIT explicite sur tout octroi ; un OCTROI postérieur doublement signé peut lever un retrait ciblé | `PERMISSION_RETIREE` |
| 9 | Couverture de la cible par les périmètres des octrois (global `INJS_ENTIER`, égalité ContentType, ou fonction de couverture injectée) | `CIBLE_HORS_PERIMETRE` |
| 10 | Validité résiduelle de la délégation (bornée, pas de re-délégation, titulaire toujours habilité) | reprend les codes `DELEGATION_*` |

Règles de décision :

- un RETRAIT actif sans périmètre annule globalement la permission ; un
  RETRAIT ciblé ne s'applique que dans son périmètre ;
- une dérogation OCTROI est toujours temporaire (≤
  `PolitiqueSecurite.duree_max_derogation_jours`, 90 par défaut), née et
  non expirée ; elle ne peut excéder la `portee_maximale` de la
  permission ; sa seconde signature est exigée quand la permission la
  requiert ;
- une dérogation OCTROI postérieure à un RETRAIT ciblé, active et
  doublement signée, lève ce retrait (élargissement toujours explicite et
  tracé, jamais silencieux — S2/S4) ;
- une délégation ne donne que ce que le délégant détient encore
  directement (pas de chaîne de délégation) ;
- le refus est fermé par défaut (*fail closed*) : une permission inconnue
  ou aucune attribution valide vaut refus.

La couverture de périmètre vis-à-vis des objets métier réels
(secrétariat d'un participant, modules d'un encadrant…) est branchée par
une fonction injectée dans le contexte d'appel (`contexte['couverture']`)
; une implémentation générique par défaut (global / égalité /
`secretariat_id`) couvre les besoins U2. Les résolveurs métier complets
seront branchés avec les écrans U4 et le référentiel U3, sans modifier le
moteur.

## 4. API REST livrée (toutes les routes sont nouvelles)

Sous `/api/habilitations/` :

| Route | Droits | Rôle |
|---|---|---|
| `GET mes-acces/` | tout compte authentifié | Vue du compte gouverné : statut, canal, MFA, rôles actifs avec périmètres lisibles, dérogations et délégations actives ; `{gouverne:false}` sinon. |
| `POST evaluer/` | soi pour tous ; un autre compte réservé aux administrateurs | Évalue `{permission, canal?, cible?}` et renvoie la décision motivée (mode, octrois, codes). Ne modifie rien. |
| `GET observations/synthese/` | administrateurs | Compteurs d'évaluations et d'écarts par code de motif. |
| `POST observations/remettre-a-zero/` | administrateurs | Vide les compteurs d'observation. |
| `GET roles/`, `GET permissions/` | authentifié (lecture) | Référentiels en lecture (vidés jusqu'à U3). |

L'écriture des rôles, attributions et dérogations par API n'est pas
d'U2 : elle arrivera avec les écrans U4 et la double commande + motif
(S4). L'admin Django et les services restent les seules voies d'écriture.

## 5. Observation : ce qui est mesuré, et ce qui ne l'est pas encore

- Chaque appel passant par `ExigePermission` (quand elle sera branchée sur
  une vue) ou par `POST evaluer/` fait l'objet d'une évaluation. En
  observation, une divergence entre décision moteur et décision constatée
  incrémente un compteur par code de motif et émet un log
  `habilitation_ecart` de niveau WARNING (username, permission, canal,
  codes — sans donnée de scolarité).
- Le **journal chaîné** n'est pas alimenté à chaque requête (volumétrie) :
  il reçoit les événements d'administration (déjà en U1) et, en mode
  application uniquement, les refus `ACCES_REFUSE`.
- La commande `observations_habilitations --campagne` évalue hors-ligne
  les comptes gouvernés sur le référentiel chargé. En U2, le référentiel
  est vide (U3) et aucun compte n'est gouverné (U8) : la campagne est
  donc volontairement sans objet et l'indique explicitement ; le
  mécanisme, lui, est complet et testé sur données fabriquées.
- La synthèse est servie par l'API et par la commande ; les compteurs
  vivent dans le cache (Redis plus tard sans changement de code).

## 6. Stratégie de test (≥ 45 ; succès, refus et abstention)

- `test_moteur_comptes` : non authentifié, absence de profil
  (abstention), les cinq statuts bloquants, expiration, canaux, MFA ;
- `test_moteur_octrois` : octroi par rôle via la matrice, module requis,
  seconde signature, incompatibilités, niveau, RETRAIT global/ciblé,
  OCTROI borné / hors durée / sans date de fin / hors portée maximale,
  levée d'un retrait par octroi postérieur signé ;
- `test_moteur_perimetres` : périmètre global, cible hors périmètre,
  couverture secrétariat par fonction injectée, délégation active,
  expirée, non signée, sans titulaire valide ;
- `test_observation` : OFF = noop total (cache et réponses intactes),
  observation qui laisse passer et compte, application qui refuse et
  journalise, abstention hors-gouvernance, réinitialisation ;
- `test_api_habilitations` : 401 anonyme, mes-accès, évaluation pour soi
  et pour autrui (`…_autorise_pour_administrateur`,
  `…_refuse_pour_secretariat`), synthèse et reset réservés, référentiels
  en lecture, extension de `capabilities` (nouvelle clé présente, clés
  existantes strictement identiques pour les 12 rôles) ;
- les tests utilisent `override_settings` pour les trois modes ; aucun
  test existant n'est modifié.

## 7. Migration et réversibilité

- `0003_matrice_role_permissions` ajoute uniquement la table M2M implicite
  (vide) entre rôles et permissions ; aucun champ de table existante n'est
  modifié. Migration retour testée sur base vide et base de
  démonstration.
- Repli d'U2 : (1) `HABILITATIONS_OBSERVATION=False` éteint tout ; (2)
  retirer l'`include` des URLs et la clé `habilitations` revient à l'état
  U1 ; (3) `migrate habilitations 0002` annule la table de matrice. Les
  tables U1 et les autres applications ne sont pas touchées.

## 8. Ce que U2 ne fait PAS (garde-fou de périmètre)

- aucun refus appliqué sur le Legacy, aucune permission DRF existante
  modifiée, aucune vue métier branchée sur `ExigePermission` ;
- aucun peuplement du référentiel (33 rôles, matrice de données) : U3 ;
- aucun écran React : U4 ;
- aucun cycle de vie actif (provisionnement, suspension effective,
  MFA réel, verrouillage réel) : U5/U6 ;
- aucune création automatique de profils `CompteUtilisateur` : migration
  de comptes U8 ; en U2, les comptes non gouvernés sont la norme.
