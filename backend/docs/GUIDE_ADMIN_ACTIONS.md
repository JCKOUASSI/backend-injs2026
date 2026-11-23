# Guide des actions — Admin Django INJS-LMD

Manuel d’utilisation pour réaliser **chaque action métier** depuis l’interface d’administration (`/admin/`).

**Public :** secrétariats, encadrants, administrateurs CPFAE.

---

## Avant de commencer

### Se connecter

1. Ouvrir `https://<domaine>/admin/` (local : `http://localhost:8001/admin/`).
2. Saisir **identifiant** et **mot de passe**.
3. Cliquer **Connexion**.

### Se déconnecter

1. Cliquer l’icône **logout** (en haut à droite).
2. Vous êtes redirigé vers la page de connexion.

### Naviguer dans l’admin

| Élément | Utilisation |
|---------|-------------|
| **Sidebar gauche** | Cliquer sur le titre d’une section (Navigation, Pédagogie, etc.) pour l’ouvrir/fermer |
| **Accueil admin** | Tableau de bord avec raccourcis et statistiques |
| **Dashboard web** | Ouvre l’application opérationnelle CPFAE (hors admin) |
| **Barre de recherche** (en haut) | Recherche globale dans l’admin |
| **Bouton Filtres** (sur les listes) | Ouvre le panneau de filtres à droite |
| **Ajouter …** (en haut à droite d’une liste) | Créer un nouvel enregistrement |
| **Actions** (liste déroulante + Exécuter) | Action groupée sur les lignes cochées |

### Actions groupées (procédure commune)

1. Ouvrir la liste concernée.
2. Cocher une ou plusieurs lignes (case à gauche).
3. En haut de la liste : menu **Action** → choisir l’action.
4. Cliquer **Exécuter**.
5. Lire le message de confirmation en haut de page.

### Filtrer une liste

1. Cliquer **Filtres** (bouton vert à côté de la recherche).
2. Choisir un critère dans le panneau (grade, groupe, date, statut…).
3. Le panneau se ferme ; la liste est filtrée.
4. Pour tout effacer : **Clear all filters** dans le panneau Filtres.

---

## 1. Navigation

### 1.1 Consulter le tableau de bord admin

**Menu :** Navigation → **Accueil admin**

- Voir les compteurs : Formations, Modules, Auditeurs, Pointages.
- Utiliser les cartes et boutons rapides pour accéder aux sections.

### 1.2 Ouvrir le dashboard web

**Menu :** Navigation → **Dashboard web**

Ouvre l’interface utilisateur CPFAE (gestion quotidienne des formations, badgeage, etc.).

### 1.3 Diagnostic volume horaire

**Menu :** Navigation → **Diagnostic volume horaire**

**Objectif :** comparer heures **prévues** (créneaux planifiés) et **réalisées** (séances terminées).

1. Ouvrir la page de diagnostic.
2. Filtrer par **Secrétariat** si besoin.
3. Cocher **Dépassements uniquement** pour ne voir que les modules en dépassement.
4. Consulter le tableau **Par module**.
5. Cliquer **Fiche module** ou **Séances** pour aller au détail.

---

## 2. Pédagogie

### 2.1 Formations

**Menu :** Pédagogie → **Formations**

#### Créer une formation

1. Cliquer **Ajouter formation**.
2. Renseigner le libellé de la formation.
3. **Enregistrer**.

#### Modifier / supprimer

1. Cliquer sur le nom dans la liste.
2. Modifier les champs → **Enregistrer**.
3. Pour supprimer : bouton **Supprimer** en bas de la fiche (si autorisé).

---

### 2.2 Modules

**Menu :** Pédagogie → **Modules**

#### Créer un module

1. **Ajouter module**.
2. Remplir les sections :
   - **Identification** : formation, intitulé, ordre, cycle
   - **Classification** : grade, groupe, vague (important pour le badgeage)
   - **Planification** : dates, durée prévue, statut
   - **Encadrement** : formateur, superviseur, secrétariat
   - **Localisation** : site, bâtiment, salle
3. **Enregistrer**.

#### Inscrire des auditeurs sur un module (inline)

1. Ouvrir la fiche du module.
2. Descendre à **Auditeurs inscrits**.
3. Cliquer **Ajouter une autre Auditeur inscrit**.
4. Rechercher l’auditeur → **Enregistrer**.

#### Assigner des formateurs (inline)

1. Fiche module → section **Formateurs assignés**.
2. Ajouter le formateur → **Enregistrer**.

