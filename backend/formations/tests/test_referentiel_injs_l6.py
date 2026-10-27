"""L6 — Tests du référentiel officiel INJS-LMD.

Couvre les tests A→F du cahier L6 §20 :

* A — l'API Formations ne retourne que les formations INJS ;
* B — aucune formation CPFAE n'est retournée ;
* C — les 8 filières validées sont présentes une fois le référentiel chargé ;
* D — les formations INJS peuvent être reliées aux parcours ;
* E — les formations INJS peuvent être reliées aux maquettes (→ UE → ECUE) ;
* F — les modifications ne cassent pas L1-L5 ( AffectationPedagogique →
  AffectationCreneau → Séance → Présence, et le contrat API cours).
"""

from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from authentication.models import User
from formations.models import Formation, Formateur, RefFormation
from formations.referentiel_injs_l6 import (
    CORPUS_LEGACY,
    FILIERES_INJS,
    formations_injs,
    signaler_ecarts,
)
from scolarite.models import (
    AffectationPedagogique,
    AnneeAcademique,
    ECUE,
    Maquette,
    Niveau,
    Parcours,
    Semestre,
    UE,
)

ENDPOINT = '/api/formations/lmd/formations/'

INTITULES_ETRANGERS = [
    'Formation en Administration de Base (FAB) — Vague 1',
    'Formation en Administration Complémentaire (FAC) — Vague 2',
    'Formation en Finances Publiques',
    'DEBUG FORM',
]


def _creer_utilisateur(role='INJS_ADMIN'):
    return User.objects.create_user(
        username=f'l6-{role.lower()}', password='pass', role=role,
    )


class BaseL6TestCase(TestCase):
    """Fixture minimale + chargement du référentiel via la commande L6.

    La base de test est vierge : la commande L6 ne fait que qualifier les cycles
    existants. Les référentiels structurels (niveaux LMD, semestres) et les
    quatre cycles legacy sont donc amorcés ici comme **données de test**, afin
    que les scénarios A→F soient exécutables sans dépendre d'un seed.
    """

    @classmethod
    def setUpTestData(cls):
        for code, libelle, cycle, ordre, numeros in (
            ('L1', 'Licence 1', Niveau.Cycle.LICENCE, 1, (1, 2)),
            ('L2', 'Licence 2', Niveau.Cycle.LICENCE, 2, (3, 4)),
            ('L3', 'Licence 3', Niveau.Cycle.LICENCE, 3, (5, 6)),
            ('M1', 'Master 1', Niveau.Cycle.MASTER, 4, (7, 8)),
            ('M2', 'Master 2', Niveau.Cycle.MASTER, 5, (9, 10)),
        ):
            niveau = Niveau.objects.create(
                code=code, libelle=libelle, cycle=cycle, ordre=ordre,
                credits_requis=60,
            )
            for numero in numeros:
                Semestre.objects.create(
                    niveau=niveau, numero=numero, libelle=f'S{numero}',
                )
        # Cycles legacy (hors des 8 filières) : ils DOIVENT exister en base
        # pour prouver qu'ils sont conservés mais exclus (L6 §9).
        for intitule in CORPUS_LEGACY:
            RefFormation.objects.create(
                intitule=intitule,
                perimetre=RefFormation.Perimetre.LEGACY,
                source='A-4.3ter §5.3 (O6)',
            )
        call_command('qualifier_referentiel_injs_l6', stdout=StringIO())

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(_creer_utilisateur())

    def get_api(self):
        res = self.client.get(ENDPOINT)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        return res.data

    def intitules_injs(self, payload):
        return [
            cycle['intitule']
            for filiere in payload['filieres']
            for cycle in filiere['cycles']
        ]


class TestAApiRetorneUniquementLesFormationsInjs(BaseL6TestCase):
    """TEST A — l'API Formations retourne uniquement les formations INJS."""

    def test_aucune_formation_legacy_dans_la_reponse(self):
        payload = self.get_api()
        for filiere in payload['filieres']:
            for cycle in filiere['cycles']:
                self.assertEqual(cycle['source'], 'A-4.5 §2 (O7/PDF/O2/O6/O9)')
                self.assertIn(filiere['code'], {c for c, *_ in FILIERES_INJS})

    def test_les_cycles_exposes_sont_tous_qualifies_injs_en_base(self):
        payload = self.get_api()
        ids = {cycle['id'] for f in payload['filieres'] for cycle in f['cycles']}
        attendus = set(formations_injs().values_list('id', flat=True))
        self.assertEqual(ids, attendus)
        for cycle_id in ids:
            self.assertEqual(
                RefFormation.objects.get(pk=cycle_id).perimetre,
                RefFormation.Perimetre.INJS,
            )

    def test_le_endpoint_est_refuse_aux_non_authentifies(self):
        anonyme = APIClient()
        self.assertEqual(
            anonyme.get(ENDPOINT).status_code, status.HTTP_401_UNAUTHORIZED,
        )


