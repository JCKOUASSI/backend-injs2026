"""Corps enseignant LMD — grade, enrichissement liste, panorama, seed.

L'écran « Enseignants » présentait 3 profils sans grade et un compteur
« Modules » qui comptait des formations continues, pendant que les 779
ECUE des maquettes actives n'avaient aucun enseignant et que le grade
pointait le référentiel des grades d'admission. Ces tests verrouillent les
corrections : grade académique exposé/saisissable, charge réelle par
enseignant, couverture des ECUE et seed d'exemple idempotent/purgeable.
"""
from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient

from authentication.models import User
from formations.models import Formateur, RefFormation
from referentiels.models import RefGradeEnseignant
from scolarite.models import (
    AffectationPedagogique, AnneeAcademique, ECUE, Groupe, Maquette, Niveau,
    Semestre, UE,
)


class EnseignantsBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username='dfrc_ens', password='pass', role='ADMIN',
        )
        cls.grade = RefGradeEnseignant.objects.create(
            code='MAITRE_CONFERENCES', libelle='Maître de Conférences',
        )
        cls.formation = RefFormation.objects.create(
            intitule='ENTRAÎNEMENT SPORTIF — LICENCE',
        )
        cls.enseignant = Formateur.objects.create(
            numerobadge='F900', nom='TEMOIN', prenom='Sara',
            email='sara.temoin@exemple.injs.ci',
            specialite='Physiologie de l’exercice', grade_ref=cls.grade,
            statut_enseignant='Titulaire',
        )
        cls.annee = AnneeAcademique.objects.create(
            libelle='2026-2027', date_debut='2026-10-01', date_fin='2027-07-31',
            courante=True,
        )
        cls.niveau = Niveau.objects.create(code='L1', libelle='Licence 1', ordre=1)
        cls.semestre = Semestre.objects.create(niveau=cls.niveau, numero=1)
        cls.maquette = Maquette.objects.create(
            annee_academique=cls.annee, ref_formation=cls.formation,
            niveau=cls.niveau, statut=Maquette.Statut.BROUILLON,
        )
        cls.ue = UE.objects.create(
            maquette=cls.maquette, semestre=cls.semestre,
            code='UE1', intitule='Sciences de la vie', credits=6,
        )
        cls.ecue = ECUE.objects.create(
            ue=cls.ue, code='ECUE1', intitule='Physiologie', credits=6,
        )
        # Créée avant activation : une maquette ACTIVE est immuable.
        cls.ecue2 = ECUE.objects.create(
            ue=cls.ue, code='ECUE2', intitule='Anatomie', credits=3,
        )
        cls.maquette.statut = Maquette.Statut.ACTIVE
        cls.maquette.save(update_fields=['statut'])
        cls.affectation = AffectationPedagogique.objects.create(
            annee_academique=cls.annee, ref_formation=cls.formation,
            niveau=cls.niveau, semestre=cls.semestre, ue=cls.ue,
            ecue=cls.ecue, enseignant=cls.enseignant,
            volume_horaire=30, statut=AffectationPedagogique.Statut.VALIDEE,
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.user)


