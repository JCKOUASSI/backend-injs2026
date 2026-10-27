"""Tests du flux de rattrapage inter-cohorte (déplacement d'un auditeur vers la
séance d'une autre cohorte pour rattraper un cours manqué).

`test_badge_naturel_lie_rattrapage` appelle `/api/scan/` : c'est le scan QR
PUBLIC, volontairement désactivé par défaut hors DEBUG
(``PUBLIC_QR_SCAN_ENABLED``, cf. config/settings.py). Le scénario testé — un
badge réel sur la séance d'accueil — suppose explicitement ce scan actif :
on l'active donc via ``override_settings``, comme le fait déjà
``presences.tests.ScanModuleExclusivityTest``. Sans cela le test échoue avec
``403 SCAN_DISABLED`` dès que ``DEBUG`` est à ``False`` (CI, production).
"""
from datetime import time

from django.test import TestCase, override_settings
from django.utils import timezone

from formations.models import (
    Formation, Module, Participant, SessionModule, ModuleParticipant,
)
from statistiques.effectifs import aggregation_seances_modules, participant_ids_notoires

from .models import Pointage, Rattrapage
from .bulk_force_auditeurs import run_rattrapage_badgeage
from .rattrapage_service import annuler_rattrapage, generer_presence_rattrapage, infer_module_origine, lier_rattrapage_au_badge
from .views import _resolve_personne


def _cohorte(formation, groupe, matricule):
    """Crée un module 'Droit' pour un groupe + une séance + un auditeur inscrit."""
    module = Module.objects.create(
        formation=formation, intitule='Droit', grade='A4', groupe=groupe,
        statut=Module.Statut.EN_COURS,
    )
    seance = SessionModule.objects.create(
        module=module,
        date_journee=timezone.localdate(),
        numero=1,
        heure_debut_prevue=time(0, 1),
        heure_fin_prevue=time(23, 59),
    )
    participant = Participant.objects.create(
        matricule=matricule, nom='Nom', prenom=matricule, grade='A4', groupe=groupe,
    )
    ModuleParticipant.objects.create(module=module, participant=participant)
    return module, seance, participant


