---
titre: Parcours académique d'un étudiant
soustitre: De la candidature à la diplômation — processus réel, cas pratiques et traces attendues
surtitre: INJS-LMD 2026 · DOSSIER 1 SUR 3
objet: Décrire la chaîne complète du parcours étudiant telle qu'elle est implémentée dans le dépôt backend-injs2026, avec des cas concrets, les statuts franchis, les contrôles serveur et les codes de refus.
public: Direction, DFRC, secrétariat, chefs de département, encadrants
perimetre: backend/injs2026 — applications admissions, scolarite, edts, presences, evaluations, jurys, graduation
date: 24 novembre 2026
header: Parcours académique — candidature à la diplômation
resume: Ce dossier décrit, étape par étape, ce que le socle fait réellement subir à un dossier étudiant, de la campagne de candidature jusqu'à l'inscription au registre des diplômes. Chaque étape est illustrée par un cas pratique chiffré et par la trace que le système en conserve. Les garde-fous sont nommés par leur code de refus, afin qu'un agent puisse relier un message à l'écran à la règle qui l'a produit.
sommaire: 1. Vue d'ensemble et paramétrage préalable; 2. Candidature — machine à états et pièces; 3. Admission — les deux propriétés qui décident de tout; 4. Inscription administrative — conversion, matricule, dossier; 5. Inscription pédagogique et équivalences; 6. Affectation en groupe; 7. Emploi du temps, séances et présences; 8. Évaluations et notes; 9. Calcul des résultats officiels; 10. Jury, délibération et PV; 11. Diplôme, registre et réédition; 12. Cas pratiques de bout en bout; 13. Ce que le système refuse de faire; 14. Où lire le code
---

# 1. Vue d'ensemble et paramétrage préalable

## 1.1 La chaîne complète

Le parcours étudiant traverse sept applications, chacune propriétaire de sa part de vérité :

```
CampagneAdmission → Candidat → Candidature (+ PieceCandidature)
        ↓ décision
Admission ──convertir_admission_en_inscription──▶ DossierEtudiant (adossé au Participant)
        ↓
InscriptionAdministrative ──▶ InscriptionPedagogique (une ligne par ECUE)
        ↓                              ↓
  AffectationGroupe / Groupe ◀── Maquette → UE → ECUE
        ↓
EmploiDuTemps → AffectationCreneau → SeanceRegistre → Présences (QR, émargement)
        ↓
SessionEvaluation → Evaluation → composants → notes → résultats ECUE / UE / semestre
        ↓
SessionJury → PropositionJury → DecisionJury → PVJury
        ↓
Diplome → RegistreDiplomes (+ Reedition, vérification publique par token)
```

Trois principes structurent cette chaîne et expliquent la plupart des blocages observés à l'écran :

- **une seule autorité par décision** : le workflow d'admission ne se contourne pas, la décision officielle est `jurys.DecisionJury`, le calcul de validation est `scolarite/validation_services.py` ;
- **pas d'enchaînement implicite** : valider une inscription administrative ne crée pas les inscriptions pédagogiques ; le passage de niveau ne crée pas l'inscription de l'année suivante ; générer un EDT ne le publie pas ;
- **une donnée manquante ne vaut jamais validation** : une ECUE sans note reste `null`, un semestre en attente rend le passage `INDETERMINABLE`, un diplôme sans décision de jury est refusé.

## 1.2 Le paramétrage qui conditionne tout le reste

| Objet | Rôle dans le parcours | Effet d'un défaut |
|---|---|---|
| AnneeAcademique (cloturee) | borne les inscriptions et les EDT | année clôturée = validation d'inscription refusée |
| RefFormation, Parcours, Niveau, Semestre | chaîne LMD ; Niveau.credits_requis (défaut 60) | pas de maquette rattachable |
| Maquette (BROUILLON, VALIDEE, ACTIVE, ARCHIVEE) | version applicable ; l'ECUE affectée doit appartenir à la maquette ACTIVE | inscription pédagogique impossible |
| UE / ECUE (crédits, coefficients, volumes) | unités de calcul et de planification | moyennes et EDT non calculables |
| RegleValidationLMD | seuil (défaut 10/20), compensation SEMESTRE, seuil_elim, credits_semestre (30) | calcul aux valeurs par défaut |
| Groupe (capacite_max, actif) | regroupement pédagogique L1-G1 | étudiant sans EDT |
| AffectationPedagogique (PROPOSEE → VALIDEE → PLANIFIEE) | relie enseignant, ECUE, groupe, volume | aucun besoin horaire, donc aucun EDT |
| CreneauTemplate, DisponibiliteHoraire | canevas et indisponibilités | CANEVAS_HORAIRE_VIDE |

