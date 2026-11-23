"""Fabriques légères pour les tests du socle d'habilitation (U1)."""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone

from habilitations.models import (
    AttributionRole,
    CompteUtilisateur,
    NiveauAcces,
    PermissionAttribuee,
    PermissionMetier,
    Perimetre,
    Personne,
    RoleMetier,
)
from habilitations.models.enums import DomaineMetier

User = get_user_model()
MOT_DE_PASSE = 'Hab#2026x'


def creer_user(username='hab-user', role_existant='ADMIN', **kwargs):
    return User.objects.create_user(
        username=username, password=MOT_DE_PASSE,
        role=role_existant, **kwargs
    )


def creer_personne(nom='Dupont', prenoms='Awa', **kwargs):
    from habilitations.services.identite import generer_matricule_personne
    valeurs = {'nom': nom, 'prenoms': prenoms}
    valeurs.update(kwargs)
    valeurs.setdefault('matricule', generer_matricule_personne())
    return Personne.objects.create(**valeurs)


def creer_compte(user=None, personne=None, **kwargs):
    user = user or creer_user(username=f"hab-c-{CompteUtilisateur.objects.count() + 1}")
    return CompteUtilisateur.objects.create(user=user, personne=personne, **kwargs)


def creer_role(code='ROLE_TEST', libellé='Rôle de test', **kwargs):
    valeurs = {
        'code': code, 'libelle': libellé,
        'domaine': DomaineMetier.TECHNIQUE,
        'niveau_defaut': NiveauAcces.N2,
    }
    valeurs.update(kwargs)
    return RoleMetier.objects.create(**valeurs)


def creer_permission(code_module='scol', ressource='inscription', action='creer',
                     **kwargs):
    return PermissionMetier.objects.create(
        module=code_module, ressource=ressource, action=action,
        libelle=kwargs.pop('libelle', f'{ressource} {action}'), **kwargs
    )


def creer_perimetre_secretariat(secretariat):
    from django.contrib.contenttypes.models import ContentType
    ct = ContentType.objects.get_for_model(secretariat.__class__)
    return Perimetre.objects.create(
        type=Perimetre.Type.SECRETARIAT,
        content_type=ct, object_id=secretariat.pk,
        reference_lisible=secretariat.numero,
        libelle=secretariat.nom,
    )


def creer_attribution(compte, role, statut=AttributionRole.Statut.ACTIVE,
                      niveau=None, **kwargs):
    kwargs.setdefault('motif', 'Attribution de test.')
    return AttributionRole.objects.create(
        compte=compte, role=role,
        niveau_effectif=niveau or role.niveau_defaut,
        statut=statut, **kwargs
    )


def creer_derogation(compte, permission, sens=PermissionAttribuee.Sens.OCTROI,
                     **kwargs):
    kwargs.setdefault('motif', 'Dérogation de test.')
    return PermissionAttribuee.objects.create(
        compte=compte, permission=permission, sens=sens, **kwargs
    )


def date_il_y_a(jours):
    return timezone.localdate() - timedelta(days=jours)


def date_dans(jours):
    return timezone.localdate() + timedelta(days=jours)


def secretariat(numero='SECR-HAB-1', nom='Secrétariat test'):
    from formations.models import Secretariat
    return Secretariat.objects.create(numero=numero, nom=nom)
