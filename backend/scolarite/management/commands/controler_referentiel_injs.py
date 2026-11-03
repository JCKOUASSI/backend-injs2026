"""Contrôle de conformité du référentiel INJS entre la source et la base.

La commande confronte, ligne à ligne, le jeu de données extrait du classeur
officiel et l'état réellement présent en base :

* nombre de filières, maquettes, UE, ECUE et crédits ;
* unicité et présence des clés métier ``Filière|Semestre|UE`` ;
* UE sans ECUE, ECUE sans UE, crédits incohérents ;
* rattachement de chaque UE à une famille officielle ;
* complétude de chaque maquette (30 ECTS par semestre) ;
* filières documentées sans maquette (F05–F08) ;
* éléments hors LMD (concours, cycles professionnels, formations à la carte).

Elle ne corrige rien : elle constate. ``--strict`` renvoie un code de sortie
non nul dès qu'une anomalie est détectée, ce qui permet de l'enchaîner en CI.

Usage
-----
    python manage.py controler_referentiel_injs
    python manage.py controler_referentiel_injs --json
    python manage.py controler_referentiel_injs --strict
"""

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count, Sum

from formations.models import RefFormation
from parametres.models import CLES_NOTATION, Parametre
from scolarite.models import ECUE, FamilleModule, Maquette, UE

DONNEES = (
    Path(__file__).resolve().parents[2]
    / 'data' / 'referentiel_offre_formation.json'
)

#: Niveaux attendus et semestres qu'ils portent.
NIVEAUX = {'L1': (1, 2), 'L2': (3, 4), 'L3': (5, 6), 'M1': (7, 8), 'M2': (9, 10)}


class _Controle:
    """Accumule les constats d'un contrôle."""

    def __init__(self):
        self.anomalies = []
        self.constats = []

    def anomalie(self, code, message, gravite='MAJEURE', **extra):
        self.anomalies.append({
            'code': code, 'message': message, 'gravite': gravite, **extra,
        })

    def constat(self, message, code='CONSTAT', **extra):
        self.constats.append({'code': code, 'message': message, **extra})


