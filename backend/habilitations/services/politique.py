"""Modification de la politique de sécurité avec historisation au journal."""
from ..models.politique import PolitiqueSecurite
from .journalisation import journaliser

# Champs de PolitiqueSecurite modifiables par ce service.
CHAMPS_AUTORISES = frozenset({
    'longueur_min_mot_de_passe', 'exige_majuscule', 'exige_minuscule',
    'exige_chiffre', 'exige_caractere_special',
    'duree_validite_mot_de_passe_jours', 'historique_mots_de_passe',
    'nombre_echecs_avant_verrouillage', 'duree_verrouillage_minutes',
    'inactivite_session_minutes', 'inactivite_suspension_jours',
    'duree_max_derogation_jours', 'periodicite_revue_jours',
    'roles_mfa_obligatoire', 'canaux_par_role',
})


def modifier_politique(auteur=None, motif='', adresse_ip=None,
                       agent_utilisateur='', **champs):
    """Met à jour le singleton et trace une entrée POLITIQUE_MODIFIEE.

    En U1, la politique n'est appliquée par aucun contrôle d'accès ; la
    fonction garantit seulement que tout changement est journalisé (R7).
    """
    politique = PolitiqueSecurite.objet()
    anciennes, nouvelles = {}, {}
    for nom, valeur in champs.items():
        if nom not in CHAMPS_AUTORISES:
            raise ValueError(f'Réglage de politique inconnu : {nom}')
        anciennes[nom] = getattr(politique, nom)
        nouvelles[nom] = valeur
        setattr(politique, nom, valeur)
    if auteur and auteur.is_authenticated:
        politique.modifie_par = auteur
    politique.save()
    if nouvelles:
        journaliser(
            'POLITIQUE_MODIFIEE',
            acteur=auteur if (auteur and auteur.is_authenticated) else None,
            cible=politique, ancienne_valeur=anciennes,
            nouvelle_valeur=nouvelles, motif=motif,
            adresse_ip=adresse_ip, agent_utilisateur=agent_utilisateur,
        )
    return politique
