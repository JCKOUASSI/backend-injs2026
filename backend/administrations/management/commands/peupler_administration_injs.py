"""Peuplement de démonstration du module Administration INJS (03/11/2026).

Remplit, de façon **idempotente** et entièrement étiquetée « démo fictive »,
les zones de la fiche du module Administration qui interviennent directement
dans le processus LMD de l'INJS d'Abidjan :

1. organigramme réel du processus : Directions → Départements → Services
   (modèle fonctionnel 13), avec responsable par unité ;
2. Secrétariats pédagogiques rattachés aux départements de scolarité ;
3. profils utilisateurs **fictifs** (comptes `demo.*`, mot de passe de
   démonstration unique) portant le rôle applicatif et le groupe de
   permissions de leur fonction — à désactiver hors démonstration ;
4. Personnels : agents RH, fonctions et affectations correspondantes ;
5. Courriers et documents officiels fictifs, avec fichiers PDF générés ;
6. Réunions, commissions et missions du processus ;
7. Archives : courriers/documents archivés et modules opérationnels archivés
   portant listes de notes validées et cahiers d'appel (séances + pointages).

Aucun montant n'est inventé (budgets de mission à 0) ; les notes et présences
des archives sont des données d'étudiants fictifs `DEMO-ARCH-*`, jamais
confondues avec des données réelles.

Usage : python manage.py peupler_administration_injs [--dry-run]
"""

from datetime import date, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from administrations.models import (
    Courrier,
    Departement,
    Direction,
    DocumentOfficiel,
    Mission,
    ReunionCommission,
    VersionDocument,
)
from authentication.role_groups import ensure_role_groups
from formations.models import (
    Formateur,
    Formation,
    Module,
    ModuleFormateur,
    ModuleParticipant,
    NoteModule,
    NoteModuleColonne,
    Participant,
    Secretariat,
    SessionModule,
)
from presences.models import Pointage
from ressources_humaines.models import (
    AffectationRH, Agent, DisponibiliteAgent, DocumentRH, Fonction, Service,
)

User = get_user_model()

MOT_DE_PASSE_DEMO = 'DemoInjs2026!'
MARQUE = '[Démo fictive]'

# Noms fictifs (prénom, nom) — personnes imaginaires, aucune homonymie visée.
NOMS = [
    ('Aya', 'Kouadio'), ('Koffi', 'N’Guessan'), ('Mariam', 'Touré'),
    ('Jean-Marc', 'Aka'), ('Fatou', 'Sangaré'), ('Yao', 'Koné'),
    ('Aminata', 'Diabaté'), ('Serge', 'Affoué'), ('Nadia', 'Bamba'),
    ('Olivier', 'Diarra'), ('Grace', 'Yao'), ('Ibrahim', 'Coulibaly'),
    ('Larissa', 'Ehui'), ('Franck', 'Gbaka'), ('Salimata', 'Fofana'),
    ('Arnaud', 'Kacou'), ('Estelle', 'Bakayoko'), ('Moussa', 'Sanogo'),
    ('Prisca', 'Adjoua'), ('Hervé', 'Lago'), ('Rokia', 'Traoré'),
    ('Cédric', 'Mobio'), ('Vanessa', 'Krah'), ('Seydou', 'Doumbia'),
    ('Inès', 'Amani'), ('Toussaint', 'Yapi'), ('Kadidiatou', 'Sylla'),
    ('Landry', 'Dibo'), ('Murielle', 'Kobenan'), ('Aziz', 'Ouattara'),
    ('Josiane', 'Britto'), ('Wilfried', 'Adayé'), ('Ténin', 'Doukouré'),
    ('Ghislain', 'N’Dri'), ('Reine', 'Assoumou'), ('Bakary', 'Kéita'),
    ('Christelle', 'Aboa'), ('Noël', 'Gnahoua'), ('Pélagie', 'Somé'),
    ('Ulrich', 'Tano'), ('Larissa', 'Djédjé'), ('Fabrice', 'Konan'),
    ('Sandrine', 'Yéo'), ('Mamadou', 'Traoré'), ('Aïcha', 'Diaby'),
    ('Windé', 'Soro'), ('Hermann', 'Zadi'), ('Clarisse', 'Pokou'),
    ('Daouda', 'Camara'), ('Rosine', 'Eba'), ('Joël', 'Bayala'),
]

DIRECTIONS = [
    ('DG', 'Direction Générale', 'Pilotage général de l’Institut, ordonnancement des processus LMD.'),
    ('SG', 'Secrétariat Général', 'Coordination administrative, courrier, archives et documentation.'),
    ('DENSEPS', 'Direction de l’ENSEPS (STAPS)', 'École des Sciences et Techniques des Activités Physiques et Sportives.'),
    ('DENSEP', 'Direction de l’ENSEP (STASE)', 'École de l’Éducation Permanente et de l’animation socio-éducative.'),
    ('DEF', 'Direction des Études, de la Formation et de la Recherche', 'Maquettes, examens, jurys, stages et diplômation.'),
    ('DAFB', 'Direction des Affaires Financières et du Budget', 'Budget, comptabilité, trésorerie et vacations.'),
    ('DRH', 'Direction des Ressources Humaines', 'Personnel, carrières et formation continue.'),
    ('DLPIS', 'Direction de la Logistique, du Patrimoine et des Infrastructures Sportives', 'Infrastructures sportives, maintenance et patrimoine.'),
]

