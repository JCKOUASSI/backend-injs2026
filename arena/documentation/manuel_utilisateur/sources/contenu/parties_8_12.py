"""Contenu rédactionnel du manuel — Parties VIII à XII."""
from __future__ import annotations

from socle import META

# ─────────────────────────────────────────────────────────────── PARTIE VIII
PARTIE_VIII = {
    "id": "partie-8",
    "numero": "VIII",
    "titre": "Évaluations, jurys et diplômation",
    "chapitres": [
        {
            "id": "ch-8-1",
            "titre": "Saisir et contrôler les notes",
            "profils": ["ENCADRANT", "SUPERVISEUR", "SECRETARIAT"],
            "blocs": [
                ("p", "La saisie des notes est ouverte à l'enseignant responsable de l'ECUE "
                      "et au secrétariat. Elle suit un circuit contrôlé : saisie, contrôle, "
                      "verrouillage, puis délibération."),
                ("etapes", [
                    "Ouvrez **Évaluations › Saisie des notes**.",
                    "Sélectionnez la formation, le niveau, le semestre et l'ECUE.",
                    "Saisissez les notes étudiant par étudiant.",
                    "Enregistrez : les notes passent à l'état **saisi**.",
                    "Contrôlez la cohérence depuis **Contrôle des notes**.",
                    "Le responsable procède au **verrouillage**, qui interdit toute "
                    "modification ultérieure non autorisée.",
                ]),
                ("encadre", {
                    "type": "danger",
                    "titre": "Le verrouillage est une décision",
                    "texte": "Une fois les notes verrouillées, toute correction exige une "
                             "procédure explicite et laisse une trace. Ne verrouillez qu'après "
                             "contrôle complet : l'opération est volontairement difficile à "
                             "défaire.",
                }),
                ("h3", "Le contrôle des notes"),
                ("p", "L'écran **Contrôle des notes** signale les anomalies détectables : "
                      "notes manquantes, valeurs hors barème, écarts entre le nombre "
                      "d'étudiants attendus et le nombre de notes saisies."),
            ],
        },
        {
            "id": "ch-8-2",
            "titre": "Délibérations et jurys",
            "profils": ["SUPERVISEUR", "DIRECTION", "ADMIN"],
            "blocs": [
                ("p", "Le jury délibère à partir des résultats calculés. L'application ne "
                      "décide pas à sa place : elle produit les moyennes, applique les "
                      "règles de passage et propose des décisions que le jury confirme ou "
                      "modifie."),
                ("tableau", {
                    "entetes": ["Étape", "Écran", "Ce qui se passe"],
                    "lignes": [
                        ["Composition", "Jurys › Composition", "Désignation des membres "
                         "du jury"],
                        ["Délibération", "Jurys › Délibérations", "Examen des résultats et "
                         "décisions"],
                        ["Procès-verbal", "Jurys › PV", "Rédaction et signature du PV"],
                        ["Validation", "Jurys › Validation", "Validation officielle des "
                         "décisions"],
                    ],
                }),
                ("h3", "Les décisions possibles"),
                ("liste", [
                    "**Admis** : l'étudiant valide son année ou son semestre.",
                    "**Admis avec dette** : validation partielle, avec ECUE à repasser.",
                    "**Redoublant** : l'année n'est pas validée.",
                    "**Ajourné** : résultats insuffisants, décision différée.",
                    "**Exclu** : décision d'exclusion prononcée par le jury.",
                ]),
                ("encadre", {
                    "type": "attention",
                    "titre": "Séparation des responsabilités",
                    "texte": "La saisie, le contrôle et la validation sont trois opérations "
                             "distinctes, confiées à des profils différents. Cette séparation "
                             "est volontaire : elle empêche qu'une même personne saisisse une "
                             "note, la valide et prononce la décision qui en découle.",
                }),
            ],
        },
        {
            "id": "ch-8-3",
            "titre": "Diplômes, attestations et relevés",
            "profils": ["DIRECTION", "SECRETARIAT", "ARCHIVE"],
            "blocs": [
                ("p", "Après validation des délibérations, les documents officiels peuvent "
                      "être établis depuis le module **Diplômation**."),
                ("tableau", {
                    "entetes": ["Écran", "Document produit"],
                    "lignes": [
                        ["Éligibilité", "Liste des étudiants remplissant les conditions de "
                         "diplomation"],
                        ["Diplômes", "Diplômes définitifs, après validation"],
                        ["Attestations", "Attestations de réussite ou de scolarité"],
                        ["Certificats", "Certificats de scolarité et de radiation"],
                        ["Registres & modèles", "Registres officiels et modèles de documents"],
                    ],
                }),
                ("encadre", {
                    "type": "danger",
                    "titre": "Un diplôme ne se révoque pas à la légère",
                    "texte": "La révocation d'un diplôme est une opération sensible, "
                             "réservée aux profils habilités, journalisée et "
                             "irréversible. Elle exige une décision écrite de la direction.",
                }),
                ("h3", "Archivage"),
                ("p", "Les listes de notes et cahiers d'appel clôturés sont conservés dans "
                      "**Archives**. Ces documents sont consultables en lecture seule : ils "
                      "constituent la preuve des résultats d'une année révolue."),
            ],
        },
    ],
}

