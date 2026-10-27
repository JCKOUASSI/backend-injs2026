"""
Commande Django pour importer les données depuis les fichiers Excel ou CSV.

Usage :
  python manage.py import_excel import_formations.xlsx
  python manage.py import_excel import_participants.xlsx
  python manage.py import_excel import_participants.csv
  python manage.py import_excel import_formations.xlsx --dry-run
"""
import csv
import io
import re
import unicodedata
from datetime import datetime, date
from difflib import SequenceMatcher

from django.core.management.base import BaseCommand, CommandError
from django.db import models, transaction
from django.utils import timezone

from openpyxl import load_workbook

from formations.categorie_referentiel import resolve_categorie_participant
from formations.models import (
    Formation, Participant, Formateur, Module,
    ModuleParticipant, ModuleFormateur, SessionModule, RefSite,
)
FormationParticipant = ModuleParticipant
FormationFormateur = ModuleFormateur


class Command(BaseCommand):
    help = 'Importer les données depuis un fichier Excel ou CSV (formations ou participants)'

    def add_arguments(self, parser):
        parser.add_argument('file', type=str, help='Chemin vers le fichier Excel (.xlsx) ou CSV (.csv)')
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Simuler l\'import sans écrire en base',
        )
        parser.add_argument(
            '--disable-auto-inscription', action='store_true',
            help='Désactiver l\'auto-inscription : force l\'utilisation explicite de la colonne Formation(s)',
        )

    def handle(self, *args, **options):
        filepath = options['file']
        dry_run = options['dry_run']
        self.disable_auto_inscription = options.get('disable_auto_inscription', False)

        is_csv = filepath.lower().endswith('.csv')
        stats = {}
        errors = []

        try:
            with transaction.atomic():
                if is_csv:
                    ws = self._load_csv(filepath)
                    # Detect type from filename
                    fname = filepath.lower()
                    if 'participant' in fname:
                        stats['participants'] = self._import_participants(ws, errors)
                    elif 'formation' in fname:
                        stats['formations'] = self._import_formations(ws, errors)  # tuple (created, updated)
                    elif 'formateur' in fname:
                        stats['formateurs'] = self._import_formateurs(ws, errors)
                    else:
                        stats['participants'] = self._import_participants(ws, errors)
                else:
                    try:
                        wb = load_workbook(filepath, read_only=True)
                    except Exception as e:
                        raise CommandError(f"Impossible d'ouvrir le fichier : {e}")

                    # Mapping des feuilles par nom standard
                    sheet_mapping = {
                        'formations': None,
                        'participants': None,
                        'seances': None,
                        'formateurs': None,
                        'inscriptions': None,
                        'formateurs_formations': None,
                        'emploi_du_temps': None,
                    }

                    # 1. Recherche par noms standards
                    if 'Formations' in wb.sheetnames:
                        sheet_mapping['formations'] = wb['Formations']
                    if 'Formateurs' in wb.sheetnames:
                        sheet_mapping['formateurs'] = wb['Formateurs']
                    if 'Participants' in wb.sheetnames:
                        sheet_mapping['participants'] = wb['Participants']
                    elif 'Auditeurs' in wb.sheetnames:
                        sheet_mapping['participants'] = wb['Auditeurs']
                    if 'Inscriptions' in wb.sheetnames:
                        sheet_mapping['inscriptions'] = wb['Inscriptions']
                    if 'Formateurs_Formations' in wb.sheetnames:
                        sheet_mapping['formateurs_formations'] = wb['Formateurs_Formations']
                    if 'Emploi du temps' in wb.sheetnames:
                        sheet_mapping['emploi_du_temps'] = wb['Emploi du temps']
                    for sheet_name in ('Séances', 'Seances'):
                        if sheet_name in wb.sheetnames:
                            sheet_mapping['seances'] = wb[sheet_name]
                            break

                    # 2. Détection automatique par contenu pour les feuilles non reconnues
                    for sheet_name in wb.sheetnames:
                        # Ignorer les feuilles déjà assignées
                        already_assigned = any(
                            sheet_mapping.get(k) == wb[sheet_name]
                            for k in sheet_mapping
                        )
                        if already_assigned:
                            continue

                        ws = wb[sheet_name]
                        detected_type = self._detect_sheet_type(ws)
                        if detected_type and not sheet_mapping.get(detected_type):
                            self.stdout.write(f"  ℹ️  Feuille '{sheet_name}' détectée comme : {detected_type}")
                            sheet_mapping[detected_type] = ws

                    # 3. Exécution des imports
                    if sheet_mapping['formations']:
                        stats['formations'] = self._import_formations(sheet_mapping['formations'], errors)
                    if sheet_mapping['formateurs']:
                        stats['formateurs'] = self._import_formateurs(sheet_mapping['formateurs'], errors)
                    if sheet_mapping['participants']:
                        stats['participants'] = self._import_participants(sheet_mapping['participants'], errors)
                    if sheet_mapping['inscriptions']:
                        stats['inscriptions'] = self._import_inscriptions(sheet_mapping['inscriptions'], errors)
                    if sheet_mapping['formateurs_formations']:
                        stats['formateurs_formations'] = self._import_formateurs_formations(
                            sheet_mapping['formateurs_formations'], errors
                        )

                    # Gestion des séances vs emploi du temps
                    if sheet_mapping['seances']:
                        ws_s = sheet_mapping['seances']
                        first_row = next(ws_s.iter_rows(values_only=True), ())
                        headers_lower = [str(h).lower().strip() if h else '' for h in first_row]
                        has_module = any('module' in h or 'grade' in h for h in headers_lower)
                        if has_module:
                            created, updated = self._import_seances(ws_s, errors)
                        else:
                            created = self._import_emploi_du_temps(ws_s, errors)
                            updated = 0
                        stats['seances'] = created
                        if updated:
                            stats['seances_mises_a_jour'] = updated
                    elif sheet_mapping['emploi_du_temps']:
                        stats['seances'] = self._import_emploi_du_temps(sheet_mapping['emploi_du_temps'], errors)

                    # Avertissement si aucune feuille détectée
                    if not any(sheet_mapping.values()):
                        errors.append("Aucune feuille reconnue dans le fichier Excel")

                    wb.close()

                if dry_run:
                    raise _DryRunRollback()

        except _DryRunRollback:
            self.stdout.write(self.style.WARNING('\n🔸 DRY RUN — aucune donnée écrite en base.\n'))

        # Résumé
        self.stdout.write('\n' + '=' * 50)
        self.stdout.write(self.style.SUCCESS('📊 Résumé de l\'import :'))
        for label, count in stats.items():
            # _import_seances retourne un tuple (created, updated) dans certains cas
            if isinstance(count, tuple):
                created, updated = count
                icon = '✅' if created > 0 else '⏭️'
                self.stdout.write(f'  {icon} {label.capitalize():.<30} {created} créées, {updated} mises à jour')
            else:
                icon = '✅' if count > 0 else '⏭️'
                self.stdout.write(f'  {icon} {label.capitalize():.<30} {count}')

        if errors:
            self.stdout.write(self.style.ERROR(f'\n⚠️  {len(errors)} erreur(s) :'))
            for err in errors:
                self.stdout.write(self.style.ERROR(f'  ❌ {err}'))
        else:
            self.stdout.write(self.style.SUCCESS('\n✅ Import terminé sans erreur.'))

    # ─── Helpers ─────────────────────────────────────

    def _load_csv(self, filepath):
        """Charge un fichier CSV et retourne un objet itérable compatible avec _rows()."""
        class _CsvSheet:
            def __init__(self, filepath):
                self._rows_data = []
                with open(filepath, newline='', encoding='utf-8-sig') as f:
                    reader = csv.reader(f)
                    for row in reader:
                        # Convertir les chaînes vides en None pour cohérence avec Excel
                        self._rows_data.append(
                            tuple(v.strip() if v.strip() else None for v in row)
                        )

            def iter_rows(self, values_only=True):
                return iter(self._rows_data)

        return _CsvSheet(filepath)

    def _load_csv_from_bytes(self, content_bytes):
        """Charge un CSV depuis des bytes (pour l'API)."""
        class _CsvSheet:
            def __init__(self, content_bytes):
                self._rows_data = []
                text = content_bytes.decode('utf-8-sig')
                reader = csv.reader(io.StringIO(text))
                for row in reader:
                    self._rows_data.append(
                        tuple(v.strip() if v.strip() else None for v in row)
                    )

            def iter_rows(self, values_only=True):
                return iter(self._rows_data)

        return _CsvSheet(content_bytes)

    def _rows(self, ws, sheet_type='participant'):
        """Itère sur les lignes de données (ignore l'en-tête, s'arrête à la première ligne vide)."""
        headers = None
        for row_idx, row in enumerate(ws.iter_rows(values_only=True), 1):
            if row_idx == 1:
                # Normaliser les en-têtes
                headers = []
                for h in row:
                    if h:
                        clean = str(h).strip().lower()
                        # Mapper les noms de colonnes du template vers les noms internes
                        # Capturer les noms composés AVANT toute autre règle
                        if clean in ('module_titre', 'module titre', 'formation_titre', 'formation titre'):
                            headers.append('module_titre')
                            continue
                        if clean in ('formation(s)', 'formations'):
                            headers.append('formation(s)')
                            continue
                        if clean in (
                            'formation (cycle)', 'formation(cycle)', 'cycle de formation', 'cycle',
                            'formation',
                        ):
                            headers.append('formation')
                            continue
                        if clean in ('intitule', 'intitulé', 'libelle', 'libellé') and sheet_type != 'formation':
                            headers.append('intitule')
                            continue
                        elif 'module' in clean and '(titre)' in clean:
                            clean = 'module'
                        else:
                            clean = clean.replace('(numero)', '').replace('(titre)', '')
                            clean = clean.replace('(h)', '').strip()
                        # Spécifiques en premier (avant les règles génériques)
                        clean = clean.replace('n° d\'inscription', 'matricule').replace('n° d inscription', 'matricule')
                        clean = clean.replace('n°d\'inscription', 'matricule')
                        clean = clean.replace('téléphone 1', 'telephone').replace('telephone 1', 'telephone')
                        clean = clean.replace('téléphone 2', 'telephone2').replace('telephone 2', 'telephone2')
                        clean = clean.replace('libelle concours', 'libelle_concours').replace('libellé concours', 'libelle_concours')
                        clean = clean.replace('type concours', 'type_concours')
                        clean = clean.replace('grade/groupe', 'grade_groupe').replace('grade groupe', 'grade_groupe').replace('grade-groupe', 'grade_groupe')
                        clean = clean.replace('date de naissance', 'date_naissance').replace('date naissance', 'date_naissance')
                        clean = clean.replace('lieu de naissance', 'lieu_naissance').replace('lieu naissance', 'lieu_naissance')

                        clean = clean.replace('volume horaire', 'duree_prevue_heures')
                        if '_' not in clean:
                            clean = clean.replace('duree', 'duree_prevue_heures').replace('durée', 'duree_prevue_heures')
                        if clean == 'module' or (('module' in clean) and ('titre' in clean or 'intitule' in clean or 'intitulé' in clean)):
                            clean = 'module'
                        clean = clean.replace('intitulé du module', 'formation').replace('intitule du module', 'formation')
                        clean = clean.replace('libellé du module', 'formation').replace('libelle du module', 'formation')
                        clean = clean.replace('intitulé de la formation', 'formation').replace('intitule de la formation', 'formation')
                        clean = clean.replace('intitulé', 'formation').replace('intitule', 'formation')
                        clean = clean.replace('libellé de la formation', 'formation').replace('libelle de la formation', 'formation')
                        if '_' not in clean:
                            clean = clean.replace('libellé', 'formation').replace('libelle', 'formation')
                        clean = clean.replace('désignation', 'formation').replace('designation', 'formation')
                        clean = clean.replace('matière', 'formation').replace('matiere', 'formation')
                        if clean == 'cours':
                            clean = 'formation'
                        clean = clean.replace('lieu de formation', 'site')
                        clean = clean.replace('centre de formation', 'site')
                        if '_' not in clean:
                            clean = clean.replace('lieu', 'site')
                        clean = clean.replace('date début', 'date_debut').replace('date fin', 'date_fin')
                        clean = clean.replace('heure début', 'heure_debut').replace('heure debut', 'heure_debut')
                        clean = clean.replace('heure fin', 'heure_fin')
                        clean = clean.replace('date journée', 'date_journee').replace('date journee', 'date_journee')
                        # Règles génériques
                        clean = clean.replace('prénoms', 'prenom').replace('prénom', 'prenom')
                        clean = clean.replace('prenom(s)', 'prenom').replace('prenoms', 'prenom')
                        clean = clean.replace('catégorie/corps', 'categorie').replace('categorie/corps', 'categorie')
                        clean = clean.replace('genre', 'sexe')
                        clean = clean.replace('téléphone', 'telephone')
                        clean = clean.replace('catégorie', 'categorie')
                        clean = clean.replace('bâtiment', 'batiment').replace('batîment', 'batiment')
                        clean = clean.replace('spécialité', 'specialite')
                        clean = clean.replace('numéro', 'numero')
                        clean = clean.replace('fncp', 'matricule')
                        if clean in ('matricule',):
                            headers.append(clean)
                            continue
                        if sheet_type == 'formation':
                            clean = clean.replace('n°', 'numero_formation')
                        else:
                            clean = clean.replace('n°', 'numero')
                            if clean == 'module':
                                clean = 'formation'
                        headers.append(clean)
                    else:
                        headers.append('')
                if headers:
                    self.stdout.write(f'  [DEBUG] Headers normalisés : {headers}')
                continue
            # Ligne vide → fin des données
            if all(v is None or str(v).strip() == '' for v in row):
                break
            yield row_idx, dict(zip(headers, row))

    def _str(self, val, default=''):
        if val is None:
            return default
        return str(val).strip()

    def _normalize_field(self, val, default='', uppercase=True):
        """Normalise un champ texte : strip, espaces multiples -> un seul, optionnellement majuscules.

        Utilisé pour grade, groupe, vague afin d'éviter les doublons dus aux espaces
        ou différences de casse (ex: 'Groupe 1' vs 'GROUPE 1' vs 'Groupe  1').
        """
        if val is None:
            return default
        result = str(val).strip()
        # Réduire les espaces multiples à un seul
        result = ' '.join(result.split())
        if uppercase:
            result = result.upper()
        return result

    def _normalize_grade(self, val, default=''):
        """Normalise un grade : extrait la lettre (B, C, D) si format B1, B2, C3...

        Règle métier : B1, B2, B3 -> B | C1, C2 -> C | D1, D2 -> D
        La différenciation se fait par groupe + vague, pas par sous-grade.
        """
        result = self._normalize_field(val, default)
        if not result:
            return default
        # Si format Lettre+Chiffre (B1, B2, C3...), retourner juste la lettre
        import re
        match = re.match(r'^([BCD])\d+$', result)
        if match:
            return match.group(1)
        return result

    def _normalize_module_title(self, val, default=''):
        return self._normalize_field(val, default=default)

    def _module_title_match_ratio(self, left, right):
        a = self._normalize_module_title(left)
        b = self._normalize_module_title(right)
        if not a or not b:
            return 0.0
        if a == b:
            return 1.0
        return SequenceMatcher(None, a, b).ratio()

    def _resolve_modules_for_seance(self, titre, grade, groupe, vague):
        """Retrouve le(s) module(s) cible(s) pour une ligne de séance.

        Stratégie :
        1. correspondance exacte (titre + grade + groupe + vague)
        2. titre + groupe + vague si un seul module correspond (grade Excel parfois erroné)
        3. rapprochement flou du titre (coquilles : MUTTE/LUTTE, etc.) sur le même groupe/vague
        """
        titre_n = self._normalize_module_title(titre)
        if not titre_n:
            return [], None

        base_qs = Module.objects.filter(
            groupe__iexact=groupe,
            vague__iexact=vague,
        ).select_related('formation')

        def _title_matches(module):
            return self._module_title_match_ratio(titre_n, module.intitule) >= 0.92

        if grade:
            exact = [m for m in base_qs.filter(grade__iexact=grade) if _title_matches(m)]
            if exact:
                return exact, None

        by_combo = [m for m in base_qs if _title_matches(m)]
        if len(by_combo) == 1:
            module = by_combo[0]
            if grade and module.grade and module.grade.upper() != grade.upper():
                return [module], (
                    f'grade Excel {grade!r} ignoré, module trouvé avec grade {module.grade!r}'
                )
            return [module], None

        fuzzy = []
        best_ratio = 0.92
        for module in base_qs:
            ratio = self._module_title_match_ratio(titre_n, module.intitule)
            if ratio >= best_ratio:
                if ratio > best_ratio:
                    fuzzy = [module]
                    best_ratio = ratio
                elif ratio == best_ratio:
                    fuzzy.append(module)
        if len(fuzzy) == 1:
            return fuzzy, f'titre rapproché de {fuzzy[0].intitule!r}'
        return [], None

    def _detect_sheet_type(self, ws):
        """Détecte le type de feuille par analyse de ses headers.

        Retourne : 'formations', 'participants', 'seances', 'formateurs', 'inscriptions', 'emploi_du_temps' ou None
        """
        first_row = next(ws.iter_rows(values_only=True), ())
        if not first_row:
            return None

        headers = [str(h).lower().strip() if h else '' for h in first_row]
        headers_set = set(headers)

        # Détection Formations : doit avoir Module + Grade + Groupe
        has_module = any('module' in h for h in headers)
        has_grade = 'grade' in headers_set
        has_groupe = 'groupe' in headers_set
        if has_module and has_grade and has_groupe:
            # Vérifier qu'il a des champs de formation (date début/fin ou volume horaire)
            # Gère les accents et les différentes variantes
            has_date_fields = any(
                'date' in h and ('debut' in h or 'début' in h or 'fin' in h)
                for h in headers
            )
            has_volume = any('volume' in h or 'horaire' in h for h in headers)
            if has_date_fields or has_volume:
                return 'formations'

        # Détection Participants : doit avoir NOM + GRADE + GROUPE
        participant_markers = {'nom', 'prenom', 'prenoms', 'grade', 'groupe', 'matricule', "n° d'inscription"}
        has_nom = any(h in headers_set for h in ['nom', 'nom'])
        has_grade = 'grade' in headers_set
        has_groupe = 'groupe' in headers_set
        if has_nom and has_grade and has_groupe:
            return 'participants'

        # Détection Séances : doit avoir module_titre/module + grade + groupe + vague + date
        # ET des champs spécifiques aux séances (numero, date_journee, heure_debut...)
        has_module = any('module' in h or 'module_titre' in h for h in headers)
        has_grade_groupe = 'grade' in headers_set and 'groupe' in headers_set
        has_seance_fields = any(h in headers_set for h in ['numero', 'date_journee', 'heure_debut', 'heure_fin'])
        if has_module and has_grade_groupe and has_seance_fields:
            return 'seances'

        # Détection Emploi du temps : a date/heure mais pas de module/groupe spécifique
        if 'date' in headers_set or 'heure' in headers_set:
            if not any('module' in h or 'groupe' in h for h in headers):
                return 'emploi_du_temps'

        # Détection Formateurs
        if 'formateur' in headers_set or 'nom formateur' in headers_set:
            return 'formateurs'

        return None

    def _resolve_categorie_participant(self, raw_categorie='', grade=''):
        """Mappe la catégorie saisie vers le libellé RefCategorie."""
        return resolve_categorie_participant(raw_categorie, grade=grade)

    def _normalize_categorie(self, cat):
        """Normalise la catégorie vers le libellé RefTypeSecretariat.
        - Compacte les variantes collées (ex. 'FABA' -> 'FAB A', 'FACB' -> 'FAC B').
        - Préserve les autres codes pour permettre une résolution dynamique
          (ex. 'FAC A', 'FAR B'… seront cherchés tels quels dans RefTypeSecretariat).
        - Une lettre seule ('A'/'B'/'C') est laissée telle quelle ; la résolution
          du secrétariat tentera alors un match par suffixe (voir _import_formations).
        """
        c = cat.strip().upper()
        if not c:
            return c
        # Variantes collées CPFAE uniquement : "FABA" -> "FAB A".
        # Ne pas découper les codes INJS (SFC, SST, SFO, SAC, SSC…).
        import re as _re
        m = _re.fullmatch(r'(FAB|FAC|FAR)\s*([A-D])', c)
        if m:
            return f'{m.group(1)} {m.group(2)}'
        return c

    def _fold_ascii(self, value):
        text = unicodedata.normalize('NFKD', value or '')
        text = ''.join(ch for ch in text if not unicodedata.combining(ch))
        return text.casefold()

    def _secretariat_type_from_participant(self, raw_categorie='', grade=''):
        """Clé RefTypeSecretariat pour un étudiant INJS / CPFAE.

        Les libellés pédagogiques (Élève Professeur, Étudiant LMD…) ne sont pas
        des types de secrétariat : on les rattache à SET ou SFC.
        """
        cat = self._normalize_categorie(raw_categorie) if raw_categorie else ''
        blob = self._fold_ascii(f'{cat} {grade or ""}')
        if cat == 'SFC' or 'formation continue' in blob or 'formation a la carte' in blob:
            return 'SFC'
        if cat in (
            'SET', 'SSC', 'SFO', 'SST', 'SAC', 'SAD', 'SAO', 'SCA', 'SCO',
            'SCR', 'SDA', 'SDD', 'SEN', 'SEX', 'SFI', 'SGE', 'SJU', 'SND',
            'SPR', 'SRH',
        ):
            return cat
        if cat.startswith('FAB') or cat.startswith('FAC') or cat.startswith('FAR'):
            return cat
        if len(cat) == 1 and cat in 'ABCD':
            return cat
        if any(tok in blob for tok in ('eleve', 'etudiant')):
            return 'SET'
        return cat

    def _secretariat_hint_from_matricule(self, matricule):
        """Retourne le code secrétariat prioritaire selon le matricule.
        FNCE* -> FAB, FNCP* -> FAC.
        """
        m = (matricule or '').strip().upper()
        if m.startswith('FNCE'):
            return 'FAB'
        if m.startswith('FNCP'):
            return 'FAC'
        return ''

    def _resolve_secretariat(self, SecretariatModel, hint, grade='', matricule='', categorie=''):
        """Résout un secrétariat depuis un hint (nom ou type libellé).

        Gère le cas où le hint est une famille (ex. « FAB ») correspondant à
        plusieurs secrétariats par grade (FAB A, FAB B…) : on désambiguïse
        d'abord avec la lettre du grade (ou, si le grade est absent, avec la
        catégorie), puis avec le préfixe du matricule.
        """
        if not hint:
            return None
        h = hint.strip()
        # 1) Correspondance exacte (nom ou type)
        sec = (
            SecretariatModel.objects.filter(nom__iexact=h).first()
            or SecretariatModel.objects.filter(type__libelle__iexact=h).first()
            or SecretariatModel.objects.filter(nom__istartswith=f'{h} ').first()
        )
        if sec:
            return sec
        # 2) Correspondance par préfixe (ex. « FAB » -> « FAB A », « FAB B »…)
        candidates = list(
            SecretariatModel.objects.filter(type__libelle__istartswith=h)[:8]
        )
        if not candidates:
            candidates = list(
                SecretariatModel.objects.filter(nom__istartswith=h)[:8]
            )
        if not candidates:
            return None
        if len(candidates) == 1:
            return candidates[0]
        # 3) Désambiguïsation par la lettre du grade (A/B/C/D), ou à défaut
        #    par la catégorie (ex. « A », « FAB A » -> A).
        g = (grade or '').strip().upper()
        grade_letter = g[0] if g and g[0] in ('A', 'B', 'C', 'D') else ''
        if not grade_letter and categorie:
            c = self._normalize_categorie(categorie)
            if c and c[-1] in ('A', 'B', 'C', 'D'):
                grade_letter = c[-1]
        if grade_letter:
            for cand in candidates:
                label = (cand.type.libelle if cand.type else '').upper()
                if label.endswith(f' {grade_letter}') or cand.nom.upper().endswith(f' {grade_letter}'):
                    return cand
        # 4) Désambiguïsation FAB/FAC par le préfixe du matricule
        m = (matricule or '').strip().upper()
        prefers_fab = not m.startswith('FNCP')
        for cand in candidates:
            label = (cand.type.libelle if cand.type else '').upper()
            if prefers_fab and label.startswith('FAB'):
                return cand
            if not prefers_fab and label.startswith('FAC'):
                return cand
        return candidates[0]

    def _resolve_ref_site(self, site_name):
        """
        Résout un libellé Excel (ex. « CPFAE-AGC ») en instance RefSite.
        Crée le site référentiel s'il n'existe pas encore.
        """
        name = self._str(site_name)
        if not name:
            return None
        site = RefSite.objects.filter(nom__iexact=name).first()
        if site:
            return site
        return RefSite.objects.create(nom=name, actif=True)
    def _int(self, val, default=None):
        if val is None:
            return default
        try:
            return int(float(val))
        except (ValueError, TypeError):
            return default

    def _has_value(self, val):
        if val is None:
            return False
        return str(val).strip().lower() not in ('', '-', '—', 'n/a', 'na', 'none')

    def _normalize_date_string(self, val_str):
        """Corrige les dates Excel mal saisies (espaces, slash manquant)."""
        val_str = str(val_str).strip()
        if not val_str:
            return val_str

        # ISO : conserver l'espace (ou T) entre date et heure
        m_iso = re.match(r'^(\d{4}-\d{2}-\d{2})(?:\s+|T)(.+)$', val_str)
        if m_iso:
            return f'{m_iso.group(1)} {m_iso.group(2).strip()}'

        # Européen avec heure : DD/MM/YYYY HH:MM
        m_eu_time = re.match(
            r'^(.+?)\s+(\d{1,2}:\d{2}(?::\d{2})?)$',
            val_str,
        )
        if m_eu_time:
            date_part = re.sub(r'\s+', '', m_eu_time.group(1).strip())
            return f'{date_part} {m_eu_time.group(2)}'

        val_str = re.sub(r'\s+', '', val_str)
        # 03/072026 → 03/07/2026
        m = re.match(r'^(\d{1,2})/(\d{2})(\d{4})$', val_str)
        if m:
            return f'{int(m.group(1)):02d}/{int(m.group(2)):02d}/{m.group(3)}'
        return val_str

    def _parse_datetime(self, val):
        if val is None:
            return None
        if isinstance(val, datetime):
            if timezone.is_naive(val):
                return timezone.make_aware(val)
            return val
        if isinstance(val, date):
            return timezone.make_aware(datetime.combine(val, datetime.min.time()))
        if isinstance(val, (int, float)):
            try:
                from openpyxl.utils.datetime import from_excel
                dt = from_excel(float(val))
                if isinstance(dt, datetime):
                    return timezone.make_aware(dt) if timezone.is_naive(dt) else dt
                if isinstance(dt, date):
                    return timezone.make_aware(datetime.combine(dt, datetime.min.time()))
            except (ValueError, OverflowError, TypeError):
                pass

        val_str = self._normalize_date_string(val)
        if not self._has_value(val_str):
            return None

        formats = (
            '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M',
            '%d/%m/%Y %H:%M:%S', '%d/%m/%Y %H:%M',
            '%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M',
            '%Y-%m-%d', '%d/%m/%Y', '%d/%m/%y',
            '%d-%m-%Y', '%d-%m-%y', '%d.%m.%Y', '%d.%m.%y',
        )
        for fmt in formats:
            try:
                dt = datetime.strptime(val_str, fmt)
                return timezone.make_aware(dt)
            except ValueError:
                continue

        m = re.match(
            r'^(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})(?:\s+(\d{1,2}):(\d{2})(?::(\d{2}))?)?$',
            val_str,
        )
        if m:
            day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if year < 100:
                year += 2000
            hour = int(m.group(4) or 0)
            minute = int(m.group(5) or 0)
            second = int(m.group(6) or 0)
            try:
                dt = datetime(year, month, day, hour, minute, second)
                return timezone.make_aware(dt)
            except ValueError:
                pass

        parsed_date = self._parse_date(val_str.split()[0] if ' ' in val_str else val_str)
        if parsed_date:
            if ' ' in val_str:
                time_part = val_str.split(maxsplit=1)[1]
                for tfmt in ('%H:%M:%S', '%H:%M'):
                    try:
                        t = datetime.strptime(time_part, tfmt).time()
                        return timezone.make_aware(datetime.combine(parsed_date, t))
                    except ValueError:
                        continue
            return timezone.make_aware(datetime.combine(parsed_date, datetime.min.time()))
        return None

    def _parse_date(self, val):
        if val is None:
            return None
        if isinstance(val, (datetime, date)):
            return val if isinstance(val, date) else val.date()
        if isinstance(val, (int, float)):
            parsed = self._parse_datetime(val)
            return parsed.date() if parsed else None
        val = self._normalize_date_string(val)
        if not self._has_value(val):
            return None
        for fmt in ('%d/%m/%Y', '%d/%m/%y', '%Y-%m-%d', '%d-%m-%Y', '%d-%m-%y', '%d.%m.%Y', '%d.%m.%y'):
            try:
                return datetime.strptime(val, fmt).date()
            except ValueError:
                continue
        m = re.match(r'^(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})$', val)
        if m:
            day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if year < 100:
                year += 2000
            try:
                return date(year, month, day)
            except ValueError:
                pass
        return None

    def _parse_optional_datetime(self, val):
        if not self._has_value(val):
            return None, False
        parsed = self._parse_datetime(val)
        return parsed, parsed is None

    # ─── Import Formations ───────────────────────────

    def _import_formations(self, ws, errors, secretariat=None):
        from formations.models import Secretariat as SecretariatModel
        count = 0
        modules_updated = 0
        _secretariat_cache = {}
        _module_order = {}  # (formation_id) -> ordre courant
        for row_idx, data in self._rows(ws, sheet_type='formation'):
            titre = self._str(data.get('formation'))
            if not titre:
                errors.append(f'Formations ligne {row_idx}: formation (module) manquante')
                continue

            raw_debut = data.get('date_debut')
            raw_fin = data.get('date_fin')
            date_debut, debut_invalide = self._parse_optional_datetime(raw_debut)
            date_fin, fin_invalide = self._parse_optional_datetime(raw_fin)
            if debut_invalide or fin_invalide:
                details = []
                if debut_invalide:
                    details.append(f'date_debut={raw_debut!r}')
                if fin_invalide:
                    details.append(f'date_fin={raw_fin!r}')
                errors.append(
                    f'Formations ligne {row_idx}: date_debut ou date_fin invalide ({", ".join(details)})'
                )
                continue

            # ``duree_prevue_heures`` est facultative dans le fichier source.
            # Si la cellule est vide pour cette ligne, on **ne touche pas** au
            # ``duree_prevue_heures`` du module existant (évite d'écraser à 0
            # une valeur déjà saisie lors d'un import précédent).
            duree_raw = data.get('duree_prevue_heures')
            duree_renseignee = duree_raw not in (None, '', 0, '0')
            duree = duree_raw or 0
            try:
                duree = float(duree)
            except (ValueError, TypeError):
                duree = 0

            # intitulé du module : colonne séparée ou titre de la formation
            module_val = self._str(data.get('module')) or titre

            # Formation ne porte que : formation (titre) + numero_formation
            formation_defaults = {
                'numero_formation': self._int(data.get('numero_formation')),
            }

            # Résolution du secrétariat (pour le Module)
            _secretariat = None
            if secretariat is not None:
                _secretariat = secretariat
            else:
                raw_cat = self._str(data.get('categorie'))
                if not raw_cat and self._str(data.get('grade')):
                    first_letter = self._str(data.get('grade')).strip()[:1].upper()
                    if first_letter in ('A', 'B', 'C'):
                        raw_cat = first_letter
                cat_val = self._normalize_categorie(raw_cat)
                if cat_val:
                    if cat_val not in _secretariat_cache:
                        sec = SecretariatModel.objects.filter(type__libelle__iexact=cat_val).first()
                        # Lettre seule (A/B/C/D) ou FAB/FAC sans lettre : tenter un match par suffixe/préfixe
                        if sec is None:
                            candidates = []
                            # Cas 1: lettre seule -> match par suffixe (FAB A, FAC A, etc.)
                            if len(cat_val) == 1 and cat_val in ('A', 'B', 'C', 'D'):
                                candidates = list(
                                    SecretariatModel.objects.filter(
                                        type__libelle__iendswith=f' {cat_val}'
                                    )[:4]
                                )
                            # Cas 2: FAB ou FAC seul -> match par préfixe
                            elif cat_val in ('FAB', 'FAC'):
                                candidates = list(
                                    SecretariatModel.objects.filter(
                                        type__libelle__istartswith=cat_val
                                    )[:4]
                                )
                                # Tenter de désambiguïser avec le grade si présent
                                grade_raw = self._str(data.get('grade'))
                                if grade_raw:
                                    g = grade_raw.strip().upper()
                                    if len(g) >= 1 and g[0] in ('A', 'B', 'C', 'D'):
                                        for cand in candidates:
                                            type_label = (cand.type.libelle if cand.type else '').upper()
                                            if type_label.endswith(f' {g[0]}'):
                                                sec = cand
                                                break
                            # Désambiguïser avec le titre de formation si pas encore trouvé
                            if not sec and candidates:
                                if len(candidates) == 1:
                                    sec = candidates[0]
                                else:
                                    titre_upper = titre.upper()
                                    is_admin = 'ADMINISTRATION' in titre_upper or 'FAB' in titre_upper
                                    is_accomp = 'ACCOMPAGNEMENT' in titre_upper or 'CARRIERE' in titre_upper or 'FAC' in titre_upper
                                    for cand in candidates:
                                        type_label = (cand.type.libelle if cand.type else '').upper()
                                        if is_admin and type_label.startswith('FAB'):
                                            sec = cand
                                            break
                                        if is_accomp and type_label.startswith('FAC'):
                                            sec = cand
                                            break
                                    if sec is None:
                                        sec = candidates[0]
                        _secretariat_cache[cat_val] = sec
                        if sec:
                            self.stdout.write(f'  🗂  Catégorie {cat_val} → Secrétariat : {sec.nom}')
                        else:
                            errors.append(
                                f'Formations ligne {row_idx}: aucun secrétariat '
                                f'de type "{cat_val}" trouvé pour "{titre}"'
                            )
                    _secretariat = _secretariat_cache.get(cat_val)

            try:
                obj, created = Formation.objects.get_or_create(
                    formation=titre,
                    defaults=formation_defaults,
                )
                if not created and formation_defaults.get('numero_formation'):
                    Formation.objects.filter(pk=obj.pk).update(**{k: v for k, v in formation_defaults.items() if v is not None})
            except Formation.MultipleObjectsReturned:
                obj = Formation.objects.filter(formation=titre).order_by('id').first()
                created = False
            except Exception as e:
                errors.append(f'Formations ligne {row_idx}: erreur lors de la sauvegarde de "{titre}" — {e}')
                continue

            # Créer ou mettre à jour le Module correspondant
            # Tous les champs métier vont sur Module
            if obj.id not in _module_order:
                existing_max = obj.modules.aggregate(m=models.Max('ordre'))['m'] or 0
                _module_order[obj.id] = existing_max
            _module_order[obj.id] += 1

            statut_excel = self._str(data.get('statut'))
            module_defaults = {
                'ordre': _module_order[obj.id],
                'grade': self._normalize_grade(data.get('grade')),
                'groupe': self._normalize_field(data.get('groupe')),
                'vague': self._normalize_field(data.get('vague')),
                'date_debut': date_debut.date() if date_debut and hasattr(date_debut, 'date') else date_debut,
                'date_fin': date_fin.date() if date_fin and hasattr(date_fin, 'date') else date_fin,
                # Champ `cycle` (NOT NULL sur certaines bases) : libellé du cycle = formation parente.
                'cycle': titre,
            }
            if statut_excel:
                module_defaults['statut'] = statut_excel
            _site_name = self._str(data.get('site'))
            _bat  = self._str(data.get('batiment'))
            _sal  = self._str(data.get('salle'))
            if _site_name:
                site_obj = self._resolve_ref_site(_site_name)
                if site_obj:
                    module_defaults['site'] = site_obj
                module_defaults['site_legacy'] = _site_name
            if _bat:  module_defaults['batiment'] = _bat
            if _sal:  module_defaults['salle'] = _sal
            if _secretariat: module_defaults['secretariat'] = _secretariat
            # On n'inscrit la durée prévue que si elle est explicitement
            # renseignée dans le fichier source, afin de ne pas écraser une
            # valeur déjà saisie par une cellule vide ou nulle.
            if duree_renseignee and duree > 0:
                module_defaults['duree_prevue_heures'] = duree

            # Lookup Module : aligné sur unique_together (formation, intitule, grade, groupe, vague)
            grade_key = self._normalize_grade(data.get('grade'))
            groupe_key = self._normalize_field(data.get('groupe'))
            vague_key = self._normalize_field(data.get('vague'))
            module_lookup = {
                'formation': obj,
                'intitule': module_val,
                'grade': grade_key,
                'groupe': groupe_key,
                'vague': vague_key,
            }

            existing_mod = Module.objects.filter(**module_lookup).first()
            if existing_mod:
                for field, value in module_defaults.items():
                    setattr(existing_mod, field, value)
                if statut_excel:
                    existing_mod.statut = statut_excel
                existing_mod.save()
                _mod = existing_mod
                mod_created = False
            else:
                create_fields = {
                    k: v for k, v in module_defaults.items()
                    if k not in module_lookup and k != 'statut'
                }
                _mod = Module.objects.create(
                    **module_lookup,
                    statut=statut_excel or 'PLANIFIEE',
                    **create_fields,
                )
                mod_created = True

            if mod_created:
                count += 1
                self.stdout.write(f'  + Module : {module_val} ({grade_key}/{groupe_key}) ({duree}h)')
            else:
                modules_updated += 1
                self.stdout.write(f'  ~ Module mis à jour : {module_val} ({grade_key}/{groupe_key})')

            # Auto-inscrire les participants déjà en base qui correspondent
            # au module (grade + groupe requis, categorie/vague optionnels sur Participant)
            grade_val = module_defaults.get('grade', '')
            groupe_val = module_defaults.get('groupe', '')
            vague_val = module_defaults.get('vague', '')
            cat_val_raw = self._str(data.get('categorie'))  # categorie est sur Participant, pas Module
            if grade_val and groupe_val:
                qs = Participant.objects.filter(
                    grade__iexact=grade_val,
                    groupe__iexact=groupe_val,
                )
                if cat_val_raw:
                    qs = qs.filter(categorie__iexact=cat_val_raw)
                if vague_val:
                    qs = qs.filter(vague__iexact=vague_val)
                inscrits = 0
                for participant in qs:
                    try:
                        _, insc_created = ModuleParticipant.objects.get_or_create(
                            module=_mod, participant=participant,
                        )
                        if insc_created:
                            inscrits += 1
                    except Exception as e:
                        errors.append(
                            f'Auto-inscription impossible : {participant} → {titre} ({e})'
                        )
                if inscrits:
                    self.stdout.write(
                        f'    ↳ {inscrits} participant(s) auto-inscrit(s) '
                        f'({cat_val_raw}/{grade_val}/{groupe_val}'
                        + (f'/{vague_val}' if vague_val else '') + ')'
                    )
        return count, modules_updated

    # ─── Import Participants ─────────────────────────

    def _import_participants(self, ws, errors, secretariat=None):
        from formations.models import Secretariat as SecretariatModel
        count = 0
        inscriptions = 0
        # Cache secretariat par categorie pour éviter une requête DB par ligne
        _secretariat_cache = {}
        # Cache des recherches de modules pour éviter de re-requêter la DB
        # pour des grades/groupes/vagues identiques d'une ligne à l'autre.
        _module_match_cache = {}
        # Inscriptions à créer en masse (bulk_create) à la fin, au lieu d'un
        # get_or_create par ligne. dédoublonnées via _queued_pairs.
        _pending_inscriptions = []
        _queued_pairs = set()

        def _queue_inscription(_mod, participant, log_msg):
            pair = (_mod.id, participant.id)
            if pair in _queued_pairs:
                return
            _queued_pairs.add(pair)
            _pending_inscriptions.append(
                ModuleParticipant(
                    module=_mod,
                    participant=participant,
                    inscrit_le=timezone.now(),
                )
            )
            self.stdout.write(log_msg)

        for row_idx, data in self._rows(ws):
            nom = self._str(data.get('nom'))
            prenom = self._str(data.get('prenom'))
            if not nom or not prenom:
                errors.append(f'Participants ligne {row_idx}: nom ou prénom manquant')
                continue
            matricule = self._str(
                data.get('matricule')
                or data.get('numero')
                or data.get("n° d'inscription")
                or data.get("n°d'inscription")
            )

            date_naissance = self._parse_date(data.get('date_naissance'))

            fields = {
                'nom': nom,
                'prenom': prenom,
                'sexe': self._str(data.get('sexe')).upper(),
                'date_naissance': date_naissance,
                'lieu_naissance': self._str(data.get('lieu_naissance')),
                'email': self._str(data.get('email')),
                'telephone': self._str(data.get('telephone')),
                'telephone2': self._str(data.get('telephone2')),
                'type_concours': self._str(data.get('type_concours') or data.get('type')),
                'libelle_concours': self._str(data.get('libelle_concours')),
                'categorie': self._str(data.get('categorie')),
                'grade': self._normalize_grade(data.get('grade')),
                'groupe': self._normalize_field(data.get('groupe')),
                'grade_groupe': self._str(data.get('grade_groupe')),
                'vague': self._normalize_field(data.get('vague')),
                'motif_notoire': self._str(
                    data.get('motif_notoire') or data.get('motif') or data.get('motif_absence')
                ),
            }

            if secretariat is not None:
                # Secretariat explicitement fourni (import via API avec user SECRETARIAT)
                fields['secretariat'] = secretariat
            else:
                # Règle prioritaire par matricule:
                # FNCE* -> secrétariat FAB ; FNCP* -> secrétariat FAC.
                # Si aucun match, on conserve la règle historique par catégorie/grade.
                forced_hint = self._secretariat_hint_from_matricule(matricule)
                if forced_hint:
                    grade_letter = (fields.get('grade') or '').strip().upper()[:1]
                    cat_key = (fields.get('categorie') or '').strip().upper()
                    cache_key = f'prefix:{forced_hint}:{grade_letter}:{cat_key}'
                    if cache_key not in _secretariat_cache:
                        sec = self._resolve_secretariat(
                            SecretariatModel, forced_hint,
                            grade=fields.get('grade', ''), matricule=matricule,
                            categorie=fields.get('categorie', ''),
                        )
                        _secretariat_cache[cache_key] = sec
                        if sec:
                            self.stdout.write(
                                f'  🗂  Matricule {forced_hint}* → Secrétariat : {sec.nom}'
                            )
                        else:
                            errors.append(
                                f'Participants ligne {row_idx}: aucun secrétariat '
                                f'"{forced_hint}" trouvé pour {nom} {prenom}'
                            )
                    sec = _secretariat_cache.get(cache_key)
                    if sec:
                        fields['secretariat'] = sec
                else:
                    # Auto-affectation par catégorie : ex 'A'/'FAB A' -> secrétariat type='FAB A'
                    # Fallback : si categorie vide, déduire depuis le grade (A4 -> A, B2 -> B, C1 -> C)
                    raw_cat = fields['categorie']
                    if not raw_cat and fields['grade']:
                        first_letter = fields['grade'].strip()[:1].upper()
                        if first_letter in ('A', 'B', 'C'):
                            raw_cat = first_letter
                    cat = self._secretariat_type_from_participant(
                        raw_cat, fields.get('grade', ''),
                    )
                    if cat:
                        if cat not in _secretariat_cache:
                            sec = SecretariatModel.objects.filter(type__libelle__iexact=cat).first()
                            # Si pas de match exact, tenter par suffixe ou préfixe et résoudre ambiguïté FAB/FAC
                            if sec is None:
                                candidates = []
                                # Cas 1: catégorie lettre seule (A, B, C, D) -> match par suffixe
                                if len(cat) == 1 and cat in ('A', 'B', 'C', 'D'):
                                    candidates = list(
                                        SecretariatModel.objects.filter(
                                            type__libelle__iendswith=f' {cat}'
                                        )[:4]
                                    )
                                # Cas 2: catégorie sans lettre (FAB, FAC) -> match par préfixe
                                elif cat in ('FAB', 'FAC'):
                                    candidates = list(
                                        SecretariatModel.objects.filter(
                                            type__libelle__istartswith=cat
                                        )[:4]
                                    )
                                    # Déterminer la lettre préférée depuis le grade si présent
                                    grade_letter = ''
                                    if fields.get('grade'):
                                        g = fields['grade'].strip().upper()
                                        if len(g) >= 1 and g[0] in ('A', 'B', 'C', 'D'):
                                            grade_letter = g[0]
                                    if grade_letter:
                                        for cand in candidates:
                                            type_label = (cand.type.libelle if cand.type else '').upper()
                                            if type_label.endswith(f' {grade_letter}'):
                                                sec = cand
                                                break
                                if not sec and candidates:
                                    if len(candidates) == 1:
                                        sec = candidates[0]
                                    else:
                                        # Plusieurs candidats : résoudre ambiguïté
                                        prefers_fab = True
                                        if matricule and isinstance(matricule, str):
                                            prefers_fab = not matricule.upper().startswith('FNCP')
                                        for cand in candidates:
                                            type_label = (cand.type.libelle if cand.type else '').upper()
                                            if prefers_fab and type_label.startswith('FAB'):
                                                sec = cand
                                                break
                                            if not prefers_fab and type_label.startswith('FAC'):
                                                sec = cand
                                                break
                                        if sec is None:
                                            sec = candidates[0]
                            _secretariat_cache[cat] = sec
                            if sec:
                                self.stdout.write(
                                    f'  🗂  Catégorie {cat} → Secrétariat : {sec.nom}'
                                )
                            else:
                                errors.append(
                                    f'Participants ligne {row_idx}: aucun secrétariat '
                                    f'de type "{cat}" trouvé pour {nom} {prenom}'
                                )
                        sec = _secretariat_cache.get(cat)
                        if sec:
                            fields['secretariat'] = sec

            resolved_cat = self._resolve_categorie_participant(
                fields.get('categorie', ''),
                grade=fields.get('grade', ''),
            )
            # Conserver les catégories INJS (Élève Professeur, Étudiant LMD…)
            # si elles ne correspondent pas au référentiel CM/TD/TP.
            fields['categorie'] = resolved_cat or fields.get('categorie', '')

            if matricule:
                obj, created = Participant.objects.update_or_create(
                    matricule=matricule,
                    defaults=fields,
                )
            else:
                obj = Participant(**fields)
                obj.save()
                created = True

            if created:
                count += 1
                self.stdout.write(f'  + Participant : {obj.matricule} — {nom} {prenom}')
            else:
                self.stdout.write(f'  ~ Participant mis à jour : {matricule}')

            # Inscrire le participant aux formations
            formations_str = self._str(
                data.get('formation(s)') or data.get('formations') or data.get('formation')
            )
            if formations_str:
                # Cas 1 : colonne Formation(s) renseignée → inscription par titre
                # Filtre par groupe + grade + vague pour identifier la bonne formation
                p_groupe = self._normalize_field(data.get('groupe'))
                p_grade  = self._normalize_grade(data.get('grade'))
                p_vague  = self._normalize_field(data.get('vague'))
                titres = [t.strip() for t in formations_str.split('|') if t.strip()]
                for titre in titres:
                    cache_key = ('titre', titre.lower(), p_grade.lower(), p_groupe.lower(), p_vague.lower())
                    if cache_key not in _module_match_cache:
                        mod_qs = Module.objects.filter(formation__formation__iexact=titre)
                        # Filtres stricts : si grade/groupe/vague sont fournis, on filtre TOUJOURS
                        if p_grade:
                            mod_qs = mod_qs.filter(grade__iexact=p_grade)
                        if p_groupe:
                            mod_qs = mod_qs.filter(groupe__iexact=p_groupe)
                        # Filtre vague : supporte les formats différents
                        # Ex: fichier a "VAGUE 2", module a "SESSION 2026 VAGUE 2"
                        if p_vague:
                            # Essayer match exact d'abord
                            exact_match = mod_qs.filter(vague__iexact=p_vague)
                            if exact_match.exists():
                                mod_qs = exact_match
                            else:
                                # Sinon recherche partielle (vague du fichier contenue dans vague du module)
                                mod_qs = mod_qs.filter(vague__icontains=p_vague)
                        _module_match_cache[cache_key] = list(
                            mod_qs.select_related('formation').order_by('ordre')
                        )
                    matched_mods = _module_match_cache[cache_key]
                    if not matched_mods:
                        crit = f'formation={titre}'
                        if p_grade:
                            crit += f' grade={p_grade}'
                        if p_groupe:
                            crit += f' groupe={p_groupe}'
                        if p_vague:
                            crit += f' vague={p_vague}'
                        errors.append(f'Participants ligne {row_idx}: aucun module trouvé pour ({crit})')
                        continue
                    for _mod in matched_mods:
                        _queue_inscription(
                            _mod, obj,
                            f'    ↳ Inscrit à : {_mod.formation.formation} / {_mod.intitule} ({_mod.groupe})',
                        )
            else:
                # Cas 2 : colonne Formation(s) vide
                # Protection 1 : --disable-auto-inscription force l'utilisation explicite de Formation(s)
                if getattr(self, 'disable_auto_inscription', False):
                    errors.append(
                        f'Participants ligne {row_idx}: {nom} {prenom} '
                        f'— colonne Formation(s) obligatoire (auto-inscription désactivée)'
                    )
                else:
                    # Auto-match strict avec protections supplémentaires
                    cat = self._str(data.get('categorie'))
                    grade = self._normalize_grade(data.get('grade'))
                    groupe = self._normalize_field(data.get('groupe'))
                    vague = self._normalize_field(data.get('vague'))
                    # Protection 2 : prendre en compte la formation/cycle si disponible
                    p_formation = self._str(data.get('formation') or data.get('cycle') or data.get('formation_cycle'))

                    if grade and groupe:
                        cache_key = ('auto', grade.lower(), groupe.lower(), vague.lower(), p_formation.lower())
                        if cache_key not in _module_match_cache:
                            mod_qs = Module.objects.filter(
                                grade__iexact=grade,
                                groupe__iexact=groupe,
                            )
                            if vague:
                                exact_match = mod_qs.filter(vague__iexact=vague)
                                if exact_match.exists():
                                    mod_qs = exact_match
                                else:
                                    mod_qs = mod_qs.filter(vague__icontains=vague)
                            # Filtre par formation/cycle si spécifié
                            if p_formation:
                                mod_qs = mod_qs.filter(formation__formation__iexact=p_formation)
                            _module_match_cache[cache_key] = list(
                                mod_qs.select_related('formation').order_by('ordre')
                            )
                        matched_mods = _module_match_cache[cache_key]

                        if not matched_mods:
                            crit = f'grade={grade} groupe={groupe}'
                            if vague:
                                crit += f' vague={vague}'
                            if p_formation:
                                crit += f' formation={p_formation}'
                            errors.append(
                                f'Participants ligne {row_idx}: '
                                f'aucun module trouvé pour {nom} {prenom} '
                                f'({crit})'
                            )
                        else:
                            for _mod in matched_mods:
                                _queue_inscription(
                                    _mod, obj,
                                    f'    ↳ Auto-inscrit → {_mod.formation.formation} / {_mod.intitule}',
                                )
                    elif not (grade or groupe):
                        errors.append(
                            f'Participants ligne {row_idx}: {nom} {prenom} '
                            f'sans Formation(s) ni grade/groupe — pas inscrit'
                        )
                    else:
                        errors.append(
                            f'Participants ligne {row_idx}: {nom} {prenom} '
                            f'auto-match incomplet (grade={grade!r} groupe={groupe!r}) '
                            f'— les 2 critères grade+groupe sont requis'
                        )

        # Création en masse des inscriptions : on filtre celles déjà existantes
        # en une seule requête, puis bulk_create (ignore_conflicts par sécurité).
        if _pending_inscriptions:
            module_ids = {mp.module_id for mp in _pending_inscriptions}
            existing_pairs = set(
                ModuleParticipant.objects.filter(module_id__in=module_ids)
                .values_list('module_id', 'participant_id')
            )
            to_create = [
                mp for mp in _pending_inscriptions
                if (mp.module_id, mp.participant_id) not in existing_pairs
            ]
            if to_create:
                ModuleParticipant.objects.bulk_create(to_create, ignore_conflicts=True)
            inscriptions = len(to_create)

        if inscriptions:
            self.stdout.write(f'  📌 {inscriptions} inscription(s) créée(s)')
        return count

    # ─── Import Formateurs ───────────────────────────

    def _import_formateurs(self, ws, errors):
        count = 0
        for row_idx, data in self._rows(ws):
            nom = self._str(data.get('nom'))
            prenom = self._str(data.get('prenom'))
            if not nom or not prenom:
                errors.append(f'Formateurs ligne {row_idx}: nom ou prénom manquant')
                continue
            numero = self._str(data.get('numero'))

            fields = {
                'nom': nom,
                'prenom': prenom,
                'email': self._str(data.get('email')),
                'telephone': self._str(data.get('telephone')),
                'specialite': self._str(data.get('specialite')),
                'organisation': self._str(data.get('organisation')),
            }

            try:
                if numero:
                    obj, created = Formateur.objects.update_or_create(
                        numerobadge=numero,
                        defaults=fields,
                    )
                else:
                    obj, created = Formateur.objects.get_or_create(
                        nom__iexact=nom,
                        prenom__iexact=prenom,
                        defaults=fields,
                    )
                    if not created:
                        for k, v in fields.items():
                            setattr(obj, k, v)
                        obj.save()
            except Exception as e:
                errors.append(f'Formateurs ligne {row_idx}: erreur lors de la sauvegarde de {nom} {prenom} — {e}')
                continue

            if created:
                count += 1
                self.stdout.write(f'  + Formateur : {obj.numerobadge} — {nom} {prenom}')
            else:
                self.stdout.write(f'  ~ Formateur mis à jour : {obj.numerobadge} — {nom} {prenom}')
        return count

    # ─── Import Inscriptions ─────────────────────────

    def _import_inscriptions(self, ws, errors):
        count = 0
        for row_idx, data in self._rows(ws):
            titre = self._str(data.get('formation_titre'))
            numero = self._str(data.get('participant_numero'))
            if not titre or not numero:
                errors.append(f'Inscriptions ligne {row_idx}: formation_titre ou participant_numero manquant')
                continue

            try:
                formation = Formation.objects.get(formation=titre)
            except Formation.DoesNotExist:
                errors.append(f'Inscriptions ligne {row_idx}: formation "{titre}" introuvable')
                continue
            except Formation.MultipleObjectsReturned:
                formation = Formation.objects.filter(formation=titre).first()

            try:
                participant = Participant.objects.get(matricule=numero)
            except Participant.DoesNotExist:
                errors.append(f'Inscriptions ligne {row_idx}: participant "{numero}" introuvable')
                continue

            module_intitule = self._str(data.get('module_titre') or data.get('module'))
            if module_intitule:
                _mod = formation.modules.filter(intitule__iexact=module_intitule).first()
            else:
                _mod = formation.modules.order_by('ordre').first()
            if not _mod:
                errors.append(f'Inscriptions ligne {row_idx}: formation "{titre}" n\'a aucun module')
                continue

            _, created = ModuleParticipant.objects.get_or_create(
                module=_mod, participant=participant,
            )
            if created:
                count += 1
                self.stdout.write(f'  + Inscription : {numero} → {titre} / {_mod.intitule}')
            else:
                self.stdout.write(f'  ~ Déjà inscrit : {numero} → {titre} / {_mod.intitule}')
        return count

    # ─── Import Formateurs ↔ Formations ──────────────

    def _import_formateurs_formations(self, ws, errors):
        count = 0
        for row_idx, data in self._rows(ws):
            titre = self._str(data.get('formation_titre'))
            numero = self._str(data.get('formateur_numero'))
            if not titre or not numero:
                errors.append(f'Formateurs_Formations ligne {row_idx}: données manquantes')
                continue

            try:
                formation = Formation.objects.get(formation=titre)
            except Formation.DoesNotExist:
                errors.append(f'Formateurs_Formations ligne {row_idx}: formation "{titre}" introuvable')
                continue
            except Formation.MultipleObjectsReturned:
                formation = Formation.objects.filter(formation=titre).first()

            try:
                formateur = Formateur.objects.get(numerobadge=numero)
            except Formateur.DoesNotExist:
                errors.append(f'Formateurs_Formations ligne {row_idx}: formateur "{numero}" introuvable')
                continue

            _mod = formation.modules.order_by('ordre').first()
            if not _mod:
                errors.append(f'Formateurs_Formations ligne {row_idx}: formation "{titre}" n\'a aucun module')
                continue
            _, created = ModuleFormateur.objects.get_or_create(
                module=_mod, formateur=formateur,
            )
            if created:
                count += 1
                self.stdout.write(f'  + Formateur assigné : {numero} → {titre}')
            else:
                self.stdout.write(f'  ~ Déjà assigné : {numero} → {titre}')
        return count


    # ─── Import Séances ──────────────────────────────

    def _import_seances_for_formation(self, ws, errors, formation):
        """Import séances pour une formation déjà connue (pas besoin de formation_titre)."""
        count = 0
        for row_idx, data in self._rows(ws):
            date_journee = self._parse_date(data.get('date_journee') or data.get('date'))
            if not date_journee:
                errors.append(f'Séances ligne {row_idx}: date_journee invalide ou manquante')
                continue

            numero = self._int(data.get('numero') or data.get('numero_seance'), default=None)
            if numero is None:
                errors.append(f'Séances ligne {row_idx}: numero de séance manquant')
                continue

            heure_debut = self._parse_time(
                data.get('heure_debut') or data.get('heure debut') or data.get('heure_debut_prevue')
            )
            heure_fin = self._parse_time(
                data.get('heure_fin') or data.get('heure fin') or data.get('heure_fin_prevue')
            )

            update_fields = {'intitule': self._str(data.get('intitule'))}
            if heure_debut is not None:
                update_fields['heure_debut_prevue'] = heure_debut
            if heure_fin is not None:
                update_fields['heure_fin_prevue'] = heure_fin

            _mod = formation.modules.order_by('ordre').first()
            if not _mod:
                errors.append(f'Séances ligne {row_idx}: formation sans module')
                continue
            obj, created = SessionModule.objects.update_or_create(
                module=_mod,
                date_journee=date_journee,
                numero=numero,
                defaults=update_fields,
            )
            if created:
                count += 1
        return count

    def _import_emploi_du_temps(self, ws, errors):
        """
        Import emploi du temps (séances) depuis un fichier à headers libres.
        Colonnes reconnues (insensible à la casse/accents) :
          - formation / titre           → titre de la formation (obligatoire)
          - date / date journée         → date de la séance (obligatoire)
          - numéro / numero / n°        → numéro de séance (obligatoire)
          - intitulé / intitule         → libellé de la séance (OPTIONNEL)
          - heure début / heure_debut   → heure de début (optionnel)
          - heure fin / heure_fin       → heure de fin (optionnel)
          - auto-démarrage / auto       → booléen (optionnel, défaut=True)
        Si les colonnes ne sont pas détectées par nom, fallback par position :
          0=formation, 1=date, 2=numéro, 3=heure début, 4=heure fin, 5=auto
        """
        count = 0
        col_map = {}  # nom normalisé → index colonne

        def _norm(h):
            import unicodedata
            s = unicodedata.normalize('NFD', str(h).strip().lower())
            s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
            return s.replace('-', ' ').replace('_', ' ')

        for row_idx, row in enumerate(ws.iter_rows(values_only=True), 1):
            if row_idx == 1:
                # Construire le mapping header → index
                for idx, h in enumerate(row):
                    if h is None:
                        continue
                    n = _norm(h)
                    if any(k in n for k in ('formation',)) and 'col_formation' not in col_map:
                        col_map['col_formation'] = idx
                    elif any(k in n for k in ('date',)) and 'col_date' not in col_map:
                        col_map['col_date'] = idx
                    elif any(k in n for k in ('numero', 'n°', 'no')) and 'col_numero' not in col_map:
                        col_map['col_numero'] = idx
                    elif any(k in n for k in ('intitule', 'intitule', 'libelle', 'session')):
                        col_map['col_intitule'] = idx
                    elif any(k in n for k in ('heure debut', 'debut')) and 'col_hdebut' not in col_map:
                        col_map['col_hdebut'] = idx
                    elif any(k in n for k in ('heure fin', 'fin')) and 'col_hfin' not in col_map:
                        col_map['col_hfin'] = idx
                    elif any(k in n for k in ('auto',)):
                        col_map['col_auto'] = idx

                # Fallback par position si colonnes non détectées
                if 'col_formation' not in col_map: col_map['col_formation'] = 0
                if 'col_date' not in col_map: col_map['col_date'] = 1
                if 'col_numero' not in col_map: col_map['col_numero'] = 2
                # Sans intitulé : heure début = col 3, heure fin = col 4
                if 'col_intitule' not in col_map:
                    if 'col_hdebut' not in col_map: col_map['col_hdebut'] = 3
                    if 'col_hfin' not in col_map: col_map['col_hfin'] = 4
                    if 'col_auto' not in col_map: col_map['col_auto'] = 5
                else:
                    if 'col_hdebut' not in col_map: col_map['col_hdebut'] = 4
                    if 'col_hfin' not in col_map: col_map['col_hfin'] = 5
                    if 'col_auto' not in col_map: col_map['col_auto'] = 6

                self.stdout.write(f'  [EDT] Mapping colonnes : {col_map}')
                continue

            if not row or all(v is None or str(v).strip() == '' for v in row):
                break

            def _col(key): return row[col_map[key]] if col_map.get(key) is not None and col_map[key] < len(row) else None

            titre = self._str(_col('col_formation'))
            date_val = _col('col_date')
            numero_val = _col('col_numero')
            heure_debut_val = _col('col_hdebut')
            heure_fin_val = _col('col_hfin')
            auto_val = self._str(_col('col_auto'))
            intitule_val = _col('col_intitule') if 'col_intitule' in col_map else None

            if not titre:
                errors.append(f'Emploi du temps ligne {row_idx}: titre de formation manquant')
                continue

            date_journee = self._parse_date(date_val)
            if not date_journee:
                errors.append(f'Emploi du temps ligne {row_idx}: date invalide pour "{titre}"')
                continue

            numero = self._int(numero_val, default=None)
            if numero is None:
                errors.append(f'Emploi du temps ligne {row_idx}: numéro de séance manquant pour "{titre}"')
                continue

            try:
                formation = Formation.objects.get(formation=titre)
            except Formation.DoesNotExist:
                errors.append(f'Emploi du temps ligne {row_idx}: formation "{titre}" introuvable en base')
                continue
            except Formation.MultipleObjectsReturned:
                formation = Formation.objects.filter(formation=titre).first()

            heure_debut = self._parse_time(heure_debut_val)
            heure_fin = self._parse_time(heure_fin_val)
            auto_demarrage = auto_val.lower() in ('oui', 'yes', '1', 'true') if auto_val else True

            _mod = formation.modules.order_by('ordre').first()
            if not _mod:
                errors.append(f'Emploi du temps ligne {row_idx}: formation "{titre}" sans module')
                continue
            obj, created = SessionModule.objects.update_or_create(
                module=_mod,
                date_journee=date_journee,
                numero=numero,
                defaults={
                    'intitule': self._str(intitule_val),
                    'heure_debut_prevue': heure_debut,
                    'heure_fin_prevue': heure_fin,
                    'auto_demarrage': auto_demarrage,
                },
            )
            if created:
                count += 1
                self.stdout.write(f'  + Séance : {titre} — {date_journee} n°{numero}')
            else:
                self.stdout.write(f'  ~ Séance mise à jour : {titre} — {date_journee} n°{numero}')
        return count

    def _import_seances(self, ws, errors):
        """
        Dispatch des séances par Module (intitule + grade + groupe + vague).
        grade, groupe et vague sont obligatoires pour identifier le cours cible.
        """
        count = 0
        updated = 0
        last_ctx = {'grade': '', 'groupe': '', 'vague': ''}
        for row_idx, data in self._rows(ws):
            titre = self._str(
                data.get('module_titre')
                or data.get('formation_titre')
                or data.get('formation')
                or data.get('module')
            )
            if not titre:
                errors.append(f'Séances ligne {row_idx}: module_titre manquant')
                continue

            date_journee = self._parse_date(data.get('date_journee') or data.get('date'))
            if not date_journee:
                errors.append(f'Séances ligne {row_idx}: date_journee invalide ou manquante')
                continue

            numero = self._int(data.get('numero') or data.get('numero_seance'), default=None)
            if numero is None:
                errors.append(f'Séances ligne {row_idx}: numero de séance manquant')
                continue

            raw_groupe = data.get('groupe')
            raw_grade = data.get('grade')
            raw_vague = data.get('vague')
            groupe = self._normalize_field(raw_groupe) or last_ctx['groupe']
            grade = self._normalize_grade(raw_grade) or last_ctx['grade']
            vague = self._normalize_field(raw_vague) or last_ctx['vague']

            if self._has_value(raw_groupe):
                last_ctx['groupe'] = groupe
            if self._has_value(raw_grade):
                last_ctx['grade'] = grade
            if self._has_value(raw_vague):
                last_ctx['vague'] = vague

            missing = [label for label, val in (
                ('grade', grade), ('groupe', groupe), ('vague', vague),
            ) if not val]
            if missing:
                errors.append(
                    f'Séances ligne {row_idx}: {", ".join(missing)} manquant(s) '
                    f'(obligatoires pour identifier le cours)'
                )
                continue

            modules_matched, resolve_hint = self._resolve_modules_for_seance(
                titre, grade, groupe, vague,
            )

            if not modules_matched:
                errors.append(
                    f'Séances ligne {row_idx}: module "{titre}" introuvable '
                    f'(grade={grade!r}, groupe={groupe!r}, vague={vague!r})'
                )
                continue

            if resolve_hint:
                self.stdout.write(f'  ↪ Ligne {row_idx}: {resolve_hint}')

            heure_debut = self._parse_time(data.get('heure_debut'))
            heure_fin = self._parse_time(data.get('heure_fin'))
            intitule = self._str(data.get('intitule') or titre)

            for module_obj in modules_matched:
                obj, created = SessionModule.objects.get_or_create(
                    module=module_obj,
                    date_journee=date_journee,
                    numero=numero,
                    defaults={
                        'intitule': intitule,
                        'heure_debut_prevue': heure_debut,
                        'heure_fin_prevue': heure_fin,
                    },
                )
                if created:
                    count += 1
                    self.stdout.write(
                        f'  + Séance : {module_obj.intitule} '
                        f'({module_obj.grade}/{module_obj.groupe}) — {date_journee} n°{numero}'
                    )
                else:
                    # Mettre à jour les heures si fournies
                    changed = False
                    if heure_debut and obj.heure_debut_prevue != heure_debut:
                        obj.heure_debut_prevue = heure_debut
                        changed = True
                    if heure_fin and obj.heure_fin_prevue != heure_fin:
                        obj.heure_fin_prevue = heure_fin
                        changed = True
                    if changed:
                        obj.save(update_fields=['heure_debut_prevue', 'heure_fin_prevue'])
                    updated += 1
                    self.stdout.write(
                        f'  ~ Séance existante : {module_obj.intitule} '
                        f'({module_obj.grade}/{module_obj.groupe}) — {date_journee} n°{numero}'
                    )
        return count, updated

    def _parse_time(self, val):
        if val is None:
            return None
        from datetime import time
        if isinstance(val, time):
            return val
        if isinstance(val, datetime):
            return val.time()
        if isinstance(val, float):
            # Excel stores times as a fraction of 24h (e.g. 0.333... = 08:00)
            total_seconds = round(val * 86400)
            h = (total_seconds // 3600) % 24
            m = (total_seconds % 3600) // 60
            s = total_seconds % 60
            return time(h, m, s)
        val = str(val).strip()
        for fmt in ('%H:%M:%S', '%H:%M', '%H%M'):
            try:
                return datetime.strptime(val, fmt).time()
            except ValueError:
                continue
        return None


class _DryRunRollback(Exception):
    """Exception interne pour annuler la transaction en dry-run."""
    pass