DEPARTEMENTS = [
    ('DG', 'DG-CAB', 'Cabinet et communication'),
    ('DG', 'DG-CIQ', 'Contrôle interne, qualité et audit'),
    ('SG', 'SG-ARC', 'Archives, courrier et documentation institutionnelle'),
    ('DENSEPS', 'ENSEPS-SCOL', 'Scolarité ENSEPS et vie étudiante'),
    ('DENSEPS', 'ENSEPS-PED', 'Pédagogie, maquettes et emplois du temps STAPS'),
    ('DENSEP', 'ENSEP-SCOL', 'Scolarité ENSEP et formation des adultes'),
    ('DENSEP', 'ENSEP-PED', 'Pédagogie et programmes STASE'),
    ('DEF', 'DEF-EXAM', 'Examens, concours et jurys'),
    ('DEF', 'DEF-STAGES', 'Stages, insertion et partenariats'),
    ('DAFB', 'DAF-BUD', 'Budget et ordonnancement'),
    ('DAFB', 'DAF-CPT', 'Comptabilité, trésorerie et vacations'),
    ('DRH', 'DRH-PERS', 'Gestion du personnel et des carrières'),
    ('DRH', 'DRH-FORM', 'Formation continue du personnel'),
    ('DLPIS', 'DL-INFRA', 'Infrastructures sportives et plateaux techniques'),
    ('DLPIS', 'DL-LOG', 'Logistique, maintenance et patrimoine'),
]

# (département, code, nom, rôle du responsable)
SERVICES = [
    ('DG-CAB', 'SRV-ACC', 'Accueil, courrier et relations extérieures', 'INJS_ADMIN'),
    ('SG-ARC', 'SRV-ARCH', 'Service des archives institutionnelles', 'ARCHIVE'),
    ('SG-ARC', 'SRV-DOC', 'Service documentation et bibliothèque', 'ARCHIVE'),
    ('ENSEPS-SCOL', 'SRV-SCOL-EPS', 'Secrétariat de scolarité ENSEPS', 'CHEF_SECRETARIAT'),
    ('ENSEPS-PED', 'SRV-MAQ-EPS', 'Service maquettes et emplois du temps STAPS', 'INJS_ADMIN'),
    ('ENSEP-SCOL', 'SRV-SCOL-EP', 'Secrétariat de scolarité ENSEP', 'CHEF_SECRETARIAT'),
    ('ENSEP-PED', 'SRV-PROG-EP', 'Service des programmes STASE', 'INJS_ADMIN'),
    ('DEF-EXAM', 'SRV-CONC', 'Service des concours et admissions', 'CHEF_SECRETARIAT'),
    ('DEF-EXAM', 'SRV-JURY', 'Service des jurys et de la diplômation', 'CHEF_SECRETARIAT'),
    ('DEF-STAGES', 'SRV-STG', 'Service des stages et de l’insertion professionnelle', 'INJS_ADMIN'),
    ('DAF-BUD', 'SRV-BUD', 'Service du budget', 'FINANCE'),
    ('DAF-CPT', 'SRV-TRE', 'Service de la trésorerie et des vacations', 'FINANCE'),
    ('DRH-PERS', 'SRV-CAR', 'Service des carrières et dossiers du personnel', 'INJS_ADMIN'),
    ('DRH-FORM', 'SRV-FC', 'Service formation continue et perfectionnement', 'INJS_ADMIN'),
    ('DL-INFRA', 'SRV-INFRA', 'Service des infrastructures sportives', 'ENCADRANT'),
    ('DL-LOG', 'SRV-PAT', 'Service maintenance et patrimoine', 'ENCADRANT'),
]

SECRETARIATS = [
    ('SEC-01', 'Secrétariat Pédagogique ENSEPS', 'ENSEPS-SCOL'),
    ('SEC-02', 'Secrétariat Pédagogique ENSEP', 'ENSEP-SCOL'),
    ('SEC-03', 'Secrétariat des Concours et de la Scolarité Centrale', 'DEF-EXAM'),
]

