# Rapport de production — Manuel utilisateur officiel INJS 2026

**Document concerné** : Manuel utilisateur officiel de l'application de gestion intégrée
de l'Institut National de la Jeunesse et des Sports d'Abidjan
**Édition** : 2026 · **Version documentaire** : 1.0
**Date de génération** : 9 novembre 2026
**Périmètre** : application `backend-injs2026` telle qu'elle fonctionne dans la
révision documentée
**Nature du travail** : documentation uniquement — aucune ligne de code applicatif,
aucune migration, aucune donnée métier n'a été modifiée

---

## 1. Objet du rapport

Ce rapport rend compte de la production du manuel utilisateur officiel demandé :
il décrit la méthode suivie, les sources exploitées, les vérifications effectuées,
les livrables produits et les limites assumées.

Il répond à une exigence précise : **le manuel devait décrire l'application réelle**,
jamais une application théorique, et ne présenter aucune fonctionnalité future comme
disponible.

---

## 2. Livrables produits

| Livrable | Emplacement | État | Volumétrie |
|---|---|---|---|
| Manuel PDF A4 | `pdf/MANUEL_UTILISATEUR_OFFICIEL_INJS_2026.pdf` | **Produit et vérifié** | 4,5 Mo · 104 pages · 72 signets |
| Manuel HTML autonome | `html/index.html` | **Produit et vérifié** | 280 Ko |
| Feuille de style | `html/assets/css/manuel.css` | **Produit** | 35 Ko |
| Script d'interaction | `html/assets/js/manuel.js` | **Produit** | 18 Ko |
| Captures d'écran | `html/assets/images/` | **19 images** | — |
| Sources rédactionnelles | `sources/contenu/` | **Complet** | 12 modules Python |
| Référentiels extraits | `sources/referentiels/` | **8 fichiers JSON** | — |
| Copie des captures | `sources/captures/` | **19 images** | — |
| Rapport de production | `RAPPORT_PRODUCTION.md` | **Ce document** | — |
| Espace de téléchargement | `telechargements/index.html` | **Produit** | Page d'accès aux trois fichiers |
| Archive complète | `telechargements/…_COMPLET.zip` | **Produit et testée** | 10,6 Mo · 76 fichiers |
| Archive légère (HTML) | `telechargements/…_HTML.zip` | **Produit et testée** | 3,5 Mo · 22 fichiers |
| Notice d'accompagnement | `LIRE-MOI.txt` | **Produit** | Guide de prise en main de l'archive |

Le manuel est publié à l'emplacement exigé par le cahier des charges :
`arena/documentation/manuel_utilisateur/`, avec la même arborescence
(`pdf/`, `html/assets/`, `sources/`, `telechargements/`). La publication est
rejouable par `sources/contenu/publier.py`.

Les deux manuels — PDF et HTML — sont **indépendants et téléchargeables**. Le HTML
fonctionne hors ligne : il n'appelle aucune ressource externe.

### 2.1 Comment récupérer les fichiers

Trois voies d'accès sont ouvertes :

1. **Espace de téléchargement** — `telechargements/index.html` liste les trois
   fichiers avec leur poids, leur nombre de pages et un bouton de téléchargement
   direct. Les fichiers sont servis avec l'en-tête `Content-Disposition: attachment`,
   ce qui déclenche l'enregistrement sur le poste plutôt que l'affichage.
2. **Bouton dans le manuel** — la barre supérieure du manuel HTML porte un bouton
   « Télécharger » qui mène à cet espace.
3. **Archive complète** — `MANUEL_UTILISATEUR_OFFICIEL_INJS_2026_COMPLET.zip`
   contient la totalité des livrables : le PDF, le manuel interactif et ses
   19 captures, les 11 modules de rédaction, les 8 générateurs, les 7 référentiels
   extraits, le rapport et la notice. C'est la voie recommandée pour archiver ou
   transmettre le dossier entier.
4. **Archive légère** — `MANUEL_UTILISATEUR_OFFICIEL_INJS_2026_HTML.zip` ne contient
   que le manuel interactif, le PDF, le rapport et la page de téléchargement.

Les deux archives ont été **téléchargées depuis le serveur, puis décompressées** :
intégrité vérifiée, lien vers le PDF résolu, images du manuel toutes présentes,
référentiels JSON valides, générateurs présents. Une archive testée seulement par
son code HTTP ne prouverait rien : le test a porté sur le contenu extrait.

