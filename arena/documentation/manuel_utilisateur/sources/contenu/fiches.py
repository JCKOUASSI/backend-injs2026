"""Génération des fiches utilisateurs par profil.

Chaque fiche est construite à partir de `profils.json` (écrans réellement
visibles) et des capacités backend vérifiées dans `authentication/role_groups.py`.
Aucune autorisation n'est supposée : les actions listées découlent du ROLE_POLICY
relevé dans le code.
"""
from __future__ import annotations

from socle import LISTE_PROFILS, SECTIONS

# Actions réellement ouvertes par ROLE_POLICY (authentication/role_groups.py)
POLITIQUE = {
    "ADMIN": {"apps": "Toutes (authentication, formations, presences, exports)",
              "actions": "Consulter, créer, modifier, supprimer",
              "special": ["Accès web", "Accès opérationnel", "Gestion des comptes",
                          "Périmètre global", "Gestion des questionnaires",
                          "Gestion des notes", "Validation des décisions",
                          "Consultation des évaluations"]},
    "CHEF_INJS_ADMIN": {"apps": "Toutes (authentication, formations, presences, exports)",
                        "actions": "Consulter, créer, modifier, supprimer",
                        "special": ["Accès web", "Accès opérationnel", "Gestion des comptes",
                                    "Périmètre global", "Gestion des questionnaires",
                                    "Gestion des notes", "Validation des décisions",
                                    "Consultation des évaluations"]},
    "INJS_ADMIN": {"apps": "Toutes (authentication, formations, presences, exports)",
                   "actions": "Consulter, créer, modifier, supprimer",
                   "special": ["Accès web", "Accès opérationnel", "Gestion des comptes",
                               "Périmètre global", "Gestion des questionnaires",
                               "Gestion des notes", "Validation des décisions",
                               "Consultation des évaluations"]},
    "DIRECTION": {"apps": "Toutes (authentication, formations, presences, exports)",
                  "actions": "Consulter uniquement",
                  "special": ["Accès web", "Accès opérationnel", "Périmètre global",
                              "Validation des décisions", "Consultation des évaluations"]},
    "CHEF_SECRETARIAT": {"apps": "formations, presences, suiviEvaluation",
                         "actions": "Consulter, créer, modifier, supprimer",
                         "special": ["Accès web", "Accès opérationnel",
                                     "Gestion des comptes", "Liste des participants",
                                     "Gestion des questionnaires", "Gestion des notes",
                                     "Validation des décisions",
                                     "Consultation des évaluations"]},
    "SECRETARIAT": {"apps": "formations, presences, suiviEvaluation",
                    "actions": "Consulter, créer, modifier, supprimer",
                    "special": ["Accès web", "Accès opérationnel",
                                "Gestion des comptes", "Liste des participants",
                                "Gestion des questionnaires", "Gestion des notes",
                                "Validation des décisions",
                                "Consultation des évaluations"]},
    "FINANCE": {"apps": "formations, presences, exports",
                "actions": "Consulter uniquement",
                "special": ["Accès web", "Module finance",
                            "Consultation des évaluations"]},
    "ARCHIVE": {"apps": "Toutes (authentication, formations, presences, exports) "
                        "+ suiviEvaluation",
                "actions": "Consulter uniquement",
                "special": ["Accès web", "Accès opérationnel", "Périmètre global",
                            "Liste des participants", "Consultation des évaluations"]},
    "ENCADRANT": {"apps": "formations, presences, suiviEvaluation",
                  "actions": "Consulter, créer, modifier, supprimer",
                  "special": ["Accès web", "Accès opérationnel",
                              "Liste des participants", "Gestion des questionnaires",
                              "Gestion des notes", "Validation des décisions",
                              "Consultation des évaluations"]},
    "SUPERVISEUR": {"apps": "suiviEvaluation",
                    "actions": "Consulter, créer, modifier, supprimer",
                    "special": ["Accès web", "Accès opérationnel",
                                "Gestion des questionnaires", "Gestion des notes",
                                "Validation des décisions",
                                "Consultation des évaluations"]},
    "FORMATEUR": {"apps": "formations, presences",
                  "actions": "Consulter uniquement",
                  "special": []},
    "AUDITEUR": {"apps": "formations, presences",
                 "actions": "Consulter uniquement",
                 "special": []},
}

