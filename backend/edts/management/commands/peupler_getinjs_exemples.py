"""Jeu de données d'exemple complet pour le module GET INJS APP.

Objectif : que l'accueil du module et ses écrans montrent des données
réelles et variées — emplois du temps générés et publiés sur les
formations officielles INJS, campagne de génération menée à son terme,
salles géolocalisées, cohorte d'inscrits importée depuis un fichier
externe (situation 2 du prompt maître).

Tout passe par les voies officielles du module (API de génération et de
publication, services de campagnes, API d'import, service de
réconciliation des registres de séances) : aucune ligne n'est fabriquée
à la main dans les tables de planification.

Idempotence : relancer la commande ne duplique rien — les EDT déjà
publiés sont reconnus, la campagne porte un libellé unique, les
géolocalisations sont créées une seule fois par salle, l'import est
clé sur (année, matricule).

Exemple :
    python manage.py peupler_getinjs_exemples
    python manage.py peupler_getinjs_exemples --sans-import
"""

import io

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.test import override_settings
from rest_framework.test import APIClient

from edts.models import EmploiDuTemps
from edts.models_interop import SalleGeolocalisation, SeanceRegistre
from formations.models import RefFormation, RefSalle
from formations.referentiel_injs_l6 import formations_injs
from scolarite.models import AnneeAcademique, Niveau, Semestre

LIBELLE_CAMPAGNE = 'Campagne d’exemple GET INJS APP — Rentrée 2026-2027'
# Centre de l'INJS de Marcory (Abidjan) : les géolocalisations d'exemple
# sont réparties de façon déterministe autour de ce point.
CENTRE_INJS = (5.295900, -3.986100)

TYPES_PAR_MOT_CLE = [
    ('AMPHI', SalleGeolocalisation.TypeEspace.AMPHITHEATRE, 120),
    ('GYM', SalleGeolocalisation.TypeEspace.GYMNASE, 150),
    ('TERRAIN', SalleGeolocalisation.TypeEspace.TERRAIN, 200),
    ('PISCINE', SalleGeolocalisation.TypeEspace.PISCINE, 150),
    ('DOJO', SalleGeolocalisation.TypeEspace.DOJO, 100),
    ('LABO', SalleGeolocalisation.TypeEspace.LABORATOIRE, 80),
    ('INFORMATIQUE', SalleGeolocalisation.TypeEspace.LABORATOIRE, 80),
]


