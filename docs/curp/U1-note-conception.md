# U1 — Note de conception : socle de données de l'habilitation

> À contresigner par RT (obligatoire pour U1). Unité **strictement
> additive** : son application n'est consommée par aucun chemin bloquant ;
> elle ne modifie aucun modèle, aucune vue, aucun test existant.
> Date : 2026-09-13. Prompt source : recueil CURP-INJS, Partie II §3.1 et
> §3.2. Fiche d'exécution : Plan-execution §7, « FICHE U1 ».

## 1. Reformulation (ce qui est créé, étendu, épargné)

**Créé** : l'application Django `habilitations` avec les 10 modèles de la
chaîne PERSONNE → COMPTE → RÔLE/PERMISSION → PÉRIMÈTRE, plus le journal
append-only **chaîné par empreintes**, des services de journalisation et de
détection de doublons (non bloquante), l'administration Django en lecture,
trois commandes de gestion et ≥ 35 tests de modèle.

**Étendu** : rien n'est modifié dans les applications existantes. Le compte
existant `authentication.User` est **prolongé** par un profil
`CompteUtilisateur` en OneToOne porté par la nouvelle application — le
modèle `User` n'est ni déplacé, ni modifié (le diff des `models.py`
existants reste vide).

**Épargné (intouché)** : `role_groups.py` et la synchro des groupes Django,
le flux JWT et ses transports, la règle canaux (FORMATEUR/AUDITEUR
mobiles), le cloisonnement secrétariat, les middlewares de démo,
`presences.DeviceBinding`, les 12 rôles et les tests existants.

**Garantie anti-régression** : l'application ne branche aucun signal
décisionnaire, aucune permission DRF, aucune route n'est mise sous contrôle
en U1. Le moteur `est_autorise()` et le mode observation sont U2. U1 ne peut
donc ni autoriser ni refuser un accès : il ajoute des tables et des outils.

## 2. Décisions d'architecture (arbitrages demandés)

