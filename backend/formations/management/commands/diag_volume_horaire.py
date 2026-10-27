"""
Commande : python manage.py diag_volume_horaire

Diagnostique d'où vient l'écart entre le volume *effectué* et le volume *prévu*
affiché sur le dashboard. Pour chaque module (filtré par secrétariat si demandé),
affiche :

  - prévu (Module.duree_prevue_heures)
  - capacité planifiée des sessions (Σ heure_fin_prevue - heure_debut_prevue)
  - effectué brut (Σ terminee_le - demarree_le)
  - effectué plafonné (mêmes règles que le dashboard)
  - écart effectué - prévu (positif = dépassement)
  - nombre de sessions sans horaires planifiés (qui retombent sur le repli 8 h)

Usage :
  python manage.py diag_volume_horaire
  python manage.py diag_volume_horaire --secretariat "FAB B"
  python manage.py diag_volume_horaire --depassements-only
  python manage.py diag_volume_horaire --secretariat "FAB B" --top 20
"""

from django.core.management.base import BaseCommand
from django.db.models import Q

from formations.models import Module, SessionModule


_MAX_DUREE_SESSION_MIN_DEFAUT = 8 * 60


def _minutes_entre_heures(h_debut, h_fin):
    """Différence en minutes entre deux objets time. None si l'un est nul."""
    if not h_debut or not h_fin:
        return None
    return (
        (h_fin.hour * 60 + h_fin.minute + h_fin.second / 60)
        - (h_debut.hour * 60 + h_debut.minute + h_debut.second / 60)
    )


class Command(BaseCommand):
    help = "Diagnostique l'écart entre volume effectué et volume prévu, module par module."

    def add_arguments(self, parser):
        parser.add_argument(
            '--secretariat',
            type=str,
            default=None,
            help="Filtre par libellé du type de secrétariat (ex. 'FAB A', 'FAB B').",
        )
        parser.add_argument(
            '--depassements-only',
            action='store_true',
            help="N'affiche que les modules où l'effectué plafonné dépasse le prévu.",
        )
        parser.add_argument(
            '--top',
            type=int,
            default=None,
            help="Affiche uniquement les N modules avec le plus gros écart.",
        )

    def handle(self, *args, **options):
        modules_qs = Module.objects.all().select_related('secretariat__type')
        secretariat = options['secretariat']
        if secretariat:
            modules_qs = modules_qs.filter(secretariat__type__libelle__iexact=secretariat)

        lignes = []
        total_prevu = 0.0
        total_effectue_brut = 0.0
        total_effectue_plafonne = 0.0
        total_capa_planifiee = 0.0
        total_sessions_sans_horaires = 0

        for module in modules_qs:
            sessions = list(
                SessionModule.objects
                .filter(module=module)
                .exclude(demarree_le__isnull=True)
                .exclude(terminee_le__isnull=True)
                .only('demarree_le', 'terminee_le', 'heure_debut_prevue', 'heure_fin_prevue')
            )

            prevu_h = float(module.duree_prevue_heures or 0)
            effectue_brut_min = 0.0
            effectue_plafonne_min = 0.0
            capa_planifiee_min = 0.0
            sessions_sans_horaires = 0

            # Capacité planifiée (toutes sessions du module avec horaires).
            for s in SessionModule.objects.filter(
                module=module,
                heure_debut_prevue__isnull=False,
                heure_fin_prevue__isnull=False,
            ).only('heure_debut_prevue', 'heure_fin_prevue'):
                capa = _minutes_entre_heures(s.heure_debut_prevue, s.heure_fin_prevue)
                if capa and capa > 0:
                    capa_planifiee_min += capa

            for s in sessions:
                elapsed = (s.terminee_le - s.demarree_le).total_seconds() / 60
                if elapsed <= 0:
                    continue
                effectue_brut_min += elapsed
                plafond = _minutes_entre_heures(s.heure_debut_prevue, s.heure_fin_prevue)
                if plafond is None or plafond <= 0:
                    plafond = _MAX_DUREE_SESSION_MIN_DEFAUT
                    sessions_sans_horaires += 1
                effectue_plafonne_min += min(elapsed, plafond)

            ecart_h = effectue_plafonne_min / 60 - prevu_h

            lignes.append({
                'module': module,
                'prevu_h': prevu_h,
                'capa_planifiee_h': capa_planifiee_min / 60,
                'effectue_brut_h': effectue_brut_min / 60,
                'effectue_plafonne_h': effectue_plafonne_min / 60,
                'ecart_h': ecart_h,
                'sessions_sans_horaires': sessions_sans_horaires,
                'nb_sessions_terminees': len(sessions),
            })

            total_prevu += prevu_h
            total_effectue_brut += effectue_brut_min / 60
            total_effectue_plafonne += effectue_plafonne_min / 60
            total_capa_planifiee += capa_planifiee_min / 60
            total_sessions_sans_horaires += sessions_sans_horaires

        if options['depassements_only']:
            lignes = [l for l in lignes if l['ecart_h'] > 0]

        # Tri par écart décroissant
        lignes.sort(key=lambda l: l['ecart_h'], reverse=True)
        if options['top']:
            lignes = lignes[: options['top']]

        # Affichage
        header = (
            f"{'Module':<40} {'Sec.':<10} {'Prévu':>8} {'CapaPlan':>10} "
            f"{'EffBrut':>9} {'EffPlaf':>9} {'Écart':>8} {'#sansH':>7} {'#sess':>6}"
        )
        self.stdout.write(header)
        self.stdout.write('-' * len(header))
        for l in lignes:
            m = l['module']
            sec = ''
            try:
                sec = (m.secretariat.type.libelle if m.secretariat and m.secretariat.type else '') or ''
            except AttributeError:
                sec = ''
            label = (m.intitule or '')[:39]
            ligne = (
                f"{label:<40} {sec[:10]:<10} "
                f"{l['prevu_h']:>7.1f}h {l['capa_planifiee_h']:>9.1f}h "
                f"{l['effectue_brut_h']:>8.1f}h {l['effectue_plafonne_h']:>8.1f}h "
                f"{l['ecart_h']:>+7.1f}h {l['sessions_sans_horaires']:>7d} {l['nb_sessions_terminees']:>6d}"
            )
            style = self.style.WARNING if l['ecart_h'] > 0 else self.style.SUCCESS
            self.stdout.write(style(ligne))

        self.stdout.write('=' * len(header))
        self.stdout.write(self.style.SUCCESS(
            f"Totaux : prévu={total_prevu:.1f}h | "
            f"capa_planifiée={total_capa_planifiee:.1f}h | "
            f"effectué_brut={total_effectue_brut:.1f}h | "
            f"effectué_plafonné={total_effectue_plafonne:.1f}h | "
            f"écart={total_effectue_plafonne - total_prevu:+.1f}h | "
            f"sessions_sans_horaires={total_sessions_sans_horaires}"
        ))