# ─────────────────────────────────────────────────────────────── PARTIE IX
PARTIE_IX = {
    "id": "partie-9",
    "numero": "IX",
    "titre": "Ressources humaines et enseignants",
    "chapitres": [
        {
            "id": "ch-9-1",
            "titre": "Gérer les enseignants et le personnel",
            "profils": ["ADMIN", "SECRETARIAT", "SUPERVISEUR"],
            "blocs": [
                ("p", "Le module **Personnel** rassemble les fiches des enseignants et des "
                      "agents administratifs, leurs affectations et leurs charges."),
                ("tableau", {
                    "entetes": ["Écran", "Usage"],
                    "lignes": [
                        ["Enseignants", "Fiches des enseignants et formateurs"],
                        ["Personnel administratif", "Fiches des agents"],
                        ["Affectations", "Rattachement aux services et départements"],
                        ["Charges / volumes horaires", "Répartition des enseignements"],
                        ["Disponibilités agents", "Indisponibilités déclarées"],
                        ["Documents RH", "Pièces administratives et contrats"],
                    ],
                }),
                ("encadre", {
                    "type": "attention",
                    "titre": "Ne pas confondre fiche et compte",
                    "texte": "La fiche d'un enseignant décrit une personne et son activité. "
                             "Le compte utilisateur décrit un accès à l'application. "
                             "Les deux sont liés mais distincts : supprimer une fiche ne "
                             "supprime pas le compte.",
                }),
            ],
        },
        {
            "id": "ch-9-2",
            "titre": "Charges d'enseignement et vacations",
            "profils": ["ADMIN", "SUPERVISEUR", "FINANCE"],
            "blocs": [
                ("p", "Les heures effectuées par les enseignants sont suivies dans "
                      "**Affectations pédagogiques** et **Charges / volumes horaires**."),
                ("p", "La rémunération des vacations se consulte depuis "
                      "**Finances étudiantes › Vacations & encadrants**. Le calcul s'appuie "
                      "sur les heures réellement validées, non sur les heures planifiées."),
                ("encadre", {
                    "type": "information",
                    "titre": "Validé prime sur planifié",
                    "texte": "Seules les heures constatées et validées servent au calcul des "
                             "vacations. Une séance planifiée mais non tenue n'ouvre aucun "
                             "droit à rémunération.",
                }),
            ],
        },
    ],
}