COURRIERS = [
    ('ENTRANT', 'Transmission de la liste des admis aux concours d’entrée 2026', 'Ministère de tutelle — Cabinet', 'Direction Générale', 'CLASSE'),
    ('ENTRANT', 'Demande d’homologation des infrastructures sportives', 'Fédération sportive nationale', 'Service des infrastructures sportives', 'EN_COURS'),
    ('ENTRANT', 'Notification des crédits de fonctionnement 2026-2027', 'Direction des affaires financières', 'Direction des Affaires Financières et du Budget', 'REPONDU'),
    ('ENTRANT', 'Transmission des maquettes pédagogiques révisées STAPS', 'Conseil de perfectionnement', 'Service maquettes et emplois du temps STAPS', 'EN_COURS'),
    ('SORTANT', 'Convocation du conseil de direction de rentrée', 'Direction Générale', 'Directeurs et chefs de département', 'CLASSE'),
    ('SORTANT', 'Transmission du budget prévisionnel 2026-2027', 'Direction des Affaires Financières et du Budget', 'Ministère de tutelle — Cabinet', 'CLASSE'),
    ('SORTANT', 'Notification des résultats des concours d’entrée', 'Service des concours et admissions', 'Directions régionales des sports', 'REPONDU'),
    ('SORTANT', 'Note d’information — calendrier des évaluations du semestre 1', 'Département Examens, concours et jurys', 'Enseignants et étudiants', 'CLASSE'),
    ('ENTRANT', 'Demande de mise à disposition du gymnase pour le championnat universitaire', 'Office national des sports universitaires', 'Direction de la Logistique (DLPIS)', 'RECU'),
    ('SORTANT', 'Accusé de réception — partenariat stages pratiques', 'Direction des Études (DEF)', 'Collectivité territoriale partenaire', 'REPONDU'),
    ('ENTRANT', 'Versement des listes de notes validées 2025-2026 aux archives', 'Secrétariats pédagogiques ENSEPS/ENSEP', 'Service des archives institutionnelles', 'ARCHIVE'),
    ('ENTRANT', 'Versement des cahiers d’appel 2025-2026 aux archives', 'Secrétariats pédagogiques ENSEPS/ENSEP', 'Service des archives institutionnelles', 'ARCHIVE'),
    ('SORTANT', 'Bordereau de versement d’archives — série scolarité 2024-2025', 'Service des archives institutionnelles', 'Archives nationales — dépôt', 'ARCHIVE'),
    ('ENTRANT', 'Invitation au comité national de pilotage de la formation sportive', 'Ministère de tutelle — DRH', 'Direction Générale', 'RECU'),
]

DOCUMENTS = [
    ('NOTE_SERVICE', 'DOC-2026/001', 'Note de service — organisation de la rentrée universitaire 2026-2027', 'PUBLIE'),
    ('NOTE_SERVICE', 'DOC-2026/002', 'Note de service — calendrier des jurys de délibération LMD', 'SIGNE'),
    ('DECISION', 'DOC-2026/003', 'Décision portant composition des jurys de fin de cycle 2026-2027', 'PUBLIE'),
    ('DECISION', 'DOC-2026/004', 'Décision portant ouverture des concours d’entrée 2027', 'EN_VALIDATION'),
    ('CIRCULAIRE', 'DOC-2026/005', 'Circulaire relative à la conservation et au versement des archives de scolarité', 'PUBLIE'),
    ('CIRCULAIRE', 'DOC-2026/006', 'Circulaire — procédure de demande et de validation des missions', 'SIGNE'),
    ('ARRETE', 'DOC-2026/007', 'Arrêté portant règlement intérieur des infrastructures sportives', 'PUBLIE'),
    ('ARRETE', 'DOC-2026/008', 'Arrêté fixant les modalités d’archivage des listes de notes et cahiers d’appel', 'SIGNE'),
    ('NOTE_SERVICE', 'DOC-2026/009', 'Note d’information — inventaire annuel du matériel sportif', 'BROUILLON'),
    ('AUTRE', 'DOC-2025/014', 'Charte d’archivage des documents pédagogiques (version archivée)', 'ARCHIVE'),
]

REUNIONS = [
    ('Conseil de direction', 'Conseil de direction de rentrée 2026-2027', date(2026, 10, 6), 'PV_EMIS'),
    ('Commission pédagogique', 'Validation des maquettes et emplois du temps 2026-2027', date(2026, 10, 13), 'PV_EMIS'),
    ('Jury de délibération', 'Jury de délibération Licence 3 STAPS — session 2026', date(2026, 11, 18), 'PLANIFIEE'),
    ('Commission des concours', 'Préparation des concours d’entrée 2027', date(2026, 12, 2), 'PLANIFIEE'),
    ('Commission budget', 'Examen du budget prévisionnel 2026-2027', date(2026, 10, 20), 'TENUE'),
    ('Comité qualité et archives', 'Revue des versements d’archives de scolarité', date(2026, 11, 10), 'TENUE'),
    ('Commission des stages', 'Validation des organismes d’accueil 2026-2027', date(2026, 11, 24), 'PLANIFIEE'),
    ('Conseil d’école ENSEPS', 'Conseil d’école ENSEPS — suivi des groupes et des salles', date(2026, 12, 8), 'PLANIFIEE'),
    ('Conseil d’école ENSEP', 'Conseil d’école ENSEP — formations professionnelles', date(2026, 12, 15), 'PLANIFIEE'),
    ('Assemblée du personnel', 'Assemblée générale du personnel — bilan du semestre', date(2027, 1, 26), 'PLANIFIEE'),
]

