"""
Commande : python manage.py repair_auditeur_fiches

Répare les comptes auditeurs rattachés à une fiche « fantôme » (Participant lié
au compte mais SANS aucune inscription à un module), alors qu'une autre fiche —
au matricule au format légèrement différent (ex. « OPH-1 » vs « OPH1 ») — est,
elle, bien inscrite aux modules.

Ce cas provenait d'une ancienne synchronisation qui, sur un simple écart de
format de matricule, déliait la vraie fiche et créait un doublon vide. Le
badgeage échouait alors avec « Vous n'êtes pas inscrit(e) à ce module ».

Pour chaque fiche fantôme détectée, la commande :

  1. retrouve la fiche réellement inscrite qui correspond au compte
     (rapprochement par matricule normalisé : casse / espaces / ponctuation) ;
  2. (avec --apply) migre les éventuels pointages de la fiche fantôme vers la
     vraie fiche (en évitant les doublons sur une même séance) ;
  3. rattache le compte à la vraie fiche et réaligne le matricule du compte ;
  4. supprime la fiche fantôme si elle ne porte plus ni inscription ni pointage.

Usage :

  # Diagnostic seul (aucune écriture) :
  python manage.py repair_auditeur_fiches

  # Cibler un compte / matricule précis :
  python manage.py repair_auditeur_fiches --user OPH1

  # Appliquer les réparations :
  python manage.py repair_auditeur_fiches --apply
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Count

from formations.models import Participant
from presences.models import Pointage
from presences.participant_scope import _compact_identifier

User = get_user_model()


def _digits_key(value):
    """Suite de chiffres d'un matricule, zéros en tête de chaque groupe neutralisés.

    Permet de rapprocher « FNCE24-00178543 » et « FNCE24-0178543 » (écart de
    zéros) que ``_compact_identifier`` considère, lui, comme distincts.
    """
    groups = []
    current = []
    for ch in (value or ''):
        if ch.isdigit():
            current.append(ch)
        elif current:
            groups.append(str(int(''.join(current))))
            current = []
    if current:
        groups.append(str(int(''.join(current))))
    return '-'.join(groups)


def _name_key(participant):
    """Clé compacte nom+prénom pour rapprocher deux fiches de la même personne."""
    return _compact_identifier(getattr(participant, 'nom', '')) + '|' + \
        _compact_identifier(getattr(participant, 'prenom', ''))


class Command(BaseCommand):
    help = (
        "Répare les comptes auditeurs liés à une fiche vide alors qu'une fiche "
        "au matricule équivalent est inscrite aux modules (badgeage impossible)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply',
            action='store_true',
            help='Applique les réparations (sinon simple diagnostic).',
        )
        parser.add_argument(
            '--user',
            type=str,
            default=None,
            help="Limiter à un compte (matricule ou username, insensible au format).",
        )

    def handle(self, *args, **options):
        apply_changes = options['apply']
        target = options['user']

        phantoms = (
            Participant.objects
            .filter(user__isnull=False)
            .annotate(nb_inscriptions=Count('modules_inscrits'))
            .filter(nb_inscriptions=0)
            .select_related('user')
            .order_by('matricule')
        )

        if target:
            target_compact = _compact_identifier(target)
            phantoms = [
                p for p in phantoms
                if target_compact in {
                    _compact_identifier(p.matricule),
                    _compact_identifier(getattr(p.user, 'matricule', '')),
                    _compact_identifier(getattr(p.user, 'username', '')),
                }
            ]

        mode = self.style.WARNING('[DRY-RUN]') if not apply_changes else self.style.SUCCESS('[APPLY]')
        self.stdout.write('=' * 80)
        self.stdout.write(f"{mode} Analyse des fiches auditeurs fantômes")
        self.stdout.write('=' * 80)

        stats = {
            'phantoms': 0,
            'repaired': 0,
            'pointages_migres': 0,
            'pointages_conflits': 0,
            'fiches_supprimees': 0,
            'sans_solution': 0,
        }

        for phantom in phantoms:
            stats['phantoms'] += 1
            self._process_phantom(phantom, apply_changes, stats)

        self.stdout.write('=' * 80)
        self.stdout.write(self.style.SUCCESS(
            "Terminé — fantômes: {phantoms}, réparés: {repaired}, "
            "pointages migrés: {pointages_migres} (conflits ignorés: {pointages_conflits}), "
            "fiches supprimées: {fiches_supprimees}, sans solution: {sans_solution}".format(**stats)
        ))
        if not apply_changes and stats['phantoms']:
            self.stdout.write(self.style.WARNING(
                "Relancez avec --apply pour appliquer les réparations."
            ))

    def _find_enrolled_fiche(self, phantom):
        """Fiche inscrite dont le matricule normalisé correspond au compte/fiche fantôme."""
        user = phantom.user
        candidates = {
            _compact_identifier(getattr(user, 'matricule', '')),
            _compact_identifier(getattr(user, 'username', '')),
            _compact_identifier(phantom.matricule),
        }
        candidates.discard('')
        if not candidates:
            return None

        enrolled = (
            Participant.objects
            .exclude(pk=phantom.pk)
            .annotate(nb_inscriptions=Count('modules_inscrits'))
            .filter(nb_inscriptions__gt=0)
        )
        best = None
        best_nb = -1
        for cand in enrolled:
            if _compact_identifier(cand.matricule) in candidates and cand.nb_inscriptions > best_nb:
                best = cand
                best_nb = cand.nb_inscriptions
        return best

    def _print_suggestions(self, phantom, limit=5):
        """Liste les fiches inscrites plausibles (même personne / matricule proche).

        Purement informatif : aide l'opérateur à décider s'il existe une vraie
        fiche à rattacher (à traiter avec --user) ou si l'auditeur n'est
        réellement inscrit à aucun module.
        """
        user = phantom.user
        name_key = _name_key(phantom)
        digit_keys = {
            _digits_key(getattr(user, 'matricule', '')),
            _digits_key(getattr(user, 'username', '')),
            _digits_key(phantom.matricule),
        }
        digit_keys.discard('')

        enrolled = (
            Participant.objects
            .exclude(pk=phantom.pk)
            .annotate(nb_inscriptions=Count('modules_inscrits'))
            .filter(nb_inscriptions__gt=0)
        )

        suggestions = []
        for cand in enrolled:
            reasons = []
            if name_key.strip('|') and _name_key(cand) == name_key:
                reasons.append('même nom+prénom')
            if _digits_key(cand.matricule) in digit_keys:
                reasons.append('matricule proche (écart de zéros)')
            if reasons:
                suggestions.append((cand, reasons))

        if not suggestions:
            self.stdout.write(
                "    (aucune fiche inscrite proche par nom ou matricule — "
                "l'auditeur n'est probablement inscrit à aucun module.)"
            )
            return

        self.stdout.write(self.style.WARNING(
            f"    Candidats possibles ({len(suggestions)}) — à vérifier puis "
            f"rattacher via --user :"
        ))
        for cand, reasons in suggestions[:limit]:
            self.stdout.write(
                f"      • #{cand.pk} matricule={cand.matricule!r} "
                f"{cand.nom} {cand.prenom} "
                f"({cand.nb_inscriptions} inscription(s), user_id={cand.user_id}) "
                f"[{', '.join(reasons)}]"
            )
        if len(suggestions) > limit:
            self.stdout.write(f"      … et {len(suggestions) - limit} autre(s).")

    def _process_phantom(self, phantom, apply_changes, stats):
        user = phantom.user
        nb_pointages = Pointage.objects.filter(participant=phantom).count()
        self.stdout.write('-' * 80)
        self.stdout.write(
            f"Fiche fantôme #{phantom.pk} matricule={phantom.matricule!r} "
            f"(compte user_id={user.pk} username={user.username!r} matricule={user.matricule!r}) "
            f"— 0 inscription, {nb_pointages} pointage(s)"
        )

        real = self._find_enrolled_fiche(phantom)
        if real is None:
            stats['sans_solution'] += 1
            self.stdout.write(self.style.ERROR(
                "  ✗ Aucune fiche inscrite ne correspond à ce compte (rapprochement "
                "strict par matricule) — vérifier manuellement."
            ))
            self._print_suggestions(phantom)
            return

        if real.user_id not in (None, user.pk):
            stats['sans_solution'] += 1
            self.stdout.write(self.style.ERROR(
                f"  ✗ Fiche inscrite #{real.pk} ({real.matricule!r}) déjà liée à un autre "
                f"compte (user_id={real.user_id}) — résolution manuelle requise."
            ))
            return

        self.stdout.write(self.style.SUCCESS(
            f"  → Fiche inscrite trouvée #{real.pk} matricule={real.matricule!r} "
            f"({real.nb_inscriptions} inscription(s))"
        ))

        if not apply_changes:
            self.stdout.write(
                f"    (dry-run) rattacherait le compte à #{real.pk}, "
                f"migrerait {nb_pointages} pointage(s), supprimerait #{phantom.pk}."
            )
            return

        with transaction.atomic():
            migres, conflits = self._migrate_pointages(phantom, real)
            stats['pointages_migres'] += migres
            stats['pointages_conflits'] += conflits

            # Détacher la fiche fantôme du compte AVANT de lier la vraie (OneToOne).
            Participant.objects.filter(pk=phantom.pk).update(user=None)
            Participant.objects.filter(pk=real.pk).update(user=user)
            if (user.matricule or '').strip() != real.matricule:
                User.objects.filter(pk=user.pk).update(matricule=real.matricule)

            stats['repaired'] += 1
            self.stdout.write(self.style.SUCCESS(
                f"    ✓ Compte rattaché à #{real.pk}, matricule aligné sur {real.matricule!r}."
            ))

            restant = Pointage.objects.filter(participant=phantom).count()
            if restant == 0:
                phantom.delete()
                stats['fiches_supprimees'] += 1
                self.stdout.write(self.style.SUCCESS(
                    f"    ✓ Fiche fantôme #{phantom.pk} supprimée."
                ))
            else:
                self.stdout.write(self.style.WARNING(
                    f"    ⚠ Fiche fantôme #{phantom.pk} conservée "
                    f"({restant} pointage(s) en conflit non migrés)."
                ))

    def _migrate_pointages(self, phantom, real):
        """Déplace les pointages de la fiche fantôme vers la vraie fiche.

        Un pointage n'est pas déplacé si un pointage existe déjà pour la vraie
        fiche sur la même séance (évite un doublon logique)."""
        migres = conflits = 0
        for pt in Pointage.objects.filter(participant=phantom):
            conflit = Pointage.objects.filter(
                participant=real, session_id=pt.session_id,
            ).exclude(pk=pt.pk).exists()
            if conflit:
                conflits += 1
                continue
            pt.participant = real
            pt.save(update_fields=['participant', 'updated_at'])
            migres += 1
        return migres, conflits
