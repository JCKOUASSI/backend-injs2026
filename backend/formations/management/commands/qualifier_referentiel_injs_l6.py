"""L6 — Qualification du référentiel INJS-LMD (non destructif).

Périmètre strict : la qualification ``formations.RefFormation`` (L6 §7) et, au
besoin, la création des coquilles de cycles manquantes pour les 8 filières
validées (L6 §6). Ne crée JAMAIS : parcours, UE, ECUE, maquettes, codes
officiels, crédits ventilés, affectations (L6 §12, §13).

Idempotent, traçable (``--dry-run``), non destructif : aucune suppression, aucun
renommage d'un cycle legacy. La source métier unique est
``formations.referentiel_injs_l6`` (A-4.5 §2). Complète — sans remplacer — la
commande A-4.4 ``import_referentiel_injs_lmd``.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from formations.models import RefFormation
from formations.referentiel_injs_l6 import (
    CORPUS_INJS,
    CORPUS_LEGACY,
    FILIERES_INJS,
    SOURCE_A45,
    signaler_ecarts,
)

SOURCE_LEGACY = 'A-4.3ter §5.3 (O6)'


class _AnnulationDryRun(Exception):
    """Interrompt la transaction pour simuler sans écrire."""


class Command(BaseCommand):
    help = "L6 — qualifie les cycles de formation INJS vs legacy (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Simule la qualification et la création des coquilles manquantes.',
        )

    def handle(self, *args, **options):
        simule = options['dry_run']
        c = {'CREE': 0, 'QUALIFIE': 0, 'DEJA': 0, 'LEGACY': 0, 'INCONNU': 0}
        lignes = []
        try:
            with transaction.atomic():
                self._qualifier_existantes(c, lignes)
                self._creer_coquilles_manquantes(c, lignes)
                self._controler(c, lignes)
                if simule:
                    raise _AnnulationDryRun()
        except _AnnulationDryRun:
            pass

        entete = ('Simulation --dry-run — aucune écriture'
                  if simule else 'Qualification L6 terminée')
        self.stdout.write(self.style.MIGRATE_HEADING(f'L6 — {entete}'))
        for ligne in lignes:
            self.stdout.write(f'  {ligne}')
        self.stdout.write('  TOTAL ' + ' | '.join(f'{k}={v}' for k, v in c.items()))

    def _qualifier_existantes(self, c, lignes):
        """Affecte périmètre / code filière / source aux lignes déjà en base."""
        for obj in RefFormation.objects.all().order_by('id'):
            code_filiere = CORPUS_INJS.get(obj.intitule)
            if code_filiere:
                maj = self._ecrire(obj, RefFormation.Perimetre.INJS,
                                   code_filiere, SOURCE_A45)
                if maj:
                    lignes.append(f'QUALIFIÉ  « {obj.intitule} » → INJS ({code_filiere}).')
                    c['QUALIFIE'] += 1
                else:
                    lignes.append(f'DÉJÀ     « {obj.intitule} » → INJS ({code_filiere}).')
                    c['DEJA'] += 1
            elif obj.intitule in CORPUS_LEGACY:
                maj = self._ecrire(obj, RefFormation.Perimetre.LEGACY, '', SOURCE_LEGACY)
                if maj:
                    lignes.append(f'LEGACY    « {obj.intitule} » → hors périmètre INJS.')
                    c['LEGACY'] += 1
                else:
                    lignes.append(f'DÉJÀ     « {obj.intitule} » → LEGACY.')
                    c['DEJA'] += 1
            else:
                c['INCONNU'] += 1
                lignes.append(
                    f'INCONNU   « {obj.intitule} » — origine non établie par la source : '
                    'laissé NON_DETERMINE (aucune valeur inventée, §7).',
                )

    @staticmethod
    def _ecrire(obj, perimetre, filiere_code, source):
        """N'écrit que les champs réellement différents ; retourne la liste."""
        maj = []
        if obj.perimetre != perimetre:
            obj.perimetre = perimetre
            maj.append('perimetre')
        if obj.filiere_code != filiere_code:
            obj.filiere_code = filiere_code
            maj.append('filiere_code')
        if obj.source != source:
            obj.source = source
            maj.append('source')
        if maj:
            obj.save(update_fields=maj)
        return maj

    def _creer_coquilles_manquantes(self, c, lignes):
        """Crée les cycles manquants, sans renseigner que des valeurs attestées.

        Les métadonnées de diplôme/durée ne sont écrites que si la source les
        documente pour la filière concernée (A-4.5 §2/§3) ; sinon la ligne est
        créée « nue » et le rapport le signale comme à confirmer.
        """
        diplomes = {code: d for code, _s, _l, _e, _d, d in FILIERES_INJS}
        domaines = {code: dom for code, _s, _l, _e, dom, _d in FILIERES_INJS}
        for intitule, code_filiere in CORPUS_INJS.items():
            if RefFormation.objects.filter(intitule=intitule).exists():
                continue
            attestes = diplomes[code_filiere]
            # ES/MS/APA/EM sont documentés « Licence + Master » (A-4.5 §3) :
            # deux cycles. Les filières ENSEP ne le sont pas : une seule
            # coquille, sans découpage inventé.
            suffixes = [''] if len(attestes) == 1 else [' — LICENCE', ' — MASTER']
            for suffixe in suffixes:
                nouvel_intitule = f'{intitule}{suffixe}'
                if RefFormation.objects.filter(intitule=nouvel_intitule).exists():
                    continue
                type_diplome = attestes[0] if not suffixe else attestes[1 - len(attestes)]
                duree = 3 if type_diplome == 'LICENCE' else 2
                RefFormation.objects.create(
                    intitule=nouvel_intitule,
                    perimetre=RefFormation.Perimetre.INJS,
                    filiere_code=code_filiere,
                    source=SOURCE_A45,
                    type_diplome=type_diplome,
                    domaine=domaines[code_filiere],
                    duree_annees=duree,
                    nb_semestres=6 if type_diplome == 'LICENCE' else 4,
                    nb_credites=duree * 60,
                )
                lignes.append(
                    f'CRÉÉ     « {nouvel_intitule} » ({type_diplome}, {code_filiere}).')
                c['CREE'] += 1

    def _controler(self, c, lignes):
        rapport = signaler_ecarts()
        detail_manquantes = (f' — manquantes : {", ".join(rapport["filieres_manquantes"])}'
                             if rapport['filieres_manquantes'] else '')
        lignes.append(
            f'CONTRÔLE filières chargées {rapport["nb_filieres_chargees"]}'
            f'/{rapport["nb_filieres_attendues"]}{detail_manquantes}',
        )
        if rapport['cycles_etrangers_inclus']:
            lignes.append(
                'ALERTE   cycles étrangers présents dans le périmètre INJS : '
                + ', '.join(rapport['cycles_etrangers_inclus']),
            )
        else:
            lignes.append('CONTRÔLE 0 cycle CPFAE/DEBUG dans le périmètre INJS.')
        lignes.append(
            f'CONTRÔLE {rapport["nb_cycles_injs"]} cycles INJS, '
            f'{rapport["nb_cycles_legacy"]} cycles legacy conservés hors périmètre.',
        )
        lignes.append('SKIPPED  UE/ECUE/parcours/maquettes : non créés (§12, §13).')
        lignes.append('SKIPPED  aucune suppression : données CPFAE conservées (§9).')
