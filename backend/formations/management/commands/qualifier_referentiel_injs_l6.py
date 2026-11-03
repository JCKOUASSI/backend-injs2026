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


def _cycle_de_intitule(intitule):
    """Cycle porté par l'intitulé (« … — LICENCE » → ``LICENCE``), sinon None."""
    for cycle in ('LICENCE', 'MASTER', 'DOCTORAT'):
        if intitule.endswith(f' — {cycle}'):
            return cycle
    return None


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
                maj += self._completer_metadonnees(obj, code_filiere)
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
    def _completer_metadonnees(obj, code_filiere):
        """Renseigne les métadonnées ATTESTÉES encore vides (jamais en écrasement).

        Les coquilles créées par l'import structurel A-4.4 portent le bon
        intitulé mais laissent ``type_diplome``/``duree_annees``/
        ``nb_semestres``/``nb_credites`` NULL. Le cycle, lui, est attesté par
        l'intitulé lui-même et par A-4.5 §2/§3 : il peut donc être qualifié.
        Aucune valeur déjà renseignée n'est modifiée.
        """
        attestes = {code: d for code, _s, _l, _e, _d, d in FILIERES_INJS}[code_filiere]
        domaines = {code: dom for code, _s, _l, _e, dom, _d in FILIERES_INJS}
        maj = []
        if not obj.type_diplome:
            cycle = _cycle_de_intitule(obj.intitule)
            if cycle in attestes:
                obj.type_diplome = cycle
                maj.append('type_diplome')
        if obj.type_diplome in attestes:
            duree = 3 if obj.type_diplome == 'LICENCE' else 2
            if not obj.duree_annees:
                obj.duree_annees = duree
                maj.append('duree_annees')
            if not obj.nb_semestres:
                obj.nb_semestres = duree * 2
                maj.append('nb_semestres')
            if not obj.nb_credites:
                obj.nb_credites = duree * 60
                maj.append('nb_credites')
        if not obj.domaine and domaines[code_filiere]:
            obj.domaine = domaines[code_filiere]
            maj.append('domaine')
        if maj:
            obj.save(update_fields=maj)
        return maj

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
            # Les intitulés de CORPUS_INJS portent DÉJÀ le cycle quand la
            # filière en compte plusieurs (« … — LICENCE », « … — MASTER »).
            # On ne re-suffixe donc jamais : le suffixer une seconde fois
            # produisait quatre lignes par filière, toutes typées MASTER.
            type_diplome = _cycle_de_intitule(intitule) or attestes[0]
            if type_diplome not in attestes:
                lignes.append(
                    f'SKIPPED  « {intitule} » — cycle {type_diplome} non attesté '
                    f'pour {code_filiere}.')
                c['SKIPPED'] += 1
                continue
            duree = 3 if type_diplome == 'LICENCE' else 2
            RefFormation.objects.create(
                intitule=intitule,
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
                f'CRÉÉ     « {intitule} » ({type_diplome}, {code_filiere}).')
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
