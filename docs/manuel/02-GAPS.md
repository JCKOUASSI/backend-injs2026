# INJS-LMD — Écarts documentaires et limites de la rédaction

Ce document accompagne le manuel utilisateurs. Il signale, de manière
transparente, ce qui n'a **pas** pu être vérifié ou ce qui présente un écart
entre le code et l'interface. Conformément au principe de transparence, rien n'a
été inventé pour combler ces manques.

## 1. Périmètre couvert et méthode

- **Source** : `docs/manuel/ManuelUtilisateurs-INJS-LMD2026.md`.
- **Captures** : 121 écrans parcourus sur l'application réelle, 29 insérés au
  manuel sous forme de figures numérotées.
- **Règles appliquées** : aucune donnée réelle, aucun mot de passe, aucun secret ;
  toute affirmation non vérifiable est déclarée ici plutôt qu'inventée.

## 2. Écrans capturés mais non illustrés dans le manuel

Les écrans suivants ont été capturés avec succès (`docs/manual-shots/`) mais ne
sont pas insérés comme figures numérotées, le texte du manuel les décrivant dans
un tableau plutôt qu'à l'image :

| Domaine | Écrans |
|---------|--------|
| Scolarité | Équivalences & dispenses, Réinscriptions & transferts, Journal de scolarité, Contrôle des dossiers, Documents scolaires |
| Formations | Filières, Parcours, Niveaux, Semestres, UE/ECUE, Modules, Enseignants, Affectations |
| GET-INJS | Créer un emploi du temps, Salles & espaces, Disponibilités, Conflits, Rattrapages, Export |
| Évaluations | Contrôle des notes, Délibérations, Résultats, Relevés |
| Jurys | Sessions, Composition, PV, Validation |
| Diplômation | Attestations, Certificats, Registres, Archives |
| Finances | Frais, Factures, Paiements, Reçus, Bourses, Ajustements, Paramétrage |
| Stages | Organismes, Affectations, Suivi, Évaluations |
| Personnel | Affectations, Disponibilités, Documents |
| Administration | Services, Départements, Directions, Secrétariats, Courrier, Réunions, Listes de notes, Cahiers d'appel |
| Utilisateurs | Rôles, Profils, Dérogations, Délégations, Revue, Provisionnement, Opérations en masse, Notifications, Journal, Paramètres |
| Statistiques | Candidatures, Admissions, Inscriptions, Effectifs, Résultats, Finances, Alertes |
| Référentiels | Années, Établissements, Formations, Filières, UE/ECUE, Niveaux, Semestres, Types de cours |
| Audit | Modifications, Sécurité, Intégrité |

> Ces captures restent disponibles et peuvent être insérées dans une version
> ultérieure du manuel.

## 3. Limites constatées

### 3.1 Compte de démonstration `dfrc`

Le compte de démonstration `dfrc` mentionné dans la documentation d'exécution
**n'a pas pu être utilisé** : la tentative de connexion a été refusée par
l'application. Conformément aux règles de la mission, **aucune modification n'a été
apportée** à ce compte (ni mot de passe, ni rôle, ni statut).

**Conséquence** : les écrans financiers ont été capturés avec le compte
administrateur, qui dispose des droits financiers. Le manuel ne dépend donc d'aucun
accès `dfrc`.

### 3.2 Données de démonstration

Les captures utilisent la base de démonstration `injs_lmd_current`. Les volumes
visibles (quelques étudiants, une campagne de concours) ne sont pas représentatifs
d'une année réelle. Les noms de personnes figurant dans les captures ont été
neutralisés par substitution.

### 3.3 Comptes visibles dans l'interface

L'écran de connexion affiche par défaut un encadré « Comptes démo » qui contient
des couples identifiant / mot de passe. La capture correspondante a été
**neutralisée** avant insertion (mots de passe remplacés par des points). Le
comportement de l'application lui-même n'a pas été modifié.

### 3.4 Écrans non capturés

Aucun écran du périmètre n'a été laissé sans capture technique : les 121 parcours
réalisés ont tous abouti. Les éventuels écrans sans **illustration numérotée**
figurent au §2 ci-dessus et ne relèvent pas d'un défaut de couverture.

### 3.5 Horloge serveur

Le décalage horaire éventuel de l'EDT (mentionné au chapitre 21) n'a pas pu être
reproduit : le serveur était à l'heure pendant la campagne.

### 3.6 Application mobile

Le module **badgeage mobile** (chapitre 8) est décrit à partir du code et de
l'interface web (affichage et QR). L'application mobile elle-même n'a pas été
pilôtée pendant cette mission ; ses écrans propres ne sont pas capturés.

## 4. Ce qui reste à faire pour une version complète

1. Insérer les captures listées au §2 comme figures numérotées (version 2.0).
2. Produire les captures propres à l'application mobile (badgeage, historique).
3. Vérifier le comportement du compte `dfrc` avec l'administrateur.
4. Actualiser le manuel à chaque évolution de libellé d'écran.

---

*Ce document fait partie des livrables du manuel utilisateurs INJS-LMD2026.*