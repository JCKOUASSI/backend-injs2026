"""Catalogue des modules et des permissions atomiques (annexe A3).

Convention de code des permissions : ``<module>.<ressource>.<action>``.

* ``JOKER`` représente le joker ``<ressource>.*`` du recueil : il est expansé
  en les treize verbes canoniques lors du chargement ;
* les autres lignes énumèrent exactement les verbes métier écrits en A3
  (dont les verbes ajoutés à l'énumération ``PermissionMetier.Action``) ;
* ``NIVEAU_VERBE`` donne le niveau N0–N4 minimal de chaque verbe ; c'est lui
  qui transforme la matrice par niveaux (A2) en permissions atomiques.
"""

# Les treize verbes canoniques du modèle fonctionnel de référence.
VERBES_CANONIQUES = (
    'consulter', 'creer', 'modifier', 'soumettre', 'valider', 'rejeter',
    'publier', 'annuler', 'exporter', 'imprimer', 'archiver', 'supprimer',
    'administrer',
)
JOKER = '*'

# Niveau minimal (0–4) requis pour chaque verbe. N0 = consultation très
# limitée (uniquement dans un périmètre PROPRE_COMPTE).
NIVEAU_VERBE = {
    # N0 / N1 — lecture et production de documents.
    'consulter': 0,
    'imprimer': 1,
    'exporter': 1,
    'generer': 1,
    # N2 — saisie et traitement.
    'creer': 2,
    'modifier': 2,
    'soumettre': 2,
    'saisir': 2,
    'editer': 2,
    'deposer': 2,
    'deplacer': 2,
    'remplacer': 2,
    'ouvrir': 2,
    'calculer': 2,
    # N3 — validation et décision.
    'valider': 3,
    'rejeter': 3,
    'publier': 3,
    'annuler': 3,
    'signer': 3,
    'verrouiller': 3,
    'instruire': 3,
    'decider': 3,
    'certifier': 3,
    'cloturer': 3,
    'resoudre': 3,
    # N4 — administration et actes sensibles.
    'supprimer': 4,
    'archiver': 4,
    'administrer': 4,
    'configurer': 4,
    'forcer': 4,
}

#: module du catalogue → (libellé, application Django correspondante ou ''
#: pour le module interne, module conditionnel selon la MOA).
MODULES = {
    'administration': ("Administration des habilitations", 'habilitations', False),
    'candidatures': ("Candidatures et concours", 'admissions', False),
    'scolarite': ("Scolarité", 'scolarite', False),
    'pedagogie': ("Pédagogie, maquettes et UE/ECUE", 'scolarite', False),
    'enseignants': ("Enseignants et charges", 'scolarite', False),
    'evaluations': ("Évaluations et notes", 'suiviEvaluation', False),
    'jurys': ("Jurys et délibérations", 'jurys', False),
    'diplomation': ("Graduation et diplômation", 'graduation', False),
    'finances_etud': ("Finances étudiantes", 'finances_etudiantes', True),
    'finances_form': ("Rémunération et vacations des formateurs", 'formations', False),
    'stages': ("Stages et conventions", 'stages', True),
    'rh': ("Ressources humaines", 'ressources_humaines', True),
    'patrimoine': ("Patrimoine, espaces et réservations", 'patrimoine', True),
    'edt': ("Emplois du temps", 'edts', False),
    'presences': ("Présences et émargements", 'presences', False),
    'administrations': ("Courriers et documents administratifs", 'administrations', True),
    'statistiques': ("Statistiques et rapports", 'statistiques', False),
    'exports': ("Exports de données", 'exports', False),
    'parametres': ("Paramètres généraux", 'parametres', False),
    'referentiels': ("Référentiels", 'referentiels', False),
}

