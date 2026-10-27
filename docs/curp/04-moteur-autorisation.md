# 04 — Moteur d'autorisation et mode observation (livrable U2)

> Unité **U2** du chantier CURP-INJS. Ce document décrit le moteur
> `est_autorise()`, ses dix contrôles ordonnés, les trois modes
> d'exploitation (arrêt, observation, application), l'API REST associée et
> les preuves de non-régression. La conception détaillée est dans
> [`U2-note-conception.md`](U2-note-conception.md). En U2, **aucun refus
> n'est appliqué sur une vue existante** (règles R2/R3).

## 1. Ce qu'apporte U2 (et ce qu'elle n'apporte pas)

U2 rend le socle de données d'U1 **exécutable** : une demande d'accès peut
désormais être évaluée comme `(compte, permission canonique, canal, cible)`
et recevoir une décision motivée. Le moteur est décisionnel et pur (aucune
écriture, aucune dépendance DRF) ; l'exploitation de sa décision relève de
trois couches :

| Couche | Fichier | Rôle |
|---|---|---|
| Moteur | `habilitations/services/moteur.py` | Les 10 contrôles, les octrois, les motifs. |
| Codes | `habilitations/services/codes.py` | Modes, codes de motif stables, largeur des périmètres. |
| Observation | `habilitations/services/observation.py` | Compteurs d'écarts dans le cache, campagne hors-ligne. |
| Permission DRF | `habilitations/permissions.py` | `ExigePermission` (no-op / observante / refusante) et permission d'administration. |
| API | `habilitations/api/` | Évaluation, mes accès, synthèse, référentiels en lecture. |
| Projection UI | `habilitations/services/projection.py` | Clé additive `habilitations` dans `/api/auth/capabilities/`. |

U2 ne peuple pas le référentiel (U3), ne crée aucun écran (U4), n'applique
aucun cycle de vie (U5/U6) et ne rattache aucun compte legacy (U8). En
conséquence, au jour d'U2, **la totalité du parc est « non gouvernée »** :
l'ancien dispositif reste seul décideur, exactement comme avant.

## 2. Les trois modes

