"""
Commande pour supprimer les participants et leurs inscriptions en masse.
Usage : python manage.py clear_participants --grade B --groupe "GROUPE 33" --formation "FORMATION EN ADMINISTRATION DE BASE"
"""
from django.core.management.base import BaseCommand
from formations.models import Participant, ModuleParticipant, Module


class Command(BaseCommand):
    help = 'Supprime les participants et leurs inscriptions (avec filtres optionnels)'

    def add_arguments(self, parser):
        parser.add_argument('--formation', type=str, help='Nom de la formation (ex: "FORMATION EN ADMINISTRATION DE BASE")')
        parser.add_argument('--grade', type=str, help='Grade (ex: B)')
        parser.add_argument('--groupe', type=str, help='Groupe (ex: "GROUPE 33")')
        parser.add_argument('--vague', type=str, help='Vague (ex: "VAGUE 2")')
        parser.add_argument('--secretariat', type=str, help='Nom du secrétariat')
        parser.add_argument('--all', action='store_true', help='SUPPRIMER TOUS LES PARTICIPANTS (⚠️ DANGER)')
        parser.add_argument('--dry-run', action='store_true', help='Simulation sans suppression')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        delete_all = options['all']

        if not any([options['formation'], options['grade'], options['groupe'],
                    options['vague'], options['secretariat'], delete_all]):
            self.stdout.write(self.style.ERROR(
                '❌ Spécifiez au moins un filtre (--formation, --grade, --groupe, --vague, --secretariat) ou --all'
            ))
            return

        # Build query
        if delete_all:
            participants = Participant.objects.all()
            self.stdout.write(self.style.WARNING('⚠️  Mode TOUS les participants activé'))
        else:
            filters = {}
            if options['grade']:
                filters['grade__iexact'] = options['grade']
            if options['groupe']:
                filters['groupe__iexact'] = options['groupe']
            if options['vague']:
                filters['vague__iexact'] = options['vague']
            if options['secretariat']:
                filters['secretariat__nom__icontains'] = options['secretariat']

            participants = Participant.objects.filter(**filters)

            # Filtre par formation via ModuleParticipant
            if options['formation']:
                participant_ids = ModuleParticipant.objects.filter(
                    module__formation__formation__iexact=options['formation']
                ).values_list('participant_id', flat=True)
                participants = participants.filter(id__in=participant_ids)

        count = participants.count()

        if count == 0:
            self.stdout.write(self.style.WARNING('Aucun participant trouvé avec ces critères'))
            return

        self.stdout.write(f'\n📊 Participants trouvés : {count}')
        self.stdout.write(f'   Filtres : {filters}')
        if options['formation']:
            self.stdout.write(f'   Formation : {options["formation"]}')

        if dry_run:
            self.stdout.write(self.style.WARNING('\n🔸 DRY RUN - Aucune suppression effectuée'))
            # Afficher les 10 premiers
            self.stdout.write('\nExemples de participants qui seraient supprimés :')
            for p in participants[:10]:
                inscriptions = ModuleParticipant.objects.filter(participant=p).count()
                self.stdout.write(f'  - {p.matricule} : {p.nom} {p.prenom} ({inscriptions} inscriptions)')
            if count > 10:
                self.stdout.write(f'  ... et {count - 10} autres')
        else:
            # Compter les inscriptions liées
            inscriptions = ModuleParticipant.objects.filter(participant__in=participants).count()

            self.stdout.write(self.style.WARNING(f'\n⚠️  Vous allez supprimer :'))
            self.stdout.write(f'   - {count} participants')
            self.stdout.write(f'   - {inscriptions} inscriptions liées')

            confirm = input('\nTapez "SUPPRIMER" pour confirmer : ')
            if confirm != 'SUPPRIMER':
                self.stdout.write(self.style.ERROR('❌ Annulé'))
                return

            # Supprimer d'abord les inscriptions (CASCADE devrait le faire, mais sécurité)
            ModuleParticipant.objects.filter(participant__in=participants).delete()
            # Puis les participants
            deleted, _ = participants.delete()

            self.stdout.write(self.style.SUCCESS(f'\n✅ Suppression terminée :'))
            self.stdout.write(f'   - {deleted.get("formations.Participant", 0)} participants supprimés')
            self.stdout.write(f'   - {deleted.get("formations.ModuleParticipant", 0)} inscriptions supprimées')