@override_settings(PUBLIC_QR_SCAN_ENABLED=True)
class RattrapageFlowTest(TestCase):
    def setUp(self):
        self.formation = Formation.objects.create(formation='Cycle A')
        # Cohorte d'origine (groupe 1) — l'auditeur P a manqué son cours.
        self.mod_a, self.seance_a, self.p = _cohorte(self.formation, 'GROUPE 1', 'P001')
        # Cohorte d'accueil (groupe 2) — même cours, autre groupe.
        self.mod_b, self.seance_b, self.q = _cohorte(self.formation, 'GROUPE 2', 'Q001')

    def _make_rattrapage(self):
        return Rattrapage.objects.create(
            participant=self.p,
            seance_rattrapage=self.seance_b,
            module_origine=self.mod_a,
            seance_manquee=self.seance_a,
            motif='Absence justifiée',
        )

    def test_badge_naturel_lie_rattrapage(self):
        """Un badge réel sur la séance d'accueil passe le rattrapage en effectué."""
        from datetime import timedelta
        from formations.models import QRToken

        rattrapage = self._make_rattrapage()
        self.seance_b.demarree_le = timezone.now()
        self.seance_b.save(update_fields=['demarree_le'])
        token = QRToken.objects.create(
            session=self.seance_b,
            expire_at=timezone.now() + timedelta(hours=1),
            actif=True,
        )
        from rest_framework.test import APIClient
        client = APIClient()
        res = client.post('/api/scan/', {
            'token_qr': str(token.token),
            'numero_participant': self.p.matricule,
        }, format='json')
        self.assertEqual(res.status_code, 201, res.data)

        rattrapage.refresh_from_db()
        self.assertEqual(rattrapage.statut, Rattrapage.Statut.EFFECTUE)
        self.assertIsNotNone(rattrapage.pointage_id)

    def test_lier_rattrapage_au_badge_idempotent(self):
        rattrapage = self._make_rattrapage()
        pointage = Pointage.objects.create(
            participant=self.p,
            session=self.seance_b,
            date_journee=timezone.localdate(),
            timestamp_entree=timezone.now(),
            statut=Pointage.Statut.EN_COURS,
        )
        lier_rattrapage_au_badge(self.p, self.seance_b, pointage)
        rattrapage.refresh_from_db()
        self.assertEqual(rattrapage.pointage_id, pointage.id)
        self.assertEqual(rattrapage.statut, Rattrapage.Statut.EFFECTUE)

    def test_scan_bloque_sans_rattrapage(self):
        """Sans rattrapage, l'auditeur du groupe 1 est refusé sur le module du groupe 2."""
        _, _, _, err = _resolve_personne('P001', self.formation, module=self.mod_b)
        self.assertIsNotNone(err)
        self.assertEqual(err.data['code'], 'PARTICIPANT_NOT_IN_LIST')

    def test_scan_autorise_avec_rattrapage_planifie(self):
        """Un rattrapage PLANIFIE autorise le scan sur le module d'accueil."""
        self._make_rattrapage()
        personne, type_str, _, err = _resolve_personne('P001', self.formation, module=self.mod_b)
        self.assertIsNone(err)
        self.assertEqual(type_str, 'participant')
        self.assertEqual(personne, self.p)

    def test_generer_presence_cree_pointage_et_effectue(self):
        rattrapage = self._make_rattrapage()
        pointage = generer_presence_rattrapage(rattrapage)
        rattrapage.refresh_from_db()

        self.assertIsNotNone(pointage)
        self.assertEqual(pointage.session, self.seance_b)
        self.assertEqual(pointage.participant, self.p)
        self.assertEqual(rattrapage.pointage_id, pointage.id)
        self.assertEqual(rattrapage.statut, Rattrapage.Statut.EFFECTUE)

    def test_rattrapage_groupé_credite_creneau_planifie_complet(self):
        """Rattrapage admin : durée = créneau EDT (heure_debut → heure_fin), pas +4 h."""
        from formations.volume_horaire import _session_prevu_minutes

        self.seance_b.heure_debut_prevue = time(8, 0)
        self.seance_b.heure_fin_prevue = time(13, 0)
        self.seance_b.save(update_fields=['heure_debut_prevue', 'heure_fin_prevue'])

        counts = run_rattrapage_badgeage(
            [self.p],
            self.seance_b,
            motif='Rattrapage test créneau complet',
            with_sortie=True,
        )
        self.assertEqual(counts['created'], 1)
        self.assertEqual(counts['sorties'], 1)

        pointage = Pointage.objects.get(session=self.seance_b, participant=self.p)
        prevu = _session_prevu_minutes(self.seance_b)
        self.assertEqual(prevu, 300.0)
        self.assertAlmostEqual(float(pointage.duree_presence_minutes), prevu, places=1)

    def test_generer_presence_credite_creneau_planifie(self):
        from formations.volume_horaire import _session_prevu_minutes

        self.seance_b.heure_debut_prevue = time(7, 30)
        self.seance_b.heure_fin_prevue = time(12, 30)
        self.seance_b.save(update_fields=['heure_debut_prevue', 'heure_fin_prevue'])

        rattrapage = self._make_rattrapage()
        pointage = generer_presence_rattrapage(rattrapage)

        self.assertAlmostEqual(
            float(pointage.duree_presence_minutes),
            _session_prevu_minutes(self.seance_b),
            places=1,
        )

    def test_generer_presence_idempotent(self):
        rattrapage = self._make_rattrapage()
        pt1 = generer_presence_rattrapage(rattrapage)
        pt2 = generer_presence_rattrapage(rattrapage)
        self.assertEqual(pt1.id, pt2.id)
        self.assertEqual(
            Pointage.objects.filter(session=self.seance_b, participant=self.p).count(), 1,
        )

    def test_rattrapage_compte_dans_stats_accueil(self):
        """La séance d'accueil compte le rattrapage dans ses statistiques (attendu + présent)."""
        rattrapage = self._make_rattrapage()
        generer_presence_rattrapage(rattrapage)

        agg = aggregation_seances_modules([self.mod_b.id])
        # Q inscrit + P (rattrapage) = 2 attendus distincts sur la séance d'accueil.
        self.assertEqual(agg['inscrits_distinct'], 2)
        # P est présent (pointage généré), Q ne l'est pas.
        self.assertEqual(agg['presents_distinct'], 1)
        self.assertEqual(agg['places_attendues'], 2)
        self.assertEqual(agg['places_presentes'], 1)

    def test_rattrapage_planifie_compte_comme_attendu(self):
        """Un rattrapage seulement planifié (sans présence) est déjà un attendu additionnel."""
        self._make_rattrapage()
        agg = aggregation_seances_modules([self.mod_b.id])
        self.assertEqual(agg['places_attendues'], 2)
        self.assertEqual(agg['places_presentes'], 0)

    def test_rattrapage_annule_exclu_des_stats(self):
        """Un rattrapage annulé n'est plus compté dans les attendus de la séance d'accueil."""
        rattrapage = self._make_rattrapage()
        annuler_rattrapage(rattrapage)
        agg = aggregation_seances_modules([self.mod_b.id])
        self.assertEqual(agg['inscrits_distinct'], 1)
        self.assertEqual(agg['places_attendues'], 1)

    def test_rattrapage_protege_de_absent_notoire(self):
        """L'auditeur qui rattrape n'est pas faussement marqué absent notoire."""
        rattrapage = self._make_rattrapage()
        generer_presence_rattrapage(rattrapage)
        notoires = participant_ids_notoires(module_ids=[self.mod_a.id])
        self.assertNotIn(self.p.id, notoires)

    def test_annuler_rattrapage(self):
        rattrapage = self._make_rattrapage()
        generer_presence_rattrapage(rattrapage)
        annuler_rattrapage(rattrapage, supprimer_pointage=True)
        rattrapage.refresh_from_db()
        self.assertEqual(rattrapage.statut, Rattrapage.Statut.ANNULE)
        self.assertIsNone(rattrapage.pointage_id)
        self.assertFalse(
            Pointage.objects.filter(session=self.seance_b, participant=self.p).exists(),
        )

    def test_unicite_participant_seance(self):
        from django.db import IntegrityError, transaction
        self._make_rattrapage()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Rattrapage.objects.create(
                    participant=self.p, seance_rattrapage=self.seance_b,
                )


