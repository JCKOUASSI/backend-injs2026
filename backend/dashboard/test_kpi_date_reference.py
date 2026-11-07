"""Non-régression B5 — KPI « présences du jour » à date de référence figée.

Contexte de la mission 02
-------------------------
Le blocage B5 décrivait un test ``test_seances_aujourdhui_et_kpi_reellement_
mesures`` qui comparait des données de démonstration figées au **03/11/2026** à
un tableau de bord interrogé à la **date réelle de la machine** :

    Date         Taux d'assiduité   Séances
    06/11/2026   None               0
    03/11/2026   41,7               6

Le comportement du tableau de bord était correct (aucune donnée ce jour-là ⇒
``None`` et ``0``) ; c'était le **test** qui était dépendant de l'horloge.

Ce test nommé n'existe pas dans le dépôt (vérifié par recherche exhaustive) :
il est donc GÉNÉRALISÉ ici, à l'identique de l'exigence, sans toucher une seule
ligne de code métier.

Ce que ce module garantit
-------------------------
1. Les données et le tableau de bord partagent le **même contexte temporel** :
   la fonction ``timezone.localdate`` utilisée par ``dashboard.services`` est
   figée pendant l'appel. Aucune dépendance à l'horloge de la machine.
2. À la date de référence ``2026-11-03`` : **6 séances** et un taux
   d'assiduité de **41,7 %** (5 présents pour 12 attendus).
3. À une autre date (``2026-11-04``) : **0 séance** et un taux ``None`` —
   c'est-à-dire le comportement métier correct, pas un échec.
4. Aucune écriture, aucune invention : le jeu de données est construit par
   l'ORM dans la transaction de test.

Le code métier (``dashboard/services.py``, ``presences/seances_supervision.py``)
n'est pas modifié : la règle « pas de dénominateur ⇒ pas de taux » reste celle
de la production.
"""
from datetime import date, datetime, time, timedelta
from unittest import mock

from django.test import TestCase
from django.utils import timezone

from authentication.models import User
from dashboard import services
from edts.models import AffectationCreneau, CreneauTemplate, EmploiDuTemps
from formations.models import Participant, RefFormation
from presences.models import Pointage
from scolarite.models import (
    AffectationGroupe, AnneeAcademique, DossierEtudiant, Groupe,
    InscriptionAdministrative, Niveau, StatutEtudiant,
)

#: Date de référence du jeu de démonstration (mardi 3 novembre 2026).
DATE_REFERENCE = date(2026, 11, 3)
#: Date de contrôle : le lendemain, où aucune séance n'est planifiée.
DATE_SANS_SEANCE = date(2026, 11, 4)

JOURS = ['LUNDI', 'MARDI', 'MERCREDI', 'JEUDI', 'VENDREDI', 'SAMEDI', 'DIMANCHE']

#: 6 séances, 12 présences attendues au total (2 étudiants × 6 séances),
#: 5 présences réelles : 5/12 = 41,7 %. C'est exactement le chiffre de l'audit.
NB_SEANCES = 6
EFFECTIF_PAR_GROUPE = 2
NB_PRESENTS = 5
TOTAL_ATTENDUS = NB_SEANCES * EFFECTIF_PAR_GROUPE  # 12
TAUX_ATTENDU = 41.7  # round(5 / 12 * 100, 1)