note:: Le canevas officiel INJS est de 24 créneaux : 6 jours (lundi à samedi) × 4 plages de 2 h — 07:30-09:30, 09:45-11:45, 13:30-15:30, 15:45-17:45. Il provient de la feuille « 13. Emploi du temps (modèle) » et se contrôle par manage.py verifier_canevas.

---

# 2. Candidature — machine à états et pièces

## 2.1 Une seule porte d'entrée

`backend/admissions/workflow.py` définit `TRANSITIONS` et une seule fonction d'application, `appliquer_transition`. Toute autre écriture est considérée comme une fuite. Une transition non déclarée lève `TransitionInterdite`.

```
BROUILLON → SOUMISE → EN_ATTENTE_DE_VERIFICATION
   ├─→ PIECES_INCOMPLETES → (dépôt) → EN_ATTENTE_DE_VERIFICATION
   └─→ PIECES_VALIDEES → EN_ETUDE
          ├─→ ADMISSIBLE → ADMIS | ADMIS_SOUS_RESERVE
          │                | LISTE_ATTENTE | REFUSE
          └─→ REFUSE
(tout état ouvert → ANNULE)
```

## 2.2 Identité et numérotation

- `Candidat` porte l'état civil (nom, prénoms, date et lieu de naissance, sexe, nationalité, contacts).
- `Candidature` porte le numéro unique, généré à la création : `CAND-<libellé de l'année>-<séquence sur 4 chiffres>`, par exemple **CAND-2026-2027-0001**. Le numéro est calculé par préfixe d'année et n'est jamais éditable.
- Une candidature porte aussi l'année, la formation, le parcours et le niveau demandés, le type de candidature et la voie d'accès (concours direct, admission sur titre).

## 2.3 Les pièces justificatives

`PieceCandidature` a son propre cycle de vie : `MANQUANTE`, `FOURNIE`, `EN_VERIFICATION`, `VALIDEE`, `REFUSEE`, `EXPIREE`. Chaque pièce porte un caractère obligatoire ou non, un fichier contrôlé par `validators_pieces.valider_piece_candidature`, un numéro de document et une date d'expiration.

Deux propriétés de `Candidature` rendent la suite possible : `dossier_complet` et `completude`, qui retourne le couple (validées, total). Ce couple est repris tel quel dans les messages d'erreur du secrétariat.

## 2.4 Les routes

| Action | Route |
|---|---|
| lister et consulter les candidats | GET /api/admissions/candidats/ et /candidats/<pk>/ |
| créer, consulter une candidature | GET, POST /api/admissions/candidatures/ |
| faire avancer le dossier | POST /api/admissions/candidatures/<pk>/transition/ |
| déposer une pièce | POST /api/admissions/pieces/<id>/deposer/ |
| vérifier une pièce | POST /api/admissions/pieces/<id>/verifier/ |
| télécharger une pièce | GET /api/admissions/pieces/<id>/fichier/ |
| statistiques par statut | GET /api/admissions/candidatures/stats/ |

cas:: **Cas 1 — dossier incomplet.** Une candidate dépose trois pièces sur quatre. Le secrétariat constate l'absence du certificat médical et fait passer le dossier en PIECES_INCOMPLETES. La candidature ne peut pas entrer en étude : la transition PIECES_INCOMPLETES → EN_ETUDE n'existe pas dans TRANSITIONS, la tentative renvoie un refus explicite. Après dépôt et vérification de la pièce manquante, le dossier repart en EN_ATTENTE_DE_VERIFICATION puis PIECES_VALIDEES, et seulement là en EN_ETUDE.

## 2.5 La voie concours

Pour les filières à concours, la même application porte `CampagneAdmission` (BROUILLON → PLANIFIEE → OUVERTE ⇄ SUSPENDUE → CLOTUREE → ARCHIVEE, avec ANNULEE), les épreuves (écrit, physique, oral, pratique), les convocations, les présences, `NoteConcours` et le classement (`classement/calculer/`, `classement/publier/`). Une épreuve verrouillée refuse toute modification de note et toute note modifiée est historisée : on ne réécrit jamais une note de concours sans trace.