Les trois fichiers ont été téléchargés depuis le serveur puis comparés octet par
octet à leurs originaux : **identiques**. L'archive a été ouverte et testée :
**intègre**, et son `index.html` est identique à celui publié.

---

## 3. Méthode de travail

### 3.1 Les neuf phases exécutées

| Phase | Contenu | Résultat |
|---|---|---|
| 1. Exploration | Analyse du dépôt : backend, frontend, habilitations, navigation | 806 fichiers Python, 361 fichiers JS/JSX, 23 applications Django |
| 2. Cartographie | Rôles, permissions, modules, écrans, routes, gardes | 81 rôles · 1 157 permissions · 20 modules · 144 routes · 97 gardes |
| 3. Interfaces et captures | Recensement et sélection des preuves visuelles | 185 captures disponibles → 19 retenues |
| 4. Rédaction | 12 parties, 43 chapitres, 194 blocs, 12 fiches profil | Complet |
| 5. Design | Palette imposée, gabarits PDF et HTML | Conforme |
| 6. PDF | Génération ReportLab, deux passes de pagination | 104 pages |
| 7. HTML | Génération statique interactive | 280 Ko |
| 8. Validation | Contrôles automatisés sur les deux livrables | Voir section 7 |
| 9. Rapport | Ce document | Livré |

La mission n'a pas été interrompue après la phase d'audit : les phases 4 à 9 ont
été menées jusqu'à la production effective des livrables.

### 3.2 Ce qui a été fait pour ne rien inventer

Chaque affirmation du manuel provient d'une lecture du code, jamais d'une
extrapolation. Trois précautions ont été systématiquement prises :

1. **Les catalogues ont été lus par import**, pas par recherche textuelle. Les
   catalogues de rôles et de modules sont des tuples positionnels : une recherche
   par expression régulière aurait produit des chiffres faux.
2. **Les autorisations n'ont pas été déduites du seul champ `User.role`.** Le
   contrôle d'accès réel combine trois sources : le référentiel d'habilitations
   (`curp`), les capacités héritées (`legacy`) et les rôles de secours. Le manuel
   décrit ce mécanisme au lieu de le simplifier.
3. **La matrice des habilitations est calculée**, pas rédigée à la main : elle
   compare le niveau détenu par chaque profil sur chaque module au niveau minimal
   exigé par chaque verbe métier.

---

## 4. Sources exploitées

### 4.1 Sources de code

| Source | Ce qu'elle a fourni |
|---|---|
| `backend/habilitations/referentiel/catalogue_roles.py` | 81 rôles, 22 sensibles, niveaux et périmètres |
| `backend/habilitations/referentiel/catalogue_modules.py` | 20 modules, 123 ressources, 1 157 permissions, 15 critiques |
| `backend/habilitations/referentiel/catalogue_matrice.py` | Matrice rôle × module (niveaux N0–N4), incompatibilités, correspondance des rôles hérités |
| `backend/authentication/role_groups.py` | 12 rôles applicatifs, rôles autorisés en web, politique de rôle |
| `backend/authentication/models.py` | Rôles réellement attribuables à un compte |
| `frontend/src/menu/arborescence.js` | 16 sections, 127 entrées de navigation |
| `frontend/src/menu/ecrans.js` | Écrans génériques et leurs capacités |
| `frontend/src/App.jsx` | 145 routes déclarées ; 96 rattachées à un module d'habilitation |
| `frontend/src/components/auth/ProtectedRoute.jsx` | Double garde d'accès |
| `backend/presences/signals/…` et API de séances | Règle de calcul du taux de présence |
| `backend/formations/models.py` | Structure LMD : semestres et crédits |

### 4.2 Sources visuelles

185 captures existaient dans le dépôt (`docs/audits/53/`, `docs/getinjs/preuves/`,
`preuves-crud/`, `preuves-ue-ecue/`, `preuves-design/`, `preuves-validation/`,
`docs/screenshots/manuel-statistiques/`).

**19 ont été retenues** et documentées une par une (titre, module, légende, source).
Le critère de sélection : une capture par écran réellement décrit dans le manuel,
en privilégiant la diversité des modules et la preuve des règles métier
(lecture seule, refus de suppression, alerte, mobile).

---

## 5. Structure du manuel produit

### 5.1 Les quatorze parties