#: Interdits notables, déduits de l'absence de capacité dans ROLE_POLICY.
INTERDITS = {
    "FINANCE": ["Saisir ou valider des notes", "Inscrire un étudiant",
                "Créer ou modifier un compte", "Gérer les emplois du temps"],
    "ARCHIVE": ["Créer, modifier ou supprimer une donnée métier",
                "Saisir des notes", "Enregistrer un paiement"],
    "ENCADRANT": ["Intervenir hors de ses propres ECUE",
                  "Valider les délibérations d'un jury",
                  "Modifier les référentiels de formation"],
    "SUPERVISEUR": ["Saisir des notes à la place d'un enseignant",
                    "Valider un procès-verbal de jury",
                    "Gérer les comptes utilisateurs"],
    "SECRETARIAT": ["Valider les délibérations d'un jury",
                    "Attribuer des rôles sur des comptes",
                    "Intervenir hors de son secrétariat"],
    "CHEF_SECRETARIAT": ["Attribuer des rôles sur des comptes",
                         "Intervenir hors de son secrétariat"],
    "DIRECTION": ["Saisir une note", "Enregistrer un paiement",
                  "Créer un compte utilisateur", "Modifier une maquette"],
    "FORMATEUR": ["Accéder à l'interface web", "Consulter les dossiers d'autres "
                  "enseignants", "Modifier une note après verrouillage"],
    "AUDITEUR": ["Accéder à l'interface web", "Consulter les notes d'autres étudiants",
                 "Modifier son propre dossier"],
}

