"""Export des UE/ECUE d'une maquette — CSV, Excel, Word, PDF.

Une ligne par ECUE (les colonnes ``UE_*`` sont répétées) ; une UE sans ECUE
sort sur une ligne dont les colonnes ``ECUE_*`` sont vides, afin qu'aucune UE
ne disparaisse de l'export.

Le module ne filtre ni ne contrôle les droits : l'appelant fournit une
maquette déjà autorisée et, éventuellement, les identifiants d'UE
sélectionnées.
"""

from __future__ import annotations

from datetime import date

from . import tableaux_export

COLONNES = [
    'SEMESTRE', 'UE_CODE', 'UE_INTITULE', 'UE_CREDITS', 'UE_CARACTERE', 'UE_STATUT',
    'ECUE_CODE', 'ECUE_INTITULE', 'ECUE_CREDITS', 'COEFFICIENT',
    'HEURES_CM', 'HEURES_TD', 'HEURES_TP', 'HEURES_TOTAL', 'ECUE_STATUT',
]


def _nombre(valeur):
    """Décimale lisible : ``12`` plutôt que ``12.00``."""
    if valeur in (None, ''):
        return ''
    nombre = float(valeur)
    return str(int(nombre)) if nombre == int(nombre) else f'{nombre:.2f}'.replace('.', ',')


def lignes_ue_ecue(maquette, ids=None):
    """Tableau ``{colonne: valeur}`` des UE de la maquette (et de leurs ECUE)."""
    ues = (
        maquette.unites_enseignement
        .select_related('semestre')
        .prefetch_related('ecues')
        .order_by('semestre__numero', 'ordre', 'code')
    )
    if ids:
        ues = ues.filter(pk__in=ids)
    resultat = []
    for ue in ues:
        commun = {
            'SEMESTRE': ue.semestre.libelle if ue.semestre_id else '',
            'UE_CODE': ue.code,
            'UE_INTITULE': ue.intitule,
            'UE_CREDITS': ue.credits,
            'UE_CARACTERE': ue.get_caractere_display(),
            'UE_STATUT': ue.get_statut_display(),
        }
        ecues = sorted(ue.ecues.all(), key=lambda ecue: (ecue.ordre, ecue.code))
        if not ecues:
            resultat.append({
                **commun,
                'ECUE_CODE': '', 'ECUE_INTITULE': '', 'ECUE_CREDITS': '',
                'COEFFICIENT': '', 'HEURES_CM': '', 'HEURES_TD': '', 'HEURES_TP': '',
                'HEURES_TOTAL': '', 'ECUE_STATUT': '',
            })
            continue
        for ecue in ecues:
            resultat.append({
                **commun,
                'ECUE_CODE': ecue.code,
                'ECUE_INTITULE': ecue.intitule,
                'ECUE_CREDITS': ecue.credits,
                'COEFFICIENT': _nombre(ecue.coefficient),
                'HEURES_CM': _nombre(ecue.volume_cm),
                'HEURES_TD': _nombre(ecue.volume_td),
                'HEURES_TP': _nombre(ecue.volume_tp),
                'HEURES_TOTAL': _nombre(ecue.volume_total),
                'ECUE_STATUT': ecue.get_statut_display(),
            })
    return resultat


def nom_fichier(maquette, fmt):
    return f'maquette-{maquette.pk}-ue-ecue_{date.today().isoformat()}.{tableaux_export.EXTENSIONS[fmt]}'


def reponse_export(maquette, fmt, ids=None):
    """Réponse de téléchargement pour les UE sélectionnées (ou toutes)."""
    lignes = lignes_ue_ecue(maquette, ids=ids)
    return tableaux_export.reponse(
        COLONNES, lignes, fmt, nom_fichier(maquette, fmt),
        feuille='UE et ECUE',
        titre=f'Maquette — {maquette}',
        sous_titre='Unités d’enseignement et éléments constitutifs',
    )


__all__ = ['COLONNES', 'lignes_ue_ecue', 'nom_fichier', 'reponse_export']