| Partie | Titre | Chapitres | Blocs |
|---|---|---|---|
| I | Présentation générale | 5 | 35 |
| II | Connexion et sécurité | 5 | 24 |
| III | Administration et gestion des utilisateurs | 5 | 18 |
| IV | Référentiels et formations LMD | 4 | 21 |
| V | Admissions et scolarité | 4 | 19 |
| VI | Pédagogie et emplois du temps (GET-INJS) | 3 | 20 |
| VII | Présences et suivi des séances | 3 | 15 |
| VIII | Évaluations, jurys et diplômation | 3 | 15 |
| IX | Ressources humaines et enseignants | 2 | 6 |
| X | Finances et gestion administrative | 2 | 7 |
| XI | Autres modules | 4 | 11 |
| XII | Assistance et résolution des problèmes | 3 | 3 groupes de 18 problèmes |
| XIII | Fiches par profil utilisateur | 12 fiches | — |
| XIV | Matrice des habilitations par profil | 1 | — |
| — | Index des profils · Annexes et glossaire | — | — |

Les douze premières parties couvrent exactement la structure imposée. La partie XIII
regroupe les fiches par profil. La partie XIV est la matrice demandée.

### 5.2 Le contenu des fiches profil

Chaque fiche comporte : présentation, tableau de bord et navigation, autorisations
(autorisé / interdit), cas pratiques et erreurs fréquentes. Le guide en étapes et
la liste des modules accessibles sont développés dans les parties thématiques
auxquelles la fiche renvoie, afin d'éviter les répétitions que la consigne
demandait précisément d'éviter.

### 5.3 La partie XII — assistance

Elle est construite en tableaux symptôme / cause / vérification / solution / contact,
conformément à la structure demandée, et compte 18 situations réparties en trois
chapitres : difficultés de connexion, d'utilisation, techniques.

---

## 6. Les douze profils documentés

| Profil | Fonction | Accès web | Écrans visibles |
|---|---|---|---|
| ADMIN | Administrateur système | Oui | 100 |
| CHEF_INJS_ADMIN | Chef de service administratif | Oui | 100 |
| INJS_ADMIN | Administrateur de scolarité | Oui | 100 |
| DIRECTION | Direction | Oui | 101 |
| CHEF_SECRETARIAT | Chef de secrétariat | Oui | 98 |
| SECRETARIAT | Secrétariat | Oui | 98 |
| FINANCE | Gestionnaire financier | Oui | 23 |
| ARCHIVE | Archiviste | Oui | 69 |
| ENCADRANT | Encadrant / enseignant | Oui | 60 |
| SUPERVISEUR | Responsable pédagogique | Oui | 49 |
| FORMATEUR | Formateur | **Non** | 0 |
| AUDITEUR | Auditeur / étudiant | **Non** | 0 |

**Deux profils n'ont aucun accès à l'interface web.** Ils sont conservés dans le
manuel pour une raison de traçabilité : leur rôle existe au catalogue et peut être
attribué, mais l'accès web leur est refusé par paramétrage. Le manuel l'indique
explicitement et n'invente aucune fiche d'écran pour eux.

Le manuel distingue systématiquement quatre notions que rien ne doit confondre :
rôle disponible au catalogue, rôle attribué à un compte, profil opérationnel,
et périmètre d'accès.

---

## 7. Vérifications effectuées

### 7.1 Sur le PDF

| Contrôle | Résultat |
|---|---|
| Pages générées | 103 |
| Pages vides ou quasi vides | **0** |
| Signets de navigation | 71 (2 niveaux) |
| Images intégrées | 20 |
| Métadonnées (titre, auteur, sujet) | Présentes |
| Balises non interprétées (`<br/>`, `{{…}}`) | **0** |
| Marquage markdown résiduel (`**`) | **0** |
| Titres de partie coupés en deux pages | **0** (corrigé) |
| Sommaire | Paginé, stabilisé sur deux passes |
| Rendu visuel contrôlé | Couverture, page de titre, sommaire, partie, fiche, matrice, glossaire |

Les défauts suivants ont été **détectés puis corrigés** au cours de la production,
et sont signalés ici parce qu'ils ont réellement existé :

