"""Contenu rédactionnel du manuel — Parties I à III."""
from __future__ import annotations

from socle import (
    APPLICATION, CAPTURES, INSTITUTION, LISTE_PROFILS, META, MODULES, ROLES,
    SECTIONS, capture, modules_par_sensibilite, roles_par_famille, roles_sensibles,
)

# ─────────────────────────────────────────────────────────────── PARTIE I
PARTIE_I = {
    "id": "partie-1",
    "numero": "I",
    "titre": "Présentation générale",
    "chapitres": [
        {
            "id": "ch-1-1",
            "titre": "À quoi sert cette application",
            "profils": ["tous"],
            "blocs": [
                ("p", "L'application de gestion intégrée de l'INJS Abidjan réunit dans un seul "
                      "environnement numérique l'ensemble des opérations administratives, "
                      "pédagogiques et financières de l'institut. Elle remplace la circulation "
                      "de dossiers papier et les fichiers tableurs dispersés par un système "
                      "unique, partagé et traçable."),
                ("p", "Chaque agent accède à la plateforme avec son compte personnel. "
                      "L'application ne montre à chacun que les écrans correspondant à ses "
                      "responsabilités ; les autres restent invisibles. Cette restriction n'est "
                      "pas un confort : elle garantit qu'aucune donnée sensible — notes, "
                      "paiements, dossiers d'étudiants — n'est consultable par un agent qui "
                      "n'a pas à la connaître."),
                ("encadre", {
                    "type": "information",
                    "titre": "Un seul système, plusieurs métiers",
                    "texte": "La plateforme couvre vingt domaines fonctionnels, de la "
                             "candidature à la diplômation, en passant par les emplois du temps, "
                             "les présences, les finances et le patrimoine. Ce manuel consacre "
                             "une fiche distincte à chaque profil utilisateur.",
                }),
                ("h3", "Ce que l'application permet"),
                ("liste", [
                    "**Instruire les candidatures** et organiser les concours d'entrée.",
                    "**Gérer la scolarité** : admissions, inscriptions, dossiers et documents.",
                    "**Construire les maquettes LMD** : UE, ECUE, crédits et volumes horaires.",
                    "**Élaborer et publier les emplois du temps**, en détectant les conflits.",
                    "**Enregistrer les présences**, y compris par badgeage QR sur mobile.",
                    "**Saisir et contrôler les notes**, conduire les délibérations et les jurys.",
                    "**Établir les diplômes**, attestations et relevés de notes.",
                    "**Suivre les finances étudiantes** et les vacations des formateurs.",
                    "**Produire des statistiques** et des tableaux de bord de pilotage.",
                    "**Administrer les comptes et les droits** avec une traçabilité complète.",
                ]),
                ("h3", "Ce que l'application ne fait pas"),
                ("p", "Ce manuel ne documente que les fonctions réellement disponibles dans "
                      "la version en service. Certaines fonctionnalités annoncées dans les "
                      "documents de conception ne sont pas encore ouvertes à tous les profils : "
                      "elles sont signalées comme telles au fil du texte, et jamais présentées "
                      "comme opérationnelles."),
            ],
        },
        {
            "id": "ch-1-2",
            "titre": "Organisation générale de la plateforme",
            "profils": ["tous"],
            "blocs": [
                ("p", "L'espace de travail se compose de quatre zones constantes. Les "
                      "reconnaître suffit à se repérer dans n'importe quel module."),
                ("figure", {"image": "02-referentiels.png",
                            "titre": "Écran type de l'application",
                            "legende": "1. Barre latérale de navigation · 2. Barre supérieure "
                                       "(recherche, année, compte) · 3. Zone de travail · "
                                       "4. Fils d'Ariane et actions de la page."}),
                ("h3", "1. La barre latérale"),
                ("p", "À gauche, elle liste les modules auxquels votre compte a droit. Un "
                      "module se déplie pour révéler ses écrans. **Si un module n'apparaît "
                      "pas, ce n'est pas une panne : votre profil n'y a pas accès.** Le bas de "
                      "la barre affiche votre nom et votre rôle."),
                ("h3", "2. La barre supérieure"),
                ("p", "Elle contient le moteur de recherche global, le sélecteur d'année "
                      "académique, les notifications et le menu de votre compte "
                      "(profil, changement de mot de passe, déconnexion)."),
                ("h3", "3. La zone de travail"),
                ("p", "C'est le contenu de l'écran ouvert : listes, formulaires, indicateurs, "
                      "tableaux de bord. Elle commence toujours par un en-tête rappelant le "
                      "module et l'action possible."),
                ("h3", "4. Le fil d'Ariane"),
                ("p", "En haut de la zone de travail, il indique votre position "
                      "(par exemple « Scolarité › Inscriptions ») et permet de remonter d'un "
                      "niveau en un clic."),
                ("h3", "Les seize modules"),
                ("p", "La navigation est organisée en seize sections regroupant "
                      f"{META['entrees_menu']} écrans. Toutes ne sont pas visibles par tous : "
                      "le tableau ci-dessous donne la répartition réelle."),
                ("tableau_modules_navigation", None),
            ],
        },
        {
            "id": "ch-1-3",
            "titre": "Les vingt domaines fonctionnels",
            "profils": ["tous"],
            "blocs": [
                ("p", "Le système d'habilitations découpe l'application en vingt modules. "
                      "Cette découpe est celle qui commande réellement les droits : c'est "
                      "elle qui décide si un bouton s'affiche et si une action est acceptée "
                      "par le serveur."),
                ("tableau_modules_rbac", None),
                ("encadre", {
                    "type": "attention",
                    "titre": "Ne pas confondre menu et permission",
                    "texte": "Un menu peut être visible sans que toutes ses actions soient "
                             "autorisées. L'inverse est vrai aussi : masquer un menu ne "
                             "supprime pas un droit. Le contrôle déterminant est toujours "
                             "effectué par le serveur.",
                }),
            ],
        },
        {
            "id": "ch-1-4",
            "titre": "Terminologie",
            "profils": ["tous"],
            "blocs": [
                ("p", "Les termes ci-dessous sont employés dans tout le manuel avec la "
                      "signification exacte que leur donne l'application."),
                ("glossaire", None),
            ],
        },
        {
            "id": "ch-1-5",
            "titre": "Prérequis et accès",
            "profils": ["tous"],
            "blocs": [
                ("h3", "Navigateurs compatibles"),
                ("p", "L'application fonctionne sur tout navigateur récent. Sont recommandés :"),
                ("liste", [
                    "**Mozilla Firefox** — version 115 ou supérieure.",
                    "**Google Chrome** — version 110 ou supérieure.",
                    "**Microsoft Edge** — version 110 ou supérieure.",
                    "**Safari** — version 16 ou supérieure (macOS et iPadOS).",
                ]),
                ("p", "Internet Explorer n'est pas pris en charge. Sur mobile, la "
                      "consultation est possible mais certaines opérations de saisie "
                      "étendues restent plus confortables sur ordinateur."),
                ("h3", "Configuration requise"),
                ("liste", [
                    "Une connexion Internet stable (l'application fonctionne en ligne).",
                    "Un écran d'au moins 1 024 pixels de large pour les tableaux complexes.",
                    "Les cookies et JavaScript activés — ils sont indispensables à la session.",
                    "Pour le badgeage : un smartphone avec appareil photo et géolocalisation.",
                ]),
                ("h3", "Adresse d'accès"),
                ("p", "L'application est accessible à l'adresse communiquée par le service "
                      "informatique de l'institut. Elle ouvre sur l'écran de connexion."),
                ("figure", {"image": "01-connexion.jpg",
                            "titre": "Écran de connexion",
                            "legende": "Saisissez votre identifiant et votre mot de passe, "
                                       "puis cliquez sur « Se connecter ». Le bouton "
                                       "« administration » ouvre l'interface de gestion "
                                       "réservée aux administrateurs."}),
                ("encadre", {
                    "type": "danger",
                    "titre": "Ne partagez jamais votre compte",
                    "texte": "Chaque action est enregistrée au nom du compte utilisé. "
                             "Prêter ses identifiants revient à signer à la place d'autrui : "
                             "la traçabilité devient fausse et votre responsabilité est "
                             "engagée.",
                }),
            ],
        },
    ],
}