class EnseignantsApiTests(EnseignantsBase):
    def test_grade_academique_expose_dans_la_liste(self):
        res = self.client.get('/api/formations/formateurs/list/')
        self.assertEqual(res.status_code, 200)
        ligne = res.data['results'][0]
        self.assertEqual(ligne['grade']['code'], 'MAITRE_CONFERENCES')
        self.assertEqual(ligne['grade']['libelle'], 'Maître de Conférences')
        self.assertEqual(ligne['statut_enseignant'], 'Titulaire')

    def test_charge_reelle_de_l_annee_courante(self):
        res = self.client.get('/api/formations/formateurs/list/')
        ens = res.data['results'][0]['enseignements']
        self.assertEqual(ens['nb_ecue'], 1)
        self.assertEqual(ens['heures'], 30.0)
        self.assertEqual(ens['formations'], ['ENTRAÎNEMENT SPORTIF — LICENCE'])

    def test_formations_sans_doublons_malgre_plusieurs_ecue(self):
        # Régression : le tri par défaut des affectations cassait distinct()
        # et la liste répétait la formation autant que d'ECUE affectées.
        AffectationPedagogique.objects.create(
            annee_academique=self.annee, ref_formation=self.formation,
            niveau=self.niveau, semestre=self.semestre, ue=self.ue,
            ecue=self.ecue2, enseignant=self.enseignant,
            volume_horaire=15, statut=AffectationPedagogique.Statut.VALIDEE,
        )
        res = self.client.get('/api/formations/formateurs/list/')
        ens = res.data['results'][0]['enseignements']
        self.assertEqual(ens['nb_ecue'], 2)
        self.assertEqual(ens['heures'], 45.0)
        self.assertEqual(ens['formations'], ['ENTRAÎNEMENT SPORTIF — LICENCE'])

    def test_filtre_par_grade(self):
        res = self.client.get(
            '/api/formations/formateurs/list/', {'grade': 'PROFESSEUR_TITULAIRE'},
        )
        self.assertEqual(res.data['count'], 0)
        res = self.client.get(
            '/api/formations/formateurs/list/', {'grade': 'MAITRE_CONFERENCES'},
        )
        self.assertEqual(res.data['count'], 1)

    def test_panorama_couverture_et_grades(self):
        res = self.client.get('/api/formations/formateurs/stats/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['enseignants'], 1)
        couverture = res.data['couverture']
        self.assertEqual(couverture['ecue_total'], 2)
        self.assertEqual(couverture['ecue_couvertes'], 1)
        self.assertEqual(couverture['taux_couverture'], 50.0)
        self.assertEqual(couverture['heures_affectees'], 30.0)
        self.assertEqual(res.data['par_statut'], {'Titulaire': 1})
        self.assertIn(
            'MAITRE_CONFERENCES',
            {g['code'] for g in res.data['grades_disponibles']},
        )


class SeedEnseignantsTests(EnseignantsBase):
    def test_seed_cree_equipe_et_couvre_les_ecue(self):
        # Un second grade nécessaire au profil par défaut de la formation.
        for code, libelle in [
            ('PROFESSEUR_TITULAIRE', 'Professeur Titulaire'),
            ('MAITRE_ASSISTANT', 'Maître-Assistant'),
            ('PROF_AGREGE_EPS', 'Professeur Agrégé d’EPS'),
        ]:
            RefGradeEnseignant.objects.get_or_create(
                code=code, defaults={'libelle': libelle},
            )
        call_command('seed_enseignants_demo')
        exemples = Formateur.objects.filter(
            email__endswith='@exemple.injs.ci', observations__startswith='[Exemple]',
        )
        self.assertEqual(exemples.count(), 4)
        self.assertTrue(exemples.exclude(grade_ref__isnull=True).count() == 4)
        affectations = AffectationPedagogique.objects.filter(
            observations__startswith='[Exemple]',
        )
        self.assertEqual(affectations.count(), 2)
        self.assertEqual(
            set(affectations.values_list('ecue_id', flat=True)),
            {self.ecue.pk, self.ecue2.pk},
        )
        # Volume d'exemple documenté : 5 h par crédit (6 crédits → 30 h).
        self.assertEqual(
            float(affectations.get(ecue=self.ecue).volume_horaire), 30.0,
        )

    def test_seed_rattache_les_affectations_aux_groupes(self):
        # Sans groupe rattaché, le tableau de bord signalait « 130 groupes
        # sans affectation pédagogique » alors que les affectations
        # existaient : le seed doit relier chaque affectation d'exemple au
        # groupe actif de son périmètre (année, formation, niveau).
        groupe = Groupe.objects.create(
            annee_academique=self.annee, ref_formation=self.formation,
            niveau=self.niveau, nom='L1 — Groupe A',
        )
        call_command('seed_enseignants_demo')
        affectations = AffectationPedagogique.objects.filter(
            observations__startswith='[Exemple]',
        )
        self.assertEqual(affectations.count(), 2)
        self.assertEqual(
            set(affectations.values_list('groupe_id', flat=True)),
            {groupe.pk},
        )
        # Régénération non destructive : mêmes lignes, pas de doublons.
        ids_avant = set(affectations.values_list('pk', flat=True))
        call_command('seed_enseignants_demo')
        self.assertEqual(
            set(AffectationPedagogique.objects.filter(
                observations__startswith='[Exemple]',
            ).values_list('pk', flat=True)),
            ids_avant,
        )

    def test_seed_idempotent_puis_purge(self):
        call_command('seed_enseignants_demo')
        total = Formateur.objects.filter(
            email__endswith='@exemple.injs.ci', observations__startswith='[Exemple]',
        ).count()
        call_command('seed_enseignants_demo')
        self.assertEqual(
            Formateur.objects.filter(
                email__endswith='@exemple.injs.ci',
                observations__startswith='[Exemple]',
            ).count(),
            total,
        )
        call_command('seed_enseignants_demo', '--purger')
        self.assertFalse(Formateur.objects.filter(
            observations__startswith='[Exemple]',
        ).exists())
        self.assertFalse(AffectationPedagogique.objects.filter(
            observations__startswith='[Exemple]',
        ).exists())
        # L'enseignant témoin (hors seed) et son affectation survivent.
        self.assertTrue(Formateur.objects.filter(pk=self.enseignant.pk).exists())
        self.assertTrue(AffectationPedagogique.objects.filter(
            pk=self.affectation.pk,
        ).exists())


class FicheEnseignantLMDTests(EnseignantsBase):
    def test_fiche_utilise_les_affectations_lmd_pas_la_paie_legacy(self):
        self.enseignant.observations = '[Exemple] Fiche fictive.'
        self.enseignant.numero_piece_identite = 'SECRET-PIECE'
        self.enseignant.numero_compte_bancaire = 'SECRET-RIB'
        self.enseignant.save()
        res = self.client.get(f'/api/formations/formateurs/{self.enseignant.pk}/fiche/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['nb_formations'], 1)
        self.assertEqual(res.data['nb_ecue'], 1)
        self.assertEqual(res.data['heures_affectees'], 30)
        self.assertEqual(res.data['grade_label'], 'Maître de Conférences')
        self.assertTrue(res.data['est_exemple'])
        self.assertEqual(res.data['charge']['affectee'], 30)
        self.assertEqual(res.data['affectations'][0]['ecue_code'], 'ECUE1')
        self.assertIsNone(res.data['taux_presence'])
        self.assertIsNone(res.data['heures_effectuees'])
        self.assertIsNone(res.data['satisfaction_etudiants'])
        self.assertNotIn('numero_piece_identite', res.data)
        self.assertNotIn('numero_compte_bancaire', res.data)
        liste = self.client.get('/api/formations/formateurs/list/')
        self.assertEqual(liste.data['results'][0]['nb_formations'], 1)

    def test_affectation_annulee_exclue_de_la_fiche(self):
        self.affectation.statut = AffectationPedagogique.Statut.ANNULEE
        self.affectation.save()
        res = self.client.get(f'/api/formations/formateurs/{self.enseignant.pk}/fiche/')
        self.assertEqual(res.data['nb_formations'], 0)
        self.assertEqual(res.data['heures_affectees'], 0)
        self.assertEqual(res.data['affectations'], [])

    def test_exports_pedagogiques_reels_sans_montants(self):
        from io import BytesIO
        from openpyxl import load_workbook
        pdf = self.client.get(f'/api/formations/formateurs/{self.enseignant.pk}/fiche/export/pdf/')
        xlsx = self.client.get(f'/api/formations/formateurs/{self.enseignant.pk}/fiche/export/xlsx/')
        self.assertEqual(pdf.status_code, 200)
        self.assertTrue(pdf.content.startswith(b'%PDF'))
        self.assertEqual(xlsx.status_code, 200)
        wb = load_workbook(BytesIO(xlsx.content))
        contenu = ' '.join(str(c.value or '') for row in wb.active.iter_rows() for c in row)
        self.assertIn('ECUE1', contenu)
        self.assertIn('Non disponible', contenu)
        self.assertNotIn('Montant réalisé', contenu)

    def test_fiche_anonyme_et_finance_refusees(self):
        url = f'/api/formations/formateurs/{self.enseignant.pk}/fiche/'
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(url).status_code, 401)
        self.client.force_authenticate(User.objects.create_user('finance-fiche', role='FINANCE'))
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_couverture_limitee_aux_ecue_des_maquettes_actives(self):
        brouillon = Maquette.objects.create(
            annee_academique=self.annee, ref_formation=self.formation,
            niveau=self.niveau, statut=Maquette.Statut.BROUILLON,
        )
        ue = UE.objects.create(maquette=brouillon, semestre=self.semestre, code='BROUILLON', intitule='Brouillon', credits=3)
        ecue = ECUE.objects.create(ue=ue, code='HORS-ACTIF', intitule='Hors actif', credits=3)
        AffectationPedagogique.objects.create(
            annee_academique=self.annee, ref_formation=self.formation,
            niveau=self.niveau, semestre=self.semestre, ue=ue, ecue=ecue,
            enseignant=self.enseignant, volume_horaire=100,
        )
        couverture = self.client.get('/api/formations/formateurs/stats/').data['couverture']
        self.assertEqual(couverture['ecue_total'], 2)
        self.assertEqual(couverture['ecue_couvertes'], 1)
        self.assertEqual(couverture['taux_couverture'], 50)
        self.assertEqual(couverture['heures_affectees'], 30)

    def test_filtre_specialite_et_source_reelle(self):
        res = self.client.get('/api/formations/formateurs/list/', {'specialite': 'Physiologie de l’exercice'})
        self.assertEqual(res.data['count'], 1)
        self.assertFalse(res.data['results'][0]['est_exemple'])
        stats = self.client.get('/api/formations/formateurs/stats/').data
        self.assertIn('Physiologie de l’exercice', stats['specialites'])