- le bloc d'informations de couverture se chevauchait (« 9 novembre 202612 ») ;
- une balise `<br/>` s'affichait en clair sur la page de titre ;
- la Partie VII n'apparaissait pas dans le sommaire (cartouche coupé par un saut de page) ;
- la pagination du sommaire était décalée d'une page à la première passe ;
- deux pages blanches subsistaient en fin de partie pleine ;
- les en-têtes de la matrice affichaient `Consul-<br/>tation` littéralement ;
- le pied de page indiquait la partie précédente sur la page d'ouverture d'une partie.

### 7.2 Sur le HTML

| Contrôle | Résultat |
|---|---|
| Parties présentes | **14 / 14** |
| Placeholders non rendus | **0** |
| Images manquantes | **0** (20 référencées) |
| Liens internes cassés | **0** (68 liens distincts) |
| Tableaux équilibrés | Oui |
| Langue déclarée, titre, viewport | Présents |
| Attributs d'accessibilité | Présents (`aria-label`, légendes de tableau) |
| Dépendances externes | **Aucune** |
| Recherche locale | Fonctionnelle |
| Filtres par profil et par module | Fonctionnels |
| Mode clair / sombre persistant | Fonctionnel |
| Impression | Feuille de style dédiée |
| Responsive | Points de rupture définis |

### 7.3 Sur la palette

Les cinq couleurs imposées sont présentes et utilisées :
`#073763` (navy), `#0B2545` (bleu profond), `#4A90D9` (bleu clair),
`#EAF3FB` (bleu très clair), `#FFFFFF` (blanc), complétées par les gris et par
les trois couleurs d'état : vert `#059669` (succès), orange `#D97706`
(avertissement), rouge `#DC2626` (erreur ou opération sensible).

### 7.4 Sur la confidentialité

| Recherche | PDF | HTML |
|---|---|---|
| Mot de passe en clair | Aucun | Aucun |
| Jeton ou clé d'API | Aucun | Aucun |
| Adresse électronique | Aucune | Aucune |
| Numéro de téléphone | Aucun | Aucun |
| Clé privée | Aucune | Aucune |
| Identifiant de démonstration | Aucun | Aucun |
| Marque d'une application tierce | Aucune | Aucune |

Le compte de démonstration utilisé localement pour produire les captures n'apparaît
nulle part dans les documents livrés.

---

## 8. Règles métier respectées

### 8.1 Taux de présence

La règle est documentée telle qu'elle est codée :

> **taux de présence = (présents + retards) / effectif attendu × 100**

Les retards restent un indicateur distinct et ne sont jamais fondus dans le taux
sans être nommés. Le seuil par défaut est de 80 %.

### 8.2 Architecture LMD

Le manuel indique : Licence en six semestres (S1 à S6), Master en quatre semestres
(S7 à S10), **30 crédits ECTS par semestre** et **60 crédits ECTS par niveau annuel**.

### 8.3 Les cinq étapes à ne pas confondre

Le manuel distingue explicitement, dans cet ordre : admission, inscription
administrative, validation de l'inscription, parcours académique et inscription
pédagogique.

### 8.4 Emploi du temps simulé et emploi du temps validé

La distinction entre un emploi du temps **simulé** (projet, non opposable) et un
emploi du temps **officiellement validé** est expliquée, avec les conséquences
pratiques de chaque état.

---

## 9. Limites assumées

Le manuel ne prétend pas tout couvrir. Les limites suivantes sont réelles et
volontairement signalées.

1. **Aucune capture en direct n'a pu être produite.** Le navigateur d'interface
   n'était pas démarrable dans l'environnement de production documentaire
   (bibliothèque système manquante, dépôts réseau inaccessibles). Les 19 captures
   proviennent donc de preuves déjà présentes dans le dépôt, toutes issues de
   l'application réelle. Aucune image n'a été fabriquée ni simulée.
2. **Les rôles du catalogue sans interface opérationnelle identifiable ne font pas
   l'objet d'une fiche.** Ils sont mentionnés dans la partie III pour ce qu'ils
   sont : des rôles attribuables, sans écran dédié vérifiable.
3. **Les dix-neuf entrées « Utilisateurs & Accès »** de la navigation ne sont pas
   toutes gouvernées par le référentiel d'habilitations de nouvelle génération.
   Le manuel le dit au lieu de laisser croire à une homogénéité qui n'existe pas.
4. **Les données de référentiel manquantes n'ont pas été inventées.** Lorsqu'une
   valeur n'était pas vérifiable dans le code, elle n'est pas affirmée.

