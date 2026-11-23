# INJS-LMD — Inventaire des écrans, rôles et droits

Document de travail joint au manuel utilisateurs, produit **automatiquement** à partir
du code — aucune saisie manuelle. Sources croisées :

- `frontend/src/menu/arborescence.js` — source unique de la barre latérale et des routes ;
- `frontend/src/App.jsx` — routes déclarées de l'application ;
- `frontend/src/menu/autorisation.js` — règle de filtrage des entrées ;
- `backend/authentication/models.py` (`User.Role`) — 12 rôles canoniques ;
- `backend/authentication/capabilities.py` — 13 modules de capacités ;
- `backend/authentication/role_groups.py` — ensembles de rôles par module.

Généré le 2026-10-05.

| Mesure | Valeur |
|--------|--------|
| Entrées de menu | 132 |
| Sections de premier niveau | 15 |
| Rôles canoniques | 12 |
| Modules de capacités serveur | 13 |

## Comment la navigation est décidée

L'interface n'accorde jamais d'accès : elle masque une entrée dont l'utilisateur ne
détient pas le droit. Trois sources sont évaluées dans cet ordre :

1. **Volet CURP** — si le compte est gouverné, on retient ses permissions effectives
   (`/api/habilitations/mes-acces/` → `permissions_effectives`) ;
2. **Volet capacités** — sinon la projection serveur (`/api/auth/capabilities/`) ;
3. **Volet rôles** — filet de sécurité avant chargement des capacités.

Une entrée sans droit déclaré reste visible ; une section qui n'a plus aucun enfant
autorisé disparaît entièrement. **Une URL saisie à la main ne contourne pas ce filtre** :
le garde de route générique applique le même index que le menu.

## Les 12 rôles

| Code | Libellé affiché | Périmètre principal |
|------|------------------|---------------------|
| `ADMIN` | Administrateur | Accès complet à toutes les fonctions |
| `DIRECTION` | Direction | Pilotage institutionnel, finance et statistiques globales |
| `CHEF_INJS_ADMIN` | Chef INJS Admin | Accès complet à toutes les fonctions |
| `INJS_ADMIN` | INJS Admin | Accès complet à toutes les fonctions |
| `CHEF_SECRETARIAT` | Chef Secrétariat | Scolarité, utilisateurs et formations (niveau N3) |
| `SECRETARIAT` | Secrétariat | Scolarité, inscriptions, groupes, documents (niveau N2) |
| `FINANCE` | Finance | Finances étudiantes et paramétrage ; accueil redirigé vers la finance |
| `ARCHIVE` | Archiviste | Consultation, archives, graduation et statistiques |
| `ENCADRANT` | Encadrant | EDT, présences, encadrés et groupes pédagogiques |
| `SUPERVISEUR` | Superviseur | Suivi d'assiduité ; vue évaluations dédiée |
| `FORMATEUR` | Formateur | Application mobile : badgeage et saisie |
| `AUDITEUR` | Étudiant | Application mobile : badgeage et consultation |

Les rôles `FORMATEUR` et `AUDITEUR` sont **réservés à l'application mobile** : ils
n'accèdent pas à la plateforme web.

## Navigation détaillée

### Tableau de bord

Écran racine : `/dashboard`

| Écran | Chemin | Droit CURP |
|-------|--------|------------|
| Tableau de bord | `/dashboard` | — |

### Scolarité

| Écran | Chemin | Droit CURP (extrait) |
|-------|--------|----------------------|
| Tableau de bord | `/scolarite` | `scolarite.dossier_etudiant.consulter` |
| Candidatures | `/scolarite/candidatures` | `candidatures.candidature.consulter` |
| Contrôle des dossiers | `/scolarite/controle-dossiers` | `candidatures.piece.consulter`, `candidatures.piece.valider` |
| Concours & Sélection | `/scolarite/campagnes` | `candidatures.concours.consulter`, `candidatures.campagne.consulter` |
| Résultats concours | `/scolarite/resultats-concours` | `candidatures.classement.calculer`, `candidatures.classement.publier` |
| Admissions | `/scolarite/admissions` | `candidatures.eligibilite.valider`, `candidatures.candidature.valider` |
| Inscriptions | `/scolarite/inscriptions` | `scolarite.inscription_administrative.consulter` |
| Étudiants | `/participants` | `scolarite.dossier_etudiant.consulter` |
| Groupes pédagogiques | `/scolarite/groupes` | `scolarite.groupe.consulter` |
| Documents scolaires | `/scolarite/documents-scolaires` | `exports.export.generer`, `exports.export.imprimer` |
| Maquettes LMD | `/scolarite/maquettes` | `pedagogie.maquette.consulter` |
| Équivalences & dispenses | `/scolarite/equivalences` | `scolarite.equivalence.consulter` |
| Réinscriptions & transferts | `/scolarite/reinscriptions` | `scolarite.transfert.consulter`, `scolarite.reorientation.consulter` |
| Journal de scolarité | `/scolarite/journal` | `scolarite.journal_scolarite.consulter` |