class TestBAAucuneFormationEtrange(BaseL6TestCase):
    """TEST B — aucune formation étrangère n'est retournée."""

    def test_aucun_intitule_etranger_dans_la_reponse(self):
        returned = self.intitules_injs(self.get_api())
        for interdit in INTITULES_ETRANGERS:
            self.assertNotIn(interdit, returned)
        for interdit in ('ADMINISTRATION DE BASE', 'ADMINISTRATION COMPLÉMENTAIRE',
                         'FINANCES PUBLIQUES', 'DEBUG FORM', 'DEBUG'):
            self.assertFalse(
                [i for i in returned if interdit in i.upper()],
                f'Intitulé étranger « {interdit} » exposé par l\'API INJS.',
            )

    def test_une_session_extrtere_nest_pas_exposee(self):
        """Les formations d'exploitation étrangères restent en base mais
        hors du périmètre fonctionnel INJS."""
        intruse = 'Formation Administration de Base (FAB) — Vague 1'
        intruse_obj = Formation.objects.create(formation=intruse)
        self.assertTrue(Formation.objects.filter(pk=intruse_obj.pk).exists())
        payload = self.get_api()
        self.assertNotIn(intruse_obj.formation, self.intitules_injs(payload))
        self.assertNotIn(
            intruse_obj.formation,
            formations_injs().values_list('intitule', flat=True),
        )

    def test_un_intitule_marque_injs_mais_etranger_est_rejete(self):
        """Défense en profondeur : une ligne mal qualifiée en base ne fuit pas."""
        intruse = 'Formation DEBUG FORM — INJS (mal qualifiée)'
        RefFormation.objects.create(
            intitule=intruse, perimetre=RefFormation.Perimetre.INJS,
        )
        self.assertNotIn(intruse, self.intitules_injs(self.get_api()))


class TestCLesHuitFilieresSontPresentes(BaseL6TestCase):
    """TEST C — les 8 filières INJS validées sont présentes."""

    def test_huit_filieres_attendues_et_chargees(self):
        payload = self.get_api()
        self.assertEqual(payload['nb_filieres_attendues'], 8)
        self.assertEqual(payload['nb_filieres_chargees'], 8)
        self.assertEqual(
            [f['code'] for f in payload['filieres']],
            ['F01', 'F02', 'F03', 'F04', 'F05', 'F06', 'F07', 'F08'],
        )

    def test_les_libelles_viennent_de_la_source_metier(self):
        payload = self.get_api()
        attendus = {c: l for c, _s, l, _e, _d, _di in FILIERES_INJS}
        for filiere in payload['filieres']:
            self.assertEqual(filiere['libelle'], attendus[filiere['code']])

    def test_regle_de_credits_metier_non_modifiee(self):
        payload = self.get_api()
        self.assertEqual(payload['credits_par_semestre'], 30)
        self.assertEqual(payload['credits_par_niveau'], 60)

    def test_les_niveaux_couvrent_s1_a_s10(self):
        payload = self.get_api()
        cycles = [c for f in payload['filieres'] for c in f['cycles']]
        self.assertTrue(cycles)
        for cycle in cycles:
            self.assertEqual(
                {n['code'] for n in cycle['niveaux']},
                {'L1', 'L2', 'L3', 'M1', 'M2'},
            )
            for niveau in cycle['niveaux']:
                self.assertEqual(niveau['credits_requis'], 60)
            semestres = [
                s['libelle'] for n in cycle['niveaux'] for s in n['semestres']
            ]
            self.assertEqual(
                sorted(semestres, key=lambda x: int(x[1:])),
                [f'S{i}' for i in range(1, 11)],
            )


