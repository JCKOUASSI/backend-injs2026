"""Le jeu de démonstration doit être identifiable, idempotent et effaçable.

Des données de démonstration sont un danger si elles fuient : un étudiant
« DEMO-… » dans une base de production fausserait des effectifs réels. Ces
tests fixent donc trois propriétés, et une quatrième qui compte autant :

1. le jeu rend l'application RÉELLEMENT utilisable (audit générable) ;
2. il est identifiable par des marqueurs stables ;
3. il est idempotent (relancer ne duplique rien) ;
4. il ne supprime QUE ce qu'il a créé — une donnée réelle voisine survit.

Le dernier point est le plus important : une commande de nettoyage qui efface
large est plus destructrice que l'absence de commande.
"""

import io
from datetime import date, time

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from edts.moteur import canevas_officiel as CO
from edts.models import CreneauTemplate
from formations.models import RefFormation, RefSalle, RefSite
from scolarite.models import AffectationPedagogique, AnneeAcademique, Groupe


def _appeler(*options):
    sortie = io.StringIO()
    call_command('donnees_demonstration_getinjs', *options,
                 stdout=sortie, stderr=io.StringIO())
    return sortie.getvalue()


@override_settings(DEBUG=True)
class JeuDemonstrationTests(TestCase):

    def test_cree_un_jeu_utilisable(self):
        sortie = _appeler()
        self.assertIn('FORMATION DÉMONSTRATION', sortie)
        self.assertTrue(AnneeAcademique.objects.filter(
            libelle__startswith='DEMO-').exists())
        self.assertEqual(Groupe.objects.filter(nom__startswith='DEMO-G').count(), 4)
        self.assertTrue(AffectationPedagogique.objects.exists())
        # Le canevas officiel complet est disponible : sans lui, aucun besoin
        # ne serait calculable et la démonstration ne démontrerait rien.
        self.assertEqual(CreneauTemplate.objects.count(), CO.nombre_officiel())

    def test_le_jeu_rend_l_audit_generable(self):
        """C'est la finalité : l'écran doit répondre « puis-je générer ? » oui."""
        from edts.moteur import besoins as B

        _appeler()
        annee = AnneeAcademique.objects.get(libelle__startswith='DEMO-')
        resultat = B.calculate_teaching_needs(annee_academique_id=annee.pk)
        self.assertFalse(resultat.vide, f'motif : {resultat.motif_echec}')
        self.assertGreater(len(resultat.besoins), 0)

    def test_idempotent(self):
        _appeler()
        groupes = Groupe.objects.filter(nom__startswith='DEMO-G').count()
        affectations = AffectationPedagogique.objects.count()
        _appeler()
        self.assertEqual(Groupe.objects.filter(nom__startswith='DEMO-G').count(),
                         groupes)
        self.assertEqual(AffectationPedagogique.objects.count(), affectations)

    def test_marqueurs_identifiables(self):
        _appeler()
        annee = AnneeAcademique.objects.get(libelle__startswith='DEMO-')
        self.assertTrue(annee.libelle.startswith('DEMO-'))
        self.assertTrue(RefFormation.objects.filter(
            intitule__startswith='FORMATION DÉMONSTRATION').exists())
        for salle in RefSalle.objects.filter(nom__startswith='DEMO-S'):
            self.assertIsNotNone(salle.capacite,
                                 'Une salle de démonstration sans capacité rendrait '
                                 'C4 invérifiable.')

    def test_formation_de_demonstration_sans_filiere_officielle(self):
        """La démonstration reste planifiable, mais ne revendique aucune filière.

        Le moteur d'EDT ne planifie que le périmètre INJS (`formations_injs()`) :
        la démonstration doit donc y figurer, sinon elle ne démontre rien. Ce qui
        la distingue d'un cycle réel, c'est l'absence de filière F01–F08 et une
        source qui dit explicitement « hors référentiel officiel ». Le contrôle
        du référentiel, lui, compte par filière : il ignore donc cette ligne.
        """
        _appeler()
        demo = RefFormation.objects.get(intitule__startswith='FORMATION DÉMONSTRATION')
        self.assertEqual(demo.filiere_code, '')
        self.assertIn('DÉMONSTRATION', demo.source)

    def test_corrige_un_jeu_anterieur_rattache_a_une_filiere(self):
        """Idempotence : un jeu F01 laissé par une version antérieure est corrigé."""
        RefFormation.objects.create(
            intitule='FORMATION DÉMONSTRATION GET-INJS', perimetre='INJS',
            filiere_code='F01', source='A45',
        )
        _appeler()
        demo = RefFormation.objects.get(intitule__startswith='FORMATION DÉMONSTRATION')
        self.assertEqual(demo.filiere_code, '')
        self.assertIn('DÉMONSTRATION', demo.source)

    def test_nombre_de_groupes_parametrable(self):
        _appeler('--groupes', '2')
        self.assertEqual(Groupe.objects.filter(nom__startswith='DEMO-G').count(), 2)


@override_settings(DEBUG=True)
class SuppressionDemonstrationTests(TestCase):
    """`--supprimer` ne doit toucher QUE les objets de démonstration."""

    def _creer_donnee_reelle(self):
        annee = AnneeAcademique.objects.create(
            libelle='2026-2027', date_debut=date(2026, 10, 1),
            date_fin=date(2027, 6, 30), courante=False,
        )
        formation = RefFormation.objects.create(
            intitule='FORMATION RÉELLE INJS', perimetre='INJS',
            filiere_code='F02', source='A45',
        )
        site = RefSite.objects.create(nom='SITE RÉEL INJS')
        salle = RefSalle.objects.create(
            site=site, nom='Amphi réel', type_lieu='AMPHI', capacite=300,
        )
        return annee, formation, salle

    def test_supprimer_efface_le_jeu_de_demonstration(self):
        _appeler()
        self.assertTrue(AnneeAcademique.objects.filter(
            libelle__startswith='DEMO-').exists())
        _appeler('--supprimer')
        self.assertFalse(AnneeAcademique.objects.filter(
            libelle__startswith='DEMO-').exists())
        self.assertFalse(Groupe.objects.filter(nom__startswith='DEMO-G').exists())
        self.assertFalse(RefSalle.objects.filter(nom__startswith='DEMO-S').exists())
        self.assertFalse(AffectationPedagogique.objects.exists())

    def test_supprimer_conserve_les_donnees_reelles(self):
        annee, formation, salle = self._creer_donnee_reelle()
        _appeler()
        _appeler('--supprimer')
        self.assertTrue(AnneeAcademique.objects.filter(pk=annee.pk).exists())
        self.assertTrue(RefFormation.objects.filter(pk=formation.pk).exists())
        self.assertTrue(RefSalle.objects.filter(pk=salle.pk).exists())

    def test_supprimer_sans_jeu_ne_casse_rien(self):
        annee, formation, salle = self._creer_donnee_reelle()
        _appeler('--supprimer')
        self.assertTrue(AnneeAcademique.objects.filter(pk=annee.pk).exists())


@override_settings(DEBUG=False)
class GardeFouProductionTests(TestCase):
    """Hors mode démonstration, la commande refuse sans --forcer."""

    def test_refuse_en_production(self):
        with self.assertRaises(CommandError) as ctx:
            _appeler()
        self.assertIn('--forcer', str(ctx.exception))
        self.assertFalse(AnneeAcademique.objects.exists())

    def test_forcer_permet_l_execution_explicite(self):
        _appeler('--forcer')
        self.assertTrue(AnneeAcademique.objects.filter(
            libelle__startswith='DEMO-').exists())