#### Consulter les séances d’un module

1. Dans la liste des modules, colonne **Séances** → cliquer **Voir X séance(s)**.
2. Page listant toutes les séances avec état (Planifiée / En cours / Terminée).
3. **Modifier** : lien vers la fiche séance.
4. **Réactiver** : disponible si la séance est terminée.

#### Changer le statut de plusieurs modules

1. Liste **Modules** → cocher les modules.
2. Action :
   - *Marquer comme « Planifiée »*
   - *Marquer comme « En cours »*
   - *Marquer comme « Suspendue »*
   - *Marquer comme « Terminée »*
3. **Exécuter**.

#### Réactiver la dernière séance terminée d’un module

1. Liste **Modules** → colonne **Réactiver séance**.
2. Cliquer le bouton (si une séance terminée existe).
3. Confirmer : la dernière séance repasse en cours (QR régénéré si besoin).

---

### 2.3 Séances

**Menu :** Pédagogie → **Séances**

#### Créer une séance

1. **Ajouter séance de module**.
2. Choisir le **module** parent.
3. Renseigner : date, numéro, intitulé, heures début/fin prévues.
4. **Enregistrer**.

#### Modifier une séance

1. Ouvrir la fiche séance.
2. Modifier planification ou horaires d’exécution (`demarree_le`, `terminee_le` si correction manuelle).
3. **Enregistrer**.

#### Voir les pointages d’une séance

1. Liste **Séances** → colonne **Pointages** → **Voir**.
2. Liste des pointages filtrée sur cette séance.

#### Réactiver une séance terminée

**Une séance :**
1. Colonne **Réactiver** → cliquer **Réactiver**.

**Plusieurs séances :**
1. Cocher les séances terminées.
2. Action **Réactiver les séances sélectionnées** → **Exécuter**.
3. Les séances non terminées sont ignorées (message d’avertissement).

#### Forcer le badgeage de rattrapage (présents / absents)

**Objectif :** créer manuellement des pointages pour des auditeurs absents ou présents sans badge.

**Depuis une séance :**
1. Cocher **une seule** séance.
2. Action **Rattrapage badgeage (présents / absents)** → **Exécuter**.

**Depuis des auditeurs :** voir § 3.1 (action identique).

**Sur l’écran de rattrapage badgeage :**
1. Vérifier le **module** et la **séance** cible.
2. Filtrer par date ou statut de séance si besoin.
3. Pour chaque séance listée : cocher les auditeurs **présents** ou **absents** à badger.
4. Renseigner le **motif** (obligatoire en cas de forçage).
5. Options :
   - **Avec sortie** : enregistre entrée + sortie (présence complète).
   - **Ignorer les contraintes** : contourne certaines vérifications (à utiliser avec prudence).
   - **Ne pas écraser les pointages existants**.
6. Valider le formulaire.
7. Lire le récapitulatif (créés / ignorés / erreurs).

---

### 2.4 Secrétariats

**Menu :** Pédagogie → **Secrétariats**

#### Créer un secrétariat

1. **Ajouter secrétariat**.
2. Renseigner : numéro, nom, type, responsable.
3. **Enregistrer**.

#### Consulter l’activité

La liste affiche le nombre de participants, modules et formations liés.

---

## 3. Personnes

### 3.1 Auditeurs

**Menu :** Personnes → **Auditeurs**

#### Créer un auditeur

1. **Ajouter participant** (auditeur).
2. Remplir :
   - **Identification** : matricule, nom, prénom, sexe, naissance
   - **Coordonnées** : email, téléphones
   - **Affectation pédagogique** : catégorie, grade, groupe, vague, secrétariat, site, salle
3. **Enregistrer**.

#### Modifier un auditeur

1. Cliquer matricule ou nom.
2. Modifier → **Enregistrer**.

#### Forcer badgeage (rattrapage) depuis la liste auditeurs

1. Cocher un ou plusieurs auditeurs.
2. Action **Forcer badgeage (rattrapage)** → **Exécuter**.
3. Suivre l’écran décrit en § 2.3 (rattrapage badgeage).

---

### 3.2 Formateurs

**Menu :** Personnes → **Formateurs**

#### Créer un formateur

1. **Ajouter formateur**.
2. Renseigner : n° badge, nom, prénom, spécialité, contacts, organisation.
3. **Enregistrer**.

#### Modifier / consulter