### Formations

| Écran | Chemin | Droit CURP (extrait) |
|-------|--------|----------------------|
| Formations LMD | `/formations` | `pedagogie.maquette.consulter`, `referentiels.referentiel.consulter` |
| Filières | `/formations/filieres` | `referentiels.referentiel.consulter` |
| Parcours | `/formations/parcours` | `referentiels.referentiel.consulter` |
| Niveaux | `/formations/niveaux` | `referentiels.referentiel.consulter` |
| Semestres | `/formations/semestres` | `referentiels.referentiel.consulter` |
| UE / ECUE | `/formations/ue-ecue` | `pedagogie.ue.consulter`, `pedagogie.ecue.consulter` |
| Cours (LMD) | `/cours` | `pedagogie.volume_horaire.consulter` |
| Enseignants | `/formateurs` | `enseignants.enseignant.consulter` |
| Affectations pédagogiques | `/scolarite/charges` | `pedagogie.affectation_pedagogique.consulter`, `enseignants.charge.consulter` |

### GET-INJS

| Écran | Chemin | Droit CURP (extrait) |
|-------|--------|----------------------|
| Tableau des emplois du temps | `/edt` | `edt.creneau.consulter`, `edt.emploi_du_temps.generer` |
| Créer un emploi du temps | `/edt/nouveau` | `edt.emploi_du_temps.generer`, `edt.emploi_du_temps.creer` |
| Présences de séance (QR & émargement) | `/edt/presences` | `presences.emargement.consulter` |
| Cours | `/cours` | `edt.seance.creer` |
| Salles & espaces | `/edt/salles-espaces` | `patrimoine.espace.consulter` |
| Disponibilités | `/edt/disponibilites` | `enseignants.disponibilite.consulter`, `enseignants.indisponibilite.consulter` |
| Enseignants | `/formateurs` | `enseignants.enseignant.consulter` |
| Conflits & contraintes | `/edt/conflits` | `edt.conflit.resoudre`, `edt.contrainte.consulter` |
| Rattrapages & examens | `/rattrapages` | `edt.rattrapage.consulter`, `edt.examen.consulter` |
| Export / Impression | `/edt/export` | `exports.export.generer`, `exports.export.imprimer` |

### Évaluations

| Écran | Chemin | Droit CURP (extrait) |
|-------|--------|----------------------|
| Tableau de bord des évaluations | `/evaluations/tableau-de-bord` | `evaluations.questionnaire.consulter` |
| Évaluations | `/evaluations` | `evaluations.questionnaire.consulter` |
| Saisie des notes | `/evaluations/saisie` | `evaluations.note.saisir` |
| Contrôle des notes | `/evaluations/controle` | `evaluations.note.valider`, `evaluations.correction_note.consulter` |
| Délibérations | `/evaluations/deliberations` | `evaluations.decision_pedagogique.consulter` |
| Résultats | `/evaluations/resultats` | `evaluations.moyenne.calculer`, `evaluations.moyenne.publier` |
| Relevés de notes | `/evaluations/releves` | `diplomation.releve_notes.consulter` |

### Jurys

| Écran | Chemin | Droit CURP (extrait) |
|-------|--------|----------------------|
| Jurys | `/scolarite/jurys` | `jurys.session_jury.consulter` |
| Composition | `/jurys/composition` | `jurys.membre_jury.consulter` |
| Délibérations | `/jurys/deliberations` | `jurys.deliberation.consulter`, `jurys.decision.consulter` |
| PV de jury | `/jurys/pv` | `jurys.pv.generer`, `jurys.pv.signer` |
| Validation | `/jurys/validation` | `jurys.resultat.publier`, `jurys.decision.valider` |