# ─────────────────────────────────────────────────────────────── PARTIE II
PARTIE_II = {
    "id": "partie-2",
    "numero": "II",
    "titre": "Connexion et sécurité",
    "chapitres": [
        {
            "id": "ch-2-1",
            "titre": "Se connecter",
            "profils": ["tous"],
            "blocs": [
                ("etapes", [
                    "Ouvrez l'adresse de l'application dans votre navigateur.",
                    "Saisissez votre **nom d'utilisateur** dans le premier champ.",
                    "Saisissez votre **mot de passe** dans le second.",
                    "Cliquez sur **Se connecter**.",
                    "L'application ouvre votre tableau de bord.",
                ]),
                ("p", "En cas de succès, la barre latérale affiche immédiatement les modules "
                      "de votre profil. En cas d'échec, un message précise la cause : "
                      "identifiants incorrects, compte désactivé, ou accès à la plateforme "
                      "non autorisé pour ce rôle."),
                ("encadre", {
                    "type": "attention",
                    "titre": "« Accès non autorisé » n'est pas une erreur",
                    "texte": "Certains rôles — notamment Formateur et Étudiant — ne disposent "
                             "pas de l'accès web. Leur connexion est refusée par conception. "
                             "Ces utilisateurs passent par les applications mobiles de badgeage.",
                }),
            ],
        },
        {
            "id": "ch-2-2",
            "titre": "Changer de mot de passe",
            "profils": ["tous"],
            "blocs": [
                ("p", "Le changement de mot de passe s'effectue depuis le menu de votre "
                      "compte, en haut à droite."),
                ("etapes", [
                    "Cliquez sur votre nom dans la barre supérieure.",
                    "Choisissez **Profil**.",
                    "Dans la section mot de passe, saisissez votre mot de passe actuel.",
                    "Saisissez le nouveau mot de passe, puis confirmez-le.",
                    "Validez : la modification prend effet immédiatement.",
                ]),
                ("h3", "Changement obligatoire à la première connexion"),
                ("p", "Lorsqu'un compte est créé par l'administration, il peut être marqué "
                      "« changement de mot de passe obligatoire ». Dans ce cas, "
                      "**aucun autre écran n'est accessible** tant que le mot de passe n'a "
                      "pas été modifié : l'application redirige automatiquement vers l'écran "
                      "dédié."),
                ("encadre", {
                    "type": "information",
                    "titre": "Règles de robustesse",
                    "texte": "Choisissez un mot de passe long, différent de ceux utilisés "
                             "sur d'autres services, et ne le communiquez à personne — pas "
                             "même à un collègue qui vous « remplace ».",
                }),
            ],
        },
        {
            "id": "ch-2-3",
            "titre": "Sessions et déconnexion",
            "profils": ["tous"],
            "blocs": [
                ("p", "Une fois connecté, votre session reste active tant que vous utilisez "
                      "l'application. Après une période d'inactivité ou à l'expiration du "
                      "jeton de sécurité, l'application vous invite à vous reconnecter : "
                      "**c'est un comportement normal**, non une perte de données."),
                ("p", "Pour terminer proprement votre travail, utilisez le menu de votre "
                      "compte puis **Déconnexion**. Fermer l'onglet sans se déconnecter "
                      "laisse la session ouverte sur un poste partagé."),
                ("encadre", {
                    "type": "danger",
                    "titre": "Postes partagés",
                    "texte": "Sur un poste utilisé par plusieurs agents, déconnectez-vous "
                             "systématiquement en quittant. Sans cela, la personne suivante "
                             "agit sous votre identité et vos droits.",
                }),
            ],
        },
        {
            "id": "ch-2-4",
            "titre": "Comprendre les droits d'accès",
            "profils": ["tous"],
            "blocs": [
                ("p", "Les droits ne se décident pas au niveau du poste de travail : "
                      "ils sont portés par le compte. Trois notions doivent être distinguées."),
                ("h3", "Le rôle"),
                ("p", "Le rôle désigne la fonction exercée. Il détermine une famille "
                      "d'écrans et de permissions. Une personne peut exercer plusieurs "
                      "fonctions : elle cumule alors les droits correspondants."),
                ("h3", "La permission"),
                ("p", "La permission est une autorisation précise, exprimée sous la forme "
                      "`module.ressource.action` — par exemple "
                      "`scolarite.inscription.valider`, qui autorise la validation d'une "
                      "inscription. Le catalogue en compte "
                      f"**{META['permissions']:,}".replace(",", " ") + "**."),
                ("h3", "Le périmètre"),
                ("p", "Le périmètre borne l'effet d'une permission à un sous-ensemble : "
                      "son secrétariat, sa formation, son parcours, ou son propre dossier. "
                      "**Deux agents ayant la même permission peuvent donc voir des données "
                      "très différentes.**"),
                ("encadre", {
                    "type": "information",
                    "titre": "Niveaux d'intervention",
                    "texte": "Les permissions sont graduées de N0 à N4 : N0 = consultation "
                             "de son propre dossier ; N1 = consultation et impression ; "
                             "N2 = saisie et traitement ; N3 = validation et décision ; "
                             "N4 = administration du module.",
                }),
            ],
        },
        {
            "id": "ch-2-5",
            "titre": "Opérations sensibles",
            "profils": ["tous"],
            "blocs": [
                ("p", "Certaines actions engagent l'institut : elles sont marquées comme "
                      "sensibles et font l'objet d'un contrôle renforcé. Elles sont "
                      "journalisées avec l'identité de leur auteur, la date et l'objet."),
                ("tableau_permissions_critiques", None),
                ("encadre", {
                    "type": "attention",
                    "titre": "Séparation des tâches",
                    "texte": "L'application interdit certaines combinaisons de rôles sur un "
                             "même compte — par exemple saisir des candidatures et contrôler "
                             "ces mêmes dossiers. Ce n'est pas une contrainte technique mais "
                             "une règle de bonne administration.",
                }),
                ("h3", "Bonnes pratiques"),
                ("liste", [
                    "Ne jamais communiquer un identifiant, même à un supérieur hiérarchique.",
                    "Vérifier l'identité de l'étudiant avant toute opération sur son dossier.",
                    "Contrôler le récapitulatif avant de valider une décision irréversible.",
                    "Signaler immédiatement au service informatique toute action suspecte.",
                    "Se déconnecter de tout poste partagé.",
                ]),
            ],
        },
        {
            "id": "ch-2-6",
            "titre": "Le parcours des six premières étapes",
            "profils": ["tous"],
            "blocs": [
                ("p", "Ce guide condense en six étapes ce qu'un agent doit faire pour être "
                      "opérationnel. Chaque étape renvoie au chapitre détaillé correspondant. "
                      "Les six étapes s'enchaînent : aucune ne peut être sautée."),
                ("tableau", {
                    "entetes": ["Étape", "Ce que vous faites", "Où", "Chapitre"],
                    "lignes": [
                        ["1", "Recevoir vos identifiants et l'adresse de la plateforme",
                         "Auprès de l'administrateur", "2.1"],
                        ["2", "Se connecter et changer le mot de passe initial",
                         "Écran de connexion", "2.1 et 2.2"],
                        ["3", "Identifier son profil et les modules visibles",
                         "Barre latérale et tableau de bord", "2.4"],
                        ["4", "Repérer les écrans de son périmètre",
                         "Menu de navigation", "Partie IV"],
                        ["5", "Effectuer une première opération de consultation",
                         "Écran de liste du module", "Partie IV"],
                        ["6", "Savoir où signaler une anomalie",
                         "Chapitre d'assistance", "Partie XII"],
                    ],
                }),
                ("encadre", {
                    "type": "information",
                    "titre": "Pourquoi changer le mot de passe à la première connexion",
                    "texte": "Le mot de passe initial est communiqué par l'administrateur. "
                             "Tant qu'il n'est pas changé, toute personne qui en aurait "
                             "connaissance pourrait se connecter sous votre identité. Le "
                             "changement est immédiat et ne nécessite aucune validation.",
                }),
                ("h3", "Après la sixième étape"),
                ("p", "Une fois ces six étapes franchies, l'agent sait se connecter, "
                      "reconnaître son profil, retrouver un écran et signaler un incident. "
                      "La suite du manuel détaille, module par module, les opérations de "
                      "son périmètre."),
            ],
        },
    ],
}

