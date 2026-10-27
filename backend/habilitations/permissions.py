"""Permissions DRF livrées par U2.

``ExigePermission`` est la brique qui reliera une vue au moteur. En U2, elle
n'est posée sur **aucune vue existante** :

* mode OFF (défaut durci par variable d'environnement) : *no-op* total, la
  permission accorde sans même évaluer ;
* mode OBSERVATION : le moteur évalue, les écarts sont comptés et loggés,
  mais la décision de l'ancien dispositif est seule appliquée — la permission
  s'abstient (elle accorde) pour les comptes gouvernés comme non gouvernés ;
* mode APPLICATION (jamais activé en U2) : le refus du moteur devient
  effectif et est tracé au journal append-only sous ``ACCES_REFUSE``.

``EstAdministrateurHabilitations`` réutilise les rôles d'administration
existants : aucune notion nouvelle de super-administrateur n'est introduite.
"""
import logging

from rest_framework.permissions import BasePermission

from .services.codes import MODE_APPLICATION, MODE_OFF
from .services.moteur import est_autorise, mode_moteur
from .services.observation import enregistrer_decision

logger = logging.getLogger(__name__)


def _canal_requete(request):
    """Détermine le canal de la demande (web par défaut pour les vues DRF)."""
    explicite = request.META.get('HTTP_X_HABILITATIONS_CANAL', '')
    if explicite in ('WEB', 'MOBILE'):
        return explicite
    donnees = getattr(request, 'data', None)
    if isinstance(donnees, dict) and donnees.get('device_id'):
        return 'MOBILE'
    return 'WEB'


class ExigePermission(BasePermission):
    """Permission DRF pilotée par ``habilitations.services.moteur``.

    Usage : ``permission_classes=[ExigePermission.pour('scol.inscription.creer')]``
    """

    message = "Accès refusé par le moteur d'habilitation."

    def __init__(self, code_permission='', niveau_minimum=None, canal=None):
        self.code_permission = code_permission
        self.niveau_minimum = niveau_minimum
        self.canal_force = canal

    @classmethod
    def pour(cls, code_permission, **kwargs):
        """Factory usable dans ``permission_classes`` (classe DRF instantiée)."""
        def fabrique():
            return cls(code_permission, **kwargs)
        fabrique.__name__ = f'ExigePermission_{code_permission.replace(".", "_")}'
        return fabrique

    def _evaluer(self, request, cible=None):
        canal = self.canal_force or _canal_requete(request)
        contexte = {}
        if self.niveau_minimum:
            contexte['niveau_minimum'] = self.niveau_minimum
        return est_autorise(
            request.user, self.code_permission,
            canal=canal, cible=cible, contexte=contexte,
        )

    def has_permission(self, request, view):
        if mode_moteur() == MODE_OFF:
            return True  # no-op total
        decision = self._evaluer(request)
        # En observation, l'écart est mesuré mais la réponse n'est pas changée.
        enregistrer_decision(
            decision, decision_legacy=True,
            username=request.user.get_username()
            if getattr(request.user, 'is_authenticated', False) else '',
        )
        if not decision.gouverne:
            return True  # abstention : l'ancien dispositif décide seul
        if mode_moteur() == MODE_APPLICATION and not decision.autorise:
            self._refuser(request, decision, cible=None)
            return False
        return True

    def has_object_permission(self, request, view, obj):
        if mode_moteur() == MODE_OFF:
            return True
        decision = self._evaluer(request, cible=obj)
        enregistrer_decision(
            decision, decision_legacy=True,
            username=request.user.get_username(),
        )
        if not decision.gouverne:
            return True
        if mode_moteur() == MODE_APPLICATION and not decision.autorise:
            self._refuser(request, decision, cible=obj)
            return False
        return True

    def _refuser(self, request, decision, cible):
        """Trace le refus au journal chaîné puis journalise (mode application)."""
        code_principal = decision.motifs[0] if decision.motifs else 'REFUS'
        self.message = (
            f"Accès refusé ({code_principal}) pour la permission "
            f"{self.code_permission}."
        )
        logger.warning(
            'habilitation_refus permission=%s utilisateur=%s motifs=%s',
            self.code_permission,
            request.user.get_username(),
            ','.join(decision.motifs),
        )
        try:
            from .services.journalisation import journaliser
            from .models import CompteUtilisateur, JournalHabilitation
            compte = CompteUtilisateur.objects.filter(user=request.user).first()
            journaliser(
                JournalHabilitation.TypeEvenement.ACCES_REFUSE,
                acteur=request.user,
                compte=compte,
                cible=cible,
                nouvelle_valeur={
                    'permission': self.code_permission,
                    'motifs': decision.motifs,
                    'canal': decision.canal,
                },
                motif=code_principal,
                adresse_ip=request.META.get('REMOTE_ADDR', ''),
                agent_utilisateur=request.META.get('HTTP_USER_AGENT', '')[:200],
            )
        except Exception:  # le refus ne doit jamais être masqué par une trace
            logger.exception('habilitation_refus_journal_echec')


class EstAdministrateurHabilitations(BasePermission):
    """Réservé au trio d'administration legacy (ADMIN, INJS_ADMIN, CHEF).

    On ne se fonde PAS sur la permission ``mutate_users`` : les secrétariats
    la détiennent pour gérer les comptes métier, mais la synthèse
    d'observation et les réglages du moteur relèvent de l'administration
    centrale et du RSSI.
    """

    message = "Réservé aux administrateurs de l'habilitation."

    def has_permission(self, request, view):
        user = request.user
        if not (user and getattr(user, 'is_authenticated', False)):
            return False
        if getattr(user, 'is_superuser', False):
            return True
        try:
            from authentication.role_groups import user_in_roles
            return user_in_roles(
                user,
                ('ADMIN', 'INJS_ADMIN', 'CHEF_INJS_ADMIN'),
            )
        except ImportError:
            return False


class ExigeDrapeauAdmin(BasePermission):
    """Garde des endpoints de la console CURP U4.

    Exige à la fois :
    * le drapeau ``flag.curp_ui_admin`` ouvert pour l'utilisateur (kill-switch
      sans passe-droit super-utilisateur) ;
    * l'appartenance au trio d'administration de l'habilitation.

    Drapeau fermé → 403 (et les routes ne sont pas référencées côté interface)
    : l'administration Django reste la seule voie, conformément au repli U4.
    """

    message = "Console d'habilitation indisponible (drapeau fermé ou droit insuffisant)."

    def has_permission(self, request, view):
        if not EstAdministrateurHabilitations().has_permission(request, view):
            return False
        try:
            from parametres.flags import is_enabled
            return is_enabled('flag.curp_ui_admin', request.user)
        except Exception:
            return False
