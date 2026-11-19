"""Contenu rédactionnel du manuel — Parties IV à VII (métier)."""
from __future__ import annotations

from socle import META

# ─────────────────────────────────────────────────────────────── PARTIE IV
PARTIE_IV = {
    "id": "partie-4",
    "numero": "IV",
    "titre": "Référentiels et formations LMD",
    "chapitres": [
        {
            "id": "ch-4-1",
            "titre": "Comprendre l'architecture LMD",
            "profils": ["ADMIN", "DIRECTION", "SUPERVISEUR", "CHEF_SECRETARIAT"],
            "blocs": [
                ("p", "L'INJS organise ses enseignements selon le système Licence-Master-"
                      "Doctorat. Cette architecture n'est pas décorative : elle conditionne "
                      "le calcul des crédits, la progression des étudiants et la délivrance "
                      "des diplômes."),
                ("tableau", {
                    "entetes": ["Cycle", "Niveaux", "Semestres", "Crédits"],
                    "lignes": [
                        ["Licence", "L1 à L3", "S1 à S6", "180 ECTS"],
                        ["Master", "M1 et M2", "S7 à S10", "120 ECTS"],
                    ],
                }),
                ("h3", "Les règles structurantes"),
                ("liste", [
                    "Un **semestre** vaut **30 crédits ECTS**.",
                    "Une **année** (deux semestres) vaut **60 crédits ECTS**.",
                    "Chaque **unité d'enseignement (UE)** regroupe un ou plusieurs "
                    "**éléments constitutifs (ECUE)**.",
                    "Chaque ECUE porte un **volume horaire** (CM, TD, TP) et des crédits.",
                    "Une **maquette pédagogique** fixe, pour une formation et un niveau, "
                    "la liste des UE et leur répartition par semestre.",
                ]),
                ("encadre", {
                    "type": "information",
                    "titre": "Maquette et référentiel ne se confondent pas",
                    "texte": "Le référentiel décrit un contenu officiel et stable ; la "
                             "maquette décrit son application à une formation et à une année "
                             "données. Une modification de maquette ne modifie jamais le "
                             "référentiel national.",
                }),
            ],
        },
        {
            "id": "ch-4-2",
            "titre": "Le catalogue des référentiels",
            "profils": ["ADMIN", "DIRECTION", "SUPERVISEUR"],
            "blocs": [
                ("p", "La section **Référentiels** de la barre latérale rassemble les "
                      "nomenclatures qui alimentent tout le reste de l'application. "
                      "Les données y sont regroupées par famille."),
                ("tableau", {
                    "entetes": ["Famille", "Contenu"],
                    "lignes": [
                        ["Référentiels institutionnels", "Mentions, écoles, entités "
                         "rattachées"],
                        ["Offre de formation", "Filières, niveaux, parcours, semestres"],
                        ["Système LMD", "Niveaux, parcours, semestres, UE et ECUE"],
                        ["Référentiels pédagogiques", "Types d'enseignement, d'espace, "
                         "d'évaluation, de décision"],
                        ["Ressources humaines pédagogiques", "Grades enseignants"],
                        ["Organisation pédagogique", "Statuts, bâtiments, salles, sites, "
                         "vagues"],
                        ["Administratif et scolarité", "Modèles de paiement, types de "
                         "document et de notification, années académiques"],
                    ],
                }),
                ("figure", {"image": "02-referentiels.png",
                            "titre": "Le catalogue des référentiels",
                            "legende": "Chaque carte indique le nombre de valeurs "
                                       "disponibles et son état de complétude. Une carte "
                                       "marquée « non renseigné » n'empêche pas le travail "
                                       "mais bloque les contrôles qui en dépendent."}),
                ("encadre", {
                    "type": "attention",
                    "titre": "Un référentiel incomplet bloque en aval",
                    "texte": "Une maquette sans UE, ou une salle sans capacité, empêche la "
                             "génération des emplois du temps. Complétez les référentiels "
                             "avant d'aborder les traitements qui les utilisent.",
                }),
            ],
        },
        {
            "id": "ch-4-3",
            "titre": "Construire une maquette pédagogique",
            "profils": ["SUPERVISEUR", "CHEF_SECRETARIAT", "ADMIN"],
            "blocs": [
                ("p", "La maquette est le document de référence d'une formation : elle "
                      "liste les UE par semestre, avec leurs crédits et volumes horaires."),
                ("etapes", [
                    "Ouvrez **Scolarité › Maquettes LMD**.",
                    "Choisissez la **formation** et le **niveau** concernés.",
                    "Créez la maquette ou ouvrez celle à réviser.",
                    "Ajoutez les **UE** une à une, en précisant le semestre et les crédits.",
                    "Pour chaque UE, ajoutez ses **ECUE** avec leurs volumes horaires.",
                    "Vérifiez le total des crédits par semestre : il doit atteindre 30.",
                    "Enregistrez, puis contrôlez la synthèse proposée par l'application.",
                ]),
                ("figure", {"image": "15-ue-ecue.png",
                            "titre": "Unités d'enseignement et éléments constitutifs",
                            "legende": "Chaque UE affiche ses ECUE, les crédits et les "
                                       "volumes horaires. L'état de la ligne indique si "
                                       "l'UE est en brouillon, active ou désactivée."}),
                ("encadre", {
                    "type": "danger",
                    "titre": "Pas de modification après publication",
                    "texte": "Une fois une maquette utilisée pour une année académique "
                             "révolue, ne la modifiez plus : vous altéreriez l'historique "
                             "des étudiants concernés. Créez une nouvelle version.",
                }),
                ("figure", {"image": "03-modules-officiels.png",
                            "titre": "Modules officiels",
                            "legende": "Les modules officiels rattachés aux maquettes. "
                                       "La colonne d'état signale les modules incomplets, "
                                       "qui doivent être complétés avant génération."}),
            ],
        },
        {
            "id": "ch-4-4",
            "titre": "Gérer les référentiels courants",
            "profils": ["ADMIN", "SUPERVISEUR", "CHEF_SECRETARIAT"],
            "blocs": [
                ("p", "Les écrans de référentiel partagent la même logique : une liste "
                      "filtrable, un formulaire de création, une fiche de modification "
                      "et une action de suppression protégée."),
                ("etapes", [
                    "Ouvrez le référentiel souhaité depuis la barre latérale.",
                    "Utilisez la **recherche** et les **filtres** pour trouver une entrée.",
                    "Cliquez sur **Nouveau** pour créer, ou sur une ligne pour modifier.",
                    "Renseignez les champs : ceux marqués d'un astérisque sont obligatoires.",
                    "Validez avec **Enregistrer**.",
                    "Contrôlez que la ligne apparaît dans la liste avec l'état attendu.",
                ]),
                ("figure", {"image": "12-crud-liste.png",
                            "titre": "Liste d'un référentiel",
                            "legende": "La liste présente les colonnes essentielles, un "
                                       "champ de recherche et des actions par ligne "
                                       "(consulter, modifier, supprimer)."}),
                ("figure", {"image": "13-crud-formulaire.png",
                            "titre": "Formulaire de création",
                            "legende": "Les champs obligatoires sont signalés. Les valeurs "
                                       "déjà utilisées sont refusées avec un message "
                                       "explicite."}),
                ("h3", "Quand la suppression est refusée"),
                ("p", "Une entrée référencée par des données métier ne peut pas être "
                      "supprimée : l'application le refuse et indique ce qui la retient. "
                      "Utilisez alors la **désactivation**, qui conserve l'historique."),
                ("figure", {"image": "14-crud-suppression-refusee.png",
                            "titre": "Suppression refusée",
                            "legende": "Le refus est explicite : il nomme la dépendance "
                                       "qui empêche la suppression. Ce n'est pas une "
                                       "panne, mais une protection de l'intégrité."}),
            ],
        },
    ],
}