### Diplômation

| Écran | Chemin | Droit CURP (extrait) |
|-------|--------|----------------------|
| Éligibilité | `/diplomation/eligibilite` | `diplomation.diplome.consulter` |
| Diplômes | `/scolarite/graduation` | `diplomation.diplome.consulter`, `diplomation.diplome.valider` |
| Attestations | `/diplomation/attestations` | `diplomation.attestation.consulter`, `diplomation.attestation.imprimer` |
| Certificats | `/diplomation/certificats` | `diplomation.modele_document.consulter` |
| Registres & modèles | `/diplomation/registres` | `diplomation.registre.consulter` |
| Archives | `/archives` | `diplomation.registre.consulter` |

### Finances étudiantes

| Écran | Chemin | Droit CURP (extrait) |
|-------|--------|----------------------|
| Frais de scolarité | `/finances-etudiantes/frais` | `finances_etud.tarification.consulter`, `finances_etud.echeancier.consulter` |
| Factures | `/finances-etudiantes/factures` | `finances_etud.facture.consulter` |
| Paiements | `/finances-etudiantes/paiements` | `finances_etud.paiement.saisir`, `finances_etud.paiement.valider` |
| Reçus | `/finances-etudiantes/recus` | `finances_etud.quittance.editer`, `finances_etud.paiement.valider` |
| Bourses & remboursements | `/finances-etudiantes/bourses` | `finances_etud.remboursement.consulter` |
| Situation financière | `/finances-etudiantes/situation` | `finances_etud.relance.consulter`, `finances_etud.rapprochement.consulter` |
| Vacations & encadrants | `/finance-encadrants` | `finances_form.etat_vacation.editer`, `finances_form.heures_certifiees.consulter` |
| Paramétrage finance | `/finance-parametrage` | `finances_form.parametrage.administrer` |

### Stages

| Écran | Chemin | Droit CURP (extrait) |
|-------|--------|----------------------|
| Conventions | `/stages/conventions` | `stages.convention.creer`, `stages.convention.signer` |
| Affectations & tuteurs | `/stages/affectations` | `stages.tuteur.consulter` |
| Suivi des stages | `/stages/suivi` | `stages.convention.valider`, `stages.convention.signer` |
| Évaluations | `/stages/evaluations` | `stages.evaluation_stage.consulter` |

### Personnel

| Écran | Chemin | Droit CURP (extrait) |
|-------|--------|----------------------|
| Enseignants | `/formateurs` | `enseignants.enseignant.consulter` |
| Personnel administratif | `/personnel/agents` | `rh.agent.consulter` |
| Affectations | `/personnel/affectations` | `rh.affectation_rh.consulter` |
| Charges / volumes horaires | `/scolarite/charges` | `enseignants.charge.consulter`, `pedagogie.volume_horaire.consulter` |
| Disponibilités agents | `/personnel/disponibilites` | `rh.disponibilite_agent.consulter` |
| Documents RH | `/personnel/documents` | `rh.document_rh.consulter`, `rh.document_rh.deposer` |

### Administration

| Écran | Chemin | Droit CURP (extrait) |
|-------|--------|----------------------|
| Services | `/administration/services` | — |
| Départements | `/administration/departements` | — |
| Directions | `/administration/directions` | — |
| Directions / Départements / Services | `/organisation` | `administrations.organigramme.consulter` |
| Personnel | `/personnel/agents` | `rh.agent.consulter` |
| Courrier / Documents | `/administration/courrier` | `administrations.courrier.consulter`, `administrations.document_officiel.consulter` |
| Réunions & missions | `/administration/reunions` | `administrations.reunion.consulter`, `administrations.mission.consulter` |
| Archives | `/archives` | `administrations.version_document.consulter` |
| Listes de notes archivées | `/archives/listes-notes` | `administrations.version_document.consulter` |

### Utilisateurs & Accès