Réglages sans redéploiement (variables d'environnement) :

| Variable | Défaut U2 | Effet |
|---|---|---|
| `HABILITATIONS_OBSERVATION` | `true` | Évalue et compte les écarts, mais ne modifie aucune réponse. |
| `HABILITATIONS_APPLICATION` | `false` | Applique les refus (et trace `ACCES_REFUSE`). Jamais activé en U2. |

- les deux éteints → **no-op total** : `ExigePermission` accorde sans lire le
  cache ni évaluer ;
- observation seule → abstention pour les comptes non gouvernés,
  transparence totale pour l'existant ;
- application → le moteur devient bloquant (utilisé par les tests et par les
  unités futures, pas posé sur une vue legacy en U2).

**Non-gouvernance = abstention.** Un `authentication.User` sans
`CompteUtilisateur` renvoie `gouverne: false` : ni autorisé ni refusé par le
moteur, il n'apparaît dans aucun écart. C'est la garantie de bascule
progressive (S1, S2).

## 3. Les dix contrôles ordonnés

Le moteur collecte tous les motifs (utile à l'observation) et fonde sa
décision sur la présence d'au moins un octroi valide et couvrant. Le refus
est fermé par défaut (*fail closed*).

| # | Contrôle | Codes de motif |
|---|---|---|
| 1 | Session authentifiée | `NON_AUTHENTIFIE` |
| 2 | Compte gouverné (profil) | abstention, pas un refus |
| 3 | Statut du compte | `COMPTE_INVITE`, `COMPTE_SUSPENDU`, `COMPTE_DESACTIVE`, `COMPTE_VERROUILLE`, `COMPTE_EXPIRE` |
| 4 | Date d'expiration | `COMPTE_EXPIRATION_ATTEINTE` |
| 5 | Canal (profil puis rôle) | `CANAL_NON_AUTORISE`, `CANAL_IMPOSE_PAR_ROLE` |
| 6 | MFA (politique ou rôle sensible) | `MFA_REQUIS_NON_ACTIF` |
| 7 | Octroi valide : rôle via la matrice, OCTROI dérogatoire, délégation | `PERMISSION_INCONNUE`, `AUCUNE_ATTRIBUTION_PERMETTANTE`, `MODULE_REQUIS_ABSENT`, `ROLE_SENSIBLE_SANS_SECONDE_SIGNATURE`, `ROLES_INCOMPATIBLES`, `NIVEAU_INSUFFISANT`, `PERIMETRE_SECRETARIAT_MANQUANT`, `DEROGATION_*`, `DELEGATION_*` |
| 8 | Priorité du RETRAIT | `PERMISSION_RETIREE` |
| 9 | Couverture de la cible | `CIBLE_HORS_PERIMETRE` |
| 10 | Titulaire de la délégation toujours habilité | `DELEGATION_SANS_TITULAIRE_VALIDE` |

### Sources d'octroi (contrôle 7)

1. **Rôle** : une `AttributionRole` ACTIVE et dans ses dates dont le
   `RoleMetier` donne la permission via la matrice M2M
   (`RoleMetier.permissions`, table ajoutée vide par la migration U2 et
   peuplée en U3). L'attribution doit en outre passer les contrôles de
   module installé, de seconde signature (rôle sensible), d'incompatibilité
   avec un autre rôle actif, de périmètre de secrétariat et de canal imposé.
2. **Dérogation OCTROI** : toujours bornée (≤
   `PolitiqueSecurite.duree_max_derogation_jours`, 90 par défaut), née et non
   expirée, dans la `portee_maximale` de la permission, doublement signée si
   la permission l'exige.
3. **Délégation** : active et bornée, signée pour les permissions critiques,
   et le délégant doit détenir la permission **directement** (pas de
   chaîne de re-délégation : profondeur 1).

### Priorités et combinaisons

- un **RETRAIT** global actif annule la permission ; un RETRAIT ciblé ne vaut
  que dans son périmètre ; les RETRAIT sont permanents (pas de date de fin
  obligatoire) ;
- un **OCTROI postérieur** au RETRAIT et doublement signé peut le lever
  (élargissement toujours explicite, S2/S4) ;
- le MFA est exigé quand un code de rôle figure dans
  `PolitiqueSecurite.roles_mfa_obligatoire` ou qu'un rôle octroyant est
  sensible ;
- la **couverture de cible** est résolue par : périmètre `INJS_ENTIER`,
  égalité ContentType, règle générique `secretariat_id`, ou une fonction de
  couverture injectée dans le contexte d'appel (les résolveurs métier
  complets seront branchés en U4 sans modifier le moteur).

## 4. API REST (toutes les routes sont nouvelles)

Préfixe `/api/habilitations/` :

| Route et méthode | Droits | Contenu |
|---|---|---|
| `GET mes-acces/` | authentifié | Profil gouverné (statut, canal, MFA), attributions actives avec périmètres lisibles, dérogations et délégations ; `{gouverne:false}` sinon. |
| `POST evaluer/` | soi pour tous ; autrui réservé aux administrateurs | Corps `{permission, canal?, cible?, niveau_minimum?, username?}` ; réponse 200 contenant `autorise`, `gouverne`, `motifs` (codes + libellés français), `octrois` et `mode`. Une évaluation d'autrui est tracée au journal. |
| `GET observations/synthese/` | administrateurs | Compteurs d'évaluations, de non-gouvernés, d'écarts par sens (risque S1 vs S2) et par motif. |
| `POST observations/remettre-a-zero/` | administrateurs | Vide les compteurs (tracé au journal). |
| `GET roles/`, `GET permissions/` | authentifié | Référentiels paginés en lecture (vidés jusqu'à U3). |

La permission `EstAdministrateurHabilitations` vise le trio
ADMIN/CPFAE_ADMIN/CHEF_CPFAE_ADMIN (et les super-utilisateurs), délibérément
sans s'appuyer sur `mutate_users` que les secrétariats détiennent déjà.

## 5. Clé additive dans les capacités d'affichage

`GET /api/auth/capabilities/` reçoit une clé racine `habilitations` :

```json
{"gouverne": false, "mode": "OBSERVATION"}
```

Pour un compte gouverné : `statut`, `canal`, `mfa_actif`,
`attributions_actives` s'ajoutent. Toutes les clés existantes (`version`,
`role`, `capacites`, `perimetres`…) sont strictement inchangées : la clé est
purement descriptive et n'accorde aucune action (S3).

## 6. Observation et campagne

- chaque évaluation passant par `ExigePermission` incrémente les compteurs
  dans le cache Django (LocMem aujourd'hui, Redis sans changement de code) ;
- les écarts sont distingués selon leur sens : **legacy autorise / moteur
  refuse** (risque de perte d'accès S1, niveau WARNING) et **legacy refuse /
  moteur autorise** (risque d'élargissement S2, niveau INFO) ;
- la commande `observations_habilitations` affiche la synthèse, vide les
  compteurs (`--remettre-a-zero`) ou joue une **campagne hors-ligne**
  (`--campagne`) qui évalue tous les comptes gouvernés sur le référentiel ;
  en U2, elle annonce explicitement qu'elle est sans objet (0 compte
  gouverné, référentiel vide) et sort toujours 0 ;
- le journal append-only n'est pas alimenté par l'observation (volume) ; il
  reçoit les refus `ACCES_REFUSE` uniquement en mode application.

## 7. Migration

`0003_rolemetier_permissions` ajoute uniquement la table M2M de la matrice
rôle ↔ permission (vide). Aucune table existante n'est modifiée ; migration
retour vérifiée sur base vide et base de démonstration.

## 8. Tests et non-régression

- **85 nouveaux tests** dans `habilitations/tests/` (objectif U2 : 45) :
  contrôles de comptes (15), octrois/dérogations/retraits (17),
  périmètres/délégations (11), observation et permission DRF (13), API et
  capacités additives (25), commande (4) ; total de l'application :
  **162 tests verts**, 2 ignorés (déclencheurs PostgreSQL).
- 110 tests de caractérisation U0 inchangés et verts ; les capacités des
  12 rôles legacy sont vérifiées intactes (SECRETARIAT, FINANCE,
  FORMATEUR…).
- Contrat d'API renouvelé selon la procédure officielle : **6 routes
  ajoutées, 0 rupture**, 0 clé supprimée.
- Fumée d'authentification : 91/91 ; chaîne du journal intègre ; campagne
  d'observation sans objet et sortie 0 sur la base de démonstration.
- Aucun fichier Python serveur ne dépasse 600 lignes (maximum : 591, le
  moteur) ; aucun `print()` runtime ; sorties, code et messages en français.

## 9. Repli

1. `HABILITATIONS_OBSERVATION=false` : no-op total, comportement U1 ;
2. retrait de l'`include` des URLs et de la clé `habilitations` : retour à
   U1 (les vues legacy n'ont aucune dépendance au moteur) ;
3. `migrate habilitations 0002` annule la table de matrice.

Le passage en mode application sur des vues legacy se fera unité par unité
(U5+), après une période d'observation sans écart S1 et un feu vert RSSI
explicite.