# ─────────────────────────────────────────────────────────────── PARTIE V
PARTIE_V = {
    "id": "partie-5",
    "numero": "V",
    "titre": "Admissions et scolarité",
    "chapitres": [
        {
            "id": "ch-5-1",
            "titre": "Les cinq étapes à ne pas confondre",
            "profils": ["SECRETARIAT", "CHEF_SECRETARIAT", "ADMIN"],
            "blocs": [
                ("p", "Le parcours d'un étudiant, de sa candidature à sa vie académique, "
                      "se déroule en cinq opérations **distinctes**. Les confondre est la "
                      "première source d'erreur constatée en exploitation."),
                ("tableau", {
                    "entetes": ["Étape", "Ce qu'elle signifie", "Qui la réalise"],
                    "lignes": [
                        ["1. Admission", "Le candidat est déclaré admis à la suite du "
                         "concours ou de l'examen du dossier", "Responsable des admissions"],
                        ["2. Inscription administrative", "L'admission devient un dossier "
                         "d'étudiant rattaché à une formation et une année", "Secrétariat"],
                        ["3. Validation de l'inscription", "L'inscription est contrôlée et "
                         "validée ; elle devient définitive", "Chef de secrétariat ou "
                         "responsable des inscriptions"],
                        ["4. Parcours académique", "L'étudiant est rattaché à un niveau, un "
                         "parcours et un groupe", "Secrétariat / responsable pédagogique"],
                        ["5. Inscription pédagogique", "L'étudiant est inscrit aux UE et "
                         "ECUE de son semestre", "Secrétariat / responsable pédagogique"],
                    ],
                }),
                ("encadre", {
                    "type": "danger",
                    "titre": "Une admission n'est pas une inscription",
                    "texte": "Un candidat admis qui ne s'inscrit pas n'existe pas dans la "
                             "scolarité : il n'apparaît ni dans les effectifs, ni dans les "
                             "listes de présence, ni dans les évaluations. "
                             "Ne considérez jamais une admission comme une inscription "
                             "réalisée.",
                }),
            ],
        },
        {
            "id": "ch-5-2",
            "titre": "Instruire les candidatures",
            "profils": ["SECRETARIAT", "CHEF_SECRETARIAT", "ADMIN"],
            "blocs": [
                ("p", "Les candidatures arrivent par campagne. Chaque campagne définit la "
                      "formation visée, la période et les pièces exigées."),
                ("etapes", [
                    "Ouvrez **Scolarité › Candidatures**.",
                    "Filtrez par **campagne**, **formation** et **statut**.",
                    "Cliquez sur une candidature pour ouvrir le dossier.",
                    "Contrôlez les pièces justificatives reçues.",
                    "Renseignez l'avis d'instruction et enregistrez.",
                ]),
                ("figure", {"image": "16-candidatures.png",
                            "titre": "Liste des candidatures",
                            "legende": "Filtres par campagne, formation et statut. "
                                       "Chaque ligne ouvre le dossier complet du candidat."}),
                ("figure", {"image": "17-candidature-formulaire.png",
                            "titre": "Dossier de candidature",
                            "legende": "Le dossier regroupe l'identité du candidat, la "
                                       "formation visée et les pièces jointes."}),
                ("h3", "Le contrôle des dossiers"),
                ("p", "Le contrôle est une étape séparée de la saisie, assurée par un agent "
                      "distinct. L'application interdit de cumuler saisie et contrôle sur "
                      "un même compte : c'est la règle de séparation des tâches."),
                ("p", "Depuis **Scolarité › Contrôle des dossiers**, chaque pièce peut être "
                      "**validée** ou **rejetée**, avec un motif. Un rejet notifie le "
                      "candidat et suspend l'instruction jusqu'à régularisation."),
            ],
        },
        {
            "id": "ch-5-3",
            "titre": "Inscrire un étudiant",
            "profils": ["SECRETARIAT", "CHEF_SECRETARIAT"],
            "blocs": [
                ("p", "L'inscription administrative crée le dossier de l'étudiant dans "
                      "l'année académique en cours."),
                ("etapes", [
                    "Ouvrez **Scolarité › Inscriptions**.",
                    "Recherchez l'étudiant : par nom, prénom ou numéro de dossier.",
                    "Si l'étudiant est nouveau, créez sa fiche depuis cet écran.",
                    "Choisissez la **formation**, le **niveau** et l'**année académique**.",
                    "Vérifiez les pièces obligatoires et la situation financière.",
                    "Enregistrez : l'inscription passe à l'état **en attente de validation**.",
                ]),
                ("figure", {"image": "18-inscriptions.png",
                            "titre": "Écran d'inscription",
                            "legende": "L'inscription rattache l'étudiant à une formation "
                                       "et une année. L'état de l'inscription est visible "
                                       "à tout moment dans la liste."}),
                ("encadre", {
                    "type": "attention",
                    "titre": "L'inscription reste provisoire jusqu'à validation",
                    "texte": "Tant que la validation n'est pas intervenue, l'étudiant "
                             "apparaît comme inscrit provisoire. Certaines opérations — "
                             "édition de documents officiels, participation aux "
                             "délibérations — restent bloquées dans cet état.",
                }),
            ],
        },
        {
            "id": "ch-5-4",
            "titre": "Documents scolaires et réinscriptions",
            "profils": ["SECRETARIAT", "CHEF_SECRETARIAT", "ARCHIVE"],
            "blocs": [
                ("p", "Une fois l'inscription validée, les documents officiels peuvent être "
                      "produits depuis **Scolarité › Documents scolaires** : attestations "
                      "d'inscription, certificats de scolarité, relevés."),
                ("p", "La **réinscription** reconduit un étudiant d'une année sur l'autre, "
                      "en conservant son parcours. Elle se traite depuis "
                      "**Scolarité › Réinscriptions & transferts**."),
                ("figure", {"image": "04-lecture-seule.png",
                            "titre": "Consultation en lecture seule",
                            "legende": "Un profil de consultation voit les données mais "
                                       "aucun bouton de création, de modification ou de "
                                       "suppression ne lui est proposé."}),
                ("h3", "Le journal de scolarité"),
                ("p", "Toutes les opérations sur un dossier sont consignées dans le "
                      "**Journal de scolarité**. En cas de contestation d'un étudiant, "
                      "c'est la source de vérité : elle indique qui a fait quoi et quand."),
            ],
        },
    ],
}