# ─────────────────────────────────────────────────────────────── PARTIE X
PARTIE_X = {
    "id": "partie-10",
    "numero": "X",
    "titre": "Finances et gestion administrative",
    "chapitres": [
        {
            "id": "ch-10-1",
            "titre": "Frais, factures et paiements",
            "profils": ["FINANCE", "ADMIN", "DIRECTION"],
            "blocs": [
                ("p", "Le module **Finances étudiantes** couvre l'ensemble du cycle "
                      "financier : définition des frais, émission des factures, "
                      "enregistrement des paiements, édition des reçus."),
                ("tableau", {
                    "entetes": ["Écran", "Usage"],
                    "lignes": [
                        ["Vue d'ensemble", "Synthèse de la situation financière"],
                        ["Frais de scolarité", "Définition des montants par formation et niveau"],
                        ["Factures", "Émission et suivi des factures"],
                        ["Paiements", "Enregistrement des règlements"],
                        ["Reçus", "Édition des justificatifs de paiement"],
                        ["Bourses & remboursements", "Gestion des aides et des remboursements"],
                        ["Situation financière", "Position d'un étudiant"],
                        ["Vacations & encadrants", "Rémunération des intervenants"],
                        ["Paramétrage finance", "Modes de paiement et règles de calcul"],
                    ],
                }),
                ("encadre", {
                    "type": "danger",
                    "titre": "La validation d'un paiement est irréversible",
                    "texte": "Un paiement validé modifie définitivement la situation "
                             "financière de l'étudiant. Vérifiez le montant, la référence et "
                             "le mode de règlement avant de valider.",
                }),
                ("h3", "Le circuit de validation"),
                ("p", "La saisie et la validation d'un paiement sont deux opérations "
                      "distinctes, confiées à des profils différents. Le validateur "
                      "financier ne saisit pas ; le caissier saisit mais ne valide pas."),
            ],
        },
        {
            "id": "ch-10-2",
            "titre": "Courriers, réunions et archives",
            "profils": ["SECRETARIAT", "ARCHIVE", "ADMIN"],
            "blocs": [
                ("p", "Le module **Administration** couvre la gestion documentaire "
                      "institutionnelle."),
                ("liste", [
                    "**Courrier / Documents** : enregistrement du courrier arrivé et "
                    "départ, affectation aux services.",
                    "**Réunions & missions** : ordres du jour, comptes rendus, ordres de "
                    "mission.",
                    "**Archives** : conservation et consultation des documents clos.",
                    "**Listes de notes archivées** et **cahiers d'appel archivés** : "
                    "consultation en lecture seule.",
                ]),
            ],
        },
    ],
}

