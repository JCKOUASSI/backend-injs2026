"""
Commande : python manage.py diag_module_auditeurs

Diagnostique le nombre d'auditeurs attendus pour un (ou plusieurs) module(s).
Pour chaque module sélectionné, affiche :

  - le total d'inscriptions (table ModuleParticipant)
  - la répartition de ces inscrits par grade / groupe / secrétariat du
    Participant (pour repérer un module "fourre-tout")
  - la liste des modules frères (même intitulé + grade + secrétariat) avec
    leur effectif respectif (utile pour voir si les autres groupes sont
    restés vides après un mauvais import)

Usage :

  python manage.py diag_module_auditeurs --module-id 266
  python manage.py diag_module_auditeurs \\
      --intitule "Culture Civique" --grade A3 \\
      --secretariat "FAB A" --groupe "GROUPE 5"
  python manage.py diag_module_auditeurs --secretariat "FAB A" --grade A3 --top 5
"""

from collections import Counter

from django.core.management.base import BaseCommand, CommandError

from formations.models import Module, ModuleParticipant


class Command(BaseCommand):
    help = (
        "Diagnostique le nombre d'auditeurs attendus pour un module "
        "(répartition par grade / groupe / secrétariat du participant)."
    )

    def add_arguments(self, parser):
        parser.add_argument('--module-id', type=int, default=None,
                            help='ID du module à diagnostiquer.')
        parser.add_argument('--intitule', type=str, default=None,
                            help="Filtre exact (insensible à la casse) sur l'intitulé.")
        parser.add_argument('--grade', type=str, default=None,
                            help="Filtre exact (insensible à la casse) sur le grade.")
        parser.add_argument('--secretariat', type=str, default=None,
                            help="Filtre 'icontains' sur le nom du secrétariat.")
        parser.add_argument('--groupe', type=str, default=None,
                            help="Filtre 'icontains' sur le champ groupe du module.")
        parser.add_argument('--top', type=int, default=None,
                            help="N'affiche que les N modules les plus chargés.")

    def handle(self, *args, **options):
        qs = Module.objects.select_related('secretariat').all()
        if options['module_id']:
            qs = qs.filter(id=options['module_id'])
        if options['intitule']:
            qs = qs.filter(intitule__iexact=options['intitule'])
        if options['grade']:
            qs = qs.filter(grade__iexact=options['grade'])
        if options['secretariat']:
            qs = qs.filter(secretariat__nom__icontains=options['secretariat'])
        if options['groupe']:
            qs = qs.filter(groupe__icontains=options['groupe'])

        modules = list(qs)
        if not modules:
            raise CommandError("Aucun module ne correspond aux filtres.")

        nb_par_module = {
            m.id: ModuleParticipant.objects.filter(module=m).count()
            for m in modules
        }
        modules.sort(key=lambda m: nb_par_module.get(m.id, 0), reverse=True)
        if options['top']:
            modules = modules[: options['top']]

        for m in modules:
            self._diag_module(m, nb_par_module[m.id])

    def _diag_module(self, m, total):
        sec_nom = m.secretariat.nom if m.secretariat else '(aucun)'
        self.stdout.write('=' * 80)
        self.stdout.write(self.style.SUCCESS(f"Module #{m.id} | {m.intitule}"))
        self.stdout.write(
            f"  grade={m.grade!r}  groupe={m.groupe!r}  vague={m.vague!r}  "
            f"secretariat={sec_nom!r}"
        )
        self.stdout.write(
            f"  dates : {m.date_debut} -> {m.date_fin}   statut={m.statut}"
        )
        self.stdout.write(self.style.WARNING(
            f"  Total inscrits (ModuleParticipant) : {total}"
        ))

        if total > 0:
            mps = (
                ModuleParticipant.objects
                .filter(module=m)
                .select_related('participant__secretariat')
            )
            c_grade = Counter(
                (mp.participant.grade or '(vide)') for mp in mps
            )
            c_groupe = Counter(
                (mp.participant.groupe or '(vide)') for mp in mps
            )
            c_sec = Counter(
                (mp.participant.secretariat.nom if mp.participant.secretariat else '(aucun)')
                for mp in mps
            )

            self._print_counter('Répartition par grade        ', c_grade, width=20)
            self._print_counter('Répartition par groupe       ', c_groupe, width=20)
            self._print_counter('Répartition par secrétariat  ', c_sec, width=40)

            # Anomalie : participant dont (grade, groupe) ne colle pas au module.
            mismatch = 0
            module_grade = (m.grade or '').strip().upper()
            module_groupe = (m.groupe or '').strip().upper()
            for mp in mps:
                p_grade = (mp.participant.grade or '').strip().upper()
                p_groupe = (mp.participant.groupe or '').strip().upper()
                if module_grade and p_grade and p_grade != module_grade:
                    mismatch += 1
                    continue
                if module_groupe and p_groupe and p_groupe != module_groupe:
                    mismatch += 1
            if mismatch:
                self.stdout.write(self.style.ERROR(
                    f"  ⚠  {mismatch} inscrit(s) avec grade/groupe différent du module"
                ))

        # Modules frères (même intitulé + grade + secrétariat).
        if m.grade and m.intitule and m.secretariat_id:
            freres = (
                Module.objects
                .filter(
                    intitule__iexact=m.intitule,
                    grade__iexact=m.grade,
                    secretariat_id=m.secretariat_id,
                )
                .exclude(id=m.id)
                .order_by('groupe', 'date_debut')
            )
            if freres.exists():
                self.stdout.write('  Modules frères (même intitulé/grade/secrétariat) :')
                for f in freres:
                    nb = ModuleParticipant.objects.filter(module=f).count()
                    groupe_label = f.groupe or '(vide)'
                    self.stdout.write(
                        f"    #{f.id} groupe={groupe_label:<15} "
                        f"dates={f.date_debut}->{f.date_fin}  inscrits={nb}"
                    )

    def _print_counter(self, label, counter, width):
        self.stdout.write(f'  {label}:')
        for k, v in sorted(counter.items(), key=lambda kv: -kv[1]):
            self.stdout.write(f"    {k:<{width}} : {v}")