# ─────────────────────────────────────────────────────────────── PARTIE III
PARTIE_III = {
    "id": "partie-3",
    "numero": "III",
    "titre": "Administration et gestion des utilisateurs",
    "chapitres": [
        {
            "id": "ch-3-1",
            "titre": "Le catalogue des rôles",
            "profils": ["ADMIN", "CHEF_INJS_ADMIN", "INJS_ADMIN"],
            "blocs": [
                ("p", "Le référentiel des habilitations comporte "
                      f"**{META['roles_catalogue']} rôles** dont "
                      f"**{META['roles_sensibles']} rôles sensibles**. Ce catalogue est "
                      "la référence officielle : il décrit ce que chaque fonction peut "
                      "faire, indépendamment des personnes nommées."),
                ("encadre", {
                    "type": "attention",
                    "titre": "Rôle disponible n'est pas rôle attribué",
                    "texte": "Un rôle du catalogue peut n'être attribué à aucun compte. "
                             "Inversement, un compte peut cumuler plusieurs rôles. "
                             "Ne déduisez jamais les droits réels d'une personne du seul "
                             "intitulé de son poste.",
                }),
                ("roles_par_famille", None),
            ],
        },
        {
            "id": "ch-3-2",
            "titre": "Créer un compte utilisateur",
            "profils": ["ADMIN", "CHEF_INJS_ADMIN", "INJS_ADMIN"],
            "blocs": [
                ("p", "La création de comptes est réservée aux profils disposant de la "
                      "permission de gestion des comptes. Elle s'effectue depuis "
                      "**Utilisateurs & Accès › Comptes utilisateurs**."),
                ("etapes", [
                    "Ouvrez **Utilisateurs & Accès** puis **Comptes utilisateurs**.",
                    "Cliquez sur **Nouveau compte**.",
                    "Renseignez le nom d'utilisateur, le nom, le prénom et l'adresse "
                    "électronique professionnelle.",
                    "Sélectionnez le **rôle** correspondant à la fonction réelle.",
                    "Rattachez le compte à un **secrétariat** lorsque le rôle l'exige : "
                    "ce rattachement détermine le périmètre des données visibles.",
                    "Activez le compte et validez.",
                ]),
                ("p", "Le compte créé reçoit un mot de passe initial. À la première "
                      "connexion, l'utilisateur doit le remplacer."),
                ("encadre", {
                    "type": "attention",
                    "titre": "Un compte par personne",
                    "texte": "Ne créez jamais de compte générique ou partagé "
                             "(« secretariat1 », « service »). La traçabilité des actions "
                             "en dépend directement.",
                }),
            ],
        },
        {
            "id": "ch-3-3",
            "titre": "Modifier, désactiver, réactiver",
            "profils": ["ADMIN", "CHEF_INJS_ADMIN", "INJS_ADMIN"],
            "blocs": [
                ("p", "Toute modification d'un compte est journalisée. Trois opérations "
                      "courantes doivent être distinguées."),
                ("tableau", {
                    "entetes": ["Opération", "Effet", "Réversible ?"],
                    "lignes": [
                        ["Modifier les informations", "Met à jour nom, courriel, "
                         "rattachement", "Oui"],
                        ["Désactiver le compte", "Interdit toute connexion ; les données "
                         "restent intactes", "Oui"],
                        ["Supprimer le compte", "Retire l'accès de façon définitive",
                         "Non"],
                    ],
                }),
                ("p", "**En cas de départ ou de mutation, désactivez le compte ; ne le "
                      "supprimez pas.** La conservation du compte préserve l'historique "
                      "des actions passées, indispensable en cas de contrôle."),
            ],
        },
        {
            "id": "ch-3-4",
            "titre": "Attribuer des rôles et des permissions",
            "profils": ["ADMIN", "CHEF_INJS_ADMIN", "INJS_ADMIN"],
            "blocs": [
                ("p", "L'attribution d'un rôle ouvre un ensemble de permissions selon le "
                      "niveau défini par la matrice. L'attribution est elle-même une "
                      "opération sensible."),
                ("etapes", [
                    "Ouvrez **Utilisateurs & Accès › Rôles**.",
                    "Recherchez le compte concerné.",
                    "Ajoutez le rôle souhaité en précisant le **périmètre** "
                    "(secrétariat, formation, parcours).",
                    "Contrôlez l'écran de synthèse : il liste les permissions réellement "
                    "accordées.",
                    "Validez, puis demandez à l'intéressé de vérifier ses accès.",
                ]),
                ("encadre", {
                    "type": "danger",
                    "titre": "Vérifier l'impact avant de valider",
                    "texte": "L'écran **Impact d'un rôle** affiche, avant toute validation, "
                             "la liste exacte des permissions qui seront ouvertes. "
                             "Consultez-le systématiquement : un rôle mal choisi peut ouvrir "
                             "l'accès aux notes ou aux paiements.",
                }),
                ("h3", "Délégations"),
                ("p", "Une délégation permet de transférer temporairement des droits à un "
                      "autre agent — par exemple pendant un congé. Elle est toujours bornée "
                      "dans le temps et son échéance est suivie par l'application, qui "
                      "signale les délégations arrivant à terme."),
            ],
        },
        {
            "id": "ch-3-5",
            "titre": "Contrôler les accès et la traçabilité",
            "profils": ["ADMIN", "CHEF_INJS_ADMIN", "INJS_ADMIN", "DIRECTION"],
            "blocs": [
                ("p", "Le module **Audit & Traçabilité** enregistre les actions sensibles "
                      "et permet de répondre à une question simple : qui a fait quoi, "
                      "quand, et sur quel objet."),
                ("tableau", {
                    "entetes": ["Écran", "Ce qu'il montre"],
                    "lignes": [
                        ["Journal d'audit", "Toutes les actions sensibles, avec auteur et "
                         "horodatage"],
                        ["Actions utilisateurs", "Les opérations effectuées par un compte "
                         "donné"],
                        ["Modifications", "Les changements de valeurs, avant et après"],
                        ["Événements de sécurité", "Connexions, échecs de connexion, "
                         "changements de mot de passe"],
                        ["Intégrité de la chaîne", "Contrôle de non-altération des "
                         "enregistrements"],
                        ["Archives d'audit", "Les journaux clôturés, conservés"],
                    ],
                }),
                ("p", "Ces écrans sont accessibles depuis la section **Audit & "
                      "Traçabilité** de la barre latérale, selon les droits du profil."),
            ],
        },
    ],
}
