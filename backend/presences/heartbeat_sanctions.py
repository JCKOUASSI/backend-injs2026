"""Sanctions liées à l'absence de heartbeat mobile (suspect, sortie auto, alerte mail)."""

from django.conf import settings
from django.utils import timezone

from authentication.emails import send_suspect_heartbeat_email
from presences.models import AuditLog, Pointage

SUSPECT_TIMEOUT_MINUTES = getattr(settings, 'MOBILE_HEARTBEAT_SUSPECT_TIMEOUT_MINUTES', 60)
AUTO_EXIT_TIMEOUT_MINUTES = getattr(settings, 'MOBILE_HEARTBEAT_AUTO_EXIT_TIMEOUT_MINUTES', 120)

NO_MOBILE_HEARTBEAT_DEVICE_IDS = frozenset({'WEB_BADGE', 'OFFLINE_WEB'})
FLUTTER_PWA_DEVICE_PREFIX = 'FLUTTER_PWA_'


def skip_mobile_heartbeat_sanctions(pointage):
    did = (pointage.device_id or '').strip()
    if did in NO_MOBILE_HEARTBEAT_DEVICE_IDS:
        return True
    if did.startswith(FLUTTER_PWA_DEVICE_PREFIX):
        return True
    return False


def _personne_label(pointage):
    personne = pointage.participant or pointage.formateur or pointage.encadrant
    if not personne:
        return '?', '?', 'participant'
    nom = (
        f"{getattr(personne, 'nom', '')} {getattr(personne, 'prenom', '')}".strip()
        or f"{getattr(personne, 'last_name', '')} {getattr(personne, 'first_name', '')}".strip()
        or getattr(personne, 'username', '?')
    )
    numero = (
        getattr(personne, 'numerobadge', None)
        or getattr(personne, 'matricule', None)
        or getattr(personne, 'numero', '?')
    )
    if pointage.formateur_id:
        type_str = 'formateur'
    elif pointage.encadrant_id:
        type_str = 'encadrant'
    else:
        type_str = 'participant'
    return numero, nom, type_str


def process_mobile_heartbeat_sanctions(*, dry_run=False, write=None):
    """
    Traite les pointages EN_COURS / HORS_LIGNE_SUSPECT sans heartbeat récent.

    Retourne le nombre de pointages traités (suspect ou sortie auto).
    """
    if getattr(settings, 'MOBILE_HEARTBEAT_DISABLED', False):
        return 0

    write = write or (lambda _msg: None)
    now = timezone.now()
    traites = 0

    pointages_ouverts = (
        Pointage.objects
        .filter(
            statut__in=[Pointage.Statut.EN_COURS, Pointage.Statut.HORS_LIGNE_SUSPECT],
            timestamp_sortie__isnull=True,
        )
        .select_related(
            'session__module__formation',
            'session__module__superviseur',
            'participant',
            'formateur',
            'encadrant',
        )
        # Lot C : les pointages de séances LMD (QR EDT) n'ont pas de session
        # legacy et ne reçoivent pas de heartbeat ; ils sont exclus.
        .filter(session__isnull=False)
    )

    for pt in pointages_ouverts:
        if skip_mobile_heartbeat_sanctions(pt):
            continue

        seance = pt.session
        numero, nom, type_str = _personne_label(pt)
        last_seen_at = pt.last_heartbeat_at or pt.timestamp_entree
        silence_minutes = int((now - last_seen_at).total_seconds() // 60)

        if silence_minutes >= AUTO_EXIT_TIMEOUT_MINUTES:
            if dry_run:
                write(
                    f"[DRY-RUN] SORTIE_AUTO {numero} {nom} — "
                    f"{seance.module.formation.formation} (silence {silence_minutes} min)"
                )
                traites += 1
                continue

            pt.timestamp_sortie = now
            pt.statut = Pointage.Statut.SORTIE_AUTO
            pt.calculer_duree()
            pt.save(update_fields=['timestamp_sortie', 'duree_presence_minutes', 'statut', 'updated_at'])

            AuditLog.objects.create(
                action=AuditLog.Action.AUTO_EXIT,
                acteur=None,
                acteur_label='Système',
                cible_type=type_str,
                cible_numero=numero,
                cible_nom=nom,
                formation=seance.module.formation,
                formation_titre=seance.module.formation.formation,
                pointage=pt,
                ip_address=None,
                device_id='SYSTEM',
                extra={
                    'motif': 'NO_HEARTBEAT_TIMEOUT',
                    'silence_minutes': silence_minutes,
                    'last_heartbeat_at': last_seen_at.isoformat() if last_seen_at else None,
                    'auto_exit_timeout_minutes': AUTO_EXIT_TIMEOUT_MINUTES,
                    'battery_level': pt.last_battery_level,
                    'is_charging': pt.last_is_charging,
                },
            )
            traites += 1
            write(f"SORTIE_AUTO : {numero} {nom} — {seance.module.formation.formation}")
            continue

        if silence_minutes >= SUSPECT_TIMEOUT_MINUTES and pt.statut == Pointage.Statut.EN_COURS:
            if dry_run:
                write(
                    f"[DRY-RUN] HORS_LIGNE_SUSPECT {numero} {nom} — "
                    f"{seance.module.formation.formation} (silence {silence_minutes} min)"
                )
                traites += 1
                continue

            pt.statut = Pointage.Statut.HORS_LIGNE_SUSPECT
            pt.save(update_fields=['statut', 'updated_at'])

            AuditLog.objects.create(
                action=AuditLog.Action.NO_HEARTBEAT,
                acteur=None,
                acteur_label='Système',
                cible_type=type_str,
                cible_numero=numero,
                cible_nom=nom,
                formation=seance.module.formation,
                formation_titre=seance.module.formation.formation,
                pointage=pt,
                ip_address=None,
                device_id='SYSTEM',
                extra={
                    'motif': 'NO_HEARTBEAT',
                    'silence_minutes': silence_minutes,
                    'last_heartbeat_at': last_seen_at.isoformat() if last_seen_at else None,
                    'suspect_timeout_minutes': SUSPECT_TIMEOUT_MINUTES,
                    'battery_level': pt.last_battery_level,
                    'is_charging': pt.last_is_charging,
                },
            )
            traites += 1
            write(f"HORS_LIGNE_SUSPECT : {numero} {nom} — {seance.module.formation.formation}")

            encadrant = seance.module.superviseur
            seance_label = seance.intitule or f'Séance {seance.numero}'
            send_suspect_heartbeat_email(
                encadrant=encadrant,
                personne_nom=nom,
                personne_numero=numero,
                formation_titre=seance.module.formation.formation,
                module_intitule=seance.module.intitule,
                seance_label=seance_label,
                silence_minutes=silence_minutes,
            )

    return traites
