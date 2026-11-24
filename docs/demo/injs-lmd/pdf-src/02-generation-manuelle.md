---
titre: Génération manuelle des emplois du temps
soustitre: Du référentiel horaire à la publication — gestes, contrôles et cas pratiques
surtitre: INJS-LMD 2026 · DOSSIER 2 SUR 3
objet: Décrire le processus de construction manuelle d'un emploi du temps : création du brouillon, pose et déplacement des séances, détection des conflits, workflow de statuts, publication et suites.
public: Secrétariat, chefs de secrétariat, INJS-Admin, encadrants, Direction
perimetre: backend/injs2026 — application edts (api.py, services.py, moteur/validation.py) et écrans /edt
date: 24 novembre 2026
header: Génération manuelle des emplois du temps
resume: La génération manuelle est le poste de travail historique : un agent pose les séances une par une, avec un contrôle à chaque geste. Elle produit exactement les mêmes données que la génération automatique — des AffectationCreneau — et suit le même circuit de validation et de publication. Ce dossier décrit les six gestes de l'agent, les trois niveaux de contrôle de conflits, la table des transitions et les codes de refus, chacun illustré par un cas concret.
sommaire: 1. Principes et habilitations; 2. Étape M1 — le référentiel horaire; 3. Étape M2 — créer le brouillon; 4. Étape M3 — poser une séance; 5. Étape M4 — ajuster, déplacer, neutraliser; 6. Étape M5 — les trois contrôles de conflits; 7. Étape M6 — le workflow de statuts; 8. Étape M7 — la publication; 9. Étape M8 — dépublication, versions, sorties; 10. Cas pratiques complets; 11. Ce que le mode manuel ne fait jamais; 12. Où lire le code
---

# 1. Principes et habilitations

## 1.1 Ce que produit le mode manuel

Chaque pose manuelle crée une ligne `AffectationCreneau` : qui enseigne quoi, où, sur quelles semaines. C'est la donnée opérationnelle de l'emploi du temps, celle que lisent la grille, l'export, les présences et la supervision. Le mode manuel et le mode automatique écrivent dans la **même** table et suivent le **même** workflow : la différence est seulement qui décide du placement.

## 1.2 Qui a le droit de faire quoi

Les habilitations sont vérifiées côté serveur, dans `backend/edts/permissions.py`, jamais seulement dans React.

| Capacité | Rôles autorisés |
|---|---|
| Planification : créer un brouillon, poser, déplacer, soumettre | ADMIN, CHEF_INJS_ADMIN, INJS_ADMIN, SECRETARIAT, CHEF_SECRETARIAT, DIRECTION, ENCADRANT |
| Validation, publication, dépublication, archivage encadré | DIRECTION, ADMIN |
| Lecture | tout compte authentifié |

note:: Un correctif documenté dans permissions.py mérite d'être connu : le littéral « DFRC » ne correspond à aucun rôle de User.Role. Les comptes INJS-Admin étaient donc silencieusement exclus de la planification. La liste PLANIFICATION_ROLES reprend désormais la matrice CURP et inclut INJS_ADMIN et CHEF_INJS_ADMIN.

## 1.3 Les écrans

| Écran | Route front | Usage |
|---|---|---|
| Liste et détail des EDT, grille, actions | /edt | poste de travail principal |
| Création d'un EDT | /edt/nouveau | choix de l'année, de la population, des semaines |
| Nouvelle affectation | /edt/:edtId/affectation/nouveau | pose d'une séance |
| Conflits | /edt/conflits | file des conflits actifs et résolution |
| Génération annuelle | /edt/generation-annuelle | voir dossier 3 |

---

# 2. Étape M1 — le référentiel horaire

## 2.1 Un créneau type est un repère d'agenda

`CreneauTemplate` est identifié par le triplet `(jour, heure_debut, heure_fin)`, normalisé à la minute. Cette normalisation n'est pas cosmétique : sans elle, deux exécutions d'un même plan de création produiraient des créneaux différents à cause des microsecondes de `datetime.now()`. Avec elle, la même demande reconduit le même créneau.

| Action | Route | Comportement |
|---|---|---|
| lister | GET /api/edts/creneaux-types/ | ordre jour puis heure |
| créer | POST /api/edts/creneaux-types/ | 409 si le triplet existe déjà |
| lire, modifier, supprimer | GET, PATCH, DELETE /api/edts/creneaux-types/<pk>/ | contrôle d'existence |
| conformité au canevas officiel | comparaison exposée par l'API et commande manage.py verifier_canevas | grille_officielle, chevauchements, comparer_canevas |

