"""Contrôle de cohérence du module Référentiels (mission 53).

La commande ne modifie rien : elle mesure et affiche. Trois familles de
constats, toutes issues d'écarts observables entre le registre, la base et le
code des autres modules :

1. **Provenance** — valeurs sans `source_document` ou restées « à renseigner » ;
2. **Duplication de référentiel** — listes métier codées en dur dans d'autres
   modules et divergentes du référentiel de la base ;
3. **Rattachement** — clés étrangères du référentiel non renseignées alors que
   l'information textuelle existe.

Sortie lisible en console ; `--strict` renvoie un code de retour non nul dès
qu'un constat est relevé (utile en CI).
"""
from django.core.management.base import BaseCommand
from django.db.models import Count

from formations.models import RefFormation
from referentiels.models import (
    RefEcole,
    RefFiliere,
    RefMention,
    RefStatutVague,
    RefTypeCursus,
    RefTypeEnseignement,
)


class Command(BaseCommand):
    help = 'Contrôle de cohérence lecture seule du module Référentiels.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--strict', action='store_true',
            help='Code de retour 1 si au moins un constat est relevé.',
        )

    # ── Famille 1 : provenance ──────────────────────────────────────────
    def _provenance(self, constats):
        modeles = [
            RefEcole, RefMention, RefFiliere, RefTypeCursus,
            RefStatutVague, RefTypeEnseignement,
        ]
        self.stdout.write(self.style.MIGRATE_HEADING('1. Provenance des valeurs'))
        for modele in modeles:
            nom = modele._meta.verbose_name_plural
            total = modele.objects.count()
            sans_source = modele.objects.filter(source_document='').count()
            a_renseigner = modele.objects.filter(fiabilite='A_RENSEIGNER').count()
            ligne = (
                f'   {nom:38} {total:>4} valeur(s) · sans source : {sans_source:>3}'
                f' · fiabilité à renseigner : {a_renseigner:>3}'
            )
            if sans_source or a_renseigner:
                constats.append(
                    f'{nom} : {sans_source} sans source, {a_renseigner} à renseigner',
                )
                self.stdout.write(self.style.WARNING(ligne))
            else:
                self.stdout.write(ligne)

    # ── Famille 2 : duplication de référentiel ─────────────────────────
    def _duplications(self, constats):
        self.stdout.write(self.style.MIGRATE_HEADING('2. Duplication de référentiel'))
        try:
            from scolarite.pedagogie_validateur import FILIERES as FILIERES_CODE
        except Exception:  # pragma: no cover — module optionnel selon branche
            FILIERES_CODE = {}

        en_base = set(RefFiliere.objects.values_list('code', flat=True))
        en_dur = set(FILIERES_CODE)
        if en_dur:
            manquantes = en_dur - en_base
            en_trop = en_base - en_dur
            if manquantes or en_trop:
                constats.append('liste de filières codée en dur divergente')
                self.stdout.write(self.style.WARNING(
                    f'   scolarite.pedagogie_validateur.FILIERES diverge du référentiel\n'
                    f'     absentes de la base : {sorted(manquantes) or "—"}\n'
                    f'     absentes du code   : {sorted(en_trop) or "—"}',
                ))
            else:
                self.stdout.write(
                    f'   liste de filières codée en dur : {len(en_dur)} code(s), '
                    'alignée sur la base',
                )
        self.stdout.write(
            '   valeurs en base : ' + ', '.join(sorted(en_base)) if en_base
            else '   valeurs en base : aucune (import non exécuté ?)',
        )

    # ── Famille 3 : rattachement ───────────────────────────────────────
    def _rattachements(self, constats):
        self.stdout.write(self.style.MIGRATE_HEADING('3. Rattachement des formations'))
        orphelines = RefFormation.objects.filter(filiere__isnull=True)
        total = RefFormation.objects.count()
        if orphelines.exists():
            constats.append(f'{orphelines.count()} formation(s) sans filière')
            self.stdout.write(self.style.WARNING(
                f'   {orphelines.count()} formation(s) sur {total} sans filière '
                'rattachée : ' + ', '.join(list(orphelines.values_list('intitule', flat=True)[:5])),
            ))
        else:
            self.stdout.write(f'   {total} formation(s), toutes rattachées à une filière')

        doublons = (
            RefFormation.objects.values('intitule')
            .annotate(n=Count('id')).filter(n__gt=1)
        )
        if doublons:
            constats.append(f'{doublons.count()} intitulé(s) de formation en doublon')
            self.stdout.write(self.style.WARNING(
                '   intitulés en doublon : '
                + ', '.join(d['intitule'] for d in doublons[:5]),
            ))

    def handle(self, *args, **options):
        constats = []
        self.stdout.write(self.style.MIGRATE_HEADING(
            'Contrôle de cohérence — module Référentiels',
        ))
        self._provenance(constats)
        self.stdout.write('')
        self._duplications(constats)
        self.stdout.write('')
        self._rattachements(constats)
        self.stdout.write('')

        if constats:
            self.stdout.write(self.style.WARNING(
                f'{len(constats)} constat(s) relevé(s) :',
            ))
            for constat in constats:
                self.stdout.write(f'   • {constat}')
            if options['strict']:
                raise SystemExit(1)
        else:
            self.stdout.write(self.style.SUCCESS('Aucun constat : référentiels cohérents.'))