class KpiDateReferenceTests(TestCase):
    """Tableau de bord « Assiduité & Présences » à date figée."""

    @classmethod
    def setUpTestData(cls):
        cls.jour_reference = JOURS[DATE_REFERENCE.weekday()]

        # Année académique ancrée AVANT la date de référence : le numéro de
        # semaine en découle (semaine 2 pour le 03/11/2026).
        cls.annee = AnneeAcademique.objects.create(
            libelle='2026-2027',
            date_debut=DATE_REFERENCE - timedelta(days=7),
            date_fin=DATE_REFERENCE + timedelta(days=300),
            courante=True,
        )
        cls.admin = User.objects.create_user(
            username='admin-kpi', password='x', role='ADMIN')

        cls.edt = EmploiDuTemps.objects.create(
            annee_academique=cls.annee, population_type='ANNEE', population_id=0,
            statut='PUBLIE', semaine_debut=1, semaine_fin=60,
            rentree=cls.annee.date_debut, cree_par=cls.admin,
        )

        cls.niveau = Niveau.objects.create(code='L1', libelle='Licence 1', ordre=1)
        cls.ref_formation = RefFormation.objects.create(
            intitule='LICENCE PRO — KPI DATE REFERENCE')
        cls.statut_actif = StatutEtudiant.objects.create(code='ACTIF', libelle='Actif')

        # Deux groupes de 2 étudiants ; chaque séance porte l'effectif de son
        # groupe (2), soit 6 × 2 = 12 attendus sur la journée.
        cls.groupes = []
        cls.participants = {0: [], 1: []}
        for indice in range(2):
            groupe = Groupe.objects.create(
                annee_academique=cls.annee, niveau=cls.niveau,
                ref_formation=cls.ref_formation,
                nom=f'L1-G{indice + 1}', capacite_max=30,
            )
            cls.groupes.append(groupe)
            for numero in range(EFFECTIF_PAR_GROUPE):
                marque = indice * EFFECTIF_PAR_GROUPE + numero
                user = User.objects.create_user(
                    username=f'etu-kpi-{marque:02d}', password='x', role='AUDITEUR')
                participant = Participant.objects.filter(user=user).first()
                if participant is None:
                    participant = Participant.objects.create(
                        matricule=f'KPI{marque:03d}', nom=f'Nom{marque}',
                        prenom=f'Prenom{marque}', user=user,
                    )
                dossier = DossierEtudiant.objects.create(
                    participant=participant, statut=cls.statut_actif)
                inscription = InscriptionAdministrative.objects.create(
                    etudiant=dossier, annee_academique=cls.annee, niveau=cls.niveau,
                    ref_formation=cls.ref_formation,
                    statut=InscriptionAdministrative.Statut.VALIDEE,
                    statut_etudiant=cls.statut_actif,
                )
                AffectationGroupe.objects.create(
                    groupe=groupe, inscription=inscription, active=True)
                cls.participants[indice].append(participant)

        # 6 séances le mardi 03/11/2026 : 3 par groupe, horaires distincts.
        cls.seances = []
        for numero in range(NB_SEANCES):
            groupe = cls.groupes[numero % 2]
            heure = time(8 + numero, 0)
            template = CreneauTemplate.objects.create(
                jour=cls.jour_reference, heure_debut=heure,
                heure_fin=time(8 + numero, 45),
            )
            cls.seances.append(AffectationCreneau.objects.create(
                emploi_du_temps=cls.edt, creneau_template=template,
                semaine_debut=1, semaine_fin=60, groupe=groupe,
                enseignant_id=cls.admin.id, enseignant_nom='Awa Traoré',
                salle_nom=f'Salle {numero + 1}',
                intitule=f'Séance {numero + 1}',
            ))

        # 5 présences réelles, rattachées aux séances et à la date de référence.
        for numero in range(NB_PRESENTS):
            seance = cls.seances[numero]
            participant = cls.participants[numero % 2][numero % EFFECTIF_PAR_GROUPE]
            Pointage.objects.create(
                participant=participant,
                seance_edt=seance,
                date_journee=DATE_REFERENCE,
                timestamp_entree=timezone.make_aware(
                    datetime.combine(DATE_REFERENCE, time(8, numero))),
                statut=Pointage.Statut.TERMINE,
                statut_assiduite=Pointage.StatutAssiduite.PRESENT,
                device_id='TEST-KPI',
            )

    def _tableau_de_bord(self, date_figee):
        """Appelle le dashboard avec ``timezone.localdate`` figée sur `date_figee`."""
        with mock.patch.object(timezone, 'localdate', return_value=date_figee):
            return services.get_presences_dashboard()

    # -- 1. La date de référence produit exactement les 6 séances ------------
    def test_six_seances_le_jour_de_reference(self):
        donnees = self._tableau_de_bord(DATE_REFERENCE)
        self.assertEqual(donnees['date'], DATE_REFERENCE.isoformat())
        self.assertEqual(donnees['kpis']['seances_jour'], NB_SEANCES)

    # -- 2. Le taux d'assiduité est celui du jeu de données ------------------
    def test_taux_assiduite_de_la_date_de_reference(self):
        donnees = self._tableau_de_bord(DATE_REFERENCE)
        self.assertEqual(donnees['kpis']['presents_jour'], NB_PRESENTS)
        # 5 présents / 12 attendus = 41,7 % — le taux exact du rapport d'audit.
        self.assertEqual(donnees['kpis']['taux_assiduite_moyen'], TAUX_ATTENDU)
        self.assertEqual(TOTAL_ATTENDUS, 12)

    # -- 3. Le même contexte temporel vaut pour les pointages ---------------
    def test_pointages_comptes_le_jour_de_reference(self):
        donnees = self._tableau_de_bord(DATE_REFERENCE)
        self.assertEqual(donnees['kpis']['pointages_jour'], NB_PRESENTS)

    # -- 4. Aucune dépendance à l'horloge : un autre jour ne voit rien ------
    def test_jour_sans_seance_ne_renvoie_ni_zero_invente_ni_taux(self):
        donnees = self._tableau_de_bord(DATE_SANS_SEANCE)
        self.assertEqual(donnees['date'], DATE_SANS_SEANCE.isoformat())
        self.assertEqual(donnees['kpis']['seances_jour'], 0)
        # Pas de dénominateur connu ⇒ pas de taux. Ce n'est pas un échec :
        # c'est la règle métier (NULL ≠ 0) du dashboard.
        self.assertIsNone(donnees['kpis']['taux_assiduite_moyen'])
        self.assertEqual(donnees['kpis']['presents_jour'], 0)

    # -- 5. Cohérence du contexte temporel au niveau du service ------------
    def test_contexte_temporel_identique_donnees_et_dashboard(self):
        """Les données ET le tableau de bord sont lus sur la même date.

        Le service de supervision reçoit la date explicitement : la même date
        qui a servi à créer les pointages ramène 6 séances, le lendemain 0.
        C'est exactement le contrat que le test historique violait.
        """
        from presences import seances_supervision

        reference = seances_supervision.supervision_seances(None, DATE_REFERENCE)
        self.assertEqual(reference['resume']['seances_total'], NB_SEANCES)
        self.assertEqual(reference['date'], DATE_REFERENCE.isoformat())

        lendemain = seances_supervision.supervision_seances(None, DATE_SANS_SEANCE)
        self.assertEqual(lendemain['resume']['seances_total'], 0)