## 2.2 Le canevas officiel

Le référentiel métier décrit 24 créneaux : six jours et quatre plages de deux heures.

| Plage | Horaire | Remarque |
|---|---|---|
| 1 | 07:30 – 09:30 | — |
| 2 | 09:45 – 11:45 | 15 minutes entre les plages 1 et 2 |
| 3 | 13:30 – 15:30 | pause méridienne de 1 h 45, déduite du référentiel |
| 4 | 15:45 – 17:45 | 15 minutes entre les plages 3 et 4 |

cas:: **Cas 1 — le doublon de créneau.** Un agent crée « Mardi 07:30-09:30 ». Il retente la même saisie persuadé que le premier enregistrement a échoué. L'API renvoie 409 : le triplet existe déjà. Sans ce refus, deux créneaux identiques auraient coexisté et les contrôles de chevauchement auraient raté la collision horaire.

## 2.3 Sans créneau type, rien n'est possible

Si le référentiel horaire est vide, aucune pose n'est possible et la génération échoue avec le motif `CANEVAS_HORAIRE_VIDE`. C'est la première cause d'échec à vérifier avant toute démonstration.

---

# 3. Étape M2 — créer le brouillon

## 3.1 L'appel

`POST /api/edts/emplois/` attend :

| Champ | Obligatoire | Valeur par défaut | Remarque |
|---|---|---|---|
| annee_academique_id | oui | — | doit exister |
| population_type | non | FORMATION | FORMATION, GROUPE, ENSEIGNANT ou SALLE |
| population_id | oui | — | résolu en libellé par _label_population |
| titre | non | vide | affichage et recherche |
| semaine_debut | non | 1 | borne de planification |
| semaine_fin | non | 36 | doit être ≥ semaine_debut |
| rentree | non | vide | date de rentrée pédagogique |

## 3.2 Deux refus à connaître

- **409 — doublon de périmètre** : un EDT existe déjà pour le même couple (année, population_type, population_id). Le message invite à ouvrir l'existant plutôt qu'à en créer un second. C'est ce qui garantit qu'il n'y a jamais deux EDT concurrents pour un même groupe.
- **400 — bornes incohérentes** : la semaine de fin doit être supérieure ou égale à la semaine de début.

## 3.3 Ce qui est écrit

L'EDT est créé au statut **BROUILLON**, avec `cree_par` renseigné, et une ligne de journal `EDT_CREE` portant la population cible. La grille est vide : c'est un dossier de travail, pas encore un emploi du temps.

cas:: **Cas 2 — l'EDT du L1-G1.** Le secrétariat crée un EDT pour l'année 2026-2027, population GROUPE, identifiant du groupe L1-G1 de Management du Sport, semaines 1 à 16, rentrée le 5 octobre. L'EDT existe en BROUILLON. Un second agent tente de créer le même : 409, il est renvoyé vers l'existant. Les deux agents travaillent désormais dans le même dossier, ce qui évite les doublons de séances.

---

# 4. Étape M3 — poser une séance

## 4.1 L'appel

`POST /api/edts/affectations/` :

| Champ | Obligatoire | Remarque |
|---|---|---|
| emploi_du_temps_id | oui | l'EDT doit exister et être modifiable |
| creneau_template_id | oui | créneau du référentiel |
| semaine_debut, semaine_fin | oui, fin ≥ début | fin par défaut = début |
| nature | non | COURS, TD, TP, EVALUATION, REMPLACEMENT, AUTRE |
| salle_nom | non | chaîne libre, contrôlée en chevauchement |
| formation_id, groupe_id | non | cibles vérifiées en existence |
| enseignant_id ou formateur_id | non | si formateur, le nom d'enseignant est dérivé automatiquement |
| intitule, commentaire | non | affichage et mémoire du geste |

## 4.2 Le contrôle à la pose

Après écriture, `services.verifier_affectation(a)` renvoie des **avertissements non bloquants** : chevauchement de semaines **et** d'horaires avec d'autres séances actives partageant le même enseignant, le même formateur, le même groupe ou la même salle. La pose est acceptée, mais l'agent est prévenu.

