"""Contrôle de cohérence des référentiels INJS (mission 53).

Le commandement ne corrige rien : il **constate**. Chaque anomalie est
identifiée, localisée et accompagnée de sa cause probable, afin qu'une
correction soit décidée sur pièces et non par un nettoyage automatique.

Codes d'anomalie
----------------
A-53-01  Doublon sémantique entre deux tables (aucune fusion automatique).
A-53-02  Filière sans code dossier : le rattachement des cycles est impossible.
A-53-03  Cycle sans filière métier rattachée.
A-53-04  Module officiel rattaché à un cycle d'une autre filière.
A-53-05  Valeur sans provenance documentaire (`source_document` vide).
A-53-06  Valeur « à renseigner » alors que la source existe.
A-53-07  Sélecteur du registre pointant un modèle absent du registre.

Usage :
    python manage.py verifier_coherence_referentiels
    python manage.py verifier_coherence_referentiels --strict   # code de sortie 1
"""

from django.core.management.base import BaseCommand

from formations.models import RefFormation
from referentiels.models import RefFiliere, RefModuleOfficiel
from referentiels.registre import REGISTRE, modele_de


class Anomalie:
    def __init__(self, code, gravite, message, objet=''):
        self.code = code
        self.gravite = gravite
        self.message = message
        self.objet = objet

    def __str__(self):
        return f'[{self.code}] ({self.gravite}) {self.objet} — {self.message}'


def _nommer(valeur):
    """Identifie une ligne par son champ parlant, sans supposer son nom."""
    for champ in ('code', 'libelle', 'nom', 'intitule', 'intitule_module'):
        texte = getattr(valeur, champ, '')
        if texte:
            return str(texte)
    return f'#{valeur.pk}'


class Command(BaseCommand):
    help = 'Contrôle de cohérence des référentiels (lecture seule).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--strict', action='store_true',
            help='Retourne un code de sortie non nul si une anomalie est détectée.',
        )

    def handle(self, *args, **options):
        anomalies = []
        anomalies.extend(self._a01_doublons_semantiques())
        anomalies.extend(self._a02_filieres_sans_code())
        anomalies.extend(self._a03_cycles_sans_filiere())
        anomalies.extend(self._a04_modules_mal_rattaches())
        anomalies.extend(self._a05_sans_source())
        anomalies.extend(self._a07_selecteurs_non_resolus())

        if not anomalies:
            self.stdout.write(self.style.SUCCESS('Aucune anomalie détectée.'))
            return

        par_code = {}
        for anomalie in anomalies:
            par_code.setdefault(anomalie.code, []).append(anomalie)
        for code in sorted(par_code):
            groupe = par_code[code]
            self.stdout.write(self.style.WARNING(f'\n{code} — {len(groupe)} occurrence(s)'))
            for anomalie in groupe[:20]:
                self.stdout.write(f'  {anomalie}')
            if len(groupe) > 20:
                self.stdout.write(f'  … et {len(groupe) - 20} autre(s)')

        self.stdout.write(self.style.HTTP_INFO(
            f'\nTotal : {len(anomalies)} anomalie(s) sur {len(par_code)} famille(s).'
        ))
        if options['strict']:
            raise SystemExit(1)

    # ── Contrôles ─────────────────────────────────────────────────────────
    def _a01_doublons_semantiques(self):
        """Deux tables qui prétendent décrire la même nomenclature."""
        from scolarite.models import TypeFormation

        constats = []
        heritage = {t.libelle.strip().lower() for t in TypeFormation.objects.all()}
        for valeur in modele_de(REGISTRE['types-cursus'])._default_manager.all():
            if valeur.libelle.strip().lower() in heritage:
                constats.append(Anomalie(
                    'A-53-01', 'majeure',
                    'même libellé présent dans scolarite.TypeFormation et RefTypeCursus : '
                    'une seule table doit faire foi (fusion planifiée, aucune suppression auto).',
                    valeur.libelle,
                ))
        return constats

    def _a02_filieres_sans_code(self):
        return [
            Anomalie('A-53-02', 'majeure',
                     'aucun code dossier (F01…F08) : les cycles ne peuvent pas être rattachés.',
                     filiere.code)
            for filiere in RefFiliere.objects.filter(code_dossier='')
        ]

    def _a03_cycles_sans_filiere(self):
        return [
            Anomalie('A-53-03', 'mineure',
                     'cycle sans filière métier rattachée (ligne héritée).',
                     cycle.intitule)
            for cycle in RefFormation.objects.filter(filiere__isnull=True)
        ]

    def _a04_modules_mal_rattaches(self):
        constats = []
        for module in RefModuleOfficiel.objects.select_related('formation__filiere'):
            filiere = module.formation.filiere
            if filiere is None:
                constats.append(Anomalie(
                    'A-53-04', 'majeure',
                    'module rattaché à un cycle sans filière : provenance invérifiable.',
                    module.libelle,
                ))
            elif filiere.code != module.filiere_code:
                constats.append(Anomalie(
                    'A-53-04', 'majeure',
                    f'module de la filière {module.filiere_code} rattaché au cycle '
                    f'de la filière {filiere.code}.',
                    module.libelle,
                ))
        return constats

    def _a05_sans_source(self):
        constats = []
        for slug, entree in REGISTRE.items():
            if not entree.get('modele'):
                continue
            modele = modele_de(entree)
            champs = {f.name for f in modele._meta.get_fields()}
            if 'source_document' not in champs:
                continue
            for valeur in modele._default_manager.filter(source_document=''):
                constats.append(Anomalie(
                    'A-53-05', 'majeure',
                    f'référentiel « {entree["libelle"]} » : aucune source documentaire.',
                    _nommer(valeur),
                ))
        return constats

    def _a07_selecteurs_non_resolus(self):
        modeles = {
            f'{modele_de(e)._meta.app_label}.{modele_de(e)._meta.model_name}'
            for e in REGISTRE.values() if e.get('modele')
        }
        constats = []
        for slug, entree in REGISTRE.items():
            if not entree.get('modele'):
                continue
            modele = modele_de(entree)
            for fk in entree['selecteurs']:
                cible = modele._meta.get_field(fk).related_model
                cle = f'{cible._meta.app_label}.{cible._meta.model_name}'
                if cle not in modeles:
                    constats.append(Anomalie(
                        'A-53-07', 'majeure',
                        f'sélecteur « {fk} » vers {cle}, absent du registre : '
                        'le front ne pourra pas charger ses options.',
                        slug,
                    ))
        return constats
