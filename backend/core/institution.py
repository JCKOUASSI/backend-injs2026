"""Identité institutionnelle imprimée sur les documents officiels de l'INJS.

Source unique des en-têtes et pieds de page des exports (PDF, Word, Excel).

Historique : plusieurs exports (liste des participants, fiche de paie
formateur, point journalier) imprimaient encore l'en-tête et jusqu'à l'adresse
postale du **CPFAE** — établissement auquel l'application ne se destine plus.
Deux exportations portaient par ailleurs déjà l'en-tête INJS correct
(`formations/notes_fiche_export.py`, `graduation/services.py`) : c'est cette
formulation, issue des documents institutionnels, qui est reprise ici.

Aucune adresse postale n'est inventée : `INJS_ADRESSE_OFFICIELLE` reste vide
tant que le commanditaire n'a pas fourni l'adresse officielle à imprimer. La
variable d'environnement ``INJS_ADRESSE_OFFICIELLE`` permet de la renseigner
sans modification de code.
"""
from django.conf import settings

#: Nom officiel de l'établissement (documenté).
NOM_OFFICIEL = "Institut National de la Jeunesse et des Sports (INJS)"

#: Ministère de tutelle, repris des en-têtes déjà utilisés par les documents
#: officiels de l'application (`formations/notes_fiche_export.py`).
MINISTERE_TUTELLE = (
    "Ministère de la Promotion des Sports et du Développement de l'Économie Sportive"
)

#: Localisation documentée de l'établissement.
VILLE = "Abidjan"


def lignes_entete(avec_ufr=False):
    """En-tête officiel à imprimer en haut d'un document.

    ``avec_ufr`` ajoute la mention de l'UFR STAPS-JL, utilisée par les
    documents pédagogiques (relevés, fiches de notes).
    """
    lignes = [
        "RÉPUBLIQUE DE CÔTE D'IVOIRE",
        MINISTERE_TUTELLE,
        NOM_OFFICIEL,
    ]
    if avec_ufr:
        lignes.append("UFR STAPS-JL — Système LMD")
    return lignes


def nom_etablissement():
    """Nom officiel, surchargeable par ``INJS_NOM_OFFICIEL``."""
    # Un réglage vide — ou réduit à des espaces — ne doit pas effacer le nom
    # officiel : on retombe alors sur la constante documentée.
    nom = (getattr(settings, 'INJS_NOM_OFFICIEL', '') or '').strip()
    return nom or NOM_OFFICIEL


def adresse_officielle():
    """Adresse postale à imprimer (vide par défaut : rien n'est inventé)."""
    return (getattr(settings, 'INJS_ADRESSE_OFFICIELLE', '') or '').strip()


def pied_de_page():
    """Ligne de pied de page : établissement, ville et adresse si configurée."""
    morceaux = [nom_etablissement(), VILLE.upper()]
    adresse = adresse_officielle()
    if adresse:
        morceaux.append(adresse)
    return ' — '.join(morceaux)