note:: Ce choix est délibéré. Un poste de travail manuel doit pouvoir enregistrer une situation imparfaite puis la corriger ; en revanche, rien ne doit passer silencieusement. L'avertissement est retourné dans le champ avertissements_conflits et le nombre d'avertissements est journalisé.

## 4.3 Ce que la séance emporte

Chaque pose est journalisée (`EDT_AFFECTATION_MODIFIEE`, opération « affectation créée », identifiant d'affectation, nombre d'avertissements). La séance peut être rattachée à une affectation pédagogique : c'est ce lien qui la rend exploitable par les présences QR et la supervision.

cas:: **Cas 3 — la salle déjà prise.** Un agent pose « Mercredi 09:45-11:45 » en salle Gymnase pour L1-G1 alors que L2-G2 y est déjà placé sur les semaines 3 à 10. La pose est acceptée, mais la réponse contient un avertissement nommant les semaines en chevauchement. L'agent corrige immédiatement vers le Terrain, puis relance la détection de conflits : zéro conflit actif.

---

# 5. Étape M4 — ajuster, déplacer, neutraliser

## 5.1 Trois façons de déplacer

| Voie | Route | Comportement en cas de conflit |
|---|---|---|
| déplacement historique | POST /api/edts/affectations/<pk>/deplacer/ | 409 avec la liste des conflits et un conseil ; accepté seulement avec forcer=true **et** un motif |
| déplacement LMD | POST /api/edts/lmd/items/<pk>/move/ | revalidation C1 → C10 ; 409 **sans aucune écriture** |
| modification de champs | PUT, PATCH /api/edts/affectations/<pk>/ | avertissements retournés après écriture |

Le déplacement LMD est le plus strict : les dix contraintes du moteur sont rejouées sur la séance avant écriture. Un déplacement qui violerait la disponibilité d'un enseignant ou la compatibilité d'une salle est refusé, pas seulement signalé.

## 5.2 Le forçage motivé

Sur la voie historique, `forcer=true` sans motif est un **400** : la traçabilité est obligatoire. Avec un motif, le déplacement est accepté et le journal conserve le drapeau `force`, le motif et la liste des conflits assumés.

cas:: **Cas 4 — le forçage tracé.** La Direction demande de maintenir un cours le vendredi 07:30 malgré l'indisponibilité déclarée de l'enseignant, ce jour-là, pour un rattrapage exceptionnel. L'agent déplace avec forcer=true et le motif « Rattrapage exceptionnel demandé par la Direction — accord écrit du 12/10/2026 ». La séance est en place et le journal porte le motif : dans six mois, la décision sera encore explicable.

## 5.3 Annuler sans effacer

En LMD, `POST /api/edts/lmd/items/<pk>/cancel/` réalise une **désactivation logique motivée** : la séance reste en base, marquée inactive, avec son motif. `reactiver` la remet en service. On ne supprime pas une trace de séance pour corriger une grille.

## 5.4 Le gel d'édition

`_peut_editer` protège les statuts avancés :

| Situation | Effet pour un rôle de planification |
|---|---|
| EDT VALIDE, PUBLIE ou ARCHIVE | 409 : édition verrouillée, un rôle Direction doit dépublier |
| EDT EN_VALIDATION | 409 : gelé également, mais l’agent peut retirer la soumission |
| EDT avec séances portant une clé v2 | 409 QR_V2_CHEMIN_HERITE_REFUSE, **y compris pour la Direction** |

alerte:: La dernière ligne est un mur volontaire. Dès qu'une année porte des occurrences v2, le chemin historique ne sait plus maintenir la date, la clé métier ni le registre QR. Toute écriture est donc refusée et renvoyée vers le service transactionnel v2.

---

# 6. Étape M5 — les trois contrôles de conflits

## 6.1 Détection persistée, par EDT

`POST /api/edts/emplois/<pk>/conflits/` appelle `services.detecter_conflits` :

1. lit les affectations **actives** de l'EDT ;
2. les compare entre elles **et** avec les affectations des autres EDT qui partagent un enseignant, un formateur, un groupe ou une salle ;
3. crée ou réactive une ligne `ConflitCreneau` par paire en conflit ;
4. **clôture** les conflits automatiques qui ne se vérifient plus ;
5. ne touche jamais à un signalement `MANUEL` ouvert par un agent ;
6. retourne des statistiques : affectations analysées, conflits détectés, conflits clôturés, horodatage.