# ─────────────────────────────────────────────────────────────── PARTIE XI
PARTIE_XI = {
    "id": "partie-11",
    "numero": "XI",
    "titre": "Autres modules",
    "chapitres": [
        {
            "id": "ch-11-1",
            "titre": "Stages et conventions",
            "profils": ["ADMIN", "SUPERVISEUR", "SECRETARIAT"],
            "blocs": [
                ("p", "Le module **Stages** suit le parcours de stage des étudiants, "
                      "depuis la convention jusqu'à l'évaluation finale."),
                ("tableau", {
                    "entetes": ["Écran", "Usage"],
                    "lignes": [
                        ["Conventions", "Établissement et suivi des conventions de stage"],
                        ["Structures d'accueil", "Répertoire des organismes partenaires"],
                        ["Affectations & tuteurs", "Rattachement étudiant / structure / tuteur"],
                        ["Suivi des stages", "Avancement et visites"],
                        ["Évaluations", "Notes de stage et appréciations"],
                    ],
                }),
            ],
        },
        {
            "id": "ch-11-2",
            "titre": "Statistiques et tableaux de bord",
            "profils": ["DIRECTION", "ADMIN", "STATISTICIEN"],
            "blocs": [
                ("p", "Le module **Statistiques** produit les indicateurs de pilotage de "
                      "l'institut. Chaque écran correspond à un thème d'analyse."),
                ("tableau", {
                    "entetes": ["Écran", "Indicateurs"],
                    "lignes": [
                        ["Candidatures", "Volumes par campagne, formation et statut"],
                        ["Admissions", "Taux d'admission et profils des admis"],
                        ["Inscriptions", "Effectifs inscrits par formation et niveau"],
                        ["Effectifs", "Répartition par genre, origine et statut"],
                        ["Résultats", "Taux de réussite par formation et semestre"],
                        ["Finances", "Recettes, impayés et taux de recouvrement"],
                        ["Rapports", "Rapports consolidés et exports"],
                        ["Alertes & seuils", "Dépassements des seuils configurés"],
                    ],
                }),
                ("figure", {"image": "10-stats-ensemble.png",
                            "titre": "Tableau de bord statistique",
                            "legende": "Les indicateurs sont calculés à partir des données "
                                       "réelles de l'application. Les filtres permettent "
                                       "de restreindre la période et le périmètre."}),
                ("figure", {"image": "11-stats-alertes.png",
                            "titre": "Alertes et seuils",
                            "legende": "Les seuils sont paramétrables. Lorsqu'un indicateur "
                                       "franchit un seuil, l'alerte apparaît sur le "
                                       "tableau de bord."}),
            ],
        },
        {
            "id": "ch-11-3",
            "titre": "Patrimoine et espaces",
            "profils": ["ADMIN", "DIRECTION"],
            "blocs": [
                ("p", "Le module **Patrimoine** recense les biens, les espaces et leurs "
                      "réservations. Il alimente la planification des salles."),
                ("p", "Les écrans **Salles & espaces** du module GET-INJS s'appuient sur ce "
                      "référentiel : une salle non enregistrée ne peut pas être affectée à "
                      "une séance."),
            ],
        },
        {
            "id": "ch-11-4",
            "titre": "Exports et paramètres",
            "profils": ["ADMIN", "DIRECTION"],
            "blocs": [
                ("p", "Le module **Exports de données** permet de produire des fichiers "
                      "exploitables (tableurs) à partir des données de l'application. "
                      "Les exports sensibles sont réservés et journalisés."),
                ("p", "Le module **Paramètres généraux** regroupe les réglages transverses : "
                      "fonctionnalités activables, politique de sécurité, paramètres de "
                      "badgeage."),
                ("encadre", {
                    "type": "attention",
                    "titre": "Un export sort du système",
                    "texte": "Un fichier exporté n'est plus protégé par les contrôles "
                             "d'accès de l'application. Rangez-le dans un emplacement "
                             "maîtrisé et ne le transmettez qu'aux destinataires habilités.",
                }),
            ],
        },
    ],
}