#: Ressources et verbes explicites de chaque module (annexe A3). Un joker
#: ``JOKER`` est expansé en les treize verbes canoniques.
RESSOURCES = {
    'administration': {
        'compte': JOKER, 'personne': JOKER, 'role': JOKER,
        'permission': JOKER, 'attribution': JOKER, 'derogation': JOKER,
        'delegation': JOKER, 'politique': JOKER, 'revue': JOKER,
        'journal': ['consulter', 'exporter'],
    },
    'candidatures': {
        'campagne': JOKER, 'candidat': JOKER, 'candidature': JOKER,
        'piece': ['consulter', 'valider', 'rejeter'],
        'eligibilite': ['valider'],
        'concours': JOKER, 'epreuve': JOKER, 'surveillance': JOKER,
        'convocation': JOKER, 'note_concours': JOKER,
        'classement': ['calculer', 'publier'],
    },
    'scolarite': {
        'annee': JOKER, 'dossier_etudiant': JOKER,
        'inscription_administrative': JOKER,
        'inscription_pedagogique': JOKER, 'groupe': JOKER,
        'affectation_groupe': JOKER, 'transfert': JOKER,
        'reorientation': JOKER, 'equivalence': JOKER,
        'journal_scolarite': ['consulter'],
    },
    'pedagogie': {
        'maquette': ['consulter', 'creer', 'modifier', 'valider', 'verrouiller'],
        'ue': JOKER, 'ecue': JOKER, 'volume_horaire': JOKER,
        'credit_ects': JOKER, 'affectation_pedagogique': JOKER,
        'passerelle': JOKER,
    },
    'enseignants': {
        'enseignant': JOKER, 'specialite': JOKER, 'disponibilite': JOKER,
        'indisponibilite': JOKER,
        'charge': ['consulter', 'modifier', 'valider'],
    },
    'evaluations': {
        'colonne_note': JOKER,
        'note': ['consulter', 'saisir', 'modifier', 'valider', 'verrouiller'],
        'correction_note': JOKER,
        'moyenne': ['calculer', 'publier'],
        'questionnaire': JOKER, 'decision_pedagogique': JOKER,
    },
    'jurys': {
        'session_jury': JOKER, 'membre_jury': JOKER, 'proposition': JOKER,
        'deliberation': JOKER, 'decision': JOKER,
        'pv': ['generer', 'signer', 'publier'],
        'resultat': ['publier'],
    },
    'diplomation': {
        'diplome': ['consulter', 'creer', 'valider', 'editer', 'revoquer'],
        'reedition': JOKER,
        'registre': ['consulter', 'administrer'],
        'attestation': JOKER, 'releve_notes': JOKER, 'modele_document': JOKER,
    },
    'finances_etud': {
        'tarification': JOKER, 'echeancier': JOKER, 'facture': JOKER,
        'paiement': ['saisir', 'valider'],
        'quittance': ['editer'],
        'remboursement': JOKER, 'relance': JOKER, 'rapprochement': JOKER,
    },
    'finances_form': {
        'parametrage': JOKER,
        'ajustement': ['saisir', 'valider', 'rejeter'],
        'heures_certifiees': ['consulter'],
        'etat_vacation': ['editer'],
    },
    'stages': {
        'organisme': JOKER, 'tuteur': JOKER,
        'convention': ['creer', 'valider', 'signer'],
        'evaluation_stage': JOKER,
        'attestation_stage': ['editer'],
    },
    'rh': {
        'service': JOKER, 'fonction': JOKER, 'agent': JOKER,
        'affectation_rh': JOKER, 'disponibilite_agent': JOKER,
        'document_rh': ['consulter', 'deposer', 'administrer'],
    },
    'patrimoine': {
        'equipement': JOKER, 'vehicule': JOKER, 'inventaire': JOKER,
        'maintenance': JOKER, 'mouvement': JOKER,
        'espace': ['consulter', 'modifier'],
        'reservation': ['creer', 'valider'],
    },
    'edt': {
        'calendrier': JOKER, 'creneau': JOKER, 'besoin': JOKER,
        'contrainte': JOKER, 'rattrapage': JOKER, 'examen': JOKER,
        'emploi_du_temps': ['creer', 'generer', 'valider', 'publier'],
        'seance': ['creer', 'deplacer', 'annuler', 'remplacer'],
        'conflit': ['resoudre'],
    },
    'presences': {
        'seance_emargement': ['ouvrir', 'cloturer'],
        'qr': ['generer'],
        'emargement': ['consulter', 'saisir', 'forcer'],
        'justificatif': ['deposer', 'instruire', 'decider'],
        'presence_intervenant': JOKER, 'cahier_texte': JOKER,
        'heures': ['certifier'],
    },
    'administrations': {
        'courrier': JOKER, 'document_officiel': JOKER,
        'version_document': JOKER, 'reunion': JOKER, 'mission': JOKER,
        # Lot A refonte — organigramme unifié (modèle 13).
        'organigramme': ['consulter', 'gerer'],
    },
    'statistiques': {
        'indicateur': ['consulter'],
        'rapport': ['generer', 'publier'],
        'alerte': ['configurer'],
        'bilan': ['editer'],
        'tableau_bord': ['consulter'],
    },
    'exports': {
        'export': ['generer', 'imprimer'],
        'export_sensible': ['generer'],
    },
    'parametres': {
        'parametre': ['consulter', 'modifier', 'administrer'],
    },
    'referentiels': {
        'referentiel': ['consulter', 'creer', 'modifier', 'archiver'],
    },
}

#: Permissions CRITIques (annexe A3) : motif obligatoire, double validation,
#: journalisation renforcée. Les jokers sont résolus en codes concrets ici
#: quand l'acte sensible est décrit (ex. ``remboursement.valider``).
PERMISSIONS_CRITIQUES = frozenset({
    'administration.role.creer',
    'administration.role.modifier',
    'administration.attribution.valider',
    'administration.compte.modifier',
    'evaluations.note.verrouiller',
    'jurys.pv.signer',
    'jurys.resultat.publier',
    'diplomation.diplome.valider',
    'diplomation.diplome.revoquer',
    'finances_etud.paiement.valider',
    'finances_etud.remboursement.valider',
    'presences.emargement.forcer',
    'edt.emploi_du_temps.publier',
    'parametres.parametre.administrer',
    'exports.export_sensible.generer',
})

#: Permissions sensibles au motif (toutes les permissions critiques, plus les
#: créations d'octrois) : ``necessite_motif=True``.
PERMISSIONS_AVEC_MOTIF = frozenset(PERMISSIONS_CRITIQUES | {
    'administration.derogation.creer',
    'administration.delegation.creer',
    'administration.attribution.creer',
    'finances_etud.paiement.saisir',
})

#: Actes d'auto-démarche des usagers sur LEUR propre dossier (les niveaux A2
#: sont N0/N1 mais ces actes sont des soumissions rendues possibles par le
#: périmètre ``PROPRE_COMPTE``).
PERMISSIONS_USAGERS = {
    'ETUDIANT': (
        'presences.justificatif.deposer',
        'presences.emargement.consulter',
    ),
    'CANDIDAT': (
        'candidatures.candidat.consulter',
        'candidatures.candidature.creer',
        'candidatures.candidature.modifier',
        'candidatures.candidature.soumettre',
        'candidatures.piece.consulter',
    ),
}
