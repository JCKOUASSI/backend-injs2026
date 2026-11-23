"""Tests du moteur GET-INJS : conflits, placement contrôlé, génération (P06/P07/P08).

Point d'attention relevé par l'audit : l'ancienne implémentation utilisait le
lookup JSON `contains`, non supporté par SQLite (`NotSupportedError`) ; ces
tests tournent donc aussi sous la base de bac à sable et verrouillent la
portabilité.
"""

from datetime import date, time

from django.test import TestCase

from edts import services
from edts.models import AffectationCreneau, ConflitCreneau, CreneauTemplate, EmploiDuTemps
from scolarite.models import AnneeAcademique


def creer_edt(annee, cible_id):
    return EmploiDuTemps.objects.create(
        annee_academique=annee, population_type='ENSEIGNANT', population_id=cible_id,
        titre=f'EDT {cible_id}', semaine_debut=1, semaine_fin=20,
    )


def creer_creneau(jour, debut, fin):
    return CreneauTemplate.objects.create(jour=jour, heure_debut=debut, heure_fin=fin)


def placer(edt, creneau, debut_s, fin_s, **champs):
    return AffectationCreneau.objects.create(
        emploi_du_temps=edt, creneau_template=creneau,
        semaine_debut=debut_s, semaine_fin=fin_s, **champs,
    )


class PrimitivesTests(TestCase):
    def test_chevauchement_semaines(self):
        self.assertTrue(services.semaines_en_chevauchement(1, 5, 5, 9))
        self.assertTrue(services.semaines_en_chevauchement(3, 4, 1, 10))
        self.assertFalse(services.semaines_en_chevauchement(1, 4, 5, 9))
        self.assertFalse(services.semaines_en_chevauchement(None, 4, 5, 9))

    def test_chevauchement_horaires(self):
        class C:
            def __init__(self, jour, debut, fin):
                self.jour, self.heure_debut, self.heure_fin = jour, debut, fin
        a = C('LUNDI', time(8), time(10))
        b = C('LUNDI', time(9, 30), time(11))
        c = C('MARDI', time(9), time(11))
        d = C('LUNDI', time(10), time(12))
        self.assertTrue(services.horaires_en_chevauchement(a, b))
        self.assertFalse(services.horaires_en_chevauchement(a, c))
        self.assertFalse(services.horaires_en_chevauchement(a, d))  # bord à bord


class DetectionConflitsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.annee = AnneeAcademique.objects.create(
            libelle='2026-2027', date_debut=date(2026, 10, 1), date_fin=date(2027, 9, 30))
        cls.lundi8 = creer_creneau('LUNDI', time(8), time(10))
        cls.lundi10 = creer_creneau('LUNDI', time(10), time(12))
        cls.edt1 = creer_edt(cls.annee, 101)
        cls.edt2 = creer_edt(cls.annee, 102)

    def _conf_autre_edt_meme_enseignant(self):
        a1 = placer(self.edt1, self.lundi8, 1, 10, enseignant_id=777, nature='COURS', intitule='M1')
        a2 = placer(self.edt2, self.lundi8, 5, 12, enseignant_id=777, nature='TD', intitule='M2')
        return a1, a2

    def test_detection_portable_sans_lookup_json(self):
        """Sur SQLite, l'ancienne implémentation levait NotSupportedError."""
        self._conf_autre_edt_meme_enseignant()
        stats = services.detecter_conflits(self.edt1)  # ne lève pas
        self.assertGreaterEqual(stats['conflits_detectes'], 1)

    def test_conflit_global_entre_edt_distincts(self):
        self._conf_autre_edt_meme_enseignant()
        services.detecter_conflits(self.edt1)
        conflit = ConflitCreneau.objects.get(emploi_du_temps=self.edt1, actif=True)
        self.assertEqual(conflit.type_conflit, 'HORAIRE_ENSEIGNANT')
        self.assertIn('même enseignant', conflit.description)

    def test_pas_de_conflit_bord_a_bord_et_salle_comune_seule(self):
        placer(self.edt1, self.lundi8, 1, 10, salle_nom='A101')
        placer(self.edt1, self.lundi10, 1, 10, salle_nom='B202')
        stats = services.detecter_conflits(self.edt1)
        self.assertEqual(stats['conflits_detectes'], 0)

    def test_cloture_automatique_des_conflits_devenus_obsoletes(self):
        a1, a2 = self._conf_autre_edt_meme_enseignant()
        services.detecter_conflits(self.edt1)
        self.assertEqual(ConflitCreneau.objects.filter(emploi_du_temps=self.edt1, actif=True).count(), 1)
        # L'enseignant est libéré sur l'autre EDT : le conflit doit se clôturer.
        a2.enseignant_id = 999
        a2.save()
        stats = services.detecter_conflits(self.edt1)
        self.assertEqual(stats['conflits_clotures'], 1)
        self.assertEqual(ConflitCreneau.objects.filter(emploi_du_temps=self.edt1, actif=True).count(), 0)

    def test_repetition_detection_sans_doublons(self):
        self._conf_autre_edt_meme_enseignant()
        services.detecter_conflits(self.edt1)
        services.detecter_conflits(self.edt1)
        self.assertEqual(ConflitCreneau.objects.filter(emploi_du_temps=self.edt1, actif=True).count(), 1)

    def test_signalement_manuel_ne_se_cloture_pas_seul(self):
        placer(self.edt1, self.lundi8, 1, 2, salle_nom='A101')
        manuel = ConflitCreneau.objects.create(
            emploi_du_temps=self.edt1, type_conflit='MANUEL',
            description='Ascenseur en panne ce jour-là.', lignes_creneaux=[],
        )
        services.detecter_conflits(self.edt1)
        manuel.refresh_from_db()
        self.assertTrue(manuel.actif)


class PlacementControleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.annee = AnneeAcademique.objects.create(
            libelle='2026-2027', date_debut=date(2026, 10, 1), date_fin=date(2027, 9, 30))
        cls.lundi8 = creer_creneau('LUNDI', time(8), time(10))
        cls.edt = creer_edt(cls.annee, 201)

    def test_verifier_affectation_signale_avant_pose(self):
        placer(self.edt, self.lundi8, 1, 10, enseignant_id=555)
        candidate = AffectationCreneau(
            emploi_du_temps=self.edt, creneau_template=self.lundi8,
            semaine_debut=5, semaine_fin=12, enseignant_id=555,
        )
        avertissements = services.verifier_affectation(candidate)
        self.assertEqual(len(avertissements), 1)
        self.assertIn('même enseignant', avertissements[0])

    def test_verifier_affectation_silencieuse_si_ressources_distinctes(self):
        placer(self.edt, self.lundi8, 1, 10, enseignant_id=555, salle_nom='A')
        candidate = AffectationCreneau(
            emploi_du_temps=self.edt, creneau_template=self.lundi8,
            semaine_debut=1, semaine_fin=10, enseignant_id=556, salle_nom='B',
        )
        self.assertEqual(services.verifier_affectation(candidate), [])


class GenerationTests(TestCase):
    """Générateur de brouillon : sans données pédagogiques, rien à placer ;
    avec affectations validées, placement sans conflit dur et explications."""

    @classmethod
    def setUpTestData(cls):
        cls.annee = AnneeAcademique.objects.create(
            libelle='2026-2027', date_debut=date(2026, 10, 1), date_fin=date(2027, 9, 30))
        cls.edt = creer_edt(cls.annee, 301)
        for jour in ('LUNDI', 'MARDI', 'MERCREDI'):
            creer_creneau(jour, time(8), time(10))
            creer_creneau(jour, time(10), time(12))

    def test_sans_creneaux_disponibles_explication(self):
        CreneauTemplate.objects.all().delete()
        stats = services.generer_brouillon(self.edt)
        self.assertEqual(stats['seances_placees'], 0)
        self.assertIn('créneau type', stats['motif_echec'])

    def test_generation_refusee_hors_brouillon(self):
        self.edt.statut = 'VALIDE'
        self.edt.save()
        with self.assertRaises(ValueError):
            services.generer_brouillon(self.edt)