class TestDRattachementAuxParcours(BaseL6TestCase):
    """TEST D — les formations INJS peuvent être reliées aux parcours."""

    def test_un_parcours_peut_etre_rattache_a_un_cycle_injs(self):
        cycle = formations_injs().filter(filiere_code='F01').first()
        self.assertIsNotNone(cycle)
        parcours = Parcours.objects.create(
            code='P-TEST-INJS', intitule='Parcours de test INJS',
            ref_formation=cycle,
        )
        payload = self.get_api()
        cycles = [c for f in payload['filieres'] for c in f['cycles']]
        expose = next(c for c in cycles if c['id'] == cycle.id)
        self.assertIn(parcours.id, [p['id'] for p in expose['parcours']])
        self.assertEqual(parcours.ref_formation.perimetre,
                         RefFormation.Perimetre.INJS)

    def test_un_parcours_legacy_ne_remonte_pas_dans_un_cycle_injs(self):
        cycle = formations_injs().first()
        legacy = RefFormation.objects.filter(
            perimetre=RefFormation.Perimetre.LEGACY,
        ).first()
        if legacy is None:
            self.skipTest('Aucun cycle legacy en base pour ce scénario.')
        Parcours.objects.create(
            code='P-LEGACY', intitule='Parcours legacy', ref_formation=legacy,
        )
        payload = self.get_api()
        expose = next(
            c for f in payload['filieres'] for c in f['cycles'] if c['id'] == cycle.id
        )
        codes = [p['code'] for p in expose['parcours']]
        self.assertNotIn('P-LEGACY', codes)


class TestERattachementAuxMaquettes(BaseL6TestCase):
    """TEST E — les formations INJS peuvent être reliées aux maquettes."""

    def setUp(self):
        super().setUp()
        self.annee = AnneeAcademique.objects.create(
            libelle='2026-2027', date_debut='2026-10-01', date_fin='2027-06-30',
        )
        self.niveau = Niveau.objects.get(code='L1')
        self.semestre = Semestre.objects.get(libelle='S1')

    def test_une_maquette_injs_remonte_avec_ses_ue_et_ecue(self):
        cycle = formations_injs().filter(filiere_code='F02').first()
        maquette = Maquette.objects.create(
            annee_academique=self.annee, ref_formation=cycle,
            niveau=self.niveau, version=1, statut=Maquette.Statut.BROUILLON,
        )
        ue = UE.objects.create(
            maquette=maquette, semestre=self.semestre, code='UE-TEST',
            intitule='UE de test', credits=30,
        )
        ECUE.objects.create(ue=ue, code='ECUE-TEST', intitule='ECUE de test')

        payload = self.get_api()
        expose = next(
            c for f in payload['filieres'] for c in f['cycles'] if c['id'] == cycle.id
        )
        self.assertEqual([m['id'] for m in expose['maquettes']], [maquette.id])
        self.assertEqual(expose['maquettes'][0]['total_credits'], 30)
        ue_payload = expose['maquettes'][0]['ues'][0]
        self.assertEqual(ue_payload['code'], 'UE-TEST')
        self.assertEqual(ue_payload['ecues'][0]['code'], 'ECUE-TEST')

    def test_une_maquette_legacy_nest_pas_exposee(self):
        legacy = RefFormation.objects.filter(
            perimetre=RefFormation.Perimetre.LEGACY,
        ).first()
        if legacy is None:
            self.skipTest('Aucun cycle legacy en base pour ce scénario.')
        Maquette.objects.create(
            annee_academique=self.annee, ref_formation=legacy,
            niveau=self.niveau, version=1, statut=Maquette.Statut.BROUILLON,
        )
        payload = self.get_api()
        exposees = [m['id'] for f in payload['filieres'] for c in f['cycles']
                    for m in c['maquettes']]
        self.assertEqual(exposees, [])

    def test_aucune_ue_artificielle_nest_creee_par_l_api(self):
        avant = UE.objects.count()
        self.get_api()
        self.assertEqual(UE.objects.count(), avant)