La vue est garde-fousée : elle ne renvoie jamais 500, même sur SQLite.

## 6.2 Les types de conflits

| Code | Signification |
|---|---|
| HORAIRE_ENSEIGNANT | chevauchement enseignant |
| HORAIRE_GROUPETUDIANT | chevauchement groupe / étudiant |
| HORAIRE_SALLE | chevauchement salle |
| HORAIRE_MODULE | chevauchement module |
| CAPACITE | capacité de salle insuffisante |
| COMPATIBILITE_SALLE | salle incompatible avec le type d'enseignement |
| HORS_CALENDRIER | séance hors période autorisée |
| DISPONIBILITE | indisponibilité enseignant ou salle |
| MANUEL | signalé à la main par un agent |

## 6.3 Le contrôle croisé inter-EDT

`services.conflits_inter_edt(edt_ids)` compare plusieurs EDT sur leur fenêtre commune et retourne un statut : OK, CONFLITS, DONNEE_INCONNUE ou INTERDIT, avec le détail des paires (type, description, EDT A, EDT B, séances concernées, jour, semaine, horaires). C'est une **lecture** : aucun éditeur, aucune suppression. Elle sert à vérifier un lot avant publication.

## 6.4 La validation moteur d'un EDT persisté

`POST /api/edts/lmd/<pk>/validate/` appelle `validation.valider_emploi_du_temps` : un EDT existant n'est **pas** jugé plus permissivement qu'un plan fraîchement généré. Sont vérifiés : C1/C2/C3 entre séances persistées, cohérence des semaines (C9), salle indisponible, absence d'affectation pédagogique (avertissement C8), volume (C10). Le statut passe à VALIDE seulement si le rapport est valide ; sinon il retombe en EN_VALIDATION et `valide_le` / `valide_par` sont remis à zéro.

## 6.5 Traiter et résoudre

| Action | Route |
|---|---|
| file des conflits | GET /api/edts/conflits/?emploi_du_temps_id=&actif=true |
| signaler un conflit manuel | POST /api/edts/conflits/ |
| résoudre (motif) | POST /api/edts/conflits/<pk>/resoudre/ |

La résolution exige un motif, ajouté à la description du conflit, et journalise `EDT_CONFLIT_RESOLU`. Un conflit déjà clôturé renvoie 409.

cas:: **Cas 5 — la boucle complète.** L'EDT du L2-G2 et celui du L1-G1 partagent l'enseignant d'Anatomie. Un agent place L1-G1 sur le créneau déjà utilisé par L2-G2. Il lance la détection : un conflit HORAIRE_ENSEIGNANT apparaît, avec les deux identifiants de séance. Il déplace la séance sur un créneau libre, relance la détection : détectés 0, clôturés 1. La ligne de conflit reste en base, inactive, avec son horodatage de recalcul : l'historique de la correction est conservé.

---

# 7. Étape M6 — le workflow de statuts

## 7.1 La table des transitions

| Depuis | Vers | Rôle requis |
|---|---|---|
| BROUILLON | EN_VALIDATION | planification |
| EN_VALIDATION | VALIDE | validation |
| EN_VALIDATION | BROUILLON | planification (retrait de soumission) |
| VALIDE | PUBLIE | validation |
| VALIDE | EN_VALIDATION | validation (renvoi en examen) |
| PUBLIE | BROUILLON | validation (dépublication) |
| BROUILLON, EN_VALIDATION | ARCHIVE | planification |
| VALIDE, PUBLIE | ARCHIVE | validation |
| ARCHIVE | BROUILLON | validation (réouverture encadrée) |

Toute autre combinaison renvoie **409** avec un message qui rappelle la chaîne attendue : BROUILLON → EN_VALIDATION → VALIDE → PUBLIE.

## 7.2 Les deux gardes de soumission

- un EDT contenant des **conflits actifs** ne peut pas être soumis : 409 avec le décompte et la consigne de résoudre ou de relancer la détection ;
- un EDT **vide** est refusé : le statut est remis à BROUILLON avant la réponse 409.

## 7.3 Les routes et le journal

`POST /emplois/<pk>/soumettre/`, `/valider/` (avec `statut: VALIDE` ou `PUBLIE`), `/publier/`, `/depublier/`, `/archiver/`. Chaque transition écrit une action de journal : EDT_SOUMIS, EDT_VALIDE, EDT_PUBLIE, EDT_DEPUBLIE, EDT_ARCHIVE, avec l'ancien et le nouveau statut.