MISSIONS = [
    ('Mission d’encadrement — championnat universitaire national', 'Yamoussoukro', date(2026, 10, 16), date(2026, 10, 18), 'TERMINEE'),
    ('Mission de supervision des stages pratiques ENSEPS', 'Bouaké', date(2026, 10, 26), date(2026, 10, 30), 'EN_COURS'),
    ('Mission d’évaluation des infrastructures sportives régionales', 'Daloa', date(2026, 11, 9), date(2026, 11, 12), 'VALIDEE'),
    ('Atelier national sur les référentiels de formation LMD', 'Grand-Bassam', date(2026, 11, 16), date(2026, 11, 18), 'VALIDEE'),
    ('Mission de prospection des organismes d’accueil de stages', 'Divo', date(2026, 11, 23), date(2026, 11, 25), 'PROPOSEE'),
    ('Mission d’audit interne — archives et GED', 'Abidjan', date(2026, 12, 14), date(2026, 12, 16), 'PROPOSEE'),
    ('Colloque régional sport, jeunesse et éducation permanente', 'Abidjan', date(2026, 12, 7), date(2026, 12, 9), 'VALIDEE'),
    ('Mission de recensement des équipements sportifs', 'Bouaflé', date(2026, 10, 19), date(2026, 10, 21), 'TERMINEE'),
]

ETUDIANTS_DEMO = [
    ('N’Dri', 'Konan Elvis'), ('Kouadio', 'Aya Marie'), ('Touré', 'Ibrahim'),
    ('Sangaré', 'Fatou'), ('Aka', 'Jean-Bosco'), ('Diabaté', 'Aminata'),
    ('Koné', 'Yao Serge'), ('Bamba', 'Nadia'), ('Diarra', 'Olivier'),
    ('Yao', 'Grace Emmanuelle'), ('Coulibaly', 'Souleymane'), ('Ehui', 'Larissa'),
]


def _pdf_fictif(titre):
    """PDF minimal valide, généré en mémoire (fichier fictif de démonstration)."""
    texte = f"{titre} — document fictif genere pour la demonstration INJS-LMD."
    contenu = f"BT /F1 11 Tf 40 800 Td ({texte[:90]}) Tj ET"
    objets = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        f"<< /Length {len(contenu)} >>\nstream\n{contenu}\nendstream".encode(),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    pdf = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, obj in enumerate(objets, start=1):
        offsets.append(len(pdf))
        pdf += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(pdf)
    pdf += f"xref\n0 {len(objets)+1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        pdf += f"{off:010d} 00000 n \n".encode()
    pdf += f"trailer\n<< /Size {len(objets)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode()
    return bytes(pdf)


