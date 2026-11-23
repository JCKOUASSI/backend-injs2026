"""Services d'identité des personnes : matricules et détection de doublons.

Conformément à la fiche U1, la détection de doublons **propose** et ne
bloque jamais : elle est paramétrable et non destructive. La fusion, qui
conserve l'historique des deux identités, est un travail ultérieur (U5/U8).
"""
import re
from difflib import SequenceMatcher

from ..models.personne import Personne

PREFIXE = 'PERS'
LONGUEUR_SEQUENCE = 5


def generer_matricule_personne(an=None):
    """Prochain matricule ``PERS-AAAA-NNNNN`` pour l'année, sous verrou."""
    from django.db import transaction
    from django.utils.timezone import now

    an = an or now().year
    prefixe = f'{PREFIXE}-{an}-'
    with transaction.atomic():
        dernier = (
            Personne.objects.select_for_update()
            .filter(matricule__startswith=prefixe)
            .order_by('-matricule')
            .only('matricule')
            .first()
        )
        numero = 1
        if dernier:
            try:
                numero = int(dernier.matricule.rsplit('-', 1)[-1]) + 1
            except ValueError:
                numero = 1
        return f'{prefixe}{numero:0{LONGUEUR_SEQUENCE}d}'


def _normaliser_nom(texte):
    return re.sub(r'\s+', ' ', (texte or '').strip().upper())


def _normaliser_tel(texte):
    return re.sub(r'[^0-9]', '', texte or '')


def _similarite(a, b):
    return SequenceMatcher(None, a, b).ratio()


def identifier_doublons(
    *, activer_nom_ddn=True, activer_telephone=True, activer_email=True,
    seuil_nom=0.92,
):
    """Retourne des listes de clés primaires de personnes probablement doubles.

    Trois critères indépendants et paramétrables :
    * nom très proche ET même date de naissance ;
    * même numéro de téléphone ;
    * même courriel (personnel ou institutionnel).

    Aucun enregistrement n'est modifié : la fonction ne fait que signaler.
    """
    groupes = []
    vues = set()

    def _enregistrer_groupe(cle, ids):
        ids = tuple(sorted(set(ids)))
        if len(ids) < 2 or ids in vues:
            return
        vues.add(ids)
        groupes.append({'critere': cle, 'personnes': ids})

    personnes = list(Personne.objects.all())

    if activer_nom_ddn:
        for i, personne in enumerate(personnes):
            if not personne.date_naissance:
                continue
            nom_a = _normaliser_nom(f'{personne.prenoms} {personne.nom}')
            pour = []
            for autre in personnes[i + 1:]:
                if autre.date_naissance != personne.date_naissance:
                    continue
                nom_b = _normaliser_nom(f'{autre.prenoms} {autre.nom}')
                if _similarite(nom_a, nom_b) >= seuil_nom:
                    pour.append(autre.pk)
            if pour:
                _enregistrer_groupe('NOM_DATE_NAISSANCE', [personne.pk, *pour])

    if activer_telephone:
        annuaire = {}
        for personne in personnes:
            for tel in (personne.telephone, personne.telephone2):
                normalise = _normaliser_tel(tel)
                if len(normalise) >= 8:
                    annuaire.setdefault(normalise, []).append(personne.pk)
        for tel, ids in annuaire.items():
            _enregistrer_groupe(f'TELEPHONE:{tel}', ids)

    if activer_email:
        courriels = {}
        for personne in personnes:
            for email in (personne.email_personnel, personne.email_institutionnel):
                valeur = (email or '').strip().lower()
                if valeur:
                    courriels.setdefault(valeur, []).append(personne.pk)
        for email, ids in courriels.items():
            _enregistrer_groupe(f'EMAIL:{email}', ids)

    return groupes


def personnes_sans_compte():
    """Personnes n'ayant encore aucun compte CURP rattaché (signal U1)."""
    return Personne.objects.filter(comptes__isnull=True)
