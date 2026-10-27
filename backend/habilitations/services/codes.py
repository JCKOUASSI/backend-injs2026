"""Constantes publiques du moteur d'autorisation (unité U2).

Ce module ne contient QUE des données sans dépendance ORM lourde : modes
d'exploitation, codes de motif stables (ils font partie du contrat d'API et
sont repris tels quels par les journaux et l'API REST) et la hiérarchie de
largeur des périmètres servant à borner les dérogations.
"""
from ..models import Perimetre

# Modes d'exploitation du dispositif.
MODE_OFF = 'OFF'
MODE_OBSERVATION = 'OBSERVATION'
MODE_APPLICATION = 'APPLICATION'
MODES = (MODE_OFF, MODE_OBSERVATION, MODE_APPLICATION)

#: Libellés en français des codes de motif (contrat d'API stable).
LIBELLES_MOTIFS = {
    'NON_AUTHENTIFIE': "Aucune session authentifiée.",
    'PERMISSION_INCONNUE': "La permission demandée n'existe pas dans le référentiel.",
    'COMPTE_INVITE': "Le compte est à l'état d'invité, non activé.",
    'COMPTE_SUSPENDU': "Le compte est suspendu.",
    'COMPTE_DESACTIVE': "Le compte est désactivé.",
    'COMPTE_VERROUILLE': "Le compte est verrouillé.",
    'COMPTE_EXPIRE': "Le compte est expiré.",
    'COMPTE_EXPIRATION_ATTEINTE': "La date d'expiration du compte est atteinte.",
    'CANAL_NON_AUTORISE': "Le canal demandé n'est pas autorisé pour ce compte.",
    'CANAL_IMPOSE_PAR_ROLE': "Un rôle attribué impose un autre canal d'accès.",
    'MFA_REQUIS_NON_ACTIF': "Un rôle ou la politique impose l'authentification multifacteur, non active sur le compte.",
    'AUCUNE_ATTRIBUTION_PERMETTANTE': "Aucune attribution active n'octroie cette permission.",
    'MODULE_REQUIS_ABSENT': "Le module métier requis par le rôle n'est pas installé.",
    'ROLE_SENSIBLE_SANS_SECONDE_SIGNATURE': "Le rôle est sensible et l'attribution n'a pas reçu de seconde signature.",
    'ROLES_INCOMPATIBLES': "Deux rôles actifs sont incompatibles (séparation des tâches).",
    'NIVEAU_INSUFFISANT': "Le niveau effectif de l'attribution est inférieur au niveau exigé.",
    'PERIMETRE_SECRETARIAT_MANQUANT': "Le rôle relève d'un secrétariat mais aucun périmètre de secrétariat n'est attaché.",
    'DEROGATION_SANS_DATE_FIN': "Une dérogation d'octroi doit être bornée par une date de fin.",
    'DEROGATION_TROP_LONGUE': "La dérogation dépasse la durée maximale prévue par la politique de sécurité.",
    'DEROGATION_PERIODE_INCOHERENTE': "La période de la dérogation est incohérente (fin avant début).",
    'DEROGATION_SANS_SECONDE_SIGNATURE': "La dérogation sur une permission critique n'a pas reçu de seconde signature.",
    'DEROGATION_HORS_PORTEE_MAXIMALE': "La dérogation excède la portée maximale de la permission.",
    'PERMISSION_RETIREE': "La permission a été explicitement retirée par une dérogation active.",
    'CIBLE_HORS_PERIMETRE': "Aucun octroi actif ne couvre la cible demandée.",
    'DELEGATION_HORS_PERIODE': "La délégation n'est pas dans sa période de validité.",
    'DELEGATION_NON_SIGNEE': "La délégation d'une permission critique n'a pas reçu de seconde signature.",
    'DELEGATION_SANS_TITULAIRE_VALIDE': "Le délégant ne détient plus directement la permission déléguée.",
}

# Largeur croissante des types de périmètre (pour borner les dérogations).
LARGEUR_PERIMETRE = {
    Perimetre.Type.PROPRE_COMPTE: 0,
    Perimetre.Type.ETUDIANT: 1,
    Perimetre.Type.MODULE_ECUE: 2,
    Perimetre.Type.GROUPE: 3,
    Perimetre.Type.NIVEAU: 4,
    Perimetre.Type.PARCOURS: 4,
    Perimetre.Type.FORMATION: 5,
    Perimetre.Type.SECRETARIAT: 6,
    Perimetre.Type.SITE: 6,
    Perimetre.Type.SERVICE: 7,
    Perimetre.Type.DIRECTION: 8,
    Perimetre.Type.INJS_ENTIER: 9,
}