class Command(BaseCommand):
    help = (
        'Peuple le module GET INJS APP avec un jeu d’exemple complet et '
        'idempotent (EDT générés/publiés, campagne, géolocalisations, '
        'cohorte importée).'
    )

    def add_arguments(self, parser):
        parser.add_argument('--sans-import', action='store_true',
                            help='Ne pas importer la cohorte d’exemple (70 lignes).')
        parser.add_argument('--sans-campagne', action='store_true',
                            help='Ne pas créer la campagne d’exemple.')
        parser.add_argument('--avec-l3', action='store_true',
                            help='Ajouter les L3/S5 des licences (générations '
                                 'nettement plus longues sur ce moteur).')

    # ── Utilitaires ────────────────────────────────────────────────────────
    def _client(self):
        admin = (
            get_user_model().objects.filter(username='admin').first()
            or get_user_model().objects.filter(is_superuser=True).first()
        )
        client = APIClient()
        client.force_authenticate(admin)
        return client, admin

    def _semestre(self, niveau_code, numero):
        niveau = Niveau.objects.filter(code=niveau_code).first()
        if niveau is None:
            return None, None
        return niveau, Semestre.objects.filter(niveau=niveau, numero=numero).first()

    # ── Étape 1 : emplois du temps générés, publiés, réconciliés ───────────
    def _generer_edts(self, client, annee, avec_l3=False):
        bilan = {'publies': 0, 'deja_publies': 0, 'non_publies': 0, 'impossibles': 0}
        # Premier semestre de chaque cycle par défaut ; les L3/S5 sont
        # opt-in (--avec-l3) car leurs maquettes chargent le moteur
        # bien plus longtemps (constat mesuré, voir Conception).
        cibles = [('L1', 1)] + ([('L3', 5)] if avec_l3 else [])
        cibles_master = [('M1', 7)]
        for formation in formations_injs().order_by('intitule'):
            perimetres = cibles_master if 'MASTER' in formation.intitule.upper() else cibles
            for niveau_code, numero in perimetres:
                niveau, semestre = self._semestre(niveau_code, numero)
                if niveau is None or semestre is None:
                    continue
                edt, _ = EmploiDuTemps.objects.get_or_create(
                    annee_academique=annee,
                    population_type='FORMATION',
                    population_id=formation.id,
                    version=1,
                    defaults={
                        'titre': f'EDT {formation.intitule} — {niveau_code} S{numero} (exemple GET)',
                        'statut': 'BROUILLON',
                    },
                )
                if edt.statut == 'PUBLIE':
                    client.post(f'/api/edts/interop/emplois/{edt.id}/reconcilier/')
                    bilan['deja_publies'] += 1
                    continue
                r = client.post('/api/edts/lmd/generate/', {
                    'ref_formation_id': formation.id,
                    'niveau_id': niveau.id,
                    'semestre_id': semestre.id,
                    'persister': 'true',
                    'remplacer': 'true',
                    'emploi_du_temps_id': edt.id,
                    'semaines': [1],
                }, format='json')
                if r.status_code not in (200, 201) or not r.data.get('persiste'):
                    bilan['impossibles'] += 1
                    self.stdout.write(
                        f'  · {formation.intitule} {niveau_code} : génération '
                        f'impossible ({r.status_code})'
                    )
                    continue
                ok = True
                for action in ('soumettre', 'valider', 'publier'):
                    r = client.post(f'/api/edts/emplois/{edt.id}/{action}/')
                    if r.status_code != 200:
                        ok = False
                        self.stdout.write(
                            f'  · {formation.intitule} {niveau_code} : {action} '
                            f'refusée ({r.status_code})'
                        )
                        break
                client.post(f'/api/edts/interop/emplois/{edt.id}/reconcilier/')
                bilan['publies' if ok else 'non_publies'] += 1
        return bilan

    # ── Étape 2 : campagne d'exemple menée jusqu'à « Prêt à générer » ──────
    def _campagne_exemple(self, admin, annee):
        from edts.models import CampagneGeneration
        from edts.moteur import campagnes as camp

        if CampagneGeneration.objects.filter(
            annee_academique=annee, libelle=LIBELLE_CAMPAGNE,
        ).exists():
            return 'déjà présente'
        em = formations_injs().filter(intitule__icontains='MOTRICIT').first()
        campagne = camp.creer_campagne(
            annee_academique_id=annee.id,
            libelle=LIBELLE_CAMPAGNE,
            user=admin,
            perimetre={'formations': [em.id] if em else []},
            parametres={'exemple': True},
        )
        try:
            camp.valider_donnees(campagne.id, user=admin)
            camp.marquer_pret(campagne.id, user=admin)
        except Exception as exc:  # bilan honnête, jamais un crash muet
            campagne.refresh_from_db()
            return f'arrêtée à {campagne.statut} ({type(exc).__name__})'
        campagne.refresh_from_db()
        # Laissée « Prêt à générer » : l'exécution se lance depuis l'écran
        # Campagnes. Le périmètre « formations » borne désormais la génération
        # à cette seule formation (correctif moteur de ce lot) ; l'exécuter ici
        # régénérerait les EDT déjà publiés de l'exemple.
        return f'créée, validée et prête (statut {campagne.statut}) — exécution depuis l’écran Campagnes'

    # ── Étape 3 : géolocalisations d'exemple ───────────────────────────────
    def _geolocalisations(self, admin):
        creees = 0
        salles = list(RefSalle.objects.order_by('nom'))
        choisies = []
        for salle in salles:
            nom = salle.nom.upper()
            for mot, type_espace, rayon in TYPES_PAR_MOT_CLE:
                if mot in nom:
                    choisies.append((salle, type_espace, rayon))
                    break
        for salle in salles:
            if len(choisies) >= 12:
                break
            if all(s.id != salle.id for s, _, _ in choisies):
                choisies.append((salle, SalleGeolocalisation.TypeEspace.SALLE_COURS, 60))
        for index, (salle, type_espace, rayon) in enumerate(choisies[:12]):
            _, cree = SalleGeolocalisation.objects.get_or_create(
                salle=salle,
                defaults={
                    'latitude': round(CENTRE_INJS[0] + (index % 4) * 0.0004, 7),
                    'longitude': round(CENTRE_INJS[1] + (index % 3) * 0.0004, 7),
                    'rayon_tolerance_m': rayon,
                    'zone_libelle': 'Campus INJS — Marcory',
                    'type_espace': type_espace,
                    'statut_configuration': SalleGeolocalisation.StatutConfiguration.CONFIGUREE,
                    'maj_par': admin,
                },
            )
            creees += int(cree)
        return creees

    # ── Étape 4 : cohorte importée d'exemple (70 lignes XLSX) ──────────────
    def _import_exemple(self, client, annee):
        import openpyxl

        em = formations_injs().filter(intitule__icontains='MOTRICIT').filter(
            intitule__icontains='LICENCE',
        ).first()
        if em is None:
            return 'formation EM introuvable, import ignoré'
        classeur = openpyxl.Workbook()
        feuille = classeur.active
        feuille.append([
            'Matricule', 'Nom', 'Prénoms', 'Sexe', 'Date de naissance',
            'Formation', 'Niveau', 'Groupe', 'Vague',
        ])
        for i in range(1, 71):
            feuille.append([
                f'GETEX26-{i:03d}',
                f'Exemple{i:02d}',
                'Étudiant',
                'F' if i % 2 else 'M',
                '12/03/2007',
                em.intitule,
                'Licence 2',
                'L2-EM-GETEX',
                'Vague 1',
            ])
        tampon = io.BytesIO()
        classeur.save(tampon)
        tampon.seek(0)
        tampon.name = 'inscrits_exemple_getinjs.xlsx'
        r = client.post(
            '/api/edts/lmd/import/inscrits/',
            {'fichier': tampon, 'annee_academique_id': annee.id},
            format='multipart',
        )
        if r.status_code not in (200, 201):
            return f'import refusé ({r.status_code})'
        return (
            f"{r.data.get('lignes_valides', '?')} lignes valides, "
            f"{r.data.get('creees', 0)} créées, "
            f"{r.data.get('mises_a_jour', 0)} mises à jour"
        )

    # ── Point d'entrée ─────────────────────────────────────────────────────
    def handle(self, *args, **options):
        annee = (
            AnneeAcademique.courante_ou_none()
            or AnneeAcademique.objects.order_by('-libelle').first()
        )
        if annee is None:
            self.stdout.write(self.style.ERROR('Aucune année académique.'))
            return
        with override_settings(ALLOWED_HOSTS=['*']):
            client, admin = self._client()
            self.stdout.write(f'Année : {annee.libelle} — génération des EDT…')
            bilan = self._generer_edts(client, annee, avec_l3=options['avec_l3'])
            self.stdout.write(f'  EDT : {bilan}')
            if not options['sans_campagne']:
                self.stdout.write(f"  Campagne : {self._campagne_exemple(admin, annee)}")
            creees = self._geolocalisations(admin)
            self.stdout.write(f'  Géolocalisations créées : {creees}')
            if not options['sans_import']:
                self.stdout.write(f"  Import : {self._import_exemple(client, annee)}")

        from django.db.models import Count

        from edts.models import AffectationCreneau, CampagneGeneration
        self.stdout.write(self.style.SUCCESS(
            'Bilan GET INJS APP : '
            f"{EmploiDuTemps.objects.count()} EDT "
            f"({EmploiDuTemps.objects.filter(statut='PUBLIE').count()} publiés), "
            f'{AffectationCreneau.objects.filter(actif=True).count()} séances placées, '
            f"{SeanceRegistre.objects.filter(statut__in=['PUBLIEE', 'MODIFIEE']).count()} "
            'séances officielles prêtes pour Présences, '
            f'{CampagneGeneration.objects.count()} campagne(s), '
            f'{SalleGeolocalisation.objects.count()} salle(s) géolocalisée(s).'
        ))