class RattrapageApiTest(TestCase):
    def setUp(self):
        from rest_framework.test import APIClient
        from authentication.models import User

        self.formation = Formation.objects.create(formation='Cycle A')
        self.mod_a, self.seance_a, self.p = _cohorte(self.formation, 'GROUPE 1', 'P100')
        self.mod_b, self.seance_b, self.q = _cohorte(self.formation, 'GROUPE 2', 'Q100')
        self.user = User.objects.create_user(username='dfrc', password='pass', role='INJS_ADMIN')
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_create_sans_generation_presence(self):
        """Par défaut, le rattrapage reste planifié : l'auditeur doit badger."""
        res = self.client.post('/api/rattrapages/', {
            'participant_id': self.p.id,
            'seance_rattrapage_id': self.seance_b.id,
            'motif': 'Absence justifiée',
        }, format='json')
        self.assertEqual(res.status_code, 201, res.data)
        cree = res.data['created'][0]
        self.assertEqual(cree['statut'], 'PLANIFIE')
        self.assertIsNone(cree['pointage_id'])
        self.assertEqual(cree['module_origine']['id'], self.mod_a.id)
        self.assertEqual(cree['seance_manquee']['id'], self.seance_a.id)
        self.assertFalse(
            Pointage.objects.filter(session=self.seance_b, participant=self.p).exists(),
        )

    def test_create_avec_generation_presence(self):
        res = self.client.post('/api/rattrapages/', {
            'participant_id': self.p.id,
            'seance_rattrapage_id': self.seance_b.id,
            'motif': 'Absence justifiée',
            'generer_presence': True,
        }, format='json')
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data['count'], 1)
        cree = res.data['created'][0]
        self.assertEqual(cree['statut'], 'EFFECTUE')
        self.assertIsNotNone(cree['pointage_id'])
        self.assertTrue(
            Pointage.objects.filter(session=self.seance_b, participant=self.p).exists(),
        )

    def test_create_multi_seances_plusieurs_jours(self):
        from datetime import time, timedelta
        seance_b2 = SessionModule.objects.create(
            module=self.mod_b,
            date_journee=timezone.localdate() + timedelta(days=1),
            numero=2,
            heure_debut_prevue=time(0, 1),
            heure_fin_prevue=time(23, 59),
        )
        res = self.client.post('/api/rattrapages/', {
            'participant_id': self.p.id,
            'seance_rattrapage_ids': [self.seance_b.id, seance_b2.id],
            'generer_presence': False,
        }, format='json')
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data['count'], 2)
        self.assertEqual(
            Rattrapage.objects.filter(participant=self.p).count(), 2,
        )

    def test_list_et_filtre(self):
        Rattrapage.objects.create(participant=self.p, seance_rattrapage=self.seance_b)
        res = self.client.get('/api/rattrapages/?statut=PLANIFIE')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.data), 1)
        self.assertEqual(res.data[0]['participant']['matricule'], 'P100')

    def test_create_doublon_conflit(self):
        Rattrapage.objects.create(participant=self.p, seance_rattrapage=self.seance_b)
        res = self.client.post('/api/rattrapages/', {
            'participant_id': self.p.id,
            'seance_rattrapage_id': self.seance_b.id,
        }, format='json')
        self.assertEqual(res.status_code, 409)

    def test_create_bloque_deja_inscrit(self):
        ModuleParticipant.objects.create(module=self.mod_b, participant=self.p)
        res = self.client.post('/api/rattrapages/', {
            'participant_id': self.p.id,
            'seance_rattrapage_id': self.seance_b.id,
        }, format='json')
        self.assertEqual(res.status_code, 400, res.data)
        self.assertIn('seance_ids', res.data)

    def test_create_infer_module_origine_par_cohorte(self):
        """Deux inscriptions « Droit » : l'origine est celle qui matche grade/groupe auditeur."""
        mod_alt = Module.objects.create(
            formation=self.formation,
            intitule='Droit',
            grade='A3',
            groupe='GROUPE 1',
            statut=Module.Statut.EN_COURS,
        )
        ModuleParticipant.objects.create(module=mod_alt, participant=self.p)

        res = self.client.post('/api/rattrapages/', {
            'participant_id': self.p.id,
            'seance_rattrapage_id': self.seance_b.id,
        }, format='json')
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data['created'][0]['module_origine']['id'], self.mod_a.id)
        self.assertNotEqual(res.data['created'][0]['module_origine']['id'], mod_alt.id)

    def test_infer_module_origine_desambiguise_grade_groupe(self):
        mod_alt = Module.objects.create(
            formation=self.formation,
            intitule='Droit',
            grade='A3',
            groupe='GROUPE 1',
            statut=Module.Statut.EN_COURS,
        )
        ModuleParticipant.objects.create(module=mod_alt, participant=self.p)
        picked = infer_module_origine(self.p, self.seance_b)
        self.assertIsNotNone(picked)
        self.assertEqual(picked.id, self.mod_a.id)

    def test_create_reouvre_annule(self):
        r = Rattrapage.objects.create(
            participant=self.p,
            seance_rattrapage=self.seance_b,
            statut=Rattrapage.Statut.ANNULE,
        )
        res = self.client.post('/api/rattrapages/', {
            'participant_id': self.p.id,
            'seance_rattrapage_id': self.seance_b.id,
            'motif': 'Nouvelle planification',
        }, format='json')
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data['count'], 1)
        self.assertEqual(res.data['reactivated'], [self.seance_b.id])
        r.refresh_from_db()
        self.assertEqual(r.statut, Rattrapage.Statut.PLANIFIE)
        self.assertEqual(r.motif, 'Nouvelle planification')
        self.assertEqual(r.module_origine_id, self.mod_a.id)
        self.assertEqual(Rattrapage.objects.filter(participant=self.p, seance_rattrapage=self.seance_b).count(), 1)

    def test_annuler(self):
        r = Rattrapage.objects.create(participant=self.p, seance_rattrapage=self.seance_b)
        res = self.client.post(f'/api/rattrapages/{r.id}/annuler/', {}, format='json')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['statut'], 'ANNULE')

    def test_recherche_participants_et_seances(self):
        res_p = self.client.get('/api/rattrapages/participants/?q=P100')
        self.assertEqual(res_p.status_code, 200)
        self.assertTrue(any(p['matricule'] == 'P100' for p in res_p.data))

        res_s = self.client.get(f'/api/rattrapages/seances/?participant={self.p.id}&q=Droit')
        self.assertEqual(res_s.status_code, 200)
        by_module = {s['module']['id']: s for s in res_s.data}
        # La séance du module d'origine (où P est inscrit) doit être signalée.
        self.assertTrue(by_module[self.mod_a.id]['deja_inscrit'])
        self.assertFalse(by_module[self.mod_b.id]['deja_inscrit'])

    def test_dashboard_seance_accueil_compte_le_rattrapage(self):
        """La séance d'accueil voit son effectif augmenter du rattrapage."""
        r = Rattrapage.objects.create(participant=self.p, seance_rattrapage=self.seance_b)
        generer_presence_rattrapage(r)

        res = self.client.get(
            f'/api/formations/{self.formation.id}/dashboard/?session_id={self.seance_b.id}'
        )
        self.assertEqual(res.status_code, 200)
        # Q (inscrit) + P (rattrapage) = 2 attendus sur cette séance.
        self.assertEqual(res.data['total_attendus'], 2)
        tous = res.data['presents'] + res.data['en_salle'] + res.data['absents']
        p_row = next((x for x in tous if x.get('id') == self.p.id), None)
        self.assertIsNotNone(p_row)
        self.assertTrue(p_row.get('rattrapage'))

    def test_recherche_modules_avec_seances(self):
        res = self.client.get(f'/api/rattrapages/modules/?participant={self.p.id}&q=Droit')
        self.assertEqual(res.status_code, 200)
        by_id = {m['id']: m for m in res.data}
        self.assertIn(self.mod_b.id, by_id)
        self.assertEqual(by_id[self.mod_b.id]['nb_seances'], 1)
        self.assertEqual(len(by_id[self.mod_b.id]['seances']), 1)
        self.assertTrue(by_id[self.mod_a.id]['deja_inscrit'])
