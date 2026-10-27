"""Validation de périmètre pour les QR codes (isolation module / groupe)."""
from rest_framework import status
from rest_framework.response import Response

from .models import SessionModule


def get_session_for_qr(*, formation, session_id, module_id=None):
    """
    Résout une séance pour une opération QR et vérifie qu'elle appartient
    à la formation (et optionnellement au module demandé).

    Retourne (session, error_response).
    """
    if session_id in (None, ''):
        return None, Response(
            {
                'code': 'SESSION_ID_REQUIRED',
                'detail': 'session_id est obligatoire pour consulter ou générer un QR.',
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        session = SessionModule.objects.select_related('module').get(
            pk=session_id,
            module__formation=formation,
        )
    except (SessionModule.DoesNotExist, ValueError, TypeError):
        return None, Response(
            {'detail': 'Séance introuvable pour cette formation.'},
            status=status.HTTP_404_NOT_FOUND,
        )

    if module_id not in (None, ''):
        try:
            module_id_int = int(module_id)
        except (TypeError, ValueError):
            return None, Response(
                {'detail': 'module_id invalide.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if session.module_id != module_id_int:
            return None, Response(
                {
                    'code': 'QR_MODULE_MISMATCH',
                    'detail': (
                        'Cette séance n\'appartient pas au module demandé. '
                        'Générez ou consultez le QR depuis le bon module / groupe.'
                    ),
                },
                status=status.HTTP_403_FORBIDDEN,
            )

    return session, None