class Command(BaseCommand):
    help = "Contrôle la conformité du référentiel INJS (source ↔ base), sans correction."

    def add_arguments(self, parser):
        parser.add_argument('--fichier', default=str(DONNEES))
        parser.add_argument('--json', action='store_true', help='Sortie JSON.')
        parser.add_argument(
            '--strict', action='store_true',
            help='Code de sortie 1 si au moins une anomalie est détectée.',
        )

    # ── Chargement ─────────────────────────────────────────────────────────
    def _charger(self, chemin):
        fichier = Path(chemin)
        if not fichier.is_file():
            raise CommandError(f'Jeu de données introuvable : {fichier}')
        return json.loads(fichier.read_text(encoding='utf-8'))

    # ── Contrôles ──────────────────────────────────────────────────────────
    def _controler_maquettes(self, donnees, controle, resume):
        """Confronte chaque maquette de la source à son état en base."""
        filiere_du_sigle = donnees.get('filiere_du_sigle') or {}
        ecarts_semestre = []

        for sigle, par_semestre in donnees.get('maquettes', {}).items():
            code_filiere = filiere_du_sigle.get(sigle)
            if not code_filiere:
                controle.anomalie(
                    'FILIERE_NON_RATTACHEE',
                    f'Le sigle {sigle} n’est rattaché à aucune filière F01–F08.',
                )
                continue

            for niveau, numeros in NIVEAUX.items():
                # On retient la maquette la plus récente du niveau : le
                # contrôle ne doit pas dépendre du drapeau « année courante »,
                # qui n'est qu'une convention d'affichage.
                maquette = (
                    Maquette.objects.filter(
                        ref_formation__filiere_code=code_filiere,
                        niveau__code=niveau,
                    )
                    .order_by('-annee_academique__date_debut', '-version')
                    .first()
                )
                if maquette is None:
                    controle.anomalie(
                        'MAQUETTE_ABSENTE',
                        f'{code_filiere} {niveau} : aucune maquette en base.',
                        filiere=code_filiere, niveau=niveau,
                    )
                    continue

                completude = maquette.controler_completude()
                for ligne in completude['semestres']:
                    attendu = par_semestre.get(str(ligne['numero']))
                    nb_source = len(attendu) if attendu else 0
                    credits_source = (
                        sum(u['credits'] or 0 for u in attendu) if attendu else 0
                    )
                    if ligne['nb_ue'] != nb_source:
                        ecarts_semestre.append({
                            'filiere': code_filiere, 'niveau': niveau,
                            'semestre': ligne['numero'], 'champ': 'nb_ue',
                            'source': nb_source, 'base': ligne['nb_ue'],
                        })
                    if ligne['credits'] != credits_source:
                        ecarts_semestre.append({
                            'filiere': code_filiere, 'niveau': niveau,
                            'semestre': ligne['numero'], 'champ': 'credits',
                            'source': credits_source, 'base': ligne['credits'],
                        })
                    if ligne['nb_ue'] == 0:
                        controle.constat(
                            f'{code_filiere} {niveau} : semestre S{ligne["numero"]} '
                            'vide en base' + (
                                ' — absent de la source officielle.'
                                if nb_source == 0 else ' — présence attendue !'
                            ),
                            filiere=code_filiere, semestre=ligne['numero'],
                        )
                if not completude['complet']:
                    resume['maquettes_incompletes'].append({
                        'filiere': code_filiere, 'niveau': niveau,
                        'credits_documentes': completude['credits_documentes'],
                        'credits_attendus': completude['credits_attendus'],
                        'credits_manquants': completude['credits_manquants'],
                        'semestres_vides': completude['semestres_vides'],
                    })

        for ecart in ecarts_semestre:
            controle.anomalie(
                'ECART_SOURCE_BASE',
                f'{ecart["filiere"]} {ecart["niveau"]} S{ecart["semestre"]} : '
                f'{ecart["champ"]} — source {ecart["source"]}, base {ecart["base"]}.',
                **ecart,
            )

    def _controler_ue(self, donnees, controle, resume):
        """Traçabilité et intégrité des UE et de leurs ECUE."""
        lignes_source = [
            ligne
            for par_semestre in donnees.get('maquettes', {}).values()
            for lignes in par_semestre.values()
            for ligne in lignes
        ]
        resume['ue_source'] = len(lignes_source)
        resume['ecue_source'] = sum(len(l['ecues']) for l in lignes_source)
        resume['credits_source'] = sum(l['credits'] or 0 for l in lignes_source)

        # Clés métier : présence et unicité.
        cles = [ligne.get('cle_source') for ligne in lignes_source]
        sans_cle = sum(1 for cle in cles if not cle)
        if sans_cle:
            controle.anomalie(
                'CLE_SOURCE_MANQUANTE',
                f'{sans_cle} UE sans clé métier « Filière|Semestre|UE ».',
            )
        doublons = {
            cle for cle in cles if cle and cles.count(cle) > 1
        }
        if doublons:
            controle.anomalie(
                'CLE_SOURCE_DUPLIQUEE',
                f'{len(doublons)} clé(s) dupliquée(s) : '
                + ', '.join(sorted(doublons)[:5]),
            )

        # UE sans ECUE dans la source.
        sans_ecue = [l['ue'] for l in lignes_source if not l['ecues']]
        if sans_ecue:
            controle.anomalie(
                'UE_SANS_ECUE_SOURCE',
                f'{len(sans_ecue)} UE sans ECUE dans la source : '
                + ', '.join(sans_ecue[:5]),
            )

        # Crédits non renseignés.
        sans_credits = [l['ue'] for l in lignes_source if l.get('credits') is None]
        if sans_credits:
            controle.anomalie(
                'UE_SANS_CREDITS',
                f'{len(sans_credits)} UE sans crédits : ' + ', '.join(sans_credits[:5]),
            )

        # État en base — PÉRIMÈTRE OFFICIEL UNIQUEMENT.
        # `UE.objects.all()` comptait aussi les maquettes hors référentiel
        # (jeu de démonstration, corpus legacy) : le contrôle annonçait 326 UE
        # pour 323, sans dire d'où venaient les trois de trop. Ces lignes ne
        # sont ni ignorées ni supprimées : elles sont comptées à part, plus bas,
        # et nommées. Un contrôle qui mélange les deux ne contrôle plus rien.
        ue_base = self._ue_du_referentiel(donnees)
        resume['ue_base'] = ue_base.count()
        resume['ue_hors_referentiel'] = UE.objects.exclude(
            pk__in=ue_base.values('pk')).count()
        resume['ecue_base'] = ECUE.objects.filter(
            archive=False, ue__in=ue_base).count()
        resume['ecue_archivees'] = ECUE.objects.filter(
            archive=True, ue__in=ue_base).count()
        resume['ecue_hors_referentiel'] = ECUE.objects.filter(
            archive=False).exclude(ue__in=ue_base).count()
        resume['credits_base'] = ue_base.aggregate(t=Sum('credits'))['t'] or 0

        if resume['ue_base'] != resume['ue_source']:
            controle.anomalie(
                'NB_UE',
                f'{resume["ue_base"]} UE en base pour {resume["ue_source"]} dans la source.',
            )
        if resume['ecue_base'] != resume['ecue_source']:
            controle.anomalie(
                'NB_ECUE',
                f'{resume["ecue_base"]} ECUE actives en base pour '
                f'{resume["ecue_source"]} dans la source.',
            )
        if resume['credits_base'] != resume['credits_source']:
            controle.anomalie(
                'NB_CREDITS',
                f'{resume["credits_base"]} crédits en base pour '
                f'{resume["credits_source"]} dans la source.',
            )

        # UE en base sans ECUE.
        ue_vides = ue_base.annotate(n=Count('ecues', filter=None)).filter(n=0)
        if ue_vides.exists():
            controle.anomalie(
                'UE_SANS_ECUE_BASE',
                f'{ue_vides.count()} UE en base sans ECUE : '
                + ', '.join(ue_vides.values_list('code', flat=True)[:5]),
            )

        # UE sans famille.
        sans_famille = ue_base.filter(famille__isnull=True).count()
        if sans_famille:
            controle.anomalie(
                'UE_SANS_FAMILLE',
                f'{sans_famille} UE sans famille de modules.',
            )
        resume['familles'] = FamilleModule.objects.count()

        # Données présentes en base mais HORS référentiel officiel : nommées,
        # jamais comptées avec le référentiel, jamais supprimées d'office.
        if resume.get('ue_hors_referentiel'):
            hors = (UE.objects.exclude(pk__in=ue_base.values('pk'))
                    .select_related('maquette__ref_formation')
                    .values_list('maquette__ref_formation__intitule', flat=True)
                    .distinct())
            controle.constat(
                f'{resume["ue_hors_referentiel"]} UE et '
                f'{resume.get("ecue_hors_referentiel", 0)} ECUE hors référentiel '
                'officiel (exclues du contrôle) : '
                + ', '.join(sorted(set(hors))[:5]),
                gravite='INFORMATION',
            )

        # UE rattachées à une maquette inexistante (intégrité référentielle).
        sans_maquette = ue_base.filter(maquette__isnull=True).count()
        if sans_maquette:
            controle.anomalie(
                'UE_ORPHELINE', f'{sans_maquette} UE sans maquette.',
            )
        # ECUE rattachées à une UE inexistante.
        ecue_orphelines = ECUE.objects.filter(ue__isnull=True).count()
        if ecue_orphelines:
            controle.anomalie(
                'ECUE_ORPHELINE', f'{ecue_orphelines} ECUE sans UE.',
            )

    @staticmethod
    def _ue_du_referentiel(donnees):
        """UE des maquettes rattachées à une des filières F01–F08 de la source.

        C'est le seul périmètre comparable à la source. Tout le reste (jeu de
        démonstration, corpus importés d'ailleurs) vit dans la même base et ne
        doit pas se mêler au contrôle du référentiel officiel.
        """
        codes = set((donnees.get('filieres') or {}).keys())
        if not codes:
            return UE.objects.all()
        return UE.objects.filter(maquette__ref_formation__filiere_code__in=codes)

    def _controler_filieres(self, donnees, controle, resume):
        """Filières documentées, avec ou sans maquette."""
        maquettes_par_filiere = {}
        for sigle in donnees.get('maquettes', {}):
            code = (donnees.get('filiere_du_sigle') or {}).get(sigle)
            if code:
                maquettes_par_filiere[code] = sigle

        resume['filieres_source'] = len(donnees.get('filieres', {}))
        resume['filieres_injs'] = RefFormation.objects.filter(
            perimetre=RefFormation.Perimetre.INJS,
        ).count()

        for code, filiere in donnees.get('filieres', {}).items():
            existe = RefFormation.objects.filter(
                filiere_code=code, perimetre=RefFormation.Perimetre.INJS,
            ).exists()
            if not existe:
                controle.anomalie(
                    'FILIERE_ABSENTE',
                    f'{code} {filiere["libelle"]} absente du périmètre INJS.',
                )
            if code not in maquettes_par_filiere:
                resume['filieres_sans_maquette'].append({
                    'code': code,
                    'libelle': filiere['libelle'],
                    'ecole': filiere['ecole'],
                    'diplomes': filiere['diplomes'],
                    'ue_documentees': 0,
                })
                controle.constat(
                    f'{code} {filiere["libelle"]} : filière documentée, '
                    'aucune maquette UE/ECUE dans la source.',
                    filiere=code, gravite='INFORMATION',
                )

    def _controler_hors_lmd(self, donnees, controle, resume):
        """Concours, cycles professionnels et formations à la carte."""
        concours = donnees.get('concours', [])
        cycles = donnees.get('cycles_professionnels', [])
        carte = donnees.get('formations_a_la_carte', [])

        resume['hors_lmd'] = {
            'concours': len(concours),
            'cycles_professionnels': len(cycles),
            'formations_a_la_carte': len(carte),
            'total': len(concours) + len(cycles) + len(carte),
        }

        for etiquette, elements, champ in (
            ('concours', concours, 'concours'),
            ('cycles professionnels', cycles, 'cycle'),
            ('formations à la carte', carte, 'formation'),
        ):
            libelles = [e[champ] for e in elements]
            doublons = {l for l in libelles if libelles.count(l) > 1}
            if doublons:
                controle.anomalie(
                    'HORS_LMD_DOUBLON',
                    f'{len(doublons)} doublon(s) dans les {etiquette} : '
                    + ', '.join(sorted(doublons)[:3]),
                    gravite='MINEURE',
                )
            if not elements:
                controle.anomalie(
                    'HORS_LMD_ABSENT',
                    f'Aucun élément extrait pour les {etiquette}.',
                )

        # Aucun de ces éléments ne doit être confondu avec une formation LMD.
        intitules_lmd = set(
            RefFormation.objects.filter(perimetre=RefFormation.Perimetre.INJS)
            .values_list('intitule', flat=True)
        )
        collisions = [
            e['concours'] for e in concours if e['concours'] in intitules_lmd
        ]
        if collisions:
            controle.anomalie(
                'HORS_LMD_CONFONDU',
                f'{len(collisions)} concours enregistré(s) comme formation LMD.',
            )
        controle.constat(
            f'{resume["hors_lmd"]["total"]} éléments hors LMD extraits et '
            'NON importés comme RefFormation (décision métier requise).',
            gravite='INFORMATION',
        )

    def _controler_notation(self, controle, resume):
        """Paramètres de notation : provisoires ou validés."""
        etats = {}
        for cle, libelle in CLES_NOTATION.items():
            parametre = Parametre.objects.filter(cle=cle).first()
            if parametre is None:
                etats[cle] = {'present': False, 'statut': None, 'valeur': None}
                controle.constat(
                    f'Paramètre {cle} absent : aucune valeur de notation '
                    'n’est configurée.',
                    gravite='INFORMATION',
                )
                continue
            etats[cle] = {
                'present': True,
                'statut': parametre.statut_validation,
                'valeur': parametre.valeur,
                'applique': (
                    Parametre.valeur_institutionnelle(cle) is not None
                ),
            }
            if parametre.statut_validation != Parametre.StatutValidation.VALIDE:
                controle.constat(
                    f'{cle} = {parametre.valeur} au statut PROVISOIRE '
                    '(non appliqué par les calculs).',
                    gravite='INFORMATION',
                )
        resume['notation'] = etats

    # ── Exécution ──────────────────────────────────────────────────────────
    def handle(self, *args, **options):
        donnees = self._charger(options['fichier'])
        controle = _Controle()
        resume = {
            'maquettes_incompletes': [],
            'filieres_sans_maquette': [],
        }

        self._controler_filieres(donnees, controle, resume)
        self._controler_maquettes(donnees, controle, resume)
        self._controler_ue(donnees, controle, resume)
        self._controler_hors_lmd(donnees, controle, resume)
        self._controler_notation(controle, resume)

        if options['json']:
            self.stdout.write(json.dumps({
                'resume': resume,
                'anomalies': controle.anomalies,
                'constats': controle.constats,
                'conforme': not controle.anomalies,
            }, ensure_ascii=False, indent=1))
        else:
            self._afficher(donnees, controle, resume)

        if options['strict'] and controle.anomalies:
            raise CommandError(
                f'{len(controle.anomalies)} anomalie(s) détectée(s).'
            )

    def _afficher(self, donnees, controle, resume):
        meta = donnees.get('meta', {})
        self.stdout.write(self.style.MIGRATE_HEADING(
            'CONTRÔLE DU RÉFÉRENTIEL INJS — source ↔ base'
        ))
        self.stdout.write(f'  Source : {meta.get("source_fichier", "?")}')
        self.stdout.write('')

        self.stdout.write(self.style.MIGRATE_HEADING('Contenus'))
        self.stdout.write(
            f'  Filières   : {resume.get("filieres_source", 0)} dans la source, '
            f'{resume.get("filieres_injs", 0)} cycles INJS en base'
        )
        self.stdout.write(
            f'  UE         : {resume.get("ue_source", 0)} source / '
            f'{resume.get("ue_base", 0)} base'
        )
        self.stdout.write(
            f'  ECUE       : {resume.get("ecue_source", 0)} source / '
            f'{resume.get("ecue_base", 0)} base '
            f'({resume.get("ecue_archivees", 0)} archivées)'
        )
        self.stdout.write(
            f'  Crédits    : {resume.get("credits_source", 0)} source / '
            f'{resume.get("credits_base", 0)} base'
        )
        self.stdout.write(f'  Familles   : {resume.get("familles", 0)}')
        # Les données hors référentiel sont nommées ici : sans cette ligne,
        # un lecteur ne pourrait pas savoir ce que « base » inclut ou exclut.
        hors_ref_ue = resume.get('ue_hors_referentiel', 0)
        hors_ref_ecue = resume.get('ecue_hors_referentiel', 0)
        if hors_ref_ue or hors_ref_ecue:
            self.stdout.write(
                f'  Hors réf.  : {hors_ref_ue} UE / {hors_ref_ecue} ECUE '
                'en base, exclues du contrôle (démonstration ou corpus étranger)'
            )
        hors = resume.get('hors_lmd') or {}
        self.stdout.write(
            f'  Hors LMD   : {hors.get("concours", 0)} concours, '
            f'{hors.get("cycles_professionnels", 0)} cycles pro, '
            f'{hors.get("formations_a_la_carte", 0)} formations à la carte '
            f'= {hors.get("total", 0)} éléments'
        )
        self.stdout.write('')

        self.stdout.write(self.style.MIGRATE_HEADING('Maquettes incomplètes'))
        if not resume['maquettes_incompletes']:
            self.stdout.write(self.style.SUCCESS('  Aucune — toutes à 60 ECTS par niveau.'))
        for maquette in resume['maquettes_incompletes']:
            self.stdout.write(self.style.WARNING(
                f'  {maquette["filiere"]} {maquette["niveau"]} : '
                f'{maquette["credits_documentes"]}/{maquette["credits_attendus"]} ECTS '
                f'— manque {maquette["credits_manquants"]} '
                f'(semestre(s) vide(s) : {maquette["semestres_vides"]})'
            ))
        self.stdout.write('')

        self.stdout.write(self.style.MIGRATE_HEADING('Filières sans maquette'))
        if not resume['filieres_sans_maquette']:
            self.stdout.write('  Aucune.')
        for filiere in resume['filieres_sans_maquette']:
            self.stdout.write(
                f'  {filiere["code"]} {filiere["libelle"]} ({filiere["ecole"]}) — '
                f'{filiere["ue_documentees"]} UE documentée(s)'
            )
        self.stdout.write('')

        self.stdout.write(self.style.MIGRATE_HEADING('Paramètres de notation'))
        for cle, etat in (resume.get('notation') or {}).items():
            if not etat['present']:
                self.stdout.write(f'  {cle} : absent')
            else:
                applique = 'APPLIQUÉ' if etat['applique'] else 'non appliqué'
                self.stdout.write(
                    f'  {cle} = {etat["valeur"]} [{etat["statut"]}] — {applique}'
                )
        self.stdout.write('')

        self.stdout.write(self.style.MIGRATE_HEADING('Anomalies'))
        if not controle.anomalies:
            self.stdout.write(self.style.SUCCESS('  Aucune anomalie détectée.'))
        for anomalie in controle.anomalies:
            couleur = (
                self.style.ERROR if anomalie['gravite'] == 'MAJEURE'
                else self.style.WARNING
            )
            self.stdout.write(couleur(
                f'  [{anomalie["code"]}] {anomalie["message"]}'
            ))
        self.stdout.write('')
        self.stdout.write(self.style.MIGRATE_HEADING('Constat'))
        self.stdout.write(
            f'  {len(controle.anomalies)} anomalie(s), '
            f'{len(controle.constats)} constat(s).'
        )
        # Les constats portent des informations qu'un « 0 anomalie » masquerait
        # (semestre absent de la source, filière sans maquette, hors référentiel).
        for constat in controle.constats:
            self.stdout.write(f'  · [{constat["code"]}] {constat["message"]}')