---

# 3. Admission — les deux propriétés qui décident de tout

`Admission` porte la décision (`ADMIS`, `ADMIS_SOUS_RESERVE`, `EN_ATTENTE`, `REFUSEE`, `ANNULEE`), sa date, sa référence, son auteur et surtout une `date_limite_inscription`. Deux propriétés gouvernent la suite du parcours :

- `est_expiree` : vrai si `date_limite_inscription` est dépassée ;
- `permet_inscription` : vrai seulement pour ADMIS ou ADMIS_SOUS_RESERVE **et** non expirée.

alerte:: Ces deux propriétés sont évaluées côté serveur au moment de la conversion. Aucun écran ne peut les contourner : une admission expirée reste expirée même si le bouton « Inscrire » est cliquable.

cas:: **Cas 2 — les deux refus d'admission.** (a) Une candidate est admise avec une date limite au 30 septembre ; le secrétariat tente l'inscription le 12 octobre : refus « Admission expirée depuis le 30/09/2026 ». (b) Un candidat est en LISTE_ATTENTE : refus « La décision “Liste d'attente” ne permet pas d'inscrire ce candidat. » Dans les deux cas rien n'est créé : ni Participant, ni matricule, ni inscription.

---

# 4. Inscription administrative — conversion, matricule, dossier

## 4.1 Une conversion, pas une saisie

`POST /api/scolarite/inscriptions/depuis-admission/` appelle `scolarite/inscription_services.convertir_admission_en_inscription(admission, acteur, matricule, valider)`. Le service exécute, dans une seule transaction :

