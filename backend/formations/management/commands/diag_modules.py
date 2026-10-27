"""
Diagnostic des modules existants pour vérifier la correspondance avec les critères d'import.
Usage : python manage.py diag_modules --formation "FORMATION EN ADMINISTRATION DE BASE"
"""
from django.core.management.base import BaseCommand
from formations.models import Module, Formation


class Command(BaseCommand):
    help = 'Diagnostic des modules existants'

    def add_arguments(self, parser):
        parser.add_argument('--formation', type=str, help='Nom de la formation')
        parser.add_argument('--grade', type=str, help='Grade (ex: B)')
        parser.add_argument('--groupe', type=str, help='Groupe (ex: GROUPE 33)')

    def handle(self, *args, **options):
        formation_name = options.get('formation')
        grade_filter = options.get('grade')
        groupe_filter = options.get('groupe')

        # Liste toutes les formations
        formations = Formation.objects.all()
        self.stdout.write(self.style.HTTP_INFO(f'\n📚 Formations en base ({formations.count()}) :'))
        for f in formations[:20]:
            modules_count = f.modules.count()
            self.stdout.write(f'  - "{f.formation}" ({modules_count} modules)')

        # Si formation spécifiée, détail des modules
        if formation_name:
            try:
                formation = Formation.objects.filter(formation__iexact=formation_name).first()
                if not formation:
                    self.stdout.write(self.style.ERROR(f'\n❌ Formation "{formation_name}" non trouvée'))
                    # Recherche approximative
                    approx = Formation.objects.filter(formation__icontains=formation_name.split()[0]).first()
                    if approx:
                        self.stdout.write(f'   Peut-être vouliez-vous : "{approx.formation}" ?')
                    return

                modules = formation.modules.all()
                if grade_filter:
                    modules = modules.filter(grade__iexact=grade_filter)
                if groupe_filter:
                    modules = modules.filter(groupe__iexact=groupe_filter)

                self.stdout.write(self.style.HTTP_INFO(
                    f'\n📋 Modules pour "{formation.formation}" ({modules.count()}) :'
                ))

                for m in modules.order_by('groupe', 'intitule'):
                    self.stdout.write(
                        f'  - {m.intitule}\n'
                        f'    grade="{m.grade}" groupe="{m.groupe}" vague="{m.vague}"'
                    )

                # Vérifier si des modules sans vague existent
                sans_vague = modules.filter(vague='').count()
                if sans_vague:
                    self.stdout.write(self.style.WARNING(
                        f'\n⚠️  {sans_vague} modules n\'ont pas de vague définie'
                    ))

                # Statistiques par groupe
                self.stdout.write(self.style.HTTP_INFO('\n📊 Statistiques par groupe :'))
                from django.db.models import Count
                stats = formation.modules.values('groupe', 'grade', 'vague').annotate(
                    count=Count('id')
                ).order_by('groupe')
                for s in stats:
                    self.stdout.write(
                        f'  - groupe="{s["groupe"]}" grade="{s["grade"]}" '
                        f'vague="{s["vague"]}" : {s["count"]} modules'
                    )

            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Erreur : {e}'))

        # Vérification spécifique : modules avec grade=B, groupe=GROUPE 33, vague=VAGUE 2
        self.stdout.write(self.style.HTTP_INFO('\n🔍 Recherche spécifique :'))
        test_filters = {'grade__iexact': 'B', 'groupe__iexact': 'GROUPE 33', 'vague__iexact': 'VAGUE 2'}
        test_modules = Module.objects.filter(**test_filters)
        self.stdout.write(f'  grade=B groupe="GROUPE 33" vague="VAGUE 2" : {test_modules.count()} modules')

        # Sans vague
        test_modules_sans_vague = Module.objects.filter(
            grade__iexact='B', groupe__iexact='GROUPE 33', vague=''
        )
        self.stdout.write(f'  grade=B groupe="GROUPE 33" vague="" : {test_modules_sans_vague.count()} modules')

        # Avec formation spécifique
        if formation_name:
            complete_filter = {
                'formation__formation__iexact': formation_name,
                'grade__iexact': 'B',
                'groupe__iexact': 'GROUPE 33',
            }
            with_vague = Module.objects.filter(**complete_filter, vague__iexact='VAGUE 2')
            without_vague = Module.objects.filter(**complete_filter, vague='')
            self.stdout.write(f'\n  Dans "{formation_name}" :')
            self.stdout.write(f'    - avec vague="VAGUE 2" : {with_vague.count()} modules')
            self.stdout.write(f'    - avec vague="" : {without_vague.count()} modules')