#: Cas pratiques représentatifs par profil.
CAS = {
    "ADMIN": [
        ("Créer un compte pour un nouvel agent de scolarité",
         "Le service scolarité accueille un agent. Il doit saisir les inscriptions du "
         "secrétariat Sciences et Techniques des Activités Physiques et Sportives.",
         ["Utilisateurs & Accès › Comptes utilisateurs › Nouveau compte",
          "Renseigner l'identité et le courriel professionnel",
          "Rôle : Secrétariat · Rattachement : le secrétariat concerné",
          "Valider, puis demander à l'agent de changer son mot de passe à la première "
          "connexion"]),
        ("Vérifier qui a modifié une note",
         "Un étudiant conteste une note modifiée après délibération.",
         ["Audit & Traçabilité › Modifications",
          "Filtrer par ECUE et par période",
          "Identifier l'auteur, l'horodatage et les valeurs avant/après",
          "Exporter la trace pour constitution du dossier"]),
    ],
    "CHEF_INJS_ADMIN": [
        ("Superviser la clôture d'une année académique",
         "Fin d'année : le chef du service administration contrôle la cohérence globale.",
         ["Statistiques › Effectifs : contrôler les inscrits par formation",
          "Scolarité › Journal de scolarité : vérifier les opérations de masse",
          "Évaluations › Résultats : s'assurer que toutes les notes sont verrouillées",
          "Jurys › Validation : contrôler que les délibérations sont validées",
          "Diplômation › Éligibilité : examiner la liste des diplômables"]),
    ],
    "DIRECTION": [
        ("Suivre les effectifs de la rentrée",
         "La direction souhaite un point d'étape sur les inscriptions à la rentrée.",
         ["Statistiques › Inscriptions",
          "Sélectionner l'année académique en cours",
          "Comparer par formation et par niveau",
          "Exporter le rapport pour le conseil de direction"]),
        ("Valider la liste des diplômés",
         "Le jury a délibéré ; la direction doit autoriser l'édition des diplômes.",
         ["Diplômation › Éligibilité",
          "Contrôler la liste proposée",
          "Vérifier que les délibérations sont validées",
          "Autoriser l'édition depuis Diplômes"]),
    ],
    "SECRETARIAT": [
        ("Inscrire un étudiant admis",
         "Un candidat admis se présente pour son inscription administrative.",
         ["Scolarité › Inscriptions",
          "Rechercher l'étudiant par nom ou numéro de dossier",
          "Choisir la formation, le niveau et l'année",
          "Contrôler les pièces et la situation financière",
          "Enregistrer : l'inscription est en attente de validation"]),
        ("Éditer une attestation d'inscription",
         "L'étudiant demande une attestation pour une démarche administrative.",
         ["Scolarité › Documents scolaires",
          "Rechercher l'étudiant",
          "Vérifier que l'inscription est validée",
          "Générer et imprimer le document"]),
    ],
    "ENCADRANT": [
        ("Saisir les notes d'une ECUE",
         "Fin de semestre : l'enseignant doit saisir les notes de son ECUE.",
         ["Évaluations › Saisie des notes",
          "Sélectionner formation, niveau, semestre et ECUE",
          "Saisir les notes étudiant par étudiant",
          "Enregistrer, puis contrôler la liste",
          "Signaler au responsable pédagogique pour verrouillage"]),
        ("Émarger une séance sans QR",
         "L'enseignant n'a pas pu projeter le QR code.",
         ["Présences QR › Séances",
          "Ouvrir la séance du jour",
          "Utiliser l'émargement manuel",
          "Marquer présents, retards et absents",
          "Clôturer la séance"]),
    ],
    "FINANCE": [
        ("Enregistrer un paiement",
         "Un étudiant règle ses frais de scolarité par mobile money.",
         ["Finances étudiantes › Paiements",
          "Rechercher l'étudiant",
          "Saisir le montant et le mode de règlement",
          "Enregistrer : le paiement est saisi, non validé",
          "Le validateur financier procède à la validation"]),
        ("Produire un état des impayés",
         "Le service souhaite relancer les étudiants débiteurs.",
         ["Finances étudiantes › Situation financière",
          "Filtrer sur les soldes non nuls",
          "Exporter la liste",
          "Transmettre au service de recouvrement"]),
    ],
    "ARCHIVE": [
        ("Retrouver une liste de notes d'une année révolue",
         "Un ancien étudiant demande une attestation de résultats.",
         ["Archives › Listes de notes archivées",
          "Filtrer par année et par formation",
          "Ouvrir le document",
          "Communiquer l'extrait selon la procédure en vigueur"]),
    ],
    "SUPERVISEUR": [
        ("Préparer l'emploi du temps d'un semestre",
         "Le responsable pédagogique doit planifier le semestre à venir.",
         ["GET INJS APP › Étudiants inscrits : vérifier la population",
          "Dimensionnement : contrôler volumes et effectifs",
          "Saisir les disponibilités des enseignants",
          "Génération : lancer le calcul",
          "Conflits & contraintes : corriger les incompatibilités",
          "Faire valider puis publier"]),
    ],
    "CHEF_SECRETARIAT": [
        ("Valider les inscriptions du secrétariat",
         "Les inscriptions saisies par les agents doivent être validées.",
         ["Scolarité › Inscriptions",
          "Filtrer sur l'état « en attente de validation »",
          "Contrôler chaque dossier : pièces, formation, année",
          "Valider les dossiers conformes",
          "Renvoyer les dossiers incomplets avec motif"]),
    ],
    "INJS_ADMIN": [
        ("Contrôler la cohérence des maquettes",
         "Avant la rentrée, l'administration vérifie les maquettes LMD.",
         ["Scolarité › Maquettes LMD",
          "Ouvrir chaque maquette par formation et niveau",
          "Contrôler le total de crédits par semestre (30 ECTS)",
          "Vérifier les volumes horaires des ECUE",
          "Corriger ou faire corriger les écarts"]),
    ],
    "FORMATEUR": [
        ("Badger une séance depuis le mobile",
         "Le formateur assure une séance et doit enregistrer les présences.",
         ["Ouvrir l'application mobile INJS",
          "Se connecter avec ses identifiants",
          "Sélectionner la séance du jour",
          "Afficher le QR code pour les étudiants",
          "Clôturer la séance en fin de cours"]),
    ],
    "AUDITEUR": [
        ("Badger sa présence",
         "L'étudiant arrive en cours et doit signaler sa présence.",
         ["Ouvrir l'application mobile INJS",
          "Se connecter avec son identifiant étudiant",
          "Scanner le QR code affiché par l'enseignant",
          "Vérifier que la présence est enregistrée"]),
    ],
}

