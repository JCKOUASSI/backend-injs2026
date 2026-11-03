"""Configure l'offre de formation INJS (maquettes UE/ECUE) depuis le référentiel.

Commande **idempotente** et **non destructive** : elle peut être relancée sans
créer de doublon, ne supprime jamais rien et n'active aucune maquette.

Source de vérité
----------------
``scolarite/data/referentiel_offre_formation.json``, produit par
``scripts/extraire_referentiel_offre_formation.py`` à partir de
``dossier_trvx/RÉFÉRENTIEL EXHAUSTIF DE L'OFFRE DE FORMATION.docx``.

Ce que la commande écrit
------------------------
Pour les filières dont le référentiel publie une maquette (F01 EM, F02 APA,
F03 ES, F04 MS) :

* une ``Maquette`` par niveau (L1, L2, L3, M1, M2), en statut **BROUILLON** ;
* les ``UE`` de chaque semestre, avec l'intitulé et les crédits officiels ;
* les ``ECUE`` de chaque UE.

Ce qu'elle n'écrit jamais
-------------------------
* aucun code officiel d'UE/ECUE : le référentiel n'en publie pas. Les codes
  sont **techniques** et dérivés du rang (``EM-S1-UE01``), conformément à la
  note de provenance du jeu de données ;
* aucun volume horaire (CM/TD/TP non publiés par le référentiel) ;
* aucun semestre absent de la source (MS S8), aucune UE inventée ;
* aucun parcours : le référentiel décrit des filières, pas des parcours ;
* aucune activation de maquette : la validation et l'activation relèvent
  d'une décision institutionnelle, pas d'un import de données.

Exemples
--------
    python manage.py configurer_referentiel_injs --dry-run
    python manage.py configurer_referentiel_injs
    python manage.py configurer_referentiel_injs --annee 2026-2027
"""

import json
import re
import unicodedata
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from formations.models import RefFormation
from scolarite.models import (
    ECUE, FamilleModule, Maquette, Niveau, Semestre, StatutEtudiant, UE,
)

#: Cycle porté par chaque niveau (L1–L3 → Licence, M1–M2 → Master).
CYCLE_PAR_NIVEAU = {
    'L1': 'LICENCE', 'L2': 'LICENCE', 'L3': 'LICENCE',
    'M1': 'MASTER', 'M2': 'MASTER',
}

#: Répartition officielle des semestres par niveau (LMD, 5 ans = S1 → S10).
NIVEAU_PAR_SEMESTRE = {
    1: 'L1', 2: 'L1',
    3: 'L2', 4: 'L2',
    5: 'L3', 6: 'L3',
    7: 'M1', 8: 'M1',
    9: 'M2', 10: 'M2',
}

#: Chemin du jeu de données produit par le script d'extraction.
DONNEES = Path(__file__).resolve().parents[2] / 'data' / 'referentiel_offre_formation.json'


#: Statut du classeur → code technique stable et lisible.
CODES_STATUT = {
    'Pré-inscrit': 'PRE_INSCRIT',
    'Inscrit': 'INSCRIT',
    'En cours': 'EN_COURS',
    'Admis(e)': 'ADMIS',
    'Redouble': 'REDOUBLE',
    'Ajourné(e)': 'AJOURNE',
    'Exclu(e)': 'EXCLU',
    'Diplômé(e)': 'DIPLOME',
    'Abandon': 'ABANDON',
}


def _normaliser_libelle(libelle):
    """Normalise un libellé pour rapprocher « Diplômé(e) » et « Diplômé »."""
    base = unicodedata.normalize('NFD', (libelle or '').lower())
    base = ''.join(c for c in base if unicodedata.category(c) != 'Mn')
    base = base.replace('(e)', '').replace('ée', 'e')
    return re.sub(r'[^a-z0-9]+', '', base)


def _code_statut(libelle):
    """Code technique d'un statut ; repli slug si le libellé est inattendu."""
    if libelle in CODES_STATUT:
        return CODES_STATUT[libelle]
    base = ''.join(
        c if c.isalnum() else '_' for c in libelle.upper().replace('É', 'E')
    )
    return '_'.join(base.split('_'))[:30]


