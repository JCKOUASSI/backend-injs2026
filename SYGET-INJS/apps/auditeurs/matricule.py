"""
Utilitaire de génération de matricule pour les auditeurs.
"""

import random
import string


def generer_matricule(nom: str, prenom: str) -> str:
    """
    Génère un matricule unique basé sur les initiales et un suffixe aléatoire.
    Format : 2 premières lettres du nom + 2 premières lettres du prénom + 4 chiffres.
    """
    prefix = (nom[:2] + prenom[:2]).upper().replace(" ", "X")
    suffix = "".join(random.choices(string.digits, k=4))
    return f"{prefix}{suffix}"