#: Erreurs fréquentes propres à chaque profil.
ERREURS = {
    "ADMIN": [
        ("Un nouveau compte n'a accès à rien",
         "Le rôle a été attribué mais aucun périmètre n'a été défini. Renseignez le "
         "secrétariat, la formation ou le parcours attendu."),
        ("Une attribution de rôle débloque trop de droits",
         "Consultez systématiquement l'écran « Impact d'un rôle » avant de valider."),
    ],
    "SECRETARIAT": [
        ("L'inscription enregistrée n'apparaît pas dans les effectifs",
         "L'inscription est en attente de validation. Elle ne compte qu'après validation "
         "par le chef de secrétariat."),
        ("Un document officiel est refusé à l'édition",
         "L'inscription n'est pas validée, ou une pièce obligatoire manque."),
    ],
    "ENCADRANT": [
        ("La saisie des notes est bloquée",
         "Les notes sont verrouillées, ou l'ECUE ne relève pas de votre périmètre. "
         "Contactez le responsable pédagogique."),
        ("Le QR code n'est pas reconnu par les étudiants",
         "La séance est clôturée ou le jeton a expiré. Réouvrez la séance ou passez à "
         "l'émargement manuel."),
    ],
    "FINANCE": [
        ("Un paiement reste « saisi » et ne s'applique pas",
         "C'est le comportement normal : la validation est une opération distincte, "
         "réservée au validateur financier."),
        ("Un reçu ne peut pas être édité",
         "Le paiement n'est pas validé. Le reçu n'est disponible qu'après validation."),
    ],
    "SUPERVISEUR": [
        ("La génération échoue systématiquement",
         "Les données d'entrée sont incomplètes. Consultez l'écran d'audit des données : "
         "il liste les blocages un par un."),
        ("Un emploi du temps modifié ne s'affiche pas pour les étudiants",
         "Les modifications d'un emploi du temps doivent être republiées pour être "
         "visibles."),
    ],
    "DIRECTION": [
        ("Un indicateur statistique semble faux",
         "Vérifiez l'année académique sélectionnée en haut de l'écran : le filtre "
         "conditionne tous les calculs."),
    ],
    "ARCHIVE": [
        ("Un document archivé est introuvable",
         "Le filtre d'année ou de formation est trop restrictif. Élargissez la recherche."),
    ],
    "CHEF_SECRETARIAT": [
        ("Une validation est refusée",
         "Le dossier est incomplet, ou l'utilisateur tente de valider sa propre saisie "
         "(séparation des tâches)."),
    ],
    "INJS_ADMIN": [
        ("Le total de crédits d'un semestre n'atteint pas 30",
         "Une UE manque ou ses crédits sont mal saisis. Corrigez la maquette avant "
         "publication."),
    ],
    "FORMATEUR": [
        ("La connexion web est refusée",
         "C'est le comportement attendu : ce profil n'a pas l'accès web. Utilisez "
         "l'application mobile."),
    ],
    "AUDITEUR": [
        ("La connexion web est refusée",
         "C'est le comportement attendu : ce profil n'a pas l'accès web. Utilisez "
         "l'application mobile."),
        ("Le badgeage est refusé",
         "Le QR code a expiré ou vous êtes hors de la zone autorisée."),
    ],
}


def _sections_du_profil(menus):
    vus = {}
    for m in menus:
        vus.setdefault(m["section"], []).append(m)
    return vus


def construire_fiches():
    """Retourne la liste des fiches, dans l'ordre de `profils.json`."""
    fiches = []
    for p in LISTE_PROFILS:
        code = p["code"]
        pol = POLITIQUE.get(code, {"apps": "—", "actions": "—", "special": []})
        par_section = _sections_du_profil(p["menus"])
        fiches.append({
            "code": code,
            "nom": p["nom"],
            "fonction": p["fonction"],
            "famille": p["famille"],
            "description": p["desc"],
            "web": p["web"],
            "niveaux": p["niveaux"],
            "ecrans_visibles": p["ecrans_visibles"],
            "apps": pol["apps"],
            "actions": pol["actions"],
            "capacites": pol["special"],
            "interdits": INTERDITS.get(code, []),
            "cas": CAS.get(code, []),
            "erreurs": ERREURS.get(code, []),
            "sections": sorted(par_section.items(), key=lambda kv: kv[0]),
        })
    return fiches
