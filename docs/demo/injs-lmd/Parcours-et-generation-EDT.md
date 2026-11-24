# Parcours académique et génération des emplois du temps (INJS-LMD 2026)

Ce document décrit trois processus **tels qu'ils sont réellement implémentés** dans le dépôt :

1. le parcours académique d'un étudiant, de la candidature à la diplômation ;
2. la génération **manuelle** des emplois du temps ;
3. la génération **automatique** des emplois du temps.

Chaque affirmation renvoie au module, au service ou à la route qui la porte. Les limites constatées sont
signalées explicitement : elles font partie de la description, elles ne sont pas des réserves de style.

Repères de lecture :

- backend : `backend/<app>/` (Django, 20 apps « à plat », cf. `ADR-005`) ;
- frontend : `frontend/src/pages/...`, menu dans `frontend/src/menu/arborescence.js` ;
- routes HTTP : préfixe `/api/<app>/...` ;
- documents de référence : `docs/ADR/ADR-003` (EDT externe / moteur natif), `docs/ADR/ADR-007`
  (génération coordonnée), `docs/audits/AUDIT_GET_INJS_2026.md` (limites du solveur annuel).

---

# 1. Parcours académique d'un étudiant, de la candidature à la diplômation

## 1.1 Vue d'ensemble de la chaîne

```
CampagneAdmission → Candidat → Candidature (+ PieceCandidature)
        ↓  (décision)
Admission  ──convertir_admission_en_inscription──▶  DossierEtudiant (adossé à Participant)
        ↓
InscriptionAdministrative (statuts)  ──▶  InscriptionPedagogique (une ligne par ECUE)
        ↓                                        ↓
   AffectationGroupe / Groupe  ◀────────  Maquette → UE → ECUE
        ↓
EmploiDuTemps (édt) → AffectationCreneau → SeanceRegistre → Présences (QR / émargement)
        ↓
Evaluations (SessionEvaluation → Evaluation → composants → notes) → résultats ECUE/UE/semestre
        ↓
SessionJury → PropositionJury → DecisionJury → PVJury
        ↓
Diplome → RegistreDiplomes (+ Reedition, vérification publique par token)
```

Cette chaîne correspond aux phases 6 à 23 du document métier
`dossier_trvx/Processus académique complet d’un étudiant — A à Z.txt` ; les phases 0 à 5 (année, offre de
formation, maquettes, règles, acteurs, ressources) sont le paramétrage préalable décrit en 1.2.

## 1.2 Paramétrage préalable (sans quoi rien n'est possible)

| Objet | Où | Rôle dans le parcours |
|---|---|---|
| `AnneeAcademique` (+ `cloturee`) | `scolarite/models.py` | borne toutes les inscriptions et tous les EDT ; une année clôturée refuse la validation d'inscription |
| `RefFormation`, `Parcours`, `Niveau`, `Semestre` | `formations/`, `scolarite/` | chaîne LMD ; `Niveau.credits_requis` sert de seuil de diplomation |
| `Maquette` (statuts `BROUILLON` / `VALIDEE` / `ACTIVE` / `ARCHIVEE`) | `scolarite/models.py` | version de maquette applicable ; l'ECUE affectée doit appartenir à la maquette ACTIVE |
| `UE` / `ECUE` | `scolarite/models.py` | unités et éléments constitutifs, crédits, coefficients, volumes |
| `RegleValidationLMD` | `scolarite/models.py` | seuil, compensation (`SEMESTRE`…), `seuil_elim`, `credits_semestre` |
| `Groupe` (`capacite_max`, `actif`) | `scolarite/models.py` | regroupement pédagogique `L1-G1` pour une année / formation / niveau |
| `AffectationPedagogique` (`PROPOSEE`→`VALIDEE`→`PLANIFIEE`→`REALISEE`) | `scolarite/models.py` | **la** clé qui relie enseignant, ECUE, groupe, volume horaire — c'est elle que consomment l'EDT et les besoins |
| `CreneauTemplate`, `DisponibiliteHoraire` | `edts/models.py` | canevas horaire et indisponibilités fortes/souples |

## 1.3 Étape 1 — Candidature

La candidature est une **machine à états unique**, `backend/admissions/workflow.py`. Aucun autre chemin
d'écriture n'est censé exister : `appliquer_transition` est le seul point d'entrée, et
`TransitionInterdite` protège les sauts.

```
BROUILLON → SOUMISE → EN_ATTENTE_DE_VERIFICATION
                          ├─→ PIECES_INCOMPLETES → (retour dépôt) → EN_ATTENTE_DE_VERIFICATION
                          └─→ PIECES_VALIDEES → EN_ETUDE
                                                 ├─→ ADMISSIBLE → ADMIS | ADMIS_SOUS_RESERVE | LISTE_ATTENTE | REFUSE
                                                 └─→ REFUSE
(tous états ouverts → ANNULE)
```

- **Identité du candidat** : `Candidat` porte l'état civil ; `Candidature` porte le numéro unique, l'année,
  la formation/parcours/niveau demandés.
- **Pièces** : `PieceCandidature` a ses propres statuts (`MANQUANTE`, `FOURNIE`, `EN_VERIFICATION`,
  `VALIDEE`, `REFUSEE`, `EXPIREE`). `Candidature.dossier_complet` et `completude` (validées/total)
  conditionnent l'admission puis l'inscription.
- **Dépôt et vérification** : `POST /api/admissions/pieces/<id>/deposer/`, `.../verifier/`,
  `.../fichier/` (`admissions/urls.py`).
- **Concours** (voie séparée, même app) : `CampagneAdmission`, épreuves, notes, classement
  (`classement/calculer/`, `classement/publier/`), convocations, verrouillage d'épreuve
  (`admissions/concours_api.py`). Le classement publié alimente la décision d'admission.
- **Transition** : `POST /api/admissions/candidatures/<pk>/transition/` ; décision et annulation :
  `POST /api/admissions/admissions/<pk>/decision/` et `.../annuler/`.

Écrans : `/scolarite/candidatures`, `/scolarite/controle-dossiers`, `/scolarite/campagnes`,
`/scolarite/resultats-concours`.

## 1.4 Étape 2 — Admission

`Admission` matérialise la décision et sa validité dans le temps :
`ADMIS`, `ADMIS_SOUS_RESERVE`, `EN_ATTENTE`, `REFUSEE`, `ANNULEE`, plus `date_limite_inscription`.

Deux propriétés portent toute la suite du parcours :

- `permet_inscription` : uniquement `ADMIS` / `ADMIS_SOUS_RESERVE` **et** non expirée ;
- `est_expiree` : compare `date_limite_inscription` à la date du jour.

Écran : `/scolarite/admissions` (droits `candidatures.eligibilite.valider`, `candidatures.candidature.valider`).

## 1.5 Étape 3 — Inscription administrative

L'inscription administrative n'est pas saisie à la main au départ : elle est **convertie** depuis
l'admission, en une transaction, par
`scolarite/inscription_services.convertir_admission_en_inscription(admission, acteur, matricule, valider)`.

Ce que fait le service, dans l'ordre :