cas:: **Cas 6 — la soumission bloquée.** Un agent soumet l'EDT du L3-G1 un vendredi. Refus : « Soumission bloquée : 2 conflit(s) actif(s) ». Il ouvre /edt/conflits, corrige une salle, résout l'autre conflit avec le motif « double réservation annulée par la scolarité », relance la détection, puis soumet. La Direction valide le lundi. Le lundi soir, la Direction publie.

---

# 8. Étape M7 — la publication

## 8.1 Deux chemins, de rigueur croissante

| Chemin | Route | Contenu |
|---|---|---|
| historique | POST /api/edts/emplois/<pk>/publier/ | simple transition VALIDE → PUBLIE, réservée Direction/Admin, refusée si séances v2 |
| LMD | POST /api/edts/lmd/<pk>/publish/ | publication contrôlée par le moteur, avec verrou et contrôle de complétude |

## 8.2 L'ordre des refus du chemin LMD

`publier_emploi_du_temps` prend un verrou (`select_for_update`) puis vérifie, dans cet ordre :

1. VERSION_EDT_MODIFIEE — la version transmise n'est plus la version courante ;
2. EDT_DEJA_PUBLIE ;
3. STATUT_EDT_INVALIDE — seul un EDT VALIDE est publiable ;
4. QR_V2_NON_PUBLIABLE — même avec force ;
5. VALIDATION_BLOQUANTE — violations C1 à C10, contournables par force mais tracées ;
6. PLAN_INCOMPLET — des séances attendues manquent ;
7. AUCUNE_AFFECTATION_A_PUBLIER.

note:: Sur la route LMD, l'option force n'est pas exposée : aucune publication forcée n'est possible par ce chemin. Les besoins attendus sont recalculés depuis le périmètre déclaré de l'EDT, jamais depuis la requête — sans quoi il suffirait d'omettre des groupes pour réduire artificiellement le nombre de séances attendues et forcer la publication d'un plan partiel.

alerte:: Le contrôle de complétude n'est appliqué que si le périmètre de l'EDT est dérivable sans ambiguïté. La réponse indique explicitement si le contrôle a pu être appliqué, et pourquoi il ne l'a pas été : un « publié » sans contrôle n'est pas présenté comme équivalent à un « publié » contrôlé.

## 8.3 Ce que la publication déclenche

Le statut passe à **PUBLIE**, `publie_le` et `publie_par` sont renseignés, et les séances deviennent exploitables par les présences : le registre de séances peut être constitué, les QR ouverts le jour de la séance.

cas:: **Cas 7 — le plan incomplet.** L'EDT du M1 a dix séances attendues et huit placées. La Direction tente de publier depuis /edt : la route LMD répond PLAN_INCOMPLET avec le décompte. Le statut reste VALIDE. Deux séances sont ajoutées à la main, la validation est relancée, puis la publication aboutit. La route historique, elle, aurait laissé passer : c'est précisément l'écart que le chemin LMD comble.

---

# 9. Étape M8 — dépublication, versions, sorties

## 9.1 Dépublication et archivage

PUBLIE → BROUILLON (Direction) rend l'EDT éditable pour corriger. L'archivage mène à ARCHIVE, et la réouverture ARCHIVE → BROUILLON reste encadrée. Aucune de ces transitions n'efface de séance.

## 9.2 Versionnage

`EmploiDuTemps` porte `version` et `motif_modification`. L'unicité est `(année, population_type, population_id, version)` : plusieurs versions d'un même périmètre coexistent. Une nouvelle version se crée **par clonage**, jamais par écrasement. `empreinte` conserve le SHA-256 des paramètres de génération, ce qui garantit qu'une relance strictement identique ne duplique rien.

## 9.3 Les sorties

| Sortie | Route | Remarque |
|---|---|---|
| grille hebdomadaire | GET /api/edts/emplois/<pk>/grille/ | services.grille_hebdomadaire, jour par jour |
| export CSV | GET /api/edts/emplois/<pk>/export.csv/ | BOM UTF-8 pour Excel |
| export PDF / XLSX | GET /api/edts/lmd/<pk>/export.pdf/ et /export.xlsx/ | mise en page institutionnelle |
| grille LMD | GET /api/edts/lmd/<pk>/grille/ | même source de données |
| audit, résultat | GET /api/edts/lmd/<pk>/audit/ et /result/ | couverture et violations |
| EDT consultables | GET /api/edts/publics/ | statuts VALIDE et PUBLIE |
| filtre par rôle | GET /api/edts/emplois/?selon_role=1 | un enseignant ne voit que ses EDT |