1. Ouvrir la fiche depuis la liste.
2. Les assignations aux modules se font depuis la fiche **Module** (inline formateurs).

---

## 4. Présences

### 4.1 Pointages

**Menu :** Présences → **Pointages**

#### Consulter les pointages

1. Ouvrir la liste.
2. Utiliser **Filtres** : date, statut, type de personne, formation, grade, groupe…
3. Rechercher par matricule, nom, module, séance.

#### Créer un pointage manuellement

1. **Ajouter pointage**.
2. **Personne** : choisir **un seul** parmi participant, formateur ou encadrant.
3. **Séance** : rechercher par formation / grade / groupe / vague.
4. Vérifier le **contexte de la séance** affiché après enregistrement.
5. **Horodatage** : entrée, sortie (optionnel), statut.
6. **Enregistrer** → action tracée dans le journal d’audit.

#### Corriger un pointage existant

1. Ouvrir la fiche pointage.
2. Modifier `timestamp_entree`, `timestamp_sortie` ou la séance.
3. **Enregistrer** → durée et statut recalculés automatiquement.

#### Remettre un pointage « en cours »

**Une ligne :**
1. Colonne **Action** → **Remettre en cours**.
2. Confirmer la boîte de dialogue.

**Depuis la fiche :**
1. Section **Remise en cours** → bouton dédié.

**Plusieurs lignes :**
1. Cocher les pointages ayant une sortie enregistrée.
2. Action **Remettre en cours les pointages selectionnes** → **Exécuter**.

> Un pointage sans `timestamp_sortie` est déjà « en cours » — l’action n’est pas proposée.

---

### 4.2 Rattrapages inter-cohorte

**Accès :** `Présences` → **Rattrapages** (URL : `/admin/presences/rattrapage/`)

**Cas d’usage :** un auditeur rattrape un cours en assistant à une séance d’**une autre cohorte**, sans changer son groupe d’origine.

#### Créer un rattrapage

1. **Ajouter rattrapage**.
2. **Auditeur** : sélectionner l’auditeur (garde son grade/groupe d’origine).
3. **Cours manqué** (optionnel) : module et séance manquée d’origine.
4. **Séance de rattrapage** : séance d’accueil (autre cohorte, même cours).
5. **Motif** : renseigner la raison.
6. **Enregistrer** (statut initial : Planifié).

#### Générer la présence de rattrapage

1. Cocher un ou plusieurs rattrapages non annulés.
2. Action **Générer / forcer la présence (rattrapage)** → **Exécuter**.
3. Un pointage est créé ou mis à jour ; le lien apparaît dans la colonne **Présence**.

#### Annuler des rattrapages

1. Cocher les rattrapages.
2. Action **Annuler les rattrapages sélectionnés** → **Exécuter**.

---

### 4.3 Codes QR

**Menu :** Présences → **Codes QR**

#### Consulter l’état d’un QR

La liste affiche pour chaque token :
- **Actif** ou non
- **Validité** : Valide / Expiré / Séance terminée / Désactivé
- Date d’expiration, séance liée

> La génération des QR se fait en priorité depuis le **dashboard web** lors du démarrage de séance. L’admin sert surtout au contrôle et au diagnostic.

---

### 4.4 Journal d’audit

**Menu :** Présences → **Journal d'audit**

**Lecture seule** — historique des actions sensibles.

1. Filtrer par action, type de cible, formation, date.
2. Rechercher par matricule, nom, IP, acteur.
3. Ouvrir une ligne pour voir le détail (`extra`).

**Actions tracées :** créations/modifications utilisateurs, pointages forcés, rattrapages, changements de statut, liaisons appareils, etc.

---

## 5. Administration

### 5.1 Utilisateurs

**Menu :** Administration → **Utilisateurs**

#### Créer un compte

1. **Ajouter utilisateur**.
2. Identifiant + mot de passe (×2).
3. **Informations supplémentaires** :
   - **Groupes** : choisir **un seul** groupe `ROLE_*` (définit le rôle et les droits).
   - Matricule, grade, téléphone, organisation, **secrétariat** (si rôle secrétariat).
4. Cocher **Staff** pour accès admin (si nécessaire).
5. **Enregistrer**.

#### Modifier un utilisateur

1. Ouvrir la fiche.
2. Changer groupe de rôle, secrétariat, statut actif, etc.
3. **Enregistrer**.

#### Réinitialiser un mot de passe