1. refuse si `admission.permet_inscription` est faux (message distinct pour l'expiration) ;
2. refuse si le dossier de pièces est incomplet (`validees/total` cité dans l'erreur) ;
3. **idempotence** : s'il existe déjà une inscription vivante pour cette admission (hors `ANNULEE`/`REJETEE`),
   elle est retournée avec `rejeu_idempotent=True` — un double clic ne crée pas deux inscriptions ; un rejeu
   `valider=True` fait seulement progresser `EN_ATTENTE → A_VALIDER → VALIDEE` ;
4. crée ou retrouve le `Participant` et lui attribue un **matricule** (`scolarite/matricules.py`, format
   `INJS<AA>-0001`, séquence par préfixe d'année) ;
5. crée ou retrouve le `DossierEtudiant` — `OneToOne` sur `Participant`, **sans dupliquer l'identité** : le
   Participant reste l'entité opérationnelle des présences, des notes et de la finance ;
6. crée l'`InscriptionAdministrative` (`type_inscription = PREMIERE`, ou `REINSCRIPTION`, `REDOUBLEMENT`,
   `REPRISE`, `REORIENTATION`, `TRANSFERT`), statut `BROUILLON` ;
7. si `valider=True`, enchaîne les transitions jusqu'à `VALIDEE`.

Machine à états de l'inscription administrative (`transition` = `appliquer_transition`) :

```
BROUILLON     → EN_ATTENTE | ANNULEE
EN_ATTENTE    → A_VALIDER | REJETEE | ANNULEE
A_VALIDER     → VALIDEE | REJETEE | EN_ATTENTE | ANNULEE
VALIDEE       → SUSPENDUE | TERMINEE | ANNULEE
SUSPENDUE     → VALIDEE | ANNULEE | TERMINEE
```

Garde-fous : une inscription archivée doit être réactivée avant toute transition ; une transition identique
au statut courant est refusée ; une année clôturée refuse le passage à `VALIDEE`.

Routes : `POST /api/scolarite/inscriptions/depuis-admission/` (201, ou 200 si rejeu),
`GET /api/scolarite/inscriptions/`, `.../stats/`, `.../inscriptions/valider-lot/`,
`.../inscriptions/action-lot/`, `.../<pk>/transition/`, `.../<pk>/reactiver/`, `.../<pk>/radier/`,
`.../<pk>/changer-parcours/` ; réinscriptions : `POST /api/scolarite/reinscriptions/`.

Écrans : `/scolarite/inscriptions`, `/scolarite/reinscriptions`, `/participants`, `/scolarite/journal`.

## 1.6 Étape 4 — Inscription pédagogique

`InscriptionPedagogique` = **une ligne par ECUE suivie**, avec statut `PREVUE`, `VALIDEE`,
`ABANDONNEE`, `DISPENSEE`, origine `AUTOMATIQUE` ou `MANUELLE`, unicité `(inscription, ecue)`, et
dénormalisation des ECTS / volumes au moment de l'inscription (la maquette peut ensuite évoluer sans
réécrire l'histoire).

- Génération depuis la maquette : `POST /api/scolarite/inscriptions/<pk>/pedagogie/generer/`
  (`scolarite/pedagogie_api.py`) ;
- ajout manuel : `.../pedagogie/ajouter/` ;
- consultation / mise à jour : `GET|PATCH /api/scolarite/pedagogie/<ligne_id>/` ;
- liste : `GET /api/scolarite/inscriptions/<pk>/pedagogie/`.

**Point de contrat important** : l'enchaînement automatique « validation administrative → génération des
inscriptions pédagogiques » est **désactivé par défaut**
(`INJS_AUTO_INSCRIPTION_PEDAGOGIQUE = False`). Il est verrouillé par
`backend/scolarite/tests/test_frontieres_metier.py` : valider une inscription administrative ne crée
**aucune** ligne pédagogique. La génération est un geste explicite du secrétariat.

**Équivalences et dispenses** : `equivalences/` porte `DemandeEquivalenceDispense`
(`BROUILLON → SOUMISE → EN_INSTRUCTION → A_COMPLETER → AVIS_PEDAGOGIQUE → DECISION → VALIDEE → APPLIQUEE`,
ou `REJETEE`). L'application d'une décision favorable bascule les inscriptions pédagogiques correspondantes
en `DISPENSEE` — le statut existait déjà, aucune table parallèle n'est créée.

## 1.7 Étape 5 — Affectation en groupe

`AffectationGroupe` rattache une inscription à un `Groupe` (même année et même niveau).

- affectation unitaire : `groupes_services.affecter_groupe` — contrôle la capacité (`capacite_max`) et la
  compatibilité année/formation/niveau ;
- affectation de masse : `POST /api/scolarite/groupes/repartition/`
  (`groupes_api.repartition_automatique`), qui ignore les étudiants déjà affectés ;
- suivi : `GET /api/scolarite/groupes/effectifs/`, `/groupes/non-affectes/`,
  `/groupes/<pk>/liste/<fmt>/` (export liste d'appel) ; retrait : `/inscriptions/<pk>/retirer-groupe/`.

Sans groupe (ou sans formation/niveau identifiables), l'étudiant reste sans EDT : la génération le
signale comme non planifiable au lieu d'inventer une affectation.

## 1.8 Étape 6 — Emploi du temps, séances et présences

### 1.8.1 Côté EDT

L'étudiant est concerné par les `AffectationCreneau` **publiées** de son groupe ou de sa formation
(statut de l'`EmploiDuTemps` = `PUBLIE`). Chaque séance peut porter une `affectation_pedagogique`
(enseignant + ECUE + volume), ce qui rend la séance traçable jusqu'au cours — la FK nullable sur
`AffectationCreneau` est renseignée à la persistance (migration additive `edts.0012`).

### 1.8.2 Contract externe (lecture seule)

`GET /api/scolarite/edt/` expose le contrat `app-injs-lmd` (version v1.1) : `groupes`, `enseignements`,
`etudiants`, `indisponibilites`, `creneaux`, `affectations`, `espaces/<id>/occupation/`, plus
`contrat` (volumétrie). C'est un **contrat de lecture** : un EDT produit par un outil externe revient dans
le socle par import Excel, cf. `ADR-003` et `moteur/import_inscrits.py`.

### 1.8.3 Séances opérationnelles

`edts.models_interop.SeanceRegistre` matérialise la séance :

```
BROUILLON → SIMULATION → EN_ATTENTE_VALIDATION → VALIDEE → PUBLIEE → (ANNULEE)
```

`moteur/interop_presences.py` gère les transitions, l'historisation, la clé métier, la reprogrammation,
la réconciliation d'un EDT et les instantanés d'étudiants attendus
(`etudiants_attendus`, `creer_instantane`). `peut_ouvrir_session_presence` empêche d'ouvrir un QR sur une
séance non publiable.

### 1.8.4 Présences

Routes (`presences/urls.py`) :

- `GET /api/presences/seances-edt/du-jour/` ;
- `GET /api/presences/seances-edt/<pk>/qr/` — permission `presences.qr.generer`, contrôles
  `peut_gerer_seance` **et** `est_seance_du_jour` ; un jeton actif est réutilisé plutôt que régénéré ;
- `POST .../<pk>/presences/`, `.../<pk>/emargement/`, `.../emargement/unitaire/`, `.../autoclore/` ;
- scan : `/api/presences/scan/`, `/scan/secure/` (+ heartbeat / exit), `/scan/offline-data/` ;
- consultation : `/api/presences/stats/*`, `/me/historique/`, `/formations/<pk>/presences/`.

Le registre n'invente aucune occurrence hors EDT : pas de séance, pas de pointage. Les secrets QR ne sont ni
journalisés ni exportés.

Écrans : `/edt` (grille), `/presences/seances`, `/presences/poste`, `/presences/registre`,
`/presences/audit`.

## 1.9 Étape 7 — Évaluations et notes

Objets (`evaluations/models.py`) : `SessionEvaluation` (type `NORMALE`, `RATTRAPAGE`, `RECTIFICATION` ;
périmètre explicite année/formation/parcours/niveau/semestre/maquette ; `verrouillee`, `regle_version`
gelée), `Evaluation` (`BROUILLON`, `PUBLIEE`, `CLOTUREE`, `ANNULEE` ; `poids` dans la moyenne de l'ECUE),
`EvaluationComposant`, `EvaluationParticipant`, `Epreuve`, `Note`, plus `RegleCalculVersion`.

Saisie des notes : `PUT /api/evaluations/composants/<pk>/notes/`. Règle de sécurité :
**une note verrouillée n'est jamais écrasée** ; chaque modification passe par l'historique
(`GET /api/evaluations/notes/historique/`).

Calcul : le moteur `evaluations/services/calcul.py` (`preparer`) produit un **projet** de résultat à partir
des composants et de leurs poids. Invariants du moteur, explicitement codés :

- une absence académique ou une dispense rend la composante **non notée** ; elle n'est jamais convertie en 0 ;
- des poids absents ne sont **pas** remplacés par un 50/50 : la situation est signalée, pas inventée ;
- la règle appliquée est figée (`regle_snapshot`, `formule_version`) et l'ensemble est empreinté en SHA-256
  (`evaluations/services/empreinte.py`) — les résultats sont reproductibles et auditables.

Hiérarchie des moyennes (`evaluations/services/`, `suiviEvaluation/services.py`) :
**ECUE → UE → semestre → décision**, sans saut d'étape ni seconde source de vérité.

## 1.10 Étape 8 — Résultats officiels et validation

`backend/scolarite/validation_services.calculer_validation_etudiant(inscription, maquette, regle)` est le
calcul qui fait foi pour la délibération :

1. ne retient que les inscriptions pédagogiques `PREVUE`/`VALIDEE` (hors abandon et dispense) ;
2. par ECUE : moyenne à partir des notes de module **verrouillées** uniquement
   (`NoteModule.verrouillee=True`), normalisées /20 puis moyennées par module ; une ECUE sans note reste
   `None` — la complétude est suivie séparément (`complet`) ;
3. par UE : moyenne pondérée par les coefficients des ECUE ; UE acquise si `≥ regle.seuil` ;
4. par semestre : moyenne pondérée par les crédits des UE ; compensation semestrielle si la règle l'autorise
   et si la moyenne du semestre atteint le seuil, **sauf** UE sous `seuil_elim` ;
5. décision proposée : `EXCLUSION` si une UE est sous le seuil éliminatoire (**jamais ramené à AJOURNE**),
   `ADMIS` si `credits_acquis ≥ Niveau.credits_requis` **et** toutes les ECUE complètes, sinon `AJOURNE`.

Le résultat retourné est un dictionnaire pur (semestres → UE → ECUE, crédits, décision proposée) : il est
reproductible et ne s'écrit pas dans le journal par effet de bord.

Tables de résultats (`ECUEResult`, `UEResult`, `SemesterResult`) : elles portent moyenne / moyenne brute,
`source = MOTEUR_LMD`, `migration_status`, `regle_snapshot`, `formule_version`, `empreinte` SHA-256 et
`verrouillee`. Elles sont **exposées en lecture seule** (`/resultats/ecue/`, `/resultats/ue/`,
`/resultats/semestre/`) et servent de source au relevé. *Limite constatée* : aucun service applicatif
n'alimente ces tables en dehors des tests — la décision qui fait autorité est celle du jury (voir 1.11),
le reste est une projection.

Relevés : `POST /api/evaluations/releves/generer/` crée **toujours une version suivante** (jamais une
réécriture) à partir des `ECUEResult`/`UEResult`/`SemesterResult` déjà publiés et des décisions de jury ;
`contenu_releve` projette la charge utile, `ReleveNotes` en conserve l'empreinte. Une absence ou une note
manquante reste `null`, jamais 0.

Passage de niveau : `GET /api/evaluations/resultats/passage/` est **un calcul technique en lecture seule**
(méthode GET). Il refuse de conclure quand une donnée manque (`AUCUN_RESULTAT`, `RESULTAT_EN_ATTENTE`,
`NIVEAU_CIBLE_INCONNU`) et ne produit **aucune** décision officielle — cf. D10.

Écrans : `/evaluations` (saisie), `/evaluations/controle`, `/evaluations/resultats`,
`/evaluations/releves`, `/evaluations/deliberations`.

## 1.11 Étape 9 — Jury et délibération

`SessionJury` suit une chaîne à neuf états, sans raccourci :

```
PREPARATION → CONTROLE → CALCUL → DELIBERATION → DECISION → PV_GENERE → VALIDE → VERROUILLE → PUBLIE
```

Actions exposées par un point unique, `POST /api/jurys/sessions/<pk>/action/` :

| `action` | Effet | Garde |
|---|---|---|
| `transition` | état suivant de la chaîne | `PV_GENERE` exige ≥ 1 `DecisionJury` ; `DELIBERATION` exige ≥ 1 `PropositionJury` |
| `calcul` | `calculer_propositions` : exécute `calculer_validation_etudiant` pour chaque inscription concernée et persiste une `PropositionJury` **append-only** (empreinte incluse) | session non verrouillée, statut `PREPARATION`/`CONTROLE`/`CALCUL` |
| `generer_pv` | génère le PV | réservé au personnel habilité (rôles complets) |
| `verifier_decisions` | vérifie que chaque étudiant concerné a une décision | — |
| `publier` | `VERROUILLE → PUBLIE` + notification Direction | PV obligatoire |

Saisie de décision : `POST /api/jurys/sessions/<pk>/decisions/` → `services.enregistrer_decision`.
Règles : saisie uniquement en `DELIBERATION`/`DECISION` ; une décision divergente de la proposition est
**manuelle** et exige une justification écrite ; unicité `(session, inscription)`. Décisions possibles :
`ADMIS`, `AJOURNE`, `ADMIS_RESERVES`, `EXCLUSION` — `EXCLUSION` n'est jamais convertie en `AJOURNE`.

**Autorité unique** : `jurys.DecisionJury` est la seule décision officielle. `suiviEvaluation` et les
relevés la reprennent telle quelle et ne recalculent jamais une décision (verrouillé par
`backend/suiviEvaluation/test_decision_hierarchie.py`). PV : `GET /api/jurys/sessions/<pk>/pv/`.

Écrans : `/scolarite/jurys`, `/jurys/composition`, `/jurys/deliberations`, `/jurys/pv`,
`/jurys/validation`.

## 1.12 Étape 10 — Diplôme, registre, réédition

Chaîne : `Diplome` → `RegistreDiplomes` (un par année, clôturable) + `Reedition` (append-only) +
vérification publique.

1. `POST /api/graduation/eligibles/` liste factuellement les inscriptions `VALIDEE` de **L3 et M2** et
   indique, pour chacune, si une décision de jury existe et si un diplôme est préparé/validé. Cet écran
   **ne décide rien**.
2. `POST /api/graduation/diplomes/creer/` — `etudiant_id`, `annee_academique_id`, `ref_formation_id`,
   `niveau_id` obligatoires ; création en `BROUILLON`.
3. `POST /api/graduation/diplomes/<pk>/valider/` (Direction / DFRC / Admin). `verifier_conditions_validation`
   exige **deux** choses : une inscription administrative `VALIDEE` sur le périmètre exact, et une
   `DecisionJury` rattachée à une session `VERROUILLE` ou `PUBLIE`. Ensuite : génération du PDF avec
   empreinte SHA-256, passage en `VALIDATED`, inscription au registre annuel, journal `DIPLOME_VALIDE`.
4. `POST .../diplomes/<pk>/revoquer/` — motif obligatoire ; le PDF d'origine reste conservé comme preuve ;
   aucune réédition tant que le diplôme n'est pas réhabilité par une nouvelle décision de jury.
5. `POST .../diplomes/<pk>/reedition/` — chaque réédition produit un **nouveau** PDF horodaté, hashé, à
   motif obligatoire ; le PDF original reste gelé (append-only).
6. `GET /api/graduation/registres/` et `/registres/<pk>/` — registre annuel ; une fois clôturé
   (`RegistreDiplomes.cloture`, `cloture_par`, `date_cloture`), tout ajout est refusé : clause de
   conservation longue durée.
7. `GET /api/graduation/diplomes/<pk>/pdf/` puis vérification publique `GET /api/graduation/verifier/<token>/`
   (`AllowAny`), le token étant l'UUID public du diplôme ; le matricule interne n'est jamais exposé.

Écrans : `/diplomation/eligibilite`, `/scolarite/graduation`, `/diplomation/registres`,
`/diplomation/attestations`, `/diplomation/certificats`, `/archives`.

## 1.13 Ce qui n'est pas automatisé dans le parcours

- la validation administrative **ne** crée **pas** les inscriptions pédagogiques (`INJS_AUTO_INSCRIPTION_PEDAGOGIQUE=False`) ;
- le passage de niveau est un calcul technique, jamais une inscription de l'année suivante : la
  réinscription reste une action explicite ;
- les conditions de diplômation ne branchent encore ni les stages ni la situation financière (les hooks L5/L6
  sont annoncés dans le modèle, pas implémentés) ;
- aucun résultat officiel n'est fabriqué par un script de démonstration : le seeding laisse les notes en
  brouillon et les paiements non confirmés (`SCENARIOS_DEMO.md`).

---

# 2. Génération **manuelle** des emplois du temps

La génération manuelle est le parcours historique, « poste par poste » : un agent pose les séances une par
une, avec un contrôle à chaque geste. Elle produit des données de même nature que la génération automatique
(`AffectationCreneau`) et suit le même circuit de validation/publication.

## 2.1 Qui a le droit de faire quoi

Défini côté serveur dans `backend/edts/permissions.py` (jamais seulement dans React) :

| Capacité | Rôles |
|---|---|
| planification (créer un brouillon, poser/déplacer une séance) | `ADMIN`, `CHEF_INJS_ADMIN`, `INJS_ADMIN`, `SECRETARIAT`, `CHEF_SECRETARIAT`, `DIRECTION`, `ENCADRANT` |
| validation / publication / dépublication / archivage encadré | `DIRECTION`, `ADMIN` (`VALIDATION_ROLES`) |
| lecture | tout compte authentifié |

## 2.2 Étape M1 — Référentiel horaire (créneaux types)

`CreneauTemplate` = couple `(jour, heure_debut, heure_fin)` normalisé à la minute : deux exécutions d'un
même plan de création reconduisent le **même** créneau au lieu d'en créer un nouveau (idempotence).

- `GET|POST /api/edts/creneaux-types/` — un doublon `(jour, début, fin)` renvoie 409 plutôt que d'être créé ;
- `GET|PATCH|DELETE /api/edts/creneaux-types/<pk>/` ;
- contrôle de conformité au canevas officiel INJS : `edts/moteur/canevas_officiel.py`
  (`grille_officielle`, `chevauchements`, `comparer_canevas`) et la commande
  `manage.py verifier_canevas` ; l'API expose la comparaison (`api_lmd.py`).

Sans créneaux types, aucune pose n'est possible : c'est le premier motif d'échec du moteur aussi
(`CANEVAS_HORAIRE_VIDE`).

## 2.3 Étape M2 — Créer l'emploi du temps en brouillon

`POST /api/edts/emplois/` :

- champs : `annee_academique_id` (requis), `population_type` ∈ `FORMATION` / `GROUPE` / `ENSEIGNANT` /
  `SALLE`, `population_id` (requis, libellé résolu par `_label_population`), `titre`,
  `semaine_debut` (défaut 1), `semaine_fin` (défaut 36), `rentree` ;
- refus **409** si un EDT existe déjà pour la même `(année, population_type, population_id)` : « ouvrez-le
  plutôt que d'en créer un second » ;
- refus si `semaine_fin < semaine_debut` ; `full_clean()` puis sauvegarde ;
- statut initial **`BROUILLON`**, `cree_par` renseigné, journal `EDT_CREE` avec la population cible.

Écran `/edt/nouveau` (`frontend/src/pages/EdtNew.jsx`) ; liste et détail sur `/edt` (`Edts.jsx`).

## 2.4 Étape M3 — Poser une affectation à la main

`POST /api/edts/affectations/` (`affectations_api`) :

- `emploi_du_temps_id`, `creneau_template_id`, `semaine_debut`, `semaine_fin` (≥ début), `nature`
  ∈ `COURS` / `TD` / `TP` / `EVALUATION` / `REMPLACEMENT` / `AUTRE`, `salle_nom`, `formation_id`,
  `groupe_id`, `enseignant_id` ou `formateur_id` (le nom d'enseignant est alors dérivé), `intitule`,
  `commentaire` ;
- contrôle préalable de l'existence de chaque cible (formation, groupe, formateur, créneau) ;
- après écriture : `services.verifier_affectation(a)` retourne des **avertissements non bloquants**
  (chevauchement de semaines **et** d'horaires sur enseignant / formateur / groupe / salle) — l'agent est
  informé, mais la pose est acceptée : c'est un poste de travail manuel ;
- journal `EDT_AFFECTATION_MODIFIEE` avec le nombre d'avertissements.

Écran dédié `/edt/:edtId/affectation/nouveau` (`AffectationNew.jsx`).

## 2.5 Étape M4 — Ajuster : déplacer, modifier, neutraliser

### Déplacement historique
`POST /api/edts/affectations/<pk>/deplacer/` : applique le nouveau créneau / les nouvelles semaines, puis
`verifier_affectation`. Si des conflits subsistent :

- **409** avec `detail`, `conflits`, `conseil` — rien n'est écrit ;
- sauf `forcer=true` **accompagné d'un motif** : le déplacement est alors accepté et tracé
  (`force`, `motif`, `conflits_assumes` dans le journal), et sans motif c'est un **400**.

### Déplacement LMD (moteur de contraintes)
`POST /api/edts/lmd/items/<pk>/move/` (`api_lmd.item_move_api`) : revalide la séance contre les contraintes
**C1 → C10** avant d'écrire ; en cas de violation, **409 sans aucune écriture**. Refus complémentaire si
l'EDT est `PUBLIE`/`ARCHIVE`, ou si l'année est passée en occurrences v2 (`QR_V2_CHEMIN_HERITE_REFUSE`).

### Modification / suppression
`GET|PATCH|DELETE /api/edts/affectations/<pk>/`. En LMD, la suppression n'est pas physique :
`POST /api/edts/lmd/items/<pk>/cancel/` réalise une **désactivation logique motivée** (le motif est
obligatoire), avec possibilité de `reactiver`. On conserve ainsi la trace de la séance annulée.

### Gel d'édition
`_peut_editer` (dans `edts/api.py`) :

- un EDT `VALIDE`, `PUBLIE` ou `ARCHIVE` est gelé pour un rôle de planification → **409** « un rôle
  Direction doit le dépublier avant toute modification » ;
- un EDT `EN_VALIDATION` est également gelé (l'agent peut retirer la soumission pour corriger) ;
- un EDT dont des séances portent une clé d'occurrence v2 est refusé sur **tout** le chemin historique, y
  compris pour la Direction : `QR_V2_CHEMIN_HERITE_REFUSE` (le service transactionnel v2 est le seul
  autorisé).

## 2.6 Étape M5 — Contrôles de conflits

Deux niveaux, complémentaires.

### Détection persistée, par EDT
`POST /api/edts/emplois/<pk>/conflits/` → `services.detecter_conflits(emploi_du_temps)` :

- compare les affectations **actives** de l'EDT entre elles **et** avec les affectations des autres EDT qui
  partagent un enseignant, un formateur, un groupe ou une salle ;
- crée ou réactive une ligne `ConflitCreneau` par paire en conflit, et **clôture** les conflits automatiques
  qui ne se vérifient plus ;
- ne touche jamais à un signalement **`MANUEL`** ouvert par un agent ;
- retourne des statistiques (détectés / clôturés) et jusqu'à 100 conflits actifs ; l'endpoint ne renvoie
  jamais 500 : la vue est garde-fousée.

Types de conflits (`CONFLIT_TYPE_CHOICES`) : `HORAIRE_ENSEIGNANT`, `HORAIRE_GROUPETUDIANT`,
`HORAIRE_SALLE`, `HORAIRE_MODULE`, `CAPACITE`, `COMPATIBILITE_SALLE`, `HORS_CALENDRIER`,
`DISPONIBILITE`, `MANUEL`.

Traitement : `GET /api/edts/conflits/` (filtres `emploi_du_temps_id`, `actif`),
`POST /api/edts/conflits/` (signalement manuel), `POST /api/edts/conflits/<pk>/resoudre/` avec un `motif`
qui est ajouté à la description puis journalisé (`EDT_CONFLIT_RESOLU`). Un conflit déjà clôturé renvoie 409.

### Contrôle croisé inter-EDT
`services.conflits_inter_edt(edt_ids)` compare plusieurs EDT sur leur fenêtre commune (C1/C2/C3) et retourne
`statut` ∈ `OK` / `CONFLITS` / `DONNEE_INCONNUE` / `INTERDIT` avec le détail des paires. C'est une lecture :
aucun éditeur, aucune suppression.

### Validation moteur d'un EDT persisté
`POST /api/edts/lmd/<pk>/validate/` → `validation.valider_emploi_du_temps(edt)` applique **exactement les
mêmes règles** que la validation d'un plan fraîchement généré (pas de tolérance supplémentaire pour un EDT
existant) : C1/C2/C3 sur les séances persistées, cohérence des semaines (C9), salle indisponible,
affectation pédagogique manquante (avertissement C8), volume (C10). Le statut passe à `VALIDE` **seulement**
si le rapport est valide, sinon il retombe en `EN_VALIDATION`, avec `valide_le`/`valide_par` remis à zéro.

## 2.7 Étape M6 — Workflow de statuts

Table `TRANSITIONS` (source unique, `edts/api.py`) et rôle requis par transition :

| Transition | Rôle |
|---|---|
| `BROUILLON → EN_VALIDATION` | planification |
| `EN_VALIDATION → VALIDE` | validation |
| `EN_VALIDATION → BROUILLON` | planification (retrait de soumission) |
| `VALIDE → PUBLIE` | validation |
| `VALIDE → EN_VALIDATION` | validation (renvoi en examen) |
| `PUBLIE → BROUILLON` | validation (dépublication) |
| `BROUILLON / EN_VALIDATION → ARCHIVE` | planification |
| `VALIDE / PUBLIE → ARCHIVE` | validation |
| `ARCHIVE → BROUILLON` | validation (réouverture encadrée) |

Toute autre combinaison est un **409** explicite qui rappelle la chaîne attendue. Chaque transition est
journalisée (`EDT_SOUMIS`, `EDT_VALIDE`, `EDT_PUBLIE`, `EDT_DEPUBLIE`, `EDT_ARCHIVE`).

Routes : `/emplois/<pk>/soumettre/`, `/valider/` (`statut: VALIDE` **ou** `PUBLIE`), `/publier/`,
`/depublier/`, `/archiver/`.

Deux gardes de soumission :

- un EDT contenant des **conflits actifs** ne peut pas être soumis → 409 « résolvez-les ou relancez la
  détection » ;
- un EDT **vide** est refusé : le statut est remis à `BROUILLON` avant la réponse 409.

## 2.8 Étape M7 — Publication

Deux chemins, de rigueur croissante.

**Chemin historique** `POST /api/edts/emplois/<pk>/publier/` : simple transition `VALIDE → PUBLIE`
(réservée Direction/Admin), refusée si des séances portent une clé v2.

**Chemin LMD** `POST /api/edts/lmd/<pk>/publish/` → `moteur/publication.publier_emploi_du_temps`, avec
verrou `select_for_update` et un **ordre de refus** strict et documenté :

1. `VERSION_EDT_MODIFIEE` — la version transmise par le client n'est plus la version courante ;
2. `EDT_DEJA_PUBLIE` ;
3. `STATUT_EDT_INVALIDE` — seul un EDT `VALIDE` est publiable ;
4. `QR_V2_NON_PUBLIABLE` — y compris avec `force` ;
5. `VALIDATION_BLOQUANTE` — violations C1→C10 (contournable par `force`, tracé) ;
6. `PLAN_INCOMPLET` — si les besoins attendus sont calculables et que des séances manquent ;
7. `AUCUNE_AFFECTATION_A_PUBLIER`.

Sur la route LMD, `force` **n'est pas exposé** : aucune publication forcée n'est possible par ce chemin. Les besoins attendus sont
recalculés depuis le périmètre déclaré de l'EDT (`_besoins_attendus_pour_publication`) — jamais depuis la
requête, qui permettrait de réduire artificiellement le nombre de séances attendues. La réponse indique en
plus si le contrôle de complétude a pu être appliqué, et pourquoi sinon.

En cas de succès : `statut = PUBLIE`, `publie_le` / `publie_par` renseignés, séances exploitables par les
présences.

## 2.9 Étape M8 — Suites : dépublication, version, sorties

- **Dépublication** : `PUBLIE → BROUILLON` (Direction), pour corriger ; l'EDT redevient éditable.
- **Archivage** : `→ ARCHIVE`, puis réouverture encadrée `ARCHIVE → BROUILLON`.
- **Versionnage** : `EmploiDuTemps.version` + `motif_modification`, unicité
  `(année, population_type, population_id, version)` et `empreinte` SHA-256 des paramètres de génération.
  Une nouvelle version se crée **par clonage**, jamais par écrasement : l'historique des versions reste
  consultable (`/api/edts/lmd/versions/`).
- **Sorties** : `GET /emplois/<pk>/grille/` (grille hebdomadaire, `services.grille_hebdomadaire`),
  `/export.csv/` (BOM UTF-8 pour Excel), `/lmd/<pk>/export.pdf/`, `/lmd/<pk>/export.xlsx/`,
  `/lmd/<pk>/grille/`, `/lmd/<pk>/audit/`, `/lmd/<pk>/result/`.
- **Consultation élargie** : `GET /api/edts/publics/` (EDT `VALIDE`/`PUBLIE`) ; `?selon_role=1` restreint un
  enseignant aux EDT où il est effectivement planifié.

## 2.10 Ce que le mode manuel ne fait pas

- il ne remplace jamais une séance existante sans que l'agent l'ait demandé ;
- il n'écrit jamais dans un EDT gelé, ni dans une année à occurrences v2 ;
- il n'efface pas une séance : `cancel` la désactive logiquement, avec motif ;
- il n'auto-publie pas : la publication reste un acte explicite d'un rôle Direction/Admin.

---

# 3. Génération **automatique** des emplois du temps

Le dépôt contient **quatre** moteurs de génération automatique, de portée croissante. Ils partagent le même
jeu de contraintes et la même règle d'or : **générer n'est jamais publier**. La publication reste l'action
explicite décrite en 2.8.

| Niveau | Entrée HTTP | Service | Portée |
|---|---|---|---|
| A — brouillon glouton | `POST /api/edts/emplois/{id}/generer/` | `edts/services.generer_brouillon` | un EDT existant |
| B — moteur LMD | `POST /api/edts/lmd/generate/` | `edts/moteur/generation.generate_schedule` | un périmètre LMD (formation → groupe) |
| C — coordonné | `POST /api/edts/lmd/generate-coordinated/` | `moteur/orchestration.generer_coordonne` | toutes les formations INJS de l'année |
| D — annuel / campagnes | `POST /api/edts/lmd/generate-annee/`, `/api/edts/campagnes/...` | `moteur/annee.generer_annee` + `moteur/campagnes` | tous les groupes de l'année, piloté par campagne |

## 3.1 Les entrées du moteur : besoins et contraintes

### Besoins (`moteur/besoins.py`)
`calculate_teaching_needs` construit un `TeachingNeed` par ligne d'`AffectationPedagogique` retenue
(`STATUTS_PLANIFIABLES = ('VALIDEE', 'PLANIFIEE')`) :
`nb_seances = max(1, round(volume_horaire / duree_moyenne_canevas))`, avec effectif du groupe, salle
compatible, nature d'enseignement et semestre. Des besoins peuvent aussi être fournis **déjà calculés**
(argument `besoins`) — c'est ainsi que sont planifiées les cohortes **importées** sans affectation
pédagogique, via `inclure_maquette` et `moteur/besoins_maquette.py`.

Motifs d'exclusion explicites, jamais silencieux : `AFFECTATIONS_PEDAGOGIQUES_VIDES`,
`HORS_PERIMETRE_INJS`, `CANEVAS_HORAIRE_VIDE`, `VOLUME_HORAIRE_INCONNU`, `C9_CALENDRIER`.

### Contraintes (`moteur/contraintes.py`, `moteur/validation.py`)
`C1` conflit enseignant · `C2` conflit groupe · `C3` conflit salle · `C4` capacité · `C5` disponibilité
enseignant · `C6` disponibilité salle · `C7` compatibilité salle/type d'enseignement · `C8` cohérence
pédagogique · `C9` calendrier · `C10` volume.

Les contraintes **dures** bloquent ; les contraintes **souples** sont paramétrables par
`PolitiqueContraintesSouples` (ligne unique, désactivée par défaut, avec auteur/date/motif). Priorité
effective : défauts du code < réglage Django < ligne `PolitiqueContraintesSouples` < paramètre explicite
d'une génération.

Le contrôle des conflits compare désormais les **intervalles de semaines complets** de deux récurrences
(cf. `AUDIT_GET_INJS_2026.md`, complément de seconde passe), et non plus seulement
`semaine_debut`.

## 3.2 Niveau A — brouillon glouton sur un EDT existant

`POST /api/edts/emplois/<pk>/generer/` → `services.generer_brouillon(emploi_du_temps, remplace_existant,
max_par_semaine=2)`.

Algorithme (glouton déterministe) :

1. source = `AffectationPedagogique` de l'année de l'EDT, statut `VALIDEE`/`PLANIFIEE`, **restreinte à la
   population** (formation ou groupe) ;
2. volume horaire → nombre de séances hebdomadaires, divisé par la durée moyenne des créneaux types et borné
   par `max_par_semaine` ;
3. placement sur la grille des créneaux types en évitant enseignant occupé, groupe occupé, salle déjà prise,
   et les indisponibilités datées quand la rentrée est connue ;
4. écriture dans l'EDT **uniquement s'il est en `BROUILLON`** (sinon 409 renvoyé par la vue).

`remplace_existant=True` supprime **uniquement les lignes générées** (`cree_par=None`) : les poses manuelles
d'un agent sont toujours conservées. La réponse contient des statistiques et l'explication de chaque échec de
placement.

Garde complémentaire : refus si des séances portent une clé v2, refus si le statut n'est pas `BROUILLON`.

C'est le bouton « Générer » de l'écran `/edt` ; il est aussi utilisé par certaines commandes.

## 3.3 Niveau B — le moteur LMD (`generate_schedule`)

`POST /api/edts/lmd/generate/` (`api_lmd.generate_api`) appelle **exclusivement**
`moteur/generation.generate_schedule` — il ne réutilise pas `generer_brouillon`. La docstring de la route le
dit explicitement.

### Paramètres du moteur
`annee_academique_id`, `ref_formation_id`, `parcours_id`, `niveau_id`, `semestre_id`, `groupe_ids`,
`semaines`, `creneaux`, `salles`, `duree_seance_heures`, `budget` (défaut `BUDGET_PLACEMENTS_DEFAUT =
200_000`), `perimetre_injs_seulement=True`, `occupations_initiales`, `besoins`, `contraintes_souples`.

La cohérence de la chaîne `Année → Formation → Parcours → Niveau → Semestre → Groupe` est vérifiée **côté
serveur** (`_parametres_lmd`) ; une incohérence renvoie `CHAINE_LMD_INCOHERENTE` avec l'action recommandée.
Les formations hors périmètre L6 (cycles legacy CPFAE, professorat) sont refusées explicitement.

### Sortie toujours structurée
`status` ∈ `GENERATION_OK` / `GENERATION_PARTIELLE` / `GENERATION_IMPOSSIBLE` /
`GENERATION_BUDGET_EXHAUSTED`, plus `placements`, `non_places`, `conflits`, `warnings`, `metrics`,
`motif_echec`. Les causes de blocage sont distinguées : `AFFECTATIONS_PEDAGOGIQUES_VIDES`,
`HORS_PERIMETRE_INJS`, `CANEVAS_HORAIRE_VIDE`, `C9_CALENDRIER`, `AUCUNE_SALLE_COMPATIBLE`,
`PLACEMENT_IMPOSSIBLE`.

### Persistance : deux temps, jamais implicite
- `persister=false` (défaut) : **prévisualisation**, le moteur n'écrit rien ;
- `persister=true` : `emploi_du_temps_id` devient obligatoire (`EDT_INTROUVABLE` sinon), l'EDT doit être
  `BROUILLON` ou `EN_VALIDATION` (`STATUT_EDT_INVALIDE`), puis `validation.validate_schedule` est exécuté :
  - rapport **valide** → `publication.persister_plan(edt, placements, remplacer)` écrit les
    `AffectationCreneau` dans une transaction (verrou sur l'année, refus si occurrences v2), réponse 201 ;
  - rapport **invalide** → **rien n'est écrit**, réponse 200 avec `raison_refus_persistance` et la liste des
    violations.

`remplacer=true` désactive les séances existantes avant réécriture : relancer une génération identique ne
duplique jamais de séances.

`generate_schedule` accepte `occupations_initiales` : un état d'occupation déjà consommé ailleurs (séances
persistées d'autres EDT, placements de runs antérieurs) qui participe aux contrôles C1/C2/C3 **sans jamais
être modifié ni persisté**. C'est la brique qui rend possible le niveau C.

## 3.4 Niveau C — génération coordonnée de toutes les formations INJS

`POST /api/edts/lmd/generate-coordinated/` → `orchestration.generer_coordonne(annee_id, semaines,
persister=False, remplacer=True)` ; conception dans `docs/ADR/ADR-007`.

Principes :

1. **périmètre dérivé, jamais fourni** : `formations_a_planifier(annee_id)` retourne les formations qualifiées
   INJS (référentiel L6) portant des affectations `VALIDEE`/`PLANIFIEE`, triées par identifiant. Aucune liste
   de formations n'est acceptée de la requête — ce serait un vecteur d'arbitraire ;
2. **ordre déterministe** : les formations sont traitées séquentiellement ; chaque run reçoit l'état
   d'occupation global (placements des runs précédents + séances persistées des autres EDT de l'année, hors
   EDT que `remplacer` va désactiver) ;
3. **atomicité par EDT** : `persister_plan` est transactionnel par EDT ; `remplacer=True` garantit
   l'idempotence (relancer ne duplique rien) ;
4. **aucune publication** : le parcours publication reste `POST /api/edts/lmd/{id}/publish/` ;
5. **refus explicites** : `annee_academique_id` requis (`ANNEE_ACADEMIQUE_REQUISE`), année inconnue
   (`ANNEE_ACADEMIQUE_INTROUVABLE`), année à occurrences v2 (`QR_V2_CHEMIN_HERITE_REFUSE`), aucune formation
   planifiable (`COORDONNEE_IMPOSSIBLE` + `MOTIF_AUCUNE_FORMATION` + action recommandée).

Statuts de bilan : `COORDONNEE_OK`, `COORDONNEE_PARTIELLE`, `COORDONNEE_CONFLITS`, `COORDONNEE_IMPOSSIBLE`
(plus `ERREUR` en cas d'exception d'un run). Le bilan expose **par EDT** les besoins, placements,
non-placements et motifs, et **globalement** les conflits inter-EDT (LOT 1, lecture seule) et les données
inconnues. « Une opération dont un EDT est incomplet, non persisté ou en conflit n'est jamais présentée comme
pleinement réussie. »

*État de l'interface* : le composant `frontend/src/components/GenerationCoordonnee.jsx` existe et connaît
tous ces statuts et motifs, **mais il n'est monté dans aucune page** (il n'apparaît que dans ses tests). La
route API est donc utilisable, l'écran dédié n'est pas branché.

## 3.5 Niveau D — génération annuelle et campagnes

### D.1 `generate-annee` : tous les groupes de l'année

`POST /api/edts/lmd/generate-annee/` → `moteur/annee.generer_annee(...)`.

Paramètres : `annee_academique_id`, `semaines`, `persister`, `remplacer`, `budget`,
`inclure_maquette` (défaut vrai : complète les cohortes sans affectation pédagogique à partir de la maquette
active), `formation_ids`, `niveau_ids`, `groupe_ids`, `semestre_numeros`, `inclure_samedi`,
`eviter_pause_meridienne`, `max_seances_par_groupe_semaine`, `calendrier_previsionnel`, `salle_ids`,
`batiment_ids`, `autoriser_plan_partiel`.

Contrôles d'entrée : les semaines doivent être des entiers **1 à 53** (une liste vide est refusée, une chaîne
`"8"` désigne la seule semaine n°8 — pas huit semaines) ; bâtiments et salles doivent être des listes
d'entiers existants et actifs ; un local sélectionné doit appartenir à un bâtiment sélectionné.

Sortie : statut `COMPLETE` / `PARTIELLE` / `IMPOSSIBLE`, bilan **par groupe** (statut, séances
attendues/placées/non placées, motif d'échec) et global. Un quota hebdomadaire écrêté reste compté comme
**attendu non placé** : le quota ne masque aucune séance. `autoriser_plan_partiel` n'écrit que les séances
conformes, et ces EDT ne deviennent pas publiables.

Garde-fou anti-faux-succès : `annee.py` mesure, **avant toute création d'EDT**, les occurrences et les heures
implicites des placements multi-semaines ; en cas d'écart de volume, de semaine hors sélection ou de
semestres non répartis, le groupe porte `REPARTITION_ANNUELLE_NON_CONFORME`, l'année n'est plus `COMPLETE` et
la persistance est refusée (aucun brouillon créé). La planification par occurrences unitaires
(`_generer_occurrences_par_semaine`) n'est activée que si l'appelant a explicitement ciblé **un seul
semestre** et fourni plusieurs semaines.

### D.2 Écran `/edt/generation-annuelle`

`frontend/src/pages/getinjs/GenerationAnnuelle.jsx` propose deux modes explicites :

- **Manuel (périmètre ciblé)** : filières, formations/parcours, niveaux, groupes, semestres, bâtiments,
  salles, liste obligatoire des semaines réelles 1–53, option samedi, option « éviter la pause méridienne »
  (12h–14h), quota `séances max / groupe / semaine`, option « publier directement ». La génération exige une
  **prévisualisation du périmètre exact** : toute modification de sélection invalide la signature d'aperçu et
  oblige à re-prévisualiser. Un plan partiel exige un consentement explicite (couverture affichée en %), et
  l'écran avertit si le périmètre est large avec trop peu de semaines ;
- **Automatique (toute l'année)** : périmètre entier, sans sélection manuelle, sans quota, sans publication.
  Le calendrier est **provisoire et non officiel** : il est dérivé des dates de l'année (semestres impairs /
  pairs, bascule estimée) et doit être **confirmé** avant lancement.

Dans les deux cas, le lancement crée une **campagne** (`POST /api/edts/campagnes/`) puis la démarre : l'écran
ne fait pas un appel de génération « nu ». Un transfert `?simulation_id=` permet de reprendre le périmètre
d'une simulation.

### D.3 Campagnes : le pilotage de bout en bout

`moteur/campagnes.py` + `api_getinjs.py`. Statuts `CampagneGeneration` :

```
BROUILLON → VALIDATION_DONNEES → PRET → EN_COURS → TERMINE | TERMINE_AVEC_ANOMALIES | ECHEC
                                                      → VALIDE → PUBLIE
```

| Étape | Route | Points de contrôle |
|---|---|---|
| créer | `POST /api/edts/campagnes/` | `annee_academique_id` + `libelle` requis (libellé unique) ; l'**effectif importé est mesuré** à la création et sert de référence ; `autoriser_plan_partiel` n'est accepté que si c'est un booléen JSON explicite, en mode `manuel`/`automatique`, et hors simulation ; en mode `automatique`, `calendrier_previsionnel_confirme` et `calendrier_dates_confirmees` sont exigés (`CALENDRIER_NON_CONFIRME`, `CALENDRIER_INVALIDE`) ; bâtiments/salles validés comme en D.1 |
| préparer | `.../donnees-pretes/`, puis interne `valider_donnees`, `marquer_pret` | aucune donnée manquante ne doit devenir une génération « réussie » |
| démarrer | `POST .../<pk>/demarrer/` | `select_for_update` + `CAMPAGNE_DEJA_EN_COURS` ; exécution dans un thread `getinjs-campagne-*` (`asynchrone=true` par défaut → 202) ; **une simulation force `persister=False`** ; refus si l'année est en occurrences v2 |
| suivre | `GET .../<pk>/statut/` | interrogation toutes les 2 s côté écran, délai maximal 20 min |
| lire le bilan | `GET .../<pk>/resultat/` | séances attendues / placées / non placées par groupe, motifs, anomalies |
| valider | `POST .../<pk>/valider/` (Direction/Admin) | refus si statut ≠ `TERMINE`, si `status_global != COMPLETE`, s'il existe des anomalies, ou si un EDT échoue aux contraintes C1–C10 ; refus si la campagne est une simulation ; refus si aucun EDT persisté. Chaque EDT est revalidé par `valider_emploi_du_temps` |
| publier | `POST .../<pk>/publier/` | **atomique** : `transaction.atomic` + `publier_emploi_du_temps` par EDT ; un seul échec lève `PUBLICATION_INCOMPLETE` et **annule tout le lot** (« on ne laisse jamais un semestre à moitié publié ») ; l'empreinte de publication est conservée dans l'historique |

Autres routes de la famille : `GET /api/edts/campagnes/` (filtre `annee`, `simulation` ; `?limite=` défaut
200, maximum 1000), `.../historique/`, `.../detail/`.

Écran `/edt/campagnes` (`CampagnesGeneration.jsx`) ; `SCENARIOS_DEMO.md` laisse volontairement une campagne à
l'état **Prêt** pour la démonstration du lancement.

### D.4 Amont du niveau D : dimensionnement et import

Rien ne sert de générer pour une population mal connue. Deux outils précèdent :

- `GET /api/edts/lmd/dimensionnement/?annee=&capacite=` → `dimensionnement.dimensionner(annee,
  capacite_cible=60)` : promotions à planifier, groupes nécessaires pour la capacité cible, EDT de groupe à
  produire (**dérivés**, jamais imposés), séances attendues d'après les maquettes actives, promotions réelles
  et anomalies à traiter. `POST .../dimensionnement/constituer/` → `constituer_groupes` (idempotent, mode
  `simulation` disponible : le calcul est visible, l'écriture est optionnelle) ;
- `POST /api/edts/lmd/import/inscrits/analyser/` puis `.../inscrits/` : analyse **sans écriture** puis import
  idempotent et journalisé de la population inscrite (résolution formation/niveau/parcours, motifs de rejet,
  `map_colonnes`, `effectif_population_consolidee`) ; `.../inscrits/journal/` et `.../inscrits/` en lecture.

Écrans : `/edt/dimensionnement`, `/edt/import-etudiants`, `/edt/etudiants-inscrits`, `/edt/simulation`.

## 3.6 Sécurité et traçabilité communes

- **Habilitations serveur** : `IsEdtPlanification`, `IsEdtValidation`, `IsEdtReadOnlyOrPlanification` —
  jamais un simple masquage de bouton ;
- **journal** : chaque génération, affectation, transition, résolution de conflit et publication laisse une
  ligne (`_journal`, `EDT_GENERATION`, `EDT_PUBLIE`, `DIPLOME_VALIDE`, etc.) avec acteur et paramètres ;
- **empreinte** : `EmploiDuTemps.empreinte` (SHA-256 des paramètres de génération) garantit qu'une relance
  strictement identique ne duplique rien ;
- **isolation v2** : dès qu'une année porte des occurrences v2, tous les chemins historiques (génération,
  persistance, édition, publication, campagne) refusent d'écrire et renvoient
  `QR_V2_CHEMIN_HERITE_REFUSE` ;
- **simulation ≠ production** : une campagne de simulation ne peut ni valider ni publier ; son périmètre doit
  être transféré vers une campagne distincte pour produire des EDT réels.

## 3.7 Limites mesurées du moteur automatique

Ces limites sont dans le dépôt (`docs/audits/AUDIT_GET_INJS_2026.md`) et sont reprises ici sans atténuation :

- **Couverture annuelle non prouvée — verdict ROUGE** pour « génération complète de l'année » : les campagnes
  globales de démonstration atteignaient 90/39 146 séances attendues, sans groupe complet ; le modèle
  `scolarite.Semestre` **ne contient pas de dates de début/fin**, donc un découpage S1/S2 par hypothèse serait
  trompeur ;
- **solveur historique** : `generation.candidats` produit un bloc récurrent sur `[semaines[0], semaines[-1]]`
  par besoin, sans répartition des occurrences réelles ; le compteur de couverture provenait des besoins, pas
  des occurrences persistées. Un contre-exemple mesuré donnait 6 h demandées / 16 h proposées sur 4 semaines,
  d'où le garde `REPARTITION_ANNUELLE_NON_CONFORME` (protection contre un faux succès, pas une résolution) ;
- **preuve positive bornée** : la planification par occurrences unitaires a été prouvée sur fixture en
  base de test — 6 h / 3 occurrences persistées sur 4 semaines, 100 % du volume ciblé, 0 conflit, brouillon
  non publié ; avec deux groupes, 12 h / 6 occurrences, zéro double occupation. Cela qualifie un **périmètre
  manuel mono-semestre** (ORANGE), pas l'année entière ;
- **échelle non démontrée** : 5 000 inscrits et 39 146 demandes n'ont pas été rejoués ; pas de mesure de
  latence/mémoire à cette échelle ;
- **index d'occupations** : le solveur ignore encore la distribution temporelle réelle dans son index, même
  si le validateur compare désormais les intervalles complets ;
- **interface** : `GenerationCoordonnee.jsx` n'est pas monté ; la route coordonnée est utilisable mais sans
  écran dédié.

Conclusion opérationnelle : la génération automatique est fiable **en prévisualisation** et sur un périmètre
ciblé validé ; elle ne doit pas être présentée comme productrice d'un EDT annuel complet et publiable, et une
campagne annuelle globale ne doit pas être lancée sans échantillon validé et sauvegarde.

---

# 4. Récapitulatif — manuel vs automatique

| | Manuel | Automatique |
|---|---|---|
| Point d'entrée | `/edt` → `POST /api/edts/emplois/` puis `/affectations/` | `/edt/generation-annuelle`, `/edt/campagnes` → `campagnes/` |
| Qui décide du placement | l'agent (référentiel `CreneauTemplate`) | le moteur (`generate_schedule`, backtracking borné) |
| Contrôles | `verifier_affectation` (avertissements), `detecter_conflits` (persisté), C1→C10 au déplacement LMD et à la validation | C1→C10 appliquées pendant la recherche, puis `validate_schedule` avant toute écriture |
| Écriture | immédiate, journalisée, séance par séance | seulement si `persister=true` **et** rapport d'audit valide |
| Statut produit | `BROUILLON` | `BROUILLON` (jamais plus) |
| Régénération | geste manuel | `remplacer=true` : désactivation puis réécriture, idempotent |
| Publication | `soumettre` → `valider` → `publier` (Direction/Admin) | identique, plus le chemin `publish` avec contrôle de complétude, plus la campagne atomique |
| Traçabilité | journal `EDT_*` + `motif_forçage` | journal `EDT_GENERATION` + `empreinte` + bilan de campagne |

Dans les deux cas : **générer n'est pas publier**, un EDT gelé n'est jamais réécrit, une année à occurrences
v2 est interdite aux chemins historiques, et une opération incomplète est toujours présentée comme
incomplète.

---

# 5. Où lire le code

| Sujet | Fichier |
|---|---|
| Candidature (machine à états) | `backend/admissions/workflow.py`, `admissions/models.py`, `admissions/urls.py` |
| Admission → inscription | `backend/scolarite/inscription_services.py` (`convertir_admission_en_inscription`), `matricules.py` |
| Inscriptions pédagogiques | `backend/scolarite/pedagogie_api.py`, `scolarite/models.py` |
| Groupes | `backend/scolarite/groupes_api.py`, `groupes_services.py` |
| Calcul de validation | `backend/scolarite/validation_services.py` |
| Notes et moteur C2 | `backend/evaluations/services/{calcul,passage,releves,empreinte}.py`, `evaluations/views.py` |
| Jury | `backend/jurys/{models,services,api}.py`, `pv_services.py` |
| Diplômation | `backend/graduation/{models,services,api,urls}.py` |
| Présences | `backend/presences/seances_edt_api.py`, `edts/models_interop.py`, `edts/moteur/interop_presences.py` |
| EDT manuel | `backend/edts/api.py`, `edts/services.py`, `edts/models.py`, `frontend/src/pages/{Edts,EdtNew,AffectationNew}.jsx` |
| Moteur LMD | `backend/edts/moteur/{generation,contraintes,validation,publication,orchestration,annee,besoins,besoins_maquette,canevas_officiel}.py` |
| Campagnes | `backend/edts/moteur/campagnes.py`, `edts/api_getinjs.py`, `frontend/src/pages/getinjs/{GenerationAnnuelle,CampagnesGeneration}.jsx` |
| Contrats et décisions d'architecture | `docs/ADR/ADR-003`, `docs/ADR/ADR-007`, `docs/audits/AUDIT_GET_INJS_2026.md` |
| Scénario de démonstration | `docs/demo/injs-lmd/SCENARIOS_DEMO.md` |
