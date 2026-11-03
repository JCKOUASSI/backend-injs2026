"""Seed EDT/assiduité : chaîne LMD, calendrier, idempotence et purge sûre."""
from datetime import datetime, timedelta, timezone as dt_timezone
from unittest.mock import patch

from django.core.management import call_command
from django.urls import reverse
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from authentication.models import User
from edts.models import AffectationCreneau, ConflitCreneau, CreneauTemplate, EmploiDuTemps
from edts.management.commands.seed_edt_demo import JOURS, SOURCE
from formations.models import Formateur, Participant, RefFormation, RefSalle, RefSite
from presences.models import Pointage
from presences.seances_edt_services import est_seance_du_jour, horodatages
from scolarite.models import (
    AffectationGroupe, AffectationPedagogique, AnneeAcademique, DossierEtudiant,
    ECUE, Groupe, InscriptionAdministrative, Maquette, Niveau, Semestre, UE,
)

NOW = datetime(2026, 11, 3, 12, tzinfo=dt_timezone.utc)
COMMAND = 'edts.management.commands.seed_edt_demo.timezone.now'


class SeedEdtDemoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(
            username='edt-seed-admin', password='x', role='ADMIN',
            is_staff=True, is_superuser=True,
        )
        cls.annee = AnneeAcademique.objects.create(
            libelle='2026-2027', date_debut='2026-10-01', date_fin='2027-07-31', courante=True,
        )
        cls.niveau = Niveau.objects.create(code='L1', libelle='Licence 1', ordre=1)
        cls.semestre = Semestre.objects.create(niveau=cls.niveau, numero=1)
        cls.groupes, cls.salles, cls.affectations = [], [], []
        site = RefSite.objects.create(nom='INJS Marcory')
        for rang in range(6):
            formation = RefFormation.objects.create(intitule=f'Formation {rang} — LICENCE')
            salle = RefSalle.objects.create(site=site, nom=f'Salle {rang}', capacite=40, type_lieu='COURS')
            groupe = Groupe.objects.create(
                annee_academique=cls.annee, ref_formation=formation,
                niveau=cls.niveau, nom='L1-G1',
            )
            maquette = Maquette.objects.create(
                annee_academique=cls.annee, ref_formation=formation, niveau=cls.niveau,
            )
            ue = UE.objects.create(maquette=maquette, semestre=cls.semestre, code=f'UE{rang}', credits=15)
            enseignant = Formateur.objects.create(nom=f'Enseignant{rang}', prenom='Exemple')
            for index in range(5):
                ecue = ECUE.objects.create(ue=ue, code=f'EC{rang}-{index}', intitule='Coursfondamental', credits=3)
                cls.affectations.append(AffectationPedagogique.objects.create(
                    annee_academique=cls.annee, ref_formation=formation,
                    niveau=cls.niveau, semestre=cls.semestre, ue=ue, ecue=ecue,
                    groupe=groupe, enseignant=enseignant, volume_horaire=15,
                    statut='VALIDEE', observations='[Exemple] Affectation test.',
                ))
            maquette.statut = 'ACTIVE'
            maquette.save(update_fields=['statut'])
            for index in range(6):
                participant = Participant.objects.create(
                    matricule=f'ETU-{rang}-{index}', nom='Etudiant', prenom=f'{rang}-{index}',
                )
                dossier = DossierEtudiant.objects.create(participant=participant)
                inscription = InscriptionAdministrative.objects.create(
                    etudiant=dossier, annee_academique=cls.annee, ref_formation=formation,
                    niveau=cls.niveau, statut='VALIDEE',
                )
                AffectationGroupe.objects.create(
                    inscription=inscription, groupe=groupe, date_debut=cls.annee.date_debut,
                )
            cls.groupes.append(groupe)
            cls.salles.append(salle)

    def seed(self, now=NOW, *args):
        with patch(COMMAND, return_value=now):
            call_command('seed_edt_demo', *args, verbosity=0)

    def test_trente_creneaux_chaine_lmd_et_pointages_passes_uniquement(self):
        self.seed()
        self.assertEqual(EmploiDuTemps.objects.count(), 6)
        self.assertEqual(AffectationCreneau.objects.count(), 30)
        self.assertEqual(ConflitCreneau.objects.filter(actif=True).count(), 0)
        self.assertTrue(all('[Exemple]' in e.titre for e in EmploiDuTemps.objects.all()))
        for seance in AffectationCreneau.objects.select_related('affectation_pedagogique'):
            ap = seance.affectation_pedagogique
            self.assertIn(ap, self.affectations)
            self.assertEqual(seance.groupe_id, ap.groupe_id)
            self.assertEqual(seance.formateur_id, ap.enseignant_id)
            self.assertEqual(seance.formation_id, ap.ref_formation_id)
            self.assertEqual(seance.semaine_debut, 1)
            self.assertEqual(seance.semaine_fin, 5)
            self.assertTrue(seance.intitule.startswith('[Exemple]'))
        points = Pointage.objects.select_related('seance_edt__creneau_template')
        self.assertGreater(points.count(), 500)
        attendus = {
            (ag.groupe_id, ag.inscription.etudiant.participant_id)
            for ag in AffectationGroupe.objects.filter(active=True)
        }
        for point in points:
            seance = point.seance_edt
            self.assertEqual(point.device_id, SOURCE)
            self.assertIsNone(point.session_id)
            self.assertEqual(point.annee_academique_id, self.annee.pk)
            self.assertEqual(point.groupe_lmd_id, seance.groupe_id)
            self.assertEqual(point.ecue_lmd_id, seance.affectation_pedagogique.ecue_id)
            self.assertIn((seance.groupe_id, point.participant_id), attendus)
            self.assertTrue(est_seance_du_jour(seance, point.date_journee))
            debut, fin = horodatages(seance, point.date_journee)
            self.assertLess(point.timestamp_sortie, NOW)
            self.assertLessEqual(point.timestamp_sortie, fin)
            self.assertGreaterEqual(point.timestamp_entree, debut)
            self.assertGreaterEqual(point.duree_presence_minutes, 0)
            self.assertIn('[Exemple]', str(point))
        self.assertEqual(points.filter(timestamp_entree__gt=NOW).count(), 0)
        self.assertEqual(points.values('seance_edt', 'date_journee', 'participant').distinct().count(), points.count())
        self.assertEqual(set(points.values_list('statut_assiduite', flat=True)), {
            'PRESENT', 'RETARD', 'ABSENT', 'ABSENCE_JUSTIFIEE', 'EXCUSE',
        })

    def test_seances_aujourdhui_et_kpi_reellement_mesures(self):
        self.seed()
        client = APIClient()
        client.force_authenticate(self.admin)
        with patch(COMMAND, return_value=NOW):
            res = client.get('/api/presences/seances-edt/supervision/', {'date': '2026-11-03'})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.data['seances']), 6)
        self.assertTrue(all(s['est_exemple'] for s in res.data['seances']))
        self.assertGreater(res.data['resume']['participants_presents'], 0)
        self.assertTrue(all(s['presences']['source_exemple'] > 0 or s['statut'] == 'A_VENIR'
                            for s in res.data['seances']))
        self.assertGreater(Pointage.objects.filter(date_journee=NOW.date()).count(), 0)
        res = client.get('/api/dashboard/overview/')
        self.assertIsNotNone(res.data['kpis']['taux_presence'])
        res = client.get('/api/dashboard/presences/')
        self.assertIsNotNone(res.data['kpis']['taux_assiduite_moyen'])
        from config.admin_dashboard import _build_admin_charts
        charts = _build_admin_charts()
        self.assertIsNotNone(charts['pointages_mensuels'])
        self.assertIsNotNone(charts['sessions_mensuelles'])
        self.assertNotEqual(charts['taux_presence'][-1]['display'], '—')
        self.assertGreater(charts['taux_presence'][-2]['presents'], 0)

    def test_idempotence_et_corrections_manuelles_conservees(self):
        self.seed()
        before = list(Pointage.objects.order_by('pk').values_list(
            'pk', 'seance_edt', 'date_journee', 'participant', 'statut_assiduite', 'timestamp_entree',
        ))
        point = Pointage.objects.first()
        point.statut_assiduite = 'EXCUSE'
        point.device_id = 'EMARGEMENT_MANUEL'
        point.save(update_fields=['statut_assiduite', 'device_id'])
        ids = set(AffectationCreneau.objects.values_list('pk', flat=True))
        self.seed()
        after = list(Pointage.objects.order_by('pk').exclude(pk=point.pk).values_list(
            'pk', 'seance_edt', 'date_journee', 'participant', 'statut_assiduite', 'timestamp_entree',
        ))
        self.assertEqual(after, [row for row in before if row[0] != point.pk])
        point.refresh_from_db()
        self.assertEqual(point.statut_assiduite, 'EXCUSE')
        self.assertEqual(point.device_id, 'EMARGEMENT_MANUEL')
        self.assertEqual(set(AffectationCreneau.objects.values_list('pk', flat=True)), ids)

    def test_reexecution_le_lendemain_complete_sans_doublons(self):
        self.seed()
        before = Pointage.objects.count()
        self.seed(NOW + timedelta(days=1))
        self.assertGreater(Pointage.objects.count(), before)
        self.assertEqual(AffectationCreneau.objects.count(), 30)
        self.assertEqual(Pointage.objects.values('seance_edt', 'date_journee', 'participant').distinct().count(),
                         Pointage.objects.count())
        self.assertTrue(Pointage.objects.filter(date_journee='2026-11-04').exists())

    def test_dry_run_ne_cree_aucune_ligne(self):
        self.seed(NOW, '--dry-run')
        self.assertEqual(EmploiDuTemps.objects.count(), 0)
        self.assertEqual(AffectationCreneau.objects.count(), 0)
        self.assertEqual(Pointage.objects.count(), 0)
        self.assertEqual(CreneauTemplate.objects.count(), 0)

    def test_purge_conserve_le_referentiel_et_les_donnees_hors_exemple(self):
        template = CreneauTemplate.objects.create(jour='LUNDI', heure_debut='06:00', heure_fin='07:00')
        edt = EmploiDuTemps.objects.create(
            annee_academique=self.annee, population_type='FORMATION', population_id=1,
            titre='EDT saisi', statut='PUBLIE',
        )
        seance = AffectationCreneau.objects.create(
            emploi_du_temps=edt, creneau_template=template, semaine_debut=1, semaine_fin=5,
        )
        reel = Pointage.objects.create(
            participant=Participant.objects.first(), seance_edt=seance,
            date_journee='2026-11-02', timestamp_entree=NOW - timedelta(days=1),
            device_id='MOBILE-REEL',
        )
        self.seed()
        call_command('seed_edt_demo', '--purger', verbosity=0)
        self.assertEqual(EmploiDuTemps.objects.count(), 1)
        self.assertEqual(AffectationCreneau.objects.count(), 1)
        self.assertTrue(Pointage.objects.filter(pk=reel.pk).exists())
        self.assertTrue(CreneauTemplate.objects.filter(pk=template.pk).exists())
        self.assertEqual(AffectationPedagogique.objects.count(), 30)
        call_command('seed_edt_demo', '--purger', verbosity=0)

    def test_purge_refuse_de_supprimer_une_presence_reelle_sur_edt_exemple(self):
        self.seed()
        point = Pointage.objects.first()
        point.device_id = 'MOBILE-REEL'
        point.save(update_fields=['device_id'])
        before = Pointage.objects.count()
        with self.assertRaisesMessage(Exception, 'Purge annulée'):
            call_command('seed_edt_demo', '--purger', verbosity=0)
        self.assertEqual(Pointage.objects.count(), before)
        self.assertEqual(EmploiDuTemps.objects.count(), 6)

    def test_calendrier_utilise_la_semaine_depuis_le_debut_de_annee(self):
        # 1er octobre 2026 est jeudi : jeudi appartient à S1, le suivant à S2.
        self.annee.refresh_from_db()
        self.assertEqual((timezone.localdate(NOW) - self.annee.date_debut).days // 7 + 1, 5)
        self.seed()
        jeudi = AffectationCreneau.objects.filter(creneau_template__jour=JOURS[3]).first()
        self.assertTrue(est_seance_du_jour(jeudi, self.annee.date_debut))
        self.assertTrue(est_seance_du_jour(jeudi, self.annee.date_debut + timedelta(days=7)))
        self.assertFalse(est_seance_du_jour(jeudi, self.annee.date_debut + timedelta(days=1)))

    def test_admin_expose_la_seance_lmd_et_la_provenance(self):
        self.seed()
        self.client.force_login(self.admin)
        pointage = Pointage.objects.filter(device_id=SOURCE).first()
        liste = self.client.get(reverse('admin:presences_pointage_changelist'), {'q': SOURCE})
        fiche = self.client.get(reverse('admin:presences_pointage_change', args=[pointage.pk]))
        self.assertEqual((liste.status_code, fiche.status_code), (200, 200))
        self.assertContains(liste, '[Exemple]')
        self.assertContains(liste, 'Assiduité')
        self.assertContains(fiche, SOURCE)
        self.assertContains(fiche, 'statut_assiduite')
        self.assertContains(fiche, 'seance_edt')
        self.assertIn(pointage.seance_edt.intitule, str(pointage))