# ─────────────────────────────────────────────────────────────── PARTIE VI
PARTIE_VI = {
    "id": "partie-6",
    "numero": "VI",
    "titre": "Pédagogie et emplois du temps (GET-INJS)",
    "chapitres": [
        {
            "id": "ch-6-1",
            "titre": "Le module GET-INJS APP",
            "profils": ["SUPERVISEUR", "ADMIN", "CHEF_SECRETARIAT"],
            "blocs": [
                ("p", "Le module **GET INJS APP** regroupe la planification pédagogique : "
                      "emplois du temps, génération, dimensionnement, salles, "
                      "disponibilités et contrôle des conflits. C'est le cœur "
                      "opérationnel de l'organisation des enseignements."),
                ("tableau", {
                    "entetes": ["Écran", "Usage"],
                    "lignes": [
                        ["Tableau de bord", "Vue d'ensemble de la planification"],
                        ["Emplois du temps", "Consultation et édition des emplois du temps"],
                        ["Génération", "Calcul annuel des emplois du temps"],
                        ["Dimensionnement", "Vérification des volumes et des effectifs"],
                        ["Import étudiants", "Chargement des étudiants inscrits"],
                        ["Étudiants inscrits", "Contrôle de la population à planifier"],
                        ["Référentiels", "Nomenclatures utilisées par la planification"],
                        ["Conception", "Construction manuelle d'un emploi du temps"],
                        ["Salles & espaces", "Capacités et affectations"],
                        ["Disponibilités", "Indisponibilités des enseignants et des salles"],
                        ["Conflits & contraintes", "Détection et résolution des conflits"],
                        ["Export / Impression", "Édition des emplois du temps"],
                    ],
                }),
            ],
        },
        {
            "id": "ch-6-2",
            "titre": "Élaborer un emploi du temps",
            "profils": ["SUPERVISEUR", "ADMIN"],
            "blocs": [
                ("p", "L'élaboration se fait en trois temps : préparer les données, "
                      "générer une proposition, puis valider et publier."),
                ("h3", "1. Préparer les données"),
                ("etapes", [
                    "Vérifiez que les **étudiants inscrits** sont chargés et complets.",
                    "Contrôlez le **dimensionnement** : volumes horaires et effectifs.",
                    "Renseignez les **disponibilités** des enseignants et des salles.",
                    "Vérifiez le **référentiel des salles** : capacité et équipement.",
                ]),
                ("figure", {"image": "08-edt-audit-donnees.png",
                            "titre": "Audit des données avant génération",
                            "legende": "L'application contrôle la cohérence des données "
                                       "d'entrée et signale les anomalies bloquantes avant "
                                       "de lancer le calcul."}),
                ("h3", "2. Générer une proposition"),
                ("etapes", [
                    "Ouvrez **GET INJS APP › Génération**.",
                    "Sélectionnez l'**année académique** et le périmètre à planifier.",
                    "Choisissez les **contraintes** à appliquer.",
                    "Lancez la génération et attendez la fin du calcul.",
                    "Examinez le résultat et la liste des conflits résiduels.",
                ]),
                ("figure", {"image": "07-edt-generation.png",
                            "titre": "Écran de génération annuelle",
                            "legende": "Le calcul produit une proposition d'emploi du temps. "
                                       "Une proposition n'est pas un emploi du temps "
                                       "officiel : elle doit être contrôlée puis validée."}),
                ("encadre", {
                    "type": "information",
                    "titre": "Proposition et publication",
                    "texte": "Une proposition générée reste modifiable et invisible des "
                             "étudiants. Seule la **publication** rend l'emploi du temps "
                             "officiel. Tant que la publication n'a pas eu lieu, "
                             "l'emploi du temps précédent reste en vigueur.",
                }),
                ("h3", "3. Contrôler les conflits"),
                ("p", "L'écran **Conflits & contraintes** liste les incompatibilités "
                      "détectées : un même enseignant sur deux séances simultanées, "
                      "une salle doublement réservée, un groupe sureffectif."),
                ("figure", {"image": "09-edt-contraintes.png",
                            "titre": "Politique de contraintes",
                            "legende": "Les contraintes sont paramétrables : "
                                       "indisponibilités, capacité des salles, "
                                       "enchaînements interdits."}),
                ("h3", "4. Publier"),
                ("p", "La publication rend l'emploi du temps visible des enseignants et "
                      "des étudiants. Elle constitue une opération sensible, réservée aux "
                      "profils habilités, et elle est journalisée."),
                ("figure", {"image": "05-edt-grille.png",
                            "titre": "Emploi du temps — grille hebdomadaire",
                            "legende": "La grille présente les créneaux, les salles, les "
                                       "groupes et les enseignants. Les couleurs distinguent "
                                       "les types d'enseignement."}),
                ("figure", {"image": "06-edt-tableau.png",
                            "titre": "Emploi du temps — vue tableau",
                            "legende": "La vue tabulaire facilite le contrôle des volumes "
                                       "horaires et sert de base à l'impression."}),
            ],
        },
        {
            "id": "ch-6-3",
            "titre": "Modifier, rattraper, exporter",
            "profils": ["SUPERVISEUR", "ADMIN"],
            "blocs": [
                ("p", "Toute modification d'un emploi du temps publié doit être motivée : "
                      "elle impacte les enseignants et les étudiants déjà informés."),
                ("liste", [
                    "**Séance déplacée** : modifiez le créneau, puis republiez.",
                    "**Rattrapage** : créez une séance supplémentaire rattachée à "
                    "l'emploi du temps existant.",
                    "**Annulation** : supprimez la séance en conservant la trace du motif.",
                    "**Export** : générez le document depuis **Export / Impression**.",
                ]),
                ("encadre", {
                    "type": "attention",
                    "titre": "Prévenir avant de modifier",
                    "texte": "L'application n'envoie pas de notification automatique aux "
                             "étudiants lors d'une modification. L'information reste à "
                             "la charge du service pédagogique.",
                }),
            ],
        },
    ],
}