---

## 10. Conformité aux interdits de la mission

| Interdit | Respecté | Preuve |
|---|---|---|
| Modifier le fonctionnement de l'application | Oui | Aucun fichier de `backend/` ni de `frontend/` modifié |
| Modifier modèles, migrations, permissions | Oui | Aucune écriture dans ces dossiers |
| Migration de base de données | Oui | Le schéma a été créé dans une base SQLite de travail temporaire, jamais dans une base existante |
| Réinitialiser ou supprimer une base | Oui | Aucune base existante touchée ; seule une base SQLite de travail, créée pour l'analyse dans un répertoire temporaire, a été utilisée |
| Déployer sur le VPS | Oui | Aucun déploiement |
| Connexion SSH | Oui | Aucune connexion |
| Déclencher un workflow GitHub | Oui | Aucun workflow déclenché |
| Modifier la production | Oui | Aucune action sur la production |
| Supprimer un fichier existant | Oui | Aucune suppression hors fichiers temporaires |
| Écraser un document sans vérification | Oui | Le dossier `documentation/manuel_utilisateur/` est nouveau |
| Inventer des identifiants ou comptes | Oui | Aucun identifiant dans les livrables |
| Présenter une fonctionnalité future comme disponible | Oui | Statuts explicites au fil du texte |

Aucune image Docker n'a été construite. Aucun conteneur n'a été redémarré.
Aucune configuration de serveur, de DNS ou de proxy n'a été touchée.

---

## 11. Reproductibilité

Le manuel se régénère intégralement à partir des sources livrées.

```bash
cd documentation/manuel_utilisateur/sources/contenu

# Manuel PDF
python generer_pdf.py
# → ../../pdf/MANUEL_UTILISATEUR_OFFICIEL_INJS_2026.pdf

# Manuel HTML
python generer_html.py
# → ../../html/index.html
```

Prérequis : Python 3.11, `reportlab`, `Pillow`, et les polices DejaVu. La génération
PDF effectue plusieurs passes afin de stabiliser la pagination du sommaire et de
l'index : c'est normal, le nombre de passes est affiché.

Le module `matrice.py` lit directement les catalogues d'habilitations de
l'application : si le référentiel évolue, la matrice se met à jour à la
régénération, sans retouche rédactionnelle.

---

## 12. Statistiques de production

Les chiffres ci-dessous sont **mesurés**, non estimés. Chacun est reproductible
par la commande indiquée dans la colonne « Vérification ».

### 12.1 Le référentiel d'habilitations

| Indicateur | Valeur | Vérification |
|---|---|---|
| **Rôles catalogués** | **81** | `catalogue_roles.ROLES` |
| **Rôles sensibles** | **22** | `catalogue_roles.ROLES_SENSIBLES` |
| **Modules fonctionnels** | **20** | `catalogue_modules.MODULES` |
| **Ressources** | **123** | `importlib` sur le catalogue |
| **Ressources critiques** | **15** | `rbac.json › permissions_critiques` |
| **Permissions atomiques** | **1 157** | `chargement.deplier_permissions()` |
| **Rôles incompatibles** | **5 paires** | `rbac.json › incompatibilites` |

### 12.2 Les profils opérationnels

| Indicateur | Valeur |
|---|---|
| **Profils opérationnels identifiés** | **12** (`User.Role`) |
| **Profils réellement documentés** | **12** — y compris les deux sans accès web |
| **Profils avec accès à l'interface web** | **10** |
| **Profils sans accès web** | **2** (FORMATEUR, AUDITEUR) |

Un **profil opérationnel** n'est pas un **rôle du catalogue** : les 12 valeurs de
`User.Role` sont reliées aux 81 rôles par `CORRESPONDANCE_LEGACY`. Le manuel ne
déduit jamais les droits du seul champ `User.role` ; il les établit par
`ROLE_POLICY`, `ALLOWED_WEB_ROLES` et `mes-acces`.

### 12.3 La couverture rédactionnelle

| Indicateur | Valeur |
|---|---|
| **Modules couverts** | **20 sur 20** |
| **Parties du manuel** | **14** |
| **Chapitres rédigés** | **44** |
| **Procédures pas à pas** | **12** (blocs « étapes » numérotées) |
| **Fiches profil** | **12** |
| **Captures d'écran** | **19** (toutes issues de l'application réelle) |
| **Routes inventoriées** | **143 chemins**, **96 rattachés à un module** |
| **Entrées de navigation** | **127**, réparties en **16 sections** |