1. contrôle de `permet_inscription` (message distinct pour l'expiration) ;
2. contrôle du dossier de pièces : refus tant que `dossier_complet` est faux, avec le décompte `validées/total` ;
3. **idempotence** : une admission ne produit qu'une seule inscription vivante. Si elle existe déjà (hors ANNULEE et REJETEE), elle est retournée telle quelle avec le marqueur interne `rejeu_idempotent`, et la réponse HTTP passe de 201 à **200** — le client ne doit pas croire qu'une seconde inscription vient d'être ouverte ;
4. création ou reprise du `Participant`, puis génération du **matricule** ;
5. création ou reprise du `DossierEtudiant` ;
6. création de l'inscription, statut BROUILLON, avec le type d'inscription (PREMIERE, REINSCRIPTION, REDOUBLEMENT, REPRISE, REORIENTATION, TRANSFERT) ;
7. si `valider=true`, enchaînement des transitions jusqu'à VALIDEE.

## 4.2 Le matricule

Format `INJS<deux derniers chiffres de l'année de début>-<séquence sur 4 chiffres>` : **INJS26-0001** pour 2026-2027. La séquence est calculée sur les seuls matricules qui suivent ce format ; les matricules importés d'Excel, qui ne suivent aucun format imposé, sont ignorés par le calcul et jamais invalidés. En cas de collision, la séquence avance.

## 4.3 Le dossier et l'identité

`DossierEtudiant` est un `OneToOne` sur `formations.Participant` : le matricule appartient au Participant, pas au dossier. Le socle évite ainsi une seconde identité étudiante. Le Participant reste l'entité référencée par les présences, les notes et la finance.

## 4.4 La machine à états de l'inscription

```
BROUILLON   → EN_ATTENTE | ANNULEE
EN_ATTENTE  → A_VALIDER | REJETEE | ANNULEE
A_VALIDER   → VALIDEE | REJETEE | EN_ATTENTE | ANNULEE
VALIDEE     → SUSPENDUE | TERMINEE | ANNULEE
SUSPENDUE   → VALIDEE | ANNULEE | TERMINEE
```

`appliquer_transition` refuse : une inscription archivée (il faut la réactiver), une transition vers le statut courant, une transition non déclarée, et le passage à VALIDEE sur une année clôturée. Chaque transition est journalisée dans `JournalScolarite`.

Table de décision du service, selon l'état de l'inscription existante lors d'un rejeu avec `valider=true` :

| Statut existant | Effet du rejeu valider=true |
|---|---|
| BROUILLON | progression vers A_VALIDER puis VALIDEE |
| EN_ATTENTE | progression vers A_VALIDER puis VALIDEE |
| A_VALIDER | passage à VALIDEE |
| VALIDEE | aucune transition : retour idempotent, 200 |
| SUSPENDUE | jamais réactivée par un rejeu : 200 sans changement |
| TERMINEE | jamais rouverte par un rejeu : 200 sans changement |

## 4.5 Les routes utiles

| Besoin | Route |
|---|---|
| convertir une admission | POST /api/scolarite/inscriptions/depuis-admission/ |
| liste et détail | GET /api/scolarite/inscriptions/ et /inscriptions/<pk>/ |
| valider en lot | POST /api/scolarite/inscriptions/valider-lot/ |
| action en lot | POST /api/scolarite/inscriptions/action-lot/ |
| transition unitaire | POST /api/scolarite/inscriptions/<pk>/transition/ |
| réactiver, radier, changer de parcours | POST .../reactiver/, .../radier/, .../changer-parcours/ |
| statistiques | GET /api/scolarite/inscriptions/stats/ |
| réinscription | GET, POST /api/scolarite/reinscriptions/ |

cas:: **Cas 3 — le double clic.** Le secrétariat clique deux fois sur « Inscrire depuis l'admission ». La première requête crée le matricule INJS26-0042, le dossier et l'inscription. La seconde retrouve l'inscription vivante et répond **200** avec le même dossier : aucun second matricule, aucune seconde inscription, une seule entrée de journal. C'est exactement le scénario que le garde-fou d'idempotence a été écrit pour couvrir.

---

# 5. Inscription pédagogique et équivalences

## 5.1 Une ligne par ECUE suivie

`InscriptionPedagogique` enregistre, ECUE par ECUE, ce que l'étudiant doit suivre. Propriétés structurantes :

- unicité `(inscription, ecue)` : on ne peut pas inscrire deux fois la même ECUE ;
- statut `PREVUE`, `VALIDEE`, `ABANDONNEE`, `DISPENSEE` ;
- origine `AUTOMATIQUE` (générée depuis la maquette) ou `MANUELLE` ;
- ECTS et volumes **dénormalisés** au moment de l'inscription : la maquette peut évoluer ensuite sans réécrire l'histoire du dossier ;
- groupe rattaché de même année et même niveau.

## 5.2 Le point de contrat le plus important

note:: L'enchaînement automatique « validation administrative → génération des inscriptions pédagogiques » est **désactivé par défaut** (INJS_AUTO_INSCRIPTION_PEDAGOGIQUE = False) et verrouillé par scolarite/tests/test_frontieres_metier.py. Valider une inscription administrative ne crée aucune ligne pédagogique. La génération est un geste explicite du secrétariat.

| Action | Route |
|---|---|
| générer depuis la maquette | POST /api/scolarite/inscriptions/<pk>/pedagogie/generer/ |
| ajouter une ligne à la main | POST /api/scolarite/inscriptions/<pk>/pedagogie/ajouter/ |
| consulter, corriger | GET, PATCH /api/scolarite/pedagogie/<ligne_id>/ |

cas:: **Cas 4 — l'oubli classique.** Une inscription administrative est validée un vendredi soir. Le lundi, l'étudiant apparaît dans le groupe mais ses ECUE ne remontent pas dans le calcul de validation : le secrétariat n'a pas lancé la génération pédagogique. La correction est un appel explicite à « pedagogie/generer », qui crée une ligne par ECUE de la maquette active, en origine AUTOMATIQUE. C'est un comportement voulu, pas une panne.

## 5.3 Équivalences et dispenses

`DemandeEquivalenceDispense` suit son propre circuit : BROUILLON → SOUMISE → EN_INSTRUCTION → A_COMPLETER → AVIS_PEDAGOGIQUE → DECISION → VALIDEE → APPLIQUEE, ou REJETEE. Une décision favorable n'invente pas de note : elle bascule les inscriptions pédagogiques visées en **DISPENSEE**, statut qui existait déjà. Le calcul de validation exclut ensuite ces ECUE de la moyenne sans les compter comme manquantes.

---

# 6. Affectation en groupe

`AffectationGroupe` relie une inscription à un `Groupe` (même année, même niveau). Deux chemins :

- **unitaire** : `groupes_services.affecter_groupe`, qui vérifie la capacité `capacite_max` et la compatibilité année / formation / niveau ;
- **de masse** : `POST /api/scolarite/groupes/repartition/` (`groupes_api.repartition_automatique`), qui ignore les étudiants déjà affectés et répartit le reste.

Suivi et sorties : `GET /api/scolarite/groupes/effectifs/`, `/groupes/non-affectes/`, `/groupes/<pk>/liste/<fmt>/` (liste d'appel exportable), retrait via `/inscriptions/<pk>/retirer-groupe/`.

cas:: **Cas 5 — la capacité qui bloque.** Le groupe L1-G1 de Management du Sport est créé avec une capacité de 30. À la 31e affectation, le service refuse et propose un autre groupe : le système ne laisse pas dépasser silencieusement une capacité déclarée. Si la capacité est vide, aucune limite n'est appliquée — c'est un choix explicite de paramétrage, pas un oubli.

Sans groupe, l'étudiant n'a pas d'emploi du temps : la génération le signalera comme non planifiable au lieu de lui inventer une affectation.

---

# 7. Emploi du temps, séances et présences

## 7.1 Ce que l'étudiant voit

L'étudiant est concerné par les `AffectationCreneau` **publiées** de son groupe ou de sa formation, c'est-à-dire rattachées à un `EmploiDuTemps` au statut PUBLIE. Chaque séance peut porter une `affectation_pedagogique` : c'est ce lien qui rend la séance exploitable par les présences et par la supervision, sans déduction par le libellé.

## 7.2 Contrat de lecture externe

`GET /api/scolarite/edt/` expose le contrat `app-injs-lmd` v1.1 : `groupes`, `enseignements`, `etudiants`, `indisponibilites`, `creneaux`, `affectations`, `espaces/<id>/occupation/`, et une description de volumétrie. C'est un contrat de **lecture** ; un EDT produit par un outil externe revient par import Excel (ADR-003).

## 7.3 Le registre de séances

`SeanceRegistre` matérialise l'occurrence opérationnelle : BROUILLON → SIMULATION → EN_ATTENTE_VALIDATION → VALIDEE → PUBLIEE, avec ANNULEE en sortie. `moteur/interop_presences.py` porte les transitions, l'historisation, la clé métier, la reprogrammation, la réconciliation d'un EDT et les instantanés d'étudiants attendus. `peut_ouvrir_session_presence` interdit d'ouvrir un QR sur une séance non publiable : le registre n'invente jamais d'occurrence hors EDT.

## 7.4 Le pointage

| Action | Route | Contrôles |
|---|---|---|
| séances du jour | GET /api/presences/seances-edt/du-jour/ | périmètre de l'utilisateur |
| ouvrir le QR d'une séance | GET /api/presences/seances-edt/<pk>/qr/ | permission presences.qr.generer, peut_gerer_seance, est_seance_du_jour ; jeton actif réutilisé |
| présences d'une séance | GET, POST .../<pk>/presences/ | séance du périmètre |
| émargement (lot, unitaire) | .../<pk>/emargement/ et .../emargement/unitaire/ | idem |
| autoclôture | POST .../<pk>/autoclore/ | fenêtre de séance |
| scan étudiant | POST /api/presences/scan/ et /scan/secure/ (+ heartbeat, exit) | jeton, géofence, session |
| historique personnel | GET /api/presences/me/historique/ | compte connecté |

cas:: **Cas 6 — QR d'un autre jour.** Un enseignant tente d'ouvrir le QR de sa séance du mercredi depuis son bureau le jeudi. Le contrôle `est_seance_du_jour` refuse : un jeton de présence n'est valable que le jour de la séance. Le secret n'est jamais écrit dans le journal d'audit ni dans un export.

---

# 8. Évaluations et notes

## 8.1 Les objets

`SessionEvaluation` (NORMALE, RATTRAPAGE, RECTIFICATION) porte un périmètre explicite — année, formation, parcours, niveau, semestre, maquette — et une `regle_version` gelée au passage en calcul. `Evaluation` porte le poids dans la moyenne de l'ECUE et un statut BROUILLON, PUBLIEE, CLOTUREE, ANNULEE. Viennent ensuite les composants, les participants, les épreuves et les notes.

## 8.2 La saisie

`PUT /api/evaluations/composants/<pk>/notes/` enregistre les notes. Deux règles de sécurité :

- une note **verrouillée** n'est jamais écrasée ;
- toute modification est historisée et consultable via `GET /api/evaluations/notes/historique/`.

## 8.3 Le calcul, et ses trois refus

`evaluations/services/calcul.py` prépare un projet de résultat à partir des composants, de leurs poids et des notes. Trois invariants sont codés en dur :

- une absence académique ou une dispense rend la composante **non notée** : elle n'est jamais convertie en 0 ;
- des poids absents ne sont pas remplacés par un 50/50 : la situation est signalée, jamais inventée ;
- la règle appliquée est figée (`regle_snapshot`, `formule_version`) et l'ensemble est empreinté en SHA-256 : un résultat est reproductible et auditable.

Hiérarchie des moyennes : ECUE → UE → semestre → décision, sans saut d'étape.

---

# 9. Calcul des résultats officiels

## 9.1 La règle, pas l'approximation

`scolarite/validation_services.calculer_validation_etudiant(inscription, maquette, regle)` est le calcul qui fait foi pour la délibération. Il procède en cinq temps :

1. ne retient que les inscriptions pédagogiques PREVUE et VALIDEE (hors abandon et dispense) ;
2. par ECUE, calcule la moyenne à partir des seules notes de module **verrouillées**, normalisées sur 20 puis moyennées par module ; une ECUE sans note reste `None` et la complétude est suivie à part ;
3. par UE, pondère les ECUE par leur coefficient ; l'UE est acquise si la moyenne atteint le seuil (10/20 par défaut) ;
4. par semestre, pondère les UE par leurs crédits ; la compensation semestrielle s'applique si la règle l'autorise et si la moyenne du semestre atteint le seuil, **sauf** UE sous le seuil éliminatoire ;
5. propose une décision : EXCLUSION si une UE est sous le seuil éliminatoire, sinon ADMIS si les crédits acquis atteignent `Niveau.credits_requis` **et** que toutes les ECUE sont complètes, sinon AJOURNE.

alerte:: EXCLUSION n'est jamais ramené à AJOURNE. C'est une décision distincte, reproduite telle quelle dans les relevés et les décisions de jury.

## 9.2 Relevés et passage

- `POST /api/evaluations/releves/generer/` crée **toujours une version suivante** du relevé, jamais une réécriture ; le relevé lit les résultats publiés et les décisions de jury, ne recalcule rien, et conserve une empreinte. Une note manquante reste `null`.
- `GET /api/evaluations/resultats/passage/` est un calcul technique **en lecture seule** : il retourne INDETERMINABLE dès qu'un semestre est en attente, et ne produit aucune décision officielle.

limite:: Les tables ECUEResult, UEResult et SemesterResult sont exposées en lecture (resultats/ecue/, resultats/ue/, resultats/semestre/) et portent source MOTEUR_LMD, empreinte et verrouillage, mais aucun service applicatif ne les alimente en dehors des tests. La décision qui fait autorité reste celle du jury ; les tables de résultats sont une projection, pas une seconde source de vérité.

---

# 10. Jury, délibération et PV

## 10.1 La chaîne à neuf états

```
PREPARATION → CONTROLE → CALCUL → DELIBERATION
      → DECISION → PV_GENERE → VALIDE
      → VERROUILLE → PUBLIE
```

Un point d'entrée unique, `POST /api/jurys/sessions/<pk>/action/`, avec les actions suivantes :

| action | Effet | Garde |
|---|---|---|
| transition | état suivant de la chaîne | PV_GENERE exige au moins une décision ; DELIBERATION exige au moins une proposition |
| calcul | calcule et persiste les propositions, append-only, avec empreinte | session non verrouillée, statut PREPARATION, CONTROLE ou CALCUL |
| generer_pv | génère le PV | personnel habilité |
| verifier_decisions | vérifie que chaque étudiant concerné a une décision | — |
| publier | VERROUILLE → PUBLIE + notification Direction | PV obligatoire |

## 10.2 La décision

`POST /api/jurys/sessions/<pk>/decisions/` → `services.enregistrer_decision`. Règles :

- saisie possible seulement en DELIBERATION ou DECISION ;
- une décision divergente de la proposition du moteur est **manuelle** et exige une justification écrite ;
- unicité `(session, inscription)` : une décision par étudiant et par session ;
- décisions possibles : ADMIS, AJOURNE, ADMIS_RESERVES, EXCLUSION.

cas:: **Cas 7 — la décision manuelle.** Le moteur propose ADMIS pour un étudiant à 10,04 de moyenne. Le jury, informé d'un plagiat, saisit AJOURNE. L'écran exige alors un texte de justification ; sans lui, l'API renvoie une erreur 400 portant sur le champ justification. La décision est enregistrée avec son auteur, son horodatage et l'écart assumé par rapport à la proposition.

## 10.3 L'autorité unique

note:: `jurys.DecisionJury` est la seule décision officielle. `suiviEvaluation` et les relevés la reprennent telle quelle et ne recalculent jamais une décision. Ce point est verrouillé par backend/suiviEvaluation/test_decision_hierarchie.py.

---

# 11. Diplôme, registre et réédition

## 11.1 Le parcours de diplômation

1. `GET /api/graduation/eligibles/` liste factuellement les inscriptions VALIDEE de L3 et M2, en indiquant pour chacune si une décision de jury existe et si un diplôme est préparé ou validé. Cet écran ne décide rien.
2. `POST /api/graduation/diplomes/creer/` crée un diplôme BROUILLON. Quatre champs sont obligatoires : étudiant, année académique, formation, niveau.
3. `POST /api/graduation/diplomes/<pk>/valider/` (Direction, DFRC, Admin) vérifie deux conditions : une inscription administrative VALIDEE sur le périmètre exact, et une décision de jury rattachée à une session VERROUILLE ou PUBLIE. Ensuite : génération du PDF avec empreinte SHA-256, passage en VALIDATED, inscription au registre annuel, journal DIPLOME_VALIDE.
4. `POST .../revoquer/` exige un motif, conserve le PDF d'origine comme preuve et interdit toute réédition tant que le diplôme n'est pas réhabilité par une nouvelle décision.
5. `POST .../reedition/` produit un **nouveau** PDF horodaté et hashé, à motif obligatoire ; le PDF original reste gelé.
6. `GET /api/graduation/registres/` affiche le registre annuel ; une fois clôturé, il refuse tout ajout.
7. `GET /api/graduation/verifier/<token>/` permet une vérification publique, sans authentification, à partir de l'UUID public du diplôme ; le matricule interne n'est jamais exposé.

## 11.2 Ce que le socle refuse de diplômer

cas:: **Cas 8 — le diplôme sans jury.** Une responsable prépare un diplôme de Master 2 complet en crédits, mais la session de jury est encore en DECISION. La validation renvoie : « La session de jury doit être verrouillée ou publiée (décision officielle). » Rien n'est écrit, aucun PDF n'est généré, le registre n'est pas touché. Après verrouillage de la session, la même action aboutit.

limite:: Les conditions de diplômation ne branchent encore ni les stages ni la situation financière : les hooks sont annoncés dans le modèle, pas implémentés. Un diplôme peut donc être validé alors qu'une convention de stage n'est pas soldée.

---

# 12. Cas pratiques de bout en bout

## 12.1 Cas A — Kouassi Aya, Licence Éducation et Motricité, promotion 2026-2027

| Étape | Ce qui est fait | Trace produite |
|---|---|---|
| 1. Candidature | campagne « Concours direct — Licence Éducation et Motricité » ouverte ; dossier déposé et complet | Candidature CAND-2026-2027-0001, statut SOUMISE puis PIECES_VALIDEES, EN_ETUDE |
| 2. Sélection | épreuves écrit, physique et pratique notées ; classement calculé puis publié | NoteConcours, ClassementConcours publié |
| 3. Admission | décision ADMIS, date limite d'inscription au 30 septembre | Admission, date_decision, decide_par |
| 4. Inscription | conversion depuis l'admission, valider=true | Participant + matricule INJS26-0001, DossierEtudiant, InscriptionAdministrative VALIDEE, JournalScolarite |
| 5. Pédagogie | génération depuis la maquette active L1 S1 et S2 | une InscriptionPedagogique par ECUE, origine AUTOMATIQUE |
| 6. Groupe | affectation en L1-G1 (capacité 30) | AffectationGroupe |
| 7. EDT | l'EDT de la formation est publié ; la grille affiche les séances de L1-G1 | AffectationCreneau rattachées à leur affectation pédagogique |
| 8. Présences | QR ouvert à l'heure de la séance, émargements enregistrés | SeanceRegistre PUBLIEE, presences |
| 9. Notes | notes de composants saisies en session NORMALE ; verrouillage après contrôle | Note, historique des notes |
| 10. Résultats | calcul : moyennes ECUE, UE, semestre ; 60 crédits requis au niveau | dictionnaire de validation, crédits acquis |
| 11. Jury | session PREPARATION → … → DECISION ; proposition ADMIS confirmée | PropositionJury, DecisionJury |
| 12. PV et publication | PV généré, session VALIDE puis VERROUILLE puis PUBLIE | PVJury, NotificationJury à la Direction |
| 13. Diplôme | diplôme créé puis validé (conditions réunies) | Diplome VALIDATED, PDF + empreinte SHA-256, RegistreDiplomes, DIPLOME_VALIDE |
| 14. Après | réédition à motif (perte du document) ; vérification publique par token | Reedition append-only, page de vérification |

## 12.2 Cas B — le même parcours, avec un semestre incomplet

Le semestre 2 reste incomplet : une ECUE n'a aucune note verrouillée. Le calcul retourne `complet = false` et propose AJOURNE même si les crédits du semestre 1 suffiraient. Le jury peut décider ADMIS_RESERVES, mais il devra le justifier : la décision diverge de la proposition. Le passage de niveau, lui, retourne INDETERMINABLE (`RESULTAT_EN_ATTENTE`), et aucun diplôme n'est validable tant que la session n'est pas verrouillée avec cette décision.

## 12.3 Cas C — la réinscription, un an plus tard

L'étudiant revient en L2. Le socle ne crée **pas** automatiquement l'inscription de l'année suivante : `POST /api/scolarite/reinscriptions/` est une action explicite, qui produit une inscription de type REINSCRIPTION (ou REDOUBLEMENT, REPRISE, RÉORIENTATION, TRANSFERT), avec un nouveau matricule de la nouvelle année uniquement si un nouveau Participant est créé. Le dossier et l'historique, eux, restent les mêmes : le journal du parcours reste consultable (`/api/scolarite/etudiants/<pk>/evenements/`).

---

# 13. Ce que le système refuse de faire

| Refus | Où il est écrit |
|---|---|
| inscrire sans admission valide ou après la date limite | inscription_services.convertir_admission_en_inscription |
| inscrire avec un dossier de pièces incomplet | idem, avec décompte validées/total |
| créer deux inscriptions pour une même admission | garde d'idempotence, réponse 200 au rejeu |
| créer les inscriptions pédagogiques par effet de bord | INJS_AUTO_INSCRIPTION_PEDAGOGIQUE = False, test_frontieres_metier.py |
| valider une inscription sur une année clôturée | appliquer_transition |
| dépasser la capacité d'un groupe | groupes_services.affecter_groupe |
| ouvrir un QR hors du jour de la séance | presences/seances_edt_api.est_seance_du_jour |
| écraser une note verrouillée | evaluations.notes_saisie |
| réécrire un relevé au lieu d'en créer une version | evaluations.releves_generer |
| conclure un passage sans résultat complet | evaluations/services/passage.py |
| convertir EXCLUSION en AJOURNE | validation_services et releves |
| générer un PV sans décision, délibérer sans proposition | jurys.services.transition |
| valider un diplôme sans décision de jury verrouillée | graduation.models.verifier_conditions_validation |
| ajouter un diplôme à un registre clôturé | graduation.models.RegistreDiplomes.ajouter |

---

# 14. Où lire le code

| Sujet | Fichier |
|---|---|
| Workflow de candidature | backend/admissions/workflow.py |
| Services et routes d'admission | backend/admissions/services.py, admission_services.py, concours_services.py, urls.py |
| Conversion et matricule | backend/scolarite/inscription_services.py, matricules.py |
| Modèles scolarité | backend/scolarite/models.py |
| Inscriptions pédagogiques | backend/scolarite/pedagogie_api.py |
| Groupes | backend/scolarite/groupes_api.py, groupes_services.py |
| Calcul de validation | backend/scolarite/validation_services.py |
| Notes, relevés, passage | backend/evaluations/services/calcul.py, releves.py, passage.py, empreinte.py |
| Jury | backend/jurys/models.py, services.py, api.py, pv_services.py |
| Diplômation | backend/graduation/models.py, services.py, api.py |
| Contrat EDT externe | backend/scolarite/edt_export.py, docs/ADR/ADR-003 |
| Présences et registre | backend/presences/seances_edt_api.py, backend/edts/models_interop.py, moteur/interop_presences.py |
