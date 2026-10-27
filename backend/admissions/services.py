"""Services métier des candidatures et des pièces justificatives."""

from django.db import transaction
from django.utils import timezone

from scolarite.models import JournalScolarite, journaliser

from .models import Candidature, PieceCandidature, ReglePiece, TypePiece


def types_pieces_attendus(ref_formation, type_formation=None):
    """Types de pièces attendus pour une formation, avec leur caractère obligatoire.

    Une règle spécifique au cycle de formation prime sur une règle par type de
    formation, qui prime elle-même sur le défaut porté par le type de pièce.
    """
    attendus = {
        type_piece: type_piece.obligatoire_par_defaut
        for type_piece in TypePiece.objects.filter(actif=True)
    }

    regles = ReglePiece.objects.filter(type_piece__actif=True).select_related('type_piece')
    if type_formation is not None:
        for regle in regles.filter(type_formation=type_formation, ref_formation__isnull=True):
            attendus[regle.type_piece] = regle.obligatoire
    for regle in regles.filter(ref_formation=ref_formation):
        attendus[regle.type_piece] = regle.obligatoire

    return attendus


@transaction.atomic
def initialiser_pieces(candidature, acteur=None):
    """Crée les lignes de pièces manquantes attendues pour la candidature.

    Idempotent : une pièce déjà présente n'est jamais réinitialisée, afin de ne
    pas écraser un dépôt ou une vérification existante.
    """
    type_formation = candidature.parcours.type_formation if candidature.parcours_id else None
    attendus = types_pieces_attendus(candidature.ref_formation, type_formation)
    existants = set(candidature.pieces.values_list('type_piece_id', flat=True))

    creees = [
        PieceCandidature(
            candidature=candidature,
            type_piece=type_piece,
            obligatoire=obligatoire,
            statut=PieceCandidature.Statut.MANQUANTE,
        )
        for type_piece, obligatoire in attendus.items()
        if type_piece.id not in existants
    ]
    if creees:
        PieceCandidature.objects.bulk_create(creees)
        journaliser(
            JournalScolarite.Action.CANDIDATURE_CREEE,
            objet=candidature,
            acteur=acteur,
            commentaire=f'{len(creees)} pièce(s) attendue(s) initialisée(s).',
        )
    return creees


@transaction.atomic
def deposer_piece(piece, fichier=None, acteur=None, **champs):
    """Enregistre le dépôt d'une pièce et la place en vérification."""
    for champ in ('numero_document', 'date_delivrance', 'date_expiration'):
        if champ in champs:
            setattr(piece, champ, champs[champ])
    if fichier is not None:
        piece.fichier = fichier
    piece.statut = PieceCandidature.Statut.EN_VERIFICATION
    piece.verifie_par = None
    piece.verifie_le = None
    piece.save()

    journaliser(
        JournalScolarite.Action.PIECE_DEPOSEE,
        objet=piece,
        acteur=acteur,
        nouvelle_valeur=piece.statut,
    )
    return piece


@transaction.atomic
def verifier_piece(piece, statut, acteur=None, commentaire=''):
    """Valide, refuse ou marque expirée une pièce déposée."""
    ancien = piece.statut
    piece.statut = statut
    piece.commentaire = commentaire
    piece.verifie_par = acteur if getattr(acteur, 'pk', None) else None
    piece.verifie_le = timezone.now()
    piece.save(update_fields=['statut', 'commentaire', 'verifie_par', 'verifie_le'])

    journaliser(
        JournalScolarite.Action.PIECE_VERIFIEE,
        objet=piece,
        acteur=acteur,
        ancienne_valeur=ancien,
        nouvelle_valeur=statut,
        commentaire=commentaire,
    )
    return piece


def rafraichir_pieces_expirees(candidature):
    """Bascule en EXPIREE les pièces validées dont la date de validité est dépassée."""
    aujourdhui = timezone.localdate()
    expirees = candidature.pieces.filter(
        statut=PieceCandidature.Statut.VALIDEE,
        date_expiration__lt=aujourdhui,
    )
    nombre = expirees.update(statut=PieceCandidature.Statut.EXPIREE)
    return nombre


@transaction.atomic
def creer_candidature(candidat, acteur=None, **champs):
    """Crée une candidature et initialise son dossier de pièces."""
    candidature = Candidature(candidat=candidat, **champs)
    candidature.full_clean(exclude=['numero'])
    candidature.save()
    initialiser_pieces(candidature, acteur=acteur)
    journaliser(
        JournalScolarite.Action.CANDIDATURE_CREEE,
        objet=candidature,
        acteur=acteur,
        nouvelle_valeur=candidature.statut,
    )
    return candidature