# ─────────────────────────────────────────────────────────────── PARTIE XII
PARTIE_XII = {
    "id": "partie-12",
    "numero": "XII",
    "titre": "Assistance et résolution des problèmes",
    "chapitres": [
        {
            "id": "ch-12-1",
            "titre": "Difficultés de connexion",
            "profils": ["tous"],
            "blocs": [
                ("problemes", [
                    {
                        "symptome": "Le message « identifiants incorrects » s'affiche alors "
                                    "que le mot de passe semble correct.",
                        "cause": "Erreur de saisie (majuscules, clavier), ou mot de passe "
                                 "réinitialisé par l'administration.",
                        "verification": "Vérifiez le verrouillage des majuscules et essayez "
                                        "de saisir le mot de passe dans un champ texte pour "
                                        "le relire.",
                        "solution": "Réessayez. Si l'échec persiste, demandez la "
                                    "réinitialisation à l'administrateur.",
                        "contact": "Administrateur de la plateforme",
                    },
                    {
                        "symptome": "Le message « accès non autorisé » apparaît.",
                        "cause": "Votre rôle ne dispose pas de l'accès web — cas des "
                                 "profils Formateur et Étudiant.",
                        "verification": "Demandez à l'administrateur quel rôle est "
                                        "réellement rattaché à votre compte.",
                        "solution": "Utilisez l'application mobile. Si un accès web est "
                                    "nécessaire, l'administrateur doit attribuer le rôle "
                                    "correspondant.",
                        "contact": "Administrateur de la plateforme",
                    },
                    {
                        "symptome": "L'application renvoie sans cesse à l'écran de "
                                    "changement de mot de passe.",
                        "cause": "Le compte est marqué « changement obligatoire ».",
                        "verification": "Aucune : c'est le comportement attendu.",
                        "solution": "Changez le mot de passe ; l'accès normal est rétabli "
                                    "immédiatement après.",
                        "contact": "—",
                    },
                ]),
            ],
        },
        {
            "id": "ch-12-2",
            "titre": "Difficultés d'utilisation",
            "profils": ["tous"],
            "blocs": [
                ("problemes", [
                    {
                        "symptome": "Un module est absent de la barre latérale.",
                        "cause": "Le rôle du compte ne donne pas accès à ce module.",
                        "verification": "Consultez votre fiche de profil dans ce manuel.",
                        "solution": "Si l'accès est légitime, l'administrateur doit "
                                    "attribuer le rôle ; sinon, sollicitez un collègue "
                                    "habilité.",
                        "contact": "Administrateur de la plateforme",
                    },
                    {
                        "symptome": "Un bouton est visible mais son clic échoue.",
                        "cause": "Le bouton est visible mais la permission précise manque "
                                 "au périmètre du compte.",
                        "verification": "Notez le message exact affiché par l'application.",
                        "solution": "Transmettez le message à l'administrateur : il indique "
                                    "précisément la permission manquante.",
                        "contact": "Administrateur de la plateforme",
                    },
                    {
                        "symptome": "Une donnée attendue est introuvable.",
                        "cause": "Filtres actifs, ou donnée hors de votre périmètre.",
                        "verification": "Réinitialisez les filtres et vérifiez l'année "
                                        "académique sélectionnée.",
                        "solution": "Si la donnée reste introuvable, vérifiez qu'elle existe "
                                    "bien dans le périmètre de votre service.",
                        "contact": "Responsable de votre service",
                    },
                    {
                        "symptome": "Une validation échoue sans explication claire.",
                        "cause": "Une règle métier bloque l'opération (pièce manquante, "
                                 "état incompatible, dépendance).",
                        "verification": "Lisez le message : il nomme généralement l'élément "
                                        "bloquant.",
                        "solution": "Corrigez l'élément signalé, puis relancez l'opération.",
                        "contact": "Administrateur de la plateforme",
                    },
                ]),
            ],
        },
        {
            "id": "ch-12-3",
            "titre": "Difficultés techniques",
            "profils": ["tous"],
            "blocs": [
                ("problemes", [
                    {
                        "symptome": "La session expire pendant le travail.",
                        "cause": "Inactivité prolongée ou jeton de sécurité expiré.",
                        "verification": "Aucune : comportement normal de sécurité.",
                        "solution": "Reconnectez-vous. Enregistrez régulièrement pour ne "
                                    "rien perdre.",
                        "contact": "—",
                    },
                    {
                        "symptome": "Un export produit un fichier vide ou incomplet.",
                        "cause": "Aucune donnée ne correspond aux filtres, ou l'export a "
                                 "été interrompu.",
                        "verification": "Vérifiez le nombre de lignes affichées à l'écran "
                                        "avant l'export.",
                        "solution": "Élargissez les filtres puis relancez l'export.",
                        "contact": "Administrateur de la plateforme",
                    },
                    {
                        "symptome": "La génération d'un emploi du temps échoue.",
                        "cause": "Données d'entrée incomplètes : volumes horaires, "
                                 "effectifs, salles ou disponibilités.",
                        "verification": "Consultez l'écran **Audit des données** : il liste "
                                        "les anomalies bloquantes.",
                        "solution": "Complétez les référentiels manquants, puis relancez.",
                        "contact": "Responsable pédagogique",
                    },
                    {
                        "symptome": "Un badgeage n'est pas reconnu.",
                        "cause": "QR code expiré, hors zone, ou séance déjà clôturée.",
                        "verification": "Contrôlez l'heure du badgeage et l'état de la "
                                        "séance.",
                        "solution": "L'enseignant peut procéder à un émargement manuel, "
                                    "tracé comme tel.",
                        "contact": "Enseignant de la séance",
                    },
                    {
                        "symptome": "La page affiche une erreur bloquante.",
                        "cause": "Incident passager ou défaut de chargement.",
                        "verification": "Rechargez la page.",
                        "solution": "Si l'erreur persiste, notez le message et l'heure, puis "
                                    "signalez-le.",
                        "contact": "Service informatique",
                    },
                ]),
            ],
        },
    ],
}