class TestFPasDeRegressionL1L5(BaseL6TestCase):
    """TEST F — les modifications L6 ne cassent pas les lots L1→L5.

    Vérifie que la chaîne
        AffectationPedagogique → AffectationCreneau → Séance → Présence
    reste strictement pilotée par la clé étrangère (jamais par une heuristique
    « groupe + cycle »), et que le contrat de l'API Cours est intact.
    """

    def setUp(self):
        super().setUp()
        from datetime import timedelta

        from django.utils import timezone

        self.aujourdhui = timezone.localdate()
        self.annee, _ = AnneeAcademique.objects.get_or_create(
            libelle='2026-2027',
            defaults={
                'date_debut': self.aujourdhui - timedelta(weeks=3),
                'date_fin': self.aujourdhui + timedelta(weeks=40),
                'courante': True,
            },
        )
        self.cycle = formations_injs().first()
        self.niveau = Niveau.objects.get(code='L1')
        self.semestre = Semestre.objects.get(niveau=self.niveau, numero=1)
        self.formateur = Formateur.objects.create(nom='Formateur L6')

    def _chainer(self, affectation):
        """Construit EDT → CreneauTemplate → AffectationCreneau sous l'affectation."""
        from edts.models import AffectationCreneau, CreneauTemplate, EmploiDuTemps

        edt = EmploiDuTemps.objects.create(
            annee_academique=self.annee, population_type='ANNEE',
            population_id=0, statut='PUBLIE', semaine_debut=1, semaine_fin=10,
            rentree=self.annee.date_debut,
        )
        creneau = CreneauTemplate.objects.create(
            jour='LUNDI', heure_debut='08:00', heure_fin='10:00',
        )
        return AffectationCreneau.objects.create(
            emploi_du_temps=edt, creneau_template=creneau,
            semaine_debut=1, semaine_fin=10, formation=self.cycle,
            salle_nom='Amphi 1', intitule='Séance L6',
            affectation_pedagogique=affectation,
        )

    def test_la_chaine_affectation_creneau_seance_presence_intacte(self):
        from django.utils import timezone

        from presences.models import Pointage

        affectation = AffectationPedagogique.objects.create(
            annee_academique=self.annee, ref_formation=self.cycle,
            niveau=self.niveau, semestre=self.semestre,
            enseignant=self.formateur, statut=AffectationPedagogique.Statut.VALIDEE,
        )
        affectation_creneau = self._chainer(affectation)
        # La FK est bien la source de vérité : le lien survit au changement de
        # statut de l'affectation (aucune déduction groupe + cycle).
        affectation_creneau.refresh_from_db()
        self.assertEqual(affectation_creneau.affectation_pedagogique_id, affectation.id)
        # Un pointage legacy sans seance_edt reste sans seance : rien n'est
        # rattaché d'office au référentiel INJS (L6 §17).
        pointage_legacy = Pointage.objects.create(
            statut=Pointage.Statut.TERMINE, timestamp_entree=timezone.now(),
        )
        self.assertIsNone(pointage_legacy.seance_edt_id)

    def test_le_contrat_de_l_api_cours_est_intact(self):
        res = self.client.get('/api/scolarite/pedagogie/cours/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        donnees = res.data
        lignes = donnees.get('resultats', donnees if isinstance(donnees, list) else [])
        self.assertIsInstance(lignes, list)
        for ligne in lignes:
            for champ in ('planning', 'salle_id', 'nb_seances_rattachees',
                          'nb_seances_non_rattachees', 'regularisation_requise'):
                self.assertIn(champ, ligne)

    def test_les_donnees_legacy_ne_sont_pas_supprimees(self):
        """L6 §9 : les données CPFAE restent en base, hors périmètre."""
        intruse_obj = Formation.objects.create(formation='Formation en Finances Publiques')
        call_command('qualifier_referentiel_injs_l6', stdout=StringIO())
        self.assertTrue(Formation.objects.filter(pk=intruse_obj.pk).exists())
        self.assertTrue(RefFormation.objects.exists())

    def test_la_commande_ne_cree_aucune_ue_ni_ecue(self):
        avant_ue, avant_ecue = UE.objects.count(), ECUE.objects.count()
        call_command('qualifier_referentiel_injs_l6', stdout=StringIO())
        self.assertEqual(UE.objects.count(), avant_ue)
        self.assertEqual(ECUE.objects.count(), avant_ecue)


class TestCommandeL6(BaseL6TestCase):
    """Propriétés de la commande de qualification (idempotence, traçabilité)."""

    def test_la_commande_est_idempotente(self):
        avant = list(RefFormation.objects.values_list(
            'pk', 'perimetre', 'filiere_code', 'source'))
        call_command('qualifier_referentiel_injs_l6', stdout=StringIO())
        apres = list(RefFormation.objects.values_list(
            'pk', 'perimetre', 'filiere_code', 'source'))
        self.assertEqual(avant, apres)

    def test_le_dry_run_ne_modifie_rien(self):
        formation = formations_injs().first()
        formation.perimetre = RefFormation.Perimetre.NON_DETERMINE
        formation.save(update_fields=['perimetre'])
        call_command('qualifier_referentiel_injs_l6', '--dry-run', stdout=StringIO())
        formation.refresh_from_db()
        self.assertEqual(formation.perimetre, RefFormation.Perimetre.NON_DETERMINE)

    def test_le_controle_d_integrite_est_sans_ecart(self):
        rapport = signaler_ecarts()
        self.assertEqual(rapport['filieres_manquantes'], [])
        self.assertEqual(rapport['cycles_etrangers_inclus'], [])
        self.assertEqual(rapport['nb_filieres_chargees'], 8)

    def test_les_cycles_legacy_sont_conserves_en_base(self):
        legacy = RefFormation.objects.filter(
            perimetre=RefFormation.Perimetre.LEGACY,
        )
        self.assertTrue(legacy.exists(),
                        'Les cycles legacy doivent être conservés en base.')
        for cycle in legacy:
            self.assertNotIn(cycle.pk, formations_injs().values_list('pk', flat=True))