| Écran | Chemin | Droit CURP (extrait) |
|-------|--------|----------------------|
| Comptes utilisateurs | `/administration/comptes` | — |
| Rôles | `/administration/comptes/roles` | — |
| Permissions | `/administration/comptes/matrice` | — |
| Départements & Services | `/administration/comptes/organisation` | — |
| Profils | `/users` | `administration.personne.consulter` |
| Dérogations | `/administration/comptes/derogations` | — |
| Délégations | `/administration/comptes/delegations` | — |
| Revue des habilitations | `/administration/comptes/revue` | — |
| File de provisionnement | `/administration/comptes/provisionnement` | — |
| Opérations en masse | `/administration/comptes/operations-masse` | — |
| Journal des accès | `/administration/comptes/journal` | — |
| Politique de sécurité | `/parametres` | `administration.politique.administrer`, `parametres.parametre.administrer` |

### Statistiques

| Écran | Chemin | Droit CURP (extrait) |
|-------|--------|----------------------|
| Tableau de bord | `/statistiques` | `statistiques.tableau_bord.consulter` |
| Candidatures | `/statistiques/candidatures` | `statistiques.indicateur.consulter` |
| Admissions | `/statistiques/admissions` | `statistiques.indicateur.consulter` |
| Inscriptions | `/statistiques/inscriptions` | `statistiques.indicateur.consulter` |
| Effectifs | `/statistiques/effectifs` | `statistiques.indicateur.consulter` |
| Résultats | `/statistiques/resultats` | `statistiques.indicateur.consulter` |
| Finances | `/statistiques/finances` | `statistiques.bilan.editer`, `statistiques.indicateur.consulter` |
| Rapports | `/statistiques/rapports` | `statistiques.rapport.generer`, `statistiques.rapport.publier` |
| Alertes & seuils | `/statistiques/alertes` | `statistiques.alerte.configurer` |

### Référentiels

| Écran | Chemin | Droit CURP (extrait) |
|-------|--------|----------------------|
| Tous les référentiels | `/referentiels` | `referentiels.referentiel.consulter` |
| Années académiques | `/referentiels/annees` | `scolarite.annee.consulter`, `referentiels.referentiel.consulter` |
| Établissements & sites | `/referentiels/etablissements` | `referentiels.referentiel.consulter` |
| Formations | `/referentiels/formations` | `referentiels.referentiel.consulter` |
| Filières | `/referentiels/filieres` | `referentiels.referentiel.consulter` |
| UE / ECUE | `/referentiels/ue-ecue` | `pedagogie.ue.consulter`, `pedagogie.ecue.consulter` |
| Niveaux | `/referentiels/niveaux` | `referentiels.referentiel.consulter` |
| Semestres | `/referentiels/semestres` | `referentiels.referentiel.consulter` |
| Types de cours | `/referentiels/types-cours` | `referentiels.referentiel.consulter` |
| Paramètres LMD | `/parametres` | `parametres.parametre.consulter` |
| Fonctionnalités (drapeaux) | `/parametres/flags` | `parametres.parametre.administrer` |
| Imports de données (Excel) | `/import` | `scolarite.dossier_etudiant.creer`, `scolarite.inscription_administrative.creer` |

### Audit & Traçabilité

| Écran | Chemin | Droit CURP (extrait) |
|-------|--------|----------------------|
| Actions utilisateurs | `/audit/actions` | `administration.journal.consulter` |
| Modifications | `/audit/modifications` | `administration.journal.consulter` |
| Événements de sécurité | `/audit/securite` | `administration.journal.consulter` |
| Intégrité de la chaîne | `/audit/integrite` | — |
| Notifications | `/administration/comptes/notifications` | — |
| Aide | `/aide` | — |

## Modules de capacités serveur

| Module | Actions |
|--------|---------|
| `web` | acceder, operationnel |
| `utilisateurs` | voir, gerer |
| `participants` | lister, creer, gerer |
| `modules` | archiver |
| `presences` | voir, agir, superviser |
| `finance` | voir, exporter, parametrer |
| `statistiques` | voir, voir_globales |
| `evaluations` | gerer_questionnaires, consulter |
| `notes` | gerer, valider_decisions |
| `scolarite` | voir, agir |
| `exports` | liste_classe |
| `dashboard` | filtrer_secretariat |
| `habilitations_admin` | gerer |

## Couverture des captures

Captures réalisées : **71** dans `docs/manual-shots/manuel-injs-lmd2026/`.
Les écarts et les écrans sans capture sont listés dans `docs/manuel/02-GAPS.md`.