class Command(BaseCommand):
    help = 'Peuple le module Administration INJS (organigramme, comptes fictifs, archives).'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        dry = options['dry_run']
        with transaction.atomic():
            bilan = self._peupler()
            if dry:
                transaction.set_rollback(True)
        self.stdout.write(self.style.SUCCESS(
            ('SIMULATION — ' if dry else '') + 'Administration INJS peuplée : '
            + ' · '.join(f'{k}={v}' for k, v in bilan.items())
        ))

    # ── Utilisateurs fictifs ─────────────────────────────────────────────
    def _utilisateur(self, index, slug, role, fonction_libelle):
        prenom, nom = NOMS[index % len(NOMS)]
        username = f'demo.{slug.lower().replace("-", ".")}'
        user, _ = User.objects.update_or_create(
            username=username,
            defaults={
                'first_name': prenom, 'last_name': f'{nom} (démo)',
                'email': f'{username}@demo.injs.ci', 'role': role,
                'is_active': True, 'must_change_password': False,
                'organisation': 'INJS — Institut National de la Jeunesse et des Sports (démo)',
            },
        )
        # Des signaux de provisionnement peuvent poser un mot de passe généré
        # à la création du compte : on force celui de démonstration, annoncé.
        if not user.check_password(MOT_DE_PASSE_DEMO):
            user.set_password(MOT_DE_PASSE_DEMO)
            user.save(update_fields=['password'])
        from authentication.role_groups import ROLE_GROUP_NAMES
        from django.contrib.auth.models import Group
        groupe = Group.objects.filter(name=ROLE_GROUP_NAMES.get(role, '')).first()
        if groupe:
            user.groups.add(groupe)
        return user, (prenom, nom, fonction_libelle)

    def _agent(self, user, prenom, nom, fonction, rang):
        matricule = f'PERS-DEMO-{user.id:03d}'
        # Variété réaliste et déterministe : entrées échelonnées 2016-2025,
        # contrats selon le profil (fonctionnaire majoritaire, contractuels
        # et vacataires en appui) — fini les 45 lignes identiques.
        date_entree = date(2016 + (rang % 10), 9, 1)
        if user.role == 'SECRETARIAT':
            type_contrat = Agent.TypeContrat.CONTRAT
        elif user.role == 'ENCADRANT':
            type_contrat = Agent.TypeContrat.VACATAIRE
        elif rang % 9 == 4:
            type_contrat = Agent.TypeContrat.CONTRAT
        else:
            type_contrat = Agent.TypeContrat.FONCTIONNAIRE
        agent, _ = Agent.objects.update_or_create(
            matricule=matricule,
            defaults={
                'user': user, 'nom': nom, 'prenom': prenom,
                'email': user.email, 'type_contrat': type_contrat,
                'statut': Agent.Statut.ACTIF, 'date_entree': date_entree,
                'telephone': f'+225 07 08 {10 + rang:02d} {20 + rang:02d} {30 + rang:02d}',
            },
        )
        # Prise de fonction dans le poste actuel : postérieure à l'entrée.
        date_debut = max(date_entree, date(2023 + (rang % 3), 9, 1))
        AffectationRH.objects.update_or_create(
            agent=agent, fonction=fonction, date_debut=date_debut,
            defaults={'date_fin': None},
        )
        return agent

    # ── Peuplement ───────────────────────────────────────────────────────
    def _peupler(self):
        ensure_role_groups()
        bilan = {}
        idx = 0
        profils = []  # (user, prenom, nom, fonction)

        # 1) Directions
        directions = {}
        for ordre, (code, libelle, desc) in enumerate(DIRECTIONS, start=1):
            user, profil = self._utilisateur(idx, f'dir-{code}', 'DIRECTION', f'Directeur — {libelle}')
            idx += 1
            profils.append((user, *profil))
            obj, _ = Direction.objects.update_or_create(code=code, defaults={
                'libelle': libelle, 'description': f'{MARQUE} {desc}',
                'ordre': ordre, 'actif': True, 'responsable': user,
                'email': f'{code.lower()}@demo.injs.ci',
                'localisation': 'Bâtiment administratif INJS Marcory',
            })
            directions[code] = (obj, user)
        bilan['directions'] = len(directions)

        # 2) Départements
        departements = {}
        for ordre, (dir_code, code, libelle) in enumerate(DEPARTEMENTS, start=1):
            user, profil = self._utilisateur(idx, f'dep-{code}', 'INJS_ADMIN', f'Chef de département — {libelle}')
            idx += 1
            profils.append((user, *profil))
            obj, _ = Departement.objects.update_or_create(code=code, defaults={
                'libelle': libelle, 'description': f'{MARQUE} Département du processus LMD INJS.',
                'direction': directions[dir_code][0], 'ordre': ordre, 'actif': True,
                'responsable': user, 'email': f'{code.lower()}@demo.injs.ci',
                'localisation': 'Bâtiment administratif INJS Marcory',
            })
            departements[code] = (obj, user)
        bilan['departements'] = len(departements)

        # 3) Services
        services = {}
        for dep_code, code, nom, role in SERVICES:
            user, profil = self._utilisateur(idx, f'svc-{code.removeprefix("SRV-")}', role, f'Chef de service — {nom}')
            idx += 1
            profils.append((user, *profil))
            obj, _ = Service.objects.update_or_create(nom=nom, defaults={
                'code': code, 'type_unite': Service.TypeUnite.SERVICE,
                'description': f'{MARQUE} Service du processus LMD INJS.',
                'departement': departements[dep_code][0], 'actif': True,
                'responsable': user, 'email': f'{code.lower()}@demo.injs.ci',
                'localisation': 'Bâtiment administratif INJS Marcory',
            })
            services[code] = (obj, user)
        bilan['services'] = len(services)

        # 4) Secrétariats (responsable chef + 1 agent chacun)
        secretariats = {}
        secretariats_profils = {}
        for numero, nom, dep_code in SECRETARIATS:
            chef, profil = self._utilisateur(idx, f'chef-{numero}', 'CHEF_SECRETARIAT', f'Chef de secrétariat — {nom}')
            idx += 1
            profils.append((chef, *profil))
            sec, _ = Secretariat.objects.update_or_create(nom=nom, defaults={
                'numero': numero, 'description': f'{MARQUE} Secrétariat du processus LMD INJS.',
                'responsable': chef, 'departement': departements[dep_code][0],
                'email': f'{numero.lower().replace("-", "")}@demo.injs.ci',
                'localisation': 'Bâtiment administratif INJS Marcory', 'actif': True,
            })
            secretariats[numero] = sec
            service_secretariat = {'SEC-01': 'SRV-SCOL-EPS', 'SEC-02': 'SRV-SCOL-EP', 'SEC-03': 'SRV-CONC'}[numero]
            secretariats_profils[numero] = (chef, profil, service_secretariat)
            membre, profil2 = self._utilisateur(idx, f'agent-{numero}', 'SECRETARIAT', f'Agent de secrétariat — {nom}')
            secretariats_profils[numero] = (chef, profil, membre, profil2, service_secretariat)
            idx += 1
            profils.append((membre, *profil2))
            if membre.secretariat_id != sec.id:
                membre.secretariat = sec
                membre.save(update_fields=['secretariat'])
        bilan['secretariats'] = len(secretariats)

        # 5) Personnels : fonction COHÉRENTE avec l'unité de chaque profil.
        # (Corrige l'incohérence initiale : 29 agents « Archiviste » par
        # défaut, 45 fonctionnaires entrés le même jour.)
        AffectationRH.objects.filter(
            agent__matricule__startswith='PERS-DEMO-').delete()

        def fonction_de(service, intitule):
            fonction, _ = Fonction.objects.get_or_create(
                intitule=intitule, service=service,
                defaults={'grade': 'Personnel administratif et technique (démo)', 'actif': True},
            )
            return fonction

        def premier_service(departement):
            for dep_code, code, _nom, _role in SERVICES:
                if dep_code == departement.code:
                    return services[code][0]
            return None

        # user_id -> (service, intitulé de fonction)
        postes = {}
        for code, (direction, user) in directions.items():
            for dep_code, dep in departements.items():
                if dep[0].direction_id == direction.id:
                    svc = premier_service(dep[0])
                    if svc is not None:
                        postes[user.id] = (svc, 'Directeur / Directrice')
                        break
        for code, (departement, user) in departements.items():
            svc = premier_service(departement)
            if svc is None:
                # Département sans service propre (ex. contrôle interne) :
                # rattachement au premier service de sa direction.
                for autre in departements.values():
                    if autre[0].direction_id == departement.direction_id:
                        svc = premier_service(autre[0])
                        if svc is not None:
                            break
            if svc is not None:
                postes[user.id] = (svc, 'Chef de département')
        for dep_code, code, nom, role in SERVICES:
            svc, user = services[code]
            intitule = 'Archiviste' if code == 'SRV-ARCH' else 'Chef de service'
            postes[user.id] = (svc, intitule)
        for numero, (chef, _p1, membre, _p2, code_service) in secretariats_profils.items():
            svc = services[code_service][0]
            postes[chef.id] = (svc, 'Chef de secrétariat')
            postes[membre.id] = (svc, 'Agent de secrétariat')

        for rang, (user, prenom, nom, fonction_libelle) in enumerate(profils):
            cible = postes.get(user.id)
            if cible is None:
                continue
            service, intitule = cible
            self._agent(user, prenom, nom.replace(' (démo)', ''),
                        fonction_de(service, intitule), rang)
        bilan['personnels'] = Agent.objects.filter(matricule__startswith='PERS-DEMO-').count()
        bilan['fonctions'] = Fonction.objects.filter(actif=True).count()

        # Indisponibilités et documents RH d'exemple (onglets dédiés du hub)
        agents_demo = list(Agent.objects.filter(
            matricule__startswith='PERS-DEMO-').order_by('id'))
        indispos = [
            ('CONGE', 'Congé annuel 2026', date(2026, 10, 26), date(2026, 11, 13)),
            ('MISSION', 'Supervision des stages pratiques', date(2026, 11, 2), date(2026, 11, 6)),
            ('FORMATION', 'Perfectionnement gestion documentaire', date(2026, 11, 3), date(2026, 11, 7)),
            ('CONGE', 'Congé annuel 2026 (2e tranche)', date(2026, 12, 21), date(2027, 1, 4)),
            ('MISSION', 'Inventaire des infrastructures régionales', date(2027, 1, 11), date(2027, 1, 15)),
            ('FORMATION', 'Gestion des archives numériques', date(2026, 9, 14), date(2026, 9, 18)),
        ]
        for rang, agent in enumerate(agents_demo[:18]):
            type_i, motif, debut, fin = indispos[rang % len(indispos)]
            DisponibiliteAgent.objects.update_or_create(
                agent=agent, date_debut=debut,
                defaults={'type_indispo': type_i, 'motif': f'[Démo fictive] {motif}',
                          'date_fin': fin},
            )
        docs_rh = [
            ('ATTESTATION', 'Attestation de prise de service'),
            ('AVIS', 'Avis de situation administrative'),
            ('EVALUATION', 'Fiche d’évaluation annuelle 2025-2026'),
            ('CONTRAT', 'Copie du contrat / arrêté de nomination'),
        ]
        for rang, agent in enumerate(agents_demo[:20]):
            type_d, intitule = docs_rh[rang % len(docs_rh)]
            DocumentRH.objects.update_or_create(
                agent=agent, intitule=f'[Démo fictive] {intitule}',
                defaults={'type_document': type_d},
            )
        bilan['indisponibilites'] = DisponibiliteAgent.objects.filter(
            motif__startswith='[Démo fictive]').count()
        bilan['documents_rh'] = DocumentRH.objects.filter(
            intitule__startswith='[Démo fictive]').count()

        # Formateurs fictifs (pour les archives pédagogiques)
        formateurs = []
        for i, specialite in enumerate(['Sciences de la Vie et de la Santé', 'Activités Physiques et Sportives']):
            user, profil = self._utilisateur(idx, f'ens-{i+1}', 'FORMATEUR', f'Enseignant (démo) — {specialite}')
            idx += 1
            profils.append((user, *profil))
            # profile_sync crée déjà un Formateur lié au compte FORMATEUR :
            # on le réutilise (contrainte OneToOne sur user).
            formateur = Formateur.objects.filter(user=user).first()
            if formateur is None:
                formateur, _ = Formateur.objects.update_or_create(
                    numerobadge=f'DEMO-ENS-{i+1:02d}',
                    defaults={'user': user},
                )
            formateur.nom = profil[1]
            formateur.prenom = profil[0]
            formateur.email = user.email
            formateur.specialite = specialite
            formateur.statut_enseignant = 'Titulaire (démo)'
            formateur.save()
            formateur.secretariats.set([secretariats['SEC-01']])
            formateurs.append(formateur)
        bilan['formateurs_demo'] = len(formateurs)

        # 6) Courriers (avec fichier fictif pour la moitié) et archives admin.
        base = date(2026, 10, 5)
        acteur = directions['DG'][1]
        nb_courriers = 0
        for rang, (sens, objet, exp, dest, statut) in enumerate(COURRIERS, start=1):
            reference = f'DEMO-2026/{"CE" if sens == "ENTRANT" else "CS"}-{rang:03d}'
            courrier, _ = Courrier.objects.update_or_create(reference=reference, defaults={
                'sens': sens, 'objet': f'{MARQUE} {objet}', 'expediteur': exp,
                'destinataire': dest, 'date_courrier': base + timedelta(days=rang * 3),
                'statut': statut, 'cree_par': acteur,
            })
            if rang % 2 == 0 and not courrier.fichier:
                courrier.fichier.save(f'{reference.replace("/", "_")}.pdf',
                                      ContentFile(_pdf_fictif(objet)), save=True)
            nb_courriers += 1
        bilan['courriers'] = nb_courriers

        # 7) Documents officiels + versions + fichiers fictifs
        for type_doc, reference, titre, statut in DOCUMENTS:
            doc, _ = DocumentOfficiel.objects.update_or_create(titre=f'{MARQUE} {titre}', defaults={
                'type_document': type_doc, 'reference': reference, 'statut': statut,
                'contenu': f'{MARQUE} Contenu fictif généré pour la démonstration du processus INJS-LMD.',
                'cree_par': acteur,
                'signe_par': directions['DG'][1] if statut in ('SIGNE', 'PUBLIE', 'ARCHIVE') else None,
                'date_signature': timezone.now() if statut in ('SIGNE', 'PUBLIE', 'ARCHIVE') else None,
            })
            if not doc.document_pdf:
                doc.document_pdf.save(f'{reference.replace("/", "_")}.pdf',
                                      ContentFile(_pdf_fictif(titre)), save=True)
            VersionDocument.objects.update_or_create(
                document=doc, numero_version=1,
                defaults={'contenu': doc.contenu, 'cree_par': acteur},
            )
        bilan['documents'] = len(DOCUMENTS)

        # 8) Réunions & missions
        participants_reunion = [directions[c][1] for c in ('DG', 'DEF', 'DENSEPS', 'DENSEP')]
        for type_r, titre, date_r, statut in REUNIONS:
            reunion, _ = ReunionCommission.objects.update_or_create(titre=f'{MARQUE} {titre}', defaults={
                'type_reunion': type_r, 'date_reunion': date_r,
                'heure_debut': time(9, 0), 'heure_fin': time(11, 0),
                'lieu': 'Salle de conseil — INJS Marcory',
                'ordre_du_jour': f'{type_r} : ordre du jour de démonstration du processus LMD.',
                'statut': statut,
                'pv_contenu': f'{MARQUE} Procès-verbal fictif de démonstration.' if statut == 'PV_EMIS' else '',
            })
            reunion.participants.set(participants_reunion)
        for objet, lieu, debut, fin, statut in MISSIONS:
            Mission.objects.update_or_create(objet=f'{MARQUE} {objet}', defaults={
                'agent': services['SRV-INFRA'][1] if 'infrastructure' in objet.lower() or 'équipement' in objet.lower() else acteur,
                'lieu': lieu, 'date_debut': debut, 'date_fin': fin,
                'statut': statut, 'budget': Decimal('0'),
                'valide_par': acteur if statut in ('VALIDEE', 'EN_COURS', 'TERMINEE') else None,
            })
        bilan['reunions'] = len(REUNIONS)
        bilan['missions'] = len(MISSIONS)

        # 9) Archives pédagogiques : module archivé + notes + cahier d'appel
        bilan.update(self._archives_pedagogiques(secretariats['SEC-01'], formateurs, services['SRV-ARCH'][1]))
        bilan['utilisateurs_demo'] = User.objects.filter(username__startswith='demo.').count()
        return bilan

    def _archives_pedagogiques(self, secretariat, formateurs, archiviste):
        """Crée la chaîne minimale d'un module archivé consultable.

        Étudiants fictifs DEMO-ARCH, séances passées, pointages et notes
        validées/verrouillées : les écrans « Listes de notes archivées » et
        « Cahiers d'appel archivés » affichent alors de vraies données.
        """
        formation, _ = Formation.objects.update_or_create(
            formation='[Démo archives] Éducation et Motricité — Licence (2025-2026)',
            defaults={},
        )
        participants = []
        for i, (nom, prenom) in enumerate(ETUDIANTS_DEMO, start=1):
            p, _ = Participant.objects.update_or_create(
                matricule=f'DEMO-ARCH-2025-{i:03d}',
                defaults={'nom': nom, 'prenom': prenom,
                          'email': f'etudiant.demo{i}@demo.injs.ci',
                          'sexe': Participant.Sexe.FEMININ if i % 2 else Participant.Sexe.MASCULIN},
            )
            participants.append(p)

        modules_specs = [
            ('Sciences de la Vie et de la Santé — S1 (archivé)', formateurs[0]),
            ('Initiation aux fondamentaux du Football — S1 (archivé)', formateurs[1]),
        ]
        nb_notes = nb_pointages = 0
        for intitule, formateur in modules_specs:
            module, _ = Module.objects.update_or_create(
                formation=formation, intitule=intitule,
                defaults={
                    'cycle': formation.formation, 'statut': Module.Statut.TERMINEE,
                    'secretariat': secretariat, 'formateur': formateur,
                    'date_debut': date(2025, 9, 15), 'date_fin': date(2026, 1, 30),
                    'duree_prevue_heures': Decimal('30'),
                    'archived': True, 'archived_at': timezone.now(),
                    'archived_by': archiviste,
                },
            )
            ModuleFormateur.objects.get_or_create(module=module, formateur=formateur)
            for p in participants:
                ModuleParticipant.objects.get_or_create(module=module, participant=p)
            # Séances du cahier d'appel (6 séances passées)
            sessions = []
            for s in range(6):
                session, _ = SessionModule.objects.update_or_create(
                    module=module, date_journee=date(2025, 9, 22) + timedelta(days=7 * s), numero=1,
                    defaults={'intitule': f'Séance {s + 1} (archivée)',
                              'heure_debut_prevue': time(8, 0), 'heure_fin_prevue': time(10, 0),
                              'terminee_le': timezone.now()},
                )
                sessions.append(session)
                for j, p in enumerate(participants):
                    present = (j + s) % 6 != 0  # motif d'absence déterministe
                    entree = timezone.make_aware(
                        timezone.datetime.combine(session.date_journee, time(8, 5)))
                    Pointage.objects.update_or_create(
                        participant=p, session=session,
                        defaults={
                            'statut': Pointage.Statut.TERMINE if present else Pointage.Statut.ABSENT_NON_BADGE,
                            'statut_assiduite': (
                                Pointage.StatutAssiduite.PRESENT if present
                                else Pointage.StatutAssiduite.ABSENT),
                            'date_journee': session.date_journee,
                            'timestamp_entree': entree,
                            'timestamp_sortie': (
                                entree + timedelta(hours=2) if present else None),
                            'duree_presence_minutes': Decimal('120') if present else None,
                            'formateur': formateur,
                        },
                    )
                    nb_pointages += 1
            # Liste de notes archivée : 2 colonnes, notes validées verrouillées
            colonnes = []
            for ordre, libelle in enumerate(['Contrôle continu', 'Examen'], start=1):
                colonne, _ = NoteModuleColonne.objects.update_or_create(
                    module=module, libelle=libelle, defaults={'ordre': ordre, 'note_max': Decimal('20')},
                )
                colonnes.append(colonne)
            for j, p in enumerate(participants):
                for k, colonne in enumerate(colonnes):
                    note = Decimal('8') + Decimal(((j * 3 + k * 2) % 11)) + Decimal('0.5') * (k)
                    NoteModule.objects.update_or_create(
                        colonne=colonne, participant=p,
                        defaults={'note': note, 'saisie_par': formateur.user,
                                  'statut_validation': NoteModule.StatutValidation.VALIDEE,
                                  'verrouillee': True, 'validation_par': archiviste,
                                  'validation_le': timezone.now()},
                    )
                    nb_notes += 1
        return {'modules_archives': len(modules_specs), 'etudiants_demo': len(participants),
                'notes_archivees': nb_notes, 'pointages_archives': nb_pointages}