---

# 10. Cas pratiques complets

## 10.1 Cas A — construire l'emploi du temps du L1-G1 en une matinée

| Heure | Geste | Résultat |
|---|---|---|
| 08:10 | vérifier le référentiel : 24 créneaux types conformes au canevas officiel | comparaison sans écart |
| 08:20 | créer l'EDT GROUPE L1-G1, semaines 1 à 16, rentrée 05/10/2026 | BROUILLON, journal EDT_CREE |
| 08:35 | poser Anatomie CM, lundi 07:30-09:30, semaines 1 à 12, salle Amphithéâtre | avertissement 0 |
| 08:45 | poser Pratique sportive TP, mardi 09:45-11:45, semaines 1 à 12, Gymnase | avertissement 0 |
| 09:00 | poser Psychologie du sport TD, mercredi 09:45-11:45, semaines 3 à 12 | **1 avertissement** : chevauchement de salle avec L2-G2 |
| 09:05 | corriger la salle vers Salle 4 | avertissement 0 après vérification |
| 09:30 | détecter les conflits | 0 détecté, 0 clôturé |
| 09:40 | soumettre | EN_VALIDATION, EDT_SOUMIS |
| 11:00 | la Direction valide | VALIDE, valide_par et valide_le renseignés |
| 11:15 | la Direction publie via le chemin LMD | PUBLIE, contrôle de complétude indiqué dans la réponse |
| 11:20 | exporter CSV pour la liste d'appel et PDF pour affichage | fichiers produits |

## 10.2 Cas B — la correction après publication

Une salle est indisponible pour travaux. La Direction dépublie (PUBLIE → BROUILLON), l'agent déplace deux séances vers le Terrain, relance la détection (0 conflit), resoumet, la Direction revalide et republie. Rien n'a été supprimé : le journal contient la dépublication, les deux déplacements et la nouvelle publication, et le motif de forçage éventuel s'il y en a eu un.

## 10.3 Cas C — le refus de réécrire une année v2

Un agent tente de modifier une séance d'un EDT dont l'année est déjà passée en occurrences v2. Réponse 409 `QR_V2_CHEMIN_HERITE_REFUSE`. Il ne s'agit pas d'un bug ni d'un manque de droits : le chemin historique ne sait pas maintenir la date de l'occurrence, sa clé métier et son registre QR. La correction doit passer par le service transactionnel v2.

---

# 11. Ce que le mode manuel ne fait jamais

| Interdit | Garantie |
|---|---|
| écrire dans un EDT VALIDE, PUBLIE ou ARCHIVE | _peut_editer, 409 explicite |
| écrire dans une année à occurrences v2 | 409 QR_V2_CHEMIN_HERITE_REFUSE, y compris Direction |
| soumettre un EDT avec conflits actifs | garde de soumission, 409 |
| soumettre un EDT vide | statut remis à BROUILLON puis 409 |
| déplacer avec conflit sans motif | 400, le forçage exige un motif |
| effacer une séance | cancel : désactivation logique motivée, réactivable |
| publier un plan incomplet par le chemin LMD | PLAN_INCOMPLET, aucun effet de bord |
| publier en forçant par le chemin LMD | option non exposée |
| auto-publier après génération | la publication est une action Direction distincte |
| perdre l'historique d'une version | clonage, motif_modification, empreinte |

---

# 12. Où lire le code

| Sujet | Fichier |
|---|---|
| API EDT manuel, transitions, gel d'édition | backend/edts/api.py |
| Permissions de planification et de validation | backend/edts/permissions.py |
| Modèles EDT, séances, conflits, créneaux | backend/edts/models.py |
| Détection de conflits, vérification, grille | backend/edts/services.py |
| Validation par le moteur | backend/edts/moteur/validation.py |
| Publication contrôlée | backend/edts/moteur/publication.py |
| Déplacement et annulation LMD | backend/edts/api_lmd.py |
| Canevas officiel | backend/edts/moteur/canevas_officiel.py |
| Écrans | frontend/src/pages/Edts.jsx, EdtNew.jsx, AffectationNew.jsx |