### Décision 1 — Une application dédiée `habilitations` (et non des modules dans `authentication`)
Le prompt autorise les deux options. Je choisis une **application séparée** :
- séparation physique entre le socle d'authentification gelé (qu'U0 vient de
  caractériser) et le nouveau dispositif, donc un périmètre de revue et de
  repli nets (retrait d'`INSTALLED_APPS` + rollback) ;
- les modèles sont transversaux (ils référencent RH, formations,
  scolarité, admissions) : les placer dans `authentication` créerait des
  dépendances inverses ;
- aucun risque de toucher aux migrations ou aux signaux sensibles de
  l'authentification. Coût : une application de plus, déjà anticipée par
  l'arborescence prescrite au §3.1.

### Décision 2 — Profil OneToOne, aucun champ ajouté au `User` existant
`CompteUtilisateur.user = OneToOneField(AUTH_USER_MODEL, related_name=
'profil_habilitation', on_delete=CASCADE)`. Tous les champs du §3.2.b
(statut, canal, dates de cycle de vie, MFA, notes…) vivent sur le profil.
Les comptes techniques peuvent exister sans profil (`personne` nullable).
Les champs déjà présents sur `User` (`must_change_password`, `secretariat`,
`role`) ne sont pas déplacés : ils restent source de l'ancien dispositif
jusqu'à E4 ; le nouveau profil les lit sans les dupliquer tant que la
migration de comptes (U8) n'a pas eu lieu.

### Décision 3 — Référence de périmètre générique (ContentType) plutôt qu'une dizaine de FK
`Perimetre` porte `type` (TextChoices) + une référence polymorphe
`(content_type, object_id, cible=GenericForeignKey)` nullable + un
`reference_lisible` (code métier, ex. `SECR-DEMO-A`) et un libellé calculé.
Justification : les périmètres visent des objets de modèles variables
(Secretariat, Formation, Groupe, Module, Participant, Site…). Des FK dures
multiples créeraient des graphes de dépendances et de migrations lourds vers
toutes les applications, et aucune n'est nécessaire au moteur pour filtrer
(U2 résoudra l'objet via ContentType). Le périmètre `SECRETARIAT` pointe vers
`formations.Secretariat` et reste **obligatoire sur les attributions qui en
relèvent** (validé par test), préservant ainsi le cloisonnement.

## 3. Les 10 modèles (fichiers `models/`, aucun > 600 lignes)

1. `Personne` — identité métier unique ; 5 liens OneToOne **nullable et non
   exclusifs** vers `ressources_humaines.Agent`, `formations.Formateur`,
   `formations.Participant`, `scolarite.DossierEtudiant`, `admissions.Candidat` ;
   matricule institutionnel lisible (`PERS-2026-00001`, format paramétrable).
2. `CompteUtilisateur` — OneToOne du `User` ; 6 statuts (INVITE, ACTIF,
   SUSPENDU, DESACTIVE, VERROUILLE, EXPIRE), 3 canaux (WEB, MOBILE,
   LES_DEUX), cycle de vie (dates, échecs, verrouillage), indicateur MFA.
3. `RoleMetier` — référentiel en base (code stable, domaine, niveau par
   défaut, module requis, sensible, cumulable, canal imposé, ordre, actif) ;
   les incompatibilités sont une M2M réflexive non symétrique.
4. `PermissionMetier` — `code = module.ressource.action`, 13 actions,
   portée maximale, criticité, motif/double validation/journalisation.
5. `Perimetre` — type + cible polymorphe + référence lisible.
6. `AttributionRole` — compte × rôle × niveau effectif × périmètres
   (M2M) × dates × motif × attribué/validé par × statut.
7. `PermissionAttribuee` — dérogation OCTROI/RETRAIT bornée (90 j max
   par défaut, valeur lue dans la politique), motif obligatoire.
8. `DelegationHabilitation` — délégant/délégataire, rôles/permissions/
   périmètres délégués, dates obligatoirement bornées, statut, validé par.
9. `PolitiqueSecurite` — singleton paramétrable sans redéploiement ; toute
   modification est historisée dans le journal (pas de 11e modèle).
10. `JournalHabilitation` — append-only, chaîné SHA-256, voir §5.

Exactement 10 modèles (les tables implicites de M2M ne sont pas des
modèles métier).

## 4. Détection de doublons d'identité (critère de sortie U1)

Service `identifier_doublons_personne(...)` paramétrable (seuil sur nom +
date de naissance, téléphone, courriel institutionnel/personnel). Il
**propose**, jamais ne refuse ni ne fusionne automatiquement : il retourne
des groupes de doublons potentiels. La commande `habilitations_diag`
l'exploite en lecture seule. La fusion (avec conservation d'historique) est
un service U5/U8 ; U1 ne fait que signaler, conformément à la fiche.

## 5. Journal append-only et chaîné (R7, et jalon à préparer)

- Une écriture par événement via le service `journaliser(...)` : acteurs,
  compte concerné, objet polymorphe dénormalisé, ancienne/nouvelle valeur
  (JSON), motif, IP, user-agent, identifiant de corrélation.
- `empreinte = SHA-256(empreinte_precedente | contenu canonique)`, calculée
  sous transaction verrouillant la dernière entrée ; `numero` unique.
- Immuabilité à **deux niveaux** :
  - modèle/ORM : `save()` refuse la mise à jour, `delete()` refusé, le
    `QuerySet` refuse `update()`/`delete()` en masse, l'admin est en lecture
    + ajout uniquement (comme l'app `core` déjà en place) ;
    - base de données : migration `RunSQL` posant des triggers
      `BEFORE UPDATE/DELETE` **PostgreSQL** (prod et CI), qui lèvent une
      exception. Sur SQLite (bascule de développement uniquement, jamais un
      moteur de production), les triggers ne sont pas posés car le vidage
      des tests `TransactionTestCase` y passe par `DELETE FROM` ; PostgreSQL
      utilise `TRUNCATE` qui ne déclenche pas les triggers ligne. L'ORM,
      lui, protège sur les deux moteurs. Ce choix est écrit et testé
      (`@skipUnless(vendor == 'postgresql')` pour le test trigger).
- Commande `verifier_chaine_habilitations` qui recalcule les empreintes et
  sort en code 1 sur rupture ou trou de séquence (base du futur travail U7).

## 6. Stratégie de test (≥ 35, succès ET refus)

Paquet `habilitations/tests/` : modèles et contraintes, génération de
matricule, liens multi-identités, détection de doublons (détection présente,
absence de faux doublon, non-blocage), statuts/canaux de compte,
attributions et dérogations (OCTROI borné, RETRAIT, échéance > 90 j
refusée par le validateur pur), délégation bornée, périmètre secrétariat,
politique singleton et historisation, immuabilité du journal par l'ORM (update,
delete, queryset, admin), chaînage cohérent et détection d'altération,
trigger PostgreSQL si présent, et un test d'**additivité** : un `User` sans
profil se comporte exactement comme avant (connexion web ADMIN 200, AUDITEUR
403 sans device / 200 avec device). Les tests existants ne sont pas modifiés.

## 7. Migrations et réversibilité

- `0001_initial` (schéma additif, FK en `SET_NULL`/`CASCADE` depuis les
  nouvelles tables uniquement ; aucune FK n'est ajoutée sur les tables
  existantes excepté le OneToOne du profil) puis migration des triggers.
- Toutes les migrations sont réversibles (les triggers ont un `DROP` en
  retour). Vérifiées sur base vide, sur la base démo peuplée (aller/retour),
  et dans les deux sens manuellement.

## 8. Stratégie de repli

1. retirer `habilitations` d'`INSTALLED_APPS` et éteindre tout (rien ne
   consomme l'app en U1) ;
2. si les tables gênent : `migrate habilitations zero` (réversible, ne
   touche aucune table existante).
Aucune donnée des 20 applications existantes n'est lue pour écriture ni
modifiée. Repli = annulation d'un ajout pur.

## 9. Ce que U1 ne fait PAS (éviter la dérive de périmètre)

- pas de moteur d'autorisation, pas de `est_autorise()`, pas de mode
  observation, pas de classe DRF `ExigePermission` (U2) ;
- pas de chargement des 33 rôles ni de la matrice (U3) ; le référentiel est
  une coquille vide prête ;
- pas d'écrans React (U4) ; pas de machine à états active, de
  provisionnement, d'imports, de MFA, de délégation effective (U5/U6) ;
- aucune décision de refus appliquée ; la détection d'anomalies ne fait que
  signaler.