1. Fiche utilisateur → lien **Changer le mot de passe** (en haut).
2. Saisir le nouveau mot de passe.
3. Cocher **must_change_password** pour forcer le changement à la prochaine connexion.

#### Rôles disponibles (groupes `ROLE_*`)

| Groupe | Usage typique |
|--------|----------------|
| ROLE_ADMIN / ROLE_INJS_ADMIN | Accès large, administration |
| ROLE_CHEF_SECRETARIAT / ROLE_SECRETARIAT | Gestion du secrétariat |
| ROLE_ENCADRANT | Supervision de modules assignés |
| ROLE_DIRECTION / ROLE_FINANCE | Consultation, exports |
| ROLE_FORMATEUR / ROLE_AUDITEUR | Comptes métier (app mobile / web) |

> Un utilisateur ne doit avoir **qu’un seul** groupe de rôle.

---

### 5.2 Liaisons appareils

**Menu :** Administration → **Liaisons appareils**

Gère les téléphones autorisés pour le badgeage mobile.

#### Désactiver un appareil

1. Cocher la ou les liaisons.
2. Action **Désactiver les liaisons sélectionnées** → **Exécuter**.

#### Réactiver

1. Cocher les liaisons inactives.
2. Action **Réactiver les liaisons sélectionnées** → **Exécuter**.

---

### 5.3 Paramètres finance

**Menu :** Administration → **Paramètres finance**

1. Ouvrir l’unique fiche de paramètres (ou la créer).
2. Modifier tarifs, en-têtes d’export, textes légaux selon les champs disponibles.
3. **Enregistrer**.

---

## 6. Référentiels

Ces menus servent aux **données de référence** utilisées dans les listes déroulantes (grades, vagues, sites, etc.).

| Menu | Action |
|------|--------|
| **Types de secrétariat** | Créer / activer / désactiver un type |
| **Catégories** | Gérer les catégories d’auditeurs |
| **Grades** | Gérer les grades (A4, A5, etc.) |
| **Vagues** | Gérer les vagues de promotion |
| **Cycles de formation** | Catalogue des cycles |
| **Modules catalogue** | Modules de référence + volumes horaires (inline) |
| **Sites et locaux** | Sites ; bâtiments et salles en inline sur la fiche site |

**Procédure type :**
1. Ouvrir le référentiel.
2. **Ajouter** ou cliquer une ligne existante.
3. Renseigner libellé, ordre, actif/inactif.
4. **Enregistrer**.

> Modifier un référentiel peut impacter les filtres et exports — vérifier l’orthographe et l’unicité des libellés.

---

## 7. Synthèse des actions spéciales

| Besoin | Où aller | Action |
|--------|----------|--------|
| Badger manuellement des absents | Séances ou Auditeurs | Rattrapage badgeage |
| Auditeur suit une autre cohorte | Présences → Rattrapages | Créer + Générer présence |
| Corriger une sortie accidentelle | Pointages | Remettre en cours |
| Rouvrir une séance clôturée | Séances ou Modules | Réactiver |
| Changer statut de modules | Modules | Actions groupées statut |
| Voir heures prévu/réalisé | Navigation | Diagnostic volume horaire |
| Bloquer un téléphone | Liaisons appareils | Désactiver |
| Donner accès admin | Utilisateurs | Staff + groupe ROLE_* |
| Tracer qui a fait quoi | Journal d'audit | Consultation |

---

## 8. Périmètre selon votre rôle

Vous ne voyez que les données de **votre périmètre** :

| Rôle | Ce que vous voyez |
|------|-------------------|
| Admin / CPFAE / Direction / Finance | Données globales |
| Secrétariat | Données de votre secrétariat |
| Encadrant | Modules et séances que vous supervisez |

Si une liste est vide ou une action est absente, vérifier votre **groupe de rôle** et votre **secrétariat** dans la fiche utilisateur.

---

## 9. Bonnes pratiques

1. **Toujours renseigner un motif** lors d’un badgeage ou pointage forcé.
2. **Vérifier grade / groupe / vague** sur le module avant un rattrapage badgeage.
3. **Consulter le journal d’audit** après une opération sensible.
4. **Ne pas supprimer** sans certitude — préférer désactiver (utilisateurs, liaisons appareils).
5. **Une séance à la fois** pour l’action « Rattrapage badgeage » depuis les séances.
6. Après modification d’horodatages, contrôler la **durée** et le **statut** du pointage.

---

*Guide opérationnel — interface admin INJS-LMD (juillet 2026).*