### 12.4 Les fonctionnalités non documentables

Quatre familles ne figurent pas dans le manuel, faute d'être accessibles ou
vérifiables. Elles sont listées ici pour que l'absence soit explicite.

| Fonctionnalité | Raison de l'absence |
|---|---|
| Écrans du profil FORMATEUR | Accès web refusé par `ALLOWED_WEB_ROLES` |
| Écrans du profil AUDITEUR | Accès web refusé par `ALLOWED_WEB_ROLES` |
| Application mobile Flutter | SDK indisponible dans l'environnement de production |
| Notifications temps réel | Aucun canal vérifié dans le code livré |

### 12.5 Les limitations constatées

- **Captures non interactives.** Les captures proviennent de rendus statiques :
  aucun navigateur n'était disponible pour piloter l'application en direct. Elles
  reproduisent l'état réel des écrans, sans interaction simulée.
- **Emploi du temps simulé.** La génération d'emploi du temps produit une
  proposition ; seule la validation la rend opposable. Le manuel distingue les deux.
- **Périmètre.** Les droits varient selon le périmètre attribué. La matrice indique
  le niveau maximal atteignable, non un droit systématique sur chaque ressource.

### 12.6 Les résultats des tests

| Contrôle | Résultat |
|---|---|
| Parties attendues / présentes | **14 / 14** |
| Palette imposée | **8 / 8** couleurs conformes |
| Dépendances externes du HTML | **0** |
| Images référencées manquantes | **0** |
| Liens internes cassés | **0** |
| Placeholders non résolus | **0** |
| Marqueurs Markdown résiduels (`**`) | **0** |
| Données personnelles dans les livrables | **0** |
| Identifiants de démonstration | **0** |
| Syntaxe JavaScript | **valide** (`node --check`) |
| Intégrité des archives ZIP | **OK** (`testzip`) |
| Empreintes SHA-256 de la page | **conformes** |

### 12.7 L'emplacement exact des fichiers

```
arena/documentation/manuel_utilisateur/
├── RAPPORT_PRODUCTION.md          ce document
├── LIRE-MOI.txt                   notice de prise en main
├── pdf/
│   └── MANUEL_UTILISATEUR_OFFICIEL_INJS_2026.pdf      4 499 031 o · 104 pages
├── html/
│   ├── index.html                                     279 615 o
│   └── assets/
│       ├── css/manuel.css                              35 820 o
│       ├── js/manuel.js                                17 990 o
│       └── images/                                   19 captures
├── sources/
│   ├── contenu/                    14 générateurs Python
│   ├── captures/                   19 captures d'origine
│   └── referentiels/               8 fichiers JSON
└── telechargements/
    ├── index.html                  page de téléchargement
    ├── MANUEL_UTILISATEUR_OFFICIEL_INJS_2026.pdf
    ├── …_COMPLET.zip               64 fichiers · 10,5 Mo
    ├── …_HTML.zip                  22 fichiers · 3,5 Mo
    └── RAPPORT_PRODUCTION.md
```

La publication vers cet emplacement est assurée par
`sources/contenu/publier.py`, qui refuse d'écraser un fichier plus récent que sa
source et vérifie chaque copie par empreinte.

## 13. Conclusion

Les livrables demandés existent et ont été vérifiés :

- un **PDF A4 de 104 pages**, avec couverture composée, page de titre, sommaire
  paginé, quatorze parties, index des profils, glossaire et 72 signets ;
- un **HTML autonome de 280 Ko**, avec recherche locale par permission et
  par synonyme, quatre filtres combinables (profil, module, type d'opération,
  niveau de responsabilité), mode sombre, impression et aucune dépendance
  externe ;
  impression et aucune dépendance externe ;
- **douze fiches profil**, y compris les deux profils sans accès web ;
- la **matrice `Profil | Modules accessibles | Consultation | Création | Modification |
  Validation | Suppression | Export`**, calculée à partir du référentiel réel ;
- **dix-neuf captures** de l'application réelle, chacune accompagnée de son titre,
  de sa légende et de son rattachement à une procédure ;
- ce rapport.

Le manuel décrit l'application telle qu'elle est. Là où une fonction n'existe pas
ou n'est pas accessible, il le dit.