# ─────────────────────────────────────────────────────────────── PARTIE VII
PARTIE_VII = {
    "id": "partie-7",
    "numero": "VII",
    "titre": "Présences et suivi des séances",
    "chapitres": [
        {
            "id": "ch-7-1",
            "titre": "Enregistrer les présences",
            "profils": ["ENCADRANT", "SECRETARIAT", "SUPERVISEUR"],
            "blocs": [
                ("p", "La présence est enregistrée séance par séance. Trois canaux sont "
                      "possibles : le badgeage par QR code depuis le téléphone de "
                      "l'étudiant, l'émargement manuel par l'enseignant, et la correction "
                      "par le secrétariat."),
                ("etapes", [
                    "Ouvrez **Présences QR › Séances**.",
                    "Sélectionnez la séance concernée : elle apparaît à sa date et à son "
                    "horaire.",
                    "Ouvrez la **séance en direct** pour suivre le badgeage.",
                    "Si nécessaire, procédez à l'**émargement manuel** pour les étudiants "
                    "présents sans badge.",
                    "Clôturez la séance une fois l'émargement terminé.",
                ]),
                ("figure", {"image": "19-mobile.png",
                            "titre": "Consultation sur mobile",
                            "legende": "L'interface s'adapte aux écrans étroits : la "
                                       "navigation se replie et les tableaux deviennent "
                                       "des cartes lisibles."}),
                ("h3", "Les statuts de présence"),
                ("tableau", {
                    "entetes": ["Statut", "Signification"],
                    "lignes": [
                        ["Présent", "L'étudiant a badgé dans les délais"],
                        ["Retard", "Badgeage effectué après le seuil de tolérance"],
                        ["Absent", "Aucun badgeage enregistré"],
                        ["Absence justifiée", "Absence documentée et acceptée"],
                        ["Excusé", "Absence couverte par une dispense"],
                        ["Non renseigné", "Statut non encore déterminé"],
                    ],
                }),
            ],
        },
        {
            "id": "ch-7-2",
            "titre": "La règle de calcul du taux de présence",
            "profils": ["tous"],
            "blocs": [
                ("p", "Le taux de présence mesure l'assiduité réelle à une séance. "
                      "La règle appliquée par l'application est la suivante :"),
                ("formule", "Taux de présence = (Présents + Retards) / Effectif attendu × 100"),
                ("p", "**Un étudiant en retard compte donc comme présent** dans le calcul "
                      "du taux. Les retards restent néanmoins affichés comme indicateur "
                      "distinct, afin de suivre la ponctualité séparément de l'assiduité."),
                ("encadre", {
                    "type": "attention",
                    "titre": "Deux indicateurs, deux usages",
                    "texte": "Le taux de présence inclut les retards ; le nombre de retards "
                             "reste un compteur à part. Ne comparez jamais les deux chiffres "
                             "comme s'ils mesuraient la même chose.",
                }),
                ("p", "Le taux n'est calculé que si l'effectif attendu est connu et "
                      "supérieur à zéro. Dans le cas contraire, l'application affiche "
                      "« non calculable » plutôt qu'un chiffre faux."),
                ("h3", "Justifications et corrections"),
                ("p", "Une absence peut être justifiée a posteriori depuis le registre. "
                      "La correction est journalisée : l'ancien statut, le nouveau et "
                      "l'identité de l'auteur sont conservés."),
            ],
        },
        {
            "id": "ch-7-3",
            "titre": "Badgeage QR et géolocalisation",
            "profils": ["ENCADRANT", "SECRETARIAT", "ADMIN"],
            "blocs": [
                ("p", "Le badgeage s'appuie sur une application mobile dédiée. L'étudiant "
                      "scanne le QR code affiché par l'enseignant ; l'application enregistre "
                      "l'heure et, lorsque le dispositif est actif, la position."),
                ("liste", [
                    "Le **jeton QR** n'est valable que pendant la séance.",
                    "Un badgeage hors de la zone autorisée est **signalé** comme anomalie.",
                    "La **tolérance de retard** est paramétrable par le service.",
                    "Les badgeages manuels sont **identifiés** comme tels dans le registre.",
                ]),
                ("encadre", {
                    "type": "information",
                    "titre": "Traçabilité du canal",
                    "texte": "Chaque présence indique son canal d'enregistrement : badge QR, "
                             "émargement manuel ou correction administrative. Cette "
                             "information est consultable dans l'écran **Audit**.",
                }),
            ],
        },
    ],
}