class _Rapport:
    """Compteurs du bilan d'exécution."""

    def __init__(self):
        self.maquettes_creees = set()      # clés (filière, niveau) réellement créées
        self.maquettes_existantes = set()  # clés déjà présentes avant l'exécution
        self.ue_creees = 0
        self.ue_maj = 0
        self.ue_inchangees = 0
        self.ecue_creees = 0
        self.ecue_maj = 0
        self.ecue_inchangees = 0
        self.ecue_archivees = 0
        self.ecue_desarchivees = 0
        self.familles_creees = 0
        self.familles_existantes = 0
        self.statuts_crees = 0
        self.statuts_existants = 0
        self.creneaux_crees = 0
        self.creneaux_existants = 0
        self.semestres_absents = []
        self.filieres_sans_maquette = []
        self.anomalies = []


class Command(BaseCommand):
    help = (
        'Configure les maquettes UE/ECUE de l’offre de formation INJS depuis '
        'le référentiel officiel (idempotent, non destructif).'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--annee',
            help='Libellé de l’année académique cible (défaut : année courante).',
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Simule l’exécution sans écrire en base (transaction annulée).',
        )
        parser.add_argument(
            '--fichier', default=str(DONNEES),
            help='Jeu de données JSON (défaut : scolarite/data/…).',
        )

    # ── Chargement et contrôles ─────────────────────────────────────────────
    def _charger(self, chemin):
        fichier = Path(chemin)
        if not fichier.is_file():
            raise CommandError(
                f'Jeu de données introuvable : {fichier}\n'
                'Générez-le avec : python scripts/extraire_referentiel_offre_formation.py'
            )
        try:
            return json.loads(fichier.read_text(encoding='utf-8'))
        except json.JSONDecodeError as erreur:
            raise CommandError(f'Jeu de données illisible : {erreur}') from erreur

    def _annee(self, libelle):
        from scolarite.models import AnneeAcademique

        if libelle:
            annee = AnneeAcademique.objects.filter(libelle=libelle).first()
            if annee is None:
                disponibles = ', '.join(
                    AnneeAcademique.objects.values_list('libelle', flat=True)
                ) or 'aucune'
                raise CommandError(
                    f'Année académique « {libelle} » inconnue. Disponibles : {disponibles}.'
                )
            return annee
        annee = (
            AnneeAcademique.objects.filter(courante=True).first()
            or AnneeAcademique.objects.order_by('-date_debut').first()
        )
        if annee is None:
            raise CommandError(
                'Aucune année académique en base : créez-en une avant de configurer '
                'les maquettes (elles sont datées par année).'
            )
        return annee

    # ── Référentiels annexes du classeur ────────────────────────────────────
    def _configurer_familles(self, donnees, rapport, simuler):
        """12 familles de modules (feuille 8, colonne « Famille de modules »)."""
        for ordre, famille in enumerate(
            donnees.get('familles_modules', {}).values(), start=1,
        ):
            existante = FamilleModule.objects.filter(
                code__iexact=famille['code'],
            ).first()
            if existante:
                rapport.familles_existantes += 1
                if existante.libelle != famille['libelle'] and not simuler:
                    existante.libelle = famille['libelle']
                    existante.save(update_fields=['libelle'])
                continue
            rapport.familles_creees += 1
            if not simuler:
                FamilleModule.objects.create(
                    code=famille['code'], libelle=famille['libelle'], ordre=ordre,
                )

    def _configurer_statuts(self, donnees, rapport, simuler):
        """Statuts étudiants de la feuille masquée « Listes ».

        Le classeur fournit les neuf libellés de statut. Il ne dit pas lesquels
        bloquent une inscription : ``bloque_inscription`` reste donc à False et
        n'est jamais déduit — c'est une règle de scolarité à confirmer.
        """
        # Rapprochement par libellé normalisé : la base peut déjà contenir
        # « Diplômé » et « Exclu » là où le classeur écrit « Diplômé(e) » et
        # « Exclu(e) ». On complète, on ne duplique pas, et on ne réécrit
        # jamais un statut existant (son drapeau de blocage appartient à la
        # règle de scolarité, pas au classeur).
        existants = {_normaliser_libelle(s.libelle): s for s in StatutEtudiant.objects.all()}
        for libelle in donnees.get('listes', {}).get('Statut', []):
            cle = _normaliser_libelle(libelle)
            if cle in existants:
                rapport.statuts_existants += 1
                continue
            code = _code_statut(libelle)
            if StatutEtudiant.objects.filter(code=code).exists():
                code = f'{code[:26]}2'
            rapport.statuts_crees += 1
            if not simuler:
                statut = StatutEtudiant.objects.create(code=code, libelle=libelle)
                existants[cle] = statut

    def _configurer_plages(self, donnees, rapport, simuler):
        """Créneaux types du modèle d'emploi du temps (feuille 13)."""
        from edts.models import CreneauTemplate

        # Le modèle stocke des CODES (LUNDI…), pas des libellés.
        jours = ['LUNDI', 'MARDI', 'MERCREDI', 'JEUDI', 'VENDREDI', 'SAMEDI']
        for plage in donnees.get('plages_horaires', []):
            for jour in jours:
                debut = CreneauTemplate.normaliser(plage['debut'])
                fin = CreneauTemplate.normaliser(plage['fin'])
                if CreneauTemplate.objects.filter(
                    jour=jour, heure_debut=debut, heure_fin=fin,
                ).exists():
                    rapport.creneaux_existants += 1
                    continue
                rapport.creneaux_crees += 1
                if not simuler:
                    CreneauTemplate.objects.create(
                        jour=jour, heure_debut=debut, heure_fin=fin,
                    )

    # ── Écriture d'une UE et de ses ECUE ────────────────────────────────────
    def _ecrire_ue(self, maquette, semestre, sigle, num_semestre, ordre, ligne, rapport,
                   simuler):
        code_ue = f'{sigle}-S{num_semestre}-UE{ordre:02d}'
        intitule = (ligne['ue'] or '').strip()
        credits = ligne['credits'] or 0

        famille = None
        if ligne.get('famille'):
            famille = FamilleModule.objects.filter(libelle=ligne['famille']).first()

        ue = UE.objects.filter(maquette=maquette, code__iexact=code_ue).first()
        if ue is None:
            rapport.ue_creees += 1
            if not simuler:
                ue = UE.objects.create(
                    maquette=maquette, semestre=semestre, code=code_ue,
                    intitule=intitule, credits=credits, ordre=ordre,
                    famille=famille,
                )
            else:
                # En simulation, on matérialise l'objet sans l'enregistrer.
                ue = UE(
                    maquette=maquette, semestre=semestre, code=code_ue,
                    intitule=intitule, credits=credits, ordre=ordre,
                )
        else:
            a_changer = []
            if ue.intitule != intitule:
                ue.intitule = intitule
                a_changer.append('intitule')
            if ue.credits != credits:
                ue.credits = credits
                a_changer.append('credits')
            if ue.semestre_id != semestre.pk:
                ue.semestre = semestre
                a_changer.append('semestre')
            if ue.ordre != ordre:
                ue.ordre = ordre
                a_changer.append('ordre')
            if famille is not None and ue.famille_id != famille.pk:
                ue.famille = famille
                a_changer.append('famille')
            if a_changer:
                rapport.ue_maj += 1
                if not simuler:
                    ue.save(update_fields=a_changer)
            else:
                rapport.ue_inchangees += 1

        # ── ECUE : crédits et volumes non publiés par le référentiel ────────
        for rang, libelle in enumerate(ligne['ecues'], start=1):
            code_ecue = f'{code_ue}-EC{rang:02d}'
            existante = ECUE.objects.filter(ue=ue, code__iexact=code_ecue).first() \
                if not simuler else None
            if existante is None:
                if simuler and getattr(ue, 'pk', None):
                    existante = ECUE.objects.filter(ue=ue, code__iexact=code_ecue).first()
                if existante is None:
                    rapport.ecue_creees += 1
                    if not simuler:
                        ECUE.objects.create(
                            ue=ue, code=code_ecue, intitule=libelle, ordre=rang,
                        )
                    continue
            if existante.archive:
                existante.archive = False
                rapport.ecue_desarchivees += 1
                if not simuler:
                    existante.save(update_fields=['archive'])
            if existante.intitule != libelle or existante.ordre != rang:
                existante.intitule = libelle
                existante.ordre = rang
                rapport.ecue_maj += 1
                if not simuler:
                    existante.save(update_fields=['intitule', 'ordre'])
            else:
                rapport.ecue_inchangees += 1

        # ── ECUE surnuméraires : archivées, jamais supprimées ───────────────
        # Le nombre d'ECUE du classeur est autoritaire. Si une ECUE avait été
        # créée en trop (cas des intitulés contenant un « ; »), elle est
        # ARCHIVÉE — donc conservée et réversible — au lieu d'être détruite.
        if getattr(ue, 'pk', None):
            surnumeraires = ECUE.objects.filter(
                ue=ue, archive=False, ordre__gt=len(ligne['ecues']),
            )
            for ecue in surnumeraires:
                rapport.ecue_archivees += 1
                if not simuler:
                    ecue.archive = True
                    ecue.save(update_fields=['archive'])

    # ── Exécution ───────────────────────────────────────────────────────────
    def handle(self, *args, **options):
        donnees = self._charger(options['fichier'])
        annee = self._annee(options.get('annee'))
        simuler = options['dry_run']
        rapport = _Rapport()

        meta = donnees.get('meta', {})
        self.stdout.write(self.style.MIGRATE_HEADING(
            'Référentiel officiel de l’offre de formation INJS'
        ))
        self.stdout.write(f'  Source          : {meta.get("source_fichier", "?")}')
        self.stdout.write(f'  Année cible     : {annee.libelle}')
        self.stdout.write(f'  Mode            : {"SIMULATION (aucune écriture)" if simuler else "ÉCRITURE"}')
        self.stdout.write('')

        filiere_du_sigle = donnees.get('filiere_du_sigle') or {}
        niveaux = {n.code: n for n in Niveau.objects.all()}
        semestres = {(s.numero): s for s in Semestre.objects.select_related('niveau')}

        # Contrôle préalable : la structure LMD doit exister.
        manquants = [c for c in ('L1', 'L2', 'L3', 'M1', 'M2') if c not in niveaux]
        if manquants:
            raise CommandError(
                f'Niveaux LMD absents : {", ".join(manquants)}. '
                'Exécutez d’abord : python manage.py import_referentiel_injs_lmd'
            )
        if not semestres:
            raise CommandError(
                'Aucun semestre en base. Exécutez d’abord : '
                'python manage.py import_referentiel_injs_lmd'
            )

        for anomalie in donnees.get('anomalies', []):
            rapport.anomalies.append(anomalie)

        with transaction.atomic():
            self._configurer_familles(donnees, rapport, simuler)
            self._configurer_statuts(donnees, rapport, simuler)
            self._configurer_plages(donnees, rapport, simuler)

            familles = {f.libelle: f for f in FamilleModule.objects.all()} if not simuler else {}

            for sigle, par_semestre in donnees.get('maquettes', {}).items():
                code_filiere = filiere_du_sigle.get(sigle, '')
                # Une maquette est rattachée à UN cycle : les semestres L1–L3
                # vont au cycle Licence, M1–M2 au cycle Master de la filière.
                formations = {
                    f.type_diplome: f for f in RefFormation.objects.filter(
                        filiere_code=code_filiere,
                        perimetre=RefFormation.Perimetre.INJS,
                    )
                }
                manquants_cycles = {
                    c for c in ('LICENCE', 'MASTER') if c not in formations
                }
                if manquants_cycles:
                    rapport.anomalies.append({
                        'type': 'FORMATION_INTROUVABLE',
                        'detail': (
                            f'Filière {code_filiere} ({sigle}) : cycle(s) '
                            f'{", ".join(sorted(manquants_cycles))} absent(s) — '
                            'maquette non créée. Exécutez '
                            '« qualifier_referentiel_injs_l6 ».'
                        ),
                    })
                    continue

                self.stdout.write(self.style.HTTP_INFO(
                    f'{sigle} — {code_filiere} : {formations["LICENCE"].intitule} / '
                    f'{formations["MASTER"].intitule}'
                ))

                # Une maquette par niveau : les UE de S1 et S2 vont dans L1, etc.
                for numero in sorted(int(n) for n in par_semestre):
                    semestre = semestres.get(numero)
                    if semestre is None:
                        rapport.anomalies.append({
                            'type': 'SEMESTRE_INTROUVABLE',
                            'detail': f'S{numero} absent de la base : semestre ignoré.',
                        })
                        continue
                    niveau = niveaux[NIVEAU_PAR_SEMESTRE[numero]]
                    formation = formations[CYCLE_PAR_NIVEAU[niveau.code]]

                    maquette = Maquette.objects.filter(
                        annee_academique=annee, ref_formation=formation,
                        parcours__isnull=True, niveau=niveau, version=1,
                    ).first()
                    cle = (code_filiere, niveau.code)
                    if maquette is None:
                        rapport.maquettes_creees.add(cle)
                        if not simuler:
                            maquette = Maquette.objects.create(
                                annee_academique=annee, ref_formation=formation,
                                niveau=niveau, version=1,
                                libelle=f'Maquette officielle {sigle} — {niveau.libelle}',
                            )
                        else:
                            maquette = Maquette(
                                annee_academique=annee, ref_formation=formation,
                                niveau=niveau, version=1,
                                libelle=f'Maquette officielle {sigle} — {niveau.libelle}',
                            )
                            # En simulation, aucune UE ne peut être écrite.
                            rapport.ue_creees += len(par_semestre[str(numero)])
                            rapport.ecue_creees += sum(
                                len(l['ecues']) for l in par_semestre[str(numero)]
                            )
                            continue
                    else:
                        rapport.maquettes_existantes.add(cle)
                        if maquette.statut in Maquette.STATUTS_VERROUILLES:
                            # Une maquette validée/active est immuable : on ne la
                            # modifie pas, on signale l'écart pour traitement.
                            rapport.anomalies.append({
                                'type': 'MAQUETTE_VERROUILLEE',
                                'detail': (
                                    f'{sigle} {niveau.code} : maquette '
                                    f'{maquette.statut} (v{maquette.version}) — '
                                    'aucune écriture. Créez une nouvelle version.'
                                ),
                            })
                            continue

                    for ordre, ligne in enumerate(par_semestre[str(numero)], start=1):
                        self._ecrire_ue(
                            maquette, semestre, sigle, numero, ordre, ligne,
                            rapport, simuler,
                        )

                # Semestres absents du référentiel pour cette filière.
                presents = {int(n) for n in par_semestre}
                for numero in range(1, 11):
                    if numero not in presents:
                        rapport.semestres_absents.append(f'{sigle} S{numero}')

            # Filières du référentiel sans maquette publiée.
            for code, filiere in donnees.get('filieres', {}).items():
                if filiere['sigle'] not in donnees.get('maquettes', {}):
                    rapport.filieres_sans_maquette.append(
                        f'{code} {filiere["libelle"]}'
                    )

            if simuler:
                transaction.set_rollback(True)

        self._bilan(rapport, simuler)

    # ── Bilan ───────────────────────────────────────────────────────────────
    def _bilan(self, rapport, simuler):
        self.stdout.write('')
        self.stdout.write(self.style.MIGRATE_HEADING('Bilan'))
        self.stdout.write(
            f'  Maquettes   : {len(rapport.maquettes_creees)} créée(s), '
            f'{len(rapport.maquettes_existantes - rapport.maquettes_creees)} '
            'déjà présente(s)'
        )
        self.stdout.write(
            f'  UE          : {rapport.ue_creees} créée(s), {rapport.ue_maj} mise(s) à jour, '
            f'{rapport.ue_inchangees} inchangée(s)'
        )
        self.stdout.write(
            f'  ECUE        : {rapport.ecue_creees} créée(s), {rapport.ecue_maj} mise(s) à jour, '
            f'{rapport.ecue_inchangees} inchangée(s), {rapport.ecue_archivees} archivée(s)'
        )
        self.stdout.write(
            f'  Familles    : {rapport.familles_creees} créée(s), '
            f'{rapport.familles_existantes} déjà présente(s)'
        )
        self.stdout.write(
            f'  Statuts     : {rapport.statuts_crees} créé(s), '
            f'{rapport.statuts_existants} déjà présent(s)'
        )
        self.stdout.write(
            f'  Créneaux    : {rapport.creneaux_crees} créé(s), '
            f'{rapport.creneaux_existants} déjà présent(s)'
        )
        if rapport.filieres_sans_maquette:
            self.stdout.write(
                '  Filières sans maquette publiée : '
                + ', '.join(rapport.filieres_sans_maquette)
            )
        if rapport.semestres_absents:
            self.stdout.write(self.style.WARNING(
                '  Semestres absents du référentiel (non créés) : '
                + ', '.join(rapport.semestres_absents)
            ))
        for anomalie in rapport.anomalies:
            self.stdout.write(self.style.WARNING(
                f'  [{anomalie.get("type")}] {anomalie.get("detail")}'
            ))
        if simuler:
            self.stdout.write(self.style.WARNING(
                '  SIMULATION : aucune modification n’a été enregistrée.'
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                '  Maquettes écrites en statut BROUILLON — aucune activation automatique.'
            ))
